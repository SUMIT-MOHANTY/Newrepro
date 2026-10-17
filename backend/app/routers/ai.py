"""
DSuite BRD Analyzer - Domain Router: AI & BRD Analysis & Vibecoding
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
import time as _time
import json as json_stdlib
import analysis_job_manager
from app.services.ai import ai_service
import ai_service_chunked
from app.integrations.llm import llm_gateway
from app.services.ai import rag_service
from app.routers.helpers import (
    ALL_SKIPPED_ANALYZE_BLOCK_MESSAGE,
    _all_answers_skipped_from_governance_context,
    _normalized_text,
)
from app.integrations.llm.llm_gateway import (
    current_user_id_var, current_project_token_var, current_project_name_var,
    current_user_org_var, current_purpose_var
)


logger = logging.getLogger(__name__)

router = APIRouter(tags=["AI & Analysis"])

# --- Extracted Block (Lines 740-765) ---
# --- Pydantic Models for AI ---
class AnalyzeRequest(BaseModel):
    document_content: str
    api_url: Optional[str] = None
    api_key: Optional[str] = None
    model: Optional[str] = None
    stream: bool = False
    user_feedback: Optional[str] = None
    image_paths: Optional[List[str]] = None
    governance_context: Optional[Dict[str, Any]] = None
    # Targeted update fields — when present, triggers surgical update instead of full regen
    previous_analysis: Optional[Dict[str, Any]] = None
    update_type: Optional[str] = None  # feedback | revision | qa
    # Optional hint: if a repo is connected, helps AI classify brownfield correctly
    repo_url: Optional[str] = None

class AIConfigUpdate(BaseModel):
    api_url: Optional[str] = None
    api_key: Optional[str] = None
    model: Optional[str] = None


class URLIngestRequest(BaseModel):
    url: str = Field(..., description="Public website URL to fetch")



# --- Extracted Block (Lines 931-1173) ---
# --- AI Analysis Endpoints ---
@router.get("/ai/config")
async def get_ai_config(
    current_user: models.User = Depends(auth.get_current_user),
):
    """Get current AI configuration."""
    return await ai_service.get_ai_config()

@router.post("/ai/analyze")
async def analyze_document_with_ai(
    analyze_req: AnalyzeRequest,
    request: Request,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """
    Analyze document content using AI with job-based polling support.
    
    Returns immediately with a job_id that can be used to poll for results.
    
    You can optionally override the default AI settings per request:
    - api_url: Custom OpenAI-compatible API URL
    - api_key: API key for the service
    - model: Model name to use
    - stream: Set to true for streaming response (Server-Sent Events) - bypasses job system
    
    Uses chunked multi-stage analysis by default (configurable via USE_CHUNKED_ANALYSIS env var)
    to reduce payload size and improve reliability.
    """
    if _all_answers_skipped_from_governance_context(analyze_req.governance_context):
        raise HTTPException(status_code=403, detail=ALL_SKIPPED_ANALYZE_BLOCK_MESSAGE)

    # Automatically resolve project token and inject the actual repository structure context
    # if it's connected and not already in the document content
    project_token = request.headers.get("x-task-token") or request.headers.get("X-Task-Token")
    if not project_token:
        project_token = request.query_params.get("project_token")
    if not project_token:
        referer = request.headers.get("referer") or ""
        if "project_token=" in referer:
            try:
                import urllib.parse
                parsed = urllib.parse.urlparse(referer)
                queries = urllib.parse.parse_qs(parsed.query)
                token_list = queries.get("project_token")
                if token_list:
                    project_token = token_list[0]
            except Exception:
                pass

    if project_token and "--- REPOSITORY CONTEXT ---" not in (analyze_req.document_content or ""):
        gov = db.query(models.GovernanceResponse).filter(
            models.GovernanceResponse.project_token == project_token
        ).first()
        
        repo_url = None
        repo_token = None
        branch = None
        
        if gov:
            repo_url = gov.source_repo_url or gov.dest_repo_url
            repo_token = gov.source_repo_token or gov.dest_repo_token
            branch = getattr(gov, "dest_repo_branch", None) or getattr(gov, "source_repo_branch", None) or "main"
                
        if not repo_url:
            cred_query = db.query(models.AgentCredential).filter(
                models.AgentCredential.project_token == project_token
            )
            org_name = _normalized_text(getattr(current_user, "organization_name", None))
            if org_name:
                org_ids = db.query(models.User.id).filter(
                    func.lower(models.User.organization_name) == org_name.lower()
                ).scalar_subquery()
                cred_query = cred_query.filter(models.AgentCredential.owner_id.in_(org_ids))
            else:
                cred_query = cred_query.filter(models.AgentCredential.owner_id == current_user.id)
            cred = cred_query.first()
            if cred:
                repo_url = cred.git_repo_url
                repo_token = cred.git_token
                
        if repo_url:
            try:
                from task_generation_service import _get_real_repository_structure
                logger.info(f"[{project_token}] Fetching repository structure for document analysis from {repo_url}...")
                real_structure = _get_real_repository_structure(repo_url, repo_token, branch)
                if real_structure:
                    analyze_req.document_content = f"{analyze_req.document_content or ''}\n\n--- REPOSITORY CONTEXT ---\n{real_structure}"
                    logger.info(f"[{project_token}] Successfully injected repository structure into document content")
            except Exception as e:
                logger.warning(f"Failed to scan repo structure for document analysis: {e}")

    # Bind context variables explicitly for TokenOps tracking across streaming and background paths
    current_user_id_var.set(current_user.id)
    if project_token:
        current_project_token_var.set(project_token)
    current_user_org_var.set(getattr(current_user, "organization_name", None))

    # If streaming is requested, use the old behavior (no job system)
    if analyze_req.stream:
        logger.info("Using streaming mode - bypassing job system")
        if settings.use_chunked_analysis:
            result = await ai_service_chunked.analyze_document(
                document_content=analyze_req.document_content,
                api_url=analyze_req.api_url,
                api_key=analyze_req.api_key,
                model=analyze_req.model,
                stream=analyze_req.stream,
                user_feedback=analyze_req.user_feedback,
                image_paths=analyze_req.image_paths,
                governance_context=analyze_req.governance_context,
            )
        else:
            result = await ai_service.analyze_document(
                document_content=analyze_req.document_content,
                api_url=analyze_req.api_url,
                api_key=analyze_req.api_key,
                model=analyze_req.model,
                stream=analyze_req.stream,
                user_feedback=analyze_req.user_feedback,
                image_paths=analyze_req.image_paths,
                governance_context=analyze_req.governance_context,
            )
        
        if isinstance(result, dict) and result.get("status") == "error":
            raise HTTPException(status_code=400, detail=result.get("error"))
            
        return StreamingResponse(result, media_type="text/event-stream")

    # Create a job for non-streaming analysis
    job_id = f"analysis_{current_user.id}_{int(_time.time() * 1000)}_{secrets.token_hex(8)}"
    job_manager = analysis_job_manager.get_job_manager()
    job = job_manager.create_job(job_id, current_user.id)
    
    # Start analysis in background
    async def run_analysis():
        # Bind context variables explicitly inside the async task context
        current_user_id_var.set(current_user.id)
        current_project_token_var.set(project_token)
        current_user_org_var.set(getattr(current_user, "organization_name", None))
        try:
            job.set_processing()
            job.update_progress(10, "Starting AI analysis...")

            # --- TARGETED UPDATE PATH ---
            # If a previous_analysis is supplied, perform a surgical diff-based update
            # instead of regenerating everything from scratch.
            if analyze_req.previous_analysis and isinstance(analyze_req.previous_analysis, dict):
                logger.info(f"Job {job_id}: Performing targeted update (type={analyze_req.update_type})")
                job.update_progress(15, "Analyzing what needs to change...")
                change_request = analyze_req.user_feedback or ""
                result = await ai_service_chunked.update_analysis_targeted(
                    previous_analysis=analyze_req.previous_analysis,
                    change_request=change_request,
                    document_content=analyze_req.document_content,
                    api_url=analyze_req.api_url,
                    api_key=analyze_req.api_key,
                    model=analyze_req.model,
                    governance_context=analyze_req.governance_context,
                    job_id=job_id,
                    update_type=analyze_req.update_type or "feedback",
                )
            # --- FULL ANALYSIS PATH ---
            elif settings.use_chunked_analysis:
                logger.info(f"Job {job_id}: Using chunked multi-stage analysis")
                job.update_progress(20, "Stage 1: Extracting requirements...")
                result = await ai_service_chunked.analyze_document(
                    document_content=analyze_req.document_content,
                    api_url=analyze_req.api_url,
                    api_key=analyze_req.api_key,
                    model=analyze_req.model,
                    stream=False,
                    user_feedback=analyze_req.user_feedback,
                    image_paths=analyze_req.image_paths,
                    governance_context=analyze_req.governance_context,
                    job_id=job_id,
                )
            else:
                logger.info(f"Job {job_id}: Using original single-stage analysis")
                job.update_progress(30, "Analyzing document with AI...")
                result = await ai_service.analyze_document(
                    document_content=analyze_req.document_content,
                    api_url=analyze_req.api_url,
                    api_key=analyze_req.api_key,
                    model=analyze_req.model,
                    stream=False,
                    user_feedback=analyze_req.user_feedback,
                    image_paths=analyze_req.image_paths,
                    governance_context=analyze_req.governance_context,
                )
            
            # Handle errors
            if isinstance(result, dict) and result.get("status") == "error":
                job.set_failed(result.get("error", "Analysis failed"))
                logger.error(f"Job {job_id} failed: {result.get('error')}")
                return
            
            # Success
            job.set_completed(result)
            logger.info(f"Job {job_id} completed successfully")
            
        except Exception as e:
            logger.exception(f"Job {job_id} failed with exception")
            job.set_failed(str(e))
    
    # Run analysis in background
    asyncio.create_task(run_analysis())
    
    # Return job ID immediately
    return {
        "job_id": job_id,
        "status": "pending",
        "message": "Analysis started. Use the job_id to poll for results at /ai/analyze/status/{job_id}"
    }


@router.get("/ai/analyze/status/{job_id}")
async def get_analysis_job_status(
    job_id: str,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get the status of an analysis job.
    
    Poll this endpoint to check if the analysis is complete.
    Falls back to completed document in database if in-memory job was cleaned up.
    """
    job_manager = analysis_job_manager.get_job_manager()
    job = job_manager.get_user_job(job_id, current_user.id)
    
    if not job:
        # Fallback to checking the database document directly
        doc = db.query(models.Document).filter(
            models.Document.owner_id == current_user.id,
            models.Document.analysis_result.contains(job_id)
        ).order_by(models.Document.id.desc()).first()
        if doc and doc.analysis_result:
            try:
                parsed = json.loads(doc.analysis_result)
                return {
                    "job_id": job_id,
                    "status": "completed",
                    "progress": 100,
                    "progress_message": "Analysis complete",
                    "result": parsed,
                    "stages": parsed.get("stages", {}),
                    "spec_status": parsed.get("spec_status", {}),
                    "created_at": doc.updated_at.isoformat() if doc.updated_at else None,
                    "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
                }
            except Exception:
                pass

        # Log for debugging
        logger.warning(f"Job {job_id} not found for user {current_user.id}. Available jobs: {list(job_manager._jobs.keys())}")
        raise HTTPException(
            status_code=404, 
            detail="Analysis job not found. It may have expired or been completed and cleaned up. Please start a new analysis."
        )
    
    return job.to_dict()


@router.get("/ai/analyze/status/{job_id}/specs")
async def get_analysis_job_specs(
    job_id: str,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db)
):
    """
    Lightweight endpoint to poll for HLD and LLD background generation progress.
    Avoids re-transmitting the full analysis report payload on every poll.
    Falls back to document database lookup if the in-memory job completed and was cleared.
    """
    job_manager = analysis_job_manager.get_job_manager()
    job = job_manager.get_user_job(job_id, current_user.id)
    
    if not job:
        # Fallback to checking the database document directly
        doc = db.query(models.Document).filter(
            models.Document.owner_id == current_user.id,
            models.Document.analysis_result.contains(job_id)
        ).order_by(models.Document.id.desc()).first()
        if doc and doc.analysis_result:
            try:
                parsed = json.loads(doc.analysis_result)
                hld = parsed.get("hld")
                lld = parsed.get("lld")
                spec_status = parsed.get("spec_status") or {}
                # Since job is None (not running), specs cannot be "generating"
                spec_status["hld"] = "ready" if hld else "pending"
                spec_status["lld"] = "ready" if lld else "pending"
                return {
                    "job_id": job_id,
                    "job_active": False,
                    "spec_status": spec_status,
                    "hld": hld,
                    "lld": lld,
                    "progress": 100 if (hld and lld) else 100,
                    "progress_message": "Specs available from database" if (hld and lld) else "Completed (specs partial)"
                }
            except Exception:
                pass
        raise HTTPException(status_code=404, detail="Analysis job not found")

    is_specs_active = getattr(job, "is_specs_active", False)
    spec_status = dict(getattr(job, "spec_status", {}) or {})
    hld = job.stages.get("hld")
    lld = job.stages.get("lld")

    if hld:
        spec_status["hld"] = "ready"
    elif is_specs_active:
        spec_status["hld"] = spec_status.get("hld", "generating")
    else:
        spec_status["hld"] = "failed" if job.status == "failed" else "pending"

    if lld:
        spec_status["lld"] = "ready"
    elif is_specs_active:
        spec_status["lld"] = spec_status.get("lld", "pending" if spec_status.get("hld") == "generating" else "generating")
    else:
        spec_status["lld"] = "failed" if job.status == "failed" else "pending"

    return {
        "job_id": job.job_id,
        "job_active": is_specs_active,
        "spec_status": spec_status,
        "hld": hld,
        "lld": lld,
        "progress": job.progress,
        "progress_message": job.progress_message
    }


# --- Extracted Block (Lines 7764-7875) ---
@router.post("/chat/messages")
def save_chat_message(
    message: dict,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """Save a chat message to the database"""
    try:
        db_message = models.ChatMessage(
            document_id=message.get("document_id"),
            user_id=current_user.id,
            role=message.get("role"),
            content=message.get("content"),
            is_error=message.get("is_error", False),
            is_qa=message.get("is_qa", False),
            affected_sections=message.get("affected_sections"),
            change_summary=message.get("change_summary"),
        )
        db.add(db_message)
        db.commit()
        db.refresh(db_message)
        
        return {
            "id": db_message.id,
            "document_id": db_message.document_id,
            "role": db_message.role,
            "content": db_message.content,
            "is_error": db_message.is_error,
            "is_qa": db_message.is_qa,
            "affected_sections": db_message.affected_sections,
            "change_summary": db_message.change_summary,
            "timestamp": db_message.created_at.isoformat() if db_message.created_at else None,
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to save chat message: {str(e)}")


@router.get("/chat/messages/{document_id}")
def get_chat_messages(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """Retrieve all chat messages for a specific document"""
    try:
        # Verify the document belongs to the current user
        document = db.query(models.Document).filter(
            models.Document.id == document_id,
            models.Document.owner_id == current_user.id
        ).first()
        
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        
        # Get all messages for this document, ordered by creation time
        messages = db.query(models.ChatMessage).filter(
            models.ChatMessage.document_id == document_id
        ).order_by(models.ChatMessage.created_at.asc()).all()
        
        return [
            {
                "id": msg.id,
                "document_id": msg.document_id,
                "role": msg.role,
                "content": msg.content,
                "is_error": msg.is_error,
                "is_qa": msg.is_qa,
                "affected_sections": msg.affected_sections,
                "change_summary": msg.change_summary,
                "timestamp": msg.created_at.isoformat() if msg.created_at else None,
            }
            for msg in messages
        ]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve chat messages: {str(e)}")


@router.delete("/chat/messages/{document_id}")
def delete_chat_messages(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """Delete all chat messages for a specific document"""
    try:
        # Verify the document belongs to the current user
        document = db.query(models.Document).filter(
            models.Document.id == document_id,
            models.Document.owner_id == current_user.id
        ).first()
        
        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        
        # Delete all messages for this document
        deleted_count = db.query(models.ChatMessage).filter(
            models.ChatMessage.document_id == document_id
        ).delete()
        
        db.commit()
        
        return {"message": f"Deleted {deleted_count} chat messages", "count": deleted_count}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete chat messages: {str(e)}")



# --- Extracted Block (Lines 8848-9120) ---
# ─── VibeCoding Handoff ─────────────────────────────────────────────────────────
HANDOFF_SECRET = os.getenv("HANDOFF_SECRET", "dsuite-vibecoding-handoff-secret-local-dev")

def _create_handoff_token(payload: dict) -> str:
    """
    Create a short handoff token ID instead of embedding all data in the token.
    The full payload is stored in the database and retrieved by VibeCoding.
    """
    # Generate a short, unique token ID
    token_id = secrets.token_urlsafe(32)  # Short, URL-safe token
    
    # Add expiry and issued-at timestamps
    payload["exp"] = int(_time.time()) + 300  # 5 minutes
    payload["iat"] = int(_time.time())
    payload["token_id"] = token_id
    
    # Create HMAC signature for the token ID only
    sig = hmac.new(HANDOFF_SECRET.encode(), token_id.encode(), hashlib.sha256).hexdigest()
    
    # Return short token: tokenId.signature
    return f"{token_id}.{sig}"


class VibeCodingHandoffRequest(BaseModel):
    project_token: str
    project_name: Optional[str] = None
    brd_text: Optional[str] = None
    analysis_data: Optional[dict] = None
    prerequisites: Optional[list] = None
    custom_rules: Optional[str] = None
    process_mode: Optional[str] = "vibe_coding"
    governance_context: Optional[dict] = None


@router.post("/api/vibecoding/handoff-token")
async def create_vibecoding_handoff_token(
    request: VibeCodingHandoffRequest,
    current_user: models.User = Depends(auth.get_current_user),
    db: Session = Depends(get_db),
):
    """
    Generate a short-lived handoff token so that VibeCoding can auto-login the
    user and receive project context without a separate sign-in.
    
    Uses a two-step approach to avoid URL length limits:
    1. Store full payload in database with a short token ID
    2. Return short token ID in URL
    3. VibeCoding retrieves full payload using token ID
    """
    gov = db.query(models.GovernanceResponse).filter(
        models.GovernanceResponse.project_token == request.project_token,
        models.GovernanceResponse.owner_id == current_user.id,
    ).first()

    brd_doc = None
    user_docs = db.query(models.Document).filter(
        models.Document.owner_id == current_user.id
    ).all()
    for doc in user_docs:
        if not doc.analysis_result:
            continue
        try:
            parsed = json_stdlib.loads(doc.analysis_result)
        except (TypeError, ValueError):
            continue
        gov_ctx = parsed.get("governanceContext") or {}
        proj_meta = parsed.get("projectMeta") or {}
        doc_token = proj_meta.get("project_token") or gov_ctx.get("project_token")
        if doc_token and str(doc_token) == str(request.project_token):
            brd_doc = parsed
            break

    project_context = {}
    if gov:
        project_context["project_name"] = gov.project_name
        project_context["classification"] = gov.classification
        project_context["recommendation"] = (gov.recommendation or "")[:2000]
        project_context["weighted_score"] = gov.weighted_score
        project_context["steps_data"] = gov.steps_data
    if brd_doc:
        summary = brd_doc.get("summary") or brd_doc.get("projectMeta", {}).get("description") or ""
        project_context["brd_summary"] = str(summary)[:2000]
        # Store full agent analysis (from the saved Document.analysis_result) for Vibecoding prompt context.
        # We truncate to avoid token/payload bloat.
        agent_analysis_raw = None
        for k in ("analysis", "agent_analysis", "analysis_report"):
            if brd_doc.get(k) is not None:
                agent_analysis_raw = brd_doc.get(k)
                break
        if agent_analysis_raw is not None:
            if isinstance(agent_analysis_raw, (dict, list)):
                agent_analysis_text = json_stdlib.dumps(agent_analysis_raw, ensure_ascii=False)
            else:
                agent_analysis_text = str(agent_analysis_raw)

            project_context["agent_analysis"] = agent_analysis_text

    payload = {
        "email": current_user.email,
        "first_name": current_user.first_name or "",
        "last_name": current_user.last_name or "",
        "project_token": request.project_token,
        "project_context": project_context,
        # Add new fields from the request
        "project_name": request.project_name or project_context.get("project_name", ""),
        "brd_text": request.brd_text or "",
        "analysis_data": request.analysis_data or brd_doc or {},
        "prerequisites": request.prerequisites or [],
        "custom_rules": request.custom_rules or "",
        "process_mode": request.process_mode or "vibe_coding",
        "governance_context": request.governance_context or {},
    }
    
    # Generate short token
    token = _create_handoff_token(payload)
    
    # Store payload in database with token ID
    # Extract token_id from token (format: tokenId.signature)
    token_id = token.split('.')[0]
    
    # Store in database (using a simple key-value approach with expiry)
    # We'll use the existing database session to store this
    try:
        # Create a handoff token record
        handoff_record = models.HandoffToken(
            token_id=token_id,
            payload=json_stdlib.dumps(payload),
            created_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(minutes=5),
            user_id=current_user.id
        )
        db.add(handoff_record)
        db.commit()
    except Exception as e:
        logger.error(f"Failed to store handoff token: {e}")
        # If database storage fails, fall back to the old method (embed in token)
        # This ensures backward compatibility
        payload["exp"] = int(_time.time()) + 300
        payload["iat"] = int(_time.time())
        payload_bytes = json_stdlib.dumps(payload, separators=(",", ":")).encode("utf-8")
        payload_b64 = base64.urlsafe_b64encode(payload_bytes).rstrip(b"=").decode()
        sig = hmac.new(HANDOFF_SECRET.encode(), payload_b64.encode(), hashlib.sha256).hexdigest()
        token = f"{payload_b64}.{sig}"
    
    return {"handoff_token": token}


@router.get("/api/vibecoding/handoff-payload/{token_id}")
async def get_vibecoding_handoff_payload(
    token_id: str,
    db: Session = Depends(get_db),
):
    """
    Retrieve the handoff payload for a given token ID.
    This endpoint is called by VibeCoding backend to get the full handoff data.
    No authentication required as the token itself is the authentication.
    """
    # Find the handoff token in database
    handoff_token = db.query(models.HandoffToken).filter(
        models.HandoffToken.token_id == token_id
    ).first()
    
    if not handoff_token:
        raise HTTPException(status_code=404, detail="Handoff token not found")
    
    # Check if token has expired
    if handoff_token.expires_at < datetime.utcnow():
        # Clean up expired token
        db.delete(handoff_token)
        db.commit()
        raise HTTPException(status_code=404, detail="Handoff token expired")
    
    # Mark token as used
    if not handoff_token.used_at:
        handoff_token.used_at = datetime.utcnow()
        db.commit()
    
    # Return the payload
    try:
        payload = json_stdlib.loads(handoff_token.payload)
        return payload
    except Exception as e:
        logger.error(f"Failed to parse handoff payload: {e}")
        raise HTTPException(status_code=500, detail="Invalid handoff payload")


@router.get("/vibecoding/api/projects/{project_id}/brd-context")
async def get_vibecoding_brd_context(
    project_id: str,
    db: Session = Depends(get_db),
):
    """
    API endpoint for the AI agent inside the container to fetch BRD context.
    This is called by the agent when it receives the trigger prompt.
    No authentication required since it's called from within the container.
    
    This endpoint retrieves the handoff data from the database using the project_id.
    """
    try:
        # Find the handoff token for this project
        handoff_token = db.query(models.HandoffToken).filter(
            models.HandoffToken.project_token == project_id
        ).order_by(models.HandoffToken.created_at.desc()).first()
        
        if not handoff_token:
            return {
                "has_brd": False,
                "message": "No handoff data found for this project"
            }
        
        # Parse the payload
        try:
            payload = json_stdlib.loads(handoff_token.payload)
        except Exception as e:
            logger.error(f"Failed to parse handoff payload: {e}")
            return {
                "has_brd": False,
                "message": "Invalid handoff payload"
            }
        
        # Extract BRD information from payload
        project_context = payload.get("project_context", {})
        brd_text = payload.get("brd_text", "")
        analysis_data = payload.get("analysis_data", {})
        prerequisites = payload.get("prerequisites", [])
        custom_rules = payload.get("custom_rules", "")
        project_name = payload.get("project_name") or project_context.get("project_name", "Unnamed Project")
        
        # Return the BRD context
        return {
            "has_brd": True,
            "project_name": project_name,
            "project_id": project_id,
            "brd_text": brd_text,
            "analysis_data": analysis_data,
            "prerequisites": prerequisites,
            "custom_rules": custom_rules,
            "governance_context": payload.get("governance_context", {}),
            "handoff_timestamp": handoff_token.created_at.isoformat() if handoff_token.created_at else "",
        }
        
    except Exception as e:
        logger.error(f"Error fetching BRD context for project {project_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/vibecoding/user-organizations")
def get_user_organizations_for_vibecoding(
    email: str,
    sig: str,
    db: Session = Depends(get_db)
):
    # Verify HMAC signature
    expected_sig = hmac.new(HANDOFF_SECRET.encode(), email.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected_sig, sig):
        raise HTTPException(status_code=401, detail="Invalid signature")
        
    orgs = set()
    user = db.query(models.User).filter(models.User.email.ilike(email)).first()
    if user:
        if user.organization_name:
            orgs.add(user.organization_name)
        roles = db.query(models.UserOrganizationRole).filter(models.UserOrganizationRole.user_id == user.id).all()
        for r in roles:
            if r.organization_name:
                orgs.add(r.organization_name)
                
    return {
        "organizations": sorted(list(orgs)),
        "primary_organization": user.organization_name if user else None
    }



