"""
Migration script to add tasks table for local task storage
"""
import sqlite3
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def migrate():
    """Add tasks table to database"""
    conn = sqlite3.connect('sql_app.db')
    cursor = conn.cursor()
    
    try:
        # Check if table exists
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='tasks'
        """)
        
        if cursor.fetchone():
            logger.info("Tasks table already exists")
            return
        
        # Create tasks table
        cursor.execute("""
            CREATE TABLE tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id VARCHAR UNIQUE NOT NULL,
                project_token VARCHAR NOT NULL,
                owner_id INTEGER NOT NULL,
                task_name VARCHAR NOT NULL,
                task_type VARCHAR NOT NULL,
                description TEXT,
                priority VARCHAR DEFAULT 'medium',
                task_wallet INTEGER DEFAULT 1,
                startdate VARCHAR,
                planned_start VARCHAR,
                deadline VARCHAR,
                assigned_to TEXT,
                reported_by VARCHAR DEFAULT 'system',
                sprint VARCHAR DEFAULT 'new',
                milestone VARCHAR DEFAULT 'main',
                linked_tasks TEXT,
                checklist TEXT,
                synced_to_nxdune BOOLEAN DEFAULT 0,
                nxdune_task_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (owner_id) REFERENCES users(id)
            )
        """)
        
        # Create indexes
        cursor.execute("CREATE INDEX ix_tasks_task_id ON tasks(task_id)")
        cursor.execute("CREATE INDEX ix_tasks_project_token ON tasks(project_token)")
        cursor.execute("CREATE INDEX ix_tasks_owner_id ON tasks(owner_id)")
        
        conn.commit()
        logger.info("✅ Successfully created tasks table")
        
    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
