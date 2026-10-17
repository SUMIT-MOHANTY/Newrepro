"""Follow-up planning & execution engine for iterative changes and surgical modifications."""
from __future__ import annotations

import json
import os
import re
import time
from typing import Any

from agent.model_router import TaskType
from agent.nodes.core.context import NodeContext
from agent.prompts.system_prompts import (
    FOLLOWUP_PLANNING_SYSTEM_PROMPT,
    PromptBuilder,
    PromptPhase,
)
from agent.state import LangGraphState
from agent.tools.tool_executor import ToolExecutor
from agent.tools.tool_registry import ToolPhase
from infrastructure.claude_tool_client import (
    ClaudeToolClient,
    FileManifest,
    generate_clean_file_tree,
    TaskChecklistTracker,
)
from infrastructure.llm_client import LLMClient


def _derive_acceptance_check(t: dict) -> dict[str, Any] | None:
    """Derive a naive greppable acceptance check when the planner omitted one."""
    desc = str(t.get("description", ""))
    action = str(t.get("action", ""))
    f_name = str(t.get("file", ""))
    spec: dict[str, Any] = {}

    m = re.search(r"\b(?:render|display|show)\s+([A-Z][A-Za-z0-9_]*)", desc)
    if not m:
        m = re.search(r"\b([A-Z][A-Za-z0-9_]*)\s+(?:as the\s+)?(?:default|landing|root)\b", desc)
    if not m:
        m = re.search(r"\bimport\s+([A-Z][A-Za-z0-9_]*)\b", desc)
    if m:
        comp = m.group(1)
        spec.setdefault("contains", []).append(f"<{comp}")

    if action == "create" and f_name.endswith((".jsx", ".js", ".tsx", ".ts")):
        spec.setdefault("contains", []).append("export")

    return spec or None


def _extract_plan_json(raw_text: Any) -> dict[str, Any] | None:
    """Robust JSON extractor for LLM planning responses using bracket balance matching."""
    if hasattr(raw_text, "content"):
        raw_text = raw_text.content
    if not isinstance(raw_text, str):
        raw_text = str(raw_text or "")
    clean_json = raw_text.strip()
    start = clean_json.find("{")
    end = -1
    if start != -1:
        depth = 0
        in_str = False
        escape = False
        for i in range(start, len(clean_json)):
            ch = clean_json[i]
            if escape:
                escape = False
                continue
            if ch == '\\':
                escape = True
                continue
            if ch == '"':
                in_str = not in_str
                continue
            if not in_str:
                if ch == '{':
                    depth += 1
                elif ch == '}':
                    depth -= 1
                    if depth == 0:
                        end = i + 1
                        break
    if start != -1 and end != -1:
        clean_json = clean_json[start:end]
    elif "{" in clean_json and "}" in clean_json:
        clean_json = clean_json[clean_json.find("{"):clean_json.rfind("}") + 1]

    try:
        plan_dict = json.loads(clean_json)
        if isinstance(plan_dict, dict) and plan_dict.get("tasks"):
            return plan_dict
    except Exception:
        pass
    return None


def scan_local_imports(ws: str) -> dict[str, list[str]]:
    """Scan workspace source files to map which local files import what."""
    if not ws or not os.path.exists(ws):
        return {}
    src_dir = os.path.join(ws, "src")
    scan_root = src_dir if os.path.exists(src_dir) else ws

    import_pat = re.compile(
        r"""(?:import\s+.*?\s+from\s+['"](?P<rel>\.[^'"]+)['"]|require\(['"](?P<req>\.[^'"]+)['"]\))"""
    )

    dep_map: dict[str, set[str]] = {}
    for root, dirs, files in os.walk(scan_root):
        dirs[:] = [d for d in dirs if d not in ("node_modules", "dist", ".git", ".next", "build")]
        for f in files:
            if not f.endswith((".js", ".jsx", ".ts", ".tsx")):
                continue
            full_p = os.path.join(root, f)
            rel_file = os.path.relpath(full_p, ws).replace("\\", "/")
            try:
                with open(full_p, "r", encoding="utf-8", errors="ignore") as fp:
                    content = fp.read()
                for m in import_pat.finditer(content):
                    spec = m.group("rel") or m.group("req")
                    target_dir = os.path.dirname(full_p)
                    resolved_target = os.path.normpath(os.path.join(target_dir, spec))
                    matched_file = None
                    for ext in ("", ".js", ".jsx", ".ts", ".tsx", os.path.sep + "index.js", os.path.sep + "index.jsx"):
                        candidate = resolved_target + ext
                        if os.path.isfile(candidate):
                            matched_file = os.path.relpath(candidate, ws).replace("\\", "/")
                            break
                    if not matched_file:
                        matched_file = os.path.relpath(resolved_target, ws).replace("\\", "/")
                    dep_map.setdefault(matched_file, set()).add(rel_file)
            except Exception:
                pass

    return {k: sorted(list(v)) for k, v in sorted(dep_map.items())}


def format_import_dependencies(dep_map: dict[str, list[str]]) -> str:
    """Format the import dependencies as a clean, concise string for the planner."""
    if not dep_map:
        return ""
    lines = ["## Codebase Import Dependencies:"]
    for target, importers in dep_map.items():
        importers_str = ", ".join(f"`{imp}`" for imp in importers)
        lines.append(f"- `{target}` is imported by: {importers_str}")
    return "\n".join(lines) + "\n"


def formulate_followup_plan(
    prompt: str,
    prompt_history: list[dict[str, Any]],
    clean_tree: str,
    active_manifest: Any,
    config: Any,
    ctx: NodeContext,
    workspace_path: str = "",
    session_id: str = "",
) -> dict[str, Any]:
    """Formulate an objective-driven, multi-file execution plan for follow-up requests."""
    history_context = ""
    if prompt_history and len(prompt_history) > 1:
        history_context = "Previous user requests in this project:\n"
        for idx, h in enumerate(prompt_history[:-1], 1):
            p = h.get("prompt", "")[:200]
            history_context += f"- Prompt {idx}: \"{p}\"\n"

    manifest_summary = ""
    if active_manifest and hasattr(active_manifest, "to_manifest_string"):
        manifest_summary = active_manifest.to_manifest_string()

    is_continue = bool(re.search(r'\bcontinue\b', prompt, re.IGNORECASE))
    continuation_note = ""
    if is_continue:
        continuation_note = (
            "IMPORTANT CONTINUATION INSTRUCTION: The user has requested to CONTINUE the previous task. "
            "Inspect the previous requests in history and the files currently in the workspace. "
            "Determine what has already been built/modified and what remains to be completed or verified. "
            "Structure your objective and tasks to finish the remaining changes and verify the build.\n\n"
        )

    ws_path = workspace_path or getattr(active_manifest, "workspace_path", "") or os.environ.get("WORKSPACE_PATH", "")
    dep_map = scan_local_imports(ws_path) if ws_path else {}
    dep_context = format_import_dependencies(dep_map)

    planning_msg = (
        "You are an expert full-stack engineer and software architect.\n"
        "A user has submitted a follow-up request to modify an existing, deployed application.\n"
        "Inspect the codebase using your tools (`read_file`, `grep_search`, `list_directory`), "
        "then call `submit_plan` with an accurate, dynamic execution plan.\n\n"
        f"WORKSPACE CODEBASE TREE:\n{clean_tree}\n\n"
        + (f"{dep_context}\n" if dep_context else "")
        + f"{manifest_summary}\n\n"
        + f"{history_context}\n"
        + f"{continuation_note}"
        + f"CURRENT USER REQUEST TO PLAN:\n\"{prompt}\"\n\n"
        "INSTRUCTIONS FOR INSPECTION & PLANNING:\n"
        "1. First, inspect the relevant existing files using your tools:\n"
        "   - Use `read_file` to check `package.json` for installed packages (e.g. recharts, lucide-react, react-router-dom, date-fns, clsx).\n"
        "   - Use `read_file` or `grep_search` to check `src/App.jsx` (or router file) for existing routes, navigation, and placeholder stubs.\n"
        "   - Inspect existing component or mock data files if relevant to understand current structure.\n"
        "2. When you understand the codebase state, call `submit_plan` with your objective, current state, changes required, and file checklist.\n"
        "   - DEPENDENCY RULE: If a library needed for the request is already in `package.json`, DO NOT plan a task to edit `package.json` or install it!\n"
        "   - ROUTING INTEGRITY: When adding or completing a section/view (e.g. replacing placeholder or adding a new tab), ensure BOTH the component file is planned (action: 'create' or 'edit') AND `src/App.jsx` is planned (action: 'edit') to import the component and mount it inside its Route element. Never leave placeholder JSX in App.jsx.\n"
        "   - If package.json is genuinely modified to add NEW dependencies, include a task with action 'install' right after it.\n"
        "   - When integrating third-party connectors or services (payments, auth, storage, database), plan interactive client-side components and mock adapters (simulated checkout modal, sandbox status, mock data, localStorage persistence) so the prototype is 100% runnable out of the box.\n"
        "   - Conclude with a verification task (`file: 'build_verification'`, `action: 'verify'`).\n"
    )

    tools = ctx.registry.get_tools(ToolPhase.followup_planning)
    executor = ToolExecutor(ctx.mcp, ctx.registry, event_callback=getattr(ctx, "post_event", None))

    client = ClaudeToolClient(
        model=config.model,
        api_key=config.api_key,
        tools=tools,
        max_tokens=config.max_tokens,
        temperature=config.temperature,
        reality_guard=ctx.reality_guard,
        file_manifest=active_manifest,
        workspace_path=ws_path,
    )

    print(f"[Graph:FollowUpPlan] 🔍 Launching Tool-Assisted Inspection loop (room: 8 turns) for session {session_id}...")
    result = client.run_tool_loop(
        system=FOLLOWUP_PLANNING_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": planning_msg}],
        tool_executor=executor,
        max_iterations=8,
        on_event=ctx.event_callback,
    )

    plan: dict[str, Any] = executor.submitted_plan or {}

    if not plan or not isinstance(plan, dict) or not plan.get("tasks"):
        plan = _extract_plan_json(result.final_text or "") or {}

    if not plan or not isinstance(plan, dict) or not plan.get("tasks"):
        try:
            print("[Graph:FollowUpPlan] ⚠️ Fallback: Calling direct completion to extract structured plan...")
            llm_fallback = LLMClient(config)
            fallback_prompt = (
                f"{planning_msg}\n\n"
                f"Assistant Notes/Observations from Inspection:\n{result.final_text}\n\n"
                "Output ONLY a valid JSON object matching this schema (no markdown code fences):\n"
                "{\n"
                '  "objective": "Clear statement of what the user wants to achieve.",\n'
                '  "current_state": "Summary of relevant components found.",\n'
                '  "changes_required": "Breakdown of changes needed.",\n'
                '  "tasks": [\n'
                '    {"task_id": 1, "file": "src/App.jsx", "action": "edit", "description": "Update routing"},\n'
                '    {"task_id": 2, "file": "build_verification", "action": "verify", "description": "Run install_and_build"}\n'
                "  ]\n"
                "}"
            )
            raw_fallback = llm_fallback.call_ai(model=config.model, prompt=fallback_prompt)
            fallback_text = getattr(raw_fallback, "content", "") if hasattr(raw_fallback, "content") else str(raw_fallback or "")
            plan = _extract_plan_json(fallback_text) or {}
        except Exception as e:
            print(f"[Graph:FollowUpPlan] Fallback extraction error: {e}")

    if not plan or not isinstance(plan, dict) or not plan.get("tasks"):
        raise RuntimeError("The AI failed to generate a valid follow-up execution plan after tool-assisted inspection.")

    validated_tasks = []
    raw_tasks = plan.get("tasks", [])
    for idx_t, t in enumerate(raw_tasks):
        if not isinstance(t, dict):
            continue
        f_name = str(t.get("file", "")).strip()
        action = str(t.get("action", "")).strip().lower()

        if action in ("verify", "install") or "verification" in f_name.lower():
            t["task_id"] = len(validated_tasks) + 1
            validated_tasks.append(t)
            continue

        file_exists = False
        if ws_path and f_name:
            norm_f = f_name.replace(ws_path, "").replace("\\", "/").lstrip("/")
            disk_p = os.path.join(ws_path, norm_f)
            file_exists = os.path.exists(disk_p)
        elif active_manifest and hasattr(active_manifest, "has_file"):
            file_exists = active_manifest.has_file(f_name)

        if action == "delete":
            if not file_exists:
                print(f"[Graph:FollowUpPlan] 🛡️ Pruned phantom delete task for non-existent file: `{f_name}`")
                continue
        elif action == "edit":
            if not file_exists:
                print(f"[Graph:FollowUpPlan] 🛡️ Converted edit to create for new file: `{f_name}`")
                t["action"] = "create"
                t["description"] = f"Create {f_name}"
        elif action == "create":
            if file_exists:
                print(f"[Graph:FollowUpPlan] 🛡️ Converted create to edit for existing file on disk: `{f_name}`")
                t["action"] = "edit"

        if not t.get("verify"):
            derived = _derive_acceptance_check(t)
            if derived:
                t["verify"] = derived
                print(f"[Graph:FollowUpPlan] 🎯 Derived acceptance check for `{f_name}`: {derived}")

        t["task_id"] = len(validated_tasks) + 1
        validated_tasks.append(t)

        if f_name.endswith("package.json"):
            has_next_install = False
            if idx_t + 1 < len(raw_tasks):
                next_t = raw_tasks[idx_t + 1]
                if isinstance(next_t, dict) and (next_t.get("action") == "install" or "install" in str(next_t.get("file", "")).lower() or "install" in str(next_t.get("description", "")).lower()):
                    has_next_install = True
            if not has_next_install:
                print("[Graph:FollowUpPlan] ⚡ Injected mandatory install task immediately following package.json update.")
                validated_tasks.append({
                    "task_id": len(validated_tasks) + 1,
                    "file": "package.json",
                    "action": "install",
                    "description": "Run install_dependencies (npm install) to install newly declared dependencies before writing code",
                })

    non_delete = [t for t in validated_tasks if t.get("action") not in ("delete", "verify")]
    delete_tasks = [t for t in validated_tasks if t.get("action") == "delete"]
    verify_tasks = [t for t in validated_tasks if t.get("action") == "verify"]

    ordered_tasks = non_delete + delete_tasks + verify_tasks
    for idx, t in enumerate(ordered_tasks, 1):
        t["task_id"] = idx
    plan["tasks"] = ordered_tasks
    print(f"[Graph:FollowUpPlan] ✅ Follow-up plan validated with {len(plan['tasks'])} tasks.")
    return plan


def follow_up_node(state: LangGraphState, ctx: NodeContext) -> dict[str, Any]:
    """Execute dedicated follow-up pipeline for Prompt 2+ (surgical edits & features)."""
    ws = state["workspace_path"]
    prompt = state["prompt"]
    session_id = state.get("session_id", "")
    task_id = state.get("task_id", "")

    print(f"[Graph:FollowUpNode] Executing dedicated follow-up pipeline for session {session_id}, task {task_id}...")
    ctx.post_event("coding_started", {
        "session_id": session_id,
        "task_id": task_id,
    })

    base_branch = state.get("base_branch") or os.environ.get("GIT_BRANCH", "main")
    from agent.nodes.discovery.discover_workspace import build_feature_branch_name
    feature_branch = state.get("feature_branch") or build_feature_branch_name(task_id, prompt[:80])
    try:
        from mcp.git_tools import GitTools
        git = GitTools(ws)
        git.init(workspace_path=ws)
        git.checkout_branch(branch=feature_branch, create=True, base_branch=base_branch)
        print(f"[Graph:FollowUpNode] 🌿 Checked out feature branch: '{feature_branch}'")
    except Exception as git_err:
        print(f"[Graph:FollowUpNode] Feature branch checkout note: {git_err}")

    if ctx.reality_guard:
        ctx.reality_guard.state.refresh()

    active_manifest = ctx.prior_manifest or ctx.active_manifest or FileManifest()
    active_manifest.scan_workspace(ws)
    ctx.active_manifest = active_manifest

    clean_tree = generate_clean_file_tree(ws)

    hist_dir = os.path.join(ws, ".agent_history")
    os.makedirs(hist_dir, exist_ok=True)
    prompts_file = os.path.join(hist_dir, "prompts_history.json")
    prompt_history_entries: list[dict[str, Any]] = []
    try:
        if os.path.exists(prompts_file):
            with open(prompts_file, "r", encoding="utf-8") as f:
                prompt_history_entries = json.load(f)
        if not prompt_history_entries or prompt_history_entries[-1].get("task_id") != task_id:
            prompt_history_entries.append({
                "task_id": task_id,
                "prompt": prompt,
                "time": time.time(),
            })
            with open(prompts_file, "w", encoding="utf-8") as f:
                json.dump(prompt_history_entries, f, indent=2)
    except Exception as e:
        print(f"[Graph:FollowUpNode] Warning writing prompt history: {e}")

    planning_config = ctx.router.route(TaskType.planning, model=state.get("model_name"))
    plan = formulate_followup_plan(
        prompt=prompt,
        prompt_history=prompt_history_entries,
        clean_tree=clean_tree,
        active_manifest=active_manifest,
        config=planning_config,
        ctx=ctx,
        workspace_path=ws,
        session_id=session_id,
    )

    try:
        plan_file = os.path.join(hist_dir, "current_plan.json")
        with open(plan_file, "w", encoding="utf-8") as f:
            json.dump(plan, f, indent=2)
    except Exception:
        pass

    objective = plan.get("objective", prompt[:200])
    current_state = plan.get("current_state", "")
    changes_required = plan.get("changes_required", "")
    tasks = plan.get("tasks", [])

    print(f"[Graph:FollowUpNode] 🎯 Objective: {objective}")
    print(f"[Graph:FollowUpNode] 🔍 Current State: {current_state}")
    print(f"[Graph:FollowUpNode] 🛠️ Changes Required: {changes_required}")
    print(f"[Graph:FollowUpNode] 📋 Planned {len(tasks)} tasks.")

    task_tracker = TaskChecklistTracker(
        tasks=tasks,
        objective=objective,
        current_state=current_state,
        changes_required=changes_required,
    )

    ctx.post_event("plan_formulated", {
        "session_id": session_id,
        "task_id": task_id,
        "objective": objective,
        "current_state": current_state,
        "changes_required": changes_required,
        "tasks": tasks,
    })
    if ctx.event_callback:
        ctx.event_callback("task_plan", {
            "objective": objective,
            "tasks": tasks,
        })

    prompt_history_text = ""
    if len(prompt_history_entries) > 1:
        prompt_history_text = "## Conversation & Project History (Previous User Requests in this session):\n"
        for idx, entry in enumerate(prompt_history_entries[:-1], 1):
            p_text = entry.get("prompt", "").strip()
            summary = p_text if len(p_text) < 300 else p_text[:300] + "..."
            prompt_history_text += f"- Request {idx}: \"{summary}\"\n"
        prompt_history_text += "\n"

    user_request_section = (
        f"{prompt_history_text}"
        f"## Current User Request to Implement:\n"
        f"{prompt}\n\n"
    )
    if re.search(r'\bcontinue\b', prompt, re.IGNORECASE):
        user_request_section += (
            "NOTE: The user is continuing the previous task. Check what files are already updated, "
            "finish any remaining implementation details, and verify with install_and_build.\n\n"
        )

    context_summary = ""
    if active_manifest and active_manifest.get_file_count() > 0:
        context_summary = (
            "## Workspace Files (already built — DO NOT re-create or overwrite):\n"
            + active_manifest.to_manifest_string()
            + "\n\nAll files above EXIST on disk. Inspect files, then apply surgical updates.\n\n"
        )

    edit_prompt = (
        context_summary
        + user_request_section
        + f"Workspace: {ws}\n\n"
        + "## Task Execution Guidelines:\n"
        + "1. Follow the task checklist to create or update the necessary files.\n"
        + "2. Read the relevant file if needed for context, then apply updates with `replace_file_content` or `write_file`.\n"
        + "3. Once all planned updates are completed, run `install_and_build` to verify the build passes.\n"
        + "4. Provide a clear, concise summary of the changes.\n"
    )

    tools = ctx.registry.get_tools(ToolPhase.editing)
    executor = ToolExecutor(ctx.mcp, ctx.registry, event_callback=getattr(ctx, "post_event", None))
    coding_config = ctx.router.route(TaskType.coding, model=state.get("model_name"))

    client = ClaudeToolClient(
        model=coding_config.model,
        api_key=coding_config.api_key,
        tools=tools,
        max_tokens=coding_config.max_tokens,
        temperature=coding_config.temperature,
        reality_guard=ctx.reality_guard,
        file_manifest=active_manifest,
        workspace_path=ws,
    )

    result = client.run_tool_loop(
        system=PromptBuilder.build(PromptPhase.EDITING),
        messages=[{"role": "user", "content": edit_prompt}],
        tool_executor=executor,
        max_iterations=25,
        on_event=ctx.event_callback,
        task_tracker=task_tracker,
        clean_file_tree=clean_tree,
    )

    try:
        fix_history_file = os.path.join(hist_dir, "fix_history.json")
        fix_entries = []
        if os.path.exists(fix_history_file):
            with open(fix_history_file, "r", encoding="utf-8") as f:
                fix_entries = json.load(f)
        fix_entries.append({
            "task_id": task_id,
            "prompt": prompt,
            "files_changed": result.files_changed,
            "tool_calls_count": len(result.tool_calls_made),
            "timestamp": time.time(),
            "final_text": (result.final_text or "")[:500],
        })
        with open(fix_history_file, "w", encoding="utf-8") as f:
            json.dump(fix_entries, f, indent=2)
    except Exception as e:
        print(f"[Graph:FollowUpNode] Warning saving fix history: {e}")

    built_ok = bool(getattr(executor, "built_successfully", False))

    return {
        "feature_branch": feature_branch,
        "files_changed": result.files_changed,
        "final_text": result.final_text,
        "build_success": built_ok,
        "status": "coded",
    }
