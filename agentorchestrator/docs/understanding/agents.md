# Agents

**Agents** are LLM-powered components that can reason, use tools, and maintain memory. They're the intelligence layer of your pipelines.

## What is an Agent?

An agent combines:

- **LLM** - The reasoning engine (GPT-4, Claude, etc.)
- **Tools** - Functions the agent can call
- **Memory** - Conversation and knowledge storage
- **Instructions** - System prompt defining behavior

```python
from agentorchestrator.agents import BaseAgent

class ResearchAgent(BaseAgent):
    name = "research_agent"
    model = "gpt-4"
    instructions = "You are a research assistant. Find and synthesize information."

    tools = [
        search_web,
        read_document,
        summarize_text,
    ]
```

## Creating Agents

### Using the Decorator

```python
from agentorchestrator import AgentOrchestrator

ao = AgentOrchestrator(name="my_app")

@ao.agent(name="analyst")
class AnalystAgent:
    model = "gpt-4"
    instructions = "Analyze data and provide insights."

    @ao.tool
    async def calculate_metrics(self, data: list[float]) -> dict:
        """Calculate statistical metrics on the data."""
        return {
            "mean": sum(data) / len(data),
            "max": max(data),
            "min": min(data),
        }
```

### Using BaseAgent

```python
from agentorchestrator.agents import BaseAgent

class WriterAgent(BaseAgent):
    name = "writer"
    model = "gpt-4"
    instructions = """
    You are a technical writer. Create clear, concise documentation.
    Always include code examples when relevant.
    """

    async def on_message(self, message: str, ctx) -> str:
        # Custom message handling
        response = await self.llm.generate(message)
        return response
```

## Agent Tools

Tools are functions agents can call to interact with the world:

```python
from agentorchestrator.agents import tool

@tool
async def search_database(query: str, limit: int = 10) -> list[dict]:
    """
    Search the database for matching records.

    Args:
        query: Search query string
        limit: Maximum results to return

    Returns:
        List of matching records
    """
    results = await db.search(query, limit=limit)
    return results

class DataAgent(BaseAgent):
    name = "data_agent"
    tools = [search_database]
```

### Tool Best Practices

!!! tip "Document Thoroughly"
    The docstring is what the LLM sees. Be specific about inputs, outputs, and behavior.

!!! tip "Handle Errors Gracefully"
    Return error messages the LLM can understand and recover from.

!!! tip "Keep Tools Focused"
    One tool, one action. Don't combine unrelated operations.

## Agent Memory

Agents can remember past interactions using storage services:

```python
from agentorchestrator.squad.storage import InMemoryChatStorage
from agentorchestrator.services import Mem0Memory

class MemoryAgent(BaseAgent):
    name = "assistant"

    def __init__(self, chat_storage=None, semantic_memory=None):
        super().__init__()
        self.chat_storage = chat_storage or InMemoryChatStorage()
        self.semantic_memory = semantic_memory  # Optional Mem0Memory

    async def process(self, message: str, user_id: str, session_id: str) -> str:
        # Fetch history
        history = await self.chat_storage.fetch_chat(user_id, session_id, self.name)

        # Optionally get semantic context
        context = ""
        if self.semantic_memory:
            context = await self.semantic_memory.get_context_for_query(message, user_id)

        # Generate response
        response = await self.llm.chat(history + [message], context=context)

        # Save to storage
        await self.chat_storage.save_chat_message(
            user_id, session_id, self.name,
            {"role": "assistant", "content": response}
        )
        return response
```

### Memory Types

| Type | Use Case |
|------|----------|
| `InMemoryChatStorage` | Short-term conversation history (development) |
| `RedisChatStorage` | Persistent chat storage (production) |
| `Mem0Memory` | Semantic search, cross-session memory |
| `CompositeMemory` | Combine multiple memory strategies |

## Resilient Agents

For production, use `ResilientAgent` with built-in fault tolerance:

```python
from agentorchestrator.agents import ResilientAgent

class ProductionAgent(ResilientAgent):
    name = "production_agent"
    model = "gpt-4"

    # Resilience settings
    max_retries = 3
    retry_delay = 1.0
    timeout = 30
    circuit_breaker_threshold = 5
```

### Resilience Features

- **Retry with backoff** - Automatic retry on transient failures
- **Circuit breaker** - Stops calling failing services
- **Timeout** - Prevents hanging requests
- **Fallback** - Return cached or default response on failure

```python
class SafeAgent(ResilientAgent):
    async def fallback(self, error: Exception, ctx) -> str:
        """Called when all retries fail."""
        return "I'm currently unable to process your request. Please try again later."
```

## Agent in Steps

Agents are commonly used within steps:

```python
analyst = AnalystAgent()

@ao.step(name="analyze")
async def analyze(ctx):
    data = ctx.get("raw_data")
    analysis = await analyst.process(
        f"Analyze this data: {data}",
        ctx,
    )
    ctx.set("analysis", analysis)
    return {"analyzed": True}
```

## Agent Configuration

Configure agents via constructor or config:

```python
class ConfigurableAgent(BaseAgent):
    def __init__(self, config: dict = None):
        super().__init__()
        config = config or {}
        self.model = config.get("model", "gpt-4")
        self.temperature = config.get("temperature", 0.7)
        self.max_tokens = config.get("max_tokens", 2000)

# Usage
agent = ConfigurableAgent({
    "model": "gpt-4-turbo",
    "temperature": 0.3,
})
```

## Best Practices

!!! tip "Clear Instructions"
    Be specific about the agent's role, capabilities, and limitations in the system prompt.

!!! tip "Validate Tool Inputs"
    Check parameters before executing tool logic to prevent errors.

!!! tip "Log Tool Calls"
    Track what tools are called for debugging and monitoring.

!!! warning "Rate Limiting"
    Implement rate limiting for agents that call external APIs.

## Next Steps

- [Multi-Agent Systems](multi_agent.md) - Coordinate multiple agents
- [Steps & Chains](steps_and_chains.md) - Integrate agents into pipelines
