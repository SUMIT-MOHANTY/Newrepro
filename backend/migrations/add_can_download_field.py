"""
Migration: Add can_download field to shared_documents table

This migration adds a can_download boolean field to control whether
shared documents can be downloaded by recipients.
"""
from sqlalchemy import text
from database import engine


def upgrade():
    """Add can_download field to shared_documents table"""
    with engine.connect() as conn:
        try:
            # Add can_download column with default value True
            conn.execute(text("""
                ALTER TABLE shared_documents 
                ADD COLUMN can_download BOOLEAN DEFAULT 1
            """))
            conn.commit()
            print("✓ Added can_download column to shared_documents table")
        except Exception as e:
            if "duplicate column name" in str(e).lower() or "already exists" in str(e).lower():
                print("⚠ can_download column already exists in shared_documents table")
            else:
                raise


def downgrade():
    """Remove can_download field from shared_documents table"""
    with engine.connect() as conn:
        try:
            # SQLite doesn't support DROP COLUMN directly, so we need to recreate the table
            # For simplicity, we'll just print a warning
            print("⚠ SQLite doesn't support DROP COLUMN. Manual intervention required to remove can_download column.")
        except Exception as e:
            print(f"⚠ Error during downgrade: {e}")


if __name__ == "__main__":
    print("=" * 60)
    print("Running migration: Add can_download field")
    print("=" * 60)
    print()
    print("This migration adds download control functionality:")
    print("  • can_download - Boolean field to control download permissions")
    print()
    
    try:
        upgrade()
        print()
        print("=" * 60)
        print("✅ Migration completed successfully!")
        print("=" * 60)
    except Exception as e:
        print()
        print("=" * 60)
        print(f"❌ Migration failed: {e}")
        print("=" * 60)
        raise