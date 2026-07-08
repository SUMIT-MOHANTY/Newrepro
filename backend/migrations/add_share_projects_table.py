"""
Migration script to add share_projects table and update shared_documents table
"""
from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, DateTime, text
from sqlalchemy.orm import sessionmaker
from database import SQLALCHEMY_DATABASE_URL
from datetime import datetime

def migrate():
    engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
    
    with engine.connect() as conn:
        # Create share_projects table
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS share_projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_token VARCHAR UNIQUE NOT NULL,
                owner_id INTEGER NOT NULL,
                project_name VARCHAR NOT NULL,
                description VARCHAR DEFAULT 'Shared Documents',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (owner_id) REFERENCES users(id)
            )
        """))
        
        # Create indexes
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_share_projects_project_token 
            ON share_projects(project_token)
        """))
        
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_share_projects_owner_id 
            ON share_projects(owner_id)
        """))
        
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_share_projects_created_at 
            ON share_projects(created_at)
        """))
        
        # Add share_project_id column to shared_documents if it doesn't exist
        try:
            conn.execute(text("""
                ALTER TABLE shared_documents 
                ADD COLUMN share_project_id INTEGER REFERENCES share_projects(id)
            """))
            print("✓ Added share_project_id column to shared_documents")
        except Exception as e:
            if "duplicate column name" in str(e).lower():
                print("✓ share_project_id column already exists in shared_documents")
            else:
                print(f"⚠ Warning adding share_project_id column: {e}")
        
        # Create index for share_project_id
        try:
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_shared_documents_share_project_id 
                ON shared_documents(share_project_id)
            """))
            print("✓ Created index on share_project_id")
        except Exception as e:
            print(f"⚠ Warning creating index: {e}")
        
        conn.commit()
        print("✓ Migration completed successfully!")

if __name__ == "__main__":
    migrate()
