"""
Migration: Add is_archived column to governance_responses table

This migration adds a boolean is_archived column to support soft-delete/archive
functionality. When a project is archived, it is hidden from the UI but stays
in the database for record-keeping.
"""
import os
import sys
from sqlalchemy import text

# Add parent directory to sys.path so we can import from database
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import engine


def upgrade():
    """Add is_archived column to governance_responses table"""
    with engine.connect() as conn:
        try:
            conn.execute(text("""
                ALTER TABLE governance_responses 
                ADD COLUMN is_archived BOOLEAN DEFAULT 0
            """))
            conn.commit()
            print("[SUCCESS] Added is_archived column to governance_responses table")
        except Exception as e:
            err_msg = str(e).lower()
            if "duplicate column name" in err_msg or "already exists" in err_msg:
                print("[INFO] is_archived column already exists in governance_responses table")
            elif "no such table" in err_msg:
                print("[INFO] Table 'governance_responses' does not exist yet.")
                print("[INFO] The table and 'is_archived' column will be created automatically on backend startup.")
            else:
                raise


def downgrade():
    """Remove is_archived column from governance_responses table"""
    with engine.connect() as conn:
        try:
            # SQLite doesn't support DROP COLUMN directly
            print("[WARNING] SQLite doesn't support DROP COLUMN. Manual intervention required to remove is_archived column.")
        except Exception as e:
            print(f"[ERROR] Error during downgrade: {e}")


if __name__ == "__main__":
    print("=" * 60)
    print("Running migration: Add is_archived field")
    print("=" * 60)
    print()
    print("This migration adds the is_archived column:")
    print("  - is_archived - Boolean flag for soft-delete/archive")
    print("    When True, project is hidden from UI but stays in DB")
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
