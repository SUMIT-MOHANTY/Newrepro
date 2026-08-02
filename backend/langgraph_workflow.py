import asyncio
from coordination_monitor import start_coordination_monitor, stop_coordination_monitor
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
    logger.info("[LangGraph] Publishing master workspace note (Bypassed - Zero token mode)...")
    return {
        "master_note": {"success": True, "approved": True, "workspace_tree": ""},
        "errors": list(state.get("errors") or []),
    }
    
    errors = list(state.get("errors") or [])
    project_token = state.get("project_token")
    
    if not result.get("success") and not result.get("skipped"):
        reason = result.get("error") or result.get("reason") or "unknown error"
        errors.append(f"master note: {reason}")
        
        # Persist failure to database
        set_bootstrap_failed(project_token, str(reason))
        
        # Broadcast failure - coordination monitor will create fix task
        db = SessionLocal()
        try:
            await comm.send_message(
                db=db,
                project_token=project_token or "",
                from_agent="MASTER_AGENT",
                message=f"🚫 Bootstrap failed: {reason}. Coordination monitor will create fix task.",
                msg_type="BLOCKED",
                payload={"bootstrap_failure": True, "error": str(reason)}
            )
        finally:
            db.close()
        
        agent_service._log_master_agent(
            f"⚠️ Master plan note failed: {reason} - Coordination monitor will handle recovery",
            level="warning",
            project_token=project_token,
        )
        
        # Don't set agents to failed - let coordination monitor create fix task
        # Agents will pick up the bootstrap fix task automatically
        
    else:
        # Success - persist to database
        save_bootstrap_planning_note(
            project_token,
            master_note_id=result.get("note_id"),
            workspace_tree=result.get("workspace_tree")
        )
        
        # Check if bootstrap task needs to be executed
        if not is_bootstrap_pushed(project_token):
            try:
                tasks = await agent_service._fetch_external_tasks(project_token)
            except Exception as fetch_exc:
                logger.warning(f"[LangGraph] Failed to fetch external tasks for checking bootstrap: {fetch_exc}")
                tasks = []
            
            bootstrap_task = next(
                (t for t in tasks if (
                    str(t.get("task_id") or t.get("external_id") or "").upper().startswith("TASK-00")
                    or "bootstrap" in str(t.get("title") or t.get("taskName") or "").lower()
                )),
                None
            )
            
            if bootstrap_task:
                agent_service._log_master_agent(
                    f"🚀 Master Agent executing bootstrap task: {bootstrap_task.get('title') or bootstrap_task.get('taskName') or 'Untitled'}",
                    project_token=project_token,
                )
                
                # Fetch Git credentials for this project
                repo_creds = agent_service._resolve_project_git_credentials(project_token, state.get("agents_config"))
                git_repo_url = repo_creds.get("repo_url")
                git_token = repo_creds.get("token")
                
                try:
                    run_result = await agent_service.run_agent(
                        agent_id="M_agent_01",
                        git_repo_url=git_repo_url,
                        git_token=git_token,
                        assigned_task=bootstrap_task,
                        project_token=project_token,
                        task_token=state.get("task_token"),
                    )
                    
                    if not run_result or not run_result.get("success"):
                        run_error = (run_result.get("error") if run_result else None) or "Unknown execution error"
                        agent_service._log_master_agent(
                            f"❌ Master Agent bootstrap execution failed: {run_error}",
                            project_token=project_token,
                            level="error",
                        )
                        set_bootstrap_failed(project_token, run_error)
                        errors.append(f"bootstrap execution failed: {run_error}")
                        
                        # Broadcast failure
                        db = SessionLocal()
                        try:
                            await comm.send_message(
                                db=db,
                                project_token=project_token or "",
                                from_agent="MASTER_AGENT",
                                message=f"🚫 Bootstrap failed: {run_error}. Coordination monitor will create fix task.",
                                msg_type="BLOCKED",
                                payload={"bootstrap_failure": True, "error": str(run_error)}
                            )
                        finally:
                            db.close()
                            
                        return {
                            "master_note": result,
                            "errors": errors,
                        }
                    else:
                        agent_service._log_master_agent(
                            "✅ Master Agent bootstrap execution succeeded.",
                            project_token=project_token,
                        )
                except Exception as run_exc:
                    logger.exception(f"[LangGraph] Master Agent bootstrap execution failed: {run_exc}")
                    set_bootstrap_failed(project_token, str(run_exc))
                    errors.append(f"bootstrap execution failed: {str(run_exc)}")
                    
                    # Broadcast failure
                    db = SessionLocal()
                    try:
                        await comm.send_message(
                            db=db,
                            project_token=project_token or "",
                            from_agent="MASTER_AGENT",
                            message=f"🚫 Bootstrap failed: {run_exc}. Coordination monitor will create fix task.",
                            msg_type="BLOCKED",
                            payload={"bootstrap_failure": True, "error": str(run_exc)}
                        )
                    finally:
                        db.close()
                        
                    return {
                        "master_note": result,
                        "errors": errors,
                    }
            else:
                from bootstrap_persistence import get_bootstrap_branch
                existing_branch = get_bootstrap_branch(project_token)
                final_branch = existing_branch if existing_branch else "no-git"

                # No bootstrap task exists in the list of tasks. Mark as success with the branch.
                agent_service._log_master_agent(
                    f"ℹ️ No bootstrap task found in the plan. Setting bootstrap success branch '{final_branch}'.",
                    project_token=project_token,
                )
                set_bootstrap_success(
                    project_token,
                    master_note_id=result.get("note_id"),
                    workspace_tree=result.get("workspace_tree"),
                    bootstrap_branch=final_branch
                )
        
        # Broadcast success
        db = SessionLocal()
        try:
            await comm.send_message(
                db=db,
                project_token=project_token or "",
                from_agent="MASTER_AGENT",
                message=f"✅ Bootstrap complete! Project structure ready.",
                msg_type="READY",
                payload={"bootstrap_success": True}
            )
        finally:
            db.close()
        
        agent_service._log_master_agent(
            f"✅ Master plan note published: {result.get('title')}",
            project_token=project_token,
        )
        agent_service.complete_run_all_waiting_state(
            project_token,
            success=True,
        )
    
    return {
        "master_note": result,
        "errors": errors,
    }


def _route_after_master_note(state: AgentWorkflowState) -> str:
    master_note = state.get("master_note") or {}
    # Even if bootstrap fails, proceed to planning
    # Coordination monitor will create fix task automatically
    # Don't pause workflow - let agents handle it
    return "plan_assignments"


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
    from coordination_monitor import start_coordination_monitor, stop_coordination_monitor

    assignments = state.get("assignments") or []
    project_token = state.get("project_token")
    
    # START COORDINATION MONITOR - handles all self-healing
    monitor = await start_coordination_monitor(project_token)
    logger.info(f"[LangGraph] Coordination monitor started for {project_token}")
    
    try:
        if not assignments:
            return {"results": [], "launched_agents": [], "errors": []}

        # Initialize coordination for this project
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

        # Run agents strictly sequentially (one task completed before the next starts)
        results = []
        for entry in assignments:
            res = await _run_coordinated_agent(entry.get("agent_id"), entry.get("assigned_task"))
            results.append(res)
        
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
    
    finally:
        # STOP COORDINATION MONITOR when agents complete
        stop_coordination_monitor(project_token)
        logger.info(f"[LangGraph] Coordination monitor stopped for {project_token}")


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
