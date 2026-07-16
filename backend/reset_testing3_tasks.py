"""Reset Testing 3 task ownerships — reset 'done' tasks back to 'claimed' for clean run"""
import sqlite3, os

os.chdir(os.path.dirname(os.path.abspath(__file__)))
conn = sqlite3.connect("sql_app.db")
cur = conn.cursor()

TOKEN = "4847e1af-721e-40af-adc9-b69aa4c15ba6"

# Show current state
cur.execute("SELECT task_id, status, agent_id, files_written, branch_name FROM agent_task_ownerships WHERE project_token=? ORDER BY task_id", (TOKEN,))
print("=== CURRENT STATE ===")
for r in cur.fetchall():
    print(f"  {r[0][-10:]:<12} status={r[1]:<12} agent={str(r[2])[:25]:<25} files={str(r[3])[:40]}")

# Reset: change 'done' → 'claimed', clear files_written and branch_name
cur.execute("""
    UPDATE agent_task_ownerships 
    SET status='claimed', 
        files_written=NULL, 
        branch_name=NULL, 
        completed_at=NULL, 
        started_at=NULL,
        error_message=NULL,
        nxdune_synced=0,
        nxdune_sync_attempts=0,
        updated_at=CURRENT_TIMESTAMP
    WHERE project_token=? AND status='done'
""", (TOKEN,))
reset_count = cur.rowcount
conn.commit()

# Verify
cur.execute("SELECT task_id, status, agent_id FROM agent_task_ownerships WHERE project_token=? ORDER BY task_id", (TOKEN,))
print("\n=== AFTER RESET ===")
for r in cur.fetchall():
    print(f"  {r[0][-10:]:<12} status={r[1]:<12} agent={str(r[2])[:25]}")

print(f"\n✅ Reset {reset_count} tasks from 'done' → 'claimed'")
print(f"📊 Now {len(cur.execute('SELECT task_id FROM agent_task_ownerships WHERE project_token=? AND status=\"done\"', (TOKEN,)).fetchall())} done, "
      f"{len(cur.execute('SELECT task_id FROM agent_task_ownerships WHERE project_token=? AND status=\"claimed\"', (TOKEN,)).fetchall())} claimed, "
      f"{len(cur.execute('SELECT task_id FROM agent_task_ownerships WHERE project_token=? AND status=\"in_progress\"', (TOKEN,)).fetchall())} in_progress")

conn.close()
print("\n✅ Ready for clean run! Now trigger agents via UI or API.")
