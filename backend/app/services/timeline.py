"""
Phase 4.2 + Section Mapping: Career timeline normalization, education study windows,
employment-type-aware tenure statistics, and gap/overlap detection.

FAIRNESS NOTE:
  Graduation/study years are used strictly to place study windows on the career timeline
  so studying is never misflagged as an employment gap. They are NEVER used to infer,
  display, or score age or "years since graduation".
"""

from datetime import date
import re
from typing import Any, List, Optional, Sequence, Tuple

from app.core.config import settings
from app.schemas.clarity import (
    TenureStats,
    TimelineEducation,
    TimelineGap,
    TimelineOverlap,
    TimelineRole,
)
from app.services.experience import (
    _PRESENT_TOKENS,
    _to_month_index,
    compute_years_experience,
    parse_resume_date,
)
from app.services.section_mapping import infer_employment_type, parse_education_dates

CORE_EMPLOYMENT_TYPES = frozenset({"full_time", "part_time", "unknown"})
INTERNSHIP_TRAINEE_TYPES = frozenset({"internship", "trainee"})
CONTRACT_FREELANCE_TYPES = frozenset({"contract", "freelance"})

_MASTERS_RE = re.compile(
    r"\b(?:m\.?s\.?c?|m\.?tech|m\.?e\.?|m\.?b\.?a\.?|m\.?c\.?a\.?|m\.?a\.?|l\.?l\.?m\.?|"
    r"master'?s?|post\s*graduate|pgdm|pg\s+diploma)\b",
    re.IGNORECASE,
)
_DIPLOMA_RE = re.compile(
    r"\b(?:diploma|polytechnic|associate'?s?|a\.?s\.?|a\.?a\.?)\b",
    re.IGNORECASE,
)


def _month_index_to_ym(idx: int) -> str:
    year = idx // 12
    month = (idx % 12) + 1
    return f"{year:04d}-{month:02d}"


def _is_present_token(raw_end: Optional[str]) -> bool:
    if not raw_end:
        return True
    return raw_end.strip().lower() in _PRESENT_TOKENS


def _estimate_degree_duration_months(degree: str) -> int:
    deg = (degree or "").strip()
    if _MASTERS_RE.search(deg):
        return max(6, int(settings.EDU_DURATION_MASTERS_MONTHS))
    if _DIPLOMA_RE.search(deg):
        return max(6, int(settings.EDU_DURATION_DIPLOMA_MONTHS))
    return max(6, int(settings.EDU_DURATION_BACHELORS_MONTHS))


def _merge_intervals(intervals: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
    if not intervals:
        return []
    ordered = sorted(intervals, key=lambda iv: (iv[0], iv[1]))
    merged: List[Tuple[int, int]] = [ordered[0]]
    for s, e in ordered[1:]:
        ps, pe = merged[-1]
        if s <= pe:
            merged[-1] = (ps, max(pe, e))
        else:
            merged.append((s, e))
    return merged


def _subtract_intervals(
    gap_start: int,
    gap_end: int,
    subtractors: List[Tuple[int, int]],
) -> List[Tuple[int, int]]:
    """Return sub-intervals of [gap_start, gap_end) not covered by any merged subtractor."""
    if gap_end <= gap_start:
        return []
    remaining: List[Tuple[int, int]] = [(gap_start, gap_end)]
    for sub_s, sub_e in subtractors:
        next_rem: List[Tuple[int, int]] = []
        for rs, re_ in remaining:
            if sub_e <= rs or sub_s >= re_:
                next_rem.append((rs, re_))
            else:
                if sub_s > rs:
                    next_rem.append((rs, sub_s))
                if sub_e < re_:
                    next_rem.append((sub_e, re_))
        remaining = next_rem
        if not remaining:
            break
    return remaining


def build_study_windows(
    education: Sequence[Any],
    *,
    today: Optional[date] = None,
    blind: bool = False,
) -> Tuple[List[TimelineEducation], List[Tuple[int, int]]]:
    """
    Build structured study windows and merged [start_month, end_month_excl) intervals
    from candidate education entries.
    """
    ref = today or date.today()
    max_month = _to_month_index(ref.year, ref.month)
    grad_month = min(12, max(1, int(settings.EDU_ESTIMATED_GRADUATION_MONTH)))
    # Academic start month is the month immediately after grad_month (e.g. July when grad_month=6)
    acad_start_month = (grad_month % 12) + 1

    windows: List[TimelineEducation] = []
    raw_intervals: List[Tuple[int, int]] = []

    for idx, item in enumerate(education or []):
        if isinstance(item, dict):
            degree = str(item.get("degree") or "").strip() or "Education"
            field_of_study = (
                str(item.get("field_of_study")).strip()
                if item.get("field_of_study")
                else None
            )
            institution = str(item.get("institution") or "").strip()
            s_raw = item.get("start_year")
            e_raw = item.get("end_year")
            g_raw = item.get("graduation_year")
            is_curr_raw = item.get("is_current")
            date_range_raw = item.get("date_range") if isinstance(item.get("date_range"), str) else None
        else:
            degree = str(getattr(item, "degree", "") or "").strip() or "Education"
            fos_val = getattr(item, "field_of_study", None)
            field_of_study = str(fos_val).strip() if fos_val else None
            institution = str(getattr(item, "institution", "") or "").strip()
            s_raw = getattr(item, "start_year", None)
            e_raw = getattr(item, "end_year", None)
            g_raw = getattr(item, "graduation_year", None)
            is_curr_raw = getattr(item, "is_current", False)
            date_range_raw = None

        s_yr, e_yr, g_yr, is_curr = parse_education_dates(
            start_year=s_raw,
            end_year=e_raw,
            graduation_year=g_raw,
            date_range=date_range_raw,
            is_current=bool(is_curr_raw) if is_curr_raw is not None else None,
        )

        # Future graduation/end year implies currently studying
        effective_end_yr = e_yr or g_yr
        if effective_end_yr is not None and _to_month_index(effective_end_yr, grad_month) > max_month:
            is_curr = True

        duration_est = _estimate_degree_duration_months(degree)
        start_idx: Optional[int] = None
        end_idx: Optional[int] = None
        estimated = False

        if s_yr is not None and effective_end_yr is not None:
            if s_yr == effective_end_yr:
                start_idx = _to_month_index(s_yr, 1)
                end_idx = _to_month_index(effective_end_yr, grad_month)
            else:
                start_idx = _to_month_index(s_yr, acad_start_month)
                end_idx = _to_month_index(effective_end_yr, grad_month)
            if is_curr:
                end_idx = max_month
        elif s_yr is not None and is_curr:
            start_idx = _to_month_index(s_yr, acad_start_month)
            end_idx = max_month
        elif effective_end_yr is not None:
            estimated = True
            end_idx = _to_month_index(effective_end_yr, grad_month)
            start_idx = end_idx - duration_est + 1
            if is_curr:
                end_idx = max_month
        elif is_curr:
            estimated = True
            end_idx = max_month
            start_idx = max_month - duration_est + 1

        if start_idx is not None and end_idx is not None:
            start_idx = min(start_idx, max_month)
            end_idx = min(end_idx, max_month)
            if end_idx >= start_idx:
                raw_intervals.append((start_idx, end_idx + 1))
            else:
                start_idx = None
                end_idx = None

        windows.append(
            TimelineEducation(
                index=idx,
                degree=degree,
                field_of_study=field_of_study,
                institution="[Institution Redacted]" if blind else institution,
                start_year=s_yr,
                end_year=e_yr,
                graduation_year=g_yr,
                start_ym=_month_index_to_ym(start_idx) if start_idx is not None else None,
                end_ym=(
                    "Present"
                    if is_curr and start_idx is not None
                    else (_month_index_to_ym(end_idx) if end_idx is not None else None)
                ),
                start_month_index=start_idx,
                end_month_index=end_idx,
                is_current=is_curr,
                estimated=estimated,
            )
        )

    windows.sort(
        key=lambda w: (
            w.end_month_index if w.end_month_index is not None else -1,
            w.start_month_index if w.start_month_index is not None else -1,
            -w.index,
        ),
        reverse=True,
    )
    return windows, _merge_intervals(raw_intervals)


def build_career_timeline(
    work_experience: Sequence[Any],
    *,
    education: Sequence[Any] = (),
    gap_threshold_months: Optional[int] = None,
    short_stint_max_months: Optional[int] = None,
    today: Optional[date] = None,
) -> tuple[
    List[TimelineRole],
    List[TimelineGap],
    List[TimelineOverlap],
    TenureStats,
]:
    """
    Normalize work_experience & education into a study-aware career timeline:
      - normalized roles (with employment_type) most-recent first
      - education study windows (real or estimated from graduation_year)
      - gaps strictly greater than `gap_threshold_months`, EXCLUDING/TRIMMING study windows
      - overlapping role pairs
      - tenure statistics distinguishing core roles (full_time/part_time/unknown) from
        internships, trainee stints, and contracts/freelance
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

    _, merged_study_intervals = build_study_windows(
        education, today=ref, blind=False
    )

    roles: List[TimelineRole] = []
    valid_intervals: list[tuple[int, int, str, bool]] = []  # (start, end_excl, label, is_current)
    core_intervals: List[Tuple[int, int]] = []
    intern_intervals: List[Tuple[int, int]] = []

    for idx, item in enumerate(work_experience or []):
        if isinstance(item, dict):
            company = str(item.get("company") or "").strip() or "Unspecified Company"
            job_title = str(item.get("job_title") or "").strip() or "Unspecified Role"
            raw_start = item.get("start_date")
            raw_end = item.get("end_date")
            explicit_emp = item.get("employment_type")
        else:
            company = str(getattr(item, "company", "") or "").strip() or "Unspecified Company"
            job_title = str(getattr(item, "job_title", "") or "").strip() or "Unspecified Role"
            raw_start = getattr(item, "start_date", None)
            raw_end = getattr(item, "end_date", None)
            explicit_emp = getattr(item, "employment_type", None)

        emp_type = infer_employment_type(job_title, company, explicit_emp)

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
                if emp_type in CORE_EMPLOYMENT_TYPES:
                    core_intervals.append((clamped_start, clamped_end + 1))
                elif emp_type in INTERNSHIP_TRAINEE_TYPES:
                    intern_intervals.append((clamped_start, clamped_end + 1))

        roles.append(
            TimelineRole(
                index=idx,
                company=company,
                job_title=job_title,
                employment_type=emp_type,
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

    # Merge work intervals and compute gaps, subtracting study windows (trimming partial overlaps)
    gaps: List[TimelineGap] = []
    if valid_intervals:
        merged_work: list[tuple[int, int, str]] = [
            (valid_intervals[0][0], valid_intervals[0][1], valid_intervals[0][2])
        ]
        for s, e, label, _ in valid_intervals[1:]:
            ps, pe, plabel = merged_work[-1]
            if s <= pe:
                new_label = label if e >= pe else plabel
                merged_work[-1] = (ps, max(pe, e), new_label)
            else:
                # Subtract study windows from the raw gap [pe, s)
                uncovered_segments = _subtract_intervals(pe, s, merged_study_intervals)
                for seg_s, seg_e in uncovered_segments:
                    gap_months = seg_e - seg_s
                    if gap_months > gap_thresh:
                        gaps.append(
                            TimelineGap(
                                from_ym=_month_index_to_ym(seg_s),
                                to_ym=_month_index_to_ym(seg_e - 1),
                                duration_months=gap_months,
                                between_roles=[plabel, label],
                            )
                        )
                merged_work.append((s, e, label))

    total_years = compute_years_experience(
        work_experience,
        today=ref,
        include_internships=settings.COUNT_INTERNSHIPS_IN_EXPERIENCE,
    )
    total_months = int(round(total_years * 12))

    merged_core = _merge_intervals(core_intervals)
    full_time_months = sum(e - s for s, e in merged_core)
    full_time_years = round(full_time_months / 12.0, 1)

    merged_intern = _merge_intervals(intern_intervals)
    internship_months = sum(e - s for s, e in merged_intern)

    core_roles = [r for r in roles if r.employment_type in CORE_EMPLOYMENT_TYPES]
    core_dated_durations = [r.duration_months for r in core_roles if r.duration_months is not None]
    all_dated_durations = [r.duration_months for r in roles if r.duration_months is not None]

    # Average tenure, jobs in last 5 years, and short stints count ONLY core roles
    avg_tenure = (
        round(sum(core_dated_durations) / len(core_dated_durations), 1)
        if core_dated_durations
        else 0.0
    )
    jobs_last_5_years = sum(
        1
        for r in core_roles
        if r.end_month_index is not None
        and not r.has_invalid_dates
        and r.end_month_index >= five_years_ago
    )
    short_stints_count = sum(
        1
        for r in core_roles
        if not r.is_current
        and not r.has_invalid_dates
        and r.duration_months is not None
        and r.duration_months < short_thresh
    )

    internship_count = sum(1 for r in roles if r.employment_type == "internship")
    trainee_count = sum(1 for r in roles if r.employment_type == "trainee")
    contract_count = sum(1 for r in roles if r.employment_type in CONTRACT_FREELANCE_TYPES)

    stats = TenureStats(
        total_years=total_years,
        total_months=total_months,
        full_time_years=full_time_years,
        internship_months=internship_months,
        role_count=len(roles),
        dated_role_count=len(all_dated_durations),
        core_role_count=len(core_roles),
        core_dated_role_count=len(core_dated_durations),
        internship_count=internship_count,
        trainee_count=trainee_count,
        contract_count=contract_count,
        average_tenure_months=avg_tenure,
        jobs_last_5_years=jobs_last_5_years,
        short_stints_count=short_stints_count,
    )
    return roles, gaps, overlaps, stats
