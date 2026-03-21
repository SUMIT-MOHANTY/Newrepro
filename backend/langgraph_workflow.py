import asyncio
import logging
import uuid
from typing import Any, Dict, List, Optional, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

logger = logging.getLogger(__name__)


class AgentWorkflowState(TypedDict, total=False):
    project_token: Optional[str]
    task_token: Optional[str]
    agents_config: Dict[str, Dict[str, str]]
    master_note: Dict[str, Any]
    assignments: List[Dict[str, Any]]
    launched_agents: List[str]
    results: List[Dict[str, Any]]
    errors: List[str]
    merge_queue_drained: bool
    summary: Dict[str, Any]


_CHECKPOINTER = InMemorySaver()


async def _publish_master_workspace_note(state: AgentWorkflowState) -> Dict[str, Any]:
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
    return {
        "master_note": result,
        "errors": errors,
    }


def _route_after_master_note(state: AgentWorkflowState) -> str:
    master_note = state.get("master_note") or {}
    if master_note.get("success"):
        return "plan_assignments"
    return "finalize"


async def _plan_assignments(state: AgentWorkflowState) -> Dict[str, Any]:
    import agent_service

    try:
        claimed = await agent_service._claim_initial_task_assignments(
            agents_config=state.get("agents_config"),
            project_token=state.get("project_token"),
            task_token=state.get("task_token"),
        )
    except Exception as exc:
        logger.warning("Initial task planning produced no launchable assignments: %s", exc)
        errors = list(state.get("errors") or [])
        errors.append(f"planning: {str(exc)}")
        return {
            "assignments": [],
            "errors": errors,
        }
    assignments = [
        {"agent_id": agent_id, "assigned_task": task}
        for agent_id, task in claimed.get("assignments", [])
    ]
    return {"assignments": assignments}


def _route_after_planning(state: AgentWorkflowState) -> str:
    if state.get("assignments"):
        return "run_parallel_agents"
    return "finalize"


async def _run_parallel_agents(state: AgentWorkflowState) -> Dict[str, Any]:
    import agent_service
    from coordinated_agent_wrapper import run_coordinated_agent
    from agent_coordination_service import initialize_project_coordination

    assignments = state.get("assignments") or []
    if not assignments:
        return {"results": [], "launched_agents": [], "errors": []}

    # Initialize coordination for this project
    project_token = state.get("project_token")
    agents_config = state.get("agents_config", {})
    master_note = state.get("master_note", {})
    
    # Initialize coordination state
    try:
        await initialize_project_coordination(
            project_token,
            agents_config,
            master_note
        )
        logger.info(f"Coordination initialized for project {project_token} with {len(agents_config)} agents")
    except Exception as coord_err:
        logger.warning(f"Coordination initialization failed: {coord_err}")

    launched_agents: List[str] = []
    for entry in assignments:
        agent_id = str(entry.get("agent_id") or "").strip()
        if agent_id and agent_id not in launched_agents:
            launched_agents.append(agent_id)

    async def _run_coordinated_agent(agent_id: str, assigned_task: dict = None) -> Dict[str, Any]:
        try:
            # Pull per-agent git credentials from agents_config
            agent_cfg = agents_config.get(agent_id) or {}
            git_repo_url = agent_cfg.get("git_repo_url") or None
            git_token = agent_cfg.get("git_token") or None

            # Use coordinated agent wrapper instead of direct agent call
            result = await run_coordinated_agent(
                agent_id=agent_id,
                project_token=project_token,
                original_run_agent_func=agent_service.run_agent,
                assigned_task=assigned_task,
                continuous=True,
                ignore_running_check=True,
                task_token=state.get("task_token"),
                git_repo_url=git_repo_url,
                git_token=git_token,
            )
            if isinstance(result, dict):
                result.setdefault("agent_id", agent_id)
            return result
        except Exception as exc:
            logger.exception("Coordinated LangGraph workflow failed for %s", agent_id)
            return {
                "success": False,
                "agent_id": agent_id,
                "error": str(exc),
                "tasks_completed": 0,
            }

    # Run agents with coordination
    results = await asyncio.gather(
        *(_run_coordinated_agent(entry.get("agent_id"), entry.get("assigned_task")) for entry in assignments)
    )
    
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


async def _await_merge_completion(state: AgentWorkflowState) -> Dict[str, Any]:
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


async def _finalize(state: AgentWorkflowState) -> Dict[str, Any]:
    results = state.get("results") or []
    launched_agents = state.get("launched_agents") or []
    master_note = state.get("master_note") or {}
    summary = {
        "workflow": "langgraph",
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
        "merge_queue_drained": state.get("merge_queue_drained", True),
        "errors": state.get("errors") or [],
    }
    return {"summary": summary}


def _build_workflow():
    builder = StateGraph(AgentWorkflowState)
    builder.add_node("publish_master_workspace_note", _publish_master_workspace_note)
    builder.add_node("plan_assignments", _plan_assignments)
    builder.add_node("run_parallel_agents", _run_parallel_agents)
    builder.add_node("await_merge_completion", _await_merge_completion)
    builder.add_node("finalize", _finalize)
    builder.add_edge(START, "publish_master_workspace_note")
    builder.add_conditional_edges(
        "publish_master_workspace_note",
        _route_after_master_note,
        {
            "plan_assignments": "plan_assignments",
            "finalize": "finalize",
        },
    )
    builder.add_conditional_edges(
        "plan_assignments",
        _route_after_planning,
        {
            "run_parallel_agents": "run_parallel_agents",
            "finalize": "finalize",
        },
    )
    builder.add_edge("run_parallel_agents", "await_merge_completion")
    builder.add_edge("await_merge_completion", "finalize")
    builder.add_edge("finalize", END)
    return builder.compile(checkpointer=_CHECKPOINTER)


_WORKFLOW = _build_workflow()


async def run_agent_supervisor_workflow(
    *,
    agents_config: Dict[str, Dict[str, str]] = None,
    project_token: Optional[str] = None,
    task_token: Optional[str] = None,
) -> Dict[str, Any]:
    workflow_id = f"agent-supervisor::{project_token or 'default'}::{uuid.uuid4().hex[:8]}"
    final_state = await _WORKFLOW.ainvoke(
        {
            "project_token": project_token,
            "task_token": task_token,
            "agents_config": agents_config or {},
        },
        {"configurable": {"thread_id": workflow_id}},
    )
    return final_state.get("summary", {})
