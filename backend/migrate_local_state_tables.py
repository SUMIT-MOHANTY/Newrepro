"""
Migration: Create Local-First State Management Tables
=====================================================
Creates: agent_task_ownerships, project_canonical_states,
         agent_execution_checkpoints, nxdune_sync_logs

Backfills:
- AgentTaskOwnership from existing ProjectRuntimeState.agent_states JSON
- ProjectCanonicalState from existing BootstrapState.workspace_tree

Safe to run multiple times (idempotent).
Run with: python migrate_local_state_tables.py
"""

import json
import logging
import sys
import os

# Ensure backend package is on path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("migrate_local_state_tables")


def run_migration():
    logger.info("=" * 60)
    logger.info("Local-First State Management Migration")
    logger.info("=" * 60)

    # ── Step 1: Create tables ──────────────────────────────────────
    logger.info("Step 1: Creating new tables...")
    try:
        from database import Base, engine
        import models  # noqa — registers all models via SQLAlchemy
        import models_bootstrap_state  # noqa

        Base.metadata.create_all(bind=engine, checkfirst=True)
        logger.info("  ✅ Tables created (or already exist)")
    except Exception as e:
        logger.error(f"  ❌ Failed to create tables: {e}")
        return False

    # ── Step 2: Backfill AgentTaskOwnership from ProjectRuntimeState ──
    logger.info("Step 2: Backfilling AgentTaskOwnership from ProjectRuntimeState...")
    try:
        from database import SessionLocal
        db = SessionLocal()

        runtime_states = db.query(models.ProjectRuntimeState).all()
        backfill_count = 0

        for state in runtime_states:
            project_token = state.project_token
            agent_states_raw = state.agent_states or {}

            if not isinstance(agent_states_raw, dict):
                try:
                    agent_states_raw = json.loads(agent_states_raw)
                except Exception:
                    continue

            for agent_id, agent_data in agent_states_raw.items():
                if not isinstance(agent_data, dict):
                    continue

                current_task = agent_data.get("current_task")
                if not isinstance(current_task, dict):
                    continue

                task_id = (
                    current_task.get("task_id")
                    or current_task.get("external_task_id")
                    or current_task.get("id")
                    or ""
                )
                if not task_id:
                    continue

                task_id = str(task_id).strip().upper()
                agent_status = str(agent_data.get("status") or "").lower()

                # Determine local status
                if agent_status in ("done", "completed"):
                    local_status = "done"
                elif agent_status in ("running", "working", "in_progress"):
                    local_status = "in_progress"
                else:
                    local_status = "claimed"

                # Check if already exists
                existing = db.query(models.AgentTaskOwnership).filter(
                    models.AgentTaskOwnership.project_token == project_token,
                    models.AgentTaskOwnership.task_id == task_id,
                ).first()

                if existing:
                    logger.debug(f"  Skipping {task_id} (already exists)")
                    continue

                title = str(current_task.get("title") or current_task.get("taskName") or "")[:500]
                record = models.AgentTaskOwnership(
                    project_token=project_token,
                    task_id=task_id,
                    agent_id=agent_id,
                    task_title=title,
                    task_data=_safe_json(current_task),
                    status=local_status,
                )
                db.add(record)
                backfill_count += 1

        db.commit()
        db.close()
        logger.info(f"  ✅ Backfilled {backfill_count} agent task ownership records")

    except Exception as e:
        logger.warning(f"  ⚠️ Backfill from ProjectRuntimeState failed (non-critical): {e}")

    # ── Step 3: Backfill ProjectCanonicalState from BootstrapState ──
    logger.info("Step 3: Backfilling ProjectCanonicalState from BootstrapState...")
    try:
        from database import SessionLocal
        db = SessionLocal()

        from models_bootstrap_state import BootstrapState
        bootstrap_states = db.query(BootstrapState).filter(
            BootstrapState.status == "success"
        ).all()

        backfill_canonical = 0
        for bs in bootstrap_states:
            project_token = bs.project_token
            workspace_tree = bs.workspace_tree

            existing = db.query(models.ProjectCanonicalState).filter(
                models.ProjectCanonicalState.project_token == project_token
            ).first()

            if existing:
                logger.debug(f"  Skipping canonical state for {project_token} (already exists)")
                continue

            record = models.ProjectCanonicalState(
                project_token=project_token,
                canonical_tree=workspace_tree,
                bootstrap_branch=bs.bootstrap_branch,
                is_ready=True,
            )
            db.add(record)
            backfill_canonical += 1

        db.commit()
        db.close()
        logger.info(f"  ✅ Backfilled {backfill_canonical} canonical state records from BootstrapState")

    except Exception as e:
        logger.warning(f"  ⚠️ Backfill from BootstrapState failed (non-critical): {e}")

    # ── Step 4: Cross-check BootstrapState with Task table ────────
    logger.info("Step 4: Cross-checking bootstrap task completion in Task table...")
    try:
        from database import SessionLocal
        db = SessionLocal()

        # Find all projects that have a TASK-00 marked as synced_to_nxdune=True
        bootstrap_tasks = db.query(models.Task).filter(
            models.Task.task_id == "TASK-00",
            models.Task.synced_to_nxdune == True,
        ).all()

        healed_count = 0
        for bt in bootstrap_tasks:
            project_token = bt.project_token

            # Ensure canonical state exists
            existing = db.query(models.ProjectCanonicalState).filter(
                models.ProjectCanonicalState.project_token == project_token
            ).first()

            if not existing:
                record = models.ProjectCanonicalState(
                    project_token=project_token,
                    is_ready=True,
                    bootstrap_branch="main",
                )
                db.add(record)
                healed_count += 1

        db.commit()
        db.close()
        logger.info(f"  ✅ Healed {healed_count} canonical state records from Task table")

    except Exception as e:
        logger.warning(f"  ⚠️ Task table cross-check failed (non-critical): {e}")

    logger.info("=" * 60)
    logger.info("Migration completed successfully!")
    logger.info("=" * 60)
    return True


def _safe_json(obj):
    """Make an object JSON-serializable."""
    if obj is None:
        return None
    try:
        json.dumps(obj)
        return obj
    except (TypeError, ValueError):
        pass
    if isinstance(obj, dict):
        return {k: _safe_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_safe_json(v) for v in obj]
    if isinstance(obj, set):
        return list(obj)
    return str(obj)


if __name__ == "__main__":
    success = run_migration()
    sys.exit(0 if success else 1)
