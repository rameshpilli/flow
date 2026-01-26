# Contributing to AgentOrchestrator

Thank you for contributing to AgentOrchestrator! This document defines the patterns and standards for extending the framework.

## Middleware Execution Order

Middleware intercepts step execution. The order of execution is determined by the `_ao_priority` attribute (default: 100). Lower numbers run earlier in the `before` phase and later in the `after` phase (onion pattern).

| Priority | Middleware | Purpose |
|----------|------------|---------|
| 10 | `MetricsMiddleware` | Track start/end times |
| 20 | `TracingMiddleware` | Start OTel spans |
| 30 | `CacheMiddleware` | Check for cached results |
| 50 | `TokenManager` | Track LLM usage |
| 100 | `LoggerMiddleware` | Log step execution |
| 200 | `OffloadMiddleware` | Handle large payloads |

To define priority:
```python
class MyMiddleware(BaseMiddleware):
    _ao_priority = 15
    async def before(self, ctx, step_name): ...
```

## Service Registration Pattern

All framework-level services should be placed in `agentorchestrator/services/`.

1. **Service Class**: Define a class that handles connections and operations.
2. **Configuration**: Use a dataclass in `config.py` for environment-driven settings.
3. **Singleton/Factory**: Provide a `get_<service>_client()` function for easy access.

Example:
```python
# agentorchestrator/services/my_service.py
class MyService:
    def __init__(self, config): ...

_instance = None
def get_my_service():
    global _instance
    if not _instance:
        _instance = MyService(get_config().my_service)
    return _instance
```

## Squad Agent Standards

Squad agents (`squad/agents/`) must follow these rules:
- Inherit from `Agent` base class.
- Support `user_id` and `session_id` for history isolation.
- Use `LLMGatewayClient` for all LLM calls to ensure unified token tracking and OAuth handling.
- Return `ConversationMessage` or an `AsyncIterable[AgentStreamResponse]`.

## Adding New Features

1. **Propose**: Create a `beads` issue (`bd create "My Feature"`) to discuss the design.
2. **Implement**: Add code following existing patterns.
3. **Test**: Add a unit test in `tests/`.
4. **Document**: Update docstrings and `AGENTS.md` if the feature is high-level.
