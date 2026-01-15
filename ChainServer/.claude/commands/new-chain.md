# Create New Chain

Create a new AgentOrchestrator chain following the established CMPT pattern.

## Usage
```
/new-chain <chain_name> <description>
```

Example: `/new-chain risk_analysis "Risk analysis pipeline for portfolio management"`

---

## Chain Architecture

Follow the 3-stage pipeline pattern from CMPT:

```
┌─────────────────┐     ┌───────────────────────┐     ┌──────────────────┐
│ Context Builder │ ──► │ Content Prioritization │ ──► │ Response Builder │
└─────────────────┘     └───────────────────────┘     └──────────────────┘
      Stage 1                   Stage 2                      Stage 3
```

---

## Directory Structure

Create the following structure:
```
{chain_name}/
├── __init__.py              # Package exports
├── chain.py                 # Main chain definition with @ao.step and @ao.chain
├── run.py                   # CLI runner and convenience functions
├── config.py                # Chain-specific configuration
├── services/
│   ├── __init__.py          # Export all models and services
│   ├── models.py            # Pydantic models for all stages
│   ├── _01_{step1}.py       # First step service
│   ├── _02_{step2}.py       # Second step service (optional)
│   ├── _03_{step3}.py       # Third step service (optional)
│   ├── agents.py            # Agent registration and factory functions
│   ├── llm_prompts.py       # LLM prompts if using LLM calls
│   └── validation_utils.py  # Validation helpers
└── tests/
    ├── __init__.py
    └── test_{chain_name}.py
```

---

## Step 1: Create Models (`services/models.py`)

```python
"""
{ChainName} Service Models

Pydantic models for all chain services with validation.
"""

from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════════════════════════════
#                              ENUMS
# ═══════════════════════════════════════════════════════════════════════════════


class DataSource(str, Enum):
    """Available data sources for the chain"""
    # Define your data sources here
    SOURCE_A = "source_a"
    SOURCE_B = "source_b"


class Priority(str, Enum):
    """Priority levels for data sources"""
    PRIMARY = "primary"
    SECONDARY = "secondary"
    TERTIARY = "tertiary"


# ═══════════════════════════════════════════════════════════════════════════════
#                         CHAIN REQUEST/RESPONSE
# ═══════════════════════════════════════════════════════════════════════════════


class ChainRequest(BaseModel):
    """
    Unified request model for the chain.

    Define all input fields from the calling application.
    """
    # Required fields
    primary_input: str = Field(..., description="Main input for the chain")

    # Optional fields
    secondary_input: str | None = None
    options: dict[str, Any] = Field(default_factory=dict)

    # User overrides (optional)
    overrides: "ChainRequestOverrides | None" = Field(
        None, description="User-provided overrides for computed values"
    )


class ChainRequestOverrides(BaseModel):
    """User-provided overrides for computed/extracted values."""
    # Define override fields here
    skip_api_calls: bool = False

    class Config:
        extra = "allow"  # Allow additional custom overrides


# Update ChainRequest to use forward reference
ChainRequest.model_rebuild()


class ChainResponse(BaseModel):
    """Unified response model for the chain"""
    # Core response fields
    result: dict[str, Any] | None = None

    # Metadata
    agent_results: dict[str, Any] | None = None
    validation_results: dict[str, Any] | None = None
    timing_ms: dict[str, float] | None = None
    success: bool = True
    error: str | None = None


# ═══════════════════════════════════════════════════════════════════════════════
#                         STEP 1: CONTEXT BUILDER MODELS
# ═══════════════════════════════════════════════════════════════════════════════


class ContextBuilderOutput(BaseModel):
    """Output from the Context Builder service."""
    # Extracted context
    extracted_data: dict[str, Any] | None = None

    # Errors and timing
    errors: dict[str, str] = Field(default_factory=dict)
    timing_ms: dict[str, float] | None = None


# ═══════════════════════════════════════════════════════════════════════════════
#                         STEP 2: CONTENT PRIORITIZATION MODELS
# ═══════════════════════════════════════════════════════════════════════════════


class PrioritizedSource(BaseModel):
    """A prioritized data source with configuration"""
    source: DataSource
    priority: Priority
    enabled: bool = True
    # Add source-specific config as needed


class Subquery(BaseModel):
    """A subquery to be executed against a data agent"""
    agent: str
    query: str
    params: dict[str, Any] = Field(default_factory=dict)
    priority: Priority = Priority.PRIMARY
    timeout_ms: int = 30000


class ContentPrioritizationOutput(BaseModel):
    """Output from the Content Prioritization service."""
    prioritized_sources: list[PrioritizedSource] = Field(default_factory=list)
    subqueries: list[Subquery] = Field(default_factory=list)
    subqueries_by_agent: dict[str, list[Subquery]] = Field(default_factory=dict)
    prioritization_reasoning: str | None = None
    timing_ms: dict[str, float] | None = None


# ═══════════════════════════════════════════════════════════════════════════════
#                         STEP 3: RESPONSE BUILDER MODELS
# ═══════════════════════════════════════════════════════════════════════════════


class AgentResult(BaseModel):
    """Result from a single data agent execution"""
    agent: str
    success: bool
    data: dict[str, Any] | None = None
    items: list[dict[str, Any]] = Field(default_factory=list)
    duration_ms: float | None = None
    error: str | None = None


class ResponseBuilderOutput(BaseModel):
    """Output from the Response Builder service."""
    agent_results: dict[str, AgentResult] = Field(default_factory=dict)
    final_output: dict[str, Any] | None = None
    agents_succeeded: int = 0
    agents_failed: int = 0
    errors: dict[str, str] = Field(default_factory=dict)
    timing_ms: dict[str, float] | None = None
```

---

## Step 2: Create Services

### Context Builder Service (`services/_01_context_builder.py`)

```python
"""
Context Builder Service

First stage of the chain - extracts context from user request.
"""

import asyncio
import logging
from datetime import datetime
from typing import Any

from {chain_name}.services.models import (
    ChainRequest,
    ChainRequestOverrides,
    ContextBuilderOutput,
)

logger = logging.getLogger(__name__)


class ContextBuilderService:
    """
    Service for extracting context from requests.

    Usage:
        service = ContextBuilderService()
        output = await service.execute(request)
    """

    # Configuration
    DEFAULT_TIMEOUT: float = 20.0

    def __init__(self, http_timeout: float = 20.0):
        self.http_timeout = http_timeout

    async def execute(self, request: ChainRequest) -> ContextBuilderOutput:
        """Execute all context extraction steps."""
        start_time = datetime.now()
        timing: dict[str, float] = {}
        errors: dict[str, str] = {}
        overrides = request.overrides or ChainRequestOverrides()

        output = ContextBuilderOutput(errors={}, timing_ms={})

        # Run extractors in parallel
        tasks = []

        # Add your extractors here
        if not overrides.skip_api_calls:
            tasks.append(("extractor_1", self._extract_data(request)))

        if tasks:
            results = await asyncio.gather(
                *[task[1] for task in tasks],
                return_exceptions=True,
            )

            for (name, _), result in zip(tasks, results):
                if isinstance(result, Exception):
                    errors[name] = str(result)
                    logger.error(f"Extractor {name} failed: {result}")
                else:
                    data, error, duration = result
                    timing[name] = duration
                    if error:
                        errors[name] = error
                    else:
                        output.extracted_data = data

        output.errors = errors
        output.timing_ms = timing

        total_duration = (datetime.now() - start_time).total_seconds() * 1000
        timing["total"] = total_duration

        logger.info(f"Context builder completed in {total_duration:.2f}ms")
        return output

    async def _extract_data(
        self, request: ChainRequest
    ) -> tuple[dict[str, Any] | None, str | None, float]:
        """Extract data from external source."""
        start = datetime.now()
        error = None
        result = None

        try:
            # Your extraction logic here
            result = {"extracted": request.primary_input}
        except Exception as e:
            error = str(e)
            logger.error(f"Extraction failed: {e}")

        duration = (datetime.now() - start).total_seconds() * 1000
        return result, error, duration
```

---

## Step 3: Create Agents (`services/agents.py`)

```python
"""
{ChainName} Data Agents - Fetch data via MCP or APIs.
"""

import logging
import time
from enum import Enum
from typing import Any

from agentorchestrator.agents.base import AgentResult, BaseAgent
from agentorchestrator.plugins.mcp_adapter import MCPAdapterAgent, MCPAdapterConfig
from agentorchestrator.testing import testable

logger = logging.getLogger(__name__)


class ToolName(Enum):
    """Data agent tool names."""
    AGENT_A = "agent_a"
    AGENT_B = "agent_b"


def _create_mcp_config(name: str, url: str, token: str | None, timeout: float = 30.0) -> MCPAdapterConfig:
    """Create MCP adapter config with auth header if token provided."""
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return MCPAdapterConfig(
        name=name,
        server_url=url,
        transport="http",
        headers=headers,
        timeout_seconds=timeout,
    )


def _agent_result(source: str, query: str, start: float, data: Any = None, error: str | None = None) -> AgentResult:
    """Helper to create AgentResult with timing."""
    return AgentResult(
        data=data or {"items": []},
        source=source,
        query=query,
        duration_ms=(time.perf_counter() - start) * 1000,
        error=error,
    )


class AgentA(MCPAdapterAgent):
    """Fetches data from source A via MCP."""

    _ao_name = ToolName.AGENT_A.value

    def __init__(self, mcp_url: str | None = None, bearer_token: str | None = None, **kwargs):
        config = (_create_mcp_config("agent_a_mcp", mcp_url, bearer_token)
                  if mcp_url else MCPAdapterConfig(name="agent_a_mcp"))
        super().__init__(config)

    async def fetch(self, query: str, **kwargs) -> AgentResult:
        """Fetch data from source A."""
        start = time.perf_counter()

        if not self._config.server_url:
            return _agent_result(self._ao_name, query, start, error="No MCP server configured")

        try:
            # Your MCP tool call logic
            args = {"query": query, **kwargs}
            result = await self.call_tool("your_tool_name", args)
            return _agent_result(self._ao_name, query, start, data=result)
        except Exception as e:
            logger.error(f"Agent A failed: {e}")
            return _agent_result(self._ao_name, query, start, error=str(e))


# ══════════════════════════════════════════════════════════════════════════════
#                           AGENT REGISTRATION
# ══════════════════════════════════════════════════════════════════════════════


@testable(
    agent_configs={},
    test_query="test",
    test_params={"param": "value"}
)
def register_{chain_name}_agents(ao: Any) -> None:
    """
    Register chain agents with resilience configuration.

    Call ao.get_agent(name, mcp_url=..., bearer_token=...) to get instances.
    """
    ao.agent(
        name=ToolName.AGENT_A.value,
        group="{chain_name}",
        description="Fetches data from source A",
        resilient=True,
        resilient_config={"timeout_seconds": 30.0, "max_retries": 2},
    )(AgentA)

    logger.info("Registered {chain_name} agents with resilience")


def get_{chain_name}_agents(
    ao: Any,
    agent_a_url: str | None = None,
    agent_a_token: str | None = None,
) -> dict[str, BaseAgent]:
    """Get configured agent instances."""
    if agent_a_url:
        return {
            ToolName.AGENT_A.value: AgentA(mcp_url=agent_a_url, bearer_token=agent_a_token),
        }
    return {
        ToolName.AGENT_A.value: ao.get_agent(ToolName.AGENT_A.value),
    }
```

---

## Step 4: Create Chain Definition (`chain.py`)

```python
"""
{ChainName} Chain Definition

This file defines the pipeline using AgentOrchestrator decorators.

Usage:
    from agentorchestrator import AgentOrchestrator
    from {chain_name}.chain import register_{chain_name}_chain

    ao = AgentOrchestrator(name="{chain_name}")
    register_{chain_name}_chain(ao)

    result = await ao.launch("{chain_name}_chain", {"request": {...}})
"""

import logging
from typing import Any

from agentorchestrator import AgentOrchestrator

from {chain_name}.services import (
    # Models
    ChainRequest,
    ChainResponse,
    ContextBuilderOutput,
    ContentPrioritizationOutput,
    ResponseBuilderOutput,
    # Services
    ContextBuilderService,
    ContentPrioritizationService,
    ResponseBuilderService,
    # Agents
    register_{chain_name}_agents,
    get_{chain_name}_agents,
)

logger = logging.getLogger(__name__)


def register_{chain_name}_chain(
    ao: AgentOrchestrator,
    use_mcp: bool = False,
    mcp_config: dict[str, str] | None = None,
    llm_client: Any | None = None,
) -> None:
    """
    Register the chain with an AgentOrchestrator instance.

    Args:
        ao: AgentOrchestrator instance to register with
        use_mcp: Whether to use MCP agents (production) or mock agents
        mcp_config: Optional MCP configuration with agent URLs
        llm_client: Optional LLM client for analysis generation
    """

    # ══════════════════════════════════════════════════════════════════════════
    # ENABLE DEFAULT MIDDLEWARE
    # ══════════════════════════════════════════════════════════════════════════

    from agentorchestrator.middleware.offload import OffloadMiddleware

    offload_middleware = OffloadMiddleware(
        default_threshold_bytes=100_000,  # 100KB threshold
    )
    ao.add_middleware(offload_middleware)
    logger.debug("Added OffloadMiddleware for large payload handling")

    # ══════════════════════════════════════════════════════════════════════════
    # REGISTER AGENTS
    # ══════════════════════════════════════════════════════════════════════════

    register_{chain_name}_agents(ao)
    agents: dict[str, Any] = {}
    if use_mcp and mcp_config:
        agents = get_{chain_name}_agents(ao, **mcp_config)
    else:
        agents = get_{chain_name}_agents(ao)

    # ══════════════════════════════════════════════════════════════════════════
    # INITIALIZE SERVICES
    # ══════════════════════════════════════════════════════════════════════════

    context_builder_service = ContextBuilderService()
    content_prioritization_service = ContentPrioritizationService()
    response_builder_service = ResponseBuilderService(
        llm_client=llm_client,
        agents=agents,
    )

    # ══════════════════════════════════════════════════════════════════════════
    # STEP 1: CONTEXT BUILDER
    # ══════════════════════════════════════════════════════════════════════════

    @ao.step(
        name="context_builder",
        description="Extract context from the request",
        produces=["context_output"],
    )
    async def context_builder_step(ctx) -> dict[str, Any]:
        """Stage 1: Build context from the incoming request."""
        request_data = ctx.get("request", {})

        if isinstance(request_data, dict):
            request = ChainRequest(**request_data)
        else:
            request = request_data

        logger.info(f"[Step 1] Context Builder: {request.primary_input}")

        output: ContextBuilderOutput = await context_builder_service.execute(request)

        ctx.set("context_output", output)

        return {
            "step": "context_builder",
            "success": len(output.errors) == 0,
        }

    # ══════════════════════════════════════════════════════════════════════════
    # STEP 2: CONTENT PRIORITIZATION
    # ══════════════════════════════════════════════════════════════════════════

    @ao.step(
        name="content_prioritization",
        description="Prioritize data sources and generate subqueries",
        deps=["context_builder"],
        produces=["prioritization_output"],
    )
    async def content_prioritization_step(ctx) -> dict[str, Any]:
        """Stage 2: Prioritize content sources and generate subqueries."""
        context_output: ContextBuilderOutput = ctx.get("context_output")

        logger.info("[Step 2] Content Prioritization")

        output: ContentPrioritizationOutput = await content_prioritization_service.execute(
            context_output
        )

        ctx.set("prioritization_output", output)

        return {
            "step": "content_prioritization",
            "sources_count": len(output.prioritized_sources),
            "subqueries_count": len(output.subqueries),
        }

    # ══════════════════════════════════════════════════════════════════════════
    # STEP 3: RESPONSE BUILDER
    # ══════════════════════════════════════════════════════════════════════════

    @ao.step(
        name="response_builder",
        description="Execute agents and build final response",
        deps=["content_prioritization"],
        produces=["response_output", "final_response"],
        timeout_ms=120000,
    )
    async def response_builder_step(ctx) -> dict[str, Any]:
        """Stage 3: Build the final response."""
        context_output: ContextBuilderOutput = ctx.get("context_output")
        prioritization_output: ContentPrioritizationOutput = ctx.get("prioritization_output")

        logger.info("[Step 3] Response Builder")

        output: ResponseBuilderOutput = await response_builder_service.execute(
            context_output,
            prioritization_output,
        )

        final_response = ChainResponse(
            result=output.final_output,
            agent_results={k: v.model_dump() for k, v in output.agent_results.items()},
            timing_ms=output.timing_ms,
        )

        ctx.set("response_output", output)
        ctx.set("final_response", final_response)

        return {
            "step": "response_builder",
            "agents_succeeded": output.agents_succeeded,
            "agents_failed": output.agents_failed,
        }

    # ══════════════════════════════════════════════════════════════════════════
    # CHAIN DEFINITION
    # ══════════════════════════════════════════════════════════════════════════

    @ao.chain(
        name="{chain_name}_chain",
        description="{description}",
    )
    class {ChainClass}Chain:
        """
        {ChainName} Chain

        Pipeline:
            ┌─────────────────┐     ┌───────────────────────┐     ┌──────────────────┐
            │ context_builder │ ──► │ content_prioritization │ ──► │ response_builder │
            └─────────────────┘     └───────────────────────┘     └──────────────────┘
        """

        steps = ["context_builder", "content_prioritization", "response_builder"]


# ═══════════════════════════════════════════════════════════════════════════════
#                           CONVENIENCE FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════


async def run_{chain_name}_chain(
    primary_input: str,
    use_mcp: bool = False,
    mcp_config: dict[str, str] | None = None,
    llm_client: Any | None = None,
) -> dict[str, Any]:
    """
    Convenience function to run the chain.

    Example:
        result = await run_{chain_name}_chain("input data")
        print(result["context"]["final_response"])
    """
    ao = AgentOrchestrator(name="{chain_name}", isolated=True)
    register_{chain_name}_chain(ao, use_mcp=use_mcp, mcp_config=mcp_config, llm_client=llm_client)

    request = {"primary_input": primary_input}

    result = await ao.launch("{chain_name}_chain", {"request": request})
    return result


def run_{chain_name}_chain_sync(
    primary_input: str,
    use_mcp: bool = False,
    mcp_config: dict[str, str] | None = None,
    llm_client: Any | None = None,
) -> dict[str, Any]:
    """Synchronous version of run_{chain_name}_chain."""
    import asyncio
    return asyncio.run(run_{chain_name}_chain(primary_input, use_mcp, mcp_config, llm_client))
```

---

## Step 5: Create Services `__init__.py`

```python
"""
{ChainName} Services

Pipeline:
  01_context_builder.py     → Extract context from request
  02_content_prioritization.py → Prioritize sources, generate subqueries
  03_response_builder.py    → Execute agents, build final response
"""

# Services
from {chain_name}.services._01_context_builder import ContextBuilderService
from {chain_name}.services._02_content_prioritization import ContentPrioritizationService
from {chain_name}.services._03_response_builder import ResponseBuilderService

# Models
from {chain_name}.services.models import (
    ChainRequest,
    ChainRequestOverrides,
    ChainResponse,
    ContextBuilderOutput,
    ContentPrioritizationOutput,
    ResponseBuilderOutput,
    # Add other models...
)

# Agents
from {chain_name}.services.agents import (
    register_{chain_name}_agents,
    get_{chain_name}_agents,
    ToolName,
)

__all__ = [
    # Services
    "ContextBuilderService",
    "ContentPrioritizationService",
    "ResponseBuilderService",
    # Models
    "ChainRequest",
    "ChainRequestOverrides",
    "ChainResponse",
    "ContextBuilderOutput",
    "ContentPrioritizationOutput",
    "ResponseBuilderOutput",
    # Agents
    "register_{chain_name}_agents",
    "get_{chain_name}_agents",
    "ToolName",
]
```

---

## Key Patterns to Follow

### 1. Decorator Pattern
- Use `@ao.step()` with `name`, `description`, `produces`, `deps`, `timeout_ms`
- Use `@ao.chain()` with `name`, `description`, and `steps` class attribute

### 2. Context Management
- Steps receive `ctx` and use `ctx.get()` / `ctx.set()` for data flow
- Each step returns a dict with status info for logging

### 3. Service Pattern
- Services are stateless and have an async `execute()` method
- Services receive typed inputs and return typed outputs (Pydantic models)

### 4. Agent Pattern
- Agents extend `BaseAgent` or `MCPAdapterAgent`
- Agents implement `async fetch(query, **kwargs) -> AgentResult`
- Use `@testable` decorator for test configuration
- Register with resilience config: `resilient=True, resilient_config={...}`

### 5. Middleware
- Add `OffloadMiddleware` for large payloads (SEC filings, etc.)
- Consider `CacheMiddleware`, `LoggerMiddleware`, `MetricsMiddleware`

### 6. Error Handling
- Services track errors in `errors: dict[str, str]`
- Agents return `AgentResult` with `error` field for failures
- Steps handle exceptions gracefully

---

## Reference Files

- **Chain Example**: [cmpt/chain.py](cmpt/chain.py)
- **Service Example**: [cmpt/services/_01_context_builder.py](cmpt/services/_01_context_builder.py)
- **Agent Example**: [cmpt/services/agents.py](cmpt/services/agents.py)
- **Models Example**: [cmpt/services/models.py](cmpt/services/models.py)
- **Middleware**: [agentorchestrator/middleware/](agentorchestrator/middleware/)
