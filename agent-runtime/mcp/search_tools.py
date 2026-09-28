"""Search MCP tools — grep_search and find_and_replace for the workspace.

These tools let Claude find exact code sections and make precise surgical edits
to existing codebases, instead of rewriting entire files.

Architecture: Registered in MCPServer as the 'search' module. All path operations
are sandboxed within the project workspace.
"""
from __future__ import annotations

import fnmatch
import os
import re
from pathlib import Path
from typing import Any

from mcp.server import ToolResult
from runtime.sandbox import Sandbox
from runtime.resource_limits import ResourceLimits


# File extensions to search (skip binary files)
_TEXT_EXTENSIONS: set[str] = {
    ".js", ".jsx", ".ts", ".tsx", ".json", ".css", ".scss", ".less",
    ".html", ".htm", ".md", ".txt", ".yaml", ".yml", ".toml",
    ".py", ".sh", ".bash", ".env", ".gitignore", ".eslintrc",
    ".prettierrc", ".svg", ".xml", ".conf", ".cfg", ".ini",
    ".vue", ".svelte", ".astro", ".mjs", ".cjs",
}

# Max results to prevent enormous output
_MAX_RESULTS = 50

# Max file size to search (skip very large files)
_MAX_SEARCH_FILE_SIZE = 2_000_000  # 2MB


class SearchTools:
    """grep_search and find_and_replace scoped to the project workspace."""

    def __init__(self, workspace_path: str) -> None:
        self._sandbox = Sandbox(workspace_path)
        self._limits = ResourceLimits()

    def _search_path_with_pattern(
        self,
        search_root: Path,
        compiled: re.Pattern,
        include_globs: list[str] | None = None,
        max_matches: int = _MAX_RESULTS,
    ) -> tuple[list[dict[str, Any]], int]:
        """Internal helper to scan file or directory with a compiled regex pattern."""
        matches: list[dict[str, Any]] = []
        files_searched = 0

        if search_root.is_file():
            if search_root.name in {"package-lock.json", "yarn.lock", "pnpm-lock.yaml", "bun.lockb"}:
                return [], 0
            files_searched = 1
            return self._search_file(search_root, compiled), files_searched

        for root, dirs, files in os.walk(str(search_root)):
            dirs[:] = [
                d for d in dirs
                if d not in {"node_modules", ".git", "dist", "build", "__pycache__", ".next", ".agent_history"}
            ]

            for filename in files:
                if filename in {"package-lock.json", "yarn.lock", "pnpm-lock.yaml", "bun.lockb"}:
                    continue
                if len(matches) >= max_matches:
                    break

                filepath = Path(root) / filename
                if filepath.suffix.lower() not in _TEXT_EXTENSIONS:
                    continue

                if include_globs:
                    if not any(fnmatch.fnmatch(filename, g) for g in include_globs):
                        continue

                try:
                    if filepath.stat().st_size > _MAX_SEARCH_FILE_SIZE:
                        continue
                except OSError:
                    continue

                file_matches = self._search_file(filepath, compiled)
                matches.extend(file_matches)
                files_searched += 1

        return matches, files_searched

    def grep_search(
        self,
        pattern: str,
        path: str | None = None,
        case_insensitive: bool = True,
        is_regex: bool = False,
        include_globs: list[str] | None = None,
    ) -> ToolResult:
        """Search for a text pattern across files in the workspace.

        Returns a list of matches with file path, line number, and line content.
        Features multi-tier fallback: exact -> multi-word stem -> regex -> keyword fallback.
        """
        search_root = self._sandbox.safe_resolve(path or str(self._sandbox.workspace_root))

        # Block search into forbidden directories or lockfiles
        if any(p in {"node_modules", ".git", ".agent_history", "dist", "build"} for p in Path(path or "").parts):
            return ToolResult(success=True, data=[])
        if Path(path or "").name in {"package-lock.json", "yarn.lock", "pnpm-lock.yaml", "bun.lockb"}:
            return ToolResult(success=True, data=[])

        # Compile pattern
        flags = re.IGNORECASE if case_insensitive else 0
        try:
            if is_regex:
                compiled = re.compile(pattern, flags)
            else:
                compiled = re.compile(re.escape(pattern), flags)
        except re.error as exc:
            return ToolResult(success=False, error=f"Invalid regex pattern: {exc}")

        # Tier 1: Direct search (literal or regex)
        matches, files_searched = self._search_path_with_pattern(search_root, compiled, include_globs)

        # Tier 2: If literal search found 0 matches and pattern contains multiple words,
        # try flexible word-stem regex (handles singular/plural and arbitrary intra-phrase spacing)
        if not matches and not is_regex:
            words = [w for w in re.findall(r"\w+", pattern) if len(w) > 1]
            if len(words) >= 2:
                try:
                    stemmed_parts = [re.escape(w.rstrip("sS")) + r"s?" for w in words]
                    stemmed_pattern = r"\b" + r"\b[\s\S]{0,40}\b".join(stemmed_parts) + r"\b"
                    stemmed_compiled = re.compile(stemmed_pattern, re.IGNORECASE)
                    matches, _ = self._search_path_with_pattern(search_root, stemmed_compiled, include_globs)
                except re.error:
                    pass

        # Tier 3: If literal search found 0 matches but pattern has regex characters, try regex
        if not matches and not is_regex and any(c in pattern for c in ("|", ".*", "\\d", "\\w", "(", ")", "[", "]", "+")):
            try:
                regex_compiled = re.compile(pattern, flags)
                matches, _ = self._search_path_with_pattern(search_root, regex_compiled, include_globs)
            except re.error:
                pass

        # Tier 4: Keyword fallback — if still 0 matches, search for substantive domain words
        if not matches and not is_regex:
            words = [w for w in re.findall(r"[a-zA-Z]{4,}", pattern)]
            stopwords = {"section", "page", "view", "coming", "soon", "please", "component", "button", "with", "from", "that", "this", "here"}
            substantive = [w for w in words if w.lower() not in stopwords]
            target_words = substantive if substantive else words
            if target_words:
                best_word = max(target_words, key=len)
                try:
                    word_compiled = re.compile(r"\b" + re.escape(best_word.rstrip("sS")) + r"s?\b", re.IGNORECASE)
                    matches, _ = self._search_path_with_pattern(search_root, word_compiled, include_globs)
                except re.error:
                    pass

        # Format output
        truncated = len(matches) >= _MAX_RESULTS
        if truncated:
            matches = matches[:_MAX_RESULTS]

        return ToolResult(
            success=True,
            data={
                "matches": matches,
                "total_matches": len(matches),
                "files_searched": files_searched,
                "truncated": truncated,
                "pattern": pattern,
            },
        )

    def find_and_replace(
        self,
        path: str,
        search_text: str,
        replace_text: str,
        occurrence: int | None = None,
    ) -> ToolResult:
        """Find exact text in a file and replace it.

        Args:
            path: Absolute path to the file.
            search_text: Exact text to find (must match including whitespace).
            replace_text: Replacement text.
            occurrence: Which occurrence to replace (1-based). 0 or None = all.

        Returns:
            ToolResult with number of replacements made.
        """
        safe_path = self._sandbox.safe_resolve(path)

        if not safe_path.exists():
            return ToolResult(success=False, error=f"File not found: {path}")
        if not safe_path.is_file():
            return ToolResult(success=False, error=f"Not a file: {path}")

        try:
            content = safe_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return ToolResult(success=False, error=f"Could not read file: {exc}")

        # Count occurrences
        count = content.count(search_text)
        if count == 0:
            # Attempt multi-strategy deterministic match fallback before failing
            from runtime.patcher import CodePatcher
            ok, patched_content, strategy = CodePatcher.patch_content(content, search_text, replace_text)
            if ok:
                new_content = patched_content
                replacements = 1
            else:
                return ToolResult(
                    success=False,
                    error=(
                        f"Search text not found in {path} ({strategy}). "
                        f"Please inspect the file with read_file, "
                        f"or use replace_file_content / write_file."
                    ),
                )
        else:
            # Replace exact
            if occurrence is None or occurrence == 0:
                new_content = content.replace(search_text, replace_text)
                replacements = count
            else:
                if occurrence > count:
                    return ToolResult(
                        success=False,
                        error=f"Occurrence {occurrence} requested but only {count} found.",
                    )
                new_content = self._replace_nth(content, search_text, replace_text, occurrence)
                replacements = 1

        # Write back
        try:
            safe_path.write_text(new_content, encoding="utf-8")
        except OSError as exc:
            return ToolResult(success=False, error=f"Could not write file: {exc}")

        return ToolResult(
            success=True,
            data={
                "path": str(safe_path),
                "replacements": replacements,
                "search_text_preview": search_text[:100],
                "replace_text_preview": replace_text[:100],
            },
        )

    def _apply_single_edit_to_content(
        self,
        content: str,
        path: str,
        target_content: str,
        replacement_content: str,
        start_line: int | None = None,
        end_line: int | None = None,
    ) -> tuple[str, bool, str]:
        """Apply a single replacement chunk to in-memory file content string."""
        from runtime.patcher import CodePatcher
        success, new_content, strategy = CodePatcher.patch_content(
            content,
            target_content,
            replacement_content,
            start_line=start_line,
            end_line=end_line,
        )
        if success:
            return new_content, True, strategy
        return content, False, f"Target content not found in {path} ({strategy})"

    def replace_file_content(
        self,
        path: str,
        target_content: str,
        replacement_content: str,
        start_line: int | None = None,
        end_line: int | None = None,
    ) -> ToolResult:
        """Replace a target block of text within specific line boundaries (precision edit standard).
        
        Args:
            path: Absolute path to the file to edit.
            target_content: The exact text chunk to replace.
            replacement_content: The replacement content.
            start_line: Optional starting line number (1-based, inclusive).
            end_line: Optional ending line number (1-based, inclusive).
        """
        safe_path = self._sandbox.safe_resolve(path)

        if not safe_path.exists():
            return ToolResult(success=False, error=f"File not found: {path}")
        if not safe_path.is_file():
            return ToolResult(success=False, error=f"Not a file: {path}")

        try:
            content = safe_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return ToolResult(success=False, error=f"Could not read file: {exc}")

        new_content, ok, strategy_or_err = self._apply_single_edit_to_content(
            content,
            path,
            target_content,
            replacement_content,
            start_line,
            end_line,
        )

        if not ok:
            return ToolResult(
                success=False,
                error=(
                    f"{strategy_or_err}. Please inspect the file with read_file "
                    f"{f'(start_line={start_line}, end_line={end_line})' if start_line and end_line else ''} "
                    f"to check current code, or use write_file to provide the complete updated file content."
                ),
            )

        # Write back
        try:
            safe_path.write_text(new_content, encoding="utf-8")
        except OSError as exc:
            return ToolResult(success=False, error=f"Could not write file: {exc}")

        total_lines = len(new_content.splitlines())
        return ToolResult(
            success=True,
            data={
                "path": str(safe_path),
                "replacements": 1,
                "strategy": strategy_or_err,
                "start_line": start_line,
                "end_line": end_line,
                "message": f"Successfully patched {path} via {strategy_or_err} (lines {start_line or 1}-{end_line or total_lines})",
            },
        )

    def batch_replace_file_content(
        self,
        edits: list[dict[str, Any]] | dict[str, Any] | str,
    ) -> ToolResult:
        """Apply multiple surgical code replacements across ONE or MORE files in a single tool call.
        
        Args:
            edits: List of dicts, each specifying:
                   - path: File path (e.g. src/App.jsx)
                   - target_content (or target / old_str): Exact code to replace
                   - replacement_content (or replacement / new_str): Replacement code
                   - start_line: Optional 1-based start line
                   - end_line: Optional 1-based end line
        """
        import json

        if isinstance(edits, str):
            try:
                edits = json.loads(edits)
            except Exception:
                return ToolResult(success=False, error="Invalid JSON for edits parameter")

        if isinstance(edits, dict):
            edits_list = edits.get("edits", edits.get("replacements", []))
            if not isinstance(edits_list, list):
                edits_list = [edits]
        elif isinstance(edits, list):
            edits_list = edits
        else:
            return ToolResult(success=False, error="edits must be a list of edit objects")

        if not edits_list:
            return ToolResult(success=False, error="No edits provided in batch_replace_file_content")

        # Group edits by file path
        by_path: dict[str, list[dict[str, Any]]] = {}
        for item in edits_list:
            if not isinstance(item, dict):
                continue
            p = item.get("path") or item.get("file_path") or item.get("file")
            if p:
                by_path.setdefault(p, []).append(item)

        if not by_path:
            return ToolResult(success=False, error="No valid file paths found in edits list")

        results = []
        errors = []
        total_applied = 0

        for path, file_edits in by_path.items():
            safe_path = self._sandbox.safe_resolve(path)
            if not safe_path.exists():
                errors.append(f"File not found: {path}")
                continue
            if not safe_path.is_file():
                errors.append(f"Not a file: {path}")
                continue

            try:
                content = safe_path.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                errors.append(f"Could not read {path}: {exc}")
                continue

            current_content = content
            file_applied = 0

            for edit in file_edits:
                target = edit.get("target_content") or edit.get("target") or edit.get("old_str") or edit.get("search")
                replacement = edit.get("replacement_content") or edit.get("replacement") or edit.get("new_str") or edit.get("replace")
                if target is None or replacement is None:
                    continue

                s_line = edit.get("start_line")
                e_line = edit.get("end_line")

                new_content, ok, err = self._apply_single_edit_to_content(
                    current_content,
                    path,
                    target,
                    replacement,
                    s_line,
                    e_line,
                )

                if ok:
                    current_content = new_content
                    file_applied += 1
                else:
                    errors.append(err)

            if file_applied > 0:
                try:
                    safe_path.write_text(current_content, encoding="utf-8")
                    total_applied += file_applied
                    results.append({
                        "path": str(safe_path),
                        "status": "success",
                        "edits_applied": file_applied,
                    })
                except OSError as exc:
                    errors.append(f"Could not write {path}: {exc}")

        if total_applied == 0 and errors:
            return ToolResult(
                success=False,
                error="Batch replace failed:\n" + "\n".join(errors),
            )

        return ToolResult(
            success=True,
            data={
                "status": "success",
                "total_edits_applied": total_applied,
                "files_modified": len(results),
                "results": results,
                "warnings": errors if errors else [],
                "message": f"Successfully applied {total_applied} surgical edit(s) across {len(results)} file(s).",
            },
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _replace_normalized(self, original_text: str, search: str, replace: str) -> str | None:
        """Fallback that matches lines ignoring leading/trailing whitespace differences."""
        orig_lines = [line.strip() for line in original_text.splitlines()]
        search_lines = [line.strip() for line in search.splitlines() if line.strip()]
        if not search_lines:
            return None

        # Filter out completely empty lines from original for matching index mapping
        orig_raw_lines = original_text.splitlines(keepends=True)
        search_len = len(search_lines)

        for i in range(len(orig_lines) - search_len + 1):
            # Check non-empty window
            window = [orig_lines[i + j] for j in range(search_len) if orig_lines[i + j]]
            if len(window) == search_len and window == search_lines:
                before = "".join(orig_raw_lines[:i])
                after = "".join(orig_raw_lines[i + search_len:])
                res = before + replace + ("\n" if not replace.endswith("\n") else "") + after
                return res

        return None

    def _replace_fuzzy(self, original_text: str, search: str, replace: str, min_similarity: float = 0.80) -> str | None:
        """Fuzzy replacement using line similarity scoring when exact formatting differs."""
        orig_raw_lines = original_text.splitlines(keepends=True)
        orig_lines = [line.strip() for line in original_text.splitlines()]
        search_lines = [line.strip() for line in search.splitlines() if line.strip()]
        if not search_lines or len(orig_lines) < len(search_lines):
            return None

        search_len = len(search_lines)
        best_score = 0.0
        best_idx = -1

        for i in range(len(orig_lines) - search_len + 1):
            matched = sum(1 for j in range(search_len) if orig_lines[i + j] == search_lines[j])
            score = matched / search_len
            if score > best_score:
                best_score = score
                best_idx = i

        if best_score >= min_similarity and best_idx != -1:
            before = "".join(orig_raw_lines[:best_idx])
            after = "".join(orig_raw_lines[best_idx + search_len:])
            return before + replace + ("\n" if not replace.endswith("\n") else "") + after

        return None

    def _search_file(self, filepath: Path, pattern: re.Pattern) -> list[dict[str, Any]]:
        """Search a single file for the pattern. Returns list of match dicts."""
        matches: list[dict[str, Any]] = []
        try:
            content = filepath.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return matches

        rel_path = str(filepath.relative_to(self._sandbox.workspace_root))

        for line_num, line in enumerate(content.splitlines(), start=1):
            if pattern.search(line):
                matches.append({
                    "file": rel_path,
                    "line": line_num,
                    "content": line.rstrip()[:500],  # truncate very long lines
                })
                if len(matches) >= _MAX_RESULTS:
                    break

        return matches

    def _replace_nth(self, text: str, search: str, replace: str, n: int) -> str:
        """Replace the nth occurrence (1-based) of search in text."""
        idx = -1
        for _ in range(n):
            idx = text.find(search, idx + 1)
            if idx == -1:
                return text  # not enough occurrences
        return text[:idx] + replace + text[idx + len(search):]

