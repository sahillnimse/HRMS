# HRMS AI — AI-Powered Resume Parser & Candidate Manager

Production-ready HRMS where HR teams upload candidate CVs (PDF/DOCX), inspect an auto-generated candidate profile & interactive skill network graph, resolve duplicates, and manage candidates in PostgreSQL (Neon).

## Tech Stack

- **Frontend:** React 18 (Vite), TypeScript, Tailwind CSS, Lucide Icons, `react-dropzone`
- **Backend:** Python (FastAPI), Pydantic v2, SQLAlchemy 2.0 async + `asyncpg`, Alembic migrations
- **Auth:** Argon2id password hashing + PyJWT bearer tokens with role-based access (`admin`, `recruiter`, `viewer`)
- **Database:** PostgreSQL / Neon Lakebase Postgres (JSONB + `pg_trgm` fuzzy name matching)
- **AI:** Google Gemini (`google-genai`) structured output (also supports OpenRouter)
- **Storage:** `BaseStorage` abstraction — `LocalStorage` (dev default) and `S3Storage` (Cloudflare R2 / S3) with authenticated file streaming

## Quick Start (Manual)

### 1. Backend

```bash
cd backend
cp .env.example .env
# Edit backend/.env with DATABASE_URL, DATABASE_URL_UNPOOLED, GEMINI_API_KEY, SECRET_KEY

python -m venv venv
# Windows: venv\Scripts\activate  |  macOS/Linux: source venv/bin/activate
pip install -r requirements.txt

# Apply database migrations (uses DATABASE_URL_UNPOOLED)
alembic upgrade head

# Create an initial admin account
python -m app.scripts.create_admin --email admin@company.com --password "strong-password" --name "Admin" --role admin

# Start API server
uvicorn app.main:app --reload --port 8000
```

### 2. Frontend

```bash
cd frontend
cp .env.example .env
npm install
npm run dev
```

- **Frontend:** http://localhost:5173 (sign in at `/login`)
- **Backend API Docs:** http://localhost:8000/docs

## Environment Variables (`backend/.env.example`)

| Variable | Description | Default |
|---|---|---|
| `APP_ENV` | `development` or `production` (production enforces strong `SECRET_KEY`) | `development` |
| `DATABASE_URL` | Pooled async Postgres URL for app traffic | local Postgres |
| `DATABASE_URL_UNPOOLED` | Direct Postgres URL used by Alembic migrations | — |
| `GEMINI_API_KEY` / `GEMINI_MODEL` | Google Gemini (or OpenRouter `sk-or-`) key & model | `gemini-2.0-flash` |
| `SECRET_KEY` | JWT signing key (must be ≥32 random chars in `production`) | `change-me-in-production` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | JWT expiration window in minutes | `60` |
| `BOOTSTRAP_ADMIN_EMAIL` / `BOOTSTRAP_ADMIN_PASSWORD` / `BOOTSTRAP_ADMIN_NAME` | Optional auto-seeded initial admin on startup | — |
| `STORAGE_BACKEND` | `local` (default), `s3`, or `r2` | `local` |
| `S3_ENDPOINT_URL`, `S3_BUCKET`, `S3_REGION`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `S3_PREFIX` | Cloudflare R2 / S3 credentials when `STORAGE_BACKEND` is `s3` or `r2` | — |
| `ORPHAN_MAX_AGE_HOURS` / `ORPHAN_CLEANUP_INTERVAL_MINUTES` / `ENABLE_CLEANUP_SCHEDULER` | Scheduled cleanup of unattached `pending` resume files | `24` / `60` / `true` |
| `DUPLICATE_NAME_SIMILARITY_THRESHOLD` | `pg_trgm` fuzzy name duplicate threshold (`0.0`–`1.0`) | `0.6` |
| `CORS_ORIGINS` | Allowed frontend origins (JSON array or comma-separated) | `["http://localhost:5173"]` |

## Roles & Permissions

- **`admin`**: Full access + user management (`POST/GET /api/v1/auth/users`) + manual orphan cleanup (`POST /api/v1/resumes/cleanup`).
- **`recruiter`**: Upload/parse resumes, create/edit/delete candidates, view profiles & stream resumes.
- **`viewer`**: Read-only access (dashboard, candidate profiles, stats, authenticated resume viewing/downloading).

## Running Tests

```bash
cd backend
pytest
```

```bash
cd frontend
npx tsc --noEmit && npm run build
```
