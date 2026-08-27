from fastapi import APIRouter, Depends, Query, HTTPException
from tokenops.schemas.superadmin import (
    BaseAPIResponse, PaginatedOrganizationResponse, OrganizationWalletView, PurchaseRequest
)
from tokenops.services.admin.admin_wallet_service import AdminWalletService
from .dependencies import verify_super_admin, get_admin_wallet_service
from models import User

router = APIRouter(tags=["Super Admin Wallet"])

@router.get("/organizations", response_model=BaseAPIResponse)
def get_organizations(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=100),
    search: str = None,
    current_user: User = Depends(verify_super_admin),
    wallet_service: AdminWalletService = Depends(get_admin_wallet_service)
):
    try:
        data = wallet_service.get_organizations(page=page, size=size, search=search)
        return BaseAPIResponse(success=True, data=data)
    except Exception as e:
        return BaseAPIResponse(success=False, error={"code": "UNKNOWN_ERROR", "message": str(e)})

@router.get("/organization/{organization_name}", response_model=BaseAPIResponse)
def get_organization(
    organization_name: str,
    current_user: User = Depends(verify_super_admin),
    wallet_service: AdminWalletService = Depends(get_admin_wallet_service)
):
    try:
        data = wallet_service.get_organization(organization_name)
        if not data:
            return BaseAPIResponse(success=False, error={"code": "NOT_FOUND", "message": "Organization not found"})
        return BaseAPIResponse(success=True, data=data)
    except Exception as e:
        return BaseAPIResponse(success=False, error={"code": "UNKNOWN_ERROR", "message": str(e)})

@router.post("/purchase", response_model=BaseAPIResponse)
def purchase_tokens(
    request: PurchaseRequest,
    current_user: User = Depends(verify_super_admin),
    wallet_service: AdminWalletService = Depends(get_admin_wallet_service)
):
    try:
        data = wallet_service.purchase_tokens(
            admin_user_id=current_user.id,
            organization_name=request.organization_name,
            token_amount=request.token_amount,
            remarks=request.remarks
        )
        return BaseAPIResponse(success=True, data=data)
    except HTTPException as e:
        return BaseAPIResponse(success=False, error={"code": "WALLET_ERROR", "message": e.detail})
    except Exception as e:
        return BaseAPIResponse(success=False, error={"code": "UNKNOWN_ERROR", "message": str(e)})
