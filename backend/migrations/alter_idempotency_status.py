"""
Migration: Add status column to idempotency_keys table.
"""
import logging
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from database import engine

logger = logging.getLogger("alter_idempotency_status")
logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")

_DDL = [
    (
        "ALTER TABLE idempotency_keys ADD COLUMN status TEXT NOT NULL DEFAULT 'COMPLETED'",
        "ALTER TABLE idempotency_keys ADD COLUMN status TEXT NOT NULL DEFAULT 'COMPLETED'"
    )
]

def upgrade() -> None:
    with engine.connect() as conn:
        for label, stmt in _DDL:
            try:
                conn.execute(text(stmt.strip()))
                conn.commit()
                logger.info("✓ %s", label)
            except Exception as e:
                # Might already exist if run twice
                if "duplicate column name" in str(e).lower():
                    logger.info("✓ %s (already exists)", label)
                else:
                    logger.error("✗ %s: %s", label, e)
                    raise
    logger.info("✅ Migration complete.")

if __name__ == "__main__":
    upgrade()
