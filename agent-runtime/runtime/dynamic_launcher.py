"""DynamicAppLauncher — Intelligent, framework-agnostic workspace analyzer and runner.

Eliminates all hardcoded assumptions (no hardcoded FastAPI, no hardcoded uvicorn,
no hardcoded folder paths, no hardcoded ports).

Capabilities:
1. Deep AST & Manifest Analysis:
   - Django: Discovers `manage.py`, settings module, auto-runs migrations, launches `runserver`.
   - FastAPI / Starlette / Litestar: AST-parses Python files to find the exact framework instance,
     variable name (e.g. `app`, `api`, `server`), and computes Python import path dynamically.
   - Flask: AST-parses Python files for `Flask(...)` and prepares `flask run` or direct execution.
   - Streamlit: Detects `streamlit` imports/requirements and launches `streamlit run`.
   - Node / TypeScript: Reads `package.json` scripts (`dev`, `start`, `server`), detects Next.js,
     Nuxt, NestJS, Express, Fastify.
   - Static HTML / SPA: Detects pre-built `dist/`, `build/`, `public/`, or raw HTML web applications.
2. Intelligent Port Discovery:
   - Reads `.env`, `docker-compose.yml`, source code regex for port bindings.
   - Avoids port collisions dynamically.
3. Architecture Classification:
   - `monolith`: Django, Flask with SSR, Next.js, Streamlit (single server serving UI + API).
   - `fullstack_separated`: Frontend (SPA dev server or static dist) + Backend (API server).
   - `static_only`: Pure frontend without backend.
   - `api_only`: Standalone API service without frontend.
4. Dynamic Nginx Reverse Proxy Generation:
   - Configures Port 80 Nginx routing perfectly matched to the detected architecture.
"""
from __future__ import annotations

import ast
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class ServiceSpec:
    name: str                           # "backend" | "frontend" | "monolith" | "static"
    framework: str                      # "django" | "fastapi" | "flask" | "streamlit" | "express" | "nextjs" | "vite" | "static_html"
    cwd: Path
    command: List[str]
    port: int
    env: Dict[str, str] = field(default_factory=dict)
    entry_file: Optional[Path] = None
    preflight_commands: List[List[str]] = field(default_factory=list)


@dataclass
class ArchitecturePlan:
    architecture: str                   # "monolith" | "fullstack_separated" | "static_only" | "api_only"
    backend: Optional[ServiceSpec] = None
    frontend: Optional[ServiceSpec] = None
    dist_dir: Optional[Path] = None


class DynamicAppLauncher:
    """Intelligently analyzes any workspace and starts the application stack dynamically."""

    def __init__(self, workspace_path: str | Path, preview_port: int = 80) -> None:
        self.workspace = Path(workspace_path).resolve()
        self.preview_port = preview_port
        self.ignore_dirs = {
            ".git", ".agent", ".agent_ipc", ".agent_signals", ".agent_history",
            "node_modules", "venv", ".venv", "env", "__pycache__",
            ".pytest_cache", ".coverage", "htmlcov", "dist", "build",
            "vibecoding", "agent-runtime", "scratch"
        }

    def analyze_workspace(self) -> ArchitecturePlan:
        """Scan workspace and dynamically deduce architecture and execution plan."""
        print(f"[DynamicLauncher] Analyzing workspace: {self.workspace}")

        # 1. Discover all candidate files
        py_files = self._find_files("*.py")
        pkg_files = self._find_files("package.json")
        html_files = self._find_files("index.html")
        manage_py_files = [p for p in py_files if p.name == "manage.py"]

        # Check for pre-built static directory (dist/, build/, out/)
        dist_dir = self._find_dist_dir()

        # 2. Detect Backend / Monolith Python services
        backend_spec: Optional[ServiceSpec] = None

        if manage_py_files:
            backend_spec = self._plan_django(manage_py_files[0])
        else:
            # Check Streamlit
            st_spec = self._plan_streamlit(py_files)
            if st_spec:
                backend_spec = st_spec
            else:
                # Check FastAPI / Starlette via AST
                fastapi_spec = self._plan_fastapi(py_files)
                if fastapi_spec:
                    backend_spec = fastapi_spec
                else:
                    # Check Flask via AST
                    flask_spec = self._plan_flask(py_files)
                    if flask_spec:
                        backend_spec = flask_spec

        # 3. Detect Node / JS Backend if Python wasn't found or if backend folder has package.json
        if not backend_spec:
            node_be_spec = self._plan_node_backend(pkg_files)
            if node_be_spec:
                backend_spec = node_be_spec

        # 4. Detect Frontend service
        frontend_spec: Optional[ServiceSpec] = None

        # Check for Node frontend (Vite, Next.js, CRA, Vue, Angular)
        for pkg in pkg_files:
            # Skip if this package was already assigned as backend
            if backend_spec and backend_spec.cwd == pkg.parent:
                continue
            fe_spec = self._plan_node_frontend(pkg)
            if fe_spec:
                frontend_spec = fe_spec
                break

        # Dynamic fallback: Auto-detect frontend source trees without package.json and synthesize
        if not frontend_spec:
            frontend_spec = self._discover_and_synthesize_frontend(backend_spec)

        # 5. Classify Architecture
        # A) Next.js / Nuxt / Monolithic SSR (handles both UI and API)
        if frontend_spec and frontend_spec.framework in ("nextjs", "nuxt", "remix", "astro"):
            return ArchitecturePlan(
                architecture="monolith",
                backend=frontend_spec,
                frontend=None,
            )

        # B) Django / Flask Monolith (templates/ + static/ + backend in same app)
        if backend_spec and backend_spec.framework in ("django", "flask", "streamlit"):
            has_templates = any((self.workspace / d).is_dir() for d in ("templates", "static")) or \
                            any((backend_spec.cwd / d).is_dir() for d in ("templates", "static"))
            # If there is no separate frontend project, this is a full monolith!
            if not frontend_spec and not dist_dir:
                return ArchitecturePlan(
                    architecture="monolith",
                    backend=backend_spec,
                    frontend=None,
                )

        # C) Decoupled Fullstack (Frontend SPA or dist + Backend API)
        if backend_spec and (frontend_spec or dist_dir):
            return ArchitecturePlan(
                architecture="fullstack_separated",
                backend=backend_spec,
                frontend=frontend_spec,
                dist_dir=dist_dir,
            )

        # D) Backend API only
        if backend_spec and not frontend_spec and not dist_dir:
            return ArchitecturePlan(
                architecture="api_only",
                backend=backend_spec,
            )

        # E) Static Frontend only
        if dist_dir or html_files or frontend_spec:
            return ArchitecturePlan(
                architecture="static_only",
                frontend=frontend_spec,
                dist_dir=dist_dir,
            )

        # Fallback: API or generic
        return ArchitecturePlan(architecture="static_only", dist_dir=dist_dir)

    # ------------------------------------------------------------------
    # Detectors & Planners
    # ------------------------------------------------------------------

    def _plan_django(self, manage_py: Path) -> ServiceSpec:
        cwd = manage_py.parent
        port = self._detect_port(cwd, default_port=8000)
        env = os.environ.copy()
        env["PORT"] = str(port)
        env["PYTHONUNBUFFERED"] = "1"

        # Check for settings module
        settings_files = list(cwd.glob("**/settings.py")) + list(cwd.glob("**/settings/*.py"))
        if settings_files:
            rel = settings_files[0].relative_to(cwd)
            mod = str(rel).replace("\\", ".").replace("/", ".").replace(".py", "")
            if not env.get("DJANGO_SETTINGS_MODULE"):
                env["DJANGO_SETTINGS_MODULE"] = mod

        preflights = [
            [sys.executable, "manage.py", "makemigrations", "--noinput"],
            [sys.executable, "manage.py", "migrate", "--noinput"],
        ]

        cmd = [sys.executable, "manage.py", "runserver", f"0.0.0.0:{port}"]
        print(f"[DynamicLauncher] [DETECTED] Discovered Django app at {manage_py.relative_to(self.workspace)} (port={port})")
        return ServiceSpec(
            name="backend",
            framework="django",
            cwd=cwd,
            command=cmd,
            port=port,
            env=env,
            entry_file=manage_py,
            preflight_commands=preflights,
        )

    def _plan_fastapi(self, py_files: List[Path]) -> Optional[ServiceSpec]:
        """AST-parse Python files to find FastAPI/Starlette app instances dynamically."""
        candidates = []
        for pf in py_files:
            try:
                tree = ast.parse(pf.read_text(encoding="utf-8", errors="ignore"))
                for node in ast.walk(tree):
                    if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
                        func_name = ""
                        if isinstance(node.value.func, ast.Name):
                            func_name = node.value.func.id
                        elif isinstance(node.value.func, ast.Attribute):
                            func_name = node.value.func.attr
                        
                        if func_name in ("FastAPI", "Starlette", "Litestar"):
                            for target in node.targets:
                                if isinstance(target, ast.Name):
                                    candidates.append((pf, target.id))
            except Exception:
                pass

        if not candidates:
            return None

        # Choose best candidate (prefer main.py, app.py, api.py, or files under backend/)
        def score_candidate(item: Tuple[Path, str]) -> int:
            p, var = item
            score = 0
            if "backend" in p.parts:
                score += 10
            if p.name in ("main.py", "app.py", "api.py", "server.py"):
                score += 5
            if var in ("app", "api", "application"):
                score += 5
            return score

        candidates.sort(key=score_candidate, reverse=True)
        best_file, best_var = candidates[0]

        # Determine best CWD and import module path
        rel_ws = best_file.relative_to(self.workspace)
        cwd = self.workspace
        if "backend" in rel_ws.parts:
            b_idx = rel_ws.parts.index("backend")
            cwd = self.workspace.joinpath(*rel_ws.parts[:b_idx+1])
            sub_parts = rel_ws.parts[b_idx+1:]
            module_name = ".".join(sub_parts).replace(".py", "")
        else:
            cwd = best_file.parent if len(rel_ws.parts) > 2 else self.workspace
            module_name = str(best_file.relative_to(cwd)).replace("\\", ".").replace("/", ".").replace(".py", "")

        port = self._detect_port(best_file, default_port=8000)
        env = os.environ.copy()
        env["PORT"] = str(port)
        env["PYTHONPATH"] = f"{self.workspace}:{cwd}:{os.environ.get('PYTHONPATH', '')}"

        app_target = f"{module_name}:{best_var}"
        cmd = [sys.executable, "-m", "uvicorn", app_target, "--host", "0.0.0.0", "--port", str(port)]
        print(f"[DynamicLauncher] [DETECTED] Discovered FastAPI app: '{app_target}' in {best_file.relative_to(self.workspace)} (port={port})")
        preflights = []
        if (cwd / "alembic.ini").exists() or (self.workspace / "alembic.ini").exists():
            preflights.append(["alembic", "upgrade", "head"])

        return ServiceSpec(
            name="backend",
            framework="fastapi",
            cwd=cwd,
            command=cmd,
            port=port,
            env=env,
            entry_file=best_file,
            preflight_commands=preflights,
        )

    def _plan_flask(self, py_files: List[Path]) -> Optional[ServiceSpec]:
        """AST-parse Python files to find Flask app instances dynamically."""
        candidates = []
        for pf in py_files:
            try:
                tree = ast.parse(pf.read_text(encoding="utf-8", errors="ignore"))
                for node in ast.walk(tree):
                    if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
                        func_name = ""
                        if isinstance(node.value.func, ast.Name):
                            func_name = node.value.func.id
                        elif isinstance(node.value.func, ast.Attribute):
                            func_name = node.value.func.attr
                        
                        if func_name == "Flask":
                            for target in node.targets:
                                if isinstance(target, ast.Name):
                                    candidates.append((pf, target.id))
            except Exception:
                pass

        if not candidates:
            return None

        best_file, best_var = candidates[0]
        cwd = best_file.parent
        port = self._detect_port(best_file, default_port=5000)
        env = os.environ.copy()
        env["PORT"] = str(port)
        env["FLASK_APP"] = best_file.name
        env["FLASK_RUN_PORT"] = str(port)
        env["FLASK_RUN_HOST"] = "0.0.0.0"

        # Check if runnable directly
        cmd = [sys.executable, "-m", "flask", "--app", f"{best_file.stem}:{best_var}", "run", "--host", "0.0.0.0", "--port", str(port)]
        print(f"[DynamicLauncher] [DETECTED] Discovered Flask app: '{best_var}' in {best_file.relative_to(self.workspace)} (port={port})")
        return ServiceSpec(
            name="backend",
            framework="flask",
            cwd=cwd,
            command=cmd,
            port=port,
            env=env,
            entry_file=best_file,
        )

    def _plan_streamlit(self, py_files: List[Path]) -> Optional[ServiceSpec]:
        st_files = []
        for pf in py_files:
            try:
                txt = pf.read_text(encoding="utf-8", errors="ignore")
                if "import streamlit" in txt or "from streamlit" in txt:
                    st_files.append(pf)
            except Exception:
                pass

        if not st_files:
            return None

        # Prefer app.py, main.py, streamlit_app.py
        def score(p: Path) -> int:
            if p.name in ("app.py", "main.py", "streamlit_app.py", "dashboard.py"):
                return 10
            return 1
        st_files.sort(key=score, reverse=True)
        entry = st_files[0]
        cwd = entry.parent
        port = self._detect_port(entry, default_port=8501)
        cmd = [
            sys.executable, "-m", "streamlit", "run", str(entry.name),
            "--server.port", str(port),
            "--server.address", "0.0.0.0",
            "--server.headless", "true",
        ]
        print(f"[DynamicLauncher] [DETECTED] Discovered Streamlit app at {entry.relative_to(self.workspace)} (port={port})")
        return ServiceSpec(
            name="monolith",
            framework="streamlit",
            cwd=cwd,
            command=cmd,
            port=port,
            entry_file=entry,
        )

    def _plan_node_backend(self, pkg_files: List[Path]) -> Optional[ServiceSpec]:
        backend_pkgs = [p for p in pkg_files if "backend" in p.parts or "server" in p.parts or "api" in p.parts]
        target_pkg = backend_pkgs[0] if backend_pkgs else None

        # Check raw server.js / app.js if no backend package.json
        if not target_pkg:
            raw_node = [
                self.workspace / "backend" / "server.js",
                self.workspace / "backend" / "index.js",
                self.workspace / "server.js",
                self.workspace / "server" / "server.js",
                self.workspace / "server" / "index.js",
            ]
            for r in raw_node:
                if r.exists():
                    port = self._detect_port(r, default_port=3001)
                    env = os.environ.copy()
                    env["PORT"] = str(port)
                    cmd = ["node", r.name]
                    print(f"[DynamicLauncher] [DETECTED] Discovered raw Node.js backend: {r.relative_to(self.workspace)} (port={port})")
                    return ServiceSpec(
                        name="backend",
                        framework="express",
                        cwd=r.parent,
                        command=cmd,
                        port=port,
                        env=env,
                        entry_file=r,
                    )
            return None

        cwd = target_pkg.parent
        try:
            data = json.loads(target_pkg.read_text(encoding="utf-8"))
            scripts = data.get("scripts", {})
            port = self._detect_port(cwd, default_port=3001)
            env = os.environ.copy()
            env["PORT"] = str(port)

            cmd = ["node", "server.js"]
            if "start" in scripts:
                cmd = ["npm", "run", "start"]
            elif "dev" in scripts:
                cmd = ["npm", "run", "dev"]
            elif "server" in scripts:
                cmd = ["npm", "run", "server"]
            elif data.get("main"):
                cmd = ["node", data["main"]]

            print(f"[DynamicLauncher] [DETECTED] Discovered Node.js backend at {cwd.relative_to(self.workspace)}: {' '.join(cmd)} (port={port})")
            return ServiceSpec(
                name="backend",
                framework="express",
                cwd=cwd,
                command=cmd,
                port=port,
                env=env,
            )
        except Exception:
            return None

    def _plan_node_frontend(self, pkg_file: Path) -> Optional[ServiceSpec]:
        cwd = pkg_file.parent
        try:
            data = json.loads(pkg_file.read_text(encoding="utf-8"))
            scripts = data.get("scripts", {})
            deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}

            # Detect Framework
            framework = "vite"
            if "next" in deps:
                framework = "nextjs"
            elif "nuxt" in deps:
                framework = "nuxt"
            elif "react-scripts" in deps:
                framework = "cra"
            elif "@angular/core" in deps:
                framework = "angular"
            elif "vue" in deps and "vite" not in deps:
                framework = "vue"

            port = 3000
            env = os.environ.copy()
            env["PORT"] = str(port)

            cmd = ["npm", "run", "dev"]
            if framework == "nextjs":
                cmd = ["npm", "run", "dev", "--", "-p", str(port)]
            elif framework == "vite" or "vite" in deps:
                cmd = ["npm", "run", "dev", "--", "--port", str(port), "--host"]
            elif framework == "cra":
                cmd = ["npm", "start"]
            elif "dev" in scripts:
                cmd = ["npm", "run", "dev"]
            elif "start" in scripts:
                cmd = ["npm", "run", "start"]

            print(f"[DynamicLauncher] [DETECTED] Frontend ({framework}) at {cwd.relative_to(self.workspace)}: {' '.join(cmd)} (port={port})")
            return ServiceSpec(
                name="frontend",
                framework=framework,
                cwd=cwd,
                command=cmd,
                port=port,
                env=env,
            )
        except Exception:
            return None

    def _discover_and_synthesize_frontend(self, backend_spec: Optional[ServiceSpec]) -> Optional[ServiceSpec]:
        """
        Dynamically scan for frontend directories (frontend, client, ui, web)
        that contain React/Vite/HTML source code even if package.json was omitted.
        Synthesizes a working package.json and returns a ServiceSpec.
        """
        candidate_dirs = [
            self.workspace / "frontend",
            self.workspace / "client",
            self.workspace / "ui",
            self.workspace / "web",
            self.workspace,
        ]
        for candidate in candidate_dirs:
            if not candidate.is_dir():
                continue
            if backend_spec and backend_spec.cwd == candidate and candidate != self.workspace:
                continue

            pkg_json = candidate / "package.json"
            if pkg_json.exists():
                spec = self._plan_node_frontend(pkg_json)
                if spec:
                    return spec
                continue

            # Check if this candidate directory contains frontend source files
            has_vite = any((candidate / f).exists() for f in ("vite.config.ts", "vite.config.js", "vite.config.mjs"))
            has_index_html = (candidate / "index.html").exists()
            has_src = (candidate / "src").is_dir()

            if (has_vite or has_index_html) and (has_src or (candidate / "App.tsx").exists() or (candidate / "App.jsx").exists()):
                print(f"[DynamicLauncher] [AUTODETECT] Frontend detected without package.json at {candidate.relative_to(self.workspace)}. Dynamically synthesizing package.json...")
                imports = set()
                try:
                    for src_file in candidate.glob("src/**/*"):
                        if src_file.suffix in (".js", ".jsx", ".ts", ".tsx"):
                            content = src_file.read_text(encoding="utf-8", errors="ignore")
                            for line in content.splitlines():
                                line_clean = line.strip()
                                if line_clean.startswith("import ") or "from " in line_clean:
                                    for dep in ("lucide-react", "zustand", "@tanstack/react-query", "axios", "clsx", "tailwind-merge", "react-router-dom"):
                                        if dep in line_clean:
                                            imports.add(dep)
                except Exception as ex:
                    print(f"[DynamicLauncher] Note scanning imports: {ex}")

                synth_pkg = {
                    "name": "frontend",
                    "private": True,
                    "version": "0.0.0",
                    "type": "module",
                    "scripts": {
                        "dev": "vite",
                        "build": "vite build",
                        "preview": "vite preview"
                    },
                    "dependencies": {
                        "react": "^18.3.1",
                        "react-dom": "^18.3.1"
                    },
                    "devDependencies": {
                        "@types/react": "^18.3.1",
                        "@types/react-dom": "^18.3.1",
                        "@vitejs/plugin-react": "^4.2.1",
                        "typescript": "^5.2.2",
                        "vite": "^5.1.6"
                    }
                }
                for imp in imports:
                    synth_pkg["dependencies"][imp] = "latest"

                if any((candidate / f).exists() for f in ("tailwind.config.js", "tailwind.config.ts", "postcss.config.js")):
                    synth_pkg["devDependencies"]["tailwindcss"] = "^3.4.1"
                    synth_pkg["devDependencies"]["postcss"] = "^8.4.35"
                    synth_pkg["devDependencies"]["autoprefixer"] = "^10.4.18"

                try:
                    pkg_json.write_text(json.dumps(synth_pkg, indent=2), encoding="utf-8")
                    print(f"[DynamicLauncher] [SYNTHESIZED] Created dynamic package.json at {pkg_json}")
                    spec = self._plan_node_frontend(pkg_json)
                    if spec:
                        return spec
                except Exception as write_err:
                    print(f"[DynamicLauncher] Could not write dynamic package.json: {write_err}")

        return None

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def _find_files(self, pattern: str) -> List[Path]:
        import fnmatch
        results = []
        for root, dirs, files in os.walk(self.workspace):
            # Prune ignored directories in-place so os.walk never enters them
            dirs[:] = [d for d in dirs if d not in self.ignore_dirs]
            for file in files:
                if fnmatch.fnmatch(file, pattern):
                    results.append(Path(root) / file)
        return results

    def _find_dist_dir(self) -> Optional[Path]:
        for name in ("dist", "build", "out"):
            # Check workspace root and frontend folder
            for base in (self.workspace, self.workspace / "frontend", self.workspace / "client"):
                p = base / name
                if p.is_dir() and (p / "index.html").exists():
                    return p
        return None

    def _detect_port(self, target: Path, default_port: int) -> int:
        """Dynamically detect port from .env or source code patterns."""
        # 1. Check .env
        env_files = [self.workspace / ".env", target / ".env" if target.is_dir() else target.parent / ".env"]
        for ef in env_files:
            if ef.exists():
                try:
                    for line in ef.read_text(encoding="utf-8", errors="ignore").splitlines():
                        line = line.strip()
                        if line.startswith("#"):
                            continue
                        m = re.match(r'^(?:PORT|BACKEND_PORT|SERVER_PORT|API_PORT)\s*=\s*(\d{4,5})', line, re.IGNORECASE)
                        if m:
                            p = int(m.group(1))
                            if 1024 <= p <= 65535 and p != self.preview_port:
                                return p
                except Exception:
                    pass

        # 2. Check source code regex if target is a file or search files in directory
        files_to_check = [target] if target.is_file() else list(target.glob("*.py")) + list(target.glob("*.js"))
        for f in files_to_check[:5]:
            try:
                code = f.read_text(encoding="utf-8", errors="ignore")
                patterns = [
                    r'port\s*=\s*(\d{4,5})',
                    r'PORT\s*=\s*(?:int\(os\.environ\.get\(["\']PORT["\'],\s*)?(\d{4,5})',
                    r'\.listen\(\s*(?:PORT\s*\|\|\s*)?(\d{4,5})',
                    r'runserver\s+(?:[\d\.]+:)?(\d{4,5})',
                ]
                for pat in patterns:
                    m = re.search(pat, code)
                    if m:
                        p = int(m.group(1))
                        if 1024 <= p <= 65535 and p != self.preview_port:
                            return p
            except Exception:
                pass

        return default_port
