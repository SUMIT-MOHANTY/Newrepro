"""
Migration: Add multi-organization and project relationships

This migration adds:
1. 'organization_name' column to 'governance_responses' table (Project & Org 1:1 mapping).
2. 'user_project_associations' table (User & Project M:M mapping).
"""
from sqlalchemy import text
from database import engine

def upgrade():
    """Apply migrations"""
    with engine.connect() as conn:
        # 1. Add organization_name to governance_responses
        try:
            conn.execute(text("""
                ALTER TABLE governance_responses
                ADD COLUMN organization_name VARCHAR
            """))
            conn.commit()
            print("✓ Added organization_name column to governance_responses table")
        except Exception as e:
            if "duplicate column name" in str(e).lower() or "already exists" in str(e).lower():
                print("⚠ organization_name column already exists in governance_responses")
            else:
                raise

        # 2. Backfill organization_name in governance_responses from owner's organization
        try:
            result = conn.execute(text("""
                UPDATE governance_responses
                SET organization_name = (
                    SELECT organization_name FROM users WHERE users.id = governance_responses.owner_id
                )
                WHERE organization_name IS NULL OR organization_name = ''
            """))
            conn.commit()
            print(f"✓ Backfilled organization_name for {result.rowcount} existing projects")
        except Exception as e:
            print(f"⚠ Error backfilling organization_name: {e}")

        # 3. Create user_project_associations table
        try:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS user_project_associations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    project_token VARCHAR NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    CONSTRAINT uq_user_project_assoc UNIQUE (user_id, project_token),
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY(project_token) REFERENCES governance_responses(project_token) ON DELETE CASCADE
                )
            """))
            conn.commit()
            print("✓ Created user_project_associations table")
        except Exception as e:
            print(f"⚠ Error creating user_project_associations table: {e}")
            raise

        # 4. Populate associations with existing project ownership so current users don't lose access to their projects
        try:
            result = conn.execute(text("""
                INSERT OR IGNORE INTO user_project_associations (user_id, project_token)
                SELECT owner_id, project_token FROM governance_responses WHERE owner_id IS NOT NULL AND project_token IS NOT NULL
            """))
            conn.commit()
            print(f"✓ Associated {result.rowcount} owners with their respective projects in user_project_associations")
        except Exception as e:
            print(f"⚠ Error backfilling project ownership associations: {e}")

def downgrade():
    """Revert migrations"""
    with engine.connect() as conn:
        # Drop user_project_associations table
        try:
            conn.execute(text("DROP TABLE IF EXISTS user_project_associations"))
            conn.commit()
            print("✓ Dropped user_project_associations table")
        except Exception as e:
            print(f"⚠ Error dropping user_project_associations: {e}")

        # Remove organization_name column
        try:
            conn.execute(text("ALTER TABLE governance_responses DROP COLUMN organization_name"))
            conn.commit()
            print("✓ Removed organization_name column from governance_responses table")
        except Exception as e:
            print(f"⚠ Error removing organization_name column: {e}")

if __name__ == "__main__":
    print("=" * 60)
    print("Running migration: Add multi-organization and project relationships")
    print("=" * 60)
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
