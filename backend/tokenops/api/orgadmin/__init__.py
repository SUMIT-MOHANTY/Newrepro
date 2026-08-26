from fastapi import APIRouter
from .users_router import router as users_router
from .allocation_router import router as allocation_router
from .reserve_router import router as reserve_router
from .block_router import router as block_router
from .analytics_router import router as analytics_router
from .reports_router import router as reports_router
from .quota_router import router as quota_router

tokenops_org_router = APIRouter(prefix="/api/org/tokenops")

tokenops_org_router.include_router(users_router, prefix="/users")
tokenops_org_router.include_router(allocation_router, prefix="/allocation")
tokenops_org_router.include_router(reserve_router, prefix="/reserve")
tokenops_org_router.include_router(block_router, prefix="/block")
tokenops_org_router.include_router(analytics_router, prefix="/analytics")
tokenops_org_router.include_router(reports_router, prefix="/reports")
tokenops_org_router.include_router(quota_router, prefix="/quota")

__all__ = ["tokenops_org_router"]
