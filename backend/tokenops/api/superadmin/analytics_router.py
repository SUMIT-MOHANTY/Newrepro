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

@router.get("/trends", response_model=BaseAPIResponse)
def get_usage_trends(
    range: Optional[str] = Query("30d"),
    current_user: User = Depends(verify_super_admin),
    analytics_service: AdminAnalyticsService = Depends(get_admin_analytics_service)
):
    try:
        data = analytics_service.get_trends(range_str=range)
        return BaseAPIResponse(success=True, data=data)
    except Exception as e:
        return BaseAPIResponse(success=False, error={"code": "UNKNOWN_ERROR", "message": str(e)})

@router.get("/models", response_model=BaseAPIResponse)
def get_model_usage(
    current_user: User = Depends(verify_super_admin),
    analytics_service: AdminAnalyticsService = Depends(get_admin_analytics_service)
):
    try:
        data = analytics_service.get_model_usage()
        return BaseAPIResponse(success=True, data=data)
    except Exception as e:
        return BaseAPIResponse(success=False, error={"code": "UNKNOWN_ERROR", "message": str(e)})

@router.get("/top-organizations", response_model=BaseAPIResponse)
def get_top_organizations(
    limit: Optional[int] = Query(10, ge=1, le=100),
    current_user: User = Depends(verify_super_admin),
    analytics_service: AdminAnalyticsService = Depends(get_admin_analytics_service)
):
    try:
        data = analytics_service.get_top_organizations(limit=limit)
        return BaseAPIResponse(success=True, data=data)
    except Exception as e:
        return BaseAPIResponse(success=False, error={"code": "UNKNOWN_ERROR", "message": str(e)})

@router.get("/alerts", response_model=BaseAPIResponse)
def get_operational_alerts(
    current_user: User = Depends(verify_super_admin),
    analytics_service: AdminAnalyticsService = Depends(get_admin_analytics_service)
):
    try:
        data = analytics_service.get_operational_alerts()
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

@router.get("/ledger", response_model=BaseAPIResponse)
def get_superadmin_financial_ledger(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    organization_name: Optional[str] = Query(None),
    transaction_type: Optional[str] = Query(None),
    purpose: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    current_user: User = Depends(verify_super_admin),
    analytics_service: AdminAnalyticsService = Depends(get_admin_analytics_service)
):
    try:
        data = analytics_service.get_ledger(
            organization_name=organization_name,
            page=page,
            size=size,
            transaction_type=transaction_type,
            purpose=purpose,
            search=search
        )
        return BaseAPIResponse(success=True, data=data)
    except Exception as e:
        return BaseAPIResponse(success=False, error={"code": "UNKNOWN_ERROR", "message": str(e)})

