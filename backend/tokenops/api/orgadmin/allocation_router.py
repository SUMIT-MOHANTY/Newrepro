from fastapi import APIRouter, Depends, HTTPException
from tokenops.schemas.orgadmin import BaseAPIResponse, AllocateRequest, ReallocateRequest, RevokeRequest
from tokenops.services.org_admin.org_wallet_service import OrgWalletService
from .dependencies import verify_org_admin, get_org_wallet_service
from models import User

router = APIRouter(tags=["Org Admin Allocation"])

@router.post("/allocate", response_model=BaseAPIResponse)
def allocate_tokens(
    request: AllocateRequest,
    current_user: User = Depends(verify_org_admin),
    wallet_service: OrgWalletService = Depends(get_org_wallet_service)
):
    try:
        data = wallet_service.allocate_tokens(
            admin_user_id=current_user.id,
            organization_name=current_user.active_organization,
            request_id=request.request_id,
            user_id=request.user_id,
            token_amount=request.token_amount,
            remarks=request.remarks
        )
        return BaseAPIResponse(success=True, data=data)
    except Exception as e:
        return BaseAPIResponse(success=False, error={"code": "ALLOCATION_ERROR", "message": str(e)})

@router.put("/reallocate", response_model=BaseAPIResponse)
def reallocate_tokens(
    request: ReallocateRequest,
    current_user: User = Depends(verify_org_admin),
    wallet_service: OrgWalletService = Depends(get_org_wallet_service)
):
    try:
        data = wallet_service.reallocate_tokens(
            admin_user_id=current_user.id,
            organization_name=current_user.active_organization,
            request_id=request.request_id,
            source_user_id=request.source_user_id,
            destination_user_id=request.destination_user_id,
            token_amount=request.token_amount
        )
        return BaseAPIResponse(success=True, data=data)
    except Exception as e:
        return BaseAPIResponse(success=False, error={"code": "REALLOCATION_ERROR", "message": str(e)})

@router.post("/revoke", response_model=BaseAPIResponse)
def revoke_tokens(
    request: RevokeRequest,
    current_user: User = Depends(verify_org_admin),
    wallet_service: OrgWalletService = Depends(get_org_wallet_service)
):
    try:
        data = wallet_service.revoke_tokens(
            admin_user_id=current_user.id,
            organization_name=current_user.active_organization,
            request_id=request.request_id,
            user_id=request.user_id,
            token_amount=request.token_amount
        )
        return BaseAPIResponse(success=True, data=data)
    except Exception as e:
        return BaseAPIResponse(success=False, error={"code": "REVOKE_ERROR", "message": str(e)})
