"""
Migration: Add coordination_state table for Phase 4 persistence.

This table stores the agent coordination state (sync points, phase gates,
agent statuses, file locks, task DAG) so it survives server restarts.

Run with:
    python -c "from add_coordination_state_table import run_migration; run_migration()"
"""

import logging
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import engine, SessionLocal
from sqlalchemy import text, Column, Integer, String, Boolean, DateTime, JSON, Text
from sqlalchemy import inspect

logger = logging.getLogger(__name__)


TABLE_NAME = "coordination_states"


def table_exists(table_name: str) -> bool:
    """Check if a table exists in the database."""
    inspector = inspect(engine)
    return table_name in inspector.get_table_names()


def run_migration():
    """Create the coordination_states table if it doesn't exist."""
    if table_exists(TABLE_NAME):
        logger.info(f"Table '{TABLE_NAME}' already exists — skipping migration")
        return

    logger.info(f"Creating table '{TABLE_NAME}'...")
    with engine.connect() as conn:
        conn.execute(text(f"""
            CREATE TABLE {TABLE_NAME} (
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

    logger.info(f"✅ Table '{TABLE_NAME}' created successfully")


def add_updated_at_trigger():
    """Add trigger to auto-update updated_at timestamp."""
    with engine.connect() as conn:
        conn.execute(text(f"""
            CREATE TRIGGER IF NOT EXISTS update_{TABLE_NAME}_updated_at
            AFTER UPDATE ON {TABLE_NAME}
            FOR EACH ROW
            BEGIN
                UPDATE {TABLE_NAME} SET updated_at = CURRENT_TIMESTAMP WHERE id = OLD.id;
            END;
        """))
        conn.commit()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_migration()
    add_updated_at_trigger()
    logger.info("Migration complete")
