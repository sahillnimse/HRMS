"""API v1 router aggregator."""

from fastapi import APIRouter

from app.api.v1.endpoints import auth, candidates, resumes

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(resumes.router, prefix="/resumes", tags=["resumes"])
api_router.include_router(candidates.router, prefix="/candidates", tags=["candidates"])
