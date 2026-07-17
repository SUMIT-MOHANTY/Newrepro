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

        # ── LAYER 3: Starvation Detection ───────────────────────────────────
        # Track consecutive "no task found" cycles per agent per project.
        # When an agent exceeds the threshold, the master force-assigns a task
        # ignoring lane restrictions — this is the safety net against starvation.
        self._starvation_cycles: Dict[str, Dict[str, int]] = {}  # project_token -> {agent_id: count}
        self._starvation_threshold: int = 5  # Consecutive empty polls before force-assign
    
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
        
        # Initialize starvation tracker for this project
        self._starvation_cycles[project_token] = {a: 0 for a in agents}
        
        # Start the coordination loop
        asyncio.create_task(self._coordination_loop(project_token))
        
        # ── LAYER 3: Launch starvation detector ────────────────────────────
        # Runs alongside the coordination loop as a safety net. Every 30s it
        # checks for agents stuck in empty polling loops and force-assigns tasks.
        asyncio.create_task(self._starvation_detector(project_token))
        
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
                    # assignment["assignments"] is a list of {agent_id, task_title, task_type}
                    for a in assignment.get("assignments", []):
                        agent_id = a["agent_id"]
                        # Find the actual task object from the task queue
                        task = next(
                            (t for t in master_task_manager.task_queue
                             if t.get("assigned_agent") == agent_id and t.get("status") == "assigned"),
                            None
                        )
                        if task:
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
    
    # ─────────────────────────────────────────────────────────────────────────
    # LAYER 3: Starvation Detection — safety net for agents stuck in empty polls
    # ─────────────────────────────────────────────────────────────────────────

    def _record_empty_poll(self, project_token: str, agent_id: str) -> int:
        """Record one empty polling cycle for an agent. Returns the consecutive count."""
        tracker = self._starvation_cycles.get(project_token, {})
        count = tracker.get(agent_id, 0) + 1
        tracker[agent_id] = count
        self._starvation_cycles[project_token] = tracker
        return count

    def _reset_starvation_counter(self, project_token: str, agent_id: str):
        """Reset starvation counter when agent picks up a task."""
        tracker = self._starvation_cycles.get(project_token, {})
        if agent_id in tracker:
            tracker[agent_id] = 0

    def _get_starved_agents(self, project_token: str) -> List[str]:
        """Return agent IDs whose consecutive empty polls exceed the threshold."""
        tracker = self._starvation_cycles.get(project_token, {})
        return [
            a for a, count in tracker.items()
            if count >= self._starvation_threshold
        ]

    async def _starvation_detector(self, project_token: str):
        """
        Run every 30 seconds as a safety net. Detects agents stuck in empty
        polling loops (starvation) and force-assigns a pending task to them,
        completely ignoring lane restrictions.
        """
        logger.info(f"🔍 Starvation detector started for {project_token} (threshold={self._starvation_threshold} empty polls)")

        while self.active_projects.get(project_token, False):
            await asyncio.sleep(30)

            try:
                starved = self._get_starved_agents(project_token)
                if not starved:
                    continue

                # Find pending tasks whose dependencies are met
                available = [
                    t for t in master_task_manager.task_queue
                    if t.get("status") == "pending"
                    and master_task_manager._task_dependencies_met(t)
                ]
                if not available:
                    continue

                logger.warning(
                    f"⚠️ Starvation detected — {len(starved)} agent(s) stuck, "
                    f"{len(available)} pending task(s). Force-assigning..."
                )

                for agent_id in starved:
                    if not available:
                        break

                    task = available.pop(0)

                    # Force-assign: bypass lane checks entirely
                    master_task_manager.agent_assignments[agent_id] = task
                    master_task_manager.agent_status[agent_id] = "assigned"
                    task["assigned_agent"] = agent_id
                    task["status"] = "assigned"
                    task["assigned_at"] = __import__("datetime").datetime.now().isoformat()
                    task["_force_assigned"] = True  # Marker so agent knows lane was overridden

                    self._reset_starvation_counter(project_token, agent_id)

                    logger.warning(
                        f"🚨 FORCE-ASSIGNED task '{task.get('title')}' to {agent_id} "
                        f"(lane restriction overridden by starvation detector)"
                    )

                    # Dispatch the agent immediately
                    asyncio.create_task(
                        self._run_coordinated_agent(agent_id, task, project_token)
                    )

            except Exception as e:
                logger.error(f"❌ Starvation detector error for {project_token}: {e}")

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
    
    def _resolve_real_agent_id(self, agent_id: str) -> str:
        """Map coordination agent IDs (dedicated_agent_01) to real agent IDs (agent_01)."""
        # dedicated_agent_01 → agent_01, dedicated_agent_02 → agent_02, etc.
        if agent_id.startswith("dedicated_agent_"):
            suffix = agent_id[len("dedicated_agent_"):]
            return f"agent_{suffix}"
        return agent_id

    async def _execute_agent_task(
        self, 
        agent_id: str, 
        task: Dict[str, Any], 
        project_token: str
    ) -> Dict[str, Any]:
        """Execute agent task using the real agent_service.run_agent."""
        real_agent_id = self._resolve_real_agent_id(agent_id)
        task_token = agent_service.get_project_task_token(project_token)

        logger.info(f"🚀 Dispatching {real_agent_id} (mapped from {agent_id}) for task: {task.get('title')}")

        try:
            result = await agent_service.run_agent(
                agent_id=real_agent_id,
                project_token=project_token,
                task_token=task_token,
                assigned_task=task,
            )
            return result or {}
        finally:
            # Release any file locks this agent held
            for file_path, holder in list(master_task_manager.file_locks.items()):
                if holder == agent_id:
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