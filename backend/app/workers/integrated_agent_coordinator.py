"""
Integrated Agent Coordinator
─────────────────────────────
The single source of truth that BRIDGES all 6 coordination systems:

  1. MasterTaskManager        — task queue, dependency graph, agent assignment
  2. AgentCoordinationService — agent status, sync points, phase gates
  3. EnhancedContextService   — rich context, file ownership, API registry, memory board
  4. AgentCommunicationService— pub/sub messaging, blocker resolution
  5. CoordinatedAgentWrapper  — per-agent coordination hooks
  6. AgentContractStore       — file locks, heartbeats, deadlock detection, API contracts

BEFORE this coordinator, the 6 systems were independent silos.
AFTER this coordinator, Master has REAL-TIME AWARENESS of:
  - What EVERY agent is doing (task, files, status, progress)
  - Which agents are ALIVE vs CRASHED (heartbeat-based)
  - Which FILES are locked and by whom (unified lock table)
  - Which agents are STUCK and need HELP (blocker auto-detection)
  - What the BRD requires and which tasks deliver it (BRD-aware routing)
  - Auto-RETRY on failure (failed tasks → reassign to next best agent)

NOTE: This module does NOT import master_coordination_service to avoid
circular imports. Instead, master_coordination_service imports from this
module and uses it as the integration layer.
"""

import asyncio
import logging
import time
from typing import Dict, List, Optional, Any, Set
from datetime import datetime
from dataclasses import dataclass, field

# ── All 6 systems (safe imports, no circular dependency) ──────────────────
from master_task_manager import master_task_manager

from agent_coordination_service import (
    coordination_service,    # ← existing global instance, not new ACS()
    CoordinationEventType,
)
from agent_communication_service import (
    send_message,
    broadcast_blocked,
    broadcast_ready,
    check_and_auto_resolve,
    get_active_blockers,
)
from enhanced_context_service import (
    enhanced_context_service,
    AgentContextUpdate,
    ContextMessageType,
)

import agent_contract_store as contract_store

from app.core.database import SessionLocal

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# 1. DATA CLASSES
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class AgentLiveStatus:
    """Real-time status of a single agent."""
    agent_id: str
    project_token: str
    status: str = "idle"
    current_task: Optional[str] = None
    current_task_id: Optional[str] = None
    progress: int = 0
    files_locked: List[str] = field(default_factory=list)
    files_created: List[str] = field(default_factory=list)
    files_modified: List[str] = field(default_factory=list)
    blocked_on: Optional[str] = None
    blocked_reason: Optional[str] = None
    waiting_for_dependencies: List[str] = field(default_factory=list)
    last_heartbeat: float = 0.0
    task_retries: int = 0
    assigned_by: str = "master"  # master | starvation_detector | retry

@dataclass
class ProjectCoordState:
    """Complete coordination state for one project."""
    project_token: str
    agents: Dict[str, AgentLiveStatus] = field(default_factory=dict)
    file_locks: Dict[str, str] = field(default_factory=dict)
    brd_analysis: Optional[Dict[str, Any]] = None
    brd_goals: List[str] = field(default_factory=list)
    brd_prerequisites: List[str] = field(default_factory=list)
    sync_points_completed: Set[str] = field(default_factory=set)
    phase_gates: Dict[str, bool] = field(default_factory=lambda: {
        "planning": False, "development": False, "integration": False,
        "testing": False, "deployment": False,
    })
    created_at: float = 0.0

# ─────────────────────────────────────────────────────────────────────────────
# 2. INTEGRATED COORDINATOR
# ─────────────────────────────────────────────────────────────────────────────

class IntegratedAgentCoordinator:
    """
    The ONE coordinator that integrates all 6 systems.

    Does NOT import master_coordination_service to avoid circular imports.
    The master_coordination_service imports and uses this coordinator.

    Usage:
        from integrated_agent_coordinator import coordinator

        await coordinator.start_coordinated_project(
            project_token="PROJ-001",
            tasks=[...],
            agents=[...],
            brd_analysis={...}
        )

        status = coordinator.get_comprehensive_status("PROJ-001")
    """

    def __init__(self):
        self._projects: Dict[str, ProjectCoordState] = {}
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._auto_retry_task: Optional[asyncio.Task] = None

    # ── PROJECT LIFECYCLE ──────────────────────────────────────────────────

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
        Initialize subsystems directly — does NOT call back to
        master_coordination_service (avoids circular recursion).

        Called by master_coordination_service.start_coordinated_project().
        """
        logger.info(f"🎯 IntegratedCoordinator initializing project: {project_token}")

        # 1. Initialize MasterTaskManager
        await master_task_manager.initialize_project(project_token, tasks, agents)

        # 2. Initialize AgentCoordinationService (uses existing global instance)
        agents_config = {a: {"capabilities": ["fullstack"]} for a in agents}
        await coordination_service.initialize_project_coordination(
            project_token, agents_config, {"tasks": tasks}
        )

        # 3. Initialize EnhancedContextService
        await enhanced_context_service.initialize_project_context(
            project_token, agents_config
        )

        # 4. Create local state with agent tracking
        state = ProjectCoordState(
            project_token=project_token,
            created_at=time.time(),
        )

        for agent_id in agents:
            state.agents[agent_id] = AgentLiveStatus(
                agent_id=agent_id,
                project_token=project_token,
                last_heartbeat=time.time(),
            )

        # 5. Extract BRD context
        if brd_analysis:
            state.brd_analysis = brd_analysis
            state.brd_goals = brd_goals or self._extract_brd_goals(brd_analysis)
            state.brd_prerequisites = brd_prerequisites or self._extract_brd_prerequisites(brd_analysis)

        self._projects[project_token] = state

        # 6. Start background monitors
        self._ensure_background_tasks()

        logger.info(
            f"✅ IntegratedCoordinator project {project_token} ready: "
            f"{len(tasks)} tasks, {len(agents)} agents, "
            f"{len(state.brd_goals)} BRD goals, {len(state.brd_prerequisites)} BRD prerequisites"
        )

        return {
            "status": "initialized",
            "project_token": project_token,
            "total_tasks": len(tasks),
            "available_agents": len(agents),
            "systems_initialized": {
                "master_task_manager": True,
                "agent_coordination_service": True,
                "enhanced_context_service": True,
                "agent_communication_service": True,
                "agent_contract_store": True,
            },
        }

    # ── AGENT LIFECYCLE (Single source of truth for status updates) ────────

    async def on_agent_status_change(
        self,
        project_token: str,
        agent_id: str,
        new_status: str,
        task_info: Optional[Dict[str, Any]] = None,
        progress: Optional[int] = None,
    ) -> None:
        """
        Called whenever an agent's status changes.
        Syncs ALL 6 systems in a single call.
        """
        state = self._get_state(project_token)
        if not state or agent_id not in state.agents:
            return

        agent = state.agents[agent_id]
        old_status = agent.status
        agent.status = new_status
        agent.last_heartbeat = time.time()

        if task_info:
            agent.current_task = task_info.get("title") or task_info.get("taskName", "")
            agent.current_task_id = (
                str(task_info.get("id"))
                or str(task_info.get("external_id"))
                or str(task_info.get("task_id"))
                or agent.current_task_id
            )

        if progress is not None:
            agent.progress = progress

        # ── Sync to MasterTaskManager ──────────────────────────────────────
        try:
            await master_task_manager.report_task_progress(agent_id, {
                "status": new_status,
                "progress": progress or 0,
                "task": agent.current_task,
            })
        except Exception as e:
            logger.debug(f"MasterTaskManager sync error: {e}")

        # ── Sync to AgentCoordinationService (global instance) ─────────────
        try:
            await coordination_service.update_agent_status(
                project_token, agent_id, new_status, task_info
            )
        except Exception as e:
            logger.debug(f"AgentCoordinationService sync error: {e}")

        # ── Sync to EnhancedContextService ─────────────────────────────────
        try:
            ctx_update = AgentContextUpdate(
                agent_id=agent_id,
                timestamp=datetime.utcnow().isoformat(),
                current_task=agent.current_task,
                current_files=agent.files_locked + agent.files_created,
                status=new_status,
                blocked_on=agent.blocked_on,
            )
            await enhanced_context_service.update_agent_context(
                project_token, ctx_update
            )
        except Exception as e:
            logger.debug(f"EnhancedContextService sync error: {e}")

        # ── Sync to AgentContractStore (heartbeat) ─────────────────────────
        try:
            await contract_store.heartbeat(project_token, agent_id)
        except Exception as e:
            logger.debug(f"ContractStore heartbeat error: {e}")

        # ── Broadcast via AgentCommunicationService ────────────────────────
        if new_status != old_status:
            try:
                db = SessionLocal()
                try:
                    await send_message(
                        db=db,
                        project_token=project_token,
                        from_agent=agent_id,
                        message=f"Status: {old_status} → {new_status}" + (
                            f" | Task: {agent.current_task}" if agent.current_task else ""
                        ),
                        msg_type="INFO",
                        related_task_id=agent.current_task_id,
                    )
                finally:
                    db.close()
            except Exception as e:
                logger.debug(f"CommService broadcast error: {e}")

        # ── Check if this resolves someone's dependency ────────────────────
        if new_status in ("completed", "ready"):
            await self._on_agent_completed(project_token, agent_id, agent)

        logger.info(
            f"🤖 [{project_token}] {agent_id}: {old_status} → {new_status}"
            + (f" ({agent.current_task})" if agent.current_task else "")
        )

    async def on_agent_file_locked(
        self, project_token: str, agent_id: str, file_path: str
    ) -> bool:
        """
        Unified file locking — routes through AgentContractStore as source of truth.
        Also syncs to MasterTaskManager and local state.
        Skips if project_token is empty (caller didn't provide one).
        """
        if not project_token:
            return False

        state = self._get_state(project_token)
        if not state:
            return False

        success = await contract_store.acquire_file_lock(project_token, agent_id, file_path)
        if not success:
            logger.warning(f"🔒 [{project_token}] {agent_id} DENIED lock on {file_path}")
            return False

        # Update local state
        state.file_locks[file_path] = agent_id
        if agent_id in state.agents and file_path not in state.agents[agent_id].files_locked:
            state.agents[agent_id].files_locked.append(file_path)

        # Sync to MasterTaskManager
        try:
            await master_task_manager.request_file_lock(agent_id, file_path)
        except Exception:
            pass

        # Log to EnhancedContext memory board
        try:
            await enhanced_context_service.post_to_memory_board(
                project_token, agent_id,
                ContextMessageType.ANNOUNCEMENT,
                f"🔒 Locked file: {file_path}",
                tags=[f"file:{file_path}", "lock"],
            )
        except Exception:
            pass

        return True

    async def on_agent_file_released(
        self, project_token: str, agent_id: str, file_path: str
    ) -> bool:
        """Unified file release — routes through AgentContractStore."""
        await contract_store.release_file_lock(project_token, agent_id, file_path)

        state = self._get_state(project_token)
        if state:
            state.file_locks.pop(file_path, None)
            if agent_id in state.agents and file_path in state.agents[agent_id].files_locked:
                state.agents[agent_id].files_locked.remove(file_path)

        try:
            await master_task_manager.release_file_lock(agent_id, file_path)
        except Exception:
            pass

        return True

    async def on_agent_files_created(
        self, project_token: str, agent_id: str, files: List[str]
    ) -> None:
        """Register files created by an agent."""
        state = self._get_state(project_token)
        if not state or agent_id not in state.agents:
            return

        state.agents[agent_id].files_created.extend(files)

        try:
            ctx_update = AgentContextUpdate(
                agent_id=agent_id,
                timestamp=datetime.utcnow().isoformat(),
                created_files=files,
                tags=["file_created"],
            )
            await enhanced_context_service.update_agent_context(project_token, ctx_update)
        except Exception:
            pass

    async def on_agent_blocked(
        self,
        project_token: str,
        agent_id: str,
        reason: str,
        needs: Optional[str] = None,
    ) -> None:
        """Agent is blocked — broadcast to all agents AND notify Master."""
        state = self._get_state(project_token)
        if not state or agent_id not in state.agents:
            return

        state.agents[agent_id].blocked_on = needs
        state.agents[agent_id].blocked_reason = reason
        state.agents[agent_id].status = "blocked"

        db = SessionLocal()
        try:
            await broadcast_blocked(
                db=db,
                project_token=project_token,
                from_agent=agent_id,
                reason=reason,
                related_task_id=state.agents[agent_id].current_task_id,
                needs=needs,
            )
        finally:
            db.close()

        try:
            await enhanced_context_service.post_to_memory_board(
                project_token, agent_id,
                ContextMessageType.BLOCKER,
                f"🚫 BLOCKED: {reason}" + (f" | Needs: {needs}" if needs else ""),
                tags=["blocked", needs] if needs else ["blocked"],
            )
        except Exception:
            pass

        logger.warning(
            f"🚫 [{project_token}] {agent_id} BLOCKED: {reason}"
            + (f" (needs: {needs})" if needs else "")
        )

    async def on_agent_ready(
        self,
        project_token: str,
        agent_id: str,
        what_is_ready: str,
    ) -> None:
        """Agent completed something — resolve blockers and notify dependents."""
        state = self._get_state(project_token)
        if not state or agent_id not in state.agents:
            return

        state.agents[agent_id].blocked_on = None
        state.agents[agent_id].blocked_reason = None

        # Single DB session for all operations
        db = SessionLocal()
        try:
            # Broadcast ready signal
            await broadcast_ready(
                db=db,
                project_token=project_token,
                from_agent=agent_id,
                what_is_ready=what_is_ready,
                related_task_id=state.agents[agent_id].current_task_id,
            )

            # Auto-resolve blockers waiting for this completion
            resolved_count = await check_and_auto_resolve(
                db=db,
                project_token=project_token,
                from_agent=agent_id,
                what_was_built=what_is_ready,
            )
            if resolved_count > 0:
                logger.info(f"✅ [{project_token}] {agent_id} auto-resolved {resolved_count} blocker(s)")
        finally:
            db.close()

        try:
            await enhanced_context_service.post_to_memory_board(
                project_token, agent_id,
                ContextMessageType.COMPLETION,
                f"✅ READY: {what_is_ready}",
                tags=["ready", "completion"],
            )
        except Exception:
            pass

    # ── AGENT CRASH DETECTION (Heartbeat Monitor) ──────────────────────────

    async def _heartbeat_monitor_loop(self):
        """
        Background loop checking agent heartbeats every 30 seconds.
        Detects crashed agents → releases locks → auto-retries tasks.
        Protected by top-level try/except to prevent silent death.
        """
        HEARTBEAT_TIMEOUT = 120  # seconds without heartbeat = crashed

        while True:
            try:
                await asyncio.sleep(30)
                now = time.time()

                for project_token, state in list(self._projects.items()):
                    crashed_agents = []

                    for agent_id, agent in list(state.agents.items()):
                        age = now - agent.last_heartbeat

                        if age > HEARTBEAT_TIMEOUT and agent.status not in ("idle", "completed", "crashed"):
                            agent.status = "crashed"
                            crashed_agents.append(agent_id)

                            logger.warning(
                                f"💀 [{project_token}] Agent {agent_id} CRASHED "
                                f"(no heartbeat for {age:.0f}s) | Last task: {agent.current_task}"
                            )

                            # Release file locks held by crashed agent
                            try:
                                await contract_store.release_all_locks(project_token, agent_id)
                            except Exception:
                                pass

                            # Remove locks from local state
                            for fp in [fp for fp, aid in list(state.file_locks.items()) if aid == agent_id]:
                                del state.file_locks[fp]

                            # Broadcast crash
                            db = SessionLocal()
                            try:
                                await send_message(
                                    db=db,
                                    project_token=project_token,
                                    from_agent="master",
                                    message=f"💀 Agent {agent_id} crashed (no heartbeat). Reassigning tasks.",
                                    msg_type="WARNING",
                                )
                            finally:
                                db.close()

                            # Auto-retry the task
                            if agent.current_task_id or agent.current_task:
                                await self._auto_retry_failed_agent(project_token, agent_id)

                    if crashed_agents:
                        logger.info(f"⚰️ [{project_token}] Crashed agents: {crashed_agents}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Heartbeat monitor error: {e}", exc_info=True)
                await asyncio.sleep(30)  # Don't tight-loop on error

    # ── AUTO-RETRY (Failed Agent → Reassign) ───────────────────────────────

    async def _auto_retry_failed_agent(
        self, project_token: str, failed_agent_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        When an agent fails or crashes:
          1. Find its task in MasterTaskManager's queue
          2. Find next best idle agent (exclude the failed one)
          3. Reassign with AI-based selection
          4. Notify the new agent via communication service
        Max 3 retries per task.
        """
        state = self._get_state(project_token)
        if not state:
            return None

        # Find the task in MasterTaskManager's queue
        failed_task = None
        for task in master_task_manager.task_queue:
            if task.get("assigned_agent") == failed_agent_id:
                failed_task = task
                break

        if not failed_task:
            agent = state.agents.get(failed_agent_id)
            target_title = agent.current_task if agent else None
            if target_title:
                for task in master_task_manager.task_queue:
                    if task.get("title") == target_title:
                        failed_task = task
                        break

        if not failed_task:
            logger.warning(f"❌ [{project_token}] No task found for crashed agent {failed_agent_id}")
            return None

        # Reset task status
        failed_task["status"] = "pending"
        failed_task["assigned_agent"] = None
        failed_task["_retry_count"] = failed_task.get("_retry_count", 0) + 1

        # Check retry limit
        if failed_task["_retry_count"] > 3:
            logger.error(
                f"🚨 [{project_token}] Task '{failed_task.get('title')}' "
                f"failed {failed_task['_retry_count']} times. Max retries exceeded."
            )
            failed_task["status"] = "failed_max_retries"
            return {"status": "max_retries_exceeded", "task": failed_task}

        # Find idle agents (exclude failed and crashed ones)
        idle_agents = [
            aid for aid, a in state.agents.items()
            if a.status == "idle" and aid != failed_agent_id
        ]
        if not idle_agents:
            logger.warning(f"❌ [{project_token}] No idle agents available to retry task")
            failed_task["status"] = "pending_retry"
            return {"status": "no_idle_agents", "task": failed_task}

        # AI-based agent selection via MasterTaskManager
        try:
            best_agent = await master_task_manager.choose_best_agent_for_task_public(
                failed_task, idle_agents
            )
            if not best_agent:
                best_agent = idle_agents[0]
        except Exception:
            best_agent = idle_agents[0]

        # Reassign
        master_task_manager.agent_assignments[best_agent] = failed_task
        master_task_manager.agent_status[best_agent] = "assigned"
        failed_task["assigned_agent"] = best_agent
        failed_task["status"] = "assigned"
        failed_task["_force_assigned"] = True
        failed_task["_retry_of"] = failed_agent_id

        if best_agent in state.agents:
            state.agents[best_agent].task_retries += 1
            state.agents[best_agent].assigned_by = "retry"

        logger.info(
            f"🔄 [{project_token}] RETRY: Task '{failed_task.get('title')}' "
            f"reassigned from {failed_agent_id} to {best_agent} "
            f"(retry #{failed_task['_retry_count']}/3)"
        )

        db = SessionLocal()
        try:
            await send_message(
                db=db,
                project_token=project_token,
                from_agent="master",
                to_agent=best_agent,
                message=(
                    f"🔄 RETRY: Task '{failed_task.get('title')}' "
                    f"(previously assigned to {failed_agent_id} which crashed). "
                    f"Retry #{failed_task['_retry_count']}/3."
                ),
                msg_type="INFO",
                related_task_id=str(failed_task.get("id") or failed_task.get("external_id", "")),
                payload={
                    "retry_of": failed_agent_id,
                    "retry_count": failed_task["_retry_count"],
                    "task": failed_task,
                    "previous_agent": failed_agent_id,
                },
            )
        finally:
            db.close()

        return {
            "status": "reassigned",
            "task": failed_task,
            "from_agent": failed_agent_id,
            "to_agent": best_agent,
            "retry_count": failed_task["_retry_count"],
            "max_retries": 3,
        }

    async def _auto_retry_monitor_loop(self):
        """
        Background loop checking for failed agents every 15 seconds.
        Protected by top-level try/except to prevent silent death.
        """
        while True:
            try:
                await asyncio.sleep(15)

                for project_token, state in list(self._projects.items()):
                    failed_agents = [
                        aid for aid, a in state.agents.items()
                        if a.status in ("failed", "error") and a.task_retries < 3
                    ]
                    for agent_id in failed_agents:
                        await self._auto_retry_failed_agent(project_token, agent_id)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Auto-retry monitor error: {e}", exc_info=True)
                await asyncio.sleep(30)

    # ── DEPENDENCY AUTO-RESOLUTION ─────────────────────────────────────────

    async def _on_agent_completed(
        self, project_token: str, agent_id: str, agent: AgentLiveStatus
    ) -> None:
        """
        When an agent completes a task, check EnhancedContextService's
        dependency graph and unblock any dependent agents.
        """
        state = self._get_state(project_token)
        if not state:
            return

        completed_task_title = agent.current_task or agent.current_task_id or ""

        try:
            deps = await enhanced_context_service.query_context(
                project_token, "dependencies", {"agent_id": agent_id}
            )
            depended_by = deps.get("depended_by", [])

            for dependent_agent_id in depended_by:
                if dependent_agent_id in state.agents:
                    dep_agent = state.agents[dependent_agent_id]
                    if dep_agent.status == "blocked":
                        dep_agent.blocked_on = None
                        dep_agent.blocked_reason = None

                        db = SessionLocal()
                        try:
                            await send_message(
                                db=db,
                                project_token=project_token,
                                from_agent="master",
                                to_agent=dependent_agent_id,
                                message=(
                                    f"✅ Dependency resolved: {agent_id} completed "
                                    f"'{completed_task_title}'. You can proceed."
                                ),
                                msg_type="RESOLVED",
                                related_task_id=dep_agent.current_task_id,
                                payload={
                                    "resolved_by": agent_id,
                                    "completed_task": completed_task_title,
                                },
                            )
                        finally:
                            db.close()

                        logger.info(
                            f"✅ [{project_token}] Dependency resolved: "
                            f"{dependent_agent_id} was waiting for {agent_id}"
                        )
        except Exception as e:
            logger.debug(f"Dependency resolution check error: {e}")

        try:
            await enhanced_context_service.post_to_memory_board(
                project_token, agent_id,
                ContextMessageType.COMPLETION,
                f"✅ Completed: {completed_task_title}",
                tags=["completed", completed_task_title.lower().replace(" ", "_")],
            )
        except Exception:
            pass

    # ── BRD-AWARE TASK ROUTING ─────────────────────────────────────────────

    def _extract_brd_goals(self, brd_analysis: Dict[str, Any]) -> List[str]:
        """Extract business goals from BRD analysis."""
        goals = []
        if not isinstance(brd_analysis, dict):
            return goals
        for key in ("businessGoals", "goals", "business_goals", "objectives", "summary"):
            val = brd_analysis.get(key)
            if isinstance(val, str) and val.strip():
                goals.append(val.strip())
            elif isinstance(val, list):
                for item in val:
                    if isinstance(item, str):
                        goals.append(item.strip())
                    elif isinstance(item, dict) and item.get("goal"):
                        goals.append(item["goal"].strip())
        return goals

    def _extract_brd_prerequisites(self, brd_analysis: Dict[str, Any]) -> List[str]:
        """Extract prerequisites from BRD analysis."""
        prereqs = []
        if not isinstance(brd_analysis, dict):
            return prereqs
        for key in ("prerequisites", "preRequisites", "pre_requisites", "assumptions", "dependencies"):
            val = brd_analysis.get(key)
            if isinstance(val, str) and val.strip():
                prereqs.append(val.strip())
            elif isinstance(val, list):
                for item in val:
                    if isinstance(item, str):
                        prereqs.append(item.strip())
                    elif isinstance(item, dict):
                        for k in ("name", "description", "item"):
                            v = item.get(k)
                            if v and isinstance(v, str):
                                prereqs.append(v.strip())
                                break
        return prereqs

    def get_brd_aware_task_priority(self, project_token: str, task: Dict[str, Any]) -> int:
        """
        Calculate BRD-aware task priority (higher = more important).

        Factors:
          - Prerequisite task: +50
          - Delivers a BRD goal: +30
          - Related to BRD prerequisites: +20
          - Deep dependency chain: -10 per level
        """
        state = self._get_state(project_token)
        if not state:
            return 0

        priority = 0
        task_text = (str(task.get("title") or "") + " " +
                     str(task.get("description") or "")).lower()

        for prereq in state.brd_prerequisites:
            if prereq.lower() in task_text:
                priority += 50
                break

        for goal in state.brd_goals:
            goal_keywords = goal.lower().split()
            if any(kw in task_text for kw in goal_keywords):
                priority += 30
                break

        deps = task.get("linked_tasks", []) or task.get("dependencies", [])
        if isinstance(deps, list):
            priority -= len(deps) * 10

        return priority

    # ── COMPREHENSIVE STATUS API ───────────────────────────────────────────

    def get_comprehensive_status(self, project_token: str) -> Dict[str, Any]:
        """
        Get COMPLETE real-time status of all agents, tasks, and coordination.
        Single API replacing 6 separate system queries.
        """
        state = self._get_state(project_token)
        if not state:
            return {"error": "Project not found"}

        completed = [t for t in master_task_manager.task_queue if t.get("status") == "completed"]
        in_progress = [t for t in master_task_manager.task_queue
                       if t.get("status") in ("assigned", "in_progress")]
        pending = [t for t in master_task_manager.task_queue if t.get("status") == "pending"]
        failed = [t for t in master_task_manager.task_queue
                  if t.get("status") in ("failed", "failed_max_retries", "error")]

        total = len(master_task_manager.task_queue)
        crashed_agents = contract_store.get_crashed_agents(project_token)
        alive_agents = [aid for aid in state.agents if aid not in crashed_agents]

        active_blockers = []
        try:
            db = SessionLocal()
            try:
                active_blockers = get_active_blockers(db, project_token)
            finally:
                db.close()
        except Exception:
            pass

        return {
            "project_token": project_token,
            "timestamp": datetime.utcnow().isoformat(),

            "tasks": {
                "total": total,
                "completed": len(completed),
                "in_progress": len(in_progress),
                "pending": len(pending),
                "failed": len(failed),
                "completion_pct": round(len(completed) / total * 100, 1) if total else 0,
            },

            "agents": {
                "total": len(state.agents),
                "alive": len(alive_agents),
                "crashed": len(crashed_agents),
                "blocked": sum(1 for a in state.agents.values() if a.status == "blocked"),
                "idle": sum(1 for a in state.agents.values() if a.status == "idle"),
                "working": sum(1 for a in state.agents.values()
                               if a.status in ("assigned", "working", "in_progress")),
            },

            "agent_details": {
                aid: {
                    "status": a.status,
                    "current_task": a.current_task,
                    "progress": a.progress,
                    "files_locked": len(a.files_locked),
                    "files_created": len(a.files_created),
                    "blocked_on": a.blocked_on,
                    "task_retries": a.task_retries,
                    "heartbeat_age_s": round(time.time() - a.last_heartbeat, 1) if a.last_heartbeat else -1,
                }
                for aid, a in state.agents.items()
            },

            "file_locks": dict(state.file_locks),
            "file_locks_count": len(state.file_locks),

            "active_blockers": [
                {
                    "id": b.get("id"),
                    "from_agent": b.get("from_agent"),
                    "message": (b.get("message") or "")[:150],
                    "created_at": b.get("created_at"),
                }
                for b in active_blockers
            ],

            "phase_gates": dict(state.phase_gates),

            "brd": {
                "has_goals": bool(state.brd_goals),
                "has_prerequisites": bool(state.brd_prerequisites),
                "goals_count": len(state.brd_goals),
                "prerequisites_count": len(state.brd_prerequisites),
            },
        }

    # ── API CONTRACT PUBLISHING (Backend → Frontend sync) ─────────────────

    async def publish_api_contracts(
        self,
        project_token: str,
        agent_id: str,
        endpoints: List[Dict[str, Any]],
    ) -> None:
        """Backend agent publishes API endpoints for frontend agents to consume."""
        await contract_store.publish_api_contract(project_token, agent_id, endpoints)

    async def get_api_contracts_for_frontend(self, project_token: str) -> Dict[str, Any]:
        """Frontend agent gets all known API endpoints before building UI."""
        return await contract_store.get_api_contracts(project_token)

    # ── INTERNAL HELPERS ───────────────────────────────────────────────────

    def _get_state(self, project_token: str) -> Optional[ProjectCoordState]:
        return self._projects.get(project_token)

    def _ensure_background_tasks(self):
        """Start heartbeat and auto-retry monitors if not already running."""
        if self._heartbeat_task is None or self._heartbeat_task.done():
            self._heartbeat_task = asyncio.create_task(
                self._heartbeat_monitor_loop(),
                name="integrated-heartbeat-monitor",
            )
        if self._auto_retry_task is None or self._auto_retry_task.done():
            self._auto_retry_task = asyncio.create_task(
                self._auto_retry_monitor_loop(),
                name="integrated-auto-retry",
            )

    # ── LEGACY PATH TRACKING (safe, no project state mutation) ─────────────

    def track_agent_event(
        self,
        project_token: str,
        agent_id: str,
        event_type: str,
        message: str = "",
    ) -> None:
        """
        Lightweight event tracking for legacy agent paths.

        Unlike on_agent_status_change(), this method does NOT require the
        project to be registered in the coordinator. It just logs the event
        and optionally stores it in a simple event buffer.

        Called from:
          - _bg_run_agent() in main.py (legacy greenfield dispatch)
          - run_brownfield_agent() in brownfield_agent_service.py

        This gives Master Agent basic awareness of ALL agents,
        even those running via legacy code paths.
        """
        logger.info(
            f"📡 [{project_token}] LEGACY EVENT: {agent_id} - {event_type}"
            + (f" | {message}" if message else "")
        )

        # Also try to update AgentContractStore for heartbeat tracking
        try:
            asyncio.create_task(
                contract_store.heartbeat(project_token, agent_id)
            )
        except Exception:
            pass

    def stop_project(self, project_token: str) -> None:
        """Clean up resources for a project."""
        if project_token in self._projects:
            del self._projects[project_token]

        logger.info(f"🛑 [{project_token}] Coordinator stopped")


# ── GLOBAL INSTANCE ─────────────────────────────────────────────────────────

coordinator = IntegratedAgentCoordinator()
