"""
Migration: Add project_token column to the documents table.

Links each document directly to a project, enabling project-wise filtering
in the history API instead of returning all documents and matching client-side.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import engine
from sqlalchemy import inspect, text


def upgrade():
    """Add project_token column to documents table."""
    inspector = inspect(engine)
    if not inspector.has_table("documents"):
        print("Table 'documents' does not exist yet. Skipping column addition.")
        return

    columns = [col["name"] for col in inspector.get_columns("documents")]
    if "project_token" in columns:
        print("Column 'project_token' already exists. Skipping.")
        return

    with engine.connect() as conn:
        conn.execute(
            text("ALTER TABLE documents ADD COLUMN project_token VARCHAR NULL")
        )
        conn.execute(
            text("CREATE INDEX IF NOT EXISTS ix_documents_project_token ON documents (project_token)")
        )
        conn.commit()
        print("✅ Added 'project_token' column with index to 'documents' table.")


def downgrade():
    """Remove project_token column."""
    with engine.connect() as conn:
        conn.execute(text("DROP INDEX IF EXISTS ix_documents_project_token"))
        conn.execute(text("ALTER TABLE documents DROP COLUMN project_token"))
        conn.commit()
        print("Removed 'project_token' column from 'documents' table.")


if __name__ == "__main__":
    upgrade()
