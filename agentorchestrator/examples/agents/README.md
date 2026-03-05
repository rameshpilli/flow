# Agent Examples

Multi-agent orchestration patterns and coordination examples.

## Overview

AgentOrchestrator supports multiple agent patterns:

| Pattern | Description | Use Case |
|---------|-------------|----------|
| **ReAct** | Thought→Action→Observation reasoning loop | Complex problem solving |
| **Supervisor** | Central coordinator delegates to specialists | Research, analysis |
| **Squad** | Team of agents with shared context | Complex workflows |
| **Resilient** | Fault-tolerant agent wrapper | Production systems |
| **Function Agent** | Explicit handoffs between agents | Pipeline workflows |

## Examples

### 1. ReAct Agent (NEW)

Industry-standard reasoning pattern with tool use.

```python
from agentorchestrator.agents import ReActAgent, Tool, ToolRegistry

# Create a tool registry with built-in tools
registry = ToolRegistry()

@registry.tool("search", "Search the web for information")
async def search(query: str) -> str:
    # Your search implementation
    return f"Results for: {query}"

@registry.tool("calculate", "Evaluate math expressions")
def calculate(expression: str) -> str:
    return str(eval(expression))  # Use safe eval in production

# Create ReAct agent
agent = ReActAgent(
    llm_client=llm_client,
    tools=registry.list_tools(),
)

# Run with full reasoning trace
result = await agent.run("What is 42 * 17?")

print(result.thought_trace)
# Thought: I need to calculate 42 * 17.
# Action: calculate("42 * 17")
# Observation: 714
# Thought: I have the answer.
# Final Answer: 42 * 17 equals 714.

print(result.final_answer)  # "42 * 17 equals 714."
```

### 2. Supervisor Chain

Supervisor coordinating specialized agents.

```bash
python supervisor_chain.py
```

**What you'll learn:**
- Creating specialized agents (researcher, analyst)
- Supervisor delegation patterns
- Result aggregation strategies

### 3. Financial Research Agent

Deep research agent with multiple data sources.

```bash
python financial_research_agent.py
```

**What you'll learn:**
- Multi-source data gathering
- Context isolation for parallel agents
- Report generation pipelines

## Quick Reference

### ReActAgent

```python
from agentorchestrator.agents import ReActAgent, ReActConfig

agent = ReActAgent(
    llm_client=client,
    tools=tools,
    config=ReActConfig(
        max_iterations=10,     # Max reasoning steps
        max_tokens=1024,       # Tokens per step
        temperature=0.2,       # LLM temperature
    ),
)

result = await agent.run("Analyze the data and provide insights")
```

### ToolRegistry

```python
from agentorchestrator.agents import ToolRegistry, ToolCategory

registry = ToolRegistry()

# Register tools with metadata
registry.register(
    name="search",
    func=search_func,
    description="Search the web",
    category=ToolCategory.SEARCH,
    tags=["web", "research"],
)

# Discover tools
web_tools = registry.find_by_tag("web")
all_tools = registry.list_all()

# Get schemas for LLM function calling
openai_schemas = registry.get_openai_schemas()
anthropic_schemas = registry.get_anthropic_schemas()
```

### LLMGatewayAgent

```python
from agentorchestrator.squad import LLMGatewayAgent

agent = LLMGatewayAgent(
    name="researcher",
    instructions="Find and analyze information on given topics.",
    llm_client=client,
)

response = await agent.process_message("Research AI trends")
```

### SupervisorAgent

```python
from agentorchestrator.squad import SupervisorAgent

supervisor = SupervisorAgent(
    name="coordinator",
    team=[researcher, analyst, writer],
    llm_client=client,
)

result = await supervisor.process_message("Analyze market trends and write report")
```

### Context Isolation

```python
from agentorchestrator.squad.context import (
    ContextIsolationManager,
    ResultAggregator,
    AggregationStrategy,
)

# Isolate each agent's context
isolation = ContextIsolationManager(ctx)
for agent in team:
    isolation.create_namespace(agent.id)

# Share only necessary data
isolation.share_with_all("query", user_query)

# Aggregate results
aggregator = ResultAggregator(strategy=AggregationStrategy.SYNTHESIZE)
final = await aggregator.aggregate(llm=client)
```

## Architecture

### ReAct Pattern

```
┌─────────────────────────────────────────────────────────┐
│                    ReAct Agent                          │
│  ┌──────────────────────────────────────────────────┐  │
│  │                  Reasoning Loop                   │  │
│  │                                                   │  │
│  │   ┌─────────┐   ┌─────────┐   ┌─────────────┐   │  │
│  │   │ Thought │ → │ Action  │ → │ Observation │   │  │
│  │   └─────────┘   └─────────┘   └─────────────┘   │  │
│  │        ↑                            │            │  │
│  │        └────────────────────────────┘            │  │
│  │                   (repeat)                       │  │
│  │                                                  │  │
│  │                ┌──────────────┐                  │  │
│  │                │ Final Answer │                  │  │
│  │                └──────────────┘                  │  │
│  └──────────────────────────────────────────────────┘  │
│                                                         │
│  Tools: [search] [calculate] [lookup] [...]            │
└─────────────────────────────────────────────────────────┘
```

### Supervisor Pattern

```
                    ┌─────────────────┐
                    │   Supervisor    │
                    │  (Coordinator)  │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
              ▼              ▼              ▼
        ┌──────────┐  ┌──────────┐  ┌──────────┐
        │Researcher│  │ Analyst  │  │  Writer  │
        └──────────┘  └──────────┘  └──────────┘
              │              │              │
              └──────────────┼──────────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │  Aggregated     │
                    │    Result       │
                    └─────────────────┘
```

### Context Isolation

```
        Coordinator Context
               │
    ┌──────────┼──────────┐
    │          │          │
    ▼          ▼          ▼
┌────────┐ ┌────────┐ ┌────────┐
│Agent A │ │Agent B │ │Agent C │
│Context │ │Context │ │Context │
│(isolated)│(isolated)│(isolated)│
└────────┘ └────────┘ └────────┘
```

## Best Practices

1. **Use ReAct for Complex Tasks** - When tasks require multi-step reasoning
2. **Use Context Isolation** - Prevents context pollution between agents
3. **Define Clear Roles** - Each agent should have specific instructions
4. **Handle Failures** - Use ResilientAgent for production systems
5. **Aggregate Strategically** - Choose the right aggregation strategy for your use case
6. **Track Tool Usage** - Use `registry.get_stats()` to monitor tool performance
