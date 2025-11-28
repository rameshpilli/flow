"""
FlowForge Main Class

A DAG-based Chain Orchestration Framework inspired by Dagster patterns.
Provides decorator-driven registration, dependency resolution, and execution.
"""

import asyncio
import logging
from collections.abc import Callable
from typing import Any, TypeVar

from flowforge.core.context import ChainContext, ContextManager
from flowforge.core.dag import ChainRunner, DAGExecutor
from flowforge.core.registry import (
    get_agent_registry,
    get_chain_registry,
    get_step_registry,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")
F = TypeVar("F", bound=Callable[..., Any])


class Definitions:
    """
    Container for FlowForge definitions (similar to Dagster's Definitions).

    Holds all registered agents, steps, chains, and resources.
    """

    def __init__(
        self,
        agents: list[Any] | None = None,
        steps: list[Any] | None = None,
        chains: list[Any] | None = None,
        resources: dict[str, Any] | None = None,
    ):
        self.agents = agents or []
        self.steps = steps or []
        self.chains = chains or []
        self.resources = resources or {}


class FlowForge:
    """
    FlowForge: A DAG-based Chain Orchestration Framework

    Inspired by Dagster's clean API patterns. Provides:
    - @fg.step() - Define processing steps (like @asset)
    - @fg.agent() - Define data agents (like resources)
    - @fg.chain() - Define execution chains (like @job)

    Usage:
        import flowforge as fg

        # Define an agent
        @fg.agent
        class NewsAgent:
            async def fetch(self, query: str) -> dict: ...

        # Define steps with dependencies via 'deps' parameter
        @fg.step
        def extract_company(ctx: fg.Context) -> dict: ...

        @fg.step(deps=[extract_company])
        def fetch_data(ctx: fg.Context) -> dict: ...

        # Define a chain
        @fg.chain
        class MeetingPrepChain:
            steps = [extract_company, fetch_data]

        # Validate & Run
        fg.check()                    # Validate definitions
        fg.list_defs()                # List all definitions
        await fg.launch("my_chain")   # Execute chain
    """

    def __init__(
        self,
        name: str = "flowforge",
        version: str = "1.0.0",
        max_parallel: int = 10,
        default_timeout_ms: int = 30000,
    ):
        self.name = name
        self.version = version

        # Registries
        self._agent_registry = get_agent_registry()
        self._step_registry = get_step_registry()
        self._chain_registry = get_chain_registry()

        # Executor & Runner
        self._executor = DAGExecutor(
            max_parallel=max_parallel,
            default_timeout_ms=default_timeout_ms,
        )
        self._runner = ChainRunner(executor=self._executor)

        # Middleware & Resources
        self._middleware: list[Any] = []
        self._resources: dict[str, Any] = {}
        self._context_manager = ContextManager()

        logger.info(f"FlowForge initialized: {name} v{version}")

    # ══════════════════════════════════════════════════════════════════
    #                         DECORATORS
    # ══════════════════════════════════════════════════════════════════

    def agent(
        self,
        cls: type[T] | None = None,
        *,
        name: str | None = None,
        description: str = "",
        group: str | None = None,
    ) -> type[T] | Callable[[type[T]], type[T]]:
        """
        Register a data agent (similar to Dagster's resource).

        Usage:
            @fg.agent
            class NewsAgent:
                async def fetch(self, query: str) -> dict: ...

            @fg.agent(name="sec_agent", group="financial")
            class SECFilingAgent:
                async def fetch(self, query: str) -> dict: ...
        """

        def decorator(cls: type[T]) -> type[T]:
            agent_name = name or cls.__name__
            self._agent_registry.register_agent(
                name=agent_name,
                agent_class=cls,
                description=description,
                group=group,
            )
            cls._fg_name = agent_name
            cls._fg_type = "agent"
            return cls

        if cls is not None:
            return decorator(cls)
        return decorator

    def step(
        self,
        func: F | None = None,
        *,
        name: str | None = None,
        deps: list[Any] | None = None,
        produces: list[str] | None = None,
        description: str = "",
        group: str | None = None,
        timeout_ms: int = 30000,
        retry: int = 0,
    ) -> F | Callable[[F], F]:
        """
        Register a chain step (similar to Dagster's @asset).

        Dependencies can be specified via:
        1. deps parameter (list of step functions or names)
        2. Function parameters (automatic resolution)

        Usage:
            @fg.step
            async def extract_company(ctx): ...

            @fg.step(deps=[extract_company], produces=["company_data"])
            async def process_data(ctx): ...

            # Or with group
            @fg.step(group="context_builder")
            async def build_context(ctx): ...
        """

        def decorator(func: F) -> F:
            step_name = name or func.__name__

            # Resolve dependencies - can be functions or strings
            resolved_deps = []
            if deps:
                for dep in deps:
                    if callable(dep) and hasattr(dep, "_fg_name"):
                        resolved_deps.append(dep._fg_name)
                    elif isinstance(dep, str):
                        resolved_deps.append(dep)
                    else:
                        resolved_deps.append(str(dep))

            self._step_registry.register_step(
                name=step_name,
                handler=func,
                dependencies=resolved_deps,
                produces=produces,
                description=description,
                group=group,
                timeout_ms=timeout_ms,
                retry_count=retry,
            )
            func._fg_name = step_name
            func._fg_type = "step"
            func._fg_deps = resolved_deps
            func._fg_produces = produces or []
            return func

        if func is not None:
            return decorator(func)
        return decorator

    def chain(
        self,
        cls: type[T] | None = None,
        *,
        name: str | None = None,
        description: str = "",
        group: str | None = None,
    ) -> type[T] | Callable[[type[T]], type[T]]:
        """
        Register a chain (similar to Dagster's @job).

        Usage:
            @fg.chain
            class MeetingPrepChain:
                steps = ["extract_company", "fetch_data", "build_response"]

            # Or with step functions directly
            @fg.chain
            class MyChain:
                steps = [extract_company, fetch_data]
        """

        def decorator(cls: type[T]) -> type[T]:
            chain_name = name or cls.__name__

            # Resolve steps - can be functions or strings
            raw_steps = getattr(cls, "steps", [])
            resolved_steps = []
            for s in raw_steps:
                if callable(s) and hasattr(s, "_fg_name"):
                    resolved_steps.append(s._fg_name)
                elif isinstance(s, str):
                    resolved_steps.append(s)
                else:
                    resolved_steps.append(str(s))

            self._chain_registry.register_chain(
                name=chain_name,
                steps=resolved_steps,
                description=description,
                group=group,
            )
            cls._fg_name = chain_name
            cls._fg_type = "chain"
            return cls

        if cls is not None:
            return decorator(cls)
        return decorator

    # ══════════════════════════════════════════════════════════════════
    #                    PROGRAMMATIC REGISTRATION
    # ══════════════════════════════════════════════════════════════════

    def register_agent(
        self,
        name: str,
        agent_class: type,
        **kwargs,
    ) -> "FlowForge":
        """Programmatically register an agent"""
        self._agent_registry.register_agent(name=name, agent_class=agent_class, **kwargs)
        return self

    def register_step(
        self,
        name: str,
        handler: Callable,
        deps: list[str] | None = None,
        produces: list[str] | None = None,
        **kwargs,
    ) -> "FlowForge":
        """Programmatically register a step"""
        self._step_registry.register_step(
            name=name,
            handler=handler,
            dependencies=deps,
            produces=produces,
            **kwargs,
        )
        return self

    def register_chain(
        self,
        name: str,
        steps: list[str],
        **kwargs,
    ) -> "FlowForge":
        """Programmatically register a chain"""
        self._chain_registry.register_chain(name=name, steps=steps, **kwargs)
        return self

    def register_resource(self, name: str, resource: Any) -> "FlowForge":
        """Register a shared resource (config, clients, etc.)"""
        self._resources[name] = resource
        return self

    def use(self, middleware: Any) -> "FlowForge":
        """Add middleware to the execution pipeline"""
        self._middleware.append(middleware)
        self._executor.add_middleware(middleware)
        return self

    # ══════════════════════════════════════════════════════════════════
    #                    DAGSTER-STYLE CLI COMMANDS
    # ══════════════════════════════════════════════════════════════════

    def check(self, chain_name: str | None = None) -> dict[str, Any]:
        """
        Validate definitions (like 'dg check defs').

        Checks:
        - All steps exist
        - Dependencies are resolvable
        - No circular dependencies
        - Chains are valid

        Usage:
            fg.check()                    # Check all
            fg.check("meeting_prep")      # Check specific chain
        """
        errors = []
        warnings = []
        chain_results = []

        chains_to_check = [chain_name] if chain_name else self.list_chains()

        if not chains_to_check:
            print("⚠ No chains registered")
            return {"valid": True, "chains": [], "errors": [], "warnings": ["No chains registered"]}

        print(f"\n{'═' * 60}")
        print(f"  FlowForge Check: {self.name} v{self.version}")
        print(f"{'═' * 60}\n")

        for cname in chains_to_check:
            result = self._check_chain(cname)
            chain_results.append(result)

            status = "✓" if result["valid"] else "✗"
            print(f"  {status} {cname}")

            # Show execution levels
            for level_idx, level in enumerate(result.get("levels", [])):
                is_parallel = len(level) > 1
                indent = "    "

                if is_parallel:
                    print(f"{indent}├─ [parallel]")
                    for step in level:
                        deps_str = f" ← {step['deps']}" if step.get("deps") else ""
                        prod_str = f" → {step['produces']}" if step.get("produces") else ""
                        print(f"{indent}│  • {step['name']}{deps_str}{prod_str}")
                else:
                    step = level[0]
                    deps_str = f" ← {step['deps']}" if step.get("deps") else ""
                    prod_str = f" → {step['produces']}" if step.get("produces") else ""
                    prefix = "├─" if level_idx < len(result.get("levels", [])) - 1 else "└─"
                    print(f"{indent}{prefix} {step['name']}{deps_str}{prod_str}")

            if result.get("errors"):
                errors.extend(result["errors"])
                for err in result["errors"]:
                    print(f"    ✗ {err}")

            print()

        valid = len(errors) == 0
        print(f"{'═' * 60}")
        print(f"  Result: {'✓ All checks passed' if valid else '✗ Errors found'}")
        print(
            f"  Agents: {len(self.list_agents())} | Steps: {len(self.list_steps())} | Chains: {len(self.list_chains())}"
        )
        print(f"{'═' * 60}\n")

        return {
            "valid": valid,
            "chains": chain_results,
            "errors": errors,
            "warnings": warnings,
        }

    def _check_chain(self, chain_name: str) -> dict[str, Any]:
        """Validate a single chain"""
        chain_spec = self._chain_registry.get_spec(chain_name)
        if not chain_spec:
            return {
                "name": chain_name,
                "valid": False,
                "errors": [f"Chain not found: {chain_name}"],
            }

        result = {"name": chain_name, "valid": True, "errors": [], "levels": []}

        # Build execution levels
        remaining = list(chain_spec.steps)
        placed = set()

        while remaining:
            level = []
            for step_name in remaining[:]:
                step_spec = self._step_registry.get_spec(step_name)
                if not step_spec:
                    result["errors"].append(f"Step not found: {step_name}")
                    remaining.remove(step_name)
                    continue

                deps = set(step_spec.dependencies) if step_spec.dependencies else set()

                # Check for missing dependencies
                missing = deps - placed - set(chain_spec.steps)
                if missing:
                    result["errors"].append(f"{step_name} requires missing: {missing}")

                if deps.issubset(placed) or not deps:
                    level.append(
                        {
                            "name": step_name,
                            "deps": list(deps) if deps else None,
                            "produces": step_spec.produces if step_spec.produces else None,
                        }
                    )
                    remaining.remove(step_name)

            if level:
                result["levels"].append(level)
                placed.update(s["name"] for s in level)
            elif remaining:
                for s in remaining:
                    result["errors"].append(f"Cannot resolve: {s} (circular dependency?)")
                break

        if result["errors"]:
            result["valid"] = False

        return result

    def list_defs(self) -> dict[str, list[str]]:
        """
        List all definitions (like 'dg list defs').

        Usage:
            fg.list_defs()
        """
        agents = self.list_agents()
        steps = self.list_steps()
        chains = self.list_chains()

        print(f"\n{'═' * 50}")
        print("  FlowForge Definitions")
        print(f"{'═' * 50}\n")

        if agents:
            print("  Agents:")
            for a in agents:
                print(f"    • {a}")
            print()

        if steps:
            print("  Steps:")
            for s in steps:
                spec = self._step_registry.get_spec(s)
                deps = f" ← {spec.dependencies}" if spec and spec.dependencies else ""
                print(f"    • {s}{deps}")
            print()

        if chains:
            print("  Chains:")
            for c in chains:
                spec = self._chain_registry.get_spec(c)
                step_count = len(spec.steps) if spec else 0
                print(f"    • {c} ({step_count} steps)")
            print()

        if self._resources:
            print("  Resources:")
            for r in self._resources:
                print(f"    • {r}")
            print()

        print(f"{'═' * 50}\n")

        return {"agents": agents, "steps": steps, "chains": chains}

    def graph(self, chain_name: str, format: str = "ascii") -> str:
        """
        Generate DAG visualization.

        Args:
            chain_name: Chain to visualize
            format: "ascii" or "mermaid"

        Usage:
            fg.graph("meeting_prep")              # ASCII
            fg.graph("meeting_prep", "mermaid")   # Mermaid.js
        """
        from flowforge.core.visualize import DAGVisualizer

        viz = DAGVisualizer()

        if format == "mermaid":
            output = viz.to_mermaid(chain_name)
        else:
            output = viz.to_ascii(chain_name)

        print(output)
        return output

    # ══════════════════════════════════════════════════════════════════
    #                         EXECUTION
    # ══════════════════════════════════════════════════════════════════

    async def launch(
        self,
        chain_name: str,
        data: dict[str, Any] | None = None,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Execute a chain (like 'dg launch').

        Usage:
            result = await fg.launch("meeting_prep", {"company": "Apple"})
        """
        return await self._runner.run(
            chain_name=chain_name,
            initial_data=data,
            request_id=request_id,
        )

    def launch_sync(
        self,
        chain_name: str,
        data: dict[str, Any] | None = None,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        """Synchronous wrapper for launch()"""
        return asyncio.run(self.launch(chain_name, data, request_id))

    # Aliases for backward compatibility
    async def run(
        self, chain_name: str, initial_data: dict[str, Any] | None = None, **kwargs
    ) -> dict[str, Any]:
        """Alias for launch() - backward compatibility"""
        return await self.launch(chain_name, initial_data, **kwargs)

    def run_sync(
        self, chain_name: str, initial_data: dict[str, Any] | None = None, **kwargs
    ) -> dict[str, Any]:
        """Alias for launch_sync() - backward compatibility"""
        return self.launch_sync(chain_name, initial_data, **kwargs)

    # ══════════════════════════════════════════════════════════════════
    #                         DISCOVERY
    # ══════════════════════════════════════════════════════════════════

    def list_agents(self) -> list[str]:
        """List all registered agents"""
        return self._agent_registry.list()

    def list_steps(self) -> list[str]:
        """List all registered steps"""
        return self._step_registry.list()

    def list_chains(self) -> list[str]:
        """List all registered chains"""
        return self._chain_registry.list()

    def get_agent(self, name: str, **kwargs) -> Any:
        """Get an agent instance"""
        return self._agent_registry.get_agent(name, **kwargs)

    def get_resource(self, name: str) -> Any:
        """Get a registered resource"""
        return self._resources.get(name)

    # ══════════════════════════════════════════════════════════════════
    #                         CONTEXT
    # ══════════════════════════════════════════════════════════════════

    def create_context(
        self,
        request_id: str,
        data: dict[str, Any] | None = None,
    ) -> ChainContext:
        """Create a new chain context"""
        return self._context_manager.create_context(request_id, data)

    def get_context(self, request_id: str) -> ChainContext | None:
        """Get an existing context"""
        return self._context_manager.get_context(request_id)

    # ══════════════════════════════════════════════════════════════════
    #                         UTILITIES
    # ══════════════════════════════════════════════════════════════════

    def clear(self) -> None:
        """Clear all registrations"""
        self._agent_registry.clear()
        self._step_registry.clear()
        self._chain_registry.clear()
        self._resources.clear()

    # Legacy alias
    def clear_registrations(self) -> None:
        """Alias for clear() - backward compatibility"""
        self.clear()

    # Legacy method - kept for backward compatibility
    def validate(
        self,
        chain_name: str | None = None,
        output: str = "ascii",
        print_output: bool = True,
    ) -> dict[str, Any]:
        """
        Legacy validate method - use check() instead.

        Kept for backward compatibility.
        """
        if output == "mermaid":
            if chain_name:
                self.graph(chain_name, "mermaid")
        return self.check(chain_name)

    def __repr__(self) -> str:
        return (
            f"FlowForge(name={self.name!r}, "
            f"agents={len(self.list_agents())}, "
            f"steps={len(self.list_steps())}, "
            f"chains={len(self.list_chains())})"
        )


# ══════════════════════════════════════════════════════════════════════════════
#                           MODULE-LEVEL API
# ══════════════════════════════════════════════════════════════════════════════

_default_forge: FlowForge | None = None


def get_forge() -> FlowForge:
    """Get or create the default FlowForge instance"""
    global _default_forge
    if _default_forge is None:
        _default_forge = FlowForge()
    return _default_forge


def set_forge(forge: FlowForge) -> None:
    """Set the default FlowForge instance"""
    global _default_forge
    _default_forge = forge


# Convenience type alias
Context = ChainContext
