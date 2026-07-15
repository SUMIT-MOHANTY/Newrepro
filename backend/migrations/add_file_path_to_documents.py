"""
Migration: Add file_path field to documents table

This migration adds a file_path column to the documents table to store
the local file path or unique filename on the server.
"""
import os
import sys

# Ensure backend directory is in the import path
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from sqlalchemy import text
from database import engine


def upgrade():
    """Add file_path field to documents table"""
    with engine.connect() as conn:
        try:
            # Add file_path column
            conn.execute(text("""
                ALTER TABLE documents 
                ADD COLUMN file_path TEXT
            """))
            conn.commit()
            print("OK: Added file_path column to documents table")
        except Exception as e:
            if "duplicate column name" in str(e).lower() or "already exists" in str(e).lower():
                print("WARNING: file_path column already exists in documents table")
            else:
                raise


def downgrade():
    """Remove file_path field from documents table"""
    with engine.connect() as conn:
        try:
            print("WARNING: SQLite doesn't support DROP COLUMN. Manual intervention required to remove file_path column.")
        except Exception as e:
            print(f"WARNING: Error during downgrade: {e}")


if __name__ == "__main__":
    print("=" * 60)
    print("Running migration: Add file_path field to documents table")
    print("=" * 60)
    print()
    print("This migration adds file path tracking to uploaded documents:")
    print("  - file_path - Text field to store local path of documents")
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
