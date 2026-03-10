"""Internal services registry adapter for architecture context injection."""

from __future__ import annotations

import json
import os
from pathlib import Path

REGISTRY_PATH = os.getenv("SERVICES_REGISTRY_PATH", "/opt/corp-services-registry/templates")


def _load_yaml_like(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        loaded = yaml.safe_load(text)
        return loaded if isinstance(loaded, dict) else {}
    except ModuleNotFoundError:
        loaded = json.loads(text)
        return loaded if isinstance(loaded, dict) else {}


class ServiceTemplate:
    def __init__(self, name: str, data: dict):
        self.name = name
        self.description = str(data.get("description", ""))
        self.code_snippet = str(data.get("code_snippet", ""))
        self.usage_notes = str(data.get("usage_notes", ""))
        self.do_list = list(data.get("do", []))
        self.dont_list = list(data.get("dont", []))
        self.imports = list(data.get("imports", []))
        self.auth_pattern = str(data.get("auth_pattern", ""))

    def as_prompt_context(self) -> str:
        return (
            f"## {self.name} (Corporate Standard)\n"
            f"{self.description}\n\n"
            f"### Approved code pattern:\n"
            f"```python\n{self.code_snippet}\n```\n\n"
            f"### Auth pattern: {self.auth_pattern}\n"
            f"### Do: {', '.join(self.do_list)}\n"
            f"### Do NOT: {', '.join(self.dont_list)}\n"
            f"### Usage notes: {self.usage_notes}"
        )


class ServiceRegistry:
    def __init__(self, registry_path: str = REGISTRY_PATH):
        self._path = Path(registry_path)

    def fetch(self, service_name: str) -> ServiceTemplate | None:
        yaml_path = self._path / f"{service_name}.yaml"
        if not yaml_path.exists():
            return None
        return ServiceTemplate(service_name, _load_yaml_like(yaml_path))

    def fetch_many(self, service_names: list[str]) -> str:
        parts: list[str] = []
        found: list[str] = []
        not_found: list[str] = []

        for name in service_names:
            template = self.fetch(name)
            if template:
                found.append(name)
                parts.append(template.as_prompt_context())
            else:
                not_found.append(name)
                parts.append(
                    f"## {name}\n"
                    "(No corporate template found. Use project defaults and add TODO for platform review.)"
                )

        try:
            from examples.polecat_swarm.swarm_logger import SwarmLogger
            from examples.polecat_swarm.types import TraceContext

            dummy_log = SwarmLogger(TraceContext(trace_id="", span_id="", expert_role=""))
            dummy_log.info("services_fetched", requested=service_names, found=found, not_found=not_found)
        except Exception:
            # Keep service lookup lightweight and non-fatal even if logger context is absent.
            pass

        return "\n\n---\n\n".join(parts)

    def list_available(self) -> list[str]:
        if not self._path.exists():
            return []
        return sorted(path.stem for path in self._path.glob("*.yaml"))
