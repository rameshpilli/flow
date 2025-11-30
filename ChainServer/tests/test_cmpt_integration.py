"""
Integration tests for the full CMPT (Client Meeting Prep Tool) Chain.

This tests the end-to-end flow from Context Builder -> Prioritization -> Response Builder,
ensuring all components wire together correctly even while using mocks.
"""

import pytest
from agentorchestrator import AgentOrchestrator
from agentorchestrator.services.context_builder import ContextBuilderService
from agentorchestrator.services.content_prioritization import ContentPrioritizationService
from agentorchestrator.services.response_builder import ResponseBuilderService
from agentorchestrator.services.models import ChainRequest, ChainRequestOverrides

@pytest.mark.asyncio
class TestCMPTIntegration:
    
    async def test_full_cmpt_flow_mocked(self):
        """
        Tests the full chain execution using the default mock implementations.
        This verifies that:
        1. ContextBuilder produces output compatible with Prioritization
        2. Prioritization produces output compatible with ResponseBuilder
        3. ResponseBuilder generates a final response
        """
        # 1. Setup
        forge = AgentOrchestrator(name="cmpt_test")
        
        # Initialize services (using default mocks)
        context_service = ContextBuilderService()
        prioritization_service = ContentPrioritizationService()
        response_service = ResponseBuilderService(
            use_llm_for_metrics=False,    # Disable LLM to avoid API calls
            use_llm_for_analysis=False,   # Disable LLM
            use_llm_for_content=False     # Disable LLM
        )

        # 2. Register Steps
        @forge.step(name="context_builder", produces=["context_output"])
        async def run_context(ctx):
            req = ctx.get("request")
            output = await context_service.execute(req)
            ctx.set("context_output", output)
            return {"company": output.company_name}

        @forge.step(name="prioritization", deps=["context_builder"], produces=["priority_output"])
        async def run_prioritization(ctx):
            context_out = ctx.get("context_output")
            output = await prioritization_service.execute(context_out)
            ctx.set("priority_output", output)
            return {"subqueries": len(output.subqueries)}

        @forge.step(name="response_builder", deps=["prioritization"], produces=["final_response"])
        async def run_response(ctx):
            context_out = ctx.get("context_output")
            priority_out = ctx.get("priority_output")
            output = await response_service.execute(context_out, priority_out)
            ctx.set("final_response", output)
            return {"prepared_content": output.prepared_content}

        @forge.chain(name="cmpt_full_chain")
        class CMPTChain:
            steps = ["context_builder", "prioritization", "response_builder"]

        # 3. Execute
        request = ChainRequest(
            corporate_company_name="Apple Inc",
            meeting_datetime="2025-02-15T10:00:00Z",
            rbc_employee_email="test.user@rbc.com",
            overrides=ChainRequestOverrides(
                ticker="AAPL",
                fiscal_quarter="Q1"
            )
        )

        result = await forge.run("cmpt_full_chain", {"request": request})

        # 4. Verify
        assert result["success"] is True, f"Chain failed with error: {result.get('error')}"
        
        ctx = result["context"]
        
        # Verify Context Builder Output
        context_out = ctx["data"]["context_output"]
        assert context_out.company_info.ticker == "AAPL"
        assert context_out.temporal_context.fiscal_quarter == "1"
        
        # Verify Prioritization Output
        priority_out = ctx["data"]["priority_output"]
        assert len(priority_out.subqueries) > 0
        
        # Verify Response Builder Output
        final_response = ctx["data"]["final_response"]
        assert final_response.prepared_content is not None
        assert "Apple Inc" in final_response.prepared_content
        assert "Financial Highlights" in final_response.prepared_content

