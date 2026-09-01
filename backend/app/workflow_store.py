"""Temporary in-memory storage for generated workflows.

MVP only (Day 1): generated workflows live in memory for the lifetime of the
backend process. Persistence (Firebase / Firestore) is a later phase and is
deliberately NOT implemented here.
"""

from __future__ import annotations

from typing import Any

_generated_workflows: dict[str, dict[str, Any]] = {}


def save_workflow(workflow: dict[str, Any]) -> None:
    """Store a generated workflow keyed by its unique id."""
    _generated_workflows[workflow["id"]] = workflow


def get_workflow(workflow_id: str) -> dict[str, Any] | None:
    """Return a generated workflow by id, or None if it does not exist."""
    return _generated_workflows.get(workflow_id)


def list_workflows() -> list[dict[str, Any]]:
    """Return all generated workflows in insertion order."""
    return list(_generated_workflows.values())