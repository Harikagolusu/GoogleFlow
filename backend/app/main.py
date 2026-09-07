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
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import ValidationError

FRONTEND_DIST = os.environ.get("FRONTEND_DIST", str(Path(__file__).resolve().parent.parent.parent / "dist"))

from . import firebase_service, gemini_service, workflow_store
from .schemas import (
    AskRequest,
    ChecklistItemUpdate,
    GmailAnalyzeRequest,
    GmailAnalyzeResponse,
    Workflow,
    AnalyzeRequest,
    AnalyzeResponse,
    MapsGeocodeRequest,
    MapsDirectionsRequest,
    RelatedResources,
    WorkflowDetail,
    VideoRecommendation,
    RelatedEmail,
    RelatedCalendarEvent,
    RelatedDriveFile,
)
from . import connections_store, google_auth, gmail_connector
from . import calendar_connector, drive_connector, maps_service
from . import youtube_service
from .service_registry import (
    SERVICE_GMAIL,
    SERVICE_CALENDAR,
    SERVICE_DRIVE,
    SERVICE_MAPS,
    OAUTH_SERVICES,
    SCOPES_FOR_SERVICE,
)

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")

DEFAULT_CORS_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:5174",
    "http://172.19.92.95:5173",
    "http://172.19.92.95:5174",
    "http://172.19.92.95:3000",
    "http://172.19.92.95:8010",
    "*",
]


def _cors_origins() -> list[str]:
    configured = os.getenv("CORS_ORIGINS")
    if configured:
        return [origin.strip() for origin in configured.split(",") if origin.strip()]
    return ["*"]


# Firebase Admin (auth + Firestore) or demo mode. Fails fast on bad config.
firebase_service.init()
_firestore_client = firebase_service.get_firestore() if firebase_service.is_enabled() else None
workflow_store.init(_firestore_client)
connections_store.init(_firestore_client)
google_auth.init_firestore(_firestore_client)

app = FastAPI(title="GoogleFlow API", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files (JS, CSS, images) from the React build
_dist_path = Path(FRONTEND_DIST)
if _dist_path.exists():
    app.mount("/assets", StaticFiles(directory=str(_dist_path / "assets"), html=False), name="static")


DEMO_UID = "demo-user"


def _require_uid(request: Request) -> str:
    """Return the verified Firebase UID (DEMO_UID in demo mode)."""
    if not firebase_service.is_enabled():
        return DEMO_UID

    auth_header = request.headers.get("authorization") or ""
    if not auth_header.lower().startswith("bearer "):
        raise HTTPException(
            status_code=401,
            detail="Sign in with Google to access your LifeFlows.",
        )
    token = auth_header.split(" ", 1)[1].strip()
    try:
        uid = firebase_service.verify_id_token(token)
        return uid
    except Exception as exc:
        import logging
        logging.warning("_require_uid: token verification failed: %s %s", type(exc).__name__, exc)
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
    """Create a LifeFlow from a described real-life situation.

    First searches connected Google services (Gmail, Calendar, Drive) for relevant
    data based on the query. Only creates a LifeFlow if relevant data is found.
    """
    uid = _require_uid(request)

    query = (payload.query or "").strip()
    if not query:
        raise HTTPException(
            status_code=400,
            detail="Please describe what you'd like to accomplish.",
        )

    diag = logging.getLogger("googleflow.analyze.diag")
    diag.info("=== ASK PIPELINE START ===")
    diag.info("uid=%s query=%s", uid, query[:100])

    gmail_messages: list[dict[str, Any]] = []
    calendar_events: list[dict[str, Any]] = []
    drive_files: list[dict[str, Any]] = []

    gmail_status = connections_store.get_public_connection(uid, "gmail")
    calendar_status = connections_store.get_public_connection(uid, "calendar")
    drive_status = connections_store.get_public_connection(uid, "drive")

    has_gmail = bool(gmail_status.get("connected"))
    has_calendar = bool(calendar_status.get("connected"))
    has_drive = bool(drive_status.get("connected"))

    if has_gmail:
        try:
            msgs = gmail_connector.fetch_recent_messages(uid, max_results=30)
            query_lower = query.lower()
            query_words = set(query_lower.split())
            gmail_messages = [
                m for m in msgs
                if any(word in (m.get("subject", "") + " " + m.get("snippet", "")).lower()
                   for word in query_words if len(word) > 3)
            ][:5]
            diag.info("Gmail search: found %d relevant out of %d", len(gmail_messages), len(msgs))
        except Exception as exc:
            diag.warning("Gmail search failed: %s", exc)

    if has_calendar:
        try:
            events = calendar_connector.search_events(uid, query, max_results=10)
            calendar_events = events[:5]
            diag.info("Calendar search: found %d relevant", len(calendar_events))
        except Exception as exc:
            diag.warning("Calendar search failed: %s", exc)

    if has_drive:
        try:
            files = drive_connector.fetch_recent_files(uid, max_results=30)
            query_lower = query.lower()
            query_words = set(query_lower.split())
            drive_files = [
                f for f in files
                if any(word in f.get("name", "").lower()
                   for word in query_words if len(word) > 3)
            ][:5]
            drive_hints = {"resume", "cv", "document", "file", "pdf", "drive", "folder", "sheet", "slide"}
            if not drive_files and any(hint in query_lower for hint in drive_hints):
                drive_files = files[:3]
            diag.info("Drive search: found %d relevant out of %d", len(drive_files), len(files))
        except Exception as exc:
            diag.warning("Drive search failed: %s", exc)

    total_found = len(gmail_messages) + len(calendar_events) + len(drive_files)
    diag.info("Total relevant data found: %d", total_found)

    if total_found == 0:
        raise HTTPException(
            status_code=404,
            detail=(
                "No relevant data found in your connected services. "
                "Try a different query or connect more services."
            ),
        )

    workflow_id = _new_workflow_id()

    try:
        raw = gemini_service.generate_workflow_dict_from_context(
            query=query,
            workflow_id=workflow_id,
            gmail_messages=gmail_messages,
            calendar_events=calendar_events,
            drive_files=drive_files,
        )
    except gemini_service.GeminiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    try:
        workflow = Workflow.model_validate(raw)
    except ValidationError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Gemini returned an invalid LifeFlow: {exc}",
        ) from exc

    workflow_dict = workflow.model_dump()
    workflow_dict["_sourceMessageIds"] = [m["id"] for m in gmail_messages]
    workflow_dict["_sourceEventIds"] = [e["id"] for e in calendar_events]
    workflow_dict["_sourceFileIds"] = [f["id"] for f in drive_files]

    workflow_store.save_workflow(uid or None, workflow_dict, is_new=True)
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


@app.delete("/api/workflows/{workflow_id}")
def delete_workflow(request: Request, workflow_id: str) -> dict[str, str]:
    """Delete one of the user's workflows."""
    uid = _require_uid(request)
    deleted = workflow_store.delete_workflow(uid or None, workflow_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Workflow not found.")
    return {"deleted": workflow_id}


@app.get("/api/workflows/{workflow_id}/detail", response_model=WorkflowDetail)
def get_workflow_detail(request: Request, workflow_id: str) -> WorkflowDetail:
    """Return a workflow with related Gmail/Calendar/Drive resources and YouTube videos.

    Related resources are fetched dynamically using the source IDs stored with the
    workflow. Only resources that actually exist and are owned by the user are returned.
    Invalid or expired source references are silently discarded.

    YouTube videos are searched based on the workflow title and checklist items.
    Returns empty lists when no sources are linked or YouTube is not configured.
    """
    uid = _require_uid(request)
    stored = workflow_store.get_workflow(uid or None, workflow_id)
    if stored is None:
        raise HTTPException(status_code=404, detail="Workflow not found.")

    workflow = Workflow.model_validate(stored)

    source_msg_ids = stored.get("_sourceMessageIds", [])
    source_event_ids = stored.get("_sourceEventIds", [])
    source_file_ids = stored.get("_sourceFileIds", [])

    related_emails: list[RelatedEmail] = []
    related_events: list[RelatedCalendarEvent] = []
    related_drives: list[RelatedDriveFile] = []

    if source_msg_ids:
        try:
            msgs = gmail_connector.fetch_messages_by_ids(uid, source_msg_ids)
            msg_map = {m["id"]: m for m in msgs}
            for mid in source_msg_ids:
                if mid in msg_map:
                    m = msg_map[mid]
                    related_emails.append(RelatedEmail(
                        id=m["id"],
                        sender=m.get("sender", ""),
                        subject=m.get("subject", ""),
                        date=m.get("date", ""),
                        snippet=m.get("snippet", ""),
                    ))
        except Exception:
            pass

    if source_event_ids:
        try:
            events = calendar_connector.fetch_upcoming_events(uid, max_results=20, days_ahead=60)
            event_map = {e["id"]: e for e in events}
            for eid in source_event_ids:
                if eid in event_map:
                    e = event_map[eid]
                    related_events.append(RelatedCalendarEvent(
                        id=e["id"],
                        summary=e.get("summary", ""),
                        start=e.get("start", ""),
                        end=e.get("end", ""),
                        location=e.get("location", ""),
                        displayStart=e.get("displayStart", ""),
                        htmlLink=e.get("htmlLink", ""),
                        meetingUrl=e.get("meetingUrl", ""),
                    ))
        except Exception:
            pass

    if not related_events and source_msg_ids:
        try:
            import re
            for email in related_emails:
                combined_text = f"{email.subject} {email.snippet}".lower()
                if not any(kw in combined_text for kw in ["interview", "calendar", "meeting", "invitation", "schedule"]):
                    continue

                keywords = []
                title_match = re.search(r"(?:interview|meeting|event)[:\s]+([^\n\r]{5,80})", combined_text, re.IGNORECASE)
                if title_match:
                    keywords.append(title_match.group(1).strip())

                date_match = re.search(r"(?:thu|fri|sat|sun|mon|tue|wed)[a-z]*\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2}[,\s]+\d{4}", combined_text, re.IGNORECASE)
                if date_match:
                    keywords.append(date_match.group(0))

                if keywords:
                    search_query = " ".join(keywords[:3])
                    try:
                        found_events = calendar_connector.search_events(uid, search_query, max_results=5)
                        for ev in found_events:
                            if ev.get("summary") and not any(e.id == ev["id"] for e in related_events):
                                related_events.append(RelatedCalendarEvent(
                                    id=ev["id"],
                                    summary=ev.get("summary", ""),
                                    start=ev.get("start", ""),
                                    end=ev.get("end", ""),
                                    location=ev.get("location", ""),
                                    displayStart=ev.get("displayStart", ""),
                                    htmlLink=ev.get("htmlLink", ""),
                                    meetingUrl=ev.get("meetingUrl", ""),
                                ))
                    except Exception:
                        pass

            if not related_events:
                bodies = gmail_connector.fetch_message_bodies(uid, source_msg_ids)
                for mid in source_msg_ids:
                    if mid not in bodies:
                        continue
                    body = bodies[mid].get("body", "") or ""

                    meet_match = re.search(r"https?://meet\.google\.com/[a-z]{3}-[a-z]{4}-[a-z]{3}[^\s]*", body, re.IGNORECASE)
                    location_lines = []
                    in_location = False
                    for line in body.split("\n"):
                        if re.match(r"^Location\s*:?\s*$", line.strip(), re.IGNORECASE):
                            in_location = True
                            continue
                        if in_location:
                            if line.strip() and not line.strip().startswith("http") and not line.strip().startswith("Join"):
                                location_lines.append(line.strip())
                            else:
                                break
                    location_text = " ".join(location_lines[:2])

                    date_match = re.search(r"(Thursday|Friday|Saturday|Sunday|Monday|Tuesday|Wednesday)\s+\w+\s+\d{1,2},\s+\d{4}\s*⋅\s*\d+am\s*–\s*\d+pm", body)

                    if meet_match or location_text:

                        related_events.append(RelatedCalendarEvent(
                            id=f"email-{mid}",
                            summary=email.subject if email else "",
                            start="",
                            end="",
                            location=location_text,
                            displayStart=date_match.group(0) if date_match else "",
                            htmlLink="",
                            meetingUrl=meet_match.group(0) if meet_match else "",
                        ))
        except Exception:
            pass

    # Fallback for LifeFlows that never stored source event IDs (e.g. created
    # via Ask LifeFlow): search the calendar using the workflow's own keywords
    # (title, location, next action) so the Calendar card still appears with
    # its location and meeting links when a matching event exists.
    if not related_events:
        try:
            search_terms = [
                workflow.title,
                workflow.location,
                workflow.nextUp,
            ]
            search_query = " ".join(t for t in search_terms if t).strip()[:200]
            if search_query:
                found_events = calendar_connector.search_events(uid, search_query, max_results=5)
                for ev in found_events:
                    if ev.get("summary") and not any(e.id == ev["id"] for e in related_events):
                        related_events.append(RelatedCalendarEvent(
                            id=ev["id"],
                            summary=ev.get("summary", ""),
                            start=ev.get("start", ""),
                            end=ev.get("end", ""),
                            location=ev.get("location", ""),
                            displayStart=ev.get("displayStart", ""),
                            htmlLink=ev.get("htmlLink", ""),
                            meetingUrl=ev.get("meetingUrl", ""),
                        ))
        except Exception:
            pass

    if source_file_ids:
        try:
            files = drive_connector.fetch_recent_files(uid, max_results=20)
            file_map = {f["id"]: f for f in files}
            for fid in source_file_ids:
                if fid in file_map:
                    f = file_map[fid]
                    related_drives.append(RelatedDriveFile(
                        id=f["id"],
                        name=f.get("name", ""),
                        mimeType=f.get("mimeType", ""),
                        modifiedTime=f.get("modifiedTime", ""),
                        webViewLink=f.get("webViewLink", ""),
                    ))
        except Exception:
            pass

    related_resources = RelatedResources(
        emails=related_emails,
        calendarEvents=related_events,
        driveFiles=related_drives,
    )

    if related_events and 'Calendar' not in workflow.connectedServices:
        workflow.connectedServices = list(workflow.connectedServices) + ['Calendar']

    youtube_topics: list[str] = []
    for email in related_emails:
        combined_text = f"{email.subject} {email.snippet}".lower()
        import re
        topic_lines = re.findall(
            r"(?:topics?|preparation|focus on|covering|will cover|discuss|questions about|areas?)\s*[:\-]\s*([^\n\r]{10,200})",
            combined_text,
            re.IGNORECASE,
        )
        for line in topic_lines:
            topics = re.split(r"[,;•·•·]+", line)
            for t in topics:
                t = t.strip()
                if 3 < len(t) < 60:
                    youtube_topics.append(t)

    if youtube_topics:
        search_query = " | ".join(youtube_topics[:5])
    else:
        search_query = workflow.title

    helpful_videos_raw = youtube_service.search_videos(
        workflow_title=search_query,
        checklist=[{"title": c.title} for c in workflow.checklist],
    )
    helpful_videos = [
        VideoRecommendation(
            id=v["id"],
            title=v["title"],
            channelTitle=v.get("channelTitle", ""),
            thumbnail=v.get("thumbnail", ""),
            publishedAt=v.get("publishedAt", ""),
            url=v.get("url", ""),
        )
        for v in helpful_videos_raw
    ]

    return WorkflowDetail(
        workflow=workflow,
        relatedResources=related_resources,
        helpfulVideos=helpful_videos,
    )


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

# ---------------------------------------------------------------------------
# Google Apps OAuth — generic layer (Gmail, Calendar, Drive)
# ---------------------------------------------------------------------------
# Gmail routes are preserved verbatim for backward compat; generic
# /api/auth/{service}/* routes reuse the same logic via _oauth_* helpers.
# Frontend redirects the browser to:
#   GET /api/auth/{service}/connect   or legacy GET /api/auth/gmail/connect
# The backend verifies the Firebase ID token, generates a cryptographically
# secure state, stores state->UID server-side, and redirects the browser to
# Google's consent screen. The frontend never sees the OAuth client secret
# or the access/refresh tokens.

DEFAULT_FRONTEND_URL = "http://localhost:3000"

import logging

_callback_logger = logging.getLogger("googleflow.callback")


def _frontend_base_url() -> str:
    return (
        os.getenv("FRONTEND_URL")
        or os.getenv("VITE_API_URL")
        or DEFAULT_FRONTEND_URL
    ).rstrip("/")


def _require_oauth_configured() -> None:
    if not google_auth.is_configured():
        raise HTTPException(
            status_code=503,
            detail="Google OAuth is not configured. Set GOOGLE_OAUTH_CLIENT_ID, "
                    "GOOGLE_OAUTH_CLIENT_SECRET, and GOOGLE_OAUTH_REDIRECT_URI.",
        )


def _validate_oauth_service(service: str) -> None:
    if service not in OAUTH_SERVICES:
        raise HTTPException(status_code=404, detail=f"Unknown service: {service}")


def _oauth_build_url(service: str, uid: str) -> dict[str, Any]:
    _validate_oauth_service(service)
    _require_oauth_configured()
    try:
        return google_auth.build_authorization_url(service, uid)
    except google_auth.StateError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def _oauth_status(uid: str, service: str) -> dict[str, Any]:
    _validate_oauth_service(service)
    return connections_store.get_public_connection(uid, service)


def _oauth_disconnect(uid: str, service: str) -> dict[str, Any]:
    _validate_oauth_service(service)
    existing = connections_store.get_connection(uid, service)
    if existing is None:
        return {"disconnected": True, "service": service, "was_connected": False}
    refresh_token = existing.get("refresh_token")
    access_token = existing.get("access_token")
    revoked = False
    if refresh_token:
        revoked = google_auth.revoke_token(refresh_token) or revoked
    if access_token and not revoked:
        google_auth.revoke_token(access_token)
    connections_store.delete_connection(uid, service)
    return {"disconnected": True, "service": service, "was_connected": True}


def _handle_oauth_callback(
    code: str | None,
    state: str | None,
    error: str | None,
) -> RedirectResponse:
    """Shared callback logic — service is recovered from state record."""
    frontend = _frontend_base_url()
    _callback_logger.warning(
        "OAuth callback received: frontend=%s error=%s code_present=%s state_present=%s",
        frontend, error, bool(code), bool(state),
    )
    if error:
        _callback_logger.warning("OAuth callback: Google returned error=%s", error)
        return RedirectResponse(f"{frontend}/profile?gmail=denied", status_code=302)
    if not code or not state:
        _callback_logger.warning("OAuth callback: missing code or state")
        return RedirectResponse(f"{frontend}/profile?gmail=invalid", status_code=302)
    try:
        record = google_auth.validate_and_consume_state(state)
        _callback_logger.warning("OAuth callback: state valid, uid=%s service=%s", record.get("uid", "<none>")[:8], record.get("service"))
    except google_auth.StateError as exc:
        _callback_logger.warning("OAuth callback: state validation failed: %s", exc)
        return RedirectResponse(f"{frontend}/profile?gmail=invalid", status_code=302)

    uid = record.get("uid") or DEMO_UID
    service = record.get("service") or SERVICE_GMAIL
    if service not in OAUTH_SERVICES:
        service = SERVICE_GMAIL
    try:
        credentials = google_auth.exchange_code(code)
        _callback_logger.warning("OAuth callback: code exchange succeeded, service=%s has_refresh=%s", service, bool(credentials.get("refresh_token")))
    except google_auth.StateError as exc:
        _callback_logger.warning("OAuth callback: code exchange failed: %s", exc)
        return RedirectResponse(f"{frontend}/profile?{service}=failed", status_code=302)
    except Exception as exc:
        _callback_logger.error("OAuth callback: unexpected error during code exchange: %s", exc, exc_info=True)
        return RedirectResponse(f"{frontend}/profile?{service}=failed", status_code=302)

    scopes = SCOPES_FOR_SERVICE.get(service, [])
    connections_store.save_connection(
        uid,
        service,
        scopes=scopes,
        access_token=credentials.get("access_token"),
        refresh_token=credentials.get("refresh_token"),
        expires_in=credentials.get("expires_in"),
    )
    _callback_logger.warning("OAuth callback: connection saved service=%s, redirecting to %s/profile?%s=connected", service, frontend, service)
    return RedirectResponse(f"{frontend}/profile?{service}=connected", status_code=302)


@app.get("/api/auth/gmail/connect")
def gmail_connect(request: Request) -> RedirectResponse:
    """Redirect the browser to Google's Gmail consent screen.

    Requires an authenticated Firebase user. UID is recovered from the
    verified Firebase ID token; never trusted from a client-supplied value.
    """
    uid = _require_uid(request)
    _require_oauth_configured()
    try:
        result = google_auth.build_authorization_url("gmail", uid)
    except google_auth.StateError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return RedirectResponse(result["authorization_url"], status_code=302)


@app.post("/api/auth/gmail/connect")
def gmail_connect_json(request: Request) -> dict[str, Any]:
    """Return the Google consent URL as JSON for the frontend service layer.

    Preferred connect path when Firebase auth is enabled: the frontend sends
    ``Authorization: Bearer <Firebase ID token>`` (via http.ts) and receives
    ``{"authorization_url": "https://accounts.google.com/..."}``, then
    navigates the browser to that URL. This keeps the token in the header
    (never a query parameter) and the OAuth client secret stays backend-only.
    """
    uid = _require_uid(request)
    _require_oauth_configured()
    try:
        result = google_auth.build_authorization_url("gmail", uid)
    except google_auth.StateError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"authorization_url": result["authorization_url"], "state": result["state"]}


@app.get("/api/auth/gmail/callback")
def gmail_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    """Legacy Gmail callback — delegates to generic handler."""
    return _handle_oauth_callback(code, state, error)


@app.get("/api/auth/callback")
def generic_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    """Generic OAuth callback for all services (calendar, drive, etc.)."""
    return _handle_oauth_callback(code, state, error)


@app.get("/api/auth/gmail/status")
def gmail_status(request: Request) -> dict[str, Any]:
    """Return the authenticated user's Gmail connection status (no tokens)."""
    uid = _require_uid(request)
    return connections_store.get_public_connection(uid, connections_store.SERVICE_GMAIL)


@app.post("/api/auth/gmail/disconnect")
def gmail_disconnect(request: Request) -> dict[str, Any]:
    """Revoke stored Gmail credentials and delete the connection record.

    The response never includes tokens, client secrets, or authorization codes.
    """
    uid = _require_uid(request)
    existing = connections_store.get_connection(uid, connections_store.SERVICE_GMAIL)
    if existing is None:
        return {"disconnected": True, "service": "gmail", "was_connected": False}

    # Best-effort Google revocation. Failure is non-fatal.
    refresh_token = existing.get("refresh_token")
    access_token = existing.get("access_token")
    revoked = False
    if refresh_token:
        revoked = google_auth.revoke_token(refresh_token) or revoked
    if access_token and not revoked:
        google_auth.revoke_token(access_token)

    connections_store.delete_connection(uid, connections_store.SERVICE_GMAIL)
    return {"disconnected": True, "service": "gmail", "was_connected": True}


# ---------------------------------------------------------------------------
# Generic OAuth routes for any service (calendar, drive, etc.)
# ---------------------------------------------------------------------------


@app.get("/api/auth/{service}/connect")
def generic_connect_redirect(service: str, request: Request) -> RedirectResponse:
    uid = _require_uid(request)
    result = _oauth_build_url(service, uid)
    return RedirectResponse(result["authorization_url"], status_code=302)


@app.post("/api/auth/{service}/connect")
def generic_connect_json(service: str, request: Request) -> dict[str, Any]:
    uid = _require_uid(request)
    result = _oauth_build_url(service, uid)
    return {"authorization_url": result["authorization_url"], "state": result["state"]}


@app.get("/api/auth/{service}/status")
def generic_status(service: str, request: Request) -> dict[str, Any]:
    uid = _require_uid(request)
    return _oauth_status(uid, service)


@app.post("/api/auth/{service}/disconnect")
def generic_disconnect(service: str, request: Request) -> dict[str, Any]:
    uid = _require_uid(request)
    return _oauth_disconnect(uid, service)


@app.get("/api/services/status")
def all_services_status(request: Request) -> dict[str, Any]:
    """Return status for all OAuth services (gmail/calendar/drive) + maps."""
    uid = _require_uid(request)
    result: dict[str, Any] = {}
    for svc in OAUTH_SERVICES:
        result[svc] = connections_store.get_public_connection(uid, svc)
    # Maps is API-key based, not per-user OAuth.
    maps_key = (os.getenv("GOOGLE_MAPS_API_KEY") or "").strip()
    result[SERVICE_MAPS] = {"connected": False, "service": "maps", "enabled": bool(maps_key), "configured": bool(maps_key)}
    return result


# ---------------------------------------------------------------------------
# Gmail message fetching
# ---------------------------------------------------------------------------


@app.get("/api/gmail/recent")
def gmail_recent(
    request: Request,
    limit: int = Query(default=10, ge=1, le=50, description="Number of recent messages to fetch"),
) -> dict[str, Any]:
    """Fetch the most recent Gmail messages for the authenticated user.

    Returns structured metadata only (no full message bodies).
    Requires an active Gmail connection with valid OAuth credentials.
    """
    uid = _require_uid(request)

    # Verify Gmail is connected.
    status = connections_store.get_public_connection(uid, connections_store.SERVICE_GMAIL)
    if not status.get("connected"):
        raise HTTPException(
            status_code=400,
            detail="Gmail is not connected. Please connect your Gmail account first.",
        )

    try:
        messages = gmail_connector.fetch_recent_messages(uid, max_results=limit)
    except ConnectionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {
        "messages": messages,
        "count": len(messages),
        "limit": limit,
    }


# ---------------------------------------------------------------------------
# Gmail analysis — AI-powered workflow generation from emails
# ---------------------------------------------------------------------------


@app.post("/api/gmail/analyze", response_model=GmailAnalyzeResponse)
def analyze_gmail(request: Request, payload: GmailAnalyzeRequest | None = None) -> GmailAnalyzeResponse:
    """Analyze Gmail messages with Gemini and create LifeFlows.

    Requires:
    - Firebase authentication
    - Connected Gmail account

    Returns a summary of what was found and created.
    """
    uid = _require_uid(request)
    limit = (payload.limit if payload else 30)

    # 1. Verify Gmail is connected.
    status = connections_store.get_public_connection(uid, connections_store.SERVICE_GMAIL)
    if not status.get("connected"):
        raise HTTPException(
            status_code=400,
            detail="Gmail is not connected. Please connect your Gmail account first.",
        )

    # 2. Fetch recent Gmail messages (metadata only).
    try:
        messages = gmail_connector.fetch_recent_messages(uid, max_results=limit)
    except ConnectionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    emails_analyzed = len(messages)
    if emails_analyzed == 0:
        return GmailAnalyzeResponse(
            success=True,
            emailsAnalyzed=0,
            flowsCreated=0,
            flowsUpdated=0,
            flowsIgnored=0,
            message="No emails found to analyze.",
        )

    # 3. Send metadata to Gemini for analysis.
    try:
        analyzed_flows, low_conf_ignored = gemini_service.analyze_gmail_messages(messages)
    except gemini_service.GeminiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    # 4. Deduplicate and persist new flows.
    flows_created = 0
    flows_ignored = 0

    for flow_data in analyzed_flows:
        source_ids = flow_data.pop("_sourceMessageIds", [])
        category = flow_data.pop("_category", "other")

        # Skip if a flow with these source messages already exists.
        if workflow_store.has_existing_flow(uid, source_ids):
            flows_ignored += 1
            continue

        # Validate and persist.
        try:
            workflow = Workflow.model_validate(flow_data)
        except ValidationError:
            flows_ignored += 1
            continue

        workflow_store.save_workflow(uid or None, workflow.model_dump(), is_new=True)
        flows_created += 1

    if flows_created > 0:
        msg = f"Found {flows_created} important LifeFlow{'s' if flows_created != 1 else ''}"
    else:
        msg = "No important LifeFlows found in your recent emails."

    return GmailAnalyzeResponse(
        success=True,
        emailsAnalyzed=emails_analyzed,
        flowsCreated=flows_created,
        flowsUpdated=0,
        flowsIgnored=flows_ignored,
        lowConfidenceIgnored=low_conf_ignored,
        message=msg,
    )


# ---------------------------------------------------------------------------
# Calendar endpoints
# ---------------------------------------------------------------------------


@app.get("/api/calendar/events")
def calendar_events(
    request: Request,
    limit: int = Query(default=10, ge=1, le=50),
    days: int = Query(default=14, ge=1, le=60),
) -> dict[str, Any]:
    uid = _require_uid(request)
    status = connections_store.get_public_connection(uid, SERVICE_CALENDAR)
    if not status.get("connected"):
        raise HTTPException(status_code=400, detail="Calendar is not connected. Please connect your Calendar first.")
    try:
        events = calendar_connector.fetch_upcoming_events(uid, max_results=limit, days_ahead=days)
    except ConnectionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"events": events, "count": len(events), "limit": limit}


# ---------------------------------------------------------------------------
# Drive endpoints
# ---------------------------------------------------------------------------


@app.get("/api/drive/recent")
def drive_recent(
    request: Request,
    limit: int = Query(default=10, ge=1, le=50),
) -> dict[str, Any]:
    uid = _require_uid(request)
    status = connections_store.get_public_connection(uid, SERVICE_DRIVE)
    if not status.get("connected"):
        raise HTTPException(status_code=400, detail="Drive is not connected. Please connect your Drive first.")
    try:
        files = drive_connector.fetch_recent_files(uid, max_results=limit)
    except ConnectionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"files": files, "count": len(files), "limit": limit}


@app.get("/api/drive/files")
def drive_files_alias(request: Request, limit: int = Query(default=10, ge=1, le=50)) -> dict[str, Any]:
    return drive_recent(request, limit)


# ---------------------------------------------------------------------------
# Maps endpoints (API-key, no OAuth)
# ---------------------------------------------------------------------------


@app.get("/api/maps/status")
def maps_status(request: Request) -> dict[str, Any]:
    # Maps is server-key based — no per-user connection.
    # Still require auth to avoid anonymous abuse (unless demo mode).
    _require_uid(request)
    configured = maps_service.is_configured()
    return {"enabled": configured, "configured": configured, "service": "maps"}


@app.post("/api/maps/geocode")
def maps_geocode(request: Request, payload: MapsGeocodeRequest) -> dict[str, Any]:
    _require_uid(request)
    try:
        result = maps_service.geocode_address(payload.address)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        msg = str(exc)
        if "not configured" in msg.lower():
            raise HTTPException(status_code=503, detail=msg) from exc
        raise HTTPException(status_code=502, detail=msg) from exc
    return result


@app.post("/api/maps/directions")
def maps_directions(request: Request, payload: MapsDirectionsRequest) -> dict[str, Any]:
    _require_uid(request)
    try:
        result = maps_service.get_directions(payload.origin, payload.destination, mode=payload.mode)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        msg = str(exc)
        if "not configured" in msg.lower():
            raise HTTPException(status_code=503, detail=msg) from exc
        raise HTTPException(status_code=502, detail=msg) from exc
    return result


# ---------------------------------------------------------------------------
# Unified multi-service analysis
# ---------------------------------------------------------------------------


@app.post("/api/analyze", response_model=AnalyzeResponse)
def unified_analyze(request: Request, payload: AnalyzeRequest | None = None) -> AnalyzeResponse:
    """Analyze connected services and create LifeFlows.

    Deterministic service selection: only fetches services that are
    connected and not explicitly excluded via payload.services.
    Fetches max 10 per service, capped to avoid excessive API calls/tokens.
    """
    uid = _require_uid(request)
    payload = payload or AnalyzeRequest()

    diag = logging.getLogger("googleflow.analyze.diag")
    diag.info("=== ANALYZE PIPELINE START ===")
    diag.info("uid=%s", uid)

    # Determine which services to include (connected + not excluded)
    requested = set(payload.services) if payload.services else None
    def _should_include(svc: str) -> bool:
        if requested is not None and svc not in requested:
            return False
        status = connections_store.get_public_connection(uid, svc)
        return bool(status.get("connected"))

    include_gmail = _should_include(SERVICE_GMAIL)
    include_calendar = _should_include(SERVICE_CALENDAR)
    include_drive = _should_include(SERVICE_DRIVE)
    diag.info("include_gmail=%s include_calendar=%s include_drive=%s", include_gmail, include_calendar, include_drive)

    # If no service connected, return friendly message.
    if not include_gmail and not include_calendar and not include_drive:
        return AnalyzeResponse(
            success=True,
            flowsCreated=0,
            flowsIgnored=0,
            message="No connected services. Please connect Gmail, Calendar, or Drive first.",
        )

    gmail_messages: list[dict[str, Any]] = []
    calendar_events: list[dict[str, Any]] = []
    drive_files: list[dict[str, Any]] = []
    gmail_count = 0
    cal_count = 0
    drive_count = 0

    # Fetch each service — fail-open per service (one failure doesn't block others)
    if include_gmail:
        try:
            limit = payload.gmailLimit or 10
            gmail_messages = gmail_connector.fetch_recent_messages(uid, max_results=limit)
            gmail_count = len(gmail_messages)
            diag.info("Gmail fetched=%d messages", gmail_count)
        except Exception as exc:
            logger = logging.getLogger("googleflow.analyze")
            logger.warning("Unified analyze: gmail fetch failed: %s", exc)

    if include_calendar:
        try:
            limit = payload.calendarLimit or 10
            calendar_events = calendar_connector.fetch_upcoming_events(uid, max_results=limit)
            cal_count = len(calendar_events)
            diag.info("Calendar fetched=%d events", cal_count)
        except Exception as exc:
            logger = logging.getLogger("googleflow.analyze")
            logger.warning("Unified analyze: calendar fetch failed: %s", exc)

    if include_drive:
        try:
            limit = payload.driveLimit or 10
            drive_files = drive_connector.fetch_recent_files(uid, max_results=limit)
            drive_count = len(drive_files)
            diag.info("Drive fetched=%d files", drive_count)
        except Exception as exc:
            logger = logging.getLogger("googleflow.analyze")
            logger.warning("Unified analyze: drive fetch failed: %s", exc)

    # Maps context — only if query/location hint provided and Maps configured
    maps_context: dict[str, Any] | None = None
    maps_used = False
    if maps_service.is_configured():
        origin = (payload.origin or "").strip() if payload.origin else ""
        destination = (payload.destination or "").strip() if payload.destination else ""
        q = (payload.query or "").strip() if payload.query else ""
        # Build maps_context deterministically without extra LLM call
        if origin and destination:
            try:
                directions = maps_service.get_directions(origin, destination)
                maps_context = {"directions": directions}
                maps_used = True
            except Exception:
                pass
        elif q and any(k in q.lower() for k in ("trip", "travel", "location", "where", "direction", "reach", "go to")):
            # Extract a location hint from query for geocoding (reuse gemini location hint)
            # Simple: if query contains "in <Place>" we geocode that place.
            try:
                import re
                m = re.search(r"\bin\s+([A-Za-z]+(?:\s+[A-Za-z]+)*)", q)
                if m:
                    loc = m.group(1).strip()
                    if len(loc) >= 3:
                        geocode = maps_service.geocode_address(loc)
                        maps_context = {"geocode": geocode, "query": q}
                        maps_used = True
            except Exception:
                pass

    if gmail_count == 0 and cal_count == 0 and drive_count == 0 and not maps_used:
        diag.info("No data fetched from any service - returning early")
        return AnalyzeResponse(
            success=True,
            flowsCreated=0,
            flowsIgnored=0,
            message="No data found in connected services to analyze.",
            gmailAnalyzed=gmail_count,
            calendarAnalyzed=cal_count,
            driveAnalyzed=drive_count,
            mapsUsed=maps_used,
            emailsAnalyzed=gmail_count,
        )

    diag.info("Calling Gemini with gmail=%d calendar=%d drive=%d", gmail_count, cal_count, drive_count)
    try:
        analyzed, low_conf_ignored = gemini_service.analyze_multi_service(
            gmail_messages=gmail_messages,
            calendar_events=calendar_events,
            drive_files=drive_files,
            maps_context=maps_context,
            query_hint=payload.query,
        )
    except gemini_service.GeminiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        import traceback
        diag.error("Unexpected error in analyze: %s", "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
        raise HTTPException(status_code=502, detail=f"Analysis failed: {exc}") from exc

    diag.info("Gemini returned flows=%d low_conf_ignored=%d", len(analyzed), low_conf_ignored)
    flows_created = 0
    flows_ignored = 0
    flows_ignored_title_dup = 0
    flows_ignored_existing = 0
    flows_ignored_validation = 0
    seen_titles: set[str] = set()
    for flow_data in analyzed:
        source_msg_ids = flow_data.pop("_sourceMessageIds", [])
        source_event_ids = flow_data.pop("_sourceEventIds", [])
        source_file_ids = flow_data.pop("_sourceFileIds", [])
        all_ids = list(source_msg_ids) + list(source_event_ids) + list(source_file_ids)
        flow_data.pop("_category", None)

        title_key = (flow_data.get("title") or "").lower().strip()
        if title_key and title_key in seen_titles:
            flows_ignored += 1
            flows_ignored_title_dup += 1
            diag.info("Rejected: duplicate title '%s'", title_key)
            continue
        if title_key:
            seen_titles.add(title_key)

        check_ids = all_ids
        if check_ids and workflow_store.has_existing_flow_multi(uid, check_ids):
            flows_ignored += 1
            flows_ignored_existing += 1
            diag.info("Rejected: existing flow for ids=%s", check_ids[:3])
            continue

        try:
            workflow = Workflow.model_validate(flow_data)
        except ValidationError:
            flows_ignored += 1
            flows_ignored_validation += 1
            diag.info("Rejected: validation error for title='%s'", flow_data.get("title"))
            continue

        to_store = workflow.model_dump()
        if source_msg_ids:
            to_store["_sourceMessageIds"] = source_msg_ids
        if source_event_ids:
            to_store["_sourceEventIds"] = source_event_ids
        if source_file_ids:
            to_store["_sourceFileIds"] = source_file_ids
        if all_ids:
            to_store["_allSourceIds"] = all_ids
        workflow_store.save_workflow(uid or None, to_store, is_new=True)
        flows_created += 1

    diag.info("Final: created=%d ignored_total=%d (title_dup=%d existing=%d validation=%d)",
              flows_created, flows_ignored, flows_ignored_title_dup, flows_ignored_existing, flows_ignored_validation)

    if flows_created > 0:
        msg = f"Found {flows_created} important LifeFlow{'s' if flows_created != 1 else ''} from your connected services"
    else:
        msg = "No important LifeFlows found in your connected services."

    return AnalyzeResponse(
        success=True,
        flowsCreated=flows_created,
        flowsIgnored=flows_ignored,
        lowConfidenceIgnored=low_conf_ignored,
        message=msg,
        gmailAnalyzed=gmail_count,
        calendarAnalyzed=cal_count,
        driveAnalyzed=drive_count,
        mapsUsed=maps_used,
        emailsAnalyzed=gmail_count,
    )


# ---------------------------------------------------------------------------
# Production: Serve React frontend
# ---------------------------------------------------------------------------




@app.get("/")
async def serve_frontend() -> FileResponse:
    index_path = Path(FRONTEND_DIST) / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    raise HTTPException(status_code=503, detail="Frontend not built. Run `npm run build` first.")


@app.get("/{path:path}")
async def serve_spa(path: str) -> FileResponse:
    """Serve React SPA for any non-API route (supports React Router)."""
    if path.startswith("api/"):
        raise HTTPException(status_code=404, detail="API endpoint not found")
    index_path = Path(FRONTEND_DIST) / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    raise HTTPException(status_code=503, detail="Frontend not built. Run `npm run build` first.")
