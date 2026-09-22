"""
DSuite BRD Analyzer - Domain Router: Projects Management & Integration
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

import agent_service
from app.integrations.vcs import azure_devops_service, github_service
from app.core.middleware import resolve_project_token
from local_task_preview_service import build_local_task_plan_preview, _normalize_project_dates, _format_date
from app.routers.helpers import (
    _ensure_org_agent_mapping,
    _normalized_text,
    _update_project_tags,
    parse_markdown_techniques,
)


logger = logging.getLogger(__name__)

router = APIRouter(tags=["Projects"])

# --- Extracted Block (Lines 8149-8351) ---
@router.post("/api/projects/ensure")
async def ensure_project_exists(
    request: dict,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """
    Ensure a project exists in the backend database.
    Prevents duplicate project creation by:
    - Returning existing project if token matches
    - Creating new project with provided token if it doesn't exist
    - Generating new token only if none provided
    - CRITICAL: Prevents duplicate project names for the same user
    
    This is called during project initiation to synchronize frontend draft projects with backend.
    """
    project_token = request.get('project_token')
    project_name = request.get('project_name', 'Untitled Project').strip()
    client_id = request.get('client_id')
    client_secret = request.get('client_secret')
    
    # Validate project name
    if not project_name or project_name.lower() == 'untitled project':
        raise HTTPException(
            status_code=400,
            detail="Please provide a valid project name"
        )
    
    # CRITICAL: Check if a project with this name already exists for this organization
    org_name = current_user.organization_name or "Default Organization"
    existing_by_name = db.query(models.GovernanceResponse).filter(
        func.lower(models.GovernanceResponse.organization_name) == org_name.lower(),
        func.lower(models.GovernanceResponse.project_name) == project_name.lower()
    ).first()
    
    if existing_by_name:
        # If project_token matches, return the existing project (user is continuing)
        if project_token and existing_by_name.project_token == project_token:
            logger.info(f"Returning existing project: {project_token} for organization {org_name}")
            # Update credentials if provided
            if not existing_by_name.organization_name:
                existing_by_name.organization_name = org_name
            if client_id:
                existing_by_name.client_id = client_id
            if client_secret:
                existing_by_name.client_secret = client_secret
            
            if 'tags' in request:
                _update_project_tags(db, existing_by_name, request['tags'])
                
            db.commit()
            db.refresh(existing_by_name)
            
            return {
                'project_token': existing_by_name.project_token,
                'project_name': existing_by_name.project_name,
                'client_id': existing_by_name.client_id,
                'client_secret': existing_by_name.client_secret,
                'owner_id': existing_by_name.owner_id,
                'exists': True,
                'tags': [{'id': t.id, 'name': t.name} for t in existing_by_name.tags]
            }
        else:
            # Different token or no token - this is a duplicate name attempt
            raise HTTPException(
                status_code=409,
                detail=f"A project named '{project_name}' already exists in your organization. Please choose a different name or continue with the existing project."
            )
    
    if project_token:
        # Check if project exists for this token and organization
        existing = db.query(models.GovernanceResponse).filter(
            models.GovernanceResponse.project_token == project_token,
            func.lower(models.GovernanceResponse.organization_name) == org_name.lower()
        ).first()
        
        if existing:
            # Project exists - return it (update credentials if provided)
            if client_id:
                existing.client_id = client_id
            if client_secret:
                existing.client_secret = client_secret
            
            if 'tags' in request:
                _update_project_tags(db, existing, request['tags'])
                
            db.commit()
            db.refresh(existing)
            
            return {
                'project_token': existing.project_token,
                'project_name': existing.project_name,
                'owner_id': existing.owner_id,
                'client_id': existing.client_id,
                'client_secret': existing.client_secret,
                'exists': True,
                'tags': [{'id': t.id, 'name': t.name} for t in existing.tags]
            }
    
    # Project doesn't exist - create it with provided or new token
    new_token = project_token or str(uuid.uuid4())
    
    # Verify token is unique
    while db.query(models.GovernanceResponse).filter(
        models.GovernanceResponse.project_token == new_token
    ).first():
        new_token = str(uuid.uuid4())
    
    # Create placeholder governance response (will be updated when user completes governance)
    new_project = models.GovernanceResponse(
        owner_id=current_user.id,
        project_token=new_token,
        organization_name=org_name,
        project_name=project_name,
        answers={},
        weighted_score=0,
        classification='PENDING',
        recommendation='Pending governance assessment',
        client_id=client_id,
        client_secret=client_secret,
    )
    
    db.add(new_project)
    db.commit()
    db.refresh(new_project)
    
    if 'tags' in request:
        _update_project_tags(db, new_project, request['tags'])
        db.commit()
        db.refresh(new_project)
    
    logger.info(f"Created new project: {new_token} with name '{project_name}' for organization {org_name}")
    
    return {
        'project_token': new_project.project_token,
        'project_name': new_project.project_name,
        'client_id': new_project.client_id,
        'client_secret': new_project.client_secret,
        'owner_id': new_project.owner_id,
        'exists': False,
        'tags': [{'id': t.id, 'name': t.name} for t in new_project.tags]
    }


@router.post("/api/projects/{project_token}/git-config", response_model=schemas.ProjectGitConfigResponse)
async def save_project_git_config(
    project_token: str,
    request: schemas.ProjectGitConfigRequest,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    project_token = _normalize_project_token(project_token)
    db_response = db.query(models.GovernanceResponse).filter(
        models.GovernanceResponse.project_token == project_token
    ).first()
    if not db_response:
        raise HTTPException(status_code=404, detail="Project not found")
        
    if request.source_repo_url is not None:
        db_response.source_repo_url = request.source_repo_url
    if request.source_repo_token is not None:
        db_response.source_repo_token = request.source_repo_token
    if request.dest_repo_url is not None:
        db_response.dest_repo_url = request.dest_repo_url
    if request.dest_repo_token is not None:
        db_response.dest_repo_token = request.dest_repo_token
        
    db.commit()
    db.refresh(db_response)
    return schemas.ProjectGitConfigResponse(
        source_repo_url=db_response.source_repo_url,
        source_repo_token=db_response.source_repo_token,
        dest_repo_url=db_response.dest_repo_url,
        dest_repo_token=db_response.dest_repo_token,
    )


@router.get("/api/projects/{project_token}/git-config", response_model=schemas.ProjectGitConfigResponse)
async def get_project_git_config(
    project_token: str,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    project_token = _normalize_project_token(project_token)
    row = db.query(
        models.GovernanceResponse.source_repo_url,
        models.GovernanceResponse.source_repo_token,
        models.GovernanceResponse.dest_repo_url,
        models.GovernanceResponse.dest_repo_token,
    ).filter(
        models.GovernanceResponse.project_token == project_token
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")
        
    return schemas.ProjectGitConfigResponse(
        source_repo_url=row.source_repo_url,
        source_repo_token=row.source_repo_token,
        dest_repo_url=row.dest_repo_url,
        dest_repo_token=row.dest_repo_token,
    )



# --- Extracted Block (Lines 8810-8846) ---
@router.post("/api/nxdune/sync-now")
async def manual_nxdune_sync(
    project_token: Optional[str] = None,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """
    Manually trigger a one-time sync of pending logs to NXDune.
    Executes without any automatic background retry loop.
    """
    from local_sync_service import trigger_nxdune_sync_now
    result = await trigger_nxdune_sync_now(db, project_token=project_token)
    return result

@router.get("/api/nxdune/sync-status")
async def get_nxdune_sync_status(
    project_token: Optional[str] = None,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """Get status counts of NXDune sync logs."""
    query = db.query(models.NXDuneSyncLog)
    if project_token:
        query = query.filter(models.NXDuneSyncLog.project_token == project_token)
        
    total = query.count()
    pending = query.filter(models.NXDuneSyncLog.success == False, models.NXDuneSyncLog.permanently_failed == False).count()
    succeeded = query.filter(models.NXDuneSyncLog.success == True).count()
    failed = query.filter(models.NXDuneSyncLog.permanently_failed == True).count()
    
    return {
        "total": total,
        "pending": pending,
        "succeeded": succeeded,
        "failed": failed
    }


# --- Extracted Block (Lines 9549-9824) ---
@router.get("/api/projects/{project_token}/elicitation-techniques")
async def get_elicitation_techniques(
    project_token: str,
    only_skills: bool = False,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get elicitation techniques for a project.
    
    If the project has skills/methods markdown files uploaded, parses them directly.
    If only_skills is True and no files exist, returns empty response.
    Otherwise, dynamically asks the AI to generate 5 SDLC-aligned elicitation techniques.
    """
    import re
    import json
    import llm_gateway
    # Bind context variables explicitly
    llm_gateway.current_user_id_var.set(current_user.id)
    llm_gateway.current_project_token_var.set(project_token)
    llm_gateway.current_user_org_var.set(getattr(current_user, "organization_name", None))

    from config import settings

    # 1. Fetch project/governance
    query = db.query(models.GovernanceResponse).filter(
        models.GovernanceResponse.owner_id == current_user.id
    )
    governance = query.filter(models.GovernanceResponse.project_token == project_token).first()
    
    # 2. Direct fallback/parsing if skills files exist
    if governance and governance.skills_md_files:
        try:
            uploaded_techniques = []
            for file_obj in governance.skills_md_files:
                file_content = file_obj.get("content", "")
                if file_content:
                    parsed = parse_markdown_techniques(file_content)
                    uploaded_techniques.extend(parsed)
            if uploaded_techniques:
                return {
                    "source": "uploaded",
                    "techniques": uploaded_techniques[:5]
                }
        except Exception as parse_err:
            logger.error(f"Failed to parse uploaded skills files: {parse_err}")

    # If only_skills is True and we got no uploaded skills, return empty response immediately
    if only_skills:
        return {
            "source": "none",
            "techniques": []
        }

    # 3. Check if skills/methods files are uploaded (for prompt context fallback)
    skills_content = ""
    if governance and governance.skills_md_files:
        skills_contents = [f.get("content", "") for f in governance.skills_md_files if f.get("content")]
        if skills_contents:
            skills_content = "\n\n".join(skills_contents)
            
    # Try to find the latest document/BRD content for this project
    brd_content = ""
    token_pattern = f'%"project_token": "{project_token}"%'
    doc = db.query(models.Document).filter(
        models.Document.owner_id == current_user.id,
        models.Document.analysis_result.like(token_pattern)
    ).order_by(models.Document.upload_date.desc()).first()
    
    if doc and doc.full_content:
        brd_content = doc.full_content

    # Extract the finalized AI Analysis/Action Plan report from the document
    analysis_report = ""
    if doc and doc.analysis_result:
        try:
            analysis_data = json.loads(doc.analysis_result)
            if isinstance(analysis_data, dict):
                analysis_report = analysis_data.get("analysis", "")
        except Exception as json_err:
            logger.error(f"Failed to parse analysis_result JSON in techniques generator: {json_err}")

    # 4. Build AI prompt based on whether skills are uploaded or not
    system_content = "You are an expert BRD analyst and SDLC process architect."
    
    if skills_content:
        logger.info(f"Skills files found for project {project_token}. Instructing AI to generate techniques based on uploaded methodology context...")
        user_content = f"""The user has uploaded a custom methodology / elicitation skills guide file.
Based on the contents of the uploaded files provided below, please generate exactly 5 elicitation techniques.
For each technique, you must provide:
1. Technique Name
2. Short Description / Instructions (how to use it based on the uploaded file guidelines)
3. Purpose / Benefit

You MUST return the output in a JSON list of objects containing fields 'name', 'description', and 'purpose'. Do not output any markdown fences, thoughts, or explanations. Only return a raw valid JSON array.

Uploaded Methodology Content:
{skills_content[:20000]}"""
    else:
        logger.info(f"No skills files found for project {project_token}. Dynamically generating SDLC-aligned techniques using AI...")
        context_to_use = analysis_report if analysis_report else brd_content
        context_label = "AI Analysis/Action Plan Report" if analysis_report else "BRD Document Content"
        
        if context_to_use:
            user_content = f"""Based on the following {context_label}, generate exactly 5 tailored requirements elicitation techniques that can improve the BRD quality, aligned with the SDLC lifecycle.
Each technique MUST have:
1. Technique Name
2. Short Description
3. Purpose/Benefit

You MUST return the output in a JSON list of objects containing fields 'name', 'description', and 'purpose'. Do not output any markdown fences, thoughts, or explanations. Only return a raw valid JSON array.

{context_label}:
{context_to_use[:15000]}"""
        else:
            user_content = """Generate exactly 5 high-quality, highly practical requirements elicitation techniques that can improve BRD quality, aligned with the SDLC lifecycle.
Each technique MUST have:
1. Technique Name
2. Short Description
3. Purpose/Benefit

The techniques should cover:
- Enhance requirement discovery
- Improve edge-case analysis
- Strengthen business logic
- Encourage stakeholder thinking
- Improve BRD completeness

You MUST return the output in a JSON list of objects containing fields 'name', 'description', and 'purpose'. Do not output any markdown fences, thoughts, or explanations. Only return a raw valid JSON array."""

    try:
        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_content}
        ]
        
        # Call LLM
        ai_response = await llm_gateway.call_llm_and_extract(
            messages=messages,
            api_url=settings.ai_api_url,
            api_key=settings.ai_api_key,
            model=settings.ai_model,
            timeout=120.0
        )
        
        # Extract JSON list from response
        cleaned_response = ai_response.strip()
        if cleaned_response.startswith("```"):
            cleaned_response = re.sub(r"^```(?:json)?\s*", "", cleaned_response)
            cleaned_response = re.sub(r"\s*```$", "", cleaned_response)
            
        techniques = json.loads(cleaned_response.strip())
        if isinstance(techniques, list) and len(techniques) > 0:
            formatted_techniques = []
            for t in techniques[:5]:
                name = t.get("name") or t.get("technique_name") or "Elicitation Technique"
                desc = t.get("description") or t.get("short_description") or ""
                purpose = t.get("purpose") or t.get("purpose_benefit") or t.get("benefit") or ""
                
                full_desc = desc
                if purpose and purpose not in desc:
                    full_desc += f"\n\nPurpose/Benefit: {purpose}"
                    
                formatted_techniques.append({
                    "name": name,
                    "description": full_desc,
                    "purpose": purpose
                })
            
            return {
                "source": "uploaded" if skills_content else "ai_generated",
                "techniques": formatted_techniques
            }
    except Exception as e:
        logger.error(f"Failed to dynamically generate elicitation techniques: {e}", exc_info=True)
        
    # Ultimate fail-safe parsing fallback: if skills files exist, parse them directly
    if governance and governance.skills_md_files:
        try:
            uploaded_techniques = []
            for file_obj in governance.skills_md_files:
                file_content = file_obj.get("content", "")
                parsed = parse_markdown_techniques(file_content)
                uploaded_techniques.extend(parsed)
            if uploaded_techniques:
                return {
                    "source": "uploaded",
                    "techniques": uploaded_techniques[:5]
                }
        except:
            pass

    # Static fallback of 5 SDLC-aligned techniques if LLM call and parsing fails
    fallback_techniques = [
        {
            "name": "Brainstorming & Feature Discovery",
            "description": "Engage stakeholders to generate a wide list of creative features and user needs.\n\nPurpose/Benefit: Unlocks divergent ideas, discovers hidden user pain points, and outlines the broad scope of requirements.",
            "purpose": "Unlocks divergent ideas, discovers hidden user pain points, and outlines the broad scope of requirements."
        },
        {
            "name": "What-If Analysis & Edge-Case Modeling",
            "description": "Systematic exploration of atypical conditions and error paths by asking 'What if...' for key user actions.\n\nPurpose/Benefit: Increases business logic resilience, prevents runtime crashes, and designs robust error-handling states.",
            "purpose": "Increases business logic resilience, prevents runtime crashes, and designs robust error-handling states."
        },
        {
            "name": "Functional Decomposition",
            "description": "Break down large, high-level business goals into fine-grained functional tasks, modules, and API needs.\n\nPurpose/Benefit: Improves architectural precision, provides clear structures for developers, and ensures no business requirement is missed.",
            "purpose": "Improves architectural precision, provides clear structures for developers, and ensures no business requirement is missed."
        },
        {
            "name": "Interface & Wireframe Prototyping",
            "description": "Define explicit screen UI states, input form fields, data validation constraints, and user navigation routes.\n\nPurpose/Benefit: Ensures stakeholder alignment on user experience, defines UI logic early, and sets expectations for frontend developers.",
            "purpose": "Ensures stakeholder alignment on user experience, defines UI logic early, and sets expectations for frontend developers."
        },
        {
            "name": "Data Flow & State Transition Mapping",
            "description": "Trace how core database records and status fields change during lifecycle milestones (e.g. Draft -> Under Review -> Approved).\n\nPurpose/Benefit: Eliminates logical deadlocks in workflow automation, models data integrity, and specifies clean API state management.",
            "purpose": "Eliminates logical deadlocks in workflow automation, models data integrity, and specifies clean API state management."
        }
    ]
    return {
        "source": "static_fallback",
        "techniques": fallback_techniques
    }



def _extract_document_analysis_context(doc: models.Document) -> Optional[Dict[str, Any]]:
    """Parse stored analysis JSON and extract project-linking metadata."""
    if not doc.analysis_result:
        return None

    try:
        import json
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
    """Return True when a document belongs to the given governance project."""
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



# --- Extracted Block (Lines 11399-12184) ---
@router.get("/api/projects/{project_token}/local-task-status")
async def get_local_task_status(
    project_token: str,
    current_user: models.User = Depends(auth.get_current_user),
):
    """
    Local-first task status endpoint — reads from AgentTaskOwnership DB only.

    Returns real-time task progress without any NXDune API calls.
    This is the recommended endpoint for the frontend task panel as it's:
    - Always up-to-date (updated immediately when agents claim/complete tasks)
    - Always available (no external API dependency)
    - Zero-latency (direct DB read)

    Response shape:
    {
        "project_token": "...",
        "bootstrap_completed": bool,
        "bootstrap_branch": str | null,
        "task_execution_order": { waves, order, summary } | null,
        "tasks": [
            {
                "task_id": "...",
                "task_title": "...",
                "agent_id": "...",
                "status": "claimed|in_progress|done|failed",
                "claimed_at": ISO | null,
                "started_at": ISO | null,
                "completed_at": ISO | null,
                "files_written_count": int,
                "files_written": [...],
                "branch_name": "...",
                "nxdune_synced": bool,
                "error_message": "..." | null,
                "task_lane": "...",
            },
            ...
        ],
        "summary": {
            "total": int,
            "done": int,
            "in_progress": int,
            "claimed": int,
            "failed": int,
        }
    }
    """
    from local_state_manager import get_local_task_statuses, get_canonical_state
    from bootstrap_persistence import is_bootstrap_pushed, get_bootstrap_branch

    task_statuses = get_local_task_statuses(project_token)

    # Summary counts
    summary = {
        "total": len(task_statuses),
        "done": sum(1 for t in task_statuses if t["status"] == "done"),
        "in_progress": sum(1 for t in task_statuses if t["status"] == "in_progress"),
        "claimed": sum(1 for t in task_statuses if t["status"] == "claimed"),
        "failed": sum(1 for t in task_statuses if t["status"] == "failed"),
    }

    # Bootstrap status
    bootstrap_completed = is_bootstrap_pushed(project_token)
    bootstrap_branch = get_bootstrap_branch(project_token) if bootstrap_completed else None

    # Task execution order (from canonical state if available)
    task_execution_order = None
    try:
        cs = get_canonical_state(project_token) or {}
        tech_stack = cs.get("tech_stack") or {}
        task_execution_order = tech_stack.get("task_execution_order")
    except Exception:
        pass

    return {
        "project_token": project_token,
        "bootstrap_completed": bootstrap_completed,
        "bootstrap_branch": bootstrap_branch,
        "task_execution_order": task_execution_order,
        "tasks": task_statuses,
        "summary": summary,
    }


# ═══════════════════════════════ AI AGENTS ═══════════════════════════════════

def _normalize_project_token(project_token: Optional[str]) -> Optional[str]:
    if not project_token:
        return None
    token = project_token.strip()
    return token or None


def _resolve_project_token(db: Session, x_task_token: Optional[str], x_project_token: Optional[str] = None) -> Optional[str]:
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
    parts = token.split('.')
    if len(parts) != 3:
        return token
        
    # Check if it looks like a JWT
    try:
        import base64
        import json
        payload_b64 = parts[1]
        payload_b64 += '=' * (-len(payload_b64) % 4)
        payload_json = base64.urlsafe_b64decode(payload_b64).decode('utf-8')
        payload_data = json.loads(payload_json)
        client_id = payload_data.get("client_id")
        if client_id:
            # Find project by client_id in GovernanceResponse
            proj = db.query(models.GovernanceResponse).filter(
                models.GovernanceResponse.client_id == client_id
            ).first()
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


def _runtime_agent_records(records: List[models.Agent], project_token: Optional[str]) -> List[Dict[str, Any]]:
    project_token = _normalize_project_token(project_token)
    from database import SessionLocal
    db = SessionLocal()
    try:
        # Query mappings to find counts
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
            kind = row[1] or 'shared'
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
                # Expand shared instances
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
                    })
                # Expand dedicated instances
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
                    })
            else:
                agent_kind = "shared" if sc > 0 else ("dedicated" if dc > 0 else (info[0] if info else "shared"))
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
                })
        return expanded
    finally:
        db.close()


def _ensure_agent_skills_columns() -> None:
    with engine.connect() as conn:
        result = conn.execute(text("PRAGMA table_info(agents)"))
        columns = [row[1] for row in result.fetchall()]
        if "skills_content" not in columns:
            conn.execute(text("ALTER TABLE agents ADD COLUMN skills_content TEXT"))
            conn.commit()
        if "skills_summary" not in columns:
            conn.execute(text("ALTER TABLE agents ADD COLUMN skills_summary VARCHAR"))
            conn.commit()
        if "skills_tags" not in columns:
            conn.execute(text("ALTER TABLE agents ADD COLUMN skills_tags JSON"))
            conn.commit()
        if "specialization" not in columns:
            conn.execute(text("ALTER TABLE agents ADD COLUMN specialization VARCHAR"))
            conn.commit()
        if "face" not in columns:
            conn.execute(text("ALTER TABLE agents ADD COLUMN face TEXT"))
            conn.commit()
        if "display_id" not in columns:
            conn.execute(text("ALTER TABLE agents ADD COLUMN display_id VARCHAR"))
            conn.commit()


def _ensure_agent_project_columns() -> None:
    with engine.connect() as conn:
        result = conn.execute(text("PRAGMA table_info(agents)"))
        columns = [row[1] for row in result.fetchall()]
        if "project_token" not in columns:
            conn.execute(text("ALTER TABLE agents ADD COLUMN project_token VARCHAR"))
            conn.commit()

        result = conn.execute(text("PRAGMA table_info(agent_credentials)"))
        columns = [row[1] for row in result.fetchall()]
        if "project_token" not in columns:
            conn.execute(text("ALTER TABLE agent_credentials ADD COLUMN project_token VARCHAR"))
            conn.commit()


def _ensure_org_agent_mapping_kind_column() -> None:
    with engine.connect() as conn:
        result = conn.execute(text("PRAGMA table_info(organization_agent_mappings)"))
        columns = [row[1] for row in result.fetchall()]
        if "agent_kind" not in columns:
            conn.execute(text("ALTER TABLE organization_agent_mappings ADD COLUMN agent_kind VARCHAR"))
            conn.commit()


def _ensure_user_organization_columns() -> None:
    with engine.connect() as conn:
        result = conn.execute(text("PRAGMA table_info(users)"))
        columns = [row[1] for row in result.fetchall()]

        if "first_name" not in columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN first_name VARCHAR"))
            conn.commit()

        if "last_name" not in columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN last_name VARCHAR"))
            conn.commit()

        if "organization_name" not in columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN organization_name VARCHAR"))
            conn.commit()

        if "is_org_admin" not in columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN is_org_admin BOOLEAN DEFAULT 0"))
            conn.commit()

        if "azure_devops_token" not in columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN azure_devops_token VARCHAR"))
            conn.commit()

        if "azure_devops_username" not in columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN azure_devops_username VARCHAR"))
            conn.commit()

def _ensure_governance_organization_columns() -> None:
    with engine.connect() as conn:
        result = conn.execute(text("PRAGMA table_info(governance_responses)"))
        columns = [row[1] for row in result.fetchall()]
        if "organization_name" not in columns:
            conn.execute(text("ALTER TABLE governance_responses ADD COLUMN organization_name VARCHAR"))
            conn.commit()

def _ensure_default_oauth_clients(db: Session) -> None:
    defaults = [
        {
            "name": "Nxdune",
            "client_id": settings.oauth_nxdune_client_id,
            "client_secret": settings.oauth_nxdune_client_secret,
            "redirect_uri": settings.oauth_nxdune_redirect_uri,
            "login_url": settings.oauth_nxdune_login_url,
        },
        {
            "name": "Kaktox",
            "client_id": settings.oauth_kaktox_client_id,
            "client_secret": settings.oauth_kaktox_client_secret,
            "redirect_uri": settings.oauth_kaktox_redirect_uri,
            "login_url": settings.oauth_kaktox_login_url,
        },
        {
            "name": "CloudSpx",
            "client_id": settings.oauth_cloudspx_client_id,
            "client_secret": settings.oauth_cloudspx_client_secret,
            "redirect_uri": settings.oauth_cloudspx_redirect_uri,
            "login_url": settings.oauth_cloudspx_login_url,
        },
    ]

    for plugin in defaults:
        client_id = _normalized_text(plugin.get("client_id"))
        redirect_uri = _normalized_text(plugin.get("redirect_uri"))
        client_secret = _normalized_text(plugin.get("client_secret"))
        if not client_id or not redirect_uri or not client_secret:
            continue

        existing = db.query(models.OAuthClient).filter(
            func.lower(models.OAuthClient.client_id) == client_id.lower()
        ).first()
        if existing:
            # Keep DB in sync with environment-driven defaults.
            existing.name = plugin["name"]
            existing.client_secret = client_secret
            existing.redirect_uri = redirect_uri
            existing.login_url = _normalized_text(plugin.get("login_url")) or None
            if not existing.is_active:
                existing.is_active = True
            db.add(existing)
            continue

        row = models.OAuthClient(
            name=plugin["name"],
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            login_url=_normalized_text(plugin.get("login_url")) or None,
            is_active=True,
        )
        db.add(row)

    db.commit()


def _ensure_default_governance_questions(db: Session) -> None:
    """Ensure basic governance questions exist in database."""
    count = db.query(models.GovernanceQuestion).count()
    if count > 0:
        return

    print("Seeding default governance questions...")
    try:
        from governance_scoring import GOVERNANCE_QUESTIONS
        for q_data in GOVERNANCE_QUESTIONS:
            # We use the specific ID if provided to keep scoring in sync
            db_question = models.GovernanceQuestion(
                id=q_data["id"],
                dimension=q_data["dimension"],
                question_text=q_data["question"],
                order=q_data["id"],
                is_active=True
            )
            db.add(db_question)
            db.flush()

            for opt_data in q_data["options"]:
                db_option = models.GovernanceQuestionOption(
                    question_id=db_question.id,
                    label=opt_data["label"],
                    score=opt_data["score"]
                )
                db.add(db_option)
        db.commit()
        print("[OK] Governance questions seeded")
    except Exception as e:
        db.rollback()
        print(f"[ERROR] Failed to seed governance questions: {e}")

# Seed sample tasks on startup
def _startup_init() -> None:
    # Ensure Docker image is ready before anything else
    print("Initializing Docker runtime environment...")
    try:
        img_res = agent_service._ensure_agent_runtime_image()
        if img_res.get("success"):
            if img_res.get("built"):
                print("[OK] Docker image built successfully.")
            else:
                print("[OK] Docker image verified (already exists).")
        else:
            print(f"[ERROR] Docker initialization failed: {img_res.get('error')}")
    except Exception as exc:
        print(f"[WARNING] Docker initialization check failed or timed out: {exc}")
        print("The server will continue to start, but agent execution tasks will require Docker to be running.")

    agent_service.seed_sample_tasks()
    db = SessionLocal()
    try:
        _ensure_agent_project_columns()
        _ensure_agent_skills_columns()
        _ensure_org_agent_mapping_kind_column()
        _ensure_user_organization_columns()
        _ensure_governance_organization_columns()
        _ensure_default_oauth_clients(db)
        _ensure_default_agents(db)
        _ensure_default_governance_questions(db)
        agents = db.query(models.Agent).filter(models.Agent.project_token.is_(None)).all()
        agent_service.initialize_agents_from_records(_runtime_agent_records(agents, None))
    finally:
        db.close()


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
    # Scope to org if user belongs to one, otherwise only current user
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


def _legacy_default_dev_agent_filter(column):
    return or_(
        column.in_(("agent_01", "agent_02")),
        column.like("%::agent_01"),
        column.like("%::agent_02"),
    )


def _cleanup_legacy_default_dev_agents(db: Session) -> None:
    """
    Remove the old built-in dev agents so only system agents remain default.
    New dev agents must come from org shared/dedicated capacity.
    
    IMPORTANT: Only delete agents that were marked as DEFAULT (is_default=True).
    User-added agents with agent_01/agent_02 IDs should NOT be deleted.
    """
    # First, get the list of agent IDs that are marked as default
    default_agent_ids = {
        row[0] for row in db.query(models.OrganizationAgentMapping.agent_id).filter(
            models.OrganizationAgentMapping.is_default.is_(True),
            _legacy_default_dev_agent_filter(models.OrganizationAgentMapping.agent_id),
        ).all()
    }
    
    # Delete the default mappings
    deleted_mappings = db.query(models.OrganizationAgentMapping).filter(
        models.OrganizationAgentMapping.is_default.is_(True),
        _legacy_default_dev_agent_filter(models.OrganizationAgentMapping.agent_id),
    ).delete(synchronize_session=False)

    # Only delete Agent records that were marked as default (not user-added ones)
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
            )
        )
    db.commit()

def _ensure_default_agents_for_org(
    db: Session,
    organization_name: str,
    project_token: Optional[str] = None,
) -> None:
    """
    Ensure default agents exist in the legacy `agents` table AND are mapped to the org as defaults.
    """
    project_token = _normalize_project_token(project_token)
    _ensure_default_agents(db, project_token)
    org = _normalized_text(organization_name)
    if not org:
        return
    for agent in agent_service.get_default_agents(project_token):
        stored_id = _stored_agent_id(agent["id"], project_token)
        _ensure_org_agent_mapping(db, org, stored_id, project_token, is_default=True)


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
    """
    Return project-wide global Git credential.
    Backfills from legacy per-agent credentials so existing users are not disrupted.
    """
    cred = _get_project_global_credential(db, user, project_token)
    if cred:
        return cred

    legacy = sorted(
        _list_legacy_agent_credentials(db, user.id, project_token),
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


def _sanitize_agent_for_user(
    agent: Dict[str, Any],
    global_cred: Optional[models.AgentCredential],
) -> Dict[str, Any]:
    safe_agent = dict(agent)
    safe_agent["git_repo_url"] = global_cred.git_repo_url if global_cred and global_cred.git_repo_url else None
    safe_agent["has_git_token"] = bool(global_cred and global_cred.git_token)
    # Default to False; will be populated by async version
    safe_agent["is_public_repo"] = False
    if "git_token" in safe_agent:
        safe_agent["git_token"] = None
    return safe_agent


async def _sanitize_agent_for_user_with_public_check(
    agent: Dict[str, Any],
    global_cred: Optional[models.AgentCredential],
) -> Dict[str, Any]:
    """Enhanced version that checks if the repository is public."""
    safe_agent = _sanitize_agent_for_user(agent, global_cred)
    
    # Only check if we have a repo URL
    if global_cred and global_cred.git_repo_url:
        repo_url = global_cred.git_repo_url.strip()
        try:
            # Check if it's a GitHub repo
            if "github.com" in repo_url:
                # Extract owner/repo from URL
                match = re.search(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?$", repo_url)
                if match:
                    owner, repo = match.groups()
                    safe_agent["is_public_repo"] = await github_service.is_repo_public(owner, repo, token=settings.GITHUB_TOKEN)
            # Check if it's Azure DevOps repo
            elif "dev.azure.com" in repo_url or "visualstudio.com" in repo_url:
                parsed = azure_devops_service.parse_azure_repo_url(repo_url)
                if parsed.get("organization") and parsed.get("project") and parsed.get("repo"):
                    safe_agent["is_public_repo"] = await azure_devops_service.is_repo_public(
                        parsed["organization"],
                        parsed["project"],
                        parsed["repo"],
                        pat=global_cred.git_token if global_cred else None
                    )
        except Exception:
            # If check fails, default to False (assume private for safety)
            safe_agent["is_public_repo"] = False
    
    return safe_agent


def _log_background_task_result(task: asyncio.Task) -> None:
    """Consume and log exceptions from fire-and-forget tasks."""
    try:
        exc = task.exception()
    except asyncio.CancelledError:
        return
    except Exception:
        logger.exception("Failed to inspect background task state")
        return

    if exc:
        logger.exception("Background task failed", exc_info=exc)


class CreateTaskRequest(BaseModel):
    title: str
    description: str
    priority: str = "medium"



