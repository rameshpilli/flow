import asyncio

import pytest

from agentorchestrator import AgentOrchestrator
from agentorchestrator.core.event_bus import Event, InMemoryEventBus
from agentorchestrator.core.context import ChainContext


@pytest.mark.asyncio
async def test_step_events_published():
    bus = InMemoryEventBus()
    ao = AgentOrchestrator(name="events_test", isolated=True, event_bus=bus)

    @ao.step(name="s1")
    async def s1(ctx: ChainContext):
        return {"x": 1}

    @ao.step(name="s2", deps=["s1"])
    async def s2(ctx: ChainContext):
        return {"y": ctx.get("x", default=None)}

    @ao.chain(name="c")
    class C:
        steps = ["s1", "s2"]

    events: list = []

    async def collect():
        async for evt in bus.subscribe(["StepStarted", "StepCompleted"]):
            events.append(evt)
            if len(events) >= 4:  # 2 steps x (started+completed)
                break

    collector = asyncio.create_task(collect())
    await ao.run("c")
    await asyncio.wait_for(collector, timeout=2.0)

    types = [e.type for e in events]
    assert "StepStarted" in types
    assert "StepCompleted" in types
    # Ensure ordering starts with start and ends with completed
    assert types[0] == "StepStarted"
    assert types[-1] == "StepCompleted"


@pytest.mark.asyncio
async def test_event_loop_with_handlers():
    bus = InMemoryEventBus()
    ao = AgentOrchestrator(name="evt_loop_test", isolated=True, event_bus=bus)

    @ao.event_handler("Ping")
    async def handle_ping(ctx: ChainContext, event: Event):
        return Event(type="Pong", payload={"n": event.payload.get("n", 0) + 1})

    result = await ao.run_event_loop(
        seed_events=[Event(type="Ping", payload={"n": 0})],
        max_events=10,
        timeout_s=2.0,
        stop_when=lambda evt, ctx: evt.type == "Pong" and evt.payload.get("n") >= 2,
        min_events=1,
    )

    assert result["processed"] >= 2
    # Ensure the handler was registered
    assert result["handlers"]["Ping"] == 1
