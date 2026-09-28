"""MCPServer — the in-process MCP server that enforces policies before
dispatching tool calls.

Architecture §8:
- AGENT → MCP CLIENT → MCP SERVER → Policies → Tool Registry → Sandbox
- The AI never calls tools directly; every call passes through here.
- Policy violations are logged with full context and raise ToolDeniedError.
- In V1 this is an in-process Python object (not HTTP) for simplicity.
  The interface is identical whether it's in-process or over HTTP, making
  the future upgrade seamless.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


class ToolDeniedError(Exception):
    """Raised when a tool call is blocked by policy."""


class ToolNotFoundError(Exception):
    """Raised when the requested tool module/name doesn't exist."""


@dataclass
class ToolResult:
    """Uniform return type from every tool call."""
    success: bool
    data: Any = None           # structured data on success
    error: str | None = None   # human-readable error on failure
    duration_ms: int = 0
    denied: bool = False       # True if blocked by policy
    denial_reason: str | None = None


class MCPServer:
    """Policy-enforcing tool dispatcher (§8).

    Tool modules are registered by name. The Orchestrator/Coder/Planner
    call mcp.call_tool(module, tool, args) and get a ToolResult back.
    They never call tool implementations directly.
    """

    def __init__(self, workspace_path: str) -> None:
        self._workspace_path = workspace_path
        self._modules: dict[str, Any] = {}
        self._custom_mcp_clients: dict[str, Any] = {}
        self._discovered_tools: list[dict[str, Any]] = []
        self._call_log: list[dict] = []     # in-memory call log (stdout in prod)
        self._register_modules()
        self._load_custom_mcps()

    def _register_modules(self) -> None:
        from mcp.filesystem_tools import FilesystemTools
        from mcp.git_tools import GitTools
        from mcp.execution_tools import ExecutionTools
        from mcp.build_tools import BuildTools
        from mcp.search_tools import SearchTools

        self._modules["filesystem"] = FilesystemTools(self._workspace_path)
        self._modules["git"] = GitTools(self._workspace_path)
        self._modules["execution"] = ExecutionTools(self._workspace_path)
        self._modules["build"] = BuildTools(self._workspace_path)
        self._modules["search"] = SearchTools(self._workspace_path)

        # Opt-in modules — only register if configured
        import os
        if os.environ.get("WEB_SEARCH_ENABLED", "").lower() == "true":
            from mcp.web_search_tools import WebSearchTools
            self._modules["web_search"] = WebSearchTools()
            print("[MCP] Web search tools enabled")

    def _load_custom_mcps(self) -> None:
        """Load external MCP servers configured via MCP_SERVERS environment variable."""
        import json
        import os
        from mcp.generic_client import GenericMCPClient

        mcp_servers_raw = os.environ.get("MCP_SERVERS", "")
        if not mcp_servers_raw:
            return

        try:
            mcp_configs = json.loads(mcp_servers_raw)
            if not isinstance(mcp_configs, list):
                return

            for cfg in mcp_configs:
                name = cfg.get("name", "").strip()
                transport = cfg.get("transport", "")
                if not name or transport == "builtin" or name.lower() == "github":
                    continue

                # Clean module identifier
                clean_mod_name = f"mcp_{name.lower().replace(' ', '_').replace('-', '_')}"
                client = GenericMCPClient(cfg)
                if client.start():
                    self._custom_mcp_clients[clean_mod_name] = client
                    tools = client.list_tools()
                    for t in tools:
                        t["_mcp_module"] = clean_mod_name
                        self._discovered_tools.append(t)
                    print(f"[MCP] Registered external MCP '{name}' as '{clean_mod_name}' with {len(tools)} tool(s)")
                else:
                    print(f"[MCP] Warning: Failed to connect to external MCP '{name}'")
        except Exception as exc:
            print(f"[MCP] Error loading MCP_SERVERS: {exc}")

    def get_discovered_tools(self) -> list[dict[str, Any]]:
        """Return dynamic tool definitions discovered from external MCP servers."""
        return self._discovered_tools

    def call_tool(self, module: str, tool: str, args: dict[str, Any]) -> ToolResult:
        """Dispatch a tool call through the policy layer.

        This is the ONLY entry point for all tool calls. All policy checks,
        logging and timing happen here.
        """
        start = time.time()
        log_entry = {
            "module": module, "tool": tool,
            "args_summary": str(args)[:200],  # never log full file contents
            "status": "pending",
        }

        # Check if this is an external custom MCP tool call
        if module in self._custom_mcp_clients:
            client = self._custom_mcp_clients[module]
            try:
                result = client.call_tool(tool, args)
                result.duration_ms = int((time.time() - start) * 1000)
                log_entry["status"] = "succeeded" if result.success else "failed"
            except Exception as exc:
                result = ToolResult(
                    success=False, error=str(exc),
                    duration_ms=int((time.time() - start) * 1000),
                )
                log_entry["status"] = "failed"
            self._log(log_entry)
            return result

        # 1. Check module exists
        module_obj = self._modules.get(module)
        if module_obj is None:
            result = ToolResult(success=False, error=f"Unknown tool module: {module}")
            log_entry["status"] = "not_found"
            self._log(log_entry)
            return result

        # 2. Check tool method exists on module
        tool_fn = getattr(module_obj, tool, None)
        if tool_fn is None:
            result = ToolResult(success=False, error=f"Unknown tool: {module}.{tool}")
            log_entry["status"] = "not_found"
            self._log(log_entry)
            return result

        # 3. Policy check
        try:
            self._enforce_policy(module, tool, args)
        except ToolDeniedError as exc:
            result = ToolResult(
                success=False, denied=True, denial_reason=str(exc),
                error=f"Tool denied by policy: {exc}",
                duration_ms=int((time.time() - start) * 1000),
            )
            log_entry.update({"status": "denied", "denial_reason": str(exc)})
            self._log(log_entry)
            return result

        # 4. Execute
        try:
            result = tool_fn(**args)
            if not isinstance(result, ToolResult):
                result = ToolResult(success=True, data=result)
            result.duration_ms = int((time.time() - start) * 1000)
            log_entry["status"] = "succeeded" if result.success else "failed"
        except Exception as exc:
            result = ToolResult(
                success=False, error=str(exc),
                duration_ms=int((time.time() - start) * 1000),
            )
            log_entry["status"] = "failed"

        self._log(log_entry)
        return result

    def _enforce_policy(self, module: str, tool: str, args: dict) -> None:
        """Gate all policy checks. Raises ToolDeniedError on violation.

        §8.3 policy examples:
        - Read /workspace/src/App.jsx → ALLOW (inside workspace)
        - Read /backend/app/auth.py → DENY (platform source)
        - Run rm -rf / → DENY (destructive)
        """
        from runtime.sandbox import Sandbox
        sandbox = Sandbox(self._workspace_path)

        # Filesystem path checks
        if module == "filesystem" and tool in ("read_file", "write_file", "delete_file",
                                                "list_directory", "file_exists", "get_file_stats"):
            path = args.get("path", "")
            if path and not sandbox.is_within_workspace(str(path)):
                raise ToolDeniedError(f"Path outside workspace not allowed: {path}")

        # Search path checks
        if module == "search" and tool in ("grep_search", "find_and_replace"):
            path = args.get("path", "")
            if path and not sandbox.is_within_workspace(str(path)):
                raise ToolDeniedError(f"Search path outside workspace not allowed: {path}")

        # Execution command checks
        if module == "execution" and tool == "run_command":
            cmd = args.get("command", [])
            if cmd:
                self._check_command_policy(cmd)

        # Research is opt-in
        if module == "research":
            import os
            if not os.environ.get("RESEARCH_TOOLS_ENABLED", "").lower() == "true":
                raise ToolDeniedError("Research tools are disabled. Set RESEARCH_TOOLS_ENABLED=true.")

    def _check_command_policy(self, command: list) -> None:
        """Validate the command against the allowlist (§8.3)."""
        from mcp.execution_tools import ALLOWED_COMMANDS, DENIED_PATTERNS
        if not command:
            raise ToolDeniedError("Empty command")
        executable = str(command[0]).split("/")[-1].split("\\\\")[-1]  # basename only
        if executable not in ALLOWED_COMMANDS:
            raise ToolDeniedError(f"Command not in allowlist: {executable}. "
                                  f"Allowed: {ALLOWED_COMMANDS}")
        cmd_str = " ".join(str(c) for c in command)
        for pattern in DENIED_PATTERNS:
            if pattern.lower() in cmd_str.lower():
                raise ToolDeniedError(f"Command matches denied pattern: {pattern}")

    def _log(self, entry: dict) -> None:
        """Structured log to stdout (Docker captures this as container logs)."""
        self._call_log.append(entry)
        status = entry.get("status", "?")
        module = entry.get("module", "?")
        tool = entry.get("tool", "?")
        print(f"[MCP] {status.upper():10s} | {module}.{tool} | {entry.get('args_summary','')[:80]}")
