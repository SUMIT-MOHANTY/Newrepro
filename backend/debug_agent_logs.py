"""🔍 Real-Time Agent Debug Logger — Per-Agent Logs for Testing 3

Shows every agent's output_log, progress, errors in real-time.
Polling every 3 seconds — watch the agents work step by step.
"""
import httpx, asyncio, json, os, getpass, datetime

TOKEN = "4847e1af-721e-40af-adc9-b69aa4c15ba6"
API = "http://localhost:8000"

# Track what we've seen per agent
seen_logs: dict = {}  # agent_id -> set of log messages

def print_header(text):
    print(f"\n{'='*70}")
    print(f"  {text}")
    print(f"{'='*70}")

def format_time():
    return datetime.datetime.now().strftime("%H:%M:%S")

async def main():
    email = os.environ.get("LOGIN_EMAIL") or input("Email: ").strip()
    password = os.environ.get("LOGIN_PASSWORD") or getpass.getpass("Password: ")
    if not email or not password:
        print("❌ Email and password required!")
        return

    async with httpx.AsyncClient(timeout=60) as client:
        # Login
        print("\n🔑 Logging in...")
        r = await client.post(f"{API}/token", data={"username": email, "password": password})
        if r.status_code != 200:
            print(f"❌ Login failed: {r.status_code}")
            return
        auth_token = r.json().get("access_token")
        print(f"   ✅ Token acquired")
        client.headers["Authorization"] = f"Bearer {auth_token}"
        client.headers["Content-Type"] = "application/json"

        # Read git config from DB
        try:
            import sqlite3
            db = sqlite3.connect("sql_app.db")
            git_repo, git_token = db.execute(
                "SELECT source_repo_url, source_repo_token FROM governance_responses WHERE project_token=?",
                (TOKEN,)
            ).fetchone() or (None, None)
            db.close()
        except:
            git_repo, git_token = None, None

        # Step 1: Initialize agents
        print_header("INITIALIZING AGENTS")
        r = await client.get(f"{API}/agents", params={"project_token": TOKEN})
        agents_data = r.json() if r.status_code == 200 else {"agents": []}
        agents = agents_data if isinstance(agents_data, list) else agents_data.get("agents", [])
        
        # Show initial state
        for a in agents:
            aid = a.get("id","?")
            name = a.get("name","?")
            status = a.get("status","?")
            task = a.get("current_task", {}) or {}
            title = task.get("title","") if isinstance(task, dict) else ""
            logs = a.get("output_log", []) or []
            seen_logs[aid] = {json.dumps(l) for l in logs}
            print(f"  {aid[:30]:<30} {name:<20} [{status:>10}] {title[:40]}")
            for l in logs[-3:]:  # Show last 3 initial logs
                print(f"     📝 {l.get('type','?')}: {l.get('message','')[:100]}")

        print(f"\n   🔗 Git: {'✅' if git_repo else '❌'} {git_repo or 'Not configured'}")

        # Step 2: Trigger agents
        print_header("TRIGGERING AGENTS")

        # Try run-all
        print("  Trying /agents/run-all...")
        try:
            r = await client.post(
                f"{API}/agents/run-all",
                params={"project_token": TOKEN},
                json={"source_repo_url": git_repo, "source_repo_token": git_token},
                timeout=120
            )
            if r.status_code == 200:
                print(f"  ✅ Run-all succeeded! {r.text[:200]}")
            else:
                print(f"  ⚠️  Run-all: {r.status_code} - {r.text[:200]}")
        except httpx.TimeoutException:
            print(f"  ⏱️  Run-all timed out (expected — agents launching in background)")
        except Exception as e:
            print(f"  ⚠️  Run-all error: {e}")

        # Fallback: trigger each worker individually
        workers = [a for a in agents if a.get("id","") not in ("G_agent_01", "M_agent_01")]
        if workers:
            print(f"\n  Also triggering {len(workers)} workers individually...")
            for a in workers:
                try:
                    r = await client.post(
                        f"{API}/agents/{a['id']}/run",
                        params={"project_token": TOKEN},
                        json={"git_repo_url": git_repo, "git_token": git_token},
                        timeout=60
                    )
                    if r.status_code == 200:
                        print(f"  ✅ {a['id'][:25]:<25} Launched")
                    elif "already" in r.text.lower():
                        print(f"  🔄 {a['id'][:25]:<25} Already running")
                    else:
                        print(f"  ⚠️  {a['id'][:25]:<25} {r.status_code}: {r.text[:80]}")
                except Exception as e:
                    print(f"  ⚠️  {a['id'][:25]:<25} Error: {e}")

        # Step 3: REAL-TIME MONITORING LOOP
        print_header("📡 REAL-TIME AGENT LOG MONITOR")
        print("  Polling every 3s — logs appear as agents emit them")
        print("  Press Ctrl+C to stop monitoring\n")

        try:
            for cycle in range(200):  # ~10 minutes
                await asyncio.sleep(3)

                r = await client.get(f"{API}/agents", params={"project_token": TOKEN})
                if r.status_code != 200:
                    continue

                data = r.json()
                agents = data if isinstance(data, list) else data.get("agents", [])
                
                # Also check task status
                tr = await client.get(f"{API}/api/projects/{TOKEN}/local-task-status")
                task_summary = {}
                if tr.status_code == 200:
                    ts = tr.json().get("summary", {})
                    task_summary = ts

                # Print status line
                running = [a for a in agents if a.get("status") in ("running","working")]
                done_agents = [a for a in agents if a.get("status") == "completed"]
                idle = [a for a in agents if a.get("status") == "idle"]
                t_done = task_summary.get('done', 0)
                t_prog = task_summary.get('in_progress', 0)
                print(f"\n[{format_time()}] Cycle {cycle+1} | 🟢 {len(running)} running | ✅ {len(done_agents)} done | ⚪ {len(idle)} idle | Tasks: {t_done} done, {t_prog} in-progress")
                print("-" * 70)

                # Show each agent's NEW logs
                for a in agents:
                    aid = a.get("id","?")
                    status = a.get("status","?")
                    task = a.get("current_task", {}) or {}
                    title = task.get("title","")[:50] if isinstance(task, dict) else ""
                    progress = a.get("progress", 0)
                    prog_msg = a.get("progress_message", "")[:80]
                    logs = a.get("output_log", []) or []

                    if status in ("running", "working", "completed"):
                        print(f"\n  🤖 {aid[:30]:<30} [{status:>10}] {progress:>3}%")
                        if title:
                            print(f"     📋 Task: {title}")
                        if prog_msg and prog_msg != title:
                            print(f"     💬 {prog_msg}")

                    # Show NEW logs only (ones we haven't seen)
                    new_logs = []
                    if aid not in seen_logs:
                        seen_logs[aid] = set()
                    for l in logs:
                        key = json.dumps(l)
                        if key not in seen_logs[aid]:
                            seen_logs[aid].add(key)
                            new_logs.append(l)

                    # Show the new logs
                    for l in new_logs:
                        lt = l.get("type","info")
                        icon = {"info":"📝", "warning":"⚠️", "error":"❌", "success":"✅"}.get(lt, "📝")
                        msg = l.get("message","")[:150]
                        raw = str(l.get("time","") or "")
                        ts = raw.split("T")[1][:8] if "T" in raw else raw[-8:]
                        print(f"     {icon} [{ts}] {msg}")

                    # If running with no new logs, show a heartbeat
                    if status == "running" and not new_logs and cycle % 10 == 0:
                        print(f"     💓 Working... (progress: {progress}%)")

                # Show task summary periodically
                if task_summary:
                    total = task_summary.get('total', 0)
                    done = task_summary.get('done', 0)
                    failed = task_summary.get('failed', 0)
                    claimed = task_summary.get('claimed', 0)
                    
                    # If all tasks done, show final summary and exit monitoring
                    if done + failed >= total and total > 0:
                        print(f"\n{'='*70}")
                        print(f"  🎉 ALL TASKS COMPLETE! {done}/{total} done, {failed} failed")
                        print(f"{'='*70}")
                        
                        # Show final per-task status
                        tr = await client.get(f"{API}/api/projects/{TOKEN}/local-task-status")
                        if tr.status_code == 200:
                            for t in tr.json().get("tasks", []):
                                icon = {"done":"✅","in_progress":"🔄","claimed":"⏳","failed":"❌"}.get(t["status"],"❓")
                                print(f"  {icon} {str(t.get('task_title',''))[:55]:<55} [{t['status']}]")
                        break

        except KeyboardInterrupt:
            print(f"\n\n⏹️  Monitoring stopped by user")

        # Final summary
        print_header("📊 FINAL SUMMARY")
        r = await client.get(f"{API}/agents", params={"project_token": TOKEN})
        if r.status_code == 200:
            data = r.json()
            agents = data if isinstance(data, list) else data.get("agents", [])
            for a in agents:
                aid = a.get("id","?")
                status = a.get("status","?")
                name = a.get("name","?")
                task = a.get("current_task", {}) or {}
                title = task.get("title","")[:60] if isinstance(task, dict) else ""
                logs = a.get("output_log", []) or []
                
                print(f"\n  🤖 {aid[:35]:<35} {name:<20}")
                print(f"     Status: {status}")
                if title:
                    print(f"     Task:   {title}")
                
                # Show ALL error/warning logs
                errors = [l for l in logs if l.get("type") in ("error", "warning")]
                if errors:
                    print(f"     Issues ({len(errors)}):")
                    for e in errors[-20:]:
                        print(f"       {e.get('type')}: {e.get('message','')[:120]}")
                
                # Show last 10 log entries
                print(f"     Recent activity ({len(logs)} total log entries):")
                for l in logs[-5:]:
                    lt = l.get("type","?")
                    msg = l.get("message","")[:120]
                    ts = str(l.get("time",""))[-8:]
                    print(f"       [{ts}] [{lt}] {msg}")

        # Task final status
        r = await client.get(f"{API}/api/projects/{TOKEN}/local-task-status")
        if r.status_code == 200:
            s = r.json().get("summary", {})
            print(f"\n{'='*70}")
            print(f"  📊 TASKS: {s.get('done',0)} done | {s.get('in_progress',0)} running | {s.get('failed',0)} failed | {s.get('claimed',0)} pending")
            for t in r.json().get("tasks", []):
                icon = {"done":"✅","in_progress":"🔄","claimed":"⏳","failed":"❌"}.get(t["status"],"❓")
                print(f"  {icon} {str(t.get('task_title',''))[:55]:<55} [{t['status']}]")
            print(f"{'='*70}")

        print(f"\n✅ Monitoring complete! Open http://localhost:5173/agents for live view")

asyncio.run(main())
