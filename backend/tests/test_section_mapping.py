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


# ---------------------------------------------------------------------------
# Stage 2 unit & API tests: study windows, employment types, whole-CV skill evidence, brief cache
# ---------------------------------------------------------------------------


def test_bug_shape_fresher_profile_fires_zero_false_flags():
    """
    Reproduce the exact reported fresher profile:
      - B.E. graduated in 2024 (old shape: graduation_year only, no start_year!)
      - Internships / trainee stints during 2023-24 with a 9-month span (2023-05 to 2024-01) during college
      - Full-time role only after graduating (Jul 2024 - Present)
      - Skills evidenced across summary, work bullets, projects, certifications, education, and ML/Postgres aliases
    NONE of the three false flags (employment_gap, repeated_short_stints, unverified_listed_skills) may fire.
    """
    from app.services.consistency import compute_skill_evidence, run_consistency_checks
    from app.services.timeline import build_career_timeline, build_study_windows

    today = date(2026, 6, 1)
    work = [
        {
            "company": "FinTech Corp",
            "job_title": "Software Engineer",
            "employment_type": "full_time",
            "start_date": "Jul 2024",
            "end_date": "Present",
            "bullets": ["Built FastAPI microservices and PostgreSQL pipelines."],
        },
        {
            "company": "TechLabs",
            "job_title": "Graduate Engineer Trainee",
            "start_date": "Feb 2024",
            "end_date": "May 2024",
            "bullets": ["Assisted with CI/CD workflows and unit testing."],
        },
        {
            "company": "AI Startup",
            "job_title": "Data Science Intern",
            "start_date": "Feb 2023",
            "end_date": "Apr 2023",
            "bullets": ["Built ML models in Python."],
        },
        {
            "company": "WebShop",
            "job_title": "Frontend Intern",
            "start_date": "Jun 2022",
            "end_date": "Aug 2022",
            "bullets": ["Created React components."],
        },
    ]
    # Old-shape education (graduation_year only -> estimated 48-month B.E. window ending June 2024)
    education = [
        {
            "degree": "B.E.",
            "field_of_study": "Computer Science and Data Structures",
            "institution": "State Tech University",
            "graduation_year": 2024,
        }
    ]
    projects = [
        {
            "name": "DocSearch",
            "description": "Semantic retrieval engine using PyTorch, Docker, and REST APIs.",
            "technologies": ["PyTorch", "Docker", "Tailwind CSS"],
        }
    ]
    certs = ["AWS Certified Cloud Practitioner"]

    roles, gaps, overlaps, stats = build_career_timeline(
        work, education=education, gap_threshold_months=3, today=today
    )
    study_windows, _ = build_study_windows(education, today=today)

    # 1. Study window covers 2020-07 to 2024-06 -> 2023-05..2024-01 gap completely eliminated!
    assert len(study_windows) == 1
    assert study_windows[0].estimated is True
    assert study_windows[0].start_ym == "2020-07"
    assert study_windows[0].end_ym == "2024-06"
    assert gaps == []

    # 2. Internships & trainee stints are NOT counted as short stints or in core average tenure
    assert stats.short_stints_count == 0
    assert stats.core_role_count == 1
    assert stats.internship_count == 2
    assert stats.trainee_count == 1
    assert stats.internship_months == 10  # 3m + 3m + 4m
    assert stats.full_time_years == 2.0  # Jul 2024..Jun 2026 = 24m
    assert stats.average_tenure_months == 24.0

    # 3. Skills evidenced across ALL sections + aliases (Machine Learning <-> ML, PostgreSQL <-> Postgres)
    listed_tech = [
        "Python",
        "FastAPI",
        "Machine Learning",
        "React",
        "PyTorch",
        "Data Structures",
        "REST API",
    ]
    listed_tools = ["PostgreSQL", "Docker", "AWS", "CI/CD", "Tailwind CSS"]
    ev = compute_skill_evidence(
        technical_skills=listed_tech,
        tools=listed_tools,
        profile_summary="Full-stack and ML engineer.",
        work_experience=work,
        projects=projects,
        certifications=certs,
        education=education,
    )
    ev_map = {item.skill: item.sources for item in ev}
    assert "experience" in ev_map["Machine Learning"]  # matched "ML" in bullet
    assert "projects" in ev_map["PyTorch"]
    assert "projects" in ev_map["Docker"]
    assert "certification" in ev_map["AWS"]
    assert "education" in ev_map["Data Structures"]

    checks = run_consistency_checks(
        roles=roles,
        gaps=gaps,
        overlaps=overlaps,
        tenure_stats=stats,
        stated_years=stats.full_time_years,
        llm_stated_years=stats.total_years,
        work_experience=work,
        profile_summary="Full-stack and ML engineer.",
        technical_skills=listed_tech,
        tools=listed_tools,
        projects=projects,
        certifications=certs,
        education=education,
        skill_evidence=ev,
    )
    codes = {c.code for c in checks}
    assert "employment_gap" not in codes
    assert "repeated_short_stints" not in codes
    assert "unverified_listed_skills" not in codes
    assert "experience_mismatch" not in codes


def test_negative_cases_still_flag_genuinely_suspicious_profiles():
    """Real post-graduation gap, repeated short full-time stints, and unevidenced skills MUST still fire."""
    from app.services.consistency import run_consistency_checks
    from app.services.timeline import build_career_timeline

    today = date(2026, 6, 1)
    work = [
        {
            "company": "Co C",
            "job_title": "Backend Engineer",
            "employment_type": "full_time",
            "start_date": "Jan 2026",
            "end_date": "Present",
            "bullets": ["Maintained Python services."],
        },
        # 8-month REAL post-graduation gap (2025-05 to 2025-12) after graduating in 2023!
        {
            "company": "Co B",
            "job_title": "Internal Tools Engineer",
            "employment_type": "full_time",
            "start_date": "Oct 2024",
            "end_date": "Apr 2025",  # 7 months -> short full-time stint #1
            "bullets": ["Built internal dashboards in Python."],
        },
        {
            "company": "Co A",
            "job_title": "Software Engineer",
            "employment_type": "full_time",
            "start_date": "Jan 2024",
            "end_date": "Aug 2024",  # 8 months -> short full-time stint #2
            "bullets": ["Wrote Python scripts."],
        },
    ]
    education = [{"degree": "B.Tech", "institution": "IIT", "start_year": 2019, "end_year": 2023}]

    roles, gaps, overlaps, stats = build_career_timeline(
        work, education=education, gap_threshold_months=3, today=today
    )
    assert len(gaps) == 1
    assert gaps[0].duration_months == 8
    assert stats.short_stints_count == 2

    checks = run_consistency_checks(
        roles=roles,
        gaps=gaps,
        overlaps=overlaps,
        tenure_stats=stats,
        stated_years=stats.total_years,
        llm_stated_years=None,
        work_experience=work,
        profile_summary="Python developer.",
        technical_skills=["Python", "Rust", "Haskell", "Erlang", "Scala", "Go"],
        tools=[],
        projects=[],
        certifications=[],
        education=education,
    )
    codes = {c.code for c in checks}
    assert "employment_gap" in codes
    assert "repeated_short_stints" in codes
    assert "unverified_listed_skills" in codes


def test_timeline_edge_cases_degrees_partial_trim_pursuing_overlapping():
    from app.services.timeline import build_career_timeline, build_study_windows

    today = date(2026, 6, 1)

    # 1. Partial gap trimming: work ends Feb 2024, next starts Jan 2025 (10m raw gap);
    # B.E. ends June 2024 -> trims Mar-Jun 2024, leaving Jul-Dec 2024 = 6m post-grad gap!
    work_partial = [
        {"company": "B", "job_title": "Engineer", "start_date": "Jan 2025", "end_date": "Present"},
        {"company": "A", "job_title": "Intern", "start_date": "Nov 2023", "end_date": "Feb 2024"},
    ]
    edu_be = [{"degree": "B.E.", "start_year": 2020, "end_year": 2024}]
    _, gaps, _, _ = build_career_timeline(work_partial, education=edu_be, gap_threshold_months=3, today=today)
    assert len(gaps) == 1
    assert gaps[0].from_ym == "2024-07"
    assert gaps[0].to_ym == "2024-12"
    assert gaps[0].duration_months == 6

    # 2. Master's (24m) & Diploma (36m) estimated windows
    ms_win, _ = build_study_windows([{"degree": "M.S. Computer Science", "graduation_year": 2024}], today=today)
    assert ms_win[0].start_ym == "2022-07" and ms_win[0].end_ym == "2024-06"

    dip_win, _ = build_study_windows([{"degree": "Diploma in Engineering", "graduation_year": 2023}], today=today)
    assert dip_win[0].start_ym == "2020-07" and dip_win[0].end_ym == "2023-06"

    # 3. Currently studying (open-ended window up to today)
    curr_win, _ = build_study_windows(
        [{"degree": "M.Tech", "start_year": 2024, "end_year": "Pursuing"}], today=today
    )
    assert curr_win[0].is_current is True
    assert curr_win[0].end_ym == "Present"

    # 4. Missing / invalid years do not crash
    bad_win, bad_intervals = build_study_windows(
        [{"degree": "B.A.", "institution": "College", "graduation_year": "invalid"}], today=today
    )
    assert len(bad_win) == 1
    assert bad_win[0].start_ym is None
    assert bad_intervals == []

    # 5. Overlapping education windows merge cleanly
    _, merged_ov = build_study_windows(
        [
            {"degree": "B.E.", "start_year": 2020, "end_year": 2024},
            {"degree": "Diploma in AI", "start_year": 2021, "end_year": 2023},
        ],
        today=today,
    )
    assert len(merged_ov) == 1


@pytest.mark.asyncio
async def test_timeline_and_brief_api_with_cache_invalidation_and_blind_mode(
    client, seeded_users, cleanup_records, monkeypatch
):
    monkeypatch.setattr(settings, "ENABLE_SEMANTIC_SEARCH", False)
    monkeypatch.setattr(settings, "ENABLE_CANDIDATE_BRIEF", False)
    rec_token = await _login(
        client, seeded_users["recruiter"]["email"], seeded_users["recruiter"]["password"]
    )
    viewer_token = await _login(
        client, seeded_users["viewer"]["email"], seeded_users["viewer"]["password"]
    )
    tag = uuid.uuid4().hex[:8]

    cand_res = await client.post(
        "/api/v1/candidates/",
        json={
            "full_name": f"Rohan Kulkarni {tag}",
            "email": f"rohan.{tag}@example.com",
            "profile_summary": "Backend engineer with ML project work.",
            "years_experience": 1.8,
            "primary_domain": "Software Engineering",
            "work_experience": [
                {
                    "company": "CloudCo",
                    "job_title": "Software Engineer",
                    "employment_type": "full_time",
                    "start_date": "Jul 2024",
                    "end_date": "Present",
                    "bullets": ["Built FastAPI services and PostgreSQL schemas."],
                },
                {
                    "company": "LabX",
                    "job_title": "Software Engineering Intern",
                    "employment_type": "internship",
                    "start_date": "Jan 2023",
                    "end_date": "Apr 2023",
                    "bullets": ["Trained ML classifiers in Python."],
                },
            ],
            "education": [
                {
                    "degree": "B.E.",
                    "field_of_study": "Computer Engineering",
                    "institution": f"Secret Institute {tag}",
                    "start_year": 2020,
                    "end_year": 2024,
                    "graduation_year": 2024,
                }
            ],
            "projects": [
                {
                    "name": "QueryBot",
                    "description": "Built RAG assistant with Docker and React.",
                    "technologies": ["Docker", "React"],
                }
            ],
            "technical_skills": ["Python", "FastAPI", "Machine Learning", "React"],
            "tools": ["PostgreSQL", "Docker"],
            "allow_duplicate": True,
        },
        headers=_auth(rec_token),
    )
    assert cand_res.status_code == 201, cand_res.text
    cid = cand_res.json()["id"]
    cleanup_records["candidates"].append(uuid.UUID(cid))

    # 1. /timeline returns study_windows, skill_evidence, zero false flags, and masks institution in blind mode
    tl = await client.get(f"/api/v1/candidates/{cid}/timeline", headers=_auth(viewer_token))
    assert tl.status_code == 200, tl.text
    tl_data = tl.json()
    assert len(tl_data["study_windows"]) == 1
    assert tl_data["study_windows"][0]["institution"] == f"Secret Institute {tag}"
    assert tl_data["gaps"] == []
    assert tl_data["tenure_stats"]["short_stints_count"] == 0
    assert tl_data["tenure_stats"]["internship_months"] == 4
    ev_map = {e["skill"]: e["sources"] for e in tl_data["skill_evidence"]}
    assert "projects" in ev_map["Docker"]
    assert "experience" in ev_map["Machine Learning"]

    tl_blind = await client.get(
        f"/api/v1/candidates/{cid}/timeline?blind=true", headers=_auth(viewer_token)
    )
    assert tl_blind.status_code == 200
    assert tl_blind.json()["study_windows"][0]["institution"] == "[Institution Redacted]"

    # 2. /brief shows "full-time (+ 4 months internships)" and caches by source_hash
    brief1 = await client.get(f"/api/v1/candidates/{cid}/brief", headers=_auth(viewer_token))
    assert brief1.status_code == 200, brief1.text
    b1 = brief1.json()
    assert "full-time (+ 4 months internships)" in b1["summary"]
    assert b1["verify_items"] == []
    hash1 = b1["source_hash"]

    # Updating projects invalidates source_hash and regenerates brief automatically
    upd = await client.put(
        f"/api/v1/candidates/{cid}",
        json={
            "projects": [
                {
                    "name": "QueryBot v2",
                    "description": "Upgraded RAG assistant with Docker, React, and Redis.",
                    "technologies": ["Docker", "React", "Redis"],
                }
            ]
        },
        headers=_auth(rec_token),
    )
    assert upd.status_code == 200

    brief2 = await client.get(f"/api/v1/candidates/{cid}/brief", headers=_auth(viewer_token))
    assert brief2.status_code == 200
    assert brief2.json()["source_hash"] != hash1
    assert brief2.json()["cached"] is False


# ---------------------------------------------------------------------------
# Quick Wins tests: PDF exports (projects + employment_type), opt-in stage auto-email, single-candidate re-parse
# ---------------------------------------------------------------------------


def test_pdf_exports_render_projects_and_employment_types_with_blind_and_viewer_safety():
    from datetime import datetime, timezone
    from app.models.user import UserRole
    from app.schemas.candidate import CandidateResponse
    from app.services.exports import build_candidate_pdf

    now = datetime.now(timezone.utc)
    cand = CandidateResponse(
        id=uuid.uuid4(),
        full_name="Meera Joshi",
        email="meera@example.com",
        phone="+91-9876543210",
        city="Pune",
        profile_summary="Full-stack engineer with internship and project portfolio.",
        years_experience=1.5,
        primary_domain="Software Engineering",
        work_experience=[
            {
                "company": "AlphaTech",
                "job_title": "Software Engineer",
                "employment_type": "full_time",
                "start_date": "Jul 2024",
                "end_date": "Present",
                "bullets": ["Built FastAPI APIs."],
            },
            {
                "company": "BetaLab",
                "job_title": "ML Intern",
                "employment_type": "internship",
                "start_date": "Jan 2024",
                "end_date": "Apr 2024",
                "bullets": ["Trained NLP models."],
            },
        ],
        education=[
            {
                "degree": "B.E.",
                "field_of_study": "Computer Engineering",
                "institution": "Secret College Name",
                "start_year": 2020,
                "end_year": 2024,
                "graduation_year": 2024,
            }
        ],
        projects=[
            {
                "name": "DocSearch Engine",
                "description": "Semantic PDF indexer with pgvector and Docker.",
                "technologies": ["Python", "Docker", "PostgreSQL"],
            }
        ],
        technical_skills=["Python", "FastAPI"],
        tools=["Docker", "PostgreSQL"],
        soft_skills=[],
        hobbies_interests=[],
        languages=["English"],
        certifications=[],
        current_ctc=1200000,
        expected_ctc=1600000,
        ctc_currency="INR",
        raw_parsed_data={},
        is_duplicate_flagged=False,
        created_at=now,
        updated_at=now,
    )

    pdf_normal = build_candidate_pdf(cand, role=UserRole.recruiter, blind=False)
    assert pdf_normal.startswith(b"%PDF-") and len(pdf_normal) > 1000

    pdf_blind_viewer = build_candidate_pdf(cand, role=UserRole.viewer, blind=True)
    assert pdf_blind_viewer.startswith(b"%PDF-") and len(pdf_blind_viewer) > 1000


@pytest.mark.asyncio
async def test_opt_in_stage_auto_email_and_single_candidate_reparse(
    client, seeded_users, cleanup_records, db_session_factory, monkeypatch
):
    from app.models.candidate import ResumeFile, ResumeFileStatus
    from app.services.email_sender import ConsoleEmailSender
    from app.services.file_storage import storage

    monkeypatch.setattr(settings, "ENABLE_SEMANTIC_SEARCH", False)
    admin_token = await _login(client, seeded_users["admin"]["email"], seeded_users["admin"]["password"])
    rec_token = await _login(
        client, seeded_users["recruiter"]["email"], seeded_users["recruiter"]["password"]
    )
    viewer_token = await _login(
        client, seeded_users["viewer"]["email"], seeded_users["viewer"]["password"]
    )
    tag = uuid.uuid4().hex[:8]

    sent_emails: list[dict] = []

    class CaptureSender(ConsoleEmailSender):
        async def send_email(self, *, to_email: str, subject: str, body: str) -> None:
            sent_emails.append({"to": to_email, "subject": subject, "body": body})

    monkeypatch.setattr("app.crud.workflow.default_email_sender", CaptureSender())

    # Save a dummy resume file for re-parse testing
    file_meta = await storage.save_file(
        file_bytes=b"Dummy CV content",
        original_filename=f"reparse-{tag}.pdf",
        content_type="application/pdf",
    )
    async with db_session_factory() as db:
        rf = ResumeFile(
            original_filename=file_meta["original_filename"],
            stored_filename=file_meta["stored_filename"],
            file_path=file_meta["file_path"],
            file_size=file_meta["file_size"],
            content_type=file_meta["content_type"],
            status=ResumeFileStatus.pending.value,
        )
        db.add(rf)
        await db.commit()
        await db.refresh(rf)
        rf_id = rf.id

    cand_res = await client.post(
        "/api/v1/candidates/",
        json={
            "resume_file_id": str(rf_id),
            "full_name": f"Nikhil Patil {tag}",
            "email": f"nikhil.{tag}@example.com",
            "profile_summary": "Backend engineer.",
            "years_experience": 2.0,
            "primary_domain": "Software Engineering",
            "technical_skills": ["Python"],
            "allow_duplicate": True,
        },
        headers=_auth(rec_token),
    )
    assert cand_res.status_code == 201, cand_res.text
    cid = cand_res.json()["id"]
    cleanup_records["candidates"].append(uuid.UUID(cid))

    # 1. Single-candidate re-parse preview: viewer gets 403; recruiter gets preview without DB mutation
    viewer_reparse = await client.post(f"/api/v1/candidates/{cid}/reparse", headers=_auth(viewer_token))
    assert viewer_reparse.status_code == 403

    async def _fake_pipeline(db, **kwargs):
        from app.schemas.candidate import DuplicateInfo

        return (
            {
                "full_name": f"Nikhil Patil {tag}",
                "profile_summary": "Updated summary from re-parse.",
                "years_experience": 2.0,
                "primary_domain": "Software Engineering",
                "projects": [{"name": "Reparsed App", "description": "Built APIs.", "technologies": ["FastAPI"]}],
                "raw_parsed_data": {"_resume_text": "SECRET RAW TEXT"},
            },
            DuplicateInfo(is_duplicate=False, matches=[]),
            False,
        )

    monkeypatch.setattr("app.api.v1.endpoints.candidates.parse_resume_pipeline", _fake_pipeline)
    reparse_res = await client.post(f"/api/v1/candidates/{cid}/reparse", headers=_auth(rec_token))
    assert reparse_res.status_code == 200, reparse_res.text
    rp = reparse_res.json()
    assert rp["parsed_data"]["projects"][0]["name"] == "Reparsed App"
    assert "_resume_text" not in str(rp)
    # Confirm DB was NOT mutated by preview
    unchanged = await client.get(f"/api/v1/candidates/{cid}", headers=_auth(rec_token))
    assert unchanged.json()["projects"] == []

    # 2. Opt-in stage auto-email: OFF by default; fires ONLY when admin enables auto_send=True on non-rejected stage
    job_res = await client.post(
        "/api/v1/jobs/",
        json={
            "title": f"Platform Eng {tag}",
            "department": "Eng",
            "location": "Remote",
            "description": "Python",
            "required_skills": ["Python"],
            "status": "open",
        },
        headers=_auth(rec_token),
    )
    jid = job_res.json()["id"]
    cleanup_records["jobs"].append(uuid.UUID(jid))

    app_res = await client.post(
        "/api/v1/applications/",
        json={"candidate_id": cid, "job_id": jid, "stage": "applied"},
        headers=_auth(rec_token),
    )
    app_id = app_res.json()["id"]

    # Create an admin opt-in auto_send template for `screened` stage
    tpl_res = await client.post(
        "/api/v1/email-templates/",
        json={
            "key": f"screened_welcome_{tag}",
            "subject": "Screening update for {{job_title}}",
            "body": "Hi {{candidate_name}}, you moved to screened.",
            "stage_trigger": "screened",
            "auto_send": True,
        },
        headers=_auth(admin_token),
    )
    assert tpl_res.status_code == 201, tpl_res.text
    tpl_id = tpl_res.json()["id"]
    try:
        mv_screened = await client.patch(
            f"/api/v1/applications/{app_id}/stage",
            json={"stage": "screened"},
            headers=_auth(rec_token),
        )
        assert mv_screened.status_code == 200
        assert len(sent_emails) == 1
        assert f"Platform Eng {tag}" in sent_emails[0]["subject"]

        # Moving to rejected NEVER auto-sends any email
        mv_rej = await client.patch(
            f"/api/v1/applications/{app_id}/stage",
            json={"stage": "rejected"},
            headers=_auth(rec_token),
        )
        assert mv_rej.status_code == 200
        assert len(sent_emails) == 1  # unchanged!
    finally:
        await client.delete(f"/api/v1/email-templates/{tpl_id}", headers=_auth(admin_token))
