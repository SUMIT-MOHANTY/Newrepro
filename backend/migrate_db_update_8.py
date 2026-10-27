"""
Migration: Add ai_usage_logs and user_activity_logs tables
 
This migration adds tables for tracking AI model costs and detailed user activity audit trails.
"""
from sqlalchemy import text
from database import engine
 
def upgrade():
    """Create logs tables"""
    with engine.connect() as conn:
        # 1. Create ai_usage_logs table
        try:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS ai_usage_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    project_token VARCHAR,
                    model VARCHAR,
                    prompt_tokens INTEGER DEFAULT 0,
                    completion_tokens INTEGER DEFAULT 0,
                    cost FLOAT DEFAULT 0.0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            """))
            conn.commit()
            print("✓ Created ai_usage_logs table")
        except Exception as e:
            if "already exists" in str(e).lower():
                print("⚠ ai_usage_logs table already exists")
            else:
                raise
       
        # Create indexes for ai_usage_logs
        for index_name, col in [("ix_ai_usage_logs_user_id", "user_id"),
                               ("ix_ai_usage_logs_project_token", "project_token"),
                               ("ix_ai_usage_logs_created_at", "created_at")]:
            try:
                conn.execute(text(f"CREATE INDEX IF NOT EXISTS {index_name} ON ai_usage_logs({col})"))
                conn.commit()
                print(f"✓ Created index on {col}")
            except Exception as e:
                print(f"⚠ Error creating index on {col}: {e}")
 
        # 2. Create user_activity_logs table
        try:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS user_activity_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    action VARCHAR NOT NULL,
                    method VARCHAR,
                    path VARCHAR,
                    ip_address VARCHAR,
                    user_agent VARCHAR,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
            """))
            conn.commit()
            print("✓ Created user_activity_logs table")
        except Exception as e:
            if "already exists" in str(e).lower():
                print("⚠ user_activity_logs table already exists")
            else:
                raise
 
        # Create indexes for user_activity_logs
        for index_name, col in [("ix_user_activity_logs_user_id", "user_id"),
                               ("ix_user_activity_logs_created_at", "created_at")]:
            try:
                conn.execute(text(f"CREATE INDEX IF NOT EXISTS {index_name} ON user_activity_logs({col})"))
                conn.commit()
                print(f"✓ Created index on {col}")
            except Exception as e:
                print(f"⚠ Error creating index on {col}: {e}")
 
def downgrade():
    """Remove tables"""
    with engine.connect() as conn:
        try:
            conn.execute(text("DROP TABLE IF EXISTS ai_usage_logs"))
            conn.commit()
            print("✓ Removed ai_usage_logs table")
        except Exception as e:
            print(f"⚠ Error removing ai_usage_logs table: {e}")
           
        try:
            conn.execute(text("DROP TABLE IF EXISTS user_activity_logs"))
            conn.commit()
            print("✓ Removed user_activity_logs table")
        except Exception as e:
            print(f"⚠ Error removing user_activity_logs table: {e}")
 
if __name__ == "__main__":
    print("=" * 60)
    print("Running migration: Add ai_usage_logs and user_activity_logs tables")
    print("=" * 60)
    try:
        upgrade()
        print("✅ Migration completed successfully!")
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        raise
