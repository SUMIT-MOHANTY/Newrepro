"""
Migration: Add display_id column to agents table

This migration adds the display_id column to the agents table, allowing
us to separate the database primary key (globally unique UUID) from
the user-facing sequential display identifier (organization-scoped unique ID).
"""
import sys
import os
from sqlalchemy import text

# Add parent directory to path so we can import from database
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import engine


def upgrade():
    """Add display_id column to agents table and backfill existing records"""
    with engine.connect() as conn:
        try:
            # Check current columns in agents table
            result = conn.execute(text("PRAGMA table_info(agents)"))
            columns = [row[1] for row in result.fetchall()]
            
            if "display_id" not in columns:
                print("Adding display_id column to agents table...")
                conn.execute(text("ALTER TABLE agents ADD COLUMN display_id VARCHAR"))
                conn.commit()
                print("✓ Successfully added display_id column")
                
                # Backfill: copy id to display_id for existing legacy agents
                print("Backfilling display_id values from existing agent IDs...")
                conn.execute(text("UPDATE agents SET display_id = id WHERE display_id IS NULL"))
                conn.commit()
                print("✓ Successfully backfilled display_id for existing agents")
            else:
                print("⚠ display_id column already exists in agents table")
        except Exception as e:
            print(f"❌ Upgrade failed: {e}")
            raise


def downgrade():
    """Downgrade: Clear display_id column values"""
    with engine.connect() as conn:
        try:
            # SQLite does not easily support ALTER TABLE DROP COLUMN.
            # We will clear display_id values to revert the migration's data impact.
            print("Clearing display_id values...")
            conn.execute(text("UPDATE agents SET display_id = NULL"))
            conn.commit()
            print("✓ Cleared display_id values")
        except Exception as e:
            print(f"⚠ Error clearing values: {e}")
            raise


if __name__ == "__main__":
    print("=" * 60)
    print("Running migration: Add display_id column to agents")
    print("=" * 60)
    print()
    print("This migration adds the display_id column to support the Dual-ID architecture:")
    print("  • database primary key (Agent.id) -> Globally unique UUID")
    print("  • user-facing display label (Agent.display_id) -> Sequential, org-scoped ID")
    print()
    print("Features:")
    print("  • Adds display_id column to agents table")
    print("  • Automatically backfills existing agents (copies id to display_id)")
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
        sys.exit(1)
