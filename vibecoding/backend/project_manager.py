import os
import uuid
import zipfile
import shutil
import docker
import asyncio
import time
import requests
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from pathlib import Path
import json
import logging
from runtime_detector import runtime_detector

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ProjectManager:
    """Manages container-based code execution and project artifacts"""
    
    def __init__(self, artifacts_dir: str = "project_artifacts"):
        self.artifacts_dir = Path(artifacts_dir)
        self.artifacts_dir.mkdir(exist_ok=True)
        self.docker_client = docker.from_env()
        self.running_containers: Dict[str, docker.models.containers.Container] = {}
        
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
        
        # 🚀 AUTO-DETECT RUNTIME (Like Base44/Replit)
        runtime_name, runtime_config = runtime_detector.detect(code)
        filename = runtime_detector.get_filename(runtime_name)
        
        logger.info(f"🔍 Detected runtime: {runtime_name}")
        logger.info(f"📝 Using filename: {filename}")
        logger.info(f"🐳 Docker image: {runtime_config['image']}")
        logger.info(f"🔌 Port: {runtime_config['port']}")
        
        # Save code file with correct name
        code_file = version_dir / filename
        with open(code_file, 'w', encoding='utf-8') as f:
            f.write(code)
        
        # Save version metadata
        version_metadata = {
            "version_id": version_id,
            "prompt": prompt,
            "created_at": datetime.now().isoformat(),
            "runtime": runtime_name,
            "filename": filename,
            "docker_image": runtime_config['image'],
            "port": runtime_config['port'],
        }
        
        with open(version_dir / "metadata.json", "w") as f:
            json.dump(version_metadata, f, indent=2)
        
        # Update project metadata
        self._update_project_metadata(project_id, version_id, prompt)
        
        # Automatically create ZIP after saving
        self.create_project_zip(project_id)
        
        logger.info(f"✅ Saved version {version_id} for project {project_id}")
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
        """Create Docker container for code execution using detected runtime"""
        project_dir = self.artifacts_dir / project_id
        version_dir = project_dir / "versions" / version_id
        metadata_file = version_dir / "metadata.json"
        
        # Read version metadata to get runtime info
        try:
            with open(metadata_file, 'r') as f:
                metadata = json.load(f)
            
            runtime = metadata.get('runtime', 'static-html')
            filename = metadata.get('filename', 'app.py')
            docker_image = metadata.get('docker_image', 'vibecoding-code-executor:latest')
            port = metadata.get('port', 80)
            
            logger.info(f"🚀 Creating container with runtime: {runtime}")
            logger.info(f"🐳 Docker image: {docker_image}")
            logger.info(f"🔌 Port: {port}")
            
        except Exception as e:
            logger.error(f"Failed to read metadata: {e}")
            return None
        
        code_file = version_dir / filename
        
        if not code_file.exists():
            logger.error(f"Code file not found: {code_file}")
            return None
        
        container_name = f"vibecoding_{project_id}_{version_id}"
        
        try:
            # Stop and remove existing container if it exists
            try:
                old_container = self.docker_client.containers.get(container_name)
                old_container.stop()
                old_container.remove()
                logger.info(f"Removed old container: {container_name}")
            except:
                pass
            
            # Create container with detected runtime
            logger.info(f"🏗️ Building container: {container_name}")
            
            container = self.docker_client.containers.run(
                docker_image,
                name=container_name,
                ports={f'{port}/tcp': None},  # Auto-assign host port
                volumes={
                    str(version_dir.absolute()): {
                        'bind': '/app',
                        'mode': 'rw'
                    }
                },
                working_dir='/app',
                detach=True,
                remove=False,
                environment={
                    'PYTHONUNBUFFERED': '1',
                    'PORT': str(port),
                }
            )
            
            # Store container reference
            self.running_containers[container_name] = container
            
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
