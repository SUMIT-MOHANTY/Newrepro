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
        
        try:
            response = requests.post(
                self.api_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.ai_model,
                    "messages": [
                        {"role": "system", "content": "You are a senior full-stack developer. You generate complete, production-ready applications as a JSON file tree."},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.2,
                },
                timeout=self.ai_timeout,
            )
            
            if response.status_code != 200:
                self.log("❌", f"AI API error {response.status_code}: {response.text[:300]}")
                raise Exception(f"AI API error {response.status_code}")

            res_json = response.json()
            content = res_json["choices"][0]["message"]["content"]

            # Extraction logic (handles markdown and raw JSON)
            for pattern in (r"```(?:json)?\s*(\{.*?\})\s*```", r"(\{.*\})"):
                match = re.search(pattern, content, re.DOTALL)
                if match:
                    return json.loads(match.group(1))
            
            self.log("⚠️", "No JSON found in AI response. Content length: " + str(len(content)))
            raise Exception("No JSON found in AI response")
            
        except Exception as e:
            self.log("❌", f"AI call failed: {e}")
            raise

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

        ai_prompt = f"""You are an expert developer generating code for a SINGLE-CONTAINER Docker deployment. The entire app runs as ONE process on ONE port inside a container.

════════════════════════════════════════════════════
 UNDERSTAND THE DEPLOYMENT FIRST
════════════════════════════════════════════════════
Browser → Host Port → Docker Container
                          └── ONE server process (managed by an AI Agent)

There is NO Nginx, NO docker-compose, NO multiple containers. ONE container. ONE process. ONE port ({self.port}).

YOU decide the best structure (folders, files, etc.). Do not force 'frontend/' or 'backend/' folders unless that structure genuinely fits the project.

════════════════════════════════════════════════════
 ABSOLUTE RULES — NEVER BREAK THESE
════════════════════════════════════════════════════

RULE 1 — PORT BINDING
  ✅ Server MUST bind to host 0.0.0.0
  ✅ Read port from PORT environment variable, fallback to {self.port}
     e.g. port = int(os.environ.get("PORT", {self.port}))
  ❌ NEVER hardcode any port other than {self.port}
  ❌ NEVER bind to 127.0.0.1 or localhost

RULE 2 — IF THE PROJECT HAS AN API
  ✅ ALL API routes MUST be prefixed with /api/
  ❌ NEVER create a route at GET "/" if a frontend exists
  ❌ NEVER create bare routes like /users, /todos at root level

RULE 3 — IF THE PROJECT HAS A FRONTEND
  ✅ The server must serve the frontend at "/"
  ✅ For SPA frameworks (React, Vue, Svelte, etc.) the server MUST return index.html for ALL paths that don't match API routes or static files.
  ❌ NEVER spin up a dev server at runtime (no vite dev, npm start, etc.)
  ❌ NEVER use CDN links for frameworks (no unpkg, jsdelivr, etc.). Use npm/yarn.
  ✅ Always use the framework's standard build tool to generate static output.

RULE 4 — API CALLS
  ✅ ALL fetch/axios/http calls MUST use relative URLs (e.g. fetch('/api/todos'))
  ❌ NEVER hardcode hostname, IP, or port in API calls.

RULE 5 — CORS
  ❌ NEVER add CORS middleware unless requested. It's unnecessary on the same port.

RULE 6 — RUN SCRIPT (CRITICAL)
  ✅ ALWAYS include a 'run.sh' bash script at the project root.
  ✅ run.sh MUST handle: dependency installation → build (if needed) → start server.
  ✅ This script is the primary entrypoint for the AI Agent.

RULE 7 — DOCKERFILE
  ✅ Include a Dockerfile as a production reference. 
  ✅ Use multi-stage builds if a build step is needed.
  ✅ Final stage must run ONE process on port {self.port}.

════════════════════════════════════════════════════
 SPA FALLBACK LOGIC
════════════════════════════════════════════════════
Implement this in your server:
  if path starts with "/api/"    → handle as API
  elif static file exists        → serve the file
  else                           → serve index.html

════════════════════════════════════════════════════
 EXPECTED JSON STRUCTURE
════════════════════════════════════════════════════
Return ONLY a raw JSON object:
{{
    "files": {{
        "path/to/file1": "...complete content...",
        "run.sh": "#!/bin/bash\\n...",
        "Dockerfile": "...",
        "metadata.json": {{
            "project_type": "stack name",
            "entrypoint": "main file"
        }}
    }}
}}

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
            
            # The user might want us to also save the prompt for self-healing context
            (version_path / "metadata.json").write_text(json.dumps({
                "prompt": prompt,
                "version": version_id,
                "timestamp": time.time()
            }, indent=2))

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
