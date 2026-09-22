from typing import List, Optional
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.user import (
    Organization,
    OrganizationSSOSettings,
    User,
    UserOrganizationRole,
)
from app.repositories.base import BaseRepository
from app.schemas.user import UserCreate


class UserRepository(BaseRepository[User, UserCreate, UserCreate]):
    """Repository managing User and Organization database persistence."""

    def __init__(self):
        super().__init__(User)

    def get_by_email(self, db: Session, email: str) -> Optional[User]:
        if not email:
            return None
        return db.query(User).filter(func.lower(User.email) == email.strip().lower()).first()

    def get_by_id(self, db: Session, user_id: int) -> Optional[User]:
        return db.query(User).filter(User.id == user_id).first()

    def list_by_organization(self, db: Session, org_name: str) -> List[User]:
        if not org_name:
            return []
        norm = org_name.strip().lower()
        return (
            db.query(User)
            .filter(func.lower(User.organization_name) == norm)
            .order_by(User.id.asc())
            .all()
        )

    def get_user_organizations(self, db: Session, user: User) -> List[str]:
        orgs = set()
        if user.organization_name and user.organization_name.strip():
            orgs.add(user.organization_name.strip())

        if UserOrganizationRole:
            mappings = (
                db.query(UserOrganizationRole.organization_name)
                .filter(UserOrganizationRole.user_id == user.id)
                .all()
            )
            for m in mappings:
                if m[0] and m[0].strip():
                    orgs.add(m[0].strip())

        return sorted(list(orgs))

    def get_sso_settings(self, db: Session, org_name: str) -> Optional[OrganizationSSOSettings]:
        if not OrganizationSSOSettings or not org_name:
            return None
        return (
            db.query(OrganizationSSOSettings)
            .filter(func.lower(OrganizationSSOSettings.organization_name) == org_name.strip().lower())
            .first()
        )

    def update_password(self, db: Session, user: User, hashed_password: str) -> User:
        user.hashed_password = hashed_password
        db.commit()
        db.refresh(user)
        return user


user_repository = UserRepository()

__all__ = ["UserRepository", "user_repository"]
