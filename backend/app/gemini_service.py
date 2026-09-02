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
import os
import re
from typing import Any

DEFAULT_MODEL = "gemini-2.5-flash"

# Canonical service names the frontend knows how to display.
KNOWN_SERVICES = [
    "Gmail",
    "Google Drive",
    "Google Calendar",
    "Google Maps",
    "YouTube",
    "Google Search",
    "Google News",
    "Google Photos",
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
    "news": "Google News",
    "google news": "Google News",
    "photos": "Google Photos",
    "google photos": "Google Photos",
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
    try:
        from google.genai import types
        model = os.getenv("GEMINI_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
        response = client.models.generate_content(
            model=model,
            contents=_build_prompt(query),
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.7,
                max_output_tokens=2048,
            ),
        )
    except GeminiError:
        raise
    except Exception as exc:
        raise GeminiError(f"Gemini request failed: {exc}") from exc

    text = (getattr(response, "text", None) or "").strip()
    if not text:
        raise GeminiError("Gemini returned an empty response.")
    return text


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
  Google News, Google Photos, Gemini. Pick 3-6 that actually help this plan.

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
            "Gmail", "Google Calendar", "Google Maps", "Google Drive", "Google Photos", "Gemini",
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