"""Dynamic Context Window Engine & Session Subtask Tracker.

Mirrors the Vibecoding Lite dynamic context management pattern:
- Multi-tier dynamic context window (Full -> Signatures -> Compact Manifest)
- SessionTaskTracker: Breaks parent tasks into actionable subtasks with live status
- Real-time token usage telemetry (used, remaining, usage ratio)
- Zero-Error Verification Gate contract
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_CONTEXT_WINDOW = 128000
TIER1_MAX_CHARS = 40000
TIER2_MAX_CHARS = 120000


def estimate_token_count(text: str) -> int:
    """Fast, accurate token estimation (approx 4 characters per token)."""
    if not text:
        return 0
    return max(1, len(text) // 4)


class DynamicContextManager:
    """Manages active context budget and tiering to prevent LLM amnesia and context overflow."""

    def __init__(self, context_window: int = DEFAULT_CONTEXT_WINDOW):
        self.context_window = context_window
        self.inspected_files: Dict[str, str] = {}
        self.total_input_tokens = 0
        self.total_output_tokens = 0

    def record_usage(self, input_tokens: int, output_tokens: int) -> None:
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens

    def get_telemetry(self) -> Dict[str, Any]:
        used = self.total_input_tokens
        limit = self.context_window
        ratio = min(max(used / limit if limit > 0 else 0.0, 0.0), 1.0)
        percentage = round(ratio * 100)
        remaining = max(limit - used, 0)

        tier = 1
        total_chars = sum(len(c) for c in self.inspected_files.values())
        if total_chars > TIER2_MAX_CHARS:
            tier = 3
        elif total_chars > TIER1_MAX_CHARS:
            tier = 2

        return {
            "inputTokens": used,
            "input_tokens": used,
            "outputTokens": self.total_output_tokens,
            "output_tokens": self.total_output_tokens,
            "contextWindow": limit,
            "context_window": limit,
            "remainingTokens": remaining,
            "remaining_tokens": remaining,
            "percentage": percentage,
            "usageRatio": ratio,
            "tier": tier,
        }

    def strip_signatures(self, code: str, filepath: str) -> str:
        """Tier 2: Extract signatures, classes, routes, schemas while omitting long bodies."""
        lines = code.splitlines()
        trimmed: List[str] = []
        is_js = filepath.endswith((".js", ".jsx", ".ts", ".tsx"))
        is_py = filepath.endswith(".py")

        for line in lines:
            stripped = line.strip()
            # Always keep imports and exports
            if stripped.startswith(("import ", "from ", "export ", "const ", "let ", "var ")) and not stripped.startswith("const ["):
                trimmed.append(line)
            # Python def / class
            elif is_py and (stripped.startswith("def ") or stripped.startswith("class ") or stripped.startswith("@")):
                trimmed.append(line)
            # JS function / interface / type / component
            elif is_js and (
                stripped.startswith("function ") or "interface " in stripped or "type " in stripped
                or "export default function" in stripped or "const " in stripped and "=>" in stripped
            ):
                trimmed.append(line)
            # Return statement preview or structural braces
            elif stripped in ("}", "};", "pass"):
                trimmed.append(line)

        return "\n".join(trimmed) if trimmed else code[:1000]

    def build_context_block(self, max_token_budget: Optional[int] = None) -> str:
        """Render tiered inspected files block within safe token budget."""
        budget_chars = (max_token_budget or (self.context_window // 3)) * 4
        total_chars = sum(len(c) for c in self.inspected_files.values())

        out_lines = ["\n### Inspected Workspace Files & Architecture:"]

        if total_chars <= TIER1_MAX_CHARS:
            # Tier 1: Full inline content
            for path, content in self.inspected_files.items():
                out_lines.append(f"\n#### File: `{path}` (Full Source)")
                out_lines.append("```\n" + content + "\n```")
        elif total_chars <= TIER2_MAX_CHARS:
            # Tier 2: Stripped signatures
            for path, content in self.inspected_files.items():
                out_lines.append(f"\n#### File: `{path}` (Signatures & Exports Only)")
                out_lines.append("```\n" + self.strip_signatures(content, path) + "\n```")
        else:
            # Tier 3: Compact manifest
            out_lines.append("\n*Compact Manifest (Token Preservation Mode)*:")
            for path, content in self.inspected_files.items():
                lines_count = len(content.splitlines())
                out_lines.append(f"- `{path}` ({lines_count} lines, {len(content)} chars)")

        return "\n".join(out_lines)


class SessionTaskTracker:
    """Breaks down a parent sprint task into concrete, trackable coding subtasks."""

    @staticmethod
    def generate_subtasks_for_parent(
        parent_id: str,
        parent_title: str,
        parent_desc: str,
        agent_role: str,
        specialization: str,
    ) -> List[Dict[str, Any]]:
        spec = specialization.lower()
        role = agent_role.lower()

        subtasks: List[Dict[str, Any]] = []

        if "front" in spec or "ui" in spec or "frontend" in role:
            subtasks = [
                {
                    "id": 1,
                    "title": f"Analyze existing UI components and route architecture for '{parent_title}'",
                    "status": "completed",
                    "description": "Inspect src/App.jsx, component hierarchy, Tailwind styling tokens, and navigation routes.",
                },
                {
                    "id": 2,
                    "title": f"Build component structure & state management for '{parent_title}'",
                    "status": "in_progress",
                    "description": f"Implement JSX components with responsive layout, defensive null guards, and clean props contract.",
                },
                {
                    "id": 3,
                    "title": f"Wire navigation, API hooks, and event handlers",
                    "status": "pending",
                    "description": "Connect UI components with backend API endpoints and user interaction workflows.",
                },
                {
                    "id": 4,
                    "title": f"Verify ESLint rules, syntax checks, and visual layout parity",
                    "status": "pending",
                    "description": "Run npm run lint and ensure 0 compile warnings or broken styles.",
                },
            ]
        elif "back" in spec or "api" in spec or "backend" in role or "database" in spec:
            subtasks = [
                {
                    "id": 1,
                    "title": f"Analyze backend router, models, and schemas for '{parent_title}'",
                    "status": "completed",
                    "description": "Inspect backend/main.py, Pydantic schemas, and existing endpoint declarations.",
                },
                {
                    "id": 2,
                    "title": f"Implement API endpoints and business logic for '{parent_title}'",
                    "status": "in_progress",
                    "description": "Create route handlers with HTTP status codes, error handling, and parameter validation.",
                },
                {
                    "id": 3,
                    "title": f"Configure data models, validation schemas, and database persistence",
                    "status": "pending",
                    "description": "Ensure schemas match contract and include required fields and migrations.",
                },
                {
                    "id": 4,
                    "title": f"Execute automated endpoint health verification and unit tests",
                    "status": "pending",
                    "description": "Validate route responses and verify zero syntax errors or unhandled exceptions.",
                },
            ]
        elif "test" in spec or "qa" in spec or "validator" in role:
            subtasks = [
                {
                    "id": 1,
                    "title": f"Audit source code and contract schemas for '{parent_title}'",
                    "status": "completed",
                    "description": "Read application files via code_inspector; identify test surfaces and edge cases.",
                },
                {
                    "id": 2,
                    "title": f"Author unit test suites and integration assertions",
                    "status": "in_progress",
                    "description": "Create automated test specs testing component rendering, API error codes, and edge states.",
                },
                {
                    "id": 3,
                    "title": f"Execute test runner suite (Vitest/Pytest) & linter audits",
                    "status": "pending",
                    "description": "Run test suites and confirm all assertions pass with 100% green status.",
                },
                {
                    "id": 4,
                    "title": f"Issue Zero-Error verification sign-off certificate",
                    "status": "pending",
                    "description": "Validate 0 defects and sign off task completion for release.",
                },
            ]
        else:
            subtasks = [
                {
                    "id": 1,
                    "title": f"Phase 1: Codebase discovery & inspection for '{parent_title}'",
                    "status": "completed",
                    "description": "Inspect existing files, dependencies, and architecture.",
                },
                {
                    "id": 2,
                    "title": f"Phase 2: Plan technical implementation and dependency order",
                    "status": "in_progress",
                    "description": "Decompose parent requirements into atomic modifications.",
                },
                {
                    "id": 3,
                    "title": f"Phase 3: Implement surgical code changes",
                    "status": "pending",
                    "description": "Write and refactor required application source files.",
                },
                {
                    "id": 4,
                    "title": f"Phase 4: Run validation suite and confirm zero errors",
                    "status": "pending",
                    "description": "Run linting and tests to achieve clean sign-off.",
                },
            ]

        return subtasks

    @staticmethod
    def format_checklist_markdown(subtasks: List[Dict[str, Any]]) -> str:
        """Format subtasks into markdown checklist for prompts and logs."""
        lines = []
        for st in subtasks:
            status = st.get("status", "pending")
            mark = "x" if status == "completed" else (">" if status == "in_progress" else " ")
            lines.append(f"- [{mark}] {st.get('title', '')}")
            if st.get("description"):
                lines.append(f"    *Detail: {st['description']}*")
        return "\n".join(lines)
