import os
import uuid
import zipfile
import shutil
import docker
import asyncio
import time
import requests
import threading
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from pathlib import Path
import json
import logging
from runtime_detector import runtime_detector
from git_manager import git_manager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

EDITOR_INJECTION_SCRIPT = """
<script id="__vibe_editor__">
(function() {
  var hoveredEl = null;
  var selectedEl = null;
  var editMode = false;

  window.addEventListener('message', function(e) {
    if (!e.data || !e.data.type) return;
    
    if (e.data.type === 'set-edit-mode') {
      editMode = e.data.value;
      if (!editMode) { clearHover(); clearSelection(); }
    } else if (e.data.type === 'update-element-property') {
      if (selectedEl && e.data.property) {
        if (e.data.property === 'textContent' || e.data.property === 'innerHTML' || e.data.property === 'innerText') {
          selectedEl[e.data.property] = e.data.value;
        } else {
          selectedEl.style[e.data.property] = e.data.value;
        }
      }
    }
  });

  function getElementInfo(el) {
    var rect = el.getBoundingClientRect();
    return {
      tagName: el.tagName,
      id: el.id || '',
      className: (typeof el.className === 'string' ? el.className : ''),
      textContent: (el.textContent || '').substring(0, 150),
      rect: { top: rect.top, left: rect.left, width: rect.width, height: rect.height }
    };
  }

  function clearHover() { window.parent.postMessage({ type: 'element-hover', data: null }, '*'); }
  function clearSelection() { selectedEl = null; window.parent.postMessage({ type: 'element-deselect' }, '*'); }

  document.addEventListener('mouseover', function(e) {
    if (!editMode) return;
    var el = e.target;
    if (!el || el.tagName === 'HTML' || el.tagName === 'BODY') { clearHover(); return; }
    hoveredEl = el;
    window.parent.postMessage({ type: 'element-hover', data: getElementInfo(el) }, '*');
  }, true);

  document.addEventListener('mouseout', function(e) {
    if (!editMode) return;
    hoveredEl = null;
    clearHover();
  }, true);

  document.addEventListener('click', function(e) {
    if (!editMode) return;
    e.preventDefault();
    e.stopPropagation();
    var el = e.target;
    if (!el || el.tagName === 'HTML' || el.tagName === 'BODY') return;
    selectedEl = el;
    var info = getElementInfo(el);
    info.mouseX = e.clientX;
    info.mouseY = e.clientY;
    window.parent.postMessage({ type: 'element-selected', data: info }, '*');
  }, true);

  document.addEventListener('scroll', function() {
    if (!editMode || !hoveredEl) return;
    window.parent.postMessage({ type: 'element-hover', data: getElementInfo(hoveredEl) }, '*');
  }, true);
})();
</script>
"""

class ProjectManager:
    """Manages container-based code execution and project artifacts"""
    
    def __init__(self, artifacts_dir: str = "project_artifacts"):
        self.artifacts_dir = Path(artifacts_dir)
        self.artifacts_dir.mkdir(exist_ok=True)
        self._docker_client = None
        self.running_containers: Dict[str, docker.models.containers.Container] = {}
        self.log_threads: Dict[str, threading.Thread] = {}
    
    @property
    def docker_client(self):
        """Lazy load Docker client on first access"""
        if self._docker_client is None:
            try:
                self._docker_client = docker.from_env()
                logger.info("✅ Docker client initialized successfully")
            except docker.errors.DockerException as e:
                logger.warning(f"⚠️ Docker is not available: {str(e)}")
                logger.warning("Preview functionality will be disabled")
                return None
        return self._docker_client
    
    def _stream_container_logs(self, container, container_name: str):
        """Stream container logs to console in a separate thread"""
        try:
            logger.info(f"📋 Starting log stream for {container_name}")
            for log_line in container.logs(stream=True, follow=True):
                try:
                    decoded_line = log_line.decode('utf-8').strip()
                    if decoded_line:
                        logger.info(f"[{container_name}] {decoded_line}")
                except Exception as e:
                    logger.debug(f"Error decoding log line: {e}")
        except Exception as e:
            logger.debug(f"Log streaming ended for {container_name}: {e}")
        
    def generate_project_id(self) -> str:
        """Generate unique project ID"""
        return str(uuid.uuid4())[:8]
    
    def create_project_directory(self, project_id: str) -> Path:
        """Create project directory with version subdirectories"""
        project_dir = self.artifacts_dir / project_id
        project_dir.mkdir(exist_ok=True)
        
        # Create versions directory
        versions_dir = project_dir / "versions"
        versions_dir.mkdir(exist_ok=True)
        
        # Create project metadata
        metadata = {
            "project_id": project_id,
            "created_at": datetime.now().isoformat(),
            "versions": [],
            "current_version": None
        }
        
        with open(project_dir / "metadata.json", "w") as f:
            json.dump(metadata, f, indent=2)
        
        return project_dir
    
    def save_code_version(self, project_id: str, code: str, prompt: str) -> Tuple[str, Path]:
        """Save code version and return version ID and file path"""
        project_dir = self.artifacts_dir / project_id
        if not project_dir.exists():
            project_dir = self.create_project_directory(project_id)
        
        # Generate version ID
        version_id = f"v{len(list(project_dir.glob('versions/*'))) + 1:03d}"
        version_dir = project_dir / "versions" / version_id
        version_dir.mkdir(exist_ok=True)
        
        # Check if code contains file markers
        import re
        file_marker_regex = r'//\s*FILE:\s*([^\n]+)|#\s*FILE:\s*([^\n]+)|<!--\s*FILE:\s*([^\n]+)\s*-->'
        matches = list(re.finditer(file_marker_regex, code))
        
        main_file_path = None
        runtime_name = None
        runtime_config = None
        
        if matches and len(matches) > 0:
            # Multi-file structure - parse and save each file
            logger.info(f"📁 Multi-file structure detected: {len(matches)} files")
            
            for i, match in enumerate(matches):
                filename = (match.group(1) or match.group(2) or match.group(3)).strip()
                start_pos = match.end()
                end_pos = matches[i + 1].start() if i < len(matches) - 1 else len(code)
                file_content = code[start_pos:end_pos].strip()
                
                # Create file path
                file_path = version_dir / filename
                file_path.parent.mkdir(parents=True, exist_ok=True)
                
                # Inject editor script into HTML files for cross-origin visual editing capability
                if filename.endswith('.html'):
                    if '</body>' in file_content:
                        file_content = file_content.replace('</body>', f'{EDITOR_INJECTION_SCRIPT}</body>')
                    else:
                        file_content += EDITOR_INJECTION_SCRIPT

                # Save file
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(file_content)
                
                logger.info(f"  ✅ Saved: {filename}")
                
                # Detect runtime from first file if not detected yet
                if runtime_name is None:
                    runtime_name, runtime_config = runtime_detector.detect(file_content)
                
                # Set main file (first Python/JS/HTML file)
                if main_file_path is None:
                    if filename.endswith(('.py', '.js', '.html', '.jsx', '.tsx')):
                        main_file_path = file_path
            
            # If no main file found, use first file
            if main_file_path is None:
                filename = (matches[0].group(1) or matches[0].group(2) or matches[0].group(3)).strip()
                main_file_path = version_dir / filename
        else:
            # Single file - use auto-detection
            runtime_name, runtime_config = runtime_detector.detect(code)
            filename = runtime_detector.get_filename(runtime_name)
            
            logger.info(f"📄 Single file detected")
            logger.info(f"🔍 Detected runtime: {runtime_name}")
            logger.info(f"📝 Using filename: {filename}")
            
            # Inject editor script if it's an HTML single file
            if filename.endswith('.html'):
                if '</body>' in code:
                    code = code.replace('</body>', f'{EDITOR_INJECTION_SCRIPT}</body>')
                else:
                    code += EDITOR_INJECTION_SCRIPT

            # Save code file
            main_file_path = version_dir / filename
            with open(main_file_path, 'w', encoding='utf-8') as f:
                f.write(code)
        
        logger.info(f"🔍 Detected runtime: {runtime_name}")
        logger.info(f"🐳 Docker image: {runtime_config['image']}")
        logger.info(f"🔌 Port: {runtime_config['port']}")
        
        # Save version metadata
        version_metadata = {
            "version_id": version_id,
            "prompt": prompt,
            "created_at": datetime.now().isoformat(),
            "runtime": runtime_name,
            "main_file": str(main_file_path.relative_to(version_dir)),
            "docker_image": runtime_config['image'],
            "port": runtime_config['port'],
            "is_multi_file": len(matches) > 0 if matches else False,
            "file_count": len(matches) if matches else 1,
        }
        
        with open(version_dir / "metadata.json", "w") as f:
            json.dump(version_metadata, f, indent=2)
        
        # Update project metadata
        self._update_project_metadata(project_id, version_id, prompt)
        
        # Automatically create ZIP after saving
        self.create_project_zip(project_id)
        
        # Sync to git workspace for version control
        try:
            git_manager.sync_workspace(project_id, version_dir)
        except Exception as e:
            logger.error(f"Failed to sync git workspace: {e}")

        logger.info(f"✅ Saved version {version_id} for project {project_id}")
        return version_id, main_file_path
    
    def _update_project_metadata(self, project_id: str, version_id: str, prompt: str):
        """Update project metadata with new version"""
        project_dir = self.artifacts_dir / project_id
        metadata_file = project_dir / "metadata.json"
        
        with open(metadata_file, 'r') as f:
            metadata = json.load(f)
        
        metadata["versions"].append({
            "version_id": version_id,
            "prompt": prompt,
            "created_at": datetime.now().isoformat()
        })
        metadata["current_version"] = version_id
        
        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)
    
    def _send_switch_command(self, container, version_id: str) -> bool:
        """Send version switch command to supervisor inside container"""
        try:
            import json
            command = json.dumps({'action': 'switch', 'version_id': version_id})
            
            # Use docker exec to send command via socket
            # Create a Python script to send the command properly
            python_cmd = f"""
import socket
import json
import sys

try:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.connect('/tmp/supervisor.sock')
    s.send(json.dumps({{'action': 'switch', 'version_id': '{version_id}'}}).encode())
    response = s.recv(1024).decode()
    print(response)
    s.close()
except Exception as e:
    print(f'Error: {{e}}', file=sys.stderr)
    sys.exit(1)
"""
            
            exec_result = container.exec_run(
                ['python3', '-c', python_cmd],
                demux=True
            )
            
            if exec_result.exit_code == 0:
                response = exec_result.output[0].decode() if exec_result.output[0] else ""
                logger.info(f"📨 Supervisor response: {response}")
                
                # Check if response indicates success
                try:
                    resp_data = json.loads(response)
                    return resp_data.get('success', False)
                except:
                    return True  # Assume success if we got a response
            else:
                error = exec_result.output[1].decode() if exec_result.output[1] else ""
                logger.error(f"❌ Failed to send switch command: {error}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error sending switch command: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def create_container_for_code(self, project_id: str, version_id: str) -> Optional[str]:
        """Create or reuse Docker container and switch to the specified version"""
        project_dir = self.artifacts_dir / project_id
        version_dir = project_dir / "versions" / version_id
        metadata_file = version_dir / "metadata.json"
        
        # Read version metadata to get runtime info
        try:
            with open(metadata_file, 'r') as f:
                metadata = json.load(f)
            
            runtime = metadata.get('runtime', 'static-html')
            docker_image = metadata.get('docker_image', 'vibecoding-code-executor:latest')
            port = metadata.get('port', 80)
            
            logger.info(f"🚀 Switching to version {version_id}")
            logger.info(f"🔍 Runtime: {runtime}")
            logger.info(f"🔌 Port: {port}")
            
        except Exception as e:
            logger.error(f"Failed to read metadata: {e}")
            return None
        
        # Use project_id only for container name (one container per project)
        container_name = f"vibecoding_{project_id}"
        
        # Check if Docker is available
        if self.docker_client is None:
            logger.error("❌ Docker client not available - cannot create container")
            logger.error("Please ensure Docker Desktop is installed and running")
            return None
        
        try:
            # Check if container already exists
            existing_container = None
            
            try:
                existing_container = self.docker_client.containers.get(container_name)
                logger.info(f"♻️ Found existing container: {container_name}")
                
                # Container exists - send version switch command
                if existing_container.status != 'running':
                    existing_container.start()
                    logger.info(f"▶️ Started container")
                    # Wait a moment for supervisor to be ready
                    await asyncio.sleep(2)
                
                # Send switch command to supervisor
                logger.info(f"📡 Sending switch command to version {version_id}")
                success = self._send_switch_command(existing_container, version_id)
                
                if success:
                    logger.info(f"✅ Switched to version {version_id}")
                    container = existing_container
                else:
                    logger.warning(f"⚠️ Failed to switch version, recreating container")
                    existing_container.stop()
                    existing_container.remove()
                    existing_container = None
                
            except docker.errors.NotFound:
                logger.info(f"🆕 Creating new container: {container_name}")
            
            # Create new container only if doesn't exist or switch failed
            if existing_container is None:
                # Mount the ENTIRE project directory so all versions are accessible
                container = self.docker_client.containers.run(
                    docker_image,
                    name=container_name,
                    ports={f'{port}/tcp': None},  # Auto-assign host port
                    volumes={
                        str(project_dir.absolute()): {
                            'bind': '/project',
                            'mode': 'rw'
                        }
                    },
                    working_dir='/app',
                    detach=True,
                    remove=False,
                    environment={
                        'PYTHONUNBUFFERED': '1',
                        'PORT': str(port),
                        'INITIAL_VERSION': version_id,
                        'NVIDIA_API_KEY': os.environ.get('NVIDIA_API_KEY', ''),
                    }
                )
                
                logger.info(f"🏗️ Created container with initial version {version_id}")
                
                # Wait for supervisor to start
                await asyncio.sleep(3)
            
            # Store container reference
            self.running_containers[container_name] = container
            
            # Start log streaming in a separate thread
            log_thread = threading.Thread(
                target=self._stream_container_logs,
                args=(container, container_name),
                daemon=True
            )
            log_thread.start()
            self.log_threads[container_name] = log_thread
            
            # Get assigned host port
            container.reload()
            port_bindings = container.ports.get(f'{port}/tcp', [])
            if not port_bindings:
                logger.error(f"No port binding found for {port}/tcp")
                return None
            
            host_port = port_bindings[0].get('HostPort')
            if not host_port:
                logger.error(f"Failed to get host port")
                return None
            
            url = f"http://localhost:{host_port}"
            logger.info(f"✅ Container running at: {url}")
            
            # Wait for server to be ready (check Docker health status)
            max_wait_time = 30  # 30 seconds
            start_time = asyncio.get_event_loop().time()
            
            while (asyncio.get_event_loop().time() - start_time) < max_wait_time:
                try:
                    # Reload container to get latest health status
                    container.reload()
                    
                    # Check if container has health check configured
                    health_status = container.attrs.get('State', {}).get('Health', {}).get('Status')
                    
                    if health_status == 'healthy':
                        logger.info(f"🎉 Container health check passed - server ready at {url}")
                        return url
                    elif health_status == 'unhealthy':
                        logger.warning(f"⚠️ Container health check failed")
                        break
                    
                    # If no health check, try HTTP request
                    if health_status is None:
                        try:
                            response = requests.get(url, timeout=2)
                            if response.status_code < 500:
                                logger.info(f"🎉 Server responding at {url}")
                                return url
                        except:
                            pass
                    
                except Exception as e:
                    logger.debug(f"Health check attempt failed: {e}")
                
                await asyncio.sleep(1)
            
            logger.info(f"⏱️ Health check timeout - container may still be starting. URL: {url}")
            return url
            
        except Exception as e:
            logger.error(f"Failed to create container: {str(e)}")
            import traceback
            traceback.print_exc()
            return None
    
    def stop_container(self, project_id: str, version_id: str = None):
        """Stop and remove container (version_id is ignored, one container per project)"""
        container_name = f"vibecoding_{project_id}"
        
        if container_name in self.running_containers:
            try:
                container = self.running_containers[container_name]
                container.stop()
                container.remove()
                del self.running_containers[container_name]
                
                # Clean up log thread reference (thread will exit automatically)
                if container_name in self.log_threads:
                    del self.log_threads[container_name]
                
                logger.info(f"Stopped container {container_name}")
            except Exception as e:
                logger.error(f"Failed to stop container {container_name}: {str(e)}")
    
    def create_project_zip(self, project_id: str) -> Optional[Path]:
        """Create ZIP archive of entire project"""
        project_dir = self.artifacts_dir / project_id
        
        if not project_dir.exists():
            logger.error(f"Project directory not found: {project_dir}")
            return None
        
        zip_path = self.artifacts_dir / f"{project_id}_complete.zip"
        
        try:
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for file_path in project_dir.rglob('*'):
                    if file_path.is_file():
                        arcname = file_path.relative_to(project_dir)
                        zipf.write(file_path, arcname)
            
            logger.info(f"Created project ZIP: {zip_path}")
            return zip_path
            
        except Exception as e:
            logger.error(f"Failed to create ZIP: {str(e)}")
            return None
    
    def get_project_info(self, project_id: str) -> Optional[Dict]:
        """Get project information"""
        project_dir = self.artifacts_dir / project_id
        metadata_file = project_dir / "metadata.json"
        
        if not metadata_file.exists():
            return None
        
        with open(metadata_file, 'r') as f:
            return json.load(f)
    
    def get_version_code(self, project_id: str, version_id: str) -> Optional[str]:
        """Get code for specific version"""
        project_dir = self.artifacts_dir / project_id
        version_dir = project_dir / "versions" / version_id
        
        # Try metadata first to find the main file
        metadata_file = version_dir / "metadata.json"
        if metadata_file.exists():
            with open(metadata_file, 'r') as f:
                metadata = json.load(f)
                main_file = metadata.get('main_file')
                if main_file:
                    code_file = version_dir / main_file
                    if code_file.exists():
                        with open(code_file, 'r', encoding='utf-8') as f:
                            return f.read()

        # Fallback to common entry points
        for filename in ["index.html", "preview.html", "app.py", "main.py", "index.js", "server.js"]:
            code_file = version_dir / filename
            if code_file.exists():
                with open(code_file, 'r', encoding='utf-8') as f:
                    return f.read()
        
        return None
    
    def list_projects(self) -> List[Dict]:
        """List all projects"""
        projects = []
        
        for project_dir in self.artifacts_dir.iterdir():
            if project_dir.is_dir():
                metadata_file = project_dir / "metadata.json"
                if metadata_file.exists():
                    with open(metadata_file, 'r') as f:
                        metadata = json.load(f)
                    projects.append(metadata)
        
        return projects
    
    def cleanup_old_containers(self):
        """Clean up old containers"""
        try:
            if self.docker_client is None:
                logger.info("Docker not available, skipping container cleanup")
                return
                
            containers = self.docker_client.containers.list(
                all=True,
                filters={"name": "vibecoding_"}
            )
            
            for container in containers:
                try:
                    container.remove(force=True)
                    logger.info(f"Removed old container: {container.name}")
                except:
                    pass
                    
        except Exception as e:
            logger.error(f"Failed to cleanup containers: {str(e)}")

# Global project manager instance
project_manager = ProjectManager()
