from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, EmailStr, Field


class UserBase(BaseModel):
    email: EmailStr


class UserCreate(UserBase):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    organization_name: Optional[str] = None
    password: Optional[str] = None


class User(UserBase):
    id: int
    is_active: bool
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    organization_name: Optional[str] = None
    is_org_admin: bool = False
    is_super_admin: bool = False

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str
    requires_selection: Optional[bool] = False
    organizations: Optional[List[str]] = None


class TokenData(BaseModel):
    email: Optional[str] = None


class SelectOrganizationRequest(BaseModel):
    organization_name: str


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str = Field(..., min_length=6)

    class Config:
        from_attributes = True


class OrganizationUserResponse(BaseModel):
    id: int
    email: EmailStr
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    role_name: Optional[str] = None
    last_login: Optional[datetime] = None
    is_org_admin: bool = False

    class Config:
        from_attributes = True


class OrganizationSSOSettingsUpdate(BaseModel):
    sso_provider: Optional[str] = None
    tenant_id: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    authority_url: Optional[str] = None
    redirect_uri: Optional[str] = None
    logout_url: Optional[str] = None
    scopes: Optional[str] = None
    domain_hint: Optional[str] = None
    sso_enabled: bool = False


class OrganizationSSOSettingsResponse(OrganizationSSOSettingsUpdate):
    organization_name: str
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


__all__ = [
    "UserBase",
    "UserCreate",
    "User",
    "Token",
    "TokenData",
    "SelectOrganizationRequest",
    "PasswordResetRequest",
    "PasswordResetConfirm",
    "OrganizationUserResponse",
    "OrganizationSSOSettingsUpdate",
    "OrganizationSSOSettingsResponse",
]
