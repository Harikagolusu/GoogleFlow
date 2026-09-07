"""Google Calendar connector — fetches upcoming events using stored OAuth credentials.

Reuses connectors.base for credential handling.
Only metadata is exposed (summary, location, start/end, attendees, description).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from googleapiclient.discovery import build

from . import connections_store
from .connectors.base import get_credentials_for_user
from .service_registry import SERVICE_CALENDAR

logger = logging.getLogger(__name__)


def _parse_event(item: dict[str, Any]) -> dict[str, Any]:
    """Normalize a Calendar API event into structured metadata."""
    start = item.get("start") or {}
    end = item.get("end") or {}
    # start/end can be dateTime (timed) or date (all-day)
    start_str = start.get("dateTime") or start.get("date") or ""
    end_str = end.get("dateTime") or end.get("date") or ""
    attendees = item.get("attendees") or []
    attendee_emails = [a.get("email", "") for a in attendees if a.get("email")]

    # Try to produce a human-readable date.
    display_start = start_str
    try:
        # dateTime is RFC3339; date is YYYY-MM-DD
        if "T" in start_str:
            dt = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
            display_start = dt.strftime("%b %d, %Y %I:%M %p")
        elif start_str:
            dt = datetime.fromisoformat(start_str)
            display_start = dt.strftime("%b %d, %Y")
    except Exception:
        pass

    # Extract meeting URL from hangoutLink, conferenceData, or location field
    meeting_url = item.get("hangoutLink") or ""
    if not meeting_url:
        conf = item.get("conferenceData") or {}
        for ep in conf.get("entryPoints", []):
            if ep.get("entryPointType") == "video":
                meeting_url = ep.get("uri", "")
                break

    # If location contains a meeting URL, use it as meeting URL
    location = item.get("location") or ""
    if not meeting_url and location:
        import re
        meet_patterns = [
            r"https?://meet\.google\.com/[a-z]{3}-[a-z]{4}-[a-z]{3}",
            r"https?://teams\.microsoft\.com/l/meetup-join/[^\s\)]+",
            r"https?://zoom\.us/j/[^\s\)]+",
            r"https?://[^\s]+\.webex\.com/[^\s]+",
            r"https?://meet\.zoom\.us/[^\s]+",
        ]
        for pattern in meet_patterns:
            match = re.search(pattern, location, re.IGNORECASE)
            if match:
                meeting_url = match.group(0)
                # If location was just the URL, treat it as no location
                if re.match(r"^https?://", location.strip(), re.IGNORECASE):
                    location = ""
                break

    return {
        "id": item.get("id", ""),
        "summary": item.get("summary") or "(no title)",
        "description": (item.get("description") or "")[:300],
        "location": location,
        "start": start_str,
        "end": end_str,
        "displayStart": display_start,
        "attendees": attendee_emails[:5],
        "htmlLink": item.get("htmlLink") or "",
        "meetingUrl": meeting_url,
        "status": item.get("status") or "confirmed",
    }


def fetch_upcoming_events(
    uid: str,
    max_results: int = 10,
    days_ahead: int = 14,
    calendar_id: str = "primary",
) -> list[dict[str, Any]]:
    """Fetch upcoming Calendar events for the authenticated user.

    Args:
        uid: Firebase UID.
        max_results: 1-50, default 10.
        days_ahead: look-ahead window, default 14 days.
        calendar_id: calendar to query, default "primary".

    Raises:
        ConnectionError: if not connected.
        PermissionError: if credentials revoked/insufficient.
        RuntimeError: other API errors.
    """
    max_results = max(1, min(50, max_results))
    days_ahead = max(1, min(60, days_ahead))

    creds = get_credentials_for_user(uid, SERVICE_CALENDAR)
    if creds is None:
        raise ConnectionError("Calendar is not connected. Please connect your Calendar first.")

    try:
        service = build("calendar", "v3", credentials=creds)
        now = datetime.now(timezone.utc).isoformat()
        time_max = (datetime.now(timezone.utc) + timedelta(days=days_ahead)).isoformat()

        results = (
            service.events()
            .list(
                calendarId=calendar_id,
                timeMin=now,
                timeMax=time_max,
                maxResults=max_results,
                singleEvents=True,
                orderBy="startTime",
                fields="items(id,summary,description,location,start,end,attendees,htmlLink,hangoutLink,conferenceData,status)",
            )
            .execute()
        )
        items = results.get("items", [])
        output = [_parse_event(it) for it in items]

        connections_store.update_last_sync(uid, SERVICE_CALENDAR)
        return output

    except ConnectionError:
        raise
    except PermissionError:
        raise
    except Exception as exc:
        err = str(exc).lower()
        if "invalid_grant" in err or "token_expired" in err or "401" in err:
            raise PermissionError(
                "Calendar credentials have expired or been revoked. Please disconnect and reconnect."
            ) from exc
        if "403" in err or "insufficient" in err:
            raise PermissionError("Calendar access denied. Please reconnect with calendar permission.") from exc
        raise RuntimeError(f"Calendar API error: {exc}") from exc


def search_events(
    uid: str,
    query: str,
    max_results: int = 10,
) -> list[dict[str, Any]]:
    """Search Calendar events by text query.

    Args:
        uid: Firebase UID.
        query: Free-text search query (matches summary, description, location).
        max_results: 1-50, default 10.

    Returns:
        List of matching event dicts.
    """
    creds = get_credentials_for_user(uid, SERVICE_CALENDAR)
    if creds is None:
        raise ConnectionError("Calendar is not connected. Please connect your Calendar first.")

    try:
        service = build("calendar", "v3", credentials=creds)
        results = (
            service.events()
            .list(
                calendarId="primary",
                q=query,
                maxResults=max(1, min(50, max_results)),
                singleEvents=True,
                orderBy="startTime",
                fields="items(id,summary,description,location,start,end,attendees,htmlLink,hangoutLink,conferenceData,status)",
            )
            .execute()
        )
        items = results.get("items", [])
        return [_parse_event(it) for it in items]

    except ConnectionError:
        raise
    except PermissionError:
        raise
    except Exception as exc:
        err = str(exc).lower()
        if "invalid_grant" in err or "token_expired" in err or "401" in err:
            raise PermissionError("Calendar credentials have expired or been revoked. Please disconnect and reconnect.") from exc
        if "403" in err or "insufficient" in err:
            raise PermissionError("Calendar access denied. Please reconnect with calendar permission.") from exc
        raise RuntimeError(f"Calendar search error: {exc}") from exc
