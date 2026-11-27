"""
Phase 4.3 + Section Mapping: Neutral, informational-only consistency checks ("worth verifying")
and whole-CV skill evidence tracking.

STRICT FAIRNESS & GOVERNANCE RULES:
- Uses ONLY job-relevant career history, dates, projects, credentials, and listed skills.
- NEVER inspects or infers age, gender, religion, caste, marital status, nationality, photo, or name origin.
- Informational only: NEVER auto-rejects a candidate and NEVER alters a JD match score.
"""

from collections import defaultdict
import re
from typing import Any, Dict, List, Optional, Sequence, Set

from app.core.config import settings
from app.schemas.clarity import (
    ConsistencyCheckItem,
    SkillEvidenceItem,
    TenureStats,
    TimelineGap,
    TimelineOverlap,
    TimelineRole,
)
from app.services.timeline import CORE_EMPLOYMENT_TYPES

# Built-in fallback synonym groups used even when DB alias_map is empty or partial
_DEFAULT_ALIAS_GROUPS: tuple[tuple[str, ...], ...] = (
    ("javascript", "js", "ecmascript", "es6"),
    ("typescript", "ts"),
    ("react", "reactjs", "react.js"),
    ("node.js", "node", "nodejs", "node js"),
    ("next.js", "nextjs"),
    ("postgresql", "postgres", "psql"),
    ("python", "python3", "python 3"),
    ("fastapi", "fast api"),
    ("kubernetes", "k8s"),
    ("docker", "docker compose", "docker engine"),
    ("aws", "amazon web services"),
    ("gcp", "google cloud", "google cloud platform"),
    ("azure", "microsoft azure"),
    ("machine learning", "ml"),
    ("deep learning", "dl"),
    ("natural language processing", "nlp"),
    ("computer vision", "cv"),
    ("large language models", "llm", "llms"),
    ("pytorch", "torch"),
    ("tensorflow", "tf"),
    ("scikit-learn", "sklearn", "scikit learn"),
    ("tailwind css", "tailwind", "tailwindcss"),
    ("mongodb", "mongo"),
    ("c++", "cpp"),
    ("c#", "csharp", "c sharp"),
    ("sql", "structured query language"),
    ("graphql", "gql"),
    ("ci/cd", "cicd", "github actions"),
    ("rest api", "rest", "restful", "restful api", "rest apis"),
    ("html", "html5"),
    ("css", "css3"),
    ("git", "github", "gitlab"),
)


def _build_bidirectional_alias_groups(
    alias_map: Optional[Dict[str, str]] = None,
) -> Dict[str, Set[str]]:
    """Map every lowercase surface form -> full set of equivalent lowercase forms."""
    by_canonical: Dict[str, Set[str]] = defaultdict(set)

    for group in _DEFAULT_ALIAS_GROUPS:
        canon = group[0].lower()
        for form in group:
            by_canonical[canon].add(form.lower())

    for alias_key, canonical_val in (alias_map or {}).items():
        c = (canonical_val or "").strip().lower()
        a = (alias_key or "").strip().lower()
        if not c:
            continue
        by_canonical[c].add(c)
        if a:
            by_canonical[c].add(a)

    # Merge any overlapping groups so lookup is symmetric across DB & default groups
    lookup: Dict[str, Set[str]] = {}
    for forms in by_canonical.values():
        merged = set(forms)
        for f in list(forms):
            if f in lookup:
                merged |= lookup[f]
        for f in merged:
            lookup[f] = merged
    return lookup


def _expand_skill_variants(skill: str, alias_groups: Dict[str, Set[str]]) -> Set[str]:
    """Generate lowercase surface variants (aliases, hyphen/space, simple plural/singular)."""
    base = (skill or "").strip().lower()
    if not base:
        return set()

    seeds: Set[str] = {base}
    spaced = re.sub(r"[-_]+", " ", base)
    spaced = re.sub(r"\s+", " ", spaced).strip()
    seeds.add(spaced)

    # Pull equivalent forms from alias groups
    expanded: Set[str] = set(seeds)
    for s in list(seeds):
        if s in alias_groups:
            expanded |= alias_groups[s]

    # Add hyphen/space & simple plural/singular variants
    final_forms: Set[str] = set()
    for form in expanded:
        if not form:
            continue
        final_forms.add(form)
        if "-" in form:
            final_forms.add(form.replace("-", " "))
            final_forms.add(form.replace("-", ""))
        if " " in form:
            final_forms.add(form.replace(" ", "-"))
        if len(form) > 3:
            if form.endswith("s") and not form.endswith("ss") and not form.endswith("js"):
                final_forms.add(form[:-1])
            elif form[-1].isalnum():
                final_forms.add(f"{form}s")
    return final_forms


def _form_mentioned_in_corpus(form: str, corpus_lower: str) -> bool:
    if not form or not corpus_lower:
        return False
    # For very short tokens (1-2 chars like C, R, ML, JS, Go) enforce strict boundaries
    escaped = re.escape(form)
    pattern = rf"(?<![a-z0-9]){escaped}(?![a-z0-9])"
    return bool(re.search(pattern, corpus_lower))


def _skill_mentioned_in_corpus(
    skill: str,
    corpus_lower: str,
    alias_groups: Optional[Dict[str, Set[str]]] = None,
) -> bool:
    s = (skill or "").strip().lower()
    if len(s) < 2 and s not in {"c", "r"}:
        return True
    if not corpus_lower:
        return False
    groups = alias_groups if alias_groups is not None else _build_bidirectional_alias_groups()
    for form in _expand_skill_variants(s, groups):
        if _form_mentioned_in_corpus(form, corpus_lower):
            return True
    return False


def compute_skill_evidence(
    *,
    technical_skills: Sequence[str],
    tools: Sequence[str],
    profile_summary: str = "",
    work_experience: Sequence[Any] = (),
    projects: Sequence[Any] = (),
    certifications: Sequence[str] = (),
    education: Sequence[Any] = (),
    alias_map: Optional[Dict[str, str]] = None,
) -> List[SkillEvidenceItem]:
    """
    Determine which CV sections outside the skills list provide evidence for each listed skill:
      - experience (profile summary + work titles, companies, bullets)
      - projects (project names, descriptions, technologies)
      - certification (certifications)
      - education (degrees, fields of study, coursework)
    """
    exp_parts: List[str] = [profile_summary or ""]
    for item in work_experience or []:
        if isinstance(item, dict):
            exp_parts.append(str(item.get("job_title") or ""))
            exp_parts.extend(str(b) for b in (item.get("bullets") or []) if b)
        else:
            exp_parts.append(str(getattr(item, "job_title", "") or ""))
            exp_parts.extend(str(b) for b in (getattr(item, "bullets", None) or []) if b)
    exp_corpus = " ".join(exp_parts).lower()

    proj_parts: List[str] = []
    for item in projects or []:
        if isinstance(item, dict):
            proj_parts.append(str(item.get("name") or ""))
            proj_parts.append(str(item.get("description") or ""))
            proj_parts.extend(str(t) for t in (item.get("technologies") or []) if t)
        else:
            proj_parts.append(str(getattr(item, "name", "") or ""))
            proj_parts.append(str(getattr(item, "description", "") or ""))
            proj_parts.extend(str(t) for t in (getattr(item, "technologies", None) or []) if t)
    proj_corpus = " ".join(proj_parts).lower()

    cert_corpus = " ".join(str(c) for c in (certifications or []) if c).lower()

    edu_parts: List[str] = []
    for item in education or []:
        if isinstance(item, dict):
            edu_parts.append(str(item.get("degree") or ""))
            edu_parts.append(str(item.get("field_of_study") or ""))
            if isinstance(item.get("coursework"), list):
                edu_parts.extend(str(c) for c in item["coursework"] if c)
            elif isinstance(item.get("coursework"), str):
                edu_parts.append(item["coursework"])
        else:
            edu_parts.append(str(getattr(item, "degree", "") or ""))
            edu_parts.append(str(getattr(item, "field_of_study", "") or ""))
    edu_corpus = " ".join(edu_parts).lower()

    alias_groups = _build_bidirectional_alias_groups(alias_map)

    all_listed: List[str] = []
    seen_low: Set[str] = set()
    for raw in [*(technical_skills or []), *(tools or [])]:
        clean = str(raw or "").strip()
        if clean and clean.lower() not in seen_low:
            seen_low.add(clean.lower())
            all_listed.append(clean)

    results: List[SkillEvidenceItem] = []
    for skill in all_listed:
        sources: List[str] = []
        if _skill_mentioned_in_corpus(skill, exp_corpus, alias_groups):
            sources.append("experience")
        if _skill_mentioned_in_corpus(skill, proj_corpus, alias_groups):
            sources.append("projects")
        if _skill_mentioned_in_corpus(skill, cert_corpus, alias_groups):
            sources.append("certification")
        if _skill_mentioned_in_corpus(skill, edu_corpus, alias_groups):
            sources.append("education")
        results.append(SkillEvidenceItem(skill=skill, sources=sources))
    return results


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
    projects: Sequence[Any] = (),
    certifications: Sequence[str] = (),
    education: Sequence[Any] = (),
    alias_map: Optional[Dict[str, str]] = None,
    skill_evidence: Optional[Sequence[SkillEvidenceItem]] = None,
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

    # 3. Employment gaps (> threshold months, already excluding/trimming study windows)
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

    # 4. Repeated short stints (ONLY core full_time/part_time/unknown completed roles < threshold)
    if tenure_stats.short_stints_count >= 2:
        short_roles = [
            f"{r.job_title} at {r.company} ({r.duration_months}m)"
            for r in roles
            if r.employment_type in CORE_EMPLOYMENT_TYPES
            and not r.is_current
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

    # 5. Stated vs computed years of experience mismatch (like-for-like comparison)
    mismatch_thresh = float(settings.EXPERIENCE_MISMATCH_YEARS_THRESHOLD)
    computed_total = tenure_stats.total_years
    computed_ft = tenure_stats.full_time_years
    has_internships = tenure_stats.internship_months > 0

    def _min_like_for_like_diff(stated: float) -> tuple[float, float]:
        """Compare stated years against matching computed basis (total vs full-time when internships exist)."""
        diff_total = abs(stated - computed_total)
        if has_internships:
            diff_ft = abs(stated - computed_ft)
            if diff_ft <= diff_total:
                return diff_ft, computed_ft
        return diff_total, computed_total

    diff_stated, basis_stated = _min_like_for_like_diff(stated_years)
    ref_stated = stated_years
    ref_diff = diff_stated
    ref_basis = basis_stated

    if llm_stated_years is not None:
        diff_llm, basis_llm = _min_like_for_like_diff(float(llm_stated_years))
        if diff_llm > ref_diff:
            ref_stated = float(llm_stated_years)
            ref_diff = diff_llm
            ref_basis = basis_llm

    if tenure_stats.dated_role_count > 0 and ref_diff >= mismatch_thresh:
        items.append(
            ConsistencyCheckItem(
                code="experience_mismatch",
                severity="check",
                message=(
                    f"Stated experience ({ref_stated:.1f} yrs) differs from dated work "
                    f"history ({ref_basis:.1f} yrs)—worth verifying internships, freelance, or "
                    "undated roles."
                ),
                evidence={
                    "stated_years": round(ref_stated, 1),
                    "computed_years": round(ref_basis, 1),
                    "difference_years": round(ref_diff, 1),
                },
            )
        )

    # 6. Listed skills with no evidence anywhere outside the skills list itself
    ev_list = (
        list(skill_evidence)
        if skill_evidence is not None
        else compute_skill_evidence(
            technical_skills=technical_skills,
            tools=tools,
            profile_summary=profile_summary,
            work_experience=work_experience,
            projects=projects,
            certifications=certifications,
            education=education,
            alias_map=alias_map,
        )
    )

    # Only run when candidate has some narrative/project/credential context to check against
    has_context = (
        len([b for we in (work_experience or []) if isinstance(we, dict) for b in (we.get("bullets") or [])]) >= 1
        or len(projects or []) >= 1
        or len((profile_summary or "").strip()) >= 30
    )

    if has_context and len(ev_list) >= 3:
        unverified = [e.skill for e in ev_list if not e.sources]
        if len(unverified) >= 3 and (len(unverified) / len(ev_list)) >= 0.4:
            preview = ", ".join(unverified[:5])
            items.append(
                ConsistencyCheckItem(
                    code="unverified_listed_skills",
                    severity="info",
                    message=(
                        f"{len(unverified)} of {len(ev_list)} listed skills ({preview}"
                        f"{'…' if len(unverified) > 5 else ''}) are not evidenced in the CV's "
                        "experience, projects, or credentials—worth exploring hands-on depth in interview."
                    ),
                    evidence={
                        "unverified_count": len(unverified),
                        "total_skills": len(ev_list),
                        "sample_skills": unverified[:8],
                    },
                )
            )

    return items
