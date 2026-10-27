"""
Migration: Add zip_password field to shared_document_files table
 
This migration adds a zip_password string field to store the password
for encrypted zip archives of shared documents.
"""
import os
import sys
from sqlalchemy import text
 
# Add parent directory to sys.path so we can import from database
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
 
from database import engine
 
 
def upgrade():
    """Add zip_password field to shared_document_files table"""
    with engine.connect() as conn:
        try:
            # Add zip_password column as VARCHAR/TEXT
            conn.execute(text("""
                ALTER TABLE shared_document_files
                ADD COLUMN zip_password VARCHAR(255) NULL
            """))
            conn.commit()
            print("[SUCCESS] Added zip_password column to shared_document_files table")
        except Exception as e:
            if "duplicate column name" in str(e).lower() or "already exists" in str(e).lower():
                print("[INFO] zip_password column already exists in shared_document_files table")
            else:
                raise
 
 
def downgrade():
    """Remove zip_password field from shared_document_files table"""
    with engine.connect() as conn:
        try:
            # SQLite doesn't support DROP COLUMN directly, so we need to recreate the table
            # For simplicity, we'll just print a warning
            print("[WARNING] SQLite doesn't support DROP COLUMN. Manual intervention required to remove zip_password column.")
        except Exception as e:
            print(f"[ERROR] Error during downgrade: {e}")
 
 
if __name__ == "__main__":
    print("=" * 60)
    print("Running migration: Add zip_password field")
    print("=" * 60)
    print()
    print("This migration adds zip password functionality:")
    print("  - zip_password - String field to store password for zip files")
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
 
