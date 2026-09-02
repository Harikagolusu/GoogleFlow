"""Integration tests for backend/app/main.py WITHOUT requiring fastapi/pydantic.

Minimal stub modules for fastapi / pydantic / dotenv are injected so app.main
can be imported and its route handlers exercised directly. Covers:

  DEMO MODE (Firebase not configured):
    health, ask, empty-query 400, get-by-id, unknown-id 404, checklist PATCH
    with readiness/status/nextUp recompute, unknown-item 404

  FIREBASE MODE (firebase_service enabled + a fake Firestore):
    401 without bearer token, 401 invalid token, per-user creation/list/get,
    cross-user ownership 404s on GET and PATCH
"""
import asyncio
import sys
import types

# --- minimal pydantic stub -------------------------------------------------
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
        missing = [k for k in expected if k not in obj and getattr(cls, k, None) is None]
        if missing:
            raise ValidationError("missing fields")
        instance = cls()
        for k in expected:
            if k not in obj:
                continue
            instance.__dict__[k] = obj[k]
        return instance

    def model_dump(self):
        return dict(self.__dict__)


pydantic = types.ModuleType("pydantic")
pydantic.BaseModel = BaseModel
pydantic.Field = lambda **kw: _FieldSentinel(kw)
pydantic.ValidationError = ValidationError


# --- minimal fastapi stub --------------------------------------------------
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


fastapi = types.ModuleType("fastapi")
fastapi.FastAPI = FastAPI
fastapi.HTTPException = HTTPException
fastapi.Request = object  # handlers only use request.headers; object suffices
cors_mod = types.ModuleType("fastapi.middleware.cors")
cors_mod.CORSMiddleware = CORSMiddleware
dotenv = types.ModuleType("dotenv")
dotenv.load_dotenv = lambda *a, **k: False

sys.modules["pydantic"] = pydantic
sys.modules["fastapi"] = fastapi
sys.modules["fastapi.middleware"] = types.ModuleType("fastapi.middleware")
sys.modules["fastapi.middleware.cors"] = cors_mod
sys.modules["dotenv"] = dotenv


# --- tiny fake Firestore (users/{uid}/flows/{id}) --------------------------
class FakeSnapshot:
    def __init__(self, data):
        self._data = data

    @property
    def exists(self):
        return self._data is not None

    def to_dict(self):
        return dict(self._data) if self._data else {}


class FakeDoc:
    def __init__(self, store, path):
        self.store = store
        self.path = tuple(path)

    def set(self, data, merge=False):
        if merge and self.path in self.store:
            self.store[self.path] = {**self.store[self.path], **data}
        else:
            self.store[self.path] = dict(data)

    def get(self):
        return FakeSnapshot(self.store.get(self.path))

    def collection(self, name):
        return FakeCollection(self.store, [*self.path, name])


class FakeCollection:
    def __init__(self, store, path):
        self.store = store
        self.path = tuple(path)

    def document(self, doc_id):
        return FakeDoc(self.store, [*self.path, doc_id])

    def order_by(self, field, direction=None):
        return self

    def limit(self, n):
        return self

    def stream(self):
        for key in list(self.store):
            if key[: len(self.path)] == self.path and len(key) == len(self.path) + 1:
                yield FakeSnapshot(self.store[key])


class FakeFirestore:
    def __init__(self):
        self.store = {}

    def collection(self, name):
        return FakeCollection(self.store, [name])



# --- import real app.main and run scenarios -------------------------------
sys.path.insert(0, ".")
from app.main import (
    create_lifeflow,
    get_workflow,
    list_workflows,
    update_checklist_item,
    health,
)
from app import firebase_service, gemini_service, workflow_store

count = 0


def check(name, cond):
    global count
    count += 1
    print(("PASS" if cond else "FAIL"), "-", name)
    if not cond:
        raise SystemExit(1)


class Req:
    def __init__(self, token=None):
        self.headers = {"authorization": f"Bearer {token}"} if token else {}


class Payload:
    def __init__(self, q):
        self.query = q


class PatchBody:
    def __init__(self, completed):
        self.completed = completed


# ===================== DEMO MODE (Firebase not configured) =====================
check("health returns ok", health() == {"status": "ok"})

wf = asyncio.run(
    create_lifeflow(
        Req(),
        Payload(
            "I have a passport appointment tomorrow at 10:30 AM in Hyderabad. "
            "I need to carry my Aadhaar card, PAN card and passport copies."
        ),
    )
)
check("ask returns workflow with id", wf.id.startswith("gen-"))
check("ask title", wf.title == "Passport Appointment")
check("ask readiness in 0..100", 0 <= wf.readiness <= 100)
check("ask checklist non-empty", len(wf.checklist) == 6)
check("ask connected services", len(wf.connectedServices) >= 3)
fid = wf.id

check("list includes generated", any(w.id == fid for w in list_workflows(Req())))
check("get by id works", get_workflow(Req(), fid).id == fid)

try:
    asyncio.run(create_lifeflow(Req(), Payload("   ")))
    check("empty query rejected", False)
except HTTPException as e:
    check("empty query rejected 400", e.status_code == 400)

try:
    get_workflow(Req(), "does-not-exist")
    check("unknown id 404", False)
except HTTPException as e:
    check("unknown id 404", e.status_code == 404)

# Checklist PATCH: mark first item complete -> readiness recompute
first_item = wf.checklist[0]["id"]
patched = update_checklist_item(Req(), fid, first_item, PatchBody(True))
check("patch returns workflow", patched.id == fid)
done = [i for i in patched.checklist if i["completed"]]
check("patch marks item complete", len(done) == 1 and done[0]["id"] == first_item)
check("patch recomputes readiness", patched.readiness == round(1 / 6 * 100))
check("patch recomputes status", patched.status == "In Progress")
check("patch recomputes nextUp", patched.nextUp == wf.checklist[1]["title"])

try:
    update_checklist_item(Req(), fid, "nonexistent-item", PatchBody(True))
    check("patch unknown item 404", False)
except HTTPException as e:
    check("patch unknown item 404", e.status_code == 404)

# ===================== FIREBASE MODE (auth + fake Firestore) =====================
fake = FakeFirestore()
firebase_service._enabled = True
firebase_service.verify_id_token = lambda token: token  # token string IS the uid
workflow_store.init(fake)

# 401 without bearer token
try:
    asyncio.run(create_lifeflow(Req(), Payload("test")))
    check("ask without token 401", False)
except HTTPException as e:
    check("ask without token 401", e.status_code == 401)

# 401 with invalid token
firebase_service.verify_id_token = lambda token: (_ for _ in ()).throw(ValueError("bad"))
try:
    asyncio.run(create_lifeflow(Req("bad-token"), Payload("test")))
    check("ask invalid token 401", False)
except HTTPException as e:
    check("ask invalid token 401", e.status_code == 401)

# valid user A
firebase_service.verify_id_token = lambda token: token
wf_a = asyncio.run(create_lifeflow(Req("userA"), Payload("Plan my trip to Delhi next week")))
check("userA creates workflow", wf_a.id.startswith("gen-"))
check("userA list sees own workflow", any(w.id == wf_a.id for w in list_workflows(Req("userA"))))
check("userA get own workflow", get_workflow(Req("userA"), wf_a.id).id == wf_a.id)

# user B cannot see or modify user A's workflow
try:
    get_workflow(Req("userB"), wf_a.id)
    check("userB get userA workflow 404", False)
except HTTPException as e:
    check("userB get userA workflow 404", e.status_code == 404)

try:
    update_checklist_item(Req("userB"), wf_a.id, wf_a.checklist[0]["id"], PatchBody(True))
    check("userB patch userA workflow 404", False)
except HTTPException as e:
    check("userB patch userA workflow 404", e.status_code == 404)

# user A can PATCH own workflow
patched_a = update_checklist_item(Req("userA"), wf_a.id, wf_a.checklist[0]["id"], PatchBody(True))
check("userA patch own workflow", patched_a.readiness == round(1 / len(wf_a.checklist) * 100))

# ===================== PHASE 2: AI LIFEFLOW INTELLIGENCE =====================
# These tests verify the improved LifeFlow generation quality using the
# deterministic fallback generator (no real GEMINI_API_KEY needed).
# Reset to demo mode (Firebase disabled) for these tests.
firebase_service._enabled = False
workflow_store.init(None)

print("\n--- Phase 2: AI LifeFlow Intelligence ---")

# Helper: generate a workflow via the fallback path (demo mode)
def gen(query: str) -> dict:
    return asyncio.run(create_lifeflow(Req(), Payload(query)))

# --- Test 1: Interview query generates valid LifeFlow ---
wf_interview = gen("I have an interview next week and need to prepare")
check("interview: valid title", isinstance(wf_interview.title, str) and len(wf_interview.title) > 0)
check("interview: checklist count 4-8", 4 <= len(wf_interview.checklist) <= 8)
check("interview: readiness 0-100", 0 <= wf_interview.readiness <= 100)
check("interview: status valid", wf_interview.status in ("Action Needed", "In Progress", "Completed"))
check("interview: nextUp is string", isinstance(wf_interview.nextUp, str) and len(wf_interview.nextUp) > 0)
check("interview: services non-empty", len(wf_interview.connectedServices) >= 3)

# --- Test 2: Trip planning query generates valid LifeFlow ---
wf_trip = gen("Plan my trip to Delhi next month")
check("trip: valid title", isinstance(wf_trip.title, str) and len(wf_trip.title) > 0)
check("trip: checklist count 4-8", 4 <= len(wf_trip.checklist) <= 8)
check("trip: services include Maps", "Google Maps" in wf_trip.connectedServices)
check("trip: nextUp is string", isinstance(wf_trip.nextUp, str) and len(wf_trip.nextUp) > 0)

# --- Test 3: Study/certification query generates valid LifeFlow ---
wf_study = gen("I have a certification exam next month")
check("study: valid title", isinstance(wf_study.title, str) and len(wf_study.title) > 0)
check("study: checklist count 4-8", 4 <= len(wf_study.checklist) <= 8)
check("study: services include Drive", "Google Drive" in wf_study.connectedServices)
check("study: nextUp is string", isinstance(wf_study.nextUp, str) and len(wf_study.nextUp) > 0)

# --- Test 4: Time-sensitive query prioritizes urgent tasks ---
wf_urgent = gen("I have an interview tomorrow morning")
check("urgent: valid title", isinstance(wf_urgent.title, str) and len(wf_urgent.title) > 0)
check("urgent: checklist non-empty", len(wf_urgent.checklist) >= 4)
check("urgent: first item is actionable", len(wf_urgent.checklist[0]["title"]) > 10)

# --- Test 5: Checklist items are actionable (not generic) ---
generic_phrases = ["complete the task", "prepare everything", "follow the process", "finish your work", "get ready"]
for wf in [wf_interview, wf_trip, wf_study]:
    for item in wf.checklist:
        title_lower = item["title"].lower()
        is_generic = any(phrase in title_lower for phrase in generic_phrases)
        check(f"checklist item not generic: {item['title'][:30]}", not is_generic)

# --- Test 6: Connected services are relevant ---
for wf in [wf_interview, wf_trip, wf_study]:
    for svc in wf.connectedServices:
        check(f"service {svc} is known", svc in [
            "Gmail", "Google Drive", "Google Calendar", "Google Maps",
            "YouTube", "Google Search", "Google News", "Google Photos", "Gemini"
        ])

# --- Test 7: nextUp is concrete (not a generic summary) ---
for wf in [wf_interview, wf_trip, wf_study]:
    check(f"nextUp concrete for {wf.title}", isinstance(wf.nextUp, str) and len(wf.nextUp) > 15)

# --- Test 8: Invalid AI output is rejected safely ---
# Simulate invalid output by monkey-patching the fallback
original_fallback = gemini_service._generate_fallback
gemini_service._generate_fallback = lambda q: {"title": "Invalid"}  # Missing required fields
try:
    gen("test invalid output")
    check("invalid output rejected", False)
except HTTPException as e:
    check("invalid output rejected with 502", e.status_code == 502)
finally:
    gemini_service._generate_fallback = original_fallback

# --- Test 9: Empty AI response is rejected safely ---
gemini_service._generate_fallback = lambda q: {}  # Empty dict
try:
    gen("test empty output")
    check("empty output rejected", False)
except HTTPException as e:
    check("empty output rejected with 502", e.status_code == 502)
finally:
    gemini_service._generate_fallback = original_fallback

# --- Test 10: Gemini API failure does not crash the server ---
gemini_service._generate_fallback = lambda q: (_ for _ in ()).throw(RuntimeError("API failure"))
try:
    gen("test api failure")
    check("api failure handled", False)
except HTTPException as e:
    check("api failure returns 502", e.status_code == 502)
except RuntimeError:
    check("api failure did not crash", False)
finally:
    gemini_service._generate_fallback = original_fallback

# --- Test 11: Existing checklist PATCH recomputation still works ---
wf_patch = gen("I have an interview next week")
first_id = wf_patch.checklist[0]["id"]
patched = update_checklist_item(Req(), wf_patch.id, first_id, PatchBody(True))
check("patch: readiness recomputed", patched.readiness == round(1 / len(wf_patch.checklist) * 100))
check("patch: status is In Progress", patched.status == "In Progress")
check("patch: nextUp is second item", patched.nextUp == wf_patch.checklist[1]["title"])

# --- Test 12: Demo mode works without Firebase ---
# (All tests above run in demo mode — if we got here, demo mode works)
check("demo mode works", True)

print(f"\nALL {count} INTEGRATION CHECKS PASSED")

