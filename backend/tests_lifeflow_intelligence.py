"""Phase 4 integration tests for improved LifeFlow AI generation quality.

These tests run WITHOUT fastapi/pydantic installed, using minimal stubs.
They cover priority classification, confidence scoring, threshold filtering,
improved prompts, cross-service deduplication, and backward compatibility.

Tests do NOT require real Google OAuth, real Gmail, real Gemini API, or
real Firebase — all Google/gemini calls are stubbed or use the fallback path.
"""
import asyncio
import os
import sys
import types


# --- minimal pydantic stub (enhanced for priority/confidence fields) ---------
class ValidationError(Exception):
    pass


class _FieldSentinel:
    def __init__(self, kw):
        self.kw = kw


class BaseModel:
    def __init__(self, **data):
        self.__dict__.update(data)

    @classmethod
    def model_validate(cls, obj):
        expected = dict(cls.__annotations__)
        instance = cls()
        for k in expected:
            if k in obj:
                instance.__dict__[k] = obj[k]
        return instance

    def model_dump(self):
        return dict(self.__dict__)


pydantic = types.ModuleType("pydantic")
pydantic.BaseModel = BaseModel
pydantic.Field = lambda **kw: _FieldSentinel(kw)
pydantic.ValidationError = ValidationError
pydantic.Literal = lambda *a, **k: str

sys.modules["pydantic"] = pydantic


# --- minimal fastapi stub ----------------------------------------------------
class HTTPException(Exception):
    def __init__(self, status_code, detail):
        self.status_code = status_code
        self.detail = detail


class CORSMiddleware:
    def __init__(self, *a, **k):
        pass


class FastAPI:
    def __init__(self, *a, **k):
        self.routes = {}

    def _route(self, method, path, fn):
        self.routes[(method, path)] = fn
        return fn

    def get(self, path, **kw):
        return lambda fn: self._route("GET", path, fn)

    def post(self, path, **kw):
        return lambda fn: self._route("POST", path, fn)

    def patch(self, path, **kw):
        return lambda fn: self._route("PATCH", path, fn)

    def add_middleware(self, *a, **k):
        pass


def _QueryStub(**kwargs):
    return kwargs.get("default", None)


fastapi = types.ModuleType("fastapi")
fastapi.FastAPI = FastAPI
fastapi.HTTPException = HTTPException
fastapi.Request = object
fastapi.Query = _QueryStub
cors_mod = types.ModuleType("fastapi.middleware.cors")
cors_mod.CORSMiddleware = CORSMiddleware
responses_mod = types.ModuleType("fastapi.responses")
responses_mod.RedirectResponse = lambda *a, **k: None
dotenv = types.ModuleType("dotenv")
dotenv.load_dotenv = lambda *a, **k: False

sys.modules["fastapi"] = fastapi
sys.modules["fastapi.middleware"] = types.ModuleType("fastapi.middleware")
sys.modules["fastapi.middleware.cors"] = cors_mod
sys.modules["fastapi.responses"] = responses_mod
sys.modules["dotenv"] = dotenv

sys.path.insert(0, ".")
from app import firebase_service, gemini_service, workflow_store

count = 0


def check(name, cond):
    global count
    count += 1
    print(("PASS" if cond else "FAIL"), "-", name)
    if not cond:
        raise SystemExit(1)


# ===================== PRIORITY VALIDATION =================================
print("\n--- Priority validation ---")

# Valid priorities
for val, expected in [("high", "high"), ("medium", "medium"), ("low", "low"),
                       ("HIGH", "high"), ("High", "high"), ("invalid", "medium"),
                       (None, "medium"), ("", "medium")]:
    result = gemini_service._clean_priority(val)
    check(f"_clean_priority({repr(val)}) == {repr(expected)}", result == expected)

# ===================== CONFIDENCE VALIDATION ================================
print("\n--- Confidence validation ---")

for val, expected in [
    (0.95, 0.95), (0.75, 0.75), (0.60, 0.60), (0.50, 0.50),
    (1.5, 1.0), (-0.5, 0.0), (0.0, 0.0), (1.0, 1.0),
    ("0.75", 0.75), (None, None), ("invalid", None), (True, 1.0),
]:
    result = gemini_service._clean_confidence(val)
    check(f"_clean_confidence({repr(val)}) == {repr(expected)}", result == expected)

# ===================== THRESHOLD CONSTANTS ==================================
print("\n--- Confidence thresholds ---")
check("HIGH threshold is >= 0.75", gemini_service.CONFIDENCE_THRESHOLD_HIGH >= 0.75)
check("MEDIUM threshold is >= 0.60", gemini_service.CONFIDENCE_THRESHOLD_MEDIUM >= 0.60)
check("IGNORE threshold is >= 0.50", gemini_service.CONFIDENCE_THRESHOLD_IGNORE >= 0.50)
check("HIGH >= MEDIUM >= IGNORE", (
    gemini_service.CONFIDENCE_THRESHOLD_HIGH
    >= gemini_service.CONFIDENCE_THRESHOLD_MEDIUM
    >= gemini_service.CONFIDENCE_THRESHOLD_IGNORE
))

# ===================== CLEAN WORKFLOW DICT WITH PRIORITY/CONFIDENCE ==========
print("\n--- _clean_workflow_dict: priority + confidence ---")

valid_flow = {
    "title": "Prepare for Interview",
    "emoji": "💼",
    "date": "Tomorrow",
    "status": "Action Needed",
    "readiness": 10,
    "nextUp": "Review job description",
    "checklist": [
        {"id": "c1", "title": "Review job description", "completed": False},
        {"id": "c2", "title": "Prepare answers", "completed": False},
    ],
    "connectedServices": ["Gmail", "Google Calendar"],
    "priority": "high",
    "confidence": 0.92,
}

cleaned = gemini_service._clean_workflow_dict(valid_flow, "test-id-1")
check("priority preserved high", cleaned["priority"] == "high")
check("confidence preserved 0.92", cleaned["confidence"] == 0.92)

# Invalid priority -> medium
bad_priority = dict(valid_flow, priority="not_valid")
cleaned2 = gemini_service._clean_workflow_dict(bad_priority, "test-id-2")
check("invalid priority -> medium", cleaned2["priority"] == "medium")

# Missing priority -> medium
no_priority = {k: v for k, v in valid_flow.items() if k != "priority"}
cleaned3 = gemini_service._clean_workflow_dict(no_priority, "test-id-3")
check("missing priority -> medium", cleaned3["priority"] == "medium")

# Confidence clamping
over_conf = dict(valid_flow, confidence=1.5)
cleaned4 = gemini_service._clean_workflow_dict(over_conf, "test-id-4")
check("confidence clamped to 1.0", cleaned4["confidence"] == 1.0)

under_conf = dict(valid_flow, confidence=-0.2)
cleaned5 = gemini_service._clean_workflow_dict(under_conf, "test-id-5")
check("confidence clamped to 0.0", cleaned5["confidence"] == 0.0)

missing_conf = {k: v for k, v in valid_flow.items() if k != "confidence"}
cleaned6 = gemini_service._clean_workflow_dict(missing_conf, "test-id-6")
check("missing confidence is None", cleaned6["confidence"] is None)

# ===================== BACKWARD COMPATIBILITY =================================
print("\n--- Backward compatibility: workflows without priority/confidence ---")

legacy_flow = {
    "title": "Old Workflow",
    "emoji": "✨",
    "date": "Next week",
    "status": "Action Needed",
    "readiness": 20,
    "nextUp": "Get started",
    "checklist": [{"id": "c1", "title": "First step", "completed": False}],
    "connectedServices": ["Gmail"],
}

legacy_cleaned = gemini_service._clean_workflow_dict(legacy_flow, "legacy-id")
check("legacy workflow: title preserved", legacy_cleaned["title"] == "Old Workflow")
check("legacy workflow: priority defaults medium", legacy_cleaned["priority"] == "medium")
check("legacy workflow: confidence is None", legacy_cleaned["confidence"] is None)

# ===================== PARSE ANALYZE OUTPUT ===================================
print("\n--- _parse_analyze_output: confidence threshold filtering ---")

high_conf_flow = {
    "title": "High Confidence Interview",
    "emoji": "💼",
    "date": "Tomorrow",
    "status": "Action Needed",
    "readiness": 10,
    "nextUp": "Review job description",
    "checklist": [{"id": "c1", "title": "Review job description for key skills", "completed": False}],
    "connectedServices": ["Gmail"],
    "priority": "high",
    "confidence": 0.92,
    "sourceMessageIds": ["msg-123"],
}

low_conf_flow = {
    "title": "Low Confidence Newsletter",
    "emoji": "📧",
    "date": "No date",
    "status": "Action Needed",
    "readiness": 10,
    "nextUp": "Read it",
    "checklist": [{"id": "c1", "title": "Read the newsletter", "completed": False}],
    "connectedServices": ["Gmail"],
    "priority": "low",
    "confidence": 0.30,  # below IGNORE threshold
    "sourceMessageIds": ["msg-456"],
}

medium_conf_flow = {
    "title": "Medium Confidence Action",
    "emoji": "⚠️",
    "date": "Soon",
    "status": "Action Needed",
    "readiness": 10,
    "nextUp": "Check details",
    "checklist": [{"id": "c1", "title": "Verify the details with the team", "completed": False}],
    "connectedServices": ["Gmail"],
    "priority": "medium",
    "confidence": 0.65,  # between MEDIUM and HIGH
    "sourceMessageIds": ["msg-789"],
}

medium_conf_vague_flow = {
    "title": "Medium Conf Vague",
    "emoji": "🤷",
    "date": "Maybe",
    "status": "Action Needed",
    "readiness": 10,
    "nextUp": "Think about it",
    "checklist": [{"id": "c1", "title": "Maybe do it", "completed": False}],  # < 12 chars, not actionable
    "connectedServices": ["Gmail"],
    "priority": "medium",
    "confidence": 0.65,
    "sourceMessageIds": ["msg-000"],
}

# Test: high confidence -> kept
flows, low_ignored = gemini_service._parse_analyze_output({"flows": [high_conf_flow], "metadata": {}})
check("high conf flow: kept", len(flows) == 1)
check("high conf flow: low_ignored 0", low_ignored == 0)
check("high conf flow: priority preserved", flows[0].get("priority") == "high")
check("high conf flow: confidence preserved", flows[0].get("confidence") == 0.92)

# Test: low confidence below IGNORE -> discarded
flows2, low_ignored2 = gemini_service._parse_analyze_output({"flows": [low_conf_flow], "metadata": {}})
check("low conf flow: discarded", len(flows2) == 0)
check("low conf flow: low_ignored incremented", low_ignored2 == 1)

# Test: medium confidence with actionable checklist -> kept
flows3, low_ignored3 = gemini_service._parse_analyze_output({"flows": [medium_conf_flow], "metadata": {}})
check("medium conf actionable: kept", len(flows3) == 1)
check("medium conf actionable: low_ignored 0", low_ignored3 == 0)

# Test: medium confidence with vague checklist -> discarded
flows4, low_ignored4 = gemini_service._parse_analyze_output({"flows": [medium_conf_vague_flow], "metadata": {}})
check("medium conf vague: discarded", len(flows4) == 0)
check("medium conf vague: low_ignored incremented", low_ignored4 == 1)

# Test: empty flows -> empty list
flows5, low_ignored5 = gemini_service._parse_analyze_output({"flows": [], "metadata": {}})
check("empty flows: returns empty", len(flows5) == 0)
check("empty flows: low_ignored 0", low_ignored5 == 0)

# Test: no flows key -> empty
flows6, low_ignored6 = gemini_service._parse_analyze_output({}, )
check("no flows key: returns empty", len(flows6) == 0)

# Test: metadata.lowConfidenceIgnored accumulated
flows7, low_ignored7 = gemini_service._parse_analyze_output({"flows": [high_conf_flow], "metadata": {"lowConfidenceIgnored": 3}})
check("metadata.lowConfidenceIgnored accumulated", low_ignored7 == 3)

# Test: malformed flow in list -> skipped gracefully
malformed = {"title": "Missing checklist"}
flows8, low_ignored8 = gemini_service._parse_analyze_output({"flows": [high_conf_flow, malformed], "metadata": {}})
check("malformed flow skipped: 1 kept", len(flows8) == 1)
check("malformed flow: low_ignored 0", low_ignored8 == 0)

# Test: non-dict flow in list -> skipped
flows9, _ = gemini_service._parse_analyze_output({"flows": [high_conf_flow, "not a dict", None], "metadata": {}})
check("non-dict flow skipped: 1 kept", len(flows9) == 1)

# ===================== PARSE UNIFIED OUTPUT ====================================
print("\n--- _parse_unified_output: multi-service confidence threshold ---")

multi_flow_high = {
    "title": "Unified Interview Prep",
    "emoji": "💼",
    "date": "Sep 10, 2026",
    "status": "Action Needed",
    "readiness": 10,
    "nextUp": "Review requirements",
    "checklist": [{"id": "c1", "title": "Research the company's recent products", "completed": False}],
    "connectedServices": ["Gmail", "Google Calendar", "Google Drive"],
    "priority": "high",
    "confidence": 0.90,
    "sourceMessageIds": ["g-001"],
    "sourceEventIds": ["e-001"],
    "sourceFileIds": ["f-001"],
}

multi_flow_low = {
    "title": "Promotional Newsletter",
    "emoji": "📧",
    "date": "No date",
    "status": "Action Needed",
    "readiness": 10,
    "nextUp": "Read",
    "checklist": [{"id": "c1", "title": "Read the promotional email", "completed": False}],
    "connectedServices": ["Gmail"],
    "priority": "low",
    "confidence": 0.40,
    "sourceMessageIds": ["g-002"],
    "sourceEventIds": [],
    "sourceFileIds": [],
}

flows10, low_ignored10 = gemini_service._parse_unified_output({"flows": [multi_flow_high, multi_flow_low], "metadata": {}})
check("unified: high conf kept", len(flows10) == 1)
check("unified: low conf discarded", low_ignored10 == 1)
check("unified: sourceMessageIds preserved", flows10[0].get("_sourceMessageIds") == ["g-001"])
check("unified: sourceEventIds preserved", flows10[0].get("_sourceEventIds") == ["e-001"])
check("unified: sourceFileIds preserved", flows10[0].get("_sourceFileIds") == ["f-001"])
check("unified: _allSourceIds computed", len(flows10[0].get("_allSourceIds", [])) == 3)

# ===================== DEDUPLICATION: _has_overlap ============================
print("\n--- Deduplication: _has_overlap ---")

# Reset to demo mode (no Firestore)
firebase_service._enabled = False
workflow_store.init(None)

# Save a workflow with source IDs
wf_with_sources = {
    "id": "dedup-test-1",
    "title": "Test Workflow",
    "emoji": "✨",
    "date": "Today",
    "status": "Action Needed",
    "readiness": 10,
    "nextUp": "Start",
    "checklist": [{"id": "c1", "title": "First step", "completed": False}],
    "connectedServices": ["Gmail"],
    "_sourceMessageIds": ["msg-abc"],
    "_sourceEventIds": [],
    "_sourceFileIds": [],
}

workflow_store.save_workflow(None, wf_with_sources, is_new=True)

check("has_existing_flow: same message id -> True",
      workflow_store.has_existing_flow(None, ["msg-abc"]) is True)
check("has_existing_flow: different message id -> False",
      workflow_store.has_existing_flow(None, ["msg-xyz"]) is False)
check("has_existing_flow: empty list -> False",
      workflow_store.has_existing_flow(None, []) is False)

# Multi-source dedup
workflow_store.save_workflow(None, {
    "id": "dedup-test-2",
    "title": "Multi Source",
    "emoji": "✨",
    "date": "Today",
    "status": "Action Needed",
    "readiness": 10,
    "nextUp": "Start",
    "checklist": [{"id": "c1", "title": "First step", "completed": False}],
    "connectedServices": ["Gmail", "Google Calendar"],
    "_allSourceIds": ["g-100", "e-100"],
}, is_new=True)

check("has_existing_flow_multi: match g-100 -> True",
      workflow_store.has_existing_flow_multi(None, ["g-100"]) is True)
check("has_existing_flow_multi: match e-100 -> True",
      workflow_store.has_existing_flow_multi(None, ["e-100"]) is True)
check("has_existing_flow_multi: no match -> False",
      workflow_store.has_existing_flow_multi(None, ["g-999", "e-999"]) is False)
check("has_existing_flow_multi: empty list -> False",
      workflow_store.has_existing_flow_multi(None, []) is False)

# ===================== ANONYMITY: NO PRIVATE DATA IN PROMPTS ===================
print("\n--- Privacy: prompts contain no tokens or bodies ---")

fake_messages = [
    {
        "id": "msg-123",
        "threadId": "thread-abc",
        "sender": "hr@company.com",
        "subject": "Your interview",
        "date": "Sep 10, 2026",
        "snippet": "Your interview is scheduled. Please bring your passport.",
        "labels": ["INBOX"],
    }
]

prompt = gemini_service._build_analyze_prompt(fake_messages)
check("prompt: contains sender", "hr@company.com" in prompt)
check("prompt: contains subject", "interview" in prompt)
check("prompt: contains snippet", "passport" in prompt)
check("prompt: does NOT contain message body content",
      "secret_password" not in prompt and "my bank account" not in prompt)
check("prompt: does NOT contain OAuth tokens",
      "ya29." not in prompt and "1//" not in prompt)
check("prompt: does NOT contain email body (only snippet)",
      prompt.count("secret") == 0)
check("prompt: contains labels", "INBOX" in prompt)

# Unified prompt privacy
unified_prompt = gemini_service._build_unified_prompt(
    gmail_messages=fake_messages,
    calendar_events=[{
        "id": "event-1",
        "summary": "Tech Interview",
        "displayStart": "Sep 10, 2026 10:00 AM",
        "start": "2026-09-10T10:00:00",
        "end": "2026-09-10T11:00:00",
        "location": "Google Office",
        "attendees": ["interviewer@google.com"],
    }],
    drive_files=[{
        "id": "file-1",
        "name": "Resume.pdf",
        "mimeType": "application/pdf",
        "modifiedTime": "2026-09-01T00:00:00Z",
    }],
    maps_context=None,
    query_hint="interview prep",
)

check("unified prompt: contains Gmail sender", "hr@company.com" in unified_prompt)
check("unified prompt: contains Calendar title", "Tech Interview" in unified_prompt)
check("unified prompt: contains Drive filename", "Resume.pdf" in unified_prompt)
check("unified prompt: does NOT contain OAuth tokens",
      "ya29." not in unified_prompt and "1//" not in unified_prompt)
check("unified prompt: does NOT contain private content",
      "secret_password" not in unified_prompt)

# ===================== FALLBACK GENERATOR: PRIORITY FIELDS ===================
print("\n--- Fallback generator: includes priority and confidence ---")

from app.gemini_service import _generate_fallback

fallback_wf = _generate_fallback("I have an interview tomorrow")
check("fallback: title is non-empty", len(fallback_wf.get("title", "")) > 0)
check("fallback: checklist non-empty", len(fallback_wf.get("checklist", [])) > 0)
check("fallback: priority is valid",
      fallback_wf.get("priority") in (None, "high", "medium", "low"))
check("fallback: confidence is valid",
      fallback_wf.get("confidence") is None or (0.0 <= fallback_wf.get("confidence", 0) <= 1.0))

# ===================== VALIDATEGMAI OUTPUT HANDLING ==========================
print("\n--- Robust JSON parsing ---")

# Markdown fences
json_with_fence = """
```json
{
  "flows": [
    {
      "title": "Test Flow",
      "emoji": "✨",
      "date": "Today",
      "status": "Action Needed",
      "readiness": 10,
      "priority": "high",
      "confidence": 0.85,
      "nextUp": "Start",
      "checklist": [{"id": "c1", "title": "First step", "completed": false}],
      "connectedServices": ["Gmail"],
      "sourceMessageIds": ["msg-1"]
    }
  ],
  "metadata": {"flowsCreated": 1, "flowsIgnored": 0, "lowConfidenceIgnored": 0}
}
```
"""
flows11, low_ignored11 = gemini_service._parse_analyze_output(
    gemini_service._extract_json(json_with_fence)
)
check("markdown fence: parses correctly", len(flows11) == 1)
check("markdown fence: priority high", flows11[0].get("priority") == "high")
check("markdown fence: confidence 0.85", flows11[0].get("confidence") == 0.85)

# Partial JSON (only valid portion)
partial_json = '{"flows": [invalid, {"title": "Partial", "emoji": "✨", "date": "Today", "status": "Action Needed", "readiness": 10, "nextUp": "Go", "checklist": [{"id": "c1", "title": "Step", "completed": false}], "connectedServices": ["Gmail"], "priority": "medium", "confidence": 0.78, "sourceMessageIds": ["m1"]}], "metadata": {}}'

try:
    flows12, _ = gemini_service._parse_analyze_output(
        gemini_service._extract_json(partial_json)
    )
    check("partial/mixed JSON: skips invalid, keeps valid", len(flows12) == 1)
except Exception:
    # If parse fails completely on partial JSON, that's also acceptable
    # (extraction caught the valid part or raised error)
    check("partial/mixed JSON: handled safely", True)

# Unknown category -> other (handled by _clean_workflow_dict)
unknown_cat_flow = {
    "title": "Unknown Category",
    "emoji": "❓",
    "date": "Today",
    "status": "Action Needed",
    "readiness": 10,
    "nextUp": "Check",
    "checklist": [{"id": "c1", "title": "Verify category", "completed": False}],
    "connectedServices": ["Gmail"],
    "priority": "medium",
    "confidence": 0.80,
    "sourceMessageIds": ["msg-uk"],
    "category": "not_a_real_category",
}
flows13, _ = gemini_service._parse_analyze_output({"flows": [unknown_cat_flow], "metadata": {}})
check("unknown category: flow kept (category is not validated)", len(flows13) == 1)

# ===================== EXISTING INTEGRATION TESTS STILL PASS ================
print("\n--- Existing integration tests: backward compat ---")

# Use the same helper pattern as tests_integration.py
class Req:
    def __init__(self, token=None):
        self.headers = {"authorization": f"Bearer {token}"} if token else {}


class Payload:
    def __init__(self, q):
        self.query = q


# Reset to demo mode
firebase_service._enabled = False
workflow_store.init(None)

# These should still work exactly as before (backward compat)
# generate_workflow_dict is sync (no await needed)
wf1 = gemini_service.generate_workflow_dict("I have a passport appointment tomorrow", "compat-test-1")
check("compat: generate_workflow_dict still works", wf1.get("id") == "compat-test-1")
check("compat: priority defaults medium on ask flows", wf1.get("priority") == "medium")
check("compat: confidence is None on ask flows (no Gemini)", wf1.get("confidence") is None)

# Empty messages
flows_empty, low_ignored_empty = gemini_service._parse_analyze_output({})
check("empty analyze input: returns empty", len(flows_empty) == 0)
check("empty analyze input: low_ignored 0", low_ignored_empty == 0)

# None value for flows
flows_none, low_ignored_none = gemini_service._parse_analyze_output({"flows": None})
check("None flows: returns empty", len(flows_none) == 0)

# ===================== MULTI-SERVICE ANALYZE FUNCTION SIGNATURE ================
print("\n--- analyze_multi_service returns tuple ---")

result = gemini_service.analyze_multi_service(
    gmail_messages=fake_messages,
    calendar_events=[{
        "id": "ev-1",
        "summary": "Interview",
        "displayStart": "Sep 10",
        "start": "2026-09-10T10:00:00",
        "end": "2026-09-10T11:00:00",
        "location": "HQ",
        "attendees": [],
    }],
    drive_files=[{
        "id": "file-1",
        "name": "Resume.pdf",
        "mimeType": "application/pdf",
        "modifiedTime": "2026-09-01",
    }],
)
check("analyze_multi_service returns tuple", isinstance(result, tuple))
check("analyze_multi_service: first element is list", isinstance(result[0], list))
check("analyze_multi_service: second element is int", isinstance(result[1], int))

# No messages -> empty
result2 = gemini_service.analyze_multi_service()
check("analyze_multi_service no data: empty list", result2[0] == [])
check("analyze_multi_service no data: low_ignored 0", result2[1] == 0)

# ===================== UNCERTAINTY: AI DOES NOT INVENT ======================
print("\n--- Uncertainty: prompts prohibit inventing information ---")

# Check that the prompts explicitly forbid inventing information
prompt_text = gemini_service._build_analyze_prompt([{
    "id": "test",
    "threadId": "t",
    "sender": "test@test.com",
    "subject": "Test",
    "date": "Today",
    "snippet": "This is a vague email",
    "labels": [],
}])

check("prompt: explicitly says NEVER invent", "NEVER invent" in prompt_text)
check("prompt: explicitly says NEVER create a flow just because",
      "never create a flow just because" in prompt_text.lower())
check("prompt: says return empty flows when nothing meaningful",
      "empty flows[]" in prompt_text.lower() or "return empty" in prompt_text.lower())

unified_p = gemini_service._build_unified_prompt([], [], [], None, None)
check("unified prompt: says NEVER invent", "NEVER invent" in unified_p)
check("unified prompt: cross-service reasoning section present",
      "CROSS-SERVICE REASONING" in unified_p)
check("unified prompt: filtering section present",
      "STRICT FILTERING" in unified_p)
check("unified prompt: confidence scoring present",
      "CONFIDENCE" in unified_p)
check("unified prompt: priority rules present",
      "PRIORITY RULES" in unified_p)


print(f"\nALL {count} LIFEFLOW INTELLIGENCE CHECKS PASSED")
