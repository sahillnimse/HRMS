"""Tests for High-ROI Backlog Features:
1. Natural-Language Search (deterministic parser + POST /api/v1/candidates/nl-search + blind mode)
2. Interview Question Generator (deterministic + blind masking + POST /api/v1/candidates/{id}/interview-questions)
3. Talent Pools & Tags CRUD + cascade delete + Silver-Medalist Resurfacing (GET /api/v1/jobs/{id}/resurface)
4. Email-to-Inbox CV Ingestion (POST /api/v1/resumes/inbound-email + idempotency + domain-only logs)
5. India DPDP Act Erasure & Consent Requests (POST /erasure-requests + admin-only /execute)
"""

import base64
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import delete, select

from app.core.config import settings
from app.models.backlog import ErasureRequest, InboundEmailLog, TalentPool, TalentPoolMember
from app.models.candidate import Candidate, ParseJob, ResumeFile
from app.models.pipeline import ApplicationStage, AuditLog
from app.services.interview_questions import generate_interview_questions
from app.services.nl_search import parse_nl_query_deterministic
from app.services.file_storage import storage


async def _login(client, email: str, password: str) -> dict:
    resp = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


# ---------------------------------------------------------------------------
# 1. Pure Unit Tests (zero DB / zero network)
# ---------------------------------------------------------------------------


def test_parse_nl_query_deterministic_extracts_structured_filters():
    alias_map = {"ml": "Machine Learning", "postgres": "PostgreSQL", "k8s": "Kubernetes"}

    parsed = parse_nl_query_deterministic(
        "Python, ML, 3+ yrs, Pune, notice < 30 days", alias_map=alias_map
    )
    assert "Python" in parsed.skills
    assert "Machine Learning" in parsed.skills
    assert parsed.min_years == 3.0
    assert parsed.max_years is None
    assert parsed.city == "Pune"
    assert parsed.max_notice_days == 30

    parsed_range = parse_nl_query_deterministic(
        "React 2-5 years Bengaluru immediate joiner frontend", alias_map=alias_map
    )
    assert "React" in parsed_range.skills
    assert parsed_range.min_years == 2.0
    assert parsed_range.max_years == 5.0
    assert parsed_range.city == "Bangalore"
    assert parsed_range.max_notice_days == 15
    assert parsed_range.primary_domain == "Software Engineering"


@pytest.mark.asyncio
async def test_interview_questions_deterministic_and_blind_masking(monkeypatch):
    monkeypatch.setattr(settings, "ENABLE_INTERVIEW_QUESTIONS", False)

    cand = SimpleNamespace(
        id=uuid.uuid4(),
        full_name="Aarav Deshmukh",
        email="aarav@example.com",
        phone="+91-9876543210",
        primary_domain="Software Engineering",
        years_experience=3.5,
        profile_summary="Backend engineer building FastAPI services and PostgreSQL pipelines.",
        technical_skills=["Python", "FastAPI", "PostgreSQL", "Docker", "Kubernetes", "GraphQL", "Kafka"],
        tools=["Git", "Docker"],
        soft_skills=["Communication"],
        certifications=[],
        education=[
            {
                "degree": "B.E. Computer Engineering",
                "institution": "Pune Institute of Computer Technology",
                "graduation_year": "2022",
                "start_year": 2018,
                "end_year": 2022,
            }
        ],
        work_experience=[
            {
                "job_title": "Backend Engineer",
                "company": "Acme Payments",
                "start_date": "2022-07",
                "end_date": "Present",
                "employment_type": "full_time",
                "description": "Built Python and FastAPI microservices on PostgreSQL for Aarav Deshmukh.",
            }
        ],
        projects=[
            {
                "name": "Realtime Fraud Engine",
                "description": "Streaming anomaly detector using Python and Redis.",
                "technologies": ["Python", "Redis"],
            }
        ],
        raw_parsed_data={},
    )
    job = SimpleNamespace(
        id=uuid.uuid4(),
        title="Senior Platform Engineer",
        required_skills=["Python", "FastAPI", "Go", "PostgreSQL"],
        nice_to_have_skills=["Redis"],
        min_years=3.0,
        max_years=6.0,
        description="Build reliable distributed backend services in Python and Go.",
        embedding=None,
    )

    resp = await generate_interview_questions(cand, job=job, count=6, blind=True, alias_map={})
    assert resp.model == "deterministic"
    assert len(resp.questions) >= 4
    categories = {q.category for q in resp.questions}
    assert "skill_gap" in categories
    assert "project_deep_dive" in categories

    joined = " ".join(f"{q.target_topic} {q.question} {q.what_to_look_for}" for q in resp.questions)
    assert "Aarav Deshmukh" not in joined
    assert "Pune Institute of Computer Technology" not in joined
    assert "Realtime Fraud Engine" in joined
    assert "Go" in joined


# ---------------------------------------------------------------------------
# 2. Natural-Language Search + Interview Questions API Integration Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_nl_search_and_interview_questions_endpoints(
    client, seeded_users, cleanup_records, monkeypatch
):
    monkeypatch.setattr(settings, "ENABLE_NL_SEARCH", False)
    monkeypatch.setattr(settings, "ENABLE_INTERVIEW_QUESTIONS", False)

    rec_headers = await _login(client, seeded_users["recruiter"]["email"], seeded_users["recruiter"]["password"])
    viewer_headers = await _login(client, seeded_users["viewer"]["email"], seeded_users["viewer"]["password"])

    tag = uuid.uuid4().hex[:6]
    c1_resp = await client.post(
        "/api/v1/candidates/",
        headers=rec_headers,
        json={
            "full_name": f"Neha Kulkarni {tag}",
            "email": f"neha-{tag}@example.com",
            "primary_domain": "Software Engineering",
            "profile_summary": "Senior Python backend engineer specializing in FastAPI and PostgreSQL.",
            "years_experience": 4.0,
            "city": "Pune",
            "notice_period_days": 20,
            "technical_skills": ["Python", "FastAPI", "PostgreSQL"],
            "work_experience": [
                {
                    "job_title": "Senior Python Engineer",
                    "company": "FinTech Labs",
                    "start_date": "2022-01",
                    "end_date": "Present",
                    "employment_type": "full_time",
                    "description": "Designed FastAPI APIs and PostgreSQL schemas.",
                }
            ],
            "projects": [
                {
                    "name": "Ledger Reconciler",
                    "description": "Automated billing reconciliation engine.",
                    "technologies": ["Python", "PostgreSQL"],
                }
            ],
            "allow_duplicate": True,
        },
    )
    assert c1_resp.status_code == 201, c1_resp.text
    c1_id = c1_resp.json()["id"]
    cleanup_records["candidates"].append(uuid.UUID(c1_id))

    # Candidate 2: different city & long notice -> should be filtered out by NL search
    c2_resp = await client.post(
        "/api/v1/candidates/",
        headers=rec_headers,
        json={
            "full_name": f"Rohan Verma {tag}",
            "email": f"rohan-{tag}@example.com",
            "primary_domain": "Software Engineering",
            "profile_summary": "Backend engineer experienced with Python and FastAPI.",
            "years_experience": 4.0,
            "city": "Chennai",
            "notice_period_days": 90,
            "technical_skills": ["Python", "FastAPI"],
            "allow_duplicate": True,
        },
    )
    assert c2_resp.status_code == 201, c2_resp.text
    c2_id = c2_resp.json()["id"]
    cleanup_records["candidates"].append(uuid.UUID(c2_id))

    # NL search: Pune + Python + 3+ yrs + notice < 30 days
    nl_resp = await client.post(
        "/api/v1/candidates/nl-search",
        headers=viewer_headers,
        json={
            "query": "Python, 3+ yrs, Pune, notice < 30 days",
            "page": 1,
            "page_size": 20,
            "blind": True,
        },
    )
    assert nl_resp.status_code == 200, nl_resp.text
    nl_data = nl_resp.json()
    assert nl_data["parser_mode"] == "deterministic"
    assert nl_data["parsed_filters"]["city"] == "Pune"
    assert nl_data["parsed_filters"]["max_notice_days"] == 30
    assert nl_data["parsed_filters"]["min_years"] == 3.0

    returned_ids = {item["id"] for item in nl_data["items"]}
    assert c1_id in returned_ids
    assert c2_id not in returned_ids

    # Verify blind mode masked PII
    matched_c1 = next(item for item in nl_data["items"] if item["id"] == c1_id)
    assert matched_c1["full_name"].startswith("Candidate #")
    assert matched_c1["email"] is None

    # Interview Questions endpoint (viewer allowed, blind=true)
    q_resp = await client.post(
        f"/api/v1/candidates/{c1_id}/interview-questions",
        headers=viewer_headers,
        json={"count": 5, "blind": True},
    )
    assert q_resp.status_code == 200, q_resp.text
    q_data = q_resp.json()
    assert q_data["model"] == "deterministic"
    assert len(q_data["questions"]) >= 3
    all_q_text = " ".join(q["question"] for q in q_data["questions"])
    assert f"Neha Kulkarni {tag}" not in all_q_text


# ---------------------------------------------------------------------------
# 3. Talent Pools & Silver-Medalist Resurfacing Integration Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_talent_pools_and_silver_medalist_resurfacing(
    client, db_session_factory, seeded_users, cleanup_records
):
    rec_headers = await _login(client, seeded_users["recruiter"]["email"], seeded_users["recruiter"]["password"])
    viewer_headers = await _login(client, seeded_users["viewer"]["email"], seeded_users["viewer"]["password"])

    tag = uuid.uuid4().hex[:6]
    pool_id = None
    try:
        # Create candidate
        c_resp = await client.post(
            "/api/v1/candidates/",
            headers=rec_headers,
            json={
                "full_name": f"Meera Nair {tag}",
                "email": f"meera-{tag}@example.com",
                "primary_domain": "Software Engineering",
                "profile_summary": "Full-stack backend engineer with strong Python, FastAPI, and PostgreSQL experience.",
                "years_experience": 5.0,
                "technical_skills": ["Python", "FastAPI", "PostgreSQL", "Docker"],
                "allow_duplicate": True,
            },
        )
        assert c_resp.status_code == 201, c_resp.text
        cand_id = c_resp.json()["id"]
        cleanup_records["candidates"].append(uuid.UUID(cand_id))

        # Create Talent Pool
        p_resp = await client.post(
            "/api/v1/talent-pools/",
            headers=rec_headers,
            json={"name": f"Silver Backend {tag}", "description": "Top Python engineers", "color": "brand"},
        )
        assert p_resp.status_code == 201, p_resp.text
        pool_id = p_resp.json()["id"]

        # Add candidate to pool
        add_m = await client.post(
            f"/api/v1/talent-pools/{pool_id}/members",
            headers=rec_headers,
            json={"candidate_id": cand_id, "notes": "Great system design"},
        )
        assert add_m.status_code == 201, add_m.text

        # Candidate's pools endpoint returns it
        cp_resp = await client.get(f"/api/v1/candidates/{cand_id}/talent-pools", headers=viewer_headers)
        assert cp_resp.status_code == 200
        assert any(p["id"] == pool_id for p in cp_resp.json())

        # Create Job A (past job where candidate reached 'interview') and Job B (new open job)
        job_a = await client.post(
            "/api/v1/jobs/",
            headers=rec_headers,
            json={
                "title": f"Backend Engineer A {tag}",
                "required_skills": ["Python", "FastAPI"],
                "min_years": 3.0,
                "max_years": 7.0,
            },
        )
        assert job_a.status_code == 201, job_a.text
        job_a_id = job_a.json()["id"]
        cleanup_records["jobs"].append(uuid.UUID(job_a_id))

        job_b = await client.post(
            "/api/v1/jobs/",
            headers=rec_headers,
            json={
                "title": f"Senior API Engineer B {tag}",
                "required_skills": ["Python", "FastAPI", "PostgreSQL"],
                "nice_to_have_skills": ["Docker"],
                "min_years": 3.0,
                "max_years": 7.0,
            },
        )
        assert job_b.status_code == 201, job_b.text
        job_b_id = job_b.json()["id"]
        cleanup_records["jobs"].append(uuid.UUID(job_b_id))

        # Apply to Job A and advance to 'interview' (making Meera a silver medalist)
        app_resp = await client.post(
            "/api/v1/applications/",
            headers=rec_headers,
            json={"candidate_id": cand_id, "job_id": job_a_id, "stage": "interview"},
        )
        assert app_resp.status_code == 201, app_resp.text

        # Resurface for Job B (blind=true) -> Meera should appear with talent pool badge and high score
        res_resp = await client.get(
            f"/api/v1/jobs/{job_b_id}/resurface",
            params={"blind": True, "min_score": 30},
            headers=viewer_headers,
        )
        assert res_resp.status_code == 200, res_resp.text
        res_data = res_resp.json()
        meera_items = [c for c in res_data["candidates"] if c["candidate_id"] == cand_id]
        assert len(meera_items) == 1
        item = meera_items[0]
        assert item["full_name"].startswith("Candidate #")
        assert item["past_highest_stage"] == ApplicationStage.interview.value
        assert item["match_score"] >= 70
        assert f"Silver Backend {tag}" in item["talent_pools"]

        # Once added to Job B, candidate should no longer be resurfaced for Job B
        add_b = await client.post(
            "/api/v1/applications/",
            headers=rec_headers,
            json={"candidate_id": cand_id, "job_id": job_b_id, "stage": "applied"},
        )
        assert add_b.status_code == 201
        res_after = await client.get(
            f"/api/v1/jobs/{job_b_id}/resurface",
            params={"min_score": 0},
            headers=viewer_headers,
        )
        assert not any(c["candidate_id"] == cand_id for c in res_after.json()["candidates"])

        # Remove from pool and delete pool
        rem = await client.delete(f"/api/v1/talent-pools/{pool_id}/members/{cand_id}", headers=rec_headers)
        assert rem.status_code == 204
    finally:
        if pool_id:
            async with db_session_factory() as db:
                await db.execute(delete(TalentPoolMember).where(TalentPoolMember.pool_id == uuid.UUID(pool_id)))
                await db.execute(delete(TalentPool).where(TalentPool.id == uuid.UUID(pool_id)))
                await db.commit()


# ---------------------------------------------------------------------------
# 4. Email-to-Inbox CV Ingestion Webhook Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_inbound_email_webhook_auth_idempotency_and_privacy(
    client, db_session_factory, seeded_users, cleanup_records, monkeypatch
):
    secret = f"inbound-secret-{uuid.uuid4().hex[:10]}"
    monkeypatch.setattr(settings, "INBOUND_EMAIL_WEBHOOK_SECRET", secret)
    rec_headers = await _login(client, seeded_users["recruiter"]["email"], seeded_users["recruiter"]["password"])

    msg_id = f"<cv-{uuid.uuid4().hex}@mail.example.com>"
    fake_pdf = b"%PDF-1.4\n1 0 obj <<>> endobj\ntrailer <<>>\n%%EOF\n"
    payload = {
        "message_id": msg_id,
        "from_email": "alice.private@applicant-domain.example.com",
        "subject": "Application for Backend Engineer",
        "attachments": [
            {
                "filename": "alice_resume.pdf",
                "content_type": "application/pdf",
                "content_base64": base64.b64encode(fake_pdf).decode("ascii"),
            },
            {
                "filename": "malware.exe",
                "content_type": "application/octet-stream",
                "content_base64": base64.b64encode(b"MZ...").decode("ascii"),
            },
        ],
    }

    stored_filenames = []
    try:
        # Missing auth -> 401
        r_unauth = await client.post("/api/v1/resumes/inbound-email", json=payload)
        assert r_unauth.status_code == 401

        # Valid webhook secret -> 202 and queues only the valid PDF (mock enqueue so no Gemini call)
        with patch(
            "app.api.v1.endpoints.resumes.enqueue_parse_jobs", new_callable=AsyncMock
        ) as mock_enq:
            r_ok = await client.post(
                "/api/v1/resumes/inbound-email",
                headers={"X-Inbound-Webhook-Secret": secret},
                json=payload,
            )
            assert r_ok.status_code == 202, r_ok.text
            data = r_ok.json()
            assert data["message_id"] == msg_id
            assert data["from_domain"] == "applicant-domain.example.com"
            assert "alice.private" not in data["from_domain"]
            assert data["attachment_count"] == 1
            assert data["status"] == "processed"
            assert data["parse_batch_id"] is not None
            mock_enq.assert_awaited_once()

            # Duplicate message_id -> idempotent return, does NOT re-enqueue
            r_dup = await client.post(
                "/api/v1/resumes/inbound-email",
                headers={"X-Inbound-Webhook-Secret": secret},
                json=payload,
            )
            assert r_dup.status_code == 202
            assert r_dup.json()["id"] == data["id"]
            assert mock_enq.await_count == 1

        # Inbound logs endpoint lists the event
        logs_resp = await client.get("/api/v1/resumes/inbound-logs", headers=rec_headers)
        assert logs_resp.status_code == 200
        assert any(row["message_id"] == msg_id for row in logs_resp.json())

        # Collect created ParseJob & ResumeFile for cleanup
        async with db_session_factory() as db:
            batch_uuid = uuid.UUID(data["parse_batch_id"])
            jobs = (await db.execute(select(ParseJob).where(ParseJob.batch_id == batch_uuid))).scalars().all()
            for j in jobs:
                cleanup_records["parse_jobs"].append(j.id)
                if j.resume_file_id:
                    rf = (await db.execute(select(ResumeFile).where(ResumeFile.id == j.resume_file_id))).scalar_one_or_none()
                    if rf:
                        stored_filenames.append(rf.stored_filename)
                        cleanup_records["resume_files"].append(rf.id)
    finally:
        for fname in stored_filenames:
            await storage.delete_file(fname)
        async with db_session_factory() as db:
            await db.execute(delete(InboundEmailLog).where(InboundEmailLog.message_id == msg_id))
            await db.commit()


# ---------------------------------------------------------------------------
# 5. India DPDP Act Erasure & Consent Requests Integration Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dpdp_erasure_request_lifecycle_and_rbac(
    client, db_session_factory, seeded_users, cleanup_records
):
    admin_headers = await _login(client, seeded_users["admin"]["email"], seeded_users["admin"]["password"])
    rec_headers = await _login(client, seeded_users["recruiter"]["email"], seeded_users["recruiter"]["password"])

    tag = uuid.uuid4().hex[:6]
    erasure_id = None
    try:
        # Create candidate to erase
        c_resp = await client.post(
            "/api/v1/candidates/",
            headers=rec_headers,
            json={
                "full_name": f"Erasure Subject {tag}",
                "email": f"erase-{tag}@example.com",
                "primary_domain": "Operations",
                "profile_summary": "Operations coordinator skilled in reporting and Excel workflows.",
                "years_experience": 2.0,
                "technical_skills": ["Excel"],
                "allow_duplicate": True,
            },
        )
        assert c_resp.status_code == 201, c_resp.text
        cand_id = c_resp.json()["id"]
        cleanup_records["candidates"].append(uuid.UUID(cand_id))

        # Recruiter can log DPDP erasure request
        req_resp = await client.post(
            "/api/v1/privacy/erasure-requests",
            headers=rec_headers,
            json={
                "candidate_id": cand_id,
                "request_type": "erasure",
                "reason": "Candidate withdrew consent via email",
            },
        )
        assert req_resp.status_code == 201, req_resp.text
        erasure_data = req_resp.json()
        erasure_id = erasure_data["id"]
        assert erasure_data["status"] == "pending"
        assert len(erasure_data["candidate_ref_hash"]) == 64

        # Recruiter cannot execute erasure -> 403
        r_forbid = await client.post(
            f"/api/v1/privacy/erasure-requests/{erasure_id}/execute",
            headers=rec_headers,
        )
        assert r_forbid.status_code == 403

        # Admin executes erasure -> candidate deleted, compliance proof retained with candidate_id=None
        r_exec = await client.post(
            f"/api/v1/privacy/erasure-requests/{erasure_id}/execute",
            headers=admin_headers,
        )
        assert r_exec.status_code == 200, r_exec.text
        done = r_exec.json()
        assert done["status"] == "completed"
        assert done["candidate_id"] is None
        assert done["candidate_ref_hash"] == erasure_data["candidate_ref_hash"]
        assert done["processed_at"] is not None

        # Candidate record is actually gone
        c_get = await client.get(f"/api/v1/candidates/{cand_id}", headers=admin_headers)
        assert c_get.status_code == 404

        # Listing erasure requests still shows completed compliance record
        list_resp = await client.get("/api/v1/privacy/erasure-requests", headers=admin_headers)
        assert list_resp.status_code == 200
        assert any(r["id"] == erasure_id and r["status"] == "completed" for r in list_resp.json())
    finally:
        if erasure_id:
            async with db_session_factory() as db:
                await db.execute(delete(AuditLog).where(AuditLog.entity_id == erasure_id))
                await db.execute(delete(ErasureRequest).where(ErasureRequest.id == uuid.UUID(erasure_id)))
                await db.commit()
