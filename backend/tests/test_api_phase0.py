"""End-to-end async HTTP tests for Phase 0 foundations (runs against the configured database)."""

from datetime import datetime, timedelta, timezone
import uuid
from unittest.mock import AsyncMock, patch

from sqlalchemy import select, update

from app.models.candidate import ResumeFile, ResumeFileStatus
from app.schemas.resume import (
    AdditionalInfo,
    ContactDetails,
    EducationItem,
    ParsedResume,
    ProfileOverview,
    Skills,
    WorkExperienceItem,
)
from app.services.cleanup import cleanup_orphan_resumes
from app.services.file_storage import storage


async def _login(client, email: str, password: str) -> str:
    resp = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


async def test_auth_login_me_and_admin_user_creation(client, seeded_users, cleanup_records):
    assert (await client.get("/api/v1/auth/me")).status_code == 401
    assert (await client.get("/api/v1/candidates/")).status_code == 401
    assert (
        await client.get("/api/v1/candidates/", headers={"Authorization": "Bearer garbage"})
    ).status_code == 401

    bad = await client.post(
        "/api/v1/auth/login",
        json={"email": seeded_users["admin"]["email"], "password": "wrong"},
    )
    assert bad.status_code == 401

    inactive = await client.post(
        "/api/v1/auth/login",
        json={
            "email": seeded_users["inactive"]["email"],
            "password": seeded_users["inactive"]["password"],
        },
    )
    assert inactive.status_code == 401

    # Email lookup is case-insensitive
    admin_token = await _login(
        client, seeded_users["admin"]["email"].upper(), seeded_users["admin"]["password"]
    )
    me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {admin_token}"})
    assert me.status_code == 200
    assert me.json()["role"] == "admin"

    rec_token = await _login(
        client, seeded_users["recruiter"]["email"], seeded_users["recruiter"]["password"]
    )
    new_email = f"created-{uuid.uuid4().hex[:8]}@example.com"
    forbid = await client.post(
        "/api/v1/auth/users",
        headers={"Authorization": f"Bearer {rec_token}"},
        json={"email": new_email, "password": "Password123!", "role": "viewer"},
    )
    assert forbid.status_code == 403

    created = await client.post(
        "/api/v1/auth/users",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"email": new_email, "full_name": "Created User", "password": "Password123!", "role": "viewer"},
    )
    assert created.status_code == 201, created.text
    cleanup_records["users"].append(uuid.UUID(created.json()["id"]))

    dup = await client.post(
        "/api/v1/auth/users",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"email": new_email, "password": "Password123!", "role": "viewer"},
    )
    assert dup.status_code == 409


async def test_viewer_is_read_only_and_no_public_files_mount(client, seeded_users):
    assert (await client.get("/files/anything.pdf")).status_code == 404

    viewer_token = await _login(
        client, seeded_users["viewer"]["email"], seeded_users["viewer"]["password"]
    )
    headers = {"Authorization": f"Bearer {viewer_token}"}

    assert (await client.get("/api/v1/candidates/", headers=headers)).status_code == 200
    assert (await client.get("/api/v1/candidates/stats", headers=headers)).status_code == 200

    create_resp = await client.post(
        "/api/v1/candidates/",
        headers=headers,
        json={
            "full_name": "Blocked Candidate",
            "profile_summary": "Summary",
            "years_experience": 2.0,
            "primary_domain": "Engineering",
        },
    )
    assert create_resp.status_code == 403

    upload_resp = await client.post(
        "/api/v1/resumes/upload",
        headers=headers,
        files={"file": ("cv.pdf", b"%PDF-1.4 fake", "application/pdf")},
    )
    assert upload_resp.status_code == 403

    random_id = uuid.uuid4()
    assert (
        await client.put(f"/api/v1/candidates/{random_id}", headers=headers, json={})
    ).status_code == 403
    assert (await client.delete(f"/api/v1/candidates/{random_id}", headers=headers)).status_code == 403
    assert (await client.post("/api/v1/resumes/cleanup", headers=headers)).status_code == 403


def _mock_resume(tag: str) -> ParsedResume:
    return ParsedResume(
        contact=ContactDetails(
            full_name=f"Priya Sharma {tag}",
            email=f"Priya.Sharma.{tag}@Example.COM",
            phone="+91 98765-43210",
            city="Bengaluru",
        ),
        profile=ProfileOverview(
            summary="Backend engineer building distributed systems.",
            years_experience=99.0,
            primary_domain="Software Engineering",
        ),
        work_experience=[
            WorkExperienceItem(
                company="Alpha Labs",
                job_title="Engineer",
                start_date="Jan 2020",
                end_date="Dec 2021",
                bullets=["Built APIs"],
            ),
            WorkExperienceItem(
                company="Beta Corp",
                job_title="Senior Engineer",
                start_date="Jul 2021",
                end_date="Dec 2022",
                bullets=["Scaled Postgres"],
            ),
        ],
        education=[EducationItem(degree="B.Tech", institution="IIT", graduation_year=2019)],
        skills=Skills(technical_skills=["Python", "FastAPI"], tools=["PostgreSQL"], soft_skills=[]),
        additional_info=AdditionalInfo(),
    )


async def test_upload_years_stream_dedup_and_resolution(
    client, seeded_users, db_session_factory, cleanup_records
):
    rec_headers = {
        "Authorization": "Bearer "
        + await _login(client, seeded_users["recruiter"]["email"], seeded_users["recruiter"]["password"])
    }
    viewer_headers = {
        "Authorization": "Bearer "
        + await _login(client, seeded_users["viewer"]["email"], seeded_users["viewer"]["password"])
    }

    tag = uuid.uuid4().hex[:6]
    mock_parsed = _mock_resume(tag)
    stored_files: list[str] = []

    try:
        with (
            patch(
                "app.api.v1.endpoints.resumes.extract_text",
                new=AsyncMock(return_value="Priya Sharma resume text with enough content"),
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
            up1 = await client.post(
                "/api/v1/resumes/upload",
                headers=rec_headers,
                files={"file": ("priya.pdf", b"%PDF-1.4 priya-v1", "application/pdf")},
            )
            assert up1.status_code == 200, up1.text
            body1 = up1.json()
            rf1_id = uuid.UUID(body1["resume_file_id"])
            cleanup_records["resume_files"].append(rf1_id)
            stored_files.append(body1["parsed_data"]["raw_parsed_data"]["_stored_filename"])

            # Jan 2020 -> Dec 2022 merged = 36 months; LLM's 99 kept for reference only
            assert body1["parsed_data"]["years_experience"] == 3.0
            assert body1["parsed_data"]["raw_parsed_data"]["_llm_years_experience"] == 99.0
            assert body1["duplicate"]["is_duplicate"] is False

            async with db_session_factory() as db:
                rf1 = (await db.execute(select(ResumeFile).where(ResumeFile.id == rf1_id))).scalar_one()
                assert rf1.status == ResumeFileStatus.pending.value

            assert (await client.get(f"/api/v1/resumes/{rf1_id}/file")).status_code == 401
            stream_res = await client.get(f"/api/v1/resumes/{rf1_id}/file", headers=viewer_headers)
            assert stream_res.status_code == 200
            assert stream_res.content == b"%PDF-1.4 priya-v1"

            save1 = await client.post(
                "/api/v1/candidates/",
                headers=rec_headers,
                json={"resume_file_id": str(rf1_id), **body1["parsed_data"]},
            )
            assert save1.status_code == 201, save1.text
            cand1 = save1.json()
            cand1_id = uuid.UUID(cand1["id"])
            cleanup_records["candidates"].append(cand1_id)
            assert cand1["email"] == f"priya.sharma.{tag}@example.com"
            assert cand1["phone_normalized"] == "9876543210"
            assert cand1["is_duplicate_flagged"] is False

            async with db_session_factory() as db:
                rf1 = (await db.execute(select(ResumeFile).where(ResumeFile.id == rf1_id))).scalar_one()
                assert rf1.status == ResumeFileStatus.attached.value

            cand_stream = await client.get(
                f"/api/v1/candidates/{cand1_id}/resume?download=true", headers=viewer_headers
            )
            assert cand_stream.status_code == 200
            assert cand_stream.content == b"%PDF-1.4 priya-v1"
            assert cand_stream.headers["content-disposition"].startswith("attachment")

            # Second CV: different email, 0-prefixed phone, misspelled name
            mock_dup = mock_parsed.model_copy(deep=True)
            mock_dup.contact.email = f"different.{tag}@example.com"
            mock_dup.contact.phone = "09876543210"
            mock_dup.contact.full_name = f"Priya Sharm {tag}"

            with patch(
                "app.api.v1.endpoints.resumes.GeminiParser.parse_resume",
                new=AsyncMock(return_value=mock_dup),
            ):
                up2 = await client.post(
                    "/api/v1/resumes/upload",
                    headers=rec_headers,
                    files={"file": ("priya-v2.pdf", b"%PDF-1.4 priya-v2", "application/pdf")},
                )
            assert up2.status_code == 200, up2.text
            body2 = up2.json()
            rf2_id = uuid.UUID(body2["resume_file_id"])
            cleanup_records["resume_files"].append(rf2_id)
            stored_files.append(body2["parsed_data"]["raw_parsed_data"]["_stored_filename"])

            assert body2["duplicate"]["is_duplicate"] is True
            match = next(
                m for m in body2["duplicate"]["matches"] if m["candidate_id"] == str(cand1_id)
            )
            assert "phone" in match["matched_fields"]
            assert "name" in match["matched_fields"]
            assert "email" not in match["matched_fields"]

            conflict = await client.post(
                "/api/v1/candidates/",
                headers=rec_headers,
                json={"resume_file_id": str(rf2_id), **body2["parsed_data"]},
            )
            assert conflict.status_code == 409

            # Option A: "update existing"
            upd = await client.put(
                f"/api/v1/candidates/{cand1_id}",
                headers=rec_headers,
                json={"resume_file_id": str(rf2_id), "phone": "+91 98765 43210", "city": "Pune"},
            )
            assert upd.status_code == 200, upd.text
            assert upd.json()["city"] == "Pune"
            assert upd.json()["resume_file_id"] == str(rf2_id)

            async with db_session_factory() as db:
                rf2 = (await db.execute(select(ResumeFile).where(ResumeFile.id == rf2_id))).scalar_one()
                assert rf2.status == ResumeFileStatus.attached.value

            # Option B: "save as new" -> created and flagged
            save_dup = await client.post(
                "/api/v1/candidates/",
                headers=rec_headers,
                json={**body2["parsed_data"], "allow_duplicate": True},
            )
            assert save_dup.status_code == 201, save_dup.text
            cand2 = save_dup.json()
            cleanup_records["candidates"].append(uuid.UUID(cand2["id"]))
            assert cand2["is_duplicate_flagged"] is True
    finally:
        for fname in stored_files:
            await storage.delete_file(fname)


async def test_orphan_pending_resume_cleanup(db_session_factory, cleanup_records):
    meta_old_pending = await storage.save_file(b"old-pending", "old.pdf", "application/pdf")
    meta_fresh_pending = await storage.save_file(b"fresh-pending", "fresh.pdf", "application/pdf")
    meta_old_attached = await storage.save_file(b"old-attached", "attached.pdf", "application/pdf")
    old_time = datetime.now(timezone.utc) - timedelta(hours=30)

    def _row(meta: dict, status: str) -> ResumeFile:
        return ResumeFile(
            original_filename=meta["original_filename"],
            stored_filename=meta["stored_filename"],
            file_path=meta["file_path"],
            file_size=meta["file_size"],
            content_type="application/pdf",
            status=status,
        )

    try:
        async with db_session_factory() as db:
            rf_old = _row(meta_old_pending, ResumeFileStatus.pending.value)
            rf_fresh = _row(meta_fresh_pending, ResumeFileStatus.pending.value)
            rf_attached = _row(meta_old_attached, ResumeFileStatus.attached.value)
            db.add_all([rf_old, rf_fresh, rf_attached])
            await db.flush()
            await db.execute(
                update(ResumeFile)
                .where(ResumeFile.id.in_([rf_old.id, rf_attached.id]))
                .values(created_at=old_time)
            )
            await db.commit()
            old_id, fresh_id, attached_id = rf_old.id, rf_fresh.id, rf_attached.id
            cleanup_records["resume_files"].extend([old_id, fresh_id, attached_id])

        async with db_session_factory() as db:
            removed = await cleanup_orphan_resumes(db, storage_backend=storage, max_age_hours=24)
            assert removed >= 1

            def _get(rid):
                return db.execute(select(ResumeFile).where(ResumeFile.id == rid))

            assert (await _get(old_id)).scalar_one_or_none() is None
            assert (await _get(fresh_id)).scalar_one_or_none() is not None
            assert (await _get(attached_id)).scalar_one_or_none() is not None

        assert await storage.delete_file(meta_old_pending["stored_filename"]) is False
        assert await storage.read_file(meta_fresh_pending["stored_filename"]) == b"fresh-pending"
        assert await storage.read_file(meta_old_attached["stored_filename"]) == b"old-attached"
    finally:
        for m in (meta_old_pending, meta_fresh_pending, meta_old_attached):
            await storage.delete_file(m["stored_filename"])


async def test_delete_candidate_removes_physical_resume_file(
    client, seeded_users, db_session_factory, cleanup_records
):
    rec_headers = {
        "Authorization": "Bearer "
        + await _login(client, seeded_users["recruiter"]["email"], seeded_users["recruiter"]["password"])
    }
    meta = await storage.save_file(b"%PDF-1.4 delete-me", "delete-me.pdf", "application/pdf")
    stored_name = meta["stored_filename"]

    try:
        async with db_session_factory() as db:
            rf = ResumeFile(
                original_filename="delete-me.pdf",
                stored_filename=stored_name,
                file_path=meta["file_path"],
                file_size=meta["file_size"],
                content_type="application/pdf",
                status=ResumeFileStatus.pending.value,
            )
            db.add(rf)
            await db.commit()
            await db.refresh(rf)
            rf_id = rf.id
            cleanup_records["resume_files"].append(rf_id)

        tag = uuid.uuid4().hex[:6]
        created = await client.post(
            "/api/v1/candidates/",
            headers=rec_headers,
            json={
                "resume_file_id": str(rf_id),
                "full_name": f"Delete Target {tag}",
                "email": f"del-{tag}@example.com",
                "profile_summary": "Candidate to verify physical file deletion.",
                "years_experience": 1.0,
                "primary_domain": "Engineering",
            },
        )
        assert created.status_code == 201, created.text
        cand_id = uuid.UUID(created.json()["id"])
        cleanup_records["candidates"].append(cand_id)

        # File exists before deletion
        assert await storage.read_file(stored_name) == b"%PDF-1.4 delete-me"

        # Delete candidate -> DB rows AND physical storage file must be removed
        del_resp = await client.delete(f"/api/v1/candidates/{cand_id}", headers=rec_headers)
        assert del_resp.status_code == 204

        assert await storage.delete_file(stored_name) is False
        async with db_session_factory() as db:
            assert (await db.execute(select(ResumeFile).where(ResumeFile.id == rf_id))).scalar_one_or_none() is None
    finally:
        await storage.delete_file(stored_name)


async def test_refresh_cookie_rotation_reuse_detection_and_logout(client, seeded_users):
    # Login issues access token + httpOnly refresh cookie
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": seeded_users["recruiter"]["email"], "password": seeded_users["recruiter"]["password"]},
    )
    assert login_resp.status_code == 200
    set_cookie = login_resp.headers.get("set-cookie", "")
    assert "hrms_refresh_token=" in set_cookie
    assert "httponly" in set_cookie.lower()
    first_cookie = login_resp.cookies.get("hrms_refresh_token")
    assert first_cookie

    # Refresh rotates cookie and returns a new access token
    ref1 = await client.post("/api/v1/auth/refresh", cookies={"hrms_refresh_token": first_cookie})
    assert ref1.status_code == 200, ref1.text
    second_cookie = ref1.cookies.get("hrms_refresh_token")
    assert second_cookie and second_cookie != first_cookie

    # Replaying the already-rotated (revoked) first cookie triggers reuse detection
    # and revokes ALL sessions for that user (including second_cookie)
    replay = await client.post("/api/v1/auth/refresh", cookies={"hrms_refresh_token": first_cookie})
    assert replay.status_code == 401

    after_replay = await client.post(
        "/api/v1/auth/refresh", cookies={"hrms_refresh_token": second_cookie}
    )
    assert after_replay.status_code == 401

    # Fresh login + logout revokes the refresh cookie cleanly
    login2 = await client.post(
        "/api/v1/auth/login",
        json={"email": seeded_users["recruiter"]["email"], "password": seeded_users["recruiter"]["password"]},
    )
    assert login2.status_code == 200
    cookie2 = login2.cookies.get("hrms_refresh_token")
    assert cookie2

    out = await client.post("/api/v1/auth/logout", cookies={"hrms_refresh_token": cookie2})
    assert out.status_code == 204

    post_logout = await client.post("/api/v1/auth/refresh", cookies={"hrms_refresh_token": cookie2})
    assert post_logout.status_code == 401


async def test_login_rate_limiting_and_lockout(client, seeded_users):
    email = seeded_users["viewer"]["email"]
    good_pw = seeded_users["viewer"]["password"]

    # Default LOGIN_MAX_ATTEMPTS = 5: first 4 fail with 401, 5th triggers 429 lockout
    for i in range(4):
        r = await client.post("/api/v1/auth/login", json={"email": email, "password": "wrong-pw"})
        assert r.status_code == 401, f"attempt {i + 1} expected 401, got {r.status_code}"

    fifth = await client.post("/api/v1/auth/login", json={"email": email, "password": "wrong-pw"})
    assert fifth.status_code == 429
    assert int(fifth.headers.get("retry-after", "0")) > 0

    # Even with the correct password, login stays locked out (429)
    blocked = await client.post("/api/v1/auth/login", json={"email": email, "password": good_pw})
    assert blocked.status_code == 429

