# Create New Service

Create a new AgentOrchestrator service following established patterns.

## Usage
```
/new-service <service_name> <description>
```

Example: `/new-service risk_calculator "Calculates portfolio risk metrics"`

---

## Service Pattern

Services are stateless classes that encapsulate business logic for chain steps.

```
Service Design:
┌─────────────────────────────────────────┐
│ Service                                 │
├─────────────────────────────────────────┤
│ - Configuration (timeouts, URLs, etc.)  │
│ - Dependency injection (LLM, agents)    │
├─────────────────────────────────────────┤
│ async execute(input) -> output          │
│   └── Orchestrates private methods      │
│       └── _extract_* (extractors)       │
│       └── _compute_* (calculations)     │
│       └── _apply_* (transformations)    │
└─────────────────────────────────────────┘
```

---

## Service Template

```python
"""
{ServiceName} Service

{ServiceDescription}

This is stage {N} of the {chain_name} chain.
"""

import asyncio
import logging
from datetime import datetime
from typing import Any

from {chain_name}.services.models import (
    {ServiceInput}Input,
    {ServiceOutput}Output,
    # Other models as needed
)

logger = logging.getLogger(__name__)


class {ServiceName}Service:
    """
    Service for {service_description}.

    Usage:
        service = {ServiceName}Service()
        output = await service.execute(input_data)

    Or as a step in AgentOrchestrator:
        @ao.step(produces=["{service_output}"])
        async def {service_step}(ctx):
            service = {ServiceName}Service()
            output = await service.execute(ctx.get("input"))
            ctx.set("{service_output}", output)
            return output.model_dump()
    """

    # ═══════════════════════════════════════════════════════════════════════════
    #                           CONFIGURATION
    # ═══════════════════════════════════════════════════════════════════════════

    # Default timeouts and limits
    DEFAULT_TIMEOUT: float = 20.0
    DEFAULT_BATCH_SIZE: int = 10

    # Default per-operation time budgets (seconds)
    DEFAULT_OPERATION_TIMEOUTS: dict[str, float] = {
        "operation_1": 10.0,
        "operation_2": 5.0,
        "operation_3": 8.0,
    }

    def __init__(
        self,
        timeout: float = 20.0,
        operation_timeouts: dict[str, float] | None = None,
        llm_client: Any | None = None,
        agents: dict[str, Any] | None = None,
        config: dict[str, Any] | None = None,
    ):
        """
        Initialize the service.

        Args:
            timeout: Default HTTP/operation timeout in seconds
            operation_timeouts: Per-operation time budgets in seconds
            llm_client: Optional LLM client for AI operations
            agents: Optional dict of data agents
            config: Additional configuration
        """
        self.timeout = timeout
        self.operation_timeouts = {
            **self.DEFAULT_OPERATION_TIMEOUTS,
            **(operation_timeouts or {}),
        }
        self.llm_client = llm_client
        self.agents = agents or {}
        self.config = config or {}

    # ═══════════════════════════════════════════════════════════════════════════
    #                           MAIN EXECUTE METHOD
    # ═══════════════════════════════════════════════════════════════════════════

    async def execute(
        self,
        input_data: {ServiceInput}Input,
    ) -> {ServiceOutput}Output:
        """
        Execute the service logic.

        Args:
            input_data: Input data for the service

        Returns:
            {ServiceOutput}Output with results
        """
        start_time = datetime.now()
        timing: dict[str, float] = {}
        errors: dict[str, str] = {}

        # Initialize output
        output = {ServiceOutput}Output(errors={}, timing_ms={})

        # ───────────────────────────────────────────────────────────────────────
        # STEP 1: Run parallel operations
        # ───────────────────────────────────────────────────────────────────────

        tasks = []

        # Add operations that can run in parallel
        tasks.append(("operation_1", self._perform_operation_1(input_data)))
        tasks.append(("operation_2", self._perform_operation_2(input_data)))

        if tasks:
            # Wrap each task with timeout protection
            wrapped_tasks = []
            for name, coro in tasks:
                timeout = self.operation_timeouts.get(name, 10.0)
                wrapped_tasks.append((name, asyncio.wait_for(coro, timeout=timeout)))

            results = await asyncio.gather(
                *[task[1] for task in wrapped_tasks],
                return_exceptions=True,
            )

            for (name, _), result in zip(wrapped_tasks, results):
                if isinstance(result, asyncio.TimeoutError):
                    timeout = self.operation_timeouts.get(name, 10.0)
                    errors[name] = f"Operation timed out after {timeout}s"
                    logger.error(f"Operation {name} timed out after {timeout}s")
                elif isinstance(result, Exception):
                    errors[name] = str(result)
                    logger.error(f"Operation {name} failed: {result}")
                else:
                    data, error, duration = result
                    timing[name] = duration

                    if error:
                        errors[name] = error
                    else:
                        self._apply_result(output, name, data)

        # ───────────────────────────────────────────────────────────────────────
        # STEP 2: Run sequential operations (depend on parallel results)
        # ───────────────────────────────────────────────────────────────────────

        if not errors.get("operation_1"):
            op3_timeout = self.operation_timeouts.get("operation_3", 8.0)
            try:
                op3_start = datetime.now()
                result, error = await asyncio.wait_for(
                    self._perform_operation_3(output),
                    timeout=op3_timeout,
                )
                timing["operation_3"] = (datetime.now() - op3_start).total_seconds() * 1000

                if error:
                    errors["operation_3"] = error
                else:
                    output.final_result = result
            except asyncio.TimeoutError:
                errors["operation_3"] = f"Operation timed out after {op3_timeout}s"
            except Exception as e:
                errors["operation_3"] = str(e)

        # ───────────────────────────────────────────────────────────────────────
        # FINALIZE OUTPUT
        # ───────────────────────────────────────────────────────────────────────

        output.errors = errors
        output.timing_ms = timing

        total_duration = (datetime.now() - start_time).total_seconds() * 1000
        timing["total"] = total_duration

        logger.info(f"{self.__class__.__name__} completed in {total_duration:.2f}ms")
        return output

    def _apply_result(
        self,
        output: {ServiceOutput}Output,
        name: str,
        data: Any,
    ) -> None:
        """Apply operation result to output."""
        if name == "operation_1" and data:
            output.operation_1_result = data
        elif name == "operation_2" and data:
            output.operation_2_result = data

    # ═══════════════════════════════════════════════════════════════════════════
    #                           PRIVATE OPERATIONS
    # ═══════════════════════════════════════════════════════════════════════════

    async def _perform_operation_1(
        self,
        input_data: {ServiceInput}Input,
    ) -> tuple[Any | None, str | None, float]:
        """
        Perform operation 1.

        Returns:
            Tuple of (result_data, error_message, duration_ms)
        """
        start = datetime.now()
        error = None
        result = None

        try:
            # Your operation logic here
            logger.info(f"Performing operation 1 for: {input_data}")

            # Example: Extract or compute something
            result = {
                "processed": True,
                "value": "computed_value",
            }

        except Exception as e:
            error = str(e)
            logger.error(f"Operation 1 failed: {e}")

        duration = (datetime.now() - start).total_seconds() * 1000
        return result, error, duration

    async def _perform_operation_2(
        self,
        input_data: {ServiceInput}Input,
    ) -> tuple[Any | None, str | None, float]:
        """
        Perform operation 2.

        Returns:
            Tuple of (result_data, error_message, duration_ms)
        """
        start = datetime.now()
        error = None
        result = None

        try:
            logger.info(f"Performing operation 2 for: {input_data}")

            # Your operation logic here
            result = {"status": "success"}

        except Exception as e:
            error = str(e)
            logger.error(f"Operation 2 failed: {e}")

        duration = (datetime.now() - start).total_seconds() * 1000
        return result, error, duration

    async def _perform_operation_3(
        self,
        current_output: {ServiceOutput}Output,
    ) -> tuple[Any | None, str | None]:
        """
        Perform operation 3 (depends on previous operations).

        Returns:
            Tuple of (result_data, error_message)
        """
        error = None
        result = None

        try:
            # Use results from previous operations
            op1_result = current_output.operation_1_result

            if op1_result:
                result = {
                    "combined": True,
                    "source": op1_result,
                }

        except Exception as e:
            error = str(e)
            logger.error(f"Operation 3 failed: {e}")

        return result, error

    # ═══════════════════════════════════════════════════════════════════════════
    #                           UTILITIES
    # ═══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def validate_input(input_data: Any) -> tuple[bool, str | None]:
        """
        Validate input data.

        Returns:
            Tuple of (is_valid, error_message)
        """
        if input_data is None:
            return False, "Input data is required"
        return True, None

    @staticmethod
    def transform_output(raw_data: Any) -> dict[str, Any]:
        """Transform raw data into expected output format."""
        # Your transformation logic here
        return {"transformed": raw_data}
```

---

## Service with Agent Execution

```python
"""
Response Builder Service

Executes data agents and builds final response.
"""

import asyncio
import logging
import time
from datetime import datetime
from typing import Any

from agentorchestrator.agents.base import AgentResult, BaseAgent

from {chain_name}.services.models import (
    ContextBuilderOutput,
    ContentPrioritizationOutput,
    ResponseBuilderOutput,
    AgentResult as ModelAgentResult,
)

logger = logging.getLogger(__name__)


class ResponseBuilderService:
    """Service that executes agents and builds responses."""

    def __init__(
        self,
        llm_client: Any | None = None,
        agents: dict[str, BaseAgent] | None = None,
        agent_timeout: float = 60.0,
    ):
        self.llm_client = llm_client
        self.agents = agents or {}
        self.agent_timeout = agent_timeout

    async def execute(
        self,
        context: ContextBuilderOutput,
        prioritization: ContentPrioritizationOutput,
    ) -> ResponseBuilderOutput:
        """Execute agents and build response."""
        start_time = datetime.now()
        timing: dict[str, float] = {}
        errors: dict[str, str] = {}

        output = ResponseBuilderOutput()

        # ───────────────────────────────────────────────────────────────────────
        # STEP 1: Execute agents in parallel
        # ───────────────────────────────────────────────────────────────────────

        agent_results = await self._execute_agents(
            prioritization.subqueries_by_agent,
            context,
        )

        for agent_name, result in agent_results.items():
            if result.success:
                output.agents_succeeded += 1
            else:
                output.agents_failed += 1
                errors[agent_name] = result.error or "Unknown error"

            output.agent_results[agent_name] = ModelAgentResult(
                agent=agent_name,
                success=result.success,
                data=result.data,
                duration_ms=result.duration_ms,
                error=result.error,
            )

            timing[f"agent_{agent_name}"] = result.duration_ms

        # ───────────────────────────────────────────────────────────────────────
        # STEP 2: Process agent results with LLM (if configured)
        # ───────────────────────────────────────────────────────────────────────

        if self.llm_client and output.agents_succeeded > 0:
            try:
                llm_start = datetime.now()
                output.final_output = await self._process_with_llm(
                    agent_results, context
                )
                timing["llm_processing"] = (datetime.now() - llm_start).total_seconds() * 1000
            except Exception as e:
                errors["llm_processing"] = str(e)
                logger.error(f"LLM processing failed: {e}")

        output.errors = errors
        output.timing_ms = timing
        output.timing_ms["total"] = (datetime.now() - start_time).total_seconds() * 1000

        return output

    async def _execute_agents(
        self,
        subqueries_by_agent: dict[str, list],
        context: ContextBuilderOutput,
    ) -> dict[str, AgentResult]:
        """Execute all agents in parallel."""
        results: dict[str, AgentResult] = {}

        if not subqueries_by_agent:
            return results

        tasks = []
        agent_names = []

        for agent_name, subqueries in subqueries_by_agent.items():
            agent = self.agents.get(agent_name)
            if not agent:
                logger.warning(f"Agent {agent_name} not found")
                continue

            if subqueries:
                subquery = subqueries[0]  # Use first subquery
                task = asyncio.wait_for(
                    agent.fetch(subquery.query, **subquery.params),
                    timeout=self.agent_timeout,
                )
                tasks.append(task)
                agent_names.append(agent_name)

        if tasks:
            task_results = await asyncio.gather(*tasks, return_exceptions=True)

            for agent_name, result in zip(agent_names, task_results):
                if isinstance(result, asyncio.TimeoutError):
                    results[agent_name] = AgentResult(
                        data=None,
                        source=agent_name,
                        query="",
                        duration_ms=self.agent_timeout * 1000,
                        error=f"Agent timed out after {self.agent_timeout}s",
                    )
                elif isinstance(result, Exception):
                    results[agent_name] = AgentResult(
                        data=None,
                        source=agent_name,
                        query="",
                        duration_ms=0,
                        error=str(result),
                    )
                else:
                    results[agent_name] = result

        return results

    async def _process_with_llm(
        self,
        agent_results: dict[str, AgentResult],
        context: ContextBuilderOutput,
    ) -> dict[str, Any]:
        """Process agent results with LLM."""
        # Combine agent data for LLM
        combined_data = {
            name: result.data
            for name, result in agent_results.items()
            if result.success and result.data
        }

        # Your LLM processing logic here
        # Example: structured output extraction
        prompt = f"Analyze the following data: {combined_data}"

        # response = await self.llm_client.generate(prompt)
        # return response

        return {"analyzed": True, "source_data": combined_data}
```

---

## Service Models Pattern

```python
class {ServiceOutput}Output(BaseModel):
    """Output from {ServiceName} service."""

    # Primary results
    operation_1_result: dict[str, Any] | None = None
    operation_2_result: dict[str, Any] | None = None
    final_result: dict[str, Any] | None = None

    # Errors and timing
    errors: dict[str, str] = Field(default_factory=dict)
    timing_ms: dict[str, float] | None = None
```

---

## Best Practices

### 1. Parallel Execution
```python
# Run independent operations in parallel
tasks = [
    ("op1", self._operation_1(input)),
    ("op2", self._operation_2(input)),
]
results = await asyncio.gather(*[t[1] for t in tasks], return_exceptions=True)
```

### 2. Timeout Protection
```python
# Wrap each operation with timeout
wrapped = asyncio.wait_for(coro, timeout=timeout_seconds)
```

### 3. Structured Error Handling
```python
# Track errors by operation name
errors: dict[str, str] = {}
if isinstance(result, Exception):
    errors["operation_name"] = str(result)
```

### 4. Timing Instrumentation
```python
# Track timing for each operation
timing: dict[str, float] = {}
start = datetime.now()
# ... operation ...
timing["operation_name"] = (datetime.now() - start).total_seconds() * 1000
```

### 5. Dependency Injection
```python
# Accept dependencies in constructor
def __init__(self, llm_client=None, agents=None, config=None):
    self.llm_client = llm_client
    self.agents = agents or {}
```

---

## Reference Files

- **Context Builder**: [cmpt/services/_01_context_builder.py](cmpt/services/_01_context_builder.py)
- **Content Prioritization**: [cmpt/services/_02_content_prioritization.py](cmpt/services/_02_content_prioritization.py)
- **Response Builder**: [cmpt/services/_03_response_builder.py](cmpt/services/_03_response_builder.py)
- **Models**: [cmpt/services/models.py](cmpt/services/models.py)
