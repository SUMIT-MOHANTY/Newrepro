"""
Migration: Update share tables for anonymous access and individual tokens

This migration:
1. Adds allow_anonymous to shared_documents
2. Adds share_token and access_level to shared_document_recipients
"""
from sqlalchemy import text
from database import engine

def upgrade():
    with engine.connect() as conn:
        # 1. Add allow_anonymous to shared_documents
        try:
            conn.execute(text("ALTER TABLE shared_documents ADD COLUMN allow_anonymous BOOLEAN DEFAULT 1"))
            conn.commit()
            print("✓ Added allow_anonymous to shared_documents")
        except Exception as e:
            if "duplicate column name" in str(e).lower() or "already exists" in str(e).lower():
                print("⚠ allow_anonymous column already exists")
            else:
                print(f"⚠ Error adding allow_anonymous: {e}")

        # 2. Add share_token to shared_document_recipients
        try:
            conn.execute(text("ALTER TABLE shared_document_recipients ADD COLUMN share_token TEXT"))
            conn.commit()
            print("✓ Added share_token to shared_document_recipients")
        except Exception as e:
            if "duplicate column name" in str(e).lower() or "already exists" in str(e).lower():
                print("⚠ share_token column already exists")
            else:
                print(f"⚠ Error adding share_token: {e}")

        # 3. Add access_level to shared_document_recipients
        try:
            conn.execute(text("ALTER TABLE shared_document_recipients ADD COLUMN access_level TEXT DEFAULT 'view'"))
            conn.commit()
            print("✓ Added access_level to shared_document_recipients")
        except Exception as e:
            if "duplicate column name" in str(e).lower() or "already exists" in str(e).lower():
                print("⚠ access_level column already exists")
            else:
                print(f"⚠ Error adding access_level: {e}")

        # Create unique index on recipients share_token
        try:
            conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_shared_document_recipients_share_token ON shared_document_recipients(share_token)"))
            conn.commit()
            print("✓ Created unique index on recipients share_token")
        except Exception as e:
            print(f"⚠ Error creating index on recipients share_token: {e}")

if __name__ == "__main__":
    upgrade()
