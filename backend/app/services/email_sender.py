"""
Phase 5.3: Pluggable EmailSender abstraction (ConsoleEmailSender default, SmtpEmailSender via env)
and safe {{placeholder}} template rendering.

PRIVACY: Never log raw CV text or full candidate PII in application logs.
"""

from abc import ABC, abstractmethod
import asyncio
from email.message import EmailMessage
import logging
import re
import smtplib
from typing import Dict, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

_PLACEHOLDER_RE = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")


def render_email_template(template_text: str, variables: Dict[str, str]) -> str:
    """Safely substitute {{placeholder}} tokens without executing expressions."""
    def _replace(match: re.Match[str]) -> str:
        key = match.group(1)
        val = variables.get(key)
        return str(val) if val is not None else match.group(0)

    return _PLACEHOLDER_RE.sub(_replace, template_text or "")


class EmailSender(ABC):
    """Abstract email transport (mirrors BaseStorage pattern)."""

    @abstractmethod
    async def send_email(
        self,
        *,
        to_email: str,
        subject: str,
        body: str,
    ) -> None:
        raise NotImplementedError


class ConsoleEmailSender(EmailSender):
    """Development default: logs delivery metadata without external SMTP calls or PII dumps."""

    async def send_email(self, *, to_email: str, subject: str, body: str) -> None:
        domain = to_email.split("@")[-1] if "@" in to_email else "unknown"
        logger.info(
            "[ConsoleEmailSender] Delivered email to *@%s | subject=%r | bytes=%d",
            domain,
            subject[:120],
            len(body.encode("utf-8")),
        )


class SmtpEmailSender(EmailSender):
    """SMTP email transport configured via SMTP_* env vars."""

    def _send_sync(self, *, to_email: str, subject: str, body: str) -> None:
        if not settings.SMTP_HOST:
            raise RuntimeError("SMTP_HOST must be configured when EMAIL_BACKEND=smtp")

        msg = EmailMessage()
        msg["From"] = settings.SMTP_FROM_EMAIL
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.set_content(body)

        with smtplib.SMTP(
            settings.SMTP_HOST,
            int(settings.SMTP_PORT),
            timeout=int(settings.SMTP_TIMEOUT_SECONDS),
        ) as server:
            if settings.SMTP_USE_TLS:
                server.starttls()
            if settings.SMTP_USERNAME and settings.SMTP_PASSWORD:
                server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            server.send_message(msg)

    async def send_email(self, *, to_email: str, subject: str, body: str) -> None:
        await asyncio.to_thread(self._send_sync, to_email=to_email, subject=subject, body=body)


def create_email_sender(backend: Optional[str] = None) -> EmailSender:
    kind = (backend or settings.EMAIL_BACKEND or "console").strip().lower()
    if kind == "smtp":
        return SmtpEmailSender()
    return ConsoleEmailSender()


email_sender: EmailSender = create_email_sender()
