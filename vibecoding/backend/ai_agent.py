"""
AI Agent that runs inside container
Handles code generation, execution, and error fixing
"""
import os
import sys
import json
import subprocess
import logging
from pathlib import Path
from typing import Dict, List, Optional
import anthropic
import openai

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CodeExecutionAgent:
    """AI Agent that builds, runs, and fixes code inside container"""
    
    def __init__(self):
        self.workspace = Path("/workspace/projects")
        self.workspace.mkdir(exist_ok=True)
        
        # Initialize AI client (supports both OpenAI and Anthropic)
        self.ai_provider = os.getenv("AI_PROVIDER", "anthropic")
        if self.ai_provider == "anthropic":
            self.client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
            self.model = "claude-3-5-sonnet-20241022"
        else:
            self.client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            self.model = "gpt-4"
    
    def analyze_requirements(self, user_message: str) -> Dict:
        """Analyze user requirements and determine what needs to be built"""
        prompt = f"""Analyze this user request and extract:
1. Programming languages needed
2. Frameworks/libraries needed
3. Database requirements
4. Project structure
5. Main functionality

User request: {user_message}

Respond in JSON format:
{{
    "languages": ["python", "javascript"],
    "frameworks": ["flask", "react"],
    "databases": ["sqlite"],
    "project_type": "fullstack_web_app",
    "description": "Todo app with Flask backend and React frontend"
}}
"""
        
        response = self._call_ai(prompt)
        try:
            return json.loads(response)
        except:
            return {
                "languages": ["python"],
                "frameworks": ["flask"],
                "databases": [],
                "project_type": "web_app",
                "description": user_message
            }
    
    def create_dockerfile(self, requirements: Dict) -> str:
        """Dynamically create Dockerfile based on requirements"""
        languages = requirements.get("languages", [])
        frameworks = requirements.get("frameworks", [])
        
        dockerfile_content = "FROM ubuntu:22.04\n\n"
        dockerfile_content += "ENV DEBIAN_FRONTEND=noninteractive\n\n"
        dockerfile_content += "RUN apt-get update && apt-get install -y \\\n"
        
        # Add language-specific installations
        if "python" in languages:
            dockerfile_content += "    python3 python3-pip \\\n"
        if "javascript" in languages or "nodejs" in languages:
            dockerfile_content += "    nodejs npm \\\n"
        if "go" in languages:
            dockerfile_content += "    golang-go \\\n"
        if "rust" in languages:
            dockerfile_content += "    rustc cargo \\\n"
        if "java" in languages:
            dockerfile_content += "    openjdk-11-jdk \\\n"
        if "ruby" in languages:
            dockerfile_content += "    ruby \\\n"
        if "php" in languages:
            dockerfile_content += "    php \\\n"
        
        dockerfile_content += "    curl wget \\\n"
        dockerfile_content += "    && rm -rf /var/lib/apt/lists/*\n\n"
        
        # Install framework-specific packages
        if "python" in languages and frameworks:
            python_packages = []
            for fw in frameworks:
                if fw in ["flask", "django", "fastapi", "streamlit"]:
                    python_packages.append(fw)
            if python_packages:
                dockerfile_content += f"RUN pip3 install {' '.join(python_packages)}\n\n"
        
        dockerfile_content += "WORKDIR /app\n"
        dockerfile_content += "EXPOSE 3000 5000 8000 8080\n"
        
        return dockerfile_content
    
    def generate_code(self, requirements: Dict) -> Dict[str, str]:
        """Generate code files based on requirements"""
        prompt = f"""Generate complete, working code for this project:

Requirements: {json.dumps(requirements, indent=2)}

Generate ALL necessary files with proper structure.
Use file markers like:
# FILE: app.py
# FILE: requirements.txt
# FILE: templates/index.html

Make sure the code is:
1. Complete and runnable
2. Includes all imports
3. Has proper error handling
4. Includes requirements/package files
5. Ready to run immediately

Generate the code now:
"""
        
        response = self._call_ai(prompt)
        return self._parse_files_from_response(response)
    
    def write_files(self, project_name: str, files: Dict[str, str]) -> Path:
        """Write generated files to disk"""
        project_dir = self.workspace / project_name
        project_dir.mkdir(exist_ok=True)
        
        for filepath, content in files.items():
            file_path = project_dir / filepath
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            logger.info(f"✅ Created: {filepath}")
        
        return project_dir
    
    def install_dependencies(self, project_dir: Path, requirements: Dict) -> bool:
        """Install project dependencies"""
        try:
            # Python dependencies
            if (project_dir / "requirements.txt").exists():
                logger.info("📦 Installing Python dependencies...")
                result = subprocess.run(
                    ["pip3", "install", "-r", "requirements.txt"],
                    cwd=project_dir,
                    capture_output=True,
                    text=True
                )
                if result.returncode != 0:
                    logger.error(f"Pip install failed: {result.stderr}")
                    return False
            
            # Node.js dependencies
            if (project_dir / "package.json").exists():
                logger.info("📦 Installing Node.js dependencies...")
                result = subprocess.run(
                    ["npm", "install"],
                    cwd=project_dir,
                    capture_output=True,
                    text=True
                )
                if result.returncode != 0:
                    logger.error(f"npm install failed: {result.stderr}")
                    return False
            
            return True
        except Exception as e:
            logger.error(f"Dependency installation failed: {e}")
            return False
    
    def run_code(self, project_dir: Path, requirements: Dict) -> subprocess.Popen:
        """Run the generated code"""
        languages = requirements.get("languages", [])
        
        # Determine how to run the code
        if "python" in languages:
            if (project_dir / "app.py").exists():
                cmd = ["python3", "app.py"]
            elif (project_dir / "main.py").exists():
                cmd = ["python3", "main.py"]
            else:
                py_files = list(project_dir.glob("*.py"))
                if py_files:
                    cmd = ["python3", py_files[0].name]
                else:
                    raise Exception("No Python file found")
        
        elif "javascript" in languages or "nodejs" in languages:
            if (project_dir / "package.json").exists():
                cmd = ["npm", "start"]
            elif (project_dir / "server.js").exists():
                cmd = ["node", "server.js"]
            elif (project_dir / "index.js").exists():
                cmd = ["node", "index.js"]
            else:
                raise Exception("No JavaScript entry point found")
        
        else:
            raise Exception(f"Unsupported language: {languages}")
        
        logger.info(f"🚀 Running: {' '.join(cmd)}")
        process = subprocess.Popen(
            cmd,
            cwd=project_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        return process
    
    def monitor_and_fix(self, process: subprocess.Popen, project_dir: Path, requirements: Dict, max_attempts: int = 3) -> bool:
        """Monitor process for errors and fix them automatically"""
        import time
        
        for attempt in range(max_attempts):
            logger.info(f"🔍 Monitoring attempt {attempt + 1}/{max_attempts}")
            
            # Wait a bit for the process to start
            time.sleep(3)
            
            # Check if process is still running
            if process.poll() is None:
                logger.info("✅ Process is running successfully!")
                return True
            
            # Process died, check errors
            stdout, stderr = process.communicate()
            error_output = stderr + stdout
            
            logger.error(f"❌ Process failed with error:\n{error_output}")
            
            # Ask AI to fix the error
            fix_prompt = f"""The code failed with this error:

{error_output}

Project requirements: {json.dumps(requirements, indent=2)}

Analyze the error and provide:
1. What caused the error
2. How to fix it (install missing package, fix code, etc.)

Respond in JSON:
{{
    "error_type": "missing_dependency",
    "fix_command": "pip3 install flask-cors",
    "explanation": "Missing flask-cors package"
}}
"""
            
            fix_response = self._call_ai(fix_prompt)
            try:
                fix_info = json.loads(fix_response)
                
                # Apply the fix
                if fix_info.get("fix_command"):
                    logger.info(f"🔧 Applying fix: {fix_info['fix_command']}")
                    subprocess.run(
                        fix_info["fix_command"],
                        shell=True,
                        cwd=project_dir,
                        capture_output=True
                    )
                
                # Try running again
                process = self.run_code(project_dir, requirements)
            
            except Exception as e:
                logger.error(f"Failed to apply fix: {e}")
        
        return False
    
    def execute_request(self, user_message: str) -> Dict:
        """Main execution flow"""
        try:
            logger.info(f"📝 User request: {user_message}")
            
            # Step 1: Analyze requirements
            logger.info("🔍 Analyzing requirements...")
            requirements = self.analyze_requirements(user_message)
            logger.info(f"Requirements: {json.dumps(requirements, indent=2)}")
            
            # Step 2: Generate code
            logger.info("💻 Generating code...")
            files = self.generate_code(requirements)
            
            # Step 3: Write files
            project_name = f"project_{hash(user_message) % 10000}"
            logger.info(f"📁 Creating project: {project_name}")
            project_dir = self.write_files(project_name, files)
            
            # Step 4: Install dependencies
            logger.info("📦 Installing dependencies...")
            if not self.install_dependencies(project_dir, requirements):
                return {
                    "success": False,
                    "error": "Failed to install dependencies"
                }
            
            # Step 5: Run code
            logger.info("🚀 Running code...")
            process = self.run_code(project_dir, requirements)
            
            # Step 6: Monitor and fix errors
            success = self.monitor_and_fix(process, project_dir, requirements)
            
            if success:
                return {
                    "success": True,
                    "project_dir": str(project_dir),
                    "message": "Application is running successfully!",
                    "url": "http://localhost:5000"  # TODO: detect actual port
                }
            else:
                return {
                    "success": False,
                    "error": "Failed to run application after multiple attempts"
                }
        
        except Exception as e:
            logger.error(f"Execution failed: {e}")
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "error": str(e)
            }
    
    def _call_ai(self, prompt: str) -> str:
        """Call AI provider"""
        if self.ai_provider == "anthropic":
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}]
            )
            return response.content[0].text
        else:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}]
            )
            return response.choices[0].message.content
    
    def _parse_files_from_response(self, response: str) -> Dict[str, str]:
        """Parse file markers from AI response"""
        import re
        
        files = {}
        file_marker_regex = r'(?:#|//|<!--|/\*)\s*FILE:\s*([^\n]+?)(?:-->|\*/)?'
        matches = list(re.finditer(file_marker_regex, response, re.IGNORECASE))
        
        for i, match in enumerate(matches):
            filename = match.group(1).strip()
            start_pos = match.end()
            end_pos = matches[i + 1].start() if i < len(matches) - 1 else len(response)
            content = response[start_pos:end_pos].strip()
            
            # Remove code block markers if present
            content = re.sub(r'^```[\w]*\n', '', content)
            content = re.sub(r'\n```$', '', content)
            
            files[filename] = content
        
        return files


if __name__ == "__main__":
    # Run as HTTP server to receive requests
    from http.server import HTTPServer, BaseHTTPRequestHandler
    
    agent = CodeExecutionAgent()
    
    class AgentHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            # Health check endpoint
            if self.path == '/health':
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(b'{"status": "healthy"}')
            else:
                self.send_response(404)
                self.end_headers()
        
        def do_POST(self):
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))
            
            user_message = data.get('message', '')
            result = agent.execute_request(user_message)
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(result).encode('utf-8'))
    
    server = HTTPServer(('0.0.0.0', 8001), AgentHandler)
    logger.info("🤖 AI Code Execution Agent running on port 8001")
    server.serve_forever()
