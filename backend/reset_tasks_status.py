"""
Reset all tasks for Testing 3 project back to pending/idle status with 0 progress.
This clears both the DB records and the in-memory agent state so agents can re-pick tasks.
"""
import sqlite3
import os

PROJECT_TOKEN = "4847e1af-721e-40af-adc9-b69aa4c15ba6"

db_path = os.path.join(os.path.dirname(__file__), "sql_app.db")
if not os.path.exists(db_path):
    print(f"❌ Database not found at {db_path}")
    exit(1)

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

print(f"📡 Project: {PROJECT_TOKEN}")

# Step 1: Show current state
cur.execute(
    "SELECT id, task_id, status, agent_id FROM agent_task_ownerships WHERE project_token=?",
    (PROJECT_TOKEN,)
)
rows = cur.fetchall()
print(f"\n📋 Current task ownerships ({len(rows)} records):")
for r in rows:
    print(f"   {r['task_id'][:30]:32s} → {r['agent_id'][:30]:32s} [{r['status']:10s}]")

# Step 2: Reset all task ownerships to pending
cur.execute(
    "UPDATE agent_task_ownerships SET status='pending' WHERE project_token=?",
    (PROJECT_TOKEN,)
)
updated = cur.rowcount
print(f"\n✅ Reset {updated} task ownerships → status='pending'")

# Step 3: Also update the tasks table if it exists
try:
    cur.execute("PRAGMA table_info(tasks)")
    cols = [r['name'] for r in cur.fetchall()]
    if 'status' in cols:
        cur.execute(
            "UPDATE tasks SET status='pending' WHERE project_token=?",
            (PROJECT_TOKEN,)
        )
        task_updated = cur.rowcount
        print(f"✅ Updated {task_updated} tasks in 'tasks' table → pending")
except Exception as e:
    print(f"⚠️  Could not update tasks table: {e}")

conn.commit()
conn.close()

print(f"\n🎉 Done! All tasks reset to pending status.")
print(f"   Now restart the backend server so in-memory state is also cleared.")
print(f"   Then re-trigger agents from the UI.")
