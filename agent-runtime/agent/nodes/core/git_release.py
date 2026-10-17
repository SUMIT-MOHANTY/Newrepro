"""Git release, feature-branch push, merge to base branch, and deliverable artifact packager."""
from __future__ import annotations

import json
import os
import re
import tarfile
import time
from typing import Any

from agent.nodes.core.context import NodeContext
from agent.nodes.discovery.discover_workspace import build_feature_branch_name
from agent.state import LangGraphState


def git_push_node(state: LangGraphState, ctx: NodeContext) -> dict[str, Any]:
    """Commit task changes on feature/<task-name>, push feature branch to remote Git,
    merge into base branch (real-developer Git workflow), and push base branch.
    """
    ws = state["workspace_path"]
    task_id = state.get("task_id", "unknown")
    session_id = state.get("session_id", "unknown")
    files_changed = state.get("files_changed", [])
    base_branch = state.get("base_branch") or os.environ.get("GIT_BRANCH", "main")
    feature_branch = (
        state.get("feature_branch")
        or build_feature_branch_name(task_id, state.get("prompt", "")[:80])
    )

    print(f"[Graph:GitPushNode] 🌿 Committing {len(files_changed)} file(s) on branch '{feature_branch}'...")

    from mcp.git_tools import GitTools
    git = GitTools(ws)

    # Step 1: Ensure git repo is initialized and on the feature branch
    try:
        git.init(workspace_path=ws)
        git.checkout_branch(branch=feature_branch, create=True, base_branch=base_branch)
    except Exception as e:
        print(f"[Graph:GitPushNode] Git branch check note: {e}")

    # Step 2: Commit checkpoint on feature branch
    mode_tag = (state.get("project_mode") or "greenfield").upper()
    summary = f"[{mode_tag}] {state.get('final_text', 'Agent task completed')[:100]}"
    commit_result = git.commit_checkpoint(
        task_id=task_id,
        summary=summary,
        files_changed=files_changed,
    )

    commit_hash = "unknown"
    if commit_result.success:
        commit_hash = commit_result.data.get("commit_hash", "unknown")
        commit_status = commit_result.data.get("status", "committed")
        print(f"[Graph:GitPushNode] 💾 Committed {commit_hash[:8]} on '{feature_branch}' ({commit_status})")
    else:
        print(f"[Graph:GitPushNode] Commit warning: {commit_result.error}")

    # Step 3: Push feature/<task-name> to remote Git repository
    push_success = False
    push_message = "Push not attempted"

    repo_url = os.environ.get("GIT_REPO_URL", "")
    auth_token = os.environ.get("GIT_AUTH_TOKEN") or os.environ.get("GIT_PAT_TOKEN", "")

    if repo_url:
        try:
            push_result = git.push(
                branch=feature_branch,
                auth_token=auth_token if auth_token else None,
                repo_url=repo_url if repo_url else None,
            )
            if push_result.success:
                push_success = True
                push_message = f"Pushed {feature_branch} to {repo_url}"
                print(f"[Graph:GitPushNode] 🚀 Pushed feature branch '{feature_branch}' to {repo_url}")
            else:
                push_message = f"Push failed: {push_result.error}"
                print(f"[Graph:GitPushNode] Push failed: {push_result.error}")
        except Exception as e:
            push_message = f"Push error: {e}"
            print(f"[Graph:GitPushNode] Push error: {e}")
    else:
        push_message = "No GIT_REPO_URL configured - local feature branch committed"
        print(f"[Graph:GitPushNode] Local branch '{feature_branch}' committed (no GIT_REPO_URL set)")

    # Step 4: Merge feature branch into base_branch and push base_branch
    try:
        merge_res = git.merge_branch(feature_branch=feature_branch, base_branch=base_branch, no_ff=True)
        if merge_res.success:
            print(f"[Graph:GitPushNode] 🔀 Merged '{feature_branch}' into '{base_branch}'")
            if repo_url:
                git.push(branch=base_branch, auth_token=auth_token if auth_token else None, repo_url=repo_url if repo_url else None)
        else:
            print(f"[Graph:GitPushNode] Merge warning (auto-aborted if conflict): {merge_res.error}")
    except Exception as merge_err:
        print(f"[Graph:GitPushNode] Merge note: {merge_err}")

    ctx.post_event("git_push_completed", {
        "session_id": session_id,
        "task_id": task_id,
        "feature_branch": feature_branch,
        "base_branch": base_branch,
        "commit_hash": commit_hash,
        "push_success": push_success,
        "push_message": push_message,
        "files_committed": len(files_changed),
    })

    return {
        "feature_branch": feature_branch,
        "commit_hash": commit_hash,
        "push_success": push_success,
        "push_message": push_message,
    }


def delivery_node(state: LangGraphState, ctx: NodeContext) -> dict[str, Any]:
    """Package the verified Greenfield, Brownfield, or Migration project into /workspace/output."""
    ws = state["workspace_path"]
    session_id = state.get("session_id", "unknown")
    task_id = state.get("task_id", "unknown")
    techstack = state.get("techstack") or {}
    project_mode = (state.get("project_mode") or techstack.get("project_mode") or "greenfield").lower()
    files_changed = state.get("files_changed", [])
    feature_branch = state.get("feature_branch", f"feature/{task_id}")

    output_dir = os.path.join(ws, "output")
    os.makedirs(output_dir, exist_ok=True)

    delivery_manifest = {
        "session_id": session_id,
        "task_id": task_id,
        "project_mode": project_mode,
        "techstack": techstack.get("stack", "react_vite"),
        "source_stack": techstack.get("source_stack"),
        "primary_language": techstack.get("primary_language", "javascript"),
        "architecture_type": techstack.get("architecture_type", "frontend"),
        "feature_branch": feature_branch,
        "commit_hash": state.get("commit_hash", "unknown"),
        "push_success": bool(state.get("push_success", False)),
        "build_verified": bool(state.get("build_success", False)),
        "platform_verified": bool(state.get("platform_verified", False)),
        "backend_healthy": bool(state.get("backend_healthy", True)),
        "preview_url": state.get("preview_url", "http://localhost:80"),
        "files_changed_count": len(files_changed),
        "files_changed": files_changed,
        "delivered_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    manifest_path = os.path.join(output_dir, "DELIVERY_MANIFEST.json")
    report_path = os.path.join(output_dir, "DELIVERY_REPORT.md")
    archive_path = os.path.join(output_dir, f"deliverable_{project_mode}_{task_id}.tar.gz")

    try:
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(delivery_manifest, f, indent=2)

        files_bullets = "\n".join(f"- `{p}`" for p in files_changed[:100]) or "- *(No files recorded)*"
        report_md = (
            f"# Project Delivery Report ({project_mode.upper()})\n\n"
            f"- **Project Mode**: `{project_mode.upper()}`\n"
            f"- **Target Tech Stack**: `{delivery_manifest['techstack']}` ({delivery_manifest['primary_language']})\n"
            f"- **Git Feature Branch**: `{feature_branch}` (Commit: `{delivery_manifest['commit_hash']}`)\n"
            f"- **Build Verified**: `{delivery_manifest['build_verified']}`\n"
            f"- **Platform Runnability Verified**: `{delivery_manifest['platform_verified']}`\n"
            f"- **Live Preview URL**: {delivery_manifest['preview_url']}\n\n"
            f"## Executive Summary\n{state.get('final_text', 'Application built, verified, and packaged.')}\n\n"
            f"## Delivered / Modified Files ({len(files_changed)})\n{files_bullets}\n"
        )
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report_md)

        def tar_filter(tarinfo: tarfile.TarInfo) -> tarfile.TarInfo | None:
            # Recursively exclude dependency & cache dirs at any depth
            parts = set(re.split(r"[\\/]", tarinfo.name))
            ignored = {"node_modules", ".git", "__pycache__", ".pytest_cache", "output", ".venv", "venv", "dist", "build"}
            if parts.intersection(ignored):
                return None
            return tarinfo

        with tarfile.open(archive_path, "w:gz") as tar:
            for item in os.listdir(ws):
                if item in {"node_modules", ".git", "__pycache__", ".pytest_cache", "output", ".venv", "venv", "dist", "build"}:
                    continue
                item_full = os.path.join(ws, item)
                tar.add(item_full, arcname=item, filter=tar_filter)
            tar.add(manifest_path, arcname="DELIVERY_MANIFEST.json")
            tar.add(report_path, arcname="DELIVERY_REPORT.md")

        delivery_manifest["manifest_path"] = manifest_path
        delivery_manifest["report_path"] = report_path
        delivery_manifest["archive_path"] = archive_path
        print(f"[Graph:DeliveryNode] 📦 Deliverable packaged at: {archive_path}")
    except Exception as e:
        print(f"[Graph:DeliveryNode] Warning packaging deliverable: {e}")

    ctx.post_event("delivery_completed", delivery_manifest)

    return {
        "delivery_manifest": delivery_manifest,
        "deliverable_archive_path": archive_path,
        "status": "completed",
    }
