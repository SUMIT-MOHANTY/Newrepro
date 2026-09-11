from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from typing import Optional
from sqlalchemy.orm import Session
from database import get_db
from models import User
from tokenops.models.quota_request import TokenQuotaRequest, QuotaRequestType, QuotaRequestStatus
from tokenops.services.tenant_resolver_service import TenantResolverService
from tokenops.schemas.superadmin import BaseAPIResponse
from .dependencies import verify_org_admin

router = APIRouter(tags=["Org Admin Quota Requests"])


class CreateQuotaRequestBody(BaseModel):
    request_type: str = Field("TOKEN_INCREASE", description="'TOKEN_INCREASE', 'PAYG_ENABLEMENT', 'LIMIT_INCREASE', or 'PAYG_DISABLEMENT'")
    requested_tokens: int = Field(0, ge=0, description="Requested token amount (for TOKEN_INCREASE)")
    requested_limit_usd: Optional[float] = Field(None, ge=0.0, description="Requested dollar spending limit (for LIMIT_INCREASE)")
    remarks: Optional[str] = Field(None, description="Reason or justification for the quota request")


@router.post("/request-quota", response_model=BaseAPIResponse)
def submit_quota_request(
    body: CreateQuotaRequestBody,
    current_user: User = Depends(verify_org_admin),
    db: Session = Depends(get_db),
):
    """
    Submit a Token Increase, PAYG Enablement, PAYG Limit Increase, or PAYG Disablement request from Org Admin to Super Admin.
    """
    user: User = current_user
    org_name = current_user.active_organization

    req_type = body.request_type.upper()
    if req_type not in ["TOKEN_INCREASE", "PAYG_ENABLEMENT", "LIMIT_INCREASE", "PAYG_DISABLEMENT"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid request_type. Must be 'TOKEN_INCREASE', 'PAYG_ENABLEMENT', 'LIMIT_INCREASE', or 'PAYG_DISABLEMENT'."
        )

    if req_type == "TOKEN_INCREASE" and body.requested_tokens <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="requested_tokens must be greater than 0 for TOKEN_INCREASE."
        )

    if req_type == "LIMIT_INCREASE" and (body.requested_limit_usd is None or body.requested_limit_usd <= 0):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="requested_limit_usd must be greater than 0 for LIMIT_INCREASE."
        )

    # Resolve organization_id
    resolver = TenantResolverService(db)
    org_id, org = resolver.resolve(org_name)

    from decimal import Decimal
    quota_req = TokenQuotaRequest(
        organization_name=org.name,
        organization_id=org_id,
        request_type=QuotaRequestType[req_type],
        requested_tokens=body.requested_tokens if req_type == "TOKEN_INCREASE" else 0,
        requested_limit_usd=Decimal(str(round(body.requested_limit_usd, 2))) if req_type == "LIMIT_INCREASE" and body.requested_limit_usd else None,
        requested_by=user.id,
        status=QuotaRequestStatus.REQUESTED,
        remarks=body.remarks,
    )
    db.add(quota_req)
    db.commit()
    db.refresh(quota_req)

    return BaseAPIResponse(
        success=True,
        data={
            "id": quota_req.id,
            "organization_name": quota_req.organization_name,
            "request_type": quota_req.request_type.value,
            "requested_tokens": quota_req.requested_tokens,
            "requested_limit_usd": float(quota_req.requested_limit_usd) if quota_req.requested_limit_usd else None,
            "status": quota_req.status.value,
            "created_at": quota_req.created_at.isoformat(),
        }
    )


@router.get("/quota-requests", response_model=BaseAPIResponse)
def get_my_org_quota_requests(
    current_user: User = Depends(verify_org_admin),
    db: Session = Depends(get_db),
):
    """
    Get all quota / PAYG requests submitted by this organization.
    """
    org_name = current_user.active_organization
    resolver = TenantResolverService(db)
    org_id, org = resolver.resolve(org_name)

    requests = db.query(TokenQuotaRequest).filter(
        (TokenQuotaRequest.organization_id == org_id) | (TokenQuotaRequest.organization_name == org.name)
    ).order_by(TokenQuotaRequest.created_at.desc()).all()

    total = len(requests)
    data = [
        {
            "id": r.id,
            "request_number": total - idx,
            "organization_name": r.organization_name,
            "request_type": r.request_type.value if hasattr(r.request_type, "value") else str(r.request_type),
            "requested_tokens": r.requested_tokens,
            "requested_limit_usd": float(r.requested_limit_usd) if r.requested_limit_usd else None,
            "status": r.status.value if hasattr(r.status, "value") else str(r.status),
            "remarks": r.remarks,
            "admin_notes": r.admin_notes,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "approved_at": r.approved_at.isoformat() if r.approved_at else None,
        }
        for idx, r in enumerate(requests)
    ]
    return BaseAPIResponse(success=True, data=data)
