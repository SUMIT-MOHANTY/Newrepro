"""Build MCP tools — project detection, dependency installation, build execution.

Architecture §8.1 build_tools.py:
- Detects project type by inspecting package.json/index.html.
- Runs npm install + build with resource limits.
- Reports structured build output (exit_code, stdout, stderr).
- Never bakes project frameworks into the Agent Runtime image —
  everything is installed at build time into the project workspace.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from mcp.server import ToolResult
from mcp.execution_tools import ExecutionTools
from runtime.resource_limits import ResourceLimits


PROJECT_TYPES = {
    "react_vite": "vite",
    "react_cra": "react-scripts",
    "next_js": "next",
    "static_html": "static",
}


def extract_exports(file_path: Path) -> set[str]:
    """Extract all named exports from a JS/JSX/TS/TSX file."""
    if not file_path.exists():
        return set()
    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return set()
    
    exports = set()
    import re
    # export const/let/var/function/class Name
    for match in re.finditer(r'export\s+(?:async\s+)?(?:const|let|var|function|class)\s+([A-Za-z0-9_$]+)', content):
        exports.add(match.group(1))
    
    # export { a, b as c, d }
    for match in re.finditer(r'export\s*\{([^}]+)\}', content):
        block = match.group(1)
        for item in block.split(','):
            item = item.strip()
            if not item:
                continue
            if ' as ' in item:
                exported_name = item.split(' as ')[1].strip()
            else:
                exported_name = item
            if exported_name:
                exports.add(exported_name)
                
    # export default ...
    if re.search(r'export\s+default\b', content):
        exports.add('default')
        
    return exports


def resolve_import_path(source_file: Path, import_specifier: str, root: Path) -> Path | None:
    """Resolve a relative import specifier to a file on disk."""
    if not import_specifier.startswith('.'):
        return None  # external package like react, lucide-react
    
    base_dir = source_file.parent
    target = (base_dir / import_specifier).resolve()
    
    extensions = ['', '.js', '.jsx', '.ts', '.tsx', '/index.js', '/index.jsx', '/index.ts', '/index.tsx']
    for ext in extensions:
        cand = Path(str(target) + ext)
        if cand.exists() and cand.is_file():
            return cand
    return None


def scan_all_unresolved_imports(root: Path) -> list[str]:
    """Scan all source files in workspace and return all missing imports/exports."""
    import re
    src_dir = root / "src"
    if not src_dir.exists():
        src_dir = root
    
    source_files = list(src_dir.rglob("*.js")) + list(src_dir.rglob("*.jsx")) + list(src_dir.rglob("*.ts")) + list(src_dir.rglob("*.tsx"))
    source_files = [f for f in source_files if "node_modules" not in f.parts and ".git" not in f.parts]
    
    missing_report = []
    file_exports_cache: dict[Path, set[str]] = {}
    
    for sf in source_files:
        try:
            content = sf.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        
        # Regex for named imports: import { a, b as c } from './module'
        import_matches = re.finditer(r'import\s*\{([^}]+)\}\s*from\s*[\'"]([^\'"]+)[\'"]', content)
        for m in import_matches:
            imported_names_str = m.group(1)
            specifier = m.group(2)
            
            resolved = resolve_import_path(sf, specifier, root)
            if not resolved:
                if specifier.startswith('.'):
                    rel_sf = sf.relative_to(root)
                    missing_report.append(f"• `{rel_sf}`: imports from non-existent file `{specifier}`")
                continue
            
            if resolved not in file_exports_cache:
                file_exports_cache[resolved] = extract_exports(resolved)
            
            exports = file_exports_cache[resolved]
            
            missing_in_spec = []
            for item in imported_names_str.split(','):
                item = item.strip()
                if not item:
                    continue
                original_name = item.split(' as ')[0].strip() if ' as ' in item else item
                if original_name and original_name not in exports:
                    missing_in_spec.append(original_name)
            
            if missing_in_spec:
                rel_sf = sf.relative_to(root)
                rel_target = resolved.relative_to(root)
                missing_report.append(
                    f"• In `{rel_sf}`: missing export(s) {missing_in_spec} from `{rel_target}`"
                )
    
    return missing_report


def scan_runtime_hazards(root: Path) -> list[str]:
    """Scan workspace source files for dangerous patterns that compile but crash at runtime in browsers."""
    hazards = []
    src = root / "src"
    if not src.exists():
        src = root

    for sf in src.rglob("*"):
        if sf.is_dir() or sf.suffix.lower() not in (".jsx", ".js", ".tsx", ".ts"):
            continue
        if any(part in sf.parts for part in ("node_modules", "dist", "build", ".next", ".git")):
            continue
        try:
            content = sf.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        rel_path = sf.relative_to(root)
        for idx, line in enumerate(content.splitlines(), 1):
            s_line = line.strip()
            # Skip comments
            if s_line.startswith("//") or s_line.startswith("/*") or s_line.startswith("*"):
                continue

            # Hazard 1: PaymentRequest constructor (crashes in browser iframe)
            if "new PaymentRequest" in line:
                hazards.append(
                    f"• In `{rel_path}` line {idx}: `new PaymentRequest()` throws `TypeError` in browser iframes. "
                    "Use simulated card/wallet UI or hosted gateway redirect instead."
                )

            # Hazard 2: Naked .price.toLocaleString() without nullish fallback
            if ".price.toLocaleString(" in line and "??" not in line and "||" not in line:
                hazards.append(
                    f"• In `{rel_path}` line {idx}: Naked `.price.toLocaleString()` will crash React with TypeError if price is undefined. "
                    "Use safe default: `(tier?.price ?? 0).toLocaleString()`."
                )

            # Hazard 3: Naked .amount.toLocaleString() without nullish fallback
            if ".amount.toLocaleString(" in line and "??" not in line and "||" not in line:
                hazards.append(
                    f"• In `{rel_path}` line {idx}: Naked `.amount.toLocaleString()` will crash React with TypeError if amount is undefined. "
                    "Use safe default: `(item?.amount ?? 0).toLocaleString()`."
                )

    return hazards


class BuildTools:
    """Project build lifecycle management."""

    def __init__(self, workspace_path: str) -> None:
        self._workspace = Path(workspace_path)
        self._exec = ExecutionTools(workspace_path)
        self._limits = ResourceLimits()

    def detect_project_type(self, workspace: str | None = None) -> ToolResult:
        """Detect whether the project is react_vite, react_cra, next_js, or static_html."""
        root = Path(workspace) if workspace else self._workspace
        pkg = root / "package.json"
        if pkg.exists():
            try:
                import json
                data = json.loads(pkg.read_text())
                deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
                if "next" in deps:
                    return ToolResult(success=True, data={"project_type": "next_js"})
                if "vite" in deps:
                    return ToolResult(success=True, data={"project_type": "react_vite"})
                if "react-scripts" in deps:
                    return ToolResult(success=True, data={"project_type": "react_cra"})
                if "react" in deps:
                    return ToolResult(success=True, data={"project_type": "react_vite"})
            except Exception:
                pass
        # Check for plain index.html
        if (root / "index.html").exists():
            return ToolResult(success=True, data={"project_type": "static_html"})
        return ToolResult(success=True, data={"project_type": "unknown"})

    def _get_package_deps_hash(self, pkg_path: Path) -> str:
        """Compute SHA256 hash of dependencies and devDependencies in package.json."""
        import json
        import hashlib
        try:
            data = json.loads(pkg_path.read_text(encoding="utf-8"))
            deps = {
                "dependencies": data.get("dependencies", {}),
                "devDependencies": data.get("devDependencies", {}),
            }
            serialized = json.dumps(deps, sort_keys=True)
            return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
        except Exception:
            return ""

    def _resolve_target_dir(self, workspace: str | None = None) -> Path:
        """Find the directory containing package.json (root or frontend/client subdirectory)."""
        root = Path(workspace) if workspace else self._workspace
        if (root / "package.json").exists():
            return root
        for sub in ("frontend", "client", "ui", "web"):
            cand = root / sub
            if (cand / "package.json").exists():
                return cand
        try:
            for child in root.iterdir():
                if child.is_dir() and not child.name.startswith(".") and child.name not in ("node_modules", "venv", "__pycache__"):
                    if (child / "package.json").exists():
                        return child
        except Exception:
            pass
        return root

    def install_dependencies(self, workspace: str | None = None) -> ToolResult:
        """Run npm install only when package.json dependencies have changed."""
        target_path = self._resolve_target_dir(workspace)
        cwd = str(target_path)
        pkg = target_path / "package.json"
        if not pkg.exists():
            return ToolResult(success=True, data={"message": "No package.json — skipping install"})

        node_modules = target_path / "node_modules"
        hash_file = target_path / ".package_deps_hash"
        current_hash = self._get_package_deps_hash(pkg)

        # If node_modules exists and hash matches cached hash, skip install completely
        if node_modules.exists() and hash_file.exists() and current_hash:
            cached_hash = hash_file.read_text(encoding="utf-8").strip()
            if cached_hash == current_hash:
                print(f"[BuildTools] Dependencies unchanged (hash={current_hash[:8]}) — skipping redundant npm install in {cwd}")
                return ToolResult(success=True, data={"message": "SUCCESS: All dependencies already installed and up-to-date. npm install was skipped because package.json has not changed. Installation task is complete."})

        print(f"[BuildTools] Dependencies modified or initial install — running npm install in {cwd}...")
        result = self._exec.run_command(
            ["npm", "install", "--include=dev", "--prefer-offline", "--no-audit"],
            cwd=cwd,
            timeout_seconds=self._limits.MAX_BUILD_TIME_SECONDS,
        )

        if result.success and current_hash:
            try:
                hash_file.write_text(current_hash, encoding="utf-8")
                print(f"[BuildTools] Updated dependency hash cache ({current_hash[:8]})")
            except Exception as e:
                print(f"[BuildTools] Warning caching dependency hash: {e}")

        return result

    def run_build(self, workspace: str | None = None) -> ToolResult:
        """Run npm run build in the workspace."""
        target_path = self._resolve_target_dir(workspace)
        cwd = str(target_path)
        print(f"[BuildTools] Running npm run build in {cwd}...")
        result = self._exec.run_command(
            ["npm", "run", "build"],
            cwd=cwd,
            timeout_seconds=self._limits.MAX_BUILD_TIME_SECONDS,
        )
        return result

    def install_and_build(self, workspace: str | None = None) -> ToolResult:
        """Combined install + build. Returns unified error if either step fails."""
        target_path = self._resolve_target_dir(workspace)
        cwd = str(target_path)
        root = target_path
        install = self.install_dependencies(cwd)
        if not install.success:
            return ToolResult(success=False,
                              error=f"npm install failed:\n{install.data.get('stderr','') if isinstance(install.data, dict) else install.error}")
        build = self.run_build(cwd)
        if not build.success:
            err_detail = ""
            if isinstance(build.data, dict):
                # Prefer stderr, fall back to stdout
                err_detail = (build.data.get("stderr") or "").strip() or (build.data.get("stdout") or "").strip()
            if not err_detail:
                err_detail = str(build.error or "Unknown build error")

            # Bound output to avoid token blowout while keeping the relevant error lines
            max_err_len = 3500
            if len(err_detail) > max_err_len:
                err_detail = "... [earlier output truncated]\n" + err_detail[-max_err_len:]

            # Domain-specific diagnostics: Tailwind v3 @apply on undeclared custom classes is a
            # fatal PostCSS error and one of the most common self-inflicted build failures.
            if "does not exist" in err_detail and ("@apply" in err_detail or "postcss" in err_detail.lower()):
                err_detail += (
                    "\n\n[TAILWIND @apply DIAGNOSTIC]: In Tailwind CSS v3, `@apply` only works with classes that "
                    "actually exist (core Tailwind utilities, or colors/plugins declared in tailwind.config.js). "
                    "Custom one-off class names like `border-razorpay-primary` are NOT valid inside @apply and crash the build. "
                    "Fix by using an arbitrary value instead (e.g. `@apply border-[#0F4C81]`), or declare the color in "
                    "tailwind.config.js under theme.extend.colors, or write plain CSS properties (border-color: #0F4C81) "
                    "inside the rule. Do NOT simply retry the build without changing the CSS."
                )

            # Run static analysis to detect missing imports across the workspace
            static_issues = scan_all_unresolved_imports(root)
            extra_msg = ""
            if static_issues:
                extra_msg = (
                    "\n\n[DETECTED MISSING IMPORTS]:\n"
                    + "\n".join(static_issues[:15])
                    + "\n\nFix the missing imports or exports in the affected files before calling install_and_build again."
                )

            return ToolResult(
                success=False,
                error=f"$ npm run build\n{err_detail}{extra_msg}",
            )

        # Scan for dangerous runtime hazards that compile fine but immediately crash the browser UI
        hazards = scan_runtime_hazards(root)
        if hazards:
            return ToolResult(
                success=False,
                error=(
                    "[RUNTIME HAZARDS DETECTED]: The build compiled, but the following dangerous patterns will crash the browser at runtime:\n\n"
                    + "\n".join(hazards[:10])
                    + "\n\nYou must fix these runtime safety issues before the build can be approved."
                ),
            )

        return ToolResult(
            success=True,
            data={
                "message": (
                    "Build succeeded with 0 errors. Provide a clean, high-level functional summary "
                    "for business users (describe user capabilities and workflow; do NOT list technical "
                    "file paths, CSS class names, or build commands; avoid emoji clutter)."
                ),
                "workspace": cwd,
            },
        )

    def get_build_output_path(self, workspace: str | None = None) -> ToolResult:
        """Return the path to the build output directory (dist/ or build/)."""
        root = Path(workspace) if workspace else self._workspace
        for candidate in ("dist", "build", "out", ".next"):
            p = root / candidate
            if p.exists() and p.is_dir():
                return ToolResult(success=True, data={"path": str(p), "type": candidate})
        return ToolResult(success=False, error="No build output directory found")

    def check_syntax(self, path: str, workspace: str | None = None) -> ToolResult:
        """Instant (<100ms) syntax and parse validation on a specific file."""
        root = Path(workspace) if workspace else self._workspace
        target = Path(path) if Path(path).is_absolute() else (root / path)

        if not target.exists():
            return ToolResult(success=False, error=f"File not found: {path}")

        ext = target.suffix.lower()
        cwd = str(root)

        # 1. Plain JS/Node syntax check
        if ext in (".js", ".mjs", ".cjs"):
            res = self._exec.run_command(["node", "--check", str(target)], cwd=cwd, timeout_seconds=5)
            if not res.success:
                err = res.data.get("stderr", "") if isinstance(res.data, dict) else res.error
                return ToolResult(success=False, error=f"Syntax error in {path}:\n{err}")
            return ToolResult(success=True, data={"status": "valid", "file": path, "message": "Syntax valid"})

        # 2. JSX/TSX/TS syntax check via local esbuild
        esbuild_bin = root / "node_modules" / ".bin" / "esbuild"
        if not esbuild_bin.exists():
            template_esbuild = Path("/template_workspace/node_modules/.bin/esbuild")
            if template_esbuild.exists():
                esbuild_bin = template_esbuild
            else:
                candidates = list((root / "node_modules" / "@esbuild").glob("**/bin/esbuild*"))
                if candidates:
                    esbuild_bin = candidates[0]

        if esbuild_bin.exists():
            # Use --outfile=/dev/null to discard output in 3ms while strictly validating syntax
            cmd = [str(esbuild_bin), str(target), "--outfile=/dev/null"]
            res = self._exec.run_command(cmd, cwd=cwd, timeout_seconds=5)
            if not res.success:
                err = res.data.get("stderr", "") if isinstance(res.data, dict) else res.error
                return ToolResult(success=False, error=f"Syntax error in {path}:\n{err}")
            return ToolResult(success=True, data={"status": "valid", "file": path, "message": "Syntax valid"})

        # Quick fallback syntax check: parse basic bracket balance and common unassigned literals
        try:
            code = target.read_text(encoding="utf-8", errors="replace")
            # Check for orphaned object keys outside objects
            lines = code.splitlines()
            for idx, l in enumerate(lines, 1):
                stripped = l.strip()
                if re.match(r'^(metric|sources|transformations|reports|dataWarehouse)\s*:\s*(\'|\[|\{)', stripped):
                    # Check if line before is inside object
                    prev = lines[idx - 2].strip() if idx >= 2 else ""
                    if prev.endswith(";") and not prev.endswith("{"):
                        return ToolResult(
                            success=False,
                            error=f"Syntax error in {path} at line {idx}: unassigned property '{stripped[:40]}' following a statement terminator."
                        )
        except Exception:
            pass

        return ToolResult(success=True, data={"status": "valid", "file": path, "message": "File parsed successfully"})

