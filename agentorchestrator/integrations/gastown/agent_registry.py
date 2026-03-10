"""Central agent registry resolver for custom expert pipelines."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

CENTRAL_REGISTRY_PATH = os.getenv("AGENT_REGISTRY_PATH", "/opt/agent-registry")


def _load_yaml_like(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        loaded = yaml.safe_load(text)
        return loaded if isinstance(loaded, dict) else {}
    except ModuleNotFoundError:
        # JSON is valid YAML 1.2 and keeps local tests dependency-light.
        loaded = json.loads(text)
        return loaded if isinstance(loaded, dict) else {}


class AgentRegistry:
    """Resolve `registry_ref` references to concrete pipeline module paths."""

    def __init__(self, path: str = CENTRAL_REGISTRY_PATH):
        self._path = Path(path)

    def resolve(self, registry_ref: str) -> str | None:
        parts = registry_ref.split("@", 1)
        agent_id = parts[0]
        version = parts[1] if len(parts) > 1 else "latest"
        if version == "latest":
            version = self._get_latest_version(agent_id)
        pipeline_path = self._path / "agents" / agent_id / version / "pipeline.py"
        return str(pipeline_path) if pipeline_path.exists() else None

    def list_agents(self) -> list[dict[str, Any]]:
        index_path = self._path / "registry.yaml"
        if not index_path.exists():
            return []
        raw = _load_yaml_like(index_path)
        agents = raw.get("agents", [])
        if isinstance(agents, list):
            return [a for a in agents if isinstance(a, dict)]
        return []

    def _get_latest_version(self, agent_id: str) -> str:
        for agent in self.list_agents():
            if str(agent.get("id")) == agent_id:
                return str(agent.get("latest") or "v1")
        return "v1"
