"""Async HTTP integration tests for Phase 2: skill normalization, hybrid search, JD matching, and compare."""

import uuid

import pytest

from app.core.config import settings


async def _login(client, email: str, password: str) -> str:
    res = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert res.status_code == 200, res.text
    return res.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _candidate_payload(tag: str, suffix: str, **overrides) -> dict:
    base = {
        "full_name": f"Phase2 Candidate {suffix} {tag}",
        "email": f"p2.{suffix}.{tag}@example.com",
        "phone": f"+91 98110{uuid.uuid4().int % 100000:05d}",
        "city": "Bengaluru",
        "profile_summary": f"Experienced engineer specializing in distributed microservices ({tag}).",
        "years_experience": 5.0,
        "primary_domain": "Software Engineering",
        "work_experience": [
            {
                "company": "Acme Cloud",
                "job_title": "Senior Backend Engineer",
                "start_date": "2021-01",
                "end_date": "Present",
                "bullets": ["Designed PostgreSQL schemas and Kubernetes pipelines."],
            }
        ],
        "education": [
            {"degree": "B.Tech CS", "institution": "IIT Bombay", "graduation_year": 2019}
        ],
        "technical_skills": ["Python", "JS", "ReactJS"],
        "tools": ["Postgres", "k8s"],
        "soft_skills": ["Leadership"],
        "hobbies_interests": [],
        "languages": ["English"],
        "certifications": [],
        "notice_period_days": 30,
        "current_ctc": 2400000,
        "expected_ctc": 3000000,
        "ctc_currency": "INR",
        "preferred_locations": ["Bengaluru"],
        "open_to_relocate": True,
        "raw_parsed_data": {
            "source": "phase2-test",
            "_resume_text": "Confidential salary 24 LPA expected 30 LPA",
        },
        "allow_duplicate": True,
    }
    base.update(overrides)
    return base


@pytest.mark.asyncio
async def test_skill_normalization_on_save_and_case_insensitive_tech_tools_filter(
    client, seeded_users, cleanup_records
):
    admin_token = await _login(client, seeded_users["admin"]["email"], seeded_users["admin"]["password"])
    rec_token = await _login(
        client, seeded_users["recruiter"]["email"], seeded_users["recruiter"]["password"]
    )
    tag = uuid.uuid4().hex[:8]

    # 1. Admin creates a custom skill alias; recruiter gets 403
    custom_canonical = f"SuperLang-{tag}"
    custom_alias = f"slang-{tag}"
    forbid = await client.post(
        "/api/v1/skills/normalizations",
        json={"canonical_name": custom_canonical, "aliases": [custom_alias]},
        headers=_auth(rec_token),
    )
    assert forbid.status_code == 403

    norm_res = await client.post(
        "/api/v1/skills/normalizations",
        json={"canonical_name": custom_canonical, "aliases": [custom_alias]},
        headers=_auth(admin_token),
    )
    assert norm_res.status_code == 201, norm_res.text
    cleanup_records["skill_normalizations"].append(uuid.UUID(norm_res.json()["id"]))

    # 2. Save candidate with unnormalized aliases across BOTH technical_skills and tools
    create_res = await client.post(
        "/api/v1/candidates/",
        json=_candidate_payload(
            tag,
            "norm",
            technical_skills=["js", "ReactJS", custom_alias.upper()],
            tools=["postgres", "K8S"],
        ),
        headers=_auth(rec_token),
    )
    assert create_res.status_code == 201, create_res.text
    cand = create_res.json()
    cleanup_records["candidates"].append(uuid.UUID(cand["id"]))

    # Stored canonically
    assert set(cand["technical_skills"]) == {"JavaScript", "React", custom_canonical}
    assert set(cand["tools"]) == {"PostgreSQL", "Kubernetes"}

    # 3. Case-insensitive skills filter spanning BOTH technical_skills AND tools using aliases
    list_res = await client.get(
        "/api/v1/candidates/",
        params={"skills": f"JS,k8s,{custom_alias}"},
        headers=_auth(rec_token),
    )
    assert list_res.status_code == 200, list_res.text
    ids = [item["id"] for item in list_res.json()["items"]]
    assert cand["id"] in ids


@pytest.mark.asyncio
async def test_hybrid_search_fts_trgm_semantic_and_feature_flag(
    client, seeded_users, cleanup_records, monkeypatch
):
    rec_token = await _login(
        client, seeded_users["recruiter"]["email"], seeded_users["recruiter"]["password"]
    )
    tag = uuid.uuid4().hex[:8]

    # Deterministic 768-dim orthogonal embeddings
    vec_ml = [1.0] + [0.0] * (settings.EMBEDDING_DIMENSIONS - 1)
    vec_sales = [0.0, 1.0] + [0.0] * (settings.EMBEDDING_DIMENSIONS - 2)

    async def fake_embed(text_val: str):
        low = (text_val or "").lower()
        if "neural" in low or "quantum" in low or "pytorch" in low:
            return vec_ml
        return vec_sales

    monkeypatch.setattr(settings, "ENABLE_SEMANTIC_SEARCH", True)
    monkeypatch.setattr("app.crud.candidate.generate_embedding", fake_embed)

    ml_res = await client.post(
        "/api/v1/candidates/",
        json=_candidate_payload(
            tag,
            "ml",
            full_name=f"Ananya Deshmukh {tag}",
            primary_domain="AI/ML Engineering",
            profile_summary=f"Research scientist specializing in neural transformers and PyTorch ({tag}).",
            technical_skills=["Python", "PyTorch"],
            tools=["Docker"],
        ),
        headers=_auth(rec_token),
    )
    assert ml_res.status_code == 201, ml_res.text
    ml_id = ml_res.json()["id"]
    cleanup_records["candidates"].append(uuid.UUID(ml_id))

    sales_res = await client.post(
        "/api/v1/candidates/",
        json=_candidate_payload(
            tag,
            "sales",
            full_name=f"Vikram Joshi {tag}",
            primary_domain="Enterprise Sales",
            profile_summary=f"Enterprise SaaS account executive closing ARR deals ({tag}).",
            technical_skills=["CRM"],
            tools=["Salesforce"],
        ),
        headers=_auth(rec_token),
    )
    assert sales_res.status_code == 201, sales_res.text
    sales_id = sales_res.json()["id"]
    cleanup_records["candidates"].append(uuid.UUID(sales_id))

    # 1. Semantic + FTS query ("quantum" doesn't appear lexically in ML candidate, only shares vector!)
    sem_res = await client.get(
        "/api/v1/candidates/search",
        params={"q": "quantum"},
        headers=_auth(rec_token),
    )
    assert sem_res.status_code == 200, sem_res.text
    sem_body = sem_res.json()
    assert sem_body["semantic_enabled"] is True
    assert sem_body["semantic_used"] is True
    found_ids = [i["id"] for i in sem_body["items"]]
    assert ml_id in found_ids
    ml_item = next(i for i in sem_body["items"] if i["id"] == ml_id)
    assert ml_item["semantic_score"] > 0.9

    # 2. Fuzzy pg_trgm typo on name ("Ananyaa Deshmuk") + FTS with semantic disabled
    monkeypatch.setattr(settings, "ENABLE_SEMANTIC_SEARCH", False)
    fuzzy_res = await client.get(
        "/api/v1/candidates/search",
        params={"q": f"Ananyaa Deshmuk {tag}"},
        headers=_auth(rec_token),
    )
    assert fuzzy_res.status_code == 200, fuzzy_res.text
    fuzzy_body = fuzzy_res.json()
    assert fuzzy_body["semantic_enabled"] is False
    assert fuzzy_body["semantic_used"] is False
    assert any(i["id"] == ml_id for i in fuzzy_body["items"])


@pytest.mark.asyncio
async def test_jd_match_scoring_cache_and_compare_with_viewer_redaction(
    client, seeded_users, cleanup_records, monkeypatch
):
    rec_token = await _login(
        client, seeded_users["recruiter"]["email"], seeded_users["recruiter"]["password"]
    )
    viewer_token = await _login(
        client, seeded_users["viewer"]["email"], seeded_users["viewer"]["password"]
    )
    tag = uuid.uuid4().hex[:8]

    # Disable external embedding/LLM calls so test is 100% deterministic & fast
    monkeypatch.setattr(settings, "ENABLE_SEMANTIC_SEARCH", False)

    # Strong candidate
    strong_res = await client.post(
        "/api/v1/candidates/",
        json=_candidate_payload(
            tag,
            "strong",
            full_name=f"Strong Match {tag}",
            years_experience=5.0,
            technical_skills=["Python", "FastAPI", "JS"],
            tools=["Postgres", "k8s", "Docker"],
            profile_summary=f"Backend architect building Python FastAPI microservices on PostgreSQL ({tag}). Salary 28 LPA.",
        ),
        headers=_auth(rec_token),
    )
    assert strong_res.status_code == 201, strong_res.text
    strong_id = strong_res.json()["id"]
    cleanup_records["candidates"].append(uuid.UUID(strong_id))

    # Weak candidate
    weak_res = await client.post(
        "/api/v1/candidates/",
        json=_candidate_payload(
            tag,
            "weak",
            full_name=f"Weak Match {tag}",
            years_experience=1.0,
            primary_domain="Design",
            technical_skills=["Figma", "JavaScript"],
            tools=["Sketch"],
            profile_summary=f"UI designer focusing on visual branding ({tag}). Current CTC 8 LPA.",
        ),
        headers=_auth(rec_token),
    )
    assert weak_res.status_code == 201, weak_res.text
    weak_id = weak_res.json()["id"]
    cleanup_records["candidates"].append(uuid.UUID(weak_id))

    # Create job
    job_res = await client.post(
        "/api/v1/jobs/",
        json={
            "title": f"Senior Python Backend Engineer {tag}",
            "department": "Engineering",
            "location": "Remote",
            "description": "Build scalable Python FastAPI services backed by PostgreSQL and Kubernetes.",
            "required_skills": ["python", "FastAPI", "postgresql"],
            "nice_to_have_skills": ["Kubernetes", "Docker"],
            "min_years": 4.0,
            "max_years": 7.0,
            "status": "open",
        },
        headers=_auth(rec_token),
    )
    assert job_res.status_code == 201, job_res.text
    job_id = job_res.json()["id"]
    cleanup_records["jobs"].append(uuid.UUID(job_id))

    # Viewer cannot trigger POST /match
    viewer_match_post = await client.post(
        f"/api/v1/jobs/{job_id}/match",
        json={"candidate_ids": [strong_id, weak_id], "include_explanations": False},
        headers=_auth(viewer_token),
    )
    assert viewer_match_post.status_code == 403

    # Recruiter runs match scoring
    match_res = await client.post(
        f"/api/v1/jobs/{job_id}/match",
        json={"candidate_ids": [strong_id, weak_id], "include_explanations": False},
        headers=_auth(rec_token),
    )
    assert match_res.status_code == 200, match_res.text
    ranked = match_res.json()
    assert len(ranked) == 2
    assert ranked[0]["candidate_id"] == strong_id
    assert ranked[1]["candidate_id"] == weak_id
    assert ranked[0]["score"] > ranked[1]["score"]
    assert ranked[0]["breakdown"]["must_have_score"] == 100.0
    assert ranked[0]["breakdown"]["experience_score"] == 100.0
    assert ranked[0]["model_version"] == "deterministic"

    # Viewer CAN read cached GET /matches
    cached_res = await client.get(f"/api/v1/jobs/{job_id}/matches", headers=_auth(viewer_token))
    assert cached_res.status_code == 200, cached_res.text
    cached_ids = [m["candidate_id"] for m in cached_res.json()]
    assert cached_ids[:2] == [strong_id, weak_id]

    # Compare endpoint validation (<2 rejected)
    bad_cmp = await client.get(
        "/api/v1/candidates/compare",
        params={"ids": strong_id},
        headers=_auth(rec_token),
    )
    assert bad_cmp.status_code == 400

    # Compare as recruiter: sees CTC and job_matches and shared JavaScript skill
    rec_cmp = await client.get(
        "/api/v1/candidates/compare",
        params={"ids": f"{strong_id},{weak_id}", "job_id": job_id},
        headers=_auth(rec_token),
    )
    assert rec_cmp.status_code == 200, rec_cmp.text
    rec_body = rec_cmp.json()
    assert len(rec_body["candidates"]) == 2
    assert "JavaScript" in rec_body["shared_skills"]
    assert strong_id in rec_body["job_matches"]
    assert rec_body["candidates"][0]["current_ctc"] == 2400000

    # Compare as viewer: CTC & free-text salary & _resume_text MUST be absent/redacted
    viewer_cmp = await client.get(
        "/api/v1/candidates/compare",
        params={"ids": f"{strong_id},{weak_id}", "job_id": job_id},
        headers=_auth(viewer_token),
    )
    assert viewer_cmp.status_code == 200, viewer_cmp.text
    viewer_body = viewer_cmp.json()
    raw_text = viewer_cmp.text
    assert "_resume_text" not in raw_text
    assert "2400000" not in raw_text
    assert "3000000" not in raw_text
    assert "28 LPA" not in raw_text
    assert "8 LPA" not in raw_text
    for c in viewer_body["candidates"]:
        assert c["current_ctc"] is None
        assert c["expected_ctc"] is None
        assert c["ctc_currency"] is None
