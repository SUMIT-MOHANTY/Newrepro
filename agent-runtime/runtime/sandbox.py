"""Sandbox — workspace path enforcement.

Architecture §7.2 sandbox.py / §8.2:
Every filesystem tool call passes through here before touching the disk.
Path traversal attempts (../../etc/passwd etc.) are caught and blocked.
The workspace root is fixed at container startup from the WORKSPACE_PATH
environment variable — it never changes per-request.
"""
from __future__ import annotations

import os
from pathlib import Path


class SandboxViolationError(Exception):
    """Raised when a path operation would escape the workspace."""


class Sandbox:
    """Enforces workspace confinement for all filesystem operations."""

    def __init__(self, workspace_path: str) -> None:
        self._workspace_root = Path(workspace_path).resolve()

    @property
    def workspace_root(self) -> Path:
        return self._workspace_root

    def safe_resolve(self, path: str | Path) -> Path:
        """Resolve path and verify it is inside the workspace.

        Raises SandboxViolationError if the resolved path escapes.
        Returns the resolved absolute Path on success.
        """
        # Handle both absolute and relative paths
        p = Path(path)
        if p.is_absolute():
            resolved = p.resolve()
        else:
            resolved = (self._workspace_root / p).resolve()

        try:
            resolved.relative_to(self._workspace_root)
        except ValueError:
            raise SandboxViolationError(
                f"Path '{path}' resolves to '{resolved}' which is outside "
                f"the workspace '{self._workspace_root}'. Access denied."
            )
        return resolved

    def is_within_workspace(self, path: str) -> bool:
        """Return True if path is within the workspace, False otherwise."""
        try:
            self.safe_resolve(path)
            return True
        except SandboxViolationError:
            return False

    def workspace_relative(self, abs_path: str | Path) -> str:
        """Return the workspace-relative form of an absolute path."""
        return str(Path(abs_path).relative_to(self._workspace_root))
