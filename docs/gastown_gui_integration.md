# gastown-gui Integration Guide for Polecat Swarm

This repo now exposes backend contracts needed by `gastown-gui`:

- `GET /convoys`
- `GET /pipeline/{convoy_id}`
- `WS /ws/swarm-events`

## Required UI-side additions

In `gastown-gui`:

1. Add HTTP proxy routes:
- `/api/swarm/convoys` -> `http://localhost:8787/convoys`
- `/api/swarm/pipeline/:convoy_id` -> `http://localhost:8787/pipeline/:convoy_id`

2. Add WebSocket bridge:
- Browser WS endpoint: `/ws/swarm`
- Upstream WS endpoint: `ws://localhost:8787/ws/swarm-events`

3. Add pipeline tab component:
- Convoy cards
- Expert step status (`pending|in_progress|success|failed|blocked`)
- Recent event log stream

## Event envelope used by backend

```json
{
  "type": "log_event",
  "trace_id": "convoy-0042",
  "payload": {
    "ts": 1741300003.5,
    "level": "INFO",
    "event": "expert_started",
    "trace_id": "convoy-0042",
    "span_id": "bd-pre-001",
    "sub_span_id": "",
    "role": "PRE",
    "repo": "pptx-agent",
    "elapsed_s": 0.5,
    "model": "claude-sonnet-4-5"
  }
}
```

## Pod env used for bridge

Pods receive `MAYOR_WS_URL` via sling env overrides.

Default:

```text
ws://mayor-api:8787/ws/swarm-events
```

Override in local testing:

```bash
export MAYOR_WS_URL=ws://127.0.0.1:8787/ws/swarm-events
```
