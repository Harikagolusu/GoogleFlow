"""YouTube Data API v3 integration for video recommendations.

Security:
    - YOUTUBE_API_KEY lives ONLY in the backend environment (backend/.env).
    - It is never shipped to or read from the frontend.
    - No OAuth tokens are involved — a simple API key is used.

Behavior:
    - When YOUTUBE_API_KEY is configured, searches YouTube for relevant videos.
    - When the key is missing, all functions return empty results gracefully.
    - Results are cached in memory per normalized query (15-minute TTL).
    - Maximum 5 relevant videos are returned per workflow.
"""

from __future__ import annotations

import json
import os
import time
import logging
from typing import Any

logger = logging.getLogger(__name__)

_MAX_VIDEOS = 5
_CACHE_TTL_SECONDS = 900  # 15 minutes

_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}


def _get_api_key() -> str:
    return os.getenv("YOUTUBE_API_KEY", "").strip()


def _is_configured() -> bool:
    key = _get_api_key()
    return bool(key) and key != "your_youtube_api_key_here"


def _normalize_query(query: str) -> str:
    import re
    query = query.lower().strip()
    query = re.sub(r"[^a-z0-9\s]", " ", query)
    query = re.sub(r"\s+", " ", query).strip()
    return query[:80]


def _build_search_query(workflow_title: str, checklist: list[dict[str, Any]]) -> str:
    """Build a YouTube search query from workflow title + checklist items.

    Title provides the core topic (e.g. "Software Engineer Interview Preparation").
    Checklist items are action reminders — we skip them entirely since they
    contain meta-instructions (confirm, review, prepare) rather than topic keywords.
    """
    import re

    def _strip_title(text: str) -> str:
        text = re.sub(r'\b(TechVista|Confluent|Amazon|Google|Microsoft|Meta|Apple|Netflix|Uber|Airbnb|LinkedIn|Indeed|Cutshort|Glassdoor|HackerRank|LeetCode|InterviewBit|IIT|IIIT|NIT)\b', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b', '', text)
        text = re.sub(r'\b\d{1,2}\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4}\b', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\b(AM|PM|IST|PST|EST|GMT|UTC)\b', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\b(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\b', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\b(confirm|accept|review|prepare|check|verify|submit|complete|finish|read|refresh)\b', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\b(calendar|invitation|email|mail|message|drive|file|document|pdf)\b', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\b(google|meet|zoom|teams|webex|conference|audio|video|equipment)\b', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    title_words = _strip_title(workflow_title)
    title_parts = [w for w in title_words.split() if len(w) > 2]
    combined = ' '.join(title_parts[:5])
    return combined[:80]


def _cache_get(key: str) -> list[dict[str, Any]] | None:
    if key not in _cache:
        return None
    timestamp, videos = _cache[key]
    if time.time() - timestamp > _CACHE_TTL_SECONDS:
        del _cache[key]
        return None
    return videos


def _cache_set(key: str, videos: list[dict[str, Any]]) -> None:
    _cache[key] = (time.time(), list(videos))


def search_videos(
    workflow_title: str,
    checklist: list[dict[str, Any]],
    max_results: int = _MAX_VIDEOS,
) -> list[dict[str, Any]]:
    """Search YouTube for relevant video recommendations.

    Args:
        workflow_title: The LifeFlow title.
        checklist: List of checklist item dicts with 'title' keys.
        max_results: Maximum number of videos to return (default 5).

    Returns:
        List of video dicts with: id, title, channelTitle, thumbnail,
        publishedAt, url. Returns empty list when YouTube API is unavailable.
    """
    if not _is_configured():
        return []

    cache_key = _normalize_query(_build_search_query(workflow_title, checklist))
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached[:max_results]

    try:
        videos = _youtube_search(cache_key, max_results=_MAX_VIDEOS)
        _cache_set(cache_key, videos)
        return videos[:max_results]
    except Exception as exc:
        logger.warning("YouTube search failed: %s", exc)
        return []


def _youtube_search(query: str, max_results: int = _MAX_VIDEOS) -> list[dict[str, Any]]:
    """Execute a YouTube Data API v3 search.

    Only public metadata is returned: videoId, title, channelTitle, thumbnail, publishedAt.
    No authentication required — API key is sent server-side only.
    """
    import urllib.parse
    import urllib.request

    api_key = _get_api_key()
    encoded_query = urllib.parse.quote(query)

    url = (
        f"https://www.googleapis.com/youtube/v3/search"
        f"?part=snippet"
        f"&q={encoded_query}"
        f"&type=video"
        f"&videoDuration=medium"
        f"&maxResults={max_results}"
        f"&key={api_key}"
    )

    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as response:
        data = json.loads(response.read().decode())

    items = data.get("items", []) if isinstance(data, dict) else []
    if not isinstance(items, list):
        return []

    results: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for item in items:
        if not isinstance(item, dict):
            continue
        snippet = item.get("snippet") or {}
        video_id = item.get("id", {}).get("videoId", "") if isinstance(item.get("id"), dict) else ""
        if not video_id or video_id in seen_ids:
            continue
        seen_ids.add(video_id)

        thumbnails = snippet.get("thumbnails", {}) or {}
        thumb = (
            thumbnails.get("medium", {})
            or thumbnails.get("high", {})
            or thumbnails.get("default", {})
        )
        thumb_url = thumb.get("url", "") if isinstance(thumb, dict) else ""

        published = snippet.get("publishedAt", "") or ""

        results.append({
            "id": video_id,
            "title": snippet.get("title", "Untitled"),
            "channelTitle": snippet.get("channelTitle", ""),
            "thumbnail": thumb_url,
            "publishedAt": published,
            "url": f"https://www.youtube.com/watch?v={video_id}",
        })

    return results
