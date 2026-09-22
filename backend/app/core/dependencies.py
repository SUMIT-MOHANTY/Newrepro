import os
import sys
from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from database import get_db
from auth import get_current_user
import models

def get_current_active_user(
    current_user: Annotated[models.User, Depends(get_current_user)]
) -> models.User:
    """Ensures that the current user is active."""
    return current_user

def require_superadmin(
    current_user: Annotated[models.User, Depends(get_current_user)]
) -> models.User:
    """Ensures that the current user has Super Admin privileges."""
    if not getattr(current_user, "is_super_admin", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Superadmin privileges required for this action."
        )
    return current_user

def require_org_admin(
    current_user: Annotated[models.User, Depends(get_current_user)]
) -> models.User:
    """Ensures that the current user has Organization Admin privileges."""
    is_super = bool(getattr(current_user, "is_super_admin", False))
    is_org_adm = bool(getattr(current_user, "is_org_admin", False))
    if not is_super and not is_org_adm:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Organization admin privileges required."
        )
    return current_user

__all__ = [
    "get_db",
    "get_current_user",
    "get_current_active_user",
    "require_superadmin",
    "require_org_admin",
]
