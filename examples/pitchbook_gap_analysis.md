# Pitchbook Workflow - Gap Analysis & Memory Architecture

## Summary

Analysis of AgentOrchestrator capabilities for the Pitchbook workflow, including the memory architecture for Global Settings.

---

## Memory Architecture

### Three-Tier Memory System

| Memory Type | Storage | Duration | Example Use | Pre-fetchable? |
|-------------|---------|----------|-------------|----------------|
| **Session Memory** | Redis | Short-term (TTL) | Current conversation | N/A |
| **Agent/Semantic Memory** | Mem0 | Long-term | User preferences, patterns | ✅ YES |
| **Reference Memory** | Cohere Compass (RAG) | Long-term | Document search, citations | ❌ NO |

### Global Settings Feature

Users can configure:
1. **General information** (text) → Mem0
2. **Additional instructions** (text) → Mem0
3. **Reference material** (docs) → RAG *(Phase 2 - later release)*

### The Pre-fetch Problem (and Solution)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           GLOBAL SETTINGS                               │
├────────────────────────────────────┬────────────────────────────────────┤
│  Instructions/Preferences          │  Reference Documents               │
│  "Always use formal tone"          │  Uploaded PDFs, Excel, PPT         │
│            │                       │            │                       │
│            ▼                       │            ▼                       │
│         MEM0                       │          RAG                       │
│    (Semantic Memory)               │   (Cohere Compass)                 │
│                                    │                                    │
│   ✅ PRE-FETCHABLE                 │   ❌ NOT PRE-FETCHABLE              │
│   (Always relevant)                │   (Need query context)             │
└────────────────────────────────────┴────────────────────────────────────┘
```

**Why can't we pre-fetch RAG?**
- RAG retrieval is query-dependent
- Without knowing the action ("edit slide for Apple"), we don't know what to search
- Mem0 preferences are always relevant regardless of the specific request

### The Flow

```
SESSION STARTS
    │
    └─→ Pre-fetch from Mem0 (preferences/instructions)
        └─→ Store in session context (Redis) ✅

        ⚠️ Cannot pre-fetch RAG - don't know what to search yet!

REQUEST ARRIVES: "Edit slide for Apple"
    │
    └─→ NOW we know: company=Apple, action=edit, context=slide content
        │
        └─→ Query RAG: "Apple" + slide context + instructions
            └─→ Get relevant document chunks ✅

EXECUTE WORKFLOW
    │
    └─→ Combine:
        ├─ Mem0 context (pre-fetched at session start)
        ├─ RAG context (queried at request time)
        └─ MCP data (News, SEC, CapIQ, etc.)
```

---

## What AgentOrchestrator Provides

### ✅ Already Available

| Feature | Status | Location |
|---------|--------|----------|
| **Multi-Agent Orchestration** | ✅ | `squad/` |
| Squad pattern with supervisor | ✅ | `squad/squad.py` |
| Parallel agent execution | ✅ | `max_concurrent_agents` |
| Agent handoffs | ✅ | `FunctionAgent` |
| **DAG-Based Workflows** | ✅ | `core/dag.py` |
| Decorator-based steps/chains | ✅ | `core/decorators.py` |
| Parallel step groups | ✅ | `parallel_groups` |
| Type-safe state (Pydantic) | ✅ | `core/state.py` |
| **RAG Integration** | ✅ | `services/vector_store.py` |
| Cohere Compass support | ✅ | `VectorStoreConfig` |
| Semantic search | ✅ | `query()` method |
| **Semantic Memory** | ✅ | `services/mem0.py` |
| Mem0 integration | ✅ | `Mem0Memory` class |
| Context retrieval | ✅ | `get_context_for_query()` |
| **MCP Connectivity** | ✅ | `connectors/mcp.py` |
| Tool discovery & invocation | ✅ | `MCPConnector` |
| **Session/Context Management** | ✅ | `core/context.py` |
| Scoped storage (STEP/CHAIN/GLOBAL) | ✅ | `ContextScope` |
| Redis-backed storage | ✅ | `services/redis.py` |

---

## ⚠️ Gaps / Feature Requests

### 1. **MCP Tool Registration in Agents** 🔴 HIGH PRIORITY

**Issue:** `LLMGatewayAgent` has a `tools` parameter but no clear mechanism to bind MCP tools.

**What's Needed:**
```python
agent = LLMGatewayAgent(LLMGatewayAgentOptions(
    name="NewsAgent",
    mcp_connectors=[MCPConnector(news_config)],  # Auto-discover tools
))
```

---

### 2. **Document Upload Service** 🔴 HIGH PRIORITY

**Issue:** Workflow requires uploading docs to S3 → indexing in Compass. No service exists.

**What's Needed:**
```python
from agentorchestrator.services import DocumentUploadService

upload_service = DocumentUploadService(
    s3_bucket="pitchbook-uploads",
    vector_store=rag_service,
)

doc_id = await upload_service.upload_and_index(
    file=file_bytes,
    filename="reference.pdf",
    user_id="user_123",
)
```

---

### 3. **GlobalSettingsService** 🟡 MEDIUM PRIORITY

**Issue:** Need a service to orchestrate global settings across Mem0 + RAG.

**Provided in Template:** `GlobalSettingsService` class handles:
- `save_global_settings()` → Store in Mem0
- `initialize_session()` → Pre-fetch from Mem0
- `get_reference_context()` → Query RAG at request time

---

### 4. **Session Context Auto-Propagation** 🟡 MEDIUM PRIORITY

**Issue:** `user_id`, `session_id` should auto-propagate through all steps.

**Status:** Partially exists via `ChainContext` but could be more explicit.

---

## Feature Request Summary

| Feature | Priority | Effort | Status |
|---------|----------|--------|--------|
| MCP Tool Registration in Agents | 🔴 High | Medium | Missing |
| Document Upload Service | 🔴 High | High | Missing |
| GlobalSettingsService | 🟡 Medium | Low | Template provided |
| Session Context Propagation | 🟡 Medium | Low | Partial |
| Company Identifier Resolution | 🟢 Low | Low | Use MCP |
| Agent-Level Caching | 🟢 Low | Low | Middleware exists |

---

## Recommended Architecture

### For Phase 1 (No Reference Material)

Just use **Mem0**:
- General info + instructions → Store in Mem0
- Pre-fetch at session start → Store in Redis/session
- Use in all workflows

```python
# Session start
session_context = await global_settings_service.initialize_session(user_id)
redis.set(f"session:{session_id}", json.dumps(session_context), ex=3600)

# Any request
session_context = json.loads(redis.get(f"session:{session_id}"))
result = await ao.launch("slide_edit_chain", {
    "request": request,
    "user_preferences": session_context["user_preferences"],
})
```

### For Phase 2 (With Reference Material)

Use **Mem0 + RAG**:
- Mem0 → Pre-fetch at session start (preferences)
- RAG → Query at request time (documents)

```python
# Session start - pre-fetch Mem0 only
session_context = await global_settings_service.initialize_session(user_id)

# Request arrives - NOW query RAG
rag_context = await global_settings_service.get_reference_context(
    query=f"{company} {slide_content}",
    user_id=user_id,
    document_ids=request.document_ids,
)
```

---

## Code Organization

```
pitchbook/
├── services/
│   ├── global_settings.py    # GlobalSettingsService
│   ├── document_upload.py    # DocumentUploadService (Phase 2)
│   └── company_resolver.py   # Company ID resolution
├── agents/
│   ├── mcp_agents.py         # MCPDataAgent implementations
│   └── content_agent.py      # Content generation
├── chains/
│   ├── slide_edit.py         # SlideEditChain
│   └── company_profile.py    # CompanyProfileChain
├── models/
│   ├── request.py            # SlideEditRequest, etc.
│   └── state.py              # PitchbookState
└── main.py                   # Entry points
```

---

## Quick Start

1. **Phase 1 (Now):** Use `Mem0Memory` for global settings
2. **Phase 2 (Later):** Add `VectorStoreService` for reference docs
3. **Use the template:** `pitchbook_workflow_template.py`
4. **Create GitHub issues** for missing features (MCP tools, upload service)
