from typing import List, Optional
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from app.models.governance import (
    GovernanceQuestion,
    GovernanceQuestionOption,
    GovernanceResponse,
    ProjectTag,
)
from app.repositories.base import BaseRepository


class GovernanceRepository(BaseRepository[GovernanceResponse, dict, dict]):
    """Repository managing Governance questions, submissions, and project records."""

    def __init__(self):
        super().__init__(GovernanceResponse)

    def list_active_questions(self, db: Session) -> List[GovernanceQuestion]:
        return (
            db.query(GovernanceQuestion)
            .options(joinedload(GovernanceQuestion.options))
            .filter(GovernanceQuestion.is_active == True)
            .order_by(GovernanceQuestion.order.asc())
            .all()
        )

    def get_by_token(self, db: Session, project_token: str) -> Optional[GovernanceResponse]:
        if not project_token:
            return None
        return (
            db.query(GovernanceResponse)
            .options(joinedload(GovernanceResponse.tags))
            .filter(GovernanceResponse.project_token == project_token)
            .first()
        )

    def get_by_id_or_token(self, db: Session, identifier: str) -> Optional[GovernanceResponse]:
        query = db.query(GovernanceResponse).options(joinedload(GovernanceResponse.tags))
        if identifier.isdigit():
            return query.filter(
                or_(
                    GovernanceResponse.id == int(identifier),
                    GovernanceResponse.project_token == identifier,
                )
            ).first()
        return query.filter(GovernanceResponse.project_token == identifier).first()

    def list_scoped_projects(
        self,
        db: Session,
        owner_id: int,
        organization_name: Optional[str] = None,
        is_super_admin: bool = False,
    ) -> List[GovernanceResponse]:
        query = db.query(GovernanceResponse).options(joinedload(GovernanceResponse.tags))
        if is_super_admin:
            pass
        elif organization_name:
            query = query.filter(
                or_(
                    GovernanceResponse.owner_id == owner_id,
                    func.lower(GovernanceResponse.organization_name) == organization_name.strip().lower(),
                )
            )
        else:
            query = query.filter(GovernanceResponse.owner_id == owner_id)

        return (
            query.filter(GovernanceResponse.is_archived.is_(False))
            .order_by(GovernanceResponse.submission_date.desc())
            .all()
        )


governance_repository = GovernanceRepository()

__all__ = ["GovernanceRepository", "governance_repository"]
