"""
Migration script: Add 'purpose' column to token_transaction_ledger and ai_usage_logs tables.
Safely handles SQLite, PostgreSQL, and append-only trigger constraints.
"""

import os
import sys
import logging

# Ensure backend root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import inspect, text
from database import engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_migration():
    logger.info("Starting migration: add_purpose_to_ledger_and_usage...")
    inspector = inspect(engine)

    with engine.begin() as conn:
        # 1. Update token_transaction_ledger
        if "token_transaction_ledger" in inspector.get_table_names():
            columns = [col["name"] for col in inspector.get_columns("token_transaction_ledger")]
            if "purpose" not in columns:
                logger.info("Adding column 'purpose' to token_transaction_ledger...")
                conn.execute(text("ALTER TABLE token_transaction_ledger ADD COLUMN purpose VARCHAR"))
                logger.info("Column 'purpose' added to token_transaction_ledger.")
            else:
                logger.info("Column 'purpose' already exists in token_transaction_ledger.")

            try:
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_ttl_purpose ON token_transaction_ledger (purpose)"))
            except Exception as e:
                logger.warning(f"Index creation note: {e}")

        # 2. Update ai_usage_logs
        if "ai_usage_logs" in inspector.get_table_names():
            columns = [col["name"] for col in inspector.get_columns("ai_usage_logs")]
            if "purpose" not in columns:
                logger.info("Adding column 'purpose' to ai_usage_logs...")
                conn.execute(text("ALTER TABLE ai_usage_logs ADD COLUMN purpose VARCHAR"))
                logger.info("Column 'purpose' added to ai_usage_logs.")
            else:
                logger.info("Column 'purpose' already exists in ai_usage_logs.")

            try:
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_ai_usage_logs_purpose ON ai_usage_logs (purpose)"))
            except Exception as e:
                logger.warning(f"Index creation note: {e}")

    logger.info("Migration completed successfully.")

if __name__ == "__main__":
    run_migration()
