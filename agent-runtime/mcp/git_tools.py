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

    def _resolve_agent_identity(self, agent_name: str | None = None) -> tuple[str, str]:
        """Resolve standard Dsuite agent Git committer name and email.

        Format: 'Dsuite-<Agent Name>' and '<clean_handle>@dsuite.internal'
        """
        raw = agent_name or os.environ.get("AGENT_NAME") or os.environ.get("AGENT_ROLE") or os.environ.get("AGENT_ID") or "Agent"
        clean = str(raw).strip()

        # Remove legacy vibecoding naming if present
        if "vibecoding" in clean.lower():
            clean = "Agent"

        # Normalize prefix if already starting with Dsuite
        clean_lower = clean.lower()
        if clean_lower.startswith("dsuite-"):
            clean = clean[7:].strip()
        elif clean_lower.startswith("dsuite_"):
            clean = clean[7:].strip()
        elif clean_lower.startswith("dsuite"):
            clean = clean[6:].strip().lstrip("-_ ")

        final_agent_name = clean.replace(" ", "") if clean else "Agent"
        author_name = f"Dsuite-{final_agent_name}"
        email_handle = author_name.lower().replace("-", "_")
        author_email = f"{email_handle}@dsuite.internal"
        return author_name, author_email

    def _ensure_ignore_rules(self, target: Path | None = None) -> None:
        """Ensure internal agent communication and sync files are strictly ignored by Git."""
        ws = target or self._workspace
        patterns = [
            ".agent/",
            ".agent",
            ".agent_history/",
            ".agent_history",
            ".agent_ipc/",
            ".agent_ipc",
            ".agent_signals/",
            ".agent_signals",
            ".agent_initialized",
            ".package_deps_hash",
        ]

        # 1. Ensure .git/info/exclude exists and contains patterns (repo-local exclude)
        git_dir = ws / ".git"
        if git_dir.exists():
            exclude_file = git_dir / "info" / "exclude"
            try:
                exclude_file.parent.mkdir(parents=True, exist_ok=True)
                existing_exclude = exclude_file.read_text(encoding="utf-8", errors="replace") if exclude_file.exists() else ""
                needed = [p for p in patterns if p not in existing_exclude]
                if needed:
                    with open(exclude_file, "a", encoding="utf-8") as f:
                        if existing_exclude and not existing_exclude.endswith("\n"):
                            f.write("\n")
                        f.write("# Dsuite internal agent communication & synchronization\n")
                        for p in needed:
                            f.write(f"{p}\n")
            except Exception:
                pass

        # 2. Ensure workspace .gitignore exists and contains patterns
        gitignore_file = ws / ".gitignore"
        try:
            existing_gi = gitignore_file.read_text(encoding="utf-8", errors="replace") if gitignore_file.exists() else ""
            needed = [p for p in patterns if p not in existing_gi]
            if needed:
                with open(gitignore_file, "a", encoding="utf-8") as f:
                    if existing_gi and not existing_gi.endswith("\n"):
                        f.write("\n")
                    f.write("\n# Dsuite internal agent communication & synchronization\n")
                    for p in needed:
                        f.write(f"{p}\n")
        except Exception:
            pass

    def _untrack_internal_agent_dirs(self, target: Path | None = None) -> None:
        """Untrack internal agent directories if they were staged or previously tracked in Git index."""
        ws = target or self._workspace
        if not (ws / ".git").exists():
            return
        targets = [
            ".agent",
            ".agent_history",
            ".agent_ipc",
            ".agent_signals",
            ".agent_initialized",
            ".package_deps_hash",
        ]
        try:
            subprocess.run(
                ["git", "rm", "-r", "--cached", "--ignore-unmatch", *targets],
                cwd=str(ws),
                capture_output=True,
                text=True,
                timeout=10,
            )
        except Exception:
            pass

        try:
            subprocess.run(
                ["git", "reset", "-q", "HEAD", "--", *targets],
                cwd=str(ws),
                capture_output=True,
                text=True,
                timeout=10,
            )
        except Exception:
            pass

    def clone(self, repo_url: str, branch: str = "main", auth_token: str | None = None, workspace_path: str | None = None) -> ToolResult:
        """Clone a remote repository into the workspace or pull latest."""
        target = Path(workspace_path) if workspace_path else self._workspace
        target.mkdir(parents=True, exist_ok=True)
        self._ensure_ignore_rules(target)

        # Inject auth token into repo URL if provided and not already present
        clean_url = repo_url.strip()
        if auth_token and "@" not in clean_url:
            if clean_url.startswith("https://"):
                clean_url = clean_url.replace("https://", f"https://x-access-token:{auth_token}@")
            elif clean_url.startswith("http://"):
                clean_url = clean_url.replace("http://", f"http://x-access-token:{auth_token}@")

        author_name, author_email = self._resolve_agent_identity()
        try:
            if (target / ".git").exists():
                self._run(["git", "fetch", "--all"], cwd=str(target))
                self._run(["git", "checkout", branch], cwd=str(target))
                self._run(["git", "pull", "origin", branch], cwd=str(target))
                self._run(["git", "config", "user.name", author_name], cwd=str(target))
                self._run(["git", "config", "user.email", author_email], cwd=str(target))
                return ToolResult(success=True, data={"message": f"Updated existing repo on branch {branch}", "path": str(target)})
            else:
                # Use robust init + remote add + fetch so it succeeds even when workspace has initial files (.agent, .gitignore)
                self._run(["git", "init"], cwd=str(target))
                self._ensure_ignore_rules(target)
                self._run(["git", "config", "user.name", author_name], cwd=str(target))
                self._run(["git", "config", "user.email", author_email], cwd=str(target))
                try:
                    self._run(["git", "remote", "remove", "origin"], cwd=str(target))
                except Exception:
                    pass
                self._run(["git", "remote", "add", "origin", clean_url], cwd=str(target))
                fetch_res = subprocess.run(
                    ["git", "fetch", "--depth", "1", "origin", branch],
                    cwd=str(target),
                    capture_output=True,
                    text=True,
                )
                if fetch_res.returncode == 0:
                    self._run(["git", "checkout", "-f", "-B", branch, f"origin/{branch}"], cwd=str(target))
                    return ToolResult(success=True, data={"message": f"Successfully cloned {repo_url} branch {branch}", "path": str(target)})
                else:
                    self._run(["git", "checkout", "-B", branch], cwd=str(target))
                    self._run(["git", "commit", "--allow-empty", f"--author={author_name} <{author_email}>", "-m", "Initialize project repository"], cwd=str(target))
                    return ToolResult(success=True, data={"message": f"Initialized repo for empty remote {repo_url}", "path": str(target)})
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

        self._ensure_ignore_rules(target)
        self._untrack_internal_agent_dirs(target)
        author_name, author_email = self._resolve_agent_identity()
        base_branch = os.environ.get("GIT_BRANCH", "main")
        if (target / ".git").exists():
            # If repo exists but has no commits (unborn HEAD), seed a root commit
            try:
                self._run(["git", "config", "user.name", author_name], cwd=str(target))
                self._run(["git", "config", "user.email", author_email], cwd=str(target))
                check_head = subprocess.run(
                    ["git", "rev-parse", "--verify", "HEAD"],
                    cwd=str(target),
                    capture_output=True,
                    text=True,
                )
                if check_head.returncode != 0:
                    self._run(["git", "checkout", "-B", base_branch], cwd=str(target))
                    self._run(["git", "commit", "--allow-empty", f"--author={author_name} <{author_email}>", "-m", "Initialize project repository"], cwd=str(target))
            except Exception:
                pass
            return ToolResult(success=True, data={"message": "Already initialized"})
        try:
            self._run(["git", "init"], cwd=str(target))
            self._run(["git", "checkout", "-B", base_branch], cwd=str(target))
            self._run(["git", "config", "user.name", author_name], cwd=str(target))
            self._run(["git", "config", "user.email", author_email], cwd=str(target))
            self._run(["git", "commit", "--allow-empty", f"--author={author_name} <{author_email}>", "-m", "Initialize project repository"], cwd=str(target))
            return ToolResult(success=True, data={"path": str(target), "branch": base_branch})
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
            self._ensure_ignore_rules()
            self._untrack_internal_agent_dirs()
            self._run(["git", "add", "-A"], cwd=str(self._workspace))
            self._untrack_internal_agent_dirs()
            return ToolResult(success=True)
        except Exception as exc:
            return ToolResult(success=False, error=str(exc))

    def commit(self, message: str, agent_name: str | None = None) -> ToolResult:
        """Commit staged changes. Returns the commit hash."""
        try:
            self._ensure_ignore_rules()
            self._untrack_internal_agent_dirs()
            self._run(["git", "add", "-A"], cwd=str(self._workspace))
            self._untrack_internal_agent_dirs()
            author_name, author_email = self._resolve_agent_identity(agent_name)
            self._run(["git", "config", "user.name", author_name], cwd=str(self._workspace))
            self._run(["git", "config", "user.email", author_email], cwd=str(self._workspace))
            out = self._run(
                ["git", "commit", f"--author={author_name} <{author_email}>", "-m", message, "--allow-empty"],
                cwd=str(self._workspace),
            )
            hash_out = self._run(["git", "rev-parse", "HEAD"], cwd=str(self._workspace))
            return ToolResult(success=True, data={"commit_hash": hash_out.strip(), "message": message, "author": author_name})
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

    def commit_checkpoint(self, task_id: str, summary: str = "", files_changed: list[str] | None = None, agent_name: str | None = None) -> ToolResult:
        """Commit all workspace changes as a named checkpoint after every AI coding turn.

        Returns commit hash which is sent to the frontend via session events so the
        user can click "Revert to this version" at any point.
        """
        try:
            self._ensure_ignore_rules()
            self._untrack_internal_agent_dirs()
            self._run(["git", "add", "-A"], cwd=str(self._workspace))
            self._untrack_internal_agent_dirs()

            author_name, author_email = self._resolve_agent_identity(agent_name)
            self._run(["git", "config", "user.name", author_name], cwd=str(self._workspace))
            self._run(["git", "config", "user.email", author_email], cwd=str(self._workspace))

            # Check if there's anything staged
            status_out = self._run(["git", "status", "--porcelain"], cwd=str(self._workspace))
            internal_prefixes = (".agent", ".agent_history", ".agent_ipc", ".agent_signals", ".agent_initialized", ".package_deps_hash")
            valid_changes = [
                line.strip() for line in status_out.splitlines()
                if line.strip() and not any(p in line for p in internal_prefixes)
            ]
            if not valid_changes:
                # Nothing changed — grab HEAD hash and return
                head = self._run(["git", "rev-parse", "HEAD"], cwd=str(self._workspace)).strip()
                return ToolResult(success=True, data={
                    "commit_hash": head,
                    "changed_files": [],
                    "status": "no_changes",
                })

            raw_changed = files_changed or valid_changes
            changed = [
                f for f in raw_changed
                if not any(p in str(f) for p in internal_prefixes)
            ]

            msg = f"[{author_name} Checkpoint] task:{task_id}"
            if summary:
                msg += f" — {summary[:120]}"
            self._run(
                ["git", "commit", f"--author={author_name} <{author_email}>", "-m", msg],
                cwd=str(self._workspace),
            )
            commit_hash = self._run(["git", "rev-parse", "HEAD"], cwd=str(self._workspace)).strip()
            return ToolResult(success=True, data={
                "commit_hash": commit_hash,
                "changed_files": changed,
                "status": "committed",
                "message": msg,
                "author": author_name,
            })
        except Exception as exc:
            return ToolResult(success=False, error=str(exc))

    def current_branch(self) -> ToolResult:
        """Get the current active branch name."""
        try:
            out = self._run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=str(self._workspace)).strip()
            return ToolResult(success=True, data={"branch": out})
        except Exception as exc:
            return ToolResult(success=False, error=str(exc))

    def checkout_branch(self, branch: str, create: bool = False, base_branch: str | None = None) -> ToolResult:
        """Checkout or create a Git branch for feature/task isolation (Brownfield & Swarm)."""
        clean_branch = branch.strip().replace(" ", "-")
        try:
            self._ensure_ignore_rules()
            self._untrack_internal_agent_dirs()
            if create:
                # Check if branch already exists
                check = subprocess.run(
                    ["git", "rev-parse", "--verify", clean_branch],
                    cwd=str(self._workspace),
                    capture_output=True,
                    text=True,
                )
                if check.returncode == 0:
                    # Branch already exists locally — checkout directly with -f
                    self._run(["git", "checkout", "-f", clean_branch], cwd=str(self._workspace))
                else:
                    cmd = ["git", "checkout", "-b", clean_branch]
                    if base_branch:
                        check_base = subprocess.run(
                            ["git", "rev-parse", "--verify", f"{base_branch}"],
                            cwd=str(self._workspace),
                            capture_output=True,
                            text=True,
                        )
                        if check_base.returncode == 0:
                            cmd.append(base_branch)
                    self._run(cmd, cwd=str(self._workspace))
            else:
                self._run(["git", "checkout", "-f", clean_branch], cwd=str(self._workspace))

            current = self.current_branch()
            return ToolResult(success=True, data={
                "branch": current.data.get("branch", clean_branch) if current.success else clean_branch,
                "message": f"Switched to branch {clean_branch}",
            })
        except Exception as exc:
            return ToolResult(success=False, error=str(exc))

    def merge_branch(self, feature_branch: str, base_branch: str = "main", no_ff: bool = True) -> ToolResult:
        """Merge feature_branch into base_branch, with automatic abort on conflict."""
        try:
            # Checkout base_branch
            checkout_res = self.checkout_branch(base_branch, create=False)
            if not checkout_res.success:
                return checkout_res
            cmd = ["git", "merge"]
            if no_ff:
                cmd.append("--no-ff")
            cmd.extend([feature_branch, "-m", f"Merge {feature_branch} into {base_branch}"])
            self._run(cmd, cwd=str(self._workspace))
            return ToolResult(success=True, data={"merged": feature_branch, "base": base_branch})
        except Exception as exc:
            # Clean up aborted merge so repo is never left in MERGE_HEAD conflict state!
            try:
                self._run(["git", "merge", "--abort"], cwd=str(self._workspace))
            except Exception:
                pass
            return ToolResult(success=False, error=str(exc))

    def create_worktree(self, branch: str, worktree_path: str, base_branch: str | None = None) -> ToolResult:
        """Create an isolated git worktree checked out to branch."""
        clean_branch = branch.strip().replace(" ", "-")
        target = Path(worktree_path)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            cmd = ["git", "worktree", "add"]
            check = subprocess.run(
                ["git", "rev-parse", "--verify", clean_branch],
                cwd=str(self._workspace),
                capture_output=True,
                text=True,
            )
            if check.returncode == 0:
                cmd.extend([str(target), clean_branch])
            else:
                cmd.extend(["-b", clean_branch, str(target)])
                if base_branch:
                    check_base = subprocess.run(
                        ["git", "rev-parse", "--verify", f"{base_branch}"],
                        cwd=str(self._workspace),
                        capture_output=True,
                        text=True,
                    )
                    if check_base.returncode == 0:
                        cmd.append(base_branch)
            self._run(cmd, cwd=str(self._workspace))
            return ToolResult(success=True, data={"worktree_path": str(target), "branch": clean_branch})
        except Exception as exc:
            return ToolResult(success=False, error=str(exc))

    def remove_worktree(self, worktree_path: str) -> ToolResult:
        """Remove a git worktree and prune worktree metadata."""
        try:
            self._run(["git", "worktree", "remove", "--force", str(worktree_path)], cwd=str(self._workspace))
            self._run(["git", "worktree", "prune"], cwd=str(self._workspace))
            return ToolResult(success=True, data={"removed": str(worktree_path)})
        except Exception as exc:
            return ToolResult(success=False, error=str(exc))

    def push(self, branch: str | None = None, remote: str = "origin", auth_token: str | None = None, repo_url: str | None = None, agent_name: str | None = None, force: bool = False) -> ToolResult:
        """Push local commits to remote repository (supports feature branches and force push)."""
        token = auth_token or os.environ.get("GIT_AUTH_TOKEN") or os.environ.get("GIT_PAT_TOKEN")
        url = repo_url or os.environ.get("GIT_REPO_URL")
        target_branch = branch
        if not target_branch:
            cur = self.current_branch()
            target_branch = cur.data.get("branch", "main") if cur.success else "main"
        
        try:
            self._ensure_ignore_rules()
            self._untrack_internal_agent_dirs()
            author_name, author_email = self._resolve_agent_identity(agent_name)
            self._run(["git", "config", "user.name", author_name], cwd=str(self._workspace))
            self._run(["git", "config", "user.email", author_email], cwd=str(self._workspace))

            # If we have a token and URL, we can set up an authenticated remote
            temp_remote = False
            if token and url:
                clean_url = url.strip()
                if "@" not in clean_url:
                    if clean_url.startswith("https://"):
                        auth_url = clean_url.replace("https://", f"https://x-access-token:{token}@")
                    elif clean_url.startswith("http://"):
                        auth_url = clean_url.replace("http://", f"http://x-access-token:{token}@")
                    else:
                        auth_url = clean_url
                        
                    try:
                        self._run(["git", "remote", "remove", "auth_origin"], cwd=str(self._workspace))
                    except Exception:
                        pass
                    self._run(["git", "remote", "add", "auth_origin", auth_url], cwd=str(self._workspace))
                    remote = "auth_origin"
                    temp_remote = True
            
            push_cmd = ["git", "push", "-u"]
            if force:
                push_cmd.append("--force")
            push_cmd.extend([remote, target_branch])
            self._run(push_cmd, cwd=str(self._workspace))
            
            if temp_remote:
                self._run(["git", "remote", "remove", "auth_origin"], cwd=str(self._workspace))
                
            return ToolResult(success=True, data={"message": f"Successfully pushed to {remote}/{target_branch}", "branch": target_branch, "author": author_name})
        except Exception as exc:
            if 'temp_remote' in locals() and temp_remote:
                try:
                    self._run(["git", "remote", "remove", "auth_origin"], cwd=str(self._workspace))
                except Exception:
                    pass
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
