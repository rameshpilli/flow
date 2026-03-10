# Bridging Agent Orchestration into Gastown: Architecture Plan

## Context

**What exists today:**

1. **Agent Orchestration (AO)** — Python SDK for building AI agent pipelines with decorators (`@agent`, `@supervisor`, `@step`, `@chain`), DAG execution, middleware stacks, multi-agent patterns (SupervisorAgent, handoffs, ReAct), and enterprise services (LLM Gateway, Redis, MCP)

2. **Gastown** ([steveyegge/gastown](https://github.com/steveyegge/gastown)) — A real, working Go-based multi-agent orchestration system:
   - **Mayor**: Claude Code instance that coordinates agents
   - **Polecats**: Worker agents (Claude Code sessions) with persistent identity, ephemeral sessions
   - **Beads**: Git-backed issue tracking (`bd` CLI, bead IDs like `gt-abc12`)
   - **Hooks**: Git worktree-based persistent storage that survives crashes
   - **Convoys**: Work batches bundling multiple beads for parallel execution
   - **Rigs**: Project containers wrapping git repos
   - **Built-in runtimes**: claude, gemini, codex, cursor, auggie, amp, opencode, copilot, pi, omp
   - **CLI**: `gt install`, `gt sling`, `gt convoy create`, `gt mayor attach`, `gt feed`

3. **Gastown Operator** ([boshu2/gastown-operator](https://github.com/boshu2/gastown-operator)) — A real K8s operator:
   - **CRDs**: Rig, Polecat, Witness, Refinery, Convoy, BeadStore
   - **Polecat pods**: Only CRD that creates pods — runs pre-built Claude Code images
   - **kubectl-gt**: `kubectl gt sling <bead-id> <rig>`, `kubectl gt polecat logs`
   - **Witness**: Monitors polecat health, detects stuck workers (runs inside operator pod)
   - **Refinery**: Watches completed polecats, merges PRs after testing (runs inside operator pod)
   - **Helm chart**: `helm install gastown-operator oci://ghcr.io/boshu2/charts/gastown-operator`

4. **Deep Research** — Production AO pipeline (5-step DAG for M&A research), Dockerized with health probes. Proves AO pipelines can run in containers.

**The gap:** Gastown runs Claude Code CLI directly in Polecat pods. There's no way to run AO-built agent suites (supervisor + sub-agents + middleware) as Polecats. No cross-pod agent-to-agent communication. No way for teams to build specialized agent suites with AO and deploy them into the Gastown K8s infrastructure.

**The goal:** Teams build agent suites with AO (QE suite, Engineering suite, Architecture suite). Those suites run as Polecat pods in K8s via the Gastown Operator. The Mayor dispatches work. Agents collaborate across pods. PRs appear automatically.

---

## Architecture: AO as an Orchestration Layer Inside Polecats

### The Mental Model

```
Mayor (Gastown / Claude Code)
  │  dispatches via: gt sling <bead-id> <rig>
  │
  ├── Polecat Pod 1: QE Suite
  │   ┌──────────────────────────────────┐
  │   │ AO SupervisorAgent (QE Lead)     │
  │   │  ├── TestWriter (AO sub-agent)   │  ← calls LLM via LLMGatewayClient
  │   │  ├── TestRunner (AO sub-agent)   │  ← runs pytest, reports results
  │   │  └── BugAnalyzer (AO sub-agent)  │  ← analyzes code, finds root causes
  │   │                                  │
  │   │ Middleware: Logger, Cache,        │
  │   │   TokenManager, Reflection        │
  │   │                                  │
  │   │ MCP Server (for cross-pod calls) │
  │   └──────────────────────────────────┘
  │
  ├── Polecat Pod 2: Engineering Suite
  │   ┌──────────────────────────────────┐
  │   │ AO SupervisorAgent (Eng Lead)    │
  │   │  ├── Coder (AO sub-agent)        │
  │   │  ├── Reviewer (AO sub-agent)     │
  │   │  └── Refactorer (AO sub-agent)   │
  │   │                                  │
  │   │ MCP Server (for cross-pod calls) │
  │   └──────────────────────────────────┘
  │
  └── Cross-pod handoffs:
      QE Pod ──MCP──→ Engineering Pod
      Engineering Pod ──MCP──→ QE Pod
```

**Why AO wraps/orchestrates rather than replacing Claude Code:**
- AO's value is the orchestration layer: supervisor patterns, sub-agent coordination, middleware (caching, rate limiting, citation tracking), DAG execution
- Sub-agents within AO call LLMs directly via `LLMGatewayClient` → LiteLLM → Bedrock Claude
- AO adds structured multi-agent coordination that raw Claude Code sessions don't have
- Each team builds their agent suite with AO's decorators — they never know about Gastown internals

**Why Mayor stays as Gastown's Claude Code coordinator:**
- Mayor already works for task decomposition and convoy creation
- The immediate value is in the specialized AO agent suites
- Mayor dispatches via `gt sling` / convoy; AO suites execute
- Long-term: Mayor could optionally use AO SupervisorAgent for more structured MEOW planning

---

## The Five Bridge Pieces

### 1. AO Polecat Image — Packaging AO Suites for Gastown

Today's Polecat image has Claude Code pre-built. We need an AO variant.

**How it works:**
- Each AO agent suite is packaged as a Docker image
- The image includes: Python + AO + the team's agent code + a standard entrypoint
- The Gastown Operator creates Polecat pods using this image instead of the default Claude Code image

**Polecat CRD with AO runtime:**
```yaml
apiVersion: gastown.gastown.io/v1alpha1
kind: Polecat
metadata:
  name: qe-task-42
spec:
  rig: payments
  desiredState: Working
  kubernetes:
    image: registry.internal/ao-suites/qe-suite:1.0.0  # AO image
    gitRepository: "git@github.com:org/payments.git"
    gitSecretRef: { name: git-ssh-key }
    task:
      description: "Write tests for auth middleware fix (issue #42)"
      bead_id: "gt-abc12"
```

**Standard AO Polecat entrypoint** (`gastown/polecat/entrypoint.py`):
```python
# 1. Read task context from environment (bead_id, description, worktree path)
# 2. Initialize AO pipeline (import the team's agent suite)
# 3. Run the pipeline with task context as ChainContext
# 4. Commit/push changes, create PR
# 5. Update bead status via bd CLI or Beads API
```

**Dockerfile template:**
```dockerfile
FROM python:3.11-slim
RUN pip install agentorchestrator[mcp,redis]
COPY qe_suite/ /app/qe_suite/
COPY gastown_entrypoint.py /app/
WORKDIR /workspace
HEALTHCHECK CMD curl -f http://localhost:8080/health
CMD ["python", "/app/gastown_entrypoint.py"]
```

**What needs building:**
- `gastown/polecat/entrypoint.py` — Standard entrypoint that reads Gastown context and runs AO pipeline (~200 lines)
- `gastown/polecat/Dockerfile.template` — Template Dockerfile for AO suites (~30 lines)
- CLI addition: `ao build --gastown` — Packages an AO suite into a Gastown-compatible image (~100 lines in AO CLI)

### 2. Agent Suite Manifest — Declaring Capabilities

Each AO suite includes a `gastown.yaml` that the operator reads:

```yaml
apiVersion: gastown/v1
kind: AgentSuite
metadata:
  name: qe-suite
  version: 1.0.0
spec:
  entrypoint: qe_suite.pipeline:app
  group: qe
  capabilities: [test_generation, test_execution, bug_analysis]
  handoff_targets: [engineering-suite]
  resources:
    cpu: "2"
    memory: "4Gi"
  runtime:
    timeout_seconds: 600
    max_llm_tokens: 100000
```

**Generated from AO decorators** — capabilities come from `@ao.agent(capabilities=[...])`, group from `@ao.agent(group="qe")`.

**What needs building:**
- `gastown/manifest/parser.py` — Reads gastown.yaml (~100 lines)
- `gastown/manifest/generator.py` — Auto-generates from AO registry metadata (~150 lines)

### 3. RemoteAgentProxy — Cross-Pod Agent Handoffs (THE CRITICAL PIECE)

When QE Agent (Pod A) needs Engineering Agent's help, it must work transparently.

**The mechanism:**
- AO's `SupervisorAgent` calls `send_messages(recipient="EngineeringAgent", ...)`
- The supervisor's `team` list includes a `RemoteAgentProxy("EngineeringAgent", mcp_url="http://eng-svc:8080/mcp")`
- `RemoteAgentProxy` implements AO's `Agent` interface but forwards requests over MCP
- AO's existing `MCPToolAdapter` handles the HTTP transport
- The supervisor never knows the agent is remote

**RemoteAgentProxy** (lives in Gastown layer, NOT in AO core):
```python
class RemoteAgentProxy(Agent):
    """Makes a remote AO agent suite look like a local Agent."""

    def __init__(self, name, description, mcp_url, capabilities):
        super().__init__(AgentOptions(name=name, description=description))
        self.mcp_url = mcp_url
        self._adapter: MCPToolAdapter  # AO's existing MCP client

    async def process_request(self, input_text, user_id, session_id, chat_history, additional_params=None):
        result = await self._adapter.session.call_tool(
            "process_request",
            {"input_text": input_text, "context": additional_params or {}}
        )
        return ConversationMessage(role="assistant", content=[{"text": result}])
```

**Complete handoff flow:**
1. QE Lead LLM decides: "I need Engineering to review this code fix"
2. Calls `send_messages(recipient="EngineeringAgent", content="Review the auth fix in middleware.py")`
3. `SupervisorAgent._send_messages()` finds `RemoteAgentProxy("EngineeringAgent")` in team list
4. Proxy sends MCP `tools/call` to `http://eng-suite-svc:8080/mcp`
5. Engineering Pod's MCP server invokes its local Engineering SupervisorAgent
6. Engineering Supervisor delegates to Reviewer sub-agent, which reviews the code
7. Result flows back: Engineering Pod → MCP response → RemoteAgentProxy → QE Supervisor → QE Lead LLM
8. QE Lead continues with the review feedback

**Failure handling:** `RemoteAgentProxy` catches MCP errors, returns error message. AO's existing supervisor error handling in `_send_message_to_agent()` already handles this gracefully — the lead LLM receives the error and decides next steps.

**How proxies get injected:**
- The Gastown Polecat entrypoint reads `gastown.yaml` → sees `handoff_targets: [engineering-suite]`
- Queries K8s DNS or Agent Service Registry for engineering-suite's MCP URL
- Creates `RemoteAgentProxy` objects and adds them to the supervisor's `team` list
- User's agent code never changes

**What needs building:**
- `gastown/agents/remote_proxy.py` — RemoteAgentProxy class (~150 lines)
- `gastown/registry/service.py` — Redis-backed agent discovery for MCP URLs (~200 lines)
- Each AO Polecat pod runs an MCP server (reuse AO's existing `MCPServer` from `server/mcp.py`)

**What already exists in AO (reuse directly):**
- `MCPToolAdapter` + `MCPSession` — HTTP client for calling remote MCP endpoints
- `MCPServer` — Expose chains/agents as MCP tools with SSE streaming
- `SupervisorAgent._send_messages()` — Parallel delegation (already works with any Agent interface)
- `RedisEventBus` — Sideband channel for progress events across pods
- `RedisChatStorage` — Shared conversation memory across agents

### 4. Gastown Operator Extension — Supporting AO Polecat Images

The operator needs to support AO-based Polecat images alongside the default Claude Code image.

**Minimal changes to the Polecat CRD:**
```yaml
spec:
  kubernetes:
    image: registry.internal/ao-suites/qe-suite:1.0.0  # Custom image
    env:                                                 # AO-specific env vars
      - name: LLM_SERVER_URL
        valueFrom: { configMapKeyRef: { name: ao-config, key: llm_url } }
      - name: LLM_API_KEY
        valueFrom: { secretKeyRef: { name: ao-secrets, key: llm_key } }
    ports:
      - containerPort: 8080  # MCP server for cross-pod handoffs
    service:
      enabled: true          # Create K8s Service for MCP discovery
```

**What the operator needs to support:**
- Custom container images per Polecat (instead of only the pre-built Claude Code image)
- Environment variable injection for AO config (LLM gateway, Redis, etc.)
- K8s Service creation per AO Polecat (for MCP-based discovery)
- Health check routing to AO's `/health` endpoint

### 5. Beads Integration — Task Context Flow

Beads bridge Gastown's task tracking with AO's pipeline execution.

**Flow:**
```
Bead (gt-abc12) → gt sling → Polecat Pod → entrypoint reads bead → AO ChainContext
```

**The entrypoint translates Bead → AO context:**
```python
# In gastown_entrypoint.py
bead = subprocess.run(["bd", "--sandbox", "show", bead_id], capture_output=True)
bead_data = json.loads(bead.stdout)

context = {
    "task": bead_data["description"],
    "issue_id": bead_data["id"],
    "repo_path": "/workspace",
    "labels": bead_data.get("labels", []),
    "priority": bead_data.get("priority", 2),
}

result = await ao.launch("main_chain", context)

# After completion, update bead
subprocess.run(["bd", "--sandbox", "update", bead_id, "--status", "completed"])
subprocess.run(["bd", "--sandbox", "export"])
```

---

## What Already Exists vs. What Needs Building

### Exists in AO (reuse directly)
| Capability | File |
|-----------|------|
| SupervisorAgent (parallel delegation) | `squad/agents/supervisor.py` |
| FunctionAgent handoffs | `squad/agents/function_agent.py` |
| MCPToolAdapter (remote MCP client) | `utils/mcp_tool_adapter.py` |
| MCPServer (expose as MCP tools) | `server/mcp.py` |
| RedisEventBus (cross-pod events) | `core/event_bus.py` |
| AgentRegistry (capabilities, groups) | `core/registry.py` |
| DAGBuilder + DAGExecutor | `core/dag.py` |
| RedisChatStorage (shared memory) | `squad/storage/redis.py` |
| LLMGatewayClient (LLM calls) | `services/llm_gateway.py` |
| Deep Research Dockerfile pattern | `deep_research/Dockerfile` |

### Exists in Gastown/Operator (reuse directly)
| Capability | Where |
|-----------|-------|
| Mayor (task decomposition, convoy creation) | Gastown CLI |
| `gt sling` (dispatch work to polecats) | Gastown CLI |
| Convoy scheduling (parallel batches) | Gastown CLI + Operator CRD |
| Beads issue tracking (`bd` CLI) | Gastown ecosystem |
| Git worktree management (Hooks) | Gastown CLI |
| Polecat pod creation | Gastown Operator |
| Witness (health monitoring) | Gastown Operator |
| Refinery (PR merging) | Gastown Operator |
| kubectl-gt plugin | Gastown Operator |

### Needs building (bridge layer)
| Component | What | Est. Size |
|-----------|------|-----------|
| `gastown/polecat/entrypoint.py` | Standard AO Polecat entrypoint (reads bead, runs pipeline, commits) | ~200 lines |
| `gastown/polecat/Dockerfile.template` | Template for packaging AO suites | ~30 lines |
| `gastown/agents/remote_proxy.py` | RemoteAgentProxy (Agent → MCP bridge for cross-pod calls) | ~150 lines |
| `gastown/registry/service.py` | Redis-backed agent suite discovery (MCP URLs) | ~200 lines |
| `gastown/manifest/parser.py` | gastown.yaml parser | ~100 lines |
| `gastown/manifest/generator.py` | Auto-generate manifest from AO decorators | ~150 lines |
| AO CLI: `ao build --gastown` | Package AO suite into Gastown-compatible image | ~100 lines |
| Operator extension | Support custom images, env injection, K8s Service per Polecat | ~300 lines (Go) |

### Needs building in AO core (minimal)
| Component | What | Est. Size |
|-----------|------|-----------|
| `RedisRunStore` | Distributed checkpointing (follows existing RunStore interface) | ~150 lines |

---

## Phased Implementation

### Phase 1: Single AO Suite in Gastown (first demo)
**Goal**: Package one AO agent suite (e.g., Deep Research or a simple Engineering suite), deploy it as a Polecat pod via the operator, have it receive a bead task, execute, and create a PR.

Build:
- AO Polecat entrypoint (`entrypoint.py`)
- Dockerfile template
- gastown.yaml manifest format
- One example agent suite (Engineering: Coder + Reviewer)
- Operator extension: custom image support

Skip: Cross-pod handoffs, agent discovery, manifest auto-generation

**Verification**: `gt sling gt-abc12 payments` → Polecat pod starts with AO image → pipeline runs → PR appears

### Phase 2: Multi-Suite + Cross-Pod Handoffs
**Goal**: Multiple AO suites (QE + Engineering) running as separate Polecats, with cross-pod agent handoffs working transparently.

Build:
- RemoteAgentProxy
- Agent Service Registry (Redis)
- MCP server per AO Polecat
- Manifest auto-generation from decorators
- `ao build --gastown` CLI command
- RedisRunStore in AO core

**Verification**: Issue needing both code fix and tests → Engineering Polecat fixes code → hands off to QE Polecat via MCP → QE writes tests → both create PRs

### Phase 3: Scale + Production Hardening
**Goal**: KEDA autoscaling, cost controls, multi-repo, self-healing.

Build:
- KEDA ScaledObject for AO Polecats
- Cost controller (token budgets, pod limits)
- Observability dashboard
- Spawn mode (sub-agents in their own pods)
- Security hardening
- Mayor optionally using AO SupervisorAgent for structured MEOW planning

---

## Verification Plan

### Phase 1 end-to-end test
1. Build QE suite Docker image: `ao build --gastown --tag qe-suite:latest`
2. Deploy to K8s: `helm install gastown-operator ...` + apply Polecat CR with custom image
3. Create a bead: `bd create "Write unit tests for auth module" --type task`
4. Dispatch: `kubectl gt sling gt-abc12 payments`
5. Watch: `kubectl gt polecat logs payments/qe-task-42 -f`
6. Verify: PR appears with test files, bead status updated to completed

### Phase 2 end-to-end test
1. Deploy both QE and Engineering suites as separate Polecat deployments
2. Create bead: "Fix auth bug and add regression tests"
3. Mayor creates convoy with two tasks (Engineering first, then QE)
4. Engineering Polecat fixes bug, then calls QE via MCP for test verification
5. Verify: Two PRs (fix + tests), cross-pod MCP call logged, both beads completed

### Phase 3 end-to-end test
1. Create convoy with 20 beads
2. Verify KEDA scales to appropriate pod count
3. Verify cost limits enforced (max pods, max tokens per task)
4. Introduce a failure → verify auto-retry
5. Verify conflicting PRs auto-rebased by Refinery
