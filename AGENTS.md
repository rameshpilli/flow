# Agent Context: AgentOrchestrator Framework

> Context for AI agents. Describes what we're building and how to work with the code.

---

## What We're Building

**AgentOrchestrator** – a production-grade, DAG-based agent orchestration framework. Think LangChain or LlamaIndex, but with:

- Decorator-driven API (like Dagster)
- Built-in services configured via environment variables
- Users set config and build agents; we handle dependencies

**Goal**: Users tap into our services, set env vars, and build agents from simple to complex.

---

## Core Patterns

### Decorator Registration
```python
ao = AgentOrchestrator()

@ao.step(name="fetch", produces=["data"])
async def fetch(ctx: ChainContext): ...

@ao.agent(name="my_agent", capabilities=["search"])
class MyAgent(BaseAgent): ...

@ao.chain(name="pipeline")
class Pipeline:
    steps = ["fetch", "process"]
```

### Type-Safe State
```python
@ao.step(name="process", state_model=PipelineState)
async def process(ctx: Context[PipelineState]):
    async with ctx.edit_state() as state:
        state.counter += 1
    return {"count": ctx.state.counter}
```

### Context Scopes
- `ContextScope.STEP` – Auto-cleaned after step
- `ContextScope.CHAIN` – Lives for entire chain
- `ContextScope.GLOBAL` – Persists across executions

### Event-Driven Workflows
```python
@ao.event_handler("ResearchTask")
async def worker(ctx: Context, event: Event):
    return Event(type="Finding", payload={...})
```

### Squad Multi-Agent
- `MultiAgentOrchestrator` – Routes to best agent
- `SupervisorAgent` – Coordinates specialists
- `LLMGatewayAgent` – Single agent with LLM backend

---

## Key Files

| Need... | Look at... |
|---------|------------|
| Orchestration | `core/orchestrator.py`, `core/dag.py` |
| Context & state | `core/context.py`, `core/state.py` |
| Event workflows | `core/event_bus.py` |
| Middleware | `middleware/base.py`, `middleware/reflection.py` |
| LLM & vector | `services/llm_gateway.py`, `services/vector_store.py` |
| Multi-agent | `squad/orchestrator.py`, `squad/agents/supervisor.py` |
| ReAct & tools | `agents/react.py`, `agents/tools.py` |
| Examples | `examples/deep_research_agent.py`, `examples/supervisor_in_chain.py` |

---

## What's Implemented

DAG execution, Pydantic state, event-driven workflows, declarative DSL, middleware pipeline, LLM integration, vector store, multi-agent routing, supervisor pattern, ReAct, tool registry, agent reflection, dynamic DAG, run isolation, retry jitter, OpenTelemetry. See `core/`, `squad/`, `agents/`, `middleware/` for details.

---

## Roadmap

**Near-term**: Human-in-the-loop workflows, memory pattern strategies, workflow debugger UI, test coverage expansion.

**Partial**: Human-in-loop (needs `@ao.approval_step()`), memory patterns (Mem0 exists, needs strategies), debugger (ASCII/Mermaid only).

---

## Environment

See `agentorchestrator/.env.example`. Key vars: `LLM_*`, `CHAIN_*`, `CONTEXT_STORE_*`, `VECTOR_*`, `AO_ENABLE_TRACING`.

---

## How to Work

```bash
pip install -e "agentorchestrator[dev]"
pytest tests/ -v
ruff check agentorchestrator
```

**Adding features**: Middleware → `middleware/`, agents → `agents/` or `squad/agents/`, services → `services/`, step options → `core/decorators.py`.

---

## Bead Workflow (bd)

### Starting Work
```bash
bd --sandbox sync --import-only
bd --sandbox update <bead-id> --status in_progress
bd --sandbox show <bead-id>
```

### During Implementation
If you discover issues, create a bead: `bd --sandbox create "<Title>" --type <bug|task|feature> --priority <0-4> --description "..." --labels "..." --owner "Ramesh Pilli"`  
Priority: P0=critical, P1=important, P2=medium, P3-P4=backlog.

### Closing a Bead (MANDATORY)

1. **Add technical story notes** – Not just file lists. Explain approach, purpose, value:
   ```bash
   bd --sandbox update <bead-id> --append-notes "$(cat /tmp/notes.txt)"
   ```
   Notes must include: Approach (HOW), Purpose (WHY), Technical Details, Integration, Verification, Unblocks.

2. **Close bead**: `bd --sandbox close <bead-id> -r "Completed: <one-line summary>"`

3. **Export & commit** (include `.beads/issues.jsonl`):
   ```bash
   bd --sandbox export
   git add <files> .beads/issues.jsonl
   git commit -m "<Title>\n\nCompleted bead: <bead-id> - <Title>\n\n<Summary>\n\nCo-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
   git push
   ```

### Key Rules
- Every bead closure includes technical story notes (what + why)
- Always `bd --sandbox export` after closing
- Always commit `.beads/issues.jsonl` – bead state lives there
- Sync before ops: `bd --sandbox sync --import-only`
- Work is NOT complete until `git push` succeeds

### Quick Reference
```bash
bd --sandbox sync --import-only
bd --sandbox list
bd --sandbox show <id>
bd --sandbox update <id> --status in_progress
bd --sandbox close <id> -r "reason"
bd --sandbox export
```

<!-- BEGIN BEADS INTEGRATION -->
## Issue Tracking with bd (beads)

**IMPORTANT**: This project uses **bd (beads)** for ALL issue tracking. Do NOT use markdown TODOs, task lists, or other tracking methods.

### Why bd?

- Dependency-aware: Track blockers and relationships between issues
- Git-friendly: Dolt-powered version control with native sync
- Agent-optimized: JSON output, ready work detection, discovered-from links
- Prevents duplicate tracking systems and confusion

### Quick Start

**Check for ready work:**

```bash
bd ready --json
```

**Create new issues:**

```bash
bd create "Issue title" --description="Detailed context" -t bug|feature|task -p 0-4 --json
bd create "Issue title" --description="What this issue is about" -p 1 --deps discovered-from:bd-123 --json
```

**Claim and update:**

```bash
bd update <id> --claim --json
bd update bd-42 --priority 1 --json
```

**Complete work:**

```bash
bd close bd-42 --reason "Completed" --json
```

### Issue Types

- `bug` - Something broken
- `feature` - New functionality
- `task` - Work item (tests, docs, refactoring)
- `epic` - Large feature with subtasks
- `chore` - Maintenance (dependencies, tooling)

### Priorities

- `0` - Critical (security, data loss, broken builds)
- `1` - High (major features, important bugs)
- `2` - Medium (default, nice-to-have)
- `3` - Low (polish, optimization)
- `4` - Backlog (future ideas)

### Workflow for AI Agents

1. **Check ready work**: `bd ready` shows unblocked issues
2. **Claim your task atomically**: `bd update <id> --claim`
3. **Work on it**: Implement, test, document
4. **Discover new work?** Create linked issue:
   - `bd create "Found bug" --description="Details about what was found" -p 1 --deps discovered-from:<parent-id>`
5. **Complete**: `bd close <id> --reason "Done"`

### Auto-Sync

bd automatically syncs via Dolt:

- Each write auto-commits to Dolt history
- Use `bd dolt push`/`bd dolt pull` for remote sync
- No manual export/import needed!

### Important Rules

- ✅ Use bd for ALL task tracking
- ✅ Always use `--json` flag for programmatic use
- ✅ Link discovered work with `discovered-from` dependencies
- ✅ Check `bd ready` before asking "what should I work on?"
- ❌ Do NOT create markdown TODO lists
- ❌ Do NOT use external issue trackers
- ❌ Do NOT duplicate tracking systems

For more details, see README.md and docs/QUICKSTART.md.

## Landing the Plane (Session Completion)

**When ending a work session**, you MUST complete ALL steps below. Work is NOT complete until `git push` succeeds.

**MANDATORY WORKFLOW:**

1. **File issues for remaining work** - Create issues for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **PUSH TO REMOTE** - This is MANDATORY:
   ```bash
   git pull --rebase
   bd sync
   git push
   git status  # MUST show "up to date with origin"
   ```
5. **Clean up** - Clear stashes, prune remote branches
6. **Verify** - All changes committed AND pushed
7. **Hand off** - Provide context for next session

**CRITICAL RULES:**
- Work is NOT complete until `git push` succeeds
- NEVER stop before pushing - that leaves work stranded locally
- NEVER say "ready to push when you are" - YOU must push
- If push fails, resolve and retry until it succeeds

<!-- END BEADS INTEGRATION -->
