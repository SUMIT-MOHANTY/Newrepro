"""Starter workspace scaffold for React + Vite single-page applications.

Seeds new workspaces with Tailwind CSS, Google Material Symbols,
and a minimal design system. All styling uses Tailwind utility classes
directly in JSX — no separate CSS files needed.
"""
from __future__ import annotations

import os

PACKAGE_JSON = """{
  "name": "vibe-app",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "lucide-react": "^0.460.0",
    "react-router-dom": "^6.26.0",
    "recharts": "^2.12.7",
    "date-fns": "^3.6.0",
    "clsx": "^2.1.1"
  },
  "devDependencies": {
    "@types/react": "^18.3.3",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.1",
    "autoprefixer": "^10.4.20",
    "postcss": "^8.4.49",
    "tailwindcss": "^3.4.17",
    "vite": "^5.3.4"
  }
}
"""

VITE_CONFIG_JS = """import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  base: './',
  build: {
    sourcemap: true,  // Enable source maps for runtime error debugging
  },
})
"""

TAILWIND_CONFIG = """/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      fontFamily: {
        sans: ['Plus Jakarta Sans', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
      colors: {
        brand: {
          50: '#f0f9ff',
          100: '#e0f2fe',
          200: '#bae6fd',
          300: '#7dd3fc',
          400: '#38bdf8',
          500: '#0ea5e9',
          600: '#0284c7',
          700: '#0369a1',
          800: '#075985',
          900: '#0c4a6e',
          950: '#082f49',
        },
        surface: {
          50: '#f8fafc',
          100: '#f1f5f9',
          200: '#e2e8f0',
          300: '#cbd5e1',
          400: '#94a3b8',
          500: '#64748b',
          600: '#475569',
          700: '#334155',
          800: '#1e293b',
          900: '#0f172a',
          950: '#020617',
        }
      },
      boxShadow: {
        'glass': '0 8px 32px 0 rgba(0, 0, 0, 0.37)',
        'glass-lg': '0 8px 30px rgba(0, 0, 0, 0.12)',
        'glow': '0 0 20px rgba(14, 165, 233, 0.15)',
        'glow-lg': '0 0 40px rgba(14, 165, 233, 0.2)',
      },
      backdropBlur: {
        'glass': '16px',
      },
      animation: {
        'fade-in': 'fadeIn 0.3s ease-out',
        'slide-up': 'slideUp 0.3s ease-out',
        'slide-down': 'slideDown 0.3s ease-out',
        'scale-in': 'scaleIn 0.2s ease-out',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideUp: {
          '0%': { opacity: '0', transform: 'translateY(10px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        slideDown: {
          '0%': { opacity: '0', transform: 'translateY(-10px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        scaleIn: {
          '0%': { opacity: '0', transform: 'scale(0.95)' },
          '100%': { opacity: '1', transform: 'scale(1)' },
        },
      },
    },
  },
  plugins: [],
}
"""

POSTCSS_CONFIG = """export default {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
}
"""

INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Dsuite Vibe Application</title>
    <!-- Google Modern Fonts -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
    <!-- Google Material Symbols (Icons) -->
    <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@24,400,0,0" />
  </head>
  <body class="bg-slate-50 text-slate-900 font-sans antialiased selection:bg-brand-500 selection:text-white">
    <div id="root"></div>
    <script type="module" src="/src/main.jsx"></script>
  </body>
</html>
"""

MAIN_JSX = """import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import './index.css'

class GlobalErrorBoundary extends React.Component {
  constructor(props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error }
  }

  componentDidCatch(error, errorInfo) {
    console.error('[App Runtime Error]', error, errorInfo)
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{
          padding: '2rem',
          fontFamily: 'system-ui, -apple-system, sans-serif',
          maxWidth: '680px',
          margin: '40px auto',
          background: '#fff1f2',
          border: '1px solid #fecdd3',
          borderRadius: '12px',
          color: '#9f1239',
          boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px' }}>
            <span style={{ fontSize: '20px' }}>⚠️</span>
            <h2 style={{ margin: 0, fontSize: '1.2rem', fontWeight: 600 }}>Application Rendering Error</h2>
          </div>
          <p style={{ margin: '0 0 12px 0', fontSize: '0.9rem', color: '#881337', lineHeight: 1.5 }}>
            {this.state.error?.message || 'An unexpected runtime error occurred while rendering this component.'}
          </p>
          <pre style={{
            background: '#ffe4e6',
            padding: '12px',
            borderRadius: '8px',
            fontSize: '0.8rem',
            overflow: 'auto',
            maxHeight: '220px',
            color: '#be123c',
            border: '1px solid #fda4af'
          }}>
            {this.state.error?.stack}
          </pre>
          <button
            onClick={() => window.location.reload()}
            style={{
              marginTop: '16px',
              padding: '8px 16px',
              background: '#e11d48',
              color: '#ffffff',
              border: 'none',
              borderRadius: '6px',
              cursor: 'pointer',
              fontWeight: 500,
              fontSize: '0.875rem'
            }}
          >
            Reload Preview
          </button>
        </div>
      )
    }
    return this.props.children
  }
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <GlobalErrorBoundary>
      <App />
    </GlobalErrorBoundary>
  </React.StrictMode>,
)
"""

APP_JSX = """import React from 'react'
import { HashRouter as Router, Routes, Route, Link, useLocation } from 'react-router-dom'
import { LayoutDashboard, Sparkles, Activity, Database } from 'lucide-react'
import api from './services/apiClient'

function Navigation() {
  const location = useLocation()
  const navItems = [
    { name: 'Dashboard', path: '/', icon: LayoutDashboard },
    { name: 'Analytics', path: '/analytics', icon: Activity },
    { name: 'Records', path: '/records', icon: Database },
  ]

  return (
    <nav className="bg-white border-b border-slate-200 sticky top-0 z-50 shadow-sm">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex justify-between h-16">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-brand-600 to-indigo-600 flex items-center justify-center text-white shadow-sm">
              <Sparkles className="w-5 h-5" />
            </div>
            <span className="font-bold text-lg text-slate-900 tracking-tight">Application Prototype</span>
          </div>
          <div className="flex items-center space-x-1 sm:space-x-4">
            {navItems.map((item) => {
              const Icon = item.icon
              const active = location.pathname === item.path
              return (
                <Link
                  key={item.path}
                  to={item.path}
                  className={`inline-flex items-center gap-2 px-3 py-2 rounded-xl text-sm font-medium transition-all ${
                    active
                      ? 'bg-brand-50 text-brand-700 font-semibold'
                      : 'text-slate-600 hover:text-slate-900 hover:bg-slate-50'
                  }`}
                >
                  <Icon className="w-4 h-4" />
                  {item.name}
                </Link>
              )
            })}
          </div>
        </div>
      </div>
    </nav>
  )
}

function Home() {
  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
      <div className="bg-white border border-slate-200/80 rounded-2xl p-6 shadow-sm">
        <h2 className="text-2xl font-bold text-slate-900 mb-2">Prototype Ready</h2>
        <p className="text-slate-600">Workspace initialized. AI agent is synthesizing domain models and views.</p>
      </div>
    </div>
  )
}

export default function App() {
  return (
    <Router>
      <div className="min-h-screen bg-slate-50 text-slate-900 flex flex-col">
        <Navigation />
        <main className="flex-1">
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="*" element={<Home />} />
          </Routes>
        </main>
      </div>
    </Router>
  )
}
"""

INDEX_CSS = """@tailwind base;
@tailwind components;
@tailwind utilities;

/* Modern SaaS utility classes and common patterns */
@layer utilities {
  .glass {
    @apply bg-white/80 backdrop-blur-md border border-slate-200/80 shadow-sm;
  }
  .glass-hover {
    @apply hover:bg-slate-50/80 hover:border-slate-300 transition-all duration-200;
  }
  .glass-card {
    @apply bg-white border border-slate-200/80 rounded-2xl p-6 shadow-sm hover:shadow-md transition-all duration-200;
  }
  .gradient-text {
    @apply bg-gradient-to-r from-brand-600 to-indigo-600 bg-clip-text text-transparent;
  }
  .gradient-bg {
    @apply bg-gradient-to-r from-brand-600 to-indigo-600 text-white;
  }
  .btn-primary {
    @apply inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl font-semibold text-sm
           bg-brand-600 text-white shadow-sm
           hover:bg-brand-700 hover:shadow
           active:scale-[0.98] transition-all duration-200;
  }
  .btn-secondary {
    @apply inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl font-semibold text-sm
           bg-white text-slate-700 border border-slate-200 shadow-sm
           hover:bg-slate-50 hover:border-slate-300
           active:scale-[0.98] transition-all duration-200;
  }
  .btn-danger {
    @apply inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl font-semibold text-sm
           bg-rose-50 text-rose-600 border border-rose-200
           hover:bg-rose-100 hover:border-rose-300
           active:scale-[0.98] transition-all duration-200;
  }
  .input-field {
    @apply w-full bg-white border border-slate-200 rounded-xl px-4 py-2.5 text-sm text-slate-900
           placeholder:text-slate-400 outline-none
           focus:border-brand-500 focus:ring-2 focus:ring-brand-500/20
           transition-all duration-200 shadow-sm;
  }
  .badge-emerald {
    @apply inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold
           bg-emerald-50 text-emerald-700 border border-emerald-200/80;
  }
  .badge-blue {
    @apply inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold
           bg-sky-50 text-sky-700 border border-sky-200/80;
  }
  .badge-amber {
    @apply inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold
           bg-amber-50 text-amber-700 border border-amber-200/80;
  }
  .badge-rose {
    @apply inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold
           bg-rose-50 text-rose-700 border border-rose-200/80;
  }
  .badge-purple {
    @apply inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold
           bg-purple-50 text-purple-700 border border-purple-200/80;
  }
}

/* Material Symbols alignment */
.material-symbols-outlined {
  font-size: 20px;
  line-height: 1;
  vertical-align: middle;
  user-select: none;
}

/* Box-sizing reset */
*, *::before, *::after {
  box-sizing: border-box;
}

/* Custom scrollbar — theme neutral */
::-webkit-scrollbar {
  width: 5px;
  height: 5px;
}
::-webkit-scrollbar-track {
  background: transparent;
}
::-webkit-scrollbar-thumb {
  background: rgba(100, 116, 139, 0.25);
  border-radius: 3px;
}
::-webkit-scrollbar-thumb:hover {
  background: rgba(100, 116, 139, 0.45);
}
"""

API_CLIENT_JS = """/**
 * UNIFIED DATA ADAPTER
 * In PROTOTYPE mode: Reads/writes from MockStore (persisted in localStorage with simulated 80ms network latency).
 * In FULLSTACK mode: Makes real HTTP requests to the platform backend (/api/*).
 * React components NEVER know or care whether the backend is live or simulated!
 */

class ApiClient {
  constructor() {
    // Automatically detect mode from environment or project config
    const envMode = typeof import.meta !== 'undefined' && import.meta.env ? import.meta.env.VITE_APP_MODE : 'PROTOTYPE';
    this.mode = envMode === 'FULLSTACK' ? 'FULLSTACK' : 'PROTOTYPE';
    this.baseUrl = '/api';
  }

  setMode(newMode) {
    this.mode = newMode;
  }

  getMode() {
    return this.mode;
  }

  // Generic request dispatcher
  async request(endpoint, options = {}) {
    if (this.mode === 'FULLSTACK') {
      const url = endpoint.startsWith('/api') ? endpoint : `${this.baseUrl}${endpoint.startsWith('/') ? '' : '/'}${endpoint}`;
      const response = await fetch(url, {
        ...options,
        headers: {
          'Content-Type': 'application/json',
          ...(options.headers || {}),
        },
      });
      if (!response.ok) {
        throw new Error(`API error [${response.status}]: ${await response.text()}`);
      }
      return response.json();
    } else {
      // PROTOTYPE MODE: Route to local simulated engine with realistic latency
      return this.mockRouter(endpoint, options);
    }
  }

  async get(endpoint) {
    return this.request(endpoint, { method: 'GET' });
  }

  async post(endpoint, data) {
    return this.request(endpoint, { method: 'POST', body: JSON.stringify(data) });
  }

  async put(endpoint, data) {
    return this.request(endpoint, { method: 'PUT', body: JSON.stringify(data) });
  }

  async delete(endpoint) {
    return this.request(endpoint, { method: 'DELETE' });
  }

  // Local simulated database engine for instant prototypes
  async mockRouter(endpoint, options = {}) {
    await new Promise((res) => setTimeout(res, 80)); // Simulated 80ms network latency
    const method = options.method || 'GET';
    const cleanPath = endpoint.replace(/^\\/api\\//, '').replace(/^\\//, '');
    const parts = cleanPath.split('/');
    const collection = parts[0] || 'records';
    const id = parts[1];
    const storageKey = `vibe_db_${collection}`;

    let table = [];
    try {
      table = JSON.parse(localStorage.getItem(storageKey) || '[]');
    } catch {
      table = [];
    }

    if (method === 'GET') {
      if (id) {
        const item = table.find((x) => String(x.id) === String(id));
        if (!item) throw new Error(`Not found: ${endpoint}`);
        return item;
      }
      return table;
    } else if (method === 'POST') {
      const payload = options.body ? JSON.parse(options.body) : {};
      const newItem = { id: `id_${Date.now()}_${Math.random().toString(36).substr(2, 4)}`, ...payload, createdAt: new Date().toISOString() };
      table.push(newItem);
      localStorage.setItem(storageKey, JSON.stringify(table));
      return newItem;
    } else if (method === 'PUT') {
      const payload = options.body ? JSON.parse(options.body) : {};
      if (!id) throw new Error('PUT requires an ID');
      const idx = table.findIndex((x) => String(x.id) === String(id));
      if (idx === -1) throw new Error(`Not found: ${endpoint}`);
      table[idx] = { ...table[idx], ...payload, updatedAt: new Date().toISOString() };
      localStorage.setItem(storageKey, JSON.stringify(table));
      return table[idx];
    } else if (method === 'DELETE') {
      if (!id) throw new Error('DELETE requires an ID');
      table = table.filter((item) => String(item.id) !== String(id));
      localStorage.setItem(storageKey, JSON.stringify(table));
      return { success: true, id };
    }
    return table;
  }

  // Seed default data if table is empty
  seedIfEmpty(collection, defaultData = []) {
    const storageKey = `vibe_db_${collection.replace(/^\\//, '')}`;
    try {
      const existing = localStorage.getItem(storageKey);
      if (!existing || JSON.parse(existing).length === 0) {
        localStorage.setItem(storageKey, JSON.stringify(defaultData));
      }
    } catch {
      localStorage.setItem(storageKey, JSON.stringify(defaultData));
    }
  }
}

export const api = new ApiClient();
export default api;
"""


def _compute_deps_hash(package_json_path: str) -> str:
    """SHA256 of dependencies/devDependencies in a package.json.

    Must stay byte-compatible with mcp/build_tools.py:_get_package_deps_hash
    so the seal written here satisfies build_tools' install-skip fast path.
    """
    import hashlib
    import json
    try:
        with open(package_json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        deps = {
            "dependencies": data.get("dependencies", {}),
            "devDependencies": data.get("devDependencies", {}),
        }
        return hashlib.sha256(json.dumps(deps, sort_keys=True).encode("utf-8")).hexdigest()
    except Exception:
        return ""


def seed_starter_scaffold(workspace_path: str) -> None:
    """Seed the workspace with starter files and pre-cached node_modules if package.json does not exist."""
    package_json_path = os.path.join(workspace_path, "package.json")
    if os.path.exists(package_json_path):
        return

    os.makedirs(workspace_path, exist_ok=True)
    src_dir = os.path.join(workspace_path, "src")
    os.makedirs(src_dir, exist_ok=True)

    # Write core configuration files
    with open(package_json_path, "w", encoding="utf-8") as f:
        f.write(PACKAGE_JSON)

    with open(os.path.join(workspace_path, "vite.config.js"), "w", encoding="utf-8") as f:
        f.write(VITE_CONFIG_JS)

    with open(os.path.join(workspace_path, "tailwind.config.js"), "w", encoding="utf-8") as f:
        f.write(TAILWIND_CONFIG)

    with open(os.path.join(workspace_path, "postcss.config.js"), "w", encoding="utf-8") as f:
        f.write(POSTCSS_CONFIG)

    with open(os.path.join(workspace_path, "index.html"), "w", encoding="utf-8") as f:
        f.write(INDEX_HTML)

    with open(os.path.join(src_dir, "main.jsx"), "w", encoding="utf-8") as f:
        f.write(MAIN_JSX)

    with open(os.path.join(src_dir, "index.css"), "w", encoding="utf-8") as f:
        f.write(INDEX_CSS)

    # Seed pre-cached node_modules & lockfile if available inside container
    workspace_node_modules = os.path.join(workspace_path, "node_modules")
    template_node_modules = "/template_workspace/node_modules"
    if os.path.exists(template_node_modules) and not os.path.exists(workspace_node_modules):
        deps_sealed = False
        try:
            # Instant symlink (<0.01s) instead of copying 30,000 individual files
            os.symlink(template_node_modules, workspace_node_modules)
            template_lock = "/template_workspace/package-lock.json"
            workspace_lock = os.path.join(workspace_path, "package-lock.json")
            if os.path.exists(template_lock) and not os.path.exists(workspace_lock):
                import shutil
                shutil.copy2(template_lock, workspace_lock)
            print(f"[StarterScaffold] ✅ Instant pre-cached node_modules symlinked to {workspace_path}")
            deps_sealed = True
        except Exception as symlink_exc:
            # Fallback to copy only if symlink creation is not permitted on the mount
            try:
                import shutil
                shutil.copytree(template_node_modules, workspace_node_modules, symlinks=True)
                print(f"[StarterScaffold] Pre-cached node_modules copied to {workspace_path}")
                deps_sealed = True
            except Exception as copy_exc:
                print(f"[StarterScaffold] Note: could not link/copy pre-cached node_modules: {copy_exc}")

        # Write the install-skip seal: node_modules on disk was installed from the
        # template's package.json. Only seal when it matches the workspace's own
        # package.json, so build_tools can skip the first (no-op) npm install.
        # Any later dependency edit changes the hash and re-enables npm install.
        if deps_sealed:
            try:
                ws_hash = _compute_deps_hash(package_json_path)
                tmpl_hash = _compute_deps_hash("/template_workspace/package.json")
                if ws_hash and tmpl_hash and ws_hash == tmpl_hash:
                    with open(os.path.join(workspace_path, ".package_deps_hash"), "w", encoding="utf-8") as hf:
                        hf.write(ws_hash)
                    print(f"[StarterScaffold] 🔒 Dependency seal written ({ws_hash[:8]}) — first npm install will be skipped")
            except Exception as seal_exc:
                print(f"[StarterScaffold] Note: could not write dependency seal: {seal_exc}")

    print(f"[StarterScaffold] Seeded Tailwind CSS workspace scaffold in {workspace_path}")
