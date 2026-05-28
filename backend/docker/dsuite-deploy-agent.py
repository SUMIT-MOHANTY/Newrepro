#!/usr/bin/env python3
"""
D-Suite Deploy Agent
Runs inside the Preview Docker container.
Handles cloning, dependency installation, running the app, Nginx reverse proxying,
and autonomous self-healing for deployment failures.
"""

import os
import sys
import json
import time
import subprocess
import requests
import re
from pathlib import Path
from typing import Dict, Any, List, Optional

WORKSPACE_DIR = Path("/workspace")
MAX_AUTO_FIXES = 5

def log(msg: str):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)

def call_llm(messages: List[Dict[str, str]], temperature=0.1) -> str:
    url = os.environ.get("LLM_API_URL", "")
    key = os.environ.get("LLM_API_KEY", "")
    model = os.environ.get("LLM_MODEL", "gpt-4o-mini")
    
    if not url or not key:
        log("LLM_API_URL or LLM_API_KEY not set. Cannot use EditEngine.")
        return ""
        
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {key}"
    }
    
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature
    }
    
    # Handle Azure/OpenAI differences loosely
    if "openai.azure" in url:
        headers["api-key"] = key
        
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=60)
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        log(f"LLM Call Failed: {e}")
        return ""

class EditEngine:
    def __init__(self, workspace_dir: Path):
        self.ws = workspace_dir

    def _list_files(self) -> List[str]:
        if not self.ws.exists():
            return []
        skip_dirs = {"node_modules", ".git", "venv", "__pycache__"}
        result = []
        for root, dirs, files in os.walk(self.ws):
            dirs[:] = [d for d in dirs if d not in skip_dirs]
            for f in files:
                rel = os.path.relpath(os.path.join(root, f), self.ws)
                result.append(rel.replace("\\", "/"))
        return sorted(result)

    def _read_file(self, rel_path: str) -> Optional[Dict[str, Any]]:
        full = self.ws / rel_path
        if not full.exists() or not full.is_file(): return None
        try:
            raw = full.read_text(encoding="utf-8", errors="replace")
        except:
            return None
        lines = raw.splitlines()
        numbered = "\n".join(f"{i+1:>4}\t{l}" for i, l in enumerate(lines))
        return {"content": numbered, "raw": raw}

    def route(self, prompt: str, error_logs: str) -> bool:
        tree = self._list_files()
        
        # Load up to 10 files for context
        context_files = {}
        for f in tree[:10]:
            fd = self._read_file(f)
            if fd: context_files[f] = fd
            
        context_str = "\\n".join(f"--- {k} ---\\n{v['content']}" for k, v in context_files.items())
        
        system_msg = "You are an autonomous code repair agent. Provide JSON operations to fix the deployment error."
        user_msg = f"""USER REQUEST: {prompt}
ERROR LOGS:
{error_logs[-2000:]}

WORKSPACE FILES:
{context_str[:20000]}

Respond ONLY in JSON with this structure:
{{
  "operations": [
    {{
      "op_type": "REPLACE_LINES",
      "file": "src/App.jsx",
      "start_line": 10,
      "end_line": 15,
      "new_content": "replaced content"
    }},
    {{
      "op_type": "CREATE_FILE",
      "file": "path/file.py",
      "new_content": "new file content"
    }},
    {{
      "op_type": "FULL_REWRITE",
      "file": "path/file.py",
      "new_content": "full content"
    }}
  ]
}}
"""
        raw = call_llm([{"role": "system", "content": system_msg}, {"role": "user", "content": user_msg}])
        if not raw: return False
        
        try:
            raw = raw.replace("```json", "").replace("```", "").strip()
            plan = json.loads(raw)
            ops = plan.get("operations", [])
            for op in ops:
                self._apply_op(op)
            return True
        except Exception as e:
            log(f"EditEngine failed to parse/apply operations: {e}")
            return False

    def _apply_op(self, op):
        op_type = op.get("op_type")
        rel_path = op.get("file")
        new_content = op.get("new_content", "")
        abs_path = self.ws / rel_path
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        
        if op_type == "CREATE_FILE" or op_type == "FULL_REWRITE":
            abs_path.write_text(new_content, encoding="utf-8")
            log(f"Applied {op_type} to {rel_path}")
        elif op_type == "REPLACE_LINES":
            if abs_path.exists():
                lines = abs_path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
                start = max(0, int(op.get("start_line", 1)) - 1)
                end = int(op.get("end_line", start + 1))
                new_lines = [l if l.endswith("\\n") else l + "\\n" for l in new_content.splitlines()] or ["\\n"]
                lines[start:end] = new_lines
                abs_path.write_text("".join(lines), encoding="utf-8")
                log(f"Applied REPLACE_LINES to {rel_path}")

def detect_stack():
    has_package = (WORKSPACE_DIR / "package.json").exists()
    has_reqs = (WORKSPACE_DIR / "requirements.txt").exists()
    has_pyproject = (WORKSPACE_DIR / "pyproject.toml").exists()
    
    if has_package:
        text = (WORKSPACE_DIR / "package.json").read_text()
        if "next" in text: return {"type": "node", "cmd": "npm install && npm run dev", "port": 3000}
        if "vite" in text: return {"type": "node", "cmd": "npm install && npm run dev", "port": 5173}
        return {"type": "node", "cmd": "npm install && npm start", "port": 3000}
        
    if has_reqs or has_pyproject:
        if has_reqs:
            text = (WORKSPACE_DIR / "requirements.txt").read_text().lower()
        else:
            text = (WORKSPACE_DIR / "pyproject.toml").read_text().lower()
            
        if "fastapi" in text or "uvicorn" in text:
            # find main file
            for root, _, files in os.walk(WORKSPACE_DIR):
                if "main.py" in files:
                    return {"type": "python", "cmd": "pip install -r requirements.txt && uvicorn main:app --host 0.0.0.0 --port 8000", "port": 8000}
            return {"type": "python", "cmd": "pip install -r requirements.txt && uvicorn app:app --host 0.0.0.0 --port 8000", "port": 8000}
        if "flask" in text:
            return {"type": "python", "cmd": "pip install -r requirements.txt && flask run --host=0.0.0.0 --port 5000", "port": 5000}
            
        return {"type": "python", "cmd": "pip install -r requirements.txt && python main.py", "port": 8000}
        
    # Default fallback
    return {"type": "static", "cmd": "python3 -m http.server 8000", "port": 8000}

def config_nginx(app_port: int):
    conf = f"""
server {{
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;
    
    location / {{
        proxy_pass http://127.0.0.01:{app_port};
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }}
}}
"""
    Path("/etc/nginx/sites-available/default").write_text(conf)
    subprocess.run(["nginx", "-s", "reload"], check=False)
    subprocess.run(["service", "nginx", "restart"], check=False)

def check_health() -> tuple[bool, str]:
    try:
        res = requests.get("http://localhost:80", timeout=5)
        if res.status_code < 500:
            return True, ""
        return False, f"HTTP {res.status_code}"
    except Exception as e:
        return False, str(e)

def get_server_logs() -> str:
    log_text = ""
    if Path("/tmp/app.log").exists():
        log_text += Path("/tmp/app.log").read_text()[-2000:]
    return log_text

def clone_repo():
    auth_url = os.environ.get("GIT_AUTH_URL")
    config_args = os.environ.get("GIT_CONFIG_ARGS", "")
    branch = os.environ.get("SPRINT_BRANCH", "agent/integration")
    
    if not auth_url:
        log("GIT_AUTH_URL not provided.")
        return
        
    log(f"Cloning {auth_url.split('@')[-1] if '@' in auth_url else auth_url} branch {branch}")
    os.chdir("/")
    
    cmd = ["git"]
    if config_args:
        # config_args might be: -c http.extraHeader=Authorization: Basic xxx
        # We split by " -c " carefully, or just pass it directly if we format it as JSON.
        try:
            args_list = json.loads(config_args)
            cmd.extend(args_list)
        except:
            pass
            
    cmd.extend([
        "clone", "--branch", branch, "--depth", "1",
        "--single-branch", "--no-tags",
        "-c", "http.postBuffer=524288000",
        auth_url, "/workspace_temp"
    ])
    
    subprocess.run(cmd, check=False)
    
    if Path("/workspace_temp").exists():
        subprocess.run(["rm", "-rf", "/workspace/*"], check=False)
        subprocess.run("cp -a /workspace_temp/. /workspace/", shell=True, check=False)
    else:
        log("Clone failed.")

def main():
    log("D-Suite Deploy Agent started.")
    
    if not os.listdir(WORKSPACE_DIR) or len(os.listdir(WORKSPACE_DIR)) <= 1:
        clone_repo()
        
    os.chdir(WORKSPACE_DIR)
    
    # Nginx install check
    subprocess.run("apt-get update && apt-get install -y nginx", shell=True, check=False)
    
    engine = EditEngine(WORKSPACE_DIR)
    
    for attempt in range(MAX_AUTO_FIXES):
        stack = detect_stack()
        log(f"Detected stack: {stack['type']}, running cmd: {stack['cmd']}")
        
        # Start app
        app_process = subprocess.Popen(
            f"{stack['cmd']} > /tmp/app.log 2>&1", 
            shell=True,
            cwd=WORKSPACE_DIR,
            preexec_fn=os.setsid
        )
        
        config_nginx(stack["port"])
        
        # Wait for boot
        log("Waiting 10s for app to boot...")
        time.sleep(10)
        
        healthy, err = check_health()
        if healthy:
            log("Application is healthy and serving on port 80!")
            while True:
                time.sleep(60)
        else:
            log(f"Health check failed (attempt {attempt+1}/{MAX_AUTO_FIXES}): {err}")
            logs = get_server_logs()
            log(f"App logs: {logs}")
            
            # Kill process
            try:
                os.killpg(os.getpgid(app_process.pid), 9)
            except:
                pass
                
            log("Triggering EditEngine for self-healing...")
            engine.route("Fix the application crash based on these logs.", logs)

    log("Max auto-fixes reached. Deployment failed.")

if __name__ == "__main__":
    main()
