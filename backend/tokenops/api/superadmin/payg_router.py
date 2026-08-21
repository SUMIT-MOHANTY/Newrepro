from fastapi import APIRouter, Depends, HTTPException
from tokenops.schemas.superadmin import BaseAPIResponse, PAYGRequestView, PAYGDecisionRequest
from tokenops.services.admin.admin_governance_service import AdminGovernanceService
from .dependencies import verify_super_admin, get_admin_governance_service
from models import User

router = APIRouter(tags=["Super Admin PAYG Governance"])

@router.get("/requests", response_model=BaseAPIResponse)
def get_payg_requests(
    current_user: User = Depends(verify_super_admin),
    gov_service: AdminGovernanceService = Depends(get_admin_governance_service)
):
    try:
        reqs = gov_service.get_payg_requests()
        data = [
            PAYGRequestView(
                id=r.id,
                organization_name=r.organization_name,
                status=r.status,
                requested_by=r.requested_by_id,
                created_at=r.created_at.isoformat() if r.created_at else ""
            ) for r in reqs
        ]
        return BaseAPIResponse(success=True, data=data)
    except Exception as e:
        return BaseAPIResponse(success=False, error={"code": "UNKNOWN_ERROR", "message": str(e)})

@router.post("/approve", response_model=BaseAPIResponse)
def approve_payg(
    request: PAYGDecisionRequest,
    current_user: User = Depends(verify_super_admin),
    gov_service: AdminGovernanceService = Depends(get_admin_governance_service)
):
    try:
        gov_service.handle_payg_request(
            admin_user_id=current_user.id,
            organization_name=request.organization_name,
            approve=True,
            remarks=request.remarks
        )
        return BaseAPIResponse(success=True)
    except HTTPException as e:
        return BaseAPIResponse(success=False, error={"code": "GOVERNANCE_ERROR", "message": e.detail})
    except Exception as e:
        return BaseAPIResponse(success=False, error={"code": "UNKNOWN_ERROR", "message": str(e)})

@router.post("/reject", response_model=BaseAPIResponse)
def reject_payg(
    request: PAYGDecisionRequest,
    current_user: User = Depends(verify_super_admin),
    gov_service: AdminGovernanceService = Depends(get_admin_governance_service)
):
    try:
        gov_service.handle_payg_request(
            admin_user_id=current_user.id,
            organization_name=request.organization_name,
            approve=False,
            remarks=request.remarks
        )
        return BaseAPIResponse(success=True)
    except HTTPException as e:
        return BaseAPIResponse(success=False, error={"code": "GOVERNANCE_ERROR", "message": e.detail})
    except Exception as e:
        return BaseAPIResponse(success=False, error={"code": "UNKNOWN_ERROR", "message": str(e)})

@router.post("/suspend", response_model=BaseAPIResponse)
def suspend_payg(
    request: PAYGDecisionRequest,
    current_user: User = Depends(verify_super_admin),
    gov_service: AdminGovernanceService = Depends(get_admin_governance_service)
):
    try:
        gov_service.suspend_payg(
            admin_user_id=current_user.id,
            organization_name=request.organization_name
        )
        return BaseAPIResponse(success=True)
    except HTTPException as e:
        return BaseAPIResponse(success=False, error={"code": "GOVERNANCE_ERROR", "message": e.detail})
    except Exception as e:
        return BaseAPIResponse(success=False, error={"code": "UNKNOWN_ERROR", "message": str(e)})
