# Changelog

All notable changes to AgentOrchestrator will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- ReAct (Reasoning + Acting) agent pattern with tool integration
- Centralized Tool Registry for agent tool management
- Event-driven workflow support with `@ao.event_handler()` decorator
- Type-safe state management with Pydantic `StateStore`
- Async-safe context updates with `async_set()` method
- Connection pooling for LLM Gateway client (httpx connection reuse)
- Configurable SSL verification for LLM Gateway (`LLM_VERIFY_SSL` env var)
- Context cleanup methods (`remove_context()`, `cleanup_old_contexts()`)
- OTEL tracing improvements: sampling rate, batch processor config
- Comprehensive test suite for LLM Gateway, Secrets, Middleware

### Changed
- Improved Redis EventBus error logging (now logs at ERROR level with event details)
- LLM Gateway client now properly closes HTTP connections with `close()` method
- Squad orchestrator uses lazy classifier initialization
- Updated documentation with comparison tables vs LangChain/LlamaIndex

### Fixed
- Memory leak in orchestrator context manager (contexts now properly cleaned up)
- Duplicate event emission in DAG executor for failed steps
- Missing `ContextScope` import in dag.py

### Security
- SSL verification is now configurable (was hardcoded to `verify=False`)
- Added warning logs when SSL verification is disabled

## [0.1.0] - 2026-01-25

### Added
- Initial release of AgentOrchestrator framework
- DAG-based step execution with automatic parallelization
- Multi-agent orchestration with `MultiAgentOrchestrator` and `SupervisorAgent`
- LLM Gateway client with OAuth and API key support
- Middleware pipeline (Cache, Logger, Rate Limiter, Circuit Breaker)
- Vector store integration (in-memory and Cohere Compass)
- Secret management (HashiCorp Vault and environment variables)
- OpenTelemetry distributed tracing
- CLI tools (`ao run`, `ao check`, `ao list`, `ao graph`)
- Project scaffolding templates

---

## Migration Guide

### From 0.0.x to 0.1.0

No breaking changes. This is the initial stable release.

### Deprecated Features

None at this time.

---

## Version History

| Version | Release Date | Python | Status |
|---------|-------------|--------|--------|
| 0.1.0 | 2026-01-25 | 3.10+ | Current |

---

## Reporting Issues

Found a bug or have a feature request? Please:

1. Check existing issues in the issue tracker
2. Create a new issue with:
   - AgentOrchestrator version
   - Python version
   - Steps to reproduce
   - Expected vs actual behavior
