import sqlite3
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def migrate():
    """Add bootstrap_branch column to bootstrap_states table"""
    # Using the same database name as in other migration scripts
    conn = sqlite3.connect('sql_app.db')
    cursor = conn.cursor()
    
    try:
        # Check if column exists
        cursor.execute("PRAGMA table_info(bootstrap_states)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if 'bootstrap_branch' not in columns:
            logger.info("Adding bootstrap_branch column...")
            cursor.execute("ALTER TABLE bootstrap_states ADD COLUMN bootstrap_branch VARCHAR")
            conn.commit()
            logger.info("✅ Successfully added bootstrap_branch column to bootstrap_states table")
        else:
            logger.info("✅ Column bootstrap_branch already exists")
            
    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
