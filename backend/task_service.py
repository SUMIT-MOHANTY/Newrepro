import httpx
from typing import Optional, Dict, Any
import logging
import time
import base64
import json
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
        self.token_expires_at: int = 0

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

                # Parse expiration time from JWT
                if self.access_token:
                    try:
                        payload_b64 = self.access_token.split('.')[1]
                        payload_b64 += '=' * (-len(payload_b64) % 4)
                        payload_json = base64.urlsafe_b64decode(payload_b64).decode('utf-8')
                        payload = json.loads(payload_json)
                        self.token_expires_at = payload.get('exp', 0)
                    except Exception as e:
                        logger.warning(f"Could not parse token expiration: {str(e)}")
                        self.token_expires_at = 0

                return self.access_token
            except httpx.HTTPError as e:
                logger.error(f"Failed to fetch task management token: {str(e)}")
                raise Exception(f"Failed to authenticate with Task Management API: {str(e)}")

    async def _get_headers(self) -> dict:
        """Get headers with authentication token."""
        # Refresh if token doesn't exist or expires in less than 60 seconds
        if not self.access_token or (self.token_expires_at and time.time() > self.token_expires_at - 60):
            await self._get_access_token()

        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

    async def _make_request(self, method: str, endpoint: str, task_token: Optional[str] = None, **kwargs) -> Any:
        """Make an authenticated request, handling token expiration."""
        url = f"{self.base_url.rstrip('/')}/{endpoint.lstrip('/')}"

        if task_token:
            headers = {
                "Authorization": f"Bearer {task_token}",
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
        else:
            headers = await self._get_headers()

        kwargs["headers"] = {**kwargs.get("headers", {}), **headers}

        async with httpx.AsyncClient() as client:
            response = await client.request(method, url, **kwargs)

            # If token is expired (401 Unauthorized or 403 Forbidden), refresh it and try again once
            if response.status_code in (401, 403) and not task_token:
                logger.info("Task Management API token expired, refreshing...")
                await self._get_access_token()
                new_headers = await self._get_headers()
                kwargs["headers"].update(new_headers)

                # Retry request with new token
                response = await client.request(method, url, **kwargs)

            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as e:
                response_text = response.text
                logger.error(
                    f"Task Management API request failed: {method} {url} "
                    f"status={response.status_code} response={response_text}"
                )
                raise Exception(
                    f"{method} {url} failed ({response.status_code}): {response_text}"
                ) from e

            # For 204 No Content, return None instead of trying to parse JSON
            if response.status_code == 204:
                return None

            return response.json()

    async def get_agents(self, task_token: Optional[str] = None) -> list:
        """Fetch the list of agents from the external task management API."""
        return await self._make_request("GET", "/api/agents/", task_token=task_token)

    async def get_projects(self, task_token: Optional[str] = None) -> dict:
        """Fetch the list of projects from the external task management API."""
        return await self._make_request("GET", "/api/agent/projects/", task_token=task_token)

    async def create_project(self, project_data: dict, task_token: Optional[str] = None) -> dict:
        """Create a new project using the external task management API."""
        return await self._make_request("POST", "/api/agent/projects/", task_token=task_token, json=project_data)

    async def create_task(self, task_data: dict, task_token: Optional[str] = None) -> dict:
        """Create a new task in external task management API."""
        return await self._make_request("POST", "/api/agent/tasks/", task_token=task_token, json=task_data)

    async def update_task(self, task_id: int, payload: dict, task_token: Optional[str] = None) -> dict:
        """Update a task in external task management API."""
        return await self._make_request("PATCH", f"/api/agent/tasks/{task_id}/", task_token=task_token, json=payload)

    async def assign_task(self, task_id: int, assignees: list, task_token: Optional[str] = None) -> dict:
        """Assign users to a task in external task management API."""
        payload = {"assignees": assignees}
        return await self.update_task(task_id, payload, task_token=task_token)

    async def get_tasks(self, page: int = None, task_token: Optional[str] = None) -> dict:
        """Fetch the list of generated tasks from the external task management API."""
        endpoint = "/api/agent/tasks-list"
        if page:
            endpoint += f"?page={page}"
        return await self._make_request("GET", endpoint, task_token=task_token)

    async def get_project_info(self, task_token: Optional[str] = None) -> dict:
        """Fetch project info (deadline, wallet, team) from the external task management API."""
        return await self._make_request("GET", "/api/agent/project-info/", task_token=task_token)

    async def add_checklist_to_task(self, task_id: Any, checklist_items: list, task_token: Optional[str] = None) -> dict:
        """Add checklist items to a task via the external task management API."""
        normalized_task_id = str(task_id).strip()
        if not normalized_task_id:
            raise Exception("Invalid task_id for checklist update")
        payload = {"checklistItems": checklist_items}
        return await self._make_request(
            "PUT", f"/api/agent/tasks/{normalized_task_id}/checklist/", task_token=task_token, json=payload
        )

    async def post_task_message(self, payload: dict, task_token: Optional[str] = None) -> dict:
        """Post a comment/message to a task."""
        return await self._make_request("POST", "/api/agent/messages/", task_token=task_token, json=payload)

    async def update_task_progress(self, payload: dict, task_token: Optional[str] = None) -> dict:
        """Update progress for a task."""
        return await self._make_request("POST", "/api/agent/task-progress/", task_token=task_token, json=payload)

    async def complete_task(self, payload: dict, task_token: Optional[str] = None) -> dict:
        """Mark a task as complete."""
        return await self._make_request("POST", "/api/agent/task-complete/", task_token=task_token, json=payload)

    async def post_timer_log(self, payload: dict, task_token: Optional[str] = None) -> dict:
        """Post a clock in/out log for a task."""
        return await self._make_request("POST", "/api/agent/timer-logs/", task_token=task_token, json=payload)

    async def get_dashboard(self, task_token: Optional[str] = None) -> dict:
        """Fetch dashboard insights from the external task management API."""
        return await self._make_request("GET", "/api/agent/dashboard/", task_token=task_token)

    async def opt_in_task(self, payload: dict, task_token: Optional[str] = None) -> dict:
        """Opt in to a task in the external task management API using X-API-Key."""
        if task_token:
            return await self._make_request("POST", "/api/agent/task-opt-in/", task_token=task_token, json=payload)

        url = f"{self.base_url.rstrip('/')}/api/agent/task-opt-in/"
        headers = {
            "Content-Type": "application/json",
            "X-API-Key": f"{self.client_id}:{self.client_secret}"
        }
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(url, json=payload, headers=headers, timeout=10.0)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                response_text = e.response.text
                logger.error(f"Failed to opt-in to task: {e.response.status_code} {response_text}")
                raise Exception(f"Failed to opt-in to task ({e.response.status_code}): {response_text}")

task_service = TaskManagementService()
