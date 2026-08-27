from fastapi import APIRouter, Depends, HTTPException
from tokenops.schemas.orgadmin import BaseAPIResponse, BlockUserRequest
from tokenops.services.org_admin.org_governance_service import OrgGovernanceService
from .dependencies import verify_org_admin, get_org_governance_service
from models import User

router = APIRouter(tags=["Org Admin Block"])

@router.post("/user", response_model=BaseAPIResponse)
def block_user(
    request: BlockUserRequest,
    current_user: User = Depends(verify_org_admin),
    gov_service: OrgGovernanceService = Depends(get_org_governance_service)
):
    try:
        gov_service.set_user_block_status(
            admin_user_id=current_user.id,
            organization_name=current_user.active_organization,
            user_id=request.user_id,
            is_blocked=True
        )
        return BaseAPIResponse(success=True)
    except HTTPException as e:
        return BaseAPIResponse(success=False, error={"code": "GOVERNANCE_ERROR", "message": e.detail})
    except Exception as e:
        return BaseAPIResponse(success=False, error={"code": "UNKNOWN_ERROR", "message": str(e)})

@router.post("/user/unblock", response_model=BaseAPIResponse)
def unblock_user(
    request: BlockUserRequest,
    current_user: User = Depends(verify_org_admin),
    gov_service: OrgGovernanceService = Depends(get_org_governance_service)
):
    try:
        gov_service.set_user_block_status(
            admin_user_id=current_user.id,
            organization_name=current_user.active_organization,
            user_id=request.user_id,
            is_blocked=False
        )
        return BaseAPIResponse(success=True)
    except HTTPException as e:
        return BaseAPIResponse(success=False, error={"code": "GOVERNANCE_ERROR", "message": e.detail})
    except Exception as e:
        return BaseAPIResponse(success=False, error={"code": "UNKNOWN_ERROR", "message": str(e)})
