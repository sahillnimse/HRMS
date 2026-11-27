"""
Tests for Stage 1 (section parsing, storage, migration, admin re-map) and
Stage 2 (study-aware timeline, employment-type tenure stats, whole-CV skill evidence, brief cache).
"""

from datetime import date
import uuid

import pytest
from sqlalchemy import text

from app.core.config import settings
from app.schemas.resume import EducationItem, ParsedResume, ProjectItem, WorkExperienceItem
from app.services.section_mapping import (
    deduplicate_skills_across_lists,
    extract_education_dates_from_text,
    extract_projects_from_text,
    infer_employment_type,
    parse_education_dates,
)


async def _login(client, email: str, password: str) -> str:
    res = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert res.status_code == 200, res.text
    return res.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Stage 1 unit tests: parser schemas, employment_type word boundaries, edu dates, projects
# ---------------------------------------------------------------------------


def test_employment_type_word_boundaries():
    assert infer_employment_type("Software Engineering Intern", "Acme") == "internship"
    assert infer_employment_type("Data Science Internship", "Beta") == "internship"
    assert infer_employment_type("Graduate Engineer Trainee", "Infosys") == "trainee"
    assert infer_employment_type("Apprentice Developer", "Startup") == "trainee"
    assert infer_employment_type("Backend Developer (Contract)", "Corp") == "contract"
    assert infer_employment_type("Freelance Designer", "Self") == "freelance"
    assert infer_employment_type("Part-time Tutor", "EdTech") == "part_time"

    # Must NOT misclassify words merely containing "intern"
    assert infer_employment_type("Internal Tools Engineer", "BigCo") == "unknown"
    assert infer_employment_type("International Relations Lead", "GlobalCo") == "unknown"
    assert infer_employment_type("Internal Tools Engineer", "BigCo", "full_time") == "full_time"


def test_education_date_formats():
    # "2020-2024"
    s, e, g, cur = parse_education_dates(date_range="2020–2024")
    assert (s, e, g, cur) == (2020, 2024, 2024, False)

    # "Aug 2020 - May 2024"
    s, e, g, cur = parse_education_dates(date_range="Aug 2020 – May 2024")
    assert (s, e, g, cur) == (2020, 2024, 2024, False)

    # "Expected 2026"
    s, e, g, cur = parse_education_dates(graduation_year="Expected 2026")
    assert (s, e, g, cur) == (None, 2026, 2026, True)

    # "Pursuing"
    s, e, g, cur = parse_education_dates(start_year=2023, end_year="Pursuing")
    assert (s, e, g, cur) == (2023, None, None, True)

    # Old shape: graduation_year only
    edu = EducationItem(degree="B.E.", institution="State Univ", graduation_year=2024)
    assert edu.end_year == 2024
    assert edu.graduation_year == 2024
    assert edu.start_year is None
    assert edu.is_current is False


def test_parsed_resume_mocked_gemini_output_with_new_sections():
    raw_gemini = {
        "contact": {"full_name": "Aanya Sharma", "email": "aanya@example.com"},
        "profile": {
            "summary": "Computer Science graduate with ML projects and backend experience.",
            "years_experience": 1.5,
            "primary_domain": "Software Engineering",
        },
        "work_experience": [
            {
                "company": "FinCorp",
                "job_title": "Internal Tools Engineer",
                "employment_type": "full_time",
                "start_date": "Jul 2024",
                "end_date": "Present",
                "bullets": ["Built internal FastAPI dashboards."],
            },
            {
                "company": "AI Lab",
                "job_title": "ML Intern",
                "start_date": "May 2023",
                "end_date": "Jul 2023",
                "bullets": ["Trained classification pipelines."],
            },
        ],
        "education": [
            {
                "degree": "B.E.",
                "field_of_study": "Computer Engineering",
                "institution": "Pune University",
                "date_range": "Aug 2020 – May 2024",
            }
        ],
        "projects": [
            {
                "name": "Resume Matcher",
                "description": "Built semantic matching with PyTorch and pgvector.",
                "technologies": ["PyTorch", "PostgreSQL", "Docker"],
                "start_date": "Jan 2024",
                "end_date": "Apr 2024",
            }
        ],
        "skills": {
            "technical_skills": ["Python", "ML", "Machine Learning", "PyTorch"],
            "tools": ["Docker", "Postgres", "PostgreSQL"],
            "soft_skills": ["Communication"],
        },
    }
    parsed = ParsedResume(**raw_gemini)
    assert parsed.work_experience[0].employment_type == "full_time"
    assert parsed.work_experience[1].employment_type == "internship"
    assert parsed.education[0].start_year == 2020
    assert parsed.education[0].end_year == 2024
    assert parsed.education[0].graduation_year == 2024
    assert parsed.education[0].field_of_study == "Computer Engineering"
    assert len(parsed.projects) == 1
    assert parsed.projects[0].name == "Resume Matcher"

    flat = parsed.to_flat_dict()
    assert "projects" in flat and len(flat["projects"]) == 1

    # Skill deduplication across technical_skills & tools via alias map
    alias_map = {
        "ml": "Machine Learning",
        "machine learning": "Machine Learning",
        "postgres": "PostgreSQL",
        "postgresql": "PostgreSQL",
        "docker": "Docker",
    }
    tech, tools = deduplicate_skills_across_lists(
        ["Python", "ML", "Machine Learning", "Docker", "REST APIs", "REST API"],
        ["Docker", "Postgres", "PostgreSQL"],
        alias_map,
    )
    assert tech == ["Python", "Machine Learning", "Docker", "REST APIs"]
    assert tools == ["PostgreSQL"]  # Docker deduplicated across lists, Postgres collapsed


def test_deterministic_text_fallback_extractors():
    sample_cv = """
    EDUCATION
    B.E. Computer Science, State Engineering College (Aug 2020 – May 2024)

    PROJECTS
    Smart Inventory Tracker | Python, FastAPI, PostgreSQL
    - Built barcode scanner and automated low-stock alerts.
    Tech: Docker, Redis

    EXPERIENCE
    Software Intern, Acme Corp
    """
    enriched_edu = extract_education_dates_from_text(
        sample_cv,
        [{"degree": "B.E. Computer Science", "institution": "State Engineering College", "graduation_year": 2024}],
    )
    assert enriched_edu[0]["start_year"] == 2020
    assert enriched_edu[0]["end_year"] == 2024

    extracted_projects = extract_projects_from_text(sample_cv)
    assert len(extracted_projects) == 1
    assert extracted_projects[0]["name"] == "Smart Inventory Tracker"
    assert "PostgreSQL" in extracted_projects[0]["technologies"]
    assert "Docker" in extracted_projects[0]["technologies"]


@pytest.mark.asyncio
async def test_admin_remap_endpoint_dry_run_and_hand_edit_protection(
    client, seeded_users, cleanup_records, db_session_factory, monkeypatch
):
    monkeypatch.setattr(settings, "ENABLE_SEMANTIC_SEARCH", False)
    admin_token = await _login(client, seeded_users["admin"]["email"], seeded_users["admin"]["password"])
    rec_token = await _login(
        client, seeded_users["recruiter"]["email"], seeded_users["recruiter"]["password"]
    )
    tag = uuid.uuid4().hex[:8]

    # Non-admin gets 403
    forbid = await client.post("/api/v1/candidates/admin/remap-sections", headers=_auth(rec_token))
    assert forbid.status_code == 403

    # Create a legacy-shaped candidate directly with _resume_text in raw_parsed_data
    cand_res = await client.post(
        "/api/v1/candidates/",
        json={
            "full_name": f"Legacy Fresher {tag}",
            "email": f"legacy.{tag}@example.com",
            "profile_summary": "Fresher developer.",
            "years_experience": 1.0,
            "primary_domain": "Software Engineering",
            "work_experience": [
                {
                    "company": "TechCo",
                    "job_title": "Software Intern",
                    "start_date": "Jan 2023",
                    "end_date": "Jun 2023",
                    "bullets": ["Built APIs."],
                }
            ],
            "education": [
                {"degree": "B.E.", "institution": "State College", "graduation_year": 2024}
            ],
            "technical_skills": ["Python"],
            "raw_parsed_data": {
                "_resume_text": (
                    "EDUCATION\n"
                    "B.E. State College 2020 - 2024\n\n"
                    "PROJECTS\n"
                    "Campus Portal | Python, React\n"
                    "- Built student timetable portal.\n"
                )
            },
            "allow_duplicate": True,
        },
        headers=_auth(rec_token),
    )
    assert cand_res.status_code == 201, cand_res.text
    cid = cand_res.json()["id"]
    cleanup_records["candidates"].append(uuid.UUID(cid))

    # Simulate legacy DB row without employment_type on work_experience
    async with db_session_factory() as db:
        await db.execute(
            text(
                "UPDATE candidates SET work_experience = CAST(:we AS jsonb), "
                "education = CAST(:ed AS jsonb) WHERE id = :cid"
            ),
            {
                "we": '[{"company": "TechCo", "job_title": "Software Intern", "start_date": "Jan 2023", "end_date": "Jun 2023", "bullets": ["Built APIs."]}]',
                "ed": '[{"degree": "B.E.", "institution": "State College", "graduation_year": 2024}]',
                "cid": uuid.UUID(cid),
            },
        )
        await db.commit()

    # 1. Dry run (default) previews changes without modifying DB
    dry = await client.post(
        f"/api/v1/candidates/admin/remap-sections?candidate_id={cid}",
        headers=_auth(admin_token),
    )
    assert dry.status_code == 200, dry.text
    dry_data = dry.json()
    assert dry_data["dry_run"] is True
    assert dry_data["would_update"] == 1
    assert dry_data["updated"] == 0
    assert set(dry_data["results"][0]["updated_fields"]) == {
        "work_experience",
        "education",
        "projects",
    }

    # Verify DB untouched by dry run
    before = await client.get(f"/api/v1/candidates/{cid}", headers=_auth(admin_token))
    assert before.json()["projects"] == []

    # 2. Hand-edit `education` via PUT -> remap must skip `education`!
    edit_res = await client.put(
        f"/api/v1/candidates/{cid}",
        json={
            "education": [
                {
                    "degree": "B.E. (Edited)",
                    "institution": "State College",
                    "start_year": 2019,
                    "end_year": 2024,
                    "graduation_year": 2024,
                }
            ]
        },
        headers=_auth(rec_token),
    )
    assert edit_res.status_code == 200

    # 3. Apply remap (dry_run=false): updates work_experience & projects, skips hand-edited education!
    applied = await client.post(
        f"/api/v1/candidates/admin/remap-sections?dry_run=false&candidate_id={cid}",
        headers=_auth(admin_token),
    )
    assert applied.status_code == 200, applied.text
    app_data = applied.json()
    assert app_data["dry_run"] is False
    assert app_data["updated"] == 1
    assert "education" in app_data["results"][0]["skipped_hand_edited_fields"]
    assert "projects" in app_data["results"][0]["updated_fields"]
    assert "work_experience" in app_data["results"][0]["updated_fields"]

    after = await client.get(f"/api/v1/candidates/{cid}", headers=_auth(admin_token))
    after_data = after.json()
    assert after_data["education"][0]["start_year"] == 2019  # Hand edit preserved!
    assert after_data["work_experience"][0]["employment_type"] == "internship"
    assert len(after_data["projects"]) == 1
    assert after_data["projects"][0]["name"] == "Campus Portal"
