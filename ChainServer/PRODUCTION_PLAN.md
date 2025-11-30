# FlowForge Production Readiness Plan

This document outlines the specific steps required to take FlowForge from a mock-backed prototype to a production-ready system.

## Phase 1: Interface Abstraction (Refactoring)

Currently, `ContextBuilderService` and `ResponseBuilderService` contain hardcoded mocks. We need to decouple the "what" (data needed) from the "how" (mock vs. real API).

### 1. Define Interfaces
Create `flowforge/interfaces.py` to define the contracts for external data:

```python
from abc import ABC, abstractmethod
from flowforge.services.models import CompanyInfo, PersonaInfo

class CompanyDataProvider(ABC):
    @abstractmethod
    async def get_company_info(self, name: str) -> CompanyInfo: ...

class PersonaProvider(ABC):
    @abstractmethod
    async def get_persona(self, email: str) -> PersonaInfo: ...

class EarningsProvider(ABC):
    @abstractmethod
    async def get_calendar(self, ticker: str) -> dict: ...
```

### 2. Implement Adapters
Create `flowforge/adapters/` to hold implementations:

*   **Mock Adapters**: Move current logic from `ContextBuilderService` to `flowforge/adapters/mock.py`.
*   **Real Adapters**: Implement `flowforge/adapters/zoominfo.py`, `flowforge/adapters/sec.py`, etc.

### 3. Dependency Injection
Update services to accept providers in `__init__`:

```python
class ContextBuilderService:
    def __init__(
        self, 
        company_provider: CompanyDataProvider,
        persona_provider: PersonaProvider
    ):
        self.company_provider = company_provider
        self.persona_provider = persona_provider
```

## Phase 2: Robustness & Error Handling

### 1. Circuit Breakers
Apply the existing `CircuitBreaker` utility to the **Real Adapters**.

```python
from flowforge.utils.circuit_breaker import CircuitBreaker

class ZoomInfoAdapter(PersonaProvider):
    @CircuitBreaker(failure_threshold=5, recovery_timeout=60)
    async def get_persona(self, email: str) -> PersonaInfo:
        # Real API call here
        ...
```

### 2. Structured Error Types
Define specific exceptions in `flowforge/exceptions.py` to handle API failures gracefully (e.g., `ProviderUnavailableError`, `RateLimitExceededError`) instead of generic `Exception`.

## Phase 3: Observability Integration

### 1. Instrument Services
Add the `@trace_span` decorator to all provider methods to visualize which external APIs are being called and how long they take.

```python
from flowforge.utils.tracing import trace_span

class ContextBuilderService:
    async def execute(self, request):
        with trace_span("context_builder", attributes={"company": request.company}):
            # ...
```

### 2. Health Checks
Implement a `/health` endpoint or CLI command that checks connectivity to all configured providers (ZoomInfo, DB, etc.) not just the service itself.

## Phase 4: Secrets Management

1.  **Secret Masking**: Ensure `ChainRequestOverrides` and logs never print raw API keys.
2.  **Configuration**: Update `flowforge/config.py` to load provider-specific secrets (e.g., `ZOOMINFO_API_KEY`, `SEC_API_KEY`).

## Migration Checklist

- [ ] Create `flowforge/interfaces.py`
- [ ] Extract mocks to `flowforge/adapters/mock.py`
- [ ] Refactor `ContextBuilderService` to use dependency injection
- [ ] Implement one real adapter (e.g., for Company Lookup)
- [ ] Add integration tests verifying the real adapter works (with VCR/cassettes for replay)

