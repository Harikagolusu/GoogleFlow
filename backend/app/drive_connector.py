"""Google Drive connector — fetches recent file metadata using stored OAuth credentials.

Only metadata is fetched (name, mimeType, modifiedTime, owners, link).
No file bodies are downloaded in MVP.
"""

from __future__ import annotations

import logging
from typing import Any

from googleapiclient.discovery import build

from . import connections_store
from .connectors.base import get_credentials_for_user
from .service_registry import SERVICE_DRIVE

logger = logging.getLogger(__name__)


def _parse_file(item: dict[str, Any]) -> dict[str, Any]:
    owners = item.get("owners") or []
    owner_name = owners[0].get("displayName") if owners else ""
    return {
        "id": item.get("id", ""),
        "name": item.get("name", ""),
        "mimeType": item.get("mimeType", ""),
        "modifiedTime": item.get("modifiedTime", ""),
        "owner": owner_name,
        "webViewLink": item.get("webViewLink") or "",
        "iconLink": item.get("iconLink") or "",
    }


def fetch_recent_files(
    uid: str,
    max_results: int = 10,
    query: str | None = None,
) -> list[dict[str, Any]]:
    """Fetch recent Drive file metadata for the authenticated user.

    Args:
        uid: Firebase UID.
        max_results: 1-50, default 10.
        query: optional Drive search query (e.g., "passport"); MVP ignores unless provided.

    Raises:
        ConnectionError: if not connected.
        PermissionError: if credentials revoked/insufficient.
        RuntimeError: other API errors.
    """
    max_results = max(1, min(50, max_results))

    creds = get_credentials_for_user(uid, SERVICE_DRIVE)
    if creds is None:
        raise ConnectionError("Drive is not connected. Please connect your Drive first.")

    try:
        service = build("drive", "v3", credentials=creds)

        # Base query: not trashed. If query provided, add name contains.
        q = "trashed = false"
        if query:
            # Escape single quotes.
            safe = query.replace("'", "\\'")
            q = f"trashed = false and name contains '{safe}'"

        results = (
            service.files()
            .list(
                pageSize=max_results,
                q=q,
                orderBy="modifiedTime desc",
                fields="files(id, name, mimeType, modifiedTime, owners, webViewLink, iconLink)",
            )
            .execute()
        )
        files = results.get("files", [])
        output = [_parse_file(f) for f in files]

        connections_store.update_last_sync(uid, SERVICE_DRIVE)
        return output[:max_results]

    except ConnectionError:
        raise
    except PermissionError:
        raise
    except Exception as exc:
        err = str(exc).lower()
        if "invalid_grant" in err or "token_expired" in err or "401" in err:
            raise PermissionError(
                "Drive credentials have expired or been revoked. Please disconnect and reconnect."
            ) from exc
        if "403" in err or "insufficient" in err:
            raise PermissionError("Drive access denied. Please reconnect with Drive permission.") from exc
        raise RuntimeError(f"Drive API error: {exc}") from exc
