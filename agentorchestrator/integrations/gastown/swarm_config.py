"""Swarm config models and loader for `.swarm/swarm.yaml`."""

from __future__ import annotations

import json
import logging
import os
from collections import defaultdict
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from .agent_registry import AgentRegistry

logger = logging.getLogger(__name__)

PLATFORM_DEFAULT_MODELS = {
    "PRE": "claude-sonnet-4-5",
    "EES": "claude-sonnet-4-5",
    "QES": "gpt-4o",
    "DE": "gpt-4-turbo",
    "RE": "gpt-4o",
}

PLATFORM_DEFAULT_PIPELINE = ["PRE", "EES", "QES", "DE", "RE"]

KNOWN_MODELS = {
    "claude-sonnet-4-5",
    "claude-opus-4",
    "claude-haiku-3-5",
    "gpt-4o",
    "gpt-4-turbo",
    "gpt-4o-mini",
    "o1",
    "o3",
}

SUPPORTED_SWARM_YAML_VERSIONS = {1}


class SwarmConfigError(ValueError):
    """Raised when swarm.yaml is invalid or unsafe to load."""


def _load_yaml_like(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        loaded = yaml.safe_load(text)
        return loaded if isinstance(loaded, dict) else {}
    except ModuleNotFoundError:
        # Accept JSON as YAML subset when PyYAML is not installed.
        try:
            loaded = json.loads(text)
        except json.JSONDecodeError as exc:
            raise SwarmConfigError(
                "PyYAML is required to parse non-JSON swarm.yaml files. "
                "Install pyyaml or provide JSON-compatible YAML."
            ) from exc
        return loaded if isinstance(loaded, dict) else {}


class ExpertConfig(BaseModel):
    role: str
    model: str
    enabled: bool = True
    is_custom: bool = False
    pipeline_module: str | None = None
    registry_ref: str | None = None
    description: str = ""
    insert_after: str | None = None
    depends_on: list[str] = Field(default_factory=list)

    @field_validator("model")
    @classmethod
    def model_must_be_known(cls, value: str) -> str:
        if value not in KNOWN_MODELS:
            raise ValueError(
                f"Unknown model '{value}'. Known models: {sorted(KNOWN_MODELS)}. "
                "Add it to KNOWN_MODELS once approved."
            )
        return value

    @field_validator("depends_on")
    @classmethod
    def no_empty_deps(cls, value: list[str]) -> list[str]:
        return [dep.strip() for dep in value if dep.strip()]


class SkillsConfig(BaseModel):
    platform_always: list[str] = Field(default_factory=list)
    per_role: dict[str, list[str]] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)

    def for_role(self, role: str) -> list[str]:
        return self.platform_always + self.per_role.get(role, [])


class SwarmConfig(BaseModel):
    repo_name: str
    repo_url: str
    commit_sha: str = ""
    language: str = "python"
    framework: str = ""
    test_command: str = "pytest"
    lint_command: str = ""
    docs_path: str = "docs/"
    main_branch: str = "main"
    services: list[str] = Field(default_factory=list)
    skills: SkillsConfig = Field(default_factory=SkillsConfig)
    pipeline: list[ExpertConfig] = Field(default_factory=list)
    trace_id: str = ""

    @model_validator(mode="after")
    def pipeline_roles_must_be_unique(self) -> SwarmConfig:
        roles = [expert.role for expert in self.pipeline]
        duplicates = [role for role in set(roles) if roles.count(role) > 1]
        if duplicates:
            raise SwarmConfigError(f"Duplicate roles in pipeline: {sorted(duplicates)}")
        return self

    @model_validator(mode="after")
    def depends_on_must_be_valid(self) -> SwarmConfig:
        enabled_roles = {e.role for e in self.pipeline if e.enabled}
        for expert in self.pipeline:
            if not expert.enabled:
                continue
            for dep in expert.depends_on:
                if dep == expert.role:
                    raise SwarmConfigError(
                        f"Expert '{expert.role}' cannot depend on itself"
                    )
                if dep not in enabled_roles:
                    raise SwarmConfigError(
                        f"Expert '{expert.role}' depends on unknown/disabled "
                        f"role '{dep}'. Available: {sorted(enabled_roles)}"
                    )
        return self

    def to_dependency_graph(self) -> dict[str, list[str]]:
        """Return {role: [dependency_roles...]} for passing to GT convoy.

        If no expert declares ``depends_on``, infer sequential order
        from the pipeline list (backward-compatible).
        """
        enabled = [e for e in self.pipeline if e.enabled]
        has_explicit = any(e.depends_on for e in enabled)

        graph: dict[str, list[str]] = {}
        for idx, expert in enumerate(enabled):
            if has_explicit:
                graph[expert.role] = list(expert.depends_on)
            else:
                # Sequential fallback: each depends on previous.
                graph[expert.role] = [enabled[idx - 1].role] if idx > 0 else []
        return graph

    def to_json(self) -> str:
        return self.model_dump_json()

    @staticmethod
    def from_json(data: str) -> SwarmConfig:
        return SwarmConfig.model_validate_json(data)


class SwarmConfigLoader:
    """Load and validate repo-level swarm configuration."""

    def __init__(self, agent_registry: AgentRegistry):
        self.agent_registry = agent_registry

    def load(
        self,
        repo_local_path: str,
        repo_url: str,
        commit_sha: str = "",
        trace_id: str = "",
    ) -> SwarmConfig:
        swarm_yaml_path = Path(repo_local_path) / ".swarm" / "swarm.yaml"
        if not swarm_yaml_path.exists():
            return self._default_config(repo_url, commit_sha, trace_id)

        raw = _load_yaml_like(swarm_yaml_path)

        version = raw.get("version")
        if version not in SUPPORTED_SWARM_YAML_VERSIONS:
            logger.error(
                "swarm_yaml_version_error version_found=%s supported=%s",
                version,
                sorted(SUPPORTED_SWARM_YAML_VERSIONS),
            )
            raise SwarmConfigError(
                f"Unsupported swarm.yaml version: {version!r}. "
                f"Supported: {sorted(SUPPORTED_SWARM_YAML_VERSIONS)}"
            )

        repo_cfg = raw.get("repo", {}) if isinstance(raw.get("repo", {}), dict) else {}
        experts = raw.get("experts", {}) if isinstance(raw.get("experts", {}), dict) else {}
        customs = raw.get("custom_agents", [])
        services = raw.get("services", [])
        skills_raw = raw.get("skills", {}) if isinstance(raw.get("skills", {}), dict) else {}

        pipeline_def = experts.get("pipeline", []) if isinstance(experts.get("pipeline", []), list) else []
        role_overrides: dict[str, dict[str, Any]] = {}
        for entry in pipeline_def:
            if isinstance(entry, dict) and entry.get("role"):
                role_overrides[str(entry["role"])] = entry

        expert_sequence: list[ExpertConfig] = []
        for role in PLATFORM_DEFAULT_PIPELINE:
            override = role_overrides.get(role, {})
            raw_deps = override.get("depends_on", [])
            depends_on = [str(d) for d in raw_deps] if isinstance(raw_deps, list) else []
            expert_sequence.append(
                ExpertConfig(
                    role=role,
                    model=str(override.get("model", PLATFORM_DEFAULT_MODELS[role])),
                    enabled=bool(override.get("enabled", True)),
                    depends_on=depends_on,
                )
            )

        custom_experts: list[ExpertConfig] = []
        for custom in customs if isinstance(customs, list) else []:
            if not isinstance(custom, dict):
                continue

            role = str(custom.get("role") or "").strip()
            if not role:
                raise SwarmConfigError("custom_agents entries must include a non-empty role")

            pipeline_module = custom.get("pipeline")
            if isinstance(pipeline_module, str) and pipeline_module and not os.path.isabs(pipeline_module):
                pipeline_module = str(Path(repo_local_path) / pipeline_module)

            registry_ref = custom.get("registry_ref")
            if isinstance(registry_ref, str) and registry_ref and not pipeline_module:
                pipeline_module = self.agent_registry.resolve(registry_ref)
                if not pipeline_module:
                    raise SwarmConfigError(f"Could not resolve custom agent registry_ref '{registry_ref}'")

            if isinstance(pipeline_module, str) and pipeline_module:
                _validate_agent_path(pipeline_module, repo_local_path)

            model = str(custom.get("model") or PLATFORM_DEFAULT_MODELS["EES"])
            custom_raw_deps = custom.get("depends_on", [])
            custom_depends = [str(d) for d in custom_raw_deps] if isinstance(custom_raw_deps, list) else []
            custom_experts.append(
                ExpertConfig(
                    role=role,
                    model=model,
                    enabled=bool(custom.get("enabled", True)),
                    is_custom=True,
                    pipeline_module=str(pipeline_module) if pipeline_module else None,
                    registry_ref=str(registry_ref) if isinstance(registry_ref, str) else None,
                    description=str(custom.get("description") or ""),
                    insert_after=str(custom.get("insert_after") or "") or None,
                    depends_on=custom_depends,
                )
            )

        final_pipeline = _insert_custom_agents(expert_sequence, custom_experts)

        platform_skills_path = os.getenv("PLATFORM_SKILLS_PATH", "/opt/corp-skills")
        skill_warnings: list[str] = []

        def resolve_skill(name: str) -> str | None:
            if os.path.isabs(name):
                return name if Path(name).exists() else None
            repo_skill = Path(repo_local_path) / ".swarm" / "skills" / f"{name}.md"
            if repo_skill.exists():
                return str(repo_skill)
            platform_skill = Path(platform_skills_path) / f"{name}.md"
            if platform_skill.exists():
                return str(platform_skill)
            return None

        def resolve_skill_list(names: list[str]) -> list[str]:
            resolved: list[str] = []
            for skill in names:
                path = resolve_skill(skill)
                if path:
                    resolved.append(path)
                else:
                    skill_warnings.append(skill)
            return resolved

        platform_declared = skills_raw.get("platform", [])
        platform_always = resolve_skill_list(platform_declared if isinstance(platform_declared, list) else [])

        per_role: dict[str, list[str]] = {}
        per_role_declared = skills_raw.get("per_role", {})
        if isinstance(per_role_declared, dict):
            for role, skill_list in per_role_declared.items():
                if isinstance(skill_list, list):
                    per_role[str(role)] = resolve_skill_list([str(item) for item in skill_list])

        logger.info(
            "skills_resolved resolved=%s missing=%s",
            sorted(platform_always + [s for vals in per_role.values() for s in vals]),
            sorted(skill_warnings),
        )

        services_list = [str(item) for item in services] if isinstance(services, list) else []
        repo_name = str(repo_cfg.get("name") or _repo_name_from_url(repo_url))

        return SwarmConfig(
            repo_name=repo_name,
            repo_url=repo_url,
            commit_sha=commit_sha,
            language=str(repo_cfg.get("language") or "python"),
            framework=str(repo_cfg.get("framework") or ""),
            test_command=str(repo_cfg.get("test_command") or "pytest"),
            lint_command=str(repo_cfg.get("lint_command") or ""),
            docs_path=str(repo_cfg.get("docs_path") or "docs/"),
            main_branch=str(repo_cfg.get("main_branch") or "main"),
            services=services_list,
            skills=SkillsConfig(
                platform_always=platform_always,
                per_role=per_role,
                warnings=skill_warnings,
            ),
            pipeline=final_pipeline,
            trace_id=trace_id,
        )

    def _default_config(self, repo_url: str, commit_sha: str, trace_id: str) -> SwarmConfig:
        pipeline = [ExpertConfig(role=role, model=PLATFORM_DEFAULT_MODELS[role]) for role in PLATFORM_DEFAULT_PIPELINE]
        return SwarmConfig(
            repo_name=_repo_name_from_url(repo_url),
            repo_url=repo_url,
            commit_sha=commit_sha,
            pipeline=pipeline,
            trace_id=trace_id,
        )


def _repo_name_from_url(repo_url: str) -> str:
    if not repo_url:
        return "unknown-repo"
    stripped = repo_url.rstrip("/")
    if stripped.endswith(".git"):
        stripped = stripped[:-4]
    return Path(stripped).name or "unknown-repo"


def _validate_agent_path(path: str, repo_local_path: str) -> None:
    central_registry_path = os.getenv("AGENT_REGISTRY_PATH", "/opt/agent-registry")
    allowed_roots = [
        os.path.realpath(os.path.join(repo_local_path, ".swarm", "agents")),
        os.path.realpath(central_registry_path),
    ]
    real_path = os.path.realpath(path)

    def _is_within(root: str, target: str) -> bool:
        try:
            return os.path.commonpath([root, target]) == root
        except ValueError:
            return False

    if not any(_is_within(root, real_path) for root in allowed_roots):
        logger.error(
            "agent_path_rejected path=%s reason=outside_allowed_roots allowed_roots=%s",
            path,
            allowed_roots,
        )
        raise SwarmConfigError(
            f"Custom agent path '{path}' (resolved '{real_path}') is outside allowed roots: "
            f"{allowed_roots}"
        )


def _insert_custom_agents(pipeline: list[ExpertConfig], customs: list[ExpertConfig]) -> list[ExpertConfig]:
    result = list(pipeline)
    by_anchor: dict[str, list[ExpertConfig]] = defaultdict(list)

    for custom in customs:
        by_anchor[custom.insert_after or "__end__"].append(custom)

    for anchor_role, agents in by_anchor.items():
        if anchor_role == "__end__":
            result.extend(agents)
            continue

        index = next((idx for idx, expert in enumerate(result) if expert.role == anchor_role), None)
        for offset, custom in enumerate(agents):
            insert_at = (index + 1 + offset) if index is not None else len(result)
            result.insert(insert_at, custom)

    return result
