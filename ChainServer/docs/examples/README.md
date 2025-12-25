# AgentOrchestrator Examples

This folder contains examples showing how to use AgentOrchestrator, organized by complexity level.

## Learning Path

Start here and work through in order:

```
01_quickstart.py          → Your first chain (START HERE!)
        ↓
02_custom_agents.py       → Creating custom data agents
        ↓
03_chain_composition.py   → Composing chains within chains
        ↓
04_meeting_prep_chain.py  → Real-world production example
        ↓
05_capiq_integration.py   → Advanced: External API integration
```

For a complete production reference, see the `cmpt/` folder at the project root.

## Quick Overview

| File | Description | Concepts |
|------|-------------|----------|
| `01_quickstart.py` | Hello World example | `@ao.step`, `@ao.chain`, `ao.launch()` |
| `02_custom_agents.py` | Custom data agents | `@ao.agent`, `BaseAgent`, MCP integration |
| `03_chain_composition.py` | Nested chains | Sub-chains, context scoping, parallel execution |
| `04_meeting_prep_chain.py` | Meeting prep | Middleware, multiple agents, error handling |
| `05_capiq_integration.py` | Financial APIs | External APIs, authentication, rate limiting |

## Running Examples

```bash
# Run any example directly
python docs/examples/01_quickstart.py

# Or via the CLI
ao run QuickstartChain --company "Apple"
```

## Key Concepts by Example

### 01_quickstart.py
- Creating an `AgentOrchestrator` instance
- Defining steps with `@ao.step`
- Setting dependencies between steps (`deps=[]`)
- Defining chains with `@ao.chain`
- Running chains with `ao.launch()`

### 02_custom_agents.py
- Creating custom agents with `@ao.agent`
- Implementing the `BaseAgent.fetch()` method
- Using agents in steps with `ao.get_agent()`
- MCP server integration

### 03_chain_composition.py
- Creating reusable sub-chains
- Composing chains within parent chains
- Context scoping (`ContextScope.CHAIN`)
- Parallel sub-chain execution

### 04_meeting_prep_chain.py
- Using middleware with `ao.use()` (logging, caching, tokens)
- Building multiple data agents
- Multi-step data processing
- LLM integration patterns

### 05_capiq_integration.py
- External API authentication
- Fetching multiple data types in parallel
- Aggregating data from multiple sources
- Generating analysis reports

## Environment Variables

For production examples (04, 05), you may need:

```bash
# LLM Gateway
LLM_GATEWAY_URL=https://your-llm-gateway.com
LLM_API_KEY=your-api-key

# Data Agents (if using real APIs)
NEWS_AGENT_MCP_URL=https://mcp-news.yourcompany.com
SEC_AGENT_MCP_URL=https://mcp-sec.yourcompany.com
```

Examples will use mock data if environment variables are not set.
