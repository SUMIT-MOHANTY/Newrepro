"""Check tasks and DAG structure for Testing 3 project - auto-discovers columns"""
import sqlite3, json, os

os.chdir(os.path.dirname(os.path.abspath(__file__)))
conn = sqlite3.connect("sql_app.db")
cur = conn.cursor()

TOKEN = "4847e1af-721e-40af-adc9-b69aa4c15ba6"

def show_table(table, where_col=None, where_val=None, label=""):
    """Dynamically discover columns and query a table"""
    try:
        cols = [r[1] for r in cur.execute(f"PRAGMA table_info({table})").fetchall()]
    except:
        return False
    
    if label:
        print(f"\n=== {label} ({table}) ===")
    
    if where_col and where_val:
        cur.execute(f"SELECT * FROM {table} WHERE \"{where_col}\"=? LIMIT 5", (where_val,))
    else:
        cur.execute(f"SELECT * FROM {table} LIMIT 3")
    
    rows = cur.fetchall()
    if not rows:
        print(f"  No rows found")
        return True
    
    for r in rows:
        print(f"  Row:")
        for i, c in enumerate(cols):
            val = str(r[i])[:100] if r[i] is not None else "NULL"
            print(f"    {c}: {val}")
        print()
    return True

def find_project_token(search_val, table, possible_cols):
    """Try to find a row matching the search value"""
    try:
        cols = [r[1] for r in cur.execute(f"PRAGMA table_info({table})").fetchall()]
    except:
        return None
    
    for col in possible_cols:
        if col in cols:
            cur.execute(f"SELECT * FROM {table} WHERE \"{col}\"=? LIMIT 1", (search_val,))
            row = cur.fetchone()
            if row:
                print(f"  ✅ Found in {table}.{col}")
                return {cols[i]: row[i] for i in range(len(cols))}
    return None

# 1. Find the project first - check governance_responses
print("=" * 60)
print("STEP 1: Finding Project 'Testing 3'")
print("=" * 60)

proj = find_project_token(TOKEN, "governance_responses", 
                          ["project_token", "client_id", "id"])
if proj:
    print(f"\n  Project Name: {proj.get('project_name', proj.get('name', 'N/A'))}")
    print(f"  Project Token: {proj.get('project_token', 'N/A')}")
else:
    # Try other tables
    for tbl in ["documents", "handoff_tokens"]:
        proj = find_project_token(TOKEN, tbl, ["project_token", "project_id"])
        if proj:
            break
    
    if not proj:
        print("  ❌ Project not found in any table!")

# 2. Show all tasks for this project
print("\n" + "=" * 60)
print("STEP 2: Finding Tasks")
print("=" * 60)

# Try tasks table
try:
    cols = [r[1] for r in cur.execute("PRAGMA table_info(tasks)").fetchall()]
    print(f"Tasks columns: {cols}")
    
    # Find which column links to project
    link_col = None
    for col in ["project_token", "client_id", "project_id", "owner_id"]:
        if col in cols:
            cur.execute(f"SELECT * FROM tasks WHERE \"{col}\"=? LIMIT 1", (TOKEN,))
            if cur.fetchone():
                link_col = col
                break
    
    if link_col:
        cur.execute(f"SELECT * FROM tasks WHERE \"{link_col}\"=? ORDER BY task_id", (TOKEN,))
        tasks = cur.fetchall()
        print(f"\n✅ FOUND {len(tasks)} TASKS (linked via '{link_col}'):")
        for t in tasks:
            tdict = {cols[i]: t[i] for i in range(len(cols))}
            tid = tdict.get("task_id", "?")
            title = tdict.get("title", tdict.get("taskName", tdict.get("task_name", "?")))
            sprint = tdict.get("sprint", tdict.get("sprint_name", "?"))
            linked = tdict.get("linked_tasks", tdict.get("dependencies", "[]"))
            priority = tdict.get("priority", "?")
            status = tdict.get("status", "?")
            desc = tdict.get("description", "")
            
            # Parse linked_tasks
            try:
                deps = json.loads(linked) if isinstance(linked, str) and linked else (linked or [])
            except:
                deps = []
            
            print(f"\n  📋 {tid}: {str(title)[:70]}")
            print(f"     Sprint: {sprint} | Priority: {priority} | Status: {status}")
            print(f"     Dependencies (linked_tasks): {deps}")
            if desc:
                print(f"     Desc: {str(desc)[:200]}")
    else:
        print("  ❓ Could not link tasks to project")
except Exception as e:
    print(f"  Error querying tasks: {e}")

# 3. Show agent assignments
print("\n" + "=" * 60)
print("STEP 3: Agent Assignments")
print("=" * 60)

for tbl in ["agent_task_ownerships", "agent_task_ownership"]:
    try:
        cols = [r[1] for r in cur.execute(f"PRAGMA table_info({tbl})").fetchall()]
        for col in ["project_token", "client_id"]:
            if col in cols:
                cur.execute(f"SELECT * FROM {tbl} WHERE \"{col}\"=?", (TOKEN,))
                rows = cur.fetchall()
                if rows:
                    print(f"✅ Found {len(rows)} records in {tbl}:")
                    for r in rows:
                        rdict = {cols[i]: r[i] for i in range(len(cols))}
                        tid = rdict.get("task_id", "?")
                        agent = rdict.get("agent_id", "?")
                        status = rdict.get("status", "?")
                        print(f"  {tid} → {agent} [{status}]")
    except:
        pass

print("\n✅ DONE")
conn.close()
