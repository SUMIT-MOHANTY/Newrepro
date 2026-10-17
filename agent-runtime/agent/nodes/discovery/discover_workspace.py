"""Discovery & initialization node — establishes environment baseline, techstack, feature branch, and state."""
from __future__ import annotations

import json
import os
import re
import time
from typing import Any

from agent.nodes.core.context import NodeContext
from agent.spec_manager import ProductSpec
from agent.state import LangGraphState
from agent.techstack_detector import detect_techstack
from infrastructure.claude_tool_client import FileManifest
from infrastructure.llm_client import LLMClient


MIGRATION_KEYWORDS = (
    "migrate", "migration", "port to", "port from", "convert from", "convert to",
    "rewrite in", "modernize", "upgrade from", "legacy to",
)


def build_feature_branch_name(task_id: str, title_or_prompt: str) -> str:
    """Create a clean human-developer branch name: feature/<task-id>-<short-slug>."""
    clean_id = re.sub(r"[^a-zA-Z0-9]+", "-", str(task_id or "task")).strip("-").lower()[:24]
    words = re.findall(r"[a-zA-Z0-9]+", (title_or_prompt or "").lower())
    stop = {"the", "and", "for", "with", "build", "create", "please", "app", "application", "project"}
    slug_words = [w for w in words if w not in stop and len(w) > 2][:4]
    slug = "-".join(slug_words)[:32]
    if slug and slug not in clean_id:
        return f"feature/{clean_id}-{slug}"
    return f"feature/{clean_id or 'work-item'}"


def _resolve_project_mode(prompt: str, task_type: str, has_existing_code: bool, detected_mode: str) -> str:
    t_lower = (task_type or "").lower()
    p_lower = (prompt or "").lower()

    if "migration" in t_lower or any(k in p_lower for k in MIGRATION_KEYWORDS) or detected_mode == "migration":
        return "migration"
    if "brownfield" in t_lower or any(k in t_lower for k in ("follow_up", "edit", "bug", "fix")):
        return "brownfield" if has_existing_code else "greenfield"
    if has_existing_code:
        return "brownfield"
    return "greenfield"


def initialize_node(state: LangGraphState, ctx: NodeContext) -> dict[str, Any]:
    """Baseline the workspace, detect tech stack & project mode, checkout feature/<task>, and init spec."""
    ws = state["workspace_path"]
    prompt = state.get("prompt", "")
    task_id = state.get("task_id", "task-01")
    task_str = str(state.get("task_type", "")).lower()

    os.makedirs(ws, exist_ok=True)
    ctx.mcp.call_tool("filesystem", "create_directory", {"path": ws})

    # 1. Detect if workspace already has source files on disk
    has_existing_code = False
    try:
        ignored = {"node_modules", "__pycache__", "output", "dist", "build", ".venv", "venv", ".git"}
        entries = [f for f in os.listdir(ws) if not f.startswith(".") and f not in ignored]
        if len(entries) > 0:
            has_existing_code = True
    except Exception:
        pass

    # 2. Detect techstack & resolve authoritative project_mode
    llm_client = LLMClient()
    techstack = detect_techstack(prompt, llm_client=llm_client, model=state.get("model_name", ""), workspace_path=ws)
    project_mode = _resolve_project_mode(
        prompt=prompt,
        task_type=task_str,
        has_existing_code=has_existing_code,
        detected_mode=techstack.get("project_mode", "greenfield"),
    )
    techstack["project_mode"] = project_mode

    print(
        f"[Graph:InitializeNode] Mode={project_mode.upper()} | Stack={techstack['stack']} | "
        f"ExistingCode={has_existing_code} | Lang={techstack.get('primary_language', 'unknown')}"
    )

    # 3. Initialize Git & Checkout Human-Style Feature Branch (feature/<task-slug>)
    base_branch = os.environ.get("GIT_BRANCH", "main")
    feature_branch = state.get("feature_branch") or build_feature_branch_name(task_id, prompt[:80])

    try:
        from mcp.git_tools import GitTools
        git = GitTools(ws)
        git.init(workspace_path=ws)
        git.checkout_branch(branch=feature_branch, create=True, base_branch=base_branch)
        print(f"[Graph:InitializeNode] 🌿 Checked out feature branch: '{feature_branch}' (from '{base_branch}')")
        ctx.post_event("branch_checked_out", {
            "session_id": state["session_id"],
            "task_id": task_id,
            "feature_branch": feature_branch,
            "base_branch": base_branch,
            "project_mode": project_mode,
        })
    except Exception as git_err:
        print(f"[Graph:InitializeNode] Git branch setup note: {git_err}")

    ctx.reality_guard.state.refresh()

    # 4. Synthesize or load Living Product Spec
    spec = ProductSpec.load_or_init(ws, prompt)

    # 5. Persist prompt history
    try:
        hist_dir = os.path.join(ws, ".agent_history")
        os.makedirs(hist_dir, exist_ok=True)
        prompts_file = os.path.join(hist_dir, "prompts_history.json")
        if not os.path.exists(prompts_file):
            with open(prompts_file, "w", encoding="utf-8") as f:
                json.dump([{"task_id": task_id, "prompt": prompt, "time": time.time()}], f, indent=2)
    except Exception:
        pass

    manifest = FileManifest()
    manifest.scan_workspace(ws)
    ctx.active_manifest = manifest

    ctx.post_event("session_started", {
        "session_id": state["session_id"],
        "task_id": task_id,
        "task_type": state["task_type"],
        "project_mode": project_mode,
        "feature_branch": feature_branch,
        "model": state["model_name"],
        "techstack": techstack,
    })

    return {
        "spec": spec.to_dict(),
        "techstack": techstack,
        "project_mode": project_mode,
        "has_existing_code": has_existing_code,
        "base_branch": base_branch,
        "feature_branch": feature_branch,
        "status": "initialized",
        "files_changed": [],
        "fix_attempts": 0,
        "build_success": False,
    }
