# AgentOrchestrator Examples

This directory contains examples demonstrating various AgentOrchestrator capabilities.

## Getting Started

Start here if you're new to AgentOrchestrator:

| Example | Description |
|---------|-------------|
| [hello_world](getting_started/hello_world.py) | Simplest possible chain - your first step |
| [simple_chain](getting_started/simple_chain.py) | Multi-step pipeline with dependencies |
| [parallel_steps](getting_started/parallel_steps.py) | Steps running in parallel |
| [ai_workflow_dag](getting_started/ai_workflow_dag.py) | DAG-style AI workflow with parallel research branches |

## Core Examples

### State Management

Type-safe state management with Pydantic:

| Example | Description |
|---------|-------------|
| [pydantic_state](pydantic_state.py) | Type-safe workflow state with validation and atomic updates |

### Workflow Patterns

Event-driven and workflow patterns:

| Example | Description |
|---------|-------------|
| [event_workflow](event_workflow.py) | Event-driven workflows with event handlers and event bus |
| [supervisor_chain](supervisor_chain.py) | Supervisor pattern with coordinator and specialists |
| [usage_examples](usage_examples.py) | Various usage patterns and best practices |

### Agents & Research

Multi-agent patterns and coordination:

| Example | Description |
|---------|-------------|
| [deep_research](deep_research_agent.py) | Multi-stage research with decomposition and parallel search |
| [financial_research](financial_research_agent.py) | Deep research agent with multiple data sources |
| [supervisor_in_chain](supervisor_in_chain.py) | Supervisor pattern integrated with chain execution |

### Large Response Handling

Patterns for managing context window limits:

| Example | Description |
|---------|-------------|
| [advanced_middleware](advanced_middleware.py) | Complete guide to all middleware patterns |

**Key patterns covered:**
- **Glob Pattern Matching** - Apply middleware to steps using `gather_*` patterns
- **Token Budget Reservation** - Explicit allocation prevents truncation
- **TREE Summarization** - Hierarchical compression for 50K+ token documents
- **Rolling Summary** - Incremental summarization for iterative data
- **Query-Aware Compression** - Focus on query-relevant content
- **Namespace-Aware Budgets** - Per-agent token allocation for multi-agent
- **ResultAggregator with Pre-Summarization** - Auto-compress before synthesis
- **Middleware Metrics** - Monitor token usage via `ao.get_middleware_metrics()`

### Memory

Storage and memory patterns:

| Example | Description |
|---------|-------------|
| [chat_storage](memory/chat_storage.py) | InMemory and Redis chat storage |
| [semantic_memory](memory/semantic_memory.py) | Mem0 semantic memory integration |

### RAG

Retrieval-augmented generation:

| Example | Description |
|---------|-------------|
| [simple_rag](rag/simple_rag.py) | Basic RAG with VectorStoreService |
| [rag_with_history](rag/rag_with_history.py) | RAG with conversation history |

## Running Examples

Each example can be run directly:

```bash
# Getting started examples
python -m agentorchestrator.examples.getting_started.hello_world
python -m agentorchestrator.examples.getting_started.ai_workflow_dag

# State management
python -m agentorchestrator.examples.pydantic_state

# Event workflows
python -m agentorchestrator.examples.event_workflow

# From specific example files
python -m agentorchestrator.examples.financial_research_agent

# Or using the CLI (for registered chains)
ao run hello_chain --data '{"name": "World"}'
```

## Example Structure

Each example follows this pattern:

```
example_name/
├── README.md           # What it does, how to run it
├── example_name.py     # Main implementation
└── config.yaml         # Optional configuration
```
