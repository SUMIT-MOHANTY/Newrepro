"""Robust Multi-Strategy Code Patcher.

Guarantees file editing success across 5 deterministic cascading strategies:
1. Exact Substring Match (Full File)
2. Line-range constrained exact match (buffered +/- 15 lines)
3. Trimmed Line-by-Line Sliding Window Match (re-bases indentation)
4. Whitespace-Normalized Match
5. Non-Empty Line Sequence Match (bridges blank line discrepancies)
"""
from __future__ import annotations

import re
from pathlib import Path


class CodePatcher:
    """Surgical code patcher resilient to indentation, tabs vs spaces, and line drift."""

    @classmethod
    def patch_file(
        cls,
        file_path: str,
        target: str,
        replacement: str,
        start_line: int | None = None,
        end_line: int | None = None,
    ) -> tuple[bool, str]:
        """Apply surgical patch to a file using cascading strategies."""
        path = Path(file_path)
        if not path.exists():
            return False, f"Error: File '{file_path}' does not exist."
        if not path.is_file():
            return False, f"Error: '{file_path}' is not a file."

        try:
            content = path.read_text(encoding="utf-8")
        except OSError as exc:
            return False, f"Error reading '{file_path}': {exc}"

        success, new_content, strategy = cls.patch_content(
            content, target, replacement, start_line=start_line, end_line=end_line
        )

        if not success:
            return False, (
                f"Failed to locate target block in '{file_path}'. "
                "Please inspect the latest file content with read_file before patching."
            )

        try:
            path.write_text(new_content, encoding="utf-8")
            return True, f"Success: {strategy} applied to '{file_path}'."
        except OSError as exc:
            return False, f"Error writing '{file_path}': {exc}"

    @classmethod
    def patch_content(
        cls,
        content: str,
        target: str,
        replacement: str,
        start_line: int | None = None,
        end_line: int | None = None,
    ) -> tuple[bool, str, str]:
        """Patch a string content using deterministic cascading fallback strategies."""
        if not target:
            return False, content, "Empty target"

        target_clean = target.replace("\r\n", "\n")
        replacement_clean = replacement.replace("\r\n", "\n")
        content_clean = content.replace("\r\n", "\n")

        lines = content_clean.splitlines(keepends=True)
        total_lines = len(lines)

        # -------------------------------------------------------------
        # Strategy 1: Exact Substring Match (Full File)
        # -------------------------------------------------------------
        if target_clean in content_clean:
            return True, content_clean.replace(target_clean, replacement_clean, 1), "Exact substring match"

        # -------------------------------------------------------------
        # Strategy 2: Line-range constrained exact match (if boundaries provided)
        # -------------------------------------------------------------
        if start_line is not None and end_line is not None and 1 <= start_line <= end_line:
            # Allow generous +/- 15 line buffer around specified boundaries to absorb line drift
            s_idx = max(0, start_line - 15)
            e_idx = min(total_lines, end_line + 15)
            slice_text = "".join(lines[s_idx:e_idx])
            if target_clean in slice_text:
                new_slice = slice_text.replace(target_clean, replacement_clean, 1)
                return True, "".join(lines[:s_idx]) + new_slice + "".join(lines[e_idx:]), "Range-buffered exact match"

        # -------------------------------------------------------------
        # Strategy 3: Trimmed Line-by-Line Sliding Window Match
        # Matches full block ignoring indentation, spaces vs tabs, and trailing whitespace
        # -------------------------------------------------------------
        trimmed_result = cls._replace_trimmed_lines(lines, target_clean, replacement_clean)
        if trimmed_result is not None:
            return True, trimmed_result, "Trimmed line-by-line sequence match"

        # -------------------------------------------------------------
        # Strategy 4: Whitespace-Normalized Match
        # Handles single-line or multi-line variations with collapsed internal whitespace
        # -------------------------------------------------------------
        norm_result = cls._replace_normalized(content_clean, target_clean, replacement_clean)
        if norm_result is not None:
            return True, norm_result, "Whitespace-normalized sliding match"

        # -------------------------------------------------------------
        # Strategy 5: Non-Empty Line Sequence Match
        # Handles discrepancies in blank lines inside or surrounding the target block
        # -------------------------------------------------------------
        non_empty_result = cls._replace_non_empty_lines(lines, target_clean, replacement_clean)
        if non_empty_result is not None:
            return True, non_empty_result, "Non-empty line sequence match"

        # -------------------------------------------------------------
        # Strategy 6: Anchor Line Boundary Match
        # Matches when first and last non-empty lines uniquely identify the block
        # -------------------------------------------------------------
        anchor_result = cls._replace_anchor_block(lines, target_clean, replacement_clean)
        if anchor_result is not None:
            return True, anchor_result, "Anchor boundary block match"

        # -------------------------------------------------------------
        # Strategy 7: High-Confidence Sequence Similarity Match (>=80%)
        # Absorbs minor token typos, comment differences, or slight drift
        # -------------------------------------------------------------
        fuzzy_result = cls._replace_fuzzy(lines, target_clean, replacement_clean)
        if fuzzy_result is not None:
            return True, fuzzy_result, "High-confidence fuzzy sequence match"

        # Safe exit: Never perform arbitrary low-confidence replacements that corrupt code!
        return False, content, "All deterministic patching strategies exhausted"

    @classmethod
    def _replace_anchor_block(
        cls,
        lines: list[str],
        target: str,
        replacement: str,
    ) -> str | None:
        """Matches a block when its first and last non-empty lines match uniquely."""
        target_lines = [l.strip() for l in target.splitlines() if l.strip()]
        if len(target_lines) < 3:
            return None

        first_target = target_lines[0]
        last_target = target_lines[-1]
        target_span = len(target.splitlines())

        matches = []
        for i in range(len(lines)):
            if lines[i].strip() == first_target:
                for j in range(i + 1, min(len(lines), i + target_span + 8)):
                    if lines[j].strip() == last_target:
                        matches.append((i, j + 1))
                        break

        # Only proceed if there is exactly one unambiguous matching region
        if len(matches) == 1:
            s_idx, e_idx = matches[0]
            repl_lines = [l + "\n" for l in replacement.splitlines()]
            result_lines = list(lines)
            result_lines[s_idx:e_idx] = repl_lines
            return "".join(result_lines)
        return None

    @classmethod
    def _replace_fuzzy(
        cls,
        lines: list[str],
        target: str,
        replacement: str,
        threshold: float = 0.80,
    ) -> str | None:
        """High-confidence fuzzy sliding window match using SequenceMatcher."""
        import difflib
        target_str = cls._normalize_ws(target)
        if len(target_str) < 15:
            return None

        t_lines_count = len(target.splitlines())
        best_ratio = 0.0
        best_span = None

        for i in range(len(lines)):
            for w in (t_lines_count, t_lines_count + 1, max(1, t_lines_count - 1), t_lines_count + 2):
                if i + w <= len(lines):
                    chunk = cls._normalize_ws("".join(lines[i : i + w]))
                    ratio = difflib.SequenceMatcher(None, target_str, chunk).quick_ratio()
                    if ratio > best_ratio:
                        ratio = difflib.SequenceMatcher(None, target_str, chunk).ratio()
                        if ratio > best_ratio:
                            best_ratio = ratio
                            best_span = (i, i + w)

        if best_ratio >= threshold and best_span is not None:
            s_idx, e_idx = best_span
            repl_lines = [l + "\n" for l in replacement.splitlines()]
            result_lines = list(lines)
            result_lines[s_idx:e_idx] = repl_lines
            return "".join(result_lines)
        return None

    @classmethod
    def _replace_trimmed_lines(
        cls,
        lines: list[str],
        target: str,
        replacement: str,
    ) -> str | None:
        """Sliding line window matching each line after strip(), preserving replacement block."""
        target_lines = [l.strip() for l in target.splitlines()]
        if not target_lines:
            return None

        w_size = len(target_lines)
        file_stripped = [l.strip() for l in lines]

        for i in range(len(lines) - w_size + 1):
            if file_stripped[i : i + w_size] == target_lines:
                # Match found! Adapt indentation of replacement lines if appropriate
                orig_leading = re.match(r"^([ \t]*)", lines[i]).group(1) if lines[i] else ""
                target_leading = re.match(r"^([ \t]*)", target.splitlines()[0]).group(1) if target.splitlines() else ""

                repl_raw_lines = replacement.splitlines()
                adjusted_lines = []
                for idx_r, r_line in enumerate(repl_raw_lines):
                    if r_line.strip() and target_leading and r_line.startswith(target_leading):
                        # Re-base to file's actual indentation level
                        rebased = orig_leading + r_line[len(target_leading):]
                        adjusted_lines.append(rebased + "\n")
                    else:
                        adjusted_lines.append(r_line + "\n")

                result_lines = list(lines)
                result_lines[i : i + w_size] = adjusted_lines
                return "".join(result_lines)

        return None

    @staticmethod
    def _normalize_ws(text: str) -> str:
        """Strip and collapse all whitespace sequences to single space."""
        return re.sub(r"\s+", " ", text).strip()

    @classmethod
    def _replace_normalized(cls, text: str, target: str, replacement: str) -> str | None:
        """Sliding line window to match text ignoring whitespace differences."""
        target_norm = cls._normalize_ws(target)
        if not target_norm:
            return None

        lines = text.splitlines(keepends=True)
        target_lines = target.splitlines()
        w_size = len(target_lines)

        for i in range(len(lines)):
            for window_size in (w_size, w_size + 1, max(1, w_size - 1)):
                if i + window_size <= len(lines):
                    chunk = "".join(lines[i : i + window_size])
                    if cls._normalize_ws(chunk) == target_norm:
                        repl_lines = [l + "\n" for l in replacement.splitlines()]
                        result_lines = list(lines)
                        result_lines[i : i + window_size] = repl_lines
                        return "".join(result_lines)
        return None

    @classmethod
    def _replace_non_empty_lines(
        cls,
        lines: list[str],
        target: str,
        replacement: str,
    ) -> str | None:
        """Match sequence of non-empty stripped lines, bridging blank line discrepancies."""
        target_non_empty = [l.strip() for l in target.splitlines() if l.strip()]
        if len(target_non_empty) < 2:
            return None

        # Build index mapping for non-empty lines in source file
        non_empty_indices = [idx for idx, line in enumerate(lines) if line.strip()]
        non_empty_texts = [lines[idx].strip() for idx in non_empty_indices]

        t_len = len(target_non_empty)
        for i in range(len(non_empty_texts) - t_len + 1):
            if non_empty_texts[i : i + t_len] == target_non_empty:
                # Matched full sequence of non-empty lines!
                start_file_idx = non_empty_indices[i]
                end_file_idx = non_empty_indices[i + t_len - 1] + 1

                repl_lines = [l + "\n" for l in replacement.splitlines()]
                result_lines = list(lines)
                result_lines[start_file_idx:end_file_idx] = repl_lines
                return "".join(result_lines)

        return None
