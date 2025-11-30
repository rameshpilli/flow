"""
Context Builder Service

Extracts context from user request:
- Customer Firm Extractor: Company info from foundation service
- Temporal Context Extractor: Earnings dates, fiscal periods
- RBC Persona Extractor: RBC employee info from LDAP
- Corporate Client Persona Extractor: Client info from ZoomInfo

This is the first stage of the CMPT chain.
"""

import asyncio
import logging
from datetime import date, datetime
from difflib import SequenceMatcher
from typing import Any

from flowforge.services.models import (
    ChainRequest,
    ChainRequestOverrides,
    CompanyInfo,
    ContextBuilderOutput,
    PersonaInfo,
    TemporalContext,
)

logger = logging.getLogger(__name__)


class ContextBuilderService:
    """
    Service for extracting context from meeting requests.

    Usage:
        service = ContextBuilderService()
        output = await service.execute(request)

    Or as a step in FlowForge:
        @forge.step(produces=["context_builder_output"])
        async def context_builder(ctx):
            service = ContextBuilderService()
            output = await service.execute(ctx.get("request"))
            ctx.set("context_builder_output", output)
            return output.model_dump()
    """

    # Configuration
    HTTP_TIMEOUT: float = 20.0
    DEFAULT_NEWS_LOOKBACK_DAYS: int = 30
    DEFAULT_FILING_QUARTERS: int = 8

    # Default per-extractor time budgets (seconds)
    DEFAULT_EXTRACTOR_TIMEOUTS: dict[str, float] = {
        "firm": 10.0,           # Company lookup
        "temporal": 5.0,        # Earnings calendar
        "rbc_persona": 5.0,     # LDAP lookup
        "client_persona": 8.0,  # ZoomInfo lookup
    }

    def __init__(
        self,
        http_timeout: float = 20.0,
        company_match_url: str | None = None,
        earnings_calendar_url: str | None = None,
        extractor_timeouts: dict[str, float] | None = None,
    ):
        """
        Initialize the Context Builder service.

        Args:
            http_timeout: HTTP request timeout in seconds
            company_match_url: URL for company matching service
            earnings_calendar_url: URL for earnings calendar service
            extractor_timeouts: Per-extractor time budgets in seconds
                Keys: "firm", "temporal", "rbc_persona", "client_persona"
                If not specified, uses DEFAULT_EXTRACTOR_TIMEOUTS
        """
        self.http_timeout = http_timeout
        self.company_match_url = company_match_url
        self.earnings_calendar_url = earnings_calendar_url
        self.extractor_timeouts = {
            **self.DEFAULT_EXTRACTOR_TIMEOUTS,
            **(extractor_timeouts or {}),
        }

    async def execute(
        self,
        request: ChainRequest,
    ) -> ContextBuilderOutput:
        """
        Execute all context extraction steps.

        Args:
            request: The chain request with meeting details

        Returns:
            ContextBuilderOutput with all extracted context

        User Overrides:
            If request.overrides is provided, those values take precedence
            over API-extracted values. Overrides can also skip API calls entirely.
        """
        start_time = datetime.now()
        timing: dict[str, float] = {}
        errors: dict[str, str] = {}
        overrides = request.overrides or ChainRequestOverrides()

        # Initialize output
        output = ContextBuilderOutput(errors={}, timing_ms={})

        # Run extractors in parallel where possible
        tasks = []

        # 1. Corporate Client Firm Extractor (can be skipped via override)
        if request.corporate_company_name and not overrides.skip_company_lookup:
            tasks.append(("firm", self._extract_firm(request.corporate_company_name)))

        # 2. Temporal Context Extractor (depends on firm result for ticker)
        # Will run after firm extraction

        # 3. RBC Persona Extractor
        if request.rbc_employee_email:
            tasks.append(("rbc_persona", self._extract_rbc_persona(request.rbc_employee_email)))

        # 4. Corporate Client Persona Extractor
        if request.corporate_client_email or request.corporate_client_names:
            tasks.append(
                (
                    "client_persona",
                    self._extract_client_persona(
                        email=request.corporate_client_email,
                        names=request.corporate_client_names,
                        company_name=request.corporate_company_name,
                    ),
                )
            )

        # Execute parallel tasks with per-extractor timeouts
        if tasks:
            # Wrap each task with asyncio.wait_for for timeout protection
            wrapped_tasks = []
            for name, coro in tasks:
                timeout = self.extractor_timeouts.get(name, 10.0)
                wrapped_tasks.append((name, asyncio.wait_for(coro, timeout=timeout)))

            results = await asyncio.gather(
                *[task[1] for task in wrapped_tasks],
                return_exceptions=True,
            )

            for (name, _), result in zip(wrapped_tasks, results):
                if isinstance(result, asyncio.TimeoutError):
                    timeout = self.extractor_timeouts.get(name, 10.0)
                    errors[name] = f"Extractor timed out after {timeout}s"
                    logger.error(f"Extractor {name} timed out after {timeout}s")
                elif isinstance(result, Exception):
                    errors[name] = str(result)
                    logger.error(f"Extractor {name} failed: {result}")
                else:
                    data, error, duration = result
                    timing[name] = duration

                    if error:
                        errors[name] = error
                    else:
                        self._apply_result(output, name, data)

        # Extract firm info first to get ticker for temporal context
        # Apply user overrides to company info
        if output.company_info:
            output.company_info = self._apply_company_overrides(output.company_info, overrides)
        elif overrides.skip_company_lookup and request.corporate_company_name:
            # Create minimal company info from overrides when API is skipped
            output.company_info = CompanyInfo(
                name=request.corporate_company_name,
                ticker=overrides.ticker,
                cik=overrides.company_cik,
                industry=overrides.industry,
                sector=overrides.sector,
            )

        ticker = overrides.ticker or (output.company_info.ticker if output.company_info else None)

        # 2. Temporal Context Extractor (needs ticker or company name)
        # Can be skipped if user provides fiscal quarter override
        if not overrides.skip_earnings_calendar_api and (request.corporate_company_name or ticker):
            temporal_timeout = self.extractor_timeouts.get("temporal", 5.0)
            try:
                temporal_start = datetime.now()
                temporal_data, temporal_error = await asyncio.wait_for(
                    self._extract_temporal_context(
                        company_name=request.corporate_company_name,
                        ticker=ticker,
                        meeting_datetime=request.meeting_datetime,
                    ),
                    timeout=temporal_timeout,
                )
                timing["temporal"] = (datetime.now() - temporal_start).total_seconds() * 1000

                if temporal_error:
                    errors["temporal"] = temporal_error
                else:
                    output.temporal_context = temporal_data
            except asyncio.TimeoutError:
                errors["temporal"] = f"Extractor timed out after {temporal_timeout}s"
                logger.error(f"Temporal extractor timed out after {temporal_timeout}s")
            except Exception as e:
                errors["temporal"] = str(e)
                logger.error(f"Temporal extractor failed: {e}")
        elif overrides.skip_earnings_calendar_api or overrides.fiscal_quarter:
            # Create temporal context from overrides/computed values
            output.temporal_context = self._create_temporal_from_overrides(
                request.meeting_datetime, overrides
            )

        # Apply temporal overrides
        if output.temporal_context:
            output.temporal_context = self._apply_temporal_overrides(
                output.temporal_context, overrides
            )

        # Set resolved company name
        if output.company_info:
            output.company_name = output.company_info.name
            output.ticker = output.company_info.ticker

        # Apply persona overrides
        if output.rbc_persona:
            output.rbc_persona = self._apply_rbc_persona_overrides(
                output.rbc_persona, overrides
            )
        if output.corporate_client_personas:
            output.corporate_client_personas = [
                self._apply_client_persona_overrides(p, overrides)
                for p in output.corporate_client_personas
            ]

        output.errors = errors
        output.timing_ms = timing

        total_duration = (datetime.now() - start_time).total_seconds() * 1000
        timing["total"] = total_duration

        logger.info(f"Context builder completed in {total_duration:.2f}ms")
        return output

    def _apply_result(
        self,
        output: ContextBuilderOutput,
        name: str,
        data: Any,
    ) -> None:
        """Apply extractor result to output"""
        if name == "firm" and data:
            output.company_info = data
            output.raw_firm_response = data.model_dump() if hasattr(data, "model_dump") else data
        elif name == "rbc_persona" and data:
            output.rbc_persona = data
        elif name == "client_persona" and data:
            if isinstance(data, list):
                output.corporate_client_personas = data
            else:
                output.corporate_client_personas = [data] if data else []

    # ═══════════════════════════════════════════════════════════════════════════
    #                           EXTRACTORS
    # ═══════════════════════════════════════════════════════════════════════════

    async def _extract_firm(
        self,
        company_name: str,
    ) -> tuple[CompanyInfo | None, str | None, float]:
        """
        Extract company information from foundation service.

        Returns:
            Tuple of (CompanyInfo, error_message, duration_ms)
        """
        start = datetime.now()
        error = None
        result = None

        try:
            # In production, this would call the foundation service
            # For now, return mock data
            logger.info(f"Extracting firm info for: {company_name}")

            # Mock implementation - replace with actual API call
            result = CompanyInfo(
                name=company_name,
                ticker=company_name[:4].upper() if len(company_name) >= 4 else company_name.upper(),
                industry="Technology",
                sector="Information Technology",
                market_cap="Large Cap",
                country="United States",
            )

        except Exception as e:
            error = str(e)
            logger.error(f"Firm extraction failed: {e}")

        duration = (datetime.now() - start).total_seconds() * 1000
        return result, error, duration

    async def _extract_temporal_context(
        self,
        company_name: str | None = None,
        ticker: str | None = None,
        meeting_datetime: str | None = None,
    ) -> tuple[TemporalContext | None, str | None]:
        """
        Extract temporal context based on company and meeting date.

        Returns:
            Tuple of (TemporalContext, error_message)
        """
        error = None
        result = None

        try:
            # Parse meeting date
            meeting_date = None
            if meeting_datetime:
                try:
                    meeting_date = datetime.fromisoformat(
                        meeting_datetime.replace("Z", "+00:00")
                    ).date()
                except ValueError:
                    meeting_date = date.today()
            else:
                meeting_date = date.today()

            # Determine current quarter
            quarter = (meeting_date.month - 1) // 3 + 1
            fiscal_quarter = str(quarter)
            fiscal_year = str(meeting_date.year)

            # In production, call earnings calendar API
            # For now, create mock temporal context
            result = TemporalContext(
                meeting_date=str(meeting_date),
                fiscal_quarter=fiscal_quarter,
                fiscal_year=fiscal_year,
                days_to_earnings=None,  # Would come from API
                news_lookback_days=self.DEFAULT_NEWS_LOOKBACK_DAYS,
                filing_quarters=self.DEFAULT_FILING_QUARTERS,
            )

        except Exception as e:
            error = str(e)
            logger.error(f"Temporal extraction failed: {e}")

        return result, error

    async def _extract_rbc_persona(
        self,
        email: str,
    ) -> tuple[PersonaInfo | None, str | None, float]:
        """
        Extract RBC employee persona from LDAP.

        Returns:
            Tuple of (PersonaInfo, error_message, duration_ms)
        """
        start = datetime.now()
        error = None
        result = None

        try:
            logger.info(f"Extracting RBC persona for: {email}")

            # In production, this would call LDAP service
            # For now, return mock data
            name_parts = email.split("@")[0].split(".")
            first_name = name_parts[0].title() if name_parts else ""
            last_name = name_parts[1].title() if len(name_parts) > 1 else ""

            result = PersonaInfo(
                name=f"{first_name} {last_name}".strip(),
                first_name=first_name,
                last_name=last_name,
                email=email,
                is_internal=True,
                source="LDAP",
            )

        except Exception as e:
            error = str(e)
            logger.error(f"RBC persona extraction failed: {e}")

        duration = (datetime.now() - start).total_seconds() * 1000
        return result, error, duration

    async def _extract_client_persona(
        self,
        email: str | None = None,
        names: str | None = None,
        company_name: str | None = None,
    ) -> tuple[list | None, str | None, float]:
        """
        Extract corporate client persona from ZoomInfo.

        Returns:
            Tuple of (list of PersonaInfo, error_message, duration_ms)
        """
        start = datetime.now()
        error = None
        result = []

        try:
            logger.info(f"Extracting client persona: email={email}, names={names}")

            # In production, this would call ZoomInfo service
            # For now, return mock data
            if email:
                name_parts = email.split("@")[0].split(".")
                first_name = name_parts[0].title() if name_parts else ""
                last_name = name_parts[1].title() if len(name_parts) > 1 else ""

                result = [
                    PersonaInfo(
                        name=f"{first_name} {last_name}".strip(),
                        first_name=first_name,
                        last_name=last_name,
                        email=email,
                        company=company_name,
                        is_internal=False,
                        source="ZoomInfo",
                    )
                ]

            elif names:
                # Parse comma-separated names
                for name in names.split(","):
                    name = name.strip()
                    if name:
                        parts = name.split()
                        result.append(
                            PersonaInfo(
                                name=name,
                                first_name=parts[0] if parts else "",
                                last_name=parts[-1] if len(parts) > 1 else "",
                                company=company_name,
                                is_internal=False,
                                source="ZoomInfo",
                            )
                        )

        except Exception as e:
            error = str(e)
            logger.error(f"Client persona extraction failed: {e}")

        duration = (datetime.now() - start).total_seconds() * 1000
        return result, error, duration

    # ═══════════════════════════════════════════════════════════════════════════
    #                           UTILITIES
    # ═══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def rank_profiles_by_company(
        profiles: list,
        user_company: str,
    ) -> list:
        """
        Rank profiles by similarity to user's company name.

        Args:
            profiles: List of profile dictionaries
            user_company: Target company name to match

        Returns:
            Sorted list of profiles with company_similarity_score added
        """
        if not profiles or not user_company:
            return profiles

        for profile in profiles:
            company_from_profile = profile.get("company", "") or profile.get("department", "")

            if company_from_profile:
                similarity = SequenceMatcher(
                    None, user_company.lower(), company_from_profile.lower()
                ).ratio()
                profile["company_similarity_score"] = similarity
            else:
                profile["company_similarity_score"] = 0.0

        return sorted(profiles, key=lambda x: x.get("company_similarity_score", 0), reverse=True)

    # ═══════════════════════════════════════════════════════════════════════════
    #                       USER OVERRIDE HELPERS
    # ═══════════════════════════════════════════════════════════════════════════

    def _apply_company_overrides(
        self,
        company_info: CompanyInfo,
        overrides: ChainRequestOverrides,
    ) -> CompanyInfo:
        """
        Apply user overrides to company info.

        Overrides take precedence over API-extracted values.
        """
        # Create a dict from the existing company info
        data = company_info.model_dump()

        # Apply overrides where provided
        if overrides.ticker:
            data["ticker"] = overrides.ticker
        if overrides.company_cik:
            data["cik"] = overrides.company_cik
        if overrides.industry:
            data["industry"] = overrides.industry
        if overrides.sector:
            data["sector"] = overrides.sector

        return CompanyInfo(**data)

    def _apply_temporal_overrides(
        self,
        temporal: TemporalContext,
        overrides: ChainRequestOverrides,
    ) -> TemporalContext:
        """
        Apply user overrides to temporal context.

        Overrides take precedence over API-extracted values.
        """
        data = temporal.model_dump()

        # Apply overrides where provided
        if overrides.fiscal_quarter:
            # Normalize quarter format (Q1, Q2, etc.)
            q = overrides.fiscal_quarter.upper().replace("Q", "").strip()
            data["fiscal_quarter"] = q
        if overrides.fiscal_year:
            # Normalize year format
            year = overrides.fiscal_year.upper().replace("FY", "").strip()
            data["fiscal_year"] = year
        if overrides.next_earnings_date:
            data["event_dt"] = overrides.next_earnings_date
        if overrides.news_lookback_days:
            data["news_lookback_days"] = overrides.news_lookback_days
        if overrides.filing_quarters:
            data["filing_quarters"] = overrides.filing_quarters

        return TemporalContext(**data)

    def _create_temporal_from_overrides(
        self,
        meeting_datetime: str | None,
        overrides: ChainRequestOverrides,
    ) -> TemporalContext:
        """
        Create temporal context from user overrides when API is skipped.

        Uses computed quarter from meeting date if not provided in overrides.
        """
        # Parse meeting date
        meeting_date = None
        if meeting_datetime:
            try:
                meeting_date = datetime.fromisoformat(
                    meeting_datetime.replace("Z", "+00:00")
                ).date()
            except ValueError:
                meeting_date = date.today()
        else:
            meeting_date = date.today()

        # Compute quarter from meeting date if not overridden
        if overrides.fiscal_quarter:
            q = overrides.fiscal_quarter.upper().replace("Q", "").strip()
            fiscal_quarter = q
        else:
            quarter = (meeting_date.month - 1) // 3 + 1
            fiscal_quarter = str(quarter)

        # Get fiscal year
        if overrides.fiscal_year:
            fiscal_year = overrides.fiscal_year.upper().replace("FY", "").strip()
        else:
            fiscal_year = str(meeting_date.year)

        return TemporalContext(
            meeting_date=str(meeting_date),
            fiscal_quarter=fiscal_quarter,
            fiscal_year=fiscal_year,
            event_dt=overrides.next_earnings_date,
            news_lookback_days=overrides.news_lookback_days or self.DEFAULT_NEWS_LOOKBACK_DAYS,
            filing_quarters=overrides.filing_quarters or self.DEFAULT_FILING_QUARTERS,
        )

    def _apply_rbc_persona_overrides(
        self,
        persona: PersonaInfo,
        overrides: ChainRequestOverrides,
    ) -> PersonaInfo:
        """
        Apply user overrides to RBC persona.
        """
        data = persona.model_dump()

        if overrides.rbc_persona_name:
            data["name"] = overrides.rbc_persona_name
            parts = overrides.rbc_persona_name.split()
            if parts:
                data["first_name"] = parts[0]
                data["last_name"] = parts[-1] if len(parts) > 1 else ""
        if overrides.rbc_persona_role:
            data["role"] = overrides.rbc_persona_role

        return PersonaInfo(**data)

    def _apply_client_persona_overrides(
        self,
        persona: PersonaInfo,
        overrides: ChainRequestOverrides,
    ) -> PersonaInfo:
        """
        Apply user overrides to client persona.

        Note: Only applies to the first client persona if multiple exist.
        """
        data = persona.model_dump()

        if overrides.client_persona_name:
            data["name"] = overrides.client_persona_name
            parts = overrides.client_persona_name.split()
            if parts:
                data["first_name"] = parts[0]
                data["last_name"] = parts[-1] if len(parts) > 1 else ""
        if overrides.client_persona_role:
            data["role"] = overrides.client_persona_role

        return PersonaInfo(**data)
