"""
CLI command for admin re-mapping of existing candidates' CV sections
(education dates, work employment_type, and projects).

Dry-run by default:
    python -m app.scripts.remap_sections
Apply changes:
    python -m app.scripts.remap_sections --apply --limit 200
"""

import argparse
import asyncio
from typing import Optional
from uuid import UUID

from app.db.session import AsyncSessionLocal, engine
from app.services.remap import remap_candidate_sections


async def _run(dry_run: bool, candidate_id: Optional[UUID], limit: int) -> None:
    try:
        async with AsyncSessionLocal() as db:
            res = await remap_candidate_sections(
                db,
                dry_run=dry_run,
                candidate_id=candidate_id,
                limit=limit,
            )
        mode = "DRY-RUN" if res.dry_run else "APPLIED"
        print(
            f"[{mode}] scanned={res.scanned} would_update={res.would_update} "
            f"updated={res.updated} skipped_hand_edited={res.skipped_hand_edited}"
        )
        for item in res.results:
            if item.updated_fields or item.skipped_hand_edited_fields:
                print(
                    f"  - candidate={item.candidate_id} source={item.source_used} "
                    f"fields={item.updated_fields} skipped={item.skipped_hand_edited_fields}"
                )
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Re-map existing candidates' education dates, employment_type, and projects."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write changes to the database (default is dry-run).",
    )
    parser.add_argument(
        "--candidate-id",
        type=str,
        default=None,
        help="Optional single candidate UUID to process.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Maximum number of candidates to scan (default 100, max 500).",
    )
    args = parser.parse_args()
    cid = UUID(args.candidate_id) if args.candidate_id else None
    asyncio.run(_run(dry_run=not args.apply, candidate_id=cid, limit=args.limit))


if __name__ == "__main__":
    main()
