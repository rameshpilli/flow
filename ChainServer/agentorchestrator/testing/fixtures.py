"""
AgentOrchestrator Test Fixtures

Provides pre-configured fixtures for testing AgentOrchestrator applications.
Compatible with pytest and unittest.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from agentorchestrator.core.context import ChainContext
from agentorchestrator.core.orchestrator import AgentOrchestrator


class IsolatedOrchestrator:
    """
    Pre-configured AgentOrchestrator instance with test isolation.

    Automatically uses isolated registries and cleans up after tests.

    Usage with async context manager:
        async with IsolatedOrchestrator() as forge:
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
            async with IsolatedOrchestrator() as f:
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
        self._forge: AgentOrchestrator | None = None
        self._context_token = None

    async def __aenter__(self) -> AgentOrchestrator:
        """Enter async context - create isolated forge."""
        # Enter temporary registries context
        self._context_token = AgentOrchestrator.temp_registries().__enter__()

        # Create forge instance
        self._forge = AgentOrchestrator(
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
            AgentOrchestrator.temp_registries().__exit__(None, None, None)

    def __enter__(self) -> AgentOrchestrator:
        """Sync context manager entry (for non-async setup)."""
        self._context_token = AgentOrchestrator.temp_registries().__enter__()
        self._forge = AgentOrchestrator(name=self._name, isolated=True)
        return self._forge

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Sync context manager exit."""
        if self._forge:
            try:
                self._forge._cleanup_resources_sync(timeout_seconds=5.0)
            except Exception:
                pass

        if self._context_token is not None:
            AgentOrchestrator.temp_registries().__exit__(None, None, None)


def create_test_forge(
    name: str = "test",
    isolated: bool = True,
) -> AgentOrchestrator:
    """
    Create a AgentOrchestrator instance configured for testing.

    Note: Caller is responsible for cleanup. Prefer using IsolatedOrchestrator
    context manager for automatic cleanup.

    Args:
        name: Forge instance name
        isolated: Use isolated registries

    Returns:
        Configured AgentOrchestrator instance
    """
    return AgentOrchestrator(name=name, isolated=isolated)


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
    Sample chain request data for testing chain flows.

    Provides generic test data. Override for domain-specific testing.
    """
    entity_name: str = "Example Entity"
    entity_id: str = "E001"
    user_query: str = "What are the key details?"
    request_date: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))
    user_id: str = "test_user_123"
    user_email: str = "user@example.com"
    max_results: int = 10

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for forge.launch()."""
        return {
            "entity_name": self.entity_name,
            "entity_id": self.entity_id,
            "user_query": self.user_query,
            "request_date": self.request_date,
            "user_id": self.user_id,
            "user_email": self.user_email,
            "max_results": self.max_results,
        }


def sample_chain_request(
    entity_name: str = "Example Entity",
    entity_id: str = "E001",
    **overrides,
) -> dict[str, Any]:
    """
    Create sample chain request data.

    Convenience function for quick test data creation.

    Args:
        entity_name: Entity name
        entity_id: Entity identifier
        **overrides: Override any default values

    Returns:
        Dict suitable for forge.launch(data=...)
    """
    request = SampleChainRequest(entity_name=entity_name, entity_id=entity_id)

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
        from agentorchestrator.testing.fixtures import (
            IsolatedOrchestrator,
            create_test_context,
            sample_chain_request,
        )

        @pytest.fixture
        async def forge():
            async with IsolatedOrchestrator() as f:
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


def sample_items(
    count: int = 3,
    entity: str = "Entity",
    item_type: str = "item",
) -> list[dict]:
    """
    Generate sample items for testing.

    Args:
        count: Number of items to generate
        entity: Entity name
        item_type: Type of item

    Returns:
        List of sample item dictionaries
    """
    sources = ["Source A", "Source B", "Source C"]
    return [
        {
            "id": f"{item_type}_{i+1}",
            "title": f"{entity} {item_type.title()} {i+1}",
            "source": sources[i % len(sources)],
            "date": datetime.now().strftime("%Y-%m-%d"),
            "summary": f"This is a sample {item_type} about {entity}.",
            "status": "active" if i % 2 == 0 else "pending",
            "url": f"https://example.com/{item_type}/{i+1}",
        }
        for i in range(count)
    ]


def sample_documents(
    count: int = 2,
    entity_id: str = "E001",
    doc_types: list[str] | None = None,
) -> list[dict]:
    """
    Generate sample documents for testing.

    Args:
        count: Number of documents to generate
        entity_id: Entity identifier
        doc_types: List of document types to cycle through

    Returns:
        List of sample document dictionaries
    """
    doc_types = doc_types or ["Report", "Summary", "Analysis"]
    return [
        {
            "doc_type": doc_types[i % len(doc_types)],
            "entity_id": entity_id,
            "date": "2024-01-15",
            "summary": f"Sample {doc_types[i % len(doc_types)]} document",
            "url": f"https://example.com/docs/{entity_id}/{i+1}",
        }
        for i in range(count)
    ]


def sample_record(entity_id: str = "E001") -> dict:
    """
    Generate a sample record for testing.

    Args:
        entity_id: Entity identifier

    Returns:
        Sample record dictionary
    """
    return {
        "id": entity_id,
        "period": "Q1 2024",
        "value_actual": 1000.0,
        "value_estimate": 950.0,
        "delta": 50.0,
        "status": "completed",
        "notes": "Sample record notes",
        "created_at": "2024-02-01",
    }


def sample_metrics(entity_id: str = "E001") -> dict:
    """
    Generate sample metrics for testing.

    Args:
        entity_id: Entity identifier

    Returns:
        Sample metrics dictionary
    """
    return {
        "id": entity_id,
        "total_count": 100,
        "success_rate": 0.95,
        "average_value": 250.5,
        "min_value": 10.0,
        "max_value": 1000.0,
        "trend": "increasing",
        "last_updated": datetime.now().strftime("%Y-%m-%d"),
    }