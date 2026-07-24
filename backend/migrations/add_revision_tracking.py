"""
Migration: Add revision tracking columns and revisions table.

This migration adds:
1. `revision_version` column to the `documents` table
2. `current_revision_version` column to the `governance_responses` table
3. `revisions` table for tracking revision versions
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text, inspect
from config import settings


def upgrade():
    """Apply migration."""
    import models
    engine = create_engine(settings.database_url)
    models.Base.metadata.create_all(bind=engine)
    inspector = inspect(engine)
    
    with engine.connect() as conn:
        table_names = inspector.get_table_names()
        
        # 1. Add revision_version to documents table
        if "documents" in table_names:
            columns = [col["name"] for col in inspector.get_columns("documents")]
            if "revision_version" not in columns:
                print("Adding 'revision_version' column to 'documents' table...")
                conn.execute(
                    text("ALTER TABLE documents ADD COLUMN revision_version INTEGER NULL")
                )
                print("Successfully added 'revision_version' column.")
            else:
                print("Column 'revision_version' already exists in 'documents' table. Skipping.")
        
        # 2. Add current_revision_version to governance_responses table
        if "governance_responses" in table_names:
            gov_columns = [col["name"] for col in inspector.get_columns("governance_responses")]
            if "current_revision_version" not in gov_columns:
                print("Adding 'current_revision_version' column to 'governance_responses' table...")
                conn.execute(
                    text("ALTER TABLE governance_responses ADD COLUMN current_revision_version INTEGER NOT NULL DEFAULT 1")
                )
                print("Successfully added 'current_revision_version' column.")
            else:
                print("Column 'current_revision_version' already exists in 'governance_responses' table. Skipping.")
        
        # 3. Create revisions table
        table_names = inspector.get_table_names()
        if "revisions" not in table_names:
            print("Creating 'revisions' table...")
            conn.execute(
                text("""
                    CREATE TABLE revisions (
                        id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                        project_token VARCHAR NOT NULL,
                        version_number INTEGER NOT NULL,
                        reason VARCHAR NULL,
                        screening_snapshot JSON NULL,
                        document_snapshots JSON NULL,
                        created_by_user_id INTEGER NULL REFERENCES users(id),
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)
            )
            # Create index on project_token
            conn.execute(
                text("CREATE INDEX ix_revisions_project_token ON revisions (project_token)")
            )
            conn.execute(
                text("CREATE INDEX ix_revisions_created_at ON revisions (created_at)")
            )
            print("Successfully created 'revisions' table.")
        else:
            print("Table 'revisions' already exists. Skipping.")
        
        conn.commit()
        print("Migration completed successfully.")


def downgrade():
    """Rollback migration."""
    engine = create_engine(settings.database_url)
    
    with engine.connect() as conn:
        # 1. Remove revision_version from documents
        conn.execute(text("ALTER TABLE documents DROP COLUMN revision_version"))
        
        # 2. Remove current_revision_version from governance_responses
        conn.execute(text("ALTER TABLE governance_responses DROP COLUMN current_revision_version"))
        
        # 3. Drop revisions table
        conn.execute(text("DROP TABLE IF EXISTS revisions"))
        
        conn.commit()
        print("Downgrade completed successfully.")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "downgrade":
        downgrade()
    else:
        upgrade()
