# Scaffolding & Code Generation

Commands for generating new components and projects.

## new agent

Generate a new agent template.

```bash
ao new agent <name> [options]
```

### Options

| Option | Short | Description |
|--------|-------|-------------|
| `--output-dir` | `-o` | Output directory (default: current) |
| `--force` | `-f` | Overwrite existing files |

### Examples

```bash
# Create a new agent in current directory
ao new agent MyCustomAgent

# Create in specific directory
ao new agent DataFetcher --output-dir ./agents/

# Overwrite existing
ao new agent MyAgent --force
```

### Generated File

Creates `<name>_agent.py`:

```python
"""
MyCustomAgent Agent

Custom data agent for fetching mycustomagent data.
"""

from agentorchestrator.agents.base import BaseAgent, AgentResult


class MyCustomAgentAgent(BaseAgent):
    """
    Agent for fetching mycustomagent data.

    Usage:
        agent = MyCustomAgentAgent()
        result = await agent.fetch(query="search term")
    """

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        # Add your initialization here

    async def fetch(self, query: str, **kwargs) -> AgentResult:
        """
        Fetch data based on query.

        Args:
            query: Search query or identifier
            **kwargs: Additional parameters

        Returns:
            AgentResult with fetched data
        """
        # TODO: Implement your data fetching logic here
        data = {
            "query": query,
            "results": [],
        }

        return AgentResult(
            data=data,
            metadata={
                "source": "mycustomagent",
                "query": query,
            }
        )

    async def health_check(self) -> bool:
        """Check if agent is healthy."""
        # TODO: Implement health check
        return True


# Register with AgentOrchestrator
def register(ao):
    """Register this agent with AgentOrchestrator instance."""
    ao.register_agent("mycustomagent", MyCustomAgentAgent)
```

---

## new chain

Generate a new chain template.

```bash
ao new chain <name> [options]
```

### Options

| Option | Short | Description |
|--------|-------|-------------|
| `--output-dir` | `-o` | Output directory (default: current) |
| `--force` | `-f` | Overwrite existing files |

### Examples

```bash
# Create a new chain
ao new chain DataPipeline

# Create in specific directory
ao new chain AnalysisPipeline --output-dir ./chains/
```

### Generated File

Creates `<name>_chain.py` with:

- Isolated AgentOrchestrator instance
- Three example steps with dependencies
- Chain definition
- Convenience functions (`run`, `check`, `graph`)
- CLI entry point

```python
"""
DataPipeline Chain

Custom chain for datapipeline workflow.
"""

from agentorchestrator import AgentOrchestrator, ChainContext


# Create AgentOrchestrator instance (isolated for this chain)
ao = AgentOrchestrator(name="datapipeline", isolated=True)


@ao.step
async def step_1(ctx: ChainContext) -> dict:
    """First step: Initialize and prepare data."""
    # ...

@ao.step(deps=[step_1])
async def step_2(ctx: ChainContext) -> dict:
    """Second step: Process data from step 1."""
    # ...

@ao.step(deps=[step_2])
async def step_3(ctx: ChainContext) -> dict:
    """Final step: Generate output."""
    # ...


@ao.chain
class DataPipelineChain:
    """Main chain for datapipeline workflow."""
    steps = [step_1, step_2, step_3]


# Convenience functions
async def run(data: dict | None = None) -> dict:
    """Run the DataPipeline chain."""
    return await ao.launch("DataPipelineChain", data)
```

---

## new project

Generate a complete AgentOrchestrator project with all scaffolding.

```bash
ao new project <name> [options]
```

### Options

| Option | Short | Description |
|--------|-------|-------------|
| `--output-dir` | `-o` | Output directory (default: current) |
| `--description` | `-d` | Project description |
| `--no-api` | | Skip FastAPI server |
| `--no-docker` | | Skip Docker files |
| `--no-ci` | | Skip CI/CD configuration |
| `--template` | `-t` | Project template: `default` or `minimal` |

### Examples

```bash
# Create full project
ao new project my_app

# Create with description
ao new project my_app --description "My awesome AI pipeline"

# Minimal project (no API, Docker, or CI)
ao new project my_app --no-api --no-docker --no-ci

# Use minimal template
ao new project my_app --template minimal
```

### Generated Structure

```
my_app/
├── src/
│   └── my_app/
│       ├── __init__.py
│       ├── chains.py          # Chain definitions
│       ├── steps.py           # Step implementations
│       ├── agents/            # Custom agents
│       │   └── __init__.py
│       └── api.py             # FastAPI server (if --no-api not set)
├── tests/
│   ├── __init__.py
│   ├── test_chains.py
│   └── conftest.py
├── pyproject.toml             # Project configuration
├── README.md
├── .env.example
├── .gitignore
├── Dockerfile                 # (if --no-docker not set)
├── docker-compose.yml         # (if --no-docker not set)
└── .github/
    └── workflows/
        └── ci.yml             # (if --no-ci not set)
```

### Next Steps After Generation

```bash
cd my_app
pip install -e '.[dev]'
ao check
ao run hello_chain --data '{"message": "Hello"}'
```

**To start the API server:**

```bash
pip install -e '.[api]'
uvicorn src.my_app.api:app --reload
```

**To run with Docker:**

```bash
docker-compose up
```
