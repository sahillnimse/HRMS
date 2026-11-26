"""API v1 router aggregator."""

from fastapi import APIRouter

from app.api.v1.endpoints import (
    analytics,
    audit,
    auth,
    candidates,
    emails,
    interviews,
    jobs,
    offers,
    privacy,
    resumes,
    skills,
)

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(resumes.router, prefix="/resumes", tags=["resumes"])
api_router.include_router(candidates.router, prefix="/candidates", tags=["candidates"])
api_router.include_router(jobs.jobs_router, prefix="/jobs", tags=["jobs"])
api_router.include_router(jobs.applications_router, prefix="/applications", tags=["applications"])
api_router.include_router(interviews.interviews_router, prefix="/interviews", tags=["interviews"])
api_router.include_router(
    interviews.scorecard_templates_router,
    prefix="/scorecard-templates",
    tags=["scorecard-templates"],
)
api_router.include_router(
    emails.email_templates_router,
    prefix="/email-templates",
    tags=["email-templates"],
)
api_router.include_router(emails.emails_router, prefix="/emails", tags=["emails"])
api_router.include_router(offers.router, prefix="/offers", tags=["offers"])
api_router.include_router(skills.router, prefix="/skills", tags=["skills"])
api_router.include_router(audit.router, prefix="/audit-logs", tags=["audit-logs"])
api_router.include_router(privacy.router, prefix="/privacy", tags=["privacy"])
api_router.include_router(analytics.router, prefix="/analytics", tags=["analytics"])
