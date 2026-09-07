"""Gmail API connector — fetches recent messages using stored OAuth credentials.

This module builds an authenticated Gmail API client from the credentials
stored in connections_store. It handles token refresh transparently.

Security notes:
- Access tokens and refresh tokens are NEVER returned to the frontend.
- Only structured metadata (sender, subject, date, snippet) is exposed.
- The connector uses the user's stored credentials, not the app's.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as AuthRequest
from googleapiclient.discovery import build

from . import connections_store

logger = logging.getLogger(__name__)

# Gmail API scope that matches the OAuth scope we requested.
_GMAIL_API_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def _build_credentials(connection: dict[str, Any]) -> Credentials:
    """Build a google.oauth2.credentials.Credentials from a stored connection.

    If the access token is expired and a refresh token is available,
    the credentials will be refreshed transparently on the first API call.
    """
    access_token = connection.get("access_token") or ""
    refresh_token = connection.get("refresh_token") or ""
    # Compute token expiry from expires_in if available.
    # stored record may have been saved a while ago, so treat as expired.
    token_uri = "https://oauth2.googleapis.com/token"
    client_id = _get_client_id()
    client_secret = _get_client_secret()

    creds = Credentials(
        token=access_token,
        refresh_token=refresh_token,
        token_uri=token_uri,
        client_id=client_id,
        client_secret=client_secret,
        scopes=_GMAIL_API_SCOPES,
    )

    # If the token is expired or about to expire, refresh it.
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(AuthRequest())
            logger.info("Refreshed expired Gmail access token for user.")
        except Exception as exc:
            logger.error("Failed to refresh Gmail access token: %s", exc)
            raise

    return creds


def _get_client_id() -> str:
    import os
    return (os.getenv("GOOGLE_OAUTH_CLIENT_ID") or "").strip()


def _get_client_secret() -> str:
    import os
    return (os.getenv("GOOGLE_OAUTH_CLIENT_SECRET") or "").strip()


def _get_credentials_for_user(uid: str) -> Credentials | None:
    """Retrieve and build OAuth credentials for the given user.

    Returns None if the user has no Gmail connection.
    """
    connection = connections_store.get_connection(uid, connections_store.SERVICE_GMAIL)
    if connection is None:
        return None

    access_token = connection.get("access_token")
    refresh_token = connection.get("refresh_token")
    if not access_token and not refresh_token:
        logger.warning("Gmail connection exists but has no tokens for uid=%s", uid)
        return None

    return _build_credentials(connection)


def _save_refreshed_token(uid: str, creds: Credentials) -> None:
    """Persist refreshed token back to the connections store."""
    connection = connections_store.get_connection(uid, connections_store.SERVICE_GMAIL)
    if connection is None:
        return
    # Update only the access token and expiry — preserve everything else.
    connections_store.save_connection(
        uid,
        connections_store.SERVICE_GMAIL,
        scopes=connection.get("scopes", _GMAIL_API_SCOPES),
        access_token=creds.token,
        refresh_token=creds.refresh_token or connection.get("refresh_token"),
        expires_in=None,
    )


def _extract_headers(headers: list[dict[str, str]], name: str) -> str:
    """Extract a single header value by name from Gmail message headers."""
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


def _parse_message(msg: dict[str, Any]) -> dict[str, Any]:
    """Parse a Gmail message list entry into structured metadata."""
    headers = msg.get("payload", {}).get("headers", [])
    date_str = _extract_headers(headers, "Date")

    # Parse the date for display.
    display_date = date_str
    try:
        # Gmail dates are like "Tue, 02 Sep 2026 10:30:00 +0530"
        dt = datetime.strptime(date_str, "%a, %d %b %Y %H:%M:%S %z")
        display_date = dt.strftime("%b %d, %Y %I:%M %p")
    except (ValueError, TypeError):
        pass

    return {
        "id": msg.get("id", ""),
        "threadId": msg.get("threadId", ""),
        "sender": _extract_headers(headers, "From"),
        "subject": _extract_headers(headers, "Subject"),
        "date": display_date,
        "snippet": msg.get("snippet", ""),
        "labels": msg.get("labelIds", []),
    }


def fetch_messages_by_ids(uid: str, message_ids: list[str]) -> list[dict[str, Any]]:
    """Fetch specific Gmail messages by their IDs.

    More efficient than fetch_recent_messages when you already know which
    message IDs you need.
    """
    if not message_ids:
        return []

    creds = _get_credentials_for_user(uid)
    if creds is None:
        raise ConnectionError("Gmail is not connected. Please connect your Gmail account first.")

    try:
        service = build("gmail", "v1", credentials=creds)
        output = []
        for msg_id in message_ids:
            if not msg_id:
                continue
            try:
                msg_detail = service.users().messages().get(
                    userId="me",
                    id=msg_id,
                    format="metadata",
                    metadataHeaders=["From", "Subject", "Date"],
                ).execute()
                output.append(_parse_message(msg_detail))
            except Exception as exc:
                logger.warning("Failed to fetch message %s: %s", msg_id, exc)
                continue

        if output:
            connections_store.update_last_sync(uid, connections_store.SERVICE_GMAIL)
        return output

    except ConnectionError:
        raise
    except PermissionError:
        raise
    except Exception as exc:
        err = str(exc).lower()
        if "invalid_grant" in err or "token_expired" in err or "401" in err:
            raise PermissionError(
                "Gmail credentials have expired or been revoked. "
                "Please disconnect and reconnect your Gmail account."
            ) from exc
        if "403" in err or "insufficient" in err:
            raise PermissionError(
                "Gmail access denied. The requested scope may not be authorized. "
                "Please disconnect and reconnect your Gmail account."
            ) from exc
        raise RuntimeError(f"Gmail API error: {exc}") from exc


def fetch_recent_messages(uid: str, max_results: int = 10) -> list[dict[str, Any]]:
    """Fetch the most recent Gmail messages for the authenticated user.

    Args:
        uid: The Firebase UID (or demo UID) of the user.
        max_results: Maximum number of messages to return (1-50, default 10).

    Returns:
        A list of dicts with structured message metadata.

    Raises:
        ConnectionError: If the user has no Gmail connection.
        PermissionError: If credentials are invalid/revoked.
        RuntimeError: For other Gmail API errors.
    """
    # Validate limit.
    max_results = max(1, min(50, max_results))

    # Get credentials.
    creds = _get_credentials_for_user(uid)
    if creds is None:
        raise ConnectionError("Gmail is not connected. Please connect your Gmail account first.")

    try:
        service = build("gmail", "v1", credentials=creds)

        # Fetch the message list (metadata only, no full bodies).
        results = service.users().messages().list(
            userId="me",
            maxResults=max_results,
        ).execute()

        messages = results.get("messages", [])
        if not messages:
            return []

        # Fetch metadata for each message.
        # Use format="metadata" to get only headers + snippet (no body).
        output = []
        for msg_stub in messages:
            msg_id = msg_stub.get("id")
            if not msg_id:
                continue
            try:
                msg_detail = service.users().messages().get(
                    userId="me",
                    id=msg_id,
                    format="metadata",
                    metadataHeaders=["From", "Subject", "Date"],
                ).execute()
                output.append(_parse_message(msg_detail))
            except Exception as exc:
                logger.warning("Failed to fetch message %s: %s", msg_id, exc)
                continue

        # Update last_sync timestamp.
        connections_store.update_last_sync(uid, connections_store.SERVICE_GMAIL)

        return output

    except ConnectionError:
        raise
    except PermissionError:
        raise
    except Exception as exc:
        error_str = str(exc).lower()
        if "invalid_grant" in error_str or "token_expired" in error_str or "401" in error_str:
            raise PermissionError(
                "Gmail credentials have expired or been revoked. "
                "Please disconnect and reconnect your Gmail account."
            ) from exc
        if "403" in error_str or "insufficient" in error_str:
            raise PermissionError(
                "Gmail access denied. The requested scope may not be authorized. "
                "Please disconnect and reconnect your Gmail account."
            ) from exc
        raise RuntimeError(f"Gmail API error: {exc}") from exc


def fetch_message_bodies(uid: str, message_ids: list[str]) -> dict[str, dict[str, Any]]:
    """Fetch full email bodies for specific message IDs.

    Returns a dict mapping messageId -> dict with 'body' (decoded text content)
    and 'snippet'. Only used server-side for workflow detail enrichment.
    """
    creds = _get_credentials_for_user(uid)
    if creds is None:
        return {}

    def _extract_text(payload: dict[str, Any]) -> str:
        mime = payload.get("mimeType", "")
        if mime == "text/plain":
            data = payload.get("body", {}).get("data", "")
            if data:
                import base64 as _b64
                return _b64.urlsafe_b64decode(data.encode()).decode("utf-8", errors="replace")
        if "parts" in payload:
            for part in payload["parts"]:
                text = _extract_text(part)
                if text:
                    return text
        return ""

    try:
        service = build("gmail", "v1", credentials=creds)
        result: dict[str, dict[str, Any]] = {}

        for msg_id in message_ids:
            if not msg_id:
                continue
            try:
                msg_detail = service.users().messages().get(
                    userId="me",
                    id=msg_id,
                    format="full",
                ).execute()

                body_text = _extract_text(msg_detail.get("payload", {}))
                snippet = msg_detail.get("snippet", "")
                result[msg_id] = {"body": body_text[:2000], "snippet": snippet}

            except Exception as exc:
                logger.warning("Failed to fetch message body %s: %s", msg_id, exc)
                continue

        return result

    except Exception:
        return {}
