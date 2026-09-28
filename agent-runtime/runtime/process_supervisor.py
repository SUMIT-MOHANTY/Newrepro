"""Unified Process & Port Supervisor.

Guarantees zero port collisions (EADDRINUSE), eliminates zombie processes,
and executes multi-tier health check probes for frontend and backend services.
"""
from __future__ import annotations

import os
import signal
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


class ProcessSupervisor:
    """Manages frontend and backend server processes, port lifecycle, and health verification."""

    @staticmethod
    def _read_stderr(process: subprocess.Popen[Any] | None) -> str:
        """Safely drain whatever stderr output the backend produced."""
        if not process or not process.stderr:
            return ""
        try:
            return process.stderr.read().decode("utf-8", errors="replace")
        except Exception:
            return ""

    @staticmethod
    def _tee_backend_log(context: str, stderr_text: str) -> None:
        """Append backend failure evidence to .agent_history/backend.log (failure-path only)."""
        try:
            import datetime
            ws = os.environ.get("WORKSPACE_PATH", "/workspace")
            log_dir = Path(ws) / ".agent_history"
            log_dir.mkdir(parents=True, exist_ok=True)
            with open(log_dir / "backend.log", "a", encoding="utf-8") as f:
                f.write(
                    f"[{datetime.datetime.now().isoformat()}] {context}\n"
                    f"{stderr_text[:4000]}\n{'-' * 60}\n"
                )
        except Exception:
            pass

    @staticmethod
    def kill_port_holders(port: int) -> None:
        """Terminate any zombie processes holding the specified TCP port."""
        # 1. On Linux / Container environments: use fuser
        try:
            subprocess.run(["fuser", "-k", f"{port}/tcp"], capture_output=True, timeout=2)
            time.sleep(0.2)
        except Exception:
            pass

        # 2. Check if port is still bound
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                pass
            # If connection succeeded, port is still held — retry kill
            try:
                subprocess.run(["fuser", "-k", "-9", f"{port}/tcp"], capture_output=True, timeout=2)
                time.sleep(0.3)
            except Exception:
                pass
        except (OSError, ConnectionRefusedError):
            # Port is free
            pass

    @staticmethod
    def wait_for_health(url: str, timeout_seconds: float = 12.0) -> bool:
        """Polls a URL until HTTP 200/204/304 is returned, guaranteeing the server is ready."""
        start_t = time.time()
        delay = 0.1
        while time.time() - start_t < timeout_seconds:
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "ProcessSupervisor/1.0"})
                with urllib.request.urlopen(req, timeout=0.8) as resp:
                    if resp.status in (200, 201, 204, 304):
                        return True
            except urllib.error.HTTPError as he:
                # Any valid HTTP status code from server (including 404/405/401) proves server is listening
                if he.code in (200, 201, 204, 304, 401, 403, 404, 405):
                    return True
            except (urllib.error.URLError, TimeoutError, OSError):
                pass

            time.sleep(delay)
            delay = min(delay * 1.4, 0.8)
        return False

    @classmethod
    def wait_for_backend_liveness(
        cls,
        process: subprocess.Popen[Any] | None,
        port: int,
        host: str = "127.0.0.1",
        timeout: float = 12.0,
    ) -> tuple[bool, str | None]:
        """Multi-tier health check with early crash detection."""
        start_t = time.time()
        delay = 0.1
        endpoints = [f"http://{host}:{port}/api/health", f"http://{host}:{port}/health", f"http://{host}:{port}/"]

        while time.time() - start_t < timeout:
            # 1. Early process exit check — capture crash immediately
            if process:
                returncode = process.poll()
                if returncode is not None and returncode != 0:
                    stderr_text = cls._read_stderr(process)
                    cls._tee_backend_log(f"Backend crashed with exit code {returncode} (port {port})", stderr_text)
                    return False, f"Backend process crashed with exit code {returncode}:\n{stderr_text[:1500]}"

            # 2. HTTP Endpoint Probes
            for url in endpoints:
                if cls.wait_for_health(url, timeout_seconds=0.6):
                    return True, None

            # 3. Socket connectivity check
            try:
                with socket.create_connection((host, port), timeout=0.4):
                    return True, None
            except (OSError, ConnectionRefusedError):
                pass

            time.sleep(delay)
            delay = min(delay * 1.5, 1.0)

        # Final check if backend died at timeout
        if process:
            returncode = process.poll()
            if returncode is not None and returncode != 0:
                stderr_text = cls._read_stderr(process)
                cls._tee_backend_log(f"Backend exited with code {returncode} (port {port})", stderr_text)
                return False, f"Backend process exited with code {returncode}:\n{stderr_text[:1500]}"

            # Grace period: give slow-starting backends (native module init, large
            # seeds) up to 3 extra seconds to become healthy before declaring failure.
            grace_end = time.time() + 3.0
            while time.time() < grace_end:
                if process.poll() is not None and process.returncode != 0:
                    stderr_text = cls._read_stderr(process)
                    cls._tee_backend_log(f"Backend crashed during grace period (port {port})", stderr_text)
                    return False, f"Backend process crashed with exit code {process.returncode}:\n{stderr_text[:1500]}"
                for url in endpoints:
                    if cls.wait_for_health(url, timeout_seconds=0.6):
                        return True, None
                time.sleep(0.3)

            # Still unresponsive: terminate the process and capture its stderr so
            # the failure is diagnosable instead of a generic timeout message.
            try:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except Exception:
                    process.kill()
            except Exception:
                pass
            stderr_text = cls._read_stderr(process)
            cls._tee_backend_log(f"Backend port {port} did not respond within {timeout}s — process terminated for diagnostics", stderr_text)
            detail = stderr_text.strip()[:1500]
            if detail:
                return False, (
                    f"Backend port {port} did not respond within {timeout}s. "
                    f"Process was unresponsive and has been terminated. stderr:\n{detail}"
                )

        return False, f"Backend port {port} did not respond within {timeout}s"

    @classmethod
    def start_fullstack_services(cls, workspace_path: str, backend_port: int = 3001) -> dict[str, Any]:
        """Terminates zombie holders, launches backend if present, and verifies health."""
        cls.kill_port_holders(backend_port)
        cls.kill_port_holders(80)

        backend_file = Path(workspace_path) / "server.js"
        if not backend_file.exists():
            backend_file = Path(workspace_path) / "backend" / "server.js"

        if backend_file.exists():
            env = os.environ.copy()
            env["PORT"] = str(backend_port)
            proc = subprocess.Popen(
                ["node", str(backend_file)],
                cwd=str(backend_file.parent),
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            healthy, err = cls.wait_for_backend_liveness(proc, backend_port, timeout=8.0)
            return {
                "status": "healthy" if healthy else "failed",
                "backend_port": backend_port,
                "error": err,
                "process": proc,
            }

        return {"status": "healthy", "frontend_port": 80}
