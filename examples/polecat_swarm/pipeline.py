"""Role router for Polecat Swarm expert execution."""

from __future__ import annotations

from agentorchestrator import AgentOrchestrator
from examples.polecat_swarm.agents import (
    DocumentationExpert,
    EngineeringSupervisorExpert,
    ProductRequirementsExpert,
    QASupervisorExpert,
    ReleaseExpert,
)
from examples.polecat_swarm.gateway_router import GatewayConfig, GatewayRouter
from examples.polecat_swarm.types import ExpertResult

ROLE_TO_EXPERT = {
    "PRE": ProductRequirementsExpert,
    "EES": EngineeringSupervisorExpert,
    "QES": QASupervisorExpert,
    "DE": DocumentationExpert,
    "RE": ReleaseExpert,
}


def _default_gateway_router() -> GatewayRouter:
    try:
        return GatewayRouter.from_env()
    except Exception:
        fallback = GatewayConfig(
            name="gateway_a",
            server_url="",
            oauth_endpoint="",
            client_id="",
            client_secret="",
            default_model="claude-sonnet-4-5",
            verify_ssl=True,
        )
        return GatewayRouter(gateway_a=fallback)


def run_expert_pipeline(
    *,
    role: str,
    bead: dict,
    swarm_config,
    worktree: str,
    output_dir: str,
    repo_root: str,
) -> ExpertResult:
    """Execute one expert role inside the current pod."""
    if swarm_config:
        enabled_roles = {expert.role for expert in swarm_config.pipeline if expert.enabled}
        if role not in enabled_roles:
            return ExpertResult(status="success", notes=f"Role {role} disabled in swarm config")

    expert_cls = ROLE_TO_EXPERT.get(role)
    if not expert_cls:
        return ExpertResult(status="failed", notes=f"Unknown expert role: {role}")

    ao = AgentOrchestrator(name=f"polecat-{role.lower()}", isolated=True)
    gateway_router = _default_gateway_router()

    expert = expert_cls(
        ao=ao,
        bead=bead,
        swarm_config=swarm_config,
        worktree=worktree,
        repo_root=repo_root,
        gateway_router=gateway_router,
    )
    return expert.execute()
