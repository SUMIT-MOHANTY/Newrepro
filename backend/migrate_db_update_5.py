"""
Migration: Add shared_count and dedicated_count fields to organization_agent_mappings table
 
This migration adds two integer columns to support quantity-based agent allocation:
  - shared_count:    how many Shared instances of this agent are allocated to the project
  - dedicated_count: how many Dedicated instances of this agent are allocated to the project
 
Previously the system only supported a single kind ('shared'/'dedicated') per agent-project
mapping (one row = one agent = one mode). With this change, a single row can express that
e.g. 3 Shared + 2 Dedicated instances of "Test Agent" are allocated to Project A.
"""
from sqlalchemy import text
from database import engine
 
 
def upgrade():
    """Add shared_count and dedicated_count columns to organization_agent_mappings table"""
    with engine.connect() as conn:
 
        # -- shared_count column -------------------------------------------------
        try:
            conn.execute(text("""
                ALTER TABLE organization_agent_mappings
                ADD COLUMN shared_count INTEGER NOT NULL DEFAULT 0
            """))
            conn.commit()
            print("Added shared_count column to organization_agent_mappings table")
        except Exception as e:
            if "duplicate column name" in str(e).lower() or "already exists" in str(e).lower():
                print("shared_count column already exists in organization_agent_mappings table")
            else:
                raise
 
        # -- dedicated_count column ----------------------------------------------
        try:
            conn.execute(text("""
                ALTER TABLE organization_agent_mappings
                ADD COLUMN dedicated_count INTEGER NOT NULL DEFAULT 0
            """))
            conn.commit()
            print("Added dedicated_count column to organization_agent_mappings table")
        except Exception as e:
            if "duplicate column name" in str(e).lower() or "already exists" in str(e).lower():
                print("dedicated_count column already exists in organization_agent_mappings table")
            else:
                raise
 
        # -- Back-fill existing rows ---------------------------------------------
        # For any row that already has agent_kind='shared' and a project assigned,
        # set shared_count = 1 so the new quota logic is consistent with legacy data.
        try:
            result = conn.execute(text("""
                UPDATE organization_agent_mappings
                SET shared_count = 1
                WHERE agent_kind = 'shared'
                  AND project_token IS NOT NULL
                  AND shared_count = 0
                  AND is_default = 0
            """))
            conn.commit()
            print(f"Back-filled shared_count=1 for {result.rowcount} existing shared mappings")
        except Exception as e:
            print(f"Warning: Could not back-fill shared_count rows: {e}")
 
        # For any row that already has agent_kind='dedicated' and a project assigned,
        # set dedicated_count = 1 for the same reason.
        try:
            result = conn.execute(text("""
                UPDATE organization_agent_mappings
                SET dedicated_count = 1
                WHERE agent_kind = 'dedicated'
                  AND project_token IS NOT NULL
                  AND dedicated_count = 0
                  AND is_default = 0
            """))
            conn.commit()
            print(f"Back-filled dedicated_count=1 for {result.rowcount} existing dedicated mappings")
        except Exception as e:
            print(f"Warning: Could not back-fill dedicated_count rows: {e}")
 
 
def downgrade():
    """Remove shared_count and dedicated_count from organization_agent_mappings"""
    with engine.connect() as conn:
        try:
            print("SQLite does not support DROP COLUMN directly.")
            print("To downgrade, manually recreate organization_agent_mappings without these columns.")
        except Exception as e:
            print(f"Warning during downgrade: {e}")
 
 
if __name__ == "__main__":
    print("=" * 60)
    print("Running migration: Add Agent Allocation Count Fields")
    print("=" * 60)
    print()
    print("This migration adds quantity-based allocation support:")
    print("  * shared_count    - number of Shared agent instances per project")
    print("  * dedicated_count - number of Dedicated agent instances per project")
    print()
    print("Back-fills existing rows:")
    print("  * Rows with agent_kind='shared'    -> shared_count = 1")
    print("  * Rows with agent_kind='dedicated' -> dedicated_count = 1")
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
 
