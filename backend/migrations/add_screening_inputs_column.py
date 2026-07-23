"""
Migration: Add screening_inputs JSON column to the documents table.

Stores the raw requirement screening inputs separately (uploaded_files,
linked_documents, manual_text, url_content, repository_context, skills_files)
so each input type is individually queryable and survives browser storage loss.
"""

import sys
import os

# Add parent dir to path so we can import from project
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import engine
from sqlalchemy import inspect, text


def upgrade():
    """Add screening_inputs column to documents table."""
    inspector = inspect(engine)
    if not inspector.has_table("documents"):
        print("Table 'documents' does not exist yet. Skipping column addition.")
        return

    columns = [col["name"] for col in inspector.get_columns("documents")]
    if "screening_inputs" in columns:
        print("Column 'screening_inputs' already exists in 'documents' table. Skipping.")
        return

    with engine.connect() as conn:
        conn.execute(
            text("ALTER TABLE documents ADD COLUMN screening_inputs JSON NULL")
        )
        conn.commit()
        print("Successfully added 'screening_inputs' column to 'documents' table.")


def downgrade():
    """Remove screening_inputs column from documents table."""
    with engine.connect() as conn:
        conn.execute(
            text("ALTER TABLE documents DROP COLUMN screening_inputs")
        )
        conn.commit()
        print("Successfully removed 'screening_inputs' column from 'documents' table.")


if __name__ == "__main__":
    upgrade()
