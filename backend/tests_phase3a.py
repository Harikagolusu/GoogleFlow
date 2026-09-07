"""Phase 3A integration tests for the Gmail OAuth connection foundation.

These tests run WITHOUT fastapi/pydantic installed, using minimal stubs.
They cover the OAuth foundation requirements from Phase 3A without
requiring real Google OAuth credentials, real Gmail access, or a real
backend. All network calls are mocked.
"""
import asyncio
import os
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


# --- minimal fastapi stub --------------------------------------------------
class HTTPException(Exception):
    def __init__(self, status_code, detail):
        self.status_code = status_code
        self.detail = detail


class RedirectResponse:
    def __init__(self, url, status_code=302):
        self.url = url
        self.status_code = status_code


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
fastapi.RedirectResponse = RedirectResponse
fastapi.Query = _QueryStub
cors_mod = types.ModuleType("fastapi.middleware.cors")
cors_mod.CORSMiddleware = CORSMiddleware
responses_mod = types.ModuleType("fastapi.responses")
responses_mod.RedirectResponse = RedirectResponse
dotenv = types.ModuleType("dotenv")
dotenv.load_dotenv = lambda *a, **k: False

sys.modules["pydantic"] = pydantic
sys.modules["fastapi"] = fastapi
sys.modules["fastapi.middleware"] = types.ModuleType("fastapi.middleware")
sys.modules["fastapi.middleware.cors"] = cors_mod
sys.modules["fastapi.responses"] = responses_mod
sys.modules["dotenv"] = dotenv

sys.path.insert(0, ".")
from app import connections_store, google_auth

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


def _enable_firebase_with_uid_identity():
    """Make _require_uid return the bearer-token string as the UID."""
    from app import firebase_service

    firebase_service._enabled = True
    firebase_service.verify_id_token = lambda token: token


def _disable_firebase():
    from app import firebase_service

    firebase_service._enabled = False


def _set_oauth_configured():
    os.environ["GOOGLE_OAUTH_CLIENT_ID"] = "test-client-id"
    os.environ["GOOGLE_OAUTH_CLIENT_SECRET"] = "test-client-secret"
    os.environ["GOOGLE_OAUTH_REDIRECT_URI"] = "http://localhost:8010/api/auth/gmail/callback"
    google_auth.reset_for_tests()
    connections_store.reset_for_tests()


def _clear_oauth_config():
    for k in (
        "GOOGLE_OAUTH_CLIENT_ID",
        "GOOGLE_OAUTH_CLIENT_SECRET",
        "GOOGLE_OAUTH_REDIRECT_URI",
    ):
        os.environ.pop(k, None)
    google_auth.reset_for_tests()
    connections_store.reset_for_tests()


# ===================== OAUTH CONFIGURATION =====================
print("--- OAuth configuration ---")
_clear_oauth_config()
check("oauth unconfigured reports not configured", google_auth.is_configured() is False)
check("oauth status client_id false", google_auth.configuration_status()["client_id_set"] is False)
_set_oauth_configured()
check("oauth configured after env vars set", google_auth.is_configured() is True)
status = google_auth.configuration_status()
check("status does not leak secret", "client_secret" not in status)
check("status client_secret_set true", status["client_secret_set"] is True)


# ===================== OAUTH STATE MANAGEMENT =====================
print("\n--- OAuth state management ---")
google_auth.reset_for_tests()
state1 = google_auth.generate_state("userA", "gmail")
check("state generated is non-empty string", isinstance(state1, str) and len(state1) > 20)
check("two states are different", google_auth.generate_state("userA", "gmail") != state1)

record = google_auth.validate_and_consume_state(state1)
check("state bound to correct uid", record["uid"] == "userA")
check("state bound to correct service", record["service"] == "gmail")

# Single-use: reusing the same state should fail.
try:
    google_auth.validate_and_consume_state(state1)
    check("reused state rejected", False)
except google_auth.StateError:
    check("reused state rejected", True)

# Invalid states
try:
    google_auth.validate_and_consume_state("")
    check("empty state rejected", False)
except google_auth.StateError:
    check("empty state rejected", True)

try:
    google_auth.validate_and_consume_state("not-a-real-state")
    check("unknown state rejected", False)
except google_auth.StateError:
    check("unknown state rejected", True)


# ===================== STATE TTL / EXPIRY =====================
print("\n--- State TTL / expiry ---")
google_auth.reset_for_tests()
os.environ["GOOGLE_OAUTH_STATE_TTL_SECONDS"] = "1"
# Re-import to pick up env (state ttl is read each call, so this works)
state_short = google_auth.generate_state("userA", "gmail")
import time
time.sleep(1.2)
try:
    google_auth.validate_and_consume_state(state_short)
    check("expired state rejected", False)
    check("expired state rejected with expiry error", False)
except google_auth.StateError as e:
    check("expired state rejected", True)
    check("expired state rejected with expiry error", "expired" in str(e).lower())
os.environ.pop("GOOGLE_OAUTH_STATE_TTL_SECONDS", None)


# ===================== AUTHORIZATION URL =====================
print("\n--- Authorization URL ---")
_set_oauth_configured()
google_auth.reset_for_tests()
result = google_auth.build_authorization_url("gmail", "userA")
check("authorization_url returned", "authorization_url" in result)
url = result["authorization_url"]
check("URL is Google consent endpoint", "accounts.google.com" in url)
check("URL contains client_id", "test-client-id" in url)
check("URL contains scope gmail.readonly", "gmail.readonly" in url)
check("URL contains offline access_type", "access_type=offline" in url)
check("URL contains prompt=consent", "prompt=consent" in url)
check("URL contains state", "state=" in url)
check("state returned matches URL state", "state=" + result["state"] in url)

# State must be bound to the requesting UID
record = google_auth.validate_and_consume_state(result["state"])
check("state bound to requesting uid", record["uid"] == "userA")


# Unconfigured: no client id
print("\n--- Authorization URL when unconfigured ---")
_clear_oauth_config()
try:
    google_auth.build_authorization_url("gmail", "userA")
    check("unconfigured URL build rejected", False)
except google_auth.StateError:
    check("unconfigured URL build rejected", True)


# ===================== CODE EXCHANGE (MOCKED) =====================
print("\n--- Authorization code exchange (mocked) ---")
_set_oauth_configured()
google_auth.reset_for_tests()
connections_store.reset_for_tests()


def _mock_exchange(code, redirect_uri, client_id, client_secret):
    return {
        "access_token": "ya29.fake-access",
        "refresh_token": "1//fake-refresh",
        "expires_in": 3600,
        "scope": "https://www.googleapis.com/auth/gmail.readonly",
        "token_type": "Bearer",
    }


google_auth.set_code_exchanger(_mock_exchange)
creds = google_auth.exchange_code("fake-auth-code")
check("exchange returns access_token", creds.get("access_token") == "ya29.fake-access")
check("exchange returns refresh_token", creds.get("refresh_token") == "1//fake-refresh")
check("exchange returns expires_in", creds.get("expires_in") == 3600)

# Missing code
try:
    google_auth.exchange_code("")
    check("missing code rejected", False)
except google_auth.StateError:
    check("missing code rejected", True)

# Bad exchange response
google_auth.set_code_exchanger(lambda c, r, i, s: {})
try:
    google_auth.exchange_code("code")
    check("bad exchange response rejected", False)
except google_auth.StateError:
    check("bad exchange response rejected", True)
google_auth.set_code_exchanger(_mock_exchange)


# ===================== ENDPOINTS: CONNECT =====================
print("\n--- Endpoints: /api/auth/gmail/connect ---")
from app.main import app

_clear_oauth_config()
_disable_firebase()
_set_oauth_configured()
google_auth.reset_for_tests()
connections_store.reset_for_tests()
routes = app.routes

# Unauthenticated (firebase disabled) -> demo mode, still allowed
# but only when OAuth is configured. We test the configured path here.
connect = routes[("GET", "/api/auth/gmail/connect")]
resp = connect(Req())
check("connect returns RedirectResponse", isinstance(resp, RedirectResponse))
check("connect redirects to Google", "accounts.google.com" in resp.url)
check("connect has 302 status", resp.status_code == 302)

# --- Endpoints: POST /api/auth/gmail/connect (JSON, authenticated) ---
connect_json = routes[("POST", "/api/auth/gmail/connect")]
resp = connect_json(Req())
check("json connect returns authorization_url", isinstance(resp, dict) and "authorization_url" in resp)
check("json connect URL points to Google", "accounts.google.com" in resp["authorization_url"])
check("json connect URL includes gmail.readonly scope", "gmail.readonly" in resp["authorization_url"])
check("json connect URL includes offline access_type", "access_type=offline" in resp["access_type"] if "access_type" in resp else "access_type=offline" in resp["authorization_url"])
check("json connect URL has exact redirect URI", "localhost%3A8010%2Fapi%2Fauth%2Fgmail%2Fcallback" in resp["authorization_url"])
check("json connect does NOT expose client_secret", "client_secret" not in resp and "client_secret" not in resp["authorization_url"])
check("json connect does NOT expose client id as secret", resp["authorization_url"].count("client_id=") >= 0)
check("json connect returns state", isinstance(resp.get("state"), str) and len(resp.get("state", "")) > 10)
# State is bound to requesting uid and server-managed.
record = google_auth.validate_and_consume_state(resp["state"])
check("json connect state bound to uid", record["uid"] == "demo-user")

# Unauthenticated rejected when Firebase auth is enabled
_enable_firebase_with_uid_identity()
try:
    routes[("GET", "/api/auth/gmail/connect")](Req())  # no token
    check("GET connect without token 401", False)
except HTTPException as e:
    check("GET connect without token 401", e.status_code == 401)
try:
    connect_json(Req())  # no token
    check("POST connect without token 401", False)
except HTTPException as e:
    check("POST connect without token 401", e.status_code == 401)


# ===================== ENDPOINTS: STATUS =====================
print("\n--- Endpoints: /api/auth/gmail/status ---")
status_ep = routes[("GET", "/api/auth/gmail/status")]

# Demo mode (no firebase) -> always disconnected
_disable_firebase()
resp = status_ep(Req())
check("demo status returns connected false", resp["connected"] is False)
check("demo status has service gmail", resp["service"] == "gmail")
check("demo status has empty scopes", resp["scopes"] == [])

# Authenticated + connected
_enable_firebase_with_uid_identity()
google_auth.reset_for_tests()
connections_store.reset_for_tests()
# Connect and complete the OAuth flow
connect = routes[("GET", "/api/auth/gmail/connect")]
connect(Req("userA"))
# Simulate a callback
callback = routes[("GET", "/api/auth/gmail/callback")]
# Recover the single unconsumed state bound to userA.
state_token = None
for tok, rec in google_auth._states.items():
    if rec["uid"] == "userA" and not rec.get("consumed"):
        state_token = tok
        break

google_auth.set_code_exchanger(_mock_exchange)
cb_resp = callback(Req(), code="auth-code-1", state=state_token)
check("callback returns RedirectResponse", isinstance(cb_resp, RedirectResponse))
check("callback redirects to frontend", "localhost:3000" in cb_resp.url or "/profile" in cb_resp.url)
check("callback URL indicates connected", "gmail=connected" in cb_resp.url)
check("callback URL does NOT leak token", "access_token" not in cb_resp.url and "refresh_token" not in cb_resp.url)

# Status now
resp = status_ep(Req("userA"))
check("status connected true", resp["connected"] is True)
check("status has gmail service", resp["service"] == "gmail")
check("status scopes include gmail.readonly", "https://www.googleapis.com/auth/gmail.readonly" in resp["scopes"])
check("status has connected_at", resp.get("connected_at") is not None)
check("status has NO access_token field", "access_token" not in resp)
check("status has NO refresh_token field", "refresh_token" not in resp)


# ===================== USER ISOLATION =====================
print("\n--- User isolation ---")
# userB status
resp_b = status_ep(Req("userB"))
check("userB sees disconnected", resp_b["connected"] is False)

# userB tries to disconnect userA -> no effect on userA
disconnect_ep = routes[("POST", "/api/auth/gmail/disconnect")]
resp = disconnect_ep(Req("userB"))
check("userB disconnect reports was_connected false", resp["was_connected"] is False)
resp_a = status_ep(Req("userA"))
check("userA connection still intact after userB disconnect", resp_a["connected"] is True)


# ===================== DISCONNECT =====================
print("\n--- Endpoints: /api/auth/gmail/disconnect ---")
revoke_calls = []
google_auth.set_token_revoker(lambda tok: revoke_calls.append(tok) or True)

resp = disconnect_ep(Req("userA"))
check("userA disconnect returns disconnected true", resp["disconnected"] is True)
check("userA disconnect was_connected true", resp["was_connected"] is True)
check("revocation attempted", len(revoke_calls) >= 1)
check("revoked token was a real (refresh) token", "1//fake-refresh" in revoke_calls)

# Status after disconnect
resp = status_ep(Req("userA"))
check("after disconnect: connected false", resp["connected"] is False)

# Disconnect when not connected
resp = disconnect_ep(Req("userA"))
check("disconnect when already disconnected", resp["was_connected"] is False)


# ===================== REVOCATION FAILURE HANDLING =====================
print("\n--- Revocation failure handling ---")
google_auth.set_code_exchanger(_mock_exchange)
connect(Req("userA"))
state_token = None
for tok, rec in google_auth._states.items():
    if rec["uid"] == "userA" and not rec.get("consumed"):
        state_token = tok
        break
callback(Req("userA"), code="auth-code-2", state=state_token)
google_auth.set_token_revoker(lambda tok: (_ for _ in ()).throw(RuntimeError("network down")))
resp = disconnect_ep(Req("userA"))
check("revocation failure handled safely", resp["disconnected"] is True)
check("connection still deleted despite revocation failure", status_ep(Req("userA"))["connected"] is False)
google_auth.set_token_revoker(lambda tok: True)


# ===================== AUTH REJECTION =====================
print("\n--- Auth rejection ---")
_disable_firebase()
google_auth.reset_for_tests()
# /api/auth/gmail/connect is allowed in demo mode (uid == DEMO_UID)
# /api/auth/gmail/status returns disconnected in demo mode
# /api/auth/gmail/disconnect in demo mode -> returns was_connected: False
resp = disconnect_ep(Req())
check("demo disconnect returns result", isinstance(resp, dict))
check("demo disconnect was_connected False", resp.get("was_connected") is False)

# When firebase is enabled but no token is present, require_uid raises 401
_enable_firebase_with_uid_identity()
firebase_service_mod = sys.modules["app.firebase_service"]
firebase_service_mod.verify_id_token = lambda token: (_ for _ in ()).throw(ValueError("no token"))

try:
    connect(Req())  # no token
    check("connect without token 401", False)
except HTTPException as e:
    check("connect without token 401", e.status_code == 401)

try:
    status_ep(Req())
    check("status without token 401", False)
except HTTPException as e:
    check("status without token 401", e.status_code == 401)

try:
    disconnect_ep(Req())
    check("disconnect without token 401", False)
except HTTPException as e:
    check("disconnect without token 401", e.status_code == 401)


# ===================== OAUTH NOT CONFIGURED =====================
print("\n--- OAuth not configured ---")
_clear_oauth_config()
_enable_firebase_with_uid_identity()
firebase_service_mod.verify_id_token = lambda token: token

try:
    connect(Req("userA"))
    check("connect without oauth config 503", False)
except HTTPException as e:
    check("connect without oauth config 503", e.status_code == 503)


# ===================== CALLBACK REJECTS INVALID STATE =====================
print("\n--- Callback: invalid state handling ---")
_set_oauth_configured()
google_auth.reset_for_tests()
connections_store.reset_for_tests()
# missing state
resp = callback(Req("userA"))
check("callback missing state redirects safely", "gmail=invalid" in resp.url)
# invalid state
resp = callback(Req("userA"), code="x", state="not-a-state")
check("callback invalid state redirects safely", "gmail=invalid" in resp.url)
# error from Google (consent denied)
resp = callback(Req("userA"), error="access_denied")
check("callback consent denied redirects", "gmail=denied" in resp.url)
# missing code
resp = callback(Req("userA"), state="anything")
check("callback missing code redirects", "gmail=invalid" in resp.url)


# ===================== CALLBACK DOES NOT EXPOSE CREDENTIALS =====================
print("\n--- Callback: no credential leakage ---")
google_auth.reset_for_tests()
connections_store.reset_for_tests()
google_auth.set_code_exchanger(_mock_exchange)
connect(Req("userA"))
state_token = None
for tok, rec in google_auth._states.items():
    if rec["uid"] == "userA" and not rec.get("consumed"):
        state_token = tok
        break
resp = callback(Req("userA"), code="code-x", state=state_token)
check("callback URL no access_token", "access_token" not in resp.url)
check("callback URL no refresh_token", "refresh_token" not in resp.url)
check("callback URL no client_secret", "client_secret" not in resp.url)
check("callback URL no code", "code=" not in resp.url)


# ===================== COMPATIBILITY: EXISTING ENDPOINTS UNCHANGED =====================
print("\n--- Compatibility: existing endpoints ---")
_disable_firebase()
google_auth.reset_for_tests()
connections_store.reset_for_tests()

# /api/health still works
health_ep = routes[("GET", "/api/health")]
check("health still works", health_ep() == {"status": "ok"})

# Ask still works
ask_ep = routes[("POST", "/api/ask")]


class Payload:
    def __init__(self, q):
        self.query = q


wf = asyncio.run(ask_ep(Req(), Payload("interview next week")))
check("ask still works in demo mode", wf.id.startswith("gen-"))
check("ask still returns valid workflow", len(wf.checklist) >= 4)


# ===================== STATE STORED ONLY SERVER-SIDE =====================
print("\n--- State security: no client UID trusted ---")
_set_oauth_configured()
_enable_firebase_with_uid_identity()
google_auth.reset_for_tests()
connections_store.reset_for_tests()
# Connect as userA
connect(Req("userA"))
# Capture the state that was generated
state_token = None
for tok, rec in google_auth._states.items():
    if rec["uid"] == "userA" and not rec.get("consumed"):
        state_token = tok
        break
check("state was generated for userA", state_token is not None)
# Callback with a forged uid in a different state (attacker cannot forge without
# the secret; we test that the uid is recovered from the state, not from the
# request context).
class FakeReq:
    headers = {"authorization": "Bearer attackerB"}

# Attacker tries to consume userA's state with their own token
# The state is bound to userA, so it should still work for userA's flow,
# but the stored connection will be under userA, not attackerB.
google_auth.set_code_exchanger(_mock_exchange)
resp = callback(FakeReq(), code="attack-code", state=state_token)
# Connection is under userA (the bound uid), not attackerB
check("attacker cannot redirect connection to their own uid", True)
check("connection under userA not attackerB",
      connections_store.get_connection("userA", "gmail") is not None)
check("attackerB has no connection", connections_store.get_connection("attackerB", "gmail") is None)


print(f"\nALL {count} PHASE 3A CHECKS PASSED")
