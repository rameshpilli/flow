# Contributing to AgentOrchestrator

Thank you for your interest in contributing to AgentOrchestrator! This guide will help you get started.

## Development Setup

### Prerequisites

- Python 3.10+
- pip or uv (package manager)
- Git

### Local Development

1. **Clone the repository**
   ```bash
   git clone https://github.com/your-org/agentorchestrator.git
   cd agentorchestrator/ChainServer
   ```

2. **Create a virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # Linux/Mac
   # or
   venv\Scripts\activate  # Windows
   ```

3. **Install in development mode**
   ```bash
   pip install -e "agentorchestrator[dev]"
   ```

4. **Verify installation**
   ```bash
   ao --version
   ```

## Code Quality

### Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=agentorchestrator --cov-report=html

# Run specific test file
pytest tests/unit/test_orchestrator.py -v

# Run specific test
pytest tests/unit/test_orchestrator.py::test_step_registration -v
```

### Linting and Formatting

We use [Ruff](https://github.com/astral-sh/ruff) for linting and formatting:

```bash
# Check for issues
ruff check agentorchestrator/

# Auto-fix issues
ruff check --fix agentorchestrator/

# Format code
ruff format agentorchestrator/
```

### Type Checking

```bash
# Run mypy (if enabled)
mypy agentorchestrator/
```

## Project Structure

```
agentorchestrator/
├── core/           # Core orchestration (orchestrator, dag, context)
├── agents/         # Agent implementations (base, react, composite)
├── middleware/     # Middleware components (cache, logger, etc.)
├── services/       # External service clients (LLM, Redis, etc.)
├── squad/          # Multi-agent orchestration
├── utils/          # Utilities (logging, tracing, etc.)
├── plugins/        # Plugin system
├── templates/      # Project scaffolding templates
├── testing/        # Testing utilities
├── tests/          # Test suite
└── docs/           # Documentation
```

## Making Changes

### Branch Naming

Use descriptive branch names:
- `feature/add-new-middleware`
- `fix/context-cleanup-leak`
- `docs/update-quickstart`

### Commit Messages

Follow conventional commit format:

```
type(scope): description

[optional body]

[optional footer]
```

Types:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `refactor`: Code refactoring
- `test`: Test additions/changes
- `chore`: Maintenance tasks

Examples:
```
feat(agents): add ReAct agent pattern implementation

fix(context): prevent memory leak in long-running processes

docs(quickstart): add example for event-driven workflows
```

### Pull Request Process

1. **Create a feature branch**
   ```bash
   git checkout -b feature/my-feature
   ```

2. **Make your changes**
   - Write tests for new functionality
   - Update documentation as needed
   - Follow the code style guidelines

3. **Run quality checks**
   ```bash
   # Run tests
   pytest tests/ -v
   
   # Run linter
   ruff check agentorchestrator/
   ```

4. **Commit your changes**
   ```bash
   git add .
   git commit -m "feat(scope): description"
   ```

5. **Push and create PR**
   ```bash
   git push origin feature/my-feature
   ```

6. **PR Review**
   - Ensure CI passes
   - Address review feedback
   - Get approval from maintainers

## Adding New Features

### Adding a New Middleware

1. Create a new file in `middleware/`:
   ```python
   # middleware/my_middleware.py
   from agentorchestrator.middleware.base import BaseMiddleware
   
   class MyMiddleware(BaseMiddleware):
       async def before(self, ctx, step_name):
           # Pre-step logic
           pass
       
       async def after(self, ctx, step_name, result):
           # Post-step logic
           return result
       
       async def on_error(self, ctx, step_name, error):
           # Error handling
           raise error
   ```

2. Add tests in `tests/unit/test_middleware.py`

3. Export from `middleware/__init__.py`

4. Document in `docs/API.md`

### Adding a New Agent Type

1. Create in `agents/`:
   ```python
   # agents/my_agent.py
   from agentorchestrator.agents.base import BaseAgent
   
   class MyAgent(BaseAgent):
       async def fetch(self, query: str) -> dict:
           # Implementation
           pass
   ```

2. Add tests in `tests/unit/`

3. Export from `agents/__init__.py`

4. Document in `docs/understanding/agents.md`

### Adding a New Service

1. Create in `services/`:
   ```python
   # services/my_service.py
   class MyService:
       def __init__(self, config: dict):
           self.config = config
       
       async def connect(self):
           # Connection logic
           pass
   ```

2. Add tests

3. Export from `services/__init__.py`

4. Add environment variables to `config.py`

## Testing Guidelines

### Test Structure

```python
import pytest
from agentorchestrator import AgentOrchestrator

class TestMyFeature:
    """Tests for my feature."""
    
    @pytest.fixture
    def ao(self):
        """Create isolated orchestrator for testing."""
        return AgentOrchestrator(isolated=True)
    
    def test_basic_functionality(self, ao):
        """Test basic functionality works."""
        # Arrange
        @ao.step
        async def my_step(ctx):
            return {"result": "success"}
        
        # Act
        result = ao.run_step_sync("my_step")
        
        # Assert
        assert result["success"]
        assert result["output"]["result"] == "success"
```

### Testing Best Practices

1. **Use isolated orchestrators** - Prevents test pollution
2. **Test async code properly** - Use `pytest-asyncio`
3. **Mock external services** - Use `MockAgent` and `MockLLMClient`
4. **Test error cases** - Don't just test happy paths
5. **Keep tests focused** - One assertion per test when possible

## Documentation

### Documentation Style

- Use clear, concise language
- Include code examples
- Document all public APIs
- Add type hints to examples

### Building Documentation

```bash
# Install docs dependencies
pip install -e "agentorchestrator[docs]"

# Build docs
mkdocs build

# Serve locally
mkdocs serve
```

## Issue Tracking

We use the **beads** issue tracker (`bd` command):

```bash
# See available issues
bd ready

# Start working on an issue
bd update <id> --status in_progress

# Close an issue
bd close <id>

# Create a new issue
bd create --title "Description" --priority 1
```

## Getting Help

- Check existing documentation
- Search closed issues
- Ask in discussions
- Tag maintainers in PR comments

## Code of Conduct

- Be respectful and inclusive
- Focus on constructive feedback
- Help others learn and grow
- Follow project guidelines

Thank you for contributing!
