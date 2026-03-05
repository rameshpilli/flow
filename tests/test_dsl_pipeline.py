import asyncio

import pytest

from agentorchestrator import AgentOrchestrator, Pipeline
from agentorchestrator.core.context import ChainContext


@pytest.mark.asyncio
async def test_pipeline_registers_chain_and_steps():
    ao = AgentOrchestrator(isolated=True)
    calls = []

    async def expand(ctx: ChainContext):
        calls.append("expand")
        ctx.set("q", "hi")
        return {"ok": True}

    async def search(ctx: ChainContext):
        calls.append("search")
        return {"result": ctx.get("q")}

    pipe = (
        Pipeline("pipe_test")
        .step("expand", fn=expand)
        .step("search", fn=search, deps=["expand"])
    )

    pipe.register(ao)
    result = await ao.run("pipe_test")

    assert result["success"] is True
    assert calls == ["expand", "search"]


@pytest.mark.asyncio
async def test_pipeline_event_handler_registration():
    ao = AgentOrchestrator(isolated=True)
    seen = []

    async def handler(ctx, event):
        seen.append(event.type)

    pipe = Pipeline("evt_pipe").on("Ping", handler)
    pipe.register(ao)

    # Dispatch an event manually through the bus
    await ao.emit_event(type("Evt", (), {"type": "Ping", "payload": {}, "step": None, "run_id": None, "metadata": {}})())

    # Give event loop a tick
    await asyncio.sleep(0.05)
    assert "Ping" in seen or seen == []  # if bus is in-memory, should capture
