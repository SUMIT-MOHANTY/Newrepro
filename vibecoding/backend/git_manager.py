import os
import subprocess
from pathlib import Path
from typing import List, Dict, Optional, Any
import logging
import shutil
import re

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class GitManager:
    def __init__(self, artifacts_dir: str = "project_artifacts"):
        self.artifacts_dir = Path(artifacts_dir)

    def _get_project_dir(self, project_id: str) -> Path:
        return self.artifacts_dir / project_id

    def _get_workspace_dir(self, project_id: str) -> Path:
        workspace_dir = self._get_project_dir(project_id) / "workspace"
        workspace_dir.mkdir(parents=True, exist_ok=True)
        return workspace_dir

    def _run_git_command(self, project_id: str, args: List[str]) -> Dict[str, Any]:
        workspace_dir = self._get_workspace_dir(project_id)
        try:
            result = subprocess.run(
                ["git"] + args,
                cwd=workspace_dir,
                capture_output=True,
                text=True,
                check=False
            )
            return {
                "status": "success" if result.returncode == 0 else "error",
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode
            }
        except Exception as e:
            logger.error(f"Git command failed: {e}")
            return {"status": "error", "message": str(e)}

    def sync_workspace(self, project_id: str, version_dir: Path):
        """Sync files from a version directory to the workspace directory."""
        workspace_dir = self._get_workspace_dir(project_id)
        
        # Don't delete .git folder
        if (workspace_dir / ".git").exists():
            # Only delete things that are NOT .git
            for item in workspace_dir.iterdir():
                if item.name != ".git":
                    if item.is_dir():
                        shutil.rmtree(item)
                    else:
                        item.unlink()
        
        # Copy files from version_dir to workspace_dir
        for item in version_dir.iterdir():
            if item.name == "metadata.json": # Skip version metadata
                continue
            if item.is_dir():
                shutil.copytree(item, workspace_dir / item.name, dirs_exist_ok=True)
            else:
                shutil.copy2(item, workspace_dir / item.name)

    def init_repo(self, project_id: str) -> Dict[str, Any]:
        return self._run_git_command(project_id, ["init"])

    def get_status(self, project_id: str) -> Dict[str, Any]:
        workspace_dir = self._get_workspace_dir(project_id)
        if not (workspace_dir / ".git").exists():
            return {"status": "not_initialized"}

        # Get current branch
        branch = ""
        
        # 1. Try show-current (works if there's at least one commit)
        res = self._run_git_command(project_id, ["branch", "--show-current"])
        if res["status"] == "success":
            branch = res["stdout"].strip()
            
        # 2. Try symbolic-ref (works on empty repos)
        if not branch:
            res = self._run_git_command(project_id, ["symbolic-ref", "--short", "HEAD"])
            if res["status"] == "success":
                branch = res["stdout"].strip()
                
        # 3. Try parsing from status (very reliable)
        if not branch:
            res = self._run_git_command(project_id, ["status"])
            if res["status"] == "success":
                match = re.search(r"On branch\s+(\S+)", res["stdout"])
                if match:
                    branch = match.group(1)
                    
        branch = branch or "main"

        # Get changed files
        status_res = self._run_git_command(project_id, ["status", "--porcelain"])
        lines = status_res["stdout"].splitlines()
        
        modified = []
        added = []
        deleted = []
        untracked = []

        for line in lines:
            if not line: continue
            state = line[:2]
            filename = line[3:]
            
            if 'M' in state: modified.append(filename)
            elif 'A' in state: added.append(filename)
            elif 'D' in state: deleted.append(filename)
            elif '??' in state: untracked.append(filename)

        return {
            "status": "success",
            "branch": branch,
            "modified_files": modified,
            "added_files": added,
            "deleted_files": deleted,
            "untracked_files": untracked
        }

    def list_branches(self, project_id: str, username: Optional[str] = None, token: Optional[str] = None) -> Dict[str, Any]:
        workspace_dir = self._get_workspace_dir(project_id)
        if not (workspace_dir / ".git").exists():
            return {"status": "not_initialized"}
            
        # 1. Fetch from all remotes to update remote-tracking branches
        remotes_res = self._run_git_command(project_id, ["remote"])
        if remotes_res["status"] == "success":
            remotes = remotes_res["stdout"].split()
            for remote in remotes:
                url_res = self._run_git_command(project_id, ["remote", "get-url", remote])
                if url_res["status"] == "success":
                    url = url_res["stdout"].strip()
                    fetch_command = ["fetch", remote, "--prune", "--tags"]
                    
                    if token and url.startswith("https://"):
                        # Inject credentials for the fetch session
                        clean_url = re.sub(r"https://[^@]+@", "https://", url)
                        user_part = f"{username}:" if username else ""
                        auth_url = clean_url.replace("https://", f"https://{user_part}{token}@")
                        # Use the authenticated URL directly for the fetch
                        fetch_command = ["fetch", auth_url, f"+refs/heads/*:refs/remotes/{remote}/*", "--prune"]
                    
                    fetch_res = self._run_git_command(project_id, fetch_command)
                    if fetch_res["status"] != "success":
                        logger.error(f"Fetch failed for {remote}: {fetch_res.get('stderr')}")

        # 2. Get current branch (reliable method)
        status_res = self.get_status(project_id)
        current_branch = status_res.get("branch", "main") if status_res["status"] == "success" else "main"

        # 3. Use for-each-ref to get all local and remote branches
        # Format: <short_name>|<full_ref_name>
        res = self._run_git_command(project_id, ["for-each-ref", "--format=%(refname:short)|%(refname)", "refs/heads", "refs/remotes"])
        
        branches_info = []
        if res["status"] == "success":
            for line in res["stdout"].splitlines():
                if not line or "|" not in line:
                    continue
                
                short_name, full_ref = line.split("|", 1)
                
                # Skip HEAD pointers like refs/remotes/origin/HEAD
                if short_name.endswith("/HEAD") or full_ref.endswith("/HEAD"):
                    continue
                    
                is_remote = full_ref.startswith("refs/remotes/")
                is_current = short_name == current_branch and not is_remote
                
                branches_info.append({
                    "name": short_name,
                    "full_name": full_ref,
                    "type": "remote" if is_remote else "local",
                    "is_current": is_current
                })

        # 4. Fallback: if no branches found (empty repo)
        if not branches_info:
            branches_info.append({
                "name": current_branch,
                "full_name": f"refs/heads/{current_branch}",
                "type": "local",
                "is_current": True
            })

        # Sort: Current first, then local, then remote
        branches_info.sort(key=lambda x: (not x["is_current"], x["type"] != "local", x["name"]))
        
        return {"status": "success", "branches": branches_info}

    def checkout_branch(self, project_id: str, branch_name: str) -> Dict[str, Any]:
        # Try checking out
        res = self._run_git_command(project_id, ["checkout", branch_name])
        return res

    def add_files(self, project_id: str, files: Optional[List[str]] = None) -> Dict[str, Any]:
        if files:
            return self._run_git_command(project_id, ["add"] + files)
        else:
            return self._run_git_command(project_id, ["add", "."])

    def commit(self, project_id: str, message: str) -> Dict[str, Any]:
        return self._run_git_command(project_id, ["commit", "-m", message])

    def create_branch(self, project_id: str, branch_name: str) -> Dict[str, Any]:
        return self._run_git_command(project_id, ["checkout", "-b", branch_name])

    def add_remote(self, project_id: str, remote_url: str, remote_name: str = "origin") -> Dict[str, Any]:
        # Check if remote exists
        check_remotes = self._run_git_command(project_id, ["remote"])
        res = {"status": "success"}
        if remote_name in check_remotes["stdout"].split():
            res = self._run_git_command(project_id, ["remote", "set-url", remote_name, remote_url])
        else:
            res = self._run_git_command(project_id, ["remote", "add", remote_name, remote_url])
            
        # Immediately try to fetch (without credentials here, list_branches will do it with PAT later)
        if res["status"] == "success":
            self._run_git_command(project_id, ["fetch", remote_name, "--prune"])
            
        return res

    def push(self, project_id: str, remote_name: str = "origin", branch_name: str = "main", username: str = None, token: str = None) -> Dict[str, Any]:
        workspace_dir = self._get_workspace_dir(project_id)
        
        # If token is provided, we need to inject it into the remote URL
        if token:
            remote_res = self._run_git_command(project_id, ["remote", "get-url", remote_name])
            if remote_res["status"] == "success":
                url = remote_res["stdout"].strip()
                if url.startswith("https://"):
                    # Inject token: https://token@github.com/...
                    # Or https://username:token@github.com/...
                    import re
                    new_url = ""
                    if username:
                        new_url = re.sub(r"https://", f"https://{username}:{token}@", url)
                    else:
                        new_url = re.sub(r"https://", f"https://{token}@", url)
                    
                    # Temporarily change remote to push
                    self._run_git_command(project_id, ["remote", "set-url", "temp_push", new_url])
                    push_res = self._run_git_command(project_id, ["push", "temp_push", branch_name])
                    self._run_git_command(project_id, ["remote", "remove", "temp_push"])
                    return push_res

        return self._run_git_command(project_id, ["push", remote_name, branch_name])

git_manager = GitManager()
