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
from git_manager import git_manager
from ai_config import ai_config

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
    
    DEFAULT_IMAGE = os.environ.get("AGENT_IMAGE", "vibecoding-agent-runtime:latest")
    DEFAULT_PORT = int(os.environ.get("AGENT_PORT", "8080"))
    DEFAULT_RUNTIME = os.environ.get("DEFAULT_RUNTIME", "universal")

    def __init__(self, artifacts_dir: str = os.environ.get("ARTIFACTS_DIR", "project_artifacts")):
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
    
    def _build_runtime_image(self, image_name: str) -> bool:
        """Build the runtime image from Dockerfile"""
        try:
            dockerfile_path = Path(__file__).parent / "docker" / "agent-runtime.Dockerfile"
            if not dockerfile_path.exists():
                logger.error(f"❌ Dockerfile not found at {dockerfile_path}")
                return False
            
            logger.info(f"🏗️ Building image {image_name} from {dockerfile_path}...")
            # Use the docker/ folder as context
            image, build_logs = self.docker_client.images.build(
                path=str(dockerfile_path.parent),
                dockerfile=dockerfile_path.name,
                tag=image_name,
                rm=True
            )
            logger.info(f"✅ Successfully built {image_name}")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to build image: {e}")
            return False

    def _ensure_image_exists(self, image_name: str) -> bool:
        """Check if image exists, build if it's the standard runtime"""
        if self.docker_client is None:
            return False
            
        try:
            self.docker_client.images.get(image_name)
            return True
        except docker.errors.ImageNotFound:
            if "vibecoding-agent-runtime" in image_name:
                return self._build_runtime_image(image_name)
            return False
        except Exception as e:
            logger.error(f"Error checking image: {e}")
            return False

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
    
    def create_project_directory(self, project_id: str, metadata: dict = None) -> Path:
        """Create project directory with version subdirectories"""
        project_dir = self.artifacts_dir / project_id
        project_dir.mkdir(exist_ok=True)
        
        # Create versions directory
        versions_dir = project_dir / "versions"
        versions_dir.mkdir(exist_ok=True)
        
        # Create project metadata
        project_meta = {
            "project_id": project_id,
            "name": metadata.get("name") if metadata else f"Project {project_id[:8]}",
            "description": metadata.get("description") if metadata else "",
            "owner_id": metadata.get("owner_id") if metadata else None,
            "created_at": datetime.now().isoformat(),
            "versions": [],
            "current_version": None
        }
        
        with open(project_dir / "metadata.json", "w") as f:
            json.dump(project_meta, f, indent=2)
        
        return project_dir
    
    def save_code_version(self, project_id: str, code: str, prompt: str) -> Tuple[str, Path]:
        """Save code version and return version ID and file path"""
        project_dir = self.artifacts_dir / project_id
        if not project_dir.exists():
            project_dir = self.create_project_directory(project_id)
        
        # Generate version ID
        version_id = f"v{len(list(project_dir.glob('versions/*'))) + 1:03d}"
        version_dir = project_dir / "versions" / version_id
        version_dir.mkdir(parents=True, exist_ok=True)
        
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
                
                # Set universal defaults
                if runtime_name is None:
                    runtime_name = self.DEFAULT_RUNTIME
                    runtime_config = {'image': self.DEFAULT_IMAGE, 'port': self.DEFAULT_PORT}
                
                # Set main file
                if main_file_path is None:
                    if filename.endswith(('.py', '.js', '.html', '.jsx', '.tsx', '.go', '.rs', '.java')):
                        main_file_path = file_path
            
            # If no main file found, use first file
            if main_file_path is None:
                filename = (matches[0].group(1) or matches[0].group(2) or matches[0].group(3)).strip()
                main_file_path = version_dir / filename
        else:
            # Single file - use universal defaults
            runtime_name = "universal"
            runtime_config = {'image': self.DEFAULT_IMAGE, 'port': self.DEFAULT_PORT}
            filename = "app.py" if any(k in code for k in ["import ", "def ", "class "]) else "index.html"
            
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
            # Auto-commit the new version
            git_manager.auto_commit_version(project_id, version_id, prompt)
        except Exception as e:
            logger.error(f"Failed to sync or commit git workspace: {e}")

        logger.info(f"✅ Saved version {version_id} for project {project_id}")
        return version_id, main_file_path

    def archive_workspace_to_version(self, project_id: str, prompt: str = "Chat Session Snapshot") -> str:
        """Create a permanent version folder from the current workspace state."""
        project_dir = self.artifacts_dir / project_id
        workspace_dir = project_dir / "workspace"
        
        if not workspace_dir.exists():
            return "v000"

        # 1. Determine next version ID
        versions_dir = project_dir / "versions"
        versions_dir.mkdir(exist_ok=True)
        version_id = f"v{len(list(versions_dir.iterdir())) + 1:03d}"
        version_dir = versions_dir / version_id
        version_dir.mkdir(parents=True, exist_ok=True)
        
        # 2. Copy files (excluding .git)
        import shutil
        for item in workspace_dir.iterdir():
            if item.name == ".git":
                continue
            if item.is_dir():
                shutil.copytree(item, version_dir / item.name, dirs_exist_ok=True)
            else:
                shutil.copy2(item, version_dir / item.name)
        
        # 3. Save metadata
        metadata = {
            "version_id": version_id,
            "prompt": prompt,
            "created_at": datetime.now().isoformat(),
            "is_archive": True
        }
        with open(version_dir / "metadata.json", "w") as f:
            json.dump(metadata, f, indent=2)
            
        # Update project metadata
        self._update_project_metadata(project_id, version_id, prompt)
        
        logger.info(f"📁 Archived workspace to version {version_id}")
        return version_id

    def get_workspace_files(self, project_id: str, max_files: int = 20, max_chars_per_file: int = 2000) -> dict:
        """Get all files from the workspace as a dictionary {filepath: content}
        
        Args:
            project_id: Project identifier
            max_files: Maximum number of files to return (to avoid token overflow)
            max_chars_per_file: Maximum characters per file (to avoid token overflow)
        """
        project_dir = self.artifacts_dir / project_id
        workspace_dir = project_dir / "workspace"
        
        if not workspace_dir.exists():
            return {}
        
        files = {}
        file_count = 0
        
        for file_path in sorted(workspace_dir.rglob('*')):
            if file_count >= max_files:
                break
                
            if file_path.is_file() and '.git' not in file_path.parts:
                try:
                    rel_path = str(file_path.relative_to(workspace_dir)).replace('\\', '/')
                    content = file_path.read_text(encoding='utf-8')
                    
                    # Truncate large files
                    if len(content) > max_chars_per_file:
                        content = content[:max_chars_per_file] + f"\n... [truncated, {len(content) - max_chars_per_file} more chars]"
                    
                    files[rel_path] = content
                    file_count += 1
                except Exception as e:
                    logger.warning(f"Could not read {file_path}: {e}")
        
        return files

    def update_workspace_from_code(self, project_id: str, code: str, prompt: str, is_incremental: bool = None) -> Tuple[str, Path]:
        """Update the git workspace directly with new code and commit it.
        
        Args:
            project_id: The project identifier
            code: Generated code with file markers
            prompt: User's prompt for the commit message
            is_incremental: If None, auto-detect. If True, only update specified files. If False, replace entire workspace.
        """
        project_dir = self.artifacts_dir / project_id
        workspace_dir = project_dir / "workspace"
        workspace_dir.mkdir(parents=True, exist_ok=True)
        
        # Ensure git is initialized
        if not (workspace_dir / ".git").exists():
            git_manager.init_repo(project_id)
            git_manager._run_git_command(project_id, ["config", "user.email", "vibe@engineer.com"])
            git_manager._run_git_command(project_id, ["config", "user.name", "Vibe Engineer"])

        # Auto-detect incremental mode if not specified
        if is_incremental is None:
            # Count existing files in workspace
            existing_files = list(workspace_dir.rglob('*'))
            existing_file_count = sum(1 for f in existing_files if f.is_file() and '.git' not in f.parts)
            
            # Parse how many files are in the generated code
            import re
            file_marker_regex = r'//\s*FILE:\s*([^\n]+)|#\s*FILE:\s*([^\n]+)|<!--\s*FILE:\s*([^\n]+)\s*-->'
            generated_file_count = len(re.findall(file_marker_regex, code))
            
            # If existing code exists and AI generated fewer files than exist, it's likely incremental
            # If AI generated many files (5+), it's likely a full regeneration
            if existing_file_count > 0 and generated_file_count > 0:
                if generated_file_count < existing_file_count * 0.5:  # Less than 50% of existing files
                    is_incremental = True
                    logger.info(f"✏️ Auto-detected incremental mode: {generated_file_count} files generated vs {existing_file_count} existing")
                else:
                    is_incremental = False
                    logger.info(f"🔄 Auto-detected full regeneration: {generated_file_count} files generated vs {existing_file_count} existing")
            else:
                is_incremental = False
                logger.info(f"🆕 New project or full generation")

        # If not incremental, clear workspace (except .git)
        if not is_incremental:
            logger.info(f"🔄 Full workspace replacement for {project_id}")
            for item in workspace_dir.iterdir():
                if item.name != '.git':
                    if item.is_dir():
                        import shutil
                        shutil.rmtree(item)
                    else:
                        item.unlink()
        else:
            logger.info(f"✏️ Incremental update for {project_id}")

        # 1. Parse code into files and write to workspace
        import re
        file_marker_regex = r'//\s*FILE:\s*([^\n]+)|#\s*FILE:\s*([^\n]+)|<!--\s*FILE:\s*([^\n]+)\s*-->'
        matches = list(re.finditer(file_marker_regex, code))
        
        main_file_path = None
        
        if matches and len(matches) > 0:
            for i, match in enumerate(matches):
                filename = (match.group(1) or match.group(2) or match.group(3)).strip()
                start_pos = match.end()
                end_pos = matches[i + 1].start() if i < len(matches) - 1 else len(code)
                file_content = code[start_pos:end_pos].strip()
                
                file_path = workspace_dir / filename
                file_path.parent.mkdir(parents=True, exist_ok=True)
                
                # Inject editor script into HTML files
                if filename.endswith('.html'):
                    if '</body>' in file_content:
                        file_content = file_content.replace('</body>', f'{EDITOR_INJECTION_SCRIPT}</body>')
                    else:
                        file_content += EDITOR_INJECTION_SCRIPT

                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(file_content)
                
                logger.info(f"  {'📝 Updated' if is_incremental else '📄 Created'}: {filename}")
                
                if main_file_path is None and filename.endswith(('.py', '.js', '.html', '.jsx', '.tsx')):
                    main_file_path = file_path
            
            if main_file_path is None:
                filename = (matches[0].group(1) or matches[0].group(2) or matches[0].group(3)).strip()
                main_file_path = workspace_dir / filename
        else:
            # Single file
            filename = "app.py" if any(k in code for k in ["import ", "def ", "class "]) else "index.html"
            if filename.endswith('.html'):
                if '</body>' in code:
                    code = code.replace('</body>', f'{EDITOR_INJECTION_SCRIPT}</body>')
                else:
                    code += EDITOR_INJECTION_SCRIPT
            
            main_file_path = workspace_dir / filename
            with open(main_file_path, 'w', encoding='utf-8') as f:
                f.write(code)

        # 2. Commit the changes
        git_manager.add_files(project_id)
        # Check if there are changes to commit
        status = git_manager.get_status(project_id)
        has_changes = status.get("modified_files") or status.get("added_files") or status.get("deleted_files") or status.get("untracked_files")
        
        if has_changes:
            commit_msg = f"{'[Incremental] ' if is_incremental else ''}{prompt}"
            git_manager.commit(project_id, commit_msg)
        
        # Get the commit hash to use as version_id/checkpoint_id
        hash_res = git_manager._run_git_command(project_id, ["rev-parse", "HEAD"])
        commit_hash = hash_res["stdout"].strip() if hash_res["status"] == "success" else f"commit_{int(time.time())}"
        
        logger.info(f"✅ Committed workspace changes: {commit_hash[:8]}")
        
        # 3. Create metadata.json for container creation
        # This is needed for create_container_for_code to work
        metadata = {
            "runtime": "static-html",  # Default runtime
            "docker_image": "vibecoding-agent-runtime:latest",
            "port": 80,
            "additional_ports": [],
            "created_at": datetime.now().isoformat(),
            "commit_hash": commit_hash
        }
        
        # Detect runtime from files
        if any(f.endswith('.py') for f in os.listdir(workspace_dir) if os.path.isfile(workspace_dir / f)):
            metadata["runtime"] = "python"
            metadata["port"] = 8000
        elif any(f.endswith(('.js', '.jsx')) for f in os.listdir(workspace_dir) if os.path.isfile(workspace_dir / f)):
            if (workspace_dir / "package.json").exists():
                metadata["runtime"] = "node"
                metadata["port"] = 3000
        
        metadata_file = workspace_dir / "metadata.json"
        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        return commit_hash, main_file_path
    
    def update_project_metadata(self, project_id: str, metadata: dict):
        """Update existing project metadata"""
        project_dir = self.artifacts_dir / project_id
        metadata_file = project_dir / "metadata.json"
        
        if not metadata_file.exists():
            return False
            
        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)
        return True

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
    
    SUPERVISOR_SOCKET = os.environ.get("SUPERVISOR_SOCKET", "/tmp/supervisor.sock")

    def _send_switch_command(self, container, version_id: str) -> bool:
        """Send version switch command to supervisor inside container"""
        try:
            # Create a Python script to send the command properly via the supervisor socket
            python_cmd = f"""
import socket, json, sys
try:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.connect('{self.SUPERVISOR_SOCKET}')
        s.send(json.dumps({{'action': 'switch', 'version_id': '{version_id}'}}).encode())
        print(s.recv(1024).decode())
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
                return True
            else:
                error = exec_result.output[1].decode() if exec_result.output[1] else ""
                logger.error(f"❌ Failed to send switch command: {error}")
                return False
        except Exception as e:
            logger.error(f"❌ Error sending switch command: {e}")
            return False

    async def switch_to_workspace(self, project_id: str) -> bool:
        """Switch the container to run from the workspace directory (Git state)
        Creates container if it doesn't exist"""
        container_name = f"vibecoding_{project_id}"
        
        if self.docker_client is None:
            return False
            
        try:
            # Try to get existing container
            try:
                container = self.docker_client.containers.get(container_name)
                if container.status != 'running':
                    container.start()
                    await asyncio.sleep(2)
                    
                return self._send_switch_command(container, "workspace")
            except docker.errors.NotFound:
                # Container doesn't exist, create it
                logger.info(f"🆕 Container not found, creating for project {project_id}")
                preview_url = await self.create_container_for_code(project_id, "workspace")
                return preview_url is not None
                
        except Exception as e:
            logger.error(f"Failed to switch to workspace: {e}")
            return False
    
    async def create_container_for_code(self, project_id: str, version_id: str) -> Optional[str]:
        """Create or reuse Docker container and switch to the specified version"""
        project_dir = self.artifacts_dir / project_id
        
        # Handle workspace vs versioned code differently
        if version_id == "workspace":
            # For workspace, metadata is in workspace directory
            version_dir = project_dir / "workspace"
            metadata_file = version_dir / "metadata.json"
        else:
            # For versioned code, metadata is in versions/{version_id}
            version_dir = project_dir / "versions" / version_id
            metadata_file = version_dir / "metadata.json"
        
        # Read version metadata to get runtime info
        try:
            with open(metadata_file, 'r') as f:
                metadata = json.load(f)
            
            runtime = metadata.get('runtime', 'static-html')
            docker_image = metadata.get('docker_image', 'vibecoding-agent-runtime:latest')
            
            # Support multiple ports
            primary_port = metadata.get('port', 80)
            additional_ports = metadata.get('additional_ports', [])
            all_ports = [primary_port] + [p for p in additional_ports if p != primary_port]
            
            logger.info(f"🚀 Switching to version {version_id}")
            logger.info(f"🔍 Runtime: {runtime}")
            logger.info(f"🔌 Ports: {all_ports}")
            
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
        
        # Ensure image exists before running
        if not self._ensure_image_exists(docker_image):
            logger.error(f"❌ Image {docker_image} not found and could not be built")
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
                # Prepare port bindings for all required ports
                port_bindings = {f'{p}/tcp': None for p in all_ports}
                
                # Mount the ENTIRE project directory so all versions are accessible
                container = self.docker_client.containers.run(
                    docker_image,
                    name=container_name,
                    ports=port_bindings,
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
                        'PORT': str(primary_port),
                        'ADDITIONAL_PORTS': ','.join(map(str, additional_ports)),
                        'INITIAL_VERSION': version_id,
                        'AI_API_KEY': ai_config.api_key,
                        'AI_API_URL': ai_config.base_url,
                        'AI_MODEL': ai_config.model,
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
            
            # Get assigned host port for the primary port
            container.reload()
            primary_port_bindings = container.ports.get(f'{primary_port}/tcp', [])
            if not primary_port_bindings:
                logger.error(f"No port binding found for {primary_port}/tcp")
                return None
            
            host_port = primary_port_bindings[0].get('HostPort')
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
                        # Skip huge, problematic folders like node_modules
                        if "node_modules" in file_path.parts:
                            continue
                        arcname = file_path.relative_to(project_dir)
                        zipf.write(file_path, arcname)
            
            logger.info(f"Created project ZIP: {zip_path}")
            return zip_path
        except Exception as e:
            logger.error(f"Failed to create ZIP: {str(e)}")
            return None
    
    async def save_chat_version(self, project_id: str, version_id: str, messages: List[Dict]):
        """Save chat history for a specific project version"""
        project_dir = self.artifacts_dir / project_id
        chats_dir = project_dir / "chats"
        chats_dir.mkdir(exist_ok=True)
        
        chat_file = chats_dir / f"{version_id}.json"
        with open(chat_file, 'w', encoding='utf-8') as f:
            json.dump(messages, f, indent=2)
        return True

    async def get_chat_version(self, project_id: str, version_id: str) -> Optional[List[Dict]]:
        """Get chat history for a specific project version"""
        project_dir = self.artifacts_dir / project_id
        chat_file = project_dir / "chats" / f"{version_id}.json"
        
        if not chat_file.exists():
            return None
            
        with open(chat_file, 'r', encoding='utf-8') as f:
            return json.load(f)

    def get_project_info(self, project_id: str) -> Optional[Dict]:
        """Get project information"""
        project_dir = self.artifacts_dir / project_id
        metadata_file = project_dir / "metadata.json"
        
        if not metadata_file.exists():
            return None
        
        try:
            with open(metadata_file, 'r') as f:
                metadata = json.load(f)
            
            # Fallback for missing fields in legacy projects
            if "name" not in metadata:
                metadata["name"] = f"Project {metadata.get('project_id', 'Unknown')[:8]}"
            if "description" not in metadata:
                metadata["description"] = ""
                
            return metadata
        except Exception as e:
            print(f"Error loading metadata for {project_id}: {e}")
            return None
    
    def get_version_code(self, project_id: str, version_id: str) -> Optional[str]:
        """Get code for specific version"""
        project_dir = self.artifacts_dir / project_id
        
        if version_id == "workspace":
            version_dir = project_dir / "workspace"
        else:
            version_dir = project_dir / "versions" / version_id
        
        if not version_dir.exists():
            return None
        
        # Try metadata first to find the main file or entrypoint
        metadata_file = version_dir / "metadata.json"
        if metadata_file.exists():
            try:
                with open(metadata_file, 'r') as f:
                    metadata = json.load(f)
                main_file = metadata.get('entrypoint') or metadata.get('main_file')
            except Exception:
                main_file = None
            
            if main_file:
                code_file = version_dir / main_file
                if code_file.exists():
                    with open(code_file, 'r', encoding='utf-8') as f:
                        return f.read()

        # Final fallback: return the first text-like file found in the root
        for p in version_dir.iterdir():
            if p.is_file() and not p.name.startswith(('.', 'metadata.json', 'package-lock.json', 'yarn.lock')):
                try:
                    return p.read_text(encoding='utf-8')
                except Exception:
                    continue
        
        return None

    def get_version_all_files(self, project_id: str, version_id: str) -> Optional[Dict]:
        """Get ALL files for a specific version as { filepath: content }"""
        project_dir = self.artifacts_dir / project_id
        
        if version_id == "workspace":
            version_dir = project_dir / "workspace"
        else:
            version_dir = project_dir / "versions" / version_id
        
        if not version_dir.exists():
            return None
        
        files = {}
        for file_path in version_dir.rglob('*'):
            if file_path.is_file() and file_path.name != 'metadata.json':
                try:
                    rel_path = str(file_path.relative_to(version_dir)).replace('\\', '/')
                    files[rel_path] = file_path.read_text(encoding='utf-8')
                except Exception:
                    continue
        
        return files

    def get_all_versions(self, project_id: str) -> List[Dict]:
        """Get metadata for all versions of a project, sorted by version_id"""
        project_dir = self.artifacts_dir / project_id
        versions_dir = project_dir / "versions"
        
        if not versions_dir.exists():
            return []
        
        versions = []
        for vdir in sorted(versions_dir.iterdir()):
            if vdir.is_dir():
                meta_file = vdir / "metadata.json"
                if meta_file.exists():
                    try:
                        with open(meta_file, 'r') as f:
                            meta = json.load(f)
                        versions.append(meta)
                    except Exception:
                        # Fallback: create basic metadata from directory name
                        versions.append({
                            "version_id": vdir.name,
                            "prompt": "",
                            "created_at": datetime.fromtimestamp(vdir.stat().st_mtime).isoformat()
                        })
                else:
                    # No metadata file, create basic entry
                    versions.append({
                        "version_id": vdir.name,
                        "prompt": "",
                        "created_at": datetime.fromtimestamp(vdir.stat().st_mtime).isoformat()
                    })
        
        return versions
    
    def list_projects(self, owner_id: Optional[int] = None) -> List[Dict]:
        """List projects, optionally filtered by owner_id"""
        projects = []
        
        for project_dir in self.artifacts_dir.iterdir():
            if project_dir.is_dir():
                metadata_file = project_dir / "metadata.json"
                if metadata_file.exists():
                    try:
                        with open(metadata_file, 'r') as f:
                            metadata = json.load(f)
                        
                        # Fallback for missing fields in legacy projects
                        if "name" not in metadata:
                            metadata["name"] = f"Project {metadata.get('project_id', 'Unknown')[:8]}"
                        if "description" not in metadata:
                            metadata["description"] = ""
                        
                        # Filter by owner_id if specified (STRICT)
                        if owner_id is not None:
                            project_owner = metadata.get("owner_id")
                            # Only show if owner matches
                            if project_owner != owner_id:
                                continue
                            
                        projects.append(metadata)
                    except Exception as e:
                        print(f"Error loading metadata for {project_dir.name}: {e}")
        
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
