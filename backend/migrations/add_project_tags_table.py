"""
Migration: Add project_tags table for project tagging functionality

This migration adds:
1. 'project_tags' table to store tags linked to project governance responses.
"""
from sqlalchemy import text
from database import engine

def upgrade():
    """Apply migrations"""
    with engine.connect() as conn:
        try:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS project_tags (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name VARCHAR NOT NULL,
                    project_id INTEGER NOT NULL,
                    FOREIGN KEY(project_id) REFERENCES governance_responses(id) ON DELETE CASCADE
                )
            """))
            conn.commit()
            print("[OK] Created project_tags table")
        except Exception as e:
            print(f"[WARN] Error creating project_tags table: {e}")
            raise

        try:
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_project_tags_id ON project_tags(id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_project_tags_name ON project_tags(name)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_project_tags_project_id ON project_tags(project_id)"))
            conn.commit()
            print("[OK] Created indexes for project_tags table")
        except Exception as e:
            print(f"[WARN] Error creating indexes: {e}")

def downgrade():
    """Revert migrations"""
    with engine.connect() as conn:
        try:
            conn.execute(text("DROP TABLE IF EXISTS project_tags"))
            conn.commit()
            print("[OK] Dropped project_tags table")
        except Exception as e:
            print(f"[WARN] Error dropping project_tags: {e}")
            raise

if __name__ == "__main__":
    print("=" * 60)
    print("Running migration: Add project_tags table")
    print("=" * 60)
    print()
    
    try:
        upgrade()
        print()
        print("=" * 60)
        print("Migration completed successfully")
        print("=" * 60)
    except Exception as e:
        print(f"Migration failed: {e}")
        exit(1)
