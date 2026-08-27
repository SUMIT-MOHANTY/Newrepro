"""
Migration: Add TokenOps database tables.

Tables created:
    1. organization_wallet          — Org prepaid token wallet
    2. user_organization            — User ↔ org adjacency list
    3. user_token_wallet            — Per-user token allocation
    4. model_pricing                — AI model pricing (replaces hardcoded rate)
    5. payg_request                 — PAYG enablement approval workflow
    6. payg_invoice                 — Monthly PAYG billing record
    7. token_transaction_ledger     — Immutable append-only financial ledger
    8. organization_usage_summary   — Prefix-sum dashboard rollup

Safety:
    • All statements use CREATE TABLE IF NOT EXISTS — fully idempotent.
    • All statements use CREATE INDEX IF NOT EXISTS — safe to re-run.
    • No existing tables are modified (backward-compatible).
    • Designed for SQLite; no PostgreSQL-specific syntax.
    • No SELECT FOR UPDATE.

Run:
    python migrations/add_tokenops_tables.py

    Or from backend root:
    python -c "from migrations.add_tokenops_tables import upgrade; upgrade()"
"""

import logging
import sys
import os

# Ensure the backend root is on sys.path when run directly.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from database import engine

logger = logging.getLogger("tokenops_migration")
logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")


# ---------------------------------------------------------------------------
# DDL statements
# ---------------------------------------------------------------------------

_DDL_STATEMENTS: list[tuple[str, str]] = [
    # ── 1. organization_wallet ───────────────────────────────────────────────
    (
        "CREATE TABLE organization_wallet",
        """
        CREATE TABLE IF NOT EXISTS organization_wallet (
            id                TEXT    NOT NULL,
            organization_name TEXT    NOT NULL,
            purchased_tokens  INTEGER NOT NULL DEFAULT 0,
            remaining_tokens  INTEGER NOT NULL DEFAULT 0,
            reserved_tokens   INTEGER NOT NULL DEFAULT 0,
            payg_enabled      INTEGER NOT NULL DEFAULT 0,
            is_blocked        INTEGER NOT NULL DEFAULT 0,
            created_at        TEXT    NOT NULL DEFAULT (datetime('now')),
            updated_at        TEXT    NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (id)
        )
        """,
    ),
    (
        "UNIQUE INDEX uq_org_wallet_org_name",
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_org_wallet_org_name
            ON organization_wallet (organization_name)
        """,
    ),
    (
        "INDEX ix_org_wallet_blocked",
        """
        CREATE INDEX IF NOT EXISTS ix_org_wallet_blocked
            ON organization_wallet (is_blocked)
        """,
    ),

    # ── 2. user_organization ─────────────────────────────────────────────────
    (
        "CREATE TABLE user_organization",
        """
        CREATE TABLE IF NOT EXISTS user_organization (
            id                INTEGER NOT NULL,
            user_id           INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            organization_name TEXT    NOT NULL,
            role              TEXT    NOT NULL DEFAULT 'member',
            is_active         INTEGER NOT NULL DEFAULT 1,
            joined_at         TEXT    NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (id)
        )
        """,
    ),
    (
        "UNIQUE INDEX uq_user_org_membership",
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_user_org_membership
            ON user_organization (user_id, organization_name)
        """,
    ),
    (
        "INDEX ix_user_org_user_org",
        """
        CREATE INDEX IF NOT EXISTS ix_user_org_user_org
            ON user_organization (user_id, organization_name)
        """,
    ),
    (
        "INDEX ix_user_org_org_active",
        """
        CREATE INDEX IF NOT EXISTS ix_user_org_org_active
            ON user_organization (organization_name, is_active)
        """,
    ),

    # ── 3. user_token_wallet ─────────────────────────────────────────────────
    (
        "CREATE TABLE user_token_wallet",
        """
        CREATE TABLE IF NOT EXISTS user_token_wallet (
            id                INTEGER NOT NULL,
            user_id           INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            organization_name TEXT    NOT NULL,
            allocated_tokens  INTEGER NOT NULL DEFAULT 0,
            consumed_tokens   INTEGER NOT NULL DEFAULT 0,
            remaining_tokens  INTEGER NOT NULL DEFAULT 0,
            is_blocked        INTEGER NOT NULL DEFAULT 0,
            created_at        TEXT    NOT NULL DEFAULT (datetime('now')),
            updated_at        TEXT    NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (id)
        )
        """,
    ),
    (
        "UNIQUE INDEX uq_user_token_wallet",
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_user_token_wallet
            ON user_token_wallet (user_id, organization_name)
        """,
    ),
    (
        "INDEX ix_user_token_wallet_org",
        """
        CREATE INDEX IF NOT EXISTS ix_user_token_wallet_org
            ON user_token_wallet (organization_name)
        """,
    ),
    (
        "INDEX ix_user_token_wallet_blocked",
        """
        CREATE INDEX IF NOT EXISTS ix_user_token_wallet_blocked
            ON user_token_wallet (is_blocked)
        """,
    ),

    # ── 4. model_pricing ─────────────────────────────────────────────────────
    (
        "CREATE TABLE model_pricing",
        """
        CREATE TABLE IF NOT EXISTS model_pricing (
            id              INTEGER NOT NULL,
            model_name      TEXT    NOT NULL,
            price_per_token REAL    NOT NULL DEFAULT 0.000007,
            effective_from  TEXT    NOT NULL DEFAULT (datetime('now')),
            is_active       INTEGER NOT NULL DEFAULT 1,
            created_by      INTEGER REFERENCES users(id) ON DELETE SET NULL,
            created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (id)
        )
        """,
    ),
    (
        "INDEX ix_model_pricing_active_lookup",
        """
        CREATE INDEX IF NOT EXISTS ix_model_pricing_active_lookup
            ON model_pricing (model_name, is_active)
        """,
    ),
    (
        "UNIQUE INDEX uq_model_pricing_active_model",
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_model_pricing_active_model
            ON model_pricing (model_name, is_active)
        """,
    ),

    # ── 5. payg_request ──────────────────────────────────────────────────────
    (
        "CREATE TABLE payg_request",
        """
        CREATE TABLE IF NOT EXISTS payg_request (
            id                INTEGER NOT NULL,
            organization_name TEXT    NOT NULL,
            requested_by      INTEGER REFERENCES users(id) ON DELETE SET NULL,
            status            TEXT    NOT NULL DEFAULT 'REQUESTED',
            approved_by       INTEGER REFERENCES users(id) ON DELETE SET NULL,
            approved_at       TEXT,
            remarks           TEXT,
            created_at        TEXT    NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (id)
        )
        """,
    ),
    (
        "INDEX ix_payg_request_org_status",
        """
        CREATE INDEX IF NOT EXISTS ix_payg_request_org_status
            ON payg_request (organization_name, status)
        """,
    ),
    (
        "INDEX ix_payg_request_status",
        """
        CREATE INDEX IF NOT EXISTS ix_payg_request_status
            ON payg_request (status)
        """,
    ),

    # ── 6. payg_invoice ──────────────────────────────────────────────────────
    (
        "CREATE TABLE payg_invoice",
        """
        CREATE TABLE IF NOT EXISTS payg_invoice (
            id                INTEGER NOT NULL,
            organization_name TEXT    NOT NULL,
            billing_month     TEXT    NOT NULL,
            total_tokens      INTEGER NOT NULL DEFAULT 0,
            total_cost        REAL    NOT NULL DEFAULT 0.0,
            invoice_status    TEXT    NOT NULL DEFAULT 'PENDING',
            generated_at      TEXT    NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (id)
        )
        """,
    ),
    (
        "UNIQUE INDEX uq_payg_invoice_org_month",
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_payg_invoice_org_month
            ON payg_invoice (organization_name, billing_month)
        """,
    ),
    (
        "INDEX ix_payg_invoice_org_month",
        """
        CREATE INDEX IF NOT EXISTS ix_payg_invoice_org_month
            ON payg_invoice (organization_name, billing_month)
        """,
    ),
    (
        "INDEX ix_payg_invoice_status",
        """
        CREATE INDEX IF NOT EXISTS ix_payg_invoice_status
            ON payg_invoice (invoice_status)
        """,
    ),

    # ── 7. token_transaction_ledger ──────────────────────────────────────────
    (
        "CREATE TABLE token_transaction_ledger",
        """
        CREATE TABLE IF NOT EXISTS token_transaction_ledger (
            id                INTEGER NOT NULL,
            organization_name TEXT    NOT NULL,
            user_id           INTEGER REFERENCES users(id) ON DELETE SET NULL,
            transaction_type  TEXT    NOT NULL,
            token_delta       INTEGER NOT NULL,
            balance_after     INTEGER NOT NULL,
            reference_id      TEXT,
            remarks           TEXT,
            created_by        INTEGER REFERENCES users(id) ON DELETE SET NULL,
            created_at        TEXT    NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (id),
            CHECK (token_delta != 0)
        )
        """,
    ),
    (
        "INDEX ix_ttl_org_created",
        """
        CREATE INDEX IF NOT EXISTS ix_ttl_org_created
            ON token_transaction_ledger (organization_name, created_at)
        """,
    ),
    (
        "INDEX ix_ttl_org_type",
        """
        CREATE INDEX IF NOT EXISTS ix_ttl_org_type
            ON token_transaction_ledger (organization_name, transaction_type)
        """,
    ),
    (
        "INDEX ix_ttl_user_created",
        """
        CREATE INDEX IF NOT EXISTS ix_ttl_user_created
            ON token_transaction_ledger (user_id, created_at)
        """,
    ),
    (
        "INDEX ix_ttl_reference",
        """
        CREATE INDEX IF NOT EXISTS ix_ttl_reference
            ON token_transaction_ledger (reference_id)
        """,
    ),
    # Append-only trigger: prevents UPDATE on any ledger row.
    # SQLite triggers use FOR EACH ROW semantics automatically.
    (
        "TRIGGER trg_ttl_no_update",
        """
        CREATE TRIGGER IF NOT EXISTS trg_ttl_no_update
        BEFORE UPDATE ON token_transaction_ledger
        BEGIN
            SELECT RAISE(FAIL, 'token_transaction_ledger is append-only: UPDATE is forbidden');
        END
        """,
    ),
    # Append-only trigger: prevents DELETE on any ledger row.
    (
        "TRIGGER trg_ttl_no_delete",
        """
        CREATE TRIGGER IF NOT EXISTS trg_ttl_no_delete
        BEFORE DELETE ON token_transaction_ledger
        BEGIN
            SELECT RAISE(FAIL, 'token_transaction_ledger is append-only: DELETE is forbidden');
        END
        """,
    ),

    # ── 8. organization_usage_summary ────────────────────────────────────────
    (
        "CREATE TABLE organization_usage_summary",
        """
        CREATE TABLE IF NOT EXISTS organization_usage_summary (
            id                      INTEGER NOT NULL,
            organization_name       TEXT    NOT NULL,
            total_prompt_tokens     INTEGER NOT NULL DEFAULT 0,
            total_completion_tokens INTEGER NOT NULL DEFAULT 0,
            total_tokens            INTEGER NOT NULL DEFAULT 0,
            total_cost              REAL    NOT NULL DEFAULT 0.0,
            request_count           INTEGER NOT NULL DEFAULT 0,
            last_updated            TEXT    NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (id)
        )
        """,
    ),
    (
        "UNIQUE INDEX uq_org_usage_summary_org",
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_org_usage_summary_org
            ON organization_usage_summary (organization_name)
        """,
    ),
    (
        "INDEX ix_org_usage_summary_org",
        """
        CREATE INDEX IF NOT EXISTS ix_org_usage_summary_org
            ON organization_usage_summary (organization_name)
        """,
    ),
    (
        "INDEX ix_org_usage_summary_updated",
        """
        CREATE INDEX IF NOT EXISTS ix_org_usage_summary_updated
            ON organization_usage_summary (last_updated)
        """,
    ),

    # ── 9. admin_audit_logs ──────────────────────────────────────────────────
    (
        "CREATE TABLE admin_audit_logs",
        """
        CREATE TABLE IF NOT EXISTS admin_audit_logs (
            id                INTEGER NOT NULL,
            admin_user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            actor_type        TEXT    NOT NULL DEFAULT 'SUPER_ADMIN',
            action            TEXT    NOT NULL,
            target_entity     TEXT    NOT NULL,
            organization_name TEXT,
            request_id        TEXT,
            details           TEXT,
            created_at        TEXT    NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (id)
        )
        """,
    ),
    (
        "INDEX ix_admin_audit_logs_admin_user_id",
        """
        CREATE INDEX IF NOT EXISTS ix_admin_audit_logs_admin_user_id
            ON admin_audit_logs (admin_user_id)
        """,
    ),
    (
        "INDEX ix_admin_audit_logs_actor_type",
        """
        CREATE INDEX IF NOT EXISTS ix_admin_audit_logs_actor_type
            ON admin_audit_logs (actor_type)
        """,
    ),
    (
        "INDEX ix_admin_audit_logs_action",
        """
        CREATE INDEX IF NOT EXISTS ix_admin_audit_logs_action
            ON admin_audit_logs (action)
        """,
    ),
    (
        "INDEX ix_admin_audit_logs_org_name",
        """
        CREATE INDEX IF NOT EXISTS ix_admin_audit_logs_org_name
            ON admin_audit_logs (organization_name)
        """,
    ),
    (
        "INDEX ix_admin_audit_logs_request_id",
        """
        CREATE INDEX IF NOT EXISTS ix_admin_audit_logs_request_id
            ON admin_audit_logs (request_id)
        """,
    ),
    (
        "INDEX ix_admin_audit_logs_created_at",
        """
        CREATE INDEX IF NOT EXISTS ix_admin_audit_logs_created_at
            ON admin_audit_logs (created_at)
        """,
    ),

    # ── 10. token_quota_requests ─────────────────────────────────────────────
    (
        "CREATE TABLE token_quota_requests",
        """
        CREATE TABLE IF NOT EXISTS token_quota_requests (
            id                INTEGER NOT NULL,
            organization_name TEXT    NOT NULL,
            organization_id   TEXT,
            request_type      TEXT    NOT NULL,
            requested_tokens  INTEGER NOT NULL DEFAULT 0,
            requested_by      INTEGER REFERENCES users(id) ON DELETE SET NULL,
            status            TEXT    NOT NULL DEFAULT 'REQUESTED',
            remarks           TEXT,
            admin_notes       TEXT,
            approved_by       INTEGER REFERENCES users(id) ON DELETE SET NULL,
            created_at        TEXT    NOT NULL DEFAULT (datetime('now')),
            approved_at       TEXT,
            PRIMARY KEY (id)
        )
        """,
    ),
    (
        "INDEX ix_token_quota_requests_org_name",
        """
        CREATE INDEX IF NOT EXISTS ix_token_quota_requests_org_name
            ON token_quota_requests (organization_name)
        """,
    ),
    (
        "INDEX ix_token_quota_requests_org_id",
        """
        CREATE INDEX IF NOT EXISTS ix_token_quota_requests_org_id
            ON token_quota_requests (organization_id)
        """,
    ),
    (
        "INDEX ix_token_quota_requests_type",
        """
        CREATE INDEX IF NOT EXISTS ix_token_quota_requests_type
            ON token_quota_requests (request_type)
        """,
    ),
    (
        "INDEX ix_token_quota_requests_status",
        """
        CREATE INDEX IF NOT EXISTS ix_token_quota_requests_status
            ON token_quota_requests (status)
        """,
    ),
    (
        "INDEX ix_token_quota_requests_requested_by",
        """
        CREATE INDEX IF NOT EXISTS ix_token_quota_requests_requested_by
            ON token_quota_requests (requested_by)
        """,
    ),
]

# Default pricing seed row — mirrors the hardcoded rate in llm_gateway.py.
# Inserted only if no active pricing row exists for "BournAI".
_SEED_PRICING = """
    INSERT OR IGNORE INTO model_pricing
        (model_name, price_per_token, effective_from, is_active, created_at)
    VALUES
        ('BournAI',   0.000007, datetime('now'), 1, datetime('now')),
        ('DSuite Model', 0.000007, datetime('now'), 1, datetime('now'))
"""


# ---------------------------------------------------------------------------
# Migration entry points
# ---------------------------------------------------------------------------

def upgrade() -> None:
    """Create all TokenOps tables, indexes, and triggers."""
    with engine.connect() as conn:
        # Enable foreign key enforcement for this session.
        conn.execute(text("PRAGMA foreign_keys = ON"))

        for label, ddl in _DDL_STATEMENTS:
            try:
                conn.execute(text(ddl.strip()))
                conn.commit()
                logger.info("✓  %s", label)
            except Exception as exc:
                err = str(exc).lower()
                if "already exists" in err:
                    logger.info("⚠  %s (already exists, skipped)", label)
                else:
                    logger.error("✗  %s: %s", label, exc)
                    raise

        # Seed default pricing rows.
        try:
            conn.execute(text(_SEED_PRICING.strip()))
            conn.commit()
            logger.info("✓  Seed model_pricing defaults (BournAI, DSuite Model)")
        except Exception as exc:
            logger.warning("⚠  Seed pricing skipped: %s", exc)

    logger.info("✅  TokenOps migration completed successfully.")


def downgrade() -> None:
    """
    Drop all TokenOps tables in reverse dependency order.
    WARNING: This is destructive and irreversible in production.
    """
    drop_order = [
        "token_quota_requests",
        "admin_audit_logs",
        "token_transaction_ledger",
        "organization_usage_summary",
        "payg_invoice",
        "payg_request",
        "model_pricing",
        "user_token_wallet",
        "user_organization",
        "organization_wallet",
    ]
    with engine.connect() as conn:
        for table in drop_order:
            try:
                conn.execute(text(f"DROP TABLE IF EXISTS {table}"))
                conn.commit()
                logger.info("✓  Dropped table %s", table)
            except Exception as exc:
                logger.error("✗  Could not drop %s: %s", table, exc)
                raise
    logger.info("✅  TokenOps downgrade completed.")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="TokenOps database migration")
    parser.add_argument(
        "--downgrade", action="store_true",
        help="Drop all TokenOps tables (DESTRUCTIVE)",
    )
    args = parser.parse_args()

    if args.downgrade:
        confirm = input(
            "⚠  This will DROP all TokenOps tables. Type 'yes' to confirm: "
        ).strip()
        if confirm.lower() != "yes":
            print("Aborted.")
            sys.exit(0)
        downgrade()
    else:
        upgrade()
