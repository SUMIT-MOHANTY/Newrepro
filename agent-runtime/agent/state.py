"""AgentState — In-memory state and typed schemas for the Vibecoding Agent Runtime.

Contains:
1. Plan and PlanStep data structures
2. Legacy AgentState dataclass (loaded from container environment variables)
3. LangGraphState TypedDict (used by the LangGraph StateGraph engine)
"""
from __future__ import annotations

import dataclasses
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional, TypedDict


@dataclass
class PlanStep:
    """One step of the AI's implementation plan."""
    step_number: int
    action: str                        # e.g. "create_component", "install_deps", "build"
    description: str
    files_involved: list[str]          # workspace-relative paths the step will touch
    status: str = "pending"           # pending | in_progress | completed | failed
    result_summary: str | None = None  # set after step executes

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_number": self.step_number,
            "action": self.action,
            "description": self.description,
            "files_involved": self.files_involved,
            "status": self.status,
            "result_summary": self.result_summary,
        }


@dataclass
class Plan:
    """The structured plan produced by Planner.create_plan()."""
    title: str
    project_type: str                  # e.g. "react_vite", "static_html"
    steps: list[PlanStep] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def total_steps(self) -> int:
        return len(self.steps)

    @property
    def completed_steps(self) -> int:
        return sum(1 for s in self.steps if s.status == "completed")

    def current_step(self) -> PlanStep | None:
        for step in self.steps:
            if step.status == "pending":
                return step
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "project_type": self.project_type,
            "steps": [s.to_dict() for s in self.steps],
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class StepResult:
    """Result from Coder.execute_step()."""
    success: bool
    files_changed: list[str] = field(default_factory=list)
    error: str | None = None
    raw_llm_output: str | None = None


@dataclass
class ReviewResult:
    """Result from Reviewer.review()."""
    approved: bool
    issues: list[str] = field(default_factory=list)
    suggested_fixes: str | None = None


@dataclass
class AgentState:
    """Complete runtime state for one agent session (dataclass for container runtime)."""
    session_id: str
    task_id: str
    task_type: str                     # AgentTaskType value from the DB
    prompt: str                        # The user's raw prompt text
    workspace_path: str                # Absolute path to /workspace
    project_id: str
    tenant_id: str
    callback_url: str                  # FastAPI endpoint to post events to
    callback_secret: str               # Shared HMAC secret for callback auth

    # Model configuration
    model_name: str = "claude"         # Specific model: claude, kimi, deepseek, etc.
    model_provider: str = "anthropic"  # "anthropic" for Claude
    tool_use_enabled: bool = True      # Use Claude's native tool-use API
    web_search_enabled: bool = False   # Enable web search for mock data research
    github_repo_url: str | None = None # Optional GitHub repo for context

    # Runtime state — mutated by the orchestrator as execution progresses
    conversation_history: list[dict[str, Any]] = field(default_factory=list)
    plan: Plan | None = None
    current_step_index: int = 0
    retry_count: int = 0               # retries on current step
    build_attempts: int = 0
    preview_url: str | None = None
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # Tool-use tracking
    tool_call_count: int = 0           # total tool calls in this session
    max_tool_calls: int = 50           # safety limit
    files_changed: list[str] = field(default_factory=list)  # accumulated file changes
    built_in_tool_loop: bool = False   # True only if build ran successfully AFTER the last file edit

    # Limits (read from resource_limits, set at init)
    max_step_retries: int = 2
    max_build_attempts: int = 6

    def add_to_history(self, role: str, content: str) -> None:
        """Append a message to the conversation history."""
        self.conversation_history.append({"role": role, "content": content})

    def mark_step_done(self, step_index: int, summary: str) -> None:
        if self.plan and 0 <= step_index < len(self.plan.steps):
            self.plan.steps[step_index].status = "completed"
            self.plan.steps[step_index].result_summary = summary

    def mark_step_failed(self, step_index: int, error: str) -> None:
        if self.plan and 0 <= step_index < len(self.plan.steps):
            self.plan.steps[step_index].status = "failed"
            self.plan.steps[step_index].result_summary = error

    def reset_retry_count(self) -> None:
        self.retry_count = 0

    def track_file_change(self, path: str) -> None:
        """Record a file that was created or modified."""
        if path not in self.files_changed:
            self.files_changed.append(path)

    @classmethod
    def from_env(cls) -> "AgentState":
        """Build state from container environment variables."""
        return cls(
            session_id=os.environ.get("SESSION_ID", "local-session"),
            task_id=os.environ.get("TASK_ID", "local-task"),
            task_type=os.environ.get("TASK_TYPE", "initial_generation"),
            prompt=os.environ.get("PROMPT", ""),
            workspace_path=os.environ.get("WORKSPACE_PATH", "/workspace"),
            project_id=os.environ.get("PROJECT_ID", "default-proj"),
            tenant_id=os.environ.get("TENANT_ID", "default-tenant"),
            callback_url=os.environ.get("CALLBACK_URL", "http://localhost:8000/callback"),
            callback_secret=os.environ.get("CALLBACK_SECRET", "secret"),
            model_name=os.environ.get("AI_MODEL") or os.environ.get("MODEL_NAME", "claude"),
            model_provider=os.environ.get("MODEL_PROVIDER", "anthropic"),
            tool_use_enabled=os.environ.get("TOOL_USE_ENABLED", "true").lower() == "true",
            web_search_enabled=os.environ.get("WEB_SEARCH_ENABLED", "false").lower() == "true",
            github_repo_url=os.environ.get("GIT_REPO_URL") or os.environ.get("GITHUB_REPO_URL") or None,
            max_tool_calls=int(os.environ.get("MAX_TOOL_CALLS", "50")),
        )


# ════════════════════════════════════════════════════════════════════════════
# LangGraph State Schema
# ════════════════════════════════════════════════════════════════════════════

class LangGraphState(TypedDict, total=False):
    """The authoritative state dictionary passed between LangGraph nodes."""

    # Core session metadata
    session_id: str
    task_id: str
    prompt: str
    workspace_path: str
    task_type: str
    model_name: str

    # Living Product Spec (product_spec.json)
    spec: dict[str, Any]

    # Tech stack detection & scaffolding
    techstack: Optional[dict[str, Any]]

    # Analysis & Plan artifacts
    analysis_summary: Optional[str]
    plan_data: Optional[dict[str, Any]]
    plan_text: Optional[str]
    ast_dependency_graph: Optional[dict[str, Any]]

    # Phased generation contract summaries
    data_exports_summary: Optional[str]
    component_exports_summary: Optional[str]

    # Conversation & Code modification state
    messages: list[dict[str, Any]]
    files_changed: list[str]
    file_manifest: dict[str, Any]

    # Build verification & self-healing state
    build_success: bool
    build_error: Optional[str]
    fix_attempts: int
    preview_url: Optional[str]

    # Backend lifecycle (detected port + health after self-heal)
    backend_port: Optional[int]
    backend_healthy: Optional[bool]

    # Lifecycle status
    final_text: str
    status: str  # "initialized", "analyzing", "planning", "coding", "verifying", "fixing", "completed", "failed"
    error: Optional[str]


def parse_plan_from_text(raw: str) -> Plan:
    """Parse an LLM's plan response (JSON or formatted text) into a Plan dataclass."""
    import json
    import re

    data = None

    # Strategy 1: Strip markdown code fences and parse
    cleaned = re.sub(r"```(?:json)?\s*", "", raw).strip()
    try:
        data = json.loads(cleaned)
    except (json.JSONDecodeError, ValueError):
        pass

    # Strategy 2: Find JSON object in the text
    if data is None:
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end > start:
            try:
                data = json.loads(raw[start:end + 1])
            except (json.JSONDecodeError, ValueError):
                pass

    # Strategy 3: Extract from ```json ... ``` blocks
    if data is None:
        json_match = re.search(r"```json\s*(\{.*?\})\s*```", raw, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group(1))
            except (json.JSONDecodeError, ValueError):
                pass

    # Strategy 4: Extract steps from text-based plans
    if data is None:
        steps = []
        for m in re.finditer(
            r"(?:^|\n)\s*(?:\d+\.\s*|Step\s+\d+[:\s]\s*|[-*]\s*)(.+)",
            raw,
        ):
            desc = m.group(1).strip()
            if len(desc) > 10:
                file_matches = re.findall(r"`([^`]+\.\w+)`", desc)
                steps.append({
                    "description": desc[:200],
                    "files_involved": file_matches[:5],
                })
        if steps:
            return Plan(
                title="Generated Application",
                project_type="react_vite",
                steps=[
                    PlanStep(
                        step_number=i + 1,
                        action="create_component",
                        description=s["description"],
                        files_involved=s["files_involved"],
                    )
                    for i, s in enumerate(steps[:15])
                ],
            )

    if data is None:
        return Plan(
            title="Generated Application",
            project_type="react_vite",
            steps=[
                PlanStep(
                    step_number=1,
                    action="create_component",
                    description="Build the application based on user requirements",
                    files_involved=[],
                ),
            ],
        )

    return Plan(
        title=data.get("title", "Generated Application"),
        project_type=data.get("project_type", "react_vite"),
        steps=[
            PlanStep(
                step_number=s.get("step_number", i + 1),
                action=s.get("action", "create_component"),
                description=s.get("description", "Create component"),
                files_involved=s.get("files_involved", []),
            )
            for i, s in enumerate(data.get("steps", []))
        ],
    )

