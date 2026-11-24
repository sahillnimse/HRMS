"""API v1 router aggregator."""

from fastapi import APIRouter

from app.api.v1.endpoints import resumes, candidates

api_router = APIRouter()

api_router.include_router(resumes.router, prefix="/resumes", tags=["resumes"])
api_router.include_router(candidates.router, prefix="/candidates", tags=["candidates"])
