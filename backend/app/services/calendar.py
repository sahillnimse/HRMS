"""
Phase 5.1: CalendarProvider abstraction with default RFC 5545 ICS provider.

Future extension point:
  Implement `GoogleCalendarProvider` (Google Calendar API v3 + service account / OAuth)
  or `OutlookCalendarProvider` (Microsoft Graph `/me/events`) subclassing `CalendarProvider`
  and switch via `settings.CALENDAR_PROVIDER`.
"""

from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from typing import Sequence

from app.core.config import settings


def _ics_escape(value: str) -> str:
    return (
        (value or "")
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )


def _utc_fmt(dt: datetime) -> str:
    utc_dt = dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    return utc_dt.strftime("%Y%m%dT%H%M%SZ")


class CalendarProvider(ABC):
    """Pluggable calendar invite provider (ICS default; Google/Outlook future extension)."""

    @abstractmethod
    def build_invite(
        self,
        *,
        uid: str,
        summary: str,
        description: str,
        start_utc: datetime,
        duration_minutes: int,
        location: str,
        attendee_emails: Sequence[str],
    ) -> bytes:
        raise NotImplementedError


class IcsCalendarProvider(CalendarProvider):
    """Generates RFC 5545 .ics calendar invites without requiring OAuth credentials."""

    def build_invite(
        self,
        *,
        uid: str,
        summary: str,
        description: str,
        start_utc: datetime,
        duration_minutes: int,
        location: str,
        attendee_emails: Sequence[str],
    ) -> bytes:
        dt_start = start_utc.astimezone(timezone.utc) if start_utc.tzinfo else start_utc.replace(tzinfo=timezone.utc)
        dt_end = dt_start + timedelta(minutes=max(10, int(duration_minutes or 45)))
        now_str = _utc_fmt(datetime.now(timezone.utc))

        lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            f"PRODID:-//{_ics_escape(settings.APP_NAME)}//Interview Scheduler//EN",
            "CALSCALE:GREGORIAN",
            "METHOD:REQUEST",
            "BEGIN:VEVENT",
            f"UID:{uid}@hrms-ai",
            f"DTSTAMP:{now_str}",
            f"DTSTART:{_utc_fmt(dt_start)}",
            f"DTEND:{_utc_fmt(dt_end)}",
            f"SUMMARY:{_ics_escape(summary)}",
            f"DESCRIPTION:{_ics_escape(description)}",
            f"LOCATION:{_ics_escape(location)}",
        ]
        for email in attendee_emails:
            clean = (email or "").strip()
            if clean:
                lines.append(f"ATTENDEE;RSVP=TRUE:mailto:{clean}")
        lines.extend(["END:VEVENT", "END:VCALENDAR", ""])
        return "\r\n".join(lines).encode("utf-8")


def create_calendar_provider() -> CalendarProvider:
    # Default ICS provider; Google/Outlook providers can be wired here via settings.CALENDAR_PROVIDER
    return IcsCalendarProvider()


calendar_provider: CalendarProvider = create_calendar_provider()
