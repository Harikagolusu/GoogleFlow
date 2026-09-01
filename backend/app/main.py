"""GoogleFlow FastAPI backend — MVP (Day 1).

Endpoints:
    GET  /api/health          -> {"status": "ok"}
    POST /api/ask             -> generate a LifeFlow via Gemini, store it in
                                 memory, and return it
    GET  /api/workflows       -> list generated workflows
    GET  /api/workflows/{id}  -> single generated workflow (404 if unknown)
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError

from . import gemini_service, workflow_store
from .schemas import AskRequest, Workflow

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")

DEFAULT_CORS_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:5174",
]


def _cors_origins() -> list[str]:
    configured = os.getenv("CORS_ORIGINS")
    if not configured:
        return DEFAULT_CORS_ORIGINS
    return [origin.strip() for origin in configured.split(",") if origin.strip()]


app = FastAPI(title="GoogleFlow API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_methods=["*"],
    allow_headers=["*"],
)


def _new_workflow_id() -> str:
    while True:
        candidate = f"gen-{uuid.uuid4().hex[:10]}"
        if workflow_store.get_workflow(candidate) is None:
            return candidate


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/ask", response_model=Workflow)
async def create_lifeflow(request: AskRequest) -> Workflow:
    """Create a LifeFlow from a described real-life situation."""
    query = (request.query or "").strip()
    if not query:
        raise HTTPException(
            status_code=400,
            detail="Please describe what you'd like to accomplish.",
        )

    workflow_id = _new_workflow_id()
    try:
        raw = gemini_service.generate_workflow_dict(query, workflow_id)
    except gemini_service.GeminiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    try:
        workflow = Workflow.model_validate(raw)
    except ValidationError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Gemini returned an invalid LifeFlow: {exc}",
        ) from exc

    workflow_store.save_workflow(workflow.model_dump())
    return workflow


@app.get("/api/workflows", response_model=list[Workflow])
def list_workflows() -> list[Workflow]:
    """List all workflows generated in this backend session."""
    return [Workflow.model_validate(wf) for wf in workflow_store.list_workflows()]


@app.get("/api/workflows/{workflow_id}", response_model=Workflow)
def get_workflow(workflow_id: str) -> Workflow:
    """Return a generated workflow by id, or 404 if it does not exist."""
    stored = workflow_store.get_workflow(workflow_id)
    if stored is None:
        raise HTTPException(status_code=404, detail="Workflow not found.")
    return Workflow.model_validate(stored)