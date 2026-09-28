"""Execution MCP tools — run approved project commands within workspace.

Architecture §8.1 execution_tools.py:
- Command must be in ALLOWED_COMMANDS allowlist.
- No shell=True (prevents injection).
- Timeout and output size limits enforced.
- Working directory restricted to workspace.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from mcp.server import ToolResult
from runtime.sandbox import Sandbox
from runtime.resource_limits import ResourceLimits


# §8.3 allowlist — only these executables may be invoked
# NOTE: 'git' is intentionally excluded — git operations must use the
# Git MCP (built-in) for local ops and GitHub MCP for remote ops.
ALLOWED_COMMANDS: set[str] = {
    "node", "npm", "npx", "yarn",
    "python", "python3", "pip", "pip3",
    "nginx", "nginx-s",
    "sh", "bash",
    "ls", "cat", "mkdir", "pwd", "echo", "which",
}

# Patterns that are always denied regardless of allowed executable
DENIED_PATTERNS: list[str] = [
    "rm -rf /",
    "sudo",
    "chmod 777",
    "curl | sh",
    "wget | sh",
    "> /dev",
    "/etc/",
    "/proc/",
    "/sys/",
]


class ExecutionTools:
    """Run approved shell commands inside the project workspace."""

    def __init__(self, workspace_path: str) -> None:
        self._sandbox = Sandbox(workspace_path)
        self._limits = ResourceLimits()
        self._workspace = Path(workspace_path)

    def run_command(
        self,
        command: list[str],
        cwd: str | None = None,
        timeout_seconds: int | None = None,
        env_extra: dict[str, str] | None = None,
    ) -> ToolResult:
        """Execute a command in the workspace. Returns stdout/stderr/exit_code.

        The caller is responsible for ensuring the command passed the policy
        check in MCPServer._check_command_policy() before this runs.
        """
        import os
        max_timeout = timeout_seconds or self._limits.MAX_BUILD_TIME_SECONDS
        max_timeout = min(max_timeout, self._limits.MAX_BUILD_TIME_SECONDS)

        # Resolve working directory to within workspace
        work_dir = str(self._workspace)
        if cwd:
            try:
                resolved = self._sandbox.safe_resolve(cwd)
                work_dir = str(resolved)
            except Exception:
                work_dir = str(self._workspace)

        # Build environment
        base_env = os.environ.copy()
        base_env["NODE_ENV"] = base_env.get("NODE_ENV", "development")
        if env_extra:
            base_env.update(env_extra)
        # Remove secrets from child process env
        for key in ("ANTHROPIC_API_KEY", "CALLBACK_SECRET", "DATABASE_URL"):
            base_env.pop(key, None)

        try:
            result = subprocess.run(
                command,
                cwd=work_dir,
                capture_output=True,
                text=True,
                timeout=max_timeout,
                env=base_env,
            )

            stdout = result.stdout[:self._limits.MAX_COMMAND_OUTPUT_BYTES]
            stderr = result.stderr[:self._limits.MAX_COMMAND_OUTPUT_BYTES]

            success = (result.returncode == 0)
            err_msg = "" if success else (stderr.strip() or stdout.strip() or f"Command exited with code {result.returncode}")

            return ToolResult(
                success=success,
                data={
                    "stdout": stdout,
                    "stderr": stderr,
                    "exit_code": result.returncode,
                    "command": " ".join(command),
                },
                error=err_msg if not success else None,
            )
        except subprocess.TimeoutExpired:
            return ToolResult(success=False,
                              error=f"Command timed out after {max_timeout}s: {command}")
        except FileNotFoundError:
            return ToolResult(success=False,
                              error=f"Command not found: {command[0]}")
        except Exception as exc:
            return ToolResult(success=False, error=str(exc))
