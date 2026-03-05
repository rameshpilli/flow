"""
LLM Gateway Usage Info Discovery Test
=====================================

Run this test on your corporate machine to discover what usage/token info
your LLM gateway exposes. This will help determine:

1. Does the gateway return token counts after each call?
2. Does it expose cost information?
3. Does it provide rate limit headers?
4. What can your framework query vs track itself?

Usage:
    # Set your environment variables first
    export LLM_SERVER_URL="https://your-gateway/v1/chat/completions"
    export LLM_API_KEY="your-key"  # or OAuth credentials

    # Run the test
    python -m pytest tests/test_gateway_usage_info.py -v -s

    # Or run directly
    python tests/test_gateway_usage_info.py

Results will be printed showing exactly what your gateway provides.
"""

import asyncio
import json
import os
import sys
from dataclasses import dataclass
from typing import Any

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@dataclass
class GatewayCapabilities:
    """Summary of what the gateway exposes."""

    # Token info
    returns_prompt_tokens: bool = False
    returns_completion_tokens: bool = False
    returns_total_tokens: bool = False

    # Cost info
    returns_cost: bool = False
    returns_cost_per_token: bool = False

    # Rate limit info
    returns_rate_limit_headers: bool = False
    rate_limit_remaining: int | None = None
    rate_limit_reset: str | None = None

    # Model info
    returns_model_used: bool = False
    model_name: str | None = None

    # Timing info
    returns_processing_time: bool = False

    # Raw data for inspection
    raw_response: dict | None = None
    raw_headers: dict | None = None

    def to_report(self) -> str:
        """Generate a human-readable report."""
        lines = [
            "=" * 60,
            "LLM GATEWAY CAPABILITIES REPORT",
            "=" * 60,
            "",
            "TOKEN TRACKING:",
            f"  ✓ Prompt tokens:     {self.returns_prompt_tokens}",
            f"  ✓ Completion tokens: {self.returns_completion_tokens}",
            f"  ✓ Total tokens:      {self.returns_total_tokens}",
            "",
            "COST TRACKING:",
            f"  ✓ Returns cost:      {self.returns_cost}",
            f"  ✓ Cost per token:    {self.returns_cost_per_token}",
            "",
            "RATE LIMITING:",
            f"  ✓ Rate limit headers: {self.returns_rate_limit_headers}",
        ]

        if self.returns_rate_limit_headers:
            lines.append(f"    - Remaining: {self.rate_limit_remaining}")
            lines.append(f"    - Reset: {self.rate_limit_reset}")

        lines.extend([
            "",
            "MODEL INFO:",
            f"  ✓ Returns model used: {self.returns_model_used}",
        ])

        if self.model_name:
            lines.append(f"    - Model: {self.model_name}")

        lines.extend([
            "",
            "TIMING:",
            f"  ✓ Processing time:   {self.returns_processing_time}",
            "",
            "=" * 60,
            "RECOMMENDATION:",
        ])

        if self.returns_prompt_tokens and self.returns_completion_tokens:
            lines.append("  → Gateway provides token counts. Your framework can QUERY")
            lines.append("    the gateway for usage instead of tracking itself.")
            lines.append("  → Modify LLMGatewayClient to extract and return usage info.")
        else:
            lines.append("  → Gateway does NOT provide token counts.")
            lines.append("  → Your framework should track tokens using tiktoken")
            lines.append("    (already implemented in _estimate_tokens).")

        if self.returns_cost:
            lines.append("  → Gateway provides cost. No need to calculate yourself.")
        else:
            lines.append("  → Gateway does NOT provide cost. Calculate using token")
            lines.append("    counts × model pricing if needed.")

        if self.returns_rate_limit_headers:
            lines.append("  → Gateway provides rate limits. Use for request throttling.")

        lines.append("=" * 60)

        return "\n".join(lines)


async def test_gateway_capabilities_raw_httpx():
    """
    Test 1: Raw HTTP call to see exactly what the gateway returns.

    This bypasses LLMGatewayClient to see the raw response.
    """
    print("\n" + "=" * 60)
    print("TEST 1: Raw HTTP Response Inspection")
    print("=" * 60)

    try:
        import httpx
    except ImportError:
        print("ERROR: httpx not installed. Run: pip install httpx")
        return None

    server_url = os.getenv("LLM_SERVER_URL")
    api_key = os.getenv("LLM_API_KEY")
    model = os.getenv("LLM_MODEL_NAME", "gpt-4")

    if not server_url:
        print("ERROR: LLM_SERVER_URL not set")
        return None

    if not api_key:
        # Try OAuth
        oauth_endpoint = os.getenv("LLM_OAUTH_ENDPOINT")
        client_id = os.getenv("LLM_CLIENT_ID")
        client_secret = os.getenv("LLM_CLIENT_SECRET")

        if all([oauth_endpoint, client_id, client_secret]):
            print(f"Fetching OAuth token from {oauth_endpoint}...")
            async with httpx.AsyncClient(verify=False) as client:
                resp = await client.post(
                    oauth_endpoint,
                    data={
                        "grant_type": "client_credentials",
                        "client_id": client_id,
                        "client_secret": client_secret,
                        "scope": "read",
                    },
                )
                api_key = resp.json().get("access_token")
                print(f"Got OAuth token: {api_key[:20]}...")
        else:
            print("ERROR: No API key or OAuth credentials configured")
            return None

    print(f"Server URL: {server_url}")
    print(f"Model: {model}")
    print(f"API Key: {api_key[:10]}..." if api_key else "No API key")

    # Make a simple request
    payload = {
        "model": model,
        "messages": [
            {"role": "user", "content": "Say 'hello' and nothing else."}
        ],
        "max_tokens": 10,
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    capabilities = GatewayCapabilities()

    try:
        verify_ssl = os.getenv("LLM_VERIFY_SSL", "true").lower() != "false"
        async with httpx.AsyncClient(timeout=60.0, verify=verify_ssl) as client:
            print("\nSending test request...")
            response = await client.post(server_url, json=payload, headers=headers)

            print(f"\nHTTP Status: {response.status_code}")

            # Capture headers
            print("\n--- Response Headers ---")
            capabilities.raw_headers = dict(response.headers)

            # Check for rate limit headers (various naming conventions)
            rate_limit_keys = [
                "x-ratelimit-remaining",
                "x-rate-limit-remaining",
                "ratelimit-remaining",
                "x-ratelimit-remaining-requests",
                "x-ratelimit-remaining-tokens",
            ]

            for key in rate_limit_keys:
                if key in response.headers:
                    capabilities.returns_rate_limit_headers = True
                    capabilities.rate_limit_remaining = response.headers.get(key)
                    break

            reset_keys = ["x-ratelimit-reset", "x-rate-limit-reset", "ratelimit-reset"]
            for key in reset_keys:
                if key in response.headers:
                    capabilities.rate_limit_reset = response.headers.get(key)
                    break

            # Print interesting headers
            interesting_headers = [
                "x-ratelimit", "x-rate-limit", "ratelimit",
                "x-request-id", "x-ms-", "openai-",
                "x-model", "x-processing-ms",
            ]

            for header, value in response.headers.items():
                if any(h in header.lower() for h in interesting_headers):
                    print(f"  {header}: {value}")

            # Parse response body
            print("\n--- Response Body ---")
            data = response.json()
            capabilities.raw_response = data
            print(json.dumps(data, indent=2))

            # Check for usage info
            usage = data.get("usage", {})
            if usage:
                print("\n--- Usage Info Found! ---")
                print(json.dumps(usage, indent=2))

                capabilities.returns_prompt_tokens = "prompt_tokens" in usage
                capabilities.returns_completion_tokens = "completion_tokens" in usage
                capabilities.returns_total_tokens = "total_tokens" in usage
            else:
                print("\n--- No 'usage' field in response ---")

            # Check for cost info (some gateways add this)
            if "cost" in data:
                capabilities.returns_cost = True
                print(f"\n--- Cost Info Found: {data['cost']} ---")

            # Check for model info
            if "model" in data:
                capabilities.returns_model_used = True
                capabilities.model_name = data["model"]

            # Check for processing time
            if "processing_ms" in data or "x-processing-ms" in response.headers:
                capabilities.returns_processing_time = True

            return capabilities

    except httpx.HTTPStatusError as e:
        print(f"\nHTTP Error: {e}")
        print(f"Response: {e.response.text}")
        return None
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        return None


async def test_gateway_client_response():
    """
    Test 2: What your current LLMGatewayClient returns.

    This shows what info is currently accessible through your client.
    """
    print("\n" + "=" * 60)
    print("TEST 2: Current LLMGatewayClient Response")
    print("=" * 60)

    try:
        from agentorchestrator.services.llm_gateway import LLMGatewayClient
    except ImportError as e:
        print(f"ERROR: Could not import LLMGatewayClient: {e}")
        return

    client = LLMGatewayClient.from_env()

    if not client._is_configured():
        print("ERROR: LLMGatewayClient not configured (no server_url or auth)")
        return

    print(f"Server URL: {client.server_url}")
    print(f"Model: {client.model_name}")

    try:
        response = await client.generate_async(
            prompt="Say 'hello' and nothing else.",
            max_input_tokens=100,
        )

        print(f"\nResponse type: {type(response)}")
        print(f"Response value: {response}")
        print("\n--- Current client returns only the text content ---")
        print("    No usage/token info is extracted.")

    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await client.close()


async def test_gateway_agent_metrics():
    """
    Test 3: What metrics LLMGatewayAgent tracks.
    """
    print("\n" + "=" * 60)
    print("TEST 3: Current LLMGatewayAgent Metrics")
    print("=" * 60)

    try:
        from agentorchestrator.squad.agents.llm_gateway_agent import (
            LLMGatewayAgent,
            LLMGatewayAgentOptions,
        )
        from agentorchestrator.services.llm_gateway import LLMGatewayClient
    except ImportError as e:
        print(f"ERROR: Could not import agent: {e}")
        return

    client = LLMGatewayClient.from_env()

    if not client._is_configured():
        print("ERROR: LLMGatewayClient not configured")
        return

    agent = LLMGatewayAgent(LLMGatewayAgentOptions(
        name="TestAgent",
        description="Test agent for metrics inspection",
        llm_client=client,
    ))

    try:
        # Make a request
        from agentorchestrator.squad.types import ConversationMessage, ParticipantRole

        response = await agent.process_request(
            input_text="Say 'hello'",
            user_id="test-user",
            session_id="test-session",
            chat_history=[],
        )

        # Get metrics
        metrics = agent.get_metrics()

        print("\n--- Agent Metrics ---")
        print(json.dumps(metrics, indent=2))

        print("\n--- Analysis ---")
        print("Current metrics tracked:")
        print("  ✓ request_count")
        print("  ✓ error_count")
        print("  ✓ total_latency_ms")
        print("  ✓ avg_latency_ms")
        print("\nNOT tracked (could be added):")
        print("  ✗ total_prompt_tokens")
        print("  ✗ total_completion_tokens")
        print("  ✗ total_cost")

    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await client.close()


def print_modification_suggestions(capabilities: GatewayCapabilities | None):
    """Print code modification suggestions based on capabilities."""

    print("\n" + "=" * 60)
    print("SUGGESTED CODE MODIFICATIONS")
    print("=" * 60)

    if capabilities and capabilities.returns_prompt_tokens:
        print("""
1. Modify LLMGatewayClient._call_llm_api to return usage info:

   async def _call_llm_api(self, messages, **kwargs) -> tuple[dict, dict | None]:
       '''Returns (response_data, usage_info)'''
       ...
       response = await client.post(...)
       data = response.json()

       usage = data.get("usage")  # Extract usage
       return data, usage

2. Add a response wrapper class:

   @dataclass
   class LLMResponse:
       content: str
       usage: dict | None = None  # {prompt_tokens, completion_tokens, total_tokens}
       model: str | None = None
       latency_ms: float | None = None

3. Update generate_async to return LLMResponse:

   async def generate_async(self, prompt, ...) -> LLMResponse:
       data, usage = await self._call_llm_api(messages)
       return LLMResponse(
           content=data["choices"][0]["message"]["content"],
           usage=usage,
           model=data.get("model"),
       )

4. Update LLMGatewayAgent.get_metrics() to include token totals:

   def get_metrics(self):
       return {
           ...
           "total_prompt_tokens": self._total_prompt_tokens,
           "total_completion_tokens": self._total_completion_tokens,
       }
""")
    else:
        print("""
Gateway does NOT return token counts. Options:

1. KEEP using _estimate_tokens() for pre-call estimation (already implemented)

2. Track estimated tokens in agent metrics:

   # In process_request:
   estimated_tokens = self.llm_client._estimate_tokens(full_prompt)
   self._total_estimated_tokens += estimated_tokens

3. For accurate post-call counts, use tiktoken on the response too:

   response_tokens = self.llm_client._estimate_tokens(response_text)
   self._total_response_tokens += response_tokens
""")


async def main():
    """Run all tests and generate report."""
    print("\n" + "=" * 60)
    print("LLM GATEWAY USAGE INFO DISCOVERY")
    print("=" * 60)
    print("\nThis test will check what usage/token information your")
    print("corporate LLM gateway exposes in its API responses.\n")

    # Check environment
    server_url = os.getenv("LLM_SERVER_URL")
    if not server_url:
        print("ERROR: LLM_SERVER_URL environment variable not set.")
        print("\nSet your environment variables:")
        print("  export LLM_SERVER_URL='https://your-gateway/v1/chat/completions'")
        print("  export LLM_API_KEY='your-key'")
        print("  # OR for OAuth:")
        print("  export LLM_OAUTH_ENDPOINT='https://auth/token'")
        print("  export LLM_CLIENT_ID='your-client-id'")
        print("  export LLM_CLIENT_SECRET='your-secret'")
        return

    # Run tests
    capabilities = await test_gateway_capabilities_raw_httpx()
    await test_gateway_client_response()
    await test_gateway_agent_metrics()

    # Print report
    if capabilities:
        print("\n" + capabilities.to_report())

    # Print suggestions
    print_modification_suggestions(capabilities)


# For pytest
async def test_gateway_usage_discovery():
    """Pytest entry point."""
    await main()


if __name__ == "__main__":
    asyncio.run(main())
