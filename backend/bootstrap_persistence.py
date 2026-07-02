"""
Bootstrap State Persistence - Replaces in-memory _bootstrap_pushed flag
Extended with:
- ProjectCanonicalState integration (local-first authoritative check)
- Removal of fragile AgentMessage heuristic
- guard_canonical_regeneration() for master agent immutability enforcement
- get_immutable_canonical_artifacts() for agent prompt injection
- save_bootstrap_canonical_artifacts() bridge for bootstrap completion
"""
from datetime import datetime
from typing import Optional, Dict, Any
from database import SessionLocal
from models_bootstrap_state import BootstrapState
import logging

logger = logging.getLogger(__name__)


def get_bootstrap_state(project_token: str) -> Dict[str, Any]:
    """Get bootstrap state from database"""
    db = SessionLocal()
    try:
        record = db.query(BootstrapState).filter(
            BootstrapState.project_token == project_token
        ).first()

        if not record:
            return {"status": "pending", "pushed": False, "bootstrap_branch": None}

        return {
            "status": record.status,
            "pushed": record.status == "success",
            "error": record.error_message,
            "bootstrap_branch": record.bootstrap_branch,
            "workspace_tree": record.workspace_tree,
            "started_at": record.started_at.isoformat() if record.started_at else None,
            "completed_at": record.completed_at.isoformat() if record.completed_at else None,
        }
    finally:
        db.close()


def set_bootstrap_running(project_token: str):
    """Mark bootstrap as running"""
    db = SessionLocal()
    try:
        record = db.query(BootstrapState).filter(
            BootstrapState.project_token == project_token
        ).first()

        if not record:
            record = BootstrapState(
                project_token=project_token,
                status="running",
                started_at=datetime.utcnow()
            )
            db.add(record)
        else:
            record.status = "running"
            record.started_at = datetime.utcnow()

        db.commit()
        logger.info(f"Bootstrap marked as running for project {project_token}")
    finally:
        db.close()


def save_bootstrap_planning_note(
    project_token: str,
    master_note_id: Optional[str] = None,
    workspace_tree: Optional[str] = None,
):
    """Save the master note ID and workspace tree when the planning note is published,
    and persist the tree to ProjectCanonicalState (so it is not regenerated),
    but do NOT mark the bootstrap execution status as success (status stays pending/running).
    """
    db = SessionLocal()
    try:
        record = db.query(BootstrapState).filter(
            BootstrapState.project_token == project_token
        ).first()

        if not record:
            record = BootstrapState(
                project_token=project_token,
                status="pending",
                started_at=datetime.utcnow(),
                master_note_id=master_note_id,
                workspace_tree=workspace_tree,
            )
            db.add(record)
        else:
            record.master_note_id = master_note_id
            if workspace_tree:
                record.workspace_tree = workspace_tree

        db.commit()
        logger.info(f"Bootstrap planning note saved for project {project_token} (status: {record.status})")
    finally:
        db.close()

    # Save to ProjectCanonicalState so the tree is cached and guard_canonical_regeneration passes,
    # but leave bootstrap_branch=None so is_bootstrap_pushed continues to return False.
    if workspace_tree:
        try:
            from local_state_manager import save_canonical_state
            save_canonical_state(
                project_token=project_token,
                canonical_tree=workspace_tree,
                bootstrap_branch=None,  # Leave None so bootstrap is not considered pushed yet
                agent_id="master_agent",
            )
        except Exception as e:
            logger.warning(f"Failed to write planning artifacts to ProjectCanonicalState: {e}")


def set_bootstrap_success(
    project_token: str,
    master_note_id: Optional[str] = None,
    workspace_tree: Optional[str] = None,
    bootstrap_branch: Optional[str] = None,
):
    """Mark bootstrap as successful and persist the bootstrap branch name.
    Also writes through to ProjectCanonicalState for local-first authority.
    """
    db = SessionLocal()
    try:
        record = db.query(BootstrapState).filter(
            BootstrapState.project_token == project_token
        ).first()

        if not record:
            record = BootstrapState(
                project_token=project_token,
                status="success",
                started_at=datetime.utcnow(),
                completed_at=datetime.utcnow(),
                master_note_id=master_note_id,
                workspace_tree=workspace_tree,
                bootstrap_branch=bootstrap_branch,
            )
            db.add(record)
        else:
            record.status = "success"
            record.completed_at = datetime.utcnow()
            record.master_note_id = master_note_id
            if workspace_tree:
                record.workspace_tree = workspace_tree
            if bootstrap_branch:
                record.bootstrap_branch = bootstrap_branch

        db.commit()
        logger.info(f"Bootstrap marked as SUCCESS for project {project_token} (branch: {bootstrap_branch})")
    finally:
        db.close()

    # Write-through to ProjectCanonicalState so future is_bootstrap_pushed checks
    # use the local-first canonical state (Priority 1) without hitting NXDune.
    if workspace_tree or bootstrap_branch:
        try:
            from local_state_manager import save_canonical_state
            save_canonical_state(
                project_token=project_token,
                canonical_tree=workspace_tree,
                bootstrap_branch=bootstrap_branch or "main",
                agent_id="bootstrap",
            )
        except Exception as e:
            logger.warning(f"Failed to write bootstrap artifacts to ProjectCanonicalState: {e}")


def set_bootstrap_failed(project_token: str, error_message: str):
    """Mark bootstrap as failed"""
    db = SessionLocal()
    try:
        record = db.query(BootstrapState).filter(
            BootstrapState.project_token == project_token
        ).first()

        if not record:
            record = BootstrapState(
                project_token=project_token,
                status="failed",
                started_at=datetime.utcnow(),
                completed_at=datetime.utcnow(),
                error_message=error_message
            )
            db.add(record)
        else:
            record.status = "failed"
            record.completed_at = datetime.utcnow()
            record.error_message = error_message

        db.commit()
        logger.error(f"Bootstrap marked as FAILED for project {project_token}: {error_message}")
    finally:
        db.close()


def is_bootstrap_pushed(project_token: str) -> bool:
    """
    Check if bootstrap has been successfully pushed.

    Priority order (local-first, no NXDune dependency):
    0. Brownfield/Migration projects are implicitly pushed (no bootstrap task)
    1. ProjectCanonicalState.is_ready and bootstrap_branch is not None — most authoritative, written atomically at bootstrap completion
    """
    # ── Priority 0: Auto-pushed for Brownfield / Migration ──────────────────
    try:
        from database import SessionLocal
        import models
        db_session = SessionLocal()
        try:
            gov = db_session.query(models.GovernanceResponse).filter(
                models.GovernanceResponse.project_token == project_token
            ).first()
            if gov and gov.project_type:
                from brownfield_agent_service import is_brownfield_project
                if is_brownfield_project(gov.project_type):
                    return True
        finally:
            db_session.close()
    except Exception as pt_err:
        logger.warning(f"Failed to check project type in is_bootstrap_pushed: {pt_err}")

    # ── Priority 1: ProjectCanonicalState (local-first, most authoritative) ─
    try:
        from local_state_manager import get_canonical_state
        cs = get_canonical_state(project_token)
        if cs and cs.get("bootstrap_branch") is not None:
            return True
    except Exception as e:
        logger.warning(f"get_canonical_state check failed: {e}")

    # ── Priority 2: BootstrapState table (legacy, still written) ────────────
    state = get_bootstrap_state(project_token)
    if state.get("pushed", False) and state.get("bootstrap_branch") is not None:
        # Write-through so future calls hit Priority 1 (faster path)
        try:
            from local_state_manager import save_canonical_state
            save_canonical_state(
                project_token=project_token,
                canonical_tree=state.get("workspace_tree"),
                bootstrap_branch=state.get("bootstrap_branch"),
                agent_id="bootstrap_recovery",
            )
        except Exception:
            pass
        return True

    # ── Priority 3: Task table (recovery for pre-migration data) ────────────
    db = SessionLocal()
    try:
        import models
        db_task = db.query(models.Task).filter(
            models.Task.project_token == project_token,
            models.Task.task_id == "TASK-00",
            models.Task.synced_to_nxdune == True,
        ).first()

        if db_task:
            set_bootstrap_success(project_token, bootstrap_branch="main")
            logger.info(
                f"Auto-healed bootstrap state for project {project_token} "
                f"(detected synced TASK-00 in local Task table)"
            )
            return True

    except Exception as e:
        logger.warning(f"Error in is_bootstrap_pushed Task recovery: {e}")
    finally:
        db.close()

    return False


def get_bootstrap_branch(project_token: str) -> Optional[str]:
    """Get the persisted bootstrap branch name.
    Checks canonical state first (local-first), falls back to BootstrapState."""
    try:
        from local_state_manager import get_canonical_state
        cs = get_canonical_state(project_token)
        if cs and cs.get("bootstrap_branch"):
            return cs["bootstrap_branch"]
    except Exception:
        pass

    state = get_bootstrap_state(project_token)
    return state.get("bootstrap_branch")


def set_bootstrap_branch(project_token: str, branch_name: str):
    """Persist the bootstrap branch name in the DB."""
    db = SessionLocal()
    try:
        record = db.query(BootstrapState).filter(
            BootstrapState.project_token == project_token
        ).first()

        if not record:
            record = BootstrapState(
                project_token=project_token,
                status="pending",
                bootstrap_branch=branch_name,
            )
            db.add(record)
        else:
            record.bootstrap_branch = branch_name

        db.commit()
        logger.info(f"Bootstrap branch persisted: {branch_name} for project {project_token}")
    finally:
        db.close()


# ── NEW: Canonical Regeneration Guard ─────────────────────────────────────────

def guard_canonical_regeneration(project_token: str) -> bool:
    """
    Returns True if the canonical project tree and technical spec are already persisted
    and the master agent MUST NOT regenerate them.

    Call this at the top of any code path that would re-generate the canonical tree or spec.

    Usage in master agent:
        if guard_canonical_regeneration(project_token):
            logger.info("Canonical state already persisted — skipping regeneration")
            return get_immutable_canonical_artifacts(project_token)

    This is the primary fix for the repeated canonical-tree/spec regeneration bug.
    Every time the master agent restarts, it would re-run expensive LLM tree-generation
    calls even though the output was already persisted. This guard prevents that.
    """
    try:
        from local_state_manager import is_canonical_state_ready
        return is_canonical_state_ready(project_token)
    except Exception as e:
        logger.warning(f"guard_canonical_regeneration check failed: {e}")
        # Fallback to BootstrapState
        state = get_bootstrap_state(project_token)
        return state.get("pushed", False)


def get_immutable_canonical_artifacts(project_token: str) -> Dict[str, Any]:
    """
    Return the immutable bootstrap artifacts (canonical tree, tech spec, tech stack).
    Reads from ProjectCanonicalState — the local-first authoritative store.

    Returns {} if canonical state is not ready (bootstrap has not completed yet).
    All master agent code paths should call this instead of re-generating tree/spec.
    """
    try:
        from local_state_manager import get_canonical_state
        state = get_canonical_state(project_token)
        return state or {}
    except Exception as e:
        logger.warning(f"get_immutable_canonical_artifacts failed: {e}")
        return {}


def save_bootstrap_canonical_artifacts(
    project_token: str,
    canonical_tree: Optional[str] = None,
    technical_spec: Optional[str] = None,
    tech_stack: Optional[Dict[str, Any]] = None,
    bootstrap_branch: Optional[str] = None,
    agent_id: Optional[str] = None,
) -> bool:
    """
    Bridge function: called by the bootstrap agent when it successfully completes.

    Atomically persists all canonical artifacts to ProjectCanonicalState (immutable)
    AND marks BootstrapState as success for legacy compatibility.

    After this call:
    - guard_canonical_regeneration() returns True → master agent skips regeneration
    - is_bootstrap_pushed() returns True → worker agents start picking tasks
    - get_immutable_canonical_artifacts() returns the stored tree/spec/stack

    This replaces the pattern: set_bootstrap_success() + separately managing workspace_tree
    """
    # 1. Persist to canonical state (primary, immutable local store)
    saved = False
    try:
        from local_state_manager import save_canonical_state
        saved = save_canonical_state(
            project_token=project_token,
            canonical_tree=canonical_tree,
            technical_spec=technical_spec,
            tech_stack=tech_stack,
            bootstrap_branch=bootstrap_branch,
            agent_id=agent_id,
        )
        if saved:
            logger.info(f"[Bootstrap] ✅ Canonical artifacts saved to local-first store for {project_token}")
        else:
            logger.info(f"[Bootstrap] Canonical artifacts already persisted for {project_token} (immutable, no-op)")
    except Exception as e:
        logger.error(f"save_bootstrap_canonical_artifacts: canonical save failed: {e}")

    # 2. Mark BootstrapState success (legacy compatibility — always write regardless of canonical save result)
    set_bootstrap_success(
        project_token=project_token,
        workspace_tree=canonical_tree,
        bootstrap_branch=bootstrap_branch,
    )

    return saved
