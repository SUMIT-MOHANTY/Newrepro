"""
Migration: Add recipient tracking and action logging to access logs

This migration adds recipient_email, action, and filename columns to 
shared_document_access_log table for better tracking.
"""
from sqlalchemy import text
from database import engine


def upgrade():
    """Add tracking columns to shared_document_access_log table"""
    with engine.connect() as conn:
        try:
            # Add recipient_email column
            conn.execute(text("ALTER TABLE shared_document_access_log ADD COLUMN recipient_email VARCHAR"))
            # Add action column
            conn.execute(text("ALTER TABLE shared_document_access_log ADD COLUMN action VARCHAR DEFAULT 'view'"))
            # Add filename column
            conn.execute(text("ALTER TABLE shared_document_access_log ADD COLUMN filename VARCHAR"))
            
            conn.commit()
            print("✓ Added tracking columns to shared_document_access_log table")
        except Exception as e:
            if "duplicate column name" in str(e).lower() or "already exists" in str(e).lower():
                print("⚠ One or more columns already exist in shared_document_access_log table")
            else:
                raise


def downgrade():
    """Remove tracking columns (not fully supported by SQLite)"""
    print("⚠ SQLite doesn't support DROP COLUMN. Manual intervention required.")


if __name__ == "__main__":
    print("=" * 60)
    print("Running migration: Update Access Log Tracking")
    print("=" * 60)
    
    try:
        upgrade()
        print("✅ Migration completed successfully!")
    except Exception as e:
        print(f"❌ Migration failed: {e}")
