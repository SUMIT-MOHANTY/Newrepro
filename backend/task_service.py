import httpx
from typing import Optional, Dict, Any
import logging
from config import settings

logger = logging.getLogger(__name__)

class TaskManagementService:
    """
    Service to interact with the external task management API.
    A token is automatically fetched upon request and refreshed if a 401 error occurs.
    """
    
    def __init__(self):
        self.base_url = settings.task_api_base_url
        self.client_id = settings.task_api_client_id
        self.client_secret = settings.task_api_client_secret
        self.access_token: Optional[str] = None
        self.refresh_token: Optional[str] = None

    async def _get_access_token(self) -> str:
        """Fetch a new access token using client credentials."""
        token_url = f"{self.base_url.rstrip('/')}/api/token/task/"
        
        payload = {
            "client_id": self.client_id,
            "client_secret": self.client_secret
        }
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(token_url, json=payload, timeout=10.0)
                response.raise_for_status()
                data = response.json()
                self.access_token = data.get("access")
                self.refresh_token = data.get("refresh")
                return self.access_token
            except httpx.HTTPError as e:
                logger.error(f"Failed to fetch task management token: {str(e)}")
                raise Exception(f"Failed to authenticate with Task Management API: {str(e)}")

    async def _get_headers(self) -> dict:
        """Get headers with authentication token."""
        if not self.access_token:
            await self._get_access_token()
            
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

    async def _make_request(self, method: str, endpoint: str, **kwargs) -> Any:
        """Make an authenticated request, handling token expiration."""
        url = f"{self.base_url.rstrip('/')}/{endpoint.lstrip('/')}"
        
        headers = await self._get_headers()
        kwargs["headers"] = {**kwargs.get("headers", {}), **headers}
        
        async with httpx.AsyncClient() as client:
            response = await client.request(method, url, **kwargs)
            
            # If token is expired (401 Unauthorized), refresh it and try again once
            if response.status_code == 401:
                logger.info("Task Management API token expired, refreshing...")
                await self._get_access_token()
                new_headers = await self._get_headers()
                kwargs["headers"].update(new_headers)
                
                # Retry request with new token
                response = await client.request(method, url, **kwargs)
                
            response.raise_for_status()
            
            # For 204 No Content, return None instead of trying to parse JSON
            if response.status_code == 204:
                return None
                
            return response.json()

    async def get_agents(self) -> list:
        """Fetch the list of agents from the external task management API."""
        return await self._make_request("GET", "/api/agents/")

    async def create_project(self, project_data: dict) -> dict:
        """Create a new project using the external task management API."""
        return await self._make_request("POST", "/api/agent/projects/", json=project_data)

    async def create_task(self, task_data: dict) -> dict:
        """Create a new task in external task management API."""
        return await self._make_request("POST", "/api/agent/tasks/", json=task_data)

    async def get_tasks(self) -> dict:
        """Fetch the list of generated tasks from the external task management API."""
        return await self._make_request("GET", "/api/agent/tasks-list")

    async def get_project_info(self) -> dict:
        """Fetch project info (deadline, wallet, team) from the external task management API."""
        return await self._make_request("GET", "/api/agent/project-info/")

task_service = TaskManagementService()

