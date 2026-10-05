"""
Project Execution Tracker — shared coordination layer for agent swarm execution.

Purpose:
- Track the live execution state of one project across all agents/tasks.
- Register failures with a classification layer so repeated structural problems
  can be detected instead of retried forever by a single agent.
- Provide a clear answer to: "Is this project currently blocked or unrunnable?"

Design notes:
- This is a local-first coordination helper. It does not assume any external
  orchestrator is perfect. It is meant to be used by master orchestrator,
  agent managers, task services, and runtime callbacks.
- Classifications are intentionally coarse at first so the system can react
  without needing perfect diagnosis on day one.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Failure classifications
# ---------------------------------------------------------------------------

FailureClass = str

FAILURE_CLASSES = {
    "syntax_or_parse_error",
    "type_or_import_error",
    "build_error",
    "generation_error",
    "dependency_or_setup_error",
    "config_or_provider_error",
    "runtime_error",
    "environment_or_env_error",
    "contract_or_integration_conflict",
    "requirement_gap",
    "unknown",
}

# ---------------------------------------------------------------------------
# In-memory project tracker
# ---------------------------------------------------------------------------

class ProjectExecutionTracker:
    """
    Tracks execution state for one project.

    This is deliberately simple at first:
    - current status
    - known tasks
    - known failures
    - repeated failure detection
    - blocked / unrunnable heuristic
    """

    def __init__(self, project_token: str) -> None:
        self.project_token = project_token
        self.status: str = "pending"
        self.updated_at: datetime = datetime.now(timezone.utc)
        self.tasks: Dict[str, Dict[str, Any]] = {}
        self.failures: List[Dict[str, Any]] = []
        self.repeated_failures: List[Dict[str, Any]] = []
        self.blocked_reasons: List[str] = []
        self.verified_runnable: Optional[bool] = None
        self.verified_at: Optional[datetime] = None

    # ------------------------------------------------------------------
    # Project status
    # ------------------------------------------------------------------

    def set_status(self, status: str) -> None:
        self.status = status
        self.updated_at = datetime.now(timezone.utc)
        logger.debug(
            "[ProjectExecutionTracker] %s status=%s",
            self.project_token,
            status,
        )

    # ------------------------------------------------------------------
    # Task bookkeeping
    # ------------------------------------------------------------------

    def register_task(self, task_id: str, info: Dict[str, Any]) -> None:
        self.tasks[task_id] = info
        self.updated_at = datetime.now(timezone.utc)

    def mark_task_completed(self, task_id: str, verified: bool = False) -> None:
        task = self.tasks.get(task_id)
        if task:
            task["completed"] = True
            task["verified"] = verified
        self.updated_at = datetime.now(timezone.utc)

    def mark_task_failed(self, task_id: str, error_message: str) -> None:
        task = self.tasks.get(task_id)
        if task:
            task["completed"] = False
            task["failed"] = True
            task["error_message"] = error_message
        self.updated_at = datetime.now(timezone.utc)

    # ------------------------------------------------------------------
    # Failure registration
    # ------------------------------------------------------------------

    def register_failure(
        self,
        task_id: Optional[str],
        agent_id: str,
        error_message: str,
        failure_class: FailureClass,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Register a failure with classification.

        Returns a failure record so callers can log or act on it immediately.
        """
        if failure_class not in FAILURE_CLASSES:
            failure_class = "unknown"

        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "task_id": task_id,
            "agent_id": agent_id,
            "error_message": error_message[:2000],
            "failure_class": failure_class,
            "context": context or {},
        }

        self.failures.append(record)
        self.updated_at = datetime.now(timezone.utc)

        logger.warning(
            "[ProjectExecutionTracker] Failure registered on %s: class=%s task=%s agent=%s err=%s",
            self.project_token,
            failure_class,
            task_id,
            agent_id,
            error_message[:200],
        )

        repeated = self._check_repeated_failure(record)
        if repeated:
            self.repeated_failures.append(repeated)
            reason = f"Repeated failure detected: class={failure_class} task={task_id} agent={agent_id}"
            if reason not in self.blocked_reasons:
                self.blocked_reasons.append(reason)
            logger.warning(
                "[ProjectExecutionTracker] Repeated failure on %s: %s",
                self.project_token,
                reason,
            )

        self._recompute_blockers()
        return record

    # ------------------------------------------------------------------
    # Repeated failure detection
    # ------------------------------------------------------------------

    def _check_repeated_failure(self, record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Detect repeated similar failures.

        Simple heuristic:
        - same failure class
        - same task_id or same agent_id
        - within a short recent window
        """
        recent = self.failures[-6:] if len(self.failures) > 6 else self.failures
        matches = 0
        for prev in reversed(recent):
            if prev["failure_class"] != record["failure_class"]:
                continue
            if record["task_id"] and prev.get("task_id") == record["task_id"]:
                matches += 1
                continue
            if prev.get("agent_id") == record["agent_id"]:
                matches += 1
                continue
        if matches >= 2:
            return {
                "class": record["failure_class"],
                "task_id": record["task_id"],
                "agent_id": record["agent_id"],
                "occurrences": matches + 1,
                "latest_error": record["error_message"],
            }
        return None

    # ------------------------------------------------------------------
    # Blocked / unrunnable heuristics
    # ------------------------------------------------------------------

    def _recompute_blockers(self) -> None:
        """
        Recompute whether the project appears blocked based on recent failures.

        This is a heuristic layer, not a full diagnosis engine. It is meant to
        give the system a shared signal that something is structurally wrong.
        """
        blockers: List[str] = []

        recent_failures = self.failures[-8:] if len(self.failures) > 8 else self.failures

        has_gen_or_setup = any(
            f["failure_class"] in {"generation_error", "dependency_or_setup_error", "config_or_provider_error"}
            for f in recent_failures
        )
        has_build = any(
            f["failure_class"] == "build_error"
            for f in recent_failures
        )
        has_runtime = any(
            f["failure_class"] == "runtime_error"
            for f in recent_failures
        )
        has_repeated = len(self.repeated_failures) > 0

        if has_repeated:
            blockers.append("repeated_failures")

        if has_gen_or_setup:
            blockers.append("generation_or_setup_failure")

        if has_build:
            blockers.append("build_failure")

        if has_runtime:
            blockers.append("runtime_failure")

        self.blocked_reasons = blockers

    def is_blocked(self) -> bool:
        return len(self.blocked_reasons) > 0

    def is_verified_runnable(self) -> Optional[bool]:
        return self.verified_runnable

    def mark_verified_runnable(self, runnable: bool) -> None:
        self.verified_runnable = runnable
        self.verified_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)
        logger.info(
            "[ProjectExecutionTracker] %s verified_runnable=%s",
            self.project_token,
            runnable,
        )

    # ------------------------------------------------------------------
    # Snapshot
    # ------------------------------------------------------------------

    def snapshot(self) -> Dict[str, Any]:
        return {
            "project_token": self.project_token,
            "status": self.status,
            "updated_at": self.updated_at.isoformat(),
            "task_count": len(self.tasks),
            "completed_tasks": sum(1 for t in self.tasks.values() if t.get("completed")),
            "verified_runnable": self.verified_runnable,
            "is_blocked": self.is_blocked(),
            "blocked_reasons": self.blocked_reasons,
            "failure_count": len(self.failures),
            "recent_failures": [
                {
                    "timestamp": f["timestamp"],
                    "task_id": f["task_id"],
                    "agent_id": f["agent_id"],
                    "failure_class": f["failure_class"],
                    "error_message": f["error_message"][:200],
                }
                for f in self.failures[-10:]
            ],
            "repeated_failure_count": len(self.repeated_failures),
        }


# ---------------------------------------------------------------------------
# Global registry helper
# ---------------------------------------------------------------------------

_project_trackers: Dict[str, ProjectExecutionTracker] = {}


def get_tracker(project_token: str) -> ProjectExecutionTracker:
    """Return or create the execution tracker for a project."""
    if project_token not in _project_trackers:
        _project_trackers[project_token] = ProjectExecutionTracker(project_token)
    return _project_trackers[project_token]


def reset_tracker(project_token: str) -> None:
    """Clear a project tracker. Useful for fresh re-runs."""
    _project_trackers.pop(project_token, None)
    logger.info("[ProjectExecutionTracker] Reset tracker for %s", project_token)


def list_tracker_summaries() -> List[Dict[str, Any]]:
    """Return snapshots for all tracked projects."""
    return [tracker.snapshot() for tracker in _project_trackers.values()]
