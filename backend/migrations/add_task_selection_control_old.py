"""
Migration: Add task selection control features
Adds:
1. is_selected_for_execution column to tasks table
2. sprints table for sprint selection control
3. milestones table for milestone selection control
"""
from sqlalchemy import text
from database import engine, Base
import models


def upgrade():
    """Add task selection control features"""
    with engine.connect() as conn:
        # Add is_selected_for_execution column to tasks table
        try:
            conn.execute(text("""
                ALTER TABLE tasks
                ADD COLUMN is_selected_for_execution BOOLEAN DEFAULT 1
            """))
            conn.commit()
            print("✓ Added is_selected_for_execution column to tasks table")
        except Exception as e:
            if "duplicate column name" in str(e).lower() or "already exists" in str(e).lower():
                print("⚠ is_selected_for_execution column already exists in tasks table")
            else:
                raise
    
    # Create sprints and milestones tables
    try:
        print("Creating sprints and milestones tables...")
        Base.metadata.create_all(engine, tables=[
            models.Sprint.__table__,
            models.Milestone.__table__
        ], checkfirst=True)
        print("✓ Created sprints and milestones tables")
    except Exception as e:
        print(f"⚠ Error creating tables: {e}")
        # Tables might already exist, continue


def downgrade():
    """Remove task selection control features"""
    with engine.connect() as conn:
        try:
            # Drop is_selected_for_execution column from tasks
            conn.execute(text("ALTER TABLE tasks DROP COLUMN is_selected_for_execution"))
            print("✓ Removed is_selected_for_execution column from tasks")
        except Exception as e:
            print(f"⚠ Error removing column: {e}")
        
        try:
            # Drop sprints and milestones tables
            conn.execute(text("DROP TABLE IF EXISTS sprints"))
            conn.execute(text("DROP TABLE IF EXISTS milestones"))
            conn.commit()
            print("✓ Removed sprints and milestones tables")
        except Exception as e:
            print(f"⚠ Error removing tables: {e}")


if __name__ == "__main__":
    print("=" * 60)
    print("Running migration: Add task selection control")
    print("=" * 60)
    print()
    print("This migration adds:")
    print("  • is_selected_for_execution column to tasks table")
    print("  • sprints table for sprint selection tracking")
    print("  • milestones table for milestone selection tracking")
    print()
    print("Purpose: Control which tasks/sprints/milestones are sent to")
    print("         NxDune for agent execution")
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

