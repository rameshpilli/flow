# Feature Examples & Patterns

> Concrete examples showing how to use AgentOrchestrator patterns.
> For full implementations, see `agentorchestrator/examples/`.

## Implementation Status

| Feature | Status | Import |
|---------|--------|--------|
| **Squad** | ✅ Implemented | `from agentorchestrator.squad import Squad` |
| **SupervisorAgent** | ✅ Implemented | `from agentorchestrator.squad import SupervisorAgent` |
| **FunctionAgent** | ✅ Implemented | `from agentorchestrator.squad import FunctionAgent` |
| **Context Isolation** | ✅ Implemented | `from agentorchestrator.squad import IsolationLevel` |
| **Middleware Suite** | ✅ Implemented | `from agentorchestrator.middleware import *` |
| **Pydantic State** | ✅ Implemented | `from agentorchestrator import Context` |
| **Event-Driven Workflows** | ✅ Implemented | `from agentorchestrator.core.event_bus import EventBus` |
| **Financial Research** | ✅ Implemented | See examples/financial_research_agent.py |
| **ReAct Pattern** | ✅ Implemented | `from agentorchestrator.agents.react import ReActAgent` |
| **Tool Registry** | ✅ Implemented | `from agentorchestrator.agents.tools import ToolRegistry` |
| **Swarm** | 🚧 Planned | Coming soon |
| **AgentNetwork** | 🚧 Planned | Coming soon |

> **Note**: Features marked 🚧 Planned show aspirational patterns.
> Check the import works before using any feature.

---

## 1. Squad Pattern ✅

**What it does**: Coordinate a team of specialist agents with a supervisor.

```python
from agentorchestrator.squad import (
    Squad,
    SquadOptions,
    LLMGatewayAgent,
    LLMGatewayAgentOptions,
)

# Create specialist agents
tech_agent = LLMGatewayAgent(LLMGatewayAgentOptions(
    name="TechAgent",
    description="Handles technical questions",
))
finance_agent = LLMGatewayAgent(LLMGatewayAgentOptions(
    name="FinanceAgent",
    description="Handles financial questions",
))

# Create supervisor (lead agent)
lead = LLMGatewayAgent(LLMGatewayAgentOptions(
    name="Supervisor",
    description="Coordinates team to answer complex questions",
))

# Create squad
squad = Squad(
    supervisor=lead,
    agents=[tech_agent, finance_agent],
    options=SquadOptions(trace=True),
)

# Execute
result = await squad.run("Analyze tech stocks for Q1")
print(result.content)
```

---

## 2. Type-Safe State Management with Pydantic ✅

**What it does**: Use Pydantic models for validated, type-safe workflow state with IDE autocomplete.

**Full implementation**: [`examples/pydantic_state.py`](../examples/pydantic_state.py)

### Basic Usage

```python
from pydantic import BaseModel, Field
from agentorchestrator import AgentOrchestrator, Context
from agentorchestrator.core.context import ChainContext

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

# Create context with state model
ctx = ChainContext("req_123", state_model=PipelineState)
```

### With Validation

```python
class ValidatedState(BaseModel):
    progress: int = Field(default=0, ge=0, le=100)  # 0-100
    email: str = Field(
        default="user@example.com",
        pattern=r"^[\w\.-]+@[\w\.-]+\.\w+$"
    )

ctx = ChainContext("req_1", state_model=ValidatedState)

# Invalid updates raise ValidationError
try:
    async with ctx.edit_state() as state:
        state.progress = 150  # Exceeds max!
except ValidationError:
    print("State unchanged due to validation")
```

**Benefits**:
- ✅ IDE autocomplete and type hints
- ✅ Automatic validation via Pydantic
- ✅ Atomic updates with rollback on error
- ✅ Thread-safe concurrent access

**See also**: [Context Management Guide](CONTEXT_MANAGEMENT.md#0-type-safe-state-management-new)

---

## 3. Event-Driven Workflows ✅

**What it does**: Event-driven execution with event handlers and pub/sub via EventBus (Redis or in-memory).

**Full implementation**: [`examples/event_workflow.py`](../examples/event_workflow.py)  
**Documentation**: [Event Workflows Guide](understanding/EVENT_WORKFLOWS.md)

### Basic Usage

```python
from agentorchestrator import AgentOrchestrator
from agentorchestrator.core.event_bus import Event
from agentorchestrator.core.context import Context

ao = AgentOrchestrator()

# Define event handlers
@ao.event_handler("ResearchTask")
async def worker(ctx: Context, event: Event):
    query = event.payload["query"]
    finding = f"finding for {query}"
    return Event(type="Finding", payload={"query": query, "text": finding})

@ao.event_handler("Finding")
async def collector(ctx: Context, event: Event):
    print(f"Found: {event.payload}")
    return None  # Terminal event

# Run event loop
async def main():
    ctx = ChainContext("req_1")
    
    # Publish events
    await ao.publish("ResearchTask", {"query": "AI trends"})
    await ao.publish("ResearchTask", {"query": "ML models"})
    
    # Run until no more events
    await ao.run_event_loop(ctx)
```

### With Redis Backend

```python
from agentorchestrator.core.event_bus import get_event_bus

# Use Redis for distributed event bus
bus = get_event_bus(backend="redis", redis_url="redis://localhost:6379")

ao = AgentOrchestrator(event_bus=bus)
# ... rest of the code same as above
```

**Features**:
- ✅ Event handlers with `@ao.event_handler()`
- ✅ Event pub/sub with `EventBus`
- ✅ Redis or in-memory backend
- ✅ Event loop with `ao.run_event_loop()`
- ✅ Type-safe event payloads

---

## 4. Financial Deep Research Agent ✅

**What it does**: Multi-stage research with Refinitiv news, SEC filings, and earnings analysis.

**Full implementation**: [`examples/financial_research_agent.py`](../examples/financial_research_agent.py)

> **Note**: The `FinancialResearchAgent` API is implemented in `examples/` and
> uses the chain execution pattern under the hood. See the example file for
> working code and configuration details.

### Using the Chain Pattern (Implemented)
```python
from agentorchestrator import AgentOrchestrator
from agentorchestrator.examples.financial_research_agent import register_financial_research_chain

ao = AgentOrchestrator(name="research")
register_financial_research_chain(ao)

result = await ao.launch("financial_research_chain", {
    "company": "Tesla",
    "topic": "EV market position",
})
```

### High-level API (Implemented)
```python
from agentorchestrator.examples.financial_research_agent import (
    FinancialResearchAgent,
)

agent = FinancialResearchAgent()
report = await agent.research(
    topic="Analyze Tesla's competitive position in the EV market",
    focus_areas=["market share", "technology", "financials"],
    depth="comprehensive",
)
```

### Architecture
```
┌─────────────────────────────────────────────────────────────┐
│                Financial Research Agent                      │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  Step 1: Decompose Question                                 │
│  └─ LLM breaks topic into 3-5 focused sub-questions        │
│                                                              │
│  Step 2: Gather Data (Parallel)                             │
│  ├─ RefinitivNewsAgent → news articles, sentiment          │
│  ├─ SECFilingsAgent → 10-K, 10-Q, 8-K filings             │
│  └─ EarningsAgent → call transcripts, guidance            │
│                                                              │
│  Step 3: Analyze Findings                                   │
│  └─ LLM extracts key findings with confidence scores       │
│                                                              │
│  Step 4: Generate Report                                    │
│  └─ Executive summary, findings, sources, methodology      │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Environment Variables
```bash
# MCP Servers
REFINITIV_MCP_URL=http://refinitiv-mcp:3001
SEC_MCP_URL=http://sec-mcp:3002
EARNINGS_MCP_URL=http://earnings-mcp:3003
REFINITIV_API_KEY=your_api_key

# LLM Gateway
LLM_SERVER_URL=https://llm-gateway/v1/chat/completions
LLM_MODEL_NAME=claude-sonnet-4

# Memory (optional)
MEM0_URL=https://mem0.your-company.com
```

### Context Management for Large Responses

When multiple agents return large responses (e.g., 100+ news articles, full SEC filings),
the combined context can overflow LLM token limits. The financial research agent uses
a multi-layered strategy to handle this:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    Context Management Pipeline                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Layer 1: Source-Level Capping (cap_per_source)                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ • Limits items per data source (news, SEC, earnings)                │   │
│  │ • Preserves balance across sources (not just first N)               │   │
│  │ • Tracks metadata: "kept 20 of 150, omitted 130 lower-relevance"   │   │
│  │ • NEVER blindly truncates - always records what was omitted        │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                              ↓                                              │
│  Layer 2: Automatic Summarization (SummarizerMiddleware)                    │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ • Triggers when step output > threshold (e.g., 8K tokens)           │   │
│  │ • Uses MAP_REDUCE strategy:                                         │   │
│  │   1. Split into chunks                                              │   │
│  │   2. Summarize each chunk in parallel                               │   │
│  │   3. Combine summaries into final summary                           │   │
│  │ • Domain-specific prompts for financial content                     │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                              ↓                                              │
│  Layer 3: Offloading (OffloadMiddleware)                                    │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ • Large payloads (>100KB) stored in Redis                           │   │
│  │ • Context keeps lightweight reference (ContextRef)                  │   │
│  │ • Full data always recoverable: await store.retrieve(ref)           │   │
│  │ • 100% data preservation - NEVER loses data                         │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                              ↓                                              │
│  Layer 4: Token Budget Management (TokenManagerMiddleware)                  │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ • Tracks total context tokens across all steps                      │   │
│  │ • Warns at 80%, auto-compresses at 100%                             │   │
│  │ • Prioritizes recent/important context over old                     │   │
│  │ • Auto-triggers summarization on oldest steps first                 │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### Configuration
```python
from agentorchestrator.examples.financial_research_agent import ResearchConfig

config = ResearchConfig(
    # Context management settings
    max_context_tokens=100_000,      # Total budget for analysis
    summarization_threshold=8_000,   # Summarize outputs over this
    offload_threshold_bytes=100_000, # Offload payloads over 100KB
    max_items_per_source=20,         # Cap items per data source
    enable_auto_summarization=True,
    enable_auto_offload=True,
)

agent = FinancialResearchAgent(config)
```

#### Using Cap Utilities Directly
```python
from agentorchestrator.middleware.offload import (
    cap_items_with_metadata,
    cap_per_source,
)

# Cap by relevance, preserve metadata
articles, meta = cap_items_with_metadata(
    all_articles,
    max_items=20,
    sort_key=lambda x: x.get("relevance", 0),
    sort_reverse=True,
)
# meta = {"original_count": 150, "kept_count": 20, "omitted_count": 130, ...}

# Cap per source for balanced representation
filings, meta = cap_per_source(
    all_filings,
    source_field="ticker",
    max_per_source=5,
    total_max=20,
)
# Ensures each company gets fair representation
```

#### Summarization Strategies
```python
from agentorchestrator.middleware.summarizer import (
    SummarizationStrategy,
    LangChainSummarizer,
    create_gateway_summarizer,
)

# STUFF: Single LLM call (small docs only)
# MAP_REDUCE: Parallel chunks → combine (best for large docs)
# REFINE: Sequential refinement (best quality, slowest)

summarizer = create_gateway_summarizer(
    strategy=SummarizationStrategy.MAP_REDUCE,
    chunk_size=2000,
)

# Register domain-specific prompts
LangChainSummarizer.register_domain_prompts(
    domain="financial_news",
    map_prompt="Summarize this financial news, preserving key metrics...",
    reduce_prompt="Combine summaries into a cohesive analysis...",
)
```

---

## 2. Agent Handoffs (flow-5t6)

**What it does**: Explicit agent-to-agent delegation with context transfer.

### Before (Current State)
```python
from agentorchestrator.squad import (
    SupervisorAgent,
    SupervisorAgentOptions,
    LLMGatewayAgent,
    LLMGatewayAgentOptions,
)

# Supervisor coordinates a team (no explicit handoff protocol)
lead = LLMGatewayAgent(LLMGatewayAgentOptions(
    name="Supervisor",
    description="Coordinates team",
))
agent_a = LLMGatewayAgent(LLMGatewayAgentOptions(
    name="AgentA",
    description="Handles topic A",
))
agent_b = LLMGatewayAgent(LLMGatewayAgentOptions(
    name="AgentB",
    description="Handles topic B",
))

supervisor = SupervisorAgent(SupervisorAgentOptions(
    lead_agent=lead,
    team=[agent_a, agent_b],
))

result = await supervisor.process_request(
    input_text=query,
    user_id="user-1",
    session_id="session-1",
    chat_history=[],
)
```

### After (With Handoff Protocol)
```python
from agentorchestrator.squad import FunctionAgent, FunctionAgentOptions

# Define agents with explicit handoff permissions
research_agent = FunctionAgent(FunctionAgentOptions(
    name="Researcher",
    description="Searches for information",
    can_handoff_to=["Writer", "User"],
))

writer_agent = FunctionAgent(FunctionAgentOptions(
    name="Writer",
    description="Writes reports from research",
    can_handoff_to=["User"],
))

# Explicit handoff with context
handoff = await research_agent.handoff(
    to_agent="Writer",
    context={
        "findings": findings,
        "sources": sources,
    },
    message="Research complete. Please write a summary.",
)

# Orchestrator routes to handoff.to_agent using handoff.context/message
```

---

## 3. ReAct Agent Pattern (flow-mly)

**What it does**: Industry-standard Thought → Action → Observation reasoning loop.

### Before (LLM Gateway Agent)
```python
from agentorchestrator.squad import LLMGatewayAgent, LLMGatewayAgentOptions

agent = LLMGatewayAgent(LLMGatewayAgentOptions(
    name="financial-analyst",
    description="Answers finance questions",
))
result = await agent.process_request(
    input_text="What is 15% of Apple's $383B revenue?",
    user_id="user-1",
    session_id="session-1",
    chat_history=[],
)
print(result.content[0]["text"])
```

### After (With ReAct Pattern)
```python
from agentorchestrator.agents.react import ReActAgent, ReActConfig, Tool
from agentorchestrator.agents.tools import get_default_registry
from agentorchestrator.services.llm_gateway import LLMGatewayClient

def web_search(query: str) -> str:
    return f"Results for '{query}'..."

llm = LLMGatewayClient.from_env()
registry = get_default_registry()
calc_def = registry.get("calculate")

agent = ReActAgent(
    llm_client=llm,
    tools=[
        Tool("web_search", "Search the web", web_search),
        Tool(calc_def.name, calc_def.description, calc_def.func),
    ],
    config=ReActConfig(max_iterations=10),
)

result = await agent.run("What is 15% of Apple's 2025 revenue?")
print(result.final_answer)
print(result.thought_trace)
```

> **Note**: `ReActAgent.run()` returns a `ReActResult` (not a stream). If you
> want step-level self-critique, apply `ReflectionMiddleware` to a chain step
> that calls the agent.

---

## 4. Event-Driven Execution (flow-2u5)

**What it does**: Beyond DAG - flexible loops, branches, and streaming events.

### Before (Current State)
```python
# DAG with fixed dependencies
@ao.step(name="a")
async def step_a(ctx): ...

@ao.step(name="b", deps=["a"])
async def step_b(ctx): ...

# Can't easily do: loops, conditional branches, dynamic routing
```

### After (With Event-Driven Execution)
```python
from agentorchestrator import AgentOrchestrator
from agentorchestrator.core.event_bus import Event

ao = AgentOrchestrator(name="research_events")
final_report = {}

async def search_sources(query: str) -> list[str]:
    return [f"Finding about {query}"]

async def write_report(findings: list[str]) -> str:
    return f"Draft report with {len(findings)} findings"

@ao.event_handler("ResearchTask")
async def research(ctx, event: Event):
    findings = await search_sources(event.payload["query"])
    needs_more = len(findings) < 2
    if needs_more:
        return Event(type="ResearchTask", payload=event.payload)
    return Event(type="WriteDraft", payload={"findings": findings})

@ao.event_handler("WriteDraft")
async def write(ctx, event: Event):
    draft = await write_report(event.payload["findings"])
    final_report["draft"] = draft
    return Event(type="Complete", payload={"draft": draft})

result = await ao.run_event_loop(
    seed_events=[Event(type="ResearchTask", payload={"query": "Research AI trends"})],
    stop_when=lambda e, ctx: e.type == "Complete",
)

print(final_report["draft"])
```

---

## 5. Tool Registry (flow-yp7)

**What it does**: Built-in tools + easy discovery, like LlamaHub.

### Before (Current State)
```python
# Define tools manually every time
def my_search_tool(query: str) -> str:
    # implement search...
    pass

from agentorchestrator.squad import LLMGatewayAgent, LLMGatewayAgentOptions
from agentorchestrator.squad.types import AgentTools, AgentTool

tools = AgentTools(tools=[
    AgentTool(name="search", description="Search the web", func=my_search_tool),
])

agent = LLMGatewayAgent(LLMGatewayAgentOptions(
    name="tool-agent",
    description="Uses tools",
    tool_config={"tool": tools},
))
```

### After (With Tool Registry)
```python
from agentorchestrator.agents.tools import get_default_registry, ToolCategory

# Discover available tools
registry = get_default_registry()
print(registry.list_all())
# ['calculate', 'get_current_time', 'text_length']

utility_tools = registry.find_by_category(ToolCategory.UTILITY)
print([t.name for t in utility_tools])
# ['get_current_time', 'text_length']

# Execute a built-in tool
result = await registry.execute("calculate", expression="412 * 0.15")
print(result.result)  # "61.8"
```

### Register Custom Tools
```python
from agentorchestrator.agents.tools import tool, ToolRegistry

@tool(
    name="stock_price",
    description="Get current stock price for a ticker symbol",
    tags=["finance", "stocks"],
)
def get_stock_price(ticker: str) -> dict:
    """
    Args:
        ticker: Stock symbol like AAPL, GOOGL

    Returns:
        dict with price, change, volume
    """
    return {"price": 150.0, "change": 2.5, "volume": 1000000}

# Auto-registered and discoverable
registry = ToolRegistry()
print(registry.has("stock_price"))  # True
```

---

## 6. Conversation Memory Patterns (flow-01k)

**What it does**: Summary, window, entity, and semantic memory strategies.

### With Your Corporate mem0 Integration

```python
from app import MemoryStoreClient
from agentorchestrator.services import (
    Mem0Memory,
    CompositeMemory,
)
# Note: WindowMemory, SummaryMemory, EntityMemory are aspirational patterns
# not yet implemented. Use Mem0Memory for semantic memory.

# Connect to your corporate mem0
mem0_client = MemoryStoreClient(
    base_url="https://mem0.your-company.com",
    agent_id="trading-agent-001"
)

# Wrap in our memory interface
memory = Mem0Memory(client=mem0_client, default_user_id="trader-123")

# Store and recall semantic memory
await memory.add("Executed buy order for 1000 shares of AAPL at $150")
results = await memory.search("What trades did I execute today?")
print(results[0].content)
```

### Memory Strategy Options

```python
# 1. Window Memory - Keep last N messages
memory = WindowMemory(window_size=10)

# 2. Summary Memory - Summarize older messages
memory = SummaryMemory(
    llm=llm_client,
    max_tokens=1000,
    summarize_after=20,  # Summarize after 20 messages
)

# 3. Entity Memory - Track entities mentioned
memory = EntityMemory(
    llm=llm_client,
    entity_types=["person", "company", "product", "trade"],
)

# Query: "What do we know about Apple?"
# Returns all Apple-related context from conversation history

# 4. Semantic Memory (mem0) - Vector search over memories
memory = Mem0Memory(
    client=MemoryStoreClient(
        base_url="https://mem0.your-company.com",
        agent_id="my-agent"
    )
)

# 5. Composite - Combine strategies
memory = CompositeMemory([
    WindowMemory(window_size=5),      # Recent context
    EntityMemory(llm=llm),            # Entity tracking
    Mem0Memory(client=mem0_client),   # Long-term semantic
])
```

### Memory in Agent Workflow

```python
from agentorchestrator import AgentOrchestrator
from agentorchestrator.middleware import MemoryLifecycleMiddleware, MemoryLifecycleConfig
from agentorchestrator.services import Mem0Memory
from app import MemoryStoreClient

ao = AgentOrchestrator(name="advisor")
mem0 = MemoryStoreClient(base_url="https://mem0.your-company.com", agent_id="client-advisor-001")

# Promote important step outputs to long-term memory
ao.use(MemoryLifecycleMiddleware(
    longterm_memory=Mem0Memory(client=mem0),
    config=MemoryLifecycleConfig(importance_threshold=0.8),
))
```

---

## 7. Human-in-the-Loop (flow-9hm) - Planned

> This feature is **not implemented yet**. The proposed API includes an
> `@ao.approval_step()` decorator and approver integrations (Slack/Email).
> Track progress under `flow-9hm`.

---

## Complete Example: Deep Research (Implemented)

For a full working pipeline (decompose → parallel research → synthesize → reflect),
see `examples/deep_research_agent.py`.

```bash
# Run the example module
python -m agentorchestrator.examples.deep_research_agent "Analyze Tesla's competitive position"
```

For a finance-specific, high-level API, see `examples/financial_research_agent.py`
and the `FinancialResearchAgent` class.

---

## 8. Context Isolation for Multi-Agent Systems (NEW)

**What it does**: Each agent operates in its own isolated context, preventing context pollution
and enabling clean result aggregation. This is the **gold standard** for scaling to 5-10+ agents.

**Implementation**: [`squad/context/`](../squad/context/)

### The Problem: Context Explosion

Without isolation, if a coordinator passes full history to each sub-agent:
```
N agents × full context = massive token usage + confused reasoning
```

Agent A's intermediate data accidentally influences Agent B. Context grows exponentially.

### The Solution: Manus-Style Context Isolation

Each agent gets its own namespace. Coordinator mediates all data sharing.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│              Coordinator Context (SupervisorAgent)                           │
│  ├─ request_id, user_query, execution_plan                                  │
└─────────────────────────────────────────────────────────────────────────────┘
                    │ Creates isolated namespaces
        ┌───────────┼───────────┐
        ↓           ↓           ↓
   ┌─────────┐ ┌─────────┐ ┌─────────┐
   │ Agent 1 │ │ Agent 2 │ │ Agent 3 │
   │Namespace│ │Namespace│ │Namespace│
   │         │ │         │ │         │
   │ - temp  │ │ - temp  │ │ - temp  │
   │ - data  │ │ - data  │ │ - data  │
   │ - result│ │ - result│ │ - result│
   └─────────┘ └─────────┘ └─────────┘
        │           │           │
        └───────────┴───────────┘
                    ↓
        ┌─────────────────────────┐
        │    ResultAggregator     │
        │ - Collect results       │
        │ - Detect conflicts      │
        │ - Synthesize/merge      │
        └─────────────────────────┘
                    ↓
              Final Response
```

### Basic Usage

```python
from agentorchestrator.squad.context import (
    ContextIsolationManager,
    ResultAggregator,
    AggregationStrategy,
    IsolationLevel,
)

# Supervisor creates isolation manager
isolation = ContextIsolationManager(coordinator_context=ctx)

# Create isolated namespaces for each team member
for agent in team:
    agent.namespace = isolation.create_namespace(
        agent_id=agent.id,
        isolation_level=IsolationLevel.FULL,  # Can't see other agents' data
    )

# Share request data with all agents
isolation.share_with_all("query", user_query)
isolation.share_with_all("user_id", user_id)

# Execute agents in parallel - each in isolated context
async with isolation.execute_parallel(team, process_agent, query) as results:
    for agent_id, result in results.items():
        print(f"{agent_id}: {result}")
```

### Agent Execution with Namespace

```python
async def process_agent(agent, query, namespace):
    """Each agent operates in its own namespace."""
    async with namespace:
        # Agent only sees:
        # 1. Explicitly shared data (query, user_id)
        # 2. Its own local data
        # 3. Nothing from other agents

        # Store intermediate work (invisible to others)
        namespace.set("raw_data", await agent.fetch_data(query))
        namespace.set("analysis", await agent.analyze(namespace.get("raw_data")))

        # Set final result for aggregation
        result = await agent.generate_response(namespace.get("analysis"))
        namespace.set_result(result, metadata={"confidence": 0.9})

        return result
```

### Result Aggregation

```python
from agentorchestrator.squad.context import ResultAggregator, AggregationStrategy

# Collect results from isolated namespaces
aggregator = ResultAggregator(strategy=AggregationStrategy.SYNTHESIZE)

for agent in team:
    aggregator.add_from_namespace(agent.id, agent.namespace)

# Aggregate with LLM synthesis
final = await aggregator.aggregate(llm=llm_client)

print(final.data)  # Synthesized response from all agents
print(final.confidence)  # Overall confidence
print(final.conflicts)  # Any disagreements between agents
```

### Aggregation Strategies

| Strategy | Description | Best For |
|----------|-------------|----------|
| `SYNTHESIZE` | LLM creates narrative from all results | Research, reports |
| `MERGE` | Deep merge dicts/lists | Structured data |
| `PRIORITIZE` | Select highest confidence result | Single-answer questions |
| `VOTE` | Majority voting | Discrete choices |
| `CHAIN` | Sequential refinement | Iterative improvement |
| `CONCAT` | Simple concatenation | Text segments |

### Selective Data Sharing

```python
# Share data from one agent to specific others (coordinator-mediated)
isolation.share_between(
    source_agent="researcher",
    key="findings",
    target_agents=["writer", "reviewer"],  # Only these can see it
)

# Agent can publish data for coordinator to share
async with namespace:
    namespace.publish("key_insight", important_finding)
    # Coordinator decides if/how to share with others
```

### Isolation Levels

```python
class IsolationLevel(Enum):
    FULL = "full"      # Only sees own data + explicitly shared keys
    PARTIAL = "partial" # Sees own data + all coordinator CHAIN data (read-only)
    NONE = "none"       # No isolation (legacy mode)
```

### Integration with Financial Research Agent

```python
from agentorchestrator.squad import LLMGatewayAgent, LLMGatewayAgentOptions
from agentorchestrator.squad.context import (
    ContextIsolationManager,
    ResultAggregator,
    AggregationStrategy,
)

# Build a team
team = [
    LLMGatewayAgent(LLMGatewayAgentOptions(
        name="Researcher",
        description="Gathers facts",
    )),
    LLMGatewayAgent(LLMGatewayAgentOptions(
        name="Writer",
        description="Drafts summaries",
    )),
]

ctx = ChainContext("ctx_1")
user_query = "Analyze Tesla's competitive position"
llm = LLMGatewayClient.from_env()

# Coordinator context + isolation manager
isolation = ContextIsolationManager(coordinator_context=ctx)
isolation.share_with_all("query", user_query)

async def process_agent(agent, query, namespace):
    return await agent.process_request(
        input_text=query,
        user_id="user-1",
        session_id="session-1",
        chat_history=[],
    )

async with isolation.execute_parallel(team, process_agent, user_query) as results:
    print(results)

# Aggregate results
aggregator = ResultAggregator(strategy=AggregationStrategy.SYNTHESIZE)
for agent in team:
    namespace = isolation.get_namespace(agent.id)
    if namespace:
        aggregator.add_result(agent.id, namespace.get_result())

final = await aggregator.aggregate(llm=llm)
```

### Benefits

| Aspect | Without Isolation | With Isolation |
|--------|-------------------|----------------|
| **Token Usage** | N × full context | N × focused context |
| **Reasoning** | Confused by irrelevant data | Clear, focused |
| **Scaling** | Breaks at 5+ agents | Linear scaling |
| **Debugging** | Hard to trace | Per-agent snapshots |
| **Security** | All data visible | Controlled sharing |

---

## Summary: What Changes

| Feature | Before | After |
|---------|--------|-------|
| **Deep Research** | Manual multi-step orchestration | Example chains in `examples/deep_research_agent.py` and `examples/financial_research_agent.py` |
| **Handoffs** | Supervisor controls everything | Agents explicitly delegate: `A → B → C → User` |
| **ReAct** | Black-box tool execution | Visible `Thought → Action → Observation` trace |
| **Events** | Fixed DAG dependencies | Dynamic loops, branches, streaming events |
| **Tools** | Define every tool manually | ToolRegistry + built-ins via `get_default_registry()` |
| **Memory** | Basic chat history | Semantic memory via `Mem0Memory` (window/entity patterns planned) |

All features integrate with your existing corporate infrastructure (mem0, LLM Gateway, etc.).
