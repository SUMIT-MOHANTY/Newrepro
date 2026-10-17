"""Gatekeeper nodes — enforce pipeline invariants, zero-write detection, and anti-loop guards."""
from __future__ import annotations

from typing import Any

from agent.nodes.core.context import NodeContext
from agent.state import LangGraphState


def fail_node(state: LangGraphState, ctx: NodeContext) -> dict[str, Any]:
    """Hard gatekeeper failure node — called when code generation produced 0 files or build failed."""
    if state.get("build_error"):
        msg = f"Build failed after fix attempts: {state['build_error']}"
    elif not state.get("files_changed"):
        msg = "Code generation failed: No files were changed by the AI model. Halting pipeline to prevent empty deployment."
    else:
        msg = state.get("error") or "Pipeline execution failed."

    print(f"[Graph:FailNode] [FAIL] {msg[:200]}")
    ctx.post_event("session_failed", {
        "session_id": state["session_id"],
        "task_id": state["task_id"],
        "error": msg,
    })
    return {
        "status": "failed",
        "error": msg,
        "build_success": False,
    }
