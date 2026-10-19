"""
Checklist Generator - Creates dynamic checklists for tasks before agent execution.

When an agent is assigned to a task, this generator breaks down the task into
step-by-step checklist items that will be stored in the database and tracked.
"""
import json
import logging
import os
import re
from typing import Any, Dict, List
from agent.model_router import ModelRouter, TaskType
from infrastructure.llm_client import LLMClient

logger = logging.getLogger(__name__)


def _load_architecture_context(
    workspace_path: str,
    lane: str,
    title: str,
    description: str,
    max_chars: int = 2500,
) -> str:
    """Extract relevant excerpts from HLD/LLD blueprints to ground checklist generation.

    Caps retrieval to ~max_chars so the prompt stays strictly within LLM planning token budgets.
    """
    candidates = [
        os.path.join(workspace_path, ".agent", "docs"),
        os.path.join(workspace_path, "docs"),
        "/workspace/.agent/docs",
    ]
    docs_dir = None
    for cand in candidates:
        if cand and os.path.isdir(cand):
            docs_dir = cand
            break

    if not docs_dir:
        return ""

    doc_files = [
        ("LLD", os.path.join(docs_dir, "LLD.md")),
        ("HLD", os.path.join(docs_dir, "HLD.md")),
        ("Executive Summary", os.path.join(docs_dir, "EXECUTIVE_SUMMARY.md")),
    ]

    lane_keywords = {
        "backend": ["database", "schema", "ddl", "table", "model", "migration", "api", "endpoint", "route", "crud", "payload"],
        "frontend": ["component", "ui", "screen", "page", "view", "state", "client", "layout", "workflow", "form"],
        "qa": ["test", "api", "endpoint", "verification", "validation", "acceptance", "edge case", "schema"],
    }.get(lane.lower(), ["schema", "api", "model", "component"])

    task_text = f"{title} {description}".lower()
    task_words = [
        w.strip() for w in re.findall(r'[a-zA-Z]{4,}', task_text)
        if w not in {"create", "implement", "update", "build", "task", "with", "from", "that", "this", "have", "need", "should"}
    ][:8]

    extracted_sections = []
    total_len = 0

    for doc_name, file_path in doc_files:
        if not os.path.isfile(file_path):
            continue
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception:
            continue

        sections = re.split(r'(?m)^(?=##\s+)', content)
        scored_sections = []

        for sec in sections:
            sec_clean = sec.strip()
            if not sec_clean:
                continue
            first_line = sec_clean.split("\n", 1)[0].lower()
            sec_lower = sec_clean.lower()

            score = 0
            for kw in lane_keywords:
                if kw in first_line:
                    score += 5
                elif kw in sec_lower[:400]:
                    score += 1

            for tw in task_words:
                if tw in first_line:
                    score += 6
                elif tw in sec_lower[:400]:
                    score += 2

            if score > 0:
                scored_sections.append((score, doc_name, sec_clean))

        scored_sections.sort(key=lambda x: x[0], reverse=True)

        for score, dname, sec_text in scored_sections[:3]:
            if len(sec_text) > 1200:
                sec_snippet = sec_text[:1200] + "\n...(truncated for context size)"
            else:
                sec_snippet = sec_text

            if total_len + len(sec_snippet) > max_chars:
                remaining = max_chars - total_len
                if remaining > 200:
                    extracted_sections.append(f"#### [{dname}] Excerpt:\n{sec_snippet[:remaining]}...")
                break

            extracted_sections.append(f"#### [{dname}] Excerpt:\n{sec_snippet}")
            total_len += len(sec_snippet)

        if total_len >= max_chars:
            break

    if not extracted_sections:
        return ""

    return "\n\n".join(extracted_sections)


async def generate_task_checklist(
    task: Any,
    lane: str,
    workspace_path: str,
    model_router: ModelRouter,
) -> List[Dict[str, Any]]:
    """
    Generate a detailed checklist for a task before execution.
    
    Args:
        task: Task object with title, description, files_involved
        lane: Agent lane (backend, frontend, qa)
        workspace_path: Project workspace path
        model_router: Model router for LLM selection
        
    Returns:
        List of checklist items with structure:
        [
            {"text": "Create user model with fields", "completed": false},
            {"text": "Set up database migration", "completed": false},
            ...
        ]
    """
    task_id = getattr(task, "task_id", getattr(task, "id", "unknown"))
    title = getattr(task, "title", getattr(task, "task_name", "Unknown"))
    description = getattr(task, "description", "")
    files_involved = getattr(task, "files_involved", [])
    task_type = getattr(task, "task_type", "TASK")
    
    logger.info(f"[ChecklistGen] Generating checklist for task {task_id}: {title}")

    # Load architectural context if blueprints exist in workspace
    arch_context = _load_architecture_context(
        workspace_path=workspace_path,
        lane=lane,
        title=title,
        description=description,
    )
    if arch_context:
        logger.info(f"[ChecklistGen] Grounded checklist in {len(arch_context)} chars of HLD/LLD architecture blueprints")
    
    # Build the prompt for checklist generation
    prompt = _build_checklist_prompt(
        title=title,
        description=description,
        task_type=task_type,
        lane=lane,
        files_involved=files_involved,
        arch_context=arch_context,
    )
    
    # Get LLM config
    config = model_router.route(TaskType.planning)
    llm_client = LLMClient(config=config)
    
    try:
        response = llm_client.complete(
            system=_get_system_prompt(lane),
            messages=[
                {"role": "user", "content": prompt},
            ],
        )
        
        # Parse checklist from response (supports LLMResponse or raw string)
        checklist = _parse_checklist_response(response)
        
        if not checklist:
            # Fallback: create basic checklist from task description
            checklist = _create_fallback_checklist(title, description, files_involved)
        
        logger.info(f"[ChecklistGen] Generated {len(checklist)} checklist items for task {task_id}")
        return checklist
        
    except Exception as e:
        logger.error(f"[ChecklistGen] Failed to generate checklist for task {task_id}: {e}")
        # Return fallback checklist
        return _create_fallback_checklist(title, description, files_involved)


def _get_system_prompt(lane: str) -> str:
    """Get lane-specific system prompt for checklist generation."""
    lane_context = {
        "backend": (
            "You are a backend development planning expert. Break down backend tasks into "
            "file-by-file implementation steps covering models, services, routes, and tests."
        ),
        "frontend": (
            "You are a frontend development planning expert. Break down UI/UX tasks into "
            "component-by-component implementation steps covering pages, components, styles, and routing."
        ),
        "qa": (
            "You are a QA planning expert. Break down testing tasks into test-by-test "
            "implementation steps covering unit tests, integration tests, and documentation."
        ),
    }
    
    return f"""{lane_context.get(lane, "You are a software development planning expert.")}

Your job is to break down a high-level task into a detailed, actionable checklist.

**RULES:**
1. Each checklist item must be **atomic** - one clear action (e.g., "Create User model in models/user.py")
2. Items must be in **logical dependency order** - foundation first, then features
3. Be **specific** - mention file paths, function names, or components
4. Keep items **actionable** - start with verbs (Create, Implement, Add, Update, Test)
5. Aim for **5-10 items** - not too granular, not too high-level
6. Each item should take **10-30 minutes** to complete
7. **Architectural Fidelity** - If architecture blueprints (LLD/HLD) are provided, follow their exact entity schemas, table names, field types, and REST route paths.

**OUTPUT FORMAT:**
Return a JSON array of checklist items:

```json
[
  {{"text": "Create database model in backend/models/user.py with email, password fields", "completed": false}},
  {{"text": "Implement password hashing with bcrypt in user model", "completed": false}},
  {{"text": "Add user authentication service in backend/services/auth.py", "completed": false}}
]
```

Only return the JSON array, no other text."""


def _build_checklist_prompt(
    title: str,
    description: str,
    task_type: str,
    lane: str,
    files_involved: List[str],
    arch_context: str = "",
) -> str:
    """Build the user prompt for checklist generation."""
    
    files_str = ""
    if files_involved:
        files_str = "\n**Files to modify/create:**\n"
        for f in files_involved[:10]:  # Limit to 10 files
            files_str += f"- {f}\n"

    arch_str = ""
    if arch_context and arch_context.strip():
        arch_str = (
            f"\n**Authoritative Architecture Blueprint Specifications (from HLD/LLD):**\n"
            f"{arch_context.strip()}\n\n"
            f"*IMPORTANT: Use the exact table names, field schemas, API routes, and components specified in the architecture blueprint above.*\n"
        )
    
    return f"""**Task:** {title}

**Type:** {task_type}
**Lane:** {lane}

**Description:**
{description[:1000]}

{files_str}
{arch_str}
**Generate a step-by-step checklist** to complete this task.

Focus on the {lane} lane responsibilities:
- Backend: Database models, API endpoints, services, authentication
- Frontend: UI components, pages, routing, styling, state management
- QA: Test suites, test cases, documentation, validation

Break this down into 5-10 actionable steps."""


def _parse_checklist_response(response: Any) -> List[Dict[str, Any]]:
    """Parse LLM response into checklist items."""
    if hasattr(response, "content"):
        response = response.content
    if not isinstance(response, str):
        response = str(response or "")
    
    # Clean response - remove markdown fences
    response_clean = response.strip()
    if response_clean.startswith("```"):
        parts = response_clean.split("```")
        if len(parts) >= 2:
            response_clean = parts[1]
            if response_clean.startswith("json"):
                response_clean = response_clean[4:]
    
    try:
        # Try to parse as JSON
        parsed = json.loads(response_clean.strip())
        
        if isinstance(parsed, list):
            # Ensure each item has required fields
            checklist = []
            for item in parsed:
                if isinstance(item, dict) and "text" in item:
                    checklist.append({
                        "text": item["text"],
                        "completed": item.get("completed", False),
                    })
                elif isinstance(item, str):
                    checklist.append({
                        "text": item,
                        "completed": False,
                    })
            return checklist
            
    except json.JSONDecodeError:
        logger.warning("[ChecklistGen] Failed to parse JSON, trying line-by-line extraction")
        pass
    
    # Fallback: extract bullet points or numbered lists
    lines = response_clean.split("\n")
    checklist = []
    
    for line in lines:
        line = line.strip()
        # Match numbered lists (1., 2., etc.) or bullet points (-, *, •)
        if line and (
            (line[0].isdigit() and "." in line[:4]) or
            line.startswith("-") or
            line.startswith("*") or
            line.startswith("•")
        ):
            # Clean the text
            text = line.lstrip("0123456789.-*• ").strip()
            if len(text) > 10:  # Must be substantial
                checklist.append({
                    "text": text,
                    "completed": False,
                })
    
    return checklist


_FILE_RE = re.compile(
    r"[\w./\\-]+\.(?:py|ts|tsx|js|jsx|json|css|scss|html|vue|svelte|yaml|yml|toml|sql|sh|md)\b"
)


def build_tracker_tasks(
    checklist: List[Dict[str, Any]],
    files_involved: List[str] | None = None,
) -> List[Dict[str, Any]]:
    """Convert generated checklist items into TaskChecklistTracker task format.

    Tracker items follow the shape the existing plan-checklist tracker expects:
        {"task_id": int, "action": "edit", "file": str, "description": str}

    Items that mention a file path are file-bound edits; items without any
    recoverable file path become "guideline" steps (they render in the
    tracker banner as guidance and are auto-completed once all file tasks
    are done, so they never block completion).
    """
    known_files = [
        str(f).replace("\\", "/").lstrip("/")
        for f in (files_involved or [])
        if f
    ]
    tracker_tasks: List[Dict[str, Any]] = []
    task_idx = 1
    for item in checklist or []:
        if isinstance(item, dict):
            text = str(item.get("text", "")).strip()
        else:
            text = str(item).strip()
        if not text:
            continue

        candidates: List[str] = []
        for candidate in _FILE_RE.findall(text):
            cand = candidate.replace("\\", "/").lstrip("/")
            if not cand or len(cand) < 4:
                continue
            if cand not in candidates:
                candidates.append(cand)

        # Sort candidate files so known_files come first if any
        if candidates and known_files:
            candidates.sort(key=lambda c: 0 if any(k == c or k in c or c.endswith(k) for k in known_files) else 1)

        if not candidates:
            tracker_tasks.append({
                "task_id": task_idx,
                "action": "step",
                "file": "",
                "description": text,
                "guideline": True,
            })
            task_idx += 1
        elif len(candidates) == 1:
            tracker_tasks.append({
                "task_id": task_idx,
                "action": "edit",
                "file": candidates[0],
                "description": text,
                "guideline": False,
            })
            task_idx += 1
        else:
            # Multi-file checklist step: emit an atomic task per file so no file is dropped
            for c_file in candidates:
                tracker_tasks.append({
                    "task_id": task_idx,
                    "action": "edit",
                    "file": c_file,
                    "description": f"{text} (target file: {c_file})",
                    "guideline": False,
                })
                task_idx += 1
    return tracker_tasks


def _create_fallback_checklist(
    title: str,
    description: str,
    files_involved: List[str],
) -> List[Dict[str, Any]]:
    """Create a basic checklist when LLM generation fails."""
    
    checklist = []
    
    # Step 1: Planning
    checklist.append({
        "text": f"Plan implementation approach for: {title[:80]}",
        "completed": False,
    })
    
    # Step 2: File creation/modification
    if files_involved:
        for f in files_involved[:5]:  # Limit to 5 files
            checklist.append({
                "text": f"Implement changes in {f}",
                "completed": False,
            })
    else:
        checklist.append({
            "text": "Create/modify necessary files",
            "completed": False,
        })
    
    # Step 3: Integration
    checklist.append({
        "text": "Integrate with existing codebase",
        "completed": False,
    })
    
    # Step 4: Testing
    checklist.append({
        "text": "Test implementation and fix any issues",
        "completed": False,
    })
    
    # Step 5: Verification
    checklist.append({
        "text": "Verify build succeeds with no errors",
        "completed": False,
    })
    
    return checklist
