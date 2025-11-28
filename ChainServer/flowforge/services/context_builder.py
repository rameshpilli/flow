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

    def __init__(
        self,
        http_timeout: float = 20.0,
        company_match_url: str | None = None,
        earnings_calendar_url: str | None = None,
    ):
        """
        Initialize the Context Builder service.

        Args:
            http_timeout: HTTP request timeout in seconds
            company_match_url: URL for company matching service
            earnings_calendar_url: URL for earnings calendar service
        """
        self.http_timeout = http_timeout
        self.company_match_url = company_match_url
        self.earnings_calendar_url = earnings_calendar_url

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
        """
        start_time = datetime.now()
        timing: dict[str, float] = {}
        errors: dict[str, str] = {}

        # Initialize output
        output = ContextBuilderOutput(errors={}, timing_ms={})

        # Run extractors in parallel where possible
        tasks = []

        # 1. Corporate Client Firm Extractor
        if request.corporate_company_name:
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

        # Execute parallel tasks
        if tasks:
            results = await asyncio.gather(*[task[1] for task in tasks], return_exceptions=True)

            for (name, _), result in zip(tasks, results):
                task_end = datetime.now()

                if isinstance(result, Exception):
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
        if output.company_info and output.company_info.ticker:
            ticker = output.company_info.ticker
        else:
            ticker = None

        # 2. Temporal Context Extractor (needs ticker or company name)
        if request.corporate_company_name or ticker:
            try:
                temporal_start = datetime.now()
                temporal_data, temporal_error = await self._extract_temporal_context(
                    company_name=request.corporate_company_name,
                    ticker=ticker,
                    meeting_datetime=request.meeting_datetime,
                )
                timing["temporal"] = (datetime.now() - temporal_start).total_seconds() * 1000

                if temporal_error:
                    errors["temporal"] = temporal_error
                else:
                    output.temporal_context = temporal_data
            except Exception as e:
                errors["temporal"] = str(e)
                logger.error(f"Temporal extractor failed: {e}")

        # Set resolved company name
        if output.company_info:
            output.company_name = output.company_info.name
            output.ticker = output.company_info.ticker

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
            current_quarter = f"Q{quarter} {meeting_date.year}"
            fiscal_year = f"FY{meeting_date.year}"

            # In production, call earnings calendar API
            # For now, create mock temporal context
            result = TemporalContext(
                meeting_date=meeting_date,
                current_quarter=current_quarter,
                fiscal_year=fiscal_year,
                days_to_earnings=None,  # Would come from API
                lookback_period="12 months",
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
