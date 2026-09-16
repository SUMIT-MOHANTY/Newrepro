from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field
from typing import Optional, List
from sqlalchemy.orm import Session

from database import get_db
from models import User
from tokenops.schemas.superadmin import BaseAPIResponse
from tokenops.services.user.user_quota_service import UserQuotaService
from .dependencies import verify_org_admin

router = APIRouter(tags=["Org Admin Member Quota Requests"])


class ReviewUserRequestBody(BaseModel):
    action: str = Field(..., description="'APPROVE' or 'REJECT'")
    approved_tokens: Optional[int] = Field(None, gt=0, description="Override token amount to allocate (optional)")
    admin_notes: Optional[str] = Field(None, max_length=1000, description="Notes or justification for decision")


@router.get("", response_model=BaseAPIResponse)
def get_user_quota_requests(
    status: Optional[str] = Query(None, description="Filter by status: 'PENDING', 'APPROVED', 'REJECTED', or 'ALL'"),
    current_user: User = Depends(verify_org_admin),
    db: Session = Depends(get_db),
):
    """
    List all member token quota top-up requests for the active organization.
    """
    org_name = current_user.active_organization
    service = UserQuotaService(db)
    requests = service.get_org_requests(org_name, status_filter=status)

    return BaseAPIResponse(
        success=True,
        data=requests
    )


@router.post("/{request_id}/review", response_model=BaseAPIResponse)
def review_user_quota_request(
    request_id: int,
    body: ReviewUserRequestBody,
    current_user: User = Depends(verify_org_admin),
    db: Session = Depends(get_db),
):
    """
    Approve or Reject a member token quota top-up request.
    Upon approval, tokens are automatically transferred from the organization reserve to the user wallet.
    """
    org_name = current_user.active_organization
    service = UserQuotaService(db)
    result = service.review_request(
        request_id=request_id,
        admin_user_id=current_user.id,
        org_identifier=org_name,
        action=body.action,
        approved_tokens=body.approved_tokens,
        admin_notes=body.admin_notes
    )

    return BaseAPIResponse(
        success=True,
        data=result
    )
