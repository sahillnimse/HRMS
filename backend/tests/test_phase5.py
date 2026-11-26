"""Phase 5 tests: Interviews, ICS invites, Scorecards (visibility rules), Email templates/send, Offers, and Cascade/Retention cleanup."""

from datetime import date, datetime, timedelta, timezone
import uuid

import pytest
from sqlalchemy import select

from app.core.config import settings
from app.crud.user import create_user
from app.models.user import UserRole
from app.models.workflow import (
    EmailLog,
    EmailTemplate,
    Interview,
    InterviewParticipant,
    Offer,
    Scorecard,
    ScorecardTemplate,
)
from app.services.calendar import IcsCalendarProvider
from app.services.email_sender import ConsoleEmailSender, render_email_template


async def _login(client, email: str, password: str) -> str:
    res = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert res.status_code == 200, res.text
    return res.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_ics_calendar_provider_and_email_template_renderer():
    provider = IcsCalendarProvider()
    ics = provider.build_invite(
        uid="test-123",
        summary="Interview: Tech Round",
        description="System design discussion",
        start_utc=datetime(2026, 12, 1, 10, 0, tzinfo=timezone.utc),
        duration_minutes=60,
        location="https://meet.example.com/abc",
        attendee_emails=["alice@example.com"],
    ).decode("utf-8")
    assert "BEGIN:VCALENDAR" in ics
    assert "DTSTART:20261201T100000Z" in ics
    assert "DTEND:20261201T110000Z" in ics
    assert "ATTENDEE;RSVP=TRUE:mailto:alice@example.com" in ics

    rendered = render_email_template(
        "Hi {{candidate_name}}, welcome to {{job_title}}!",
        {"candidate_name": "Neha", "job_title": "Staff Engineer"},
    )
    assert rendered == "Hi Neha, welcome to Staff Engineer!"


@pytest.mark.asyncio
async def test_interviews_ics_and_scorecard_visibility_rules(
    client, seeded_users, cleanup_records, db_session_factory, monkeypatch
):
    admin_token = await _login(client, seeded_users["admin"]["email"], seeded_users["admin"]["password"])
    rec_token = await _login(
        client, seeded_users["recruiter"]["email"], seeded_users["recruiter"]["password"]
    )
    viewer_token = await _login(
        client, seeded_users["viewer"]["email"], seeded_users["viewer"]["password"]
    )
    tag = uuid.uuid4().hex[:8]
    monkeypatch.setattr(settings, "ENABLE_SEMANTIC_SEARCH", False)

    # Create a second recruiter interviewer so we can test blind peer scorecard lock
    async with db_session_factory() as db:
        rec2 = await create_user(
            db,
            email=f"rec2-{tag}@example.com",
            password="RecruiterPass123!",
            full_name="Second Interviewer",
            role=UserRole.recruiter,
            is_active=True,
        )
        rec2_id = rec2.id
    cleanup_records["users"].append(rec2_id)
    rec2_token = await _login(client, f"rec2-{tag}@example.com", "RecruiterPass123!")

    # Candidate + Job + Application
    cand_res = await client.post(
        "/api/v1/candidates/",
        json={
            "full_name": f"Karan Verma {tag}",
            "email": f"karan.{tag}@example.com",
            "profile_summary": "Backend engineer.",
            "years_experience": 4.0,
            "primary_domain": "Software Engineering",
            "technical_skills": ["Python"],
            "notice_period_days": 30,
            "allow_duplicate": True,
        },
        headers=_auth(rec_token),
    )
    cid = cand_res.json()["id"]
    cleanup_records["candidates"].append(uuid.UUID(cid))

    job_res = await client.post(
        "/api/v1/jobs/",
        json={
            "title": f"Backend Engineer {tag}",
            "department": "Eng",
            "location": "Remote",
            "description": "Python APIs",
            "required_skills": ["Python"],
            "status": "open",
        },
        headers=_auth(rec_token),
    )
    jid = job_res.json()["id"]
    cleanup_records["jobs"].append(uuid.UUID(jid))

    app_res = await client.post(
        "/api/v1/applications/",
        json={"candidate_id": cid, "job_id": jid, "stage": "interview"},
        headers=_auth(rec_token),
    )
    app_id = app_res.json()["id"]

    # Schedule interview with BOTH recruiter1 and recruiter2 as participants
    iv_res = await client.post(
        f"/api/v1/applications/{app_id}/interviews",
        json={
            "round_name": "Technical Round 1",
            "scheduled_at": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
            "duration_minutes": 45,
            "mode": "video",
            "location_or_link": "https://meet.example.com/r1",
            "participant_ids": [str(seeded_users["recruiter"]["id"]), str(rec2_id)],
        },
        headers=_auth(rec_token),
    )
    assert iv_res.status_code == 201, iv_res.text
    iv_id = iv_res.json()["id"]

    # /interviews/mine includes it for rec2
    mine = await client.get("/api/v1/interviews/mine", headers=_auth(rec2_token))
    assert mine.status_code == 200
    assert any(i["id"] == iv_id for i in mine.json())

    # .ics download works and respects blind mode
    ics_blind = await client.get(
        f"/api/v1/interviews/{iv_id}/ics", params={"blind": True}, headers=_auth(viewer_token)
    )
    assert ics_blind.status_code == 200
    assert "BEGIN:VCALENDAR" in ics_blind.text
    assert f"Karan Verma {tag}" not in ics_blind.text

    # Recruiter 1 submits scorecard
    sc1 = await client.post(
        f"/api/v1/interviews/{iv_id}/scorecards",
        json={
            "ratings": {"Role & Technical Depth": 5, "Problem Solving": 4},
            "recommendation": "strong_yes",
            "comments": "Excellent architecture depth.",
        },
        headers=_auth(rec_token),
    )
    assert sc1.status_code == 201, sc1.text

    # Recruiter 2 (assigned participant, hasn't submitted yet) CANNOT see Recruiter 1's scorecard!
    locked = await client.get(f"/api/v1/interviews/{iv_id}/scorecards", headers=_auth(rec2_token))
    assert locked.status_code == 200
    assert locked.json()["peer_scorecards_locked"] is True
    assert locked.json()["scorecards"] == []

    # Admin sees all scorecards even without submitting
    admin_view = await client.get(f"/api/v1/interviews/{iv_id}/scorecards", headers=_auth(admin_token))
    assert admin_view.status_code == 200
    assert len(admin_view.json()["scorecards"]) == 1
    assert admin_view.json()["aggregate"]["average_rating"] == 4.5

    # Viewer sees aggregate ONLY and cannot submit
    viewer_view = await client.get(f"/api/v1/interviews/{iv_id}/scorecards", headers=_auth(viewer_token))
    assert viewer_view.status_code == 200
    assert viewer_view.json()["viewer_aggregate_only"] is True
    assert viewer_view.json()["scorecards"] == []
    assert viewer_view.json()["aggregate"]["count"] == 1
    assert viewer_view.json()["aggregate"]["average_rating"] == 4.5

    viewer_post = await client.post(
        f"/api/v1/interviews/{iv_id}/scorecards",
        json={"ratings": {"Tech": 3}, "recommendation": "yes", "comments": "No"},
        headers=_auth(viewer_token),
    )
    assert viewer_post.status_code == 403

    # Once Recruiter 2 submits, Recruiter 2 unlocks and sees both scorecards!
    sc2 = await client.post(
        f"/api/v1/interviews/{iv_id}/scorecards",
        json={
            "ratings": {"Role & Technical Depth": 4, "Problem Solving": 4},
            "recommendation": "yes",
            "comments": "Solid coder.",
        },
        headers=_auth(rec2_token),
    )
    assert sc2.status_code == 201
    unlocked = await client.get(f"/api/v1/interviews/{iv_id}/scorecards", headers=_auth(rec2_token))
    assert unlocked.json()["peer_scorecards_locked"] is False
    assert len(unlocked.json()["scorecards"]) == 2
    assert unlocked.json()["aggregate"]["count"] == 2

    # Kanban Job detail surfaces scorecard aggregate on application card
    job_detail = await client.get(f"/api/v1/jobs/{jid}", headers=_auth(viewer_token))
    assert job_detail.status_code == 200
    app_card = job_detail.json()["applications"][0]
    assert app_card["scorecard_count"] == 2
    assert app_card["scorecard_average"] == 4.25


@pytest.mark.asyncio
async def test_emails_rejection_guard_offers_stage_sync_and_cascade(
    client, seeded_users, cleanup_records, db_session_factory, monkeypatch
):
    admin_token = await _login(client, seeded_users["admin"]["email"], seeded_users["admin"]["password"])
    rec_token = await _login(
        client, seeded_users["recruiter"]["email"], seeded_users["recruiter"]["password"]
    )
    viewer_token = await _login(
        client, seeded_users["viewer"]["email"], seeded_users["viewer"]["password"]
    )
    tag = uuid.uuid4().hex[:8]
    monkeypatch.setattr(settings, "ENABLE_SEMANTIC_SEARCH", False)

    # Capture mocked email deliveries (zero network calls)
    sent_messages = []

    class FakeSender(ConsoleEmailSender):
        async def send_email(self, *, to_email: str, subject: str, body: str) -> None:
            sent_messages.append({"to": to_email, "subject": subject, "body": body})

    monkeypatch.setattr("app.crud.workflow.default_email_sender", FakeSender())

    # Candidate with 30-day notice period + old consent for retention cascade test
    cand_res = await client.post(
        "/api/v1/candidates/",
        json={
            "full_name": f"Sneha Rao {tag}",
            "email": f"sneha.{tag}@example.com",
            "profile_summary": "Product designer.",
            "years_experience": 5.0,
            "primary_domain": "Design",
            "technical_skills": ["Figma"],
            "notice_period_days": 30,
            "consent_given_at": (datetime.now(timezone.utc) - timedelta(days=400)).isoformat(),
            "allow_duplicate": True,
        },
        headers=_auth(rec_token),
    )
    cid = cand_res.json()["id"]
    cleanup_records["candidates"].append(uuid.UUID(cid))

    job_res = await client.post(
        "/api/v1/jobs/",
        json={
            "title": f"Lead Designer {tag}",
            "department": "Design",
            "location": "Remote",
            "description": "Design systems",
            "required_skills": ["Figma"],
            "status": "open",
        },
        headers=_auth(rec_token),
    )
    jid = job_res.json()["id"]
    cleanup_records["jobs"].append(uuid.UUID(jid))

    app_res = await client.post(
        "/api/v1/applications/",
        json={"candidate_id": cid, "job_id": jid, "stage": "interview"},
        headers=_auth(rec_token),
    )
    app_id = app_res.json()["id"]

    # 1. Email templates: recruiter cannot create; admin can; rejection forces auto_send=False
    rec_tpl_forbid = await client.post(
        "/api/v1/email-templates/",
        json={"key": f"custom_reject_{tag}", "subject": "Hi", "body": "Body", "auto_send": True},
        headers=_auth(rec_token),
    )
    assert rec_tpl_forbid.status_code == 403

    # Preview & rejection confirmation guard
    prev = await client.post(
        "/api/v1/emails/preview",
        json={"candidate_id": cid, "application_id": app_id, "template_key": "rejection_notice"},
        headers=_auth(rec_token),
    )
    assert prev.status_code == 200
    assert f"Sneha Rao {tag}" in prev.json()["body"]

    rej_unconfirmed = await client.post(
        "/api/v1/emails/send",
        json={
            "candidate_id": cid,
            "application_id": app_id,
            "template_key": "rejection_notice",
            "confirm_rejection": False,
        },
        headers=_auth(rec_token),
    )
    assert rej_unconfirmed.status_code == 400

    # Confirmed email send succeeds, appears in candidate activity timeline
    send_ok = await client.post(
        "/api/v1/emails/send",
        json={
            "candidate_id": cid,
            "application_id": app_id,
            "template_key": "interview_invite",
        },
        headers=_auth(rec_token),
    )
    assert send_ok.status_code == 201, send_ok.text
    assert send_ok.json()["status"] == "sent"
    assert len(sent_messages) == 1

    activity = await client.get(f"/api/v1/candidates/{cid}/activity", headers=_auth(viewer_token))
    assert activity.status_code == 200
    assert any(item["kind"] == "email" for item in activity.json())

    # 2. Offers: viewer gets 403; recruiter creates offer -> expected_joining_date defaults from notice_period_days
    viewer_offer = await client.get(f"/api/v1/applications/{app_id}/offers", headers=_auth(viewer_token))
    assert viewer_offer.status_code == 403

    offer_res = await client.post(
        f"/api/v1/applications/{app_id}/offers",
        json={"offered_ctc": 2600000, "currency": "INR", "status": "extended", "notes": "Band L5"},
        headers=_auth(rec_token),
    )
    assert offer_res.status_code == 201, offer_res.text
    offer = offer_res.json()
    expected_join = (date.today() + timedelta(days=30)).isoformat()
    assert offer["expected_joining_date"] == expected_join

    # Extending offer moved application stage -> offer
    apps_after_ext = await client.get(f"/api/v1/candidates/{cid}/applications", headers=_auth(rec_token))
    assert apps_after_ext.json()[0]["stage"] == "offer"

    # Accepting offer moves application stage -> hired
    accept_res = await client.patch(
        f"/api/v1/offers/{offer['id']}",
        json={"status": "accepted"},
        headers=_auth(rec_token),
    )
    assert accept_res.status_code == 200
    apps_after_acc = await client.get(f"/api/v1/candidates/{cid}/applications", headers=_auth(rec_token))
    assert apps_after_acc.json()[0]["stage"] == "hired"

    # Also schedule an interview + scorecard so retention purge proves ALL Phase 5 rows cascade!
    iv_res = await client.post(
        f"/api/v1/applications/{app_id}/interviews",
        json={
            "round_name": "Portfolio Review",
            "scheduled_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
            "duration_minutes": 45,
            "mode": "video",
        },
        headers=_auth(rec_token),
    )
    iv_id = uuid.UUID(iv_res.json()["id"])
    await client.post(
        f"/api/v1/interviews/{iv_id}/scorecards",
        json={"ratings": {"Craft": 5}, "recommendation": "strong_yes", "comments": "Great"},
        headers=_auth(rec_token),
    )

    # Retention purge removes candidate AND cascades interviews, participants, scorecards, email_log, offers
    purge = await client.post(
        "/api/v1/privacy/purge-expired",
        params={"retention_days": 365, "dry_run": False},
        headers=_auth(admin_token),
    )
    assert purge.status_code == 200
    assert cid in purge.json()["candidate_ids"]

    async with db_session_factory() as db:
        assert (await db.execute(select(Interview).where(Interview.id == iv_id))).scalar_one_or_none() is None
        assert (
            await db.execute(select(InterviewParticipant).where(InterviewParticipant.interview_id == iv_id))
        ).scalars().all() == []
        assert (
            await db.execute(select(Scorecard).where(Scorecard.interview_id == iv_id))
        ).scalars().all() == []
        assert (
            await db.execute(select(EmailLog).where(EmailLog.candidate_id == uuid.UUID(cid)))
        ).scalars().all() == []
        assert (
            await db.execute(select(Offer).where(Offer.id == uuid.UUID(offer["id"])))
        ).scalar_one_or_none() is None
