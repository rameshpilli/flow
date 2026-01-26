# Multi-Agent Patterns in AgentOrchestrator

**Clear Guide to Squad, SupervisorAgent, FunctionAgent, and MultiAgentOrchestrator**

---

## Quick Reference Table

| Pattern | When to Use | Coordination Style | Example Use Case |
|---------|-------------|-------------------|------------------|
| **Squad** | 🟢 **Start here** - Simple team coordination | Supervisor delegates to specialists | "Build me a research team" |
| **SupervisorAgent** | Advanced control over Squad | Central coordinator with parallel delegation | Custom supervisor logic |
| **FunctionAgent** | Explicit A→B→C pipeline | Sequential handoffs with context | Research → Write → Review pipeline |
| **MultiAgentOrchestrator** | Intent-based routing | Classifier picks the right agent | Customer support routing |
| **Linear Chains** ⚠️ | DAG execution, not agents | Automatic dependency resolution | ETL pipelines, data processing |

---

## 1. Squad (Recommended - Simplest API)

**What it is:** High-level wrapper around SupervisorAgent that provides the simplest API for team coordination.

**Architecture:**
```
User Query
     │
     ▼
┌────────────┐
│ Supervisor │ ← (LLMGatewayAgent acting as coordinator)
│    Lead    │
└─────┬──────┘
      │ delegates to team in parallel
      ├──────────┬──────────┬──────────┐
      ▼          ▼          ▼          ▼
  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐
  │ Tech   │ │Finance │ │ Data   │ │Research│
  │ Agent  │ │ Agent  │ │ Agent  │ │ Agent  │
  └────────┘ └────────┘ └────────┘ └────────┘
      │          │          │          │
      └──────────┴──────────┴──────────┘
                  │
                  ▼
          Synthesized Response
```

**Code Example:**
```python
from agentorchestrator.squad import Squad, LLMGatewayAgent, LLMGatewayAgentOptions

# 1. Create specialist agents
tech_agent = LLMGatewayAgent(LLMGatewayAgentOptions(
    name="TechAgent",
    description="Handles technical programming questions",
    system_prompt="You are a helpful technical assistant.",
))

finance_agent = LLMGatewayAgent(LLMGatewayAgentOptions(
    name="FinanceAgent",
    description="Handles financial queries",
    system_prompt="You are a helpful financial analyst.",
))

# 2. Create supervisor (lead agent)
lead = LLMGatewayAgent(LLMGatewayAgentOptions(
    name="Supervisor",
    description="Coordinates team to answer complex questions",
))

# 3. Create squad
squad = Squad(
    supervisor=lead,
    agents=[tech_agent, finance_agent],
)

# 4. Execute - supervisor coordinates automatically
result = await squad.run("How do I optimize Python code for trading algorithms?")
print(result.content)
```

**How it works:**
1. Supervisor receives the query
2. Supervisor **decides** which team members to involve
3. Supervisor **delegates** tasks in **parallel** to selected agents
4. Supervisor **synthesizes** their responses into final answer

**Key Features:**
- ✅ Simplest API (just 3 steps: create agents, create squad, run)
- ✅ Automatic parallel delegation
- ✅ Built-in chat history
- ✅ Supervisor synthesizes responses automatically

**When to use:**
- 🟢 You want simple team coordination
- 🟢 You have specialist agents with different expertise
- 🟢 You want the supervisor to decide who to involve

---

## 2. SupervisorAgent (Lower-Level, More Control)

**What it is:** The actual implementation underlying Squad. Use this when you need more control than Squad provides.

**Difference from Squad:**
- **Squad** = high-level wrapper (easier API)
- **SupervisorAgent** = lower-level implementation (more control)

**Code Example:**
```python
from agentorchestrator.squad import (
    SupervisorAgent,
    SupervisorAgentOptions,
    LLMGatewayAgent,
)

# Create supervisor directly (same as Squad internals)
supervisor = SupervisorAgent(SupervisorAgentOptions(
    name="Supervisor",
    description="Coordinates team",
    lead_agent=lead_agent,
    team=[tech_agent, finance_agent],
    trace=True,  # More control options
    enable_validation=True,  # Response validation
    validator=custom_validator,  # Custom validator function
    max_concurrent_agents=5,  # Limit parallelism
    agent_timeout_seconds=30.0,
    guardrails=["no_pii", "no_profanity"],  # Safety checks
))

# Use it
response = await supervisor.process_request(
    "How do I optimize Python code for trading?",
    user_id="user-1",
    session_id="session-1",
    chat_history=[],
)
```

**Additional Features vs Squad:**
- ✅ Custom validator for response quality
- ✅ Guardrails (PII detection, profanity filter)
- ✅ Fine-grained timeout control
- ✅ Custom max concurrent agents

**When to use:**
- 🟡 You need features Squad doesn't expose
- 🟡 You need custom validation logic
- 🟡 You need guardrails or safety checks

---

## 3. FunctionAgent (Explicit Handoffs - Pipeline Pattern)

**What it is:** Agent with **explicit handoff** capabilities for sequential A→B→C pipelines.

**Architecture:**
```
User Query
     │
     ▼
┌──────────┐
│Researcher│ ───handoff───► ┌────────┐ ───handoff───► ┌──────────┐
│  Agent   │  with context  │ Writer │  with context  │ Reviewer │
└──────────┘                │ Agent  │                │  Agent   │
                            └────────┘                └──────────┘
                                                            │
                                                            ▼
                                                        User
```

**Code Example:**
```python
from agentorchestrator.squad import FunctionAgent, FunctionAgentOptions

# Create agents with explicit handoff permissions
researcher = FunctionAgent(FunctionAgentOptions(
    name="Researcher",
    description="Gathers information",
    can_handoff_to=["Writer"],  # Can only hand off to Writer
))

writer = FunctionAgent(FunctionAgentOptions(
    name="Writer",
    description="Writes reports from research",
    can_handoff_to=["Reviewer"],  # Can only hand off to Reviewer
))

reviewer = FunctionAgent(FunctionAgentOptions(
    name="Reviewer",
    description="Reviews and improves content",
    can_handoff_to=["User"],  # Terminal - returns to user
))

# Researcher does its work and hands off
handoff = await researcher.handoff(
    to_agent="Writer",
    context={
        "findings": findings,
        "sources": sources,
    },
    message="Research complete. Please write a summary.",
)

# Orchestrator routes to Writer using handoff.to_agent
# Writer processes and hands off to Reviewer
# Reviewer processes and returns to User
```

**How it works:**
1. Researcher processes query, creates `HandoffResult`
2. **Orchestrator** sees the handoff and routes to Writer
3. Writer processes with context from Researcher, hands off to Reviewer
4. Reviewer processes and returns to User (or hands back)

**Key Features:**
- ✅ **Explicit** control over who hands to whom
- ✅ **Context transfer** between agents
- ✅ **Sequential** pipeline (not parallel)
- ✅ Type-safe handoff targets (`can_handoff_to` list)

**When to use:**
- 🟢 You need a **clear pipeline**: Research → Write → Review
- 🟢 Each step depends on previous step's output
- 🟢 You want **explicit control** over delegation

**Difference from Supervisor:**
- **Supervisor**: Central coordinator decides & delegates in **parallel**
- **FunctionAgent**: Agents hand off **sequentially** to each other

---

## 4. MultiAgentOrchestrator (Intent-Based Routing)

**What it is:** Routes queries to the **right specialist** based on **intent classification**.

**Architecture:**
```
User Query
     │
     ▼
┌───────────────┐
│  Classifier   │ ← (LLM-based or rule-based)
│ (Intent       │
│  Detection)   │
└───────┬───────┘
        │ routes to best agent
        ├────────────┬────────────┬────────────┐
        ▼            ▼            ▼            ▼
    ┌────────┐  ┌────────┐  ┌────────┐  ┌────────┐
    │ Tech   │  │Finance │  │ Data   │  │Customer│
    │ Agent  │  │ Agent  │  │ Agent  │  │Support │
    └────────┘  └────────┘  └────────┘  └────────┘
        │            │            │            │
        └────────────┴────────────┴────────────┘
                     │
                     ▼
            Response (from 1 agent)
```

**Code Example:**
```python
from agentorchestrator.squad import (
    MultiAgentOrchestrator,
    LLMGatewayAgent,
    LLMGatewayClassifier,
)

# Create orchestrator with classifier
orchestrator = MultiAgentOrchestrator(
    classifier=LLMGatewayClassifier(),  # Uses LLM for intent classification
)

# Add specialist agents
orchestrator.add_agent(tech_agent)
orchestrator.add_agent(finance_agent)
orchestrator.add_agent(support_agent)
orchestrator.set_default_agent(tech_agent)  # Fallback

# Route request - classifier picks ONE agent
response = await orchestrator.route_request(
    user_input="How do I optimize my Python code?",
    user_id="user-123",
    session_id="session-456",
)
# Routes to tech_agent based on intent
```

**How it works:**
1. **Classifier** analyzes query intent (technical? financial? support?)
2. **Routes** to the **most suitable** agent
3. **ONE agent** handles the request (not parallel like Supervisor)
4. Response comes from that single agent

**Key Features:**
- ✅ Automatic **intent classification**
- ✅ Routes to **one specialist** (not multiple)
- ✅ Good for **domain-specific** routing
- ✅ Can use Supervisor as one of the agents!

**When to use:**
- 🟢 You have **domain-specific** agents (tech, finance, support)
- 🟢 Each query should go to **one specialist**
- 🟢 You want **automatic routing** based on intent

**Difference from Supervisor:**
- **MultiAgentOrchestrator**: Routes to **ONE** agent based on intent
- **Supervisor**: Delegates to **MULTIPLE** agents in parallel

---

## 5. Linear Chains (Not an Agent Pattern!)

⚠️ **Important:** "Linear Chains" is NOT an agent pattern - it's just **DAG execution** with `@ao.step()` decorators.

**What it is:** Sequential or parallel step execution using DAG dependencies.

**Code Example:**
```python
from agentorchestrator import AgentOrchestrator

ao = AgentOrchestrator()

@ao.step(name="fetch")
async def fetch(ctx):
    ctx.set("data", [1, 2, 3])
    return {"fetched": True}

@ao.step(name="process", deps=["fetch"])  # Depends on fetch
async def process(ctx):
    data = ctx.get("data")
    ctx.set("processed", [x * 2 for x in data])
    return {"processed": True}

@ao.chain(name="pipeline")
class Pipeline:
    steps = ["fetch", "process"]

result = await ao.launch("pipeline", {})
```

**This is NOT an agent** - it's just a **pipeline** with automatic dependency resolution.

**Difference from FunctionAgent:**
- **Linear Chain**: Steps execute based on **DAG dependencies** (automatic)
- **FunctionAgent**: Agents **explicitly hand off** to each other (manual)

---

## Summary: When to Use What?

### Use **Squad** when:
- ✅ You want simple team coordination
- ✅ Supervisor should delegate to specialists in **parallel**
- ✅ You want automatic synthesis of responses
- ✅ **Start here if unsure!**

### Use **SupervisorAgent** when:
- ⚠️ You need features Squad doesn't expose (validators, guardrails)
- ⚠️ You need fine-grained control over concurrency
- ⚠️ You need custom validation logic

### Use **FunctionAgent** when:
- ✅ You have a **clear pipeline**: A → B → C
- ✅ Each step depends on previous step
- ✅ You want **explicit control** over handoffs

### Use **MultiAgentOrchestrator** when:
- ✅ You need **intent-based routing**
- ✅ Each query goes to **ONE specialist**
- ✅ You have **domain-specific agents** (tech, finance, support)

### Use **Linear Chains** when:
- ✅ You have a **data pipeline** (not agents!)
- ✅ You want automatic parallelization via DAG
- ✅ Simple ETL or data processing

---

## Combining Patterns

You can **combine** these patterns! Examples:

### Example 1: Supervisor Inside MultiAgentOrchestrator
```python
# Create a supervisor for complex questions
supervisor = SupervisorAgent(...)

# Add it to orchestrator as one of the agents
orchestrator.add_agent(supervisor)
orchestrator.add_agent(simple_qa_agent)
orchestrator.add_agent(support_agent)

# Classifier routes complex questions to supervisor
# Simple questions go directly to simple_qa_agent
```

### Example 2: FunctionAgent Pipeline with Supervisor
```python
# Create a pipeline where one step is a supervisor
researcher = FunctionAgent(...)  # Hands off to supervisor
supervisor = SupervisorAgent(...)  # Coordinates team
writer = FunctionAgent(...)  # Receives from supervisor

# Flow: Researcher → Supervisor (team) → Writer
```

---

## Quick Decision Tree

```
Do you need multiple agents?
│
├─ NO → Use Linear Chains (@ao.step with deps)
│
└─ YES → What coordination style?
    │
    ├─ ONE agent per query (routing) → MultiAgentOrchestrator
    │
    ├─ MULTIPLE agents in parallel → Squad (or SupervisorAgent)
    │
    └─ Sequential pipeline A→B→C → FunctionAgent
```

---

## Common Misconceptions

❌ **WRONG:** "Squad and Supervisor are different patterns"
✅ **CORRECT:** Squad is a **wrapper** around SupervisorAgent (simpler API)

❌ **WRONG:** "FunctionAgent and Linear Chains are the same"
✅ **CORRECT:** FunctionAgent = agent handoffs, Linear Chains = DAG execution

❌ **WRONG:** "MultiAgentOrchestrator calls multiple agents"
✅ **CORRECT:** It routes to **ONE** agent based on intent

❌ **WRONG:** "Supervisor is like a manager that just assigns tasks"
✅ **CORRECT:** Supervisor delegates in **parallel** and **synthesizes** responses

---

## Code Location Reference

| Pattern | File |
|---------|------|
| Squad | `squad/squad.py` |
| SupervisorAgent | `squad/agents/supervisor.py` |
| FunctionAgent | `squad/agents/function_agent.py` |
| MultiAgentOrchestrator | `squad/orchestrator.py` |
| Linear Chains | `core/orchestrator.py` (DAG execution) |

---

## Next Steps

1. **Start with Squad** for most use cases
2. **Add FunctionAgent** if you need explicit pipelines
3. **Use MultiAgentOrchestrator** for domain routing
4. **Drop to SupervisorAgent** only if you need advanced features

Questions? Check the examples:
- Squad: `examples/supervisor_chain.py`
- FunctionAgent: (coming soon - see code docs)
- MultiAgentOrchestrator: `squad/__init__.py` examples
