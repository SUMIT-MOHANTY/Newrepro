from fastapi import APIRouter, Depends, HTTPException
from tokenops.schemas.superadmin import BaseAPIResponse, PricingUpdateRequest, NewModelRequest
from tokenops.services.admin.admin_pricing_service import AdminPricingService
from .dependencies import verify_super_admin, get_admin_pricing_service
from models import User

router = APIRouter(tags=["Super Admin Pricing"])

@router.get("/", response_model=BaseAPIResponse)
def get_pricing(
    current_user: User = Depends(verify_super_admin),
    pricing_service: AdminPricingService = Depends(get_admin_pricing_service)
):
    try:
        data = pricing_service.get_all_pricing()
        return BaseAPIResponse(success=True, data=data)
    except Exception as e:
        return BaseAPIResponse(success=False, error={"code": "UNKNOWN_ERROR", "message": str(e)})

@router.put("/{model_name}", response_model=BaseAPIResponse)
def update_pricing(
    model_name: str,
    request: PricingUpdateRequest,
    current_user: User = Depends(verify_super_admin),
    pricing_service: AdminPricingService = Depends(get_admin_pricing_service)
):
    try:
        pricing_service.update_price(
            admin_user_id=current_user.id,
            model_name=model_name,
            price_per_token=request.price_per_token
        )
        return BaseAPIResponse(success=True)
    except Exception as e:
        return BaseAPIResponse(success=False, error={"code": "UNKNOWN_ERROR", "message": str(e)})

@router.post("/model", response_model=BaseAPIResponse)
def add_model(
    request: NewModelRequest,
    current_user: User = Depends(verify_super_admin),
    pricing_service: AdminPricingService = Depends(get_admin_pricing_service)
):
    try:
        pricing_service.add_model(
            admin_user_id=current_user.id,
            model_name=request.model_name,
            price_per_token=request.price_per_token
        )
        return BaseAPIResponse(success=True)
    except Exception as e:
        return BaseAPIResponse(success=False, error={"code": "UNKNOWN_ERROR", "message": str(e)})
