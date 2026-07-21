"""
Master Coordination Service - Integration layer between Master Task Manager and existing system

NOW INTEGRATED with IntegratedCoordinator for:
  - Real-time agent heartbeat tracking
  - Auto-retry on agent failure
  - Unified file locking across all 6 systems
  - BRD-aware task prioritization
  - Dependency auto-resolution
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any
from master_task_manager import master_task_manager
import agent_service

# Integration with all 6 coordination systems
from integrated_agent_coordinator import coordinator as integrated_coordinator

logger = logging.getLogger(__name__)

class MasterCoordinationService:
    """
    Bridges the Master Task Manager with existing agent_service
    Ensures ONLY the Master controls task assignment

    Now integrated with IntegratedCoordinator for:
      - Heartbeat monitoring (detect crashed agents)
      - Auto-retry on failure (max 3 retries)
      - Unified file locking (prevents same-file conflicts)
      - BRD-aware routing (prerequisites first, goals-driven)
      - Dependency auto-resolution
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
        agents: List[str],
        brd_analysis: Optional[Dict[str, Any]] = None,
        brd_goals: Optional[List[str]] = None,
        brd_prerequisites: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Start a project with full integration across all 6 coordination systems.
        
        This is the entry point — it initializes the IntegratedCoordinator which
        bridges MasterTaskManager, AgentCoordinationService, EnhancedContextService,
        AgentCommunicationService, CoordinatedAgentWrapper, and AgentContractStore.
        """
        logger.info(f"🎯 Starting coordinated project: {project_token}")
        
        # 1. Initialize IntegratedCoordinator (bridges all 6 systems)
        await integrated_coordinator.start_coordinated_project(
            project_token=project_token,
            tasks=tasks,
            agents=agents,
            brd_analysis=brd_analysis,
            brd_goals=brd_goals,
            brd_prerequisites=brd_prerequisites,
        )
        
        # 2. Mark project as active
        self.active_projects[project_token] = True
        
        # 3. Initialize starvation tracker for this project
        self._starvation_cycles[project_token] = {a: 0 for a in agents}
        
        # 4. Apply BRD-aware task prioritization
        if brd_analysis or brd_goals:
            await self._apply_brd_task_prioritization(project_token)
        
        # 5. Start the coordination loop
        asyncio.create_task(self._coordination_loop(project_token))
        
        # 6. Launch starvation detector (safety net for stuck agents)
        asyncio.create_task(self._starvation_detector(project_token))
        
        return {
            "status": "started",
            "project_token": project_token,
            "total_tasks": len(tasks),
            "available_agents": len(agents),
            "systems_integrated": [
                "master_task_manager",
                "agent_coordination_service",
                "enhanced_context_service",
                "agent_communication_service",
                "coordinated_agent_wrapper",
                "agent_contract_store",
            ],
            "message": "All 6 coordination systems integrated and controlling all agents",
        }
    
    async def _apply_brd_task_prioritization(self, project_token: str) -> None:
        """
        Re-prioritize tasks based on BRD analysis.
        Prerequisite tasks get moved to the front of the queue.
        BRD-goal-aligned tasks get priority boost.
        """
        try:
            # Calculate BRD priority for each task
            task_scores = []
            for i, task in enumerate(master_task_manager.task_queue):
                priority = integrated_coordinator.get_brd_aware_task_priority(project_token, task)
                task_scores.append((priority, i, task))

            # Sort by priority (descending), keeping original order for ties
            task_scores.sort(key=lambda x: (-x[0], x[1]))
            
            # Rebuild queue with sorted tasks
            master_task_manager.task_queue = [t[2] for t in task_scores]
            
            # Update sequence numbers
            for idx, task in enumerate(master_task_manager.task_queue):
                task["_brd_priority"] = task_scores[idx][0]
                
            logger.info(f"📊 [{project_token}] BRD-aware task prioritization applied to {len(master_task_manager.task_queue)} tasks")
        except Exception as e:
            logger.error(f"❌ BRD prioritization error: {e}")
    
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
        Run an agent under Master coordination with full integration.
        
        Now integrated with IntegratedCoordinator for:
          - Real-time status sync across all 6 systems
          - Heartbeat tracking (AgentContractStore)
          - File lock management (unified)
          - Progress updates to EnhancedContextService
          - Auto-retry on failure
        """
        logger.info(f"🤖 Starting coordinated agent {agent_id} for task: {task['title']}")
        
        try:
            # ── STEP 1: Notify all systems that agent is starting ──────────
            await integrated_coordinator.on_agent_status_change(
                project_token, agent_id, "assigned",
                task_info=task, progress=0
            )
            
            # ── STEP 2: Predict files and acquire locks ────────────────────
            predicted_files = self._extract_file_intents_from_task(task)
            for file_path in predicted_files:
                await integrated_coordinator.on_agent_file_locked(
                    project_token, agent_id, file_path
                )
            
            # ── STEP 3: Run the actual agent work ──────────────────────────
            result = await self._execute_agent_task(agent_id, task, project_token)
            
            # ── STEP 4: On success, sync completion ────────────────────────
            await integrated_coordinator.on_agent_status_change(
                project_token, agent_id, "completed",
                task_info=task, progress=100
            )
            
            # Release predicted file locks
            for file_path in predicted_files:
                await integrated_coordinator.on_agent_file_released(
                    project_token, agent_id, file_path
                )
            
            # Register files created (if any in result)
            files_created = (result or {}).get("files_created", [])
            if files_created:
                await integrated_coordinator.on_agent_files_created(
                    project_token, agent_id, files_created
                )
            
            # Signal readiness for dependency resolution
            await integrated_coordinator.on_agent_ready(
                project_token, agent_id,
                what_is_ready=task.get("title", "")
            )
            
            # Report completion to MasterTaskManager
            await master_task_manager.complete_task(agent_id, result)
            
        except Exception as e:
            logger.error(f"❌ Agent {agent_id} failed: {e}")
            
            # Report failure through IntegratedCoordinator (triggers auto-retry)
            await integrated_coordinator.on_agent_status_change(
                project_token, agent_id, "failed",
                task_info=task, progress=0
            )
            
            # Broadcast blocker
            await integrated_coordinator.on_agent_blocked(
                project_token, agent_id,
                reason=str(e),
                needs=f"Fix for task: {task.get('title', '')}"
            )
            
            # Report failure to MasterTaskManager
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
            # Release any file locks this agent held using unified coordinator
            state = master_task_manager
            for file_path, holder in list(state.file_locks.items()):
                if holder == agent_id:
                    await integrated_coordinator.on_agent_file_released(
                        project_token, agent_id, file_path
                    )
    
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
        Wait for file lock to become available.
        Uses MasterTaskManager's native locking (no project_token available here).
        """
        waited = 0
        while waited < max_wait:
            result = await master_task_manager.request_file_lock(agent_id, file_path)
            if result.get("granted"):
                return
            await asyncio.sleep(10)
            waited += 10
        raise Exception(f"Timeout waiting for file lock: {file_path}")

# Global coordination service
master_coordination_service = MasterCoordinationService()