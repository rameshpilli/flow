#!/usr/bin/env python3
"""
FlowForge CLI

Command-line interface for running chains, validating definitions, and scaffolding.

Usage:
    flowforge run <chain_name> [--company "Apple"] [--data '{"key": "value"}']
    flowforge check [<chain_name>]
    flowforge list
    flowforge graph <chain_name> [--format mermaid]
    flowforge new agent <name>
    flowforge new chain <name>
    flowforge dev [--watch]
    flowforge health
    flowforge version
"""

import argparse
import asyncio
import importlib
import importlib.util
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any


def get_forge():
    """
    Get or create the FlowForge instance, importing chain definitions.

    Uses importlib.util for proper module loading without sys.path manipulation.
    """
    from flowforge import FlowForge, get_forge as _get_forge

    cwd = Path.cwd()

    # Look for common chain definition files
    definition_files = [
        "chains.py",
        "flowforge_chains.py",
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
        from flowforge.chains import CMPTChain
    except ImportError:
        pass

    return _get_forge()


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


def cmd_run(args: argparse.Namespace) -> int:
    """Run a chain with optional input data."""
    forge = get_forge()

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

    print(f"\n{'═' * 60}")
    print(f"  Running: {args.chain_name}")
    print(f"  Input: {json.dumps(data, indent=2) if data else '{}'}")
    print(f"{'═' * 60}\n")

    start_time = time.perf_counter()

    try:
        result = asyncio.run(forge.launch(args.chain_name, data))
        duration = (time.perf_counter() - start_time) * 1000

        print(f"\n{'═' * 60}")
        print(f"  Result: {'SUCCESS' if result.get('success') else 'FAILED'}")
        print(f"  Duration: {duration:.2f}ms")
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


def cmd_check(args: argparse.Namespace) -> int:
    """Validate chain definitions."""
    forge = get_forge()

    result = forge.check(args.chain_name)

    return 0 if result.get("valid") else 1


def cmd_list(args: argparse.Namespace) -> int:
    """List all definitions."""
    forge = get_forge()

    forge.list_defs()

    return 0


def cmd_graph(args: argparse.Namespace) -> int:
    """Show DAG visualization."""
    forge = get_forge()

    try:
        forge.graph(args.chain_name, format=args.format)
        return 0
    except Exception as e:
        print(f"Error: {e}")
        return 1


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

from flowforge.agents.base import BaseAgent, AgentResult


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


# Register with FlowForge
def register(forge):
    """Register this agent with FlowForge instance."""
    forge.register_agent("{name.lower()}", {name}Agent)
'''

    if agent_file.exists() and not args.force:
        print(f"Error: {agent_file} already exists. Use --force to overwrite.")
        return 1

    agent_file.write_text(template)
    print(f"Created: {agent_file}")
    print(f"\nTo use this agent:")
    print(f"  from {name.lower()}_agent import {name}Agent")
    print(f"  agent = {name}Agent()")
    print(f"  result = await agent.fetch('query')")

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

from flowforge import FlowForge, ChainContext


# Create FlowForge instance (isolated for this chain)
forge = FlowForge(name="{name.lower()}", isolated=True)


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
    print(f"\nTo use this chain:")
    print(f"  from {name.lower()}_chain import run, check, graph")
    print(f"  result = await run({{'key': 'value'}})")
    print(f"\nOr via CLI:")
    print(f"  flowforge run {name}Chain")

    return 0


def cmd_health(args: argparse.Namespace) -> int:
    """Check health status of FlowForge."""
    from flowforge.utils.config import get_health

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
        print(f"  FlowForge Health Check")
        print(f"{'═' * 50}\n")

        print(f"  Status: {color}{health.status.upper()}{reset}")
        print(f"  Version: {health.version}")
        print(f"  Environment: {health.environment}")

        if health.checks:
            print(f"\n  Checks:")
            for check, passed in health.checks.items():
                icon = "✓" if passed else "✗"
                check_color = "\033[92m" if passed else "\033[91m"
                print(f"    {check_color}{icon}{reset} {check}")

        print(f"\n{'═' * 50}\n")

        if args.json:
            print(json.dumps(health.to_dict(), indent=2))

        return 0 if health.status == "healthy" else 1

    except Exception as e:
        print(f"Error checking health: {e}")
        return 1


def cmd_version(args: argparse.Namespace) -> int:
    """Show version information."""
    from flowforge.utils.config import get_version

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


def cmd_config(args: argparse.Namespace) -> int:
    """Show current configuration (secrets masked)."""
    from flowforge.utils.config import get_config, ConfigError

    try:
        config = get_config()
        safe_config = config.to_safe_dict()

        print(f"\n{'═' * 50}")
        print(f"  FlowForge Configuration")
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


def cmd_dev(args: argparse.Namespace) -> int:
    """Run in development mode with hot reloading."""
    print("Starting FlowForge development server...")

    # Try to import watchdog for file watching
    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler
        WATCHDOG_AVAILABLE = True
    except ImportError:
        WATCHDOG_AVAILABLE = False
        if args.watch:
            print("Warning: watchdog not installed. Install with: pip install watchdog")
            print("Running without hot reload...")

    forge = get_forge()

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
    from flowforge.utils.config import get_config
    import datetime

    forge = get_forge()
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
    from flowforge.core.context import ChainContext

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


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="flowforge",
        description="FlowForge CLI - DAG-based Chain Orchestration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  flowforge run cmpt_chain --company "Apple Inc"
  flowforge check
  flowforge list
  flowforge graph cmpt_chain --format mermaid
  flowforge new agent MyCustomAgent
  flowforge new chain DataPipeline
  flowforge dev --watch
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
        "extra", nargs="*", help="Additional key=value pairs"
    )
    run_parser.set_defaults(func=cmd_run)

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

    # dev command
    dev_parser = subparsers.add_parser("dev", help="Development mode with hot reload")
    dev_parser.add_argument(
        "--watch", "-w", action="store_true", help="Watch for file changes"
    )
    dev_parser.set_defaults(func=cmd_dev)

    # health command
    health_parser = subparsers.add_parser("health", help="Check health status")
    health_parser.add_argument(
        "--json", "-j", action="store_true", help="Output as JSON"
    )
    health_parser.set_defaults(func=cmd_health)

    # version command
    version_parser = subparsers.add_parser("version", help="Show version info")
    version_parser.add_argument(
        "--json", "-j", action="store_true", help="Output as JSON"
    )
    version_parser.set_defaults(func=cmd_version)

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
        help="Directory for snapshots (default: .flowforge/snapshots)"
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
