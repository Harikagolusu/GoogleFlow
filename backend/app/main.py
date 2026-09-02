"""GoogleFlow FastAPI backend — MVP (Firebase auth + Firestore phase).

Endpoints:
    GET    /api/health                    -> {"status": "ok"} (public)
    POST   /api/ask                       -> generate a LifeFlow via Gemini,
                                             persist it under the
                                             authenticated user, return it
    GET    /api/workflows                 -> the user's workflows
    GET    /api/workflows/{workflow_id}   -> single workflow (404 if missing
                                             or not owned)
    PATCH  /api/workflows/{workflow_id}/checklist/{item_id}
                                          -> set one checklist item, recompute
                                             readiness / status / nextUp

Authentication:
    The frontend sends the Firebase ID token as `Authorization: Bearer <token>`.
    The backend verifies it with the Firebase Admin SDK and derives the UID —
    a UID sent by the client is never trusted. When Firebase is NOT configured
    the API runs in demo mode (no auth, in-memory store) so local development
    keeps working.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError

from . import firebase_service, gemini_service, workflow_store
from .schemas import AskRequest, ChecklistItemUpdate, Workflow

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


# Firebase Admin (auth + Firestore) or demo mode. Fails fast on bad config.
firebase_service.init()
workflow_store.init(firebase_service.get_firestore() if firebase_service.is_enabled() else None)

app = FastAPI(title="GoogleFlow API", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_methods=["*"],
    allow_headers=["*"],
)


def _require_uid(request: Request) -> str:
    """Return the verified Firebase UID ("" in demo mode)."""
    if not firebase_service.is_enabled():
        return ""

    auth_header = request.headers.get("authorization") or ""
    if not auth_header.lower().startswith("bearer "):
        raise HTTPException(
            status_code=401,
            detail="Sign in with Google to access your LifeFlows.",
        )
    token = auth_header.split(" ", 1)[1].strip()
    try:
        return firebase_service.verify_id_token(token)
    except Exception as exc:
        raise HTTPException(
            status_code=401,
            detail="Your session has expired. Please sign in again.",
        ) from exc


def _new_workflow_id() -> str:
    while True:
        candidate = f"gen-{uuid.uuid4().hex[:10]}"
        # Demo store check; Firestore ids are namespaced per user anyway.
        if workflow_store.get_workflow(None, candidate) is None:
            return candidate


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/ask", response_model=Workflow)
async def create_lifeflow(request: Request, payload: AskRequest) -> Workflow:
    """Create a LifeFlow from a described real-life situation."""
    uid = _require_uid(request)

    query = (payload.query or "").strip()
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

    workflow_store.save_workflow(uid or None, workflow.model_dump(), is_new=True)
    return workflow


@app.get("/api/workflows", response_model=list[Workflow])
def list_workflows(request: Request) -> list[Workflow]:
    """List the authenticated user's workflows."""
    uid = _require_uid(request)
    return [
        Workflow.model_validate(wf)
        for wf in workflow_store.list_workflows(uid or None)
    ]


@app.get("/api/workflows/{workflow_id}", response_model=Workflow)
def get_workflow(request: Request, workflow_id: str) -> Workflow:
    """Return one of the user's workflows (404 if missing or not owned)."""
    uid = _require_uid(request)
    stored = workflow_store.get_workflow(uid or None, workflow_id)
    if stored is None:
        raise HTTPException(status_code=404, detail="Workflow not found.")
    return Workflow.model_validate(stored)


@app.patch(
    "/api/workflows/{workflow_id}/checklist/{item_id}",
    response_model=Workflow,
)
def update_checklist_item(
    request: Request,
    workflow_id: str,
    item_id: str,
    payload: ChecklistItemUpdate,
) -> Workflow:
    """Set one checklist item and recompute readiness / status / nextUp."""
    uid = _require_uid(request)
    stored = workflow_store.get_workflow(uid or None, workflow_id)
    if stored is None:
        raise HTTPException(status_code=404, detail="Workflow not found.")

    updated = workflow_store.apply_checklist_update(stored, item_id, payload.completed)
    if updated is None:
        raise HTTPException(status_code=404, detail="Checklist item not found.")

    workflow_store.save_workflow(uid or None, updated)
    return Workflow.model_validate(updated)