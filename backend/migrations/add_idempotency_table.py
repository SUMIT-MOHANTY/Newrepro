"""
Migration: Add idempotency_keys table.
"""
import logging
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from database import engine

logger = logging.getLogger("idempotency_migration")
logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")

_DDL = [
    (
        "CREATE TABLE idempotency_keys",
        """
        CREATE TABLE IF NOT EXISTS idempotency_keys (
            request_id TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (request_id)
        )
        """
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
                logger.error("✗ %s: %s", label, e)
                raise
    logger.info("✅ Migration complete.")

if __name__ == "__main__":
    upgrade()
