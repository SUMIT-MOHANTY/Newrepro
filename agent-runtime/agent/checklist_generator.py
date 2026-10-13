"""
Checklist Generator - Creates dynamic checklists for tasks before agent execution.

When an agent is assigned to a task, this generator breaks down the task into
step-by-step checklist items that will be stored in the database and tracked.
"""
import json
import logging
import re
from typing import Any, Dict, List
from agent.model_router import ModelRouter, TaskType
from infrastructure.llm_client import LLMClient

logger = logging.getLogger(__name__)


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
    
    # Build the prompt for checklist generation
    prompt = _build_checklist_prompt(
        title=title,
        description=description,
        task_type=task_type,
        lane=lane,
        files_involved=files_involved,
    )
    
    # Get LLM config
    config = model_router.route(TaskType.planning)
    llm_client = LLMClient(
        model=config.model,
        api_key=config.api_key,
        api_url=config.api_url,
        max_tokens=2000,
        temperature=0.3,  # Lower temperature for structured output
    )
    
    try:
        response = await llm_client.complete(
            messages=[
                {"role": "system", "content": _get_system_prompt(lane)},
                {"role": "user", "content": prompt},
            ],
            timeout=30.0,
        )
        
        # Parse checklist from response
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
) -> str:
    """Build the user prompt for checklist generation."""
    
    files_str = ""
    if files_involved:
        files_str = "\n**Files to modify/create:**\n"
        for f in files_involved[:10]:  # Limit to 10 files
            files_str += f"- {f}\n"
    
    return f"""**Task:** {title}

**Type:** {task_type}
**Lane:** {lane}

**Description:**
{description[:1000]}

{files_str}

**Generate a step-by-step checklist** to complete this task.

Focus on the {lane} lane responsibilities:
- Backend: Database models, API endpoints, services, authentication
- Frontend: UI components, pages, routing, styling, state management
- QA: Test suites, test cases, documentation, validation

Break this down into 5-10 actionable steps."""


def _parse_checklist_response(response: str) -> List[Dict[str, Any]]:
    """Parse LLM response into checklist items."""
    
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
    for idx, item in enumerate(checklist or [], start=1):
        if isinstance(item, dict):
            text = str(item.get("text", "")).strip()
        else:
            text = str(item).strip()
        if not text:
            continue

        file_path = ""
        for candidate in _FILE_RE.findall(text):
            cand = candidate.replace("\\", "/").lstrip("/")
            if not cand or len(cand) < 4:
                continue
            # Prefer candidates that map to a known involved file.
            if any(k == cand or k in cand or cand.endswith(k) for k in known_files):
                file_path = cand
                break
            if not file_path:
                file_path = cand
        tracker_tasks.append({
            "task_id": idx,
            "action": "edit" if file_path else "step",
            "file": file_path,
            "description": text,
            "guideline": not file_path,
        })
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
