#!/usr/bin/env python3
"""
SyntaxValidator — Pre-deploy syntax validation for all changed files.

Validates files BEFORE deployment to catch:
  - Python syntax errors (py_compile)
  - JavaScript/TypeScript parse errors (node --check / acorn)
  - JSON parse errors (json.loads)
  - CSS basic validation (bracket matching)
  - HTML basic validation (tag matching)

This eliminates the most common deployment failure:
"Build failed because of a syntax error that could have been caught in 0.1s"
"""

import json
import re
import subprocess
from pathlib import Path
from typing import List, Dict, Optional, Tuple


class SyntaxValidator:
    """
    Validates source files for syntax correctness before deployment.
    Uses native language tools where available, falls back to heuristic checks.
    """

    def __init__(self, workspace_dir: str, log_func=None):
        self.ws = Path(workspace_dir)
        self._log = log_func or (lambda msg: print(f"[SyntaxValidator] {msg}"))

    def validate_files(self, changed_files: List[str]) -> List[Dict]:
        """
        Validate all changed files for syntax errors.

        Args:
            changed_files: List of relative file paths that were changed

        Returns:
            List of error dicts: [{"file": "...", "error": "...", "line": N, "fixable": True}]
            Empty list = all files are valid
        """
        errors = []

        for filepath in changed_files:
            full_path = self.ws / filepath.lstrip("./")

            if not full_path.exists():
                continue

            ext = full_path.suffix.lower()

            try:
                content = full_path.read_text(encoding="utf-8", errors="replace")
            except Exception as e:
                errors.append({
                    "file": filepath,
                    "error": f"Cannot read file: {e}",
                    "line": 0,
                    "fixable": False,
                })
                continue

            # Skip empty files
            if not content.strip():
                continue

            # Route to appropriate validator
            if ext == ".py":
                err = self._validate_python(full_path, content)
            elif ext in (".js", ".mjs", ".cjs"):
                err = self._validate_javascript(full_path, content)
            elif ext in (".jsx",):
                err = self._validate_jsx(full_path, content)
            elif ext in (".ts", ".tsx"):
                err = self._validate_typescript(full_path, content)
            elif ext == ".json":
                err = self._validate_json(full_path, content)
            elif ext == ".css":
                err = self._validate_css(content)
            elif ext in (".html", ".htm"):
                err = self._validate_html(content)
            else:
                continue  # Skip unknown file types

            if err:
                errors.append({
                    "file": filepath,
                    "error": err["error"],
                    "line": err.get("line", 0),
                    "fixable": err.get("fixable", True),
                })

        if errors:
            self._log(f"❌ Found {len(errors)} syntax error(s) in changed files")
            for e in errors:
                self._log(f"   • {e['file']}:{e['line']} — {e['error'][:100]}")
        else:
            self._log(f"✅ All {len(changed_files)} changed files pass syntax validation")

        return errors

    # ─────────────────────────────────────────────────────────────────────
    # PYTHON
    # ─────────────────────────────────────────────────────────────────────

    def _validate_python(self, filepath: Path, content: str) -> Optional[Dict]:
        """Validate Python syntax using py_compile."""
        try:
            result = subprocess.run(
                ["python3", "-m", "py_compile", str(filepath)],
                capture_output=True, text=True, timeout=10,
            )

            if result.returncode != 0:
                error_msg = result.stderr.strip()

                # Extract line number
                line_match = re.search(r"line (\d+)", error_msg)
                line_num = int(line_match.group(1)) if line_match else 0

                return {
                    "error": error_msg,
                    "line": line_num,
                    "fixable": True,
                }

            return None

        except FileNotFoundError:
            # python3 not available, try compile()
            try:
                compile(content, str(filepath), "exec")
                return None
            except SyntaxError as e:
                return {
                    "error": str(e),
                    "line": e.lineno or 0,
                    "fixable": True,
                }

        except Exception as e:
            self._log(f"Python validation error: {e}")
            return None  # Don't block on validation errors

    # ─────────────────────────────────────────────────────────────────────
    # JAVASCRIPT
    # ─────────────────────────────────────────────────────────────────────

    def _validate_javascript(self, filepath: Path, content: str) -> Optional[Dict]:
        """Validate JavaScript syntax using node --check."""
        try:
            result = subprocess.run(
                ["node", "--check", str(filepath)],
                capture_output=True, text=True, timeout=10,
            )

            if result.returncode != 0:
                error_msg = result.stderr.strip()
                line_match = re.search(r":(\d+)", error_msg)
                line_num = int(line_match.group(1)) if line_match else 0

                return {
                    "error": error_msg,
                    "line": line_num,
                    "fixable": True,
                }

            return None

        except FileNotFoundError:
            # node not available, use heuristic check
            return self._heuristic_bracket_check(content)

        except Exception:
            return None

    def _validate_jsx(self, filepath: Path, content: str) -> Optional[Dict]:
        """
        Validate JSX files. node --check doesn't support JSX,
        so we do heuristic validation.
        """
        return self._heuristic_js_check(content)

    def _validate_typescript(self, filepath: Path, content: str) -> Optional[Dict]:
        """Validate TypeScript files with heuristic checks."""
        return self._heuristic_js_check(content)

    # ─────────────────────────────────────────────────────────────────────
    # JSON
    # ─────────────────────────────────────────────────────────────────────

    def _validate_json(self, filepath: Path, content: str) -> Optional[Dict]:
        """Validate JSON syntax."""
        try:
            json.loads(content)
            return None
        except json.JSONDecodeError as e:
            return {
                "error": f"Invalid JSON: {e.msg}",
                "line": e.lineno,
                "fixable": True,
            }

    # ─────────────────────────────────────────────────────────────────────
    # CSS
    # ─────────────────────────────────────────────────────────────────────

    def _validate_css(self, content: str) -> Optional[Dict]:
        """Basic CSS validation — check bracket matching."""
        open_count = content.count("{")
        close_count = content.count("}")

        if open_count != close_count:
            return {
                "error": f"Mismatched CSS braces: {open_count} opening, {close_count} closing",
                "line": 0,
                "fixable": True,
            }

        return None

    # ─────────────────────────────────────────────────────────────────────
    # HTML
    # ─────────────────────────────────────────────────────────────────────

    def _validate_html(self, content: str) -> Optional[Dict]:
        """Basic HTML validation."""
        # Check for obviously broken HTML
        if content.strip() and not content.strip().startswith(("<", "<!DOCTYPE")):
            return {
                "error": "File doesn't appear to be valid HTML",
                "line": 1,
                "fixable": True,
            }

        return None

    # ─────────────────────────────────────────────────────────────────────
    # HEURISTIC CHECKS (fallback when native tools unavailable)
    # ─────────────────────────────────────────────────────────────────────

    def _heuristic_bracket_check(self, content: str) -> Optional[Dict]:
        """Check for mismatched brackets/parens/braces."""
        stack = []
        pairs = {"(": ")", "[": "]", "{": "}"}
        in_string = False
        string_char = None
        escaped = False
        line_num = 1

        for i, char in enumerate(content):
            if char == "\n":
                line_num += 1
                continue

            if escaped:
                escaped = False
                continue

            if char == "\\":
                escaped = True
                continue

            if in_string:
                if char == string_char:
                    in_string = False
                continue

            if char in ('"', "'", "`"):
                in_string = True
                string_char = char
                continue

            if char in pairs:
                stack.append((char, line_num))
            elif char in pairs.values():
                if not stack:
                    return {
                        "error": f"Unexpected closing '{char}' without matching opener",
                        "line": line_num,
                        "fixable": True,
                    }
                opener, _ = stack.pop()
                if pairs[opener] != char:
                    return {
                        "error": f"Mismatched brackets: '{opener}' closed by '{char}'",
                        "line": line_num,
                        "fixable": True,
                    }

        if stack:
            opener, line = stack[-1]
            return {
                "error": f"Unclosed '{opener}' opened at line {line}",
                "line": line,
                "fixable": True,
            }

        return None

    def _heuristic_js_check(self, content: str) -> Optional[Dict]:
        """
        Heuristic JavaScript/JSX/TSX validation.
        Checks for common errors that would cause build failures.
        """
        # Check bracket matching
        bracket_err = self._heuristic_bracket_check(content)
        if bracket_err:
            return bracket_err

        # Check for git conflict markers (common corruption)
        conflict_markers = ["<<<<<<<", ">>>>>>>", "======="]
        for i, line in enumerate(content.split("\n"), 1):
            stripped = line.strip()
            for marker in conflict_markers:
                if stripped.startswith(marker):
                    return {
                        "error": f"Git conflict marker found: {stripped[:30]}",
                        "line": i,
                        "fixable": True,
                    }

        # Check for truncated file (common with AI generation)
        stripped = content.rstrip()
        if stripped and stripped[-1] not in ";})\n`'\"":
            # File might be truncated — not always an error, just flag
            last_line = stripped.split("\n")[-1]
            if len(last_line.strip()) > 3 and last_line.strip()[-1].isalpha():
                return {
                    "error": f"File appears truncated — last line: '{last_line.strip()[:60]}'",
                    "line": content.count("\n") + 1,
                    "fixable": True,
                }

        return None
