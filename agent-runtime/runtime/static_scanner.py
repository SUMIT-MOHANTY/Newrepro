"""Static Pre-Flight Scanner — Inspects all workspace source files in ~50ms.

Finds ALL missing imports (Lucide icons, components), missing files,
mismatched default/named exports, and unguarded array iterations across
every file in /workspace/src at once before or after build.

Enables the AI to fix ALL structural issues in a single pass instead of
looping one error at a time through browser crashes.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Standard HTML / SVG elements that are never imported
STANDARD_JSX_TAGS = {
    "a", "abbr", "address", "area", "article", "aside", "audio", "b", "base",
    "bdi", "bdo", "blockquote", "body", "br", "button", "canvas", "caption",
    "cite", "code", "col", "colgroup", "data", "datalist", "dd", "del", "details",
    "dfn", "dialog", "div", "dl", "dt", "em", "embed", "fieldset", "figcaption",
    "figure", "footer", "form", "h1", "h2", "h3", "h4", "h5", "h6", "head",
    "header", "hgroup", "hr", "html", "i", "iframe", "img", "input", "ins",
    "kbd", "label", "legend", "li", "link", "main", "map", "mark", "menu",
    "meta", "meter", "nav", "noscript", "object", "ol", "optgroup", "option",
    "output", "p", "param", "picture", "pre", "progress", "q", "rp", "rt",
    "ruby", "s", "samp", "script", "search", "section", "select", "small",
    "source", "span", "strong", "style", "sub", "summary", "sup", "table",
    "tbody", "td", "template", "textarea", "tfoot", "th", "thead", "time",
    "title", "tr", "track", "u", "ul", "var", "video", "wbr",
    # SVG tags
    "svg", "path", "circle", "rect", "line", "polyline", "polygon", "text",
    "g", "defs", "clippath", "mask", "pattern", "image", "switch", "foreignobject",
    "lineargradient", "radialgradient", "stop", "animate", "animatetransform",
    "feBlend", "feColorMatrix", "feGaussianBlur", "feMerge", "feMergeNode", "feOffset",
    # React specials
    "fragment", "React.Fragment",
}


@dataclass
class StaticIssue:
    file_path: str
    line_number: int
    issue_type: str  # "missing_import", "missing_file", "mismatched_export", "unguarded_array"
    identifier: str
    snippet: str
    suggested_fix: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_path": self.file_path,
            "line_number": self.line_number,
            "issue_type": self.issue_type,
            "identifier": self.identifier,
            "snippet": self.snippet,
            "suggested_fix": self.suggested_fix,
        }


@dataclass
class StaticScanResult:
    issues: list[StaticIssue] = field(default_factory=list)
    files_scanned: int = 0
    duration_ms: int = 0

    @property
    def has_issues(self) -> bool:
        return len(self.issues) > 0

    @property
    def issue_count(self) -> int:
        return len(self.issues)

    def to_fix_prompt(self) -> str:
        """Format all issues into a single batch fix prompt for AI."""
        if not self.has_issues:
            return ""

        # Group issues by file
        by_file: dict[str, list[StaticIssue]] = {}
        for issue in self.issues:
            by_file.setdefault(issue.file_path, []).append(issue)

        lines = [
            "## ⚡ Static Pre-Flight Scan Issues Detected (Fix in ONE Batch)",
            "",
            f"Static analysis found {len(self.issues)} issue(s) across {len(by_file)} file(s).",
            "Fix ALL of these issues in ONE single `batch_replace_file_content` call (or `replace_file_content` for 1 file):",
            "",
        ]

        for fpath, file_issues in by_file.items():
            lines.append(f"### File: `{fpath}`")
            for issue in file_issues:
                if issue.issue_type == "missing_import":
                    lines.append(f"- Line {issue.line_number}: `<{issue.identifier} />` is used but NOT imported.")
                    lines.append(f"  **Code**: `{issue.snippet}`")
                    lines.append(f"  **Fix**: {issue.suggested_fix}")
                elif issue.issue_type == "missing_file":
                    lines.append(f"- Line {issue.line_number}: Import references missing file `{issue.identifier}`.")
                    lines.append(f"  **Fix**: {issue.suggested_fix}")
                elif issue.issue_type == "mismatched_export":
                    lines.append(f"- Line {issue.line_number}: {issue.snippet}")
                    lines.append(f"  **Fix**: {issue.suggested_fix}")
                elif issue.issue_type == "unguarded_array":
                    lines.append(f"- Line {issue.line_number}: Unguarded array call `{issue.snippet}` may crash if null/undefined.")
                    lines.append(f"  **Fix**: {issue.suggested_fix}")
            lines.append("")

        lines.extend([
            "### REQUIRED ACTION:",
            "1. Use `batch_replace_file_content` to apply all surgical fixes across the affected files in ONE single call (do NOT rewrite full files).",
            "2. If creating a brand new missing file, use `write_file` for that specific new file.",
            "3. Then call `install_and_build` to verify.",
        ])

        return "\n".join(lines)


# Browser / React / Node APIs that must NOT be null-guarded
SAFE_PROPERTY_ACCESSORS = {
    # Event handlers
    'e.target', 'e.currentTarget', 'e.preventDefault', 'e.stopPropagation',
    'e.nativeEvent', 'e.persist', 'event.target', 'event.currentTarget',
    # Console
    'console.log', 'console.error', 'console.warn', 'console.info',
    # Math / JSON
    'Math.floor', 'Math.ceil', 'Math.round', 'Math.min', 'Math.max',
    'Math.random', 'Math.abs', 'Math.sqrt', 'Math.pow',
    'JSON.stringify', 'JSON.parse',
    # Window / Document
    'window.location', 'window.localStorage', 'window.sessionStorage',
    'window.open', 'window.close', 'window.addEventListener',
    'document.getElementById', 'document.querySelector',
    'document.querySelectorAll', 'document.createElement',
    # React
    'React.useState', 'React.useEffect', 'React.useRef', 'React.useContext',
    'React.createElement', 'React.createContext', 'React.memo',
    'useState', 'useEffect', 'useRef', 'useContext', 'useMemo', 'useCallback',
    'createContext', 'createElement', 'memo', 'forwardRef',
    # Process / env
    'process.env', 'import.meta.env',
    # Common safe patterns
    'Object.keys', 'Object.values', 'Object.entries', 'Object.assign',
    'Array.isArray', 'Array.from', 'Array.of',
    'String.prototype', 'Number.prototype',
    'Promise.all', 'Promise.race', 'Promise.resolve', 'Promise.reject',
}

# Deep property chain pattern: obj.prop1.prop2 (2+ levels)
# Excludes: function calls (obj.method()), assignments (obj.x =), imports
DEEP_CHAIN_PATTERN = re.compile(
    r"(?<![\w])"  # Not preceded by word char
    r"([a-zA-Z_][\w]*(?:\.[a-zA-Z_][\w]*){1,})"  # obj.prop1.prop2 (2+ levels)
    r"(?![\s]*[=(])"  # Not followed by = or ( (assignment or function call)
)

# Already guarded patterns
GUARD_PATTERNS = [
    '?.',      # Optional chaining
    '|| []',   # Fallback array
    '?? []',   # Nullish coalescing array
    '|| {}',   # Fallback object
    '?? {}',   # Nullish coalescing object
    '|| ''',  # Fallback string
    '?? ''',  # Nullish coalescing string
    '|| 0',    # Fallback number
    '?? 0',    # Nullish coalescing number
]


class StaticScanner:
    """Fast AST/Regex scanner for React + Vite codebases."""

    def __init__(self, workspace_path: str):
        self.workspace_path = Path(workspace_path).resolve()
        self.src_dir = (self.workspace_path / "src").resolve()
        if not self.src_dir.exists():
            self.src_dir = self.workspace_path

    def scan(self) -> StaticScanResult:
        """Run full static scan across all source files."""
        import time
        start_time = time.time()
        issues: list[StaticIssue] = []

        if not self.src_dir.exists():
            return StaticScanResult(issues=[], files_scanned=0, duration_ms=0)

        # 1. Discover all source files
        source_files = list(self.src_dir.glob("**/*.jsx")) + list(self.src_dir.glob("**/*.tsx")) + list(self.src_dir.glob("**/*.js"))
        source_files = [f for f in source_files if "node_modules" not in str(f) and "dist" not in str(f)]

        # 2. Build export registry: rel_path -> { 'default': bool, 'named': set[str] }
        export_registry: dict[str, dict[str, Any]] = {}
        file_contents: dict[str, str] = {}

        for sf in source_files:
            rel_path = str(sf.relative_to(self.workspace_path)).replace("\\", "/")
            try:
                content = sf.read_text(encoding="utf-8", errors="replace")
                file_contents[rel_path] = content
                export_registry[rel_path] = self._parse_exports(content)
            except Exception:
                pass

        # 3. Scan each file for issues
        for sf in source_files:
            rel_path = str(sf.relative_to(self.workspace_path)).replace("\\", "/")
            content = file_contents.get(rel_path, "")
            if not content:
                continue

            # Check 1: Missing icon/component imports in JSX
            issues.extend(self._check_missing_jsx_imports(rel_path, content, export_registry))

            # Check 2: Missing local imported files and export mismatches
            issues.extend(self._check_import_paths_and_exports(rel_path, content, export_registry))

            # Check 3: Unguarded array iterations
            issues.extend(self._check_unguarded_arrays(rel_path, content))

            # Check 4: Unguarded deep property accesses
            issues.extend(self._check_unguarded_property_chains(rel_path, content))

        duration_ms = int((time.time() - start_time) * 1000)
        return StaticScanResult(
            issues=issues,
            files_scanned=len(source_files),
            duration_ms=duration_ms,
        )

    def _parse_exports(self, content: str) -> dict[str, Any]:
        """Extract default and named exports from a JS/JSX file."""
        has_default = bool(re.search(r"\bexport\s+default\b", content))
        named_exports: set[str] = set()

        # export const/function/class Foo
        for m in re.finditer(r"\bexport\s+(?:const|let|var|function|class)\s+([\w]+)", content):
            named_exports.add(m.group(1))

        # export { Foo, Bar as Baz }
        for m in re.finditer(r"\bexport\s*\{([^}]+)\}", content):
            for item in m.group(1).split(","):
                clean_item = item.strip()
                if " as " in clean_item:
                    clean_item = clean_item.split(" as ")[-1].strip()
                if clean_item and clean_item != "default":
                    named_exports.add(clean_item)

        return {"has_default": has_default, "named": named_exports}

    def _check_missing_jsx_imports(
        self,
        rel_path: str,
        content: str,
        export_registry: dict[str, dict[str, Any]]
    ) -> list[StaticIssue]:
        """Find JSX tags that are neither imported nor defined in the file."""
        issues: list[StaticIssue] = []
        lines = content.splitlines()

        # Parse all imported identifiers in this file (supports single & multi-line imports)
        imported_symbols: set[str] = set()

        # import { Foo, Bar as Baz } from '...' (supports multiline with re.DOTALL)
        for named_m in re.finditer(r"import\s*\{([^}]+)\}\s*from", content, re.DOTALL):
            for item in named_m.group(1).split(","):
                sym = item.strip()
                if " as " in sym:
                    sym = sym.split(" as ")[-1].strip()
                if sym:
                    imported_symbols.add(sym)

        # import Foo from '...'
        for def_m in re.finditer(r"import\s+([\w]+)\s+from", content):
            imported_symbols.add(def_m.group(1))

        # import * as Foo from '...'
        for ns_m in re.finditer(r"import\s+\*\s+as\s+([\w]+)\s+from", content):
            imported_symbols.add(ns_m.group(1))

        # Parse all locally defined identifiers in this file
        defined_symbols: set[str] = set()
        for line in lines:
            for m in re.finditer(r"\b(?:function|const|let|var|class)\s+([\w]+)", line):
                defined_symbols.add(m.group(1))

        # Scan for JSX tags: <CapitalizedTag ...> or <CapitalizedTag>
        seen_missing_in_file: set[str] = set()
        for idx, line in enumerate(lines, start=1):
            if line.strip().startswith("//") or line.strip().startswith("/*"):
                continue

            # Match <Identifier or <Identifier.Sub
            for m in re.finditer(r"<([A-Z][\w]*)", line):
                tag = m.group(1)
                if tag in STANDARD_JSX_TAGS:
                    continue
                if tag in imported_symbols or tag in defined_symbols:
                    continue
                if tag in seen_missing_in_file:
                    continue

                seen_missing_in_file.add(tag)

                # Check if this identifier is exported in another workspace file
                matching_export_file = None
                for other_path, exp in export_registry.items():
                    if other_path == rel_path:
                        continue
                    if tag in exp["named"] or (exp["has_default"] and Path(other_path).stem == tag):
                        matching_export_file = other_path
                        break

                if matching_export_file:
                    # It's a workspace component!
                    rel_import = os.path.relpath(
                        matching_export_file,
                        str(Path(rel_path).parent)
                    ).replace("\\", "/")
                    if not rel_import.startswith("."):
                        rel_import = f"./{rel_import}"
                    # Strip extension
                    rel_import = re.sub(r"\.(jsx?|tsx?)$", "", rel_import)
                    suggested = f"Add `import {tag} from '{rel_import}';` at the top of `{rel_path}`."
                else:
                    # It's likely a Lucide icon
                    suggested = f"Add `import {{ {tag} }} from 'lucide-react';` at the top of `{rel_path}`."

                issues.append(StaticIssue(
                    file_path=rel_path,
                    line_number=idx,
                    issue_type="missing_import",
                    identifier=tag,
                    snippet=line.strip()[:100],
                    suggested_fix=suggested,
                ))

        return issues

    def _check_import_paths_and_exports(
        self,
        rel_path: str,
        content: str,
        export_registry: dict[str, dict[str, Any]]
    ) -> list[StaticIssue]:
        """Check for broken local imports and mismatched named/default exports."""
        issues: list[StaticIssue] = []
        lines = content.splitlines()
        file_dir = Path(rel_path).parent

        # Match local imports: import ... from './...' or '../...' (supports single & multi-line)
        for m in re.finditer(
            r"import\s+(?:(?P<default>[\w]+)\s*,?\s*)?(?:\{(?P<named>[^}]+)\})?\s*from\s*['\"](?P<spec>\.\.?/[^'\"]+)['\"]",
            content,
            re.DOTALL,
        ):
            import_specifier = m.group("spec")
            raw_statement = m.group(0)
            idx = content[:m.start()].count('\n') + 1

            # Resolve target file path relative to workspace
            target_candidate = (file_dir / import_specifier).as_posix()

            # Try exact, .jsx, .js, .tsx, /index.jsx
            resolved_target = None
            for ext in ("", ".jsx", ".tsx", ".js", ".ts", "/index.jsx", "/index.js", "/index.tsx"):
                test_p = (self.workspace_path / f"{target_candidate}{ext}").resolve()
                try:
                    rel_test = str(test_p.relative_to(self.workspace_path)).replace("\\", "/")
                    if rel_test in export_registry:
                        resolved_target = rel_test
                        break
                except ValueError:
                    pass

            if not resolved_target:
                # Target file doesn't exist!
                issues.append(StaticIssue(
                    file_path=rel_path,
                    line_number=idx,
                    issue_type="missing_file",
                    identifier=import_specifier,
                    snippet=raw_statement.splitlines()[0].strip()[:100],
                    suggested_fix=f"File `{import_specifier}` does not exist. Create the component or update the import path in `{rel_path}`.",
                ))
            else:
                # File exists — verify named vs default export consistency
                exp = export_registry[resolved_target]
                named_block = m.group("named")
                if named_block:
                    for sym in named_block.split(","):
                        clean_sym = sym.strip()
                        if " as " in clean_sym:
                            clean_sym = clean_sym.split(" as ")[0].strip()
                        if clean_sym and clean_sym not in exp["named"]:
                            if exp["has_default"]:
                                issues.append(StaticIssue(
                                    file_path=rel_path,
                                    line_number=idx,
                                    issue_type="mismatched_export",
                                    identifier=clean_sym,
                                    snippet=f"`{clean_sym}` imported as named `{{ {clean_sym} }}`, but `{resolved_target}` uses `export default`",
                                    suggested_fix=f"Change to `import {clean_sym} from '{import_specifier}';` in `{rel_path}`, or add `export const {clean_sym}` to `{resolved_target}`.",
                                ))
                            else:
                                issues.append(StaticIssue(
                                    file_path=rel_path,
                                    line_number=idx,
                                    issue_type="mismatched_export",
                                    identifier=clean_sym,
                                    snippet=f"`{clean_sym}` is not exported by `{resolved_target}`",
                                    suggested_fix=f"Export `{clean_sym}` from `{resolved_target}` or remove it from the import in `{rel_path}`.",
                                ))

        return issues

    def _check_unguarded_arrays(self, rel_path: str, content: str) -> list[StaticIssue]:
        """Detect unguarded .map(), .filter(), .forEach() calls that could crash on initial render."""
        issues: list[StaticIssue] = []
        lines = content.splitlines()

        for idx, line in enumerate(lines, start=1):
            if line.strip().startswith("//") or line.strip().startswith("/*"):
                continue

            for method in ("map", "filter", "forEach"):
                pattern = rf"(\b[\w]+(?:\.[\w]+)*)\.{method}\("
                for m in re.finditer(pattern, line):
                    caller = m.group(1)
                    # Ignore safe callers: Array, Object, list || [], data?.
                    if caller in ("Array", "Object", "Math", "Promise"):
                        continue
                    # Check if line already has a null guard
                    has_guard = (
                        f"?.{method}(" in line or
                        f"|| []).{method}(" in line or
                        f"?? []).{method}(" in line or
                        f"({caller} || [])" in line or
                        f"&& {caller}.{method}(" in line
                    )
                    if not has_guard:
                        issues.append(StaticIssue(
                            file_path=rel_path,
                            line_number=idx,
                            issue_type="unguarded_array",
                            identifier=f"{caller}.{method}",
                            snippet=line.strip()[:100],
                            suggested_fix=f"Add null guard: `({caller} || []).{method}(...)` or `{caller}?.{method}(...) || []`.",
                        ))

        # Limit unguarded array warnings to max 3 per file to prevent prompt bloat
        return issues[:3]


    def _check_unguarded_property_chains(self, rel_path: str, content: str) -> list[StaticIssue]:
        """Detect unguarded deep property accesses like booking.guestDetails.adults."""
        issues: list[StaticIssue] = []
        lines = content.splitlines()

        for idx, line in enumerate(lines, start=1):
            if line.strip().startswith("//") or line.strip().startswith("/*"):
                continue
            if line.strip().startswith("import"):
                continue

            for m in DEEP_CHAIN_PATTERN.finditer(line):
                chain = m.group(1)

                # Skip if already guarded — but verify THIS specific chain is guarded
                line_has_any_guard = any(guard in line for guard in GUARD_PATTERNS)
                if line_has_any_guard:
                    chain_is_guarded = False
                    parts = chain.split(".")
                    for i in range(1, len(parts)):
                        partial = ".".join(parts[:i+1])
                        if f"{parts[i-1]}." + f"?.{parts[i]}" in line:
                            chain_is_guarded = True
                            break
                        if f"{partial} ||" in line or f"{partial}??" in line:
                            chain_is_guarded = True
                            break
                    if chain_is_guarded:
                        continue  # This specific chain is guarded — skip
                    # Chain is NOT guarded — fall through to flag it

                # Skip safe property accessors (check full chain and partial matches)
                is_safe = False
                for safe in SAFE_PROPERTY_ACCESSORS:
                    if chain == safe or chain.startswith(safe + "."):
                        is_safe = True
                        break
                if is_safe:
                    continue

                # Check if it's a known safe pattern (single-level access)
                parts = chain.split(".")
                if len(parts) < 2:
                    continue

                # Skip if it's a function call (method invocation)
                # Look ahead for ( after the chain
                end_pos = m.end()
                if end_pos < len(line) and line[end_pos] == "(":
                    continue

                # Skip if it's an assignment target
                if end_pos < len(line) and line[end_pos] == "=":

                    continue

                # This is a risky deep chain — add null guard suggestion
                # Suggestion: add ?. to the first level
                first_dot = chain.index(".")
                obj_name = chain[:first_dot]
                rest_chain = chain[first_dot:]

                # Skip if the object is a standard type
                if obj_name in ("this", "self", "window", "document", "console",
                                "Math", "JSON", "Object", "Array", "String",
                                "Number", "Boolean", "Date", "RegExp", "Error",
                                "Promise", "React", "process", "globalThis"):
                    continue

                issues.append(StaticIssue(
                    file_path=rel_path,
                    line_number=idx,
                    issue_type="unguarded_property",
                    identifier=chain,
                    snippet=line.strip()[:120],
                    suggested_fix=(
                        f"Add null guard: `{obj_name}?.{rest_chain.lstrip('.')}` "
                        f"or `{chain} || default` to prevent crash when data is undefined."
                    ),
                ))

        # Limit to max 5 per file to prevent prompt bloat
        return issues[:5]


def run_static_scan(workspace_path: str) -> StaticScanResult:
    """Convenience function to run a static pre-flight scan on a workspace."""
    scanner = StaticScanner(workspace_path)
    return scanner.scan()
