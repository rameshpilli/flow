"""
Context Builder Service - Stage 1 of the CMPT Chain

Extracts context from user request by calling external APIs:
- Foundation Service: Query resolution (company name → ticker, industry)
- Foundation Service: Earnings calendar (earnings dates)
- LDAP: RBC employee info (TODO: implement real API)
- ZoomInfo: Client persona info (TODO: implement real API)
"""

import asyncio
import logging
import os
from datetime import date, datetime
from typing import Any

import httpx

from cmpt.services.models import (
    ChainRequest,
    ChainRequestOverrides,
    CompanyInfo,
    ContextBuilderOutput,
    PersonaInfo,
    TemporalContext,
)

logger = logging.getLogger(__name__)

# Foundation Service URLs
FOUNDATION_BASE_URL = os.getenv(
    "FOUNDATION_BASE_URL",
    "https://tg40-aiden-foundation-service.cfk.devfg.rbc.com"
)
FOUNDATION_QUERY_RESOLUTION_URL = os.getenv(
    "FOUNDATION_QUERY_RESOLUTION_URL",
    f"{FOUNDATION_BASE_URL}/query_resolution"
)
FOUNDATION_EARNINGS_CALENDAR_URL = os.getenv(
    "FOUNDATION_EARNING_CALENDAR_URL",
    f"{FOUNDATION_BASE_URL}/company_earnings_calendar"
)


class ContextBuilderService:
    """
    Extracts context from meeting requests via external APIs.

    Usage:
        service = ContextBuilderService()
        output = await service.execute(request)
    """

    HTTP_TIMEOUT: float = 20.0
    DEFAULT_NEWS_LOOKBACK_DAYS: int = 30
    DEFAULT_FILING_QUARTERS: int = 8
    DEFAULT_EXTRACTOR_TIMEOUTS: dict[str, float] = {
        "firm_temporal": 10.0,
        "rbc_persona": 5.0,
        "client_persona": 8.0,
    }

    def __init__(self, http_timeout: float = 20.0, extractor_timeouts: dict[str, float] | None = None):
        self.http_timeout = http_timeout
        self.extractor_timeouts = {**self.DEFAULT_EXTRACTOR_TIMEOUTS, **(extractor_timeouts or {})}

    async def execute(self, request: ChainRequest) -> ContextBuilderOutput:
        """Execute all context extraction steps."""
        start_time = datetime.now()
        timing: dict[str, float] = {}
        errors: dict[str, str] = {}
        overrides = request.overrides or ChainRequestOverrides()
        output = ContextBuilderOutput(errors={}, timing_ms={})

        # Build list of extractors to run in parallel
        tasks = []

        # Firm + Temporal extraction via earnings calendar API
        # The API accepts company_name and returns company info + earnings dates
        if request.corporate_company_name and not overrides.skip_earnings_calendar_api:
            tasks.append(("firm_temporal", self._extract_firm_and_temporal(
                company_name=request.corporate_company_name,
                ticker=overrides.ticker,
                meeting_datetime=request.meeting_datetime,
                earnings_override=overrides.next_earnings_date,
            )))

        if request.rbc_employee_email:
            tasks.append(("rbc_persona", self._extract_rbc_persona(request.rbc_employee_email)))

        if request.corporate_client_email or request.corporate_client_names:
            tasks.append(("client_persona", self._extract_client_persona(
                email=request.corporate_client_email,
                names=request.corporate_client_names,
                company_name=request.corporate_company_name,
            )))

        # Execute parallel tasks
        if tasks:
            wrapped = [(name, asyncio.wait_for(coro, timeout=self.extractor_timeouts.get(name, 10.0)))
                       for name, coro in tasks]
            results = await asyncio.gather(*[t[1] for t in wrapped], return_exceptions=True)

            for (name, _), result in zip(wrapped, results):
                if isinstance(result, asyncio.TimeoutError):
                    errors[name] = f"Timed out after {self.extractor_timeouts.get(name, 10.0)}s"
                elif isinstance(result, Exception):
                    errors[name] = str(result)
                else:
                    data, error, duration = result
                    timing[name] = duration
                    if error:
                        errors[name] = error
                    elif data:
                        self._apply_result(output, name, data)

        # Fallback: create company info from request if API failed
        if not output.company_info and request.corporate_company_name:
            output.company_info = CompanyInfo(
                name=request.corporate_company_name,
                ticker=overrides.ticker,
                cik=overrides.company_cik,
                industry=overrides.industry,
                sector=overrides.sector,
            )

        # Fallback: create temporal context if API failed
        if not output.temporal_context:
            output.temporal_context = self._create_default_temporal(request.meeting_datetime, overrides)

        # Apply overrides
        if output.company_info:
            output.company_info = self._apply_company_overrides(output.company_info, overrides)
        if output.temporal_context:
            output.temporal_context = self._apply_temporal_overrides(output.temporal_context, overrides)

        # Set resolved company name and ticker
        if output.company_info:
            output.company_name = output.company_info.name
            output.ticker = output.company_info.ticker

        output.errors = errors
        output.timing_ms = timing
        timing["total"] = (datetime.now() - start_time).total_seconds() * 1000
        logger.info(f"Context builder completed in {timing['total']:.0f}ms")
        return output

    def _apply_result(self, output: ContextBuilderOutput, name: str, data: Any) -> None:
        """Apply extractor result to output."""
        if name == "firm_temporal":
            company_info, temporal_context = data
            if company_info:
                output.company_info = company_info
                output.raw_firm_response = company_info.model_dump()
            if temporal_context:
                output.temporal_context = temporal_context
        elif name == "rbc_persona":
            output.rbc_persona = data
        elif name == "client_persona":
            output.corporate_client_personas = data if isinstance(data, list) else [data] if data else []

    # ═══════════════════════════════════════════════════════════════════════════
    # EXTRACTORS
    # ═══════════════════════════════════════════════════════════════════════════

    async def _extract_firm_and_temporal(
        self,
        company_name: str,
        ticker: str | None,
        meeting_datetime: str | None,
        earnings_override: str | None,
    ) -> tuple[tuple[CompanyInfo | None, TemporalContext | None], str | None, float]:
        """
        Extract company info AND temporal context using Foundation Service APIs.

        1. Query Resolution API: Resolve company name → ticker, industry
        2. Earnings Calendar API: Get earnings dates using resolved ticker
        """
        start = datetime.now()
        company_info = None
        temporal_context = None
        error = None

        try:
            meeting_date = self._parse_date(meeting_datetime)

            # Step 1: Resolve company info via query_resolution API
            resolved = await self._fetch_query_resolution(company_name)
            resolved_name = company_name
            resolved_ticker = ticker
            resolved_industry = None

            if resolved:
                resolved_name = resolved.get("company_name") or company_name
                resolved_ticker = ticker or resolved.get("ticker_symbol")
                resolved_industry = resolved.get("industry")
                logger.info(f"Resolved: {company_name} → {resolved_name} ({resolved_ticker})")

            # Step 2: Fetch earnings calendar using resolved ticker
            earnings_data = None
            if resolved_ticker:
                earnings_data = await self._fetch_earnings_calendar(ticker=resolved_ticker)

            # Build CompanyInfo
            if resolved or earnings_data:
                company_info = CompanyInfo(
                    name=resolved_name,
                    ticker=resolved_ticker,
                    industry=resolved_industry,
                )

            # Build TemporalContext from earnings data
            if earnings_data:
                next_earnings = self._find_next_earnings(earnings_data, meeting_date)
                event_dt = earnings_override or (next_earnings.get("event_dt") if next_earnings else None)
                fiscal_quarter = (next_earnings.get("fiscal_period") if next_earnings else None) or str((meeting_date.month - 1) // 3 + 1)
                fy = next_earnings.get("fiscal_year") if next_earnings else None
                fiscal_year = str(int(fy)) if fy else str(meeting_date.year)

                # Compute days to earnings
                days_to_earnings = None
                if event_dt:
                    try:
                        earnings_date = datetime.strptime(event_dt, "%Y-%m-%d").date()
                        days_to_earnings = (earnings_date - meeting_date).days
                    except ValueError:
                        pass

                temporal_context = TemporalContext(
                    meeting_date=str(meeting_date),
                    event_dt=event_dt,
                    fiscal_quarter=fiscal_quarter,
                    fiscal_year=fiscal_year,
                    days_to_earnings=days_to_earnings,
                    news_lookback_days=self.DEFAULT_NEWS_LOOKBACK_DAYS,
                    filing_quarters=self.DEFAULT_FILING_QUARTERS,
                )
            elif not resolved:
                error = f"Could not resolve company: {company_name}"

        except Exception as e:
            error = str(e)
            logger.error(f"Firm/temporal extraction failed: {e}")

        duration = (datetime.now() - start).total_seconds() * 1000
        return (company_info, temporal_context), error, duration

    async def _fetch_query_resolution(self, query: str) -> dict | None:
        """
        Resolve company name to structured data via query_resolution API.

        Returns: {company_name, ticker_symbol, industry} or None
        """
        try:
            async with httpx.AsyncClient(timeout=self.http_timeout, verify=False) as client:
                response = await client.post(
                    FOUNDATION_QUERY_RESOLUTION_URL,
                    json={"query": query},
                    headers={"Content-Type": "application/json"}
                )
                if response.status_code == 200:
                    data = response.json()
                    # Parse response: result.companies.<name>.matches[0]
                    result = data.get("result", {})
                    companies = result.get("companies", {})
                    if companies:
                        # Get first company's first match
                        first_company = next(iter(companies.values()), {})
                        matches = first_company.get("matches", [])
                        if matches:
                            return matches[0]
                else:
                    logger.warning(f"Query resolution API returned {response.status_code}: {response.text[:200]}")
                return None
        except Exception as e:
            logger.warning(f"Query resolution API failed: {e}")
            return None

    async def _fetch_earnings_calendar(self, company_name: str | None = None, ticker: str | None = None) -> list[dict] | None:
        """
        Fetch earnings calendar from Foundation Service API.

        API accepts: company_name, ticker, isin, region, top_n
        Returns: list of earnings events with company info
        """
        try:
            # Build payload - API accepts company_name or ticker
            payload: dict[str, Any] = {}
            if ticker:
                payload["ticker"] = ticker
            if company_name:
                payload["company_name"] = company_name

            async with httpx.AsyncClient(timeout=self.http_timeout, verify=False) as client:
                response = await client.post(
                    FOUNDATION_EARNINGS_CALENDAR_URL,
                    json=payload,
                    headers={"Content-Type": "application/json"}
                )
                if response.status_code == 200:
                    data = response.json()
                    if isinstance(data, dict) and "result" in data:
                        return data["result"]
                    if isinstance(data, list):
                        return data
                else:
                    logger.warning(f"Earnings calendar API returned {response.status_code}: {response.text[:200]}")
                return None
        except Exception as e:
            logger.warning(f"Earnings calendar API failed: {e}")
            return None

    def _find_next_earnings(self, earnings_data: list[dict], reference_date: date) -> dict | None:
        """Find next upcoming earnings event after reference date."""
        seen, unique = set(), []
        for event in earnings_data:
            dt = event.get("event_dt")
            if dt and dt not in seen:
                seen.add(dt)
                unique.append(event)
        unique.sort(key=lambda x: x.get("event_dt", ""))

        for event in unique:
            try:
                event_date = datetime.strptime(event["event_dt"], "%Y-%m-%d").date()
                if event_date >= reference_date:
                    return event
            except (ValueError, KeyError):
                continue
        return unique[-1] if unique else None

    async def _extract_rbc_persona(self, email: str) -> tuple[PersonaInfo | None, str | None, float]:
        """Extract RBC employee persona (TODO: implement real LDAP call)."""
        start = datetime.now()
        try:
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
            return result, None, (datetime.now() - start).total_seconds() * 1000
        except Exception as e:
            return None, str(e), (datetime.now() - start).total_seconds() * 1000

    async def _extract_client_persona(
        self, email: str | None, names: str | None, company_name: str | None
    ) -> tuple[list[PersonaInfo], str | None, float]:
        """Extract client persona (TODO: implement real ZoomInfo call)."""
        start = datetime.now()
        result = []
        try:
            if email:
                name_parts = email.split("@")[0].split(".")
                first_name = name_parts[0].title() if name_parts else ""
                last_name = name_parts[1].title() if len(name_parts) > 1 else ""
                result.append(PersonaInfo(
                    name=f"{first_name} {last_name}".strip(),
                    first_name=first_name,
                    last_name=last_name,
                    email=email,
                    company=company_name,
                    is_internal=False,
                    source="ZoomInfo",
                ))
            elif names:
                for name in names.split(","):
                    name = name.strip()
                    if name:
                        parts = name.split()
                        result.append(PersonaInfo(
                            name=name,
                            first_name=parts[0] if parts else "",
                            last_name=parts[-1] if len(parts) > 1 else "",
                            company=company_name,
                            is_internal=False,
                            source="ZoomInfo",
                        ))
            return result, None, (datetime.now() - start).total_seconds() * 1000
        except Exception as e:
            return [], str(e), (datetime.now() - start).total_seconds() * 1000

    # ═══════════════════════════════════════════════════════════════════════════
    # OVERRIDE & FALLBACK HELPERS
    # ═══════════════════════════════════════════════════════════════════════════

    def _apply_company_overrides(self, company: CompanyInfo, overrides: ChainRequestOverrides) -> CompanyInfo:
        """Apply user overrides to company info."""
        data = company.model_dump()
        if overrides.ticker:
            data["ticker"] = overrides.ticker
        if overrides.company_cik:
            data["cik"] = overrides.company_cik
        if overrides.industry:
            data["industry"] = overrides.industry
        if overrides.sector:
            data["sector"] = overrides.sector
        return CompanyInfo(**data)

    def _apply_temporal_overrides(self, temporal: TemporalContext, overrides: ChainRequestOverrides) -> TemporalContext:
        """Apply user overrides to temporal context."""
        data = temporal.model_dump()
        if overrides.fiscal_quarter:
            data["fiscal_quarter"] = overrides.fiscal_quarter.upper().replace("Q", "").strip()
        if overrides.fiscal_year:
            data["fiscal_year"] = overrides.fiscal_year.upper().replace("FY", "").strip()
        if overrides.next_earnings_date:
            data["event_dt"] = overrides.next_earnings_date
        if overrides.news_lookback_days:
            data["news_lookback_days"] = overrides.news_lookback_days
        if overrides.filing_quarters:
            data["filing_quarters"] = overrides.filing_quarters
        return TemporalContext(**data)

    def _create_default_temporal(self, meeting_datetime: str | None, overrides: ChainRequestOverrides) -> TemporalContext:
        """Create default temporal context when API fails."""
        meeting_date = self._parse_date(meeting_datetime)
        quarter = (meeting_date.month - 1) // 3 + 1
        return TemporalContext(
            meeting_date=str(meeting_date),
            fiscal_quarter=str(quarter),
            fiscal_year=str(meeting_date.year),
            event_dt=overrides.next_earnings_date,
            news_lookback_days=overrides.news_lookback_days or self.DEFAULT_NEWS_LOOKBACK_DAYS,
            filing_quarters=overrides.filing_quarters or self.DEFAULT_FILING_QUARTERS,
        )

    def _parse_date(self, date_str: str | None) -> date:
        """Parse date string or return today's date."""
        if date_str:
            try:
                return datetime.fromisoformat(date_str.replace("Z", "+00:00")).date()
            except ValueError:
                pass
        return date.today()

