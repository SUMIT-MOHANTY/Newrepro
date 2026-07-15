"""
AI Agent Container Manager
Manages the lifecycle of AI agent containers
"""
import docker
import logging
import requests
import time
from ai_config import ai_config
from typing import Optional, Dict
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AIAgentManager:
    """Manages AI agent containers"""
    
    def __init__(self):
        try:
            self.docker_client = docker.from_env()
            logger.info("✅ Docker client initialized")
        except Exception as e:
            logger.error(f"❌ Docker not available: {e}")
            self.docker_client = None
        
        self.agent_container = None
        self.agent_url = None
    
    def build_agent_image(self) -> bool:
        """Build the AI agent Docker image"""
        try:
            logger.info("🏗️ Building AI agent image...")
            
            # Build from docker/agent-runtime.Dockerfile
            image, build_logs = self.docker_client.images.build(
                path=str(Path(__file__).parent / "docker"),
                dockerfile="agent-runtime.Dockerfile",
                tag="vibecoding-agent-runtime:latest",
                rm=True
            )
            
            for log in build_logs:
                if 'stream' in log:
                    logger.info(log['stream'].strip())
            
            logger.info("✅ AI agent image built successfully")
            return True
        
        except Exception as e:
            logger.error(f"❌ Failed to build image: {e}")
            return False
    
    def start_agent_container(self, api_key: str, provider: str = "anthropic") -> Optional[str]:
        """Start AI agent container"""
        if self.docker_client is None:
            logger.error("Docker not available")
            return None
        
        try:
            # Check if image exists, build if not
            try:
                self.docker_client.images.get("vibecoding-agent-runtime:latest")
            except docker.errors.ImageNotFound:
                logger.info("Image not found, building...")
                if not self.build_agent_image():
                    return None
            
            # Stop existing container if running
            self.stop_agent_container()
            
            # Start new container
            logger.info("🚀 Starting AI agent container...")
            
            # Determine backend URL for API communication
            # Use environment variable if set, otherwise detect based on deployment
            backend_url = os.environ.get('BACKEND_URL')
            if not backend_url:
                # Check if we're running in production (dsuite-backend.bourntec.com)
                if os.environ.get('PRODUCTION') == 'true':
                    backend_url = 'https://dsuite-backend.bourntec.com'
                else:
                    # Local development - use host.docker.internal to reach host from container
                    backend_url = 'http://host.docker.internal:8001'
            
            # Prepare environment variables dynamically
            env_vars = {
                "AI_PROVIDER": provider,
                "AI_API_KEY": api_key,
                "AI_API_URL": ai_config.base_url,
                "AI_MODEL": ai_config.ai_model if hasattr(ai_config, 'ai_model') else ai_config.model,
                "AI_TIMEOUT": "120",
                "BACKEND_URL": backend_url  # Add backend URL for API communication
            }
            
            # Also forward provider-specific keys for backward compatibility
            if "anthropic" in provider.lower():
                env_vars["ANTHROPIC_API_KEY"] = api_key
            elif "openai" in provider.lower():
                env_vars["OPENAI_API_KEY"] = api_key
            
            logger.info(f"🔗 Agent will communicate with backend at: {backend_url}")
            
            self.agent_container = self.docker_client.containers.run(
                "vibecoding-agent-runtime:latest",
                name="vibecoding-ai-agent",
                detach=True,
                remove=False,
                ports={'8080/tcp': None},  # Auto-assign port
                environment=env_vars,
                # Only mount Docker socket - no database mount needed anymore!
                volumes={
                    '/var/run/docker.sock': {
                        'bind': '/var/run/docker.sock',
                        'mode': 'rw'
                    }
                },
                # Add extra_hosts for Linux compatibility with host.docker.internal
                extra_hosts={'host.docker.internal': 'host-gateway'} if backend_url.startswith('http://host.docker.internal') else None
            )
            
            # Get assigned port
            self.agent_container.reload()
            port_bindings = self.agent_container.ports.get('8080/tcp', [])
            if not port_bindings:
                logger.error("No port binding found")
                return None
            
            host_port = port_bindings[0].get('HostPort')
            self.agent_url = f"http://localhost:{host_port}"
            
            logger.info(f"✅ AI agent running at {self.agent_url}")
            
            # Wait for agent to be ready
            if self._wait_for_agent():
                return self.agent_url
            else:
                logger.error("Agent failed to start")
                return None
        
        except Exception as e:
            logger.error(f"Failed to start agent container: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def stop_agent_container(self):
        """Stop AI agent container"""
        try:
            if self.agent_container:
                self.agent_container.stop()
                self.agent_container.remove()
                logger.info("Stopped AI agent container")
                self.agent_container = None
                self.agent_url = None
        except:
            pass
        
        # Also try to stop by name
        try:
            container = self.docker_client.containers.get("vibecoding-ai-agent")
            container.stop()
            container.remove()
        except:
            pass
    
    def send_request(self, message: str) -> Dict:
        """Send request to AI agent"""
        if not self.agent_url:
            return {
                "success": False,
                "error": "AI agent not running"
            }
        
        try:
            response = requests.post(
                self.agent_url,
                json={"message": message},
                timeout=300  # 5 minutes timeout for code generation
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                return {
                    "success": False,
                    "error": f"Agent returned status {response.status_code}"
                }
        
        except Exception as e:
            logger.error(f"Failed to send request to agent: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def _wait_for_agent(self, timeout: int = 30) -> bool:
        """Wait for agent to be ready"""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                response = requests.get(f"{self.agent_url}/health", timeout=2)
                if response.status_code == 200:
                    logger.info("✅ AI agent is ready")
                    return True
            except:
                pass
            
            time.sleep(1)
        
        return False
    
    def get_agent_logs(self, lines: int = 50) -> str:
        """Get logs from agent container"""
        if not self.agent_container:
            return "No agent container running"
        
        try:
            logs = self.agent_container.logs(tail=lines).decode('utf-8')
            return logs
        except Exception as e:
            return f"Failed to get logs: {e}"


# Singleton instance
_agent_manager = None

def get_agent_manager() -> AIAgentManager:
    """Get singleton agent manager instance"""
    global _agent_manager
    if _agent_manager is None:
        _agent_manager = AIAgentManager()
    return _agent_manager
