import asyncio
import logging
from typing import Dict, List, Any, Optional, Set
from datetime import datetime, timedelta
from enum import Enum
import json

logger = logging.getLogger(__name__)

# Set up detailed coordination logging
coordination_logger = logging.getLogger("coordination")
coordination_logger.setLevel(logging.INFO)

# Create console handler for coordination events
if not coordination_logger.handlers:
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    formatter = logging.Formatter(
        '🤖 [COORDINATION] %(asctime)s - %(levelname)s - %(message)s',
        datefmt='%H:%M:%S'
    )
    console_handler.setFormatter(formatter)
    coordination_logger.addHandler(console_handler)
    coordination_logger.propagate = False


class CoordinationEventType(Enum):
    AGENT_STATUS_CHANGE = "agent_status_change"
    TASK_PROGRESS_UPDATE = "task_progress_update"
    FILE_LOCK_REQUEST = "file_lock_request"
    FILE_LOCK_RELEASE = "file_lock_release"
    SYNC_POINT_REQUEST = "sync_point_request"
    COMMUNICATION_MESSAGE = "communication_message"
    DEPENDENCY_RESOLVED = "dependency_resolved"
    CONFLICT_DETECTED = "conflict_detected"


class AgentCoordinationService:
    """Service for coordinating multiple agents working on the same project"""
    
    def __init__(self):
        self.coordination_state = {}
        self.event_subscribers = {}
        self.coordination_locks = {}
        
    async def initialize_project_coordination(
        self, 
        project_token: str, 
        agents_config: Dict[str, Any],
        master_plan: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Initialize coordination state for a project"""
        
        coordination_state = {
            "project_token": project_token,
            "agents": {
                agent_id: {
                    "status": "idle",
                    "current_task": None,
                    "progress": 0,
                    "last_heartbeat": datetime.utcnow().isoformat(),
                    "capabilities": config.get("capabilities", []),
                    "file_locks": [],
                    "dependencies_waiting": [],
                    "sync_points_waiting": []
                }
                for agent_id, config in agents_config.items()
            },
            "shared_context": {
                "master_plan": master_plan,
                "project_architecture": {},
                "coding_standards": {},
                "file_structure": {},
                "dependencies": {},
                "integration_points": [],
                "last_updated": datetime.utcnow().isoformat()
            },
            "file_locks": {},  # file_path -> {"agent_id": str, "locked_at": str, "lock_type": str}
            "task_dependencies": {},  # task_id -> [dependent_task_ids]
            "sync_points": {
                "architecture_review": {
                    "required_agents": [],
                    "completed_agents": [],
                    "status": "pending",
                    "data": {}
                },
                "integration_checkpoint": {
                    "required_agents": [],
                    "completed_agents": [],
                    "status": "pending", 
                    "data": {}
                },
                "testing_gate": {
                    "required_agents": [],
                    "completed_agents": [],
                    "status": "pending",
                    "data": {}
                },
                "deployment_ready": {
                    "required_agents": [],
                    "completed_agents": [],
                    "status": "pending",
                    "data": {}
                }
            },
            "communication_log": [],
            "conflict_resolution": [],
            "phase_gates": {
                "planning": False,
                "development": False,
                "integration": False,
                "testing": False,
                "deployment": False
            }
        }
        
        self.coordination_state[project_token] = coordination_state
        return coordination_state
    
    async def update_agent_status(
        self, 
        project_token: str, 
        agent_id: str, 
        status: str,
        task_info: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Update agent status and notify other agents"""
        
        if project_token not in self.coordination_state:
            return False
            
        state = self.coordination_state[project_token]
        
        if agent_id not in state["agents"]:
            return False
            
        # Update agent status
        agent_state = state["agents"][agent_id]
        old_status = agent_state["status"]
        agent_state["status"] = status
        agent_state["last_heartbeat"] = datetime.utcnow().isoformat()
        
        if task_info:
            agent_state["current_task"] = task_info
            
        # Log the status change
        await self._log_coordination_event(
            project_token,
            CoordinationEventType.AGENT_STATUS_CHANGE,
            {
                "agent_id": agent_id,
                "old_status": old_status,
                "new_status": status,
                "task_info": task_info
            }
        )
        
        # Notify other agents of status change
        await self._broadcast_to_agents(
            project_token,
            {
                "type": "agent_status_update",
                "agent_id": agent_id,
                "status": status,
                "timestamp": datetime.utcnow().isoformat()
            },
            exclude_agent=agent_id
        )
        
        # Check if this status change affects any waiting dependencies
        await self._check_dependency_resolution(project_token, agent_id, status)
        
        return True
    
    async def request_file_lock(
        self, 
        project_token: str, 
        agent_id: str, 
        file_path: str,
        lock_type: str = "write"
    ) -> Dict[str, Any]:
        """Request exclusive access to a file"""
        
        if project_token not in self.coordination_state:
            return {"success": False, "error": "Project not found"}
            
        state = self.coordination_state[project_token]
        
        # Check if file is already locked
        if file_path in state["file_locks"]:
            existing_lock = state["file_locks"][file_path]
            if existing_lock["agent_id"] != agent_id:
                # File is locked by another agent
                return {
                    "success": False,
                    "error": "File locked by another agent",
                    "locked_by": existing_lock["agent_id"],
                    "locked_at": existing_lock["locked_at"]
                }
        
        # Grant the lock
        state["file_locks"][file_path] = {
            "agent_id": agent_id,
            "locked_at": datetime.utcnow().isoformat(),
            "lock_type": lock_type
        }
        
        # Update agent's lock list
        agent_locks = state["agents"][agent_id]["file_locks"]
        if file_path not in agent_locks:
            agent_locks.append(file_path)
        
        await self._log_coordination_event(
            project_token,
            CoordinationEventType.FILE_LOCK_REQUEST,
            {
                "agent_id": agent_id,
                "file_path": file_path,
                "lock_type": lock_type,
                "granted": True
            }
        )
        
        return {"success": True, "lock_granted": True}
    
    async def release_file_lock(
        self, 
        project_token: str, 
        agent_id: str, 
        file_path: str
    ) -> bool:
        """Release file lock"""
        
        if project_token not in self.coordination_state:
            return False
            
        state = self.coordination_state[project_token]
        
        # Check if agent owns the lock
        if file_path in state["file_locks"]:
            lock_info = state["file_locks"][file_path]
            if lock_info["agent_id"] == agent_id:
                # Remove the lock
                del state["file_locks"][file_path]
                
                # Remove from agent's lock list
                agent_locks = state["agents"][agent_id]["file_locks"]
                if file_path in agent_locks:
                    agent_locks.remove(file_path)
                
                await self._log_coordination_event(
                    project_token,
                    CoordinationEventType.FILE_LOCK_RELEASE,
                    {
                        "agent_id": agent_id,
                        "file_path": file_path
                    }
                )
                
                return True
        
        return False
    
    async def update_shared_context(
        self, 
        project_token: str, 
        agent_id: str, 
        context_updates: Dict[str, Any]
    ) -> bool:
        """Update shared project context"""
        
        if project_token not in self.coordination_state:
            return False
            
        state = self.coordination_state[project_token]
        shared_context = state["shared_context"]
        
        # Merge updates into shared context
        for key, value in context_updates.items():
            if key in shared_context:
                if isinstance(shared_context[key], dict) and isinstance(value, dict):
                    shared_context[key].update(value)
                else:
                    shared_context[key] = value
            else:
                shared_context[key] = value
        
        shared_context["last_updated"] = datetime.utcnow().isoformat()
        shared_context["last_updated_by"] = agent_id
        
        # Notify other agents of context update
        await self._broadcast_to_agents(
            project_token,
            {
                "type": "shared_context_update",
                "updated_by": agent_id,
                "updates": context_updates,
                "timestamp": datetime.utcnow().isoformat()
            },
            exclude_agent=agent_id
        )
        
        return True
    
    async def request_sync_point(
        self, 
        project_token: str, 
        agent_id: str, 
        sync_point_name: str,
        data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Request to reach a synchronization point"""
        
        if project_token not in self.coordination_state:
            return {"success": False, "error": "Project not found"}
            
        state = self.coordination_state[project_token]
        
        if sync_point_name not in state["sync_points"]:
            return {"success": False, "error": "Unknown sync point"}
        
        sync_point = state["sync_points"][sync_point_name]
        
        # Add agent to completed list if not already there
        if agent_id not in sync_point["completed_agents"]:
            sync_point["completed_agents"].append(agent_id)
        
        # Store agent's data for this sync point
        if data:
            sync_point["data"][agent_id] = data
        
        await self._log_coordination_event(
            project_token,
            CoordinationEventType.SYNC_POINT_REQUEST,
            {
                "agent_id": agent_id,
                "sync_point": sync_point_name,
                "data": data
            }
        )
        
        # Check if all required agents have reached this sync point
        required_agents = set(sync_point["required_agents"])
        completed_agents = set(sync_point["completed_agents"])
        
        if required_agents.issubset(completed_agents):
            # All required agents have reached this sync point
            sync_point["status"] = "completed"
            
            # Notify all agents that sync point is complete
            await self._broadcast_to_agents(
                project_token,
                {
                    "type": "sync_point_completed",
                    "sync_point": sync_point_name,
                    "data": sync_point["data"],
                    "timestamp": datetime.utcnow().isoformat()
                }
            )
            
            return {"success": True, "sync_completed": True, "data": sync_point["data"]}
        else:
            # Still waiting for other agents
            waiting_for = required_agents - completed_agents
            return {
                "success": True, 
                "sync_completed": False, 
                "waiting_for": list(waiting_for)
            }
    
    async def send_agent_message(
        self, 
        project_token: str, 
        from_agent: str, 
        to_agent: Optional[str], 
        message: Dict[str, Any]
    ) -> bool:
        """Send message between agents"""
        
        if project_token not in self.coordination_state:
            return False
        
        message_data = {
            "from_agent": from_agent,
            "to_agent": to_agent,  # None means broadcast
            "message": message,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        await self._log_coordination_event(
            project_token,
            CoordinationEventType.COMMUNICATION_MESSAGE,
            message_data
        )
        
        # Deliver message
        if to_agent:
            # Direct message
            await self._send_to_agent(project_token, to_agent, {
                "type": "agent_message",
                **message_data
            })
        else:
            # Broadcast message
            await self._broadcast_to_agents(
                project_token,
                {
                    "type": "agent_message",
                    **message_data
                },
                exclude_agent=from_agent
            )
        
        return True
    
    async def get_coordination_state(self, project_token: str) -> Optional[Dict[str, Any]]:
        """Get current coordination state for a project"""
        return self.coordination_state.get(project_token)
    
    async def get_agent_view(self, project_token: str, agent_id: str) -> Optional[Dict[str, Any]]:
        """Get coordination state from specific agent's perspective"""
        
        if project_token not in self.coordination_state:
            return None
            
        state = self.coordination_state[project_token]
        
        if agent_id not in state["agents"]:
            return None
        
        # Return filtered view for this agent
        return {
            "project_token": project_token,
            "agent_id": agent_id,
            "my_status": state["agents"][agent_id],
            "other_agents": {
                aid: {
                    "status": info["status"],
                    "progress": info["progress"],
                    "last_heartbeat": info["last_heartbeat"]
                }
                for aid, info in state["agents"].items() 
                if aid != agent_id
            },
            "shared_context": state["shared_context"],
            "my_file_locks": state["agents"][agent_id]["file_locks"],
            "available_files": [
                path for path, lock in state["file_locks"].items()
                if lock["agent_id"] != agent_id
            ],
            "sync_points": state["sync_points"],
            "recent_communications": state["communication_log"][-10:],  # Last 10 messages
            "phase_gates": state["phase_gates"]
        }
    
    # Private helper methods
    
    async def _log_coordination_event(
        self, 
        project_token: str, 
        event_type: CoordinationEventType, 
        data: Dict[str, Any]
    ):
        """Log coordination event with detailed console output"""
        
        if project_token not in self.coordination_state:
            return
            
        state = self.coordination_state[project_token]
        
        event = {
            "timestamp": datetime.utcnow().isoformat(),
            "type": event_type.value,
            "data": data
        }
        
        state["communication_log"].append(event)
        
        # Keep only last 1000 events to prevent memory bloat
        if len(state["communication_log"]) > 1000:
            state["communication_log"] = state["communication_log"][-1000:]
            
        # Enhanced console logging for different event types
        agent_id = data.get("agent_id", "unknown")
        project_short = project_token[-8:] if project_token else "unknown"
        
        if event_type == CoordinationEventType.AGENT_STATUS_CHANGE:
            old_status = data.get("old_status", "unknown")
            new_status = data.get("new_status", "unknown")
            task_info = data.get("task_info", {})
            task_title = task_info.get("title", "No task") if task_info else "No task"
            
            coordination_logger.info(
                f"📊 Agent {agent_id} [{project_short}]: {old_status} → {new_status} | Task: {task_title[:50]}"
            )
            
        elif event_type == CoordinationEventType.FILE_LOCK_REQUEST:
            file_path = data.get("file_path", "unknown")
            lock_type = data.get("lock_type", "write")
            success = data.get("success", False)
            status = "✅ GRANTED" if success else "❌ DENIED"
            
            coordination_logger.info(
                f"🔒 File Lock {status} [{project_short}]: {agent_id} → {file_path} ({lock_type})"
            )
            
        elif event_type == CoordinationEventType.FILE_LOCK_RELEASE:
            file_path = data.get("file_path", "unknown")
            
            coordination_logger.info(
                f"🔓 File Unlocked [{project_short}]: {agent_id} released {file_path}"
            )
            
        elif event_type == CoordinationEventType.SYNC_POINT_REQUEST:
            sync_name = data.get("sync_name", "unknown")
            status = data.get("status", "waiting")
            waiting_agents = data.get("waiting_agents", [])
            
            if status == "completed":
                coordination_logger.info(
                    f"🎯 Sync Point COMPLETED [{project_short}]: {sync_name} - All agents synchronized"
                )
            else:
                coordination_logger.info(
                    f"⏳ Sync Point WAITING [{project_short}]: {agent_id} at {sync_name} | Waiting for: {waiting_agents}"
                )
                
        elif event_type == CoordinationEventType.COMMUNICATION_MESSAGE:
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
            coordination_logger.info(
                f"💬 Message [{project_short}]: {from_agent} {target} | {message_type}: {message_text[:100]}"
            )
            
        elif event_type == CoordinationEventType.TASK_PROGRESS_UPDATE:
            progress = data.get("progress", {})
            task_title = progress.get("task_title", "Unknown task")
            completion = progress.get("completion_percentage", 0)
            
            coordination_logger.info(
                f"📈 Progress [{project_short}]: {agent_id} | {task_title[:40]} - {completion}%"
            )
            
        elif event_type == CoordinationEventType.CONFLICT_DETECTED:
            conflict_type = data.get("conflict_type", "unknown")
            details = data.get("details", "")
            
            coordination_logger.warning(
                f"⚠️ Conflict Detected [{project_short}]: {conflict_type} | {details[:100]}"
            )
            
        elif event_type == CoordinationEventType.DEPENDENCY_RESOLVED:
            dependency = data.get("dependency", "unknown")
            
            coordination_logger.info(
                f"✅ Dependency Resolved [{project_short}]: {agent_id} | {dependency}"
            )
    
    async def _broadcast_to_agents(
        self, 
        project_token: str, 
        message: Dict[str, Any],
        exclude_agent: Optional[str] = None
    ):
        """Broadcast message to all agents in project"""
        
        if project_token not in self.coordination_state:
            return
            
        state = self.coordination_state[project_token]
        
        for agent_id in state["agents"]:
            if agent_id != exclude_agent:
                await self._send_to_agent(project_token, agent_id, message)
    
    async def _send_to_agent(self, project_token: str, agent_id: str, message: Dict[str, Any]):
        """Send message to specific agent"""
        # This would integrate with your agent communication system
        # For now, we'll just log it
        logger.info(f"Message to {agent_id} in {project_token}: {message}")
    
    async def _check_dependency_resolution(
        self, 
        project_token: str, 
        agent_id: str, 
        new_status: str
    ):
        """Check if agent status change resolves any dependencies"""
        
        if project_token not in self.coordination_state:
            return
            
        state = self.coordination_state[project_token]
        
        # Check if any agents were waiting for this agent
        for other_agent_id, agent_info in state["agents"].items():
            if other_agent_id != agent_id:
                dependencies_waiting = agent_info["dependencies_waiting"]
                if agent_id in dependencies_waiting and new_status == "completed":
                    dependencies_waiting.remove(agent_id)
                    
                    # Notify the waiting agent
                    await self._send_to_agent(
                        project_token,
                        other_agent_id,
                        {
                            "type": "dependency_resolved",
                            "resolved_agent": agent_id,
                            "timestamp": datetime.utcnow().isoformat()
                        }
                    )


# Global coordination service instance
coordination_service = AgentCoordinationService()


# Helper functions for integration with existing agent service

async def initialize_project_coordination(
    project_token: str, 
    agents_config: Dict[str, Any],
    master_plan: Dict[str, Any]
) -> Dict[str, Any]:
    """Initialize coordination for a project"""
    return await coordination_service.initialize_project_coordination(
        project_token, agents_config, master_plan
    )


async def get_agent_coordination_view(project_token: str, agent_id: str) -> Optional[Dict[str, Any]]:
    """Get coordination state for specific agent"""
    return await coordination_service.get_agent_view(project_token, agent_id)


async def update_agent_coordination_status(
    project_token: str, 
    agent_id: str, 
    status: str,
    task_info: Optional[Dict[str, Any]] = None
) -> bool:
    """Update agent status in coordination system"""
    return await coordination_service.update_agent_status(
        project_token, agent_id, status, task_info
    )


async def request_coordination_file_lock(
    project_token: str, 
    agent_id: str, 
    file_path: str,
    lock_type: str = "write"
) -> Dict[str, Any]:
    """Request file lock through coordination system"""
    return await coordination_service.request_file_lock(
        project_token, agent_id, file_path, lock_type
    )


async def release_coordination_file_lock(
    project_token: str, 
    agent_id: str, 
    file_path: str
) -> bool:
    """Release file lock through coordination system"""
    return await coordination_service.release_file_lock(
        project_token, agent_id, file_path
    )