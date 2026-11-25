"""Phase 3 tests: bulk upload queue, OCR fallback, PDF/XLSX exports, blind mode, pending delete, and privacy retention."""

from datetime import datetime, timedelta, timezone
from io import BytesIO
import uuid

import fitz
from openpyxl import load_workbook
import pytest
from sqlalchemy import select

from app.core.config import settings
from app.models.candidate import Candidate, ResumeFile, ResumeFileStatus
from app.models.pipeline import AuditLog
from app.schemas.resume import (
    AdditionalInfo,
    ContactDetails,
    EducationItem,
    ParsedResume,
    ProfileOverview,
    Skills,
    WorkExperienceItem,
)
from app.services.file_storage import storage
from app.services.text_extraction import extract_text_from_pdf_with_ocr


def _make_pdf_bytes(text: str = "") -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    if text:
        page.insert_text((72, 72), text)
    out = doc.tobytes()
    doc.close()
    return out


async def _login(client, email: str, password: str) -> str:
    res = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert res.status_code == 200, res.text
    return res.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_ocr_fallback_for_scanned_pdf(monkeypatch):
    # Blank/image-only PDF triggers OCR fallback when enabled
    scanned_pdf = _make_pdf_bytes("")

    async def fake_ocr(_pdf_bytes: bytes) -> str:
        return "Jane Scanned — Senior DevOps Engineer with 6 years of Kubernetes and AWS experience."

    monkeypatch.setattr(settings, "ENABLE_OCR_FALLBACK", True)
    monkeypatch.setattr("app.services.text_extraction.ocr_scanned_pdf", fake_ocr)

    text_out, ocr_used = await extract_text_from_pdf_with_ocr(scanned_pdf)
    assert ocr_used is True
    assert "Senior DevOps Engineer" in text_out

    # When disabled, OCR is skipped
    monkeypatch.setattr(settings, "ENABLE_OCR_FALLBACK", False)
    text_disabled, ocr_disabled = await extract_text_from_pdf_with_ocr(scanned_pdf)
    assert ocr_disabled is False
    assert text_disabled == ""

    # Digital text PDF does NOT trigger OCR
    monkeypatch.setattr(settings, "ENABLE_OCR_FALLBACK", True)
    digital_pdf = _make_pdf_bytes(
        "Digital Resume — Full Stack Engineer specializing in Python, FastAPI, React, and PostgreSQL."
    )
    text_digital, ocr_digital = await extract_text_from_pdf_with_ocr(digital_pdf)
    assert ocr_digital is False
    assert "Full Stack Engineer" in text_digital


@pytest.mark.asyncio
async def test_pending_resume_delete_and_attached_guard(
    client, seeded_users, cleanup_records, db_session_factory
):
    rec_token = await _login(
        client, seeded_users["recruiter"]["email"], seeded_users["recruiter"]["password"]
    )
    viewer_token = await _login(
        client, seeded_users["viewer"]["email"], seeded_users["viewer"]["password"]
    )

    # Store a pending file
    pdf_bytes = _make_pdf_bytes("Pending Candidate CV")
    meta = await storage.save_file(pdf_bytes, "pending-discard.pdf", "application/pdf")
    async with db_session_factory() as db:
        rf = ResumeFile(
            original_filename=meta["original_filename"],
            stored_filename=meta["stored_filename"],
            file_path=meta["file_path"],
            file_size=meta["file_size"],
            content_type=meta["content_type"],
            status=ResumeFileStatus.pending.value,
        )
        db.add(rf)
        await db.commit()
        await db.refresh(rf)
        rf_id = rf.id

    cleanup_records["resume_files"].append(rf_id)

    # Viewer cannot delete
    forbid = await client.delete(f"/api/v1/resumes/{rf_id}", headers=_auth(viewer_token))
    assert forbid.status_code == 403

    # Recruiter can delete pending file -> removed from DB & physical storage
    del_res = await client.delete(f"/api/v1/resumes/{rf_id}", headers=_auth(rec_token))
    assert del_res.status_code == 204
    with pytest.raises(FileNotFoundError):
        await storage.read_file(meta["stored_filename"])


@pytest.mark.asyncio
async def test_bulk_upload_queue_and_polling(
    client, seeded_users, cleanup_records, db_session_factory, monkeypatch
):
    rec_token = await _login(
        client, seeded_users["recruiter"]["email"], seeded_users["recruiter"]["password"]
    )
    tag = uuid.uuid4().hex[:8]

    async def fake_parse(self, resume_text: str) -> ParsedResume:
        who = "Alice Bulk" if "Alice" in resume_text else "Bob Bulk"
        return ParsedResume(
            contact=ContactDetails(
                full_name=f"{who} {tag}",
                email=f"{who.split()[0].lower()}.{tag}@example.com",
                phone="+91 9820012345",
                city="Mumbai",
            ),
            profile=ProfileOverview(
                summary="Experienced software engineer.",
                years_experience=1.0,
                primary_domain="Software Engineering",
            ),
            work_experience=[
                WorkExperienceItem(
                    company="TechCorp",
                    job_title="Engineer",
                    start_date="Jan 2021",
                    end_date="Jan 2024",
                    bullets=["Built scalable APIs."],
                )
            ],
            education=[
                EducationItem(degree="B.Tech", institution="NIT Surat", graduation_year=2020)
            ],
            skills=Skills(technical_skills=["Python"], tools=["Docker"], soft_skills=["Teamwork"]),
            additional_info=AdditionalInfo(languages=["English"]),
        )

    monkeypatch.setattr("app.services.bulk_parse.GeminiParser.parse_resume", fake_parse)
    monkeypatch.setattr("app.services.bulk_parse.AsyncSessionLocal", db_session_factory)
    monkeypatch.setattr(settings, "REDIS_URL", None)

    pdf1 = _make_pdf_bytes("Alice Resume — Senior Python Engineer with FastAPI and Docker skills.")
    pdf2 = _make_pdf_bytes("Bob Resume — Backend Engineer specializing in PostgreSQL and Python.")

    res = await client.post(
        "/api/v1/resumes/bulk-upload",
        files=[
            ("files", ("alice.pdf", pdf1, "application/pdf")),
            ("files", ("bob.pdf", pdf2, "application/pdf")),
        ],
        headers=_auth(rec_token),
    )
    assert res.status_code == 202, res.text
    body = res.json()
    assert body["queue_backend"] == "background_tasks"
    assert len(body["jobs"]) == 2
    batch_id = body["batch_id"]

    for j in body["jobs"]:
        cleanup_records["parse_jobs"].append(uuid.UUID(j["id"]))
        if j.get("resume_file_id"):
            cleanup_records["resume_files"].append(uuid.UUID(j["resume_file_id"]))

    # Poll batch jobs (ASGITransport runs FastAPI BackgroundTasks before response finishes)
    poll = await client.get(
        "/api/v1/resumes/parse-jobs",
        params={"batch_id": batch_id},
        headers=_auth(rec_token),
    )
    assert poll.status_code == 200, poll.text
    assert "_resume_text" not in poll.text
    jobs = poll.json()
    assert len(jobs) == 2
    for j in jobs:
        assert j["status"] == "done", j
        assert j["result_json"]["years_experience"] == 3.1  # deterministic Jan 2021 - Jan 2024 inclusive (37 mos)

    # Clean up stored files created during test
    async with db_session_factory() as db:
        rfs = (
            await db.execute(
                select(ResumeFile).where(ResumeFile.id.in_(cleanup_records["resume_files"]))
            )
        ).scalars().all()
        for rf in rfs:
            await storage.delete_file(rf.stored_filename)


@pytest.mark.asyncio
async def test_pdf_xlsx_exports_and_blind_screening_redaction(
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

    secret_name = f"Priya Sharma {tag}"
    secret_email = f"priya.{tag}@example.com"
    secret_phone = "+91 9876543210"
    secret_college = f"Stanford University {tag}"

    create_res = await client.post(
        "/api/v1/candidates/",
        json={
            "full_name": secret_name,
            "email": secret_email,
            "phone": secret_phone,
            "city": "Pune",
            "linkedin_url": f"https://linkedin.com/in/priya-{tag}",
            "profile_summary": f"{secret_name} is a Staff ML Engineer expecting 42 LPA.",
            "years_experience": 7.0,
            "primary_domain": "AI/ML Engineering",
            "work_experience": [
                {
                    "company": "DeepScale",
                    "job_title": "Staff ML Engineer",
                    "start_date": "2020-01",
                    "end_date": "Present",
                    "bullets": ["Led LLM inference team."],
                }
            ],
            "education": [
                {"degree": "M.S. Computer Science", "institution": secret_college, "graduation_year": 2018}
            ],
            "technical_skills": ["Python", "PyTorch"],
            "tools": ["Kubernetes"],
            "soft_skills": ["Mentoring"],
            "hobbies_interests": [],
            "languages": ["English"],
            "certifications": ["AWS ML Specialty"],
            "notice_period_days": 30,
            "current_ctc": 3500000,
            "expected_ctc": 4200000,
            "ctc_currency": "INR",
            "source": "referral",
            "consent_given_at": datetime.now(timezone.utc).isoformat(),
            "allow_duplicate": True,
        },
        headers=_auth(rec_token),
    )
    assert create_res.status_code == 201, create_res.text
    cand = create_res.json()
    cid = cand["id"]
    cleanup_records["candidates"].append(uuid.UUID(cid))
    assert cand["source"] == "referral"
    assert cand["consent_given_at"] is not None

    # 1. Blind candidate detail hides name, email, phone, social links, and college
    blind_detail = await client.get(
        f"/api/v1/candidates/{cid}",
        params={"blind": True},
        headers=_auth(viewer_token),
    )
    assert blind_detail.status_code == 200
    b_body = blind_detail.json()
    assert b_body["full_name"].startswith("Candidate #")
    assert b_body["email"] is None
    assert b_body["phone"] is None
    assert b_body["linkedin_url"] is None
    assert b_body["education"][0]["institution"] == "[Institution Redacted]"
    for forbidden in (secret_name, secret_email, secret_phone, secret_college, "3500000", "42 LPA"):
        assert forbidden not in blind_detail.text

    # 2. One-page PDF export (blind + viewer)
    pdf_res = await client.get(
        f"/api/v1/candidates/{cid}/export/pdf",
        params={"blind": True},
        headers=_auth(viewer_token),
    )
    assert pdf_res.status_code == 200
    assert pdf_res.headers["content-type"].startswith("application/pdf")
    assert pdf_res.content.startswith(b"%PDF")
    pdf_doc = fitz.open(stream=pdf_res.content, filetype="pdf")
    assert len(pdf_doc) == 1
    pdf_text = pdf_doc[0].get_text()
    pdf_doc.close()
    assert "BLIND SCREENING BRIEF" in pdf_text
    assert "Candidate #" in pdf_text
    assert "Python" in pdf_text
    for forbidden in (secret_name, secret_email, secret_phone, secret_college, "3,500,000", "42 LPA"):
        assert forbidden not in pdf_text

    # 3. Job shortlist XLSX export (blind + viewer)
    job_res = await client.post(
        "/api/v1/jobs/",
        json={
            "title": f"Staff ML Engineer {tag}",
            "department": "AI",
            "location": "Remote",
            "description": "PyTorch & Kubernetes",
            "required_skills": ["Python", "PyTorch"],
            "nice_to_have_skills": ["Kubernetes"],
            "min_years": 5.0,
            "max_years": 10.0,
            "status": "open",
        },
        headers=_auth(rec_token),
    )
    assert job_res.status_code == 201
    job_id = job_res.json()["id"]
    cleanup_records["jobs"].append(uuid.UUID(job_id))

    app_res = await client.post(
        "/api/v1/applications/",
        json={"candidate_id": cid, "job_id": job_id, "stage": "interview"},
        headers=_auth(rec_token),
    )
    assert app_res.status_code == 201

    xlsx_res = await client.get(
        f"/api/v1/jobs/{job_id}/export/xlsx",
        params={"blind": True},
        headers=_auth(viewer_token),
    )
    assert xlsx_res.status_code == 200
    wb = load_workbook(BytesIO(xlsx_res.content))
    ws = wb.active
    assert ws is not None
    all_cells = [
        str(cell.value or "")
        for row in ws.iter_rows()
        for cell in row
    ]
    joined = " | ".join(all_cells)
    assert "Candidate #" in joined
    assert "interview" in joined
    assert "Current CTC" not in joined
    assert "Email" not in joined
    for forbidden in (secret_name, secret_email, secret_phone, secret_college, "3500000"):
        assert forbidden not in joined


@pytest.mark.asyncio
async def test_retention_purge_removes_file_and_keeps_pii_free_audit(
    client, seeded_users, cleanup_records, db_session_factory, monkeypatch
):
    admin_token = await _login(client, seeded_users["admin"]["email"], seeded_users["admin"]["password"])
    rec_token = await _login(
        client, seeded_users["recruiter"]["email"], seeded_users["recruiter"]["password"]
    )
    tag = uuid.uuid4().hex[:8]
    monkeypatch.setattr(settings, "ENABLE_SEMANTIC_SEARCH", False)

    # Save a real resume file and attach to an expired candidate (400 days old consent)
    pdf_bytes = _make_pdf_bytes("Expired candidate resume text")
    meta = await storage.save_file(pdf_bytes, f"expired-{tag}.pdf", "application/pdf")
    async with db_session_factory() as db:
        rf = ResumeFile(
            original_filename=meta["original_filename"],
            stored_filename=meta["stored_filename"],
            file_path=meta["file_path"],
            file_size=meta["file_size"],
            content_type=meta["content_type"],
            status=ResumeFileStatus.pending.value,
        )
        db.add(rf)
        await db.commit()
        await db.refresh(rf)
        rf_id = rf.id

    old_consent = (datetime.now(timezone.utc) - timedelta(days=400)).isoformat()
    old_name = f"Expired Person {tag}"
    old_email = f"expired.{tag}@example.com"

    create_res = await client.post(
        "/api/v1/candidates/",
        json={
            "resume_file_id": str(rf_id),
            "full_name": old_name,
            "email": old_email,
            "profile_summary": "Expired retention test candidate.",
            "years_experience": 3.0,
            "primary_domain": "Operations",
            "technical_skills": ["Excel"],
            "source": "careers",
            "consent_given_at": old_consent,
            "raw_parsed_data": {"_resume_text": "SENSITIVE RAW RESUME TEXT"},
            "allow_duplicate": True,
        },
        headers=_auth(rec_token),
    )
    assert create_res.status_code == 201, create_res.text
    cid = uuid.UUID(create_res.json()["id"])
    cleanup_records["candidates"].append(cid)
    cleanup_records["resume_files"].append(rf_id)

    # Recruiter forbidden from triggering retention purge
    forbid = await client.post(
        "/api/v1/privacy/purge-expired",
        params={"retention_days": 365, "dry_run": True},
        headers=_auth(rec_token),
    )
    assert forbid.status_code == 403

    # Admin dry-run finds candidate without deleting
    dry_res = await client.post(
        "/api/v1/privacy/purge-expired",
        params={"retention_days": 365, "dry_run": True},
        headers=_auth(admin_token),
    )
    assert dry_res.status_code == 200, dry_res.text
    dry_body = dry_res.json()
    assert str(cid) in dry_body["candidate_ids"]
    assert dry_body["purged_count"] == 0

    # Admin real purge removes candidate row, wipes _resume_text, deletes physical file, keeps PII-free audit
    purge_res = await client.post(
        "/api/v1/privacy/purge-expired",
        params={"retention_days": 365, "dry_run": False},
        headers=_auth(admin_token),
    )
    assert purge_res.status_code == 200, purge_res.text
    assert str(cid) in purge_res.json()["candidate_ids"]
    assert purge_res.json()["purged_count"] >= 1

    # Physical resume file is gone
    with pytest.raises(FileNotFoundError):
        await storage.read_file(meta["stored_filename"])

    # Candidate row is gone, PII-free audit entry remains
    async with db_session_factory() as db:
        cand_row = (await db.execute(select(Candidate).where(Candidate.id == cid))).scalar_one_or_none()
        assert cand_row is None

        audit_row = (
            await db.execute(
                select(AuditLog).where(
                    AuditLog.entity == "candidate",
                    AuditLog.entity_id == str(cid),
                    AuditLog.action == "retention_purge",
                )
            )
        ).scalar_one_or_none()
        assert audit_row is not None
        audit_blob = str(audit_row.details)
        assert old_name not in audit_blob
        assert old_email not in audit_blob
        assert "SENSITIVE RAW RESUME TEXT" not in audit_blob
