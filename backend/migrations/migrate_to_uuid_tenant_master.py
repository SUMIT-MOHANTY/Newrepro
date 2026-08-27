"""
Migration: Phase 6.1 Tenant Master & UUID Hardening.

1. Creates `organizations` table (UUID PK).
2. Creates `legacy_organization_identifiers` table (deterministic mapping).
3. Backfills all legacy organization names from existing tables into `organizations` and `legacy_organization_identifiers`.
4. Adds `organization_id` columns to all dependent tables and backfills them.
"""

import logging
import os
import sys
import uuid
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from database import engine

logger = logging.getLogger("migrate_to_uuid_tenant_master")
logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")


def upgrade() -> None:
    with engine.connect() as conn:
        conn.execute(text("PRAGMA foreign_keys = OFF"))

        # 1. Create organizations table
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS organizations (
                id VARCHAR(36) PRIMARY KEY,
                name TEXT NOT NULL,
                is_active BOOLEAN NOT NULL DEFAULT 1,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_organizations_name ON organizations (name);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_organizations_active ON organizations (is_active);"))
        logger.info("✓ Created table 'organizations'")

        # 2. Create legacy_organization_identifiers table
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS legacy_organization_identifiers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                organization_id VARCHAR(36) NOT NULL,
                legacy_name TEXT NOT NULL UNIQUE,
                alias_type TEXT NOT NULL DEFAULT 'LEGACY_NAME',
                is_active BOOLEAN NOT NULL DEFAULT 1,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (organization_id) REFERENCES organizations (id) ON DELETE CASCADE
            );
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_legacy_org_name ON legacy_organization_identifiers (legacy_name);"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_legacy_org_id ON legacy_organization_identifiers (organization_id);"))
        logger.info("✓ Created table 'legacy_organization_identifiers'")
        conn.commit()

        # 3. Discover and seed all legacy organization names
        tables_with_org_name = [
            ("organization_wallet", "organization_name"),
            ("user_organization", "organization_name"),
            ("user_token_wallet", "organization_name"),
            ("token_transaction_ledger", "organization_name"),
            ("organization_usage_summary", "organization_name"),
            ("user_usage_summary", "organization_name"),
            ("payg_request", "organization_name"),
            ("payg_invoice", "organization_name"),
            ("organization_roles", "organization_name"),
            ("user_organization_roles", "organization_name"),
            ("users", "organization_name"),
        ]

        discovered_orgs = set()
        for tbl, col in tables_with_org_name:
            try:
                res = conn.execute(text(f"SELECT DISTINCT {col} FROM {tbl} WHERE {col} IS NOT NULL AND {col} != ''")).fetchall()
                for row in res:
                    if row[0]:
                        discovered_orgs.add(str(row[0]).strip())
            except Exception as e:
                # Table might not exist yet or have different schema
                continue

        # Add default DSuite Organization if none found
        if not discovered_orgs:
            discovered_orgs.add("Default Organization")
            discovered_orgs.add("BournAI")

        for org_name in discovered_orgs:
            # Check if alias already exists
            existing = conn.execute(
                text("SELECT organization_id FROM legacy_organization_identifiers WHERE legacy_name = :name"),
                {"name": org_name}
            ).fetchone()

            if not existing:
                org_uuid = str(uuid.uuid4())
                now = datetime.utcnow()
                conn.execute(
                    text("INSERT INTO organizations (id, name, is_active, created_at, updated_at) VALUES (:id, :name, 1, :now, :now)"),
                    {"id": org_uuid, "name": org_name, "now": now}
                )
                conn.execute(
                    text("INSERT INTO legacy_organization_identifiers (organization_id, legacy_name, alias_type, is_active, created_at) VALUES (:org_id, :name, 'LEGACY_NAME', 1, :now)"),
                    {"org_id": org_uuid, "name": org_name, "now": now}
                )
                logger.info(f"✓ Seeded Org: '{org_name}' -> UUID: {org_uuid}")

        conn.commit()

        # 4. Add organization_id column to tables if not present, and backfill
        dependent_tables = [
            "organization_wallet",
            "user_organization",
            "user_token_wallet",
            "token_transaction_ledger",
            "organization_usage_summary",
            "user_usage_summary",
            "payg_request",
            "payg_invoice",
            "ai_usage_logs",
            "organization_roles",
            "user_organization_roles"
        ]

        for tbl in dependent_tables:
            try:
                conn.execute(text(f"ALTER TABLE {tbl} ADD COLUMN organization_id VARCHAR(36)"))
                logger.info(f"✓ Added column 'organization_id' to '{tbl}'")
            except Exception as e:
                if "duplicate column name" in str(e).lower():
                    logger.info(f"  Column 'organization_id' already exists in '{tbl}'")
                else:
                    logger.warning(f"  Note on table '{tbl}': {e}")
            conn.commit()

            # Backfill organization_id
            try:
                if tbl == "ai_usage_logs":
                    # Join with legacy_organization_identifiers on project_token or organization_name
                    conn.execute(text("""
                        UPDATE ai_usage_logs
                        SET organization_id = (
                            SELECT organization_id FROM legacy_organization_identifiers 
                            WHERE legacy_organization_identifiers.legacy_name = ai_usage_logs.project_token
                            LIMIT 1
                        )
                        WHERE organization_id IS NULL AND project_token IS NOT NULL;
                    """))
                else:
                    conn.execute(text(f"""
                        UPDATE {tbl}
                        SET organization_id = (
                            SELECT organization_id FROM legacy_organization_identifiers 
                            WHERE legacy_organization_identifiers.legacy_name = {tbl}.organization_name
                            LIMIT 1
                        )
                        WHERE organization_id IS NULL AND organization_name IS NOT NULL;
                    """))
                conn.commit()
                logger.info(f"✓ Backfilled 'organization_id' on '{tbl}'")
            except Exception as e:
                logger.warning(f"  Backfill skipped for '{tbl}': {e}")

        conn.execute(text("PRAGMA foreign_keys = ON"))
        logger.info("✅ Phase 6.1 UUID Tenant Master migration completed successfully.")


if __name__ == "__main__":
    upgrade()
