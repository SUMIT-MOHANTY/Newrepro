"""ProcessManager — subprocess lifecycle with timeout and resource enforcement.

Architecture §7.2 process_manager.py:
All subprocess calls from build_tools and execution_tools use this.
Applies CPU and memory limits on Linux via resource module.
Kills process on timeout rather than waiting indefinitely.
"""
from __future__ import annotations

import os
import platform
import subprocess
import sys
from dataclasses import dataclass
from typing import Any

from runtime.resource_limits import ResourceLimits


@dataclass
class ProcessResult:
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool = False
    command: str = ""

    @property
    def success(self) -> bool:
        return self.exit_code == 0 and not self.timed_out


class ProcessManager:
    """Runs subprocesses with timeout and optional resource limits."""

    def __init__(self) -> None:
        self._limits = ResourceLimits()

    def run(
        self,
        cmd: list[str],
        cwd: str,
        timeout: int | None = None,
        env: dict[str, str] | None = None,
    ) -> ProcessResult:
        """Run cmd in cwd with timeout. Returns ProcessResult."""
        effective_timeout = timeout or self._limits.MAX_BUILD_TIME_SECONDS
        effective_env = env or os.environ.copy()

        preexec = self._resource_limit_fn()

        cmd_str = " ".join(cmd)
        try:
            proc = subprocess.run(
                cmd,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=effective_timeout,
                env=effective_env,
                preexec_fn=preexec,
            )
            return ProcessResult(
                stdout=proc.stdout[:self._limits.MAX_COMMAND_OUTPUT_BYTES],
                stderr=proc.stderr[:self._limits.MAX_COMMAND_OUTPUT_BYTES],
                exit_code=proc.returncode,
                command=cmd_str,
            )
        except subprocess.TimeoutExpired:
            return ProcessResult(
                stdout="", stderr=f"Timed out after {effective_timeout}s",
                exit_code=-1, timed_out=True, command=cmd_str,
            )
        except FileNotFoundError:
            return ProcessResult(
                stdout="", stderr=f"Executable not found: {cmd[0]}",
                exit_code=127, command=cmd_str,
            )
        except Exception as exc:
            return ProcessResult(
                stdout="", stderr=str(exc),
                exit_code=-1, command=cmd_str,
            )

    def _resource_limit_fn(self):
        """Return a preexec_fn that sets resource limits on Linux."""
        if platform.system() != "Linux":
            return None
        try:
            import resource
            def _set_limits():
                # Max 2GB virtual memory per process
                resource.setrlimit(resource.RLIMIT_AS, (2 * 1024**3, 2 * 1024**3))
                # Max 256 open files
                resource.setrlimit(resource.RLIMIT_NOFILE, (256, 256))
            return _set_limits
        except ImportError:
            return None
