from fastapi import APIRouter, Depends, Query
from tokenops.schemas.orgadmin import BaseAPIResponse
from tokenops.services.org_admin.org_analytics_service import OrgAnalyticsService
from .dependencies import verify_org_admin, get_org_analytics_service
from models import User
from typing import Optional

router = APIRouter(tags=["Org Admin Analytics"])

@router.get("/overview", response_model=BaseAPIResponse)
def get_overview(
    current_user: User = Depends(verify_org_admin),
    analytics_service: OrgAnalyticsService = Depends(get_org_analytics_service)
):
    try:
        data = analytics_service.get_overview(
            organization_name=current_user.active_organization
        )
        return BaseAPIResponse(success=True, data=data)
    except Exception as e:
        return BaseAPIResponse(success=False, error={"code": "UNKNOWN_ERROR", "message": str(e)})

@router.get("/users", response_model=BaseAPIResponse)
def get_top_users(
    from_date: Optional[str] = Query(None),
    to_date: Optional[str] = Query(None),
    model_name: Optional[str] = Query(None),
    limit: int = Query(10, ge=1, le=50),
    current_user: User = Depends(verify_org_admin),
    analytics_service: OrgAnalyticsService = Depends(get_org_analytics_service)
):
    try:
        # Note: from_date, to_date, model_name filters can be added to UserUsageSummary if we introduce dimensions.
        data = analytics_service.get_top_users(
            organization_name=current_user.active_organization,
            limit=limit
        )
        return BaseAPIResponse(success=True, data=data)
    except Exception as e:
        return BaseAPIResponse(success=False, error={"code": "UNKNOWN_ERROR", "message": str(e)})
