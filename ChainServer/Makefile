# ============================================================
# AgentOrchestrator - Makefile
# ============================================================
#
# Usage:
#   make install      - Install production dependencies
#   make install-dev  - Install all dependencies (including dev)
#   make test         - Run tests
#   make lint         - Run linters
#   make format       - Format code
#   make check        - Run all checks (lint, type-check, test)
#   make run          - Run the CMPT chain test
#   make docs         - Build documentation
#   make clean        - Remove build artifacts
#
# ============================================================

.PHONY: install install-dev lint format type-check test check run docs clean help

# Default target
.DEFAULT_GOAL := help

# Python and UV settings
PYTHON := python3
UV := uv
PIP := $(UV) pip

# Use --system flag if no venv is active (set SYSTEM=1 to install globally)
ifdef SYSTEM
	PIP_FLAGS := --system
else
	PIP_FLAGS :=
endif

# ============================================================
# INSTALLATION
# ============================================================

install:
	@echo "Installing production dependencies..."
	$(PIP) install $(PIP_FLAGS) -r requirements.txt

install-dev:
	@echo "Installing all dependencies (including dev)..."
	$(PIP) install $(PIP_FLAGS) -r requirements.txt -r requirements-dev.txt

install-all:
	@echo "Installing with all optional dependencies..."
	$(PIP) install $(PIP_FLAGS) -r requirements.txt -r requirements-dev.txt -r requirements-optional.txt

install-editable:
	@echo "Installing package in editable mode..."
	$(PIP) install $(PIP_FLAGS) -e .

# ============================================================
# CODE QUALITY
# ============================================================

lint:
	@echo "Running linters..."
	$(PYTHON) -m ruff check agentorchestrator tests examples
	$(PYTHON) -m black --check agentorchestrator tests examples

format:
	@echo "Formatting code..."
	$(PYTHON) -m ruff check --fix agentorchestrator tests examples
	$(PYTHON) -m black agentorchestrator tests examples

type-check:
	@echo "Running type checker..."
	$(PYTHON) -m mypy agentorchestrator

# ============================================================
# TESTING
# ============================================================

test:
	@echo "Running tests..."
	$(PYTHON) -m pytest

test-verbose:
	@echo "Running tests (verbose)..."
	$(PYTHON) -m pytest -v

test-cov:
	@echo "Running tests with coverage..."
	$(PYTHON) -m pytest --cov=agentorchestrator --cov-report=html --cov-report=term-missing

test-fast:
	@echo "Running tests (excluding slow)..."
	$(PYTHON) -m pytest -m "not slow"

# ============================================================
# COMBINED CHECKS
# ============================================================

check: format lint type-check test
	@echo "All checks passed!"

ci: lint type-check test
	@echo "CI checks passed!"

# ============================================================
# RUN EXAMPLES
# ============================================================

run:
	@echo "Running CMPT chain test..."
	$(PYTHON) -m agentorchestrator.test_cmpt_chain

run-quickstart:
	@echo "Running quickstart example..."
	$(PYTHON) examples/quickstart.py

run-meeting-prep:
	@echo "Running meeting prep example..."
	$(PYTHON) examples/meeting_prep_chain.py

run-capiq:
	@echo "Running CapIQ integration example..."
	$(PYTHON) examples/capiq_integration.py

run-custom-agent:
	@echo "Running custom agent example..."
	$(PYTHON) examples/custom_agent_example.py

# ============================================================
# DOCUMENTATION
# ============================================================

docs:
	@echo "Building documentation..."
	$(PYTHON) -m mkdocs build

docs-serve:
	@echo "Serving documentation..."
	$(PYTHON) -m mkdocs serve

# ============================================================
# BUILD & PUBLISH
# ============================================================

build:
	@echo "Building package..."
	$(PYTHON) -m build

publish-test:
	@echo "Publishing to TestPyPI..."
	$(PYTHON) -m twine upload --repository testpypi dist/*

publish:
	@echo "Publishing to PyPI..."
	$(PYTHON) -m twine upload dist/*

# ============================================================
# VIRTUAL ENVIRONMENT
# ============================================================

venv:
	@echo "Creating virtual environment with uv..."
	$(UV) venv .venv
	@echo "Activate with: source .venv/bin/activate"

sync:
	@echo "Syncing dependencies with uv..."
	$(UV) pip sync requirements.txt requirements-dev.txt

# ============================================================
# CLEANUP
# ============================================================

clean:
	@echo "Cleaning build artifacts..."
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type f -name "*.pyo" -delete 2>/dev/null || true
	find . -type f -name "*.pyd" -delete 2>/dev/null || true
	find . -type f -name ".coverage" -delete 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "htmlcov" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "dist" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "build" -exec rm -rf {} + 2>/dev/null || true
	@echo "Clean complete!"

clean-all: clean
	@echo "Removing virtual environment..."
	rm -rf .venv
	@echo "Clean all complete!"

# ============================================================
# PORT MANAGEMENT
# ============================================================

# Kill process on a specific port: make kill-port PORT=6277
kill-port:
	@if [ -z "$(PORT)" ]; then \
		echo "Usage: make kill-port PORT=<port_number>"; \
		echo "Example: make kill-port PORT=6277"; \
	else \
		echo "Finding process on port $(PORT)..."; \
		lsof -ti:$(PORT) | xargs kill -9 2>/dev/null && echo "Killed process on port $(PORT)" || echo "No process found on port $(PORT)"; \
	fi

# Kill common development ports (6277, 8000, 8080, 3000, 5000)
kill-ports:
	@echo "Killing processes on common dev ports..."
	@lsof -ti:6277 | xargs kill -9 2>/dev/null || true
	@lsof -ti:8000 | xargs kill -9 2>/dev/null || true
	@lsof -ti:8080 | xargs kill -9 2>/dev/null || true
	@lsof -ti:3000 | xargs kill -9 2>/dev/null || true
	@lsof -ti:5000 | xargs kill -9 2>/dev/null || true
	@echo "Done!"

# Show what's running on a port: make check-port PORT=6277
check-port:
	@if [ -z "$(PORT)" ]; then \
		echo "Usage: make check-port PORT=<port_number>"; \
	else \
		echo "Process on port $(PORT):"; \
		lsof -i:$(PORT) || echo "Nothing running on port $(PORT)"; \
	fi

# ============================================================
# DEVELOPMENT SETUP
# ============================================================

setup: venv install-dev
	@echo "Setting up pre-commit hooks..."
	$(PYTHON) -m pre_commit install
	@echo "Setup complete!"

# ============================================================
# VIRTUAL ENVIRONMENT
# ============================================================

venv:
	@echo "Creating virtual environment with uv..."
	$(UV) venv .venv
	@echo ""
	@echo "To activate, run:"
	@echo "  source .venv/bin/activate"

activate:
	@echo "Run this command to activate the virtual environment:"
	@echo ""
	@echo "  source .venv/bin/activate"
	@echo ""
	@echo "(Makefile cannot activate venv in your current shell)"

# ============================================================
# REQUIREMENTS MANAGEMENT (uv)
# ============================================================

lock:
	@echo "Creating uv.lock from pyproject.toml..."
	$(UV) lock

sync:
	@echo "Syncing dependencies from uv.lock..."
	$(UV) sync

sync-dev:
	@echo "Syncing all dependencies (including dev) from uv.lock..."
	$(UV) sync --extra dev

export-requirements:
	@echo "Exporting requirements from uv.lock..."
	$(UV) export --no-hashes > requirements.txt
	$(UV) export --extra dev --no-hashes > requirements-dev.txt
	$(UV) export --extra all --no-hashes > requirements-optional.txt

upgrade:
	@echo "Upgrading all dependencies..."
	$(UV) lock --upgrade

# ============================================================
# HELP
# ============================================================

help:
	@echo ""
	@echo "AgentOrchestrator - DAG-based Chain Orchestration Framework"
	@echo "============================================================"
	@echo ""
	@echo "Installation (using uv pip):"
	@echo "  make install       Install production dependencies"
	@echo "  make install-dev   Install all dependencies (including dev)"
	@echo "  make install-all   Install with all optional dependencies"
	@echo "  make install-editable  Install package in editable mode"
	@echo "  make setup         Full development setup (venv + deps + pre-commit)"
	@echo ""
	@echo "Virtual Environment:"
	@echo "  make venv          Create virtual environment with uv"
	@echo "  make activate      Show command to activate venv"
	@echo ""
	@echo "Code Quality:"
	@echo "  make lint          Run linters (ruff, black --check)"
	@echo "  make format        Format code (ruff --fix, black)"
	@echo "  make type-check    Run mypy type checker"
	@echo ""
	@echo "Testing:"
	@echo "  make test          Run tests"
	@echo "  make test-verbose  Run tests (verbose output)"
	@echo "  make test-cov      Run tests with coverage report"
	@echo "  make test-fast     Run tests (excluding slow)"
	@echo ""
	@echo "Combined:"
	@echo "  make check         Run format + lint + type-check + test"
	@echo "  make ci            Run lint + type-check + test (for CI)"
	@echo ""
	@echo "Run Examples:"
	@echo "  make run               Run CMPT chain test"
	@echo "  make run-quickstart    Run quickstart example"
	@echo "  make run-meeting-prep  Run meeting prep example"
	@echo "  make run-capiq         Run CapIQ integration example"
	@echo ""
	@echo "Documentation:"
	@echo "  make docs          Build documentation"
	@echo "  make docs-serve    Serve documentation locally"
	@echo ""
	@echo "Build & Publish:"
	@echo "  make build         Build package"
	@echo "  make publish-test  Publish to TestPyPI"
	@echo "  make publish       Publish to PyPI"
	@echo ""
	@echo "Requirements (uv):"
	@echo "  make lock          Create/update uv.lock from pyproject.toml"
	@echo "  make sync          Sync dependencies from uv.lock"
	@echo "  make sync-dev      Sync all deps (including dev) from uv.lock"
	@echo "  make export-requirements  Export uv.lock to requirements*.txt"
	@echo "  make upgrade       Upgrade all dependencies"
	@echo ""
	@echo "Cleanup:"
	@echo "  make clean         Remove build artifacts"
	@echo "  make clean-all     Remove build artifacts + venv"
	@echo ""
	@echo "Port Management:"
	@echo "  make kill-port PORT=6277  Kill process on specific port"
	@echo "  make kill-ports           Kill common dev ports (6277,8000,8080,3000,5000)"
	@echo "  make check-port PORT=6277 Show what's running on a port"
	@echo ""
