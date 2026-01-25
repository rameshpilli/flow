# Feature Examples & Patterns

> Concrete examples showing how to use AgentOrchestrator patterns.
> For full implementations, see `agentorchestrator/examples/`.

---

## 1. Financial Deep Research Agent

**What it does**: Multi-stage research with Refinitiv news, SEC filings, and earnings analysis.

**Full implementation**: [`examples/financial_research_agent.py`](../examples/financial_research_agent.py)

### Quick Start
```python
from agentorchestrator.examples.financial_research_agent import (
    FinancialResearchAgent,
)

# Create agent (connects to Refinitiv, SEC, Earnings MCP servers)
agent = FinancialResearchAgent()

# Run deep research
report = await agent.research(
    topic="Analyze Tesla's competitive position in the EV market",
    focus_areas=["market share", "technology", "financials"],
    depth="comprehensive",
)

# Results include:
print(report.executive_summary)
for finding in report.key_findings:
    print(f"- [{finding.category}] {finding.finding} ({finding.confidence:.0%})")
print(f"Sources: {len(report.sources)} from news, SEC, earnings")
```

### With Persistent Memory (mem0)
```python
from app import MemoryStoreClient
from agentorchestrator.squad.storage import Mem0Memory

# Connect to corporate mem0
mem0 = MemoryStoreClient(
    base_url="https://mem0.cfk.devfg.rbc.com",
    agent_id="research-agent-001"
)

# Agent remembers past research
agent = FinancialResearchAgent().with_memory(Mem0Memory(client=mem0))

# First research session
await agent.research("Tesla EV market analysis")

# Later session - agent recalls previous research
await agent.research("Compare Tesla to Rivian")
# Agent: "Based on my previous Tesla analysis..."
```

### Stream Research Progress
```python
async for event in agent.research_stream("Impact of AI on banking"):
    match event["step"]:
        case "decompose_question":
            print(f"📝 Breaking into sub-questions...")
        case "gather_news":
            print(f"📰 Searching Refinitiv news...")
        case "gather_sec":
            print(f"📋 Fetching SEC filings...")
        case "analyze_findings":
            print(f"🔍 Analyzing {event['finding_count']} findings...")
        case "complete":
            print(f"✅ Report ready!")
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
MEM0_URL=https://mem0.cfk.devfg.rbc.com
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
# Supervisor calls agents, but no explicit handoff protocol
supervisor = SupervisorAgent(team=[agent_a, agent_b])
result = await supervisor.process_message(query)
```

### After (With Handoff Protocol)
```python
from agentorchestrator.squad import FunctionAgent, AgentWorkflow

# Define agents with explicit handoff permissions
research_agent = FunctionAgent(
    name="researcher",
    description="Searches for information",
    tools=[web_search, doc_search],
    can_handoff_to=["writer", "user"],  # Explicit handoff targets
)

writer_agent = FunctionAgent(
    name="writer",
    description="Writes reports from research",
    tools=[format_report],
    can_handoff_to=["reviewer", "user"],
)

reviewer_agent = FunctionAgent(
    name="reviewer",
    description="Reviews and improves content",
    tools=[grammar_check, fact_check],
    can_handoff_to=["user"],  # Final step - returns to user
)

# Create workflow with handoff orchestration
workflow = AgentWorkflow(
    agents=[research_agent, writer_agent, reviewer_agent],
    initial_agent="researcher",
)

# Execute - agents hand off automatically based on task completion
async for event in workflow.run("Write a report on Tesla's EV market share"):
    if event.type == "handoff":
        print(f"🔄 {event.from_agent} → {event.to_agent}")
        print(f"   Context: {event.context_summary}")
    elif event.type == "agent_response":
        print(f"📝 {event.agent}: {event.message[:100]}...")
    elif event.type == "final":
        print(f"✅ Final report ready")

# Output:
# 🔄 researcher → writer
#    Context: Found 15 sources on Tesla EV market share...
# 🔄 writer → reviewer
#    Context: Draft report with 3 sections...
# 🔄 reviewer → user
#    Context: Final reviewed report with 2 corrections...
# ✅ Final report ready
```

### Handoff with Context Transfer
```python
# Agent can pass specific context when handing off
class ResearchAgent(FunctionAgent):
    async def process(self, query, ctx):
        findings = await self.search(query)

        # Explicit handoff with context
        return await self.handoff(
            to_agent="writer",
            context={
                "findings": findings,
                "sources": self.sources,
                "key_points": self.extract_key_points(findings),
            },
            message="Research complete. Please write a summary.",
        )
```

---

## 3. ReAct Agent Pattern (flow-mly)

**What it does**: Industry-standard Thought → Action → Observation reasoning loop.

### Before (Current State)
```python
# Tools execute but no visible reasoning trace
agent = LLMGatewayAgent(tools=[calculator, search])
result = await agent.process_message("What is 15% of Apple's $383B revenue?")
```

### After (With ReAct Pattern)
```python
from agentorchestrator.patterns import ReActAgent

agent = ReActAgent(
    name="financial-analyst",
    tools=[web_search, calculator, stock_lookup],
    max_iterations=10,
    verbose=True,  # Show reasoning trace
)

# Run with visible reasoning
async for step in agent.run("What is 15% of Apple's 2025 revenue?"):
    print(f"[{step.type}] {step.content}")

# Output:
# [THOUGHT] I need to find Apple's 2025 revenue first
# [ACTION] web_search("Apple 2025 annual revenue")
# [OBSERVATION] Apple reported $412 billion in revenue for FY2025
# [THOUGHT] Now I can calculate 15% of $412 billion
# [ACTION] calculator("412 * 0.15")
# [OBSERVATION] 61.8
# [THOUGHT] I have the answer
# [FINAL] 15% of Apple's 2025 revenue ($412B) is $61.8 billion

# Access the full reasoning trace
print(agent.reasoning_trace)
# [
#   {"type": "thought", "content": "I need to find..."},
#   {"type": "action", "tool": "web_search", "input": "Apple 2025..."},
#   {"type": "observation", "content": "Apple reported..."},
#   ...
# ]
```

### ReAct with Reflection
```python
# Add self-critique after each iteration
agent = ReActAgent(
    tools=[...],
    enable_reflection=True,
    reflection_prompt="Am I making progress? Should I try a different approach?",
)

async for step in agent.run(query):
    if step.type == "REFLECTION":
        print(f"🤔 Self-critique: {step.content}")
```

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
from agentorchestrator.events import StartEvent, StopEvent, Event
from agentorchestrator.workflow import Workflow, step

# Define custom events
class ResearchComplete(Event):
    findings: list[str]
    needs_more: bool

class WriteComplete(Event):
    draft: str
    quality_score: float

# Steps subscribe to and emit events
class ResearchWorkflow(Workflow):

    @step
    async def start(self, event: StartEvent) -> ResearchComplete:
        """Initial research step"""
        findings = await self.search(event.query)
        return ResearchComplete(
            findings=findings,
            needs_more=len(findings) < 5
        )

    @step
    async def maybe_more_research(self, event: ResearchComplete) -> ResearchComplete | WriteComplete:
        """Conditional: do more research or proceed to writing"""
        if event.needs_more:
            # Loop back - do more research
            more = await self.deep_search(event.findings)
            return ResearchComplete(findings=more, needs_more=False)
        else:
            # Proceed to writing
            draft = await self.write(event.findings)
            return WriteComplete(draft=draft, quality_score=0.8)

    @step
    async def review(self, event: WriteComplete) -> StopEvent:
        """Final review"""
        if event.quality_score < 0.9:
            # Improve and re-emit (loop)
            improved = await self.improve(event.draft)
            return WriteComplete(draft=improved, quality_score=0.95)
        return StopEvent(result=event.draft)

# Run with event streaming
workflow = ResearchWorkflow()
async for event in workflow.stream("Research AI trends"):
    print(f"Event: {event.__class__.__name__}")
    # Event: StartEvent
    # Event: ResearchComplete (needs_more=True)
    # Event: ResearchComplete (needs_more=False)  <- loop happened
    # Event: WriteComplete (quality_score=0.8)
    # Event: WriteComplete (quality_score=0.95)   <- improvement loop
    # Event: StopEvent
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

agent = LLMGatewayAgent(tools=[my_search_tool])
```

### After (With Tool Registry)
```python
from agentorchestrator.tools import ToolRegistry, get_tool

# Discover available tools
registry = ToolRegistry()
print(registry.list_tools())
# ['web_search', 'tavily_search', 'file_read', 'file_write',
#  'sql_query', 'python_repl', 'vector_search', 'calculator', ...]

print(registry.search("search"))
# [
#   {"name": "web_search", "description": "Search the web using..."},
#   {"name": "tavily_search", "description": "AI-powered search..."},
#   {"name": "vector_search", "description": "Semantic search over..."},
# ]

# Get and use built-in tools
web_search = get_tool("web_search")
calculator = get_tool("calculator")
sql = get_tool("sql_query", connection_string="postgresql://...")

# Create agent with registry tools
agent = FunctionAgent(
    tools=[
        get_tool("web_search"),
        get_tool("calculator"),
        get_tool("python_repl"),
    ]
)

# Or use tool bundles
from agentorchestrator.tools.bundles import research_tools, data_tools

agent = FunctionAgent(
    tools=research_tools + data_tools
)
```

### Register Custom Tools
```python
from agentorchestrator.tools import tool, ToolRegistry

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
print("stock_price" in registry.list_tools())  # True
```

---

## 6. Conversation Memory Patterns (flow-01k)

**What it does**: Summary, window, entity, and semantic memory strategies.

### With Your Corporate mem0 Integration

```python
from app import MemoryStoreClient
from agentorchestrator.memory import (
    Mem0Memory,
    WindowMemory,
    SummaryMemory,
    EntityMemory,
    CompositeMemory,
)

# Connect to your corporate mem0
mem0_client = MemoryStoreClient(
    base_url="https://mem0.cfk.devfg.rbc.com",
    agent_id="trading-agent-001"
)

# Wrap in our memory interface
memory = Mem0Memory(client=mem0_client)

# Use with an agent
agent = FunctionAgent(
    name="trading-assistant",
    memory=memory,
    tools=[execute_trade, get_portfolio],
)

# Conversations are automatically stored and retrieved
result = await agent.process_message(
    "Execute buy order for 1000 shares of AAPL at $150",
    user_id="trader-123",
    session_id="session-456",
)

# Later - memory is automatically searched for context
result = await agent.process_message(
    "What trades did I execute today?",
    user_id="trader-123",
    session_id="session-789",  # Different session!
)
# Agent recalls: "You executed a buy order for 1000 AAPL at $150"
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
        base_url="https://mem0.cfk.devfg.rbc.com",
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
from agentorchestrator.squad import LLMGatewayAgent
from agentorchestrator.memory import Mem0Memory
from app import MemoryStoreClient

# Your corporate memory store
mem0 = MemoryStoreClient(
    base_url="https://mem0.cfk.devfg.rbc.com",
    agent_id="client-advisor-001"
)

# Agent with persistent memory
agent = LLMGatewayAgent(
    name="ClientAdvisor",
    memory=Mem0Memory(client=mem0),
    system_prompt="You are a financial advisor. Use conversation history to personalize advice.",
)

# Session 1: Client discusses their portfolio
await agent.process_message(
    "I'm concerned about my tech-heavy portfolio",
    user_id="client-abc"
)
# Memory stores: "Client concerned about tech concentration"

# Session 2 (days later): Agent remembers context
await agent.process_message(
    "What should I do about the market volatility?",
    user_id="client-abc"
)
# Agent retrieves memory and responds:
# "Given your concern about tech concentration we discussed,
#  you might consider diversifying into defensive sectors..."
```

---

## 7. Human-in-the-Loop (flow-9hm) - Enhanced

### After Implementation

```python
from agentorchestrator.patterns import ApprovalWorkflow
from agentorchestrator.approval import SlackApprover, EmailApprover

# Define steps that require approval
@ao.step(name="prepare_trade")
async def prepare_trade(ctx):
    return {"ticker": "AAPL", "shares": 10000, "price": 150}

@ao.approval_step(
    name="approve_trade",
    deps=["prepare_trade"],
    approvers=[
        SlackApprover(channel="#trade-approvals"),
        EmailApprover(to="risk@company.com"),
    ],
    timeout_hours=24,
    on_timeout="reject",
)
async def approve_trade(ctx, approval_result):
    if approval_result.approved:
        return await execute_trade(ctx.get("prepare_trade"))
    else:
        return {"status": "rejected", "reason": approval_result.reason}

# Run workflow
result = await ao.launch("trade_workflow", {"order": order_data})

# Slack message sent:
# 🔔 Trade Approval Required
# Ticker: AAPL | Shares: 10000 | Value: $1.5M
# [Approve] [Reject] [Request More Info]
```

---

## Complete Example: Research Agent with Memory

Putting it all together with your mem0 integration:

```python
from agentorchestrator import AgentOrchestrator
from agentorchestrator.patterns import DeepResearchAgent, ReActAgent
from agentorchestrator.memory import Mem0Memory, CompositeMemory, EntityMemory
from agentorchestrator.tools import get_tool, ToolRegistry
from app import MemoryStoreClient

# Setup memory with your corporate mem0
mem0_client = MemoryStoreClient(
    base_url="https://mem0.cfk.devfg.rbc.com",
    agent_id="research-agent-001"
)

memory = CompositeMemory([
    EntityMemory(entity_types=["company", "person", "product"]),
    Mem0Memory(client=mem0_client),
])

# Create research agent with ReAct reasoning
agent = DeepResearchAgent(
    name="market-researcher",
    reasoning_pattern="react",  # Use ReAct for visible reasoning
    tools=[
        get_tool("web_search"),
        get_tool("sec_filings"),
        get_tool("news_search"),
    ],
    memory=memory,
    can_handoff_to=["report_writer", "user"],
)

# Run research with full observability
async for event in agent.research_stream("Analyze Tesla's competitive position"):
    match event.type:
        case "thought":
            print(f"💭 {event.content}")
        case "action":
            print(f"🔧 Using {event.tool}: {event.input}")
        case "observation":
            print(f"👁️ Found: {event.content[:100]}...")
        case "memory_recall":
            print(f"🧠 Recalled: {event.memory}")
        case "handoff":
            print(f"🔄 Handing off to {event.to_agent}")
        case "final":
            print(f"✅ Research complete")
            print(event.report)

# Output:
# 💭 I should first check what we already know about Tesla
# 🧠 Recalled: Previous research on Tesla's EV market share from last week
# 💭 I need to find recent competitive analysis
# 🔧 Using web_search: "Tesla competitors 2026 market analysis"
# 👁️ Found: Rivian and Lucid gained market share while Tesla...
# 🔧 Using sec_filings: "Tesla 10-K 2025"
# 👁️ Found: Tesla reported 1.8M deliveries with 23% margin...
# 💭 I have enough information to synthesize findings
# 🔄 Handing off to report_writer
# ✅ Research complete
# [Full report with citations]
```

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
from agentorchestrator.examples.financial_research_agent import FinancialResearchAgent
from agentorchestrator.squad.context import ContextIsolationManager

# The financial research agent now uses context isolation internally
agent = FinancialResearchAgent(
    config=ResearchConfig(
        # Context isolation is enabled by default for multi-agent steps
        enable_context_isolation=True,
    )
)

# News, SEC, and Earnings agents each get isolated contexts
# Their huge responses don't pollute each other
# Coordinator aggregates only the relevant findings
report = await agent.research("Analyze Tesla's competitive position")
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
| **Deep Research** | Manual multi-step orchestration | `DeepResearchAgent.research(topic)` - one line |
| **Handoffs** | Supervisor controls everything | Agents explicitly delegate: `A → B → C → User` |
| **ReAct** | Black-box tool execution | Visible `Thought → Action → Observation` trace |
| **Events** | Fixed DAG dependencies | Dynamic loops, branches, streaming events |
| **Tools** | Define every tool manually | `get_tool("web_search")` from registry |
| **Memory** | Basic chat history | Entity tracking, semantic search, cross-session recall |

All features integrate with your existing corporate infrastructure (mem0, LLM Gateway, etc.).
