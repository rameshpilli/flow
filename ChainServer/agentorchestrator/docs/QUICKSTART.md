# AgentOrchestrator Quickstart

Get up and running with AgentOrchestrator in 5 minutes.

## Installation

```bash
pip install -e ./agentorchestrator
```

## Hello World

```python
from agentorchestrator import AgentOrchestrator

# Create an orchestrator instance
ao = AgentOrchestrator(name="my_app")

# Define a step
@ao.step(name="greet")
async def greet(ctx):
    name = ctx.get("name", "World")
    return {"greeting": f"Hello, {name}!"}

# Define a chain
@ao.chain(name="hello_chain")
class HelloChain:
    steps = ["greet"]

# Run it
import asyncio

async def main():
    result = await ao.launch("hello_chain", {"name": "AgentOrchestrator"})
    print(result["greeting"])  # "Hello, AgentOrchestrator!"

asyncio.run(main())
```

## Multi-Step Pipeline

```python
from agentorchestrator import AgentOrchestrator

ao = AgentOrchestrator(name="pipeline")

@ao.step(name="fetch")
async def fetch(ctx):
    # Simulate fetching data
    ctx.set("data", [1, 2, 3, 4, 5])
    return {"fetched": True}

@ao.step(name="process", deps=["fetch"])  # Runs after fetch
async def process(ctx):
    data = ctx.get("data")
    result = [x * 2 for x in data]
    ctx.set("processed", result)
    return {"processed": result}

@ao.step(name="summarize", deps=["process"])
async def summarize(ctx):
    data = ctx.get("processed")
    return {"sum": sum(data), "count": len(data)}

@ao.chain(name="data_pipeline")
class DataPipeline:
    steps = ["fetch", "process", "summarize"]

# Run
async def main():
    result = await ao.launch("data_pipeline", {})
    print(f"Sum: {result['sum']}, Count: {result['count']}")

asyncio.run(main())
```

## Parallel Execution

Steps without dependencies run in parallel:

```python
@ao.step(name="fetch_a")
async def fetch_a(ctx):
    await asyncio.sleep(1)  # Simulates slow API
    return {"a": "data_a"}

@ao.step(name="fetch_b")
async def fetch_b(ctx):
    await asyncio.sleep(1)  # Simulates slow API
    return {"b": "data_b"}

@ao.step(name="combine", deps=["fetch_a", "fetch_b"])
async def combine(ctx):
    return {"combined": True}

@ao.chain(name="parallel_chain")
class ParallelChain:
    steps = ["fetch_a", "fetch_b", "combine"]

# fetch_a and fetch_b run in parallel (total ~1s, not 2s)
```

## Add Middleware

```python
from agentorchestrator import AgentOrchestrator
from agentorchestrator.middleware import LoggerMiddleware, CacheMiddleware

ao = AgentOrchestrator(name="my_app")

# Add logging
ao.use(LoggerMiddleware())

# Add caching (5 minute TTL)
ao.use(CacheMiddleware(ttl_seconds=300))
```

## LLM Gateway (Corporate Environments)

For corporate environments that require OAuth authentication:

```python
from agentorchestrator.services import LLMGatewayClient

# Option 1: Direct configuration
client = LLMGatewayClient(
    server_url="https://llm-gateway.corp.com/v1/chat/completions",
    oauth_endpoint="https://auth.corp.com/token",
    client_id="my-app",
    client_secret="secret",
)

# Option 2: From environment variables
# Set: LLM_SERVER_URL, LLM_OAUTH_ENDPOINT, LLM_CLIENT_ID, LLM_CLIENT_SECRET
client = LLMGatewayClient.from_env()

# Generate text
response = await client.generate_async("What is 2+2?")

# Structured output
from pydantic import BaseModel

class Answer(BaseModel):
    result: int

result = await client.generate_structured_async(
    "What is 2+2?",
    response_model=Answer,
)
print(result.result)  # 4
```

## Testing

```python
from agentorchestrator.testing import IsolatedOrchestrator

async def test_my_chain():
    async with IsolatedOrchestrator() as ao:
        @ao.step(name="test_step")
        async def test_step(ctx):
            return {"result": "ok"}

        @ao.chain(name="test_chain")
        class TestChain:
            steps = ["test_step"]

        result = await ao.launch("test_chain", {})
        assert result["success"]
```

## Optional RAG + Chat History

```python
from agentorchestrator import AgentOrchestrator
from agentorchestrator.services import VectorStoreService, VectorDocument
from agentorchestrator.squad.storage import InMemoryChatStorage

vs = VectorStoreService()
chat = InMemoryChatStorage()
await vs.upsert([VectorDocument(id="d1", text="Use async/await for I/O")])

ao = AgentOrchestrator(name="rag_demo")

@ao.step(name="retrieve")
async def retrieve(ctx):
    ctx.set("rag_context", await vs.query(ctx.get("query", "")))

@ao.step(name="answer", deps=["retrieve"])
async def answer(ctx):
    return {"answer": f"Using {len(ctx.get('rag_context', []))} snippets"}

@ao.chain(name="rag_chain")
class RAGChain:
    steps = ["retrieve", "answer"]
```

## Semantic Memory with Mem0

```python
from agentorchestrator.services import Mem0Memory

# Create memory (requires corporate MemoryStoreClient)
from your_app import MemoryStoreClient

client = MemoryStoreClient(
    base_url="https://mem0.corp.com",
    agent_id="my-agent"
)
memory = Mem0Memory(client=client)

# Store memories
await memory.add("User prefers technical explanations")

# Search memories
results = await memory.search("What are user's preferences?")
for mem in results:
    print(mem.content)
```

## Type-Safe State with Pydantic

Use Pydantic models for validated, type-safe state management:

```python
from pydantic import BaseModel, Field
from agentorchestrator import AgentOrchestrator, Context

class PipelineState(BaseModel):
    """Type-safe state for the pipeline."""
    counter: int = Field(default=0)
    items: list[str] = Field(default_factory=list)
    status: str = "pending"

ao = AgentOrchestrator(name="typed_app")

@ao.step(name="process", state_model=PipelineState)
async def process(ctx: Context[PipelineState]):
    # Type-safe with IDE autocomplete!
    async with ctx.edit_state() as state:
        state.counter += 1
        state.items.append("processed")
        state.status = "complete"
    
    return {"count": ctx.state.counter}

@ao.chain(name="typed_pipeline")
class TypedPipeline:
    steps = ["process"]
```

## Event-Driven Workflows

Build reactive workflows with the event bus:

```python
from agentorchestrator import AgentOrchestrator
from agentorchestrator.core.event_bus import Event

ao = AgentOrchestrator(name="event_app")

# Define event handlers
@ao.event_handler("TaskCreated")
async def handle_task(ctx, event: Event):
    task_id = event.payload.get("task_id")
    # Process the task...
    return Event(type="TaskCompleted", payload={"task_id": task_id})

@ao.event_handler("TaskCompleted")
async def handle_completion(ctx, event: Event):
    print(f"Task {event.payload['task_id']} completed!")

# Run the event loop
async def main():
    result = await ao.run_event_loop(
        seed_events=[
            Event(type="TaskCreated", payload={"task_id": "task-001"})
        ],
        stop_when=lambda e, ctx: e.type == "TaskCompleted",
        timeout_s=30.0,
    )
    print(f"Processed {result['processed']} events")

asyncio.run(main())
```

## ReAct Agent Pattern

Build reasoning agents with the ReAct (Reasoning + Acting) pattern:

```python
from agentorchestrator.agents.react import ReActAgent, Tool, ReActConfig
from agentorchestrator.services import LLMGatewayClient

# Define tools
def search(query: str) -> str:
    return f"Search results for: {query}"

def calculate(expression: str) -> str:
    return str(eval(expression))

# Create agent with tools
llm = LLMGatewayClient.from_env()
agent = ReActAgent(
    llm_client=llm,
    tools=[
        Tool("search", "Search the web for information", search),
        Tool("calculate", "Evaluate a math expression", calculate),
    ],
    config=ReActConfig(max_iterations=5),
)

# Run the agent
async def main():
    result = await agent.run("What is the population of France divided by 3?")
    print(f"Answer: {result.final_answer}")
    print(f"Reasoning trace:\n{result.thought_trace}")

asyncio.run(main())
```

## Agent Reflection (Self-Critique)

Improve output quality with agent reflection:

```python
from agentorchestrator.middleware import ReflectionMiddleware, ReflectionConfig

# Add reflection to improve outputs
reflection = ReflectionMiddleware(
    llm_client=llm,
    config=ReflectionConfig(
        quality_threshold=0.8,  # Require 80% quality score
        max_revisions=2,        # Allow up to 2 revisions
    ),
)
ao.use(reflection)

# Or apply to specific steps with the decorator
from agentorchestrator.middleware.reflection import reflect

@ao.step(name="generate_report")
@reflect(llm_client=llm, quality_threshold=0.85)
async def generate_report(ctx):
    # This output will be reflected upon and revised if needed
    return {"report": "..."}
```

## CLI

The CLI is available as `ao` (recommended) or `agentorchestrator` (full name):

```bash
# Run a chain
ao run my_chain --data '{"name": "Test"}'

# Run with checkpointing (for resume capability)
ao run my_chain --resumable --data '{"name": "Test"}'

# Dry run - see execution plan without running
ao run my_chain --dry-run --data '{"name": "Test"}'

# Validate definitions
ao check

# Comprehensive validation
ao validate my_chain

# List all registered components
ao list

# Visualize chain DAG
ao graph my_chain

# Development mode with hot reload
ao dev --watch

# Debug mode with context snapshots
ao debug my_chain --data '{"name": "Test"}'

# Health check
ao health --detailed

# Diagnose setup issues
ao doctor
```

See [CLI Reference](cli/index.md) for complete documentation.

## Next Steps

- See [API.md](API.md) for full API reference
- See [Understanding](understanding/) for core concepts
- See [Patterns](patterns/) for production patterns
- See [examples/](../examples/) for more complex examples
