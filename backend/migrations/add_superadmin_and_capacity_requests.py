"""
Migration: Add Super Admin and Capacity Increase Request tracking columns and tables.

This migration script updates:
1. 'users' table: adds 'is_super_admin' column.
2. 'organization_agent_quotas' table: adds 'max_agent_capacity' column.
3. 'organization_agent_mappings' table: adds 'home_project_token', 'current_borrowed_project_token', and 'is_borrowed' columns.
4. Creates 'capacity_increase_requests' table.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from database import engine

def upgrade():
    """Apply schema updates"""
    with engine.connect() as conn:
        print("Starting migration: Super Admin & Capacity Management Schema Updates...")

        # 1. Add is_super_admin column to users table
        try:
            cursor = conn.execute(text("PRAGMA table_info(users)"))
            user_cols = [row[1] for row in cursor.fetchall()]
            if "is_super_admin" not in user_cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN is_super_admin BOOLEAN DEFAULT 0"))
                conn.commit()
                print("[OK] Added 'is_super_admin' column to 'users' table.")
            else:
                print("[INFO] 'is_super_admin' column already exists in 'users' table.")
        except Exception as e:
            print(f"[WARNING] Error updating 'users' table: {e}")

        # 2. Add max_agent_capacity column to organization_agent_quotas table
        try:
            cursor = conn.execute(text("PRAGMA table_info(organization_agent_quotas)"))
            quota_cols = [row[1] for row in cursor.fetchall()]
            if quota_cols and "max_agent_capacity" not in quota_cols:
                conn.execute(text("ALTER TABLE organization_agent_quotas ADD COLUMN max_agent_capacity INTEGER DEFAULT 10"))
                conn.commit()
                print("[OK] Added 'max_agent_capacity' column to 'organization_agent_quotas' table.")
            else:
                print("[INFO] 'max_agent_capacity' column already present or table not initialized yet.")
        except Exception as e:
            print(f"[WARNING] Error updating 'organization_agent_quotas' table: {e}")

        # 3. Add borrowing columns to organization_agent_mappings table
        try:
            cursor = conn.execute(text("PRAGMA table_info(organization_agent_mappings)"))
            mapping_cols = [row[1] for row in cursor.fetchall()]
            if mapping_cols:
                if "home_project_token" not in mapping_cols:
                    conn.execute(text("ALTER TABLE organization_agent_mappings ADD COLUMN home_project_token VARCHAR"))
                    print("[OK] Added 'home_project_token' column to 'organization_agent_mappings' table.")
                if "current_borrowed_project_token" not in mapping_cols:
                    conn.execute(text("ALTER TABLE organization_agent_mappings ADD COLUMN current_borrowed_project_token VARCHAR"))
                    print("[OK] Added 'current_borrowed_project_token' column to 'organization_agent_mappings' table.")
                if "is_borrowed" not in mapping_cols:
                    conn.execute(text("ALTER TABLE organization_agent_mappings ADD COLUMN is_borrowed BOOLEAN DEFAULT 0"))
                    print("[OK] Added 'is_borrowed' column to 'organization_agent_mappings' table.")
                conn.commit()
        except Exception as e:
            print(f"[WARNING] Error updating 'organization_agent_mappings' table: {e}")

        # 4. Create capacity_increase_requests table
        try:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS capacity_increase_requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    organization_name VARCHAR NOT NULL,
                    requested_by_user_id INTEGER NOT NULL,
                    project_token VARCHAR,
                    requested_shared_count INTEGER DEFAULT 0,
                    requested_dedicated_count INTEGER DEFAULT 0,
                    total_requested_increase INTEGER DEFAULT 0,
                    reason TEXT,
                    status VARCHAR DEFAULT 'PENDING',
                    approved_total_capacity INTEGER,
                    reviewed_by_user_id INTEGER,
                    review_comment TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (requested_by_user_id) REFERENCES users(id),
                    FOREIGN KEY (reviewed_by_user_id) REFERENCES users(id)
                )
            """))
            conn.commit()
            print("[OK] Created 'capacity_increase_requests' table.")
        except Exception as e:
            if "already exists" in str(e).lower():
                print("[INFO] 'capacity_increase_requests' table already exists.")
            else:
                raise

        # Create indexes for capacity_increase_requests
        for index_name, col in [
            ("ix_capacity_req_org", "organization_name"),
            ("ix_capacity_req_status", "status"),
            ("ix_capacity_req_user", "requested_by_user_id")
        ]:
            try:
                conn.execute(text(f"CREATE INDEX IF NOT EXISTS {index_name} ON capacity_increase_requests({col})"))
                conn.commit()
                print(f"[OK] Created index on '{col}'")
            except Exception as e:
                print(f"[WARNING] Error creating index on '{col}': {e}")

def downgrade():
    """Downgrade schema"""
    with engine.connect() as conn:
        try:
            conn.execute(text("DROP TABLE IF EXISTS capacity_increase_requests"))
            conn.commit()
            print("[OK] Removed 'capacity_increase_requests' table.")
        except Exception as e:
            print(f"[WARNING] Error removing table: {e}")

if __name__ == "__main__":
    print("=" * 60)
    print("Running migration: Add Super Admin & Capacity Management Schema")
    print("=" * 60)
    try:
        upgrade()
        print("[SUCCESS] Migration completed successfully!")
    except Exception as e:
        print(f"[ERROR] Migration failed: {e}")
        raise
