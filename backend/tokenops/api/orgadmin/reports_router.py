from fastapi import APIRouter, Depends, Query
from tokenops.schemas.orgadmin import BaseAPIResponse
from tokenops.services.org_admin.org_analytics_service import OrgAnalyticsService
from .dependencies import verify_org_admin, get_org_analytics_service
from models import User
from typing import Optional

router = APIRouter(tags=["Org Admin Reports"])

@router.get("/usage", response_model=BaseAPIResponse)
def get_org_usage(
    current_user: User = Depends(verify_org_admin),
    analytics_service: OrgAnalyticsService = Depends(get_org_analytics_service)
):
    try:
        data = analytics_service.get_org_usage_report(
            organization_name=current_user.active_organization
        )
        return BaseAPIResponse(success=True, data=data)
    except Exception as e:
        return BaseAPIResponse(success=False, error={"code": "UNKNOWN_ERROR", "message": str(e)})

@router.get("/users", response_model=BaseAPIResponse)
def get_user_consumption(
    current_user: User = Depends(verify_org_admin),
    analytics_service: OrgAnalyticsService = Depends(get_org_analytics_service)
):
    try:
        data = analytics_service.get_user_consumption_report(
            organization_name=current_user.active_organization
        )
        return BaseAPIResponse(success=True, data=data)
    except Exception as e:
        return BaseAPIResponse(success=False, error={"code": "UNKNOWN_ERROR", "message": str(e)})

@router.get("/ledger", response_model=BaseAPIResponse)
def get_financial_ledger(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    transaction_type: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    current_user: User = Depends(verify_org_admin),
    analytics_service: OrgAnalyticsService = Depends(get_org_analytics_service)
):
    try:
        data = analytics_service.get_ledger(
            organization_name=current_user.active_organization,
            page=page,
            size=size,
            transaction_type=transaction_type,
            search=search
        )
        return BaseAPIResponse(success=True, data=data)
    except Exception as e:
        return BaseAPIResponse(success=False, error={"code": "UNKNOWN_ERROR", "message": str(e)})
