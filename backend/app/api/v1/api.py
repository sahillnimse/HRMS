"""API v1 router aggregator."""

from fastapi import APIRouter

from app.api.v1.endpoints import audit, auth, candidates, jobs, resumes, skills

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(resumes.router, prefix="/resumes", tags=["resumes"])
api_router.include_router(candidates.router, prefix="/candidates", tags=["candidates"])
api_router.include_router(jobs.jobs_router, prefix="/jobs", tags=["jobs"])
api_router.include_router(jobs.applications_router, prefix="/applications", tags=["applications"])
api_router.include_router(skills.router, prefix="/skills", tags=["skills"])
api_router.include_router(audit.router, prefix="/audit-logs", tags=["audit-logs"])
