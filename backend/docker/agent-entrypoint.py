#!/usr/bin/env python3
"""
Intelligent Agent Runtime - Auto-detects, installs, and runs any project
"""
import os
import sys
import json
import subprocess
import time
from pathlib import Path

class IntelligentAgent:
    def __init__(self, workspace="/workspace"):
        self.workspace = Path(workspace)
        self.max_retries = 3
        
    def log(self, emoji, message):
        print(f"{emoji} {message}", flush=True)
        
    def run_command(self, cmd, shell=True, check=False):
        """Run command and return output"""
        try:
            result = subprocess.run(
                cmd, 
                shell=shell, 
                capture_output=True, 
                text=True,
                cwd=self.workspace
            )
            return result.returncode == 0, result.stdout, result.stderr
        except Exception as e:
            return False, "", str(e)
    
    def detect_project_type(self):
        """Detect what type of project this is"""
        files = list(self.workspace.rglob("*"))
        filenames = [f.name for f in files if f.is_file()]
        
        self.log("🔍", "Analyzing project structure...")
        
        # Django
        if "manage.py" in filenames:
            return "django"
        
        # Flask
        if any("flask" in f.read_text().lower() for f in files if f.suffix == ".py" and f.is_file()):
            return "flask"
        
        # FastAPI
        if any("fastapi" in f.read_text().lower() for f in files if f.suffix == ".py" and f.is_file()):
            return "fastapi"
        
        # Node.js/React
        if "package.json" in filenames:
            return "nodejs"
        
        # Python generic
        if any(f.suffix == ".py" for f in files):
            return "python"
        
        # HTML/Static
        if any(f.suffix == ".html" for f in files):
            return "static"
        
        return "unknown"
    
    def install_python_deps(self):
        """Install Python dependencies"""
        requirements = self.workspace / "requirements.txt"
        
        if requirements.exists():
            self.log("📦", "Installing Python dependencies...")
            success, stdout, stderr = self.run_command("pip install -r requirements.txt")
            if not success:
                self.log("⚠️", f"Dependency installation warning: {stderr}")
        else:
            self.log("ℹ️", "No requirements.txt found")
    
    def install_node_deps(self):
        """Install Node.js dependencies"""
        package_json = self.workspace / "package.json"
        
        if package_json.exists():
            self.log("📦", "Installing Node.js dependencies...")
            success, stdout, stderr = self.run_command("npm install")
            if not success:
                self.log("⚠️", f"npm install failed: {stderr}")
                return False
            return True
        return True
    
    def run_django(self):
        """Run Django project"""
        self.log("🎯", "Detected: Django Project")
        self.install_python_deps()
        
        # Run migrations
        self.log("🔄", "Running migrations...")
        self.run_command("python manage.py migrate --noinput")
        
        # Start server
        self.log("🚀", "Starting Django server on 0.0.0.0:8000")
        os.execvp("python", ["python", "manage.py", "runserver", "0.0.0.0:8000"])
    
    def run_flask(self):
        """Run Flask project"""
        self.log("🎯", "Detected: Flask Application")
        self.install_python_deps()
        
        # Find main file
        main_file = None
        for name in ["app.py", "main.py", "application.py"]:
            if (self.workspace / name).exists():
                main_file = name
                break
        
        if not main_file:
            self.log("❌", "No Flask entry point found (app.py, main.py)")
            sys.exit(1)
        
        # Set Flask environment
        os.environ["FLASK_APP"] = main_file
        os.environ["FLASK_RUN_HOST"] = "0.0.0.0"
        os.environ["FLASK_RUN_PORT"] = "5000"
        
        self.log("🚀", f"Starting Flask server: {main_file}")
        os.execvp("python", ["python", main_file])
    
    def run_fastapi(self):
        """Run FastAPI project"""
        self.log("🎯", "Detected: FastAPI Application")
        self.install_python_deps()
        
        # Find main file
        main_file = None
        for name in ["main.py", "app.py", "api.py"]:
            if (self.workspace / name).exists():
                main_file = name
                break
        
        if not main_file:
            self.log("❌", "No FastAPI entry point found")
            sys.exit(1)
        
        self.log("🚀", f"Starting FastAPI server: {main_file}")
        os.execvp("python", ["python", main_file])
    
    def run_nodejs(self):
        """Run Node.js project"""
        self.log("🎯", "Detected: Node.js Project")
        
        if not self.install_node_deps():
            sys.exit(1)
        
        # Read package.json for start script
        package_json = self.workspace / "package.json"
        with open(package_json) as f:
            pkg = json.load(f)
        
        # Check for start script
        scripts = pkg.get("scripts", {})
        if "dev" in scripts:
            self.log("🚀", "Starting with: npm run dev")
            os.execvp("npm", ["npm", "run", "dev"])
        elif "start" in scripts:
            self.log("🚀", "Starting with: npm start")
            os.execvp("npm", ["npm", "start"])
        else:
            # Try to find entry point
            main = pkg.get("main", "index.js")
            self.log("🚀", f"Starting with: node {main}")
            os.execvp("node", ["node", main])
    
    def run_python(self):
        """Run generic Python project"""
        self.log("🎯", "Detected: Python Application")
        self.install_python_deps()
        
        # Find main file
        main_file = None
        for name in ["main.py", "app.py", "run.py", "server.py"]:
            if (self.workspace / name).exists():
                main_file = name
                break
        
        if not main_file:
            # Find any .py file
            py_files = list(self.workspace.glob("*.py"))
            if py_files:
                main_file = py_files[0].name
        
        if not main_file:
            self.log("❌", "No Python entry point found")
            sys.exit(1)
        
        self.log("🚀", f"Starting Python app: {main_file}")
        os.execvp("python", ["python", main_file])
    
    def run_static(self):
        """Serve static HTML"""
        self.log("🎯", "Detected: Static HTML")
        self.log("🚀", "Starting HTTP server on port 8000")
        os.execvp("python", ["python", "-m", "http.server", "8000", "--bind", "0.0.0.0"])
    
    def run(self):
        """Main entry point"""
        self.log("🤖", "VibeCoding Intelligent Agent Starting...")
        self.log("📂", f"Workspace: {self.workspace}")
        
        # Detect project type
        project_type = self.detect_project_type()
        
        # Run appropriate handler
        handlers = {
            "django": self.run_django,
            "flask": self.run_flask,
            "fastapi": self.run_fastapi,
            "nodejs": self.run_nodejs,
            "python": self.run_python,
            "static": self.run_static,
        }
        
        handler = handlers.get(project_type)
        if handler:
            handler()
        else:
            self.log("❌", f"Unknown project type: {project_type}")
            self.log("📋", "Files found:")
            for f in self.workspace.rglob("*"):
                if f.is_file():
                    self.log("  ", f"  - {f.relative_to(self.workspace)}")
            sys.exit(1)

if __name__ == "__main__":
    agent = IntelligentAgent()
    agent.run()
