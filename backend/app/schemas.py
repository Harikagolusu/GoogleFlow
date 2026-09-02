"""Pydantic models that mirror the frontend contracts in src/types/.

These must match src/types/workflow.ts exactly — the backend response is the
frontend contract and is never redesigned here.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

# Matches WorkflowStatus in src/types/workflow.ts
WorkflowStatus = Literal["Completed", "In Progress", "Action Needed"]


class ChecklistItem(BaseModel):
    """Matches ChecklistItem in src/types/workflow.ts."""

    id: str
    title: str
    completed: bool


class Workflow(BaseModel):
    """Matches the Workflow interface in src/types/workflow.ts."""

    id: str
    title: str
    emoji: str
    date: str
    location: Optional[str] = None
    status: WorkflowStatus
    readiness: int = Field(ge=0, le=100, description="0-100 percent ready")
    nextUp: Optional[str] = None
    checklist: list[ChecklistItem]
    connectedServices: list[str]


class AskRequest(BaseModel):
    """POST /api/ask request body."""

    query: str


class ChecklistItemUpdate(BaseModel):
    """PATCH /api/workflows/{id}/checklist/{item_id} request body."""

    completed: bool