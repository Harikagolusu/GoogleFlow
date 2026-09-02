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
from app import firebase_service, workflow_store

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

print(f"\nALL {count} INTEGRATION CHECKS PASSED")

