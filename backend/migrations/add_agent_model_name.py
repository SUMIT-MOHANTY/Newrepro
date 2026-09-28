"""
Migration: Add model_name column to agents table

Allows developers/users to configure specific AI models (Claude, DeepSeek, Kimi)
for each agent according to their role.
"""
import sys
import os
from sqlalchemy import text, inspect

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.core.database import engine


def upgrade():
    """Add model_name column to agents table if not already present."""
    insp = inspect(engine)
    existing_tables = set(insp.get_table_names())

    with engine.connect() as conn:
        if "agents" in existing_tables:
            columns = {c["name"] for c in insp.get_columns("agents")}
            if "model_name" not in columns:
                print("Adding 'model_name' column to agents table...")
                conn.execute(text("ALTER TABLE agents ADD COLUMN model_name VARCHAR(50) DEFAULT 'claude'"))
                conn.commit()
                print("[OK] Successfully added 'model_name' column to agents table")
                
                # Backfill existing agents
                conn.execute(text("UPDATE agents SET model_name = 'claude' WHERE model_name IS NULL"))
                conn.commit()
                print("[OK] Backfilled model_name = 'claude' for existing agents")
            else:
                print("[INFO] 'model_name' column already exists in agents table")


def downgrade():
    """Clear model_name column if needed."""
    pass


if __name__ == "__main__":
    upgrade()
