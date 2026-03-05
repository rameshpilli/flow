# Deployment Guide

This guide covers deploying AgentOrchestrator in production environments.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Deployment Options](#deployment-options)
- [Scaling](#scaling)
- [Monitoring](#monitoring)
- [Troubleshooting](#troubleshooting)

## Prerequisites

### System Requirements

- Python 3.10 or higher
- 2GB+ RAM (depends on workload)
- Network access to LLM gateway and external services

### Dependencies

```bash
# Core installation
pip install agentorchestrator

# With all optional dependencies
pip install agentorchestrator[all]

# Specific extras
pip install agentorchestrator[redis,vault,otel]
```

## Configuration

### Environment Variables

Create a `.env` file or set environment variables:

```bash
# ═══════════════════════════════════════════════════════════════════
# LLM Configuration (Required)
# ═══════════════════════════════════════════════════════════════════
LLM_SERVER_URL=https://llm-gateway.corp.com/v1/chat/completions
LLM_MODEL_NAME=gpt-4

# Authentication (choose one)
# Option A: OAuth
LLM_OAUTH_ENDPOINT=https://auth.corp.com/oauth/token
LLM_CLIENT_ID=your-client-id
LLM_CLIENT_SECRET=your-client-secret

# Option B: API Key
LLM_API_KEY=sk-your-api-key

# SSL (production: true, dev with self-signed certs: false)
LLM_VERIFY_SSL=true

# ═══════════════════════════════════════════════════════════════════
# Chain Execution
# ═══════════════════════════════════════════════════════════════════
CHAIN_MAX_PARALLEL_STEPS=5
CHAIN_DEFAULT_TIMEOUT_MS=30000
CHAIN_ERROR_HANDLING=fail_fast  # continue, retry

# ═══════════════════════════════════════════════════════════════════
# Context Storage
# ═══════════════════════════════════════════════════════════════════
CONTEXT_STORE_BACKEND=redis  # memory, redis
CONTEXT_STORE_REDIS_HOST=redis.corp.com
CONTEXT_STORE_REDIS_PORT=6379
CONTEXT_STORE_REDIS_PASSWORD=your-redis-password

# ═══════════════════════════════════════════════════════════════════
# Vector Store (for RAG)
# ═══════════════════════════════════════════════════════════════════
VECTOR_PROVIDER=remote  # memory, remote
VECTOR_HOST=https://vector.corp.com/api
VECTOR_API_KEY=your-vector-api-key

# ═══════════════════════════════════════════════════════════════════
# Secret Management (optional - Vault)
# ═══════════════════════════════════════════════════════════════════
VAULT_URL=https://vault.corp.com
VAULT_TOKEN=your-vault-token

# ═══════════════════════════════════════════════════════════════════
# Observability
# ═══════════════════════════════════════════════════════════════════
AO_ENABLE_TRACING=true
AO_TRACE_SERVICE=my-agent-service
AO_TRACE_SAMPLING_RATE=0.1  # 10% sampling for high-throughput
AO_TRACE_BATCH_SIZE=512

# OTEL Collector endpoint
OTEL_EXPORTER_OTLP_ENDPOINT=https://otel-collector.corp.com:4317

# ═══════════════════════════════════════════════════════════════════
# Application
# ═══════════════════════════════════════════════════════════════════
LOG_LEVEL=INFO
SERVICE_VERSION=1.0.0
DEPLOYMENT_ENV=production
```

### Configuration File

For complex configurations, use a config file:

```python
# config.py
from agentorchestrator.config import Config

config = Config(
    llm_server_url="https://llm-gateway.corp.com/v1/chat/completions",
    llm_model_name="gpt-4",
    max_parallel_steps=10,
    enable_tracing=True,
)
```

## Deployment Options

### Docker

```dockerfile
# Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Health check
HEALTHCHECK --interval=30s --timeout=10s \
  CMD python -c "from agentorchestrator import AgentOrchestrator; print('ok')"

# Run application
CMD ["python", "-m", "your_app"]
```

```yaml
# docker-compose.yml
version: '3.8'

services:
  agent-service:
    build: .
    env_file: .env
    ports:
      - "8000:8000"
    depends_on:
      - redis
    deploy:
      replicas: 3
      resources:
        limits:
          memory: 2G
        reservations:
          memory: 512M

  redis:
    image: redis:7-alpine
    volumes:
      - redis-data:/data
    command: redis-server --appendonly yes

volumes:
  redis-data:
```

### Kubernetes

```yaml
# deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: agent-service
spec:
  replicas: 3
  selector:
    matchLabels:
      app: agent-service
  template:
    metadata:
      labels:
        app: agent-service
    spec:
      containers:
      - name: agent
        image: your-registry/agent-service:latest
        ports:
        - containerPort: 8000
        envFrom:
        - secretRef:
            name: agent-secrets
        - configMapRef:
            name: agent-config
        resources:
          requests:
            memory: "512Mi"
            cpu: "250m"
          limits:
            memory: "2Gi"
            cpu: "1000m"
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 10
          periodSeconds: 30
        readinessProbe:
          httpGet:
            path: /ready
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 10
```

```yaml
# configmap.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: agent-config
data:
  LLM_SERVER_URL: "https://llm-gateway.corp.com/v1/chat/completions"
  LLM_MODEL_NAME: "gpt-4"
  CHAIN_MAX_PARALLEL_STEPS: "5"
  AO_ENABLE_TRACING: "true"
  AO_TRACE_SAMPLING_RATE: "0.1"
```

### AWS Lambda

```python
# handler.py
from agentorchestrator import AgentOrchestrator

# Initialize outside handler for connection reuse
ao = AgentOrchestrator()

@ao.step(name="process")
async def process(ctx):
    return {"result": "processed"}

@ao.chain(name="lambda_chain")
class LambdaChain:
    steps = ["process"]

def handler(event, context):
    """AWS Lambda handler."""
    import asyncio
    
    async def run():
        ctx = ao.create_context("lambda-" + context.aws_request_id)
        try:
            result = await ao.launch("lambda_chain", ctx=ctx)
            return {"statusCode": 200, "body": result}
        finally:
            ao.remove_context(ctx.request_id)
    
    return asyncio.get_event_loop().run_until_complete(run())
```

## Scaling

### Horizontal Scaling

AgentOrchestrator supports horizontal scaling with Redis:

```python
# Use Redis for shared state
from agentorchestrator.squad.storage.redis import RedisChatStorage

storage = RedisChatStorage(
    redis_url="redis://redis.corp.com:6379",
    key_prefix="ao:chat:",
)

squad = Squad(
    supervisor=lead,
    agents=team,
    options=SquadOptions(storage=storage),
)
```

### Connection Pooling

LLM Gateway client uses connection pooling by default:

```python
client = LLMGatewayClient.from_env()

# Connection pool settings are automatic:
# - max_keepalive_connections: 10
# - max_connections: 20
# - keepalive_expiry: 30s

# Remember to close when done
await client.close()
```

### Rate Limiting

Protect upstream services:

```python
from agentorchestrator.middleware.rate_limiter import RateLimiterMiddleware

ao.add_middleware(RateLimiterMiddleware({
    "llm_call": {"requests_per_second": 10},
    "vector_search": {"requests_per_second": 50},
}))
```

### Circuit Breaker

Prevent cascade failures:

```python
from agentorchestrator.middleware.circuit_breaker import CircuitBreakerMiddleware

ao.add_middleware(CircuitBreakerMiddleware({
    "external_api": {
        "failure_threshold": 5,
        "reset_timeout": 60,
    },
}))
```

## Monitoring

### Health Checks

```python
from fastapi import FastAPI
from agentorchestrator import AgentOrchestrator

app = FastAPI()
ao = AgentOrchestrator()

@app.get("/health")
async def health():
    return {"status": "healthy"}

@app.get("/ready")
async def ready():
    # Check dependencies
    checks = {
        "llm_gateway": await check_llm_gateway(),
        "redis": await check_redis(),
    }
    all_ready = all(checks.values())
    return {
        "ready": all_ready,
        "checks": checks,
    }
```

### Metrics

Expose Prometheus metrics:

```python
from prometheus_client import Counter, Histogram, generate_latest

requests_total = Counter(
    "ao_requests_total",
    "Total requests",
    ["chain", "status"],
)

request_latency = Histogram(
    "ao_request_latency_seconds",
    "Request latency",
    ["chain"],
)

@ao.middleware
class MetricsMiddleware:
    async def after(self, ctx, step_name, result):
        requests_total.labels(
            chain=ctx.chain_name,
            status="success" if result.success else "error",
        ).inc()
        request_latency.labels(chain=ctx.chain_name).observe(
            result.duration_ms / 1000
        )
```

### Distributed Tracing

```python
from agentorchestrator.utils.tracing import configure_tracing

# Configure with OTLP exporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

configure_tracing(
    service_name="agent-service",
    exporter=OTLPSpanExporter(endpoint="otel-collector:4317"),
    sampling_rate=0.1,  # 10% sampling
)
```

### Logging

```python
import logging
import json

# Structured JSON logging for production
class JSONFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps({
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "message": record.getMessage(),
            "module": record.module,
            "request_id": getattr(record, "request_id", None),
        })

handler = logging.StreamHandler()
handler.setFormatter(JSONFormatter())
logging.getLogger("agentorchestrator").addHandler(handler)
```

## Troubleshooting

### Common Issues

#### 1. OAuth Token Refresh Failures

```
ERROR: Failed to fetch OAuth token: Connection refused
```

**Solutions:**
- Verify `LLM_OAUTH_ENDPOINT` is accessible
- Check client credentials are correct
- Ensure network allows outbound HTTPS

#### 2. Context Memory Leak

```
WARNING: High memory usage detected
```

**Solutions:**
- Call `ao.remove_context(request_id)` after processing
- Enable periodic cleanup:
  ```python
  # In a background task
  while True:
      ao.cleanup_old_contexts(max_age_seconds=3600)
      await asyncio.sleep(300)  # Every 5 minutes
  ```

#### 3. Redis Connection Issues

```
ERROR: Redis connection failed
```

**Solutions:**
- Verify Redis is running and accessible
- Check password in `CONTEXT_STORE_REDIS_PASSWORD`
- Ensure firewall allows Redis port (6379)

#### 4. Slow LLM Responses

```
WARNING: LLM call took 45000ms (timeout: 30000ms)
```

**Solutions:**
- Increase timeout: `CHAIN_DEFAULT_TIMEOUT_MS=60000`
- Check LLM gateway health
- Review prompt complexity
- Enable response streaming

### Debug Mode

Enable debug logging:

```python
import logging
logging.getLogger("agentorchestrator").setLevel(logging.DEBUG)
```

Or via environment:

```bash
export LOG_LEVEL=DEBUG
```

### Support

For production issues:
1. Check logs for error messages
2. Verify environment configuration
3. Test connectivity to dependencies
4. Review metrics and traces
5. Contact support with request IDs and traces
