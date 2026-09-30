"""Starter Scaffold Service — Greenfield Project Bootstrapping.

Detects greenfield (empty) project workspaces and seeds a clean, production-ready
Vite + React + Tailwind CSS + FastAPI starter scaffold before developer agents begin tasks.
Mirrors the Vibecoding Lite greenfield initialization pattern.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def is_greenfield_workspace(workspace_path: str) -> bool:
    """Return True if workspace has no source code or manifest files."""
    if not os.path.exists(workspace_path):
        return True

    ignore_entries = {
        ".git", ".agent_signals", ".agent_history", ".agent_initialized",
        ".cache", "__pycache__", ".DS_Store", "Thumbs.db"
    }

    try:
        entries = [e for e in os.listdir(workspace_path) if e not in ignore_entries]
        if not entries:
            return True

        # Check for core project manifests
        has_frontend = any(
            os.path.exists(os.path.join(workspace_path, f))
            for f in ("package.json", "vite.config.js", "vite.config.ts", "index.html")
        )
        has_backend = any(
            os.path.exists(os.path.join(workspace_path, f))
            for f in ("main.py", "requirements.txt", "pyproject.toml", "server.js", "backend/main.py")
        )
        has_src = os.path.isdir(os.path.join(workspace_path, "src"))

        return not (has_frontend or has_backend or has_src)
    except Exception as e:
        logger.warning(f"[StarterScaffold] Error checking greenfield status: {e}")
        return False


def seed_starter_scaffold(workspace_path: str, project_name: str = "DSuite App") -> Dict[str, Any]:
    """Generate production-grade Vite + React 18 + Tailwind + FastAPI starter scaffold."""
    os.makedirs(workspace_path, exist_ok=True)
    created_files: List[str] = []

    clean_name = "".join(c if c.isalnum() or c in "-_" else "-" for c in project_name.lower()).strip("-") or "dsuite-app"

    # 1. package.json
    pkg_json_path = os.path.join(workspace_path, "package.json")
    if not os.path.exists(pkg_json_path):
        pkg_content = f"""{{
  "name": "{clean_name}",
  "private": true,
  "version": "1.0.0",
  "type": "module",
  "scripts": {{
    "dev": "vite --host 0.0.0.0 --port 3000",
    "build": "vite build",
    "preview": "vite preview --port 3000",
    "lint": "eslint src --ext js,jsx --report-unused-disable-directives --max-warnings 0"
  }},
  "dependencies": {{
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-router-dom": "^6.23.0",
    "lucide-react": "^0.378.0",
    "axios": "^1.6.8"
  }},
  "devDependencies": {{
    "@vitejs/plugin-react": "^4.2.1",
    "vite": "^5.2.0",
    "tailwindcss": "^3.4.3",
    "postcss": "^8.4.38",
    "autoprefixer": "^10.4.19"
  }}
}}
"""
        with open(pkg_json_path, "w", encoding="utf-8") as f:
            f.write(pkg_content)
        created_files.append("package.json")

    # 2. vite.config.js
    vite_config_path = os.path.join(workspace_path, "vite.config.js")
    if not os.path.exists(vite_config_path):
        vite_content = """import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 3000,
    strictPort: true,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        secure: false,
      }
    }
  },
  preview: {
    host: '0.0.0.0',
    port: 3000
  }
});
"""
        with open(vite_config_path, "w", encoding="utf-8") as f:
            f.write(vite_content)
        created_files.append("vite.config.js")

    # 3. tailwind.config.js
    tailwind_config_path = os.path.join(workspace_path, "tailwind.config.js")
    if not os.path.exists(tailwind_config_path):
        tailwind_content = """/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        brand: {
          50: '#eef2ff',
          100: '#e0e7ff',
          500: '#6366f1',
          600: '#4f46e5',
          700: '#4338ca',
        }
      }
    },
  },
  plugins: [],
};
"""
        with open(tailwind_config_path, "w", encoding="utf-8") as f:
            f.write(tailwind_content)
        created_files.append("tailwind.config.js")

    # 4. postcss.config.js
    postcss_path = os.path.join(workspace_path, "postcss.config.js")
    if not os.path.exists(postcss_path):
        postcss_content = """export default {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
};
"""
        with open(postcss_path, "w", encoding="utf-8") as f:
            f.write(postcss_content)
        created_files.append("postcss.config.js")

    # 5. index.html
    html_path = os.path.join(workspace_path, "index.html")
    if not os.path.exists(html_path):
        html_content = f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <link rel="icon" type="image/svg+xml" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='%236366f1'><path d='M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5'/></svg>" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>{project_name}</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
  </head>
  <body class="bg-slate-900 text-slate-100 font-['Inter',sans-serif] antialiased selection:bg-indigo-500 selection:text-white">
    <div id="root"></div>
    <script type="module" src="/src/main.jsx"></script>
  </body>
</html>
"""
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        created_files.append("index.html")

    # Source directory structure
    src_dir = os.path.join(workspace_path, "src")
    components_dir = os.path.join(src_dir, "components")
    pages_dir = os.path.join(src_dir, "pages")
    os.makedirs(components_dir, exist_ok=True)
    os.makedirs(pages_dir, exist_ok=True)

    # 6. src/main.jsx
    main_jsx_path = os.path.join(src_dir, "main.jsx")
    if not os.path.exists(main_jsx_path):
        main_jsx_content = """import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App.jsx';
import './index.css';

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
"""
        with open(main_jsx_path, "w", encoding="utf-8") as f:
            f.write(main_jsx_content)
        created_files.append("src/main.jsx")

    # 7. src/index.css
    index_css_path = os.path.join(src_dir, "index.css")
    if not os.path.exists(index_css_path):
        index_css_content = """@tailwind base;
@tailwind components;
@tailwind utilities;

:root {
  color-scheme: dark;
}

body {
  margin: 0;
  min-height: 100vh;
}
"""
        with open(index_css_path, "w", encoding="utf-8") as f:
            f.write(index_css_content)
        created_files.append("src/index.css")

    # 8. src/App.jsx
    app_jsx_path = os.path.join(src_dir, "App.jsx")
    if not os.path.exists(app_jsx_path):
        app_jsx_content = f"""import React, {{ useState, useEffect }} from 'react';
import {{ Layout, Code2, Server, CheckCircle2, ArrowRight, ShieldCheck, Terminal, Layers }} from 'lucide-react';
import Header from './components/Header.jsx';
import Dashboard from './components/Dashboard.jsx';

export default function App() {{
  const [backendHealth, setBackendHealth] = useState(null);

  useEffect(() => {{
    fetch('/api/health')
      .then((res) => res.json())
      .then((data) => setBackendHealth(data))
      .catch(() => setBackendHealth({{ status: 'standby', message: 'Backend service connecting...' }}));
  }}, []);

  return (
    <div className="min-h-screen bg-[#0d1117] text-slate-100 flex flex-col">
      <Header projectName="{project_name}" backendHealth={{backendHealth}} />

      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8 flex flex-col gap-8">
        <Dashboard projectName="{project_name}" />
      </main>

      <footer className="border-t border-slate-800/80 bg-slate-950/40 py-6 text-center text-xs text-slate-500">
        <p>Built with D-Suite Autonomous Multi-Agent Orchestration • Vibecoding Architecture</p>
      </footer>
    </div>
  );
}}
"""
        with open(app_jsx_path, "w", encoding="utf-8") as f:
            f.write(app_jsx_content)
        created_files.append("src/App.jsx")

    # 9. src/components/Header.jsx
    header_path = os.path.join(components_dir, "Header.jsx")
    if not os.path.exists(header_path):
        header_content = """import React from 'react';
import { Layers, Activity, CheckCircle, Clock } from 'lucide-react';

export default function Header({ projectName, backendHealth }) {
  const isHealthy = backendHealth?.status === 'ok';

  return (
    <header className="sticky top-0 z-40 w-full backdrop-blur-md bg-slate-950/80 border-b border-slate-800/80 px-6 py-4">
      <div className="max-w-7xl mx-auto flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-indigo-600 to-violet-500 flex items-center justify-center text-white shadow-md shadow-indigo-500/20">
            <Layers className="w-5 h-5" />
          </div>
          <div>
            <h1 className="text-base font-bold tracking-tight text-white">{projectName}</h1>
            <p className="text-[11px] text-slate-400 font-mono">D-Suite Autonomous Scaffold v1.0</p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-slate-900 border border-slate-800 text-xs">
            <span className={`w-2 h-2 rounded-full ${isHealthy ? 'bg-emerald-400 animate-pulse' : 'bg-amber-400'}`} />
            <span className="text-slate-300 font-medium">API: {backendHealth?.status || 'Connecting'}</span>
          </div>
        </div>
      </div>
    </header>
  );
}
"""
        with open(header_path, "w", encoding="utf-8") as f:
            f.write(header_content)
        created_files.append("src/components/Header.jsx")

    # 10. src/components/Dashboard.jsx
    dashboard_path = os.path.join(components_dir, "Dashboard.jsx")
    if not os.path.exists(dashboard_path):
        dashboard_content = f"""import React from 'react';
import {{ Code2, Server, CheckCircle2, ShieldCheck, Terminal, Sparkles }} from 'lucide-react';

export default function Dashboard({{ projectName }}) {{
  return (
    <div className="space-y-6">
      {{/* Hero Banner */}}
      <div className="relative overflow-hidden rounded-2xl border border-indigo-500/20 bg-gradient-to-br from-indigo-950/40 via-slate-900/60 to-purple-950/30 p-8 shadow-2xl">
        <div className="relative z-10 max-w-2xl space-y-3">
          <div className="inline-flex items-center gap-2 px-2.5 py-1 rounded-full bg-indigo-500/10 border border-indigo-500/30 text-indigo-300 text-xs font-medium">
            <Sparkles className="w-3.5 h-3.5 text-indigo-400" />
            <span>Master Agent Seeded Scaffold</span>
          </div>
          <h2 className="text-2xl sm:text-3xl font-extrabold text-white tracking-tight">
            {{projectName}} Workspace
          </h2>
          <p className="text-sm text-slate-300 leading-relaxed">
            Starter architecture generated and validated. Autonomous specialized agents (Frontend, Backend, and QA) are equipped to build application features phase-by-phase.
          </p>
        </div>
      </div>

      {{/* Architecture Tiles */}}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="p-5 rounded-xl border border-slate-800 bg-slate-900/50 space-y-3">
          <div className="w-10 h-10 rounded-lg bg-sky-500/10 border border-sky-500/20 text-sky-400 flex items-center justify-center">
            <Code2 className="w-5 h-5" />
          </div>
          <h3 className="text-sm font-semibold text-white">Frontend Stack</h3>
          <p className="text-xs text-slate-400">Vite 5, React 18, Tailwind CSS, Lucide icons, React Router ready for UI components.</p>
        </div>

        <div className="p-5 rounded-xl border border-slate-800 bg-slate-900/50 space-y-3">
          <div className="w-10 h-10 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 flex items-center justify-center">
            <Server className="w-5 h-5" />
          </div>
          <h3 className="text-sm font-semibold text-white">Backend APIs</h3>
          <p className="text-xs text-slate-400">FastAPI backend runtime on port 8000 with CORS middleware and schema validation.</p>
        </div>

        <div className="p-5 rounded-xl border border-slate-800 bg-slate-900/50 space-y-3">
          <div className="w-10 h-10 rounded-lg bg-amber-500/10 border border-amber-500/20 text-amber-400 flex items-center justify-center">
            <ShieldCheck className="w-5 h-5" />
          </div>
          <h3 className="text-sm font-semibold text-white">Zero-Error Gate</h3>
          <p className="text-xs text-slate-400">Continuous ESLint verification, syntax tests, and unit test validations before signoff.</p>
        </div>
      </div>
    </div>
  );
}}
"""
        with open(dashboard_path, "w", encoding="utf-8") as f:
            f.write(dashboard_content)
        created_files.append("src/components/Dashboard.jsx")

    # 11. Backend API structure (main.py & requirements.txt)
    backend_dir = os.path.join(workspace_path, "backend")
    os.makedirs(backend_dir, exist_ok=True)

    backend_main_path = os.path.join(backend_dir, "main.py")
    if not os.path.exists(backend_main_path):
        backend_main_content = f"""from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timezone

app = FastAPI(title="{project_name} API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/health")
def health_check():
    return {{
        "status": "ok",
        "app": "{project_name}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ready": True
    }}

@app.get("/api/v1/info")
def get_info():
    return {{
        "project": "{project_name}",
        "engine": "FastAPI + Vite React",
        "version": "1.0.0"
    }}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
"""
        with open(backend_main_path, "w", encoding="utf-8") as f:
            f.write(backend_main_content)
        created_files.append("backend/main.py")

    req_path = os.path.join(backend_dir, "requirements.txt")
    if not os.path.exists(req_path):
        req_content = """fastapi>=0.110.0
uvicorn[standard]>=0.28.0
pydantic>=2.6.0
python-multipart>=0.0.9
requests>=2.31.0
"""
        with open(req_path, "w", encoding="utf-8") as f:
            f.write(req_content)
        created_files.append("backend/requirements.txt")

    # 12. Nginx configuration for container reverse proxy on port 80
    nginx_conf_path = os.path.join(workspace_path, "nginx.conf")
    if not os.path.exists(nginx_conf_path):
        nginx_content = """events { worker_connections 1024; }

http {
    include /etc/nginx/mime.types;
    default_type application/octet-stream;
    sendfile on;

    server {
        listen 80;
        server_name localhost;

        location /api {
            proxy_pass http://127.0.0.1:8000;
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection 'upgrade';
            proxy_set_header Host $host;
            proxy_cache_bypass $http_upgrade;
        }

        location / {
            proxy_pass http://127.0.0.1:3000;
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection 'upgrade';
            proxy_set_header Host $host;
            proxy_cache_bypass $http_upgrade;
        }
    }
}
"""
        with open(nginx_conf_path, "w", encoding="utf-8") as f:
            f.write(nginx_content)
        created_files.append("nginx.conf")

    # 13. .gitignore
    gitignore_path = os.path.join(workspace_path, ".gitignore")
    if not os.path.exists(gitignore_path):
        gitignore_content = """node_modules
dist
dist-ssr
*.local
.env
.cache
__pycache__
*.pyc
.pytest_cache
venv
.venv
.agent_signals
"""
        with open(gitignore_path, "w", encoding="utf-8") as f:
            f.write(gitignore_content)
        created_files.append(".gitignore")

    # Marker to indicate workspace is initialized
    marker_path = os.path.join(workspace_path, ".agent_initialized")
    with open(marker_path, "w", encoding="utf-8") as f:
        f.write(f'{{"seeded_at": "{os.times()}", "project": "{project_name}"}}')

    logger.info(f"[StarterScaffold] Successfully seeded {len(created_files)} scaffold files into {workspace_path}")
    return {
        "status": "seeded",
        "workspace_path": workspace_path,
        "files_created": created_files,
        "total_files": len(created_files)
    }
