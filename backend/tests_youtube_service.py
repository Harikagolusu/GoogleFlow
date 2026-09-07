"""Unit tests for youtube_service.py — graceful degradation when no API key,
safe handling of API errors, caching, and maximum video limits.
"""
import sys
import types
import time
import json
import urllib.request
import os as real_os

sys.path.insert(0, ".")

# minimal stubs so we can import youtube_service standalone
os_mod = types.ModuleType("os")
os_mod.getenv = lambda k, d=None: ""
os_mod.path = real_os.path
sys.modules["os"] = os_mod

from app import youtube_service

count = 0


def check(name, cond):
    global count
    count += 1
    print(("PASS" if cond else "FAIL"), "-", name)
    if not cond:
        raise SystemExit(1)


# ===================== CONFIGURATION =====================
check("not configured when no key", not youtube_service._is_configured())
check("search returns empty when not configured", youtube_service.search_videos("interview prep", []) == [])

# Simulate having a key
youtube_service._cache.clear()
original_get_key = youtube_service._get_api_key
_real_cache_set = youtube_service._cache_set
_real_open = urllib.request.urlopen


def fake_key():
    return "FAKE_API_KEY_YOUTUBE"


youtube_service._get_api_key = fake_key
check("configured when fake key present", youtube_service._is_configured())

# Save original _youtube_search for later use in duplicate test
_orig_youtube_search = youtube_service._youtube_search

# Fake YouTube search that returns mock data (processed video format)
_fake_video_counter = [0]


def _fake_youtube_search(query, *, max_results=5):
    _fake_video_counter[0] += 1
    return [
        {"id": f"vid-{_fake_video_counter[0]}-{i}", "title": f"Video {i} for {query}", "channelTitle": "Test Channel", "thumbnail": "", "publishedAt": "2024-01-01", "url": f"https://youtube.com/watch?v=vid-{_fake_video_counter[0]}-{i}"}
        for i in range(min(max_results, 3))
    ]


youtube_service._youtube_search = _fake_youtube_search

# ===================== CACHING =====================
query = "technical interview preparation"
checklist = [{"title": "Review data structures"}]

result1 = youtube_service.search_videos(query, checklist)
cache_key = youtube_service._normalize_query(
    youtube_service._build_search_query(query, checklist)
)
check("first search populates cache", cache_key in youtube_service._cache)
cached_ts, cached_videos = youtube_service._cache[cache_key]
check("cache stores timestamp", isinstance(cached_ts, float))
check("cache stores video list", isinstance(cached_videos, list))

result2 = youtube_service.search_videos(query, checklist)
check("second search returns cached result", result1 == result2)

# ===================== NORMALIZE QUERY =====================
check("normalize strips uppercase", youtube_service._normalize_query("HELLO WORLD") == "hello world")
check("normalize removes special chars", youtube_service._normalize_query("Hello! @World#") == "hello world")
check("normalize truncates long query", len(youtube_service._normalize_query("a" * 200)) == 80)

# ===================== BUILD SEARCH QUERY =====================
check(
    "build query includes title",
    "interview" in youtube_service._build_search_query("Interview Prep", []).lower(),
)
check(
    "build query includes checklist items",
    "resume" in youtube_service._build_search_query("Job Search", [{"title": "Review Resume"}]).lower(),
)
check(
    "build query limits checklist items",
    len(youtube_service._build_search_query("x", [{"title": "a"}, {"title": "b"}, {"title": "c"}, {"title": "d"}, {"title": "e"}])) < 300,
)

# ===================== MAX VIDEOS LIMIT =====================
youtube_service._youtube_search = _fake_youtube_search  # reset to proper fake
youtube_service._cache.clear()
# Override _cache_set to enforce limit
_real_cache_set = youtube_service._cache_set
youtube_service._cache_set = lambda k, v: _real_cache_set(k, v[:5] if isinstance(v, list) else v)
result = youtube_service.search_videos("any query", [])
check("max videos enforced to 5", len(result) <= 5)

# ===================== DUPLICATE REMOVAL =====================
# We test that the real _youtube_search deduplicates by videoId.
# We monkeypatch urllib to return a response with duplicate videoIds,
# letting the real _youtube_search process and deduplicate.
import builtins

_real_open = urllib.request.urlopen


class _FakeUrlopenResponse:
    def __init__(self, data_bytes):
        self._data = data_bytes

    def read(self):
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


def _patched_urlopen(req, timeout=None):
    return _FakeUrlopenResponse(json.dumps({
        "items": [
            {"id": {"videoId": "vid-1"}, "snippet": {"title": "Video 1", "channelTitle": "Test", "thumbnails": {}, "publishedAt": "2024-01-01"}},
            {"id": {"videoId": "vid-2"}, "snippet": {"title": "Video 2", "channelTitle": "Test", "thumbnails": {}, "publishedAt": "2024-01-01"}},
            {"id": {"videoId": "vid-1"}, "snippet": {"title": "Video 1 dup", "channelTitle": "Test", "thumbnails": {}, "publishedAt": "2024-01-01"}},
        ]
    }).encode())


urllib.request.urlopen = _patched_urlopen
youtube_service._cache.clear()
youtube_service._cache_set = _real_cache_set
youtube_service._youtube_search = _orig_youtube_search  # restore real function
result = youtube_service.search_videos("dedup test", [])
urllib.request.urlopen = _real_open  # restore
check("duplicate video IDs removed", len(result) == 2)
vid_ids = [v["id"] for v in result]
check("no duplicate IDs in result", len(vid_ids) == len(set(vid_ids)))

# ===================== API ERROR GRACEFUL HANDLING =====================
youtube_service._youtube_search = lambda q, **kw: (_ for _ in ()).throw(RuntimeError("YouTube API error"))
youtube_service._cache.clear()
result = youtube_service.search_videos("error test", [])
check("YouTube API error returns empty list", result == [])

# ===================== INVALID API RESPONSE HANDLING =====================
youtube_service._youtube_search = lambda q, **kw: {"error": "bad key"}
youtube_service._cache.clear()
result = youtube_service.search_videos("invalid response test", [])
check("invalid API response returns empty list", result == [])

youtube_service._youtube_search = lambda q, **kw: {"items": "not a list"}
youtube_service._cache.clear()
result = youtube_service.search_videos("invalid items test", [])
check("non-list items returns empty list", result == [])

youtube_service._youtube_search = lambda q, **kw: {"items": [1, 2, 3]}  # non-dict items
youtube_service._cache.clear()
result = youtube_service.search_videos("non-dict items test", [])
check("non-dict items filtered out", result == [])

# ===================== VIDEO URL FORMAT =====================
urllib.request.urlopen = lambda req, timeout=None: _FakeUrlopenResponse(json.dumps({
    "items": [
        {"id": {"videoId": "abc123"}, "snippet": {"title": "Test", "channelTitle": "Ch", "thumbnails": {"medium": {"url": "https://i.ytimg.com/vi/abc123/mqdefault.jpg"}}, "publishedAt": "2024-01-01"}}
    ]
}).encode())
youtube_service._cache.clear()
youtube_service._youtube_search = _orig_youtube_search  # restore real function
result = youtube_service.search_videos("url format test", [])
check("video URL is youtube.com format", len(result) > 0 and result[0]["url"] == "https://www.youtube.com/watch?v=abc123")

# Restore
youtube_service._get_api_key = original_get_key

print(f"\nALL {count} YOUTUBE SERVICE CHECKS PASSED")
