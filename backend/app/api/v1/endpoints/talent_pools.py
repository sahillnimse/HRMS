"""Talent Pools & Tags endpoints (`/api/v1/talent-pools`)."""

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_role
from app.crud.backlog import (
    add_candidate_to_pool,
    create_talent_pool,
    delete_talent_pool,
    list_pool_members,
    list_talent_pools,
    remove_candidate_from_pool,
)
from app.models.user import User, UserRole
from app.schemas.backlog import (
    TalentPoolCreate,
    TalentPoolMemberAdd,
    TalentPoolMemberItem,
    TalentPoolResponse,
)

router = APIRouter()

READ_ROLES = (UserRole.admin, UserRole.recruiter, UserRole.viewer)
WRITE_ROLES = (UserRole.admin, UserRole.recruiter)


@router.get("/", response_model=List[TalentPoolResponse])
async def list_talent_pools_endpoint(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(*READ_ROLES)),
):
    return await list_talent_pools(db)


@router.post("/", response_model=TalentPoolResponse, status_code=status.HTTP_201_CREATED)
async def create_talent_pool_endpoint(
    payload: TalentPoolCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*WRITE_ROLES)),
):
    try:
        return await create_talent_pool(db, payload, actor_id=current_user.id)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A talent pool with that name already exists",
        )


@router.delete("/{pool_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_talent_pool_endpoint(
    pool_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(*WRITE_ROLES)),
):
    ok = await delete_talent_pool(db, pool_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Talent pool not found")
    return None


@router.get("/{pool_id}/members", response_model=List[TalentPoolMemberItem])
async def list_pool_members_endpoint(
    pool_id: UUID,
    blind: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(*READ_ROLES)),
):
    members = await list_pool_members(db, pool_id, blind=blind)
    if members is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Talent pool not found")
    return members


@router.post("/{pool_id}/members", status_code=status.HTTP_201_CREATED)
async def add_pool_member_endpoint(
    pool_id: UUID,
    payload: TalentPoolMemberAdd,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*WRITE_ROLES)),
):
    ok, err = await add_candidate_to_pool(
        db, pool_id, payload.candidate_id, notes=payload.notes, actor_id=current_user.id
    )
    if err == "pool_not_found":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Talent pool not found")
    if err == "candidate_not_found":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")
    return {"status": "added", "pool_id": str(pool_id), "candidate_id": str(payload.candidate_id)}


@router.delete("/{pool_id}/members/{candidate_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_pool_member_endpoint(
    pool_id: UUID,
    candidate_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(*WRITE_ROLES)),
):
    ok = await remove_candidate_from_pool(db, pool_id, candidate_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pool membership not found")
    return None
