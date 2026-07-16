"""
Reset all tasks for Testing 3 project (token: 4847e1af-721e-40af-adc9-b69aa4c15ba6)
to idle/pending status with 0 progress so agents can re-pick and re-run them.
"""
import json, sqlite3, os

PROJECT_TOKEN = "4847e1af-721e-40af-adc9-b69aa4c15ba6"
db_path = os.path.join(os.path.dirname(__file__), "sql_app.db")

if not os.path.exists(db_path):
    print(f"❌ DB not found: {db_path}")
    exit(1)

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

print(f"📡 Resetting tasks for project: {PROJECT_TOKEN}")

# ---- 0. Check which columns exist ----
cur.execute("PRAGMA table_info(agent_task_ownerships)")
ownership_cols = [c["name"] for c in cur.fetchall()]
print(f"\n📋 agent_task_ownerships columns: {ownership_cols}")

# Build SELECT dynamically
select_cols = ["id", "task_id", "status", "agent_id"]
for c in ["progress"]:
    if c in ownership_cols:
        select_cols.append(c)

# ---- 1. Show current state ----
cur.execute(
    f"SELECT {', '.join(select_cols)} FROM agent_task_ownerships WHERE project_token=?",
    (PROJECT_TOKEN,)
)
rows = cur.fetchall()
print(f"\n📋 Current ({len(rows)} records):")
for r in rows:
    tid = (r["task_id"] or "")[-40:]
    aid = (r["agent_id"] or "")[:32]
    prog = f" progress={r.get('progress','?')}" if "progress" in select_cols else ""
    print(f"   {r['id']:4d}  ..{tid:38s}  →  {aid:32s}  [{r['status']:10s}]{prog}")

# ---- 2. Reset agent_task_ownerships ----
set_clauses = ["status='pending'"]

# Clear all completion/state columns to make tasks truly fresh
null_cols = ["claimed_at", "started_at", "completed_at", "branch_name", "files_written", "error_message"]
for col in null_cols:
    if col in ownership_cols:
        set_clauses.append(f"{col}=NULL")

# Set progress to 0 if column exists
if "progress" in ownership_cols:
    set_clauses.append("progress=0")

# Also reset task_progress inside the task_data JSON column
if "task_data" in ownership_cols:
    # Fetch current task_data to update its task_progress
    cur.execute(
        "SELECT id, task_data FROM agent_task_ownerships WHERE project_token=?",
        (PROJECT_TOKEN,)
    )
    task_data_rows = cur.fetchall()
    updated_json = 0
    for trow in task_data_rows:
        td_raw = trow["task_data"]
        if td_raw:
            try:
                td = json.loads(td_raw) if isinstance(td_raw, str) else td_raw
                if isinstance(td, dict) and td.get("task_progress") is not None:
                    td["task_progress"] = 0
                    cur.execute(
                        "UPDATE agent_task_ownerships SET task_data=? WHERE id=?",
                        (json.dumps(td), trow["id"])
                    )
                    updated_json += 1
            except (json.JSONDecodeError, TypeError):
                pass

cur.execute(
    f"UPDATE agent_task_ownerships SET {', '.join(set_clauses)} WHERE project_token=?",
    (PROJECT_TOKEN,)
)
nulled = [c for c in null_cols if c in ownership_cols]
print(f"\n✅ Reset {cur.rowcount} agent_task_ownerships → pending, cleared: {nulled}" + (" + progress=0" if "progress" in ownership_cols else ""))
if "task_data" in ownership_cols:
    print(f"✅ Cleared task_progress in {updated_json} task_data JSON records")

# ---- 3. Also reset the tasks table ----
try:
    cur.execute("PRAGMA table_info(tasks)")
    task_cols = [c["name"] for c in cur.fetchall()]
    print(f"\n📋 tasks columns: {task_cols}")

    set_clauses2 = ["status='pending'"]
    if "progress" in task_cols:
        set_clauses2.append("progress=0")

    cur.execute(
        f"UPDATE tasks SET {', '.join(set_clauses2)} WHERE project_token=?",
        (PROJECT_TOKEN,)
    )
    print(f"✅ Reset {cur.rowcount} tasks → pending" + (" + progress=0" if "progress" in task_cols else ""))
except Exception as e:
    print(f"⚠️  Could not update tasks table: {e}")

conn.commit()
conn.close()

print(f"\n🎉 Done! Now restart the backend server so in-memory state clears.")
