"""Shared pytest fixtures for async FastAPI integration tests."""

import os
import uuid

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

os.environ.setdefault("ENABLE_CLEANUP_SCHEDULER", "false")

from app.api.deps import get_db  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.core.rate_limit import login_rate_limiter  # noqa: E402
from app.crud.user import create_user  # noqa: E402
from app.db.session import _normalize_asyncpg_url  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models.candidate import Candidate, ResumeFile  # noqa: E402
from app.models.matching import SkillNormalization  # noqa: E402
from app.models.pipeline import AuditLog, Job  # noqa: E402
from app.models.user import User, UserRole  # noqa: E402

settings.ENABLE_CLEANUP_SCHEDULER = False


@pytest_asyncio.fixture(autouse=True)
async def reset_login_limiter():
    login_rate_limiter.reset()
    yield
    login_rate_limiter.reset()


@pytest_asyncio.fixture
async def db_session_factory():
    """Isolated NullPool async engine bound to the current test's event loop."""
    async_url, connect_args = _normalize_asyncpg_url(settings.DATABASE_URL)
    test_engine = create_async_engine(async_url, poolclass=NullPool, connect_args=connect_args)
    factory = async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )
    try:
        yield factory
    finally:
        await test_engine.dispose()


@pytest_asyncio.fixture
async def client(db_session_factory):
    """HTTPX AsyncClient wired to a fresh FastAPI app using the test DB session factory."""
    app = create_app()

    async def _override_get_db():
        async with db_session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


@pytest_asyncio.fixture
async def seeded_users(db_session_factory):
    """Temporary admin, recruiter, viewer and inactive users; removed after the test."""
    tag = uuid.uuid4().hex[:8]
    created_ids = []
    users_info = {}

    async with db_session_factory() as db:
        specs = [
            ("admin", f"admin-{tag}@example.com", "AdminPass123!", UserRole.admin, True),
            ("recruiter", f"recruiter-{tag}@example.com", "RecruiterPass123!", UserRole.recruiter, True),
            ("viewer", f"viewer-{tag}@example.com", "ViewerPass123!", UserRole.viewer, True),
            ("inactive", f"inactive-{tag}@example.com", "InactivePass123!", UserRole.recruiter, False),
        ]
        for key, email, password, role, active in specs:
            u = await create_user(
                db,
                email=email,
                password=password,
                full_name=f"Test {key.title()}",
                role=role,
                is_active=active,
            )
            created_ids.append(u.id)
            users_info[key] = {"id": u.id, "email": email, "password": password, "role": role.value}

    try:
        yield users_info
    finally:
        async with db_session_factory() as db:
            await db.execute(delete(User).where(User.id.in_(created_ids)))
            await db.commit()


@pytest_asyncio.fixture
async def cleanup_records(db_session_factory):
    """Track IDs created during a test and purge them afterwards."""
    tracker: dict[str, list] = {
        "candidates": [],
        "resume_files": [],
        "users": [],
        "jobs": [],
        "skill_normalizations": [],
    }
    try:
        yield tracker
    finally:
        async with db_session_factory() as db:
            entity_ids = [
                str(eid)
                for key in ("candidates", "resume_files", "jobs")
                for eid in tracker[key]
            ]
            if entity_ids:
                await db.execute(delete(AuditLog).where(AuditLog.entity_id.in_(entity_ids)))
            if tracker["jobs"]:
                await db.execute(delete(Job).where(Job.id.in_(tracker["jobs"])))
            if tracker["candidates"]:
                await db.execute(delete(Candidate).where(Candidate.id.in_(tracker["candidates"])))
            if tracker["resume_files"]:
                await db.execute(delete(ResumeFile).where(ResumeFile.id.in_(tracker["resume_files"])))
            if tracker["skill_normalizations"]:
                await db.execute(
                    delete(SkillNormalization).where(
                        SkillNormalization.id.in_(tracker["skill_normalizations"])
                    )
                )
            if tracker["users"]:
                await db.execute(delete(User).where(User.id.in_(tracker["users"])))
            await db.commit()
