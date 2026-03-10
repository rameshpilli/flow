"""Polecat CRD manifest helper.

Used when consumers need to inspect/generated manifests outside `gt sling`.
"""

from __future__ import annotations

from typing import Any


def build_polecat_manifest(
    *,
    name: str,
    namespace: str,
    image: str,
    bead_id: str,
    rig: str,
    mayor_ws_url: str = "ws://mayor-api:8787/ws/swarm-events",
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build a minimal Polecat CRD-like manifest payload."""
    env_payload = dict(env or {})
    env_payload.setdefault("MAYOR_WS_URL", mayor_ws_url)
    env_items = [{"name": key, "value": value} for key, value in env_payload.items() if value]
    return {
        "apiVersion": "gastown.io/v1alpha1",
        "kind": "Polecat",
        "metadata": {
            "name": name,
            "namespace": namespace,
            "labels": {
                "bead-id": bead_id,
                "rig": rig,
                "app": "polecat-swarm",
            },
        },
        "spec": {
            "image": image,
            "beadId": bead_id,
            "rig": rig,
            "env": env_items,
        },
    }
