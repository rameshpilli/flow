# Polecat Swarm MVP: End-to-End Flow

## What users do

1. Build agents with AgentOrchestrator in their repo.
2. Add `.swarm/swarm.yaml` to declare expert pipeline, models, services, skills, and optional custom agents.
3. Create a bead in `.beads/issues.jsonl` (via `bd create ...`) with `repo_url`.
4. Call Mayor API `POST /chat/plan` to preview resolved pipeline.
5. Call Mayor API `POST /chat` to dispatch.
6. Monitor logs and bead notes while experts run (`PRE -> EES -> QES -> DE -> RE` plus custom roles).
7. Review artifacts in `.gastown/specs/<bead-id>/` and final `result.json`.

## What the platform does

1. Mayor API reads bead and clones repo at dispatch.
2. `SwarmConfigLoader` validates `.swarm/swarm.yaml`, pins `commit_sha`, resolves custom agents and skills.
3. Mayor creates sub-beads, writes `SwarmConfig` into `swarm-config-<bead-id>` reference.
4. Mayor slings first expert with `gt sling` and env contract (`EXPERT_ROLE`, `SWARM_CONFIG_REF`, next handoff IDs).
5. Pod entrypoint claims bead atomically (`bd update --claim`), checks out pinned SHA, and runs role pipeline.
6. Expert writes artifacts, returns gate scores, and updates bead state (`done`/`failed`/`blocked`).
7. On success, pod slings next expert; RE closes with release summary and optional PR metadata.

## Runtime contract

- Inputs:
  - `GASTOWN_BEAD_JSON` or `GASTOWN_BEAD_ID`
  - `EXPERT_ROLE`
  - `SWARM_CONFIG_REF`
  - `WORKTREE_PATH`
- Outputs:
  - `${GASTOWN_OUTPUT_DIR:-/output}/result.json`
  - role artifacts under `.gastown/specs/<bead-id>/`

## Important design rules

- Use `gt sling` for dispatch/handoff; no direct pod job creation in expert flow.
- Use `bd update --claim` for atomic bead claim.
- Keep `SWARM_CONFIG_REF` stable from Mayor to all pods for one convoy.
- Use `swarm/<bead-id>` branch naming for release isolation.

## Local dev notes

- `configmap_store.py` supports local fallback store (`SWARM_CONFIG_FORCE_LOCAL=true`) for test/dev without Kubernetes.
- `OpencodeExecutor` supports dry-run mode via `DryRunExecutor` for tests and planning.

## gastown-gui live pipeline support

- Mayor API now exposes:
  - `GET /convoys`
  - `GET /pipeline/{convoy_id}`
  - `WS /ws/swarm-events`
- Pod entrypoint forwards structured logger events to Mayor API over `MAYOR_WS_URL`.
- See [gastown_gui_integration.md](/Users/rameshpilli/.claude-worktrees/flow/thirsty-pasteur/docs/gastown_gui_integration.md) and [user_docs.md](/Users/rameshpilli/.claude-worktrees/flow/thirsty-pasteur/docs/user_docs.md) for UI hookup and end-to-end testing.
