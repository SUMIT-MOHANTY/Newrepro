"""PreviewManager — Serves full-stack applications (Frontend + Backend) via Nginx on Port 80.

Architecture & Capabilities:
- Full-Stack Detection: Identifies Node.js/Express or Python/FastAPI backend servers alongside React/Vite.
- Backend Lifecycle: Automatically installs backend dependencies (if needed) and spawns the backend service in background.
- Unified Nginx Reverse Proxy:
  - Port 80 serves the Frontend SPA at `/` (static dist or dev proxy).
  - Reverse proxies all `/api/` traffic directly to the running backend service (port 3001 or 8000).
  - Supports WebSockets, SSE, and long-polling headers.
- Graceful Reload: Dynamically writes Nginx project configuration and reloads without downtime.
"""
from __future__ import annotations

import os
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class PreviewInfo:
    url: str
    port: int
    preview_type: str   # "fullstack_static" | "fullstack_dev" | "static" | "dev_server"
    dist_path: str | None = None
    backend_port: int | None = None
    backend_error: str | None = None  # Error output if backend failed to start
    backend_entrypoint: str | None = None  # Exact path to backend entrypoint
    backend_cwd: str | None = None  # Working directory of backend service


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
    """Manages the live preview of the generated frontend and backend application."""

    def __init__(self, workspace_path: str) -> None:
        self._workspace = Path(workspace_path)
        self._nginx_conf_dir = Path("/etc/nginx/conf.d")
        self._app_port = int(os.environ.get("APP_PORT", "3000"))
        self._backend_port = int(os.environ.get("BACKEND_PORT", "3001"))
        self._preview_port = int(os.environ.get("PREVIEW_PORT", "80"))
        self._backend_process: subprocess.Popen[Any] | None = None
        self._frontend_process: subprocess.Popen[Any] | None = None

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

    def detect_backend_port(self) -> int | None:
        """Detect the backend port without spawning anything (public helper).

        Scans known Node.js backend entrypoints and inspects their source for a
        hardcoded port. Returns the detected port or None if no backend exists.
        """
        node_entrypoints = [
            self._workspace / "backend" / "server.js",
            self._workspace / "backend" / "index.js",
            self._workspace / "backend" / "app.js",
            self._workspace / "backend" / "src" / "server.js",
            self._workspace / "backend" / "src" / "index.js",
            self._workspace / "server.js",
            self._workspace / "server" / "index.js",
            self._workspace / "server" / "server.js",
        ]
        for entry_file in node_entrypoints:
            if entry_file.exists():
                return self._detect_backend_port(entry_file, self._backend_port)
        return None

    def smoke_test_backend(self, timeout: float = 10.0) -> tuple[bool, str | None]:
        """Boot-test the backend (if present) and report liveness.

        Observability-only: intended for build verification so backend crashes
        surface early with their stderr. Never called on the success path of
        frontend-only projects (returns (True, None) immediately).
        """
        info = self._detect_and_start_backend()
        if info is None:
            return True, None  # No backend in this project — nothing to test
        if info.get("backend_error"):
            return False, info["backend_error"]
        return True, None

    def start(self, project_type: str = "react_vite") -> PreviewInfo:
        """Alias for start_preview for backward compatibility."""
        return self.start_preview(project_type=project_type)

    def start_preview(self, project_type: str = "react_vite") -> PreviewInfo:
        """Start backend (if present), configure unified Nginx proxy on Port 80, and serve preview."""
        # 1. Detect and start backend service
        backend_info = self._detect_and_start_backend()
        backend_error = backend_info.get("backend_error") if backend_info else None

        # 2. Check for built static frontend (dist/ or build/)
        dist = self._find_dist_dir()
        if dist:
            self._sanitize_dist_api_urls(dist)

        info: PreviewInfo
        if dist and backend_info:
            info = self._start_fullstack_static_preview(dist, backend_info["port"])
            info.backend_error = backend_error
        elif dist:
            info = self._start_static_preview(dist)
        elif backend_info:
            info = self._start_fullstack_dev_preview(project_type, backend_info["port"])
            info.backend_error = backend_error
        else:
            info = self._start_dev_server_preview(project_type)

        if backend_info:
            info.backend_entrypoint = backend_info.get("path")
            info.backend_cwd = backend_info.get("cwd")

        # 3. Wise Frontend Health Check — verify Nginx on Port 80 is serving content
        fe_ok, fe_err = self._wait_for_frontend_health(port=self._preview_port)
        if not fe_ok:
            print(f"[PreviewManager] ⚠️ Frontend health check warning: {fe_err}")

        return info

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

    def _detect_backend_port(self, entry_file: Path, default_port: int) -> int:
        """Inspect entrypoint code to detect if a specific port was hardcoded (e.g. 5000, 3001, 8000, 8080)."""
        try:
            code = entry_file.read_text(encoding="utf-8", errors="ignore")
            patterns = [
                r'(?:const|let|var)\s+PORT\s*=\s*(?:process\.env\.PORT\s*\|\|\s*)?(\d{4,5})',
                r'\.listen\(\s*(?:PORT\s*\|\|\s*)?(\d{4,5})',
                r'PORT\s*=\s*int\(os\.environ\.get\(["\']PORT["\'],\s*(\d{4,5})\)\)',
                r'PORT\s*=\s*(\d{4,5})',
                r'port\s*=\s*(\d{4,5})',
            ]
            for pat in patterns:
                m = re.search(pat, code)
                if m:
                    p = int(m.group(1))
                    if 1024 <= p <= 65535 and p != 80:
                        return p
        except Exception:
            pass
        return default_port

    def _detect_and_start_backend(self) -> dict[str, Any] | None:
        """Detect and spawn background backend server process with dynamic port detection."""
        # Check Node.js backend locations
        node_entrypoints = [
            (self._workspace / "backend" / "server.js", self._workspace / "backend"),
            (self._workspace / "backend" / "index.js", self._workspace / "backend"),
            (self._workspace / "backend" / "app.js", self._workspace / "backend"),
            (self._workspace / "backend" / "src" / "server.js", self._workspace / "backend"),
            (self._workspace / "backend" / "src" / "index.js", self._workspace / "backend"),
            (self._workspace / "server.js", self._workspace),
            (self._workspace / "server" / "index.js", self._workspace / "server"),
            (self._workspace / "server" / "server.js", self._workspace / "server"),
        ]

        for entry_file, cwd in node_entrypoints:
            if entry_file.exists():
                print(f"[PreviewManager] Found Node.js backend at {entry_file}")
                # Ensure backend dependencies are installed
                pkg_json = cwd / "package.json"
                target_dir = cwd
                if not pkg_json.exists() and (self._workspace / "package.json").exists():
                    pkg_json = self._workspace / "package.json"
                    target_dir = self._workspace

                if pkg_json.exists():
                    node_modules = target_dir / "node_modules"
                    needs_install = False
                    if not node_modules.exists():
                        needs_install = True
                    else:
                        try:
                            pkg_data = json.loads(pkg_json.read_text(encoding="utf-8"))
                            all_deps = list(pkg_data.get("dependencies", {}).keys()) + list(pkg_data.get("devDependencies", {}).keys())
                            for dep in all_deps:
                                if dep.startswith("@"):
                                    parts = dep.split("/")
                                    if len(parts) == 2 and not (node_modules / parts[0] / parts[1]).exists():
                                        needs_install = True
                                        break
                                elif not (node_modules / dep).exists():
                                    needs_install = True
                                    break
                        except Exception:
                            pass

                    if needs_install:
                        print(f"[PreviewManager] Installing missing backend dependencies in {target_dir}...")
                        try:
                            subprocess.run(["npm", "install", "--prefer-offline", "--no-audit"], cwd=str(target_dir), timeout=60, capture_output=True)
                        except Exception as exc:
                            print(f"[PreviewManager] Warning during npm install: {exc}")

                node_port = self._detect_backend_port(entry_file, self._backend_port)
                env = os.environ.copy()
                env["PORT"] = str(node_port)
                rel_path = entry_file.name if cwd == entry_file.parent else str(entry_file.relative_to(cwd))
                cmd = ["node", rel_path]
                print(f"[PreviewManager] Spawning backend server: {' '.join(cmd)} (port={node_port}) in {cwd}")

                try:
                    # Capture stderr to detect crash reasons (not DEVNULL)
                    self._backend_process = subprocess.Popen(
                        cmd,
                        cwd=str(cwd),
                        env=env,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.PIPE,
                    )
                    ready, backend_err = self._wait_for_backend_health(node_port)
                    if ready:
                        print(f"[PreviewManager] ✅ Backend server ready and healthy on port {node_port}")
                        return {"type": "node", "port": node_port, "path": str(entry_file), "cwd": str(cwd)}

                    print(f"[PreviewManager] ❌ Backend health check failed: {backend_err}")
                    return {"type": "node", "port": node_port, "path": str(entry_file), "cwd": str(cwd), "backend_error": backend_err or "Backend did not start"}
                except Exception as exc:
                    print(f"[PreviewManager] Failed to spawn Node backend: {exc}")
                    return {"type": "node", "port": node_port, "path": str(entry_file), "cwd": str(cwd), "backend_error": str(exc)}

        # Check Python FastAPI / Flask backend locations
        py_entrypoints = [
            (self._workspace / "backend" / "main.py", self._workspace / "backend"),
            (self._workspace / "backend" / "app.py", self._workspace / "backend"),
            (self._workspace / "main.py", self._workspace),
            (self._workspace / "app.py", self._workspace),
        ]

        for entry_file, cwd in py_entrypoints:
            if entry_file.exists():
                print(f"[PreviewManager] Found Python backend at {entry_file}")
                py_port = self._detect_backend_port(entry_file, 8000)
                env = os.environ.copy()
                env["PORT"] = str(py_port)
                mod_name = entry_file.stem
                cmd = ["uvicorn", f"{mod_name}:app", "--host", "127.0.0.1", "--port", str(py_port)]
                print(f"[PreviewManager] Spawning Python backend: {' '.join(cmd)} (port={py_port})")
                try:
                    self._backend_process = subprocess.Popen(
                        cmd,
                        cwd=str(cwd),
                        env=env,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.PIPE,
                    )
                    ready, backend_err = self._wait_for_backend_health(py_port)
                    if ready:
                        print(f"[PreviewManager] ✅ Python backend ready and healthy on port {py_port}")
                        return {"type": "python", "port": py_port, "path": str(entry_file), "cwd": str(cwd)}
                    return {"type": "python", "port": py_port, "path": str(entry_file), "cwd": str(cwd), "backend_error": backend_err}
                except Exception:
                    # Fallback to python server.py
                    try:
                        self._backend_process = subprocess.Popen(
                            ["python", entry_file.name],
                            cwd=str(cwd),
                            env=env,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.PIPE,
                        )
                        ready, backend_err = self._wait_for_backend_health(py_port, timeout=8.0)
                        if ready:
                            return {"type": "python", "port": py_port, "path": str(entry_file), "cwd": str(cwd)}
                        return {"type": "python", "port": py_port, "path": str(entry_file), "cwd": str(cwd), "backend_error": backend_err}
                    except Exception as exc:
                        print(f"[PreviewManager] Failed to spawn Python backend: {exc}")

        return None

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
        cmd = ["npm", "run", "dev", "--", "--port", str(self._app_port), "--host"]
        print(f"[PreviewManager] Starting dev server: {cmd}")
        self._frontend_process = subprocess.Popen(
            cmd,
            cwd=str(self._workspace),
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
                # Reload failed (e.g. invalid PID or nginx not yet running) -> start nginx directly
                print(f"[PreviewManager] Nginx reload returned {r.returncode}: {r.stderr.strip()}. Attempting direct Nginx start...")
                start_res = subprocess.run(["nginx"], timeout=10, capture_output=True, text=True)
                if start_res.returncode == 0:
                    print("[PreviewManager] Nginx daemon started successfully")
                else:
                    print(f"[PreviewManager] Nginx start returned {start_res.returncode}: {start_res.stderr.strip()}")
        except Exception as exc:
            print(f"[PreviewManager] WARNING: Could not reload or start Nginx: {exc}")
