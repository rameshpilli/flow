# AgentOrchestrator

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)

**A DAG-based Chain Orchestration Framework for AI/ML Pipelines**

AgentOrchestrator is a lightweight, decorator-driven framework for building data processing pipelines with automatic dependency resolution, parallel execution, and production-grade resilience. It works alongside existing frameworks like LangChain, LlamaIndex, and CrewAI without requiring platform migration.

---

## Why AgentOrchestrator?

| Feature | AgentOrchestrator | LangChain | LlamaIndex |
|---------|-------------------|-----------|------------|
| **Decorator-driven API** | ✅ `@ao.step()`, `@ao.chain()` | ❌ Class-based chains | ❌ Class-based |
| **DAG execution** | ✅ Auto-parallel, resumable | ⚠️ Sequential chains | ⚠️ Limited |
| **Type-safe state** | ✅ Pydantic models | ❌ Dict-based | ❌ Dict-based |
| **Event-driven workflows** | ✅ Redis/in-memory bus | ❌ No native support | ❌ No native support |
| **Multi-agent patterns** | ✅ Squad, Supervisor, ReAct | ⚠️ Agent executor only | ⚠️ Agent runner |
| **Built-in resilience** | ✅ Retry, circuit breaker | ❌ Manual setup | ❌ Manual setup |
| **Checkpointing/Resume** | ✅ Automatic | ❌ Manual | ❌ Manual |
| **Corporate auth (OAuth)** | ✅ LLM Gateway | ❌ API keys only | ❌ API keys only |

**Best for**: Teams that want Dagster-style ergonomics for AI pipelines with built-in resilience, multi-agent support, and enterprise authentication.

---

## Key Capabilities

| Capability | Description |
|------------|-------------|
| **Decorator-Based Pipelines** | Simple `@ao.step()`, `@ao.chain()`, `@ao.agent()` decorators for intuitive pipeline definition |
| **DAG Execution Engine** | Automatic dependency resolution with parallel execution for optimal performance |
| **Multi-Agent Patterns** | Squad, Supervisor, FunctionAgent with handoffs, and intent-based routing |
| **Type-Safe State Management** | Pydantic models for validated, type-safe workflow state with IDE autocomplete |
| **LLM Gateway Integration** | OAuth-enabled LLM client for corporate environments with structured output support |
| **RAG with Cohere Compass** | Built-in support for Cohere Compass for high-performance enterprise document retrieval |
| **Memory & Storage** | InMemory, Redis, and Mem0 semantic memory for conversation persistence |
| **Shared Squad Memory** | Cross-agent shared context for collaborative multi-agent teams |
| **Secret Management** | Standardized HashiCorp Vault integration with environment fallback |
| **Middleware Stack** | Pluggable logging, caching, rate limiting, and circuit breakers |
| **Summarization Strategies** | Three LLM strategies (STUFF, MAP_REDUCE, REFINE) with domain-specific prompts for large responses |
| **Self-Critique (Reflection)** | Agent self-critique with quality scoring, automatic revision, and `@reflect` decorator |
| **Citation Tracking** | Automatic source attribution and citation reports for RAG pipelines |
| **Memory Lifecycle** | Auto-promote important session data to long-term memory with importance scoring |
| **MCP Connectors** | Model Context Protocol integration for external tool servers (HTTP, stdio, SSE) |
| **Resilience Patterns** | Retry with backoff, circuit breakers, timeouts, and fail-fast cancellation |
| **Observability** | Standardized observability service for tracing, metrics, and application logs |
| **CLI Tools** | Run, validate, visualize, and debug chains from command line |
| **Event-Driven Workflows** | Event bus (Redis-backed or in-memory), event handlers, streaming step/agent/tool events |
| **Declarative DSL (Preview)** | Build pipelines via a fluent builder instead of decorators; register steps, chains, and events together |

---

## Agent Patterns

AgentOrchestrator provides multiple patterns for building AI agents:

| Pattern | Use Case | Example |
|---------|----------|---------|
| **Squad** | Team coordination with supervisor | Research teams, complex analysis |
| **Supervisor Agent** | Central coordinator with specialists | Customer support, multi-domain Q&A |
| **FunctionAgent** | Explicit handoffs between agents | Pipeline workflows (Research → Write → Review) |
| **MultiAgentOrchestrator** | Intent-based routing | Route to specialists based on query type |
| **Linear Chains** | Sequential DAG execution | ETL pipelines, data processing |
| **Deep Research Agent** | Multi-source research synthesis | Financial analysis, market research |

### Quick Comparison

```
┌─────────────────────┬─────────────────────┬─────────────────────┐
│     SQUAD           │   SUPERVISOR        │   FUNCTION AGENT    │
│                     │                     │                     │
│ squad.run(query)    │ supervisor.process()│ agent.handoff()     │
│                     │                     │                     │
│   ┌───────┐         │      ┌───┐          │  ┌───┐    ┌───┐     │
│   │ Lead  │         │      │ S │          │  │ A │ →  │ B │     │
│   └───┬───┘         │      └─┬─┘          │  └───┘    └───┘     │
│   ┌───┴───┐         │    ┌───┼───┐        │                     │
│ ┌─┴─┐ ┌─┴─┐ ┌─┴─┐   │  ┌─┴─┐ ┌─┴─┐ ┌─┴─┐  │  Explicit handoff   │
│ │ A │ │ B │ │ C │   │  │ A │ │ B │ │ C │  │  with context        │
│ └───┘ └───┘ └───┘   │  └───┘ └───┘ └───┘  │                     │
│                     │                     │                     │
│ Simple API          │ Full control        │  Pipeline pattern   │
└─────────────────────┴─────────────────────┴─────────────────────┘
```

---

## Installation

```bash
# Basic installation
pip install -e .

# With all optional features (Redis, LangChain, observability, mem0, vault)
pip install -e ".[all]"

# With specific extras
pip install -e ".[redis]"              # Redis for context store and chat storage
pip install -e ".[summarization]"      # LangChain integration for summarization
pip install -e ".[openai]"             # OpenAI-backed summarizer helpers
pip install -e ".[anthropic]"          # Anthropic-backed summarizer helpers
pip install -e ".[observability]"      # OpenTelemetry tracing
pip install -e ".[workflows]"          # Event-driven workflows (Redis-backed bus)

# Multiple extras
pip install -e ".[redis,summarization,observability]"
```

**Available Extras:**
- `redis` - Redis for context store, chat storage, and event bus
- `summarization` - LangChain integration (summarizers, text splitters, tiktoken)
- `langchain` - Alias for `summarization` (backwards compatibility)
- `openai` - LangChain OpenAI client for OpenAI summarizers
- `anthropic` - LangChain Anthropic client for Anthropic summarizers
- `http` - aiohttp for connector/agent HTTP sessions
- `observability` - OpenTelemetry tracing and structured logging
- `workflows` - Event-driven workflows (includes Redis)
- `memory` - Mem0 semantic memory integration (`mem0ai`)
- `secrets` - HashiCorp Vault integration (`hvac`)
- `all` - Everything above (redis, summarization, openai, anthropic, http, observability, memory, secrets)
- `dev` - Development tools (pytest, ruff, watchdog)
- `docs` - Documentation tools (mkdocs)

**Requirements**: Python 3.10+

---

## Quick Start

### Hello World

```python
from agentorchestrator import AgentOrchestrator

ao = AgentOrchestrator(name="hello_world")

@ao.step(name="greet")
async def greet(ctx):
    name = ctx.get("name", "World")
    return {"greeting": f"Hello, {name}!"}

@ao.chain(name="hello_chain")
class HelloChain:
    steps = ["greet"]

# Run
import asyncio
result = asyncio.run(ao.launch("hello_chain", {"name": "AgentOrchestrator"}))
print(result["results"][0]["output"]["greeting"])  # "Hello, AgentOrchestrator!"
```

### DAG-Style AI Workflow (Parallel Branches)

Define a DAG-style AI workflow in a few lines:

```python
from agentorchestrator import AgentOrchestrator

ao = AgentOrchestrator(name="ai_workflow")

@ao.step(name="plan")
async def plan(ctx):
    question = ctx.get("question")
    ctx.set("query", question)
    return {"plan": f"Research '{question}'"}

@ao.step(name="search_web", deps=["plan"])
async def search_web(ctx):
    web = f"Web notes for {ctx.get('query')}"
    ctx.set("web", web)
    return {"web": web}

@ao.step(name="retrieve_docs", deps=["plan"])
async def retrieve_docs(ctx):
    docs = f"Doc notes for {ctx.get('query')}"
    ctx.set("docs", docs)
    return {"docs": docs}

@ao.step(name="synthesize", deps=["search_web", "retrieve_docs"])
async def synthesize(ctx):
    return {"summary": f"{ctx.get('web')}; {ctx.get('docs')}"}

@ao.chain(name="ai_workflow")
class AIWorkflow:
    steps = ["plan", "search_web", "retrieve_docs", "synthesize"]

result = asyncio.run(ao.launch("ai_workflow", {"question": "AI trends"}))
print(result["results"][-1]["output"]["summary"])
```

Swap the stubbed strings with real LLM/tool calls — the DAG wiring stays the same.

See the runnable example in `agentorchestrator/examples/getting_started/ai_workflow_dag.py`.

### Multi-Step Pipeline with Dependencies

```python
@ao.step(name="fetch")
async def fetch(ctx):
    ctx.set("data", [1, 2, 3, 4, 5])
    return {"fetched": True}

@ao.step(name="process", deps=["fetch"])  # Runs after fetch
async def process(ctx):
    data = ctx.get("data")
    ctx.set("processed", [x * 2 for x in data])
    return {"processed": True}

@ao.step(name="summarize", deps=["process"])
async def summarize(ctx):
    data = ctx.get("processed")
    return {"sum": sum(data), "count": len(data)}

@ao.chain(name="data_pipeline")
class DataPipeline:
    steps = ["fetch", "process", "summarize"]

result = asyncio.run(ao.launch("data_pipeline", {}))
summary = result["results"][-1]["output"]
print(f"Sum: {summary['sum']}, Count: {summary['count']}")
```

### Type-Safe State with Pydantic

Use Pydantic models for validated, type-safe workflow state:

```python
from pydantic import BaseModel, Field
from agentorchestrator import AgentOrchestrator, Context

class PipelineState(BaseModel):
    counter: int = Field(default=0)
    items: list[str] = Field(default_factory=list)
    processed: bool = Field(default=False)

ao = AgentOrchestrator()

@ao.step(name="process", state_model=PipelineState)
async def process(ctx: Context[PipelineState]):
    # Type-safe access with IDE autocomplete!
    async with ctx.edit_state() as state:
        state.counter += 1  # ← IDE knows this is an int
        state.items.append("new_item")  # ← IDE knows this is a list
    
    # Read-only access
    count = ctx.state.counter  # ← Typed!
    return {"count": count}

# When you launch the chain, the state model is picked up automatically
# (all steps must share the same state model).
# result = await ao.launch("typed_pipeline")

# Optional: create a context manually with a state model
from agentorchestrator.core.context import ChainContext
ctx = ChainContext("req_123", state_model=PipelineState)
```

**Benefits**:
- ✅ IDE autocomplete and type hints
- ✅ Automatic validation via Pydantic
- ✅ Atomic updates via context manager
- ✅ Thread-safe concurrent access

### Parallel Execution

Steps without dependencies run in parallel automatically:

```python
@ao.step(name="fetch_news")
async def fetch_news(ctx):
    await asyncio.sleep(1)  # Simulates API call
    return {"news": ["headline1", "headline2"]}

@ao.step(name="fetch_stocks")
async def fetch_stocks(ctx):
    await asyncio.sleep(1)  # Simulates API call
    return {"stocks": {"AAPL": 150, "GOOGL": 140}}

@ao.step(name="combine", deps=["fetch_news", "fetch_stocks"])
async def combine(ctx):
    return {"combined": True}

@ao.chain(name="parallel_chain")
class ParallelChain:
    steps = ["fetch_news", "fetch_stocks", "combine"]

# fetch_news and fetch_stocks run in parallel (~1s total, not 2s)
```

### Dataflow-Based Dependencies

Automatically resolve step dependencies based on data flow using `produces`/`consumes`:

```python
from agentorchestrator import AgentOrchestrator, produces, consumes

ao = AgentOrchestrator(name="dataflow_example")

@produces("company_data")
@ao.step(name="fetch_company")
async def fetch_company(ctx):
    data = await api.get_company("AAPL")
    ctx.set("company_data", data)
    return data

@consumes("company_data")
@produces("analysis")
@ao.step(name="analyze")
async def analyze(ctx):
    data = ctx.get("company_data")
    return {"analysis": analyze_data(data)}

@consumes("company_data", "analysis")
@ao.step(name="report")
async def report(ctx):
    return {"report": generate_report(ctx)}

# Enable dataflow resolution on the chain
@ao.chain(name="research_chain", dataflow=True)
class ResearchChain:
    steps = ["fetch_company", "analyze", "report"]
```

With `dataflow=True`:
- `analyze` automatically depends on `fetch_company` (consumes `company_data`)
- `report` automatically depends on both (consumes `company_data` and `analysis`)
- Explicit `deps=[]` declarations are merged with dataflow-inferred dependencies

Use `ao.check()` to validate dataflow resolution and see the resolved dependency graph.

---

## Multi-Agent Patterns

### 1. Squad Pattern (Recommended for Teams)

The simplest way to coordinate multiple agents:

```python
from agentorchestrator.squad import (
    Squad,
    SquadOptions,
    LLMGatewayAgent,
    LLMGatewayAgentOptions,
)

# Create specialist agents
research_agent = LLMGatewayAgent(LLMGatewayAgentOptions(
    name="Researcher",
    description="Find and gather information on topics.",
    llm_client=llm_client,
))

analyst_agent = LLMGatewayAgent(LLMGatewayAgentOptions(
    name="Analyst",
    description="Analyze data and provide insights.",
    llm_client=llm_client,
))

writer_agent = LLMGatewayAgent(LLMGatewayAgentOptions(
    name="Writer",
    description="Write clear, compelling content.",
    llm_client=llm_client,
))

# Create supervisor (lead agent)
lead = LLMGatewayAgent(LLMGatewayAgentOptions(
    name="ProjectLead",
    description="Coordinates team to answer complex questions",
    llm_client=llm_client,
))

# Form the squad
squad = Squad(
    supervisor=lead,
    agents=[research_agent, analyst_agent, writer_agent],
    options=SquadOptions(trace=True),
)

# Execute - supervisor coordinates the team automatically
result = await squad.run("Research AI trends and write a report")
print(result.content)
```

See: [examples/supervisor_chain.py](examples/supervisor_chain.py)

### 2. FunctionAgent with Handoffs (Pipeline Pattern)

For explicit agent-to-agent workflows:

```python
from agentorchestrator.squad import FunctionAgent, FunctionAgentOptions

# Create agents with handoff permissions
researcher = FunctionAgent(FunctionAgentOptions(
    name="Researcher",
    description="Gathers information",
    llm_client=llm_client,
    can_handoff_to=["Writer"],  # Can only hand off to Writer
))

writer = FunctionAgent(FunctionAgentOptions(
    name="Writer",
    description="Writes reports",
    llm_client=llm_client,
    can_handoff_to=["User"],  # Terminal - returns to user
))

# Researcher hands off to Writer with context
handoff = await researcher.handoff(
    to_agent="Writer",
    context={"findings": findings, "sources": sources},
    message="Research complete. Please write a summary.",
)

# Orchestrator routes using handoff.to_agent
print(f"{handoff.from_agent} → {handoff.to_agent}")
# "Researcher → Writer"
```

### 3. Deep Research Agent (Financial Analysis)

Multi-source research with context management:

```python
from agentorchestrator.examples.financial_research_agent import (
    FinancialResearchAgent,
    ResearchConfig,
)

# Create agent with context management
agent = FinancialResearchAgent(ResearchConfig(
    max_context_tokens=100_000,
    enable_auto_summarization=True,
))

# Run comprehensive research
report = await agent.research(
    topic="Analyze Tesla's competitive position in the EV market",
    focus_areas=["market share", "technology", "financials"],
    depth="comprehensive",
)

print(report.executive_summary)
for finding in report.key_findings:
    print(f"- {finding.finding} ({finding.confidence:.0%} confidence)")
```

See: [examples/financial_research_agent.py](examples/financial_research_agent.py)

### 4. MultiAgentOrchestrator (Intent-Based Routing)

Route queries to specialists based on intent:

```python
from agentorchestrator.squad import (
    MultiAgentOrchestrator,
    LLMGatewayClassifier,
    LLMGatewayAgent,
)

# Create orchestrator with classifier
orchestrator = MultiAgentOrchestrator(
    classifier=LLMGatewayClassifier(llm_client=llm_client),
)

# Add specialist agents
orchestrator.add_agent(tech_agent)
orchestrator.add_agent(finance_agent)
orchestrator.add_agent(support_agent)

# Classifier automatically routes to the right agent
response = await orchestrator.route_request(
    "How do I optimize my Python code?",
    user_id="user-123",
)
# Routes to tech_agent based on query content
```

---

## LLM Gateway (Corporate Environments)

For corporate environments behind an LLM gateway with OAuth authentication:

```python
from agentorchestrator.services import LLMGatewayClient, LLMGatewayConfig

# Option 1: Direct configuration
client = LLMGatewayClient(
    server_url="https://llm-gateway.corp.com/v1/chat/completions",
    oauth_endpoint="https://auth.corp.com/token",
    client_id="my-app",
    client_secret="secret",
    model_name="gpt-4",
)

# Option 2: From environment variables
# Set: LLM_SERVER_URL, LLM_OAUTH_ENDPOINT, LLM_CLIENT_ID, LLM_CLIENT_SECRET
client = LLMGatewayClient.from_env()

# Generate text
response = await client.generate_async("What is 2+2?")

# Structured output with Pydantic
from pydantic import BaseModel

class Answer(BaseModel):
    result: int
    explanation: str

result = await client.generate_structured_async(
    "What is 2+2?",
    response_model=Answer,
)
print(result.result)  # 4
```

---

## Memory & Storage

### Chat Storage (Conversation History)

```python
from agentorchestrator.squad.storage import InMemoryChatStorage

# In-memory storage (development)
storage = InMemoryChatStorage()

# Save messages
await storage.save_chat_message(
    user_id="user-123",
    session_id="session-abc",
    agent_id="assistant",
    new_message={"role": "user", "content": "Hello!"}
)

# Fetch history
history = await storage.fetch_chat("user-123", "session-abc", "assistant")
```

### Redis Storage (Production)

```python
from agentorchestrator.squad.storage.redis import RedisChatStorage

# Redis storage (production)
storage = RedisChatStorage(
    host="redis.corp.com",
    port=6379,
    password="secret",
)
```

### Semantic Memory (Mem0)

```python
from agentorchestrator.services import Mem0Memory
from your_app import MemoryStoreClient

# Connect to corporate mem0
client = MemoryStoreClient(
    base_url="https://mem0.corp.com",
    agent_id="my-agent"
)
memory = Mem0Memory(client=client)

# Store memories
await memory.add("User prefers technical explanations")

# Search memories semantically
results = await memory.search("What are user's preferences?")
for mem in results:
    print(mem.content)
```

---

## Context Isolation

Prevent context pollution in multi-agent systems:

```python
from agentorchestrator.squad.context import (
    ContextIsolationManager,
    IsolationLevel,
    ResultAggregator,
    AggregationStrategy,
)

# Create isolation manager
isolation = ContextIsolationManager(
    coordinator_context=ctx,
    isolation_level=IsolationLevel.FULL,
)

# Each agent gets isolated namespace
for agent in team:
    isolation.create_namespace(agent.id)

# Share only what's needed
isolation.share_with_all("query", user_query)
isolation.share_between("researcher", "findings", ["analyst", "writer"])

# Aggregate results
aggregator = ResultAggregator(strategy=AggregationStrategy.SYNTHESIZE)
final = await aggregator.aggregate(llm=client)
```

---

## Event-Driven Workflows

Build reactive pipelines with event handlers and pub/sub:

```python
from agentorchestrator import AgentOrchestrator
from agentorchestrator.core.event_bus import Event

ao = AgentOrchestrator()

# Define event handlers
@ao.event_handler("ResearchTask")
async def handle_research(ctx, event):
    """Process research tasks and emit findings."""
    query = event.payload.get("query")
    findings = await do_research(query)
    
    # Emit new event with findings
    return Event(
        type="ResearchComplete",
        payload={"findings": findings, "query": query},
    )

@ao.event_handler("ResearchComplete")
async def handle_research_complete(ctx, event):
    """Aggregate research findings."""
    findings = event.payload.get("findings")
    ctx.set("research_findings", findings)
    
    # Could emit more events for further processing
    return Event(type="SynthesizeReport", payload={"findings": findings})

# Run the event loop
result = await ao.run_event_loop(
    seed_events=[
        Event(type="ResearchTask", payload={"query": "AI trends 2024"}),
    ],
    max_events=50,
    timeout_s=60.0,
    stop_when=lambda event, ctx: event.type == "SynthesizeReport",
)

print(f"Processed {result['processed']} events in {result['duration_ms']}ms")
```

### Event Bus Configuration

```python
# Use Redis-backed event bus for distributed systems
from agentorchestrator.core.event_bus import get_event_bus

# Auto-detects Redis if available, falls back to in-memory
event_bus = get_event_bus(prefer_redis=True)

# Create orchestrator with custom event bus
ao = AgentOrchestrator(event_bus=event_bus)
```

### Built-in Events

The DAG executor emits these events automatically:

**Step Events:**

| Event Type | Payload | When Emitted |
|------------|---------|--------------|
| `StepStarted` | `{attempt}` | Step begins execution |
| `StepCompleted` | `{duration_ms, retry_count}` | Step completes successfully |
| `StepFailed` | `{error, error_type, duration_ms}` | Step fails |
| `StepSkipped` | `{reason}` | Step skipped (dependency failed) |

**Chain Lifecycle Events:**

| Event Type | Payload | When Emitted |
|------------|---------|--------------|
| `ChainStarted` | `{step_count}` | Before first step executes |
| `ChainCompleted` | `{completed, failed, skipped}` | After all steps complete successfully |
| `ChainFailed` | `{error}` | When chain execution fails |
| `DynamicStepInjected` | `{injected_steps, parent_step}` | When dynamic steps are added |

See: [examples/event_workflow.py](examples/event_workflow.py)

---

## ReAct Agent Pattern

Industry-standard Thought→Action→Observation loop:

```python
from agentorchestrator.agents import ReActAgent, Tool, ToolRegistry

# Create a tool registry
registry = ToolRegistry()

@registry.tool("search", "Search the web for information")
async def search(query: str) -> str:
    return await web_search(query)

@registry.tool("calculate", "Evaluate mathematical expressions")
def calculate(expression: str) -> str:
    return str(eval(expression))  # Use safe eval in production

# Create ReAct agent
agent = ReActAgent(
    llm_client=llm_client,
    tools=registry.list_tools(),
)

# Run with reasoning trace
result = await agent.run("What is the population of France divided by 3?")

print(result.thought_trace)
# Thought: I need to find the population of France first.
# Action: search("population of France 2024")
# Observation: The population of France is approximately 68 million.
# Thought: Now I need to divide 68 million by 3.
# Action: calculate("68000000 / 3")
# Observation: 22666666.67
# Thought: I have the answer.
# Final Answer: The population of France (68 million) divided by 3 is approximately 22.67 million.

print(result.final_answer)
```

---

## MCP Connectors (Model Context Protocol)

Connect to external MCP servers to extend your agents with custom tools and data sources:

```python
from agentorchestrator.plugins import MCPAdapterAgent, MCPAdapterConfig

# Create MCP adapter for an external tool server
config = MCPAdapterConfig(
    name="my_mcp_server",
    server_url="http://localhost:3000/mcp",
    transport="http",  # "http", "stdio", or "sse"
    timeout_seconds=30.0,
    cache_enabled=True,        # Cache tool responses
    cache_ttl_seconds=3600,    # 1 hour cache
)

agent = MCPAdapterAgent(config)
await agent.initialize()

# List available tools from the MCP server
tools = await agent.list_tools()
for tool in tools:
    print(f"Tool: {tool.name} - {tool.description}")

# Call a tool
result = await agent.call_tool("search", {"query": "AI trends 2024"})
print(result)

# Or use the fetch interface
result = await agent.fetch("search", tool_args={"query": "AI trends"})
```

### MCP Transport Types

| Transport | Use Case | Configuration |
|-----------|----------|---------------|
| `http` | Remote MCP servers | `server_url="https://..."` |
| `stdio` | Local subprocess servers | `server_command="npx", server_args=["-y", "@modelcontextprotocol/server"]` |
| `sse` | Server-sent events | `server_url="https://..."` (streaming) |

### Creating Custom MCP Agents

```python
from agentorchestrator.connectors import MCPAgent, ConnectorConfig
from agentorchestrator import ao

@ao.agent(name="my_data_source")
class MyDataAgent(MCPAgent):
    """Custom agent wrapping an MCP server."""

    connector_config = ConnectorConfig(
        name="my_mcp",
        base_url="http://localhost:8000",
    )

    async def fetch(self, query: str, **kwargs) -> AgentResult:
        result = await self.connector.call_tool("search", {"query": query})
        return AgentResult(data=result, source="my_mcp", query=query)
```

### Factory Function

```python
from agentorchestrator.plugins import create_mcp_agent

# Quick creation with factory function
agent = create_mcp_agent(
    name="financial_data",
    server_url="http://localhost:3000",
    transport="http",
    headers={"Authorization": "Bearer token"},
    cache_enabled=True,
)

await agent.initialize()
result = await agent.call_tool("get_stock_price", {"symbol": "AAPL"})
```

### MCP with Deep Research Agent

```python
from agentorchestrator.examples.financial_research_agent import FinancialResearchAgent

# The financial research agent uses MCP servers for data sources
agent = FinancialResearchAgent(config)

# MCP servers provide real-time financial data
report = await agent.research(
    topic="Analyze Tesla's Q4 earnings",
    focus_areas=["revenue", "margins", "guidance"],
)
```

See: [MCP Connectors Documentation](docs/MCP_CONNECTORS.md) for complete reference.

---

## Middleware

Add cross-cutting concerns to your pipelines:

```python
from agentorchestrator.middleware import (
    LoggerMiddleware,
    CacheMiddleware,
    SummarizerMiddleware,
    RateLimiterMiddleware,
    MiddlewareCircuitBreakerConfig,
    CircuitBreakerMiddleware,
    ReflectionMiddleware,
    CitationMiddleware,
    TokenManagerMiddleware,
    MetricsMiddleware,
    IdempotencyMiddleware,
)

ao = AgentOrchestrator(name="my_app")

# Logging
ao.use(LoggerMiddleware(level="INFO"))

# Caching (5 minute TTL)
ao.use(CacheMiddleware(ttl_seconds=300))

# Summarization for large outputs
ao.use(SummarizerMiddleware(summarizer=summarizer, max_tokens=4000))

# Rate limiting
ao.use(RateLimiterMiddleware({
    "fetch_data": {"requests_per_second": 10},
}))

# Circuit breaker for resilience
ao.use(CircuitBreakerMiddleware({
    "external_api": MiddlewareCircuitBreakerConfig(failure_threshold=5),
}))

# Self-critique / reflection (see section below)
ao.use(ReflectionMiddleware(quality_threshold=0.8, max_revisions=2))

# Citation tracking for RAG
ao.use(CitationMiddleware())

# Token budget management
ao.use(TokenManagerMiddleware(max_tokens=8000))

# Metrics collection
ao.use(MetricsMiddleware())

# Idempotent step execution (prevent duplicates)
ao.use(IdempotencyMiddleware())
```

### Available Middleware

| Middleware | Purpose |
|------------|---------|
| `LoggerMiddleware` | Structured logging for step execution |
| `CacheMiddleware` | Response caching with TTL |
| `SummarizerMiddleware` | LLM-based summarization (stuff, map_reduce, refine) |
| `RateLimiterMiddleware` | Request rate limiting per step |
| `CircuitBreakerMiddleware` | Failure protection (CLOSED → OPEN → HALF_OPEN) |
| `ReflectionMiddleware` | Agent self-critique with quality scoring |
| `CitationMiddleware` | Source attribution tracking for RAG |
| `TokenManagerMiddleware` | Token budget management |
| `MetricsMiddleware` | Execution metrics (latency, success rate) |
| `IdempotencyMiddleware` | Prevent duplicate step execution |
| `OffloadMiddleware` | Auto-offload large payloads to Redis |
| `UsageAnalyticsMiddleware` | Usage tracking and analytics |
| `MemoryLifecycleMiddleware` | Auto-promote session data to long-term memory |

---

## Summarization Strategies

When agents return large responses that exceed context windows, use `SummarizerMiddleware` to intelligently compress content while preserving key information:

```python
from agentorchestrator.middleware import (
    SummarizerMiddleware,
    SummarizationStrategy,
    LangChainSummarizer,
    create_gateway_summarizer,
)

# Create a summarizer (using LLM Gateway, OpenAI, or Anthropic)
summarizer = create_gateway_summarizer(
    server_url="https://llm-gateway.corp.com/v1",
    model_name="gpt-4",
)

# Apply middleware with chosen strategy
ao.use(SummarizerMiddleware(
    summarizer=summarizer,
    strategy=SummarizationStrategy.MAP_REDUCE,  # or STUFF, REFINE
    max_tokens=4000,              # Target summary size
    threshold_tokens=8000,        # Only summarize if > threshold
    preserve_original=True,       # Store original for debugging
))
```

### Three Strategies

| Strategy | Best For | How It Works |
|----------|----------|--------------|
| **STUFF** | Small documents (<8K tokens) | Single LLM call with all text |
| **MAP_REDUCE** | Large documents, parallel processing | Split → summarize chunks in parallel → combine |
| **REFINE** | Maintaining coherence, sequential docs | Iteratively refine summary with each chunk |

```
MAP_REDUCE Strategy:
┌──────────────────────────────────────────────────────────────┐
│  Large Document (50K tokens)                                 │
└──────────────────────────────────────────────────────────────┘
                           │
                           ▼
        ┌──────────────────┼──────────────────┐
        │                  │                  │
        ▼                  ▼                  ▼
   ┌─────────┐        ┌─────────┐        ┌─────────┐
   │ Chunk 1 │        │ Chunk 2 │        │ Chunk 3 │   (parallel)
   └────┬────┘        └────┬────┘        └────┬────┘
        │                  │                  │
        ▼                  ▼                  ▼
   ┌─────────┐        ┌─────────┐        ┌─────────┐
   │Summary 1│        │Summary 2│        │Summary 3│
   └────┬────┘        └────┬────┘        └────┬────┘
        │                  │                  │
        └──────────────────┼──────────────────┘
                           │
                           ▼
                   ┌───────────────┐
                   │ Final Summary │  (4K tokens)
                   └───────────────┘
```

### Domain-Specific Prompts

Customize summarization for different content types to preserve domain-specific details:

```python
# Register domain-specific prompts
LangChainSummarizer.register_domain_prompts(
    domain="financial_news",
    map_prompt="""Summarize this financial news, preserving:
- Company names and tickers
- Key metrics (revenue, EPS, growth rates)
- Analyst opinions and price targets

{text}

Summary:""",
    reduce_prompt="""Combine these financial summaries into a cohesive analysis:

{text}

Final Analysis:""",
)

# Apply to specific steps
ao.use(SummarizerMiddleware(
    summarizer=summarizer,
    step_content_types={
        "gather_news": "financial_news",
        "gather_sec": "sec_filings",
        "gather_earnings": "financial_news",
    },
))
```

### Step-Specific Configuration

Configure different strategies and limits per step:

```python
ao.use(SummarizerMiddleware(
    summarizer=summarizer,
    step_strategies={
        "gather_news": SummarizationStrategy.MAP_REDUCE,   # Large, parallel
        "gather_sec": SummarizationStrategy.REFINE,       # Sequential, coherent
        "quick_lookup": SummarizationStrategy.STUFF,      # Small, fast
    },
    step_max_tokens={
        "gather_news": 2000,
        "gather_sec": 3000,
        "quick_lookup": 1000,
    },
))
```

### Factory Functions

```python
# OpenAI
from agentorchestrator.middleware import create_openai_summarizer
summarizer = create_openai_summarizer(model="gpt-4", api_key="...")

# Anthropic Claude
from agentorchestrator.middleware import create_anthropic_summarizer
summarizer = create_anthropic_summarizer(model="claude-3-sonnet-20240229")

# LLM Gateway (corporate environments with OAuth)
from agentorchestrator.middleware import create_gateway_summarizer
summarizer = create_gateway_summarizer(
    server_url=os.getenv("LLM_SERVER_URL"),
    oauth_endpoint=os.getenv("LLM_OAUTH_ENDPOINT"),
    client_id=os.getenv("LLM_CLIENT_ID"),
    client_secret=os.getenv("LLM_CLIENT_SECRET"),
)
```

### Combining with Token Management

For comprehensive context management, layer multiple middleware:

```python
# 1. Token budget management (triggers auto-compression)
ao.use(TokenManagerMiddleware(
    max_total_tokens=8000,
    warning_threshold=0.8,
    auto_summarize=True,
))

# 2. Summarization (compresses large outputs)
ao.use(SummarizerMiddleware(
    summarizer=summarizer,
    max_tokens=4000,
    threshold_tokens=6000,
))

# 3. Offload to Redis (for very large data)
ao.use(OffloadMiddleware(
    store=RedisContextStore(),
    threshold_bytes=500_000,
))
```

See: [Summarization Pattern Guide](docs/patterns/summarization.md) for complete reference with decision trees and advanced examples.

---

## Memory Lifecycle Management

Automatically promote important session data to long-term memory using the MemoryLifecycleMiddleware:

```python
from agentorchestrator.middleware import (
    MemoryLifecycleMiddleware,
    MemoryLifecycleConfig,
    create_memory_lifecycle_middleware,
)
from agentorchestrator.squad.storage.redis import RedisChatStorage
from agentorchestrator.services import Mem0Memory

# Setup memory backends with user-configurable TTL
session_storage = RedisChatStorage(ttl_seconds=86400)  # 24 hours
longterm_memory = Mem0Memory(client=mem0_client)

# Option 1: Heuristic-based promotion (no LLM required)
ao.use(MemoryLifecycleMiddleware(
    session_storage=session_storage,
    longterm_memory=longterm_memory,
    config=MemoryLifecycleConfig(
        importance_threshold=0.8,      # Promote if score >= 0.8
        auto_promote_patterns=True,    # User preferences/patterns
        auto_promote_decisions=True,   # Key decisions
        batch_size=10,                 # Batch before promoting
        deduplicate=True,              # Skip duplicates
    ),
))

# Option 2: LLM-based importance evaluation (more accurate)
ao.use(create_memory_lifecycle_middleware(
    session_storage=session_storage,
    longterm_memory=longterm_memory,
    llm_client=llm_client,             # Enables LLM evaluation
    importance_threshold=0.75,
))
```

### How Memory Promotion Works

```
Session Memory (Redis)              Long-term Memory (Mem0)
      │                                     ▲
      │                                     │
      ▼                                     │
┌──────────────┐                           │
│ Step Output  │                           │
└──────┬───────┘                           │
       │                                    │
       ▼                                    │
┌──────────────┐                           │
│  Evaluate    │  score >= 0.8? ───Yes────►│
│  Importance  │                           │
└──────┬───────┘                           │
       │                                    │
       No                                   │
       ▼                                    │
   (discard)
```

### Importance Evaluation Methods

**Heuristic Evaluator** (default):
- Detects patterns: "prefer", "like", "style", "always"
- Detects decisions: "decide", "chose", "approve"
- Detects solutions: "fix", "resolve", "workaround"

**LLM Evaluator** (optional):
```python
from agentorchestrator.middleware import LLMImportanceEvaluator

evaluator = LLMImportanceEvaluator(llm_client)
middleware = MemoryLifecycleMiddleware(
    longterm_memory=longterm_memory,
    evaluator=evaluator,
)
```

### Statistics

```python
stats = middleware.get_stats()
# {"evaluated": 100, "promoted": 15, "rejected": 85, "avg_importance_score": 0.62}

await middleware.flush()  # Manually flush pending promotions
```

---

## Self-Critique / Reflection

Enable agents to review and revise their own outputs using the ReflectionMiddleware:

```python
from agentorchestrator.middleware import (
    ReflectionMiddleware,
    ReflectionConfig,
    reflect,
)

# Option 1: Apply middleware globally
ao.use(ReflectionMiddleware(
    config=ReflectionConfig(
        quality_threshold=0.8,  # Minimum score (0.0-1.0) to accept
        max_revisions=2,        # Max revision attempts
    ),
))

# Option 2: Use @reflect decorator on specific steps
@ao.step(name="generate_report")
@reflect(
    critique_prompt="Review this report for accuracy, clarity, and completeness.",
    quality_threshold=0.85,
    max_revisions=3,
)
async def generate_report(ctx):
    data = ctx.get("research_findings")
    report = await generate_report_content(data)
    return {"report": report}
```

### How Reflection Works

```
┌─────────────────────────────────────────────────────────────┐
│                    REFLECTION CYCLE                          │
│                                                              │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐              │
│  │ Generate │ →  │ Critique │ →  │  Score   │              │
│  │  Output  │    │  (LLM)   │    │ (0.0-1.0)│              │
│  └──────────┘    └──────────┘    └────┬─────┘              │
│                                       │                     │
│                    ┌──────────────────┴──────────────────┐  │
│                    │                                     │  │
│               score >= threshold?                        │  │
│                    │                                     │  │
│              Yes ──┴── No                                │  │
│               │        │                                 │  │
│               ▼        ▼                                 │  │
│         ┌─────────┐  ┌─────────┐                        │  │
│         │ Return  │  │ Revise  │ → (loop up to max)     │  │
│         │ Output  │  │  Output │                        │  │
│         └─────────┘  └─────────┘                        │  │
└─────────────────────────────────────────────────────────────┘
```

### Reflection Configuration

```python
from agentorchestrator.middleware import ReflectionConfig

config = ReflectionConfig(
    quality_threshold=0.8,      # Score needed to pass (0.0-1.0)
    max_revisions=2,            # Max revision attempts
    critique_prompt=None,       # Custom critique prompt (optional)
    revision_prompt=None,       # Custom revision prompt (optional)
    enabled=True,               # Enable/disable reflection
    store_trace=True,           # Store reflection trace in context
    applies_to=["step1"],       # Only apply to specific steps
    excludes=["step2"],         # Exclude specific steps
)
```

### Accessing Reflection Results

```python
# After step execution, access the reflection trace
traces = ctx.get("_reflection_trace", default={})
step_trace = traces.get("generate_report")

print(f"Quality Score: {step_trace['quality_score']}")
print(f"Revisions: {step_trace['revision_count']}")
print(f"Passed Threshold: {step_trace['passed_threshold']}")
```

> **Note**: The examples directory does not currently include a dedicated self-critique/reflection example. Use the middleware configuration shown above to add reflection to your pipelines.

---

## Examples

| Example | Description | Location |
|---------|-------------|----------|
| **Hello World** | Basic step and chain setup | [examples/getting_started/](examples/getting_started/) |
| **Supervisor Chain** | Multi-agent supervisor pattern | [examples/supervisor_chain.py](examples/supervisor_chain.py) |
| **Financial Research** | Deep research agent with MCP servers | [examples/financial_research_agent.py](examples/financial_research_agent.py) |
| **Hybrid Memory** | 3-layer memory architecture (Session/Long-term/Reference) | [examples/hybrid_memory_pitchbook.py](examples/hybrid_memory_pitchbook.py) |
| **RAG Pipeline** | Retrieval-augmented generation | [examples/rag/](examples/rag/) |
| **Memory Integration** | Chat storage and semantic memory | [examples/memory/](examples/memory/) |

### Running Examples

```bash
# Run the supervisor chain example
python -m agentorchestrator.examples.supervisor_chain

# Run the financial research agent
python -m agentorchestrator.examples.financial_research_agent \
    "Analyze Tesla's competitive position" \
    --focus "market share" "technology" \
    --depth comprehensive

# Or use the CLI
ao run hello_chain --data '{"name": "World"}'
```

---

## CLI

The CLI is available as both `ao` (shorthand, recommended) and `agentorchestrator` (full name):

```bash
# Execution Commands
ao run my_pipeline --data '{"key": "value"}'      # Run a chain
ao run my_pipeline --resumable                    # With checkpointing
ao run my_pipeline --dry-run                      # Preview execution plan
ao run my_pipeline --step my_step                 # Test single step
ao resume <run_id>                                # Resume failed run
ao runs --status failed                           # List failed runs
ao run-info <run_id>                              # Show run details
ao run-output <run_id>                            # Get partial outputs

# Validation & Inspection
ao check                                          # Quick validation
ao validate my_chain                              # Comprehensive validation
ao validate my_chain --data '{"sample": "data"}'  # With sample data
ao list                                           # List all components
ao graph my_pipeline                              # ASCII DAG visualization
ao graph my_pipeline --format mermaid             # Mermaid diagram

# Development & Debugging
ao dev --watch                                    # Hot reload mode
ao debug my_chain --data '{"key": "value"}'       # Debug with snapshots

# Health & Diagnostics
ao health                                         # Basic health check
ao health --detailed                              # Full dependency check
ao doctor                                         # Diagnose setup issues
ao version                                        # Show version
ao config                                         # Show config (masked)

# Scaffolding
ao new agent MyAgent                              # Generate agent template
ao new chain MyChain                              # Generate chain template
ao new project my-app                             # Generate full project
```

See [CLI Reference](docs/cli/index.md) for complete documentation.

---

## Documentation

| Section | Description |
|---------|-------------|
| [Quick Start](docs/QUICKSTART.md) | Get started in 5 minutes |
| [Understanding](docs/understanding/) | Core concepts: Context, Steps, Agents, Multi-Agent |
| [Patterns](docs/patterns/) | Production patterns: Isolation, Summarization, Routing |
| [API Reference](docs/API.md) | Full API documentation |
| [Architecture](docs/ARCHITECTURE.md) | System design & diagrams |
| [MCP Connectors](docs/MCP_CONNECTORS.md) | Model Context Protocol integration guide |
| [Troubleshooting](docs/TROUBLESHOOTING.md) | Common issues & solutions |

### Build Documentation Site

```bash
pip install mkdocs-material mkdocs-minify-plugin
cd ..  # ChainServer root
mkdocs serve
```

---

## Project Structure

```
agentorchestrator/
├── core/               # AgentOrchestrator, Context, DAG, Registry
├── middleware/         # Cache, Logger, Summarizer, Rate Limiter
├── squad/              # Multi-agent orchestration
│   ├── agents/         # LLMGatewayAgent, SupervisorAgent, FunctionAgent
│   ├── classifiers/    # Intent classification
│   ├── context/        # Context isolation & result aggregation
│   └── storage/        # Chat storage (InMemory, Redis)
├── agents/             # BaseAgent, ResilientAgent
├── services/           # External integrations
│   ├── llm_gateway.py  # LLMGatewayClient with OAuth
│   ├── redis.py        # RedisService
│   ├── vector_store.py # VectorStoreService
│   └── mem0.py         # Mem0Memory (semantic memory)
├── utils/              # Logging, tracing, circuit breaker
├── examples/           # Example implementations
│   ├── getting_started/# Hello world, simple chains
│   ├── agents/         # Multi-agent examples
│   ├── rag/            # RAG pipeline examples
│   └── memory/         # Memory integration examples
└── docs/               # Documentation
```

---

## Key Imports

```python
# Core
from agentorchestrator import AgentOrchestrator, Context

# Services
from agentorchestrator.services import (
    LLMGatewayClient,       # LLM with OAuth
    LLMGatewayConfig,       # LLM configuration
    RedisService,           # Redis client
    VectorStoreService,     # Vector search
    VectorDocument,         # Document for vector store
    Mem0Memory,             # Semantic memory
    CompositeMemory,        # Combined memory strategies
)

# Storage
from agentorchestrator.squad.storage import InMemoryChatStorage
from agentorchestrator.squad.storage.redis import RedisChatStorage

# Agents
from agentorchestrator.agents import BaseAgent, ResilientAgent, AgentResult

# Squad (Multi-Agent) - All patterns
from agentorchestrator.squad import (
    # High-level Squad wrapper
    Squad,
    SquadOptions,
    # Agent types
    LLMGatewayAgent,
    LLMGatewayAgentOptions,
    SupervisorAgent,
    SupervisorAgentOptions,
    FunctionAgent,
    FunctionAgentOptions,
    HandoffResult,
    # Routing
    MultiAgentOrchestrator,
    LLMGatewayClassifier,
    # Context management
    IsolationLevel,
    ContextIsolationManager,
    ResultAggregator,
    AggregationStrategy,
)

# Middleware
from agentorchestrator.middleware import (
    # Core middleware
    CacheMiddleware,
    LoggerMiddleware,
    SummarizerMiddleware,
    RateLimiterMiddleware,
    CircuitBreakerMiddleware,
    MiddlewareCircuitBreakerConfig,
    # Self-critique / Reflection
    ReflectionMiddleware,
    ReflectionConfig,
    reflect,
    # Citation tracking
    CitationMiddleware,
    cite,
    get_citation_report,
    # Token & metrics
    TokenManagerMiddleware,
    MetricsMiddleware,
    # Idempotency
    IdempotencyMiddleware,
    # Offload large payloads
    OffloadMiddleware,
    # Usage analytics
    UsageAnalyticsMiddleware,
    # Memory lifecycle (session → long-term promotion)
    MemoryLifecycleMiddleware,
    MemoryLifecycleConfig,
    create_memory_lifecycle_middleware,
)

# MCP Connectors (Model Context Protocol)
from agentorchestrator.plugins import (
    MCPAdapterAgent,
    MCPAdapterConfig,
    create_mcp_agent,
)
from agentorchestrator.connectors import (
    MCPConnector,
    MCPAgent,
    ConnectorConfig,
)

# Utilities
from agentorchestrator.utils import (
    CircuitBreaker,
    configure_logging,
    get_logger,
)
```

---

## Environment Variables

### LLM Gateway

| Variable | Description | Default |
|----------|-------------|---------|
| `LLM_SERVER_URL` | LLM Gateway endpoint | - |
| `LLM_MODEL_NAME` | Model to use | `gpt-4` |
| `LLM_OAUTH_ENDPOINT` | OAuth token endpoint | - |
| `LLM_CLIENT_ID` | OAuth client ID | - |
| `LLM_CLIENT_SECRET` | OAuth client secret | - |
| `LLM_API_KEY` | API key (alternative to OAuth) | - |
| `LLM_TEMPERATURE` | Sampling temperature | `0.2` |
| `LLM_MAX_TOKENS` | Max output tokens | `4096` |
| `LLM_TIMEOUT` | Request timeout in seconds | `120` |
| `LLM_VERIFY_SSL` | Verify TLS certificates to the LLM gateway | `true` |

### Chain Execution

| Variable | Description | Default |
|----------|-------------|---------|
| `CHAIN_MAX_PARALLEL_STEPS` | Max concurrent steps | `5` |
| `CHAIN_DEFAULT_TIMEOUT_MS` | Step timeout in milliseconds | `30000` |
| `CHAIN_DEFAULT_RETRIES` | Default retry count | `3` |
| `CHAIN_ERROR_HANDLING` | Error strategy: `fail_fast`, `continue`, `retry` | `fail_fast` |

### Context Store (Redis/Mem0)

| Variable | Description | Default |
|----------|-------------|---------|
| `CONTEXT_STORE_BACKEND` | Backend: `memory`, `redis`, `mem0` | `memory` |
| `CONTEXT_STORE_REDIS_HOST` | Redis host | `localhost` |
| `CONTEXT_STORE_REDIS_PORT` | Redis port | `6379` |
| `CONTEXT_STORE_REDIS_PASSWORD` | Redis password | - |
| `CONTEXT_STORE_REDIS_DB` | Redis database number | `0` |
| `CONTEXT_STORE_REDIS_SSL` | Enable TLS | `false` |
| `CONTEXT_STORE_REDIS_SSL_CERT_REQS` | SSL cert requirements | - |
| `CONTEXT_STORE_REDIS_MAXMEMORY` | Memory limit (e.g., `128mb`) | - |
| `CONTEXT_STORE_REDIS_MAXMEMORY_POLICY` | Eviction policy | `allkeys-lru` |
| `CONTEXT_STORE_TTL` | Default TTL in seconds | `3600` |

### Mem0 Semantic Memory

| Variable | Description | Default |
|----------|-------------|---------|
| `MEM0_URL` | Mem0 service URL (self-hosted) | - |
| `MEM0_API_KEY` | Mem0 cloud API key | - |
| `MEM0_AGENT_ID` | Agent/user ID for memory scoping | - |
| `MEM0_ORG_ID` | Organization ID (optional) | - |

### Cohere Compass (RAG)

| Variable | Description | Default |
|----------|-------------|---------|
| `VECTOR_PROVIDER` | Provider: `memory`, `cohere_compass` | `memory` |
| `COHERE_COMPASS_URL` | Compass server URL | - |
| `COHERE_COMPASS_API_KEY` | Compass API key | - |
| `COHERE_COMPASS_INDEX_NAME` | Index name | - |
| `COHERE_COMPASS_PARSER_URL` | Parser service URL (optional) | - |
| `COHERE_COMPASS_PARSER_API_KEY` | Parser API key (optional) | - |
| `VECTOR_VERIFY_SSL` | Verify TLS certificates for remote vector calls | `true` |

**Remote providers (Compass/custom HTTP) require:** `VECTOR_HOST` (or `COHERE_COMPASS_URL`) **and** `VECTOR_API_KEY` (or `COHERE_COMPASS_API_KEY`). Missing values raise a configuration error at service initialization. The in-memory backend remains default and is namespace-isolated per `VECTOR_NAMESPACE`.

### Secret Management (Vault)

| Variable | Description | Default |
|----------|-------------|---------|
| `VAULT_ADDR` | HashiCorp Vault URL (standard naming) | - |
| `VAULT_TOKEN` | Vault authentication token | - |
| `VAULT_MOUNT_POINT` | Vault KV mount point name | `secret` |

### Observability

| Variable | Description | Default |
|----------|-------------|---------|
| `AO_ENABLE_TRACING` | Enable OpenTelemetry tracing | `false` |
| `AO_TRACE_SERVICE` | Service name for traces | `agentorchestrator` |
| `LOG_LEVEL` | Logging level | `INFO` |

Note: ObservabilityService currently wraps standard logging and tracing hooks;
add your own OpenTelemetry/metric backend in `services/observability.py` as needed.

### Summarizer

| Variable | Description | Default |
|----------|-------------|---------|
| `SUMMARIZER_MAX_TOKENS` | Max tokens for summaries | `4000` |
| `SUMMARIZER_CHUNK_SIZE` | Chunk size for splitting | `2000` |
| `SUMMARIZER_CHUNK_OVERLAP` | Overlap between chunks | `200` |
| `SUMMARIZER_STRATEGY` | Strategy: `stuff`, `map_reduce`, `refine` | `map_reduce` |

---

## License

MIT
