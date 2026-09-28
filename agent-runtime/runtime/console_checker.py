"""ConsoleChecker — Captures browser console errors using Playwright.

After the build succeeds and preview is live, this module:
1. Launches a headless Chromium browser
2. Visits the app at http://localhost:80
3. Captures all console errors (TypeError, ReferenceError, etc.)
4. Returns structured error list for AI auto-fix

Architecture: This is the safety net that catches runtime errors
the build step can't detect (mismatched props, undefined variables, etc.)
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ConsoleError:
    """A single browser console error."""
    type: str          # "error", "warning", "TypeError", etc.
    message: str       # Full error message
    url: str = ""      # Source URL (file where error occurred)
    line: int = 0      # Line number
    column: int = 0    # Column number
    stack: str = ""    # Stack trace if available

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "message": self.message,
            "url": self.url,
            "line": self.line,
            "column": self.column,
            "stack": self.stack,
        }

    def __str__(self) -> str:
        loc = f" at {self.url}:{self.line}:{self.column}" if self.url else ""
        return f"[{self.type}] {self.message}{loc}"


@dataclass
class ConsoleCheckResult:
    """Result from a console error check."""
    success: bool
    errors: list[ConsoleError] = field(default_factory=list)
    warnings: list[ConsoleError] = field(default_factory=list)
    error_count: int = 0
    warning_count: int = 0
    check_duration_ms: int = 0

    @property
    def has_errors(self) -> bool:
        return self.error_count > 0

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "errors": [e.to_dict() for e in self.errors],
            "warnings": [e.to_dict() for e in self.warnings],
            "check_duration_ms": self.check_duration_ms,
        }

    def to_fix_prompt(self, workspace_path: str | None = None) -> str:
        """Format errors into a targeted, actionable prompt for AI auto-fix with exact file locations."""
        if not self.has_errors:
            return ""

        # Filter out network 502/504/404/favicon errors and React boundary noise
        valid_errors = []
        for e in self.errors:
            full_text = f"{e.message} {e.url}".lower()
            if any(net_term in full_text for net_term in ("502", "504", "favicon", "the above error occurred in", "connection_refused", "connection refused", "net::err_")):
                continue
            valid_errors.append(e)


        if not valid_errors:
            return ""

        # Deduplicate errors by core message
        unique_errors = []
        seen_msgs = set()
        for e in valid_errors:
            norm = re.sub(r'http://[^\s]+', '', e.message).strip()
            if norm not in seen_msgs:
                seen_msgs.add(norm)
                # Parse file path from message text if not already set
                # e.g. "Dashboard.jsx:87 Uncaught ReferenceError..." -> url=Dashboard.jsx, line=87
                if (not e.url or e.line <= 0) and e.message:
                    fp_match = re.search(r'((?:src/)?[\w/]+\.(?:jsx?|tsx?)):(\d+)', e.message)
                    if fp_match:
                        e.url = fp_match.group(1)
                        e.line = int(fp_match.group(2))
                unique_errors.append(e)

        lines = [
            "## Browser Runtime Console Errors Detected",
            "",
            "The build compiled successfully, but runtime exceptions occurred in the browser when rendering components or handling state.",
            "Fix these specific runtime errors immediately using targeted edits.",
            "",
            "### Targeted Errors & Exact File Locations:",
            "",
        ]

        ws_root = Path(workspace_path) if workspace_path else Path("/workspace")
        src_root = ws_root / "src" if (ws_root / "src").exists() else ws_root

        # Cache all source file contents once (avoids re-reading for each error)
        _file_cache: dict[str, tuple[list[str], str]] = {}  # rel_path -> (lines, text)
        if src_root.exists():
            for src_file in list(src_root.glob("**/*.jsx")) + list(src_root.glob("**/*.js")) + list(src_root.glob("**/*.tsx")):
                try:
                    text = src_file.read_text(encoding="utf-8", errors="replace")
                    rel = str(src_file.relative_to(ws_root)).replace("\\", "/")
                    _file_cache[rel] = (text.splitlines(), text)
                except Exception:
                    pass

        for i, err in enumerate(unique_errors, 1):
            lines.append(f"#### Issue {i}: `{err.message}`")
            if err.url:
                # Filter out node_modules paths — these are third-party internals.
                # The real fix is always in the user's src/ files, not in packages.
                if "node_modules" in err.url or "template_workspace" in err.url:
                    lines.append(
                        f"**Error Origin**: The error traces to a third-party library (`{err.url}`). "
                        "**DO NOT read or edit node_modules files.** "
                        "Search your OWN source files (`src/`) for the component that calls the failing function, "
                        "then fix the CALLER (add null guards, fix prop types, or add missing keys)."
                    )
                else:
                    loc_str = f"(Line {err.line})" if err.line > 0 else ""
                    lines.append(f"**Error Location**: `{err.url}` {loc_str}")

            # Extract property from "Cannot read properties of null (reading 'X')" or undefined
            prop_match = re.search(r"reading ['\"]([^'\"]+)['\"]", err.message)
            if not prop_match:
                prop_match = re.search(r"Cannot read property ['\"]([^'\"]+)['\"]", err.message)

            prop_name = prop_match.group(1) if prop_match else None
            candidates = []
            sibling_warnings = []
            if prop_name and src_root.exists():
                # Scan cached files for occurrences of .prop_name, grouped by file
                try:
                    for rel_path, (file_lines, text) in _file_cache.items():
                        file_matches = []
                        parent_chains = set()

                        for line_idx, line in enumerate(file_lines, start=1):
                            if f".{prop_name}" in line or f"['{prop_name}']" in line or f'["{prop_name}"]' in line:
                                file_matches.append((line_idx, line.strip()))
                                # Extract parent object chain (e.g. conversation.response or item.details)
                                matches = re.finditer(rf"([\w]+(?:(?:\.|\?\.)[\w]+)*)(?:\.|\?\.)" + re.escape(prop_name), line)
                                for m in matches:
                                    raw_parent = m.group(1).replace("?.", ".")
                                    if raw_parent and raw_parent not in ("this", "window", "document", "Math", "JSON", "console", "Object"):
                                        parent_chains.add(raw_parent)

                        if file_matches:
                            candidates.append((rel_path, file_matches))

                            # Scan for all sibling property accesses on the same parent chains
                            for parent in parent_chains:
                                parts = [re.escape(p) for p in parent.split(".")]
                                parent_regex = r"(?:\.|\?\.)".join(parts) + r"(?:\.|\?\.)([\w]+)"
                                sib_matches = []
                                for line_idx, line in enumerate(file_lines, start=1):
                                    for sm in re.finditer(parent_regex, line):
                                        sib_prop = sm.group(1)
                                        sib_matches.append((line_idx, line.strip(), sib_prop))
                                if len(sib_matches) > 1:
                                    sibling_warnings.append((rel_path, parent, sib_matches))
                except Exception:
                    pass

            if candidates:
                lines.append(f"**ALL Workspace Files accessing property `.{prop_name}`:**")
                for c_path, file_matches in candidates[:10]:
                    lines.append(f"- **`{c_path}`**:")
                    for c_line, c_content in file_matches[:5]:
                        lines.append(f"    Line {c_line}: `{c_content[:90]}`")

                if sibling_warnings:
                    lines.append("")
                    lines.append("⚠️ **CRITICAL: PARENT OBJECT SIBLING PROPERTY CASCADE DETECTED**:")
                    lines.append("The parent object is undefined at runtime! You MUST add optional chaining `?.` or safe defaults to ALL sibling property accesses on this object in the SAME file, otherwise each line will crash sequentially:")
                    for s_path, s_parent, s_matches in sibling_warnings[:5]:
                        lines.append(f"- **`{s_path}`** (Parent `{s_parent}` accesses):")
                        for s_line, s_content, s_prop in s_matches[:8]:
                            lines.append(f"    Line {s_line} (`.{s_prop}`): `{s_content[:90]}`")

                lines.append("")
                safe_guard_example = f"?.{prop_name}" if prop_name else "?.prop"
                lines.append(f"**Recommended Fix**: You MUST add null guards (e.g. `{safe_guard_example}` or `(data?.{prop_name or 'prop'} || [])`) to ALL listed files and sibling lines above at once, and ensure component props provide safe defaults like `const Component = ({{ entity = {{}}, entities = [] }}) => ...`!")

            # Handle ReferenceError: 'X is not defined'
            elif "is not defined" in err.message:
                func_match = re.search(r"([\w]+)\s+is not defined", err.message)
                func_name = func_match.group(1) if func_match else None
                if func_name and src_root.exists():
                    func_candidates = []
                    # Search cached files for where this function is defined/exported
                    for rel_path, (file_lines, text) in _file_cache.items():
                        for line_idx, line in enumerate(file_lines, start=1):
                            # Look for actual export/definition of this function
                            is_export = bool(re.search(rf"\bexport\s+(?:const|function|class|default\s+function|let|var)\s+{func_name}\b|\bexport\s*\{{[^}}]*\b{func_name}\b", line))
                            is_def = bool(re.search(rf"\b(?:function|const|let|var|class)\s+{func_name}\b\s*(?:=|\()", line))
                            if is_export:
                                func_candidates.append((rel_path, line_idx, line.strip(), "export"))
                            elif is_def and not line.strip().startswith("import"):
                                func_candidates.append((rel_path, line_idx, line.strip(), "definition"))

                    if func_candidates:
                        lines.append(f"**Function `{func_name}` is defined here but not imported correctly:**")
                        for f_path, f_line, f_content, f_type in func_candidates[:3]:
                            lines.append(f"- File: `{f_path}` (Line {f_line}) [{f_type}] → `{f_content[:90]}`")
                        lines.append(f"**Recommended Fix**: Import `{func_name}` correctly in the file that uses it, or check if the function name is misspelled.")
                    else:
                        # Search cached files for usage locations that lack an import
                        usage_candidates = []
                        for rel_path, (file_lines, text) in _file_cache.items():
                            # Check if func_name is imported anywhere in file (supports single & multi-line imports)
                            has_import = bool(re.search(rf"\bimport\s+[^;]*\b{re.escape(func_name)}\b[^;]*['\"]", text, re.DOTALL))
                            if not has_import:
                                for line_idx, line in enumerate(file_lines, start=1):
                                    # Ignore comments and import lines
                                    stripped = line.strip()
                                    if (
                                        func_name in line
                                        and not stripped.startswith(("//", "/*", "*", "import"))
                                        and "from " not in stripped
                                    ):
                                        usage_candidates.append((rel_path, line_idx, stripped))
                        if usage_candidates:
                            lines.append(f"**`{func_name}` is used here but NOT imported in the file:**")
                            for u_path, u_line, u_content in usage_candidates[:5]:
                                lines.append(f"- File: `{u_path}` (Line {u_line}) → `{u_content[:90]}`")
                            lines.append(f"**Recommended Fix**: Add missing import: `import {{ {func_name} }} from 'lucide-react';` (or appropriate module) to `{usage_candidates[0][0]}`.")


            # Handle TypeError: 'X.method is not a function'
            elif "is not a function" in err.message and "is not defined" not in err.message:
                # Extract object and method: "K.map is not a function" -> object=K, method=map
                method_match = re.search(r"([\w]+)\.([\w]+)\s+is not a function", err.message)
                if not method_match:
                    method_match = re.search(r"([\w]+)\s+is not a function", err.message)

                if method_match:
                    obj_name = method_match.group(1)
                    method_name = method_match.group(2) if method_match.lastindex >= 2 else None

                    # The minified name (K, Q, etc.) doesn't help us find the source
                    # But we know the METHOD name - scan cached files for .method() calls
                    if method_name and src_root.exists():
                        method_candidates = []
                        for rel_path, (file_lines, text) in _file_cache.items():
                            for line_idx, line in enumerate(file_lines, start=1):
                                # Look for .method( calls without null guards
                                if f".{method_name}(" in line:
                                    # Check if it has a null guard
                                    has_guard = any(g in line for g in (
                                        f"?.{method_name}(",
                                        f"|| []).{method_name}(",
                                        f"?? []).{method_name}(",
                                        f"|| []).{method_name}(",
                                    ))
                                    if not has_guard:
                                        method_candidates.append((rel_path, line_idx, line.strip()))

                        if method_candidates:
                            lines.append(f"**Unguarded `.{method_name}()` calls that may crash (minified as `{obj_name}`):**")
                            for m_path, m_line, m_content in method_candidates[:5]:
                                lines.append(f"- File: `{m_path}` (Line {m_line}) → `{m_content[:90]}`")
                            lines.append(f"**Recommended Fix**: Add null guard: `(data || []).{method_name}(...)` or `data?.{method_name}(...) || []`")
                        else:
                            # Fallback: just show the source URL
                            lines.append(f"Source: `{err.url}:{err.line}:{err.column}` (minified `{obj_name}.{method_name}`)")
                    else:
                        lines.append(f"Source: `{err.url}:{err.line}:{err.column}`")

            elif err.url:
                lines.append(f"Source: `{err.url}:{err.line}:{err.column}`")

            lines.append("")

        # ADDITIONAL: Scan for ALL unguarded .map/.filter/.forEach calls
        # This catches errors like Q.map where the exact component is unknown
        if src_root.exists():
            unguarded_calls = []
            try:
                for jsx_file in src_root.glob("**/*.jsx"):
                    text = jsx_file.read_text(encoding="utf-8", errors="replace")
                    rel_path = str(jsx_file.relative_to(ws_root)).replace("\\", "/")
                    for line_idx, line in enumerate(text.splitlines(), start=1):
                        stripped = line.strip()
                        # Check for .map( .filter( .forEach( without null checks
                        for method in (".map(", ".filter(", ".forEach("):
                            if method in stripped:
                                # Check if there's a null guard: ?.map or || []).map or (x || []).map
                                has_guard = any(guard in stripped for guard in (
                                    "?." + method[1:],  # ?.map
                                    "|| []" + method,    # || []).map
                                    "|| []" + method.replace("(", "("),
                                    "?? []" + method,    # ?? []).map
                                    "def " in stripped,   # function definition
                                ))
                                if not has_guard and "import" not in stripped and "export" not in stripped:
                                    unguarded_calls.append((rel_path, line_idx, stripped[:120]))
            except Exception:
                pass

            if unguarded_calls:
                lines.append("### ⚠️ UNGUARDED ARRAY METHOD CALLS (potential runtime crashes):")
                lines.append("")
                lines.append("These `.map()`, `.filter()`, `.forEach()` calls have NO null checks.")
                lines.append("If the data is undefined/null (e.g., before API loads), these will crash.")
                lines.append("")
                for u_path, u_line, u_content in unguarded_calls[:15]:  # Limit to 15
                    lines.append(f"- `{u_path}` (Line {u_line}): `{u_content}`")
                lines.append("")
                lines.append("**Fix ALL of these by adding null guards:**")
                lines.append("- Change `data.map(...)` → `(data || []).map(...)` or `data?.map(...) || []`")
                lines.append("- Change `data.filter(...)` → `(data || []).filter(...)` or `data?.filter(...) || []`")
                lines.append("- Change `data.forEach(...)` → `(data || []).forEach(...)` or `data?.forEach(...)`")
                lines.append("")

        lines.extend([
            "### REQUIRED ACTION WORKFLOW:",
            "1. Fix the specific errors listed above first.",
            "2. THEN fix ALL unguarded array method calls listed in the section above.",
            "3. Use `replace_file_content` to add null guards: `(data || []).map(...)` or `data?.map(...)`.",
            "4. Verify each fix with `check_syntax(path='...')`.",
            "5. After fixing ALL issues, conclude immediately.",
        ])

        return "\n".join(lines)


def _resolve_source_maps(
    errors: list[ConsoleError],
    workspace_path: str | None = None,
) -> list[ConsoleError]:
    """Resolve minified error locations to original source files using Vite source maps.

    Vite builds with `sourcemap: true` produce .map files alongside JS bundles.
    This function reads those maps and resolves minified positions (e.g.,
    'index-MbRIANpi.js:264:204') to original source files (e.g., 'src/App.jsx:338').

    This eliminates the AI's need to guess which file to fix.
    """
    try:
        from runtime.sourcemap_parser import parse_source_map
    except ImportError:
        print("[ConsoleChecker] sourcemap library not installed — skipping source map resolution")
        return errors

    # Find dist/ directory
    ws = Path(workspace_path) if workspace_path else Path("/workspace")
    dist_dir = None
    for name in ("dist", "build", "out"):
        p = ws / name
        if p.exists() and p.is_dir():
            dist_dir = p
            break

    if not dist_dir:
        return errors

    # Build a map: JS filename → source map lookup function
    # Vite produces files like: assets/index-MbRIANpi.js + assets/index-MbRIANpi.js.map
    source_maps: dict[str, Any] = {}
    try:
        for map_file in dist_dir.glob("**/*.map"):
            try:
                map_content = map_file.read_text(encoding="utf-8")
                lookup = parse_source_map(json.loads(map_content))
                if lookup:
                    js_name = map_file.name.removesuffix(".map")
                    source_maps[js_name] = lookup
                    rel_path = str(map_file.relative_to(dist_dir)).replace("\\", "/").removesuffix(".map")
                    source_maps[rel_path] = lookup
                    print(f"[ConsoleChecker] Loaded source map: {map_file.name}")
            except Exception as e:
                print(f"[ConsoleChecker] Failed to parse source map {map_file.name}: {e}")
    except Exception as e:
        print(f"[ConsoleChecker] Error scanning source maps: {e}")

    if not source_maps:
        print("[ConsoleChecker] No source maps found in dist/")
        return errors

    print(f"[ConsoleChecker] Loaded {len(source_maps)} source maps")

    # Resolve each error
    resolved_count = 0
    for err in errors:
        if not err.url or err.line <= 0:
            continue

        # Extract JS filename from URL
        # URLs like: http://localhost:80/assets/index-MbRIANpi.js
        #            http://localhost:5173/src/App.jsx (already source)
        url_path = err.url
        if "/" in url_path:
            url_path = url_path.split("/")[-1]

        # Skip if already a source file (not minified)
        if url_path.endswith(".jsx") or url_path.endswith(".tsx") or url_path.endswith(".ts"):
            continue

        # Try to find source map for this JS file
        source_map = source_maps.get(url_path)
        if not source_map:
            # Try with assets/ prefix
            source_map = source_maps.get(f"assets/{url_path}")
        if not source_map:
            continue

        # Resolve: (line, column) → (source_file, source_line, source_column)
        try:
            # Source map lines are 0-based, errors are 1-based
            result = source_map(err.line - 1, err.column)
            if result:
                old_url = err.url
                old_line = err.line
                # Update error with resolved source info
                err.url = result[0]
                err.line = result[1]  # Already 1-based from parser
                err.column = 0  # Column not needed for file-level resolution
                resolved_count += 1
                print(f"[ConsoleChecker] Resolved: {old_url}:{old_line} → {err.url}:{err.line}")
        except Exception:
            pass  # If resolution fails, keep the original minified location

    if resolved_count > 0:
        print(f"[ConsoleChecker] Resolved {resolved_count}/{len(errors)} errors to source files")

    # Fallback: Parse stack traces for workspace file references
    # If source map resolved to node_modules, look for workspace files in stack
    for err in errors:
        if err.stack and (not err.url or "node_modules" in err.url or "template_workspace" in err.url):
            import re as _re
            # Find first frame pointing to workspace src/ files
            stack_lines = err.stack.split(chr(10))
            for frame in stack_lines:
                # Match: at Component (path/to/file.jsx:87:27)
                m = _re.search(r"at\s+\w+\s*\(([^)]+?(src/[^\s:]+):(\d+):(\d+)\)", frame)
                if not m:
                    # Match: at path/to/file.jsx:87:27
                    m = _re.search(r"at\s+([^\s:]+\.jsx):(\d+):(\d+)", frame)
                if m:
                    file_path = m.group(1) if m.lastindex >= 3 else m.group(1)
                    line_num = int(m.group(2) if m.lastindex >= 3 else m.group(2))
                    # Normalize path
                    if "src/" in file_path:
                        err.url = file_path
                        err.line = line_num
                        print(f"[ConsoleChecker] Stack trace resolved: {err.url}:{err.line}")
                        break

    return errors


def check_console_errors(
    url: str = "http://localhost:80",
    timeout_ms: int = 15000,
    wait_after_load_ms: int = 3000,
    workspace_path: str | None = None,
) -> ConsoleCheckResult:
    """Run Playwright to capture browser console errors.

    Checks both page load AND user interactions (clicking buttons)
    to catch runtime errors that only appear on interaction.

    Args:
        url: The URL to visit
        timeout_ms: Max time to wait for page load
        wait_after_load_ms: Wait time after load to catch async errors

    Returns:
        ConsoleCheckResult with all captured errors
    """
    import time
    start = time.time()

    # Create a Python script that uses Playwright to capture errors
    # IMPORTANT: We interact with the page (click buttons) to trigger runtime errors
    script = f'''
import json
import sys
from playwright.sync_api import sync_playwright

errors = []
warnings = []

def handle_console(msg):
    text = msg.text
    # Ignore network status errors (502, 504, 404) and favicon noise
    if any(n in text.lower() for n in ("502", "504 (gateway timeout)", "failed to load resource", "favicon.ico")):
        return
    entry = {{
        "type": msg.type,
        "message": text,
        "url": msg.location.get("url", "") if msg.location else "",
        "line": msg.location.get("lineNumber", 0) if msg.location else 0,
        "column": msg.location.get("columnNumber", 0) if msg.location else 0,
    }}
    if msg.type in ("error",):
        errors.append(entry)
    elif msg.type in ("warning",):
        warnings.append(entry)

def handle_page_error(err):
    text = str(err)
    if any(n in text.lower() for n in ("502", "failed to load resource", "favicon.ico")):
        return
    errors.append({{
        "type": "page_error",
        "message": text,
        "url": "",
        "line": 0,
        "column": 0,
    }})

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={{"width": 1280, "height": 800}})
    page.on("console", handle_console)
    page.on("pageerror", handle_page_error)
    
    try:
        resp = None
        resp = page.goto("{url}", timeout={timeout_ms})
        if resp and resp.status >= 400:
            errors.append({{
                "type": "http_error",
                "message": "Server returned HTTP " + str(resp.status) + " at {url} (preview unreachable or proxy gateway failure)",
                "url": "{url}",
                "line": 0,
                "column": 0,
            }})
        title = page.title()
        if any(bad in title.lower() for bad in ("502 bad gateway", "504 gateway timeout", "500 internal server error")):
            errors.append({{
                "type": "gateway_error",
                "message": "Page returned gateway error: '" + str(title) + "'",
                "url": "{url}",
                "line": 0,
                "column": 0,
            }})
        page.wait_for_timeout({wait_after_load_ms})
    except Exception as e:
        errors.append({{
            "type": "navigation_error",
            "message": str(e),
            "url": "{url}",
            "line": 0,
            "column": 0,
        }})
    
    # INTERACT with the page to trigger runtime errors
    # Click buttons, navigate between views — this catches errors
    # that only appear on user interaction (onClick handlers, state changes, etc.)
    try:
        buttons = page.query_selector_all("button")
        clicked = 0
        for btn in buttons[:15]:  # Click up to 15 buttons
            try:
                if btn.is_visible() and btn.is_enabled():
                    btn.click()
                    page.wait_for_timeout(800)  # Wait for state changes
                    clicked += 1
            except Exception:
                pass  # Element may have been removed from DOM
        
        # Also try navigating to different views if sidebar exists
        nav_items = page.query_selector_all("nav button, [role='tab'], .nav-tab, a[href]")
        for item in nav_items[:10]:
            try:
                if item.is_visible():
                    item.click()
                    page.wait_for_timeout(800)
            except Exception:
                pass
                
    except Exception:
        pass
    
    browser.close()

result = {{
    "errors": errors,
    "warnings": warnings,
    "error_count": len(errors),
    "warning_count": len(warnings),
}}
print(json.dumps(result))
'''

    try:
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            timeout=30,
        )

        duration_ms = int((time.time() - start) * 1000)

        if result.returncode != 0:
            # Playwright not installed or crashed
            return ConsoleCheckResult(
                success=False,
                error_count=0,
                check_duration_ms=duration_ms,
            )

        # Parse JSON output
        try:
            data = json.loads(result.stdout.strip())
        except json.JSONDecodeError:
            return ConsoleCheckResult(
                success=False,
                error_count=0,
                check_duration_ms=duration_ms,
            )

        errors = []
        for e in data.get("errors", []):
            errors.append(ConsoleError(
                type=e.get("type", "error"),
                message=e.get("message", ""),
                url=e.get("url", ""),
                line=e.get("line", 0),
                column=e.get("column", 0),
                stack=e.get("stack", ""),
            ))

        warnings = []
        for w in data.get("warnings", []):
            warnings.append(ConsoleError(
                type=w.get("type", "warning"),
                message=w.get("message", ""),
                url=w.get("url", ""),
                line=w.get("line", 0),
                column=w.get("column", 0),
            ))

        # Resolve source maps: map minified positions → original source files
        errors = _resolve_source_maps(errors, workspace_path=workspace_path)

        return ConsoleCheckResult(
            success=True,
            errors=errors,
            warnings=warnings,
            error_count=data.get("error_count", 0),
            warning_count=data.get("warning_count", 0),
            check_duration_ms=duration_ms,
        )

    except subprocess.TimeoutExpired:
        return ConsoleCheckResult(
            success=False,
            error_count=0,
            check_duration_ms=int((time.time() - start) * 1000),
        )
    except Exception as exc:
        print(f"[ConsoleChecker] Error: {exc}")
        return ConsoleCheckResult(
            success=False,
            error_count=0,
            check_duration_ms=int((time.time() - start) * 1000),
        )
