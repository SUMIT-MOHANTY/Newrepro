from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.core.database import get_db
from app.core.dependencies import get_current_user
from models import User, AIUsageLog
from tokenops.models import UserTokenWallet, OrganizationWallet, UserOrganization
from tokenops.schemas.superadmin import BaseAPIResponse

router = APIRouter(prefix="/api/tokenops/user", tags=["User TokenOps Transparency"])


@router.get("/my-quota", response_model=BaseAPIResponse)
def get_my_quota(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get personal token allocation, consumed tokens, remaining tokens,
    cost calculations, and recent usage history for the logged-in user in their active organization.
    """
    from sqlalchemy import or_, and_
    from tokenops.services.tenant_resolver_service import TenantResolverService

    org_identifier = getattr(current_user, "organization_name", None)
    if not org_identifier or not org_identifier.strip() or org_identifier == "Default Organization":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="ORGANIZATION_SELECTION_REQUIRED"
        )

    resolver = TenantResolverService(db)
    org_id, org = resolver.resolve(org_identifier)
    canonical_name = org.name

    # Check org PAYG status
    org_wallet = db.query(OrganizationWallet).filter(
        (OrganizationWallet.id == org_id) | (func.lower(OrganizationWallet.organization_name) == canonical_name.lower())
    ).first()
    is_payg = bool(org_wallet.payg_enabled) if org_wallet else False

    # Get user wallet
    user_wallet = db.query(UserTokenWallet).filter(
        UserTokenWallet.user_id == current_user.id,
        (UserTokenWallet.organization_id == org_id) | (func.lower(UserTokenWallet.organization_name) == canonical_name.lower())
    ).first()

    allocated_tokens = user_wallet.allocated_tokens if user_wallet else 0
    consumed_tokens = user_wallet.consumed_tokens if user_wallet else 0
    remaining_tokens = user_wallet.remaining_tokens if user_wallet else 0
    is_blocked = bool(user_wallet.is_blocked) if user_wallet else False

    # Tenant filter: UUID-first with NULL-only legacy fallback
    tenant_filter = or_(
        AIUsageLog.organization_id == org_id,
        and_(
            AIUsageLog.organization_id.is_(None),
            func.lower(AIUsageLog.organization_name) == canonical_name.lower()
        )
    )

    # Calculate total cost from AI usage logs for this user in this active organization
    cost_res = db.query(
        func.sum(AIUsageLog.cost).label("total_cost"),
        func.sum(AIUsageLog.prompt_tokens + AIUsageLog.completion_tokens).label("total_tokens_used")
    ).filter(
        AIUsageLog.user_id == current_user.id,
        tenant_filter
    ).first()

    total_cost = float(cost_res.total_cost or 0.0) if cost_res else 0.0

    # Get recent AI logs for transparency
    recent_logs = db.query(AIUsageLog).filter(
        AIUsageLog.user_id == current_user.id,
        tenant_filter
    ).order_by(AIUsageLog.created_at.desc()).limit(20).all()

    logs_data = [
        {
            "id": log.id,
            "model": log.model or "Default",
            "prompt_tokens": log.prompt_tokens or 0,
            "completion_tokens": log.completion_tokens or 0,
            "total_tokens": (log.prompt_tokens or 0) + (log.completion_tokens or 0),
            "cost": float(log.cost or 0.0),
            "usage_status": log.usage_status or "COMPLETED",
            "created_at": (log.created_at.isoformat() + "Z") if log.created_at else None,
        }
        for log in recent_logs
    ]

    from tokenops.repositories.pricing import PricingRepository
    from tokenops.services.pricing_service import PricingService
    from tokenops.services.user.user_quota_service import UserQuotaService
    from app.core.config import settings
    pricing_repo = PricingRepository(db)
    pricing_service = PricingService(pricing_repo)
    reference_price = float(pricing_service.get_price(settings.ai_model))

    user_quota_service = UserQuotaService(db)
    latest_request = user_quota_service.get_user_latest_request(current_user.id, org_identifier)

    return BaseAPIResponse(
        success=True,
        data={
            "user_id": current_user.id,
            "email": current_user.email,
            "organization_name": canonical_name,
            "organization_id": org_id,
            "is_payg": is_payg,
            "is_blocked": is_blocked,
            "allocated_tokens": allocated_tokens,
            "consumed_tokens": consumed_tokens,
            "remaining_tokens": remaining_tokens,
            "total_cost_usd": round(total_cost, 4),
            "recent_usage": logs_data,
            "reference_price": reference_price,
            "latest_request": latest_request,
        }
    )


from pydantic import BaseModel, Field
from typing import Optional


class CreateUserQuotaRequestBody(BaseModel):
    requested_tokens: int = Field(..., gt=0, description="Quantity of tokens requested")
    reason: Optional[str] = Field(None, max_length=1000, description="Justification / project context")


@router.post("/quota-request", response_model=BaseAPIResponse)
def submit_quota_request(
    body: CreateUserQuotaRequestBody,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Submit a token top-up request to the Organization Admin.
    Enforces the exhaustion guard (can only submit when remaining_tokens <= 0).
    """
    from tokenops.services.user.user_quota_service import UserQuotaService

    org_identifier = getattr(current_user, "organization_name", None)
    if not org_identifier or not org_identifier.strip() or org_identifier == "Default Organization":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="ORGANIZATION_SELECTION_REQUIRED"
        )

    service = UserQuotaService(db)
    req = service.create_request(
        user_id=current_user.id,
        org_identifier=org_identifier,
        requested_tokens=body.requested_tokens,
        reason=body.reason
    )

    return BaseAPIResponse(
        success=True,
        data={
            "id": req.id,
            "requested_tokens": req.requested_tokens,
            "status": req.status,
            "reason": req.reason,
            "created_at": req.created_at.isoformat() if req.created_at else None,
            "message": "Token top-up request submitted successfully. Waiting for Organization Admin review."
        }
    )
