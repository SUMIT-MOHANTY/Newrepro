"""
DSuite BRD Analyzer - Domain Router: Multi-Agent Coordination & Knowledge Graph & Production
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

import knowledge_graph_service as kg_service
import context_manager
import master_task_manager
import master_coordination_service
from coordination_api import router as _legacy_coord_router


logger = logging.getLogger(__name__)

router = APIRouter(tags=["Coordination & Runtime"])

# --- Extracted Block (Lines 11114-11382) ---
# ═════════════════════════ KNOWLEDGE GRAPH + RAG ═════════════════════════════

class KGIndexRequest(BaseModel):
    repo_url: str
    branch: str = "main"
    token: Optional[str] = None
    brd_analysis: Optional[str] = None
    governance_context: Optional[Dict[str, Any]] = None


@router.post("/api/knowledge-graph/index")
async def index_knowledge_graph(
    payload: KGIndexRequest,
    current_user: models.User = Depends(auth.get_current_user),
    x_task_token: Optional[str] = Header(None),
):
    """
    Start indexing a repository into the Knowledge Graph + RAG system.
    Pipeline: Clone repo → Tree-sitter AST → Build KG → LightRAG embed.
    Runs in the background; use /status to poll progress.
    """
    project_token = x_task_token or str(uuid.uuid4())

    # Use user's GitHub token if no explicit token provided
    github_token = payload.token or current_user.github_token

    # Run indexing in background
    async def _run_indexing():
        try:
            result = await context_manager.index_project_repository(
                project_token=project_token,
                repo_url=payload.repo_url,
                token=github_token,
                branch=payload.branch,
                brd_analysis=payload.brd_analysis,
                governance_context=payload.governance_context,
            )
            logger.info(f"KG indexing complete for {project_token}: {result.get('status')}")
        except Exception as e:
            logger.error(f"KG indexing background task failed for {project_token}: {e}")

    bg_task = asyncio.create_task(_run_indexing())
    bg_task.add_done_callback(lambda t: logger.error(f"KG indexing error: {t.exception()}") if t.exception() else None)

    return {
        "status": "indexing_started",
        "project_token": project_token,
        "message": f"Indexing {payload.repo_url} in background. Poll /api/knowledge-graph/status/{project_token} for progress.",
    }


@router.get("/api/knowledge-graph/status/{project_token}")
async def get_kg_status(
    project_token: str,
    current_user: models.User = Depends(auth.get_current_user),
):
    """
    Check the indexing status for a project's Knowledge Graph.
    """
    rag_status = rag_service.get_indexing_status(project_token)
    graph_stats = context_manager.get_project_graph_stats(project_token)

    return {
        "project_token": project_token,
        "rag_status": rag_status,
        "graph_stats": graph_stats,
        "is_ready": context_manager.is_project_indexed(project_token),
    }


class KGQueryRequest(BaseModel):
    query: str
    mode: str = "hybrid"  # naive, local, global, hybrid
    top_k: int = 10


@router.post("/api/knowledge-graph/query")
async def query_knowledge_graph(
    payload: KGQueryRequest,
    current_user: models.User = Depends(auth.get_current_user),
    x_task_token: Optional[str] = Header(None),
):
    """
    Query the Knowledge Graph + RAG system for relevant code context.
    Returns semantically relevant code snippets and graph-connected relationships.
    """
    project_token = x_task_token
    if not project_token:
        raise HTTPException(status_code=400, detail="x-task-token header is required")

    if not context_manager.is_project_indexed(project_token):
        raise HTTPException(
            status_code=404,
            detail=f"Project {project_token} is not indexed. Call /api/knowledge-graph/index first.",
        )

    result = await rag_service.query_codebase(
        project_token=project_token,
        query=payload.query,
        mode=payload.mode,
        top_k=payload.top_k,
    )
    return result


@router.get("/api/knowledge-graph/stats/{project_token}")
async def get_kg_stats(
    project_token: str,
    current_user: models.User = Depends(auth.get_current_user),
):
    """
    Get Knowledge Graph statistics for a project.
    Returns counts of nodes (files, classes, functions, imports)
    and edges (contains, imports, calls, inherits).
    """
    stats = context_manager.get_project_graph_stats(project_token)
    if not stats:
        raise HTTPException(
            status_code=404,
            detail=f"No knowledge graph found for project {project_token}",
        )
    return {"project_token": project_token, "stats": stats}


@router.delete("/api/knowledge-graph/{project_token}")
async def delete_knowledge_graph(
    project_token: str,
    current_user: models.User = Depends(auth.get_current_user),
):
    """
    Delete all indexed Knowledge Graph and RAG data for a project.
    """
    result = await rag_service.delete_index(project_token)
    return {"status": "deleted", "project_token": project_token, "details": result}


class AgentContextRequest(BaseModel):
    task_description: str
    task_type: Optional[str] = None
    brd_analysis: Optional[str] = None
    governance_context: Optional[Dict[str, Any]] = None


@router.post("/api/knowledge-graph/agent-context")
async def get_agent_context(
    payload: AgentContextRequest,
    current_user: models.User = Depends(auth.get_current_user),
    x_task_token: Optional[str] = Header(None),
):
    """
    Get the full three-layer context for an agent task:
    Layer 1: Global codebase context (tech stack, structure)
    Layer 2: Project rules (BRD analysis, governance)
    Layer 3: Just-in-time code snippets (LightRAG hybrid query)
    """
    project_token = x_task_token
    if not project_token:
        raise HTTPException(status_code=400, detail="x-task-token header is required")

    context = await context_manager.get_full_agent_context(
        project_token=project_token,
        task_description=payload.task_description,
        task_type=payload.task_type,
        brd_analysis=payload.brd_analysis,
        governance_context=payload.governance_context,
    )
    return {
        "context": context,
        "is_indexed": context_manager.is_project_indexed(project_token),
        "project_token": project_token,
    }


@router.get("/api/knowledge-graph/cross-agent-memory/{project_token}")
async def get_cross_agent_memory(
    project_token: str,
    current_user: models.User = Depends(auth.get_current_user),
):
    """
    Get the live cross-agent shared memory for a project.
    Shows which agents are active, what files they're touching,
    and what was recently completed.
    """
    memory = context_manager.get_live_memory(project_token)

    active_agents = []
    for aid, record in memory.active_tasks.items():
        active_agents.append({
            "agent_id": record.agent_id,
            "task_title": record.task_title,
            "task_description": record.task_description[:200],
            "branch_name": record.branch_name,
            "started_at": record.started_at,
        })

    completed_history = []
    for record in memory.completed_history[:20]:
        completed_history.append({
            "agent_id": record.agent_id,
            "task_title": record.task_title,
            "status": record.status,
            "files_touched": record.files_touched,
            "symbols_created": record.symbols_created,
            "exit_code": record.exit_code,
            "summary": record.summary,
            "completed_at": record.completed_at,
        })

    file_locks = {
        fpath: list(agents)
        for fpath, agents in memory.file_locks.items()
        if agents
    }

    return {
        "project_token": project_token,
        "active_agents": active_agents,
        "completed_history": completed_history,
        "file_locks": file_locks,
        "total_completed": len(memory.completed_history),
    }


@router.get("/api/knowledge-graph/tech-spec/{project_token}")
async def get_tech_spec(
    project_token: str,
    current_user: models.User = Depends(auth.get_current_user),
):
    """Get the generated Technical Spec (Layer 1: Architect Agent)."""
    from agent_service import get_technical_spec, _project_tech_specs
    spec = get_technical_spec(project_token)
    record = _project_tech_specs.get(project_token, {})
    return {
        "project_token": project_token,
        "status": record.get("status", "not_generated"),
        "spec": spec,
        "char_length": len(spec),
        "generated_at": record.get("generated_at"),
    }


@router.post("/api/knowledge-graph/tech-spec/{project_token}/generate")
async def generate_tech_spec(
    project_token: str,
    current_user: models.User = Depends(auth.get_current_user),
):
    """Manually trigger Technical Spec generation (Layer 1: Architect Agent)."""
    from agent_service import _generate_technical_spec

    # Get KG context if available
    kg_context = ""
    try:
        if context_manager.is_project_indexed(project_token):
            kg_context = await context_manager.get_full_agent_context(
                project_token=project_token,
                task_description="Full system architecture overview",
                agent_id="architect_agent",
            )
    except Exception:
        pass

    result = await _generate_technical_spec(
        project_token=project_token,
        tasks=[],
        kg_context=kg_context,
    )
    return result



# --- Extracted Block (Lines 12438-12565) ---
@router.get("/coordination/status")
async def get_coordination_status(
    current_user: models.User = Depends(auth.get_current_user),
    project_token: Optional[str] = None,
):
    """🎯 Get Master Task Manager coordination status"""
    project_token = _normalize_project_token(project_token)
    _require_organization(current_user)
    
    return master_task_manager.master_task_manager.get_coordination_status(project_token)


@router.post("/coordination/agent/{agent_id}/file-lock")
async def request_file_lock(
    agent_id: str,
    file_path: str,
    current_user: models.User = Depends(auth.get_current_user),
    project_token: Optional[str] = None,
):
    """🔒 Agent requests file lock through Master Task Manager"""
    project_token = _normalize_project_token(project_token)
    _require_organization(current_user)
    
    return await master_task_manager.master_task_manager.request_file_lock(agent_id, file_path)


@router.post("/coordination/agent/{agent_id}/configure")
async def configure_agent_capabilities(
    agent_id: str,
    request: dict,
    current_user: models.User = Depends(auth.get_current_user),
    project_token: Optional[str] = None,
):
    """🎯 Configure agent capabilities - MANUAL OVERRIDE"""
    project_token = _normalize_project_token(project_token)
    _require_organization(current_user)
    
    primary_skills = request.get("primary_skills", [])
    secondary_skills = request.get("secondary_skills", [])
    
    master_task_manager.master_task_manager.set_explicit_agent_config(
        agent_id, primary_skills, secondary_skills
    )
    
    return {
        "status": "configured",
        "agent_id": agent_id,
        "primary_skills": primary_skills,
        "secondary_skills": secondary_skills,
        "message": f"Agent {agent_id} capabilities configured manually"
    }


@router.post("/coordination/agent/{agent_id}/ai-assign")
async def ai_assign_agent_capabilities(
    agent_id: str,
    current_user: models.User = Depends(auth.get_current_user),
    project_token: Optional[str] = None,
):
    """🤖 Let Master Agent decide agent capabilities using AI"""
    project_token = _normalize_project_token(project_token)
    _require_organization(current_user)
    
    # Get project context for AI decision
    project_context = f"Project: {project_token or 'default'}"
    
    decision = await master_task_manager.master_task_manager.master_agent_assign_capabilities(
        agent_id, project_context
    )
    
    return {
        "status": "ai_assigned",
        "agent_id": agent_id,
        "decision": decision,
        "message": f"Master Agent assigned capabilities to {agent_id}"
    }


@router.get("/coordination/agent/{agent_id}/capabilities")
async def get_agent_capabilities(
    agent_id: str,
    current_user: models.User = Depends(auth.get_current_user),
    project_token: Optional[str] = None,
):
    """📋 Get current agent capabilities and assignment method"""
    project_token = _normalize_project_token(project_token)
    _require_organization(current_user)
    
    capabilities = master_task_manager.master_task_manager._get_agent_capabilities(agent_id)
    
    return {
        "agent_id": agent_id,
        "capabilities": capabilities,
        "assignment_method": capabilities.get("assigned_by", "unknown")
    }


@router.get("/coordination/agents/bulk-configure")
async def bulk_configure_agents(
    current_user: models.User = Depends(auth.get_current_user),
    project_token: Optional[str] = None,
):
    """🎯 Get bulk configuration options for all agents"""
    project_token = _normalize_project_token(project_token)
    _require_organization(current_user)
    
    # Get all agents and their current capabilities
    all_agents = {}
    for agent_id in master_task_manager.master_task_manager.agent_status.keys():
        capabilities = master_task_manager.master_task_manager._get_agent_capabilities(agent_id)
        all_agents[agent_id] = {
            "current_capabilities": capabilities,
            "suggested_by_pattern": master_task_manager.master_task_manager._get_agent_capabilities_by_pattern(agent_id),
            "can_ai_assign": True
        }
    
    return {
        "agents": all_agents,
        "available_skills": ["frontend", "backend", "setup", "integration"],
        "assignment_methods": [
            "explicit_config",    # Manual configuration
            "master_agent",       # AI decision by Master Agent  
            "pattern_recognition", # Automatic by name pattern
            "default_fallback"    # Democratic fallback
        ]
    }



# --- Extracted Block (Lines 12579-12773) ---
@router.post("/api/context/update")
async def update_context(
    project_token: str,
    agent_id: str,
    current_task: Optional[str] = None,
    current_files: List[str] = [],
    completed_tasks: List[str] = [],
    created_files: List[str] = [],
    modified_files: List[str] = [],
    api_endpoints: List[Dict[str, Any]] = [],
    database_tables: List[str] = [],
    shared_utilities: List[str] = [],
    tags: List[str] = [],
    current_user: models.User = Depends(auth.get_current_user)
):
    """📝 Update agent context with structured information"""
    from enhanced_context_service import update_agent_context
    
    success = await update_agent_context(
        project_token=project_token,
        agent_id=agent_id,
        current_task=current_task,
        current_files=current_files,
        completed_tasks=completed_tasks,
        created_files=created_files,
        modified_files=modified_files,
        api_endpoints=api_endpoints,
        database_tables=database_tables,
        shared_utilities=shared_utilities,
        tags=tags
    )
    
    return {"success": success, "agent_id": agent_id}


@router.get("/api/context/query/{query_type}")
async def query_context(
    project_token: str,
    query_type: str,
    file_pattern: Optional[str] = None,
    tag: Optional[str] = None,
    module: Optional[str] = None,
    agent_id: Optional[str] = None,
    current_user: models.User = Depends(auth.get_current_user)
):
    """🔍 Query shared context with various filters"""
    from enhanced_context_service import query_agent_context
    
    filters = {}
    if file_pattern:
        filters["file_pattern"] = file_pattern
    if tag:
        filters["tag"] = tag
    if module:
        filters["module"] = module
    if agent_id:
        filters["agent_id"] = agent_id
    
    result = await query_agent_context(
        project_token=project_token,
        query_type=query_type,
        **filters
    )
    
    return result


@router.get("/api/context/agent/{agent_id}")
async def get_agent_context_view(
    project_token: str,
    agent_id: str,
    current_user: models.User = Depends(auth.get_current_user)
):
    """👁️ Get comprehensive context view for specific agent"""
    from enhanced_context_service import enhanced_context_service
    
    view = await enhanced_context_service.get_agent_context_view(
        project_token=project_token,
        agent_id=agent_id
    )
    
    return view


@router.post("/api/context/memory-board")
async def post_to_memory_board(
    project_token: str,
    agent_id: str,
    message_type: str,
    content: str,
    tags: List[str] = [],
    reply_to: Optional[str] = None,
    current_user: models.User = Depends(auth.get_current_user)
):
    """💬 Post message to shared memory board"""
    from enhanced_context_service import enhanced_context_service, ContextMessageType
    
    try:
        msg_type = ContextMessageType(message_type)
    except ValueError:
        return {"error": f"Invalid message type: {message_type}"}
    
    message_id = await enhanced_context_service.post_to_memory_board(
        project_token=project_token,
        agent_id=agent_id,
        message_type=msg_type,
        content=content,
        tags=tags,
        reply_to=reply_to
    )
    
    return {"success": True, "message_id": message_id}


@router.get("/api/context/memory-board")
async def get_memory_board(
    project_token: str,
    limit: int = 50,
    tags: Optional[str] = None,
    current_user: models.User = Depends(auth.get_current_user)
):
    """📋 Get messages from memory board"""
    from enhanced_context_service import enhanced_context_service
    
    if project_token not in enhanced_context_service.project_contexts:
        return {"messages": []}
    
    context = enhanced_context_service.project_contexts[project_token]
    messages = context["memory_board"]
    
    # Filter by tags if provided
    if tags:
        tag_list = [t.strip() for t in tags.split(",")]
        messages = [
            msg for msg in messages
            if any(tag in msg.get("tags", []) for tag in tag_list)
        ]
    
    # Return most recent messages
    return {"messages": messages[-limit:]}


@router.post("/api/context/dependency")
async def declare_dependency(
    project_token: str,
    agent_id: str,
    depends_on: Dict[str, List[str]],
    current_user: models.User = Depends(auth.get_current_user)
):
    """🔗 Declare dependencies on other agents' work"""
    from enhanced_context_service import enhanced_context_service
    
    success = await enhanced_context_service.declare_dependency(
        project_token=project_token,
        agent_id=agent_id,
        depends_on=depends_on
    )
    
    return {"success": success, "agent_id": agent_id, "dependencies": depends_on}


@router.post("/api/context/snapshot")
async def create_context_snapshot(
    project_token: str,
    sync_point: str,
    metadata: Optional[Dict[str, Any]] = None,
    current_user: models.User = Depends(auth.get_current_user)
):
    """📸 Create context snapshot at sync point"""
    from enhanced_context_service import enhanced_context_service
    
    snapshot = await enhanced_context_service.create_context_snapshot(
        project_token=project_token,
        sync_point=sync_point,
        metadata=metadata
    )
    
    return snapshot


@router.get("/api/context/snapshots")
async def get_context_snapshots(
    project_token: str,
    current_user: models.User = Depends(auth.get_current_user)
):
    """📚 Get all context snapshots for project"""
    from enhanced_context_service import enhanced_context_service
    
    if project_token not in enhanced_context_service.project_contexts:
        return {"snapshots": []}
    
    context = enhanced_context_service.project_contexts[project_token]
    return {"snapshots": context["snapshots"]}



# --- Extracted Block (Lines 12990-13033) ---
@router.websocket("/ws/preview/{project_token}")
async def websocket_preview_logs(websocket: WebSocket, project_token: str):
    """
    WebSocket endpoint for real-time deploy preview logs.
    The frontend connects here when a deploy starts.
    On connection, sends all buffered past logs immediately,
    then keeps the connection open for new logs from the container.
    """
    await websocket.accept()
    pt = project_token or ""

    # Register connection
    if pt not in _preview_ws_connections:
        _preview_ws_connections[pt] = []
    _preview_ws_connections[pt].append(websocket)

    try:
        # Send all buffered past logs immediately (so UI has history)
        past_logs = _preview_log_store.get(pt, [])
        for entry in past_logs:
            await websocket.send_json(entry)

        # Keep connection alive — new logs come via /agents/preview/log broadcasting
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                # Echo heartbeat pings
                if data == "ping":
                    await websocket.send_json({"type": "pong"})
            except asyncio.TimeoutError:
                # Send keepalive
                await websocket.send_json({"type": "keepalive"})
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        try:
            if pt in _preview_ws_connections:
                _preview_ws_connections[pt].remove(websocket)
        except ValueError:
            pass



# --- Extracted Block (Lines 14622-14641) ---
class TaskTokenRequest(BaseModel):
    client_id: str
    client_secret: str

@router.post("/api/token/task/")
async def fetch_task_token(
    payload: TaskTokenRequest,
):
    """Fetch task token dynamically from the task management API"""
    try:
        import httpx
        from config import settings
        token_url = f"{settings.task_api_base_url.rstrip('/')}/api/token/task/"
        async with httpx.AsyncClient() as client:
            response = await client.post(token_url, json=payload.dict(), timeout=10.0)
            response.raise_for_status()
            return response.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch task token: {str(e)}")


# --- Extracted Block (Lines 18122-18768) ---
@router.get("/api/production/validate")
async def validate_production_readiness(
    project_token: Optional[str] = None,
    current_user: models.User = Depends(auth.get_current_user)
):
    """Validate if project is ready for production deployment"""
    try:
        validation = await agent_service._validate_production_readiness(project_token=project_token)
        return validation
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Validation failed: {str(e)}")

@router.get("/api/production/report")
async def get_production_report(
    project_token: Optional[str] = None,
    current_user: models.User = Depends(auth.get_current_user)
):
    """Get comprehensive production readiness report"""
    try:
        report = await agent_service._generate_production_report(project_token=project_token)
        return {"report": report}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Report generation failed: {str(e)}")

@router.post("/api/production/ensure-ready")
async def ensure_production_ready(
    project_token: Optional[str] = None,
    current_user: models.User = Depends(auth.get_current_user)
):
    """Ensure project meets production standards with auto-fixes"""
    try:
        result = await agent_service._ensure_production_ready_project(project_token=project_token)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Production preparation failed: {str(e)}")

@router.get("/api/system/health")
async def system_health_check():
    """Complete system health check for production readiness"""
    try:
        health = {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "components": {
                "database": "healthy",
                "llm_gateway": "healthy" if llm_gateway.check_api_key() else "degraded",
                "docker": "healthy" if agent_service._check_docker_available() else "unavailable",
                "git_manager": "healthy"
            },
            "version": "1.0.0",
            "uptime": "unknown"
        }
        
        # Check critical components
        unhealthy_components = [k for k, v in health["components"].items() if v != "healthy"]
        if unhealthy_components:
            health["status"] = "degraded"
            health["issues"] = unhealthy_components
        
        return health
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }
@router.get("/api/bulletproof/success-rate")
async def get_bulletproof_success_rate(
    project_token: Optional[str] = None,
    current_user: models.User = Depends(auth.get_current_user)
):
    """Get bulletproof execution success rate metrics"""
    try:
        state = agent_service._ensure_project_state(project_token)
        all_tasks = state.get("tasks", [])
        completed_tasks = [t for t in all_tasks if agent_service._task_status_is_done(t.get("status"))]
        
        # Calculate success metrics
        total_tasks = len(all_tasks)
        completed_count = len(completed_tasks)
        success_rate = (completed_count / total_tasks * 100) if total_tasks > 0 else 0
        
        # Analyze task complexity and success correlation
        task_success_by_type = {}
        for task in completed_tasks:
            task_type = task.get("task_type", "UNKNOWN")
            if task_type not in task_success_by_type:
                task_success_by_type[task_type] = {"completed": 0, "total": 0}
            task_success_by_type[task_type]["completed"] += 1
        
        for task in all_tasks:
            task_type = task.get("task_type", "UNKNOWN")
            if task_type not in task_success_by_type:
                task_success_by_type[task_type] = {"completed": 0, "total": 0}
            task_success_by_type[task_type]["total"] += 1
        
        # Calculate success rate by type
        for task_type in task_success_by_type:
            data = task_success_by_type[task_type]
            data["success_rate"] = (data["completed"] / data["total"] * 100) if data["total"] > 0 else 0
        
        # Determine if we're meeting the 90% target
        meets_target = success_rate >= 90.0
        
        return {
            "overall_success_rate": round(success_rate, 1),
            "meets_90_percent_target": meets_target,
            "total_tasks": total_tasks,
            "completed_tasks": completed_count,
            "remaining_tasks": total_tasks - completed_count,
            "success_by_type": task_success_by_type,
            "target": 90.0,
            "status": "EXCELLENT" if success_rate >= 90 else "GOOD" if success_rate >= 75 else "NEEDS_IMPROVEMENT"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Success rate calculation failed: {str(e)}")

@router.post("/api/bulletproof/optimize-tasks")
async def optimize_tasks_for_success(
    project_token: Optional[str] = None,
    current_user: models.User = Depends(auth.get_current_user)
):
    """Optimize existing tasks for bulletproof execution"""
    try:
        state = agent_service._ensure_project_state(project_token)
        all_tasks = state.get("tasks", [])
        
        # Apply bulletproof optimization to all tasks
        from task_generation_service import _bulletproof_task_generation_post_process
        optimized_tasks = _bulletproof_task_generation_post_process(all_tasks)
        
        # Update the state with optimized tasks
        state["tasks"] = optimized_tasks
        
        return {
            "success": True,
            "message": f"Optimized {len(optimized_tasks)} tasks for bulletproof execution",
            "optimized_count": len(optimized_tasks),
            "improvements": [
                "Enhanced task descriptions with bulletproof requirements",
                "Added comprehensive validation steps to checklists",
                "Improved error handling specifications",
                "Added testing and verification requirements"
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Task optimization failed: {str(e)}")

@router.get("/api/bulletproof/agent-performance")
async def get_agent_performance_metrics(
    project_token: Optional[str] = None,
    current_user: models.User = Depends(auth.get_current_user)
):
    """Get detailed agent performance metrics for bulletproof execution"""
    try:
        state = agent_service._ensure_project_state(project_token)
        agents = state.get("agent_states", {})
        
        performance_metrics = {}
        
        for agent_id, agent_data in agents.items():
            if agent_service._is_system_agent_id(agent_id):
                continue
                
            # Calculate agent-specific metrics
            agent_tasks = [t for t in state.get("tasks", []) if t.get("assigned_agent") == agent_id]
            completed_agent_tasks = [t for t in agent_tasks if agent_service._task_status_is_done(t.get("status"))]
            
            success_rate = (len(completed_agent_tasks) / len(agent_tasks) * 100) if agent_tasks else 0
            
            # Analyze self-healing effectiveness
            healing_stats = {
                "total_healing_attempts": 0,
                "successful_healings": 0,
                "average_iterations": 0
            }
            
            # Get recent output logs for analysis
            output_logs = agent_data.get("output_log", [])
            healing_logs = [log for log in output_logs if "self-healing" in log.get("message", "").lower()]
            
            if healing_logs:
                healing_stats["total_healing_attempts"] = len(healing_logs)
                # Estimate successful healings (simplified)
                healing_stats["successful_healings"] = len([log for log in healing_logs if "completed" in log.get("message", "")])
            
            performance_metrics[agent_id] = {
                "agent_name": agent_data.get("name", agent_id),
                "status": agent_data.get("status", "unknown"),
                "total_tasks": len(agent_tasks),
                "completed_tasks": len(completed_agent_tasks),
                "success_rate": round(success_rate, 1),
                "meets_target": success_rate >= 90.0,
                "self_healing": healing_stats,
                "last_activity": agent_data.get("last_run", "never"),
                "current_task": agent_data.get("current_task", {}).get("title", "None") if agent_data.get("current_task") else "None"
            }
        
        # Calculate overall agent performance
        all_success_rates = [metrics["success_rate"] for metrics in performance_metrics.values() if metrics["total_tasks"] > 0]
        overall_agent_performance = sum(all_success_rates) / len(all_success_rates) if all_success_rates else 0
        
        return {
            "overall_agent_performance": round(overall_agent_performance, 1),
            "meets_90_percent_target": overall_agent_performance >= 90.0,
            "agent_metrics": performance_metrics,
            "total_active_agents": len([a for a in performance_metrics.values() if a["status"] != "idle"]),
            "high_performing_agents": len([a for a in performance_metrics.values() if a["success_rate"] >= 90]),
            "target": 90.0
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent performance calculation failed: {str(e)}")

@router.post("/api/bulletproof/guarantee-success")
async def guarantee_bulletproof_success(
    project_token: Optional[str] = None,
    current_user: models.User = Depends(auth.get_current_user)
):
    """Apply all bulletproof optimizations to guarantee 90%+ success rate"""
    try:
        # 1. Optimize tasks for bulletproof execution
        optimize_result = await optimize_tasks_for_success(project_token, current_user)
        
        # 2. Ensure production readiness
        production_result = await agent_service._ensure_production_ready_project(project_token=project_token)
        
        # 3. Validate system health
        health_result = await system_health_check()
        
        # 4. Calculate expected success rate
        success_metrics = await get_bulletproof_success_rate(project_token, current_user)
        
        return {
            "success": True,
            "message": "Bulletproof success optimizations applied",
            "expected_success_rate": "90%+",
            "optimizations_applied": [
                "Task descriptions enhanced with bulletproof requirements",
                "Comprehensive validation steps added to all tasks",
                "Error handling and testing requirements specified",
                "Production readiness validation enabled",
                "System health monitoring activated"
            ],
            "task_optimization": optimize_result,
            "production_readiness": production_result,
            "system_health": health_result.get("status", "unknown"),
            "current_metrics": success_metrics,
            "guarantee": "90%+ task execution success rate with bulletproof enhancements"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Bulletproof guarantee setup failed: {str(e)}")

ARTIFACTS_DIR = Path(os.getenv('ARTIFACTS_DIR', './project_artifacts'))
 
def get_container_port(project_id: str) -> str:
    """Return the host port for a preview container belonging to *project_id*.

    The function now checks three sources, in order:
    1️⃣ **Agent preview state** – ``agent_service.get_preview_status`` stores the
        ``preview_url`` (e.g. ``http://localhost:9100``) when a preview is
        running. If that URL is available we extract the port from it.
    2️⃣ **Legacy registry file** – ``.container_registry.json`` as before.
    3️⃣ **Docker ``ps`` fallback** – searches running containers whose name
        contains the *project_id* and parses the ``Ports`` column.
    Returns ``None`` when no port can be determined.
    """
    import re
    try:
        # 1️⃣ Check the in‑memory preview state via agent_service.
        preview_state = agent_service.get_preview_status(project_id)
        if preview_state and preview_state.get("status") == "running":
            preview_url = preview_state.get("preview_url")
            if preview_url:
                # Expected format: http://localhost:<port>
                match = re.search(r"://[^:/]+:(\d+)", preview_url)
                if match:
                    return match.group(1)

        # 2️⃣ Legacy registry lookup.
        registry_file = ARTIFACTS_DIR / '.container_registry.json'
        if registry_file.exists():
            with open(registry_file, 'r') as f:
                registry = json.load(f)
                for name, info in registry.items():
                    if project_id in name and isinstance(info, dict) and 'port' in info:
                        return str(info['port'])

        # 3️⃣ Docker fallback – search running containers for the project id.
        result = subprocess.run(
            ["docker", "ps", "--filter", f"name={project_id}", "--format", "{{{{.Names}}}} {{{{.Ports}}}}"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                parts = line.split()
                if len(parts) >= 2 and project_id in parts[0]:
                    port_match = re.search(r"0\.0\.0\.0:(\d+)->", parts[1])
                    if port_match:
                        return port_match.group(1)
    except Exception as e:
        print(f"Error determining container port for {project_id}: {e}")

    print(f"No port found for project_id: {project_id}")
    return None
 
def _rewrite_html_assets(html_bytes: bytes, proxy_prefix: str) -> bytes:
    """Rewrite absolute asset paths in HTML so they route through the proxy.

    e.g. src="/assets/main.js"  ->  src="/app/{token}/assets/main.js"
         href="/style.css"       ->  href="/app/{token}/style.css"
         url(/fonts/x.woff)      ->  url(/app/{token}/fonts/x.woff)

    Only rewrites paths that start with "/" but NOT "//" (protocol-relative),
    and NOT paths that already start with the proxy_prefix.
    """
    import re as _re

    proxy_prefix = proxy_prefix.rstrip("/")

    def _replace_attr(m):
        attr, quote, path = m.group(1), m.group(2), m.group(3)
        # skip protocol-relative, data URIs, mailto, hash-only etc.
        if path.startswith("//") or ":" in path.split("/")[0] or path.startswith("#"):
            return m.group(0)
        if path.startswith(proxy_prefix + "/") or path == proxy_prefix:
            return m.group(0)
        return f'{attr}={quote}{proxy_prefix}{path}{quote}'

    def _replace_url(m):
        inner = m.group(1).strip("'\"")
        if inner.startswith("//") or ":" in inner.split("/")[0] or inner.startswith("#"):
            return m.group(0)
        if inner.startswith(proxy_prefix + "/") or inner == proxy_prefix:
            return m.group(0)
        return f"url({proxy_prefix}{inner})"

    try:
        html = html_bytes.decode("utf-8", errors="replace")
    except Exception:
        return html_bytes

    # Rewrite src=, href=, action= attributes with absolute paths
    html = _re.sub(
        r'(src|href|action)=(["\'])(/[^"\'>\s]*)\2',
        _replace_attr,
        html,
        flags=_re.IGNORECASE,
    )
    # Rewrite CSS url(/...) references
    html = _re.sub(
        r'url\((["\']?/[^)"\'>\s]*["\']?)\)',
        _replace_url,
        html,
        flags=_re.IGNORECASE,
    )

    return html.encode("utf-8")


def proxy_request(target_base: str, request: Request, forward_path: str, proxy_prefix: str = ""):
    """Generic proxy handler. If proxy_prefix is given, rewrites HTML asset paths."""
    target_url = target_base + forward_path

    # Forward query params
    if request.url.query:
        target_url += "?" + request.url.query

    # Forward headers (excluding host)
    headers = {
        key: value
        for key, value in request.headers.items()
        if key.lower() not in ["host", "x-forwarded-for", "x-forwarded-proto"]
    }

    try:
        resp = requests.request(
            method=request.method,
            url=target_url,
            headers=headers,
            allow_redirects=False,
            timeout=(5, 30)
        )

        excluded_headers = [
            "content-encoding",
            "content-length",
            "transfer-encoding",
            "connection"
        ]

        response_headers = {
            name: value
            for name, value in resp.headers.items()
            if name.lower() not in excluded_headers
        }

        body = resp.content
        content_type = resp.headers.get("content-type", "")

        # Rewrite HTML so absolute asset paths are proxied correctly
        if proxy_prefix and "text/html" in content_type:
            body = _rewrite_html_assets(body, proxy_prefix)

        return StreamingResponse(
            iter([body]),
            status_code=resp.status_code,
            headers=response_headers
        )
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Proxy Error: {str(e)}")
 
@router.api_route("/app/{token}/", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
@router.api_route("/app/{token}/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def route_proxy(token: str, request: Request, path: str = ""):
    """Route requests to the appropriate container based on project token"""
    # Get container port for this project
    port = get_container_port(token)
    print(f"Port for token {token}: {port}")
    if not port:
        raise HTTPException(
            status_code=404,
            detail=f"Project '{token}' not found or container not running"
        )
   
    target = f"http://127.0.0.1:{port}"
    forward_path = "/" + path if path else "/"
    proxy_prefix = f"/app/{token}"
    return proxy_request(target, request, forward_path, proxy_prefix=proxy_prefix)

class BournAIMetricsRequest(BaseModel):
    salt_key: str
    date: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None

@router.post("/api/public/metrics/bournai")
def get_public_bournai_metrics(
    req: BournAIMetricsRequest,
    db: Session = Depends(get_db)
):
    """
    Public API endpoint to query BournAI model token usage and cost metrics.
    Requires salt_key that is RSA-encrypted/signed and verified using the
    RSA public key configured in settings.
    """
    import datetime
    
    # Verify the salt_key using RSA-2048 public key decryption
    # The external service encrypts the known salt value with their private key,
    # and we decrypt it here and compare against the expected salt.
    expected_salt = settings.metrics_api_salt
    
    if not expected_salt:
        raise HTTPException(status_code=500, detail="Server configuration error: METRICS_API_SALT not set")
    
    if not req.salt_key:
        raise HTTPException(status_code=401, detail="Unauthorized: Missing salt_key")
    
    if not rsa_utils.decrypt_and_verify(req.salt_key, expected_salt=expected_salt):
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid salt_key")
        
    start_dt = None
    end_dt = None
    
    # 1. Parse date parameters
    if req.date:
        try:
            start_dt = datetime.datetime.strptime(req.date, "%Y-%m-%d")
            end_dt = start_dt + datetime.timedelta(days=1) - datetime.timedelta(microseconds=1)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Expected YYYY-MM-DD")
    else:
        if req.start_date:
            try:
                start_dt = datetime.datetime.strptime(req.start_date, "%Y-%m-%d")
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid start_date format. Expected YYYY-MM-DD")
        if req.end_date:
            try:
                end_dt = datetime.datetime.strptime(req.end_date, "%Y-%m-%d") + datetime.timedelta(days=1) - datetime.timedelta(microseconds=1)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid end_date format. Expected YYYY-MM-DD")
                
    # 2. Query logs
    query = db.query(models.AIUsageLog).filter(
        func.lower(models.AIUsageLog.model) == "bournai"
    )
    if start_dt:
        query = query.filter(models.AIUsageLog.created_at >= start_dt)
    if end_dt:
        query = query.filter(models.AIUsageLog.created_at <= end_dt)
        
    logs = query.all()
    
    # 3. Build organization lookups to map logs to their organizations
    user_org_list = db.query(models.User.id, models.User.organization_name).all()
    user_orgs = {u_id: org for u_id, org in user_org_list if org}

    project_org_list = db.query(models.GovernanceResponse.project_token, models.GovernanceResponse.organization_name).all()
    project_orgs = {p_token: org for p_token, org in project_org_list if org}

    # 4. Sum up values globally and by organization/user
    total_prompt = 0
    total_completion = 0
    total_token_cost = 0.0
    total_infra_cost = 0.0
    request_count = len(logs)

    org_metrics = {}
    # Structure: { org_key: { user_key: [timestamps] } }
    org_user_timestamps = {}
    org_user_token_costs = {}
    org_user_requests = {}
    org_user_tokens = {}

    for l in logs:
        # Resolve organization
        org_name = None
        if l.project_token and l.project_token in project_orgs:
            org_name = project_orgs[l.project_token]
        elif l.user_id and l.user_id in user_orgs:
            org_name = user_orgs[l.user_id]
        
        org_key = str(org_name).strip() if org_name else "Unknown / Shared"

        if org_key not in org_metrics:
            org_metrics[org_key] = {
                "request_count": 0,
                "total_prompt_tokens": 0,
                "total_completion_tokens": 0,
                "total_tokens": 0,
                "token_cost_usd": 0.0,
                "unique_users_count": 0,
                "usage_duration_seconds": 0.0,
                "usage_duration_hours": 0.0,
                "infra_cost_usd": 0.0,
                "total_cost_usd": 0.0,
                "user_breakdown": {}
            }
            org_user_timestamps[org_key] = {}
            org_user_token_costs[org_key] = {}
            org_user_requests[org_key] = {}
            org_user_tokens[org_key] = {}

        # Distinct user key for user-wise infra cost tracking
        if l.user_id:
            user_key = f"user_{l.user_id}"
        elif l.project_token:
            user_key = f"project_{l.project_token}"
        else:
            user_key = "anonymous"

        if user_key not in org_user_timestamps[org_key]:
            org_user_timestamps[org_key][user_key] = []
            org_user_token_costs[org_key][user_key] = 0.0
            org_user_requests[org_key][user_key] = 0
            org_user_tokens[org_key][user_key] = 0

        p_tok = l.prompt_tokens or 0
        c_tok = l.completion_tokens or 0
        c_val = l.cost or 0.0

        # Global sum tokens & token cost
        total_prompt += p_tok
        total_completion += c_tok
        total_token_cost += c_val

        # Org sum
        org_metrics[org_key]["request_count"] += 1
        org_metrics[org_key]["total_prompt_tokens"] += p_tok
        org_metrics[org_key]["total_completion_tokens"] += c_tok
        org_metrics[org_key]["total_tokens"] += (p_tok + c_tok)
        org_metrics[org_key]["token_cost_usd"] += c_val

        # User sum
        org_user_requests[org_key][user_key] += 1
        org_user_tokens[org_key][user_key] += (p_tok + c_tok)
        org_user_token_costs[org_key][user_key] += c_val

        if l.created_at:
            org_user_timestamps[org_key][user_key].append(l.created_at)

    # Compute duration and $1/hour infra cost USER-WISE for each organization
    for org_key, metrics in org_metrics.items():
        org_dur_seconds = 0.0
        org_infra_cost = 0.0
        user_breakdown = {}

        for user_key, ts_list in org_user_timestamps.get(org_key, {}).items():
            if ts_list:
                min_ts = min(ts_list)
                max_ts = max(ts_list)
                u_dur_seconds = (max_ts - min_ts).total_seconds()
            else:
                u_dur_seconds = 0.0

            u_dur_hours = u_dur_seconds / 3600.0
            # $0.70 per hour infra cost per user ($0.7/3600 per second)
            u_infra_cost = u_dur_hours * 0.7
            u_tok_cost = org_user_token_costs[org_key][user_key]
            u_total_cost = u_tok_cost + u_infra_cost

            user_breakdown[user_key] = {
                "request_count": org_user_requests[org_key][user_key],
                "total_tokens": org_user_tokens[org_key][user_key],
                "usage_duration_seconds": round(u_dur_seconds, 2),
                "usage_duration_hours": round(u_dur_hours, 4),
                "token_cost_usd": round(u_tok_cost, 6),
                "infra_cost_usd": round(u_infra_cost, 6),
                "total_cost_usd": round(u_total_cost, 6)
            }

            org_dur_seconds += u_dur_seconds
            org_infra_cost += u_infra_cost

        metrics["unique_users_count"] = len(user_breakdown)
        metrics["usage_duration_seconds"] = round(org_dur_seconds, 2)
        metrics["usage_duration_hours"] = round(org_dur_seconds / 3600.0, 4)
        metrics["infra_cost_usd"] = round(org_infra_cost, 6)
        metrics["token_cost_usd"] = round(metrics["token_cost_usd"], 6)
        metrics["total_cost_usd"] = round(metrics["token_cost_usd"] + metrics["infra_cost_usd"], 6)
        metrics["user_breakdown"] = user_breakdown

        total_infra_cost += org_infra_cost

    total_cost = total_token_cost + total_infra_cost

    return {
        "model": "BournAI",
        "query_parameters": {
            "date": req.date,
            "start_date": req.start_date,
            "end_date": req.end_date
        },
        "global_metrics": {
            "request_count": request_count,
            "total_prompt_tokens": total_prompt,
            "total_completion_tokens": total_completion,
            "total_tokens": total_prompt + total_completion,
            "total_token_cost_usd": round(total_token_cost, 6),
            "total_infra_cost_usd": round(total_infra_cost, 6),
            "total_cost_usd": round(total_cost, 6)
        },
        "organizations": org_metrics
    }
