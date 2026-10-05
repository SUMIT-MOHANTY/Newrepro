"""Agent Callbacks Domain Router.

Receives lifecycle and tool execution events from isolated Agent Runtime containers
and broadcasts them live to connected WebSockets in real time.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.routers.helpers import _preview_log_store, _preview_ws_connections
from app.services.agents.agent_service import agent_service
import models

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Agent Container Callbacks"])


@router.post("/callback")
@router.post("/agent/callback")
@router.post("/api/v1/agent/callback")
@router.post("/api/v1/callback")
@router.post("/api/agent/callback")
async def receive_agent_callback(
    request: Request,
    db: Session = Depends(get_db),
    x_callback_secret: Optional[str] = Header(None),
) -> Dict[str, Any]:
    """Receive event from Agent Runtime container and broadcast to frontend."""
    settings = get_settings()
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    event_type = body.get("event_type", "log")
    payload = body.get("payload", {})
    if not isinstance(payload, dict):
        payload = {"message": str(payload)}

    session_id = payload.get("session_id")
    task_id = payload.get("task_id")
    project_id = payload.get("project_id") or request.headers.get("x-project-id")

    # If project_id not in payload or header, lookup via session
    if not project_id and session_id:
        sess = db.query(models.AgentSession).filter(models.AgentSession.id == session_id).first()
        if sess:
            project_id = sess.project_id

    # Fallback: resolve project_id via task_id
    if not project_id and task_id:
        t = db.query(models.Task).filter(models.Task.task_id == task_id).first()
        if t and t.project_token:
            project_id = t.project_token
        elif "_" in str(task_id):
            cand = str(task_id).split("_")[0]
            if len(cand) >= 10:
                project_id = cand
        elif "-" in str(task_id):
            parts = str(task_id).rsplit("-", 1)
            if len(parts) == 2 and len(parts[0]) >= 10:
                project_id = parts[0]

    # Record event in database
    if session_id:
        try:
            agent_service.record_event(
                db=db,
                session_id=session_id,
                event_type=event_type,
                payload=payload,
                task_id=task_id,
            )
        except Exception as e:
            logger.warning(f"[AgentCallback] Failed to record event in DB: {e}")

    # Build human-readable live log message
    msg = payload.get("message") or payload.get("label") or payload.get("final_text") or event_type
    import time
    is_success = event_type in ("preview_ready", "session_completed")
    is_error = "fail" in str(event_type).lower() or "error" in str(event_type).lower()
    status_meta = "success" if is_success else ("error" if is_error else None)
    clean_preview_url = payload.get("preview_url") or (f"/app/{project_id}/" if is_success and project_id else None)

    log_entry = {
        "timestamp": payload.get("timestamp") or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "type": "deploy_log",
        "event_type": event_type,
        "content": msg,
        "message": msg,
        "session_id": session_id,
        "task_id": task_id,
        "payload": payload,
        "metadata": {
            "status": status_meta,
            "preview_url": clean_preview_url,
            "event_type": event_type,
            "payload": payload,
        },
    }

    # Store in memory log store
    if project_id:
        if project_id not in _preview_log_store:
            _preview_log_store[project_id] = []
        _preview_log_store[project_id].append(log_entry)
        if len(_preview_log_store[project_id]) > 500:
            _preview_log_store[project_id] = _preview_log_store[project_id][-500:]

        # Also push to agent log store if agent is identified
        agent_id = payload.get("agent_id") or payload.get("agent")
        if agent_id:
            try:
                agent_service.append_agent_log(
                    agent_id=str(agent_id),
                    message=f"[{event_type}] {msg}"[:500],
                    log_type="error" if is_error else ("success" if is_success else "output"),
                    project_token=project_id,
                )
            except Exception:
                pass

        # Broadcast to all live WebSockets listening on this project
        ws_list = _preview_ws_connections.get(project_id, [])
        if ws_list:
            dead_ws = []
            for ws in ws_list:
                try:
                    await ws.send_json(log_entry)
                except Exception:
                    dead_ws.append(ws)
            for d in dead_ws:
                if d in ws_list:
                    ws_list.remove(d)

    return {"status": "ok", "event_type": event_type}


@router.get("/api/v1/sessions/{session_id}")
def get_session_info(session_id: str, db: Session = Depends(get_db)):
    """Fetch complete session details including tasks and events."""
    sess = db.query(models.AgentSession).filter(models.AgentSession.id == session_id).first()
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")

    tasks = (
        db.query(models.AgentTask)
        .filter(models.AgentTask.session_id == session_id)
        .order_by(models.AgentTask.created_at.asc())
        .all()
    )
    events = (
        db.query(models.AgentEvent)
        .filter(models.AgentEvent.session_id == session_id)
        .order_by(models.AgentEvent.created_at.asc())
        .all()
    )

    return {
        "id": sess.id,
        "project_id": sess.project_id,
        "status": sess.status,
        "preview_url": sess.preview_url,
        "preview_port": sess.preview_port,
        "started_at": sess.started_at,
        "last_activity_at": sess.last_activity_at,
        "ended_at": sess.ended_at,
        "tasks": [
            {
                "id": t.id,
                "task_type": t.task_type,
                "description": t.description,
                "status": t.status,
                "model_name": t.model_name,
                "created_at": t.created_at,
            }
            for t in tasks
        ],
        "events": [
            {
                "id": e.id,
                "task_id": e.task_id,
                "event_type": e.event_type,
                "payload": e.payload,
                "created_at": e.created_at,
            }
            for e in events
        ],
    }


@router.get("/api/v1/projects/{project_id}/active-session")
def get_project_active_session(project_id: str, db: Session = Depends(get_db)):
    """Get the latest session and logs for a project."""
    sess = agent_service.get_latest_session_for_project(db, project_id)
    if not sess:
        return {"session": None, "preview": agent_service.get_preview_status(project_id)}

    return {
        "session": {
            "id": sess.id,
            "project_id": sess.project_id,
            "status": sess.status,
            "preview_url": sess.preview_url,
        },
        "preview": agent_service.get_preview_status(project_id),
        "recent_logs": _preview_log_store.get(project_id, [])[-50:],
    }


def _record_callback_outcome(
    project_token: str,
    session_id: Optional[str],
    task_id: Optional[str],
    event_type: str,
    payload: Dict[str, Any],
) -> None:
    """Lightweight coordination hook: reflect callback events into the execution tracker.

    This is intentionally defensive. If it fails, callback processing still succeeds.
    """
    if not project_token:
        return

    agent_id = payload.get("agent_id") or payload.get("agent") or (session_id or "unknown")
    message = payload.get("message") or payload.get("final_text") or ""

    completed_events = {"preview_ready", "session_completed", "build_completed", "coding_completed"}
    failed_events = {"session_failed", "build_failed", "coding_failed", "task_failed"}

    if event_type in completed_events:
        from app.services.agents.local_state_manager import publish_task_outcome_to_tracker

        publish_task_outcome_to_tracker(
            project_token=project_token,
            task_id=task_id or "callback-task",
            agent_id=agent_id,
            status="done",
            error_message=None,
            failure_class="unknown",
        )
    elif event_type in failed_events:
        from app.services.agents.local_state_manager import publish_task_outcome_to_tracker

        failure_class = "runtime_error"
        if "build" in event_type:
            failure_class = "build_error"
        elif "code" in event_type or "coding" in event_type:
            failure_class = "generation_error"

        publish_task_outcome_to_tracker(
            project_token=project_token,
            task_id=task_id or "callback-task",
            agent_id=agent_id,
            status="failed",
            error_message=message or f"Callback failure: {event_type}",
            failure_class=failure_class,
        )
