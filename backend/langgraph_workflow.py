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

    result = await agent_service.ensure_master_workspace_note(
        project_token=state.get("project_token"),
        task_token=state.get("task_token"),
    )
    errors = list(state.get("errors") or [])
    if not result.get("success") and not result.get("skipped"):
        reason = result.get("error") or result.get("reason") or "unknown error"
        errors.append(f"master note: {reason}")
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
        {"agent_id": agent_id, "task": task}
        for agent_id, task in claimed.get("assignments", [])
    ]
    return {"assignments": assignments}


def _route_after_planning(state: AgentWorkflowState) -> str:
    if state.get("assignments"):
        return "run_parallel_agents"
    return "finalize"


async def _run_parallel_agents(state: AgentWorkflowState) -> Dict[str, Any]:
    import agent_service

    assignments = state.get("assignments") or []
    if not assignments:
        return {"results": [], "launched_agents": [], "errors": []}

    async def _run_one(entry: Dict[str, Any]) -> Dict[str, Any]:
        agent_id = entry["agent_id"]
        task = entry["task"]
        try:
            result = await agent_service.run_agent(
                agent_id,
                assigned_task=task,
                continuous=True,
                ignore_running_check=True,
                project_token=state.get("project_token"),
                task_token=state.get("task_token"),
            )
            if isinstance(result, dict):
                result.setdefault("agent_id", agent_id)
            return result
        except Exception as exc:
            logger.exception("LangGraph workflow failed for %s", agent_id)
            return {
                "success": False,
                "agent_id": agent_id,
                "error": str(exc),
            }

    results = await asyncio.gather(*(_run_one(entry) for entry in assignments))
    errors = [
        f"{item.get('agent_id')}: {item.get('error')}"
        for item in results
        if isinstance(item, dict) and item.get("error")
    ]
    return {
        "results": results,
        "launched_agents": [entry["agent_id"] for entry in assignments],
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
    assignments = state.get("assignments") or []
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
        "launched": len(assignments),
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
