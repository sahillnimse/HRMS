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
| `ENABLE_SEMANTIC_SEARCH` / `EMBEDDING_MODEL` / `EMBEDDING_DIMENSIONS` | Feature-flagged pgvector + Gemini semantic search & matching | `true` / `gemini-embedding-001` / `768` |
| `SECRET_KEY` | JWT signing key (must be ≥32 random chars in `production`) | `change-me-in-production` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Short-lived access JWT TTL in minutes | `15` |
| `REFRESH_TOKEN_EXPIRE_DAYS` | Rotating `HttpOnly` refresh cookie TTL in days | `7` |
| `REFRESH_COOKIE_NAME` / `REFRESH_COOKIE_SECURE` / `REFRESH_COOKIE_SAMESITE` | Refresh cookie settings (`Secure` auto-enabled in production) | `hrms_refresh_token` / auto / `lax` |
| `LOGIN_MAX_ATTEMPTS` / `LOGIN_WINDOW_MINUTES` / `LOGIN_LOCKOUT_MINUTES` | Login brute-force throttling & lockout window | `5` / `15` / `15` |
| `BOOTSTRAP_ADMIN_EMAIL` / `BOOTSTRAP_ADMIN_PASSWORD` / `BOOTSTRAP_ADMIN_NAME` | Optional auto-seeded initial admin on startup | — |
| `STORAGE_BACKEND` | `local` (default), `s3`, or `r2` | `local` |
| `S3_ENDPOINT_URL`, `S3_BUCKET`, `S3_REGION`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `S3_PREFIX` | Cloudflare R2 / S3 credentials when `STORAGE_BACKEND` is `s3` or `r2` | — |
| `ORPHAN_MAX_AGE_HOURS` / `ORPHAN_CLEANUP_INTERVAL_MINUTES` / `ENABLE_CLEANUP_SCHEDULER` | Scheduled cleanup of unattached `pending` resume files | `24` / `60` / `true` |
| `RETENTION_DAYS` | Candidate data retention window in days (`0` disables automatic purge) | `365` |
| `ENABLE_OCR_FALLBACK` / `OCR_MIN_TEXT_LENGTH` | Automatic OCR fallback (Tesseract / Gemini multimodal) for scanned PDFs | `true` / `40` |
| `BULK_UPLOAD_MAX_FILES` / `REDIS_URL` | Bulk upload batch limit and optional Redis/ARQ worker queue (falls back to FastAPI `BackgroundTasks`) | `25` / — |
| `DUPLICATE_NAME_SIMILARITY_THRESHOLD` | `pg_trgm` fuzzy name duplicate threshold (`0.0`–`1.0`) | `0.6` |
| `CORS_ORIGINS` | Allowed frontend origins (JSON array or comma-separated) | `["http://localhost:5173"]` |

## Roles & Permissions

- **`admin`**: Full access + user management (`POST/GET /api/v1/auth/users`) + manual orphan cleanup (`POST /api/v1/resumes/cleanup`).
- **`recruiter`**: Upload/parse resumes, create/edit/delete candidates, view profiles & stream resumes.
- **`viewer`**: Read-only access (dashboard, candidate profiles, stats, authenticated resume viewing/downloading).

## Deployment Topology (Vercel + Render + Neon + R2)

```text
Browser (https://your-app.vercel.app)
   │  same-origin requests to /api/v1/* (HttpOnly; SameSite=Lax; Secure cookie)
   ▼
Vercel Edge (vercel.json)
   ├── /api/(.*)  ──► https://<your-render-service>.onrender.com/api/$1
   └── /(.*)      ──► /index.html (React SPA)
                         │
                         ▼
                  Render Web Service (FastAPI + Alembic preDeployCommand)
                    ├── Neon Lakebase Postgres (pooled DATABASE_URL + unpooled migrations)
                    └── Cloudflare R2 / S3 (STORAGE_BACKEND=r2, streamed via auth endpoints)
```

### Why `/api/(.*)` is rewritten through Vercel
The authentication refresh cookie uses `HttpOnly; SameSite=Lax; Secure; Path=/api/v1/auth`. If the browser called Render directly on a different domain (`*.onrender.com` from `*.vercel.app`), browsers would treat it as cross-site and withhold the `SameSite=Lax` refresh cookie. Proxying `/api/(.*)` through `vercel.json` keeps all API and auth calls strictly same-origin.

### Required deployment settings
1. **Vercel (`vercel.json`):**
   - Replace `https://hrms-ai-backend.onrender.com` in `vercel.json` with your actual Render Web Service URL.
   - Keep `VITE_API_BASE_URL=/api/v1` (relative — do **not** point it directly at `onrender.com`).
2. **Render (`backend/render.yaml`):**
   - `preDeployCommand: alembic upgrade head` applies migrations automatically before traffic switches (the Dockerfile `CMD` also runs `alembic upgrade head`).
   - Set `REFRESH_COOKIE_SAMESITE=lax` and `REFRESH_COOKIE_SECURE=true` (consistent with HTTPS same-site via Vercel).
   - Set `STORAGE_BACKEND=r2` and supply `S3_ENDPOINT_URL`, `S3_BUCKET`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `GEMINI_API_KEY`, and `CORS_ORIGINS=https://your-app.vercel.app`.

## Running Tests

```bash
cd backend
pytest
```

```bash
cd frontend
npx tsc --noEmit && npm run build
```
