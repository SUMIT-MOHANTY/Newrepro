import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from database import engine, Base
import models
import tokenops.models.organization
import tokenops.models.token_wallet
import tokenops.models.pricing
import tokenops.models.payg
import tokenops.models.quota_request
import tokenops.models.ledger
import tokenops.models.summary
import tokenops.models.audit

logger = logging.getLogger("add_payg_grace_period_to_org_wallet")
logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")


def upgrade():
    logger.info("Starting migration: create tokenops tables and add missing columns...")
    
    # 1. Ensure all TokenOps tables exist
    Base.metadata.create_all(bind=engine)
    logger.info("✓ Ensured all TokenOps tables exist (token_quota_requests, admin_audit_logs, etc.)")

    with engine.connect() as conn:
        # 2. OrganizationWallet columns check and add
        org_wallet_cols = [
            ("payg_grace_period_months", "ALTER TABLE organization_wallet ADD COLUMN payg_grace_period_months INTEGER NOT NULL DEFAULT 3;"),
            ("payg_reserved_spend_usd", "ALTER TABLE organization_wallet ADD COLUMN payg_reserved_spend_usd NUMERIC(20, 8) NOT NULL DEFAULT 0.0;"),
            ("payg_billing_email", "ALTER TABLE organization_wallet ADD COLUMN payg_billing_email VARCHAR;"),
            ("payg_soft_limit_usd", "ALTER TABLE organization_wallet ADD COLUMN payg_soft_limit_usd NUMERIC(10, 2);"),
            ("payg_hard_limit_usd", "ALTER TABLE organization_wallet ADD COLUMN payg_hard_limit_usd NUMERIC(10, 2);"),
            ("payg_current_spend_usd", "ALTER TABLE organization_wallet ADD COLUMN payg_current_spend_usd NUMERIC(20, 8) NOT NULL DEFAULT 0.0;"),
            ("organization_id", "ALTER TABLE organization_wallet ADD COLUMN organization_id VARCHAR(36);")
        ]

        for col, ddl in org_wallet_cols:
            try:
                conn.execute(text(ddl))
                logger.info(f"✓ Added column '{col}' to organization_wallet")
            except Exception as e:
                if "duplicate column name" in str(e).lower():
                    logger.info(f"  Column '{col}' already exists in organization_wallet")
                else:
                    logger.warning(f"  Note on '{col}': {e}")

        conn.commit()

        # Verify final columns in organization_wallet
        res = conn.execute(text("PRAGMA table_info(organization_wallet)")).fetchall()
        logger.info("Final columns in organization_wallet: %s", [r[1] for r in res])
        logger.info("Migration completed successfully.")


if __name__ == "__main__":
    upgrade()
