#!/usr/bin/env python3
"""
Supervisor process that manages version switching inside the container.
Listens on a control socket and switches between versions on demand.
"""
import os
import sys
import signal
import subprocess
import json
import socket
import threading
import time
from pathlib import Path

class VersionSupervisor:
    def __init__(self):
        self.config = {
            'project_dir': os.environ.get('PROJECT_DIR', '/project'),
            'socket_path': os.environ.get('SUPERVISOR_SOCKET', '/tmp/supervisor.sock'),
            'port': os.environ.get('PORT', '8080')
        }
        self.current_process = None
        self.current_version = None
        self.running = True
        
    def log(self, emoji, message):
        timestamp = time.strftime("%H:%M:%S")
        print(f"[{timestamp}] {emoji} {message}", flush=True)
    
    def stop_current_process(self):
        """Surgically stop the entire process group"""
        if self.current_process:
            self.log("⏹️", f"Stopping version {self.current_version}...")
            try:
                # Kill the whole process group created by setsid
                pgid = os.getpgid(self.current_process.pid)
                os.killpg(pgid, signal.SIGTERM)
                
                # Give it a moment to breathe
                try:
                    self.current_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.log("⚠️", "Force killing stubborn process...")
                    os.killpg(pgid, signal.SIGKILL)
                    self.current_process.wait()
            except ProcessLookupError:
                pass
            except Exception as e:
                self.log("❌", f"Stop error: {e}")
            
            self.current_process = None
            self.current_version = None
    
    def start_version(self, version_id):
        """Spawn the AI Agent for a specific version"""
        version_path = Path(self.config['project_dir']) / "versions" / version_id
        
        if not version_path.exists():
            self.log("❌", f"Directory missing: {version_path}")
            return False
        
        self.stop_current_process()
        
        self.log("🚀", f"Activating Version: {version_id}")
        
        try:
            # We use python3 explicitly to ensure shebang issues don't block us
            self.current_process = subprocess.Popen(
                ["python3", "/usr/local/bin/ai-agent.py"],
                cwd=str(version_path),
                preexec_fn=os.setsid, # Create session to manage group
                stdout=sys.stdout,
                stderr=sys.stderr,
                env={
                    **os.environ,
                    'PORT': self.config['port'],
                    'CURRENT_VERSION': version_id,
                    'PYTHONUNBUFFERED': '1'
                }
            )
            self.current_version = version_id
            self.log("✅", f"Agent started (PID: {self.current_process.pid})")
            return True
        except Exception as e:
            self.log("❌", f"Activation failed: {e}")
            return False

    def handle_client(self, conn):
        """Unified command handler for the control socket"""
        try:
            raw = conn.recv(2048).decode('utf-8')
            if not raw: return
            
            data = json.loads(raw)
            action = data.get('action')
            
            if action == 'switch':
                vid = data.get('version_id')
                success = self.start_version(vid)
                resp = {'status': 'ok' if success else 'error', 'version': vid}
            elif action == 'status':
                resp = {
                    'running': self.current_process is not None,
                    'version': self.current_version,
                    'pid': self.current_process.pid if self.current_process else None
                }
            elif action == 'stop':
                self.stop_current_process()
                resp = {'status': 'stopped'}
            else:
                resp = {'status': 'unknown_command'}
                
            conn.send(json.dumps(resp).encode('utf-8'))
        except Exception as e:
            self.log("⚠️", f"Client handler error: {e}")
        finally:
            conn.close()

    def run(self):
        """Execution engine for the supervisor"""
        self.log("🛡️", "Supervisor standing guard...")
        
        # Socket setup
        if os.path.exists(self.config['socket_path']):
            os.remove(self.config['socket_path'])
            
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(self.config['socket_path'])
        server.listen(10)
        
        # Initial boot
        init_v = os.environ.get('INITIAL_VERSION')
        if init_v:
            self.start_version(init_v)
            
        server.settimeout(5.0)
        try:
            while self.running:
                try:
                    client, _ = server.accept()
                    threading.Thread(target=self.handle_client, args=(client,), daemon=True).start()
                except socket.timeout:
                    pass
                
                # Passive health check of the managed agent
                if self.current_process and self.current_process.poll() is not None:
                    self.log("⚠️", "AI Agent exited. Waiting for next command.")
                    self.current_process = None
        except KeyboardInterrupt:
            self.log("🛑", "Manual shutdown requested")
        finally:
            self.stop_current_process()
            if os.path.exists(self.config['socket_path']):
                os.remove(self.config['socket_path'])

if __name__ == "__main__":
    VersionSupervisor().run()
