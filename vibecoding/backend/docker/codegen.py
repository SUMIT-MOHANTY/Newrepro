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
        # AI settings with USE_BRN_LLAMA support (DSuite-style)
        use_brn = os.environ.get('USE_BRN_LLAMA', 'false').lower().strip() in ('true', '1', 'yes')
        
        if use_brn:
            # BRN Llama configuration
            self.api_key = os.environ.get('BRN_AGENT_ID', '')
            self.api_url = os.environ.get('BRN_LLAMA_URL', 'https://brn-llama.bourntec.com/api/process')
            self.ai_model = os.environ.get('BRN_MODEL', 'BournAI')
            self.ai_provider = 'bournai'
        else:
            # OpenAI-compatible configuration (NVIDIA, OpenAI, etc.)
            self.api_key = os.environ.get('AI_API_KEY') or os.environ.get('NVIDIA_API_KEY', '')
            self.api_url = os.environ.get('AI_BASE_URL') or os.environ.get('AI_API_URL', 'https://integrate.api.nvidia.com/v1/chat/completions')
            self.ai_model = os.environ.get('AI_MODEL', 'openai/gpt-oss-120b')
            self.ai_provider = os.environ.get('AI_PROVIDER', 'openai').lower().strip()
        
        self.ai_timeout = int(os.environ.get('AI_TIMEOUT', '120'))
        
        # Paths
        self.versions_dir = Path(os.environ.get('PROJECT_VERSIONS_DIR', '/project/versions'))
        self.socket_path = os.environ.get('SUPERVISOR_SOCKET', '/tmp/supervisor.sock')
        self.port = os.environ.get('PORT', '8080')

    def log(self, emoji, message):
        timestamp = time.strftime("%H:%M:%S")
        print(f"[{timestamp}] {emoji} {message}", flush=True)

    def _call_ai(self, prompt: str) -> str:
        import requests
        self.log("🤖", "Calling AI for code generation...")

        provider = self.ai_provider

        try:
            if provider == 'bournai':
                headers = {"Content-Type": "application/json"}
                payload = {
                    "agent_id": self.api_key,
                    "model": self.ai_model or "BournAI",
                    "platform_id": os.environ.get('BRN_PLATFORM_ID', 'DSuite'),
                    "stream": True,
                    "prompt": prompt,
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

            return content

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

        ai_prompt = f"""You are an expert developer generating a complete, working application.
Generate a bash script that will create all necessary files and set up the project.

════════════════════════════════════════════════════
 DEPLOYMENT ENVIRONMENT
════════════════════════════════════════════════════
- Running in Docker container (Ubuntu 22.04)
- Pre-installed: Python3, pip3, Node.js 18, npm, Nginx, serve, git, curl
- Working directory: /project/workspace
- Target port: {self.port}
- An AI agent will auto-detect the stack and run: install → build → serve

════════════════════════════════════════════════════
 YOUR TASK
════════════════════════════════════════════════════
Generate a bash script that creates ALL project files using cat with heredoc syntax.
The script will be executed to set up the complete project structure.

════════════════════════════════════════════════════
 BASH SCRIPT FORMAT (CRITICAL)
════════════════════════════════════════════════════
Use this EXACT format for creating files:

#!/bin/bash
set -e  # Exit on any error

# Create directory structure
mkdir -p src/components
mkdir -p public

# Create package.json
cat > package.json << 'PACKAGE_JSON_EOF'
{{
  "name": "my-app",
  "version": "1.0.0",
  "type": "module",
  "scripts": {{
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview"
  }},
  "dependencies": {{
    "react": "^18.2.0",
    "react-dom": "^18.2.0"
  }},
  "devDependencies": {{
    "@vitejs/plugin-react": "^4.2.0",
    "vite": "^5.0.0"
  }}
}}
PACKAGE_JSON_EOF

# Create index.html
cat > index.html << 'INDEX_HTML_EOF'
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>My App</title>
</head>
<body>
  <div id="root"></div>
  <script type="module" src="/src/main.jsx"></script>
</body>
</html>
INDEX_HTML_EOF

# Create vite.config.js
cat > vite.config.js << 'VITE_CONFIG_EOF'
import {{ defineConfig }} from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({{
  plugins: [react()],
  server: {{
    host: '0.0.0.0',
    port: 3000
  }}
}})
VITE_CONFIG_EOF

# Create src/main.jsx
cat > src/main.jsx << 'MAIN_JSX_EOF'
import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
)
MAIN_JSX_EOF

# Create src/App.jsx
cat > src/App.jsx << 'APP_JSX_EOF'
import React from 'react'
import './App.css'

function App() {{
  return (
    <div className="app">
      <h1>Hello World</h1>
    </div>
  )
}}

export default App
APP_JSX_EOF

# Create src/App.css
cat > src/App.css << 'APP_CSS_EOF'
.app {{
  padding: 2rem;
  text-align: center;
}}
APP_CSS_EOF

echo "✅ Project setup complete!"

════════════════════════════════════════════════════
 CRITICAL RULES
════════════════════════════════════════════════════
1. Use 'FILENAME_EOF' as heredoc delimiter (unique per file)
2. Use single quotes around delimiter: << 'EOF' (prevents variable expansion)
3. For JSON files, escape {{ as {{{{ and }} as }}}}
4. Include ALL necessary files (package.json, config files, source files)
5. Create directories with mkdir -p before creating files in them
6. For React/Vite: index.html at root, src/main.jsx, src/App.jsx, package.json, vite.config.js
7. For Python: app.py, requirements.txt
8. For static sites: index.html, styles.css, script.js
9. Choose the BEST stack for the user's request
10. Make the code COMPLETE and WORKING - no placeholders or TODOs

════════════════════════════════════════════════════
 OUTPUT FORMAT
════════════════════════════════════════════════════
Return ONLY the bash script. No explanations, no markdown fences, no extra text.
Start with #!/bin/bash and end with the last file creation.

USER REQUEST: {prompt}

Generate the complete bash script now:"""
        try:
            response = self._call_ai(ai_prompt)
            
            # Extract bash script from response
            script_content = None
            
            # Try to extract from markdown code block
            if "```bash" in response or "```sh" in response:
                import re
                match = re.search(r'```(?:bash|sh)\s*\n(.*?)```', response, re.DOTALL)
                if match:
                    script_content = match.group(1).strip()
            
            # If no code block, check if response starts with shebang
            if not script_content:
                if response.strip().startswith('#!/bin/bash') or response.strip().startswith('#!/bin/sh'):
                    script_content = response.strip()
            
            # If still no script, try to find it anywhere in the response
            if not script_content:
                import re
                match = re.search(r'(#!/bin/(?:ba)?sh.*)', response, re.DOTALL)
                if match:
                    script_content = match.group(1).strip()
            
            if not script_content:
                self.log("❌", "Could not extract bash script from AI response")
                self.log("📄", f"Response preview: {response[:500]}")
                return None
            
            # Write the script to a file
            script_path = version_path / "setup.sh"
            script_path.write_text(script_content)
            script_path.chmod(0o755)  # Make executable
            
            self.log("📝", f"Generated setup script: {script_path}")
            
            # Execute the script to create all files
            self.log("🔨", "Executing setup script...")
            result = subprocess.run(
                ['bash', str(script_path)],
                cwd=str(version_path),
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode != 0:
                self.log("❌", f"Setup script failed with exit code {result.returncode}")
                self.log("📄", f"STDOUT: {result.stdout}")
                self.log("📄", f"STDERR: {result.stderr}")
                return None
            
            self.log("✅", "Setup script executed successfully")
            self.log("📄", result.stdout)
            
            # Count created files
            created_files = list(version_path.rglob('*'))
            file_count = len([f for f in created_files if f.is_file() and f.name != 'setup.sh'])
            
            self.log("✅", f"Created {file_count} files in {version_path}")
            
            # Create metadata.json
            metadata = {
                "prompt": prompt,
                "version": version_id,
                "timestamp": time.time(),
                "project_type": "auto-detected"
            }
            
            metadata_path = version_path / "metadata.json"
            metadata_path.write_text(json.dumps(metadata, indent=2))

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
