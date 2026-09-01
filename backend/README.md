# GoogleFlow Backend — MVP (Day 1)

FastAPI backend that powers the **Ask LifeFlow → Gemini → Generated LifeFlow →
Workflow Details** flow for the GoogleFlow frontend.

## Stack

- Python 3.11+
- FastAPI + Uvicorn
- Pydantic v2 (validation matches `src/types/workflow.ts`)
- `google-genai` (official Gemini SDK)

## Project layout

```
backend/
├── app/
│   ├── main.py            # FastAPI app + routes
│   ├── schemas.py         # Pydantic models mirroring the frontend contract
│   ├── gemini_service.py  # Gemini prompt, parsing, validation + demo fallback
│   └── workflow_store.py  # temporary in-memory workflow storage
├── requirements.txt
└── .env.example           # GEMINI_API_KEY lives here (backend only)
```

## Setup

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env       # then paste your real Gemini API key
```

## Run

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Health check: `curl http://localhost:8000/api/health`

## API

| Method | Path                    | Description                                  |
|--------|-------------------------|----------------------------------------------|
| GET    | `/api/health`           | `{"status": "ok"}`                           |
| POST   | `/api/ask`              | `{"query": "..."}` → creates & stores a LifeFlow |
| GET    | `/api/workflows`        | Lists workflows generated this session       |
| GET    | `/api/workflows/{id}`   | Single generated workflow (404 if unknown)   |

### Example

```bash
curl -X POST http://localhost:8000/api/ask \
  -H "Content-Type: application/json" \
  -d '{"query": "I have a passport appointment tomorrow at 10:30 AM in Hyderabad. I need to carry my Aadhaar card, PAN card and passport copies."}'
```

Response is a `Workflow` JSON object matching the frontend `Workflow` type.

## Environment variables (backend only)

| Variable        | Required | Default            | Notes                                |
|-----------------|----------|--------------------|--------------------------------------|
| `GEMINI_API_KEY`| Yes*     | —                  | Real key for live Gemini generation. |
| `GEMINI_MODEL`  | No       | `gemini-2.5-flash` | Any stable model your key can access.|
| `CORS_ORIGINS`  | No       | `localhost:5173,5174` | Comma-separated dev origins.      |

\* Without a key, the backend runs in **demo mode** using a small deterministic
fallback generator that produces the same structured LifeFlow shape — the full
frontend flow works end-to-end, but content is canned, not AI-generated.

## Security note

`GEMINI_API_KEY` is read **only** from the backend environment. Never put it in
`.env` next to the React app, in Vite `import.meta.env`, or in any committed file.

## CORS

Restricted to localhost:5173 / 5174 by default (override with `CORS_ORIGINS`).

## Later phases (not implemented)

Auth (Firebase/Google Sign-In), Gmail/Calendar/Drive/Maps API access, real
persistence (Firebase/Firestore), deployment (Cloud Run).