"""
Reset Task Progress Script
Usage: python reset_task_progress.py <project_token>
Resets all tasks' progress to 0, status to "To Do" / "pending",
and clears bootstrap state so agents can re-run from scratch.

This is safe to run multiple times (idempotent).
"""
import sys
import json
from datetime import datetime

from database import SessionLocal
import models
from models_bootstrap_state import BootstrapState

import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def reset_task_progress(project_token: str) -> dict:
    """Reset all task progress and status for the given project_token."""
    results = {
        "tasks_reset": 0,
        "ownerships_reset": 0,
        "bootstrap_reset": 0,
        "canonical_reset": 0,
    }
    
    db = SessionLocal()
    try:
        # ── 1. Reset AgentTaskOwnership records ──────────────────────────────
        ownerships = db.query(models.AgentTaskOwnership).filter(
            models.AgentTaskOwnership.project_token == project_token
        ).all()
        
        for ow in ownerships:
            ow.status = "pending"
            ow.completed_at = None
            ow.error_message = None
            
            # Reset task_data JSON to have progress=0 and status="To Do"
            task_data = dict(ow.task_data) if ow.task_data else {}
            task_data["task_progress"] = 0
            task_data["taskStatus"] = "To Do"
            ow.task_data = task_data
            ow.updated_at = datetime.utcnow()
            
            results["ownerships_reset"] += 1
        
        db.flush()
        logger.info(f"Reset {results['ownerships_reset']} AgentTaskOwnership records")
        
        # ── 2. Reset Task records (selected flag for re-selection) ───────────
        tasks = db.query(models.Task).filter(
            models.Task.project_token == project_token
        ).all()
        
        for task in tasks:
            task.selected = False
            task.synced_to_nxdune = False
            results["tasks_reset"] += 1
        
        db.flush()
        logger.info(f"Reset {results['tasks_reset']} Task records")
        
        # ── 3. Reset BootstrapState ──────────────────────────────────────────
        bootstrap = db.query(BootstrapState).filter(
            BootstrapState.project_token == project_token
        ).first()
        
        if bootstrap:
            bootstrap.status = "pending"
            bootstrap.bootstrap_branch = None
            bootstrap.completed_at = None
            bootstrap.error_message = None
            bootstrap.workspace_tree = None
            bootstrap.master_note_id = None
            results["bootstrap_reset"] = 1
            logger.info("Reset BootstrapState record")
        else:
            logger.info("No BootstrapState record found (nothing to reset)")
        
        # ── 4. Reset ProjectCanonicalState ──────────────────────────────────
        try:
            from local_state_manager import save_canonical_state
            # Write a reset state: is_ready = False, bootstrap_branch = None
            from local_state_manager import get_canonical_state
            existing = get_canonical_state(project_token)
            if existing:
                # Force reset canonical state
                save_canonical_state(
                    project_token=project_token,
                    canonical_tree=None,
                    technical_spec=None,
                    tech_stack=None,
                    bootstrap_branch=None,
                    agent_id="reset_script",
                    force_reset=True,
                )
                results["canonical_reset"] = 1
                logger.info("Reset ProjectCanonicalState")
        except Exception as e:
            logger.warning(f"Could not reset canonical state (non-fatal): {e}")
        
        # ── Commit all changes ──────────────────────────────────────────────
        db.commit()
        logger.info("All changes committed successfully")
        
    except Exception as e:
        db.rollback()
        logger.error(f"Reset failed, rolled back: {e}")
        raise
    finally:
        db.close()
    
    return results


def main():
    if len(sys.argv) < 2:
        print("Usage: python reset_task_progress.py <project_token>")
        print("")
        print("Example: python reset_task_progress.py 4847e1")
        sys.exit(1)
    
    project_token = sys.argv[1].strip()
    
    print(f"\n🔁 Resetting all task progress for project: {project_token}")
    print("=" * 50)
    
    confirm = input("Are you sure? This will reset all tasks to pending status. (yes/no): ")
    if confirm.lower() not in ("yes", "y"):
        print("Aborted.")
        sys.exit(0)
    
    results = reset_task_progress(project_token)
    
    print(f"\n✅ Reset complete!")
    print(f"   Tasks reset:          {results['tasks_reset']}")
    print(f"   Ownerships reset:     {results['ownerships_reset']}")
    print(f"   Bootstrap reset:      {results['bootstrap_reset']}")
    print(f"   Canonical state reset: {results['canonical_reset']}")
    print(f"\nAll tasks are now back to 'To Do' status with 0% progress.")
    print(f"You can now dispatch agents again to re-run from scratch.")


if __name__ == "__main__":
    main()
