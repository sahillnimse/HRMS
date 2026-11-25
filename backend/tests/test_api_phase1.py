"""End-to-end async HTTP tests for Phase 1 (Hiring Pipeline, Notes, CTC RBAC, Audit Logs)."""

import uuid

from sqlalchemy import select

from app.models.pipeline import ApplicationEvent, AuditLog


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
