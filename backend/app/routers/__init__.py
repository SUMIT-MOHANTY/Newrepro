"""
DSuite BRD Analyzer - Routers Aggregator
Aggregates all 12 enterprise-grade domain routers into a unified api_router.
"""

from fastapi import APIRouter

from app.routers.tickets import router as tickets_router
from app.routers.auth import router as auth_router
from app.routers.users import router as users_router
from app.routers.oauth import router as oauth_router
from app.routers.vcs import router as vcs_router
from app.routers.documents import router as documents_router
from app.routers.governance import router as governance_router
from app.routers.projects import router as projects_router
from app.routers.ai import router as ai_router
from app.routers.superadmin import router as superadmin_router
from app.routers.agents import router as agents_router
from app.routers.coordination import router as coordination_router

api_router = APIRouter()

# Register all domain routers
api_router.include_router(tickets_router)
api_router.include_router(auth_router)
api_router.include_router(users_router)
api_router.include_router(oauth_router)
api_router.include_router(vcs_router)
api_router.include_router(documents_router)
api_router.include_router(governance_router)
api_router.include_router(projects_router)
api_router.include_router(ai_router)
api_router.include_router(superadmin_router)
api_router.include_router(agents_router)
api_router.include_router(coordination_router)

__all__ = [
    "api_router",
    "tickets_router",
    "auth_router",
    "users_router",
    "oauth_router",
    "vcs_router",
    "documents_router",
    "governance_router",
    "projects_router",
    "ai_router",
    "superadmin_router",
    "agents_router",
    "coordination_router",
]
