# Create New Agent

Create a new AgentOrchestrator data agent following established patterns.

## Usage
```
/new-agent <agent_name> <description> [--mcp|--http|--mock]
```

Example: `/new-agent portfolio_agent "Fetches portfolio data from internal API" --mcp`

---

## Agent Types

### 1. MCP Agent (Recommended for MCP servers)
Extends `MCPAdapterAgent` for Model Context Protocol servers.

### 2. HTTP Agent
Uses `httpx` for REST API calls.

### 3. Mock Agent
For testing and development without external dependencies.

---

## MCP Agent Template

```python
"""
{AgentName} Agent - Fetches data via MCP.
"""

import logging
import time
from typing import Any

from agentorchestrator.agents.base import AgentResult, BaseAgent
from agentorchestrator.plugins.mcp_adapter import MCPAdapterAgent, MCPAdapterConfig

logger = logging.getLogger(__name__)


def _create_mcp_config(
    name: str,
    url: str,
    token: str | None,
    timeout: float = 30.0,
    verify_ssl: bool = False,
) -> MCPAdapterConfig:
    """Create MCP adapter config with auth header if token provided."""
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return MCPAdapterConfig(
        name=name,
        server_url=url,
        transport="http",
        headers=headers,
        timeout_seconds=timeout,
        verify_ssl=verify_ssl,
    )


def _agent_result(
    source: str,
    query: str,
    start: float,
    data: Any = None,
    error: str | None = None,
) -> AgentResult:
    """Helper to create AgentResult with timing."""
    return AgentResult(
        data=data or {"items": []},
        source=source,
        query=query,
        duration_ms=(time.perf_counter() - start) * 1000,
        error=error,
    )


class {AgentClass}Agent(MCPAdapterAgent):
    """
    {AgentDescription}

    Usage:
        agent = {AgentClass}Agent(mcp_url="http://localhost:8000", bearer_token="...")
        result = await agent.fetch("query", param1="value1")
    """

    _ao_name = "{agent_name}"

    def __init__(
        self,
        mcp_url: str | None = None,
        bearer_token: str | None = None,
        timeout: float = 30.0,
        **kwargs,
    ):
        config = (
            _create_mcp_config("{agent_name}_mcp", mcp_url, bearer_token, timeout)
            if mcp_url
            else MCPAdapterConfig(name="{agent_name}_mcp")
        )
        super().__init__(config)

    async def fetch(self, query: str, **kwargs) -> AgentResult:
        """
        Fetch data based on query.

        Args:
            query: Search query or identifier
            **kwargs: Additional parameters for the MCP tool

        Returns:
            AgentResult with fetched data or error
        """
        start = time.perf_counter()

        # Check if MCP server is configured
        if not self._config.server_url:
            return _agent_result(
                self._ao_name,
                query,
                start,
                error="No MCP server configured",
            )

        # Lazy initialization - connect if not already connected
        if not self._mcp_session:
            try:
                await self.initialize()
            except Exception as e:
                logger.error(f"Failed to initialize {self._ao_name}: {e}")
                return _agent_result(
                    self._ao_name,
                    query,
                    start,
                    error=f"Initialization failed: {e}",
                )

        try:
            # Extract parameters from kwargs
            param1 = kwargs.get("param1", query)
            param2 = kwargs.get("param2", "default_value")

            # Build args matching MCP tool schema
            args = {
                "param1": param1,
                "param2": param2,
                # Add more parameters as needed by your MCP tool
            }

            logger.info(f"{self._ao_name} calling with: {args}")

            # Call the MCP tool
            result = await self.call_tool("{mcp_tool_name}", args)

            return _agent_result(self._ao_name, query, start, data=result)

        except Exception as e:
            logger.error(f"{self._ao_name} failed: {e}")
            return _agent_result(self._ao_name, query, start, error=str(e))
```

---

## HTTP Agent Template

```python
"""
{AgentName} Agent - Fetches data via HTTP/REST API.
"""

import logging
import time
from typing import Any

import httpx

from agentorchestrator.agents.base import AgentResult, BaseAgent

logger = logging.getLogger(__name__)


class {AgentClass}Agent(BaseAgent):
    """
    {AgentDescription}

    Usage:
        agent = {AgentClass}Agent(api_url="http://api.example.com", api_key="...")
        result = await agent.fetch("query", param1="value1")
    """

    _ao_name = "{agent_name}"
    _ao_version = "1.0.0"

    def __init__(
        self,
        api_url: str | None = None,
        api_key: str | None = None,
        timeout: float = 30.0,
        config: dict[str, Any] | None = None,
    ):
        super().__init__(config)
        self.api_url = api_url
        self.api_key = api_key
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def initialize(self) -> None:
        """Initialize HTTP client."""
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
            # Or use X-API-Key header:
            # headers["X-API-Key"] = self.api_key

        self._client = httpx.AsyncClient(
            timeout=self.timeout,
            headers=headers,
        )
        await super().initialize()

    async def cleanup(self) -> None:
        """Cleanup HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
        await super().cleanup()

    async def fetch(self, query: str, **kwargs) -> AgentResult:
        """
        Fetch data from API.

        Args:
            query: Search query or identifier
            **kwargs: Additional parameters

        Returns:
            AgentResult with fetched data or error
        """
        start = time.perf_counter()

        if not self.api_url:
            return AgentResult(
                data=None,
                source=self._ao_name,
                query=query,
                duration_ms=(time.perf_counter() - start) * 1000,
                error="No API URL configured",
            )

        # Lazy initialization
        if not self._client:
            await self.initialize()

        try:
            # Build request parameters
            params = {
                "q": query,
                **{k: v for k, v in kwargs.items() if v is not None},
            }

            # Make API request
            response = await self._client.get(
                f"{self.api_url}/search",
                params=params,
            )
            response.raise_for_status()

            data = response.json()

            return AgentResult(
                data=data,
                source=self._ao_name,
                query=query,
                duration_ms=(time.perf_counter() - start) * 1000,
                metadata={
                    "status_code": response.status_code,
                    "item_count": len(data.get("items", [])),
                },
            )

        except httpx.HTTPStatusError as e:
            logger.error(f"{self._ao_name} HTTP error: {e}")
            return AgentResult(
                data=None,
                source=self._ao_name,
                query=query,
                duration_ms=(time.perf_counter() - start) * 1000,
                error=f"HTTP {e.response.status_code}: {e.response.text[:200]}",
            )
        except Exception as e:
            logger.error(f"{self._ao_name} failed: {e}")
            return AgentResult(
                data=None,
                source=self._ao_name,
                query=query,
                duration_ms=(time.perf_counter() - start) * 1000,
                error=str(e),
            )

    async def health_check(self) -> bool:
        """Check if API is reachable."""
        if not self.api_url or not self._client:
            return False
        try:
            response = await self._client.get(f"{self.api_url}/health")
            return response.status_code == 200
        except Exception:
            return False
```

---

## Agent Registration Pattern

Add to your chain's `services/agents.py`:

```python
from agentorchestrator.testing import testable


@testable(
    agent_configs={
        "{agent_name}": {
            "mcp_url": "http://localhost:8000",
            "bearer_token": "test_token",
        }
    },
    test_query="test_query",
    test_params={"param1": "value1"},
)
def register_{chain_name}_agents(ao: Any) -> None:
    """
    Register agents with resilience configuration.

    To test: await register_{chain_name}_agents.test(ao)
    """
    ao.agent(
        name="{agent_name}",
        group="{chain_name}",
        description="{AgentDescription}",
        resilient=True,
        resilient_config={
            "timeout_seconds": 30.0,
            "max_retries": 2,
            "retry_delay_ms": 1000,
            "retry_backoff": 2.0,
            "circuit_failure_threshold": 5,
            "circuit_recovery_seconds": 30.0,
        },
    )({AgentClass}Agent)

    logger.info("Registered {agent_name} with resilience")


def get_{chain_name}_agents(
    ao: Any,
    {agent_name}_url: str | None = None,
    {agent_name}_token: str | None = None,
) -> dict[str, BaseAgent]:
    """
    Get configured agent instances.

    Args:
        ao: AgentOrchestrator instance
        {agent_name}_url: MCP/API URL for the agent
        {agent_name}_token: Bearer token for authentication

    Returns:
        Dict of {agent_name: agent_instance}
    """
    if {agent_name}_url:
        return {
            "{agent_name}": {AgentClass}Agent(
                mcp_url={agent_name}_url,
                bearer_token={agent_name}_token,
            ),
        }

    # Get registered agents from orchestrator
    return {
        "{agent_name}": ao.get_agent("{agent_name}"),
    }
```

---

## AgentResult Structure

```python
@dataclass
class AgentResult(Generic[T]):
    """Result from an agent operation."""

    data: T                          # The fetched data
    source: str                      # Agent name
    query: str                       # Query that was executed
    timestamp: datetime              # When the result was created
    metadata: dict[str, Any]         # Additional metadata
    error: str | None                # Error message if failed
    duration_ms: float               # Execution time
    citations: list[Citation]        # Source citations
    raw_content: str | None          # Raw content for verification

    @property
    def success(self) -> bool:
        return self.error is None

    @property
    def has_citations(self) -> bool:
        return len(self.citations) > 0

    def add_citation(self, content: str, reasoning: str | None = None, ...) -> "AgentResult[T]":
        """Add a citation to this result."""
        ...
```

---

## Resilience Configuration

```python
@dataclass
class ResilientAgentConfig:
    """Configuration for resilient agent wrapper."""

    timeout_seconds: float = 30.0          # Per-call timeout
    max_retries: int = 3                   # Max retry attempts
    retry_delay_ms: int = 1000             # Initial retry delay
    retry_backoff: float = 2.0             # Backoff multiplier
    circuit_failure_threshold: int = 5     # Failures before opening circuit
    circuit_recovery_seconds: float = 30.0 # Seconds before half-open
```

---

## Best Practices

### 1. Lazy Initialization
```python
# Connect on first use, not in __init__
if not self._mcp_session:
    await self.initialize()
```

### 2. Timeout Protection
```python
# Always wrap external calls with timeout
result = await asyncio.wait_for(
    self._make_request(),
    timeout=self.timeout,
)
```

### 3. Structured Error Handling
```python
try:
    result = await self.call_tool(...)
    return _agent_result(self._ao_name, query, start, data=result)
except SpecificError as e:
    logger.error(f"Specific error: {e}")
    return _agent_result(self._ao_name, query, start, error=f"Specific: {e}")
except Exception as e:
    logger.error(f"Unexpected error: {e}")
    return _agent_result(self._ao_name, query, start, error=str(e))
```

### 4. Citation Support
```python
result = await self.fetch(query)
result.add_citation(
    content="Verbatim quote from source",
    reasoning="Why this supports the data",
    document_id="doc-123",
)
```

---

## Reference Files

- **MCP Agent Example**: [cmpt/services/agents.py](cmpt/services/agents.py)
- **Base Agent Class**: [agentorchestrator/agents/base.py](agentorchestrator/agents/base.py)
- **MCP Adapter**: [agentorchestrator/plugins/mcp_adapter.py](agentorchestrator/plugins/mcp_adapter.py)
- **Resilient Agent**: [agentorchestrator/agents/base.py:247](agentorchestrator/agents/base.py#L247) (ResilientAgent class)
