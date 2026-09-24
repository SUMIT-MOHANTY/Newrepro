"""
Backward-compatibility shim for backend/auth.py.
Authoritative implementations reside in app.core.security and app.core.dependencies.
"""
from app.core.security import (
    pwd_context,
    oauth2_scheme,
    verify_password,
    get_password_hash,
    create_access_token,
    verify_token,
)
from app.core.dependencies import (
    get_current_user,
    get_current_active_user,
    get_current_super_admin,
    require_superadmin,
    require_org_admin,
)

__all__ = [
    "pwd_context",
    "oauth2_scheme",
    "verify_password",
    "get_password_hash",
    "create_access_token",
    "verify_token",
    "get_current_user",
    "get_current_active_user",
    "get_current_super_admin",
    "require_superadmin",
    "require_org_admin",
]
