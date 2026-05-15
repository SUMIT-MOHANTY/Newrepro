"""
Migration: Add share BRD tables for document sharing functionality

This migration adds tables to support sharing BRD documents with external users
via secure links with configurable access controls and email notifications.
"""
from sqlalchemy import text
from database import engine


def upgrade():
    """Create share BRD tables"""
    with engine.connect() as conn:
        # Create shared_documents table
        try:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS shared_documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    share_token TEXT UNIQUE NOT NULL,
                    user_id INTEGER NOT NULL,
                    title TEXT,
                    access_type TEXT DEFAULT 'once',
                    expiration_time TEXT,
                    expires_at TIMESTAMP,
                    require_password BOOLEAN DEFAULT 0,
                    password_hash TEXT,
                    access_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            """))
            conn.commit()
            print("✓ Created shared_documents table")
        except Exception as e:
            if "already exists" in str(e).lower():
                print("⚠ shared_documents table already exists")
            else:
                raise
        
        # Create shared_document_files table
        try:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS shared_document_files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    share_id INTEGER NOT NULL,
                    filename TEXT NOT NULL,
                    original_filename TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    file_size INTEGER,
                    file_type TEXT,
                    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (share_id) REFERENCES shared_documents(id) ON DELETE CASCADE
                )
            """))
            conn.commit()
            print("✓ Created shared_document_files table")
        except Exception as e:
            if "already exists" in str(e).lower():
                print("⚠ shared_document_files table already exists")
            else:
                raise
        
        # Create shared_document_recipients table
        try:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS shared_document_recipients (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    share_id INTEGER NOT NULL,
                    email TEXT NOT NULL,
                    notified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (share_id) REFERENCES shared_documents(id) ON DELETE CASCADE
                )
            """))
            conn.commit()
            print("✓ Created shared_document_recipients table")
        except Exception as e:
            if "already exists" in str(e).lower():
                print("⚠ shared_document_recipients table already exists")
            else:
                raise
        
        # Create shared_document_access_log table
        try:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS shared_document_access_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    share_id INTEGER NOT NULL,
                    accessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    ip_address TEXT,
                    user_agent TEXT,
                    FOREIGN KEY (share_id) REFERENCES shared_documents(id) ON DELETE CASCADE
                )
            """))
            conn.commit()
            print("✓ Created shared_document_access_log table")
        except Exception as e:
            if "already exists" in str(e).lower():
                print("⚠ shared_document_access_log table already exists")
            else:
                raise
        
        # Create indexes for better query performance
        try:
            conn.execute(text("""
                CREATE UNIQUE INDEX IF NOT EXISTS ix_shared_documents_share_token 
                ON shared_documents(share_token)
            """))
            conn.commit()
            print("✓ Created unique index on share_token")
        except Exception as e:
            print(f"⚠ Error creating share_token index: {e}")
        
        try:
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_shared_documents_user_id 
                ON shared_documents(user_id)
            """))
            conn.commit()
            print("✓ Created index on user_id")
        except Exception as e:
            print(f"⚠ Error creating user_id index: {e}")
        
        try:
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_shared_documents_expires_at 
                ON shared_documents(expires_at)
            """))
            conn.commit()
            print("✓ Created index on expires_at")
        except Exception as e:
            print(f"⚠ Error creating expires_at index: {e}")
        
        try:
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_shared_document_files_share_id 
                ON shared_document_files(share_id)
            """))
            conn.commit()
            print("✓ Created index on shared_document_files.share_id")
        except Exception as e:
            print(f"⚠ Error creating files share_id index: {e}")
        
        try:
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_shared_document_recipients_share_id 
                ON shared_document_recipients(share_id)
            """))
            conn.commit()
            print("✓ Created index on shared_document_recipients.share_id")
        except Exception as e:
            print(f"⚠ Error creating recipients share_id index: {e}")
        
        try:
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_shared_document_access_log_share_id 
                ON shared_document_access_log(share_id)
            """))
            conn.commit()
            print("✓ Created index on shared_document_access_log.share_id")
        except Exception as e:
            print(f"⚠ Error creating access_log share_id index: {e}")
        
        try:
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_shared_document_access_log_accessed_at 
                ON shared_document_access_log(accessed_at)
            """))
            conn.commit()
            print("✓ Created index on accessed_at")
        except Exception as e:
            print(f"⚠ Error creating accessed_at index: {e}")


def downgrade():
    """Remove share BRD tables"""
    with engine.connect() as conn:
        # Drop tables in reverse order due to foreign key constraints
        tables = [
            "shared_document_access_log",
            "shared_document_recipients", 
            "shared_document_files",
            "shared_documents"
        ]
        
        for table in tables:
            try:
                conn.execute(text(f"DROP TABLE IF EXISTS {table}"))
                conn.commit()
                print(f"✓ Removed {table} table")
            except Exception as e:
                print(f"⚠ Error removing {table} table: {e}")


if __name__ == "__main__":
    print("=" * 60)
    print("Running migration: Add share BRD tables")
    print("=" * 60)
    print()
    print("This migration adds document sharing functionality:")
    print("  • shared_documents - Main sharing configuration")
    print("  • shared_document_files - Files associated with shares")
    print("  • shared_document_recipients - Email recipients")
    print("  • shared_document_access_log - Access tracking")
    print()
    print("Features:")
    print("  • Secure token-based sharing")
    print("  • Configurable access controls (once/always)")
    print("  • Password protection")
    print("  • Expiration dates")
    print("  • Email notifications")
    print("  • Access logging and analytics")
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