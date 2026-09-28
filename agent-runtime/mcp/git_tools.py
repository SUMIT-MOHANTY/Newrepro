"""Git MCP tools — version control operations scoped to the project workspace.

Architecture §8.1 git_tools.py:
- All operations are restricted to the project workspace.
- No remote push in V1 — commits are local snapshots that the control
  plane can reference via commit hash (§10.3 project_versions.commit_reference).
"""
from __future__ import annotations

import subprocess
import os
from pathlib import Path
from typing import Any

from mcp.server import ToolResult
from runtime.sandbox import Sandbox


class GitTools:
    """Git operations for project version control."""

    def __init__(self, workspace_path: str) -> None:
        self._sandbox = Sandbox(workspace_path)
        self._workspace = Path(workspace_path)

    def clone(self, repo_url: str, branch: str = "main", auth_token: str | None = None, workspace_path: str | None = None) -> ToolResult:
        """Clone a remote repository into the workspace or pull latest."""
        target = Path(workspace_path) if workspace_path else self._workspace
        target.mkdir(parents=True, exist_ok=True)
        
        # Inject auth token into repo URL if provided and not already present
        clean_url = repo_url.strip()
        if auth_token and "@" not in clean_url:
            if clean_url.startswith("https://"):
                clean_url = clean_url.replace("https://", f"https://x-access-token:{auth_token}@")
            elif clean_url.startswith("http://"):
                clean_url = clean_url.replace("http://", f"http://x-access-token:{auth_token}@")

        try:
            if (target / ".git").exists():
                self._run(["git", "fetch", "--all"], cwd=str(target))
                self._run(["git", "checkout", branch], cwd=str(target))
                self._run(["git", "pull", "origin", branch], cwd=str(target))
                return ToolResult(success=True, data={"message": f"Updated existing repo on branch {branch}", "path": str(target)})
            else:
                cmd = ["git", "clone", "--branch", branch, "--depth", "1", clean_url, "."]
                self._run(cmd, cwd=str(target))
                self._run(["git", "config", "user.email", "agent@dsuite.internal"], cwd=str(target))
                self._run(["git", "config", "user.name", "DSuite Agent"], cwd=str(target))
                return ToolResult(success=True, data={"message": f"Successfully cloned {repo_url} branch {branch}", "path": str(target)})
        except Exception as exc:
            return ToolResult(success=False, error=str(exc))

    def init(self, workspace_path: str | None = None) -> ToolResult:
        """Initialize a git repository in the workspace."""
        target = Path(workspace_path) if workspace_path else self._workspace
        
        # Clean up stale lock files from previous crashed sessions
        lock_file = target / ".git" / "index.lock"
        if lock_file.exists():
            try:
                lock_file.unlink()
            except Exception:
                pass
        
        if (target / ".git").exists():
            return ToolResult(success=True, data={"message": "Already initialized"})
        try:
            self._run(["git", "init"], cwd=str(target))
            self._run(["git", "config", "user.email", "agent@vibecoding.internal"], cwd=str(target))
            self._run(["git", "config", "user.name", "Vibecoding Agent"], cwd=str(target))
            return ToolResult(success=True, data={"path": str(target)})
        except Exception as exc:
            return ToolResult(success=False, error=str(exc))

    def status(self) -> ToolResult:
        """Return list of changed files."""
        try:
            out = self._run(["git", "status", "--porcelain"], cwd=str(self._workspace))
            lines = [l for l in out.splitlines() if l.strip()]
            return ToolResult(success=True, data={"changes": lines, "count": len(lines)})
        except Exception as exc:
            return ToolResult(success=False, error=str(exc))

    def add_all(self) -> ToolResult:
        """Stage all changes."""
        try:
            self._run(["git", "add", "-A"], cwd=str(self._workspace))
            return ToolResult(success=True)
        except Exception as exc:
            return ToolResult(success=False, error=str(exc))

    def commit(self, message: str) -> ToolResult:
        """Commit staged changes. Returns the commit hash."""
        try:
            self._run(["git", "add", "-A"], cwd=str(self._workspace))
            out = self._run(
                ["git", "commit", "-m", message, "--allow-empty"],
                cwd=str(self._workspace),
            )
            hash_out = self._run(["git", "rev-parse", "HEAD"], cwd=str(self._workspace))
            return ToolResult(success=True, data={"commit_hash": hash_out.strip(), "message": message})
        except Exception as exc:
            return ToolResult(success=False, error=str(exc))

    def diff(self) -> ToolResult:
        """Return the current diff."""
        try:
            out = self._run(["git", "diff", "HEAD"], cwd=str(self._workspace))
            return ToolResult(success=True, data={"diff": out})
        except Exception as exc:
            return ToolResult(success=False, error=str(exc))

    def log(self, n: int = 10) -> ToolResult:
        """Return recent commit log."""
        try:
            out = self._run(
                ["git", "log", f"-{n}", "--oneline", "--no-color"],
                cwd=str(self._workspace),
            )
            entries = [{"line": l} for l in out.splitlines() if l.strip()]
            return ToolResult(success=True, data={"commits": entries})
        except Exception as exc:
            return ToolResult(success=False, error=str(exc))

    def _run(self, cmd: list[str], cwd: str) -> str:
        result = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip())
        return result.stdout

    def commit_checkpoint(self, task_id: str, summary: str = "", files_changed: list[str] | None = None) -> ToolResult:
        """Commit all workspace changes as a named checkpoint after every AI coding turn.

        Returns commit hash which is sent to the frontend via session events so the
        user can click "Revert to this version" at any point.
        """
        try:
            self._run(["git", "add", "-A"], cwd=str(self._workspace))
            # Check if there's anything staged
            status_out = self._run(["git", "status", "--porcelain"], cwd=str(self._workspace))
            if not status_out.strip():
                # Nothing changed — grab HEAD hash and return
                head = self._run(["git", "rev-parse", "HEAD"], cwd=str(self._workspace)).strip()
                return ToolResult(success=True, data={
                    "commit_hash": head,
                    "changed_files": [],
                    "status": "no_changes",
                })

            changed = files_changed or [line.strip() for line in status_out.splitlines() if line.strip()]
            msg = f"[Vibecoding Checkpoint] task:{task_id}"
            if summary:
                msg += f" — {summary[:120]}"
            self._run(["git", "commit", "-m", msg], cwd=str(self._workspace))
            commit_hash = self._run(["git", "rev-parse", "HEAD"], cwd=str(self._workspace)).strip()
            return ToolResult(success=True, data={
                "commit_hash": commit_hash,
                "changed_files": changed,
                "status": "committed",
                "message": msg,
            })
        except Exception as exc:
            return ToolResult(success=False, error=str(exc))

    def revert_checkpoint(self, commit_hash: str) -> ToolResult:
        """Hard-reset the workspace to the given commit hash.

        Used when the user clicks "Revert changes" in the UI.
        After reverting, the caller is responsible for rebuilding and reloading the preview.
        """
        try:
            # Safety: ensure commit_hash is a valid hex string (40 chars)
            clean_hash = commit_hash.strip()
            if not all(c in "0123456789abcdefABCDEF" for c in clean_hash) or len(clean_hash) < 7:
                return ToolResult(success=False, error=f"Invalid commit hash: '{clean_hash}'")

            self._run(["git", "reset", "--hard", clean_hash], cwd=str(self._workspace))
            self._run(["git", "clean", "-fd"], cwd=str(self._workspace))
            return ToolResult(success=True, data={
                "reverted_to": clean_hash,
                "status": "reverted",
            })
        except Exception as exc:
            return ToolResult(success=False, error=str(exc))
