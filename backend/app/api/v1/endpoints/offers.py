"""Phase 5.4 endpoints: Offers management (admin / recruiter ONLY)."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_role
from app.crud.workflow import delete_offer, update_offer
from app.models.user import User, UserRole
from app.schemas.workflow import OfferResponse, OfferUpdate

router = APIRouter()

WRITE_ROLES = (UserRole.admin, UserRole.recruiter)


@router.patch("/{offer_id}", response_model=OfferResponse)
async def update_offer_endpoint(
    offer_id: UUID,
    payload: OfferUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*WRITE_ROLES)),
):
    updated = await update_offer(db, offer_id, payload, actor_id=current_user.id)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Offer not found")
    return updated


@router.delete("/{offer_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_offer_endpoint(
    offer_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*WRITE_ROLES)),
):
    ok = await delete_offer(db, offer_id, actor_id=current_user.id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Offer not found")
    return None
