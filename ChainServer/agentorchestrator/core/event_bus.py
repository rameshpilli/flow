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
        try:
            await self.redis_service.ensure_connected()
            await self.redis_service.client().publish(self.channel, event.to_json())
        except Exception as e:
            logger.warning("RedisEventBus publish failed, dropping event: %s", e)

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
]
