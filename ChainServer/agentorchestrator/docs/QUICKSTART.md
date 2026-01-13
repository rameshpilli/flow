# AgentOrchestrator Quickstart

Get up and running with AgentOrchestrator in 5 minutes.

## Installation

```bash
pip install -e ./agentorchestrator
```

## Hello World

```python
from agentorchestrator import AgentOrchestrator

# Create an AgentOrchestrator instance
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
from agentorchestrator import AgentOrchestrator, LoggerMiddleware, CacheMiddleware

ao = AgentOrchestrator(name="my_app")

# Add logging
ao.use(LoggerMiddleware())

# Add caching (5 minute TTL)
ao.use(CacheMiddleware(ttl_seconds=300))
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

## CLI

```bash
# Run a chain
agentorchestrator run my_chain --data '{"name": "Test"}'

# Validate definitions
agentorchestrator check

# List all registered components
agentorchestrator list

# Visualize chain DAG
agentorchestrator graph my_chain
```

## Agent Squad Integration (Multi-Agent Routing)

For intelligent multi-agent routing with supervisor patterns:

### Prerequisites

```bash
# Python 3.11+ required
python --version  # Must be 3.11, 3.12, or 3.13

# Optional: Install agent-squad for native AWS Labs features
pip install agent-squad[anthropic]   # For Anthropic Claude
pip install agent-squad[openai]      # For OpenAI
pip install agent-squad[aws]         # For AWS Bedrock
pip install agent-squad[all]         # For all providers
```

### Using LLM Gateway (Behind Proxy)

If you're behind a proxy, use `LLMGatewayClassifier` with your existing OAuth configuration - no direct API keys needed:

```python
from agentorchestrator.integrations import AgentSquadBridge, LLMGatewayClassifier
from agentorchestrator.services.llm_gateway import LLMGatewayClient
from cmpt.config import Config

# Create LLM Gateway client (uses your existing OAuth config)
llm_client = LLMGatewayClient(
    server_url=Config.LLM_SERVER_URL,
    oauth_endpoint=Config.LLM_OAUTH_ENDPOINT,
    client_id=Config.LLM_CLIENT_ID,
    client_secret=Config.LLM_CLIENT_SECRET,
    model_name=Config.LLM_MODEL_NAME,
)

# Use with Agent Squad bridge
bridge = AgentSquadBridge(classifier=LLMGatewayClassifier(llm_client))
bridge.add_ao_agent(sec_agent, description="SEC filing expert")
bridge.add_ao_agent(capiq_agent, description="Financial data analyst")

result = await bridge.route("What was Apple's revenue last quarter?")
```

### Using Direct API Keys (Optional)

If you have direct API access:

```bash
# Add to your .env file
ANTHROPIC_API_KEY=sk-ant-...   # For Anthropic Claude
OPENAI_API_KEY=sk-...          # For OpenAI
AWS_ACCESS_KEY_ID=...          # For AWS Bedrock
AWS_SECRET_ACCESS_KEY=...
AWS_DEFAULT_REGION=us-east-1
```

```python
from agentorchestrator.agents import (
    SupervisorAgent,
    SupervisorConfig,
    AgentSquadBridge,
    LLMClassifier,
)

# With direct LLM access
bridge = AgentSquadBridge(classifier=LLMClassifier(llm=my_langchain_llm))
bridge.add_ao_agent(sec_agent, description="SEC filing expert")
bridge.add_ao_agent(capiq_agent, description="Financial data analyst")

result = await bridge.route("What was Apple's revenue last quarter?")
```

### Supervisor Pattern

```python
from agentorchestrator.agents import SupervisorAgent, SupervisorConfig

# Create a supervisor with team agents
supervisor = SupervisorAgent(
    team=[sec_agent, capiq_agent, news_agent],
    config=SupervisorConfig(
        lead_model=Config.LLM_MODEL_NAME,  # Uses your LLM Gateway model
        parallel_execution=True,
    ),
    llm=llm_client,  # LLMGatewayClient works here too
)

# Lead agent dynamically decides which team members to invoke
result = await supervisor.fetch("What are Apple's key financial risks?")
```

### Pluggable Interfaces

Implement custom memory stores or classifiers:

```python
from agentorchestrator.agents import ConversationMemoryStore, AgentClassifier

# Custom Redis memory store
class RedisMemoryStore(ConversationMemoryStore):
    async def store(self, session_id, user_id, entry):
        await redis.rpush(f"conv:{session_id}:{user_id}", json.dumps(entry))

    async def retrieve(self, session_id, user_id, limit=10):
        return [json.loads(e) for e in await redis.lrange(...)]

# Use with bridge
bridge = AgentSquadBridge(memory_store=RedisMemoryStore())
```

## Next Steps

- See [API.md](API.md) for full API reference
- See [REQUIREMENTS.md](REQUIREMENTS.md) for production setup
- See [examples/](../examples/) for more complex examples