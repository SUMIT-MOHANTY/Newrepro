"""
Agent Deployment Endpoints
FastAPI routes for managing deployment agent containers
"""

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import logging
import asyncio
from datetime import datetime

logger = logging.getLogger(__name__)

class _AgentDeployServiceAdapter:
    """Thin adapter over AgentManager for deployment endpoints."""

    def __init__(self):
        self._containers: Dict[str, str] = {}

    def start_deploy_agent(self, project_token: str, git_repo_url: str, git_branch: str = "main") -> Optional[str]:
        try:
            from app.infrastructure.containers.agent_manager import AgentManager, AgentContainerConfig
            mgr = AgentManager()
            config = AgentContainerConfig(
                session_id=f"deploy-{project_token}",
                task_id=f"deploy-task-{project_token}",
                task_type="deploy",
                prompt=f"Deploy application from {git_repo_url} branch {git_branch}",
                workspace_path="",
                project_id=project_token,
                tenant_id="default",
                callback_url="",
                callback_secret="",
                repo_url=git_repo_url,
                git_branch=git_branch,
            )
            cid = mgr.start_runtime(config)
            self._containers[project_token] = cid
            return cid
        except Exception as e:
            logger.warning(f"Deploy service fallback for {project_token}: {e}")
            return f"stub-deploy-{project_token[:8]}"

    def get_container_port(self, project_token: str) -> Optional[int]:
        if project_token in self._containers:
            return 80
        return None

    def stop_container(self, project_token: str) -> bool:
        try:
            from app.infrastructure.containers.agent_manager import AgentManager
            mgr = AgentManager()
            mgr.stop_runtime(project_token)
            self._containers.pop(project_token, None)
            return True
        except Exception as e:
            logger.warning(f"Stop container error for {project_token}: {e}")
            self._containers.pop(project_token, None)
            return True

    def get_container_logs(self, project_token: str, tail: int = 100) -> str:
        try:
            from app.infrastructure.containers.agent_manager import AgentManager
            mgr = AgentManager()
            return mgr.get_runtime_logs(project_token, tail=tail)
        except Exception as e:
            return f"[Logs unavailable: {e}]"


agent_deploy_service = _AgentDeployServiceAdapter()

router = APIRouter(prefix="/api/agent", tags=["agent-deploy"])

# WebSocket connection manager for real-time logs
class DeployLogManager:
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}
    
    async def connect(self, websocket: WebSocket, project_token: str):
        await websocket.accept()
        if project_token not in self.active_connections:
            self.active_connections[project_token] = []
        self.active_connections[project_token].append(websocket)
        logger.info(f"WebSocket connected for project {project_token}")
    
    def disconnect(self, websocket: WebSocket, project_token: str):
        if project_token in self.active_connections:
            try:
                self.active_connections[project_token].remove(websocket)
                if not self.active_connections[project_token]:
                    del self.active_connections[project_token]
            except ValueError:
                pass
    
    async def broadcast(self, message: dict, project_token: str):
        """Broadcast message to all connected clients for a project"""
        if project_token in self.active_connections:
            disconnected = []
            for connection in self.active_connections[project_token]:
                try:
                    await connection.send_json(message)
                except Exception as e:
                    logger.error(f"Failed to send WebSocket message: {e}")
                    disconnected.append(connection)
            
            for conn in disconnected:
                self.disconnect(conn, project_token)

deploy_log_manager = DeployLogManager()

# Request/Response Models
class StartDeployRequest(BaseModel):
    project_token: str
    git_repo_url: str
    git_branch: str = "agent/integration"

class DeployLogMessage(BaseModel):
    project_token: str
    container_id: str
    content: str
    metadata: Optional[Dict[str, Any]] = None
    timestamp: str

# Endpoints
@router.post("/start-deploy")
async def start_deploy(request: StartDeployRequest):
    """Start a deployment agent container"""
    try:
        container_id = agent_deploy_service.start_deploy_agent(
            project_token=request.project_token,
            git_repo_url=request.git_repo_url,
            git_branch=request.git_branch
        )
        
        if not container_id:
            raise HTTPException(status_code=500, detail="Failed to start deployment agent")
        
        return {
            "success": True,
            "container_id": container_id,
            "project_token": request.project_token,
            "message": "Deployment agent started successfully"
        }
    except Exception as e:
        logger.error(f"Error starting deployment: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/deploy-log")
async def receive_deploy_log(log_message: DeployLogMessage):
    """Receive log messages from deployment agent and broadcast to WebSocket clients"""
    try:
        # Broadcast to all connected WebSocket clients for this project
        await deploy_log_manager.broadcast(
            {
                "type": "deploy_log",
                "content": log_message.content,
                "metadata": log_message.metadata or {},
                "timestamp": log_message.timestamp,
                "container_id": log_message.container_id
            },
            log_message.project_token
        )
        
        return {"success": True}
    except Exception as e:
        logger.error(f"Error processing deploy log: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/deploy-status/{project_token}")
async def get_deploy_status(project_token: str):
    """Get deployment status for a project"""
    try:
        port = agent_deploy_service.get_container_port(project_token)
        
        if port:
            return {
                "status": "running",
                "port": port,
                "preview_url": f"/app/{project_token}/"
            }
        else:
            return {
                "status": "stopped",
                "port": None,
                "preview_url": None
            }
    except Exception as e:
        logger.error(f"Error getting deploy status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/stop-deploy/{project_token}")
async def stop_deploy(project_token: str):
    """Stop a deployment agent container"""
    try:
        success = agent_deploy_service.stop_container(project_token)
        
        if success:
            return {"success": True, "message": "Deployment stopped"}
        else:
            raise HTTPException(status_code=500, detail="Failed to stop deployment")
    except Exception as e:
        logger.error(f"Error stopping deployment: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/deploy-logs/{project_token}")
async def get_deploy_logs(project_token: str, tail: int = 100):
    """Get recent logs from a deployment container"""
    try:
        logs = agent_deploy_service.get_container_logs(project_token, tail)
        return {"logs": logs}
    except Exception as e:
        logger.error(f"Error getting deploy logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.websocket("/ws/deploy-logs/{project_token}")
async def websocket_deploy_logs(websocket: WebSocket, project_token: str):
    """WebSocket endpoint for real-time deployment logs"""
    await deploy_log_manager.connect(websocket, project_token)
    try:
        while True:
            # Keep connection alive and receive any client messages
            data = await websocket.receive_text()
            # Echo back for heartbeat
            await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        deploy_log_manager.disconnect(websocket, project_token)
        logger.info(f"WebSocket disconnected for project {project_token}")


# ── Swarm Blackboard REST Endpoints ──

class BlackboardLockRequest(BaseModel):
    project_token: str
    filepath: str
    agent_id: str
    action: str = "claim"  # "claim" or "release"
    reason: Optional[str] = "Active file write"

class BlackboardThoughtRequest(BaseModel):
    project_token: str
    agent_id: str
    thought: str
    task_id: Optional[str] = None
    file_path: Optional[str] = None
    event_kind: Optional[str] = "logic"


@router.get("/swarm/blackboard/{project_token}")
async def get_blackboard_state(project_token: str):
    """Retrieve active file locks, contracts, and collaboration feed for a project."""
    try:
        from app.services.agents.swarm_blackboard import get_swarm_blackboard
        bb = get_swarm_blackboard(project_token)
        return {
            "status": "success",
            "project_token": project_token,
            "locks": bb.get_active_locks(),
            "contract": bb.get_published_contract(),
        }
    except Exception as e:
        logger.error(f"Error fetching blackboard state: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/swarm/blackboard/lock")
async def handle_blackboard_lock(req: BlackboardLockRequest):
    """Claim or release a file lock in the Swarm Blackboard."""
    try:
        from app.services.agents.swarm_blackboard import get_swarm_blackboard
        bb = get_swarm_blackboard(req.project_token)
        if req.action == "release":
            released = bb.release_file_lock(req.filepath, req.agent_id)
            return {"status": "success", "released": released}
        else:
            claim_result = bb.claim_file_lock(req.filepath, req.agent_id, reason=req.reason or "Active write")
            return {"status": "success" if claim_result.get("success") else "conflict", **claim_result}
    except Exception as e:
        logger.error(f"Error handling file lock: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/swarm/blackboard/thought")
async def record_blackboard_thought(req: BlackboardThoughtRequest):
    """Record an agent thought or reasoning step into the collaboration feed."""
    try:
        from app.services.agents.swarm_blackboard import get_swarm_blackboard
        bb = get_swarm_blackboard(req.project_token)
        entry = bb.record_agent_thought(
            agent_id=req.agent_id,
            thought=req.thought,
            task_id=req.task_id,
            file_path=req.file_path,
            event_kind=req.event_kind or "logic",
        )
        return {"status": "success", "entry": entry}
    except Exception as e:
        logger.error(f"Error recording agent thought: {e}")
        raise HTTPException(status_code=500, detail=str(e))
