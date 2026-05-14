"""
Migration: Add chat_messages table for persistent BRD chat history

This migration adds the chat_messages table to store conversation history
between users and the AI for each document analysis.
"""
from sqlalchemy import text
from database import engine


def upgrade():
    """Create chat_messages table"""
    with engine.connect() as conn:
        # Create chat_messages table
        try:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    document_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    role VARCHAR NOT NULL,
                    content TEXT NOT NULL,
                    is_error BOOLEAN DEFAULT 0,
                    is_qa BOOLEAN DEFAULT 0,
                    affected_sections JSON,
                    change_summary TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (document_id) REFERENCES documents(id),
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            """))
            conn.commit()
            print("✓ Created chat_messages table")
        except Exception as e:
            if "already exists" in str(e).lower():
                print("⚠ chat_messages table already exists")
            else:
                raise
        
        # Create indexes for better query performance
        try:
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_chat_messages_document_id 
                ON chat_messages(document_id)
            """))
            conn.commit()
            print("✓ Created index on document_id")
        except Exception as e:
            print(f"⚠ Error creating document_id index: {e}")
        
        try:
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_chat_messages_user_id 
                ON chat_messages(user_id)
            """))
            conn.commit()
            print("✓ Created index on user_id")
        except Exception as e:
            print(f"⚠ Error creating user_id index: {e}")
        
        try:
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_chat_messages_created_at 
                ON chat_messages(created_at)
            """))
            conn.commit()
            print("✓ Created index on created_at")
        except Exception as e:
            print(f"⚠ Error creating created_at index: {e}")


def downgrade():
    """Remove chat_messages table"""
    with engine.connect() as conn:
        try:
            conn.execute(text("DROP TABLE IF EXISTS chat_messages"))
            conn.commit()
            print("✓ Removed chat_messages table")
        except Exception as e:
            print(f"⚠ Error removing table: {e}")


if __name__ == "__main__":
    print("=" * 60)
    print("Running migration: Add chat_messages table")
    print("=" * 60)
    print()
    print("This migration adds persistent chat history for BRD analysis:")
    print("  • chat_messages table - Stores all chat conversations")
    print("  • Indexes on document_id, user_id, created_at")
    print()
    print("Features:")
    print("  • Persistent chat history per document")
    print("  • Track user and assistant messages")
    print("  • Store Q&A submissions and error messages")
    print("  • Track affected sections and change summaries")
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
