import asyncio
import logging
from typing import Dict, Any, Optional

from integrated_agent_coordinator import coordinator as integrated_coordinator
from agent_coordination_service import (
    coordination_service,
    get_agent_coordination_view
)

logger = logging.getLogger(__name__)


class CoordinatedAgentWrapper:
    """Wrapper that adds coordination capabilities to existing agents.
    All coordination operations route through IntegratedCoordinator
    which syncs all 6 systems atomically."""
    
    def __init__(self, agent_id: str, project_token: str):
        self.agent_id = agent_id
        self.project_token = project_token
        self.coordination_callbacks = {}
        
    async def run_with_coordination(
        self,
        original_run_agent_func,
        **kwargs
    ) -> Dict[str, Any]:
        """Run agent with full coordination. All operations route through IntegratedCoordinator."""
        self.coordination_callbacks = {
            "on_file_access": self._handle_file_access,
            "on_progress_update": self._handle_progress_update,
            "on_sync_request": self._handle_sync_request,
            "on_communication": self._handle_agent_communication,
            "on_status_change": self._handle_status_change
        }

        try:
            await self._pre_execution_setup()

            assigned_task = kwargs.get("assigned_task")
            await integrated_coordinator.on_agent_status_change(
                self.project_token, self.agent_id, "working",
                task_info=assigned_task
            )

            result = await self._run_with_coordination_hooks(
                original_run_agent_func, **kwargs
            )

            await self._post_execution_cleanup(result)

            final_status = "completed" if result.get("success") else "failed"
            await integrated_coordinator.on_agent_status_change(
                self.project_token, self.agent_id, final_status,
                task_info=assigned_task,
                progress=100 if result.get("success") else 0
            )

            if result.get("success") and assigned_task:
                await integrated_coordinator.on_agent_ready(
                    self.project_token, self.agent_id,
                    what_is_ready=assigned_task.get("title", "")
                )
                files = result.get("files_created", [])
                if files:
                    await integrated_coordinator.on_agent_files_created(
                        self.project_token, self.agent_id, files
                    )

            return result

        except Exception as exc:
            logger.exception(f"Coordinated agent execution failed for {self.agent_id}")

            await integrated_coordinator.on_agent_status_change(
                self.project_token, self.agent_id, "failed",
                task_info=kwargs.get("assigned_task")
            )
            await integrated_coordinator.on_agent_blocked(
                self.project_token, self.agent_id,
                reason=str(exc),
                needs=f"Fix for: {kwargs.get('assigned_task', {}).get('title', 'unknown')}"
            )

            return {
                "success": False,
                "agent_id": self.agent_id,
                "error": str(exc),
                "tasks_completed": 0,
            }
    
    async def _pre_execution_setup(self):
        """Setup coordination before agent execution."""
        coord_view = await get_agent_coordination_view(
            self.project_token, self.agent_id
        )

        if coord_view:
            my_status = coord_view.get("my_status", {})
            dependencies_waiting = my_status.get("dependencies_waiting", [])

            if dependencies_waiting:
                logger.info(f"Agent {self.agent_id} waiting for deps: {dependencies_waiting}")
                await integrated_coordinator.on_agent_status_change(
                    self.project_token, self.agent_id, "blocked",
                    task_info={"blocked_on": dependencies_waiting}
                )

            other_agents = coord_view.get("other_agents", {})
            active_agents = [
                aid for aid, info in other_agents.items()
                if info.get("status") == "working"
            ]
            if active_agents:
                logger.info(f"Agent {self.agent_id} starting with {len(active_agents)} active peers")
            else:
                logger.info(f"Agent {self.agent_id} starting as the only active agent")
    
    async def _run_with_coordination_hooks(
        self, original_run_agent_func, **kwargs
    ) -> Dict[str, Any]:
        """Run agent with coordination monitoring and unified file locking."""
        assigned_task = kwargs.get("assigned_task")

        # Predict files this task will work on
        predicted_files = []
        if assigned_task:
            task_combined = (
                str(assigned_task.get("description", "") or "") + " " +
                str(assigned_task.get("title", "") or "")
            ).lower()

            if "docker" in task_combined:
                predicted_files = ["Dockerfile", "docker-compose.yml", ".dockerignore"]
            elif "api" in task_combined or "endpoint" in task_combined:
                predicted_files = ["app.py", "main.py", "routes.py"]
            elif "frontend" in task_combined or "react" in task_combined or "ui" in task_combined:
                predicted_files = ["src/App.jsx", "src/components/", "package.json"]
            elif "database" in task_combined or "schema" in task_combined:
                predicted_files = ["models.py", "schema.sql", "migrations/"]
            elif "auth" in task_combined:
                predicted_files = ["auth.py", "middleware.py", "config.py"]

        # Unified file locking via IntegratedCoordinator
        locked_files = []
        for file_path in predicted_files:
            granted = await integrated_coordinator.on_agent_file_locked(
                self.project_token, self.agent_id, file_path
            )
            if granted:
                locked_files.append(file_path)

        if assigned_task:
            await integrated_coordinator.on_agent_status_change(
                self.project_token, self.agent_id, "in_progress",
                task_info=assigned_task, progress=0
            )

        monitor_task = asyncio.create_task(self._coordination_monitor())
        result = {"success": False, "tasks_completed": 0, "failed_tasks": 0}

        try:
            result = await original_run_agent_func(**kwargs)
            success = result.get("success", False)
            await integrated_coordinator.on_agent_status_change(
                self.project_token, self.agent_id,
                "completed" if success else "failed",
                task_info=assigned_task,
                progress=100 if success else 0,
            )
            return result
        finally:
            monitor_task.cancel()
            try:
                await monitor_task
            except asyncio.CancelledError:
                pass
            for file_path in locked_files:
                await integrated_coordinator.on_agent_file_released(
                    self.project_token, self.agent_id, file_path
                )
    
    async def _coordination_monitor(self):
        """Background monitoring of coordination state"""
        
        while True:
            try:
                # Get current coordination view
                coord_view = await get_agent_coordination_view(
                    self.project_token, 
                    self.agent_id
                )
                
                if coord_view:
                    # Check for messages from other agents
                    recent_comms = coord_view.get("recent_communications", [])
                    for comm in recent_comms[-5:]:  # Check last 5 messages
                        if comm.get("type") == "agent_message":
                            await self._handle_incoming_message(comm)
                    
                    # Check sync point status
                    sync_points = coord_view.get("sync_points", {})
                    for sync_name, sync_info in sync_points.items():
                        if sync_info.get("status") == "completed":
                            logger.info(f"Agent {self.agent_id}: sync point {sync_name} completed")

                await asyncio.sleep(3)
                
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.exception(f"Coordination monitor error for {self.agent_id}: {exc}")
                await asyncio.sleep(5)
    
    async def _post_execution_cleanup(self, result: Dict[str, Any]):
        """Cleanup after agent execution."""
        if result.get("success"):
            files = result.get("files_created", [])
            if files:
                await integrated_coordinator.on_agent_files_created(
                    self.project_token, self.agent_id, files
                )
    
    # Coordination event handlers
    
    async def _handle_file_access(self, file_path: str, access_type: str = "write"):
        """Handle file access through unified locking."""
        return await integrated_coordinator.on_agent_file_locked(
            self.project_token, self.agent_id, file_path
        )
    
    async def _handle_progress_update(self, progress_info: Dict[str, Any]):
        """Handle progress update via coordinator."""
        await integrated_coordinator.on_agent_status_change(
            self.project_token, self.agent_id, "working",
            task_info=progress_info,
            progress=progress_info.get("progress", 0)
        )
    
    async def _handle_sync_request(self, sync_type: str, data: Optional[Dict[str, Any]] = None):
        """Handle synchronization point requests"""
        
        sync_result = await coordination_service.request_sync_point(
            self.project_token,
            self.agent_id,
            sync_type,
            data
        )
        
        if sync_result.get("sync_completed"):
            logger.info(f"Agent {self.agent_id} completed sync point: {sync_type}")
            return sync_result.get("data", {})
        else:
            waiting_for = sync_result.get("waiting_for", [])
            logger.info(f"Agent {self.agent_id} waiting at sync point {sync_type} for: {waiting_for}")
            return None
    
    async def _handle_agent_communication(self, message: Dict[str, Any]):
        """Handle inter-agent communication"""
        
        await coordination_service.send_agent_message(
            self.project_token,
            self.agent_id,
            message.get("to_agent"),
            message
        )
    
    async def _handle_status_change(self, new_status: str):
        """Handle status changes via coordinator."""
        await integrated_coordinator.on_agent_status_change(
            self.project_token, self.agent_id, new_status
        )
    
    async def _handle_incoming_message(self, message: Dict[str, Any]):
        """Handle incoming messages from other agents"""
        
        msg_type = message.get("message", {}).get("type")
        from_agent = message.get("from_agent")
        
        if msg_type == "progress_milestone":
            logger.info(f"Agent {self.agent_id} received progress update from {from_agent}: {message.get('message', {}).get('message', '')}")
        
        elif msg_type == "file_conflict":
            # Handle file conflict notifications
            conflicted_file = message.get("message", {}).get("file_path")
            logger.warning(f"Agent {self.agent_id} notified of file conflict on {conflicted_file} by {from_agent}")
        
        elif msg_type == "dependency_resolved":
            # Handle dependency resolution notifications
            logger.info(f"Agent {self.agent_id} notified that dependency {from_agent} is resolved")
    


# ── Public wrapper function ─────────────────────────────────────────────
async def run_coordinated_agent(
    agent_id: str,
    project_token: str,
    original_run_agent_func,
    **kwargs
) -> Dict[str, Any]:
    """
    Run an agent with FULL coordination (IntegratedCoordinator).
    All status changes, file locks, and broadcasts route through
    IntegratedCoordinator which syncs all 6 systems atomically.
    """
    wrapper = CoordinatedAgentWrapper(agent_id, project_token)
    return await wrapper.run_with_coordination(
        original_run_agent_func,
        agent_id=agent_id,
        project_token=project_token,
        **kwargs
    )


# ── Backward-compatibility stub ─────────────────────────────────────────
# Kept for modules that still import run_coordinated_agents_langgraph.
# Routes through IntegratedCoordinator under the hood.

async def run_coordinated_agents_langgraph(
    project_token: str,
    agents_config: Dict[str, Dict[str, str]],
    task_token: Optional[str] = None
) -> Dict[str, Any]:
    """
    [Deprecated] Use master_coordination_service.start_coordinated_project() instead.
    This stub delegates to IntegratedCoordinator for backward compatibility.
    """
    from integrated_agent_coordinator import coordinator
    agents = list(agents_config.keys())
    result = await coordinator.start_coordinated_project(
        project_token=project_token,
        tasks=[],
        agents=agents,
    )
    return result