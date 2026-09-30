"""
Playground Container Manager — Docker Lifecycle for Agent Runtime Playgrounds.

Manages dedicated and shared playground containers for agents in an organization.
Enforces that total active containers do not exceed the organization's max_agent_capacity.
Agents acquire a container from the pool, execute tasks sequentially from their queue,
and release the container back to the idle pool upon completion.
"""

from __future__ import annotations

import logging
import os
import subprocess
import threading
import time
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# Prefer dsuite-agent-runtime:latest since it contains both Python 3.12 and Node 20.20
PREFERRED_IMAGES = [
    "dsuite-agent-runtime:latest",
    "python:3.10-slim",
    "node:18-slim",
    "ubuntu:22.04",
]


class PlaygroundContainerManager:
    """Manages Docker playground containers for agent execution."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.containers: Dict[str, Dict[str, Any]] = {}
        self._docker_client = None
        self._init_docker()

    def _init_docker(self) -> None:
        try:
            import docker
            client = docker.from_env()
            client.ping()
            self._docker_client = client
            logger.info("[PlaygroundManager] Docker client connected successfully.")
        except Exception as exc:
            logger.warning(f"[PlaygroundManager] Docker client connection error: {exc}. Will use subprocess CLI fallback.")
            self._docker_client = None

    def _get_available_image(self) -> str:
        """Find the best available Docker image locally."""
        if self._docker_client:
            try:
                local_images = [tag for img in self._docker_client.images.list() for tag in (img.tags or [])]
                for preferred in PREFERRED_IMAGES:
                    if any(preferred in t for t in local_images):
                        return preferred
            except Exception:
                pass
        return "dsuite-agent-runtime:latest"

    def _is_container_running(self, container_name: str) -> bool:
        if self._docker_client:
            try:
                c = self._docker_client.containers.get(container_name)
                return c.status == "running"
            except Exception:
                return False
        try:
            res = subprocess.run(
                ["docker", "inspect", "-f", "{{.State.Running}}", container_name],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return res.stdout.strip().lower() == "true"
        except Exception:
            return False

    def acquire_playground(
        self,
        org_name: str,
        project_token: str,
        agent_id: str,
        workspace_host_path: str,
        max_capacity: int = 10,
    ) -> Optional[str]:
        """
        Acquire or provision a playground container for the agent.
        Enforces that running containers do not exceed max_capacity.
        """
        with self.lock:
            # 1. If an existing container is already assigned and running for this agent/project, reuse it
            for name, meta in self.containers.items():
                if (
                    meta.get("status") == "BUSY"
                    and meta.get("agent_id") == agent_id
                    and meta.get("project_token") == project_token
                ):
                    if self._is_container_running(name):
                        logger.info(f"[PlaygroundManager] Reusing active container {name} for agent {agent_id}")
                        return name

            # 2. Check for an IDLE container in our registered pool
            for name, meta in self.containers.items():
                if meta.get("status") == "IDLE":
                    if self._ensure_container_started(name, workspace_host_path):
                        meta["status"] = "BUSY"
                        meta["agent_id"] = agent_id
                        meta["project_token"] = project_token
                        meta["org_name"] = org_name
                        meta["last_used"] = time.time()
                        logger.info(f"[PlaygroundManager] Re-assigned IDLE container {name} to agent {agent_id}")
                        return name

            # 3. Check capacity limit before creating a new container
            running_count = self.get_running_containers_count()
            if running_count >= max_capacity:
                logger.warning(
                    f"[PlaygroundManager] Max container capacity reached ({running_count}/{max_capacity}). "
                    f"Attempting to reuse LRU idle container..."
                )
                # Find oldest idle container
                lru_name = None
                lru_time = float("inf")
                for name, meta in self.containers.items():
                    if meta.get("status") == "IDLE" and meta.get("last_used", 0) < lru_time:
                        lru_name = name
                        lru_time = meta.get("last_used", 0)

                if lru_name and self._ensure_container_started(lru_name, workspace_host_path):
                    self.containers[lru_name].update({
                        "status": "BUSY",
                        "agent_id": agent_id,
                        "project_token": project_token,
                        "org_name": org_name,
                        "last_used": time.time(),
                    })
                    return lru_name

            # 4. Provision a new playground container
            clean_org = "".join(c for c in (org_name or "default") if c.isalnum() or c == "_")[:12].lower()
            slot = len(self.containers) + 1
            container_name = f"dsuite_playground_{clean_org}_{slot}"

            # Make sure no conflicting stale container with this name exists in Docker
            self._force_remove_container(container_name)

            image = self._get_available_image()
            logger.info(
                f"[PlaygroundManager] Provisioning new playground container '{container_name}' "
                f"using image '{image}' (mount: {workspace_host_path} -> /workspace)..."
            )

            try:
                os.makedirs(workspace_host_path, exist_ok=True)
                if self._docker_client:
                    c = self._docker_client.containers.run(
                        image=image,
                        name=container_name,
                        detach=True,
                        volumes={os.path.abspath(workspace_host_path): {"bind": "/workspace", "mode": "rw"}},
                        working_dir="/workspace",
                        entrypoint="/bin/sh",
                        command=["-c", "mkdir -p /var/log && printf '[Playground Container Online] Ready for Agent Swarm execution.\\n' > /proc/1/fd/1; tail -f /dev/null"],
                        network_mode="bridge",
                        remove=False,
                        labels={
                            "dsuite.org": org_name,
                            "dsuite.project": project_token,
                            "dsuite.agent": agent_id,
                            "dsuite.role": "playground",
                        },
                    )
                    c_id = c.id
                else:
                    cmd = [
                        "docker", "run", "-d",
                        "--name", container_name,
                        "-v", f"{os.path.abspath(workspace_host_path)}:/workspace",
                        "-w", "/workspace",
                        "--entrypoint", "/bin/sh",
                        image,
                        "-c", "mkdir -p /var/log && printf '[Playground Container Online] Ready for Agent Swarm execution.\\n' > /proc/1/fd/1; tail -f /dev/null",
                    ]
                    res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                    if res.returncode != 0:
                        logger.error(f"[PlaygroundManager] Failed to launch container CLI: {res.stderr}")
                        return None
                    c_id = res.stdout.strip()

                self.containers[container_name] = {
                    "id": c_id,
                    "status": "BUSY",
                    "org_name": org_name,
                    "project_token": project_token,
                    "agent_id": agent_id,
                    "workspace_path": workspace_host_path,
                    "image": image,
                    "last_used": time.time(),
                }
                logger.info(f"[PlaygroundManager] Container '{container_name}' successfully provisioned and running.")
                self.append_log_to_container(container_name, f"🚀 Playground initialized for {agent_id} in {org_name}.")
                return container_name

            except Exception as e:
                logger.error(f"[PlaygroundManager] Error provisioning container {container_name}: {e}", exc_info=True)
                return None

    def _ensure_container_started(self, container_name: str, workspace_host_path: str) -> bool:
        """Ensure an existing container is active and mounted correctly."""
        try:
            if self._is_container_running(container_name):
                return True
            logger.info(f"[PlaygroundManager] Starting container '{container_name}'...")
            if self._docker_client:
                c = self._docker_client.containers.get(container_name)
                c.start()
            else:
                subprocess.run(["docker", "start", container_name], capture_output=True, timeout=15)
            return self._is_container_running(container_name)
        except Exception as e:
            logger.warning(f"[PlaygroundManager] Could not restart {container_name}: {e}")
            return False

    def _force_remove_container(self, container_name: str) -> None:
        try:
            if self._docker_client:
                try:
                    c = self._docker_client.containers.get(container_name)
                    c.remove(force=True)
                except Exception:
                    pass
            else:
                subprocess.run(["docker", "rm", "-f", container_name], capture_output=True, timeout=10)
        except Exception:
            pass

    def append_log_to_container(self, container_name: str, message: str) -> None:
        """Stream formatted log directly into PID 1 stdout and /var/log/agent.log so `docker logs <container>` displays live output."""
        try:
            import datetime
            now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            formatted = f"[{now_str}] {message}"
            safe = formatted.replace('\\', '\\\\').replace('"', '\\"').replace('$', '\\$').replace('`', '\\`')
            # Write directly to PID 1 stdout (/proc/1/fd/1) so docker logs captures it, and persist to file
            cmd = f'printf "%s\\n" "{safe}" > /proc/1/fd/1 2>/dev/null; printf "%s\\n" "{safe}" >> /var/log/agent.log 2>/dev/null || true'
            if self._docker_client:
                c = self._docker_client.containers.get(container_name)
                c.exec_run(cmd=["sh", "-c", cmd], demux=False)
            else:
                subprocess.run(["docker", "exec", container_name, "sh", "-c", cmd], capture_output=True, timeout=5)
        except Exception as e:
            logger.debug(f"[PlaygroundManager] Failed writing log to {container_name}: {e}")

    def write_file_in_playground(self, container_name: str, relative_path: str, content: str) -> Tuple[bool, str]:
        """Write a file inside /workspace in the playground container via mounted host volume."""
        try:
            meta = self.containers.get(container_name)
            host_root = meta.get("workspace_path") if meta else None
            if not host_root:
                # Try finding from running containers
                for m in self.containers.values():
                    if m.get("workspace_path"):
                        host_root = m["workspace_path"]
                        break
            if host_root:
                host_path = os.path.join(host_root, relative_path.replace("/", os.sep))
                os.makedirs(os.path.dirname(host_path), exist_ok=True)
                with open(host_path, "w", encoding="utf-8") as f:
                    f.write(content)
                line_count = len(content.splitlines())
                msg = f"📄 [Tool: write_file] Wrote /workspace/{relative_path} ({line_count} lines)"
                self.append_log_to_container(container_name, msg)
                return True, msg
            return False, "Workspace path not found for container"
        except Exception as e:
            err = f"Failed to write {relative_path}: {e}"
            self.append_log_to_container(container_name, f"❌ [Tool: write_file] {err}")
            return False, err

    def exec_in_playground(
        self,
        container_name: str,
        command: str,
        workdir: str = "/workspace",
        timeout: int = 45,
    ) -> Tuple[int, str]:
        """
        Execute a shell command inside the playground container.
        Returns (exit_code, output_text).
        Logs command and output into container's /var/log/agent.log.
        """
        self.append_log_to_container(container_name, f"$ {command}")
        try:
            if self._docker_client:
                c = self._docker_client.containers.get(container_name)
                exec_res = c.exec_run(
                    cmd=["sh", "-c", command],
                    workdir=workdir,
                    demux=False,
                )
                output = exec_res.output.decode("utf-8", errors="replace") if exec_res.output else ""
                if output.strip():
                    self.append_log_to_container(container_name, output.strip()[:1000])
                return exec_res.exit_code, output
            else:
                cmd = ["docker", "exec", "-w", workdir, container_name, "sh", "-c", command]
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
                output = (res.stdout or "") + (res.stderr or "")
                if output.strip():
                    self.append_log_to_container(container_name, output.strip()[:1000])
                return res.returncode, output
        except subprocess.TimeoutExpired:
            self.append_log_to_container(container_name, f"Command timed out after {timeout}s")
            return -1, f"Command timed out after {timeout} seconds."
        except Exception as e:
            self.append_log_to_container(container_name, f"Execution failed: {e}")
            return -1, f"Execution failed: {e}"

    def release_playground(self, container_name: str, stop: bool = False) -> None:
        """Mark container as IDLE so other agents can reuse it, or optionally stop it."""
        with self.lock:
            if container_name in self.containers:
                self.containers[container_name]["status"] = "IDLE"
                self.containers[container_name]["last_used"] = time.time()
                logger.info(f"[PlaygroundManager] Released container '{container_name}' to IDLE pool.")

        if stop:
            try:
                if self._docker_client:
                    c = self._docker_client.containers.get(container_name)
                    c.stop(timeout=5)
                else:
                    subprocess.run(["docker", "stop", "-t", "5", container_name], capture_output=True, timeout=10)
            except Exception as e:
                logger.warning(f"[PlaygroundManager] Error stopping {container_name}: {e}")

    def get_running_containers_count(self) -> int:
        """Return the count of actively running dsuite playground containers."""
        try:
            if self._docker_client:
                running = self._docker_client.containers.list(filters={"name": "dsuite_playground_"})
                return len(running)
            res = subprocess.run(
                ["docker", "ps", "--filter", "name=dsuite_playground_", "--format", "{{.Names}}"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if res.returncode == 0:
                names = [line.strip() for line in res.stdout.splitlines() if line.strip()]
                return len(names)
        except Exception as e:
            logger.warning(f"[PlaygroundManager] Error counting running containers: {e}")
        return len([c for c in self.containers.values() if c.get("status") == "BUSY"])

    def cleanup_all(self) -> None:
        """Cleanly remove all playground containers."""
        with self.lock:
            for name in list(self.containers.keys()):
                self._force_remove_container(name)
            self.containers.clear()


# Global singleton instance
playground_manager = PlaygroundContainerManager()
