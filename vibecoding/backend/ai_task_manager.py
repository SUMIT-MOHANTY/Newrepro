"""
AI Task Manager - Handles long-running AI requests with polling support
"""
import asyncio
import json
import sqlite3
import uuid
from datetime import datetime
from typing import Optional, Dict, Any
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

class AITaskManager:
    def __init__(self, db_path: str = "vibecoding_users.db"):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """Initialize the AI tasks table if it doesn't exist"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ai_tasks (
                task_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                user_id TEXT,
                request_type TEXT NOT NULL,
                request_data TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                result TEXT,
                error TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP
            )
        """)
        
        # Create index for faster lookups
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_ai_tasks_project_id 
            ON ai_tasks(project_id)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_ai_tasks_status 
            ON ai_tasks(status)
        """)
        
        conn.commit()
        conn.close()
    
    def create_task(
        self, 
        project_id: str, 
        request_type: str, 
        request_data: Dict[Any, Any],
        user_id: Optional[str] = None
    ) -> str:
        """Create a new AI task and return the task ID"""
        task_id = str(uuid.uuid4())
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO ai_tasks (task_id, project_id, user_id, request_type, request_data, status)
            VALUES (?, ?, ?, ?, ?, 'pending')
        """, (task_id, project_id, user_id, request_type, json.dumps(request_data)))
        
        conn.commit()
        conn.close()
        
        logger.info(f"Created AI task {task_id} for project {project_id}")
        return task_id
    
    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get task status and result"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT task_id, project_id, user_id, request_type, status, result, error, 
                   created_at, updated_at, completed_at
            FROM ai_tasks
            WHERE task_id = ?
        """, (task_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return None
        
        task = dict(row)
        
        # Parse JSON result if present
        if task['result']:
            try:
                task['result'] = json.loads(task['result'])
            except json.JSONDecodeError:
                pass
        
        return task
    
    def update_task_status(self, task_id: str, status: str):
        """Update task status (pending, processing, completed, failed)"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE ai_tasks 
            SET status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE task_id = ?
        """, (status, task_id))
        
        conn.commit()
        conn.close()
        
        logger.info(f"Updated task {task_id} status to {status}")
    
    def complete_task(self, task_id: str, result: Dict[Any, Any]):
        """Mark task as completed with result"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE ai_tasks 
            SET status = 'completed', 
                result = ?,
                updated_at = CURRENT_TIMESTAMP,
                completed_at = CURRENT_TIMESTAMP
            WHERE task_id = ?
        """, (json.dumps(result), task_id))
        
        conn.commit()
        conn.close()
        
        logger.info(f"Completed task {task_id}")
    
    def fail_task(self, task_id: str, error: str):
        """Mark task as failed with error message"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE ai_tasks 
            SET status = 'failed', 
                error = ?,
                updated_at = CURRENT_TIMESTAMP,
                completed_at = CURRENT_TIMESTAMP
            WHERE task_id = ?
        """, (error, task_id))
        
        conn.commit()
        conn.close()
        
        logger.error(f"Failed task {task_id}: {error}")
    
    def cleanup_old_tasks(self, days: int = 7):
        """Clean up tasks older than specified days"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            DELETE FROM ai_tasks 
            WHERE created_at < datetime('now', '-' || ? || ' days')
        """, (days,))
        
        deleted = cursor.rowcount
        conn.commit()
        conn.close()
        
        logger.info(f"Cleaned up {deleted} old AI tasks")
        return deleted
    
    def get_project_tasks(self, project_id: str, limit: int = 10) -> list:
        """Get recent tasks for a project"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT task_id, request_type, status, created_at, completed_at
            FROM ai_tasks
            WHERE project_id = ?
            ORDER BY created_at DESC
            LIMIT ?
        """, (project_id, limit))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]


# Global instance
ai_task_manager = AITaskManager()
