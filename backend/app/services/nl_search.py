"""
Natural-Language Candidate Search parser:
Converts queries like "Python, 3+ yrs, Pune, notice < 30 days" into structured filters
using Gemini structured output (behind `ENABLE_NL_SEARCH`) with a fast deterministic regex
parser fallback so it works cleanly offline or without an AI key.
"""

import asyncio
import json
import logging
import re
from typing import Dict, List, Optional, Tuple

from google import genai
from google.genai import types
import requests

from app.core.config import settings
from app.schemas.backlog import ParsedNLFilters
from app.services.gemini_parser import OPENROUTER_URL, _extract_json_object
from app.services.skills import normalize_skill_list

logger = logging.getLogger(__name__)

_NL_SYSTEM_PROMPT = """Convert an HR recruiter's natural-language candidate search query into structured JSON filters:
{
  "skills": ["canonical technical skills or tools explicitly mentioned"],
  "min_years": null,
  "max_years": null,
  "city": null,
  "max_notice_days": null,
  "primary_domain": null,
  "semantic_query": "remaining role/domain keywords for semantic ranking (empty string if purely structured filters)"
}

Rules:
- Extract ONLY filters explicitly stated in the query. Never invent filters.
- "immediate joiner" -> max_notice_days: 15. "notice < 30 days" or "30 days notice" -> max_notice_days: 30.
- "3+ yrs" -> min_years: 3.0. "2-5 years" -> min_years: 2.0, max_years: 5.0.
- Return ONLY raw JSON."""

_COMMON_CITIES = (
    "pune", "mumbai", "bangalore", "bengaluru", "hyderabad", "delhi", "new delhi",
    "noida", "gurgaon", "gurugram", "chennai", "kolkata", "ahmedabad", "jaipur",
    "indore", "kochi", "chandigarh", "remote", "san francisco", "new york",
    "london", "singapore", "dubai", "toronto", "berlin", "austin", "seattle",
)

_DOMAIN_KEYWORDS = {
    "data science": "Data Science",
    "machine learning": "Data Science",
    "devops": "Software Engineering",
    "frontend": "Software Engineering",
    "backend": "Software Engineering",
    "full stack": "Software Engineering",
    "fullstack": "Software Engineering",
    "product manager": "Product Management",
    "product management": "Product Management",
    "ui/ux": "Design",
    "product design": "Design",
    "marketing": "Digital Marketing",
    "finance": "Finance",
    "sales": "Sales",
}


def parse_nl_query_deterministic(
    query: str,
    alias_map: Optional[Dict[str, str]] = None,
) -> ParsedNLFilters:
    """Fast deterministic parser for structured HR search syntax."""
    raw = (query or "").strip()
    low = raw.lower()
    remaining = raw

    min_years: Optional[float] = None
    max_years: Optional[float] = None
    max_notice_days: Optional[int] = None
    city: Optional[str] = None
    primary_domain: Optional[str] = None

    # 1. Experience range: "2-5 yrs", "2 to 5 years"
    m_range = re.search(
        r"\b(\d+(?:\.\d+)?)\s*(?:-|–|to)\s*(\d+(?:\.\d+)?)\s*(?:\+?\s*)?(?:yrs?|years?)\b",
        low,
    )
    if m_range:
        min_years = float(m_range.group(1))
        max_years = float(m_range.group(2))
        remaining = re.sub(re.escape(m_range.group(0)), " ", remaining, flags=re.IGNORECASE)
    else:
        # "3+ yrs", ">= 3 years", "at least 4 yrs", "min 3 years"
        m_min = re.search(
            r"(?:(?:>=|at\s+least|min(?:imum)?)\s*(\d+(?:\.\d+)?)\s*(?:yrs?|years?)|(\d+(?:\.\d+)?)\s*\+\s*(?:yrs?|years?))",
            low,
        )
        if m_min:
            val = m_min.group(1) or m_min.group(2)
            min_years = float(val)
            remaining = re.sub(re.escape(m_min.group(0)), " ", remaining, flags=re.IGNORECASE)

        # "< 5 yrs", "under 4 years", "max 6 yrs"
        m_max = re.search(
            r"(?:<=|<|under|below|max(?:imum)?|up\s+to)\s*(\d+(?:\.\d+)?)\s*(?:yrs?|years?)",
            low,
        )
        if m_max:
            max_years = float(m_max.group(1))
            remaining = re.sub(re.escape(m_max.group(0)), " ", remaining, flags=re.IGNORECASE)

    # 2. Notice period: "notice < 30 days", "notice <= 45d", "30 days notice", "immediate joiner"
    if re.search(r"\bimmediate(?:\s+joiner)?\b", low):
        max_notice_days = 15
        remaining = re.sub(r"\bimmediate(?:\s+joiner)?\b", " ", remaining, flags=re.IGNORECASE)
    else:
        m_notice = re.search(
            r"\bnotice(?:\s+period)?\s*(?:<=|<|under|within|max)?\s*(\d+)\s*(?:days?|d)?\b"
            r"|\b(\d+)\s*(?:days?|d)\s*notice\b",
            low,
        )
        if m_notice:
            val = m_notice.group(1) or m_notice.group(2)
            max_notice_days = int(val)
            remaining = re.sub(re.escape(m_notice.group(0)), " ", remaining, flags=re.IGNORECASE)

    # 3. City: explicit "in <City>" or known city names
    for c_name in sorted(_COMMON_CITIES, key=len, reverse=True):
        pat = rf"\b(?:in\s+|from\s+|based\s+in\s+)?{re.escape(c_name)}\b"
        m_city = re.search(pat, remaining, flags=re.IGNORECASE)
        if m_city:
            city = "Bangalore" if c_name == "bengaluru" else c_name.title()
            remaining = re.sub(pat, " ", remaining, count=1, flags=re.IGNORECASE)
            break

    # 4. Skills via alias_map + common tech tokens (canonical display casing)
    amap = alias_map or {}
    default_canonical = {
        "python": "Python",
        "fastapi": "FastAPI",
        "django": "Django",
        "flask": "Flask",
        "react": "React",
        "typescript": "TypeScript",
        "javascript": "JavaScript",
        "node.js": "Node.js",
        "nodejs": "Node.js",
        "postgresql": "PostgreSQL",
        "postgres": "PostgreSQL",
        "sql": "SQL",
        "mongodb": "MongoDB",
        "redis": "Redis",
        "docker": "Docker",
        "kubernetes": "Kubernetes",
        "k8s": "Kubernetes",
        "aws": "AWS",
        "gcp": "GCP",
        "azure": "Azure",
        "pytorch": "PyTorch",
        "tensorflow": "TensorFlow",
        "machine learning": "Machine Learning",
        "ml": "Machine Learning",
        "deep learning": "Deep Learning",
        "java": "Java",
        "spring boot": "Spring Boot",
        "go": "Go",
        "golang": "Go",
        "rust": "Rust",
        "c++": "C++",
        "figma": "Figma",
        "graphql": "GraphQL",
        "tailwind": "Tailwind CSS",
        "next.js": "Next.js",
        "nextjs": "Next.js",
        "git": "Git",
    }
    combined_map = {**default_canonical, **amap}
    candidate_vocab = set(combined_map.keys())
    found_skills: List[str] = []
    for term in sorted(candidate_vocab, key=len, reverse=True):
        if len(term) < 2:
            continue
        pat = rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])"
        if re.search(pat, remaining, flags=re.IGNORECASE):
            found_skills.append(combined_map.get(term, term))
            remaining = re.sub(pat, " ", remaining, flags=re.IGNORECASE)

    norm_skills = normalize_skill_list(found_skills, combined_map)

    # 5. Primary domain hint (only if explicitly matched)
    for kw, dom in _DOMAIN_KEYWORDS.items():
        if re.search(rf"\b{re.escape(kw)}\b", low):
            primary_domain = dom
            break

    # Clean up remaining free-text semantic query
    sem_clean = re.sub(r"[,;/|]+", " ", remaining)
    sem_clean = re.sub(r"\b(?:with|and|or|in|for|who|knows|having|experience|exp)\b", " ", sem_clean, flags=re.IGNORECASE)
    sem_clean = re.sub(r"\s+", " ", sem_clean).strip()

    return ParsedNLFilters(
        skills=norm_skills,
        min_years=min_years,
        max_years=max_years,
        city=city,
        max_notice_days=max_notice_days,
        primary_domain=primary_domain,
        semantic_query=sem_clean,
    )


async def parse_nl_search_query(
    query: str,
    alias_map: Optional[Dict[str, str]] = None,
) -> Tuple[ParsedNLFilters, str]:
    """Parse NL query with Gemini when enabled, falling back cleanly to deterministic parser."""
    det = parse_nl_query_deterministic(query, alias_map=alias_map)
    if not settings.ENABLE_NL_SEARCH:
        return det, "deterministic"
    api_key = (settings.GEMINI_API_KEY or "").strip()
    if not api_key:
        return det, "deterministic"

    model_name = (settings.GEMINI_MODEL or "gemini-2.0-flash").strip()
    use_openrouter = api_key.startswith("sk-or-") or "/" in model_name

    try:
        if use_openrouter:
            def _call_or() -> str:
                resp = requests.post(
                    OPENROUTER_URL,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model_name,
                        "temperature": 0.0,
                        "max_tokens": 260,
                        "messages": [
                            {"role": "system", "content": _NL_SYSTEM_PROMPT},
                            {"role": "user", "content": query},
                        ],
                    },
                    timeout=12,
                )
                resp.raise_for_status()
                return str(
                    (resp.json().get("choices") or [{}])[0].get("message", {}).get("content", "")
                )

            raw = await asyncio.wait_for(asyncio.to_thread(_call_or), timeout=14)
        else:
            client = genai.Client(api_key=api_key)
            resp = await asyncio.wait_for(
                client.aio.models.generate_content(
                    model=model_name,
                    contents=[
                        types.Content(
                            role="user",
                            parts=[types.Part.from_text(text=f"{_NL_SYSTEM_PROMPT}\n\nQuery: {query}")],
                        )
                    ],
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=ParsedNLFilters,
                        temperature=0.0,
                    ),
                ),
                timeout=12,
            )
            raw = resp.text or "{}"

        parsed = ParsedNLFilters(**_extract_json_object(raw))
        parsed.skills = normalize_skill_list(parsed.skills, alias_map or {})
        return parsed, model_name
    except Exception:
        logger.warning("AI NL search parse failed; using deterministic parser", exc_info=True)
        return det, "deterministic"
