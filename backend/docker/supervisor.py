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

class VersionSupervisor:
    def __init__(self):
        self.current_process = None
        self.current_version = None
        self.project_dir = "/project"
        self.control_socket_path = "/tmp/supervisor.sock"
        self.running = True
        
    def log(self, emoji, message):
        print(f"{emoji} {message}", flush=True)
    
    def stop_current_process(self):
        """Stop the currently running version"""
        if self.current_process:
            self.log("⏹️", f"Stopping version {self.current_version}")
            try:
                # Send SIGTERM to process group
                os.killpg(os.getpgid(self.current_process.pid), signal.SIGTERM)
                self.current_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                # Force kill if doesn't stop gracefully
                os.killpg(os.getpgid(self.current_process.pid), signal.SIGKILL)
                self.current_process.wait()
            except Exception as e:
                self.log("⚠️", f"Error stopping process: {e}")
            
            self.current_process = None
            self.log("✅", f"Stopped version {self.current_version}")
    
    def start_version(self, version_id):
        """Start a specific version using AI agent"""
        version_dir = os.path.join(self.project_dir, "versions", version_id)
        
        if not os.path.exists(version_dir):
            self.log("❌", f"Version directory not found: {version_dir}")
            return False
        
        # Stop current version if running
        if self.current_process:
            self.stop_current_process()
        
        self.log("🚀", f"Starting version {version_id} with AI agent")
        self.log("📂", f"Version directory: {version_dir}")
        
        # Verify files exist
        files = os.listdir(version_dir)
        self.log("📋", f"Files in version: {', '.join(files[:5])}")
        
        # Run the AI agent (it will detect, run, and heal the application)
        try:
            self.current_process = subprocess.Popen(
                ["/usr/local/bin/ai-agent.py"],
                cwd=version_dir,  # Set working directory to version
                preexec_fn=os.setsid,  # Create new process group
                stdout=sys.stdout,
                stderr=sys.stderr,
                env={
                    **os.environ, 
                    'PYTHONUNBUFFERED': '1',
                    'CURRENT_VERSION': version_id,
                    'PWD': version_dir  # Explicitly set PWD
                }
            )
            self.current_version = version_id
            self.log("✅", f"Started version {version_id} (PID: {self.current_process.pid})")
            return True
        except Exception as e:
            self.log("❌", f"Failed to start version: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def handle_client(self, client_socket):
        """Handle commands from control socket"""
        try:
            data = client_socket.recv(1024).decode('utf-8')
            if not data:
                return
            
            command = json.loads(data)
            action = command.get('action')
            
            if action == 'switch':
                version_id = command.get('version_id')
                self.log("🔄", f"Received switch command to version {version_id}")
                success = self.start_version(version_id)
                response = {'success': success, 'version': version_id}
            elif action == 'status':
                response = {
                    'running': self.current_process is not None,
                    'version': self.current_version,
                    'pid': self.current_process.pid if self.current_process else None
                }
            elif action == 'stop':
                self.stop_current_process()
                response = {'success': True}
            else:
                response = {'error': 'Unknown action'}
            
            client_socket.send(json.dumps(response).encode('utf-8'))
        except Exception as e:
            self.log("⚠️", f"Error handling client: {e}")
        finally:
            client_socket.close()
    
    def start_control_socket(self):
        """Start listening on control socket for commands"""
        # Remove old socket if exists
        if os.path.exists(self.control_socket_path):
            os.remove(self.control_socket_path)
        
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(self.control_socket_path)
        server.listen(5)
        
        self.log("👂", f"Listening on {self.control_socket_path}")
        
        while self.running:
            try:
                client, _ = server.accept()
                # Handle each client in a separate thread
                threading.Thread(target=self.handle_client, args=(client,), daemon=True).start()
            except Exception as e:
                if self.running:
                    self.log("⚠️", f"Socket error: {e}")
    
    def monitor_process(self):
        """Monitor the current process and restart if it crashes"""
        while self.running:
            if self.current_process:
                # Check if process is still running
                if self.current_process.poll() is not None:
                    self.log("⚠️", f"Version {self.current_version} exited unexpectedly")
                    self.current_process = None
            time.sleep(1)
    
    def run(self):
        """Main supervisor loop"""
        self.log("🤖", "VibeCoding Version Supervisor Starting...")
        
        # Start monitor thread
        monitor_thread = threading.Thread(target=self.monitor_process, daemon=True)
        monitor_thread.start()
        
        # Check if initial version is specified
        initial_version = os.environ.get('INITIAL_VERSION')
        if initial_version:
            self.start_version(initial_version)
        else:
            self.log("⏸️", "No initial version specified, waiting for commands...")
        
        # Start control socket (blocking)
        try:
            self.start_control_socket()
        except KeyboardInterrupt:
            self.log("🛑", "Shutting down...")
            self.running = False
            self.stop_current_process()

if __name__ == "__main__":
    supervisor = VersionSupervisor()
    supervisor.run()
