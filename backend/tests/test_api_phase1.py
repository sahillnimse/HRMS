"""End-to-end async HTTP tests for Phase 1 (Hiring Pipeline, Notes, CTC RBAC, Audit Logs)."""

import json
from pathlib import Path
import uuid
from unittest.mock import AsyncMock, patch

from sqlalchemy import select

from app.models.candidate import Candidate
from app.models.pipeline import ApplicationEvent, AuditLog
from app.schemas.resume import (
    AdditionalInfo,
    ContactDetails,
    ParsedResume,
    ProfileOverview,
    Skills,
)
from app.services.file_storage import storage


async def _login(client, email: str, password: str) -> dict[str, str]:
    resp = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def test_jobs_applications_kanban_events_notes_and_audit(
    client, seeded_users, db_session_factory, cleanup_records
):
    admin_h = await _login(client, seeded_users["admin"]["email"], seeded_users["admin"]["password"])
    rec_h = await _login(client, seeded_users["recruiter"]["email"], seeded_users["recruiter"]["password"])
    viewer_h = await _login(client, seeded_users["viewer"]["email"], seeded_users["viewer"]["password"])

    tag = uuid.uuid4().hex[:6]

    # 1. Viewer cannot create a job
    forbid_job = await client.post(
        "/api/v1/jobs/",
        headers=viewer_h,
        json={"title": "Blocked Job", "status": "open"},
    )
    assert forbid_job.status_code == 403

    # 2. Recruiter creates a job
    job_resp = await client.post(
        "/api/v1/jobs/",
        headers=rec_h,
        json={
            "title": f"Senior Backend Engineer {tag}",
            "department": "Engineering",
            "location": "Mumbai",
            "description": "Own FastAPI + Postgres platform.",
            "required_skills": ["Python", "FastAPI", "PostgreSQL"],
            "nice_to_have_skills": ["Docker", "AWS"],
            "min_years": 3.0,
            "max_years": 7.0,
            "status": "open",
        },
    )
    assert job_resp.status_code == 201, job_resp.text
    job_id = uuid.UUID(job_resp.json()["id"])
    cleanup_records["jobs"].append(job_id)

    # 3. Create candidate with CTC + mobility fields
    cand_resp = await client.post(
        "/api/v1/candidates/",
        headers=rec_h,
        json={
            "full_name": f"Arjun Patel {tag}",
            "email": f"arjun.{tag}@example.com",
            "profile_summary": "Backend engineer specializing in Python and Postgres.",
            "years_experience": 4.5,
            "primary_domain": "Software Engineering",
            "technical_skills": ["Python", "FastAPI", "PostgreSQL"],
            "notice_period_days": 30,
            "current_ctc": 1400000,
            "expected_ctc": 1800000,
            "ctc_currency": "INR",
            "preferred_locations": ["Mumbai", "Remote"],
            "open_to_relocate": True,
            "raw_parsed_data": {"current_ctc": 1400000, "expected_ctc": 1800000, "ctc_currency": "INR"},
        },
    )
    assert cand_resp.status_code == 201, cand_resp.text
    cand_id = uuid.UUID(cand_resp.json()["id"])
    cleanup_records["candidates"].append(cand_id)

    # 4. CTC visibility RBAC: recruiter sees CTC; viewer gets CTC redacted (top-level + raw_parsed_data)
    rec_view = await client.get(f"/api/v1/candidates/{cand_id}", headers=rec_h)
    assert rec_view.status_code == 200
    assert rec_view.json()["current_ctc"] == 1400000
    assert rec_view.json()["expected_ctc"] == 1800000
    assert rec_view.json()["ctc_currency"] == "INR"

    viewer_view = await client.get(f"/api/v1/candidates/{cand_id}", headers=viewer_h)
    assert viewer_view.status_code == 200
    vbody = viewer_view.json()
    assert vbody["current_ctc"] is None
    assert vbody["expected_ctc"] is None
    assert vbody["ctc_currency"] is None
    assert "current_ctc" not in vbody["raw_parsed_data"]
    assert vbody["notice_period_days"] == 30
    assert vbody["open_to_relocate"] is True

    # Export JSON respects viewer CTC redaction & logs export audit
    viewer_export = await client.get(f"/api/v1/candidates/{cand_id}/export", headers=viewer_h)
    assert viewer_export.status_code == 200
    assert viewer_export.json()["current_ctc"] is None

    # Edit candidate logs edit audit
    upd_cand = await client.put(
        f"/api/v1/candidates/{cand_id}",
        headers=rec_h,
        json={"notice_period_days": 15},
    )
    assert upd_cand.status_code == 200
    assert upd_cand.json()["notice_period_days"] == 15

    # 5. Add candidate to job + duplicate guard (UNIQUE(candidate_id, job_id))
    app_resp = await client.post(
        "/api/v1/applications/",
        headers=rec_h,
        json={"candidate_id": str(cand_id), "job_id": str(job_id)},
    )
    assert app_resp.status_code == 201, app_resp.text
    app_id = uuid.UUID(app_resp.json()["id"])
    assert app_resp.json()["stage"] == "applied"

    dup_app = await client.post(
        "/api/v1/applications/",
        headers=rec_h,
        json={"candidate_id": str(cand_id), "job_id": str(job_id)},
    )
    assert dup_app.status_code == 409

    # 6. Move stage: applied -> interview -> rejected (with reason)
    mv1 = await client.patch(
        f"/api/v1/applications/{app_id}/stage",
        headers=rec_h,
        json={"stage": "interview", "reason": "Strong screening call"},
    )
    assert mv1.status_code == 200
    assert mv1.json()["stage"] == "interview"

    mv2 = await client.patch(
        f"/api/v1/applications/{app_id}/stage",
        headers=rec_h,
        json={"stage": "rejected", "rejection_reason": "Role filled internally"},
    )
    assert mv2.status_code == 200
    assert mv2.json()["stage"] == "rejected"
    assert mv2.json()["rejection_reason"] == "Role filled internally"

    # Viewer cannot move stage
    mv_forbid = await client.patch(
        f"/api/v1/applications/{app_id}/stage",
        headers=viewer_h,
        json={"stage": "hired"},
    )
    assert mv_forbid.status_code == 403

    # Verify application_events recorded 3 transitions (None->applied, applied->interview, interview->rejected)
    async with db_session_factory() as db:
        evs = (
            await db.execute(
                select(ApplicationEvent).where(ApplicationEvent.application_id == app_id)
            )
        ).scalars().all()
        assert len(evs) == 3

    # Job detail returns applications + stage counts
    jd = await client.get(f"/api/v1/jobs/{job_id}", headers=viewer_h)
    assert jd.status_code == 200
    assert jd.json()["application_count"] == 1
    assert jd.json()["stage_counts"]["rejected"] == 1

    # 7. Notes CRUD
    assert (
        await client.post(
            f"/api/v1/candidates/{cand_id}/notes",
            headers=viewer_h,
            json={"body": "Viewer blocked"},
        )
    ).status_code == 403

    note_resp = await client.post(
        f"/api/v1/candidates/{cand_id}/notes",
        headers=rec_h,
        json={"body": "Excellent FastAPI depth.", "tags": ["screening", "python"]},
    )
    assert note_resp.status_code == 201, note_resp.text
    note_id = note_resp.json()["id"]

    notes_list = await client.get(f"/api/v1/candidates/{cand_id}/notes", headers=viewer_h)
    assert notes_list.status_code == 200
    assert len(notes_list.json()) == 1

    # 8. Candidate activity timeline combines stage changes, notes, and view/edit/export audits
    act = await client.get(f"/api/v1/candidates/{cand_id}/activity", headers=viewer_h)
    assert act.status_code == 200
    kinds = {item["kind"] for item in act.json()}
    assert {"stage_change", "note", "audit"}.issubset(kinds)

    # Delete note
    assert (
        await client.delete(f"/api/v1/candidates/{cand_id}/notes/{note_id}", headers=rec_h)
    ).status_code == 204

    # 9. Delete candidate + verify audit_logs (admin only endpoint)
    assert (await client.get("/api/v1/audit-logs/", headers=rec_h)).status_code == 403
    assert (await client.delete(f"/api/v1/candidates/{cand_id}", headers=rec_h)).status_code == 204

    audit_resp = await client.get(
        "/api/v1/audit-logs/",
        headers=admin_h,
        params={"entity": "candidate", "entity_id": str(cand_id)},
    )
    assert audit_resp.status_code == 200
    actions = {row["action"] for row in audit_resp.json()}
    assert {"create", "view", "edit", "export", "delete"}.issubset(actions)

    # Stage-change audit recorded for the application
    async with db_session_factory() as db:
        stage_audits = (
            await db.execute(
                select(AuditLog).where(
                    AuditLog.entity == "application",
                    AuditLog.entity_id == str(app_id),
                    AuditLog.action == "stage_change",
                )
            )
        ).scalars().all()
        assert len(stage_audits) == 3


async def test_resume_text_never_exposed_and_viewer_ctc_redacted_including_free_text(
    client, seeded_users, db_session_factory, cleanup_records
):
    rec_h = await _login(client, seeded_users["recruiter"]["email"], seeded_users["recruiter"]["password"])
    viewer_h = await _login(client, seeded_users["viewer"]["email"], seeded_users["viewer"]["password"])

    tag = uuid.uuid4().hex[:6]
    secret_resume_text = (
        f"Rohan Verma {tag} Resume. Current CTC: 18 LPA. Expected CTC: 24 LPA. "
        "Confidential salary expectation ₹24,00,000 per annum. $150,000/yr."
    )

    mock_parsed = ParsedResume(
        contact=ContactDetails(
            full_name=f"Rohan Verma {tag}",
            email=f"rohan.{tag}@example.com",
            city="Pune",
        ),
        profile=ProfileOverview(
            summary="Senior engineer; Current CTC: 18 LPA, Expected CTC: 24 LPA, target $150,000/yr.",
            years_experience=5.0,
            primary_domain="Software Engineering",
        ),
        work_experience=[],
        education=[],
        skills=Skills(technical_skills=["Python"], tools=["Docker"], soft_skills=[]),
        additional_info=AdditionalInfo(
            current_ctc=1800000,
            expected_ctc=2400000,
            ctc_currency="INR",
            notice_period_days=60,
        ),
    )

    stored_name: str | None = None
    try:
        # 1. Verify upload response never contains _resume_text
        with (
            patch(
                "app.api.v1.endpoints.resumes.extract_text",
                new=AsyncMock(return_value=secret_resume_text),
            ),
            patch(
                "app.api.v1.endpoints.resumes.GeminiParser.__init__",
                new=lambda self, *a, **k: None,
            ),
            patch(
                "app.api.v1.endpoints.resumes.GeminiParser.parse_resume",
                new=AsyncMock(return_value=mock_parsed),
            ),
        ):
            up = await client.post(
                "/api/v1/resumes/upload",
                headers=rec_h,
                files={"file": ("rohan.pdf", b"%PDF-1.4 rohan", "application/pdf")},
            )
            assert up.status_code == 200, up.text
            up_body = up.json()
            rf_id = uuid.UUID(up_body["resume_file_id"])
            cleanup_records["resume_files"].append(rf_id)
            stored_name = up_body["parsed_data"]["raw_parsed_data"]["_stored_filename"]
            assert "_resume_text" not in json.dumps(up_body)

        # 2. Save candidate WITH _resume_text stored server-side in DB raw_parsed_data
        #    and CTC written in free text (summary, bullets, raw_parsed_data)
        payload = {
            "resume_file_id": str(rf_id),
            **up_body["parsed_data"],
            "work_experience": [
                {
                    "company": "Acme",
                    "job_title": "Engineer",
                    "start_date": "Jan 2020",
                    "end_date": "Present",
                    "bullets": ["Built APIs; compensation package ₹18,00,000 p.a."],
                }
            ],
            "raw_parsed_data": {
                **up_body["parsed_data"]["raw_parsed_data"],
                "_resume_text": secret_resume_text,
                "current_ctc": 1800000,
                "expected_ctc": 2400000,
                "ctc_currency": "INR",
                "free_note": "Candidate asked for Expected CTC: 24 LPA or $150,000/yr",
            },
        }
        created = await client.post("/api/v1/candidates/", headers=rec_h, json=payload)
        assert created.status_code == 201, created.text
        cand_id = uuid.UUID(created.json()["id"])
        cleanup_records["candidates"].append(cand_id)

        # Create response itself never leaks _resume_text
        assert "_resume_text" not in json.dumps(created.json())

        # Confirm _resume_text IS preserved in DB only
        async with db_session_factory() as db:
            db_cand = (await db.execute(select(Candidate).where(Candidate.id == cand_id))).scalar_one()
            assert db_cand.raw_parsed_data.get("_resume_text") == secret_resume_text

        # Confirm recruiter GET and PUT never expose _resume_text, while DB retains it
        rec_get = await client.get(f"/api/v1/candidates/{cand_id}", headers=rec_h)
        assert rec_get.status_code == 200
        assert "_resume_text" not in json.dumps(rec_get.json())
        assert rec_get.json()["current_ctc"] == 1800000

        rec_put = await client.put(
            f"/api/v1/candidates/{cand_id}",
            headers=rec_h,
            json={"raw_parsed_data": rec_get.json()["raw_parsed_data"], "city": "Mumbai"},
        )
        assert rec_put.status_code == 200
        assert "_resume_text" not in json.dumps(rec_put.json())

        async with db_session_factory() as db:
            db_cand = (await db.execute(select(Candidate).where(Candidate.id == cand_id))).scalar_one()
            assert db_cand.raw_parsed_data.get("_resume_text") == secret_resume_text

        # 3. Viewer detail AND export responses MUST NOT contain _resume_text or ANY CTC values
        forbidden_substrings = [
            "_resume_text",
            "1800000",
            "2400000",
            "18 LPA",
            "24 LPA",
            "24,00,000",
            "18,00,000",
            "$150,000",
            "Confidential salary",
        ]
        for path in (f"/api/v1/candidates/{cand_id}", f"/api/v1/candidates/{cand_id}/export"):
            resp = await client.get(path, headers=viewer_h)
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["current_ctc"] is None
            assert body["expected_ctc"] is None
            assert body["ctc_currency"] is None
            assert body["notice_period_days"] == 60

            serialized = json.dumps(body)
            for forbidden in forbidden_substrings:
                assert forbidden not in serialized, f"{forbidden!r} leaked in {path}: {serialized}"
    finally:
        if stored_name:
            await storage.delete_file(stored_name)


def test_vercel_json_rewrites_api_before_spa_catch_all():
    repo_root = Path(__file__).resolve().parents[2]
    cfg = json.loads((repo_root / "vercel.json").read_text(encoding="utf-8"))
    rewrites = cfg.get("rewrites", [])
    assert len(rewrites) >= 2
    assert rewrites[0]["source"] == "/api/(.*)"
    assert rewrites[0]["destination"].startswith("https://")
    assert rewrites[0]["destination"].endswith("/api/$1")
    assert rewrites[1]["source"] == "/(.*)"
    assert rewrites[1]["destination"] == "/index.html"

