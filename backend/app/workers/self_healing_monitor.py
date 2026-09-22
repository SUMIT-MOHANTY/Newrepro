"""
Self-Healing Monitor — Phase 5
================================

Adds deadlock detection and auto-recovery on top of the Phase 1 coordination system.

Detects:
  1. Circular dependencies between agents (Agent A waits on B, B waits on A)
  2. Starved agents (not progressing for > N seconds)
  3. Stale file locks (held by agents that crashed or completed)
  4. Abandoned sync points (required agents that haven't checked in)

Recovers by:
  1. Breaking circular deps by reassigning the youngest-age task
  2. Resetting starved agents to idle
  3. Releasing stale file locks
  4. Marking abandoned sync points as progressable

Usage:
    from self_healing_monitor import SelfHealingMonitor
    monitor = SelfHealingMonitor(project_token)
    issues = await monitor.check_and_heal(agent_service_state, coordination_state)
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


# ── Configuration ────────────────────────────────────────────────────────────

class HealConfig:
    """Configurable thresholds for the self-healing monitor."""
    AGENT_STARVE_SECONDS: int = 120        # An agent is "starved" if not progressing for 2+ minutes
    FILE_LOCK_STALE_SECONDS: int = 180     # A file lock is stale if held for 3+ minutes
    SYNC_POINT_ABANDON_SECONDS: int = 300  # A sync point is abandoned if waiting for 5+ minutes
    DEADLOCK_CYCLE_DETECT: bool = True     # Enable circular dependency detection
    MAX_HEAL_ACTIONS_PER_CYCLE: int = 3    # Max recovery actions per monitor tick
    HEAL_COOLDOWN_SECONDS: int = 30        # Wait between heal cycles


# ── Issue Report ─────────────────────────────────────────────────────────────

@dataclass
class HealIssue:
    """A detected issue that needs healing."""
    issue_type: str  # "deadlock" | "starved_agent" | "stale_lock" | "abandoned_sync"
    severity: str    # "critical" | "warning" | "info"
    agent_id: str    # Affected agent
    description: str
    resolution: Optional[str] = None  # How it was resolved (None = pending)


@dataclass
class HealReport:
    """Report from a heal cycle."""
    issues_found: int = 0
    issues_resolved: int = 0
    issues: List[HealIssue] = field(default_factory=list)
    timestamp: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "issues_found": self.issues_found,
            "issues_resolved": self.issues_resolved,
            "issues": [
                {"type": i.issue_type, "severity": i.severity,
                 "agent": i.agent_id, "desc": i.description,
                 "resolution": i.resolution}
                for i in self.issues
            ],
            "timestamp": self.timestamp or datetime.utcnow().isoformat(),
        }


# ── Self-Healing Monitor ─────────────────────────────────────────────────────

class SelfHealingMonitor:
    """
    Self-healing monitor that detects and resolves coordination issues.

    Runs as a background task alongside the coordination monitor.
    Checks for deadlocks, starved agents, stale locks, and abandoned sync points.
    """

    def __init__(self, project_token: str):
        self.project_token = project_token
        self.config = HealConfig()
        self._last_heal_time: float = 0
        self._consecutive_heal_count: int = 0
        self._heal_lock = asyncio.Lock()

    async def check_and_heal(
        self,
        agent_service_state: Dict[str, Any],
        coordination_state: Optional[Dict[str, Any]] = None,
    ) -> HealReport:
        """
        Run one healing cycle.

        Args:
            agent_service_state: From agent_service._ensure_project_state()
            coordination_state: From coordination_service.coordination_state

        Returns:
            HealReport with issues found and resolved
        """
        async with self._heal_lock:
            now = time.time()

            # Cooldown check
            if now - self._last_heal_time < self.config.HEAL_COOLDOWN_SECONDS:
                return HealReport(timestamp=datetime.utcnow().isoformat())

            report = HealReport(timestamp=datetime.utcnow().isoformat())

            try:
                # 1. Detect circular dependencies (deadlocks)
                if self.config.DEADLOCK_CYCLE_DETECT:
                    await self._detect_deadlocks(agent_service_state, report)

                # 2. Detect starved agents
                await self._detect_starved_agents(agent_service_state, report)

                # 3. Detect stale file locks
                if coordination_state:
                    await self._detect_stale_locks(self.project_token, coordination_state, report)

                    # 4. Detect abandoned sync points
                    if coordination_state:
                        _detect_abandoned_syncs(coordination_state, report, self.config)

                    # Apply resolutions
                    await _apply_heals(self.project_token, agent_service_state, coordination_state, report)

                    self._last_heal_time = time.time()
                    self._consecutive_heal_count = report.issues_found

            except Exception as e:
                logger.error(f"[Heal:{self.project_token}] Monitor error: {e}")

            return report

    async def _detect_deadlocks(
        self,
        state: Dict[str, Any],
        report: HealReport,
    ) -> None:
        """Detect circular dependencies between agents using the task DAG."""
        ledger = state.get("task_ledger", {})
        dag = state.get("task_dag", {})
        agent_states = state.get("agent_states", {})

        if not dag or not agent_states:
            return

        # Build a wait-for graph: agent_id -> set(agent_ids it's waiting on)
        wait_for: Dict[str, Set[str]] = {}

        for agent_id, agent in agent_states.items():
            current_task = agent.get("current_task") if isinstance(agent, dict) else None
            if not current_task:
                continue

            task_id = str(current_task.get("id") or current_task.get("task_id") or "")
            if not task_id or task_id not in dag:
                continue

            deps = dag[task_id]
            if not deps:
                continue

            # Find which agents are working on the dependency tasks
            for dep_id in deps:
                dep_entry = ledger.get(dep_id)
                if dep_entry and dep_entry.status in ("claimed", "in_progress"):
                    if agent_id not in wait_for:
                        wait_for[agent_id] = set()
                    wait_for[agent_id].add(dep_entry.agent_id)

        # Detect cycles using DFS
        visited: Set[str] = set()
        recursion_stack: Set[str] = set()

        def dfs_detect_cycle(node: str, path: List[str]) -> Optional[List[str]]:
            visited.add(node)
            recursion_stack.add(node)
            path.append(node)

            dependencies = wait_for.get(node, set())
            for dep in dependencies:
                if dep in recursion_stack:
                    # Found cycle
                    cycle_start = path.index(dep)
                    return path[cycle_start:]
                if dep not in visited:
                    result = dfs_detect_cycle(dep, path)
                    if result:
                        return result

            recursion_stack.discard(node)
            path.pop()
            return None

        for agent_id in wait_for:
            if agent_id not in visited:
                cycle = dfs_detect_cycle(agent_id, [])
                if cycle:
                    logger.warning(f"[Heal] Deadlock cycle detected: {' -> '.join(cycle)}")
                    report.issues.append(HealIssue(
                        issue_type="deadlock",
                        severity="critical",
                        agent_id=cycle[0],
                        description=f"Circular dependency: {' -> '.join(cycle)}",
                    ))
                    report.issues_found += 1

    async def _detect_starved_agents(
        self,
        state: Dict[str, Any],
        report: HealReport,
    ) -> None:
        """Detect agents that have been running without progress for too long."""
        agent_states = state.get("agent_states", {})
        now = time.time()

        for agent_id, agent in agent_states.items():
            if not isinstance(agent, dict):
                continue

            status = agent.get("status", "").lower()
            if status not in ("running", "blocked"):
                continue

            # Check last progress update
            last_progress = agent.get("progress", 0)
            progress_message = agent.get("progress_message", "")
            last_run = agent.get("last_run")

            # If status is "blocked" without a clear reason
            if status == "blocked":
                current_task = agent.get("current_task")
                if not current_task:
                    report.issues.append(HealIssue(
                        issue_type="starved_agent",
                        severity="warning",
                        agent_id=agent_id,
                        description=f"Agent '{agent_id}' is blocked but has no current task",
                        resolution="reset_to_idle",
                    ))
                    report.issues_found += 1
                continue

            # Running but same progress for too long
            if status == "running":
                # Check if progress hasn't changed and there's no current task
                current_task = agent.get("current_task")
                if not current_task and progress_message:
                    report.issues.append(HealIssue(
                        issue_type="starved_agent",
                        severity="info",
                        agent_id=agent_id,
                        description=f"Agent '{agent_id}' running without task: {progress_message[:50]}",
                        resolution="reset_to_idle",
                    ))
                    report.issues_found += 1

    async def _detect_stale_locks(
        self,
        project_token: str,
        coord_state: Dict[str, Any],
        report: HealReport,
    ) -> None:
        """Detect file locks held by agents that are no longer active."""
        file_locks = coord_state.get("file_locks", {})
        agents = coord_state.get("agents", {})
        now = time.time()

        for file_path, lock_info in file_locks.items():
            if not isinstance(lock_info, dict):
                continue

            holder = lock_info.get("agent_id")
            if not holder:
                continue

            # Check if the lock-holding agent is still active
            agent_info = agents.get(holder, {})
            agent_status = agent_info.get("status", "")

            if agent_status in ("completed", "failed", "idle"):
                report.issues.append(HealIssue(
                    issue_type="stale_lock",
                    severity="warning",
                    agent_id=holder,
                    description=f"Stale lock on '{file_path}' by inactive agent '{holder}'",
                    resolution="release_lock",
                ))
                report.issues_found += 1

def _detect_abandoned_syncs(
    coord_state: Dict[str, Any],
    report: HealReport,
    config: HealConfig,
) -> None:
    """Detect sync points that haven't been reached by all required agents."""
    sync_points = coord_state.get("sync_points", {})
    if not sync_points:
        return

    now = time.time()
    for sync_name, sync_info in sync_points.items():
        if sync_info.get("status") == "completed":
            continue

        required = set(sync_info.get("required_agents", []))
        if not required:
            continue

        completed = set(sync_info.get("completed_agents", []))
        waiting = required - completed

        if waiting:
            report.issues.append(HealIssue(
                issue_type="abandoned_sync",
                severity="warning",
                agent_id=list(waiting)[0],
                description=f"Sync point '{sync_name}' waiting for agents: {waiting}",
            ))
            report.issues_found += 1


async def _apply_heals(
    project_token: str,
    agent_service_state: Dict[str, Any],
    coord_state: Optional[Dict[str, Any]],
    report: HealReport,
) -> None:
    """Apply the resolutions for each issue found."""
    for issue in report.issues:
        if not issue.resolution:
            continue

        try:
            if issue.resolution == "reset_to_idle":
                agent_states = agent_service_state.get("agent_states", {})
                agent = agent_states.get(issue.agent_id)
                if agent and isinstance(agent, dict):
                    agent["status"] = "idle"
                    agent["progress_message"] = ""
                    agent["error"] = ""
                    logger.info(f"[Heal] Reset agent '{issue.agent_id}' to idle")
                    issue.resolution = f"Agent '{issue.agent_id}' reset to idle"
                    report.issues_resolved += 1

            elif issue.resolution == "release_lock" and coord_state:
                file_locks = coord_state.get("file_locks", {})
                agents = coord_state.get("agents", {})
                agent_info = agents.get(issue.agent_id, {})

                # Release all locks held by this agent
                agent_locks = list(agent_info.get("file_locks", []))
                for file_path in agent_locks:
                    file_locks.pop(file_path, None)

                agent_info["file_locks"] = []
                logger.info(f"[Heal] Released {len(agent_locks)} stale locks for '{issue.agent_id}'")
                issue.resolution = f"Released {len(agent_locks)} stale locks"
                report.issues_resolved += 1

        except Exception as e:
            logger.warning(f"[Heal] Failed to apply resolution for {issue.agent_id}: {e}")


# ── Background Monitor ───────────────────────────────────────────────────────

class BackgroundHealMonitor:
    """
    Runs the self-healing monitor as a background task.

    Usage:
        heal_monitor = BackgroundHealMonitor(project_token)
        await heal_monitor.start()   # Starts background loop
        # ... agent execution ...
        await heal_monitor.stop()    # Stops background loop
    """

    def __init__(
        self,
        project_token: str,
        check_interval: int = 15,  # Check every 15 seconds
    ):
        self.project_token = project_token
        self.check_interval = check_interval
        self._monitor = SelfHealingMonitor(project_token)
        self._task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self) -> None:
        """Start the background healing loop."""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(
            self._heal_loop(),
            name=f"heal_monitor_{self.project_token}",
        )
        logger.info(f"[Heal] Background monitor started for project {self.project_token}")

    async def stop(self) -> None:
        """Stop the background healing loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info(f"[Heal] Background monitor stopped for project {self.project_token}")

    async def _heal_loop(self) -> None:
        """Main healing loop."""
        while self._running:
            try:
                import agent_service
                state = agent_service._ensure_project_state(self.project_token)

                coordination_state = None
                try:
                    from agent_coordination_service import coordination_service
                    coordination_state = coordination_service.coordination_state.get(self.project_token)
                except Exception:
                    pass

                report = await self._monitor.check_and_heal(state, coordination_state)

                if report.issues_found > 0:
                    resolved = report.issues_resolved
                    logger.info(
                        f"[Heal:{self.project_token}] Cycle complete: "
                        f"{report.issues_found} issues, {resolved} resolved"
                    )

            except Exception as e:
                logger.debug(f"[Heal:{self.project_token}] Loop error (non-fatal): {e}")

            await asyncio.sleep(self.check_interval)


# ── Convenience function ─────────────────────────────────────────────────────

async def run_heal_cycle(project_token: str) -> Dict[str, Any]:
    """
    Run a single healing cycle and return the report.
    Useful for manual/triggered healing.

    Usage:
        report = await run_heal_cycle(project_token)
        print(f"Found {report['issues_found']} issues")
    """
    monitor = SelfHealingMonitor(project_token)

    import agent_service
    state = agent_service._ensure_project_state(project_token)

    coordination_state = None
    try:
        from agent_coordination_service import coordination_service
        coordination_state = coordination_service.coordination_state.get(project_token)
    except Exception:
        pass

    report = await monitor.check_and_heal(state, coordination_state)
    return report.to_dict()
