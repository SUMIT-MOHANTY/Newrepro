"""Generic MCP (Model Context Protocol) Client.

Connects to arbitrary MCP servers over stdio or SSE/HTTP, discovers their tools,
and executes tool calls using the standard JSON-RPC 2.0 protocol.

Protocol specification:
- https://spec.modelcontextprotocol.io/
"""
from __future__ import annotations

import json
import os
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from mcp.server import ToolResult


class GenericMCPClient:
    """Client for connecting to an external MCP server (stdio or HTTP)."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.name = config.get("name", "custom_mcp")
        self.transport = config.get("transport", "stdio")
        self.command = config.get("command")
        self.args = config.get("args") or []
        self.env = config.get("env") or {}
        self.url = config.get("url")
        self.headers = config.get("headers") or {}

        self._process: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._request_id = 0
        self._tools: list[dict[str, Any]] = []
        self._is_initialized = False

    def start(self) -> bool:
        """Start the MCP client connection and initialize the session."""
        if self.transport == "stdio":
            return self._start_stdio()
        elif self.transport in ("sse", "streamable-http"):
            return self._start_http()
        return False

    def list_tools(self) -> list[dict[str, Any]]:
        """Return the list of tools discovered from this MCP server."""
        if not self._is_initialized:
            self.start()
        return self._tools

    def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> ToolResult:
        """Call a specific tool on the MCP server."""
        if not self._is_initialized:
            if not self.start():
                return ToolResult(
                    success=False,
                    error=f"MCP server '{self.name}' is not running or failed to initialize",
                )

        if self.transport == "stdio":
            return self._call_stdio(tool_name, arguments)
        elif self.transport in ("sse", "streamable-http"):
            return self._call_http(tool_name, arguments)

        return ToolResult(success=False, error=f"Unsupported transport: {self.transport}")

    def close(self) -> None:
        """Terminate connection and process."""
        if self._process:
            try:
                self._process.terminate()
                self._process.wait(timeout=3)
            except Exception:
                try:
                    self._process.kill()
                except Exception:
                    pass
            self._process = None
            self._is_initialized = False

    # ------------------------------------------------------------------
    # stdio Implementation
    # ------------------------------------------------------------------

    def _start_stdio(self) -> bool:
        if not self.command:
            print(f"[GenericMCPClient] No command provided for stdio MCP '{self.name}'")
            return False

        cmd = [self.command] + self.args
        env = os.environ.copy()
        env.update(self.env)

        try:
            print(f"[GenericMCPClient] Spawning stdio MCP server '{self.name}': {' '.join(cmd)}")
            self._process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                env=env,
            )

            # 1. Send initialize request
            init_req = {
                "jsonrpc": "2.0",
                "id": self._next_id(),
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "vibecoding-agent", "version": "1.0"},
                },
            }
            resp = self._send_stdio_request(init_req)
            if not resp or "error" in resp:
                print(f"[GenericMCPClient] Initialize failed for '{self.name}': {resp}")
                return False

            # 2. Send initialized notification
            init_notify = {
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
            }
            self._send_stdio_notification(init_notify)

            # 3. Discover tools
            tools_req = {
                "jsonrpc": "2.0",
                "id": self._next_id(),
                "method": "tools/list",
                "params": {},
            }
            tools_resp = self._send_stdio_request(tools_req)
            if tools_resp and "result" in tools_resp:
                self._tools = tools_resp["result"].get("tools", [])
                print(f"[GenericMCPClient] Discovered {len(self._tools)} tool(s) from '{self.name}': "
                      f"{[t.get('name') for t in self._tools]}")
                self._is_initialized = True
                return True
            else:
                print(f"[GenericMCPClient] tools/list returned no result for '{self.name}': {tools_resp}")
                self._is_initialized = True
                return True

        except Exception as exc:
            print(f"[GenericMCPClient] Failed to start stdio MCP '{self.name}': {exc}")
            self.close()
            return False

    def _call_stdio(self, tool_name: str, arguments: dict[str, Any]) -> ToolResult:
        req = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments,
            },
        }
        resp = self._send_stdio_request(req)
        if not resp:
            return ToolResult(success=False, error=f"No response from MCP server '{self.name}'")

        if "error" in resp:
            err = resp["error"]
            err_msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
            return ToolResult(success=False, error=f"MCP Error: {err_msg}")

        result_data = resp.get("result", {})
        is_error = result_data.get("isError", False)

        # Extract text content
        content_items = result_data.get("content", [])
        text_outputs = []
        for item in content_items:
            if isinstance(item, dict) and item.get("type") == "text":
                text_outputs.append(item.get("text", ""))
            elif isinstance(item, str):
                text_outputs.append(item)

        output_str = "\n".join(text_outputs) if text_outputs else json.dumps(result_data)

        if is_error:
            return ToolResult(success=False, error=output_str or "Tool returned an error")

        return ToolResult(success=True, data=output_str)

    def _send_stdio_request(self, req: dict[str, Any], timeout: float = 30.0) -> dict[str, Any] | None:
        with self._lock:
            if not self._process or self._process.poll() is not None:
                return None

            try:
                line = json.dumps(req) + "\n"
                assert self._process.stdin is not None
                self._process.stdin.write(line)
                self._process.stdin.flush()

                # Read response line
                assert self._process.stdout is not None
                resp_line = self._process.stdout.readline()
                if not resp_line:
                    return None
                return json.loads(resp_line.strip())
            except Exception as exc:
                print(f"[GenericMCPClient] Request error on '{self.name}': {exc}")
                return None

    def _send_stdio_notification(self, notify: dict[str, Any]) -> None:
        with self._lock:
            if not self._process or self._process.poll() is not None:
                return
            try:
                line = json.dumps(notify) + "\n"
                assert self._process.stdin is not None
                self._process.stdin.write(line)
                self._process.stdin.flush()
            except Exception as exc:
                print(f"[GenericMCPClient] Notification error on '{self.name}': {exc}")

    # ------------------------------------------------------------------
    # HTTP / SSE Implementation
    # ------------------------------------------------------------------

    def _start_http(self) -> bool:
        if not self.url:
            print(f"[GenericMCPClient] No URL provided for HTTP MCP '{self.name}'")
            return False

        try:
            # Attempt to query tools/list endpoint or send JSON-RPC over POST
            req_data = json.dumps({
                "jsonrpc": "2.0",
                "id": self._next_id(),
                "method": "tools/list",
                "params": {},
            }).encode("utf-8")

            headers = {"Content-Type": "application/json", "Accept": "application/json"}
            headers.update(self.headers)

            req = urllib.request.Request(self.url, data=req_data, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if "result" in data:
                    self._tools = data["result"].get("tools", [])
                elif isinstance(data, list):
                    self._tools = data
                print(f"[GenericMCPClient] Discovered {len(self._tools)} tool(s) from HTTP '{self.name}'")
                self._is_initialized = True
                return True
        except Exception as exc:
            print(f"[GenericMCPClient] HTTP MCP '{self.name}' connection test: {exc}")
            # Mark initialized so calls can still be attempted
            self._is_initialized = True
            return True

    def _call_http(self, tool_name: str, arguments: dict[str, Any]) -> ToolResult:
        if not self.url:
            return ToolResult(success=False, error="No URL configured for HTTP MCP")

        try:
            req_data = json.dumps({
                "jsonrpc": "2.0",
                "id": self._next_id(),
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": arguments,
                },
            }).encode("utf-8")

            headers = {"Content-Type": "application/json", "Accept": "application/json"}
            headers.update(self.headers)

            req = urllib.request.Request(self.url, data=req_data, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if "error" in data:
                    return ToolResult(success=False, error=str(data["error"]))
                result = data.get("result", data)
                return ToolResult(success=True, data=result)
        except Exception as exc:
            return ToolResult(success=False, error=f"HTTP MCP call failed: {exc}")

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id
