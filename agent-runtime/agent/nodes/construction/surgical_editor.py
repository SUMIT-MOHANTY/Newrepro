"""Surgical editor node (edit_code_node) for targeted and follow-up modifications."""
from __future__ import annotations

from typing import Any

from agent.nodes.core.context import NodeContext
from agent.nodes.planning.followup_planner import follow_up_node
from agent.state import LangGraphState


def edit_code_node(state: LangGraphState, ctx: NodeContext) -> dict[str, Any]:
    """Backwards-compatible wrapper delegating to follow_up_node."""
    return follow_up_node(state, ctx)
