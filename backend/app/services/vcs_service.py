import logging
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from app.core.exceptions import BusinessRuleViolationError, EntityNotFoundError
from app.integrations.vcs.github_client import github_service
from app.integrations.vcs.azure_devops_client import azure_devops_service, azure_devops_oauth_service
from app.models.user import User

logger = logging.getLogger(__name__)


class VCSService:
    """Service orchestrating VCS OAuth, repository fetching, and code context extraction."""

    # ── GitHub Operations ───────────────────────────────────────────────────

    def get_github_auth_url(self, user: User) -> str:
        return github_service.get_oauth_url(state=str(user.id))

    async def connect_github_oauth(
        self, db: Session, user: User, code: str
    ) -> Dict[str, Any]:
        token_data = await github_service.exchange_code_for_token(code)
        access_token = token_data.get("access_token")
        if not access_token:
            raise BusinessRuleViolationError("Failed to obtain GitHub token")

        gh_user = await github_service.get_github_user(access_token)
        username = gh_user.get("login", "")

        user.github_token = access_token
        user.github_username = username
        db.commit()
        db.refresh(user)

        return {"status": "connected", "github_username": username}

    def disconnect_github(self, db: Session, user: User) -> Dict[str, str]:
        user.github_token = None
        user.github_username = None
        db.commit()
        db.refresh(user)
        return {"status": "disconnected"}

    async def list_github_repos(
        self, user: User, page: int = 1, per_page: int = 30
    ) -> List[Dict[str, Any]]:
        if not getattr(user, "github_token", None):
            raise BusinessRuleViolationError("GitHub not connected")
        return await github_service.list_repos(user.github_token, per_page=per_page, page=page)

    # ── Azure DevOps Operations ─────────────────────────────────────────────

    def disconnect_azure_devops(self, db: Session, user: User) -> Dict[str, str]:
        user.azure_devops_token = None
        user.azure_devops_username = None
        user.azure_devops_refresh_token = None
        db.commit()
        db.refresh(user)
        return {"status": "disconnected"}


vcs_service = VCSService()

__all__ = ["VCSService", "vcs_service"]
