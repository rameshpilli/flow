"""SwarmConfig transport using ConfigMap (with local fallback for development/tests).

This stores the SwarmConfig (pipeline definitions, repo metadata, skills)
so that pods can read shared config on startup.  Dependencies and execution
order are NOT stored here — GT uses bead-level ``bd depend`` and its own
convoy scheduler for that.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from .swarm_config import SwarmConfig

CONFIGMAP_LABEL = "app=polecat-swarm"
LOCAL_STORE_DIR = Path(os.getenv("SWARM_CONFIG_LOCAL_STORE", "/tmp/polecat-swarm-configmaps"))


def _kubectl_enabled() -> bool:
    force_local = os.getenv("SWARM_CONFIG_FORCE_LOCAL", "").strip().lower()
    if force_local in {"1", "true", "yes", "on"}:
        return False
    return shutil.which("kubectl") is not None


def _local_path(name: str) -> Path:
    LOCAL_STORE_DIR.mkdir(parents=True, exist_ok=True)
    return LOCAL_STORE_DIR / f"{name}.json"


def write_swarm_configmap(
    bead_id: str,
    swarm_config: SwarmConfig,
    namespace: str = "gastown-workers",
) -> str:
    """Persist SwarmConfig and return reference name.

    This stores pipeline config (models, skills, repo metadata) so pods
    can read it on startup.  Dependency information is carried on beads
    themselves via ``bd depend`` — not in this ConfigMap.
    """
    name = f"swarm-config-{bead_id}"
    config_payload = swarm_config.to_json()

    if _kubectl_enabled():
        manifest = {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {
                "name": name,
                "namespace": namespace,
                "labels": {"app": "polecat-swarm", "bead-id": bead_id},
            },
            "data": {"swarm_config.json": config_payload},
        }
        subprocess.run(
            ["kubectl", "apply", "-f", "-"],
            input=json.dumps(manifest),
            text=True,
            check=True,
            capture_output=True,
        )
        return name

    # Local fallback: store config as a JSON file.
    _local_path(name).write_text(config_payload, encoding="utf-8")
    return name


def read_swarm_configmap(configmap_name: str, namespace: str = "gastown-workers") -> SwarmConfig:
    """Read SwarmConfig from ConfigMap reference name."""
    if _kubectl_enabled():
        result = subprocess.run(
            [
                "kubectl",
                "get",
                "configmap",
                configmap_name,
                "-n",
                namespace,
                "-o",
                "jsonpath={.data.swarm_config\\.json}",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        return SwarmConfig.from_json(result.stdout)

    path = _local_path(configmap_name)
    if not path.exists():
        raise FileNotFoundError(f"Local swarm config reference not found: {configmap_name}")
    return SwarmConfig.from_json(path.read_text(encoding="utf-8"))


def delete_swarm_configmap(configmap_name: str, namespace: str = "gastown-workers") -> None:
    """Best-effort config cleanup."""
    if _kubectl_enabled():
        subprocess.run(
            ["kubectl", "delete", "configmap", configmap_name, "-n", namespace],
            capture_output=True,
            text=True,
            check=False,
        )
        return

    path = _local_path(configmap_name)
    if path.exists():
        path.unlink()
