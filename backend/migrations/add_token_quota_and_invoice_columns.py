"""
Migration: Add missing requested_limit_usd to token_quota_requests and financial columns to payg_invoice.

Ensures schema parity between SQLAlchemy models and the SQLite database.
"""
import sys
import os
from sqlalchemy import text, inspect

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.core.database import engine


def upgrade():
    """Add requested_limit_usd to token_quota_requests and missing invoice columns."""
    insp = inspect(engine)
    existing_tables = set(insp.get_table_names())

    with engine.connect() as conn:
        # 1. token_quota_requests
        if "token_quota_requests" in existing_tables:
            columns = {c["name"] for c in insp.get_columns("token_quota_requests")}
            if "requested_limit_usd" not in columns:
                print("Adding 'requested_limit_usd' column to token_quota_requests...")
                conn.execute(text("ALTER TABLE token_quota_requests ADD COLUMN requested_limit_usd NUMERIC(10, 2)"))
                conn.commit()
                print("[OK] Successfully added 'requested_limit_usd' to token_quota_requests")
            else:
                print("[INFO] 'requested_limit_usd' already exists in token_quota_requests")
        else:
            print("[INFO] Table 'token_quota_requests' does not exist yet")

        # 2. payg_invoice
        if "payg_invoice" in existing_tables:
            invoice_cols = {c["name"] for c in insp.get_columns("payg_invoice")}
            new_invoice_columns = [
                ("prompt_tokens", "INTEGER NOT NULL DEFAULT 0"),
                ("completion_tokens", "INTEGER NOT NULL DEFAULT 0"),
                ("input_cost", "REAL NOT NULL DEFAULT 0.0"),
                ("output_cost", "REAL NOT NULL DEFAULT 0.0"),
                ("line_items", "TEXT"),
                ("recipient_email", "TEXT"),
                ("paid_at", "DATETIME"),
            ]
            for col_name, col_type in new_invoice_columns:
                if col_name not in invoice_cols:
                    print(f"Adding '{col_name}' column to payg_invoice...")
                    conn.execute(text(f"ALTER TABLE payg_invoice ADD COLUMN {col_name} {col_type}"))
                    conn.commit()
                    print(f"[OK] Successfully added '{col_name}' to payg_invoice")
                else:
                    print(f"[INFO] '{col_name}' already exists in payg_invoice")
        else:
            print("[INFO] Table 'payg_invoice' does not exist yet")


def downgrade():
    """SQLite does not support DROP COLUMN cleanly in older versions, nothing to do."""
    pass


if __name__ == "__main__":
    upgrade()
