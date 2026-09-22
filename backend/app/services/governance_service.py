import logging
import os
import sys
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.core.exceptions import EntityNotFoundError, PermissionDeniedError
from app.models.governance import GovernanceQuestion, GovernanceResponse
from app.models.user import User
from app.repositories.governance_repository import governance_repository
from app.schemas.governance import (
    GovernanceDimensionScores,
    GovernanceQuestion as GovernanceQuestionSchema,
    GovernanceResult,
    ProjectTagSchema,
)
import governance_scoring

logger = logging.getLogger(__name__)


class GovernanceService:
    """Business logic for governance evaluation, scoring rules, and project classification."""

    def get_active_questions(self, db: Session) -> List[GovernanceQuestion]:
        return governance_repository.list_active_questions(db)

    def get_project_result(
        self, db: Session, identifier: str, current_user: User
    ) -> GovernanceResult:
        project = governance_repository.get_by_id_or_token(db, identifier)
        if not project:
            raise EntityNotFoundError(f"Project '{identifier}' not found.")

        # Scoped access check
        is_super = bool(getattr(current_user, "is_super_admin", False))
        is_creator = project.owner_id == current_user.id
        same_org = (
            current_user.organization_name
            and project.organization_name
            and current_user.organization_name.lower() == project.organization_name.lower()
        )
        if not (is_super or is_creator or same_org):
            raise PermissionDeniedError("Access denied to this project.")

        tag_schemas = [
            ProjectTagSchema(id=t.id, name=t.name)
            for t in (project.tags or [])
        ]

        dimension_scores = GovernanceDimensionScores(
            business_value=project.business_value_score or 0.0,
            data_sensitivity=project.data_sensitivity_score or 0.0,
            integration_complexity=project.integration_complexity_score or 0.0,
            operational_impact=project.operational_impact_score or 0.0,
            ai_risk=project.ai_risk_score or 0.0,
            ownership=project.ownership_score or 0.0,
        )

        return GovernanceResult(
            id=project.id,
            project_token=project.project_token,
            project_name=project.project_name or "",
            submission_date=project.submission_date,
            tags=tag_schemas,
            dimension_scores=dimension_scores,
            weighted_score=project.weighted_score or 0.0,
            classification=project.classification or "SANDBOX",
            recommendation=project.recommendation or "",
            pending_revision_reason=project.pending_revision_reason,
            client_id=project.client_id,
            client_secret=project.client_secret,
        )


governance_service = GovernanceService()

__all__ = ["GovernanceService", "governance_service"]
