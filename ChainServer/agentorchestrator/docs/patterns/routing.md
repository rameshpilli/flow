# Routing Pattern

Dynamically route tasks to the right agent based on intent, capability, or load.

## The Problem

Different queries need different specialists:

```
"What are NVDA's financials?"  → Financial Analyst
"How do I use the API?"        → Tech Support
"Schedule a meeting"           → Calendar Agent
```

## The Solution

A router agent analyzes intent and delegates to specialists:

```
                    ┌────────────────┐
                    │     Router     │
                    │    Agent       │
                    └───────┬────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
        ▼                   ▼                   ▼
┌───────────────┐   ┌───────────────┐   ┌───────────────┐
│   Financial   │   │     Tech      │   │   Calendar    │
│   Analyst     │   │   Support     │   │    Agent      │
└───────────────┘   └───────────────┘   └───────────────┘
```

> **Status:** `RouterAgent`, `AgentNetwork`, `CapabilityRouter`, and `LoadBalancer`
> are planned but not yet implemented. For production routing today, use
> `MultiAgentOrchestrator` with an intent classifier.

## When to Use

| Scenario | Use Routing? |
|----------|--------------|
| Multiple specialized agents | :material-check: Yes |
| Dynamic task assignment | :material-check: Yes |
| Load balancing | :material-check: Yes |
| Single-purpose pipeline | :material-close: No |
| Static workflows | :material-close: No |

## Current Implementation (MultiAgentOrchestrator)

```python
from agentorchestrator.squad import (
    MultiAgentOrchestrator,
    LLMGatewayClassifier,
    LLMGatewayAgent,
    LLMGatewayAgentOptions,
)

classifier = LLMGatewayClassifier()
orchestrator = MultiAgentOrchestrator(classifier=classifier)

orchestrator.add_agent(LLMGatewayAgent(LLMGatewayAgentOptions(
    name="financial",
    description="Financial analysis",
)))
orchestrator.add_agent(LLMGatewayAgent(LLMGatewayAgentOptions(
    name="technical",
    description="API support",
)))

orchestrator.set_default_agent(
    LLMGatewayAgent(LLMGatewayAgentOptions(
        name="general",
        description="General assistance",
    ))
)

response = await orchestrator.route_request(
    user_input="What is NVDA's P/E ratio?",
    user_id="user-1",
    session_id="session-1",
)
```

## Planned APIs (Not Yet Implemented)

The following examples are forward-looking and will not run in the current release.

### Basic Router

```python
from agentorchestrator.squad import RouterAgent

class IntentRouter(RouterAgent):
    name = "router"
    instructions = """
    You route requests to the appropriate specialist.
    Available specialists:
    - financial: For stock analysis, market data, financial reports
    - technical: For API questions, integration help, debugging
    - general: For everything else

    Respond with just the specialist name.
    """

    async def route(self, query: str) -> str:
        response = await self.llm.generate(
            f"Route this query: {query}"
        )
        return response.strip().lower()

# Setup router with agents
router = IntentRouter()
agents = {
    "financial": FinancialAgent(),
    "technical": TechnicalAgent(),
    "general": GeneralAgent(),
}

# Route and execute
target = await router.route("What is NVDA's P/E ratio?")
result = await agents[target].process(query)
```

### Decorator-Based Routing

```python
from agentorchestrator.squad import route

class TriageAgent(BaseAgent):
    name = "triage"

    @route(to=["billing", "technical", "sales"])
    async def classify(self, message: str) -> str:
        """Classify the message intent."""
        prompt = f"""Classify this customer message:
        "{message}"

        Categories: billing, technical, sales
        Respond with just the category."""

        return await self.llm.generate(prompt)
```

### Agent Network

For complex routing with multiple hops:

```python
from agentorchestrator.squad import AgentNetwork

network = AgentNetwork(
    router=TriageAgent(),
    agents={
        "billing": BillingAgent(),
        "technical": TechnicalAgent(),
        "sales": SalesAgent(),
    },
    fallback="general",  # Default if routing fails
)

result = await network.handle("I can't access my account")
```

## Advanced Patterns

### Multi-Hop Routing

Route through multiple specialists:

```python
class MultiHopRouter(RouterAgent):
    async def route(self, query: str) -> list[str]:
        """Return ordered list of agents to consult."""
        response = await self.llm.generate(f"""
            For this query, which agents should be consulted in order?
            Query: {query}

            Available: researcher, analyst, writer

            Respond with comma-separated list.
        """)
        return [a.strip() for a in response.split(",")]

# Execute multi-hop
targets = await router.route("Research NVDA and write a report")
# ["researcher", "analyst", "writer"]

context = {}
for agent_name in targets:
    result = await agents[agent_name].process(query, context)
    context.update(result)
```

### Capability-Based Routing

Route based on agent capabilities:

```python
from agentorchestrator.squad import CapabilityRouter

# Register agent capabilities
registry = {
    "gpt4_agent": {
        "capabilities": ["reasoning", "coding", "analysis"],
        "cost": "high",
        "latency": "medium",
    },
    "claude_agent": {
        "capabilities": ["writing", "reasoning", "research"],
        "cost": "medium",
        "latency": "low",
    },
    "fast_agent": {
        "capabilities": ["classification", "extraction"],
        "cost": "low",
        "latency": "very_low",
    },
}

router = CapabilityRouter(registry)

# Route by capability
agent = router.find_agent(
    required=["coding"],
    prefer_low_cost=True,
)
```

### Load-Balanced Routing

Distribute across agent instances:

```python
from agentorchestrator.squad import LoadBalancer

balancer = LoadBalancer(
    agents=[
        AnalysisAgent(instance=1),
        AnalysisAgent(instance=2),
        AnalysisAgent(instance=3),
    ],
    strategy="round_robin",  # or "least_busy", "random"
)

# Automatically selects least loaded instance
result = await balancer.route(query)
```

## Full Example

```python
from agentorchestrator import AgentOrchestrator
from agentorchestrator.squad import AgentNetwork, RouterAgent
from agentorchestrator.agents import BaseAgent

ao = AgentOrchestrator(name="support_system")

# Specialist agents
class BillingAgent(BaseAgent):
    name = "billing"
    instructions = "Help with billing questions, invoices, refunds."

class TechnicalAgent(BaseAgent):
    name = "technical"
    instructions = "Help with API issues, integration, debugging."

class SalesAgent(BaseAgent):
    name = "sales"
    instructions = "Handle product inquiries, pricing, upgrades."

# Router
class SupportRouter(RouterAgent):
    name = "router"
    instructions = """
    Classify customer intent:
    - billing: invoices, payments, refunds, charges
    - technical: API, bugs, integration, errors
    - sales: pricing, features, upgrades, demos
    """

    async def route(self, message: str) -> str:
        response = await self.llm.generate(
            f"Classify: {message}\n\nRespond with: billing, technical, or sales"
        )
        intent = response.strip().lower()
        if intent not in ["billing", "technical", "sales"]:
            return "technical"  # Default fallback
        return intent

# Build network
network = AgentNetwork(
    router=SupportRouter(),
    agents={
        "billing": BillingAgent(),
        "technical": TechnicalAgent(),
        "sales": SalesAgent(),
    },
)

@ao.step(name="handle_support")
async def handle_support(ctx):
    message = ctx.get("message")

    # Route to appropriate agent
    result = await network.handle(message)

    return {
        "response": result.content,
        "handled_by": result.agent_id,
        "confidence": result.confidence,
    }

@ao.chain(name="support_chain")
class SupportChain:
    steps = ["handle_support"]
```

## Routing Strategies

| Strategy | Description | Use When |
|----------|-------------|----------|
| Intent-based | LLM classifies intent | Natural language routing |
| Keyword-based | Pattern matching | Known keywords/phrases |
| Capability-based | Match requirements to skills | Complex capability needs |
| Load-balanced | Distribute evenly | Multiple instances available |
| Priority-based | Route to highest priority available | Tiered service levels |

## Metrics & Monitoring

```python
# Track routing decisions
@ao.step(name="routed_request")
async def routed_request(ctx):
    target = await router.route(ctx.get("query"))

    # Log routing decision
    ao.metrics.increment("routing.decisions", tags={
        "target": target,
        "source": "support",
    })

    result = await agents[target].process(ctx.get("query"))
    return result
```

## Best Practices

!!! tip "Clear Routing Instructions"
    Give the router explicit categories and examples.

!!! tip "Provide Fallback"
    Always have a default agent for unclassified requests.

!!! tip "Log Routing Decisions"
    Track which agents handle what for optimization.

!!! warning "Avoid Routing Loops"
    Ensure agents don't route back to the router.

## Related Patterns

- [Context Isolation](context_isolation.md) - Isolate routed agent contexts
- [Aggregation](aggregation.md) - Combine multi-hop results

## API Reference

::: agentorchestrator.squad.RouterAgent
::: agentorchestrator.squad.AgentNetwork
::: agentorchestrator.squad.CapabilityRouter
