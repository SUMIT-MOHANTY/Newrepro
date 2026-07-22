"""
Migration: Add prerequisites_data JSON column to governance_responses table.
This allows persisting user-checked prerequisite checklist items and filled values in the database.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import engine
from sqlalchemy import text, inspect

def run_migration():
    print("Running migration: add_prerequisites_data_column")
    inspector = inspect(engine)
    
    if "governance_responses" in inspector.get_table_names():
        columns = [c["name"] for c in inspector.get_columns("governance_responses")]
        if "prerequisites_data" not in columns:
            print("Adding 'prerequisites_data' column to 'governance_responses' table...")
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE governance_responses ADD COLUMN prerequisites_data JSON NULL"))
                conn.commit()
            print("OK: 'prerequisites_data' column added successfully!")
        else:
            print("OK: 'prerequisites_data' column already exists in 'governance_responses' table.")

if __name__ == "__main__":
    run_migration()
