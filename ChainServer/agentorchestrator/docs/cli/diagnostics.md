# Health & Diagnostics Commands

Commands for checking system health and diagnosing issues.

## health

Check health status of AgentOrchestrator.

```bash
ao health [options]
```

### Options

| Option | Short | Description |
|--------|-------|-------------|
| `--detailed` | `-d` | Run detailed checks including external dependencies |
| `--timeout` | `-t` | Timeout for each health check in seconds (default: 10) |
| `--json` | `-j` | Output as JSON |
| `--verbose` | `-v` | Show detailed component info |

### Examples

```bash
# Basic health check (quick)
ao health

# Detailed check with external dependencies
ao health --detailed

# With custom timeout
ao health --detailed --timeout 30

# JSON output
ao health --json
```

### Basic Health Check

Quick check without external dependencies:

```
══════════════════════════════════════════════════════
  AgentOrchestrator Health Check
══════════════════════════════════════════════════════

  Status: HEALTHY
  Version: 0.1.0
  Environment: development

  Checks:
    ✓ core_imports
    ✓ registry_available
    ✓ config_valid

══════════════════════════════════════════════════════
  Tip: Use --detailed for full dependency checks
══════════════════════════════════════════════════════
```

### Detailed Health Check

Includes external dependency checks (Redis, LLM, etc.):

```
════════════════════════════════════════════════════════════════
  AgentOrchestrator Health Check (Detailed)
════════════════════════════════════════════════════════════════

  Status: HEALTHY
  Version: 0.1.0
  Environment: development
  Total Latency: 234.56ms

  Summary:
    Healthy:   5
    Degraded:  0
    Unhealthy: 0

  Components:
    ✓ core: healthy (12.3ms)
    ✓ registry: healthy (5.2ms)
    ✓ config: healthy (3.1ms)
    ✓ redis: healthy (45.6ms)
      Connected to localhost:6379
    ✓ llm: healthy (168.3ms)
      Model: gpt-4 available

════════════════════════════════════════════════════════════════
```

### Health Statuses

| Status | Description |
|--------|-------------|
| `HEALTHY` | All checks passed |
| `DEGRADED` | Some optional dependencies unavailable |
| `UNHEALTHY` | Critical components failing |

---

## doctor

Diagnose common issues with AgentOrchestrator setup.

```bash
ao doctor
```

### What It Checks

1. **Python version** - Requires 3.10+
2. **Required dependencies** - pydantic, httpx
3. **Optional dependencies** - aiohttp, tiktoken, langchain, opentelemetry, structlog, redis
4. **Environment variables** - LLM_SERVER_URL/LLM_GATEWAY_URL, LLM_API_KEY or OAuth vars
5. **AgentOrchestrator imports** - Core module accessibility
6. **Circular import detection** - Checks for import issues
7. **Registered chain validation** - Validates all registered chains

### Example Output

```
    ___    ____
   /   |  / __ \
  / /| | / / / /
 / ___ |/ /_/ /
/_/  |_|\____/

  Your Agentic AI Workflow
  v0.1.0

══════════════════════════════════════════════════════
  AgentOrchestrator Doctor
══════════════════════════════════════════════════════

  ✅ Python version: 3.11.4
  ✅ pydantic: 2.5.0 (Data validation)
  ✅ httpx: 0.25.0 (HTTP client)
  ✅ aiohttp: 3.9.0 (Async HTTP client)
  ⚪ tiktoken: not installed (Token counting) - optional
  ⚪ langchain: not installed (LLM chains) - optional
  ✅ opentelemetry: 1.21.0 (Distributed tracing)
  ✅ structlog: 23.2.0 (Structured logging)
  ⚪ redis: not installed (Redis context store) - optional

  Environment Variables:
  ✅ LLM_SERVER_URL: https://llm-gateway.example.com/v1/chat/completions
  ⚪ LLM_GATEWAY_URL: not set (Alias for LLM_SERVER_URL) - optional
  ✅ LLM_API_KEY: ***key1
  ⚪ LLM_OAUTH_ENDPOINT: not set (OAuth token endpoint) - optional
  ⚪ LLM_CLIENT_ID: not set (OAuth client ID) - optional
  ⚪ LLM_CLIENT_SECRET: not set (OAuth client secret) - optional

  AgentOrchestrator Imports:
  ✅ AgentOrchestrator core imports successful
  ✅ No circular import issues detected

  Registered Chains:
  ✅ my_chain: valid
  ✅ other_chain: valid

══════════════════════════════════════════════════════
  Summary: 15/15 checks passed

  🎉 All checks passed! AgentOrchestrator is ready to use.
══════════════════════════════════════════════════════
```

### Exit Codes

| Code | Meaning |
|------|---------|
| `0` | All critical checks passed (warnings OK) |
| `1` | Critical issues found |

### Troubleshooting Common Doctor Issues

#### Issue: "pydantic not found"

```bash
# Install pydantic
pip install pydantic>=2.0.0
```

#### Issue: "LLM_API_KEY not set"

```bash
# Set your LLM API key
export LLM_API_KEY=sk-your-key-here

# Or use OAuth credentials instead
export LLM_OAUTH_ENDPOINT=https://auth.corp.com/token
export LLM_CLIENT_ID=your-client-id
export LLM_CLIENT_SECRET=your-secret
```

#### Issue: "Circular import detected"

This usually means there's a module importing another module that imports the first one. Check your custom step/agent files for:

```python
# Bad: Circular imports
# In agents.py
from steps import my_step  # my_step imports agents.py

# Good: Import inside function or use TYPE_CHECKING
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from steps import my_step
```

#### Issue: "Chain validation failed"

```bash
# Check chain details
ao check

# Visualize the chain to see dependencies
ao graph your_chain_name
```

#### Issue: "Redis connection failed"

```bash
# Check if Redis is running
redis-cli ping

# Verify REDIS_URL environment variable
echo $REDIS_URL

# Default if not set: redis://localhost:6379
```

---

## version

Show version information.

```bash
ao version [options]
```

### Options

| Option | Short | Description |
|--------|-------|-------------|
| `--json` | `-j` | Output as JSON |

### Examples

```bash
# Standard output
ao version

# JSON output
ao version --json
```

### Output

```
    ___    ____
   /   |  / __ \
  / /| | / / / /
 / ___ |/ /_/ /
/_/  |_|\____/

  Your Agentic AI Workflow

════════════════════════════════════════
  agentorchestrator v0.1.0
  Environment: development
════════════════════════════════════════
```

### JSON Output

```json
{
  "name": "agentorchestrator",
  "version": "0.1.0",
  "environment": "development"
}
```

---

## config

Show current configuration with secrets masked.

```bash
ao config [options]
```

### Options

| Option | Short | Description |
|--------|-------|-------------|
| `--json` | `-j` | Output as JSON |

### Examples

```bash
# Show config
ao config

# JSON output
ao config --json
```

### Output

```
══════════════════════════════════════════════════════
  AgentOrchestrator Configuration
══════════════════════════════════════════════════════

  environment: development
  debug: false
  llm_api_key: ***masked***
  llm_base_url: https://api.openai.com/v1
  redis_url: redis://localhost:6379
  log_level: INFO
  trace_enabled: false

══════════════════════════════════════════════════════
```

Sensitive values (API keys, tokens, passwords) are automatically masked for security.
