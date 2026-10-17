"""Supervisor Agent — Master Architect / Init Process (PID 1).

Architecture:
    The Supervisor is the top-level orchestrator that:
    1. Loads all tasks from task_config.json
    2. Builds a DAG of task dependencies
    3. Assigns tasks to specialized sub-agents (Backend, Frontend, QA)
    4. Runs independent tasks in parallel via ThreadPoolExecutor
    5. Auto-commits and pushes to Git after each task completes
    6. Monitors progress and coordinates IPC between agents
    7. Posts lifecycle events to the control plane via callback

    This replaces the monolithic single-agent approach with a true
    multi-agent swarm where each agent works within its lane.
"""
from __future__ import annotations

import asyncio
import copy
import json
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable

from mcp.server import MCPServer
from mcp.git_tools import GitTools
from agent.model_router import ModelRouter
from agent.dag_scheduler import DAGScheduler, Task, TaskStatus
from agent.sub_agents import BackendSubAgent, FrontendSubAgent, QASubAgent, SubAgent
from agent.ipc import IPCRouter

# Platform verification engine (Gate A/B/C) — optional import so legacy
# deployments without the engine keep working.
try:
    from runtime.verification_engine import VerificationEngine
    _VERIFICATION_AVAILABLE = True
except Exception:  # pragma: no cover
    _VERIFICATION_AVAILABLE = False

logger = logging.getLogger(__name__)


class SupervisorAgent:
    """Master Architect for orchestrating the agent swarm.

    Follows the architecture diagram:
        SUPERVISOR AGENT / INIT PROCESS (Master Architect, PID 1)
        ├── Dynamic DAG Scheduler
        ├── Context Pager
        ├── Task Forking
        └── IPC Router
    """

    def __init__(
        self,
        workspace_path: str,
        mcp: MCPServer,
        router: ModelRouter,
        callback: Callable[[str, dict[str, Any]], None] | None = None,
        task_config: dict[str, Any] | None = None,
    ):
        self.workspace_path = workspace_path
        self.mcp = mcp
        self.router = router
        self.callback = callback
        self.task_config = task_config or {}

        # DAG Scheduler — loads tasks with per-agent isolation support
        agent_config_file = os.environ.get("AGENT_CONFIG_FILE")
        agent_id = os.environ.get("AGENT_ID")
        config_path = None
        if agent_config_file:
            cand = os.path.join(workspace_path, ".agent", agent_config_file)
            if os.path.exists(cand):
                config_path = cand
        if not config_path and agent_id:
            clean_aid = "".join(c for c in agent_id if c.isalnum() or c == "_")
            cand = os.path.join(workspace_path, ".agent", f"task_config_{clean_aid}.json")
            if os.path.exists(cand):
                config_path = cand
        if not config_path:
            cand = os.path.join(workspace_path, ".agent", "task_config.json")
            if os.path.exists(cand):
                config_path = cand
            else:
                config_path = os.path.join(workspace_path, "task_config.json")

        tasks_list = self.task_config.get("tasks") if isinstance(self.task_config, dict) else None
        self.scheduler = DAGScheduler(config_path, tasks_data=tasks_list)

        # IPC Router — file-based inter-agent communication
        self.ipc = IPCRouter(workspace_path)

        # Git Tools — available for final delivery
        self.git_tools = GitTools(workspace_path)
        import threading
        self._git_lock = threading.RLock()

        # Sub-Agent Pool — one per lane
        self.agents: dict[str, SubAgent] = {
            "backend": BackendSubAgent(),
            "frontend": FrontendSubAgent(),
            "qa": QASubAgent(),
        }

        # Stats
        self.tasks_completed = 0
        self.tasks_failed = 0
        self.total_files_changed: list[str] = []
        self.task_results: dict[str, dict[str, Any]] = {}

        # Platform-verification repair loop state. How many repair rounds the
        # swarm may run is configuration, not a hard-coded assumption.
        try:
            self.max_platform_repair_rounds = max(0, int(os.environ.get("VERIFICATION_MAX_REPAIR_ROUNDS", "3")))
        except (TypeError, ValueError):
            self.max_platform_repair_rounds = 3
        self._platform_repair_rounds_done = 0
        self.verification_history: list[dict[str, Any]] = []
        self._last_verification_signature: str | None = None
        self.repair_tasks_created = 0

    def _post_event(self, event_type: str, data: dict[str, Any]) -> None:
        """Post a lifecycle event to the control plane."""
        if self.callback:
            try:
                self.callback(event_type, data)
            except Exception as e:
                logger.error(f"[Supervisor] Callback error for '{event_type}': {e}")
        # Also log for visibility
    def _sync_checklist_progress(self, task_id: str, checklist_progress: dict[str, int]) -> None:
        """Sync final checklist progress to the Task Management API (best-effort).

        Uses the same endpoint and auth as the initial checklist sync in
        _execute_single_task, so the user sees completed/total per task.
        """
        import httpx

        task_api_url = os.environ.get("TASK_API_BASE_URL", "http://localhost:8000")
        task_token = os.environ.get("CALLBACK_SECRET") or os.environ.get("TASK_TOKEN")
        if not task_token:
            return

        async def _sync():
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.put(
                    f"{task_api_url}/api/agent/tasks/{task_id}/checklist-progress/",
                    json={"progress": checklist_progress},
                    headers={"Authorization": f"Bearer {task_token}"},
                )
                return response.status_code

        status = asyncio.run(_sync())
        if status == 200:
            print(f"[Supervisor] 💾 Synced checklist progress {checklist_progress} for {task_id}")
        else:
            logger.warning(f"[Supervisor] Checklist progress sync returned HTTP {status} (non-blocking)")

    def _drain_followup_queue(self) -> int:
        """Drain agent-discovered follow-up tasks into the DAG scheduler.

        Agents append validated tasks to .agent/pending_followup_tasks.json
        (via submit_followup_tasks). Each becomes a DAG task that depends on
        its origin task so it runs when that prerequisite work is real — not
        before. Discovered work is scheduled, not lost or silently absorbed.
        """
        queue_file = os.path.join(self.workspace_path, ".agent", "pending_followup_tasks.json")
        if not os.path.exists(queue_file):
            return 0
        try:
            with open(queue_file, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except (OSError, ValueError) as e:
            logger.warning(f"[Supervisor] Failed to read follow-up queue: {e}")
            return 0
        items = raw if isinstance(raw, list) else (raw.get("tasks", []) if isinstance(raw, dict) else [])
        if not isinstance(items, list) or not items:
            return 0

        added = 0
        seen_titles: set[str] = set()
        for item in items:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title", "")).strip()
            desc = str(item.get("description", "")).strip()
            lane = str(item.get("lane", "backend")).strip().lower() or "backend"
            if not title or not desc:
                continue
            origin = str(item.get("origin", "agent")).strip() or "agent"
            deps = [str(d) for d in (item.get("depends_on") or []) if str(d).strip()]

            # DAG-level dedup: skip if the title already exists in the DAG (from
            # config or a previous drain), or was already created from this batch
            # (two agents discovering the same work in one drain → one task).
            title_key = title.lower()
            exists_in_dag = any(
                str(t.title).strip().lower() == title_key
                for t in self.scheduler.tasks.values()
            )
            if exists_in_dag or title_key in seen_titles:
                logger.info(f"[Supervisor] Skipping duplicate follow-up task '{title}' (already exists in DAG or duplicated in queue)")
                seen_titles.add(title_key)
                continue

            # Parent dependency is STRICT: the follow-up truly runs after the
            # origin task completes, regardless of lane (see Task.strict_deps).
            strict_deps: list[str] = []
            if not deps:
                parent_task_id = str(item.get("parent_task_id", "")).strip()
                if parent_task_id:
                    strict_deps = [parent_task_id]
                else:
                    # No known parent: schedule conservatively as a root task
                    # (backend/frontend roots exist from config anyway).
                    pass
            task_id = f"{origin}_{len(self.scheduler.tasks) + 1}_{int(time.time())}"
            new_task_data = {
                "task_id": task_id,
                "title": title,
                "description": (
                    f"[Dynamic follow-up discovered by {origin}]\n{desc}"
                ),
                "lane": lane,
                "depends_on": deps,
                "status": "pending",
                "subtasks": [],
            }
            if strict_deps:
                new_task_data["strict_deps"] = strict_deps
            self.scheduler.tasks[task_id] = Task(new_task_data)
            self.scheduler.save_tasks()
            added += 1
            self._post_event("followup_task_created", {
                "task_id": task_id,
                "title": title,
                "lane": lane,
                "depends_on": deps,
                "origin": origin,
            })
            logger.info(f"[Supervisor] 📌 Queued dynamic follow-up task {task_id}: {title} ({lane}) deps={deps}")

        # Allow sibling agents (other containers) to see the new tasks too.
        try:
            self.ipc.broadcast("Supervisor", "followup_tasks_added", {"count": added})
        except Exception:
            pass
        try:
            os.remove(queue_file)
        except OSError:
            pass
        return added

    def _ensure_early_preview_running(self) -> None:
        """Auto-boot live application preview early in a background daemon thread
        as soon as baseline frontend or backend structure is in place, so user can see
        the running UI while remaining swarm tasks continue in the background."""
        if getattr(self, "_early_preview_started", False):
            return
        ws = self.workspace_path
        has_fe = os.path.exists(os.path.join(ws, "frontend", "package.json")) or os.path.exists(os.path.join(ws, "package.json"))
        has_be = os.path.exists(os.path.join(ws, "backend", "app", "main.py")) or os.path.exists(os.path.join(ws, "main.py"))
        if has_fe or has_be:
            self._early_preview_started = True
            import threading
            def _boot():
                try:
                    from runtime.preview_manager import PreviewManager
                    pm = PreviewManager(workspace_path=self.workspace_path)
                    info = pm.start_preview(project_type="auto")
                    print(f"[Supervisor] 🚀 Early live preview online at: {info.url}")
                    self._post_event("preview_ready", {
                        "status": "success",
                        "preview_url": info.url,
                        "port": info.port,
                        "message": "In-flight live preview auto-booted while swarm executes in background",
                    })
                except Exception as pe:
                    logger.debug(f"[Supervisor] Early preview note: {pe}")
            t = threading.Thread(target=_boot, daemon=True)
            t.start()

    def _execute_single_task(self, task) -> bool:
        """Execute a single task by delegating to the appropriate sub-agent.

        Returns True if the task completed successfully.
        """
        canonical_lane = (getattr(task, "lane", "") or "backend").lower().strip()
        if canonical_lane in ("frontend", "ui", "web", "react", "view"):
            agent = self.agents["frontend"]
        elif canonical_lane in ("qa", "test", "testing", "verification", "audit"):
            agent = self.agents["qa"]
        elif canonical_lane == "general":
            title_desc = f"{getattr(task, 'title', '')} {getattr(task, 'description', '')}".lower()
            if any(w in title_desc for w in ("ui", "screen", "component", "frontend", "form", "page", "modal", "view")):
                agent = self.agents["frontend"]
            else:
                agent = self.agents["backend"]
        else:
            agent = self.agents.get(canonical_lane, self.agents["backend"])

        from agent.nodes.discovery.discover_workspace import build_feature_branch_name
        task_id = task.task_id
        feature_branch = build_feature_branch_name(task_id, getattr(task, "title", ""))
        base_branch = os.environ.get("GIT_BRANCH", "main")

        # Feature Branch Isolation for Brownfield / Swarm tasks
        with self._git_lock:
            try:
                self.git_tools.checkout_branch(feature_branch, create=True, base_branch=base_branch)
                print(f"[Supervisor] 🌿 Task {task_id} isolated on feature branch: {feature_branch} (base: {base_branch})")
                self._post_event("branch_checked_out", {
                    "task_id": task_id,
                    "agent": agent.name,
                    "feature_branch": feature_branch,
                    "base_branch": base_branch,
                })
            except Exception as branch_err:
                logger.debug(f"[Supervisor] Feature branch checkout note: {branch_err}")

        print(f"\n{'='*60}")
        print(f"[Supervisor] 🚀 Dispatching task to {agent.name}: {task.title}")
        print(f"[Supervisor]    Task ID: {task_id} | Lane: {task.lane} | Branch: {feature_branch}")
        
        # ═══════════════════════════════════════════════════════════════════════
        # DYNAMIC CHECKLIST GENERATION (Agent creates their own checklist)
        # ═══════════════════════════════════════════════════════════════════════
        try:
            from agent.checklist_generator import generate_task_checklist

            # NOTE: do NOT 'import os' / 'import asyncio' inside this try block.
            # A local import shadows the module-level binding, so if the try
            # raises before the import executes, every later os.*/asyncio.* use
            # below raises UnboundLocalError. Both are imported at module top.

            print(f"[Supervisor] 📋 Generating dynamic checklist for {agent.name}...")
            
            # Generate checklist asynchronously
            checklist = asyncio.run(generate_task_checklist(
                task=task,
                lane=canonical_lane,
                workspace_path=self.workspace_path,
                model_router=self.router,
            ))
            
            if checklist:
                print(f"[Supervisor] ✅ Generated {len(checklist)} checklist items:")
                for idx, item in enumerate(checklist[:5], 1):  # Show first 5
                    print(f"[Supervisor]    {idx}. {item['text'][:80]}")
                if len(checklist) > 5:
                    print(f"[Supervisor]    ... and {len(checklist) - 5} more items")
                
                # Store checklist in task object for agent to use
                setattr(task, "checklist", checklist)
                
                # Try to sync to external Task Management API via HTTP
                # (We can't import backend.app.services here in Docker, so use HTTP)
                try:
                    import httpx

                    # 'os' comes from the module-level import — a local
                    # 'import os' here would shadow it and blow up later
                    # (UnboundLocalError) if httpx ever failed to import.

                    # Get Task Management API URL from environment
                    task_api_url = os.environ.get("TASK_API_BASE_URL", "http://localhost:8000")
                    task_token = os.environ.get("CALLBACK_SECRET") or os.environ.get("TASK_TOKEN")
                    
                    if task_token:
                        # Call Task Management API directly via HTTP
                        async def sync_checklist():
                            async with httpx.AsyncClient(timeout=10.0) as client:
                                response = await client.put(
                                    f"{task_api_url}/api/agent/tasks/{task_id}/checklist/",
                                    json={"checklistItems": checklist},
                                    headers={"Authorization": f"Bearer {task_token}"}
                                )
                                return response.status_code == 200
                        
                        success = asyncio.run(sync_checklist())
                        if success:
                            print(f"[Supervisor] 💾 Synced checklist to Task Management API")
                        else:
                            logger.warning(f"[Supervisor] Could not sync checklist to API (non-blocking)")
                except Exception as sync_err:
                    logger.warning(f"[Supervisor] Could not sync checklist to API: {sync_err}")
        except Exception as checklist_err:
            logger.warning(f"[Supervisor] Checklist generation failed, agent will work without checklist: {checklist_err}")
        
        print(f"{'='*60}\n")

        # Update status to RUNNING (and stamp the current task id so the agent's
        # submit_followup_tasks calls can default their dependency to this task)
        os.environ["PARENT_TASK_ID"] = task_id
        self.scheduler.update_task_status(task_id, TaskStatus.RUNNING)
        self._post_event("task_started", {
            "task_id": task_id,
            "agent": agent.name,
            "lane": task.lane,
            "title": task.title,
        })

        # Broadcast to other agents via IPC
        self.ipc.broadcast("Supervisor", "task_status", {
            "task_id": task_id, "status": "running", "agent": agent.name
        })

        # ═══════════════════════════════════════════════════
        # DYNAMIC UPSTREAM DEPENDENCY AWARENESS
        # ═══════════════════════════════════════════════════
        upstream_failures = []
        for dep in getattr(task, "depends_on", []):
            dep_task = self.scheduler._find_task_by_id(dep)
            if dep_task and dep_task.status == TaskStatus.FAILED:
                upstream_failures.append(f"- Upstream dependency '{dep_task.title}' ({dep}) ended with status FAILED.")
        if upstream_failures:
            context_note = (
                "\n\n[UPSTREAM DEPENDENCY NOTICE]\n"
                "The following upstream task(s) encountered issues or failed:\n"
                + "\n".join(upstream_failures) + "\n"
                "INSTRUCTION: DO NOT abort. Inspect existing workspace files, adapt or create any missing "
                "interfaces, models, or components required by your task, and proceed to complete your scope.\n"
            )
            task.description = (getattr(task, "description", "") or "") + context_note

        # ═══════════════════════════════════════════════════
        # DELEGATE: Sub-agent runs its ReAct tool loop
        # ═══════════════════════════════════════════════════
        start_time = time.time()
        result = agent.execute_task(task, self.workspace_path, self.mcp, self.router, context=self.task_config)

        # ── Gate A+: Platform-owned per-task verification with Autonomous Self-Healing ──
        # If verification detects broken imports, syntax, or contract mismatches,
        # do NOT immediately declare failure and abort the swarm. Give the agent an
        # immediate, focused repair turn with the exact compiler/verification error.
        max_gate_repairs = 2
        gate_repair_attempt = 0

        while gate_repair_attempt < max_gate_repairs:
            if not result.success:
                # If execution itself failed with an error, attempt focused repair
                gate_repair_attempt += 1
                logger.warning(
                    f"[Supervisor] 🩹 Task {task_id} encountered execution error: {result.error}. "
                    f"Triggering autonomous repair turn ({gate_repair_attempt}/{max_gate_repairs})..."
                )
                repair_task = copy.deepcopy(task)
                repair_task.description = (
                    f"AUTONOMOUS SELF-HEALING REPAIR TURN ({gate_repair_attempt}/{max_gate_repairs}):\n"
                    f"The previous execution of task '{task.title}' failed with this error:\n"
                    f"--------------------------------------------------\n"
                    f"{result.error}\n"
                    f"--------------------------------------------------\n"
                    f"INSTRUCTIONS: Locate the referenced files, resolve the missing imports, syntax, or "
                    f"unexported symbols using real tool calls, and ensure the code compiles cleanly."
                )
                result = agent.execute_task(repair_task, self.workspace_path, self.mcp, self.router, context=self.task_config)
                continue

            # Check verification engine if execution was reported successful
            if _VERIFICATION_AVAILABLE:
                try:
                    print(f"\n[Supervisor] 🧪 Testing & verifying task {task_id} changes ({len(result.files_changed)} files)...")
                    gate = VerificationEngine(self.workspace_path).verify_task_changes(result.files_changed)
                    result.verification = gate.to_dict()
                    if not gate.passed:
                        gate_repair_attempt += 1
                        logger.warning(
                            f"[Supervisor] 🩹 Gate verification failed for {task_id}:\n{gate.detail}\n"
                            f"Triggering autonomous repair turn ({gate_repair_attempt}/{max_gate_repairs})..."
                        )
                        repair_task = copy.deepcopy(task)
                        repair_task.description = (
                            f"AUTONOMOUS VERIFICATION REPAIR TURN ({gate_repair_attempt}/{max_gate_repairs}):\n"
                            f"Platform verification detected the following issues in files modified for '{task.title}':\n"
                            f"--------------------------------------------------\n"
                            f"{gate.detail}\n"
                            f"--------------------------------------------------\n"
                            f"INSTRUCTIONS: Fix the root cause immediately using write_file or replace_file_content. "
                            f"Ensure all imported files exist and all exports are present."
                        )
                        result = agent.execute_task(repair_task, self.workspace_path, self.mcp, self.router, context=self.task_config)
                        continue
                    else:
                        print(f"[Supervisor] ✅ Task {task_id} verification PASSED.")
                        break
                except Exception as gate_err:
                    result.verification = {"skipped": True, "reason": str(gate_err)[:300]}
                    break
            else:
                result.verification = {"skipped": True, "reason": "verification engine unavailable"}
                break

        elapsed = time.time() - start_time

        if result.success:
            self.tasks_completed += 1
            self.total_files_changed.extend(result.files_changed)
            self.scheduler.update_task_status(task_id, TaskStatus.COMPLETED)

            # Checklist progress: pull the agent's final tracker state, sync it
            # to the Task API (best-effort), and record it in the task result.
            checklist_progress = getattr(result, "checklist_progress", None)
            if checklist_progress:
                checklist_progress = dict(checklist_progress)
                try:
                    self._sync_checklist_progress(task_id, checklist_progress)
                except Exception as sync_err:
                    logger.warning(f"[Supervisor] Checklist progress sync failed (non-blocking): {sync_err}")

            self.task_results[task_id] = {
                "status": "completed",
                "agent": agent.name,
                "lane": task.lane,
                "elapsed_seconds": round(elapsed, 1),
                "files_changed": result.files_changed,
                # Gate C honesty: agent-reported vs platform-verified
                "agent_reported_status": "completed",
                "platform_verified": bool((getattr(result, "verification", None) or {}).get("passed")),
                "verification": getattr(result, "verification", None),
                "checklist_progress": checklist_progress,
            }

            print(f"\n[Supervisor] ✅ Task {task_id} completed by {agent.name} "
                  f"in {elapsed:.1f}s ({len(result.files_changed)} files changed)")

            # Auto-commit feature checkpoint & push feature branch
            commit_hash = "unknown"
            push_success = False
            push_message = ""
            with self._git_lock:
                try:
                    commit_res = self.git_tools.commit_checkpoint(
                        task_id=task_id,
                        summary=task.title,
                        files_changed=result.files_changed,
                    )
                    if commit_res.success:
                        commit_hash = commit_res.data.get("commit_hash", "unknown")
                        print(f"[Supervisor] 💾 Committed feature checkpoint {commit_hash[:8]} on branch {feature_branch}")
                    else:
                        print(f"[Supervisor] ⚠️ Checkpoint commit failed: {commit_res.error}")

                    # Push feature branch if remote repository is configured
                    repo_url = os.environ.get("GIT_REPO_URL")
                    auth_token = os.environ.get("GIT_AUTH_TOKEN") or os.environ.get("GIT_PAT_TOKEN")
                    if repo_url:
                        print(f"[Supervisor] 🚀 Pushing feature branch '{feature_branch}' to remote: {repo_url}...")
                        push_res = self.git_tools.push(branch=feature_branch, auth_token=auth_token, repo_url=repo_url)
                        if push_res.success:
                            push_success = True
                            push_message = f"Pushed {feature_branch} to {repo_url}"
                            print(f"[Supervisor] ✅ Successfully pushed feature branch '{feature_branch}' to remote: {repo_url}")
                            self._post_event("git_push_completed", {
                                "task_id": task_id,
                                "feature_branch": feature_branch,
                                "commit_hash": commit_hash,
                                "repo_url": repo_url,
                                "status": "success",
                            })
                        else:
                            push_message = f"Push failed: {push_res.error}"
                            print(f"[Supervisor] ❌ Feature branch push failed: {push_res.error}")
                            self._post_event("git_push_failed", {
                                "task_id": task_id,
                                "feature_branch": feature_branch,
                                "commit_hash": commit_hash,
                                "error": str(push_res.error),
                            })
                    else:
                        push_message = "GIT_REPO_URL not configured - remote push skipped"
                        print(f"[Supervisor] ℹ️ Remote push skipped: GIT_REPO_URL is not configured.")

                    # Merge feature branch into base_branch with automatic conflict abort, and push base_branch
                    try:
                        merge_res = self.git_tools.merge_branch(feature_branch=feature_branch, base_branch=base_branch, no_ff=True)
                        if merge_res.success:
                            print(f"[Supervisor] 🔀 Merged '{feature_branch}' into '{base_branch}'")
                            if repo_url:
                                self.git_tools.push(branch=base_branch, auth_token=auth_token, repo_url=repo_url)
                        else:
                            print(f"[Supervisor] ⚠️ Merge conflict/error (auto-aborted cleanly): {merge_res.error}")
                    except Exception as merge_err:
                        logger.debug(f"[Supervisor] Base branch merge note: {merge_err}")
                except Exception as git_err:
                    logger.warning(f"[Supervisor] Feature git workflow note: {git_err}")

            self._post_event("task_completed", {
                "task_id": task_id,
                "agent": agent.name,
                "elapsed_seconds": round(elapsed, 1),
                "files_changed": len(result.files_changed),
                "commit_hash": commit_hash,
                "feature_branch": feature_branch,
                "push_success": push_success,
                "push_message": push_message,
            })

            # Notify dependent tasks via IPC
            self.ipc.broadcast("Supervisor", "dependency_ready", {
                "task_id": task_id,
                "status": "completed",
            })

            # Auto-boot early live preview in background so UI is live while swarm continues
            self._ensure_early_preview_running()

            return True

        else:
            self.tasks_failed += 1
            self.scheduler.update_task_status(task_id, TaskStatus.FAILED)
            self.task_results[task_id] = {
                "status": "failed",
                "agent": agent.name,
                "lane": task.lane,
                "elapsed_seconds": round(elapsed, 1),
                "error": result.error or "Unknown error",
                # Gate C honesty: distinguish agent-reported failure from gate failure
                "agent_reported_status": "completed" if result.files_changed else "failed",
                "verification": getattr(result, "verification", None),
            }

            print(f"\n[Supervisor] ❌ Task {task_id} FAILED by {agent.name} "
                  f"after {elapsed:.1f}s: {result.error}")

            self._post_event("task_failed", {
                "task_id": task_id,
                "agent": agent.name,
                "elapsed_seconds": round(elapsed, 1),
                "error": result.error or "Unknown error",
            })

            self.ipc.broadcast("Supervisor", "task_status", {
                "task_id": task_id, "status": "failed", "error": result.error
            })

            return False

    # ═══════════════════════════════════════════════════════════════════════
    # PLATFORM VERIFICATION → AGENT REPAIR FEEDBACK
    # ═══════════════════════════════════════════════════════════════════════

    def _platform_verify(self) -> dict[str, Any] | None:
        """Run the platform's runnability gates over the whole workspace.

        Stage selection is dynamic (the engine derives the applicable stages from
        what is actually on disk), so no stage names are hard-coded here.
        """
        if not _VERIFICATION_AVAILABLE:
            return {"skipped": True, "reason": "verification engine unavailable"}
        try:
            report = VerificationEngine(self.workspace_path).run_full_verification()
            return report.to_dict()
        except Exception as verify_err:
            logger.warning(f"[Supervisor] Platform verification error: {verify_err}")
            return {"skipped": True, "reason": str(verify_err)[:300]}

    def _workspace_roots(self) -> dict[str, list[str]]:
        """Workspace layout, discovered by the platform (single source of truth)."""
        try:
            from runtime.verification_engine import VerificationEngine as _VE
            return _VE(self.workspace_path)._find_roots()
        except Exception:
            return {"python": [], "node": []}

    def _lane_for_failure(self, stage: dict[str, Any]) -> str:
        """Decide which lane owns a verification failure — from the failure itself.

        Ownership is inferred from the workspace layout (discovered roots) and the
        paths named in the failure text, falling back to gate semantics. No project
        layout or directory name is assumed.
        """
        detail = str(stage.get("detail") or "").replace("\\", "/").lower()
        gate = str(stage.get("name") or "").lower()
        roots = self._workspace_roots()

        # Connectivity failures are caused by whichever side is actually down —
        # the frontend config merely points at the API, so name the real cause.
        if gate == "connectivity":
            first_line = detail.splitlines()[0] if detail else ""
            if "backend unreachable" in detail or "backend" in first_line:
                return "backend"
            return "frontend"

        def _rel(root: str) -> str:
            try:
                rel = os.path.relpath(root, self.workspace_path).replace("\\", "/").lower()
            except ValueError:
                return ""
            return "" if rel in (".", "") else rel

        node_rels = [r for r in (_rel(nr) for nr in roots.get("node", [])) if r]
        py_rels = [r for r in (_rel(pr) for pr in roots.get("python", [])) if r]

        if any(r in detail for r in node_rels):
            return "frontend"
        if any(r in detail for r in py_rels):
            return "backend"

        if re.search(r"\.(tsx|jsx|vue|svelte|css|scss|sass|html)\b", detail):
            return "frontend"
        if re.search(r"\.py\b", detail):
            return "backend"

        if gate in ("build", "serve"):
            return "frontend"
        if gate in ("imports", "boot", "contract"):
            return "backend"
        return "qa"

    def _enqueue_verification_repairs(self, report: dict[str, Any]) -> int:
        """Turn platform verification failures into repair tasks for the lane agents.

        Each failing gate is grouped under the lane that owns the affected files;
        the lane agent picks the task up on the next scheduling round, fixes the
        root cause, and the platform re-verifies. Returns the number of tasks added.
        """
        stages = report.get("stages") or []
        failures = [
            st for st in stages
            if isinstance(st, dict) and not st.get("passed") and not st.get("skipped")
        ]
        if not failures:
            return 0

        try:
            from runtime.verification_engine import classify_failure as _classify
        except Exception:
            _classify = lambda raw: "unknown"  # noqa: E731

        grouped: dict[str, list[dict[str, Any]]] = {}
        for st in failures:
            grouped.setdefault(self._lane_for_failure(st), []).append(st)

        created = 0
        for lane, items in grouped.items():
            if lane not in self.agents:
                lane = "backend" if lane == "backend" else "qa"
            gate_names = ", ".join(str(i.get("name")) for i in items)
            title = f"[Platform Repair] {gate_names} gate failing"
            lines = [
                "PLATFORM VERIFICATION FAILURE — the assembled project did not pass the",
                "platform's runnability gates. Fix the ROOT CAUSE in the referenced files",
                "so the same gates pass on the next verification round.",
                "Address every item below, then exercise the affected build/run command",
                "yourself to confirm it succeeds. Do not weaken, delete or bypass checks,",
                "and do not hard-code values to silence a failure.",
                "",
            ]
            for it in items:
                detail = str(it.get("detail") or "")
                lines.append(f"### Gate: {it.get('name')} (failure class: {_classify(detail)})")
                lines.append(detail[:4000])
                lines.append("")
            task_id = f"verification_repair_{lane}_{int(time.time())}_{created + 1}"
            self.scheduler.tasks[task_id] = Task({
                "task_id": task_id,
                "title": title,
                "description": "\n".join(lines),
                "lane": lane,
                "depends_on": [],
                "status": "pending",
                "subtasks": [],
            })
            self.scheduler.save_tasks()
            created += 1

            self._post_event("verification_repair_dispatched", {
                "task_id": task_id,
                "lane": lane,
                "gates": [str(i.get("name")) for i in items],
                "failure_classes": [_classify(str(i.get("detail") or "")) for i in items],
            })
            try:
                self.ipc.broadcast("Supervisor", "verification_issue_routed", {
                    "task_id": task_id,
                    "lane": lane,
                    "error": str(items[0].get("detail") or "")[:500],
                })
            except Exception:
                pass
            logger.info(
                f"[Supervisor] 🛠️  Verification repair routed to '{lane}' lane "
                f"({task_id}): {title}"
            )
        return created

    def run(self) -> dict[str, Any]:
        """Execute all tasks in dependency order with parallel execution.

        Returns a summary dict with completion stats.
        """
        total_tasks = len(self.scheduler.tasks)
        print(f"\n{'#'*60}")
        print(f"[Supervisor] 🏗️  Starting Agent Swarm Execution")
        print(f"[Supervisor]    Total tasks: {total_tasks}")
        print(f"[Supervisor]    Available agents: {', '.join(a.name for a in self.agents.values())}")

        # Show execution order
        batches = self.scheduler.get_execution_order()
        for i, batch in enumerate(batches):
            tasks_str = ", ".join(f"{t.title} ({t.lane})" for t in batch)
            print(f"[Supervisor]    Batch {i+1}: [{tasks_str}]")
        print(f"{'#'*60}\n")

        self._post_event("supervisor_started", {
            "total_tasks": total_tasks,
            "agents": list(self.agents.keys()),
            "execution_batches": len(batches),
        })

        # Ensure git is initialized
        try:
            self.git_tools.init()
        except Exception as e:
            logger.warning(f"[Supervisor] Git init: {e}")

        # Ensure early in-flight live preview is active if foundation exists
        self._ensure_early_preview_running()

        # ═══════════════════════════════════════════════════════
        # MAIN EXECUTION LOOP — process DAG in topological order
        # ═══════════════════════════════════════════════════════
        max_idle_rounds = 10
        idle_rounds = 0

        while True:
            # Drain agent-discovered follow-up tasks into the DAG before
            # scheduling, so newly discovered work joins the run rather than
            # being silently absorbed or lost.
            try:
                self._drain_followup_queue()
            except Exception as drain_err:
                logger.warning(f"[Supervisor] Follow-up drain error: {drain_err}")

            ready_tasks = self.scheduler.get_ready_tasks()

            if not ready_tasks:
                # Check if all done
                all_done = all(
                    t.status in (TaskStatus.COMPLETED, TaskStatus.FAILED)
                    for t in self.scheduler.tasks.values()
                )
                if all_done:
                    print(f"\n[Supervisor] 🏁 All tasks processed!")

                    # ── Platform runnability decides whether the run is really done ──
                    # Task counts alone never mean "done": the platform proves the
                    # assembled app is installable, buildable, bootable and
                    # connected. When it is not, the failures are converted into
                    # repair tasks and routed to the lane agents that own the
                    # affected files — the swarm then fixes them and we re-verify.
                    if not _VERIFICATION_AVAILABLE:
                        break

                    report = self._platform_verify()
                    if report is not None:
                        self.verification_history.append(report)

                    if report is None or report.get("skipped") or report.get("passed"):
                        break

                    signature = str(report.get("error_signature") or "")
                    if signature and signature == self._last_verification_signature:
                        # Failures not shrinking: another round would repeat the same
                        # broken attempt, so stop and report convergence honestly.
                        report.setdefault("convergence", True)
                        logger.warning(
                            "[Supervisor] Verification failures are not shrinking — "
                            "stopping the repair loop (convergence)."
                        )
                        break
                    self._last_verification_signature = signature

                    if self._platform_repair_rounds_done >= self.max_platform_repair_rounds:
                        logger.warning(
                            f"[Supervisor] Platform repair rounds exhausted "
                            f"({self._platform_repair_rounds_done}/{self.max_platform_repair_rounds}) — "
                            "reporting the project as not runnable."
                        )
                        break

                    created = self._enqueue_verification_repairs(report)
                    if not created:
                        break

                    self._platform_repair_rounds_done += 1
                    self.repair_tasks_created += created
                    print(
                        f"\n[Supervisor] 🔁 Platform verification round "
                        f"{self._platform_repair_rounds_done}/{self.max_platform_repair_rounds}: "
                        f"routed {created} repair task(s) to the owning lane agents."
                    )
                    idle_rounds = 0
                    continue

                # Check for deadlock or stalled tasks
                idle_rounds += 1
                if idle_rounds >= 3:
                    # Recover any stalled RUNNING tasks
                    stalled_running = [t for t in self.scheduler.tasks.values() if t.status == TaskStatus.RUNNING]
                    for st in stalled_running:
                        logger.warning(f"[Supervisor] ⚡ Recovering stalled RUNNING task {st.task_id} ('{st.title}') back to PENDING.")
                        st.status = TaskStatus.PENDING

                    pending_tasks = [t for t in self.scheduler.tasks.values() if t.status == TaskStatus.PENDING]
                    if pending_tasks:
                        logger.warning(
                            f"[Supervisor] ⚡ Deadlock resolution: Unblocking {len(pending_tasks)} remaining pending task(s) "
                            f"to guarantee swarm completion: {', '.join(t.task_id for t in pending_tasks)}"
                        )
                        ready_tasks = [pending_tasks[0]]
                        idle_rounds = 0
                    else:
                        logger.info("[Supervisor] All tasks have been processed.")
                        break
                else:
                    time.sleep(1)
                    continue


            idle_rounds = 0

            if len(ready_tasks) == 1:
                # Single task — run directly
                self._execute_single_task(ready_tasks[0])
            else:
                # Multiple independent tasks — run in parallel!
                print(f"\n[Supervisor] ⚡ Running {len(ready_tasks)} tasks in PARALLEL:")
                for t in ready_tasks:
                    print(f"[Supervisor]    → {t.title} ({t.lane}) via {self.agents.get(t.lane, self.agents['backend']).name}")

                with ThreadPoolExecutor(max_workers=min(len(ready_tasks), 3)) as pool:
                    futures = {
                        pool.submit(self._execute_single_task, task): task
                        for task in ready_tasks
                    }
                    for future in as_completed(futures):
                        task = futures[future]
                        try:
                            future.result()
                        except Exception as e:
                            logger.error(f"[Supervisor] Thread error for {task.task_id}: {e}")
                            self.scheduler.update_task_status(task.task_id, TaskStatus.FAILED)

        # ═══════════════════════════════════════════════════════
        # SUMMARY
        # ═══════════════════════════════════════════════════════
        # Repair tasks created by the verification loop join the same run, so the
        # final task count is whatever the scheduler ended up holding.
        total_tasks = len(self.scheduler.tasks)

        summary = {
            "total_tasks": total_tasks,
            "completed": self.tasks_completed,
            "failed": self.tasks_failed,
            "files_changed": len(set(self.total_files_changed)),
            "tasks": self.task_results,
            "verification_rounds": len(self.verification_history),
            "repair_tasks_created": self.repair_tasks_created,
            "verification_max_repair_rounds": self.max_platform_repair_rounds,
        }

        # ── Gate B/C: global platform verification of the whole workspace ─────
        # The swarm summary never claims success from task counts alone: the last
        # platform verification round (dynamic stages, run inside the DAG loop)
        # decides the honest global status for the assembled application.
        global_verification: dict[str, Any] = {"skipped": True, "reason": "verification engine unavailable"}
        if self.verification_history:
            global_verification = self.verification_history[-1]
        elif _VERIFICATION_AVAILABLE:
            try:
                global_verification = self._platform_verify() or global_verification
            except Exception as g_exc:
                global_verification = {"skipped": True, "reason": str(g_exc)[:300]}

        if global_verification.get("skipped"):
            platform_status = "unverified"
        elif global_verification.get("passed"):
            platform_status = "runnable"
        else:
            platform_status = "not_runnable"

        summary["agent_reported_status"] = (
            "completed" if self.tasks_completed == total_tasks and total_tasks > 0
            else ("partial" if self.tasks_completed else "failed")
        )
        summary["platform_verified_status"] = platform_status
        summary["platform_verification"] = global_verification
        print(f"[Supervisor] 🔎 Platform verification (Gate B/C): {platform_status} "
              f"(agent-reported: {summary['agent_reported_status']})")

        print(f"\n{'#'*60}")
        print(f"[Supervisor] 📊 Execution Summary")
        print(f"[Supervisor]    Completed: {summary['completed']}/{total_tasks}")
        print(f"[Supervisor]    Failed:    {summary['failed']}/{total_tasks}")
        print(f"[Supervisor]    Files:     {summary['files_changed']} unique files changed")
        print(f"{'#'*60}\n")

        # Persist task summary to .agent/task_summary.json (and per-agent file).
        # Merge (never overwrite): multiple sub-agent containers share /workspace/.agent,
        # so a plain 'w' write from the last finishing agent erases every other
        # agent's task history.
        try:
            self._persist_merged_summary(summary)
        except Exception as se:
            logger.warning(f"[Supervisor] Could not write task_summary.json: {se}")

        self._post_event("supervisor_completed", summary)
        return summary

    # ------------------------------------------------------------------
    # Summary persistence: cross-agent merge with atomic writes
    # ------------------------------------------------------------------

    @staticmethod
    def _merge_summaries(summary_dir: str, summary: dict[str, Any]) -> dict[str, Any]:
        """Merge this run's summary into the existing task_summary.json.

        Task results are keyed by task_id: previous runs' entries are kept,
        this run's entries win on conflict. Totals are recomputed from the
        merged ledger so the summary stays honest across agents and runs.
        """
        path = os.path.join(summary_dir, "task_summary.json")
        existing: dict[str, Any] = {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except (OSError, ValueError):
            existing = {}

        merged_tasks: dict[str, Any] = dict(existing.get("tasks") or {})
        merged_tasks.update(summary.get("tasks") or {})

        completed = sum(
            1 for t in merged_tasks.values()
            if isinstance(t, dict) and t.get("status") == "completed"
        )
        failed = sum(
            1 for t in merged_tasks.values()
            if isinstance(t, dict) and t.get("status") == "failed"
        )

        files_changed: set[str] = set()
        for t in merged_tasks.values():
            if isinstance(t, dict):
                for fp in (t.get("files_changed") or []):
                    files_changed.add(str(fp))

        merged = dict(existing)
        merged.update(summary)
        merged["total_tasks"] = len(merged_tasks)
        merged["completed"] = completed
        merged["failed"] = failed
        merged["tasks"] = merged_tasks
        if files_changed:
            merged["files_changed"] = len(files_changed)
        merged["agent_reported_status"] = (
            "completed" if merged_tasks and completed == len(merged_tasks)
            else ("partial" if completed else "failed")
        )
        return merged

    def _persist_merged_summary(self, summary: dict[str, Any]) -> None:
        """Write task summaries atomically under an advisory lock.

        - task_summary.json: merged across all agents/runs (history preserved).
        - task_summary_<agent>.json: this agent's own run summary (overwrite OK).
        """
        import tempfile

        agent_id = os.environ.get("AGENT_ID")
        clean_aid = "".join(c for c in agent_id if c.isalnum() or c == "_") if agent_id else ""
        summary_dir = os.path.join(self.workspace_path, ".agent")
        os.makedirs(summary_dir, exist_ok=True)

        lock_path = os.path.join(summary_dir, "task_summary.lock")
        lock_fd = None
        deadline = time.time() + 10
        while time.time() < deadline:
            try:
                lock_fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                break
            except FileExistsError:
                time.sleep(0.1)
        if lock_fd is None:
            # Stale or contended lock — take over rather than lose history.
            try:
                os.unlink(lock_path)
            except OSError:
                pass
            try:
                lock_fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                pass  # best-effort; atomic replace below still prevents torn files

        try:
            merged = self._merge_summaries(summary_dir, summary)

            writes: list[tuple[str, dict[str, Any]]] = [
                (os.path.join(summary_dir, "task_summary.json"), merged)
            ]
            if clean_aid:
                writes.append(
                    (os.path.join(summary_dir, f"task_summary_{clean_aid}.json"), summary)
                )

            for path, data in writes:
                fd, tmp_path = tempfile.mkstemp(dir=summary_dir, suffix=".tmp")
                try:
                    with os.fdopen(fd, "w", encoding="utf-8") as f:
                        json.dump(data, f, indent=2)
                    os.replace(tmp_path, path)
                except Exception:
                    try:
                        os.unlink(tmp_path)
                    except OSError:
                        pass
                    raise

            print(f"[Supervisor] 📝 Task summary merged into "
                  f"{os.path.join(summary_dir, 'task_summary.json')} "
                  f"({merged.get('total_tasks', 0)} tasks in ledger)")
        finally:
            if lock_fd is not None:
                try:
                    os.close(lock_fd)
                    os.unlink(lock_path)
                except OSError:
                    pass
