"""
Migration script for Agent Subtypes.
1. Adds missing columns to organization_agent_quotas and organization_agent_mappings.
2. Backfills subtype quotas (100 dev / 40 test ratio).
3. Updates existing mappings to 'dev' subtype.
"""
import sqlite3
import os

DB_PATH = 'sql_app.db'
DEV_RATIO = 100 / 140

def migrate():
    if not os.path.exists(DB_PATH):
        print(f"Database not found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 1. Add columns to organization_agent_quotas
    cursor.execute("PRAGMA table_info(organization_agent_quotas)")
    quota_cols = [row[1] for row in cursor.fetchall()]
    
    new_quota_cols = [
        ('dedicated_dev_quota', 'INTEGER DEFAULT 0'),
        ('dedicated_test_quota', 'INTEGER DEFAULT 0'),
        ('shared_dev_quota', 'INTEGER DEFAULT 0'),
        ('shared_test_quota', 'INTEGER DEFAULT 0'),
        ('dedicated_dev_used', 'INTEGER DEFAULT 0'),
        ('dedicated_test_used', 'INTEGER DEFAULT 0'),
        ('shared_dev_used', 'INTEGER DEFAULT 0'),
        ('shared_test_used', 'INTEGER DEFAULT 0')
    ]

    for col_name, col_def in new_quota_cols:
        if col_name not in quota_cols:
            print(f"Adding {col_name} to organization_agent_quotas...")
            cursor.execute(f"ALTER TABLE organization_agent_quotas ADD COLUMN {col_name} {col_def}")
    
    # 2. Add column to organization_agent_mappings
    cursor.execute("PRAGMA table_info(organization_agent_mappings)")
    mapping_cols = [row[1] for row in cursor.fetchall()]

    if 'agent_sub_type' not in mapping_cols:
        print("Adding agent_sub_type to organization_agent_mappings...")
        cursor.execute("ALTER TABLE organization_agent_mappings ADD COLUMN agent_sub_type VARCHAR DEFAULT 'dev'")

    # 3. Backfill Quotas
    print("Backfilling subtype quotas...")
    cursor.execute("SELECT id, organization_name, shared_quota, dedicated_quota, shared_dev_quota, shared_test_quota, dedicated_dev_quota, dedicated_test_quota FROM organization_agent_quotas")
    rows = cursor.fetchall()
    
    for row in rows:
        qid, org, sh_total, ded_total, sh_dev, sh_test, ded_dev, ded_test = row
        
        updates = []
        # Dedicated split
        if (ded_total or 0) > 0 and (ded_dev or 0) == 0 and (ded_test or 0) == 0:
            dev = round(ded_total * DEV_RATIO)
            test = ded_total - dev
            updates.append(("dedicated_dev_quota", dev))
            updates.append(("dedicated_test_quota", test))
            print(f"[{org}] Dedicated {ded_total} -> Dev {dev}, Test {test}")
            
        # Shared split
        if (sh_total or 0) > 0 and (sh_dev or 0) == 0 and (sh_test or 0) == 0:
            dev = round(sh_total * DEV_RATIO)
            test = sh_total - dev
            updates.append(("shared_dev_quota", dev))
            updates.append(("shared_test_quota", test))
            print(f"[{org}] Shared {sh_total} -> Dev {dev}, Test {test}")
            
        if updates:
            set_clause = ", ".join([f"{col} = ?" for col, val in updates])
            params = [val for col, val in updates] + [qid]
            cursor.execute(f"UPDATE organization_agent_quotas SET {set_clause} WHERE id = ?", params)

    # 4. Update Mappings
    print("Ensuring all mappings have a sub_type...")
    cursor.execute("UPDATE organization_agent_mappings SET agent_sub_type = 'dev' WHERE agent_sub_type IS NULL OR agent_sub_type = ''")

    conn.commit()
    conn.close()
    print("\nMigration completed successfully.")

if __name__ == "__main__":
    migrate()
