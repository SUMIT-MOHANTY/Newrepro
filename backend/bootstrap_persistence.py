"""
Bootstrap State Persistence - Replaces in-memory _bootstrap_pushed flag
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


def set_bootstrap_success(project_token: str, master_note_id: Optional[str] = None, workspace_tree: Optional[str] = None, bootstrap_branch: Optional[str] = None):
    """Mark bootstrap as successful and persist the bootstrap branch name"""
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
            record.workspace_tree = workspace_tree
            if bootstrap_branch:
                record.bootstrap_branch = bootstrap_branch
        
        db.commit()
        logger.info(f"Bootstrap marked as SUCCESS for project {project_token} (branch: {bootstrap_branch})")
    finally:
        db.close()


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
    """Check if bootstrap has been successfully pushed (replaces _bootstrap_pushed dict)"""
    state = get_bootstrap_state(project_token)
    return state.get("pushed", False)


def get_bootstrap_branch(project_token: str) -> Optional[str]:
    """Get the persisted bootstrap branch name from DB.
    Returns the branch name where bootstrap scaffold was pushed, or None."""
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
