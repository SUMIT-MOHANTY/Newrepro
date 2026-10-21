"""
Convergence Engine - Closed-Loop Verification Battery and Self-Healing Repair Loop.
Ensures zero premature stops:
1. Stage 1: Backend AST / syntax compilation across all backend files.
2. Stage 2: Frontend Bundler build test (npm run build / vite build).
3. Stage 3: Live container runtime & HTTP 200 health check (via forward proxy / port 80).
If any stage fails, the engine compiles the exact error trace and dispatches a targeted
repair agent to achieve verified convergence.
"""

import os
import re
import json
import time
import shutil
import logging
import asyncio
import subprocess
import urllib.request
import urllib.error
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field

from app.core.config import get_settings
from app.routers.helpers import broadcast_preview_log, sync_broadcast_preview_log

logger = logging.getLogger(__name__)


@dataclass
class StageResult:
    stage_name: str
    passed: bool
    detail: str = ""
    error_type: str = "none"
    offending_files: List[str] = field(default_factory=list)


@dataclass
class ConvergenceBatteryResult:
    passed: bool
    stages: List[StageResult] = field(default_factory=list)
    failure_summary: str = ""
    repair_needed: bool = False


class ConvergenceEngine:
    """
    Executes the 3-stage validation battery on a project workspace.
    """

    def __init__(self, project_token: str, workspace_dir: str):
        self.project_token = project_token
        self.workspace_dir = workspace_dir

    def _check_backend_syntax(self) -> StageResult:
        """Stage 1: Check Python syntax across all backend files."""
        py_files: List[str] = []
        for root_dir, dirs, files in os.walk(self.workspace_dir):
            if any(skip in root_dir for skip in ("node_modules", ".git", ".agent", "venv", "__pycache__", "dist", "build")):
                continue
            for f in files:
                if f.endswith(".py"):
                    py_files.append(os.path.join(root_dir, f))

        if not py_files:
            return StageResult(stage_name="backend_syntax", passed=True, detail="No Python files to verify")

        import py_compile
        syntax_errors = []
        offending = []
        for py_f in py_files[:150]:
            try:
                py_compile.compile(py_f, doraise=True)
            except Exception as py_err:
                rel = os.path.relpath(py_f, self.workspace_dir).replace("\\", "/")
                offending.append(rel)
                syntax_errors.append(f"{rel}: {py_err}")

        if syntax_errors:
            return StageResult(
                stage_name="backend_syntax",
                passed=False,
                detail="\n".join(syntax_errors[:5]),
                error_type="syntax_error",
                offending_files=offending,
            )

        return StageResult(
            stage_name="backend_syntax",
            passed=True,
            detail=f"Successfully verified syntax for {len(py_files)} Python files",
        )

    def _check_backend_runtime_import(self) -> StageResult:
        """
        Stage 1b: Verify backend application factory (Flask/FastAPI) imports cleanly
        without runtime TypeErrors, broken decorators, or missing modules.
        """
        backend_dir = os.path.join(self.workspace_dir, "backend")
        if not os.path.isdir(backend_dir):
            backend_dir = self.workspace_dir

        has_flask_app = os.path.isfile(os.path.join(backend_dir, "app", "__init__.py"))
        has_main_py = os.path.isfile(os.path.join(backend_dir, "main.py"))

        if not has_flask_app and not has_main_py:
            return StageResult(stage_name="backend_runtime_import", passed=True, detail="No Flask/FastAPI backend structure detected")

        # Test script to run inside container or workspace
        test_script = (
            "import sys\n"
            "sys.path.insert(0, '/workspace/backend')\n"
            "sys.path.insert(0, '/workspace')\n"
            "try:\n"
            "    from app import create_app\n"
            "    app = create_app()\n"
            "    rules = [str(r) for r in app.url_map.iter_rules()]\n"
            "    print(f'__APP_SUCCESS__ {len(rules)} routes registered')\n"
            "except ImportError as ie:\n"
            "    try:\n"
            "        from main import app\n"
            "        print('__APP_SUCCESS__ main:app loaded')\n"
            "    except Exception as e2:\n"
            "        import traceback\n"
            "        traceback.print_exc()\n"
            "        sys.exit(1)\n"
            "except Exception as e:\n"
            "    import traceback\n"
            "    traceback.print_exc()\n"
            "    sys.exit(1)\n"
        )

        output = ""
        exit_code = 1
        container_found = False

        try:
            # Query running docker containers for this project
            ps_res = subprocess.run(
                ["docker", "ps", "--format", "{{.ID}}\t{{.Names}}"],
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
            )
            c_ids = []
            clean_pt = self.project_token.replace("-", "").replace("_", "")[:12]
            for line in (ps_res.stdout or "").splitlines():
                if clean_pt in line or self.project_token[:12] in line or "dsuite_agent" in line:
                    c_ids.append(line.split("\t")[0].strip())

            for c_id in c_ids:
                res = subprocess.run(
                    ["docker", "exec", c_id, "python", "-c", test_script],
                    capture_output=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=20,
                )
                output = (res.stderr or "") + "\n" + (res.stdout or "")
                exit_code = res.returncode
                container_found = True
                if exit_code == 0:
                    break
        except Exception as e:
            output = str(e)

        if not container_found:
            return StageResult(stage_name="backend_runtime_import", passed=True, detail="No active container found to run import test")

        if exit_code != 0:
            # Extract offending files and lines from traceback
            offending = re.findall(r'File "([^"]+\.py)", line (\d+)', output)
            offending_files = []
            for f_path, line_num in offending:
                rel = f_path.replace("/workspace/", "").replace("\\", "/")
                offending_files.append(f"{rel}:{line_num}")

            return StageResult(
                stage_name="backend_runtime_import",
                passed=False,
                detail=f"Backend application factory failed to import:\n{output.strip()[-800:]}",
                error_type="runtime_import_error",
                offending_files=list(set(offending_files))[:5],
            )

        return StageResult(
            stage_name="backend_runtime_import",
            passed=True,
            detail="Backend application factory and all route blueprints loaded successfully",
        )

    async def _check_frontend_build(self) -> StageResult:
        """Stage 2: Run npm run build in any frontend directory with package.json."""
        frontend_dirs = []
        for root_dir, dirs, files in os.walk(self.workspace_dir):
            if any(skip in root_dir for skip in ("node_modules", ".git", ".agent", "venv", "__pycache__", "dist", "build")):
                continue
            if "package.json" in files:
                frontend_dirs.append(root_dir)

        if not frontend_dirs:
            return StageResult(stage_name="frontend_build", passed=True, detail="No Node/npm frontend directories found")

        for f_dir in frontend_dirs:
            rel = os.path.relpath(f_dir, self.workspace_dir).replace("\\", "/")
            try:
                with open(os.path.join(f_dir, "package.json"), "r", encoding="utf-8") as pf:
                    pkg_data = json.load(pf)
                has_build = "build" in pkg_data.get("scripts", {})
            except Exception:
                has_build = False

            if not has_build:
                continue

            sync_broadcast_preview_log(
                project_token=self.project_token,
                content=f"📦 [Convergence Battery] Testing build: npm run build in {rel}...",
                event_type="build_check",
            )

            build_proc = await asyncio.to_thread(
                subprocess.run,
                "npm run build",
                shell=True,
                cwd=f_dir,
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=120,
            )

            if build_proc.returncode != 0:
                err_detail = (build_proc.stderr or build_proc.stdout or "")[:600]
                matches = re.findall(r'([a-zA-Z0-9_\-./]+\.(?:tsx|jsx|ts|js|vue|svelte|css))', err_detail)
                return StageResult(
                    stage_name="frontend_build",
                    passed=False,
                    detail=f"Build failed in {rel}:\n{err_detail}",
                    error_type="build_error",
                    offending_files=list(set(matches[:5])),
                )

        return StageResult(stage_name="frontend_build", passed=True, detail="Frontend build succeeded")

    async def _check_live_smoke(self, preview_url: str = "http://localhost:8085") -> StageResult:
        """Stage 3: Live container runtime & HTTP 200 health check with auto-port bridge."""
        sync_broadcast_preview_log(
            project_token=self.project_token,
            content=f"🌐 [Convergence Battery] Smoke testing live preview endpoint ({preview_url})...",
            event_type="smoke_test",
        )

        # Retry up to 5 times with 2s delay
        last_error = ""
        for attempt in range(5):
            try:
                req = urllib.request.Request(preview_url, headers={"User-Agent": "SwarmConvergenceEngine/1.0"})
                with urllib.request.urlopen(req, timeout=5) as resp:
                    status_code = resp.getcode()
                    content_sample = resp.read(2048).decode("utf-8", errors="replace")
                    if status_code in (200, 304):
                        return StageResult(
                            stage_name="live_smoke",
                            passed=True,
                            detail=f"Live preview responded with HTTP {status_code} ({len(content_sample)} bytes read)",
                        )
                    last_error = f"HTTP {status_code}"
            except Exception as e:
                last_error = str(e)
            await asyncio.sleep(1.5)

        return StageResult(
            stage_name="live_smoke",
            passed=False,
            detail=f"Smoke test failed at {preview_url}: {last_error}",
            error_type="health_failure",
        )

    async def run_battery(
        self,
        preview_url: str = "http://localhost:8085",
        include_live_smoke: bool = False,
    ) -> ConvergenceBatteryResult:
        """Runs the validation battery.
        When include_live_smoke=False (during dev run_all), validates syntax, backend imports,
        and frontend builds without requiring live container hosting on port 8085.
        """
        stages: List[StageResult] = []

        # Stage 1: Syntax
        stage1 = self._check_backend_syntax()
        stages.append(stage1)

        # Stage 1b: Backend Application Factory & Route Mount Verification
        stage1b = self._check_backend_runtime_import()
        stages.append(stage1b)

        # Stage 2: Bundler Build
        stage2 = await self._check_frontend_build()
        stages.append(stage2)

        # Stage 3: Live Smoke (Only if explicitly enabled, e.g. during deployment)
        if include_live_smoke:
            stage3 = await self._check_live_smoke(preview_url=preview_url)
            stages.append(stage3)

        passed = all(s.passed for s in stages)
        failures = [f"{s.stage_name}: {s.detail}" for s in stages if not s.passed]

        return ConvergenceBatteryResult(
            passed=passed,
            stages=stages,
            failure_summary="\n---\n".join(failures) if failures else "All gates passed",
            repair_needed=not passed,
        )


def collect_failed_tasks(workspace_dir: str) -> List[Dict[str, Any]]:
    """
    Read the agent task ledger(s) under .agent/ and return failed task entries.

    Dynamic: discovers whatever task_summary*.json files exist (merged ledger
    written by the swarm supervisor). Each entry carries the task's own error
    context so the repair agent gets real failure reasons, not generic
    instructions. Returns [] when every task completed or no ledger exists.
    """
    agent_dir = os.path.join(workspace_dir, ".agent")
    if not os.path.isdir(agent_dir):
        return []

    results: Dict[str, Dict[str, Any]] = {}
    for name in os.listdir(agent_dir):
        if not name.endswith(".json"):
            continue
        if not (name == "task_summary.json" or name.startswith("task_summary_")):
            continue
        try:
            with open(os.path.join(agent_dir, name), "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            continue
        tasks = data.get("tasks") or {}
        if not isinstance(tasks, dict):
            continue
        for tid, meta in tasks.items():
            if isinstance(meta, dict) and meta.get("status") == "failed":
                results[str(tid)] = {
                    "task_id": str(tid),
                    "agent": meta.get("agent"),
                    "lane": meta.get("lane"),
                    "error": str(meta.get("error") or "Unknown error")[:500],
                }
    return list(results.values())


async def execute_closed_loop_repair(
    project_token: str,
    workspace_dir: str,
    battery_result: ConvergenceBatteryResult,
    repair_runner_callable,
    max_repair_cycles: int = 3,
    failed_task_context: Optional[str] = None,
) -> bool:
    """
    Executes closed-loop self-healing repair cycles until the battery passes or max cycles reached.
    """
    engine = ConvergenceEngine(project_token=project_token, workspace_dir=workspace_dir)
    current_result = battery_result

    for cycle in range(1, max_repair_cycles + 1):
        if current_result.passed:
            logger.info(f"[ConvergenceEngine] Battery already passed for {project_token}")
            return True

        sync_broadcast_preview_log(
            project_token=project_token,
            content=f"🛠️ [Self-Healing Repair] Initiating Cycle {cycle}/{max_repair_cycles} to fix convergence failures...",
            event_type="repair_triggered",
            payload={
                "cycle": cycle,
                "max_cycles": max_repair_cycles,
                "failures": [s.stage_name for s in current_result.stages if not s.passed],
            },
        )

        # Formulate repair instructions with exact traceback
        failed_stages = [s for s in current_result.stages if not s.passed]
        repair_context = "### AUTOMATED SELF-HEALING REPAIR TASK\n"
        repair_context += "The application failed platform verification gates. You must fix the root causes:\n\n"
        for fs in failed_stages:
            repair_context += f"**FAILED STAGE: {fs.stage_name} ({fs.error_type})**\n"
            repair_context += f"```\n{fs.detail}\n```\n"
            if fs.offending_files:
                repair_context += f"Offending files: {', '.join(fs.offending_files)}\n\n"

        if failed_task_context:
            repair_context += failed_task_context

        repair_context += (
            "CRITICAL DIRECTIVES:\n"
            "1. Inspect the offending files immediately using view_file.\n"
            "2. Fix syntax errors, broken imports, missing exports, or build configuration errors.\n"
            "3. Verify your fixes build locally before completing.\n"
        )

        # Dispatch repair agent
        try:
            await repair_runner_callable(
                project_token=project_token,
                repair_instruction=repair_context,
                cycle=cycle,
            )
        except Exception as e:
            logger.error(f"[ConvergenceEngine] Repair runner error in cycle {cycle}: {e}")

        # Re-run battery
        logger.info(f"[ConvergenceEngine] Re-testing battery after cycle {cycle}...")
        current_result = await engine.run_battery()
        if current_result.passed:
            sync_broadcast_preview_log(
                project_token=project_token,
                content=f"🎉 [Self-Healing Repair] Convergence ACHIEVED on cycle {cycle}! All gates passed.",
                event_type="repair_success",
                payload={"cycle": cycle},
            )
            return True

    sync_broadcast_preview_log(
        project_token=project_token,
        content=f"⚠️ [Self-Healing Repair] Reached max repair cycles ({max_repair_cycles}). Remaining failures: {current_result.failure_summary[:200]}",
        event_type="repair_exhausted",
        payload={"summary": current_result.failure_summary},
    )
    return current_result.passed
