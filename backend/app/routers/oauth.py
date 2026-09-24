"""
DSuite BRD Analyzer - Domain Router: OAuth 2.0 & Plugins Integration
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
from fastapi.security import OAuth2PasswordRequestForm
from jose import JWTError, jwt
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, or_, text
from sqlalchemy.orm import Session

from app.core import security as auth
import models
import schemas
from app.core.config import settings
from app.core.database import SessionLocal, engine, get_db
from app.routers.helpers import _normalized_text



logger = logging.getLogger(__name__)

router = APIRouter(tags=["OAuth"])

OAUTH_AUTH_CODE_TTL_SECONDS = 300
OAUTH_ACCESS_TOKEN_TTL_SECONDS = 3600

# --- Extracted Block (Lines 2028-2261) ---
def _strip_query_param(raw_url: str, param_name: str) -> str:
    parsed = urlsplit(raw_url)
    filtered = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True) if k != param_name]
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(filtered), parsed.fragment))

def _build_login_redirect_for_oauth(request: Request) -> str:
    authorize_url = _strip_query_param(str(request.url), "dsuite_token")
    return f"{settings.frontend_url.rstrip('/')}/login?{urlencode({'next': authorize_url})}"

def _resolve_user_from_access_token(token: str, db: Session) -> Optional[models.User]:
    cleaned = _normalized_text(token)
    if not cleaned:
        return None
    try:
        payload = jwt.decode(
            cleaned,
            settings.secret_key,
            algorithms=[settings.algorithm],
            options={"verify_aud": False},
        )
    except JWTError:
        return None

    email = _normalized_text(payload.get("sub")).lower()
    if not email:
        return None
    return db.query(models.User).filter(func.lower(models.User.email) == email).first()

def _resolve_oauth_client(
    db: Session,
    client_id: str,
    redirect_uri: Optional[str],
) -> tuple[models.OAuthClient, str]:
    normalized_client_id = _normalized_text(client_id)
    client = db.query(models.OAuthClient).filter(
        func.lower(models.OAuthClient.client_id) == normalized_client_id.lower()
    ).first()
    if not client or not client.is_active:
        raise HTTPException(status_code=400, detail="Invalid or inactive OAuth client.")

    expected_redirect_uri = _normalized_text(client.redirect_uri)
    incoming_redirect_uri = _normalized_text(redirect_uri) or expected_redirect_uri
    if not incoming_redirect_uri:
        raise HTTPException(status_code=400, detail="Redirect URI is required.")
    if incoming_redirect_uri != expected_redirect_uri:
        raise HTTPException(status_code=400, detail="Redirect URI mismatch for this client.")

    return client, incoming_redirect_uri

def _redirect_with_oauth_error(redirect_uri: str, error_message: str, state: Optional[str]) -> RedirectResponse:
    params: Dict[str, str] = {"error": error_message}
    if state:
        params["state"] = state
    return RedirectResponse(
        url=f"{redirect_uri}?{urlencode(params)}",
        status_code=302,
    )

def _build_oauth_authorize_url(
    request: Request,
    client_id: str,
    redirect_uri: str,
    scope: str,
    state: str,
    dsuite_token: str,
) -> str:
    base_url = str(request.url_for("oauth_authorize"))
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": scope,
        "state": state,
        "dsuite_token": dsuite_token,
    }
    return f"{base_url}?{urlencode(params)}"

def _find_plugin_connection(
    db: Session,
    organization_name: str,
    oauth_client_id: str,
) -> Optional[models.OrganizationPluginConnection]:
    org = _normalized_text(organization_name)
    cid = _normalized_text(oauth_client_id)
    if not org or not cid:
        return None
    return db.query(models.OrganizationPluginConnection).filter(
        func.lower(models.OrganizationPluginConnection.organization_name) == org.lower(),
        func.lower(models.OrganizationPluginConnection.oauth_client_id) == cid.lower(),
    ).first()

def _get_or_create_plugin_connection(
    db: Session,
    organization_name: str,
    oauth_client_id: str,
) -> models.OrganizationPluginConnection:
    org = _normalized_text(organization_name)
    cid = _normalized_text(oauth_client_id)
    if not org:
        raise HTTPException(status_code=400, detail="User organization is not configured.")
    if not cid:
        raise HTTPException(status_code=400, detail="Plugin client ID is invalid.")

    existing = _find_plugin_connection(db, org, cid)
    if existing:
        return existing

    row = models.OrganizationPluginConnection(
        organization_name=org,
        oauth_client_id=cid,
        is_connected=False,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row

def _find_org_sso_settings(
    db: Session,
    organization_name: str,
) -> Optional[models.OrganizationSSOSetting]:
    org = _normalized_text(organization_name)
    if not org:
        return None
    return db.query(models.OrganizationSSOSetting).filter(
        func.lower(models.OrganizationSSOSetting.organization_name) == org.lower()
    ).first()

def _mark_plugin_connected(
    db: Session,
    connection: models.OrganizationPluginConnection,
    message: str,
) -> None:
    connection.is_connected = True
    if connection.connected_at is None:
        connection.connected_at = datetime.utcnow()
    connection.last_message = _normalized_text(message) or "Connected."
    connection.last_error = None
    db.add(connection)
    db.commit()
    db.refresh(connection)

async def _ensure_nxdune_organization_connection(
    db: Session,
    current_user: models.User,
    connection: models.OrganizationPluginConnection,
) -> None:
    if connection.is_connected and _normalized_text(connection.remote_org_tenant):
        return

    organization_name = _normalized_text(current_user.organization_name)
    sso = _find_org_sso_settings(db, organization_name)
    if not sso:
        raise HTTPException(
            status_code=400,
            detail="Configure Organization SSO settings first before connecting Nxdune.",
        )

    tenant_id = _normalized_text(sso.tenant_id)
    client_id = _normalized_text(sso.client_id)
    client_secret = _normalized_text(sso.client_secret)
    if not tenant_id or not client_id or not client_secret:
        raise HTTPException(
            status_code=400,
            detail="Tenant ID, Client ID, and Client Secret are required in Organization SSO settings for Nxdune connect.",
        )

    payload = {
        "name": organization_name,
        "tenant_id": tenant_id,
        "client_id": client_id,
        "client_secret": client_secret,
        "remarks": "Created via DSuite plugin connect",
    }

    headers = {"Content-Type": "application/json"}
    auth_token = _normalized_text(settings.nxdune_org_create_auth_token)
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"

    try:
        async with httpx.AsyncClient(timeout=float(settings.nxdune_org_create_timeout_seconds)) as client:
            response = await client.post(
                settings.nxdune_org_create_url,
                json=payload,
                headers=headers,
            )
        response_data = {}
        if response.content:
            try:
                response_data = response.json()
            except Exception:
                response_data = {}

        if response.status_code == 409:
            # Treat "already exists" as connected for idempotent behavior.
            connection.is_connected = True
            connection.connected_at = connection.connected_at or datetime.utcnow()
            connection.remote_org_tenant = _normalized_text(response_data.get("org_tenant")) or connection.remote_org_tenant
            connection.last_message = _normalized_text(response_data.get("message")) or "Organization already exists in Nxdune."
            connection.last_error = None
            db.add(connection)
            db.commit()
            db.refresh(connection)
            return

        if response.status_code >= 400:
            error_body = _normalized_text(response.text)[:400] or f"HTTP {response.status_code}"
            connection.is_connected = False
            connection.last_error = f"Nxdune connect failed: {error_body}"
            db.add(connection)
            db.commit()
            raise HTTPException(status_code=400, detail=connection.last_error)
    except HTTPException:
        raise
    except Exception as exc:
        connection.is_connected = False
        connection.last_error = f"Nxdune connect failed: {str(exc)}"
        db.add(connection)
        db.commit()
        raise HTTPException(status_code=400, detail=connection.last_error)

    remote_tenant = _normalized_text(response_data.get("org_tenant")) or None
    message = _normalized_text(response_data.get("message")) or "Organization created successfully."

    connection.is_connected = True
    connection.connected_at = connection.connected_at or datetime.utcnow()
    connection.remote_org_tenant = remote_tenant
    connection.last_message = message
    connection.last_error = None
    db.add(connection)
    db.commit()
    db.refresh(connection)


# --- Extracted Block (Lines 2262-2513) ---
@router.get("/oauth/clients", response_model=List[schemas.OAuthClientPublic])
def list_oauth_clients(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(models.OAuthClient).filter(models.OAuthClient.is_active.is_(True))
    organization_name = _normalized_text(current_user.organization_name)
    if organization_name:
        query = query.filter(
            or_(
                models.OAuthClient.allowed_organization.is_(None),
                func.lower(models.OAuthClient.allowed_organization) == organization_name.lower(),
            )
        )
    clients = query.order_by(models.OAuthClient.name.asc()).all()
    connection_map: Dict[str, models.OrganizationPluginConnection] = {}
    if organization_name:
        rows = db.query(models.OrganizationPluginConnection).filter(
            func.lower(models.OrganizationPluginConnection.organization_name) == organization_name.lower()
        ).all()
        connection_map = {row.oauth_client_id.lower(): row for row in rows}

    response: List[schemas.OAuthClientPublic] = []
    for client in clients:
        connection = connection_map.get(client.client_id.lower())
        response.append(
            schemas.OAuthClientPublic(
                name=client.name,
                client_id=client.client_id,
                login_url=client.login_url,
                connected=bool(connection and connection.is_connected),
                connected_at=connection.connected_at if connection else None,
                remote_org_tenant=connection.remote_org_tenant if connection else None,
                connection_message=connection.last_message if connection else None,
                connection_error=connection.last_error if connection else None,
            )
        )
    return response

@router.get("/oauth/plugins/{client_id}/launch", response_model=schemas.OAuthPluginLaunchResponse)
async def get_oauth_plugin_launch_url(
    client_id: str,
    request: Request,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    client, redirect_uri = _resolve_oauth_client(db, client_id, None)
    organization_name = _normalized_text(current_user.organization_name)
    allowed_org = _normalized_text(client.allowed_organization)
    if allowed_org and organization_name.lower() != allowed_org.lower():
        raise HTTPException(
            status_code=403,
            detail="Your organization is not allowed to access this plugin.",
        )

    connection = _get_or_create_plugin_connection(db, organization_name, client.client_id)
    if client.client_id.lower() == settings.oauth_nxdune_client_id.lower():
        try:
            await _ensure_nxdune_organization_connection(db, current_user, connection)
        except HTTPException as exc:
            # Log the error but allow OAuth flow to proceed
            # Organization creation can be retried later
            logger.warning(f"Nxdune organization creation failed: {exc.detail}. Proceeding with OAuth launch.")
            connection.last_error = str(exc.detail)[:400]
            db.add(connection)
            db.commit()
    elif not connection.is_connected:
        _mark_plugin_connected(db, connection, "Connected via DSuite launch.")

    launch_token = auth.create_access_token(
        data={
            "sub": current_user.email,
            "token_use": "oauth_launch",
            "organization_name": organization_name or "",
        },
        expires_delta=timedelta(minutes=10),
    )
    state = secrets.token_urlsafe(18)
    scope = "openid profile email"
    launch_url = _build_oauth_authorize_url(
        request=request,
        client_id=client.client_id,
        redirect_uri=redirect_uri,
        scope=scope,
        state=state,
        dsuite_token=launch_token,
    )
    return schemas.OAuthPluginLaunchResponse(
        launch_url=launch_url,
        connected=connection.is_connected,
    )

@router.get("/oauth/authorize")
async def oauth_authorize(
    request: Request,
    client_id: str,
    response_type: str = "code",
    redirect_uri: Optional[str] = None,
    scope: str = "openid profile email",
    state: Optional[str] = None,
    dsuite_token: Optional[str] = None,
    db: Session = Depends(get_db),
):
    if response_type != "code":
        raise HTTPException(status_code=400, detail="Only response_type=code is supported.")

    client, resolved_redirect_uri = _resolve_oauth_client(db, client_id, redirect_uri)
    user = _resolve_user_from_access_token(dsuite_token or "", db)
    if not user:
        return RedirectResponse(url=_build_login_redirect_for_oauth(request), status_code=302)

    allowed_org = _normalized_text(client.allowed_organization)
    user_org = _normalized_text(user.organization_name)
    if allowed_org and user_org.lower() != allowed_org.lower():
        return _redirect_with_oauth_error(
            redirect_uri=resolved_redirect_uri,
            error_message="organization_not_allowed",
            state=state,
        )

    try:
        connection = _get_or_create_plugin_connection(db, user_org, client.client_id)
        if client.client_id.lower() == settings.oauth_nxdune_client_id.lower():
            await _ensure_nxdune_organization_connection(db, user, connection)
        elif not connection.is_connected:
            _mark_plugin_connected(db, connection, "Connected via DSuite login.")
    except HTTPException as exc:
        return _redirect_with_oauth_error(
            redirect_uri=resolved_redirect_uri,
            error_message=_normalized_text(str(exc.detail)) or "organization_provisioning_failed",
            state=state,
        )

    auth_code = secrets.token_urlsafe(48)
    expires_at = datetime.utcnow() + timedelta(seconds=OAUTH_AUTH_CODE_TTL_SECONDS)
    db_code = models.OAuthAuthorizationCode(
        code=auth_code,
        client_id=client.client_id,
        user_id=user.id,
        organization_name=user_org or None,
        redirect_uri=resolved_redirect_uri,
        scope=_normalized_text(scope) or "openid profile email",
        state=_normalized_text(state) or None,
        expires_at=expires_at,
    )
    db.add(db_code)
    db.commit()

    params: Dict[str, str] = {"code": auth_code}
    if state:
        params["state"] = state
    return RedirectResponse(
        url=f"{resolved_redirect_uri}?{urlencode(params)}",
        status_code=302,
    )

@router.post("/oauth/token", response_model=schemas.OAuthTokenResponse)
def oauth_token_exchange(
    grant_type: str = Form(...),
    code: str = Form(...),
    client_id: str = Form(...),
    client_secret: str = Form(...),
    redirect_uri: str = Form(...),
    db: Session = Depends(get_db),
):
    if _normalized_text(grant_type) != "authorization_code":
        raise HTTPException(status_code=400, detail="Unsupported grant type.")

    client, resolved_redirect_uri = _resolve_oauth_client(db, client_id, redirect_uri)
    if _normalized_text(client_secret) != _normalized_text(client.client_secret):
        raise HTTPException(status_code=401, detail="Invalid client credentials.")

    db_code = db.query(models.OAuthAuthorizationCode).filter(
        models.OAuthAuthorizationCode.code == _normalized_text(code),
        func.lower(models.OAuthAuthorizationCode.client_id) == client.client_id.lower(),
    ).first()
    if not db_code:
        raise HTTPException(status_code=400, detail="Invalid authorization code.")
    if db_code.used_at is not None:
        raise HTTPException(status_code=400, detail="Authorization code already used.")
    if db_code.expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Authorization code expired.")
    if _normalized_text(db_code.redirect_uri) != resolved_redirect_uri:
        raise HTTPException(status_code=400, detail="Authorization code redirect URI mismatch.")

    user = db.query(models.User).filter(models.User.id == db_code.user_id).first()
    if not user:
        raise HTTPException(status_code=400, detail="User not found for authorization code.")

    role = "admin" if user.is_org_admin else "member"
    org_name = _normalized_text(user.organization_name)
    claims = {
        "sub": user.email,
        "user_id": str(user.id),
        "email": user.email,
        "org_id": org_name.lower().replace(" ", "_"),
        "org_name": org_name,
        "organization_name": org_name,
        "role": role,
        "aud": client.client_id,
        "iss": settings.oauth_issuer,
        "token_use": "plugin_access",
    }
    access_token = auth.create_access_token(
        data=claims,
        expires_delta=timedelta(seconds=OAUTH_ACCESS_TOKEN_TTL_SECONDS),
    )

    db_code.used_at = datetime.utcnow()
    db.commit()

    return schemas.OAuthTokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=OAUTH_ACCESS_TOKEN_TTL_SECONDS,
        scope=db_code.scope or "openid profile email",
    )

@router.get("/oauth/userinfo")
def oauth_userinfo(
    authorization: Optional[str] = Header(None),
):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token.")

    token = authorization.split(" ", 1)[1].strip()
    try:
        claims = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.algorithm],
            options={"verify_aud": False},
        )
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token.")

    if _normalized_text(claims.get("token_use")) not in {"plugin_access", "oauth_launch"}:
        raise HTTPException(status_code=401, detail="Invalid token type.")

    return {
        "sub": claims.get("sub"),
        "email": claims.get("email") or claims.get("sub"),
        "user_id": claims.get("user_id"),
        "org_id": claims.get("org_id"),
        "org_name": claims.get("org_name"),
        "organization_name": claims.get("organization_name"),
        "role": claims.get("role"),
        "aud": claims.get("aud"),
        "iss": claims.get("iss"),
        "exp": claims.get("exp"),
    }


