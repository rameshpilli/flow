"""
FlowForge Project Templates

Provides scaffolding templates for new projects, chains, and agents.
"""

from pathlib import Path

TEMPLATES_DIR = Path(__file__).parent


def get_template_path(template_name: str) -> Path:
    """Get path to a template directory."""
    return TEMPLATES_DIR / template_name


__all__ = ["TEMPLATES_DIR", "get_template_path"]
