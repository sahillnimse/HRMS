"""Phase 4.2: Career timeline normalization, gap/overlap detection, and tenure statistics."""

from datetime import date
from typing import Any, List, Optional, Sequence

from app.core.config import settings
from app.schemas.clarity import TenureStats, TimelineGap, TimelineOverlap, TimelineRole
from app.services.experience import (
    _PRESENT_TOKENS,
    _to_month_index,
    compute_years_experience,
    parse_resume_date,
)


def _month_index_to_ym(idx: int) -> str:
    year = idx // 12
    month = (idx % 12) + 1
    return f"{year:04d}-{month:02d}"


def _is_present_token(raw_end: Optional[str]) -> bool:
    if not raw_end:
        return True
    return raw_end.strip().lower() in _PRESENT_TOKENS


def build_career_timeline(
    work_experience: Sequence[Any],
    *,
    gap_threshold_months: Optional[int] = None,
    short_stint_max_months: Optional[int] = None,
    today: Optional[date] = None,
) -> tuple[List[TimelineRole], List[TimelineGap], List[TimelineOverlap], TenureStats]:
    """
    Normalize work_experience using `parse_resume_date` and compute:
      - normalized roles (most-recent first)
      - gaps strictly greater than `gap_threshold_months` (default 3)
      - overlapping role pairs
      - tenure statistics (total years via `compute_years_experience`, average tenure, jobs in last 5 yrs)
    """
    ref = today or date.today()
    max_month = _to_month_index(ref.year, ref.month)
    five_years_ago = max_month - 60

    gap_thresh = (
        settings.TIMELINE_GAP_THRESHOLD_MONTHS
        if gap_threshold_months is None
        else max(1, int(gap_threshold_months))
    )
    short_thresh = (
        settings.SHORT_STINT_MAX_MONTHS
        if short_stint_max_months is None
        else max(1, int(short_stint_max_months))
    )

    roles: List[TimelineRole] = []
    valid_intervals: list[tuple[int, int, str, bool]] = []  # (start, end_excl, label, is_current)

    for idx, item in enumerate(work_experience or []):
        if isinstance(item, dict):
            company = str(item.get("company") or "").strip() or "Unspecified Company"
            job_title = str(item.get("job_title") or "").strip() or "Unspecified Role"
            raw_start = item.get("start_date")
            raw_end = item.get("end_date")
        else:
            company = str(getattr(item, "company", "") or "").strip() or "Unspecified Company"
            job_title = str(getattr(item, "job_title", "") or "").strip() or "Unspecified Role"
            raw_start = getattr(item, "start_date", None)
            raw_end = getattr(item, "end_date", None)

        start_idx = parse_resume_date(raw_start, is_end=False, today=ref)
        is_current = bool(start_idx is not None and _is_present_token(raw_end))
        end_idx = (
            parse_resume_date(raw_end, is_end=True, today=ref)
            if raw_end
            else (max_month if start_idx is not None else None)
        )

        has_invalid_dates = False
        duration_months: Optional[int] = None
        clamped_start = min(start_idx, max_month) if start_idx is not None else None
        clamped_end = min(end_idx, max_month) if end_idx is not None else None

        if clamped_start is not None and clamped_end is not None:
            if clamped_end < clamped_start:
                has_invalid_dates = True
            else:
                duration_months = (clamped_end - clamped_start) + 1
                label = f"{job_title} at {company}"
                valid_intervals.append((clamped_start, clamped_end + 1, label, is_current))

        roles.append(
            TimelineRole(
                index=idx,
                company=company,
                job_title=job_title,
                raw_start=str(raw_start) if raw_start is not None else None,
                raw_end=str(raw_end) if raw_end is not None else None,
                start_ym=_month_index_to_ym(clamped_start) if clamped_start is not None else None,
                end_ym=(
                    "Present"
                    if is_current and not has_invalid_dates
                    else (_month_index_to_ym(clamped_end) if clamped_end is not None else None)
                ),
                start_month_index=clamped_start,
                end_month_index=clamped_end,
                duration_months=duration_months,
                is_current=is_current and not has_invalid_dates,
                has_invalid_dates=has_invalid_dates,
            )
        )

    # Sort roles most-recent first (undated roles at bottom in original order)
    roles.sort(
        key=lambda r: (
            r.end_month_index if r.end_month_index is not None else -1,
            r.start_month_index if r.start_month_index is not None else -1,
            -r.index,
        ),
        reverse=True,
    )

    # Sort valid intervals chronologically to detect overlaps & gaps
    valid_intervals.sort(key=lambda iv: (iv[0], iv[1]))

    overlaps: List[TimelineOverlap] = []
    for i in range(len(valid_intervals)):
        s1, e1, label1, _ = valid_intervals[i]
        for j in range(i + 1, len(valid_intervals)):
            s2, e2, label2, _ = valid_intervals[j]
            if s2 >= e1:
                break
            ov_start = max(s1, s2)
            ov_end = min(e1, e2)
            # Adjacent same-month handover (1 month) is normal; flag true overlap >= 2 months
            ov_months = ov_end - ov_start
            if ov_months >= 2:
                overlaps.append(
                    TimelineOverlap(
                        from_ym=_month_index_to_ym(ov_start),
                        to_ym=_month_index_to_ym(ov_end - 1),
                        overlap_months=ov_months,
                        roles=[label1, label2],
                    )
                )

    # Merge intervals to compute gaps between periods of employment
    gaps: List[TimelineGap] = []
    if valid_intervals:
        merged: list[tuple[int, int, str]] = [
            (valid_intervals[0][0], valid_intervals[0][1], valid_intervals[0][2])
        ]
        for s, e, label, _ in valid_intervals[1:]:
            ps, pe, plabel = merged[-1]
            if s <= pe:
                new_label = label if e >= pe else plabel
                merged[-1] = (ps, max(pe, e), new_label)
            else:
                gap_months = s - pe
                if gap_months > gap_thresh:
                    gaps.append(
                        TimelineGap(
                            from_ym=_month_index_to_ym(pe),
                            to_ym=_month_index_to_ym(s - 1),
                            duration_months=gap_months,
                            between_roles=[plabel, label],
                        )
                    )
                merged.append((s, e, label))

    total_years = compute_years_experience(work_experience, today=ref)
    total_months = int(round(total_years * 12))
    dated_durations = [r.duration_months for r in roles if r.duration_months is not None]
    avg_tenure = round(sum(dated_durations) / len(dated_durations), 1) if dated_durations else 0.0

    jobs_last_5_years = sum(
        1
        for r in roles
        if r.end_month_index is not None
        and not r.has_invalid_dates
        and r.end_month_index >= five_years_ago
    )
    short_stints_count = sum(
        1
        for r in roles
        if not r.is_current
        and not r.has_invalid_dates
        and r.duration_months is not None
        and r.duration_months < short_thresh
    )

    stats = TenureStats(
        total_years=total_years,
        total_months=total_months,
        role_count=len(roles),
        dated_role_count=len(dated_durations),
        average_tenure_months=avg_tenure,
        jobs_last_5_years=jobs_last_5_years,
        short_stints_count=short_stints_count,
    )
    return roles, gaps, overlaps, stats
