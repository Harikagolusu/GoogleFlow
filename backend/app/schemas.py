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


class WorkflowPriority(BaseModel):
    """Priority classification for a LifeFlow."""

    value: Literal["high", "medium", "low"] = "medium"


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
    priority: Optional[str] = Field(
        default="medium",
        description="AI-assigned priority: high, medium, or low. backward compat: older workflows may be missing this field.",
    )
    confidence: Optional[float] = Field(
        default=None,
        description="AI confidence score 0.0-1.0 that this LifeFlow is genuinely useful. Older workflows may be missing this field.",
    )


class AskRequest(BaseModel):
    """POST /api/ask request body."""

    query: str


class ChecklistItemUpdate(BaseModel):
    """PATCH /api/workflows/{id}/checklist/{item_id} request body."""

    completed: bool


# ---------------------------------------------------------------------------
# Gmail analysis
# ---------------------------------------------------------------------------


class GmailAnalyzeRequest(BaseModel):
    """POST /api/gmail/analyze request body."""

    limit: int = Field(default=30, ge=1, le=50, description="Max emails to analyze")


class GmailAnalyzeResponse(BaseModel):
    """POST /api/gmail/analyze response body."""

    success: bool
    emailsAnalyzed: int
    flowsCreated: int
    flowsUpdated: int
    flowsIgnored: int
    message: str
    lowConfidenceIgnored: int = Field(
        default=0,
        description="Flows ignored because their confidence score was below the threshold.",
    )


# ---------------------------------------------------------------------------
# Unified multi-service analysis
# ---------------------------------------------------------------------------


class AnalyzeRequest(BaseModel):
    """POST /api/analyze request body — unified."""

    # Optional per-service limits; if not set, server uses defaults.
    gmailLimit: int | None = Field(default=None, ge=1, le=50)
    calendarLimit: int | None = Field(default=None, ge=1, le=50)
    driveLimit: int | None = Field(default=None, ge=1, le=50)
    # Optional: limit services analyzed; empty means auto (connected services only).
    services: list[str] | None = None
    # Optional: user query / destination for Maps context.
    query: str | None = None
    origin: str | None = None
    destination: str | None = None


class AnalyzeResponse(BaseModel):
    """POST /api/analyze response body."""

    success: bool
    flowsCreated: int
    flowsIgnored: int
    message: str
    gmailAnalyzed: int = 0
    calendarAnalyzed: int = 0
    driveAnalyzed: int = 0
    mapsUsed: bool = False
    emailsAnalyzed: int = 0
    lowConfidenceIgnored: int = Field(
        default=0,
        description="Flows ignored because their confidence score was below the threshold.",
    )


# ---------------------------------------------------------------------------
# Maps
# ---------------------------------------------------------------------------


class MapsGeocodeRequest(BaseModel):
    """POST /api/maps/geocode request body."""

    address: str = Field(description="Address or place name to geocode")


class MapsDirectionsRequest(BaseModel):
    """POST /api/maps/directions request body."""

    origin: str
    destination: str
    mode: str = Field(default="driving", description="driving|walking|bicycling|transit")


# ---------------------------------------------------------------------------
# Related resources (Gmail, Calendar, Drive) for workflow detail view
# ---------------------------------------------------------------------------


class RelatedEmail(BaseModel):
    """Gmail message reference stored with a workflow."""

    id: str
    sender: str
    subject: str
    date: str
    snippet: str


class RelatedCalendarEvent(BaseModel):
    """Calendar event reference stored with a workflow."""

    id: str
    summary: str
    start: str
    end: str
    location: str
    displayStart: str
    htmlLink: str = ""
    meetingUrl: str = ""


class RelatedDriveFile(BaseModel):
    """Drive file reference stored with a workflow."""

    id: str
    name: str
    mimeType: str
    modifiedTime: str
    webViewLink: str


class RelatedResources(BaseModel):
    """Related Gmail / Calendar / Drive resources for a workflow."""

    emails: list[RelatedEmail] = Field(default_factory=list)
    calendarEvents: list[RelatedCalendarEvent] = Field(default_factory=list)
    driveFiles: list[RelatedDriveFile] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpful YouTube video recommendations
# ---------------------------------------------------------------------------


class VideoRecommendation(BaseModel):
    """A YouTube video recommendation for a workflow."""

    id: str
    title: str
    channelTitle: str = ""
    thumbnail: str = ""
    publishedAt: str = ""
    url: str = ""


class WorkflowDetail(BaseModel):
    """Extended workflow response including related resources and videos."""

    workflow: Workflow
    relatedResources: RelatedResources = Field(default_factory=RelatedResources)
    helpfulVideos: list[VideoRecommendation] = Field(default_factory=list)