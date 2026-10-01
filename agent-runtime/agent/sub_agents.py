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

    def _build_system_prompt(self, task: Any) -> str:
        """Build a role-specific system prompt for the ReAct loop."""
        subtask_list = ""
        for st in getattr(task, "subtasks", []):
            done_marker = "✅" if st.get("done") else "⬜"
            subtask_list += f"  {done_marker} {st.get('title', '')}\n"

        return (
            f"# Agent Role: {self.role}\n"
            f"You are **{self.name}**, a specialized {self.role} agent.\n\n"
            f"## File Ownership Scope\n"
            f"You may ONLY create/edit files within: {', '.join(self.file_ownership_scope)}\n"
            f"Do NOT modify files outside your scope.\n\n"
            f"## Skills\n{self.skills}\n\n"
            f"## Current Task\n"
            f"**{getattr(task, 'title', 'Unknown')}**\n"
            f"{getattr(task, 'description', '')}\n\n"
            f"## Subtask Checklist\n{subtask_list}\n\n"
            f"## ReAct Execution Protocol\n"
            f"For each subtask:\n"
            f"1. **OBSERVE**: Read relevant files to understand current state\n"
            f"2. **THINK**: Plan the minimal changes needed\n"
            f"3. **ACT**: Write/modify files using write_file or replace_file_content\n"
            f"4. **VERIFY**: Run check_syntax or execute build to confirm zero errors\n"
            f"5. **REPEAT**: Until all subtasks are complete\n\n"
            f"After completing ALL subtasks, output a summary of what was done.\n"
        )


class BaseReActAgent(SubAgent):
    """Sub-agent that executes tasks using the ClaudeToolClient ReAct loop."""

    def execute_task(self, task: Any, workspace_path: str,
                     mcp: Any, router: ModelRouter) -> TaskResult:
        """Execute a task through the ReAct tool loop."""
        task_id = getattr(task, "task_id", "unknown")
        title = getattr(task, "title", "Unknown task")
        logger.info(f"[{self.name}] Starting task: {title} ({task_id})")

        start_time = time.time()

        try:
            # Route model configuration for coding phase
            config = router.route(TaskType.coding)

            # Build tools for the coding phase
            registry = ToolRegistry(web_search_enabled=False)
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

            # Build the system prompt with role enforcement
            system_prompt = self._build_system_prompt(task)

            # Build the user message
            user_msg = (
                f"Execute the following task in workspace: {workspace_path}\n\n"
                f"Task: {title}\n"
                f"Description: {getattr(task, 'description', '')}\n\n"
                f"Complete ALL subtasks listed in the system prompt.\n"
                f"IMPORTANT: Only modify files within your ownership scope: "
                f"{', '.join(self.file_ownership_scope)}"
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
                f"[{self.name}] Task {task_id} completed in {elapsed:.1f}s. "
                f"Files changed: {len(files)}"
            )

            return TaskResult(
                task_id=task_id,
                success=True,
                output=result.final_text if hasattr(result, "final_text") else str(result),
                files_changed=files,
            )

        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"[{self.name}] Task {task_id} failed after {elapsed:.1f}s: {e}")
            return TaskResult(
                task_id=task_id,
                success=False,
                output="",
                error=str(e),
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
                "database/", "migrations/", "services/", "routes/", "backend/"
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
            role="Frontend Developer",
            lane="frontend",
            file_ownership_scope=[
                "src/", "components/", "pages/", "styles/",
                "public/", "assets/", "frontend/"
            ],
            skills=(
                "Frontend developer specializing in React, Vue, Angular, "
                "Tailwind CSS, Material-UI, responsive design, and SPA architecture."
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
                "cypress/", "e2e/", "docs/"
            ],
            skills=(
                "QA engineer specializing in unit testing (Jest, pytest), "
                "integration testing, API documentation (Swagger/OpenAPI), "
                "and end-to-end validation."
            ),
        )
