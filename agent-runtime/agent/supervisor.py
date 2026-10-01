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
    ):
        self.workspace_path = workspace_path
        self.mcp = mcp
        self.router = router
        self.callback = callback

        # DAG Scheduler — loads tasks and determines execution order
        config_path = os.path.join(workspace_path, ".agent", "task_config.json")
        if not os.path.exists(config_path):
            # Fallback: try workspace root
            config_path = os.path.join(workspace_path, "task_config.json")
        self.scheduler = DAGScheduler(config_path)

        # IPC Router — file-based inter-agent communication
        self.ipc = IPCRouter(workspace_path)

        # Git Tools — for auto-commit and push
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
        agent = self.agents.get(task.lane)
        if not agent:
            # Default to backend agent if lane is unknown
            logger.warning(f"[Supervisor] No agent for lane '{task.lane}', defaulting to BackendAgent")
            agent = self.agents["backend"]

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
        result = agent.execute_task(task, self.workspace_path, self.mcp, self.router)
        elapsed = time.time() - start_time

        if result.success:
            self.tasks_completed += 1
            self.total_files_changed.extend(result.files_changed)
            self.scheduler.update_task_status(task_id, TaskStatus.COMPLETED)

            print(f"\n[Supervisor] ✅ Task {task_id} completed by {agent.name} "
                  f"in {elapsed:.1f}s ({len(result.files_changed)} files changed)")

            self._post_event("task_completed", {
                "task_id": task_id,
                "agent": agent.name,
                "elapsed_seconds": round(elapsed, 1),
                "files_changed": len(result.files_changed),
            })

            # ═══════════════════════════════════════════════════
            # AUTO-COMMIT + AUTO-PUSH after each task
            # ═══════════════════════════════════════════════════
            try:
                commit_msg = (
                    f"[{agent.name}] Completed: {task.title}\n\n"
                    f"Task ID: {task_id}\n"
                    f"Files changed: {len(result.files_changed)}\n"
                    f"Duration: {elapsed:.1f}s"
                )
                commit_result = self.git_tools.commit(commit_msg)
                if commit_result.success:
                    commit_hash = commit_result.data.get("commit_hash", "unknown")
                    print(f"[Supervisor] 📝 Committed: {commit_hash[:8]}")

                    # Push to remote
                    push_result = self.git_tools.push()
                    if push_result.success:
                        print(f"[Supervisor] 🚀 Pushed to remote")
                        self._post_event("git_push_completed", {
                            "task_id": task_id,
                            "commit_hash": commit_hash,
                            "push_success": True,
                        })
                    else:
                        print(f"[Supervisor] ⚠️ Push failed: {push_result.error}")
                else:
                    print(f"[Supervisor] ⚠️ Commit failed: {commit_result.error}")
            except Exception as e:
                logger.error(f"[Supervisor] Git operations failed for {task_id}: {e}")

            # Notify dependent tasks via IPC
            self.ipc.broadcast("Supervisor", "dependency_ready", {
                "task_id": task_id,
                "status": "completed",
            })

            return True

        else:
            self.tasks_failed += 1
            self.scheduler.update_task_status(task_id, TaskStatus.FAILED)

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
        }

        print(f"\n{'#'*60}")
        print(f"[Supervisor] 📊 Execution Summary")
        print(f"[Supervisor]    Completed: {summary['completed']}/{total_tasks}")
        print(f"[Supervisor]    Failed:    {summary['failed']}/{total_tasks}")
        print(f"[Supervisor]    Files:     {summary['files_changed']} unique files changed")
        print(f"{'#'*60}\n")

        self._post_event("supervisor_completed", summary)
        return summary
