"""Integration test for backend/app/main.py WITHOUT requiring fastapi/pydantic.

Injects minimal stub modules for fastapi / pydantic / dotenv so `app.main` can
be imported and its route-handler functions exercised directly (validation,
storage round-trip, 400 empty-query, 404 unknown-id).
Run from the backend/ directory.
"""
import asyncio
import sys
import types

# --- minimal pydantic stub -------------------------------------------------
import re


class ValidationError(Exception):
    pass


class Field:
    def __init__(self, **kw):
        self.kw = kw


def FieldFactory(**kw):
    # pydantic uses Field(...) as a default; emulate as a sentinel
    return _FieldSentinel(kw)


class _FieldSentinel:
    def __init__(self, kw):
        self.kw = kw


def _type_name(t):
    name = getattr(t, "__name__", None)
    if name:
        return name
    return str(t).replace("typing.", "").replace("Literal[", "Lit:").replace("]", "")


class BaseModelMeta(type):
    pass


class BaseModel(metaclass=BaseModelMeta):
    def __init__(self, **data):
        self.__dict__.update(data)

    @classmethod
    def model_validate(cls, obj):
        import inspect

        expected = {}
        for name, ann in cls.__annotations__.items():
            default = getattr(cls, name, inspect.Parameter.empty)
            expected[name] = ann
        missing = [k for k in expected if k not in obj and getattr(cls, k, None) is None]
        if missing:
            raise ValidationError(f"missing fields: {missing}")
        instance = cls()
        for k, ann in expected.items():
            if k not in obj:
                if isinstance(getattr(cls, k, None), _FieldSentinel):
                    instance.__dict__[k] = None
                    continue
                continue
            val = obj[k]
            if _type_name(ann) == "int":
                if not isinstance(val, int) and not isinstance(val, float):
                    raise ValidationError(f"{k} must be int")
                val = int(val)
            elif _type_name(ann) == "bool":
                val = bool(val)
            elif _type_name(ann) == "str":
                if not isinstance(val, str):
                    raise ValidationError(f"{k} must be str")
            instance.__dict__[k] = val
        return instance

    def model_dump(self):
        return dict(self.__dict__)


pydantic = types.ModuleType("pydantic")
pydantic.BaseModel = BaseModel
pydantic.Field = FieldFactory
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

    def get(self, path, **kw):
        def deco(fn):
            self.routes[("GET", path)] = fn
            return fn
        return deco

    def post(self, path, **kw):
        def deco(fn):
            self.routes[("POST", path)] = fn
            return fn
        return deco

    def add_middleware(self, *a, **k):
        pass


fastapi = types.ModuleType("fastapi")
fastapi.FastAPI = FastAPI
fastapi.HTTPException = HTTPException
cors_mod = types.ModuleType("fastapi.middleware.cors")
cors_mod.CORSMiddleware = CORSMiddleware

dotenv = types.ModuleType("dotenv")
dotenv.load_dotenv = lambda *a, **k: False

sys.modules["pydantic"] = pydantic
sys.modules["fastapi"] = fastapi
sys.modules["fastapi.middleware"] = types.ModuleType("fastapi.middleware")
sys.modules["fastapi.middleware.cors"] = cors_mod
sys.modules["dotenv"] = dotenv

# --- import real app.main and run handlers ---------------------------------
sys.path.insert(0, ".")
from app.main import app, create_lifeflow, list_workflows, get_workflow, health

count = 0


def check(name, cond):
    global count
    count += 1
    print(("PASS" if cond else "FAIL"), "-", name)
    if not cond:
        raise SystemExit(1)


# health
check("health returns ok", health() == {"status": "ok"})

# ask with the task's example
class Req:
    def __init__(self, q):
        self.query = q


async def _run_ask(q):
    return await create_lifeflow(Req(q))


async def _run_ask_empty():
    return await create_lifeflow(Req("   "))


wf = asyncio.run(_run_ask("I have a passport appointment tomorrow at 10:30 AM in Hyderabad. I need to carry my Aadhaar card, PAN card and passport copies."))
check("ask returns workflow with id", wf.id.startswith("gen-"))
check("ask title Pasport", wf.title == "Passport Appointment")
check("ask readiness int in 0..100", 0 <= wf.readiness <= 100)
check("ask checklist non-empty", len(wf.checklist) == 6)
check("ask connected services", len(wf.connectedServices) >= 3)
fid = wf.id

# stored + retrievable
check("list includes generated", any(w.id == fid for w in list_workflows()))
check("get by id works", get_workflow(fid).id == fid)

# empty query
try:
    asyncio.run(_run_ask_empty())
    check("empty query rejected", False)
except HTTPException as e:
    check("empty query rejected 400", e.status_code == 400)

# unknown id -> 404
try:
    get_workflow("does-not-exist")
    check("unknown id 404", False)
except HTTPException as e:
    check("unknown id 404", e.status_code == 404)

# invalid generated output -> not a crash: build a workflow with a checklist that
# fails status (ok) - verify model rejects out-of-range readiness
try:
    from app.schemas import Workflow
    Workflow.model_validate({
        "id": "x", "title": "t", "emoji": "e", "date": "d", "status": "Bogus",
        "readiness": 999, "checklist": [{"id": "c1", "title": "a", "completed": False}],
        "connectedServices": ["Gmail"],
    })
    check("schema rejects bogus", False)
except ValidationError:
    check("schema rejects bogus status", True)

print(f"\nALL {count} INTEGRATION CHECKS PASSED")
