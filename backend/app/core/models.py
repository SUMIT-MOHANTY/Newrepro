"""
Core models for the Django Todo Application
Includes RefreshTokenBlacklist for JWT token management
"""
from django.db import models
import uuid


class RefreshTokenBlacklist(models.Model):
    """
    Model for storing blacklisted JWT refresh tokens.
    Used to implement token revocation on logout.
    """
    
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        verbose_name="ID"
    )
    token_jti = models.CharField(
        max_length=255,
        unique=True,
        db_index=True,
        verbose_name="token JTI",
        help_text="Unique identifier (JTI) of the JWT token"
    )
    user_id = models.UUIDField(
        null=True,
        blank=True,
        db_index=True,
        verbose_name="user ID",
        help_text="ID of the user who owned this token"
    )
    expires_at = models.DateTimeField(
        db_index=True,
        verbose_name="expires at",
        help_text="When the token expires"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="created at",
        help_text="When the token was blacklisted"
    )
    
    class Meta:
        db_table = "refresh_token_blacklist"
        verbose_name = "blacklisted refresh token"
        verbose_name_plural = "blacklisted refresh tokens"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["token_jti"], name="token_blacklist_jti_idx"),
            models.Index(fields=["expires_at"], name="token_blacklist_expires_idx"),
            models.Index(fields=["user_id"], name="token_blacklist_user_idx"),
        ]
    
    def __str__(self):
        return f"Blacklisted token {self.token_jti[:20]}..."
    
    @classmethod
    def is_blacklisted(cls, token_jti: str) -> bool:
        """Check if a token JTI is in the blacklist."""
        return cls.objects.filter(token_jti=token_jti).exists()
    
    @classmethod
    def blacklist_token(cls, token_jti: str, expires_at, user_id=None):
        """Add a token to the blacklist."""
        return cls.objects.create(
            token_jti=token_jti,
            expires_at=expires_at,
            user_id=user_id
        )
    
    @classmethod
    def cleanup_expired(cls):
        """Remove expired tokens from the blacklist."""
        from django.utils import timezone
        return cls.objects.filter(expires_at__lt=timezone.now()).delete()


__all__ = ["RefreshTokenBlacklist"]
