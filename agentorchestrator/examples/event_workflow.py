"""
Minimal event-driven workflow example.

Run:
    # optional: use redis-backed bus if redis is installed/configured
    # pip install -e ".[workflows]"
    # otherwise falls back to in-memory

    python -m agentorchestrator.examples.event_workflow
"""

import asyncio
from agentorchestrator import AgentOrchestrator, Event, ChainContext


def build_workflow():
    ao = AgentOrchestrator(name="event_demo")

    # Emit work items from a DAG step (optional)
    @ao.step(name="seed_tasks")
    async def seed_tasks(ctx: ChainContext) -> dict:
        await ao.emit_event(Event(type="ResearchTask", payload={"query": "AAPL 10-K"}))
        await ao.emit_event(Event(type="ResearchTask", payload={"query": "Risks section"}))
        return {"seeded": True}

    @ao.chain(name="seed_chain")
    class SeedChain:
        steps = ["seed_tasks"]

    # Event handler that acts on ResearchTask events
    @ao.event_handler("ResearchTask")
    async def worker(ctx: ChainContext, event: Event) -> Event:
        query = event.payload["query"]
        finding = f"finding for {query}"
        return Event(type="Finding", payload={"query": query, "text": finding})

    # Event handler that stops after first two findings
    findings: list[dict] = []

    @ao.event_handler("Finding")
    async def collector(ctx: ChainContext, event: Event) -> None:
        findings.append(event.payload)
        # emit nothing; stop_when will terminate
        return None

    return ao, findings


async def main():
    ao, findings = build_workflow()

    # Kick off DAG to emit seed events
    await ao.run("seed_chain")

    # Process events until we collect 2 findings or timeout
    result = await ao.run_event_loop(
        max_events=20,
        timeout_s=5.0,
        stop_when=lambda evt, ctx: evt.type == "Finding" and len(findings) >= 2,
        min_events=1,
    )

    print("run summary:", result)
    print("findings:", findings)


if __name__ == "__main__":
    asyncio.run(main())
