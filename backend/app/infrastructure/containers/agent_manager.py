"""AgentManager — Docker SDK Controller for Agent Runtime Containers.

Starts, stops, monitors, and proxies Docker containers running the isolated
agent-runtime.
"""
from __future__ import annotations

import os
import time
import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from app.core.config import get_settings


class ContainerStatus(str, Enum):
    running = "running"
    stopped = "stopped"
    not_found = "not_found"
    error = "error"


@dataclass
class AgentContainerConfig:
    """All settings needed to start one Agent Runtime container."""
    session_id: str
    task_id: str
    task_type: str
    prompt: str
    workspace_path: str   # absolute host path — bind-mounted to /workspace
    project_id: str
    tenant_id: str
    callback_url: str
    callback_secret: str
    model: str | None = None
    user_id: str | None = None
    repo_url: str | None = None
    git_token: str | None = None
    git_branch: str | None = "main"
    tools: list[str] | None = None


_cached_docker_client = None
_docker_initialized = False


def _get_shared_docker_client():
    global _cached_docker_client, _docker_initialized
    if _docker_initialized:
        return _cached_docker_client
    try:
        import docker
        client = docker.from_env()
        client.ping()
        print("[AgentManager] Docker client initialized")
        _cached_docker_client = client
    except Exception as exc:
        print(f"[AgentManager] Docker unavailable — running in stub/dev mode: {exc}")
        _cached_docker_client = None
    _docker_initialized = True
    return _cached_docker_client


class AgentManager:
    """Infrastructure abstraction for Agent Runtime container lifecycle."""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._image = self._settings.agent_runtime_image
        self._client = _get_shared_docker_client()
        print(f"[AgentManager] Initialized with agent runtime image: '{self._image}'")

    def start_runtime(self, config: AgentContainerConfig) -> str:
        """Start or wake an Agent Runtime container for a project. Returns container_id."""
        if self._client is None:
            print(f"[AgentManager] Dev/Stub: would start container for session {config.session_id}")
            return f"stub-container-{config.session_id[:8]}"

        env = self._build_env(config)
        volumes = {
            config.workspace_path: {"bind": "/workspace", "mode": "rw"},
        }
        clean_project_id = config.project_id.replace("/", "_").replace("\\", "_")[:16]
        container_name = f"dsuite-agent-{clean_project_id}"

        # Queue prompt signal in the workspace volume
        try:
            signal_data = {
                "session_id": config.session_id,
                "task_id": config.task_id,
                "task_type": config.task_type,
                "prompt": config.prompt,
                "model": config.model,
                "repo_url": config.repo_url,
                "git_token": config.git_token,
                "git_branch": config.git_branch,
                "allowed_tools": config.tools or ["filesystem", "git", "terminal", "build_tool"],
                "timestamp": time.time(),
            }
            signal_fname = f"prompt_{int(time.time()*1000)}_{config.task_id[:8]}.json"
            signal_path = os.path.join(config.workspace_path, ".agent_signals", signal_fname)
            os.makedirs(os.path.dirname(signal_path), exist_ok=True)
            with open(signal_path, "w", encoding="utf-8") as f:
                json.dump(signal_data, f)
            print(f"[AgentManager] Prompt signal queued at {signal_path}")
        except Exception as sig_err:
            print(f"[AgentManager] Warning queueing prompt signal: {sig_err}")

        # Check existing container
        try:
            existing = self._client.containers.get(container_name)
            if existing:
                status = existing.status
                if status == "running":
                    print(f"[AgentManager] Container {existing.id[:12]} ({container_name}) already running — signal queued")
                    return existing.id
                elif status in ("exited", "stopped", "created"):
                    exit_code = existing.attrs.get("State", {}).get("ExitCode", 0)
                    init_marker = os.path.join(config.workspace_path, ".agent_initialized")
                    if exit_code == 0 and os.path.exists(init_marker):
                        try:
                            print(f"[AgentManager] Waking up sleeping container {existing.id[:12]} ({container_name})...")
                            existing.start()
                            return existing.id
                        except Exception as wake_err:
                            print(f"[AgentManager] Could not wake container {existing.id[:12]} ({wake_err}) — recreating")
                            try:
                                existing.remove(force=True)
                            except Exception:
                                pass
                    else:
                        try:
                            existing.remove(force=True)
                        except Exception:
                            pass
                else:
                    try:
                        existing.remove(force=True)
                    except Exception:
                        pass
        except Exception as inspect_err:
            try:
                stale = self._client.containers.get(container_name)
                stale.remove(force=True)
            except Exception:
                pass

        try:
            print(f"[AgentManager] Starting agent container '{container_name}' using image: '{self._image}'")
            container = self._client.containers.run(
                image=self._image,
                name=container_name,
                detach=True,
                environment=env,
                volumes=volumes,
                ports={"80/tcp": ("127.0.0.1", None)},
                extra_hosts={"host.docker.internal": "host-gateway"},
                mem_limit=self._settings.agent_container_memory_limit,
                cpu_quota=self._settings.agent_container_cpu_quota,
                cpu_period=100_000,
                network_mode="bridge",
                remove=False,
                labels={
                    "dsuite.session_id": config.session_id,
                    "dsuite.tenant_id": config.tenant_id,
                    "dsuite.project_id": config.project_id,
                },
            )
            print(f"[AgentManager] Started container {container.id[:12]} ({container_name}) for session {config.session_id}")
            return container.id
        except Exception as exc:
            print(f"[AgentManager] Failed to start container: {exc}")
            raise

    def stop_runtime(self, container_id: str, timeout: int = 0) -> None:
        """Soft-stop: Cancel active task without killing container."""
        if self._client is None or container_id.startswith("stub-"):
            return
        try:
            container = self._client.containers.get(container_id)
            workspace_host_path = None
            for m in container.attrs.get("Mounts", []):
                if m.get("Destination") == "/workspace":
                    workspace_host_path = m.get("Source")
                    break

            if workspace_host_path and os.path.exists(workspace_host_path):
                sig_dir = os.path.join(workspace_host_path, ".agent_signals")
                os.makedirs(sig_dir, exist_ok=True)
                cancel_file = os.path.join(sig_dir, "cancel_active.json")
                with open(cancel_file, "w", encoding="utf-8") as f:
                    f.write(f'{{"action": "cancel", "timestamp": {time.time()}}}')

            if container.status == "running":
                try:
                    container.exec_run("touch /workspace/.agent_signals/cancel_active.json", detach=True)
                except Exception:
                    pass
        except Exception as exc:
            print(f"[AgentManager] Could not soft-stop container {container_id}: {exc}")

    def stop_project_container(self, project_id: str) -> None:
        """Soft-stop any active task for a project."""
        if self._client is None:
            return
        clean_project_id = project_id.replace("/", "_").replace("\\", "_")[:16]
        container_name = f"dsuite-agent-{clean_project_id}"
        try:
            container = self._client.containers.get(container_name)
            self.stop_runtime(container.id)
        except Exception:
            pass

    def get_port(self, container_id: str, port: int = 80) -> int | None:
        """Return host port mapped to container port."""
        if self._client is None or container_id.startswith("stub-"):
            return None
        try:
            container = self._client.containers.get(container_id)
            container.reload()
            ports = container.attrs.get("NetworkSettings", {}).get("Ports", {})
            mapping = ports.get(f"{port}/tcp")
            if mapping and len(mapping) > 0:
                host_port = mapping[0].get("HostPort")
                if host_port:
                    return int(host_port)
        except Exception:
            pass
        return None

    def get_status(self, container_id: str) -> ContainerStatus:
        """Return current status of a container."""
        if self._client is None or container_id.startswith("stub-"):
            return ContainerStatus.running
        try:
            container = self._client.containers.get(container_id)
            status_map = {
                "running": ContainerStatus.running,
                "exited": ContainerStatus.stopped,
                "created": ContainerStatus.running,
            }
            return status_map.get(container.status, ContainerStatus.error)
        except Exception:
            return ContainerStatus.not_found

    def get_logs(self, container_id: str, tail: int = 200) -> str:
        """Return container stdout/stderr logs."""
        if self._client is None or container_id.startswith("stub-"):
            return f"[Dev Mode] Stub logs for container {container_id}"
        try:
            container = self._client.containers.get(container_id)
            return container.logs(tail=tail).decode("utf-8", errors="replace")
        except Exception as exc:
            return f"Could not retrieve logs: {exc}"

    def get_running_containers_count(self) -> int:
        """Count running agent containers."""
        if self._client is None:
            return 0
        try:
            running = self._client.containers.list(filters={"name": "dsuite-agent-"})
            return len(running)
        except Exception:
            return 0

    def _build_env(self, config: AgentContainerConfig) -> dict[str, str]:
        settings = self._settings
        env: dict[str, str] = {
            "SESSION_ID": config.session_id,
            "TASK_ID": config.task_id,
            "TASK_TYPE": config.task_type,
            "PROMPT": config.prompt,
            "WORKSPACE_PATH": "/workspace",
            "PROJECT_ID": config.project_id,
            "TENANT_ID": config.tenant_id,
            "CALLBACK_URL": config.callback_url,
            "CALLBACK_SECRET": config.callback_secret,
            "MODEL_NAME": config.model or settings.ai_model,
            "MODEL_PROVIDER": "nvidia" if "nvidia" in (settings.ai_api_url or "") else "custom",
            "AI_API_URL": settings.ai_api_url or "",
            "AI_API_KEY": settings.ai_api_key or "",
            "AI_MODEL": config.model or settings.ai_model or "",
            "TOOL_USE_ENABLED": "true",
            "ALLOWED_TOOLS": ",".join(config.tools or ["filesystem", "git", "terminal", "build_tool"]),
            "MAX_TOOL_CALLS": "50",
            "WEB_SEARCH_ENABLED": "true",
            "GIT_REPO_URL": config.repo_url or "",
            "GIT_TOKEN": config.git_token or "",
            "GIT_BRANCH": config.git_branch or "main",
            "IDLE_TIMEOUT_SECONDS": "900",
        }
        return env
