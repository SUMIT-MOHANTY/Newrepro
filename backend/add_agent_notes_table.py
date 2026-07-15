"""
Migration: Add agent_notes table for local-first coordination notes

This migration adds the agent_notes table to store coordination notes (such as
the master project tree plans, task handoffs, and agent statuses) locally.
"""
from sqlalchemy import text
from database import engine


def upgrade():
    """Create agent_notes table"""
    with engine.connect() as conn:
        # Create agent_notes table
        try:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS agent_notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_token VARCHAR NOT NULL,
                    title VARCHAR NOT NULL,
                    content_payload JSON NOT NULL,
                    content_text TEXT,
                    user VARCHAR,
                    synced_to_nxdune BOOLEAN DEFAULT 0,
                    nxdune_note_id INTEGER,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """))
            conn.commit()
            print("✓ Created agent_notes table")
        except Exception as e:
            if "already exists" in str(e).lower():
                print("⚠ agent_notes table already exists")
            else:
                raise
        
        # Create indexes for better query performance
        try:
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_agent_notes_project_token 
                ON agent_notes(project_token)
            """))
            conn.commit()
            print("✓ Created index on project_token")
        except Exception as e:
            print(f"⚠ Error creating project_token index: {e}")
        
        try:
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_agent_notes_title 
                ON agent_notes(title)
            """))
            conn.commit()
            print("✓ Created index on title")
        except Exception as e:
            print(f"⚠ Error creating title index: {e}")


def downgrade():
    """Remove agent_notes table"""
    with engine.connect() as conn:
        try:
            conn.execute(text("DROP TABLE IF EXISTS agent_notes"))
            conn.commit()
            print("✓ Removed agent_notes table")
        except Exception as e:
            print(f"⚠ Error removing table: {e}")


if __name__ == "__main__":
    print("=" * 60)
    print("Running migration: Add agent_notes table")
    print("=" * 60)
    print()
    print("This migration adds local notes persistence for agents:")
    print("  • agent_notes table - Stores coordination notes locally")
    print("  • Indexes on project_token, title")
    print()
    print("Features:")
    print("  • Persistent local coordination plans and status summaries")
    print("  • Decouples agent planning context from NXDune notes API")
    print("  • Sync tracking flag (synced_to_nxdune)")
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
