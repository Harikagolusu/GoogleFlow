"""Shared credential helpers for OAuth connectors.

All Calendar/Drive/Gmail connectors use this so token refresh and
credential construction is not duplicated.
"""

from __future__ import annotations

import os
import logging
from typing import Any

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as AuthRequest

from .. import connections_store
from ..service_registry import SCOPES_FOR_SERVICE

logger = logging.getLogger(__name__)

_TOKEN_URI = "https://oauth2.googleapis.com/token"


def _get_client_id() -> str:
    return (os.getenv("GOOGLE_OAUTH_CLIENT_ID") or "").strip()


def _get_client_secret() -> str:
    return (os.getenv("GOOGLE_OAUTH_CLIENT_SECRET") or "").strip()


def _scopes_for(service: str) -> list[str]:
    return list(SCOPES_FOR_SERVICE.get(service, []))


def build_credentials(connection: dict[str, Any], service: str) -> Credentials:
    """Build Credentials from a stored connection dict for `service`."""
    scopes = _scopes_for(service) or connection.get("scopes") or []
    creds = Credentials(
        token=connection.get("access_token") or "",
        refresh_token=connection.get("refresh_token") or "",
        token_uri=_TOKEN_URI,
        client_id=_get_client_id(),
        client_secret=_get_client_secret(),
        scopes=scopes,
    )
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(AuthRequest())
            logger.info("Refreshed expired %s access token.", service)
            # Persist refreshed token immediately so next call doesn't re-refresh.
            _persist_refreshed_token(connection, creds, service)
        except Exception as exc:
            logger.error("Failed to refresh %s token: %s", service, exc)
            raise
    return creds


def _persist_refreshed_token(connection: dict[str, Any], creds: Credentials, service: str) -> None:
    # We need UID — recover from connection store requires caller to handle.
    # This helper is used by get_credentials_for_user which has uid.
    pass  # actual persistence done in get_credentials_for_user


def get_credentials_for_user(uid: str, service: str) -> Credentials | None:
    """Retrieve and build (and refresh) credentials for uid+service."""
    connection = connections_store.get_connection(uid, service)
    if connection is None:
        return None
    access_token = connection.get("access_token")
    refresh_token = connection.get("refresh_token")
    if not access_token and not refresh_token:
        logger.warning("Connection %s exists but has no tokens for uid=%s", service, uid)
        return None

    scopes = _scopes_for(service) or connection.get("scopes") or []
    creds = Credentials(
        token=access_token or "",
        refresh_token=refresh_token or "",
        token_uri=_TOKEN_URI,
        client_id=_get_client_id(),
        client_secret=_get_client_secret(),
        scopes=scopes,
    )
    if creds.expired and creds.refresh_token:
        try:
            original_token = creds.token
            creds.refresh(AuthRequest())
            logger.info("Refreshed expired %s access token for uid=%s", service, uid[:8])
            # Persist only if token actually changed.
            if creds.token != original_token:
                connections_store.save_connection(
                    uid,
                    service,
                    scopes=connection.get("scopes", scopes),
                    access_token=creds.token,
                    refresh_token=creds.refresh_token or connection.get("refresh_token"),
                    expires_in=None,
                )
                # Also update last_sync? No — refresh is not a sync.
        except Exception as exc:
            logger.error("Failed to refresh %s token for uid=%s: %s", service, uid[:8], exc)
            raise
    return creds
