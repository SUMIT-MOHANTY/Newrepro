from fastapi import APIRouter, Depends, Query
from tokenops.schemas.orgadmin import BaseAPIResponse
from tokenops.services.org_admin.org_wallet_service import OrgWalletService
from .dependencies import verify_org_admin, get_org_wallet_service
from models import User

router = APIRouter(tags=["Org Admin Users"])

@router.get("/", response_model=BaseAPIResponse)
def get_users(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=100),
    search: str = None,
    current_user: User = Depends(verify_org_admin),
    wallet_service: OrgWalletService = Depends(get_org_wallet_service)
):
    try:
        data = wallet_service.get_users(
            organization_name=current_user.active_organization,
            page=page, 
            size=size, 
            search=search
        )
        return BaseAPIResponse(success=True, data=data)
    except Exception as e:
        return BaseAPIResponse(success=False, error={"code": "UNKNOWN_ERROR", "message": str(e)})

@router.get("/{user_id}", response_model=BaseAPIResponse)
def get_user_wallet(
    user_id: int,
    current_user: User = Depends(verify_org_admin),
    wallet_service: OrgWalletService = Depends(get_org_wallet_service)
):
    try:
        data = wallet_service.get_user(
            organization_name=current_user.active_organization,
            user_id=user_id
        )
        if not data:
            return BaseAPIResponse(success=False, error={"code": "NOT_FOUND", "message": "User wallet not found"})
        return BaseAPIResponse(success=True, data=data)
    except Exception as e:
        return BaseAPIResponse(success=False, error={"code": "UNKNOWN_ERROR", "message": str(e)})
