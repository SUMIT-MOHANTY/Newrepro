import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from database import engine

logger = logging.getLogger("fix_ai_usage_logs_columns")
logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")


def upgrade():
    with engine.connect() as conn:
        for col, ddl in [
            ("organization_name", "ALTER TABLE ai_usage_logs ADD COLUMN organization_name VARCHAR;"),
            ("organization_id", "ALTER TABLE ai_usage_logs ADD COLUMN organization_id VARCHAR(36);"),
            ("usage_status", "ALTER TABLE ai_usage_logs ADD COLUMN usage_status VARCHAR NOT NULL DEFAULT 'COMPLETED';"),
        ]:
            try:
                conn.execute(text(ddl))
                logger.info(f"✓ Added column '{col}' to ai_usage_logs")
            except Exception as e:
                if "duplicate column name" in str(e).lower():
                    logger.info(f"  Column '{col}' already exists in ai_usage_logs")
                else:
                    logger.warning(f"  Note on '{col}': {e}")
        conn.commit()

        # Backfill organization_name and organization_id if NULL
        try:
            conn.execute(text("""
                UPDATE ai_usage_logs
                SET organization_name = COALESCE(
                    (SELECT legacy_name FROM legacy_organization_identifiers WHERE legacy_organization_identifiers.organization_id = ai_usage_logs.organization_id LIMIT 1),
                    project_token
                )
                WHERE organization_name IS NULL;
            """))
            conn.execute(text("""
                UPDATE ai_usage_logs
                SET organization_id = (
                    SELECT organization_id FROM legacy_organization_identifiers 
                    WHERE legacy_organization_identifiers.legacy_name = ai_usage_logs.organization_name
                    LIMIT 1
                )
                WHERE organization_id IS NULL AND organization_name IS NOT NULL;
            """))
            conn.commit()
            logger.info("✓ Backfilled organization_name and organization_id on ai_usage_logs")
        except Exception as e:
            logger.warning(f"Backfill note: {e}")

        res = conn.execute(text("PRAGMA table_info(ai_usage_logs)")).fetchall()
        logger.info("Final columns in ai_usage_logs: %s", [r[1] for r in res])


if __name__ == "__main__":
    upgrade()
