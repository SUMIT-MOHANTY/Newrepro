"""LangGraph StateGraph Engine — Unified Multi-Mode (Greenfield, Brownfield, Migration) Pipeline."""
from __future__ import annotations

from typing import Literal
from langgraph.graph import END, START, StateGraph

from agent.nodes.core.context import NodeContext
from agent.nodes.core.gatekeepers import fail_node
from agent.nodes.core.git_release import delivery_node, git_push_node
from agent.nodes.discovery.discover_workspace import initialize_node
from agent.nodes.planning.enterprise_spec import plan_node
from agent.nodes.planning.followup_planner import follow_up_node
from agent.nodes.construction.batch_coder import (
    custom_batch_code_node,
    migration_code_node,
)
from agent.nodes.construction.surgical_editor import edit_code_node
from agent.nodes.legacy.frontend_ui_helper import sequential_code_node
from agent.nodes.verification.verification_nodes import (
    build_node,
    fix_node,
    preview_node,
    qa_verification_node,
    reconcile_deps_node,
)
from agent.state import LangGraphState


def route_entry(state: LangGraphState) -> Literal["initialize", "follow_up", "qa_verification"]:
    """Dynamic intent router supporting Build, Edit, Migration, and Standalone QA/Testing."""
    task_str = str(state.get("task_type", "")).lower()
    intent = str(state.get("execution_intent", "")).lower()

    # 1. Pure QA / Testing / Audit mode (No code generation — straight to live preview & functional testing)
    if intent == "qa_test_only" or any(k in task_str for k in ("qa_only", "test_only", "e2e_audit", "verify_only")):
        print("[GraphRouter] 🧪 Standalone QA / E2E Audit mode -> routing directly to qa_verification.")
        return "qa_verification"

    # 2. Surgical Edit / Bug Fix on existing code
    if any(k in task_str for k in ("follow_up", "edit", "bug", "question")):
        return "follow_up"

    # 3. Greenfield, Brownfield Feature Onboarding, or Migration
    return "initialize"


def route_after_initialize(state: LangGraphState) -> Literal["plan", "follow_up", "edit_code"]:
    """Route follow-up or surgical edit tasks directly; route Greenfield, Brownfield onboarding,
    and Migration tasks to architectural planning (plan).
    """
    task_str = str(state.get("task_type", "")).lower()
    if any(k in task_str for k in ("edit", "surgical")):
        return "edit_code"
    if any(k in task_str for k in ("follow_up", "bug", "question")):
        return "follow_up"
    return "plan"


def route_after_plan(
    state: LangGraphState,
) -> Literal["sequential_code", "custom_batch_code", "migration_code"]:
    """Route after plan_node based on project_mode and techstack."""
    techstack = state.get("techstack") or {}
    mode = (state.get("project_mode") or techstack.get("project_mode") or "greenfield").lower()

    if mode == "migration":
        print("[GraphRouter] 🔄 Migration mode -> routing to migration_code_node.")
        return "migration_code"
    if techstack.get("is_custom") or techstack.get("stack") not in ("react_vite", "react_vite_tailwind", "generic"):
        print(f"[GraphRouter] 🏗️ Custom stack '{techstack.get('stack')}' -> routing to custom_batch_code_node.")
        return "custom_batch_code"
    print("[GraphRouter] ⚡ React/Vite Greenfield -> routing to sequential_code_node.")
    return "sequential_code"


def route_code_result(state: LangGraphState) -> Literal["reconcile_deps", "fail"]:
    if not state.get("files_changed"):
        print("[GraphRouter] [FAIL] Zero files changed in code generation! Routing to fail_node.")
        return "fail"
    return "reconcile_deps"


def route_follow_up_result(state: LangGraphState) -> Literal["preview", "reconcile_deps", "fail"]:
    if state.get("build_success"):
        return "preview"
    if state.get("files_changed"):
        return "reconcile_deps"
    return "fail"


def route_build_result(state: LangGraphState) -> Literal["preview", "fix", "fail"]:
    if state.get("build_success"):
        return "preview"

    fix_attempts = state.get("fix_attempts", 0)
    current_sig = state.get("verification_signature") or ""
    prev_sig = state.get("previous_failure_signature") or ""

    if fix_attempts >= 2:
        return "fail"
    if current_sig and prev_sig and current_sig == prev_sig:
        return "fail"
    return "fix"


def route_preview_result(state: LangGraphState) -> Literal["git_push", "fix"]:
    """Route runtime browser or backend crashes directly into fix_node for hot-repair."""
    if state.get("preview_verified", True):
        return "git_push"

    fix_attempts = state.get("fix_attempts", 0)
    if fix_attempts >= 2:
        print("[GraphRouter] ⚠️ Max runtime fix attempts reached; completing with warnings.")
        return "git_push"

    print("[GraphRouter] 🔧 Live preview crash detected -> routing to fix_node for hot-repair.")
    return "fix"


def create_agent_graph(ctx: NodeContext) -> StateGraph:
    """Compile the LangGraph StateGraph with Greenfield, Brownfield, and Migration support."""
    builder = StateGraph(LangGraphState)

    builder.add_node("initialize", lambda s: initialize_node(s, ctx))
    builder.add_node("plan", lambda s: plan_node(s, ctx))
    builder.add_node("sequential_code", lambda s: sequential_code_node(s, ctx))
    builder.add_node("custom_batch_code", lambda s: custom_batch_code_node(s, ctx))
    builder.add_node("migration_code", lambda s: migration_code_node(s, ctx))
    builder.add_node("follow_up", lambda s: follow_up_node(s, ctx))
    builder.add_node("edit_code", lambda s: edit_code_node(s, ctx))
    builder.add_node("reconcile_deps", lambda s: reconcile_deps_node(s, ctx))
    builder.add_node("build", lambda s: build_node(s, ctx))
    builder.add_node("fix", lambda s: fix_node(s, ctx))
    builder.add_node("preview", lambda s: preview_node(s, ctx))
    builder.add_node("qa_verification", lambda s: qa_verification_node(s, ctx))
    builder.add_node("git_push", lambda s: git_push_node(s, ctx))
    builder.add_node("delivery", lambda s: delivery_node(s, ctx))
    builder.add_node("fail", lambda s: fail_node(s, ctx))

    builder.add_conditional_edges(
        START,
        route_entry,
        {
            "initialize": "initialize",
            "follow_up": "follow_up",
            "qa_verification": "qa_verification",
        },
    )

    builder.add_conditional_edges(
        "initialize",
        route_after_initialize,
        {"plan": "plan", "follow_up": "follow_up", "edit_code": "edit_code"},
    )

    builder.add_conditional_edges(
        "plan",
        route_after_plan,
        {
            "sequential_code": "sequential_code",
            "custom_batch_code": "custom_batch_code",
            "migration_code": "migration_code",
        },
    )

    for c_node in ("sequential_code", "custom_batch_code", "migration_code"):
        builder.add_conditional_edges(
            c_node,
            route_code_result,
            {"reconcile_deps": "reconcile_deps", "fail": "fail"},
        )

    for f_node in ("follow_up", "edit_code"):
        builder.add_conditional_edges(
            f_node,
            route_follow_up_result,
            {"preview": "preview", "reconcile_deps": "reconcile_deps", "fail": "fail"},
        )

    builder.add_edge("fail", END)
    builder.add_edge("reconcile_deps", "build")

    builder.add_conditional_edges(
        "build",
        route_build_result,
        {"preview": "preview", "fix": "fix", "fail": "fail"},
    )

    builder.add_edge("fix", "build")
    builder.add_conditional_edges(
        "preview",
        route_preview_result,
        {"git_push": "git_push", "fix": "fix"},
    )
    builder.add_edge("qa_verification", "delivery")
    builder.add_edge("git_push", "delivery")
    builder.add_edge("delivery", END)

    return builder.compile()
