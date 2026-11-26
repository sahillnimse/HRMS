"""Phase 5.3 endpoints: Email templates (admin edits) and preview/send notifications (admin/recruiter)."""

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_role
from app.crud.workflow import (
    build_email_preview,
    create_email_template,
    delete_email_template,
    list_email_templates,
    send_candidate_email,
    update_email_template,
)
from app.models.user import User, UserRole
from app.schemas.workflow import (
    EmailLogResponse,
    EmailPreviewRequest,
    EmailPreviewResponse,
    EmailSendRequest,
    EmailTemplateCreate,
    EmailTemplateResponse,
    EmailTemplateUpdate,
)

email_templates_router = APIRouter()
emails_router = APIRouter()

READ_ROLES = (UserRole.admin, UserRole.recruiter, UserRole.viewer)
WRITE_ROLES = (UserRole.admin, UserRole.recruiter)


@email_templates_router.get("/", response_model=List[EmailTemplateResponse])
async def list_email_templates_endpoint(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(*READ_ROLES)),
):
    return await list_email_templates(db)


@email_templates_router.post(
    "/",
    response_model=EmailTemplateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_email_template_endpoint(
    payload: EmailTemplateCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(UserRole.admin)),
):
    try:
        return await create_email_template(db, payload)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An email template with that key already exists",
        )


@email_templates_router.put("/{template_id}", response_model=EmailTemplateResponse)
async def update_email_template_endpoint(
    template_id: UUID,
    payload: EmailTemplateUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(UserRole.admin)),
):
    updated = await update_email_template(db, template_id, payload)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Email template not found")
    return updated


@email_templates_router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_email_template_endpoint(
    template_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(UserRole.admin)),
):
    ok = await delete_email_template(db, template_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Email template not found")
    return None


@emails_router.post("/preview", response_model=EmailPreviewResponse)
async def preview_email_endpoint(
    payload: EmailPreviewRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(*WRITE_ROLES)),
):
    preview, err = await build_email_preview(
        db,
        candidate_id=payload.candidate_id,
        application_id=payload.application_id,
        template_key=payload.template_key,
        subject_override=payload.subject,
        body_override=payload.body,
        extra_vars=payload.extra_vars,
    )
    if err == "candidate_not_found":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")
    if err == "template_not_found":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Email template not found")
    assert preview is not None
    return preview


@emails_router.post("/send", response_model=EmailLogResponse, status_code=status.HTTP_201_CREATED)
async def send_email_endpoint(
    payload: EmailSendRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*WRITE_ROLES)),
):
    sent, err = await send_candidate_email(db, payload, actor_id=current_user.id)
    if err == "rejection_confirmation_required":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Rejection emails require explicit manual confirmation (`confirm_rejection: true`).",
        )
    if err == "candidate_not_found":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")
    if err == "template_not_found":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Email template not found")
    if err in ("missing_recipient_email", "missing_subject"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err.replace("_", " "))
    assert sent is not None
    return sent
