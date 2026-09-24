import asyncio
import logging
import uuid
from typing import Any, Dict, List, Optional, TypedDict, Set
from datetime import datetime, timedelta
from enum import Enum

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

logger = logging.getLogger(__name__)


class AgentStatus(Enum):
    IDLE = "idle"
    WORKING = "working"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    FAILED = "failed"


class SynchronizedAgentState(TypedDict, total=False):
    project_token: Optional[str]
    task_token: Optional[str]
    agents_config: Dict[str, Dict[str, str]]
    
    # Shared coordination state
    shared_context: Dict[str, Any]  # Global project context all agents can see
    agent_statuses: Dict[str, AgentStatus]  # Real-time agent status tracking
    task_progress: Dict[str, Dict[str, Any]]  # Task progress with dependencies
    file_locks: Dict[str, str]  # File-level locking (file_path -> agent_id)
    communication_log: List[Dict[str, Any]]  # Inter-agent communication
    
    # Coordination checkpoints
    sync_points: List[Dict[str, Any]]  # Synchronization checkpoints
    current_phase: str  # Current project phase
    phase_gates: Dict[str, bool]  # Phase completion gates
    
    # Results and monitoring
    assignments: List[Dict[str, Any]]
    launched_agents: List[str]
    results: List[Dict[str, Any]]
    errors: List[str]
    merge_queue_drained: bool
    summary: Dict[str, Any]


_CHECKPOINTER = InMemorySaver()


async def _initialize_coordination_state(state: SynchronizedAgentState) -> Dict[str, Any]:
    """Initialize shared coordination state for all agents"""
    from app.services.agents import agent_service
    
    # Get project context and task dependencies
    project_token = state.get("project_token")
    
    # Initialize shared context
    shared_context = {
        "project_architecture": {},
        "file_structure": {},
        "dependencies": {},
        "coding_standards": {},
        "test_requirements": {},
        "deployment_config": {},
        "last_updated": datetime.utcnow().isoformat()
    }
    
    # Initialize agent tracking
    agents_config = state.get("agents_config", {})
    agent_statuses = {agent_id: AgentStatus.IDLE for agent_id in agents_config.keys()}
    
    # Initialize task progress tracking
    task_progress = {}
    
    # Initialize coordination structures
    sync_points = [
        {"name": "architecture_review", "required_agents": [], "completed": False},
        {"name": "integration_checkpoint", "required_agents": [], "completed": False},
        {"name": "testing_gate", "required_agents": [], "completed": False},
        {"name": "deployment_ready", "required_agents": [], "completed": False}
    ]
    
    phase_gates = {
        "planning": False,
        "development": False,
        "integration": False,
        "testing": False,
        "deployment": False
    }
    
    return {
        "shared_context": shared_context,
        "agent_statuses": agent_statuses,
        "task_progress": task_progress,
        "file_locks": {},
        "communication_log": [],
        "sync_points": sync_points,
        "current_phase": "planning",
        "phase_gates": phase_gates
    }


async def _publish_master_workspace_note(state: SynchronizedAgentState) -> Dict[str, Any]:
    """Enhanced master note with coordination context"""
    from app.services.agents import agent_service

    agent_service.prime_project_git_credentials(
        state.get("agents_config"),
        project_token=state.get("project_token"),
    )
    
    result = await agent_service.ensure_master_workspace_note(
        project_token=state.get("project_token"),
        task_token=state.get("task_token"),
    )
    
    errors = list(state.get("errors") or [])
    if not result.get("success") and not result.get("skipped"):
        reason = result.get("error") or result.get("reason") or "unknown error"
        errors.append(f"master note: {reason}")
        agent_service.complete_run_all_waiting_state(
            state.get("project_token"),
            success=False,
            error_message=str(reason),
        )
    else:
        agent_service.complete_run_all_waiting_state(
            state.get("project_token"),
            success=True,
        )
        
        # Update shared context with master plan
        shared_context = state.get("shared_context", {})
        shared_context.update({
            "master_plan": result.get("task_plan", {}),
            "project_structure": result.get("workspace_tree", {}),
            "last_updated": datetime.utcnow().isoformat()
        })
    
    return {
        "master_note": result,
        "errors": errors,
        "shared_context": shared_context,
        "phase_gates": {**state.get("phase_gates", {}), "planning": True}
    }


async def _plan_synchronized_assignments(state: SynchronizedAgentState) -> Dict[str, Any]:
    """Enhanced planning with dependency awareness and synchronization points"""
    from app.services.agents import agent_service

    try:
        claimed = await agent_service._claim_initial_task_assignments(
            agents_config=state.get("agents_config"),
            project_token=state.get("project_token"),
            task_token=state.get("task_token"),
        )
        
        assignments = []
        task_progress = {}
        
        for agent_id, task in claimed.get("assignments", []):
            # Analyze task dependencies
            task_deps = _analyze_task_dependencies(task, state.get("shared_context", {}))
            
            assignment = {
                "agent_id": agent_id,
                "assigned_task": task,
                "dependencies": task_deps,
                "sync_requirements": _determine_sync_requirements(task),
                "file_intents": _extract_file_intents(task)
            }
            assignments.append(assignment)
            
            # Track task progress
            task_id = task.get("id") or f"task_{len(task_progress)}"
            task_progress[task_id] = {
                "agent_id": agent_id,
                "status": TaskStatus.PENDING,
                "dependencies": task_deps,
                "progress": 0,
                "last_update": datetime.utcnow().isoformat(),
                "blocking_tasks": [],
                "blocked_by": []
            }
        
        # Update sync points with required agents
        sync_points = state.get("sync_points", [])
        for sync_point in sync_points:
            sync_point["required_agents"] = [a["agent_id"] for a in assignments 
                                           if _requires_sync_point(a, sync_point["name"])]
        
        return {
            "assignments": assignments,
            "task_progress": task_progress,
            "sync_points": sync_points
        }
        
    except Exception as exc:
        logger.warning("Synchronized task planning failed: %s", exc)
        errors = list(state.get("errors") or [])
        errors.append(f"planning: {str(exc)}")
        return {
            "assignments": [],
            "errors": errors,
        }


async def _run_coordinated_agents(state: SynchronizedAgentState) -> Dict[str, Any]:
    """Run agents with real-time coordination and synchronization"""
    from app.services.agents import agent_service
    
    assignments = state.get("assignments") or []
    if not assignments:
        return {"results": [], "launched_agents": [], "errors": []}

    launched_agents = []
    coordination_tasks = []
    
    # Start coordination monitor
    coordination_task = asyncio.create_task(
        _coordination_monitor(state)
    )
    coordination_tasks.append(coordination_task)
    
    # Launch agents with coordination wrapper
    async def _run_coordinated_agent(assignment: Dict[str, Any]) -> Dict[str, Any]:
        agent_id = assignment["agent_id"]
        assigned_task = assignment["assigned_task"]
        
        try:
            # Update agent status
            await _update_agent_status(state, agent_id, AgentStatus.WORKING)
            
            # Run agent with coordination hooks
            result = await _run_agent_with_coordination(
                agent_id=agent_id,
                assigned_task=assigned_task,
                state=state
            )
            
            # Update final status
            final_status = AgentStatus.COMPLETED if result.get("success") else AgentStatus.FAILED
            await _update_agent_status(state, agent_id, final_status)
            
            return result
            
        except Exception as exc:
            logger.exception("Coordinated agent execution failed for %s", agent_id)
            await _update_agent_status(state, agent_id, AgentStatus.FAILED)
            return {
                "success": False,
                "agent_id": agent_id,
                "error": str(exc),
                "tasks_completed": 0,
            }
    
    # Launch all agents
    for assignment in assignments:
        agent_id = assignment["agent_id"]
        if agent_id not in launched_agents:
            launched_agents.append(agent_id)
    
    # Run agents with coordination
    agent_tasks = [_run_coordinated_agent(assignment) for assignment in assignments]
    results = await asyncio.gather(*agent_tasks)
    
    # Stop coordination monitor
    coordination_task.cancel()
    
    errors = [
        f"{item.get('agent_id')}: {item.get('error')}"
        for item in results
        if isinstance(item, dict) and item.get("error")
    ]

    return {
        "results": results,
        "launched_agents": launched_agents,
        "errors": errors,
    }


async def _coordination_monitor(state: SynchronizedAgentState):
    """Background task to monitor and coordinate agent activities"""
    while True:
        try:
            # Check for sync point requirements
            await _check_sync_points(state)
            
            # Resolve file conflicts
            await _resolve_file_conflicts(state)
            
            # Update shared context
            await _update_shared_context(state)
            
            # Check for blocked agents
            await _resolve_blocked_agents(state)
            
            # Phase gate management
            await _manage_phase_gates(state)
            
            await asyncio.sleep(2)  # Check every 2 seconds
            
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.exception("Coordination monitor error: %s", exc)
            await asyncio.sleep(5)


async def _run_agent_with_coordination(
    agent_id: str, 
    assigned_task: Dict[str, Any], 
    state: SynchronizedAgentState
) -> Dict[str, Any]:
    """Run agent with coordination hooks and shared state awareness"""
    from app.services.agents import agent_service
    
    # Pre-execution coordination
    await _pre_execution_coordination(agent_id, assigned_task, state)
    
    # Enhanced agent execution with coordination callbacks
    result = await agent_service.run_agent(
        agent_id,
        assigned_task=assigned_task,
        continuous=True,
        ignore_running_check=True,
        project_token=state.get("project_token"),
        task_token=state.get("task_token"),
        coordination_state=state,  # Pass coordination state
        coordination_callbacks={
            "on_file_access": lambda file_path: _handle_file_access(agent_id, file_path, state),
            "on_progress_update": lambda progress: _handle_progress_update(agent_id, progress, state),
            "on_sync_request": lambda sync_type: _handle_sync_request(agent_id, sync_type, state),
            "on_communication": lambda message: _handle_agent_communication(agent_id, message, state)
        }
    )
    
    # Post-execution coordination — pass the original assigned_task for sync point tracking
    await _post_execution_coordination(agent_id, result, state, assigned_task=assigned_task)
    
    if isinstance(result, dict):
        result.setdefault("agent_id", agent_id)
    
    return result


# Coordination helper functions
def _analyze_task_dependencies(task: Dict[str, Any], shared_context: Dict[str, Any]) -> List[str]:
    """Analyze task dependencies from shared context"""
    # Implementation would analyze task requirements against shared context
    return []

def _determine_sync_requirements(task: Dict[str, Any]) -> List[str]:
    """Determine which sync points this task requires"""
    sync_reqs = []
    
    # Check task type and requirements
    if task.get("type") == "architecture":
        sync_reqs.append("architecture_review")
    if task.get("involves_integration"):
        sync_reqs.append("integration_checkpoint")
    if task.get("requires_testing"):
        sync_reqs.append("testing_gate")
    if task.get("deployment_related"):
        sync_reqs.append("deployment_ready")
        
    return sync_reqs

def _extract_file_intents(task: Dict[str, Any]) -> List[str]:
    """Extract which files this task intends to modify by parsing the description"""
    import re

    file_intents = set()

    # Get task description and title
    description = str(task.get("description") or task.get("taskDescription") or "")
    title = str(task.get("title") or task.get("taskName") or "")
    combined = title + " " + description

    # 1. Parse explicit file paths from description (e.g. "/src/app.js", "backend/api.py")
    file_paths = re.findall(
        r'(?:^|[\s,;:])(/[\w/.-]+\.[a-zA-Z]+|[\w/.-]+\.[a-zA-Z]{2,4})',
        combined
    )
    for fp in file_paths:
        fp = fp.strip().strip(",;.")
        if fp and len(fp) > 3:
            file_intents.add(fp)

    # 2. Parse checklist items that reference files
    checklist = task.get("checklist", [])
    if isinstance(checklist, list):
        for item in checklist:
            text = str(item.get("text", item)) if isinstance(item, dict) else str(item)
            paths_in_checklist = re.findall(
                r'(?:^|[\s,;:])(/[\w/.-]+\.[a-zA-Z]+|[\w/.-]+\.[a-zA-Z]{2,4})',
                text
            )
            for fp in paths_in_checklist:
                fp = fp.strip().strip(",;.")
                if fp and len(fp) > 3:
                    file_intents.add(fp)

    # 3. Extract from linked_files or planned_files if present
    for key in ("planned_files", "linked_files", "files"):
        files_list = task.get(key, [])
        if isinstance(files_list, list):
            for f in files_list:
                if isinstance(f, str) and f.strip():
                    file_intents.add(f.strip())

    result = sorted(file_intents)
    if result:
        logger.debug(f"Extracted file intents from task '{title[:40]}': {result}")

    return result

def _requires_sync_point(assignment: Dict[str, Any], sync_point_name: str) -> bool:
    """Check if assignment requires specific sync point"""
    return sync_point_name in assignment.get("sync_requirements", [])

async def _update_agent_status(state: SynchronizedAgentState, agent_id: str, status: AgentStatus):
    """Update agent status in shared state"""
    agent_statuses = state.get("agent_statuses", {})
    agent_statuses[agent_id] = status
    
    # Log status change
    communication_log = state.get("communication_log", [])
    communication_log.append({
        "timestamp": datetime.utcnow().isoformat(),
        "type": "status_update",
        "agent_id": agent_id,
        "status": status.value,
        "message": f"Agent {agent_id} status changed to {status.value}"
    })

async def _pre_execution_coordination(agent_id: str, task: Dict[str, Any], state: SynchronizedAgentState):
    """Coordination checks before agent execution"""
    project_token = state.get("project_token")
    if not project_token:
        return

    try:
        from agent_coordination_service import coordination_service

        # 1. Check task dependencies via agent_service task_ledger
        from app.services.agents import agent_service
        state_data = agent_service._ensure_project_state(project_token)
        ledger = state_data.get("task_ledger", {})
        dag = state_data.get("task_dag", {})
        task_id = str(task.get("id") or task.get("task_id") or "")
        if task_id and task_id in dag:
            deps = dag[task_id]
            for dep_id in deps:
                dep_entry = ledger.get(dep_id)
                if dep_entry and dep_entry.status not in ("done", "completed"):
                    logger.info(f"[{agent_id}] Waiting for dependency {dep_id} before starting {task_id}")
                    # Wait up to 30s for dep to complete
                    for _ in range(30):
                        dep_entry = ledger.get(dep_id)
                        if dep_entry and dep_entry.status in ("done", "completed"):
                            break
                        await asyncio.sleep(1)

        # 2. Request file locks for files this task intends to modify
        file_intents = _extract_file_intents(task)
        for file_path in file_intents:
            lock_result = await coordination_service.request_file_lock(
                project_token, agent_id, file_path, "write"
            )
            if not lock_result.get("success"):
                logger.warning(f"[{agent_id}] Could not lock {file_path}: {lock_result.get('error')}")

        # 3. Wait for required sync points
        sync_reqs = _determine_sync_requirements(task)
        for sync_name in sync_reqs:
            result = await coordination_service.request_sync_point(
                project_token, agent_id, sync_name, {"status": "ready"}
            )
            if result.get("sync_completed"):
                logger.info(f"[{agent_id}] Sync point {sync_name} already completed")
            elif not result.get("success"):
                logger.warning(f"[{agent_id}] Sync point {sync_name} not available")

        # 4. Update agent status to working
        await coordination_service.update_agent_status(
            project_token, agent_id, "working", {"task": task}
        )

        # 5. Log in communication log
        comm_log = state.get("communication_log", [])
        comm_log.append({
            "timestamp": datetime.utcnow().isoformat(),
            "type": "pre_execution",
            "agent_id": agent_id,
            "task_id": task_id,
            "message": f"Agent {agent_id} starting task {task_id}"
        })

    except Exception as e:
        logger.error(f"Pre-execution coordination failed for {agent_id}: {e}")


async def _post_execution_coordination(agent_id: str, result: Dict[str, Any], state: SynchronizedAgentState, assigned_task: Optional[Dict[str, Any]] = None):
    """Coordination updates after agent execution"""
    project_token = state.get("project_token")
    if not project_token:
        return

    try:
        from agent_coordination_service import coordination_service

        # 1. Release all file locks held by this agent
        agent_state = coordination_service.coordination_state.get(project_token, {})
        agent_info = agent_state.get("agents", {}).get(agent_id, {})
        for file_path in list(agent_info.get("file_locks", [])):
            await coordination_service.release_file_lock(project_token, agent_id, file_path)
            logger.info(f"[{agent_id}] Released lock on {file_path}")

        # 2. Update shared context with agent results
        if isinstance(result, dict):
            context_updates = {
                f"agent_results/{agent_id}": {
                    "success": result.get("success", False),
                    "files_created": result.get("files_written", []),
                    "branch": result.get("branch_name", ""),
                    "completed_at": datetime.utcnow().isoformat()
                }
            }
            await coordination_service.update_shared_context(
                project_token, agent_id, context_updates
            )

        # 3. Signal sync point completion for this agent
        # Use assigned_task if provided (more reliable than extracting from result)
        task_for_sync = assigned_task or result.get("assigned_task", {})
        sync_reqs = _determine_sync_requirements(task_for_sync)
        for sync_name in sync_reqs:
            await coordination_service.request_sync_point(
                project_token, agent_id, sync_name, {
                    "status": "completed",
                    "result": result.get("success", False)
                }
            )

        # 4. Update agent status
        final_status = "completed" if result.get("success") else "failed"
        await coordination_service.update_agent_status(
            project_token, agent_id, final_status
        )

        # 5. Log in communication log
        comm_log = state.get("communication_log", [])
        comm_log.append({
            "timestamp": datetime.utcnow().isoformat(),
            "type": "post_execution",
            "agent_id": agent_id,
            "success": result.get("success", False),
            "message": f"Agent {agent_id} completed with status {final_status}"
        })

    except Exception as e:
        logger.error(f"Post-execution coordination failed for {agent_id}: {e}")


async def _check_sync_points(state: SynchronizedAgentState):
    """Check and manage synchronization points"""
    project_token = state.get("project_token")
    if not project_token:
        return

    try:
        from agent_coordination_service import coordination_service

        coord_state = coordination_service.coordination_state.get(project_token)
        if not coord_state:
            return

        sync_points = coord_state.get("sync_points", {})
        task_progress = state.get("task_progress", {})

        for sync_name, sync_info in sync_points.items():
            if sync_info.get("status") == "completed":
                continue  # Already done

            required = set(sync_info.get("required_agents", []))
            completed = set(sync_info.get("completed_agents", []))

            if required and required.issubset(completed):
                sync_info["status"] = "completed"
                logger.info(f"Sync point {sync_name} COMPLETED - all agents synchronized")

                # Also update state's sync_points list
                for sp in state.get("sync_points", []):
                    if sp["name"] == sync_name:
                        sp["completed"] = True
                        break

        # Log current sync point status
        active_syncs = [s for s in sync_points.values() if s.get("status") != "completed"]
        if active_syncs:
            for s in active_syncs:
                waiting = set(s.get("required_agents", [])) - set(s.get("completed_agents", []))
                if waiting:
                    logger.debug(f"Sync '{s}' waiting for agents: {waiting}")

    except Exception as e:
        logger.error(f"Sync point check failed: {e}")


async def _resolve_file_conflicts(state: SynchronizedAgentState):
    """Resolve file access conflicts between agents"""
    project_token = state.get("project_token")
    if not project_token:
        return

    try:
        from agent_coordination_service import coordination_service

        coord_state = coordination_service.coordination_state.get(project_token)
        if not coord_state:
            return

        file_locks = coord_state.get("file_locks", {})

        # Track which files have multiple agents waiting
        file_access_counts: Dict[str, int] = {}
        for agent_id, agent_info in coord_state.get("agents", {}).items():
            for f in agent_info.get("file_locks", []):
                file_access_counts[f] = file_access_counts.get(f, 0) + 1

        # Detect conflicts: files locked by one agent while another agent also has interests
        comm_log = state.get("communication_log", [])
        for file_path, lock_info in file_locks.items():
            lock_holder = lock_info.get("agent_id")
            if not lock_holder:
                continue

            # Check if any other agent has this file in their intent list
            for agent_id, agent_info in coord_state.get("agents", {}).items():
                if agent_id == lock_holder:
                    continue
                if file_path in agent_info.get("file_locks", []):
                    logger.warning(f"File conflict detected: {file_path} locked by {lock_holder}, needed by {agent_id}")
                    comm_log.append({
                        "timestamp": datetime.utcnow().isoformat(),
                        "type": "file_conflict",
                        "file_path": file_path,
                        "locked_by": lock_holder,
                        "requested_by": agent_id,
                        "resolved": False
                    })

        # Log summary
        if file_access_counts:
            multi_access = {f: c for f, c in file_access_counts.items() if c > 1}
            if multi_access:
                logger.info(f"Files with multi-agent access: {multi_access}")

    except Exception as e:
        logger.error(f"File conflict resolution failed: {e}")


async def _update_shared_context(state: SynchronizedAgentState):
    """Update shared context with latest information"""
    project_token = state.get("project_token")
    if not project_token:
        return

    try:
        # Get latest from agent_service in-memory state
        from app.services.agents import agent_service
        state_data = agent_service._ensure_project_state(project_token)

        shared_context = state.get("shared_context", {})

        # Pull task progress (task_ledger) into shared context
        ledger = state_data.get("task_ledger", {})
        task_progress_summary = {}
        for task_id, entry in ledger.items():
            task_progress_summary[task_id] = {
                "status": entry.status,
                "agent_id": entry.agent_id,
                "title": entry.task_title,
                "files": entry.files_written[:5],
                "branch": entry.branch_name
            }
        shared_context["task_progress_summary"] = task_progress_summary

        # Pull DAG info
        dag = state_data.get("task_dag", {})
        shared_context["dependency_graph"] = {k: list(v) for k, v in dag.items()}

        # Pull agent statuses
        agent_statuses = {}
        for aid, astate in state_data.get("agent_states", {}).items():
            agent_statuses[aid] = {
                "status": astate.get("status", "unknown"),
                "current_task": str(astate.get("current_task", {}).get("id", "")),
                "progress": astate.get("progress", 0)
            }
        shared_context["agent_statuses"] = agent_statuses

        # Update timestamp
        shared_context["last_updated"] = datetime.utcnow().isoformat()

        # Also sync into coordination_service if available
        try:
            from agent_coordination_service import coordination_service
            coord_state = coordination_service.coordination_state.get(project_token)
            if coord_state:
                coord_state["shared_context"].update(shared_context)
        except Exception:
            pass

    except Exception as e:
        logger.error(f"Shared context update failed: {e}")


async def _resolve_blocked_agents(state: SynchronizedAgentState):
    """Identify and resolve blocked agents"""
    project_token = state.get("project_token")
    if not project_token:
        return

    try:
        from app.services.agents import agent_service
        state_data = agent_service._ensure_project_state(project_token)
        ledger = state_data.get("task_ledger", {})
        dag = state_data.get("task_dag", {})

        comm_log = state.get("communication_log", [])

        # Check each agent - are they stuck waiting for deps that are now met?
        for agent_id, agent_state_data in state_data.get("agent_states", {}).items():
            current_task = agent_state_data.get("current_task")
            if not current_task:
                continue

            task_id = str(current_task.get("id") or current_task.get("task_id") or "")
            if not task_id or task_id not in dag:
                continue

            deps = dag[task_id]
            if not deps:
                continue  # No dependencies, can't be blocked on deps

            # Check if all deps are done
            all_deps_met = True
            for dep_id in deps:
                dep_entry = ledger.get(dep_id)
                if not dep_entry or dep_entry.status not in ("done", "completed"):
                    all_deps_met = False
                    break

            if all_deps_met:
                # This agent's dependencies are met - unblock if blocked
                if agent_state_data.get("status") == "blocked":
                    logger.info(f"Unblocking agent {agent_id} - all dependencies for {task_id} are met")
                    agent_state_data["status"] = "idle"
                    agent_state_data["error"] = ""
                    comm_log.append({
                        "timestamp": datetime.utcnow().isoformat(),
                        "type": "agent_unblocked",
                        "agent_id": agent_id,
                        "task_id": task_id,
                        "message": f"Agent {agent_id} unblocked - dependencies met"
                    })

        # Also check coordination_service for blocked agents
        try:
            from agent_coordination_service import coordination_service
            coord_state = coordination_service.coordination_state.get(project_token)
            if coord_state:
                for agent_id, agent_info in coord_state.get("agents", {}).items():
                    waiting = agent_info.get("dependencies_waiting", [])
                    if waiting:
                        still_waiting = []
                        for dep_id in waiting:
                            dep_entry = ledger.get(dep_id)
                            if not dep_entry or dep_entry.status not in ("done", "completed"):
                                still_waiting.append(dep_id)
                            else:
                                logger.info(f"Dependency {dep_id} resolved for agent {agent_id}")
                        if len(still_waiting) < len(waiting):
                            agent_info["dependencies_waiting"] = still_waiting
        except Exception:
            pass

    except Exception as e:
        logger.error(f"Blocked agent resolution failed: {e}")


async def _manage_phase_gates(state: SynchronizedAgentState):
    """Manage project phase transitions"""
    project_token = state.get("project_token")
    if not project_token:
        return

    try:
        from agent_coordination_service import coordination_service

        coord_state = coordination_service.coordination_state.get(project_token)
        if not coord_state:
            return

        phase_order = ["planning", "development", "integration", "testing", "deployment"]
        current_phase = coord_state.get("current_phase", "planning")
        phase_gates = coord_state.get("phase_gates", {})

        # Map phases to sync points
        phase_sync_map = {
            "planning": [],
            "development": ["architecture_review"],
            "integration": ["integration_checkpoint"],
            "testing": ["testing_gate"],
            "deployment": ["deployment_ready"]
        }

        sync_points = coord_state.get("sync_points", {})

        # Check if current phase gates are met
        required_syncs = phase_sync_map.get(current_phase, [])
        phase_ready = True
        for sync_name in required_syncs:
            sync_info = sync_points.get(sync_name, {})
            if sync_info.get("status") != "completed":
                phase_ready = False
                break

        if phase_ready and not phase_gates.get(current_phase, False):
            # Mark current phase as completed
            phase_gates[current_phase] = True
            logger.info(f"Phase gate PASSED: {current_phase}")

            # Advance to next phase
            current_idx = phase_order.index(current_phase) if current_phase in phase_order else -1
            if current_idx >= 0 and current_idx < len(phase_order) - 1:
                next_phase = phase_order[current_idx + 1]
                coord_state["current_phase"] = next_phase
                logger.info(f"Advancing to phase: {next_phase}")

                # Log in communication
                comm_log = state.get("communication_log", [])
                comm_log.append({
                    "timestamp": datetime.utcnow().isoformat(),
                    "type": "phase_transition",
                    "from_phase": current_phase,
                    "to_phase": next_phase,
                    "message": f"Phase transition: {current_phase} -> {next_phase}"
                })

        # Also sync state's phase_gates
        phase_gates_state = state.get("phase_gates", {})
        phase_gates_state.update(phase_gates)

    except Exception as e:
        logger.error(f"Phase gate management failed: {e}")


def _handle_file_access(agent_id: str, file_path: str, state: SynchronizedAgentState):
    """Handle file access coordination - check if file is locked by another agent"""
    file_locks = state.get("file_locks", {})
    lock_info = file_locks.get(file_path)

    if lock_info and lock_info.get("agent_id") != agent_id:
        # File is locked by another agent
        logger.warning(f"File {file_path} is locked by {lock_info['agent_id']}, {agent_id} must wait")
        return {"granted": False, "locked_by": lock_info["agent_id"]}

    # Grant access
    file_locks[file_path] = {
        "agent_id": agent_id,
        "acquired_at": datetime.utcnow().isoformat()
    }
    return {"granted": True}


def _handle_progress_update(agent_id: str, progress: Dict[str, Any], state: SynchronizedAgentState):
    """Handle agent progress updates"""
    task_progress = state.get("task_progress", {})
    task_id = progress.get("task_id", f"agent_{agent_id}_task")

    # Update task progress
    task_progress[task_id] = {
        "agent_id": agent_id,
        "progress": progress.get("progress", 0),
        "status": progress.get("status", "in_progress"),
        "message": progress.get("message", ""),
        "last_update": datetime.utcnow().isoformat()
    }

    # Log status change for monitoring
    logger.debug(f"Progress update from {agent_id}: {progress.get('progress', 0)}% - {progress.get('message', '')[:50]}")


def _handle_sync_request(agent_id: str, sync_type: str, state: SynchronizedAgentState):
    """Handle agent synchronization requests"""
    sync_points = state.get("sync_points", [])

    for sp in sync_points:
        if sp["name"] == sync_type:
            # Ensure agent is tracked as having reached this sync point
            if "reached_agents" not in sp:
                sp["reached_agents"] = []
            if agent_id not in sp["reached_agents"]:
                sp["reached_agents"].append(agent_id)

            logger.info(f"Agent {agent_id} reached sync point: {sync_type}")

            # Check if all required agents have reached this point
            required = sp.get("required_agents", [])
            reached = sp.get("reached_agents", [])
            if required and set(required).issubset(set(reached)):
                sp["completed"] = True
                logger.info(f"Sync point {sync_type} COMPLETED by all agents")
            return True

    logger.warning(f"Unknown sync point requested: {sync_type} by agent {agent_id}")
    return False


def _handle_agent_communication(agent_id: str, message: Dict[str, Any], state: SynchronizedAgentState):
    """Handle inter-agent communication"""
    comm_log = state.get("communication_log", [])

    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "from_agent": agent_id,
        "message": message.get("text", str(message)),
        "msg_type": message.get("type", "general")
    }

    comm_log.append(entry)

    # Limit log size
    if len(comm_log) > 1000:
        state["communication_log"] = comm_log[-1000:]

    logger.info(f"Communication from {agent_id}: {entry['msg_type']} - {entry['message'][:80]}")


# Rest of the workflow functions (finalize, etc.) remain similar but use SynchronizedAgentState


def _build_synchronized_workflow():
    """Build the synchronized agent workflow"""
    builder = StateGraph(SynchronizedAgentState)
    
    builder.add_node("initialize_coordination", _initialize_coordination_state)
    builder.add_node("publish_master_workspace_note", _publish_master_workspace_note)
    builder.add_node("plan_synchronized_assignments", _plan_synchronized_assignments)
    builder.add_node("run_coordinated_agents", _run_coordinated_agents)
    builder.add_node("await_merge_completion", _await_merge_completion)
    builder.add_node("finalize", _finalize)
    
    # Build workflow edges
    builder.add_edge(START, "initialize_coordination")
    builder.add_edge("initialize_coordination", "publish_master_workspace_note")
    builder.add_conditional_edges(
        "publish_master_workspace_note",
        _route_after_master_note,
        {
            "plan_assignments": "plan_synchronized_assignments",
            "finalize": "finalize",
        },
    )
    builder.add_conditional_edges(
        "plan_synchronized_assignments",
        _route_after_planning,
        {
            "run_parallel_agents": "run_coordinated_agents",
            "finalize": "finalize",
        },
    )
    builder.add_edge("run_coordinated_agents", "await_merge_completion")
    builder.add_edge("await_merge_completion", "finalize")
    builder.add_edge("finalize", END)
    
    return builder.compile(checkpointer=_CHECKPOINTER)


# Reuse some functions from original workflow
async def _await_merge_completion(state: SynchronizedAgentState) -> Dict[str, Any]:
    from app.services.agents import agent_service
    
    drained = await agent_service.wait_for_git_merge_drain(
        project_token=state.get("project_token"),
        timeout_seconds=600.0,
        poll_interval=1.0,
    )
    errors = []
    if not drained:
        errors.append("git merge queue did not drain before workflow timeout")
    return {
        "merge_queue_drained": drained,
        "errors": (state.get("errors") or []) + errors,
    }


async def _finalize(state: SynchronizedAgentState) -> Dict[str, Any]:
    results = state.get("results") or []
    launched_agents = state.get("launched_agents") or []
    master_note = state.get("master_note") or {}
    
    summary = {
        "workflow": "synchronized_langgraph",
        "master_note": {
            "success": master_note.get("success"),
            "title": master_note.get("title"),
            "note_id": master_note.get("note_id"),
            "task_count": master_note.get("task_count"),
            "validation": master_note.get("validation"),
        },
        "launched": len(launched_agents),
        "agents": launched_agents,
        "results": results,
        "coordination_stats": {
            "sync_points_completed": len([sp for sp in state.get("sync_points", []) if sp.get("completed")]),
            "phase_gates_passed": len([pg for pg in state.get("phase_gates", {}).values() if pg]),
            "communication_events": len(state.get("communication_log", [])),
            "file_conflicts_resolved": 0  # Would track actual conflicts
        },
        "merge_queue_drained": state.get("merge_queue_drained", True),
        "errors": state.get("errors") or [],
    }
    return {"summary": summary}


def _route_after_master_note(state: SynchronizedAgentState) -> str:
    master_note = state.get("master_note") or {}
    if master_note.get("success"):
        return "plan_assignments"
    return "finalize"


def _route_after_planning(state: SynchronizedAgentState) -> str:
    if state.get("assignments"):
        return "run_parallel_agents"
    return "finalize"


_SYNCHRONIZED_WORKFLOW = _build_synchronized_workflow()


async def run_synchronized_agent_workflow(
    *,
    agents_config: Dict[str, Dict[str, str]] = None,
    project_token: Optional[str] = None,
    task_token: Optional[str] = None,
) -> Dict[str, Any]:
    """Run the synchronized agent workflow with full coordination"""
    workflow_id = f"sync-agent-supervisor::{project_token or 'default'}::{uuid.uuid4().hex[:8]}"
    
    final_state = await _SYNCHRONIZED_WORKFLOW.ainvoke(
        {
            "project_token": project_token,
            "task_token": task_token,
            "agents_config": agents_config or {},
        },
        {"configurable": {"thread_id": workflow_id}},
    )
    
    return final_state.get("summary", {})