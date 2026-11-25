"""Gemini embeddings & pgvector helpers behind the ENABLE_SEMANTIC_SEARCH feature flag."""

import logging
import math
from typing import Any, List, Optional, Sequence
from uuid import UUID

from google import genai
from google.genai import types
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings

logger = logging.getLogger(__name__)


def build_candidate_embedding_text(
    *,
    primary_domain: str,
    profile_summary: str,
    technical_skills: Sequence[str],
    tools: Sequence[str],
    work_experience: Sequence[Any],
) -> str:
    """Build a PII-free, CTC-free semantic representation of a candidate."""
    titles: List[str] = []
    for item in work_experience or []:
        if isinstance(item, dict):
            title = str(item.get("job_title") or "").strip()
            company = str(item.get("company") or "").strip()
            if title or company:
                titles.append(f"{title} at {company}".strip(" at"))
    parts = [
        f"Domain: {primary_domain}" if primary_domain else "",
        f"Roles: {'; '.join(titles)}" if titles else "",
        f"Technical Skills: {', '.join(technical_skills)}" if technical_skills else "",
        f"Tools: {', '.join(tools)}" if tools else "",
        f"Summary: {profile_summary}" if profile_summary else "",
    ]
    return "\n".join(p for p in parts if p).strip()


def build_job_embedding_text(
    *,
    title: str,
    department: str,
    description: str,
    required_skills: Sequence[str],
    nice_to_have_skills: Sequence[str],
) -> str:
    parts = [
        f"Job Title: {title}" if title else "",
        f"Department: {department}" if department else "",
        f"Required Skills: {', '.join(required_skills)}" if required_skills else "",
        f"Nice to Have: {', '.join(nice_to_have_skills)}" if nice_to_have_skills else "",
        f"Description: {description}" if description else "",
    ]
    return "\n".join(p for p in parts if p).strip()


async def generate_embedding(input_text: str) -> Optional[List[float]]:
    """
    Generate a Gemini embedding vector when ENABLE_SEMANTIC_SEARCH is True and a
    Google Gemini API key is configured. Returns None gracefully otherwise.
    """
    if not settings.ENABLE_SEMANTIC_SEARCH:
        return None
    cleaned = (input_text or "").strip()
    if not cleaned:
        return None
    api_key = (settings.GEMINI_API_KEY or "").strip()
    # OpenRouter sk-or- keys do not work with Google Gemini's embed_content API
    if not api_key or api_key.startswith("sk-or-"):
        return None

    try:
        client = genai.Client(api_key=api_key)
        response = await client.aio.models.embed_content(
            model=settings.EMBEDDING_MODEL,
            contents=cleaned[:8000],
            config=types.EmbedContentConfig(output_dimensionality=settings.EMBEDDING_DIMENSIONS),
        )
        embeddings = getattr(response, "embeddings", None)
        if not embeddings:
            return None
        values = getattr(embeddings[0], "values", None)
        if not values:
            return None
        return [float(x) for x in values]
    except Exception:
        logger.warning("Gemini embedding generation skipped due to error", exc_info=True)
        return None


def cosine_similarity(a: Optional[Sequence[float]], b: Optional[Sequence[float]]) -> float:
    """Compute cosine similarity in [0.0, 1.0] between two equal-length vectors."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for x, y in zip(a, b):
        dot += x * y
        norm_a += x * x
        norm_b += y * y
    denom = math.sqrt(norm_a) * math.sqrt(norm_b)
    if denom <= 0.0:
        return 0.0
    return max(0.0, min(1.0, dot / denom))


async def has_pgvector_column(db: AsyncSession) -> bool:
    """Return True if the `candidates.embedding` pgvector column exists in this database."""
    if not settings.ENABLE_SEMANTIC_SEARCH:
        return False
    res = await db.execute(
        text(
            "SELECT EXISTS ("
            "  SELECT 1 FROM information_schema.columns "
            "  WHERE table_name = 'candidates' AND column_name = 'embedding'"
            ")"
        )
    )
    return bool(res.scalar_one())


async def sync_candidate_pgvector(
    db: AsyncSession,
    candidate_id: UUID,
    vec: Optional[Sequence[float]],
) -> None:
    """Update the native pgvector `embedding` column when pgvector is enabled."""
    if not vec or not await has_pgvector_column(db):
        return
    if len(vec) != settings.EMBEDDING_DIMENSIONS:
        return
    vec_literal = "[" + ",".join(f"{float(v):.6f}" for v in vec) + "]"
    await db.execute(
        text("UPDATE candidates SET embedding = CAST(:vec AS vector) WHERE id = :cid"),
        {"vec": vec_literal, "cid": candidate_id},
    )
