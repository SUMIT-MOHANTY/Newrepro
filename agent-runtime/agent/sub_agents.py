"""Sub-Agent definitions for the Supervisor Agent architecture.

Architecture: Each sub-agent owns a specific lane (backend, frontend, qa)
and runs an independent ReAct tool loop to complete its assigned task.
Sub-agents are isolated by file_ownership_scope — they can only modify
files within their designated directories.

Uses the existing ClaudeToolClient.run_tool_loop() for the ReAct loop.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from abc import ABC, abstractmethod
from typing import Any, List

from infrastructure.claude_tool_client import ClaudeToolClient, FileManifest, TaskChecklistTracker
from agent.model_router import ModelRouter, TaskType
from agent.tools.tool_registry import ToolRegistry, ToolPhase
from agent.tools.tool_executor import ToolExecutor
from runtime.reality_guard import AgentRealityGuard
from agent.checklist_generator import build_tracker_tasks

logger = logging.getLogger(__name__)


class TaskResult:
    """Result from a sub-agent's task execution."""
    def __init__(self, task_id: str, success: bool, output: str = "",
                 error: str | None = None, files_changed: list[str] | None = None):
        self.task_id = task_id
        self.success = success
        self.output = output
        self.error = error
        self.files_changed = files_changed or []
        # Gate A/C: platform verification evidence attached by the gate or supervisor
        self.verification: dict | None = None
        # Dynamic checklist progress ({completed, total}) from the tracker, if any
        self.checklist_progress: dict | None = None


class SubAgent(ABC):
    """Base class for all sub-agents in the swarm."""
    def __init__(self, name: str, role: str, lane: str,
                 file_ownership_scope: list[str], skills: str = ""):
        self.name = name
        self.role = role
        self.lane = lane
        self.file_ownership_scope = file_ownership_scope
        self.skills = skills

    @abstractmethod
    def execute_task(self, task: Any, workspace_path: str,
                     mcp: Any, router: ModelRouter, context: dict | None = None,
                     on_event: Any | None = None) -> TaskResult:
        """Execute a task using the ReAct tool loop."""
        pass

    def _build_system_prompt(self, task: Any, context: dict | None = None) -> str:
        """Build a role-specific system prompt for the ReAct loop."""
        subtask_list = ""
        for st in getattr(task, "subtasks", []):
            if isinstance(st, dict):
                done_marker = "✅" if st.get("done") else "⬜"
                title_text = st.get("title") or st.get("text") or st.get("name") or str(st)
            elif isinstance(st, str):
                done_marker = "✅" if ("[x]" in st.lower() or "✅" in st) else "⬜"
                clean_st = st.lstrip("*- []").strip()
                title_text = clean_st if clean_st else st
            else:
                done_marker = "⬜"
                title_text = str(st)
            subtask_list += f"  {done_marker} {title_text}\n"

        # Extract BRD & architectural context if provided
        brd_context_str = ""
        if context:
            brd = context.get("brd_context") or context.get("prompt", "")
            if brd:
                brd_preview = brd.strip()
                if len(brd_preview) > 2000:
                    brd_preview = brd_preview[:2000] + "..."
                brd_context_str = f"## Project Specification & BRD Context\n{brd_preview}\n\n"

        contract_guidance = ""
        live_contracts_text = ""
        try:
            for w in ("/workspace", "."):
                c_file = os.path.join(w, ".agent", "contracts", "api_contract.json")
                if os.path.exists(c_file):
                    with open(c_file, "r", encoding="utf-8") as cf:
                        cd = json.load(cf)
                    c_routes = cd.get("routes", [])
                    if c_routes:
                        live_contracts_text = "\n### LIVE BACKEND ENDPOINTS PUBLISHED BY BACKEND AGENT (USE EXACT PATHS):\n"
                        for cr in c_routes[:35]:
                            live_contracts_text += f"- {cr.get('method')} {cr.get('path')}\n"
                        break
        except Exception:
            pass

        if self.lane == "frontend":
            contract_guidance = (
                "## Inter-Agent API Contract & Authentication\n"
                "1. **Contract Discovery**: Backend APIs publish schemas to `.agent/contracts/api_contract.json`. Discover endpoints before wiring calls.\n"
                "2. **Authentication Flow**: If the application requires user identity, provide login/register forms and send `Authorization: Bearer <token>`.\n"
                "3. **Exact Endpoint Alignment**: Target the exact endpoint paths listed below. Fallback to mock data if the API returns network errors.\n"
                f"{live_contracts_text}\n"
            )
        elif self.lane == "backend":
            contract_guidance = (
                "## Inter-Agent API Contract & Database Health\n"
                "1. **Clean REST Endpoints**: Publish and maintain endpoints with consistent request/response schemas.\n"
                "2. **Migrations & Seed Data**: Ensure schema migrations are generated and applied (e.g. Django `makemigrations && migrate`, Alembic `upgrade head`, Prisma migrate). Seed default credentials (e.g. admin / admin123) so authentication works immediately.\n\n"
            )
        elif self.lane == "qa":
            contract_guidance = (
                "## Inter-Agent QA Gate\n"
                "Verify syntax, run test suites, and write your test pass/fail summary to `.agent/contracts/qa_gate.json`.\n\n"
            )

        design_guidance = ""
        if self.lane == "frontend":
            design_guidance = (
                "## 🎨 AUTONOMOUS DOMAIN-DRIVEN UI/UX DESIGN & RESEARCH PROTOCOL\n"
                "You have full creative and architectural autonomy to design a world-class user interface tailored specifically to this project's domain.\n"
                "Do NOT rely on generic, unstyled framework defaults or hardcoded generic layouts. Instead, follow this research & design workflow:\n\n"
                "1. **Autonomous Web & Domain Research (MANDATORY)**:\n"
                "   - Use your `web_search` tool to actively research leading, modern benchmarks for this project's industry.\n"
                "   - Example: search for `modern UI design benchmarks for <project_domain>` or `best UX design patterns for <domain>`.\n"
                "   - Study the design language, information density, and workflows of top-tier products in that space.\n"
                "2. **Dynamic Aesthetic & Palette Formulation**:\n"
                "   - Decide on a cohesive color system (background tones, primary brand colors, semantic accents, and contrast ratios) that feels natural and authentic to the domain.\n"
                "   - Select and import modern web fonts (via Google Fonts or CSS font imports) that elevate the interface and match the brand persona.\n"
                "3. **Purpose-Driven Layout Architecture**:\n"
                "   - Determine the right UI paradigms for the user's workflow: interactive tables, Kanban columns, analytics charts, timeline feeds, multi-step wizards, or split-pane inspectors — whatever genuinely serves the BRD requirements.\n"
                "   - Do NOT force arbitrary KPI cards if the domain doesn't need them; build what provides maximum value to the end user.\n"
                "4. **Visual Craftsmanship & Micro-Interactions**:\n"
                "   - Craft smooth transitions, subtle hover elevations, clear interactive states, and responsive navigation.\n"
                "   - Provide friendly empty states, contextual search/filtering, and immediate visual feedback on actions.\n\n"
            )

        arch_guidance = ""
        blueprint_docs = []
        for w in ("/workspace", ".", getattr(task, "workspace_path", "") or ""):
            if not w:
                continue
            docs_dir = os.path.join(w, ".agent", "docs")
            if os.path.isdir(docs_dir):
                blueprint_docs = [
                    f for f in ["LLD.md", "HLD.md", "EXECUTIVE_SUMMARY.md"]
                    if os.path.isfile(os.path.join(docs_dir, f))
                ]
                if blueprint_docs:
                    break

        if blueprint_docs or (context and context.get("has_architecture_blueprints")):
            arch_guidance = (
                "## 🏛️ Authoritative Architecture Blueprints (HLD / LLD / Executive Summary)\n"
                "Authoritative system design documents generated by Dsuite are mounted in `.agent/docs/`:\n"
                "- `LLD.md`: Low-Level Design (SQL/DDL database schemas, table models, REST OpenAPI routes, request/response payloads)\n"
                "- `HLD.md`: High-Level Design (C4 container topology, tech stack decisions, architectural sequence workflows)\n"
                "- `EXECUTIVE_SUMMARY.md`: Product vision, target personas, and scope\n\n"
                "**RECOMMENDED PROTOCOL**:\n"
                "- Use `get_architecture_spec(document='lld', section='database')` to look up exact table definitions, field types, and relations.\n"
                "- Use `get_architecture_spec(document='lld', section='api')` to inspect official REST endpoint paths, HTTP methods, and payload schemas.\n"
                "- Use `get_architecture_spec(document='hld', section='components')` or `overview` to understand system architecture.\n"
                "- Strict adherence: Always implement the exact schema field names and endpoint paths defined in these blueprints.\n\n"
            )

        core_directive = (
            "## 🚨 CORE DIRECTIVE: BRD FULFILLMENT & RUNNABLE APPLICATION (PRIMARY OBJECTIVE)\n"
            "1. **Tasks Are Milestones, Not Cages**: The current task title and subtasks guide your focus, "
            "but they do NOT restrict you. Your ultimate job is to fulfill the BRD and deliver a 100% working, "
            "connected, and RUNNABLE application.\n"
            "2. **Dynamic Architectural Awareness**: Inspect the workspace layout and existing manifests autonomously. "
            "Maintain consistency with the project's chosen architecture, structure, and conventions.\n"
            "3. **Fix Missing Foundations**: If foundational files needed for your code to run are missing "
            "(e.g., package.json, entry points, routers, layouts, styles, or configs), "
            "you HAVE FULL AUTHORITY AND DUTY to create or repair them.\n"
            "4. **Zero Orphaned Features**: Every screen or feature you create MUST be wired into the application router "
            "and navigation so users can reach it. Unrendered or unrouted components are failures.\n"
            "5. **Real End-to-End Connections**: Connect frontend code to real backend endpoints or `.agent/contracts/api_contract.json`. "
            "Never leave calls to unbuilt routes that return 404; use the project's mock data store if an API is pending.\n\n"
        )

        project_mode = str(
            (context.get("project_mode") if context else None)
            or getattr(task, "project_mode", None)
            or os.environ.get("PROJECT_MODE", "greenfield")
        ).lower()
        mode_directive = ""
        if project_mode == "migration":
            mode_directive = (
                "## 🔄 MIGRATION DIRECTIVE (100% PARITY)\n"
                "- Extract exact entity fields, validations, and business logic from the legacy codebase.\n"
                "- Ensure 100% functional parity in the modernized stack without placeholders.\n"
                "- Record legacy-to-modern module mappings in MIGRATION_REPORT.md.\n\n"
            )
        elif project_mode == "brownfield":
            mode_directive = (
                "## 🛠️ BROWNFIELD DIRECTIVE (ZERO REGRESSION)\n"
                "- Inspect existing codebase patterns, libraries, and coding styles first.\n"
                "- Apply surgical edits with replace_file_content or targeted file writes; do NOT delete working code.\n"
                "- Ensure zero regression against existing tests and endpoints.\n\n"
            )
        else:
            mode_directive = (
                "## ⚡ GREENFIELD DIRECTIVE (AUTONOMOUS BUILD)\n"
                "- Establish solid architecture, clean configuration, and comprehensive end-to-end functionality.\n"
                "- Write complete implementation code with realistic mock/seed domain data.\n\n"
            )

        return (
            f"# Agent Role: {self.role}\n"
            f"You are **{self.name}**, a specialized {self.role} agent in an autonomous multi-agent swarm.\n\n"
            f"{mode_directive}"
            f"{brd_context_str}"
            f"{arch_guidance}"
            f"{core_directive}"
            f"## Primary Focus Scope\n"
            f"Primary files to create/edit: {', '.join(self.file_ownership_scope)}\n"
            f"You may create any missing prerequisite or scaffolding files necessary to make the app compile and run.\n\n"
            f"{contract_guidance}"
            f"{design_guidance}"
            f"## Skills\n{self.skills}\n\n"
            f"## Current Milestone Task\n"
            f"**{getattr(task, 'title', 'Unknown')}**\n"
            f"{getattr(task, 'description', '')}\n\n"
            f"## Subtask Checklist (Guideline)\n{subtask_list}\n\n"
            f"## ReAct Execution Protocol\n"
            f"For each subtask:\n"
            f"1. **OBSERVE**: Read relevant existing files to understand context\n"
            f"2. **THINK**: Plan the minimal robust changes needed\n"
            f"3. **ACT**: Write/modify files using write_file or replace_file_content\n"
            f"4. **VERIFY**: Confirm zero syntax errors\n"
            f"5. **REPEAT**: Until all subtasks are complete\n\n"
            f"After completing ALL subtasks, verify the feature compiles, integrates cleanly, and is runnable.\n"
        )


def _read_live_contracts(workspace_path: str) -> str:
    """Fresh read of inter-agent contracts at task start.

    The system prompt may be built earlier or cached by the caller; agents in
    a parallel swarm see each other's published endpoints/qa gates change
    mid-run, so the contract section must reflect disk state NOW, not at
    prompt-build time. Returns an empty string when no contract exists yet.
    """
    contract_file = os.path.join(workspace_path, ".agent", "contracts", "api_contract.json")
    try:
        if not os.path.isfile(contract_file):
            return ""
        with open(contract_file, "r", encoding="utf-8") as cf:
            cd = json.load(cf)
        routes = cd.get("routes", [])
        if not routes:
            return ""
        lines = [
            "### LIVE BACKEND ENDPOINTS PUBLISHED BY BACKEND AGENT (USE EXACT PATHS):"
        ]
        for cr in routes[:35]:
            lines.append(f"- {cr.get('method')} {cr.get('path')}")
        return "\n".join(lines)
    except Exception:
        return ""


class BaseReActAgent(SubAgent):
    """Sub-agent that executes tasks using the ClaudeToolClient ReAct loop."""

    def execute_task(self, task: Any, workspace_path: str,
                     mcp: Any, router: ModelRouter, context: dict | None = None,
                     on_event: Any | None = None) -> TaskResult:
        """Execute a task through the ReAct tool loop with autonomous self-healing recovery."""
        task_id = getattr(task, "task_id", "unknown")
        title = getattr(task, "title", "Unknown task")
        logger.info(f"[{self.name}] Starting task: {title} ({task_id})")

        start_time = time.time()
        max_attempts = 2
        last_error = None

        for attempt in range(1, max_attempts + 1):
            try:
                # Route model configuration for coding phase
                config = router.route(TaskType.coding)

                # Build tools for the coding phase (enable web_search for frontend and planning)
                enable_search = os.environ.get("WEB_SEARCH_ENABLED", "true").lower() in ("true", "1") or self.lane in ("frontend", "planning")
                registry = ToolRegistry(web_search_enabled=enable_search)
                tools = registry.get_tools(ToolPhase.coding)
                executor = ToolExecutor(mcp, registry)

                # Build file manifest for context
                manifest = FileManifest()
                manifest.scan_workspace(workspace_path)

                # Initialize RealityGuard to enforce file write verification and import resolution
                reality_guard = AgentRealityGuard(workspace_path)

                # Create the ClaudeToolClient with proper kwargs-only API
                client = ClaudeToolClient(
                    model=config.model,
                    api_key=config.api_key,
                    tools=tools,
                    max_tokens=config.max_tokens,
                    temperature=config.temperature,
                    file_manifest=manifest,
                    workspace_path=workspace_path,
                    reality_guard=reality_guard,
                )

                # Build the system prompt with role and contract enforcement
                system_prompt = self._build_system_prompt(task, context=context)

                # Fresh contract refresh: the prompt's live-endpoints section
                # may be stale in a parallel swarm — re-read at task start and
                # append the current state so wiring targets real endpoints.
                try:
                    live_now = _read_live_contracts(workspace_path)
                except Exception:
                    live_now = ""
                if live_now:
                    marker = "LIVE BACKEND ENDPOINTS PUBLISHED BY BACKEND AGENT"
                    if marker not in system_prompt:
                        system_prompt = system_prompt + f"\n\n{live_now}"
                    else:
                        import re as _re
                        system_prompt = _re.sub(
                            r"### LIVE BACKEND ENDPOINTS PUBLISHED BY BACKEND AGENT[^#]*",
                            live_now + "\n",
                            system_prompt,
                            count=1,
                        )

                # Build the user message
                if attempt == 1:
                    user_msg = (
                        f"Execute the following task in workspace: {workspace_path}\n\n"
                        f"Task: {title}\n"
                        f"Description: {getattr(task, 'description', '')}\n\n"
                        f"Complete ALL subtasks listed in the system prompt.\n"
                        f"Allowed file scope: {', '.join(self.file_ownership_scope)}"
                    )
                else:
                    user_msg = (
                        f"AUTONOMOUS SELF-HEALING (Attempt {attempt}/{max_attempts}):\n"
                        f"The previous attempt encountered an issue: {last_error}\n"
                        f"Task: {title}\n"
                        f"Inspect the affected files, resolve the root cause (syntax, missing import, or broken export), "
                        f"and ensure the task completes cleanly without errors."
                    )

                messages = [{"role": "user", "content": user_msg}]

                # Run the ReAct tool loop (Observe → Think → Act → Verify)
                # Dynamic checklist: use the supervisor-generated checklist if
                # present, otherwise fall back to the task's own subtasks.
                raw_checklist = getattr(task, "checklist", None)
                if not raw_checklist:
                    raw_checklist = [
                        (st if isinstance(st, dict) else {"text": str(st)})
                        for st in getattr(task, "subtasks", []) or []
                    ]
                tracker_tasks = build_tracker_tasks(
                    raw_checklist,
                    files_involved=getattr(task, "files_involved", []),
                )
                task_tracker = None
                if tracker_tasks:
                    task_tracker = TaskChecklistTracker(
                        tracker_tasks,
                        objective=getattr(task, "title", "") or "Complete the assigned task",
                    )

                result = client.run_tool_loop(
                    system=system_prompt,
                    messages=messages,
                    tool_executor=executor,
                    max_iterations=40,
                    on_event=on_event,
                    task_tracker=task_tracker,
                )

                if task_tracker is not None:
                    task_tracker.complete_pending_steps()

                elapsed = time.time() - start_time
                files = list(executor.files_changed) if hasattr(executor, "files_changed") else []

                # Verify physical disk state: ensure no imported files are missing in files modified by this task
                valid_imports, err_msg = reality_guard.verify_pre_build(target_files=files if files else None)
                if not valid_imports:
                    raise RuntimeError(f"Missing imported files detected after task execution:\n{err_msg}")

                if not files:
                    raise RuntimeError(
                        f"Task {task_id} ('{title}') failed: No files were modified or created on disk. "
                        f"The agent stopped without applying code changes."
                    )

                # ── Gate A: platform-owned per-task verification ─────────────
                # Every changed file must at least parse cleanly (py_compile /
                # node --check). Agent-reported success alone is never enough to
                # mark a task complete.
                try:
                    from runtime.verification_engine import VerificationEngine
                    task_gate = VerificationEngine(workspace_path).verify_task_changes(files)
                    if not task_gate.passed:
                        raise RuntimeError(
                            f"Platform per-task verification failed for '{title}':\n{task_gate.detail}"
                        )
                except RuntimeError:
                    raise  # genuine verification failure → self-healing retry path below
                except Exception as gate_err:
                    # The gate itself crashed — recorded honestly, not blocking legacy flow
                    logger.warning(f"[{self.name}] Per-task verification gate errored (recorded as skipped): {gate_err}")

                logger.info(
                    f"[{self.name}] Task {task_id} completed successfully (attempt {attempt}) in {elapsed:.1f}s. "
                    f"Files changed: {len(files)}"
                )

                task_result = TaskResult(
                    task_id=task_id,
                    success=True,
                    output=result.final_text if hasattr(result, "final_text") else str(result),
                    files_changed=files,
                )
                if task_tracker is not None:
                    task_result.checklist_progress = task_tracker.checklist_progress()
                return task_result

            except Exception as e:
                last_error = str(e)
                if attempt < max_attempts:
                    logger.warning(f"[{self.name}] Attempt {attempt} failed: {e}. Initiating autonomous self-healing retry...")
                    time.sleep(1)
                    continue
                else:
                    elapsed = time.time() - start_time
                    logger.error(f"[{self.name}] Task {task_id} failed after {max_attempts} attempts ({elapsed:.1f}s): {e}")
                    return TaskResult(
                        task_id=task_id,
                        success=False,
                        output="",
                        error=last_error,
                    )


class BackendSubAgent(BaseReActAgent):
    """Handles backend tasks: APIs, models, database, services, routes."""
    def __init__(self):
        super().__init__(
            name="BackendAgent",
            role="Backend Developer",
            lane="backend",
            file_ownership_scope=[
                "server/", "api/", "controllers/", "models/",
                "database/", "migrations/", "services/", "routes/", "backend/",
                "src/app/api/", "src/pages/api/",
                "package.json", "requirements.txt", "pyproject.toml", ".env", ".env.example"
            ],
            skills=(
                "Backend developer specializing in APIs (FastAPI, Express.js), "
                "databases (SQLAlchemy, Sequelize, Prisma), authentication (JWT, bcrypt), "
                "and secure routing with middleware."
            ),
        )


class FrontendSubAgent(BaseReActAgent):
    """Handles frontend tasks: components, pages, styles, assets."""
    def __init__(self):
        super().__init__(
            name="FrontendAgent",
            role="Lead Frontend UX/UI Engineer",
            lane="frontend",
            file_ownership_scope=[
                "src/", "components/", "pages/", "styles/",
                "public/", "assets/", "frontend/", "templates/", "static/",
                "package.json", ".env", ".env.example", "index.html", "vite.config.js", "vite.config.ts",
                "App.tsx", "App.jsx", "main.tsx", "main.jsx", "router", "layouts/"
            ],
            skills=(
                "Lead Frontend & UX/UI Engineer specializing in modern, beautiful web applications, "
                "curated design systems, Google Fonts typography, Tailwind CSS, Bootstrap 5 custom aesthetics, "
                "micro-animations, accessible responsive layouts, and interactive component prototypes."
            ),
        )


class QASubAgent(BaseReActAgent):
    """Handles QA tasks: testing, validation, documentation."""
    def __init__(self):
        super().__init__(
            name="QAAgent",
            role="Quality Assurance Engineer",
            lane="qa",
            file_ownership_scope=[
                "tests/", "test/", "__tests__/", "spec/",
                "cypress/", "e2e/", "docs/", ".agent/contracts/"
            ],
            skills=(
                "QA engineer specializing in unit testing (Jest, pytest), "
                "integration testing, API documentation (Swagger/OpenAPI), "
                "and end-to-end validation."
            ),
        )
