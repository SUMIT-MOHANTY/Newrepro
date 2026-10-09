"""ClaudeToolClient â€” Tool-use execution loop for Agent Runtime.

Integrates with the Bourntec AI processing API (Claude, Kimi, DeepSeek), executes MCP tools,
streams live step-by-step logs into the container console, and tracks exact token usage directly
from the AI response without any client-side token calculations.

Smart Context Management (v2):
- Persistent file manifest tracks every file written with key exports/structure
- Smart compaction replaces aggressive truncation with meaningful summaries
- Larger recent window (8 messages) for better continuity
- Token budget guard compacts harder when near limit, but ALWAYS preserves file manifest
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

from agent.tools.tool_executor import ToolExecutor
from infrastructure.llm_client import LLMClient, LLMResponse, log
from infrastructure.model_profile import get_profile
from runtime.resource_limits import ResourceLimits


# --- Token budget constants ---
# Approximate chars-per-token ratio for English text
CHARS_PER_TOKEN = 4
DEFAULT_CONTEXT_WINDOW = 128_000
RESERVED_HEADROOM_TOKENS = 16_000  # Intentionally reserved headroom for model output & reasoning
# Max tokens we're willing to send in the prompt (conservative default)
MAX_PROMPT_TOKENS = DEFAULT_CONTEXT_WINDOW - RESERVED_HEADROOM_TOKENS
# Max chars = max_tokens * chars_per_token
MAX_PROMPT_CHARS = MAX_PROMPT_TOKENS * CHARS_PER_TOKEN
# Number of recent messages to keep in FULL detail (no compaction)
RECENT_WINDOW = 8
# Max chars for a single compacted tool result
COMPACTED_TOOL_RESULT_MAX = 400
# Max chars for a single compacted assistant message
COMPACTED_ASSISTANT_MAX = 600
# Hard cap on conversation message count â€” beyond this, oldest messages are merged
MAX_CONVERSATION_MESSAGES = 100


def _clean_pseudo_tools_from_text(text: Any) -> str:
    """Strip any pseudo-tool call syntax, fake User/Input blocks, and bracketed tool calls from text."""
    if not text:
        return ""
    if not isinstance(text, str):
        if isinstance(text, dict):
            try:
                text = json.dumps(text)
            except Exception:
                text = str(text)
        elif isinstance(text, (list, tuple)):
            try:
                text = " ".join(str(x) for x in text)
            except Exception:
                text = str(text)
        else:
            text = str(text)
    # Strip DeepSeek DSML tags
    cleaned = re.sub(r'<[ï½œ|]DSML[ï½œ|][^>]*>', '', text)
    cleaned = re.sub(r'<[ï½œ|]/?(?:DSML|function_calls?)[ï½œ|]>', '', cleaned)
    # Strip function tags: <function=name>...</function>
    cleaned = re.sub(r'(?s)<function=[^>]+>.*?</function>', '', cleaned)
    # Strip blocks like: User: [Tool: write_files] or [Tool: write_files]
    cleaned = re.sub(r'(?i)(?:User:\s*)?\[Tool:\s*[^\]]+\](?:\s*Input:\s*[^\n]+)?', '', cleaned)
    # Strip raw tool calls in text: write_files(files=[...]) or write_file(path=..., content=...)
    cleaned = re.sub(r'(?is)(?:write_file|write_files|replace_file_content)\s*\([^)]*\)', '', cleaned)
    # Strip Input: files=[...] or Input: path=...
    cleaned = re.sub(r'(?i)^\s*Input:\s*(?:files|path|content|edits)=.*$', '', cleaned, flags=re.MULTILINE)
    # Strip pseudo Tool Result lines
    cleaned = re.sub(r'(?i)^\s*(?:Tool\s*Result|Function\s*Result|Result)\s*\([^)]*\):.*$', '', cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r'(?i)^\s*(?:Tool|Function)?\s*Results?:\s*.*$', '', cleaned, flags=re.MULTILINE)
    # Strip User: [Tool Result] headers if leaked into assistant content
    cleaned = re.sub(r'(?i)^\s*User:\s*\[?Tool\s*Results?\]?.*$', '', cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r'(?i)^\s*User:\s*Tool\s*execution\s*outputs?:.*$', '', cleaned, flags=re.MULTILINE)
    # Collapse excess whitespace
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    return cleaned.strip()


def _format_clean_tool_result(tool_name: str, raw_res: str, is_err: bool) -> str:
    """Format tool execution results cleanly so model sees outcome without syntax pollution."""
    if is_err:
        return f"[Error in {tool_name}]: {raw_res.strip()}"

    # For write tools, extract clean file list summary without code dumps
    if tool_name in ("write_file", "write_files") and "files_written" in raw_res:
        try:
            data = json.loads(raw_res) if raw_res.strip().startswith("{") else {}
            files = data.get("files", [])
            file_summaries = [f"{f.get('path', '')} ({f.get('size', 0)} bytes)" for f in files if isinstance(f, dict)]
            next_step = data.get("next_step", "Proceed to next components or build.")
            return (
                f"Successfully wrote {len(file_summaries)} file(s) to workspace:\n"
                + "\n".join(f"  âœ“ {fs}" for fs in file_summaries)
                + f"\n{next_step}"
            )
        except Exception:
            pass

    return raw_res.strip()


@dataclass
class ToolLoopResult:
    """Result from a complete tool-use loop."""
    final_text: str
    tool_calls_made: list[dict[str, Any]] = field(default_factory=list)
    files_changed: list[str] = field(default_factory=list)
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_tokens: int = 0
    iterations: int = 0
    stop_reason: str = ""
    model: str = ""
    conversation: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class FileManifestEntry:
    """Tracks a file that was written during the session."""
    path: str
    size_chars: int
    iteration: int
    # Key structural info extracted from content (exports, imports, component names)
    summary: str = ""
    # Full content preview (first N chars) for context
    content_preview: str = ""


class FileManifest:
    """Persistent manifest of all files written during the session.
    
    This survives context compaction â€” the model always knows what files
    exist and their key structure, even after old messages are summarized.
    """
    
    def __init__(self):
        self._entries: dict[str, FileManifestEntry] = {}
    
    def track_file(self, path: str, content: Any, iteration: int) -> None:
        """Record a file write with extracted structural info."""
        if not isinstance(content, str):
            if isinstance(content, dict):
                content = content.get("content") or content.get("code") or json.dumps(content)
            elif isinstance(content, (bytes, bytearray)):
                content = content.decode("utf-8", errors="ignore")
            else:
                content = str(content or "")
        summary = self._extract_summary(path, content)
        preview = content[:200].replace("\n", " ").strip()
        
        self._entries[path] = FileManifestEntry(
            path=path,
            size_chars=len(content),
            iteration=iteration,
            summary=summary,
            content_preview=preview,
        )

    def add_or_update_file(self, path: str, content: Any, iteration: int = 0, summary: str = "") -> None:
        """Alias for track_file for manifest compatibility."""
        self.track_file(path, content, iteration)
    
    def _extract_summary(self, path: str, content: Any) -> str:
        """Extract key structural info from file content (exports, component names)."""
        if not isinstance(content, str):
            if isinstance(content, dict):
                content = content.get("content") or content.get("code") or json.dumps(content)
            else:
                content = str(content or "")
        parts = []
        
        # Extract exports
        exports = re.findall(
            r'export\s+(?:default\s+)?(?:function|const|class)\s+(\w+)',
            content
        )
        if exports:
            parts.append(f"exports: {', '.join(exports)}")
        
        # Extract imports (just the module names)
        imports = re.findall(r"import\s+.*?from\s+['\"]([^'\"]+)['\"]", content)
        if imports:
            unique_imports = list(dict.fromkeys(imports))  # dedupe, preserve order
            parts.append(f"imports: {', '.join(unique_imports[:6])}")
        
        # For mockData files, extract top-level export names
        if "mockData" in path or "mock" in path.lower():
            mock_exports = re.findall(r'export\s+const\s+(\w+)', content)
            if mock_exports:
                parts.append(f"mock exports: {', '.join(mock_exports[:10])}")
        
        # For component files, extract prop interface
        if ".jsx" in path or ".tsx" in path:
            props_match = re.search(r'(?:function|const)\s+(\w+)\s*=\s*\(\s*\{([^}]+)\}', content)
            if props_match:
                parts.append(f"props: {props_match.group(2).strip()[:100]}")
        
        return "; ".join(parts) if parts else f"{len(content)} chars"

    def scan_workspace(self, workspace_path: str) -> None:
        """Scan physical workspace and register existing files into the manifest."""
        from pathlib import Path
        ws = Path(workspace_path)
        if not ws.exists():
            return
        
        ignored_dirs = {".git", "node_modules", "dist", ".agent_history", ".vscode"}
        for root, dirs, files in os.walk(ws):
            dirs[:] = [d for d in dirs if d not in ignored_dirs and not d.startswith(".")]
            for f in files:
                if f.startswith("."):
                    continue
                full_path = Path(root) / f
                rel_path = str(full_path.relative_to(ws)).replace("\\", "/")
                if rel_path in self._entries:
                    continue
                try:
                    if full_path.stat().st_size > 100_000:
                        continue
                    content = full_path.read_text(encoding="utf-8", errors="ignore")
                    summary = self._extract_summary(rel_path, content)
                    self._entries[rel_path] = FileManifestEntry(
                        path=rel_path,
                        size_chars=len(content),
                        iteration=0,
                        summary=summary,
                        content_preview=content[:200].replace("\n", " ").strip(),
                    )
                except Exception:
                    pass
    
    def to_manifest_string(self) -> str:
        """Render the manifest as a string for injection into conversation."""
        if not self._entries:
            return ""
        
        lines = ["WORKSPACE FILE MANIFEST:"]
        for path, entry in self._entries.items():
            iter_tag = f"iter {entry.iteration}" if entry.iteration > 0 else "scaffold"
            lines.append(
                f"  - {path} ({entry.size_chars} chars, {iter_tag}): "
                f"{entry.summary}"
            )
        lines.append(
            "\nThese files EXIST in the workspace. You do NOT need to explore directories to find them."
        )
        return "\n".join(lines)
    
    def get_file_count(self) -> int:
        return len(self._entries)
    
    def get_total_chars(self) -> int:
        return sum(e.size_chars for e in self._entries.values())


def generate_clean_file_tree(workspace_path: str) -> str:
    """Generate a clean, compact ASCII directory tree of source code files.
    
    Filters out node_modules, dist, build, .git, .agent_history, lockfiles, and hidden files.
    """
    from pathlib import Path
    ws = Path(workspace_path)
    if not ws.exists():
        return ""

    ignored_dirs = {
        ".git", "node_modules", "dist", "build", ".agent_history",
        ".vscode", "__pycache__", ".next", ".cache", "coverage", ".turbo"
    }
    ignored_files = {
        "package-lock.json", "bun.lockb", "yarn.lock", "pnpm-lock.yaml",
        ".DS_Store", "Thumbs.db"
    }

    file_paths = []
    for root, dirs, files in os.walk(ws):
        dirs[:] = [d for d in dirs if d not in ignored_dirs and not d.startswith(".")]
        for f in files:
            if f in ignored_files or f.startswith("."):
                continue
            full_path = Path(root) / f
            try:
                rel_path = str(full_path.relative_to(ws)).replace("\\", "/")
                file_paths.append(rel_path)
            except Exception:
                pass

    if not file_paths:
        return ""

    file_paths.sort()

    tree: dict[str, Any] = {}
    for p in file_paths:
        parts = p.split("/")
        curr = tree
        for part in parts[:-1]:
            curr = curr.setdefault(part, {})
        curr[parts[-1]] = None

    lines = ["Project Structure:"]
    def _render(node: dict[str, Any], prefix: str = ""):
        keys = sorted(node.keys(), key=lambda k: (node[k] is None, k.lower()))
        for i, k in enumerate(keys):
            is_last = (i == len(keys) - 1)
            connector = "â””â”€â”€ " if is_last else "â”œâ”€â”€ "
            child_prefix = "    " if is_last else "â”‚   "
            if node[k] is None:
                lines.append(f"{prefix}{connector}{k}")
            else:
                lines.append(f"{prefix}{connector}{k}/")
                _render(node[k], prefix + child_prefix)

    _render(tree)
    return "\n".join(lines)


def _extract_compiler_error_files(error_text: str) -> list[str]:
    """Extract workspace source file paths from compiler/build error output.

    Recognizes Vite/Rollup/PostCSS/TypeScript/tsc error formats, e.g.:
      [vite:css] [postcss] /workspace/src/index.css:115:3: ...
      file: /workspace/src/components/App.jsx
      src/services/paymentService.js(12,5): error TS...
    """
    import re
    if not error_text:
        return []
    files: list[str] = []
    seen: set[str] = set()
    patterns = [
        r"(?:file:\s+)?(?:/workspace/)?([\w./-]+\.(?:js|jsx|ts|tsx|css|scss|vue|svelte|html|json)):(?:\d+)(?::\d+)?",
        r"file:\s+(/workspace/[\w./-]+)",
        r"([\w./-]+\.(?:js|jsx|ts|tsx|css|scss|vue|svelte|html|json))\(\d+,\d+\)",
    ]
    for pat in patterns:
        for m in re.finditer(pat, error_text):
            f = m.group(1).replace("\\", "/").lstrip("/")
            if f.startswith("node_modules/") or "node_modules" in f:
                continue
            if f not in seen:
                seen.add(f)
                files.append(f)
        if files:
            break
    return files[:5]


def _summarize_compiler_error(error_text: str) -> str:
    """Extract the most relevant diagnostic lines from a build error for prompt injection."""
    if not error_text:
        return "Compiler error (no details captured)"
    import re
    lines = [ln.strip() for ln in error_text.splitlines() if ln.strip()]
    keep: list[str] = []
    for ln in lines:
        low = ln.lower()
        if (
            "error" in low
            or "does not exist" in low
            or "failed" in low
            or low.startswith("x ")
            or re.search(r"[\w./-]+\.(?:js|jsx|ts|tsx|css|scss|vue|svelte|html|json):\d+", ln)
        ):
            if len(ln) > 300:
                ln = ln[:300] + "…"
            if ln not in keep:
                keep.append(ln)
        if len(keep) >= 5:
            break
    if not keep:
        # Fallback: last non-empty lines usually carry the root cause
        keep = [ln[:300] for ln in lines[-3:]]
    return " | ".join(keep)


class TaskChecklistTracker:
    """Tracks structured execution tasks for follow-up prompts.
    
    Guarantees:
    - AI remains focused on the user's high-level objective without drifting.
    - Completed file tasks are checked off when edited and syntax-verified.
    - Prevents single-file re-edit loops by explicitly directing the model to the next task.
    """

    def __init__(
        self,
        tasks: list[dict[str, Any]],
        objective: str = "",
        current_state: str = "",
        changes_required: str = "",
    ):
        self.tasks = list(tasks)
        self.objective = objective
        self.current_state = current_state
        self.changes_required = changes_required
        self.completed_task_ids: set[int] = set()
        self.active_task_index: int = 0
        self.files_completed: set[str] = set()
        # Build-repair state: tracks the last build failure so the banner can switch
        # from "VERIFY" to "BUILD REPAIR REQUIRED" and stop commanding a futile re-build.
        self.build_failed: bool = False
        self.build_error_summary: str = ""
        self.build_error_files: list[str] = []
    def record_build_failure(self, error_summary: str, affected_files: list[str] | None = None) -> None:
        """Record that the build failed so the banner demands edits instead of re-builds."""
        self.build_failed = True
        self.build_error_summary = (error_summary or "Compiler error (summary unavailable)")[:500]
        self.build_error_files = list(affected_files or [])

    def clear_build_failure(self) -> None:
        """Clear build-failure state after any successful file edit (gate re-arms the build)."""
        self.build_failed = False
        self.build_error_summary = ""
        self.build_error_files = []

    def mark_file_completed(self, file_path: str, clear_cache_callback: "Callable[[], None] | None" = None, content: str | None = None) -> None:
        # A successful edit re-arms the build: the repair banner must not persist after the fix
        self.clear_build_failure()
        """Mark task associated with file_path as completed and advance to next."""
        norm_path = file_path.replace("\\", "/").lstrip("/")
        prev_index = self.active_task_index

        for idx, t in enumerate(self.tasks):
            action = str(t.get("action", "")).lower()
            if action in ("install", "verify"):
                continue
            t_file = t.get("file", "").replace("\\", "/").lstrip("/")
            if t_file and (t_file == norm_path or norm_path.endswith(t_file) or t_file.endswith(norm_path)):
                tid = t.get("task_id", idx + 1)
                if tid not in self.completed_task_ids:
                    self.completed_task_ids.add(tid)
                    self.files_completed.add(t_file)
                    log(f"✅ [Task Tracker] Task {tid} COMPLETED: `{t_file}`")

        # Advance active_task_index to first incomplete task
        while (
            self.active_task_index < len(self.tasks)
            and self.tasks[self.active_task_index].get("task_id", self.active_task_index + 1) in self.completed_task_ids
        ):
            self.active_task_index += 1

        # Clear inspected-files cache when task advances to prevent stale context bleed
        if self.active_task_index != prev_index and clear_cache_callback:
            clear_cache_callback()
            log(f"🧹 [Task Tracker] Cleared inspected-files cache on task advance ({prev_index} -> {self.active_task_index}).")

    def mark_verification_completed(self, clear_cache_callback: "Callable[[], None] | None" = None) -> None:
        """Mark build verification task as completed."""
        prev_index = self.active_task_index
        for idx, t in enumerate(self.tasks):
            if t.get("action") == "verify" or "build" in t.get("file", "").lower():
                tid = t.get("task_id", idx + 1)
                self.completed_task_ids.add(tid)
                log(f"âœ… [Task Tracker] Verification Task {tid} COMPLETED.")
        # Advance index
        while (
            self.active_task_index < len(self.tasks)
            and self.tasks[self.active_task_index].get("task_id", self.active_task_index + 1) in self.completed_task_ids
        ):
            self.active_task_index += 1
        if self.active_task_index != prev_index and clear_cache_callback:
            clear_cache_callback()
            log(f"ðŸ§¹ [Task Tracker] Cleared inspected-files cache on verify advance ({prev_index} -> {self.active_task_index}).")

    def mark_install_completed(self, clear_cache_callback: "Callable[[], None] | None" = None) -> None:
        """Mark install task as completed and advance to next."""
        prev_index = self.active_task_index
        for idx, t in enumerate(self.tasks):
            if t.get("action") == "install":
                tid = t.get("task_id", idx + 1)
                if tid not in self.completed_task_ids:
                    self.completed_task_ids.add(tid)
                    log(f"✅ [Task Tracker] Task {tid} COMPLETED (action: install).")
        while (
            self.active_task_index < len(self.tasks)
            and self.tasks[self.active_task_index].get("task_id", self.active_task_index + 1) in self.completed_task_ids
        ):
            self.active_task_index += 1
        # Clear inspected-files cache whenever task advances so the AI cannot
        # confuse content from a previous task as the current task's context
        if self.active_task_index != prev_index and clear_cache_callback:
            clear_cache_callback()
            log(f"🧹 [Task Tracker] Cleared inspected-files cache on task advance ({prev_index} -> {self.active_task_index}).")

    def is_all_file_tasks_completed(self) -> bool:
        """Check if all non-verification file tasks are completed."""
        for idx, t in enumerate(self.tasks):
            if t.get("action") not in ("verify", "install") and "build" not in t.get("file", "").lower():
                if t.get("task_id", idx + 1) not in self.completed_task_ids:
                    return False
        return True

    def reset_verification(self) -> None:
        """Un-mark verification tasks when build fails so checklist reflects pending verification."""
        for idx, t in enumerate(self.tasks):
            if t.get("action") == "verify" or "build" in t.get("file", "").lower():
                tid = t.get("task_id", idx + 1)
                if tid in self.completed_task_ids:
                    self.completed_task_ids.remove(tid)
                    log(f"🔄 [Task Tracker] Verification Task {tid} reset to pending after build failure.")

    def render_prompt_banner(self) -> str:
        """Render the authoritative task banner for prompt injection."""
        if not self.tasks:
            return ""

        total_tasks = len(self.tasks)
        completed_count = len(self.completed_task_ids)

        lines = []
        if self.objective:
            lines.append(f"## SESSION OBJECTIVE\n{self.objective}\n")
        if self.current_state or self.changes_required:
            lines.append("## CODEBASE GAP ANALYSIS")
            if self.current_state:
                lines.append(f"- **What is Present:** {self.current_state}")
            if self.changes_required:
                lines.append(f"- **Changes Required:** {self.changes_required}")
            lines.append("")


        # Explicit position counter â€” the model MUST know exactly where it is
        lines.append(f"## ACTIVE TASK CHECKLIST  [{completed_count}/{total_tasks} completed]")
        lines.append(
            "IMPORTANT: The 'Active Inspected Files' section below may contain files read in PREVIOUS turns. "
            "Do NOT re-read a file you have already written. "
            "The tracker state below is the AUTHORITATIVE record of what is done and what is next."
        )
        lines.append("")

        for idx, t in enumerate(self.tasks):
            tid = t.get("task_id", idx + 1)
            t_file = t.get("file", "")
            t_desc = t.get("description", t.get("instructions", ""))
            is_done = tid in self.completed_task_ids
            is_active = (idx == self.active_task_index and not is_done)

            if is_done:
                lines.append(f"[x] Task {tid}: `{t_file}` â€” {t_desc} (DONE)")
            elif is_active:
                lines.append(f">>> [ACTIVE - Task {tid} of {total_tasks}] `{t_file}` â€” {t_desc}  <<<")
            else:
                lines.append(f"[ ] Task {tid}: `{t_file}` â€” {t_desc}")

        lines.append("")
        # Add turn directive â€” strict action matching, no description string matching
        if self.active_task_index < len(self.tasks):
            curr_task = self.tasks[self.active_task_index]
            c_file = curr_task.get("file", "")
            c_action = curr_task.get("action", "edit")
            c_desc = curr_task.get("description", "")
            curr_tid = curr_task.get("task_id", self.active_task_index + 1)
            if self.build_failed:
                affected = ", ".join(f"`{f}`" for f in self.build_error_files) or "the file(s) named in the error below"
                lines.append(
                    f"DIRECTIVE FOR THIS TURN (Task {curr_tid} of {total_tasks} — BUILD REPAIR REQUIRED):\n"
                    "- ⚠️ THE BUILD FAILED WITH COMPILER ERRORS — code is NOT complete!\n"
                    "- Calling `install_and_build` without editing any file is BLOCKED by the runtime.\n"
                    f"- Compiler error: {self.build_error_summary}\n"
                    f"- Target file(s) to fix: {affected}\n"
                    "- You MUST modify the code using `replace_file_content` or `write_file` NOW to resolve the compiler error.\n"
                    "- Once you have edited the broken file(s), the build gate unlocks and `install_and_build` verifies the fix."
                )
            elif c_action == "verify" or "build" in c_file.lower():
                lines.append(
                    f"DIRECTIVE FOR THIS TURN (Task {curr_tid} of {total_tasks} â€” {c_action.upper()}):\n"
                    "- All code modifications across identified files are complete.\n"
                    "- Execute `install_and_build` to verify compilation with zero errors.\n"
                    "- Once build passes, provide your final high-level functional summary for business users (focus on user capabilities and experience; omit file paths, CSS classes, and build commands) and conclude."
                )
            elif c_action == "install":
                completed_names = ", ".join(f"`{f}`" for f in sorted(self.files_completed)) or "None"
                lines.append(
                    f"DIRECTIVE FOR THIS TURN (Task {curr_tid} of {total_tasks} â€” INSTALL):\n"
                    f"- `package.json` was updated. Execute `install_dependencies` NOW to run `npm install`.\n"
                    f"- Do NOT read any files. Do NOT write any code files. ONLY call `install_dependencies`.\n"
                    f"- Once `install_dependencies` succeeds, the tracker will advance to Task {curr_tid + 1}."
                )
            elif c_action == "delete":
                completed_names = ", ".join(f"`{f}`" for f in sorted(self.files_completed)) or "None"
                lines.append(
                    f"DIRECTIVE FOR THIS TURN (Task {curr_tid} of {total_tasks} â€” DELETE):\n"
                    f"- Already completed: {completed_names}. Do NOT touch completed files.\n"
                    f"- Call `delete_file` immediately on `{c_file}`. Do NOT call `read_file` or `list_directory` first.\n"
                    f"- Once deleted, the tracker advances to Task {curr_tid + 1}."
                )
            elif c_action == "create":
                completed_names = ", ".join(f"`{f}`" for f in sorted(self.files_completed)) or "None"
                lines.append(
                    f"DIRECTIVE FOR THIS TURN (Task {curr_tid} of {total_tasks} â€” CREATE):\n"
                    f"- Already completed: {completed_names}. Do NOT touch completed files.\n"
                    f"- `{c_file}` does NOT exist yet. Do NOT call `read_file` on it.\n"
                    f"- Call `write_file` immediately to create `{c_file}` with full, production-ready code.\n"
                    f"- Once written and verified, the tracker advances to Task {curr_tid + 1}."
                )
            else:
                completed_names = ", ".join(f"`{f}`" for f in sorted(self.files_completed)) or "None"
                lines.append(
                    f"DIRECTIVE FOR THIS TURN (Task {curr_tid} of {total_tasks} â€” {c_action.upper()}):\n"
                    f"- Already completed: {completed_names}. Do NOT touch completed files.\n"
                    f"- Apply changes to `{c_file}` using `replace_file_content` or `write_file`. Read it first ONLY if not in Active Inspected Files above.\n"
                    f"- Once `{c_file}` is written and verified, the tracker advances to Task {curr_tid + 1}."
                )
        else:
            lines.append(
                "DIRECTIVE FOR THIS TURN:\n"
                "- All tasks are marked completed. Call `install_and_build` or provide your final high-level functional summary for business users."
            )

        return "\n".join(lines)





class ClaudeToolClient:
    """Agent tool loop runner connecting to the AI API."""

    def __init__(
        self,
        *,
        model: str | None = None,
        api_key: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int = 16384,
        temperature: float = 0.2,
        reality_guard: Any | None = None,
        file_manifest: FileManifest | None = None,
        workspace_path: str | None = None,
    ) -> None:
        self._model = model or os.environ.get("AI_MODEL") or os.environ.get("MODEL_NAME", "claude")
        self._tools = tools or []
        env_max = os.environ.get("MAX_OUTPUT_TOKENS") or os.environ.get("AI_MAX_TOKENS")
        self._max_tokens = int(env_max) if env_max and env_max.isdigit() else max_tokens
        self._temperature = temperature
        self._limits = ResourceLimits()
        self._llm_client = LLMClient()
        self._file_manifest = file_manifest or FileManifest()
        self._reality_guard = reality_guard
        self._workspace_path = workspace_path or getattr(reality_guard, "workspace_path", None) or os.environ.get("WORKSPACE_PATH", "/workspace")
        
        # Dynamic Token Headroom calculation: Model Context Limit - Reserved Headroom
        context_window = int(os.environ.get("MODEL_CONTEXT_WINDOW", DEFAULT_CONTEXT_WINDOW))
        self._max_prompt_tokens = max(context_window - RESERVED_HEADROOM_TOKENS, 32_000)
        self._max_prompt_chars = self._max_prompt_tokens * CHARS_PER_TOKEN
        self._inspected_paths: set[str] = set()
        self._inspected_files: dict[str, str] = {}
        self._inspected_files_iter: dict[str, int] = {}  # Tracks which iteration each file was cached
        self._consecutive_reads: int = 0
        self._last_tool_sig: str = ""
        self._duplicate_call_count: int = 0
        # Build-repair state (Build Redundancy Gate): prevents the futile
        # read_file → install_and_build → read_file loop after a build failure.
        self._last_build_failed: bool = False
        self._files_modified_since_build: int = 0
        self._last_build_error_summary: str = ""
        self._last_build_error_files: list[str] = []
        self._consecutive_reads_since_build_failure: int = 0

    def _log_to_transcript(self, role: str, content: Any, metadata: dict[str, Any] | None = None) -> None:
        """Persist full conversation history and tool events to disk transcript for recall."""
        try:
            import time
            from pathlib import Path
            hist_dir = Path(self._workspace_path) / ".agent_history"
            hist_dir.mkdir(parents=True, exist_ok=True)
            transcript_file = hist_dir / "full_transcript.jsonl"
            entry = {
                "timestamp": time.time(),
                "role": role,
                "content": content,
                "metadata": metadata or {},
            }
            with open(transcript_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception:
            pass

    def _clear_inspected_cache(self) -> None:
        """Clear both the inspected files cache and the iteration tracker atomically."""
        self._inspected_files.clear()
        self._inspected_files_iter.clear()

    def _clear_build_repair_state(self) -> None:
        """Reset build-repair gate state after a successful build/install or any successful edit."""
        self._last_build_failed = False
        self._files_modified_since_build = 0
        self._consecutive_reads_since_build_failure = 0
        self._last_build_error_summary = ""
        self._last_build_error_files = []

    def run_tool_loop(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tool_executor: ToolExecutor,
        max_iterations: int = 40,
        on_event: Any | None = None,
        task_tracker: TaskChecklistTracker | None = None,
        clean_file_tree: str = "",
    ) -> ToolLoopResult:
        """Run the AI tool-use loop until completion."""
        result = ToolLoopResult(final_text="", model=self._model)
        conversation = list(messages)
        # Log incoming messages to transcript
        for m in messages:
            self._log_to_transcript(m.get("role", "user"), m.get("content", ""))
        write_counts: dict[str, int] = {}
        failed_calls: dict[str, int] = {}
        patch_fails_per_file: dict[str, int] = {}
        was_truncated_previous_turn = False

        log(f"ðŸš€ [Tool Loop] Starting agent session with model: '{self._model}'")
        log(f"   Execution phase: {len(self._tools)} available tools")

        # Reset turn inspection cache and consecutive read counter
        self._inspected_files.clear()
        self._inspected_files_iter.clear()
        self._consecutive_reads = 0
        self._consecutive_reads_since_build_failure = 0
        self._clear_build_repair_state()
        self._active_task_tracker = task_tracker

        for iteration in range(max_iterations):
            result.iterations = iteration + 1
            log(f"ðŸ”„ [Step {iteration + 1}] Preparing prompt...")

            # Merge old messages if conversation exceeds hard cap
            if len(conversation) > MAX_CONVERSATION_MESSAGES:
                conversation = self._compact_conversation(conversation)

            # Format prompt for AI API:
            # 1. System Prompt (rules, identity, instructions)
            # 2. Initial User Task & Requirements (prompt, plan, living spec)
            # 3. File Manifest (authoritative ground truth of files physically on disk)
            # 4. Active Inspected Files Cache (accumulated read results â€” solves model amnesia)
            # 5. Latest Action Outcome (immediate preceding turn's tool execution result)
            # 6. Consecutive Read Circuit Breaker (forces model to write after 2 inspections)
            parts = []
            if system:
                parts.append(f"System: {system}")

            # Dynamic Task Checklist & Objective (if task_tracker active)
            if task_tracker:
                parts.append(task_tracker.render_prompt_banner())

            # 1. Primary User Task & Requirements (from initial conversation messages)
            initial_user_msgs = [
                m.get("content", "") for m in conversation
                if m.get("role") == "user" and isinstance(m.get("content"), str)
            ]
            if initial_user_msgs:
                parts.append(f"User: {initial_user_msgs[0]}")

            # Clean Codebase File Tree (if provided)
            if clean_file_tree:
                parts.append(f"## Clean Codebase Tree:\n```\n{clean_file_tree}\n```")

            # 2. Authoritative File Manifest (source of truth on physical disk)
            manifest_str = self._file_manifest.to_manifest_string()
            if manifest_str and self._file_manifest.get_file_count() > 0:
                parts.append(f"\n{manifest_str}")

            # 3. Active Inspected Files Cache (Preserves all read files in context)
            if self._inspected_files:
                prof = get_profile(self._model)
                ctx_window = max(getattr(prof, "context_window", 100_000) or 100_000, 100_000)
                chars_per_tok = getattr(prof, "chars_per_token", 3.8) or 3.8
                # Allocate ~35% of model context window to active inspection cache (e.g. 133k-266k chars)
                max_cache_chars = int(ctx_window * 0.35 * chars_per_tok)
                retain_chars = int(max_cache_chars * 0.80)

                total_inspect_chars = sum(len(c) for c in self._inspected_files.values())
                if total_inspect_chars > max_cache_chars:
                    # Offload older inspected files to disk archive
                    try:
                        hist_dir = os.path.join(self._workspace_path, ".agent_history")
                        os.makedirs(hist_dir, exist_ok=True)
                        archive_file = os.path.join(hist_dir, "inspected_archive.json")
                        existing_archive = {}
                        if os.path.exists(archive_file):
                            with open(archive_file, "r", encoding="utf-8") as f:
                                existing_archive = json.load(f)
                        existing_archive.update(self._inspected_files)
                        with open(archive_file, "w", encoding="utf-8") as f:
                            json.dump(existing_archive, f, indent=2)
                    except Exception as arch_e:
                        log(f"Warning archiving inspected files: {arch_e}")

                    # Retain newest entries fitting within retain_chars
                    retained: dict[str, str] = {}
                    curr_chars = 0
                    for k, v in reversed(list(self._inspected_files.items())):
                        if curr_chars + len(v) <= retain_chars:
                            retained[k] = v
                            curr_chars += len(v)
                        else:
                            break
                    self._inspected_files = dict(reversed(list(retained.items())))
                    log(f"ðŸ“¦ [Context Offload] Inspected files trimmed to {len(self._inspected_files)} files (~{curr_chars} chars of {max_cache_chars:,} limit). Older inspections archived to .agent_history/inspected_archive.json.")

                cache_lines = [
                    "## Active Inspected Files (Read Cache):",
                    "NOTE: Each file below was cached from disk when it was first read. The step number shows when it was read â€” NOT the current step. Do NOT re-read files already shown here.",
                ]
                for file_path, file_content in self._inspected_files.items():
                    read_at = self._inspected_files_iter.get(file_path, 0)
                    numbered_lines = [f"{idx}: {line}" for idx, line in enumerate(file_content.splitlines(), start=1)]
                    cache_lines.append(f"### File: {file_path} (read at step {read_at}, numbered lines):\n```\n" + "\n".join(numbered_lines) + "\n```")
                parts.append("\n".join(cache_lines))

            # 4. Immediate preceding turn's outcome or directive (if any)
            if len(conversation) > 1:
                last_msg = conversation[-1]
                last_role = last_msg.get("role", "user")
                last_content = last_msg.get("content", "")

                if isinstance(last_content, list):
                    # Immediate tool execution results from the turn just completed
                    text_pieces = []
                    for item in last_content:
                        if isinstance(item, dict) and item.get("type") == "tool_result":
                            tool_name = item.get("tool_name", "")
                            raw_res = str(item.get("content", ""))
                            is_err = item.get("is_error", False)
                            if tool_name in ("read_file", "get_generated_file") and not is_err:
                                if "Lines " in raw_res:
                                    clean_res = _format_clean_tool_result(tool_name, raw_res, is_err)
                                    text_pieces.append(f"{tool_name} slice output:\n{clean_res}")
                                else:
                                    # Include full/chunked lines directly in conversational outcome
                                    lines_out = raw_res.split("\n")
                                    if len(lines_out) > 500:
                                        chunk_preview = "\n".join(lines_out[:500]) + f"\n// ... ({len(lines_out)-500} remaining lines visible in Active Inspected Files above)"
                                    else:
                                        chunk_preview = raw_res
                                    text_pieces.append(f"{tool_name} output:\n{chunk_preview}")
                            else:

                                clean_res = _format_clean_tool_result(tool_name, raw_res, is_err)
                                text_pieces.append(f"{tool_name} output:\n{clean_res}")
                        elif isinstance(item, str):
                            text_pieces.append(item)
                    if text_pieces:
                        parts.append("User:\nLatest Action Outcome:\n" + "\n".join(text_pieces))
                elif isinstance(last_content, str) and last_role == "user" and last_content != (initial_user_msgs[0] if initial_user_msgs else ""):
                    # Runtime directive or continuation prompt
                    cleaned_directive = _clean_pseudo_tools_from_text(last_content)
                    if cleaned_directive.strip():
                        parts.append(f"User:\n{cleaned_directive.strip()}")
                elif isinstance(last_content, str) and last_role == "assistant":
                    # Assistant text from immediate previous turn
                    cleaned_text = _clean_pseudo_tools_from_text(last_content)
                    if cleaned_text.strip() and not any(k in cleaned_text.lower() for k in ("executing workspace operations", "user: [tool")):
                        parts.append(f"Assistant: {cleaned_text.strip()}")

            # 5. Rollback-Blocked Files Banner (shown every turn until write_file resolves them)
            rollback_blocked = getattr(tool_executor, "rollback_blocked_files", set())
            if rollback_blocked:
                blocked_list_str = ", ".join(f"`{p}`" for p in sorted(rollback_blocked))
                parts.append(
                    f"User:\n[ðŸš« PATCH TOOLS BLOCKED: {blocked_list_str} â€” rolled back due to syntax error. "
                    "You MUST call `write_file` with the COMPLETE file content. "
                    "Do NOT call read_file, replace_file_content, or batch_replace_file_content. "
                    "The file is already in Active Inspected Files above â€” write it NOW.]"
                )

            # 6. Progress Guard Guidance on Consecutive Reads (suppress when files are blocked — only write_file matters)
            elif self._consecutive_reads >= 3:
                inspected_list = ", ".join(self._inspected_files.keys()) if self._inspected_files else "workspace files"
                parts.append(
                    f"User:\n[Notice: You have inspected {inspected_list}. "
                    "If you have gathered sufficient context, proceed to implement your edits using `write_file` or `replace_file_content`.]"
                )

            # 7. Modified files tracking reminder
            if tool_executor.files_changed:
                parts.append(f"User:\n[Files modified so far in this session: {', '.join(tool_executor.files_changed)}]")

            if len(tool_executor.files_changed) == 0 and iteration >= 1 and not self._inspected_files:
                parts.append("User:\n[Action Required: Workspace files are listed in the manifest above. You MUST now call write_file with 'path' and 'content' to implement the application components.]")

            prompt_text = "\n\n".join(parts)

            # Token budget guard: if we're over the limit, compact harder or rollover to a fresh session
            estimated_chars = len(prompt_text)
            if estimated_chars > self._max_prompt_chars:
                log(f"⚠️ [Token Budget] Prompt is ~{estimated_chars // CHARS_PER_TOKEN:,} tokens "
                    f"(limit: {self._max_prompt_tokens:,}, headroom: {RESERVED_HEADROOM_TOKENS:,}). Evaluating context rollover...")
                if len(conversation) > 4:
                    conversation = self._rollover_to_new_session_context(
                        conversation=conversation,
                        system=system,
                        tool_executor=tool_executor,
                        task_tracker=task_tracker,
                        iteration=iteration,
                    )
                    # Rebuild clean prompt_text for the new session
                    parts = []
                    if system:
                        parts.append(f"System: {system}")
                    parts.append(f"User: {conversation[0]['content']}")
                    prompt_text = "\n\n".join(parts)
                else:
                    prompt_text = self._aggressive_compact(prompt_text, system)

            # Dynamic Tool Funnels (Guaranteed phase progression across all models):
            effective_tools = list(self._tools)

            # In Planning phase: Towards the end of the planning budget, focus the model on submit_plan
            has_submit_plan = any(t.get("name") == "submit_plan" for t in effective_tools)
            has_inspection_tools = any(t.get("name") in ("read_file", "grep_search", "list_directory") for t in self._tools)
            planning_funnel_threshold = max(3, max_iterations - 2) if has_inspection_tools else 1
            if has_submit_plan and iteration >= planning_funnel_threshold:
                effective_tools = [t for t in effective_tools if t.get("name") == "submit_plan"]
                log(f"🎯 [Planning Funnel] Step {iteration + 1}: Focusing model strictly on submit_plan.")

            # Rollback-Block Tool Funnel: When any file is blocked after rollback,
            # restrict the model to ONLY write_file. No reads, no patches.
            # This hard-funnels the AI to provide the complete corrected file immediately.
            if getattr(tool_executor, "rollback_blocked_files", set()):
                rollback_blocked_now = getattr(tool_executor, "rollback_blocked_files", set())
                write_file_only = [
                    t for t in effective_tools
                    if (t.get("name") or t.get("function", {}).get("name")) == "write_file"
                ]
                if write_file_only:
                    effective_tools = write_file_only
                    log(f"ðŸš« [Rollback-Block Funnel] Step {iteration + 1}: "
                        f"Blocked files: {sorted(rollback_blocked_now)}. "
                        f"Restricting model to write_file ONLY.")


            # In Editing / Follow-Up phase: Progress Guard on runaway reads (circuit breaker: >= 6 reads with 0 writes)
            # Normal exploration is supported. Runaway reading loops are funneled directly to write/build tools.
            elif self._consecutive_reads >= 6:
                write_action_tools = [
                    t for t in effective_tools
                    if (t.get("name") or t.get("function", {}).get("name")) in (
                        "replace_file_content",
                        "batch_replace_file_content",
                        "write_file",
                        "find_and_replace",
                        "install_and_build",
                    )
                ]
                if write_action_tools:
                    effective_tools = write_action_tools
                    log(f"⚡ [Progress Guard Funnel] Step {iteration + 1}: Consecutive reads threshold met "
                        f"(consecutive_reads={self._consecutive_reads}). "
                        f"Focusing model on file modification using: {[t.get('name') for t in effective_tools]}")
                    prompt_text += (
                        "\n\nUser:\n[Action Required: You have completed exploration. Inspection tools are now disabled. "
                        "You MUST write code now using `write_file` with 'path' and 'content' for the next file.]"
                    )

            # Call AI engine
            try:
                response: LLMResponse = self._llm_client.call_ai(
                    prompt_text,
                    tools=effective_tools,
                    model=self._model,
                    max_tokens=self._max_tokens,
                )
            except Exception as exc:
                log(f"âŒ [Step {iteration + 1}] Error calling AI: {exc}")
                result.final_text = f"AI execution error: {exc}"
                result.files_changed = tool_executor.files_changed
                result.conversation = conversation
                return result

            # Track EXACT token usage directly from model response (no client calculations)
            result.total_input_tokens += response.input_tokens
            result.total_output_tokens += response.output_tokens
            result.total_tokens += response.total_tokens
            result.stop_reason = response.stop_reason

            log(f"ðŸ“Š [Token Accumulator] Total so far: in={result.total_input_tokens}, out={result.total_output_tokens}, total={result.total_tokens}")

            # Check if there are tool calls in the response
            tool_calls = response.tool_calls
            assistant_content = response.content

            # Step 2: Strict Message Ownership â€” ASSISTANT role stores only model text/reasoning.
            # Tool call invocations and pseudo-tool syntax are NEVER stored in assistant messages.
            clean_assistant = _clean_pseudo_tools_from_text(assistant_content or "")
            if not clean_assistant.strip():
                clean_reasoning = _clean_pseudo_tools_from_text(response.reasoning or "")
                clean_assistant = (
                    clean_reasoning.strip()
                    if clean_reasoning.strip()
                    else ("Executing workspace operations." if tool_calls else "")
                )
            conversation.append({
                "role": "assistant",
                "content": clean_assistant,
            })
            self._log_to_transcript("assistant", assistant_content or "", metadata={"iteration": iteration + 1})

            # Stream thinking/reasoning if present
            thought_text = response.reasoning or (assistant_content if tool_calls else "")
            if thought_text and on_event:
                clean_thought = thought_text.strip()
                if clean_thought:
                    first_thought = clean_thought.split("\n")[0][:180]
                    on_event("thinking", {
                        "reasoning": clean_thought,
                        "thought_summary": first_thought,
                        "iteration": iteration + 1,
                    })

            # ================================================================
            # STEP 1: Tool Execution Firewall
            # Only execute tools from structured response.tool_calls.
            # If there are no tool_calls, treat entire response as plain text.
            # Do NOT regex-parse content for pseudo-tool syntax.
            # ================================================================
            if not tool_calls:
                # â”€â”€ Truncation Detection â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
                # Detect if the model hit the max output token ceiling (e.g. 8k or 16k tokens)
                # or if a tool call was cut off midway through generation.
                is_truncated_generation = (
                    response.output_tokens >= (self._max_tokens - 200 if self._max_tokens > 1000 else 7900)
                    or response.stop_reason in ("length", "max_tokens")
                    or any(tag in (assistant_content or "") for tag in ("DSML", "function_calls", "<ï½œ", "<|", "write_files"))
                )
                if is_truncated_generation:
                    was_truncated_previous_turn = True
                    log(f"âš ï¸ [Truncation Detected] Model generation was cut off at output ceiling (tokens={response.output_tokens}, stop_reason='{response.stop_reason}'). Asking AI to continue...")
                    if on_event:
                        on_event("warning", {
                            "message": f"âš ï¸ Output truncation detected ({response.output_tokens} tokens). Asking AI to continue with smaller chunks...",
                        })

                    # Critical Fix: Prune any cut-off code or pseudo-tool dumps from assistant message
                    # The AI must NEVER see incomplete code or pseudo tool calls in its own chat history!
                    if conversation and conversation[-1].get("role") == "assistant":
                        curr_content = conversation[-1].get("content", "")
                        clean_thought = _clean_pseudo_tools_from_text(curr_content)
                        first_para = clean_thought.split("\n\n")[0] if clean_thought else ""
                        if first_para and len(first_para) < 400 and not any(k in first_para.lower() for k in ("export", "import", "class ", "function ", "<div", "{", "}")):
                            conversation[-1]["content"] = first_para.strip()
                        else:
                            conversation[-1]["content"] = "Generating application files (interrupted by output token limit)."

                    conversation.append({
                        "role": "user",
                        "content": (
                            "âš ï¸ OUTPUT TOKEN LIMIT REACHED â€” GENERATION TRUNCATED:\n\n"
                            "Your previous response exceeded the output token limit and was truncated.\n"
                            "The files successfully written to disk so far are tracked in the File Manifest below.\n"
                            "Please continue by generating ONLY the remaining files that have NOT yet been written.\n"
                            "Generate ONE file at a time using structured `write_file` (do not attempt to generate all files at once)."
                        ),
                    })
                    continue

                # Continuation enforcement: if previous turn hit output ceiling, model MUST resume tool calls
                if was_truncated_previous_turn and iteration < (max_iterations - 2) and not is_question_mode:
                    was_truncated_previous_turn = False
                    log(f"âš ï¸ [Continuation Enforcement] Model emitted text instead of resuming file creation after truncation. Forcing continuation...")
                    workspace_summary = (
                        self._reality_guard.state.to_verified_summary()
                        if self._reality_guard else ""
                    )
                    conversation.append({
                        "role": "user",
                        "content": (
                            "CONTINUATION REQUIRED:\n\n"
                            "Your generation was interrupted by the output token limit in the previous turn.\n"
                            "Do NOT provide a plain text explanation, apologies, or stop yet.\n"
                            "Proceed immediately by issuing a structured `write_file` tool call for the next file.\n\n"
                            f"{workspace_summary}"
                        ),
                    })
                    continue

                # Check if model emitted fake tool syntax as plain text (Kimi / DeepSeek hallucination)
                has_fake, _ = (
                    self._reality_guard.detect_fake_tool_transcripts(assistant_content)
                    if self._reality_guard else (False, assistant_content)
                )
                if has_fake:
                    log("ðŸ›¡ï¸ [RealityGuard FIREWALL] Model emitted pseudo-tool syntax in content. "
                        "Rejected â€” no tool will be executed from plain text.")
                    # Prune the fake tool syntax from assistant message so it doesn't loop in history
                    if conversation and conversation[-1].get("role") == "assistant":
                        sanitized = _clean_pseudo_tools_from_text(conversation[-1].get("content", ""))
                        conversation[-1]["content"] = sanitized or "Attempted action without structured tool calling."

                    workspace_summary = (
                        self._reality_guard.state.to_verified_summary()
                        if self._reality_guard else ""
                    )
                    # Inject authoritative runtime correction as USER message
                    conversation.append({
                        "role": "user",
                        "content": (
                            "RUNTIME CORRECTION:\n\n"
                            "No filesystem changes occurred during your previous turn.\n"
                            "The files you may have described as created DO NOT EXIST on physical disk.\n"
                            "Do not assume any previous write succeeded.\n\n"
                            f"{workspace_summary}\n\n"
                            "Next action MUST be an actual structured tool call (e.g. write_file, write_files).\n"
                            "Plain-text tool syntax will not execute."
                        ),
                    })
                    continue

                # Check if plan was submitted via submit_plan
                if getattr(tool_executor, "submitted_plan", None) is not None:
                    result.final_text = assistant_content or json.dumps(tool_executor.submitted_plan)
                    result.files_changed = tool_executor.files_changed
                    result.conversation = conversation
                    log("ðŸ [Planning Complete] submit_plan received â€” exiting cleanly.")
                    return result

                # Check if this session actually has write/mutating tools
                has_write_tools = any(
                    (t.get("name") or t.get("function", {}).get("name")) in (
                        "write_file", "write_files", "replace_file_content", "batch_replace_file_content", "find_and_replace"
                    )
                    for t in (self._tools or [])
                )
                if not has_write_tools:
                    # READ-ONLY / PLANNING / REVIEWING SESSION:
                    # Model produced its text response/plan without tools â€” clean, immediate exit!
                    result.final_text = assistant_content
                    result.files_changed = tool_executor.files_changed
                    result.conversation = conversation
                    log("ðŸ [Read-Only Phase Finished] Clean exit.")
                    return result

                # If write tools are available but no files were written yet, prompt ONCE on first turn only
                is_question_mode = any("QUESTION MODE" in str(msg.get("content", "")) for msg in conversation[:3])
                has_batch_write = any((t.get("name") or t.get("function", {}).get("name")) == "write_files" for t in (self._tools or []))

                if has_write_tools and len(tool_executor.files_changed) == 0 and iteration == 0 and not is_question_mode:
                    prompt_msg = "Action required: Please create the necessary files using `write_file` (with 'path' and 'content') or `replace_file_content`."
                    log(f"âš ï¸ [Prompt] No files changed on first turn â€” prompting once: {prompt_msg}")
                    conversation.append({
                        "role": "user",
                        "content": prompt_msg,
                    })
                    continue

                # Mount Guard: Check if new components were created without updating src/App.jsx
                has_app_jsx = os.path.exists(os.path.join(str(self._workspace_path), "src", "App.jsx"))
                app_modified = any("App.jsx" in f for f in tool_executor.files_changed)
                has_new_subcomponents = any(
                    ("components" in f or "contexts" in f) for f in tool_executor.files_changed
                )
                if has_app_jsx and not app_modified and has_new_subcomponents and not getattr(self, "_mount_prompted", False) and iteration < (max_iterations - 1):
                    self._mount_prompted = True
                    new_files_str = ", ".join(tool_executor.files_changed)
                    mount_msg = (
                        f"Action required: You have created new components/contexts ({new_files_str}), "
                        "but you have NOT yet imported or mounted them in `src/App.jsx`!\n"
                        "Users will not see or be able to interact with the new feature unless it is rendered in `src/App.jsx`.\n"
                        "Please use `replace_file_content` or `write_file` now to import and mount these changes into `src/App.jsx`."
                    )
                    log(f"âš ï¸ [Mount Guard] Intercepting natural completion: new components created ({new_files_str}) but src/App.jsx untouched. Prompting to mount in App.jsx.")
                    conversation.append({
                        "role": "user",
                        "content": mount_msg,
                    })
                    continue

                # Clean natural exit â€” model responded with text answer, no more tool calls needed
                result.final_text = assistant_content
                result.files_changed = tool_executor.files_changed
                result.conversation = conversation
                result.stop_reason = "natural_completion"
                log(f"ðŸ [Tool Phase Finished] Model completed naturally at iteration {iteration + 1}. Changed {len(result.files_changed)} file(s).")
                return result

            # Reset truncation flag when real tool calls are made
            was_truncated_previous_turn = False

            # ================================================================
            # STEP 5: Reality Check â€” snapshot BEFORE executing this batch
            # ================================================================
            if self._reality_guard:
                self._reality_guard.capture_snapshot()

            # ================================================================
            # STEP 2: Runtime-Owned Tool Execution
            # Only the runtime executor appends tool results (role: tool_result).
            # Model cannot create or simulate tool results.
            # ================================================================
            tool_results: list[dict[str, Any]] = []
            for tc in tool_calls:
                tool_name = tc.get("name") or tc.get("function", {}).get("name") or tc.get("tool", "")
                print(f"[TOOL_DEBUG] raw tc keys: {list(tc.keys())} content: {repr(tc)[:300]}", flush=True)
                tool_input = (
                    tc.get("input")
                    or tc.get("function", {}).get("arguments")
                    or tc.get("args")
                    or tc.get("parameters")
                    or {}
                )
                if isinstance(tool_input, str):
                    try:
                        tool_input = json.loads(tool_input)
                    except Exception:
                        pass
                tool_id = tc.get("id") or tc.get("toolUseId") or f"call_{iteration}_{len(tool_results)}"

                log(f"ðŸ”§ [Tool Call] {tool_name}({_summarize_args(tool_input if isinstance(tool_input, dict) else {})})")

                result.tool_calls_made.append({
                    "tool": tool_name,
                    "input_summary": _summarize_args(tool_input if isinstance(tool_input, dict) else {}),
                    "iteration": iteration + 1,
                })

                if on_event:
                    desc = tool_name
                    is_file = False
                    if tool_name == "write_file":
                        target_p = tool_input.get("path", "") if isinstance(tool_input, dict) else ""
                        desc = f"Writing file {target_p.replace('/workspace/', '')}"
                        is_file = True
                    elif tool_name == "read_file":
                        target_p = tool_input.get("path", "") if isinstance(tool_input, dict) else ""
                        s_line = tool_input.get("start_line") if isinstance(tool_input, dict) else None
                        e_line = tool_input.get("end_line") if isinstance(tool_input, dict) else None
                        line_info = f" (lines {s_line}-{e_line})" if s_line and e_line else ""
                        desc = f"Reading {target_p.replace('/workspace/', '')}{line_info}"
                    elif tool_name == "find_and_replace":
                        target_p = tool_input.get("path", "") if isinstance(tool_input, dict) else ""
                        desc = f"Editing {target_p.replace('/workspace/', '')}"
                        is_file = True
                    elif tool_name == "replace_file_content":
                        target_p = tool_input.get("path", "") if isinstance(tool_input, dict) else ""
                        s_line = tool_input.get("start_line") if isinstance(tool_input, dict) else None
                        e_line = tool_input.get("end_line") if isinstance(tool_input, dict) else None
                        line_info = f" (lines {s_line}-{e_line})" if s_line and e_line else ""
                        desc = f"Patching {target_p.replace('/workspace/', '')}{line_info}"
                        is_file = True
                    elif tool_name == "batch_replace_file_content":
                        edits = tool_input.get("edits", []) if isinstance(tool_input, dict) else (tool_input if isinstance(tool_input, list) else [])
                        unique_files = len(set(e.get("path", "") for e in edits if isinstance(e, dict) and e.get("path")))
                        desc = f"Batch surgical patching: {len(edits)} edit(s) across {unique_files} file(s)"
                        is_file = True
                    elif tool_name == "check_syntax":
                        target_p = tool_input.get("path", "") if isinstance(tool_input, dict) else ""
                        desc = f"Validating syntax in {target_p.replace('/workspace/', '')}"
                        is_file = True
                    elif tool_name == "list_directory":
                        target_p = tool_input.get("path", "") if isinstance(tool_input, dict) else ""
                        desc = f"Inspecting workspace ({target_p.replace('/workspace', '') or 'root'})"
                    elif tool_name == "grep_search":
                        q = tool_input.get("query", "") if isinstance(tool_input, dict) else ""
                        desc = f"Searching for '{q}'" if q and q.strip() else ""
                    elif tool_name == "web_search":
                        q = tool_input.get("query", "") if isinstance(tool_input, dict) else ""
                        desc = f"Web research: {q}"
                    elif tool_name == "install_and_build":
                        desc = "Building application bundle"

                    if desc:
                        on_event("tool_called", {
                            "tool": tool_name,
                            "description": desc,
                            "is_file": is_file,
                            "iteration": iteration + 1,
                            "args": tool_input if isinstance(tool_input, dict) else {},
                        })

                # Execute tool through the runtime executor with anti-loop guard
                exec_result = self._execute_single_tool(tool_name, tool_input, tool_executor, iteration)

                if exec_result.get("truncation_detected") and on_event:
                    file_name = exec_result.get("file", "file")
                    line_num = exec_result.get("line", 0)
                    on_event("warning", {
                        "message": f"âš ï¸ Syntax error/truncation detected in `{file_name}` (line {line_num}). Asking the AI to fix or complete the file...",
                    })

                out_str = str(exec_result.get("content", ""))
                log(f"   Tool output:\n{out_str}")


                # Track file writes in the manifest
                if tool_name in ("write_file", "write_files") and not exec_result.get("is_error"):
                    self._track_written_files(tool_input, exec_result, iteration)

                # Conclude planning immediately when submit_plan is executed
                if tool_name == "submit_plan" and not exec_result.get("is_error"):
                    result.final_text = assistant_content or json.dumps(getattr(tool_executor, "submitted_plan", {}))
                    result.files_changed = tool_executor.files_changed
                    result.conversation = conversation
                    log(f"ðŸ [Planning Finished] submit_plan executed on iteration {iteration + 1} â€” concluding planning phase.")
                    return result

                # ============================================================
                # STEP 4: Post-Write Verification
                # Immediately stat() the file after every write tool execution.
                # If the file doesn't exist or is empty, return a StateVerificationError
                # to the model so it retries with a real corrected tool call.
                # ============================================================
                write_tools = ("write_file", "write_files", "find_and_replace", "replace_file_content", "batch_replace_file_content")
                if tool_name in write_tools and not exec_result.get("is_error") and self._reality_guard:
                    paths_to_verify: list[str] = []
                    if tool_name in ("write_file", "replace_file_content", "find_and_replace"):
                        p = tool_input.get("path", "") if isinstance(tool_input, dict) else ""
                        if p:
                            paths_to_verify.append(p)
                    elif tool_name == "write_files":
                        files_list = tool_input.get("files", []) if isinstance(tool_input, dict) else []
                        for f in files_list:
                            if isinstance(f, dict) and f.get("path"):
                                paths_to_verify.append(f["path"])
                    elif tool_name == "batch_replace_file_content":
                        edits_list = tool_input.get("edits", []) if isinstance(tool_input, dict) else []
                        for edit in edits_list:
                            if isinstance(edit, dict) and edit.get("path"):
                                paths_to_verify.append(edit["path"])

                    failed_verifications: list[str] = []
                    for verify_path in paths_to_verify:
                        ok, msg = self._reality_guard.verify_file_write(verify_path)
                        if not ok:
                            failed_verifications.append(msg)
                            log(f"   âŒ [PostWrite Verification FAILED] {msg}")
                        else:
                            log(f"   âœ… [PostWrite Verified] {msg}")

                    if failed_verifications:
                        # Override the tool result with a StateVerificationError
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": tool_id,
                            "tool_name": tool_name,
                            "tool_input": _summarize_args(tool_input if isinstance(tool_input, dict) else {}),
                            "content": (
                                "StateVerificationError: Write reported success but physical disk check failed.\n"
                                + "\n".join(failed_verifications)
                                + "\n\nPlease retry writing these files using a new write_file tool call."
                            ),
                            "is_error": True,
                        })
                        continue

                tool_res_content = exec_result.get("content", "")

                # delete_file completes its tracked task (plan actions: "delete")
                if (
                    tool_name == "delete_file"
                    and not exec_result.get("is_error")
                    and task_tracker
                    and isinstance(tool_input, dict)
                    and tool_input.get("path")
                ):
                    deleted_norm = str(tool_input["path"]).replace(str(self._workspace_path), "").replace("\\", "/").lstrip("/")
                    task_tracker.mark_file_completed(deleted_norm, clear_cache_callback=self._clear_inspected_cache)
                    log(f"ðŸ—‘ï¸ [Task Tracker] delete_file completed task for `{deleted_norm}`")
                    tool_res_content = (
                        f"{tool_res_content}\n"
                        "[Runtime: File deleted. Task checklist advanced â€” proceed to the next task, "
                        "or call install_and_build when all tasks are complete.]"
                    )

                if not exec_result.get("is_error") and tool_name in write_tools:
                    # Any successful edit re-arms the build: unlock the Build Redundancy Gate
                    # and clear the BUILD REPAIR REQUIRED banner.
                    self._files_modified_since_build += 1
                    self._consecutive_reads_since_build_failure = 0
                    self._last_build_failed = False
                    if task_tracker:
                        task_tracker.clear_build_failure()
                    tool_res_content = (
                        f"{tool_res_content}\n"
                        "[Runtime: File written and verified on disk. "
                        "Proceed to the next file or run install_and_build when all files are complete.]"
                    )
                elif not exec_result.get("is_error") and tool_name == "install_dependencies":
                    self._clear_build_repair_state()
                    if task_tracker:
                        task_tracker.mark_install_completed(clear_cache_callback=self._clear_inspected_cache)
                    tool_res_content = (
                        f"{tool_res_content}\n"
                        "[Runtime: Dependencies installed successfully via npm install. "
                        "Task checklist advanced â€” proceed to the NEXT task shown in the checklist.]"
                    )
                elif not exec_result.get("is_error") and tool_name == "install_and_build":
                    self._clear_build_repair_state()
                    if task_tracker:
                        task_tracker.mark_install_completed(clear_cache_callback=self._clear_inspected_cache)
                        if task_tracker.is_all_file_tasks_completed():
                            task_tracker.mark_verification_completed(clear_cache_callback=self._clear_inspected_cache)
                            tool_res_content = (
                                f"{tool_res_content}\n"
                                "[Runtime: Build succeeded. All planned tasks are completed and application is compiled. "
                                "Provide your final response to complete the session.]"
                            )
                        else:
                            # Model called install_and_build prematurely (e.g. to install packages or intermediate test)
                            # Reset built_successfully so intermediate build does NOT trigger the terminal funnel early!
                            tool_executor._built_successfully = False
                            tool_res_content = (
                                f"{tool_res_content}\n"
                                "[Runtime: Intermediate build/install succeeded with 0 errors. "
                                "Notice: You still have pending file tasks in your checklist! "
                                "Do NOT stop here — proceed to implement the NEXT task shown in the checklist.]"
                            )
                    else:
                        tool_res_content = (
                            f"{tool_res_content}\n"
                            "[Runtime: Build succeeded. Application compiled and ready. "
                            "Provide your final response to complete the session.]"
                        )
                elif exec_result.get("is_error") and tool_name == "install_and_build":
                    err_text = str(tool_res_content or "")
                    # CRITICAL FIX: Do NOT treat internal guard blocks or loop protection as genuine compiler errors!
                    if "install_and_build is BLOCKED" in err_text or "Loop Protection Activated" in err_text or "Notice:" in err_text:
                        log("⚠️ [Build Error Handler] Intercepted internal block/notice — ignoring from compiler error tracking.")
                    else:
                        self._last_build_failed = True
                        self._files_modified_since_build = 0
                        self._consecutive_reads_since_build_failure = 0
                        self._last_build_error_files = _extract_compiler_error_files(err_text)
                        self._last_build_error_summary = _summarize_compiler_error(err_text)
                        if task_tracker:
                            task_tracker.reset_verification()
                            task_tracker.record_build_failure(self._last_build_error_summary, self._last_build_error_files)
                        tool_res_content = (
                            f"{tool_res_content}\n\n"
                            "[Runtime: Build failed with compiler error above. "
                            "Inspect the affected file(s) and apply fixes using `replace_file_content` or `write_file`, "
                            "then run `install_and_build` to verify.]"
                        )

                # Step 2: Tool results are ONLY created by the runtime executor.
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "tool_name": tool_name,
                    "tool_input": _summarize_args(tool_input if isinstance(tool_input, dict) else {}),
                    "content": tool_res_content,
                    "is_error": exec_result.get("is_error", False),
                })

                # Update Active Inspected Files Cache and consecutive read tracking
                if tool_name in ("read_file", "get_generated_file") and not exec_result.get("is_error"):
                    p = tool_input.get("path", "") if isinstance(tool_input, dict) else ""
                    norm_p = p.replace(str(self._workspace_path), "").replace("\\", "/").lstrip("/")

                    # Defense-in-depth: Never cache lockfiles, node_modules, or build artifacts
                    forbidden_cache_files = {"package-lock.json", "yarn.lock", "pnpm-lock.yaml", "bun.lockb"}
                    is_forbidden = (
                        any(part in ("node_modules", ".git", ".agent_history", "dist", "build", ".next", "__pycache__") for part in norm_p.split("/"))
                        or any(norm_p.endswith(f) for f in forbidden_cache_files)
                    )

                    if not is_forbidden:
                        # Load the clean, full physical file from disk so slices never overwrite or corrupt the cache
                        full_disk_content = None
                        try:
                            full_disk_path = os.path.join(str(self._workspace_path), norm_p)
                            if os.path.isfile(full_disk_path):
                                with open(full_disk_path, "r", encoding="utf-8", errors="replace") as f:
                                    full_disk_content = f.read()
                        except Exception:
                            pass

                        # Store full file in cache (cap at 25,000 chars / ~350 lines to prevent token explosion)
                        max_full_file_chars = 25_000
                        if full_disk_content is not None:
                            if len(full_disk_content) <= max_full_file_chars:
                                self._inspected_files[norm_p] = full_disk_content
                            else:
                                d_lines = full_disk_content.split("\n")
                                self._inspected_files[norm_p] = "\n".join(d_lines[:350]) + f"\n// ... ({len(d_lines)-350} more lines omitted for token efficiency)"
                        else:
                            res_text = str(exec_result.get("content", ""))
                            if len(res_text) <= max_full_file_chars:
                                self._inspected_files[norm_p] = res_text
                            else:
                                lines = res_text.split("\n")
                                self._inspected_files[norm_p] = "\n".join(lines[:350]) + f"\n// ... ({len(lines)-350} more lines omitted for token efficiency)"
                        # Record when this file was read (1-based iteration for readability)
                        self._inspected_files_iter[norm_p] = iteration + 1

                    self._consecutive_reads += 1
                elif tool_name in ("list_directory", "grep_search"):
                    self._consecutive_reads += 1
                elif tool_name in write_tools or tool_name in ("delete_file", "install_dependencies", "install_and_build"):
                    if not exec_result.get("is_error"):
                        self._consecutive_reads = 0
                        self._last_tool_sig = ""
                        self._duplicate_call_count = 0
                    if not exec_result.get("is_error") or exec_result.get("rolled_back"):
                        # Update cache with latest content from disk (or clean rolled-back content)
                        paths_written = []
                        if tool_name in ("write_file", "replace_file_content", "find_and_replace"):
                            p = tool_input.get("path", "") if isinstance(tool_input, dict) else ""
                            if p:
                                paths_written.append(p)
                        elif tool_name == "write_files" and isinstance(tool_input, dict):
                            for f in tool_input.get("files", []):
                                if isinstance(f, dict) and f.get("path"):
                                    paths_written.append(f["path"])
                        elif tool_name == "batch_replace_file_content" and isinstance(tool_input, dict):
                            for e in tool_input.get("edits", []):
                                if isinstance(e, dict) and e.get("path"):
                                    paths_written.append(e["path"])

                        for wp in paths_written:
                            norm_wp = wp.replace(str(self._workspace_path), "").replace("\\", "/").lstrip("/")
                            # Read freshly-written content FIRST so acceptance checks run against real disk state
                            fresh_content: str | None = None
                            full_disk_path = os.path.join(str(self._workspace_path), norm_wp)
                            if os.path.isfile(full_disk_path):
                                try:
                                    with open(full_disk_path, "r", encoding="utf-8", errors="replace") as f:
                                        fresh_content = f.read()
                                except Exception:
                                    fresh_content = None
                            if task_tracker and not exec_result.get("is_error"):
                                task_tracker.mark_file_completed(norm_wp, clear_cache_callback=self._clear_inspected_cache)
                            if fresh_content is not None and len(fresh_content) <= 25_000:
                                self._inspected_files[norm_wp] = fresh_content
                                self._inspected_files_iter[norm_wp] = iteration + 1

                    # When write_file successfully resolves a rollback-blocked file,
                    # inject a "done â€” now build" directive so the AI doesn't wander off reading more files.
                    write_unblocked = exec_result.get("write_unblocked", [])
                    if write_unblocked and not exec_result.get("is_error"):
                        unblocked_str = ", ".join(f"`{p}`" for p in write_unblocked)
                        log(f"âœ… [Rollback-Block Resolved] write_file succeeded for {unblocked_str}. Injecting done directive.")
                        # Append a strong done directive to the current tool result to steer exit
                        for tr in tool_results:
                            if tr.get("tool_name") == "write_file" and not tr.get("is_error"):
                                tr["content"] = (
                                    tr.get("content", "") + "\n\n"
                                    f"âœ… ROLLBACK RESOLVED: {unblocked_str} has been successfully rewritten and verified.\n"
                                    "The fix is complete. Do NOT read any more files.\n"
                                    "Next step: call `install_and_build` to verify the build, then provide your final response."
                                )
                                break

            # ================================================================
            # STEP 5: Snapshot Diff Reality Check â€” after all tools in this batch
            # If 0 files changed on a turn where writes were expected, inject a
            # hard RUNTIME CORRECTION rather than silently continuing.
            # ================================================================
            write_tool_names = {"write_file", "write_files", "find_and_replace", "replace_file_content"}
            batch_claimed_writes = any(
                (tc.get("name") or tc.get("function", {}).get("name") or tc.get("tool", "")) in write_tool_names
                for tc in tool_calls
            )
            if self._reality_guard and batch_claimed_writes:
                diff_summary, correction = self._reality_guard.verify_post_iteration(
                    claimed_actions=True
                )
                if correction:
                    workspace_summary = self._reality_guard.state.to_verified_summary()
                    log(f"ðŸ›¡ï¸ [RealityGuard] 0-diff detected after write batch. "
                        f"Injecting RUNTIME CORRECTION.")
                    # Replace tool_results with the hard correction so model sees real state
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": f"reality_check_{iteration}",
                        "tool_name": "reality_guard",
                        "content": (
                            "RUNTIME CORRECTION:\n\n"
                            "No filesystem changes occurred during your previous turn.\n"
                            "The files you may have described as created DO NOT EXIST on physical disk.\n"
                            "Do not assume any previous write succeeded.\n\n"
                            f"{workspace_summary}\n\n"
                            "Next action MUST be an actual structured tool call.\n"
                            "Use `write_file` with 'path' and 'content' to create the next file.\n"
                            "Do NOT call write_files with an empty payload."
                        ),
                        "is_error": True,
                    })
                else:
                    log(f"âœ… [RealityGuard] Snapshot diff confirmed: "
                        f"{diff_summary['total_changed']} file(s) changed on disk.")
                    # Emit file-changed events for UI visibility
                    if on_event and diff_summary["total_changed"] > 0:
                        on_event("files_changed", {
                            "created": diff_summary["created"],
                            "modified": diff_summary["modified"],
                            "deleted": diff_summary["deleted"],
                            "iteration": iteration + 1,
                        })

            # Append runtime-owned tool results to conversation (role: user with tool_result content)
            conversation.append({
                "role": "user",
                "content": tool_results,
            })
            self._log_to_transcript("tool_results", tool_results, metadata={"iteration": iteration + 1})

        changed_files_list = list(tool_executor.files_changed) if tool_executor else []
        if changed_files_list:
            files_preview = ", ".join(f"`{f}`" for f in changed_files_list[:5])
            if len(changed_files_list) > 5:
                files_preview += f" (+{len(changed_files_list) - 5} more)"
            result.final_text = (
                f"### Agent Paused â€” Reached Iteration Limit\n\n"
                f"The agent reached the maximum iteration limit ({max_iterations} steps) for this task turn.\n\n"
                f"- **Progress so far**: Successfully modified {len(changed_files_list)} file(s) ({files_preview}).\n"
                f"- **Next steps**: Click the **Continue** button below (or enter 'continue') to proceed with the remaining changes."
            )
        else:
            result.final_text = (
                f"### Agent Paused â€” Reached Iteration Limit\n\n"
                f"The agent reached the maximum iteration limit ({max_iterations} steps) for this task turn before completing all changes.\n\n"
                f"Please click the **Continue** button below (or enter 'continue') to resume execution."
            )
        result.files_changed = tool_executor.files_changed
        result.conversation = conversation
        log(f"âš ï¸ [Tool Loop Max Iterations] Reached limit of {max_iterations} iterations")
        return result

    def generate_single_file(
        self,
        *,
        system: str,
        prompt: str,
        target_path: str,
        tool_executor: Any,
        tools: list[dict[str, Any]] | None = None,
        on_event: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> tuple[bool, str]:
        """Generate exactly one file deterministically without runaway iteration loops.
        
        Terminates immediately once target_path is verified on disk.
        Allows at most 1 inspection turn (if get_generated_file called) or 1 continuation turn if truncated.
        Returns: (success: bool, file_content: str)
        """
        effective_tools = tools if tools is not None else self._tools
        ws = self._workspace_path
        abs_target = os.path.join(ws, target_path.lstrip("/\\")) if not os.path.isabs(target_path) else target_path

        def _verify_target() -> tuple[bool, str]:
            if os.path.exists(abs_target) and os.path.getsize(abs_target) > 20:
                try:
                    with open(abs_target, "r", encoding="utf-8", errors="replace") as f:
                        c = f.read()
                    return True, c
                except Exception:
                    pass
            return False, ""

        conversation = [{"role": "user", "content": prompt}]
        log(f"ðŸŽ¯ [SingleFileGen] Generating `{target_path}`...")

        max_turns = 3  # Turn 0: direct write OR inspect. Turn 1: write after inspect OR truncation continuation. Turn 2: final continuation.
        for turn in range(max_turns):
            if turn > 0:
                log(f"   [SingleFileGen Continuation] Completing `{target_path}`...")

            # Format full prompt string for Bourntec API
            parts = []
            if system:
                parts.append(f"System: {system}")
            for msg in conversation:
                role = msg.get("role", "user")
                c = msg.get("content", "")
                if isinstance(c, list):
                    text_pieces = []
                    for item in c:
                        if isinstance(item, dict) and item.get("type") == "tool_result":
                            t_name = item.get("tool_name", "")
                            raw = str(item.get("content", ""))
                            text_pieces.append(f"{t_name} output:\n{raw}")
                        elif isinstance(item, str):
                            text_pieces.append(item)
                    if text_pieces:
                        parts.append(f"{role.capitalize()}:\n" + "\n".join(text_pieces))
                elif isinstance(c, str) and c.strip():
                    parts.append(f"{role.capitalize()}: {c.strip()}")

            prompt_text = "\n\n".join(parts)

            try:
                response = self._llm_client.call_ai(
                    prompt_text,
                    tools=effective_tools,
                    model=self._model,
                    max_tokens=self._max_tokens,
                )
            except Exception as exc:
                log(f"âŒ [SingleFileGen] Error calling AI: {exc}")
                return False, ""

            tool_calls = response.tool_calls
            assistant_content = response.content or ""
            stop_reason = response.stop_reason

            conversation.append({
                "role": "assistant",
                "content": assistant_content or "Generating file.",
            })

            # Stream thinking if present
            thought_text = response.reasoning or (assistant_content if tool_calls else "")
            if thought_text and on_event:
                clean_thought = thought_text.strip()
                if clean_thought:
                    on_event("thinking", {
                        "reasoning": clean_thought,
                        "thought_summary": clean_thought.split("\n")[0][:180],
                        "iteration": 1,
                    })

            # Case A: Truncation detected
            is_truncated = (
                response.output_tokens >= (self._max_tokens - 200 if self._max_tokens > 1000 else 7900)
                or stop_reason in ("length", "max_tokens")
            )
            if is_truncated and not tool_calls:
                log(f"âš ï¸ [SingleFileGen] Output truncation at {response.output_tokens} tokens. Prompting continuation...")
                if on_event:
                    on_event("warning", {"message": f"Output truncated for `{target_path}`. Completing file..."})
                conversation.append({
                    "role": "user",
                    "content": f"Your output for `{target_path}` was truncated. Please complete the remaining code for `{target_path}` using `write_file` now."
                })
                continue

            # Case B: AI executed tool calls
            if tool_calls:
                tool_results = []
                for tc in tool_calls:
                    t_name = tc.get("name") or tc.get("function", {}).get("name") or tc.get("tool", "")
                    t_input = tc.get("input") or tc.get("function", {}).get("arguments") or tc.get("args") or {}
                    if isinstance(t_input, str):
                        try:
                            t_input = json.loads(t_input)
                        except Exception:
                            pass
                    t_id = tc.get("id") or f"call_{turn}"

                    log(f"ðŸ”§ [SingleFileGen Tool] {t_name}({_summarize_args(t_input if isinstance(t_input, dict) else {})})")
                    if on_event:
                        desc = f"Writing {target_path}" if t_name in ("write_file", "write_files") else "Inspecting file"
                        on_event("tool_called", {
                            "tool": t_name,
                            "description": desc,
                            "is_file": True,
                            "iteration": 1,
                            "args": t_input if isinstance(t_input, dict) else {},
                        })

                    exec_res = self._execute_single_tool(t_name, t_input, tool_executor, turn)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": t_id,
                        "tool_name": t_name,
                        "content": str(exec_res.get("content", "")),
                        "is_error": exec_res.get("is_error", False),
                    })

                # Check if target file was written and verified on disk
                ok, content = _verify_target()
                if ok:
                    log(f"âœ… [SingleFileGen] Verified `{target_path}` on physical disk ({len(content)} chars). Clean exit!")
                    if self._file_manifest:
                        rel = target_path.replace(str(ws), "").lstrip("/\\")
                        self._file_manifest.add_or_update_file(rel, content, 1, f"Generated file {rel}")
                    if on_event:
                        on_event("files_changed", {
                            "created": [target_path],
                            "modified": [],
                            "deleted": [],
                            "iteration": 1,
                        })
                    return True, content

                # If tool was get_generated_file, append result and allow next turn to write
                conversation.append({"role": "user", "content": tool_results})
                continue

            # Case C: No tool calls emitted â€” check if model output code inside markdown block
            code_match = re.search(r'```(?:jsx?|tsx?|javascript|typescript|json|html|css)?\s*\n(.*?)```', assistant_content, re.DOTALL)
            if code_match:
                extracted_code = code_match.group(1).strip()
                if len(extracted_code) > 20:
                    log(f"ðŸ“ [SingleFileGen] Extracted code block for `{target_path}` ({len(extracted_code)} chars). Writing to disk...")
                    tool_executor.execute("write_file", {"path": target_path, "content": extracted_code})
                    ok, content = _verify_target()
                    if ok:
                        log(f"âœ… [SingleFileGen] Verified `{target_path}` on physical disk ({len(content)} chars). Clean exit!")
                        if self._file_manifest:
                            rel = target_path.replace(str(ws), "").lstrip("/\\")
                            self._file_manifest.add_or_update_file(rel, content, 1, f"Generated file {rel}")
                        if on_event:
                            on_event("files_changed", {
                                "created": [target_path],
                                "modified": [],
                                "deleted": [],
                                "iteration": 1,
                            })
                        return True, content

            ok, content = _verify_target()
            if ok:
                return True, content

            if turn == 0:
                log(f"âš ï¸ [SingleFileGen] No tool call emitted. Nudging model to issue write_file...")
                conversation.append({
                    "role": "user",
                    "content": f"Action required: You MUST issue a structured `write_file` tool call to write `{target_path}`."
                })

        ok, content = _verify_target()
        return ok, content

    # ------------------------------------------------------------------
    # Tool execution & anti-loop interception
    # ------------------------------------------------------------------

    def _try_phase_escalation(self, tool_name: str, tool_executor: Any) -> bool:
        """Dynamically decide whether a phase-blocked tool should be promoted.

        Fully state-derived — no hardcoded tool lists or phase names:
        1. The tool must actually exist in the runtime registry (real, executable).
        2. There must be live evidence the agent needs it right now:
           an active task tracker with unfinished file tasks, or a workspace
           where this agent has already written files (execution posture).
        Post-build wrap-up (all tasks done + successful build) never escalates,
        so the completion firewall keeps working unchanged.
        """
        # 1. Tool must be real and executable through the MCP registry.
        registry = getattr(tool_executor, "registry", None) or getattr(tool_executor, "_registry", None)
        if registry is not None:
            try:
                if registry.get_mcp_mapping(tool_name) is None:
                    return False
            except Exception:
                return False

        # 2a. Unfinished file work in the active task checklist.
        tracker = getattr(self, "_active_task_tracker", None)
        if tracker is not None:
            try:
                if not tracker.is_all_file_tasks_completed():
                    return True
            except Exception:
                pass

        # 2b. Agent already mutated the workspace — it is in execution posture,
        # so further writes are a continuation of real work, not planning.
        try:
            files_changed = getattr(tool_executor, "files_changed", None)
            if files_changed:
                return True
        except Exception:
            pass

        # 2c. Write/repair tools permitted when fixing errors or active execution
        write_tools = ("write_file", "write_files", "replace_file_content", "batch_replace_file_content")
        if tool_name in write_tools:
            if getattr(self, "_last_build_failed", False) or getattr(tool_executor, "last_build_failed", False):
                return True
            if registry is not None and registry.get_mcp_mapping(tool_name) is not None:
                return True

        return False

    def _execute_single_tool(
        self,
        tool_name: str,
        tool_input: Any,
        tool_executor: Any,
        iteration: int = 0,
    ) -> dict[str, Any]:
        """Execute a single tool through the runtime executor with whitelist enforcement."""
        allowed_names = {
            t.get("name") if isinstance(t, dict) else getattr(t, "name", "")
            for t in (self._tools or [])
        }
        escalated_tools = getattr(self, "_escalated_tools", None)
        if escalated_tools is None:
            escalated_tools = set()
            self._escalated_tools = escalated_tools
        if (
            allowed_names
            and tool_name not in allowed_names
            and tool_name not in escalated_tools
            and not self._try_phase_escalation(tool_name, tool_executor)
        ):
            log(f"ðŸ›‘ [Tool Whitelist Firewall] Denied '{tool_name}' â€” not permitted in this phase. Allowed: {sorted(list(allowed_names))}")
            return {
                "type": "tool_result",
                "content": (
                    f"Error: Tool '{tool_name}' is forbidden during this phase.\n"
                    f"Allowed tools for this phase: {sorted(list(allowed_names))}\n"
                    "Please execute ONLY the allowed tools."
                ),
                "is_error": True,
            }

        if allowed_names and tool_name not in allowed_names and tool_name not in escalated_tools:
            # Reaching here means _try_phase_escalation approved the promotion.
            escalated_tools.add(tool_name)
            log(f"\U0001F513 [Phase Escalation] '{tool_name}' promoted into the active phase from live task state.")

        # Post-Build Action Firewall: If build already succeeded with 0 errors, block exploratory read tools (strictly when all file tasks are done)
        if getattr(tool_executor, "built_successfully", False):
            active_tracker = getattr(self, "_active_task_tracker", None)
            if not active_tracker or active_tracker.is_all_file_tasks_completed():
                if tool_name in ("read_file", "list_directory", "grep_search", "get_generated_file", "check_syntax"):
                    log(f"🛑 [Post-Build Firewall] Intercepted '{tool_name}' after successful build and checklist completion. Directing model to complete.")
                    return {
                        "type": "tool_result",
                        "content": (
                            "Notice: The application build has already succeeded with 0 errors and all planned checklist tasks are completed. "
                            "Further file inspection is not required. "
                            "Please provide your final high-level functional summary for business users now to conclude the session."
                        ),
                        "is_error": False,
                    }
                elif tool_name in ("install_and_build", "install_dependencies"):
                    log(f"🛑 [Post-Build Firewall] Intercepted redundant '{tool_name}' after successful build and checklist completion. Directing model to complete.")
                    return {
                        "type": "tool_result",
                        "content": (
                            "Notice: The application build has already succeeded with 0 errors and all planned checklist tasks are completed. "
                            "The application is fully compiled and the preview is live. "
                            "Do NOT re-run build or installation. Please provide your final high-level functional summary for business users now to conclude the session."
                        ),
                        "is_error": False,
                    }


        # Task Checklist Action Guard: Intercept read attempts on files planned to be created or deleted
        active_tracker = getattr(self, "_active_task_tracker", None)
        if active_tracker and active_tracker.active_task_index < len(active_tracker.tasks):
            curr_task = active_tracker.tasks[active_tracker.active_task_index]
            c_file = curr_task.get("file", "").replace("\\", "/").lstrip("/")
            c_action = curr_task.get("action", "edit")
            target_p = tool_input.get("path", "") if isinstance(tool_input, dict) else ""
            norm_tp = target_p.replace(str(self._workspace_path), "").replace("\\", "/").lstrip("/")
            is_target_active_file = norm_tp and (norm_tp == c_file or c_file.endswith(norm_tp) or norm_tp.endswith(c_file))

            c_desc = str(curr_task.get("description", "")).lower()

            if c_action == "create" and tool_name in ("read_file", "get_generated_file") and is_target_active_file:
                # Check if the file actually exists on physical disk already
                full_disk_check = os.path.join(str(self._workspace_path), norm_tp)
                if os.path.isfile(full_disk_check):
                    log(f"ℹ️ [Create Guard] `{c_file}` already exists on physical disk ({os.path.getsize(full_disk_check)} bytes). Allowing read and converting task action to 'edit'.")
                    curr_task["action"] = "edit"
                else:
                    log(f"🛑 [Create Guard] Intercepted read of uncreated file '{c_file}'. Directing model to write.")
                    return {
                        "type": "tool_result",
                        "content": (
                            f"Notice: `{c_file}` is a NEW file planned to be created (`action: 'create'`). "
                            "It does not exist yet on disk. Do not read or inspect non-existent files. "
                            f"Please call `write_file` now to create `{c_file}` with full, production-ready code."
                        ),
                        "is_error": False,
                    }
            elif c_action == "install" and tool_name not in ("install_dependencies", "install_and_build"):
                log(f"ðŸ›‘ [Install Guard] Intercepted '{tool_name}' during install task. Directing model to call install_dependencies.")
                return {
                    "type": "tool_result",
                    "content": (
                        "Notice: The current active task is to install dependencies (action: 'install'). "
                        "Please call `install_dependencies` now to run npm install. "
                        "Do NOT read or write files until dependencies are installed."
                    ),
                    "is_error": False,
                }
            elif c_action == "delete" and tool_name in ("read_file", "get_generated_file") and is_target_active_file:
                log(f"ðŸ›‘ [Delete Guard] Intercepted read of file marked for deletion '{c_file}'. Directing model to delete.")
                return {
                    "type": "tool_result",
                    "content": (
                        f"Notice: `{c_file}` is marked for deletion (`action: 'delete'`). "
                        f"Please call `delete_file` immediately to remove `{c_file}` without reading it."
                    ),
                    "is_error": False,
                }

        # ---- Build Redundancy Gate: no re-build without an edit after a failure ----
        if tool_name == "install_and_build" and getattr(self, "_last_build_failed", False):
            if self._files_modified_since_build == 0:
                affected = ", ".join(f"`{f}`" for f in (self._last_build_error_files or [])) or "the affected file(s)"
                log("🛑 [Build Redundancy Gate] Blocked install_and_build — no file edits since last build failure.")
                return {
                    "type": "tool_result",
                    "content": (
                        "Error: install_and_build is BLOCKED. The build failed with this exact compiler error "
                        "and NO file has been modified since. Re-running the build without an edit is guaranteed "
                        "to fail identically and is forbidden.\n\n"
                        f"Compiler error: {self._last_build_error_summary}\n"
                        f"Affected file(s): {affected}\n\n"
                        "You MUST edit the affected file(s) NOW using `replace_file_content` or `write_file`. "
                        "The build gate unlocks automatically after your first successful edit."
                    ),
                    "is_error": True,
                }

        # ---- Build Repair Read Cap: after a failed build, cap exploratory reads at 3 ----
        # Reads of the file(s) named in the build error are always allowed (focused repair).
        if (
            getattr(self, "_last_build_failed", False)
            and tool_name in ("read_file", "list_directory", "grep_search", "get_generated_file")
        ):
            target_p = tool_input.get("path", "") if isinstance(tool_input, dict) else ""
            norm_tp = str(target_p).replace(str(self._workspace_path), "").replace("\\", "/").lstrip("/")
            is_affected = any(
                norm_tp and (f == norm_tp or f.endswith(norm_tp) or norm_tp.endswith(f))
                for f in (self._last_build_error_files or [])
            )
            if not is_affected:
                self._consecutive_reads_since_build_failure += 1
                if self._consecutive_reads_since_build_failure > 3:
                    log("🛑 [Build Repair Read Cap] Blocked exploratory read after build failure (limit 3).")
                    return {
                        "type": "tool_result",
                        "content": (
                            "Error: Inspection limit reached after the build failure — you already have enough context.\n"
                            f"Failing file(s): {', '.join(self._last_build_error_files or ['the affected file(s)'])}\n"
                            f"Compiler error: {self._last_build_error_summary}\n\n"
                            "Apply your fix NOW with `replace_file_content` or `write_file`. "
                            "Further exploratory reads are blocked until you edit."
                        ),
                        "is_error": True,
                    }

        # Consecutive Read Circuit Breaker: Block runaway read loops (>= 8 consecutive reads with 0 writes)
        if (
            self._consecutive_reads >= 8
            and tool_name in ("read_file", "list_directory", "grep_search", "get_generated_file")
        ):
            log(f"🛑 [Read Circuit Breaker] Intercepted read/search tool '{tool_name}' ({self._consecutive_reads} consecutive reads). Forcing write/edit.")
            return {
                "type": "tool_result",
                "content": (
                    f"Error: Consecutive read limit reached ({self._consecutive_reads} consecutive inspection calls). "
                    "You have already gathered sufficient context. Further read/search calls are blocked. "
                    "You MUST now proceed to apply the planned changes using `write_file` or `replace_file_content`."
                ),
                "is_error": True,
            }

        # Progress Guard: Consecutive duplicate call detection & anti-oscillation
        try:
            input_repr = json.dumps(tool_input, sort_keys=True) if isinstance(tool_input, (dict, list)) else str(tool_input)
        except Exception:
            input_repr = str(tool_input)
        call_sig = f"{tool_name}:{input_repr}"

        if call_sig == getattr(self, "_last_tool_sig", ""):
            self._duplicate_call_count = getattr(self, "_duplicate_call_count", 0) + 1
        else:
            self._last_tool_sig = call_sig
            self._duplicate_call_count = 1

        # Track read-inspection tools vs write tools to stop ping-pong read loops
        inspection_tools = ("read_file", "list_directory", "check_syntax", "get_generated_file", "file_exists")
        write_tools = ("write_file", "write_files", "replace_file_content", "batch_replace_file_content", "run_command", "install_and_build", "run_build")

        if tool_name in inspection_tools:
            self._consecutive_inspection_count = getattr(self, "_consecutive_inspection_count", 0) + 1
        elif tool_name in write_tools:
            self._consecutive_inspection_count = 0
            if hasattr(self, "_file_inspection_counts"):
                self._file_inspection_counts.clear()

        # Extract target file path for inspection tracking
        target_file_cand = None
        if isinstance(tool_input, dict):
            target_file_cand = tool_input.get("path") or tool_input.get("file")
        elif isinstance(tool_input, str) and ("/" in tool_input or "\\" in tool_input):
            target_file_cand = tool_input

        if not hasattr(self, "_file_inspection_counts"):
            self._file_inspection_counts = {}

        if target_file_cand and tool_name in ("read_file", "check_syntax"):
            clean_tf = str(target_file_cand).replace("\\", "/").strip()
            self._file_inspection_counts[clean_tf] = self._file_inspection_counts.get(clean_tf, 0) + 1
            if self._file_inspection_counts[clean_tf] >= 3:
                log(f"🛑 [Progress Guard] Intercepted repetitive inspection of {clean_tf}")
                return {
                    "type": "tool_result",
                    "content": (
                        f"Notice: You have inspected `{clean_tf}` {self._file_inspection_counts[clean_tf]} times. "
                        f"The complete file contents and syntax status are already in your conversation context above. "
                        f"DO NOT re-read or re-check this file. Proceed directly to apply your changes "
                        f"using `replace_file_content` or `write_file` now."
                    ),
                    "is_error": False,
                }

        if getattr(self, "_consecutive_inspection_count", 0) >= 5:
            log(f"🛑 [Progress Guard] Intercepted runaway inspection sequence ({self._consecutive_inspection_count} turns)")
            return {
                "type": "tool_result",
                "content": (
                    f"Notice: You have executed {self._consecutive_inspection_count} consecutive inspection tools without modifying any file. "
                    f"All necessary workspace state is in your conversation context. "
                    f"Proceed directly to write or update your code using `write_file`, `write_files`, or `replace_file_content` now."
                ),
                "is_error": False,
            }

        if self._duplicate_call_count >= 3:
            log(f"🛑 [Progress Guard] Duplicate tool call rejected ({tool_name}, repeated 3x consecutively)")
            return {
                "type": "tool_result",
                "content": (
                    f"Error: Duplicate tool call rejected by Progress Guard. "
                    f"You have executed '{tool_name}' with identical parameters 3 times consecutively without taking further action. "
                    f"The result is already in your context above. You MUST now proceed to make your edits with replace_file_content or take a different action."
                ),
                "is_error": True,
            }

        result = tool_executor.execute(
            tool_name, tool_input if isinstance(tool_input, (dict, list, str)) else {}
        )


        if getattr(self, "_duplicate_call_count", 1) == 2 and not result.get("is_error"):
            existing_c = str(result.get("content", ""))
            result["content"] = (
                f"{existing_c}\n\n"
                "[Notice: You have executed this exact tool call twice consecutively. "
                "The requested information is already in your context. "
                "Please proceed with editing using replace_file_content or write_file.]"
            )

        # Cap get_generated_file responses at 120 lines to prevent inspection token explosion.
        # Full file content (e.g. 25KB DataTable.jsx) injected as a tool result adds ~6,400 input
        # tokens, leaving almost no room for App.jsx output and causing truncation at the 8K ceiling.
        if tool_name == "get_generated_file":
            raw_content = result.get("content", "") if isinstance(result, dict) else str(result)
            if isinstance(raw_content, str):
                lines = raw_content.split("\n")
                max_inspection_lines = 120
                if len(lines) > max_inspection_lines:
                    truncated = "\n".join(lines[:max_inspection_lines])
                    omitted = len(lines) - max_inspection_lines
                    truncated += f"\n// ... ({omitted} more lines â€” use this file's exports as shown above)"
                    if isinstance(result, dict):
                        result = {**result, "content": truncated}
                    else:
                        result = {"content": truncated}
                    log(f"âœ‚ï¸  [SingleFileGen] get_generated_file truncated to {max_inspection_lines} lines (saved ~{omitted * 40} chars)")

        return result

    # ------------------------------------------------------------------
    # File manifest tracking
    # ------------------------------------------------------------------

    def _track_written_files(
        self, tool_input: dict, exec_result: dict, iteration: int
    ) -> None:
        """Track files that were successfully written to the manifest."""
        # handle write_file (single file)
        if "path" in tool_input and "content" in tool_input:
            path = tool_input["path"]
            content = tool_input["content"]
            self._file_manifest.track_file(path, content, iteration)
            log(f"ðŸ“‹ [File Manifest] Tracking: {path} ({len(content)} chars)")

        # handle write_files (batch)
        if "files" in tool_input and isinstance(tool_input["files"], list):
            for f in tool_input["files"]:
                if isinstance(f, dict) and "path" in f and "content" in f:
                    self._file_manifest.track_file(f["path"], f["content"], iteration)
                    log(f"ðŸ“‹ [File Manifest] Tracking: {f['path']} ({len(f['content'])} chars)")

    # ------------------------------------------------------------------
    # Smart compaction methods
    # ------------------------------------------------------------------

    def _compact_tool_result(self, raw_res: str, is_err: bool, tool_use_id: str, iteration: int) -> str:
        """Create a meaningful summary of an old tool result instead of truncating."""
        if is_err:
            # For errors, keep the first meaningful line
            first_line = raw_res.strip().split("\n")[0][:200]
            return f"[Previous error: '{first_line}' â€” check workspace if unresolved]"

        # For write_file/write_files results, check if the file is in our manifest
        if len(raw_res) < 5000 and ("files_written" in raw_res or "written" in raw_res.lower()):
            if raw_res.strip().startswith("{"):
                try:
                    data = json.loads(raw_res)
                    files = data.get("files", [])
                    if files:
                        file_list = ", ".join(
                            f"{f.get('path', '?')} ({f.get('size', '?')} chars)"
                            for f in files[:5]
                        )
                        return f"[Wrote {len(files)} file(s): {file_list} â€” tracked in file manifest]"
                except (json.JSONDecodeError, AttributeError):
                    pass

        # For list_directory results, summarize what was found
        if len(raw_res) < 5000 and raw_res.strip().startswith("[") and "name" in raw_res and "type" in raw_res:
            try:
                items = json.loads(raw_res)
                if isinstance(items, list):
                    dirs = [i["name"] for i in items if i.get("type") == "directory"]
                    files = [i["name"] for i in items if i.get("type") == "file"]
                    parts = []
                    if dirs:
                        parts.append(f"dirs: {', '.join(dirs[:8])}")
                    if files:
                        parts.append(f"files: {', '.join(files[:8])}")
                    return f"[Workspace contains: {'; '.join(parts)}]"
            except (json.JSONDecodeError, AttributeError):
                pass

        # For grep/search results, keep a meaningful preview
        if len(raw_res) > COMPACTED_TOOL_RESULT_MAX:
            # Keep first 2-3 lines that are meaningful
            lines = [l.strip() for l in raw_res.strip().split("\n") if l.strip()]
            preview = " | ".join(lines[:3])[:COMPACTED_TOOL_RESULT_MAX]
            return f"[Search result ({len(raw_res)} chars): {preview}...]"

        # For small results, keep as-is
        return raw_res

    def _compact_assistant_message(self, raw_str: str, iteration: int) -> str:
        """Summarize an old assistant message preserving key decisions and removing any tool syntax."""
        cleaned = _clean_pseudo_tools_from_text(raw_str)
        if len(cleaned) <= COMPACTED_ASSISTANT_MAX:
            return cleaned

        # Try to extract the key parts: plan/decisions and follow-ups
        parts = []

        # Keep the first paragraph (usually the plan/summary)
        first_para = cleaned.split("\n\n")[0] if "\n\n" in cleaned else cleaned[:400]
        if first_para.strip():
            parts.append(first_para.strip()[:400])

        # If we have a "Now let me" or "I'll" follow-up, keep it
        followups = re.findall(r'(?:Now|Next|Then|I\'ll|Let me)\s+[^\n]{10,100}', cleaned)
        if followups:
            parts.append("Next: " + followups[0])

        summary = " | ".join(parts) if parts else cleaned[:COMPACTED_ASSISTANT_MAX]
        return summary[:COMPACTED_ASSISTANT_MAX] + f" [summarized from {len(cleaned)} chars]"

    def _aggressive_compact(self, prompt_text: str, system: str) -> str:
        """When over token budget, aggressively compact while preserving file manifest."""
        parts = prompt_text.split("\n\n")
        
        # Always keep the system prompt and file manifest
        manifest_start = prompt_text.find("FILES WRITTEN THIS SESSION:")
        manifest_end = prompt_text.find("\n\n", manifest_start) if manifest_start >= 0 else -1
        
        if manifest_start >= 0:
            manifest_section = prompt_text[manifest_start:manifest_end] if manifest_end > manifest_start else prompt_text[manifest_start:]
        else:
            manifest_section = ""
        
        # Rebuild with aggressive compaction on everything except manifest
        compacted_parts = []
        for part in parts:
            # Skip the manifest section (we'll add it back at the end)
            if "FILES WRITTEN THIS SESSION:" in part:
                continue
            
            # Aggressively compact any remaining large parts
            if len(part) > 2000:
                # Keep first 500 chars and note it was compacted
                compacted_parts.append(part[:500] + f"\n[...compacted from {len(part)} chars to save tokens...]")
            else:
                compacted_parts.append(part)
        
        result = "\n\n".join(compacted_parts)
        
        # Re-append the manifest (never compact this!)
        if manifest_section:
            result += f"\n\n{manifest_section}"
        
        return result

    def _compact_conversation(self, conversation: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Merge old messages when conversation exceeds MAX_CONVERSATION_MESSAGES.
        
        Keeps the RECENT_WINDOW messages intact, merges everything before
        that into a single summary message. Preserves the file manifest
        injection point (always last user message).
        """
        if len(conversation) <= MAX_CONVERSATION_MESSAGES:
            return conversation

        # Keep recent window + 2 (one user, one assistant minimum)
        keep_recent = RECENT_WINDOW + 2
        old_messages = conversation[:-keep_recent]
        recent_messages = conversation[-keep_recent:]

        # Summarize old messages into a single context block
        summary_parts = ["[Context: Earlier in this session, the following happened]"]
        tools_called = []
        key_decisions = []

        for msg in old_messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if isinstance(content, list):
                # Tool result â€” extract operation name without syntax
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "tool_result":
                        tool_name = item.get("tool_name", "operation")
                        tools_called.append(tool_name)
            elif isinstance(content, str) and role == "assistant":
                # Extract key decisions from assistant messages
                clean_msg = _clean_pseudo_tools_from_text(content)
                if len(clean_msg) > 50:
                    first_line = clean_msg.split("\n")[0][:120]
                    key_decisions.append(first_line)

        if tools_called:
            summary_parts.append(f"Operations executed: {len(tools_called)} ({', '.join(dict.fromkeys(tools_called)[:5])})")
        if key_decisions:
            summary_parts.append(f"Key decisions: {'; '.join(key_decisions[:3])}")

        summary_msg = {
            "role": "user",
            "content": "\n".join(summary_parts) + "\n\nProceeding from where we left off.",
        }

        compacted = [summary_msg] + recent_messages
        log(f"[Conversation Compaction] {len(conversation)} messages -> {len(compacted)} messages "
            f"(merged {len(old_messages)} old messages into summary)")
        return compacted

    def _rollover_to_new_session_context(
        self,
        conversation: list[dict[str, Any]],
        system: str,
        tool_executor: ToolExecutor,
        task_tracker: Any | None,
        iteration: int,
    ) -> list[dict[str, Any]]:
        """Summarize conversation history and roll over into a clean session chat.
        
        Triggered when context window reaches limits (e.g. 128k tokens or prompt tokens > limit).
        Archives inspected files to disk, compresses past turns into a structured brief,
        and returns a fresh conversation list so the agent completes its work without token exhaustion.
        """
        log(f"🔄 [Session Rollover] Context approaching window limit ({self._max_prompt_tokens:,} tokens). "
            f"Consolidating prior context into new clean session at step {iteration + 1}...")

        # 1. Archive inspected files to disk to preserve history without context cost
        try:
            hist_dir = os.path.join(self._workspace_path, ".agent_history")
            os.makedirs(hist_dir, exist_ok=True)
            archive_file = os.path.join(hist_dir, "session_rollover_archive.json")
            with open(archive_file, "w", encoding="utf-8") as f:
                json.dump({
                    "iteration": iteration + 1,
                    "inspected_files": self._inspected_files,
                    "files_changed": list(tool_executor.files_changed),
                    "timestamp": datetime.utcnow().isoformat(),
                }, f, indent=2)
        except Exception as e:
            log(f"Warning writing session rollover archive: {e}")

        # 2. Extract initial user requirements
        initial_prompt = ""
        for m in conversation:
            if m.get("role") == "user" and isinstance(m.get("content"), str):
                initial_prompt = m["content"]
                break

        # 3. Extract completed operations & key actions
        files_written = list(tool_executor.files_changed)

        # 4. Build task tracker status if available
        tracker_status = ""
        if task_tracker and hasattr(task_tracker, "render_prompt_banner"):
            tracker_status = task_tracker.render_prompt_banner()

        # 5. Extract manifest summary
        manifest_str = self._file_manifest.to_manifest_string()

        # 6. Compose clean rollover brief
        rollover_prompt = (
            "## 🔄 SESSION CONTEXT ROLLOVER (Fresh Session Context Resumed)\n\n"
            "Earlier conversation context reached the model context window limit (128k tokens).\n"
            "All previous progress has been summarized below so you can complete the work without token amnesia.\n\n"
            f"### 1. Original User Task & Objective:\n{initial_prompt[:2500]}\n\n"
            f"### 2. Files Modified / Written So Far ({len(files_written)} files):\n"
            + (", ".join(f"`{f}`" for f in files_written[:30]) if files_written else "None yet") + "\n\n"
        )
        if tracker_status:
            rollover_prompt += f"### 3. Task Progress & Checklist:\n{tracker_status}\n\n"
        if manifest_str:
            rollover_prompt += f"### 4. Verified Workspace Files:\n{manifest_str[:3000]}\n\n"

        rollover_prompt += (
            "### 5. Immediate Directive:\n"
            "All previous progress is preserved above. Continue executing the remaining subtasks.\n"
            "Use structured tools (`write_file`, `replace_file_content`, `install_and_build`) to finalize the implementation."
        )

        # Clear active inspected files cache to free context tokens
        self._inspected_files.clear()
        self._inspected_files_iter.clear()

        # Reset conversation to this single authoritative brief
        new_conversation = [{"role": "user", "content": rollover_prompt}]
        log(f"✅ [Session Rollover] Clean session initialized with consolidated progress summary. Resuming agent loop...")
        return new_conversation


def _summarize_args(args: dict) -> str:
    """Create full summary of tool arguments for logging."""
    parts = []
    for key, value in args.items():
        if key in ("content", "file_content"):
            parts.append(f"{key}=<{len(str(value))} chars>")
        elif key == "replace_text":
            parts.append(f"replace_text=<{len(str(value))} chars>")
        elif key == "files" and isinstance(value, list):
            file_paths = [
                f.get("path", "?") if isinstance(f, dict) else str(f)[:30]
                for f in value[:10]
            ]
            parts.append(f"files=[{', '.join(file_paths)}] ({len(value)} files)")
        elif key in ("edits", "replacements") and isinstance(value, list):
            parts.append(f"{key}=<{len(value)} items>")
        else:
            val_str = str(value)
            if len(val_str) > 100:
                val_str = val_str[:100] + "..."
            parts.append(f"{key}={val_str}")
    return ", ".join(parts)

