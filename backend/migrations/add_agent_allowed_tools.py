"""
Migration: Add allowed_tools column to agents table

Allows developers/users to configure specific sandbox tools and runtime permissions
for each agent (e.g. filesystem, git, terminal, build_tool, test_runner, web_search, visual_qa, mcp).
"""
import sys
import os
import json
from sqlalchemy import text

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.core.database import engine


def upgrade():
    """Add allowed_tools column to agents table and backfill defaults."""
    with engine.connect() as conn:
        try:
            result = conn.execute(text("PRAGMA table_info(agents)"))
            columns = [row[1] for row in result.fetchall()]

            if "allowed_tools" not in columns:
                print("Adding allowed_tools column to agents table...")
                conn.execute(text("ALTER TABLE agents ADD COLUMN allowed_tools JSON"))
                conn.commit()
                print("[OK] Successfully added allowed_tools column")

                # Backfill existing agents
                print("Backfilling default allowed_tools for existing agents...")
                dev_tools = json.dumps(["filesystem", "git", "terminal", "build_tool"])
                test_tools = json.dumps(["terminal", "test_runner", "visual_qa", "filesystem"])
                
                conn.execute(text(f"""
                    UPDATE agents 
                    SET allowed_tools = '{test_tools}' 
                    WHERE (LOWER(specialization) LIKE '%test%' OR LOWER(name) LIKE '%test%' OR LOWER(name) LIKE '%qa%')
                    AND allowed_tools IS NULL
                """))
                conn.execute(text(f"""
                    UPDATE agents 
                    SET allowed_tools = '{dev_tools}' 
                    WHERE allowed_tools IS NULL
                """))
                conn.commit()
                print("[OK] Successfully backfilled allowed_tools for existing agents")
            else:
                print("[INFO] allowed_tools column already exists in agents table")
        except Exception as e:
            print(f"[ERROR] Migration failed: {e}")
            raise


def downgrade():
    """Clear allowed_tools values."""
    with engine.connect() as conn:
        try:
            conn.execute(text("UPDATE agents SET allowed_tools = NULL"))
            conn.commit()
            print("[OK] Cleared allowed_tools values")
        except Exception as e:
            print(f"[ERROR] Downgrade error: {e}")
            raise


if __name__ == "__main__":
    print("=" * 60)
    print("Running migration: Add allowed_tools column to agents table")
    print("=" * 60)
    upgrade()
    print("Migration complete!")
