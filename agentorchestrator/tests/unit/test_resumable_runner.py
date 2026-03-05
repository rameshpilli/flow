import uuid

import pytest

from agentorchestrator import AgentOrchestrator


@pytest.mark.asyncio
async def test_resume_skips_completed_steps():
    ao = AgentOrchestrator.temp_registries("resumable_resume")

    step1_calls = 0
    step2_calls = 0
    should_fail = True

    @ao.step(name="step1")
    async def step1(ctx):
        nonlocal step1_calls
        step1_calls += 1
        ctx.set("step1_output", {"value": step1_calls})
        return {"value": step1_calls}

    @ao.step(name="step2", deps=["step1"])
    async def step2(ctx):
        nonlocal step2_calls, should_fail
        step2_calls += 1
        if should_fail:
            should_fail = False
            raise RuntimeError("boom")
        return {"done": True, "value": ctx.get("step1_output")["value"]}

    @ao.chain(name="test_chain")
    class TestChain:
        steps = ["step1", "step2"]

    run_id = f"run_{uuid.uuid4().hex[:8]}"

    with pytest.raises(RuntimeError):
        await ao.launch_resumable("test_chain", run_id=run_id)

    assert step1_calls == 1
    assert step2_calls == 1

    resume_result = await ao.resume(run_id)
    assert resume_result["success"] is True
    assert step1_calls == 1  # step1 should not re-run
    assert step2_calls == 2


@pytest.mark.asyncio
async def test_retry_failed_runs_only_failed_steps():
    ao = AgentOrchestrator.temp_registries("resumable_retry")

    step1_calls = 0
    step2_calls = 0
    should_fail = True

    @ao.step(name="step1")
    async def step1(ctx):
        nonlocal step1_calls
        step1_calls += 1
        ctx.set("step1_output", {"value": step1_calls})
        return {"value": step1_calls}

    @ao.step(name="step2", deps=["step1"])
    async def step2(ctx):
        nonlocal step2_calls, should_fail
        step2_calls += 1
        if should_fail:
            should_fail = False
            raise RuntimeError("boom")
        return {"done": True, "value": ctx.get("step1_output")["value"]}

    @ao.chain(name="test_chain")
    class TestChain:
        steps = ["step1", "step2"]

    run_id = f"run_{uuid.uuid4().hex[:8]}"

    with pytest.raises(RuntimeError):
        await ao.launch_resumable("test_chain", run_id=run_id)

    assert step1_calls == 1
    assert step2_calls == 1

    retry_result = await ao.retry_failed(run_id)
    assert retry_result["success"] is True
    assert step1_calls == 1  # step1 should not re-run
    assert step2_calls == 2
