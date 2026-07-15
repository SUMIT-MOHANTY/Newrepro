"""
Migration: Add current_step field to share_projects table

This migration adds a current_step integer field to track the last visited step
for each share project.
"""
from sqlalchemy import text
from database import engine


def upgrade():
    """Add current_step field to share_projects table"""
    with engine.connect() as conn:
        try:
            # Add current_step column with default value 0
            conn.execute(text("""
                ALTER TABLE share_projects 
                ADD COLUMN current_step INTEGER DEFAULT 0
            """))
            conn.commit()
            print("✓ Added current_step column to share_projects table")
        except Exception as e:
            if "duplicate column name" in str(e).lower() or "already exists" in str(e).lower():
                print("⚠ current_step column already exists in share_projects table")
            else:
                raise


def downgrade():
    """Remove current_step field from share_projects table"""
    with engine.connect() as conn:
        try:
            # SQLite doesn't support DROP COLUMN directly
            print("⚠ SQLite doesn't support DROP COLUMN. Manual intervention required to remove current_step column.")
        except Exception as e:
            print(f"⚠ Error during downgrade: {e}")


if __name__ == "__main__":
    print("=" * 60)
    print("Running migration: Add current_step to share_projects")
    print("=" * 60)
    print()
    print("This migration adds progress tracking to share projects:")
    print("  • current_step - Integer field to track the last visited step")
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
