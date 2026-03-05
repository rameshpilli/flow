import pytest

from agentorchestrator import AgentOrchestrator
from agentorchestrator.core.event_bus import Event, InMemoryEventBus
from agentorchestrator.core.run_store import InMemoryRunStore


@pytest.mark.asyncio
async def test_resume_event_loop_restores_context():
    ao = AgentOrchestrator.temp_registries("event_loop_resume")
    ao._event_bus = InMemoryEventBus()
    store = InMemoryRunStore()

    @ao.event_handler("Start")
    async def handle_start(ctx, event):
        ctx.set("value", 1)
        return None

    @ao.event_handler("Continue")
    async def handle_continue(ctx, event):
        ctx.set("value", (ctx.get("value") or 0) + 1)
        return None

    result1 = await ao.run_event_loop(
        seed_events=[Event(type="Start")],
        max_events=1,
        run_store=store,
        checkpoint_interval=1,
    )
    run_id = result1["run_id"]

    checkpoint1 = await store.load_checkpoint(run_id)
    assert checkpoint1 is not None
    data1 = checkpoint1.context_data.get("data", checkpoint1.context_data)
    assert data1.get("value") == 1

    await ao.resume_event_loop(
        run_id=run_id,
        run_store=store,
        seed_events=[Event(type="Continue")],
        max_events=1,
        checkpoint_interval=1,
    )

    checkpoint2 = await store.load_checkpoint(run_id)
    assert checkpoint2 is not None
    data2 = checkpoint2.context_data.get("data", checkpoint2.context_data)
    assert data2.get("value") == 2
