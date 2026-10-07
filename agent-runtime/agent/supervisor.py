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

import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable

from mcp.server import MCPServer
from mcp.git_tools import GitTools
from agent.model_router import ModelRouter
from agent.dag_scheduler import DAGScheduler, TaskStatus
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

    def _post_event(self, event_type: str, data: dict[str, Any]) -> None:
        """Post a lifecycle event to the control plane."""
        if self.callback:
            try:
                self.callback(event_type, data)
            except Exception as e:
                logger.error(f"[Supervisor] Callback error for '{event_type}': {e}")
        # Also log for visibility
        logger.info(f"[Supervisor] Event: {event_type} | {json.dumps(data, default=str)[:200]}")

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

        task_id = task.task_id
        print(f"\n{'='*60}")
        print(f"[Supervisor] 🚀 Dispatching task to {agent.name}: {task.title}")
        print(f"[Supervisor]    Task ID: {task_id} | Lane: {task.lane}")
        print(f"{'='*60}\n")

        # Update status to RUNNING
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
        # DELEGATE: Sub-agent runs its ReAct tool loop
        # ═══════════════════════════════════════════════════
        start_time = time.time()
        result = agent.execute_task(task, self.workspace_path, self.mcp, self.router, context=self.task_config)
        elapsed = time.time() - start_time

        # ── Gate A+: platform-owned per-task verification before accepting success ──
        # The sub-agent already parse-checked its own files (Gate A). This second,
        # independent pass catches files the agent's own gate missed. A failed gate
        # flips the task to failed with a classified error — agent opinion is never
        # the final word.
        if result.success and _VERIFICATION_AVAILABLE:
            try:
                gate = VerificationEngine(self.workspace_path).verify_task_changes(result.files_changed)
                result.verification = gate.to_dict()
                if not gate.passed:
                    result.success = False
                    result.error = f"Platform per-task verification failed:\n{gate.detail}"
            except Exception as gate_err:
                result.verification = {"skipped": True, "reason": str(gate_err)[:300]}
        elif result.success:
            result.verification = {"skipped": True, "reason": "verification engine unavailable"}

        if result.success:
            self.tasks_completed += 1
            self.total_files_changed.extend(result.files_changed)
            self.scheduler.update_task_status(task_id, TaskStatus.COMPLETED)
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
            }

            print(f"\n[Supervisor] ✅ Task {task_id} completed by {agent.name} "
                  f"in {elapsed:.1f}s ({len(result.files_changed)} files changed)")

            self._post_event("task_completed", {
                "task_id": task_id,
                "agent": agent.name,
                "elapsed_seconds": round(elapsed, 1),
                "files_changed": len(result.files_changed),
            })

            # Notify dependent tasks via IPC
            self.ipc.broadcast("Supervisor", "dependency_ready", {
                "task_id": task_id,
                "status": "completed",
            })

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

        # ═══════════════════════════════════════════════════════
        # MAIN EXECUTION LOOP — process DAG in topological order
        # ═══════════════════════════════════════════════════════
        max_idle_rounds = 10
        idle_rounds = 0

        while True:
            ready_tasks = self.scheduler.get_ready_tasks()

            if not ready_tasks:
                # Check if all done
                all_done = all(
                    t.status in (TaskStatus.COMPLETED, TaskStatus.FAILED)
                    for t in self.scheduler.tasks.values()
                )
                if all_done:
                    print(f"\n[Supervisor] 🏁 All tasks processed!")
                    break

                # Check for deadlock
                any_running = any(
                    t.status == TaskStatus.RUNNING
                    for t in self.scheduler.tasks.values()
                )
                if not any_running:
                    idle_rounds += 1
                    if idle_rounds > max_idle_rounds:
                        logger.error("[Supervisor] Deadlock detected — tasks blocked by failed dependencies")
                        break
                    time.sleep(1)
                    continue
                else:
                    idle_rounds = 0
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
        summary = {
            "total_tasks": total_tasks,
            "completed": self.tasks_completed,
            "failed": self.tasks_failed,
            "files_changed": len(set(self.total_files_changed)),
            "tasks": self.task_results,
        }

        # ── Gate B/C: global platform verification of the whole workspace ─────
        # The swarm summary no longer claims success from task counts alone: the
        # platform proves the assembled app is runnable (foundation/imports/boot/
        # contract) and records the honest global status.
        global_verification: dict[str, Any] = {"skipped": True, "reason": "verification engine unavailable"}
        if _VERIFICATION_AVAILABLE:
            try:
                g_report = VerificationEngine(self.workspace_path).run_full_verification(
                    stages=["foundation", "imports", "boot", "contract"]
                )
                global_verification = g_report.to_dict()
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

        # Persist task summary to .agent/task_summary.json (and per-agent file)
        try:
            agent_id = os.environ.get("AGENT_ID")
            clean_aid = "".join(c for c in agent_id if c.isalnum() or c == "_") if agent_id else ""
            summary_dir = os.path.join(self.workspace_path, ".agent")
            os.makedirs(summary_dir, exist_ok=True)

            # Write standard summary
            summary_path = os.path.join(summary_dir, "task_summary.json")
            with open(summary_path, "w", encoding="utf-8") as f:
                json.dump(summary, f, indent=2)

            # Write per-agent summary if running in dedicated sub-agent container
            if clean_aid:
                per_agent_path = os.path.join(summary_dir, f"task_summary_{clean_aid}.json")
                with open(per_agent_path, "w", encoding="utf-8") as f:
                    json.dump(summary, f, indent=2)

            print(f"[Supervisor] 📝 Task summary written to {summary_path}")
        except Exception as se:
            logger.warning(f"[Supervisor] Could not write task_summary.json: {se}")

        self._post_event("supervisor_completed", summary)
        return summary
