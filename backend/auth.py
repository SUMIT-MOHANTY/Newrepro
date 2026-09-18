from datetime import datetime, timedelta, timezone
from typing import Annotated, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from schemas import TokenData
from database import get_db
from models import User
from config import settings

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
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

async def get_current_user(token: Annotated[str, Depends(oauth2_scheme)], db: Session = Depends(get_db)):
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
        token_data = TokenData(email=email)
    except JWTError:
        raise credentials_exception
    user = db.query(User).filter(User.email == token_data.email).first()
    if user is None:
        raise credentials_exception
        
    # Dynamically inject the active organization from JWT token if available
    active_org = payload.get("org")
    if active_org:
        import models
        from sqlalchemy import func
        from sqlalchemy.orm.attributes import set_committed_value
        
        # 1. Check if user has an explicit mapping for this org
        role_mapping = db.query(models.UserOrganizationRole).filter(
            models.UserOrganizationRole.user_id == user.id,
            func.lower(models.UserOrganizationRole.organization_name) == active_org.lower()
        ).first()
        
        # 2. Check if this is the user's legacy native organization
        is_legacy_member = bool(
            user.organization_name and 
            user.organization_name.lower() == active_org.lower()
        )
        
        # 3. Security Block: Must be mapped, native, or Super Admin
        if not role_mapping and not is_legacy_member and not getattr(user, "is_super_admin", False):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"User is not a member of organization: {active_org}"
            )
            
        # 4. Apply the override context
        set_committed_value(user, "organization_name", active_org)
        
        # 5. Evaluate is_org_admin status for the active organization
        if role_mapping:
            role = db.query(models.OrganizationRole).filter(models.OrganizationRole.id == role_mapping.role_id).first()
            if role and "admin" in role.name.lower():
                set_committed_value(user, "is_org_admin", True)
            else:
                set_committed_value(user, "is_org_admin", False)
        elif is_legacy_member:
            # Keep the native user.is_org_admin value if no mapping exists but it matches their native org
            pass
        elif getattr(user, "is_super_admin", False):
            # Super Admins impersonating an org are effectively Org Admins in that context
            set_committed_value(user, "is_org_admin", True)
                
    return user


async def get_current_super_admin(
    current_user: Annotated[User, Depends(get_current_user)]
) -> User:
    """Ensure current user has Super Admin privileges."""
    if not bool(getattr(current_user, "is_super_admin", False)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super Admin privileges required"
        )
    return current_user



