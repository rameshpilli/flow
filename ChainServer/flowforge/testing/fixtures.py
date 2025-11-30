"""
FlowForge Test Fixtures

Provides pre-configured fixtures for testing FlowForge applications.
Compatible with pytest and unittest.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from flowforge.core.context import ChainContext
from flowforge.core.forge import FlowForge


class IsolatedForge:
    """
    Pre-configured FlowForge instance with test isolation.

    Automatically uses isolated registries and cleans up after tests.

    Usage with async context manager:
        async with IsolatedForge() as forge:
            @forge.step(name="my_step")
            async def my_step(ctx):
                return {"result": True}

            @forge.chain(name="my_chain")
            class MyChain:
                steps = ["my_step"]

            result = await forge.launch("my_chain", {})
            assert result["success"]

    Usage with pytest fixture:
        @pytest.fixture
        async def forge():
            async with IsolatedForge() as f:
                yield f

        async def test_something(forge):
            ...
    """

    def __init__(
        self,
        name: str = "test",
        enable_middleware: bool = True,
        enable_tracing: bool = False,
    ):
        """
        Initialize isolated forge.

        Args:
            name: Forge instance name
            enable_middleware: Enable middleware system
            enable_tracing: Enable OpenTelemetry tracing
        """
        self._name = name
        self._enable_middleware = enable_middleware
        self._enable_tracing = enable_tracing
        self._forge: FlowForge | None = None
        self._context_token = None

    async def __aenter__(self) -> FlowForge:
        """Enter async context - create isolated forge."""
        # Enter temporary registries context
        self._context_token = FlowForge.temp_registries().__enter__()

        # Create forge instance
        self._forge = FlowForge(
            name=self._name,
            isolated=True,
        )

        return self._forge

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit async context - cleanup."""
        if self._forge:
            try:
                await self._forge.cleanup_resources(timeout_seconds=5.0)
            except Exception:
                pass  # Ignore cleanup errors in tests

        # Exit temporary registries context
        if self._context_token is not None:
            FlowForge.temp_registries().__exit__(None, None, None)

    def __enter__(self) -> FlowForge:
        """Sync context manager entry (for non-async setup)."""
        self._context_token = FlowForge.temp_registries().__enter__()
        self._forge = FlowForge(name=self._name, isolated=True)
        return self._forge

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Sync context manager exit."""
        if self._forge:
            try:
                self._forge._cleanup_resources_sync(timeout_seconds=5.0)
            except Exception:
                pass

        if self._context_token is not None:
            FlowForge.temp_registries().__exit__(None, None, None)


def create_test_forge(
    name: str = "test",
    isolated: bool = True,
) -> FlowForge:
    """
    Create a FlowForge instance configured for testing.

    Note: Caller is responsible for cleanup. Prefer using IsolatedForge
    context manager for automatic cleanup.

    Args:
        name: Forge instance name
        isolated: Use isolated registries

    Returns:
        Configured FlowForge instance
    """
    return FlowForge(name=name, isolated=isolated)


def create_test_context(
    request_id: str | None = None,
    initial_data: dict[str, Any] | None = None,
    chain_name: str = "test_chain",
) -> ChainContext:
    """
    Create a ChainContext for unit testing steps.

    Usage:
        ctx = create_test_context(initial_data={"company": "Apple"})
        result = await my_step(ctx)
        assert ctx.get("output_key") == expected

    Args:
        request_id: Optional request ID (generated if not provided)
        initial_data: Initial context data
        chain_name: Chain name for context

    Returns:
        Configured ChainContext
    """
    ctx = ChainContext(
        request_id=request_id or f"test_{uuid.uuid4().hex[:8]}",
        initial_data=initial_data or {},
    )
    # Store chain_name in metadata if provided
    if chain_name:
        ctx.metadata["chain_name"] = chain_name
    return ctx


@dataclass
class SampleChainRequest:
    """
    Sample chain request data for testing CMPT flows.

    Provides realistic test data for common scenarios.
    """
    company_name: str = "Apple Inc"
    ticker: str = "AAPL"
    user_query: str = "What are the key financial metrics?"
    meeting_date: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))
    rbc_employee_id: str = "12345"
    client_email: str = "client@example.com"
    include_news: bool = True
    include_sec: bool = True
    include_earnings: bool = True
    max_results: int = 10

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for forge.launch()."""
        return {
            "company_name": self.company_name,
            "ticker": self.ticker,
            "user_query": self.user_query,
            "meeting_date": self.meeting_date,
            "rbc_employee_id": self.rbc_employee_id,
            "client_email": self.client_email,
            "include_news": self.include_news,
            "include_sec": self.include_sec,
            "include_earnings": self.include_earnings,
            "max_results": self.max_results,
        }


def sample_chain_request(
    company: str = "Apple Inc",
    ticker: str = "AAPL",
    **overrides,
) -> dict[str, Any]:
    """
    Create sample chain request data.

    Convenience function for quick test data creation.

    Args:
        company: Company name
        ticker: Stock ticker
        **overrides: Override any default values

    Returns:
        Dict suitable for forge.launch(data=...)
    """
    request = SampleChainRequest(company_name=company, ticker=ticker)

    data = request.to_dict()
    data.update(overrides)

    return data


# ═══════════════════════════════════════════════════════════════════════════════
#                         PYTEST FIXTURES
# ═══════════════════════════════════════════════════════════════════════════════

# Note: Import these in conftest.py if using pytest

def pytest_fixtures():
    """
    Example pytest fixtures. Copy to your conftest.py.

    Usage in conftest.py:
        import pytest
        from flowforge.testing.fixtures import (
            IsolatedForge,
            create_test_context,
            sample_chain_request,
        )

        @pytest.fixture
        async def forge():
            async with IsolatedForge() as f:
                yield f

        @pytest.fixture
        def ctx():
            return create_test_context()

        @pytest.fixture
        def sample_request():
            return sample_chain_request()
    """
    pass


# ═══════════════════════════════════════════════════════════════════════════════
#                         SAMPLE DATA GENERATORS
# ═══════════════════════════════════════════════════════════════════════════════


def sample_news_articles(count: int = 3, company: str = "Apple") -> list[dict]:
    """Generate sample news articles for testing."""
    return [
        {
            "title": f"{company} News Article {i+1}",
            "source": "Reuters" if i % 2 == 0 else "Bloomberg",
            "date": datetime.now().strftime("%Y-%m-%d"),
            "summary": f"This is a sample news article about {company}.",
            "sentiment": "positive" if i % 3 == 0 else "neutral",
            "url": f"https://example.com/news/{i+1}",
        }
        for i in range(count)
    ]


def sample_sec_filings(count: int = 2, ticker: str = "AAPL") -> list[dict]:
    """Generate sample SEC filings for testing."""
    filing_types = ["10-K", "10-Q", "8-K"]
    return [
        {
            "filing_type": filing_types[i % len(filing_types)],
            "ticker": ticker,
            "date": "2024-01-15",
            "summary": f"Sample {filing_types[i % len(filing_types)]} filing",
            "url": f"https://sec.gov/filing/{ticker}/{i+1}",
        }
        for i in range(count)
    ]


def sample_earnings_data(ticker: str = "AAPL") -> dict:
    """Generate sample earnings data for testing."""
    return {
        "ticker": ticker,
        "quarter": "Q1 2024",
        "eps_actual": 2.18,
        "eps_estimate": 2.10,
        "revenue_actual": 119500000000,
        "revenue_estimate": 118000000000,
        "guidance": "Positive outlook for FY2024",
        "call_date": "2024-02-01",
    }


def sample_financial_metrics(ticker: str = "AAPL") -> dict:
    """Generate sample financial metrics for testing."""
    return {
        "ticker": ticker,
        "market_cap": 3000000000000,
        "pe_ratio": 28.5,
        "dividend_yield": 0.5,
        "revenue_ttm": 385000000000,
        "net_income_ttm": 97000000000,
        "debt_to_equity": 1.8,
        "current_ratio": 1.0,
    }
