from fastapi import APIRouter, Depends, Query, HTTPException
from tokenops.schemas.superadmin import BaseAPIResponse
from tokenops.services.admin.admin_analytics_service import AdminAnalyticsService
from .dependencies import verify_super_admin, get_admin_analytics_service
from models import User
from typing import Optional

router = APIRouter(tags=["Super Admin Analytics"])

@router.get("/overview", response_model=BaseAPIResponse)
def get_overview(
    from_date: Optional[str] = Query(None),
    to_date: Optional[str] = Query(None),
    organization: Optional[str] = Query(None),
    billing_mode: Optional[str] = Query(None),
    current_user: User = Depends(verify_super_admin),
    analytics_service: AdminAnalyticsService = Depends(get_admin_analytics_service)
):
    try:
        data = analytics_service.get_overview(
            from_date=from_date,
            to_date=to_date,
            organization=organization,
            billing_mode=billing_mode
        )
        return BaseAPIResponse(success=True, data=data)
    except Exception as e:
        return BaseAPIResponse(success=False, error={"code": "UNKNOWN_ERROR", "message": str(e)})

@router.get("/organization/{organization_name}", response_model=BaseAPIResponse)
def get_organization_analytics(
    organization_name: str,
    current_user: User = Depends(verify_super_admin),
    analytics_service: AdminAnalyticsService = Depends(get_admin_analytics_service)
):
    try:
        data = analytics_service.get_organization_analytics(organization_name)
        if not data:
            return BaseAPIResponse(success=False, error={"code": "NOT_FOUND", "message": "Organization not found"})
        return BaseAPIResponse(success=True, data=data)
    except Exception as e:
        return BaseAPIResponse(success=False, error={"code": "UNKNOWN_ERROR", "message": str(e)})
