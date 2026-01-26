"""
Lightweight event bus with in-memory default and optional Redis backend.

Use this to enable event-driven execution (loops/branches/streams). The factory
prefers Redis when available/configured, otherwise falls back to in-memory—
so it works out-of-the-box locally and scales to multi-process with Redis.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Iterable, Optional, Sequence

logger = logging.getLogger(__name__)


# =============================================================================
# Event model
# =============================================================================


@dataclass
class Event:
    """Typed event envelope for orchestration."""

    type: str
    payload: Any = field(default_factory=dict)
    step: str | None = None
    run_id: str | None = None
    timestamp: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(
            {
                "type": self.type,
                "payload": self.payload,
                "step": self.step,
                "run_id": self.run_id,
                "timestamp": self.timestamp.isoformat(),
                "metadata": self.metadata,
            }
        )

    @classmethod
    def from_json(cls, raw: str) -> "Event":
        data = json.loads(raw)
        ts = data.get("timestamp")
        return cls(
            type=data["type"],
            payload=data.get("payload"),
            step=data.get("step"),
            run_id=data.get("run_id"),
            timestamp=datetime.fromisoformat(ts) if ts else datetime.now(timezone.utc),
            metadata=data.get("metadata", {}),
        )


# =============================================================================
# Base interface
# =============================================================================


class EventBus:
    """Async event bus interface."""

    async def publish(self, event: Event) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    async def subscribe(
        self, event_types: Optional[Sequence[str]] = None
    ) -> AsyncIterator[Event]:  # pragma: no cover - interface
        raise NotImplementedError

    async def close(self) -> None:  # pragma: no cover - interface
        raise NotImplementedError


# =============================================================================
# In-memory implementation (default)
# =============================================================================


class InMemoryEventBus(EventBus):
    """Process-local pub/sub using asyncio queues."""

    def __init__(self, max_queue_size: int = 1000):
        self._subscribers: list[tuple[asyncio.Queue[Event], set[str] | None]] = []
        self._max_queue_size = max_queue_size
        self._lock = asyncio.Lock()

    async def publish(self, event: Event) -> None:
        async with self._lock:
            targets = list(self._subscribers)
        delivered = 0
        for queue, filters in targets:
            if filters is None or event.type in filters:
                try:
                    queue.put_nowait(event)
                    delivered += 1
                except asyncio.QueueFull:
                    logger.warning("Event queue full; dropping event %s", event.type)
        logger.debug("Event published type=%s delivered=%s", event.type, delivered)

    async def subscribe(
        self, event_types: Optional[Sequence[str]] = None
    ) -> AsyncIterator[Event]:
        filters = set(event_types) if event_types else None
        queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=self._max_queue_size)
        async with self._lock:
            self._subscribers.append((queue, filters))

        try:
            while True:
                event = await queue.get()
                yield event
        finally:
            async with self._lock:
                self._subscribers = [
                    (q, f) for (q, f) in self._subscribers if q is not queue
                ]

    async def close(self) -> None:
        async with self._lock:
            self._subscribers.clear()


# =============================================================================
# Redis implementation (optional)
# =============================================================================


class RedisEventBus(EventBus):
    """Redis pub/sub backed event bus."""

    def __init__(self, redis_service: Any, channel: str = "ao:events"):
        self.redis_service = redis_service
        self.channel = channel
        self._pubsub = None

    async def _ensure_pubsub(self):
        if self._pubsub is None:
            await self.redis_service.ensure_connected()
            client = self.redis_service.client()
            self._pubsub = client.pubsub()
            await self._pubsub.subscribe(self.channel)

    async def publish(self, event: Event) -> None:
        """
        Publish an event to Redis pub/sub.
        
        Failure handling:
        - Connection errors are logged and event is dropped (best-effort)
        - For critical events, consider using a persistent queue instead
        
        Note: Redis pub/sub is fire-and-forget. If no subscribers are 
        listening, the message is lost. For guaranteed delivery, use
        Redis Streams or a message queue like RabbitMQ/Kafka.
        """
        try:
            await self.redis_service.ensure_connected()
            await self.redis_service.client().publish(self.channel, event.to_json())
        except Exception as e:
            # Log at error level for visibility in monitoring
            # Include event type for debugging which events are being lost
            logger.error(
                "RedisEventBus publish failed for event type=%s run_id=%s: %s. "
                "Event will be dropped. Consider using persistent messaging for critical events.",
                event.type,
                event.run_id,
                e,
            )

    async def subscribe(
        self, event_types: Optional[Sequence[str]] = None
    ) -> AsyncIterator[Event]:
        filters = set(event_types) if event_types else None
        await self._ensure_pubsub()
        pubsub = self._pubsub

        async for message in pubsub.listen():
            if message is None:
                continue
            if message["type"] != "message":
                continue
            try:
                raw = message["data"]
                if isinstance(raw, (bytes, bytearray)):
                    raw = raw.decode("utf-8")
                event = Event.from_json(raw)
            except Exception:
                continue
            if filters is None or event.type in filters:
                yield event

    async def close(self) -> None:
        if self._pubsub:
            try:
                await self._pubsub.unsubscribe(self.channel)
                await self._pubsub.close()
            except Exception:
                pass
            self._pubsub = None


# =============================================================================
# Factory
# =============================================================================


def get_event_bus(
    prefer_redis: bool = True,
    channel: str = "ao:events",
    redis_service: Any | None = None,
) -> EventBus:
    """
    Return an EventBus instance.

    - If prefer_redis is True and Redis is available/configured, returns RedisEventBus.
    - Otherwise returns an InMemoryEventBus.
    """
    if prefer_redis:
        try:
            if redis_service is None:
                from agentorchestrator.services.redis import (
                    get_redis_client,
                    REDIS_AVAILABLE,
                )

                if REDIS_AVAILABLE:
                    redis_service = get_redis_client()
            if redis_service is not None:
                return RedisEventBus(redis_service, channel=channel)
        except Exception as e:
            logger.info("Redis event bus unavailable, falling back to memory: %s", e)

    return InMemoryEventBus()


__all__ = [
    "Event",
    "EventBus",
    "InMemoryEventBus",
    "RedisEventBus",
    "get_event_bus",
    # Standard event types
    "EventTypes",
    "emit_agent_event",
    "emit_tool_event",
]


class EventTypes:
    """
    Standard event type constants for AgentOrchestrator.
    
    Use these for consistent event naming across the framework.
    
    Step Events (emitted by DAGExecutor):
        - StepStarted: Step execution began
        - StepCompleted: Step finished successfully
        - StepFailed: Step failed with error
    
    Agent Events (emit from your agent code):
        - AgentStarted: Agent began processing
        - AgentCompleted: Agent finished successfully
        - AgentFailed: Agent failed with error
        - AgentHandoff: Agent handed off to another agent
    
    Tool Events (emit from tool execution):
        - ToolStarted: Tool execution began
        - ToolCompleted: Tool finished with result
        - ToolFailed: Tool failed with error
    
    Workflow Events:
        - ChainStarted: Chain execution began
        - ChainCompleted: Chain finished successfully
        - ChainFailed: Chain failed
    
    Example:
        >>> from agentorchestrator.core.event_bus import EventTypes, emit_agent_event
        >>>
        >>> # In your agent code
        >>> await emit_agent_event(
        ...     bus, EventTypes.AGENT_STARTED,
        ...     agent_name="researcher",
        ...     run_id=ctx.request_id,
        ... )
    """
    # Step events (emitted by framework)
    STEP_STARTED = "StepStarted"
    STEP_COMPLETED = "StepCompleted"
    STEP_FAILED = "StepFailed"
    
    # Agent events
    AGENT_STARTED = "AgentStarted"
    AGENT_COMPLETED = "AgentCompleted"
    AGENT_FAILED = "AgentFailed"
    AGENT_HANDOFF = "AgentHandoff"
    AGENT_THINKING = "AgentThinking"  # For streaming thought process
    
    # Tool events
    TOOL_STARTED = "ToolStarted"
    TOOL_COMPLETED = "ToolCompleted"
    TOOL_FAILED = "ToolFailed"
    
    # Chain/workflow events
    CHAIN_STARTED = "ChainStarted"
    CHAIN_COMPLETED = "ChainCompleted"
    CHAIN_FAILED = "ChainFailed"
    
    # Dynamic workflow events
    DYNAMIC_STEP_INJECTED = "DynamicStepInjected"
    DAG_REBUILT = "DAGRebuilt"


async def emit_agent_event(
    bus: EventBus,
    event_type: str,
    agent_name: str,
    run_id: str | None = None,
    payload: dict | None = None,
    **metadata,
) -> None:
    """
    Emit an agent lifecycle event.
    
    Use this helper to emit standardized agent events from your agent code.
    
    Args:
        bus: The EventBus instance to publish to.
        event_type: One of EventTypes.AGENT_* constants.
        agent_name: Name of the agent emitting the event.
        run_id: Run identifier for event correlation.
        payload: Optional event payload data.
        **metadata: Additional metadata fields.
    
    Example:
        >>> bus = get_event_bus()
        >>>
        >>> # When agent starts
        >>> await emit_agent_event(
        ...     bus, EventTypes.AGENT_STARTED,
        ...     agent_name="researcher",
        ...     run_id=ctx.request_id,
        ...     payload={"input": query},
        ... )
        >>>
        >>> # When agent completes
        >>> await emit_agent_event(
        ...     bus, EventTypes.AGENT_COMPLETED,
        ...     agent_name="researcher",
        ...     run_id=ctx.request_id,
        ...     payload={"result": result},
        ...     tokens_used=150,
        ... )
    """
    event = Event(
        type=event_type,
        payload={
            "agent_name": agent_name,
            **(payload or {}),
        },
        run_id=run_id,
        metadata={"agent": agent_name, **metadata},
    )
    await bus.publish(event)


async def emit_tool_event(
    bus: EventBus,
    event_type: str,
    tool_name: str,
    run_id: str | None = None,
    agent_name: str | None = None,
    payload: dict | None = None,
    **metadata,
) -> None:
    """
    Emit a tool execution event.
    
    Use this helper to emit standardized tool events during tool execution.
    
    Args:
        bus: The EventBus instance to publish to.
        event_type: One of EventTypes.TOOL_* constants.
        tool_name: Name of the tool being executed.
        run_id: Run identifier for event correlation.
        agent_name: Optional name of agent invoking the tool.
        payload: Optional event payload data.
        **metadata: Additional metadata fields.
    
    Example:
        >>> bus = get_event_bus()
        >>>
        >>> # When tool starts
        >>> await emit_tool_event(
        ...     bus, EventTypes.TOOL_STARTED,
        ...     tool_name="search",
        ...     agent_name="researcher",
        ...     run_id=ctx.request_id,
        ...     payload={"args": {"query": "AI trends"}},
        ... )
        >>>
        >>> # When tool completes
        >>> await emit_tool_event(
        ...     bus, EventTypes.TOOL_COMPLETED,
        ...     tool_name="search",
        ...     run_id=ctx.request_id,
        ...     payload={"result": search_results},
        ...     duration_ms=150.5,
        ... )
    """
    event = Event(
        type=event_type,
        payload={
            "tool_name": tool_name,
            **({"agent_name": agent_name} if agent_name else {}),
            **(payload or {}),
        },
        run_id=run_id,
        metadata={"tool": tool_name, **metadata},
    )
    await bus.publish(event)
