from fastapi import APIRouter, Depends
from tokenops.schemas.orgadmin import BaseAPIResponse
from tokenops.services.org_admin.org_wallet_service import OrgWalletService
from .dependencies import verify_org_admin, get_org_wallet_service
from models import User

router = APIRouter(tags=["Org Admin Reserve"])

@router.get("", response_model=BaseAPIResponse)
@router.get("/", response_model=BaseAPIResponse, include_in_schema=False)
def get_reserve(
    current_user: User = Depends(verify_org_admin),
    wallet_service: OrgWalletService = Depends(get_org_wallet_service)
):
    try:
        data = wallet_service.get_reserve(
            organization_name=current_user.active_organization
        )
        if not data:
            return BaseAPIResponse(success=False, error={"code": "NOT_FOUND", "message": "Reserve wallet not found"})
        return BaseAPIResponse(success=True, data=data)
    except Exception as e:
        return BaseAPIResponse(success=False, error={"code": "UNKNOWN_ERROR", "message": str(e)})
