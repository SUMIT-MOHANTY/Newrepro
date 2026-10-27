 
"""
Migration: Add task selection control fields
 
This migration adds the 'selected' field to the tasks table to allow users
to select which tasks should be synced to NxDune.
"""
from sqlalchemy import text
from database import engine
 
 
def upgrade():
    """Add selected field to tasks table"""
    with engine.connect() as conn:
        # Add selected column
        try:
            conn.execute(text("""
                ALTER TABLE tasks
                ADD COLUMN selected BOOLEAN DEFAULT 0
            """))
            conn.commit()
            print("✓ Added selected column to tasks table")
        except Exception as e:
            if "duplicate column name" in str(e).lower() or "already exists" in str(e).lower():
                print("⚠ selected column already exists")
            else:
                raise
       
        # Set all existing unsynced tasks as NOT selected by default
        # Users must explicitly select tasks to sync
        try:
            result = conn.execute(text("""
                UPDATE tasks
                SET selected = 0
                WHERE synced_to_nxdune = 0
            """))
            conn.commit()
            print(f"✓ Set {result.rowcount} existing unsynced tasks as unselected (user must select)")
        except Exception as e:
            print(f"⚠ Error updating existing tasks: {e}")
 
 
def downgrade():
    """Remove selected field from tasks table"""
    with engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE tasks DROP COLUMN selected"))
            conn.commit()
            print("✓ Removed selected column from tasks table")
        except Exception as e:
            print(f"⚠ Error removing column: {e}")
 
 
if __name__ == "__main__":
    print("=" * 60)
    print("Running migration: Add task selection control")
    print("=" * 60)
    print()
    print("This migration adds task selection control to the tasks table:")
    print("  • selected (BOOLEAN) - User must check tasks to sync to NxDune")
    print()
    print("IMPORTANT: Tasks are NOT auto-synced anymore.")
    print("Users must explicitly select tasks before syncing to NxDune.")
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
 
 
