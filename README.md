# Datacove AI — Complete Project

> AI-native data cleaning, profiling, and ML platform.

## Project structure

```
datacove_complete/
├── backend/          FastAPI backend (Python 3.12)
│   ├── main.py
│   ├── config.py
│   ├── requirements.txt
│   ├── Dockerfile
│   ├── docker-compose.yml
│   ├── .env.example       ← copy to .env and fill in values
│   ├── sample_datasets/   ← 3 sample CSVs for onboarding
│   ├── routes/            ← 20 route files
│   ├── services/          ← 20+ business logic services
│   ├── models/
│   ├── utils/
│   └── tests/             ← pytest unit tests
│
└── frontend/         React + Vite frontend
    └── src/
        ├── App.jsx
        ├── pages/         ← UploadPage, Dashboard, DatasetsPage
        ├── components/    ← 25 panel components
        ├── services/
        │   └── api.js     ← all API calls
        └── hooks/
```

---

## Quick start

### 1. Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Set up environment
cp .env.example .env
# Edit .env:
#   JWT_SECRET=<run: python -c "import secrets; print(secrets.token_hex(32))">
#   CORS_ORIGINS=http://localhost:5173
#   AUTH_ENABLED=true
#   ANTHROPIC_API_KEY=<your key>   # optional — enables AI features

uvicorn main:app --reload --port 8000
# API docs: http://localhost:8000/docs
```

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
# App: http://localhost:5173
```

### 3. Docker (both together)

```bash
docker-compose up --build
```

---

## Phases completed

### Phase 1 — Security (ship-blockers)
- Auth enabled by default, JWT secret validated at startup
- CORS locked to configured origins (not wildcard)
- SQLite-persisted user accounts (survive restarts)
- Per-user salted password hashing (PBKDF2-SHA256)
- Auth dependency on all protected routes
- `.bak` file removed, `.gitignore` hardened

### Phase 2 — Core product gaps
- User-scoped sessions (owner_id stamped, 403 on access by others)
- Sessions persisted to SQLite (survive restarts + memory eviction)
- `GET /api/sessions` — "My Datasets" listing
- `DELETE /api/sessions/{id}` — delete own dataset
- NL commands are two-step: parse (preview) → confirm (apply)
- 35+ unit tests across cleaning engine, health score, auth

### Phase 3 — Growth features
- **Onboarding**: 3 sample datasets, `/api/samples` catalogue + loader
- **Sharing**: share links with view/fork permissions + expiry + revoke
- **Schedules**: cron schedules + webhook triggers for pipelines
- **Connectors**: URL, Google Sheets, AWS S3, SQL database import
- **Billing**: free/pro/team tiers, usage tracking, Stripe checkout
- **Export destinations**: Google Sheets, Airtable, Notion, Slack

---

## Environment variables

See `.env.example` for full documentation. Key variables:

| Variable | Required | Description |
|---|---|---|
| `JWT_SECRET` | **Yes** | 32+ random bytes — generate with `secrets.token_hex(32)` |
| `AUTH_ENABLED` | **Yes** | Set `true` in production |
| `CORS_ORIGINS` | **Yes** | Your frontend domain(s), comma-separated |
| `ANTHROPIC_API_KEY` | No | Enables AI suggestions + NL commands |
| `STRIPE_SECRET_KEY` | No | Enables billing/upgrade flow |
| `GOOGLE_SA_JSON` | No | Enables Google Sheets connector + export |
| `AIRTABLE_API_KEY` | No | Enables Airtable export |
| `NOTION_API_KEY` | No | Enables Notion export |

---

## Running tests

```bash
cd backend
pip install pytest
pytest tests/ -v
```

---

## Optional dependencies

Uncomment in `requirements.txt` to enable:

| Package | Feature |
|---|---|
| `boto3` | AWS S3 connector |
| `gspread` + `google-auth` | Google Sheets connector + export |
| `stripe` | Billing / Stripe integration |
| `apscheduler` | Scheduled pipeline runs |
| `sqlalchemy` | SQL database connector |
