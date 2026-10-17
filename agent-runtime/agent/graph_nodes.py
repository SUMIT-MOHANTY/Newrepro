"""Deprecated — backward compatibility module re-exporting modular node implementations.

All nodes have been migrated to domain-specific packages:
- agent.nodes.core: context, gatekeepers, git_release
- agent.nodes.discovery: discover_workspace
- agent.nodes.planning: enterprise_spec, followup_planner
- agent.nodes.construction: batch_coder, surgical_editor
- agent.nodes.legacy: frontend_ui_helper
- agent.nodes.verification: verification_nodes
"""
from __future__ import annotations

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
    reconcile_local_imports,
    reconcile_deps_node,
    build_node,
    fix_node,
    preview_node,
    qa_verification_node,
)

__all__ = [
    "NodeContext",
    "fail_node",
    "delivery_node",
    "git_push_node",
    "initialize_node",
    "plan_node",
    "follow_up_node",
    "custom_batch_code_node",
    "migration_code_node",
    "edit_code_node",
    "sequential_code_node",
    "reconcile_local_imports",
    "reconcile_deps_node",
    "build_node",
    "fix_node",
    "preview_node",
    "qa_verification_node",
]
