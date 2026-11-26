"""
Phase 4.3: Neutral, informational-only consistency checks ("worth verifying").

STRICT FAIRNESS & GOVERNANCE RULES:
- Uses ONLY job-relevant career history, dates, and listed skills.
- NEVER inspects or infers age, gender, religion, caste, marital status, nationality, photo, or name origin.
- Informational only: NEVER auto-rejects a candidate and NEVER alters a JD match score.
"""

import re
from typing import Any, List, Optional, Sequence

from app.core.config import settings
from app.schemas.clarity import (
    ConsistencyCheckItem,
    TenureStats,
    TimelineGap,
    TimelineOverlap,
    TimelineRole,
)


def _skill_mentioned_in_corpus(skill: str, corpus_lower: str) -> bool:
    s = (skill or "").strip().lower()
    if len(s) < 2:
        return True
    # Word-boundary-friendly check that still supports C++, C#, Node.js, CI/CD
    escaped = re.escape(s)
    pattern = rf"(?<![a-z0-9]){escaped}(?![a-z0-9])"
    return bool(re.search(pattern, corpus_lower))


def run_consistency_checks(
    *,
    roles: Sequence[TimelineRole],
    gaps: Sequence[TimelineGap],
    overlaps: Sequence[TimelineOverlap],
    tenure_stats: TenureStats,
    stated_years: float,
    llm_stated_years: Optional[float],
    work_experience: Sequence[Any],
    profile_summary: str,
    technical_skills: Sequence[str],
    tools: Sequence[str],
) -> List[ConsistencyCheckItem]:
    """
    Return neutral, evidence-backed verification items for human review.
    """
    items: List[ConsistencyCheckItem] = []

    # 1. End-before-start dates
    invalid_roles = [r for r in roles if r.has_invalid_dates]
    for r in invalid_roles[:2]:
        items.append(
            ConsistencyCheckItem(
                code="end_before_start",
                severity="check",
                message=(
                    f"Date range for {r.job_title} at {r.company} lists an end date "
                    f"({r.raw_end}) earlier than the start date ({r.raw_start})."
                ),
                evidence={
                    "role": f"{r.job_title} at {r.company}",
                    "raw_start": r.raw_start,
                    "raw_end": r.raw_end,
                },
            )
        )

    # 2. Overlapping employment dates (>= 2 months)
    if overlaps:
        top_ov = max(overlaps, key=lambda o: o.overlap_months)
        items.append(
            ConsistencyCheckItem(
                code="overlapping_dates",
                severity="check" if top_ov.overlap_months >= 4 else "info",
                message=(
                    f"Overlapping dates ({top_ov.overlap_months} months, {top_ov.from_ym} to "
                    f"{top_ov.to_ym}) between {' and '.join(top_ov.roles)}—worth confirming "
                    "whether roles were concurrent or consulting."
                ),
                evidence={
                    "count": len(overlaps),
                    "from_ym": top_ov.from_ym,
                    "to_ym": top_ov.to_ym,
                    "overlap_months": top_ov.overlap_months,
                    "roles": top_ov.roles,
                },
            )
        )

    # 3. Employment gaps (> threshold months)
    if gaps:
        longest_gap = max(gaps, key=lambda g: g.duration_months)
        items.append(
            ConsistencyCheckItem(
                code="employment_gap",
                severity="check" if longest_gap.duration_months >= 6 else "info",
                message=(
                    f"Career timeline has a {longest_gap.duration_months}-month gap "
                    f"({longest_gap.from_ym} to {longest_gap.to_ym})—worth asking about "
                    "study, sabbatical, freelance work, or unlisted projects."
                ),
                evidence={
                    "count": len(gaps),
                    "from_ym": longest_gap.from_ym,
                    "to_ym": longest_gap.to_ym,
                    "duration_months": longest_gap.duration_months,
                    "between_roles": longest_gap.between_roles,
                },
            )
        )

    # 4. Repeated short stints (2+ completed roles under SHORT_STINT_MAX_MONTHS)
    if tenure_stats.short_stints_count >= 2:
        short_roles = [
            f"{r.job_title} at {r.company} ({r.duration_months}m)"
            for r in roles
            if not r.is_current
            and not r.has_invalid_dates
            and r.duration_months is not None
            and r.duration_months < settings.SHORT_STINT_MAX_MONTHS
        ]
        items.append(
            ConsistencyCheckItem(
                code="repeated_short_stints",
                severity="info",
                message=(
                    f"{tenure_stats.short_stints_count} completed roles lasted under "
                    f"{settings.SHORT_STINT_MAX_MONTHS} months—worth clarifying role scope, "
                    "contract engagements, or team changes."
                ),
                evidence={
                    "short_stints_count": tenure_stats.short_stints_count,
                    "threshold_months": settings.SHORT_STINT_MAX_MONTHS,
                    "roles": short_roles[:4],
                },
            )
        )

    # 5. Stated vs computed years of experience mismatch
    mismatch_thresh = float(settings.EXPERIENCE_MISMATCH_YEARS_THRESHOLD)
    computed = tenure_stats.total_years
    reference_stated = stated_years
    if llm_stated_years is not None and abs(llm_stated_years - computed) > abs(stated_years - computed):
        reference_stated = float(llm_stated_years)

    if tenure_stats.dated_role_count > 0 and abs(reference_stated - computed) >= mismatch_thresh:
        items.append(
            ConsistencyCheckItem(
                code="experience_mismatch",
                severity="check",
                message=(
                    f"Stated experience ({reference_stated:.1f} yrs) differs from dated work "
                    f"history ({computed:.1f} yrs)—worth verifying internships, freelance, or "
                    "undated roles."
                ),
                evidence={
                    "stated_years": round(reference_stated, 1),
                    "computed_years": round(computed, 1),
                    "difference_years": round(abs(reference_stated - computed), 1),
                },
            )
        )

    # 6. Listed skills with no supporting mention in roles or summary
    bullet_texts: list[str] = []
    for item in work_experience or []:
        if isinstance(item, dict):
            bullet_texts.append(str(item.get("job_title") or ""))
            bullet_texts.extend(str(b) for b in (item.get("bullets") or []) if b)
    corpus = " ".join([profile_summary or "", *bullet_texts]).lower()

    all_listed = list(dict.fromkeys([*(technical_skills or []), *(tools or [])]))
    if len(bullet_texts) >= 2 and len(all_listed) >= 3:
        unverified = [sk for sk in all_listed if not _skill_mentioned_in_corpus(sk, corpus)]
        # Flag only when a noticeable subset (>= 3 skills and >= 40% of listed) has no role mention
        if len(unverified) >= 3 and (len(unverified) / len(all_listed)) >= 0.4:
            preview = ", ".join(unverified[:5])
            items.append(
                ConsistencyCheckItem(
                    code="unverified_listed_skills",
                    severity="info",
                    message=(
                        f"{len(unverified)} of {len(all_listed)} listed skills ({preview}"
                        f"{'…' if len(unverified) > 5 else ''}) are not referenced in role "
                        "descriptions—worth exploring hands-on depth in interview."
                    ),
                    evidence={
                        "unverified_count": len(unverified),
                        "total_skills": len(all_listed),
                        "sample_skills": unverified[:8],
                    },
                )
            )

    return items
