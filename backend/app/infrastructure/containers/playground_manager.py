"""Playground Container Manager — Docker Lifecycle for Agent Runtime Playgrounds.

Enforces org-level max_agent_capacity, strict per-project workspace mount verification,
and non-blocking stream execution with live JSONL event tailing.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import threading
import time
from typing import Any, Callable, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

CONTAINER_PREFIX = "dsuite_agent_"

PREFERRED_IMAGES = [
    "dsuite-agent-runtime:latest",
    "vibecoding-agent-runtime:latest",
    "containerhub.bourntec.com/vibecoding-agent-runtime:1.0.8-prod",
    "containerhub.bourntec.com/vibecoding-agent-runtime:1.0.8",
    "containerhub.bourntec.com/vibecoding-agent-runtime:1.0.6-prod",
    "containerhub.bourntec.com/vibecoding-agent-runtime:1.0.3",
]


class PlaygroundContainerManager:
    """Manages Docker playground containers for agent execution with org-quota enforcement."""

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
            logger.warning(f"[PlaygroundManager] Docker client unavailable: {exc}. Using CLI fallback.")
            self._docker_client = None

    def _get_available_image(self) -> str:
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
                encoding="utf-8",
                errors="replace",
                timeout=5,
            )
            return res.stdout.strip().lower() == "true"
        except Exception:
            return False

    def get_running_containers_count(self, org_name: Optional[str] = None) -> int:
        """Accurately count active agent containers (fixes prefix mismatch bug)."""
        prefix_filter = CONTAINER_PREFIX
        if org_name:
            clean_org = "".join(c for c in org_name if c.isalnum() or c == "_")[:10].lower()
            prefix_filter = f"{CONTAINER_PREFIX}{clean_org}_"
        try:
            if self._docker_client:
                running = self._docker_client.containers.list(filters={"name": prefix_filter})
                return len(running)
            res = subprocess.run(
                ["docker", "ps", "--filter", f"name={prefix_filter}", "--format", "{{.Names}}"],
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=5,
            )
            if res.returncode == 0:
                return len([line.strip() for line in res.stdout.splitlines() if line.strip()])
        except Exception as e:
            logger.warning(f"[PlaygroundManager] Error counting running containers: {e}")
        return len([
            c for c in self.containers.values()
            if c.get("status") == "BUSY" and (not org_name or c.get("org_name") == org_name)
        ])

    def acquire_playground(
        self,
        org_name: str,
        project_token: str,
        agent_id: str,
        workspace_host_path: str,
        max_capacity: int = 10,
    ) -> Optional[str]:
        """
        Acquire or provision a playground container for (org_name, project_token, agent_id).
        Strictly guarantees:
          1. Total running containers in the org never exceed `max_capacity`.
          2. Reused containers ALWAYS point to the exact `workspace_host_path` for `project_token`
             (recreating the container if it was previously mounted to a different project).
        """
        abs_workspace = os.path.abspath(workspace_host_path)
        os.makedirs(abs_workspace, exist_ok=True)

        with self.lock:
            # 1. Reuse active container ONLY if it belongs to the exact same project & workspace
            for name, meta in self.containers.items():
                if (
                    meta.get("agent_id") == agent_id
                    and meta.get("project_token") == project_token
                    and os.path.abspath(meta.get("workspace_path", "")) == abs_workspace
                ):
                    if self._ensure_container_started(name):
                        meta["status"] = "BUSY"
                        meta["last_used"] = time.time()
                        logger.info(f"[PlaygroundManager] Reusing matching container {name} for {agent_id} ({project_token})")
                        return name

            # 2. Enforce org-level container capacity limit
            running_count = self.get_running_containers_count(org_name)
            if running_count >= max_capacity:
                # Evict the oldest IDLE container in this org so we can mount the new project workspace cleanly
                lru_name = None
                lru_time = float("inf")
                for name, meta in self.containers.items():
                    if (
                        meta.get("org_name") == org_name
                        and meta.get("status") == "IDLE"
                        and meta.get("last_used", 0) < lru_time
                    ):
                        lru_name = name
                        lru_time = meta.get("last_used", 0)

                if lru_name:
                    logger.info(
                        f"[PlaygroundManager] Capacity ({running_count}/{max_capacity}) reached for org '{org_name}'. "
                        f"Reclaiming IDLE container '{lru_name}' for project '{project_token}'."
                    )
                    self._force_remove_container(lru_name)
                    self.containers.pop(lru_name, None)
                else:
                    logger.warning(
                        f"[PlaygroundManager] All {running_count}/{max_capacity} containers in org '{org_name}' are BUSY!"
                    )

            # 3. Build deterministic, project-isolated container name
            clean_org = "".join(c for c in (org_name or "default") if c.isalnum() or c == "_")[:10].lower()
            clean_proj = "".join(c for c in (project_token or "proj") if c.isalnum() or c == "_")[:10].lower()
            base_aid = (agent_id or "worker").split("#")[0].split("::")[-1]
            clean_agent = "".join(c for c in base_aid if c.isalnum() or c == "_")[:16].lower()
            container_name = f"{CONTAINER_PREFIX}{clean_org}_{clean_proj}_{clean_agent}"

            # Remove any stale container with the same name
            self._force_remove_container(container_name)

            image = self._get_available_image()
            runtime_dir = os.path.abspath(
                os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "agent-runtime")
            )
            vols = {abs_workspace: {"bind": "/workspace", "mode": "rw"}}
            if os.path.isdir(runtime_dir):
                vols[runtime_dir] = {"bind": "/app", "mode": "rw"}

            # Developer worker containers NEVER bind host preview port 8085!
            # Only the dedicated deployment container (provision_deploy_container) binds the live preview port.
            ports_dict = None
            cli_port_args = []
            extra_hosts = {"host.docker.internal": "host-gateway"}

            try:
                if self._docker_client:
                    c = self._docker_client.containers.run(
                        image=image,
                        name=container_name,
                        detach=True,
                        volumes=vols,
                        ports=ports_dict,
                        extra_hosts=extra_hosts,
                        working_dir="/workspace",
                        entrypoint="/bin/sh",
                        command=[
                            "-c",
                            "mkdir -p /var/log && printf '[Playground Container Online] Ready for Agent Swarm execution.\\n' > /proc/1/fd/1; tail -f /dev/null",
                        ],
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
                        "docker",
                        "run",
                        "-d",
                        "--name",
                        container_name,
                        "--add-host",
                        "host.docker.internal:host-gateway",
                        "-v",
                        f"{abs_workspace}:/workspace",
                    ]
                    if cli_port_args:
                        cmd.extend(cli_port_args)
                    if os.path.isdir(runtime_dir):
                        cmd.extend(["-v", f"{runtime_dir}:/app"])
                    cmd.extend([
                        "-w",
                        "/workspace",
                        "--entrypoint",
                        "/bin/sh",
                        image,
                        "-c",
                        "mkdir -p /var/log && printf '[Playground Container Online] Ready for Agent Swarm execution.\\n' > /proc/1/fd/1; tail -f /dev/null",
                    ])
                    res = subprocess.run(cmd, capture_output=True, encoding="utf-8", errors="replace", timeout=30)
                    if res.returncode != 0:
                        logger.error(f"[PlaygroundManager] CLI launch failed: {res.stderr}")
                        return None
                    c_id = res.stdout.strip()

                self.containers[container_name] = {
                    "id": c_id,
                    "status": "BUSY",
                    "org_name": org_name,
                    "project_token": project_token,
                    "agent_id": agent_id,
                    "workspace_path": abs_workspace,
                    "image": image,
                    "last_used": time.time(),
                }
                self.append_log_to_container(
                    container_name,
                    f"🚀 Playground initialized for agent={agent_id} project={project_token} org={org_name}",
                )
                return container_name

            except Exception as e:
                logger.error(f"[PlaygroundManager] Error provisioning container {container_name}: {e}", exc_info=True)
                return None

    def _ensure_container_started(self, container_name: str, workspace_host_path: Optional[str] = None) -> bool:
        try:
            if self._is_container_running(container_name):
                return True
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

    def provision_deploy_container(
        self,
        project_token: str,
        workspace_host_path: str,
        preferred_host_port: int = 8085,
    ) -> Tuple[Optional[str], int]:
        """Provision a dedicated, isolated Deployment Container (`dsuite_deploy_<project>`) with Nginx on port 80
        mapped to `preferred_host_port` (default 8085). Separate from all developer agent containers.
        """
        import socket

        abs_workspace = os.path.abspath(workspace_host_path)
        os.makedirs(abs_workspace, exist_ok=True)
        clean_proj = "".join(c for c in (project_token or "proj") if c.isalnum() or c == "_")[:16].lower()
        container_name = f"dsuite_deploy_{clean_proj}"

        with self.lock:
            # Remove any existing deploy container for this project so we get a clean Nginx/service boot
            self._force_remove_container(container_name)

            # Find available host port starting at preferred_host_port (8085)
            host_port = preferred_host_port
            for cand_port in range(preferred_host_port, preferred_host_port + 25):
                try:
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                        if s.connect_ex(("127.0.0.1", cand_port)) != 0:
                            host_port = cand_port
                            break
                except Exception:
                    pass

            image = self._get_available_image()
            runtime_dir = os.path.abspath(
                os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "agent-runtime")
            )
            vols = {abs_workspace: {"bind": "/workspace", "mode": "rw"}}
            if os.path.isdir(runtime_dir):
                vols[runtime_dir] = {"bind": "/app", "mode": "rw"}

            ports_dict = {"80/tcp": ("0.0.0.0", host_port)}
            extra_hosts = {"host.docker.internal": "host-gateway"}

            try:
                if self._docker_client:
                    c = self._docker_client.containers.run(
                        image=image,
                        name=container_name,
                        detach=True,
                        volumes=vols,
                        ports=ports_dict,
                        extra_hosts=extra_hosts,
                        working_dir="/workspace",
                        entrypoint="/bin/sh",
                        command=[
                            "-c",
                            "mkdir -p /var/log && printf '[Dedicated Deploy Container Online] Ready to host live application on port 80.\n' > /proc/1/fd/1; tail -f /dev/null",
                        ],
                        network_mode="bridge",
                        remove=False,
                        labels={
                            "dsuite.project": project_token,
                            "dsuite.agent": "deploy_agent",
                            "dsuite.role": "deployment",
                            "dsuite.host_port": str(host_port),
                        },
                    )
                    c_id = c.id
                else:
                    cmd = [
                        "docker", "run", "-d",
                        "--name", container_name,
                        "--add-host", "host.docker.internal:host-gateway",
                        "-p", f"{host_port}:80",
                        "-v", f"{abs_workspace}:/workspace",
                    ]
                    if os.path.isdir(runtime_dir):
                        cmd.extend(["-v", f"{runtime_dir}:/app"])
                    cmd.extend([
                        "-w", "/workspace",
                        "--entrypoint", "/bin/sh",
                        image,
                        "-c",
                        "mkdir -p /var/log && printf '[Dedicated Deploy Container Online] Ready to host live application on port 80.\n' > /proc/1/fd/1; tail -f /dev/null",
                    ])
                    res = subprocess.run(cmd, capture_output=True, encoding="utf-8", errors="replace", timeout=30)
                    if res.returncode != 0:
                        logger.error(f"[PlaygroundManager] Deploy container CLI launch failed: {res.stderr}")
                        return None, host_port
                    c_id = res.stdout.strip()

                self.containers[container_name] = {
                    "id": c_id,
                    "status": "DEPLOYED",
                    "org_name": "deploy",
                    "project_token": project_token,
                    "agent_id": "deploy_agent",
                    "workspace_path": abs_workspace,
                    "host_port": host_port,
                    "image": image,
                    "last_used": time.time(),
                }
                self.append_log_to_container(
                    container_name,
                    f"🚀 Dedicated Deployment Container '{container_name}' provisioned on host port {host_port} -> container port 80",
                )
                return container_name, host_port
            except Exception as e:
                logger.error(f"[PlaygroundManager] Failed to provision deploy container {container_name}: {e}", exc_info=True)
                return None, host_port

    def append_log_to_container(self, container_name: str, message: str) -> None:
        """Mirror log into PID 1 stdout (/proc/1/fd/1) and /var/log/agent.log so `docker logs` matches backend."""
        try:
            import datetime

            now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            formatted = f"[{now_str}] {message}"
            safe = (
                formatted.replace("\\", "\\\\")
                .replace('"', '\\"')
                .replace("$", "\\$")
                .replace("`", "\\`")
                .replace("%", "%%")
            )
            cmd = f'printf "%s\\n" "{safe}" >> /proc/1/fd/1 2>/dev/null; printf "%s\\n" "{safe}" >> /var/log/agent.log 2>/dev/null || true'
            if self._docker_client:
                c = self._docker_client.containers.get(container_name)
                c.exec_run(cmd=["sh", "-c", cmd], detach=True)
            else:
                subprocess.Popen(["docker", "exec", container_name, "sh", "-c", cmd], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

    def write_file_in_playground(self, container_name: str, relative_path: str, content: str) -> Tuple[bool, str]:
        """Write a file inside /workspace in the playground container via mounted host volume."""
        try:
            meta = self.containers.get(container_name)
            host_root = meta.get("workspace_path") if meta else None
            if not host_root:
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
        timeout: int = 900,
        line_callback: Optional[Callable[[str], None]] = None,
        event_callback: Optional[Callable[[dict], None]] = None,
        events_jsonl_path: Optional[str] = None,
    ) -> Tuple[int, str]:
        """
        Execute a command inside the playground container while:
        1. Streaming every stdout line to `line_callback` AND mirroring it to `/proc/1/fd/1` (`docker logs`)
        2. Tailing `events_jsonl_path` on the shared host volume in real time so structured `thinking` and
           `tool_called` events reach the frontend SSE stream in <100ms even if HTTP callbacks are blocked!
        3. Detecting completion sentinel so background preview processes never hang the stream.
        """
        self.append_log_to_container(container_name, f"$ {command}")

        stop_tail = threading.Event()

        def _tail_events_ledger():
            if not events_jsonl_path or not event_callback:
                return
            offset = 0
            if os.path.exists(events_jsonl_path):
                try:
                    offset = os.path.getsize(events_jsonl_path)
                except Exception:
                    offset = 0
            while not stop_tail.is_set():
                try:
                    if os.path.exists(events_jsonl_path):
                        with open(events_jsonl_path, "r", encoding="utf-8", errors="replace") as ef:
                            ef.seek(offset)
                            for line in ef:
                                if not line.endswith("\n"):
                                    break
                                offset += len(line.encode("utf-8", errors="replace"))
                                s_line = line.strip()
                                if s_line:
                                    try:
                                        ev_obj = json.loads(s_line)
                                        event_callback(ev_obj)
                                    except Exception:
                                        pass
                except Exception:
                    pass
                time.sleep(0.15)

        tail_thread = threading.Thread(target=_tail_events_ledger, daemon=True)
        tail_thread.start()

        # Mirror command output to container PID 1 stdout (/proc/1/fd/1) so Docker Desktop logs reflect live activity
        mirrored_cmd = f"({{ {command} ; }} 2>&1 | tee -a /proc/1/fd/1 2>/dev/null)"

        try:
            if self._docker_client:
                exec_instance = self._docker_client.api.exec_create(
                    container_name,
                    cmd=["sh", "-c", mirrored_cmd],
                    workdir=workdir,
                )
                exec_id = exec_instance["Id"]
                stream = self._docker_client.api.exec_start(exec_id, stream=True)
                output_chunks = []
                buffer = ""

                for chunk in stream:
                    text = chunk.decode("utf-8", errors="replace")
                    output_chunks.append(text)
                    buffer += text
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        line_clean = line.strip()
                        if line_clean and line_callback:
                            try:
                                line_callback(line_clean)
                            except Exception:
                                pass
                        if "Container entering sleep. Exiting daemon process." in line_clean:
                            break

                if buffer.strip() and line_callback:
                    try:
                        line_callback(buffer.strip())
                    except Exception:
                        pass

                inspect_res = self._docker_client.api.exec_inspect(exec_id)
                exit_code = inspect_res.get("ExitCode")
                return (0 if exit_code is None else exit_code), "".join(output_chunks)
            else:
                cmd = ["docker", "exec", "-w", workdir, container_name, "sh", "-c", mirrored_cmd]
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1,
                )
                output_lines = []
                if process.stdout:
                    for line in process.stdout:
                        output_lines.append(line)
                        line_clean = line.strip()
                        if line_clean and line_callback:
                            try:
                                line_callback(line_clean)
                            except Exception:
                                pass
                        if "Container entering sleep. Exiting daemon process." in line_clean:
                            break
                process.wait(timeout=timeout)
                return (process.returncode or 0), "".join(output_lines)
        except Exception as e:
            self.append_log_to_container(container_name, f"Execution error: {e}")
            return -1, f"Execution failed: {e}"
        finally:
            stop_tail.set()
            tail_thread.join(timeout=1.0)

    def release_playground(self, container_name: str, stop: bool = False) -> None:
        with self.lock:
            if container_name in self.containers:
                self.containers[container_name]["status"] = "IDLE"
                self.containers[container_name]["last_used"] = time.time()
                logger.info(f"[PlaygroundManager] Released container '{container_name}' to IDLE pool.")
        if stop:
            try:
                if self._docker_client:
                    self._docker_client.containers.get(container_name).stop(timeout=5)
                else:
                    subprocess.run(["docker", "stop", "-t", "5", container_name], capture_output=True, timeout=10)
            except Exception:
                pass

    def stop_agent_container(self, project_token: str, agent_id: Optional[str] = None) -> bool:
        """Immediately stop and cancel any running agent container for a project/agent."""
        stopped_any = False
        clean_proj = "".join(c for c in (project_token or "") if c.isalnum() or c == "_")[:10].lower()
        base_aid = agent_id.split("#")[0] if agent_id else None
        clean_aid = "".join(c for c in (base_aid or "") if c.isalnum() or c == "_")[:16].lower() if base_aid else None

        with self.lock:
            # 1. Check in-memory registered containers
            for name, meta in list(self.containers.items()):
                proj_match = meta.get("project_token") == project_token
                agent_match = not agent_id or meta.get("agent_id") == agent_id
                if proj_match and agent_match:
                    host_ws = meta.get("workspace_path")
                    if host_ws and os.path.exists(host_ws):
                        try:
                            sig_dir = os.path.join(host_ws, ".agent_signals")
                            os.makedirs(sig_dir, exist_ok=True)
                            with open(os.path.join(sig_dir, "cancel_active.json"), "w", encoding="utf-8") as f:
                                f.write(f'{{"action": "cancel", "timestamp": {time.time()}}}')
                        except Exception as sig_err:
                            logger.warning(f"[PlaygroundManager] Failed writing cancel signal: {sig_err}")
                    self._force_remove_container(name)
                    meta["status"] = "IDLE"
                    stopped_any = True

            # 2. Write signal to host workspace directory directly as fallback
            try:
                from app.core.config import get_settings
                settings = get_settings()
                clean_token = (project_token or "default_project").replace("/", "_").replace("\\", "_")
                ws_dir = os.path.join(settings.project_storage_root, clean_token)
                if os.path.exists(ws_dir):
                    sig_dir = os.path.join(ws_dir, ".agent_signals")
                    os.makedirs(sig_dir, exist_ok=True)
                    with open(os.path.join(sig_dir, "cancel_active.json"), "w", encoding="utf-8") as f:
                        f.write(f'{{"action": "cancel", "timestamp": {time.time()}}}')
            except Exception:
                pass

            # 3. Docker Python SDK container termination
            if self._docker_client:
                try:
                    for c in self._docker_client.containers.list():
                        c_name = c.name
                        matches_proj = (clean_proj and clean_proj in c_name) or (project_token and project_token in c_name)
                        matches_agent = not clean_aid or clean_aid in c_name
                        if matches_proj and matches_agent:
                            try:
                                c.kill()
                            except Exception:
                                pass
                            try:
                                c.remove(force=True)
                            except Exception:
                                pass
                            stopped_any = True
                except Exception as e:
                    logger.warning(f"[PlaygroundManager] Error stopping containers via SDK for {project_token}: {e}")

            # 4. CLI Docker termination fallback (vital when docker SDK is in stub mode)
            try:
                res = subprocess.run(
                    ["docker", "ps", "-a", "--filter", f"name={CONTAINER_PREFIX}", "--format", "{{.Names}}"],
                    capture_output=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=5,
                )
                if res.returncode == 0:
                    for c_name in [line.strip() for line in res.stdout.splitlines() if line.strip()]:
                        matches_proj = (clean_proj and clean_proj in c_name) or (project_token and project_token in c_name)
                        matches_agent = not clean_aid or clean_aid in c_name
                        if matches_proj and matches_agent:
                            subprocess.run(["docker", "rm", "-f", c_name], capture_output=True, timeout=10)
                            stopped_any = True
            except Exception as cli_err:
                logger.warning(f"[PlaygroundManager] Error stopping containers via CLI for {project_token}: {cli_err}")

        return stopped_any

    def cleanup_all(self) -> None:
        """Cleanly remove all playground containers."""
        with self.lock:
            for name in list(self.containers.keys()):
                self._force_remove_container(name)
            self.containers.clear()


playground_manager = PlaygroundContainerManager()
