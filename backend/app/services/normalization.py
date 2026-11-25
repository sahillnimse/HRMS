"""Contact normalization helpers for reliable deduplication."""

import re
from typing import Optional


def normalize_email(email: Optional[str]) -> Optional[str]:
    """Lowercase and trim email addresses."""
    if not email:
        return None
    cleaned = email.strip().lower()
    return cleaned or None


def normalize_phone(phone: Optional[str]) -> Optional[str]:
    """
    Keep digits only, strip leading +91 / 0091 (for 10-digit Indian numbers) and
    leading zeros so formatting variations match cleanly.
    """
    if not phone:
        return None
    digits = re.sub(r"\D+", "", phone)
    if not digits:
        return None

    # Strip international exit prefix 00
    if digits.startswith("00") and len(digits) > 10:
        digits = digits[2:]

    # Strip Indian country code 91 when followed by a 10-digit subscriber number
    if digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]

    # Strip leading trunk zeros (e.g. 09876543210 -> 9876543210)
    digits = digits.lstrip("0")

    return digits if len(digits) >= 7 else None
