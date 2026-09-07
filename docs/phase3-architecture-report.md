# Phase 3, Step 1: Authentication & Google Apps Connection Architecture Report

## 1. Current Authentication Architecture

### Frontend Layer
| Component | File | Responsibility |
|---|---|---|
| Firebase Config | `src/config/firebase.ts` | Reads `VITE_FIREBASE_*` env vars, initializes Firebase app, exports `firebaseAuth` |
| Auth Service | `src/services/authService.ts` | ONLY place that talks to Firebase Auth. `signInWithGoogle()`, `signOut()`, `getIdToken()` |
| Auth Hook | `src/hooks/useAuthUser.ts` | React binding: `{ user, loading, signedIn, isAuthEnabled }` |
| HTTP Layer | `src/services/http.ts` | Single `fetch()` wrapper, accepts auth headers |
| Workflow Service | `src/services/workflowService.ts` | Attaches Firebase ID token as `Bearer` to protected calls |

### Backend Layer
| Component | File | Responsibility |
|---|---|---|
| FastAPI Routes | `backend/app/main.py` | Endpoints + `_require_uid()` for token verification |
| Firebase Service | `backend/app/firebase_service.py` | Admin SDK init, `verify_id_token()`, `get_firestore()` |
| Workflow Store | `backend/app/workflow_store.py` | Persistence (Firestore or in-memory demo) |
| Schemas | `backend/app/schemas.py` | Pydantic models matching frontend types |

---

## 2. Exact Authentication Flow (File/Function Reference)

```
User clicks "Continue with Google"
    ↓
[Profile.tsx / Ask.tsx] handleSignIn()
    ↓
[authService.ts:76] signInWithGoogle()
    ├── new GoogleAuthProvider()
    ├── provider.setCustomParameters({ prompt: 'select_account' })
    └── signInWithPopup(firebaseAuth, provider)  ← Firebase popup
            ↓
    Firebase returns User object (contains uid, displayName, email, photoURL)
            ↓
[authService.ts:41] onAuthStateChanged() fires → currentUser = user → notify()
    ↓
[useAuthUser.ts:20] setState() → signedIn = Boolean(state.user)
    ↓
[workflowService.ts:30] authHeaders() → getIdToken()
    ↓
[authService.ts:96] currentUser.getIdToken() ← Firebase ID token (JWT, temporary)
    ↓
[http.ts:65] apiPost('/api/ask', body, { headers: { Authorization: Bearer <token> } })
    ↓
[main.py:69] _require_uid(request)
    ├── If firebase_service.is_enabled() == False: return "" (demo mode)
    ├── Extract Bearer token from Authorization header
    └── firebase_service.verify_id_token(token) → uid
            ↓
[firebase_service.py:79] firebase_admin.auth.verify_id_token(token, app=_firebase_app)
    ↓
Returns verified UID (string)
    ↓
[workflow_store.py] users/{uid}/flows/{workflowId} (Firestore) OR in-memory dict (demo)
```

### Data Persistence
| Data | Persisted Where | Lifetime |
|---|---|---|
| Firebase User Session | Firebase Auth SDK (localStorage in browser) | Until sign-out or token expiry |
| Firebase ID token | Memory only (refreshed on demand via `getIdToken()`) | ~1 hour |
| Backend Workflows | Firestore `users/{uid}/flows/{id}` OR in-memory dict | Persistent / session-only |

---

## 3. Existing Google-Related Code Found

| Library | Location | Used? |
|---|---|---|
| `firebase/auth` (Web SDK) | `src/config/firebase.ts`, `src/services/authService.ts` | ✅ Yes — sign-in/sign-out |
| `firebase/firestore` (Web SDK) | `src/config/firebase.ts` | ❌ Imported but NOT used in app code |
| `firebase-admin` (Python) | `backend/app/firebase_service.py` | ✅ Yes — token verification |
| `google-genai` | `backend/app/gemini_service.py` | ✅ Yes — LifeFlow generation |
| `google-auth` (Python) | `backend/.deps/` | ❌ Installed (transitive dep), NOT used |
| `google-api-python-client` | `backend/.deps/` | ❌ Installed (transitive dep), NOT used |

**Conclusion:** There is NO existing Google Apps (Gmail/Calendar/Drive) authorization code. Only Firebase Authentication for identity.

---

## 4. Gap Between Firebase Authentication and Gmail API Authorization

### A. Current: Firebase Authentication (Identity)
- **Purpose:** Prove who the user is
- **Mechanism:** Google Sign-In popup → Firebase issues ID token
- **Scope:** `profile`, `email`, `openid` (basic identity)
- **Token:** Firebase ID token (JWT, ~1hr, no refresh token stored)
- **Access:** NO access to Gmail, Calendar, Drive data

### B. Required: Google OAuth Authorization (API Access)
- **Purpose:** Access user's Gmail/Calendar data with permission
- **Mechanism:** Google consent screen → OAuth 2.0 authorization code flow
- **Scopes:** `gmail.readonly`, `calendar.readonly`, etc.
- **Tokens:**
  - **Access token** (~1hr) — used to call APIs
  - **Refresh token** (long-lived) — used to get new access tokens
- **Critical difference:** Refresh tokens MUST be stored securely for offline access

### What's Missing
| Capability | Status |
|---|---|
| Google OAuth consent flow | ❌ Not implemented |
| Authorization code exchange | ❌ Not implemented |
| Access token management | ❌ Not implemented |
| Refresh token storage | ❌ Not implemented |
| Gmail API connector | ❌ Not implemented |
| Calendar API connector | ❌ Not implemented |
| Connection status tracking | ❌ Not implemented |
| Disconnect/revoke capability | ❌ Not implemented |
| Per-user token isolation | ❌ Not implemented |

---

## 5. Recommended Secure Architecture

### Design Principles
1. **Never expose refresh tokens to the frontend** — they live only in the backend
2. **Associate all Google connections with Firebase UID** — use UID as the key
3. **Use incremental authorization** — request minimum scopes first
4. **Store tokens encrypted at rest** — use Firestore with per-user isolation
5. **Support disconnect/revoke** — user can revoke access anytime

### Recommended Architecture

```
Frontend (React)                          Backend (FastAPI)
─────────────────                         ─────────────────
User clicks "Connect Gmail"
    ↓
[gmailService.ts]
  → redirect to
  /api/auth/gmail/connect
                  ──────────────────→     [main.py]
                                          → Generate Google OAuth URL
                                          → Store state + Firebase UID
                                          → Redirect to Google consent
                                                 ↓
User consents to Gmail.readonly            Google consent screen
                                                 ↓
                                          Google redirects to
                                          /api/auth/gmail/callback
                  ──────────────────→     [main.py]
                                          → Verify state (CSRF protection)
                                          → Exchange code for tokens
                                          → Store {accessToken, refreshToken}
                                              encrypted under users/{uid}/connections/gmail
                                          → Redirect back to frontend
    ↓
[gmailService.ts]
  → Show "Gmail connected" status
    ↓
Future: Fetch important emails
  → GET /api/gmail/messages
                  ──────────────────→     [main.py]
                                          → Retrieve refresh token
                                          → Refresh access token if needed
                                          → Call Gmail API
                                          → Return normalized messages
    ↓
[Future Gemini extraction]
  → Detect events → Create LifeFlows
```

### Token Handling
| Token | Where Stored | How Protected |
|---|---|---|
| Access token | Backend memory (short-lived) | Never persisted long-term |
| Refresh token | Firestore `users/{uid}/connections/gmail` | Encrypted at rest, isolated by UID |
| Firebase ID token | Frontend memory only | Refreshed on demand |

### UID Association
```
Firestore structure:
users/{firebaseUid}/
  ├── flows/{workflowId}          ← existing workflows
  └── connections/
      ├── gmail                   ← Gmail connection record
      │   ├── refreshToken (encrypted)
      │   ├── scopes
      │   ├── connectedAt
      │   └── expiresAt
      └── calendar                ← Future Calendar connection
```

---

## 6. Recommended Gmail-First OAuth Scope

### Minimum Scope: `https://www.googleapis.com/auth/gmail.readonly`

**Why this scope:**
| Aspect | Details |
|---|---|
| Read-only | Cannot send, delete, or modify emails — safer for users |
| Access | Read messages, threads, labels, and metadata |
| No compose/send | We only need to DETECT events, not interact |

**What we can do with `gmail.readonly`:**
- List messages with filters (e.g., `newer_than:7d`, `subject:interview`)
- Get message metadata (subject, from, date, snippet)
- Get full message content (body, attachments info)
- Read labels and folders

**What we CANNOT do (intentionally):**
- Send emails
- Delete or modify emails
- Create drafts or labels

### Privacy & Implementation Trade-offs

| Approach | Pros | Cons |
|---|---|---|
| `gmail.readonly` (full) | Can search/filter on server | Broad permission — users may hesitate |
| `gmail.metadata` (future alternative) | More privacy-preserving — only headers | Can't read message body content |

**Recommendation:** Start with `gmail.readonly` but implement **server-side filtering**:
- Only fetch emails matching specific criteria (events, appointments, deadlines)
- Never download the full mailbox
- Process emails server-side, send only extracted events to Gemini
- Raw email content never persisted long-term

---

## 7. Required Future Backend Endpoints

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/auth/gmail/connect` | GET | Generate OAuth URL, redirect to Google consent |
| `/api/auth/gmail/callback` | GET | Handle consent callback, exchange code, store tokens |
| `/api/auth/gmail/status` | GET | Check if user has connected Gmail |
| `/api/auth/gmail/disconnect` | POST | Revoke tokens, delete connection |
| `/api/gmail/messages` | GET | Fetch filtered emails (server-side filtering) |
| `/api/gmail/sync` | POST | Trigger email analysis → event detection |
| `/api/events` | GET | List detected events from Gmail |

---

## 8. Proposed Data Model for User Google Connections

```python
# Firestore: users/{firebaseUid}/connections/gmail
class GmailConnection(BaseModel):
    refresh_token: str          # Encrypted at rest
    access_token: str           # Ephemeral, refreshed as needed
    token_uri: str              # https://oauth2.googleapis.com/token
    client_id: str              # Google OAuth client ID
    client_secret: str          # Google OAuth client secret (encrypted)
    scopes: list[str]            # ["https://www.googleapis.com/auth/gmail.readonly"]
    connected_at: str           # ISO timestamp
    expires_at: str             # Token expiry
    last_sync_at: str | null    # Last successful sync
    is_active: bool             # False when revoked

# Firestore: users/{firebaseUid}/events/{eventId}
class DetectedEvent(BaseModel):
    source: str                 # "gmail"
    source_id: str              # Gmail message ID
    title: str                  # Extracted event title
    description: str            # Event details
    event_date: str | null      # When the event occurs
    event_type: str             # "interview", "appointment", "deadline"
    confidence: float           # 0-1, Gemini's confidence
    status: str                 # "pending", "accepted", "dismissed"
    created_flow_id: str | null # If user accepted → created LifeFlow
```

---

## 9. Security Considerations

| Risk | Mitigation |
|---|---|
| Refresh token theft | Store encrypted in Firestore, never expose to frontend |
| Cross-user data access | All queries scoped by Firebase UID — never trust client-provided UID |
| CSRF on OAuth callback | Verify `state` parameter matches stored value |
| Token leakage in logs | Never log access tokens or refresh tokens |
| Over-requesting scopes | Use incremental authorization — Gmail only, minimum scope |
| Stale tokens | Auto-refresh with refresh token; handle 401 by re-authing |
| User disconnect | Revoke token via Google API + delete Firestore record |
| Email content exposure | Server-side filtering, only extracted events stored, raw emails not persisted |

---

## 10. Exact Next Implementation Steps

### Phase 3A — Google Apps Connection Foundation
1. Create Google Cloud OAuth 2.0 credentials (Web application)
2. Add OAuth consent screen with `gmail.readonly` scope
3. Create `backend/app/google_auth.py` — OAuth URL generation + callback handling
4. Create `backend/app/models.py` (or extend schemas.py) — `GmailConnection` model
5. Add Firestore collections for `connections` and `events`
6. Implement token encryption/decryption for refresh tokens

### Phase 3B — Gmail Authorization
1. Implement `GET /api/auth/gmail/connect` → redirect to Google
2. Implement `GET /api/auth/gmail/callback` → exchange code, store tokens
3. Implement `GET /api/auth/gmail/status` → connection status
4. Implement `POST /api/auth/gmail/disconnect` → revoke + delete
5. Add frontend `src/services/gmailService.ts` — connection management

### Phase 3C — Gmail Connector
1. Install `google-api-python-client` and `google-auth-oauthlib` explicitly
2. Create `backend/app/gmail_connector.py` — fetch filtered messages
3. Implement server-side filtering (date range, keywords)
4. Normalize Gmail API response → internal event format

### Phase 3D — Event Detection
1. Filter messages for event-like content (interviews, appointments, deadlines)
2. Extract structured data (date, time, location, participants)
3. Send to Gemini for analysis and LifeFlow suggestion

### Phase 3E — LifeFlow Creation
1. Gemini analyzes detected events → suggests LifeFlows
2. Duplicate detection (don't create same LifeFlow twice)
3. Persist to Firestore under user's UID
4. Frontend shows suggested LifeFlows for user acceptance

---

## 11. Files That Will Likely Need Changes

| File | Change |
|---|---|
| `backend/app/main.py` | Add OAuth routes + Gmail API routes |
| `backend/app/firebase_service.py` | No changes needed (already handles UID) |
| `backend/app/schemas.py` | Add `GmailConnection`, `DetectedEvent` models |
| `backend/app/google_auth.py` | **NEW** — OAuth flow + token management |
| `backend/app/gmail_connector.py` | **NEW** — Gmail API interaction |
| `backend/requirements.txt` | Add `google-api-python-client`, `google-auth-oauthlib` |
| `backend/.env.example` | Add `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET` |
| `src/services/gmailService.ts` | **NEW** — Frontend Gmail connection service |
| `src/pages/Profile.tsx` | Add "Connect Gmail" button |
| `src/types/` | Add `GmailConnection`, `DetectedEvent` types |

---

## 12. Risks & Blockers

| Risk | Impact | Mitigation |
|---|---|---|
| Google OAuth verification | New apps may require Google verification for sensitive scopes | Use `gmail.readonly` (sensitive but not restricted); for development, add test users in Google Cloud Console |
| Refresh token expiration | Tokens can expire if unused for 6 months | Implement token refresh logic; prompt re-auth if refresh fails |
| Firestore not configured | Can't persist connections | Falls back to demo mode OR requires Firebase setup |
| Gemini cost | Processing many emails via Gemini could be expensive | Server-side pre-filtering to minimize tokens sent to Gemini |
| User trust | Users may hesitate to grant Gmail access | Clear privacy policy; show exactly what we access; support easy disconnect |
| OAuth redirect URI mismatch | Common development pitfall | Register `http://localhost:8010/api/auth/gmail/callback` as authorized redirect URI |

---

## Summary

The current architecture has a clean separation:
- **Frontend:** Firebase Auth for identity, single `fetch` layer with bearer tokens
- **Backend:** Firebase Admin for verification, UID-scoped operations, demo mode fallback

To add Gmail access, we need to:
1. Add Google OAuth 2.0 flow (consent → code → tokens)
2. Store refresh tokens securely (Firestore, encrypted, per-UID)
3. Build Gmail connector with server-side filtering
4. Detect events → Gemini → LifeFlows

The existing `google-auth` and `google-api-python-client` libraries are already installed as transitive dependencies, so adding explicit usage will be straightforward.
