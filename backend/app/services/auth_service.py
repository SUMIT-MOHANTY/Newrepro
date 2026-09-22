from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import (
    BusinessRuleViolationError,
    EntityNotFoundError,
    PermissionDeniedError,
)
from app.core.security import create_access_token, get_password_hash, verify_password, verify_token
from app.models.user import User
from app.repositories.user_repository import user_repository
from app.schemas.user import Token


class AuthService:
    """Business logic service for authentication, JWT lifecycle, and multi-tenant access."""

    def authenticate_user(
        self, db: Session, email: str, password: str
    ) -> User:
        user = user_repository.get_by_email(db, email)
        if not user:
            raise PermissionDeniedError("Incorrect email or password")

        # Verify password (checks both hashed_password and legacy plain if needed)
        valid = False
        if getattr(user, "hashed_password", None):
            valid = verify_password(password, user.hashed_password)
        elif getattr(user, "password", None):
            valid = (user.password == password)

        if not valid:
            raise PermissionDeniedError("Incorrect email or password")

        if not getattr(user, "is_active", True):
            raise PermissionDeniedError("User account is disabled")

        return user

    def create_user_tokens(
        self, db: Session, user: User, selected_org: Optional[str] = None
    ) -> Token:
        user_orgs = user_repository.get_user_organizations(db, user)

        # Multi-org selection requirement: If user has > 1 org and no org is specified yet
        if len(user_orgs) > 1 and not selected_org and not getattr(user, "is_super_admin", False):
            temp_token = create_access_token(
                data={"sub": user.email, "partial": True},
                expires_delta=timedelta(minutes=15),
            )
            return Token(
                access_token=temp_token,
                token_type="bearer",
                requires_selection=True,
                organizations=user_orgs,
            )

        active_org = selected_org or (user_orgs[0] if user_orgs else user.organization_name)
        token_data = {"sub": user.email}
        if active_org:
            token_data["org"] = active_org

        access_token = create_access_token(
            data=token_data,
            expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
        )
        return Token(
            access_token=access_token,
            token_type="bearer",
            requires_selection=False,
            organizations=user_orgs,
        )

    def select_organization(
        self, db: Session, user: User, organization_name: str
    ) -> Token:
        user_orgs = user_repository.get_user_organizations(db, user)
        is_super = bool(getattr(user, "is_super_admin", False))

        matching_org = next(
            (o for o in user_orgs if o.lower() == organization_name.strip().lower()), None
        )
        if not matching_org and not is_super:
            raise PermissionDeniedError(
                f"You do not have access to organization '{organization_name}'"
            )

        target_org = matching_org or organization_name.strip()
        access_token = create_access_token(
            data={"sub": user.email, "org": target_org},
            expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
        )
        return Token(
            access_token=access_token,
            token_type="bearer",
            requires_selection=False,
            organizations=user_orgs,
        )

    def reset_password_with_token(
        self, db: Session, token: str, new_password: str
    ) -> User:
        payload = verify_token(token)
        if not payload or not payload.get("sub") or payload.get("scope") != "password_reset":
            raise BusinessRuleViolationError("Invalid or expired password reset token")

        email = payload.get("sub")
        user = user_repository.get_by_email(db, email)
        if not user:
            raise EntityNotFoundError("User not found")

        hashed = get_password_hash(new_password)
        return user_repository.update_password(db, user, hashed)


auth_service = AuthService()

__all__ = ["AuthService", "auth_service"]
