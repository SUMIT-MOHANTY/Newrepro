"""
Local State Manager — Primary Source of Truth for Agent Orchestration
=====================================================================
All agent orchestration decisions (task claiming, bootstrap guard, assignment restore,
canonical context) consult this module FIRST. NXDune is used only as a secondary
synchronization layer for governance/visibility purposes.

Design principles:
- Every write to NXDune is mirrored here atomically first.
- On server restart, all agents restore state from local DB — zero NXDune dependency.
- Bootstrap artifacts (canonical tree, tech spec, tech stack) are immutable once set.
- Local DB wins over NXDune for completed task status.
- No background sync threads — NXDune updates happen inline with existing call sites,
  failures are logged to NXDuneSyncLog for audit trail.
"""

import json
import logging
import re
from datetime import datetime
from typing import Dict, List, Optional, Any, Set

from database import SessionLocal
import models

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Task Ownership — claim / complete / restore
# ---------------------------------------------------------------------------

def claim_task_local(
    project_token: str,
    agent_id: str,
    task_id: str,
    task_data: Dict[str, Any],
    task_lane: Optional[str] = None,
) -> bool:
    """
    Atomically claim a task in the local DB.
    Returns True if the claim succeeded (this agent now owns it).
    Returns False if another agent already owns it.

    Replaces the fragile in-memory claimed_task_ids set that was lost on restart.
    """
    db = SessionLocal()
    try:
        # Check if already claimed by someone else
        existing = db.query(models.AgentTaskOwnership).filter(
            models.AgentTaskOwnership.project_token == project_token,
            models.AgentTaskOwnership.task_id == task_id,
        ).first()

        if existing:
            if existing.agent_id == agent_id:
                # Already claimed by this agent — idempotent success
                if existing.status in ("claimed", "in_progress"):
                    logger.debug(f"[LocalState] Task {task_id} re-claimed by same agent {agent_id}")
                    return True
                else:
                    # Task was marked done/failed — do not re-claim
                    logger.info(f"[LocalState] Task {task_id} already {existing.status} by {agent_id} — skipping re-claim")
                    return False
            else:
                if existing.status in ("done", "failed"):
                    # Completed by another agent — treat as unclaimed for a fresh attempt
                    # (shouldn't happen in normal flow but guard against it)
                    logger.warning(f"[LocalState] Task {task_id} done/failed by {existing.agent_id} — allowing fresh claim by {agent_id}")
                else:
                    logger.info(f"[LocalState] Task {task_id} already owned by {existing.agent_id} — rejecting claim by {agent_id}")
                    return False

        title = str(task_data.get("title") or task_data.get("taskName") or "")[:500]
        # Serialize task_data safely (remove non-JSON types)
        safe_task_data = _safe_json(task_data)

        if existing and existing.agent_id != agent_id and existing.status in ("done", "failed"):
            # Fresh claim on completed task — reset the record
            existing.agent_id = agent_id
            existing.task_title = title
            existing.task_data = safe_task_data
            existing.task_lane = task_lane
            existing.status = "claimed"
            existing.claimed_at = datetime.utcnow()
            existing.started_at = None
            existing.completed_at = None
            existing.branch_name = None
            existing.files_written = []
            existing.error_message = None
            existing.nxdune_synced = False
            existing.nxdune_sync_attempts = 0
            existing.updated_at = datetime.utcnow()
        else:
            # New claim record
            record = models.AgentTaskOwnership(
                project_token=project_token,
                task_id=task_id,
                agent_id=agent_id,
                task_title=title,
                task_data=safe_task_data,
                task_lane=task_lane,
                status="claimed",
                claimed_at=datetime.utcnow(),
            )
            db.add(record)

        db.commit()
        logger.info(f"[LocalState] ✅ Task {task_id} claimed by agent {agent_id} (lane={task_lane})")
        return True

    except Exception as e:
        db.rollback()
        logger.error(f"[LocalState] claim_task_local failed for {task_id}/{agent_id}: {e}")
        return False
    finally:
        db.close()


def start_task_local(
    project_token: str,
    agent_id: str,
    task_id: str,
    branch_name: Optional[str] = None,
) -> None:
    """Mark a claimed task as in_progress and record the branch."""
    db = SessionLocal()
    try:
        record = db.query(models.AgentTaskOwnership).filter(
            models.AgentTaskOwnership.project_token == project_token,
            models.AgentTaskOwnership.task_id == task_id,
            models.AgentTaskOwnership.agent_id == agent_id,
        ).first()

        if record:
            record.status = "in_progress"
            record.started_at = datetime.utcnow()
            if branch_name:
                record.branch_name = branch_name
            record.updated_at = datetime.utcnow()
            db.commit()
            logger.info(f"[LocalState] Task {task_id} started by {agent_id} (branch={branch_name})")
        else:
            logger.warning(f"[LocalState] start_task_local: record not found for {task_id}/{agent_id}")
    except Exception as e:
        db.rollback()
        logger.error(f"[LocalState] start_task_local failed: {e}")
    finally:
        db.close()


def complete_task_local(
    project_token: str,
    agent_id: str,
    task_id: str,
    files_written: Optional[List[str]] = None,
    branch_name: Optional[str] = None,
) -> None:
    """
    Record task completion in local DB.
    Called immediately when task finishes — BEFORE any NXDune update attempt.
    Guarantees no progress is lost even if NXDune sync fails.
    """
    db = SessionLocal()
    try:
        record = db.query(models.AgentTaskOwnership).filter(
            models.AgentTaskOwnership.project_token == project_token,
            models.AgentTaskOwnership.task_id == task_id,
            models.AgentTaskOwnership.agent_id == agent_id,
        ).first()

        if record:
            record.status = "done"
            record.completed_at = datetime.utcnow()
            if files_written:
                record.files_written = files_written
            if branch_name:
                record.branch_name = branch_name
            record.updated_at = datetime.utcnow()
        else:
            # Create record if somehow missing (defensive)
            record = models.AgentTaskOwnership(
                project_token=project_token,
                task_id=task_id,
                agent_id=agent_id,
                status="done",
                claimed_at=datetime.utcnow(),
                started_at=datetime.utcnow(),
                completed_at=datetime.utcnow(),
                files_written=files_written or [],
                branch_name=branch_name,
            )
            db.add(record)

        db.commit()
        logger.info(f"[LocalState] ✅ Task {task_id} completed by {agent_id} — {len(files_written or [])} files written")
    except Exception as e:
        db.rollback()
        logger.error(f"[LocalState] complete_task_local failed: {e}")
    finally:
        db.close()


def fail_task_local(
    project_token: str,
    agent_id: str,
    task_id: str,
    error_message: str,
) -> None:
    """Mark task as failed in local DB."""
    db = SessionLocal()
    try:
        record = db.query(models.AgentTaskOwnership).filter(
            models.AgentTaskOwnership.project_token == project_token,
            models.AgentTaskOwnership.task_id == task_id,
            models.AgentTaskOwnership.agent_id == agent_id,
        ).first()

        if record:
            record.status = "failed"
            record.completed_at = datetime.utcnow()
            record.error_message = error_message[:2000] if error_message else None
            record.updated_at = datetime.utcnow()
            db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"[LocalState] fail_task_local failed: {e}")
    finally:
        db.close()


def get_agent_active_task(project_token: str, agent_id: str) -> Optional[Dict[str, Any]]:
    """
    Return the active task data for an agent from local DB.
    Returns None if no active task found.
    Used by assignment restore to bypass the stale in-memory cache.
    """
    db = SessionLocal()
    try:
        record = db.query(models.AgentTaskOwnership).filter(
            models.AgentTaskOwnership.project_token == project_token,
            models.AgentTaskOwnership.agent_id == agent_id,
            models.AgentTaskOwnership.status.in_(["claimed", "in_progress"]),
        ).order_by(models.AgentTaskOwnership.claimed_at.desc()).first()

        if record and record.task_data:
            task = dict(record.task_data)
            task["_local_status"] = record.status
            task["_local_branch"] = record.branch_name
            task["_local_task_id"] = record.task_id
            return task
        return None
    except Exception as e:
        logger.error(f"[LocalState] get_agent_active_task failed: {e}")
        return None
    finally:
        db.close()


def get_all_claimed_tasks(project_token: str) -> Set[str]:
    """
    Return the set of all claimed (non-done, non-failed) task IDs from local DB.
    Replaces the in-memory claimed_task_ids set that was lost on restart.
    """
    db = SessionLocal()
    try:
        records = db.query(models.AgentTaskOwnership.task_id).filter(
            models.AgentTaskOwnership.project_token == project_token,
            models.AgentTaskOwnership.status.in_(["claimed", "in_progress"]),
        ).all()
        return {r.task_id for r in records}
    except Exception as e:
        logger.error(f"[LocalState] get_all_claimed_tasks failed: {e}")
        return set()
    finally:
        db.close()


def is_task_completed_locally(project_token: str, task_id: str) -> bool:
    """
    Check if a task is marked done in local DB.
    Local DB wins over NXDune — if we say it's done, it's done.
    """
    db = SessionLocal()
    try:
        record = db.query(models.AgentTaskOwnership).filter(
            models.AgentTaskOwnership.project_token == project_token,
            models.AgentTaskOwnership.task_id == task_id,
            models.AgentTaskOwnership.status == "done",
        ).first()
        return record is not None
    except Exception as e:
        logger.error(f"[LocalState] is_task_completed_locally failed: {e}")
        return False
    finally:
        db.close()


def get_task_owner(project_token: str, task_id: str) -> Optional[str]:
    """Return the agent_id that currently owns this task, or None."""
    db = SessionLocal()
    try:
        record = db.query(models.AgentTaskOwnership).filter(
            models.AgentTaskOwnership.project_token == project_token,
            models.AgentTaskOwnership.task_id == task_id,
            models.AgentTaskOwnership.status.in_(["claimed", "in_progress"]),
        ).first()
        return record.agent_id if record else None
    except Exception as e:
        logger.error(f"[LocalState] get_task_owner failed: {e}")
        return None
    finally:
        db.close()


def get_local_task_statuses(project_token: str) -> List[Dict[str, Any]]:
    """
    Return a complete local-first snapshot of all task statuses for a project.

    Queries the AgentTaskOwnership table which is the authoritative local source
    of truth for task progress. Sorted by most-recently-updated first.

    Returns a list of dicts, each with:
    - task_id: str
    - agent_id: str
    - status: 'claimed' | 'in_progress' | 'done' | 'failed'
    - claimed_at: ISO timestamp or None
    - started_at: ISO timestamp or None
    - completed_at: ISO timestamp or None
    - files_written_count: int (number of files written)
    - branch_name: str or None
    - nxdune_synced: bool
    - error_message: str or None (first 500 chars)
    - task_title: str or None (from task_data if available)
    - task_lane: str or None (from task_data if available)
    """
    db = SessionLocal()
    try:
        records = db.query(models.AgentTaskOwnership).filter(
            models.AgentTaskOwnership.project_token == project_token,
        ).order_by(models.AgentTaskOwnership.updated_at.desc()).all()

        result = []
        for r in records:
            # Extract title and lane from task_data JSON if available
            task_data = r.task_data or {}
            task_title = (
                task_data.get("title")
                or task_data.get("taskName")
                or task_data.get("task_title")
                or None
            )
            task_lane = (
                task_data.get("task_lane")
                or task_data.get("lane")
                or task_data.get("domain")
                or None
            )

            result.append({
                "task_id": r.task_id,
                "agent_id": r.agent_id,
                "status": r.status,
                "claimed_at": r.claimed_at.isoformat() if r.claimed_at else None,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
                "files_written_count": len(r.files_written or []),
                "files_written": r.files_written or [],
                "branch_name": r.branch_name,
                "nxdune_synced": bool(r.nxdune_synced),
                "error_message": (r.error_message or "")[:500] if r.error_message else None,
                "task_title": task_title,
                "task_lane": task_lane,
                "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            })

        return result
    except Exception as e:
        logger.error(f"[LocalState] get_local_task_statuses failed: {e}")
        return []
    finally:
        db.close()


def get_all_agent_file_ownerships(project_token: str) -> Dict[str, str]:
    """
    Return {file_path: agent_id} for all files written by completed tasks.
    Used for file ownership enforcement in agent prompts.
    """
    db = SessionLocal()
    try:
        records = db.query(
            models.AgentTaskOwnership.agent_id,
            models.AgentTaskOwnership.files_written,
        ).filter(
            models.AgentTaskOwnership.project_token == project_token,
            models.AgentTaskOwnership.status == "done",
            models.AgentTaskOwnership.files_written.isnot(None),
        ).all()

        ownership: Dict[str, str] = {}
        for r in records:
            for fpath in (r.files_written or []):
                ownership[fpath] = r.agent_id
        return ownership
    except Exception as e:
        logger.error(f"[LocalState] get_all_agent_file_ownerships failed: {e}")
        return {}
    finally:
        db.close()


def mark_nxdune_synced(project_token: str, task_id: str) -> None:
    """Mark that NXDune has been successfully updated for this task."""
    db = SessionLocal()
    try:
        record = db.query(models.AgentTaskOwnership).filter(
            models.AgentTaskOwnership.project_token == project_token,
            models.AgentTaskOwnership.task_id == task_id,
        ).first()
        if record:
            record.nxdune_synced = True
            record.nxdune_synced_at = datetime.utcnow()
            record.updated_at = datetime.utcnow()
            db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"[LocalState] mark_nxdune_synced failed: {e}")
    finally:
        db.close()


# ---------------------------------------------------------------------------
# NXDune Sync Logging — audit trail without background service
# ---------------------------------------------------------------------------

def log_nxdune_sync(
    project_token: str,
    operation: str,
    success: bool,
    agent_id: Optional[str] = None,
    task_id: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
    status_code: Optional[int] = None,
    error_message: Optional[str] = None,
    response_body: Optional[str] = None,
) -> None:
    """
    Record any NXDune sync attempt in the audit log.
    Call this from existing NXDune update sites on both success and failure.
    On failure, the payload is preserved here so nothing is lost.
    """
    db = SessionLocal()
    try:
        record = models.NXDuneSyncLog(
            project_token=project_token,
            agent_id=agent_id,
            task_id=task_id,
            operation=operation,
            payload=_safe_json(payload) if payload else None,
            success=success,
            status_code=status_code,
            error_message=(error_message or "")[:2000],
            response_body=(response_body or "")[:4000],
        )
        db.add(record)
        db.commit()
    except Exception as e:
        db.rollback()
        logger.debug(f"[LocalState] log_nxdune_sync failed (non-critical): {e}")
    finally:
        db.close()


def get_pending_nxdune_syncs(project_token: str, limit: int = 50) -> List[Dict[str, Any]]:
    """
    Return failed NXDune sync operations that can be retried.
    Called on-demand (e.g. when a task finishes) — NOT by a background service.
    """
    db = SessionLocal()
    try:
        records = db.query(models.NXDuneSyncLog).filter(
            models.NXDuneSyncLog.project_token == project_token,
            models.NXDuneSyncLog.success == False,
            models.NXDuneSyncLog.permanently_failed == False,
        ).order_by(models.NXDuneSyncLog.created_at.asc()).limit(limit).all()

        return [
            {
                "id": r.id,
                "operation": r.operation,
                "task_id": r.task_id,
                "agent_id": r.agent_id,
                "payload": r.payload,
                "retry_count": r.retry_count,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in records
        ]
    except Exception as e:
        logger.error(f"[LocalState] get_pending_nxdune_syncs failed: {e}")
        return []
    finally:
        db.close()


def mark_sync_log_result(log_id: int, success: bool, error_message: Optional[str] = None) -> None:
    """Update a sync log entry after a retry attempt."""
    db = SessionLocal()
    try:
        record = db.query(models.NXDuneSyncLog).filter(
            models.NXDuneSyncLog.id == log_id
        ).first()
        if record:
            record.success = success
            record.retry_count = (record.retry_count or 0) + 1
            record.last_retry_at = datetime.utcnow()
            if error_message:
                record.error_message = error_message[:2000]
            if record.retry_count >= 5:
                record.permanently_failed = True
            db.commit()
    except Exception as e:
        db.rollback()
        logger.debug(f"[LocalState] mark_sync_log_result failed (non-critical): {e}")
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Canonical State — immutable bootstrap artifacts
# ---------------------------------------------------------------------------

def save_canonical_state(
    project_token: str,
    canonical_tree: Optional[str] = None,
    technical_spec: Optional[str] = None,
    tech_stack: Optional[Dict[str, Any]] = None,
    bootstrap_branch: Optional[str] = None,
    agent_id: Optional[str] = None,
    force_reset: bool = False,
) -> bool:
    """
    Persist the bootstrap-generated canonical project tree, tech spec, and stack.

    IMMUTABILITY RULE:
    - If a record already exists with is_ready=True, this call is a no-op (returns False).
    - Set force_reset=True ONLY for admin/debugging purposes to overwrite.

    Resolves: master agent regenerating canonical tree/spec on every restart.
    """
    db = SessionLocal()
    try:
        record = db.query(models.ProjectCanonicalState).filter(
            models.ProjectCanonicalState.project_token == project_token
        ).first()

        if record and record.is_ready and not force_reset:
            logger.info(f"[LocalState] Canonical state already persisted for {project_token} — skipping (immutable)")
            return False

        domain_map = _build_domain_file_map(canonical_tree) if canonical_tree else None

        if record:
            if canonical_tree is not None:
                record.canonical_tree = canonical_tree
            if technical_spec is not None:
                record.technical_spec = technical_spec
            if tech_stack is not None:
                record.tech_stack = _safe_json(tech_stack)
            if bootstrap_branch is not None:
                record.bootstrap_branch = bootstrap_branch
            if domain_map is not None:
                record.domain_file_map = domain_map
            record.is_ready = True
            record.force_reset = False
            record.version = (record.version or 1) + 1
            record.last_agent_id = agent_id
            record.updated_at = datetime.utcnow()
        else:
            record = models.ProjectCanonicalState(
                project_token=project_token,
                canonical_tree=canonical_tree,
                technical_spec=technical_spec,
                tech_stack=_safe_json(tech_stack) if tech_stack else None,
                bootstrap_branch=bootstrap_branch,
                domain_file_map=domain_map,
                is_ready=True,
                last_agent_id=agent_id,
            )
            db.add(record)

        db.commit()
        logger.info(f"[LocalState] ✅ Canonical state saved for project {project_token} (v{record.version})")
        return True

    except Exception as e:
        db.rollback()
        logger.error(f"[LocalState] save_canonical_state failed: {e}")
        return False
    finally:
        db.close()


def get_canonical_state(project_token: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve the canonical project state from local DB.
    Returns None if bootstrap hasn't completed yet.
    """
    db = SessionLocal()
    try:
        record = db.query(models.ProjectCanonicalState).filter(
            models.ProjectCanonicalState.project_token == project_token,
            models.ProjectCanonicalState.is_ready == True,
        ).first()

        if not record:
            return None

        return {
            "canonical_tree": record.canonical_tree,
            "technical_spec": record.technical_spec,
            "tech_stack": record.tech_stack,
            "bootstrap_branch": record.bootstrap_branch,
            "domain_file_map": record.domain_file_map or {},
            "version": record.version,
        }
    except Exception as e:
        logger.error(f"[LocalState] get_canonical_state failed: {e}")
        return None
    finally:
        db.close()


def is_canonical_state_ready(project_token: str) -> bool:
    """
    Fast check: has the bootstrap completed and canonical state been persisted?
    Uses local DB — NO NXDune call.
    """
    db = SessionLocal()
    try:
        record = db.query(models.ProjectCanonicalState.is_ready).filter(
            models.ProjectCanonicalState.project_token == project_token,
            models.ProjectCanonicalState.is_ready == True,
        ).first()
        return record is not None
    except Exception as e:
        logger.error(f"[LocalState] is_canonical_state_ready failed: {e}")
        return False
    finally:
        db.close()


def guard_bootstrap_regeneration(project_token: str) -> bool:
    """
    Returns True if canonical state is already persisted and agents MUST NOT regenerate it.
    Call this at the top of any code path that would re-generate the canonical tree or spec.

    Usage:
        if guard_bootstrap_regeneration(project_token):
            logger.info("Canonical state already persisted — skipping regeneration")
            return existing_state
    """
    return is_canonical_state_ready(project_token)


def get_canonical_context_for_task(
    project_token: str,
    task: Dict[str, Any],
    max_paths: int = 20,
) -> str:
    """
    Build a targeted canonical project context block for injection into agent prompts.
    Scoped to the paths most relevant to the task's domain — avoids bloating token count.

    Returns an empty string if canonical state is not ready (bootstrap not done).
    """
    state = get_canonical_state(project_token)
    if not state:
        return ""

    task_domain = str(task.get("domain") or task.get("task_domain") or "").lower().strip()
    task_title = str(task.get("title") or task.get("taskName") or "").lower()
    task_desc = str(task.get("description") or "").lower()

    domain_map: Dict[str, List[str]] = state.get("domain_file_map") or {}
    canonical_tree: str = state.get("canonical_tree") or ""
    tech_spec: str = state.get("technical_spec") or ""

    # Step 1: Find paths relevant to this task's domain
    relevant_paths: List[str] = []

    # Try exact domain match first
    if task_domain and task_domain in domain_map:
        relevant_paths.extend(domain_map[task_domain])

    # Fall back to keyword matching across all paths
    if not relevant_paths and canonical_tree:
        all_paths = _extract_all_paths_from_tree_text(canonical_tree)
        keywords = set(re.findall(r"[a-z]{4,}", task_title + " " + task_desc))
        scored = []
        for path in all_paths:
            score = sum(1 for kw in keywords if kw in path.lower())
            if task_domain and task_domain in path.lower():
                score += 5
            if score > 0:
                scored.append((score, path))
        scored.sort(key=lambda x: -x[0])
        relevant_paths = [p for _, p in scored[:max_paths]]

    # Step 2: Extract relevant tech spec sections
    spec_excerpt = ""
    if tech_spec:
        # Try to extract the section relevant to the task domain
        spec_excerpt = _extract_spec_section(tech_spec, task_domain, task_title, max_chars=1500)

    if not relevant_paths and not spec_excerpt:
        return ""

    lines = [
        "=" * 60,
        "CANONICAL PROJECT CONTEXT (from bootstrap — DO NOT DEVIATE)",
        "=" * 60,
        "",
    ]

    if relevant_paths:
        lines.append(f"FILES FOR YOUR TASK DOMAIN ({task_domain or 'general'}):")
        lines.append("Create/modify ONLY paths listed in the canonical tree. Do not invent new paths.")
        for p in relevant_paths[:max_paths]:
            lines.append(f"  • {p}")
        lines.append("")

    if spec_excerpt:
        lines.append("RELEVANT TECHNICAL SPECIFICATION:")
        lines.append(spec_excerpt)
        lines.append("")

    tech_stack = state.get("tech_stack") or {}
    if tech_stack:
        backend = tech_stack.get("backend") or tech_stack.get("backend_framework") or ""
        frontend = tech_stack.get("frontend") or tech_stack.get("frontend_framework") or ""
        stack_parts = []
        if backend:
            stack_parts.append(f"Backend: {backend}")
        if frontend:
            stack_parts.append(f"Frontend: {frontend}")
        if stack_parts:
            lines.append(f"TECH STACK: {' | '.join(stack_parts)}")
            lines.append("")

    lines.append("=" * 60)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Execution Checkpoints — resume after restart
# ---------------------------------------------------------------------------

def save_execution_checkpoint(
    project_token: str,
    agent_id: str,
    current_task_id: Optional[str],
    current_task_data: Optional[Dict[str, Any]],
    progress: int,
    progress_message: str,
    last_milestone: Optional[str] = None,
    files_written_so_far: Optional[List[str]] = None,
) -> None:
    """
    Save an execution checkpoint for an agent.
    Allows the agent to resume after server restart without re-querying NXDune.
    """
    db = SessionLocal()
    try:
        record = db.query(models.AgentExecutionCheckpoint).filter(
            models.AgentExecutionCheckpoint.project_token == project_token,
            models.AgentExecutionCheckpoint.agent_id == agent_id,
        ).first()

        safe_task_data = _safe_json(current_task_data) if current_task_data else None

        if record:
            record.current_task_id = current_task_id
            record.current_task_data = safe_task_data
            record.current_task_status = "in_progress" if current_task_id else None
            record.progress = progress
            record.progress_message = progress_message
            record.last_milestone = last_milestone
            record.files_written_so_far = files_written_so_far or []
            record.version = (record.version or 1) + 1
            record.updated_at = datetime.utcnow()
        else:
            record = models.AgentExecutionCheckpoint(
                project_token=project_token,
                agent_id=agent_id,
                current_task_id=current_task_id,
                current_task_data=safe_task_data,
                current_task_status="in_progress" if current_task_id else None,
                progress=progress,
                progress_message=progress_message,
                last_milestone=last_milestone,
                files_written_so_far=files_written_so_far or [],
            )
            db.add(record)

        db.commit()
    except Exception as e:
        db.rollback()
        logger.debug(f"[LocalState] save_execution_checkpoint failed (non-critical): {e}")
    finally:
        db.close()


def get_latest_checkpoint(project_token: str, agent_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve the latest execution checkpoint for an agent.
    Returns None if no checkpoint exists.
    """
    db = SessionLocal()
    try:
        record = db.query(models.AgentExecutionCheckpoint).filter(
            models.AgentExecutionCheckpoint.project_token == project_token,
            models.AgentExecutionCheckpoint.agent_id == agent_id,
        ).first()

        if not record:
            return None

        return {
            "current_task_id": record.current_task_id,
            "current_task_data": record.current_task_data,
            "current_task_status": record.current_task_status,
            "progress": record.progress,
            "progress_message": record.progress_message,
            "last_milestone": record.last_milestone,
            "files_written_so_far": record.files_written_so_far or [],
            "version": record.version,
        }
    except Exception as e:
        logger.error(f"[LocalState] get_latest_checkpoint failed: {e}")
        return None
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Assignment Restore — replaces fragile in-memory cache
# ---------------------------------------------------------------------------

def restore_agent_assignments_from_local_db(
    project_token: str,
    agent_ids: List[str],
) -> Dict[str, Dict[str, Any]]:
    """
    Restore persisted task assignments from local DB for all given agents.
    Returns {agent_id: task_data} for agents that have active tasks.

    Replaces: the 2-minute in-memory cache in _restore_persisted_agent_assignments()
    that was lost on server restart and caused "Skipping persisted assignment restore".
    """
    if not agent_ids:
        return {}

    db = SessionLocal()
    try:
        records = db.query(models.AgentTaskOwnership).filter(
            models.AgentTaskOwnership.project_token == project_token,
            models.AgentTaskOwnership.agent_id.in_(agent_ids),
            models.AgentTaskOwnership.status.in_(["claimed", "in_progress"]),
        ).order_by(models.AgentTaskOwnership.claimed_at.desc()).all()

        # One active task per agent (most recent)
        restored: Dict[str, Dict[str, Any]] = {}
        seen_agents: Set[str] = set()
        for record in records:
            if record.agent_id in seen_agents:
                continue
            seen_agents.add(record.agent_id)

            task_data = dict(record.task_data) if record.task_data else {}
            task_data["_local_status"] = record.status
            task_data["_local_branch"] = record.branch_name
            task_data["_local_task_id"] = record.task_id
            task_data["assigned_agent"] = record.agent_id
            restored[record.agent_id] = task_data

        if restored:
            logger.info(f"[LocalState] Restored {len(restored)} agent assignments from local DB for project {project_token}")
        return restored

    except Exception as e:
        logger.error(f"[LocalState] restore_agent_assignments_from_local_db failed: {e}")
        return {}
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Skill-Based Agent Governance Lane
# ---------------------------------------------------------------------------

def get_agent_lanes_from_skills(agent_id: str, skills_tags: Any, specialization: Optional[str] = None) -> Set[str]:
    """
    Determine which execution lanes an agent can work in based on their skills_tags.
    This handles the governance case: if an agent has governance-related skills,
    they are added to the "governance" lane. Agents are matched to tasks by skill,
    not by hard-coded type categories.

    Lanes:
        frontend, backend, qa, devops, governance, integration, general
    """
    lanes: Set[str] = {"general"}

    tags: List[str] = []
    if isinstance(skills_tags, list):
        tags = [str(t).lower() for t in skills_tags if t]
    elif isinstance(skills_tags, str):
        try:
            parsed = json.loads(skills_tags)
            if isinstance(parsed, list):
                tags = [str(t).lower() for t in parsed if t]
        except Exception:
            # Plain string — treat as comma-separated tags
            tags = [t.strip().lower() for t in skills_tags.split(",") if t.strip()]

    # Frontend lane
    _FE_TAGS = {"frontend", "react", "vue", "angular", "ui", "ux", "web", "component",
                "vite", "tailwind", "css", "html", "javascript", "typescript", "jsx", "tsx",
                "next", "nextjs", "svelte"}
    if any(t in _FE_TAGS for t in tags):
        lanes.add("frontend")

    # Backend lane
    _BE_TAGS = {"backend", "api", "server", "python", "node", "express", "fastapi",
                "django", "flask", "java", "spring", "dotnet", "csharp", "go", "rust",
                "database", "sql", "sqlite", "postgres", "mysql", "mongodb", "redis",
                "graphql", "rest", "grpc", "microservice"}
    if any(t in _BE_TAGS for t in tags):
        lanes.add("backend")

    # QA lane
    _QA_TAGS = {"qa", "test", "testing", "quality", "validator", "validation",
                "pytest", "jest", "vitest", "cypress", "selenium", "playwright",
                "unit", "integration", "e2e", "automation"}
    if any(t in _QA_TAGS for t in tags):
        lanes.add("qa")

    # DevOps lane
    _DO_TAGS = {"devops", "infra", "infrastructure", "deploy", "deployment", "release",
                "ops", "docker", "kubernetes", "ci", "cd", "terraform", "ansible",
                "aws", "gcp", "azure", "monitoring", "observability"}
    if any(t in _DO_TAGS for t in tags):
        lanes.add("devops")

    # Governance lane (new — skill-based, not type-based)
    _GOV_TAGS = {"governance", "compliance", "risk", "audit", "policy", "regulation",
                 "security", "privacy", "gdpr", "hipaa", "sox", "review", "assessment",
                 "brd", "requirements", "business", "stakeholder", "analysis"}
    if any(t in _GOV_TAGS for t in tags):
        lanes.add("governance")

    # Integration lane
    _INT_TAGS = {"integration", "fullstack", "full-stack", "shared", "orchestration"}
    if any(t in _INT_TAGS for t in tags):
        lanes.add("integration")

    # Fall back to specialization field if no tags matched
    if len(lanes) == 1 and specialization:
        spec = specialization.lower().strip()
        _SPEC_MAP = {
            "frontend": "frontend",
            "backend": "backend",
            "testing": "qa", "qa": "qa", "quality": "qa",
            "devops": "devops", "operations": "devops",
            "governance": "governance", "compliance": "governance",
            "integration": "integration",
        }
        mapped = _SPEC_MAP.get(spec)
        if mapped:
            lanes.add(mapped)

    return lanes


def is_task_in_agent_lanes(task_lane: str, agent_lanes: Set[str]) -> bool:
    """
    Returns True if the agent is allowed to work on a task of the given lane.
    "general" lane is always allowed for unspecialized tasks.
    """
    if not task_lane or task_lane == "general":
        return True  # Any agent can handle general tasks
    if "general" in agent_lanes and len(agent_lanes) == 1:
        return True  # Unspecialized agent — allow all tasks
    return task_lane in agent_lanes


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _safe_json(obj: Any) -> Any:
    """Serialize an object to a JSON-safe form (handles datetime, sets, etc.)."""
    if obj is None:
        return None
    try:
        json.dumps(obj)
        return obj
    except (TypeError, ValueError):
        pass
    # Convert non-serializable types
    if isinstance(obj, dict):
        return {k: _safe_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_safe_json(v) for v in obj]
    if isinstance(obj, set):
        return list(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    return str(obj)


def _build_domain_file_map(canonical_tree_json: str) -> Dict[str, List[str]]:
    """
    Parse the canonical tree JSON and build a {domain: [paths]} map.
    Domains are inferred from top-level folder names (auth, booking, frontend, backend, etc.).
    """
    if not canonical_tree_json:
        return {}

    try:
        tree = json.loads(canonical_tree_json)
    except Exception:
        return {}

    domain_map: Dict[str, List[str]] = {}

    def walk(node: Any, current_path: str, root_domain: Optional[str]) -> None:
        if not isinstance(node, dict):
            return
        name = node.get("name", "")
        path = f"{current_path}/{name}".lstrip("/") if current_path else name
        children = node.get("children") or []

        # Top-level folders become domain keys
        domain = root_domain
        if not current_path and name not in ("project", "root", "app", "project_root"):
            domain = name.lower()

        if not children:
            # Leaf node = file
            if domain:
                domain_map.setdefault(domain, []).append(path)
        else:
            for child in children:
                walk(child, path, domain)

    # Walk root children
    root_children = tree.get("children") or []
    for child in root_children:
        walk(child, "", None)

    return domain_map


def _extract_all_paths_from_tree_text(canonical_tree: str) -> List[str]:
    """Extract all file paths from a canonical tree JSON string."""
    try:
        tree = json.loads(canonical_tree)
    except Exception:
        return []

    paths: List[str] = []

    def walk(node: Any, prefix: str) -> None:
        if not isinstance(node, dict):
            return
        name = node.get("name", "")
        path = f"{prefix}/{name}".lstrip("/") if prefix else name
        children = node.get("children") or []
        if not children:
            paths.append(path)
        else:
            for child in children:
                walk(child, path)

    for child in (tree.get("children") or []):
        walk(child, "")

    return paths


def _extract_spec_section(tech_spec: str, domain: str, task_title: str, max_chars: int = 1500) -> str:
    """
    Extract the most relevant section of the technical spec for a given domain/task.
    Looks for headings containing the domain name or task keywords.
    Falls back to the first max_chars if no specific section is found.
    """
    if not tech_spec:
        return ""

    if not domain and not task_title:
        return tech_spec[:max_chars]

    lines = tech_spec.split("\n")
    keywords = set(re.findall(r"[a-z]{4,}", (domain + " " + task_title).lower()))

    # Find the most relevant heading
    best_start = -1
    best_score = 0
    for i, line in enumerate(lines):
        if line.startswith("#"):
            score = sum(1 for kw in keywords if kw in line.lower())
            if score > best_score:
                best_score = score
                best_start = i

    if best_start == -1:
        return tech_spec[:max_chars]

    # Extract section from best_start to next heading of same or higher level
    heading_level = len(lines[best_start]) - len(lines[best_start].lstrip("#"))
    section_lines = [lines[best_start]]
    for i in range(best_start + 1, len(lines)):
        line = lines[i]
        if line.startswith("#"):
            level = len(line) - len(line.lstrip("#"))
            if level <= heading_level:
                break
        section_lines.append(line)

    section = "\n".join(section_lines)
    return section[:max_chars]
