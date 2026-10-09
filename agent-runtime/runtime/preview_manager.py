"""PreviewManager — Dynamically serves applications via intelligent framework detection & Nginx on Port 80.

Architecture & Capabilities:
- Dynamic Framework Detection: Integrates DynamicAppLauncher to automatically detect:
  - Django (manage.py, auto-runs migrations, runserver)
  - FastAPI / Starlette / Litestar (AST-parsed module and variable name, uvicorn)
  - Flask (AST-parsed app instance, python/flask run)
  - Streamlit (dashboard runner)
  - Next.js / Nuxt / Remix / Astro (monolithic SSR frameworks)
  - Node.js / Express / NestJS / Fastify (package.json scripts or raw scripts)
  - React / Vite / CRA / Vue / Angular (frontend SPA dev server or pre-built dist)
  - Pure HTML/CSS/JS static applications
- Unified Reverse Proxy on Port 80:
  - Monoliths (Django, Flask SSR, Next.js, Streamlit): Proxies all `/` traffic to application port.
  - Decoupled Fullstack: Proxies `/api/`, `/docs`, `/openapi.json`, `/ws/` to backend, `/` to frontend.
  - Pure Static: Serves static files directly with HTML5 SPA pushState routing.
- Zero Hardcoding: Dynamically inspects project AST, manifests, and .env files.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from runtime.dynamic_launcher import DynamicAppLauncher, ArchitecturePlan, ServiceSpec


@dataclass
class PreviewInfo:
    url: str
    port: int
    preview_type: str   # "fullstack_static" | "fullstack_dev" | "static" | "dev_server" | "monolith"
    dist_path: str | None = None
    backend_port: int | None = None
    backend_error: str | None = None       # Error output if backend failed to start
    backend_entrypoint: str | None = None  # Exact path to backend entrypoint
    backend_cwd: str | None = None         # Working directory of backend service
    frontend_error: str | None = None      # Error output if frontend failed to start / compile
    frontend_cwd: str | None = None        # Working directory of frontend service


NGINX_MONOLITH_CONF = """
server {{
    listen 80 default_server;
    server_name _;
    client_max_body_size 50M;

    location / {{
        proxy_pass http://127.0.0.1:{app_port};
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
        proxy_connect_timeout 10s;
        proxy_cache_bypass $http_upgrade;
    }}

    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml;
}}
"""

NGINX_FULLSTACK_STATIC_CONF = """
server {{
    listen 80 default_server;
    server_name _;
    client_max_body_size 50M;

    # 1. API Reverse Proxy to Backend Service
    location /api/ {{
        proxy_pass http://127.0.0.1:{backend_port};
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
        proxy_connect_timeout 10s;
        proxy_cache_bypass $http_upgrade;
    }}

    location = /api {{
        proxy_pass http://127.0.0.1:{backend_port};
        proxy_http_version 1.1;
        proxy_set_header Host $host;
    }}

    location /docs {{
        proxy_pass http://127.0.0.1:{backend_port};
        proxy_http_version 1.1;
        proxy_set_header Host $host;
    }}

    location /openapi.json {{
        proxy_pass http://127.0.0.1:{backend_port};
        proxy_http_version 1.1;
        proxy_set_header Host $host;
    }}

    # 2. Frontend Application (Static SPA)
    location / {{
        root {dist_path};
        index index.html;
        try_files $uri $uri/ /index.html;
    }}

    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml;
}}
"""

NGINX_FULLSTACK_DEV_CONF = """
server {{
    listen 80 default_server;
    server_name _;
    client_max_body_size 50M;

    # 1. API Reverse Proxy to Backend Service
    location /api/ {{
        proxy_pass http://127.0.0.1:{backend_port};
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
        proxy_connect_timeout 10s;
        proxy_cache_bypass $http_upgrade;
    }}

    location = /api {{
        proxy_pass http://127.0.0.1:{backend_port};
        proxy_http_version 1.1;
        proxy_set_header Host $host;
    }}

    location /docs {{
        proxy_pass http://127.0.0.1:{backend_port};
        proxy_http_version 1.1;
        proxy_set_header Host $host;
    }}

    location /openapi.json {{
        proxy_pass http://127.0.0.1:{backend_port};
        proxy_http_version 1.1;
        proxy_set_header Host $host;
    }}

    location /admin/ {{
        proxy_pass http://127.0.0.1:{backend_port};
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }}

    location = /admin {{
        proxy_pass http://127.0.0.1:{backend_port};
        proxy_http_version 1.1;
        proxy_set_header Host $host;
    }}

    # 2. Frontend Dev Server Proxy
    location / {{
        proxy_pass http://127.0.0.1:{app_port};
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }}
}}
"""

NGINX_STATIC_CONF = """
server {{
    listen 80 default_server;
    server_name _;
    client_max_body_size 50M;
    root {dist_path};
    index index.html;
    location / {{
        try_files $uri $uri/ /index.html;
    }}
    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml;
}}
"""

NGINX_PROXY_CONF = """
server {{
    listen 80 default_server;
    server_name _;
    client_max_body_size 50M;
    location / {{
        proxy_pass http://127.0.0.1:{app_port};
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }}
}}
"""


class PreviewManager:
    """Manages the live preview of any generated application stack dynamically."""

    def __init__(self, workspace_path: str) -> None:
        self._workspace = Path(workspace_path)
        self._nginx_conf_dir = Path("/etc/nginx/conf.d")
        self._app_port = int(os.environ.get("APP_PORT", "3000"))
        self._backend_port = int(os.environ.get("BACKEND_PORT", "8000"))
        self._preview_port = int(os.environ.get("PREVIEW_PORT", "80"))
        self._backend_process: subprocess.Popen[Any] | None = None
        self._frontend_process: subprocess.Popen[Any] | None = None
        self._launcher = DynamicAppLauncher(self._workspace, preview_port=self._preview_port)

    def stop_backend(self, port: int | None = None) -> None:
        """Cleanly kill the running backend server process and release the port."""
        from runtime.process_supervisor import ProcessSupervisor
        target_port = port or self._backend_port
        if self._backend_process and self._backend_process.poll() is None:
            try:
                self._backend_process.terminate()
                self._backend_process.wait(timeout=2)
                print(f"[PreviewManager] Backend process (PID={self._backend_process.pid}) stopped via SIGTERM")
            except Exception:
                try:
                    self._backend_process.kill()
                    print(f"[PreviewManager] Backend process force-killed via SIGKILL")
                except Exception:
                    pass
            self._backend_process = None

        # Terminate any lingering port holders to prevent EADDRINUSE
        ProcessSupervisor.kill_port_holders(target_port)

    def stop_frontend(self, port: int | None = None) -> None:
        """Cleanly kill the running frontend server process and release the port."""
        from runtime.process_supervisor import ProcessSupervisor
        target_port = port or self._app_port
        if self._frontend_process and self._frontend_process.poll() is None:
            try:
                self._frontend_process.terminate()
                self._frontend_process.wait(timeout=2)
                print(f"[PreviewManager] Frontend process (PID={self._frontend_process.pid}) stopped via SIGTERM")
            except Exception:
                try:
                    self._frontend_process.kill()
                    print(f"[PreviewManager] Frontend process force-killed via SIGKILL")
                except Exception:
                    pass
            self._frontend_process = None

        # Terminate any lingering port holders on frontend port (e.g. 3000, 5173)
        ProcessSupervisor.kill_port_holders(target_port)

    def probe_api_health(self, info: PreviewInfo, timeout: float = 3.0) -> tuple[bool, str | None]:
        """Dynamically probe backend API endpoint health if a backend is running.
        
        Returns (True, None) if healthy or no backend.
        Returns (False, error_details) if 500 error or database crash is detected.
        """
        if not info.backend_port:
            return True, None

        import urllib.request
        import urllib.error

        urls_to_test = [
            f"http://127.0.0.1:{info.backend_port}/api/",
            f"http://127.0.0.1:{info.backend_port}/",
            f"http://127.0.0.1:{self._preview_port}/api/",
        ]

        for url in urls_to_test:
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "HealthProbe/1.0"})
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    return True, None
            except urllib.error.HTTPError as he:
                if he.code in (401, 403, 404, 405):
                    continue
                if he.code >= 500:
                    try:
                        body = he.read().decode("utf-8", errors="ignore")[:1000]
                    except Exception:
                        body = str(he)
                    return False, f"Backend returned HTTP {he.code} on {url}: {body}"
            except Exception:
                pass

        return True, None

    def detect_backend_port(self) -> int | None:
        """Detect the backend port dynamically via DynamicAppLauncher."""
        try:
            plan = self._launcher.analyze_workspace()
            if plan.backend:
                return plan.backend.port
        except Exception as exc:
            print(f"[PreviewManager] Dynamic port detection warning: {exc}")
        return None

    def smoke_test_backend(self, timeout: float = 10.0) -> tuple[bool, str | None]:
        """Boot-test the backend (if present) and report liveness."""
        plan = self._launcher.analyze_workspace()
        if not plan.backend:
            return True, None
        info = self._start_backend_service(plan.backend)
        if info.get("backend_error"):
            return False, info["backend_error"]
        return True, None

    def start(self, project_type: str = "auto") -> PreviewInfo:
        """Alias for start_preview for backward compatibility."""
        return self.start_preview(project_type=project_type)

    def start_preview(self, project_type: str = "auto") -> PreviewInfo:
        """Dynamically analyze workspace, launch services, configure Nginx, and serve live preview."""
        # 1. Analyze workspace architecture dynamically
        plan = self._launcher.analyze_workspace()
        print(f"[PreviewManager] Dynamic architecture determined: {plan.architecture}")

        info: PreviewInfo

        # -------------------------------------------------------------
        # Architecture A: Monolith (Django, Flask SSR, Next.js, Streamlit)
        # -------------------------------------------------------------
        if plan.architecture == "monolith" and plan.backend:
            backend_info = self._start_backend_service(plan.backend)
            port = plan.backend.port
            conf = NGINX_MONOLITH_CONF.format(app_port=port)
            self._write_nginx_conf(conf)
            self._reload_nginx()
            url = f"http://localhost:{self._preview_port}"
            print(f"[PreviewManager] Monolith live at {url} (Proxied to {plan.backend.framework} on :{port})")
            info = PreviewInfo(
                url=url,
                port=self._preview_port,
                preview_type="monolith",
                backend_port=port,
                backend_error=backend_info.get("backend_error"),
                backend_entrypoint=backend_info.get("path"),
                backend_cwd=backend_info.get("cwd"),
            )

        # -------------------------------------------------------------
        # Architecture B: Decoupled Fullstack (Frontend SPA + Backend API)
        # -------------------------------------------------------------
        elif plan.architecture == "fullstack_separated" and plan.backend:
            backend_info = self._start_backend_service(plan.backend)
            backend_err = backend_info.get("backend_error")

            if plan.dist_dir:
                self._sanitize_dist_api_urls(plan.dist_dir)
                info = self._start_fullstack_static_preview(plan.dist_dir, plan.backend.port)
            elif plan.frontend:
                info = self._start_fullstack_dev_preview_spec(plan.frontend, plan.backend.port)
            else:
                info = self._start_fullstack_dev_preview(project_type, plan.backend.port)

            info.backend_error = backend_err
            info.backend_entrypoint = backend_info.get("path")
            info.backend_cwd = backend_info.get("cwd")

        # -------------------------------------------------------------
        # Architecture C: Standalone API Only
        # -------------------------------------------------------------
        elif plan.architecture == "api_only" and plan.backend:
            backend_info = self._start_backend_service(plan.backend)
            port = plan.backend.port
            conf = NGINX_MONOLITH_CONF.format(app_port=port)
            self._write_nginx_conf(conf)
            self._reload_nginx()
            url = f"http://localhost:{self._preview_port}"
            print(f"[PreviewManager] API service live at {url} (Proxied to {plan.backend.framework} on :{port})")
            info = PreviewInfo(
                url=url,
                port=self._preview_port,
                preview_type="monolith",
                backend_port=port,
                backend_error=backend_info.get("backend_error"),
                backend_entrypoint=backend_info.get("path"),
                backend_cwd=backend_info.get("cwd"),
            )

        # -------------------------------------------------------------
        # Architecture D: Pure Static Frontend Only
        # -------------------------------------------------------------
        else:
            if plan.dist_dir:
                self._sanitize_dist_api_urls(plan.dist_dir)
                info = self._start_static_preview(plan.dist_dir)
            elif plan.frontend:
                info = self._start_dev_server_spec(plan.frontend)
            else:
                dist = self._find_dist_dir() or self._workspace
                info = self._start_static_preview(dist)

        # Verify Nginx on Port 80 is serving content
        fe_ok, fe_err = self._wait_for_frontend_health(port=self._preview_port)
        if not fe_ok:
            print(f"[PreviewManager] [WARNING] Frontend health check note: {fe_err}")

        return info

    def _start_backend_service(self, spec: ServiceSpec) -> dict[str, Any]:
        """Spawn the detected backend/monolith service with preflight execution & health check."""
        print(f"[PreviewManager] Preparing backend service ({spec.framework})...")

        # 1. Run preflight commands (e.g. Django migrations)
        for preflight in spec.preflight_commands:
            try:
                print(f"[PreviewManager] Running preflight: {' '.join(preflight)} in {spec.cwd}")
                subprocess.run(preflight, cwd=str(spec.cwd), env=spec.env, timeout=60, capture_output=True)
            except Exception as pe:
                print(f"[PreviewManager] Note during preflight: {pe}")

        # 2. Check dependencies (Python pip or Node npm)
        if spec.framework in ("fastapi", "django", "flask", "streamlit"):
            self._ensure_python_dependencies(spec.cwd)
        elif spec.framework in ("express", "nestjs", "nextjs", "nuxt"):
            self._ensure_node_dependencies(spec.cwd)

        # 3. Spawn server process
        cmd = spec.command
        print(f"[PreviewManager] Spawning {spec.framework} server: {' '.join(cmd)} (port={spec.port}) in {spec.cwd}")

        try:
            self._backend_process = subprocess.Popen(
                cmd,
                cwd=str(spec.cwd),
                env=spec.env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            ready, backend_err = self._wait_for_backend_health(spec.port)
            if ready:
                print(f"[PreviewManager] [READY] Backend server ready on port {spec.port}")
                return {
                    "type": spec.framework,
                    "port": spec.port,
                    "path": str(spec.entry_file or spec.cwd),
                    "cwd": str(spec.cwd),
                }

            print(f"[PreviewManager] [ERROR] Backend health check failed: {backend_err}")
            return {
                "type": spec.framework,
                "port": spec.port,
                "path": str(spec.entry_file or spec.cwd),
                "cwd": str(spec.cwd),
                "backend_error": backend_err or f"{spec.framework} did not respond on port {spec.port}",
            }
        except Exception as exc:
            print(f"[PreviewManager] Failed to spawn {spec.framework} backend: {exc}")
            return {
                "type": spec.framework,
                "port": spec.port,
                "path": str(spec.entry_file or spec.cwd),
                "cwd": str(spec.cwd),
                "backend_error": str(exc),
            }

    def _ensure_python_dependencies(self, cwd: Path) -> None:
        """Run pip install if requirements.txt exists."""
        import sys
        req_files = [cwd / "requirements.txt", self._workspace / "requirements.txt", self._workspace / "backend" / "requirements.txt"]
        target_req = None
        for rf in req_files:
            if rf.exists():
                target_req = rf
                break

        if target_req:
            print(f"[PreviewManager] Installing missing Python requirements from {target_req}...")
            try:
                subprocess.run(
                    [sys.executable, "-m", "pip", "install", "-r", str(target_req), "--prefer-binary", "--no-warn-script-location"],
                    cwd=str(cwd),
                    timeout=120,
                    capture_output=True,
                )
            except Exception as exc:
                print(f"[PreviewManager] Note during pip install: {exc}")

    def _ensure_node_dependencies(self, cwd: Path) -> None:
        """Run npm install if node_modules does not exist."""
        pkg_json = cwd / "package.json"
        if not pkg_json.exists() and (self._workspace / "package.json").exists():
            pkg_json = self._workspace / "package.json"
            cwd = self._workspace

        if pkg_json.exists():
            node_modules = cwd / "node_modules"
            bin_dir = node_modules / ".bin"
            if not node_modules.exists() or not bin_dir.exists():
                print(f"[PreviewManager] Installing dependencies in {cwd}...")
                try:
                    subprocess.run(
                        ["npm", "install", "--prefer-offline", "--no-audit"],
                        cwd=str(cwd),
                        timeout=300,
                        capture_output=True,
                    )
                except Exception as exc:
                    print(f"[PreviewManager] Note during npm install: {exc}")

    def _ensure_valid_entrypoint(self, cwd: Path) -> None:
        """Ensure index.html points to an existing entrypoint (main.tsx / main.jsx / index.tsx / App.tsx)."""
        idx = cwd / "index.html"
        if not idx.exists():
            idx = self._workspace / "index.html"
        if not idx.exists():
            return
        try:
            content = idx.read_text(encoding="utf-8", errors="replace")
            src_dir = cwd / "src"
            if not src_dir.exists():
                src_dir = self._workspace / "src"
            if src_dir.exists():
                has_main = any((src_dir / f"main.{ext}").exists() for ext in ("tsx", "jsx", "ts", "js"))
                if has_main and ("/src/App." in content and "/src/main." not in content):
                    for ext in ("tsx", "jsx", "ts", "js"):
                        if (src_dir / f"main.{ext}").exists():
                            content = content.replace("/src/App.tsx", f"/src/main.{ext}").replace("/src/App.jsx", f"/src/main.{ext}")
                            idx.write_text(content, encoding="utf-8")
                            print(f"[PreviewManager] Fixed index.html entrypoint -> /src/main.{ext}")
                            break
        except Exception as e:
            print(f"[PreviewManager] Entrypoint fix note: {e}")

    def _start_fullstack_dev_preview_spec(self, fe_spec: ServiceSpec, backend_port: int) -> PreviewInfo:
        """Start frontend dev server from detected ServiceSpec and proxy through Nginx."""
        self._ensure_node_dependencies(fe_spec.cwd)
        self._ensure_valid_entrypoint(fe_spec.cwd)
        cmd = fe_spec.command
        print(f"[PreviewManager] Starting frontend dev server: {' '.join(cmd)} in {fe_spec.cwd}")
        
        log_file = Path("/tmp/frontend_dev.log")
        log_handle = open(log_file, "w", encoding="utf-8")
        self._frontend_process = subprocess.Popen(
            cmd,
            cwd=str(fe_spec.cwd),
            stdout=log_handle,
            stderr=subprocess.STDOUT,
        )
        time.sleep(3)

        frontend_err = None
        if self._frontend_process.poll() is not None:
            log_handle.flush()
            try:
                frontend_err = log_file.read_text(encoding="utf-8", errors="ignore")[-2000:]
            except Exception:
                frontend_err = f"Frontend server exited with code {self._frontend_process.returncode}"
            print(f"[PreviewManager] [ERROR] Frontend dev server failed: {frontend_err[:300]}")
        else:
            # Probe frontend dev server on its port
            fe_ok, probe_err = self._wait_for_frontend_health(fe_spec.port, timeout=8.0)
            if not fe_ok:
                log_handle.flush()
                try:
                    fe_content = log_file.read_text(encoding="utf-8", errors="ignore")[-2000:]
                    frontend_err = fe_content if fe_content.strip() else probe_err
                except Exception:
                    frontend_err = probe_err

        conf = NGINX_FULLSTACK_DEV_CONF.format(app_port=fe_spec.port, backend_port=backend_port)
        self._write_nginx_conf(conf)
        self._reload_nginx()
        url = f"http://localhost:{self._preview_port}"
        print(f"[PreviewManager] Full-Stack Dev live at {url} (FE: :{fe_spec.port}, BE: :{backend_port})")
        return PreviewInfo(
            url=url,
            port=self._preview_port,
            preview_type="fullstack_dev",
            backend_port=backend_port,
            frontend_error=frontend_err,
            frontend_cwd=str(fe_spec.cwd),
        )

    def _start_dev_server_spec(self, fe_spec: ServiceSpec) -> PreviewInfo:
        """Start standalone frontend dev server from ServiceSpec."""
        self._ensure_node_dependencies(fe_spec.cwd)
        cmd = fe_spec.command
        print(f"[PreviewManager] Starting dev server: {' '.join(cmd)} in {fe_spec.cwd}")
        
        log_file = Path("/tmp/frontend_dev.log")
        log_handle = open(log_file, "w", encoding="utf-8")
        self._frontend_process = subprocess.Popen(
            cmd,
            cwd=str(fe_spec.cwd),
            stdout=log_handle,
            stderr=subprocess.STDOUT,
        )
        time.sleep(3)

        frontend_err = None
        if self._frontend_process.poll() is not None:
            log_handle.flush()
            try:
                frontend_err = log_file.read_text(encoding="utf-8", errors="ignore")[-2000:]
            except Exception:
                frontend_err = f"Frontend server exited with code {self._frontend_process.returncode}"
            print(f"[PreviewManager] [ERROR] Frontend dev server failed: {frontend_err[:300]}")
        else:
            fe_ok, probe_err = self._wait_for_frontend_health(fe_spec.port, timeout=8.0)
            if not fe_ok:
                log_handle.flush()
                try:
                    fe_content = log_file.read_text(encoding="utf-8", errors="ignore")[-2000:]
                    frontend_err = fe_content if fe_content.strip() else probe_err
                except Exception:
                    frontend_err = probe_err

        conf = NGINX_PROXY_CONF.format(app_port=fe_spec.port)
        self._write_nginx_conf(conf)
        self._reload_nginx()
        url = f"http://localhost:{self._preview_port}"
        print(f"[PreviewManager] Dev server preview proxied at {url}")
        return PreviewInfo(
            url=url,
            port=self._preview_port,
            preview_type="dev_server",
            frontend_error=frontend_err,
            frontend_cwd=str(fe_spec.cwd),
        )

    def _start_fullstack_static_preview(self, dist: Path, backend_port: int) -> PreviewInfo:
        conf = NGINX_FULLSTACK_STATIC_CONF.format(dist_path=str(dist), backend_port=backend_port)
        self._write_nginx_conf(conf)
        self._reload_nginx()
        url = f"http://localhost:{self._preview_port}"
        print(f"[PreviewManager] Full-Stack Static Preview live at {url} (Frontend: {dist}, Backend API: :{backend_port})")
        return PreviewInfo(
            url=url,
            port=self._preview_port,
            preview_type="fullstack_static",
            dist_path=str(dist),
            backend_port=backend_port,
        )

    def _start_fullstack_dev_preview(self, project_type: str, backend_port: int) -> PreviewInfo:
        fe_cwd = self._workspace / "frontend" if (self._workspace / "frontend").exists() else self._workspace
        cmd = ["npm", "run", "dev", "--", "--port", str(self._app_port), "--host"]
        print(f"[PreviewManager] Starting dev server: {cmd} in {fe_cwd}")
        self._frontend_process = subprocess.Popen(
            cmd,
            cwd=str(fe_cwd),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(3)

        conf = NGINX_FULLSTACK_DEV_CONF.format(app_port=self._app_port, backend_port=backend_port)
        self._write_nginx_conf(conf)
        self._reload_nginx()
        url = f"http://localhost:{self._preview_port}"
        print(f"[PreviewManager] Full-Stack Dev Preview proxied at {url} (Frontend Dev: :{self._app_port}, Backend: :{backend_port})")
        return PreviewInfo(
            url=url,
            port=self._preview_port,
            preview_type="fullstack_dev",
            backend_port=backend_port,
        )

    def _start_static_preview(self, dist: Path) -> PreviewInfo:
        conf = NGINX_STATIC_CONF.format(dist_path=str(dist))
        self._write_nginx_conf(conf)
        self._reload_nginx()
        url = f"http://localhost:{self._preview_port}"
        print(f"[PreviewManager] Static preview at {url} serving {dist}")
        return PreviewInfo(url=url, port=self._preview_port, preview_type="static", dist_path=str(dist))

    def _start_dev_server_preview(self, project_type: str) -> PreviewInfo:
        cmd = ["npm", "run", "dev", "--", "--port", str(self._app_port), "--host"]
        print(f"[PreviewManager] Starting dev server: {cmd}")
        self._frontend_process = subprocess.Popen(
            cmd,
            cwd=str(self._workspace),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(3)

        conf = NGINX_PROXY_CONF.format(app_port=self._app_port)
        self._write_nginx_conf(conf)
        self._reload_nginx()
        url = f"http://localhost:{self._preview_port}"
        print(f"[PreviewManager] Dev server preview proxied at {url}")
        return PreviewInfo(url=url, port=self._preview_port, preview_type="dev_server")

    def _wait_for_backend_health(
        self, port: int, host: str = "127.0.0.1", timeout: float = 12.0
    ) -> tuple[bool, str | None]:
        """Multi-stage wise health check for backend servers delegating to ProcessSupervisor."""
        from runtime.process_supervisor import ProcessSupervisor
        return ProcessSupervisor.wait_for_backend_liveness(
            self._backend_process, port, host=host, timeout=timeout
        )

    def _wait_for_frontend_health(
        self, port: int = 80, host: str = "127.0.0.1", timeout: float = 8.0
    ) -> tuple[bool, str | None]:
        """Wise health check for Frontend/Nginx serving preview on Port 80 via ProcessSupervisor."""
        from runtime.process_supervisor import ProcessSupervisor
        ok = ProcessSupervisor.wait_for_health(f"http://{host}:{port}/", timeout_seconds=timeout)
        if ok:
            return True, None
        return False, f"Frontend on port {port} did not return HTTP 200 within {timeout}s"

    def _wait_for_port_ready(self, port: int, host: str = "127.0.0.1", timeout: float = 15.0) -> bool:
        """Backward compatibility wrapper delegating to _wait_for_backend_health."""
        ok, _ = self._wait_for_backend_health(port, host=host, timeout=timeout)
        return ok

    def _sanitize_dist_api_urls(self, dist: Path) -> None:
        """Sanitize any hardcoded localhost backend URLs in built JS bundles to relative /api paths."""
        try:
            for js_file in dist.glob("**/*.js"):
                content = js_file.read_text(encoding="utf-8", errors="ignore")
                need_fix = False
                for prefix in (
                    "http://localhost:3001/api",
                    "http://localhost:8000/api",
                    "http://localhost:5000/api",
                    "http://127.0.0.1:3001/api",
                    "http://127.0.0.1:8000/api",
                    "http://127.0.0.1:5000/api",
                ):
                    if prefix in content:
                        content = content.replace(prefix, "/api")
                        need_fix = True
                if need_fix:
                    js_file.write_text(content, encoding="utf-8")
                    print(f"[PreviewManager] Sanitized hardcoded localhost API URLs in {js_file.name} -> /api")
        except Exception as exc:
            print(f"[PreviewManager] Warning during dist sanitization: {exc}")

    def _find_dist_dir(self) -> Path | None:
        for name in ("dist", "build", "out"):
            p = self._workspace / name
            if p.exists() and p.is_dir() and list(p.iterdir()):
                return p
        return None

    def _write_nginx_conf(self, conf: str) -> None:
        conf_file = self._nginx_conf_dir / "project.conf"
        try:
            self._nginx_conf_dir.mkdir(parents=True, exist_ok=True)
            # Remove any default.conf that could conflict with project.conf
            for old in ("default.conf", "00-default.conf"):
                p = self._nginx_conf_dir / old
                if p.exists():
                    try:
                        p.unlink()
                    except Exception:
                        pass
            conf_file.write_text(conf)
            print(f"[PreviewManager] Wrote Nginx config to {conf_file}")
        except OSError as exc:
            print(f"[PreviewManager] WARNING: Could not write Nginx config: {exc}")

    def _reload_nginx(self) -> None:
        try:
            t = subprocess.run(["nginx", "-t"], timeout=10, capture_output=True, text=True)
            if t.returncode != 0:
                print(f"[PreviewManager] Nginx config test failed: {t.stderr.strip()}")
            r = subprocess.run(["nginx", "-s", "reload"], timeout=10, capture_output=True, text=True)
            if r.returncode == 0:
                print("[PreviewManager] Nginx reloaded successfully")
            else:
                print(f"[PreviewManager] Nginx reload returned {r.returncode}: {r.stderr.strip()}. Attempting direct start...")
                start_res = subprocess.run(["nginx"], timeout=10, capture_output=True, text=True)
                if start_res.returncode == 0:
                    print("[PreviewManager] Nginx daemon started successfully")
                else:
                    print(f"[PreviewManager] Nginx start returned {start_res.returncode}: {start_res.stderr.strip()}")
        except Exception as exc:
            print(f"[PreviewManager] WARNING: Could not reload or start Nginx: {exc}")
