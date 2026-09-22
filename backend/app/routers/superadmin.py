"""
DSuite BRD Analyzer - Domain Router: SuperAdmin Administration & Capacity & Billing
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
import agent_service


logger = logging.getLogger(__name__)

router = APIRouter(tags=["SuperAdmin & Billing"])

# --- Extracted Block (Lines 2805-3090) ---
def _resolve_vibecoding_db_path() -> Optional[str]:
    """Dynamically resolve vibecoding_users.db strictly from the official Vibecoding application database location."""
    env_path = os.getenv("VIBECODING_DB_PATH")
    if env_path and os.path.exists(env_path):
        return env_path

    candidates = [
        r"D:\Vibecoding\BRD_Analyzer\vibecoding\backend\vibecoding_users.db",
        "/app/vibecoding/backend/vibecoding_users.db",
        "/var/lib/vibecoding/vibecoding_users.db",
    ]

    for p in candidates:
        if os.path.exists(p):
            return p
    return None


def _resolve_vibecoding_artifacts_dirs() -> List[str]:
    """Dynamically resolve Vibecoding project_artifacts directory strictly from official Vibecoding location."""
    env_dir = os.getenv("VIBECODING_ARTIFACTS_DIR")
    dirs = []
    if env_dir and os.path.exists(env_dir):
        dirs.append(env_dir)

    candidates = [
        r"D:\Vibecoding\BRD_Analyzer\vibecoding\backend\project_artifacts",
        "/app/vibecoding/backend/project_artifacts",
    ]

    for p in candidates:
        if os.path.exists(p) and p not in dirs:
            dirs.append(p)
    return dirs


def _get_vibecoding_usage_logs(start_dt=None, end_dt=None):
    """
    Fetch Vibecoding usage logs strictly from the Vibecoding HTTP API.
    If the API is not available, returns an empty list (direct SQLite fallback removed).
    """
    import requests
    vibecoding_url = os.getenv("VIBECODING_BACKEND_URL", "http://127.0.0.1:8001")
    if not vibecoding_url:
        return []
    if not vibecoding_url.endswith("/"):
        vibecoding_url += "/"
    telemetry_url = f"{vibecoding_url}vibecoding/api/telemetry/usage-costs"
    q_params = []
    if start_dt:
        q_params.append(f"start_date={start_dt.isoformat() if hasattr(start_dt, 'isoformat') else str(start_dt)}")
    if end_dt:
        q_params.append(f"end_date={end_dt.isoformat() if hasattr(end_dt, 'isoformat') else str(end_dt)}")
    if q_params:
        telemetry_url += "?" + "&".join(q_params)

    try:
        resp = requests.get(telemetry_url, timeout=(0.5, 1.5))
        if resp.ok:
            data = resp.json()
            raw_logs = data.get("logs", [])
            logs = []
            for r in raw_logs:
                p_tokens = r.get("prompt_tokens") or 0
                c_tokens = r.get("completion_tokens") or 0
                cost = r.get("cost") or ((p_tokens + c_tokens) * 0.00007)
                logs.append({
                    "username": r.get("username"),
                    "project_token": r.get("project_id") or "vibecoding_workspace",
                    "prompt_tokens": p_tokens,
                    "completion_tokens": c_tokens,
                    "cost": round(cost, 6),
                    "model": "BournAI (VibeCoding)"
                })
            return logs
    except Exception as err:
        logging.getLogger(__name__).warning(f"Could not fetch Vibecoding usage logs via HTTP ({telemetry_url}): {err}")

    return []


def _fetch_vibecoding_data_directly(start_dt=None, end_dt=None):
    import sqlite3
    target_db = _resolve_vibecoding_db_path()
    if not target_db:
        return {"logs": [], "users": [], "project_names": {}}

    logs = []
    users = []
    project_names = {}

    try:
        conn = sqlite3.connect(target_db)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT id, username, email, full_name FROM users")
            for u in cursor.fetchall():
                users.append(dict(u))
        except Exception:
            pass

        conn.close()
    except Exception as e:
        logging.getLogger(__name__).warning(f"Error reading Vibecoding users table: {e}")

    # Build user lookup maps
    users_by_id = {}
    users_by_name = {}
    for u in users:
        u_id = u.get("id")
        if u_id: users_by_id[u_id] = u
        uname = u.get("username")
        if uname: users_by_name[uname.lower()] = u
        uemail = u.get("email")
        if uemail: users_by_name[uemail.lower()] = u

    default_user = list(users_by_id.values())[0] if users_by_id else None

    # Resolve project names and project owner_ids from project_artifacts
    artifacts_dirs = _resolve_vibecoding_artifacts_dirs()
    project_owners = {}
    for art_dir in artifacts_dirs:
        if os.path.exists(art_dir):
            try:
                for p_id in os.listdir(art_dir):
                    meta_p = os.path.join(art_dir, p_id, "metadata.json")
                    if os.path.exists(meta_p):
                        try:
                            with open(meta_p, "r", encoding="utf-8") as f:
                                m_data = json.load(f)
                            if p_id not in project_names:
                                name = m_data.get("name")
                                if not name and m_data.get("versions"):
                                    name = m_data["versions"][0].get("prompt")
                                if name:
                                    project_names[p_id] = name[:50]
                            oid = m_data.get("owner_id")
                            if oid and oid in users_by_id and p_id not in project_owners:
                                project_owners[p_id] = users_by_id[oid]
                        except Exception:
                            pass
            except Exception:
                pass

    seen_log_ids = set()

    try:
        conn = sqlite3.connect(target_db)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT id, username, project_id, prompt_tokens, completion_tokens, total_tokens, status, timestamp FROM user_logs")
            rows = cursor.fetchall()
            for r in rows:
                seen_log_ids.add(r["id"])
                ts_str = r["timestamp"]
                dt = None
                if ts_str:
                    try:
                        dt = datetime.fromisoformat(ts_str)
                        dt = dt.replace(tzinfo=None)
                    except Exception:
                        pass

                if start_dt and dt and dt < start_dt:
                    continue
                if end_dt and dt and dt > end_dt:
                    continue

                raw_uname = r["username"] or "user"
                pid = r["project_id"] or "default"

                # Dynamic resolution of real user email/username
                u_info = None
                if raw_uname and raw_uname.lower() in users_by_name and raw_uname.lower() != "user":
                    u_info = users_by_name[raw_uname.lower()]
                elif pid in project_owners:
                    u_info = project_owners[pid]
                else:
                    u_info = default_user

                resolved_username = u_info.get("username") if u_info else raw_uname
                resolved_email = u_info.get("email") if u_info else raw_uname
                resolved_fullname = u_info.get("full_name") if u_info else resolved_username

                p_tokens = r["prompt_tokens"] or 0
                c_tokens = r["completion_tokens"] or 0
                t_tokens = r["total_tokens"] or (p_tokens + c_tokens)
                cost = round(t_tokens * 0.00007, 6)

                logs.append({
                    "id": r["id"],
                    "username": resolved_username,
                    "email": resolved_email,
                    "full_name": resolved_fullname,
                    "project_id": pid,
                    "prompt_tokens": p_tokens,
                    "completion_tokens": c_tokens,
                    "total_tokens": t_tokens,
                    "cost": cost,
                    "timestamp": ts_str
                })
        except Exception as log_err:
            logging.getLogger(__name__).warning(f"Could not read user_logs: {log_err}")

        # Extract telemetry from messages table
        try:
            cursor.execute("SELECT id, project_id, role, content, timestamp FROM messages ORDER BY timestamp ASC")
            msg_rows = cursor.fetchall()
            msg_by_proj = {}
            for m in msg_rows:
                pid = m["project_id"] or "default"
                if pid not in msg_by_proj:
                    msg_by_proj[pid] = []
                msg_by_proj[pid].append(dict(m))

            for pid, m_list in msg_by_proj.items():
                u_info = project_owners.get(pid) or default_user
                resolved_username = u_info.get("username") if u_info else "user"
                resolved_email = u_info.get("email") if u_info else "user"
                resolved_fullname = u_info.get("full_name") if u_info else resolved_username

                curr_log = None
                for m in m_list:
                    if m["id"] in seen_log_ids:
                        continue
                    ts_str = m.get("timestamp")
                    dt = None
                    if ts_str:
                        try:
                            dt = datetime.fromisoformat(ts_str)
                            dt = dt.replace(tzinfo=None)
                        except Exception:
                            pass
                    if start_dt and dt and dt < start_dt:
                        continue
                    if end_dt and dt and dt > end_dt:
                        continue

                    if m["role"] == "user":
                        if curr_log:
                            logs.append(curr_log)
                        content = m.get("content") or ""
                        p_tok = max(1, len(content) // 4)
                        curr_log = {
                            "id": m["id"],
                            "username": resolved_username,
                            "email": resolved_email,
                            "full_name": resolved_fullname,
                            "project_id": pid,
                            "prompt_tokens": p_tok,
                            "completion_tokens": 0,
                            "total_tokens": p_tok,
                            "cost": round(p_tok * 0.00007, 6),
                            "timestamp": ts_str
                        }
                    elif m["role"] == "assistant" and curr_log:
                        content = m.get("content") or ""
                        c_tok = max(1, len(content) // 4)
                        curr_log["completion_tokens"] += c_tok
                        curr_log["total_tokens"] += c_tok
                        curr_log["cost"] = round(curr_log["total_tokens"] * 0.00007, 6)

                if curr_log:
                    logs.append(curr_log)
        except Exception as msg_err:
            logging.getLogger(__name__).warning(f"Could not extract messages telemetry: {msg_err}")

        conn.close()
    except Exception as e:
        logging.getLogger(__name__).warning(f"Error reading Vibecoding direct data: {e}")

    return {
        "logs": logs,
        "users": users,
        "project_names": project_names
    }


def _require_super_admin(current_user: models.User) -> None:
    if not bool(getattr(current_user, "is_super_admin", False)):
        raise HTTPException(status_code=403, detail="Super Admin access required")


# --- Extracted Block (Lines 3091-4032) ---
@router.get("/api/superadmin/dashboard-stats")
def get_superadmin_dashboard_stats(
    current_user: Annotated[models.User, Depends(auth.get_current_user)],
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db),
):
    _require_super_admin(current_user)
    import datetime

    start_dt, end_dt = None, None
    if start_date:
        try: start_dt = datetime.datetime.fromisoformat(start_date)
        except Exception: pass
    if end_date:
        try: end_dt = datetime.datetime.fromisoformat(end_date) + datetime.timedelta(days=1) - datetime.timedelta(microseconds=1)
        except Exception: pass

    # Total registered organization names
    org_names = [
        row[0] for row in db.query(models.User.organization_name).filter(
            models.User.organization_name.isnot(None)
        ).distinct().all() if row[0] and row[0].strip()
    ]
    total_organizations = len(org_names)

    # Agents count
    total_onboarded_agents = db.query(models.OrganizationAgentMapping).filter(
        models.OrganizationAgentMapping.is_default == False
    ).count()

    shared_agents = db.query(models.OrganizationAgentMapping).filter(
        models.OrganizationAgentMapping.is_default == False,
        func.lower(models.OrganizationAgentMapping.agent_kind) == "shared"
    ).count()

    dedicated_agents = db.query(models.OrganizationAgentMapping).filter(
        models.OrganizationAgentMapping.is_default == False,
        func.lower(models.OrganizationAgentMapping.agent_kind) == "dedicated"
    ).count()

    borrowed_dedicated_agents = db.query(models.OrganizationAgentMapping).filter(
        models.OrganizationAgentMapping.is_borrowed == True
    ).count()

    # Pending capacity requests
    pending_capacity_requests = db.query(models.CapacityIncreaseRequest).filter(
        models.CapacityIncreaseRequest.status == "PENDING"
    ).count()

    # Total AI tokens and platform billing
    ai_query = db.query(models.AIUsageLog)
    if start_dt:
        ai_query = ai_query.filter(models.AIUsageLog.created_at >= start_dt)
    if end_dt:
        ai_query = ai_query.filter(models.AIUsageLog.created_at <= end_dt)
    ai_logs = ai_query.all()
    
    vibe_logs = _get_vibecoding_usage_logs(start_dt, end_dt)
    vibe_tokens = sum((vl["prompt_tokens"] or 0) + (vl["completion_tokens"] or 0) for vl in vibe_logs)
    vibe_cost = sum(vl["cost"] or 0.0 for vl in vibe_logs)

    ai_tokens_consumed = sum((l.prompt_tokens or 0) + (l.completion_tokens or 0) for l in ai_logs) + vibe_tokens
    platform_billing = round(sum(l.cost or 0.0 for l in ai_logs) + vibe_cost, 2)

    # Projects count
    proj_query = db.query(models.GovernanceResponse)
    if start_dt:
        proj_query = proj_query.filter(models.GovernanceResponse.submission_date >= start_dt)
    if end_dt:
        proj_query = proj_query.filter(models.GovernanceResponse.submission_date <= end_dt)
    total_projects = proj_query.count()
    active_projects = proj_query.filter(
        models.GovernanceResponse.is_archived == False
    ).count()

    # Users count
    active_users = db.query(models.User).filter(models.User.is_active == True).count()

    # Docker containers
    running_containers = agent_service.get_running_containers_count() if hasattr(agent_service, "get_running_containers_count") else 0

    return {
        "total_organizations": total_organizations,
        "total_onboarded_agents": total_onboarded_agents,
        "total_running_containers": running_containers,
        "dedicated_agents": dedicated_agents,
        "shared_agents": shared_agents,
        "borrowed_dedicated_agents": borrowed_dedicated_agents,
        "pending_capacity_requests": pending_capacity_requests,
        "platform_billing": platform_billing,
        "ai_tokens_consumed": ai_tokens_consumed,
        "project_telemetry": {
            "active": active_projects,
            "total": total_projects
        },
        "active_users": active_users,
        "agent_utilization": 85 if total_onboarded_agents > 0 else 0
    }

@router.get("/api/superadmin/organizations")
def get_superadmin_organizations(
    current_user: Annotated[models.User, Depends(auth.get_current_user)],
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db),
):
    _require_super_admin(current_user)
    import datetime

    start_dt, end_dt = None, None
    if start_date:
        try: start_dt = datetime.datetime.fromisoformat(start_date)
        except Exception: pass
    if end_date:
        try: end_dt = datetime.datetime.fromisoformat(end_date) + datetime.timedelta(days=1) - datetime.timedelta(microseconds=1)
        except Exception: pass

    org_names = sorted(list({
        row[0].strip() for row in db.query(models.User.organization_name).filter(
            models.User.organization_name.isnot(None)
        ).all() if row[0] and row[0].strip()
    }))

    vibe_logs = _get_vibecoding_usage_logs(start_dt, end_dt)

    result = []
    for name in org_names:
        quota = db.query(models.OrganizationAgentQuota).filter(
            func.lower(models.OrganizationAgentQuota.organization_name) == name.lower()
        ).first()

        max_cap = quota.max_agent_capacity if quota and quota.max_agent_capacity is not None else 0

        users = db.query(models.User).filter(
            func.lower(models.User.organization_name) == name.lower()
        ).all()

        user_ids = [u.id for u in users]

        # Resolve canonical tenant UUID & name for accurate attribution
        try:
            from tokenops.services.tenant_resolver_service import TenantResolverService
            resolver = TenantResolverService(db)
            org_id, org_obj = resolver.resolve(name)
            canonical_org_name = org_obj.name
        except Exception:
            org_id = None
            canonical_org_name = name

        tenant_filter = or_(
            models.AIUsageLog.organization_id == org_id,
            and_(
                models.AIUsageLog.organization_id.is_(None),
                func.lower(models.AIUsageLog.organization_name) == canonical_org_name.lower()
            )
        )
        ai_query = db.query(models.AIUsageLog).filter(tenant_filter)
        if start_dt:
            ai_query = ai_query.filter(models.AIUsageLog.created_at >= start_dt)
        if end_dt:
            ai_query = ai_query.filter(models.AIUsageLog.created_at <= end_dt)
        org_ai_logs = ai_query.all()
        
        # Convert ORM logs to dictionaries so we can merge VibeCoding logs
        logs_list = []
        for l in org_ai_logs:
            logs_list.append({
                "user_id": l.user_id,
                "project_token": l.project_token,
                "prompt_tokens": l.prompt_tokens or 0,
                "completion_tokens": l.completion_tokens or 0,
                "cost": l.cost or 0.0,
                "model": l.model or "DSuite Model"
            })
            
        org_emails = {u.email.lower() for u in users}
        for vl in vibe_logs:
            if vl["username"] and vl["username"].lower() in org_emails:
                matching_user = next((u for u in users if u.email.lower() == vl["username"].lower()), None)
                if matching_user:
                    logs_list.append({
                        "user_id": matching_user.id,
                        "project_token": vl["project_token"],
                        "prompt_tokens": vl["prompt_tokens"],
                        "completion_tokens": vl["completion_tokens"],
                        "cost": vl["cost"],
                        "model": vl["model"]
                    })
                    
        total_tokens = sum(l["prompt_tokens"] + l["completion_tokens"] for l in logs_list)
        token_cost = sum(l["cost"] for l in logs_list)

        # Build user breakdown and project breakdown
        org_govs = db.query(models.GovernanceResponse).filter(
            func.lower(models.GovernanceResponse.organization_name) == name.lower()
        ).all()
        
        all_org_tags = sorted(list({t.name for gr in org_govs for t in gr.tags}))
        project_tags = {gr.project_token: [t.name for t in gr.tags] for gr in org_govs}
        project_names = {gr.project_token: gr.project_name for gr in org_govs}

        # Also load any ShareProject created by this organization's members
        org_shares = db.query(models.ShareProject).filter(
            models.ShareProject.owner_id.in_(user_ids)
        ).all() if user_ids else []
        for sp in org_shares:
            if sp.project_token and sp.project_token not in project_names:
                project_names[sp.project_token] = sp.project_name or f"Share: {sp.project_token[:8]}"

        def _normalize_project_token(tok):
            if not tok:
                return "direct_api"
            s = str(tok).strip().lower()
            if s in ("direct_api", name.lower(), canonical_org_name.lower()):
                return "direct_api"
            if org_id and s == str(org_id).lower():
                return "direct_api"
            return tok

        project_tokens = list({_normalize_project_token(l["project_token"]) for l in logs_list})
        for p_tok in project_tokens:
            if p_tok == "direct_api":
                project_names[p_tok] = "Direct API / Custom Workspace"
            elif p_tok not in project_names:
                project_names[p_tok] = f"Project ({p_tok})"

        org_projects = {}
        # Pre-populate with all known projects from DB to list them even if 0 cost
        for gr in org_govs:
            p_tok = gr.project_token
            org_projects[p_tok] = {
                "project_token": p_tok,
                "project_name": gr.project_name or p_tok,
                "total_tokens": 0,
                "total_cost": 0.0,
                "tags": project_tags.get(p_tok, [])
            }

        for sp in org_shares:
            p_tok = sp.project_token
            if p_tok and p_tok not in org_projects:
                org_projects[p_tok] = {
                    "project_token": p_tok,
                    "project_name": sp.project_name or f"Share: {p_tok[:8]}",
                    "total_tokens": 0,
                    "total_cost": 0.0,
                    "tags": []
                }

        for log in logs_list:
            p_tok = _normalize_project_token(log["project_token"])
            p_name = project_names.get(p_tok, "Direct API / Custom Workspace" if p_tok == "direct_api" else f"Project ({p_tok})")
            if p_tok not in org_projects:
                org_projects[p_tok] = {
                    "project_token": p_tok,
                    "project_name": p_name,
                    "total_tokens": 0,
                    "total_cost": 0.0,
                    "tags": project_tags.get(p_tok, [])
                }
            org_projects[p_tok]["total_tokens"] += log["prompt_tokens"] + log["completion_tokens"]
            org_projects[p_tok]["total_cost"] += log["cost"]

        for p_tok in org_projects:
            org_projects[p_tok]["total_cost"] = round(org_projects[p_tok]["total_cost"], 4)

        user_breakdown = []
        for u in users:
            u_logs = [l for l in logs_list if l["user_id"] == u.id]
            u_tokens = sum(l["prompt_tokens"] + l["completion_tokens"] for l in u_logs)
            u_cost = round(sum(l["cost"] for l in u_logs), 4)

            u_projects = {}
            for log in u_logs:
                p_tok = _normalize_project_token(log["project_token"])
                p_name = project_names.get(p_tok, "Direct API / Custom Workspace" if p_tok == "direct_api" else f"Project ({p_tok})")
                if p_tok not in u_projects:
                    u_projects[p_tok] = {
                        "project_token": p_tok,
                        "project_name": p_name,
                        "total_tokens": 0,
                        "total_cost": 0.0,
                        "tags": project_tags.get(p_tok, [])
                    }
                u_projects[p_tok]["total_tokens"] += log["prompt_tokens"] + log["completion_tokens"]
                u_projects[p_tok]["total_cost"] += log["cost"]

            for p_tok in u_projects:
                u_projects[p_tok]["total_cost"] = round(u_projects[p_tok]["total_cost"], 4)

            user_breakdown.append({
                "id": u.id,
                "email": u.email,
                "first_name": u.first_name,
                "last_name": u.last_name,
                "is_org_admin": u.is_org_admin,
                "is_super_admin": u.is_super_admin,
                "ai_tokens": u_tokens,
                "total_cost": u_cost,
                "last_login": u.last_login.isoformat() if u.last_login else None,
                "projects": sorted(list(u_projects.values()), key=lambda x: x["total_cost"], reverse=True)
            })

        onboarded = db.query(models.OrganizationAgentMapping).filter(
            func.lower(models.OrganizationAgentMapping.organization_name) == name.lower(),
            models.OrganizationAgentMapping.is_default == False
        ).count()

        result.append({
            "organization_name": name,
            "max_agent_capacity": max_cap,
            "total_onboarded_agents": onboarded,
            "available_capacity": max(0, max_cap - onboarded),
            "user_count": len(users),
            "total_tokens_consumed": total_tokens,
            "total_cost": round(token_cost, 4),
            "projects": sorted(list(org_projects.values()), key=lambda x: x["total_cost"], reverse=True),
            "users": user_breakdown,
            "organization_tags": all_org_tags
        })

    return result


@router.get("/api/superadmin/vibecoding-costs")
def get_superadmin_vibecoding_costs(
    current_user: Annotated[models.User, Depends(auth.get_current_user)],
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db),
):
    _require_super_admin(current_user)
    import datetime
    import requests

    start_dt, end_dt = None, None
    if start_date:
        try: start_dt = datetime.datetime.fromisoformat(start_date)
        except Exception: pass
    if end_date:
        try: end_dt = datetime.datetime.fromisoformat(end_date) + datetime.timedelta(days=1) - datetime.timedelta(microseconds=1)
        except Exception: pass

    # 1. Fetch raw data from Vibecoding Service HTTP endpoint if available, else SQLite DB fallback
    vibe_data = None
    vibecoding_url = os.getenv("VIBECODING_BACKEND_URL", "http://127.0.0.1:8001")
    if vibecoding_url:
        if not vibecoding_url.endswith("/"):
            vibecoding_url += "/"
        telemetry_url = f"{vibecoding_url}vibecoding/api/telemetry/usage-costs"
        q_params = []
        if start_date: q_params.append(f"start_date={start_date}")
        if end_date: q_params.append(f"end_date={end_date}")
        if q_params:
            telemetry_url += "?" + "&".join(q_params)

        try:
            resp = requests.get(telemetry_url, timeout=(0.5, 1.5))
            if resp.ok:
                vibe_data = resp.json()
        except Exception as err:
            logging.getLogger(__name__).warning(f"Could not fetch Vibecoding telemetry via HTTP ({telemetry_url}): {err}")

    # If the API endpoint is not available, return no data (direct SQLite fallback removed)
    if not vibe_data or not isinstance(vibe_data, dict):
        return {
            "summary": {
                "total_organizations": 0,
                "total_projects": 0,
                "total_users": 0,
                "total_prompts": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "total_cost": 0.0
            },
            "organization_breakdown": [],
            "project_breakdown": [],
            "user_breakdown": [],
            "status": "not_available",
            "message": "Vibecoding telemetry API is not available"
        }

    raw_logs = vibe_data.get("logs", [])
    raw_users = vibe_data.get("users", [])
    project_names = vibe_data.get("project_names", {})

    # Map Dsuite users to organization names and user info
    dsuite_users = db.query(models.User).all()
    user_org_map = {}
    user_info_map = {}
    user_info_by_prefix = {}

    for u in dsuite_users:
        if u.email:
            email_key = u.email.lower().strip()
            org_n = u.organization_name or "Default Organization"
            f_name = f"{u.first_name or ''} {u.last_name or ''}".strip() or u.email
            u_data = {
                "id": u.id,
                "email": u.email,
                "full_name": f_name,
                "organization_name": org_n
            }
            user_org_map[email_key] = org_n
            user_info_map[email_key] = u_data
            prefix = email_key.split("@")[0]
            if prefix and prefix not in user_info_by_prefix:
                user_info_by_prefix[prefix] = u_data

    org_map = {}
    proj_map = {}
    user_summary_map = {}

    total_prompts = len(raw_logs)
    total_p_tokens = 0
    total_c_tokens = 0
    total_tokens = 0
    total_cost = 0.0

    for log in raw_logs:
        raw_uname = log.get("username") or "user"
        log_email = log.get("email") or raw_uname
        log_fname = log.get("full_name") or raw_uname
        p_id = log.get("project_id") or "default"
        p_tok = log.get("prompt_tokens") or 0
        c_tok = log.get("completion_tokens") or 0
        t_tok = log.get("total_tokens") or (p_tok + c_tok)
        cost = log.get("cost") or round(t_tok * 0.00007, 6)

        total_p_tokens += p_tok
        total_c_tokens += c_tok
        total_tokens += t_tok
        total_cost += cost

        # Match log user against Dsuite users by email or email prefix
        e_key = log_email.lower().strip() if log_email else ""
        d_user = user_info_map.get(e_key)
        if not d_user and e_key:
            prefix = e_key.split("@")[0]
            d_user = user_info_by_prefix.get(prefix)

        if d_user:
            email = d_user["email"]
            full_name = d_user["full_name"]
            org_name = d_user["organization_name"]
            username = raw_uname if raw_uname != "user" else d_user["email"].split("@")[0]
        else:
            email = log_email
            full_name = log_fname
            org_name = "Bourntec"
            username = raw_uname

        p_name = project_names.get(p_id) or f"Project {p_id[:8]}"

        # User aggregation (keyed by real email)
        u_key = email.lower().strip()
        if u_key not in user_summary_map:
            user_summary_map[u_key] = {
                "username": username,
                "email": email,
                "full_name": full_name,
                "organization_name": org_name,
                "projects": set(),
                "log_count": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "total_cost": 0.0
            }
        user_summary_map[u_key]["projects"].add(p_id)
        user_summary_map[u_key]["log_count"] += 1
        user_summary_map[u_key]["prompt_tokens"] += p_tok
        user_summary_map[u_key]["completion_tokens"] += c_tok
        user_summary_map[u_key]["total_tokens"] += t_tok
        user_summary_map[u_key]["total_cost"] += cost

        # Project aggregation
        if p_id not in proj_map:
            proj_map[p_id] = {
                "project_id": p_id,
                "project_name": p_name,
                "organization_name": org_name,
                "username": username,
                "email": email,
                "log_count": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "total_cost": 0.0
            }
        proj_map[p_id]["log_count"] += 1
        proj_map[p_id]["prompt_tokens"] += p_tok
        proj_map[p_id]["completion_tokens"] += c_tok
        proj_map[p_id]["total_tokens"] += t_tok
        proj_map[p_id]["total_cost"] += cost

        # Organization aggregation
        if org_name not in org_map:
            org_map[org_name] = {
                "organization_name": org_name,
                "users": set(),
                "projects": set(),
                "log_count": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "total_cost": 0.0
            }
        org_map[org_name]["users"].add(email)
        org_map[org_name]["projects"].add(p_id)
        org_map[org_name]["log_count"] += 1
        org_map[org_name]["prompt_tokens"] += p_tok
        org_map[org_name]["completion_tokens"] += c_tok
        org_map[org_name]["total_tokens"] += t_tok
        org_map[org_name]["total_cost"] += cost

    # Format arrays
    org_breakdown = []
    for org_n, data in org_map.items():
        org_breakdown.append({
            "organization_name": org_n,
            "user_count": len(data["users"]),
            "project_count": len(data["projects"]),
            "log_count": data["log_count"],
            "prompt_tokens": data["prompt_tokens"],
            "completion_tokens": data["completion_tokens"],
            "total_tokens": data["total_tokens"],
            "total_cost": round(data["total_cost"], 4),
            "users": list(data["users"]),
            "projects": list(data["projects"])
        })
    org_breakdown.sort(key=lambda x: x["total_cost"], reverse=True)

    proj_breakdown = []
    for p_id, data in proj_map.items():
        proj_breakdown.append({
            "project_id": p_id,
            "project_name": data["project_name"],
            "organization_name": data["organization_name"],
            "username": data["username"],
            "email": data["email"],
            "log_count": data["log_count"],
            "prompt_tokens": data["prompt_tokens"],
            "completion_tokens": data["completion_tokens"],
            "total_tokens": data["total_tokens"],
            "total_cost": round(data["total_cost"], 4)
        })
    proj_breakdown.sort(key=lambda x: x["total_cost"], reverse=True)

    user_breakdown = []
    for u_n, data in user_summary_map.items():
        user_breakdown.append({
            "username": data["username"],
            "email": data["email"],
            "full_name": data["full_name"],
            "organization_name": data["organization_name"],
            "project_count": len(data["projects"]),
            "log_count": data["log_count"],
            "prompt_tokens": data["prompt_tokens"],
            "completion_tokens": data["completion_tokens"],
            "total_tokens": data["total_tokens"],
            "total_cost": round(data["total_cost"], 4),
            "projects": list(data["projects"])
        })
    user_breakdown.sort(key=lambda x: x["total_cost"], reverse=True)

    return {
        "summary": {
            "total_organizations": len(org_map),
            "total_projects": len(proj_map),
            "total_users": len(user_summary_map),
            "total_prompts": total_prompts,
            "prompt_tokens": total_p_tokens,
            "completion_tokens": total_c_tokens,
            "total_tokens": total_tokens,
            "total_cost": round(total_cost, 4)
        },
        "organization_breakdown": org_breakdown,
        "project_breakdown": proj_breakdown,
        "user_breakdown": user_breakdown
    }


@router.get("/api/superadmin/master-report/export")
def export_superadmin_master_report(
    current_user: Annotated[models.User, Depends(auth.get_current_user)],
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Generate and stream a multi-sheet Excel master report (.xlsx) for Dsuite & Vibecoding telemetry."""
    _require_super_admin(current_user)
    import io, openpyxl, datetime
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    # 1. Fetch Dsuite & Vibecoding data
    d_stats = get_superadmin_dashboard_stats(current_user=current_user, start_date=start_date, end_date=end_date, db=db)
    d_orgs = get_superadmin_organizations(current_user=current_user, start_date=start_date, end_date=end_date, db=db)
    vibe_data = get_superadmin_vibecoding_costs(current_user=current_user, start_date=start_date, end_date=end_date, db=db)

    wb = openpyxl.Workbook()

    # Styling setup
    purple_fill = PatternFill(start_color="4C1D95", end_color="4C1D95", fill_type="solid")
    cyan_fill = PatternFill(start_color="0891B2", end_color="0891B2", fill_type="solid")
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    title_font = Font(name="Calibri", size=14, bold=True, color="1E1B4B")
    sub_font = Font(name="Calibri", size=10, italic=True, color="6B7280")

    def style_headers(ws, row_idx, fill):
        for cell in ws[row_idx]:
            cell.fill = fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    def auto_fit_columns(ws):
        ws.views.sheetView[0].showGridLines = True
        for col in ws.columns:
            max_len = 0
            col_letter = get_column_letter(col[0].column)
            for cell in col:
                val_str = str(cell.value if cell.value is not None else "")
                if isinstance(cell.value, float):
                    val_str = f"{cell.value:,.4f}"
                elif isinstance(cell.value, int):
                    val_str = f"{cell.value:,}"
                max_len = max(max_len, len(val_str))
            ws.column_dimensions[col_letter].width = max(max_len + 5, 14)

    # -------------------------------------------------------------
    # SHEET 1: Executive Summary
    # -------------------------------------------------------------
    ws1 = wb.active
    ws1.title = "Executive Summary"
    ws1.append(["DSUITE & VIBECODING MASTER TELEMETRY REPORT"])
    ws1.cell(row=1, column=1).font = title_font
    ws1.append(["Export Date:", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
    ws1.cell(row=2, column=1).font = sub_font
    ws1.append([])

    ws1.append(["Platform / System", "Metric Description", "Recorded Value"])
    style_headers(ws1, 4, purple_fill)

    v_sum = vibe_data.get("summary", {})
    summary_rows = [
        ["Dsuite Governance", "Total Organizations Registered", len(d_orgs)],
        ["Dsuite Governance", "Total Onboarded Agents", d_stats.get("total_onboarded_agents", 0)],
        ["Dsuite Governance", "Docker Containers Active", d_stats.get("active_containers", 0)],
        ["Dsuite Governance", "Total AI Tokens Consumed", d_stats.get("total_tokens_consumed", 0)],
        ["Dsuite Governance", "Total Platform Usage Cost ($)", d_stats.get("total_usage_cost", 0.0)],
        ["Vibecoding System", "Active Organizations", v_sum.get("total_organizations", 0)],
        ["Vibecoding System", "Active Projects", v_sum.get("total_projects", 0)],
        ["Vibecoding System", "Active Users", v_sum.get("total_users", 0)],
        ["Vibecoding System", "Prompts Logged", v_sum.get("total_prompts", 0)],
        ["Vibecoding System", "Prompt Tokens", v_sum.get("prompt_tokens", 0)],
        ["Vibecoding System", "Completion Tokens", v_sum.get("completion_tokens", 0)],
        ["Vibecoding System", "Total AI Tokens", v_sum.get("total_tokens", 0)],
        ["Vibecoding System", "Total Usage Cost ($)", v_sum.get("total_cost", 0.0)],
    ]
    for r in summary_rows:
        ws1.append(r)
    auto_fit_columns(ws1)

    # -------------------------------------------------------------
    # SHEET 2: Dsuite Organizations Capacity
    # -------------------------------------------------------------
    ws2 = wb.create_sheet(title="Dsuite Organizations")
    ws2.append(["Organization Name", "Max Agent Capacity", "Onboarded Agents", "Total AI Tokens", "Usage Cost ($)"])
    style_headers(ws2, 1, purple_fill)
    for org in d_orgs:
        ws2.append([
            org.get("organization_name"),
            org.get("max_agent_capacity", 0),
            org.get("total_onboarded_agents", 0),
            org.get("total_tokens_consumed", 0),
            org.get("total_cost", 0.0)
        ])
    auto_fit_columns(ws2)

    # -------------------------------------------------------------
    # SHEET 3: Vibecoding Organizations Breakdown
    # -------------------------------------------------------------
    ws3 = wb.create_sheet(title="Vibecoding Organizations")
    ws3.append(["Organization Name", "Total Users", "Total Projects", "Prompts Logged", "Prompt Tokens", "Completion Tokens", "Total Tokens", "Usage Cost ($)"])
    style_headers(ws3, 1, cyan_fill)
    for org in vibe_data.get("organization_breakdown", []):
        ws3.append([
            org.get("organization_name"),
            org.get("user_count", 0),
            org.get("project_count", 0),
            org.get("log_count", 0),
            org.get("prompt_tokens", 0),
            org.get("completion_tokens", 0),
            org.get("total_tokens", 0),
            org.get("total_cost", 0.0)
        ])
    auto_fit_columns(ws3)

    # -------------------------------------------------------------
    # SHEET 4: Vibecoding Projects Breakdown
    # -------------------------------------------------------------
    ws4 = wb.create_sheet(title="Vibecoding Projects")
    ws4.append(["Project Name", "Project ID", "Organization Name", "Primary User Email", "Prompts Logged", "Prompt Tokens", "Completion Tokens", "Total Tokens", "Usage Cost ($)"])
    style_headers(ws4, 1, cyan_fill)
    for proj in vibe_data.get("project_breakdown", []):
        ws4.append([
            proj.get("project_name"),
            proj.get("project_id"),
            proj.get("organization_name"),
            proj.get("email") or proj.get("username"),
            proj.get("log_count", 0),
            proj.get("prompt_tokens", 0),
            proj.get("completion_tokens", 0),
            proj.get("total_tokens", 0),
            proj.get("total_cost", 0.0)
        ])
    auto_fit_columns(ws4)

    # -------------------------------------------------------------
    # SHEET 5: Vibecoding Users Breakdown
    # -------------------------------------------------------------
    ws5 = wb.create_sheet(title="Vibecoding Users")
    ws5.append(["User Email", "Username", "Full Name", "Organization Name", "Active Projects", "Prompts Logged", "Prompt Tokens", "Completion Tokens", "Total Tokens", "Usage Cost ($)"])
    style_headers(ws5, 1, cyan_fill)
    for u in vibe_data.get("user_breakdown", []):
        ws5.append([
            u.get("email"),
            u.get("username"),
            u.get("full_name"),
            u.get("organization_name"),
            u.get("project_count", 0),
            u.get("log_count", 0),
            u.get("prompt_tokens", 0),
            u.get("completion_tokens", 0),
            u.get("total_tokens", 0),
            u.get("total_cost", 0.0)
        ])
    auto_fit_columns(ws5)

    # Save to buffer
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    filename = f"Dsuite_Vibecoding_Master_Report_{datetime.datetime.now().strftime('%Y%m%d')}.xlsx"
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


class UpdateCapacityPayload(BaseModel):
    max_agent_capacity: int

@router.put("/api/superadmin/organizations/{org_name}/capacity")
def update_superadmin_org_capacity(
    org_name: str,
    payload: UpdateCapacityPayload,
    current_user: Annotated[models.User, Depends(auth.get_current_user)],
    db: Session = Depends(get_db),
):
    _require_super_admin(current_user)

    clean_org = org_name.strip()
    quota = db.query(models.OrganizationAgentQuota).filter(
        func.lower(models.OrganizationAgentQuota.organization_name) == clean_org.lower()
    ).first()

    if not quota:
        quota = models.OrganizationAgentQuota(
            organization_name=clean_org,
            max_agent_capacity=payload.max_agent_capacity
        )
        db.add(quota)
    else:
        quota.max_agent_capacity = payload.max_agent_capacity

    db.commit()
    db.refresh(quota)
    return {
        "success": True,
        "organization_name": clean_org,
        "max_agent_capacity": quota.max_agent_capacity
    }

@router.get("/api/superadmin/capacity-requests")
def get_superadmin_capacity_requests(
    current_user: Annotated[models.User, Depends(auth.get_current_user)],
    db: Session = Depends(get_db),
):
    _require_super_admin(current_user)

    requests = db.query(models.CapacityIncreaseRequest).order_by(
        models.CapacityIncreaseRequest.created_at.desc()
    ).all()

    result = []
    for r in requests:
        user = db.query(models.User).filter(models.User.id == r.requested_by_user_id).first()
        quota = db.query(models.OrganizationAgentQuota).filter(
            func.lower(models.OrganizationAgentQuota.organization_name) == (r.organization_name or "").lower()
        ).first()
        cur_cap = quota.max_agent_capacity if (quota and quota.max_agent_capacity is not None) else 0
        inc = r.total_requested_increase or ((r.requested_shared_count or 0) + (r.requested_dedicated_count or 0)) or 1

        result.append({
            "id": r.id,
            "organization_name": r.organization_name,
            "project_token": getattr(r, "project_token", None),
            "requested_by_user_id": r.requested_by_user_id,
            "requested_by_email": user.email if user else "Unknown",
            "current_capacity": cur_cap,
            "requested_capacity": cur_cap + inc,
            "total_requested_increase": inc,
            "requested_shared_count": getattr(r, "requested_shared_count", 0) or 0,
            "requested_dedicated_count": getattr(r, "requested_dedicated_count", 0) or 0,
            "reason": r.reason,
            "status": r.status,
            "review_comment": r.review_comment,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        })
    return result

class CapacityReviewPayload(BaseModel):
    status: str
    approved_total_capacity: Optional[int] = None
    review_comment: Optional[str] = None

@router.post("/api/superadmin/capacity-requests/{request_id}/approve")
def approve_superadmin_capacity_request(
    request_id: int,
    payload: CapacityReviewPayload,
    current_user: Annotated[models.User, Depends(auth.get_current_user)],
    db: Session = Depends(get_db),
):
    _require_super_admin(current_user)

    req = db.query(models.CapacityIncreaseRequest).filter(
        models.CapacityIncreaseRequest.id == request_id
    ).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")

    quota = _get_or_init_org_agent_quota(db, req.organization_name)
    inc = req.total_requested_increase or ((req.requested_shared_count or 0) + (req.requested_dedicated_count or 0)) or 1
    if payload.approved_total_capacity and payload.approved_total_capacity > (quota.max_agent_capacity or 0):
        approved_cap = payload.approved_total_capacity
    else:
        inc_val = payload.approved_total_capacity or inc
        approved_cap = int(quota.max_agent_capacity or 10) + inc_val

    req.status = "APPROVED"
    req.approved_total_capacity = approved_cap
    req.review_comment = payload.review_comment
    req.reviewed_by_user_id = current_user.id
    req.updated_at = datetime.utcnow()

    # Increase org capacity in OrganizationAgentQuota
    quota.max_agent_capacity = approved_cap
    quota.shared_quota = max(int(quota.shared_quota or 0), approved_cap)
    quota.dedicated_quota = max(int(quota.dedicated_quota or 0), approved_cap)

    # Sync corresponding ProjectAgentRequests to APPROVED
    proj_reqs_query = db.query(models.ProjectAgentRequest).filter(
        func.lower(models.ProjectAgentRequest.organization_name) == req.organization_name.lower(),
        models.ProjectAgentRequest.status.in_(["ESCALATED", "PENDING"])
    )
    if getattr(req, "project_token", None):
        proj_reqs_query = proj_reqs_query.filter(models.ProjectAgentRequest.project_token == req.project_token)
    proj_reqs = proj_reqs_query.all()
    for pr in proj_reqs:
        pr.status = "APPROVED"
        pr.review_comment = payload.review_comment or "Approved by Super Admin"
        pr.reviewed_by_user_id = current_user.id
        pr.updated_at = datetime.utcnow()

    db.commit()
    return {"success": True, "message": "Request approved", "approved_capacity": approved_cap}

@router.post("/api/superadmin/capacity-requests/{request_id}/reject")
def reject_superadmin_capacity_request(
    request_id: int,
    payload: CapacityReviewPayload,
    current_user: Annotated[models.User, Depends(auth.get_current_user)],
    db: Session = Depends(get_db),
):
    _require_super_admin(current_user)

    req = db.query(models.CapacityIncreaseRequest).filter(
        models.CapacityIncreaseRequest.id == request_id
    ).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")

    req.status = "REJECTED"
    req.review_comment = payload.review_comment
    req.reviewed_by_user_id = current_user.id
    req.updated_at = datetime.utcnow()

    # Sync corresponding ProjectAgentRequests to REJECTED
    proj_reqs_query = db.query(models.ProjectAgentRequest).filter(
        func.lower(models.ProjectAgentRequest.organization_name) == req.organization_name.lower(),
        models.ProjectAgentRequest.status.in_(["ESCALATED", "PENDING"])
    )
    if getattr(req, "project_token", None):
        proj_reqs_query = proj_reqs_query.filter(models.ProjectAgentRequest.project_token == req.project_token)
    proj_reqs = proj_reqs_query.all()
    for pr in proj_reqs:
        pr.status = "REJECTED"
        pr.review_comment = payload.review_comment or "Rejected by Super Admin"
        pr.reviewed_by_user_id = current_user.id
        pr.updated_at = datetime.utcnow()

    db.commit()
    return {"success": True, "message": "Request rejected"}

def _require_org_admin_or_super_admin(current_user: models.User) -> None:
    if not (bool(getattr(current_user, "is_org_admin", False)) or bool(getattr(current_user, "is_super_admin", False))):
        raise HTTPException(status_code=403, detail="Only Organization Admins can perform this action")

# ── End-User & Org Admin Agent Capacity Request Endpoints ───────────────────

class ProjectAgentRequestCreate(BaseModel):
    project_token: str
    project_name: Optional[str] = None
    requested_shared_count: int = 0
    requested_dedicated_count: int = 0
    reason: Optional[str] = None

class CapacityIncreaseCreate(BaseModel):
    project_token: Optional[str] = None
    project_name: Optional[str] = None
    requested_shared_count: int = 0
    requested_dedicated_count: int = 0
    total_requested_increase: int = 1
    reason: Optional[str] = None


# --- Extracted Block (Lines 4256-4283) ---
@router.get("/api/superadmin/audit-logs")
def get_superadmin_audit_logs(
    current_user: Annotated[models.User, Depends(auth.get_current_user)],
    db: Session = Depends(get_db),
):
    _require_super_admin(current_user)

    logs = db.query(models.UserActivityLog).order_by(
        models.UserActivityLog.created_at.desc()
    ).limit(200).all()

    result = []
    for l in logs:
        user = db.query(models.User).filter(models.User.id == l.user_id).first() if l.user_id else None
        result.append({
            "id": l.id,
            "user_id": l.user_id,
            "email": user.email if user else "Anonymous",
            "organization_name": user.organization_name if user else "System",
            "action": l.action,
            "method": l.method,
            "path": l.path,
            "ip_address": l.ip_address,
            "user_agent": l.user_agent,
            "created_at": l.created_at.isoformat() if l.created_at else None
        })
    return result


# --- Extracted Block (Lines 4544-5269) ---
@router.get("/organization/billing-logs")
def get_org_billing_and_logs(
    current_user: Annotated[models.User, Depends(auth.get_current_user)],
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db),
):
    import datetime
    organization_name = _require_org_admin(current_user)
    
    # Parse date filters
    start_dt = None
    end_dt = None
    if start_date:
        try:
            start_dt = datetime.datetime.fromisoformat(start_date)
        except Exception:
            pass
    if end_date:
        try:
            end_dt = datetime.datetime.fromisoformat(end_date) + datetime.timedelta(days=1) - datetime.timedelta(microseconds=1)
        except Exception:
            pass

    # 1. Get all users in the organization
    org_users = db.query(models.User).filter(
        func.lower(models.User.organization_name) == organization_name.lower()
    ).all()
    org_user_ids = [u.id for u in org_users]
    org_user_map = {u.id: u for u in org_users}

    # Determine organization onboarded_at timestamp (earliest activity/mapping date)
    onboard_dates = []
    uor_list = db.query(models.UserOrganizationRole).filter(
        func.lower(models.UserOrganizationRole.organization_name) == organization_name.lower()
    ).all()
    for uor in uor_list:
        if uor.created_at:
            onboard_dates.append(uor.created_at)

    roles_list = db.query(models.OrganizationRole).filter(
        func.lower(models.OrganizationRole.organization_name) == organization_name.lower()
    ).all()
    for r in roles_list:
        if r.created_at:
            onboard_dates.append(r.created_at)

    all_org_projects = db.query(models.GovernanceResponse).filter(
        (models.GovernanceResponse.owner_id.in_(org_user_ids)) |
        (func.lower(models.GovernanceResponse.organization_name) == organization_name.lower())
    ).all()
    for p in all_org_projects:
        if p.submission_date:
            onboard_dates.append(p.submission_date)

    try:
        from tokenops.services.tenant_resolver_service import TenantResolverService
        resolver = TenantResolverService(db)
        org_id, org_obj = resolver.resolve(organization_name)
        canonical_org_name = org_obj.name
    except Exception:
        org_id = None
        canonical_org_name = organization_name

    tenant_filter = or_(
        models.AIUsageLog.organization_id == org_id,
        and_(
            models.AIUsageLog.organization_id.is_(None),
            func.lower(models.AIUsageLog.organization_name) == canonical_org_name.lower()
        )
    )

    all_org_ai_logs = db.query(models.AIUsageLog).filter(tenant_filter).all()
    for l in all_org_ai_logs:
        if l.created_at:
            onboard_dates.append(l.created_at)

    if onboard_dates:
        onboarded_at_str = min(onboard_dates).isoformat()
    else:
        onboarded_at_str = None
    
    # 2. Get all projects in the organization
    org_projects_query = db.query(models.GovernanceResponse).filter(
        (models.GovernanceResponse.owner_id.in_(org_user_ids)) |
        (func.lower(models.GovernanceResponse.organization_name) == organization_name.lower())
    )
    if start_dt:
        org_projects_query = org_projects_query.filter(models.GovernanceResponse.submission_date >= start_dt)
    if end_dt:
        org_projects_query = org_projects_query.filter(models.GovernanceResponse.submission_date <= end_dt)
    org_projects = org_projects_query.all()
    
    # Aggregate AI stats
    ai_logs_query = db.query(models.AIUsageLog).filter(tenant_filter)
    if start_dt:
        ai_logs_query = ai_logs_query.filter(models.AIUsageLog.created_at >= start_dt)
    if end_dt:
        ai_logs_query = ai_logs_query.filter(models.AIUsageLog.created_at <= end_dt)
    ai_logs = ai_logs_query.all()
    
    total_cost = 0.0
    total_prompt_tokens = 0
    total_completion_tokens = 0
    cost_by_model = {}
    cost_by_user = {} # user_id -> cost
    tokens_by_user = {} # user_id -> tokens
    
    for log in ai_logs:
        total_cost += log.cost or 0.0
        total_prompt_tokens += log.prompt_tokens or 0
        total_completion_tokens += log.completion_tokens or 0
        
        model = log.model or "unknown"
        cost_by_model[model] = cost_by_model.get(model, 0.0) + (log.cost or 0.0)
        
        uid = log.user_id
        if uid:
            cost_by_user[uid] = cost_by_user.get(uid, 0.0) + (log.cost or 0.0)
            tokens_by_user[uid] = tokens_by_user.get(uid, 0) + (log.prompt_tokens or 0) + (log.completion_tokens or 0)
            
    # Round float values
    total_cost = round(total_cost, 4)
    cost_by_model = {k: round(v, 4) for k, v in cost_by_model.items()}
    
    # 3. Calculate session durations based on activity logs
    activity_logs_query = db.query(models.UserActivityLog).filter(
        models.UserActivityLog.user_id.in_(org_user_ids)
    )
    if start_dt:
        activity_logs_query = activity_logs_query.filter(models.UserActivityLog.created_at >= start_dt)
    if end_dt:
        activity_logs_query = activity_logs_query.filter(models.UserActivityLog.created_at <= end_dt)
    activity_logs = activity_logs_query.order_by(models.UserActivityLog.user_id, models.UserActivityLog.created_at).all()
    
    user_durations = {} # user_id -> seconds
    user_last_time = {} # user_id -> datetime
    user_session_count = {} # user_id -> sessions
    
    for log in activity_logs:
        uid = log.user_id
        log_time = log.created_at
        if not log_time:
            continue
        if uid not in user_durations:
            user_durations[uid] = 0
            user_last_time[uid] = log_time
            user_session_count[uid] = 1
            continue
            
        last_time = user_last_time[uid]
        diff_sec = (log_time - last_time).total_seconds()
        
        # If the gap is less than 30 minutes, accumulate it
        if 0 < diff_sec < 1800:
            user_durations[uid] += diff_sec
        elif diff_sec >= 1800:
            # new session
            user_session_count[uid] = user_session_count.get(uid, 0) + 1
            
        user_last_time[uid] = log_time

    # 4. Enrich user statistics list & compute user-wise infra costs ($1/hr based on active BournAI usage duration)
    total_token_cost = 0.0
    total_infra_cost = 0.0
    total_bournai_prompt_tokens = 0
    total_bournai_completion_tokens = 0
    user_stats = []

    for u in org_users:
        duration_sec = user_durations.get(u.id, 0)
        session_count = user_session_count.get(u.id, 0)
        
        # Count projects created by this user
        proj_count = sum(1 for p in org_projects if p.owner_id == u.id)
        
        # AI usage details for modal & user-wise infra cost calculation
        user_ai_logs = [log for log in ai_logs if log.user_id == u.id]
        ai_usage_by_model = {}
        user_ai_timestamps = []
        user_bournai_tokens = 0
        u_token_cost = 0.0

        for log in user_ai_logs:
            m = log.model or "unknown"
            if m not in ai_usage_by_model:
                ai_usage_by_model[m] = {"model": m, "requests": 0, "prompt": 0, "completion": 0, "cost": 0.0}
            ai_usage_by_model[m]["requests"] += 1
            ai_usage_by_model[m]["prompt"] += log.prompt_tokens or 0
            ai_usage_by_model[m]["completion"] += log.completion_tokens or 0
            ai_usage_by_model[m]["cost"] += log.cost or 0.0

            if log.created_at:
                user_ai_timestamps.append(log.created_at)

            is_bournai = m.lower() == "bournai"
            if is_bournai:
                u_token_cost += (log.cost or 0.0)
                b_tokens = (log.prompt_tokens or 0) + (log.completion_tokens or 0)
                user_bournai_tokens += b_tokens
                total_bournai_prompt_tokens += (log.prompt_tokens or 0)
                total_bournai_completion_tokens += (log.completion_tokens or 0)
            
        # User-wise token cost & infra cost ($0.70 / hr based on overall usage duration)
        if user_ai_timestamps:
            u_usage_dur_sec = (max(user_ai_timestamps) - min(user_ai_timestamps)).total_seconds()
        else:
            u_usage_dur_sec = 0.0
        
        u_infra_cost = (u_usage_dur_sec / 3600.0) * 0.7  # $0.7/hr rate per user
        u_total_cost = u_token_cost + u_infra_cost

        total_token_cost += u_token_cost
        total_infra_cost += u_infra_cost

        # Format for modal
        ai_usage_list = []
        for m, stats in ai_usage_by_model.items():
            stats["cost"] = round(stats["cost"], 4)
            ai_usage_list.append(stats)
            
        # Projects list for modal
        user_projects_list = []
        for p in org_projects:
            if p.owner_id == u.id:
                b_state = db.query(models.BootstrapState).filter(
                    models.BootstrapState.project_token == p.project_token
                ).first()
                user_projects_list.append({
                    "project_name": p.project_name or p.project_token,
                    "classification": p.classification or "SANDBOX",
                    "status": b_state.status if b_state else "pending"
                })
                
        # Recent sessions for modal
        recent_sessions_list = []
        user_activities = [l for l in activity_logs if l.user_id == u.id][-10:]
        user_activities.reverse()
        for act in user_activities:
            recent_sessions_list.append({
                "created_at": act.created_at.isoformat() if act.created_at else None,
                "action": act.action,
                "method": act.method,
                "path": act.path,
                "ip_address": act.ip_address or "—",
                "user_agent": act.user_agent or "—"
            })
            
        # Permissions paths for modal
        permissions_paths = db.query(models.UserOrganizationRole).filter(
            models.UserOrganizationRole.user_id == u.id,
            func.lower(models.UserOrganizationRole.organization_name) == organization_name.lower()
        ).all()
        paths_set = set()
        for uor in permissions_paths:
            perms = db.query(models.OrganizationRolePermission).filter(
                models.OrganizationRolePermission.role_id == uor.role_id
            ).all()
            for p_perm in perms:
                paths_set.add(p_perm.path)

        user_stats.append({
            "id": u.id,
            "email": u.email,
            "name": f"{u.first_name or ''} {u.last_name or ''}".strip() or u.email.split('@')[0],
            "is_active": u.is_active,
            "is_org_admin": u.is_org_admin,
            "total_duration_hours": round(duration_sec / 3600, 2),
            "usage_duration_hours": round(u_usage_dur_sec / 3600.0, 2),
            "token_cost": round(u_token_cost, 4),
            "infra_cost": round(u_infra_cost, 4),
            "total_cost": round(u_total_cost, 4),
            "ai_tokens": user_bournai_tokens,
            "projects_count": proj_count,
            "session_count": session_count,
            "last_login": u.last_login.isoformat() if u.last_login else None,
            "github_username": u.github_username or "—",
            "azure_devops_username": u.azure_devops_username or "—",
            # Details for drilldown modal
            "ai_usage": ai_usage_list,
            "projects": user_projects_list,
            "recent_sessions": recent_sessions_list,
            "permissions": sorted(list(paths_set))
        })
        
    # 5. Enrich projects list
    projects_list = []
    for p in org_projects:
        owner = org_user_map.get(p.owner_id)
        owner_email = owner.email if owner else "—"
        
        b_states = db.query(models.BootstrapState).filter(
            models.BootstrapState.project_token == p.project_token
        ).all()
        run_status = b_states[-1].status if b_states else "pending"
        total_runs = len(b_states)
        
        projects_list.append({
            "project_token": p.project_token,
            "project_name": p.project_name or p.project_token,
            "owner_email": owner_email,
            "classification": p.classification or "SANDBOX",
            "total_runs": total_runs,
            "run_status": run_status,
            "submission_date": p.submission_date.isoformat() if p.submission_date else None
        })

    # Serialize detailed AI logs for Excel export
    detailed_ai_logs = []
    project_name_map = {p.project_token: p.project_name for p in org_projects}
    for log in ai_logs:
        user_obj = org_user_map.get(log.user_id)
        user_email = user_obj.email if user_obj else "unknown"
        user_name = f"{user_obj.first_name or ''} {user_obj.last_name or ''}".strip() if user_obj else "unknown"
        if not user_name:
            user_name = user_email.split('@')[0]
            
        proj_name = project_name_map.get(log.project_token) or log.project_token or "System/General"
        
        detailed_ai_logs.append({
            "id": log.id,
            "created_at": log.created_at.isoformat() if log.created_at else None,
            "user_email": user_email,
            "user_name": user_name,
            "project_name": proj_name,
            "project_token": log.project_token or "—",
            "model": log.model or "unknown",
            "prompt_tokens": log.prompt_tokens or 0,
            "completion_tokens": log.completion_tokens or 0,
            "cost": round(log.cost or 0.0, 6)
        })

    total_combined_cost = round(total_token_cost + total_infra_cost, 4)

    return {
        "organization_name": organization_name,
        "onboarded_at": onboarded_at_str,
        "summary": {
            "total_token_cost": round(total_token_cost, 4),
            "total_infra_cost": round(total_infra_cost, 4),
            "total_cost": total_combined_cost,
            "total_prompt_tokens": total_bournai_prompt_tokens,
            "total_completion_tokens": total_bournai_completion_tokens,
            "cost_by_model": cost_by_model,
        },
        "user_stats": user_stats,
        "projects_list": projects_list,
        "detailed_ai_logs": detailed_ai_logs
    }

@router.get("/organization/download-billing-report")
def download_org_billing_report(
    current_user: Annotated[models.User, Depends(auth.get_current_user)],
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db),
):
    import io
    import json
    import datetime
    from interactive_dashboard_server import DASHBOARD_HTML_TEMPLATE
    
    organization_name = _require_org_admin(current_user)
    
    # Parse date filters
    start_dt = None
    end_dt = None
    if start_date:
        try:
            start_dt = datetime.datetime.fromisoformat(start_date)
        except Exception:
            pass
    if end_date:
        try:
            end_dt = datetime.datetime.fromisoformat(end_date) + datetime.timedelta(days=1) - datetime.timedelta(microseconds=1)
        except Exception:
            pass

    # 1. Get all users in the organization
    org_users = db.query(models.User).filter(
        func.lower(models.User.organization_name) == organization_name.lower()
    ).all()
    org_user_ids = [u.id for u in org_users]
    org_user_map = {u.id: u for u in org_users}
    
    # 2. Get all projects in the organization
    org_projects_query = db.query(models.GovernanceResponse).filter(
        (models.GovernanceResponse.owner_id.in_(org_user_ids)) |
        (func.lower(models.GovernanceResponse.organization_name) == organization_name.lower())
    )
    if start_dt:
        org_projects_query = org_projects_query.filter(models.GovernanceResponse.submission_date >= start_dt)
    if end_dt:
        org_projects_query = org_projects_query.filter(models.GovernanceResponse.submission_date <= end_dt)
    org_projects = org_projects_query.all()
    
    # Aggregate AI stats
    try:
        from tokenops.services.tenant_resolver_service import TenantResolverService
        resolver = TenantResolverService(db)
        org_id, org_obj = resolver.resolve(organization_name)
        canonical_org_name = org_obj.name
    except Exception:
        org_id = None
        canonical_org_name = organization_name

    tenant_filter = or_(
        models.AIUsageLog.organization_id == org_id,
        and_(
            models.AIUsageLog.organization_id.is_(None),
            func.lower(models.AIUsageLog.organization_name) == canonical_org_name.lower()
        )
    )

    ai_logs_query = db.query(models.AIUsageLog).filter(tenant_filter)
    if start_dt:
        ai_logs_query = ai_logs_query.filter(models.AIUsageLog.created_at >= start_dt)
    if end_dt:
        ai_logs_query = ai_logs_query.filter(models.AIUsageLog.created_at <= end_dt)
    ai_logs = ai_logs_query.all()
    
    total_prompt_tokens = 0
    total_completion_tokens = 0
    cost_by_model = {}
    cost_by_user = {}
    tokens_by_user = {}
    
    for log in ai_logs:
        total_prompt_tokens += log.prompt_tokens or 0
        total_completion_tokens += log.completion_tokens or 0
        
        model = log.model or "unknown"
        cost_by_model[model] = cost_by_model.get(model, 0.0) + (log.cost or 0.0)
        
        uid = log.user_id
        if uid:
            cost_by_user[uid] = cost_by_user.get(uid, 0.0) + (log.cost or 0.0)
            tokens_by_user[uid] = tokens_by_user.get(uid, 0) + (log.prompt_tokens or 0) + (log.completion_tokens or 0)
            
    cost_by_model = {k: round(v, 4) for k, v in cost_by_model.items()}
    
    # Calculate session durations based on activity logs
    activity_logs_query = db.query(models.UserActivityLog).filter(
        models.UserActivityLog.user_id.in_(org_user_ids)
    )
    if start_dt:
        activity_logs_query = activity_logs_query.filter(models.UserActivityLog.created_at >= start_dt)
    if end_dt:
        activity_logs_query = activity_logs_query.filter(models.UserActivityLog.created_at <= end_dt)
    activity_logs = activity_logs_query.order_by(models.UserActivityLog.user_id, models.UserActivityLog.created_at).all()
    
    user_durations = {}
    user_last_time = {}
    user_session_count = {}
    
    for log in activity_logs:
        uid = log.user_id
        log_time = log.created_at
        if not log_time:
            continue
        if uid not in user_durations:
            user_durations[uid] = 0
            user_last_time[uid] = log_time
            user_session_count[uid] = 1
            continue
            
        last_time = user_last_time[uid]
        diff_sec = (log_time - last_time).total_seconds()
        
        if 0 < diff_sec < 1800:
            user_durations[uid] += diff_sec
        elif diff_sec >= 1800:
            user_session_count[uid] = user_session_count.get(uid, 0) + 1
            
        user_last_time[uid] = log_time

    # Enrich user statistics list & calculate user-wise infra cost ($1/hr)
    total_token_cost = 0.0
    total_infra_cost = 0.0
    user_stats = []
    user_details_cache = {}

    for u in org_users:
        duration_sec = user_durations.get(u.id, 0)
        user_tokens = tokens_by_user.get(u.id, 0)
        session_count = user_session_count.get(u.id, 0)
        
        proj_count = sum(1 for p in org_projects if p.owner_id == u.id)
        
        user_ai_logs = [log for log in ai_logs if log.user_id == u.id]
        ai_usage_by_model = {}
        user_ai_timestamps = []

        for log in user_ai_logs:
            m = log.model or "unknown"
            if m not in ai_usage_by_model:
                ai_usage_by_model[m] = {"model": m, "requests": 0, "prompt": 0, "completion": 0, "cost": 0.0}
            ai_usage_by_model[m]["requests"] += 1
            ai_usage_by_model[m]["prompt"] += log.prompt_tokens or 0
            ai_usage_by_model[m]["completion"] += log.completion_tokens or 0
            ai_usage_by_model[m]["cost"] += log.cost or 0.0

            if log.created_at:
                user_ai_timestamps.append(log.created_at)

        u_token_cost = sum(log.cost or 0.0 for log in user_ai_logs)
        if user_ai_timestamps:
            u_usage_dur_sec = (max(user_ai_timestamps) - min(user_ai_timestamps)).total_seconds()
        else:
            u_usage_dur_sec = 0.0

        u_infra_cost = (u_usage_dur_sec / 3600.0) * 0.7  # $0.7/hr rate per user
        u_total_cost = u_token_cost + u_infra_cost

        total_token_cost += u_token_cost
        total_infra_cost += u_infra_cost
            
        ai_usage_list = []
        for m, stats in ai_usage_by_model.items():
            stats["cost"] = round(stats["cost"], 4)
            ai_usage_list.append(stats)
            
        user_projects_list = []
        for p in org_projects:
            if p.owner_id == u.id:
                b_state = db.query(models.BootstrapState).filter(
                    models.BootstrapState.project_token == p.project_token
                ).first()
                user_projects_list.append({
                    "project_name": p.project_name or p.project_token,
                    "classification": p.classification or "SANDBOX",
                    "status": b_state.status if b_state else "pending"
                })
                
        recent_sessions_list = []
        user_activities = [l for l in activity_logs if l.user_id == u.id][-10:]
        user_activities.reverse()
        for act in user_activities:
            recent_sessions_list.append({
                "created_at": act.created_at.isoformat() if act.created_at else None,
                "action": act.action,
                "method": act.method,
                "path": act.path,
                "ip_address": act.ip_address or "—",
                "user_agent": act.user_agent or "—"
            })
            
        permissions_paths = db.query(models.UserOrganizationRole).filter(
            models.UserOrganizationRole.user_id == u.id,
            func.lower(models.UserOrganizationRole.organization_name) == organization_name.lower()
        ).all()
        paths_set = set()
        for uor in permissions_paths:
            perms = db.query(models.OrganizationRolePermission).filter(
                models.OrganizationRolePermission.role_id == uor.role_id
            ).all()
            for p_perm in perms:
                paths_set.add(p_perm.path)

        u_stat = {
            "id": u.id,
            "email": u.email,
            "name": f"{u.first_name or ''} {u.last_name or ''}".strip() or u.email.split('@')[0],
            "is_active": u.is_active,
            "is_org_admin": u.is_org_admin,
            "total_duration_hours": round(duration_sec / 3600, 2),
            "usage_duration_hours": round(u_usage_dur_sec / 3600.0, 2),
            "token_cost": round(u_token_cost, 4),
            "infra_cost": round(u_infra_cost, 4),
            "total_cost": round(u_total_cost, 4),
            "ai_tokens": user_tokens,
            "projects_count": proj_count,
            "session_count": session_count,
            "last_login": u.last_login.isoformat() if u.last_login else None,
            "github_username": u.github_username or "—",
            "azure_devops_username": u.azure_devops_username or "—"
        }
        user_stats.append(u_stat)
        
        user_details_cache[str(u.id)] = {
            "projects": user_projects_list,
            "sessions": recent_sessions_list,
            "permissions": sorted(list(paths_set)),
            "ai_usage": ai_usage_list
        }
        
    projects_list = []
    for p in org_projects:
        owner = org_user_map.get(p.owner_id)
        owner_email = owner.email if owner else "—"
        
        b_states = db.query(models.BootstrapState).filter(
            models.BootstrapState.project_token == p.project_token
        ).all()
        run_status = b_states[-1].status if b_states else "pending"
        total_runs = len(b_states)
        
        projects_list.append({
            "project_token": p.project_token,
            "project_name": p.project_name or p.project_token,
            "owner_email": owner_email,
            "classification": p.classification or "SANDBOX",
            "total_runs": total_runs,
            "run_status": run_status,
            "submission_date": p.submission_date.isoformat() if p.submission_date else None
        })

    summary_data = {
        "total_token_cost": round(total_token_cost, 4),
        "total_infra_cost": round(total_infra_cost, 4),
        "total_cost": round(total_token_cost + total_infra_cost, 4),
        "total_prompt_tokens": total_prompt_tokens,
        "total_completion_tokens": total_completion_tokens,
        "cost_by_model": cost_by_model,
    }
    
    html = DASHBOARD_HTML_TEMPLATE
    html = html.replace("/*USERS_DATA_JSON_PLACEHOLDER*/ []", json.dumps(user_stats))
    html = html.replace("/*SUMMARY_DATA_JSON_PLACEHOLDER*/ {}", json.dumps(summary_data))
    html = html.replace("/*PROJECTS_DATA_JSON_PLACEHOLDER*/ []", json.dumps(projects_list))
    html = html.replace("/*ORGS_DATA_JSON_PLACEHOLDER*/ []", json.dumps([organization_name]))
    html = html.replace("/*USER_DETAILS_CACHE_PLACEHOLDER*/ {}", json.dumps(user_details_cache))
    
    bio = io.BytesIO(html.encode("utf-8"))
    return StreamingResponse(
        bio,
        media_type="text/html",
        headers={"Content-Disposition": f"attachment; filename={organization_name.replace(' ', '_')}_utilization_report.html"}
    )

@router.post("/admin/billing-emails/trigger")
async def trigger_billing_emails(
    current_user: Annotated[models.User, Depends(auth.get_current_user)],
    date: Optional[str] = None,
    email: Optional[str] = None,
    skip_logging_run_date: bool = False,
    dry_run: bool = False,
    super_user_only: bool = False,
    db: Session = Depends(get_db)
):
    """
    Manually triggers sending daily utilization & cost email reports.
    If 'date' is provided (format: YYYY-MM-DD), reports are sent for that date.
    If 'email' is provided, only sends to that specific user email.
    """
    if not current_user.is_org_admin:
        raise HTTPException(status_code=403, detail="Forbidden. Org admin rights required.")
        
    from daily_billing_email_service import send_daily_billing_emails, send_super_user_billing_report
    import datetime
    
    if super_user_only:
        run_date = datetime.datetime.utcnow()
        if date:
            try:
                parsed_dt = datetime.datetime.strptime(date, "%Y-%m-%d")
                # For super user report, set run_date to the end of target date so it queries midnight to 23:59:59
                run_date = parsed_dt.replace(hour=23, minute=59, second=59, microsecond=999999)
            except Exception:
                raise HTTPException(status_code=400, detail="Invalid date format. Expected YYYY-MM-DD.")
        try:
            results = await send_super_user_billing_report(db, run_date, dry_run=dry_run)
            return results
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to execute super user billing report: {str(e)}")
    else:
        run_date = datetime.datetime.utcnow()
        if date:
            try:
                # Parse target date and set run_date to the end of target date so it queries midnight to 23:59:59 of that day
                parsed_dt = datetime.datetime.strptime(date, "%Y-%m-%d")
                run_date = parsed_dt.replace(hour=23, minute=59, second=59, microsecond=999999)
            except Exception:
                raise HTTPException(status_code=400, detail="Invalid date format. Expected YYYY-MM-DD.")
                
        try:
            results = await send_daily_billing_emails(
                db, run_date, target_email=email, skip_logging_run_date=skip_logging_run_date, dry_run=dry_run
            )
            return results
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to execute daily billing emails: {str(e)}")


@router.get("/admin/billing-emails/controls")
def get_billing_emails_controls(
    current_user: Annotated[models.User, Depends(auth.get_current_user)]
):
    """
    Returns the current global blocklist and allowlist configurations.
    """
    if not current_user.is_org_admin:
        raise HTTPException(status_code=403, detail="Forbidden. Org admin rights required.")
        
    from daily_billing_email_service import load_email_controls
    return load_email_controls()


@router.post("/admin/billing-emails/controls")
def update_billing_emails_controls(
    payload: dict,
    current_user: Annotated[models.User, Depends(auth.get_current_user)]
):
    """
    Updates the global blocklist, allowlist, scheduler, and template configurations.
    """
    if not current_user.is_org_admin:
        raise HTTPException(status_code=403, detail="Forbidden. Org admin rights required.")
        
    from daily_billing_email_service import load_email_controls, save_email_controls
    
    controls = load_email_controls()
    
    # Deep merge payload recursively
    def _deep_merge(dest: dict, source: dict) -> None:
        for k, v in source.items():
            if k in dest and isinstance(dest[k], dict) and isinstance(v, dict):
                _deep_merge(dest[k], v)
            else:
                dest[k] = v
                
    _deep_merge(controls, payload)
                
    save_email_controls(controls)
    return {"message": "Email delivery controls updated successfully", "controls": controls}


# --- Extracted Block (Lines 5449-5645) ---
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


# --- Extracted Block (Lines 5716-6108) ---
@router.get("/organization/agent-quota", response_model=schemas.OrganizationAgentQuotaResponse)
def get_organization_agent_quota(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    organization_name = _require_organization(current_user)
    quota = _get_or_init_org_agent_quota(db, organization_name)
    usage = _count_org_agent_usage(db, organization_name)
    shared_quota = int(quota.shared_quota or 0)
    dedicated_quota = int(quota.dedicated_quota or 0)
    max_cap = int(getattr(quota, "max_agent_capacity", 0) or 0)

    # Count total non-default onboarded custom agents for this organization
    total_onboarded = db.query(models.OrganizationAgentMapping).filter(
        func.lower(models.OrganizationAgentMapping.organization_name) == organization_name.lower(),
        models.OrganizationAgentMapping.is_default.is_(False),
        models.OrganizationAgentMapping.project_token.isnot(None)
    ).count()

    physical_onboarded = db.query(models.OrganizationAgentMapping).filter(
        func.lower(models.OrganizationAgentMapping.organization_name) == organization_name.lower(),
        models.OrganizationAgentMapping.is_default.is_(False),
        models.OrganizationAgentMapping.is_virtual_shared.is_(False),
        models.OrganizationAgentMapping.project_token.isnot(None)
    ).count()

    virtual_onboarded = db.query(models.OrganizationAgentMapping).filter(
        func.lower(models.OrganizationAgentMapping.organization_name) == organization_name.lower(),
        models.OrganizationAgentMapping.is_default.is_(False),
        models.OrganizationAgentMapping.is_virtual_shared.is_(True),
        models.OrganizationAgentMapping.project_token.isnot(None)
    ).count()

    available_cap = max(0, max_cap - physical_onboarded)

    return schemas.OrganizationAgentQuotaResponse(
        organization_name=organization_name,
        max_agent_capacity=max_cap,
        total_onboarded_agents=total_onboarded,
        physical_workers_onboarded=physical_onboarded,
        virtual_shared_onboarded=virtual_onboarded,
        available_capacity=available_cap,
        shared_quota=shared_quota,
        dedicated_quota=dedicated_quota,
        shared_used=usage["shared"],
        dedicated_used=usage["dedicated"],
        shared_available=max(0, shared_quota - usage["shared"]),
        dedicated_available=max(0, dedicated_quota - usage["dedicated"]),
        shared_dev_quota=int(quota.shared_dev_quota or 0),
        shared_test_quota=int(quota.shared_test_quota or 0),
        dedicated_dev_quota=int(quota.dedicated_dev_quota or 0),
        dedicated_test_quota=int(quota.dedicated_test_quota or 0),
        shared_dev_used=usage["shared_dev"],
        shared_test_used=usage["shared_test"],
        dedicated_dev_used=usage["dedicated_dev"],
        dedicated_test_used=usage["dedicated_test"],
        updated_at=quota.updated_at,
    )



@router.post("/organization/agent-quota/increase", response_model=schemas.OrganizationAgentQuotaResponse)
def increase_organization_agent_quota(
    payload: schemas.OrganizationAgentQuotaIncreaseRequest,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    organization_name = _require_org_admin(current_user)
    kind = _normalized_text(payload.kind).lower()
    sub_type = _normalized_text(getattr(payload, 'sub_type', None) or '').lower()
    amount = int(payload.amount or 0)
    if kind not in ("shared", "dedicated"):
        raise HTTPException(status_code=400, detail="kind must be 'shared' or 'dedicated'")
    if amount <= 0 or amount > 1000:
        raise HTTPException(status_code=400, detail="amount must be between 1 and 1000")

    quota = _get_or_init_org_agent_quota(db, organization_name)
    if kind == "shared":
        if sub_type == "dev":
            quota.shared_dev_quota = int(quota.shared_dev_quota or 0) + amount
        elif sub_type == "test":
            quota.shared_test_quota = int(quota.shared_test_quota or 0) + amount
        else:
            quota.shared_dev_quota = int(quota.shared_dev_quota or 0) + amount
        # Enforce shared_quota is the sum of Dev and Test capacity
        quota.shared_quota = int(quota.shared_dev_quota or 0) + int(quota.shared_test_quota or 0)
    elif kind == "dedicated":
        if sub_type == "dev":
            quota.dedicated_dev_quota = int(quota.dedicated_dev_quota or 0) + amount
        elif sub_type == "test":
            quota.dedicated_test_quota = int(quota.dedicated_test_quota or 0) + amount
        else:
            quota.dedicated_dev_quota = int(quota.dedicated_dev_quota or 0) + amount
        # Enforce dedicated_quota is the sum of Dev and Test capacity
        quota.dedicated_quota = int(quota.dedicated_dev_quota or 0) + int(quota.dedicated_test_quota or 0)
    
    db.add(quota)
    db.commit()
    db.refresh(quota)

    usage = _count_org_agent_usage(db, organization_name)
    shared_quota = int(quota.shared_quota or 0)
    dedicated_quota = int(quota.dedicated_quota or 0)
    return schemas.OrganizationAgentQuotaResponse(
        organization_name=organization_name,
        shared_quota=shared_quota,
        dedicated_quota=dedicated_quota,
        shared_used=usage["shared"],
        dedicated_used=usage["dedicated"],
        shared_available=max(0, shared_quota - usage["shared"]),
        dedicated_available=max(0, dedicated_quota - usage["dedicated"]),
        shared_dev_quota=int(quota.shared_dev_quota or 0),
        shared_test_quota=int(quota.shared_test_quota or 0),
        dedicated_dev_quota=int(quota.dedicated_dev_quota or 0),
        dedicated_test_quota=int(quota.dedicated_test_quota or 0),
        shared_dev_used=usage["shared_dev"],
    )


# ===== SUPER ADMIN & CAPACITY REQUEST ENDPOINTS =====

@router.get("/api/superadmin/dashboard-stats", response_model=schemas.SuperAdminDashboardStatsResponse)
def get_super_admin_dashboard_stats(
    super_admin: models.User = Depends(auth.get_current_super_admin),
    db: Session = Depends(get_db),
):
    # Total organizations
    user_orgs = db.query(models.User.organization_name).filter(models.User.organization_name.isnot(None)).distinct()
    quota_orgs = db.query(models.OrganizationAgentQuota.organization_name).distinct()
    all_orgs = set([r[0] for r in user_orgs.all() if r[0]] + [r[0] for r in quota_orgs.all() if r[0]])
    total_organizations = len(all_orgs)

    # Total onboarded agents
    total_onboarded_agents = db.query(models.Agent).count()

    # Dedicated / Shared / Borrowed breakdown
    dedicated_agents = db.query(models.OrganizationAgentMapping).filter(models.OrganizationAgentMapping.agent_kind == "dedicated").count()
    shared_agents = db.query(models.OrganizationAgentMapping).filter(models.OrganizationAgentMapping.agent_kind == "shared").count()
    borrowed_dedicated_agents = db.query(models.OrganizationAgentMapping).filter(models.OrganizationAgentMapping.is_borrowed.is_(True)).count()

    # Pending capacity requests
    pending_capacity_requests = db.query(models.CapacityIncreaseRequest).filter(models.CapacityIncreaseRequest.status == "PENDING").count()

    # Billing & Token Usage
    usage_logs = db.query(models.AIUsageLog).all()
    organization_billing = sum([float(log.cost or 0.0) for log in usage_logs])
    ai_token_usage = sum([int((log.prompt_tokens or 0) + (log.completion_tokens or 0)) for log in usage_logs])

    # Project Stats
    total_projects = db.query(models.GovernanceResponse).count()
    archived_projects = db.query(models.GovernanceResponse).filter(models.GovernanceResponse.is_archived.is_(True)).count()
    active_projects = total_projects - archived_projects

    # Active Users
    active_users = db.query(models.User).filter(models.User.is_active.is_(True)).count()

    # Running Containers & Utilization
    running_docker_containers = agent_service.get_running_containers_count() if hasattr(agent_service, "get_running_containers_count") else (dedicated_agents + shared_agents)
    agent_utilization = round((float(running_docker_containers) / float(max(1, total_onboarded_agents))) * 100.0, 1)

    return schemas.SuperAdminDashboardStatsResponse(
        total_organizations=total_organizations,
        total_onboarded_agents=total_onboarded_agents,
        running_docker_containers=running_docker_containers,
        dedicated_agents=dedicated_agents,
        shared_agents=shared_agents,
        borrowed_dedicated_agents=borrowed_dedicated_agents,
        pending_capacity_requests=pending_capacity_requests,
        organization_billing=round(organization_billing, 2),
        ai_token_usage=ai_token_usage,
        project_statistics={"total": total_projects, "active": active_projects, "archived": archived_projects},
        active_users=active_users,
        agent_utilization=agent_utilization,
    )


@router.get("/api/superadmin/organizations")
def get_super_admin_organizations(
    super_admin: models.User = Depends(auth.get_current_super_admin),
    db: Session = Depends(get_db),
):
    quotas = db.query(models.OrganizationAgentQuota).all()
    results = []
    for q in quotas:
        onboarded = db.query(models.OrganizationAgentMapping).filter(
            func.lower(models.OrganizationAgentMapping.organization_name) == q.organization_name.lower(),
            models.OrganizationAgentMapping.is_default.is_(False)
        ).count()
        user_count = db.query(models.User).filter(
            func.lower(models.User.organization_name) == q.organization_name.lower()
        ).count()
        results.append({
            "organization_name": q.organization_name,
            "max_agent_capacity": q.max_agent_capacity,
            "total_onboarded_agents": onboarded,
            "available_capacity": max(0, q.max_agent_capacity - onboarded),
            "shared_quota": q.shared_quota,
            "dedicated_quota": q.dedicated_quota,
            "user_count": user_count,
            "updated_at": q.updated_at,
        })
    return results


@router.put("/api/superadmin/organizations/{org_name}/capacity")
def update_super_admin_organization_capacity(
    org_name: str,
    payload: schemas.SuperAdminCapUpdate,
    super_admin: models.User = Depends(auth.get_current_super_admin),
    db: Session = Depends(get_db),
):
    quota = _get_or_init_org_agent_quota(db, org_name)
    quota.max_agent_capacity = max(1, payload.max_agent_capacity)
    db.add(quota)
    db.commit()
    db.refresh(quota)
    return {
        "success": True,
        "organization_name": org_name,
        "max_agent_capacity": quota.max_agent_capacity,
    }


@router.get("/api/superadmin/capacity-requests", response_model=List[schemas.CapacityIncreaseRequestResponse])
def get_super_admin_capacity_requests(
    super_admin: models.User = Depends(auth.get_current_super_admin),
    db: Session = Depends(get_db),
):
    requests = db.query(models.CapacityIncreaseRequest).order_by(models.CapacityIncreaseRequest.created_at.desc()).all()
    response = []
    for req in requests:
        user = db.query(models.User).filter(models.User.id == req.requested_by_user_id).first()
        item = schemas.CapacityIncreaseRequestResponse(
            id=req.id,
            organization_name=req.organization_name,
            requested_by_user_id=req.requested_by_user_id,
            requested_by_email=user.email if user else None,
            project_token=req.project_token,
            requested_shared_count=req.requested_shared_count or 0,
            requested_dedicated_count=req.requested_dedicated_count or 0,
            total_requested_increase=req.total_requested_increase or 1,
            reason=req.reason,
            status=req.status,
            approved_total_capacity=req.approved_total_capacity,
            reviewed_by_user_id=req.reviewed_by_user_id,
            review_comment=req.review_comment,
            created_at=req.created_at,
            updated_at=req.updated_at,
        )
        response.append(item)
    return response


@router.post("/api/superadmin/capacity-requests/{request_id}/approve")
def approve_capacity_request(
    request_id: int,
    payload: schemas.CapacityIncreaseRequestReview,
    super_admin: models.User = Depends(auth.get_current_super_admin),
    db: Session = Depends(get_db),
):
    req = db.query(models.CapacityIncreaseRequest).filter(models.CapacityIncreaseRequest.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Capacity request not found")

    req.status = "APPROVED"
    req.reviewed_by_user_id = super_admin.id
    req.review_comment = payload.review_comment

    quota = _get_or_init_org_agent_quota(db, req.organization_name)
    inc_amount = payload.approved_total_capacity or req.total_requested_increase or 1
    if payload.approved_total_capacity and payload.approved_total_capacity > (quota.max_agent_capacity or 0):
        approved_cap = payload.approved_total_capacity
    else:
        approved_cap = int(quota.max_agent_capacity or 10) + inc_amount

    quota.max_agent_capacity = approved_cap
    quota.shared_quota = max(int(quota.shared_quota or 0), approved_cap)
    quota.dedicated_quota = max(int(quota.dedicated_quota or 0), approved_cap)
    req.approved_total_capacity = quota.max_agent_capacity

    db.add(req)
    db.add(quota)
    db.commit()
    db.refresh(quota)
    db.refresh(req)

    return {
        "success": True,
        "request_id": req.id,
        "status": "APPROVED",
        "new_max_agent_capacity": quota.max_agent_capacity,
    }


@router.post("/api/superadmin/capacity-requests/{request_id}/reject")
def reject_capacity_request(
    request_id: int,
    payload: schemas.CapacityIncreaseRequestReview,
    super_admin: models.User = Depends(auth.get_current_super_admin),
    db: Session = Depends(get_db),
):
    req = db.query(models.CapacityIncreaseRequest).filter(models.CapacityIncreaseRequest.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Capacity request not found")

    req.status = "REJECTED"
    req.reviewed_by_user_id = super_admin.id
    req.review_comment = payload.review_comment

    db.add(req)
    db.commit()
    db.refresh(req)

    return {
        "success": True,
        "request_id": req.id,
        "status": "REJECTED",
    }


@router.get("/api/superadmin/audit-logs")
def get_super_admin_audit_logs(
    page: int = 1,
    limit: int = 20,
    super_admin: models.User = Depends(auth.get_current_super_admin),
    db: Session = Depends(get_db),
):
    offset = (page - 1) * limit
    total = db.query(models.UserActivityLog).count()
    logs = db.query(models.UserActivityLog).order_by(models.UserActivityLog.created_at.desc()).offset(offset).limit(limit).all()
    return {
        "total": total,
        "page": page,
        "limit": limit,
        "logs": [
            {
                "id": l.id,
                "user_id": l.user_id,
                "action": l.action,
                "method": l.method,
                "path": l.path,
                "ip_address": l.ip_address,
                "created_at": l.created_at,
            } for l in logs
        ]
    }


@router.post("/api/organization/capacity-request")
def submit_organization_capacity_request(
    payload: schemas.CapacityIncreaseRequestCreate,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    organization_name = _require_organization(current_user)
    tot_req = max(1, payload.requested_shared_count + payload.requested_dedicated_count)
    if payload.total_requested_increase > 0:
        tot_req = payload.total_requested_increase

    req = models.CapacityIncreaseRequest(
        organization_name=organization_name,
        requested_by_user_id=current_user.id,
        project_token=payload.project_token,
        requested_shared_count=payload.requested_shared_count,
        requested_dedicated_count=payload.requested_dedicated_count,
        total_requested_increase=tot_req,
        reason=payload.reason or "Capacity expansion requested",
        status="PENDING",
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    return {
        "success": True,
        "request_id": req.id,
        "organization_name": organization_name,
        "status": "PENDING",
        "message": "Capacity increase request submitted to Super Admin."
    }


@router.get("/api/organization/capacity-requests")
def get_organization_capacity_requests(
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    organization_name = _require_organization(current_user)
    reqs = db.query(models.CapacityIncreaseRequest).filter(
        func.lower(models.CapacityIncreaseRequest.organization_name) == organization_name.lower()
    ).order_by(models.CapacityIncreaseRequest.created_at.desc()).all()
    return reqs

# --- Document Endpoints ---

