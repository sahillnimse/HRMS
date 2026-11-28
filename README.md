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
| `ENABLE_CANDIDATE_BRIEF` / `CANDIDATE_BRIEF_TIMEOUT_SECONDS` | Feature-flagged AI candidate brief generation (deterministic template fallback when off/unavailable) | `true` / `25` |
| `TIMELINE_GAP_THRESHOLD_MONTHS` / `SHORT_STINT_MAX_MONTHS` / `EXPERIENCE_MISMATCH_YEARS_THRESHOLD` | Career timeline gap threshold and neutral consistency-check thresholds (informational only) | `3` / `12` / `1.5` |
| `EDU_DURATION_BACHELORS_MONTHS` / `EDU_DURATION_MASTERS_MONTHS` / `EDU_DURATION_DIPLOMA_MONTHS` / `EDU_ESTIMATED_GRADUATION_MONTH` | Estimated education study window lengths (months) and default graduation month (`6` = June) when a CV lists graduation year only | `48` / `24` / `36` / `6` |
| `COUNT_INTERNSHIPS_IN_EXPERIENCE` | Whether internship/trainee roles count toward stored `years_experience` (`true` preserves default matching behavior; briefs always show full-time + internship split) | `true` |
| `DEFAULT_TIMEZONE` / `CALENDAR_PROVIDER` | Display timezone (`Asia/Kolkata`) and calendar provider (`ics`; Google/Outlook future extension point) | `Asia/Kolkata` / `ics` |
| `EMAIL_BACKEND` / `SMTP_*` | Pluggable email sender (`console` dev default, or `smtp` with `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM_EMAIL`, `SMTP_USE_TLS`) | `console` / `587` |
| `STUCK_APPLIED_DAYS` / `STUCK_SCREENED_DAYS` / `STUCK_INTERVIEW_DAYS` / `STUCK_OFFER_DAYS` | Default per-stage thresholds (days) for stuck-candidate analytics | `7` / `7` / `10` / `7` |
| `ENABLE_INTERVIEW_QUESTIONS` / `ENABLE_NL_SEARCH` | Feature flags for AI interview question generation & natural-language candidate search (both have deterministic fallbacks) | `true` / `true` |
| `INBOUND_EMAIL_WEBHOOK_SECRET` | Shared `X-Inbound-Webhook-Secret` header for automated email-to-inbox CV ingestion webhooks | — |
| `SENTRY_DSN` / `SENTRY_TRACES_SAMPLE_RATE` | Optional Sentry error monitoring (`send_default_pii=False` strictly enforced when enabled) | — / `0.1` |
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

- **`admin`**: Full access + user management (`POST/GET /api/v1/auth/users`) + manual orphan cleanup (`POST /api/v1/resumes/cleanup`) + retention purge (`POST /api/v1/privacy/purge-expired`).
- **`recruiter`**: Upload/parse resumes (single & bulk), create/edit/delete candidates, regenerate candidate briefs, manage jobs/pipelines, score matches, view profiles & stream/export resumes.
- **`viewer`**: Read-only access (dashboard, candidate profiles/briefs/timelines, stats, matches, compare, authenticated resume viewing & CTC-redacted exports).

## Key Phase 4 Endpoints (Candidate Clarity)

- `GET /api/v1/candidates/{id}/brief?blind=false` — Lazy-generated, cached candidate brief (≤5-line summary, 2–4 strengths, 0–4 neutral "worth verifying" items; refreshes automatically when job-relevant profile fields change).
- `POST /api/v1/candidates/{id}/brief/regenerate` — Force-regenerate a candidate brief (`admin` / `recruiter`).
- `GET /api/v1/candidates/{id}/timeline?gap_months=3&blind=false` — Normalized career timeline, study windows (real or estimated from graduation year), gap & overlap markers, employment-type-aware tenure statistics, whole-CV skill evidence, and informational-only consistency checks.
- `POST /api/v1/candidates/admin/remap-sections?dry_run=true&limit=100` — Admin-only re-mapping of legacy candidates' education dates, work `employment_type`, and `projects` from stored resume files/text (dry-run by default; skips hand-edited sections). CLI equivalent: `python -m app.scripts.remap_sections [--apply]`.
- `GET /api/v1/jobs/{id}/shortlist/export/pdf?candidate_ids=...&blind=false` — Multi-page Shortlist Pack PDF (one page per candidate: brief, timeline summary, top skills, JD skill-gap & match explanation; omits CTC for `viewer`; audit-logged).

## Key Phase 5 Endpoints (Interview Workflow)

- `POST/GET /api/v1/applications/{id}/interviews`, `GET/PATCH/DELETE /api/v1/interviews/{id}`, `GET /api/v1/interviews/mine`, `GET /api/v1/interviews/{id}/ics` — Interview scheduling, participant assignment, UTC storage with `Asia/Kolkata` display, and RFC 5545 `.ics` calendar invite download (`CalendarProvider` abstraction with Google/Outlook extension point).
- `GET/POST/PATCH /api/v1/scorecard-templates`, `GET/POST /api/v1/interviews/{id}/scorecards` — Structured 1–5 competency scorecards with blind-interviewer enforcement (assigned participants cannot see peer scorecards until submitting their own) and viewer aggregate-only visibility.
- `GET/POST/PATCH /api/v1/email-templates`, `POST /api/v1/emails/preview`, `POST /api/v1/emails/send`, `GET /api/v1/candidates/{id}/emails` — Templated candidate outreach via pluggable `EmailSender` (`console` dev default, `smtp` via env vars); automatic stage-change emails are OFF by default and rejection emails always require explicit manual confirmation.
- `POST/GET /api/v1/applications/{id}/offers`, `PATCH /api/v1/offers/{id}` — Offer management (`admin`/`recruiter` only, `expected_joining_date` defaulted from `notice_period_days`, auto-synced with `offer`/`hired` pipeline stages).

## Key Phase 6 Endpoints (Hiring Analytics — No Extra Migration)

All analytics metrics are derived directly from `application_events`, `applications`, `jobs`, and `candidates.source` (migration `0006`). Read-only for `admin`, `recruiter`, and `viewer`:

- `GET /api/v1/analytics/funnel?job_id=&start_date=&end_date=` — Stage reach, current stage counts, step-by-step and applied-to-stage conversion rates, and overall hire rate.
- `GET /api/v1/analytics/time-in-stage?job_id=&start_date=&end_date=` — Average, median, min, and max days spent per active stage from consecutive `ApplicationEvent` transitions.
- `GET /api/v1/analytics/time-to-hire?job_id=&start_date=&end_date=` — Average, median, min, and max days from application start to `hired`.
- `GET /api/v1/analytics/sources?job_id=&start_date=&end_date=` — Candidate volume, applications, screened/interviewed counts, hires, and hire rate grouped by `Candidate.source`.
- `GET /api/v1/analytics/stuck?job_id=&applied_days=&screened_days=&interview_days=&offer_days=&blind=false` — Active applications exceeding per-stage SLA thresholds (blind-mode aware).

## High-ROI Backlog Endpoints

- `POST /api/v1/candidates/{id}/interview-questions` — Generate fair, tailored interview questions grounded in projects, JD skill gaps/adjacent skills, and neutral "worth verifying" prompts (Gemini structured output + deterministic fallback).
- `POST /api/v1/candidates/nl-search` — Natural-language search (`"Python, 3+ yrs, Pune, notice < 30 days"`) parsed into structured filters + existing hybrid/semantic search (deterministic regex fallback when AI is off).
- `GET/POST/DELETE /api/v1/talent-pools`, `GET/POST/DELETE /api/v1/talent-pools/{id}/members`, `GET /api/v1/jobs/{id}/resurface` — Curated talent pools & automatic silver-medalist resurfacing (past `interview`/`offer` near-misses scored against new jobs).
- `POST /api/v1/resumes/inbound-email`, `GET /api/v1/resumes/inbound-logs` — Idempotent email-to-inbox CV ingestion webhook (`X-Inbound-Webhook-Secret` or recruiter/admin Bearer JWT) feeding PDF/DOCX attachments straight into the bulk review queue.
- `GET/POST /api/v1/privacy/erasure-requests`, `POST /api/v1/privacy/erasure-requests/{id}/execute` — India DPDP Act erasure & consent-withdrawal ledger with admin-executed full PII/file deletion and PII-free compliance proof.
- **Playwright E2E Smoke Suite:** `frontend/e2e/smoke.spec.ts` (run locally via `npx playwright test frontend/e2e/smoke.spec.ts`).

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
