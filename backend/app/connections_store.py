"""Backend-only storage for Google Apps connections (Gmail, Calendar, ...).

This module owns the persistence layer for connection records that hold
OAuth credentials. It is INTENTIONALLY a separate module from
`workflow_store.py` so workflow data and credential data have distinct
ownership boundaries.

Storage strategy:
- Firestore (production):
      users/{firebaseUid}/connections/{service}
      where {service} is e.g. "gmail".
- In-memory dict (demo / development):
      { uid: { service: connection_dict } }

Security notes:
- The Firebase UID is the SOLE ownership boundary. It is always derived
  from the verified Firebase ID token, never from a client-supplied value.
- Refresh tokens live ONLY in this store. They are never returned to the
  frontend by any API path.
- Credential data is stored in plain dicts. Application-level encryption
  is intentionally OUT OF SCOPE for this phase: the security boundary
  is the database ACL (Firestore security rules) + the verified UID.
  The connection record carries an `encrypted: false` marker so the
  storage layer makes the boundary explicit and honest.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

# Service identifier constants — re-exported from registry for backward compat.
from .service_registry import SERVICE_GMAIL, SERVICE_CALENDAR, SERVICE_DRIVE, SERVICE_MAPS  # noqa: F401

# Storage backing
_firestore: Any = None
_memory: dict[str, dict[str, Any]] = {}


def init(firestore_client: Any) -> None:
    """Wire connections storage to Firestore (or None for in-memory demo)."""
    global _firestore
    _firestore = firestore_client


def is_persistent() -> bool:
    return _firestore is not None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _conn_doc(uid: str, service: str) -> Any:
    return (
        _firestore.collection("users")
        .document(uid)
        .collection("connections")
        .document(service)
    )


def _public_view(record: dict[str, Any] | None, service: str | None = None) -> dict[str, Any]:
    """Return a SAFE view of a connection (no tokens, no client secrets)."""
    if not record:
        svc = service or "gmail"
        return {"connected": False, "service": svc, "scopes": []}
    # Use stored service name; fallback to passed service or "gmail" for legacy records.
    svc = record.get("service") or service or "gmail"
    return {
        "connected": bool(record.get("is_active", True)),
        "service": svc,
        "scopes": list(record.get("scopes") or []),
        "connected_at": record.get("connected_at"),
        "last_sync_at": record.get("last_sync_at"),
    }


def save_connection(
    uid: str,
    service: str,
    *,
    scopes: list[str],
    access_token: str | None,
    refresh_token: str | None,
    expires_in: int | None = None,
) -> dict[str, Any]:
    """Create or replace a connection record for (uid, service).

    `access_token` and `refresh_token` are stored only in the returned
    record; they are NEVER propagated to the frontend.
    """
    if not uid:
        raise ValueError("save_connection requires a verified uid.")
    record = {
        "service": service,
        "scopes": list(scopes),
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_in": expires_in,
        "connected_at": _now_iso(),
        "last_sync_at": None,
        "is_active": True,
        # Explicit, honest marker: this record is NOT application-encrypted.
        # See module docstring for the security boundary.
        "encrypted": False,
    }
    if _firestore is None:
        _memory.setdefault(uid, {})[service] = record
    else:
        try:
            _conn_doc(uid, service).set(record)
        except Exception:
            # Firestore disabled — keep in memory so OAuth still works
            _memory.setdefault(uid, {})[service] = record
    return record


def get_connection(uid: str, service: str) -> dict[str, Any] | None:
    """Return the full connection record (includes tokens) for backend use.

    This MUST NOT be returned to the frontend. Callers that expose
    connection info must go through `get_public_connection` instead.
    """
    if _firestore is None:
        return (_memory.get(uid) or {}).get(service)
    try:
        snapshot = _conn_doc(uid, service).get()
    except Exception:
        # Firestore may be disabled (e.g. API not enabled) — treat as not connected.
        return None
    if not snapshot.exists:
        return None
    return dict(snapshot.to_dict() or {})


def get_public_connection(uid: str, service: str) -> dict[str, Any]:
    """Return the safe, public-facing view of the user's connection."""
    return _public_view(get_connection(uid, service), service=service)


def delete_connection(uid: str, service: str) -> dict[str, Any] | None:
    """Delete and return the removed connection (or None if none existed)."""
    existing = get_connection(uid, service)
    if existing is None:
        return None
    if _firestore is None:
        user = _memory.get(uid) or {}
        user.pop(service, None)
        if not user:
            _memory.pop(uid, None)
    else:
        try:
            _conn_doc(uid, service).delete()
        except Exception:
            pass
    return existing


def update_last_sync(uid: str, service: str) -> None:
    """Stamp the last_sync_at field without touching credentials."""
    if _firestore is None:
        record = (_memory.get(uid) or {}).get(service)
        if record is not None:
            record["last_sync_at"] = _now_iso()
        return
    _conn_doc(uid, service).set({"last_sync_at": _now_iso()}, merge=True)


def reset_for_tests() -> None:
    """Clear all in-memory connection state. Tests call this between scenarios."""
    _memory.clear()
