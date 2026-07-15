#!/usr/bin/env python3
import os
import sys
import time
import subprocess
from pathlib import Path

def log(msg):
    print(f"🛠️ [VibeFix] {msg}", flush=True)

def fix_and_persist():
    project_dir = os.environ.get('PROJECT_DIR', '/project')
    workspace_dir = Path(project_dir) / "workspace"
    versions_dir = Path(project_dir) / "versions"
    
    # 1. Identify current source
    current_version = os.environ.get('CURRENT_VERSION', 'workspace')
    if current_version == 'workspace':
        source_dir = workspace_dir
    else:
        source_dir = versions_dir / current_version
        
    if not source_dir.exists():
        log(f"Error: Source directory {source_dir} not found")
        sys.exit(1)

    log(f"Starting Vibe Fix in {source_dir}...")
    
    # Start the agent and watch it
    # We use a temporary env to ensure it doesn't loop forever if we want one-shot,
    # but the agent already handles retries.
    try:
        # Run agent for a limited time or until it's healthy
        # For now, we'll run it and monitor the port
        agent_process = subprocess.Popen(
            ["python3", "/usr/local/bin/ai-agent.py"],
            cwd=str(source_dir),
            env={**os.environ, 'PYTHONUNBUFFERED': '1'}
        )
        
        log("Agent is working on fixes... (This may take a minute)")
        
        # Simple health check loop
        port = os.environ.get('PORT', '8080')
        start_time = time.time()
        timeout = 300 # 5 minutes
        
        is_healthy = False
        while time.time() - start_time < timeout:
            if agent_process.poll() is not None:
                log("Agent exited early. Checking if successful...")
                break
                
            try:
                # Check if port is listening
                # We can use lsof or just try a dummy connection
                res = subprocess.run(["lsof", f"-i:{port}"], capture_output=True)
                if res.returncode == 0:
                    log(f"✅ Success! Project is now listening on {port}")
                    is_healthy = True
                    break
            except:
                pass
            
            time.sleep(5)
            
        if not is_healthy:
            log("❌ Timeout or agent failure while fixing.")
        else:
            # 2. Persist to workspace if we weren't already there
            if current_version != 'workspace':
                log(f"Persisting fixes from {current_version} back to workspace...")
                # Avoid copying node_modules, .git etc
                cmd = [
                    "rsync", "-av", "--exclude", "node_modules", 
                    "--exclude", ".git", "--exclude", "__pycache__",
                    str(source_dir) + "/", str(workspace_dir) + "/"
                ]
                subprocess.run(cmd)
                log("✅ Done! Fixes are now persistent in the workspace.")
            else:
                log("✅ Fixes are already in the workspace.")

    finally:
        if agent_process and agent_process.poll() is None:
            agent_process.terminate()
            agent_process.wait()

if __name__ == "__main__":
    fix_and_persist()
