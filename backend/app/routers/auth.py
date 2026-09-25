"""
DSuite BRD Analyzer - Domain Router: Authentication & RBAC & Invites
Auto-extracted enterprise clean architecture domain router.
"""

import asyncio
import base64
import concurrent.futures
import hashlib
import html as html_lib
import hmac
import ipaddress
import json
import logging
import os
import re
import secrets
import time
import urllib.parse
import uuid
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Annotated, Any, Dict, List, Optional, Union
from urllib.parse import parse_qsl, urlencode, urlparse, urlsplit, urlunsplit

import httpx
import requests
from fastapi import (
    APIRouter, Depends, File, Form, Header, HTTPException, Query,
    Request, Response, UploadFile, WebSocket, WebSocketDisconnect, status
)
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, or_, text
from sqlalchemy.orm import Session

from app.core import security as auth
import models
import schemas
from app.core.config import settings
from app.core.database import SessionLocal, engine, get_db
from app.services import email_service
from app.routers.helpers import _normalize_agent_kind, _normalize_project_token



logger = logging.getLogger(__name__)

router = APIRouter(tags=["Authentication & RBAC"])

SSO_DEFAULT_SCOPES = "openid profile email"
SSO_STATE_TTL_SECONDS = 1800
SSO_STATE_CLOCK_SKEW_SECONDS = 300

def _generate_registration_password() -> str:
    return secrets.token_urlsafe(12)

# --- Extracted Block (Lines 1452-2027) ---
@router.post("/token", response_model=schemas.Token)
async def login_for_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Session = Depends(get_db),
):
    user = db.query(models.User).filter(func.lower(models.User.email) == form_data.username.strip().lower()).first()
    if not user or not auth.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Resolve all organizations this user is associated with
    org_mappings = db.query(models.UserOrganizationRole).filter(models.UserOrganizationRole.user_id == user.id).all()
    orgs = list(set([m.organization_name for m in org_mappings if m.organization_name]))
    if user.organization_name and user.organization_name not in orgs:
        orgs.append(user.organization_name)

    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)

    if len(orgs) > 1:
        # Create a temporary token for organization selection (sub only, no org)
        temp_token = auth.create_access_token(
            data={"sub": user.email.strip().lower()}, expires_delta=timedelta(minutes=60)
        )
        return {
            "access_token": temp_token,
            "token_type": "bearer",
            "requires_selection": True,
            "organizations": orgs
        }

    # If they belong to exactly one organization, bind it directly to the token
    active_org = orgs[0] if orgs else (user.organization_name or "Default Organization")

    access_token = auth.create_access_token(
        data={"sub": user.email, "org": active_org}, expires_delta=access_token_expires
    )

    user.last_login = datetime.now(timezone.utc)
    db.add(user)
    db.commit()
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "requires_selection": False,
        "organizations": [active_org]
    }

oauth2_scheme_optional = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)

@router.post("/auth/select-organization", response_model=schemas.Token)
async def select_organization(
    payload: schemas.SelectOrganizationRequest,
    db: Session = Depends(get_db),
    token_from_header: Optional[str] = Depends(oauth2_scheme_optional),
):
    token = token_from_header or payload.temp_token
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user_payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        email = user_payload.get("sub")
        if not email:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
    except JWTError as e:
        logger.warning(f"select-organization JWT error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    current_user = db.query(models.User).filter(
        func.lower(func.trim(models.User.email)) == email.strip().lower()
    ).first()
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    org_name = payload.organization_name.strip()
    
    org_mappings = db.query(models.UserOrganizationRole).filter(
        models.UserOrganizationRole.user_id == current_user.id
    ).all()
    orgs = list(set([m.organization_name.strip() for m in org_mappings if m.organization_name and m.organization_name.strip()]))
    if current_user.organization_name and current_user.organization_name.strip() not in orgs:
        orgs.append(current_user.organization_name.strip())
        
    matching_org = next((o for o in orgs if o.strip().lower() == org_name.lower()), None)
    if not matching_org:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this organization."
        )
        
    # Update active organization in database for this user
    current_user.organization_name = matching_org
    current_user.last_login = datetime.now(timezone.utc)
    
    # Update is_org_admin based on role in the selected organization
    role_mapping = db.query(models.UserOrganizationRole).filter(
        models.UserOrganizationRole.user_id == current_user.id,
        func.lower(func.trim(models.UserOrganizationRole.organization_name)) == matching_org.lower()
    ).first()
    if role_mapping:
        role = db.query(models.OrganizationRole).filter(models.OrganizationRole.id == role_mapping.role_id).first()
        if role and "admin" in role.name.lower():
            current_user.is_org_admin = True
        else:
            current_user.is_org_admin = False
    elif getattr(current_user, "is_super_admin", False):
        current_user.is_org_admin = True

    db.add(current_user)
    db.commit()
    db.refresh(current_user)

    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    access_token = auth.create_access_token(
        data={"sub": current_user.email, "org": matching_org},
        expires_delta=access_token_expires
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "requires_selection": False,
        "organizations": [matching_org]
    }

@router.post("/auth/forgot-password")
async def forgot_password(
    payload: schemas.PasswordResetRequest,
    db: Session = Depends(get_db)
):
    normalized_email = payload.email.strip().lower()

    user = db.query(models.User).filter(func.lower(models.User.email) == normalized_email).first()

    if not user:
        return {"message": "This email is not registered with us"}
    
    token = secrets.token_urlsafe(32)
    token_hash = _hash_invite_token(token)
    expires_at = datetime.utcnow() + timedelta(hours=1)

    # Deactivate previous unused tokens
    db.query(models.PasswordReset).filter(
        models.PasswordReset.user_id == user.id,
        models.PasswordReset.used_at == None
    ).update(
        {"expires_at": datetime.utcnow()},
        synchronize_session=False
    )

    reset = models.PasswordReset(
        user_id = user.id,
        token_hash = token_hash,
        expires_at = expires_at
    )

    db.add(reset)
    db.commit()

    reset_url = (
        f"{settings.frontend_url.rstrip('/')}"
        f"/reset-password?token={token}"
    )

    try:
        email_service.send_password_reset_email(
            user.email,
            reset_url
        )
    except Exception:
        logger.exception(
            "Failed to send password reset email to %s",
            user.email
        )
    
    return {
        "message": "Password reset email sent successfully."
    }

@router.post("/auth/reset-password")
async def reset_password(
    payload: schemas.PasswordResetConfirm,
    db: Session = Depends(get_db)
):
    token_hash = _hash_invite_token(payload.token)
    reset = db.query(models.PasswordReset).filter(
        models.PasswordReset.token_hash == token_hash,
        models.PasswordReset.used_at == None,
        models.PasswordReset.expires_at > datetime.utcnow()
    ).first()
    
    if not reset:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token.")
    
    user = db.query(models.User).filter(models.User.id == reset.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    
    user.hashed_password = auth.get_password_hash(payload.new_password)
    reset.used_at = datetime.utcnow()
    db.commit()
    
    return {"message": "Password has been reset successfully."}

def _normalized_text(value: Optional[str]) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()

def _find_sso_setting_by_organization(
    db: Session,
    organization_name: str,
) -> Optional[models.OrganizationSSOSetting]:
    org_name = _normalized_text(organization_name)
    if not org_name:
        return None
    return db.query(models.OrganizationSSOSetting).filter(
        func.lower(models.OrganizationSSOSetting.organization_name) == org_name.lower()
    ).first()

def _find_sso_setting_by_domain(
    db: Session,
    domain: str,
) -> Optional[models.OrganizationSSOSetting]:
    cleaned_domain = _normalized_text(domain).lower()
    if not cleaned_domain:
        return None
    matches = db.query(models.OrganizationSSOSetting).filter(
        models.OrganizationSSOSetting.sso_enabled.is_(True),
        func.lower(models.OrganizationSSOSetting.domain_hint) == cleaned_domain,
    ).all()
    if len(matches) > 1:
        raise HTTPException(
            status_code=400,
            detail="Multiple organizations are mapped to this email domain. Contact your administrator.",
        )
    return matches[0] if matches else None

def _resolve_login_sso_setting(
    payload: schemas.SSOStartRequest,
    db: Session,
) -> tuple[models.OrganizationSSOSetting, str, str]:
    email_hint = _normalized_text(payload.email).lower()
    requested_org_name = _normalized_text(payload.organization_name)

    setting: Optional[models.OrganizationSSOSetting] = None
    resolved_org_name = ""

    if email_hint:
        user = db.query(models.User).filter(func.lower(models.User.email) == email_hint).first()
        if user and _normalized_text(user.organization_name):
            resolved_org_name = _normalized_text(user.organization_name)
            setting = _find_sso_setting_by_organization(db, resolved_org_name)

        if not setting and "@" in email_hint:
            domain = email_hint.split("@", 1)[1]
            setting = _find_sso_setting_by_domain(db, domain)
            if setting:
                resolved_org_name = setting.organization_name

    if not setting and requested_org_name:
        setting = _find_sso_setting_by_organization(db, requested_org_name)
        if setting:
            resolved_org_name = setting.organization_name

    if not setting:
        raise HTTPException(
            status_code=404,
            detail="No SSO-enabled organization found for this account.",
        )
    if not setting.sso_enabled:
        raise HTTPException(status_code=400, detail="SSO is disabled for this organization.")
    if not _normalized_text(setting.client_id):
        raise HTTPException(status_code=400, detail="Organization SSO client ID is not configured.")
    if not _normalized_text(setting.client_secret):
        raise HTTPException(status_code=400, detail="Organization SSO client secret is not configured.")
    # Authority URL is now derived in the backend from tenant / environment,
    # so we no longer block if the stored authority_url is empty here.

    return setting, resolved_org_name, email_hint

def _resolve_sso_redirect_uri(
    setting: models.OrganizationSSOSetting,
    request: Request,
) -> str:
    configured = _normalized_text(setting.redirect_uri)
    if configured:
        return configured
    return str(request.url_for("sso_callback"))

def _build_frontend_sso_redirect(
    *,
    token: Optional[str] = None,
    error: Optional[str] = None,
    next_url: Optional[str] = None,
) -> str:
    base_url = f"{settings.frontend_url.rstrip('/')}/sso/callback"
    params: Dict[str, str] = {}
    if token:
        params["token"] = token
    if error:
        params["error"] = error
    if next_url:
        params["next"] = next_url
    if not params:
        return base_url
    return f"{base_url}?{urlencode(params)}"

async def _fetch_oidc_metadata(setting: models.OrganizationSSOSetting) -> Dict[str, str]:
    authority_url = _normalized_text(setting.authority_url)
    if not authority_url:
        # Derive a default authority URL from tenant_id if available (Azure AD / Entra ID)
        tenant = _normalized_text(setting.tenant_id)
        if tenant:
            authority_url = f"https://login.microsoftonline.com/{tenant}"
        else:
            raise HTTPException(status_code=400, detail="Organization authority URL is missing.")

    if "/.well-known/openid-configuration" in authority_url:
        metadata_url = authority_url
        authority_base = authority_url.split("/.well-known/openid-configuration", 1)[0].rstrip("/")
    else:
        authority_base = authority_url.rstrip("/")
        metadata_url = f"{authority_base}/.well-known/openid-configuration"

    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            metadata_response = await client.get(metadata_url)
            metadata_response.raise_for_status()
        metadata = metadata_response.json()
    except Exception as exc:
        if _normalized_text(setting.sso_provider).lower() == "azure_ad":
            return {
                "authorization_endpoint": f"{authority_base}/oauth2/v2.0/authorize",
                "token_endpoint": f"{authority_base}/oauth2/v2.0/token",
                "userinfo_endpoint": "",
            }
        raise HTTPException(
            status_code=400,
            detail=f"Unable to fetch provider metadata from {metadata_url}. {str(exc)}",
        )

    authorization_endpoint = _normalized_text(metadata.get("authorization_endpoint"))
    token_endpoint = _normalized_text(metadata.get("token_endpoint"))
    userinfo_endpoint = _normalized_text(metadata.get("userinfo_endpoint"))

    if not authorization_endpoint or not token_endpoint:
        raise HTTPException(
            status_code=400,
            detail="OIDC provider metadata is missing authorization/token endpoints.",
        )

    return {
        "authorization_endpoint": authorization_endpoint,
        "token_endpoint": token_endpoint,
        "userinfo_endpoint": userinfo_endpoint,
    }

def _extract_email_from_claims(claims: Dict[str, Any]) -> str:
    return _normalized_text(
        claims.get("email")
        or claims.get("preferred_username")
        or claims.get("upn")
        or claims.get("unique_name")
    )

async def _fetch_userinfo_claims(userinfo_endpoint: str, access_token: str) -> Dict[str, Any]:
    endpoint = _normalized_text(userinfo_endpoint)
    token = _normalized_text(access_token)
    if not endpoint or not token:
        return {}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                endpoint,
                headers={"Authorization": f"Bearer {token}"},
            )
        if response.status_code >= 400:
            return {}
        payload = response.json()
        if isinstance(payload, dict):
            return payload
    except Exception:
        return {}
    return {}

def _validate_sso_state_window(state_payload: Dict[str, Any]) -> bool:
    try:
        exp_ts = int(state_payload.get("exp"))
        iat_ts = int(state_payload.get("iat"))
    except (TypeError, ValueError):
        return False

    now_ts = int(datetime.now(timezone.utc).timestamp())
    if exp_ts + SSO_STATE_CLOCK_SKEW_SECONDS < now_ts:
        return False
    if iat_ts - SSO_STATE_CLOCK_SKEW_SECONDS > now_ts:
        return False
    return True

@router.post("/auth/sso/start", response_model=schemas.SSOStartResponse)
async def start_sso_login(
    payload: schemas.SSOStartRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    if not payload.email and not _normalized_text(payload.organization_name):
        raise HTTPException(status_code=400, detail="Email or organization name is required.")

    setting, organization_name, email_hint = _resolve_login_sso_setting(payload, db)
    metadata = await _fetch_oidc_metadata(setting)
    redirect_uri = _resolve_sso_redirect_uri(setting, request)
    nonce = secrets.token_urlsafe(16)

    now = datetime.now(timezone.utc)
    state_payload = {
        "org": organization_name,
        "email_hint": email_hint or None,
        "nonce": nonce,
        "redirect_uri": redirect_uri,
        "next": _normalized_text(payload.next) or None,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=SSO_STATE_TTL_SECONDS)).timestamp()),
    }
    state_token = jwt.encode(state_payload, settings.secret_key, algorithm=settings.algorithm)

    query_params = {
        "client_id": setting.client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "response_mode": "query",
        "scope": _normalized_text(setting.scopes) or SSO_DEFAULT_SCOPES,
        "state": state_token,
        "nonce": nonce,
    }
    if email_hint:
        query_params["login_hint"] = email_hint
    if _normalized_text(setting.domain_hint):
        query_params["domain_hint"] = _normalized_text(setting.domain_hint)

    auth_url = f"{metadata['authorization_endpoint']}?{urlencode(query_params)}"
    return schemas.SSOStartResponse(auth_url=auth_url)

@router.get("/auth/sso/callback")
async def sso_callback(
    request: Request,
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
    error_description: Optional[str] = None,
    db: Session = Depends(get_db),
):
    if error:
        message = _normalized_text(error_description) or _normalized_text(error) or "SSO sign-in failed."
        return RedirectResponse(url=_build_frontend_sso_redirect(error=message), status_code=302)

    if not code or not state:
        return RedirectResponse(
            url=_build_frontend_sso_redirect(error="Missing authorization code or state."),
            status_code=302,
        )

    try:
        state_payload = jwt.decode(
            state,
            settings.secret_key,
            algorithms=[settings.algorithm],
            options={"verify_exp": False, "verify_aud": False},
        )
    except JWTError as exc:
        logger.warning("SSO state decode failed: %s", exc)
        return RedirectResponse(
            url=_build_frontend_sso_redirect(error="Invalid SSO state. Please try Sign in with SSO again."),
            status_code=302,
        )
    if not _validate_sso_state_window(state_payload):
        return RedirectResponse(
            url=_build_frontend_sso_redirect(error="SSO state expired. Please click Sign in with SSO again."),
            status_code=302,
        )

    organization_name = _normalized_text(state_payload.get("org"))
    if not organization_name:
        return RedirectResponse(
            url=_build_frontend_sso_redirect(error="Invalid organization context in SSO state."),
            status_code=302,
        )

    setting = _find_sso_setting_by_organization(db, organization_name)
    if not setting or not setting.sso_enabled:
        return RedirectResponse(
            url=_build_frontend_sso_redirect(error="Organization SSO is not available."),
            status_code=302,
        )

    try:
        metadata = await _fetch_oidc_metadata(setting)
    except HTTPException as exc:
        return RedirectResponse(
            url=_build_frontend_sso_redirect(error=str(exc.detail)),
            status_code=302,
        )

    redirect_uri = _normalized_text(state_payload.get("redirect_uri")) or _resolve_sso_redirect_uri(setting, request)
    token_payload = {
        "grant_type": "authorization_code",
        "client_id": _normalized_text(setting.client_id),
        "client_secret": _normalized_text(setting.client_secret),
        "code": code,
        "redirect_uri": redirect_uri,
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            token_response = await client.post(
                metadata["token_endpoint"],
                data=token_payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        if token_response.status_code >= 400:
            truncated_error = token_response.text[:300] or "Token exchange failed."
            return RedirectResponse(
                url=_build_frontend_sso_redirect(error=f"SSO token exchange failed. {truncated_error}"),
                status_code=302,
            )
        token_data = token_response.json()
    except Exception as exc:
        return RedirectResponse(
            url=_build_frontend_sso_redirect(error=f"Unable to complete SSO token exchange. {str(exc)}"),
            status_code=302,
        )

    claims: Dict[str, Any] = {}
    id_token = token_data.get("id_token")
    if id_token:
        try:
            claims = jwt.get_unverified_claims(id_token) or {}
        except Exception:
            claims = {}

    expected_nonce = _normalized_text(state_payload.get("nonce"))
    id_token_nonce = _normalized_text(claims.get("nonce"))
    if expected_nonce and id_token_nonce and expected_nonce != id_token_nonce:
        return RedirectResponse(
            url=_build_frontend_sso_redirect(error="SSO nonce validation failed."),
            status_code=302,
        )

    email = _extract_email_from_claims(claims)
    if not email:
        userinfo_claims = await _fetch_userinfo_claims(
            metadata.get("userinfo_endpoint", ""),
            token_data.get("access_token", ""),
        )
        if userinfo_claims:
            merged_claims = dict(userinfo_claims)
            merged_claims.update(claims)
            claims = merged_claims
            email = _extract_email_from_claims(claims)

    if not email:
        email = _normalized_text(state_payload.get("email_hint"))

    if not email:
        return RedirectResponse(
            url=_build_frontend_sso_redirect(error="Unable to determine user email from SSO provider."),
            status_code=302,
        )

    normalized_email = email.lower()
    first_name = _normalized_text(claims.get("given_name")) or None
    last_name = _normalized_text(claims.get("family_name")) or None

    user = db.query(models.User).filter(func.lower(models.User.email) == normalized_email).first()
    if user:
        existing_org = _normalized_text(user.organization_name)
        if existing_org and existing_org.lower() != organization_name.lower():
            return RedirectResponse(
                url=_build_frontend_sso_redirect(error="This account belongs to a different organization."),
                status_code=302,
            )
        if not existing_org:
            user.organization_name = organization_name
        if not user.first_name and first_name:
            user.first_name = first_name
        if not user.last_name and last_name:
            user.last_name = last_name
    else:
        # Generate a random password because this user signs in through SSO.
        generated_password = secrets.token_urlsafe(32)
        user = models.User(
            email=normalized_email,
            hashed_password=auth.get_password_hash(generated_password),
            first_name=first_name,
            last_name=last_name,
            organization_name=organization_name,
            is_org_admin=False,
        )
        db.add(user)

    user.last_login = datetime.utcnow()
    db.add(user)
    db.commit()
    db.refresh(user)

    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    app_access_token = auth.create_access_token(
        data={"sub": user.email},
        expires_delta=access_token_expires,
    )
    next_url = _normalized_text(state_payload.get("next")) or None
    return RedirectResponse(
        url=_build_frontend_sso_redirect(token=app_access_token, next_url=next_url),
        status_code=302,
    )


# --- Extracted Block (Lines 2634-2804) ---
def _require_org_admin(current_user: models.User) -> str:
    if not current_user.is_org_admin:
        raise HTTPException(status_code=403, detail="Organization admin access required")
    organization_name = (current_user.organization_name or "").strip()
    if not organization_name:
        raise HTTPException(status_code=400, detail="Organization not configured for this account")
    return organization_name

def _require_organization(current_user: models.User) -> str:
    organization_name = _normalized_text(getattr(current_user, "organization_name", None))
    if not organization_name:
        raise HTTPException(status_code=400, detail="Organization not configured for this account")
    return organization_name

# --- Org-scoped project visibility ---

def _org_user_ids_subquery(db: Session, organization_name: str):
    org = _normalized_text(organization_name)
    if not org:
        return None
    return db.query(models.User.id).filter(
        func.lower(models.User.organization_name) == org.lower()
    ).scalar_subquery()


def _governance_query_for_user(db: Session, user: models.User):
    """
    Build a GovernanceResponse query scoped to the user's organization (if org exists),
    falling back to personal-scope only if the user has no organization.
    This ensures org members can see and act on each other's projects.
    """
    org = _normalized_text(getattr(user, "organization_name", None))
    if not org:
        return db.query(models.GovernanceResponse).filter(
            models.GovernanceResponse.owner_id == user.id
        )
    org_user_ids = _org_user_ids_subquery(db, org)
    return db.query(models.GovernanceResponse).filter(
        models.GovernanceResponse.owner_id.in_(org_user_ids)
    )


# --- Organization RBAC + Invites ---

ORG_MANAGED_PAGES: list[schemas.OrganizationPage] = [
    schemas.OrganizationPage(path="/status-dashboard", label="Status Dashboard"),
    schemas.OrganizationPage(path="/dashboard", label="Requirements Analyzer"),
    schemas.OrganizationPage(path="/new-project", label="New Project (wizard)"),
    schemas.OrganizationPage(path="/new-project/governance", label="Governance"),
    schemas.OrganizationPage(path="/agent-analysis", label="Agent Analysis"),
    schemas.OrganizationPage(path="/prerequisites", label="Prerequisites"),
    schemas.OrganizationPage(path="/task-creation", label="Task Creation"),
    schemas.OrganizationPage(path="/resource-onboarding", label="Resource Onboarding"),
    schemas.OrganizationPage(path="/agents", label="Agents"),
    schemas.OrganizationPage(path="/plugins", label="Plugins"),
    schemas.OrganizationPage(path="/organization-admin", label="Organization Admin"),
    schemas.OrganizationPage(path="/governance-management", label="Governance Management"),
    schemas.OrganizationPage(path="/billing", label="Billing & Activity"),
    schemas.OrganizationPage(path="/tickets", label="Support Tickets"),
]

def _hash_invite_token(token: str) -> str:
    normalized = _normalized_text(token)
    if not normalized:
        return ""
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

def _ensure_default_rbac_roles(db: Session, organization_name: str) -> None:
    """
    Ensure an org has a baseline 'Member' role used for non-admin accounts.
    Org admins (User.is_org_admin) are treated as super-admins regardless of role assignments.
    """
    org = _normalized_text(organization_name)
    if not org:
        return
    existing = db.query(models.OrganizationRole).filter(
        func.lower(models.OrganizationRole.organization_name) == org.lower()
    ).first()
    if existing:
        return

    # Default member role: all authenticated pages except organization admin.
    member_paths = [p.path for p in ORG_MANAGED_PAGES if p.path != "/organization-admin"]
    member = models.OrganizationRole(
        organization_name=org,
        name="Member",
        description="Default role for organization members.",
        is_system=True,
    )
    db.add(member)
    db.commit()
    db.refresh(member)
    for path in member_paths:
        db.add(models.OrganizationRolePermission(role_id=member.id, path=path))
    db.commit()

def _role_to_response(role: models.OrganizationRole) -> schemas.OrganizationRoleResponse:
    allowed_paths = sorted({(perm.path or "").strip() for perm in (role.permissions or []) if (perm.path or "").strip()})
    return schemas.OrganizationRoleResponse(
        id=role.id,
        organization_name=role.organization_name,
        name=role.name,
        description=role.description,
        allowed_paths=allowed_paths,
        is_system=bool(role.is_system),
        created_at=getattr(role, "created_at", None),
        updated_at=getattr(role, "updated_at", None),
    )

def _get_user_allowed_paths(db: Session, user: models.User) -> tuple[Optional[str], list[str]]:
    """
    Returns (role_name, allowed_paths).
    - Org admins: all managed pages
    - Non-admins: role-mapped allowed paths; if missing, assign default 'Member' role
    """
    org = _normalized_text(getattr(user, "organization_name", None))
    if not org:
        return None, []

    if bool(getattr(user, "is_super_admin", False)):
        superadmin_paths = [p.path for p in ORG_MANAGED_PAGES] + [
            "/superadmin/dashboard",
            "/superadmin/requests",
            "/superadmin/organizations",
            "/superadmin/billing",
            "/superadmin/global-billing",
            "/superadmin/roles",
            "/superadmin/capacity",
            "/superadmin/logs",
            "/superadmin/tickets",
        ]
        return "Super Admin", superadmin_paths

    if bool(getattr(user, "is_org_admin", False)):
        return "Admin", [p.path for p in ORG_MANAGED_PAGES]

    _ensure_default_rbac_roles(db, org)
    mapping = db.query(models.UserOrganizationRole).filter(
        models.UserOrganizationRole.user_id == user.id,
        func.lower(models.UserOrganizationRole.organization_name) == org.lower(),
    ).first()

    if not mapping:
        member = db.query(models.OrganizationRole).filter(
            func.lower(models.OrganizationRole.organization_name) == org.lower(),
            func.lower(models.OrganizationRole.name) == "member",
        ).first()
        if member:
            mapping = models.UserOrganizationRole(user_id=user.id, organization_name=org, role_id=member.id)
            db.add(mapping)
            db.commit()
            db.refresh(mapping)

    if not mapping:
        return None, ["/tickets"]

    role = db.query(models.OrganizationRole).filter(models.OrganizationRole.id == mapping.role_id).first()
    if not role:
        return None, ["/tickets"]

    allowed_paths = sorted({(perm.path or "").strip() for perm in (role.permissions or []) if (perm.path or "").strip()})
    if "/tickets" not in allowed_paths:
        allowed_paths.append("/tickets")
    return role.name, allowed_paths

def _can_manage_governance(db: Session, user: models.User) -> bool:
    if bool(getattr(user, "is_org_admin", False)):
        return True
    _, allowed_paths = _get_user_allowed_paths(db, user)
    return "/governance-management" in (allowed_paths or [])


# --- Extracted Block (Lines 4284-4543) ---
@router.get("/organization/rbac/pages", response_model=list[schemas.OrganizationPage])
def list_org_pages(
    current_user: Annotated[models.User, Depends(auth.get_current_user)],
):
    # Admin UI helper (no authz beyond being logged in)
    return ORG_MANAGED_PAGES

@router.get("/organization/rbac/me", response_model=schemas.OrganizationRbacMeResponse)
def organization_rbac_me(
    current_user: Annotated[models.User, Depends(auth.get_current_user)],
    db: Session = Depends(get_db),
):
    org = _normalized_text(getattr(current_user, "organization_name", None)) or None
    role_name, allowed_paths = _get_user_allowed_paths(db, current_user)
    return schemas.OrganizationRbacMeResponse(
        is_org_admin=bool(getattr(current_user, "is_org_admin", False)),
        organization_name=org,
        role_name=role_name,
        allowed_paths=allowed_paths,
    )

@router.get("/organization/rbac/roles", response_model=list[schemas.OrganizationRoleResponse])
def list_org_roles(
    current_user: Annotated[models.User, Depends(auth.get_current_user)],
    db: Session = Depends(get_db),
):
    organization_name = _require_org_admin(current_user)
    _ensure_default_rbac_roles(db, organization_name)
    roles = db.query(models.OrganizationRole).filter(
        func.lower(models.OrganizationRole.organization_name) == organization_name.lower()
    ).order_by(models.OrganizationRole.name.asc()).all()
    return [_role_to_response(r) for r in roles]

@router.post("/organization/rbac/roles", response_model=schemas.OrganizationRoleResponse)
def create_org_role(
    payload: schemas.OrganizationRoleUpsert,
    current_user: Annotated[models.User, Depends(auth.get_current_user)],
    db: Session = Depends(get_db),
):
    organization_name = _require_org_admin(current_user)
    _ensure_default_rbac_roles(db, organization_name)
    role = models.OrganizationRole(
        organization_name=organization_name,
        name=_normalized_text(payload.name),
        description=_normalized_text(payload.description) or None,
        is_system=False,
    )
    db.add(role)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=400, detail="Role name already exists for this organization.")
    db.refresh(role)

    allowed = sorted({p for p in (payload.allowed_paths or []) if _normalized_text(p)})
    managed_paths = {p.path for p in ORG_MANAGED_PAGES}
    for path in allowed:
        if path not in managed_paths:
            continue
        db.add(models.OrganizationRolePermission(role_id=role.id, path=path))
    db.commit()
    db.refresh(role)
    return _role_to_response(role)

@router.put("/organization/rbac/roles/{role_id}", response_model=schemas.OrganizationRoleResponse)
def update_org_role(
    role_id: int,
    payload: schemas.OrganizationRoleUpsert,
    current_user: Annotated[models.User, Depends(auth.get_current_user)],
    db: Session = Depends(get_db),
):
    organization_name = _require_org_admin(current_user)
    role = db.query(models.OrganizationRole).filter(
        models.OrganizationRole.id == role_id,
        func.lower(models.OrganizationRole.organization_name) == organization_name.lower(),
    ).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found.")
    if role.is_system:
        # allow updating permissions/description, but keep the name stable
        role.description = _normalized_text(payload.description) or None
    else:
        role.name = _normalized_text(payload.name) or role.name
        role.description = _normalized_text(payload.description) or None

    # Replace permissions
    db.query(models.OrganizationRolePermission).filter(models.OrganizationRolePermission.role_id == role.id).delete()
    managed_paths = {p.path for p in ORG_MANAGED_PAGES}
    allowed = sorted({p for p in (payload.allowed_paths or []) if _normalized_text(p)})
    for path in allowed:
        if path not in managed_paths:
            continue
        db.add(models.OrganizationRolePermission(role_id=role.id, path=path))
    db.add(role)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(status_code=400, detail="Unable to update role (possible duplicate name).")
    db.refresh(role)
    return _role_to_response(role)

@router.delete("/organization/rbac/roles/{role_id}")
def delete_org_role(
    role_id: int,
    current_user: Annotated[models.User, Depends(auth.get_current_user)],
    db: Session = Depends(get_db),
):
    organization_name = _require_org_admin(current_user)
    role = db.query(models.OrganizationRole).filter(
        models.OrganizationRole.id == role_id,
        func.lower(models.OrganizationRole.organization_name) == organization_name.lower(),
    ).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found.")
    if role.is_system:
        raise HTTPException(status_code=400, detail="System roles cannot be deleted.")

    in_use = db.query(models.UserOrganizationRole).filter(models.UserOrganizationRole.role_id == role.id).first()
    if in_use:
        raise HTTPException(status_code=400, detail="Role is assigned to one or more users.")

    db.delete(role)
    db.commit()
    return {"ok": True}

@router.post("/organization/rbac/request-access")
async def request_access(
    request: schemas.AccessRequest,
    current_user: Annotated[models.User, Depends(auth.get_current_user)],
    db: Session = Depends(get_db)
):
    if not current_user.organization_name:
        raise HTTPException(status_code=400, detail="User not associated with an organization")
    
    # Super admins as recipients
    admins = db.query(models.User).filter(
        models.User.organization_name == current_user.organization_name,
        models.User.is_org_admin == True
    ).all()
    
    # Find roles that have this path
    roles_with_access = db.query(models.OrganizationRole).join(models.OrganizationRolePermission).filter(
        models.OrganizationRole.organization_name == current_user.organization_name,
        models.OrganizationRolePermission.path == request.path
    ).all()
    
    role_ids = [r.id for r in roles_with_access]
    users_with_roles = []
    if role_ids:
        users_with_roles = db.query(models.User).join(models.UserOrganizationRole).filter(
            models.UserOrganizationRole.role_id.in_(role_ids)
        ).all()
    
    # Combine recipients
    recipients = {u.email for u in admins} | {u.email for u in users_with_roles}
    
    if not recipients:
        raise HTTPException(status_code=404, detail="No authorized users found to receive this request")

    requester_name = f"{current_user.first_name or ''} {current_user.last_name or ''}".strip() or current_user.email
    
    sent_count = 0
    for email in recipients:
        try:
            email_service.send_access_request_email(
                recipient_email=email,
                requester_name=requester_name,
                requester_email=current_user.email,
                organization_name=current_user.organization_name,
                section_name=request.section_name
            )
            sent_count += 1
        except Exception as e:
            logger.error(f"Failed to send access request email to {email}: {e}")
            
    return {"status": "success", "message": f"Access request sent to {sent_count} administrators"}

@router.get("/organization/rbac/page-access-info")
def get_page_access_info(
    path: str,
    current_user: Annotated[models.User, Depends(auth.get_current_user)],
    db: Session = Depends(get_db)
):
    if not current_user.organization_name:
        raise HTTPException(status_code=400, detail="User not associated with an organization")
    
    # Find roles in this org that have this path permission
    roles = db.query(models.OrganizationRole).join(models.OrganizationRolePermission).filter(
        models.OrganizationRole.organization_name == current_user.organization_name,
        models.OrganizationRolePermission.path == path
    ).all()
    
    role_names = [r.name for r in roles]
    return {"path": path, "role_names": role_names}

@router.get("/organization/invites", response_model=list[schemas.OrganizationInviteResponse])
def list_org_invites(
    current_user: Annotated[models.User, Depends(auth.get_current_user)],
    db: Session = Depends(get_db),
):
    organization_name = _require_org_admin(current_user)
    invites = db.query(models.OrganizationInvite).join(models.OrganizationRole).filter(
        func.lower(models.OrganizationInvite.organization_name) == organization_name.lower()
    ).order_by(models.OrganizationInvite.created_at.desc()).limit(100).all()

    response: list[schemas.OrganizationInviteResponse] = []
    for inv in invites:
        role = db.query(models.OrganizationRole).filter(models.OrganizationRole.id == inv.role_id).first()
        response.append(
            schemas.OrganizationInviteResponse(
                id=inv.id,
                organization_name=inv.organization_name,
                email=inv.email,
                role_id=inv.role_id,
                role_name=role.name if role else "Unknown",
                invite_url="",  # do not re-emit token links from the list
                expires_at=inv.expires_at,
                accepted_at=inv.accepted_at,
                created_at=inv.created_at,
            )
        )
    return response

@router.get("/organization/users", response_model=list[schemas.OrganizationUserResponse])
def list_org_users(
    current_user: Annotated[models.User, Depends(auth.get_current_user)],
    db: Session = Depends(get_db),
):
    organization_name = _require_org_admin(current_user)
    users = db.query(models.User).filter(
        func.lower(models.User.organization_name) == organization_name.lower()
    ).all()
    
    response = []
    for user in users:
        # Get role from mapping
        mapping = db.query(models.UserOrganizationRole).filter(
            models.UserOrganizationRole.user_id == user.id,
            func.lower(models.UserOrganizationRole.organization_name) == organization_name.lower()
        ).first()
        
        role_name = "Organization Admin" if user.is_org_admin else "No Role Assigned"
        if mapping:
            role = db.query(models.OrganizationRole).filter(models.OrganizationRole.id == mapping.role_id).first()
            if role:
                role_name = role.name
        
        response.append(schemas.OrganizationUserResponse(
            id=user.id,
            email=user.email,
            first_name=user.first_name,
            last_name=user.last_name,
            role_name=role_name,
            last_login=user.last_login,
            is_org_admin=user.is_org_admin
        ))
    return response


# --- Extracted Block (Lines 5270-5715) ---
@router.get("/organization/invites/preview", response_model=schemas.OrganizationInvitePreviewResponse)
def preview_org_invite(
    token: str,
    db: Session = Depends(get_db),
):
    token_hash = _hash_invite_token(token)
    if not token_hash:
        raise HTTPException(status_code=400, detail="Invalid invite token.")

    invite = db.query(models.OrganizationInvite).filter(models.OrganizationInvite.token_hash == token_hash).first()
    if not invite:
        raise HTTPException(status_code=404, detail="Invite not found.")

    role = db.query(models.OrganizationRole).filter(models.OrganizationRole.id == invite.role_id).first()
    role_name = role.name if role else "Unknown"

    user_exists = False
    first_name = ""
    last_name = ""
    if invite.email:
        existing_user = db.query(models.User).filter(
            func.lower(func.trim(models.User.email)) == invite.email.strip().lower()
        ).first()
        if existing_user:
            user_exists = True
            first_name = existing_user.first_name or ""
            last_name = existing_user.last_name or ""

    return schemas.OrganizationInvitePreviewResponse(
        organization_name=invite.organization_name,
        email=invite.email,
        role_name=role_name,
        expires_at=invite.expires_at,
        accepted_at=invite.accepted_at,
        user_exists=user_exists,
        first_name=first_name,
        last_name=last_name,
    )


@router.get("/organization/invites/check-user")
def check_invite_user(
    email: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
):
    """
    Check if a user exists by email to prefetch their name for invite acceptance.
    """
    normalized = email.strip().lower()
    user = db.query(models.User).filter(
        func.lower(func.trim(models.User.email)) == normalized
    ).first()
    if user:
        return {
            "exists": True,
            "first_name": user.first_name or "",
            "last_name": user.last_name or "",
        }
    return {
        "exists": False,
        "first_name": "",
        "last_name": "",
    }

@router.post("/organization/invites", response_model=schemas.OrganizationInviteResponse)
def create_org_invite(
    payload: schemas.OrganizationInviteCreate,
    current_user: Annotated[models.User, Depends(auth.get_current_user)],
    db: Session = Depends(get_db),
):
    organization_name = _require_org_admin(current_user)
    _ensure_default_rbac_roles(db, organization_name)
    role = db.query(models.OrganizationRole).filter(
        models.OrganizationRole.id == payload.role_id,
        func.lower(models.OrganizationRole.organization_name) == organization_name.lower(),
    ).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found for this organization.")

    target_email = _normalized_text(str(payload.email or "")).lower()
    if target_email:
        existing_u = db.query(models.User).filter(func.lower(func.trim(models.User.email)) == target_email).first()
        if existing_u:
            existing_m = db.query(models.UserOrganizationRole).filter(
                models.UserOrganizationRole.user_id == existing_u.id,
                func.lower(func.trim(models.UserOrganizationRole.organization_name)) == organization_name.lower()
            ).first()
            if existing_m or (existing_u.organization_name and existing_u.organization_name.lower() == organization_name.lower()):
                raise HTTPException(status_code=400, detail="This user is already a member of your organization.")

    expires_days = payload.expires_in_days if isinstance(payload.expires_in_days, int) else 7
    expires_days = max(1, min(30, expires_days))
    expires_at = datetime.utcnow() + timedelta(days=expires_days)

    token = secrets.token_urlsafe(32)
    token_hash = _hash_invite_token(token)
    invite = models.OrganizationInvite(
        organization_name=organization_name,
        email=target_email or None,
        role_id=role.id,
        token_hash=token_hash,
        expires_at=expires_at,
        created_by_user_id=current_user.id,
    )
    db.add(invite)
    db.commit()
    db.refresh(invite)

    invite_url = f"{settings.frontend_url.rstrip('/')}/invite?token={token}"

    if invite.email:
        try:
            email_service.send_organization_invite_email(
                recipient_email=invite.email,
                organization_name=organization_name,
                role_name=role.name,
                invite_url=invite_url,
            )
        except Exception:
            logger.exception("Failed to deliver organization invite email to %s", invite.email)

    # Also notify the admin who created the link so they can forward it
    try:
        email_service.send_invite_notification_to_admin(
            admin_email=current_user.email,
            organization_name=organization_name,
            invitee_email=invite.email,
            role_name=role.name,
            invite_url=invite_url,
        )
    except Exception:
        logger.exception("Failed to deliver admin notification for invite creation to %s", current_user.email)

    return schemas.OrganizationInviteResponse(
        id=invite.id,
        organization_name=invite.organization_name,
        email=invite.email,
        role_id=role.id,
        role_name=role.name,
        invite_url=invite_url,
        expires_at=invite.expires_at,
        accepted_at=invite.accepted_at,
        created_at=invite.created_at,
    )

@router.post("/organization/invites/accept", response_model=schemas.OrganizationInviteAcceptResponse)
def accept_org_invite(
    payload: schemas.OrganizationInviteAcceptRequest,
    db: Session = Depends(get_db),
):
    token_hash = _hash_invite_token(payload.token)
    if not token_hash:
        raise HTTPException(status_code=400, detail="Invalid invite token.")

    invite = db.query(models.OrganizationInvite).filter(models.OrganizationInvite.token_hash == token_hash).first()
    if not invite:
        raise HTTPException(status_code=404, detail="Invite not found.")
    if invite.accepted_at is not None:
        raise HTTPException(status_code=400, detail="Invite link already used.")
    if invite.expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Invite link expired.")

    requested_email = payload.email.strip().lower()
    if invite.email and invite.email.strip().lower() != requested_email:
        raise HTTPException(status_code=400, detail="This invite link is restricted to a different email address.")

    existing_user = db.query(models.User).filter(func.lower(func.trim(models.User.email)) == requested_email).first()
    
    role = db.query(models.OrganizationRole).filter(models.OrganizationRole.id == invite.role_id).first()
    if not role:
        raise HTTPException(status_code=400, detail="Invite role is no longer available.")

    is_admin_role = bool(role and role.name and "admin" in role.name.strip().lower())

    if existing_user:
        # Check if user already has a mapping in this organization
        existing_mapping = db.query(models.UserOrganizationRole).filter(
            models.UserOrganizationRole.user_id == existing_user.id,
            func.lower(func.trim(models.UserOrganizationRole.organization_name)) == invite.organization_name.lower()
        ).first()
        if existing_mapping:
            raise HTTPException(status_code=400, detail="You are already a member of this organization.")

        # Verify password for security
        if not auth.verify_password(payload.password, existing_user.hashed_password):
            raise HTTPException(status_code=400, detail="Invalid password for existing user account.")

        user = existing_user
        user.last_login = datetime.utcnow()
        # CRITICAL: Switch the active organization in DB to the newly joined organization!
        user.organization_name = invite.organization_name
        user.is_org_admin = is_admin_role
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        raw_password = payload.password
        hashed_password = auth.get_password_hash(raw_password)
        user = models.User(
            email=requested_email,
            hashed_password=hashed_password,
            first_name=_normalized_text(payload.first_name) or None,
            last_name=_normalized_text(payload.last_name) or None,
            organization_name=invite.organization_name,
            is_org_admin=is_admin_role,
            last_login=datetime.utcnow(),
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    mapping = models.UserOrganizationRole(
        user_id=user.id,
        organization_name=invite.organization_name,
        role_id=role.id,
    )
    db.add(mapping)
    invite.accepted_at = datetime.utcnow()
    invite.accepted_by_user_id = user.id
    db.add(invite)
    db.commit()

    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    access_token = auth.create_access_token(
        data={"sub": user.email, "org": invite.organization_name},
        expires_delta=access_token_expires
    )
    role_name, allowed_paths = _get_user_allowed_paths(db, user)
    return schemas.OrganizationInviteAcceptResponse(
        access_token=access_token,
        organization_name=invite.organization_name,
        role_name=role_name or role.name,
        allowed_paths=allowed_paths,
    )

def _bootstrap_org_agent_mappings_if_missing(
    db: Session,
    organization_name: str,
    project_token: Optional[str],
) -> None:
    """
    Backward-compatibility: if an org has no mappings yet for this project_token context,
    map all existing agents in that context to this org.
    """
    organization_name = _normalized_text(organization_name)
    project_token = _normalize_project_token(project_token)
    if not organization_name:
        return

    mapping_q = db.query(models.OrganizationAgentMapping).filter(
        func.lower(models.OrganizationAgentMapping.organization_name) == organization_name.lower()
    )
    if project_token:
        mapping_q = mapping_q.filter(models.OrganizationAgentMapping.project_token == project_token)
    else:
        mapping_q = mapping_q.filter(models.OrganizationAgentMapping.project_token.is_(None))
    if mapping_q.first():
        return

    agent_q = db.query(models.Agent)
    if project_token:
        agent_q = agent_q.filter(models.Agent.project_token == project_token)
    else:
        agent_q = agent_q.filter(models.Agent.project_token.is_(None))
    existing = agent_q.all()
    if not existing:
        return

    for agent in existing:
        inferred_kind = _normalize_agent_kind(None, getattr(agent, "project_token", project_token), is_default=False)
        db.add(
            models.OrganizationAgentMapping(
                organization_name=organization_name,
                agent_id=agent.id,
                project_token=project_token,
                agent_kind=inferred_kind,
                is_default=False,
            )
        )
    db.commit()

def _ensure_org_agent_mapping(
    db: Session,
    organization_name: str,
    agent_id: str,
    project_token: Optional[str],
    *,
    agent_kind: Optional[str] = None,
    agent_sub_type: Optional[str] = None,
    is_default: bool,
) -> None:
    organization_name = _normalized_text(organization_name)
    if not organization_name:
        return
    project_token = _normalize_project_token(project_token)
    normalized_kind = _normalize_agent_kind(agent_kind, project_token, is_default=is_default)
    normalized_sub_type = (_normalized_text(agent_sub_type) or '').lower() or None
    existing = db.query(models.OrganizationAgentMapping).filter(
        func.lower(models.OrganizationAgentMapping.organization_name) == organization_name.lower(),
        models.OrganizationAgentMapping.agent_id == agent_id,
    ).first()
    if existing:
        # Keep latest project_token/default flag consistent
        existing.project_token = project_token
        existing.agent_kind = normalized_kind
        existing.is_default = bool(is_default)
        if normalized_sub_type:  # only update sub_type if explicitly provided
            existing.agent_sub_type = normalized_sub_type
        db.add(existing)
        db.commit()
        return
    db.add(
        models.OrganizationAgentMapping(
            organization_name=organization_name,
            agent_id=agent_id,
            project_token=project_token,
            agent_kind=normalized_kind,
            agent_sub_type=normalized_sub_type,
            is_default=bool(is_default),
        )
    )
    db.commit()

def _count_org_agent_usage(
    db: Session,
    organization_name: str,
) -> dict[str, int]:
    """Returns a dict with shared_used, dedicated_used, and subtype breakdowns."""
    org = _normalized_text(organization_name)
    if not org:
        return {
            "shared": 0, "dedicated": 0,
            "shared_dev": 0, "shared_test": 0,
            "dedicated_dev": 0, "dedicated_test": 0
        }
    rows = db.query(models.OrganizationAgentMapping).filter(
        func.lower(models.OrganizationAgentMapping.organization_name) == org.lower(),
        models.OrganizationAgentMapping.is_default.is_(False),
        models.OrganizationAgentMapping.project_token.isnot(None),
    ).all()
    stats = {
        "shared": 0, "dedicated": 0,
        "shared_dev": 0, "shared_test": 0,
        "dedicated_dev": 0, "dedicated_test": 0
    }
    for row in rows:
        kind = _normalize_agent_kind(row.agent_kind, row.project_token, is_default=bool(row.is_default))
        sub_type = (_normalized_text(row.agent_sub_type) or "dev").lower()
        
        if kind == "shared":
            stats["shared"] += 1
            if sub_type == "test": stats["shared_test"] += 1
            else: stats["shared_dev"] += 1
        elif kind == "dedicated":
            stats["dedicated"] += 1
            if sub_type == "test": stats["dedicated_test"] += 1
            else: stats["dedicated_dev"] += 1
    return stats


def _count_org_agent_usage_for_project(
    db: Session,
    organization_name: str,
    project_token: Optional[str],
) -> dict[str, int]:
    """Return usage for a single project, excluding built-in defaults."""
    org = _normalized_text(organization_name)
    normalized_project_token = _normalize_project_token(project_token)
    if not org or not normalized_project_token:
        return {
            "shared": 0, "dedicated": 0,
            "shared_dev": 0, "shared_test": 0,
            "dedicated_dev": 0, "dedicated_test": 0
        }

    rows = db.query(models.OrganizationAgentMapping).filter(
        func.lower(models.OrganizationAgentMapping.organization_name) == org.lower(),
        models.OrganizationAgentMapping.is_default.is_(False),
        models.OrganizationAgentMapping.project_token == normalized_project_token,
    ).all()

    stats = {
        "shared": 0, "dedicated": 0,
        "shared_dev": 0, "shared_test": 0,
        "dedicated_dev": 0, "dedicated_test": 0
    }
    for row in rows:
        kind = _normalize_agent_kind(row.agent_kind, row.project_token, is_default=bool(row.is_default))
        sub_type = (_normalized_text(row.agent_sub_type) or "dev").lower()
        if kind == "shared":
            stats["shared"] += 1
            if sub_type == "test": stats["shared_test"] += 1
            else: stats["shared_dev"] += 1
        elif kind == "dedicated":
            stats["dedicated"] += 1
            if sub_type == "test": stats["dedicated_test"] += 1
            else: stats["dedicated_dev"] += 1
    return stats


def _get_or_init_org_agent_quota(
    db: Session,
    organization_name: str,
) -> models.OrganizationAgentQuota:
    org = _normalized_text(organization_name)
    quota = db.query(models.OrganizationAgentQuota).filter(
        func.lower(models.OrganizationAgentQuota.organization_name) == org.lower()
    ).first()
    if quota:
        if not quota.max_agent_capacity or quota.max_agent_capacity <= 0:
            quota.max_agent_capacity = 10
            quota.shared_quota = max(10, int(quota.shared_quota or 0))
            quota.dedicated_quota = max(10, int(quota.dedicated_quota or 0))
            db.commit()
            db.refresh(quota)
        return quota

    # Initialize quotas to standard default 10
    usage = _count_org_agent_usage(db, org)
    shared_used = usage["shared"]
    dedicated_used = usage["dedicated"]
    quota = models.OrganizationAgentQuota(
        organization_name=org,
        max_agent_capacity=10,
        shared_quota=max(10, int(shared_used)),
        dedicated_quota=max(10, int(dedicated_used)),
    )
    db.add(quota)
    db.commit()
    db.refresh(quota)
    return quota

@router.get("/organization/sso-settings", response_model=schemas.OrganizationSSOSettingsResponse)
def get_organization_sso_settings(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    organization_name = _require_org_admin(current_user)
    row = db.query(models.OrganizationSSOSetting).filter(
        func.lower(models.OrganizationSSOSetting.organization_name) == organization_name.lower()
    ).first()
    if not row:
        return schemas.OrganizationSSOSettingsResponse(
            organization_name=organization_name,
            sso_provider=None,
            tenant_id=None,
            client_id=None,
            client_secret=None,
            authority_url=None,
            redirect_uri=None,
            logout_url=None,
            scopes=None,
            domain_hint=None,
            sso_enabled=False,
            updated_at=None,
        )
    return row

@router.put("/organization/sso-settings", response_model=schemas.OrganizationSSOSettingsResponse)
def update_organization_sso_settings(
    payload: schemas.OrganizationSSOSettingsUpdate,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    organization_name = _require_org_admin(current_user)
    row = db.query(models.OrganizationSSOSetting).filter(
        func.lower(models.OrganizationSSOSetting.organization_name) == organization_name.lower()
    ).first()
    if not row:
        row = models.OrganizationSSOSetting(
            organization_name=organization_name,
            admin_user_id=current_user.id,
        )
        db.add(row)

    row.sso_provider = payload.sso_provider
    row.tenant_id = payload.tenant_id
    row.client_id = payload.client_id
    row.client_secret = payload.client_secret
    row.authority_url = payload.authority_url
    row.redirect_uri = payload.redirect_uri
    row.logout_url = payload.logout_url
    row.scopes = payload.scopes

    # Domain hint is no longer configured from the frontend UI; if it is not
    # explicitly provided, derive it from the org admin's email domain so that
    # all users with that domain (e.g. *@company.com) can use SSO.
    if payload.domain_hint is not None:
        row.domain_hint = payload.domain_hint
    if not _normalized_text(row.domain_hint):
        admin_email = _normalized_text(current_user.email)
        if "@" in admin_email:
            row.domain_hint = admin_email.split("@", 1)[1].lower()

    row.sso_enabled = payload.sso_enabled
    row.admin_user_id = current_user.id

    db.commit()
    db.refresh(row)
    return row



