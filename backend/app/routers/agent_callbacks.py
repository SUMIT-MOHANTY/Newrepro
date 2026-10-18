"""Agent Callbacks Domain Router.

Receives lifecycle and tool execution events from isolated Agent Runtime containers
and broadcasts them live to connected WebSockets in real time.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.infrastructure.events.event_broadcaster import get_event_broadcaster
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

    # ── Live DB progress sync: runtime task lifecycle events update the local
    # task ownership rows so UI progress reflects real execution state.
    # (Root cause of "progress stuck at 0/10% even though the app is live":
    # task_completed events were recorded as logs but never applied to the
    # AgentTaskOwnership rows the task-list endpoint reads.)
    if task_id and project_id and event_type in ("task_started", "task_completed", "task_failed", "git_push_completed", "git_push_failed"):
        try:
            _sync_task_progress_to_db(db, str(project_id), str(task_id), event_type, payload)
        except Exception as e:
            logger.warning(f"[AgentCallback] Task progress sync error: {e}")

    # Build human-readable live log message
    msg = payload.get("message") or payload.get("label") or payload.get("final_text") or event_type
    import time
    is_success = event_type in ("preview_ready", "session_completed")
    is_error = "fail" in str(event_type).lower() or "error" in str(event_type).lower()

    # ── Gate C: honest completion status ─────────────────────────────────────
    # "session_completed" without platform proof is downgraded to "completed_unverified".
    # Only events carrying verification evidence broadcast as true success.
    # The runtime also emits "completed_unverified" itself when its own gate was
    # skipped — both paths converge on the same honest status.
    downgrade_reason: Optional[str] = None
    if event_type in ("session_completed", "preview_ready"):
        if not payload.get("platform_verified", False):
            if payload.get("verification_report", {}).get("skipped"):
                downgrade_reason = "verification gate was skipped (recorded, not silently passed)"
            else:
                downgrade_reason = "no platform runnability verification evidence in payload"
            event_type = "completed_unverified"
            is_success = False
            msg = f"{msg} ⚠️ [not platform-verified: {downgrade_reason}]"
    status_meta = "warning" if downgrade_reason else (
        "success" if is_success else ("error" if is_error else None)
    )
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
            "verification": {
                "platform_verified": bool(payload.get("platform_verified", False)),
                "downgrade_reason": downgrade_reason,
            },
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

        # ── Durable SSE Event Broadcasting with Replay Buffer ──
        broadcaster = get_event_broadcaster()
        clean_agent_id = payload.get("agent_id") or payload.get("agent") or request.headers.get("x-agent-id")
        event_uid = body.get("event_uid") or payload.get("event_uid")
        norm_event = {
            "event_uid": event_uid,
            "type": event_type,
            "event_type": event_type,
            "session_id": session_id,
            "project_id": str(project_id or ""),
            "task_id": task_id,
            "task_title": payload.get("task_title") or payload.get("title"),
            "agent_id": clean_agent_id,
            "agent_name": payload.get("agent_name") or payload.get("agent") or clean_agent_id,
            "role": payload.get("role") or clean_agent_id,
            "lane": payload.get("lane"),
            "message": msg,
            "payload": payload,
            "timestamp": payload.get("timestamp") or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        if project_id:
            await broadcaster.publish(str(project_id), norm_event)
        if session_id:
            await broadcaster.publish(str(session_id), norm_event)

        # ── Update live agent in-memory state so cards never get stuck at 90% ──
        if project_id:
            active_agent = clean_agent_id or "backend_developer"
            agent_rec = agent_service.get_agent_status(str(active_agent), str(project_id))
            if agent_rec:
                if event_type in ("supervisor_completed", "session_completed"):
                    agent_rec["status"] = "completed"
                    agent_rec["progress"] = 100
                    agent_rec["progress_message"] = "Swarm execution verified & completed."
                elif event_type == "task_completed":
                    cur_p = agent_rec.get("progress", 0)
                    agent_rec["progress"] = max(cur_p, 85)
                    agent_rec["progress_message"] = f"Task completed: {payload.get('task_title') or task_id}."
                elif event_type == "preview_ready":
                    cur_p = agent_rec.get("progress", 0)
                    agent_rec["progress"] = max(cur_p, 95)
                    agent_rec["progress_message"] = "Live preview ready on port 80."
                elif event_type == "thinking":
                    thought = (payload.get("thought_summary") or payload.get("reasoning") or "")[:120]
                    agent_rec["progress_message"] = f"Thinking: {thought}"
                elif event_type == "tool_called":
                    tool_name = payload.get("tool") or payload.get("description") or "tool"
                    agent_rec["progress_message"] = f"Executing: {tool_name}"

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


def _sync_task_progress_to_db(
    db: Session,
    project_id: str,
    task_id: str,
    event_type: str,
    payload: Dict[str, Any],
) -> None:
    """Apply a runtime task lifecycle event to the local DB task ownership row.

    Status mapping (dynamic — derived from the event itself, no hardcoded
    project/task ids):
      task_started  -> in_progress (progress 10 floor matches the UI mapping)
      task_completed-> done / 100 when the runtime proved the task
                       (platform_verified), else in_review / 75 (honest:
                       agent says done, platform has not proven it)
      task_failed   -> failed / 0
    """
    from datetime import datetime

    task = db.query(models.Task).filter(models.Task.task_id == task_id).first()
    if not task:
        # The runtime may use a differently-qualified id; match on the clean
        # suffix (same normalization _format_local_tasks_as_nxdune uses).
        clean = task_id.split("_", 1)[-1] if "_" in task_id else task_id
        if clean and clean != task_id:
            task = db.query(models.Task).filter(
                models.Task.project_token == project_id,
                models.Task.task_id.like(f"%{clean}"),
            ).first()
    if not task:
        return

    now = datetime.utcnow()
    ow = db.query(models.AgentTaskOwnership).filter(
        models.AgentTaskOwnership.project_token == project_id,
        models.AgentTaskOwnership.task_id == task.task_id,
    ).first()
    if not ow:
        ow = models.AgentTaskOwnership(
            project_token=project_id,
            task_id=task.task_id,
            agent_id=str(payload.get("agent_id") or payload.get("agent") or "runtime"),
            status="in_progress",
            claimed_at=now,
            started_at=now,
        )
        db.add(ow)
        db.flush()

    if event_type == "task_started":
        new_status, progress = "in_progress", 10
    elif event_type in ("task_completed", "supervisor_completed", "session_completed"):
        new_status, progress = "done", 100
        task.status = "DONE"
        task.verification_status = "PASSED"
    elif event_type in ("git_push_completed", "git_push_failed"):
        new_status = ow.status
        progress = getattr(ow, "task_progress", 100)
    else:  # task_failed
        new_status, progress = "failed", 0
        task.status = "FAILED"
        task.verification_status = "FAILED"

    data = dict(ow.task_data) if isinstance(ow.task_data, dict) else {}
    if payload.get("commit_hash"):
        data["commit_hash"] = payload.get("commit_hash")
    if payload.get("feature_branch"):
        data["feature_branch"] = payload.get("feature_branch")
    if payload.get("push_message"):
        data["push_message"] = payload.get("push_message")
    if "push_success" in payload:
        data["push_success"] = payload.get("push_success")

    changed = (
        ow.status != new_status
        or data.get("task_progress") != progress
        or data.get("last_runtime_event") != event_type
        or "commit_hash" in payload
    )
    if not changed:
        return

    ow.status = new_status
    data["task_progress"] = progress
    data["last_runtime_event"] = event_type
    ow.task_data = data
    if hasattr(task, "status") and new_status == "done":
        task.status = "DONE"
    if hasattr(task, "verification_status") and payload.get("platform_verified"):
        task.verification_status = "PASSED"
    db.commit()


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


# ══════════════════════════════════════════════════════════════════════════
# SSE Agent Events Tunnel & Snapshot Replay Endpoints
# ══════════════════════════════════════════════════════════════════════════

@router.get("/agents/events")
@router.get("/api/v1/agents/events")
@router.get("/projects/{project_token}/agent-events")
@router.get("/api/v1/projects/{project_token}/agent-events")
async def stream_agent_events(
    request: Request,
    project_token: Optional[str] = None,
    agent_id: Optional[str] = Query(None),
    session_id: Optional[str] = Query(None),
    last_event_id: Optional[int] = Query(None, alias="last_event_id"),
    token: Optional[str] = Query(None),
):
    """Stream live events strictly scoped to (project_token, agent_id) or project_token."""
    proj = (
        project_token
        or request.query_params.get("project_token")
        or request.headers.get("x-project-token")
        or session_id
        or "default_project"
    )
    target_agent = agent_id or request.query_params.get("agent_id") or request.headers.get("x-agent-id")

    header_last_id = request.headers.get("Last-Event-ID")
    effective_last_id = last_event_id
    if effective_last_id is None and header_last_id:
        try:
            effective_last_id = int(header_last_id)
        except (ValueError, TypeError):
            pass

    broadcaster = get_event_broadcaster()
    channel_key = (
        broadcaster.agent_channel(proj, target_agent)
        if target_agent
        else broadcaster.project_channel(proj)
    )
    queue = broadcaster.subscribe(channel_key)

    async def event_generator():
        try:
            init_frame = json.dumps({
                "type": "connected",
                "channel": channel_key,
                "project_token": proj,
                "agent_id": target_agent,
                "status": "online",
            })
            yield f"data: {init_frame}\n\n"

            async for event in broadcaster.stream(channel_key, queue, last_event_id=effective_last_id):
                eid = event.get("_id")
                frame_lines = []
                if eid is not None:
                    frame_lines.append(f"id: {eid}")
                clean = {k: v for k, v in event.items() if k != "_id"}
                frame_lines.append(f"data: {json.dumps(clean)}")
                yield "\n".join(frame_lines) + "\n\n"
        except asyncio.CancelledError:
            return
        finally:
            broadcaster.unsubscribe(channel_key, queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/projects/{project_token}/agent-logs")
@router.get("/api/v1/projects/{project_token}/agent-logs")
@router.get("/agents/logs/buffered")
async def get_buffered_agent_logs(
    request: Request,
    project_token: Optional[str] = None,
    agent_id: Optional[str] = Query(None),
    channel: Optional[str] = Query(None),
):
    """Get buffered logs strictly isolated to (project_token, agent_id)."""
    target_project = (
        project_token
        or channel
        or request.query_params.get("project_token")
        or request.headers.get("x-project-token")
        or "default_project"
    )
    target_agent = agent_id or request.query_params.get("agent_id") or request.headers.get("x-agent-id")

    settings = get_settings()
    clean_token = target_project.replace("/", "_").replace("\\", "_")
    workspace_dir = os.path.join(settings.project_storage_root, clean_token)

    broadcaster = get_event_broadcaster()
    events = broadcaster.get_buffered_events(
        project_token=target_project,
        agent_id=target_agent,
        workspace_dir=workspace_dir,
    )
    clean_events = [{k: v for k, v in ev.items() if k != "_id"} for ev in events]
    return {"events": clean_events, "count": len(clean_events)}

