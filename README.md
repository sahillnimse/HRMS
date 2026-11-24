# HRMS AI — AI-Powered Resume Parser & Candidate Manager

Production-ready HRMS where HR teams upload candidate CVs (PDF/DOCX) and get a
simplified, structured candidate profile parsed by Google Gemini with
human-in-the-loop review before saving to PostgreSQL.

## Tech Stack

- **Frontend:** React (Vite), Tailwind CSS, Lucide Icons, `react-dropzone`
- **Backend:** Python (FastAPI), Pydantic v2, SQLAlchemy (async) + `asyncpg`
- **Database:** PostgreSQL (JSONB for nested resume sections, indexed columns for search)
- **AI:** Google Gemini (`google-genai`) with Structured Outputs
- **Storage:** Local (dev) with abstraction layer for Supabase Storage / Cloudflare R2

## Monorepo Layout

```
hrms-ai/
├── backend/          # FastAPI app
├── frontend/         # React + Vite app
├── docker-compose.yml
├── vercel.json
├── backend/render.yaml
└── README.md
```

## Quick Start (Docker Compose)

```bash
# 1. Copy env files
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env

# 2. Edit backend/.env and add your GEMINI_API_KEY

# 3. Start everything
docker-compose up --build

# Services:
# - Frontend:  http://localhost:5173
# - Backend:   http://localhost:8000
# - API Docs:  http://localhost:8000/docs
# - DB:        localhost:5432
```

## Manual Setup

### Backend

```bash
cd backend
pip install -r requirements.txt
# Set DATABASE_URL and GEMINI_API_KEY in .env
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

## Deployment

### Backend — Render

1. Push code to GitHub.
2. In Render, create a **Web Service** from the `backend/` directory using `Dockerfile`.
3. Add environment variables from `backend/.env.example` (especially `GEMINI_API_KEY`, `SECRET_KEY`, `CORS_ORIGINS`).
4. Create a **PostgreSQL** database on Render (or use Supabase/Render DB) and set `DATABASE_URL`.
5. Deploy.

See `backend/render.yaml` for a Render blueprint example.

### Database — Supabase / Render

- Use standard indexed columns + JSONB as defined in `backend/app/models/candidate.py`.
- Connection string format: `postgresql+asyncpg://user:pass@host:5432/db`

### Frontend — Vercel

1. Connect the `frontend/` directory to Vercel.
2. Set build command: `npm run build`, output directory: `dist`.
3. Add env var: `VITE_API_BASE_URL=https://your-backend.onrender.com/api/v1`.
4. Deploy.

See `vercel.json`.

## Core Features

1. **`POST /api/v1/resumes/upload`** — Upload PDF/DOCX, extract text, parse with Gemini
   structured output, check PostgreSQL for duplicates by email/phone.
2. **Human-in-the-loop Review** — Editable form next to original resume preview;
   HR fixes errors before clicking "Save Candidate".
3. **Candidate Dashboard** — Searchable/filterable table/cards; filter by skills,
   domain, years of experience; click to view full profile and download CV.

## Storage Abstraction

`backend/app/services/file_storage.py` defines `BaseStorage`. `LocalStorage` is
the dev implementation. To swap to Supabase Storage or Cloudflare R2, subclass
`BaseStorage` — no route or CRUD changes needed.
