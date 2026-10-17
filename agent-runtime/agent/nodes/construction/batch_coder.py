"""Multi-stack batch and migration code generation nodes."""
from __future__ import annotations

from typing import Any

from agent.model_router import TaskType
from agent.nodes.core.context import NodeContext
from agent.nodes.legacy.frontend_ui_helper import sequential_code_node
from agent.prompts.system_prompts import CODING_SYSTEM_PROMPT
from agent.spec_manager import ProductSpec
from agent.state import LangGraphState
from agent.tools.tool_executor import ToolExecutor
from agent.tools.tool_registry import ToolPhase
from infrastructure.claude_tool_client import (
    ClaudeToolClient,
    FileManifest,
    generate_clean_file_tree,
)


def custom_batch_code_node(state: LangGraphState, ctx: NodeContext) -> dict[str, Any]:
    """2-Batch Generation for custom and enterprise Greenfield tech stacks (Java, Python, Go, Next.js, Vue, etc.)."""
    print("[Graph:CustomBatchCodeNode] Starting enterprise tech stack batch generation...")
    ctx.post_event("coding_started", {
        "session_id": state["session_id"],
        "task_id": state["task_id"],
        "project_mode": state.get("project_mode", "greenfield"),
    })

    config = ctx.router.route(TaskType.coding, model=state.get("model_name"))
    tools = ctx.registry.get_tools(ToolPhase.batch_coding)
    executor = ToolExecutor(ctx.mcp, ctx.registry, event_callback=getattr(ctx, "post_event", None))

    client = ClaudeToolClient(
        model=config.model,
        api_key=config.api_key,
        tools=tools,
        max_tokens=config.max_tokens,
        temperature=config.temperature,
        reality_guard=ctx.reality_guard,
        file_manifest=ctx.active_manifest,
    )

    ws = state["workspace_path"]
    spec = ProductSpec.load_or_init(ws, state.get("prompt", ""))
    spec_context = spec.to_system_context()
    plan_text = state.get("plan_text", "")
    base_context = f"{spec_context}\n\nUser Prompt:\n{state['prompt']}\n{plan_text}"

    techstack = state.get("techstack") or {"is_custom": True, "stack": "custom"}
    custom_stack_name = techstack.get("stack", "custom")

    print(f"[Graph:CustomBatchCodeNode] 📦 Batch 1/2: Generating Architecture Tree for {custom_stack_name}...")
    batch1_msg = (
        f"{base_context}\n\n"
        f"### BATCH 1 DIRECTIVE: Project Tree & Tooling ({custom_stack_name})\n"
        "You MUST issue a structured `write_files` (or `write_file`) tool call now to write:\n"
        "1. Dependency manifest (`package.json`, `requirements.txt`, `pom.xml`, `go.mod`, etc.).\n"
        "2. Build & bundler configurations and environment defaults.\n"
        "3. Root entrypoint / server / application bootstrap files.\n"
    )

    res1 = client.run_tool_loop(
        system=CODING_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": batch1_msg}],
        tool_executor=executor,
        max_iterations=4,
        on_event=ctx.event_callback,
    )

    print(f"[Graph:CustomBatchCodeNode] 📦 Batch 2/2: Generating Domain Logic, Views & README for {custom_stack_name}...")
    batch2_msg = (
        f"{base_context}\n\n"
        f"### BATCH 2 DIRECTIVE: Domain Logic, Views & README.md ({custom_stack_name})\n"
        "You MUST issue `write_files` (or `write_file`) calls now to write:\n"
        "1. Realistic domain data, models, services, and API controllers/adapters.\n"
        "2. All UI views, routes, components, and unit/smoke tests implementing the user's requirements.\n"
        "3. A complete `README.md` at the workspace root.\n"
    )

    res2 = client.run_tool_loop(
        system=CODING_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": batch2_msg}],
        tool_executor=executor,
        max_iterations=6,
        on_event=ctx.event_callback,
    )

    all_files_changed = list(dict.fromkeys(res1.files_changed + res2.files_changed))
    print(f"[Graph:CustomBatchCodeNode] Completed custom batch generation. Total files: {len(all_files_changed)}")

    return {
        "files_changed": all_files_changed,
        "final_text": res2.final_text or res1.final_text or "Custom batch code generation completed.",
        "status": "coded",
    }


def migration_code_node(state: LangGraphState, ctx: NodeContext) -> dict[str, Any]:
    """Execute Legacy-to-Modern Stack Migration with full Read + Write + Verification tools."""
    ws = state["workspace_path"]
    prompt = state["prompt"]
    plan_text = state.get("plan_text", "")
    techstack = state.get("techstack") or {}
    source_stack = techstack.get("source_stack", "legacy_codebase")
    target_stack = techstack.get("stack", "modern_stack")

    print(f"[Graph:MigrationCodeNode] 🔄 Migrating from '{source_stack}' -> '{target_stack}' in {ws}...")
    ctx.post_event("coding_started", {
        "session_id": state["session_id"],
        "task_id": state["task_id"],
        "project_mode": "migration",
        "source_stack": source_stack,
        "target_stack": target_stack,
    })

    config = ctx.router.route(TaskType.coding, model=state.get("model_name"))
    tools = ctx.registry.get_tools(ToolPhase.migration)
    executor = ToolExecutor(ctx.mcp, ctx.registry, event_callback=getattr(ctx, "post_event", None))

    active_manifest = ctx.active_manifest or FileManifest()
    active_manifest.scan_workspace(ws)
    ctx.active_manifest = active_manifest
    clean_tree = generate_clean_file_tree(ws)

    client = ClaudeToolClient(
        model=config.model,
        api_key=config.api_key,
        tools=tools,
        max_tokens=config.max_tokens,
        temperature=0.15,
        reality_guard=ctx.reality_guard,
        file_manifest=active_manifest,
        workspace_path=ws,
    )

    migration_msg = (
        f"## 🔄 CODEBASE MIGRATION DIRECTIVE (`{source_stack}` -> `{target_stack}`)\n\n"
        f"### Current Workspace File Tree:\n```\n{clean_tree}\n```\n\n"
        f"### User Migration Requirement:\n{prompt}\n\n"
        f"{plan_text}\n\n"
        "### MANDATORY MIGRATION PROTOCOL:\n"
        "1. **Legacy Archaeology**: Use `read_file` and `grep_search` to inspect existing legacy files on disk. "
        "Extract every entity field, business rule, validation, and API route.\n"
        "2. **Scaffold Target Stack**: Create the modern stack manifest (`package.json`, `requirements.txt`, `pom.xml`, `go.mod`, etc.) "
        "and directory structure using `write_file` or `write_files`.\n"
        "3. **Port Modules with 100% Parity**: Rewrite each legacy module into `{target_stack}` with complete business logic "
        "(zero `// TODO` or stub placeholders).\n"
        "4. **Parity Documentation**: Create `MIGRATION_REPORT.md` documenting legacy-to-modern file mappings and `README.md`.\n"
        "5. **Verify**: Run `check_syntax` or `install_and_build` to confirm the modernized stack builds cleanly.\n"
    )

    result = client.run_tool_loop(
        system=CODING_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": migration_msg}],
        tool_executor=executor,
        max_iterations=25,
        on_event=ctx.event_callback,
        clean_file_tree=clean_tree,
    )

    built_ok = bool(getattr(executor, "built_successfully", False))
    print(f"[Graph:MigrationCodeNode] Migration complete. {len(result.files_changed)} file(s) created/migrated.")

    return {
        "files_changed": result.files_changed,
        "final_text": result.final_text or f"Successfully migrated project from {source_stack} to {target_stack}.",
        "build_success": built_ok,
        "status": "coded",
    }


def batch_code_node(state: LangGraphState, ctx: NodeContext) -> dict[str, Any]:
    """Router node — dispatches to Migration, Custom Stack, or Sequential React pipeline."""
    techstack = state.get("techstack") or {}
    mode = (state.get("project_mode") or techstack.get("project_mode") or "greenfield").lower()
    if mode == "migration":
        return migration_code_node(state, ctx)
    if techstack.get("is_custom"):
        return custom_batch_code_node(state, ctx)
    return sequential_code_node(state, ctx)
