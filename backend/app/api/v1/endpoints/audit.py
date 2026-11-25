"""Admin-only audit log query endpoint."""

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_role
from app.crud.pipeline import list_audit_logs
from app.models.user import User, UserRole
from app.schemas.pipeline import AuditLogResponse

router = APIRouter()


@router.get("/", response_model=List[AuditLogResponse])
async def get_audit_logs(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(UserRole.admin)),
    entity: Optional[str] = Query(None),
    entity_id: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    user_id: Optional[UUID] = Query(None),
    limit: int = Query(100, ge=1, le=500),
):
    """Admin-only: inspect audit trail entries."""
    return await list_audit_logs(
        db,
        entity=entity,
        entity_id=entity_id,
        action=action,
        user_id=user_id,
        limit=limit,
    )
