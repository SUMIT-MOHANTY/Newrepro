"""
Migration: Add project_runtime_states table for persistent project execution state

This migration adds the project_runtime_states table to store claimed tasks, 
agent loop statuses, and execution log history across backend restarts.
"""
import sys
import os
# Add parent directory to path so database.py can be found
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from database import engine


def upgrade():
    """Create project_runtime_states table"""
    with engine.connect() as conn:
        try:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS project_runtime_states (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_token VARCHAR NOT NULL UNIQUE,
                    master_tree_created BOOLEAN DEFAULT 0,
                    claimed_task_ids JSON,
                    agent_states JSON,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """))
            conn.commit()
            print("✓ Created project_runtime_states table")
        except Exception as e:
            if "already exists" in str(e).lower():
                print("⚠ project_runtime_states table already exists")
            else:
                raise
        
        # Create indexes
        try:
            conn.execute(text("""
                CREATE UNIQUE INDEX IF NOT EXISTS ix_project_runtime_states_project_token 
                ON project_runtime_states(project_token)
            """))
            conn.commit()
            print("✓ Created unique index on project_token")
        except Exception as e:
            print(f"⚠ Error creating project_token index: {e}")


def downgrade():
    """Remove project_runtime_states table"""
    with engine.connect() as conn:
        try:
            conn.execute(text("DROP TABLE IF EXISTS project_runtime_states"))
            conn.commit()
            print("✓ Removed project_runtime_states table")
        except Exception as e:
            print(f"⚠ Error removing table: {e}")


if __name__ == "__main__":
    print("=" * 60)
    print("Running migration: Add project_runtime_states table")
    print("=" * 60)
    print()
    print("This migration adds the project_runtime_states table:")
    print("  • project_runtime_states table - Stores claimed task IDs, agent statuses, and logs")
    print("  • Unique index on project_token")
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
