"""
Deterministic years-of-experience calculator from work experience start/end dates.

Parses common resume date formats ("Jan 2020", "January 2020", "01/2020",
"2020-01", "2020", "Q2 2021", "Present", "Current", etc.), merges overlapping
intervals so concurrent roles are not double-counted, and returns years rounded
to one decimal place.
"""

from datetime import date
import re
from typing import Any, Optional, Sequence

_MONTHS = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}

_PRESENT_TOKENS = {"present", "current", "now", "ongoing", "till date", "to date", "today"}


def _to_month_index(year: int, month: int) -> int:
    return year * 12 + (month - 1)


def parse_resume_date(
    value: Optional[str],
    *,
    is_end: bool = False,
    today: Optional[date] = None,
) -> Optional[int]:
    """
    Convert a resume date string into a monotonic month index (year * 12 + month - 1).
    Returns None if the date cannot be parsed.
    """
    if not value or not isinstance(value, str):
        return None
    ref = today or date.today()
    s = value.strip()
    if not s:
        return None

    low = re.sub(r"\s+", " ", s.lower())
    if low in _PRESENT_TOKENS:
        return _to_month_index(ref.year, ref.month)

    # ISO / YYYY-MM or YYYY/MM or YYYY-MM-DD
    m = re.match(r"^((?:19|20)\d{2})[-/.](\d{1,2})(?:[-/.]\d{1,2})?$", low)
    if m:
        year, month = int(m.group(1)), int(m.group(2))
        if 1 <= month <= 12:
            return _to_month_index(year, month)

    # MM/YYYY or MM-YYYY
    m = re.match(r"^(\d{1,2})[-/.]((?:19|20)\d{2})$", low)
    if m:
        month, year = int(m.group(1)), int(m.group(2))
        if 1 <= month <= 12:
            return _to_month_index(year, month)

    # Quarter: Q1 2021 / 2021 Q3
    m = re.search(r"\bq([1-4])\s*[-/,]?\s*((?:19|20)\d{2})\b", low)
    if m:
        q, year = int(m.group(1)), int(m.group(2))
        month = (q * 3) if is_end else ((q - 1) * 3 + 1)
        return _to_month_index(year, month)

    # Month name + Year (e.g. "Jan 2020", "Sept. 2020", "January, 2020", "2020 Jan")
    year_match = re.search(r"\b((?:19|20)\d{2})\b", low)
    if year_match:
        year = int(year_match.group(1))
        for token in re.findall(r"[a-z]+", low):
            if token in _MONTHS:
                return _to_month_index(year, _MONTHS[token])
        # Year-only format (e.g. "2020")
        month = 12 if is_end else 1
        # Do not extend a year-only end date past current month if it's the current year
        if is_end and year == ref.year:
            month = ref.month
        return _to_month_index(year, month)

    return None


def compute_years_experience(
    work_experience: Sequence[Any],
    *,
    today: Optional[date] = None,
) -> float:
    """
    Compute total non-overlapping professional years from work_experience items.
    Accepts dicts or objects exposing start_date / end_date attributes.
    """
    ref = today or date.today()
    max_month = _to_month_index(ref.year, ref.month)
    intervals: list[tuple[int, int]] = []

    for item in work_experience or []:
        if isinstance(item, dict):
            raw_start = item.get("start_date")
            raw_end = item.get("end_date")
        else:
            raw_start = getattr(item, "start_date", None)
            raw_end = getattr(item, "end_date", None)

        start = parse_resume_date(raw_start, is_end=False, today=ref)
        if start is None:
            continue

        # If end_date is omitted while start_date is present, default to current month
        end = (
            parse_resume_date(raw_end, is_end=True, today=ref)
            if raw_end
            else max_month
        )
        if end is None:
            continue

        start = min(start, max_month)
        end = min(end, max_month)
        if end < start:
            continue

        # Inclusive of both start and end months (+1 month) for realistic resume tenure
        intervals.append((start, end + 1))

    if not intervals:
        return 0.0

    intervals.sort(key=lambda iv: (iv[0], iv[1]))
    merged: list[tuple[int, int]] = [intervals[0]]
    for start, end in intervals[1:]:
        prev_start, prev_end = merged[-1]
        if start <= prev_end:
            merged[-1] = (prev_start, max(prev_end, end))
        else:
            merged.append((start, end))

    total_months = sum(end - start for start, end in merged)
    return round(total_months / 12.0, 1)
