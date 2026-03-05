# Middleware Selection Guide

Quick reference for choosing the right middleware.

## Decision Tree

```
What problem are you solving?
│
├── Large data exceeding context window
│   └── → [Large Response Handling](large_response_handling.md)
│
├── Preventing duplicate execution
│   └── → [Idempotency](idempotency.md)
│
├── Caching for speed
│   └── → CacheMiddleware
│
└── Rate limiting external APIs
    └── → RateLimiterMiddleware
```

## Quick Reference

| Middleware | Use For | Not For |
|------------|---------|---------|
| **TokenManagerMiddleware** | Managing total context budget | Single doc summarization |
| **SummarizerMiddleware** | Compressing large outputs | Token tracking |
| **RollingSummaryMiddleware** | Incremental updates | One-time compression |
| **OffloadMiddleware** | Storing large data externally | Small payloads |
| **IdempotencyMiddleware** | Preventing duplicate execution | Pure functions |
| **CacheMiddleware** | Speeding up repeated calls | Side effects |
| **RateLimiterMiddleware** | API rate limiting | Internal calls |

## Priority Order

| Middleware | Priority | Phase |
|------------|----------|-------|
| RateLimiterMiddleware | 1 | Blocks if exceeded |
| IdempotencyMiddleware | 5 | Skips if cached |
| LoggerMiddleware | 10 | Logging |
| TokenManagerMiddleware | 50 | Token tracking |
| SummarizerMiddleware | 60 | Compression |
| MetricsMiddleware | 90 | Final metrics |

## Detailed Guides

- **[Large Response Handling](large_response_handling.md)** - Comprehensive guide for TokenManager, Summarizer, Offload
- **[Idempotency](idempotency.md)** - Preventing duplicate execution
- **[Context Isolation](context_isolation.md)** - Multi-agent isolation
