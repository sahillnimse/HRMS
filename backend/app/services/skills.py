"""Skill normalization helpers backed by the `skill_normalizations` table."""

from typing import Dict, List, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.matching import SkillNormalization


async def load_skill_alias_map(db: AsyncSession) -> Dict[str, str]:
    """Build a lowercase lookup dict mapping every alias and canonical name -> canonical_name."""
    rows = (await db.execute(select(SkillNormalization))).scalars().all()
    alias_map: Dict[str, str] = {}
    for row in rows:
        canonical = (row.canonical_name or "").strip()
        if not canonical:
            continue
        alias_map[canonical.lower()] = canonical
        for alias in row.aliases or []:
            cleaned = str(alias).strip()
            if cleaned:
                alias_map[cleaned.lower()] = canonical
    return alias_map


def normalize_skill_name(skill: str, alias_map: Dict[str, str]) -> str:
    """Resolve a single skill string to its canonical form if registered."""
    cleaned = (skill or "").strip()
    if not cleaned:
        return ""
    return alias_map.get(cleaned.lower(), cleaned)


def normalize_skill_list(skills: Sequence[str], alias_map: Dict[str, str]) -> List[str]:
    """Normalize and deduplicate a list of skills (case-insensitive), preserving order."""
    seen: set[str] = set()
    out: List[str] = []
    for raw in skills or []:
        canonical = normalize_skill_name(str(raw), alias_map)
        if not canonical:
            continue
        key = canonical.lower()
        if key not in seen:
            seen.add(key)
            out.append(canonical)
    return out
