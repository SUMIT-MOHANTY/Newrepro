"""📡 Agent Log Capture — Real-Time File Writing
Logs are written to files IMMEDIATELY as agents produce them.
No waiting until the end — check the files anytime!

Files:
  agent_logs_live.json    → Appended in real-time (every new log entry)
  agent_logs_live.txt     → Readable per-agent summary (refreshed every 3s)
"""

import httpx, asyncio, json, os, getpass, datetime, socket, sys
from pathlib import Path

# Resolve token dynamically (env variable -> CLI argument -> latest DB project -> fallback)
TOKEN = os.environ.get("PROJECT_TOKEN")
if not TOKEN:
    if len(sys.argv) > 1 and len(sys.argv[1]) == 36 and "-" in sys.argv[1]:
        TOKEN = sys.argv[1]

if not TOKEN:
    try:
        import sqlite3
        # Look for sql_app.db in current or parent dirs
        db_file = "sql_app.db"
        if os.path.exists(db_file):
            conn = sqlite3.connect(db_file)
            cur = conn.cursor()
            cur.execute("SELECT project_token FROM governance_responses ORDER BY id DESC LIMIT 1")
            row = cur.fetchone()
            if row:
                TOKEN = row[0]
                print(f"Auto-detected active project token from DB: {TOKEN}")
            conn.close()
    except Exception:
        pass

if not TOKEN:
    TOKEN = "4847e1af-721e-40af-adc9-b69aa4c15ba6"

API = "http://localhost:8000"

# File paths
JSON_PATH = Path("agent_logs_live.json")
TXT_PATH = Path("agent_logs_live.txt")

captured = {
    "project_token": TOKEN,
    "started_at": None,
    "agents": {},
    "task_history": [],
}

def write_live_log(agent_id: str, log_entry: dict):
    """Append a single log entry to the JSON file immediately"""
    entry = {
        "time": log_entry.get("time", datetime.datetime.utcnow().isoformat()),
        "agent_id": agent_id,
        "agent_name": captured["agents"].get(agent_id, {}).get("name", "?"),
        "type": log_entry.get("type", "info"),
        "message": log_entry.get("message", ""),
    }
    with open(JSON_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")

def write_status_snapshot(agents_data: list, task_data: dict):
    """Write current agent status + task summary to readable text file"""
    lines = []
    lines.append(f"{'='*70}")
    lines.append(f"  AGENT STATUS SNAPSHOT — {datetime.datetime.now().strftime('%H:%M:%S')}")
    lines.append(f"{'='*70}")
    
    s = task_data.get("summary", {}) if task_data else {}
    if s:
        lines.append(f"  TASKS: {s.get('done',0)} done | {s.get('in_progress',0)} running | {s.get('failed',0)} failed | {s.get('claimed',0)} pending")
        lines.append("")
    
    for a in agents_data:
        aid = a.get("id","?")
        status = a.get("status","?")
        name = a.get("name","?")
        task = a.get("current_task", {}) or {}
        title = task.get("title","")[:60] if isinstance(task, dict) else ""
        progress = a.get("progress", 0)
        logs = a.get("output_log", []) or []
        
        icon = {"running":"▶️","working":"▶️","completed":"✅","idle":"⚪","error":"❌"}.get(status, "❓")
        lines.append(f"\n  {icon} {name:<20} | {status:<10} | {progress:>3}%")
        if title:
            lines.append(f"     Task: {title}")
        
        # Show recent logs
        recent = logs[-10:] if logs else []
        for l in recent:
            lt = l.get("type","info")
            icon_l = {"info":"  ","warning":"⚠️","error":"❌"}.get(lt, "  ")
            msg = l.get("message","")[:150]
            lines.append(f"     {icon_l} {msg}")
    
    with open(TXT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

async def main():
    auth_token = os.environ.get("LOGIN_TOKEN")
    if auth_token:
        print("\n🔑 Using LOGIN_TOKEN from environment...")
        email = "auto@captured"
        password = "auto"
    else:
        email = os.environ.get("LOGIN_EMAIL") or input("Email: ").strip()
        password = os.environ.get("LOGIN_PASSWORD") or getpass.getpass("Password: ")
    
    if not auth_token and (not email or not password):
        print("❌ Email and password required!")
        return

    async with httpx.AsyncClient(timeout=30) as client:
        if not auth_token:
            # Login
            print("\n🔑 Logging in...")
            r = await client.post(f"{API}/token", data={"username": email, "password": password})
            if r.status_code != 200:
                print(f"❌ Login failed: {r.status_code}")
                return
            auth_token = r.json().get("access_token")
        
        client.headers["Authorization"] = f"Bearer {auth_token}"
        client.headers["Content-Type"] = "application/json"

        # Single-instance socket lock after successful login/token resolution
        global _lock_socket
        try:
            _lock_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            _lock_socket.bind(("127.0.0.1", 19999))
        except OSError:
            print("⚠️ capture_agent_logs.py is already running. Exiting.")
            sys.exit(0)

        captured["started_at"] = datetime.datetime.utcnow().isoformat()

        # Init log files with a start marker
        start_marker = {"type": "capture_started", "time": captured["started_at"], "project_token": TOKEN}
        JSON_PATH.write_text(json.dumps(start_marker) + "\n")
        TXT_PATH.write_text(f"[LOG CAPTURE] Started at {captured['started_at']}\n{'='*70}\n", encoding="utf-8")

        # Initial agents snapshot
        r = await client.get(f"{API}/agents", params={"project_token": TOKEN})
        if r.status_code != 200:
            print(f"❌ Failed: {r.status_code}")
            return
        data = r.json()
        agents_init = data if isinstance(data, list) else data.get("agents", [])
        
        print(f"\n{'='*70}")
        print(f"  📡 REAL-TIME LOG CAPTURE")
        print(f"  ✅ {len(agents_init)} agents ready. Trigger agents NOW from UI!")
        print(f"\n  📁 Files being written LIVE:")
        print(f"     {JSON_PATH} — Every agent log entry (appended instantly)")
        print(f"     {TXT_PATH}  — Status snapshot (refreshed every 3s)")
        print(f"\n  Open {TXT_PATH} anytime to see current progress!")
        print(f"  Press Ctrl+C to stop")
        print(f"{'='*70}\n")

        # Initialize tracking
        seen_logs = {}  # agent_id -> set of log keys
        for a in agents_init:
            aid = a.get("id","?")
            captured["agents"][aid] = {
                "name": a.get("name","?"),
                "first_seen": datetime.datetime.utcnow().isoformat(),
            }
            seen_logs[aid] = set()
            for l in (a.get("output_log") or []):
                key = json.dumps(l)
                seen_logs[aid].add(key)

        write_status_snapshot(agents_init, {})

        # Monitoring loop
        idle_cycles = 0
        try:
            for cycle in range(600):
                await asyncio.sleep(3)

                r = await client.get(f"{API}/agents", params={"project_token": TOKEN})
                if r.status_code != 200:
                    continue
                data = r.json()
                agents = data if isinstance(data, list) else data.get("agents", [])

                # Get tasks
                tr = await client.get(f"{API}/api/projects/{TOKEN}/local-task-status")
                task_data = tr.json() if tr.status_code == 200 else {}

                # Process each agent — write NEW logs immediately
                any_active = False
                for a in agents:
                    aid = a.get("id","?")
                    status = a.get("status","?")
                    logs = a.get("output_log", []) or []
                    progress = a.get("progress", 0)
                    
                    if aid not in seen_logs:
                        seen_logs[aid] = set()
                    if aid not in captured["agents"]:
                        captured["agents"][aid] = {"name": a.get("name","?"), "first_seen": datetime.datetime.utcnow().isoformat()}

                    # Write NEW log entries to file IMMEDIATELY
                    for l in logs:
                        key = json.dumps(l)
                        if key not in seen_logs[aid]:
                            seen_logs[aid].add(key)
                            write_live_log(aid, l)  # ← WRITTEN TO FILE NOW!
                            # Also show on screen
                            msg = l.get("message","")[:150]
                            ts = str(l.get("time",""))[-8:]
                            lt = l.get("type","info")
                            print(f"  [{datetime.datetime.now().strftime('%H:%M:%S')}] {a.get('name','?')[:20]:<20} [{lt.upper()}] {msg}")

                    if status in ("running", "working"):
                        any_active = True

                # Write status snapshot
                write_status_snapshot(agents, task_data)

                # Show status line
                if any_active:
                    idle_cycles = 0
                    running = sum(1 for a in agents if a.get("status") in ("running","working"))
                    s = task_data.get("summary", {}) or {}
                    print(f"  [{datetime.datetime.now().strftime('%H:%M:%S')}] 🟢 {running} running | Tasks: {s.get('done',0)}/{s.get('total',0)} done")
                else:
                    idle_cycles += 1
                    if cycle % 10 == 0:
                        print(f"  [{datetime.datetime.now().strftime('%H:%M:%S')}] ⏳ Waiting... ")

                # Auto-stop if all done
                s = task_data.get("summary", {}) or {}
                if s.get("total", 0) > 0 and (s.get("done",0) + s.get("failed",0)) >= s.get("total",0):
                    print(f"\n{'='*70}")
                    print(f"  🎉 ALL TASKS COMPLETE!")
                    print(f"{'='*70}")
                    for t in task_data.get("tasks", []):
                        icon = {"done":"✅","in_progress":"🔄","claimed":"⏳","failed":"❌"}.get(t["status"],"❓")
                        print(f"  {icon} {str(t.get('task_title',''))[:55]:<55} [{t['status']}]")
                    break

        except KeyboardInterrupt:
            print(f"\n\n⏹️  Stopped by user")

        # Final summary
        print(f"\n{'='*70}")
        print(f"  ✅ LOG FILES SAVED:")
        print(f"  📄 {JSON_PATH} — {os.path.getsize(JSON_PATH)/1024:.1f} KB (all agent log entries)")
        print(f"  📄 {TXT_PATH}  — {os.path.getsize(TXT_PATH)/1024:.1f} KB (readable status)")
        
        # Show final stats
        agent_count = len(captured["agents"])
        total_logs = sum(1 for _ in open(JSON_PATH)) if JSON_PATH.exists() else 0
        print(f"\n  📊 Agents tracked: {agent_count}")
        print(f"  📊 Log entries:   {total_logs}")
        print(f"\n  Open {TXT_PATH} to see the final agent status summary!")
        print(f"{'='*70}")


async def auto_capture_loop():
    """
    Runs in the background of the FastAPI web server.
    Directly queries the in-memory agent service and SQLite DB to update
    agent_logs_live.json and agent_logs_live.txt in real-time.
    """
    import asyncio
    import datetime
    import json
    from pathlib import Path
    
    json_path = Path("agent_logs_live.json")
    txt_path = Path("agent_logs_live.txt")
    
    # Auto-detect project token dynamically
    token = None
    try:
        import sqlite3
        db_file = "sql_app.db"
        if os.path.exists(db_file):
            conn = sqlite3.connect(db_file)
            cur = conn.cursor()
            cur.execute("SELECT project_token FROM governance_responses ORDER BY id DESC LIMIT 1")
            row = cur.fetchone()
            if row:
                token = row[0]
            conn.close()
    except Exception:
        pass
        
    if not token:
        token = "7e2855a0-ec9a-4246-b3df-ad80dffe8322"  # fallback to 'main test'

    # Clear/initialize live files on server start
    try:
        start_marker = {"type": "capture_started", "time": datetime.datetime.utcnow().isoformat(), "project_token": token}
        json_path.write_text(json.dumps(start_marker) + "\n", encoding="utf-8")
        txt_path.write_text(f"[LOG CAPTURE] Auto-started at {datetime.datetime.utcnow().isoformat()}\n{'='*70}\n", encoding="utf-8")
    except Exception:
        pass

    seen_logs = {}  # agent_id -> set of log keys
    
    # Import locally to avoid circular dependency
    import agent_service
    from database import SessionLocal
    import models

    while True:
        try:
            await asyncio.sleep(2)
            
            # Fetch all agents from in-memory agent_service
            agents = agent_service.get_all_agents(token)
            if not agents:
                continue
                
            # Fetch local task summary status
            db = SessionLocal()
            task_data = {}
            try:
                local_tasks = db.query(models.Task).filter(
                    models.Task.project_token == token
                ).all()
                if local_tasks:
                    done = sum(1 for t in local_tasks if t.synced_to_nxdune)
                    total = len(local_tasks)
                    task_data = {
                        "summary": {
                            "done": done,
                            "in_progress": sum(1 for t in local_tasks if t.selected and not t.synced_to_nxdune),
                            "total": total
                        }
                    }
            except Exception:
                pass
            finally:
                db.close()

            # Process new log entries
            for a in agents:
                aid = a.get("id", "?")
                logs = a.get("output_log", []) or []
                
                if aid not in seen_logs:
                    seen_logs[aid] = set()
                    # Mark existing initial logs as seen
                    for l in logs:
                        seen_logs[aid].add(json.dumps(l))
                    continue

                for l in logs:
                    key = json.dumps(l)
                    if key not in seen_logs[aid]:
                        seen_logs[aid].add(key)
                        
                        # Append to agent_logs_live.json
                        entry = {
                            "time": l.get("time", datetime.datetime.utcnow().isoformat()),
                            "agent_id": aid,
                            "agent_name": a.get("name", "?"),
                            "type": l.get("type", "info"),
                            "message": l.get("message", ""),
                        }
                        try:
                            with open(json_path, "a", encoding="utf-8") as f:
                                f.write(json.dumps(entry) + "\n")
                        except Exception:
                            pass
                            
            # Update readable status snapshot TXT file
            try:
                from capture_agent_logs import write_status_snapshot
                write_status_snapshot(agents, task_data)
            except Exception:
                pass

        except asyncio.CancelledError:
            break
        except Exception:
            await asyncio.sleep(2)


if __name__ == "__main__":
    asyncio.run(main())
