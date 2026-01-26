# Event-Driven Workflows (Preview)

Goal: enable loops, conditionals, and streaming telemetry without being locked to a static DAG. Events flow through a bus (Redis if available, otherwise in-memory).

## Quickstart

```python
from agentorchestrator import AgentOrchestrator, Event, ChainContext

ao = AgentOrchestrator()

@ao.event_handler("ResearchTask")
async def worker(ctx: ChainContext, event: Event) -> Event:
    # pretend work
    finding = f"finding for {event.payload['query']}"
    return Event(type="Finding", payload={"text": finding})

result = await ao.run_event_loop(
    seed_events=[Event(type="ResearchTask", payload={"query": "AAPL 10-K"})],
    max_events=10,
    timeout_s=5,
    stop_when=lambda evt, ctx: evt.type == "Finding",
)

# result => {run_id, processed, handlers, duration_ms}
```

## Declarative + events (preview)

```python
from agentorchestrator import AgentOrchestrator, Pipeline, Event, ChainContext

ao = AgentOrchestrator()

pipe = (
  Pipeline("research_pipe")
    .step("expand", fn=lambda ctx: {"queries": ["AAPL 10-K", "risks"]})
)
pipe.register(ao)  # registers steps + chain

@ao.event_handler("Finding")
async def on_finding(ctx: ChainContext, event: Event) -> None:
    print("finding:", event.payload)
```

## Streaming telemetry (agents)
- Step events: `StepStarted`, `StepCompleted`, `StepFailed`, `StepSkipped`
- Agent streaming: `AgentTokenChunk`, `AgentStreamCompleted`
- Tool calls: `ToolCallStarted`, `ToolCallResult`

These are emitted to the same event bus; subscribe to `ao:events` (Redis) or in-process for live dashboards.

## Redis vs In-memory
- `get_event_bus(prefer_redis=True)` uses Redis if the redis package/env is configured; otherwise it falls back to in-memory.
- Works out of the box for local dev; production can switch to Redis without code changes.
- Install with Redis support: `pip install -e ".[workflows]"` (adds redis client).

## Patterns to build next
- Dynamic fan-out/fan-in research loops
- Condition-based stopping (first high-confidence result, majority vote)
- Tool-call traces to power live debugging UI
- See example: `agentorchestrator/examples/event_workflow.py`

> Status: preview. APIs may evolve; contributions welcome.
