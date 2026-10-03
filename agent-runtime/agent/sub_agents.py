"""Sub-Agent definitions for the Supervisor Agent architecture.

Architecture: Each sub-agent owns a specific lane (backend, frontend, qa)
and runs an independent ReAct tool loop to complete its assigned task.
Sub-agents are isolated by file_ownership_scope — they can only modify
files within their designated directories.

Uses the existing ClaudeToolClient.run_tool_loop() for the ReAct loop.
"""
from __future__ import annotations

import logging
import os
import time
from abc import ABC, abstractmethod
from typing import Any, List

from infrastructure.claude_tool_client import ClaudeToolClient, FileManifest
from agent.model_router import ModelRouter, TaskType
from agent.tools.tool_registry import ToolRegistry, ToolPhase
from agent.tools.tool_executor import ToolExecutor

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
                     mcp: Any, router: ModelRouter) -> TaskResult:
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
        if self.lane == "frontend":
            contract_guidance = (
                "## Inter-Agent API Contract\n"
                "Backend APIs publish verified schemas to `.agent/contracts/api_contract.json`.\n"
                "Inspect `.agent/contracts/api_contract.json` (or read backend models/routes) to discover the "
                "exact HTTP endpoints, methods, and payload structures before wiring API calls.\n\n"
            )
        elif self.lane == "backend":
            contract_guidance = (
                "## Inter-Agent API Contract\n"
                "Design clean, RESTful endpoints with consistent request/response schemas so the Frontend Agent "
                "can seamlessly integrate with them.\n\n"
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

        return (
            f"# Agent Role: {self.role}\n"
            f"You are **{self.name}**, a specialized {self.role} agent in an autonomous multi-agent swarm.\n\n"
            f"{brd_context_str}"
            f"## File Ownership Scope\n"
            f"You may create/edit files within: {', '.join(self.file_ownership_scope)}\n"
            f"Do NOT overwrite or delete components outside your scope.\n\n"
            f"{contract_guidance}"
            f"{design_guidance}"
            f"## Skills\n{self.skills}\n\n"
            f"## Current Task\n"
            f"**{getattr(task, 'title', 'Unknown')}**\n"
            f"{getattr(task, 'description', '')}\n\n"
            f"## Subtask Checklist\n{subtask_list}\n\n"
            f"## ReAct Execution Protocol\n"
            f"For each subtask:\n"
            f"1. **OBSERVE**: Read relevant existing files to understand context\n"
            f"2. **THINK**: Plan the minimal robust changes needed\n"
            f"3. **ACT**: Write/modify files using write_file or replace_file_content\n"
            f"4. **VERIFY**: Confirm zero syntax errors\n"
            f"5. **REPEAT**: Until all subtasks are complete\n\n"
            f"After completing ALL subtasks, output a concise summary of what was done.\n"
        )


class BaseReActAgent(SubAgent):
    """Sub-agent that executes tasks using the ClaudeToolClient ReAct loop."""

    def execute_task(self, task: Any, workspace_path: str,
                     mcp: Any, router: ModelRouter, context: dict | None = None) -> TaskResult:
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

                # Create the ClaudeToolClient with proper kwargs-only API
                client = ClaudeToolClient(
                    model=config.model,
                    api_key=config.api_key,
                    tools=tools,
                    max_tokens=config.max_tokens,
                    temperature=config.temperature,
                    file_manifest=manifest,
                    workspace_path=workspace_path,
                )

                # Build the system prompt with role and contract enforcement
                system_prompt = self._build_system_prompt(task, context=context)

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
                result = client.run_tool_loop(
                    system=system_prompt,
                    messages=messages,
                    tool_executor=executor,
                    max_iterations=40,
                )

                elapsed = time.time() - start_time
                files = list(executor.files_changed) if hasattr(executor, "files_changed") else []

                logger.info(
                    f"[{self.name}] Task {task_id} completed successfully (attempt {attempt}) in {elapsed:.1f}s. "
                    f"Files changed: {len(files)}"
                )

                return TaskResult(
                    task_id=task_id,
                    success=True,
                    output=result.final_text if hasattr(result, "final_text") else str(result),
                    files_changed=files,
                )

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
                "package.json", ".env", ".env.example", "index.html", "vite.config.js", "vite.config.ts"
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
