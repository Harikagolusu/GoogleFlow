"""Gemini integration for GoogleFlow.

Security:
    The Gemini API key lives ONLY in the backend environment
    (backend/.env or the process environment). It is never shipped to,
    bundled with, or read from the frontend.

Behavior:
    - When GEMINI_API_KEY is configured, Gemini is called and must return a
      JSON object matching the frontend Workflow interface
      (src/types/workflow.ts). Output is parsed defensively and cleaned.
    - When GEMINI_API_KEY is missing, a small deterministic fallback
      generator kicks in so the full Ask -> LifeFlow -> Details flow can be
      demoed end-to-end before a real key is provisioned.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gemini-3.6-flash"

# Confidence thresholds for flow filtering — all configurable via env vars.
# CONFIDENCE_THRESHOLD_IGNORE : flows below this are discarded.
# CONFIDENCE_THRESHOLD_MEDIUM  : flows below this are created only if actionable.
# CONFIDENCE_THRESHOLD_HIGH    : flows at or above this are created normally.
import os as _os

def _read_float(env_key: str, default: float) -> float:
    try:
        return float(_os.getenv(env_key, "").strip())
    except (ValueError, TypeError):
        return default

CONFIDENCE_THRESHOLD_HIGH = _read_float("LIFEFLOW_CONFIDENCE_HIGH", 0.75)
CONFIDENCE_THRESHOLD_MEDIUM = _read_float("LIFEFLOW_CONFIDENCE_MEDIUM", 0.60)
CONFIDENCE_THRESHOLD_IGNORE = _read_float("LIFEFLOW_CONFIDENCE_IGNORE", 0.50)

# Ensure invariant: IGNORE <= MEDIUM <= HIGH <= 1.0
CONFIDENCE_THRESHOLD_HIGH = min(1.0, max(CONFIDENCE_THRESHOLD_HIGH, 0.0))
CONFIDENCE_THRESHOLD_MEDIUM = min(CONFIDENCE_THRESHOLD_HIGH, max(CONFIDENCE_THRESHOLD_MEDIUM, 0.0))
CONFIDENCE_THRESHOLD_IGNORE = min(CONFIDENCE_THRESHOLD_MEDIUM, max(CONFIDENCE_THRESHOLD_IGNORE, 0.0))

# Canonical service names the frontend knows how to display.
KNOWN_SERVICES = [
    "Gmail",
    "Google Drive",
    "Google Calendar",
    "Google Maps",
    "YouTube",
    "Google Search",
    "Gemini",
]

_SERVICE_ALIASES = {
    "gmail": "Gmail",
    "mail": "Gmail",
    "drive": "Google Drive",
    "google drive": "Google Drive",
    "gdrive": "Google Drive",
    "calendar": "Google Calendar",
    "google calendar": "Google Calendar",
    "maps": "Google Maps",
    "google maps": "Google Maps",
    "youtube": "YouTube",
    "search": "Google Search",
    "google search": "Google Search",
    "gemini": "Gemini",
    "google ai": "Gemini",
}


class GeminiError(Exception):
    """Raised when Gemini cannot produce a valid LifeFlow."""


# ---------------------------------------------------------------------------
# Public entry point used by the API layer
# ---------------------------------------------------------------------------


def generate_workflow_dict(query: str, workflow_id: str) -> dict[str, Any]:
    """Return a cleaned, Workflow-shaped dict for a described situation.

    Uses the real Gemini API when a key is configured, otherwise falls back
    to a deterministic local generator so the demo flow keeps working.
    Any exception from generation is converted to GeminiError so the API
    layer can return a clean 502 instead of crashing.
    """
    try:
        client = _get_client()
        if client is None:
            return _clean_workflow_dict(_generate_fallback(query), workflow_id)

        text = _call_gemini(client, query)
        raw = _extract_json(text)
        return _clean_workflow_dict(raw, workflow_id)
    except GeminiError:
        raise
    except Exception as exc:
        raise GeminiError(f"LifeFlow generation failed: {exc}") from exc


def generate_workflow_dict_from_context(
    query: str,
    workflow_id: str,
    gmail_messages: list[dict[str, Any]] | None = None,
    calendar_events: list[dict[str, Any]] | None = None,
    drive_files: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Generate a LifeFlow using real data from Gmail, Calendar, and Drive.

    Builds a rich context prompt from the fetched data and passes it to Gemini.
    """
    gmail_messages = gmail_messages or []
    calendar_events = calendar_events or []
    drive_files = drive_files or []

    context_parts = [f"User query: {query}\n"]

    if gmail_messages:
        context_parts.append("\n=== GMAIL MESSAGES ===\n")
        for m in gmail_messages:
            context_parts.append(
                f"- From: {m.get('sender', 'Unknown')}\n"
                f"  Subject: {m.get('subject', 'No subject')}\n"
                f"  Snippet: {m.get('snippet', '')[:200]}\n"
            )

    if calendar_events:
        context_parts.append("\n=== CALENDAR EVENTS ===\n")
        for e in calendar_events:
            context_parts.append(
                f"- {e.get('summary', 'No title')}\n"
                f"  Start: {e.get('displayStart', e.get('start', 'Unknown'))}\n"
                f"  Location: {e.get('location', 'No location')}\n"
            )

    if drive_files:
        context_parts.append("\n=== DRIVE FILES ===\n")
        for f in drive_files:
            context_parts.append(
                f"- {f.get('name', 'Untitled')}\n"
                f"  Type: {f.get('mimeType', 'Unknown')}\n"
            )

    context = "".join(context_parts)

    try:
        client = _get_client()
        if client is None:
            return _clean_workflow_dict(_generate_fallback(query), workflow_id)

        prompt = _build_context_prompt(query, context)
        text = _call_gemini(client, prompt)
        raw = _extract_json(text)
        return _clean_workflow_dict(raw, workflow_id)
    except GeminiError:
        raise
    except Exception as exc:
        raise GeminiError(f"LifeFlow generation failed: {exc}") from exc


def _build_context_prompt(query: str, context: str) -> str:
    """Build a Gemini prompt from the query and fetched data context."""
    return (
        f"You are an AI assistant that creates LifeFlows from real user data.\n\n"
        f"{context}\n\n"
        f"Based on the data above, create a LifeFlow that helps the user accomplish: {query}\n\n"
        f"Respond with ONLY a valid JSON object with these fields:\n"
        f"- title: short descriptive title\n"
        f"- emoji: single emoji\n"
        f"- date: human-readable date/time\n"
        f"- status: 'Action Needed' | 'In Progress' | 'Completed'\n"
        f"- readiness: integer 0-100\n"
        f"- nextUp: next action item\n"
        f"- checklist: array of {{id, title, completed}} items\n"
        f"- connectedServices: array of service names\n"
        f"- priority: 'high' | 'medium' | 'low'\n"
        f"Only create the LifeFlow if the data is relevant. If no useful LifeFlow can be created from this data, return a generic helpful response."
    )


# ---------------------------------------------------------------------------
# Gemini API interaction
# ---------------------------------------------------------------------------


def _get_client() -> Any:
    """Return a genai.Client, or None when the demo fallback should be used."""
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key or api_key == "your_gemini_api_key_here":
        return None
    try:
        from google import genai  # installed via pip (google-genai)
        return genai.Client(api_key=api_key)
    except Exception as exc:
        raise GeminiError(f"Gemini SDK failed to initialize: {exc}") from exc


def _call_gemini(client: Any, query: str) -> str:
    """Call Gemini and return the raw text response."""
    return _call_gemini_with_fallback(client, _build_prompt(query),
        response_mime_type="application/json",
        temperature=0.7,
        max_output_tokens=2048,
    )


def _extract_response_text(response: Any) -> str:
    """Extract text from a Gemini response, handling SDK quirks."""
    # Try the standard .text property first.
    text = (getattr(response, "text", None) or "").strip()
    if text:
        return text
    # Fall back to candidates[0].content.parts[0].text
    candidates = getattr(response, "candidates", None) or []
    for candidate in candidates:
        content = getattr(candidate, "content", None)
        if content:
            parts = getattr(content, "parts", None) or []
            for part in parts:
                part_text = getattr(part, "text", None)
                if part_text:
                    return part_text.strip()
    return ""


def _call_gemini_with_fallback(
    client: Any, prompt: str, *,
    response_mime_type: str = "text/plain",
    temperature: float = 0.7,
    max_output_tokens: int = 2048,
) -> str:
    """Call Gemini with automatic model fallback on 404/deprecation errors."""
    from google.genai import types
    import google.genai.errors as genai_errors

    configured_model = os.getenv("GEMINI_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
    # Fallback models when the configured one is deprecated.
    models_to_try = [configured_model, "gemini-2.5-flash", "gemini-3.6-flash"]
    # Deduplicate while preserving order.
    seen: set[str] = set()
    unique_models: list[str] = []
    for m in models_to_try:
        if m not in seen:
            seen.add(m)
            unique_models.append(m)

    last_error: Exception | None = None
    for model in unique_models:
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type=response_mime_type,
                    temperature=temperature,
                    max_output_tokens=max_output_tokens,
                ),
            )
            text = _extract_response_text(response)
            if not text:
                raise GeminiError("Gemini returned an empty response.")
            if model != configured_model:
                logger.warning("Gemini: fell back from %s to %s", configured_model, model)
            return text
        except GeminiError:
            raise
        except genai_errors.ClientError as exc:
            last_error = exc
            if "404" in str(exc) or "not found" in str(exc).lower() or "no longer available" in str(exc).lower():
                logger.warning("Gemini model %s unavailable, trying next: %s", model, exc)
                continue
            raise GeminiError(f"Gemini request failed: {exc}") from exc
        except Exception as exc:
            raise GeminiError(f"Gemini request failed: {exc}") from exc

    raise GeminiError(f"All Gemini models failed. Last error: {last_error}")


def _build_prompt(query: str) -> str:
    return f"""You are LifeFlow, the assistant inside GoogleFlow. You turn a user's
described real-life situation into a structured "LifeFlow" action plan.

Return ONLY a single JSON object with EXACTLY these fields (no markdown, no
commentary):

- "title": short, specific plan title (5 words or fewer)
- "emoji": one relevant emoji for the plan
- "date": short human-readable date derived ONLY from the user's words
  (e.g. "Tomorrow · 10:30 AM", "Today", "This week"). If no date is given
  use "No fixed date — to be confirmed".
- "location": the location if the user mentioned one, otherwise omit the field
- "status": one of "Action Needed", "In Progress", "Completed"
- "readiness": integer 0-100. How prepared the user already seems. A brand-new
  plan should start around 10-30.
- "nextUp": the single most important next action (a short string)
- "checklist": an array of 4 to 8 practical steps. Each item is an object:
  {{"id": "c1", "title": "step description", "completed": false}}
  Use sequential ids c1, c2, ... For a new plan most items are completed:false;
  you may mark a few clearly-already-done steps completed:true.
- "connectedServices": array of relevant Google services chosen ONLY from:
  Gmail, Google Drive, Google Calendar, Google Maps, YouTube, Google Search,
  Gemini. Pick 3-6 that actually help this plan.

Rules:
- Be practical and useful even if the user gave incomplete information. For
  missing details, create reasonable next steps such as "Confirm appointment
  details", "Verify required documents", "Check location", "Plan travel".
- Do NOT invent critical facts like exact bookings, confirmation numbers, or
  dates the user did not provide. Mark unclear details as steps to verify.
- "connectedServices" means services relevant to this workflow — NOT a claim
  that any real Google account access has happened.
- CHECKLIST items must be SPECIFIC and ACTIONABLE. Never use generic items like:
  "Complete the task", "Prepare everything", "Follow the process", "Finish your
  work", "Get ready", "Do what's needed". Instead, describe a concrete action.
- If the user mentions TIME (tomorrow, next week, Friday, in 3 days), prioritize
  the most urgent preparation tasks first in the checklist.
- "nextUp" must be the single most useful IMMEDIATE action — concrete and
  specific, not a generic summary. Bad: "Prepare for interview". Good: "Review
  the job description and identify the top 3 skills to prepare".

Here is an example of the expected shape (values are illustrative):

{{
  "title": "Passport Appointment",
  "emoji": "🛂",
  "date": "Tomorrow · 10:30 AM",
  "location": "Hyderabad",
  "status": "Action Needed",
  "readiness": 14,
  "nextUp": "Confirm appointment details",
  "checklist": [
    {{"id": "c1", "title": "Confirm appointment details", "completed": false}},
    {{"id": "c2", "title": "Keep Aadhaar card ready", "completed": false}},
    {{"id": "c3", "title": "Keep PAN card ready", "completed": false}},
    {{"id": "c4", "title": "Find passport copies", "completed": false}},
    {{"id": "c5", "title": "Check location and directions", "completed": false}},
    {{"id": "c6", "title": "Plan travel to the appointment", "completed": false}}
  ],
  "connectedServices": ["Gmail", "Google Calendar", "Google Drive", "Google Maps", "Gemini"]
}}

User's situation:
{query}"""
# ---------------------------------------------------------------------------
# Defensive JSON parsing + validation of the Gemini output
# ---------------------------------------------------------------------------


def _extract_json(text: str) -> Any:
    """Parse model output as JSON, tolerating markdown code fences."""
    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = re.sub(r"^```(?:json)?\s*", "", candidate, flags=re.IGNORECASE)
        candidate = re.sub(r"\s*```$", "", candidate)
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(candidate[start : end + 1])
            except json.JSONDecodeError:
                pass
        raise GeminiError("Gemini returned invalid JSON.")


def _clean_priority(value: Any) -> str:
    """Return a valid priority string or 'medium' as safe default."""
    raw = str(value or "").strip().lower()
    if raw in ("high", "medium", "low"):
        return raw
    return "medium"


def _clean_confidence(value: Any) -> float | None:
    """Return a confidence value clamped to [0.0, 1.0] or None."""
    if value is None:
        return None
    try:
        conf = float(value)
        return max(0.0, min(1.0, conf))
    except (TypeError, ValueError):
        return None


def _clean_workflow_dict(data: Any, workflow_id: str) -> dict[str, Any]:
    """Normalize whatever Gemini (or the fallback) produced into the exact
    shape of the frontend Workflow interface."""
    if not isinstance(data, dict):
        raise GeminiError("Gemini response was not a JSON object.")

    checklist = _clean_checklist(data.get("checklist"))
    if not checklist:
        raise GeminiError("Gemini returned a LifeFlow without checklist items.")

    done = sum(1 for item in checklist if item["completed"])
    total = len(checklist)
    derived_readiness = round(done / total * 100) if total else 0

    try:
        readiness = int(data.get("readiness", derived_readiness))
    except (TypeError, ValueError):
        readiness = derived_readiness
    readiness = max(0, min(100, readiness))

    status_raw = str(data.get("status") or "").strip().lower()
    if "completed" in status_raw:
        status = "Completed"
    elif "in progress" in status_raw:
        status = "In Progress"
    elif "action" in status_raw:
        status = "Action Needed"
    elif readiness >= 100:
        status = "Completed"
    elif readiness == 0:
        status = "Action Needed"
    else:
        status = "In Progress"

    title = str(data.get("title") or "").strip() or "LifeFlow Plan"
    emoji = str(data.get("emoji") or "").strip() or "✨"
    date = str(data.get("date") or "").strip() or "No fixed date — to be confirmed"

    location = data.get("location")
    location = str(location).strip() if location else None

    next_item = next((item["title"] for item in checklist if not item["completed"]), None)
    next_up = str(data.get("nextUp") or "").strip() or next_item or "Review your plan"

    services = _clean_services(data.get("connectedServices"))

    priority = _clean_priority(data.get("priority"))
    confidence = _clean_confidence(data.get("confidence"))

    return {
        "id": workflow_id,
        "title": title,
        "emoji": emoji,
        "date": date,
        "location": location,
        "status": status,
        "readiness": readiness,
        "nextUp": next_up,
        "checklist": checklist,
        "connectedServices": services,
        "priority": priority,
        "confidence": confidence,
    }


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _clean_checklist(data: Any) -> list[dict[str, Any]]:
    if not isinstance(data, list):
        return []
    result: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, item in enumerate(data, start=1):
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        item_id = str(item.get("id") or f"c{index}").strip() or f"c{index}"
        if item_id in seen_ids:
            item_id = f"c{index}"
        seen_ids.add(item_id)
        result.append(
            {
                "id": item_id,
                "title": title[:140],
                "completed": _as_bool(item.get("completed", False)),
            }
        )
    return result


def _clean_services(data: Any) -> list[str]:
    if not isinstance(data, list):
        return ["Gmail", "Gemini"]
    services: list[str] = []
    for raw in data:
        name = _SERVICE_ALIASES.get(str(raw or "").strip().lower())
        if name and name not in services:
            services.append(name)
    return services[:8] or ["Gmail", "Gemini"]
# ---------------------------------------------------------------------------
# Deterministic fallback generator (demo mode without a Gemini API key)
# ---------------------------------------------------------------------------


_TIME_RE = re.compile(r"\b(\d{1,2}(?::\d{2})?\s?(?:am|pm))\b", re.IGNORECASE)
_DAYS_RE = re.compile(r"\bin\s+(\d+)\s+days?\b", re.IGNORECASE)
_STOPWORDS = {"in", "and", "need", "my", "the", "of", "at", "on", "for", "to"}


def _generate_fallback(query: str) -> dict[str, Any]:
    q = query.lower()
    if any(k in q for k in ("passport", "visa", "aadhaar", "pan card")):
        return _fallback_passport(query)
    if any(k in q for k in ("interview", "job talk", "hiring round")):
        return _fallback_interview(query)
    if any(k in q for k in ("trip", "travel", "flight", "hotel", "vacation", "tour")):
        return _fallback_trip(query)
    if any(k in q for k in ("exam", "test", "certification", "study", "course")):
        return _fallback_exam(query)
    return _fallback_generic(query)


def _hint_date(query: str) -> str:
    q = query.lower()
    time_match = _TIME_RE.search(query)
    time_part = f" · {time_match.group(1)}" if time_match else ""
    if "tomorrow" in q:
        return f"Tomorrow{time_part}"
    if "today" in q:
        return f"Today{time_part}"
    if "next week" in q:
        return "Next week"
    if "next month" in q:
        return "Next month"
    days_match = _DAYS_RE.search(query)
    if days_match:
        return f"In {days_match.group(1)} days"
    return "No fixed date — to be confirmed"


def _hint_location(query: str) -> str | None:
    for match in re.finditer(r"\bin\s+([A-Za-z]+(?:\s+[A-Za-z]+)*)", query):
        words = match.group(1).split()
        if not words:
            continue
        candidate: list[str] = []
        for word in words:
            if word[0].isupper() and len(word) >= 3 and word.lower() not in _STOPWORDS:
                candidate.append(word)
            else:
                break
        if candidate:
            return " ".join(candidate)
    return None


def _fallback_passport(query: str) -> dict[str, Any]:
    return {
        "title": "Passport Appointment",
        "emoji": "🛂",
        "date": _hint_date(query),
        "location": _hint_location(query),
        "status": "Action Needed",
        "readiness": 10,
        "nextUp": "Confirm appointment details",
        "checklist": [
            {"id": "c1", "title": "Confirm appointment details", "completed": False},
            {"id": "c2", "title": "Keep Aadhaar card ready", "completed": False},
            {"id": "c3", "title": "Keep PAN card ready", "completed": False},
            {"id": "c4", "title": "Find passport copies", "completed": False},
            {"id": "c5", "title": "Check location and directions", "completed": False},
            {"id": "c6", "title": "Plan travel to the appointment", "completed": False},
        ],
        "connectedServices": [
            "Gmail", "Google Calendar", "Google Drive", "Google Maps", "Gemini",
        ],
    }
def _fallback_interview(query: str) -> dict[str, Any]:
    location = _hint_location(query)
    if not location and any(k in query.lower() for k in ("online", "virtual", "zoom")):
        location = "Online"
    # Time-aware prioritization: if urgent, put most critical prep first
    urgent = any(k in query.lower() for k in ("tomorrow", "today", "tonight", "in 1 day", "in one day"))
    if urgent:
        checklist = [
            {"id": "c1", "title": "Review the job description and highlight required skills", "completed": False},
            {"id": "c2", "title": "Research the company's products and recent news", "completed": False},
            {"id": "c3", "title": "Prepare answers for likely technical questions", "completed": False},
            {"id": "c4", "title": "Practice explaining your past projects concisely", "completed": False},
            {"id": "c5", "title": "Update and review your resume", "completed": False},
            {"id": "c6", "title": "Prepare 3-5 questions to ask the interviewer", "completed": False},
        ]
    else:
        checklist = [
            {"id": "c1", "title": "Review the job description and identify key skills to prepare", "completed": False},
            {"id": "c2", "title": "Research the company's products, culture, and recent work", "completed": False},
            {"id": "c3", "title": "Prepare answers for likely technical or role-specific questions", "completed": False},
            {"id": "c4", "title": "Practice explaining your previous projects and experience aloud", "completed": False},
            {"id": "c5", "title": "Update and review your resume for relevance", "completed": False},
            {"id": "c6", "title": "Prepare 3-5 thoughtful questions to ask the interviewer", "completed": False},
        ]
    return {
        "title": "Interview Preparation",
        "emoji": "💼",
        "date": _hint_date(query),
        "location": location,
        "status": "Action Needed",
        "readiness": 15,
        "nextUp": checklist[0]["title"],
        "checklist": checklist,
        "connectedServices": [
            "Gmail", "Google Calendar", "Google Drive", "YouTube", "Google Search", "Gemini",
        ],
    }


def _fallback_trip(query: str) -> dict[str, Any]:
    return {
        "title": "Trip Planning",
        "emoji": "✈️",
        "date": _hint_date(query),
        "location": _hint_location(query),
        "status": "Action Needed",
        "readiness": 15,
        "nextUp": "Confirm travel dates and book flights if not done",
        "checklist": [
            {"id": "c1", "title": "Confirm travel dates and book flights if not done", "completed": False},
            {"id": "c2", "title": "Review hotel and transport reservations", "completed": False},
            {"id": "c3", "title": "Check passport, visa, and required travel documents", "completed": False},
            {"id": "c4", "title": "Plan itinerary and bookmark places to visit", "completed": False},
            {"id": "c5", "title": "Pack essentials based on weather and activities", "completed": False},
            {"id": "c6", "title": "Save maps, directions, and key addresses offline", "completed": False},
        ],
        "connectedServices": [
            "Gmail", "Google Calendar", "Google Maps", "Google Drive", "Gemini",
        ],
    }


def _fallback_exam(query: str) -> dict[str, Any]:
    return {
        "title": "Exam Preparation",
        "emoji": "🎓",
        "date": _hint_date(query),
        "location": _hint_location(query),
        "status": "Action Needed",
        "readiness": 10,
        "nextUp": "Review the syllabus and create a study schedule",
        "checklist": [
            {"id": "c1", "title": "Review the syllabus and create a study schedule", "completed": False},
            {"id": "c2", "title": "Collect study materials, notes, and reference books", "completed": False},
            {"id": "c3", "title": "Identify key topics and areas of weakness", "completed": False},
            {"id": "c4", "title": "Practice with past papers or mock tests", "completed": False},
            {"id": "c5", "title": "Confirm exam date, time, and venue", "completed": False},
            {"id": "c6", "title": "Keep admit card, ID, and stationery ready", "completed": False},
        ],
        "connectedServices": [
            "Gmail", "Google Calendar", "Google Drive", "YouTube", "Google Search", "Gemini",
        ],
    }


def _fallback_generic(query: str) -> dict[str, Any]:
    return {
        "title": "Personal Goal Plan",
        "emoji": "✨",
        "date": _hint_date(query),
        "location": _hint_location(query),
        "status": "Action Needed",
        "readiness": 10,
        "nextUp": "Clarify the goal and identify the first concrete step",
        "checklist": [
            {"id": "c1", "title": "Clarify the goal and desired outcome", "completed": False},
            {"id": "c2", "title": "List what resources and knowledge you already have", "completed": False},
            {"id": "c3", "title": "Identify gaps and what you need to learn or gather", "completed": False},
            {"id": "c4", "title": "Break the goal into smaller actionable steps", "completed": False},
            {"id": "c5", "title": "Schedule dedicated time to work on it", "completed": False},
        ],
        "connectedServices": ["Gmail", "Google Calendar", "Google Drive", "Gemini"],
    }


# ---------------------------------------------------------------------------
# Gmail analysis — identify actionable situations from email metadata
# ---------------------------------------------------------------------------

class AnalyzeError(Exception):
    """Raised when Gemini cannot produce a valid analysis."""


def analyze_gmail_messages(messages: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """Analyze Gmail message metadata and return actionable LifeFlow dicts.

    Returns (flows, lowConfidenceIgnored_count).
    Never returns tokens, secrets, or raw email content to the caller.
    """
    if not messages:
        return [], 0

    client = _get_client()
    if client is None:
        return [], 0

    try:
        text = _call_gemini_analyze(client, messages)
        raw = _extract_json(text)
        return _parse_analyze_output(raw)
    except GeminiError:
        raise
    except Exception as exc:
        raise GeminiError(f"Gmail analysis failed: {exc}") from exc


def _call_gemini_analyze(client: Any, messages: list[dict[str, Any]]) -> str:
    """Call Gemini with Gmail metadata to identify actionable situations."""
    prompt = _build_analyze_prompt(messages)
    return _call_gemini_with_fallback(client, prompt,
        response_mime_type="application/json",
        temperature=0.3,
        max_output_tokens=4096,
    )


def _build_analyze_prompt(messages: list[dict[str, Any]]) -> str:
    """Build the analysis prompt from Gmail message metadata.

    PRIVACY: Only sender, subject, date, and snippet are sent to Gemini.
    No email bodies, no tokens, no private content.
    """
    email_summaries = []
    for msg in messages:
        email_summaries.append(
            f"- From: {msg.get('sender', 'Unknown')}\n"
            f"  Subject: {msg.get('subject', '(no subject)')}\n"
            f"  Date: {msg.get('date', 'Unknown')}\n"
            f"  Snippet: {msg.get('snippet', '')}\n"
            f"  MessageID: {msg.get('id', '')}\n"
            f"  ThreadID: {msg.get('threadId', '')}\n"
            f"  Labels: {', '.join(msg.get('labels', []))}"
        )

    email_block = "\n".join(email_summaries)

    return f"""You are LifeFlow, an AI assistant inside GoogleFlow that analyzes Gmail
email metadata to identify genuinely important, actionable situations.

Analyze the following Gmail message metadata and identify LifeFlows — structured
action plans for real commitments the user needs to act on.

===========================
CATEGORIES (use the "category" field):
===========================
- deadline       : Clear submission/expiry/payment deadline with date
- appointment    : Scheduled meeting, call, interview, examination
- interview      : Job or academic interview (technical, HR, video, in-person)
- travel         : Flight, train, hotel, trip, travel booking
- payment        : Bill, invoice, refund, subscription, financial action
- application    : Job application, course registration, visa, permit, certification
- education      : Exam, course deadline, class schedule, certification renewal
- certification  : Credential expiry, professional certification renewal
- document       : Document request, contract, agreement requiring action
- task           : Clear action item not fitting other categories
- reminder       : Non-urgent follow-up or informational reminder
- other          : Anything not fitting above

===========================
PRIORITY RULES (set the "priority" field):
===========================
- HIGH   : Deadline within 3 days | Interview/appointment within 48h | Travel within 7 days
           | Urgent payment or refund | Expiring document/certification
           | Explicit urgent language ("asap", "immediately", "urgent", "today")
- MEDIUM : Deadline within 14 days | Important but not yet urgent | Application follow-up
           | Document review needed | Upcoming event 1-2 weeks away
- LOW    : Useful informational flows | No real deadline | Non-urgent follow-ups
           | Generic reminders

===========================
CONFIDENCE SCORING (set the "confidence" field as 0.0-1.0):
===========================
- 0.95+ : Clear evidence — exact date, exact event name, sender is authoritative
- 0.85+ : Strong evidence — likely real event, reasonable date inference
- 0.75+ : Good evidence — meaningful action, some uncertainty on details
- 0.60+ : Moderate — possible real action, but ambiguous or incomplete info
          ONLY create if the checklist items are genuinely useful.
- Below 0.60: DO NOT CREATE a flow. Ignore it.

===========================
STRICT FILTERING — IGNORE THESE COMPLETELY:
===========================
- Spam, promotional, marketing, and deal emails
- Newsletters from companies the user subscribed to (unless a real deadline)
- Social media notifications (LinkedIn, Twitter, Facebook, Instagram)
- Generic product announcements, feature updates, release notes
- Automated system emails: password resets, security alerts, OTPs, 2FA codes
  UNLESS they indicate a real account problem requiring user action
- Generic receipts/invoices with NO required action, refund, or dispute
- Duplicate messages in the same thread (keep only one flow per thread)
- Messages with NO meaningful user action and no deadline
- Emails from unknown senders about vague "opportunities"
- Automated shipping/delivery notifications with everything in order
- Meeting invitations for events already reflected in Calendar
  (merge Gmail+Calendar duplicates — prefer Calendar as the source of truth)

===========================
CROSS-SERVICE REASONING:
===========================
- If an email references an interview/appointment and Calendar has the same event,
  create ONE unified flow combining both sources. Use Calendar's date/time.
  In the flow, note "Gmail + Calendar" in sourceMessageIds/sourceEventIds.
- If an email references a document and Drive has a relevant file
  (e.g., email about "resume" + Drive has "resume.pdf"), link them in the flow.
- If multiple emails refer to the same event/thread, create ONE flow only.
  Group them by threadId or normalized subject similarity.

===========================
STRICT RULES — NEVER DO THESE:
===========================
- NEVER invent a date, deadline, time, location, or event name
- NEVER assume an email from a known company is important
- NEVER present uncertain information as fact
- If a date is unclear, use "To be confirmed" for that field
- NEVER create a flow just because an email exists — only if action is needed
- NEVER send the user a generic checklist — steps must be specific to the situation
- If the email says "your application is being reviewed", do NOT invent a follow-up date
- If no clear action exists, return empty flows[]

===========================
OUTPUT FORMAT:
===========================
Return ONLY a JSON object with this exact structure:
{{
  "flows": [
    {{
      "title": "short specific title (5 words or fewer)",
      "emoji": "one relevant emoji",
      "date": "human-readable date from source, or 'To be confirmed'",
      "status": "Action Needed",
      "readiness": 10,
      "priority": "high|medium|low",
      "confidence": 0.0-1.0,
      "nextUp": "single most important immediate action",
      "checklist": [
        {{"id": "c1", "title": "specific actionable step", "completed": false}}
      ],
      "connectedServices": ["Gmail", "Google Calendar", "Google Drive", "Google Maps", "Gemini"],
      "sourceMessageIds": ["message id from the email"],
      "category": "deadline|appointment|interview|travel|payment|application|education|certification|document|task|reminder|other"
    }}
  ],
  "metadata": {{
    "flowsCreated": 0,
    "flowsIgnored": 0,
    "lowConfidenceIgnored": 0
  }}
}}

connectedServices must be chosen only from: Gmail, Google Drive, Google Calendar,
Google Maps, YouTube, Google Search, Gemini. Include only services that genuinely
contributed context.

Gmail messages to analyze:
{email_block}"""


def _parse_analyze_output(raw: Any) -> tuple[list[dict[str, Any]], int]:
    """Parse the Gemini analyze output into a list of cleaned Workflow dicts.

    Returns (flows, lowConfidenceIgnored_count).
    Flows below the confidence threshold are discarded and counted.
    """
    if not isinstance(raw, dict):
        raise GeminiError("Analysis response was not a JSON object.")

    flows = raw.get("flows")
    if not isinstance(flows, list):
        return [], 0

    metadata = raw.get("metadata") or {}
    if not isinstance(metadata, dict):
        metadata = {}

    result = []
    low_confidence_ignored = 0

    for flow_data in flows:
        try:
            if not isinstance(flow_data, dict):
                continue
            confidence = _clean_confidence(flow_data.get("confidence"))
            if confidence is not None and confidence < CONFIDENCE_THRESHOLD_IGNORE:
                low_confidence_ignored += 1
                continue
            if confidence is not None and confidence < CONFIDENCE_THRESHOLD_HIGH:
                checklist = flow_data.get("checklist", [])
                is_actionable = any(
                    len(str(item.get("title", "")).strip()) > 12
                    for item in checklist
                    if isinstance(item, dict)
                )
                if not is_actionable:
                    low_confidence_ignored += 1
                    continue

            cleaned = _clean_workflow_dict(flow_data, _generate_flow_id(flow_data))
            cleaned["_sourceMessageIds"] = flow_data.get("sourceMessageIds", [])
            cleaned["_category"] = flow_data.get("category", "other")
            result.append(cleaned)
        except GeminiError:
            continue

    metadata_low = metadata.get("lowConfidenceIgnored", 0)
    if isinstance(metadata_low, (int, float)):
        low_confidence_ignored += int(metadata_low)

    return result, low_confidence_ignored


def _generate_flow_id(flow_data: dict) -> str:
    """Generate a deterministic ID from source message IDs for deduplication."""
    source_ids = flow_data.get("sourceMessageIds", [])
    if source_ids:
        # Use the first message ID as a stable identifier.
        return f"gmail-{source_ids[0]}"
    import hashlib
    title = flow_data.get("title", "unknown")
    return f"gmail-{hashlib.md5(title.encode()).hexdigest()[:12]}"


# ---------------------------------------------------------------------------
# Unified multi-service analysis
# ---------------------------------------------------------------------------


def analyze_multi_service(
    gmail_messages: list[dict[str, Any]] | None = None,
    calendar_events: list[dict[str, Any]] | None = None,
    drive_files: list[dict[str, Any]] | None = None,
    maps_context: dict[str, Any] | None = None,
    query_hint: str | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """Analyze context from multiple services and return (LifeFlows, lowConfidenceIgnored).

    Caps: gmail 10, calendar 10, drive 10, maps 1-2.
    Returns (cleaned_workflows, lowConfidenceIgnored_count).
    Each workflow includes provenance: _sourceMessageIds, _sourceEventIds, _sourceFileIds.
    """
    gmail_messages = gmail_messages or []
    calendar_events = calendar_events or []
    drive_files = drive_files or []
    if not gmail_messages and not calendar_events and not drive_files:
        return [], 0

    client = _get_client()
    if client is None:
        return [], 0

    try:
        text = _call_gemini_unified(gmail_messages, calendar_events, drive_files, maps_context, query_hint)
        raw = _extract_json(text)
        return _parse_unified_output(raw)
    except GeminiError:
        raise
    except Exception as exc:
        raise GeminiError(f"Unified analysis failed: {exc}") from exc


def _call_gemini_unified(
    gmail_messages: list[dict[str, Any]],
    calendar_events: list[dict[str, Any]],
    drive_files: list[dict[str, Any]],
    maps_context: dict[str, Any] | None,
    query_hint: str | None,
) -> str:
    prompt = _build_unified_prompt(gmail_messages, calendar_events, drive_files, maps_context, query_hint)
    return _call_gemini_with_fallback(
        _get_client(),
        prompt,
        response_mime_type="application/json",
        temperature=0.3,
        max_output_tokens=4096,
    )


def _build_unified_prompt(
    gmail_messages: list[dict[str, Any]],
    calendar_events: list[dict[str, Any]],
    drive_files: list[dict[str, Any]],
    maps_context: dict[str, Any] | None,
    query_hint: str | None,
) -> str:
    """Build prompt with sections for each connected service. Privacy-preserving."""
    gmail_block = ""
    if gmail_messages:
        lines = []
        for msg in gmail_messages[:10]:
            sender = msg.get('sender', 'Unknown')
            subject = msg.get('subject', '(no subject)')
            date = msg.get('date', 'Unknown')
            snippet = (msg.get('snippet', '') or '')[:200]
            labels = ', '.join(msg.get('labels', []))
            lines.append(
                f"- From: {sender}\n"
                f"  Subject: {subject}\n"
                f"  Date: {date}\n"
                f"  Snippet: {snippet}\n"
                f"  Labels: [{labels}]\n"
                f"  MessageID: {msg.get('id','')}  ThreadID: {msg.get('threadId','')}"
            )
        gmail_block = "\n".join(lines)
    else:
        gmail_block = "(no Gmail context — not connected or no messages)"

    cal_block = ""
    if calendar_events:
        lines = []
        for ev in calendar_events[:10]:
            lines.append(
                f"- Title: {ev.get('summary','(no title)')}\n"
                f"  When: {ev.get('displayStart','')} ({ev.get('start','')} -> {ev.get('end','')})\n"
                f"  Location: {ev.get('location','')}\n"
                f"  Attendees: {', '.join(ev.get('attendees',[])[:3])}\n"
                f"  EventID: {ev.get('id','')}"
            )
        cal_block = "\n".join(lines)
    else:
        cal_block = "(no Calendar context — not connected or no upcoming events)"

    drive_block = ""
    if drive_files:
        lines = []
        for f in drive_files[:10]:
            lines.append(
                f"- Name: {f.get('name','')}\n"
                f"  Type: {f.get('mimeType','')}\n"
                f"  Modified: {f.get('modifiedTime','')}\n"
                f"  FileID: {f.get('id','')}"
            )
        drive_block = "\n".join(lines)
    else:
        drive_block = "(no Drive context — not connected or no files)"

    maps_block = ""
    if maps_context:
        if maps_context.get("geocode"):
            g = maps_context["geocode"]
            maps_block += f"Geocode: {g.get('formatted_address')} ({g.get('lat')},{g.get('lng')})\n"
        if maps_context.get("directions"):
            d = maps_context["directions"]
            maps_block += f"Directions: {d.get('origin')} -> {d.get('destination')} : {d.get('distance_text')} / {d.get('duration_text')} ({d.get('mode')})\n"
        if maps_context.get("query"):
            maps_block += f"Query: {maps_context.get('query')}\n"
    else:
        maps_block = "(no Maps context)"

    hint = query_hint or "(no additional query)"

    return f"""You are LifeFlow, an AI assistant inside GoogleFlow. You analyze Google service
data (Gmail, Calendar, Drive, Maps) to identify genuinely important, actionable
situations and create structured LifeFlow action plans.

===========================
SERVICE DATA (metadata only, privacy-preserving):
===========================

Gmail (last 10 messages, metadata only):
{gmail_block}

Calendar (next 14 days, metadata only):
{cal_block}

Drive (recent files, metadata only):
{drive_block}

Maps / location context:
{maps_block}

User hint: {hint}

===========================
CATEGORIES (use "category" field):
===========================
- deadline       : Submission/expiry/payment/policy renewal with explicit date
- appointment    : Meeting, call, class, seminar
- interview      : Job or academic interview (technical, HR, video, in-person)
- travel         : Flight, train, hotel, trip, travel booking
- payment        : Bill, invoice, refund, subscription, payment due
- application    : Job/course/visa/permit/certification application
- education      : Exam, course deadline, class schedule, certification renewal
- certification  : Credential expiry, professional certification
- document       : Document request, contract, agreement requiring action
- task           : Action item not fitting other categories
- reminder       : Non-urgent follow-up or informational
- other          : Does not fit above

===========================
PRIORITY RULES (set "priority" field):
===========================
- HIGH   : Deadline within 3 days | Interview within 48h | Travel within 7 days
           | Urgent payment/refund | Expiring document/certification
           | Explicit urgent language ("asap", "immediately", "urgent")
- MEDIUM : Deadline within 14 days | Application follow-up | Document review
           | Upcoming event within 1-2 weeks | Important but not urgent
- LOW    : Informational only | No real deadline | Non-urgent follow-up
NEVER mark everything HIGH — use evidence to justify priority.

===========================
CONFIDENCE SCORING (set "confidence" 0.0-1.0):
===========================
- 0.95+  : Exact date, exact event, authoritative source (company HR, airline, etc.)
- 0.85+  : Strong evidence — likely real event, clear inference
- 0.75+  : Good evidence — meaningful action, some uncertainty
- 0.60-0.74: Moderate — possible action, ambiguous info
            ONLY create if checklist steps are genuinely useful.
- Below 0.60: IGNORE — do not create a flow.

===========================
CROSS-SERVICE REASONING (critical improvement):
===========================
1. GMAIL + CALENDAR: If Gmail mentions an interview/appointment AND Calendar has
   the same event, create ONE unified flow. Use Calendar's date/time as authoritative.
   Include both sourceMessageIds AND sourceEventIds in the flow.
   Example: Gmail "Interview scheduled for Sep 10" + Calendar "Tech Interview Sep 10 10AM"
   -> ONE flow: "Prepare for Technical Interview" with Calendar date.

2. GMAIL + DRIVE: If Gmail references a document (resume, certificate, form) AND
   Drive has a matching file, link them. Suggest document review in checklist.
   Example: Gmail "Complete application" + Drive "resume.pdf"
   -> "Complete job application" with relevant Drive file linked.

3. CALENDAR + MAPS: If Calendar has a location AND Maps context exists, suggest
   travel directions and departure time in the checklist.

4. THREAD/DUPLICATE MERGING:
   - Multiple Gmail emails in the same threadId -> ONE flow only
   - Gmail and Calendar describing the same event -> ONE unified flow
   - Similar titles with overlapping dates -> merge into one

5. DRIVE CONTEXT: Use Drive file names and types to add relevant checklist steps.
   Example: Drive has "passport-scan.pdf" near travel dates -> suggest document prep.

===========================
STRICT FILTERING — IGNORE THESE:
===========================
- Spam, promotions, marketing, deal emails
- Newsletters unless they contain a real deadline or action
- Social notifications (LinkedIn, Twitter, Facebook, Instagram)
- Generic product announcements and release notes
- System emails (password resets, OTPs, 2FA) unless real account action needed
- Generic receipts with everything in order, no dispute/refund needed
- Meeting invitations already in Calendar (avoid Gmail+Calendar duplication)
- Automated shipping notifications with no issue
- Duplicate messages in the same thread -> keep ONE
- Unknown senders with vague "opportunity" emails
- Emails with no meaningful user action

===========================
STRICT RULES — NEVER DO THESE:
===========================
- NEVER invent dates, times, locations, or event names
- NEVER assume an email from a known company is important without clear action
- NEVER present uncertain information as fact
- If information is unclear: date="To be confirmed", confidence below 0.75
- NEVER create a flow just because a message exists — only when action is needed
- NEVER use generic checklist items — every step must be specific to the situation
- If "application is being reviewed", do NOT invent a follow-up date
- If no clear action exists, return empty flows[]
- NEVER claim Drive file content was "reviewed" — only metadata was available

===========================
OUTPUT FORMAT:
===========================
Return ONLY a valid JSON object:
{{
  "flows": [
    {{
      "title": "short title (5 words or fewer)",
      "emoji": "one relevant emoji",
      "date": "human-readable date or 'To be confirmed'",
      "status": "Action Needed",
      "readiness": 10,
      "priority": "high|medium|low",
      "confidence": 0.0-1.0,
      "nextUp": "most important immediate action",
      "checklist": [{{"id": "c1", "title": "specific step", "completed": false}}],
      "connectedServices": ["Gmail", "Google Calendar", "Google Drive", "Google Maps", "YouTube", "Google Search", "Gemini"],
      "sourceMessageIds": ["gmail message id"],
      "sourceEventIds": ["calendar event id"],
      "sourceFileIds": ["drive file id"],
      "category": "deadline|appointment|interview|travel|payment|application|education|certification|document|task|reminder|other"
    }}
  ],
  "metadata": {{
    "flowsCreated": 0,
    "flowsIgnored": 0,
    "lowConfidenceIgnored": 0
  }}
}}

Only include a service in connectedServices if it genuinely contributed context.
Set confidence based on evidence strength — be honest, not generous.
Return empty flows[] when nothing meaningful is found."""


def _parse_unified_output(raw: Any) -> tuple[list[dict[str, Any]], int]:
    """Parse the unified analysis output into (flows, lowConfidenceIgnored_count)."""
    if not isinstance(raw, dict):
        raise GeminiError("Unified analysis response was not a JSON object.")
    flows = raw.get("flows")
    if not isinstance(flows, list):
        return [], 0

    metadata = raw.get("metadata") or {}
    if not isinstance(metadata, dict):
        metadata = {}

    result = []
    low_confidence_ignored = 0
    for flow_data in flows:
        try:
            if not isinstance(flow_data, dict):
                continue
            confidence = _clean_confidence(flow_data.get("confidence"))
            if confidence is not None and confidence < CONFIDENCE_THRESHOLD_IGNORE:
                low_confidence_ignored += 1
                continue
            if confidence is not None and confidence < CONFIDENCE_THRESHOLD_HIGH:
                checklist = flow_data.get("checklist", [])
                is_actionable = any(
                    len(str(item.get("title", "")).strip()) > 12
                    for item in checklist
                    if isinstance(item, dict)
                )
                if not is_actionable:
                    low_confidence_ignored += 1
                    continue

            cleaned = _clean_workflow_dict(flow_data, _generate_unified_id(flow_data))
            cleaned["_sourceMessageIds"] = flow_data.get("sourceMessageIds", [])
            cleaned["_sourceEventIds"] = flow_data.get("sourceEventIds", [])
            cleaned["_sourceFileIds"] = flow_data.get("sourceFileIds", [])
            cleaned["_category"] = flow_data.get("category", "other")
            all_ids = list(cleaned["_sourceMessageIds"]) + list(cleaned["_sourceEventIds"]) + list(cleaned["_sourceFileIds"])
            cleaned["_allSourceIds"] = all_ids
            result.append(cleaned)
        except GeminiError:
            continue

    metadata_low = metadata.get("lowConfidenceIgnored", 0)
    if isinstance(metadata_low, (int, float)):
        low_confidence_ignored += int(metadata_low)

    return result, low_confidence_ignored


def _generate_unified_id(flow_data: dict) -> str:
    for key in ("sourceMessageIds", "sourceEventIds", "sourceFileIds"):
        ids = flow_data.get(key, [])
        if ids:
            prefix = {"sourceMessageIds": "gmail", "sourceEventIds": "cal", "sourceFileIds": "drive"}[key]
            return f"{prefix}-{ids[0]}"
    import hashlib
    title = flow_data.get("title", "unknown")
    return f"unified-{hashlib.md5(title.encode()).hexdigest()[:12]}"