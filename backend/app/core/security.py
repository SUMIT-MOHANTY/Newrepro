from datetime import datetime, timedelta, timezone
from typing import Annotated, Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from sqlalchemy import func
from sqlalchemy.orm.attributes import set_committed_value

from app.core.config import settings
from app.core.database import get_db
import models

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)
    return encoded_jwt

def verify_token(token: str) -> Optional[dict]:
    """Decodes and validates a JWT token, returning payload dictionary or None."""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        return payload
    except JWTError:
        return None

async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Session = Depends(get_db)
) -> models.User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
        
    user = db.query(models.User).filter(models.User.email == email).first()
    if user is None:
        raise credentials_exception
        
    # Dynamically inject the active organization from JWT token if available
    active_org = payload.get("org")
    if active_org:
        role_mapping = db.query(models.UserOrganizationRole).filter(
            models.UserOrganizationRole.user_id == user.id,
            func.lower(models.UserOrganizationRole.organization_name) == active_org.lower()
        ).first()
        
        is_legacy_member = bool(
            user.organization_name and 
            user.organization_name.lower() == active_org.lower()
        )
        
        if not role_mapping and not is_legacy_member and not getattr(user, "is_super_admin", False):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"User is not a member of organization: {active_org}"
            )
            
        set_committed_value(user, "organization_name", active_org)
        
        if role_mapping:
            role = db.query(models.OrganizationRole).filter(models.OrganizationRole.id == role_mapping.role_id).first()
            if role and "admin" in role.name.lower():
                set_committed_value(user, "is_org_admin", True)
            else:
                set_committed_value(user, "is_org_admin", False)
        elif is_legacy_member:
            pass
        elif getattr(user, "is_super_admin", False):
            set_committed_value(user, "is_org_admin", True)
                
    return user

def get_current_active_user(
    current_user: Annotated[models.User, Depends(get_current_user)]
) -> models.User:
    """Ensures that the current user is active."""
    return current_user

async def get_current_super_admin(
    current_user: Annotated[models.User, Depends(get_current_user)]
) -> models.User:
    """Ensure current user has Super Admin privileges."""
    if not bool(getattr(current_user, "is_super_admin", False)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super Admin privileges required"
        )
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
    "verify_password",
    "get_password_hash",
    "create_access_token",
    "verify_token",
    "pwd_context",
    "oauth2_scheme",
    "get_current_user",
    "get_current_active_user",
    "get_current_super_admin",
    "require_superadmin",
    "require_org_admin",
]
