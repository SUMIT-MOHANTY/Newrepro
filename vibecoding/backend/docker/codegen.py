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
The entire project runs inside ONE container, but it can have MULTIPLE processes (e.g. a separate frontend and backend) on DIFFERENT ports if needed.

════════════════════════════════════════════════════
 UNDERSTAND THE NETWORKING
════════════════════════════════════════════════════
Browser → Host Ports → Docker Container
                           └── Multiple processes managed by an AI Supervisor

DEFAULT PRIMARY PORT: {{self.port}} (Usually for the Frontend)

════════════════════════════════════════════════════
 ABSOLUTE RULES
════════════════════════════════════════════════════

RULE 1 — PORT BINDING
  ✅ Servers MUST bind to 0.0.0.0 (NOT 127.0.0.1)
  ✅ Primary service should use PORT environment variable (default {self.port})
  ✅ Secondary services should use unique ports (e.g. 5000, 3000).

RULE 2 — MULTI-SERVICE DISCOVERY
  ✅ If you have a separate Backend and Frontend, the Frontend must know how to find the Backend.
  ✅ Use relative paths if possible, or environment variables.

RULE 3 — RUN SCRIPT (CRITICAL)
  ✅ ALWAYS include a 'run.sh' bash script at the project root.
  ✅ run.sh MUST start ALL required services.
  ✅ Use '&' for background processes and 'wait' at the end, or similar.

RULE 4 — SPA FALLBACK
  ✅ If you use a frontend framework, the server MUST handle routing (serve index.html for unknown paths).

════════════════════════════════════════════════════
 EXPECTED JSON STRUCTURE
════════════════════════════════════════════════════
Return ONLY a raw JSON object:
{{
    "files": {{
        "path/to/file1": "...content...",
        "run.sh": "#!/bin/bash\n# start backend\npython app.py &\n# start frontend\nnpm start",
        "metadata.json": {{
            "project_type": "React + Flask",
            "port": {self.port},
            "additional_ports": [5000],
            "entrypoint": "run.sh"
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
