from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from database import get_db
from auth import get_current_user
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
    cost calculations, and recent usage history for the logged-in user.
    """
    org_name = current_user.organization_name or "Default Organization"

    # Check org PAYG status
    org_wallet = db.query(OrganizationWallet).filter(
        OrganizationWallet.organization_name == org_name
    ).first()
    is_payg = bool(org_wallet.payg_enabled) if org_wallet else False

    # Get user wallet
    user_wallet = db.query(UserTokenWallet).filter(
        UserTokenWallet.user_id == current_user.id,
        UserTokenWallet.organization_name == org_name
    ).first()

    allocated_tokens = user_wallet.allocated_tokens if user_wallet else 0
    consumed_tokens = user_wallet.consumed_tokens if user_wallet else 0
    remaining_tokens = user_wallet.remaining_tokens if user_wallet else 0
    is_blocked = bool(user_wallet.is_blocked) if user_wallet else False

    # Calculate total cost from AI usage logs
    cost_res = db.query(
        func.sum(AIUsageLog.cost).label("total_cost"),
        func.sum(AIUsageLog.prompt_tokens + AIUsageLog.completion_tokens).label("total_tokens_used")
    ).filter(
        AIUsageLog.user_id == current_user.id
    ).first()

    total_cost = float(cost_res.total_cost or 0.0) if cost_res else 0.0

    # Get recent AI logs for transparency
    recent_logs = db.query(AIUsageLog).filter(
        AIUsageLog.user_id == current_user.id
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
            "created_at": log.created_at.isoformat() if log.created_at else None,
        }
        for log in recent_logs
    ]

    from tokenops.repositories.pricing import PricingRepository
    from tokenops.services.pricing_service import PricingService
    from config import settings
    pricing_repo = PricingRepository(db)
    pricing_service = PricingService(pricing_repo)
    reference_price = float(pricing_service.get_price(settings.ai_model))

    return BaseAPIResponse(
        success=True,
        data={
            "user_id": current_user.id,
            "email": current_user.email,
            "organization_name": org_name,
            "is_payg": is_payg,
            "is_blocked": is_blocked,
            "allocated_tokens": allocated_tokens,
            "consumed_tokens": consumed_tokens,
            "remaining_tokens": remaining_tokens,
            "total_cost_usd": round(total_cost, 4),
            "recent_usage": logs_data,
            "reference_price": reference_price,
        }
    )
