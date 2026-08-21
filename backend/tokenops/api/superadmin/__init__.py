from fastapi import APIRouter
from .wallet_router import router as wallet_router
from .pricing_router import router as pricing_router
from .block_router import router as block_router
from .payg_router import router as payg_router
from .analytics_router import router as analytics_router

tokenops_admin_router = APIRouter(prefix="/api/superadmin/tokenops")

tokenops_admin_router.include_router(wallet_router, prefix="/wallet")
tokenops_admin_router.include_router(pricing_router, prefix="/pricing")
tokenops_admin_router.include_router(block_router, prefix="/block")
tokenops_admin_router.include_router(payg_router, prefix="/payg")
tokenops_admin_router.include_router(analytics_router, prefix="/analytics")

__all__ = ["tokenops_admin_router"]
