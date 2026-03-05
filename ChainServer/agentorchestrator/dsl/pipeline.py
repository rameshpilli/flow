from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional


@dataclass
class StepDef:
    name: str
    fn: Callable
    deps: list[str] = field(default_factory=list)
    timeout_ms: int | None = None
    cache_ttl: int | None = None
    description: str = ""
    max_concurrency: int | None = None


@dataclass
class EventDef:
    on: str
    handler: Callable


class Pipeline:
    """
    Minimal declarative pipeline builder (preview).

    Why:
    - Define pipelines without sprinkling decorators across files.
    - Keep wiring in one place; easy to diff/templatize.
    - Pairs with the event bus so you can register event handlers alongside steps.

    Quick use:
        pipe = (
          Pipeline("research_report")
            .step("expand", fn=expand_query)
            .step("search", fn=search_web, deps=["expand"])
            .on("ToolCallResult", log_tool)
        )
        pipe.register(ao)  # registers steps + chain + handlers
    """

    def __init__(self, name: str):
        self.name = name
        self._steps: list[StepDef] = []
        self._events: list[EventDef] = []

    def step(
        self,
        name: str,
        fn: Callable,
        *,
        deps: Optional[list[str]] = None,
        timeout_ms: int | None = None,
        cache_ttl: int | None = None,
        description: str = "",
        max_concurrency: int | None = None,
    ) -> "Pipeline":
        """
        Add a step definition.

        Args:
            name: Step name (registered in ao).
            fn: Callable(ctx) -> dict | Any.
            deps: Names of steps that must complete first.
            timeout_ms: Optional per-step timeout override.
            cache_ttl: Reserved for future caching support.
            description: Human-friendly description.
            max_concurrency: Optional per-step concurrency cap.
        """
        self._steps.append(
            StepDef(
                name=name,
                fn=fn,
                deps=deps or [],
                timeout_ms=timeout_ms,
                cache_ttl=cache_ttl,
                description=description,
                max_concurrency=max_concurrency,
            )
        )
        return self

    def on(self, event_type: str, handler: Callable) -> "Pipeline":
        """Register an event handler to be bound when `register` is called."""
        self._events.append(EventDef(on=event_type, handler=handler))
        return self

    def register(self, ao) -> None:
        """Register steps, chain, and event handlers on an AgentOrchestrator."""
        # Register steps
        for s in self._steps:
            ao.step(
                name=s.name,
                deps=s.deps,
                timeout_ms=s.timeout_ms or 30000,
                max_concurrency=s.max_concurrency,
                description=s.description,
            )(s.fn)

        # Register chain with declared step order
        class _Chain:
            steps = [s.name for s in self._steps]

        ao.chain(name=self.name)(_Chain)

        # Register event handlers
        for ev in self._events:
            ao.event_handler(ev.on)(ev.handler)

    def to_dict(self) -> dict[str, Any]:
        """Export the pipeline definition (for future YAML/JSON serialization)."""
        return {
            "name": self.name,
            "steps": [
                {
                    "name": s.name,
                    "deps": s.deps,
                    "timeout_ms": s.timeout_ms,
                    "cache_ttl": s.cache_ttl,
                    "description": s.description,
                    "max_concurrency": s.max_concurrency,
                }
                for s in self._steps
            ],
            "events": [{"on": e.on, "handler": getattr(e.handler, "__name__", "<fn>")} for e in self._events],
        }
