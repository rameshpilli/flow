"""
AgentOrchestrator Health Check Aggregator

Provides comprehensive health checks for external dependencies:
- Agents (data agents, resilient agents)
- Context store (Redis)
- LLM gateway
- MCP connectors (if configured)

Usage:
    from agentorchestrator.utils.health import HealthAggregator, run_health_checks

    # Quick check
    result = await run_health_checks()
    print(result.status)  # "healthy", "degraded", "unhealthy"

    # Detailed check with custom components
    aggregator = HealthAggregator()
    aggregator.register_check("my_service", my_health_check_fn)
    result = await aggregator.check_all()

CLI:
    ao health              # Basic health check
    ao health --detailed   # Full dependency checks
    ao health --json       # JSON output
"""

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """Health check status levels."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class ComponentHealth:
    """Health status for a single component."""

    name: str
    status: HealthStatus
    message: str = ""
    latency_ms: float = 0.0
    details: dict[str, Any] = field(default_factory=dict)
    checked_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status.value,
            "message": self.message,
            "latency_ms": self.latency_ms,
            "details": self.details,
            "checked_at": self.checked_at.isoformat(),
        }


@dataclass
class AggregatedHealth:
    """Aggregated health status across all components."""

    status: HealthStatus
    components: list[ComponentHealth] = field(default_factory=list)
    total_latency_ms: float = 0.0
    checked_at: datetime = field(default_factory=datetime.utcnow)
    version: str = ""
    environment: str = ""

    @property
    def healthy_count(self) -> int:
        return sum(1 for c in self.components if c.status == HealthStatus.HEALTHY)

    @property
    def degraded_count(self) -> int:
        return sum(1 for c in self.components if c.status == HealthStatus.DEGRADED)

    @property
    def unhealthy_count(self) -> int:
        return sum(1 for c in self.components if c.status == HealthStatus.UNHEALTHY)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "version": self.version,
            "environment": self.environment,
            "total_latency_ms": self.total_latency_ms,
            "checked_at": self.checked_at.isoformat(),
            "summary": {
                "healthy": self.healthy_count,
                "degraded": self.degraded_count,
                "unhealthy": self.unhealthy_count,
                "total": len(self.components),
            },
            "components": [c.to_dict() for c in self.components],
        }


# Type alias for health check functions
HealthCheckFn = Callable[[], Awaitable[ComponentHealth]]


class HealthAggregator:
    """
    Aggregates health checks from multiple components.

    Usage:
        aggregator = HealthAggregator()
        aggregator.register_check("redis", check_redis_health)
        aggregator.register_check("llm", check_llm_health)

        result = await aggregator.check_all()
        print(result.status)  # Overall status
    """

    def __init__(
        self,
        timeout_seconds: float = 10.0,
        parallel: bool = True,
    ):
        """
        Initialize health aggregator.

        Args:
            timeout_seconds: Timeout for each health check
            parallel: Run checks in parallel (True) or sequential (False)
        """
        self.timeout_seconds = timeout_seconds
        self.parallel = parallel
        self._checks: dict[str, HealthCheckFn] = {}

    def register_check(self, name: str, check_fn: HealthCheckFn) -> None:
        """Register a health check function."""
        self._checks[name] = check_fn
        logger.debug(f"Registered health check: {name}")

    def unregister_check(self, name: str) -> None:
        """Unregister a health check."""
        self._checks.pop(name, None)

    async def check_component(self, name: str, check_fn: HealthCheckFn) -> ComponentHealth:
        """Run a single health check with timeout."""
        start = time.perf_counter()
        try:
            result = await asyncio.wait_for(
                check_fn(),
                timeout=self.timeout_seconds,
            )
            result.latency_ms = (time.perf_counter() - start) * 1000
            return result
        except asyncio.TimeoutError:
            return ComponentHealth(
                name=name,
                status=HealthStatus.UNHEALTHY,
                message=f"Health check timed out after {self.timeout_seconds}s",
                latency_ms=(time.perf_counter() - start) * 1000,
            )
        except Exception as e:
            return ComponentHealth(
                name=name,
                status=HealthStatus.UNHEALTHY,
                message=f"Health check failed: {e}",
                latency_ms=(time.perf_counter() - start) * 1000,
                details={"error_type": type(e).__name__},
            )

    async def check_all(self) -> AggregatedHealth:
        """
        Run all registered health checks.

        Returns:
            AggregatedHealth with overall status and per-component details
        """
        from agentorchestrator.utils.config import get_config

        start = time.perf_counter()
        config = get_config()

        if not self._checks:
            return AggregatedHealth(
                status=HealthStatus.UNKNOWN,
                version=config.service_version,
                environment=config.environment,
                total_latency_ms=0,
            )

        # Run checks
        if self.parallel:
            tasks = [
                self.check_component(name, fn)
                for name, fn in self._checks.items()
            ]
            results = await asyncio.gather(*tasks)
        else:
            results = []
            for name, fn in self._checks.items():
                results.append(await self.check_component(name, fn))

        total_latency = (time.perf_counter() - start) * 1000

        # Determine overall status
        unhealthy = any(r.status == HealthStatus.UNHEALTHY for r in results)
        degraded = any(r.status == HealthStatus.DEGRADED for r in results)

        if unhealthy:
            overall_status = HealthStatus.UNHEALTHY
        elif degraded:
            overall_status = HealthStatus.DEGRADED
        else:
            overall_status = HealthStatus.HEALTHY

        return AggregatedHealth(
            status=overall_status,
            components=list(results),
            total_latency_ms=total_latency,
            version=config.service_version,
            environment=config.environment,
        )


# ═══════════════════════════════════════════════════════════════════════════════
#                         BUILT-IN HEALTH CHECKS
# ═══════════════════════════════════════════════════════════════════════════════


async def check_config_health() -> ComponentHealth:
    """Check if configuration is properly loaded."""
    try:
        from agentorchestrator.utils.config import get_config
        config = get_config()
        return ComponentHealth(
            name="config",
            status=HealthStatus.HEALTHY,
            message="Configuration loaded successfully",
            details={
                "environment": config.environment,
                "llm_configured": bool(config.llm_api_key),
                "otel_enabled": config.otel_enabled,
            },
        )
    except Exception as e:
        return ComponentHealth(
            name="config",
            status=HealthStatus.UNHEALTHY,
            message=f"Configuration error: {e}",
        )


async def check_redis_health() -> ComponentHealth:
    """Check Redis context store connectivity."""
    try:
        from agentorchestrator.core.context_store import get_context_store
        store = get_context_store()

        # Try a simple ping/set/get operation
        test_key = "__flowforge_health_check__"
        test_value = {"timestamp": datetime.utcnow().isoformat()}

        await store.store(test_key, test_value, ttl_seconds=10)
        retrieved = await store.retrieve(test_key)

        if retrieved is None:
            return ComponentHealth(
                name="redis",
                status=HealthStatus.DEGRADED,
                message="Redis write succeeded but read returned None",
            )

        # Cleanup
        await store.delete(test_key)

        return ComponentHealth(
            name="redis",
            status=HealthStatus.HEALTHY,
            message="Redis context store is healthy",
            details={
                "store_type": type(store).__name__,
            },
        )
    except ImportError:
        return ComponentHealth(
            name="redis",
            status=HealthStatus.DEGRADED,
            message="Redis context store not configured",
        )
    except Exception as e:
        return ComponentHealth(
            name="redis",
            status=HealthStatus.UNHEALTHY,
            message=f"Redis health check failed: {e}",
            details={"error_type": type(e).__name__},
        )


async def check_llm_health() -> ComponentHealth:
    """Check LLM gateway connectivity (basic check)."""
    try:
        from agentorchestrator.utils.config import get_config
        config = get_config()

        if not config.llm_api_key:
            return ComponentHealth(
                name="llm",
                status=HealthStatus.DEGRADED,
                message="LLM API key not configured",
            )

        # Basic connectivity check - just verify the URL is reachable
        # A full health check would make an actual API call
        import aiohttp

        async with aiohttp.ClientSession() as session:
            # Try to reach the base URL (may return 404/401, but connection works)
            try:
                async with session.get(
                    f"{config.llm_base_url}/health",
                    timeout=aiohttp.ClientTimeout(total=5.0),
                ) as response:
                    # Any response means connectivity is OK
                    return ComponentHealth(
                        name="llm",
                        status=HealthStatus.HEALTHY,
                        message="LLM gateway is reachable",
                        details={
                            "base_url": config.llm_base_url,
                            "model": config.llm_model,
                            "status_code": response.status,
                        },
                    )
            except aiohttp.ClientConnectorError:
                return ComponentHealth(
                    name="llm",
                    status=HealthStatus.UNHEALTHY,
                    message=f"Cannot connect to LLM gateway at {config.llm_base_url}",
                )

    except ImportError:
        return ComponentHealth(
            name="llm",
            status=HealthStatus.DEGRADED,
            message="aiohttp not installed for LLM health check",
        )
    except Exception as e:
        return ComponentHealth(
            name="llm",
            status=HealthStatus.UNHEALTHY,
            message=f"LLM health check failed: {e}",
        )


async def check_agents_health() -> ComponentHealth:
    """Check registered agents health."""
    try:
        from agentorchestrator import get_orchestrator

        forge = get_orchestrator()
        agent_names = list(forge._agent_registry.keys())

        if not agent_names:
            return ComponentHealth(
                name="agents",
                status=HealthStatus.HEALTHY,
                message="No agents registered",
                details={"count": 0},
            )

        # Check health of each agent
        healthy_agents = []
        unhealthy_agents = []

        for name in agent_names:
            try:
                agent = forge.get_agent(name)
                if hasattr(agent, "health_check"):
                    is_healthy = await agent.health_check()
                    if is_healthy:
                        healthy_agents.append(name)
                    else:
                        unhealthy_agents.append(name)
                else:
                    # No health check = assume healthy
                    healthy_agents.append(name)
            except Exception as e:
                logger.warning(f"Agent {name} health check failed: {e}")
                unhealthy_agents.append(name)

        if unhealthy_agents:
            status = HealthStatus.DEGRADED if healthy_agents else HealthStatus.UNHEALTHY
            message = f"{len(unhealthy_agents)} agent(s) unhealthy"
        else:
            status = HealthStatus.HEALTHY
            message = f"All {len(healthy_agents)} agent(s) healthy"

        return ComponentHealth(
            name="agents",
            status=status,
            message=message,
            details={
                "total": len(agent_names),
                "healthy": healthy_agents,
                "unhealthy": unhealthy_agents,
            },
        )
    except Exception as e:
        return ComponentHealth(
            name="agents",
            status=HealthStatus.UNHEALTHY,
            message=f"Agent health check failed: {e}",
        )


async def check_chains_health() -> ComponentHealth:
    """Check registered chains are valid."""
    try:
        from agentorchestrator import get_orchestrator

        forge = get_orchestrator()
        chain_names = list(forge._chain_registry.keys())

        if not chain_names:
            return ComponentHealth(
                name="chains",
                status=HealthStatus.HEALTHY,
                message="No chains registered",
                details={"count": 0},
            )

        # Validate each chain
        valid_chains = []
        invalid_chains = []

        for name in chain_names:
            try:
                result = forge.check(name)
                if result.get("valid"):
                    valid_chains.append(name)
                else:
                    invalid_chains.append({
                        "name": name,
                        "errors": result.get("errors", []),
                    })
            except Exception as e:
                invalid_chains.append({
                    "name": name,
                    "errors": [str(e)],
                })

        if invalid_chains:
            status = HealthStatus.DEGRADED
            message = f"{len(invalid_chains)} chain(s) have validation errors"
        else:
            status = HealthStatus.HEALTHY
            message = f"All {len(valid_chains)} chain(s) valid"

        return ComponentHealth(
            name="chains",
            status=status,
            message=message,
            details={
                "total": len(chain_names),
                "valid": valid_chains,
                "invalid": [c["name"] for c in invalid_chains],
            },
        )
    except Exception as e:
        return ComponentHealth(
            name="chains",
            status=HealthStatus.UNHEALTHY,
            message=f"Chain health check failed: {e}",
        )


# ═══════════════════════════════════════════════════════════════════════════════
#                         CONVENIENCE FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════


def create_default_aggregator(include_external: bool = True) -> HealthAggregator:
    """
    Create health aggregator with default checks.

    Args:
        include_external: Include external dependency checks (Redis, LLM)

    Returns:
        Configured HealthAggregator
    """
    aggregator = HealthAggregator()

    # Always check config
    aggregator.register_check("config", check_config_health)

    # Check internal components
    aggregator.register_check("chains", check_chains_health)
    aggregator.register_check("agents", check_agents_health)

    # External dependencies (optional - can be slow)
    if include_external:
        aggregator.register_check("redis", check_redis_health)
        aggregator.register_check("llm", check_llm_health)

    return aggregator


async def run_health_checks(
    include_external: bool = True,
    timeout_seconds: float = 10.0,
) -> AggregatedHealth:
    """
    Run all health checks and return aggregated result.

    Args:
        include_external: Include external dependency checks
        timeout_seconds: Timeout for each check

    Returns:
        AggregatedHealth with overall status
    """
    aggregator = create_default_aggregator(include_external=include_external)
    aggregator.timeout_seconds = timeout_seconds
    return await aggregator.check_all()


async def is_ready() -> bool:
    """
    Quick readiness check for Kubernetes probes.

    Returns True if critical components are healthy.
    """
    result = await run_health_checks(include_external=False, timeout_seconds=5.0)
    return result.status != HealthStatus.UNHEALTHY


async def is_live() -> bool:
    """
    Quick liveness check for Kubernetes probes.

    Just checks if the process is responsive.
    """
    try:
        # Basic check - config loads
        from agentorchestrator.utils.config import get_config
        get_config()
        return True
    except Exception:
        return False
