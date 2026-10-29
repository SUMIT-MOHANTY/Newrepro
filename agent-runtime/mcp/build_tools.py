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
    "vue_vite": "vue",
    "node_generic": "node",
    "python_fastapi": "fastapi",
    "python_django": "django",
    "python_flask": "flask",
    "python_generic": "python",
    "java_maven": "maven",
    "java_gradle": "gradle",
    "go_module": "go",
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

    def _inspect_dir_project(self, target_dir: Path) -> dict[str, Any] | None:
        """Inspect a single directory for project manifests across stacks."""
        if not target_dir.exists() or not target_dir.is_dir():
            return None

        # 1. Java Maven
        if (target_dir / "pom.xml").exists():
            return {"path": target_dir, "type": "java_maven", "tool": "mvn", "manifest": "pom.xml"}

        # 2. Java Gradle
        if (target_dir / "build.gradle").exists():
            return {"path": target_dir, "type": "java_gradle", "tool": "gradle", "manifest": "build.gradle"}
        if (target_dir / "build.gradle.kts").exists():
            return {"path": target_dir, "type": "java_gradle", "tool": "gradle", "manifest": "build.gradle.kts"}

        # 3. Go
        if (target_dir / "go.mod").exists():
            return {"path": target_dir, "type": "go_module", "tool": "go", "manifest": "go.mod"}

        # 4. Python
        py_manifest = None
        for cand in ("requirements.txt", "pyproject.toml", "setup.py", "Pipfile"):
            if (target_dir / cand).exists():
                py_manifest = cand
                break
        if py_manifest:
            ptype = "python_generic"
            try:
                content = (target_dir / py_manifest).read_text(encoding="utf-8", errors="replace").lower()
                if "fastapi" in content:
                    ptype = "python_fastapi"
                elif "django" in content:
                    ptype = "python_django"
                elif "flask" in content:
                    ptype = "python_flask"
            except Exception:
                pass
            return {"path": target_dir, "type": ptype, "tool": "pip", "manifest": py_manifest}

        # 5. Node.js / Frontend
        pkg = target_dir / "package.json"
        if pkg.exists():
            ptype = "node_generic"
            try:
                import json
                data = json.loads(pkg.read_text(encoding="utf-8", errors="replace"))
                deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
                if "next" in deps:
                    ptype = "next_js"
                elif "vue" in deps or "@vitejs/plugin-vue" in deps:
                    ptype = "vue_vite"
                elif "vite" in deps or "react" in deps:
                    ptype = "react_vite"
                elif "react-scripts" in deps:
                    ptype = "react_cra"
            except Exception:
                pass
            return {"path": target_dir, "type": ptype, "tool": "npm", "manifest": "package.json"}

        # 6. Static HTML (only if index.html exists)
        if (target_dir / "index.html").exists():
            return {"path": target_dir, "type": "static_html", "tool": "static", "manifest": "index.html"}

        return None

    def _find_all_project_dirs(self, root: Path) -> list[dict[str, Any]]:
        """Discover all subprojects within the workspace across stacks."""
        projects: list[dict[str, Any]] = []
        root_proj = self._inspect_dir_project(root)
        if root_proj:
            projects.append(root_proj)

        # Inspect common subdirectories and first-level children
        subdirs_to_check = ["backend", "server", "api", "service", "frontend", "client", "ui", "web", "app"]
        seen_paths = {root}
        if root_proj:
            seen_paths.add(root_proj["path"])

        for sub in subdirs_to_check:
            cand = root / sub
            if cand.exists() and cand.is_dir() and cand not in seen_paths:
                p_info = self._inspect_dir_project(cand)
                if p_info:
                    projects.append(p_info)
                    seen_paths.add(cand)

        try:
            for child in root.iterdir():
                if (
                    child.is_dir()
                    and not child.name.startswith(".")
                    and child.name not in ("node_modules", "venv", "__pycache__", "target", "build", "dist", ".git", "vibecoding", "agent-runtime", "scratch")
                    and child not in seen_paths
                ):
                    p_info = self._inspect_dir_project(child)
                    if p_info:
                        projects.append(p_info)
                        seen_paths.add(child)
        except Exception:
            pass

        return projects

    def detect_project_type(self, workspace: str | None = None) -> ToolResult:
        """Detect project stack dynamically across Java, Python, Go, Node, and HTML."""
        root = Path(workspace) if workspace else self._workspace
        projects = self._find_all_project_dirs(root)

        if not projects:
            # Check for loose python files
            if list(root.glob("*.py")):
                return ToolResult(success=True, data={"project_type": "python_generic", "manifests": []})
            # Check for loose java files
            if list(root.glob("*.java")):
                return ToolResult(success=True, data={"project_type": "java_maven", "manifests": []})
            return ToolResult(success=True, data={"project_type": "unknown", "manifests": []})

        primary = projects[0]["type"]
        if len(projects) > 1:
            types = [p["type"] for p in projects]
            has_backend = any("java" in t or "python" in t or "go" in t for t in types)
            has_frontend = any("react" in t or "vue" in t or "next" in t or "node" in t for t in types)
            if has_backend and has_frontend:
                primary = "fullstack"

        return ToolResult(
            success=True,
            data={
                "project_type": primary,
                "projects": [
                    {
                        "path": str(p["path"].relative_to(root)) if p["path"] != root else ".",
                        "type": p["type"],
                        "tool": p["tool"],
                        "manifest": p["manifest"],
                    }
                    for p in projects
                ],
            },
        )

    def _get_manifest_hash(self, manifest_file: Path) -> str:
        """Compute SHA256 hash of dependency manifest file."""
        import hashlib
        try:
            if not manifest_file.exists():
                return ""
            if manifest_file.name == "package.json":
                import json
                data = json.loads(manifest_file.read_text(encoding="utf-8", errors="replace"))
                deps = {
                    "dependencies": data.get("dependencies", {}),
                    "devDependencies": data.get("devDependencies", {}),
                }
                serialized = json.dumps(deps, sort_keys=True)
                return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
            else:
                content = manifest_file.read_bytes()
                return hashlib.sha256(content).hexdigest()
        except Exception:
            return ""

    def install_dependencies(self, workspace: str | None = None) -> ToolResult:
        """Run dependency installation dynamically based on detected manifests."""
        root = Path(workspace) if workspace else self._workspace
        projects = self._find_all_project_dirs(root)

        if not projects:
            return ToolResult(success=True, data={"message": "No recognized dependency manifest found — skipping install"})

        installed_messages: list[str] = []
        for p in projects:
            target_path = p["path"]
            cwd = str(target_path)
            ptype = p["type"]
            manifest_name = p["manifest"]
            manifest_file = target_path / manifest_name

            # 1. Java Maven
            if ptype == "java_maven":
                hash_file = target_path / ".maven_deps_hash"
                curr_hash = self._get_manifest_hash(manifest_file)
                if hash_file.exists() and curr_hash and hash_file.read_text(encoding="utf-8").strip() == curr_hash:
                    installed_messages.append(f"Maven dependencies up-to-date in {cwd}")
                    continue
                mvn_cmd = ["./mvnw", "dependency:resolve", "-B"] if (target_path / "mvnw").exists() else ["mvn", "dependency:resolve", "-B"]
                res = self._exec.run_command(mvn_cmd, cwd=cwd, timeout_seconds=self._limits.MAX_BUILD_TIME_SECONDS)
                if not res.success:
                    err = res.data.get("stderr") or res.data.get("stdout") or res.error if isinstance(res.data, dict) else res.error
                    return ToolResult(success=False, error=f"Maven dependency resolution failed in {cwd}:\n{err}")
                if curr_hash:
                    try:
                        hash_file.write_text(curr_hash, encoding="utf-8")
                    except Exception:
                        pass
                installed_messages.append(f"Maven dependencies resolved in {cwd}")

            # 2. Java Gradle
            elif ptype == "java_gradle":
                hash_file = target_path / ".gradle_deps_hash"
                curr_hash = self._get_manifest_hash(manifest_file)
                if hash_file.exists() and curr_hash and hash_file.read_text(encoding="utf-8").strip() == curr_hash:
                    installed_messages.append(f"Gradle dependencies up-to-date in {cwd}")
                    continue
                gradle_cmd = ["./gradlew", "dependencies", "--no-daemon"] if (target_path / "gradlew").exists() else ["gradle", "dependencies"]
                res = self._exec.run_command(gradle_cmd, cwd=cwd, timeout_seconds=self._limits.MAX_BUILD_TIME_SECONDS)
                if not res.success:
                    err = res.data.get("stderr") or res.data.get("stdout") or res.error if isinstance(res.data, dict) else res.error
                    return ToolResult(success=False, error=f"Gradle dependency resolution failed in {cwd}:\n{err}")
                if curr_hash:
                    try:
                        hash_file.write_text(curr_hash, encoding="utf-8")
                    except Exception:
                        pass
                installed_messages.append(f"Gradle dependencies resolved in {cwd}")

            # 3. Go
            elif ptype == "go_module":
                hash_file = target_path / ".go_deps_hash"
                curr_hash = self._get_manifest_hash(manifest_file)
                if hash_file.exists() and curr_hash and hash_file.read_text(encoding="utf-8").strip() == curr_hash:
                    installed_messages.append(f"Go module dependencies up-to-date in {cwd}")
                    continue
                res = self._exec.run_command(["go", "mod", "download"], cwd=cwd, timeout_seconds=self._limits.MAX_BUILD_TIME_SECONDS)
                if not res.success:
                    err = res.data.get("stderr") or res.data.get("stdout") or res.error if isinstance(res.data, dict) else res.error
                    return ToolResult(success=False, error=f"Go mod download failed in {cwd}:\n{err}")
                if curr_hash:
                    try:
                        hash_file.write_text(curr_hash, encoding="utf-8")
                    except Exception:
                        pass
                installed_messages.append(f"Go dependencies downloaded in {cwd}")

            # 4. Python
            elif ptype.startswith("python_"):
                hash_file = target_path / ".pip_deps_hash"
                curr_hash = self._get_manifest_hash(manifest_file)
                if hash_file.exists() and curr_hash and hash_file.read_text(encoding="utf-8").strip() == curr_hash:
                    installed_messages.append(f"Python dependencies up-to-date in {cwd}")
                    continue
                pip_cmd = ["pip", "install", "-r", manifest_name] if manifest_name == "requirements.txt" else ["pip", "install", "."]
                res = self._exec.run_command(pip_cmd, cwd=cwd, timeout_seconds=self._limits.MAX_BUILD_TIME_SECONDS)
                if not res.success:
                    err = res.data.get("stderr") or res.data.get("stdout") or res.error if isinstance(res.data, dict) else res.error
                    return ToolResult(success=False, error=f"pip install failed in {cwd}:\n{err}")
                if curr_hash:
                    try:
                        hash_file.write_text(curr_hash, encoding="utf-8")
                    except Exception:
                        pass
                installed_messages.append(f"Python dependencies installed in {cwd}")

            # 5. Node.js
            elif ptype in ("react_vite", "react_cra", "next_js", "vue_vite", "node_generic"):
                node_modules = target_path / "node_modules"
                hash_file = target_path / ".package_deps_hash"
                curr_hash = self._get_manifest_hash(manifest_file)
                if node_modules.exists() and hash_file.exists() and curr_hash:
                    if hash_file.read_text(encoding="utf-8").strip() == curr_hash:
                        installed_messages.append(f"Node dependencies up-to-date in {cwd}")
                        continue
                res = self._exec.run_command(
                    ["npm", "install", "--include=dev", "--prefer-offline", "--no-audit"],
                    cwd=cwd,
                    timeout_seconds=self._limits.MAX_BUILD_TIME_SECONDS,
                )
                if not res.success:
                    err = res.data.get("stderr") or res.data.get("stdout") or res.error if isinstance(res.data, dict) else res.error
                    return ToolResult(success=False, error=f"npm install failed in {cwd}:\n{err}")
                if curr_hash:
                    try:
                        hash_file.write_text(curr_hash, encoding="utf-8")
                    except Exception:
                        pass
                installed_messages.append(f"npm dependencies installed in {cwd}")

        return ToolResult(
            success=True,
            data={
                "message": "Dependencies processed: " + "; ".join(installed_messages),
                "installed_components": installed_messages,
            },
        )

    def run_build(self, workspace: str | None = None) -> ToolResult:
        """Run build across all detected projects in the workspace."""
        root = Path(workspace) if workspace else self._workspace
        projects = self._find_all_project_dirs(root)

        if not projects:
            # Fallback Python syntax check if loose python files exist
            py_files = [f for f in root.rglob("*.py") if "venv" not in f.parts and ".git" not in f.parts and "__pycache__" not in f.parts]
            if py_files:
                import py_compile
                errors = []
                for pf in py_files:
                    try:
                        py_compile.compile(str(pf), doraise=True)
                    except py_compile.PyCompileError as pe:
                        errors.append(str(pe))
                if errors:
                    return ToolResult(success=False, error="Python syntax errors:\n" + "\n".join(errors[:10]))
                return ToolResult(success=True, data={"message": f"Syntax verified for {len(py_files)} Python file(s)"})
            return ToolResult(success=True, data={"message": "No builds required for this project type"})

        for p in projects:
            target_path = p["path"]
            cwd = str(target_path)
            ptype = p["type"]

            # Java Maven
            if ptype == "java_maven":
                mvn_cmd = ["./mvnw", "compile", "-B"] if (target_path / "mvnw").exists() else ["mvn", "compile", "-B"]
                res = self._exec.run_command(mvn_cmd, cwd=cwd, timeout_seconds=self._limits.MAX_BUILD_TIME_SECONDS)
                if not res.success:
                    err = res.data.get("stderr") or res.data.get("stdout") or res.error if isinstance(res.data, dict) else res.error
                    return ToolResult(success=False, error=f"Maven compilation failed in {cwd}:\n{err}")

            # Java Gradle
            elif ptype == "java_gradle":
                gradle_cmd = ["./gradlew", "build", "-x", "test", "--no-daemon"] if (target_path / "gradlew").exists() else ["gradle", "build", "-x", "test"]
                res = self._exec.run_command(gradle_cmd, cwd=cwd, timeout_seconds=self._limits.MAX_BUILD_TIME_SECONDS)
                if not res.success:
                    err = res.data.get("stderr") or res.data.get("stdout") or res.error if isinstance(res.data, dict) else res.error
                    return ToolResult(success=False, error=f"Gradle build failed in {cwd}:\n{err}")

            # Go
            elif ptype == "go_module":
                res = self._exec.run_command(["go", "build", "./..."], cwd=cwd, timeout_seconds=self._limits.MAX_BUILD_TIME_SECONDS)
                if not res.success:
                    err = res.data.get("stderr") or res.data.get("stdout") or res.error if isinstance(res.data, dict) else res.error
                    return ToolResult(success=False, error=f"Go build failed in {cwd}:\n{err}")

            # Python
            elif ptype.startswith("python_"):
                import py_compile
                py_files = [f for f in target_path.rglob("*.py") if "venv" not in f.parts and ".git" not in f.parts and "__pycache__" not in f.parts]
                errors = []
                for pf in py_files:
                    try:
                        py_compile.compile(str(pf), doraise=True)
                    except py_compile.PyCompileError as pe:
                        errors.append(str(pe))
                if errors:
                    return ToolResult(success=False, error=f"Python compilation failed in {cwd}:\n" + "\n".join(errors[:10]))

            # Node.js
            elif ptype in ("react_vite", "react_cra", "next_js", "vue_vite", "node_generic"):
                pkg = target_path / "package.json"
                has_build_script = False
                if pkg.exists():
                    try:
                        import json
                        data = json.loads(pkg.read_text(encoding="utf-8", errors="replace"))
                        has_build_script = "build" in data.get("scripts", {})
                    except Exception:
                        pass
                if has_build_script:
                    res = self._exec.run_command(["npm", "run", "build"], cwd=cwd, timeout_seconds=self._limits.MAX_BUILD_TIME_SECONDS)
                    if not res.success:
                        err = res.data.get("stderr") or res.data.get("stdout") or res.error if isinstance(res.data, dict) else res.error
                        return ToolResult(success=False, error=f"npm run build failed in {cwd}:\n{err}")

        return ToolResult(success=True, data={"message": "All project components built and verified successfully", "workspace": str(root)})

    def install_and_build(self, workspace: str | None = None) -> ToolResult:
        """Combined install + build across any project stack (Java, Python, Go, Node, Fullstack)."""
        root = Path(workspace) if workspace else self._workspace

        # Step 1: Install dependencies
        install_res = self.install_dependencies(str(root))
        if not install_res.success:
            return install_res

        # Step 2: Run build
        build_res = self.run_build(str(root))
        if not build_res.success:
            err_detail = build_res.error or ""

            # Tailwind CSS @apply diagnostic
            if "does not exist" in err_detail and ("@apply" in err_detail or "postcss" in err_detail.lower()):
                err_detail += (
                    "\n\n[TAILWIND @apply DIAGNOSTIC]: In Tailwind CSS v3, `@apply` only works with classes that "
                    "actually exist (core Tailwind utilities, or colors/plugins declared in tailwind.config.js). "
                    "Custom one-off class names are NOT valid inside @apply. "
                    "Fix by using an arbitrary value instead (e.g. `@apply border-[#0F4C81]`), or declare the color in "
                    "tailwind.config.js under theme.extend.colors."
                )

            # Static unresolved imports check for JS/TS
            static_issues = scan_all_unresolved_imports(root)
            if static_issues:
                err_detail += (
                    "\n\n[DETECTED MISSING IMPORTS]:\n"
                    + "\n".join(static_issues[:15])
                    + "\n\nFix the missing imports or exports in the affected files before calling install_and_build again."
                )

            return ToolResult(success=False, error=err_detail)

        # Step 3: Scan runtime browser hazards for frontend components
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
                    "Build succeeded with 0 errors across all stack components. Provide a clean, high-level functional "
                    "summary for business users (describe user capabilities and workflow; omit technical paths and emoji clutter)."
                ),
                "workspace": str(root),
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
        import ast
        import shutil

        root = Path(workspace) if workspace else self._workspace
        target = Path(path) if Path(path).is_absolute() else (root / path)

        if not target.exists():
            return ToolResult(success=False, error=f"File not found: {path}")

        ext = target.suffix.lower()
        cwd = str(root)

        # 1. Python syntax check via native AST parse (exact line and column)
        if ext == ".py":
            try:
                code = target.read_text(encoding="utf-8", errors="replace")
                ast.parse(code, filename=str(target))
                return ToolResult(success=True, data={"status": "valid", "file": path, "message": "Python syntax valid"})
            except SyntaxError as se:
                return ToolResult(
                    success=False,
                    error=f"Python syntax error in {path} at line {se.lineno}, column {se.offset}:\n  {se.text or ''}\n{se.msg}"
                )
            except Exception as e:
                return ToolResult(success=False, error=f"Python parse error in {path}: {e}")

        # 2. JSON syntax check
        if ext == ".json":
            try:
                code = target.read_text(encoding="utf-8", errors="replace")
                import json
                json.loads(code)
                return ToolResult(success=True, data={"status": "valid", "file": path, "message": "JSON valid"})
            except Exception as e:
                return ToolResult(success=False, error=f"JSON parse error in {path}: {e}")

        # 3. Plain JS/Node syntax check
        if ext in (".js", ".mjs", ".cjs"):
            res = self._exec.run_command(["node", "--check", str(target)], cwd=cwd, timeout_seconds=5)
            if not res.success:
                err = res.data.get("stderr", "") if isinstance(res.data, dict) else res.error
                return ToolResult(success=False, error=f"Syntax error in {path}:\n{err}")
            return ToolResult(success=True, data={"status": "valid", "file": path, "message": "Syntax valid"})

        # 4. Java syntax check
        if ext == ".java":
            javac_bin = shutil.which("javac")
            if javac_bin:
                res = self._exec.run_command([javac_bin, "-Xlint:none", str(target)], cwd=str(target.parent), timeout_seconds=10)
                if not res.success:
                    err = res.data.get("stderr", "") if isinstance(res.data, dict) else res.error
                    return ToolResult(success=False, error=f"Java syntax error in {path}:\n{err}")
                return ToolResult(success=True, data={"status": "valid", "file": path, "message": "Java syntax valid"})

        # 5. Go syntax check
        if ext == ".go":
            go_bin = shutil.which("go")
            if go_bin:
                res = self._exec.run_command([go_bin, "vet", str(target)], cwd=str(target.parent), timeout_seconds=10)
                if not res.success:
                    err = res.data.get("stderr", "") if isinstance(res.data, dict) else res.error
                    return ToolResult(success=False, error=f"Go syntax error in {path}:\n{err}")
                return ToolResult(success=True, data={"status": "valid", "file": path, "message": "Go syntax valid"})

        # 6. JSX/TSX/TS syntax check via nearest project esbuild
        if ext in (".ts", ".tsx", ".jsx", ".vue", ".svelte", ".java", ".go"):
            esbuild_bin = None
            curr = target.parent
            while curr != curr.parent:
                cand = curr / "node_modules" / ".bin" / "esbuild"
                if cand.exists():
                    esbuild_bin = cand
                    break
                if (curr / "node_modules" / "@esbuild").exists():
                    cand_glob = list((curr / "node_modules" / "@esbuild").glob("**/bin/esbuild*"))
                    if cand_glob:
                        esbuild_bin = cand_glob[0]
                        break
                if curr == root or (curr / ".git").exists():
                    break
                curr = curr.parent

            if not esbuild_bin:
                for p in (root / "node_modules" / ".bin" / "esbuild",
                          Path("/template_workspace/node_modules/.bin/esbuild")):
                    if p.exists():
                        esbuild_bin = p
                        break

            if not esbuild_bin:
                which_eb = shutil.which("esbuild")
                if which_eb:
                    esbuild_bin = Path(which_eb)

            if esbuild_bin and esbuild_bin.exists():
                loader_arg = "--loader=tsx" if ext in (".tsx", ".jsx") else ("--loader=ts" if ext == ".ts" else None)
                cmd = [str(esbuild_bin), str(target), "--outfile=/dev/null"]
                if loader_arg:
                    cmd.append(loader_arg)
                res = self._exec.run_command(cmd, cwd=str(target.parent), timeout_seconds=5)
                if not res.success:
                    err = res.data.get("stderr", "") if isinstance(res.data, dict) else res.error
                    return ToolResult(success=False, error=f"Syntax error in {path}:\n{err}")
                return ToolResult(success=True, data={"status": "valid", "file": path, "message": "Syntax valid"})

            # Delimiter and bracket balance validator if esbuild binary is missing
            try:
                code = target.read_text(encoding="utf-8", errors="replace")
                lines = code.splitlines()
                stack = []
                delims = {'(': ')', '{': '}', '[': ']'}
                in_str = False
                str_char = None
                escape = False
                for line_idx, line in enumerate(lines, 1):
                    for col_idx, char in enumerate(line, 1):
                        if escape:
                            escape = False
                            continue
                        if char == '\\':
                            escape = True
                            continue
                        if in_str:
                            if char == str_char:
                                in_str = False
                            continue
                        if char in ('"', "'", '`'):
                            in_str = True
                            str_char = char
                            continue
                        if char in delims:
                            stack.append((char, line_idx, col_idx))
                        elif char in delims.values():
                            if not stack:
                                return ToolResult(
                                    success=False,
                                    error=f"Syntax error in {path} at line {line_idx}, col {col_idx}: Unexpected closing '{char}' with no opening match."
                                )
                            open_c, o_line, o_col = stack.pop()
                            if delims[open_c] != char:
                                return ToolResult(
                                    success=False,
                                    error=f"Syntax error in {path} at line {line_idx}, col {col_idx}: Mismatched bracket '{char}' (expected '{delims[open_c]}' opened at line {o_line})."
                                )
                if stack:
                    open_c, o_line, o_col = stack[-1]
                    return ToolResult(
                        success=False,
                        error=f"Syntax error in {path}: Unclosed '{open_c}' from line {o_line}, column {o_col}."
                    )
            except Exception:
                pass

        return ToolResult(success=True, data={"status": "valid", "file": path, "message": "File parsed successfully"})

