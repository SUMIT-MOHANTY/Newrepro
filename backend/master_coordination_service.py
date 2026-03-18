"""
Master Coordination Service - Integration layer between Master Task Manager and existing system
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any
from master_task_manager import master_task_manager
import agent_service

logger = logging.getLogger(__name__)

class MasterCoordinationService:
    """
    Bridges the Master Task Manager with existing agent_service
    Ensures ONLY the Master controls task assignment
    """
    
    def __init__(self):
        self.active_projects: Dict[str, bool] = {}
    
    async def start_coordinated_project(
        self, 
        project_token: str, 
        tasks: List[Dict[str, Any]], 
        agents: List[str]
    ) -> Dict[str, Any]:
        """
        Start a project with Master Task Manager in full control
        """
        logger.info(f"🎯 Starting coordinated project: {project_token}")
        
        # Initialize Master Task Manager
        await master_task_manager.initialize_project(project_token, tasks, agents)
        
        # Mark project as active
        self.active_projects[project_token] = True
        
        # Start the coordination loop
        asyncio.create_task(self._coordination_loop(project_token))
        
        return {
            "status": "started",
            "project_token": project_token,
            "total_tasks": len(tasks),
            "available_agents": len(agents),
            "message": "Master Task Manager is now controlling all agents"
        }
    
    async def _coordination_loop(self, project_token: str):
        """
        Main coordination loop - Master assigns tasks continuously
        """
        logger.info(f"🔄 Starting coordination loop for {project_token}")
        
        while self.active_projects.get(project_token, False):
            try:
                # Try to assign next task
                assignment = await master_task_manager.assign_next_task(project_token)
                
                if assignment["status"] == "assigned":
                    # Start the assigned agent
                    agent_id = assignment["agent_id"]
                    task = assignment["task"]
                    
                    # Launch agent with coordination
                    asyncio.create_task(
                        self._run_coordinated_agent(agent_id, task, project_token)
                    )
                
                elif assignment["status"] == "no_available_tasks":
                    # Check if project is complete
                    status = master_task_manager.get_coordination_status(project_token)
                    if status["pending_tasks"] == 0 and status["in_progress_tasks"] == 0:
                        logger.info(f"🎉 Project {project_token} completed!")
                        self.active_projects[project_token] = False
                        break
                
                # Wait before next assignment check
                await asyncio.sleep(5)
                
            except Exception as e:
                logger.error(f"❌ Error in coordination loop: {e}")
                await asyncio.sleep(10)  # Wait longer on error
    
    async def _run_coordinated_agent(
        self, 
        agent_id: str, 
        task: Dict[str, Any], 
        project_token: str
    ):
        """
        Run an agent under Master coordination
        """
        logger.info(f"🤖 Starting coordinated agent {agent_id} for task: {task['title']}")
        
        try:
            # Report task start
            await master_task_manager.report_task_progress(
                agent_id, 
                {"status": "in_progress", "progress": 0}
            )
            
            # Run the actual agent work (modified to be coordinated)
            result = await self._execute_agent_task(agent_id, task, project_token)
            
            # Report completion
            await master_task_manager.complete_task(agent_id, result)
            
        except Exception as e:
            logger.error(f"❌ Agent {agent_id} failed: {e}")
            # Report failure
            await master_task_manager.report_task_progress(
                agent_id,
                {"status": "failed", "error": str(e)}
            )
    
    async def _execute_agent_task(
        self, 
        agent_id: str, 
        task: Dict[str, Any], 
        project_token: str
    ) -> Dict[str, Any]:
        """
        Execute agent task with coordination hooks
        """
        # This replaces the old agent_service.run_agent with coordinated version
        
        # Step 1: Request file locks for files this task will modify
        file_intents = self._extract_file_intents_from_task(task)
        locked_files = []
        
        for file_path in file_intents:
            lock_result = await master_task_manager.request_file_lock(agent_id, file_path)
            if lock_result["granted"]:
                locked_files.append(file_path)
            else:
                # Wait for file to be available
                logger.info(f"⏳ {agent_id} waiting for file: {file_path}")
                await self._wait_for_file_lock(agent_id, file_path)
                locked_files.append(file_path)
        
        try:
            # Step 2: Execute the actual work (call existing agent_service)
            # But with coordination hooks
            result = await agent_service._run_agent_once(
                agent_id=agent_id,
                project_token=project_token,
                task_token=None,  # Master manages tasks, not external system
                coordination_mode=True  # New flag to indicate coordinated execution
            )
            
            # Step 3: Report progress periodically
            await master_task_manager.report_task_progress(
                agent_id,
                {"status": "in_progress", "progress": 50}
            )
            
            return result
            
        finally:
            # Step 4: Always release file locks
            for file_path in locked_files:
                await master_task_manager.release_file_lock(agent_id, file_path)
    
    def _extract_file_intents_from_task(self, task: Dict[str, Any]) -> List[str]:
        """
        Extract which files this task will likely modify
        """
        # Simple heuristic based on task type and description
        file_intents = []
        
        task_type = task.get("classified_type", "backend")
        title = task.get("title", "").lower()
        description = task.get("description", "").lower()
        
        if task_type == "backend":
            file_intents.extend([
                "backend/main.py",
                "backend/models.py", 
                "backend/requirements.txt"
            ])
        elif task_type == "frontend":
            file_intents.extend([
                "frontend/src/",
                "frontend/package.json"
            ])
        elif task_type == "setup":
            file_intents.extend([
                "README.md",
                "docker-compose.yml",
                ".env"
            ])
        
        return file_intents
    
    async def _wait_for_file_lock(self, agent_id: str, file_path: str, max_wait: int = 300):
        """
        Wait for file lock to become available
        """
        waited = 0
        while waited < max_wait:
            lock_result = await master_task_manager.request_file_lock(agent_id, file_path)
            if lock_result["granted"]:
                return
            
            await asyncio.sleep(10)
            waited += 10
        
        raise Exception(f"Timeout waiting for file lock: {file_path}")

# Global coordination service
master_coordination_service = MasterCoordinationService()