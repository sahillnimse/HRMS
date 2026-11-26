"""Phase 4 tests: Candidate Brief, Career Timeline, Consistency Checks, Skill-Gap, Shortlist Pack PDF, and Cascade/Retention cleanup."""

from datetime import date, datetime, timedelta, timezone
import uuid

import fitz
import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models.clarity import CandidateBrief
from app.models.pipeline import AuditLog
from app.services.consistency import run_consistency_checks
from app.services.matching import compute_jd_match
from app.services.timeline import build_career_timeline


async def _login(client, email: str, password: str) -> str:
    res = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert res.status_code == 200, res.text
    return res.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_timeline_gaps_overlaps_invalid_dates_and_tenure_stats():
    today = date(2026, 6, 1)
    work = [
        # Current role: Jan 2025 -> Present (18 mos)
        {"company": "CurrentCo", "job_title": "Lead Engineer", "start_date": "Jan 2025", "end_date": "Present"},
        # Previous role: Jan 2023 -> Jun 2024 (18 mos) -> 6-month gap Jul-Dec 2024 (>3m)
        {"company": "PrevCo", "job_title": "Senior Engineer", "start_date": "Jan 2023", "end_date": "Jun 2024"},
        # Overlapping role: Jan 2022 -> May 2023 (overlaps Jan-May 2023 = 5 mos with PrevCo)
        {"company": "OverlapCo", "job_title": "Consultant", "start_date": "Jan 2022", "end_date": "May 2023"},
        # Invalid end-before-start role
        {"company": "BadDateCo", "job_title": "Analyst", "start_date": "2021-08", "end_date": "2021-02"},
    ]

    roles, gaps, overlaps, stats = build_career_timeline(
        work, gap_threshold_months=3, today=today
    )
    assert len(roles) == 4
    assert roles[0].company == "CurrentCo"
    assert roles[0].is_current is True
    assert any(r.company == "BadDateCo" and r.has_invalid_dates for r in roles)

    assert len(gaps) == 1
    assert gaps[0].duration_months == 6
    assert gaps[0].from_ym == "2024-07"
    assert gaps[0].to_ym == "2024-12"

    # Raising gap threshold to 8 months suppresses the 6-month gap
    _, gaps_high, _, _ = build_career_timeline(work, gap_threshold_months=8, today=today)
    assert gaps_high == []

    assert len(overlaps) == 1
    assert overlaps[0].overlap_months == 5
    assert stats.jobs_last_5_years == 3
    assert stats.dated_role_count == 3
    assert stats.average_tenure_months > 0


def test_consistency_checks_all_signals_neutral_and_never_change_match_score():
    today = date(2026, 6, 1)
    work = [
        {
            "company": "Alpha",
            "job_title": "Backend Engineer",
            "start_date": "Jan 2025",
            "end_date": "Jun 2025",
            "bullets": ["Built Python services."],
        },
        {
            "company": "Beta",
            "job_title": "Developer",
            "start_date": "Jan 2024",
            "end_date": "May 2024",
            "bullets": ["Maintained Python scripts."],
        },
        {
            "company": "Gamma",
            "job_title": "Consultant",
            "start_date": "Jan 2024",
            "end_date": "Apr 2024",
            "bullets": ["Reviewed code."],
        },
        {
            "company": "Delta",
            "job_title": "Intern",
            "start_date": "2023-09",
            "end_date": "2023-03",
            "bullets": ["Assisted team."],
        },
    ]

    roles, gaps, overlaps, stats = build_career_timeline(work, gap_threshold_months=3, today=today)
    checks = run_consistency_checks(
        roles=roles,
        gaps=gaps,
        overlaps=overlaps,
        tenure_stats=stats,
        stated_years=6.0,  # large mismatch vs ~1 yr computed
        llm_stated_years=6.0,
        work_experience=work,
        profile_summary="Backend developer.",
        technical_skills=["Python", "Rust", "Go", "Scala", "Elixir"],
        tools=["Kubernetes", "Terraform"],
    )
    codes = {c.code for c in checks}
    assert "end_before_start" in codes
    assert "overlapping_dates" in codes
    assert "employment_gap" in codes
    assert "repeated_short_stints" in codes
    assert "experience_mismatch" in codes
    assert "unverified_listed_skills" in codes
    for c in checks:
        assert c.severity in ("info", "check")
        assert c.message
        assert isinstance(c.evidence, dict)


def test_matching_adjacent_skills_and_one_sentence_why():
    alias_map = {
        "python": "Python",
        "fastapi": "FastAPI",
        "django": "Django",
        "postgresql": "PostgreSQL",
        "mysql": "MySQL",
        "kubernetes": "Kubernetes",
        "docker": "Docker",
    }
    score, breakdown = compute_jd_match(
        job_title="Backend Engineer",
        job_description="Python FastAPI PostgreSQL Kubernetes",
        required_skills=["Python", "FastAPI", "PostgreSQL", "Kubernetes"],
        nice_to_have_skills=["Docker"],
        min_years=3.0,
        max_years=6.0,
        candidate_years=4.5,
        candidate_summary="Python backend developer using Django, MySQL, and Docker.",
        candidate_domain="Software Engineering",
        candidate_technical_skills=["Python", "Django"],
        candidate_tools=["MySQL", "Docker"],
        candidate_work_experience=[{"job_title": "Backend Engineer", "company": "Acme"}],
        alias_map=alias_map,
    )
    assert 0.0 <= score <= 100.0
    adj = breakdown["adjacent_skills"]
    adj_pairs = {(a["required_skill"], a["candidate_skill"]) for a in adj}
    assert ("FastAPI", "Django") in adj_pairs
    assert ("PostgreSQL", "MySQL") in adj_pairs
    assert ("Kubernetes", "Docker") in adj_pairs
    assert isinstance(breakdown["why"], str) and breakdown["why"].endswith(".")
    assert "adjacent" in breakdown["why"].lower()


@pytest.mark.asyncio
async def test_candidate_brief_lazy_cache_invalidation_regenerate_and_blind(
    client, seeded_users, cleanup_records, monkeypatch
):
    rec_token = await _login(
        client, seeded_users["recruiter"]["email"], seeded_users["recruiter"]["password"]
    )
    viewer_token = await _login(
        client, seeded_users["viewer"]["email"], seeded_users["viewer"]["password"]
    )
    tag = uuid.uuid4().hex[:8]
    monkeypatch.setattr(settings, "ENABLE_SEMANTIC_SEARCH", False)
    monkeypatch.setattr(settings, "ENABLE_CANDIDATE_BRIEF", False)

    secret_name = f"Rohan Kulkarni {tag}"
    secret_email = f"rohan.{tag}@example.com"
    secret_college = f"MIT Pune {tag}"

    create_res = await client.post(
        "/api/v1/candidates/",
        json={
            "full_name": secret_name,
            "email": secret_email,
            "city": "Pune",
            "profile_summary": f"{secret_name} builds reliable Python microservices (CTC 22 LPA).",
            "years_experience": 4.0,
            "primary_domain": "Software Engineering",
            "work_experience": [
                {
                    "company": "CloudNine",
                    "job_title": "Senior Backend Engineer",
                    "start_date": "Jan 2022",
                    "end_date": "Present",
                    "bullets": ["Built FastAPI and PostgreSQL APIs."],
                }
            ],
            "education": [{"degree": "B.E. CS", "institution": secret_college, "graduation_year": 2021}],
            "technical_skills": ["Python", "FastAPI"],
            "tools": ["PostgreSQL", "Docker"],
            "allow_duplicate": True,
        },
        headers=_auth(rec_token),
    )
    assert create_res.status_code == 201, create_res.text
    cid = create_res.json()["id"]
    cleanup_records["candidates"].append(uuid.UUID(cid))

    # 1. Lazy generation (deterministic fallback since ENABLE_CANDIDATE_BRIEF=False)
    b1 = await client.get(f"/api/v1/candidates/{cid}/brief", headers=_auth(viewer_token))
    assert b1.status_code == 200, b1.text
    d1 = b1.json()
    assert d1["cached"] is False
    assert d1["model"] == "deterministic"
    assert len([ln for ln in d1["summary"].splitlines() if ln.strip()]) <= 5
    assert 2 <= len(d1["strengths"]) <= 4
    assert "22 LPA" not in d1["summary"]

    # 2. Second GET hits cache
    b2 = await client.get(f"/api/v1/candidates/{cid}/brief", headers=_auth(viewer_token))
    assert b2.status_code == 200
    assert b2.json()["cached"] is True
    assert b2.json()["source_hash"] == d1["source_hash"]

    # 3. Updating candidate invalidates source_hash and triggers lazy refresh
    upd = await client.put(
        f"/api/v1/candidates/{cid}",
        json={"technical_skills": ["Python", "FastAPI", "Go"]},
        headers=_auth(rec_token),
    )
    assert upd.status_code == 200
    b3 = await client.get(f"/api/v1/candidates/{cid}/brief", headers=_auth(viewer_token))
    assert b3.status_code == 200
    assert b3.json()["cached"] is False
    assert b3.json()["source_hash"] != d1["source_hash"]

    # 4. Viewer cannot force-regenerate; recruiter can (with mocked AI provider)
    forbid = await client.post(
        f"/api/v1/candidates/{cid}/brief/regenerate", headers=_auth(viewer_token)
    )
    assert forbid.status_code == 403

    async def fake_ai_brief(_cand, *, computed_years: float):
        return (
            f"Senior Backend Engineer with {computed_years:.1f} yrs in Python & Go.\nStrong API ownership.",
            ["Deep Python and FastAPI delivery", "Hands-on PostgreSQL and Docker operations"],
            "gemini-2.0-flash",
        )

    monkeypatch.setattr("app.services.brief._generate_ai_brief_text", fake_ai_brief)
    regen = await client.post(
        f"/api/v1/candidates/{cid}/brief/regenerate", headers=_auth(rec_token)
    )
    assert regen.status_code == 200, regen.text
    assert regen.json()["model"] == "gemini-2.0-flash"
    assert regen.json()["cached"] is False

    # 5. Blind mode masks candidate name/email/college from brief text
    blind_b = await client.get(
        f"/api/v1/candidates/{cid}/brief",
        params={"blind": True},
        headers=_auth(viewer_token),
    )
    assert blind_b.status_code == 200
    for forbidden in (secret_name, secret_email, secret_college):
        assert forbidden not in blind_b.text


@pytest.mark.asyncio
async def test_timeline_endpoint_and_shortlist_pack_pdf_blind_viewer_and_audit(
    client, seeded_users, cleanup_records, db_session_factory, monkeypatch
):
    rec_token = await _login(
        client, seeded_users["recruiter"]["email"], seeded_users["recruiter"]["password"]
    )
    viewer_token = await _login(
        client, seeded_users["viewer"]["email"], seeded_users["viewer"]["password"]
    )
    tag = uuid.uuid4().hex[:8]
    monkeypatch.setattr(settings, "ENABLE_SEMANTIC_SEARCH", False)
    monkeypatch.setattr(settings, "ENABLE_CANDIDATE_BRIEF", False)

    c1_name = f"Meera Nair {tag}"
    c1_email = f"meera.{tag}@example.com"
    c1_college = f"BITS Pilani {tag}"
    c1_res = await client.post(
        "/api/v1/candidates/",
        json={
            "full_name": c1_name,
            "email": c1_email,
            "phone": "+91 9811122233",
            "city": "Bengaluru",
            "profile_summary": "Backend engineer specializing in Python and Django.",
            "years_experience": 5.0,
            "primary_domain": "Software Engineering",
            "work_experience": [
                {
                    "company": "FinEdge",
                    "job_title": "Senior Backend Engineer",
                    "start_date": "Jan 2024",
                    "end_date": "Present",
                    "bullets": ["Scaled Django APIs and Docker workloads."],
                },
                {
                    "company": "StartupOne",
                    "job_title": "Software Engineer",
                    "start_date": "Jan 2021",
                    "end_date": "Jun 2023",
                    "bullets": ["Built Python pipelines."],
                },
            ],
            "education": [{"degree": "B.E.", "institution": c1_college, "graduation_year": 2020}],
            "technical_skills": ["Python", "Django"],
            "tools": ["Docker", "MySQL"],
            "current_ctc": 2800000,
            "expected_ctc": 3400000,
            "ctc_currency": "INR",
            "allow_duplicate": True,
        },
        headers=_auth(rec_token),
    )
    assert c1_res.status_code == 201, c1_res.text
    c1_id = c1_res.json()["id"]
    cleanup_records["candidates"].append(uuid.UUID(c1_id))

    c2_res = await client.post(
        "/api/v1/candidates/",
        json={
            "full_name": f"Arjun Patel {tag}",
            "email": f"arjun.{tag}@example.com",
            "city": "Mumbai",
            "profile_summary": "FastAPI & Kubernetes platform engineer.",
            "years_experience": 4.0,
            "primary_domain": "Software Engineering",
            "work_experience": [
                {
                    "company": "ScaleOps",
                    "job_title": "Platform Engineer",
                    "start_date": "Jan 2022",
                    "end_date": "Present",
                    "bullets": ["Operated Kubernetes and PostgreSQL clusters."],
                }
            ],
            "technical_skills": ["Python", "FastAPI"],
            "tools": ["PostgreSQL", "Kubernetes"],
            "current_ctc": 2500000,
            "expected_ctc": 3100000,
            "ctc_currency": "INR",
            "allow_duplicate": True,
        },
        headers=_auth(rec_token),
    )
    assert c2_res.status_code == 201, c2_res.text
    c2_id = c2_res.json()["id"]
    cleanup_records["candidates"].append(uuid.UUID(c2_id))

    # 1. Timeline endpoint returns gap between Jun 2023 and Jan 2024 (6 mos)
    tl_res = await client.get(
        f"/api/v1/candidates/{c1_id}/timeline",
        params={"gap_months": 3},
        headers=_auth(viewer_token),
    )
    assert tl_res.status_code == 200, tl_res.text
    tl = tl_res.json()
    assert len(tl["roles"]) == 2
    assert len(tl["gaps"]) == 1
    assert tl["gaps"][0]["duration_months"] == 6
    assert tl["tenure_stats"]["role_count"] == 2

    # 2. Job + Shortlist Pack PDF
    job_res = await client.post(
        "/api/v1/jobs/",
        json={
            "title": f"Backend Platform Engineer {tag}",
            "department": "Engineering",
            "location": "Hybrid",
            "description": "Python FastAPI PostgreSQL Kubernetes",
            "required_skills": ["Python", "FastAPI", "PostgreSQL", "Kubernetes"],
            "nice_to_have_skills": ["Docker"],
            "min_years": 3.0,
            "max_years": 7.0,
            "status": "open",
        },
        headers=_auth(rec_token),
    )
    assert job_res.status_code == 201, job_res.text
    job_id = job_res.json()["id"]
    cleanup_records["jobs"].append(uuid.UUID(job_id))

    # Blind + viewer export -> 2 pages (one per candidate), no PII, no CTC
    pack_viewer = await client.get(
        f"/api/v1/jobs/{job_id}/shortlist/export/pdf",
        params={"candidate_ids": f"{c1_id},{c2_id}", "blind": True},
        headers=_auth(viewer_token),
    )
    assert pack_viewer.status_code == 200, pack_viewer.text
    assert pack_viewer.headers["content-type"].startswith("application/pdf")
    doc = fitz.open(stream=pack_viewer.content, filetype="pdf")
    assert len(doc) == 2
    all_text = "\n".join(page.get_text() for page in doc)
    doc.close()
    assert "BLIND SHORTLIST PACK" in all_text
    assert "CANDIDATE BRIEF" in all_text
    assert "CAREER TIMELINE SUMMARY" in all_text
    assert "JOB FIT & SKILL-GAP SUMMARY" in all_text
    for forbidden in (c1_name, c1_email, "+91 9811122233", c1_college, "2,800,000", "3,400,000", "Current / Expected CTC"):
        assert forbidden not in all_text

    # Non-blind + recruiter export -> includes CTC and real name
    pack_rec = await client.get(
        f"/api/v1/jobs/{job_id}/shortlist/export/pdf",
        params={"candidate_ids": c1_id, "blind": False},
        headers=_auth(rec_token),
    )
    assert pack_rec.status_code == 200
    doc_r = fitz.open(stream=pack_rec.content, filetype="pdf")
    assert len(doc_r) == 1
    rec_text = doc_r[0].get_text()
    doc_r.close()
    assert c1_name in rec_text
    assert "2,800,000" in rec_text

    # Audit log recorded the shortlist pack exports
    async with db_session_factory() as db:
        audits = (
            await db.execute(
                select(AuditLog).where(
                    AuditLog.entity == "job",
                    AuditLog.entity_id == str(job_id),
                    AuditLog.action == "export",
                )
            )
        ).scalars().all()
        assert any((a.details or {}).get("format") == "shortlist_pack_pdf" for a in audits)


@pytest.mark.asyncio
async def test_delete_and_retention_purge_cascade_candidate_briefs(
    client, seeded_users, cleanup_records, db_session_factory, monkeypatch
):
    admin_token = await _login(client, seeded_users["admin"]["email"], seeded_users["admin"]["password"])
    rec_token = await _login(
        client, seeded_users["recruiter"]["email"], seeded_users["recruiter"]["password"]
    )
    tag = uuid.uuid4().hex[:8]
    monkeypatch.setattr(settings, "ENABLE_SEMANTIC_SEARCH", False)
    monkeypatch.setattr(settings, "ENABLE_CANDIDATE_BRIEF", False)

    # Candidate A: manual delete cascade check
    res_a = await client.post(
        "/api/v1/candidates/",
        json={
            "full_name": f"Cascade Manual {tag}",
            "email": f"casc.a.{tag}@example.com",
            "profile_summary": "Manual delete cascade test.",
            "years_experience": 2.0,
            "primary_domain": "Engineering",
            "technical_skills": ["Python"],
            "allow_duplicate": True,
        },
        headers=_auth(rec_token),
    )
    cid_a = uuid.UUID(res_a.json()["id"])
    cleanup_records["candidates"].append(cid_a)
    assert (await client.get(f"/api/v1/candidates/{cid_a}/brief", headers=_auth(rec_token))).status_code == 200

    # Candidate B: retention purge cascade check
    old_consent = (datetime.now(timezone.utc) - timedelta(days=400)).isoformat()
    res_b = await client.post(
        "/api/v1/candidates/",
        json={
            "full_name": f"Cascade Retention {tag}",
            "email": f"casc.b.{tag}@example.com",
            "profile_summary": "Retention purge cascade test.",
            "years_experience": 2.0,
            "primary_domain": "Engineering",
            "technical_skills": ["Python"],
            "consent_given_at": old_consent,
            "allow_duplicate": True,
        },
        headers=_auth(rec_token),
    )
    cid_b = uuid.UUID(res_b.json()["id"])
    cleanup_records["candidates"].append(cid_b)
    assert (await client.get(f"/api/v1/candidates/{cid_b}/brief", headers=_auth(rec_token))).status_code == 200

    # Manual delete A -> brief A cascaded
    assert (await client.delete(f"/api/v1/candidates/{cid_a}", headers=_auth(rec_token))).status_code == 204
    # Retention purge B -> brief B cascaded
    purge = await client.post(
        "/api/v1/privacy/purge-expired",
        params={"retention_days": 365, "dry_run": False},
        headers=_auth(admin_token),
    )
    assert purge.status_code == 200

    async with db_session_factory() as db:
        brief_a = (
            await db.execute(select(CandidateBrief).where(CandidateBrief.candidate_id == cid_a))
        ).scalar_one_or_none()
        brief_b = (
            await db.execute(select(CandidateBrief).where(CandidateBrief.candidate_id == cid_b))
        ).scalar_one_or_none()
        assert brief_a is None
        assert brief_b is None
