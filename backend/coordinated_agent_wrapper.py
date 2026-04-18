import asyncio
import logging
from typing import Dict, Any, Optional
from datetime import datetime

from agent_coordination_service import (
    coordination_service,
    update_agent_coordination_status,
    request_coordination_file_lock,
    release_coordination_file_lock,
    get_agent_coordination_view
)

logger = logging.getLogger(__name__)


class CoordinatedAgentWrapper:
    """Wrapper that adds coordination capabilities to existing agents"""
    
    def __init__(self, agent_id: str, project_token: str):
        self.agent_id = agent_id
        self.project_token = project_token
        self.coordination_callbacks = {}
        
    async def run_with_coordination(
        self,
        original_run_agent_func,
        **kwargs
    ) -> Dict[str, Any]:
        """Run agent with coordination awareness"""
        
        # Initialize coordination callbacks
        self.coordination_callbacks = {
            "on_file_access": self._handle_file_access,
            "on_progress_update": self._handle_progress_update,
            "on_sync_request": self._handle_sync_request,
            "on_communication": self._handle_agent_communication,
            "on_status_change": self._handle_status_change
        }
        
        try:
            # Pre-execution coordination setup
            await self._pre_execution_setup()
            
            # Update status to working
            await update_agent_coordination_status(
                self.project_token, 
                self.agent_id, 
                "working",
                kwargs.get("assigned_task")
            )
            
            # Run the original agent function with coordination hooks
            result = await self._run_with_coordination_hooks(
                original_run_agent_func, 
                **kwargs
            )
            
            # Post-execution coordination cleanup
            await self._post_execution_cleanup(result)
            
            # Update final status
            final_status = "completed" if result.get("success") else "failed"
            await update_agent_coordination_status(
                self.project_token, 
                self.agent_id, 
                final_status
            )
            
            return result
            
        except Exception as exc:
            logger.exception(f"Coordinated agent execution failed for {self.agent_id}")
            
            # Update status to failed
            await update_agent_coordination_status(
                self.project_token, 
                self.agent_id, 
                "failed"
            )
            
            return {
                "success": False,
                "agent_id": self.agent_id,
                "error": str(exc),
                "tasks_completed": 0,
            }
    
    async def _pre_execution_setup(self):
        """Setup coordination before agent execution"""
        
        # Update status to indicate we're starting
        await update_agent_coordination_status(
            self.project_token, 
            self.agent_id, 
            "initializing",
            {"message": "Setting up coordination"}
        )
        
        # Get current coordination view
        coord_view = await get_agent_coordination_view(
            self.project_token, 
            self.agent_id
        )
        
        if coord_view:
            # Check for any blocking conditions
            my_status = coord_view.get("my_status", {})
            dependencies_waiting = my_status.get("dependencies_waiting", [])
            
            if dependencies_waiting:
                logger.info(f"🔄 Agent {self.agent_id} waiting for dependencies: {dependencies_waiting}")
                await update_agent_coordination_status(
                    self.project_token, 
                    self.agent_id, 
                    "waiting_dependency",
                    {"dependencies": dependencies_waiting}
                )
                # Could implement waiting logic here
            
            # Log coordination context
            other_agents = coord_view.get("other_agents", {})
            active_agents = [
                aid for aid, info in other_agents.items() 
                if info.get("status") == "working"
            ]
            
            if active_agents:
                logger.info(f"🤝 Agent {self.agent_id} starting with {len(active_agents)} other active agents: {active_agents}")
            else:
                logger.info(f"🚀 Agent {self.agent_id} starting as the only active agent")
                
            # Check for available file locks
            available_files = coord_view.get("available_files", [])
            locked_files = coord_view.get("locked_files", {})
            
            if locked_files:
                logger.info(f"🔒 Agent {self.agent_id} sees {len(locked_files)} locked files: {list(locked_files.keys())[:3]}")
            
            # Check for pending sync points
            pending_syncs = coord_view.get("pending_sync_points", {})
            if pending_syncs:
                logger.info(f"⏳ Agent {self.agent_id} sees {len(pending_syncs)} pending sync points: {list(pending_syncs.keys())}")
        
        # Mark as ready to work
        await update_agent_coordination_status(
            self.project_token, 
            self.agent_id, 
            "ready",
            {"message": "Coordination setup complete"}
        )
    
    async def _run_with_coordination_hooks(
        self, 
        original_run_agent_func, 
        **kwargs
    ) -> Dict[str, Any]:
        """Run agent with coordination monitoring and file locking"""
        
        assigned_task = kwargs.get("assigned_task")
        
        # Update status to working
        await update_agent_coordination_status(
            self.project_token, 
            self.agent_id, 
            "working",
            assigned_task
        )
        
        # Predict files this task will work on
        predicted_files = []
        if assigned_task:
            task_desc = assigned_task.get("description", "")
            task_title = assigned_task.get("title", "")
            
            # Simple file prediction based on task content
            if "dockerfile" in task_desc.lower() or "docker" in task_title.lower():
                predicted_files = ["Dockerfile", "docker-compose.yml", ".dockerignore"]
            elif "api" in task_desc.lower() or "endpoint" in task_desc.lower():
                predicted_files = ["app.py", "main.py", "routes.py", "api.py"]
            elif "frontend" in task_desc.lower() or "react" in task_desc.lower():
                predicted_files = ["src/App.jsx", "src/components/", "package.json"]
            elif "database" in task_desc.lower() or "schema" in task_desc.lower():
                predicted_files = ["models.py", "schema.sql", "migrations/"]
        
        # Request file locks for predicted files
        locked_files = []
        for file_path in predicted_files:
            try:
                lock_result = await request_coordination_file_lock(
                    self.project_token, self.agent_id, file_path, "write"
                )
                if lock_result.get("success"):
                    locked_files.append(file_path)
                    logger.info(f"🔒 Agent {self.agent_id} locked file: {file_path}")
                else:
                    logger.info(f"⚠️ Agent {self.agent_id} couldn't lock {file_path}: {lock_result.get('error', 'unknown')}")
            except Exception as lock_err:
                logger.warning(f"File lock request failed for {file_path}: {lock_err}")
        
        # Send coordination message about task start
        if assigned_task:
            try:
                from agent_coordination_service import coordination_service
                await coordination_service.send_agent_message(
                    self.project_token, self.agent_id, None,  # Broadcast to all
                    {
                        "type": "task_start",
                        "message": f"Starting task: {assigned_task.get('title', 'Unknown task')}",
                        "task_details": {
                            "title": assigned_task.get("title"),
                            "description": assigned_task.get("description", "")[:200],
                            "predicted_files": predicted_files
                        }
                    }
                )
            except Exception as msg_err:
                logger.warning(f"Failed to send task start message: {msg_err}")
        
        # Start coordination monitoring task
        monitor_task = asyncio.create_task(
            self._coordination_monitor()
        )
        
        try:
            # Run the original agent function
            result = await original_run_agent_func(**kwargs)
            
            # Send completion message
            success = result.get("success", False)
            tasks_completed = result.get("tasks_completed", 0)
            failed_tasks = result.get("failed_tasks", 0)
            
            try:
                from agent_coordination_service import coordination_service
                await coordination_service.send_agent_message(
                    self.project_token, self.agent_id, None,  # Broadcast to all
                    {
                        "type": "task_complete",
                        "message": f"{'Completed' if success else 'Failed'} {tasks_completed} task(s)" + 
                                 (f" ({failed_tasks} failed)" if failed_tasks > 0 else ""),
                        "result_summary": {
                            "success": success,
                            "tasks_completed": tasks_completed,
                            "failed_tasks": failed_tasks,
                            "duration": result.get("total_duration", 0)
                        }
                    }
                )
            except Exception as msg_err:
                logger.warning(f"Failed to send task completion message: {msg_err}")
            
            return result
            
        finally:
            # Stop monitoring
            monitor_task.cancel()
            try:
                await monitor_task
            except asyncio.CancelledError:
                pass
            
            # Release all file locks
            for file_path in locked_files:
                try:
                    await release_coordination_file_lock(
                        self.project_token, self.agent_id, file_path
                    )
                    logger.info(f"🔓 Agent {self.agent_id} released file: {file_path}")
                except Exception as release_err:
                    logger.warning(f"Failed to release file lock for {file_path}: {release_err}")
            
            # Update final status
            final_status = "completed" if result.get("success", False) else "error"
            await update_agent_coordination_status(
                self.project_token, 
                self.agent_id, 
                final_status,
                {
                    "tasks_completed": result.get("tasks_completed", 0),
                    "failed_tasks": result.get("failed_tasks", 0)
                }
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
                            await self._handle_sync_point_completed(sync_name, sync_info)
                
                await asyncio.sleep(3)  # Check every 3 seconds
                
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.exception(f"Coordination monitor error for {self.agent_id}: {exc}")
                await asyncio.sleep(5)
    
    async def _post_execution_cleanup(self, result: Dict[str, Any]):
        """Cleanup coordination after agent execution"""
        
        # Release any file locks held by this agent
        coord_view = await get_agent_coordination_view(
            self.project_token, 
            self.agent_id
        )
        
        if coord_view:
            my_locks = coord_view.get("my_status", {}).get("file_locks", [])
            for file_path in my_locks:
                await release_coordination_file_lock(
                    self.project_token, 
                    self.agent_id, 
                    file_path
                )
        
        # Update shared context with results
        if result.get("success"):
            context_updates = {
                "completed_tasks": {
                    self.agent_id: {
                        "completed_at": datetime.utcnow().isoformat(),
                        "tasks_completed": result.get("tasks_completed", 0),
                        "duration": result.get("duration", 0)
                    }
                }
            }
            
            await coordination_service.update_shared_context(
                self.project_token,
                self.agent_id,
                context_updates
            )
    
    # Coordination event handlers
    
    async def _handle_file_access(self, file_path: str, access_type: str = "write"):
        """Handle file access coordination"""
        
        # Request file lock
        lock_result = await request_coordination_file_lock(
            self.project_token,
            self.agent_id,
            file_path,
            access_type
        )
        
        if not lock_result.get("success"):
            # File is locked by another agent
            locked_by = lock_result.get("locked_by")
            logger.warning(f"Agent {self.agent_id} blocked: file {file_path} locked by {locked_by}")
            
            # Could implement waiting or alternative strategy here
            return False
        
        return True
    
    async def _handle_progress_update(self, progress_info: Dict[str, Any]):
        """Handle progress update coordination"""
        
        # Update coordination system with progress
        await update_agent_coordination_status(
            self.project_token,
            self.agent_id,
            "working",
            progress_info
        )
        
        # Broadcast progress to other agents if significant milestone
        progress = progress_info.get("progress", 0)
        if progress in [25, 50, 75, 90]:  # Milestone progress points
            await coordination_service.send_agent_message(
                self.project_token,
                self.agent_id,
                None,  # Broadcast to all
                {
                    "type": "progress_milestone",
                    "progress": progress,
                    "task": progress_info.get("task_title", ""),
                    "message": f"Reached {progress}% completion"
                }
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
        """Handle agent status changes"""
        
        await update_agent_coordination_status(
            self.project_token,
            self.agent_id,
            new_status
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
    
    async def _handle_sync_point_completed(self, sync_name: str, sync_info: Dict[str, Any]):
        """Handle sync point completion"""
        
        logger.info(f"Agent {self.agent_id} notified that sync point {sync_name} is completed")
        
        # Could trigger specific actions based on sync point type
        if sync_name == "architecture_review":
            # Architecture is finalized, can proceed with implementation
            pass
        elif sync_name == "integration_checkpoint":
            # Integration phase complete, can proceed with testing
            pass


# Integration function to wrap existing run_agent calls
async def run_coordinated_agent(
    agent_id: str,
    project_token: str,
    original_run_agent_func,
    **kwargs
) -> Dict[str, Any]:
    """
    Wrapper function to run an agent with coordination capabilities
    
    Usage:
        from coordinated_agent_wrapper import run_coordinated_agent
        import agent_service
        
        result = await run_coordinated_agent(
            agent_id="dev_agent_1",
            project_token="project_123",
            original_run_agent_func=agent_service.run_agent,
            git_repo_url="https://github.com/user/repo",
            assigned_task=task_dict,
            continuous=True
        )
    """
    
    wrapper = CoordinatedAgentWrapper(agent_id, project_token)
    return await wrapper.run_with_coordination(
        original_run_agent_func,
        agent_id=agent_id,
        project_token=project_token,
        **kwargs
    )


# Enhanced LangGraph integration
async def run_coordinated_agents_langgraph(
    project_token: str,
    agents_config: Dict[str, Dict[str, str]],
    task_token: Optional[str] = None
) -> Dict[str, Any]:
    """
    Run multiple agents with full coordination through LangGraph
    """
    
    # Initialize coordination for the project
    from agent_coordination_service import initialize_project_coordination
    
    # Get master plan (would come from your existing workflow)
    master_plan = {}  # This would be populated from your master workspace note
    
    # Initialize coordination state
    coord_state = await initialize_project_coordination(
        project_token,
        agents_config,
        master_plan
    )
    
    # Run the synchronized LangGraph workflow
    from synchronized_langgraph_workflow import run_synchronized_agent_workflow
    
    result = await run_synchronized_agent_workflow(
        agents_config=agents_config,
        project_token=project_token,
        task_token=task_token
    )
    
    return result