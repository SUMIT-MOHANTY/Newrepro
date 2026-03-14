#!/usr/bin/env python3
"""
AI-Powered Self-Healing Agent
Uses LLM to understand errors and generate fixes for any language/framework
"""
import os
import sys
import subprocess
import json
import time
import re
from pathlib import Path

class AIAgent:
    def __init__(self):
        self.max_retries = 3
        self.retry_count = 0
        self.workspace = os.getcwd()
        
        # Check if workspace is empty, look for project files
        if not os.listdir(self.workspace):
            # Try to find version directory
            current_version = os.environ.get('CURRENT_VERSION') or os.environ.get('INITIAL_VERSION')
            if current_version and os.path.exists(f'/project/versions/{current_version}'):
                self.workspace = f'/project/versions/{current_version}'
                os.chdir(self.workspace)
            elif os.path.exists('/project/versions'):
                # Find latest version
                versions = sorted(os.listdir('/project/versions'))
                if versions:
                    self.workspace = f'/project/versions/{versions[-1]}'
                    os.chdir(self.workspace)
        
        self.api_key = os.environ.get('NVIDIA_API_KEY', '')
        self.api_url = os.environ.get('AI_API_URL', 'https://integrate.api.nvidia.com/v1/chat/completions')
        self.ai_model = os.environ.get('AI_MODEL', 'openai/gpt-oss-120b')  # Read from environment
        
    def log(self, emoji, message):
        print(f"{emoji} {message}", flush=True)
    
    def detect_project_type(self):
        """Detect project type and main files"""
        files = os.listdir(self.workspace)
        
        # Django
        if 'manage.py' in files:
            return 'django', 'manage.py', 'python3 manage.py runserver 0.0.0.0:5000'
        
        # Flask
        for f in ['app.py', 'main.py', 'application.py']:
            if f in files:
                with open(f, 'r') as file:
                    content = file.read()
                    if 'flask' in content.lower():
                        return 'flask', f, f'python3 {f}'
        
        # Node.js
        if 'package.json' in files:
            with open('package.json', 'r') as f:
                pkg = json.load(f)
                scripts = pkg.get('scripts', {})
                if 'dev' in scripts:
                    return 'nodejs', 'package.json', 'npm run dev'
                elif 'start' in scripts:
                    return 'nodejs', 'package.json', 'npm start'
                else:
                    main = pkg.get('main', 'index.js')
                    return 'nodejs', main, f'node {main}'
        
        # FastAPI
        for f in ['main.py', 'app.py']:
            if f in files:
                with open(f, 'r') as file:
                    content = file.read()
                    if 'fastapi' in content.lower():
                        return 'fastapi', f, f'uvicorn {f.replace(".py", "")}:app --host 0.0.0.0 --port 5000'
        
        # Static HTML
        html_files = [f for f in files if f.endswith('.html')]
        if html_files:
            return 'static', html_files[0], 'python3 -m http.server 5000 --bind 0.0.0.0'
        
        # Generic Python
        py_files = [f for f in files if f.endswith('.py')]
        if py_files:
            return 'python', py_files[0], f'python3 {py_files[0]}'
        
        return 'unknown', None, None
    
    def install_dependencies(self, project_type):
        """Install dependencies based on project type"""
        self.log("📦", "Installing dependencies...")
        
        if project_type in ['django', 'flask', 'fastapi', 'python']:
            if os.path.exists('requirements.txt'):
                subprocess.run(['pip3', 'install', '-q', '-r', 'requirements.txt'], 
                             stderr=subprocess.DEVNULL)
            
            # Django-specific setup
            if project_type == 'django' and os.path.exists('manage.py'):
                self.log("🔧", "Running Django setup...")
                
                # Run migrations
                try:
                    subprocess.run(['python3', 'manage.py', 'migrate', '--noinput'], 
                                 check=True, timeout=60, capture_output=True)
                    self.log("✅", "Migrations applied")
                except:
                    self.log("⚠️", "Migrations skipped")
                
                # Create static directory if missing
                try:
                    os.makedirs('static', exist_ok=True)
                    self.log("✅", "Static directory ready")
                except:
                    pass
                
                # Collect static files
                try:
                    subprocess.run(['python3', 'manage.py', 'collectstatic', '--noinput'], 
                                 timeout=30, capture_output=True)
                    self.log("✅", "Static files collected")
                except:
                    self.log("⚠️", "Static collection skipped")
        
        elif project_type == 'nodejs':
            if os.path.exists('package.json'):
                subprocess.run(['npm', 'install', '--silent'], 
                             stderr=subprocess.DEVNULL)
    
    def apply_basic_fixes(self, error_log, project_type):
        """Apply basic pattern-matching fixes without AI"""
        self.log("🔧", "Trying basic auto-fixes...")
        fixed = False
        
        # Fix 1: Missing Django
        if 'No module named' in error_log and 'django' in error_log.lower():
            self.log("📦", "Installing Django...")
            try:
                subprocess.run(['pip3', 'install', '-q', 'django'], check=True, timeout=60)
                fixed = True
            except:
                pass
        
        # Fix 2: Missing Flask
        elif 'No module named' in error_log and 'flask' in error_log.lower():
            self.log("📦", "Installing Flask...")
            try:
                subprocess.run(['pip3', 'install', '-q', 'flask'], check=True, timeout=60)
                fixed = True
            except:
                pass
        
        # Fix 3: Missing any Python module
        elif 'ModuleNotFoundError' in error_log or 'No module named' in error_log:
            import re
            match = re.search(r"No module named ['\"]([^'\"]+)['\"]", error_log)
            if match:
                module = match.group(1)
                self.log("📦", f"Installing missing module: {module}")
                try:
                    subprocess.run(['pip3', 'install', '-q', module], check=True, timeout=60)
                    fixed = True
                except:
                    pass
        
        # Fix 4: Missing requirements.txt packages
        if not fixed and os.path.exists('requirements.txt'):
            self.log("📦", "Reinstalling all requirements...")
            try:
                subprocess.run(['pip3', 'install', '-q', '-r', 'requirements.txt'], 
                             check=True, timeout=120)
                fixed = True
            except:
                pass
        
        # Fix 5: Deprecated Flask syntax
        if '@app.before_first_request' in error_log or 'before_first_request' in error_log:
            self.log("🔧", "Fixing deprecated Flask syntax...")
            for file in Path('.').glob('*.py'):
                try:
                    content = file.read_text()
                    if '@app.before_first_request' in content:
                        content = content.replace('@app.before_first_request', 
                                                 '# @app.before_first_request (deprecated)')
                        file.write_text(content)
                        fixed = True
                except:
                    pass
        
        # Fix 6: Port already in use
        if 'Address already in use' in error_log or 'port' in error_log.lower() and 'use' in error_log.lower():
            self.log("🔧", "Killing processes on port...")
            try:
                subprocess.run(['pkill', '-f', 'python.*app.py'], timeout=5)
                subprocess.run(['pkill', '-f', 'flask'], timeout=5)
                subprocess.run(['pkill', '-f', 'django'], timeout=5)
                time.sleep(2)
                fixed = True
            except:
                pass
        
        # Fix 7: Database not initialized (Django)
        if 'no such table' in error_log.lower() and os.path.exists('manage.py'):
            self.log("🔧", "Running Django migrations...")
            try:
                subprocess.run(['python3', 'manage.py', 'migrate', '--noinput'], 
                             check=True, timeout=60)
                fixed = True
            except:
                pass
        
        # Fix 8: Django static template tag not loaded
        if "KeyError: 'static'" in error_log or 'static' in error_log and 'django' in error_log.lower():
            self.log("🔧", "Fixing Django static template tag...")
            for file in Path('.').rglob('*.html'):
                try:
                    content = file.read_text()
                    # Check if using {% static %} without loading it
                    if '{% static' in content and '{% load static %}' not in content:
                        # Add {% load static %} at the top after {% extends %}
                        if '{% extends' in content:
                            content = content.replace('{% extends', '{% load static %}\n{% extends', 1)
                        else:
                            content = '{% load static %}\n' + content
                        file.write_text(content)
                        self.log("✅", f"Fixed {file.name}")
                        fixed = True
                except:
                    pass
        
        # Fix 9: Missing webpack or webpack-cli
        if 'webpack' in error_log and ('not found' in error_log.lower() or 'command failed' in error_log.lower()):
            self.log("🔧", "Installing webpack...")
            try:
                subprocess.run(['npm', 'install', '--save-dev', 'webpack', 'webpack-cli', 'webpack-dev-server'], 
                             check=True, timeout=120)
                fixed = True
            except:
                pass
        
        # Fix 10: Missing react-scripts
        if 'react-scripts' in error_log and ('not found' in error_log.lower() or 'command failed' in error_log.lower()):
            self.log("🔧", "Installing react-scripts...")
            try:
                subprocess.run(['npm', 'install', '--save', 'react-scripts'], 
                             check=True, timeout=120)
                fixed = True
            except:
                pass
        
        # Fix 11: Missing Node.js dependencies (general)
        if project_type == 'nodejs' and os.path.exists('package.json'):
            if 'cannot find module' in error_log.lower() or 'error:' in error_log.lower() or 'not found' in error_log.lower():
                self.log("🔧", "Reinstalling Node.js dependencies...")
                try:
                    # Clear node_modules and reinstall
                    subprocess.run(['rm', '-rf', 'node_modules'], timeout=30)
                    subprocess.run(['npm', 'install'], check=True, timeout=180)
                    fixed = True
                except:
                    pass
        
        # Fix 12: Missing tzdata for Django
        if 'tzdata' in error_log and 'ModuleNotFoundError' in error_log:
            self.log("🔧", "Installing tzdata...")
            try:
                subprocess.run(['pip3', 'install', '-q', 'tzdata'], check=True, timeout=60)
                fixed = True
            except:
                pass
        
        if fixed:
            self.log("✅", "Basic fix applied")
        
        return fixed
    
    def call_ai_for_fix(self, error_log, project_type, files_content):
        """Call AI to analyze error and suggest fix"""
        if not self.api_key:
            self.log("❌", "No NVIDIA_API_KEY found in environment")
            return None
        
        self.log("🤖", "Consulting AI for error analysis...")
        
        # Prepare context (limit size to avoid token overflow)
        files_context = "\n\n".join([
            f"// FILE: {name}\n{content[:1000]}" 
            for name, content in list(files_content.items())[:5]
        ])
        
        prompt = f"""You are an expert debugging AI agent. Analyze this error and provide a fix.

PROJECT TYPE: {project_type}
ERROR LOG:
{error_log[-2000:]}

PROJECT FILES:
{files_context}

Analyze the error and provide:
1. Root cause explanation
2. Specific fix (code changes, commands to run, or packages to install)

Respond in JSON format:
{{
    "diagnosis": "explanation of the error",
    "fix_type": "code_change|install_package|run_command",
    "fix_details": {{
        "file": "filename if code change",
        "changes": "exact code to replace or add",
        "command": "command to run if install/command",
        "package": "package name if install"
    }},
    "confidence": "high|medium|low"
}}"""
        
        try:
            import requests
            import json
            
            self.log("📡", f"Calling AI API...")
            self.log("🔍", f"Error snippet: {error_log[-200:]}")
            self.log("🔑", f"API Key present: {bool(self.api_key)}")
            self.log("🌐", f"API URL: {self.api_url}")
            self.log("🤖", f"Model: {self.ai_model}")
            
            response = requests.post(
                self.api_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": self.ai_model,
                    "messages": [
                        {"role": "system", "content": "You are an expert debugging AI that analyzes errors and provides precise fixes in JSON format."},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.2,
                    "max_tokens": 1500
                },
                timeout=30
            )
            
            self.log("📨", f"AI API response status: {response.status_code}")
            
            if response.status_code == 200:
                ai_response = response.json()['choices'][0]['message']['content']
                self.log("✅", "AI response received")
                self.log("📄", f"AI response preview: {ai_response[:200]}...")
                
                # Extract JSON from response
                import re
                json_match = re.search(r'\{.*\}', ai_response, re.DOTALL)
                if json_match:
                    fix_data = json.loads(json_match.group())
                    self.log("🔍", f"AI diagnosis: {fix_data.get('diagnosis', 'N/A')[:100]}")
                    return fix_data
                else:
                    self.log("⚠️", "Could not parse JSON from AI response")
                    self.log("📄", f"Full response: {ai_response}")
            elif response.status_code == 401:
                self.log("❌", "AI API authentication failed - check NVIDIA_API_KEY")
            elif response.status_code == 429:
                self.log("❌", "AI API rate limit exceeded - too many requests")
            else:
                self.log("❌", f"AI API error: {response.status_code}")
                self.log("📄", f"Response: {response.text[:500]}")
            
        except ImportError:
            self.log("❌", "requests library not installed in container")
        except requests.exceptions.Timeout:
            self.log("❌", "AI API request timed out (30s)")
        except requests.exceptions.ConnectionError:
            self.log("❌", "Cannot connect to AI API - check internet connection")
        except json.JSONDecodeError as e:
            self.log("❌", f"Failed to parse AI response as JSON: {e}")
        except Exception as e:
            self.log("❌", f"AI call failed: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
        
        return None
    
    def apply_fix(self, fix_data):
        """Apply the fix suggested by AI"""
        if not fix_data:
            return False
        
        self.log("🔧", f"Applying fix: {fix_data.get('diagnosis', 'Unknown issue')[:100]}")
        
        fix_type = fix_data.get('fix_type')
        details = fix_data.get('fix_details', {})
        
        try:
            if fix_type == 'install_package':
                package = details.get('package') or details.get('command', '').replace('pip install ', '').replace('npm install ', '')
                
                # Detect if it's Python or Node.js package
                if 'npm' in details.get('command', '') or os.path.exists('package.json'):
                    self.log("📦", f"Installing Node.js package: {package}")
                    subprocess.run(['npm', 'install', package], check=True, timeout=120)
                else:
                    self.log("📦", f"Installing Python package: {package}")
                    subprocess.run(['pip3', 'install', '-q', package], check=True, timeout=60)
                return True
            
            elif fix_type == 'run_command':
                command = details.get('command')
                self.log("⚙️", f"Running command: {command}")
                subprocess.run(command, shell=True, check=True, timeout=120)
                return True
            
            elif fix_type == 'code_change':
                filename = details.get('file')
                changes = details.get('changes')
                
                if filename and changes:
                    self.log("✏️", f"Modifying file: {filename}")
                    
                    # Read current content
                    if os.path.exists(filename):
                        with open(filename, 'r') as f:
                            current_content = f.read()
                        
                        # Try to intelligently apply changes
                        # If changes contain full file content, replace
                        if len(changes) > 100:
                            with open(filename, 'w') as f:
                                f.write(changes)
                        else:
                            # Append or smart merge
                            with open(filename, 'a') as f:
                                f.write('\n' + changes)
                        
                        return True
            
            elif fix_type == 'config_change':
                # Handle configuration changes
                self.log("⚙️", "Applying configuration changes...")
                command = details.get('command')
                if command:
                    subprocess.run(command, shell=True, check=True, timeout=60)
                return True
        
        except subprocess.TimeoutExpired:
            self.log("❌", "Fix command timed out")
            return False
        except subprocess.CalledProcessError as e:
            self.log("❌", f"Fix command failed with exit code {e.returncode}")
            return False
        except Exception as e:
            self.log("❌", f"Failed to apply fix: {type(e).__name__}: {e}")
            return False
        
        return False
    
    def get_project_files_content(self):
        """Get content of main project files for AI context"""
        files_content = {}
        
        # Get all relevant files (limit to avoid token overflow)
        extensions = ['.py', '.js', '.jsx', '.ts', '.tsx', '.json', '.html', '.css']
        
        for file in Path(self.workspace).glob('*'):
            if file.is_file() and file.suffix in extensions:
                try:
                    with open(file, 'r', encoding='utf-8') as f:
                        content = f.read()
                        if len(content) < 5000:  # Limit file size
                            files_content[file.name] = content
                except:
                    pass
        
        return files_content
    
    def run_with_healing(self):
        """Main loop: run app, detect errors, heal, retry"""
        self.log("🤖", "AI-Powered Self-Healing Agent Starting...")
        
        # Log AI configuration
        if self.api_key:
            masked_key = self.api_key[:8] + '...' + self.api_key[-4:] if len(self.api_key) > 12 else '***'
            self.log("🔑", f"AI API Key: {masked_key}")
            self.log("🌐", f"API URL: {self.api_url}")
            self.log("🤖", f"AI Model: {self.ai_model}")
        else:
            self.log("⚠️", "No AI API key - AI fixes disabled")
        self.log("📂", f"Workspace: {self.workspace}")
        
        # Verify workspace has files
        files = os.listdir(self.workspace)
        if not files:
            self.log("❌", "No files found in workspace")
            self.log("📋", f"Checked directory: {self.workspace}")
            return False
        
        self.log("📋", f"Found {len(files)} files: {', '.join(files[:5])}")
        
        # Detect project
        project_type, main_file, run_command = self.detect_project_type()
        
        if project_type == 'unknown':
            self.log("❌", "Could not detect project type")
            self.log("📋", f"Files in workspace: {files}")
            return False
        
        self.log("🎯", f"Detected: {project_type.upper()} project")
        self.log("📄", f"Main file: {main_file}")
        self.log("▶️", f"Run command: {run_command}")
        
        # Install dependencies
        self.install_dependencies(project_type)
        
        # Get project files for AI context
        files_content = self.get_project_files_content()
        
        # Main healing loop
        while self.retry_count < self.max_retries:
            self.log("🚀", f"Starting application (attempt {self.retry_count + 1}/{self.max_retries})")
            
            # Run the application and capture output
            try:
                process = subprocess.Popen(
                    run_command,
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1
                )
                
                # Monitor for 10 seconds
                output_lines = []
                start_time = time.time()
                error_detected = False
                
                while time.time() - start_time < 10:
                    line = process.stdout.readline()
                    if line:
                        print(line, end='', flush=True)
                        output_lines.append(line)
                        
                        # Detect runtime errors even if server is running
                        if any(err in line.lower() for err in ['error', 'exception', 'traceback', 'failed']):
                            if 'Traceback' in line or 'Error:' in line:
                                error_detected = True
                    
                    # Check if process is still running
                    if process.poll() is not None:
                        # Process exited
                        remaining = process.stdout.read()
                        if remaining:
                            print(remaining, flush=True)
                            output_lines.append(remaining)
                        break
                    
                    time.sleep(0.1)
                
                # Check if still running (success!)
                if process.poll() is None:
                    # Server is running, but check for runtime errors
                    if error_detected:
                        self.log("⚠️", "Application started but has runtime errors, analyzing...")
                        error_log = ''.join(output_lines)
                        
                        # Try to fix runtime errors
                        if self.apply_basic_fixes(error_log, project_type):
                            self.log("✅", "Applied fix for runtime error, restarting...")
                            process.terminate()
                            process.wait()
                            self.retry_count += 1
                            files_content = self.get_project_files_content()
                            continue
                        
                        # Try AI fix if basic didn't work
                        if self.api_key:
                            fix_data = self.call_ai_for_fix(error_log, project_type, files_content)
                            if fix_data and fix_data.get('confidence') != 'low':
                                if self.apply_fix(fix_data):
                                    self.log("✅", "AI fix applied, restarting...")
                                    process.terminate()
                                    process.wait()
                                    self.retry_count += 1
                                    files_content = self.get_project_files_content()
                                    continue
                    
                    self.log("✅", "Application running successfully!")
                    
                    # Continue monitoring for errors in background
                    self.log("👀", "Monitoring for runtime errors...")
                    monitor_start = time.time()
                    
                    while time.time() - monitor_start < 30:  # Monitor for 30 more seconds
                        line = process.stdout.readline()
                        if line:
                            print(line, end='', flush=True)
                            
                            # Detect critical errors that need fixing
                            if 'ModuleNotFoundError' in line or 'No module named' in line:
                                self.log("⚠️", "Runtime error detected, attempting fix...")
                                
                                # Extract module name
                                import re
                                match = re.search(r"No module named ['\"]([^'\"]+)['\"]", line)
                                if match:
                                    module = match.group(1)
                                    self.log("📦", f"Installing missing module: {module}")
                                    try:
                                        subprocess.run(['pip3', 'install', '-q', module], 
                                                     check=True, timeout=60)
                                        self.log("✅", "Module installed, restarting...")
                                        process.terminate()
                                        process.wait()
                                        self.retry_count += 1
                                        break  # Exit monitoring loop to retry
                                    except:
                                        pass
                        
                        if process.poll() is not None:
                            self.log("⚠️", "Application stopped unexpectedly")
                            break
                        
                        time.sleep(0.1)
                    
                    # If we broke out of monitoring loop, retry
                    if self.retry_count < self.max_retries and process.poll() is not None:
                        continue
                    
                    # Keep it running
                    if process.poll() is None:
                        process.wait()
                    return True
                
                # Process crashed - analyze error
                error_log = ''.join(output_lines)
                self.log("❌", "Application crashed, analyzing error...")
                
                # Try basic auto-fixes first (faster, no API needed)
                if self.apply_basic_fixes(error_log, project_type):
                    self.log("✅", "Applied basic fix, retrying...")
                    self.retry_count += 1
                    files_content = self.get_project_files_content()
                    continue
                
                # If basic fixes didn't work, try AI
                self.log("🤖", "Basic fixes didn't work, trying AI...")
                if self.api_key:
                    self.log("🔑", "API key found, calling AI...")
                    fix_data = self.call_ai_for_fix(error_log, project_type, files_content)
                    
                    if fix_data:
                        self.log("📋", f"AI Response: {json.dumps(fix_data, indent=2)}")
                        
                        if fix_data.get('confidence') == 'low':
                            self.log("⚠️", "AI confidence is low, skipping fix")
                        else:
                            self.log("🔧", f"AI suggests: {fix_data.get('fix_type')}")
                            if self.apply_fix(fix_data):
                                self.log("✅", "AI fix applied, retrying...")
                                self.retry_count += 1
                                files_content = self.get_project_files_content()
                                continue
                            else:
                                self.log("❌", "AI fix failed to apply")
                    else:
                        self.log("❌", "AI returned no fix suggestion")
                else:
                    self.log("⚠️", "No AI API key available (NVIDIA_API_KEY not set)")
                    self.log("💡", "Set NVIDIA_API_KEY environment variable to enable AI fixes")
                
                # No fix available or fix failed
                self.log("❌", "Could not auto-fix the error")
                self.log("📋", "Error log:")
                print(error_log)
                return False
                
            except Exception as e:
                self.log("❌", f"Unexpected error: {e}")
                return False
        
        self.log("❌", f"Max retries ({self.max_retries}) reached")
        return False

if __name__ == "__main__":
    agent = AIAgent()
    success = agent.run_with_healing()
    sys.exit(0 if success else 1)
