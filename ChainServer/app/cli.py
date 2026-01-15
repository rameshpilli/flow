"""
Memory Store CLI

Command-line interface for managing the memory store service.
"""

import logging
import sys

import uvicorn

from app.config import get_config


def setup_logging(log_level: str = "INFO"):
    """Set up logging configuration."""
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )


def main():
    """Main CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Memory Store Service")
    parser.add_argument(
        "--host",
        default=None,
        help="Host to bind to (overrides config)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Port to bind to (overrides config)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help="Number of workers (overrides config)",
    )
    parser.add_argument(
        "--log-level",
        default=None,
        help="Log level (overrides config)",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload for development",
    )

    args = parser.parse_args()

    # Load configuration
    try:
        config = get_config()
    except ValueError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        sys.exit(1)

    # Set up logging
    log_level = args.log_level or config.service.log_level
    setup_logging(log_level)

    # Get service settings
    host = args.host or config.service.host
    port = args.port or config.service.port
    workers = args.workers or config.service.workers

    # Print configuration
    print("=" * 80)
    print("Memory Store Service")
    print("=" * 80)
    print(f"Host: {host}")
    print(f"Port: {port}")
    print(f"Workers: {workers}")
    print(f"Log Level: {log_level}")
    print(f"Reload: {args.reload}")
    print("=" * 80)
    print(f"\nAPI Docs: http://{host}:{port}/docs")
    print(f"Health Check: http://{host}:{port}/health")
    print("=" * 80)

    # Run the server
    uvicorn.run(
        "app.api:app",
        host=host,
        port=port,
        workers=1 if args.reload else workers,
        log_level=log_level.lower(),
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
