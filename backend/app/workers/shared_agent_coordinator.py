"""
Global Shared Agent Coordinator
Manages shared agents across multiple projects
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class SharedAgentStatus(Enum):
    IDLE = "idle"
    BUSY = "busy"
    OFFLINE = "offline"


@dataclass
class SharedAgentState:
    agent_id: str
    status: SharedAgentStatus
    current_project: Optional[str] = None
    current_task: Optional[Dict[str, Any]] = None
    locked_at: Optional[str] = None
    last_active: Optional[str] = None


@dataclass
class QueuedTask:
    project_token: str
    task: Dict[str, Any]
    priority: int
    queued_at: str
    master_agent_id: str


class SharedAgentCoordinator:
    """
    Global coordinator for shared agents across all projects.
    Ensures shared agents only work on one task at a time.
    """
    
    def __init__(self):
        # Global state for all shared agents
        self._agent_states: Dict[str, SharedAgentState] = {}
        
        # Locks for each shared agent
        self._agent_locks: Dict[str, asyncio.Lock] = {}
        
        # Task queues for each shared agent
        self._task_queues: Dict[str, List[QueuedTask]] = {}
        
        # Project waiting lists
        self._waiting_projects: Dict[str, List[str]] = {}  # agent_id -> [project_tokens]
        
        # Coordinator lock
        self._coordinator_lock = asyncio.Lock()
    
    async def register_shared_agent(self, agent_id: str) -> None:
        """Register a shared agent in the global coordinator"""
        async with self._coordinator_lock:
            if agent_id not in self._agent_states:
                self._agent_states[agent_id] = SharedAgentState(
                    agent_id=agent_id,
                    status=SharedAgentStatus.IDLE,
                    last_active=datetime.utcnow().isoformat()
                )
                self._agent_locks[agent_id] = asyncio.Lock()
                self._task_queues[agent_id] = []
                self._waiting_projects[agent_id] = []
                
                logger.info(f"✅ Registered shared agent: {agent_id}")
    
    async def is_agent_available(self, agent_id: str) -> bool:
        """Check if shared agent is available across ALL projects"""
        async with self._coordinator_lock:
            if agent_id not in self._agent_states:
                return True
            
            state = self._agent_states[agent_id]
            return state.status == SharedAgentStatus.IDLE
    
    async def get_agent_current_project(self, agent_id: str) -> Optional[str]:
        """Get which project the shared agent is currently working on"""
        async with self._coordinator_lock:
            if agent_id not in self._agent_states:
                return None
            
            state = self._agent_states[agent_id]
            return state.current_project if state.status == SharedAgentStatus.BUSY else None
    
    async def acquire_agent(
        self, 
        agent_id: str, 
        project_token: str, 
        task: Dict[str, Any],
        master_agent_id: str = "M_agent_01",
        timeout_seconds: float = 30.0
    ) -> bool:
        """
        Acquire exclusive access to a shared agent for a project.
        Returns True if acquired, False if timeout.
        """
        if agent_id not in self._agent_locks:
            await self.register_shared_agent(agent_id)
        
        lock = self._agent_locks[agent_id]
        
        try:
            # Try to acquire lock with timeout
            acquired = await asyncio.wait_for(
                lock.acquire(),
                timeout=timeout_seconds
            )
            
            if acquired:
                async with self._coordinator_lock:
                    # Mark agent as busy
                    self._agent_states[agent_id] = SharedAgentState(
                        agent_id=agent_id,
                        status=SharedAgentStatus.BUSY,
                        current_project=project_token,
                        current_task=task,
                        locked_at=datetime.utcnow().isoformat(),
                        last_active=datetime.utcnow().isoformat()
                    )
                    
                    logger.info(
                        f"🔒 Agent {agent_id} acquired by project {project_token} "
                        f"for task: {task.get('title', 'Untitled')}"
                    )
                
                return True
            
        except asyncio.TimeoutError:
            logger.warning(
                f"⏱️ Timeout acquiring agent {agent_id} for project {project_token}"
            )
            return False
        
        return False
    
    async def release_agent(self, agent_id: str, project_token: str) -> None:
        """Release shared agent after task completion"""
        if agent_id not in self._agent_locks:
            return
        
        lock = self._agent_locks[agent_id]
        
        async with self._coordinator_lock:
            state = self._agent_states.get(agent_id)
            
            if state and state.current_project == project_token:
                # Mark agent as idle
                self._agent_states[agent_id] = SharedAgentState(
                    agent_id=agent_id,
                    status=SharedAgentStatus.IDLE,
                    last_active=datetime.utcnow().isoformat()
                )
                
                logger.info(
                    f"🔓 Agent {agent_id} released by project {project_token}"
                )
                
                # Release lock
                if lock.locked():
                    lock.release()
                
                # Notify waiting projects
                await self._notify_waiting_projects(agent_id)

    async def preempt_borrowed_agent(
        self,
        agent_id: str,
        home_project_token: str,
        reason: str = "Home project requirement raised"
    ) -> bool:
        """
        Immediately preempt a Dedicated Agent borrowed by another project as a Shared Agent,
        returning it to its home project. The interrupted task is re-queued.
        """
        async with self._coordinator_lock:
            state = self._agent_states.get(agent_id)
            if not state or state.status != SharedAgentStatus.BUSY:
                logger.info(f"⚡ Preemption check for {agent_id}: Agent is not currently busy on a borrowed task.")
                return False

            borrowed_project = state.current_project
            borrowed_task = state.current_task

            logger.warning(
                f"🚨 PREEMPTING Agent {agent_id} from borrowed project {borrowed_project} "
                f"back to home project {home_project_token}. Reason: {reason}"
            )

            # Re-queue interrupted borrowed task back into FIFO queue
            if borrowed_task and borrowed_project:
                if agent_id not in self._task_queues:
                    self._task_queues[agent_id] = []
                self._task_queues[agent_id].insert(0, QueuedTask(
                    project_token=borrowed_project,
                    task=borrowed_task,
                    priority=1,  # Top priority on re-queue
                    queued_at=datetime.utcnow().isoformat(),
                    master_agent_id="M_agent_01"
                ))
                logger.info(f"🔁 Re-queued interrupted task for borrowed project {borrowed_project}")

            # Reset agent state to idle for home project
            self._agent_states[agent_id] = SharedAgentState(
                agent_id=agent_id,
                status=SharedAgentStatus.IDLE,
                current_project=home_project_token,
                last_active=datetime.utcnow().isoformat()
            )

            # Force release lock if held
            lock = self._agent_locks.get(agent_id)
            if lock and lock.locked():
                try:
                    lock.release()
                except RuntimeError:
                    pass

            return True

    async def queue_task(
        self,
        agent_id: str,
        project_token: str,
        task: Dict[str, Any],
        priority: int = 5,
        master_agent_id: str = "M_agent_01"
    ) -> int:
        """
        Queue a task for a shared agent when it's busy.
        Returns queue position.
        """
        async with self._coordinator_lock:
            if agent_id not in self._task_queues:
                self._task_queues[agent_id] = []
            
            queued_task = QueuedTask(
                project_token=project_token,
                task=task,
                priority=priority,
                queued_at=datetime.utcnow().isoformat(),
                master_agent_id=master_agent_id
            )
            
            self._task_queues[agent_id].append(queued_task)
            
            # Sort by priority (lower number = higher priority)
            self._task_queues[agent_id].sort(key=lambda x: x.priority)
            
            # Add project to waiting list
            if project_token not in self._waiting_projects.get(agent_id, []):
                self._waiting_projects.setdefault(agent_id, []).append(project_token)
            
            queue_position = len(self._task_queues[agent_id])
            
            logger.info(
                f"📥 Task queued for agent {agent_id} from project {project_token}. "
                f"Queue position: {queue_position}"
            )
            
            return queue_position
    
    async def _notify_waiting_projects(self, agent_id: str) -> None:
        """Notify all projects waiting for this agent that it's now available"""
        waiting_projects = self._waiting_projects.get(agent_id, [])
        
        if waiting_projects:
            logger.info(
                f"📢 Notifying {len(waiting_projects)} project(s) that agent {agent_id} is available"
            )
            
            # Trigger next task assignment from queue
            await self._assign_next_queued_task(agent_id)
    
    async def _assign_next_queued_task(self, agent_id: str) -> None:
        """Assign the next queued task to the agent"""
        queue = self._task_queues.get(agent_id, [])
        
        if not queue:
            return
        
        # Get highest priority task
        next_task = queue.pop(0)
        
        logger.info(
            f"🎯 Auto-assigning next queued task to agent {agent_id} "
            f"from project {next_task.project_token}"
        )
        
        # Acquire agent for the next project
        acquired = await self.acquire_agent(
            agent_id=agent_id,
            project_token=next_task.project_token,
            task=next_task.task,
            timeout_seconds=5.0
        )
        
        if acquired:
            # Trigger agent execution (call agent_service.run_agent)
            from app.services.agents import agent_service
            asyncio.create_task(
                agent_service.run_agent(
                    agent_id=agent_id,
                    project_token=next_task.project_token,
                    task_token=agent_service.get_project_task_token(next_task.project_token),
                    continuous=False
                )
            )
    
    async def get_agent_status(self, agent_id: str) -> Dict[str, Any]:
        """Get detailed status of a shared agent"""
        async with self._coordinator_lock:
            if agent_id not in self._agent_states:
                return {"error": "Agent not found"}
            
            state = self._agent_states[agent_id]
            queue = self._task_queues.get(agent_id, [])
            
            return {
                "agent_id": agent_id,
                "status": state.status.value,
                "current_project": state.current_project,
                "current_task": state.current_task.get("title") if state.current_task else None,
                "locked_at": state.locked_at,
                "last_active": state.last_active,
                "queued_tasks": len(queue),
                "waiting_projects": self._waiting_projects.get(agent_id, [])
            }
    
    async def get_all_shared_agents_status(self) -> List[Dict[str, Any]]:
        """Get status of all shared agents"""
        async with self._coordinator_lock:
            results = []
            for agent_id in list(self._agent_states.keys()):
                state = self._agent_states.get(agent_id)
                if not state:
                    results.append({"error": "Agent not found"})
                    continue
                queue = self._task_queues.get(agent_id, [])
                results.append({
                    "agent_id": agent_id,
                    "status": state.status.value,
                    "current_project": state.current_project,
                    "current_task": state.current_task.get("title") if state.current_task else None,
                    "locked_at": state.locked_at,
                    "last_active": state.last_active,
                    "queued_tasks": len(queue),
                    "waiting_projects": self._waiting_projects.get(agent_id, [])
                })
            return results


# Global singleton instance
_shared_agent_coordinator = SharedAgentCoordinator()


async def get_shared_agent_coordinator() -> SharedAgentCoordinator:
    """Get the global shared agent coordinator instance"""
    return _shared_agent_coordinator
