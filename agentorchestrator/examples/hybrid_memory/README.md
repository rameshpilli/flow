# Hybrid Memory Architecture Example

This example demonstrates a sophisticated multi-agent AI system for pitchbook editing with a three-layer memory architecture.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         MEMORY ARCHITECTURE                              │
├─────────────────────┬─────────────────────┬─────────────────────────────┤
│   Session Memory    │   Long-term Memory  │   Reference Memory          │
│   (Redis)           │   (Mem0)            │   (Cohere Compass)          │
├─────────────────────┼─────────────────────┼─────────────────────────────┤
│ TTL: Configurable   │ Permanent           │ Project lifetime            │
│ Default: 24 hours   │                     │                             │
│                     │                     │                             │
│ - Current edits     │ - User preferences  │ - Reference documents       │
│ - Undo/redo states  │ - Company context   │ - Research materials        │
│ - Working drafts    │ - Writing patterns  │ - Source files              │
│ - Session context   │ - Approved templates│ - Citations                 │
└─────────────────────┴─────────────────────┴─────────────────────────────┘
```

## Configurable Session Retention (TTL)

Users can configure their own Redis retention period:

```python
from agentorchestrator.squad.storage.redis import RedisChatStorage

# 24-hour retention (default)
storage = RedisChatStorage(ttl_seconds=86400)

# 1-hour retention for short sessions
storage = RedisChatStorage(ttl_seconds=3600)

# 7-day retention for longer projects
storage = RedisChatStorage(ttl_seconds=604800)

# No expiration (persistent)
storage = RedisChatStorage(ttl_seconds=None)
```

Or via environment variable:
```bash
export SESSION_TTL_SECONDS=86400  # 24 hours
```

## Agent Team

| Agent | Responsibility |
|-------|----------------|
| **Orchestrator** | Coordinates workflow, manages user interactions |
| **DocumentParser** | Extracts text and structure from PPTX files |
| **ContextBuilder** | Synthesizes information into project context |
| **ContentGenerator** | Generates text based on instructions |
| **RefinementAgent** | Iterative improvement with self-critique |
| **CompassAgent** | Searches reference docs, provides citations |
| **MemoryManager** | Coordinates between all memory systems |

## Quick Start

```python
from agentorchestrator.examples.hybrid_memory_pitchbook import (
    PitchbookEditor,
    HybridMemoryConfig,
)

# Load config from environment
config = HybridMemoryConfig.from_env()

# Or configure manually
config = HybridMemoryConfig(
    # Session Memory (Redis)
    session_ttl_seconds=86400,  # 24 hours - USER CONFIGURABLE!
    redis_host="redis.corp.com",
    redis_port=6379,
    redis_password="secret",
    redis_ssl=True,

    # Long-term Memory (Mem0)
    mem0_host="https://mem0.corp.com",
    mem0_api_key="your-api-key",

    # Reference Memory (Cohere Compass)
    compass_url="https://compass.corp.com",
    compass_api_key="your-api-key",
    compass_index_name="pitchbook_references",

    # LLM
    llm_server_url="https://llm-gateway.corp.com/v1/chat/completions",
    llm_client_id="your-client-id",
    llm_client_secret="your-client-secret",
)

# Create editor
editor = PitchbookEditor(config)
await editor.initialize()

# Parse a pitchbook
context = await editor.parse_pitchbook("path/to/pitchbook.pptx")

# Edit a slide
result = await editor.edit_slide(
    user_id="user123",
    session_id="session456",
    slide_number=3,
    instruction="Make the financial projections more conservative and add disclaimers",
)

print(result["edited_content"])
```

## Environment Variables

### Session Memory (Redis)
| Variable | Description | Default |
|----------|-------------|---------|
| `SESSION_TTL_SECONDS` | Session retention in seconds | `86400` (24h) |
| `REDIS_HOST` | Redis server host | `localhost` |
| `REDIS_PORT` | Redis server port | `6379` |
| `REDIS_PASSWORD` | Redis password | - |
| `REDIS_SSL` | Enable TLS | `false` |

### Long-term Memory (Mem0)
| Variable | Description | Default |
|----------|-------------|---------|
| `MEM0_HOST` | Mem0 server URL | - |
| `MEM0_API_KEY` | Mem0 API key | - |

### Reference Memory (Cohere Compass)
| Variable | Description | Default |
|----------|-------------|---------|
| `COHERE_COMPASS_URL` | Compass server URL | - |
| `COHERE_COMPASS_API_KEY` | Compass API key | - |
| `COMPASS_INDEX_NAME` | Index name | `pitchbook_references` |

### LLM Gateway
| Variable | Description | Default |
|----------|-------------|---------|
| `LLM_SERVER_URL` | LLM Gateway endpoint | - |
| `LLM_CLIENT_ID` | OAuth client ID | - |
| `LLM_CLIENT_SECRET` | OAuth client secret | - |
| `LLM_MODEL_NAME` | Model to use | `gpt-4` |

## Running the Example

```bash
# Install dependencies
pip install agentorchestrator[all]
pip install python-pptx

# Set environment variables
export LLM_SERVER_URL="https://llm-gateway.corp.com/v1/chat/completions"
export SESSION_TTL_SECONDS=86400

# Run the demo
python -m agentorchestrator.examples.hybrid_memory_pitchbook

# Or with a sample PPTX
export DEMO_PPTX_PATH="path/to/sample.pptx"
python -m agentorchestrator.examples.hybrid_memory_pitchbook
```

## Memory Promotion Pattern

The system can automatically promote important session data to long-term memory:

```python
# In MemoryManagerAgent
await memory_manager.promote_to_longterm(
    content="User prefers conservative financial projections",
    metadata={"user_id": "user123", "type": "preference"},
    importance_score=0.9,  # Above threshold (0.8)
)
```

## Features Demonstrated

1. **Three-Layer Memory Architecture**
   - Session (Redis) with configurable TTL
   - Long-term (Mem0) for persistent knowledge
   - Reference (Compass) for document search

2. **Multi-Agent Coordination**
   - SupervisorAgent orchestrating team
   - Context isolation between agents
   - Shared memory for collaboration

3. **Self-Critique/Reflection**
   - ReflectionMiddleware for quality control
   - Iterative refinement cycles
   - Quality scoring (0.0-1.0)

4. **Citation Tracking**
   - CitationMiddleware for RAG pipelines
   - Source attribution from Compass

5. **Document Processing**
   - PPTX parsing with python-pptx
   - Slide content extraction
   - Metadata extraction
