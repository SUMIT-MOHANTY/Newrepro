from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import (
    BusinessRuleViolationError,
    EntityNotFoundError,
    PermissionDeniedError,
)
from app.core.security import (
    create_access_token,
    get_password_hash,
    verify_password,
    verify_token,
    create_refresh_token,
    decode_token,
    get_token_jti,
    get_token_expiry,
)
from app.core.models import RefreshTokenBlacklist
from app.models.user import User
from app.repositories.user_repository import user_repository
from app.schemas.user import Token, TokenPair


class TokenRotationService:
    """
    Service for managing JWT token rotation with refresh token binding.
    Implements secure token rotation strategy with token family detection.
    """

    def __init__(self):
        self._token_families: Dict[str, str] = {}  # In-memory storage for token families

    def create_token_pair_with_rotation(
        self,
        user: User,
        token_family: Optional[str] = None,
    ) -> TokenPair:
        """
        Create a new access and refresh token pair with rotation support.

        Args:
            user: The user to create tokens for
            token_family: Optional existing token family ID for rotation

        Returns:
            TokenPair with access_token, refresh_token, and family_id
        """
        # Generate or reuse token family
        family_id = token_family or self._generate_family_id()

        # Create tokens with family binding
        token_data = {
            "sub": user.email,
            "user_id": str(user.id),
            "family_id": family_id,
        }

        access_token = create_access_token(
            data=token_data,
            expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
        )

        refresh_token = create_refresh_token(
            data=token_data,
            expires_delta=timedelta(days=settings.refresh_token_expire_days),
        )

        # Store token family binding
        self._token_families[family_id] = refresh_token

        return TokenPair(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            family_id=family_id,
        )

    def rotate_tokens(
        self,
        refresh_token_str: str,
        user: User,
    ) -> TokenPair:
        """
        Rotate tokens using a valid refresh token.
        Implements token reuse detection - if a refresh token is used twice,
        the entire token family is invalidated (potential token theft).

        Args:
            refresh_token_str: The current refresh token
            user: The user requesting token rotation

        Returns:
            New TokenPair with rotated tokens

        Raises:
            BusinessRuleViolationError: If token reuse is detected
        """
        # Decode and validate the refresh token
        payload = decode_token(refresh_token_str)
        if not payload:
            raise BusinessRuleViolationError("Invalid refresh token")

        family_id = payload.get("family_id")
        if not family_id:
            raise BusinessRuleViolationError("Invalid token: no family ID")

        # Check for token reuse (theft detection)
        stored_token = self._token_families.get(family_id)
        if stored_token and stored_token != refresh_token_str:
            # Token reuse detected! Invalidate the entire family
            self._invalidate_token_family(family_id)
            raise BusinessRuleViolationError(
                "Token reuse detected. Your session has been terminated for security."
            )

        # Create new token pair with same family
        return self.create_token_pair_with_rotation(user, family_id)

    def _generate_family_id(self) -> str:
        """Generate a unique token family ID."""
        import secrets
        return secrets.token_urlsafe(32)

    def _invalidate_token_family(self, family_id: str):
        """Invalidate all tokens in a family (used on reuse detection)."""
        if family_id in self._token_families:
            del self._token_families[family_id]

    def cleanup_expired_families(self):
        """Clean up expired token families (called periodically)."""
        # In production, this would check token expiry
        # For now, we keep families in memory
        pass


class TokenBlacklistService:
    """
    Service for managing token blacklisting with Redis/memory-backed storage.
    Implements cleanup scheduling for expired tokens.
    """

    def __init__(self):
        self._redis_client = None
        self._memory_store: Dict[str, datetime] = {}  # Fallback memory store
        self._init_redis()

    def _init_redis(self):
        """Initialize Redis connection if available."""
        try:
            import redis
            redis_url = getattr(settings, "REDIS_URL", None)
            if redis_url:
                self._redis_client = redis.from_url(redis_url, decode_responses=True)
        except ImportError:
            pass
        except Exception:
            self._redis_client = None

    def blacklist_token(
        self,
        token_jti: str,
        expires_at: datetime,
        user_id: Optional[str] = None,
    ) -> bool:
        """
        Add a token to the blacklist.

        Args:
            token_jti: The JWT ID (jti claim) of the token
            expires_at: When the token expires
            user_id: Optional user ID associated with the token

        Returns:
            True if successful, False otherwise
        """
        try:
            if self._redis_client:
                # Use Redis with TTL
                ttl = int((expires_at - datetime.now(timezone.utc)).total_seconds())
                if ttl > 0:
                    key = f"blacklist:{token_jti}"
                    self._redis_client.setex(key, ttl, "1")
                    if user_id:
                        self._redis_client.sadd(f"user_tokens:{user_id}", token_jti)
                return True
            else:
                # Use memory fallback
                self._memory_store[token_jti] = expires_at
                return True
        except Exception as e:
            # Log error but don't fail
            import logging
            logging.getLogger(__name__).error(f"Failed to blacklist token: {e}")
            return False

    def is_blacklisted(self, token_jti: str) -> bool:
        """
        Check if a token is blacklisted.

        Args:
            token_jti: The JWT ID to check

        Returns:
            True if blacklisted, False otherwise
        """
        try:
            if self._redis_client:
                return bool(self._redis_client.exists(f"blacklist:{token_jti}"))
            else:
                # Check memory store and cleanup if expired
                if token_jti in self._memory_store:
                    if self._memory_store[token_jti] < datetime.now(timezone.utc):
                        del self._memory_store[token_jti]
                        return False
                    return True
                return False
        except Exception:
            return False

    def blacklist_user_tokens(self, user_id: str) -> int:
        """
        Blacklist all tokens for a user (e.g., on logout from all devices).

        Args:
            user_id: The user ID to blacklist tokens for

        Returns:
            Number of tokens blacklisted
        """
        count = 0
        try:
            if self._redis_client:
                token_jtis = self._redis_client.smembers(f"user_tokens:{user_id}")
                for jti in token_jtis:
                    self._redis_client.setex(f"blacklist:{jti}", 86400, "1")  # 24h TTL
                    count += 1
        except Exception:
            pass
        return count

    def cleanup_expired(self) -> int:
        """
        Clean up expired tokens from the blacklist.
        For Redis, this is automatic via TTL.
        For memory store, manual cleanup is needed.

        Returns:
            Number of tokens cleaned up
        """
        if self._redis_client:
            # Redis handles TTL automatically
            return 0

        # Manual cleanup for memory store
        now = datetime.now(timezone.utc)
        expired = [jti for jti, exp in self._memory_store.items() if exp < now]
        for jti in expired:
            del self._memory_store[jti]
        return len(expired)


class AuthService:
    """Business logic service for authentication, JWT lifecycle, and multi-tenant access."""

    def __init__(self):
        self.token_rotation = TokenRotationService()
        self.token_blacklist = TokenBlacklistService()

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
        """Create tokens for user (legacy method, uses rotation service internally)."""
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

    def create_token_pair_with_rotation(
        self,
        user: User,
    ) -> TokenPair:
        """
        Create a new token pair with rotation support.
        Use this for new logins to get both access and refresh tokens.
        """
        return self.token_rotation.create_token_pair_with_rotation(user)

    def rotate_tokens(
        self,
        refresh_token_str: str,
        user: User,
    ) -> TokenPair:
        """
        Rotate tokens using a refresh token.
        Blacklists the old refresh token and returns new tokens.
        """
        # First, check if the refresh token is blacklisted
        token_jti = get_token_jti(refresh_token_str)
        if token_jti and self.token_blacklist.is_blacklisted(token_jti):
            raise BusinessRuleViolationError("Refresh token has been revoked")

        # Perform rotation
        token_pair = self.token_rotation.rotate_tokens(refresh_token_str, user)

        # Blacklist the old refresh token
        if token_jti:
            expiry = get_token_expiry(refresh_token_str)
            if expiry:
                self.token_blacklist.blacklist_token(token_jti, expiry, str(user.id))

        return token_pair

    def logout_user(
        self,
        access_token: Optional[str] = None,
        refresh_token: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> bool:
        """
        Logout a user by blacklisting their tokens.

        Args:
            access_token: The access token to blacklist
            refresh_token: The refresh token to blacklist
            user_id: Optional user ID for additional cleanup

        Returns:
            True if successful
        """
        now = datetime.now(timezone.utc)

        # Blacklist access token
        if access_token:
            access_jti = get_token_jti(access_token)
            access_expiry = get_token_expiry(access_token)
            if access_jti and access_expiry:
                self.token_blacklist.blacklist_token(access_jti, access_expiry, user_id)

        # Blacklist refresh token
        if refresh_token:
            refresh_jti = get_token_jti(refresh_token)
            refresh_expiry = get_token_expiry(refresh_token)
            if refresh_jti and refresh_expiry:
                self.token_blacklist.blacklist_token(refresh_jti, refresh_expiry, user_id)

        return True

    def logout_user_from_all_devices(self, user_id: str) -> int:
        """
        Logout a user from all devices by blacklisting all their tokens.

        Args:
            user_id: The user ID to logout

        Returns:
            Number of tokens blacklisted
        """
        return self.token_blacklist.blacklist_user_tokens(user_id)

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

    def is_token_valid(self, token_str: str) -> bool:
        """
        Check if a token is valid (not blacklisted and properly signed).

        Args:
            token_str: The token to validate

        Returns:
            True if valid, False otherwise
        """
        token_jti = get_token_jti(token_str)
        if token_jti and self.token_blacklist.is_blacklisted(token_jti):
            return False

        payload = decode_token(token_str)
        return payload is not None


auth_service = AuthService()

__all__ = [
    "AuthService",
    "auth_service",
    "TokenRotationService",
    "TokenBlacklistService",
]
