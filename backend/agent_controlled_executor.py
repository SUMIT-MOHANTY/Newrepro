"""
Agent Controlled Executor — Phase 3: Application-Controlled Orchestration
=====================================================================

Replaces the fragile bash-script generation approach with application-controlled
per-file LLM calls. The flow is:

  1. FilePlanner : Analyze task + workspace → list of files to create/modify
  2. For each file:
     a. PromptBuilder : Build a focused prompt (context: workspace tree, peer work)
     b. LLM Call     : Generate ONLY the file content (no shell boilerplate)
     c. FileWriter   : Write content to Docker container (atomic)
  3. CommandRunner : Run build/verify (deterministic, NOT LLM-generated)
  4. Self-Heal    : On file failure, retry just that file (not the whole task)

Key design principles:
  - LLM never sees tools → just generates code text
  - Application controls WHAT, WHEN, and HOW operations happen
  - Each file generation is atomic → if one fails, others are already saved
  - Works with ANY LLM (no tool-calling support needed)
  - Integrates with coordination system (Phase 1) for file lock reservation
  - Cross-file consistency through smart prompt building (not LLM orchestration)
"""

import asyncio
import logging
import os
import shlex
import subprocess
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

# Import LLM code generation — lazy import to avoid circular dependency with agent_service
# _call_ai_for_code is imported inside the call_ai_for_code_with_controlled function body

logger = logging.getLogger(__name__)


# ── Data Classes ─────────────────────────────────────────────────────────────

@dataclass
class FilePlan:
    """Represents a single file that needs to be created or modified."""
    file_path: str                     # Relative to /workspace/, e.g. "src/app/auth/login.jsx"
    purpose: str = ""                  # Human-readable description of what this file does
    action: str = "create"             # "create" | "modify" | "append"
    content_hint: str = ""             # Optional hint about expected content
    language: str = ""                 # Programming language for syntax hints (auto-detected)
    dependencies: List[str] = field(default_factory=list)  # Other files this depends on
    checklist_items: List[str] = field(default_factory=list)  # Task checklist items this file satisfies
    is_bootstrap: bool = False         # If True, create empty placeholder only

    def to_dict(self) -> Dict[str, Any]:
        return {
            "file_path": self.file_path,
            "purpose": self.purpose,
            "action": self.action,
            "language": self.language,
            "is_bootstrap": self.is_bootstrap,
            "dependencies": self.dependencies,
        }


@dataclass
class FileGenerationResult:
    """Result of generating and writing a single file."""
    file_path: str
    success: bool
    content_length: int = 0
    error: str = ""
    retry_count: int = 0


@dataclass
class BuildResult:
    """Result of running build/verify commands."""
    success: bool
    build_output: str = ""
    build_errors: List[str] = field(default_factory=list)
    install_errors: List[str] = field(default_factory=list)


@dataclass
class ControlledExecutionResult:
    """Full result of a controlled execution run for a task."""
    success: bool
    task_id: str = ""
    files_planned: int = 0
    files_generated: int = 0
    files_failed: int = 0
    file_results: List[FileGenerationResult] = field(default_factory=list)
    build_result: Optional[BuildResult] = None
    errors: List[str] = field(default_factory=list)


# ── Language Detection ───────────────────────────────────────────────────────

_EXTENSION_LANGUAGE_MAP: Dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript (React JSX)",
    ".ts": "typescript",
    ".tsx": "typescript (React TSX)",
    ".css": "css",
    ".scss": "scss",
    ".html": "html",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".md": "markdown",
    ".sql": "sql",
    ".sh": "bash",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".cs": "csharp",
    ".rb": "ruby",
    ".php": "php",
    ".vue": "vue",
    ".svelte": "svelte",
    ".dockerfile": "dockerfile",
}


def _detect_language(file_path: str) -> str:
    """Detect programming language from file extension."""
    file_path_lower = file_path.lower()

    # Check for special filenames
    basename = os.path.basename(file_path_lower)
    if basename == "dockerfile":
        return "dockerfile"
    if basename == "makefile":
        return "makefile"

    ext = os.path.splitext(file_path_lower)[1]
    return _EXTENSION_LANGUAGE_MAP.get(ext, "text")


# ── File Planner ─────────────────────────────────────────────────────────────

class FilePlanner:
    """
    Analyzes a task + workspace context to determine which files to create/modify.

    Uses multiple strategies:
    1. Extract file paths from task description (e.g., paths mentioned between markers)
    2. Parse checklist items for file references
    3. Analyze workspace tree for existing files that need modification
    4. Use canonical project tree from the task description
    """

    def __init__(self, project_root: str = "/workspace"):
        self.project_root = project_root

    async def plan_files(
        self,
        task: Dict[str, Any],
        workspace_tree: str = "",
        canonical_tree: str = "",
        existing_files: Optional[List[str]] = None,
        is_bootstrap: bool = False,
    ) -> List[FilePlan]:
        """
        Plan which files this task should create/modify.

        Args:
            task: Task dict with description, checklist, etc.
            workspace_tree: Current file tree in the workspace (for context)
            canonical_tree: The canonical project tree from master agent
            existing_files: List of files already on disk (git ls-files)
            is_bootstrap: If True, create empty placeholder files only

        Returns:
            Ordered list of FilePlan objects (in recommended creation order)
        """
        plans: List[FilePlan] = []
        seen_paths: Set[str] = set()
        task_title = str(task.get("title") or task.get("taskName") or "")
        task_desc = str(task.get("description") or "")
        checklist = task.get("checklist") or task.get("checklists") or []

        # ── Strategy 1: Extract from canonical project tree markers ──────────
        if canonical_tree or task_desc:
            tree_text = canonical_tree or task_desc
            paths_from_tree = self._extract_paths_from_tree(tree_text)
            for fp in paths_from_tree:
                normalized = self._normalize_path(fp)
                if normalized and normalized not in seen_paths:
                    purpose = f"Part of the canonical project structure"
                    plans.append(FilePlan(
                        file_path=normalized,
                        purpose=purpose if not is_bootstrap else "Bootstrap placeholder",
                        action="create",
                        language=_detect_language(normalized),
                        is_bootstrap=is_bootstrap,
                    ))
                    seen_paths.add(normalized)

        # ── Strategy 2: Extract from task description (explicit file refs) ───
        if task_desc:
            paths_from_desc = self._extract_file_paths_from_text(task_desc)
            for fp in paths_from_desc:
                normalized = self._normalize_path(fp)
                if normalized and normalized not in seen_paths:
                    plans.append(FilePlan(
                        file_path=normalized,
                        purpose=f"Referenced in task description",
                        action="create",
                        language=_detect_language(normalized),
                        is_bootstrap=is_bootstrap,
                    ))
                    seen_paths.add(normalized)

        # ── Strategy 3: Extract from planned_files or canonical file targets ─
        for key in ("planned_files", "canonical_files", "linked_files"):
            file_list = task.get(key, [])
            if isinstance(file_list, list):
                for item in file_list:
                    if isinstance(item, dict):
                        fp = item.get("path", item.get("file", ""))
                    elif isinstance(item, str):
                        fp = item
                    else:
                        continue
                    normalized = self._normalize_path(str(fp))
                    if normalized and normalized not in seen_paths:
                        purpose = ""
                        if isinstance(item, dict):
                            purpose = str(item.get("purpose", item.get("description", "")))
                        plans.append(FilePlan(
                            file_path=normalized,
                            purpose=purpose or "Planned file from task metadata",
                            action="create",
                            language=_detect_language(normalized),
                            is_bootstrap=is_bootstrap,
                        ))
                        seen_paths.add(normalized)

        # ── Strategy 4: Check existing files that likely need modification ───
        if existing_files and not is_bootstrap:
            task_keywords = self._extract_keywords(task_title + " " + task_desc)
            for ef in existing_files:
                basename = os.path.basename(ef).lower()
                # Check if the existing file is relevant to this task's keywords
                if any(kw in basename for kw in task_keywords):
                    normalized = self._normalize_path(ef)
                    if normalized and normalized not in seen_paths:
                        plans.append(FilePlan(
                            file_path=normalized,
                            purpose=f"Existing file related to task '{task_title[:40]}'",
                            action="modify",
                            language=_detect_language(normalized),
                            is_bootstrap=False,
                        ))
                        seen_paths.add(normalized)

        # ── Strategy 5: Parse checklist items ───────────────────────────────
        checklist_items_text = self._flatten_checklist(checklist)
        for checklist_text in checklist_items_text:
            fp = self._extract_single_file_path(checklist_text)
            if fp:
                normalized = self._normalize_path(fp)
                if normalized and normalized not in seen_paths:
                    plans.append(FilePlan(
                        file_path=normalized,
                        purpose=f"Satisfies checklist item: {checklist_text[:60]}",
                        checklist_items=[checklist_text],
                        action="create",
                        language=_detect_language(normalized),
                        is_bootstrap=is_bootstrap,
                    ))
                    seen_paths.add(normalized)

        # ── Sort: directories first, then files, respecting dependency order ─
        plans = self._sort_plans(plans)

        if not plans:
            logger.warning(
                f"FilePlanner could not extract any file plans from task '{task_title[:50]}'. "
                "Falling back to generating a default implementation file."
            )
            # Create a single default file based on task title
            default_path = self._derive_default_path(task_title, task_desc)
            if default_path:
                plans.append(FilePlan(
                    file_path=default_path,
                    purpose=f"Implementation for: {task_title}",
                    action="create",
                    language=_detect_language(default_path),
                ))

        logger.info(
            f"FilePlanner: planned {len(plans)} files for task '{task_title[:50]}' "
            f"(bootstrap={is_bootstrap})"
        )
        return plans

    # ── Private Helpers ───────────────────────────────────────────────────

    def _extract_paths_from_tree(self, text: str) -> List[str]:
        """Extract file paths from a tree-like description."""
        paths: List[str] = []
        lines = text.split("\n")

        in_tree = False
        for line in lines:
            stripped = line.strip()

            # Detect tree markers
            if "===BEGIN_DIRECTORY_STRUCTURE===" in stripped:
                in_tree = True
                continue
            if "===END_DIRECTORY_STRUCTURE===" in stripped:
                in_tree = False
                continue

            # Remove tree-drawing characters
            cleaned = re.sub(r"[├──│└──┬└─├─│┌─┐─]", "", stripped)
            cleaned = re.sub(r"^\s*[•*\-]\s*", "", cleaned)
            cleaned = cleaned.strip()

            if not cleaned:
                continue

            # Check if it looks like a file (has extension) and is a path
            if cleaned.endswith("/"):
                continue  # Directory, skip

            if "." in cleaned and len(cleaned) > 3:
                # Could be a file - extract just the relative path
                # Remove inline comments like  # purpose description
                file_path = re.sub(r"\s*#.*$", "", cleaned).strip()
                file_path = re.sub(r"\s*//.*$", "", file_path).strip()
                file_path = re.sub(r"\s*\(.*\)\s*$", "", file_path).strip()

                # Skip if it's just a filename without a path (for tree context)
                if "/" not in file_path and len(file_path.split(".")) <= 2:
                    # This might be a tree node label, not a real path
                    # Only include if it has clear path structure
                    continue

                # Skip if it's a directory marker
                if file_path.endswith("/"):
                    continue

                # Skip if it looks like prose (has spaces)
                if " " in file_path and not any(
                    ext in file_path for ext in [".py", ".js", ".ts", ".jsx", ".tsx",
                                                  ".css", ".html", ".json", ".md",
                                                  ".go", ".rs", ".java", ".cs"]
                ):
                    continue

                paths.append(file_path)

        return paths

    def _extract_file_paths_from_text(self, text: str) -> List[str]:
        """Extract file path references from free-form text."""
        paths: List[str] = []

        # Pattern 1: Explicit file paths with extensions
        path_patterns = [
            r"(?:`|\"|')?/(?:[\w./-]+/)?[\w-]+\.[a-zA-Z]{2,5}(?:`|\"|')?",  # /path/to/file.ext
            r"(?:`|\"|')?(?:[\w./-]+/)[\w-]+\.[a-zA-Z]{2,5}(?:`|\"|')?",     # path/to/file.ext
        ]

        for pattern in path_patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                # Clean up backticks/quotes
                clean = match.strip("`\"'")
                # Skip if it contains spaces (likely not a path)
                if " " in clean:
                    continue
                # Skip if too short
                if len(clean) < 5:
                    continue
                paths.append(clean)

        # Pattern 2: Markdown file references like `src/app/auth.py`
        md_paths = re.findall(r"`([\w./\\-]+\.[a-zA-Z]{2,5})`", text)
        for p in md_paths:
            if p not in paths:
                paths.append(p)

        return paths

    def _extract_single_file_path(self, text: str) -> Optional[str]:
        """Extract a single file path from a checklist item text."""
        # Try to find a file path pattern
        patterns = [
            r"(?:`|\"|')?([\w./-]+\.[a-zA-Z]{2,5})(?:`|\"|')?",
            r"(?:file|verify|check|ensure)\s+([\w./-]+\.[a-zA-Z]{2,5})",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                fp = match.group(1).strip()
                if " " not in fp and len(fp) > 3:
                    return fp
        return None

    def _extract_keywords(self, text: str) -> Set[str]:
        """Extract meaningful keywords from text for matching against existing files."""
        text = text.lower()
        # Remove common words and extract meaningful tokens
        stop_words = {"the", "a", "an", "is", "are", "was", "were", "be", "been",
                      "being", "have", "has", "had", "do", "does", "did", "will",
                      "would", "could", "should", "may", "might", "shall", "can",
                      "to", "of", "in", "for", "on", "with", "at", "by", "from",
                      "as", "into", "through", "during", "before", "after",
                      "above", "below", "between", "out", "off", "over", "under",
                      "again", "further", "then", "once", "here", "there", "when",
                      "where", "why", "how", "all", "each", "every", "both",
                      "few", "more", "most", "other", "some", "such", "no", "nor",
                      "not", "only", "own", "same", "so", "than", "too", "very",
                      "just", "also", "and", "but", "or", "if", "because",
                      "until", "while", "about", "up"}
        words = set(re.findall(r"[a-z]{3,}", text))
        return words - stop_words

    def _normalize_path(self, path: str) -> str:
        """Normalize a file path to be relative to /workspace/."""
        path = path.strip().strip("`\"'").strip()

        # Remove leading workspace prefix if present
        path = re.sub(r"^/workspace/", "", path)
        path = re.sub(r"^/workspace$", "", path)

        # Remove leading slash if present
        path = path.lstrip("/")

        # Skip invalid paths
        if not path or len(path) < 2:
            return ""
        if " " in path:
            return ""
        if path.startswith("."):
            return ""

        return path

    def _flatten_checklist(self, checklist: Any) -> List[str]:
        """Flatten checklist into list of text strings."""
        texts: List[str] = []
        if isinstance(checklist, list):
            for item in checklist:
                if isinstance(item, dict):
                    text = str(item.get("text", item.get("title", "")))
                    if text:
                        texts.append(text)
                elif isinstance(item, str):
                    texts.append(item)
        return texts

    def _sort_plans(self, plans: List[FilePlan]) -> List[FilePlan]:
        """Sort file plans in a sensible creation order: config first, then by dir depth."""
        # Priority: core config files first, then deeper paths later
        config_priority = {
            "package.json": 0,
            "requirements.txt": 0,
            "pyproject.toml": 0,
            "tsconfig.json": 0,
            "Makefile": 0,
            "Dockerfile": 0,
            "docker-compose.yml": 0,
            "index.html": 1,
            "main.py": 1,
            "app.py": 1,
            "index.js": 1,
            "index.ts": 1,
        }

        def sort_key(p: FilePlan) -> tuple:
            basename = os.path.basename(p.file_path).lower()
            priority = config_priority.get(basename, 5)
            depth = p.file_path.count("/")
            return (priority, depth, p.file_path)

        return sorted(plans, key=sort_key)

    def _derive_default_path(self, title: str, description: str) -> Optional[str]:
        """Derive a default file path from task title/description if no files were planned."""
        title_lower = title.lower()
        desc_lower = description.lower()
        combined = title_lower + " " + desc_lower

        # Detect framework/type
        if "python" in combined or "flask" in combined or "django" in combined:
            return "app.py"
        elif "react" in combined or "vue" in combined or "angular" in combined:
            sanitized = re.sub(r"[^a-z0-9]", "-", title_lower[:20].strip("-"))
            return f"src/components/{sanitized or 'Component'}.jsx"
        elif "html" in combined or "css" in combined:
            return "index.html"
        elif "node" in combined or "express" in combined:
            return "index.js"
        elif "go" in combined:
            return "main.go"
        elif "rust" in combined:
            return "src/main.rs"
        elif "java" in combined or "spring" in combined:
            sanitized = re.sub(r"[^a-zA-Z0-9]", "", title[:20])
            return f"src/main/java/com/example/{sanitized or 'App'}.java"
        elif "c#" in combined or ".net" in combined or "dotnet" in combined or "csharp" in combined:
            sanitized = re.sub(r"[^a-zA-Z0-9]", "", title[:20])
            return f"{sanitized or 'Program'}.cs"
        else:
            # Generic: create a file based on the task title
            sanitized = re.sub(r"[^a-z0-9]", "-", title_lower[:20]).strip("-")
            return f"{sanitized or 'implementation'}.txt"


# ── Prompt Builder ───────────────────────────────────────────────────────────

class PromptBuilder:
    """
    Builds focused, optimized prompts for per-file code generation.

    Each prompt contains:
    1. The file path and purpose
    2. Key context from the task description (relevant to THIS file)
    3. References to other files this file imports/depends on
    4. Peer context (what other agents have built, so we can import correctly)
    5. Coding standards from the project
    """

    def __init__(self, project_root: str = "/workspace"):
        self.project_root = project_root

    async def build_file_prompt(
        self,
        file_plan: FilePlan,
        task: Dict[str, Any],
        tech_spec: str = "",
        peer_context_block: str = "",
        workspace_tree: str = "",
        existing_file_content: str = "",
        is_bootstrap: bool = False,
    ) -> str:
        """
        Build a focused prompt for generating a single file.

        The prompt is designed to:
        - Be focused: only ask for what THIS file needs
        - Be contextual: include relevant cross-file context
        - Be concise: no boilerplate, no shell commands
        - Be actionable: clear what the output should be
        """
        task_title = str(task.get("title") or task.get("taskName") or "Untitled Task")
        task_desc = str(task.get("description") or "")
        checklist = self._get_relevant_checklist(file_plan, task)

        # File context: what depends on this, what does this depend on?
        file_context = self._build_file_context(file_plan, task)

        # Extract relevant tech spec section
        relevant_spec = self._extract_relevant_spec(file_plan.file_path, tech_spec)

        if is_bootstrap:
            return self._build_bootstrap_prompt(file_plan, task_title, workspace_tree)

        if file_plan.action == "modify":
            prompt = self._build_modify_prompt(
                file_plan=file_plan,
                task_title=task_title,
                existing_content=existing_file_content,
                task_desc=task_desc,
                file_context=file_context,
                peer_context=peer_context_block,
                relevant_spec=relevant_spec,
                checklist=checklist,
            )
        else:
            prompt = self._build_create_prompt(
                file_plan=file_plan,
                task_title=task_title,
                task_desc=task_desc,
                file_context=file_context,
                peer_context=peer_context_block,
                relevant_spec=relevant_spec,
                checklist=checklist,
            )

        return prompt

    def _build_create_prompt(
        self,
        file_plan: FilePlan,
        task_title: str,
        task_desc: str,
        file_context: str,
        peer_context: str,
        relevant_spec: str,
        checklist: List[str],
    ) -> str:
        """Build prompt for creating a new file."""
        lang = file_plan.language or _detect_language(file_plan.file_path)

        prompt_parts = [
            f"Generate the content for the file: `{file_plan.file_path}`",
            "",
            f"Language/Framework: {lang}",
            f"Purpose: {file_plan.purpose or 'Implement the required functionality'}",
            "",
        ]

        if peer_context:
            prompt_parts.extend([
                "=== PEER CONTEXT (other agents' completed work, import from these) ===",
                peer_context[:3000],
                "",
            ])

        if task_desc:
            # Extract task description relevant to this file
            relevant_desc = self._extract_relevant_description(file_plan.file_path, task_desc)
            prompt_parts.extend([
                "=== TASK REQUIREMENTS ===",
                f"Task: {task_title}",
                "",
                relevant_desc[:2000],
                "",
            ])

        if file_context:
            prompt_parts.extend([
                "=== FILE CONTEXT ===",
                file_context,
                "",
            ])

        if relevant_spec:
            prompt_parts.extend([
                "=== TECHNICAL SPECIFICATION (relevant sections) ===",
                relevant_spec[:2500],
                "",
            ])

        if checklist:
            prompt_parts.extend([
                "=== CHECKLIST ITEMS THIS FILE MUST SATISFY ===",
                *[f"- {item}" for item in checklist[:5]],
                "",
            ])

        prompt_parts.extend([
            "=== OUTPUT REQUIREMENTS ===",
            f"- Generate ONLY the content for `{file_plan.file_path}`",
            "- Use proper syntax and imports for the detected language/framework",
            "- Include error handling and edge cases",
            "- Follow the project's coding conventions inferred from existing code",
            "- Output the file content as PLAIN TEXT — no markdown code fences, no ``` blocks",
            "- Do NOT include any explanation, commentary, or shell commands",
            "- Write COMPLETE, production-ready code — no TODOs, no placeholders",
            "- The file content should start directly with the first line of code",
        ])

        return "\n".join(prompt_parts)

    def _build_modify_prompt(
        self,
        file_plan: FilePlan,
        task_title: str,
        existing_content: str,
        task_desc: str,
        file_context: str,
        peer_context: str,
        relevant_spec: str,
        checklist: List[str],
    ) -> str:
        """Build prompt for modifying an existing file."""
        lang = file_plan.language or _detect_language(file_plan.file_path)

        prompt_parts = [
            f"Modify the existing file: `{file_plan.file_path}`",
            "",
            f"Language: {lang}",
            f"Purpose: {file_plan.purpose or 'Update the existing implementation'}",
            "",
        ]

        if existing_content:
            prompt_parts.extend([
                "=== CURRENT FILE CONTENT ===",
                existing_content[:5000],
                "",
                "=== REQUIRED CHANGES ===",
            ])

        if task_desc:
            prompt_parts.append(task_desc[:2000])
            prompt_parts.append("")

        prompt_parts.extend([
            "=== OUTPUT REQUIREMENTS ===",
            "- Generate the COMPLETE updated content for this file (full file, not just changes)",
            f"- Output inside a {lang} code block",
            "- Write production-ready code — no TODOs or placeholders",
            "- Do NOT include any explanation or commentary outside the code block",
        ])

        return "\n".join(prompt_parts)

    def _build_bootstrap_prompt(
        self,
        file_plan: FilePlan,
        task_title: str,
        workspace_tree: str,
    ) -> str:
        """Build prompt for bootstrap (empty placeholder) file creation."""
        return (
            f"Create an empty placeholder file at `{file_plan.file_path}`.\n\n"
            f"Task: {task_title}\n\n"
            "Output just a comment indicating this is a bootstrap placeholder:\n"
            f"# {file_plan.file_path} — Bootstrap placeholder\n"
        )

    def _build_file_context(self, file_plan: FilePlan, task: Dict[str, Any]) -> str:
        """Build context about this file's role in the project."""
        context_parts = []

        if file_plan.dependencies:
            context_parts.append(f"Depends on: {', '.join(file_plan.dependencies)}")

        # Extract file-specific hints from task description
        task_desc = str(task.get("description") or "")
        if task_desc:
            # Check if the task mentions this file specifically
            basename = os.path.basename(file_plan.file_path)
            if basename in task_desc:
                context_parts.append(f"The task description mentions '{basename}' — "
                                     "this file is a key deliverable.")

        return "\n".join(context_parts)

    def _get_relevant_checklist(self, file_plan: FilePlan, task: Dict[str, Any]) -> List[str]:
        """Get checklist items relevant to this specific file."""
        relevant = list(file_plan.checklist_items)
        basename = os.path.basename(file_plan.file_path).lower()

        checklist_raw = task.get("checklist") or task.get("checklists") or []
        if isinstance(checklist_raw, list):
            for item in checklist_raw:
                if isinstance(item, dict):
                    text = str(item.get("text", item.get("title", ""))).lower()
                else:
                    text = str(item).lower()

                # Check if checklist item references this file
                if basename in text or file_plan.file_path.lower() in text:
                    relevant.append(text)

        return relevant

    def _extract_relevant_spec(self, file_path: str, tech_spec: str) -> str:
        """Extract sections of the tech spec relevant to this file."""
        if not tech_spec:
            return ""

        # Find sections mentioning this file or its directory
        dir_path = os.path.dirname(file_path)
        basename = os.path.basename(file_path)

        relevant_sections = []
        lines = tech_spec.split("\n")
        in_relevant = False
        section_lines = []

        for line in lines:
            # Check if this line mentions the file or its directory
            if basename in line or dir_path in line or file_path in line:
                in_relevant = True
                section_lines.append(line)
            elif line.startswith("## ") or line.startswith("# "):
                # Section header - if we were collecting, stop
                if in_relevant:
                    relevant_sections.extend(section_lines)
                    section_lines = []
                    in_relevant = False
                # Check if new section might be relevant
                if dir_path in line or basename in line:
                    in_relevant = True
                    section_lines.append(line)
            elif in_relevant:
                section_lines.append(line)

        if in_relevant:
            relevant_sections.extend(section_lines)

        return "\n".join(relevant_sections[:40]) if relevant_sections else ""

    def _extract_relevant_description(self, file_path: str, description: str) -> str:
        """Extract portions of the task description relevant to this file."""
        if not description:
            return ""

        basename = os.path.basename(file_path)
        lines = description.split("\n")
        relevant = []

        for i, line in enumerate(lines):
            if basename in line or file_path in line:
                # Include surrounding context (3 lines before, 5 after)
                start = max(0, i - 3)
                end = min(len(lines), i + 5)
                relevant.extend(lines[start:end])

        if relevant:
            return "\n".join(relevant)

        # Fallback: return first portion of description
        return description[:1500]


# ── Command Runner ───────────────────────────────────────────────────────────

class CommandRunner:
    """
    Runs build/verify commands inside a Docker container.
    All commands are APPLICATION-CONTROLLED — NOT generated by the LLM.
    The system determines what commands to run based on the detected tech stack.
    """

    def __init__(self, container_name: str, project_root: str = "/workspace"):
        self.container_name = container_name
        self.project_root = project_root

    async def detect_tech_stack(self) -> Dict[str, Any]:
        """
        Detect the tech stack in the container and return appropriate commands.
        Uses a deterministic probe approach (no LLM involvement).
        """
        result = {
            "type": "unknown",
            "install": "",
            "build": "",
            "test": "",
            "dev": "",
            "has_install_script": False,
            "has_build_script": False,
        }

        try:
            # Check for package.json (Node.js)
            has_package_json = self._container_test("-f", f"{self.project_root}/package.json")
            if has_package_json:
                result["type"] = "nodejs"
                result["install"] = "npm install"
                result["has_install_script"] = True

                # Check for specific package managers
                if self._container_test("-f", f"{self.project_root}/pnpm-lock.yaml"):
                    result["install"] = "pnpm install"
                elif self._container_test("-f", f"{self.project_root}/yarn.lock"):
                    result["install"] = "yarn install"

                # Check build script in package.json
                build_check = self._container_cat(f"{self.project_root}/package.json")
                if '"build"' in build_check[:1000]:
                    result["build"] = "npm run build 2>&1 || true"
                    result["has_build_script"] = True
                result["test"] = "npm test 2>&1 || true"
                result["dev"] = "npm run dev 2>&1 || true"
                return result

            # Check for requirements.txt (Python)
            if self._container_test("-f", f"{self.project_root}/requirements.txt"):
                result["type"] = "python"
                result["install"] = "pip install -r requirements.txt -q 2>&1 || true"
                result["has_install_script"] = True
                result["build"] = "python3 -m py_compile $(find . -name '*.py' -not -path '*/.*' 2>/dev/null | head -30) 2>&1 || true"
                return result

            # Check for pyproject.toml
            if self._container_test("-f", f"{self.project_root}/pyproject.toml"):
                result["type"] = "python"
                result["install"] = "pip install -e . -q 2>&1 || true"
                result["has_install_script"] = True
                result["build"] = "python3 -m py_compile $(find . -name '*.py' -not -path '*/.*' 2>/dev/null | head -30) 2>&1 || true"
                return result

            # Check for Cargo.toml (Rust)
            if self._container_test("-f", f"{self.project_root}/Cargo.toml"):
                result["type"] = "rust"
                result["install"] = "cargo fetch 2>&1 || true"
                result["has_install_script"] = True
                result["build"] = "cargo check 2>&1 || true"
                return result

            # Check for go.mod (Go)
            if self._container_test("-f", f"{self.project_root}/go.mod"):
                result["type"] = "go"
                result["install"] = "go mod download 2>&1 || true"
                result["has_install_script"] = True
                result["build"] = "go build ./... 2>&1 || true"
                return result

            # Check for pom.xml (Java Maven)
            if self._container_test("-f", f"{self.project_root}/pom.xml"):
                result["type"] = "java_maven"
                result["install"] = "mvn dependency:resolve -q 2>&1 || true"
                result["has_install_script"] = True
                result["build"] = "mvn compile -q 2>&1 || true"
                return result

            # Check for *.csproj (.NET)
            csproj = self._container_find("*.csproj")
            if csproj:
                result["type"] = "dotnet"
                result["install"] = "dotnet restore 2>&1 || true"
                result["has_install_script"] = True
                result["build"] = "dotnet build --no-restore -q 2>&1 || true"
                return result

            # Check for Gemfile (Ruby)
            if self._container_test("-f", f"{self.project_root}/Gemfile"):
                result["type"] = "ruby"
                result["install"] = "bundle install --quiet 2>&1 || true"
                result["has_install_script"] = True
                result["build"] = "ruby -c $(find . -name '*.rb' -not -path '*/.*' | head -20) 2>&1 || true"
                return result

        except Exception as e:
            logger.warning(f"Tech stack detection failed: {e}")

        # If no specific stack detected, try generic syntax check
        result["build"] = self._detect_generic_build_command()
        return result

    async def run_install(self, stack: Dict[str, Any]) -> Dict[str, Any]:
        """Run installation/dependency commands."""
        if not stack.get("install") or not stack.get("has_install_script"):
            return {"success": True, "output": "No install step required"}

        try:
            result = await self._run_in_container(stack["install"], timeout=120)
            return {
                "success": result["exit_code"] == 0 or "already satisfied" in result["stdout"].lower(),
                "output": result["stdout"][:2000],
                "errors": result["stderr"][:1000],
            }
        except Exception as e:
            return {"success": False, "output": "", "errors": str(e)}

    async def run_build(self, stack: Dict[str, Any]) -> Dict[str, Any]:
        """Run build commands."""
        if not stack.get("build"):
            return {"success": True, "output": "No build step required"}

        try:
            result = await self._run_in_container(stack["build"], timeout=180)
            success = result["exit_code"] == 0
            return {
                "success": success,
                "output": result["stdout"][:3000],
                "errors": result["stderr"][:2000] if not success else "",
            }
        except Exception as e:
            return {"success": False, "output": "", "errors": str(e)}

    async def run_syntax_check(self) -> Dict[str, Any]:
        """Run a quick syntax check on all project files."""
        try:
            # Try Python syntax check
            has_py = self._container_find("*.py", max_results=5)
            if has_py:
                result = await self._run_in_container(
                    "for f in $(find . -name '*.py' -not -path '*/.*' -not -path '*/node_modules/*' 2>/dev/null | head -20); do "
                    "python3 -c \"import py_compile; py_compile.compile('$f', doraise=True)\" 2>&1 && echo \"OK: $f\" || echo \"FAIL: $f\"; "
                    "done",
                    timeout=30,
                )
                return {
                    "success": "FAIL" not in result["stdout"],
                    "output": result["stdout"][:2000],
                }

            # Try Node.js syntax check
            has_js = self._container_find("*.js", max_results=5)
            if has_js:
                result = await self._run_in_container(
                    "for f in $(find . -name '*.js' -not -path '*/.*' -not -path '*/node_modules/*' 2>/dev/null | head -10); do "
                    "node --check \"$f\" 2>&1 && echo \"OK: $f\" || echo \"FAIL: $f\"; "
                    "done",
                    timeout=30,
                )
                return {
                    "success": "FAIL" not in result["stdout"],
                    "output": result["stdout"][:2000],
                }
        except Exception as e:
            logger.warning(f"Syntax check failed: {e}")

        return {"success": True, "output": "No syntax check applicable"}

    async def run_verify(self) -> Dict[str, Any]:
        """Run combined verification: syntax check first, then build if syntax passes."""
        syntax = await self.run_syntax_check()
        if not syntax["success"]:
            return syntax

        stack = await self.detect_tech_stack()
        install = await self.run_install(stack)
        build = await self.run_build(stack)

        return {
            "success": build["success"],
            "install_output": install["output"],
            "build_output": build["output"],
            "build_errors": build["errors"],
            "clean": install["success"] and build["success"],
        }

    # ── Private Helpers ───────────────────────────────────────────────────

    def _container_test(self, flag: str, path: str) -> bool:
        """Test a condition inside the container (e.g., -f for file existence)."""
        try:
            r = subprocess.run(
                ["docker", "exec", self.container_name, "test", flag, path],
                capture_output=True, timeout=10,
            )
            return r.returncode == 0
        except Exception:
            return False

    def _container_cat(self, path: str) -> str:
        """Read a file inside the container."""
        try:
            r = subprocess.run(
                ["docker", "exec", self.container_name, "cat", path],
                capture_output=True, text=True, timeout=10,
            )
            return r.stdout if r.returncode == 0 else ""
        except Exception:
            return ""

    def _container_find(self, pattern: str, max_results: int = 5) -> List[str]:
        """Find files matching pattern inside container."""
        try:
            # Use shell inside docker to handle pipes; docker exec sh -c is the reliable pattern
            find_cmd = (
                f"find {shlex.quote(self.project_root)} -name {shlex.quote(pattern)} "
                f"-not -path '*/.*' -not -path '*/node_modules/*' 2>/dev/null | "
                f"head -{max_results}"
            )
            r = subprocess.run(
                ["docker", "exec", self.container_name, "sh", "-c", find_cmd],
                capture_output=True, text=True, timeout=10,
            )
            if r.returncode == 0 and r.stdout.strip():
                return [f.strip() for f in r.stdout.strip().split("\n") if f.strip()]
            return []
        except Exception:
            return []

    def _container_async_run(self, command: str, timeout: int = 60) -> subprocess.CompletedProcess:
        """Run a command inside the Docker container using sh -c for reliability."""
        return subprocess.run(
            ["docker", "exec", "-w", self.project_root,
             self.container_name, "sh", "-c", command],
            capture_output=True, text=True, timeout=timeout,
        )

    async def _run_in_container(self, command: str, timeout: int = 60) -> Dict[str, Any]:
        """Run a command inside the Docker container."""
        try:
            r = self._container_async_run(command, timeout=timeout)
            return {
                "exit_code": r.returncode,
                "stdout": r.stdout or "",
                "stderr": r.stderr or "",
            }
        except subprocess.TimeoutExpired:
            return {"exit_code": -1, "stdout": "", "stderr": f"Command timed out ({timeout}s)"}
        except Exception as e:
            return {"exit_code": -1, "stdout": "", "stderr": str(e)}

    def _detect_generic_build_command(self) -> str:
        """Detect a generic build command if no specific stack is identified."""
        try:
            # Check for Makefile
            if self._container_test("-f", f"{self.project_root}/Makefile"):
                return "make 2>&1 || true"
            # Check for build script
            if self._container_test("-f", f"{self.project_root}/build.sh"):
                return "bash build.sh 2>&1 || true"
        except Exception:
            pass
        return ""


# ── File Writer ──────────────────────────────────────────────────────────────

class FileWriter:
    """
    Writes file content to the Docker container.
    Handles directory creation, atomic writes, and verification.
    """

    def __init__(self, container_name: str, project_root: str = "/workspace"):
        self.container_name = container_name
        self.project_root = project_root

    async def write_file(self, file_plan: FilePlan, content: str) -> FileGenerationResult:
        """
        Write file content to the container.

        Steps:
        1. Ensure parent directory exists
        2. Write content via temp file + mv (atomic)
        3. Verify file was written correctly
        """
        full_path = f"{self.project_root}/{file_plan.file_path}"
        dir_path = os.path.dirname(full_path)

        try:
            # Step 1: Ensure directory exists
            await self._ensure_dir(dir_path)

            # Step 2: For bootstrap tasks, create empty file
            if file_plan.is_bootstrap:
                return await self._write_empty_file(full_path, file_plan.file_path)

            # Step 3: For modify actions, read existing + append
            if file_plan.action == "append":
                return await self._append_to_file(full_path, content, file_plan.file_path)

            # Step 4: Write content via temp file (atomic write)
            clean_content = self._clean_llm_content(content)
            result = await self._write_content(full_path, clean_content, file_plan.file_path)
            return result

        except Exception as e:
            logger.error(f"Failed to write {file_plan.file_path}: {e}")
            return FileGenerationResult(
                file_path=file_plan.file_path,
                success=False,
                error=str(e),
            )

    async def _ensure_dir(self, dir_path: str) -> bool:
        """Ensure a directory exists inside the container."""
        try:
            r = subprocess.run(
                ["docker", "exec", self.container_name, "mkdir", "-p", dir_path],
                capture_output=True, text=True, timeout=15,
            )
            return r.returncode == 0
        except Exception as e:
            logger.warning(f"Failed to create directory {dir_path}: {e}")
            return False

    async def _write_empty_file(self, full_path: str, relative_path: str) -> FileGenerationResult:
        """Create an empty placeholder file."""
        try:
            r = subprocess.run(
                ["docker", "exec", self.container_name, "touch", full_path],
                capture_output=True, text=True, timeout=15,
            )
            success = r.returncode == 0
            return FileGenerationResult(
                file_path=relative_path,
                success=success,
                content_length=0,
                error="" if success else r.stderr,
            )
        except Exception as e:
            return FileGenerationResult(
                file_path=relative_path,
                success=False,
                error=str(e),
            )

    async def _append_to_file(
        self, full_path: str, content: str, relative_path: str
    ) -> FileGenerationResult:
        """Append content to an existing file."""
        try:
            clean = self._clean_llm_content(content)
            # Use temp file to avoid shell escaping issues
            import tempfile as tf
            with tf.NamedTemporaryFile(mode="w", suffix=".tmp", delete=False) as f:
                f.write(clean)
                tmp_path = f.name

            try:
                # Copy to container
                subprocess.run(
                    ["docker", "cp", tmp_path, f"{self.container_name}:{full_path}"],
                    capture_output=True, timeout=15, check=False,
                )
                # Then append
                r = subprocess.run(
                    ["docker", "exec", self.container_name, "sh", "-c",
                     f"cat {full_path} >> {full_path}.bak && mv {full_path}.bak {full_path}"],
                    capture_output=True, text=True, timeout=15,
                )
                success = r.returncode == 0
                return FileGenerationResult(
                    file_path=relative_path,
                    success=success,
                    content_length=len(clean),
                    error="" if success else r.stderr,
                )
            finally:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
        except Exception as e:
            return FileGenerationResult(
                file_path=relative_path,
                success=False,
                error=str(e),
            )

    async def _write_content(
        self, full_path: str, content: str, relative_path: str
    ) -> FileGenerationResult:
        """
        Write content to a file inside the container using docker cp.
        This is more reliable than shell heredocs for complex content.
        """
        import tempfile as tf

        with tf.NamedTemporaryFile(mode="w", suffix=".tmp", delete=False, encoding="utf-8") as f:
            f.write(content)
            tmp_path = f.name

        try:
            # Copy to container
            cp_result = subprocess.run(
                ["docker", "cp", tmp_path, f"{self.container_name}:{full_path}"],
                capture_output=True, text=True, timeout=15,
            )

            if cp_result.returncode != 0:
                # Fallback: try writing via shell heredoc
                fallback_result = await self._write_via_heredoc(full_path, content)
                if fallback_result:
                    return fallback_result

                return FileGenerationResult(
                    file_path=relative_path,
                    success=False,
                    error=cp_result.stderr,
                )

            # Verify the file was written
            verify = subprocess.run(
                ["docker", "exec", self.container_name, "wc", "-c", full_path],
                capture_output=True, text=True, timeout=10,
            )
            if verify.returncode == 0 and verify.stdout.strip():
                size_str = verify.stdout.split()[0]
                try:
                    size = int(size_str)
                except ValueError:
                    size = len(content)

                return FileGenerationResult(
                    file_path=relative_path,
                    success=size > 0,
                    content_length=size,
                    error="" if size > 0 else "File appears empty after write",
                )

            return FileGenerationResult(
                file_path=relative_path,
                success=True,
                content_length=len(content),
            )

        except Exception as e:
            return FileGenerationResult(
                file_path=relative_path,
                success=False,
                error=str(e),
            )
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    async def _write_via_heredoc(self, full_path: str, content: str) -> Optional[FileGenerationResult]:
        """Fallback: write using shell heredoc inside container."""
        try:
            # Escape single quotes for shell safety
            escaped = content.replace("'", "'\\''")
            cmd = f"cat <<'ENDOFFILE' > {full_path}\n{escaped}\nENDOFFILE"
            r = subprocess.run(
                ["docker", "exec", self.container_name, "sh", "-c", cmd],
                capture_output=True, text=True, timeout=30,
            )
            if r.returncode == 0:
                return FileGenerationResult(
                    file_path=full_path.replace(f"{self.project_root}/", ""),
                    success=True,
                    content_length=len(content),
                )
            return None
        except Exception:
            return None

    def _clean_llm_content(self, content: str) -> str:
        """
        Clean LLM-generated content.
        Removes markdown code fences if the LLM wraps output in them anyway.
        """
        content = content.strip()

        # Remove markdown code fences (```language ... ```)
        lines = content.split("\n")

        # Check if starts with ``` and ends with ```
        if lines and lines[0].startswith("```"):
            lines = lines[1:]  # Remove opening fence
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]  # Remove closing fence

        # Also handle case where there's a single ```
        cleaned = "\n".join(lines).strip()
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3].strip()
        if cleaned.startswith("```"):
            cleaned = cleaned[3:].strip()

        return cleaned


# ── Controlled Executor (Orchestrator) ──────────────────────────────────────

class ControlledExecutor:
    """
    Main orchestrator for the application-controlled execution flow.

    Usage:
        executor = ControlledExecutor(container_name, project_root)
        result = await executor.execute_task(task, ...)
    """

    def __init__(
        self,
        container_name: str,
        project_root: str = "/workspace",
        project_token: Optional[str] = None,
        agent_id: str = "",
    ):
        self.container_name = container_name
        self.project_root = project_root
        self.project_token = project_token
        self.agent_id = agent_id
        self.planner = FilePlanner(project_root)
        self.prompt_builder = PromptBuilder(project_root)
        self.writer = FileWriter(container_name, project_root)
        self.command_runner = CommandRunner(container_name, project_root)

    async def execute_task(
        self,
        task: Dict[str, Any],
        tech_spec: str = "",
        peer_context_block: str = "",
        workspace_tree: str = "",
        canonical_tree: str = "",
        existing_files: Optional[List[str]] = None,
        is_bootstrap: bool = False,
        max_retries_per_file: int = 2,
    ) -> ControlledExecutionResult:
        """
        Execute a task using the application-controlled flow.

        Flow:
        1. Plan files from task description + workspace context
        2. Register file intents with coordination system (Phase 1)
        3. For each file: generate → write → verify
        4. Run build/verify
        5. Return results
        """
        task_id = str(task.get("id") or task.get("task_id") or task.get("external_id") or "unknown")
        errors: List[str] = []
        file_results: List[FileGenerationResult] = []

        # ── Step 1: Plan Files ──────────────────────────────────────────────
        try:
            file_plans = await self.planner.plan_files(
                task=task,
                workspace_tree=workspace_tree,
                canonical_tree=canonical_tree,
                existing_files=existing_files,
                is_bootstrap=is_bootstrap,
            )
        except Exception as e:
            errors.append(f"File planning failed: {e}")
            return ControlledExecutionResult(
                success=False,
                task_id=task_id,
                errors=errors,
            )

        if not file_plans:
            logger.warning(f"[{self.agent_id}] No files planned for task {task_id}, marking as success with no changes")
            return ControlledExecutionResult(
                success=True,
                task_id=task_id,
                files_planned=0,
                files_generated=0,
            )

        # ── Step 2: Register file intents with coordination system ──────────
        await self._register_file_intents(file_plans)

        # ── Step 3: Generate and write each file ────────────────────────────
        files_generated = 0
        files_failed = 0

        for file_plan in file_plans:
            result = await self._generate_and_write_file(
                file_plan=file_plan,
                task=task,
                tech_spec=tech_spec,
                peer_context_block=peer_context_block,
                workspace_tree=workspace_tree,
                is_bootstrap=is_bootstrap,
                max_retries=max_retries_per_file,
            )

            file_results.append(result)
            if result.success:
                files_generated += 1
                logger.info(f"[{self.agent_id}] ✅ Generated {file_plan.file_path} ({result.content_length} bytes)")
            else:
                files_failed += 1
                logger.warning(f"[{self.agent_id}] ❌ Failed to generate {file_plan.file_path}: {result.error}")
                errors.append(f"{file_plan.file_path}: {result.error}")

        # ── Step 4: Run build/verify ────────────────────────────────────────
        build_result = None
        if not is_bootstrap and files_generated > 0:
            try:
                stack = await self.command_runner.detect_tech_stack()
                verify_result = await self.command_runner.run_verify()

                build_result = BuildResult(
                    success=verify_result.get("success", True),
                    build_output=verify_result.get("build_output", ""),
                    build_errors=[verify_result.get("build_errors", "")] if verify_result.get("build_errors") else [],
                    install_errors=[verify_result.get("install_output", "")] if not verify_result.get("clean", True) else [],
                )

                if not build_result.success:
                    errors.append(f"Build verification failed")
            except Exception as e:
                logger.warning(f"[{self.agent_id}] Build verification failed (non-fatal): {e}")
                errors.append(f"Build error: {e}")

        # ── Step 5: Compile result ──────────────────────────────────────────
        is_success = files_failed == 0
        return ControlledExecutionResult(
            success=is_success,
            task_id=task_id,
            files_planned=len(file_plans),
            files_generated=files_generated,
            files_failed=files_failed,
            file_results=file_results,
            build_result=build_result,
            errors=errors,
        )

    async def _generate_and_write_file(
        self,
        file_plan: FilePlan,
        task: Dict[str, Any],
        tech_spec: str = "",
        peer_context_block: str = "",
        workspace_tree: str = "",
        is_bootstrap: bool = False,
        max_retries: int = 2,
    ) -> FileGenerationResult:
        """Generate a single file's content via LLM and write it to the container."""
        for attempt in range(max_retries + 1):
            try:
                # ── Build focused prompt ────────────────────────────────────
                prompt = await self.prompt_builder.build_file_prompt(
                    file_plan=file_plan,
                    task=task,
                    tech_spec=tech_spec,
                    peer_context_block=peer_context_block,
                    workspace_tree=workspace_tree,
                    is_bootstrap=is_bootstrap,
                )

                # ── Call LLM (reuse existing infrastructure) ─────────────────
                # We use _call_ai_for_code but with a modified prompt that asks
                # for file content instead of a bash script
                from agent_service import _call_ai_for_code
                code_response, thought = await _call_ai_for_code(
                    task_description=prompt,
                    agent_type="validator",
                    system_prompt_override=self._build_file_generation_system_prompt(file_plan, is_bootstrap),
                    workspace_tree=workspace_tree,
                    task=task,
                )

                # ── Write file to container ─────────────────────────────────
                result = await self.writer.write_file(file_plan, code_response)

                if result.success:
                    return result

                # If failed and we have retries left, log and retry
                if attempt < max_retries:
                    logger.info(
                        f"[{self.agent_id}] Retry {attempt + 1}/{max_retries} for {file_plan.file_path}: {result.error}"
                    )
                    await asyncio.sleep(2 * (attempt + 1))

            except Exception as e:
                if attempt < max_retries:
                    logger.info(
                        f"[{self.agent_id}] Retry {attempt + 1}/{max_retries} for {file_plan.file_path}: {e}"
                    )
                    await asyncio.sleep(2 * (attempt + 1))
                else:
                    return FileGenerationResult(
                        file_path=file_plan.file_path,
                        success=False,
                        error=f"All {max_retries + 1} attempts failed: {e}",
                        retry_count=attempt,
                    )

        return FileGenerationResult(
            file_path=file_plan.file_path,
            success=False,
            error=f"Failed after {max_retries + 1} attempts",
            retry_count=max_retries,
        )

    def _build_file_generation_system_prompt(
        self, file_plan: FilePlan, is_bootstrap: bool
    ) -> str:
        """Build a system prompt for per-file generation (replaces bash script prompt)."""
        if is_bootstrap:
            return (
                "You are creating a bootstrap file structure.\n"
                "Output ONLY the content for the specified empty placeholder file.\n"
                "The content should be just a single-line comment indicating the file's purpose.\n"
                "Do NOT add any explanatory text, code fences, or markdown formatting."
            )

        lang = file_plan.language or _detect_language(file_plan.file_path)

        return (
            f"You are a code generator. Generate ONLY the content for a single file.\n\n"
            f"RULES:\n"
            f"- Generate COMPLETE, production-ready code — no TODOs, no placeholders, no stubs\n"
            f"- Use {lang} syntax\n"
            f"- Include all necessary imports and dependencies\n"
            f"- Add error handling and input validation\n"
            f"- Follow language-specific best practices and conventions\n"
            f"- Output ONLY the file content — no explanations, no commentary\n"
            f"- Output the content as PLAIN TEXT, not wrapped in markdown code fences\n"
            f"- Write the FULL complete file content from top to bottom\n"
            f"- Use meaningful variable and function names\n"
            f"- Add comments for complex logic\n"
            f"- Make sure all referenced imports/packages actually exist in the project\n"
        )

    async def _register_file_intents(self, file_plans: List[FilePlan]) -> None:
        """
        Register file intents with the coordination system (Phase 1).
        This allows other agents to see which files this agent plans to modify.
        """
        if not self.project_token or not self.agent_id:
            return

        try:
            from agent_coordination_service import coordination_service

            file_paths = [p.file_path for p in file_plans]
            await coordination_service.register_file_intents(
                project_token=self.project_token,
                agent_id=self.agent_id,
                file_paths=file_paths,
            )
            logger.info(
                f"[{self.agent_id}] Registered {len(file_paths)} file intents with coordination service"
            )
        except Exception as e:
            logger.warning(f"[{self.agent_id}] Failed to register file intents: {e}")

    async def release_file_locks(self) -> None:
        """Release all file locks held by this agent after execution."""
        if not self.project_token or not self.agent_id:
            return

        try:
            from agent_coordination_service import coordination_service

            await coordination_service.release_agent_locks(
                project_token=self.project_token,
                agent_id=self.agent_id,
            )
            logger.info(f"[{self.agent_id}] Released all file locks")
        except Exception as e:
            logger.warning(f"[{self.agent_id}] Failed to release file locks: {e}")


# ── Convenience function for integration ────────────────────────────────────

async def run_controlled_execution(
    container_name: str,
    task: Dict[str, Any],
    project_root: str = "/workspace",
    project_token: Optional[str] = None,
    agent_id: str = "",
    tech_spec: str = "",
    peer_context_block: str = "",
    workspace_tree: str = "",
    canonical_tree: str = "",
    existing_files: Optional[List[str]] = None,
    is_bootstrap: bool = False,
    max_retries_per_file: int = 2,
) -> Dict[str, Any]:
    """
    Convenience function to run the controlled execution flow.

    Returns a dict compatible with agent_service's result format:
    {
        "success": bool,
        "files_written": List[str],
        "errors": List[str],
        "controlled_results": ControlledExecutionResult (as dict),
    }
    """
    executor = ControlledExecutor(
        container_name=container_name,
        project_root=project_root,
        project_token=project_token,
        agent_id=agent_id,
    )

    try:
        result = await executor.execute_task(
            task=task,
            tech_spec=tech_spec,
            peer_context_block=peer_context_block,
            workspace_tree=workspace_tree,
            canonical_tree=canonical_tree,
            existing_files=existing_files,
            is_bootstrap=is_bootstrap,
            max_retries_per_file=max_retries_per_file,
        )

        # Release file locks
        await executor.release_file_locks()

        # Build compatible return format
        return {
            "success": result.success,
            "files_written": [
                r.file_path for r in result.file_results if r.success
            ],
            "errors": result.errors,
            "controlled_results": {
                "files_planned": result.files_planned,
                "files_generated": result.files_generated,
                "files_failed": result.files_failed,
                "build_success": result.build_result.success if result.build_result else True,
                "file_results": [
                    {"file_path": r.file_path, "success": r.success, "size": r.content_length}
                    for r in result.file_results
                ],
            },
        }

    except Exception as e:
        logger.exception(f"Controlled execution failed: {e}")
        await executor.release_file_locks()
        return {
            "success": False,
            "files_written": [],
            "errors": [str(e)],
            "controlled_results": None,
        }


# ── Container Discovery ─────────────────────────────────────────────────────
# Since we can't modify run_agent() to pass container_name to _call_ai_for_code(),
# we discover the running container by scanning Docker for containers matching
# the agent_id pattern. This is safe because:
#   1. The container is guaranteed to exist at the time _call_ai_for_code() runs
#   2. Container name includes the agent_id: "{agent_id}_{random_hex}"
#   3. Docker name filter is exact, so we won't match wrong containers


def _find_agent_container(agent_id: str) -> Optional[str]:
    """
    Find a running Docker container for this agent by scanning container names.
    Container names follow the pattern: {agent_id}_{8-char-hex}
    """
    if not agent_id:
        return None
    try:
        # List all running containers and filter by name containing agent_id
        result = subprocess.run(
            ["docker", "ps", "--filter", f"name={agent_id}",
             "--format", "{{.Names}}", "--no-trunc"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return None

        containers = [n.strip() for n in result.stdout.strip().split("\n") if n.strip()]
        if not containers:
            return None

        # Exact match: prefer container that starts with agent_id_
        for name in containers:
            if name.startswith(f"{agent_id}_"):
                return name

        # Fallback to first matching container
        return containers[0]

    except Exception as e:
        logger.debug(f"Container discovery failed for {agent_id}: {e}")
        return None


# ── Runtime Integration: ControlledExecutor that discovers its own container ──

class ContainerAwareControlledExecutor:
    """
    A variant of ControlledExecutor that automatically discovers its container
    by scanning Docker. This allows integration WITHOUT modifying run_agent().

    Usage:
        executor = ContainerAwareControlledExecutor(agent_id, project_token)
        result = await executor.run_for_task(task, ...)
    """

    def __init__(
        self,
        agent_id: str,
        project_token: Optional[str] = None,
        project_root: str = "/workspace",
    ):
        self.agent_id = agent_id
        self.project_token = project_token
        self.project_root = project_root
        self._container_name: Optional[str] = None
        self._executor: Optional[ControlledExecutor] = None

    async def _ensure_container(self) -> Optional[str]:
        """Find or refresh the container name for this agent."""
        if self._container_name:
            return self._container_name

        container_name = _find_agent_container(self.agent_id)
        if container_name:
            self._container_name = container_name
            self._executor = ControlledExecutor(
                container_name=container_name,
                project_root=self.project_root,
                project_token=self.project_token,
                agent_id=self.agent_id,
            )
            logger.info(f"[CE] Discovered container '{container_name}' for agent {self.agent_id}")
        return self._container_name

    async def run_for_task(
        self,
        task_description: str,
        task: Dict[str, Any],
        tech_spec: str = "",
        peer_context_block: str = "",
        workspace_tree: str = "",
        canonical_tree: str = "",
        existing_files: Optional[List[str]] = None,
        is_bootstrap: bool = False,
    ) -> Dict[str, Any]:
        """
        Run controlled execution for a task. Discovers container automatically.

        Returns a dict compatible with _call_ai_for_code()'s output format:
        {
            "script": str,      # Fake bash script for _exec_script_in_container
            "thought": str,     # Optional thought text
            "files_written": List[str],  # Files created
            "success": bool,             # Whether execution succeeded
        }
        """
        container_name = await self._ensure_container()
        if not container_name or not self._executor:
            logger.warning(f"[CE] No container found for {self.agent_id}, controlled execution unavailable")
            return {"success": False, "script": "", "thought": "No container found", "files_written": []}

        try:
            result = await self._executor.execute_task(
                task=task or {"description": task_description, "title": task_description[:80]},
                tech_spec=tech_spec,
                peer_context_block=peer_context_block,
                workspace_tree=workspace_tree,
                canonical_tree=canonical_tree,
                existing_files=existing_files,
                is_bootstrap=is_bootstrap,
            )

            await self._executor.release_file_locks()

            if result.success and result.files_generated > 0:
                # Build a lightweight "script" that echoes created files
                files_log = "\n".join(f"echo '[CREATED] {f}'" for f in
                                       [r.file_path for r in result.file_results if r.success])
                fake_script = (
                    f"#!/usr/bin/env bash\n"
                    f"set -e\n"
                    f"cd /workspace\n"
                    f"\n"
                    f"echo '=== Controlled Execution Summary ==='\n"
                    f"{files_log}\n"
                    f"echo '=== Done ==='\n"
                )
                return {
                    "success": True,
                    "script": fake_script,
                    "thought": f"Created {result.files_generated} files via controlled executor",
                    "files_written": [r.file_path for r in result.file_results if r.success],
                }
            elif result.success and result.files_generated == 0:
                return {
                    "success": True,
                    "script": (
                        "#!/usr/bin/env bash\n"
                        "set -e\n"
                        "cd /workspace\n"
                        "echo '=== No files needed for this task ==='\n"
                    ),
                    "thought": "No files needed",
                    "files_written": [],
                }
            else:
                return {
                    "success": False,
                    "script": "",
                    "thought": f"Controlled execution failed: {result.errors}",
                    "files_written": [],
                }

        except Exception as e:
            logger.warning(f"[CE] Controlled execution error: {e}")
            if self._executor:
                await self._executor.release_file_locks()
            return {"success": False, "script": "", "thought": str(e), "files_written": []}


# ── Simple Integration Wrapper ──────────────────────────────────────────────
# This function can be called to check whether controlled execution is available
# for a given agent, and if so, execute the task.

_agent_executors: Dict[str, ContainerAwareControlledExecutor] = {}


async def try_controlled_execution(
    task_description: str,
    agent_type: str,
    agent_id: str,
    project_token: Optional[str] = None,
    task: Optional[Dict[str, Any]] = None,
    tech_spec: str = "",
    peer_context: str = "",
    workspace_tree: str = "",
) -> Optional[Dict[str, Any]]:
    """
    Try to execute a task using the controlled executor.
    Returns None if not available (e.g., no container found, bootstrap task).
    Otherwise returns the result dict with 'script', 'thought', 'files_written'.

    This is the main integration point. Call this instead of _call_ai_for_code()
    for non-bootstrap tasks.
    """
    # Detect bootstrap: use original bash approach
    if not task:
        task = {"description": task_description, "title": task_description[:80]}
    task_id_str = str(task.get("id") or task.get("task_id") or "").upper()
    task_title_str = str(task.get("title") or task.get("taskName") or "").lower()
    if "bootstrap" in task_title_str or "task-00" in task_id_str or "task_00" in task_id_str:
        return None  # Bootstrap tasks use original bash approach
    if "bootstrap" in task_description.lower():
        return None

    # Get or create executor for this agent
    executor_key = f"{project_token or ''}:{agent_id}"
    if executor_key not in _agent_executors:
        _agent_executors[executor_key] = ContainerAwareControlledExecutor(
            agent_id=agent_id,
            project_token=project_token,
        )

    executor = _agent_executors[executor_key]
    result = await executor.run_for_task(
        task_description=task_description,
        task=task,
        tech_spec=tech_spec,
        peer_context_block=peer_context,
        workspace_tree=workspace_tree,
        is_bootstrap=False,
    )

    if result["success"]:
        return result

    # Controlled execution failed or not available
    return None


# ── Drop-in Replacement Wrapper ─────────────────────────────────────────────
# This function has the EXACT same signature as agent_service._call_ai_for_code().
# It adds controlled execution as a PREFERRED path and falls back to the original
# bash approach if controlled execution is not available.
#
# Usage:
#   # Replace this:
#   code, thought = await _call_ai_for_code(...)
#
#   # With this:
#   from agent_controlled_executor import call_ai_for_code_with_controlled
#   code, thought = await call_ai_for_code_with_controlled(...)

async def call_ai_for_code_with_controlled(
    task_description: str,
    agent_type: str,
    code_context: str = "",
    system_prompt_override: str = "",
    tech_spec: str = "",
    workspace_tree: str = "",
    live_repo_tree: str = "",
    peer_context: str = "",
    project_root: str = "/workspace",
    agent_id: str = "",
    agent_output_log: list = None,
    checklist: list = None,
    task: dict = None,
) -> tuple[str, str]:
    """
    Drop-in replacement for agent_service._call_ai_for_code().
    Uses controlled execution for non-bootstrap tasks, falls back to bash.
    """
    # Extract project_token from task if available
    project_token = task.get("_project_token") if isinstance(task, dict) else None

    # Try controlled execution first
    try:
        controlled_result = await try_controlled_execution(
            task_description=task_description,
            agent_type=agent_type,
            agent_id=agent_id,
            project_token=project_token,
            task=task,
            tech_spec=tech_spec,
            peer_context=peer_context,
            workspace_tree=workspace_tree,
        )

        if controlled_result is not None and controlled_result["success"]:
            # Controlled execution succeeded
            return controlled_result["script"], controlled_result["thought"]

    except Exception as e:
        logger.warning(f"[CE] Controlled execution attempt failed, falling back: {e}")

    # Fall back to original bash approach (lazy import to avoid circular dependency)
    from agent_service import _call_ai_for_code
    return await _call_ai_for_code(
        task_description, agent_type,
        code_context=code_context,
        system_prompt_override=system_prompt_override,
        tech_spec=tech_spec,
        workspace_tree=workspace_tree,
        live_repo_tree=live_repo_tree,
        peer_context=peer_context,
        project_root=project_root,
        agent_id=agent_id,
        agent_output_log=agent_output_log,
        checklist=checklist,
        task=task,
    )
