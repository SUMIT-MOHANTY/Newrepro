"""ToolExecutor — executes Claude's native tool calls through the MCP server.

When Claude responds with tool_use content blocks, this class:
1. Maps the tool name to the corresponding MCP module + method
2. Executes it through MCPServer.call_tool() (which enforces sandbox policies)
3. Returns a properly formatted tool_result content block for the next API call

This is the bridge between Claude's tool-use protocol and our MCP tool infrastructure.
"""
from __future__ import annotations

import os
import json
from typing import Any, TYPE_CHECKING

from agent.tools.tool_registry import ToolRegistry

if TYPE_CHECKING:
    from mcp.server import MCPServer


def _safe_print(msg: str) -> None:
    """Print message safely on consoles that might fail on unicode emojis (e.g. Windows cp1252)."""
    try:
        print(msg)
    except UnicodeEncodeError:
        try:
            print(msg.encode("ascii", errors="replace").decode("ascii"))
        except Exception:
            pass
    except Exception:
        pass


class ToolExecutor:
    """Executes tool calls from Claude's tool_use response blocks via MCP."""

    def __init__(self, mcp: "MCPServer", registry: ToolRegistry, event_callback: Optional[Any] = None) -> None:
        self._mcp = mcp
        self._registry = registry
        self._event_callback = event_callback
        self._files_changed: list[str] = []
        self._tool_call_count: int = 0
        self._built_successfully: bool = False
        self._call_history: list[str] = []
        # Files blocked from patch tools after a rollback — require write_file only
        self._rollback_blocked_files: set[str] = set()

    @property
    def files_changed(self) -> list[str]:
        """Files that were created or modified during this executor's lifetime."""
        return list(set(self._files_changed))

    @property
    def built_successfully(self) -> bool:
        """True if the application was built successfully AFTER all file edits in this session."""
        return self._built_successfully

    @property
    def rollback_blocked_files(self) -> set[str]:
        """Normalized relative paths of files blocked from patch tools (require write_file after rollback)."""
        return self._rollback_blocked_files

    @property
    def tool_call_count(self) -> int:
        return self._tool_call_count

    def execute(self, tool_name: str, tool_input: dict[str, Any]) -> dict[str, Any]:
        """Execute a single tool call and return the result for Claude.

        Returns a dict with 'content' suitable for an Anthropic tool_result message.
        """
        self._tool_call_count += 1

        # Loop detector: check for identical repeated tool calls
        call_key = f"{tool_name}:{json.dumps(tool_input, sort_keys=True)}"
        self._call_history.append(call_key)
        if len(self._call_history) >= 3:
            if self._call_history[-1] == self._call_history[-2] == self._call_history[-3]:
                return self._error_result(
                    f"Loop Protection Activated: You have called '{tool_name}' with the exact same parameters 3 times in a row. "
                    "Do NOT call this again with identical arguments. Please inspect the code directly using read_file or change your approach."
                )

        # Handle batch write_files specially — write each file through MCP
        if tool_name == "write_files":
            return self._execute_batch_write(tool_input)

        # Handle conversation history retrieval directly from disk transcript
        if tool_name == "get_conversation_history":
            return self._execute_get_conversation_history(tool_input)

        # Handle past fixes retrieval directly from disk history
        if tool_name == "get_past_fixes":
            return self._execute_get_past_fixes(tool_input)

        # Handle product specification updates directly
        if tool_name == "update_product_spec":
            return self._execute_update_product_spec(tool_input)

        # Handle plan submission directly
        if tool_name == "submit_plan":
            return self._execute_submit_plan(tool_input)

        mapping = self._registry.get_mcp_mapping(tool_name)
        if mapping is None:
            return self._error_result(f"Unknown tool: {tool_name}")

        mcp_module, mcp_method = mapping

        workspace_path = getattr(self._mcp, "_workspace_path", None) or os.environ.get("WORKSPACE_PATH", "/workspace")
        pre_patch_snapshots: dict[str, str] = {}

        # ── Rollback Block Guard ─────────────────────────────────────────────
        # After a rollback fires for a file, patch tools (replace_file_content /
        # batch_replace_file_content / find_and_replace) are blocked for that file
        # until write_file is used to provide a complete, validated replacement.
        # This prevents the AI from looping through repeated failed patch attempts.
        if tool_name in ("replace_file_content", "find_and_replace", "batch_replace_file_content"):
            blocked_paths_in_call: list[str] = []
            if tool_name in ("replace_file_content", "find_and_replace"):
                p = tool_input.get("path", "") if isinstance(tool_input, dict) else ""
                if p:
                    norm_p = p.replace(str(workspace_path), "").replace("\\", "/").lstrip("/")
                    if norm_p in self._rollback_blocked_files:
                        blocked_paths_in_call.append(norm_p)
            elif tool_name == "batch_replace_file_content":
                edits_check = []
                if isinstance(tool_input, dict):
                    edits_check = tool_input.get("edits", [])
                elif isinstance(tool_input, list):
                    edits_check = tool_input
                for e in edits_check:
                    if isinstance(e, dict):
                        p = e.get("path") or e.get("file_path") or e.get("file")
                        if p:
                            norm_p = p.replace(str(workspace_path), "").replace("\\", "/").lstrip("/")
                            if norm_p in self._rollback_blocked_files and norm_p not in blocked_paths_in_call:
                                blocked_paths_in_call.append(norm_p)

            if blocked_paths_in_call:
                blocked_list = ", ".join(f"`{p}`" for p in blocked_paths_in_call)
                return {
                    "type": "tool_result",
                    "content": (
                        f"🚫 PATCH BLOCKED: {blocked_list} — these files were rolled back due to a syntax error.\n\n"
                        "You MUST use `write_file` with the COMPLETE, valid file content.\n"
                        "`replace_file_content` and `batch_replace_file_content` are BLOCKED for these files until `write_file` succeeds.\n\n"
                        "Do NOT read more files first. You already have the complete content in the Active Inspected Files cache above.\n"
                        "Write the entire corrected file NOW using `write_file`."
                    ),
                    "is_error": True,
                }

        # Snapshot file(s) before patch to allow clean, instant auto-rollback if syntax check fails
        if tool_name in ("replace_file_content", "find_and_replace"):
            p = tool_input.get("path", "") if isinstance(tool_input, dict) else ""
            if p:
                norm_p = p.replace(str(workspace_path), "").replace("\\", "/").lstrip("/")
                full_p = os.path.join(str(workspace_path), norm_p)
                if os.path.isfile(full_p):
                    try:
                        with open(full_p, "r", encoding="utf-8", errors="replace") as f:
                            pre_patch_snapshots[full_p] = f.read()
                    except Exception:
                        pass
        elif tool_name == "batch_replace_file_content":
            edits = []
            if isinstance(tool_input, dict):
                edits = tool_input.get("edits", [])
            elif isinstance(tool_input, list):
                edits = tool_input
            for e in edits:
                if isinstance(e, dict):
                    p = e.get("path") or e.get("file_path") or e.get("file")
                    if p:
                        norm_p = p.replace(str(workspace_path), "").replace("\\", "/").lstrip("/")
                        full_p = os.path.join(str(workspace_path), norm_p)
                        if full_p not in pre_patch_snapshots and os.path.isfile(full_p):
                            try:
                                with open(full_p, "r", encoding="utf-8", errors="replace") as f:
                                    pre_patch_snapshots[full_p] = f.read()
                            except Exception:
                                pass

        # Translate tool input args to MCP call args
        mcp_args = self._translate_args(tool_name, mcp_module, mcp_method, tool_input)

        # Execute through MCP (sandbox policies enforced here)
        result = self._mcp.call_tool(mcp_module, mcp_method, mcp_args)

        # Track file changes
        self._track_changes(tool_name, tool_input, result)

        # Format result for Claude
        if result.denied:
            return self._error_result(
                f"Tool denied by security policy: {result.denial_reason}"
            )

        if not result.success:
            # Auto-retry: if push_files fails on empty repo, seed with create_or_update_file first
            if (
                tool_name == "push_files"
                and result.error
                and "empty" in str(result.error).lower()
                and tool_input.get("files")
            ):
                first_file = tool_input["files"][0]
                owner, repo = self._parse_repo_from_push(tool_input)
                if owner and repo:
                    seed_result = self._mcp.call_tool(
                        "mcp_github",
                        "create_or_update_file",
                        {
                            "owner": owner,
                            "repo": repo,
                            "path": first_file["path"],
                            "content": first_file["content"],
                            "message": tool_input.get("message", "Initial commit"),
                            "branch": tool_input.get("branch", "main"),
                        },
                    )
                    if seed_result.success:
                        # Retry push_files with remaining files
                        remaining = tool_input["files"][1:]
                        if remaining:
                            retry_input = {**tool_input, "files": remaining}
                            retry_args = self._translate_args(
                                tool_name, mcp_module, mcp_method, retry_input
                            )
                            result = self._mcp.call_tool(
                                mcp_module, mcp_method, retry_args
                            )
                            if result.success:
                                return self._success_result(result.data)
                        else:
                            return self._success_result(
                                seed_result.data or "Successfully pushed to empty repository"
                            )

            if tool_name in ("replace_file_content", "find_and_replace", "batch_replace_file_content"):
                err_msg = str(result.error or "Target content not found")
                p = tool_input.get("path", "") if isinstance(tool_input, dict) else ""
                return {
                    "type": "tool_result",
                    "content": (
                        f"Error executing {tool_name} for `{p}`: {err_msg}\n\n"
                        f"The file on disk has NOT been modified.\n"
                        f"RECOMMENDATION: If matching exact lines or indentation is difficult, or if wrapping components across the file, please use `write_file` to output the complete, updated file directly."
                    ),
                    "is_error": True,
                }

            return self._error_result(result.error or "Tool execution failed")

        paths_to_check: list[str] = []
        had_soft_warning = False  # tracks if any non-fatal validator notice fired (must be at same scope as paths_to_check)
        # Validate syntax and truncation for modified files
        if result.success and tool_name in ("write_file", "replace_file_content", "find_and_replace", "batch_replace_file_content"):
            if tool_name in ("write_file", "replace_file_content", "find_and_replace"):
                p = tool_input.get("path", "") if isinstance(tool_input, dict) else ""
                if p:
                    paths_to_check.append(p)

            elif tool_name == "batch_replace_file_content":
                edits = []
                if isinstance(tool_input, dict):
                    edits = tool_input.get("edits", [])
                elif isinstance(tool_input, list):
                    edits = tool_input
                for e in edits:
                    if isinstance(e, dict):
                        p = e.get("path") or e.get("file_path") or e.get("file")
                        if p and p not in paths_to_check:
                            paths_to_check.append(p)

            for path in paths_to_check:
                try:
                    from runtime.syntax_validator import SyntaxValidator
                    from pathlib import Path
                    validator = SyntaxValidator(workspace_path)
                    rel_path = path.replace(str(workspace_path), "").replace("\\", "/").lstrip("/")

                    # FIX: Call _validate_content directly to skip the slow workspace-wide
                    # cross-import scan (validate_files() calls that and takes 40-60s).
                    # Per-file syntax check is all we need here; cross-import analysis stays in build_fix.
                    full_disk_path = Path(str(workspace_path)) / rel_path
                    file_content = ""
                    try:
                        file_content = full_disk_path.read_text(encoding="utf-8", errors="replace")
                    except Exception:
                        pass

                    err_item = None
                    if file_content:
                        err_item = validator._validate_content(full_disk_path, rel_path, file_content)

                    file_errs = [err_item] if err_item else []

                    if file_errs:
                        err_item = file_errs[0]
                        err_msg = str(err_item.get("error", "Syntax error"))
                        line_num = err_item.get("line", 0)
                        # Only reject if there is an actual syntax parse failure (not cross-import warnings)
                        # Includes duplicate declarations (e.g. `HashRouter has already been declared`)
                        # which are guaranteed build breakers (Fix #5: block task completion on them).
                        #
                        # FIX: Expanded keyword list to catch:
                        #   - "JSX syntax error: Unexpected closing X tag does not match opening Y tag"
                        #     (produced by esbuild/babel parser via _parser_check → returned as
                        #      "JSX syntax error: <esbuild msg>" in syntax_validator._parser_check)
                        #   - Heuristic truncation / conflict marker errors
                        # Previously these fell through to the "Post-write notice" branch → AI saw
                        # syntax_status=PASSED and continued making changes despite the real error.
                        is_actual_syntax = any(
                            k in err_msg.lower() for k in (
                                "syntaxerror", "unexpected token", "unclosed", "unterminated",
                                "unexpected end", "unexpected eof", "already been declared",
                                "duplicate declaration", "redeclaration",
                                # JSX tag-mismatch errors from esbuild / babel parser
                                "jsx syntax error", "does not match", "unexpected closing",
                                # Heuristic truncation / conflict marker errors
                                "truncated", "conflict marker", "ai patch",
                                # Generic "syntax error:" prefix from any parser
                                "syntax error:",
                            )
                        )
                        if is_actual_syntax:
                            msg = f"⚠️ Syntax error detected in `{rel_path}` (line {line_num}): {err_msg}"
                            _safe_print(f"[ToolExecutor] {msg}")

                            # Auto-rollback to pre-patch snapshot
                            rolled_back = False
                            if pre_patch_snapshots:
                                for full_p, orig_c in pre_patch_snapshots.items():
                                    try:
                                        with open(full_p, "w", encoding="utf-8") as f:
                                            f.write(orig_c)
                                        _safe_print(f"[ToolExecutor] 🔄 Auto-rolled back {full_p} to pre-patch clean state due to syntax error.")
                                        rolled_back = True
                                    except Exception as rb_exc:
                                        _safe_print(f"[ToolExecutor] Rollback failed for {full_p}: {rb_exc}")

                                # Remove rolled-back files from self._files_changed
                                for full_p in pre_patch_snapshots.keys():
                                    norm_fp = full_p.replace(str(workspace_path), "").replace("\\", "/").lstrip("/")
                                    for changed_p in list(self._files_changed):
                                        norm_ch = changed_p.replace(str(workspace_path), "").replace("\\", "/").lstrip("/")
                                        if norm_ch == norm_fp or changed_p == full_p:
                                            self._files_changed.remove(changed_p)

                                    # Block this file from further patch tools — require write_file
                                    norm_rb = full_p.replace(str(workspace_path), "").replace("\\", "/").lstrip("/")
                                    self._rollback_blocked_files.add(norm_rb)
                                    _safe_print(f"[ToolExecutor] 🚫 Patch-blocked `{norm_rb}` — write_file required.")

                            rollback_note = (
                                "CRITICAL SAFETY ACTION: The file on disk was AUTOMATICALLY ROLLED BACK to its previous valid state.\n"
                                "Your partial patch left unclosed tags or syntax errors.\n\n"
                                "🚫 PATCH TOOLS ARE NOW BLOCKED FOR THIS FILE.\n"
                                "You MUST use `write_file` with the COMPLETE, valid file content.\n"
                                "Do NOT use replace_file_content or batch_replace_file_content — they are blocked.\n"
                                "Do NOT read more files. You already have the file content in Active Inspected Files cache.\n"
                                "Write the entire corrected file immediately using `write_file`."
                                if rolled_back else
                                f"Please provide the corrected code for `{rel_path}` using write_file."
                            )

                            return {
                                "type": "tool_result",
                                "content": (
                                    f"{msg}\n\n"
                                    f"SYNTAX ERROR: {err_msg}\n"
                                    f"Line: {line_num}\n\n"
                                    f"{rollback_note}"
                                ),
                                "is_error": True,
                                "truncation_detected": True,
                                "file": rel_path,
                                "line": line_num,
                                "rolled_back": rolled_back,
                            }
                        else:
                            # Non-syntax warning (e.g. pending cross-import) — log only, do not reject write.
                            # FIX: Track that a soft warning fired so we do NOT emit a false PASSED banner.
                            had_soft_warning = True
                            _safe_print(f"[ToolExecutor] Post-write notice for `{rel_path}`: {err_msg}")
                except Exception as val_exc:
                    _safe_print(f"[ToolExecutor] Syntax validation note: {val_exc}")

        # Unblock a file that was previously rollback-blocked when write_file succeeds
        write_unblocked: list[str] = []
        if tool_name == "write_file" and result.success:
            p = tool_input.get("path", "") if isinstance(tool_input, dict) else ""
            if p:
                norm_p = p.replace(str(workspace_path), "").replace("\\", "/").lstrip("/")
                if norm_p in self._rollback_blocked_files:
                    self._rollback_blocked_files.discard(norm_p)
                    write_unblocked.append(norm_p)
                    _safe_print(f"[ToolExecutor] ✅ write_file resolved rollback-blocked `{norm_p}`. Patch tools re-enabled.")

        if write_unblocked:
            unblock_notice = (
                f"\n\n[ToolExecutor: ✅ write_file successfully resolved rollback-blocked {', '.join(f'`{p}`' for p in write_unblocked)}. "
                "Rollback block lifted. Patch tools re-enabled.]"
            )
            if isinstance(result.data, str):
                result.data += unblock_notice
            elif isinstance(result.data, dict):
                result.data["unblock_notice"] = unblock_notice.strip()

        # Build clean success message with syntax validation confirmation.
        # FIX: Do NOT emit PASSED banner when a soft (non-fatal) validator warning fired —
        # that would falsely assure the AI that everything is fine.
        data_content = result.data
        if paths_to_check and result.success and not had_soft_warning:
            verified_paths = ", ".join(f"`{p.replace(str(workspace_path), '').replace('\\', '/').lstrip('/')}`" for p in paths_to_check)
            syntax_confirmation = (
                f"\n\n[SyntaxValidator: ✅ Syntax check PASSED for {verified_paths}. "
                "No parse errors or unclosed tags. Proceed to the next task in your checklist, "
                "or call install_and_build() to test the application.]"
            )
            if isinstance(data_content, str):
                data_content += syntax_confirmation
            elif isinstance(data_content, dict):
                data_content["syntax_status"] = "PASSED"
                data_content["validation_notice"] = syntax_confirmation.strip()

        success_result = self._success_result(data_content)
        if write_unblocked:
            success_result["write_unblocked"] = write_unblocked
        return success_result



    def _translate_args(
        self,
        tool_name: str,
        mcp_module: str,
        mcp_method: str,
        tool_input: dict[str, Any],
    ) -> dict[str, Any]:
        """Translate Claude's tool input into MCP call arguments.

        Most tools pass through directly, but some need arg name mapping.
        """
        # Git tools have no args or different arg names
        if tool_name == "git_status":
            return {}
        if tool_name == "git_diff":
            return {}
        if tool_name == "git_commit":
            return {"message": tool_input.get("message", "Auto-commit by agent")}

        # Default: pass through directly
        return tool_input

    @staticmethod
    def _parse_repo_from_push(tool_input: dict) -> tuple[str, str]:
        """Extract (owner, repo) from push_files input.

        Handles: owner/repo string, full URL, or separate owner+repo params.
        """
        import urllib.parse

        # Case 1: separate owner + repo params (GitHub MCP format)
        owner = tool_input.get("owner", "")
        repo = tool_input.get("repo", "")
        if owner and repo:
            return owner, repo.removesuffix(".git")

        # Case 2: combined repo string (URL or owner/repo)
        repo_str = repo or ""
        if not repo_str:
            return "", ""
        if "/" in repo_str and ("github.com" in repo_str or repo_str.startswith("http")):
            parsed = urllib.parse.urlparse(repo_str)
            parts = [p for p in parsed.path.strip("/").split("/") if p]
            if len(parts) >= 2:
                return parts[0], parts[1].removesuffix(".git")
        parts = repo_str.split("/")
        if len(parts) == 2:
            return parts[0], parts[1]
        return "", ""

    def _track_changes(self, tool_name: str, tool_input: dict, result: Any) -> None:
        """Track which files were created or modified, and build state."""
        changed_now: list[str] = []
        if tool_name in ("write_file", "find_and_replace", "replace_file_content", "delete_file") and result.success:
            path = tool_input.get("path", "")
            if path and path not in self._files_changed:
                self._files_changed.append(path)
                changed_now.append(path)
            self._built_successfully = False  # File changed, requires a new build
        elif tool_name == "batch_replace_file_content" and result.success:
            edits = []
            if isinstance(tool_input, dict):
                edits = tool_input.get("edits", [])
            elif isinstance(tool_input, list):
                edits = tool_input
            for edit in edits:
                if isinstance(edit, dict):
                    p = edit.get("path") or edit.get("file_path") or edit.get("file")
                    if p and p not in self._files_changed:
                        self._files_changed.append(p)
                        changed_now.append(p)
            self._built_successfully = False
        elif tool_name in ("install_and_build", "run_build") and result.success:
            self._built_successfully = True

        if changed_now and getattr(self, "_event_callback", None):
            for p in changed_now:
                try:
                    self._event_callback("file_written", {
                        "project_id": os.environ.get("PROJECT_ID", ""),
                        "agent_id": os.environ.get("AGENT_ID", ""),
                        "file_path": str(p),
                    })
                except Exception:
                    pass

    def _success_result(self, data: Any) -> dict[str, Any]:
        """Format a successful tool result for Claude."""
        if data is None:
            content = "Success"
        elif isinstance(data, str):
            content = data
        elif isinstance(data, dict):
            content = json.dumps(data, indent=2, default=str)
        elif isinstance(data, list):
            content = json.dumps(data, indent=2, default=str)
        else:
            content = str(data)

        # Truncate very large outputs to stay within token limits
        max_len = 100_000
        if len(content) > max_len:
            content = content[:max_len] + "\n\n... [output truncated]"

        return {"type": "tool_result", "content": content, "is_error": False}

    def _execute_batch_write(self, tool_input: dict[str, Any] | list[Any] | str) -> dict[str, Any]:
        """Execute a batch write_files call — write multiple related files in one operation.

        This is the key to multi-file generation: child components + parent components
        are written together so prop names, imports, and class names are consistent.
        """
        import json

        # Normalize tool_input if it arrived as a JSON string
        if isinstance(tool_input, str):
            try:
                tool_input = json.loads(tool_input)
            except Exception:
                try:
                    import ast
                    tool_input = ast.literal_eval(tool_input)
                except Exception:
                    pass

        files = []
        if isinstance(tool_input, list):
            files = tool_input
        elif isinstance(tool_input, dict):
            # Case 1: Standard {"files": [...]}
            raw_files = tool_input.get("files")
            if raw_files is None:
                # Also check common synonyms
                raw_files = (
                    tool_input.get("file_list")
                    or tool_input.get("file")
                    or tool_input.get("items")
                    or tool_input.get("file_paths")
                    or tool_input.get("operations")
                    or tool_input.get("changes")
                    or tool_input.get("modifications")
                    or tool_input.get("sources")
                    or tool_input.get("documents")
                )

            if isinstance(raw_files, list) and raw_files:
                files = raw_files
            elif isinstance(raw_files, dict) and raw_files:
                # Case 2: {"files": {"path": "...", "content": "..."}}
                if "path" in raw_files or "file" in raw_files:
                    files = [raw_files]
                else:
                    # Case 3: {"files": {"path1": "content1", "path2": "content2"}}
                    files = [{"path": str(k), "content": str(v)} for k, v in raw_files.items()]
            elif isinstance(raw_files, str) and raw_files.strip():
                # Case 4: {"files": "[{...}]"}
                try:
                    parsed = json.loads(raw_files)
                    if isinstance(parsed, list):
                        files = parsed
                    elif isinstance(parsed, dict):
                        files = [parsed]
                except Exception:
                    pass

            if not files and ("path" in tool_input or "file" in tool_input) and any(k in tool_input for k in ("content", "code", "source", "text")):
                # Case 5: Single file payload passed directly: {"path": "...", "content": "..."}
                norm_p = tool_input.get("path") or tool_input.get("file")
                norm_c = tool_input.get("content") or tool_input.get("code") or tool_input.get("source") or tool_input.get("text", "")
                files = [{"path": norm_p, "content": norm_c}]
            elif not files and any(isinstance(v, (str, dict)) for v in tool_input.values()):
                # Case 6: Top-level dict mapping paths to contents: {"frontend/src/App.tsx": "..."}
                inferred = []
                for k, v in tool_input.items():
                    if isinstance(v, str) and ('.' in k or '/' in k or '\\' in k):
                        inferred.append({"path": k, "content": v})
                    elif isinstance(v, dict) and any(c in v for c in ("content", "code", "source", "text")):
                        p = v.get("path", k)
                        c = v.get("content") or v.get("code") or v.get("source") or v.get("text", "")
                        inferred.append({"path": p, "content": c})
                if inferred:
                    files = inferred

        # If files is a string, attempt multiple decoding strategies
        if isinstance(files, str):
            clean_str = files.strip()
            if clean_str.startswith("files=") or clean_str.startswith("files:"):
                clean_str = clean_str[6:].strip()
            elif clean_str.startswith("files ="):
                clean_str = clean_str.split("=", 1)[1].strip()

            try:
                files = json.loads(clean_str)
            except Exception:
                try:
                    import ast
                    files = ast.literal_eval(clean_str)
                except Exception:
                    pass

            # If still a string (e.g. malformed JSON or Python triple quotes """..."""), extract entries via regex
            if isinstance(files, str):
                import re
                extracted = []
                pattern = re.compile(
                    r'["\'](?:path|file|name)["\']\s*:\s*["\']([^"\']+)["\']\s*,\s*["\'](?:content|code|source|text)["\']\s*:\s*(?:"""(.*?)"""|\'\'\'(.*?)\'\'\'|"(.*?)"|\'(.*?)\')',
                    re.DOTALL
                )
                for m in pattern.finditer(clean_str):
                    p = m.group(1)
                    c = m.group(2) or m.group(3) or m.group(4) or m.group(5) or ""
                    extracted.append({"path": p, "content": c})
                if extracted:
                    files = extracted

        if not isinstance(files, list) or not files:
            return self._error_result(
                "Error: write_files requires a non-empty 'files' array. You provided 0 files.\n"
                "To write a file, you MUST use `write_file` with 'path' and 'content', e.g.:\n"
                "write_file(path='backend/src/index.ts', content='export const app = ...')\n"
                "Or provide the complete array: {'files': [{'path': '...', 'content': '...'}]}"
            )

        results = []
        errors = []

        for file_entry in files:
            # Handle if file_entry is a stringified JSON object
            if isinstance(file_entry, str):
                try:
                    file_entry = json.loads(file_entry)
                except Exception:
                    errors.append(f"Invalid file entry: expected object with 'path' and 'content', got string '{file_entry[:50]}'")
                    continue

            if not isinstance(file_entry, dict):
                errors.append(f"Invalid file entry: expected object, got {type(file_entry).__name__}")
                continue

            path = file_entry.get("path") or file_entry.get("file_path") or file_entry.get("file") or file_entry.get("name") or ""
            content = file_entry.get("content")
            if content is None:
                content = file_entry.get("code") or file_entry.get("source") or file_entry.get("text") or file_entry.get("body") or ""

            if not path or not content:
                errors.append(f"{path or 'unnamed_entry'}: skipped (missing path or content)")
                continue

            # Write each file through MCP
            result = self._mcp.call_tool("filesystem", "write_file", {
                "path": path,
                "content": content,
            })

            if result.success:
                self._track_changes("write_file", {"path": path}, result)
                # Check for syntax error or truncation
                try:
                    from runtime.syntax_validator import SyntaxValidator
                    workspace_path = getattr(self._mcp, "_workspace_path", None) or os.environ.get("WORKSPACE_PATH", "/workspace")
                    validator = SyntaxValidator(workspace_path)
                    rel_path = path.replace(str(workspace_path), "").lstrip("/\\")
                    file_errs = validator.validate_files([rel_path])
                    if file_errs:
                        err_item = file_errs[0]
                        err_msg = err_item.get("error", "Syntax or truncation error")
                        line_num = err_item.get("line", 0)
                        msg = f"⚠️ Syntax error/truncation detected in `{rel_path}` (line {line_num}). Asking the AI to fix or complete the file..."
                        try:
                            print(f"[ToolExecutor] {msg}")
                        except UnicodeEncodeError:
                            print(f"[ToolExecutor] {msg.encode('ascii', errors='replace').decode('ascii')}")
                        errors.append(f"{msg}: {err_msg}")
                        results.append({"path": path, "status": "truncated", "warning": msg})
                    else:
                        results.append({"path": path, "status": "written", "size": len(content)})
                        try:
                            print(f"   ✍️ Batch write: {path} ({len(content)} chars)")
                        except UnicodeEncodeError:
                            print(f"   Batch write: {path} ({len(content)} chars)")
                except Exception as val_exc:
                    results.append({"path": path, "status": "written", "size": len(content)})
            else:
                errors.append(f"{path}: {result.error}")

        # Build summary response with anti-loop directive
        has_truncation = any(r.get("status") == "truncated" for r in results)
        summary = {
            "files_written": len(results),
            "files": results,
            "status": "warning" if has_truncation else "success",
            "next_step": (
                "⚠️ Truncation/syntax error detected in one or more files. Like 'Continue' in chat, please rewrite/complete those files now before building."
                if has_truncation else
                "Files written successfully. DO NOT re-read or list workspace files. Proceed directly to creating any remaining components or call install_and_build()."
            )
        }
        if errors:
            summary["notes"] = errors

        return self._success_result(summary)

    def _execute_get_conversation_history(self, tool_input: dict[str, Any] | str) -> dict[str, Any]:
        """Retrieve past user requirements and assistant responses from disk transcript."""
        import os
        from pathlib import Path

        if isinstance(tool_input, str):
            try:
                tool_input = json.loads(tool_input)
            except Exception:
                tool_input = {}

        turn_limit = min(int(tool_input.get("turn_limit", 5)), 20)
        query = str(tool_input.get("query", "")).lower().strip()
        workspace_path = getattr(self._mcp, "_workspace_path", None) or os.environ.get("WORKSPACE_PATH", "/workspace")
        transcript_file = Path(workspace_path) / ".agent_history" / "full_transcript.jsonl"

        if not transcript_file.exists():
            return self._success_result("No previous conversation transcript found on disk.")

        try:
            lines = transcript_file.read_text(encoding="utf-8", errors="replace").strip().splitlines()
            entries = []
            for line in lines:
                if not line.strip():
                    continue
                try:
                    entries.append(json.loads(line))
                except Exception:
                    pass

            if query:
                entries = [
                    e for e in entries
                    if query in str(e.get("content", "")).lower() or query in str(e.get("role", "")).lower()
                ]

            selected = entries[-turn_limit:]
            if not selected:
                return self._success_result(f"No conversation turns matched query '{query}'.")

            output_lines = [f"### 📜 Retrieved {len(selected)} Past Conversation Turn(s):"]
            for idx, item in enumerate(selected, 1):
                role = item.get("role", "unknown").upper()
                content = item.get("content", "")
                if isinstance(content, list):
                    content = "\n".join(str(c) for c in content)
                output_lines.append(f"\n#### Turn {idx} [{role}]:")
                # Give more headroom (up to 4000 chars) especially for recent turns so user requirements aren't truncated
                char_limit = 4000 if idx == len(selected) or role == "USER" else 2000
                output_lines.append(str(content)[:char_limit])

            return self._success_result("\n".join(output_lines))
        except Exception as e:
            return self._error_result(f"Error reading conversation history: {e}")

    def _execute_get_past_fixes(self, tool_input: dict[str, Any] | str) -> dict[str, Any]:
        """Retrieve history of previous user change requests and fixes implemented in this workspace."""
        if isinstance(tool_input, str):
            try:
                tool_input = json.loads(tool_input)
            except Exception:
                tool_input = {}

        limit = min(int(tool_input.get("limit", 5)), 20)
        workspace_path = getattr(self._mcp, "_workspace_path", None) or os.environ.get("WORKSPACE_PATH", "/workspace")
        fix_file = os.path.join(workspace_path, ".agent_history", "fix_history.json")
        prompts_file = os.path.join(workspace_path, ".agent_history", "prompts_history.json")

        output_lines = ["### 🛠️ Previous Project Fixes & Requests:"]
        found = False

        if os.path.exists(fix_file):
            try:
                with open(fix_file, "r", encoding="utf-8") as f:
                    fixes = json.load(f)
                if isinstance(fixes, list) and fixes:
                    found = True
                    for idx, fix in enumerate(fixes[-limit:], 1):
                        prompt = fix.get("prompt", "")
                        files = ", ".join(fix.get("files_changed", [])) or "None"
                        summary = fix.get("final_text", "")
                        output_lines.append(f"\n#### Fix #{idx}:")
                        output_lines.append(f"- Request: \"{prompt}\"")
                        output_lines.append(f"- Files Modified: {files}")
                        if summary:
                            output_lines.append(f"- Summary: {summary[:200]}")
            except Exception as e:
                output_lines.append(f"Error reading fix history: {e}")

        if not found and os.path.exists(prompts_file):
            try:
                with open(prompts_file, "r", encoding="utf-8") as f:
                    prompts = json.load(f)
                if isinstance(prompts, list) and prompts:
                    found = True
                    for idx, entry in enumerate(prompts[-limit:], 1):
                        p = entry.get("prompt", "")
                        output_lines.append(f"\n#### Request #{idx}: \"{p}\"")
            except Exception as e:
                output_lines.append(f"Error reading prompt history: {e}")

        if not found:
            return self._success_result("No past fix history found in this workspace.")

        # Check if there is also an inspected archive
        archive_file = os.path.join(workspace_path, ".agent_history", "inspected_archive.json")
        if os.path.exists(archive_file):
            try:
                with open(archive_file, "r", encoding="utf-8") as f:
                    archived = json.load(f)
                if archived:
                    output_lines.append(f"\n#### Archived File Inspections on disk: {', '.join(archived.keys())}")
            except Exception:
                pass

        return self._success_result("\n".join(output_lines))

    def _execute_update_product_spec(self, tool_input: dict[str, Any] | str) -> dict[str, Any]:
        """Update the living product specification (product_spec.json)."""
        import os
        from agent.spec_manager import ProductSpec

        if isinstance(tool_input, str):
            try:
                tool_input = json.loads(tool_input)
            except Exception:
                tool_input = {}

        workspace_path = getattr(self._mcp, "_workspace_path", None) or os.environ.get("WORKSPACE_PATH", "/workspace")
        spec = ProductSpec.load_or_init(workspace_path)
        spec.update_spec(
            workspace_path,
            architecture_tier=tool_input.get("architecture_tier"),
            entities=tool_input.get("entities"),
            workflows=tool_input.get("workflows"),
            active_features=tool_input.get("active_features"),
        )
        return self._success_result({
            "status": "updated",
            "message": f"Living Product Specification updated: tier={spec.architecture_tier}, entities={list(spec.entities.keys())}",
            "architecture_tier": spec.architecture_tier,
            "entities": spec.entities,
            "workflows": spec.workflows,
            "active_features": spec.active_features,
        })

    def _execute_submit_plan(self, tool_input: dict[str, Any] | str) -> dict[str, Any]:
        """Record the submitted implementation plan and conclude planning."""
        import json
        if isinstance(tool_input, str):
            try:
                tool_input = json.loads(tool_input)
            except Exception:
                tool_input = {}
        self._submitted_plan = tool_input
        title = tool_input.get("title") or tool_input.get("objective", "Implementation Plan")
        items = tool_input.get("steps") or tool_input.get("tasks", [])
        msg = f"[ToolExecutor] 📋 Implementation plan submitted: '{title}' ({len(items)} items)"
        try:
            print(msg)
        except UnicodeEncodeError:
            print(msg.encode("ascii", errors="replace").decode("ascii"))
        return self._success_result(
            f"Plan '{title}' accepted with {len(items)} items. Planning phase complete. Proceeding to coding phase."
        )

    @property
    def submitted_plan(self) -> dict[str, Any] | None:
        """Return the plan submitted via submit_plan, if any."""
        return getattr(self, "_submitted_plan", None)

    def _error_result(self, error: str) -> dict[str, Any]:
        """Format a failed tool result for Claude."""
        return {"type": "tool_result", "content": f"Error: {error}", "is_error": True}
