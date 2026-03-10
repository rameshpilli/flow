# Polecat Swarm User Docs (with gastown-gui)

## What is now integrated

The platform now includes:

- Mayor API convoy/event endpoints for GUI consumption:
  - `GET /convoys`
  - `GET /pipeline/{convoy_id}`
  - `WS /ws/swarm-events`
- Pod-side `SwarmLogBridge` that forwards `SwarmLogger` JSON events to Mayor API.
- `MAYOR_WS_URL` env propagation in sling/crd paths.

## Quick local test (no Kubernetes required)

1. Run focused tests:

```bash
.venv/bin/pytest -q \
  tests/test_polecat_swarm_swarm_config.py \
  tests/test_polecat_swarm_bead_state_manager.py \
  tests/test_polecat_swarm_swarm_logger.py \
  tests/test_polecat_swarm_configmap_store.py \
  tests/test_polecat_swarm_mayor_events.py
```

2. Start Mayor API locally:

```bash
export BEADS_REPO_ROOT=/Users/rameshpilli/.claude-worktrees/flow/thirsty-pasteur
export GT_WORKSPACE=$HOME/gt
export POLECAT_NAMESPACE=gastown-workers
.venv/bin/uvicorn agentorchestrator.integrations.gastown.mayor_api:app --host 0.0.0.0 --port 8787
```

3. Verify health and convoy endpoints:

```bash
curl -s http://127.0.0.1:8787/health | jq .
curl -s http://127.0.0.1:8787/convoys | jq .
```

## Dispatch flow test (with bead)

1. Create bead (repo contains `.beads`):

```bash
bd --sandbox create "Swarm GUI smoke" --type task -p 2 --description "Test GUI convoy updates" --json
```

2. Preview pipeline:

```bash
curl -sS -X POST http://127.0.0.1:8787/chat/plan \
  -H 'content-type: application/json' \
  -d '{"bead_id":"<BEAD_ID>","repo_url":"<REPO_URL>"}' | jq .
```

3. Dispatch:

```bash
curl -sS -X POST http://127.0.0.1:8787/chat \
  -H 'content-type: application/json' \
  -d '{"bead_id":"<BEAD_ID>","repo_url":"<REPO_URL>","rig":"myproject"}' | jq .
```

4. Watch convoy state:

```bash
watch -n 1 "curl -s http://127.0.0.1:8787/convoys | jq ."
```

## UI walkthrough (what to click)

1. Start Mayor API (`8787`) and gastown-gui (`7667`).
2. Open `http://localhost:7667`.
3. Click `Pipeline` tab.
4. Confirm convoy cards appear from `GET /api/swarm/convoys`.
5. Open `Mayor Output` (eye icon near command bar).
6. Scroll up in Mayor Output and wait 2-3 seconds:
   - It should stay where you scrolled.
   - It should only auto-scroll if you are already near the bottom.
7. Click `Crews` tab:
   - Empty state is expected if no crew exists.
   - This does not block bead dispatch.
8. Trigger dispatch:

```bash
BEAD_ID=$(bd --sandbox create "Swarm GUI E2E" --type task -p 2 --description "Validate GUI flow" --json | jq -r '.id // .[0].id')
curl -sS -X POST http://127.0.0.1:8787/chat \
  -H 'content-type: application/json' \
  -d "{\"bead_id\":\"$BEAD_ID\",\"repo_url\":\"<REPO_URL>\",\"rig\":\"myproject\"}" | jq .
```

9. Re-open `Pipeline` tab and verify expert states move (`pending -> in_progress -> done/failed`).

## Crew, Rig, Polecat (quick definitions)

- `Rig`: project/repo container in Gastown (`gt rig add ...`).
- `Polecat`: worker runtime that executes work.
- `Crew`: optional group/workspace for coordinating multiple polecats.

You do not need a crew for Mayor dispatch to work. Creating a task/bead can run through Mayor + pipeline without creating any crew.

## gastown-gui hookup

Use your `gastown-gui` repo (`https://github.com/web3dev1337/gastown-gui`) and configure:

```bash
export MAYOR_API_URL=http://127.0.0.1:8787
export MAYOR_WS_URL=ws://127.0.0.1:8787/ws/swarm-events
```

Then apply the server/UI integration snippets from your AGENTS plan (proxy `/api/swarm/*` and bridge `/ws/swarm`).

## Troubleshooting

- Setup checks flip from green to red (`gt`/`bd`/workspace/rigs):
  - Ensure this shell PATH includes Go-installed CLIs:
    ```bash
    export PATH="$HOME/go/bin:$PATH"
    command -v gt && gt --version
    command -v bd && bd version
    ```
  - If `bd` is old (for example `0.47.x`), install latest:
    ```bash
    /opt/homebrew/bin/go install github.com/steveyegge/beads/cmd/bd@latest
    ```
  - Make sure GT workspace and rig exist:
    ```bash
    gt install ~/gt --git
    gt dolt init-rig myproject
    gt dolt start
    gt rig add myproject --adopt --force --url https://github.com/rameshpilli/flow.git
    ```
  - For `dolt` identity errors, set:
    ```bash
    dolt config --global --add user.name "rameshpilli"
    dolt config --global --add user.email "ramesh.pilli@hotmail.com"
    ```

- No convoy updates in UI:
  - Confirm pod has `MAYOR_WS_URL` in env.
  - Confirm Mayor API has active `WS /ws/swarm-events` connection.
- Convoy exists but expert status not moving:
  - Check pod logs for `expert_started` / `expert_completed` events.
  - Ensure `SwarmLogger` records are JSON and bridge dependency is available.
- `POST /chat` fails with `no route found for prefix` or `'... not found'` during `gt sling`:
  - Your bead store and rig are mismatched.
  - Start Mayor API with `BEADS_REPO_ROOT` pointing to the same rig bead DB you dispatch to.
  - Example:
    ```bash
    export BEADS_REPO_ROOT=$HOME/gt/myproject
    export GT_WORKSPACE=$HOME/gt
    .venv/bin/uvicorn agentorchestrator.integrations.gastown.mayor_api:app --host 0.0.0.0 --port 8787
    ```
  - Create the parent bead in that same store (example in `~/gt/myproject`) before `/chat`.
- Config not found in pod:
  - Verify `SWARM_CONFIG_REF` and `POLECAT_NAMESPACE` are injected.
