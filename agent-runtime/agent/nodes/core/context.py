"""Core NodeContext dependency container for LangGraph execution nodes."""
from __future__ import annotations

from typing import Any, Callable, TYPE_CHECKING

from agent.model_router import ModelRouter
from agent.tools.tool_registry import ToolRegistry
from mcp.server import MCPServer
from runtime.reality_guard import AgentRealityGuard

if TYPE_CHECKING:
    from infrastructure.claude_tool_client import FileManifest


class NodeContext:
    """Dependency container passed to all LangGraph nodes."""

    def __init__(
        self,
        mcp: MCPServer,
        registry: ToolRegistry,
        router: ModelRouter,
        reality_guard: AgentRealityGuard | None = None,
        event_callback: Callable[[str, dict[str, Any]], None] | None = None,
        prior_conversation: list[dict[str, Any]] | None = None,
        prior_manifest: FileManifest | None = None,
    ) -> None:
        self.mcp = mcp
        self.registry = registry
        self.router = router
        self.reality_guard = reality_guard or AgentRealityGuard(getattr(mcp, "_workspace_path", "/workspace"))
        self.event_callback = event_callback
        self.active_manifest: FileManifest | None = None
        self.active_conversation: list[dict[str, Any]] = []
        # Prior session context — threaded from orchestrator for follow-up continuity
        self.prior_conversation: list[dict[str, Any]] = prior_conversation or []
        self.prior_manifest: FileManifest | None = prior_manifest

    def post_event(self, event_name: str, data: dict[str, Any]) -> None:
        if self.event_callback:
            try:
                self.event_callback(event_name, data)
            except Exception as e:
                print(f"[NodeContext] Error posting event '{event_name}': {e}")
