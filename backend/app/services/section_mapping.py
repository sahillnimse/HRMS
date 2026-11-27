"""
Deterministic CV section mapping helpers:
  - Employment type inference (word-boundary safe: "Internal Tools Engineer" != internship)
  - Education date range & status parsing ("2020-2024", "Aug 2020 - May 2024", "Expected 2025", "Pursuing")
  - Project normalization & capping + deterministic extraction from raw resume text
  - Cross-list skill deduplication using the alias/normalization map
"""

import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

VALID_EMPLOYMENT_TYPES = frozenset(
    {"full_time", "internship", "trainee", "contract", "freelance", "part_time", "unknown"}
)

MAX_PROJECTS = 15
MAX_PROJECT_DESC_CHARS = 500
MAX_PROJECT_TECHS = 20

# Strict word-boundary regexes so e.g. "Internal Tools Engineer" or "International" never match "intern"
_INTERNSHIP_RE = re.compile(
    r"\b(?:intern|interns|internship|co[-\s]?op|summer\s+analyst)\b",
    re.IGNORECASE,
)
_TRAINEE_RE = re.compile(
    r"\b(?:trainee|apprentice|apprenticeship|graduate\s+engineer\s+trainee)\b",
    re.IGNORECASE,
)
_CONTRACT_RE = re.compile(
    r"\b(?:contract|contractor|contractual)\b",
    re.IGNORECASE,
)
_FREELANCE_RE = re.compile(
    r"\b(?:freelance|freelancer|self[-\s]?employed)\b",
    re.IGNORECASE,
)
_PART_TIME_RE = re.compile(
    r"\bpart[-\s]?time\b",
    re.IGNORECASE,
)
_FULL_TIME_RE = re.compile(
    r"\bfull[-\s]?time\b",
    re.IGNORECASE,
)

_PURSUING_RE = re.compile(
    r"\b(?:pursuing|present|current|ongoing|expected|anticipated|in\s+progress|continuing)\b",
    re.IGNORECASE,
)
_YEAR_RE = re.compile(r"\b((?:19|20)\d{2})\b")

_SECTION_HEADING_RE = re.compile(
    r"^\s*(?:projects?|academic\s+projects?|personal\s+projects?|key\s+projects?|selected\s+projects?)\s*:?\s*$",
    re.IGNORECASE,
)
_OTHER_HEADING_RE = re.compile(
    r"^\s*(?:experience|work\s+experience|employment|education|skills|technical\s+skills|"
    r"certifications?|awards?|achievements?|publications?|languages?|interests?|hobbies?|"
    r"summary|profile|objective|references?|volunteer|extra[-\s]?curricular)\s*:?\s*$",
    re.IGNORECASE,
)
_EDU_HEADING_RE = re.compile(
    r"^\s*(?:education|academic\s+background|qualifications?|academics?)\s*:?\s*$",
    re.IGNORECASE,
)


def normalize_employment_type_value(raw: Any) -> str:
    """Coerce common LLM / UI spellings into one of VALID_EMPLOYMENT_TYPES."""
    if not raw or not isinstance(raw, str):
        return "unknown"
    cleaned = re.sub(r"[\s\-]+", "_", raw.strip().lower())
    mapping = {
        "full_time": "full_time",
        "fulltime": "full_time",
        "permanent": "full_time",
        "regular": "full_time",
        "intern": "internship",
        "internship": "internship",
        "co_op": "internship",
        "coop": "internship",
        "trainee": "trainee",
        "apprentice": "trainee",
        "apprenticeship": "trainee",
        "contract": "contract",
        "contractor": "contract",
        "contractual": "contract",
        "freelance": "freelance",
        "freelancer": "freelance",
        "part_time": "part_time",
        "parttime": "part_time",
        "unknown": "unknown",
    }
    return mapping.get(cleaned, "unknown")


def infer_employment_type(
    job_title: str = "",
    company: str = "",
    explicit_type: Optional[str] = None,
) -> str:
    """
    Determine role employment_type.
    Uses an explicit valid non-unknown type when supplied; otherwise infers deterministically
    from job_title and company using strict word boundaries.
    """
    norm_explicit = normalize_employment_type_value(explicit_type)
    if norm_explicit != "unknown":
        return norm_explicit

    combined = f"{job_title or ''} {company or ''}".strip()
    if not combined:
        return "unknown"

    if _INTERNSHIP_RE.search(combined):
        return "internship"
    if _TRAINEE_RE.search(combined):
        return "trainee"
    if _FREELANCE_RE.search(combined):
        return "freelance"
    if _CONTRACT_RE.search(combined):
        return "contract"
    if _PART_TIME_RE.search(combined):
        return "part_time"
    if _FULL_TIME_RE.search(combined):
        return "full_time"
    return "unknown"


def _extract_year(val: Any) -> Optional[int]:
    if val is None or val == "":
        return None
    if isinstance(val, bool):
        return None
    if isinstance(val, int):
        return val if 1950 <= val <= 2040 else None
    m = _YEAR_RE.search(str(val))
    if not m:
        return None
    yr = int(m.group(1))
    return yr if 1950 <= yr <= 2040 else None


def parse_education_dates(
    *,
    start_year: Any = None,
    end_year: Any = None,
    graduation_year: Any = None,
    date_range: Optional[str] = None,
    is_current: Optional[bool] = None,
) -> Tuple[Optional[int], Optional[int], Optional[int], bool]:
    """
    Parse education date fields & free-form range strings ("2020-2024", "Aug 2020 - May 2024",
    "Expected 2025", "Pursuing", "2022 - Present") into:
      (start_year, end_year, graduation_year, is_current).
    """
    raw_texts = [
        str(v)
        for v in (date_range, start_year, end_year, graduation_year)
        if isinstance(v, str) and v.strip()
    ]
    combined_text = " ".join(raw_texts)
    inferred_current = bool(is_current) or bool(_PURSUING_RE.search(combined_text))

    parsed_start = _extract_year(start_year)
    parsed_end = _extract_year(end_year)
    parsed_grad = _extract_year(graduation_year)

    # Check if any string field itself contains a range like "2020–2024" or "Aug 2020 - May 2024"
    for text_val in raw_texts:
        years = [int(y) for y in _YEAR_RE.findall(text_val) if 1950 <= int(y) <= 2040]
        if len(years) >= 2:
            if parsed_start is None:
                parsed_start = years[0]
            if parsed_end is None:
                parsed_end = years[-1]
        elif len(years) == 1:
            if _PURSUING_RE.search(text_val):
                # "Expected 2025" -> expected graduation/end year; "2022 - Present" -> start year
                if re.search(r"\b(?:expected|anticipated|graduating)\b", text_val, re.IGNORECASE):
                    if parsed_end is None:
                        parsed_end = years[0]
                elif re.search(r"[-–—]\s*(?:present|current|pursuing|ongoing|now)", text_val, re.IGNORECASE):
                    if parsed_start is None:
                        parsed_start = years[0]
                elif parsed_grad is None and parsed_end is None:
                    parsed_end = years[0]
            elif parsed_end is None and parsed_grad is None:
                parsed_end = years[0]

    # Synchronize end_year <-> graduation_year for backward compatibility
    if parsed_end is None and parsed_grad is not None:
        parsed_end = parsed_grad
    if parsed_grad is None and parsed_end is not None:
        parsed_grad = parsed_end

    # Guard against reversed years
    if parsed_start is not None and parsed_end is not None and parsed_end < parsed_start:
        parsed_start, parsed_end = parsed_end, parsed_start
        parsed_grad = parsed_end

    return parsed_start, parsed_end, parsed_grad, inferred_current


def normalize_work_experience_list(work_experience: Sequence[Any]) -> List[dict]:
    """Ensure every work_experience entry has a valid inferred `employment_type`."""
    out: List[dict] = []
    for item in work_experience or []:
        if isinstance(item, dict):
            d = dict(item)
        elif hasattr(item, "model_dump"):
            d = item.model_dump()
        else:
            continue
        title = str(d.get("job_title") or "").strip()
        company = str(d.get("company") or "").strip()
        d["employment_type"] = infer_employment_type(
            title, company, d.get("employment_type")
        )
        out.append(d)
    return out


def normalize_education_list(education: Sequence[Any]) -> List[dict]:
    """Normalize education items, keeping graduation_year synced with end_year."""
    out: List[dict] = []
    for item in education or []:
        if isinstance(item, dict):
            d = dict(item)
        elif hasattr(item, "model_dump"):
            d = item.model_dump()
        else:
            continue
        s_yr, e_yr, g_yr, is_curr = parse_education_dates(
            start_year=d.get("start_year"),
            end_year=d.get("end_year"),
            graduation_year=d.get("graduation_year"),
            date_range=d.get("date_range") if isinstance(d.get("date_range"), str) else None,
            is_current=bool(d.get("is_current")) if d.get("is_current") is not None else None,
        )
        d["degree"] = str(d.get("degree") or "").strip()
        d["institution"] = str(d.get("institution") or "").strip()
        fos = d.get("field_of_study")
        d["field_of_study"] = str(fos).strip() if isinstance(fos, str) and fos.strip() else None
        d["start_year"] = s_yr
        d["end_year"] = e_yr
        d["graduation_year"] = g_yr
        d["is_current"] = is_curr
        d.pop("date_range", None)
        out.append(d)
    return out


def normalize_projects_list(projects: Sequence[Any]) -> List[dict]:
    """Normalize and cap projects list (count, description length, technology count)."""
    out: List[dict] = []
    for item in projects or []:
        if len(out) >= MAX_PROJECTS:
            break
        if isinstance(item, dict):
            d = dict(item)
        elif hasattr(item, "model_dump"):
            d = item.model_dump()
        else:
            continue
        name = str(d.get("name") or "").strip()
        desc = str(d.get("description") or "").strip()[:MAX_PROJECT_DESC_CHARS]
        if not name and not desc:
            continue
        raw_techs = d.get("technologies") or []
        if isinstance(raw_techs, str):
            techs = [t.strip() for t in raw_techs.split(",") if t.strip()]
        elif isinstance(raw_techs, list):
            techs = [str(t).strip() for t in raw_techs if t is not None and str(t).strip()]
        else:
            techs = []
        # Deduplicate technologies case-insensitively
        seen_t: set[str] = set()
        clean_techs: List[str] = []
        for t in techs:
            if t.lower() not in seen_t:
                seen_t.add(t.lower())
                clean_techs.append(t)
            if len(clean_techs) >= MAX_PROJECT_TECHS:
                break

        start_d = str(d.get("start_date")).strip() if d.get("start_date") else None
        end_d = str(d.get("end_date")).strip() if d.get("end_date") else None
        out.append(
            {
                "name": name or "Untitled Project",
                "description": desc,
                "technologies": clean_techs,
                "start_date": start_d or None,
                "end_date": end_d or None,
            }
        )
    return out


def _skill_dedup_key(skill: str, alias_map: Dict[str, str]) -> str:
    """Canonical deduplication key folding case, alias map, and hyphen/space/dot variants."""
    raw = (skill or "").strip()
    if not raw:
        return ""
    low = raw.lower()
    if low in alias_map:
        return alias_map[low].lower()
    # Try hyphen/space normalized lookup (e.g. "scikit learn" -> "scikit-learn")
    spaced = re.sub(r"[-_]+", " ", low)
    spaced = re.sub(r"\s+", " ", spaced).strip()
    if spaced in alias_map:
        return alias_map[spaced].lower()
    compact = re.sub(r"[\s\-_]+", "", low)
    for k, canonical in alias_map.items():
        if re.sub(r"[\s\-_]+", "", k) == compact:
            return canonical.lower()
    # Simple plural fold for deduplication (e.g., "REST APIs" vs "REST API")
    if len(spaced) > 4 and spaced.endswith("s") and not spaced.endswith("ss") and not spaced.endswith("js"):
        return spaced[:-1]
    return spaced


def deduplicate_skills_across_lists(
    technical_skills: Sequence[str],
    tools: Sequence[str],
    alias_map: Dict[str, str],
) -> Tuple[List[str], List[str]]:
    """
    Normalize & deduplicate `technical_skills` and `tools` via the alias map and
    simple variant folding (case, hyphen/space, plural), removing cross-list duplicates
    without dropping distinct real skills.
    """
    from app.services.skills import normalize_skill_name

    seen_keys: set[str] = set()
    clean_tech: List[str] = []
    clean_tools: List[str] = []

    for raw in technical_skills or []:
        canonical = normalize_skill_name(str(raw), alias_map)
        if not canonical:
            continue
        key = _skill_dedup_key(canonical, alias_map)
        if key and key not in seen_keys:
            seen_keys.add(key)
            clean_tech.append(canonical)

    for raw in tools or []:
        canonical = normalize_skill_name(str(raw), alias_map)
        if not canonical:
            continue
        key = _skill_dedup_key(canonical, alias_map)
        if key and key not in seen_keys:
            seen_keys.add(key)
            clean_tools.append(canonical)

    return clean_tech, clean_tools


def extract_education_dates_from_text(
    resume_text: str,
    existing_education: Sequence[dict],
) -> List[dict]:
    """
    Deterministically enrich existing education entries with start_year / end_year / is_current
    parsed from the Education section of raw resume text (used by admin re-mapping).
    """
    edu_list = normalize_education_list(existing_education)
    if not resume_text or not edu_list:
        return edu_list

    lines = [ln.strip() for ln in resume_text.splitlines() if ln.strip()]
    edu_lines: List[str] = []
    in_edu = False
    for ln in lines:
        if _EDU_HEADING_RE.match(ln):
            in_edu = True
            continue
        if in_edu and (_OTHER_HEADING_RE.match(ln) or _SECTION_HEADING_RE.match(ln)):
            break
        if in_edu:
            edu_lines.append(ln)

    search_pool = edu_lines if edu_lines else lines

    for edu in edu_list:
        if edu.get("start_year") is not None and edu.get("end_year") is not None:
            continue
        degree_tokens = [
            t.lower()
            for t in re.findall(r"[a-zA-Z0-9.]{2,}", edu.get("degree") or "")
            if t.lower() not in {"in", "of", "and", "the"}
        ]
        inst_tokens = [
            t.lower()
            for t in re.findall(r"[a-zA-Z0-9]{3,}", edu.get("institution") or "")
            if t.lower() not in {"university", "college", "institute", "school", "of", "and", "the"}
        ]
        grad_yr = edu.get("graduation_year")

        best_chunk = ""
        for idx, ln in enumerate(search_pool):
            low = ln.lower()
            score = 0
            if any(tok in low for tok in degree_tokens[:3]):
                score += 2
            if any(tok in low for tok in inst_tokens[:3]):
                score += 2
            if grad_yr and str(grad_yr) in low:
                score += 2
            if score >= 2:
                # Combine current line and immediate neighbor line (often dates are on next line)
                window = " ".join(search_pool[idx : min(len(search_pool), idx + 2)])
                if _YEAR_RE.search(window) or _PURSUING_RE.search(window):
                    best_chunk = window
                    break

        if best_chunk:
            s_yr, e_yr, g_yr, is_curr = parse_education_dates(
                start_year=edu.get("start_year"),
                end_year=edu.get("end_year"),
                graduation_year=edu.get("graduation_year"),
                date_range=best_chunk,
                is_current=edu.get("is_current"),
            )
            edu["start_year"] = s_yr
            edu["end_year"] = e_yr
            edu["graduation_year"] = g_yr
            edu["is_current"] = is_curr

    return edu_list


def extract_projects_from_text(resume_text: str) -> List[dict]:
    """
    Deterministic fallback extractor for a CV's Projects section when re-mapping stored resumes.
    Looks for a `Projects` heading and parses project title lines + bullets until the next section.
    """
    if not resume_text:
        return []

    lines = [ln.rstrip() for ln in resume_text.splitlines()]
    proj_lines: List[str] = []
    in_proj = False
    for ln in lines:
        stripped = ln.strip()
        if not stripped:
            if in_proj:
                proj_lines.append("")
            continue
        if _SECTION_HEADING_RE.match(stripped):
            in_proj = True
            continue
        if in_proj and _OTHER_HEADING_RE.match(stripped):
            break
        if in_proj:
            proj_lines.append(stripped)

    if not proj_lines:
        return []

    projects: List[dict] = []
    current_name = ""
    current_desc_parts: List[str] = []
    current_techs: List[str] = []

    def _flush() -> None:
        nonlocal current_name, current_desc_parts, current_techs
        if current_name or current_desc_parts:
            projects.append(
                {
                    "name": current_name or "Project",
                    "description": " ".join(current_desc_parts).strip()[:MAX_PROJECT_DESC_CHARS],
                    "technologies": current_techs,
                    "start_date": None,
                    "end_date": None,
                }
            )
        current_name = ""
        current_desc_parts = []
        current_techs = []

    bullet_prefix_re = re.compile(r"^[\-\*•▪◦‣–—]\s+")
    tech_label_re = re.compile(
        r"^(?:tech(?:nologies)?|stack|tools?|built\s+with)\s*:\s*(.+)$",
        re.IGNORECASE,
    )

    for ln in proj_lines:
        if not ln:
            if current_name and current_desc_parts:
                _flush()
            continue
        m_tech = tech_label_re.match(ln)
        if m_tech:
            current_techs.extend(
                [t.strip() for t in re.split(r"[,|•/]", m_tech.group(1)) if t.strip()]
            )
            continue
        if bullet_prefix_re.match(ln):
            body = bullet_prefix_re.sub("", ln).strip()
            if not current_name:
                current_name = body[:80]
            else:
                current_desc_parts.append(body)
        else:
            if current_name and current_desc_parts:
                _flush()
            if not current_name:
                # Split "Project Name | Python, React" if pipe-delimited
                if "|" in ln:
                    parts = [p.strip() for p in ln.split("|", 1)]
                    current_name = parts[0][:100]
                    if len(parts) > 1 and parts[1]:
                        current_techs.extend(
                            [t.strip() for t in parts[1].split(",") if t.strip()]
                        )
                else:
                    current_name = ln[:100]
            else:
                current_desc_parts.append(ln)

    _flush()
    return normalize_projects_list(projects)
