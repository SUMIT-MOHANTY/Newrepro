import os
import subprocess
import logging
import threading
import time
from typing import Dict, Any, Optional, List

logger = logging.getLogger("container_pool_manager")

class WorkerContainerPoolManager:
    """
    Manages a pool of generic, reusable Docker worker containers (e.g. dsuite_worker_pool_01).
    Enforces strict physical container caps set by Super Admin (max_agent_capacity).
    Handles container acquisition, workspace sanitization, idle borrowing, and graceful handover.
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(WorkerContainerPoolManager, cls).__new__(cls)
                cls._instance._init_manager()
            return cls._instance

    def _init_manager(self):
        self.pool_lock = threading.Lock()
        # Pool registry: { container_name: { "status": "IDLE"|"BUSY", "assigned_org": str, "project_token": str, "agent_kind": str, "current_task_id": str, "last_used": float } }
        self.containers: Dict[str, Dict[str, Any]] = {}
        self.max_cap = 10  # Default cap, synced dynamically from OrganizationAgentQuota

    def sync_max_capacity(self, new_cap: int):
        with self.pool_lock:
            if new_cap > 0:
                self.max_cap = new_cap
                logger.info(f"[ContainerPoolManager] Synced max_agent_capacity to {self.max_cap}")

    def _format_container_name(self, index: int) -> str:
        return f"dsuite_worker_pool_{index:02d}"

    def _is_container_running(self, container_name: str) -> bool:
        try:
            res = subprocess.run(
                ["docker", "inspect", "-f", "{{.State.Running}}", container_name],
                capture_output=True, text=True, timeout=5
            )
            return res.returncode == 0 and res.stdout.strip().lower() == "true"
        except Exception:
            return False

    def _ensure_physical_container(self, container_name: str) -> bool:
        """Create and start a generic reusable worker container if it does not exist."""
        try:
            # Check if exists
            check = subprocess.run(
                ["docker", "inspect", container_name],
                capture_output=True, text=True, timeout=5
            )
            if check.returncode != 0:
                # Create generic container
                logger.info(f"[ContainerPoolManager] Creating generic worker container: {container_name}")
                create_res = subprocess.run(
                    [
                        "docker", "create",
                        "--name", container_name,
                        "-w", "/workspace",
                        "ubuntu:22.04",
                        "tail", "-f", "/dev/null"
                    ],
                    capture_output=True, text=True, timeout=15
                )
                if create_res.returncode != 0:
                    logger.error(f"Failed to create {container_name}: {create_res.stderr}")
                    return False

            # Ensure started
            if not self._is_container_running(container_name):
                logger.info(f"[ContainerPoolManager] Starting worker container: {container_name}")
                start_res = subprocess.run(["docker", "start", container_name], capture_output=True, text=True, timeout=15)
                if start_res.returncode != 0:
                    logger.error(f"Failed to start {container_name}: {start_res.stderr}")
                    return False
                
                # Ensure /workspace directory exists
                subprocess.run(["docker", "exec", container_name, "mkdir", "-p", "/workspace"], capture_output=True, timeout=10)

            return True
        except Exception as e:
            logger.error(f"[ContainerPoolManager] Error provisioning {container_name}: {e}")
            return False

    def acquire_worker(
        self,
        org_name: str,
        project_token: str,
        agent_kind: str = "shared",
        agent_id: Optional[str] = None,
        max_cap_limit: Optional[int] = None
    ) -> Optional[str]:
        """
        Acquire a generic reusable worker container from the pool.
        Enforces that total containers <= max_cap_limit.
        """
        with self.pool_lock:
            if max_cap_limit and max_cap_limit > 0:
                self.max_cap = max_cap_limit

            # 1. Check if a worker is already busy for this exact project/agent
            for name, meta in self.containers.items():
                if meta["status"] == "BUSY" and meta.get("project_token") == project_token and meta.get("agent_id") == agent_id:
                    if self._is_container_running(name):
                        return name

            # 2. Find an IDLE container in our pool registry
            for name, meta in self.containers.items():
                if meta["status"] == "IDLE":
                    if self._ensure_physical_container(name):
                        meta["status"] = "BUSY"
                        meta["assigned_org"] = org_name
                        meta["project_token"] = project_token
                        meta["agent_kind"] = agent_kind
                        meta["agent_id"] = agent_id
                        meta["last_used"] = time.time()
                        logger.info(f"[ContainerPoolManager] Reusing idle worker {name} for project {project_token}")
                        return name

            # 3. Provision a new worker container if pool size < max_cap
            current_pool_size = len(self.containers)
            if current_pool_size < self.max_cap:
                next_index = current_pool_size + 1
                container_name = self._format_container_name(next_index)
                if self._ensure_physical_container(container_name):
                    self.containers[container_name] = {
                        "status": "BUSY",
                        "assigned_org": org_name,
                        "project_token": project_token,
                        "agent_kind": agent_kind,
                        "agent_id": agent_id,
                        "last_used": time.time()
                    }
                    logger.info(f"[ContainerPoolManager] Allocated new worker {container_name} ({next_index}/{self.max_cap})")
                    return container_name

            # 4. If pool is full, find the least recently used idle container or steal an idle container
            lru_container = None
            lru_time = float("inf")
            for name, meta in self.containers.items():
                if meta["status"] == "IDLE" and meta["last_used"] < lru_time:
                    lru_time = meta["last_used"]
                    lru_container = name

            if lru_container and self._ensure_physical_container(lru_container):
                self.containers[lru_container].update({
                    "status": "BUSY",
                    "assigned_org": org_name,
                    "project_token": project_token,
                    "agent_kind": agent_kind,
                    "agent_id": agent_id,
                    "last_used": time.time()
                })
                logger.info(f"[ContainerPoolManager] Reassigned LRU worker {lru_container}")
                return lru_container

            # Fallback: if all workers are busy, return the first running worker to avoid hard blocking
            if self.containers:
                fallback_name = list(self.containers.keys())[0]
                if self._ensure_physical_container(fallback_name):
                    return fallback_name

            # Ultimate fallback if pool empty
            default_name = self._format_container_name(1)
            if self._ensure_physical_container(default_name):
                self.containers[default_name] = {
                    "status": "BUSY",
                    "assigned_org": org_name,
                    "project_token": project_token,
                    "agent_kind": agent_kind,
                    "agent_id": agent_id,
                    "last_used": time.time()
                }
                return default_name

            return None

    def sanitize_workspace(self, container_name: str):
        """Sanitize /workspace inside worker container so it is clean for the next agent."""
        try:
            cmd = ["docker", "exec", container_name, "sh", "-c", "rm -rf /workspace/* /workspace/.* 2>/dev/null || true"]
            subprocess.run(cmd, capture_output=True, timeout=10)
            logger.info(f"[ContainerPoolManager] Sanitized workspace for {container_name}")
        except Exception as e:
            logger.warning(f"Failed to sanitize workspace in {container_name}: {e}")

    def release_worker(self, container_name: str, sanitize: bool = True):
        """Release worker container back to IDLE state."""
        with self.pool_lock:
            if container_name in self.containers:
                self.containers[container_name]["status"] = "IDLE"
                self.containers[container_name]["last_used"] = time.time()
                logger.info(f"[ContainerPoolManager] Released worker {container_name} to IDLE pool")
        if sanitize:
            self.sanitize_workspace(container_name)

    def get_running_containers_count(self) -> int:
        """Returns live running generic worker pool container count."""
        try:
            cmd = ["docker", "ps", "--format", "{{.Names}}"]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)
            if res.returncode == 0:
                names = [l.strip() for l in res.stdout.splitlines() if l.strip()]
                pool_containers = [n for n in names if n.startswith("dsuite_worker_pool_") or n.startswith("agt_") or n.startswith("git_manager")]
                return len(pool_containers) if pool_containers else len(names)
        except Exception as e:
            logger.warning(f"Error checking running containers count: {e}")
        return len(self.containers)

# Global singleton accessor
pool_manager = WorkerContainerPoolManager()
