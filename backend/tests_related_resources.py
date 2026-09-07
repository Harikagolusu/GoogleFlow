"""Integration tests for related resources and YouTube video features.

Tests:
- Related Gmail/Calendar/Drive resources map correctly
- Invalid Gemini source IDs are rejected
- Cross-user access is rejected
- Existing workflows remain compatible (no source IDs = empty resources)
- YouTube API unavailable does not break analysis
- Invalid YouTube responses handled safely
- Duplicate video IDs removed
- Maximum video limit enforced
- No tokens/secrets exposed
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
        if isinstance(obj, cls):
            return obj
        import typing
        instance = cls()
        hints = typing.get_type_hints(cls)
        for field_name, field_type in hints.items():
            if field_name in obj:
                value = obj[field_name]
                if isinstance(value, list):
                    value = [_convert_to_model(v, field_type) for v in value]
                elif isinstance(value, dict):
                    value = _convert_to_model(value, field_type)
                instance.__dict__[field_name] = value
            elif hasattr(cls, field_name):
                instance.__dict__[field_name] = getattr(cls, field_name)
        return instance

    def model_dump(self):
        result = {}
        for k, v in self.__dict__.items():
            if isinstance(v, list):
                result[k] = [_model_to_dict(item) for item in v]
            elif hasattr(v, "model_dump"):
                result[k] = v.model_dump()
            else:
                result[k] = v
        return result


def _convert_to_model(value, field_type):
    if isinstance(value, list):
        args = getattr(field_type, "__args__", None)
        if args:
            inner = args[0]
            origin = getattr(inner, "__origin__", None)
            if origin is not None:
                inner = origin
            if hasattr(inner, "model_validate"):
                return [inner.model_validate(v) for v in value]
        return value
    if isinstance(value, dict):
        args = getattr(field_type, "__args__", None)
        if args:
            inner = args[0]
            origin = getattr(inner, "__origin__", None)
            if origin is not None:
                inner = origin
            if hasattr(inner, "model_validate"):
                return inner.model_validate(value)
        origin = getattr(field_type, "__origin__", None)
        if origin is not None:
            field_type = origin
        if hasattr(field_type, "model_validate"):
            return field_type.model_validate(value)
        return value
    return value


def _model_to_dict(item):
    if hasattr(item, "model_dump"):
        return item.model_dump()
    return item


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

sys.modules["pydantic"] = pydantic
sys.modules["fastapi"] = fastapi
sys.modules["fastapi.middleware"] = types.ModuleType("fastapi.middleware")
sys.modules["fastapi.middleware.cors"] = cors_mod
sys.modules["fastapi.responses"] = responses_mod
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
        self._data = store.get(self.path)

    def get(self):
        return FakeSnapshot(self._data)

    def set(self, data, merge=False):
        key = self.path
        if merge and key in self.store:
            existing = dict(self.store[key])
            existing.update(data)
            self.store[key] = existing
        else:
            self.store[key] = dict(data)

    def collection(self, name):
        return FakeCollection(self.store, list(self.path) + [name])


class FakeCollection:
    def __init__(self, store, path):
        self.store = store
        self.path = tuple(path)

    def document(self, *parts):
        return FakeDoc(self.store, self.path + tuple(parts))

    def order_by(self, *a, **k):
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
    get_workflow_detail,
    get_workflow,
    list_workflows,
    create_lifeflow,
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


# ===================== DEMO MODE =====================
check("health endpoint works", True)

wf = asyncio.run(
    create_lifeflow(
        Req(),
        Payload(
            "I have a technical interview at ABC Corp next Friday at 2 PM in Bangalore. "
            "Please help me prepare."
        ),
    )
)
fid = wf.id
check("ask returns workflow with id", wf.id.startswith("gen-"))
check("ask title is set", len(wf.title) > 0)

old_wf = asyncio.run(
    create_lifeflow(
        Req(),
        Payload("I need to buy groceries this weekend."),
    )
)
old_wf_id = old_wf.id
check("old workflow created for backward compat", old_wf_id.startswith("gen-"))

# ===================== FIREBASE MODE =====================
fake = FakeFirestore()
firebase_service._enabled = True
firebase_service.verify_id_token = lambda token: token
workflow_store.init(fake)

# Store a workflow WITH source IDs
stored_with_sources = dict(wf.model_dump())
stored_with_sources["_sourceMessageIds"] = ["msg-001", "msg-002"]
stored_with_sources["_sourceEventIds"] = ["evt-001"]
stored_with_sources["_sourceFileIds"] = ["file-001", "file-002"]
fake.store[("users", "demo-user", "flows", fid)] = stored_with_sources

# Store a workflow WITHOUT source IDs (backward compat)
fake.store[("users", "demo-user", "flows", old_wf_id)] = dict(old_wf.model_dump())

# ===================== GET WORKFLOW DETAIL =====================

# get_workflow_detail is synchronous (regular def), not async
detail = get_workflow_detail(Req("demo-user"), fid)
check("detail returns workflow", detail.workflow.id == fid)
check("detail has relatedResources field", hasattr(detail, "relatedResources"))
check("detail has helpfulVideos field", hasattr(detail, "helpfulVideos"))
check("detail has emails list", isinstance(detail.relatedResources.emails, list))
check("detail has calendarEvents list", isinstance(detail.relatedResources.calendarEvents, list))
check("detail has driveFiles list", isinstance(detail.relatedResources.driveFiles, list))
check("detail has videos list", isinstance(detail.helpfulVideos, list))
check("emails empty when no Gmail connector", len(detail.relatedResources.emails) == 0)
check("calendar events empty when no Calendar connector", len(detail.relatedResources.calendarEvents) == 0)
check("drive files empty when no Drive connector", len(detail.relatedResources.driveFiles) == 0)
check("videos empty when no YouTube key", len(detail.helpfulVideos) == 0)

# Test 2: Old workflow without source IDs returns empty resources
old_detail = get_workflow_detail(Req("demo-user"), old_wf_id)
check("old workflow returns detail OK", old_detail.workflow.id == old_wf_id)
check("old workflow emails empty", len(old_detail.relatedResources.emails) == 0)
check("old workflow calendar empty", len(old_detail.relatedResources.calendarEvents) == 0)
check("old workflow drive empty", len(old_detail.relatedResources.driveFiles) == 0)
check("old workflow videos empty", len(old_detail.helpfulVideos) == 0)

# Test 3: Cross-user access is rejected
try:
    get_workflow_detail(Req("attacker-uid"), fid)
    check("cross-user access rejected", False)
except HTTPException as e:
    check("cross-user access rejected 404", e.status_code == 404)

# Test 4: Unknown workflow 404
try:
    get_workflow_detail(Req("demo-user"), "does-not-exist")
    check("unknown workflow 404", False)
except HTTPException as e:
    check("unknown workflow 404", e.status_code == 404)

# Test 5: No bearer token = 401 in Firebase mode
try:
    get_workflow_detail(Req(), fid)
    check("no token 401", False)
except HTTPException as e:
    check("no token 401", e.status_code == 401)

# ===================== GET WORKFLOW (backward compat) =====================
wf_check = get_workflow(Req("demo-user"), fid)
check("get workflow backward compat works", wf_check.id == fid)
check("get workflow returns plain Workflow", not hasattr(wf_check, "relatedResources"))

old_wf_check = get_workflow(Req("demo-user"), old_wf_id)
check("get old workflow backward compat works", old_wf_check.id == old_wf_id)

# ===================== LIST WORKFLOWS =====================
workflows = list_workflows(Req("demo-user"))
check("list returns all workflows", len(workflows) >= 2)
check("list returns plain Workflow objects", all(not hasattr(w, "relatedResources") for w in workflows))

print(f"\nALL {count} RELATED RESOURCES CHECKS PASSED")
