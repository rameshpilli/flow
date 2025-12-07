"""
Dynamic Agent Test Suite Generator

Auto-generates test suites for registered agents.

Usage:
    from agentorchestrator.testing import testable, generate_test_suite

    @testable(agent_configs={...}, test_query="TEST")
    def register_agents(ao):
        ao.agent(name="agent1")(Agent1)

    await register_agents.test(ao)
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from agentorchestrator.agents.base import BaseAgent, AgentResult

logger = logging.getLogger(__name__)

# Box drawing characters for clean output
LINE_H = "─"
LINE_DOUBLE = "═"


@dataclass
class TestConfig:
    """Configuration for a single agent test."""
    agent_name: str
    runtime_config: dict[str, Any] = field(default_factory=dict)
    test_params: dict[str, Any] = field(default_factory=dict)
    expected_behavior: str = "success"


@dataclass
class TestResult:
    """Result of a single agent test."""
    agent_name: str
    passed: bool
    duration_ms: float
    error: str | None = None
    agent_result: AgentResult | None = None


class AgentTestSuite:
    """Dynamic test suite for registered agents."""

    def __init__(
        self,
        orchestrator: Any,
        test_configs: list[TestConfig],
        test_query: str = "TEST",
        verbose: bool = True,
        show_descriptions: bool = False,
    ):
        self.ao = orchestrator
        self.test_configs = test_configs
        self.test_query = test_query
        self.verbose = verbose
        self.show_descriptions = show_descriptions
        self.results: list[TestResult] = []
    
    async def run(self) -> bool:
        """Run all tests. Returns True if all passed."""
        if self.verbose:
            self._print_header()
        
        agents = await self._initialize_agents()
        
        for config in self.test_configs:
            agent = agents.get(config.agent_name)
            if not agent:
                self._add_result(config.agent_name, False, 0, error="Agent not found")
                continue
            
            result = await self._test_agent(agent, config)
            self.results.append(result)
        
        await self._cleanup_agents(agents)
        
        if self.verbose:
            self._print_summary()
        
        return all(r.passed for r in self.results)
    
    async def _initialize_agents(self) -> dict[str, BaseAgent]:
        """Initialize all agents with runtime configs and display discovered tools."""
        agents = {}

        if self.verbose:
            print()
            print(LINE_H * 80)
            print("DISCOVERY PHASE")
            print(LINE_H * 80)
            print()

        for config in self.test_configs:
            try:
                agent = self.ao.get_agent(config.agent_name, **config.runtime_config)
                await agent.initialize()
                agents[config.agent_name] = agent

                if self.verbose:
                    self._print_agent_discovery(config.agent_name, agent)

            except Exception as e:
                if self.verbose:
                    print(f"[{config.agent_name}] Failed: {e}")
                    print()

        return agents

    def _print_agent_discovery(self, agent_name: str, agent: BaseAgent) -> None:
        """Print discovered tools and their schemas for an agent."""
        # Unwrap ResilientAgent to get the actual agent
        actual_agent = agent
        if hasattr(agent, "_wrapped_agent"):
            actual_agent = agent._wrapped_agent

        # Get server URL if available (for MCP agents)
        server_url = ""
        if hasattr(actual_agent, "_config") and hasattr(actual_agent._config, "server_url"):
            server_url = f" -> {actual_agent._config.server_url}" if actual_agent._config.server_url else ""

        print(f"[{agent_name}]{server_url}")

        # Check if agent has MCP tools
        tools = []
        if hasattr(actual_agent, "_tools") and actual_agent._tools:
            tools = actual_agent._tools

        if tools:
            print(f"  Tools ({len(tools)}):")
            for tool in tools:
                print(f"    - {tool.name}")

                # Show description only if show_descriptions is True
                if self.show_descriptions and tool.description:
                    # Truncate long descriptions
                    desc = tool.description.strip()
                    if len(desc) > 200:
                        desc = desc[:197] + "..."
                    # Show first line only for cleaner output
                    first_line = desc.split('\n')[0].strip()
                    print(f"        {first_line}")

                # Print input schema parameters
                if tool.input_schema:
                    props = tool.input_schema.get("properties", {})
                    required = tool.input_schema.get("required", [])

                    if props:
                        for param_name, param_info in props.items():
                            param_type = param_info.get("type", "any")
                            is_required = param_name in required
                            default = param_info.get("default")

                            # Build parameter description
                            type_info = f"({param_type}"
                            if is_required:
                                type_info += ", required"
                            if default is not None:
                                type_info += f", default: {default}"
                            type_info += ")"

                            print(f"        {param_name} {type_info}")
        else:
            print("  Tools: (none discovered)")

        print()
    
    async def _test_agent(self, agent: BaseAgent, config: TestConfig) -> TestResult:
        """Test a single agent."""
        start = time.perf_counter()

        try:
            result = await agent.fetch(self.test_query, **config.test_params)
            duration_ms = (time.perf_counter() - start) * 1000

            if config.expected_behavior == "success":
                passed = result.success
            elif config.expected_behavior == "error":
                passed = not result.success
            else:
                passed = True

            return TestResult(
                agent_name=config.agent_name,
                passed=passed,
                duration_ms=duration_ms,
                agent_result=result,
            )

        except Exception as e:
            duration_ms = (time.perf_counter() - start) * 1000
            passed = config.expected_behavior == "error"

            return TestResult(
                agent_name=config.agent_name,
                passed=passed,
                duration_ms=duration_ms,
                error=str(e),
            )
    
    async def _cleanup_agents(self, agents: dict[str, BaseAgent]) -> None:
        """Cleanup all agents."""
        for agent in agents.values():
            try:
                await agent.cleanup()
            except Exception:
                pass
    
    def _add_result(self, agent_name: str, passed: bool, duration_ms: float, error: str | None = None):
        """Add a test result."""
        self.results.append(TestResult(
            agent_name=agent_name,
            passed=passed,
            duration_ms=duration_ms,
            error=error,
        ))
    
    def _print_header(self):
        """Print test header."""
        print()
        print(LINE_DOUBLE * 80)
        print(f"AGENT TEST SUITE: {self.ao.name}")
        print(LINE_DOUBLE * 80)
    
    def _print_summary(self):
        """Print test summary."""
        passed = sum(1 for r in self.results if r.passed)
        total = len(self.results)

        print()
        print(LINE_DOUBLE * 80)
        print(f"RESULTS: {passed}/{total} passed")
        print(LINE_DOUBLE * 80)

        for result in self.results:
            status = "PASS" if result.passed else "FAIL"
            items_info = ""
            if result.agent_result and result.agent_result.data:
                data = result.agent_result.data
                if isinstance(data, dict):
                    items = data.get("items", [])
                    if isinstance(items, list):
                        items_info = f"  {len(items)} items"

            error_info = f"  Error: {result.error}" if result.error else ""
            print(f"  [{status}] {result.agent_name:<20} {result.duration_ms:>8.0f}ms{items_info}{error_info}")

        print()


def generate_test_suite(
    orchestrator: Any,
    agent_configs: dict[str, dict[str, Any]] | None = None,
    test_query: str = "TEST",
    test_params: dict[str, Any] | None = None,
    verbose: bool = True,
    show_descriptions: bool = False,
) -> AgentTestSuite:
    """
    Generate a test suite for registered agents.

    Args:
        orchestrator: AgentOrchestrator instance
        agent_configs: Dict mapping agent_name -> runtime config
        test_query: Query to use for testing
        test_params: Additional parameters to pass to agent.fetch()
        verbose: Whether to print detailed output
        show_descriptions: Whether to show tool descriptions (default: False for compact output)

    Returns:
        AgentTestSuite ready to run
    """
    agent_configs = agent_configs or {}
    test_params = test_params or {}

    registered_agents = orchestrator.list_agents()

    test_configs = []
    for agent_name in registered_agents:
        runtime_config = agent_configs.get(agent_name, {})
        test_configs.append(TestConfig(
            agent_name=agent_name,
            runtime_config=runtime_config,
            test_params=test_params,
            expected_behavior="success",
        ))

    return AgentTestSuite(
        orchestrator=orchestrator,
        test_configs=test_configs,
        test_query=test_query,
        verbose=verbose,
        show_descriptions=show_descriptions,
    )


def testable(
    agent_configs: dict[str, dict[str, Any]] | None = None,
    test_query: str = "TEST",
    test_params: dict[str, Any] | None = None,
):
    """
    Decorator to make agent registration functions testable.

    Adds a .test() method to the decorated function.

    Usage:
        @testable(agent_configs={...}, test_query="AAPL")
        def register_agents(ao):
            ao.agent(name="news_agent")(NewsAgent)

        # Run tests (compact output by default)
        await register_agents.test(ao)

        # Run tests with full descriptions
        await register_agents.test(ao, show_descriptions=True)
    """
    def decorator(register_func: Callable):
        async def test_wrapper(
            orchestrator: Any = None,
            verbose: bool = True,
            show_descriptions: bool = False,
        ):
            """Auto-generated test method."""
            if orchestrator is None:
                raise ValueError("Orchestrator instance required for testing")

            suite = generate_test_suite(
                orchestrator,
                agent_configs=agent_configs,
                test_query=test_query,
                test_params=test_params,
                verbose=verbose,
                show_descriptions=show_descriptions,
            )
            return await suite.run()

        register_func.test = test_wrapper
        register_func._is_testable = True

        return register_func

    return decorator