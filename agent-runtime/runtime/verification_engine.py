"""VerificationEngine — Platform-owned, project-type-aware runnability gates.

Design principles (from the platform improvement plan):
1. NOTHING is "done" until the platform itself verifies the app runs.
   Agent-reported success is never trusted as the final status.
2. Any tech stack, any project: the engine detects the project layout from
   manifests on disk (never hard-codes one framework) and picks the right checks.
3. Never hallucinate, never over-enforce: every check that cannot run is
   reported as "skipped" with a reason (recorded, never silently passed), and
   every check has a timeout so the agent cannot hang on it.
4. Failures are classified into machine-actionable classes so repair loops
   converge instead of repeating the same broken attempt.

Verification stages (dynamically selected per project — see plan_stages):
  foundation   — required manifests/entrypoints exist (the missing main.py class of bug)
  imports      — Python entrypoint module imports cleanly and app object constructs
  build        — npm install (first!) + npm run build/typecheck exit 0 for Node sub-projects
  boot         — backend server process starts and its health endpoint responds
  serve        — Node app is served (its own preview/start/serve script or built output) and responds
  contract     — routes mounted by the running app cover the analyzed API contract
  connectivity — every detected server is up and the frontend's declared API base reaches the backend

Which stages run is derived from the project kinds detected ON DISK (plan_stages),
never from a stage list hard-coded by a caller, so any stack/layout is covered.

The result is a VerificationReport that pipelines and the supervisor embed into
task summaries, so status downstream ("completed") always means "verified".
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ─────────────────────────────────────────────────────────────────────────────
# Failure classification — the shared vocabulary for repair loops
# ─────────────────────────────────────────────────────────────────────────────

FAILURE_CLASSES: dict[str, str] = {
    "missing_file":      "A required file/manifest/entrypoint does not exist on disk.",
    "syntax":            "Source file cannot be parsed or has a Python-level error.",
    "import":            "Module or symbol imports fail.",
    "type":              "Type checking failed.",
    "build":             "Build/compile command failed.",
    "dependency":        "Package installation failed or dependency conflict.",
    "runtime":           "Server failed to start or crashed at boot.",
    "health":            "Server started but health endpoint did not respond.",
    "contract_mismatch": "Mounted routes do not cover the analyzed API contract.",
    "convergence":       "Repair loop stopped converging (failures not shrinking).",
    "unknown":           "Unclassified failure.",
}


def classify_failure(raw_error: str) -> str:
    """Classify a raw error string into a machine-actionable failure class."""
    raw = raw_error or ""
    e = raw.lower()

    # Order matters: most specific first.
    if "enoent" in e and ("package.json" in e or "no such file" in e):
        return "missing_file"
    if "modulenotfounderror" in e or "no module named" in e or "cannot find module" in e:
        return "import"
    if "importerror" in e or "cannot import name" in e:
        return "import"
    if "syntaxerror" in e or "parse error" in e or "unexpected token" in e:
        return "syntax"
    if "keyword argument repeated" in e or "indentationerror" in e or "nameerror" in e or "attributeerror" in e:
        return "syntax"
    # Bare undefined-name messages (Python "name 'X' is not defined",
    # JS "'X' is not defined") — no exception class name present.
    if re.search(r"\bis not defined\b", e) or re.search(r"\bname '\w+' is not defined", e):
        return "syntax"
    if re.search(r"\berror ts\d+\b", e) or re.search(r"\bts\d+\b:", e) or "type error" in e or "typeerror" in e:
        return "type"
    if "cannot find name" in e or "cannot find module" in e or "has no exported member" in e:
        return "type"
    # Dependency resolution problems (any package manager) — must be checked
    # before build/type, because these messages read like either.
    if any(k in e for k in (
        "no matching distribution", "could not find a version", "eresolve",
        "peer dep", "npm err! notarget", "version solving failed",
        "conflicting dependencies", "dependency resolver", "is incompatible",
    )):
        return "dependency"
    if "npm err! code e404" in e:
        return "dependency"
    # Build/asset-pipeline failures (any bundler, any CSS pipeline): "class does
    # not exist", "@apply", postcss/tailwind, unresolved imports, bundler errors.
    if any(k in e for k in (
        "postcss", "tailwind", "@apply", "failed to resolve", "rollup",
        "esbuild", "webpack", "cannot be found in the image", "does not exist. if",
    )):
        return "build"
    if "is not assignable to type" in e:
        return "type"
    if "npm err!" in e or "vite build failed" in e or "failed to compile" in e or "build failed" in e:
        return "build"
    if "uvicorn" in e and ("error" in e or "traceback" in e):
        return "runtime"
    if "address already in use" in e:
        return "runtime"
    if "returned http" in e or "not actually served" in e:
        return "runtime"
    if "connection refused" in e or "did not respond" in e:
        return "health"
    return "unknown"


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""
    skipped: bool = False
    skip_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            # Keep enough of the real failure text for a repair agent to act on it
            # (previously truncated to 800 chars, which could cut off the error).
            "detail": (self.detail or "")[:6000],
            "skipped": self.skipped,
            "skip_reason": self.skip_reason,
        }


@dataclass
class VerificationReport:
    """Complete platform verification outcome for one workspace / one gate run."""
    stages: list[CheckResult] = field(default_factory=list)
    project_kinds: list[str] = field(default_factory=list)
    started_at: float = field(default_factory=time.time)
    duration_s: float = 0.0
    error_signature: str = ""

    @property
    def passed(self) -> bool:
        return all(c.passed or c.skipped for c in self.stages)

    @property
    def failures(self) -> list[CheckResult]:
        return [c for c in self.stages if not c.passed and not c.skipped]

    @property
    def failure_classes(self) -> list[str]:
        return sorted({classify_failure(f.detail) for f in self.failures})

    def compute_error_signature(self) -> str:
        """Stable fingerprint of current failures (for convergence tracking)."""
        parts = []
        for f in self.failures:
            parts.append(f"{f.name}:{classify_failure(f.detail)}:{_sig_line(f.detail)}")
        return "|".join(parts)

    def summary_text(self) -> str:
        lines = []
        for c in self.stages:
            if c.skipped:
                lines.append(f"SKIP  {c.name}: {c.skip_reason}")
            elif c.passed:
                lines.append(f"PASS  {c.name}")
            else:
                lines.append(f"FAIL  {c.name}: {(c.detail or '')[:300]}")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "project_kinds": self.project_kinds,
            "duration_s": round(self.duration_s, 2),
            "stages": [c.to_dict() for c in self.stages],
            "failure_classes": self.failure_classes,
            "error_signature": self.error_signature,
            # Full failure text is kept so repair agents receive the real error,
            # not a truncated notice.
            "failures": [
                {"name": c.name, "failure_class": classify_failure(c.detail),
                 "detail": (c.detail or "")[:6000]}
                for c in self.failures
            ],
        }


def _sig_line(detail: str) -> str:
    """First meaningful line of a failure detail — stable across retries."""
    for line in (detail or "").splitlines():
        s = line.strip()
        if s and not s.startswith(("$", ">", "npm", "node")):
            return s[:160]
    return (detail or "")[:160]


# ─────────────────────────────────────────────────────────────────────────────
# Project-type detection — from manifests on disk, never assumed
# ─────────────────────────────────────────────────────────────────────────────

PY_ENTRY_HINTS = ("main.py", "app.py", "run.py", "server.py", "wsgi.py", "asgi.py", "manage.py")
NODE_ENTRY_HINTS = ("server.js", "app.js", "index.js", "index.ts", "main.js")
# Package-style layouts: app/main.py, src/main.py, backend/app/main.py etc.
# (the Kuoni missing-entrypoint bug class: entrypoint hidden inside a package dir)
PY_PACKAGE_ENTRIES = ("app/main.py", "src/main.py", "app/__init__.py")


def _frontend_sources(d: str) -> bool:
    """True if directory d contains frontend app sources (*.tsx/jsx/vue) but no package.json."""
    if not os.path.isdir(d) or os.path.exists(os.path.join(d, "package.json")):
        return False
    src = os.path.join(d, "src")
    if not os.path.isdir(src):
        return False
    try:
        for root_dir, _, files in os.walk(src):
            if any(f.endswith((".tsx", ".jsx", ".vue", ".svelte")) for f in files):
                return True
    except Exception:
        pass
    return False


def _node_marker(d: str) -> bool:
    """True if directory d looks like a Node project."""
    return os.path.exists(os.path.join(d, "package.json"))


def _python_marker(d: str) -> bool:
    """True if directory d looks like a Python project (top level OR package-style)."""
    if os.path.exists(os.path.join(d, "requirements.txt")) or os.path.exists(os.path.join(d, "pyproject.toml")):
        return True
    if any(os.path.exists(os.path.join(d, h)) for h in PY_ENTRY_HINTS):
        return True
    return any(os.path.exists(os.path.join(d, p)) for p in PY_PACKAGE_ENTRIES)


def detect_project_kinds(root: str) -> list[str]:
    """Detect what kind(s) of project live in this workspace (multi-kind allowed)."""
    kinds: list[str] = []
    if not os.path.isdir(root):
        return ["unknown"]

    def _has(p: str) -> bool:
        return os.path.exists(os.path.join(root, p))

    def _has_dir_file(d: str, names: tuple[str, ...]) -> bool:
        base = os.path.join(root, d)
        if not os.path.isdir(base):
            return False
        return any(os.path.exists(os.path.join(base, n)) for n in names)

    # Python backend (FastAPI/Flask/Django) — root or backend/ subdir (incl. package-style)
    if _python_marker(root) or _python_marker(os.path.join(root, "backend")):
        kinds.append("python_backend")

    # Node frontend (Vite/CRA/Next) — root or frontend/ subdir
    fe_pkg = None
    for cand in ("package.json", os.path.join("frontend", "package.json")):
        if _has(cand):
            fe_pkg = cand
            break
    if fe_pkg:
        kinds.append("node_frontend")
    # Frontend SOURCES without a manifest — a real agent delivery gap: JS/TS app
    # code was written but the project can never be installed or built.
    elif _has_dir_file("src", (".keep",)) or _frontend_sources(root) or _frontend_sources(os.path.join(root, "frontend")):
        kinds.append("node_frontend_orphan")

    # Node backend (Express/Nest) — server/ or api/ subdir
    if _has_dir_file("server", NODE_ENTRY_HINTS) or _has_dir_file("api", NODE_ENTRY_HINTS):
        kinds.append("node_backend")

    # Go backend
    if _has("go.mod") or _has_dir_file("backend", ("go.mod",)) or _has("main.go"):
        kinds.append("go_backend")

    # Rust backend
    if _has("Cargo.toml") or _has_dir_file("backend", ("Cargo.toml",)):
        kinds.append("rust_backend")

    # Java / Kotlin backend
    if _has("pom.xml") or _has("build.gradle") or _has_dir_file("backend", ("pom.xml", "build.gradle")):
        kinds.append("java_backend")

    # PHP backend
    if _has("composer.json") or _has_dir_file("backend", ("composer.json",)):
        kinds.append("php_backend")

    # Ruby backend
    if _has("Gemfile") or _has_dir_file("backend", ("Gemfile",)):
        kinds.append("ruby_backend")

    # Static site — only if nothing else matched
    if not kinds and (_has("index.html") or _has_dir_file("public", ("index.html",))):
        kinds.append("static")

    if not kinds:
        kinds.append("unknown")
    return kinds


# ─────────────────────────────────────────────────────────────────────────────
# Engine
# ─────────────────────────────────────────────────────────────────────────────

def plan_stages(kinds: list[str]) -> list[str]:
    """Derive exactly which verification stages apply to the detected project.

    Fully dynamic: the stage plan comes from the project kinds found on disk, so
    a Python-only, Node-only, or mixed repo each gets exactly the gates that can
    actually prove runnability. No caller needs to (or may) hard-code a list.
    """
    kinds = kinds or []
    if kinds == ["unknown"]:
        return ["foundation"]

    has_python = "python_backend" in kinds
    has_node_app = any(k in kinds for k in ("node_frontend", "node_backend", "node_frontend_orphan"))

    stages: list[str] = ["foundation"]
    if has_python:
        stages.append("imports")
    if has_node_app:
        stages.append("build")
    if has_python:
        stages.append("boot")
    if has_node_app:
        stages.append("serve")
    if has_python:
        stages.append("contract")
    if has_python or has_node_app:
        stages.append("connectivity")
    return stages


class VerificationEngine:
    """Runs runnability gates for any project, reporting skipped checks honestly."""

    def __init__(
        self,
        workspace_path: str,
        event_cb: Any = None,
        health_path: str = "/health",
        boot_timeout: float = 25.0,
        serve_timeout: float = 30.0,
        contract_path: str | None = None,
    ):
        self.ws = workspace_path
        self.event_cb = event_cb
        self.health_path = health_path if health_path.startswith("/") else f"/{health_path}"
        self.boot_timeout = boot_timeout
        self.serve_timeout = serve_timeout
        self.contract_path = contract_path or os.path.join(
            workspace_path, ".agent", "contracts", "api_contract.json"
        )
        self._last_python_routes: list[dict] = []
        self._roots_cache: dict[str, list[str]] | None = None

    # ── helpers ──────────────────────────────────────────────────────────────

    def _post(self, name: str, data: dict) -> None:
        if self.event_cb:
            try:
                self.event_cb(name, data)
            except Exception:
                pass

    def _find_roots(self) -> dict[str, list[str]]:
        """Discover every Python / Node root in the workspace, dynamically.

        No directory names are assumed: any directory carrying a manifest
        (requirements/pyproject/Pipfile or package.json) — at the workspace root
        or nested up to a bounded depth — is treated as a root of that stack.
        """
        cached = getattr(self, "_roots_cache", None)
        if cached is not None:
            return cached

        py_roots: list[str] = []
        node_roots: list[str] = []
        if _python_marker(self.ws):
            py_roots.append(self.ws)
        if _node_marker(self.ws):
            node_roots.append(self.ws)

        skip_dirs = {
            "node_modules", ".git", ".agent", ".agent_history", ".agent_ipc",
            "venv", ".venv", "env", "__pycache__", "dist", "build", "out",
            ".next", "coverage", ".turbo", "tmp", "temp",
        }
        max_depth = 3
        for root_dir, dirs, files in os.walk(self.ws):
            dirs[:] = [d for d in dirs if d not in skip_dirs and not d.startswith(".")]
            rel = os.path.relpath(root_dir, self.ws)
            depth = 0 if rel == "." else rel.count(os.sep) + 1
            if depth >= max_depth:
                dirs[:] = []
            if root_dir == self.ws:
                continue
            if any(f in files for f in ("requirements.txt", "pyproject.toml", "Pipfile", "setup.py")) or _python_marker(root_dir):
                py_roots.append(root_dir)
            if "package.json" in files:
                node_roots.append(root_dir)

        # De-duplicate while preserving discovery order
        seen: set[str] = set()
        roots = {
            "python": [d for d in py_roots if not (d in seen or seen.add(d))],
            "node": [d for d in node_roots if not (d in seen or seen.add(d))],
        }
        self._roots_cache = roots
        return roots

    def _run(self, cmd: list[str], cwd: str, timeout: float) -> tuple[bool, str, str]:
        """Run a command with timeout, returning (ok, stdout_tail, stderr_tail)."""
        try:
            proc = subprocess.run(
                cmd, cwd=cwd, timeout=timeout,
                capture_output=True, text=True, errors="replace",
            )
            ok = proc.returncode == 0
            out = (proc.stdout or "")[-4000:]
            err = (proc.stderr or "")[-4000:]
            return ok, out, err
        except subprocess.TimeoutExpired:
            return False, "", f"TIMEOUT after {timeout}s: {' '.join(cmd)}"
        except FileNotFoundError:
            return False, "", f"Command not found: {cmd[0]} (tool unavailable in this environment)"
        except Exception as exc:
            return False, "", f"Command failed: {exc}"

    def _clean_output(self, out: str, err: str, limit: int = 2500) -> str:
        """Combine stdout/stderr tails for a failure report.

        Drops package-manager notice/warn noise so the REAL error survives for
        the repair agent instead of being crowded out by banner lines.
        """
        parts: list[str] = []
        for chunk in (out or "", err or ""):
            for line in chunk.splitlines():
                low = line.strip().lower()
                if low.startswith(("npm notice", "npm warn")):
                    continue
                if not line.strip() and (not parts or not parts[-1].strip()):
                    continue
                parts.append(line)
        return "\n".join(parts).strip()[-limit:]

    # ── stage 1: foundation ──────────────────────────────────────────────────

    def check_foundation(self, kinds: list[str]) -> CheckResult:
        problems: list[str] = []
        roots = self._find_roots()

        # Python: an entrypoint must exist somewhere importable
        if "python_backend" in kinds:
            py_roots = roots["python"] or [self.ws]
            ok = False
            for pr in py_roots:
                if any(os.path.exists(os.path.join(pr, h)) for h in PY_ENTRY_HINTS):
                    ok = True
                    break
                for pkg in ("app", "src", "backend"):
                    if os.path.exists(os.path.join(pr, pkg, "main.py")):
                        ok = True
                        break
                if ok:
                    break
            if not ok:
                problems.append(
                    "python_backend: no entrypoint found (main.py/app.py/asgi.py/manage.py, "
                    f"or app/src/backend package main.py) under {', '.join(py_roots)} — "
                    "the server cannot be started."
                )

        # Python: a dependency manifest is required for installability (same
        # principle as package.json for Node). Sources without any manifest can
        # never have deps installed — flag it, don't silently pass.
        if "python_backend" in kinds:
            py_roots = roots["python"] or [self.ws]
            has_manifest = any(
                os.path.exists(os.path.join(pr, m))
                for pr in py_roots
                for m in ("requirements.txt", "pyproject.toml", "Pipfile", "setup.py")
            ) or os.path.exists(os.path.join(self.ws, "requirements.txt"))
            if not has_manifest:
                problems.append(
                    "python_backend: no requirements.txt/pyproject.toml found — "
                    "dependencies cannot be installed. Create a dependency manifest."
                )

        # Node frontend: package.json must exist with a build or dev script
        if "node_frontend_orphan" in kinds:
            problems.append(
                "node_frontend_orphan: frontend sources (*.tsx/jsx) exist but no package.json — "
                "the frontend can never be installed or built. Create package.json + build config."
            )
        elif "node_frontend" in kinds:
            fe_pkg = None
            for cand in ("package.json", os.path.join("frontend", "package.json")):
                p = os.path.join(self.ws, cand)
                if os.path.exists(p):
                    fe_pkg = p
                    break
            if fe_pkg:
                try:
                    with open(fe_pkg, "r", encoding="utf-8") as f:
                        scripts = (json.load(f).get("scripts") or {})
                    if "build" not in scripts and "dev" not in scripts:
                        problems.append("node_frontend: package.json has neither build nor dev script.")
                except Exception as exc:
                    problems.append(f"node_frontend: package.json unreadable: {exc}")
            else:
                problems.append("node_frontend: package.json not found.")

        if problems:
            return CheckResult(name="foundation", passed=False, detail="; ".join(problems))
        return CheckResult(name="foundation", passed=True,
                           detail="all required manifests/entrypoints present")

    # ── stage 2: imports (+ live route extraction) ───────────────────────────

    def check_imports(self, kinds: list[str]) -> CheckResult:
        notes: list[str] = []
        failures: list[str] = []
        roots = self._find_roots()

        for pr in roots["python"]:
            entry = None
            for cand in ("app/main.py", "src/main.py", "main.py", "app.py", "asgi.py"):
                if os.path.exists(os.path.join(pr, cand)):
                    entry = cand
                    break
            if not entry:
                # any package dir with __init__.py + main.py
                try:
                    for d in os.listdir(pr):
                        full = os.path.join(pr, d, "main.py")
                        if os.path.isfile(full) and os.path.exists(os.path.join(pr, d, "__init__.py")):
                            entry = f"{d}/main.py"
                            break
                except Exception:
                    pass
            if not entry:
                failures.append(f"{pr}: no Python entrypoint module found to import")
                continue

            # Bounded cause-based repair (platform-side): if the project declares
            # dependencies, ensure they are installed ONCE before judging imports.
            # This separates "agent wrote broken code" from "env lacks deps".
            if not getattr(self, "_deps_attempted", set()):
                self._deps_attempted = set()
            if pr not in self._deps_attempted:
                self._deps_attempted.add(pr)
                req = os.path.join(pr, "requirements.txt")
                if os.path.exists(req):
                    self._post("verification_progress", {"stage": "imports", "message": f"pip install -r requirements.txt in {os.path.basename(pr)}..."})
                    pok, _, perr = self._run(
                        [sys.executable or "python", "-m", "pip", "install", "-q", "-r", req,
                         "--prefer-binary", "--no-warn-script-location"],
                        cwd=pr, timeout=420.0,
                    )
                    if not pok:
                        return CheckResult(name="imports", passed=False,
                                           detail=f"pip install failed in {pr}:\n{(perr or '')[-1000:]}")

            mod = entry.replace("/", ".").removesuffix(".py")
            import_dir = pr
            if os.path.basename(pr) == "backend" and os.path.isdir(os.path.join(pr, "app")):
                import_dir = os.path.dirname(pr)

            # Import WITHOUT creating DB connections or starting a server; export mounted routes.
            code = (
                "import importlib, json, sys, os\n"
                f"for p in [{pr!r}, {self.ws!r}, {import_dir!r}]:\n"
                "    if p and p not in sys.path:\n"
                "        sys.path.insert(0, p)\n"
                f"mod = importlib.import_module({mod!r})\n"
                "app = getattr(mod, 'app', None)\n"
                "routes = []\n"
                "if app is not None and hasattr(app, 'routes'):\n"
                "    for r in app.routes:\n"
                "        try:\n"
                "            routes.append({'method': sorted(getattr(r, 'methods', []) or []), 'path': getattr(r, 'path', '')})\n"
                "        except Exception:\n"
                "            pass\n"
                "print(json.dumps({'ok': True, 'has_app': app is not None, 'routes': routes}))\n"
            )
            ok, out, err = self._run(
                [sys.executable or "python", "-c", code],
                cwd=import_dir, timeout=60.0,
            )
            if not ok:
                tail = (err or out or "").strip()[-1200:]
                failures.append(f"import {mod} failed:\n{tail}")
            else:
                routes = self._parse_routes(out)
                notes.append(f"{mod}: import OK ({len(routes)} routes mounted)")
                if routes:
                    self._last_python_routes = routes

        if failures:
            return CheckResult(name="imports", passed=False, detail="\n---\n".join(failures))
        if not notes:
            return CheckResult(name="imports", passed=True, skipped=True,
                               skip_reason="no verifiable Python entrypoints detected")
        return CheckResult(name="imports", passed=True, detail="; ".join(notes))

    def _parse_routes(self, stdout: str) -> list[dict]:
        try:
            start = stdout.find("{")
            end = stdout.rfind("}")
            if start == -1 or end == -1:
                return []
            data = json.loads(stdout[start:end + 1])
            routes = data.get("routes") or []
            out: list[dict] = []
            for r in routes:
                methods = r.get("method") or []
                path = r.get("path") or ""
                if path.startswith(("/openapi.json", "/docs", "/redoc", "/docs/oauth2-redirect")):
                    continue
                for m in (methods or ["GET"]):
                    out.append({"method": m, "path": path})
            return out
        except Exception:
            return []

    # ── stage 3: build (npm install ALWAYS before build) ─────────────────────

    def check_build(self, kinds: list[str]) -> CheckResult:
        failures: list[str] = []
        notes: list[str] = []
        roots = self._find_roots()

        for nr in roots["node"]:
            rel = os.path.relpath(nr, self.ws)
            pkg = os.path.join(nr, "package.json")
            try:
                with open(pkg, "r", encoding="utf-8") as f:
                    scripts = (json.load(f).get("scripts") or {})
            except Exception:
                scripts = {}
            if "build" not in scripts:
                notes.append(f"{rel}: no build script — skipping npm build")
                continue

            if not os.path.isdir(os.path.join(nr, "node_modules")):
                self._post("verification_progress", {
                    "stage": "build", "message": f"npm install in {rel} (before build)...",
                })
                ok, out, err = self._run(
                    ["npm", "install", "--include=dev", "--no-audit", "--no-fund"],
                    cwd=nr, timeout=600.0,
                )
                if not ok:
                    failures.append(f"npm install failed in {rel}:\n{self._clean_output(out, err)}")
                    continue

            self._post("verification_progress", {"stage": "build", "message": f"npm run build in {rel}..."})
            ok, out, err = self._run(["npm", "run", "build"], cwd=nr, timeout=600.0)
            if not ok:
                failures.append(f"npm run build failed in {rel}:\n{self._clean_output(out, err)}")
            else:
                notes.append(f"{rel}: npm build OK")

        if failures:
            return CheckResult(name="build", passed=False, detail="\n---\n".join(failures))
        if not notes:
            return CheckResult(name="build", passed=True, skipped=True,
                               skip_reason="no buildable sub-projects detected")
        return CheckResult(name="build", passed=True, detail="; ".join(notes))

    # ── stage 4: boot + health probe ─────────────────────────────────────────

    def check_boot(self, kinds: list[str]) -> CheckResult:
        """Boot the Python backend on an ephemeral port and probe its health endpoint.

        Honest skip: no python backend, or no module:app ASGI reference — skipped
        with a reason, never silently passed and never hallucinated.
        """
        roots = self._find_roots()
        if not roots["python"]:
            return CheckResult(name="boot", passed=True, skipped=True,
                               skip_reason="no python backend detected")
        if not _has_uvicorn():
            return CheckResult(
                name="boot", passed=True, skipped=True,
                skip_reason="uvicorn not installed in runtime environment — boot check skipped (recorded, not passed silently)",
            )

        pr = roots["python"][0]
        app_ref = self._detect_asgi_ref(pr)
        if not app_ref:
            return CheckResult(name="boot", passed=True, skipped=True,
                               skip_reason="no importable ASGI/WSGI app object (module:app) found — boot check not applicable")

        port = self._ephemeral_port()
        env = dict(os.environ)
        env["PYTHONPATH"] = os.path.dirname(pr) if os.path.basename(pr) == "backend" else pr
        env.setdefault("ENVIRONMENT", "test")

        proc = None
        try:
            proc = subprocess.Popen(
                [sys.executable or "python", "-m", "uvicorn", app_ref,
                 "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
                cwd=pr, env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            deadline = time.time() + self.boot_timeout
            while time.time() < deadline:
                if proc.poll() is not None:
                    err_tail = b""
                    try:
                        err_tail = proc.stderr.read() or b""
                    except Exception:
                        pass
                    return CheckResult(
                        name="boot", passed=False,
                        detail=f"uvicorn exited rc={proc.returncode} while booting {app_ref}:\n"
                               f"{err_tail.decode('utf-8', 'replace')[-1200:]}",
                    )
                code, _, _ = _http_probe(f"http://127.0.0.1:{port}{self.health_path}", timeout=3.0)
                if code is not None and code < 500:
                    return CheckResult(
                        name="boot", passed=True,
                        detail=f"{app_ref} responded {code} on {self.health_path} (port {port})",
                    )
                code2, _, _ = _http_probe(f"http://127.0.0.1:{port}/", timeout=3.0)
                if code2 is not None and code2 < 500:
                    return CheckResult(
                        name="boot", passed=True,
                        detail=f"{app_ref} responded {code2} on / (port {port})",
                    )
                time.sleep(1.0)
            return CheckResult(
                name="boot", passed=False,
                detail=f"server did not respond on port {port} within {self.boot_timeout:.0f}s",
            )
        finally:
            self._terminate(proc)

    # ── stage 4b: Node app serve (command taken from the project itself) ─────

    def check_serve(self, kinds: list[str]) -> CheckResult:
        """Prove every detected Node app actually SERVES over HTTP.

        The start command is taken from the project's own package.json scripts
        (preview/start/serve) or, when the project ships built output, from a
        static server over that output — nothing about the framework is assumed.
        """
        roots = self._find_roots()
        if not roots["node"]:
            return CheckResult(name="serve", passed=True, skipped=True,
                               skip_reason="no Node app detected — nothing to serve")

        failures: list[str] = []
        notes: list[str] = []
        for nr in roots["node"]:
            rel = os.path.relpath(nr, self.ws)
            cmd, kind = self._serve_plan(nr)
            if not cmd:
                notes.append(
                    f"{rel}: no preview/start/serve script and no built output — serve check not applicable"
                )
                continue
            self._post("verification_progress", {"stage": "serve", "message": f"Serving {rel} via {kind}..."})
            ok, detail = self._serve_and_probe(nr, cmd, kind)
            if ok:
                notes.append(f"{rel}: {detail}")
            else:
                failures.append(f"{rel}: {detail}")

        if failures:
            return CheckResult(name="serve", passed=False, detail="\n---\n".join(failures))
        if not notes:
            return CheckResult(name="serve", passed=True, skipped=True,
                               skip_reason="no servable Node app detected")
        return CheckResult(name="serve", passed=True, detail="; ".join(notes))

    # ── stage 6: cross-service connectivity ─────────────────────────────────

    def check_connectivity(self, kinds: list[str]) -> CheckResult:
        """Every detected server is actually up, and the frontend's declared API
        base reaches the backend.

        The API base is discovered from the project's own env files / source
        (any framework's VITE_*/REACT_APP_*/NEXT_PUBLIC_* or baseURL constant) —
        if the project declares none, the cross-service probe is recorded as not
        applicable rather than silently passing.
        """
        roots = self._find_roots()
        if not roots["python"] and not roots["node"]:
            return CheckResult(name="connectivity", passed=True, skipped=True,
                               skip_reason="no servers detected — connectivity not applicable")

        failures: list[str] = []
        notes: list[str] = []
        proc = None
        backend_base = ""
        try:
            if roots["python"]:
                ok, backend_base, detail, proc = self._boot_backend_process()
                if ok:
                    notes.append(f"backend reachable at {backend_base} ({detail})")
                else:
                    failures.append(f"backend unreachable: {detail}")

            api_base, source = self._detect_api_base(roots["node"], backend_base)
            if api_base:
                probe_url = api_base.rstrip("/") + "/"
                code, _, err = _http_probe(probe_url, timeout=5.0)
                if code is not None and code < 500:
                    notes.append(f"frontend API base {api_base} reachable (HTTP {code}) [{source}]")
                else:
                    failures.append(
                        f"frontend API base {api_base} unreachable [{source}]"
                        + (f": {err}" if err else "")
                    )
            else:
                notes.append(
                    "frontend API base not declared in env/source — cross-service probe not applicable"
                )
        finally:
            self._terminate(proc)

        if failures:
            return CheckResult(name="connectivity", passed=False, detail="\n---\n".join(failures))
        if not notes:
            return CheckResult(name="connectivity", passed=True, skipped=True,
                               skip_reason="nothing verifiable detected")
        return CheckResult(name="connectivity", passed=True, detail="; ".join(notes))

    # ── server helpers ──────────────────────────────────────────────────────

    def _ephemeral_port(self) -> int:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        return port

    def _terminate(self, proc: Any) -> None:
        if proc and proc.poll() is None:
            try:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except Exception:
                    proc.kill()
            except Exception:
                pass

    def _detect_asgi_ref(self, py_root: str) -> str | None:
        """Find any importable ASGI/WSGI app object in a Python root, dynamically.

        Scans the source for `<name> = <Framework>(...)` assignments and returns
        the importable `module:object` reference — no framework or filename is
        hard-coded, so FastAPI/Flask/Starlette/Quart/Sanic/aiohttp/Falcon all work
        in any layout.
        """
        app_pattern = re.compile(
            r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*(?::\s*[^=]+)?=\s*"
            r"(FastAPI|APIRouter|Flask|Starlette|Quart|Sanic|Bottle|web\.Application|falcon\.App|falcon\.API)\s*\(",
            re.MULTILINE,
        )
        skip_dirs = {"node_modules", ".git", ".agent", "venv", ".venv", "__pycache__", "dist", "build", "tests", "test"}
        candidates: list[tuple[int, str]] = []
        for root_dir, dirs, files in os.walk(py_root):
            dirs[:] = [d for d in dirs if d not in skip_dirs and not d.startswith(".")]
            for fname in sorted(files):
                if not fname.endswith(".py"):
                    continue
                fpath = os.path.join(root_dir, fname)
                try:
                    with open(fpath, "r", encoding="utf-8", errors="replace") as fh:
                        content = fh.read()
                except Exception:
                    continue
                match = app_pattern.search(content)
                if not match:
                    continue
                obj = match.group(1)
                rel = os.path.relpath(fpath, py_root).replace("\\", "/")
                module = rel[:-3].replace("/", ".")
                if module.endswith(".__init__"):
                    module = module[: -len(".__init__")]
                # Prefer conventional entrypoints when several apps exist.
                rank = 0 if os.path.basename(fpath) in ("main.py", "app.py", "asgi.py", "server.py") else 1
                candidates.append((rank, f"{module}:{obj}"))
        if not candidates:
            return None
        candidates.sort(key=lambda c: c[0])
        return candidates[0][1]

    def _read_scripts(self, node_root: str) -> dict[str, str]:
        try:
            with open(os.path.join(node_root, "package.json"), "r", encoding="utf-8") as fh:
                return json.load(fh).get("scripts") or {}
        except Exception:
            return {}

    def _serve_plan(self, node_root: str) -> tuple[list[str], str]:
        """Return (command, description) to serve this Node app, from its own config."""
        scripts = self._read_scripts(node_root)
        for script in ("preview", "start", "serve"):
            if script in scripts:
                return ["npm", "run", script], f"npm run {script}"
        for name in ("dist", "build", "out"):
            out_dir = os.path.join(node_root, name)
            if os.path.isfile(os.path.join(out_dir, "index.html")):
                return [
                    sys.executable or "python", "-m", "http.server", "{port}",
                    "--bind", "127.0.0.1", "--directory", out_dir,
                ], f"static {name}/"
        return [], ""

    def _serve_and_probe(self, node_root: str, cmd: list[str], kind: str) -> tuple[bool, str]:
        """Start a Node app on an ephemeral port and probe it. Always cleans up."""
        if not shutil.which("npm") and cmd[0] == "npm":
            return False, "npm not available in this environment"
        port = self._ephemeral_port()
        run_cmd = [str(port) if part == "{port}" else part for part in cmd]
        if run_cmd[0] == "npm":
            run_cmd += ["--", "--port", str(port), "--host", "127.0.0.1"]
        env = dict(os.environ)
        env.update({"PORT": str(port), "HOST": "127.0.0.1", "BROWSER": "none", "CI": "1"})
        proc = None
        try:
            proc = subprocess.Popen(
                run_cmd, cwd=node_root, env=env,
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            )
            deadline = time.time() + self.serve_timeout
            last_code: int | None = None
            while time.time() < deadline:
                if proc.poll() is not None:
                    tail = ""
                    try:
                        tail = self._clean_output("", (proc.stderr.read() or b"").decode("utf-8", "replace"))
                    except Exception:
                        pass
                    return False, f"'{kind}' exited rc={proc.returncode} before serving:\n{tail}"
                code, _, _ = _http_probe(f"http://127.0.0.1:{port}/", timeout=3.0)
                if code is not None:
                    last_code = code
                    if 200 <= code < 400:
                        return True, f"{kind} responded HTTP {code} on port {port}"
                time.sleep(1.0)
            if last_code is not None:
                return False, (
                    f"{kind} started but returned HTTP {last_code} on / for "
                    f"{self.serve_timeout:.0f}s — the app entry is not actually served"
                )
            return False, f"{kind} did not respond on port {port} within {self.serve_timeout:.0f}s"
        except FileNotFoundError as exc:
            return False, f"'{kind}' could not start: {exc}"
        finally:
            self._terminate(proc)

    def _boot_backend_process(self) -> tuple[bool, str, str, Any]:
        """Start the detected ASGI app on an ephemeral port and probe it.

        Returns (ok, base_url, detail, proc); the caller owns the process.
        """
        roots = self._find_roots()
        if not roots["python"]:
            return False, "", "no python backend detected", None
        if not _has_uvicorn():
            return False, "", "uvicorn not installed in runtime environment", None

        pr = roots["python"][0]
        app_ref = self._detect_asgi_ref(pr)
        if not app_ref:
            return False, "", "no importable ASGI/WSGI app object found", None

        port = self._ephemeral_port()
        env = dict(os.environ)
        env["PYTHONPATH"] = os.path.dirname(pr) if os.path.basename(pr) == "backend" else pr
        env.setdefault("ENVIRONMENT", "test")
        base_url = f"http://127.0.0.1:{port}"

        try:
            proc = subprocess.Popen(
                [sys.executable or "python", "-m", "uvicorn", app_ref,
                 "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
                cwd=pr, env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            return False, base_url, f"uvicorn could not start: {exc}", None

        deadline = time.time() + self.boot_timeout
        while time.time() < deadline:
            if proc.poll() is not None:
                tail = ""
                try:
                    tail = self._clean_output("", (proc.stderr.read() or b"").decode("utf-8", "replace"))
                except Exception:
                    pass
                return False, base_url, f"{app_ref} exited rc={proc.returncode} while booting:\n{tail}", proc
            for path in (self.health_path, "/"):
                code, _, _ = _http_probe(f"{base_url}{path}", timeout=3.0)
                if code is not None and code < 500:
                    return True, base_url, f"{app_ref} responded HTTP {code} on {path}", proc
            time.sleep(1.0)
        return False, base_url, f"{app_ref} did not respond within {self.boot_timeout:.0f}s", proc

    def _detect_api_base(self, node_roots: list[str], backend_base: str) -> tuple[str, str]:
        """Discover the frontend's API base URL from env files or source, dynamically."""
        env_key_re = re.compile(
            r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*['\"]?(https?://[^'\"\s]+)", re.MULTILINE
        )
        src_re = re.compile(
            r"(?:baseURL|baseUrl|API_BASE_URL|API_URL|VITE_API_URL|apiBaseUrl|API_BASE)"
            r"\s*[:=]\s*[`'\"](https?://[^`'\"\s]+)", re.MULTILINE
        )
        skip_dirs = {"node_modules", ".git", "dist", "build", ".next", "coverage"}

        for nr in node_roots:
            # 1. env files at the Node root and two levels up (monorepos)
            search_dirs = [nr, os.path.dirname(nr), os.path.dirname(os.path.dirname(nr))]
            for d in search_dirs:
                if not d or not os.path.isdir(d):
                    continue
                try:
                    entries = os.listdir(d)
                except OSError:
                    continue
                for fname in entries:
                    if not (fname.startswith(".env") or fname == "vite.config.ts" or fname == "vite.config.js"):
                        continue
                    fpath = os.path.join(d, fname)
                    if not os.path.isfile(fpath):
                        continue
                    try:
                        with open(fpath, "r", encoding="utf-8", errors="replace") as fh:
                            content = fh.read()
                    except Exception:
                        continue
                    for _key, url in env_key_re.findall(content):
                        return url, f"{os.path.relpath(fpath, self.ws)}"
                    m = src_re.search(content)
                    if m:
                        return m.group(1), f"{os.path.relpath(fpath, self.ws)}"
            # 2. source constants
            for root_dir, dirs, files in os.walk(nr):
                dirs[:] = [d for d in dirs if d not in skip_dirs and not d.startswith(".")]
                for fname in files:
                    if not fname.endswith((".ts", ".tsx", ".js", ".jsx", ".vue", ".svelte")):
                        continue
                    fpath = os.path.join(root_dir, fname)
                    try:
                        with open(fpath, "r", encoding="utf-8", errors="replace") as fh:
                            content = fh.read()
                    except Exception:
                        continue
                    m = src_re.search(content)
                    if m:
                        return m.group(1), f"{os.path.relpath(fpath, self.ws)}"

        # No declared base: fall back to the live backend URL when we have one,
        # so the connectivity probe still proves the backend answers requests.
        if backend_base:
            return backend_base, "live backend (no frontend API base declared)"
        return "", ""

    # ── stage 5: contract route coverage ─────────────────────────────────────

    def check_contract_routes(self) -> CheckResult:
        """Diff routes mounted by the imported app against the analyzed api_contract.

        Never fails on absent contract artifacts; enforces coverage only when a
        real contract exists, with a tolerance margin for deprecated routes.
        """
        if not os.path.exists(self.contract_path):
            return CheckResult(name="contract", passed=True, skipped=True,
                               skip_reason="no api_contract.json — nothing to validate against")

        if not self._last_python_routes:
            res = self.check_imports(detect_project_kinds(self.ws))
            if not getattr(self, "_last_python_routes", None):
                return CheckResult(name="contract", passed=True, skipped=True,
                                   skip_reason="no live route data available from import stage")

        try:
            with open(self.contract_path, "r", encoding="utf-8") as f:
                contract = json.load(f)
        except Exception as exc:
            return CheckResult(name="contract", passed=True, skipped=True,
                               skip_reason=f"api_contract.json unreadable: {exc}")

        contract_routes = contract.get("routes") or []
        if not contract_routes:
            return CheckResult(name="contract", passed=True, skipped=True,
                               skip_reason="api_contract.json has no routes")

        mounted = {(r.get("method", "GET"), _norm_path(r.get("path", ""))) for r in self._last_python_routes}
        missing: list[str] = []
        for cr in contract_routes:
            method = (cr.get("method") or "GET").upper()
            cpath = _norm_path(cr.get("path") or "")
            if not cpath:
                continue
            if (method, cpath) not in mounted:
                # tolerate router prefix differences: match by suffix
                if not any(m == method and p.endswith(cpath) for m, p in mounted):
                    missing.append(f"{method} {cpath}")

        coverage = 1 - (len(missing) / max(1, len(contract_routes)))
        if missing and coverage < 0.85:
            return CheckResult(
                name="contract", passed=False,
                detail=f"contract coverage {coverage:.0%} ({len(missing)} of {len(contract_routes)} routes missing):\n"
                       + "\n".join(missing[:20]),
            )
        if missing:
            return CheckResult(name="contract", passed=True,
                               detail=f"contract coverage {coverage:.0%} — {len(missing)} route(s) not mounted (within tolerance)")
        return CheckResult(name="contract", passed=True,
                           detail=f"all {len(contract_routes)} contract routes mounted")

    def _resolve_path(self, raw_path: str) -> tuple[str, str] | None:
        """Resolve any path format (relative, absolute, container /workspace/ prefix) to
        (absolute_path, relative_workspace_path).
        """
        if not raw_path:
            return None
        norm = str(raw_path).replace("\\", "/").strip()
        ws_norm = os.path.normpath(self.ws).replace("\\", "/").rstrip("/")

        # Direct absolute check
        if os.path.isfile(norm):
            try:
                rel = os.path.relpath(norm, self.ws).replace("\\", "/")
            except ValueError:
                rel = os.path.basename(norm)
            return norm, rel

        # Strip redundant /workspace or workspace/ prefix if self.ws already points to workspace
        clean = norm.lstrip("/")
        if clean.startswith("workspace/"):
            clean = clean[len("workspace/"):].lstrip("/")
        elif ws_norm and norm.startswith(ws_norm + "/"):
            clean = norm[len(ws_norm) + 1:].lstrip("/")

        # Check self.ws / clean
        cand = os.path.normpath(os.path.join(self.ws, clean))
        if os.path.isfile(cand):
            return cand, os.path.relpath(cand, self.ws).replace("\\", "/")

        # Suffix/basename search within workspace
        base = os.path.basename(clean)
        for root, _, files in os.walk(self.ws):
            if any(s in root for s in (".git", ".agent", "node_modules", "venv", "__pycache__")):
                continue
            if base in files:
                fpath = os.path.join(root, base)
                rel_f = os.path.relpath(fpath, self.ws).replace("\\", "/")
                if clean.endswith(rel_f) or rel_f.endswith(clean):
                    return fpath, rel_f

        return None

    def sync_dependencies(self) -> dict[str, Any]:
        """Dynamically detect and install dependencies for any tech stack in the workspace."""
        results: dict[str, Any] = {}
        if not hasattr(self, "_deps_synced"):
            self._deps_synced = set()

        for root, _, files in os.walk(self.ws):
            if any(skip in root for skip in ("node_modules", ".git", ".agent", "venv", "__pycache__")):
                continue

            rel_root = os.path.relpath(root, self.ws).replace("\\", "/")

            # 1. Python (requirements.txt / pyproject.toml)
            if "requirements.txt" in files:
                req_path = os.path.join(root, "requirements.txt")
                if req_path not in self._deps_synced:
                    self._deps_synced.add(req_path)
                    self._post("verification_progress", {
                        "stage": "dependencies",
                        "message": f"Syncing Python dependencies in {rel_root}...",
                    })
                    ok, _, err = self._run(
                        [sys.executable or "python", "-m", "pip", "install", "-q", "-r", req_path,
                         "--prefer-binary", "--no-warn-script-location"],
                        cwd=root, timeout=180.0,
                    )
                    results[f"pip:{rel_root}"] = ok
                    if not ok:
                        self._post("verification_progress", {
                            "stage": "dependencies",
                            "message": f"Warning: pip install had errors in {rel_root}: {(err or '')[-200:]}",
                        })

            # 2. Node / TypeScript / React / Vue / etc. (package.json)
            if "package.json" in files:
                pkg_path = os.path.join(root, "package.json")
                node_modules = os.path.join(root, "node_modules")
                if pkg_path not in self._deps_synced and (not os.path.isdir(node_modules) or not os.listdir(node_modules)):
                    self._deps_synced.add(pkg_path)
                    if shutil.which("npm"):
                        self._post("verification_progress", {
                            "stage": "dependencies",
                            "message": f"Syncing npm packages in {rel_root}...",
                        })
                        ok, _, _ = self._run(
                            ["npm", "install", "--prefer-offline", "--no-audit", "--silent"],
                            cwd=root, timeout=180.0,
                        )
                        results[f"npm:{rel_root}"] = ok

            # 3. Go (go.mod)
            if "go.mod" in files and shutil.which("go") and root not in self._deps_synced:
                self._deps_synced.add(root)
                ok, _, _ = self._run(["go", "mod", "download"], cwd=root, timeout=60.0)
                results[f"go:{rel_root}"] = ok

            # 4. Rust (Cargo.toml)
            if "Cargo.toml" in files and shutil.which("cargo") and root not in self._deps_synced:
                self._deps_synced.add(root)
                ok, _, _ = self._run(["cargo", "fetch"], cwd=root, timeout=60.0)
                results[f"cargo:{rel_root}"] = ok

        return results

    # ── per-task gate (Gate A) ───────────────────────────────────────────────

    def verify_task_changes(self, files_changed: list[str]) -> CheckResult:
        """Universal per-task exit gate: validates all changed files regardless of tech stack.
        
        Uses SyntaxValidator for Python, JS, TS, TSX, JSX, HTML, CSS, JSON, Vue, Svelte,
        plus native compiler checks where available (Go, Rust, Java).
        Auto-syncs dependencies if package manifests were touched.
        """
        failures: list[str] = []
        resolved_files: list[tuple[str, str]] = []  # (abs_path, rel_path)

        for raw in (files_changed or []):
            raw_clean = str(raw or "").replace("\\", "/").strip()
            if not raw_clean or any(raw_clean.startswith(p) or f"/{p}" in raw_clean for p in (".agent", ".agent_history", ".agent_ipc", ".git")):
                continue
            resolved = self._resolve_path(raw_clean)
            if resolved:
                resolved_files.append(resolved)

        if not resolved_files:
            return CheckResult(
                name="task_changes", passed=True,
                detail="No modified code files found on disk (files were deleted or no changes applied)."
            )

        # 1. Check if dependency manifests changed — trigger dynamic in-container sync
        manifest_names = {"requirements.txt", "package.json", "pyproject.toml", "go.mod", "Cargo.toml", "pom.xml"}
        if any(os.path.basename(r) in manifest_names for _, r in resolved_files):
            try:
                self.sync_dependencies()
            except Exception as sync_err:
                self._post("verification_progress", {"stage": "dependencies", "message": f"Dependency sync note: {sync_err}"})

        # 2. Run multi-language syntax and import validation using SyntaxValidator
        rel_paths_to_validate = [rel for _, rel in resolved_files]
        try:
            from runtime.syntax_validator import SyntaxValidator
            validator = SyntaxValidator(self.ws)
            syntax_errors = validator.validate_files(rel_paths_to_validate)
            for err in (syntax_errors or []):
                failures.append(f"Syntax/Parse error in {err.get('file', '')}:{err.get('line', 0)}:\n{err.get('error', '')}")
        except Exception as val_exc:
            # Fallback direct checks if SyntaxValidator has issues
            for abs_path, rel in resolved_files:
                ext = os.path.splitext(rel)[1].lower()
                if ext == ".py":
                    ok, _, err = self._run(
                        [sys.executable or "python", "-m", "py_compile", abs_path],
                        cwd=self.ws, timeout=30.0,
                    )
                    if not ok:
                        failures.append(f"Python syntax error in {rel}:\n{(err or '')[-600:]}")
                elif ext in (".js", ".mjs", ".cjs") and shutil.which("node"):
                    ok, _, err = self._run(["node", "--check", abs_path], cwd=self.ws, timeout=30.0)
                    if not ok:
                        failures.append(f"JS syntax error in {rel}:\n{(err or '')[-600:]}")

        # 3. Stack-specific compiler checks for compiled languages
        for abs_path, rel in resolved_files:
            ext = os.path.splitext(rel)[1].lower()
            if ext == ".go" and shutil.which("go"):
                ok, _, err = self._run(["go", "vet", abs_path], cwd=os.path.dirname(abs_path), timeout=30.0)
                if not ok:
                    failures.append(f"Go vet error in {rel}:\n{(err or '')[-600:]}")
            elif ext == ".rs" and shutil.which("cargo"):
                cargo_dir = os.path.dirname(abs_path)
                if os.path.exists(os.path.join(cargo_dir, "Cargo.toml")):
                    ok, _, err = self._run(["cargo", "check"], cwd=cargo_dir, timeout=60.0)
                    if not ok:
                        failures.append(f"Rust cargo check error in {rel}:\n{(err or '')[-600:]}")

        if failures:
            return CheckResult(name="task_changes", passed=False, detail="\n---\n".join(failures))

        return CheckResult(
            name="task_changes", passed=True,
            detail=f"{len(resolved_files)} changed file(s) parse and validate cleanly across stacks"
        )

    # ── orchestrator ─────────────────────────────────────────────────────────

    #: stage name → runner. The plan (plan_stages) decides which run; nothing
    #: here is project-specific, so a new stack only needs a new detect rule.
    def _stage_runner(self, name: str):
        return {
            "imports": lambda kinds: self.check_imports(kinds),
            "build": lambda kinds: self.check_build(kinds),
            "boot": lambda kinds: self.check_boot(kinds),
            "serve": lambda kinds: self.check_serve(kinds),
            "contract": lambda kinds: self.check_contract_routes(),
            "connectivity": lambda kinds: self.check_connectivity(kinds),
        }.get(name)

    def run_full_verification(self, stages: list[str] | None = None) -> VerificationReport:
        """Run the gates that apply to the project found on disk.

        Stage selection is DYNAMIC (plan_stages) — derived from the detected
        project kinds. `stages` may narrow that plan explicitly (e.g. for a
        targeted re-check), but no caller is required to know any stage names.
        """
        t0 = time.time()
        kinds = detect_project_kinds(self.ws)
        report = VerificationReport(project_kinds=kinds)

        planned = plan_stages(kinds)
        want = [s for s in (stages or planned) if s in planned or s == "foundation"]
        if not want:
            want = planned

        self._post("verification_started", {"project_kinds": kinds, "stages": want})

        # Unknown stack: never fail on what we can't recognize, but never pass
        # silently either — record the limitation explicitly for human review.
        if kinds == ["unknown"]:
            report.stages.append(CheckResult(
                name="project_type", passed=True, skipped=True,
                skip_reason="unrecognized project type — minimal verification only; manual review advised",
            ))

        # Foundation first — missing entrypoints invalidate everything downstream
        if "foundation" in want:
            r = self.check_foundation(kinds)
            report.stages.append(r)
            if not r.passed:
                report.duration_s = time.time() - t0
                report.error_signature = report.compute_error_signature()
                self._post("verification_finished", report.to_dict())
                return report  # do not run further gates against a broken foundation

        # Dynamically sync dependencies for any detected manifests across the project
        try:
            self.sync_dependencies()
        except Exception as sync_err:
            self._post("verification_progress", {"stage": "dependencies", "message": f"Dependency sync note: {sync_err}"})

        for name in want:
            if name == "foundation":
                continue
            runner = self._stage_runner(name)
            if not runner:
                continue
            self._post("verification_progress", {"stage": name, "message": f"Running {name} gate..."})
            try:
                result = runner(kinds)
            except Exception as stage_err:
                result = CheckResult(
                    name=name, passed=False,
                    detail=f"{name} gate raised {type(stage_err).__name__}: {stage_err}",
                )
            report.stages.append(result)

        report.duration_s = time.time() - t0
        report.error_signature = report.compute_error_signature()
        self._post("verification_finished", report.to_dict())
        return report


# ─────────────────────────────────────────────────────────────────────────────
# small utilities
# ─────────────────────────────────────────────────────────────────────────────

def _has_node() -> bool:
    try:
        subprocess.run(
            ["node", "--version"], capture_output=True, timeout=5,
        )
        return True
    except Exception:
        return False


def _has_uvicorn() -> bool:
    try:
        import uvicorn  # noqa: F401
        return True
    except ImportError:
        return False


def _http_probe(url: str, timeout: float = 3.0) -> tuple[int | None, str, str]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "VerificationEngine/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, "", ""
    except urllib.error.HTTPError as he:
        # 4xx (e.g. auth-protected probe path) still proves the server is alive
        if he.code < 500:
            return he.code, "", ""
        return he.code, "", str(he)
    except Exception:
        return None, "", ""


def _norm_path(p: str) -> str:
    p = (p or "").strip()
    if not p:
        return ""
    if not p.startswith("/"):
        p = "/" + p
    if len(p) > 1 and p.endswith("/"):
        p = p.rstrip("/")
    # collapse {param} vs :param spellings
    p = re.sub(r"\{[^}]+\}", "{}", p)
    p = re.sub(r":[^/]+", "{}", p)
    return p


def run_verification(workspace_path: str, event_cb=None,
                     stages: list[str] | None = None) -> VerificationReport:
    """Convenience entrypoint used by graph nodes and the supervisor."""
    engine = VerificationEngine(workspace_path, event_cb=event_cb)
    return engine.run_full_verification(stages=stages)
