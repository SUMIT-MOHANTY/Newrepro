"""
Coordination State Persistence — Phase 4
=========================================

Persists the agent coordination state (sync points, phase gates, agent statuses,
file locks, task DAG) so it survives server restarts.

Integrates with:
  - synchronized_langgraph_workflow.py (Phase 1)
  - agent_coordination_service.py (Phase 1)
  - agent_service.py (_ensure_project_state)
  - task_generation_service.py (Task DAG)

Usage:
    from coordination_persistence import CoordinationPersistence
    cp = CoordinationPersistence(project_token)
    await cp.save_coordination_state(state)
    state = await cp.load_coordination_state()
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from database import SessionLocal, engine
from sqlalchemy import text, inspect

logger = logging.getLogger(__name__)

TABLE_NAME = "coordination_states"


# ── Schema Management ────────────────────────────────────────────────────────

def ensure_table() -> bool:
    """Ensure the coordination_states table exists."""
    try:
        inspector = inspect(engine)
        if TABLE_NAME in inspector.get_table_names():
            return True
        with engine.connect() as conn:
            conn.execute(text(f"""
                CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_token VARCHAR NOT NULL UNIQUE,
                    current_phase VARCHAR NOT NULL DEFAULT 'planning',
                    phase_gates JSON DEFAULT '{{}}',
                    sync_points JSON DEFAULT '[]',
                    agent_statuses JSON DEFAULT '{{}}',
                    agent_assignments JSON DEFAULT '{{}}',
                    file_locks JSON DEFAULT '{{}}',
                    task_dag JSON DEFAULT '{{}}',
                    communication_log JSON DEFAULT '[]',
                    shared_context JSON DEFAULT '{{}}',
                    version INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            conn.commit()
        logger.info(f"[CoordPersistence] Table '{TABLE_NAME}' created")
        return True
    except Exception as e:
        logger.error(f"[CoordPersistence] Failed to create table: {e}")
        return False


# ── Save / Load / Clear ──────────────────────────────────────────────────────

def _serialize(obj: Any) -> Any:
    """Serialize an object to a JSON-safe form."""
    if isinstance(obj, set):
        return list(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    return obj


def save_coordination_state(
    project_token: str,
    current_phase: str = "planning",
    phase_gates: Optional[Dict[str, bool]] = None,
    sync_points: Optional[List[Dict[str, Any]]] = None,
    agent_statuses: Optional[Dict[str, str]] = None,
    agent_assignments: Optional[Dict[str, str]] = None,
    file_locks: Optional[Dict[str, Any]] = None,
    task_dag: Optional[Dict[str, List[str]]] = None,
    communication_log: Optional[List[Dict[str, Any]]] = None,
    shared_context: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Save or update coordination state for a project.

    This is called:
    - After every significant state change in Phase 1 coordination
    - When sync points complete
    - When phase gates pass
    - When agent statuses change
    - After task DAG is built (Phase 2)
    """
    ensure_table()
    db = SessionLocal()
    try:
        # Check if record exists
        existing = db.execute(
            text(f"SELECT id FROM {TABLE_NAME} WHERE project_token = :pt"),
            {"pt": project_token},
        ).fetchone()

        serialized = {
            "current_phase": current_phase,
            "phase_gates": json.dumps(_serialize(phase_gates or {})),
            "sync_points": json.dumps(_serialize(sync_points or [])),
            "agent_statuses": json.dumps(_serialize(agent_statuses or {})),
            "agent_assignments": json.dumps(_serialize(agent_assignments or {})),
            "file_locks": json.dumps(_serialize(file_locks or {})),
            "task_dag": json.dumps(_serialize(task_dag or {})),
            "communication_log": json.dumps(_serialize(communication_log or [])),
            "shared_context": json.dumps(_serialize(shared_context or {})),
        }

        if existing:
            db.execute(
                text(f"""
                    UPDATE {TABLE_NAME} SET
                        current_phase = :current_phase,
                        phase_gates = :phase_gates,
                        sync_points = :sync_points,
                        agent_statuses = :agent_statuses,
                        agent_assignments = :agent_assignments,
                        file_locks = :file_locks,
                        task_dag = :task_dag,
                        communication_log = :communication_log,
                        shared_context = :shared_context,
                        version = version + 1,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE project_token = :pt
                """),
                {"pt": project_token, **serialized},
            )
        else:
            db.execute(
                text(f"""
                    INSERT INTO {TABLE_NAME} (
                        project_token, current_phase, phase_gates, sync_points,
                        agent_statuses, agent_assignments, file_locks, task_dag,
                        communication_log, shared_context
                    ) VALUES (
                        :pt, :current_phase, :phase_gates, :sync_points,
                        :agent_statuses, :agent_assignments, :file_locks, :task_dag,
                        :communication_log, :shared_context
                    )
                """),
                {"pt": project_token, **serialized},
            )

        db.commit()
        return True

    except Exception as e:
        db.rollback()
        logger.error(f"[CoordPersistence] Save failed for {project_token}: {e}")
        return False
    finally:
        db.close()


def load_coordination_state(project_token: str) -> Optional[Dict[str, Any]]:
    """
    Load coordination state from the database.

    Returns None if no state exists for this project.
    Called on server startup / first use to restore state.
    """
    ensure_table()
    db = SessionLocal()
    try:
        row = db.execute(
            text(f"""
                SELECT current_phase, phase_gates, sync_points, agent_statuses,
                       agent_assignments, file_locks, task_dag, communication_log,
                       shared_context, version
                FROM {TABLE_NAME}
                WHERE project_token = :pt
            """),
            {"pt": project_token},
        ).fetchone()

        if not row:
            return None

        return {
            "current_phase": row[0],
            "phase_gates": json.loads(row[1]) if row[1] else {},
            "sync_points": json.loads(row[2]) if row[2] else [],
            "agent_statuses": json.loads(row[3]) if row[3] else {},
            "agent_assignments": json.loads(row[4]) if row[4] else {},
            "file_locks": json.loads(row[5]) if row[5] else {},
            "task_dag": json.loads(row[6]) if row[6] else {},
            "communication_log": json.loads(row[7]) if row[7] else [],
            "shared_context": json.loads(row[8]) if row[8] else {},
            "version": row[9],
        }

    except Exception as e:
        logger.error(f"[CoordPersistence] Load failed for {project_token}: {e}")
        return None
    finally:
        db.close()


def clear_coordination_state(project_token: str) -> bool:
    """Clear coordination state for a project (e.g. on project reset)."""
    ensure_table()
    db = SessionLocal()
    try:
        db.execute(
            text(f"DELETE FROM {TABLE_NAME} WHERE project_token = :pt"),
            {"pt": project_token},
        )
        db.commit()
        return True
    except Exception as e:
        db.rollback()
        logger.error(f"[CoordPersistence] Clear failed for {project_token}: {e}")
        return False
    finally:
        db.close()


def coordination_state_exists(project_token: str) -> bool:
    """Check if coordination state exists for a project."""
    ensure_table()
    db = SessionLocal()
    try:
        row = db.execute(
            text(f"SELECT 1 FROM {TABLE_NAME} WHERE project_token = :pt"),
            {"pt": project_token},
        ).fetchone()
        return row is not None
    except Exception:
        return False
    finally:
        db.close()


# ── Integration Helpers ──────────────────────────────────────────────────────

def save_coordination_from_state(project_token: str, state: Dict[str, Any]) -> bool:
    """
    Save coordination state from a SynchronizedAgentState dict.

    This is the main integration point with Phase 1.
    Call this after coordination monitor cycles or state changes.

    Args:
        project_token: Project identifier
        state: Dict with keys from SynchronizedAgentState
               (sync_points, current_phase, phase_gates, agent_statuses,
                file_locks, communication_log, shared_context)
    """
    return save_coordination_state(
        project_token=project_token,
        current_phase=state.get("current_phase", "planning"),
        phase_gates=state.get("phase_gates"),
        sync_points=state.get("sync_points"),
        agent_statuses={
            aid: s.value if hasattr(s, "value") else str(s)
            for aid, s in (state.get("agent_statuses") or {}).items()
        } if state.get("agent_statuses") else None,
        file_locks=state.get("file_locks"),
        communication_log=state.get("communication_log"),
        shared_context=state.get("shared_context"),
    )


def save_task_dag(project_token: str, dag: Dict[str, set]) -> bool:
    """
    Save the task DAG (dependency graph) to the database.

    This is the integration point with Phase 2.
    Call after _build_task_dag() completes.

    Args:
        project_token: Project identifier
        dag: Dict of {task_id: set(dependency_ids)}
    """
    return save_coordination_state(
        project_token=project_token,
        task_dag={k: list(v) for k, v in dag.items()},
    )


def load_task_dag(project_token: str) -> Dict[str, set]:
    """
    Load the task DAG from the database.

    Returns empty dict if no DAG exists.
    """
    state = load_coordination_state(project_token)
    if state and state.get("task_dag"):
        return {k: set(v) for k, v in state["task_dag"].items()}
    return {}


def save_file_locks(project_token: str, file_locks: Dict[str, Any]) -> bool:
    """Save file locks to coordinate state. Integration with Phase 1."""
    return save_coordination_state(project_token=project_token, file_locks=file_locks)


def save_agent_status(project_token: str, agent_id: str, status: str) -> bool:
    """Update a single agent's status in the coordination state."""
    state = load_coordination_state(project_token)
    agent_statuses = state.get("agent_statuses", {}) if state else {}
    agent_statuses[agent_id] = status
    return save_coordination_state(project_token=project_token, agent_statuses=agent_statuses)


def save_phase_gate(project_token: str, phase: str, completed: bool) -> bool:
    """Update a single phase gate."""
    state = load_coordination_state(project_token)
    phase_gates = state.get("phase_gates", {}) if state else {}
    phase_gates[phase] = completed
    return save_coordination_state(project_token=project_token, phase_gates=phase_gates)
