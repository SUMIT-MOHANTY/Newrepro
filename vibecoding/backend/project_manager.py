import os
import uuid
import zipfile
import shutil
import docker
import asyncio
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from pathlib import Path
import json
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ProjectManager:
    """Manages container-based code execution and project artifacts"""
    
    def __init__(self, artifacts_dir: str = "project_artifacts"):
        self.artifacts_dir = Path(artifacts_dir)
        self.artifacts_dir.mkdir(exist_ok=True)
        self._docker_client = None
        self.running_containers: Dict[str, docker.models.containers.Container] = {}
    
    @property
    def docker_client(self):
        """Lazy load Docker client on first access"""
        if self._docker_client is None:
            try:
                self._docker_client = docker.from_env()
            except docker.errors.DockerException as e:
                logger.warning(f"Docker is not available: {str(e)}")
                return None
        return self._docker_client
        
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
        
        # Determine file type and extension
        file_extension = "html"
        is_python_file = False
        
        if code.strip().startswith(('from flask', 'import flask', 'app = Flask', 'def ', 'class ')) and 'def ' in code:
            file_extension = "py"
            is_python_file = True
        elif code.strip().startswith('<!DOCTYPE') or '<html' in code:
            file_extension = "html"
            is_python_file = False
        
        # Save code file
        code_file = version_dir / f"index.{file_extension}"
        with open(code_file, 'w', encoding='utf-8') as f:
            f.write(code)
        
        # Save version metadata
        version_metadata = {
            "version_id": version_id,
            "prompt": prompt,
            "created_at": datetime.now().isoformat(),
            "files": [f"index.{file_extension}"],
            "file_type": "python" if is_python_file else "html"
        }
        
        with open(version_dir / "metadata.json", "w") as f:
            json.dump(version_metadata, f, indent=2)
        
        # Update project metadata
        self._update_project_metadata(project_id, version_id, prompt)
        
        # Automatically create ZIP after saving
        self.create_project_zip(project_id)
        
        logger.info(f"Saved version {version_id} for project {project_id} and created ZIP")
        return version_id, code_file
    
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
    
    async def create_container_for_code(self, project_id: str, version_id: str) -> Optional[str]:
        """Create Docker container for code execution"""
        project_dir = self.artifacts_dir / project_id
        version_dir = project_dir / "versions" / version_id
        metadata_file = version_dir / "metadata.json"
        
        # Read version metadata to determine file type
        try:
            with open(metadata_file, 'r') as f:
                version_metadata = json.load(f)
            file_type = version_metadata.get('file_type', 'html')
            main_file = f"index.{version_metadata.get('files', ['index.html'])[0].split('.')[1]}"
        except:
            file_type = 'html'
            main_file = 'index.html'
        
        code_file = version_dir / main_file
        
        if not code_file.exists():
            logger.error(f"Code file not found: {code_file}")
            return None
        
        container_name = f"vibecoding_{project_id}_{version_id}"
        
        try:
            # Stop and remove existing container if it exists
            if container_name in self.running_containers:
                container = self.running_containers[container_name]
                container.stop()
                container.remove()
                del self.running_containers[container_name]
            
            # Convert path to absolute path for Docker volume
            abs_code_path = str(code_file.absolute())
            
            if self.docker_client is None:
                logger.error("Docker is not available. Cannot execute code.")
                raise RuntimeError("Docker is not available. Please start Docker daemon.")
            
            if file_type == 'python':
                # Use Python container for Python files
                container = self.docker_client.containers.run(
                    "vibecoding-python-executor:latest",
                    name=container_name,
                    ports={'5000/tcp': None},  # Auto-assign port
                    volumes={
                        abs_code_path: {
                            'bind': '/app',
                            'mode': 'rw'
                        }
                    },
                    working_dir='/app',
                    command=["python", "index.py"],
                    detach=True,
                    remove=False
                )
                
                # Get assigned port
                container.reload()
                port = container.ports['5000/tcp'][0]['HostPort']
                
                logger.info(f"Python container {container_name} running on port {port}")
                return f"http://localhost:{port}"
                
            else:
                # Use Nginx container for HTML files
                container = self.docker_client.containers.run(
                    "vibecoding-code-executor:latest",
                    name=container_name,
                    ports={'80/tcp': None},  # Auto-assign port
                    volumes={
                        abs_code_path: {
                            'bind': '/usr/share/nginx/html',
                            'mode': 'ro'
                        }
                    },
                    detach=True,
                    remove=False
                )
                
                # Get assigned port
                container.reload()
                port = container.ports['80/tcp'][0]['HostPort']
                
                logger.info(f"Nginx container {container_name} running on port {port}")
                return f"http://localhost:{port}"
            
        except Exception as e:
            logger.error(f"Failed to create container: {str(e)}")
            return None
    
    def stop_container(self, project_id: str, version_id: str):
        """Stop and remove container"""
        container_name = f"vibecoding_{project_id}_{version_id}"
        
        if container_name in self.running_containers:
            try:
                container = self.running_containers[container_name]
                container.stop()
                container.remove()
                del self.running_containers[container_name]
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
        code_file = version_dir / "index.html"
        
        if not code_file.exists():
            return None
        
        with open(code_file, 'r', encoding='utf-8') as f:
            return f.read()
    
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
