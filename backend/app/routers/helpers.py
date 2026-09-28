"""
DSuite BRD Analyzer - Router Helpers & Shared Utilities
Consolidates cross-cutting router helper functions, shared in-memory caches,
and data normalization routines extracted from legacy main.py.
"""

import asyncio
import hashlib
import json
import logging
import os
import re
import secrets
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from fastapi import HTTPException, WebSocket, status
from pydantic import BaseModel
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

import models
import schemas
from app.core.config import settings

logger = logging.getLogger(__name__)

# --- Caching and Rate Limiting ---

_agent_status_cache: Dict[str, Dict[str, Any]] = {}
_agent_cache_timestamps: Dict[str, float] = {}
AGENT_CACHE_TTL = 5.0

_task_cache: Dict[str, Dict[str, Any]] = {}
_task_cache_timestamps: Dict[str, float] = {}
TASK_CACHE_TTL = 3.0

_agent_status_rate_limit: Dict[str, float] = {}
AGENT_STATUS_RATE_LIMIT = 10.0

# WebSocket connections & live preview logs
_preview_log_store: Dict[str, List[Dict[str, Any]]] = {}
_preview_ws_connections: Dict[str, List[WebSocket]] = {}


def _get_cache_key(organization_name: str, project_token: Optional[str], user_id: int) -> str:
    return f"{organization_name}:{project_token or 'none'}:{user_id}"


def _is_cache_valid(cache_key: str) -> bool:
    if cache_key not in _agent_cache_timestamps:
        return False
    return time.time() - _agent_cache_timestamps[cache_key] < AGENT_CACHE_TTL


def _get_cached_agents(cache_key: str) -> Optional[Dict[str, Any]]:
    if _is_cache_valid(cache_key):
        return _agent_status_cache.get(cache_key)
    return None


def _cache_agents(cache_key: str, data: Dict[str, Any]) -> None:
    _agent_status_cache[cache_key] = data
    _agent_cache_timestamps[cache_key] = time.time()


def _get_task_cache_key(task_token: Optional[str], page: Optional[int]) -> str:
    return f"tasks:{task_token or 'none'}:{page or 'none'}"


def _is_task_cache_valid(cache_key: str) -> bool:
    if cache_key not in _task_cache_timestamps:
        return False
    return time.time() - _task_cache_timestamps[cache_key] < TASK_CACHE_TTL


def _get_cached_tasks(cache_key: str) -> Optional[Dict[str, Any]]:
    if _is_task_cache_valid(cache_key):
        return _task_cache.get(cache_key)
    return None


def _cache_tasks(cache_key: str, data: Dict[str, Any]) -> None:
    _task_cache[cache_key] = data
    _task_cache_timestamps[cache_key] = time.time()


def _check_agent_status_rate_limit(agent_id: str, user_id: int, project_token: Optional[str]) -> bool:
    rate_key = f"agent_status_rate:{agent_id}:{user_id}:{project_token or 'none'}"
    now = time.time()
    if rate_key in _agent_status_rate_limit:
        if now - _agent_status_rate_limit[rate_key] < AGENT_STATUS_RATE_LIMIT:
            return False
    _agent_status_rate_limit[rate_key] = now
    return True


def _invalidate_agent_cache(organization_name: str, project_token: Optional[str] = None) -> None:
    keys_to_remove = []
    for cache_key in _agent_status_cache.keys():
        if organization_name == "__all__":
            pt = project_token or "none"
            if f":{pt}:" in cache_key:
                keys_to_remove.append(cache_key)
        elif cache_key.startswith(f"{organization_name}:{project_token or 'none'}:"):
            keys_to_remove.append(cache_key)

    for key in keys_to_remove:
        _agent_status_cache.pop(key, None)
        _agent_cache_timestamps.pop(key, None)


def _invalidate_task_cache(task_token: Optional[str] = None) -> None:
    keys_to_remove = []
    for cache_key in _task_cache.keys():
        if cache_key.startswith(f"tasks:{task_token or 'none'}:"):
            keys_to_remove.append(cache_key)

    for key in keys_to_remove:
        _task_cache.pop(key, None)
        _task_cache_timestamps.pop(key, None)


# --- Text and Identifier Normalization ---

def _normalized_text(value: Optional[str]) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()


def _normalize_project_token(project_token: Optional[str]) -> Optional[str]:
    if not project_token:
        return None
    token = str(project_token).strip()
    return token or None


def _resolve_project_token(
    db: Session,
    x_task_token: Optional[str],
    x_project_token: Optional[str] = None,
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
        payload_b64 = parts[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)
        payload_json = base64.urlsafe_b64decode(payload_b64).decode("utf-8")
        payload_data = json.loads(payload_json)
        client_id = payload_data.get("client_id")
        if client_id:
            proj = (
                db.query(models.GovernanceResponse)
                .filter(models.GovernanceResponse.client_id == client_id)
                .first()
            )
            if proj:
                return proj.project_token
    except Exception as e:
        logger.error(f"Error decoding JWT in _resolve_project_token: {e}")

    return token


def _normalize_agent_kind(
    agent_kind: Optional[str],
    project_token: Optional[str],
    *,
    is_default: bool = False,
) -> str:
    kind = _normalized_text(agent_kind).lower()
    if is_default:
        return "system"
    if kind in {"shared", "dedicated"}:
        return kind
    return "dedicated" if _normalize_project_token(project_token) else "shared"


def _stored_agent_id(agent_id: str, project_token: Optional[str]) -> str:
    base_id = agent_id.split("#")[0] if "#" in agent_id else agent_id
    project_token = _normalize_project_token(project_token)
    if not project_token:
        return base_id
    prefix = f"{project_token}::"
    if base_id.startswith(prefix):
        return base_id
    return f"{prefix}{base_id}"


def _public_agent_id(agent_id: str, project_token: Optional[str]) -> str:
    base_id = agent_id.split("#")[0] if "#" in agent_id else agent_id
    project_token = _normalize_project_token(project_token)
    if not project_token:
        return base_id
    prefix = f"{project_token}::"
    if base_id.startswith(prefix):
        return base_id[len(prefix):]
    return base_id


def _generate_registration_password() -> str:
    return secrets.token_urlsafe(12)


# --- Authorization & Organization Helpers ---

def _require_organization(current_user: models.User) -> str:
    organization_name = _normalized_text(getattr(current_user, "organization_name", None))
    if not organization_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Organization not configured for this account",
        )
    return organization_name


def _require_org_admin(current_user: models.User) -> str:
    if not bool(getattr(current_user, "is_org_admin", False)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Organization admin access required",
        )
    organization_name = _normalized_text(getattr(current_user, "organization_name", None))
    if not organization_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Organization not configured for this account",
        )
    return organization_name


def _require_org_admin_or_super_admin(current_user: models.User) -> None:
    if not (bool(getattr(current_user, "is_org_admin", False)) or bool(getattr(current_user, "is_super_admin", False))):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only Organization Admins can perform this action",
        )


def _org_user_ids_subquery(db: Session, organization_name: str):
    org = _normalized_text(organization_name)
    if not org:
        return None
    return db.query(models.User.id).filter(
        func.lower(models.User.organization_name) == org.lower()
    ).scalar_subquery()


def _governance_query_for_user(db: Session, user: models.User):
    org = _normalized_text(getattr(user, "organization_name", None))
    if not org:
        return db.query(models.GovernanceResponse).filter(
            models.GovernanceResponse.owner_id == user.id
        )
    org_user_ids = _org_user_ids_subquery(db, org)
    return db.query(models.GovernanceResponse).filter(
        models.GovernanceResponse.owner_id.in_(org_user_ids)
    )


def check_project_name_exists_in_org(
    db: Session,
    project_name: str,
    user: models.User,
    exclude_token: Optional[str] = None,
) -> Optional[models.GovernanceResponse]:
    """
    Check if an active project with the given name already exists within the user's organization/tenant.
    Comparison is case-insensitive and trims whitespace.
    
    Returns the conflicting GovernanceResponse if found, otherwise None.
    """
    name = (project_name or "").strip()
    if not name:
        return None

    org_name = _normalized_text(getattr(user, "organization_name", None))
    not_archived = or_(
        models.GovernanceResponse.is_archived.is_(None),
        models.GovernanceResponse.is_archived.is_(False),
    )

    query = db.query(models.GovernanceResponse).filter(
        func.lower(func.trim(models.GovernanceResponse.project_name)) == name.lower(),
        not_archived,
    )

    if exclude_token:
        norm_token = _normalize_project_token(exclude_token)
        if norm_token:
            query = query.filter(models.GovernanceResponse.project_token != norm_token)

    if org_name:
        org_user_ids = _org_user_ids_subquery(db, org_name)
        if org_user_ids is not None:
            query = query.filter(
                or_(
                    func.lower(func.trim(models.GovernanceResponse.organization_name)) == org_name.lower(),
                    models.GovernanceResponse.owner_id.in_(org_user_ids),
                )
            )
        else:
            query = query.filter(
                func.lower(func.trim(models.GovernanceResponse.organization_name)) == org_name.lower()
            )
    else:
        # If user has no organization set, scope to the user's own projects
        query = query.filter(models.GovernanceResponse.owner_id == user.id)

    return query.first()


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


def _get_user_allowed_paths(db: Session, user: models.User) -> Tuple[Optional[str], List[str]]:
    org = _normalized_text(getattr(user, "organization_name", None))
    if not org:
        return None, []

    if bool(getattr(user, "is_super_admin", False)):
        superadmin_paths = [p.path for p in ORG_MANAGED_PAGES] + [
            "/superadmin/dashboard",
            "/superadmin/requests",
            "/superadmin/organizations",
            "/superadmin/global-billing",
            "/superadmin/tokenops",
            "/superadmin/roles",
            "/superadmin/capacity",
            "/superadmin/logs",
            "/superadmin/tickets",
        ]
        return "Super Admin", sorted(set(superadmin_paths))

    if bool(getattr(user, "is_org_admin", False)):
        return "Organization Admin", [p.path for p in ORG_MANAGED_PAGES]

    assignment = db.query(models.UserOrganizationRole).filter(
        models.UserOrganizationRole.user_id == user.id,
        func.lower(models.UserOrganizationRole.organization_name) == org.lower(),
    ).first()

    role = None
    if assignment:
        role = db.query(models.OrganizationRole).filter(
            models.OrganizationRole.id == assignment.role_id
        ).first()

    if not role:
        # Fallback to default Member role
        member_role = db.query(models.OrganizationRole).filter(
            func.lower(models.OrganizationRole.organization_name) == org.lower(),
            func.lower(models.OrganizationRole.name) == "member",
        ).first()
        if member_role:
            role = member_role

    if not role:
        # If no role, grant non-admin default paths
        default_paths = [p.path for p in ORG_MANAGED_PAGES if p.path != "/organization-admin"]
        return "Member", default_paths

    allowed = sorted({(perm.path or "").strip() for perm in (role.permissions or []) if (perm.path or "").strip()})
    return role.name, allowed


def _can_manage_governance(db: Session, user: models.User) -> bool:
    if bool(getattr(user, "is_org_admin", False)):
        return True
    _, allowed_paths = _get_user_allowed_paths(db, user)
    return "/governance-management" in (allowed_paths or [])


# --- Document and Governance Linking ---

def _extract_document_analysis_context(doc: models.Document) -> Optional[Dict[str, Any]]:
    if not doc.analysis_result:
        return None

    try:
        analysis = json.loads(doc.analysis_result)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None

    if not isinstance(analysis, dict):
        return None

    gov_ctx = analysis.get("governanceContext") if isinstance(analysis.get("governanceContext"), dict) else {}
    proj_meta = analysis.get("projectMeta") if isinstance(analysis.get("projectMeta"), dict) else {}

    return {
        "analysis": analysis,
        "result_id": proj_meta.get("governance_result_id") or gov_ctx.get("result_id"),
        "project_token": proj_meta.get("project_token") or gov_ctx.get("project_token"),
        "project_name": str(
            proj_meta.get("project_name") or gov_ctx.get("project_name") or ""
        ).strip().lower(),
    }


def _is_document_linked_to_governance(
    doc: models.Document,
    governance: models.GovernanceResponse,
) -> bool:
    ctx = _extract_document_analysis_context(doc)
    if not ctx:
        return False

    governance_token = str(governance.project_token or "").strip()
    governance_name = str(governance.project_name or "").strip().lower()

    if ctx["result_id"] is not None and str(ctx["result_id"]) == str(governance.id):
        return True
    if governance_token and ctx["project_token"] and str(ctx["project_token"]) == governance_token:
        return True
    if governance_name and ctx["project_name"] == governance_name:
        return True

    return False


def _update_project_tags(db: Session, project: models.GovernanceResponse, tags_list: list[str]):
    db.query(models.ProjectTag).filter(models.ProjectTag.project_id == project.id).delete()
    db.flush()
    for t in tags_list:
        t_stripped = t.strip()
        if t_stripped:
            db.add(models.ProjectTag(name=t_stripped, project_id=project.id))
    db.flush()


def parse_markdown_techniques(content: str) -> List[Dict[str, str]]:
    techniques = []
    if not content:
        return techniques

    lines = content.split("\n")
    current_name = None
    current_desc = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        if stripped.startswith("#"):
            if current_name:
                desc_str = "\n".join(current_desc).strip()
                desc_str = re.sub(r"^(description|instructions?)\s*:\s*", "", desc_str, flags=re.IGNORECASE)
                techniques.append({
                    "name": current_name,
                    "description": desc_str
                })
            current_name = stripped.lstrip("#").strip()
            current_desc = []
        else:
            if current_name is not None:
                current_desc.append(stripped)

    if current_name and current_desc:
        desc_str = "\n".join(current_desc).strip()
        desc_str = re.sub(r"^(description|instructions?)\s*:\s*", "", desc_str, flags=re.IGNORECASE)
        techniques.append({
            "name": current_name,
            "description": desc_str
        })

    if techniques:
        return techniques

    for line in lines:
        stripped = line.strip()
        if stripped.startswith(("-", "*", "+")) or (stripped and stripped[0].isdigit() and ". " in stripped[:4]):
            item = re.sub(r"^[\-\*\+\d\.\s]+", "", stripped).strip()
            match = re.match(r"^\*?\*?([^\*:\-\>]+)\*?\*?\s*(?::|-|->)\s*(.+)$", item)
            if match:
                name = match.group(1).strip()
                desc = match.group(2).strip()
                techniques.append({
                    "name": name,
                    "description": desc
                })

    return techniques


# --- All-Skipped Governance Logic ---

ALL_SKIPPED_GOVERNANCE_MESSAGE = "Our IT team will reach out to you. Thanks for connecting."
ALL_SKIPPED_ANALYZE_BLOCK_MESSAGE = "Sandbox is not approved. Our IT team will reach out to you soon."
ALL_SKIPPED_HARD_STOP = "All governance questions were skipped. IT follow-up is required before BRD analysis."
ALL_SKIPPED_SCORE = 5.0


def _is_skip_option_label(label: Optional[str]) -> bool:
    return str(label or "").strip().lower() == "skip"


def _all_answers_skipped_from_payload(payload: Any) -> bool:
    if not isinstance(payload, dict) or not payload:
        return False
    for value in payload.values():
        if not isinstance(value, dict):
            return False
        if not _is_skip_option_label(value.get("selected_option")):
            return False
    return True


def _all_answers_skipped_from_governance_context(governance_context: Optional[Dict[str, Any]]) -> bool:
    if not isinstance(governance_context, dict):
        return False

    answers = governance_context.get("answers")
    if isinstance(answers, list):
        answer_entries = [entry for entry in answers if isinstance(entry, dict)]
        if not answer_entries or len(answer_entries) != len(answers):
            return False
        return all(_is_skip_option_label(entry.get("selected_option")) for entry in answer_entries)

    if isinstance(answers, dict):
        return _all_answers_skipped_from_payload(answers)

    classification_description = str(governance_context.get("classification_description") or "").strip().lower()
    return "our it team will reach out to you" in classification_description


# --- Project Git Credentials Helpers ---

GLOBAL_GIT_CREDENTIAL_AGENT_ID = "__global_git__"


def _get_project_global_credential(
    db: Session,
    user: Union[models.User, int],
    project_token: Optional[str],
) -> Optional[models.AgentCredential]:
    if isinstance(user, int):
        resolved_user = db.query(models.User).filter(models.User.id == user).first()
        if not resolved_user:
            return None
        user = resolved_user

    project_token = _normalize_project_token(project_token)
    cred_query = db.query(models.AgentCredential).filter(
        models.AgentCredential.agent_id == GLOBAL_GIT_CREDENTIAL_AGENT_ID,
    )
    if project_token:
        cred_query = cred_query.filter(models.AgentCredential.project_token == project_token)
    else:
        cred_query = cred_query.filter(models.AgentCredential.project_token.is_(None))

    org_name = _normalized_text(getattr(user, "organization_name", None))
    if org_name:
        org_ids = db.query(models.User.id).filter(
            func.lower(models.User.organization_name) == org_name.lower()
        ).scalar_subquery()
        cred_query = cred_query.filter(models.AgentCredential.owner_id.in_(org_ids))
    else:
        cred_query = cred_query.filter(models.AgentCredential.owner_id == user.id)
    return cred_query.first()


def _list_legacy_agent_credentials(
    db: Session,
    user_id: Union[models.User, int],
    project_token: Optional[str],
) -> List[models.AgentCredential]:
    uid = user_id.id if isinstance(user_id, models.User) else user_id
    project_token = _normalize_project_token(project_token)
    cred_query = db.query(models.AgentCredential).filter(
        models.AgentCredential.owner_id == uid,
        models.AgentCredential.agent_id != GLOBAL_GIT_CREDENTIAL_AGENT_ID,
    )
    if project_token:
        cred_query = cred_query.filter(models.AgentCredential.project_token == project_token)
    else:
        cred_query = cred_query.filter(models.AgentCredential.project_token.is_(None))
    return cred_query.all()


def _upsert_project_global_credentials(
    db: Session,
    user: Union[models.User, int],
    git_repo_url: Optional[str] = None,
    git_token: Optional[str] = None,
    project_token: Optional[str] = None,
) -> models.AgentCredential:
    if isinstance(user, int):
        resolved_user = db.query(models.User).filter(models.User.id == user).first()
        if resolved_user:
            user = resolved_user

    project_token = _normalize_project_token(project_token)
    cred = _get_project_global_credential(db, user, project_token)
    if not cred:
        uid = user.id if isinstance(user, models.User) else user
        cred = models.AgentCredential(
            owner_id=uid,
            agent_id=GLOBAL_GIT_CREDENTIAL_AGENT_ID,
            project_token=project_token,
        )
        db.add(cred)

    if git_repo_url is not None:
        cleaned_repo = git_repo_url.strip()
        cred.git_repo_url = cleaned_repo or None
    if git_token is not None:
        cleaned_token = git_token.strip()
        cred.git_token = cleaned_token or None

    db.commit()
    db.refresh(cred)
    return cred


def _resolve_project_global_credential(
    db: Session,
    user: Union[models.User, int],
    project_token: Optional[str],
) -> Optional[models.AgentCredential]:
    cred = _get_project_global_credential(db, user, project_token)
    if cred:
        return cred

    uid = user.id if isinstance(user, models.User) else user
    legacy = sorted(
        _list_legacy_agent_credentials(db, uid, project_token),
        key=lambda row: row.updated_at or datetime.min,
        reverse=True,
    )
    if not legacy:
        return None

    latest_complete = next((row for row in legacy if row.git_repo_url and row.git_token), None)
    if latest_complete:
        repo_val = latest_complete.git_repo_url.strip()
        token_val = latest_complete.git_token.strip()
    else:
        first_repo = next((row.git_repo_url for row in legacy if row.git_repo_url), None)
        first_token = next((row.git_token for row in legacy if row.git_token), None)
        repo_val = first_repo.strip() if first_repo else None
        token_val = first_token.strip() if first_token else None

    if not repo_val and not token_val:
        return None

    return _upsert_project_global_credentials(
        db,
        user,
        git_repo_url=repo_val,
        git_token=token_val,
        project_token=project_token,
    )


# --- Agent DB & Quota Operations ---

def _legacy_default_dev_agent_filter(column):
    return or_(
        column.in_(("agent_01", "agent_02")),
        column.like("%::agent_01"),
        column.like("%::agent_02"),
    )


def _cleanup_legacy_default_dev_agents(db: Session) -> None:
    from app.services.agents import agent_service
    default_agent_ids = {
        row[0] for row in db.query(models.OrganizationAgentMapping.agent_id).filter(
            models.OrganizationAgentMapping.is_default.is_(True),
            _legacy_default_dev_agent_filter(models.OrganizationAgentMapping.agent_id),
        ).all()
    }

    deleted_mappings = db.query(models.OrganizationAgentMapping).filter(
        models.OrganizationAgentMapping.is_default.is_(True),
        _legacy_default_dev_agent_filter(models.OrganizationAgentMapping.agent_id),
    ).delete(synchronize_session=False)

    deleted_agents = 0
    if default_agent_ids:
        deleted_agents = db.query(models.Agent).filter(
            models.Agent.id.in_(default_agent_ids),
        ).delete(synchronize_session=False)

    if deleted_mappings or deleted_agents:
        logger.info(f"[cleanup] Removed {deleted_mappings} legacy default mappings and {deleted_agents} legacy default agents")
        db.commit()
        agent_service.clear_all_runtime_state()


def _ensure_default_agents(db: Session, project_token: Optional[str] = None) -> None:
    from app.services.agents import agent_service
    project_token = _normalize_project_token(project_token)
    _cleanup_legacy_default_dev_agents(db)
    default_agents = agent_service.get_default_agents(project_token)
    stored_ids = [_stored_agent_id(agent["id"], project_token) for agent in default_agents]
    existing_agents = {
        agent.id: agent
        for agent in db.query(models.Agent).filter(models.Agent.id.in_(stored_ids)).all()
    }
    for agent in default_agents:
        stored_id = _stored_agent_id(agent["id"], project_token)
        if stored_id in existing_agents:
            existing_agent = existing_agents[stored_id]
            if existing_agent.project_token != project_token:
                existing_agent.project_token = project_token
                db.add(existing_agent)
            continue
        db.add(
            models.Agent(
                id=stored_id,
                name=agent["name"],
                type=agent.get("type"),
                project_token=project_token,
                specialization=agent.get("specialization"),
                skills_summary=agent.get("skills_summary"),
                allowed_tools=agent.get("allowed_tools"),
            )
        )
    db.commit()


def _ensure_default_agents_for_org(
    db: Session,
    organization_name: str,
    project_token: Optional[str] = None,
) -> None:
    from app.services.agents import agent_service
    project_token = _normalize_project_token(project_token)
    _ensure_default_agents(db, project_token)
    org = _normalized_text(organization_name)
    if not org:
        return
    for agent in agent_service.get_default_agents(project_token):
        stored_id = _stored_agent_id(agent["id"], project_token)
        _ensure_org_agent_mapping(db, org, stored_id, project_token, is_default=True)


def _bootstrap_org_agent_mappings_if_missing(
    db: Session,
    organization_name: str,
    project_token: Optional[str],
) -> None:
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
    normalized_sub_type = (_normalized_text(agent_sub_type) or "").lower() or None
    existing = db.query(models.OrganizationAgentMapping).filter(
        func.lower(models.OrganizationAgentMapping.organization_name) == organization_name.lower(),
        models.OrganizationAgentMapping.agent_id == agent_id,
    ).first()
    if existing:
        existing.project_token = project_token
        existing.agent_kind = normalized_kind
        existing.is_default = bool(is_default)
        if normalized_sub_type:
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
) -> Dict[str, int]:
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
            if sub_type == "test":
                stats["shared_test"] += 1
            else:
                stats["shared_dev"] += 1
        elif kind == "dedicated":
            stats["dedicated"] += 1
            if sub_type == "test":
                stats["dedicated_test"] += 1
            else:
                stats["dedicated_dev"] += 1
    return stats


def _count_org_agent_usage_for_project(
    db: Session,
    organization_name: str,
    project_token: Optional[str],
) -> Dict[str, int]:
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
            if sub_type == "test":
                stats["shared_test"] += 1
            else:
                stats["shared_dev"] += 1
        elif kind == "dedicated":
            stats["dedicated"] += 1
            if sub_type == "test":
                stats["dedicated_test"] += 1
            else:
                stats["dedicated_dev"] += 1
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


def _upsert_agent_record(
    db: Session,
    agent_id: str,
    name: Optional[str],
    agent_type: Optional[str],
    project_token: Optional[str],
) -> models.Agent:
    project_token = _normalize_project_token(project_token)
    stored_id = _stored_agent_id(agent_id, project_token)
    record = db.query(models.Agent).filter(models.Agent.id == stored_id).first()
    if not record:
        record = models.Agent(
            id=stored_id,
            name=name or agent_id,
            type=agent_type,
            project_token=project_token,
        )
        db.add(record)
    else:
        if name:
            record.name = name
        if agent_type:
            record.type = agent_type
        if record.project_token != project_token:
            record.project_token = project_token
    db.commit()
    db.refresh(record)
    return record


def _delete_agent_record(db: Session, agent_id: str, project_token: Optional[str]) -> None:
    project_token = _normalize_project_token(project_token)
    stored_id = _stored_agent_id(agent_id, project_token)
    db.query(models.Agent).filter(models.Agent.id == stored_id).delete()
    db.commit()


def _runtime_agent_records(records: List[models.Agent], project_token: Optional[str]) -> List[Dict[str, Any]]:
    project_token = _normalize_project_token(project_token)
    from app.core.database import SessionLocal
    db = SessionLocal()
    try:
        mapping_rows = db.query(
            models.OrganizationAgentMapping.agent_id,
            models.OrganizationAgentMapping.agent_kind,
            models.OrganizationAgentMapping.shared_count,
            models.OrganizationAgentMapping.dedicated_count,
        ).filter(
            models.OrganizationAgentMapping.project_token == project_token
        ).all() if project_token else []

        mapping_info = {}
        for row in mapping_rows:
            raw_id = row[0]
            kind = row[1] or "shared"
            sc = int(row[2] or 0)
            dc = int(row[3] or 0)
            mapping_info[_public_agent_id(raw_id, project_token)] = (kind, sc, dc)

        expanded = []
        for rec in records:
            public_id = _public_agent_id(rec.id, project_token)
            is_default_system = public_id in ("g_agent_01", "m_agent_01", "deploy_agent") or public_id.startswith("g_agent_") or public_id.startswith("m_agent_")

            info = mapping_info.get(public_id)
            sc = info[1] if info else 0
            dc = info[2] if info else 0
            total_instances = sc + dc

            if not is_default_system and total_instances > 1:
                for i in range(1, sc + 1):
                    expanded.append({
                        "id": f"{public_id}#{i}",
                        "display_id": f"{getattr(rec, 'display_id', None) or public_id}#{i}",
                        "name": f"{rec.name} (Shared #{i})" if sc > 1 else f"{rec.name} (Shared)",
                        "agent_kind": "shared",
                        "type": rec.type,
                        "skills_content": getattr(rec, "skills_content", None),
                        "skills_summary": getattr(rec, "skills_summary", None),
                        "skills_tags": getattr(rec, "skills_tags", None),
                        "specialization": getattr(rec, "specialization", None),
                        "face": getattr(rec, "face", None),
                        "allowed_tools": getattr(rec, "allowed_tools", None) or [],
                        "model_name": getattr(rec, "model_name", None) or "claude",
                    })
                for j in range(1, dc + 1):
                    idx = sc + j
                    expanded.append({
                        "id": f"{public_id}#{idx}",
                        "display_id": f"{getattr(rec, 'display_id', None) or public_id}#{idx}",
                        "name": f"{rec.name} (Dedicated #{j})" if dc > 1 else f"{rec.name} (Dedicated)",
                        "agent_kind": "dedicated",
                        "type": rec.type,
                        "skills_content": getattr(rec, "skills_content", None),
                        "skills_summary": getattr(rec, "skills_summary", None),
                        "skills_tags": getattr(rec, "skills_tags", None),
                        "specialization": getattr(rec, "specialization", None),
                        "face": getattr(rec, "face", None),
                        "allowed_tools": getattr(rec, "allowed_tools", None) or [],
                        "model_name": getattr(rec, "model_name", None) or "claude",
                    })
            else:
                agent_kind = "system" if is_default_system else (info[0] if info else "shared")
                expanded.append({
                    "id": public_id,
                    "display_id": getattr(rec, "display_id", None) or public_id,
                    "name": rec.name,
                    "agent_kind": agent_kind,
                    "type": rec.type,
                    "skills_content": getattr(rec, "skills_content", None),
                    "skills_summary": getattr(rec, "skills_summary", None),
                    "skills_tags": getattr(rec, "skills_tags", None),
                    "specialization": getattr(rec, "specialization", None),
                    "face": getattr(rec, "face", None),
                    "allowed_tools": getattr(rec, "allowed_tools", None) or [],
                    "model_name": getattr(rec, "model_name", None) or "claude",
                })
        return expanded
    finally:
        db.close()


def _sanitize_agent_for_user(
    agent: Dict[str, Any],
    global_cred: Optional[models.AgentCredential],
) -> Dict[str, Any]:
    safe_agent = dict(agent)
    safe_agent["git_repo_url"] = global_cred.git_repo_url if global_cred and global_cred.git_repo_url else None
    safe_agent["has_git_token"] = bool(global_cred and global_cred.git_token)
    safe_agent["is_public_repo"] = False
    if "git_token" in safe_agent:
        safe_agent["git_token"] = None
    return safe_agent


async def _sanitize_agent_for_user_with_public_check(
    agent: Dict[str, Any],
    global_cred: Optional[models.AgentCredential],
) -> Dict[str, Any]:
    safe_agent = _sanitize_agent_for_user(agent, global_cred)
    if global_cred and global_cred.git_repo_url:
        repo_url = global_cred.git_repo_url.strip()
        try:
            if "github.com" in repo_url:
                match = re.search(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?$", repo_url)
                if match:
                    owner, repo = match.groups()
                    from app.integrations.vcs import github_service
                    safe_agent["is_public_repo"] = await github_service.is_repo_public(
                        owner, repo, token=getattr(settings, "GITHUB_TOKEN", None)
                    )
            elif "dev.azure.com" in repo_url or "visualstudio.com" in repo_url:
                from app.integrations.vcs import azure_devops_service
                parsed = azure_devops_service.parse_azure_repo_url(repo_url)
                if parsed.get("organization") and parsed.get("project") and parsed.get("repo"):
                    safe_agent["is_public_repo"] = await azure_devops_service.is_repo_public(
                        parsed["organization"],
                        parsed["project"],
                        parsed["repo"],
                        pat=global_cred.git_token if global_cred else None,
                    )
        except Exception:
            safe_agent["is_public_repo"] = False

    return safe_agent


def _log_background_task_result(task: asyncio.Task) -> None:
    try:
        exc = task.exception()
    except asyncio.CancelledError:
        return
    except Exception:
        logger.exception("Failed to inspect background task state")
        return

    if exc:
        logger.error(f"Background task failed with exception: {exc}", exc_info=exc)
