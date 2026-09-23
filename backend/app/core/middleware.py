"""
DSuite BRD Analyzer - Core HTTP Middlewares
Audit logging and context propagation middleware.
"""

import asyncio
import concurrent.futures
import logging
import re
import urllib.parse
from typing import Dict, Optional

from fastapi import Request
from jose import jwt

import models
from database import SessionLocal
from config import settings
try:
    from app.integrations.llm.llm_gateway import (
        current_project_name_var,
        current_project_token_var,
        current_purpose_var,
        current_user_id_var,
        current_user_org_var,
    )
except ImportError:
    from llm_gateway import (
        current_project_name_var,
        current_project_token_var,
        current_purpose_var,
        current_user_id_var,
        current_user_org_var,
    )

logger = logging.getLogger(__name__)

# In-memory email to user_id cache to avoid DB hits on every request
_user_id_cache: Dict[str, int] = {}
# In-memory project_token to project_name cache
_project_name_cache: Dict[str, str] = {}

# Whitelist of major application actions to log (all minor/polling APIs are ignored)
MAJOR_ACTION_PATTERNS = [
    # 1. Authentication & User Management
    "/auth/login",
    "/auth/register",
    "/auth/logout",
    "/auth/sso",
    "/token",
    # 2. Document Management
    "/upload",
    "/documents/upload",
    "/documents/delete",
    "/documents/download",
    # 3. BRD Analysis & AI Workflows
    "/ai/analyze",
    "/api/agent/assistant",
    # 4. Governance & Projects
    "/governance/submit",
    "/governance/projects",
    "/governance/revision",
    "/governance/archive",
    # 5. Agent & Task Execution Workflows
    "/api/agent/start",
    "/api/agent/execute",
    "/api/agent/nxdune/sync",
    # 6. Shared Documents
    "/shared-documents/create",
    "/shared-documents/download",
]


def is_major_action(path: str) -> bool:
    """Check if the given request path matches any major action pattern."""
    path_lower = path.lower()
    return any(pat in path_lower for pat in MAJOR_ACTION_PATTERNS)


def save_activity_log_bg(
    user_id: Optional[int],
    action: str,
    method: str,
    path: str,
    ip_address: Optional[str],
    user_agent: Optional[str],
):
    """Save user activity log to DB in a background thread to prevent blocking HTTP requests."""
    db_session = SessionLocal()
    try:
        activity = models.UserActivityLog(
            user_id=user_id,
            action=action,
            method=method,
            path=path,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        db_session.add(activity)
        db_session.commit()
    except Exception as e:
        logger.error(f"Failed to save user activity log: {e}")
    finally:
        db_session.close()


# Executor pool for background activity logging
_activity_logger_executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)


def is_jwt_token_string(val: Optional[str]) -> bool:
    if not val or not isinstance(val, str):
        return False
    parts = val.strip().split(".")
    return len(parts) == 3 and parts[0].startswith("ey")


def resolve_project_token(
    db, x_task_token: Optional[str], x_project_token: Optional[str] = None
) -> Optional[str]:
    if x_project_token:
        token = x_project_token.strip()
        if token:
            return token

    if not x_task_token:
        return None
    token = x_task_token.strip()
    if not token:
        return None

    # Check if x_task_token itself is actually a project UUID (doesn't look like JWT)
    parts = token.split(".")
    if len(parts) != 3:
        return token

    # Check if it looks like a JWT
    try:
        import base64
        import json

        payload_b64 = parts[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)
        payload_json = base64.urlsafe_b64decode(payload_b64).decode("utf-8")
        payload_data = json.loads(payload_json)
        client_id = payload_data.get("client_id")
        if client_id:
            # Find project by client_id in GovernanceResponse
            proj = (
                db.query(models.GovernanceResponse)
                .filter(models.GovernanceResponse.client_id == client_id)
                .first()
            )
            if proj:
                return proj.project_token
    except Exception as e:
        logger.error(f"Error decoding JWT in resolve_project_token: {e}")

    return token


async def activity_logging_middleware(request: Request, call_next):
    """
    Middleware that captures user activities and propagates LLM gateway context variables.
    """
    path = request.url.path

    # 1. Resolve user and project from auth token without extra DB queries
    auth_header = request.headers.get("Authorization")
    user_id = None
    user_org = None
    if auth_header and auth_header.startswith("Bearer "):
        try:
            token = auth_header.split(" ")[1]
            payload = jwt.decode(
                token, settings.secret_key, algorithms=[settings.algorithm]
            )
            # Check if user_id is directly in token payload
            user_id = payload.get("user_id") or payload.get("id")
            user_org = payload.get("org")
            if not user_id:
                email = payload.get("sub")
                if email:
                    # Use in-memory cache first to avoid DB query per request
                    if email in _user_id_cache:
                        user_id = _user_id_cache[email]
                    elif is_major_action(path):
                        # Only query DB for user_id if this is a major action step
                        db_session = SessionLocal()
                        try:
                            user = (
                                db_session.query(models.User)
                                .filter(models.User.email == email)
                                .first()
                            )
                            if user:
                                user_id = user.id
                                _user_id_cache[email] = user_id
                        finally:
                            db_session.close()
        except Exception:
            pass

    # Extract project token safely (never let JWT task tokens become project_token)
    raw_header_token = request.headers.get(
        "x-project-token"
    ) or request.headers.get("X-Project-Token")
    if raw_header_token and not is_jwt_token_string(raw_header_token):
        project_token = raw_header_token.strip()
    else:
        project_token = None

    if not project_token:
        raw_task_token = request.headers.get(
            "x-task-token"
        ) or request.headers.get("X-Task-Token")
        if raw_task_token:
            if not is_jwt_token_string(raw_task_token):
                project_token = raw_task_token.strip()
            else:
                try:
                    db_session = SessionLocal()
                    try:
                        resolved = resolve_project_token(
                            db_session, raw_task_token
                        )
                        if resolved and not is_jwt_token_string(resolved):
                            project_token = resolved
                    finally:
                        db_session.close()
                except Exception:
                    pass

    if not project_token:
        project_token = request.query_params.get("project_token")
    if not project_token:
        referer = request.headers.get("referer") or ""
        if "project_token=" in referer:
            try:
                parsed = urllib.parse.urlparse(referer)
                queries = urllib.parse.parse_qs(parsed.query)
                token_list = queries.get("project_token")
                if token_list and not is_jwt_token_string(token_list[0]):
                    project_token = token_list[0]
            except Exception:
                pass
    if not project_token:
        m = re.search(r"/projects?/([^/?#]+)", path)
        if m:
            candidate = m.group(1)
            if candidate not in (
                "list",
                "create",
                "all",
                "recent",
                "stats",
                "export",
            ) and not is_jwt_token_string(candidate):
                project_token = candidate

    # If project_token is still not found and user is authenticated, fall back to user's last_project_token
    if not project_token and user_id:
        try:
            db_session = SessionLocal()
            try:
                u = (
                    db_session.query(models.User)
                    .filter(models.User.id == user_id)
                    .first()
                )
                if (
                    u
                    and u.last_project_token
                    and not is_jwt_token_string(u.last_project_token)
                ):
                    project_token = u.last_project_token
            finally:
                db_session.close()
        except Exception:
            pass

    if is_jwt_token_string(project_token):
        project_token = None

    # Resolve project name if project_token is present
    project_name = None
    if project_token:
        if project_token in _project_name_cache:
            project_name = _project_name_cache[project_token]
        else:
            try:
                db_session = SessionLocal()
                try:
                    gov = (
                        db_session.query(models.GovernanceResponse)
                        .filter(
                            models.GovernanceResponse.project_token
                            == project_token
                        )
                        .first()
                    )
                    if gov and gov.project_name:
                        project_name = gov.project_name
                    else:
                        sp = (
                            db_session.query(models.ShareProject)
                            .filter(
                                models.ShareProject.project_token
                                == project_token
                            )
                            .first()
                        )
                        if sp and sp.project_name:
                            project_name = sp.project_name
                    if project_name:
                        _project_name_cache[project_token] = project_name
                finally:
                    db_session.close()
            except Exception:
                pass

    # Infer purpose from path for downstream LLM tracking if not explicitly set
    inferred_purpose = None
    lower_path = path.lower()
    if any(k in lower_path for k in ["/screening", "/screen"]):
        inferred_purpose = "Requirement Screening"
    elif any(k in lower_path for k in ["/analyze", "/analysis"]):
        inferred_purpose = "BRD Analysis & Architecture"
    elif any(k in lower_path for k in ["/gap-analysis", "/gap"]):
        inferred_purpose = "Codebase Gap Analysis"
    elif any(k in lower_path for k in ["/testcase", "/test-case", "/test_case"]):
        inferred_purpose = "Test Case Generation"
    elif any(k in lower_path for k in ["/chat", "/copilot"]):
        inferred_purpose = "Copilot Chat"
    elif any(
        k in lower_path
        for k in ["/agent", "/playground", "/react", "/master-task"]
    ):
        inferred_purpose = "Autonomous Coding Agent"
    elif any(
        k in lower_path
        for k in ["/pr-description", "/pr_description", "/pull-request"]
    ):
        inferred_purpose = "PR Description Generation"
    elif any(k in lower_path for k in ["/commit-message", "/commit_message"]):
        inferred_purpose = "Commit Message Generation"
    elif any(k in lower_path for k in ["/upload", "/extract", "/ingest"]):
        inferred_purpose = "Document Ingestion & OCR"

    # Set context variables for LLM log tracking
    token_user = current_user_id_var.set(user_id)
    token_proj = current_project_token_var.set(project_token)
    token_pname = current_project_name_var.set(project_name)
    token_org = current_user_org_var.set(user_org)
    token_purpose = current_purpose_var.set(inferred_purpose)

    try:
        response = await call_next(request)
    finally:
        current_user_id_var.reset(token_user)
        current_project_token_var.reset(token_proj)
        current_project_name_var.reset(token_pname)
        current_user_org_var.reset(token_org)
        current_purpose_var.reset(token_purpose)

    # 2. Log ONLY major application steps asynchronously in background
    if is_major_action(path):
        action = f"{request.method} {path}"
        ip_addr = request.client.host if request.client else None
        u_agent = request.headers.get("user-agent")

        try:
            loop = asyncio.get_running_loop()
            loop.run_in_executor(
                _activity_logger_executor,
                save_activity_log_bg,
                user_id,
                action,
                request.method,
                path,
                ip_addr,
                u_agent,
            )
        except Exception as e:
            logger.error(
                f"Failed to dispatch user activity log background task: {e}"
            )

    return response
