from fastapi import APIRouter, Depends, HTTPException
from tokenops.schemas.superadmin import BaseAPIResponse, BlockOrgRequest, BlockUserRequest
from tokenops.services.admin.admin_governance_service import AdminGovernanceService
from .dependencies import verify_super_admin, get_admin_governance_service
from models import User

router = APIRouter(tags=["Super Admin Block"])

@router.post("/organization", response_model=BaseAPIResponse)
def block_organization(
    request: BlockOrgRequest,
    current_user: User = Depends(verify_super_admin),
    gov_service: AdminGovernanceService = Depends(get_admin_governance_service)
):
    try:
        gov_service.set_organization_block_status(
            admin_user_id=current_user.id,
            organization_name=request.organization_name,
            is_blocked=True
        )
        return BaseAPIResponse(success=True)
    except HTTPException as e:
        return BaseAPIResponse(success=False, error={"code": "GOVERNANCE_ERROR", "message": e.detail})
    except Exception as e:
        return BaseAPIResponse(success=False, error={"code": "UNKNOWN_ERROR", "message": str(e)})

@router.post("/organization/unblock", response_model=BaseAPIResponse)
def unblock_organization(
    request: BlockOrgRequest,
    current_user: User = Depends(verify_super_admin),
    gov_service: AdminGovernanceService = Depends(get_admin_governance_service)
):
    try:
        gov_service.set_organization_block_status(
            admin_user_id=current_user.id,
            organization_name=request.organization_name,
            is_blocked=False
        )
        return BaseAPIResponse(success=True)
    except HTTPException as e:
        return BaseAPIResponse(success=False, error={"code": "GOVERNANCE_ERROR", "message": e.detail})
    except Exception as e:
        return BaseAPIResponse(success=False, error={"code": "UNKNOWN_ERROR", "message": str(e)})

@router.post("/user", response_model=BaseAPIResponse)
def block_user(
    request: BlockUserRequest,
    current_user: User = Depends(verify_super_admin),
    gov_service: AdminGovernanceService = Depends(get_admin_governance_service)
):
    try:
        gov_service.set_user_block_status(
            admin_user_id=current_user.id,
            user_id=request.user_id,
            organization_name=request.organization_name,
            is_active=False
        )
        return BaseAPIResponse(success=True)
    except HTTPException as e:
        return BaseAPIResponse(success=False, error={"code": "GOVERNANCE_ERROR", "message": e.detail})
    except Exception as e:
        return BaseAPIResponse(success=False, error={"code": "UNKNOWN_ERROR", "message": str(e)})

@router.post("/user/unblock", response_model=BaseAPIResponse)
def unblock_user(
    request: BlockUserRequest,
    current_user: User = Depends(verify_super_admin),
    gov_service: AdminGovernanceService = Depends(get_admin_governance_service)
):
    try:
        gov_service.set_user_block_status(
            admin_user_id=current_user.id,
            user_id=request.user_id,
            organization_name=request.organization_name,
            is_active=True
        )
        return BaseAPIResponse(success=True)
    except HTTPException as e:
        return BaseAPIResponse(success=False, error={"code": "GOVERNANCE_ERROR", "message": e.detail})
    except Exception as e:
        return BaseAPIResponse(success=False, error={"code": "UNKNOWN_ERROR", "message": str(e)})
