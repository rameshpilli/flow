"""
Input Validation Example
========================

Demonstrates Pydantic-based input validation at chain and step level.

Usage:
    python input_validation.py                    # Valid input
    python input_validation.py --invalid          # Invalid input (validation error)
    python input_validation.py --step-validation  # Step-level validation

What this example demonstrates:
    - Chain-level input_model for fail-fast validation
    - Step-level input_model for per-step validation
    - Pydantic validators for custom rules
    - Catching validation errors

Expected output (valid):
    Validating meeting request...
    Processing meeting for: Acme Corp on 2024-03-15
    Generating agenda for Acme Corp...

    Result: SUCCESS
    Agenda: Discussion points for Acme Corp meeting

Expected output (invalid):
    Validation error: company must be at least 2 characters
"""

from __future__ import annotations

import argparse
import asyncio

from pydantic import BaseModel, Field, field_validator

from agentorchestrator import AgentOrchestrator
from agentorchestrator.core.validation import ContractValidationError


# =============================================================================
# Pydantic Models for Validation
# =============================================================================


class MeetingRequest(BaseModel):
    """
    Input model for meeting preparation requests.

    Pydantic validates this at chain launch time (fail-fast),
    so invalid requests never start processing.
    """

    company: str = Field(..., min_length=2, description="Company name")
    meeting_date: str = Field(..., description="Meeting date (YYYY-MM-DD)")
    attendees: list[str] = Field(default_factory=list, description="List of attendees")

    @field_validator("meeting_date")
    @classmethod
    def validate_date_format(cls, v: str) -> str:
        """Ensure date is in YYYY-MM-DD format."""
        import re

        if not re.match(r"^\d{4}-\d{2}-\d{2}$", v):
            raise ValueError("meeting_date must be in YYYY-MM-DD format")
        return v

    @field_validator("company")
    @classmethod
    def sanitize_company(cls, v: str) -> str:
        """Basic sanitization of company name."""
        # Remove potential injection attempts
        dangerous = ["<script>", "javascript:", "onclick"]
        for d in dangerous:
            if d.lower() in v.lower():
                raise ValueError("Invalid content in company name")
        return v.strip()


class AgendaRequest(BaseModel):
    """Input model for agenda generation step."""

    company: str
    topics: list[str] = Field(default_factory=list)


# =============================================================================
# Chain-Level Validation Example
# =============================================================================


def create_chain_validated_orchestrator() -> AgentOrchestrator:
    """
    Create orchestrator with chain-level input validation.

    The input_model on @ao.chain validates data at launch() time,
    before any steps execute. This is fail-fast validation.
    """
    ao = AgentOrchestrator(name="chain_validation", isolated=True)

    @ao.step(name="prepare")
    async def prepare(ctx):
        """Prepare meeting data."""
        # Input is already validated by chain-level input_model
        request = ctx.get("request")
        print(f"Processing meeting for: {request['company']} on {request['meeting_date']}")

        ctx.set("meeting_info", {
            "company": request["company"],
            "date": request["meeting_date"],
            "attendees": request.get("attendees", []),
        })
        return {"prepared": True}

    @ao.step(name="generate_agenda", deps=["prepare"])
    async def generate_agenda(ctx):
        """Generate meeting agenda."""
        info = ctx.get("meeting_info")
        print(f"Generating agenda for {info['company']}...")

        # In a real app, this might call an LLM
        agenda = f"Discussion points for {info['company']} meeting"
        ctx.set("agenda", agenda)
        return {"agenda": agenda}

    # Chain-level input_model - validated at launch() before any steps run
    @ao.chain(name="meeting_prep", input_model=MeetingRequest, input_key="request")
    class MeetingPrepChain:
        """
        Meeting preparation chain with input validation.

        The input_model parameter validates the 'request' key in initial data
        at chain launch time. If validation fails, no steps execute.
        """

        steps = ["prepare", "generate_agenda"]

    return ao


# =============================================================================
# Step-Level Validation Example
# =============================================================================


def create_step_validated_orchestrator() -> AgentOrchestrator:
    """
    Create orchestrator with step-level input validation.

    The input_model on @ao.step validates data when that specific
    step executes. The first step's input_model is also checked at
    chain launch for fail-fast validation.
    """
    ao = AgentOrchestrator(name="step_validation", isolated=True)

    # First step with input_model - validated at chain launch (fail-fast)
    @ao.step(name="validate_request", input_model=MeetingRequest, input_key="request")
    async def validate_request(ctx):
        """Validate and prepare request."""
        print("Validating meeting request...")
        request = ctx.get("request")

        # Request is already validated by input_model
        ctx.set("validated_request", {
            "company": request["company"],
            "date": request["meeting_date"],
        })
        return {"valid": True}

    # Mid-chain step with its own input_model
    # Note: This is validated when the step runs, not at chain launch
    @ao.step(name="create_agenda", deps=["validate_request"], input_model=AgendaRequest, input_key="agenda_input")
    async def create_agenda(ctx):
        """Create agenda from validated request."""
        # For mid-chain steps, you may need to prepare the input
        validated = ctx.get("validated_request")

        # Set up input for this step's validation
        ctx.set("agenda_input", {"company": validated["company"], "topics": ["intro", "discussion"]})

        agenda_input = ctx.get("agenda_input")
        print(f"Creating agenda for {agenda_input['company']}...")

        agenda = f"Agenda for {agenda_input['company']}: {', '.join(agenda_input['topics'])}"
        ctx.set("agenda", agenda)
        return {"agenda": agenda}

    @ao.chain(name="validated_meeting")
    class ValidatedMeetingChain:
        """Chain with step-level validation."""

        steps = ["validate_request", "create_agenda"]

    return ao


# =============================================================================
# Main
# =============================================================================


async def run_chain_validation(invalid: bool = False) -> dict:
    """Run chain-level validation example."""
    ao = create_chain_validated_orchestrator()

    # Prepare input data
    if invalid:
        # This will fail validation (company too short)
        data = {"request": {"company": "A", "meeting_date": "2024-03-15"}}
    else:
        data = {"request": {"company": "Acme Corp", "meeting_date": "2024-03-15", "attendees": ["Alice", "Bob"]}}

    try:
        result = await ao.launch("meeting_prep", data)
        return result
    except ContractValidationError as e:
        return {"success": False, "error": str(e), "validation_failed": True}


async def run_step_validation() -> dict:
    """Run step-level validation example."""
    ao = create_step_validated_orchestrator()

    data = {"request": {"company": "TechCorp", "meeting_date": "2024-04-20"}}

    try:
        result = await ao.launch("validated_meeting", data)
        return result
    except ContractValidationError as e:
        return {"success": False, "error": str(e), "validation_failed": True}


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Input validation example")
    parser.add_argument("--invalid", action="store_true", help="Use invalid input to trigger validation error")
    parser.add_argument("--step-validation", action="store_true", help="Use step-level validation instead of chain-level")
    args = parser.parse_args()

    if args.step_validation:
        result = asyncio.run(run_step_validation())
    else:
        result = asyncio.run(run_chain_validation(invalid=args.invalid))

    print()
    if result.get("validation_failed"):
        print(f"Result: VALIDATION ERROR")
        print(f"Error: {result['error']}")
    elif result.get("success"):
        print(f"Result: SUCCESS")
        agenda = result.get("context", {}).get("data", {}).get("agenda", "N/A")
        print(f"Agenda: {agenda}")
    else:
        print(f"Result: FAILED")
        print(f"Error: {result.get('error', 'Unknown')}")


if __name__ == "__main__":
    main()
