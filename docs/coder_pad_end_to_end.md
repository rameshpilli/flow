# Coder Pad End-to-End (Bead -> Mayor API -> Polecat -> Result)

This document explains the full local MVP flow from start to finish.

## What This System Is

This setup provides a bead-first autonomous coding flow:

1. User creates or references a bead.
2. User sends a request to a Mayor-style `/chat` API.
3. Mayor API dispatches a Kubernetes Job (Polecat).
4. Polecat runs the AO pipeline (`code -> qa -> docs -> test -> finalize`).
5. Mayor API reads result, updates bead, returns structured response.

## Components

- `Mayor API`:
  - File: `agentorchestrator/integrations/coder_pad_mvp/mayor_api.py`
  - Endpoints: `/health`, `/beads`, `/beads/{id}`, `/chat`
- `Polecat Runtime Entrypoint`:
  - File: `agentorchestrator/integrations/coder_pad_mvp/entrypoint.py`
  - Bead-only runtime contract
- `AO Pipeline + Supervisors`:
  - Files:
    - `examples/coder_pad_mvp/pipeline.py`
    - `examples/coder_pad_mvp/agents.py`
- `Beads Store`:
  - Source of truth via `bd`
  - Exported JSONL: `.beads/issues.jsonl`
- `Kubernetes Execution`:
  - Cluster: local `kind`
  - Work units: Kubernetes `Job` (one Polecat job per bead dispatch)

## Runtime Contract

### Mayor API env vars

- `BEADS_REPO_ROOT` (default: current directory)
- `POLECAT_NAMESPACE` (default: `default`)
- `POLECAT_IMAGE` (default: `polecat-mvp:local`)
- `MAYOR_API_HOST` (default: `0.0.0.0`)
- `MAYOR_API_PORT` (default: `8787`)

### Polecat env vars (set by Mayor API)

- `GASTOWN_BEAD_JSON` (preferred)
- `GASTOWN_BEAD_ID` (fallback identifier)
- `WORKTREE_PATH`
- `GASTOWN_OUTPUT_DIR`
- `POLECAT_TEST_CMD`
- `POLECAT_AUTOCOMMIT`

`GASTOWN_TASK_JSON` is intentionally not used in this Coder Pad bead-first flow.

## End-to-End Sequence

1. User calls `POST /beads` or passes an existing `bead_id` to `/chat`.
2. Mayor API loads bead details through `bd --sandbox show <id> --json`.
3. Mayor API builds and applies a Kubernetes Job manifest (`kubectl apply -f -`).
4. Polecat container starts and runs:
   - `python -m agentorchestrator.integrations.coder_pad_mvp.entrypoint`
5. Entrypoint resolves bead context and launches AO chain.
6. AO chain runs:
   - `ingest_task`
   - `run_coder_supervisor`
   - `build_context_from_code`
   - `run_qa_supervisor`
   - `run_docs_supervisor`
   - `execute_changes_and_tests`
   - `finalize_and_publish`
7. Polecat prints final JSON outcome to stdout.
8. Mayor API waits for job completion, fetches pod logs, parses final JSON.
9. Mayor API updates bead:
   - `status`: `closed` on success, `open` on failure
   - `notes`: suite summary
   - exports `.beads/issues.jsonl`
10. Mayor API returns a final response with:
   - `bead_id`
   - `job_name`, `pod_name`
   - `status`
   - `summary`
   - `outcome` payload

## Quick Start (Local Cluster)

1. Build and load image:

```bash
make coderpad-image-build
make coderpad-kind-load
```

2. Start Mayor API:

```bash
BEADS_REPO_ROOT="$(pwd)" \
POLECAT_NAMESPACE=default \
POLECAT_IMAGE=polecat-mvp:local \
make coderpad-mayor-run
```

3. Create a bead:

```bash
curl -sS -X POST http://127.0.0.1:8787/beads \
  -H 'content-type: application/json' \
  -d '{
    "title": "Build calculator with docs",
    "description": "Create calculator app with CLI, tests, and docs",
    "issue_type": "task",
    "priority": 1,
    "labels": ["coder-pad","qa","docs"]
  }'
```

4. Dispatch via chat (replace bead id):

```bash
curl -sS -X POST http://127.0.0.1:8787/chat \
  -H 'content-type: application/json' \
  -d '{
    "bead_id": "REPLACE_WITH_BEAD_ID",
    "message": "Fix this bead",
    "wait_for_completion": true,
    "timeout_seconds": 300
  }'
```

5. Verify Kubernetes jobs/pods:

```bash
kubectl get jobs,pods -n default
```

6. Verify bead updated:

```bash
bd --sandbox show REPLACE_WITH_BEAD_ID --json
```

## What You Get Back

From `/chat`:

- final status (`closed` if successful)
- job + pod identifiers
- summary
- full `outcome` (chain result, QA/docs output, execution evidence)

From bead store:

- updated bead status
- summary in `notes`
- exported `.beads/issues.jsonl`

## Current MVP Limits

- Dispatch is direct via `kubectl` job creation, not `gt sling` yet.
- Coder/QA/docs behavior is deterministic scaffold logic.
- Pod does not include `bd`; bead updates happen in Mayor API process.
- Cross-pod remote handoff via MCP is not enabled in this flow.

## Next Upgrade Targets

1. Swap direct `kubectl` dispatch to real Gastown `gt sling`/convoy path.
2. Replace deterministic Coder/QA/Docs with LLM-driven agents (`local_llm`/gateway).
3. Add operator-managed service discovery for multi-pod handoffs.
4. Add stronger policy controls for command sandboxing and file scopes.
