#!/usr/bin/env python3
"""
WorkspaceGit — Local Git-based backup and rollback for the workspace.

Every edit creates a snapshot commit. Every successful deployment creates a tag.
If anything fails (bad edit, broken build, deployment crash), we can instantly
revert to the last known-good state.

Usage:
    git = WorkspaceGit('/project/workspace')
    git.ensure_repo()

    # Before editing
    snapshot_id = git.snapshot_before_edit("User asked to change button color")

    # ... apply edits ...

    # If edits pass validation
    git.commit_after_edit(snapshot_id, changed_files, "Applied button color change")

    # If edits fail validation → rollback
    git.rollback_to(snapshot_id)

    # After successful deployment
    git.tag_deployment("deploy-v3", "Deployed successfully after button color change")

    # Nuclear rollback to last deployment
    git.rollback_to_last_deployment()
"""

import os
import subprocess
import time
import json
import hashlib
from pathlib import Path
from typing import Optional, List, Dict, Tuple
from datetime import datetime, timezone


class WorkspaceGit:
    """
    Git-powered backup system for the AI agent workspace.

    Commit strategy:
        - PRE_EDIT snapshots (lightweight): before any file change
        - POST_EDIT commits: after validated edits
        - DEPLOY tags: after successful deployment
        - ROLLBACK: instant revert to any prior state

    All operations are local — no remote pushes from inside the container.
    """

    # Git config
    GIT_USER_NAME = "VibeCoding Agent"
    GIT_USER_EMAIL = "agent@vibecoding.local"

    # Branch names
    MAIN_BRANCH = "main"
    EDIT_BRANCH_PREFIX = "edit/"

    # Tag prefixes
    DEPLOY_TAG_PREFIX = "deploy-v"
    SNAPSHOT_TAG_PREFIX = "pre-edit-"

    # Directories to always exclude
    GITIGNORE_CONTENT = """# VibeCoding agent managed

# General
.DS_Store
Thumbs.db
*.log
.env
.cache/
metadata.json

# VibeCoding Specific
.vibecoding/deploy_cache.json

# Node.js / Frontend
node_modules/
dist/
build/
.next/
out/
.vite/
.nuxt/

# Python
__pycache__/
*.pyc
*.pyo
*.pyd
.Python
env/
venv/
.venv/
env.bak/
venv.bak/

# .NET / C#
bin/
obj/
.vs/
*.user
*.suo
*.userosscache
*.sln.docstates

# Java
target/
*.class
.idea/
*.iml
.gradle/

# Go
*.exe
*.exe~
*.dll
*.so
*.dylib
*.test
*.out

# Rust
target/
**/*.rs.bk

# C / C++
*.o
*.obj
*.out
*.app
"""

    def __init__(self, workspace_dir: str, log_func=None):
        self.ws = Path(workspace_dir)
        self._log = log_func or (lambda msg: print(f"[WorkspaceGit] {msg}"))

    # ─────────────────────────────────────────────────────────────────────
    # INITIALIZATION
    # ─────────────────────────────────────────────────────────────────────

    def cleanup_git_lock(self):
        """Remove stale git index.lock if it exists to prevent git commands from hanging or failing."""
        lock_file = self.ws / ".git" / "index.lock"
        if lock_file.exists():
            try:
                lock_file.unlink()
                self._log("🧹 Removed stale .git/index.lock file")
            except Exception as e:
                self._log(f"⚠️ Failed to remove stale .git/index.lock: {e}")

    def ensure_repo(self) -> bool:
        """
        Initialize the workspace as a git repo if it isn't already.
        Safe to call multiple times — idempotent.
        Returns True if repo is ready.
        """
        if not self.ws.exists():
            self._log("Workspace does not exist yet — skipping git init")
            return False

        # ALWAYS ensure .gitignore exists, even if repo is already initialized.
        # This prevents massive directories like node_modules from freezing git operations.
        gitignore = self.ws / ".gitignore"
        if not gitignore.exists():
            try:
                gitignore.write_text(self.GITIGNORE_CONTENT)
                self._log("✅ Created robust .gitignore")
            except Exception as e:
                self._log(f"⚠️ Failed to write .gitignore: {e}")

        git_dir = self.ws / ".git"
        if git_dir.exists():
            self._log("Git repo already initialized")
            return True

        try:
            self._run_git("init")
            self._run_git("config", "user.name", self.GIT_USER_NAME)
            self._run_git("config", "user.email", self.GIT_USER_EMAIL)
            # Disable advice messages
            self._run_git("config", "advice.detachedHead", "false")

            # Initial commit (even if workspace is empty)
            self._run_git("add", "-A")
            self._run_git("commit", "-m", "Initial workspace snapshot",
                          "--allow-empty")

            self._log("✅ Git repo initialized with initial commit")
            return True

        except Exception as e:
            self._log(f"❌ Git init failed: {e}")
            return False

    # ─────────────────────────────────────────────────────────────────────
    # SNAPSHOT (before edits)
    # ─────────────────────────────────────────────────────────────────────

    def snapshot_before_edit(self, description: str = "") -> str:
        """
        Create a snapshot of the current workspace state BEFORE applying edits.
        This is the rollback point if edits fail.

        Returns:
            snapshot_id (str) — the commit hash to rollback to
        """
        self.cleanup_git_lock()
        try:
            # Stage everything and commit
            self._run_git("add", "-A")

            # Check if there are changes to commit
            status = self._run_git("status", "--porcelain")
            if status.strip():
                timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
                msg = f"[SNAPSHOT] Pre-edit backup {timestamp}"
                if description:
                    msg += f" | {description[:100]}"
                self._run_git("commit", "-m", msg)
            else:
                self._log("No changes to snapshot — workspace is clean")

            # Get current commit hash
            commit_hash = self._run_git("rev-parse", "HEAD").strip()

            # Create a lightweight tag for easy reference
            tag_name = f"{self.SNAPSHOT_TAG_PREFIX}{commit_hash[:8]}"
            try:
                self._run_git("tag", "-f", tag_name)
            except Exception:
                pass  # Tag might already exist

            self._log(f"📸 Snapshot created: {commit_hash[:8]} ({description[:50]})")
            return commit_hash

        except Exception as e:
            self._log(f"⚠️ Snapshot failed: {e}")
            # Return empty string — caller should still proceed
            return ""

    # ─────────────────────────────────────────────────────────────────────
    # COMMIT (after validated edits)
    # ─────────────────────────────────────────────────────────────────────

    def commit_after_edit(self, snapshot_id: str, changed_files: List[str],
                          description: str = "") -> str:
        """
        Commit the workspace after edits have been validated.

        Args:
            snapshot_id: The pre-edit snapshot (for reference in message)
            changed_files: List of files that were changed
            description: Human-readable description of changes

        Returns:
            commit_hash of the new commit
        """
        self.cleanup_git_lock()
        try:
            self._run_git("add", "-A")

            status = self._run_git("status", "--porcelain")
            if not status.strip():
                self._log("No changes to commit after edit")
                return self._run_git("rev-parse", "HEAD").strip()

            # Build descriptive commit message
            files_summary = ", ".join(changed_files[:5])
            if len(changed_files) > 5:
                files_summary += f" (+{len(changed_files) - 5} more)"

            msg_lines = [
                f"[EDIT] {description[:200]}" if description else "[EDIT] Code changes applied",
                "",
                f"Files changed ({len(changed_files)}):",
                *[f"  - {f}" for f in changed_files[:15]],
            ]
            if snapshot_id:
                msg_lines.append(f"\nRollback point: {snapshot_id[:8]}")

            commit_msg = "\n".join(msg_lines)
            self._run_git("commit", "-m", commit_msg)

            commit_hash = self._run_git("rev-parse", "HEAD").strip()
            self._log(f"✅ Edit committed: {commit_hash[:8]} ({len(changed_files)} files)")
            return commit_hash

        except Exception as e:
            self._log(f"⚠️ Commit after edit failed: {e}")
            return ""

    # ─────────────────────────────────────────────────────────────────────
    # DEPLOYMENT TAGGING
    # ─────────────────────────────────────────────────────────────────────

    def tag_deployment(self, description: str = "") -> str:
        """
        Tag the current commit as a successful deployment.
        This is the "known-good" state we can always return to.

        Returns:
            tag_name
        """
        try:
            # Find next version number
            existing_tags = self._run_git("tag", "-l", f"{self.DEPLOY_TAG_PREFIX}*")
            versions = []
            for tag in existing_tags.strip().split("\n"):
                tag = tag.strip()
                if tag.startswith(self.DEPLOY_TAG_PREFIX):
                    try:
                        ver = int(tag[len(self.DEPLOY_TAG_PREFIX):])
                        versions.append(ver)
                    except ValueError:
                        pass

            next_version = max(versions, default=0) + 1
            tag_name = f"{self.DEPLOY_TAG_PREFIX}{next_version}"

            # Create annotated tag
            tag_msg = f"Successful deployment v{next_version}"
            if description:
                tag_msg += f"\n\n{description}"
            tag_msg += f"\nTimestamp: {datetime.now(timezone.utc).isoformat()}"

            self._run_git("tag", "-a", tag_name, "-m", tag_msg)

            self._log(f"🏷️ Deployment tagged: {tag_name}")
            return tag_name

        except Exception as e:
            self._log(f"⚠️ Deployment tagging failed: {e}")
            return ""

    def get_last_deployment_tag(self) -> Optional[str]:
        """Get the most recent deployment tag."""
        try:
            tags = self._run_git("tag", "-l", f"{self.DEPLOY_TAG_PREFIX}*",
                                 "--sort=-version:refname")
            tag_list = [t.strip() for t in tags.strip().split("\n") if t.strip()]
            return tag_list[0] if tag_list else None
        except Exception:
            return None

    # ─────────────────────────────────────────────────────────────────────
    # ROLLBACK
    # ─────────────────────────────────────────────────────────────────────

    def rollback_to(self, commit_or_tag: str) -> bool:
        """
        Hard-reset the workspace to a specific commit or tag.
        This is the nuclear option — all uncommitted changes are lost.

        Args:
            commit_or_tag: Commit hash, tag name, or snapshot ID

        Returns:
            True if rollback succeeded
        """
        if not commit_or_tag:
            self._log("⚠️ No rollback target provided")
            return False

        try:
            self._run_git("reset", "--hard", commit_or_tag)
            self._run_git("clean", "-fd")  # Remove untracked files

            current = self._run_git("rev-parse", "HEAD").strip()
            self._log(f"⏪ Rolled back to {commit_or_tag[:12]} (now at {current[:8]})")
            return True

        except Exception as e:
            self._log(f"❌ Rollback failed: {e}")
            return False

    def rollback_to_last_deployment(self) -> bool:
        """Roll back to the last successfully deployed state."""
        tag = self.get_last_deployment_tag()
        if not tag:
            self._log("⚠️ No deployment tags found — cannot rollback")
            return False

        self._log(f"⏪ Rolling back to last deployment: {tag}")
        return self.rollback_to(tag)

    def rollback_last_edit(self) -> bool:
        """
        Undo the last edit by going back one commit.
        Safer than rollback_to_last_deployment — only undoes the most recent change.
        """
        try:
            self._run_git("reset", "--hard", "HEAD~1")
            current = self._run_git("rev-parse", "HEAD").strip()
            self._log(f"⏪ Rolled back last edit (now at {current[:8]})")
            return True
        except Exception as e:
            self._log(f"❌ Rollback last edit failed: {e}")
            return False

    # ─────────────────────────────────────────────────────────────────────
    # DIFF / STATUS
    # ─────────────────────────────────────────────────────────────────────

    def get_changed_files_since(self, commit_or_tag: str) -> List[str]:
        """Get list of files changed since a commit/tag."""
        try:
            output = self._run_git("diff", "--name-only", commit_or_tag, "HEAD")
            return [f.strip() for f in output.strip().split("\n") if f.strip()]
        except Exception:
            return []

    def get_diff_since(self, commit_or_tag: str, max_chars: int = 5000) -> str:
        """Get the actual diff since a commit/tag."""
        try:
            output = self._run_git("diff", commit_or_tag, "HEAD")
            return output[:max_chars]
        except Exception:
            return ""

    def get_status(self) -> Dict[str, any]:
        """Get current workspace git status."""
        try:
            status = self._run_git("status", "--porcelain")
            commit = self._run_git("rev-parse", "HEAD").strip()
            last_tag = self.get_last_deployment_tag()

            log_output = self._run_git("log", "--oneline", "-5")

            return {
                "current_commit": commit[:8],
                "last_deploy_tag": last_tag,
                "uncommitted_changes": len([l for l in status.split("\n") if l.strip()]),
                "recent_commits": log_output.strip(),
                "is_clean": not bool(status.strip()),
            }
        except Exception as e:
            return {"error": str(e)}

    def get_file_at_commit(self, filepath: str, commit: str) -> Optional[str]:
        """Retrieve file content at a specific commit (for comparison)."""
        try:
            return self._run_git("show", f"{commit}:{filepath}")
        except Exception:
            return None

    # ─────────────────────────────────────────────────────────────────────
    # HISTORY
    # ─────────────────────────────────────────────────────────────────────

    def get_deployment_history(self, limit: int = 10) -> List[Dict]:
        """Get history of deployments (tags)."""
        try:
            tags = self._run_git("tag", "-l", f"{self.DEPLOY_TAG_PREFIX}*",
                                 "--sort=-version:refname")
            tag_list = [t.strip() for t in tags.strip().split("\n") if t.strip()]

            history = []
            for tag in tag_list[:limit]:
                try:
                    info = self._run_git("tag", "-v", tag)
                    commit = self._run_git("rev-list", "-1", tag).strip()
                    history.append({
                        "tag": tag,
                        "commit": commit[:8],
                        "info": info[:500],
                    })
                except Exception:
                    history.append({"tag": tag, "commit": "unknown"})

            return history
        except Exception:
            return []

    def get_edit_log(self, limit: int = 20) -> List[Dict]:
        """Get recent edit commits."""
        try:
            output = self._run_git("log", "--oneline", f"-{limit}",
                                   "--grep=[EDIT]", "--grep=[SNAPSHOT]",
                                   "--all-match")
            commits = []
            for line in output.strip().split("\n"):
                if line.strip():
                    parts = line.strip().split(" ", 1)
                    commits.append({
                        "hash": parts[0],
                        "message": parts[1] if len(parts) > 1 else "",
                    })
            return commits
        except Exception:
            return []

    # ─────────────────────────────────────────────────────────────────────
    # STASH (for temporary saves)
    # ─────────────────────────────────────────────────────────────────────

    def stash_changes(self, message: str = "") -> bool:
        """Stash current uncommitted changes."""
        try:
            msg = message or f"Agent stash {datetime.now(timezone.utc).strftime('%H:%M:%S')}"
            self._run_git("stash", "push", "-m", msg)
            self._log(f"📦 Changes stashed: {msg}")
            return True
        except Exception as e:
            self._log(f"⚠️ Stash failed: {e}")
            return False

    def pop_stash(self) -> bool:
        """Restore stashed changes."""
        try:
            self._run_git("stash", "pop")
            self._log("📦 Stash restored")
            return True
        except Exception as e:
            self._log(f"⚠️ Stash pop failed: {e}")
            return False

    # ─────────────────────────────────────────────────────────────────────
    # INTERNAL
    # ─────────────────────────────────────────────────────────────────────

    def _run_git(self, *args, timeout: int = 30) -> str:
        """Run a git command in the workspace directory."""
        git_exe = "/usr/bin/git" if os.name != "nt" else "git"
        cmd = [git_exe] + list(args)
        try:
            result = subprocess.run(
                cmd,
                cwd=str(self.ws),
                capture_output=True,
                text=True,
                timeout=timeout,
                env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
            )

            if result.returncode != 0:
                stderr = result.stderr.strip()
                # Some git commands return non-zero for expected reasons
                if "nothing to commit" in stderr or "nothing to commit" in result.stdout:
                    return result.stdout
                raise subprocess.CalledProcessError(
                    result.returncode, cmd, result.stdout, stderr
                )

            return result.stdout

        except subprocess.TimeoutExpired:
            self._log(f"⏱️ Git command timed out: {' '.join(cmd)}")
            raise
