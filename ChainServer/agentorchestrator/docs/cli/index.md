# CLI Reference

AgentOrchestrator provides a powerful command-line interface for managing your AI/ML pipelines.

## Command Names

The CLI is available under two equivalent command names:

| Command | Description |
|---------|-------------|
| `ao` | **Recommended** - Short, convenient alias |
| `agentorchestrator` | Full name, useful in scripts for clarity |

Both commands are identical and point to the same entry point. All examples in this documentation use `ao` for brevity.

```bash
# These are equivalent:
ao run my_chain --data '{"key": "value"}'
agentorchestrator run my_chain --data '{"key": "value"}'
```

## Command Categories

### Execution Commands
Run and manage chain executions.

| Command | Description |
|---------|-------------|
| [`ao run`](./run.md) | Run a chain with optional input data |
| [`ao resume`](./run.md#resume) | Resume a failed or partial run |
| [`ao runs`](./run.md#runs) | List chain runs with filtering |
| [`ao run-info`](./run.md#run-info) | Show detailed run information |
| [`ao run-output`](./run.md#run-output) | Get partial outputs from a run |

### Validation & Inspection
Validate and inspect your chain definitions.

| Command | Description |
|---------|-------------|
| [`ao check`](./validation.md#check) | Quick validation of chain definitions |
| [`ao validate`](./validation.md#validate) | Comprehensive validation with detailed checks |
| [`ao list`](./validation.md#list) | List all registered components |
| [`ao graph`](./validation.md#graph) | Show DAG visualization |

### Scaffolding & Code Generation
Generate new components and projects.

| Command | Description |
|---------|-------------|
| [`ao new agent`](./scaffolding.md#new-agent) | Generate a new agent template |
| [`ao new chain`](./scaffolding.md#new-chain) | Generate a new chain template |
| [`ao new project`](./scaffolding.md#new-project) | Generate a complete project |

### Development & Debugging
Tools for development workflow.

| Command | Description |
|---------|-------------|
| [`ao dev`](./development.md#dev) | Development mode with hot reload |
| [`ao debug`](./development.md#debug) | Debug mode with context snapshots |

### Health & Diagnostics
Check system health and diagnose issues.

| Command | Description |
|---------|-------------|
| [`ao health`](./diagnostics.md#health) | Check health status |
| [`ao doctor`](./diagnostics.md#doctor) | Diagnose common setup issues |
| [`ao version`](./diagnostics.md#version) | Show version information |
| [`ao config`](./diagnostics.md#config) | Show configuration (secrets masked) |

## Quick Examples

```bash
# Run a chain
ao run my_chain --data '{"name": "Test"}'

# Run with checkpointing for resume capability
ao run my_chain --resumable --data '{"key": "value"}'

# Test a single step in isolation
ao run my_chain --step my_step --data '{"key": "value"}'

# Dry run - see execution plan without running
ao run my_chain --dry-run --data '{"key": "value"}'

# Resume a failed run
ao resume run_abc123

# Validate all definitions
ao check

# Validate a specific chain with comprehensive checks
ao validate my_chain --data '{"sample": "data"}'

# List all registered chains and steps
ao list

# Visualize chain as Mermaid diagram
ao graph my_chain --format mermaid

# Create a new project
ao new project my_app

# Development mode with file watching
ao dev --watch

# Debug with context snapshots
ao debug my_chain --data '{"key": "value"}'

# Health check
ao health --detailed

# Diagnose setup issues
ao doctor
```

## Global Options

```bash
ao --version              # Show version
ao --definitions PATH     # Specify chain definition paths (can be repeated)
ao --help                 # Show help
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `AO_ENABLE_LOGGING` | Enable structured logging | `false` |
| `AO_LOG_LEVEL` | Log level (DEBUG, INFO, WARNING, ERROR) | `INFO` |
| `AO_LOG_JSON` | Output logs as JSON | `false` |
| `AO_ENABLE_TRACING` | Enable distributed tracing | `false` |
| `AO_TRACE_SERVICE` | Service name for traces | `agentorchestrator` |
| `AO_ENV` | Environment name | `development` |
| `AO_DEBUG` | Enable debug mode | `false` |
| `LLM_API_KEY` | LLM API authentication key | - |
| `LLM_BASE_URL` | LLM endpoint URL | - |

## Chain Definition Discovery

The CLI automatically discovers chain definitions from these locations (in order):

1. Explicit paths via `--definitions` / `-D` flag
2. `chains.py` in current directory
3. `agentorchestrator_chains.py` in current directory
4. `definitions.py` in current directory
5. `flows.py` in current directory
6. `chains/` package (directory with `__init__.py`)

```bash
# Use explicit definition paths
ao -D ./my_chains.py -D ./more_chains/ run my_chain

# Or let it auto-discover from current directory
cd my_project
ao run my_chain
```
