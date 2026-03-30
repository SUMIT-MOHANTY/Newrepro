#!/usr/bin/env python3
import os
import sys
import json
import time
import socket
import re
import subprocess
from pathlib import Path
from typing import Optional

class CodegenAgent:
    def __init__(self):
        # AI settings
        self.api_key = os.environ.get('AI_API_KEY') or os.environ.get('NVIDIA_API_KEY', '')
        self.api_url = os.environ.get('AI_API_URL', 'https://integrate.api.nvidia.com/v1/chat/completions')
        self.ai_model = os.environ.get('AI_MODEL', 'openai/gpt-oss-120b')
        self.ai_timeout = int(os.environ.get('AI_TIMEOUT', '120'))
        
        # Paths
        self.versions_dir = Path(os.environ.get('PROJECT_VERSIONS_DIR', '/project/versions'))
        self.socket_path = os.environ.get('SUPERVISOR_SOCKET', '/tmp/supervisor.sock')
        self.port = os.environ.get('PORT', '8080')

    def log(self, emoji, message):
        timestamp = time.strftime("%H:%M:%S")
        print(f"[{timestamp}] {emoji} {message}", flush=True)

    def _call_ai(self, prompt: str) -> dict:
        import requests
        self.log("🤖", "Calling AI for code generation...")

        provider = os.environ.get('AI_PROVIDER', 'openai').lower().strip()

        try:
            if provider == 'bournai':
                headers = {"Content-Type": "application/json"}
                payload = {
                    "agent_id": self.api_key,
                    "model": self.ai_model or "BournAI",
                    "platform_id": os.environ.get('BOURNAI_PLATFORM_ID', 'DSuite'),
                    "stream": True,
                    "prompt": f"You are a senior full-stack developer. You generate complete, production-ready applications as a JSON file tree.\n\n{prompt}",
                }
                is_stream = True
            else:
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                }
                payload = {
                    "model": self.ai_model,
                    "messages": [
                        {"role": "system", "content": "You are a senior full-stack developer. You generate complete, production-ready applications as a JSON file tree."},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.2,
                }
                is_stream = False

            response = requests.post(
                self.api_url,
                headers=headers,
                json=payload,
                stream=is_stream,
                timeout=self.ai_timeout,
            )

            if response.status_code != 200:
                self.log("❌", f"AI API error {response.status_code}: {response.text[:300]}")
                raise Exception(f"AI API error {response.status_code}")

            if is_stream:
                content = self._aggregate_stream(response, provider)
            else:
                res_json = response.json()
                content = res_json["choices"][0]["message"]["content"]

            for pattern in (r"```(?:json)?\s*(\{.*?\})\s*```", r"(\{.*\})"):
                match = re.search(pattern, content, re.DOTALL)
                if match:
                    return json.loads(match.group(1))

            self.log("⚠️", "No JSON found in AI response. Content length: " + str(len(content)))
            raise Exception("No JSON found in AI response")

        except Exception as e:
            self.log("❌", f"AI call failed: {e}")
            raise

    def _aggregate_stream(self, response, provider: str) -> str:
        """Aggregate SSE stream into a single string."""
        content = ""
        for raw_line in response.iter_lines():
            if not raw_line:
                continue
            line = raw_line.decode("utf-8")
            if line.startswith("data: "):
                line = line[6:]
            if line.strip() == "[DONE]":
                break
            try:
                chunk = json.loads(line)
                if provider == 'bournai':
                    for part in chunk.get("content", []):
                        if isinstance(part, dict) and part.get("type") == "text":
                            content += part.get("text", "")
                    if chunk.get("stop_reason") == "end_turn":
                        break
                else:
                    if "choices" in chunk and chunk["choices"]:
                        delta = chunk["choices"][0].get("delta", {})
                        if delta.get("content"):
                            content += delta["content"]
            except json.JSONDecodeError:
                continue
        return content

    def _signal_supervisor(self, version_id: str):
        """Tells the supervisor to activate the newly generated version"""
        if not os.path.exists(self.socket_path):
            self.log("⚠️", f"Supervisor socket {self.socket_path} not found. Skipping signal.")
            return

        self.log("🔌", f"Signaling supervisor to switch to {version_id}...")
        try:
            # We try a few times in case supervisor is still booting
            for i in range(5):
                try:
                    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                        s.connect(self.socket_path)
                        cmd = {"action": "switch", "version_id": version_id}
                        s.sendall(json.dumps(cmd).encode('utf-8'))
                        resp = s.recv(2048).decode('utf-8')
                        self.log("🛡️", f"Supervisor response: {resp}")
                        return
                except (ConnectionRefusedError, FileNotFoundError):
                    time.sleep(1)
            
            self.log("❌", "Failed to connect to supervisor socket after several attempts")
        except Exception as e:
            self.log("❌", f"Failed to signal supervisor: {e}")

    def generate(self, prompt: str) -> Optional[str]:
        if not prompt:
            self.log("❌", "No USER_PROMPT provided")
            return None

        version_id = f"v{int(time.time())}"
        version_path = self.versions_dir / version_id
        version_path.mkdir(parents=True, exist_ok=True)

        self.log("🏗️", f"Generating Version {version_id}...")

        ai_prompt = f"""You are an expert developer generating code for a SINGLE-CONTAINER Docker deployment.
The container has Python 3, Node.js 18, Nginx, and `serve` (static file server) pre-installed.
An AI DevOps agent inside the container auto-detects the stack, runs setup/install, builds, and starts the server.

════════════════════════════════════════════════════
 DEPLOYMENT ENVIRONMENT
════════════════════════════════════════════════════
Browser → Host Ports → Docker Container
                           └── AI Agent auto-manages: install → build → serve

DEFAULT PRIMARY PORT: {self.port}
Pre-installed: Python3, pip3, Node.js 18, npm, Nginx, serve, git, curl

════════════════════════════════════════════════════
 ABSOLUTE RULES
════════════════════════════════════════════════════

RULE 1 — PORT BINDING
  ✅ Servers MUST bind to 0.0.0.0 (NOT 127.0.0.1)
  ✅ Primary service uses PORT env var (default {self.port})

RULE 2 — COMPLETE BUILDABLE CODE
  ✅ All source files must be COMPLETE — no truncation or placeholders
  ✅ If a package manager is used (npm, pip, etc.), include the manifest listing ALL dependencies
  ✅ Choose the BEST technology stack for the user's request — do NOT default to any specific stack

RULE 3 — STRUCTURE REFERENCE (follow the standard patterns for whichever stack you choose)
  The AI agent inside the container auto-detects ANY stack, installs deps, builds, and serves.
  Here are deployment patterns for COMMON frameworks (use the right one, or invent your own):

  React (CRA):   public/index.html + src/index.js + src/App.js + package.json (with react-scripts)
  React (Vite):  index.html + src/main.jsx + src/App.jsx + package.json + vite.config.js
  Vue.js:        src/main.js + src/App.vue + package.json
  Angular:       src/app/ + package.json (with @angular/cli)
  Svelte:        src/App.svelte + package.json
  Next.js:       pages/index.js (or app/page.js) + package.json (with next)
  Python:        app.py + requirements.txt (bind to 0.0.0.0, use PORT env var)
  Node.js:       server.js + package.json (bind to 0.0.0.0, use PORT env var)
  Go:            main.go + go.mod
  Static:        index.html (no manifest needed — served directly)
  ANY OTHER:     Include the standard project structure for that stack

RULE 4 — SPA FALLBACK
  ✅ For frontend frameworks, `serve -s build` handles SPA routing automatically.

════════════════════════════════════════════════════
 EXPECTED JSON STRUCTURE
════════════════════════════════════════════════════
Return ONLY a raw JSON object (no markdown fences):
{{
    "files": {{
        "path/to/file1": "...complete file content...",
        "package.json": "...complete valid JSON...",
        "metadata.json": {{
            "project_type": "React | Vue | Flask | Static HTML | etc.",
            "port": {self.port}
        }}
    }}
}}

CRITICAL: Every file must contain COMPLETE, WORKING content. Do NOT truncate.
The metadata.json helps the AI agent understand the project type.
Do NOT include run.sh — the AI agent auto-detects how to run the project.

USER REQUEST: {prompt}
"""
        try:
            result = self._call_ai(ai_prompt)
            files = result.get("files", {})
            if not files:
                raise Exception("AI returned empty file list")

            for filepath, content in files.items():
                full_path = version_path / filepath
                full_path.parent.mkdir(parents=True, exist_ok=True)
                
                if isinstance(content, (dict, list)):
                    full_path.write_text(json.dumps(content, indent=2))
                else:
                    full_path.write_text(content)

            self.log("✅", f"Successfully wrote {len(files)} files to {version_path}")
            
            # Merge system metadata with AI-generated metadata if any
            metadata = {}
            existing_metadata_path = version_path / "metadata.json"
            if existing_metadata_path.exists():
                try:
                    metadata = json.loads(existing_metadata_path.read_text())
                except:
                    pass
            
            metadata.update({
                "prompt": prompt,
                "version": version_id,
                "timestamp": time.time()
            })
            existing_metadata_path.write_text(json.dumps(metadata, indent=2))

            self._signal_supervisor(version_id)
            return version_id

        except Exception as e:
            self.log("❌", f"Codegen failure: {e}")
            return None

if __name__ == "__main__":
    prompt = os.environ.get('USER_PROMPT')
    if not prompt:
        # Check if passed via command line
        if len(sys.argv) > 1:
            prompt = " ".join(sys.argv[1:])
    
    if prompt:
        CodegenAgent().generate(prompt)
    else:
        print("Usage: USER_PROMPT='...' python3 codegen.py")
        sys.exit(1)
