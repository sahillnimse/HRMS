"""Phase 6 tests: Hiring Analytics (funnel, time-in-stage, time-to-hire, sources, stuck, filters, blind mode, viewer read-only)."""

from datetime import datetime, timedelta, timezone
import uuid

import pytest
from sqlalchemy import select, update

from app.core.config import settings
from app.models.pipeline import Application, ApplicationEvent


async def _login(client, email: str, password: str) -> str:
    res = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert res.status_code == 200, res.text
    return res.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_phase6_analytics_end_to_end(
    client, seeded_users, cleanup_records, db_session_factory, monkeypatch
):
    monkeypatch.setattr(settings, "ENABLE_SEMANTIC_SEARCH", False)
    rec_token = await _login(
        client, seeded_users["recruiter"]["email"], seeded_users["recruiter"]["password"]
    )
    viewer_token = await _login(
        client, seeded_users["viewer"]["email"], seeded_users["viewer"]["password"]
    )
    tag = uuid.uuid4().hex[:8]

    # Create a dedicated job so analytics filtered by job_id are 100% isolated from other rows
    job_res = await client.post(
        "/api/v1/jobs/",
        json={
            "title": f"Analytics Test Role {tag}",
            "department": "Engineering",
            "location": "Remote",
            "description": "Test role for Phase 6 analytics",
            "required_skills": ["Python"],
            "status": "open",
        },
        headers=_auth(rec_token),
    )
    assert job_res.status_code == 201, job_res.text
    job_id = job_res.json()["id"]
    cleanup_records["jobs"].append(uuid.UUID(job_id))

    # Create 3 candidates with different sources
    candidates_spec = [
        (f"Aarav Hired {tag}", f"referral_{tag}"),
        (f"Diya Stuck {tag}", f"linkedin_{tag}"),
        (f"Kabir Rejected {tag}", f"referral_{tag}"),
    ]
    cids = []
    for full_name, src in candidates_spec:
        c_res = await client.post(
            "/api/v1/candidates/",
            json={
                "full_name": full_name,
                "email": f"{full_name.lower().replace(' ', '.')}@example.com",
                "profile_summary": "Software engineer.",
                "years_experience": 4.0,
                "primary_domain": "Software Engineering",
                "technical_skills": ["Python"],
                "source": src,
                "allow_duplicate": True,
            },
            headers=_auth(rec_token),
        )
        assert c_res.status_code == 201, c_res.text
        cid = c_res.json()["id"]
        cids.append(cid)
        cleanup_records["candidates"].append(uuid.UUID(cid))

    # Create 3 applications
    app_ids = []
    for cid in cids:
        a_res = await client.post(
            "/api/v1/applications/",
            json={"candidate_id": cid, "job_id": job_id},
            headers=_auth(rec_token),
        )
        assert a_res.status_code == 201, a_res.text
        app_ids.append(a_res.json()["id"])

    app_hired, app_stuck, app_rejected = app_ids

    # Candidate 1: applied -> screened -> interview -> offer -> hired
    for st in ("screened", "interview", "offer", "hired"):
        r = await client.patch(
            f"/api/v1/applications/{app_hired}/stage",
            json={"stage": st},
            headers=_auth(rec_token),
        )
        assert r.status_code == 200, r.text

    # Candidate 2: applied -> screened -> interview (remains stuck in interview for 15 days)
    for st in ("screened", "interview"):
        r = await client.patch(
            f"/api/v1/applications/{app_stuck}/stage",
            json={"stage": st},
            headers=_auth(rec_token),
        )
        assert r.status_code == 200, r.text

    # Candidate 3: applied -> rejected
    r = await client.patch(
        f"/api/v1/applications/{app_rejected}/stage",
        json={"stage": "rejected", "reason": "Role mismatch"},
        headers=_auth(rec_token),
    )
    assert r.status_code == 200, r.text

    # Backdate ApplicationEvent and Application timestamps deterministically for exact math
    now = datetime.now(timezone.utc)
    async with db_session_factory() as db:
        # App 1 (hired): applied t-20d -> screened t-18d (2d) -> interview t-14d (4d) -> offer t-8d (6d) -> hired t-5d (3d)
        # Total time-to-hire = 15.0 days
        hired_offsets = {"applied": 20, "screened": 18, "interview": 14, "offer": 8, "hired": 5}
        evs1 = (
            await db.execute(
                select(ApplicationEvent).where(ApplicationEvent.application_id == uuid.UUID(app_hired))
            )
        ).scalars().all()
        for ev in evs1:
            if ev.to_stage in hired_offsets:
                ev.created_at = now - timedelta(days=hired_offsets[ev.to_stage])
        await db.execute(
            update(Application)
            .where(Application.id == uuid.UUID(app_hired))
            .values(created_at=now - timedelta(days=20), stage_changed_at=now - timedelta(days=5))
        )

        # App 2 (stuck in interview): applied t-21d -> screened t-19d (2d) -> interview t-15d (4d)
        stuck_offsets = {"applied": 21, "screened": 19, "interview": 15}
        evs2 = (
            await db.execute(
                select(ApplicationEvent).where(ApplicationEvent.application_id == uuid.UUID(app_stuck))
            )
        ).scalars().all()
        for ev in evs2:
            if ev.to_stage in stuck_offsets:
                ev.created_at = now - timedelta(days=stuck_offsets[ev.to_stage])
        await db.execute(
            update(Application)
            .where(Application.id == uuid.UUID(app_stuck))
            .values(created_at=now - timedelta(days=21), stage_changed_at=now - timedelta(days=15))
        )

        # App 3 (rejected): applied t-10d -> rejected t-6d (4d in applied)
        rej_offsets = {"applied": 10, "rejected": 6}
        evs3 = (
            await db.execute(
                select(ApplicationEvent).where(ApplicationEvent.application_id == uuid.UUID(app_rejected))
            )
        ).scalars().all()
        for ev in evs3:
            if ev.to_stage in rej_offsets:
                ev.created_at = now - timedelta(days=rej_offsets[ev.to_stage])
        await db.execute(
            update(Application)
            .where(Application.id == uuid.UUID(app_rejected))
            .values(created_at=now - timedelta(days=10), stage_changed_at=now - timedelta(days=6))
        )
        await db.commit()

    # 1. Funnel (tested as viewer to verify read-only access)
    funnel_res = await client.get(
        f"/api/v1/analytics/funnel?job_id={job_id}", headers=_auth(viewer_token)
    )
    assert funnel_res.status_code == 200, funnel_res.text
    funnel = funnel_res.json()
    assert funnel["total_applications"] == 3
    assert funnel["active_applications"] == 1
    assert funnel["hired_count"] == 1
    assert funnel["rejected_count"] == 1
    assert funnel["overall_hire_rate_pct"] == 33.3
    stages_map = {s["stage"]: s for s in funnel["stages"]}
    assert stages_map["applied"]["reached_count"] == 3
    assert stages_map["screened"]["reached_count"] == 2
    assert stages_map["interview"]["reached_count"] == 2
    assert stages_map["interview"]["current_count"] == 1
    assert stages_map["offer"]["reached_count"] == 1
    assert stages_map["hired"]["reached_count"] == 1

    # 2. Time in Stage
    tis_res = await client.get(
        f"/api/v1/analytics/time-in-stage?job_id={job_id}", headers=_auth(viewer_token)
    )
    assert tis_res.status_code == 200, tis_res.text
    tis_map = {s["stage"]: s for s in tis_res.json()["stages"]}
    # applied samples: [2.0, 2.0, 4.0] -> median 2.0, avg 2.7
    assert tis_map["applied"]["sample_count"] == 3
    assert tis_map["applied"]["median_days"] == 2.0
    assert tis_map["applied"]["avg_days"] == 2.7
    # screened samples: [4.0, 4.0] -> median 4.0, avg 4.0
    assert tis_map["screened"]["sample_count"] == 2
    assert tis_map["screened"]["median_days"] == 4.0
    # interview completed sample: [6.0]
    assert tis_map["interview"]["sample_count"] == 1
    assert tis_map["interview"]["avg_days"] == 6.0
    # offer completed sample: [3.0]
    assert tis_map["offer"]["sample_count"] == 1
    assert tis_map["offer"]["avg_days"] == 3.0

    # 3. Time to Hire
    tth_res = await client.get(
        f"/api/v1/analytics/time-to-hire?job_id={job_id}", headers=_auth(viewer_token)
    )
    assert tth_res.status_code == 200, tth_res.text
    tth = tth_res.json()
    assert tth["hired_count"] == 1
    assert tth["avg_days"] == 15.0
    assert tth["median_days"] == 15.0

    # 4. Sources (uses Candidate.source from migration 0006)
    src_res = await client.get(
        f"/api/v1/analytics/sources?job_id={job_id}", headers=_auth(viewer_token)
    )
    assert src_res.status_code == 200, src_res.text
    src_map = {s["source"]: s for s in src_res.json()["sources"]}
    assert src_map[f"referral_{tag}"]["candidates_count"] == 2
    assert src_map[f"referral_{tag}"]["applications_count"] == 2
    assert src_map[f"referral_{tag}"]["hired_count"] == 1
    assert src_map[f"referral_{tag}"]["hire_rate_pct"] == 50.0
    assert src_map[f"linkedin_{tag}"]["interview_count"] == 1
    assert src_map[f"linkedin_{tag}"]["hired_count"] == 0

    # 5. Stuck applications (default interview threshold=10d -> catches App 2 at 15d)
    stuck_res = await client.get(
        f"/api/v1/analytics/stuck?job_id={job_id}", headers=_auth(viewer_token)
    )
    assert stuck_res.status_code == 200, stuck_res.text
    stuck = stuck_res.json()
    assert stuck["total_stuck"] == 1
    assert stuck["items"][0]["application_id"] == app_stuck
    assert stuck["items"][0]["stage"] == "interview"
    assert stuck["items"][0]["days_in_stage"] >= 14.9
    assert f"Diya Stuck {tag}" in stuck["items"][0]["candidate_name"]

    # Blind mode masks candidate name in stuck table
    stuck_blind_res = await client.get(
        f"/api/v1/analytics/stuck?job_id={job_id}&blind=true", headers=_auth(viewer_token)
    )
    assert stuck_blind_res.status_code == 200
    assert stuck_blind_res.json()["items"][0]["candidate_name"].startswith("Candidate #")
    assert "Diya" not in stuck_blind_res.json()["items"][0]["candidate_name"]

    # Higher per-stage override (interview_days=30) excludes App 2 (15d < 30d)
    stuck_high = await client.get(
        f"/api/v1/analytics/stuck?job_id={job_id}&interview_days=30",
        headers=_auth(viewer_token),
    )
    assert stuck_high.status_code == 200
    assert stuck_high.json()["total_stuck"] == 0
    assert stuck_high.json()["thresholds"]["interview"] == 30

    # Date-range filter: only last 12 days should include only App 3 (t-10d), excluding App 1 (t-20d) & App 2 (t-21d)
    start_12 = (now - timedelta(days=12)).date().isoformat()
    funnel_recent = await client.get(
        f"/api/v1/analytics/funnel?job_id={job_id}&start_date={start_12}",
        headers=_auth(rec_token),
    )
    assert funnel_recent.status_code == 200
    assert funnel_recent.json()["total_applications"] == 1
    assert funnel_recent.json()["rejected_count"] == 1
    assert funnel_recent.json()["hired_count"] == 0


@pytest.mark.asyncio
async def test_phase6_analytics_requires_auth(client):
    for path in (
        "/api/v1/analytics/funnel",
        "/api/v1/analytics/time-in-stage",
        "/api/v1/analytics/time-to-hire",
        "/api/v1/analytics/sources",
        "/api/v1/analytics/stuck",
    ):
        res = await client.get(path)
        assert res.status_code == 401
