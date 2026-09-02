"""Firebase Admin SDK integration — token verification + Firestore access.

Configuration (environment variables only — never commit credentials):

    FIREBASE_SERVICE_ACCOUNT_PATH   Path to the service-account JSON file.
    GOOGLE_APPLICATION_CREDENTIALS  Alternative standard name for the same file.
    FIREBASE_PROJECT_ID             Only needed when relying on Application
                                    Default Credentials (e.g. Cloud Run).

When none of these are set the backend runs in DEMO MODE: authentication is
disabled and workflows live in an in-memory store (see workflow_store.py).
"""

from __future__ import annotations

import os
from typing import Any

_firebase_app: Any = None
_firestore: Any = None
_enabled: bool = False


def _service_account_path() -> str | None:
    for var in ("FIREBASE_SERVICE_ACCOUNT_PATH", "GOOGLE_APPLICATION_CREDENTIALS"):
        value = os.getenv(var)
        if value and value.strip():
            return value.strip()
    return None


def init() -> None:
    """Initialize the Firebase Admin SDK. Call once at application startup.

    Raises RuntimeError when Firebase env vars are set but the SDK or the
    credentials are broken — misconfiguration must fail fast, not silently
    fall back to demo mode.
    """
    global _firebase_app, _firestore, _enabled

    service_account = _service_account_path()
    project_id = (os.getenv("FIREBASE_PROJECT_ID") or "").strip() or None

    if not service_account and not project_id:
        _enabled = False
        return

    try:
        import firebase_admin
        from firebase_admin import credentials, firestore
    except Exception as exc:  # pragma: no cover - depends on environment
        raise RuntimeError(
            "Firebase env vars are set but firebase-admin is not installed. "
            "Run: pip install -r requirements.txt"
        ) from exc

    if service_account:
        if not os.path.exists(service_account):
            raise RuntimeError(
                f"FIREBASE_SERVICE_ACCOUNT_PATH does not exist: {service_account}"
            )
        cred: Any = credentials.Certificate(service_account)
        _firebase_app = firebase_admin.initialize_app(cred)
    else:
        # Application Default Credentials (Cloud Run, gcloud auth, etc.)
        cred = credentials.ApplicationDefault()
        options = {"projectId": project_id} if project_id else None
        _firebase_app = firebase_admin.initialize_app(cred, options)

    _firestore = firestore.client(_firebase_app)
    _enabled = True


def is_enabled() -> bool:
    """True when Firebase Admin is initialized (auth + Firestore required)."""
    return _enabled


def verify_id_token(id_token: str) -> str:
    """Verify a Firebase ID token and return the user's UID.

    Raises an exception on invalid/expired tokens — callers translate that
    into an HTTP 401.
    """
    from firebase_admin import auth as firebase_auth

    decoded = firebase_auth.verify_id_token(id_token, app=_firebase_app)
    uid = decoded.get("uid")
    if not uid:
        raise ValueError("ID token does not contain a uid")
    return str(uid)


def get_firestore() -> Any:
    """Return the Firestore client (only valid when is_enabled())."""
    return _firestore