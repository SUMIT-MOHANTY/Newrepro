"""
JWT Token Rotation Service
Implements secure token rotation with refresh token versioning and family detection
"""
import uuid
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import RefreshToken, AccessToken
from rest_framework_simplejwt.exceptions import TokenError, InvalidToken

from app.core.models import RefreshTokenBlacklist

logger = logging.getLogger(__name__)
User = get_user_model()


class TokenFamily:
    """
    Represents a token family for detecting token reuse.
    Each family tracks the current token version to detect rotation attacks.
    """
    
    def __init__(self, family_id: str, current_version: int = 0):
        self.family_id = family_id
        self.current_version = current_version
        self.created_at = datetime.utcnow()
    
    def increment_version(self) -> int:
        """Increment the token version."""
        self.current_version += 1
        return self.current_version


class TokenRotationService:
    """
    Service for managing JWT token rotation with security features:
    - Refresh token versioning
    - Token family tracking
    - Token reuse detection
    - Automatic blacklisting on rotation
    """
    
    def __init__(self):
        self.token_families: Dict[str, TokenFamily] = {}
    
    def create_token_pair(self, user) -> Dict[str, str]:
        """
        Create a new token pair with rotation metadata.
        
        Returns:
            Dictionary containing access_token, refresh_token, and metadata
        """
        # Create refresh token
        refresh = RefreshToken.for_user(user)
        
        # Create token family for tracking
        family_id = str(uuid.uuid4())
        version = 1
        
        # Add custom claims to refresh token
        refresh["family_id"] = family_id
        refresh["version"] = version
        refresh["jti"] = str(uuid.uuid4())
        
        # Create access token
        access = refresh.access_token
        access["family_id"] = family_id
        access["version"] = version
        access["email"] = user.email
        # Use email as identifier since username field may vary
        access["user_identifier"] = user.email
        
        # Store token family
        self.token_families[family_id] = TokenFamily(family_id, version)
        
        logger.info(f"Created token pair for user {user.id} with family {family_id}")
        
        return {
            "access_token": str(access),
            "refresh_token": str(refresh),
            "token_type": "Bearer",
            "family_id": family_id,
            "version": version,
        }
    
    def rotate_tokens(self, refresh_token_str: str) -> Dict[str, str]:
        """
        Rotate tokens using a valid refresh token.
        Implements token family versioning and reuse detection.
        
        Args:
            refresh_token_str: The current refresh token
            
        Returns:
            New token pair
            
        Raises:
            InvalidToken: If token is invalid, blacklisted, or reused
        """
        try:
            # Decode the refresh token without verification first to get claims
            refresh = RefreshToken(refresh_token_str)
            family_id = refresh.get("family_id")
            version = refresh.get("version")
            jti = refresh.get("jti")
            user_id = refresh.get("user_id")
            
            if not family_id or not version:
                logger.warning("Token missing rotation metadata")
                raise InvalidToken("Invalid token format")
            
            # Check if token is blacklisted
            if RefreshTokenBlacklist.is_blacklisted(jti):
                logger.warning(f"Attempted use of blacklisted token: {jti}")
                raise InvalidToken("Token has been revoked")
            
            # Check for token reuse (version mismatch)
            current_family = self.token_families.get(family_id)
            if current_family and version < current_family.current_version:
                # Token reuse detected! Blacklist entire family
                logger.warning(f"Token reuse detected for family {family_id}")
                self._blacklist_family(family_id)
                raise InvalidToken("Token reuse detected. Please login again.")
            
            # Get user
            try:
                user = User.objects.get(id=user_id)
            except User.DoesNotExist:
                raise InvalidToken("User not found")
            
            # Blacklist the current token
            self._blacklist_token(jti, refresh_token_str, user_id)
            
            # Create new token pair with incremented version
            new_family_id = str(uuid.uuid4())
            new_version = 1
            
            new_refresh = RefreshToken.for_user(user)
            new_refresh["family_id"] = new_family_id
            new_refresh["version"] = new_version
            new_refresh["jti"] = str(uuid.uuid4())
            
            new_access = new_refresh.access_token
            new_access["family_id"] = new_family_id
            new_access["version"] = new_version
            new_access["email"] = user.email
            new_access["user_identifier"] = user.email
            
            # Update token family tracking
            self.token_families[new_family_id] = TokenFamily(new_family_id, new_version)
            
            logger.info(f"Rotated tokens for user {user_id}: family {family_id} -> {new_family_id}")
            
            return {
                "access_token": str(new_access),
                "refresh_token": str(new_refresh),
                "token_type": "Bearer",
                "family_id": new_family_id,
                "version": new_version,
            }
            
        except TokenError as e:
            logger.warning(f"Token rotation failed: {e}")
            raise InvalidToken("Invalid or expired refresh token")
    
    def _blacklist_token(self, jti: str, token: str, user_id: Optional[int] = None):
        """Add a token to the blacklist."""
        try:
            # Calculate expiry
            token_obj = RefreshToken(token)
            exp_timestamp = token_obj.payload.get("exp")
            expires_at = datetime.fromtimestamp(exp_timestamp, tz=datetime.timezone.utc) if exp_timestamp else datetime.utcnow() + timedelta(days=7)
            
            # Use the class method to blacklist the token
            RefreshTokenBlacklist.blacklist_token(
                token_jti=jti,
                expires_at=expires_at,
                user_id=user_id
            )
            logger.debug(f"Blacklisted token {jti}")
        except Exception as e:
            logger.error(f"Failed to blacklist token: {e}")
    
    def _blacklist_family(self, family_id: str):
        """Blacklist all tokens in a family (for reuse detection)."""
        # Remove from tracking
        if family_id in self.token_families:
            del self.token_families[family_id]
        logger.warning(f"Blacklisted entire token family: {family_id}")
    
    def logout(self, refresh_token_str: str) -> bool:
        """
        Logout a user by blacklisting their refresh token.
        
        Args:
            refresh_token_str: The refresh token to blacklist
            
        Returns:
            True if successful
        """
        try:
            refresh = RefreshToken(refresh_token_str)
            jti = refresh.get("jti")
            user_id = refresh.get("user_id")
            
            if jti:
                self._blacklist_token(jti, refresh_token_str, user_id)
                logger.info(f"User {user_id} logged out, token {jti} blacklisted")
            
            return True
        except Exception as e:
            logger.error(f"Logout failed: {e}")
            return False
    
    def cleanup_expired_tokens(self) -> int:
        """
        Clean up expired tokens from the blacklist.
        
        Returns:
            Number of tokens removed
        """
        deleted_count, _ = RefreshTokenBlacklist.cleanup_expired()
        logger.info(f"Cleaned up {deleted_count} expired tokens from blacklist")
        return deleted_count


# Global instance
token_rotation_service = TokenRotationService()


def create_token_pair(user) -> Dict[str, str]:
    """Convenience function to create token pair."""
    return token_rotation_service.create_token_pair(user)


def rotate_tokens(refresh_token: str) -> Dict[str, str]:
    """Convenience function to rotate tokens."""
    return token_rotation_service.rotate_tokens(refresh_token)


def logout_user(refresh_token: str) -> bool:
    """Convenience function to logout user."""
    return token_rotation_service.logout(refresh_token)


__all__ = [
    "TokenRotationService",
    "token_rotation_service",
    "create_token_pair",
    "rotate_tokens",
    "logout_user",
]
