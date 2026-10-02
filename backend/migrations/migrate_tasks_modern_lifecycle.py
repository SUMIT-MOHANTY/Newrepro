"""
Migration: Add modern task lifecycle columns to tasks table
Adds status, assigned_agent_role, assigned_agent_id, verification_status,
files_modified, execution_logs, and error_details to the tasks table.
"""
import sys
import os

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from sqlalchemy import inspect, text
from app.core.database import engine

def migrate():
    inspector = inspect(engine)
    columns = [col['name'] for col in inspector.get_columns('tasks')]
    
    new_columns = [
        ("status", "VARCHAR(32) DEFAULT 'TODO'"),
        ("assigned_agent_role", "VARCHAR(64)"),
        ("assigned_agent_id", "VARCHAR(64)"),
        ("verification_status", "VARCHAR(32) DEFAULT 'PENDING'"),
        ("files_modified", "TEXT DEFAULT '[]'"),
        ("execution_logs", "TEXT"),
        ("error_details", "TEXT"),
    ]
    
    with engine.connect() as conn:
        for col_name, col_type in new_columns:
            if col_name not in columns:
                print(f"Adding column '{col_name}' to tasks table...")
                conn.execute(text(f"ALTER TABLE tasks ADD COLUMN {col_name} {col_type}"))
                conn.commit()
                print(f"[OK] Added '{col_name}'")
            else:
                print(f"Column '{col_name}' already exists.")
                
    print("Tasks table migration completed successfully!")

if __name__ == "__main__":
    migrate()
