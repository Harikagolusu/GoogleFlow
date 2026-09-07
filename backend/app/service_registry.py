"""Central registry for Google service integrations.

Single source of truth for supported services, their OAuth scopes,
display names and API identifiers. Gmail, Calendar and Drive use
OAuth + per-user token storage; Maps uses a server API key (no OAuth).

Adding a new OAuth service = one entry here + one connector.
"""

from __future__ import annotations

# OAuth scopes — read-only MVP.
GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
CALENDAR_SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]
DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
# Alternative privacy-preserving scope: ["https://www.googleapis.com/auth/drive.metadata.readonly"]
# MVP uses drive.readonly so metadata + future file-content phase works with same consent.

# Service identifiers (canonical, lowercase — used in URLs and Firestore doc ids).
SERVICE_GMAIL = "gmail"
SERVICE_CALENDAR = "calendar"
SERVICE_DRIVE = "drive"
SERVICE_MAPS = "maps"  # Maps is API-key only, not OAuth.

# OAuth services — require user consent.
OAUTH_SERVICES = {SERVICE_GMAIL, SERVICE_CALENDAR, SERVICE_DRIVE}

# All services including Maps (for UI grids).
ALL_SERVICES = {SERVICE_GMAIL, SERVICE_CALENDAR, SERVICE_DRIVE, SERVICE_MAPS}

# Scope lookup used by google_auth._scopes_for()
SCOPES_FOR_SERVICE: dict[str, list[str]] = {
    SERVICE_GMAIL: GMAIL_SCOPES,
    SERVICE_CALENDAR: CALENDAR_SCOPES,
    SERVICE_DRIVE: DRIVE_SCOPES,
}

# Human-readable names matching gemini_service.KNOWN_SERVICES / ServiceLogo.
DISPLAY_NAME: dict[str, str] = {
    SERVICE_GMAIL: "Gmail",
    SERVICE_CALENDAR: "Google Calendar",
    SERVICE_DRIVE: "Google Drive",
    SERVICE_MAPS: "Google Maps",
}

# Google API service names for googleapiclient.discovery.build()
API_SERVICE_NAME: dict[str, str] = {
    SERVICE_GMAIL: "gmail",
    SERVICE_CALENDAR: "calendar",
    SERVICE_DRIVE: "drive",
}

API_VERSION: dict[str, str] = {
    SERVICE_GMAIL: "v1",
    SERVICE_CALENDAR: "v3",
    SERVICE_DRIVE: "v3",
}


def is_oauth_service(service: str) -> bool:
    return service in OAUTH_SERVICES


def is_valid_service(service: str) -> bool:
    return service in ALL_SERVICES


def get_scopes(service: str) -> list[str]:
    return list(SCOPES_FOR_SERVICE.get(service, []))
