"""Google Maps Platform service — Geocoding + Directions via server-side API key.

Maps does NOT use per-user OAuth. The API key is server-only, never exposed
to the frontend. Frontend calls POST /api/maps/geocode etc. which proxy here.

APIs used (all via https://maps.googleapis.com):
 - Geocoding API: address -> lat/lng + formatted_address
 - Directions API: origin/destination -> distance/duration
 - Distance Matrix API (optional fallback): same as directions for duration

Cost: ~$5/1000 requests; free tier $200/mo. MVP caches results 1h.
"""

from __future__ import annotations

import os
import logging
import time
from typing import Any
import requests  # already used by google_auth; available in backend deps

logger = logging.getLogger(__name__)

_GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"
_DIRECTIONS_URL = "https://maps.googleapis.com/maps/api/directions/json"
_DISTANCE_MATRIX_URL = "https://maps.googleapis.com/maps/api/distancematrix/json"

# Simple in-memory cache: key -> (expiry_epoch, value)
_cache: dict[str, tuple[float, Any]] = {}
_CACHE_TTL = 3600  # 1 hour


def _get_api_key() -> str:
    return (os.getenv("GOOGLE_MAPS_API_KEY") or "").strip()


def is_configured() -> bool:
    return bool(_get_api_key())


def _cached(key: str) -> Any | None:
    entry = _cache.get(key)
    if not entry:
        return None
    expiry, value = entry
    if time.time() > expiry:
        _cache.pop(key, None)
        return None
    return value


def _store(key: str, value: Any) -> None:
    _cache[key] = (time.time() + _CACHE_TTL, value)


def geocode_address(address: str) -> dict[str, Any]:
    """Geocode a single address string.

    Returns: { formatted_address, lat, lng, place_id } or raises RuntimeError.
    Requires GOOGLE_MAPS_API_KEY.
    """
    address = address.strip()
    if not address:
        raise ValueError("Address is empty.")
    api_key = _get_api_key()
    if not api_key:
        raise RuntimeError("Google Maps API key is not configured. Set GOOGLE_MAPS_API_KEY.")

    cache_key = f"geocode:{address.lower()}"
    cached = _cached(cache_key)
    if cached is not None:
        return cached

    try:
        resp = requests.get(
            _GEOCODE_URL,
            params={"address": address, "key": api_key},
            timeout=10,
        )
        data = resp.json()
    except Exception as exc:
        raise RuntimeError(f"Maps Geocoding request failed: {exc}") from exc

    status = data.get("status")
    if status != "OK":
        err = data.get("error_message") or status
        if status in ("OVER_QUERY_LIMIT", "REQUEST_DENIED"):
            raise RuntimeError(f"Maps Geocoding error ({status}): {err}")
        if status == "ZERO_RESULTS":
            raise RuntimeError(f"No results for address: {address}")
        raise RuntimeError(f"Maps Geocoding failed: {err}")

    results = data.get("results") or []
    if not results:
        raise RuntimeError(f"No results for address: {address}")

    first = results[0]
    geometry = first.get("geometry") or {}
    location = geometry.get("location") or {}
    out = {
        "formatted_address": first.get("formatted_address") or address,
        "lat": location.get("lat"),
        "lng": location.get("lng"),
        "place_id": first.get("place_id") or "",
    }
    _store(cache_key, out)
    return out


def get_directions(
    origin: str,
    destination: str,
    mode: str = "driving",
) -> dict[str, Any]:
    """Get directions between origin and destination.

    mode: driving, walking, bicycling, transit
    Returns: { distance_text, distance_meters, duration_text, duration_seconds, polyline? }
    """
    origin = origin.strip()
    destination = destination.strip()
    if not origin or not destination:
        raise ValueError("Origin and destination are required.")
    if mode not in ("driving", "walking", "bicycling", "transit"):
        mode = "driving"
    api_key = _get_api_key()
    if not api_key:
        raise RuntimeError("Google Maps API key is not configured. Set GOOGLE_MAPS_API_KEY.")

    cache_key = f"directions:{origin.lower()}|{destination.lower()}|{mode}"
    cached = _cached(cache_key)
    if cached is not None:
        return cached

    try:
        resp = requests.get(
            _DIRECTIONS_URL,
            params={"origin": origin, "destination": destination, "mode": mode, "key": api_key},
            timeout=10,
        )
        data = resp.json()
    except Exception as exc:
        raise RuntimeError(f"Maps Directions request failed: {exc}") from exc

    status = data.get("status")
    if status != "OK":
        err = data.get("error_message") or status
        if status in ("OVER_QUERY_LIMIT", "REQUEST_DENIED"):
            raise RuntimeError(f"Maps Directions error ({status}): {err}")
        if status in ("ZERO_RESULTS", "NOT_FOUND"):
            raise RuntimeError(f"No route between {origin} and {destination}")
        raise RuntimeError(f"Maps Directions failed: {err}")

    routes = data.get("routes") or []
    if not routes:
        raise RuntimeError("No route found.")
    legs = (routes[0].get("legs") or [])
    if not legs:
        raise RuntimeError("No legs in route.")

    leg = legs[0]
    distance = leg.get("distance") or {}
    duration = leg.get("duration") or {}
    out = {
        "origin": origin,
        "destination": destination,
        "mode": mode,
        "distance_text": distance.get("text") or "",
        "distance_meters": distance.get("value") or 0,
        "duration_text": duration.get("text") or "",
        "duration_seconds": duration.get("value") or 0,
    }
    _store(cache_key, out)
    return out


def get_travel_time(origin: str, destination: str, mode: str = "driving") -> dict[str, Any]:
    """Alias for get_directions — returns same payload."""
    return get_directions(origin, destination, mode=mode)
