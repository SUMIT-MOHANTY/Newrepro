#!/usr/bin/env python3
"""
D-Suite Deploy Agent
Runs inside the Preview Docker container.
Handles cloning, dependency installation, running the app, Nginx reverse proxying,
and autonomous self-healing for deployment failures.

Logs are streamed in real-time to the BRD Analyzer backend via the report() function,
which mirrors the VibeCoding ai-agent.py report pattern.
"""

import os
import sys
import json
import time
import subprocess
import requests
import re
import threading
from pathlib import Path
from typing import Dict, Any, List, Optional

WORKSPACE_DIR = Path("/workspace")
MAX_AUTO_FIXES = 5

# ── Reporting configuration (set via environment variables by the host) ──────
BACKEND_URL = os.environ.get("BACKEND_URL", "http://host.docker.internal:8000")
PROJECT_TOKEN = os.environ.get("PROJECT_TOKEN", "")

def log(msg: str):
    """Print to stdout (captured as container docker logs)."""
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def report(msg: str, metadata: Optional[Dict[str, Any]] = None):
    """
    Send a log message to the BRD Analyzer backend.
    This mirrors the report() function in VibeCoding's ai-agent.py.
    The backend broadcasts these to connected WebSocket clients in real-time.
    """
    # Always print to stdout (docker logs)
    log(msg)

    if not PROJECT_TOKEN:
        return  # No project token, skip reporting

    payload = {
        "project_token": PROJECT_TOKEN,
        "content": msg,
        "metadata": metadata or {},
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    try:
        requests.post(
            f"{BACKEND_URL}/agents/preview/log",
            json=payload,
            timeout=5,
        )
    except Exception as e:
        # Never let reporting errors crash the agent
        print(f"[report error] {e}", flush=True)


def tail_log_file():
    log_path = Path("/tmp/app.log")
    last_ino = None
    f = None
    log("Started background tail thread for /tmp/app.log")
    while True:
        try:
            if not log_path.exists():
                if f:
                    f.close()
                    f = None
                time.sleep(0.5)
                continue

            current_ino = log_path.stat().st_ino
            if f is None or current_ino != last_ino:
                if f:
                    f.close()
                f = open(log_path, "r", encoding="utf-8", errors="replace")
                last_ino = current_ino
                log(f"Tailing new instance of /tmp/app.log (inode: {last_ino})")

            line = f.readline()
            if not line:
                time.sleep(0.1)
                continue
            # Print directly to system stdout (docker logs)
            sys.stdout.write(line)
            sys.stdout.flush()
        except Exception as e:
            time.sleep(0.5)


def _is_brn_llama_enabled() -> bool:
    use_brn = os.environ.get('USE_BRN_LLAMA', 'false').lower().strip()
    return use_brn in ('true', '1', 'yes')


def extract_content(data: dict) -> str:
    """Extract content from various LLM response structures (Claude Sonnet, ChatGPT-OSS/Nvidia, etc.)."""
    if not isinstance(data, dict):
        return ""
    
    # 1. Claude Sonnet (Anthropic-style): {"content": [{"type": "text", "text": "..."}]}
    content_list = data.get("content")
    if isinstance(content_list, list):
        parts = []
        for block in content_list:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        if parts:
            return "".join(parts)
            
    # 2. ChatGPT-OSS / NVIDIA API (OpenAI-compatible): choices[0].message.content
    choices = data.get("choices")
    if isinstance(choices, list) and len(choices) > 0:
        message = choices[0].get("message", {})
        content = message.get("content", "")
        if content:
            return content

    # 3. Generic BRN Llama / fallback fields
    for key in ("response", "text"):
        val = data.get(key)
        if val and isinstance(val, str):
            return val

    # 4. Fallback: plain content string
    plain = data.get("content")
    if isinstance(plain, str) and plain:
        return plain

    return ""


def call_llm(messages: List[Dict[str, str]], temperature=0.1) -> str:
    if _is_brn_llama_enabled():
        url = os.environ.get("BRN_LLAMA_URL", "https://brn-llama.bourntec.com/api/process")
        key = os.environ.get("BRN_AGENT_ID", "")
        model = os.environ.get("BRN_MODEL", "BournAI")
        provider = "bournai"
    else:
        url = os.environ.get("AI_API_URL") or os.environ.get("AI_BASE_URL") or os.environ.get("LLM_API_URL", "")
        key = os.environ.get("AI_API_KEY") or os.environ.get("LLM_API_KEY", "")
        model = os.environ.get("AI_MODEL") or os.environ.get("LLM_MODEL", "gpt-4o-mini")
        provider = os.environ.get("AI_PROVIDER", "openai").lower().strip()

    if not url or (provider != 'bournai' and not key):
        log("LLM API endpoint or API Key not configured. Cannot use EditEngine.")
        return ""

    headers = {
        "Content-Type": "application/json"
    }

    if provider == 'bournai':
        parts = []
        for m in messages:
            role = m.get('role', 'user')
            content = m.get('content', '')
            tag = {'system': '[System]', 'user': '[User]', 'assistant': '[Assistant]'}.get(role, f'[{role}]')
            parts.append(f'{tag}\n{content}')
        
        payload = {
            'agent_id': key,
            'model': model,
            'platform_id': os.environ.get('BRN_PLATFORM_ID', 'DSuite'),
            'stream': False,
            'prompt': '\n\n'.join(parts),
        }
        
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=60)
            response.raise_for_status()
            data = response.json()
            return extract_content(data)
        except Exception as e:
            log(f"BRN Llama Call Failed: {e}")
            return ""
    else:
        headers["Authorization"] = f"Bearer {key}"
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
            return extract_content(data)
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

        context_str = "\n".join(f"--- {k} ---\n{v['content']}" for k, v in context_files.items())

        system_msg = "You are an autonomous code repair agent. Provide JSON operations to fix the deployment error. You must output ONLY a valid JSON object matching the requested schema. Do not output any conversational prose, think blocks, or code blocks outside the JSON."
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
        report("🤖 [AI Call] Preparing healing prompt for LLM...")
        log(f"--- [AI PROMPT SENT TO LLM] ---\n{user_msg}\n--- [END OF PROMPT] ---")

        raw = call_llm([{"role": "system", "content": system_msg}, {"role": "user", "content": user_msg}])
        if not raw:
            report("❌ [AI Call] LLM returned an empty response or call failed.")
            return False

        report(f"🤖 [AI Call] Raw AI Response received.")

        try:
            content = raw.strip()
            
            # Strip think tags if the LLM output contains reasoning blocks
            content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL)
            
            # Find bounds of the JSON object
            start_idx = content.find("{")
            end_idx = content.rfind("}")
            if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                content = content[start_idx:end_idx + 1]
            
            plan = json.loads(content)
            ops = plan.get("operations", [])
            report(f"🔧 [AI Parser] Extracted {len(ops)} self-healing operations to apply.")
            for op in ops:
                self._apply_op(op)
            return True
        except Exception as e:
            report(f"❌ [AI Edit] EditEngine failed to parse/apply operations: {e}")
            return False

    def _apply_op(self, op):
        op_type = op.get("op_type")
        rel_path = op.get("file")
        new_content = op.get("new_content", "")
        abs_path = self.ws / rel_path
        abs_path.parent.mkdir(parents=True, exist_ok=True)

        report(f"🔨 [AI Patch] Executing operation '{op_type}' on '{rel_path}'")
        if op_type == "CREATE_FILE" or op_type == "FULL_REWRITE":
            abs_path.write_text(new_content, encoding="utf-8")
            report(f"✅ [AI Patch] Successfully wrote file: {rel_path} ({len(new_content)} chars)")
        elif op_type == "REPLACE_LINES":
            if abs_path.exists():
                lines = abs_path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
                start = max(0, int(op.get("start_line", 1)) - 1)
                end = int(op.get("end_line", start + 1))
                new_lines = [l if l.endswith("\n") else l + "\n" for l in new_content.splitlines()] or ["\n"]
                lines[start:end] = new_lines
                abs_path.write_text("".join(lines), encoding="utf-8")
                report(f"✅ [AI Patch] Successfully replaced lines {start+1} to {end} in {rel_path}")


def detect_stack():
    # Recursive search for package/dependency configurations
    skip_dirs = {"node_modules", ".git", "venv", "__pycache__"}
    candidates = []

    report("🔍 [Stack Scanner] Traversing workspace directories to detect stack type...")
    for root, dirs, files in os.walk(WORKSPACE_DIR):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        depth = len(Path(root).relative_to(WORKSPACE_DIR).parts)
        if depth > 3:
            continue

        if "package.json" in files:
            candidates.append((root, "package.json"))
        if "requirements.txt" in files or "pyproject.toml" in files:
            candidates.append((root, "python"))
        if "index.html" in files:
            candidates.append((root, "static"))

    target_dir = str(WORKSPACE_DIR)
    stack_type = "static"
    cmd = "python3 -m http.server 8000"
    port = 8000

    node_cand = [c for c in candidates if c[1] == "package.json"]
    py_cand = [c for c in candidates if c[1] == "python"]
    static_cand = [c for c in candidates if c[1] == "static"]

    if node_cand:
        target_dir = node_cand[0][0]
        pjson_path = Path(target_dir) / "package.json"
        text = pjson_path.read_text(encoding="utf-8", errors="ignore")
        stack_type = "node"
        if "next" in text:
            cmd = "npm install && npm run build && npm run dev"
            port = 3000
        elif "vite" in text:
            cmd = "npm install && npm run build && npm run dev -- --host 0.0.0.0"
            port = 5173
        else:
            cmd = "npm install && npm start"
            port = 3000
    elif py_cand:
        target_dir = py_cand[0][0]
        stack_type = "python"
        has_reqs = (Path(target_dir) / "requirements.txt").exists()
        has_pyproject = (Path(target_dir) / "pyproject.toml").exists()
        text = ""
        if has_reqs:
            text = (Path(target_dir) / "requirements.txt").read_text(encoding="utf-8", errors="ignore").lower()
        elif has_pyproject:
            text = (Path(target_dir) / "pyproject.toml").read_text(encoding="utf-8", errors="ignore").lower()

        if "fastapi" in text or "uvicorn" in text:
            files_in_dir = os.listdir(target_dir)
            if "main.py" in files_in_dir:
                cmd = "pip install -r requirements.txt && uvicorn main:app --host 0.0.0.0 --port 8000"
            else:
                cmd = "pip install -r requirements.txt && uvicorn app:app --host 0.0.0.0 --port 8000"
            port = 8000
        elif "flask" in text:
            cmd = "pip install -r requirements.txt && flask run --host=0.0.0.0 --port 5000"
            port = 5000
        else:
            cmd = "pip install -r requirements.txt && python main.py"
            port = 8000
    elif static_cand:
        target_dir = static_cand[0][0]
        stack_type = "static"
        cmd = "python3 -m http.server 8000"
        port = 8000

    report(f"🎯 [Stack Scanner] Detected stack: {stack_type.upper()} in directory: {target_dir}")
    return {"type": stack_type, "cmd": cmd, "port": port, "cwd": target_dir}


def config_nginx(app_port: int):
    conf = f"""
server {{
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;

    location / {{
        proxy_pass http://127.0.0.1:{app_port};
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }}
}}
"""
    report(f"⚙️ [Nginx Manager] Exposing local port {app_port} via Nginx reverse proxy on port 80...")
    Path("/etc/nginx/sites-available/default").write_text(conf, encoding="utf-8")
    subprocess.run(["nginx", "-s", "reload"], check=False)
    subprocess.run(["service", "nginx", "restart"], check=False)
    report("⚙️ [Nginx Manager] Nginx restarted successfully.")


def check_health() -> tuple:
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
        log_text += Path("/tmp/app.log").read_text(encoding="utf-8", errors="replace")[-2000:]
    return log_text


def clone_repo():
    auth_url = os.environ.get("GIT_AUTH_URL")
    config_args = os.environ.get("GIT_CONFIG_ARGS", "")
    branch = os.environ.get("SPRINT_BRANCH", "agent/integration")

    if not auth_url:
        report("❌ [Git Manager] GIT_AUTH_URL not provided.")
        return

    safe_url = auth_url.split('@')[-1] if '@' in auth_url else auth_url
    report(f"🚀 [Git Manager] Cloning branch '{branch}' from '{safe_url}'...")
    os.chdir("/")

    cmd = ["git"]
    if config_args:
        try:
            args_list = json.loads(config_args)
            cmd.extend(args_list)
        except Exception as e:
            report(f"⚠️ [Git Manager] Failed to parse extra config args: {e}")

    cmd.extend([
        "clone", "--branch", branch, "--depth", "1",
        "--single-branch", "--no-tags",
        "-c", "http.postBuffer=524288000",
        auth_url, "/workspace_temp"
    ])

    report(f"🚀 [Git Manager] Command execution: {' '.join(cmd[:-1])} <SECRET_URL>")
    result = subprocess.run(cmd, check=False, capture_output=True, text=True)

    if result.returncode != 0:
        report(f"❌ [Git Manager] Clone failed: {result.stderr[-500:]}")

    if Path("/workspace_temp").exists():
        report("🚀 [Git Manager] Clone successful. Transferring files to /workspace...")
        subprocess.run(["rm", "-rf", "/workspace/*"], check=False)
        subprocess.run("cp -a /workspace_temp/. /workspace/", shell=True, check=False)
        subprocess.run(["rm", "-rf", "/workspace_temp"], check=False)
        report("🚀 [Git Manager] Repository extraction completed.")
    else:
        report("❌ [Git Manager] Repository cloning failed — workspace_temp not found.")


def main():
    report("🏁 D-Suite Deploy Agent initialized.")
    report(f"📡 Backend URL: {BACKEND_URL}")
    report(f"🔑 Project Token: {'set' if PROJECT_TOKEN else 'NOT SET'}")

    # Start the continuous app.log tail thread
    t = threading.Thread(target=tail_log_file, daemon=True)
    t.start()

    if not os.listdir(WORKSPACE_DIR) or len(os.listdir(WORKSPACE_DIR)) <= 1:
        clone_repo()

    os.chdir(WORKSPACE_DIR)

    # Nginx install check (already installed in Dockerfile, this is a safety net)
    report("⚙️ [SysInit] Ensuring Nginx is installed and started...")
    subprocess.run("service nginx start", shell=True, check=False)

    engine = EditEngine(WORKSPACE_DIR)

    for attempt in range(MAX_AUTO_FIXES):
        stack = detect_stack()
        report(f"🚀 [Deploy Core] Attempt {attempt+1}/{MAX_AUTO_FIXES}: Starting application server in {stack['cwd']}...")

        # Start app with log redirection
        app_process = subprocess.Popen(
            f"{stack['cmd']} > /tmp/app.log 2>&1",
            shell=True,
            cwd=stack['cwd'],
            preexec_fn=os.setsid
        )

        config_nginx(stack["port"])

        # Wait for boot
        report("⏳ [Deploy Core] Waiting 15s for application to boot and serve...")
        time.sleep(15)

        healthy, err = check_health()
        if healthy:
            report(
                "🎉 [Deploy Core] Application is healthy and responsive on Port 80!",
                metadata={"status": "success", "preview_url": f"/app/{PROJECT_TOKEN}/"}
            )
            report("📡 Keep-alive loops active. Deploy Agent running...")
            while True:
                time.sleep(60)
                # Send periodic heartbeat
                healthy, err = check_health()
                if not healthy:
                    report(f"⚠️ [Keep-alive] Health check failed: {err}")
                    break
        else:
            report(f"⚠️ [Deploy Core] Health check failed: {err}")
            logs = get_server_logs()
            report(f"📋 [Deploy Core] Recent compilation and server logs:\n{logs}")

            # Kill process group
            report("🛑 [Deploy Core] Terminating dead server process group...")
            try:
                os.killpg(os.getpgid(app_process.pid), 9)
            except Exception as ex:
                report(f"⚠️ [Deploy Core] Error killing server group: {ex}")

            report("🤖 [Deploy Core] Initiating AI self-healing repair session...")
            engine.route("Fix the application crash based on these logs.", logs)

    report(
        "❌ [Deploy Core] Maximum auto-fixes reached. Deployment failed.",
        metadata={"status": "error"}
    )


if __name__ == "__main__":
    main()
