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
    import agent_service
    
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
    import agent_service

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
    import agent_service

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
    import agent_service
    
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
    import agent_service
    
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
    
    # Post-execution coordination
    await _post_execution_coordination(agent_id, result, state)
    
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
    """Extract which files this task intends to modify"""
    # Implementation would parse task description for file paths
    return []

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
    # Check dependencies
    # Request file locks
    # Wait for sync points if needed
    pass

async def _post_execution_coordination(agent_id: str, result: Dict[str, Any], state: SynchronizedAgentState):
    """Coordination updates after agent execution"""
    # Release file locks
    # Update shared context
    # Signal sync point completion
    pass

async def _check_sync_points(state: SynchronizedAgentState):
    """Check and manage synchronization points"""
    pass

async def _resolve_file_conflicts(state: SynchronizedAgentState):
    """Resolve file access conflicts between agents"""
    pass

async def _update_shared_context(state: SynchronizedAgentState):
    """Update shared context with latest information"""
    pass

async def _resolve_blocked_agents(state: SynchronizedAgentState):
    """Identify and resolve blocked agents"""
    pass

async def _manage_phase_gates(state: SynchronizedAgentState):
    """Manage project phase transitions"""
    pass

def _handle_file_access(agent_id: str, file_path: str, state: SynchronizedAgentState):
    """Handle file access coordination"""
    pass

def _handle_progress_update(agent_id: str, progress: Dict[str, Any], state: SynchronizedAgentState):
    """Handle agent progress updates"""
    pass

def _handle_sync_request(agent_id: str, sync_type: str, state: SynchronizedAgentState):
    """Handle agent synchronization requests"""
    pass

def _handle_agent_communication(agent_id: str, message: Dict[str, Any], state: SynchronizedAgentState):
    """Handle inter-agent communication"""
    pass


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
    import agent_service
    
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