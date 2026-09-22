"""
DSuite BRD Analyzer - Domain Router: Users & Profile Management
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

import auth
import models
import schemas
from config import settings
from database import SessionLocal, engine, get_db
import email_service
from app.routers.helpers import ORG_MANAGED_PAGES, _generate_registration_password



logger = logging.getLogger(__name__)

router = APIRouter(tags=["Users"])

# --- Extracted Block (Lines 2514-2633) ---
@router.post("/users/", response_model=schemas.User)
def create_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    normalized_email = user.email.strip().lower()
    db_user = db.query(models.User).filter(func.lower(models.User.email) == normalized_email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    organization_name = (user.organization_name or "").strip()
    if not organization_name:
        local_name = normalized_email.split("@", 1)[0].replace(".", " ").replace("_", " ").strip().title()
        organization_name = f"{local_name or 'Default'} Organization"

    existing_org_admin = db.query(models.User).filter(
        func.lower(models.User.organization_name) == organization_name.lower(),
        models.User.is_org_admin.is_(True),
    ).first()
    if existing_org_admin:
        raise HTTPException(
            status_code=400,
            detail="Organization already registered. Sign in with your admin account.",
        )

    # For now, allow registration without enforcing SMTP configuration.
    # If the client sends an explicit password, use it; otherwise fall back to a generated one.
    raw_password = (user.password or "").strip() or _generate_registration_password()
    hashed_password = auth.get_password_hash(raw_password)
    db_user = models.User(
        email=normalized_email,
        hashed_password=hashed_password,
        first_name=(user.first_name or "").strip() or None,
        last_name=(user.last_name or "").strip() or None,
        organization_name=organization_name,
        is_org_admin=True,
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)

    # Seed Organization Role and User role mapping for newly created user
    admin_role = db.query(models.OrganizationRole).filter(
        func.lower(models.OrganizationRole.organization_name) == organization_name.lower(),
        func.lower(models.OrganizationRole.name) == "admin"
    ).first()
    if not admin_role:
        admin_role = models.OrganizationRole(
            organization_name=organization_name,
            name="Admin",
            description="Administrator role with all permissions.",
            is_system=True
        )
        db.add(admin_role)
        db.commit()
        db.refresh(admin_role)
        # All pages permission for admin
        for page in ORG_MANAGED_PAGES:
            db.add(models.OrganizationRolePermission(role_id=admin_role.id, path=page.path))
        db.commit()

    db.add(models.UserOrganizationRole(
        user_id=db_user.id,
        organization_name=organization_name,
        role_id=admin_role.id
    ))
    db.commit()

    try:
        email_service.send_organization_registration_password_email(
            recipient_email=normalized_email,
            organization_name=organization_name,
            generated_password=raw_password,
            first_name=(user.first_name or "").strip() or None,
        )
    except Exception:
        # Log the failure but do not block registration when SMTP is not configured.
        logger.exception("Failed to deliver organization registration email to %s", normalized_email)

    return db_user

@router.get("/users/me", response_model=schemas.User)
async def read_users_me(
    current_user: Annotated[models.User, Depends(auth.get_current_user)],
):
    return current_user

@router.put("/users/me/progress")
async def update_user_progress(
    current_user: Annotated[models.User, Depends(auth.get_current_user)],
    page_path: str = None,
    project_token: str = None,
    db: Session = Depends(get_db)
):
    """Update user's last visited page and project for progress tracking"""
    try:
        if page_path is not None:
            current_user.last_page_path = page_path
        if project_token is not None:
            current_user.last_project_token = project_token
        
        db.commit()
        db.refresh(current_user)
        
        return {
            "success": True,
            "last_page_path": current_user.last_page_path,
            "last_project_token": current_user.last_project_token
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update progress: {str(e)}")

@router.get("/users/me/progress")
async def get_user_progress(
    current_user: Annotated[models.User, Depends(auth.get_current_user)],
):
    """Get user's last visited page and project"""
    return {
        "last_page_path": current_user.last_page_path,
        "last_project_token": current_user.last_project_token
    }


