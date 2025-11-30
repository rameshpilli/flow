#!/usr/bin/env python3
"""
AgentOrchestrator CLI

Command-line interface for running chains, validating definitions, and scaffolding.

Usage:
    ao run <chain_name> [--company "Apple"] [--data '{"key": "value"}']
    ao run <chain_name> --resumable  # Run with checkpointing
    ao resume <run_id>               # Resume failed run
    ao runs [--chain <name>] [--status failed]  # List runs
    ao run-info <run_id>             # Show run details
    ao run-output <run_id>           # Get partial outputs
    ao check [<chain_name>]
    ao list
    ao graph <chain_name> [--format mermaid]
    ao new agent <name>
    ao new chain <name>
    ao dev [--watch]
    ao debug <chain_name>            # Debug with snapshots
    ao health                        # Basic health check
    ao health --detailed             # Full dependency health check
    ao doctor                        # Diagnose common issues
    ao version
"""

import argparse
import asyncio
import importlib
import importlib.util
import json
import os
import sys
import time
from pathlib import Path


def get_orchestrator():
    """
    Get or create the AgentOrchestrator instance, importing chain definitions.

    Uses importlib.util for proper module loading without sys.path manipulation.
    """
    from agentorchestrator import get_orchestrator as _get_orchestrator

    cwd = Path.cwd()

    # Look for common chain definition files
    definition_files = [
        "chains.py",
        "agentorchestrator_chains.py",
        "definitions.py",
        "flows.py",
    ]

    # Import definition files using importlib.util (no sys.path manipulation)
    for def_file in definition_files:
        file_path = cwd / def_file
        if file_path.exists():
            _import_module_from_path(def_file.replace(".py", ""), file_path)

    # Check for a chains/ directory with __init__.py
    chains_dir = cwd / "chains"
    if chains_dir.is_dir() and (chains_dir / "__init__.py").exists():
        _import_module_from_path("chains", chains_dir / "__init__.py")

    # Import CMPT chain by default if nothing else was imported
    try:
        from agentorchestrator.chains import CMPTChain  # noqa: F401
    except ImportError:
        pass

    return _get_orchestrator()


def _import_module_from_path(module_name: str, file_path: Path) -> None:
    """
    Import a module from a file path without sys.path manipulation.

    Uses importlib.util for proper isolation.
    """
    try:
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
    except Exception as e:
        print(f"Warning: Could not import {file_path}: {e}")


# =============================================================================
# CHAIN EXECUTION COMMANDS
# Commands: run, resume, runs, run-info, run-output
# =============================================================================


def cmd_run(args: argparse.Namespace) -> int:
    """Run a chain with optional input data."""
    forge = get_orchestrator()

    # Build input data
    data = {}

    # Parse --data JSON
    if args.data:
        try:
            data = json.loads(args.data)
        except json.JSONDecodeError as e:
            print(f"Error parsing --data JSON: {e}")
            return 1

    # Add --company if provided
    if args.company:
        data["corporate_company_name"] = args.company

    # Add any extra key=value pairs
    if args.extra:
        for item in args.extra:
            if "=" in item:
                key, value = item.split("=", 1)
                data[key] = value

    # Check if resumable mode requested
    resumable = getattr(args, 'resumable', False)
    run_id = getattr(args, 'run_id', None)

    print(f"\n{'═' * 60}")
    print(f"  Running: {args.chain_name}")
    if resumable:
        print("  Mode: Resumable (checkpoints enabled)")
        if run_id:
            print(f"  Run ID: {run_id}")
    print(f"  Input: {json.dumps(data, indent=2) if data else '{}'}")
    print(f"{'═' * 60}\n")

    start_time = time.perf_counter()

    try:
        if resumable:
            # Run with checkpointing
            result = asyncio.run(forge.launch_resumable(args.chain_name, data, run_id))
            run_id = result.get("run_id", "unknown")
        else:
            result = asyncio.run(forge.launch(args.chain_name, data))

        duration = (time.perf_counter() - start_time) * 1000

        print(f"\n{'═' * 60}")
        print(f"  Result: {'SUCCESS' if result.get('success') else 'FAILED'}")
        print(f"  Duration: {duration:.2f}ms")
        if resumable:
            print(f"  Run ID: {result.get('run_id', 'unknown')}")
            if not result.get('success'):
                print(f"  Resume with: ao resume {result.get('run_id')}")
        print(f"{'═' * 60}\n")

        if args.output:
            with open(args.output, "w") as f:
                json.dump(result, f, indent=2, default=str)
            print(f"Output saved to: {args.output}")
        elif args.verbose:
            print(json.dumps(result, indent=2, default=str))

        return 0 if result.get("success") else 1

    except Exception as e:
        print(f"\nError: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


def cmd_resume(args: argparse.Namespace) -> int:
    """Resume a failed or partial chain run."""
    forge = get_orchestrator()

    print(f"\n{'═' * 60}")
    print(f"  Resuming Run: {args.run_id}")
    print(f"{'═' * 60}\n")

    start_time = time.perf_counter()

    try:
        result = asyncio.run(forge.resume(args.run_id, skip_completed=not args.rerun_all))
        duration = (time.perf_counter() - start_time) * 1000

        print(f"\n{'═' * 60}")
        print(f"  Result: {'SUCCESS' if result.get('success') else 'FAILED'}")
        print(f"  Duration: {duration:.2f}ms")
        print(f"  Chain: {result.get('chain_name', 'unknown')}")
        print(f"{'═' * 60}\n")

        if args.output:
            with open(args.output, "w") as f:
                json.dump(result, f, indent=2, default=str)
            print(f"Output saved to: {args.output}")
        elif args.verbose:
            print(json.dumps(result, indent=2, default=str))

        return 0 if result.get("success") else 1

    except ValueError as e:
        print(f"\nError: {e}")
        return 1
    except Exception as e:
        print(f"\nError: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


def cmd_runs(args: argparse.Namespace) -> int:
    """List chain runs with optional filters."""
    forge = get_orchestrator()

    chain_name = getattr(args, 'chain_name', None)
    status = getattr(args, 'status', None)
    limit = getattr(args, 'limit', 20)

    try:
        runs = asyncio.run(forge.list_runs(
            chain_name=chain_name,
            status=status,
            limit=limit,
        ))

        if not runs:
            print("\nNo runs found matching criteria.\n")
            return 0

        print(f"\n{'═' * 80}")
        print("  Chain Runs" + (f" ({chain_name})" if chain_name else ""))
        print(f"{'═' * 80}\n")

        # Header
        print(f"  {'Run ID':<20} {'Chain':<20} {'Status':<10} {'Steps':<12} {'Created':<20}")
        print(f"  {'-' * 20} {'-' * 20} {'-' * 10} {'-' * 12} {'-' * 20}")

        for run in runs:
            run_id = run.run_id[:18] if len(run.run_id) > 18 else run.run_id
            chain = run.chain_name[:18] if len(run.chain_name) > 18 else run.chain_name
            steps = f"{run.completed_steps}/{run.total_steps}"
            created = run.created_at[:19] if run.created_at else "unknown"

            # Status coloring
            status_colors = {
                "completed": "\033[92m",  # Green
                "partial": "\033[93m",     # Yellow
                "failed": "\033[91m",      # Red
                "running": "\033[94m",     # Blue
            }
            reset = "\033[0m"
            color = status_colors.get(run.status, "")

            print(f"  {run_id:<20} {chain:<20} {color}{run.status:<10}{reset} {steps:<12} {created:<20}")

        print(f"\n{'═' * 80}")
        print(f"  Total: {len(runs)} runs")
        if args.resumable_only:
            print("  (showing resumable runs only)")
        print(f"{'═' * 80}\n")

        return 0

    except Exception as e:
        print(f"\nError listing runs: {e}")
        if getattr(args, 'verbose', False):
            import traceback
            traceback.print_exc()
        return 1


def cmd_run_info(args: argparse.Namespace) -> int:
    """Show detailed information about a specific run."""
    forge = get_orchestrator()

    try:
        run = asyncio.run(forge.get_run(args.run_id))

        if run is None:
            print(f"\nRun not found: {args.run_id}\n")
            return 1

        print(f"\n{'═' * 60}")
        print(f"  Run Details: {run.run_id}")
        print(f"{'═' * 60}\n")

        print(f"  Chain: {run.chain_name}")
        print(f"  Status: {run.status}")
        print(f"  Created: {run.created_at}")
        print(f"  Updated: {run.updated_at}")
        if run.completed_at:
            print(f"  Completed: {run.completed_at}")
        print(f"  Duration: {run.total_duration_ms:.2f}ms")
        print(f"  Steps: {run.completed_steps}/{run.total_steps}")
        if run.resumable:
            print("  Resumable: Yes")
            print(f"  Last Completed: {run.last_completed_step or 'None'}")

        if run.steps:
            print("\n  Steps:")
            for step in run.steps:
                status_icon = {
                    "completed": "✓",
                    "failed": "✗",
                    "skipped": "○",
                    "pending": "·",
                    "running": "▸",
                }.get(step.status, "?")
                print(f"    {status_icon} {step.step_name}: {step.status} ({step.duration_ms:.2f}ms)")
                if step.error:
                    print(f"      Error: {step.error}")

        print(f"\n{'═' * 60}\n")

        if args.json:
            print(json.dumps(run.to_dict(), indent=2, default=str))

        return 0

    except Exception as e:
        print(f"\nError getting run info: {e}")
        return 1


def cmd_run_output(args: argparse.Namespace) -> int:
    """Get partial outputs from a run."""
    forge = get_orchestrator()

    try:
        result = asyncio.run(forge.get_partial_output(args.run_id))

        if not result:
            print(f"\nNo outputs found for run: {args.run_id}\n")
            return 1

        print(f"\n{'═' * 60}")
        print(f"  Partial Outputs: {result.get('run_id', args.run_id)}")
        print(f"  Chain: {result.get('chain_name', 'unknown')}")
        print(f"  Status: {result.get('status', 'unknown')}")
        print(f"  Completed: {result.get('completed_steps', 0)}/{result.get('total_steps', 0)} steps")
        print(f"{'═' * 60}\n")

        outputs = result.get("outputs", {})
        for step_name, output in outputs.items():
            print(f"  {step_name}:")
            if isinstance(output, dict):
                for key, value in list(output.items())[:5]:  # Show first 5 keys
                    value_str = str(value)[:80] + "..." if len(str(value)) > 80 else str(value)
                    print(f"    {key}: {value_str}")
            else:
                print(f"    {str(output)[:100]}...")
            print()

        if args.json:
            print(json.dumps(result, indent=2, default=str))

        return 0

    except ValueError as e:
        print(f"\nError: {e}")
        return 1
    except Exception as e:
        print(f"\nError getting outputs: {e}")
        return 1


# =============================================================================
# INSPECTION & VALIDATION COMMANDS
# Commands: check, list, graph, validate
# =============================================================================


def cmd_check(args: argparse.Namespace) -> int:
    """Validate chain definitions."""
    forge = get_orchestrator()

    result = forge.check(args.chain_name)

    return 0 if result.get("valid") else 1


def cmd_list(args: argparse.Namespace) -> int:
    """List all definitions."""
    forge = get_orchestrator()

    forge.list_defs()

    return 0


def cmd_graph(args: argparse.Namespace) -> int:
    """Show DAG visualization."""
    forge = get_orchestrator()

    try:
        forge.graph(args.chain_name, format=args.format)
        return 0
    except Exception as e:
        print(f"Error: {e}")
        return 1


# =============================================================================
# SCAFFOLDING & CODE GENERATION COMMANDS
# Commands: new agent, new chain, new project
# =============================================================================


def cmd_new_agent(args: argparse.Namespace) -> int:
    """Generate a new agent template."""
    name = args.name
    output_dir = Path(args.output_dir or ".")

    # Create agent file
    agent_file = output_dir / f"{name.lower()}_agent.py"

    template = f'''"""
{name} Agent

Custom data agent for fetching {name.lower()} data.
"""

from agentorchestrator.agents.base import BaseAgent, AgentResult


class {name}Agent(BaseAgent):
    """
    Agent for fetching {name.lower()} data.

    Usage:
        agent = {name}Agent()
        result = await agent.fetch(query="search term")
    """

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        # Add your initialization here

    async def fetch(self, query: str, **kwargs) -> AgentResult:
        """
        Fetch data based on query.

        Args:
            query: Search query or identifier
            **kwargs: Additional parameters

        Returns:
            AgentResult with fetched data
        """
        # TODO: Implement your data fetching logic here
        data = {{
            "query": query,
            "results": [],
        }}

        return AgentResult(
            data=data,
            metadata={{
                "source": "{name.lower()}",
                "query": query,
            }}
        )

    async def health_check(self) -> bool:
        """Check if agent is healthy."""
        # TODO: Implement health check
        return True


# Register with AgentOrchestrator
def register(forge):
    """Register this agent with AgentOrchestrator instance."""
    forge.register_agent("{name.lower()}", {name}Agent)
'''

    if agent_file.exists() and not args.force:
        print(f"Error: {agent_file} already exists. Use --force to overwrite.")
        return 1

    agent_file.write_text(template)
    print(f"Created: {agent_file}")
    print("\nTo use this agent:")
    print(f"  from {name.lower()}_agent import {name}Agent")
    print(f"  agent = {name}Agent()")
    print("  result = await agent.fetch('query')")

    return 0


def cmd_new_chain(args: argparse.Namespace) -> int:
    """Generate a new chain template."""
    name = args.name
    output_dir = Path(args.output_dir or ".")

    # Create chain file
    chain_file = output_dir / f"{name.lower()}_chain.py"

    template = f'''"""
{name} Chain

Custom chain for {name.lower()} workflow.
"""

from agentorchestrator import AgentOrchestrator, ChainContext


# Create AgentOrchestrator instance (isolated for this chain)
forge = AgentOrchestrator(name="{name.lower()}", isolated=True)


# Define steps
@forge.step
async def step_1(ctx: ChainContext) -> dict:
    """First step: Initialize and prepare data."""
    initial_data = ctx.initial_data or {{}}

    # TODO: Implement your logic
    result = {{
        "status": "initialized",
        "input": initial_data,
    }}

    ctx.set("step_1_result", result)
    return result


@forge.step(deps=[step_1])
async def step_2(ctx: ChainContext) -> dict:
    """Second step: Process data from step 1."""
    step_1_result = ctx.get("step_1_result")

    # TODO: Implement your logic
    result = {{
        "status": "processed",
        "previous": step_1_result,
    }}

    ctx.set("step_2_result", result)
    return result


@forge.step(deps=[step_2])
async def step_3(ctx: ChainContext) -> dict:
    """Final step: Generate output."""
    step_2_result = ctx.get("step_2_result")

    # TODO: Implement your logic
    result = {{
        "status": "completed",
        "output": step_2_result,
    }}

    return result


# Define chain
@forge.chain
class {name}Chain:
    """Main chain for {name.lower()} workflow."""
    steps = [step_1, step_2, step_3]


# Convenience functions
async def run(data: dict | None = None) -> dict:
    """Run the {name} chain."""
    return await forge.launch("{name}Chain", data)


def check() -> dict:
    """Validate chain definitions."""
    return forge.check("{name}Chain")


def graph(format: str = "ascii") -> str:
    """Show chain DAG visualization."""
    return forge.graph("{name}Chain", format=format)


# CLI entry point
if __name__ == "__main__":
    import asyncio
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "check":
        check()
    elif len(sys.argv) > 1 and sys.argv[1] == "graph":
        graph()
    else:
        result = asyncio.run(run())
        print(result)
'''

    if chain_file.exists() and not args.force:
        print(f"Error: {chain_file} already exists. Use --force to overwrite.")
        return 1

    chain_file.write_text(template)
    print(f"Created: {chain_file}")
    print("\nTo use this chain:")
    print(f"  from {name.lower()}_chain import run, check, graph")
    print("  result = await run({'key': 'value'})")
    print("\nOr via CLI:")
    print(f"  ao run {name}Chain")

    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    """Validate chain definition (dry-run mode)."""
    from agentorchestrator.core.versioning import validate_chain

    chain_name = args.chain_name
    dry_run = not getattr(args, "execute", False)

    # Parse sample data if provided
    sample_data = None
    if args.data:
        try:
            sample_data = json.loads(args.data)
        except json.JSONDecodeError as e:
            print(f"Error parsing --data JSON: {e}")
            return 1

    print(f"\n{'=' * 60}")
    print(f"  Validating: {chain_name}")
    print(f"  Mode: {'Dry Run' if dry_run else 'Full Validation'}")
    print(f"{'=' * 60}\n")

    try:
        result = asyncio.run(validate_chain(
            chain_name,
            dry_run=dry_run,
            check_agents=args.check_agents,
            check_resources=args.check_resources,
            sample_data=sample_data,
        ))

        # Print results
        status_color = "\033[92m" if result.valid else "\033[91m"
        reset = "\033[0m"

        print(f"  Status: {status_color}{'VALID' if result.valid else 'INVALID'}{reset}")
        print(f"  Steps validated: {result.steps_validated}")
        print(f"  Agents checked: {len(result.agents_checked)}")
        print(f"  Resources checked: {len(result.resources_checked)}")

        if result.errors:
            print("\n  \033[91mErrors:\033[0m")
            for error in result.errors:
                print(f"    - {error}")

        if result.warnings:
            print("\n  \033[93mWarnings:\033[0m")
            for warning in result.warnings:
                print(f"    - {warning}")

        print(f"\n{'=' * 60}\n")

        if args.json:
            print(json.dumps(result.to_dict(), indent=2))

        return 0 if result.valid else 1

    except Exception as e:
        print(f"Error during validation: {e}")
        return 1


def cmd_new_project(args: argparse.Namespace) -> int:
    """Generate a complete AgentOrchestrator project."""
    from agentorchestrator.templates.scaffolding import generate_project, to_snake_case

    name = args.name
    output_dir = Path(args.output_dir or ".")
    description = args.description or ""
    snake_name = to_snake_case(name)

    print(f"\n{'=' * 60}")
    print(f"  Creating AgentOrchestrator Project: {name}")
    print(f"{'=' * 60}\n")

    try:
        created_files = generate_project(
            name=name,
            output_dir=output_dir,
            description=description,
            with_api=not args.no_api,
            with_docker=not args.no_docker,
            with_ci=not args.no_ci,
            template=args.template,
        )

        print(f"  Created {len(created_files)} files:\n")
        for f in created_files[:15]:
            print(f"    {f}")
        if len(created_files) > 15:
            print(f"    ... and {len(created_files) - 15} more")

        print(f"\n{'=' * 60}")
        print(f"  Project created at: {output_dir / snake_name}")
        print(f"{'=' * 60}\n")

        print("  Next steps:\n")
        print(f"    cd {snake_name}")
        print("    pip install -e '.[dev]'")
        print("    ao check")
        print("    ao run hello_chain --data '{\"message\": \"Hello\"}'\n")

        if not args.no_api:
            print("  To start the API server:\n")
            print("    pip install -e '.[api]'")
            print(f"    uvicorn src.{snake_name}.api:app --reload\n")

        if not args.no_docker:
            print("  To run with Docker:\n")
            print("    docker-compose up\n")

        return 0

    except Exception as e:
        print(f"Error creating project: {e}")
        import traceback
        traceback.print_exc()
        return 1


# =============================================================================
# HEALTH, DIAGNOSTICS & CONFIGURATION COMMANDS
# Commands: health, doctor, version, config
# =============================================================================


def cmd_health(args: argparse.Namespace) -> int:
    """Check health status of AgentOrchestrator."""
    detailed = getattr(args, 'detailed', False)

    # Use the comprehensive health aggregator for detailed checks
    if detailed:
        from agentorchestrator.utils.health import HealthStatus, run_health_checks

        try:
            result = asyncio.run(run_health_checks(
                include_external=True,
                timeout_seconds=getattr(args, 'timeout', 10.0),
            ))

            # Colorize status
            status_colors = {
                HealthStatus.HEALTHY: "\033[92m",    # Green
                HealthStatus.DEGRADED: "\033[93m",   # Yellow
                HealthStatus.UNHEALTHY: "\033[91m",  # Red
                HealthStatus.UNKNOWN: "\033[90m",    # Gray
            }
            reset = "\033[0m"
            color = status_colors.get(result.status, "")

            print(f"\n{'═' * 60}")
            print("  AgentOrchestrator Health Check (Detailed)")
            print(f"{'═' * 60}\n")

            print(f"  Status: {color}{result.status.value.upper()}{reset}")
            print(f"  Version: {result.version}")
            print(f"  Environment: {result.environment}")
            print(f"  Total Latency: {result.total_latency_ms:.2f}ms")

            print("\n  Summary:")
            print(f"    Healthy:   {result.healthy_count}")
            print(f"    Degraded:  {result.degraded_count}")
            print(f"    Unhealthy: {result.unhealthy_count}")

            print("\n  Components:")
            for comp in result.components:
                comp_color = status_colors.get(comp.status, "")
                icon = {
                    HealthStatus.HEALTHY: "✓",
                    HealthStatus.DEGRADED: "!",
                    HealthStatus.UNHEALTHY: "✗",
                    HealthStatus.UNKNOWN: "?",
                }.get(comp.status, "?")
                print(f"    {comp_color}{icon}{reset} {comp.name}: {comp.status.value} ({comp.latency_ms:.1f}ms)")
                if comp.message:
                    print(f"      {comp.message}")
                if args.verbose and comp.details:
                    for key, value in comp.details.items():
                        print(f"      {key}: {value}")

            print(f"\n{'═' * 60}\n")

            if args.json:
                print(json.dumps(result.to_dict(), indent=2, default=str))

            return 0 if result.status == HealthStatus.HEALTHY else 1

        except Exception as e:
            print(f"Error running detailed health check: {e}")
            if getattr(args, 'verbose', False):
                import traceback
                traceback.print_exc()
            return 1

    # Basic health check (quick, no external dependencies)
    from agentorchestrator.utils.config import get_health

    try:
        health = get_health()

        # Colorize status
        status_colors = {
            "healthy": "\033[92m",  # Green
            "degraded": "\033[93m",  # Yellow
            "unhealthy": "\033[91m",  # Red
        }
        reset = "\033[0m"
        color = status_colors.get(health.status, "")

        print(f"\n{'═' * 50}")
        print("  AgentOrchestrator Health Check")
        print(f"{'═' * 50}\n")

        print(f"  Status: {color}{health.status.upper()}{reset}")
        print(f"  Version: {health.version}")
        print(f"  Environment: {health.environment}")

        if health.checks:
            print("\n  Checks:")
            for check, passed in health.checks.items():
                icon = "✓" if passed else "✗"
                check_color = "\033[92m" if passed else "\033[91m"
                print(f"    {check_color}{icon}{reset} {check}")

        print(f"\n{'═' * 50}")
        print("  Tip: Use --detailed for full dependency checks")
        print(f"{'═' * 50}\n")

        if args.json:
            print(json.dumps(health.to_dict(), indent=2))

        return 0 if health.status == "healthy" else 1

    except Exception as e:
        print(f"Error checking health: {e}")
        return 1


def cmd_version(args: argparse.Namespace) -> int:
    """Show version information."""
    from agentorchestrator.utils.config import get_version

    try:
        version_info = get_version()

        if args.json:
            print(json.dumps(version_info, indent=2))
        else:
            print(f"\n{'═' * 40}")
            print(f"  {version_info['name']} v{version_info['version']}")
            print(f"  Environment: {version_info['environment']}")
            print(f"{'═' * 40}\n")

        return 0

    except Exception as e:
        print(f"Error getting version: {e}")
        return 1


def cmd_doctor(args: argparse.Namespace) -> int:
    """
    Diagnose common issues with AgentOrchestrator setup.

    Checks:
    - Python version compatibility
    - Required dependencies installed
    - Optional dependencies status
    - Environment variables configured
    - Chain definitions valid
    - Circular import detection
    """
    import platform

    print(f"\n{'═' * 50}")
    print("  AgentOrchestrator Doctor")
    print(f"{'═' * 50}\n")

    issues = []
    warnings = []
    checks_passed = 0
    checks_total = 0

    # 1. Python version check
    checks_total += 1
    py_version = platform.python_version()
    py_major, py_minor = map(int, py_version.split('.')[:2])
    if py_major >= 3 and py_minor >= 10:
        print(f"  ✅ Python version: {py_version}")
        checks_passed += 1
    elif py_major >= 3 and py_minor >= 9:
        print(f"  ⚠️  Python version: {py_version} (3.10+ recommended)")
        warnings.append(f"Python {py_version} works but 3.10+ is recommended")
        checks_passed += 1
    else:
        print(f"  ❌ Python version: {py_version} (requires 3.9+)")
        issues.append(f"Python 3.9+ required, found {py_version}")

    # 2. Required dependencies
    required_deps = [
        ("pydantic", "Data validation"),
        ("httpx", "HTTP client"),
    ]

    for dep_name, dep_desc in required_deps:
        checks_total += 1
        try:
            module = importlib.import_module(dep_name)
            version = getattr(module, "__version__", "unknown")
            print(f"  ✅ {dep_name}: {version} ({dep_desc})")
            checks_passed += 1
        except ImportError:
            print(f"  ❌ {dep_name}: NOT INSTALLED ({dep_desc})")
            issues.append(f"Required dependency '{dep_name}' not installed")

    # 3. Optional dependencies
    optional_deps = [
        ("aiohttp", "Async HTTP client"),
        ("tiktoken", "Token counting"),
        ("langchain", "LLM chains"),
        ("opentelemetry", "Distributed tracing"),
        ("structlog", "Structured logging"),
        ("redis", "Redis context store"),
    ]

    for dep_name, dep_desc in optional_deps:
        checks_total += 1
        try:
            module = importlib.import_module(dep_name)
            version = getattr(module, "__version__", "installed")
            print(f"  ✅ {dep_name}: {version} ({dep_desc})")
            checks_passed += 1
        except ImportError:
            print(f"  ⚪ {dep_name}: not installed ({dep_desc}) - optional")
            checks_passed += 1  # Optional, so still passes

    # 4. Environment variables
    print("\n  Environment Variables:")
    env_vars = [
        ("LLM_API_KEY", True, "LLM API authentication"),
        ("LLM_BASE_URL", False, "LLM endpoint URL"),
        ("FLOWFORGE_ENV", False, "Environment name"),
        ("FLOWFORGE_DEBUG", False, "Debug mode"),
    ]

    for var_name, required, desc in env_vars:
        checks_total += 1
        value = os.getenv(var_name)
        if value:
            masked = "***" + value[-4:] if "KEY" in var_name or "TOKEN" in var_name else value
            print(f"  ✅ {var_name}: {masked}")
            checks_passed += 1
        elif required:
            print(f"  ⚠️  {var_name}: not set ({desc})")
            warnings.append(f"{var_name} not set - required for {desc}")
            checks_passed += 1  # Warning, not failure
        else:
            print(f"  ⚪ {var_name}: not set ({desc}) - optional")
            checks_passed += 1

    # 5. AgentOrchestrator imports
    print("\n  AgentOrchestrator Imports:")
    checks_total += 1
    try:
        from agentorchestrator import AgentOrchestrator, get_orchestrator  # noqa: F401
        print("  ✅ AgentOrchestrator core imports successful")
        checks_passed += 1
    except ImportError as e:
        print(f"  ❌ AgentOrchestrator import failed: {e}")
        issues.append(f"AgentOrchestrator import error: {e}")

    # 6. Check for circular imports (basic check)
    checks_total += 1
    try:
        from agentorchestrator.agents import base as agent_base  # noqa: F401
        from agentorchestrator.core import context, dag, orchestrator, registry  # noqa: F401
        from agentorchestrator.middleware import base as mw_base  # noqa: F401
        print("  ✅ No circular import issues detected")
        checks_passed += 1
    except ImportError as e:
        print(f"  ❌ Circular import detected: {e}")
        issues.append(f"Circular import: {e}")

    # 7. Validate registered chains
    print("\n  Registered Chains:")
    checks_total += 1
    try:
        forge = get_orchestrator()
        chains = forge.list_chains()
        if chains:
            valid_count = 0
            for chain_name in chains:
                try:
                    result = forge.check(chain_name)
                    if result.get("valid"):
                        print(f"  ✅ {chain_name}: valid")
                        valid_count += 1
                    else:
                        errors = result.get("errors", [])
                        print(f"  ❌ {chain_name}: invalid - {errors[0] if errors else 'unknown error'}")
                        issues.append(f"Chain '{chain_name}' is invalid")
                except Exception as e:
                    print(f"  ❌ {chain_name}: validation error - {e}")
                    issues.append(f"Chain '{chain_name}' validation failed: {e}")
            if valid_count == len(chains):
                checks_passed += 1
        else:
            print("  ⚪ No chains registered")
            checks_passed += 1
    except Exception as e:
        print(f"  ❌ Could not check chains: {e}")
        issues.append(f"Chain check failed: {e}")

    # Summary
    print(f"\n{'═' * 50}")
    print(f"  Summary: {checks_passed}/{checks_total} checks passed")

    if issues:
        print(f"\n  ❌ Issues ({len(issues)}):")
        for issue in issues:
            print(f"     - {issue}")

    if warnings:
        print(f"\n  ⚠️  Warnings ({len(warnings)}):")
        for warning in warnings:
            print(f"     - {warning}")

    if not issues and not warnings:
        print("\n  🎉 All checks passed! AgentOrchestrator is ready to use.")
    elif not issues:
        print("\n  ✅ AgentOrchestrator is functional with minor warnings.")
    else:
        print("\n  ❌ Please fix the issues above before using AgentOrchestrator.")

    print(f"{'═' * 50}\n")

    # Return code: 0 if no issues, 1 if issues
    return 1 if issues else 0


def cmd_config(args: argparse.Namespace) -> int:
    """Show current configuration (secrets masked)."""
    from agentorchestrator.utils.config import ConfigError, get_config

    try:
        config = get_config()
        safe_config = config.to_safe_dict()

        print(f"\n{'═' * 50}")
        print("  AgentOrchestrator Configuration")
        print(f"{'═' * 50}\n")

        for key, value in safe_config.items():
            print(f"  {key}: {value}")

        print(f"\n{'═' * 50}\n")

        if args.json:
            print(json.dumps(safe_config, indent=2))

        return 0

    except ConfigError as e:
        print(f"Configuration Error: {e}")
        return 1
    except Exception as e:
        print(f"Error loading config: {e}")
        return 1


# =============================================================================
# DEVELOPMENT & DEBUGGING COMMANDS
# Commands: dev, debug
# =============================================================================


def cmd_dev(args: argparse.Namespace) -> int:
    """Run in development mode with hot reloading."""
    print("Starting AgentOrchestrator development server...")

    # Try to import watchdog for file watching
    try:
        from watchdog.events import FileSystemEventHandler
        from watchdog.observers import Observer
        WATCHDOG_AVAILABLE = True
    except ImportError:
        WATCHDOG_AVAILABLE = False
        if args.watch:
            print("Warning: watchdog not installed. Install with: pip install watchdog")
            print("Running without hot reload...")

    forge = get_orchestrator()

    # Initial check
    print("\n--- Initial Validation ---")
    forge.check()
    forge.list_defs()

    if not args.watch or not WATCHDOG_AVAILABLE:
        return 0

    # File watcher for hot reloading
    class ReloadHandler(FileSystemEventHandler):
        def __init__(self):
            self.last_reload = 0

        def on_modified(self, event):
            if not event.src_path.endswith(".py"):
                return

            # Debounce
            current_time = time.time()
            if current_time - self.last_reload < 1:
                return
            self.last_reload = current_time

            print(f"\n--- File changed: {event.src_path} ---")
            print("Reloading definitions...")

            # Clear registries and reimport
            forge.clear()

            # Reimport modules
            cwd = Path.cwd()
            for module_name in list(sys.modules.keys()):
                module = sys.modules.get(module_name)
                if module and hasattr(module, "__file__") and module.__file__:
                    if str(cwd) in module.__file__:
                        try:
                            importlib.reload(module)
                        except Exception as e:
                            print(f"Error reloading {module_name}: {e}")

            # Re-validate
            print("\n--- Validation ---")
            forge.check()

    observer = Observer()
    observer.schedule(ReloadHandler(), str(Path.cwd()), recursive=True)
    observer.start()

    print(f"\nWatching for changes in {Path.cwd()}")
    print("Press Ctrl+C to stop...\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        print("\nStopping development server...")

    observer.join()
    return 0


def cmd_debug(args: argparse.Namespace) -> int:
    """
    Run a chain in debug mode with context snapshots after each step.

    Creates snapshot files in the debug directory showing:
    - Context state after each step
    - Step results with timing
    - Error details and tracebacks
    """
    import datetime

    from agentorchestrator.utils.config import get_config

    forge = get_orchestrator()
    config = get_config()

    # Determine snapshot directory
    snapshot_dir = Path(args.snapshot_dir or config.debug_snapshot_dir)
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    # Build input data (same as run command)
    data = {}
    if args.data:
        try:
            data = json.loads(args.data)
        except json.JSONDecodeError as e:
            print(f"Error parsing --data JSON: {e}")
            return 1

    if args.company:
        data["corporate_company_name"] = args.company

    # Generate run ID for this debug session
    run_id = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = snapshot_dir / f"{args.chain_name}_{run_id}"
    run_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'═' * 60}")
    print(f"  DEBUG MODE: {args.chain_name}")
    print(f"  Snapshots: {run_dir}")
    print(f"{'═' * 60}\n")

    # Create debug context with snapshot callback
    from agentorchestrator.core.context import ChainContext

    step_count = [0]  # Use list to allow modification in nested function

    def snapshot_callback(ctx: ChainContext, step_name: str, result: dict):
        """Callback to snapshot context after each step."""
        step_count[0] += 1
        snapshot_file = run_dir / f"{step_count[0]:02d}_{step_name}.json"

        # Build snapshot data
        snapshot = {
            "step_number": step_count[0],
            "step_name": step_name,
            "timestamp": datetime.datetime.now().isoformat(),
            "result": {
                "success": result.get("success", False),
                "output": result.get("output"),
                "duration_ms": result.get("duration_ms", 0),
                "error": str(result.get("error")) if result.get("error") else None,
                "error_type": result.get("error_type"),
            },
            "context": {
                "request_id": ctx.request_id,
                "total_tokens": ctx.total_tokens,
                "data": ctx.to_dict().get("data", {}),
            },
            "results_so_far": [
                {
                    "step": r.step_name,
                    "success": r.success,
                    "duration_ms": r.duration_ms,
                }
                for r in ctx.results
            ],
        }

        with open(snapshot_file, "w") as f:
            json.dump(snapshot, f, indent=2, default=str)

        status = "✓" if result.get("success", True) else "✗"
        duration = result.get("duration_ms", 0)
        print(f"  [{status}] {step_name} ({duration:.2f}ms) → {snapshot_file.name}")

    start_time = time.perf_counter()

    try:
        # Run with debug callback - now fully wired through forge.launch -> runner -> executor
        result = asyncio.run(
            forge.launch(
                args.chain_name,
                data,
                debug_callback=snapshot_callback,
            )
        )
        duration = (time.perf_counter() - start_time) * 1000

        # Save final summary
        summary_file = run_dir / "00_summary.json"
        summary = {
            "chain_name": args.chain_name,
            "run_id": run_id,
            "success": result.get("success", False),
            "total_duration_ms": duration,
            "total_steps": len(result.get("results", [])),
            "input_data": data,
            "final_result": result,
        }

        with open(summary_file, "w") as f:
            json.dump(summary, f, indent=2, default=str)

        print(f"\n{'═' * 60}")
        print(f"  Result: {'SUCCESS' if result.get('success') else 'FAILED'}")
        print(f"  Duration: {duration:.2f}ms")
        print(f"  Snapshots: {run_dir}")
        print(f"{'═' * 60}\n")

        # Show results summary
        for r in result.get("results", []):
            status = "✓" if r.get("success", not r.get("error")) else "✗"
            name = r.get("step_name", "unknown")
            dur = r.get("duration_ms", 0)
            print(f"  {status} {name}: {dur:.2f}ms")

        return 0 if result.get("success") else 1

    except Exception as e:
        duration = (time.perf_counter() - start_time) * 1000
        print(f"\n  Error: {e}")

        # Save error snapshot
        error_file = run_dir / "99_error.json"
        import traceback
        error_snapshot = {
            "chain_name": args.chain_name,
            "run_id": run_id,
            "error": str(e),
            "error_type": type(e).__name__,
            "traceback": traceback.format_exc(),
            "duration_ms": duration,
            "input_data": data,
        }

        with open(error_file, "w") as f:
            json.dump(error_snapshot, f, indent=2, default=str)

        if args.verbose:
            traceback.print_exc()

        print(f"\n  Error snapshot saved: {error_file}")
        return 1


# =============================================================================
# CLI ARGUMENT PARSER & ENTRY POINT
# =============================================================================


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="agentorchestrator",
        description="AgentOrchestrator CLI - DAG-based Chain Orchestration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  ao run cmpt_chain --company "Apple Inc"
  ao run cmpt_chain --resumable --company "Apple Inc"  # With checkpointing
  ao resume run_abc123                                  # Resume failed run
  ao runs --status failed                               # List failed runs
  ao run-info run_abc123                                # Show run details
  ao run-output run_abc123                              # Get partial outputs
  ao check
  ao list
  ao graph cmpt_chain --format mermaid
  ao new agent MyCustomAgent
  ao new chain DataPipeline
  ao dev --watch
  ao debug cmpt_chain --company "Apple Inc"
        """,
    )

    parser.add_argument(
        "--version", action="version", version="%(prog)s 0.1.0"
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # run command
    run_parser = subparsers.add_parser("run", help="Run a chain")
    run_parser.add_argument("chain_name", help="Name of the chain to run")
    run_parser.add_argument(
        "--company", "-c", help="Company name (shortcut for corporate_company_name)"
    )
    run_parser.add_argument(
        "--data", "-d", help="JSON input data"
    )
    run_parser.add_argument(
        "--output", "-o", help="Output file for results (JSON)"
    )
    run_parser.add_argument(
        "--verbose", "-v", action="store_true", help="Verbose output"
    )
    run_parser.add_argument(
        "--resumable", "-r", action="store_true",
        help="Enable checkpointing for resume capability"
    )
    run_parser.add_argument(
        "--run-id", help="Custom run ID (for resumable runs)"
    )
    run_parser.add_argument(
        "extra", nargs="*", help="Additional key=value pairs"
    )
    run_parser.set_defaults(func=cmd_run)

    # resume command
    resume_parser = subparsers.add_parser("resume", help="Resume a failed or partial run")
    resume_parser.add_argument("run_id", help="ID of the run to resume")
    resume_parser.add_argument(
        "--rerun-all", action="store_true",
        help="Rerun all steps (don't skip completed)"
    )
    resume_parser.add_argument(
        "--output", "-o", help="Output file for results (JSON)"
    )
    resume_parser.add_argument(
        "--verbose", "-v", action="store_true", help="Verbose output"
    )
    resume_parser.set_defaults(func=cmd_resume)

    # runs command (list runs)
    runs_parser = subparsers.add_parser("runs", help="List chain runs")
    runs_parser.add_argument(
        "--chain", "-c", dest="chain_name",
        help="Filter by chain name"
    )
    runs_parser.add_argument(
        "--status", "-s",
        choices=["completed", "failed", "partial", "running"],
        help="Filter by status"
    )
    runs_parser.add_argument(
        "--limit", "-n", type=int, default=20,
        help="Maximum runs to show (default: 20)"
    )
    runs_parser.add_argument(
        "--resumable-only", action="store_true",
        help="Show only resumable runs"
    )
    runs_parser.add_argument(
        "--verbose", "-v", action="store_true", help="Verbose output"
    )
    runs_parser.set_defaults(func=cmd_runs)

    # run-info command
    run_info_parser = subparsers.add_parser("run-info", help="Show details of a specific run")
    run_info_parser.add_argument("run_id", help="ID of the run")
    run_info_parser.add_argument(
        "--json", "-j", action="store_true", help="Output as JSON"
    )
    run_info_parser.set_defaults(func=cmd_run_info)

    # run-output command
    run_output_parser = subparsers.add_parser(
        "run-output", help="Get partial outputs from a run"
    )
    run_output_parser.add_argument("run_id", help="ID of the run")
    run_output_parser.add_argument(
        "--json", "-j", action="store_true", help="Output as JSON"
    )
    run_output_parser.set_defaults(func=cmd_run_output)

    # check command
    check_parser = subparsers.add_parser("check", help="Validate definitions")
    check_parser.add_argument(
        "chain_name", nargs="?", help="Specific chain to check (optional)"
    )
    check_parser.set_defaults(func=cmd_check)

    # list command
    list_parser = subparsers.add_parser("list", help="List all definitions")
    list_parser.set_defaults(func=cmd_list)

    # graph command
    graph_parser = subparsers.add_parser("graph", help="Show DAG visualization")
    graph_parser.add_argument("chain_name", help="Name of the chain")
    graph_parser.add_argument(
        "--format", "-f", choices=["ascii", "mermaid"], default="ascii",
        help="Output format (default: ascii)"
    )
    graph_parser.set_defaults(func=cmd_graph)

    # new command (subcommand)
    new_parser = subparsers.add_parser("new", help="Generate new components")
    new_subparsers = new_parser.add_subparsers(dest="new_type", help="Component type")

    # new agent
    new_agent_parser = new_subparsers.add_parser("agent", help="Create new agent")
    new_agent_parser.add_argument("name", help="Agent name (e.g., MyCustomAgent)")
    new_agent_parser.add_argument(
        "--output-dir", "-o", help="Output directory (default: current)"
    )
    new_agent_parser.add_argument(
        "--force", "-f", action="store_true", help="Overwrite existing files"
    )
    new_agent_parser.set_defaults(func=cmd_new_agent)

    # new chain
    new_chain_parser = new_subparsers.add_parser("chain", help="Create new chain")
    new_chain_parser.add_argument("name", help="Chain name (e.g., DataPipeline)")
    new_chain_parser.add_argument(
        "--output-dir", "-o", help="Output directory (default: current)"
    )
    new_chain_parser.add_argument(
        "--force", "-f", action="store_true", help="Overwrite existing files"
    )
    new_chain_parser.set_defaults(func=cmd_new_chain)

    # new project
    new_project_parser = new_subparsers.add_parser(
        "project",
        help="Create a complete AgentOrchestrator project"
    )
    new_project_parser.add_argument("name", help="Project name (e.g., my_app)")
    new_project_parser.add_argument(
        "--output-dir", "-o",
        help="Output directory (default: current)"
    )
    new_project_parser.add_argument(
        "--description", "-d",
        help="Project description"
    )
    new_project_parser.add_argument(
        "--no-api", action="store_true",
        help="Skip FastAPI server"
    )
    new_project_parser.add_argument(
        "--no-docker", action="store_true",
        help="Skip Docker files"
    )
    new_project_parser.add_argument(
        "--no-ci", action="store_true",
        help="Skip CI/CD configuration"
    )
    new_project_parser.add_argument(
        "--template", "-t",
        choices=["default", "cmpt"],
        default="default",
        help="Project template (default: default)"
    )
    new_project_parser.set_defaults(func=cmd_new_project)

    # dev command
    dev_parser = subparsers.add_parser("dev", help="Development mode with hot reload")
    dev_parser.add_argument(
        "--watch", "-w", action="store_true", help="Watch for file changes"
    )
    dev_parser.set_defaults(func=cmd_dev)

    # validate command (dry-run mode)
    validate_parser = subparsers.add_parser(
        "validate",
        help="Validate chain (dry-run mode)"
    )
    validate_parser.add_argument("chain_name", help="Chain to validate")
    validate_parser.add_argument(
        "--execute", "-e", action="store_true",
        help="Actually execute validation (not just dry-run)"
    )
    validate_parser.add_argument(
        "--check-agents", action="store_true", default=True,
        help="Check agent availability"
    )
    validate_parser.add_argument(
        "--check-resources", action="store_true", default=True,
        help="Check resource registration"
    )
    validate_parser.add_argument(
        "--data", "-d",
        help="Sample JSON input data for contract validation"
    )
    validate_parser.add_argument(
        "--json", "-j", action="store_true", help="Output as JSON"
    )
    validate_parser.set_defaults(func=cmd_validate)

    # health command
    health_parser = subparsers.add_parser("health", help="Check health status")
    health_parser.add_argument(
        "--detailed", "-d", action="store_true",
        help="Run detailed checks including external dependencies (Redis, LLM)"
    )
    health_parser.add_argument(
        "--timeout", "-t", type=float, default=10.0,
        help="Timeout for each health check in seconds (default: 10)"
    )
    health_parser.add_argument(
        "--json", "-j", action="store_true", help="Output as JSON"
    )
    health_parser.add_argument(
        "--verbose", "-v", action="store_true", help="Show detailed component info"
    )
    health_parser.set_defaults(func=cmd_health)

    # version command
    version_parser = subparsers.add_parser("version", help="Show version info")
    version_parser.add_argument(
        "--json", "-j", action="store_true", help="Output as JSON"
    )
    version_parser.set_defaults(func=cmd_version)

    # doctor command
    doctor_parser = subparsers.add_parser(
        "doctor",
        help="Diagnose common issues with AgentOrchestrator setup"
    )
    doctor_parser.set_defaults(func=cmd_doctor)

    # config command
    config_parser = subparsers.add_parser("config", help="Show configuration (secrets masked)")
    config_parser.add_argument(
        "--json", "-j", action="store_true", help="Output as JSON"
    )
    config_parser.set_defaults(func=cmd_config)

    # debug command
    debug_parser = subparsers.add_parser(
        "debug",
        help="Run chain in debug mode with context snapshots"
    )
    debug_parser.add_argument("chain_name", help="Name of the chain to run")
    debug_parser.add_argument(
        "--company", "-c", help="Company name (shortcut for corporate_company_name)"
    )
    debug_parser.add_argument(
        "--data", "-d", help="JSON input data"
    )
    debug_parser.add_argument(
        "--snapshot-dir", "-s",
        help="Directory for snapshots (default: .agentorchestrator/snapshots)"
    )
    debug_parser.add_argument(
        "--verbose", "-v", action="store_true", help="Show full tracebacks"
    )
    debug_parser.set_defaults(func=cmd_debug)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    if hasattr(args, "func"):
        return args.func(args)
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
