# Deployment Guide

This guide covers deploying AgentOrchestrator applications in production environments.

## Deployment Architectures

### Single Process

Simplest deployment for low-traffic applications:

```
┌─────────────────┐
│   Application   │
│  + AgentOrch    │
│  + In-Memory    │
└─────────────────┘
```

**Pros:** Simple, no external dependencies
**Cons:** No horizontal scaling, state lost on restart

### With Redis Backend

Recommended for production:

```
┌─────────────────┐     ┌─────────────────┐
│   App Node 1    │     │   App Node 2    │
│  + AgentOrch    │────▶│  + AgentOrch    │
└────────┬────────┘     └────────┬────────┘
         │                       │
         └───────────┬───────────┘
                     │
              ┌──────▼──────┐
              │    Redis    │
              └─────────────┘
```

**Pros:** Shared state, horizontal scaling, persistence
**Cons:** Redis dependency, network latency

## Environment Configuration

### Required Variables

```bash
# LLM Gateway (required for AI features)
LLM_SERVER_URL=https://llm-gateway.example.com/v1/chat/completions
LLM_MODEL_NAME=claude-sonnet-4
LLM_OAUTH_ENDPOINT=https://auth.example.com/token
LLM_CLIENT_ID=your_client_id
LLM_CLIENT_SECRET=your_client_secret

# Or use API key instead of OAuth
# LLM_API_KEY=your_api_key

# SSL verification (default: true, set to "false" for self-signed certs)
# LLM_VERIFY_SSL=true
```

### Optional Variables

```bash
# Chain Execution
CHAIN_MAX_PARALLEL_STEPS=5
CHAIN_DEFAULT_TIMEOUT_MS=30000
CHAIN_ERROR_HANDLING=fail_fast

# Context Storage (for multi-process)
CONTEXT_STORE_BACKEND=redis
CONTEXT_STORE_REDIS_HOST=redis.example.com
CONTEXT_STORE_REDIS_PORT=6379
CONTEXT_STORE_REDIS_PASSWORD=your_password

# Observability
AO_ENABLE_TRACING=true
AO_TRACE_SERVICE=my_service
OTEL_EXPORTER_OTLP_ENDPOINT=https://otel.example.com:4317

# Secrets (HashiCorp Vault)
VAULT_ADDR=https://vault.example.com
VAULT_TOKEN=your_token
```

## Docker Deployment

### Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Install the package
RUN pip install -e .

# Run the application
CMD ["python", "-m", "your_app"]
```

### docker-compose.yml

```yaml
version: '3.8'

services:
  app:
    build: .
    ports:
      - "8000:8000"
    environment:
      - LLM_SERVER_URL=${LLM_SERVER_URL}
      - LLM_MODEL_NAME=${LLM_MODEL_NAME}
      - LLM_OAUTH_ENDPOINT=${LLM_OAUTH_ENDPOINT}
      - LLM_CLIENT_ID=${LLM_CLIENT_ID}
      - LLM_CLIENT_SECRET=${LLM_CLIENT_SECRET}
      - CONTEXT_STORE_BACKEND=redis
      - CONTEXT_STORE_REDIS_HOST=redis
    depends_on:
      - redis
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    volumes:
      - redis_data:/data
    restart: unless-stopped

volumes:
  redis_data:
```

## Kubernetes Deployment

### Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: agentorchestrator
spec:
  replicas: 3
  selector:
    matchLabels:
      app: agentorchestrator
  template:
    metadata:
      labels:
        app: agentorchestrator
    spec:
      containers:
      - name: app
        image: your-registry/agentorchestrator:latest
        ports:
        - containerPort: 8000
        envFrom:
        - secretRef:
            name: ao-secrets
        - configMapRef:
            name: ao-config
        resources:
          requests:
            cpu: "500m"
            memory: "512Mi"
          limits:
            cpu: "2000m"
            memory: "2Gi"
        livenessProbe:
          httpGet:
            path: /health/live
            port: 8000
          initialDelaySeconds: 10
          periodSeconds: 30
        readinessProbe:
          httpGet:
            path: /health/ready
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 10
```

### ConfigMap

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: ao-config
data:
  CHAIN_MAX_PARALLEL_STEPS: "5"
  CHAIN_DEFAULT_TIMEOUT_MS: "30000"
  CONTEXT_STORE_BACKEND: "redis"
  AO_ENABLE_TRACING: "true"
```

### Secret

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: ao-secrets
type: Opaque
stringData:
  LLM_SERVER_URL: "https://llm-gateway.example.com/v1/chat/completions"
  LLM_CLIENT_ID: "your_client_id"
  LLM_CLIENT_SECRET: "your_client_secret"
  CONTEXT_STORE_REDIS_PASSWORD: "your_redis_password"
```

## Health Checks

### FastAPI Integration

```python
from fastapi import FastAPI
from agentorchestrator.utils import is_ready, is_live, run_health_checks

app = FastAPI()

@app.get("/health/live")
async def liveness():
    """Kubernetes liveness probe."""
    return {"status": "ok" if is_live() else "error"}

@app.get("/health/ready")
async def readiness():
    """Kubernetes readiness probe."""
    return {"status": "ok" if await is_ready() else "error"}

@app.get("/health/detailed")
async def detailed_health():
    """Detailed health check for debugging."""
    return await run_health_checks()
```

## Production Checklist

### Pre-Deployment

- [ ] All tests passing
- [ ] Environment variables configured
- [ ] Secrets properly managed (not in code)
- [ ] Resource limits set
- [ ] Health checks configured
- [ ] Logging configured
- [ ] Tracing enabled (optional)

### Monitoring

- [ ] Application logs collected
- [ ] Metrics exported (Prometheus)
- [ ] Traces collected (Jaeger/Zipkin)
- [ ] Alerts configured
- [ ] Dashboards created

### Security

- [ ] TLS/HTTPS enabled
- [ ] Authentication configured
- [ ] Rate limiting in place
- [ ] Secrets rotated regularly
- [ ] Audit logging enabled

### Scaling

- [ ] Horizontal scaling tested
- [ ] Load balancing configured
- [ ] Connection pooling optimized
- [ ] Cache warming strategy
- [ ] Graceful shutdown implemented

## Graceful Shutdown

```python
import asyncio
import signal
from agentorchestrator import AgentOrchestrator

ao = AgentOrchestrator()

async def shutdown(sig, loop):
    """Handle shutdown signals."""
    print(f"Received exit signal {sig.name}...")
    
    # Stop accepting new requests
    # ...
    
    # Wait for in-flight requests
    await asyncio.sleep(5)
    
    # Cleanup resources
    await ao.cleanup_resources()
    
    # Stop the event loop
    loop.stop()

def main():
    loop = asyncio.get_event_loop()
    
    # Register signal handlers
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(
            sig,
            lambda s=sig: asyncio.create_task(shutdown(s, loop))
        )
    
    # Run your application
    loop.run_forever()

if __name__ == "__main__":
    main()
```

## Troubleshooting

### Common Issues

1. **Connection refused to Redis**
   - Check Redis host/port configuration
   - Verify network connectivity
   - Check firewall rules

2. **LLM timeouts**
   - Increase `LLM_TIMEOUT_SECONDS`
   - Check LLM gateway health
   - Verify OAuth token refresh

3. **Memory issues**
   - Enable auto context cleanup
   - Check for large payloads in context
   - Monitor with memory profiler

4. **High latency**
   - Check Redis connection pooling
   - Enable caching middleware
   - Profile slow steps

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for more details.
