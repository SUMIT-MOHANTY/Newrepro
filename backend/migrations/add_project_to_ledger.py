"""
Migration script: Add 'project_name' and 'project_token' columns to token_transaction_ledger and 'project_name' to ai_usage_logs.
Safely handles SQLite, PostgreSQL, and append-only trigger constraints without UPDATEs.
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
    logger.info("Starting migration: add_project_to_ledger...")
    inspector = inspect(engine)

    with engine.begin() as conn:
        # 1. Update token_transaction_ledger
        if "token_transaction_ledger" in inspector.get_table_names():
            columns = [col["name"] for col in inspector.get_columns("token_transaction_ledger")]
            
            if "project_token" not in columns:
                logger.info("Adding column 'project_token' to token_transaction_ledger...")
                conn.execute(text("ALTER TABLE token_transaction_ledger ADD COLUMN project_token VARCHAR"))
                logger.info("Column 'project_token' added to token_transaction_ledger.")
            else:
                logger.info("Column 'project_token' already exists in token_transaction_ledger.")

            if "project_name" not in columns:
                logger.info("Adding column 'project_name' to token_transaction_ledger...")
                conn.execute(text("ALTER TABLE token_transaction_ledger ADD COLUMN project_name VARCHAR"))
                logger.info("Column 'project_name' added to token_transaction_ledger.")
            else:
                logger.info("Column 'project_name' already exists in token_transaction_ledger.")

            try:
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_ttl_project_token ON token_transaction_ledger (project_token)"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_ttl_project_name ON token_transaction_ledger (project_name)"))
            except Exception as e:
                logger.warning(f"Index creation note for token_transaction_ledger: {e}")

        # 2. Update ai_usage_logs
        if "ai_usage_logs" in inspector.get_table_names():
            columns = [col["name"] for col in inspector.get_columns("ai_usage_logs")]
            
            if "project_name" not in columns:
                logger.info("Adding column 'project_name' to ai_usage_logs...")
                conn.execute(text("ALTER TABLE ai_usage_logs ADD COLUMN project_name VARCHAR"))
                logger.info("Column 'project_name' added to ai_usage_logs.")
            else:
                logger.info("Column 'project_name' already exists in ai_usage_logs.")

            try:
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_ai_usage_logs_project_name ON ai_usage_logs (project_name)"))
            except Exception as e:
                logger.warning(f"Index creation note for ai_usage_logs: {e}")

    logger.info("Migration add_project_to_ledger completed successfully.")

if __name__ == "__main__":
    run_migration()
