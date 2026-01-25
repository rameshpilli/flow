# AgentOrchestrator Examples

This directory contains examples demonstrating various AgentOrchestrator capabilities.

## Getting Started

Start here if you're new to AgentOrchestrator:

| Example | Description |
|---------|-------------|
| [hello_world](getting_started/hello_world.py) | Simplest possible chain - your first step |
| [simple_chain](getting_started/simple_chain.py) | Multi-step pipeline with dependencies |
| [parallel_steps](getting_started/parallel_steps.py) | Steps running in parallel |

## Core Examples

### Agents

Multi-agent patterns and coordination:

| Example | Description |
|---------|-------------|
| [supervisor_chain](agents/) | Supervisor coordinating specialized agents |
| [financial_research](agents/) | Deep research agent with multiple data sources |

### Memory

Storage and memory patterns:

| Example | Description |
|---------|-------------|
| [chat_storage](memory/) | InMemory and Redis chat storage |
| [semantic_memory](memory/) | Mem0 semantic memory integration |

### RAG

Retrieval-augmented generation:

| Example | Description |
|---------|-------------|
| [simple_rag](rag/) | Basic RAG with VectorStoreService |
| [rag_with_history](rag/) | RAG with conversation history |

## Running Examples

Each example can be run directly:

```bash
# From the examples directory
python getting_started/hello_world.py

# Or using the CLI
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
