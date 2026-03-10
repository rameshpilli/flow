"""Gateway router for model-family based LLM routing."""

from __future__ import annotations

import os
from dataclasses import dataclass

from agentorchestrator.services import LLMGatewayClient

CLAUDE_PREFIXES = ("claude",)
GPT_PREFIXES = ("gpt", "o1", "o3", "o4", "text-davinci", "chatgpt")


@dataclass
class GatewayConfig:
    name: str
    server_url: str
    oauth_endpoint: str
    client_id: str
    client_secret: str
    default_model: str
    verify_ssl: bool = True


class GatewayRouter:
    """Injectable gateway resolver used by experts."""

    def __init__(self, gateway_a: GatewayConfig, gateway_b: GatewayConfig | None = None):
        self._a = gateway_a
        self._b = gateway_b

    def client_for_model(self, model_name: str) -> LLMGatewayClient:
        cfg = self._resolve(model_name)

        # LLMGatewayClient currently reads SSL behavior from env.
        if not cfg.verify_ssl:
            os.environ["LLM_VERIFY_SSL"] = "false"

        return LLMGatewayClient(
            server_url=cfg.server_url,
            oauth_endpoint=cfg.oauth_endpoint,
            client_id=cfg.client_id,
            client_secret=cfg.client_secret,
            model_name=model_name or cfg.default_model,
        )

    def _resolve(self, model_name: str) -> GatewayConfig:
        model = (model_name or "").lower()
        use_b = any(model.startswith(prefix) for prefix in GPT_PREFIXES)
        if use_b and self._b is not None:
            return self._b
        return self._a

    @classmethod
    def from_env(cls) -> GatewayRouter:
        gateway_a = GatewayConfig(
            name="gateway_a",
            server_url=os.environ.get("LLM_GATEWAY_A_URL", os.environ.get("LLM_SERVER_URL", "")),
            oauth_endpoint=os.environ.get("LLM_GATEWAY_A_OAUTH_ENDPOINT", os.environ.get("LLM_OAUTH_ENDPOINT", "")),
            client_id=os.environ.get("LLM_GATEWAY_A_CLIENT_ID", os.environ.get("LLM_CLIENT_ID", "")),
            client_secret=os.environ.get("LLM_GATEWAY_A_CLIENT_SECRET", os.environ.get("LLM_CLIENT_SECRET", "")),
            default_model=os.environ.get("LLM_GATEWAY_A_DEFAULT_MODEL", "claude-sonnet-4-5"),
            verify_ssl=os.environ.get("LLM_GATEWAY_A_VERIFY_SSL", "true").lower() != "false",
        )

        gateway_b = None
        if os.environ.get("LLM_GATEWAY_B_URL"):
            gateway_b = GatewayConfig(
                name="gateway_b",
                server_url=os.environ["LLM_GATEWAY_B_URL"],
                oauth_endpoint=os.environ.get("LLM_GATEWAY_B_OAUTH_ENDPOINT", ""),
                client_id=os.environ.get("LLM_GATEWAY_B_CLIENT_ID", ""),
                client_secret=os.environ.get("LLM_GATEWAY_B_CLIENT_SECRET", ""),
                default_model=os.environ.get("LLM_GATEWAY_B_DEFAULT_MODEL", "gpt-4o"),
                verify_ssl=os.environ.get("LLM_GATEWAY_B_VERIFY_SSL", "true").lower() != "false",
            )

        return cls(gateway_a=gateway_a, gateway_b=gateway_b)
