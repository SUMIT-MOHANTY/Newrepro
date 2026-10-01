"""LangGraph StateGraph Engine — Multi-Stage Deterministic Agent Workflow Compiler.

Wires discrete graph nodes into a clean, deterministic pipeline:
1. Phase 1: Plan & Domain Research (Web search for UI, domain data, and KPIs)
2. Phase 2: Sequential 1-File-at-a-Time Code Generation:
   - For react_vite_tailwind:
     * sequential_code_node (Topologically ordered: mockData -> apiClient -> Components -> App.jsx)
     * Accumulated source context injection with 40k char buffer guard and get_generated_file
   - For custom tech stack:
     * custom_batch_code_node (Configs/Tree -> Application logic)
3. Phase 3: Pre-Build Dependency Reconciliation (reconcile_deps_node):
   - Statically audits workspace imports vs package.json
   - Updates package.json and runs npm install before build
4. Phase 4: Verification & Deployment:
   - static_scan_node (AST preflight <50ms)
   - build_node + bounded cyclic fix_node (max 2 attempts)
   - preview_node (live reverse-proxied preview)
"""
from __future__ import annotations

from typing import Literal

from langgraph.graph import END, START, StateGraph

from agent.graph_nodes import (
    NodeContext,
    build_node,
    custom_batch_code_node,
    edit_code_node,
    fail_node,
    fix_node,
    follow_up_node,
    git_push_node,
    initialize_node,
    plan_node,
    preview_node,
    reconcile_deps_node,
    sequential_code_node,
    static_scan_node,
)
from agent.state import LangGraphState


def route_entry(state: LangGraphState) -> Literal["initialize", "follow_up"]:
    """Route initial generation (Prompt 1) to initialize, or follow-up prompts (Prompt 2+)
    to dedicated follow_up node.
    """
    task_str = str(state.get("task_type", "")).lower()
    if any(k in task_str for k in ("follow_up", "edit", "bug", "question")):
        return "follow_up"
    return "initialize"


def route_initial_or_edit(state: LangGraphState) -> Literal["plan", "edit_code"]:
    """Route new greenfield project to plan (research & blueprint), or follow-up tasks directly to edit_code."""
    task_str = str(state.get("task_type", "")).lower()
    if any(k in task_str for k in ("follow_up", "edit", "bug", "question")):
        return "edit_code"
    return "plan"


def route_after_plan(state: LangGraphState) -> Literal["sequential_code", "custom_batch_code"]:
    """Route default react_vite_tailwind to sequential_code, or custom tech stack to custom generation."""
    techstack = state.get("techstack") or {}
    if techstack.get("is_custom"):
        return "custom_batch_code"
    return "sequential_code"


def route_code_result(state: LangGraphState) -> Literal["reconcile_deps", "fail"]:
    """HARD GATEKEEPER: Halt pipeline immediately if zero files were changed.
    
    NEVER compile or deploy the placeholder scaffold when the AI failed to write code.
    Used for initial Greenfield generation (Prompt 1).
    """
    files_changed = state.get("files_changed", [])
    if not files_changed:
        print("[GraphRouter] [FAIL] Gatekeeper: Zero files changed in code generation! Routing to fail_node.")
        return "fail"
    return "reconcile_deps"


def route_follow_up_result(state: LangGraphState) -> Literal["preview", "reconcile_deps", "fail"]:
    """Route follow-up node result for Prompt 2+.
    
    1. If the build succeeded during this follow-up session, route directly to preview.
    2. If files were modified but build hasn't run or verified yet, route to reconcile_deps -> build -> preview.
    3. Only route to fail if zero files changed and no build succeeded.
    """
    built_ok = bool(state.get("build_success", False))
    files_changed = state.get("files_changed", [])

    if built_ok:
        print("[GraphRouter] [OK] Follow-up task verified / built successfully in this session. Routing to preview.")
        return "preview"

    if files_changed:
        print(f"[GraphRouter] Follow-up changed {len(files_changed)} file(s) without build verification. Routing to reconcile_deps for build.")
        return "reconcile_deps"

    print("[GraphRouter] [FAIL] Follow-up changed 0 files and no build verified. Routing to fail_node.")
    return "fail"



def route_build_result(state: LangGraphState) -> Literal["preview", "fix", "fail"]:
    """Route successful build to preview, or failed build to self-healing fix loop (max 2 attempts), or fail."""
    if state.get("build_success"):
        return "preview"

    if state.get("fix_attempts", 0) < 2:
        return "fix"

    print("[GraphRouter] [FAIL] Exceeded max fix attempts (2) and build still failing — routing to fail_node.")
    return "fail"


def create_agent_graph(ctx: NodeContext) -> StateGraph:
    """Compile the LangGraph StateGraph with all nodes and deterministic edges."""
    builder = StateGraph(LangGraphState)

    # 1. Register discrete nodes
    # Prompt 1: Initial Greenfield Generation Nodes (preserved 100% intact)
    builder.add_node("initialize", lambda s: initialize_node(s, ctx))
    builder.add_node("plan", lambda s: plan_node(s, ctx))
    builder.add_node("sequential_code", lambda s: sequential_code_node(s, ctx))
    builder.add_node("custom_batch_code", lambda s: custom_batch_code_node(s, ctx))
    builder.add_node("fail", lambda s: fail_node(s, ctx))

    # Prompt 2+: Dedicated Follow-up Pipeline Nodes (bypasses techstack AI call)
    builder.add_node("follow_up", lambda s: follow_up_node(s, ctx))
    builder.add_node("edit_code", lambda s: edit_code_node(s, ctx))

    # Pre-build reconciliation & Verification Nodes
    builder.add_node("reconcile_deps", lambda s: reconcile_deps_node(s, ctx))
    # builder.add_node("static_scan", lambda s: static_scan_node(s, ctx))  # Bypassed per user request
    builder.add_node("build", lambda s: build_node(s, ctx))
    builder.add_node("fix", lambda s: fix_node(s, ctx))
    builder.add_node("preview", lambda s: preview_node(s, ctx))

    # Git Push Node — auto-commit and push after successful task completion
    builder.add_node("git_push", lambda s: git_push_node(s, ctx))

    # 2. Wire edges
    # START conditional branch: Initial generation (Prompt 1) vs Dedicated Follow-Up (Prompt 2+)
    builder.add_conditional_edges(
        START,
        route_entry,
        {
            "initialize": "initialize",
            "follow_up": "follow_up",
        },
    )

    # Initial pipeline (Prompt 1) — always goes from initialize directly to plan
    builder.add_edge("initialize", "plan")

    # Greenfield routing: Phased React vs Custom Stack
    builder.add_conditional_edges(
        "plan",
        route_after_plan,
        {
            "sequential_code": "sequential_code",
            "custom_batch_code": "custom_batch_code",
        },
    )

    # Gatekeeper routing: verify files were written before dependency reconciliation
    builder.add_conditional_edges(
        "sequential_code",
        route_code_result,
        {
            "reconcile_deps": "reconcile_deps",
            "fail": "fail",
        },
    )

    builder.add_conditional_edges(
        "custom_batch_code",
        route_code_result,
        {
            "reconcile_deps": "reconcile_deps",
            "fail": "fail",
        },
    )

    builder.add_conditional_edges(
        "follow_up",
        route_follow_up_result,
        {
            "preview": "preview",
            "reconcile_deps": "reconcile_deps",
            "fail": "fail",
        },
    )

    builder.add_conditional_edges(
        "edit_code",
        route_follow_up_result,
        {
            "preview": "preview",
            "reconcile_deps": "reconcile_deps",
            "fail": "fail",
        },
    )


    # Gatekeeper failure exits immediately
    builder.add_edge("fail", END)

    # Pre-build & verification flow (static_scan bypassed to achieve fast output)
    builder.add_edge("reconcile_deps", "build")
    # builder.add_edge("reconcile_deps", "static_scan")
    # builder.add_edge("static_scan", "build")

    builder.add_conditional_edges(
        "build",
        route_build_result,
        {
            "preview": "preview",
            "fix": "fix",
            "fail": "fail",
        },
    )

    # Cyclic self-healing edge
    builder.add_edge("fix", "build")

    # Preview → Git Push → END (auto-commit + push after every successful task)
    builder.add_edge("preview", "git_push")
    builder.add_edge("git_push", END)

    return builder.compile()

