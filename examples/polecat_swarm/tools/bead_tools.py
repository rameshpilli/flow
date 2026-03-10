"""Bead helper wrappers for expert code."""

from __future__ import annotations

from agentorchestrator.integrations.gastown.bead_client import BeadClient


def bead_labels(bead: dict) -> list[str]:
    labels = bead.get("labels") or []
    return [str(label) for label in labels if label]


def bead_title(bead: dict) -> str:
    return str(bead.get("title") or bead.get("name") or "Untitled bead")


def bead_description(bead: dict) -> str:
    return str(bead.get("description") or "")


def load_bead(repo_root: str, bead_id: str) -> dict:
    return BeadClient(repo_root).show(bead_id)
