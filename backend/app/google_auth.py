"""Google OAuth 2.0 service for Google Apps (Gmail, Calendar, etc.) access.

This is a SEPARATE authorization layer from Firebase Authentication:

- Firebase Authentication (firebase_service.py) proves WHO the user is via
  their Firebase ID token. It does NOT grant access to Gmail or Calendar.
- This module implements Google OAuth 2.0 so the application can request
  scoped permission to access Google APIs on behalf of the signed-in user.

What lives here:
- OAuth client configuration (read from env vars; never hard-coded).
- Cryptographically secure OAuth state token generation.
- Temporary in-memory state store keyed by state token, associated with the
  verified Firebase UID. Single-use, expires after a configurable TTL.
- Authorization URL construction.
- Authorization code exchange for OAuth credentials (access + refresh tokens).
- Backend-only storage of refresh tokens under users/{uid}/connections/{service}.
- Google token revocation when the user disconnects.

What does NOT live here:
- Gmail API calls (next phase: gmail_connector.py).
- Calendar API calls (future phase).
- Anything that exposes tokens to the frontend.

Security:
- Client secret and refresh tokens are never returned to the frontend.
- OAuth state is single-use and TTL-bounded.
- The Firebase UID used to associate state is recovered from the backend's
  own state map on the callback — never from a client-supplied value.
- The OAuth client_id/client_secret are only read from environment variables.
"""
from __future__ import annotations

import logging
import os
import secrets
import time
from typing import Any
from urllib.parse import urlencode

logger = logging.getLogger(__name__)

# Default TTL for an unused OAuth state before it is considered expired.
DEFAULT_STATE_TTL_SECONDS = 600  # 10 minutes

# Gmail scope — read-only. The minimum scope needed to detect events without
# write/modify access to the user's mailbox.
# Kept for backward compat — new code should import from service_registry.
from .service_registry import GMAIL_SCOPES, CALENDAR_SCOPES, DRIVE_SCOPES, SCOPES_FOR_SERVICE  # noqa: F401

# Token endpoint for exchanging authorization codes + revoking tokens.
_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
_GOOGLE_REVOKE_URL = "https://oauth2.googleapis.com/revoke"

# Module-level state store. Two implementations:
# - In-memory dict (default; demo + development). Disappears on restart.
# - Firestore-backed (when initialized via init_firestore). Same TTL semantics.
_states: dict[str, dict[str, Any]] = {}
_firestore: Any = None

# Pluggable function for exchanging an authorization code for credentials.
# Defaults to a real HTTP call. Tests inject a mock to avoid network I/O.
_code_exchanger: Any = None
# Pluggable function for revoking a token. Tests inject a mock.
_token_revoker: Any = None


def init_firestore(firestore_client: Any) -> None:
    """Wire state storage to Firestore when available. Pass None for in-memory.

    Firestore collection: oauth_states/{state}
    Document fields:
        uid          - verified Firebase UID of the requesting user
        service      - service name (e.g. "gmail")
        created_at   - unix timestamp (seconds)
        expires_at   - unix timestamp (seconds)
        consumed     - True once the state has been used (single-use)
    """
    global _firestore
    _firestore = firestore_client


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def _client_id() -> str:
    return (os.getenv("GOOGLE_OAUTH_CLIENT_ID") or "").strip()


def _client_secret() -> str:
    return (os.getenv("GOOGLE_OAUTH_CLIENT_SECRET") or "").strip()


def _redirect_uri() -> str:
    return (
        os.getenv("GOOGLE_OAUTH_REDIRECT_URI")
        or "http://localhost:8010/api/auth/gmail/callback"
    ).strip()


def is_configured() -> bool:
    """True when all required OAuth env vars are present."""
    return bool(_client_id() and _client_secret() and _redirect_uri())


def configuration_status() -> dict[str, Any]:
    """Return a safe description of which OAuth env vars are present.

    Never includes secret values; only a boolean for each.
    """
    return {
        "client_id_set": bool(_client_id()),
        "client_secret_set": bool(_client_secret()),
        "redirect_uri": _redirect_uri() or None,
        "configured": is_configured(),
    }


# ---------------------------------------------------------------------------
# State token management
# ---------------------------------------------------------------------------


def _state_ttl_seconds() -> int:
    raw = os.getenv("GOOGLE_OAUTH_STATE_TTL_SECONDS", str(DEFAULT_STATE_TTL_SECONDS))
    try:
        value = int(raw)
        return value if value > 0 else DEFAULT_STATE_TTL_SECONDS
    except ValueError:
        return DEFAULT_STATE_TTL_SECONDS


def generate_state(uid: str, service: str) -> str:
    """Create a single-use OAuth state token bound to (uid, service).

    Uses cryptographically secure randomness (secrets.token_urlsafe).
    """
    state = secrets.token_urlsafe(32)
    now = int(time.time())
    expires_at = now + _state_ttl_seconds()
    record = {
        "uid": uid,
        "service": service,
        "created_at": now,
        "expires_at": expires_at,
        "consumed": False,
    }
    if _firestore is None:
        _states[state] = record
    else:
        try:
            _firestore.collection("oauth_states").document(state).set(record)
        except Exception:
            # Firestore disabled (e.g. API not enabled) — fallback to memory
            _states[state] = record
    return state


class StateError(Exception):
    """Raised when an OAuth state is missing/invalid/expired/consumed."""


def _load_state(state: str) -> dict[str, Any] | None:
    if not state:
        return None
    if _firestore is None:
        return _states.get(state)
    try:
        snapshot = _firestore.collection("oauth_states").document(state).get()
    except Exception:
        return _states.get(state)
    if not snapshot.exists:
        return None
    return dict(snapshot.to_dict() or {})


def _mark_state_consumed(state: str) -> None:
    if _firestore is None:
        if state in _states:
            _states.pop(state, None)
    else:
        try:
            _firestore.collection("oauth_states").document(state).delete()
        except Exception:
            pass
        _states.pop(state, None)


def validate_and_consume_state(state: str) -> dict[str, Any]:
    """Validate the state token and atomically consume it.

    Returns the stored record (uid, service) on success.
    Raises StateError on missing/invalid/expired/consumed state.
    """
    if not state:
        raise StateError("Missing OAuth state.")
    record = _load_state(state)
    if record is None:
        raise StateError("OAuth state not found.")
    if record.get("consumed"):
        raise StateError("OAuth state has already been used.")
    now = int(time.time())
    if now >= int(record.get("expires_at", 0)):
        _mark_state_consumed(state)
        raise StateError("OAuth state has expired.")
    _mark_state_consumed(state)
    return record


# ---------------------------------------------------------------------------
# Authorization URL + token exchange
# ---------------------------------------------------------------------------


def build_authorization_url(service: str, uid: str) -> dict[str, str]:
    """Build the Google consent-screen URL for the given service.

    Returns a dict with `authorization_url` and `state` so the caller can
    attach the state to a server-managed session/cookie. The frontend must
    never construct this URL itself.
    """
    if not is_configured():
        raise StateError(
            "Google OAuth is not configured. Set GOOGLE_OAUTH_CLIENT_ID, "
            "GOOGLE_OAUTH_CLIENT_SECRET, and GOOGLE_OAUTH_REDIRECT_URI."
        )
    state = generate_state(uid, service)
    scopes = _scopes_for(service)
    params = {
        "client_id": _client_id(),
        "redirect_uri": _redirect_uri(),
        "response_type": "code",
        "scope": " ".join(scopes),
        # "offline" + consent ensures Google returns a refresh_token.
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": state,
    }
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)
    return {"authorization_url": url, "state": state}


def _scopes_for(service: str) -> list[str]:
    return list(SCOPES_FOR_SERVICE.get(service, []))


# ---------------------------------------------------------------------------
# Authorization code exchange
# ---------------------------------------------------------------------------


def set_code_exchanger(fn: Any) -> None:
    """Inject a function to exchange an authorization code for credentials.

    Signature: (code, redirect_uri, client_id, client_secret) -> dict
    Defaults to a real HTTP POST to Google's token endpoint.
    """
    global _code_exchanger
    _code_exchanger = fn


def _default_code_exchange(
    code: str, redirect_uri: str, client_id: str, client_secret: str
) -> dict[str, Any]:
    import requests

    logger.warning("_default_code_exchange: exchanging code at %s, redirect_uri=%s", _GOOGLE_TOKEN_URL, redirect_uri)
    response = requests.post(
        _GOOGLE_TOKEN_URL,
        data={
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
        timeout=15,
    )
    logger.warning("_default_code_exchange: Google responded with status %d", response.status_code)
    if response.status_code != 200:
        logger.error("_default_code_exchange: Google rejected code. Response body: %s", response.text[:500])
        raise StateError(
            f"Google rejected the authorization code (status {response.status_code})."
        )
    return response.json()


def exchange_code(code: str) -> dict[str, Any]:
    """Exchange an authorization code for OAuth credentials.

    Returns a normalized dict with keys:
        access_token, refresh_token (may be missing if Google did not return
        one - common for re-consent), expires_in, scope, token_type, id_token.
    The caller (api layer) is responsible for storing the refresh token
    server-side under users/{uid}/connections/{service}.
    """
    if not is_configured():
        raise StateError("Google OAuth is not configured.")
    if not code:
        raise StateError("Missing authorization code.")
    exchanger = _code_exchanger or _default_code_exchange
    raw = exchanger(code, _redirect_uri(), _client_id(), _client_secret())
    if not isinstance(raw, dict) or "access_token" not in raw:
        raise StateError("Google did not return an access token.")
    return {
        "access_token": raw.get("access_token"),
        "refresh_token": raw.get("refresh_token"),
        "expires_in": raw.get("expires_in"),
        "scope": raw.get("scope"),
        "token_type": raw.get("token_type"),
        "id_token": raw.get("id_token"),
    }


# ---------------------------------------------------------------------------
# Token revocation
# ---------------------------------------------------------------------------


def set_token_revoker(fn: Any) -> None:
    """Inject a function to revoke a Google OAuth token.

    Signature: (token: str) -> bool
    Returns True on success, False otherwise. Defaults to a real HTTP POST.
    """
    global _token_revoker
    _token_revoker = fn


def _default_revoke(token: str) -> bool:
    import requests

    response = requests.post(
        _GOOGLE_REVOKE_URL,
        params={"token": token},
        timeout=15,
    )
    return response.status_code == 200


def revoke_token(token: str | None) -> bool:
    """Best-effort Google token revocation. Returns True on success.

    Failures are non-fatal: the caller should always delete the stored
    connection record regardless of the revocation result.
    """
    if not token:
        return False
    try:
        revoker = _token_revoker or _default_revoke
        return bool(revoker(token))
    except Exception as exc:  # pragma: no cover - network dependent
        logger.warning("Google token revocation failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Test/admin helpers
# ---------------------------------------------------------------------------


def reset_for_tests() -> None:
    """Clear all in-memory state. Tests call this between scenarios."""
    _states.clear()
