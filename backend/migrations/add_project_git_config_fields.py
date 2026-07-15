"""
Migration: Add project-wise Git configuration fields to governance_responses table

This migration adds columns to store separate source and destination repository
URLs and credentials on a per-project basis.
"""
import os
import sys
from sqlalchemy import text

# Add parent directory to sys.path so we can import from database
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import engine


def upgrade():
    """Add source and destination repo fields to governance_responses table"""
    with engine.connect() as conn:
        columns_to_add = [
            ("source_repo_url", "VARCHAR(1000)"),
            ("source_repo_token", "VARCHAR(255)"),
            ("dest_repo_url", "VARCHAR(1000)"),
            ("dest_repo_token", "VARCHAR(255)"),
        ]
        
        for col_name, col_type in columns_to_add:
            try:
                conn.execute(text(f"""
                    ALTER TABLE governance_responses 
                    ADD COLUMN {col_name} {col_type} NULL
                """))
                conn.commit()
                print(f"[SUCCESS] Added {col_name} column to governance_responses table")
            except Exception as e:
                if "duplicate column name" in str(e).lower() or "already exists" in str(e).lower():
                    print(f"[INFO] {col_name} column already exists in governance_responses table")
                else:
                    raise


def downgrade():
    """Remove Git configuration fields from governance_responses table"""
    with engine.connect() as conn:
        try:
            # SQLite doesn't support DROP COLUMN directly
            print("[WARNING] SQLite doesn't support DROP COLUMN. Manual intervention required to remove Git configuration columns.")
        except Exception as e:
            print(f"[ERROR] Error during downgrade: {e}")


if __name__ == "__main__":
    print("=" * 60)
    print("Running migration: Add project-wise Git configuration fields")
    print("=" * 60)
    print()
    print("This migration adds project-wise Git configuration columns:")
    print("  - source_repo_url - URL to clone source codebase from")
    print("  - source_repo_token - Authentication token for the source repo")
    print("  - dest_repo_url - URL to push features/changes to")
    print("  - dest_repo_token - Authentication token for the destination repo")
    print()
    
    try:
        upgrade()
        print()
        print("=" * 60)
        print("Migration completed successfully!")
        print("=" * 60)
    except Exception as e:
        print()
        print("=" * 60)
        print(f"Migration failed: {e}")
        print("=" * 60)
        raise
