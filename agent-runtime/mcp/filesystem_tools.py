"""Filesystem MCP tools — list/read/write/create/delete within workspace.

Architecture §8.1:
- All paths are validated against the workspace root (sandbox.py).
- Platform source, host filesystem, and other tenants' workspaces are
  unreachable from here.
- File size limits are enforced on reads and writes.
"""
from __future__ import annotations

import os
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mcp.server import ToolResult
from runtime.sandbox import Sandbox
from runtime.resource_limits import ResourceLimits


_FORBIDDEN_DIR_NAMES = {
    "node_modules",
    ".git",
    ".agent_history",
    "dist",
    "build",
    ".next",
    "__pycache__",
    "vibecoding",
    "agent-runtime",
    "scratch",
}

_FORBIDDEN_FILE_NAMES = {
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "bun.lockb",
}


def _check_forbidden_access(path_str: str) -> tuple[bool, str]:
    """Check if a path accesses forbidden dependency, lockfile, or build artifacts."""
    norm = str(path_str).replace("\\", "/").strip("/").lower()
    parts = norm.split("/")
    for p in parts:
        if p in _FORBIDDEN_DIR_NAMES:
            return True, f"Access denied: '{path_str}' is inside protected directory '{p}'."
    if parts and parts[-1] in _FORBIDDEN_FILE_NAMES:
        return True, f"Access denied: '{path_str}' is a protected dependency lockfile. To inspect dependencies, read 'package.json'."
    return False, ""


class FilesystemTools:
    """Safe filesystem operations scoped to the project workspace."""

    def __init__(self, workspace_path: str) -> None:
        self._sandbox = Sandbox(workspace_path)
        self._limits = ResourceLimits()

    def list_directory(self, path: str) -> ToolResult:
        """List files and directories under path.

        §8.1: list/read within allowed workspace paths.
        """
        is_forbidden, reason = _check_forbidden_access(path)
        if is_forbidden:
            return ToolResult(success=False, error=reason)

        safe = self._sandbox.safe_resolve(path)
        if not safe.exists():
            return ToolResult(success=True, data=[])  # empty, not an error
        if not safe.is_dir():
            return ToolResult(success=False, error=f"Not a directory: {path}")

        entries: list[dict] = []
        count = 0
        for item in sorted(safe.iterdir()):
            if item.name in _FORBIDDEN_DIR_NAMES or item.name in _FORBIDDEN_FILE_NAMES:
                continue
            if count >= self._limits.MAX_FILES_IN_LISTING:
                break
            rel = str(item.relative_to(self._sandbox.workspace_root))
            entries.append({
                "name": item.name,
                "path": rel,
                "type": "directory" if item.is_dir() else "file",
                "size": item.stat().st_size if item.is_file() else None,
            })
            count += 1
        return ToolResult(success=True, data=entries)

    def read_file(
        self,
        path: str,
        start_line: int | None = None,
        end_line: int | None = None,
    ) -> ToolResult:
        """Read the content of a file within the workspace, optionally sliced by line range."""
        is_forbidden, reason = _check_forbidden_access(path)
        if is_forbidden:
            return ToolResult(success=False, error=reason)

        safe = self._sandbox.safe_resolve(path)
        if not safe.exists():
            return ToolResult(success=False, error=f"File not found: {path}")
        if safe.is_dir():
            return ToolResult(
                success=False,
                error=f"'{path}' is a directory, not a file. Call list_directory('{path}') to inspect files inside it."
            )
        if not safe.is_file():
            return ToolResult(success=False, error=f"Not a regular file: {path}")

        size = safe.stat().st_size
        if size > self._limits.MAX_FILE_SIZE_BYTES:
            return ToolResult(success=False,
                              error=f"File too large to read: {size} bytes (limit: {self._limits.MAX_FILE_SIZE_BYTES})")
        try:
            content = safe.read_text(encoding="utf-8", errors="replace")
            lines = content.splitlines()
            total_lines = len(lines)
            rel = str(safe.relative_to(self._sandbox.workspace_root)) if str(safe).startswith(str(self._sandbox.workspace_root)) else path

            if start_line is not None or end_line is not None:
                s = max(1, start_line) if start_line is not None else 1
                e = min(total_lines, end_line) if end_line is not None else total_lines
                # Ensure generous reading window: minimum 50 lines of context
                if (e - s + 1) < 50 and total_lines > (e - s + 1):
                    target_len = min(50, total_lines)
                    needed = target_len - (e - s + 1)
                    expand_before = needed // 2
                    expand_after = needed - expand_before
                    s = max(1, s - expand_before)
                    e = min(total_lines, e + expand_after)
                    # If clamped at either boundary, expand into the remaining available range
                    if (e - s + 1) < target_len:
                        if s == 1:
                            e = min(total_lines, s + target_len - 1)
                        elif e == total_lines:
                            s = max(1, e - target_len + 1)

                s_idx = max(0, s - 1)
                e_idx = max(s_idx, e)
                selected = lines[s_idx:e_idx]
                numbered = "\n".join(f"{s_idx + i + 1}: {line}" for i, line in enumerate(selected))
                return ToolResult(
                    success=True,
                    data=f"[{rel}] Lines {s}-{e} of {total_lines}:\n\n{numbered}"
                )

            # Full file read: include line numbers for files up to 600 lines for precision editing
            if total_lines <= 600:
                numbered = "\n".join(f"{i + 1}: {line}" for i, line in enumerate(lines))
                return ToolResult(
                    success=True,
                    data=f"[{rel}] Total {total_lines} lines:\n\n{numbered}"
                )
            return ToolResult(success=True, data=content)
        except OSError as exc:
            return ToolResult(success=False, error=str(exc))

    def write_file(self, path: str, content: str) -> ToolResult:
        """Write content to a file, creating parent directories as needed."""
        is_forbidden, reason = _check_forbidden_access(path)
        if is_forbidden:
            return ToolResult(success=False, error=reason)

        safe = self._sandbox.safe_resolve(path)
        if len(content.encode("utf-8")) > self._limits.MAX_FILE_SIZE_BYTES:
            return ToolResult(success=False,
                              error=f"Content too large (limit: {self._limits.MAX_FILE_SIZE_BYTES} bytes)")
        try:
            safe.parent.mkdir(parents=True, exist_ok=True)
            safe.write_text(content, encoding="utf-8")
            return ToolResult(success=True, data={"path": str(safe), "size": len(content)})
        except OSError as exc:
            return ToolResult(success=False, error=str(exc))

    def create_directory(self, path: str) -> ToolResult:
        """Create a directory (and any missing parents) within the workspace."""
        is_forbidden, reason = _check_forbidden_access(path)
        if is_forbidden:
            return ToolResult(success=False, error=reason)

        safe = self._sandbox.safe_resolve(path)
        try:
            safe.mkdir(parents=True, exist_ok=True)
            return ToolResult(success=True, data={"path": str(safe)})
        except OSError as exc:
            return ToolResult(success=False, error=str(exc))

    def delete_file(self, path: str) -> ToolResult:
        """Delete a file within the workspace. Does not delete directories."""
        is_forbidden, reason = _check_forbidden_access(path)
        if is_forbidden:
            return ToolResult(success=False, error=reason)

        safe = self._sandbox.safe_resolve(path)
        if not safe.exists():
            return ToolResult(success=False, error=f"File not found: {path}")
        if safe.is_dir():
            return ToolResult(success=False,
                              error=f"Cannot delete directory with delete_file. Path: {path}")
        try:
            safe.unlink()
            return ToolResult(success=True)
        except OSError as exc:
            return ToolResult(success=False, error=str(exc))

    def file_exists(self, path: str) -> ToolResult:
        """Check whether a path exists within the workspace."""
        try:
            safe = self._sandbox.safe_resolve(path)
            return ToolResult(success=True, data={
                "exists": safe.exists(),
                "is_file": safe.is_file(),
                "is_directory": safe.is_dir(),
            })
        except Exception as exc:
            return ToolResult(success=False, error=str(exc))

    def get_file_stats(self, path: str) -> ToolResult:
        """Return metadata about a file."""
        safe = self._sandbox.safe_resolve(path)
        if not safe.exists():
            return ToolResult(success=False, error=f"Not found: {path}")
        s = safe.stat()
        return ToolResult(success=True, data={
            "size_bytes": s.st_size,
            "modified_at": datetime.fromtimestamp(s.st_mtime, tz=timezone.utc).isoformat(),
            "is_file": safe.is_file(),
            "is_directory": safe.is_dir(),
        })
