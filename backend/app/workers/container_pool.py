"""
Container Pool Worker
Manages the Docker container execution pool for multi-agent workloads.
"""

import logging
from typing import Any, Dict, Optional
import os
import sys

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

try:
    from container_pool_manager import WorkerContainerPoolManager
except ImportError:
    WorkerContainerPoolManager = None

logger = logging.getLogger(__name__)


class ContainerPoolWorker:
    """
    Worker abstraction for managing dedicated & shared agent Docker containers.
    """

    def __init__(self):
        self._pool = WorkerContainerPoolManager() if WorkerContainerPoolManager else None

    def sync_capacity(self, max_capacity: int):
        """Synchronize the container pool maximum capacity with DB quotas."""
        if self._pool:
            self._pool.sync_max_capacity(max_capacity)

    def acquire(
        self,
        assigned_org: str,
        project_token: str,
        agent_kind: str,
        task_id: str = "",
    ) -> Optional[str]:
        """
        Acquire an available container from the pool or allocate a new one within quota.
        Returns container name or None if at capacity.
        """
        if not self._pool:
            logger.warning("[ContainerPoolWorker] Container pool manager unavailable.")
            return None
        return self._pool.acquire_worker(
            assigned_org=assigned_org,
            project_token=project_token,
            agent_kind=agent_kind,
            current_task_id=task_id,
        )

    def release(self, container_name: str, force_sanitize: bool = False):
        """Release a container back to the idle pool or sanitize workspace."""
        if self._pool:
            self._pool.release_worker(container_name, force_sanitize=force_sanitize)

    def get_status(self) -> Dict[str, Any]:
        """Return the current utilization and health status of the container pool."""
        if not self._pool:
            return {"active_containers": 0, "max_capacity": 0, "containers": {}}
        return {
            "max_capacity": getattr(self._pool, "max_cap", 0),
            "running_count": self._pool.get_running_containers_count(),
            "containers": getattr(self._pool, "containers", {}),
        }


container_pool_worker = ContainerPoolWorker()
