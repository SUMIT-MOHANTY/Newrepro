"""🚀 Run agents on Testing 3 — auto-login, longer timeout, per-agent fallback"""
import httpx, asyncio, json, os, getpass, sqlite3

TOKEN = "4847e1af-721e-40af-adc9-b69aa4c15ba6"
API = "http://localhost:8000"

async def trigger_agent(client, agent_id, git_repo, git_token):
    """Try to trigger a single agent via POST /agents/{id}/run"""
    try:
        payload = {}
        if git_repo: payload["git_repo_url"] = git_repo
        if git_token: payload["git_token"] = git_token
        r = await client.post(
            f"{API}/agents/{agent_id}/run",
            params={"project_token": TOKEN},
            json=payload,
            timeout=30
        )
        return r.status_code, r.text[:200]
    except Exception as e:
        return -1, str(e)

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
            db = sqlite3.connect("sql_app.db")
            cur = db.cursor()
            cur.execute("SELECT source_repo_url, source_repo_token FROM governance_responses WHERE project_token=?", (TOKEN,))
            row = cur.fetchone()
            git_repo, git_token = (row[0] or None, row[1] or None) if row else (None, None)
            db.close()
        except:
            git_repo, git_token = None, None

        # Step 1: Initialize & get agents
        print(f"\n📡 Step 1: Getting agents...")
        r = await client.get(f"{API}/agents", params={"project_token": TOKEN})
        if r.status_code != 200:
            print(f"❌ Failed: {r.status_code}")
            return
        data = r.json()
        agents = data if isinstance(data, list) else data.get("agents", data.get("data", []))
        
        # Filter to worker agents (not system)
        workers = [a for a in agents if a.get("id","") not in ("G_agent_01", "M_agent_01")]
        print(f"   ✅ {len(agents)} agents initialized ({len(workers)} workers)")
        for a in agents:
            aid = a.get("id","?")[:25]
            status = a.get("status","?")
            print(f"      {aid:<25} {status}")

        # Step 2: Try run-all first with longer timeout
        print(f"\n🚀 Step 2: Trying /agents/run-all (60s timeout)...")
        try:
            r = await client.post(
                f"{API}/agents/run-all",
                params={"project_token": TOKEN},
                json={"source_repo_url": git_repo, "source_repo_token": git_token},
                timeout=120  # 2 minutes for initialization
            )
            print(f"   ✅ Run-all responded: {r.status_code}")
            if r.status_code == 200:
                print(f"   {r.text[:300]}")
            else:
                print(f"   {r.text[:300]}")
        except httpx.TimeoutException:
            print(f"   ⏱️  Run-all timed out (expected - it's initializing in background)")
            print(f"   ✅ Agents may still launch in background!")
        except Exception as e:
            print(f"   ⚠️  Run-all error: {e}")
        
        # Step 3: If run-all failed, trigger each worker agent individually
        print(f"\n🚀 Step 3: Triggering each worker agent individually...")
        results = await asyncio.gather(*[
            trigger_agent(client, a["id"], git_repo, git_token)
            for a in workers
        ])
        for agent, (status, text) in zip(workers, results):
            aid = agent["id"][:25]
            if status == 200:
                print(f"   ✅ {aid:<25} Launched!")
            elif status == 400 and "idle" in text.lower():
                print(f"   ⏳ {aid:<25} Not idle (may already be running)")
            else:
                print(f"   ⚠️  {aid:<25} {status}: {text[:60]}")

        # Step 4: Quick monitor
        print(f"\n👀 Monitoring for 30s...")
        for i in range(6):
            await asyncio.sleep(5)
            r = await client.get(f"{API}/agents", params={"project_token": TOKEN})
            if r.status_code != 200:
                continue
            data = r.json()
            agents = data if isinstance(data, list) else data.get("agents", [])
            active = [a for a in agents if a.get("status") in ("running","working")]
            done = [a for a in agents if a.get("status") == "completed"]
            if active or done:
                for a in active:
                    task = a.get("current_task", {}) or {}
                    print(f"      ▶️ {a.get('id','')[:20]:<20} [{a.get('progress',0):>3}%] {task.get('title','')[:50]}")
                for a in done:
                    print(f"      ✅ {a.get('id','')[:20]:<20} Completed!")
            else:
                print(f"   [{i+1}/6] Waiting...")

        print(f"\n✅ Done! Check http://localhost:5173/agents for live progress")

asyncio.run(main())
