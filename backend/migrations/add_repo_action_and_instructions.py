"""
Migration: Add repo_action, repo_custom_instructions, and project_type columns to governance_responses table.

This ensures existing staging and production databases have the columns required
by the GovernanceResponse SQLAlchemy model without crashing on SELECT queries.
"""
import sys
import os
from sqlalchemy import text, inspect

# Add backend directory to sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from app.core.database import engine
except Exception:
    from database import engine


def upgrade():
    print("[MIGRATION] Running upgrade: add_repo_action_and_instructions")
    inspector = inspect(engine)
    
    if "governance_responses" not in inspector.get_table_names():
        print("[INFO] 'governance_responses' table does not exist yet. Nothing to alter.")
        return

    columns = {c["name"] for c in inspector.get_columns("governance_responses")}

    columns_to_add = [
        ("repo_action", "VARCHAR(255) NULL"),
        ("repo_custom_instructions", "TEXT NULL"),
        ("project_type", "VARCHAR(100) NULL DEFAULT 'greenfield'"),
    ]

    with engine.connect() as conn:
        for col_name, col_type in columns_to_add:
            if col_name not in columns:
                print(f"[ADDING] Column '{col_name}' ({col_type}) to 'governance_responses'...")
                try:
                    conn.execute(text(f"ALTER TABLE governance_responses ADD COLUMN {col_name} {col_type}"))
                    conn.commit()
                    print(f"[SUCCESS] Added '{col_name}' successfully.")
                except Exception as e:
                    if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
                        print(f"[INFO] Column '{col_name}' already exists.")
                    else:
                        print(f"[ERROR] Failed to add column '{col_name}': {e}")
                        raise
            else:
                print(f"[OK] Column '{col_name}' already exists in 'governance_responses'.")


def downgrade():
    print("[WARNING] SQLite does not support DROP COLUMN cleanly. No-op for downgrade.")


if __name__ == "__main__":
    upgrade()
