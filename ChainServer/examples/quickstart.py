"""
FlowForge Quickstart Guide

The simplest way to get started with FlowForge.
This demonstrates the minimal code needed to create and run a chain.
"""

import asyncio

from flowforge import ChainContext, FlowForge

# 1. Create FlowForge instance
forge = FlowForge(name="quickstart")


# 2. Define steps using decorators
@forge.step(name="step_a", produces=["data_a"])
async def step_a(ctx: ChainContext):
    """First step - fetch some data"""
    ctx.set("data_a", {"message": "Hello from step A"})
    return {"data_a": ctx.get("data_a")}


@forge.step(name="step_b", dependencies=["step_a"], produces=["data_b"])
async def step_b(ctx: ChainContext):
    """Second step - depends on step A"""
    data_a = ctx.get("data_a", {})
    ctx.set("data_b", {"message": f"Step B received: {data_a.get('message')}"})
    return {"data_b": ctx.get("data_b")}


@forge.step(name="step_c", dependencies=["step_b"], produces=["result"])
async def step_c(ctx: ChainContext):
    """Third step - produces final result"""
    data_b = ctx.get("data_b", {})
    result = {"final": f"Complete! {data_b.get('message')}"}
    ctx.set("result", result)
    return {"result": result}


# 3. Define a chain
@forge.chain(name="my_chain")
class MyChain:
    steps = ["step_a", "step_b", "step_c"]


# 4. Run it!
async def main():
    result = await forge.run("my_chain")

    print(f"Success: {result['success']}")
    print(f"Duration: {result['duration_ms']:.2f}ms")

    for step in result["results"]:
        print(f"  {step['step']}: {step['output']}")


if __name__ == "__main__":
    asyncio.run(main())
