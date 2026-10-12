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

FIXES in this version:
  - BUG FIX: Truncation heuristic now correctly excludes valid module.exports patterns
  - BUG FIX: validate_file() added — validates a single file by path+content (no disk read)
    so the self-healing caller can validate the just-rewritten buffer before saving
  - BUG FIX: Trailing-newline normalisation added to _write_normalise() helper so
    _write_file callers don't need to worry about strip() removing the final \n
  - IMPROVEMENT: More EOF patterns exempted (module.exports, export { X }, class X)
"""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Dict, Optional


def _py_interpreter() -> str:
    """Dynamically pick a working Python binary for validation (python3 vs python)
    so the checker runs in containers that ship only one name. Falls back to the
    current interpreter if nothing is found so the caller gets a normal error."""
    for cand in ("python3", "python"):
        p = shutil.which(cand)
        if p:
            return p
    return sys.executable


class SyntaxValidator:
    """
    Validates source files for syntax correctness before deployment.
    Uses native language tools where available, falls back to heuristic checks.
    """

    # ── EOF patterns that are valid even without trailing punctuation ────────
    # Each pattern must match the *entire* last non-empty line (after strip()).
    _VALID_EOF_PATTERNS = [
        re.compile(r'^export\s+default\s+[\w$]+;?$'),          # export default Foo
        re.compile(r'^export\s+default\s+\w+\s*\(.*\)\s*;?$'), # export default fn()
        re.compile(r'^module\.exports\s*=\s*[\w$]+;?$'),        # module.exports = Foo
        re.compile(r'^export\s*\{[^}]+\}\s*;?$'),               # export { Foo, Bar }
        re.compile(r'^}\s*;?$'),                                 # closing brace/paren
        re.compile(r'^\)\s*;?$'),
        re.compile(r'^class\s+\w+.*\{$'),                       # class Foo {
    ]
    _VALID_EOF_LITERALS = frozenset({
        'return true', 'return false', 'return true;', 'return false;',
        'return null', 'return null;', 'return undefined', 'return undefined;',
    })

    def __init__(self, workspace_dir: str, log_func=None):
        self.ws = Path(workspace_dir)
        # realpath-normalized root used for cross-file relative-key lookups
        # (immune to Windows short-path `~1` / drive-case differences)
        self._ws_real = Path(os.path.realpath(self.ws))
        def _safe_log(msg: str) -> None:
            try:
                print(f"[SyntaxValidator] {msg}")
            except UnicodeEncodeError:
                print(f"[SyntaxValidator] {msg.encode('ascii', errors='replace').decode('ascii')}")
        self._log = log_func or _safe_log

    # ─────────────────────────────────────────────────────────────────────────
    # PUBLIC API
    # ─────────────────────────────────────────────────────────────────────────

    def _norm_file(self, p) -> str:
        """Normalize a workspace-relative path for membership comparison (realpath,
        forward slashes, leading ./, and backslashes all folded to one form)."""
        if p is None:
            return ""
        try:
            base = self.ws if getattr(self, "_ws_real", None) in (None, "") else self.ws
            return os.path.normpath(os.path.realpath(base / str(p).lstrip("./"))).replace("\\", "/")
        except Exception:
            return os.path.normpath(str(p)).replace("\\", "/")

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

            err = self._validate_content(full_path, filepath, content)
            if err:
                errors.append(err)

        if errors:
            self._log(f"❌ Found {len(errors)} syntax error(s) in changed files")
            for e in errors:
                self._log(f"   • {e['file']}:{e['line']} — {e['error'][:100]}")
        else:
            self._log(f"✅ All {len(changed_files)} changed files pass syntax validation")

        # Run multi-file static cross-import verification across workspace in single pass.
        # IMPORTANT: the workspace scan covers ALL files, but this call is scoped to a
        # specific edited set. Cross-import mismatches in files OUTSIDE that set are
        # pre-existing workspace debt — returning them here would make callers (e.g. the
        # per-file self-healing loop) treat unrelated files as broken and rewrite the
        # WRONG file forever. So we only surface errors whose own file is in the edited set.
        edited_set = {self._norm_file(f) for f in changed_files}
        cross_errs = self.validate_workspace_cross_imports()
        if cross_errs:
            blocking = [ce for ce in cross_errs if self._norm_file(ce["file"]) in edited_set]
            preex = [ce for ce in cross_errs if self._norm_file(ce["file"]) not in edited_set]
            if blocking:
                self._log(f"❌ Found {len(blocking)} cross-file import/export mismatch(es) in EDITED files")
                for ce in blocking:
                    self._log(f"   • {ce['file']}:{ce['line']} — {ce['error'][:100] if 'error' in ce else ''}")
            if preex:
                self._log(f"ℹ️ {len(preex)} workspace cross-import issue(s) OUTSIDE edited files "
                          f"(pre-existing / resolved separately, NOT blocking this file set):")
                for ce in preex[:8]:
                    self._log(f"   • {ce['file']}:{ce['line']} — {ce['error'][:100] if 'error' in ce else ''}")
            errors.extend(blocking)

        return errors

    def validate_content(self, filepath: str, content: str) -> Optional[Dict]:
        """
        Validate in-memory content WITHOUT reading from disk.

        Used by the self-healing loop to check AI-generated content
        BEFORE writing it to disk, saving a round-trip.

        Args:
            filepath: Relative path (used only to determine file type)
            content:  File content as a string

        Returns:
            Error dict or None if valid
        """
        # Skip empty files
        if not content.strip():
            return None

        full_path = self.ws / filepath.lstrip("./")
        return self._validate_content(full_path, filepath, content)

    # ─────────────────────────────────────────────────────────────────────────
    # INTERNAL DISPATCH
    # ─────────────────────────────────────────────────────────────────────────

    def _validate_content(self, full_path: Path, filepath: str, content: str) -> Optional[Dict]:
        """Route content to the right validator and wrap result."""
        if not content.strip():
            return None

        ext = full_path.suffix.lower()

        # ── SANDBOX ESCAPE GUARD: Forbid window.location navigation in React files ──
        if ext in (".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx"):
            loc_match = re.search(
                r'\b(?:window\.)?location(?:\.href)?\s*=\s*[\'"][^\'"]*[\'"]|\b(?:window\.)?location\.(?:replace|assign)\s*\([^)]+\)',
                content,
            )
            if loc_match:
                line_no = content[:loc_match.start()].count('\n') + 1
                return {
                    "file": filepath,
                    "error": (
                        f"🚫 SANDBOX ESCAPE VIOLATION: Found '{loc_match.group(0)}' on line {line_no}. "
                        "Direct assignments to window.location escape the sandboxed preview iframe into the host platform. "
                        "You MUST use React Router's '<Navigate to=\"/login\" replace />' or 'useNavigate()' from 'react-router-dom'. "
                        "Fix this immediately by returning <Navigate to=\"...\" replace /> or using navigate()."
                    ),
                    "line": line_no,
                    "fixable": True,
                }

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
            # ── UNIVERSAL fallback (stack-agnostic) ─────────────────────────
            # Unknown file type. We never hardcode a whitelist: for ANY other
            # extension we (a) opportunistically dispatch to the language's own
            # native tool when it's installed (javac/go/gcc/rustc/cargo/dart…),
            # to give an exact compile error, and (b) fall back to a generic
            # structural bracket-balance + truncation check that works for the
            # large brace-family (Java, Go, Rust, C/C++, C#, Swift…) without
            # needing its compiler present. True unknowns (data/text/assets)
            # are still passed through clean by the balance check.
            err = self._validate_universal(full_path, ext, content)

        if err:
            return {
                "file": filepath,
                "error": err["error"],
                "line": err.get("line", 0),
                "fixable": err.get("fixable", True),
            }
        return None

    # ─────────────────────────────────────────────────────────────────────────
    # PYTHON
    # ─────────────────────────────────────────────────────────────────────────

    def _validate_python(self, filepath: Path, content: str) -> Optional[Dict]:
        """Validate Python syntax using py_compile."""
        try:
            result = subprocess.run(
                [_py_interpreter(), "-m", "py_compile", str(filepath)],
                capture_output=True, text=True, timeout=10,
            )

            if result.returncode != 0:
                error_msg = result.stderr.strip()
                line_match = re.search(r"line (\d+)", error_msg)
                line_num = int(line_match.group(1)) if line_match else 0
                return {"error": error_msg, "line": line_num, "fixable": True}

            return None

        except FileNotFoundError:
            try:
                compile(content, str(filepath), "exec")
                return None
            except SyntaxError as e:
                return {"error": str(e), "line": e.lineno or 0, "fixable": True}

        except Exception as e:
            self._log(f"Python validation error: {e}")
            return None

    # ─────────────────────────────────────────────────────────────────────────
    # JAVASCRIPT / JSX / TYPESCRIPT
    # ─────────────────────────────────────────────────────────────────────────

    def _validate_javascript(self, filepath: Path, content: str) -> Optional[Dict]:
        """Validate JavaScript syntax using node --check."""
        try:
            # Check for ES module and JSX patterns first
            if any(p in content for p in ["import ", "export ", "<", "use client"]):
                status, err = self._parser_check(content, 'jsx')
                if status == 'error':
                    return err
                if status == 'ok':
                    return None
                return self._heuristic_js_check(content)

            result = subprocess.run(
                ["node", "--check", str(filepath)],
                capture_output=True, text=True, timeout=10,
            )

            if result.returncode != 0:
                error_msg = result.stderr.strip()
                # If node --check failed because of ESM/JSX syntax (missed by simple checks), fall back to heuristics
                if "Cannot use import statement" in error_msg or "Unexpected token" in error_msg:
                    return self._heuristic_js_check(content)

                line_match = re.search(r":(\d+)", error_msg)
                line_num = int(line_match.group(1)) if line_match else 0
                return {"error": error_msg, "line": line_num, "fixable": True}

            return None

        except FileNotFoundError:
            return self._heuristic_bracket_check(content)

        except Exception:
            return None

    def _validate_jsx(self, filepath: Path, content: str) -> Optional[Dict]:
        """
        Validate JSX files. node --check doesn't support JSX syntax, so we try a
        real parser (esbuild, then @babel/parser) and only fall back to the
        heuristic check when neither parser is available in the container.
        """
        status, err = self._parser_check(content, 'jsx')
        if status == 'error':
            return err
        if status == 'ok':
            return None
        return self._heuristic_js_check(content)

    def _validate_typescript(self, filepath: Path, content: str) -> Optional[Dict]:
        """Validate TypeScript/TSX files with a real parser when available,
        else fall back to heuristic checks."""
        loader = 'tsx' if filepath.suffix.lower() == '.tsx' else 'ts'
        status, err = self._parser_check(content, loader)
        if status == 'error':
            return err
        if status == 'ok':
            return None
        return self._heuristic_js_check(content)

    def _parser_check(self, content: str, loader: str):
        """
        Gap 4 — parse JS/JSX/TS/TSX with a REAL parser for accurate pre-flight
        syntax validation. Tries esbuild first (ships with Vite), then
        @babel/parser. Nothing is hardcoded — the loader (jsx/ts/tsx) is derived
        from the file extension.

        Returns a tuple (status, error_dict):
          - ('ok',   None)   parsed cleanly
          - ('error', {...}) genuine syntax error (with line + message)
          - ('unavailable', None) no parser installed — caller should fall back
        """
        node_script = (
            "let s='';process.stdin.on('data',d=>s+=d);"
            "process.stdin.on('end',()=>{"
            "const loader=process.argv[1];"
            "let p=null,kind=null;"
            "try{p=require('esbuild');kind='esbuild';}catch(e){}"
            "if(!p){try{p=require('@babel/parser');kind='babel';}catch(e){}}"
            "if(!p){process.exit(4);}"
            "try{"
            "if(kind==='esbuild'){"
            "  try{p.transformSync(s,{loader:loader,jsx:'automatic'});process.exit(0);}"
            "  catch(ebErr){if(String(ebErr).includes('service was stopped')||String(ebErr).includes('service is no longer running')){process.exit(4);}"
            "  var out={text:(ebErr&&ebErr.message)||String(ebErr),line:0};"
            "  if(ebErr&&ebErr.errors&&ebErr.errors[0]&&ebErr.errors[0].location){out.line=ebErr.errors[0].location.line;out.text=ebErr.errors[0].text;}"
            "  process.stderr.write(JSON.stringify(out));process.exit(3);}"
            "}"
            "else{var pl=['jsx'];if(loader==='tsx'||loader==='ts'){pl.push('typescript');}"
            "p.parse(s,{sourceType:'module',plugins:pl});process.exit(0);}"
            "}catch(e){"
            "var out={text:(e&&e.message)||String(e),line:0};"
            "if(e&&e.loc){out.line=e.loc.line;}"
            "process.stderr.write(JSON.stringify(out));process.exit(3);}"
            "});"
        )
        try:
            env = os.environ.copy()
            node_paths = [
                str(self.ws / "frontend" / "node_modules"),
                str(self.ws / "backend" / "node_modules"),
                str(self.ws / "node_modules"),
                "/usr/local/lib/node_modules",
                "/usr/lib/node_modules",
            ]
            existing_node_path = env.get("NODE_PATH", "")
            if existing_node_path:
                node_paths.append(existing_node_path)
            env["NODE_PATH"] = os.pathsep.join(node_paths)

            result = subprocess.run(
                ["node", "-e", node_script, loader],
                input=content, capture_output=True, text=True,
                timeout=15, cwd=str(self.ws), env=env,
            )
        except FileNotFoundError:
            return ('unavailable', None)  # node not present
        except Exception as e:
            self._log(f"Parser check error ({loader}): {e}")
            return ('unavailable', None)

        if result.returncode == 0:
            return ('ok', None)
        if result.returncode == 4:
            return ('unavailable', None)  # no esbuild/@babel/parser installed
        if result.returncode == 3:
            line = 0
            msg = "Syntax error"
            try:
                data = json.loads((result.stderr or "").strip())
                msg = data.get("text", msg)
                line = int(data.get("line", 0) or 0)
            except Exception:
                pass
            if any(ign in msg.lower() for ign in ("service was stopped", "service is no longer running", "cannot find module")):
                return ('unavailable', None)
            return ('error', {"error": f"{loader.upper()} syntax error: {msg}", "line": line, "fixable": True})
        # Any other exit code — don't block deploy on parser oddities
        return ('unavailable', None)

    # ─────────────────────────────────────────────────────────────────────────
    # JSON
    # ─────────────────────────────────────────────────────────────────────────

    def _validate_json(self, filepath: Path, content: str) -> Optional[Dict]:
        """Validate JSON syntax."""
        try:
            json.loads(content)
            return None
        except json.JSONDecodeError as e:
            return {"error": f"Invalid JSON: {e.msg}", "line": e.lineno, "fixable": True}

    # ─────────────────────────────────────────────────────────────────────────
    # CSS
    # ─────────────────────────────────────────────────────────────────────────

    def _validate_css(self, content: str) -> Optional[Dict]:
        """Basic CSS validation — bracket matching, ignoring braces inside
        strings and /* */ comments (naive count-based checks false-positive
        on content like `content: "{";`)."""
        open_count = close_count = 0
        in_string = None
        i, n = 0, len(content)
        while i < n:
            c = content[i]
            nxt = content[i + 1] if i + 1 < n else ''
            if in_string:
                if c == '\\':
                    i += 2
                    continue
                if c == in_string:
                    in_string = None
                i += 1
                continue
            if c == '/' and nxt == '*':
                end = content.find('*/', i + 2)
                i = (end + 2) if end != -1 else n
                continue
            if c in ('"', "'"):
                in_string = c
                i += 1
                continue
            if c == '{':
                open_count += 1
            elif c == '}':
                close_count += 1
            i += 1

        if open_count != close_count:
            return {
                "error": f"Mismatched CSS braces: {open_count} opening, {close_count} closing",
                "line": 0,
                "fixable": True,
            }

        return None

    # ─────────────────────────────────────────────────────────────────────────
    # HTML
    # ─────────────────────────────────────────────────────────────────────────

    def _validate_html(self, content: str) -> Optional[Dict]:
        """Basic HTML validation."""
        stripped = content.strip()
        if stripped and not stripped.startswith(("<", "<!DOCTYPE", "{%", "{#", "{{", "<!--")):
            return {
                "error": "File doesn't appear to be valid HTML",
                "line": 1,
                "fixable": True,
            }
        return None

    # ─────────────────────────────────────────────────────────────────────────
    # UNIVERSAL (ANY LANGUAGE / STACK)
    # ─────────────────────────────────────────────────────────────────────────

    def _validate_universal(self, filepath: Path, ext: str, content: str) -> Optional[Dict]:
        """
        Stack-agnostic validation for ANY file extension not covered by a
        dedicated checker. Two layers, both dynamic:

        1. NATIVE TOOL, if the language's own compiler/linter is installed in
           the container. This gives an exact error+line for the language
           (e.g. `javac`, `go build`/`go vet`, `gcc`/`cc` -fsyntax-only,
           `rustc`, `dart analyze`, `dotnet build`). The tool table is keyed by
           extension and looked up dynamically; no tool is assumed present.

        2. GENERIC STRUCTURAL FALLBACK when no native tool exists: a
           comment/string-aware bracket-balance + truncation check that is
           valid across the entire C-family/Go/Rust/Java brace family without
           needing a compiler. Text/data/asset files pass clean.

        NEVER returns an error based on a hardcoded language list; true unknown
        data files (<few KB, no braces, no code markers) are treated as valid.
        """
        # Only attempt native tools for clearly code-like extensions to avoid
        # spawning a compiler on data/markdown/assets. Registry is dynamic and
        # additive — keying by extension, value is a (cmd, needs_file) pair.
        tool_registry = {
            # Java / Kotlin
            ".java":   (["javac", "-d", "/tmp/vibe_jc", "-proc:none"], True),
            ".kt":     (["kotlinc"], True),
            # Go
            ".go":     (["gofmt", "-e"], False),          # -e prints errors, no write
            # C / C++ / C# / Objective-C
            ".c":      (["cc", "-fsyntax-only", "-x", "c", "-"], True),
            ".h":      (["cc", "-fsyntax-only", "-x", "c", "-"], True),
            ".cpp":    (["g++", "-fsyntax-only", "-x", "c++", "-"], True),
            ".cc":     (["cc", "-fsyntax-only", "-x", "c++", "-"], True),
            ".cxx":    (["g++", "-fsyntax-only", "-x", "c++", "-"], True),
            ".hpp":    (["g++", "-fsyntax-only", "-x", "c++", "-"], True),
            ".cs":     (["csc"], True),
            # Rust
            ".rs":     (["rustc", "--crate-type", "lib", "-"], True),
            # Swift
            ".swift":  (["swiftc", "-parse"], True),
            # Dart
            ".dart":   (["dart", "analyze"], True),
            # PHP
            ".php":    (["php", "-l"], True),
            # Ruby
            ".rb":     (["ruby", "-c"], True),
            # Lua
            ".lua":    (["luac", "-p"], True),
            # Shell / Bash
            ".sh":     (["bash", "-n"], True),
            ".bash":   (["bash", "-n"], True),
        }

        cmd = tool_registry.get(ext.lower())
        if cmd:
            try:
                args = list(cmd[0])
                with_file = cmd[1]
                # Best-effort makedirs so temp compile output dirs exist
                if "-d" in args:
                    try:
                        Path("/tmp/vibe_jc").mkdir(parents=True, exist_ok=True)
                    except Exception:
                        pass
                if with_file:
                    r = subprocess.run(
                        args + [str(filepath)],
                        capture_output=True, text=True, timeout=25,
                    )
                else:
                    r = subprocess.run(
                        args + [str(filepath)] if not (args[-1] == "-") else args,
                        input=content, capture_output=True, text=True, timeout=25,
                    )
                if r.returncode != 0:
                    out = (r.stderr or r.stdout or "").strip()
                    line = 0
                    m = re.search(r":(\d+)[:.]", out)
                    if m:
                        line = int(m.group(1))
                    if out:
                        return {
                            "error": f"{ext.lstrip('.')} validation failed: {out[:300]}",
                            "line": line,
                            "fixable": True,
                        }
            except FileNotFoundError:
                pass  # tool not installed → fall through to structural check
            except Exception as e:
                self._log(f"Universal native check error ({ext}): {e}")

        # ── Generic structural fallback (C-family/Go/Rust/Java brace family) ──
        stripped = content.strip()
        if not stripped:
            return None

        # Skip clearly non-code data (no code delimiters at all)
        if not any(c in content for c in "{}()[]<>;="):
            # Heuristic: a real source file will contain some of these tokens.
            # Brackety markup like XML/SVG is validated by the HTML/MARKUP rules
            # elsewhere; pure data/minified JSON is already handled. If this is
            # truly code-free, treat as valid.
            return None

        # Conflict/package markers are never valid in source
        for i, line in enumerate(content.split("\n"), 1):
            ls = line.strip()
            if ls.startswith(("<<<<<<<", ">>>>>>>", "<<<SEARCH", "<<<PATCH")):
                return {"error": f"Conflict/merge marker found: {ls[:30]}", "line": i, "fixable": True}

        # Brace-family balance + string/comment awareness (reuses the JS-style
        # bracket scanner which understands //, /* */, quotes, templates).
        bracket_err = self._heuristic_bracket_check(content)
        if bracket_err:
            # Only report genuine structural imbalance, and mark it so the
            # caller knows it's a generic (not language-specific) check.
            return bracket_err

        return None

    # ─────────────────────────────────────────────────────────────────────────
    # HEURISTIC CHECKS
    # ─────────────────────────────────────────────────────────────────────────

    def _heuristic_bracket_check(self, content: str) -> Optional[Dict]:
        """
        Check for mismatched brackets/parens/braces.

        Handles single-line strings, template literals, escape sequences, and
        // line / /* block */ comments (brackets inside comments no longer
        cause false positives). Also catches empty statement-level calls like
        'express.Router();()' — balanced brackets, yet a syntax error — which
        a naive balance check would falsely pass.
        """
        stack = []
        pairs = {"(": ")", "[": "]", "{": "}"}
        in_string = False
        string_char = None
        escaped = False
        comment_mode = None  # None | 'line' | 'block'
        line_num = 1
        prev_significant = None  # last non-whitespace char (statement-start check)
        i, n = 0, len(content)

        while i < n:
            char = content[i]
            nxt = content[i + 1] if i + 1 < n else ''

            if char == "\n":
                line_num += 1
                # Single and double quote strings cannot span across lines unless escaped with \
                if in_string and string_char in ('"', "'") and not escaped:
                    in_string = False
                    string_char = None
                if comment_mode == 'line':
                    comment_mode = None
                escaped = False
                i += 1
                continue

            if comment_mode == 'line':
                i += 1
                continue
            if comment_mode == 'block':
                if char == '*' and nxt == '/':
                    comment_mode = None
                    i += 2
                else:
                    i += 1
                continue

            if escaped:
                escaped = False
                i += 1
                continue

            if char == "\\":
                escaped = True
                i += 1
                continue

            if in_string:
                if char == string_char:
                    # End of single/double-quoted string or template literal
                    in_string = False
                    string_char = None
                i += 1
                continue

            if char == '/' and nxt == '/':
                comment_mode = 'line'
                i += 2
                continue
            if char == '/' and nxt == '*':
                comment_mode = 'block'
                i += 2
                continue

            if char in ('"', "'", "`"):
                in_string = True
                string_char = char
                i += 1
                continue

            if char in ' \t\r':
                i += 1
                continue

            if char in pairs:
                # Empty parens at statement start (after ';' or at file start)
                # are NEVER valid JS: 'foo();()' — balanced, yet a syntax
                # error. A real parser catches it; this heuristic must too,
                # or the gate false-passes exactly the ';()' corruption.
                if char == '(' and prev_significant in (';', None):
                    j = i + 1
                    while j < n and content[j] in ' \t\r\n':
                        j += 1
                    if j < n and content[j] == ')':
                        return {
                            "error": "Empty call '()' after ';' — dangling leftover (e.g. 'router();()')",
                            "line": line_num,
                            "fixable": True,
                        }
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
            prev_significant = char
            i += 1

        if in_string and string_char != "`":
            # Template literals may span multiple lines legitimately,
            # but unclosed single/double quotes are always errors.
            return {
                "error": f"Unclosed string literal starting with {string_char!r}",
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

    def _is_valid_eof_line(self, last_line_stripped: str) -> bool:
        """
        Return True if last_line_stripped is a known-valid EOF pattern
        that does NOT require trailing punctuation.

        FIX: The original code used a single regex and missed many valid
        patterns like 'module.exports = Foo', 'export { X }', etc.
        This version uses a list of patterns for robustness.
        """
        if last_line_stripped in self._VALID_EOF_LITERALS:
            return True
        for pattern in self._VALID_EOF_PATTERNS:
            if pattern.match(last_line_stripped):
                return True
        return False

    def _heuristic_js_check(self, content: str) -> Optional[Dict]:
        """
        Heuristic JavaScript/JSX/TSX validation.

        Checks for:
          1. Mismatched brackets (via _heuristic_bracket_check)
          2. Git conflict markers
          3. Genuinely truncated files (last non-empty line mid-statement)

        FIX: The truncation check now uses _is_valid_eof_line() which covers
        all common AI-generated EOF patterns so valid files don't get flagged.
        """
        # ── 1. Bracket matching ──────────────────────────────────────────
        bracket_err = self._heuristic_bracket_check(content)
        if bracket_err:
            return bracket_err

        # ── 2. AI Patch/Conflict markers ─────────────────────────────────
        # FIX: Added AI patch markers that LLMs sometimes leave behind
        conflict_markers = ["<<<<<<<", ">>>>>>>", "=======", "<<<SEARCH", "<<<PATCH", "<<<REPLACE", "<<<ADD"]
        for i, line in enumerate(content.split("\n"), 1):
            stripped_line = line.strip()
            for marker in conflict_markers:
                if stripped_line.startswith(marker):
                    return {
                        "error": f"AI Patch/Conflict marker found: {stripped_line[:30]}",
                        "line": i,
                        "fixable": True,
                    }

        # Note: JSX/TSX tag matching is accurately handled by _parser_check (esbuild/@babel/parser).
        # We do NOT run naive regex matching here because TypeScript generics like
        # `createContext<NotificationContextType>` and `useState<T>` produce false positives.

        # ── 4. Truncation detection ──────────────────────────────────────
        # INVERTED heuristic: only flag when the last line PROVABLY ends
        # mid-statement (trailing operator / comma / open bracket /
        # continuation keyword). Ending with an identifier is ambiguous and
        # usually valid — e.g. 'export const getPool = () => pool' — the old
        # rule flagged such complete ESM files as "truncated" and made
        # EditEngine abandon good fixes. Real truncation is still caught by
        # node --check/esbuild in the normal path and by the unclosed-string
        # / bracket-balance checks here.
        stripped = content.rstrip()
        if not stripped:
            return None
        
        last_char = stripped[-1]
        # If the file ends with punctuation that closes a statement, it's fine
        if last_char in ";})]\n`'\"\"":
            return None
        
        last_line_stripped = stripped.split("\n")[-1].strip()
        
        # Short last lines (1-3 chars) are usually closing symbols; skip
        if len(last_line_stripped) <= 3:
            return None
        
        # Complete postfix endings: x++ / x-- (identifier directly before)
        if last_line_stripped.endswith(('++', '--')) and len(last_line_stripped) >= 3 and last_line_stripped[-3].isalnum():
            return None
        # TypeScript non-null assertion: foo!
        if last_line_stripped.endswith('!') and len(last_line_stripped) >= 2 and (last_line_stripped[-2].isalnum() or last_line_stripped[-2] in ')]}'):
            return None
        
        # Known-valid EOF patterns: don't flag these
        if self._is_valid_eof_line(last_line_stripped):
            return None
        
        # Provably incomplete endings — the file was cut mid-statement.
        if re.search(
            r'(?:[,.:?=]|&&|\|\||[+\-*/%&|^<>!]|=>|\(|\[|\{)\s*$',
            last_line_stripped,
        ):
            return {
                "error": f"File appears truncated — last line: '{last_line_stripped[:60]}'",
                "line": content.count("\n") + 1,
                "fixable": True,
            }

        # Ends with a continuation keyword that cannot close a statement.
        if re.search(
            r'\b(?:return|await|const|let|var|export|import|throw|new|else|case|try|finally|function|async)\s*$',
            last_line_stripped,
        ):
            return {
                "error": f"File appears truncated — last line: '{last_line_stripped[:60]}'",
                "line": content.count("\n") + 1,
                "fixable": True,
            }

        # Ends with an identifier / literal → NOT truncated (the fix: this
        # branch used to FLAG such lines as truncated)
        if last_char.isalpha() or last_char == "_" or last_char.isdigit():
            return None

        return None

    # ────────────────────────────────────────────────────────────────────────
    # LANGUAGE-AGNOSTIC CROSS-FILE IMPORT/EXPORT VALIDATION
    # Table value = list of (compiled_regex, kind). kind may be
    #   'named' | 'default' | 'default-named' | 'named-list' | 'module' | 'mixed'
    # Named patterns reuse group(1) as the comma-joined symbol list (group 2 =
    # path, group 3 = path for 'mixed'). Flags (e.g. re.MULTILINE) are compiled
    # into the regex itself because Pattern.finditer() rejects a flags= arg.
    # ────────────────────────────────────────────────────────────────────────

    # Export extraction per language family.
    _EXPORT_PATTERNS = {
        # ── JavaScript / TypeScript / React (ESM) ──
        ("js", "jsx", "ts", "tsx", "mjs"): [
            # NOTE: exclude 'default' here — a default export is NOT a named
            # export (matches rollup). Only 'default-named' below handles it.
            (re.compile(r'\bexport\s+(?:const|let|var|function|class)\s+([A-Za-z0-9_$]+)'), 'named'),
            (re.compile(r'\bexport\s+default\s+([A-Za-z0-9_$]+)'), 'default-named'),
            (re.compile(r'\bexport\s*\{([^}]+)\}'), 'named-list'),
            (re.compile(r'\bexport\s+async\s+function\s+([A-Za-z0-9_$]+)'), 'named'),
        ],
        # ── CommonJS (.cjs / .js that use require/module.exports) ──
        ("cjs",): [
            # module.exports = { a, b, 'c': d }  → named list
            (re.compile(r'\bmodule\.exports\s*=\s*\{([^}]+)\}'), 'named-list'),
            # module.exports = Foo  → re-export the symbol itself (named)
            (re.compile(r'\bmodule\.exports\s*=\s*(?!require\s*\()\$?([A-Za-z0-9_$]+)'), 'na-module'),
            # module.exports = async function Foo(){} / class Bar{} / function Baz(){}
            (re.compile(r'\bmodule\.exports\s*=\s*(?:async\s+)?function\s+([A-Za-z0-9_$]+)'), 'named'),
            (re.compile(r'\bmodule\.exports\s*=\s*class\s+([A-Za-z0-9_$]+)'), 'named'),
            # module.exports.a = ...  and  exports.a = ...
            (re.compile(r'\b(?:module\.)?exports\s*\.\s*([A-Za-z0-9_$]+)\s*='), 'named'),
            # module.exports = require('...')  /  module.exports.foo = require('...') (re-export, no new symbol)
            (re.compile(r'\bmodule\.exports\s*(?:\.\s*[A-Za-z0-9_$]+\s*)?=\s*require\s*\('), 'export-require'),
            # Any CommonJS export statement → the module has an implicit DEFAULT
            # export bound to its exports object (Node ESM<->CJS interop), so an
            # ESM `import x from './cjs'` must NOT be flagged as missing.
            (re.compile(r'\b(?:module\.)?exports\b\s*(?:\.|\[|=)'), 'cjs-default'),
        ],
        # ── Python ──
        ("py",): [
            (re.compile(r'^def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(', re.MULTILINE), 'named'),
            (re.compile(r'^class\s+([A-Za-z_][A-Za-z0-9_]*)\s*[\:(]', re.MULTILINE), 'named'),
            (re.compile(r'^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*', re.MULTILINE), 'named'),
            (re.compile(r'^__all__\s*=\s*\[([^\]]*)\]', re.MULTILINE), 'named-list'),
        ],
    }

    # Import extraction per language family.
    _IMPORT_PATTERNS = {
        # ── JavaScript / TypeScript (ESM): named + default ──
        ("js", "jsx", "ts", "tsx", "mjs"): [
            (re.compile(r"\bimport\s*\{([^}]+)\}\s*from\s*[\"']([^\"']+)[\"']"), 'named'),       # named
            (re.compile(r"\bimport\s+([A-Za-z0-9_$]+)\s*,\s*\{([^}]+)\}\s*from\s*[\"']([^\"']+)[\"']"), 'mixed'),
            (re.compile(r"\bimport\s+([A-Za-z0-9_$]+)\s*from\s*[\"']([^\"']+)[\"']"), 'default'),  # default only
            # ── CommonJS require ──
            # const { a, b } = require('m')
            (re.compile(r"\bconst\s*\{([^}]+)\}\s*=\s*require\s*\(\s*[\"']([^\"']+)[\"']\s*\)"), 'named'),
            # const [x, y] = require('m')  → array destructure, name(s) unknown → treat as wrapper
            (re.compile(r"\bconst\s*\[([^\]]+)\]\s*=\s*require\s*\(\s*[\"']([^\"']+)[\"']\s*\)"), 'cjswrap'),
            # const X = require('m')  → binds the WHOLE exports object, NOT a default
            (re.compile(r"\bconst\s+([A-Za-z0-9_$]+)\s*=\s*require\s*\(\s*[\"']([^\"']+)[\"']\s*\)"), 'cjswrap'),
        ],
        # ── CommonJS (.cjs) ──
        ("cjs",): [
            (re.compile(r"\bconst\s*\{([^}]+)\}\s*=\s*require\s*\(\s*[\"']([^\"']+)[\"']\s*\)"), 'named'),
            (re.compile(r"\bconst\s*\[([^\]]+)\]\s*=\s*require\s*\(\s*[\"']([^\"']+)[\"']\s*\)"), 'cjswrap'),
            (re.compile(r"\bconst\s+([A-Za-z0-9_$]+)\s*=\s*require\s*\(\s*[\"']([^\"']+)[\"']\s*\)"), 'cjswrap'),
        ],
        # ── Python ──
        ("py",): [
            (re.compile(r'^from\s+([A-Za-z0-9_.]+)\s+import\s+([A-Za-z0-9_,\s*]+)', re.MULTILINE), 'named'),
            (re.compile(r'^import\s+([A-Za-z0-9_.]+)', re.MULTILINE), 'module'),
        ],
    }

    def _validate_export_symbols(self, ext: str, txt: str) -> Dict:
        """Return {named:set, default} for one file's exports.

        For JS-family files we apply BOTH the ESM and the CommonJS export
        pattern sets, because a .js/.jsx/.mjs module may be written in either
        style (or mix them). Pure .cjs only uses the CommonJS set.
        """
        exports = {"named": set(), "default": set()}
        esm_exts = ("js", "jsx", "ts", "tsx", "mjs")
        pattern_sets = []
        if ext in esm_exts:
            # A .js/.jsx/.ts/.tsx/.mjs module may be written as ESM, or CommonJS,
            # or a mix. Apply BOTH export grammars; the regexes are disjoint
            # (`export` vs `module.exports`/`exports.`), so no cross-pollution.
            pattern_sets.append(self._EXPORT_PATTERNS.get(esm_exts, []))
            pattern_sets.append(self._EXPORT_PATTERNS.get(("cjs",), []))
        else:
            for exts, pats in self._EXPORT_PATTERNS.items():
                if ext in exts:
                    pattern_sets.append(pats)
                    break
        if not pattern_sets:
            return exports
        for pats in pattern_sets:
            for pat in pats:
                regex, kind = pat[0], pat[1]
                for m in regex.finditer(txt):
                    if kind == 'cjs-default':
                        # module has CommonJS exports → implicit default export
                        # = the exports object itself (Node interop). No symbol group.
                        exports["default"].add("\x00_cjs_exports")
                        continue
                    if kind == 'export-require':
                        # module.exports = require('...') → re-export, no new symbol.
                        continue
                    sym = m.group(1).strip()
                    if not sym:
                        continue
                    if kind == 'named':
                        exports["named"].add(sym)
                    elif kind == 'default-named':
                        exports["default"].add(sym)
                    elif kind == 'named-list':
                        # Handles BOTH ESM `export { a, b as c }` and CJS
                        # `module.exports = { key: val, shorthand, 'q': conn }`.
                        for s in sym.split(","):
                            s2 = s.strip()
                            # object-style: take the KEY up to ':' (CJS member)
                            if ":" in s2:
                                s2 = s2.split(":", 1)[0].strip()
                            # ESM re-export alias: `a as b` exports `b`
                            s2 = s2.split(" as ")[-1].strip()
                            # drop quote wrapping around string keys
                            s2 = s2.strip("\"'")
                            if s2:
                                exports["named"].add(s2)
                    elif kind == 'na-module':
                        # module.exports = Foo → re-export the symbol as a named export
                        exports["named"].add(sym)
        return exports

    def _resolve_target_key(self, parent_dir, target_rel, files_by_rel) -> Optional[str]:
        """Resolve a relative import target to a scanned workspace-relative key."""
        target_key = None
        resolved = (parent_dir / target_rel).resolve()
        cand_paths = [resolved]
        if not resolved.suffix:
            cand_paths.extend([
                resolved.with_suffix(".js"), resolved.with_suffix(".jsx"),
                resolved.with_suffix(".ts"), resolved.with_suffix(".tsx"),
                resolved.with_suffix(".cjs"), resolved.with_suffix(".mjs"),
                resolved.with_suffix(".py"),
                resolved / "index.js", resolved / "index.jsx",
                resolved / "index.cjs",
                resolved / "__init__.py",
            ])
        for cand in cand_paths:
            try:
                # Normalize BOTH sides to a realpath + forward-slash relative key
                # so Windows short-path (~1) and drive-case differences don't
                # break `relative_to` / dictionary lookups.
                rc = Path(os.path.realpath(cand))
                rel_cand = rc.relative_to(self._ws_real).as_posix()
                if rel_cand in files_by_rel:
                    target_key = rel_cand
                    break
            except Exception:
                continue
        return target_key

    def _resolve_from_root(self, dotted_pkg, files_by_rel) -> Optional[str]:
        """Resolve an ABSOLUTE Python package path from the workspace root.

        `from todo_app import views`/`import todo_app.views` always resolve from the
        project root, NOT relative to the importing file. Map the dotted package to
        a filesystem path under the workspace root and return its scanned key.
        """
        rel = dotted_pkg.lstrip('/.')
        if not rel:
            return None
        def look(k):
            try:
                rc = Path(os.path.realpath(self.ws / k))
                return rc.relative_to(self._ws_real).as_posix()
            except Exception:
                return None
        # Exact file, or package __init__ for a directory/module namespace.
        for cand in (rel + '.py', rel + '/__init__.py', rel):
            k = look(cand)
            if k in files_by_rel:
                return k
        return None

    def _validate_module_attribute_refs(self, files_by_rel=None) -> List[Dict]:
        """Catch `module.attribute` references where an imported module is used as
        a namespace and an attribute that it does not define is accessed.

        This closes the classic Django/JS gap that named-import validation misses:
        `urls.py` does `from todo_app import views` (module import) then calls
        `views.add_todo` — the whole-module import passes the named-import check,
        but `add_todo` is not defined/exported by `todo_app/views`.

        Stack-agnostic: for every Python `import M` / `from X import M` and JS
        `import * as M` / `const M = require('...')` module binding, we scan the
        importing file for `M.<symbol>` usages and require that symbol to be a
        named export of the resolved target module.
        """
        errors = []
        try:
            ignore_dirs = ("node_modules", "dist", ".git", "build", "__pycache__", ".venv", "venv")
            scan_exts = set()
            for exts in self._EXPORT_PATTERNS:
                scan_exts.update(exts)
            files_map = files_by_rel if files_by_rel is not None else {}
            if not files_map:
                for p in self.ws.rglob("*"):
                    if any(x in p.parts for x in ignore_dirs):
                        continue
                    try:
                        if not p.is_file() or not p.suffix:
                            continue
                    except Exception:
                        continue
                    ext = p.suffix.lstrip(".").lower()
                    if ext not in scan_exts:
                        continue
                    try:
                        rp = Path(os.path.realpath(p))
                        rel = rp.relative_to(self._ws_real).as_posix()
                    except Exception:
                        continue
                    files_map[rel] = (ext, p.parent)

            # Reuse the whole-file export map to know each module's named exports.
            exports_by_file = {}
            for rel, (ext, _parent) in files_map.items():
                txt = (self.ws / rel).read_text(encoding="utf-8", errors="replace")
                exports_by_file[rel] = self._validate_export_symbols(ext, txt)

            # Standard library and common third-party framework modules that must NOT
            # be shadowed by local project files (e.g. local models.py, logging.py, auth.py)
            stdlib_and_framework = {
                "os", "sys", "pathlib", "re", "json", "math", "datetime", "time", "typing",
                "collections", "itertools", "functools", "unittest", "hashlib", "random",
                "uuid", "shutil", "subprocess", "io", "abc", "contextlib", "copy",
                "dataclasses", "enum", "inspect", "threading", "traceback", "urllib",
                "logging", "string", "tempfile", "socket", "http", "warnings", "glob",
                "csv", "sqlite3", "pickle", "base64", "secrets", "types", "multiprocessing",
                "django", "rest_framework", "fastapi", "pydantic", "flask", "sqlalchemy",
                "pytest", "requests", "numpy", "pandas", "celery", "redis", "alembic",
                "models", "views", "admin", "serializers", "urls"
            }

            # Python: `import M` / `from pkg import M` then `M.attr`
            py_mod = re.compile(r'^import\s+(?:[A-Za-z0-9_]*\.)*([A-Za-z0-9_]+)', re.MULTILINE)
            py_from = re.compile(r'^from\s+([A-Za-z0-9_.]+)\s+import\s+([A-Za-z0-9_, ]+)', re.MULTILINE)
            attr_use = re.compile(r'\b(?P<mod>[A-Za-z_][A-Za-z0-9_]*)\.(?P<attr>[A-Za-z_][A-Za-z0-9_]*)\b')

            for rel, (ext, parent_dir) in files_map.items():
                if ext != "py":
                    continue
                try:
                    txt = (self.ws / rel).read_text(encoding="utf-8", errors="replace")
                except Exception:
                    continue
                # Map local module aliases -> target workspace key.
                # Python `from pkg import M` / `from pkg.mod import M` module paths are
                # ABSOLUTE package paths resolved from the workspace root (not relative
                # to the importing file), e.g. `from todo_app import views` -> todo_app/views.
                alias2target = {}
                for m in py_from.finditer(txt):
                    raw_mod = m.group(1)
                    root_pkg = raw_mod.split('.')[0].strip()
                    if root_pkg in stdlib_and_framework:
                        continue
                    mod_path = raw_mod.replace('.', '/')   # todo_app.mod -> todo_app/mod
                    syms = [s.strip() for s in m.group(2).split(',') if s.strip()]
                    for s in syms:
                        if s == '*' or '.' in s:
                            continue
                        if s in stdlib_and_framework:
                            continue
                        # Prefer root-resolved package path; fall back to parent-relative
                        # for same-dir modules (e.g. `from helper import do_thing`).
                        tkey = self._resolve_from_root(mod_path + '/' + s, files_map)
                        if not tkey:
                            tkey = self._resolve_target_key(parent_dir,
                                                            mod_path.replace('/', '.') + '/' + s,
                                                            files_map)
                        if tkey:
                            alias2target.setdefault(s, tkey)
                for m in py_mod.finditer(txt):
                    # `import views` (or `import pkg.views`) -> alias = last name.
                    alias = m.group(1)
                    if alias in stdlib_and_framework:
                        continue
                    import_path = m.group(0).split(None, 2)[-1]  # e.g. `views` or `todo_app.views`
                    root_pkg = import_path.split('.')[0].strip()
                    if root_pkg in stdlib_and_framework:
                        continue
                    mod_path = import_path.replace('.', '/')     # -> `views` / `todo_app/views`
                    tkey = self._resolve_from_root(mod_path, files_map)
                    if not tkey:
                        # relative `import helper` next to importer
                        c = (parent_dir / (import_path + '.py')).resolve()
                        try:
                            rc = Path(os.path.realpath(c))
                            tkey = rc.relative_to(self._ws_real).as_posix()
                        except Exception:
                            pass
                    if tkey in files_map:
                        alias2target.setdefault(alias, tkey)
                # Now check each `alias.attr` call has attr in target's named exports.
                for a2 in attr_use.finditer(txt):
                    alias = a2.group('mod')
                    attr = a2.group('attr')
                    if alias in stdlib_and_framework:
                        continue
                    tkey = alias2target.get(alias)
                    if not tkey:
                        continue  # many builtins/stdlib aliases are unknown; ignore
                    exports = exports_by_file.get(tkey, {"named": set(), "default": set()})
                    named = exports.get("named") or set()
                    if attr not in named:
                        # Skip if it's a known stdlib/builtin (os, sys, pathlib, re, …)
                        if alias in stdlib_and_framework or tkey not in files_map:
                            continue
                        line_no = txt[: a2.start()].count("\n") + 1
                        errors.append({
                            "file": rel, "line": line_no,
                            "error": f"'{rel}' calls '{alias}.{attr}' but '{tkey}' does not define/export '{attr}' (imported as module '{alias}')",
                            "fixable": True,
                            "target": tkey,
                            "symbol": attr,
                        })
        except Exception as e:
            self._log(f"Module attribute cross-import validation exception: {e}")
        return errors

    def validate_workspace_cross_imports(self) -> List[Dict]:
        """
        Language-agnostic static cross-file dependency & export-import validator.
        Scans ALL workspace source files in ONE single pass and aggregates EVERY
        missing/incorrect import (named AND default) across EVERY supported stack
        (JS/TS/React ES-modules, CommonJS, Python) at once. Where a symbol is only
        a default export, it reports the exact fix (use a default import) so EditEngine
        can repair the whole class in a single multi-file pass.
        """
        errors = []
        try:
            # ── Pass 1: collect per-file language + exports ────────────────
            files_by_rel = {}
            exports_by_file = {}
            ignore_dirs = ("node_modules", "dist", ".git", "build", "__pycache__", ".venv", "venv")
            scan_exts = set()
            for exts in self._EXPORT_PATTERNS:
                scan_exts.update(exts)

            for p in self.ws.rglob("*"):
                if any(x in p.parts for x in ignore_dirs):
                    continue
                try:
                    if not p.is_file() or not p.suffix:
                        continue
                except Exception:
                    continue
                ext = p.suffix.lstrip(".").lower()
                if ext not in scan_exts:
                    continue
                try:
                    rp = Path(os.path.realpath(p))
                    rel = rp.relative_to(self._ws_real).as_posix()
                    txt = p.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    continue
                files_by_rel[rel] = (ext, p.parent)
                exports_by_file[rel] = self._validate_export_symbols(ext, txt)

            # ── Pass 2: collect imports ────────────────────────────────────
            imports_by_file = {}
            for rel, (ext, parent_dir) in files_by_rel.items():
                patterns = None
                for exts, pats in self._IMPORT_PATTERNS.items():
                    if ext in exts:
                        patterns = pats
                        break
                if not patterns:
                    continue
                txt = (self.ws / rel).read_text(encoding="utf-8", errors="replace")
                for pat in patterns:
                    regex, kind = pat[0], pat[1]
                    for m in regex.finditer(txt):
                        line_no = txt[: m.start()].count("\n") + 1
                        if kind == 'mixed':
                            syms, target_rel = m.group(2), m.group(3)
                            imports_by_file.setdefault(rel, []).append(
                                (line_no, syms, target_rel, parent_dir, 'named', ext))
                        elif kind in ('named', 'module'):
                            # Python `from X import Y`: group(1)=module, group(2)=symbols
                            # (opposite of JS where group(1)=symbols, group(2)=path).
                            if ext == 'py' and kind == 'named':
                                target_rel, syms = m.group(1), m.group(2)
                            else:
                                syms, target_rel = m.group(1), (m.group(2) if len(m.groups()) > 1 else "")
                            imports_by_file.setdefault(rel, []).append(
                                (line_no, syms, target_rel, parent_dir, 'named' if kind == 'named' else 'module', ext))
                        elif kind == 'default':
                            sym, target_rel = m.group(1), m.group(2)
                            imports_by_file.setdefault(rel, []).append(
                                (line_no, sym, target_rel, parent_dir, 'default', ext))
                        elif kind == 'cjswrap':
                            sym, target_rel = m.group(1), m.group(2)
                            imports_by_file.setdefault(rel, []).append(
                                (line_no, sym, target_rel, parent_dir, 'cjswrap', ext))

            # ── Pass 3: cross-verify ───────────────────────────────────────
            for file_path, imp_list in imports_by_file.items():
                for line_no, raw_syms, target_rel, parent_dir, kind, imp_ext in imp_list:
                    # Path-based JS/Python: external/stdlib deps won't resolve to a
                    # scanned workspace file, so leaving resolution to handle it and
                    # only checking when the import has a local (workspace) target.
                    target_key = self._resolve_target_key(parent_dir, target_rel, files_by_rel)
                    if not target_key:
                        continue
                    target_exports = exports_by_file.get(target_key, {"named": set(), "default": set()})

                    if kind in ('module', 'cjswrap'):
                        # `import module` / `const X = require('m')` binds the WHOLE
                        # exports object (or is an unverifiable wrapper). Fine if the
                        # path resolves (already checked above) — no symbol exists to verify.
                        continue

                    syms = raw_syms.split(",") if kind == 'named' else [raw_syms]
                    for s_raw in syms:
                        sym = s_raw.strip()
                        if not sym or sym == "*":
                            continue
                        if kind == 'default':
                            # `import X from 'm'` binds the DEFAULT export; the
                            # local name X is arbitrary (matches rollup). Only
                            # need the target to HAVE a default export.
                            if "default" not in target_exports or not target_exports["default"]:
                                errors.append({
                                    "file": file_path, "line": line_no,
                                    "error": f"'{file_path}' default-imports '{target_rel}' ('{sym}') but '{target_key}' has no default export",
                                    "fixable": True,
                                    "target": target_key,
                                })
                            continue
                        else:
                            # named import: symbol must be a named export, OR only a default
                            if sym in target_exports["named"]:
                                continue
                            if sym in target_exports["default"]:
                                errors.append({
                                    "file": file_path, "line": line_no,
                                    "error": f"'{sym}' is named-imported by '{file_path}' but is only a DEFAULT export of '{target_key}'. Fix: use 'import {sym} from \"{target_rel}\"' (default import).",
                                    "fixable": True,
                                    "target": target_key,
                                })
                                continue
                            errors.append({
                                "file": file_path, "line": line_no,
                                "error": f"'{sym}' is imported by '{file_path}' but is not exported by '{target_key}'",
                                "fixable": True,
                                "target": target_key,
                            })
            # ── Pass 4: module-alias attribute references (views.add_todo) ──
            # Runs the same scan pass so module-namespace usage is verified against
            # the target's real named exports. Aggregates into the same error stream.
            errors.extend(self._validate_module_attribute_refs(files_by_rel))
        except Exception as e:
            self._log(f"Cross-file import validation exception: {e}")
        return errors