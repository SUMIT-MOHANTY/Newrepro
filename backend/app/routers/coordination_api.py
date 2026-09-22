from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from typing import Dict, Any, Optional, List
from pydantic import BaseModel
import asyncio
import json

from agent_coordination_service import coordination_service
from coordinated_agent_wrapper import run_coordinated_agents_langgraph
import agent_communication_service as comm
from database import get_db
from sqlalchemy.orm import Session

router = APIRouter(prefix="/coordination", tags=["Agent Coordination"])


class CoordinationStatusResponse(BaseModel):
    project_token: str
    agents: Dict[str, Dict[str, Any]]
    shared_context: Dict[str, Any]
    file_locks: Dict[str, Dict[str, Any]]
    sync_points: Dict[str, Dict[str, Any]]
    communication_log: List[Dict[str, Any]]
    phase_gates: Dict[str, bool]


class RunCoordinatedAgentsRequest(BaseModel):
    project_token: str
    agents_config: Dict[str, Dict[str, str]]
    task_token: Optional[str] = None


@router.get("/status/{project_token}", response_model=CoordinationStatusResponse)
async def get_coordination_status(project_token: str):
    """Get current coordination status for a project"""
    
    coord_state = await coordination_service.get_coordination_state(project_token)
    
    if not coord_state:
        raise HTTPException(status_code=404, detail="Project coordination not found")
    
    return CoordinationStatusResponse(
        project_token=project_token,
        agents=coord_state.get("agents", {}),
        shared_context=coord_state.get("shared_context", {}),
        file_locks=coord_state.get("file_locks", {}),
        sync_points=coord_state.get("sync_points", {}),
        communication_log=coord_state.get("communication_log", [])[-20:],  # Last 20 events
        phase_gates=coord_state.get("phase_gates", {})
    )


@router.get("/dashboard/{project_token}")
async def get_coordination_dashboard(project_token: str):
    """Get comprehensive coordination dashboard with real-time status"""
    
    coord_state = await coordination_service.get_coordination_state(project_token)
    
    if not coord_state:
        raise HTTPException(status_code=404, detail="Project coordination not found")
    
    agents = coord_state.get("agents", {})
    file_locks = coord_state.get("file_locks", {})
    sync_points = coord_state.get("sync_points", {})
    communication_log = coord_state.get("communication_log", [])
    
    # Analyze agent statuses
    agent_summary = {}
    for agent_id, agent_data in agents.items():
        status = agent_data.get("status", "unknown")
        current_task = agent_data.get("current_task", {})
        last_heartbeat = agent_data.get("last_heartbeat", "")
        
        agent_summary[agent_id] = {
            "status": status,
            "current_task_title": current_task.get("title", "No task") if current_task else "No task",
            "last_heartbeat": last_heartbeat,
            "is_active": status in ["working", "waiting_sync", "requesting_lock"],
            "is_blocked": status in ["blocked", "waiting_dependency", "error"]
        }
    
    # Analyze file locks
    active_locks = {}
    for file_path, lock_info in file_locks.items():
        if lock_info.get("locked", False):
            active_locks[file_path] = {
                "agent_id": lock_info.get("agent_id"),
                "lock_type": lock_info.get("lock_type", "write"),
                "locked_at": lock_info.get("locked_at")
            }
    
    # Analyze sync points
    active_sync_points = {}
    for sync_name, sync_data in sync_points.items():
        if not sync_data.get("completed", False):
            waiting_agents = sync_data.get("waiting_agents", [])
            required_agents = sync_data.get("required_agents", [])
            
            active_sync_points[sync_name] = {
                "waiting_agents": waiting_agents,
                "required_agents": required_agents,
                "progress": f"{len(waiting_agents)}/{len(required_agents)}" if required_agents else "0/0"
            }
    
    # Recent activity (last 10 events)
    recent_activity = []
    for event in communication_log[-10:]:
        event_type = event.get("type", "unknown")
        timestamp = event.get("timestamp", "")
        data = event.get("data", {})
        
        # Format event for display
        if event_type == "agent_status_change":
            agent_id = data.get("agent_id", "unknown")
            new_status = data.get("new_status", "unknown")
            task_info = data.get("task_info", {})
            task_title = task_info.get("title", "") if task_info else ""
            
            recent_activity.append({
                "timestamp": timestamp,
                "type": "status_change",
                "description": f"Agent {agent_id} → {new_status}",
                "details": f"Task: {task_title[:50]}" if task_title else "No task"
            })
            
        elif event_type == "file_lock_request":
            agent_id = data.get("agent_id", "unknown")
            file_path = data.get("file_path", "unknown")
            success = data.get("success", False)
            
            recent_activity.append({
                "timestamp": timestamp,
                "type": "file_lock",
                "description": f"{'✅' if success else '❌'} {agent_id} → {file_path}",
                "details": "Lock granted" if success else "Lock denied"
            })
            
        elif event_type == "sync_point_request":
            agent_id = data.get("agent_id", "unknown")
            sync_name = data.get("sync_name", "unknown")
            status = data.get("status", "waiting")
            
            recent_activity.append({
                "timestamp": timestamp,
                "type": "sync_point",
                "description": f"{agent_id} → {sync_name}",
                "details": f"Status: {status}"
            })
            
        elif event_type == "communication_message":
            from_agent = data.get("from_agent", "unknown")
            to_agent = data.get("to_agent", "all")
            message_type = data.get("message_type", "general")
            
            recent_activity.append({
                "timestamp": timestamp,
                "type": "message",
                "description": f"{from_agent} → {to_agent}",
                "details": f"{message_type}: {str(data.get('message', ''))[:50]}"
            })
    
    return {
        "project_token": project_token,
        "summary": {
            "total_agents": len(agents),
            "active_agents": len([a for a in agent_summary.values() if a["is_active"]]),
            "blocked_agents": len([a for a in agent_summary.values() if a["is_blocked"]]),
            "active_file_locks": len(active_locks),
            "pending_sync_points": len(active_sync_points),
            "total_events": len(communication_log)
        },
        "agents": agent_summary,
        "active_file_locks": active_locks,
        "pending_sync_points": active_sync_points,
        "recent_activity": recent_activity,
        "last_updated": coord_state.get("last_updated", "")
    }


@router.get("/live-log/{project_token}")
async def get_live_coordination_log(project_token: str, limit: int = 50):
    """Get live coordination log with formatted messages for easy reading"""
    
    coord_state = await coordination_service.get_coordination_state(project_token)
    
    if not coord_state:
        raise HTTPException(status_code=404, detail="Project coordination not found")
    
    communication_log = coord_state.get("communication_log", [])
    
    # Format events for easy reading
    formatted_events = []
    for event in communication_log[-limit:]:
        timestamp = event.get("timestamp", "")
        event_type = event.get("type", "unknown")
        data = event.get("data", {})
        
        # Format timestamp for display
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            display_time = dt.strftime("%H:%M:%S")
        except:
            display_time = timestamp[-8:] if len(timestamp) >= 8 else timestamp
        
        agent_id = data.get("agent_id", "unknown")
        project_short = project_token[-8:] if project_token else "unknown"
        
        if event_type == "agent_status_change":
            old_status = data.get("old_status", "unknown")
            new_status = data.get("new_status", "unknown")
            task_info = data.get("task_info", {})
            task_title = task_info.get("title", "No task") if task_info else "No task"
            
            formatted_events.append({
                "timestamp": display_time,
                "icon": "📊",
                "message": f"Agent {agent_id}: {old_status} → {new_status}",
                "details": f"Task: {task_title[:60]}",
                "type": "status_change",
                "agent_id": agent_id
            })
            
        elif event_type == "file_lock_request":
            file_path = data.get("file_path", "unknown")
            lock_type = data.get("lock_type", "write")
            success = data.get("success", False)
            
            formatted_events.append({
                "timestamp": display_time,
                "icon": "🔒" if success else "❌",
                "message": f"File Lock {'GRANTED' if success else 'DENIED'}: {agent_id}",
                "details": f"{file_path} ({lock_type})",
                "type": "file_lock",
                "agent_id": agent_id
            })
            
        elif event_type == "file_lock_release":
            file_path = data.get("file_path", "unknown")
            
            formatted_events.append({
                "timestamp": display_time,
                "icon": "🔓",
                "message": f"File Unlocked: {agent_id}",
                "details": f"Released {file_path}",
                "type": "file_unlock",
                "agent_id": agent_id
            })
            
        elif event_type == "sync_point_request":
            sync_name = data.get("sync_name", "unknown")
            status = data.get("status", "waiting")
            waiting_agents = data.get("waiting_agents", [])
            
            if status == "completed":
                formatted_events.append({
                    "timestamp": display_time,
                    "icon": "🎯",
                    "message": f"Sync Point COMPLETED: {sync_name}",
                    "details": "All agents synchronized",
                    "type": "sync_complete",
                    "agent_id": "system"
                })
            else:
                formatted_events.append({
                    "timestamp": display_time,
                    "icon": "⏳",
                    "message": f"Sync Point WAITING: {agent_id}",
                    "details": f"{sync_name} | Waiting for: {', '.join(waiting_agents)}",
                    "type": "sync_waiting",
                    "agent_id": agent_id
                })
                
        elif event_type == "communication_message":
            from_agent = data.get("from_agent", "unknown")
            to_agent = data.get("to_agent", "all")
            message_type = data.get("message_type", "general")
            message = data.get("message", "")
            
            # Handle message being a dict or string
            if isinstance(message, dict):
                message_text = message.get("message", str(message))
            else:
                message_text = str(message)
            
            target = f"→ {to_agent}" if to_agent != "all" else "→ ALL"
            formatted_events.append({
                "timestamp": display_time,
                "icon": "💬",
                "message": f"Message: {from_agent} {target}",
                "details": f"{message_type}: {message_text[:80]}",
                "type": "message",
                "agent_id": from_agent
            })
            
        elif event_type == "task_progress_update":
            progress = data.get("progress", {})
            task_title = progress.get("task_title", "Unknown task")
            completion = progress.get("completion_percentage", 0)
            
            formatted_events.append({
                "timestamp": display_time,
                "icon": "📈",
                "message": f"Progress Update: {agent_id}",
                "details": f"{task_title[:50]} - {completion}%",
                "type": "progress",
                "agent_id": agent_id
            })
            
        elif event_type == "conflict_detected":
            conflict_type = data.get("conflict_type", "unknown")
            details = data.get("details", "")
            
            formatted_events.append({
                "timestamp": display_time,
                "icon": "⚠️",
                "message": f"Conflict Detected: {conflict_type}",
                "details": details[:80],
                "type": "conflict",
                "agent_id": agent_id
            })
            
        elif event_type == "dependency_resolved":
            dependency = data.get("dependency", "unknown")
            
            formatted_events.append({
                "timestamp": display_time,
                "icon": "✅",
                "message": f"Dependency Resolved: {agent_id}",
                "details": dependency,
                "type": "dependency",
                "agent_id": agent_id
            })
        else:
            # Generic event format
            formatted_events.append({
                "timestamp": display_time,
                "icon": "ℹ️",
                "message": f"{event_type}: {agent_id}",
                "details": str(data)[:80],
                "type": "generic",
                "agent_id": agent_id
            })
    
    return {
        "project_token": project_token,
        "project_short": project_short,
        "events": formatted_events,
        "total_events": len(communication_log),
        "showing": len(formatted_events)
    }


@router.get("/agent/{project_token}/{agent_id}")
async def get_agent_coordination_view(project_token: str, agent_id: str):
    """Get coordination state from specific agent's perspective"""
    
    agent_view = await coordination_service.get_agent_view(project_token, agent_id)
    
    if not agent_view:
        raise HTTPException(status_code=404, detail="Agent coordination view not found")
    
    return agent_view


@router.post("/run-coordinated")
async def run_coordinated_agents(request: RunCoordinatedAgentsRequest):
    """Run multiple agents with full coordination"""
    
    try:
        result = await run_coordinated_agents_langgraph(
            project_token=request.project_token,
            agents_config=request.agents_config,
            task_token=request.task_token
        )
        
        return {
            "success": True,
            "result": result
        }
        
    except Exception as exc:
        raise HTTPException(
            status_code=500, 
            detail=f"Coordinated agent execution failed: {str(exc)}"
        )


@router.post("/send-message/{project_token}")
async def send_agent_message(
    project_token: str,
    from_agent: str,
    to_agent: Optional[str] = None,
    message: Dict[str, Any] = {}
):
    """Send message between agents"""
    
    success = await coordination_service.send_agent_message(
        project_token, from_agent, to_agent, message
    )
    
    if not success:
        raise HTTPException(status_code=400, detail="Failed to send message")
    
    return {"success": True, "message": "Message sent"}


@router.post("/sync-point/{project_token}")
async def request_sync_point(
    project_token: str,
    agent_id: str,
    sync_point_name: str,
    data: Optional[Dict[str, Any]] = None
):
    """Request to reach a synchronization point"""
    
    result = await coordination_service.request_sync_point(
        project_token, agent_id, sync_point_name, data
    )
    
    return result


@router.post("/file-lock/{project_token}")
async def request_file_lock(
    project_token: str,
    agent_id: str,
    file_path: str,
    lock_type: str = "write"
):
    """Request file lock"""
    
    result = await coordination_service.request_file_lock(
        project_token, agent_id, file_path, lock_type
    )
    
    return result


@router.delete("/file-lock/{project_token}")
async def release_file_lock(
    project_token: str,
    agent_id: str,
    file_path: str
):
    """Release file lock"""
    
    success = await coordination_service.release_file_lock(
        project_token, agent_id, file_path
    )
    
    return {"success": success}


@router.get("/communication-log/{project_token}")
async def get_communication_log(project_token: str, limit: int = 50):
    """Get communication log for a project"""
    
    coord_state = await coordination_service.get_coordination_state(project_token)
    
    if not coord_state:
        raise HTTPException(status_code=404, detail="Project coordination not found")
    
    comm_log = coord_state.get("communication_log", [])
    
    return {
        "project_token": project_token,
        "communication_log": comm_log[-limit:],
        "total_events": len(comm_log)
    }


# ═══════════════════════════════════════════════════════════════════════════
# AGENT COMMUNICATION ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════

class SendMessageRequest(BaseModel):
    from_agent: str
    message: str
    msg_type: str = "INFO"  # INFO | BLOCKED | OFFERING | READY | HELP_REQUEST | RESPONSE | RESOLVED
    to_agent: Optional[str] = None
    related_task_id: Optional[str] = None
    payload: Optional[Dict[str, Any]] = None


class ResolveBlockerRequest(BaseModel):
    message_id: int
    resolved_by: str


class BlockedRequest(BaseModel):
    from_agent: str
    reason: str
    related_task_id: Optional[str] = None
    needs: Optional[str] = None  # e.g. "Loan model from banking module"


class ReadyRequest(BaseModel):
    from_agent: str
    what_is_ready: str
    related_task_id: Optional[str] = None


@router.post("/chat/{project_token}/send")
async def send_agent_chat_message(
    project_token: str,
    req: SendMessageRequest,
    db: Session = Depends(get_db),
):
    """Send a message from one agent to others (or broadcast)."""
    msg = await comm.send_message(
        db=db,
        project_token=project_token,
        from_agent=req.from_agent,
        message=req.message,
        msg_type=req.msg_type,
        to_agent=req.to_agent,
        related_task_id=req.related_task_id,
        payload=req.payload,
    )
    return {"status": "sent", "message_id": msg.id}


@router.post("/chat/{project_token}/blocked")
async def agent_blocked(
    project_token: str,
    req: BlockedRequest,
    db: Session = Depends(get_db),
):
    """Agent reports it is blocked and broadcasts what it needs."""
    msg = await comm.broadcast_blocked(
        db=db,
        project_token=project_token,
        from_agent=req.from_agent,
        reason=req.reason,
        related_task_id=req.related_task_id,
        needs=req.needs,
    )
    return {"status": "broadcast", "message_id": msg.id}


@router.post("/chat/{project_token}/ready")
async def agent_ready(
    project_token: str,
    req: ReadyRequest,
    db: Session = Depends(get_db),
):
    """Agent signals it finished something and auto-resolves waiting blockers."""
    msg = await comm.broadcast_ready(
        db=db,
        project_token=project_token,
        from_agent=req.from_agent,
        what_is_ready=req.what_is_ready,
        related_task_id=req.related_task_id,
    )
    resolved = await comm.check_and_auto_resolve(
        db=db,
        project_token=project_token,
        from_agent=req.from_agent,
        what_was_built=req.what_is_ready,
    )
    return {"status": "broadcast", "message_id": msg.id, "auto_resolved_blockers": resolved}


@router.post("/chat/{project_token}/resolve/{message_id}")
async def resolve_blocker(
    project_token: str,
    message_id: int,
    req: ResolveBlockerRequest,
    db: Session = Depends(get_db),
):
    """Mark a BLOCKED message as resolved."""
    msg = await comm.resolve_blocker(db=db, project_token=project_token, message_id=message_id, resolved_by=req.resolved_by)
    if not msg:
        raise HTTPException(status_code=404, detail="Message not found")
    return {"status": "resolved", "message_id": msg.id}


@router.get("/chat/{project_token}/messages")
async def get_chat_messages(
    project_token: str,
    limit: int = 100,
    msg_type: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Get all messages for a project (newest first)."""
    messages = comm.get_messages(db, project_token, limit=limit, msg_type=msg_type)
    return {"messages": messages, "count": len(messages)}


@router.get("/chat/{project_token}/blockers")
async def get_active_blockers(
    project_token: str,
    db: Session = Depends(get_db),
):
    """Get all unresolved BLOCKED messages."""
    blockers = comm.get_active_blockers(db, project_token)
    return {"blockers": blockers, "count": len(blockers)}


@router.get("/chat/{project_token}/stream")
async def stream_chat(project_token: str, db: Session = Depends(get_db)):
    """
    Server-Sent Events stream — frontend subscribes here to get
    real-time agent messages without polling.
    """
    async def event_generator():
        q = await comm.subscribe(project_token)
        try:
            # Send last 20 messages as initial state
            history = comm.get_messages(db, project_token, limit=20)
            for msg in reversed(history):
                yield f"data: {json.dumps(msg)}\n\n"

            while True:
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=30.0)
                    yield f"data: {json.dumps(msg)}\n\n"
                except asyncio.TimeoutError:
                    yield "data: {\"_ping\": true}\n\n"
        finally:
            await comm.unsubscribe(project_token, q)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ── Contract Store endpoints ──────────────────────────────────────────────────
import agent_contract_store as _cs


@router.get("/contracts/{project_token}/apis")
async def get_api_contracts(project_token: str):
    """Get all published API endpoint contracts for a project."""
    contracts = await _cs.get_api_contracts(project_token)
    return {"contracts": contracts, "count": len(contracts)}


@router.get("/contracts/{project_token}/models")
async def get_registered_models(project_token: str):
    """Get all registered DB models for a project."""
    models = _cs.get_registered_models(project_token)
    return {"models": models, "count": len(models)}


@router.get("/contracts/{project_token}/locks")
async def get_active_locks(project_token: str):
    """Get all active file locks for a project."""
    locks = _cs.get_active_locks(project_token)
    return {"locks": locks, "count": len(locks)}


@router.get("/contracts/{project_token}/health")
async def get_agent_health(project_token: str):
    """Get heartbeat status for all agents in a project."""
    from agent_contract_store import _heartbeats, HEARTBEAT_TIMEOUT
    import time
    beats = _heartbeats.get(project_token, {})
    now = time.time()
    health = {
        aid: {
            "last_heartbeat": ts,
            "seconds_ago": round(now - ts, 1),
            "alive": (now - ts) <= HEARTBEAT_TIMEOUT,
        }
        for aid, ts in beats.items()
    }
    crashed = _cs.get_crashed_agents(project_token)
    return {"agents": health, "crashed": crashed}
