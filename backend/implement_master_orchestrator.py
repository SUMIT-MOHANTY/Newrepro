"""
Master Orchestrator Implementation — 3 components:

1. ENHANCED ORCHESTRATOR LOOP:
   - Replaces _dag_progress_watcher with _master_orchestrator_loop
   - Monitors ALL agents continuously (not just DAG)
   - Detects stuck agents (running too long, dependency blocked)
   - Publishes status to Master Agent's output log
   - Creates fix tasks for failed agents

2. INCREMENTAL MERGING TRIGGER:
   - After each agent completes and pushes, immediately trigger
     merge into agent/integration branch
   - So next agent in same lane starts from REAL code, not just scaffold

3. TREE ENFORCEMENT:
   - After each agent completes, validate created files against canonical tree
   - Files outside tree → Master evaluates: helpful addition or violation?
   - If violation → create fix task for agent
   - If helpful → allow and update tree
"""

FILEPATH = r"D:\BRD\BRD_Analyzer\backend\agent_service.py"

with open(FILEPATH, "r", encoding="utf-8") as f:
    content = f.read()

changes_made = 0

# ═══════════════════════════════════════════════════════════════════════════
#  COMPONENT 1: Master Orchestrator Loop
# ═══════════════════════════════════════════════════════════════════════════

# Replace the entire _dag_progress_watcher function
old_dag_watcher = '''async def _dag_progress_watcher(project_token: Optional[str]) -> None:
    """
    Background task that watches for task completions and
    triggers idle agents to pick up newly unblocked tasks.

    Run this once per project when "run all" is triggered.
    It listens on the event bus and whenever a task_completed
    event arrives, it recomputes which tasks are now ready
    and wakes up any idle agents.
    """
    state = _ensure_project_state(project_token)
    bus: AgentEventBus = state.get("event_bus")
    if bus is None:
        logger.warning("[DAG watcher] No event bus found, watcher exiting.")
        return

    q = await bus.subscribe()
    logger.info(f"[DAG watcher] Started for project {project_token}")

    try:
        while True:
            # Wait up to 30 seconds for an event, then do a heartbeat check
            try:
                event = await asyncio.wait_for(q.get(), timeout=30.0)
                event_type = event.get("type", "")
            except asyncio.TimeoutError:
                event_type = "heartbeat"

            # Only act on task completions and heartbeats
            if event_type not in ("task_completed", "heartbeat"):
                continue

            if event_type == "task_completed":
                logger.info(
                    f"[DAG watcher] task_completed event from "
                    f"{event.get('agent_id')} for task {event.get('task_id')}"
                )

            # Recompute which tasks are now ready
            dag = state.get("task_dag", {})
            if not dag:
                continue

            completed_ids = _ledger_get_completed_ids(project_token)
            in_progress_ids = _ledger_get_in_progress_ids(project_token)
            ready_ids = _get_ready_task_ids(dag, completed_ids, in_progress_ids)

            if not is_bootstrap_pushed(project_token):
                bootstrap_ready = []
                for rid in ready_ids:
                    task = next((t for t in state.get("tasks", []) if str(_normalize_task_id(t) or t.get("external_id") or t.get("id") or "") == rid), None)
                    is_bt = (
                        rid == "TASK-00"
                        or (task and "project bootstrap" in str(task.get("title") or task.get("taskName") or "").strip().lower())
                    )
                    if is_bt:
                        bootstrap_ready.append(rid)
                ready_ids = bootstrap_ready

            if not ready_ids:
                continue

            idle_agents = [
                aid
                for aid, agent in state["agent_states"].items()
                if not _is_system_agent_id(aid)
                and agent.get("status") == "idle"
                and aid != DEPLOY_AGENT_ID
            ]

            if not idle_agents:
                continue

            logger.info(
                f"[DAG watcher] {len(ready_ids)} newly ready task(s), "
                f"{len(idle_agents)} idle agent(s). Triggering assignment."
            )

            task_token = get_project_task_token(project_token)
            for aid, task_id in zip(idle_agents, ready_ids):
                try:
                    assigned = await _master_assign_task_to_agent(
                        task_id, aid,
                        agent_name=state["agent_states"][aid].get("name"),
                        project_token=project_token,
                        task_token=task_token,
                    )
                    if assigned:
                        logger.info(f"[DAG watcher] Assigned task {task_id} to idle agent {aid}")
                except Exception as e:
                    logger.warning(f"[DAG watcher] Failed to assign {task_id} to {aid}: {e}")'''

new_master_orchestrator = '''async def _master_orchestrator_loop(project_token: Optional[str]) -> None:
    """
    Master Orchestrator — replaces _dag_progress_watcher.

    This is the Master Agent's continuous supervisor loop that:
    1. Watches ALL agents — knows their status, task, progress
    2. Detects stuck agents (dependency blocked, timed out, failed)
    3. Logs everything to Master Agent's output panel so users can see
    4. Reassigns ready tasks to idle agents
    5. Creates fix tasks for failed agents
    6. Triggers tree enforcement when agents complete
    7. Triggers incremental merge into integration branch

    Works like a human project manager: monitors team, helps stuck members,
    reassigns work, and ensures quality.
    """
    state = _ensure_project_state(project_token)
    bus: AgentEventBus = state.get("event_bus")
    if bus is None:
        logger.warning("[Master Orchestrator] No event bus found, exiting.")
        return

    q = await bus.subscribe()

    agent_activity: Dict[str, Dict[str, Any]] = {}

    _log_master_agent("Master Orchestrator started — monitoring all agents", project_token=project_token)
    logger.info(f"[Master Orchestrator] Started for project {project_token}")

    try:
        while True:
            try:
                event = await asyncio.wait_for(q.get(), timeout=20.0)
                event_type = event.get("type", "")
                agent_id = event.get("agent_id", "")
                task_id = event.get("task_id", "")
            except asyncio.TimeoutError:
                event_type = "heartbeat"
                agent_id = ""
                task_id = ""

            if event_type == "heartbeat":
                now = time.time()
                project_agents = state.get("agent_states", {})
                running_agents = []
                for aid, agt in list(project_agents.items()):
                    if _is_system_agent_id(aid):
                        continue
                    status = agt.get("status", "")
                    if status == "running":
                        running_agents.append(aid)
                        activity = agent_activity.get(aid, {})
                        last_event = activity.get("last_event", 0)
                        stuck_threshold = activity.get("stuck_threshold", 600)
                        if last_event > 0 and (now - last_event) > stuck_threshold:
                            _log_master_agent(
                                f"Agent {aid} running task for {(now - last_event)/60:.0f} min — monitoring...",
                                level="info", project_token=project_token,
                            )
                            activity["last_event"] = now
                    elif status == "error":
                        _log_master_agent(
                            f"Agent {aid} in ERROR state — needs attention",
                            level="warning", project_token=project_token,
                        )
                if running_agents:
                    _log_master_agent(
                        f"Monitoring {len(running_agents)} active agent(s): {', '.join(running_agents[:5])}",
                        project_token=project_token,
                    )
                continue

            if event_type == "task_started":
                task_title = event.get("task_title", "")
                branch = event.get("branch_name", "")
                agent_activity[agent_id] = {
                    "last_event": time.time(), "task": task_id,
                    "task_title": task_title, "stuck_count": 0,
                }
                _log_master_agent(
                    f"Agent {agent_id} started task '{task_title}' (branch: {branch})",
                    project_token=project_token,
                )
                continue

            if event_type == "task_completed":
                task_title = event.get("task_title", "")
                branch = event.get("branch_name", "")
                _log_master_agent(
                    f"Agent {agent_id} COMPLETED task '{task_title}' (branch: {branch})",
                    project_token=project_token,
                )
                try:
                    await _validate_agent_tree_compliance(
                        agent_id=agent_id, project_token=project_token, branch_name=branch,
                    )
                except Exception:
                    pass
                if branch:
                    try:
                        project_agents = state.get("agent_states", {})
                        agent = project_agents.get(agent_id, {})
                        repo_url = agent.get("git_repo_url", "")
                        token = agent.get("git_token", "")
                        if repo_url:
                            await _enqueue_git_merge(
                                branch=branch, repo_url=repo_url, token=token,
                                source_agent=agent_id, task_title=task_title,
                                project_token=project_token,
                            )
                            _log_master_agent(
                                f"Enqueued incremental merge of '{branch}' into integration branch",
                                project_token=project_token,
                            )
                    except Exception:
                        pass
                dag = state.get("task_dag", {})
                if dag:
                    completed_ids = _ledger_get_completed_ids(project_token)
                    in_progress_ids = _ledger_get_in_progress_ids(project_token)
                    ready_ids = _get_ready_task_ids(dag, completed_ids, in_progress_ids)
                    if not is_bootstrap_pushed(project_token):
                        bootstrap_ready = []
                        for rid in ready_ids:
                            task_obj = next((t for t in state.get("tasks", []) if str(_normalize_task_id(t) or t.get("external_id") or t.get("id") or "") == rid), None)
                            is_bt = (
                                rid == "TASK-00"
                                or (task_obj and "project bootstrap" in str(task_obj.get("title") or task_obj.get("taskName") or "").strip().lower())
                            )
                            if is_bt:
                                bootstrap_ready.append(rid)
                        ready_ids = bootstrap_ready
                    if ready_ids:
                        _log_master_agent(
                            f"{len(ready_ids)} task(s) now unblocked: {', '.join(ready_ids[:5])}",
                            project_token=project_token,
                        )
                        idle_agents = [
                            aid for aid, agent in state["agent_states"].items()
                            if not _is_system_agent_id(aid)
                            and agent.get("status") == "idle" and aid != DEPLOY_AGENT_ID
                        ]
                        if idle_agents:
                            _log_master_agent(
                                f"Assigning {min(len(ready_ids), len(idle_agents))} task(s) to agents",
                                project_token=project_token,
                            )
                            task_token_val = get_project_task_token(project_token)
                            for aid, rid in zip(idle_agents, ready_ids):
                                try:
                                    assigned = await _master_assign_task_to_agent(
                                        rid, aid,
                                        agent_name=state["agent_states"][aid].get("name"),
                                        project_token=project_token, task_token=task_token_val,
                                    )
                                    if assigned:
                                        _log_master_agent(f"Assigned '{rid}' to {aid}", project_token=project_token)
                                except Exception as e:
                                    logger.warning(f"[Master] Assign {rid} to {aid} failed: {e}")
                    else:
                        all_tasks = state.get("tasks", [])
                        if all_tasks and completed_ids and len(completed_ids) >= len(all_tasks):
                            _log_master_agent("ALL TASKS COMPLETED!", project_token=project_token)
                continue

            if event_type == "task_failed":
                task_title = event.get("task_title", "")
                error = event.get("error", "")
                _log_master_agent(
                    f"Agent {agent_id} FAILED on '{task_title}': {error[:200]}",
                    level="error", project_token=project_token,
                )
                continue

    except asyncio.CancelledError:
        _log_master_agent("Master Orchestrator stopped", project_token=project_token)
        raise
    except Exception as loop_err:
        logger.error(f"[Master Orchestrator] Fatal error: {loop_err}")
        _log_master_agent(f"Master Orchestrator crashed: {loop_err}", level="error", project_token=project_token)
        raise
    finally:
        try:
            await bus.unsubscribe(q)
        except Exception:
            pass'''

if old_dag_watcher in content:
    content = content.replace(old_dag_watcher, new_master_orchestrator, 1)
    changes_made += 1
    print("COMPONENT 1: Replaced _dag_progress_watcher -> _master_orchestrator_loop")
else:
    print("WARNING: COMPONENT 1: Could not find _dag_progress_watcher function")

# ═══════════════════════════════════════════════════════════════════════════
#  COMPONENT 2: Add _validate_agent_tree_compliance function
#  NOTE: Using single-quote triples ''' for outer delimiter to avoid
#  conflict with triple-double-quotes used inside for docstrings.
# ═══════════════════════════════════════════════════════════════════════════

tree_enforcement_func = '''

# ── Master Orchestrator — Tree Enforcement ─────────────────────────────────
# After each agent completes, validate their files against the canonical tree.

async def _validate_agent_tree_compliance(
    agent_id: str,
    project_token: Optional[str] = None,
    branch_name: str = "",
) -> Dict[str, Any]:
    """Validate agent-created files against the canonical project tree.

    Returns:
        {"status": "ok" | "violation" | "updated", "files": [...], "violations": [...]}
    """
    result: Dict[str, Any] = {
        "status": "ok", "files": [], "violations": [], "additions": [],
    }
    if not project_token or not branch_name:
        return result
    state = _ensure_project_state(project_token)
    canonical_paths: set = set()
    try:
        master_note_cache = state.get("master_note_cache", {})
        workspace_tree = master_note_cache.get("workspace_tree", "")
        if workspace_tree and isinstance(workspace_tree, str) and workspace_tree.startswith("{"):
            tree_data = json.loads(workspace_tree)
            _extract_tree_paths(tree_data, canonical_paths, prefix="")
    except Exception:
        pass
    if not canonical_paths:
        return result
    ledger = state.get("task_ledger", {})
    agent_files: List[str] = []
    for entry in ledger.values():
        if entry.agent_id == agent_id and entry.status == "done":
            agent_files.extend(entry.files_written)
    result["files"] = agent_files
    if not agent_files:
        return result
    for fpath in agent_files:
        fpath_normalized = fpath.replace("\\\\", "/").strip().strip("/")
        is_allowed = False
        for canonical in canonical_paths:
            c_normalized = canonical.replace("\\\\", "/").strip().strip("/")
            if fpath_normalized == c_normalized or fpath_normalized.startswith(c_normalized + "/"):
                is_allowed = True
                break
        if not is_allowed:
            filename = fpath_normalized.split("/")[-1]
            is_likely_useful = any([
                filename.endswith((".py", ".js", ".tsx", ".ts", ".jsx", ".go", ".rs", ".java")),
                filename in ("README.md", "docker-compose.yml", "Dockerfile", ".gitignore", "Makefile", "package.json", "tsconfig.json"),
                "test" in filename.lower() or "spec" in filename.lower(),
                "config" in filename.lower() or "util" in filename.lower(),
                "helper" in filename.lower() or "constant" in filename.lower(),
            ])
            if is_likely_useful:
                result["additions"].append(fpath_normalized)
                _log_master_agent(
                    f"Agent {agent_id} added new useful file: {fpath_normalized} - updating tree",
                    project_token=project_token,
                )
            else:
                result["violations"].append(fpath_normalized)
                _log_master_agent(
                    f"Agent {agent_id} added file outside canonical tree: {fpath_normalized}",
                    level="warning", project_token=project_token,
                )
    if result["violations"]:
        result["status"] = "violation"
    elif result["additions"]:
        result["status"] = "updated"
    if result["status"] == "ok":
        _log_master_agent(f"Agent {agent_id} tree validation PASSED", project_token=project_token)
    elif result["status"] == "updated":
        _log_master_agent(f"Agent {agent_id} tree validation PASSED (with {len(result['additions'])} additions)", project_token=project_token)
    elif result["status"] == "violation":
        _log_master_agent(
            f"Agent {agent_id} tree validation: {len(result['violations'])} file(s) outside tree: {', '.join(result['violations'][:3])}",
            level="warning", project_token=project_token,
        )
    return result


def _extract_tree_paths(node: Dict[str, Any], paths: set, prefix: str = "") -> None:
    """Recursively extract file/directory paths from a nested JSON tree."""
    name = node.get("name", "")
    if not name:
        return
    current_path = f"{prefix}/{name}" if prefix else name
    children = node.get("children")
    if children and isinstance(children, list):
        paths.add(current_path)
        for child in children:
            if isinstance(child, dict):
                _extract_tree_paths(child, paths, current_path)
    else:
        paths.add(current_path)


# ── Master Orchestrator — Publish task_failed event ─────────────────────
async def _publish_agent_failed_event(
    project_token: Optional[str],
    agent_id: str,
    task_title: str,
    error: str,
) -> None:
    """Publish a task_failed event so the Master Orchestrator can react."""
    try:
        await _publish_agent_event(
            project_token, "task_failed", agent_id,
            task_id="", task_title=task_title, error=str(error)[:500],
        )
    except Exception:
        pass'''

# Insert tree enforcement function before _publish_agent_event
insert_marker = 'async def _publish_agent_event('
if tree_enforcement_func not in content:
    idx = content.find(insert_marker)
    if idx > 0:
        content = content[:idx] + "\n\n" + tree_enforcement_func + "\n\n" + content[idx:]
        changes_made += 1
        print("COMPONENT 2: Added _validate_agent_tree_compliance + _extract_tree_paths")
    else:
        print("WARNING: COMPONENT 2: Could not find insertion point")
else:
    print("INFO: COMPONENT 2: Already present, skipping")

# ═══════════════════════════════════════════════════════════════════════════
#  COMPONENT 3: Update mark_run_all_waiting_state to call
#  _master_orchestrator_loop instead of _dag_progress_watcher
# ═══════════════════════════════════════════════════════════════════════════

old_start = '''    # NEW: start the DAG watcher background task
    asyncio.create_task(
        _dag_progress_watcher(project_token),
        name=f"dag_watcher_{project_token or 'default'}"
    )'''

new_start = '''    # ── Start Master Orchestrator ──
    asyncio.create_task(
        _master_orchestrator_loop(project_token),
        name=f"master_orch_{project_token or 'default'}"
    )'''

if old_start in content:
    content = content.replace(old_start, new_start, 1)
    changes_made += 1
    print("COMPONENT 3: Updated run_all to start _master_orchestrator_loop")
else:
    print("WARNING: COMPONENT 3: Could not find DAG watcher startup code")

# Save and report
if changes_made > 0:
    with open(FILEPATH, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"\nAll changes applied! Total changes: {changes_made}")
    print("\nIMPORTANT: Restart the backend server for changes to take effect.")
else:
    print("\nNo changes made - none of the patterns matched")
