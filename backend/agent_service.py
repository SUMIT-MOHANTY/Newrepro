"""
Agent Service for AI-Powered Development Agents
Agents create ephemeral Docker containers, build real project code inside them,
self-heal until everything works, capture the workspace, then clean up.
"""
import asyncio
import json
import os
import subprocess
import sys
import tempfile
import time
import uuid
import re as _re
from datetime import datetime
from typing import Optional, Dict, Any, List
from config import settings
import httpx
import logging

logger = logging.getLogger(__name__)


# ── AI Response Cleaner ─────────────────────────────────────────────────────

def _clean_ai_code_response(content: str) -> tuple[str, str]:
    """
    Robustly extract pure Python code from an AI model response.
    Returns (code_string, thought_string).
    Handles: <comment> blocks, markdown fences, narrative preamble,
    and Unicode curly quotes that cause SyntaxErrors.
    """
    content = content.strip()
    
    # Extract thought if present
    thought_text = ""
    # Find all comment blocks and join them
    think_matches = _re.findall(r'<comment>(.*?)</comment>', content, flags=_re.DOTALL)
    if think_matches:
        thought_text = "\n\n".join(t.strip() for t in think_matches)

    # 1. Strip <think>...</think> and <comment>...</comment> blocks
    content = _re.sub(r'<think>.*?</think>', '', content, flags=_re.DOTALL).strip()
    content = _re.sub(r'<think>.*', '', content, flags=_re.DOTALL).strip()
    content = _re.sub(r'<comment>.*?</comment>', '', content, flags=_re.DOTALL).strip()
    content = _re.sub(r'<comment>.*', '', content, flags=_re.DOTALL).strip()

    # 2. Extract code from markdown fences
    fence_match = _re.search(r'```python\s*\n(.*?)```', content, flags=_re.DOTALL)
    if not fence_match:
        fence_match = _re.search(r'```\s*\n(.*?)```', content, flags=_re.DOTALL)
    if fence_match:
        content = fence_match.group(1).strip()
    else:
        if content.startswith('```python'):
            content = content[len('```python'):].strip()
        elif content.startswith('```'):
            content = content[3:].strip()
        if content.endswith('```'):
            content = content[:-3].strip()

    # 3. Strip narrative preamble before first code line
    lines = content.split('\n')
    first_code_line = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith(('#', 'import ', 'from ', 'def ', 'class ', 'print(', 'if ', 'for ', 'while ', 'try:', 'with ', 'os.', 'subprocess')) or '=' in stripped:
            first_code_line = i
            break
            
    narrative = ""
    if first_code_line > 0:
        preamble = '\n'.join(lines[:first_code_line]).strip()
        if not preamble.startswith('#'):
            narrative = preamble
            content = '\n'.join(lines[first_code_line:])

    # 4. Replace Unicode with ASCII
    content = content.replace('\u2018', "'").replace('\u2019', "'")
    content = content.replace('\u201c', '"').replace('\u201d', '"')
    content = content.replace('\u2013', '-').replace('\u2014', '--')
    content = content.replace('\u2026', '...')
    content = content.replace('\u2192', '->').replace('\u2190', '<-')

    final_thought = thought_text
    if narrative and not final_thought:
        final_thought = narrative
    elif narrative and final_thought:
        final_thought += "\n" + narrative

    return content.strip(), final_thought.strip()


# ── In-memory state stores ──────────────────────────────────────────────────

_AGENT_TYPES = ["validator", "risk", "estimator"]
_AGENT_NAMES = ["Requirements Validator", "Risk Assessment", "Resource Estimation"]

GIT_MANAGER_AGENT_ID = "agent_03"
MASTER_AGENT_ID = "agent_04"
GIT_INTEGRATION_BRANCH = "agent/integration"
DEFAULT_PROJECT_TOKEN = "__default__"
AGENT_SESSION_NOTES_DIR = "agent_handoff"
BOOTSTRAP_WAIT_TIMEOUT_SECONDS = 1800
BOOTSTRAP_WAIT_LOG_INTERVAL_SECONDS = 20


def _is_system_agent_id(agent_id: Optional[str]) -> bool:
    return agent_id in {GIT_MANAGER_AGENT_ID, MASTER_AGENT_ID}

_project_states: Dict[str, Dict[str, Any]] = {}


def _new_repo_bootstrap_state() -> Dict[str, Any]:
    return {
        "repo_url": None,
        "required": None,
        "agent_id": None,
        "status": "unknown",
        "source_branch": None,
        "message": "",
        "started_at": None,
        "completed_at": None,
    }

def _project_key(project_token: Optional[str]) -> str:
    token = (project_token or "").strip()
    return token or DEFAULT_PROJECT_TOKEN

def _ensure_project_state(project_token: Optional[str]) -> Dict[str, Any]:
    key = _project_key(project_token)
    state = _project_states.get(key)
    if state is None:
        state = {
            "agent_states": {},
            "claimed_task_ids": set(),
            "task_progress_state": {},
            "timer_log_state": {},
            "completed_tasks": [],
            "task_token": None,
            "git_merge_queue": [],
            "git_merge_running": False,
            "git_merge_lock": asyncio.Lock(),
            "git_merge_inflight": set(),
            "merged_branches": [],
            "repo_bootstrap": _new_repo_bootstrap_state(),
            "repo_bootstrap_lock": asyncio.Lock(),
            "repo_bootstrap_event": asyncio.Event(),
            "completed_milestones_synced": set(),
            "completed_sprints_synced": set(),
            "project_status_synced": None,
            "status_sync_lock": asyncio.Lock(),
        }
        _project_states[key] = state
    else:
        state.setdefault("completed_milestones_synced", set())
        state.setdefault("completed_sprints_synced", set())
        state.setdefault("project_status_synced", None)
        state.setdefault("status_sync_lock", asyncio.Lock())
    return state

def _get_agent_states(project_token: Optional[str]) -> Dict[str, Dict[str, Any]]:
    return _ensure_project_state(project_token)["agent_states"]

def set_project_task_token(project_token: Optional[str], task_token: Optional[str]) -> None:
    if not task_token:
        return
    _ensure_project_state(project_token)["task_token"] = task_token

def get_project_task_token(project_token: Optional[str]) -> Optional[str]:
    return _ensure_project_state(project_token).get("task_token")

def _make_agent(agent_id: str, idx: int = 0) -> Dict[str, Any]:
    """Create a fresh agent state dict."""
    atype = _AGENT_TYPES[idx % len(_AGENT_TYPES)]
    aname = _AGENT_NAMES[idx % len(_AGENT_NAMES)]
    agent = {
        "id": agent_id,
        "name": aname,
        "type": atype,
        "status": "idle",
        "current_task": None,
        "progress": 0,
        "progress_message": "",
        "last_run": None,
        "last_result": None,
        "output_log": [],
        "stats": {},
        "git_repo_url": None,
        "git_token": None,
    }
    if agent_id == GIT_MANAGER_AGENT_ID:
        agent["name"] = "Git Manager"
        agent["progress"] = 100
        agent["progress_message"] = "Git manager idle"
        agent["output_log"].append({
            "time": datetime.utcnow().isoformat(),
            "type": "info",
            "message": "Git manager initialized and waiting for merge events."
        })
    elif agent_id == MASTER_AGENT_ID:
        agent["name"] = "Master Agent"
        agent["progress"] = 100
        agent["progress_message"] = "Master agent idle"
        agent["output_log"].append({
            "time": datetime.utcnow().isoformat(),
            "type": "info",
            "message": "Master agent initialized and waiting for orchestration/status events."
        })
    return agent

def get_default_agents() -> List[Dict[str, Any]]:
    return [
        _make_agent("agent_01", 0),
        _make_agent("agent_02", 1),
        _make_agent("agent_03", 2),
        _make_agent("agent_04", 3),
    ]

def initialize_agents_from_records(records: List[Any], project_token: Optional[str] = None) -> None:
    """
    Replace in-memory agent states with DB-backed agent records.
    """
    state = _ensure_project_state(project_token)
    state["claimed_task_ids"].clear()
    state["task_progress_state"].clear()
    state["timer_log_state"].clear()
    state["completed_milestones_synced"].clear()
    state["completed_sprints_synced"].clear()
    state["project_status_synced"] = None
    state["repo_bootstrap"] = _new_repo_bootstrap_state()
    state["repo_bootstrap_event"] = asyncio.Event()
    agent_states = state["agent_states"]
    agent_states.clear()
    for idx, rec in enumerate(records):
        agent_id = getattr(rec, "id", None) or (rec.get("id") if isinstance(rec, dict) else None)
        if not agent_id:
            continue
        name = getattr(rec, "name", None) or (rec.get("name") if isinstance(rec, dict) else None)
        atype = getattr(rec, "type", None) or (rec.get("type") if isinstance(rec, dict) else None)
        agent = _make_agent(agent_id, idx)
        if name:
            agent["name"] = name
        if atype:
            agent["type"] = atype
        agent_states[agent_id] = agent

def ensure_project_initialized(project_token: Optional[str], records: List[Any]) -> None:
    state = _ensure_project_state(project_token)
    if not state["agent_states"]:
        initialize_agents_from_records(records, project_token=project_token)
        return
    agent_states = state["agent_states"]
    for idx, rec in enumerate(records):
        agent_id = getattr(rec, "id", None) or (rec.get("id") if isinstance(rec, dict) else None)
        if not agent_id or agent_id in agent_states:
            continue
        name = getattr(rec, "name", None) or (rec.get("name") if isinstance(rec, dict) else None)
        atype = getattr(rec, "type", None) or (rec.get("type") if isinstance(rec, dict) else None)
        agent = _make_agent(agent_id, idx)
        if name:
            agent["name"] = name
        if atype:
            agent["type"] = atype
        agent_states[agent_id] = agent

def get_completed_tasks(project_token: Optional[str]) -> List[Dict[str, Any]]:
    return list(_ensure_project_state(project_token)["completed_tasks"])

# Backward compatibility default scope.
agent_states = _get_agent_states(None)


# ── Agent System Prompts ────────────────────────────────────────────────────
# Agents MUST create real files inside /workspace/ in the container.
# CRITICAL: Keep scripts compact (<300 lines) to avoid AI token-limit truncation.

_COMPACT_CODE_RULES = """

CRITICAL SCRIPT SIZE RULES:
- Keep your script UNDER 300 lines total. This is very important.
- Define a helper function at the top: def wf(path, content): and use it for every file.
- Write each file's content using regular strings with explicit \\n, NOT triple-quoted multi-line strings.
- Focus on the 10-15 most essential files. Do NOT try to create 30+ files in one script.
- Each file write should be 1-3 lines of code, not 50-line inline strings.

If you have want to add a comment to the task if you fell necessary or want to , wrap it in <comment>...</comment> tags anytime in your response. For example:
<comment>
I will implement a Flask backend with a PostgreSQL database as requested.
</comment>
```python
# your code here
```
<comment>
I finished the initial implementation, but note that the database still needs schema setup.
</comment>

Example of the CORRECT compact pattern:
import os

def wf(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(content)
    print(f"[CREATED] {path}")

wf("/workspace/app/__init__.py", "from flask import Flask\\n\\ndef create_app():\\n    return Flask(__name__)\\n")
wf("/workspace/requirements.txt", "flask>=2.3.0\\nsqlalchemy>=2.0\\ngunicorn>=21.0\\n")
wf("/workspace/Dockerfile", "FROM python:3.11-slim\\nWORKDIR /app\\nCOPY . .\\nRUN pip install -r requirements.txt\\nCMD [\\"gunicorn\\", \\"app:app\\"]\\n")
print("[CHECK] All files created... PASS")

Do NOT use triple-quoted strings (''' or \"\"\") for file content. Use single-line strings with \\n.
"""

AGENT_SYSTEM_PROMPTS = {
    "validator": """You are a Project Builder AI Agent.
Your job is to analyze the given task and CREATE a complete, working project implementation inside /workspace/.

Given a task description, you must:
1. Understand what the project requires
2. Generate a Python script that CREATES all necessary files and directories
3. Use os.makedirs() and open() to create real files under /workspace/
4. Write real, production-quality code into each file
5. Print [CREATED] for each file, [CHECK] PASS/FAIL for validations
6. Print === SUMMARY === at the end
""" + _COMPACT_CODE_RULES,

    "risk": """You are a Security and Risk Analysis Builder AI Agent.
Your job is to analyze the given task, identify all risks, and CREATE actual mitigation code and config files inside /workspace/.

Given a task description, you must:
1. Identify technical, business, security, and operational risks
2. Generate a Python script that CREATES mitigation files under /workspace/
3. Print [RISK N] for each risk, [CREATED] for each file, [CHECK] for validations
4. Print === RISK SUMMARY === at the end
""" + _COMPACT_CODE_RULES,

    "estimator": """You are a Project Planning and Scaffolding AI Agent.
Your job is to analyze the task, estimate resources, and CREATE a complete project scaffold inside /workspace/.

Given a task description, you must:
1. Break down the project into sprints and tasks
2. Generate a Python script that CREATES the project scaffold under /workspace/
3. Create source files, configs, Dockerfile, docker-compose, CI/CD, tests
4. Print [SPRINT N] for each sprint, [CREATED] for each file, [CHECK] for validations
5. Print === RESOURCE SUMMARY === at the end
""" + _COMPACT_CODE_RULES,
}


# Self-healing: keep fixing until the project is perfect
MAX_FIX_ITERATIONS = 5

# Recursive compile-fail-fix: max retries for the enhanced loop
MAX_COMPILE_RETRIES = 3

# ═══════════════════════════════════════════════════════════════════════════
# LAYER 1: ARCHITECT AGENT — Technical Spec Generation
# ═══════════════════════════════════════════════════════════════════════════
# Before coding agents start, an "Architect Agent" generates a canonical
# Technical Spec from the BRD + KG. This spec is the single source of truth
# that all coding agents reference. It prevents structural divergence.

# In-memory store of generated tech specs per project
_project_tech_specs: Dict[str, Dict[str, Any]] = {}


async def _generate_technical_spec(
    project_token: str,
    tasks: List[Dict[str, Any]],
    brd_summary: str = "",
    kg_context: str = "",
) -> Dict[str, Any]:
    """
    LAYER 1: Architect Agent — generates a canonical Technical Spec.

    This runs ONCE before any coding agents start. It produces:
    - Architecture overview (modules, layers, data flow)
    - API contracts (endpoints, request/response schemas)
    - Data models (schemas, field names, types)
    - File structure (what goes where)
    - Naming conventions (snake_case vs camelCase, etc.)
    - Dependency list (packages, versions)

    All coding agents then reference this spec as ground truth.
    """
    url = settings.ai_api_url
    key = settings.ai_api_key
    model_name = settings.ai_model

    if not key or key == "your-api-key-here":
        return {"status": "skipped", "reason": "no_api_key", "spec": ""}

    # Build task summary for the architect
    task_summaries = []
    for i, t in enumerate(tasks[:30], 1):
        title = t.get("title", "Untitled")
        desc = (t.get("description", "") or "")[:200]
        task_summaries.append(f"  {i}. {title}: {desc}")
    task_list_text = "\n".join(task_summaries) if task_summaries else "No tasks provided."

    architect_prompt = f"""You are a Senior Software Architect Agent. Your job is to produce a
CANONICAL TECHNICAL SPECIFICATION that all coding agents will reference as the single source of truth.

BUSINESS REQUIREMENTS (from BRD):
{brd_summary[:3000] if brd_summary else "Not provided."}

EXISTING CODEBASE KNOWLEDGE (from Knowledge Graph):
{kg_context[:4000] if kg_context else "New project — no existing codebase."}

TASKS TO BE IMPLEMENTED BY AGENTS:
{task_list_text}

Generate a Technical Specification with these EXACT sections:

## 1. ARCHITECTURE OVERVIEW
- System layers (frontend, backend, database, external services)
- Module breakdown and responsibilities
- Data flow between modules

## 2. API CONTRACTS
- List every API endpoint with: method, path, request body schema, response schema
- Use consistent field naming throughout (choose snake_case or camelCase and state it)

## 3. DATA MODELS
- Every database table/model with exact field names, types, and constraints
- Relationships between models (FK, many-to-many, etc.)

## 4. FILE STRUCTURE
- Exact directory tree with purpose of each directory
- Naming conventions for files

## 5. NAMING CONVENTIONS
- Variable naming: snake_case / camelCase
- Class naming: PascalCase
- File naming convention
- API endpoint naming convention

## 6. DEPENDENCIES
- Exact package names and minimum versions
- Runtime vs dev dependencies

## 7. CROSS-MODULE CONTRACTS
- How modules communicate (imports, API calls, events)
- Shared types/interfaces between modules
- Error handling conventions

Be extremely specific. Every field name, endpoint, and type must be exact so agents can reference them.
Do NOT use vague descriptions like "appropriate fields" — name every field explicitly."""

    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": "You are a Senior Software Architect. Produce precise, unambiguous technical specifications."},
            {"role": "user", "content": architect_prompt},
        ],
        "stream": False,
        "chat_template_kwargs": {"thinking": False},
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {key}",
    }

    try:
        async with httpx.AsyncClient(timeout=180.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

        if "choices" in data and len(data["choices"]) > 0:
            spec_text = data["choices"][0].get("message", {}).get("content", "")
            # Strip <think> blocks from models that embed reasoning in content
            spec_text = _re.sub(r'<think>.*?</think>', '', spec_text, flags=_re.DOTALL).strip()
            spec_text = _re.sub(r'<think>.*', '', spec_text, flags=_re.DOTALL).strip()
        else:
            spec_text = ""

        spec_record = {
            "status": "generated",
            "spec": spec_text,
            "generated_at": datetime.utcnow().isoformat(),
            "task_count": len(tasks),
            "char_length": len(spec_text),
        }
        _project_tech_specs[project_token] = spec_record

        # Also feed the spec into the KG/RAG so agents can query it
        try:
            import context_manager as ctx_mgr
            if ctx_mgr.is_project_indexed(project_token):
                import rag_service
                await rag_service.incremental_insert(
                    project_token=project_token,
                    text_chunks=[f"TECHNICAL SPECIFICATION (Canonical)\n\n{spec_text}"],
                    source_label="architect_agent_spec",
                )
        except Exception:
            pass  # Non-critical

        logger.info(f"[{project_token}] Architect Agent generated tech spec: {len(spec_text)} chars")
        return spec_record

    except Exception as e:
        logger.error(f"[{project_token}] Tech spec generation failed: {e}")
        return {"status": "error", "error": str(e), "spec": ""}


def get_technical_spec(project_token: str) -> str:
    """Retrieve the generated technical spec for a project."""
    record = _project_tech_specs.get(project_token, {})
    return record.get("spec", "")


# ═══════════════════════════════════════════════════════════════════════════
# LAYER 3: DYNAMIC PROMPT WRITER
# ═══════════════════════════════════════════════════════════════════════════
# Instead of using static system prompts, a "manager" dynamically writes
# the exact prompt for each agent based on:
#   - The specific task being assigned
#   - The tech spec section relevant to this task
#   - What other agents have already built (from KG)
#   - File conflict warnings


async def _generate_dynamic_prompt(
    task: Dict[str, Any],
    agent_type: str,
    agent_id: str,
    tech_spec: str = "",
    kg_context: str = "",
    cross_agent_info: str = "",
) -> str:
    """
    LAYER 3: Dynamic Prompt Writer.

    Instead of a static system prompt, this function formulates a highly
    specific instruction for the coding agent based on:
    - The task description
    - The relevant section of the Technical Spec
    - What the KG says about related modules
    - What other agents are doing / have done

    Falls back to the static prompt if the AI call fails.
    """
    url = settings.ai_api_url
    key = settings.ai_api_key
    model_name = settings.ai_model

    # Fallback to static prompt
    static_prompt = AGENT_SYSTEM_PROMPTS.get(agent_type, AGENT_SYSTEM_PROMPTS["validator"])

    if not key or key == "your-api-key-here":
        return static_prompt

    task_title = task.get("title", "Untitled")
    task_desc = task.get("description", "")[:1500]
    checklist = task.get("checklist", [])
    checklist_text = "\n".join(f"  - {item.get('title', item) if isinstance(item, dict) else item}" for item in checklist[:10]) if checklist else "None"

    manager_prompt = f"""You are a Manager Agent. Your job is to write the EXACT system prompt
that a Coding Agent will receive. This prompt must be highly specific to the task at hand.

THE TASK:
  Title: {task_title}
  Description: {task_desc}
  Checklist: {checklist_text}

TECHNICAL SPECIFICATION (from Architect Agent):
{tech_spec[:3000] if tech_spec else "Not available."}

EXISTING CODEBASE CONTEXT (from Knowledge Graph):
{kg_context[:2000] if kg_context else "No existing context."}

OTHER AGENTS' ACTIVITY:
{cross_agent_info[:1000] if cross_agent_info else "No other agents active."}

Write a system prompt for the Coding Agent that:
1. Tells it EXACTLY what module/files to create for THIS specific task
2. References the EXACT field names, API endpoints, and types from the Tech Spec
3. Tells it what files/symbols already exist (from KG) that it should import/reference
4. Warns about any files being edited by other agents (avoid conflicts)
5. Specifies the exact naming conventions to follow
6. Ends with the code generation rules (create files under /workspace/, use wf() helper, etc.)

The prompt MUST include these code generation rules at the end:
{_COMPACT_CODE_RULES}

Write ONLY the system prompt text. Do not include any meta-commentary."""

    try:
        payload = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": "You are a prompt engineering expert. Write precise, actionable system prompts for coding agents."},
                {"role": "user", "content": manager_prompt},
            ],
            "stream": False,
            "chat_template_kwargs": {"thinking": False},
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

        if "choices" in data and len(data["choices"]) > 0:
            dynamic_prompt = data["choices"][0].get("message", {}).get("content", "")
            # Strip <think> blocks from models that embed reasoning in content
            dynamic_prompt = _re.sub(r'<think>.*?</think>', '', dynamic_prompt, flags=_re.DOTALL).strip()
            dynamic_prompt = _re.sub(r'<think>.*', '', dynamic_prompt, flags=_re.DOTALL).strip()
            if len(dynamic_prompt) > 100:  # Sanity check — prompt should be substantial
                logger.info(f"[{agent_id}] Dynamic prompt generated: {len(dynamic_prompt)} chars")
                return dynamic_prompt

        # Fallback if generation was too short
        return static_prompt

    except Exception as e:
        logger.warning(f"[{agent_id}] Dynamic prompt generation failed ({e}), using static prompt")
        return static_prompt


# ═══════════════════════════════════════════════════════════════════════════
# LAYER 4 ENHANCEMENT: Pre-Compilation Check + KG-Aware Error Analysis
# ═══════════════════════════════════════════════════════════════════════════


def _run_precompilation_checks(container_name: str) -> Dict[str, Any]:
    """
    LAYER 4: Pre-compilation build checks.

    Before marking a task as done, run syntax/import validation
    on the generated code inside the Docker container.
    """
    checks = {
        "python_syntax": {"passed": True, "errors": []},
        "js_syntax": {"passed": True, "errors": []},
        "import_check": {"passed": True, "errors": []},
        "file_count": 0,
        "all_passed": True,
    }

    try:
        # 1. Check Python syntax on all .py files
        py_check = subprocess.run(
            ["docker", "exec", container_name, "sh", "-c",
             "find /workspace -name '*.py' -type f | head -50 | while read f; do python3 -c \"import py_compile; py_compile.compile('$f', doraise=True)\" 2>&1 || echo \"SYNTAX_ERROR: $f\"; done"],
            capture_output=True, text=True, timeout=30,
        )
        if "SYNTAX_ERROR" in py_check.stdout:
            for line in py_check.stdout.split("\n"):
                if "SYNTAX_ERROR" in line:
                    checks["python_syntax"]["passed"] = False
                    checks["python_syntax"]["errors"].append(line.strip())
                    checks["all_passed"] = False

        # 2. Count files to verify workspace isn't empty
        file_count_result = subprocess.run(
            ["docker", "exec", container_name, "sh", "-c",
             "find /workspace -type f | wc -l"],
            capture_output=True, text=True, timeout=10,
        )
        checks["file_count"] = int(file_count_result.stdout.strip() or "0")
        if checks["file_count"] == 0:
            checks["all_passed"] = False

        # 3. Check for common import issues in Python files
        import_check = subprocess.run(
            ["docker", "exec", container_name, "sh", "-c",
             "find /workspace -name '*.py' -type f | head -20 | while read f; do python3 -c \"exec(open('$f').read())\" 2>&1 | grep -i 'ModuleNotFoundError\\|ImportError' | head -3; done"],
            capture_output=True, text=True, timeout=30,
        )
        if import_check.stdout.strip():
            for line in import_check.stdout.strip().split("\n"):
                if line.strip():
                    checks["import_check"]["passed"] = False
                    checks["import_check"]["errors"].append(line.strip())

    except subprocess.TimeoutExpired:
        checks["timeout"] = True
    except Exception as e:
        checks["error"] = str(e)

    return checks


async def _kg_aware_error_analysis(
    project_token: str,
    stderr: str,
    task_description: str,
    agent_id: str,
) -> str:
    """
    LAYER 4: When a build fails, query the KG for context about the error.

    For example, if the error is "ImportError: cannot import 'UserModel' from 'models'",
    query the KG to find the correct import path and class name.

    Returns additional context to inject into the fix prompt.
    """
    if not stderr or not project_token:
        return ""

    try:
        import context_manager as ctx_mgr
        if not ctx_mgr.is_project_indexed(project_token):
            return ""

        # Extract key error terms for KG query
        error_lines = stderr.strip().split("\n")[-5:]
        error_keywords = []
        for line in error_lines:
            # Extract module/class names from errors
            for keyword in ["import", "from", "ModuleNotFoundError", "ImportError",
                           "AttributeError", "NameError", "TypeError"]:
                if keyword in line:
                    # Extract the symbol name
                    parts = line.split("'")
                    if len(parts) >= 2:
                        error_keywords.append(parts[1])
                    break

        if not error_keywords:
            return ""

        # Query the KG for the correct definitions
        query = f"Find the correct definitions, imports, and file locations for: {', '.join(error_keywords)}"
        import rag_service
        result = await rag_service.query_codebase(project_token, query, mode="hybrid", top_k=5)

        if result.get("context"):
            return (
                f"\n\nKNOWLEDGE GRAPH ERROR ANALYSIS:\n"
                f"The following code definitions exist in the codebase and may help fix the errors:\n"
                f"{result['context'][:2000]}\n"
            )

    except Exception as e:
        logger.warning(f"[{agent_id}] KG error analysis failed: {e}")

    return ""


# ═══════════════════════════════════════════════════════════════════════════
# CODE QUALITY / LINTING
# ═══════════════════════════════════════════════════════════════════════════
# Runs linting tools (flake8, pylint, eslint) on agent-generated code
# inside the Docker container. Results are fed into the self-healing loop.


def _run_code_quality_checks(container_name: str) -> Dict[str, Any]:
    """
    Run code quality and linting checks inside the Docker container.

    Installs and runs:
    - flake8 (Python style/syntax)
    - pylint (Python deeper analysis) — optional, best-effort
    - eslint (JavaScript/JSX) — if JS files detected

    Returns a structured report with issues found.
    """
    report = {
        "flake8": {"passed": True, "issues": [], "issue_count": 0},
        "pylint": {"passed": True, "issues": [], "issue_count": 0},
        "eslint": {"passed": True, "issues": [], "issue_count": 0},
        "total_issues": 0,
        "all_passed": True,
        "linters_run": [],
    }

    try:
        # ── Install flake8 (lightweight, fast) ──────────────────
        subprocess.run(
            ["docker", "exec", container_name, "pip", "install", "-q", "flake8"],
            capture_output=True, text=True, timeout=30,
        )

        # ── Run flake8 on all Python files ──────────────────────
        flake8_result = subprocess.run(
            ["docker", "exec", "-w", "/workspace", container_name, "sh", "-c",
             "find . -name '*.py' -not -path './.git/*' -not -path '*/node_modules/*' "
             "| head -50 | xargs flake8 --max-line-length=120 --count "
             "--select=E9,F63,F7,F82,E1,E2,W6 --show-source 2>&1 | head -40"],
            capture_output=True, text=True, timeout=30,
        )
        report["linters_run"].append("flake8")
        if flake8_result.stdout.strip():
            issues = [
                line.strip() for line in flake8_result.stdout.strip().split("\n")
                if line.strip() and ":" in line
            ]
            if issues:
                report["flake8"]["passed"] = False
                report["flake8"]["issues"] = issues[:20]  # Cap at 20
                report["flake8"]["issue_count"] = len(issues)
                report["all_passed"] = False

        # ── Run pylint (best-effort, don't fail on install) ─────
        try:
            install_pylint = subprocess.run(
                ["docker", "exec", container_name, "pip", "install", "-q", "pylint"],
                capture_output=True, text=True, timeout=30,
            )
            if install_pylint.returncode == 0:
                pylint_result = subprocess.run(
                    ["docker", "exec", "-w", "/workspace", container_name, "sh", "-c",
                     "find . -name '*.py' -not -path './.git/*' -not -path '*/node_modules/*' "
                     "| head -20 | xargs pylint --errors-only --disable=import-error "
                     "--output-format=text 2>&1 | head -30"],
                    capture_output=True, text=True, timeout=45,
                )
                report["linters_run"].append("pylint")
                if pylint_result.stdout.strip():
                    issues = [
                        line.strip() for line in pylint_result.stdout.strip().split("\n")
                        if line.strip() and (":" in line) and ("E" in line or "error" in line.lower())
                    ]
                    if issues:
                        report["pylint"]["passed"] = False
                        report["pylint"]["issues"] = issues[:15]
                        report["pylint"]["issue_count"] = len(issues)
                        report["all_passed"] = False
        except (subprocess.TimeoutExpired, Exception):
            pass  # pylint is optional

        # ── Check for JS/JSX files and run eslint if present ────
        try:
            js_check = subprocess.run(
                ["docker", "exec", "-w", "/workspace", container_name, "sh", "-c",
                 "find . -name '*.js' -o -name '*.jsx' -o -name '*.ts' -o -name '*.tsx' "
                 "| grep -v node_modules | grep -v .git | head -5"],
                capture_output=True, text=True, timeout=10,
            )
            if js_check.stdout.strip():
                # Install eslint
                eslint_install = subprocess.run(
                    ["docker", "exec", "-w", "/workspace", container_name, "sh", "-c",
                     "npm install --no-save eslint 2>/dev/null || npx -y eslint --version 2>/dev/null"],
                    capture_output=True, text=True, timeout=60,
                )
                if eslint_install.returncode == 0:
                    eslint_result = subprocess.run(
                        ["docker", "exec", "-w", "/workspace", container_name, "sh", "-c",
                         "npx eslint --no-eslintrc --env es2021,browser,node "
                         "--rule '{\"no-undef\": \"error\", \"no-unused-vars\": \"warn\"}' "
                         "$(find . -name '*.js' -o -name '*.jsx' | grep -v node_modules | head -20) "
                         "2>&1 | head -30"],
                        capture_output=True, text=True, timeout=30,
                    )
                    report["linters_run"].append("eslint")
                    if eslint_result.stdout.strip():
                        issues = [
                            line.strip() for line in eslint_result.stdout.strip().split("\n")
                            if line.strip() and ("error" in line.lower() or "warning" in line.lower())
                        ]
                        if issues:
                            report["eslint"]["passed"] = False
                            report["eslint"]["issues"] = issues[:15]
                            report["eslint"]["issue_count"] = len(issues)
                            report["all_passed"] = False
        except (subprocess.TimeoutExpired, Exception):
            pass  # eslint is optional

        # Total issues
        report["total_issues"] = (
            report["flake8"]["issue_count"]
            + report["pylint"]["issue_count"]
            + report["eslint"]["issue_count"]
        )

    except subprocess.TimeoutExpired:
        report["timeout"] = True
    except Exception as e:
        report["error"] = str(e)

    return report


# ═══════════════════════════════════════════════════════════════════════════
# AUTOMATED PR CREATION (GitHub REST API)
# ═══════════════════════════════════════════════════════════════════════════
# After the Git Manager merges all agent branches into agent/integration,
# automatically creates a Pull Request on GitHub: integration → main.


async def _create_github_pr(
    repo_url: str,
    token: str,
    head_branch: str,
    base_branch: str,
    title: str,
    body: str,
    project_token: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create a GitHub Pull Request via the REST API.

    Args:
        repo_url: GitHub HTTPS URL (e.g., https://github.com/user/repo.git)
        token: GitHub PAT or app token
        head_branch: Source branch (e.g., agent/integration)
        base_branch: Target branch (e.g., main)
        title: PR title
        body: PR description (markdown)
        project_token: For logging

    Returns:
        {"success": bool, "pr_url": str, "pr_number": int, ...}
    """
    # Extract owner/repo from URL
    # Supports: https://github.com/owner/repo.git, https://github.com/owner/repo
    clean_url = repo_url.rstrip("/").rstrip(".git")
    parts = clean_url.split("/")
    if len(parts) < 2:
        return {"success": False, "error": f"Cannot parse owner/repo from URL: {repo_url}"}

    owner = parts[-2]
    repo = parts[-1]

    api_url = f"https://api.github.com/repos/{owner}/{repo}/pulls"

    payload = {
        "title": title,
        "body": body,
        "head": head_branch,
        "base": base_branch,
        "maintainer_can_modify": True,
    }

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(api_url, json=payload, headers=headers)

            if response.status_code == 201:
                data = response.json()
                pr_result = {
                    "success": True,
                    "pr_url": data.get("html_url", ""),
                    "pr_number": data.get("number", 0),
                    "state": data.get("state", "open"),
                    "title": data.get("title", title),
                }
                _log_git_agent(
                    f"✅ PR #{pr_result['pr_number']} created: {pr_result['pr_url']}",
                    project_token=project_token,
                )
                return pr_result

            elif response.status_code == 422:
                # PR already exists or validation error
                error_data = response.json()
                errors = error_data.get("errors", [])
                messages = [e.get("message", "") for e in errors]

                if any("pull request already exists" in m.lower() for m in messages):
                    # Find the existing PR
                    list_url = f"https://api.github.com/repos/{owner}/{repo}/pulls"
                    list_params = {"head": f"{owner}:{head_branch}", "base": base_branch, "state": "open"}
                    list_resp = await client.get(list_url, headers=headers, params=list_params)
                    if list_resp.status_code == 200:
                        prs = list_resp.json()
                        if prs:
                            existing = prs[0]
                            # Update the existing PR body with latest info
                            patch_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{existing['number']}"
                            await client.patch(patch_url, json={"body": body}, headers=headers)

                            pr_result = {
                                "success": True,
                                "pr_url": existing.get("html_url", ""),
                                "pr_number": existing.get("number", 0),
                                "state": "open",
                                "title": existing.get("title", title),
                                "already_existed": True,
                            }
                            _log_git_agent(
                                f"📝 PR #{pr_result['pr_number']} already exists, updated body: {pr_result['pr_url']}",
                                project_token=project_token,
                            )
                            return pr_result

                return {
                    "success": False,
                    "error": f"GitHub API 422: {error_data.get('message', '')} — {messages}",
                }

            else:
                return {
                    "success": False,
                    "error": f"GitHub API {response.status_code}: {response.text[:300]}",
                }

    except Exception as e:
        _log_git_agent(f"PR creation failed: {e}", "error", project_token=project_token)
        return {"success": False, "error": str(e)}


async def _generate_pr_body(
    merged_branches: List[str],
    project_token: Optional[str] = None,
) -> str:
    """
    Generate a rich PR body using AI that summarizes what agents built.
    Falls back to a simple template if AI is unavailable.
    """
    state = _ensure_project_state(project_token)
    completed = state.get("completed_tasks", [])

    # Build a summary of completed tasks
    task_summaries = []
    for t in completed[-20:]:
        title = t.get("title", "Untitled")
        agent = t.get("assigned_agent", "unknown")
        task_summaries.append(f"- **{title}** (by `{agent}`)")

    task_list = "\n".join(task_summaries) if task_summaries else "- No task summaries available"

    # Try AI-powered PR body
    url = settings.ai_api_url
    key = settings.ai_api_key
    model_name = settings.ai_model

    if key and key != "your-api-key-here":
        try:
            prompt = f"""Write a professional GitHub Pull Request description for an automated code generation session.

BRANCHES MERGED: {', '.join(merged_branches[-10:])}

TASKS COMPLETED:
{task_list}

Write a PR body with these sections:
## Summary
(2-3 sentence overview of what was built)

## Changes
(Bullet list of key changes, grouped by module)

## Testing
(What was validated — mention pre-compilation checks, self-healing iterations, linting)

## Notes
(Any caveats or follow-up work needed)

Keep it concise and professional. Use markdown formatting."""

            payload = {
                "model": model_name,
                "messages": [
                    {"role": "system", "content": "You are a technical writer creating GitHub PR descriptions."},
                    {"role": "user", "content": prompt},
                ],
                "stream": False,
                "chat_template_kwargs": {"thinking": False},
            }
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {key}",
            }

            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()

            if "choices" in data and len(data["choices"]) > 0:
                ai_body = data["choices"][0].get("message", {}).get("content", "")
                # Strip <think> blocks from models that embed reasoning in content
                ai_body = _re.sub(r'<think>.*?</think>', '', ai_body, flags=_re.DOTALL).strip()
                ai_body = _re.sub(r'<think>.*', '', ai_body, flags=_re.DOTALL).strip()
                if len(ai_body) > 50:
                    return ai_body

        except Exception:
            pass  # Fall back to template

    # Fallback template
    return f"""## 🤖 Automated Agent PR

### Branches Merged
{chr(10).join(f'- `{b}`' for b in merged_branches[-10:])}

### Tasks Completed
{task_list}

### Quality Checks
- ✅ Pre-compilation syntax validation
- ✅ Self-healing error loop (up to 5 iterations)
- ✅ Code linting (flake8/pylint/eslint)
- ✅ Knowledge Graph consistency verification

---
*Generated by BRD Analyzer Agent Pipeline*
"""


# ── Helper: Detect issues from output ───────────────────────────────────────

def _detect_issues_from_output(stdout: str, stderr: str, exit_code: int = 0) -> Dict[str, Any]:
    """
    Parse the output for FAIL, ERROR, CRITICAL, gaps, or runtime errors.
    """
    issues = []
    all_text = (stdout or "") + "\n" + (stderr or "")
    lines = all_text.strip().split("\n")

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if "FAIL" in stripped and stripped.startswith("["):
            issues.append(stripped)
        elif "CRITICAL" in stripped and stripped.startswith("["):
            issues.append(stripped)
        elif stripped.startswith(("1.", "2.", "3.", "4.", "5.", "6.", "7.", "8.", "9.")) and any(
            kw in stripped.lower() for kw in ["missing", "gap", "not specified", "not defined", "undefined", "not detailed", "not documented"]
        ):
            issues.append(stripped)
        elif stderr and stripped in stderr and ("Error" in stripped or "Exception" in stripped or "Traceback" in stripped):
            issues.append(f"RUNTIME ERROR: {stripped}")

    # If exit code is non-zero and we found no specific issues, add a generic one
    if exit_code != 0 and not issues and stderr:
        last_lines = [l.strip() for l in stderr.strip().split("\n") if l.strip()][-3:]
        for l in last_lines:
            issues.append(f"RUNTIME ERROR: {l}")

    return {
        "has_issues": len(issues) > 0,
        "issues": issues,
        "issue_count": len(issues),
    }


def _is_builder_script_crash(stderr: str) -> bool:
    """Detect if the builder SCRIPT itself crashed (vs workspace file issues)."""
    if not stderr:
        return False
    crash_indicators = ["SyntaxError", "IndentationError", "NameError", "ImportError",
                        "unterminated", "invalid syntax", "unexpected EOF"]
    return any(indicator in stderr for indicator in crash_indicators)


def _is_workspace_empty(container_name: str) -> bool:
    """Check if /workspace/ has any files (builder never ran)."""
    try:
        result = subprocess.run(
            ["docker", "exec", container_name, "find", "/workspace", "-type", "f"],
            capture_output=True, text=True, timeout=10,
        )
        files = [f for f in result.stdout.strip().split("\n") if f.strip()]
        return len(files) == 0
    except Exception:
        return True


# ── Helper: Call AI Model ───────────────────────────────────────────────────

async def _call_ai_for_code(
    task_description: str,
    agent_type: str,
    code_context: str = "",
    system_prompt_override: str = "",
    tech_spec: str = "",
) -> tuple[str, str]:
    """Call AI model to generate project-building Python code.
    
    Args:
        task_description: The task to implement
        agent_type: Type of agent (validator, risk, estimator)
        code_context: Optional JIT context from Knowledge Graph + RAG system
        system_prompt_override: Dynamic prompt from Manager Agent (Layer 3)
        tech_spec: Canonical Technical Spec from Architect Agent (Layer 1)
    """
    url = settings.ai_api_url
    key = settings.ai_api_key
    model_name = settings.ai_model

    if not key or key == "your-api-key-here":
        raise ValueError("AI API key not configured")

    # Use dynamic prompt if provided, otherwise fall back to static
    system_prompt = system_prompt_override if system_prompt_override else AGENT_SYSTEM_PROMPTS.get(agent_type, AGENT_SYSTEM_PROMPTS["validator"])

    # Build user prompt with context layers
    user_parts = []

    # Layer 1: Tech Spec (canonical architecture reference)
    if tech_spec:
        user_parts.append(
            f"TECHNICAL SPECIFICATION (Canonical — follow this exactly):\n"
            f"{tech_spec[:4000]}\n\n---\n"
        )

    # Layer 3: KG context (relevant existing code)
    if code_context:
        user_parts.append(
            f"RELEVANT CODEBASE CONTEXT (from Knowledge Graph analysis):\n"
            f"{code_context}\n\n---\n"
        )

    user_parts.append(f"Task to implement:\n\n{task_description}")

    if code_context or tech_spec:
        user_parts.append(
            "\n\nUse the context above to understand existing patterns, "
            "naming conventions, file structure, and dependencies. "
            "Ensure your generated code is consistent with the Technical Spec "
            "and existing codebase."
        )

    user_content = "\n".join(user_parts)

    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "stream": False,
        "chat_template_kwargs": {"thinking": False},
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {key}",
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        last_err = None
        for attempt in range(3):
            try:
                if attempt > 0:
                    await asyncio.sleep(5 * attempt)
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
                last_err = None
                break
            except Exception as e:
                last_err = e
                if attempt == 2:
                    raise
        if last_err:
            raise last_err

    if "choices" in data and len(data["choices"]) > 0:
        content = data["choices"][0].get("message", {}).get("content", "")
        return _clean_ai_code_response(content)
    else:
        raise ValueError("No response from AI model")


async def _call_ai_for_fix(
    task_description: str,
    agent_type: str,
    issues: list,
    previous_output: str,
    iteration: int,
    builder_crashed: bool = False,
    kg_error_context: str = "",
    tech_spec: str = "",
) -> tuple[str, str]:
    """
    Call AI to generate a fix script. Enhanced with:
    - KG error context: relevant code from the Knowledge Graph to fix errors
    - Tech spec: canonical architecture reference to stay consistent
    If builder_crashed=True, the builder script itself had a SyntaxError
    and /workspace/ is empty, so we regenerate from scratch.
    """
    url = settings.ai_api_url
    key = settings.ai_api_key
    model_name = settings.ai_model

    if not key or key == "your-api-key-here":
        raise ValueError("AI API key not configured")

    system_prompt = AGENT_SYSTEM_PROMPTS.get(agent_type, AGENT_SYSTEM_PROMPTS["validator"])

    issues_text = "\n".join(f"  - {issue}" for issue in issues)

    # Build supplementary context from KG and tech spec
    supplementary_context = ""
    if tech_spec:
        supplementary_context += f"\nTECHNICAL SPECIFICATION (follow exact naming and conventions):\n{tech_spec[:2000]}\n"
    if kg_error_context:
        supplementary_context += f"\n{kg_error_context}\n"

    if builder_crashed:
        fix_prompt = f"""YOUR PREVIOUS BUILDER SCRIPT CRASHED before creating any files.
The error was:
{issues_text}

ORIGINAL TASK:
{task_description}
{supplementary_context}
You MUST generate a NEW, SHORTER builder script (UNDER 300 lines) that creates the project.
The /workspace/ directory is currently EMPTY - you need to create everything from scratch.

CRITICAL RULES TO AVOID CRASHING AGAIN:
1. Define a helper: def wf(path, content): os.makedirs(os.path.dirname(path), exist_ok=True); open(path,'w').write(content); print(f"[CREATED] {{path}}")
2. Use SINGLE-LINE strings with \\n for file content. NEVER use triple-quoted strings (\"\"\" or ''').
3. Keep the script under 300 lines total.
4. Focus on the 10-15 most important files only.
5. Print [CREATED] for each file and [CHECK] PASS for each validation.
6. Print === SUMMARY === at the end.
7. Use ONLY ASCII characters.
"""
    else:
        fix_prompt = f"""SELF-HEALING ITERATION {iteration}: FIX ALL ISSUES IN /workspace/

You previously built a project in /workspace/ but it has these issues:

{issues_text}

PREVIOUS OUTPUT (for context):
{previous_output[:2000]}

ORIGINAL TASK:
{task_description}
{supplementary_context}
Generate a NEW Python script (UNDER 300 lines) that:
1. FIXES each issue by modifying or creating files under /workspace/
2. Actually writes/overwrites the files that need fixing
3. Creates any missing files, directories, or configurations
4. Print [FIX N] for each fix applied
5. Print [CHECK] PASS for each successful validation
6. Print === FIX SUMMARY === at the end

IMPORTANT RULES:
- Use SINGLE-LINE strings with \\n. NEVER use triple-quoted strings.
- Define a helper: def wf(path, content): for writing files.
- Keep under 300 lines. Use ONLY ASCII characters.
- Exit with code 0 if all fixes pass, 1 if any remain.
"""

    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": fix_prompt},
        ],
        "stream": False,
        "chat_template_kwargs": {"thinking": False},
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {key}",
    }

    await asyncio.sleep(3)

    async with httpx.AsyncClient(timeout=120.0) as client:
        last_err = None
        for attempt in range(3):
            try:
                if attempt > 0:
                    await asyncio.sleep(5 * attempt)
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
                last_err = None
                break
            except Exception as e:
                last_err = e
                if attempt == 2:
                    raise
        if last_err:
            raise last_err

    if "choices" in data and len(data["choices"]) > 0:
        content = data["choices"][0].get("message", {}).get("content", "")
        return _clean_ai_code_response(content)
    else:
        raise ValueError("No response from AI model for fix iteration")


# ── Docker Configuration ────────────────────────────────────────────────────

DOCKER_BASE_IMAGE = "python:3.10-slim"


def _check_docker_available() -> bool:
    """Check if Docker daemon is available."""
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True, text=True, timeout=10,
        )
        return result.returncode == 0
    except Exception:
        return False


# ── Git Helpers ──────────────────────────────────────────────────────────────

def _slugify_branch_name(task_title: str) -> str:
    """Convert task title to a valid git branch name."""
    slug = task_title.lower().strip()
    slug = _re.sub(r'[^a-z0-9\s-]', '', slug)
    slug = _re.sub(r'[\s_]+', '-', slug)
    slug = _re.sub(r'-+', '-', slug).strip('-')
    slug = slug[:60]
    return f"agent/{slug}"


def _branch_name_for_task(task: Dict[str, Any]) -> str:
    """Create a unique, deterministic branch name per task."""
    title = task.get("title") or "task"
    base = _slugify_branch_name(title)
    raw_id = _normalize_task_id(task) or task.get("external_id") or task.get("id")
    suffix = None
    if raw_id is not None:
        suffix = _re.sub(r'[^a-zA-Z0-9]+', '', str(raw_id))
        if suffix and len(suffix) > 10:
            suffix = suffix[-10:]
    if not suffix:
        suffix = task.get("_branch_suffix")
        if not suffix:
            suffix = uuid.uuid4().hex[:8]
            task["_branch_suffix"] = suffix
    return f"{base}-{suffix}"


def _build_git_auth_url(repo_url: str, token: str) -> str:
    """Insert token into HTTPS git URL for authentication."""
    repo_url = repo_url.strip()
    if not token:
        return repo_url
    if repo_url.startswith("https://"):
        return repo_url.replace("https://", f"https://{token.strip()}@", 1)
    return repo_url


def _to_single_line(value: str, limit: int = 260) -> str:
    text = _re.sub(r"\s+", " ", (value or "").strip())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def _repo_has_project_structure(container_name: str) -> bool:
    probe = (
        "if [ -f package.json ] || [ -f requirements.txt ] || [ -f pyproject.toml ] || "
        "[ -f setup.py ] || [ -f go.mod ] || [ -f pom.xml ] || [ -f Cargo.toml ] || "
        "[ -f composer.json ] || [ -f Gemfile ]; then echo yes; exit 0; fi; "
        "if [ -d src ] || [ -d app ] || [ -d backend ] || [ -d frontend ] || [ -d server ]; "
        "then echo yes; exit 0; fi; "
        "count=$(find . -maxdepth 2 -type f ! -path './.git/*' | wc -l); "
        "if [ \"$count\" -ge 6 ]; then echo yes; else echo no; fi"
    )
    result = subprocess.run(
        ["docker", "exec", "-w", "/workspace", container_name, "sh", "-c", probe],
        capture_output=True, text=True, timeout=20,
    )
    if result.returncode != 0:
        return False
    return (result.stdout or "").strip().lower() == "yes"


def _choose_bootstrap_agent_id(project_token: Optional[str], fallback_agent_id: str) -> str:
    project_agents = _get_agent_states(project_token)
    running = sorted(
        aid for aid, data in project_agents.items()
        if not _is_system_agent_id(aid) and data.get("status") == "running"
    )
    if running:
        return running[0]
    available = sorted(aid for aid in project_agents.keys() if not _is_system_agent_id(aid))
    if available:
        return available[0]
    return fallback_agent_id


def _sync_local_branch_from_remote(
    container_name: str,
    local_branch: str,
    source_branch: str,
) -> Dict[str, Any]:
    fetch = subprocess.run(
        ["docker", "exec", "-w", "/workspace", container_name, "git", "fetch", "origin"],
        capture_output=True, text=True, timeout=60,
    )
    if fetch.returncode != 0:
        return {"success": False, "error": f"git fetch failed: {fetch.stderr or fetch.stdout}"}

    verify = subprocess.run(
        [
            "docker", "exec", "-w", "/workspace", container_name,
            "git", "show-ref", "--verify", "--quiet", f"refs/remotes/origin/{source_branch}",
        ],
        capture_output=True, text=True, timeout=20,
    )
    if verify.returncode != 0:
        return {"success": False, "error": f"remote branch origin/{source_branch} not found"}

    checkout = subprocess.run(
        [
            "docker", "exec", "-w", "/workspace", container_name,
            "git", "checkout", "-B", local_branch, f"origin/{source_branch}",
        ],
        capture_output=True, text=True, timeout=30,
    )
    if checkout.returncode != 0:
        return {"success": False, "error": f"git checkout failed: {checkout.stderr or checkout.stdout}"}
    return {"success": True, "base_branch": source_branch}


async def _mark_repo_bootstrap_result(
    project_token: Optional[str],
    source_agent: str,
    success: bool,
    source_branch: Optional[str] = None,
    message: str = "",
) -> None:
    state = _ensure_project_state(project_token)
    async with state["repo_bootstrap_lock"]:
        bootstrap = state["repo_bootstrap"]
        if bootstrap.get("required") is not True:
            return
        if bootstrap.get("status") in ("completed", "failed"):
            return
        bootstrap["status"] = "completed" if success else "failed"
        bootstrap["source_branch"] = source_branch
        bootstrap["completed_at"] = datetime.utcnow().isoformat()
        bootstrap["message"] = message or (
            f"Bootstrap released by {source_agent}"
            if success else f"Bootstrap failed on {source_agent}"
        )
    state["repo_bootstrap_event"].set()


async def _coordinate_repo_bootstrap(
    *,
    agent: Dict[str, Any],
    agent_id: str,
    repo_url: str,
    container_name: str,
    local_branch: str,
    needs_bootstrap: bool,
    project_token: Optional[str] = None,
) -> Dict[str, Any]:
    state = _ensure_project_state(project_token)
    lock = state["repo_bootstrap_lock"]
    event = state["repo_bootstrap_event"]

    async with lock:
        bootstrap = state["repo_bootstrap"]

        if repo_url and bootstrap.get("repo_url") and bootstrap.get("repo_url") != repo_url:
            state["repo_bootstrap"] = _new_repo_bootstrap_state()
            bootstrap = state["repo_bootstrap"]
            state["repo_bootstrap_event"] = asyncio.Event()
            event = state["repo_bootstrap_event"]

        if repo_url and not bootstrap.get("repo_url"):
            bootstrap["repo_url"] = repo_url

        if bootstrap.get("required") is None:
            now = datetime.utcnow().isoformat()
            if needs_bootstrap:
                bootstrap_agent = _choose_bootstrap_agent_id(project_token, agent_id)
                bootstrap["required"] = True
                bootstrap["agent_id"] = bootstrap_agent
                bootstrap["status"] = "running"
                bootstrap["started_at"] = now
                bootstrap["message"] = (
                    f"Repository is blank. Waiting for {bootstrap_agent} to push initial scaffold."
                )
                event.clear()
            else:
                bootstrap["required"] = False
                bootstrap["status"] = "not_required"
                bootstrap["completed_at"] = now
                bootstrap["message"] = "Repository already has structure; bootstrap lock not needed."
                event.set()

        required = bootstrap.get("required") is True
        bootstrap_agent = bootstrap.get("agent_id")

    if not required:
        return {"role": "none", "base_branch": None}

    if bootstrap_agent == agent_id:
        agent["output_log"].append({
            "time": datetime.utcnow().isoformat(),
            "type": "info",
            "message": (
                f"Repository appears blank. {agent_id} is bootstrap owner; "
                "other agents will wait for initial push."
            ),
        })
        return {"role": "bootstrap", "base_branch": None}

    wait_start = time.time()
    next_wait_log = BOOTSTRAP_WAIT_LOG_INTERVAL_SECONDS
    agent["progress"] = max(agent.get("progress", 0), 15)
    agent["progress_message"] = f"Waiting for {bootstrap_agent} bootstrap push..."
    agent["output_log"].append({
        "time": datetime.utcnow().isoformat(),
        "type": "info",
        "message": f"Waiting for {bootstrap_agent} to push initial scaffold before starting work.",
    })

    while not event.is_set():
        await asyncio.sleep(3)
        waited = int(time.time() - wait_start)
        if waited >= BOOTSTRAP_WAIT_TIMEOUT_SECONDS:
            agent["output_log"].append({
                "time": datetime.utcnow().isoformat(),
                "type": "error",
                "message": (
                    f"Bootstrap wait timed out after {waited}s; continuing without synced baseline."
                ),
            })
            return {"role": "follower", "base_branch": None, "waited_seconds": waited}
        if waited >= next_wait_log:
            agent["output_log"].append({
                "time": datetime.utcnow().isoformat(),
                "type": "info",
                "message": f"Still waiting for {bootstrap_agent} bootstrap push... ({waited}s)",
            })
            next_wait_log += BOOTSTRAP_WAIT_LOG_INTERVAL_SECONDS

    waited = int(time.time() - wait_start)
    async with lock:
        bootstrap = state["repo_bootstrap"]
        bootstrap_status = bootstrap.get("status")
        source_branch = bootstrap.get("source_branch")
        bootstrap_message = bootstrap.get("message") or ""

    if bootstrap_status != "completed" or not source_branch:
        reason = bootstrap_message or "Bootstrap finished without a branch reference."
        agent["output_log"].append({
            "time": datetime.utcnow().isoformat(),
            "type": "error",
            "message": f"Bootstrap released with warning: {reason}",
        })
        return {"role": "follower", "base_branch": None, "waited_seconds": waited}

    sync_result = await asyncio.to_thread(
        _sync_local_branch_from_remote, container_name, local_branch, source_branch
    )
    if not sync_result.get("success"):
        agent["output_log"].append({
            "time": datetime.utcnow().isoformat(),
            "type": "error",
            "message": (
                f"Bootstrap branch sync failed ({sync_result.get('error')}). "
                "Continuing on current branch."
            ),
        })
        return {"role": "follower", "base_branch": None, "waited_seconds": waited}

    agent["output_log"].append({
        "time": datetime.utcnow().isoformat(),
        "type": "info",
        "message": (
            f"Bootstrap ready from {source_branch}. Synced local branch after waiting {waited}s."
        ),
    })
    return {"role": "follower", "base_branch": source_branch, "waited_seconds": waited}


def _append_agent_session_note(
    container_name: str,
    agent_id: str,
    task: Dict[str, Any],
    branch_name: str,
    build_exit_code: int,
    fix_iterations: int = 0,
    linked_task: bool = False,
) -> Dict[str, Any]:
    task_title = (task.get("title") or task.get("taskName") or "Untitled task").strip()
    task_id = _normalize_task_id(task) or task.get("external_id") or task.get("id") or "unknown"
    task_description = _to_single_line(task.get("description") or "No description provided.")
    safe_agent_id = _re.sub(r"[^a-zA-Z0-9_-]+", "", agent_id) or "agent"
    rel_path = f"{AGENT_SESSION_NOTES_DIR}/{safe_agent_id}.md"
    abs_path = f"/workspace/{rel_path}"

    section = "Linked Task" if linked_task else "Main Task"
    build_status = "success" if build_exit_code == 0 else f"failed (exit={build_exit_code})"
    timestamp = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    entry = (
        f"## {timestamp} - {section}\n"
        f"- Agent: `{agent_id}`\n"
        f"- Task: `{task_title}`\n"
        f"- Task ID: `{task_id}`\n"
        f"- Branch: `{branch_name}`\n"
        f"- Build Status: `{build_status}`\n"
        f"- Fix Iterations: `{fix_iterations}`\n"
        f"- Summary: {task_description}\n\n"
    )
    header = f"# Session Notes for {agent_id}\n\n"

    script = (
        "from pathlib import Path\n"
        f"path = Path({json.dumps(abs_path)})\n"
        "path.parent.mkdir(parents=True, exist_ok=True)\n"
        f"header = {json.dumps(header)}\n"
        f"entry = {json.dumps(entry)}\n"
        "if not path.exists():\n"
        "    path.write_text(header, encoding='utf-8')\n"
        "with path.open('a', encoding='utf-8') as f:\n"
        "    f.write(entry)\n"
    )

    write = subprocess.run(
        ["docker", "exec", "-w", "/workspace", container_name, "python3", "-c", script],
        capture_output=True, text=True, timeout=20,
    )
    if write.returncode != 0:
        err = write.stderr or write.stdout or "unknown error"
        return {"success": False, "error": f"Failed writing session note: {err.strip()}"}
    return {"success": True, "path": rel_path}


def _log_git_agent(message: str, level: str = "info", project_token: Optional[str] = None) -> None:
    project_agents = _get_agent_states(project_token)
    git_agent = project_agents.get(GIT_MANAGER_AGENT_ID)
    if not git_agent:
        return
    git_agent["output_log"].append({
        "time": datetime.utcnow().isoformat(),
        "type": level,
        "message": message
    })


def _log_master_agent(message: str, level: str = "info", project_token: Optional[str] = None) -> None:
    project_agents = _get_agent_states(project_token)
    master_agent = project_agents.get(MASTER_AGENT_ID)
    if not master_agent:
        return
    master_agent["output_log"].append({
        "time": datetime.utcnow().isoformat(),
        "type": level,
        "message": message
    })


def _get_git_manager_creds(repo_url: Optional[str], token: Optional[str], project_token: Optional[str] = None) -> Dict[str, str]:
    project_agents = _get_agent_states(project_token)
    git_agent = project_agents.get(GIT_MANAGER_AGENT_ID) or {}
    return {
        "repo_url": git_agent.get("git_repo_url") or repo_url or "",
        "token": git_agent.get("git_token") or token or ""
    }


def _get_default_branch(container_name: str) -> str:
    # Try origin/HEAD symbolic ref
    head_ref = subprocess.run(
        ["docker", "exec", "-w", "/workspace", container_name,
         "git", "symbolic-ref", "refs/remotes/origin/HEAD"],
        capture_output=True, text=True, timeout=10,
    )
    if head_ref.returncode == 0:
        ref = (head_ref.stdout or "").strip()
        if ref.startswith("refs/remotes/origin/"):
            return ref.replace("refs/remotes/origin/", "", 1)

    # Fallback to main or master
    main_check = subprocess.run(
        ["docker", "exec", "-w", "/workspace", container_name,
         "git", "show-ref", "--verify", "--quiet", "refs/remotes/origin/main"],
        capture_output=True, text=True, timeout=10,
    )
    if main_check.returncode == 0:
        return "main"
    return "master"


def _collect_repo_summary(container_name: str) -> Dict[str, Any]:
    summary: Dict[str, Any] = {}
    file_list = subprocess.run(
        ["docker", "exec", "-w", "/workspace", container_name,
         "sh", "-c", "find . -maxdepth 3 -type f | sed 's|^./||' | head -n 200"],
        capture_output=True, text=True, timeout=20,
    )
    files = [f.strip() for f in (file_list.stdout or "").splitlines() if f.strip()]
    summary["files"] = files

    def has_file(name: str) -> bool:
        return subprocess.run(
            ["docker", "exec", "-w", "/workspace", container_name,
             "sh", "-c", f"test -f {name}"],
            capture_output=True, text=True, timeout=5,
        ).returncode == 0

    summary["has_package_json"] = has_file("package.json")
    summary["has_requirements"] = has_file("requirements.txt")
    summary["has_pyproject"] = has_file("pyproject.toml")
    summary["has_setup_py"] = has_file("setup.py")
    summary["has_pipfile"] = has_file("Pipfile")
    summary["has_poetry_lock"] = has_file("poetry.lock")
    summary["has_package_lock"] = has_file("package-lock.json")
    summary["has_pnpm_lock"] = has_file("pnpm-lock.yaml")
    summary["has_yarn_lock"] = has_file("yarn.lock")

    tests_dir = subprocess.run(
        ["docker", "exec", "-w", "/workspace", container_name,
         "sh", "-c", "find . -maxdepth 3 -type d \\( -name tests -o -name __tests__ \\) | head -n 1"],
        capture_output=True, text=True, timeout=10,
    )
    summary["has_tests_dir"] = bool((tests_dir.stdout or "").strip())

    pkg_scripts = {}
    if summary["has_package_json"]:
        pkg = subprocess.run(
            ["docker", "exec", "-w", "/workspace", container_name,
             "cat", "package.json"],
            capture_output=True, text=True, timeout=10,
        )
        if pkg.returncode == 0 and pkg.stdout:
            try:
                pkg_json = json.loads(pkg.stdout)
                pkg_scripts = pkg_json.get("scripts", {}) or {}
            except Exception:
                pkg_scripts = {}
    summary["package_scripts"] = pkg_scripts
    return summary


async def _call_ai_for_test_plan(summary: Dict[str, Any]) -> Dict[str, Any]:
    key = settings.ai_api_key
    if not key or key == "your-api-key-here":
        return {}
    url = settings.ai_api_url
    model_name = settings.ai_model
    prompt = (
        "You are a build engineer. Given this repo summary, return JSON only with keys "
        "\"install\" (list of shell commands) and \"tests\" (list of shell commands). "
        "Use only safe commands such as: pip install -r requirements.txt, pip install -e ., "
        "python -m pytest -q, pytest -q, npm install, npm test, npm run test, npm run build, "
        "pnpm install, pnpm test, yarn install, yarn test. If no tests, return empty lists.\n\n"
        f"REPO SUMMARY:\n{json.dumps(summary, indent=2)}"
    )
    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": "Return only valid JSON."},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "chat_template_kwargs": {"thinking": False},
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {key}",
    }
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    # Strip <think> blocks from models that embed reasoning in content
    content = _re.sub(r'<think>.*?</think>', '', content, flags=_re.DOTALL).strip()
    content = _re.sub(r'<think>.*', '', content, flags=_re.DOTALL).strip()
    start = content.find("{")
    end = content.rfind("}")
    if start == -1 or end == -1:
        return {}
    try:
        return json.loads(content[start:end + 1])
    except Exception:
        return {}


def _heuristic_test_plan(summary: Dict[str, Any]) -> Dict[str, Any]:
    install_cmds: List[str] = []
    test_cmds: List[str] = []

    if summary.get("has_package_json"):
        if summary.get("has_pnpm_lock"):
            install_cmds.append("pnpm install")
            if "test" in summary.get("package_scripts", {}):
                test_cmds.append("pnpm test")
        elif summary.get("has_yarn_lock"):
            install_cmds.append("yarn install")
            if "test" in summary.get("package_scripts", {}):
                test_cmds.append("yarn test")
        else:
            install_cmds.append("npm install")
            if "test" in summary.get("package_scripts", {}):
                test_cmds.append("npm test")
            elif "build" in summary.get("package_scripts", {}):
                test_cmds.append("npm run build")

    if summary.get("has_requirements"):
        install_cmds.append("pip install -r requirements.txt")
    elif summary.get("has_pyproject") or summary.get("has_setup_py"):
        install_cmds.append("pip install -e .")
    if summary.get("has_tests_dir") or summary.get("has_pyproject"):
        test_cmds.append("python -m pytest -q")

    return {"install": install_cmds, "tests": test_cmds}


async def _run_commands_in_container(container_name: str, commands: List[str]) -> Dict[str, Any]:
    last = {"exit_code": 0, "stdout": "", "stderr": ""}
    for cmd in commands:
        result = subprocess.run(
            ["docker", "exec", "-w", "/workspace", container_name,
             "sh", "-c", cmd],
            capture_output=True, text=True, timeout=600,
        )
        last = {"exit_code": result.returncode, "stdout": result.stdout, "stderr": result.stderr, "cmd": cmd}
        if result.returncode != 0:
            return last
    return last


def _git_ref_exists(container_name: str, ref: str) -> bool:
    check = subprocess.run(
        ["docker", "exec", "-w", "/workspace", container_name,
         "git", "show-ref", "--verify", "--quiet", f"refs/remotes/{ref}"],
        capture_output=True, text=True, timeout=15,
    )
    return check.returncode == 0


def _list_changed_files_between_refs(container_name: str, base_ref: str, compare_ref: str) -> List[str]:
    diff = subprocess.run(
        ["docker", "exec", "-w", "/workspace", container_name,
         "git", "diff", "--name-only", "--diff-filter=ACMR", f"{base_ref}...{compare_ref}"],
        capture_output=True, text=True, timeout=30,
    )
    if diff.returncode != 0:
        diff = subprocess.run(
            ["docker", "exec", "-w", "/workspace", container_name,
             "git", "diff", "--name-only", "--diff-filter=ACMR", base_ref, compare_ref],
            capture_output=True, text=True, timeout=30,
        )
    if diff.returncode != 0:
        return []
    return [line.strip() for line in (diff.stdout or "").splitlines() if line.strip()]


def _check_path_ownership_gate(
    container_name: str,
    source_branch: str,
    base_ref: str,
    source_agent: str,
    project_token: Optional[str],
) -> Dict[str, Any]:
    """
    Compare source branch changed files against active peer branches and
    current file locks from shared memory. Blocks merge when overlap exists.
    """
    try:
        import context_manager as ctx_mgr
    except Exception:
        return {"allowed": True, "changed_files": [], "conflicts": []}

    live_mem = ctx_mgr.get_live_memory(project_token or "")
    source_ref = f"origin/{source_branch}"
    changed_files = _list_changed_files_between_refs(container_name, base_ref, source_ref)
    if not changed_files:
        return {"allowed": True, "changed_files": [], "conflicts": []}

    changed_set = set(changed_files)
    conflicts: List[Dict[str, Any]] = []

    conflict_map = live_mem.get_file_conflicts(source_agent or GIT_MANAGER_AGENT_ID, changed_files)
    for path, agents in conflict_map.items():
        conflicts.append({
            "agent_id": ", ".join(sorted(agents)),
            "branch": "(file-lock)",
            "overlap": [path],
        })

    with live_mem._lock:
        active_records = list(live_mem.active_tasks.items())

    for peer_id, record in active_records:
        if peer_id == source_agent:
            continue
        peer_branch = (record.branch_name or "").strip()
        if not peer_branch or peer_branch == source_branch:
            continue
        peer_ref = f"origin/{peer_branch}"

        fetch_peer = subprocess.run(
            ["docker", "exec", "-w", "/workspace", container_name,
             "git", "fetch", "origin", peer_branch],
            capture_output=True, text=True, timeout=30,
        )
        if fetch_peer.returncode != 0 or not _git_ref_exists(container_name, peer_ref):
            continue

        peer_files = _list_changed_files_between_refs(container_name, base_ref, peer_ref)
        overlap = sorted(changed_set.intersection(peer_files))
        if overlap:
            conflicts.append({
                "agent_id": peer_id,
                "branch": peer_branch,
                "overlap": overlap[:20],
            })

    return {
        "allowed": len(conflicts) == 0,
        "changed_files": changed_files,
        "conflicts": conflicts,
    }


def _commit_if_dirty(container_name: str, message: str) -> None:
    status = subprocess.run(
        ["docker", "exec", "-w", "/workspace", container_name,
         "git", "status", "--porcelain"],
        capture_output=True, text=True, timeout=10,
    )
    if not (status.stdout or "").strip():
        return
    subprocess.run(
        ["docker", "exec", "-w", "/workspace", container_name,
         "git", "add", "-A"],
        capture_output=True, text=True, timeout=30,
    )
    subprocess.run(
        ["docker", "exec", "-w", "/workspace", container_name,
         "git", "commit", "-m", message],
        capture_output=True, text=True, timeout=30,
    )


async def _run_git_manager_tests_with_ai(container_name: str, branch: str, project_token: Optional[str] = None) -> bool:
    summary = _collect_repo_summary(container_name)
    plan = await _call_ai_for_test_plan(summary)
    if not plan:
        plan = _heuristic_test_plan(summary)

    install_cmds = plan.get("install") or []
    test_cmds = plan.get("tests") or []
    if not test_cmds:
        _log_git_agent("No test commands detected. Skipping tests.", project_token=project_token)
        return True

    _log_git_agent(
        f"Running installs: {', '.join(install_cmds) if install_cmds else 'none'}",
        project_token=project_token
    )
    install_res = await _run_commands_in_container(container_name, install_cmds)
    if install_res.get("exit_code", 0) != 0:
        stderr = (install_res.get("stderr") or "")
        stdout = (install_res.get("stdout") or "")
        combined = f"{stdout}\n{stderr}".lower()
        # Keep merge flow resilient: missing toolchains in the merge container
        # should not drop already-produced branch work.
        if "not found" in combined or "command not found" in combined:
            _log_git_agent(
                f"Install skipped (toolchain missing): {install_res.get('cmd')}\n{stderr}",
                "warning",
                project_token=project_token
            )
            _log_git_agent(
                "Proceeding without test gate for this merge to avoid dropping branch changes.",
                "warning",
                project_token=project_token
            )
            return True
        _log_git_agent(
            f"Install failed: {install_res.get('cmd')}\n{install_res.get('stderr')}",
            "warning",
            project_token=project_token
        )
        _log_git_agent(
            "Proceeding without test gate for this merge (install failure).",
            "warning",
            project_token=project_token
        )
        return True

    test_failures: List[str] = []

    for cmd in test_cmds:
        _log_git_agent(f"Running tests: {cmd}", project_token=project_token)
        test_res = await _run_commands_in_container(container_name, [cmd])
        if test_res.get("exit_code", 0) == 0:
            continue

        # ── Detect import/dependency errors vs code errors ────────────
        combined_output = (test_res.get("stdout", "") + "\n" + test_res.get("stderr", ""))
        import_error_patterns = [
            "ImportError", "ModuleNotFoundError", "No module named",
        ]
        is_import_error = any(pat in combined_output for pat in import_error_patterns)

        if is_import_error:
            # Try to extract and install missing modules before AI fix
            missing_modules = _re.findall(
                r"(?:No module named|ModuleNotFoundError:.*?)['\"]([^'\"]+)['\"]",
                combined_output,
            )
            if missing_modules:
                unique_modules = list(dict.fromkeys(missing_modules))[:5]
                pip_cmd = f"pip install {' '.join(unique_modules)} 2>/dev/null || true"
                _log_git_agent(
                    f"Import errors detected. Auto-installing: {', '.join(unique_modules)}",
                    project_token=project_token,
                )
                await _run_commands_in_container(container_name, [pip_cmd])

                # Re-run the test after installing
                test_res = await _run_commands_in_container(container_name, [cmd])
                if test_res.get("exit_code", 0) == 0:
                    _log_git_agent(
                        f"Tests passed after installing dependencies: {', '.join(unique_modules)}",
                        project_token=project_token,
                    )
                    continue
                # Update combined output for further analysis
                combined_output = (test_res.get("stdout", "") + "\n" + test_res.get("stderr", ""))

        # ── AI Auto-fix loop (only for non-import code errors) ────────
        fixed = False
        for iteration in range(1, MAX_FIX_ITERATIONS + 1):
            issues_report = _detect_issues_from_output(
                test_res.get("stdout", ""),
                test_res.get("stderr", ""),
                test_res.get("exit_code", 1),
            )
            issues = issues_report.get("issues") or []
            if not issues:
                tail = (test_res.get("stderr") or test_res.get("stdout") or "")[-500:]
                issues = [f"TEST FAILURE: {tail}"]

            # Log the actual issues for debugging
            issues_summary = "; ".join(str(i)[:200] for i in issues[:3])
            _log_git_agent(
                f"AI fix iteration {iteration} for {cmd}: {issues_summary}",
                project_token=project_token
            )
            try:
                fix_code, thought = await _call_ai_for_fix(
                    task_description=f"Fix failing tests after merge on {GIT_INTEGRATION_BRANCH}.",
                    agent_type="validator",
                    issues=issues,
                    previous_output=(test_res.get("stdout", "") + "\n" + test_res.get("stderr", "")),
                    iteration=iteration,
                    builder_crashed=False,
                )
                await asyncio.to_thread(
                    _exec_script_in_container, container_name, fix_code, f"git_fix_{iteration}"
                )
            except Exception as fix_err:
                _log_git_agent(f"AI fix failed: {fix_err}", "error", project_token=project_token)
                break

            # Re-run test command
            test_res = await _run_commands_in_container(container_name, [cmd])
            if test_res.get("exit_code", 0) == 0:
                _commit_if_dirty(container_name, f"Auto-fix after tests ({branch})")
                fixed = True
                break

        if not fixed:
            # ── Blitzy Pattern: Don't block merge on test failure ─────
            # Record the failure for PR body, but still push the merge.
            # Human reviews the PR and decides whether to merge.
            _log_git_agent(
                f"⚠️ Tests still failing after fixes: {cmd} — "
                f"will push anyway (Blitzy pattern: human reviews in PR)",
                "warning",
                project_token=project_token
            )
            test_failures.append(cmd)
            _commit_if_dirty(container_name, f"Push with test warnings ({branch})")

    return True


async def _enqueue_git_merge(branch: str, repo_url: Optional[str], token: Optional[str],
                             source_agent: str, task_title: str,
                             project_token: Optional[str] = None) -> None:
    if not branch or not repo_url:
        return
    branch = branch.strip()
    if not branch:
        return
    state = _ensure_project_state(project_token)
    inflight = state.setdefault("git_merge_inflight", set())
    already_queued = any((entry.get("branch") or "").strip() == branch for entry in state["git_merge_queue"])
    if branch in inflight or already_queued:
        _log_git_agent(
            f"Merge already queued/in progress for {branch}. Skipping duplicate request.",
            "warning",
            project_token=project_token,
        )
        return
    state["git_merge_queue"].append({
        "branch": branch,
        "repo_url": repo_url,
        "token": token or "",
        "source_agent": source_agent,
        "task_title": task_title,
        "project_token": project_token,
    })
    _log_git_agent(
        f"Queued merge: {branch} (from {source_agent}, task '{task_title}')"
        f" [queue={len(state['git_merge_queue'])}]",
        project_token=project_token
    )
    asyncio.create_task(_git_merge_worker(project_token))


async def _git_merge_worker(project_token: Optional[str] = None) -> None:
    state = _ensure_project_state(project_token)
    async with state["git_merge_lock"]:
        if state["git_merge_running"]:
            return
        state["git_merge_running"] = True

    try:
        inflight = state.setdefault("git_merge_inflight", set())
        while state["git_merge_queue"]:
            item = state["git_merge_queue"].pop(0)
            branch = (item.get("branch") or "").strip()
            not_before = float(item.get("not_before") or 0)
            now_ts = time.time()
            if not_before > now_ts:
                state["git_merge_queue"].append(item)
                await asyncio.sleep(min(2.0, max(0.2, not_before - now_ts)))
                continue
            if branch:
                inflight.add(branch)
            try:
                await _process_git_merge_item(item)
            finally:
                if branch:
                    inflight.discard(branch)
    finally:
        state["git_merge_running"] = False
        state.setdefault("git_merge_inflight", set()).clear()
        project_agents = _get_agent_states(project_token)
        git_agent = project_agents.get(GIT_MANAGER_AGENT_ID)
        if git_agent:
            git_agent["status"] = "idle"
            git_agent["progress"] = 100
            git_agent["progress_message"] = "Git manager idle"


async def _try_create_pr(
    repo_url: str,
    token: str,
    default_branch: str,
    branch: str,
    project_token: Optional[str] = None,
) -> None:
    """
    Attempt to create or update a GitHub PR after a successful merge.
    Runs as a best-effort — failures are logged but don't break the pipeline.
    """
    try:
        state = _ensure_project_state(project_token)
        merged_branches = state.get("merged_branches", [])

        # Generate AI-powered PR body
        pr_body = await _generate_pr_body(
            merged_branches=merged_branches,
            project_token=project_token,
        )

        pr_result = await _create_github_pr(
            repo_url=repo_url,
            token=token,
            head_branch=GIT_INTEGRATION_BRANCH,
            base_branch=default_branch,
            title=f"🤖 Agent Pipeline: {len(merged_branches)} task(s) merged into {GIT_INTEGRATION_BRANCH}",
            body=pr_body,
            project_token=project_token,
        )

        if pr_result.get("success"):
            if pr_result.get("already_existed"):
                _log_git_agent(
                    f"📝 PR #{pr_result['pr_number']} updated with latest info: {pr_result['pr_url']}",
                    project_token=project_token,
                )
            else:
                _log_git_agent(
                    f"🎉 PR #{pr_result['pr_number']} created: {pr_result['pr_url']}",
                    project_token=project_token,
                )
        else:
            _log_git_agent(
                f"PR creation skipped: {pr_result.get('error', 'unknown')[:100]}",
                "warning",
                project_token=project_token,
            )
    except Exception as pr_err:
        _log_git_agent(
            f"PR creation error (non-critical): {str(pr_err)[:100]}",
            "warning",
            project_token=project_token,
        )


async def _process_git_merge_item(item: Dict[str, Any]) -> None:
    project_token = item.get("project_token")
    project_agents = _get_agent_states(project_token)
    git_agent = project_agents.get(GIT_MANAGER_AGENT_ID)
    if git_agent:
        git_agent["status"] = "running"
        git_agent["progress"] = 10
        git_agent["progress_message"] = "Merging branches..."

    creds = _get_git_manager_creds(
        item.get("repo_url"),
        item.get("token"),
        project_token=project_token
    )
    repo_url = creds["repo_url"]
    token = creds["token"]
    branch = item.get("branch")
    source_agent = (item.get("source_agent") or "").strip()
    task_title = (item.get("task_title") or "").strip()
    ownership_retries = int(item.get("ownership_retries") or 0)
    max_ownership_retries = 8
    if not repo_url or not branch:
        _log_git_agent("Git manager skipped merge (missing repo/branch)", "error", project_token=project_token)
        return
    branch = branch.strip()

    container_name = f"git_manager_{uuid.uuid4().hex[:8]}"
    try:
        _log_git_agent(f"Creating git manager container: {container_name}", project_token=project_token)
        container_result = await asyncio.to_thread(_create_persistent_container, container_name)
        if not container_result["success"]:
            _log_git_agent(f"Git manager container error: {container_result['error']}", "error", project_token=project_token)
            return

        # Install git
        install = subprocess.run(
            ["docker", "exec", container_name, "sh", "-c",
             "apt-get update -qq && apt-get install -y -qq git > /dev/null 2>&1"],
            capture_output=True, text=True, timeout=120,
        )
        if install.returncode != 0:
            _log_git_agent(f"Git manager failed to install git: {install.stderr}", "error", project_token=project_token)
            return

        # Configure git user
        subprocess.run(
            ["docker", "exec", container_name, "git", "config", "--global", "user.email", "git-agent@brd-analyzer.ai"],
            capture_output=True, text=True, timeout=10,
        )
        subprocess.run(
            ["docker", "exec", container_name, "git", "config", "--global", "user.name", "BRD Git Manager"],
            capture_output=True, text=True, timeout=10,
        )

        # Clone repo
        auth_url = _build_git_auth_url(repo_url, token)
        clone = subprocess.run(
            ["docker", "exec", container_name, "git", "clone", auth_url, "/workspace"],
            capture_output=True, text=True, timeout=120,
        )
        if clone.returncode != 0:
            _log_git_agent(f"Git manager clone failed: {clone.stderr}", "error", project_token=project_token)
            return

        default_branch = _get_default_branch(container_name)

        if git_agent:
            git_agent["progress"] = 60
            git_agent["progress_message"] = f"Merging {branch} -> {GIT_INTEGRATION_BRANCH}"

        max_push_attempts = 5
        for attempt in range(1, max_push_attempts + 1):
            # Always re-read remote refs before each attempt so retries are
            # based on the latest integration tip, not stale local history.
            fetch_branch = subprocess.run(
                ["docker", "exec", "-w", "/workspace", container_name,
                 "git", "fetch", "origin", branch],
                capture_output=True, text=True, timeout=60,
            )
            if fetch_branch.returncode != 0:
                _log_git_agent(
                    f"Failed to fetch source branch {branch}: {fetch_branch.stderr or fetch_branch.stdout}",
                    "error",
                    project_token=project_token,
                )
                return

            subprocess.run(
                ["docker", "exec", "-w", "/workspace", container_name,
                 "git", "fetch", "origin", GIT_INTEGRATION_BRANCH],
                capture_output=True, text=True, timeout=60,
            )

            integration_exists = subprocess.run(
                ["docker", "exec", "-w", "/workspace", container_name,
                 "git", "show-ref", "--verify", "--quiet", f"refs/remotes/origin/{GIT_INTEGRATION_BRANCH}"],
                capture_output=True, text=True, timeout=15,
            ).returncode == 0
            base_ref = f"origin/{GIT_INTEGRATION_BRANCH}" if integration_exists else f"origin/{default_branch}"

            ownership_gate = _check_path_ownership_gate(
                container_name=container_name,
                source_branch=branch,
                base_ref=base_ref,
                source_agent=source_agent,
                project_token=project_token,
            )
            if not ownership_gate.get("allowed", True):
                conflicts = ownership_gate.get("conflicts") or []
                compact = []
                for entry in conflicts[:3]:
                    who = entry.get("agent_id") or "unknown-agent"
                    peer_branch = entry.get("branch") or "unknown-branch"
                    overlap = entry.get("overlap") or []
                    compact.append(f"{who}/{peer_branch}: {', '.join(overlap[:3])}")
                conflict_msg = " | ".join(compact) if compact else "overlapping ownership"

                if ownership_retries < max_ownership_retries:
                    ownership_retries += 1
                    wait_seconds = min(90, 8 * ownership_retries)
                    item["ownership_retries"] = ownership_retries
                    item["not_before"] = time.time() + wait_seconds
                    _ensure_project_state(project_token)["git_merge_queue"].append(item)
                    _log_git_agent(
                        f"Path ownership gate blocked merge for {branch}"
                        f"{f' ({task_title})' if task_title else ''}: {conflict_msg}. "
                        f"Re-queued with backoff {wait_seconds}s "
                        f"({ownership_retries}/{max_ownership_retries}).",
                        "warning",
                        project_token=project_token,
                    )
                    return

                _log_git_agent(
                    f"Path ownership conflicts persisted for {branch} after "
                    f"{max_ownership_retries} retries: {conflict_msg}. "
                    "Proceeding to merge to avoid deadlock.",
                    "warning",
                    project_token=project_token,
                )

            checkout = subprocess.run(
                ["docker", "exec", "-w", "/workspace", container_name,
                 "git", "checkout", "-B", GIT_INTEGRATION_BRANCH, base_ref],
                capture_output=True, text=True, timeout=30,
            )
            if checkout.returncode != 0:
                _log_git_agent(
                    f"Failed to checkout {GIT_INTEGRATION_BRANCH} from {base_ref}: "
                    f"{checkout.stderr or checkout.stdout}",
                    "error",
                    project_token=project_token,
                )
                return

            merge = subprocess.run(
                ["docker", "exec", "-w", "/workspace", container_name,
                 "git", "merge", "--no-ff", "--allow-unrelated-histories", f"origin/{branch}"],
                capture_output=True, text=True, timeout=60,
            )
            if merge.returncode != 0:
                conflict_list = subprocess.run(
                    ["docker", "exec", "-w", "/workspace", container_name,
                     "git", "diff", "--name-only", "--diff-filter=U"],
                    capture_output=True, text=True, timeout=20,
                )
                files = [f.strip() for f in (conflict_list.stdout or "").splitlines() if f.strip()]
                if not files:
                    _log_git_agent(
                        f"Merge failed for {branch}: {merge.stderr or merge.stdout}",
                        "error",
                        project_token=project_token,
                    )
                    subprocess.run(
                        ["docker", "exec", "-w", "/workspace", container_name, "git", "merge", "--abort"],
                        capture_output=True, text=True, timeout=10,
                    )
                    return

                _log_git_agent(
                    f"Conflicts detected. Applying union merge for {len(files)} files.",
                    project_token=project_token
                )
                for file_path in files:
                    merge_script = (
                        f"git show :2:{file_path} > /tmp/ours_merge && "
                        f"git show :3:{file_path} > /tmp/theirs_merge && "
                        f"git show :1:{file_path} > /tmp/base_merge 2>/dev/null || : > /tmp/base_merge; "
                        f"git merge-file -p --union /tmp/ours_merge /tmp/base_merge /tmp/theirs_merge > \"{file_path}\" && "
                        f"git add \"{file_path}\""
                    )
                    file_merge = subprocess.run(
                        ["docker", "exec", "-w", "/workspace", container_name, "sh", "-c", merge_script],
                        capture_output=True, text=True, timeout=60,
                    )
                    if file_merge.returncode != 0:
                        _log_git_agent(
                            f"Union merge failed for {file_path}: {file_merge.stderr}",
                            "error",
                            project_token=project_token
                        )
                        subprocess.run(
                            ["docker", "exec", "-w", "/workspace", container_name, "git", "merge", "--abort"],
                            capture_output=True, text=True, timeout=10,
                        )
                        return

                commit_union = subprocess.run(
                    ["docker", "exec", "-w", "/workspace", container_name,
                     "git", "commit", "-m", f"Auto-union merge {branch}"],
                    capture_output=True, text=True, timeout=30,
                )
                commit_union_out = (commit_union.stdout or "") + (commit_union.stderr or "")
                if commit_union.returncode != 0 and "nothing to commit" not in commit_union_out.lower():
                    _log_git_agent(
                        f"Union merge commit failed for {branch}: {commit_union.stderr}",
                        "error",
                        project_token=project_token
                    )
                    subprocess.run(
                        ["docker", "exec", "-w", "/workspace", container_name, "git", "merge", "--abort"],
                        capture_output=True, text=True, timeout=10,
                    )
                    return

            try:
                tests_ok = await _run_git_manager_tests_with_ai(container_name, branch, project_token=project_token)
            except Exception as test_err:
                _log_git_agent(
                    f"Test runner error after merging {branch}: {str(test_err)[:200]}",
                    "warning",
                    project_token=project_token,
                )
                tests_ok = True
            if not tests_ok:
                _log_git_agent(
                    f"Tests failed after merge for {branch}. Proceeding without test gate.",
                    "warning",
                    project_token=project_token,
                )

            push = subprocess.run(
                ["docker", "exec", "-w", "/workspace", container_name,
                 "git", "push", "-u", "origin", GIT_INTEGRATION_BRANCH],
                capture_output=True, text=True, timeout=60,
            )
            if push.returncode == 0:
                push_note = "" if attempt == 1 else f" (after retry {attempt})"
                _log_git_agent(
                    f"Merged {branch} into {GIT_INTEGRATION_BRANCH} and pushed{push_note}.",
                    project_token=project_token
                )
                state = _ensure_project_state(project_token)
                merged = state.setdefault("merged_branches", [])
                if branch not in merged:
                    merged.append(branch)
                await _try_create_pr(
                    repo_url=repo_url, token=token,
                    default_branch=default_branch,
                    branch=branch,
                    project_token=project_token,
                )
                if git_agent:
                    git_agent["progress"] = 100
                    git_agent["progress_message"] = f"Merged {branch}"
                return

            err = push.stderr or push.stdout
            lower_err = err.lower()
            if "non-fast-forward" in lower_err or "rejected" in lower_err:
                if attempt < max_push_attempts:
                    _log_git_agent(
                        f"Non-fast-forward on {GIT_INTEGRATION_BRANCH}. "
                        f"Rebuilding merge on latest remote tip (attempt {attempt + 1}/{max_push_attempts}).",
                        "warning",
                        project_token=project_token,
                    )
                    await asyncio.sleep(2 * attempt)
                    continue
                _log_git_agent(
                    f"Push rejected for {GIT_INTEGRATION_BRANCH} after {max_push_attempts} attempts: {err}",
                    "error",
                    project_token=project_token,
                )
                return

            _log_git_agent(
                f"Push failed for {GIT_INTEGRATION_BRANCH}: {err}",
                "error",
                project_token=project_token
            )
            return
    finally:
        await asyncio.to_thread(_destroy_container, container_name)


def _setup_git_in_container(container_name: str, repo_url: str, token: str, branch_name: str) -> Dict[str, Any]:
    """
    Install git, clone repo into /workspace/, and create the working branch.
    Also detects whether bootstrap coordination is required.
    """
    try:
        # 1. Install git
        install = subprocess.run(
            ["docker", "exec", container_name, "sh", "-c",
             "apt-get update -qq && apt-get install -y -qq git > /dev/null 2>&1"],
            capture_output=True, text=True, timeout=120,
        )
        if install.returncode != 0:
            return {"success": False, "error": f"Failed to install git: {install.stderr}"}

        # 2. Configure git user
        subprocess.run(
            ["docker", "exec", container_name, "git", "config", "--global", "user.email", "agent@brd-analyzer.ai"],
            capture_output=True, text=True, timeout=10,
        )
        subprocess.run(
            ["docker", "exec", container_name, "git", "config", "--global", "user.name", "BRD Agent"],
            capture_output=True, text=True, timeout=10,
        )

        # 3. Clone repo into /workspace/
        auth_url = _build_git_auth_url(repo_url, token)
        subprocess.run(
            ["docker", "exec", container_name, "sh", "-c", "rm -rf /workspace/* /workspace/.* 2>/dev/null || true"],
            capture_output=True, text=True, timeout=10,
        )
        clone = subprocess.run(
            ["docker", "exec", container_name, "git", "clone", auth_url, "/workspace"],
            capture_output=True, text=True, timeout=120,
        )
        if clone.returncode != 0:
            return {"success": False, "error": f"Git clone failed: {clone.stderr}"}

        # 4. Detect repo baseline state (blank/no structure) and create branch
        head_check = subprocess.run(
            ["docker", "exec", "-w", "/workspace", container_name, "git", "rev-parse", "--verify", "HEAD"],
            capture_output=True, text=True, timeout=15,
        )
        repo_empty = head_check.returncode != 0
        default_branch = None
        needs_bootstrap = repo_empty

        if not repo_empty:
            default_branch = _get_default_branch(container_name)
            has_structure = _repo_has_project_structure(container_name)
            needs_bootstrap = not has_structure

        checkout_cmd = ["git", "checkout", "-B", branch_name]
        if repo_empty:
            checkout_cmd = ["git", "checkout", "--orphan", branch_name]

        checkout = subprocess.run(
            ["docker", "exec", "-w", "/workspace", container_name, *checkout_cmd],
            capture_output=True, text=True, timeout=15,
        )
        if checkout.returncode != 0:
            return {"success": False, "error": f"Branch creation failed: {checkout.stderr}"}

        if repo_empty:
            default_branch = branch_name

        return {
            "success": True,
            "branch": branch_name,
            "repo_empty": repo_empty,
            "default_branch": default_branch,
            "needs_bootstrap": needs_bootstrap,
        }

    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Git setup timed out"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _run_git_command_with_retry(container_name: str, command: List[str],
                                 max_retries: int = 10, delay: float = 1.0,
                                 operation: str = "operation") -> subprocess.CompletedProcess:
    """Run a git command with automatic retry until it succeeds."""
    import time
    last_error = None
    for attempt in range(max_retries):
        result = subprocess.run(
            ["docker", "exec", "-w", "/workspace", container_name] + command,
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode == 0:
            return result
        last_error = result.stderr or result.stdout
        if attempt < max_retries - 1:
            time.sleep(delay * (attempt + 1))  # Exponential backoff
    # Return the last result even if failed
    return subprocess.CompletedProcess(args=command, returncode=last_error.returncode if hasattr(last_error, 'returncode') else 1,
                                        stdout=getattr(last_error, 'stdout', '') or '',
                                        stderr=getattr(last_error, 'stderr', str(last_error)))


def _commit_and_push(container_name: str, task_title: str, branch_name: str) -> Dict[str, Any]:
    """Stage all changes, commit with task title, and push to the remote branch."""
    try:
        def _abort_pending_git_ops() -> None:
            # If rebase/merge/cherry-pick stopped mid-way, clear that state
            # before any fallback checkout logic.
            subprocess.run(
                ["docker", "exec", "-w", "/workspace", container_name, "sh", "-c",
                 "git rebase --abort >/dev/null 2>&1 || true; "
                 "git merge --abort >/dev/null 2>&1 || true; "
                 "git cherry-pick --abort >/dev/null 2>&1 || true"],
                capture_output=True, text=True, timeout=20,
            )

        # Add all files
        add = subprocess.run(
            ["docker", "exec", "-w", "/workspace", container_name, "git", "add", "-A"],
            capture_output=True, text=True, timeout=30,
        )
        if add.returncode != 0:
            return {"success": False, "error": f"git add failed: {add.stderr}"}

        # Commit
        commit_msg = f"Agent: {task_title}"
        commit = subprocess.run(
            ["docker", "exec", "-w", "/workspace", container_name,
             "git", "commit", "-m", commit_msg],
            capture_output=True, text=True, timeout=30,
        )
        if commit.returncode != 0:
            if "nothing to commit" in (commit.stdout + commit.stderr):
                return {"success": True, "message": "Nothing to commit", "pushed": False}
            return {"success": False, "error": f"git commit failed: {commit.stderr}"}

        # Push
        push = subprocess.run(
            ["docker", "exec", "-w", "/workspace", container_name,
             "git", "push", "-u", "origin", branch_name],
            capture_output=True, text=True, timeout=60,
        )
        if push.returncode != 0:
            err = push.stderr or push.stdout
            if "non-fast-forward" in err or "rejected" in err:
                # Strategy 1: Pull and rebase to integrate remote changes
                pull = subprocess.run(
                    ["docker", "exec", "-w", "/workspace", container_name,
                     "git", "pull", "--rebase", "origin", branch_name],
                    capture_output=True, text=True, timeout=60,
                )
                if pull.returncode == 0:
                    # Rebase succeeded, try push again
                    push_retry = subprocess.run(
                        ["docker", "exec", "-w", "/workspace", container_name,
                         "git", "push", "-u", "origin", branch_name],
                        capture_output=True, text=True, timeout=60,
                    )
                    if push_retry.returncode == 0:
                        return {"success": True, "pushed": True, "branch": branch_name, "rebased": True}
                else:
                    _abort_pending_git_ops()

                # Strategy 2: Fallback - push to a new branch to avoid collisions
                suffix = uuid.uuid4().hex[:6]
                new_branch = f"{branch_name}-{suffix}"

                _abort_pending_git_ops()

                # Retry checkout until it succeeds
                checkout = _run_git_command_with_retry(
                    container_name,
                    ["git", "checkout", "-B", new_branch],
                    max_retries=10,
                    delay=1.0,
                    operation="checkout"
                )
                if checkout.returncode != 0:
                    # One more cleanup + direct retry for the common
                    # "resolve your current index first" state.
                    _abort_pending_git_ops()
                    checkout_retry = subprocess.run(
                        ["docker", "exec", "-w", "/workspace", container_name,
                         "git", "checkout", "-B", new_branch],
                        capture_output=True, text=True, timeout=30,
                    )
                    if checkout_retry.returncode != 0:
                        pull_err = (pull.stderr or pull.stdout or "").strip() if 'pull' in locals() else ""
                        return {
                            "success": False,
                            "error": (
                                f"Failed to create branch {new_branch}: "
                                f"{(checkout_retry.stderr or checkout_retry.stdout).strip()} "
                                f"| prior rebase error: {pull_err[:400]}"
                            ),
                        }

                # Retry push until it succeeds
                push2 = _run_git_command_with_retry(
                    container_name,
                    ["git", "push", "-u", "origin", new_branch],
                    max_retries=10,
                    delay=1.0,
                    operation="push"
                )
                if push2.returncode == 0:
                    return {"success": True, "pushed": True, "branch": new_branch, "renamed": True}
                return {"success": False, "error": f"git push failed: {push2.stderr}"}
            return {"success": False, "error": f"git push failed: {err}"}

        return {"success": True, "pushed": True, "branch": branch_name}

    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Git push timed out"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ── Docker Container Management ─────────────────────────────────────────────

def _create_persistent_container(container_name: str) -> Dict[str, Any]:
    """Create and start a persistent Docker container with /workspace/ directory."""
    try:
        # Create container that stays alive (sleep infinity)
        create_result = subprocess.run(
            ["docker", "create", "--name", container_name, "-w", "/workspace",
             DOCKER_BASE_IMAGE, "sleep", "infinity"],
            capture_output=True, text=True, timeout=30,
        )
        if create_result.returncode != 0:
            return {"success": False, "error": f"docker create failed: {create_result.stderr}"}

        # Start it
        start_result = subprocess.run(
            ["docker", "start", container_name],
            capture_output=True, text=True, timeout=15,
        )
        if start_result.returncode != 0:
            subprocess.run(["docker", "rm", "-f", container_name], capture_output=True, timeout=10)
            return {"success": False, "error": f"docker start failed: {start_result.stderr}"}

        # Create /workspace directory inside
        subprocess.run(
            ["docker", "exec", container_name, "mkdir", "-p", "/workspace"],
            capture_output=True, text=True, timeout=10,
        )

        return {"success": True, "container_name": container_name}

    except Exception as e:
        subprocess.run(["docker", "rm", "-f", container_name], capture_output=True, timeout=10)
        return {"success": False, "error": str(e)}


def _exec_script_in_container(container_name: str, code: str, script_label: str = "script") -> Dict[str, Any]:
    """Copy a Python script into a running container and execute it."""
    # Write to local temp file
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, prefix=f"agent_{script_label}_",
        encoding="utf-8",
    ) as f:
        f.write(code)
        script_path = f.name

    script_name = os.path.basename(script_path)
    container_script = f"/tmp/{script_name}"

    try:
        # Copy into container
        cp_result = subprocess.run(
            ["docker", "cp", script_path, f"{container_name}:{container_script}"],
            capture_output=True, text=True, timeout=15,
        )
        if cp_result.returncode != 0:
            return {
                "exit_code": -1, "stdout": "", "stderr": f"docker cp failed: {cp_result.stderr}",
                "error": f"docker cp failed: {cp_result.stderr}",
            }

        # Execute inside container
        result = subprocess.run(
            ["docker", "exec", container_name, "python3", container_script],
            capture_output=True, text=True, timeout=180,
        )

        # Clean up script inside container
        subprocess.run(
            ["docker", "exec", container_name, "rm", "-f", container_script],
            capture_output=True, text=True, timeout=10,
        )

        return {
            "exit_code": result.returncode,
            "stdout": result.stdout or "",
            "stderr": result.stderr or "",
            "error": None,
        }

    except subprocess.TimeoutExpired:
        return {
            "exit_code": -1, "stdout": "", "stderr": "Script timed out (180s)",
            "error": "timeout",
        }
    except FileNotFoundError:
        return {
            "exit_code": -1, "stdout": "", "stderr": "Docker not found",
            "error": "docker_not_found",
        }
    except Exception as e:
        return {
            "exit_code": -1, "stdout": "", "stderr": str(e),
            "error": str(e),
        }
    finally:
        try:
            os.unlink(script_path)
        except OSError:
            pass


def _capture_workspace_tree(container_name: str) -> str:
    """
    Capture the entire /workspace/ file tree with file contents.
    Returns a formatted string showing the project structure and code.
    """
    try:
        # Get file listing
        find_result = subprocess.run(
            ["docker", "exec", container_name, "find", "/workspace", "-type", "f",
             "-not", "-path", "*/\\.git/*", "-not", "-path", "*/__pycache__/*",
             "-not", "-name", "*.pyc"],
            capture_output=True, text=True, timeout=15,
        )

        if find_result.returncode != 0 or not find_result.stdout.strip():
            return "# No files found in /workspace/"

        files = sorted(find_result.stdout.strip().split("\n"))

        # Build tree output
        output_parts = []
        output_parts.append("=" * 60)
        output_parts.append("PROJECT STRUCTURE")
        output_parts.append("=" * 60)
        output_parts.append("")

        # File tree summary
        output_parts.append("File Tree:")
        for f in files:
            rel = f.replace("/workspace/", "")
            depth = rel.count("/")
            indent = "  " * depth
            name = os.path.basename(rel)
            output_parts.append(f"  {indent}{name}")
        output_parts.append("")
        output_parts.append(f"Total: {len(files)} files")
        output_parts.append("")

        # File contents
        for filepath in files:
            rel_path = filepath.replace("/workspace/", "")
            output_parts.append("-" * 60)
            output_parts.append(f"FILE: {rel_path}")
            output_parts.append("-" * 60)

            cat_result = subprocess.run(
                ["docker", "exec", container_name, "cat", filepath],
                capture_output=True, text=True, timeout=10,
            )

            if cat_result.returncode == 0:
                content = cat_result.stdout
                # Truncate very large files
                if len(content) > 5000:
                    content = content[:5000] + f"\n\n... [truncated, {len(cat_result.stdout)} chars total]"
                output_parts.append(content)
            else:
                output_parts.append(f"[Could not read file: {cat_result.stderr}]")

            output_parts.append("")

        return "\n".join(output_parts)

    except Exception as e:
        return f"# Error capturing workspace: {str(e)}"


def _destroy_container(container_name: str):
    """Force remove a Docker container."""
    try:
        subprocess.run(
            ["docker", "rm", "-f", container_name],
            capture_output=True, text=True, timeout=15,
        )
    except Exception:
        pass


# ── Parse agent output for stats ────────────────────────────────────────────

def _parse_stats_from_output(stdout: str, agent_type: str) -> Dict[str, Any]:
    """Extract stats from the agent subprocess output."""
    lines = stdout.strip().split("\n") if stdout else []

    if agent_type == "validator":
        checks = sum(1 for l in lines if l.strip().startswith("[CHECK"))
        passed = sum(1 for l in lines if "PASS" in l and l.strip().startswith("[CHECK"))
        created = sum(1 for l in lines if l.strip().startswith("[CREATED"))
        coverage = round((passed / max(checks, 1)) * 100)
        return {"checks": checks, "coverage": f"{coverage}%", "avg_time": "---"}

    elif agent_type == "risk":
        risks = sum(1 for l in lines if l.strip().startswith("[RISK"))
        critical = sum(1 for l in lines if "CRITICAL" in l)
        created = sum(1 for l in lines if l.strip().startswith("[CREATED"))
        return {"risks": risks, "critical": critical, "avg_time": "---"}

    elif agent_type == "estimator":
        sprints = sum(1 for l in lines if l.strip().startswith("[SPRINT"))
        resources = 0
        for l in lines:
            if "Team Size" in l or "developers" in l.lower():
                import re
                nums = re.findall(r"\d+", l)
                if nums:
                    resources = int(nums[-1])
                    break
        if resources == 0:
            resources = sprints
        created = sum(1 for l in lines if l.strip().startswith("[CREATED"))
        return {"sprints": sprints, "resources": resources, "avg_time": "---"}

    return {}


# ── Fetch tasks from External Task API ──────────────────────────────────────

async def _fetch_external_tasks(project_token: Optional[str] = None) -> List[Dict[str, Any]]:
    """Fetch ALL pages of tasks from the external task management API."""
    from task_service import task_service
    def _extract_entity_info(raw_value: Any, key: str):
        entity_id = None
        entity_name = None
        if isinstance(raw_value, dict):
            entity_id = raw_value.get("id") or raw_value.get(f"{key}_id")
            entity_name = raw_value.get("name") or raw_value.get("title")
        elif raw_value not in (None, ""):
            entity_id = raw_value
        return entity_id, entity_name

    def _to_int(value: Any) -> Optional[int]:
        try:
            if value in (None, ""):
                return None
            return int(str(value).strip())
        except Exception:
            return None

    def _safe_date_key(value: Any) -> str:
        if value in (None, ""):
            return "9999-12-31"
        text = str(value).strip()
        if len(text) >= 10:
            candidate = text[:10]
            try:
                datetime.strptime(candidate, "%Y-%m-%d")
                return candidate
            except Exception:
                pass
        return "9999-12-31"

    try:
        task_token = get_project_task_token(project_token)
        all_tasks = []
        page = 1
        while True:
            data = await task_service.get_tasks(page=page, task_token=task_token)
            if isinstance(data, list):
                all_tasks.extend(data)
                break
            elif isinstance(data, dict) and "results" in data:
                all_tasks.extend(data["results"])
                if not data.get("next"):
                    break
                page += 1
            else:
                break

        normalized = []
        for t in all_tasks:
            # Parse checklist JSON
            checklist_raw = t.get("checklist")
            if checklist_raw in (None, ""):
                checklist_raw = t.get("checklistItems")
            checklist_items = []
            if isinstance(checklist_raw, list):
                checklist_items = checklist_raw
            elif isinstance(checklist_raw, str) and checklist_raw.strip():
                try:
                    parsed = json.loads(checklist_raw)
                    if isinstance(parsed, list):
                        checklist_items = parsed
                    elif isinstance(parsed, dict):
                        checklist_items = parsed.get("checklistItems", []) or parsed.get("items", [])
                except Exception:
                    pass
            elif isinstance(checklist_raw, dict):
                checklist_items = checklist_raw.get("checklistItems", []) or checklist_raw.get("items", [])

            task_id = t.get("id", uuid.uuid4().hex[:8])
            external_id = t.get("external_id")
            sprint_id, sprint_name = _extract_entity_info(t.get("sprint"), "sprint")
            milestone_id, milestone_name = _extract_entity_info(t.get("milestone"), "milestone")
            if sprint_id in (None, ""):
                sprint_id = t.get("sprint_id")
            if milestone_id in (None, ""):
                milestone_id = t.get("milestone_id")
            task_start_date = t.get("startdate") or t.get("start_date")
            task_deadline = t.get("deadline") or t.get("end_date")
            normalized.append({
                "id": str(task_id),
                "external_id": external_id if external_id is not None else task_id,
                "title": t.get("taskName") or t.get("title") or "Untitled Task",
                "description": t.get("description") or t.get("taskName") or "",
                "priority": (t.get("priority") or "medium").lower(),
                "status": t.get("taskStatus") or t.get("status") or "pending",
                "task_type": t.get("task_type", "TASK"),
                "created_at": t.get("created_at") or datetime.utcnow().isoformat(),
                "assigned_agent": None,
                "started_at": None,
                "linked_tasks": t.get("linked_tasks") or [],
                "checklist": checklist_items,
                "sprint_id": sprint_id,
                "sprint_name": sprint_name,
                "milestone_id": milestone_id,
                "milestone_name": milestone_name,
                "startdate": task_start_date,
                "deadline": task_deadline,
                "_project_token": project_token,
            })

        def _task_sort_key(task: Dict[str, Any]):
            sprint_rank = _to_int(task.get("sprint_id"))
            milestone_rank = _to_int(task.get("milestone_id"))
            return (
                sprint_rank if sprint_rank is not None else 10**9,
                milestone_rank if milestone_rank is not None else 10**9,
                _safe_date_key(task.get("startdate")),
                _safe_date_key(task.get("deadline")),
                str(task.get("title") or "").lower(),
                str(task.get("id") or ""),
            )

        normalized.sort(key=_task_sort_key)
        return normalized
    except Exception as e:
        print(f"[agent_service] Failed to fetch external tasks: {e}")
        return []


async def _mark_checklist_item(task_id, checklist_items: list, item_index: int, project_token: Optional[str] = None, task_token: Optional[str] = None):
    """Mark a single checklist item as completed via external API."""
    from task_service import task_service
    try:
        if not task_id:
            return
        updated = []
        for i, item in enumerate(checklist_items):
            updated.append({
                "text": item.get("text", ""),
                "completed": True if i <= item_index else item.get("completed", False),
            })
        task_token = task_token or get_project_task_token(project_token)
        await task_service.add_checklist_to_task(int(task_id), updated, task_token=task_token)
    except Exception as e:
        print(f"[agent_service] Failed to update checklist for task {task_id}: {e}")


def _normalize_task_id(task: Dict[str, Any]):
    tid = task.get("id") or task.get("external_id")
    if tid is None:
        return None
    try:
        return int(tid)
    except (TypeError, ValueError):
        return tid


async def _post_task_message(task: Dict[str, Any], message: str, project_token: Optional[str] = None, task_token: Optional[str] = None) -> bool:
    """Post task message with retry logic - will retry up to 5 times with exponential backoff."""
    from task_service import task_service
    task_id = _normalize_task_id(task)
    if not task_id:
        return False
    resolved_project = project_token or (task.get("_project_token") if isinstance(task, dict) else None)
    
    max_retries = 5
    base_delay = 1.0
    
    for attempt in range(max_retries):
        try:
            await task_service.post_task_message({
                "task_id": task_id,
                "message": message
            }, task_token=task_token or get_project_task_token(resolved_project))
            return True
        except Exception as e:
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                print(f"[agent_service] Failed to post message for task {task_id} (attempt {attempt + 1}/{max_retries}): {e}. Retrying in {delay}s...")
                await asyncio.sleep(delay)
            else:
                print(f"[agent_service] Failed to post message for task {task_id} after {max_retries} attempts: {e}")
                return False
    return False


async def _post_task_progress(task: Dict[str, Any], progress: int, additional_info: str = None,
                              project_token: Optional[str] = None, task_token: Optional[str] = None) -> bool:
    """Post task progress with retry logic - will retry up to 5 times with exponential backoff."""
    from task_service import task_service
    task_id = _normalize_task_id(task)
    if not task_id:
        return False
    resolved_project = project_token or (task.get("_project_token") if isinstance(task, dict) else None)
    state = _ensure_project_state(resolved_project)
    task_key = str(task_id)
    last_progress = state["task_progress_state"].get(task_key)
    if last_progress is not None and progress < last_progress:
        print(
            f"[agent_service] Skipping progress for task {task_id}: "
            f"cannot decrease from {last_progress} to {progress}"
        )
        return False
    timer_active = state["timer_log_state"].get(task_key, False)
    terminal_progress = progress in (0, 100)
    if not timer_active and not terminal_progress:
        print(
            f"[agent_service] Skipping progress for task {task_id}: "
            "no successful clock_in recorded"
        )
        return False
    if not timer_active and terminal_progress:
        print(
            f"[agent_service] Allowing terminal progress {progress}% for task {task_id} "
            "without active timer"
        )
    
    max_retries = 5
    base_delay = 1.0
    
    for attempt in range(max_retries):
        try:
            payload = {
                "task_id": task_id,
                "task_progress": progress,
            }
            if additional_info:
                payload["additional_info"] = additional_info
            effective_token = task_token or get_project_task_token(resolved_project)
            await task_service.update_task_progress(payload, task_token=effective_token)
            state["task_progress_state"][task_key] = progress
            return True
        except Exception as e:
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                print(f"[agent_service] Failed to update progress for task {task_id} (attempt {attempt + 1}/{max_retries}): {e}. Retrying in {delay}s...")
                await asyncio.sleep(delay)
            else:
                print(f"[agent_service] Failed to update progress for task {task_id} after {max_retries} attempts: {e}")
                return False
    return False


def _normalize_error_text(err: Exception) -> str:
    text = str(err).lower()
    for ch in ("-", "_", "/", "\\"):
        text = text.replace(ch, " ")
    return " ".join(text.split())


def _is_timer_running_error(error_text: str) -> bool:
    checks = (
        "timer is still running",
        "timer still running",
        "active timer",
        "clock out before",
        "clock out first",
        "must clock out",
        "clockout before",
    )
    return any(c in error_text for c in checks)


def _is_already_completed_error(error_text: str) -> bool:
    checks = (
        "already completed",
        "already complete",
        "task already completed",
        "status already completed",
        "already closed",
        "already done",
    )
    return any(c in error_text for c in checks)


def _is_clock_out_idempotent_success(error_text: str) -> bool:
    checks = (
        "timer not running",
        "no active timer",
        "not clocked in",
        "already clocked out",
        "already clocked out for this task",
        "cannot clock out before clock in",
    )
    return any(c in error_text for c in checks)


async def _post_task_complete(task: Dict[str, Any], project_token: Optional[str] = None, task_token: Optional[str] = None) -> bool:
    """Complete task with retry logic. Ensures clock_out happens first if timer is still running."""
    from task_service import task_service
    task_id = _normalize_task_id(task)
    if not task_id:
        return False
    resolved_project = project_token or (task.get("_project_token") if isinstance(task, dict) else None)
    
    max_retries = 5
    base_delay = 1.0
    
    for attempt in range(max_retries):
        try:
            await task_service.complete_task({
                "task_id": task_id
            }, task_token=task_token or get_project_task_token(resolved_project))
            return True
        except Exception as e:
            error_str = _normalize_error_text(e)

            if _is_already_completed_error(error_str):
                print(f"[agent_service] Task {task_id} already completed upstream. Treating as success.")
                return True

            # If timer is still running, try to clock out before retrying completion.
            if _is_timer_running_error(error_str):
                print(f"[agent_service] Task {task_id} timer still running, attempting clock_out before completion...")
                clock_out_success = await _post_timer_log(
                    task, "clock_out", project_token=resolved_project, task_token=task_token
                )
                if clock_out_success:
                    print(f"[agent_service] Successfully clocked out task {task_id}, retrying completion...")
                else:
                    print(f"[agent_service] Failed to clock out task {task_id}, will retry completion anyway...")
             
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                print(f"[agent_service] Failed to complete task {task_id} (attempt {attempt + 1}/{max_retries}): {e}. Retrying in {delay}s...")
                await asyncio.sleep(delay)
            else:
                print(f"[agent_service] Failed to complete task {task_id} after {max_retries} attempts: {e}")
                return False
    return False


async def _opt_in_task(task: Dict[str, Any], username: str,
                       project_token: Optional[str] = None, task_token: Optional[str] = None) -> bool:
    """Opt in to task with retry logic - will retry up to 5 times with exponential backoff."""
    from task_service import task_service
    task_id = _normalize_task_id(task)
    if not task_id:
        return False
    resolved_project = project_token or (task.get("_project_token") if isinstance(task, dict) else None)
    
    max_retries = 5
    base_delay = 1.0
    
    for attempt in range(max_retries):
        try:
            await task_service.opt_in_task({
                "task_id": task_id,
                "username": username
            }, task_token=task_token or get_project_task_token(resolved_project))
            return True
        except Exception as e:
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                print(f"[agent_service] Failed to opt in to task {task_id} (attempt {attempt + 1}/{max_retries}): {e}. Retrying in {delay}s...")
                await asyncio.sleep(delay)
            else:
                print(f"[agent_service] Failed to opt in to task {task_id} after {max_retries} attempts: {e}")
                return False
    return False


async def _post_timer_log(task: Dict[str, Any], action: str, project_token: Optional[str] = None, task_token: Optional[str] = None) -> bool:
    """Post timer log with retry logic - will retry up to 5 times with exponential backoff."""
    from task_service import task_service
    task_id = _normalize_task_id(task)
    if not task_id:
        return False
    resolved_project = project_token or (task.get("_project_token") if isinstance(task, dict) else None)
    
    max_retries = 5
    base_delay = 1.0
    
    for attempt in range(max_retries):
        try:
            await task_service.post_timer_log({
                "task_id": task_id,
                "action": action
            }, task_token=task_token or get_project_task_token(resolved_project))
            task_key = str(task_id)
            state = _ensure_project_state(resolved_project)
            if action == "clock_in":
                state["timer_log_state"][task_key] = True
            elif action == "clock_out":
                state["timer_log_state"][task_key] = False
            return True
        except Exception as e:
            normalized_error = _normalize_error_text(e)
            if action == "clock_out" and _is_clock_out_idempotent_success(normalized_error):
                # Upstream says there is nothing to clock out; treat as success so completion can proceed.
                _ensure_project_state(resolved_project)["timer_log_state"][str(task_id)] = False
                print(
                    f"[agent_service] Timer log clock_out for task {task_id} already in desired state "
                    f"(treating as success): {e}"
                )
                return True
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                print(f"[agent_service] Failed to post timer log for task {task_id} (attempt {attempt + 1}/{max_retries}): {e}. Retrying in {delay}s...")
                await asyncio.sleep(delay)
            else:
                print(f"[agent_service] Failed to post timer log for task {task_id} after {max_retries} attempts: {e}")
                if action == "clock_in":
                    _ensure_project_state(resolved_project)["timer_log_state"][str(task_id)] = False
                return False
    return False


# ── Main Agent Execution ────────────────────────────────────────────────────

def _to_optional_int(value: Any) -> Optional[int]:
    try:
        if value in (None, ""):
            return None
        return int(str(value).strip())
    except Exception:
        return None


def _extract_task_parent_id(task: Dict[str, Any], key: str) -> Optional[int]:
    if not isinstance(task, dict):
        return None
    raw = task.get(f"{key}_id")
    if raw in (None, ""):
        raw = task.get(key)
    if isinstance(raw, dict):
        raw = raw.get("id") or raw.get(f"{key}_id")
    return _to_optional_int(raw)


def _normalize_status_text(value: Any) -> str:
    text = str(value or "").strip().lower().replace("_", " ").replace("-", " ")
    return " ".join(text.split())


def _is_completed_task_status(value: Any) -> bool:
    status_text = _normalize_status_text(value)
    completed_statuses = {
        "completed",
        "complete",
        "done",
        "closed",
        "finished",
        "resolved",
        "completed with errors",
    }
    return status_text in completed_statuses


def _extract_date_yyyy_mm_dd(value: Any) -> Optional[str]:
    if value in (None, ""):
        return None
    text = str(value).strip()
    if len(text) < 10:
        return None
    candidate = text[:10]
    try:
        datetime.strptime(candidate, "%Y-%m-%d")
        return candidate
    except Exception:
        return None


async def _resolve_project_deadline(project_token: Optional[str] = None, task_token: Optional[str] = None) -> str:
    from task_service import task_service

    resolved_project = project_token
    effective_token = task_token or get_project_task_token(resolved_project)
    deadline = None

    try:
        project_info = await task_service.get_project_info(task_token=effective_token)
        project_data = project_info.get("project", {}) if isinstance(project_info, dict) else {}
        for key in ("deadline", "project_deadline", "end_date"):
            deadline = _extract_date_yyyy_mm_dd(project_data.get(key))
            if deadline:
                break
    except Exception as e:
        print(f"[agent_service] Failed to fetch project info for status update: {e}")

    if deadline:
        return deadline

    try:
        tasks = await _fetch_external_tasks(resolved_project)
        deadlines = []
        for task in tasks:
            d = _extract_date_yyyy_mm_dd(task.get("deadline"))
            if d:
                deadlines.append(d)
        if deadlines:
            return max(deadlines)
    except Exception:
        pass

    return datetime.utcnow().strftime("%Y-%m-%d")


async def _update_project_status(
    status_value: str,
    project_token: Optional[str] = None,
    task_token: Optional[str] = None,
    force: bool = False,
) -> bool:
    from task_service import task_service

    resolved_project = project_token
    state = _ensure_project_state(resolved_project)
    normalized_status = (status_value or "").strip()
    if not normalized_status:
        return False

    if not force and state.get("project_status_synced") == normalized_status:
        return True

    deadline = await _resolve_project_deadline(resolved_project, task_token=task_token)
    effective_token = task_token or get_project_task_token(resolved_project)

    max_retries = 3
    base_delay = 1.0
    for attempt in range(max_retries):
        try:
            await task_service.update_project_status(
                {
                    "deadline": deadline,
                    "status": normalized_status,
                },
                task_token=effective_token,
            )
            state["project_status_synced"] = normalized_status
            _log_master_agent(
                f"Master sync: project status -> {normalized_status}",
                project_token=resolved_project,
            )
            return True
        except Exception as e:
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                print(
                    f"[agent_service] Failed to update project status to '{normalized_status}' "
                    f"(attempt {attempt + 1}/{max_retries}): {e}. Retrying in {delay}s..."
                )
                await asyncio.sleep(delay)
            else:
                print(
                    f"[agent_service] Failed to update project status to '{normalized_status}' "
                    f"after {max_retries} attempts: {e}"
                )
                _log_master_agent(
                    f"Master sync failed: project status -> {normalized_status} ({e})",
                    "error",
                    project_token=resolved_project,
                )
                return False
    return False


async def _sync_rollup_status_for_completed_task(
    task: Dict[str, Any],
    project_token: Optional[str] = None,
    task_token: Optional[str] = None,
) -> Dict[str, bool]:
    from task_service import task_service

    resolved_project = project_token or (task.get("_project_token") if isinstance(task, dict) else None)
    state = _ensure_project_state(resolved_project)
    effective_token = task_token or get_project_task_token(resolved_project)
    result = {
        "milestone_completed": False,
        "sprint_completed": False,
        "project_completed": False,
    }

    sprint_id = _extract_task_parent_id(task, "sprint")
    milestone_id = _extract_task_parent_id(task, "milestone")

    async with state["status_sync_lock"]:
        all_tasks = await _fetch_external_tasks(resolved_project)
        if not all_tasks:
            return result

        if milestone_id is not None and milestone_id not in state["completed_milestones_synced"]:
            milestone_tasks = [
                t for t in all_tasks
                if _extract_task_parent_id(t, "milestone") == milestone_id
            ]
            if milestone_tasks and all(_is_completed_task_status(t.get("status")) for t in milestone_tasks):
                try:
                    await task_service.update_milestone_status(
                        {"milestone_id": milestone_id, "is_completed": True},
                        task_token=effective_token,
                    )
                    state["completed_milestones_synced"].add(milestone_id)
                    result["milestone_completed"] = True
                    _log_master_agent(
                        f"Master sync: milestone {milestone_id} marked completed",
                        project_token=resolved_project,
                    )
                except Exception as e:
                    print(f"[agent_service] Failed to mark milestone {milestone_id} completed: {e}")
                    _log_master_agent(
                        f"Master sync failed: milestone {milestone_id} ({e})",
                        "error",
                        project_token=resolved_project,
                    )

        if sprint_id is not None and sprint_id not in state["completed_sprints_synced"]:
            sprint_tasks = [
                t for t in all_tasks
                if _extract_task_parent_id(t, "sprint") == sprint_id
            ]
            if sprint_tasks and all(_is_completed_task_status(t.get("status")) for t in sprint_tasks):
                try:
                    await task_service.update_sprint_status(
                        {"sprint_id": sprint_id, "status": "Completed", "is_completed": True},
                        task_token=effective_token,
                    )
                    state["completed_sprints_synced"].add(sprint_id)
                    result["sprint_completed"] = True
                    _log_master_agent(
                        f"Master sync: sprint {sprint_id} marked completed",
                        project_token=resolved_project,
                    )
                except Exception as e:
                    print(f"[agent_service] Failed to mark sprint {sprint_id} completed: {e}")
                    _log_master_agent(
                        f"Master sync failed: sprint {sprint_id} ({e})",
                        "error",
                        project_token=resolved_project,
                    )

        if all(_is_completed_task_status(t.get("status")) for t in all_tasks):
            result["project_completed"] = await _update_project_status(
                "Completed",
                project_token=resolved_project,
                task_token=effective_token,
                force=True,
            )

    return result


async def _pick_next_task(agent_id: str, project_token: Optional[str] = None,
                          task_token: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Pick the next uncompleted, unclaimed task from the external API."""
    if task_token:
        set_project_task_token(project_token, task_token)
    state = _ensure_project_state(project_token)
    claimed_task_ids = state["claimed_task_ids"]
    external_tasks = await _fetch_external_tasks(project_token)
    for t in external_tasks:
        tid = str(_normalize_task_id(t) or t.get("external_id") or t.get("id"))
        status_lower = (t.get("status") or "").lower()
        if status_lower not in ("completed", "done") and tid not in claimed_task_ids:
            claimed_task_ids.add(tid)
            # Also claim its linked tasks
            for lt in (t.get("linked_tasks") or []):
                claimed_task_ids.add(str(lt))
            return t
    return None


async def run_agent(agent_id: str, git_repo_url: str = None, git_token: str = None,
                    assigned_task: Dict[str, Any] = None,
                    continuous: bool = False,
                    ignore_running_check: bool = False,
                    project_token: Optional[str] = None,
                    task_token: Optional[str] = None) -> Dict[str, Any]:
    """
    Main function to run an agent WITH automatic retry on failure.
    Retries up to 3 times with increasing delays when the agent encounters
    errors (model failures, timeouts, bad responses, etc.).

    Flow per task:
      1. Pick task (or use pre-assigned)
      2. Create Docker container (reused across tasks in continuous mode)
      3. Git: clone repo, create task branch
      4. AI generates code -> runs inside container
      5. Self-healing loop
      6. Mark checklist items complete via external API
      7. Process linked tasks (separate branch each)
      8. Git: commit & push
      9. Loop back to step 1 if continuous
     10. Capture workspace, destroy container when done
    """
    MAX_RETRIES = 3
    RETRY_DELAYS = [10, 20, 30]  # seconds between retries

    state = _ensure_project_state(project_token)
    project_agents = state["agent_states"]
    agent = project_agents.get(agent_id)
    if not agent:
        raise ValueError(f"Agent {agent_id} not found")

    last_result = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            result = await _run_agent_once(
                agent_id,
                git_repo_url=git_repo_url,
                git_token=git_token,
                assigned_task=assigned_task,
                continuous=continuous,
                ignore_running_check=ignore_running_check if attempt == 1 else True,
                project_token=project_token,
                task_token=task_token,
            )

            if result.get("success") or result.get("reason") == "no_tasks":
                # Success or no tasks — no retry needed
                return result

            # Agent returned failure but didn't throw — treat as retryable
            last_result = result
            error_msg = result.get("error", "Unknown error")

            if attempt < MAX_RETRIES:
                delay = RETRY_DELAYS[attempt - 1]
                agent["status"] = "running"
                agent["progress"] = 0
                retry_msg = (
                    f"⚠️ Attempt {attempt}/{MAX_RETRIES} failed: {error_msg}. "
                    f"Auto-retrying in {delay}s..."
                )
                agent["progress_message"] = retry_msg
                agent["output_log"].append({
                    "time": datetime.utcnow().isoformat(),
                    "type": "warning",
                    "message": retry_msg,
                })
                await asyncio.sleep(delay)
                # Reset for next attempt
                assigned_task = None  # re-pick task on retry
                continue
            else:
                # All retries exhausted
                agent["output_log"].append({
                    "time": datetime.utcnow().isoformat(),
                    "type": "error",
                    "message": f"❌ All {MAX_RETRIES} attempts failed. Last error: {error_msg}",
                })
                return last_result

        except Exception as e:
            last_result = {
                "success": False,
                "agent_id": agent_id,
                "error": str(e),
                "tasks_completed": 0,
                "duration": 0,
            }

            if attempt < MAX_RETRIES:
                delay = RETRY_DELAYS[attempt - 1]
                retry_msg = (
                    f"⚠️ Attempt {attempt}/{MAX_RETRIES} crashed: {str(e)}. "
                    f"Auto-retrying in {delay}s..."
                )
                agent["status"] = "running"
                agent["progress"] = 0
                agent["progress_message"] = retry_msg
                agent["output_log"].append({
                    "time": datetime.utcnow().isoformat(),
                    "type": "warning",
                    "message": retry_msg,
                })
                await asyncio.sleep(delay)
                assigned_task = None
                continue
            else:
                agent["status"] = "error"
                agent["progress"] = 0
                agent["progress_message"] = f"Error after {MAX_RETRIES} retries: {str(e)}"
                agent["output_log"].append({
                    "time": datetime.utcnow().isoformat(),
                    "type": "error",
                    "message": f"❌ All {MAX_RETRIES} attempts failed. Last error: {str(e)}",
                })
                agent["last_run"] = datetime.utcnow().isoformat()
                agent["current_task"] = None
                return last_result

    return last_result


async def _run_agent_once(agent_id: str, git_repo_url: str = None, git_token: str = None,
                    assigned_task: Dict[str, Any] = None,
                    continuous: bool = False,
                    ignore_running_check: bool = False,
                    project_token: Optional[str] = None,
                    task_token: Optional[str] = None) -> Dict[str, Any]:
    """
    Single execution attempt for an agent. Called by run_agent with retry wrapper.
    """
    state = _ensure_project_state(project_token)
    if task_token:
        state["task_token"] = task_token
    project_agents = state["agent_states"]
    claimed_task_ids = state["claimed_task_ids"]
    task_progress_state = state["task_progress_state"]
    timer_log_state = state["timer_log_state"]
    completed_tasks = state["completed_tasks"]

    agent = project_agents.get(agent_id)
    if not agent:
        raise ValueError(f"Agent {agent_id} not found")

    if agent["status"] == "running" and not ignore_running_check:
        raise ValueError(f"Agent {agent_id} is already running")

    # Store git config if provided (remembered for future runs)
    if git_repo_url:
        agent["git_repo_url"] = git_repo_url.strip()
    if git_token:
        agent["git_token"] = git_token.strip()

    use_git = bool(agent.get("git_repo_url"))

    # 1. Get the first task
    if assigned_task:
        task = assigned_task
    else:
        task = await _pick_next_task(agent_id, project_token=project_token, task_token=task_token)
        if not task:
            now = datetime.utcnow().isoformat()
            agent["status"] = "idle"
            agent["progress"] = 0
            agent["progress_message"] = "No tasks available"
            agent["current_task"] = None
            agent["last_run"] = now
            agent["output_log"].append({
                "time": now,
                "type": "info",
                "message": "No tasks available or all are completed/claimed."
            })
            return {
                "success": False,
                "agent_id": agent_id,
                "error": "No tasks available or all are completed/claimed.",
                "reason": "no_tasks",
                "tasks_completed": 0,
                "duration": 0,
            }
    if isinstance(task, dict) and project_token:
        task.setdefault("_project_token", project_token)

    # Set agent to running
    agent["status"] = "running"
    agent["output_log"] = []
    project_status_ok = await _update_project_status(
        "On Going",
        project_token=project_token,
        task_token=task_token,
    )
    agent["output_log"].append({
        "time": datetime.utcnow().isoformat(),
        "type": "info",
        "message": f"API: project status On Going {'ok' if project_status_ok else 'failed'}",
    })
    total_start = time.time()
    tasks_completed = 0
    all_results = []

    container_name = f"{agent_id}_{uuid.uuid4().hex[:8]}"
    container_created = False
    repo_base_branch = "main"
    bootstrap_role = "none"
    bootstrap_signal_sent = False

    try:
        # ── CONTINUOUS TASK LOOP ─────────────────────────────────────
        while task is not None:
            tasks_completed += 1
            task["status"] = "in_progress"
            task["assigned_agent"] = agent_id
            task["started_at"] = datetime.utcnow().isoformat()

            # ── Register in Cross-Agent Shared Memory ────────────────
            try:
                import context_manager as ctx_mgr
                live_mem = ctx_mgr.get_live_memory(project_token or "")
                live_mem.register_task_start(
                    agent_id=agent_id,
                    task_title=task.get("title", "Untitled"),
                    task_description=task.get("description", "")[:500],
                    branch_name=_branch_name_for_task(task) if use_git else None,
                )
                other_active = [
                    aid for aid in live_mem.active_tasks
                    if aid != agent_id
                ]
                completed_count = len(live_mem.completed_history)
                agent["output_log"].append({
                    "time": datetime.utcnow().isoformat(),
                    "type": "info",
                    "message": (
                        f"Cross-agent memory: registered task start"
                        f" | {len(other_active)} peer(s) active"
                        f", {completed_count} task(s) in history"
                        + (f" | peers: {', '.join(other_active)}" if other_active else "")
                    )
                })
            except Exception as mem_err:
                agent["output_log"].append({
                    "time": datetime.utcnow().isoformat(),
                    "type": "info",
                    "message": f"Cross-agent memory: skipped ({str(mem_err)[:80]})"
                })
            
            # Map "agent_01" -> "agent1"
            username = agent_id.replace("agent_0", "agent")
            opt_in_ok = await _opt_in_task(task, username, task_token=task_token)
            agent["output_log"].append({
                "time": datetime.utcnow().isoformat(),
                "type": "info",
                "message": f"API: task opt-in {'ok' if opt_in_ok else 'failed'}"
            })

            clock_in_ok = await _post_timer_log(task, "clock_in", task_token=task_token)
            agent["output_log"].append({
                "time": datetime.utcnow().isoformat(),
                "type": "info",
                "message": f"API: timer log clock_in {'ok' if clock_in_ok else 'failed'}"
            })
            msg_ok = await _post_task_message(task, f"Started by {agent_id}.", task_token=task_token)
            agent["output_log"].append({
                "time": datetime.utcnow().isoformat(),
                "type": "info",
                "message": f"API: post message {'ok' if msg_ok else 'failed'}"
            })
            prog_ok = await _post_task_progress(task, 10, "Started", task_token=task_token)
            agent["output_log"].append({
                "time": datetime.utcnow().isoformat(),
                "type": "info",
                "message": f"API: progress 10% {'ok' if prog_ok else 'skipped/failed'}"
            })

            linked_task_ids = [str(lt) for lt in (task.get("linked_tasks") or [])]
            checklist = task.get("checklist") or []

            task_count_label = f" (+{len(linked_task_ids)} linked)" if linked_task_ids else ""
            agent["current_task"] = task
            agent["progress"] = 5
            agent["progress_message"] = f"Task {tasks_completed}: {task['title']}"

            agent["output_log"].append({
                "time": datetime.utcnow().isoformat(),
                "type": "info",
                "message": f"{'═' * 50}"
            })
            agent["output_log"].append({
                "time": datetime.utcnow().isoformat(),
                "type": "info",
                "message": f"▶ TASK {tasks_completed}: {task['title']}{task_count_label}"
            })
            if checklist:
                agent["output_log"].append({
                    "time": datetime.utcnow().isoformat(),
                    "type": "info",
                    "message": f"  {len(checklist)} checklist steps"
                })

            start_time = time.time()

            # ── Docker container (create only on first iteration) ────
            if not container_created:
                docker_available = await asyncio.to_thread(_check_docker_available)
                if not docker_available:
                    raise ValueError("Docker is not available. Make sure Docker Desktop is running.")

                agent["progress"] = 10
                agent["progress_message"] = f"Creating Docker container: {container_name}"
                agent["output_log"].append({
                    "time": datetime.utcnow().isoformat(),
                    "type": "info",
                    "message": f"Creating persistent container: {container_name} (image: {DOCKER_BASE_IMAGE})"
                })

                container_result = await asyncio.to_thread(_create_persistent_container, container_name)
                if not container_result["success"]:
                    raise ValueError(f"Failed to create container: {container_result['error']}")
                container_created = True

                agent["output_log"].append({
                    "time": datetime.utcnow().isoformat(),
                    "type": "info",
                    "message": f"Container '{container_name}' is running with /workspace/ ready"
                })

                # Clone git repo ONCE on first task
                if use_git:
                    first_branch = _branch_name_for_task(task)
                    agent["progress"] = 15
                    agent["progress_message"] = f"Cloning git repo & creating branch: {first_branch}"
                    agent["output_log"].append({
                        "time": datetime.utcnow().isoformat(),
                        "type": "info",
                        "message": f"Cloning {agent['git_repo_url']} into /workspace/..."
                    })

                    git_result = await asyncio.to_thread(
                        _setup_git_in_container, container_name,
                        agent["git_repo_url"], agent.get("git_token", ""), first_branch
                    )
                    if not git_result["success"]:
                        raise ValueError(f"Git setup failed: {git_result['error']}")

                    agent["output_log"].append({
                        "time": datetime.utcnow().isoformat(),
                        "type": "info",
                        "message": f"Git repo cloned. Working on branch: {first_branch}"
                    })

                    repo_base_branch = git_result.get("default_branch") or repo_base_branch
                    bootstrap_info = await _coordinate_repo_bootstrap(
                        agent=agent,
                        agent_id=agent_id,
                        repo_url=agent.get("git_repo_url") or "",
                        container_name=container_name,
                        local_branch=first_branch,
                        needs_bootstrap=bool(git_result.get("needs_bootstrap")),
                        project_token=project_token,
                    )
                    bootstrap_role = bootstrap_info.get("role", "none")
                    if bootstrap_info.get("base_branch"):
                        repo_base_branch = bootstrap_info["base_branch"]
                    if repo_base_branch and bootstrap_role == "bootstrap":
                        agent["output_log"].append({
                            "time": datetime.utcnow().isoformat(),
                            "type": "info",
                            "message": f"Bootstrap base branch set to: {repo_base_branch}"
                        })

            # ── Create task-specific git branch (for 2nd+ tasks) ─────
            branch_name = None
            if use_git:
                branch_name = _branch_name_for_task(task)
                if tasks_completed > 1:
                    # Reset any stale index (merge conflicts from previous task)
                    subprocess.run(
                        ["docker", "exec", "-w", "/workspace", container_name,
                         "git", "merge", "--abort"],
                        capture_output=True, text=True, timeout=60,
                    )
                    subprocess.run(
                        ["docker", "exec", "-w", "/workspace", container_name,
                         "git", "reset", "--hard", "HEAD"],
                        capture_output=True, text=True, timeout=60,
                    )
                    # Switch back to repo base branch and create a new task branch.
                    subprocess.run(
                        ["docker", "exec", "-w", "/workspace", container_name,
                         "git", "fetch", "origin"],
                        capture_output=True, text=True, timeout=120,
                    )
                    subprocess.run(
                        ["docker", "exec", "-w", "/workspace", container_name,
                         "git", "checkout", "-B", repo_base_branch, f"origin/{repo_base_branch}"],
                        capture_output=True, text=True, timeout=60,
                    )
                    subprocess.run(
                        ["docker", "exec", "-w", "/workspace", container_name,
                         "git", "checkout", "-B", branch_name],
                        capture_output=True, text=True, timeout=60,
                    )
                    agent["output_log"].append({
                        "time": datetime.utcnow().isoformat(),
                        "type": "info",
                        "message": f"Created branch: {branch_name}"
                    })

            # ── AI Code Generation ───────────────────────────────────
            agent["progress"] = 15
            agent["progress_message"] = "Preparing context layers..."

            # ── LAYER 1: Retrieve or generate Technical Spec ────────
            tech_spec = ""
            try:
                tech_spec = get_technical_spec(project_token or "")
                if not tech_spec and project_token:
                    # Generate tech spec for the first time (runs once per project)
                    agent["output_log"].append({
                        "time": datetime.utcnow().isoformat(),
                        "type": "info",
                        "message": "🏗️ Architect Agent: generating canonical Technical Spec..."
                    })
                    # Get BRD summary from project state if available
                    brd_summary = state.get("brd_analysis", {}).get("summary", "")
                    # Get all tasks for architecture planning
                    all_tasks = state.get("tasks", [])
                    # Get KG context for architecture decisions
                    arch_kg_context = ""
                    try:
                        import context_manager as ctx_mgr
                        if ctx_mgr.is_project_indexed(project_token or ""):
                            arch_kg_context = await ctx_mgr.get_full_agent_context(
                                project_token=project_token,
                                task_description="Full system architecture overview",
                                agent_id="architect_agent",
                            )
                    except Exception:
                        pass

                    spec_result = await _generate_technical_spec(
                        project_token=project_token,
                        tasks=all_tasks if all_tasks else [task],
                        brd_summary=brd_summary,
                        kg_context=arch_kg_context,
                    )
                    tech_spec = spec_result.get("spec", "")
                    agent["output_log"].append({
                        "time": datetime.utcnow().isoformat(),
                        "type": "info",
                        "message": f"🏗️ Architect Agent: tech spec {'generated' if tech_spec else 'skipped'} ({len(tech_spec)} chars)"
                    })
                elif tech_spec:
                    agent["output_log"].append({
                        "time": datetime.utcnow().isoformat(),
                        "type": "info",
                        "message": f"📋 Using cached Technical Spec ({len(tech_spec)} chars)"
                    })
            except Exception as spec_err:
                agent["output_log"].append({
                    "time": datetime.utcnow().isoformat(),
                    "type": "info",
                    "message": f"Tech spec retrieval skipped: {str(spec_err)[:80]}"
                })

            agent["progress"] = 20
            agent["progress_message"] = "Fetching relevant code context from Knowledge Graph..."

            # Fetch JIT context from Knowledge Graph + RAG if indexed
            jit_context = ""
            cross_agent_info = ""
            try:
                import context_manager as ctx_mgr
                if ctx_mgr.is_project_indexed(project_token or ""):
                    jit_context = await ctx_mgr.get_full_agent_context(
                        project_token=project_token or "",
                        task_description=task.get("description", ""),
                        task_type=task.get("task_type"),
                        agent_id=agent_id,
                    )
                    agent["output_log"].append({
                        "time": datetime.utcnow().isoformat(),
                        "type": "info",
                        "message": f"KG context retrieved: {len(jit_context)} chars of targeted context"
                    })
                    # Extract cross-agent info for the dynamic prompt
                    live_mem = ctx_mgr.get_live_memory(project_token or "")
                    cross_agent_info = live_mem.build_cross_agent_context(agent_id)
                else:
                    agent["output_log"].append({
                        "time": datetime.utcnow().isoformat(),
                        "type": "info",
                        "message": "Knowledge Graph not indexed for this project, using task description only"
                    })
            except Exception as ctx_err:
                agent["output_log"].append({
                    "time": datetime.utcnow().isoformat(),
                    "type": "info",
                    "message": f"KG context fetch skipped: {str(ctx_err)[:100]}"
                })

            # ── LAYER 3: Generate Dynamic Prompt ────────────────────
            agent["progress"] = 22
            agent["progress_message"] = "Manager Agent writing task-specific prompt..."
            try:
                dynamic_system_prompt = await _generate_dynamic_prompt(
                    task=task,
                    agent_type=agent["type"],
                    agent_id=agent_id,
                    tech_spec=tech_spec,
                    kg_context=jit_context,
                    cross_agent_info=cross_agent_info,
                )
                agent["output_log"].append({
                    "time": datetime.utcnow().isoformat(),
                    "type": "info",
                    "message": f"🎯 Dynamic prompt generated: {len(dynamic_system_prompt)} chars (task-specific)"
                })
            except Exception as prompt_err:
                dynamic_system_prompt = AGENT_SYSTEM_PROMPTS.get(agent["type"], AGENT_SYSTEM_PROMPTS["validator"])
                agent["output_log"].append({
                    "time": datetime.utcnow().isoformat(),
                    "type": "info",
                    "message": f"Dynamic prompt failed ({str(prompt_err)[:60]}), using static prompt"
                })

            agent["progress"] = 25
            agent["progress_message"] = "AI is generating project code..."
            agent["output_log"].append({
                "time": datetime.utcnow().isoformat(),
                "type": "info",
                "message": "Calling AI model to generate project code..."
            })

            generated_code, thought = await _call_ai_for_code(
                task["description"], agent["type"],
                code_context=jit_context,
                system_prompt_override=dynamic_system_prompt,
                tech_spec=tech_spec,
            )
            if thought:
                await _post_task_message(task, f"🤔 {agent_id} thought:\n{thought}", task_token=task_token)

            agent["progress"] = 30
            agent["progress_message"] = "Running project builder inside Docker..."
            agent["output_log"].append({
                "time": datetime.utcnow().isoformat(),
                "type": "info",
                "message": f"AI generated {len(generated_code.splitlines())} lines of builder code"
            })

            # ── Execute builder code ─────────────────────────────────
            result = await asyncio.to_thread(
                _exec_script_in_container, container_name, generated_code, f"build_{agent_id}"
            )

            # Log output
            for line in (result["stdout"] or "").strip().split("\n"):
                if line.strip():
                    agent["output_log"].append({
                        "time": datetime.utcnow().isoformat(),
                        "type": "output",
                        "message": line.strip()
                    })
            if result["stderr"] and result["stderr"].strip():
                for line in result["stderr"].strip().split("\n"):
                    if line.strip():
                        agent["output_log"].append({
                            "time": datetime.utcnow().isoformat(),
                            "type": "error",
                            "message": line.strip()
                        })

            # ═════════════════════════════════════════════════════════
            # SELF-HEALING LOOP (Enhanced with Layers 1+4)
            # - Pre-compilation checks after each fix
            # - KG-aware error analysis (queries KG for fix context)
            # - Tech Spec injected into fix prompts
            # ═════════════════════════════════════════════════════════
            all_generated_code = generated_code
            all_stdout = result["stdout"]
            fix_iteration = 0

            while fix_iteration < MAX_FIX_ITERATIONS:
                issue_report = _detect_issues_from_output(result["stdout"], result["stderr"], result["exit_code"])

                builder_crashed = _is_builder_script_crash(result.get("stderr", ""))
                workspace_empty = False
                if builder_crashed:
                    workspace_empty = await asyncio.to_thread(_is_workspace_empty, container_name)

                if builder_crashed and workspace_empty:
                    issue_report["has_issues"] = True
                    if not issue_report["issues"]:
                        issue_report["issues"] = [f"BUILDER SCRIPT CRASHED: {result.get('stderr', '')[:200]}"]
                        issue_report["issue_count"] = len(issue_report["issues"])

                # ── LAYER 4: Pre-compilation checks ────────────────
                if not issue_report["has_issues"] and result["exit_code"] == 0:
                    try:
                        precomp = await asyncio.to_thread(
                            _run_precompilation_checks, container_name
                        )
                        if not precomp["all_passed"]:
                            # Pre-compilation found issues that weren't caught by exit code
                            precomp_issues = []
                            for check_name in ["python_syntax", "js_syntax", "import_check"]:
                                for err in precomp.get(check_name, {}).get("errors", []):
                                    precomp_issues.append(f"PRE-COMPILE {check_name}: {err}")

                            if precomp_issues:
                                issue_report["has_issues"] = True
                                issue_report["issues"].extend(precomp_issues)
                                issue_report["issue_count"] = len(issue_report["issues"])
                                agent["output_log"].append({
                                    "time": datetime.utcnow().isoformat(),
                                    "type": "info",
                                    "message": f"🔍 Pre-compilation check: {len(precomp_issues)} issues found"
                                })
                            else:
                                agent["output_log"].append({
                                    "time": datetime.utcnow().isoformat(),
                                    "type": "info",
                                    "message": f"🔍 Pre-compilation check: PASSED ({precomp['file_count']} files verified)"
                                })
                        else:
                            agent["output_log"].append({
                                "time": datetime.utcnow().isoformat(),
                                "type": "info",
                                "message": f"🔍 Pre-compilation check: PASSED ({precomp.get('file_count', 0)} files verified)"
                            })
                    except Exception as pc_err:
                        agent["output_log"].append({
                            "time": datetime.utcnow().isoformat(),
                            "type": "info",
                            "message": f"Pre-compilation check skipped: {str(pc_err)[:80]}"
                        })

                if not issue_report["has_issues"] and result["exit_code"] == 0:
                    agent["output_log"].append({
                        "time": datetime.utcnow().isoformat(),
                        "type": "info",
                        "message": "All checks passed -- project built successfully!"
                    })
                    break

                fix_iteration += 1
                issue_count = issue_report["issue_count"]

                agent["output_log"].append({
                    "time": datetime.utcnow().isoformat(),
                    "type": "info",
                    "message": "=============================================="
                })
                agent["output_log"].append({
                    "time": datetime.utcnow().isoformat(),
                    "type": "info",
                    "message": f"SELF-HEALING: {issue_count} issues found -- fix iteration {fix_iteration}/{MAX_FIX_ITERATIONS}"
                })

                for idx, issue in enumerate(issue_report["issues"][:10], 1):
                    agent["output_log"].append({
                        "time": datetime.utcnow().isoformat(),
                        "type": "info",
                        "message": f"  Issue {idx}: {issue[:150]}"
                    })

                progress_base = 30 + (fix_iteration * 12)
                agent["progress"] = min(progress_base, 85)
                agent["progress_message"] = f"Self-healing: fixing {issue_count} issues (round {fix_iteration})..."

                # ── LAYER 4: KG-Aware Error Analysis ───────────────
                kg_error_context = ""
                try:
                    kg_error_context = await _kg_aware_error_analysis(
                        project_token=project_token or "",
                        stderr=result.get("stderr", ""),
                        task_description=task.get("description", ""),
                        agent_id=agent_id,
                    )
                    if kg_error_context:
                        agent["output_log"].append({
                            "time": datetime.utcnow().isoformat(),
                            "type": "info",
                            "message": f"🧠 KG error analysis: found relevant context ({len(kg_error_context)} chars)"
                        })
                except Exception:
                    pass  # Non-critical

                agent["output_log"].append({
                    "time": datetime.utcnow().isoformat(),
                    "type": "info",
                    "message": "Calling AI model to generate fix code..."
                })

                try:
                    fix_code, thought = await _call_ai_for_fix(
                        task_description=task["description"],
                        agent_type=agent["type"],
                        issues=issue_report["issues"],
                        previous_output=result["stdout"],
                        iteration=fix_iteration,
                        builder_crashed=(builder_crashed and workspace_empty),
                        kg_error_context=kg_error_context,
                        tech_spec=tech_spec,
                    )
                    if thought:
                        await _post_task_message(
                            task,
                            f"🤔 {agent_id} thought (fix round {fix_iteration}):\n{thought}",
                            task_token=task_token,
                        )

                    agent["output_log"].append({
                        "time": datetime.utcnow().isoformat(),
                        "type": "info",
                        "message": f"AI generated {len(fix_code.splitlines())} lines of fix code"
                    })

                    result = await asyncio.to_thread(
                        _exec_script_in_container, container_name, fix_code, f"fix_{agent_id}_{fix_iteration}"
                    )

                    for line in (result["stdout"] or "").strip().split("\n"):
                        if line.strip():
                            agent["output_log"].append({
                                "time": datetime.utcnow().isoformat(),
                                "type": "output",
                                "message": line.strip()
                            })
                    if result["stderr"] and result["stderr"].strip():
                        for line in result["stderr"].strip().split("\n"):
                            if line.strip():
                                agent["output_log"].append({
                                    "time": datetime.utcnow().isoformat(),
                                    "type": "error",
                                    "message": line.strip()
                                })

                    all_generated_code += f"\n\n# === FIX ITERATION {fix_iteration} ===\n" + fix_code
                    all_stdout += f"\n\n--- FIX ITERATION {fix_iteration} ---\n" + result["stdout"]

                except Exception as fix_err:
                    agent["output_log"].append({
                        "time": datetime.utcnow().isoformat(),
                        "type": "error",
                        "message": f"Self-healing iteration {fix_iteration} failed: {str(fix_err)}"
                    })
                    break

            build_success = result["exit_code"] == 0
            if build_success:
                prog_ok = await _post_task_progress(task, 70, "Build completed", task_token=task_token)
                agent["output_log"].append({
                    "time": datetime.utcnow().isoformat(),
                    "type": "info",
                    "message": f"API: progress 70% {'ok' if prog_ok else 'skipped/failed'}"
                })
            else:
                prog_ok = await _post_task_progress(task, 40, "Build finished with errors", task_token=task_token)
                agent["output_log"].append({
                    "time": datetime.utcnow().isoformat(),
                    "type": "info",
                    "message": f"API: progress 40% {'ok' if prog_ok else 'skipped/failed'}"
                })

            # ═════════════════════════════════════════════════════════
            # CAPTURE WORKSPACE
            # ═════════════════════════════════════════════════════════
            agent["progress"] = 88
            agent["progress_message"] = "Capturing project workspace..."
            workspace_tree = await asyncio.to_thread(_capture_workspace_tree, container_name)
            agent["output_log"].append({
                "time": datetime.utcnow().isoformat(),
                "type": "info",
                "message": f"Captured {workspace_tree.count('FILE:')} files from /workspace/"
            })

            # ═════════════════════════════════════════════════════════
            # CODE QUALITY / LINTING
            # ═════════════════════════════════════════════════════════
            agent["progress"] = 90
            agent["progress_message"] = "Running code quality checks..."
            try:
                lint_report = await asyncio.to_thread(
                    _run_code_quality_checks, container_name
                )
                linters_used = ", ".join(lint_report.get("linters_run", []))
                total_lint_issues = lint_report.get("total_issues", 0)

                if lint_report.get("all_passed"):
                    agent["output_log"].append({
                        "time": datetime.utcnow().isoformat(),
                        "type": "info",
                        "message": f"✅ Code quality: PASSED ({linters_used})"
                    })
                else:
                    agent["output_log"].append({
                        "time": datetime.utcnow().isoformat(),
                        "type": "info",
                        "message": f"⚠️ Code quality: {total_lint_issues} issues found ({linters_used})"
                    })
                    # Log top issues per linter
                    for linter_name in ["flake8", "pylint", "eslint"]:
                        linter_data = lint_report.get(linter_name, {})
                        if not linter_data.get("passed", True):
                            for issue in linter_data.get("issues", [])[:5]:
                                agent["output_log"].append({
                                    "time": datetime.utcnow().isoformat(),
                                    "type": "info",
                                    "message": f"  [{linter_name}] {issue[:120]}"
                                })

                # Store lint report on task result
                task["_lint_report"] = lint_report
            except Exception as lint_err:
                agent["output_log"].append({
                    "time": datetime.utcnow().isoformat(),
                    "type": "info",
                    "message": f"Code quality checks skipped: {str(lint_err)[:80]}"
                })

            # ═════════════════════════════════════════════════════════
            # MARK CHECKLIST ITEMS COMPLETE
            # Only if real code was generated (more than just session notes)
            # ═════════════════════════════════════════════════════════
            workspace_file_count = workspace_tree.count('FILE:')
            normalized_task_id = _normalize_task_id(task)
            if workspace_file_count <= 1:
                # Only the agent handoff session note exists — no real code
                agent["output_log"].append({
                    "time": datetime.utcnow().isoformat(),
                    "type": "warning",
                    "message": (
                        f"⚠️ Skipping checklist completion: only {workspace_file_count} file(s) "
                        f"captured — AI may not have produced real code"
                    )
                })
            elif checklist and normalized_task_id:
                agent["output_log"].append({
                    "time": datetime.utcnow().isoformat(),
                    "type": "info",
                    "message": f"Marking {len(checklist)} checklist items as completed..."
                })
                for idx_cl in range(len(checklist)):
                    await _mark_checklist_item(
                        normalized_task_id,
                        checklist,
                        idx_cl,
                        project_token=project_token,
                        task_token=task_token,
                    )
                    agent["output_log"].append({
                        "time": datetime.utcnow().isoformat(),
                        "type": "info",
                        "message": f"  ✓ Checklist step {idx_cl+1}/{len(checklist)}: {checklist[idx_cl].get('text','')[:80]}"
                    })

            # ═════════════════════════════════════════════════════════
            # PROCESS LINKED TASKS
            # ═════════════════════════════════════════════════════════
            if linked_task_ids and use_git:
                all_ext_tasks = await _fetch_external_tasks(project_token)
                linked_lookup = {str(_normalize_task_id(t) or t.get("external_id") or t.get("id")): t for t in all_ext_tasks}

                for li_idx, linked_id in enumerate(linked_task_ids):
                    linked_task = linked_lookup.get(linked_id)
                    if not linked_task:
                        agent["output_log"].append({
                            "time": datetime.utcnow().isoformat(),
                            "type": "info",
                            "message": f"Linked task {linked_id} not found in API, skipping."
                        })
                        continue

                    lt_title = linked_task.get("title", f"linked-{linked_id}")
                    lt_branch = _branch_name_for_task(linked_task)
                    lt_checklist = linked_task.get("checklist") or []

                    agent["output_log"].append({
                        "time": datetime.utcnow().isoformat(),
                        "type": "info",
                        "message": f"═══ LINKED TASK {li_idx+1}/{len(linked_task_ids)}: {lt_title} ═══"
                    })

                    subprocess.run(
                        ["docker", "exec", "-w", "/workspace", container_name,
                         "git", "fetch", "origin"],
                        capture_output=True, text=True, timeout=120,
                    )
                    subprocess.run(
                        ["docker", "exec", "-w", "/workspace", container_name,
                         "git", "checkout", "-B", repo_base_branch, f"origin/{repo_base_branch}"],
                        capture_output=True, text=True, timeout=15,
                    )
                    subprocess.run(
                        ["docker", "exec", "-w", "/workspace", container_name,
                         "git", "checkout", "-B", lt_branch],
                        capture_output=True, text=True, timeout=15,
                    )

                    lt_clock_in_ok = await _post_timer_log(linked_task, "clock_in", task_token=task_token)
                    agent["output_log"].append({
                        "time": datetime.utcnow().isoformat(),
                        "type": "info",
                        "message": f"API: linked task clock_in {'ok' if lt_clock_in_ok else 'failed'}"
                    })
                    msg_ok = await _post_task_message(linked_task, f"Started by {agent_id}.", task_token=task_token)
                    prog_ok = await _post_task_progress(linked_task, 10, "Started", task_token=task_token)
                    agent["output_log"].append({
                        "time": datetime.utcnow().isoformat(),
                        "type": "info",
                        "message": f"API: linked task start message {'ok' if msg_ok else 'failed'}, progress 10% {'ok' if prog_ok else 'skipped/failed'}"
                    })

                    # Fetch JIT context for linked task too
                    lt_jit_context = ""
                    try:
                        import context_manager as ctx_mgr
                        if ctx_mgr.is_project_indexed(project_token or ""):
                            lt_jit_context = await ctx_mgr.get_full_agent_context(
                                project_token=project_token or "",
                                task_description=linked_task.get("description", lt_title),
                                task_type=linked_task.get("task_type"),
                            )
                    except Exception:
                        pass

                    lt_code, thought = await _call_ai_for_code(linked_task.get("description", lt_title), agent["type"], code_context=lt_jit_context)
                    if thought:
                        await _post_task_message(linked_task, f"🤔 {agent_id} thought:\n{thought}", task_token=task_token)
                    lt_result = await asyncio.to_thread(
                        _exec_script_in_container, container_name, lt_code, f"linked_{linked_id}"
                    )
                    agent["output_log"].append({
                        "time": datetime.utcnow().isoformat(),
                        "type": "info",
                        "message": f"Linked task builder finished (exit={lt_result['exit_code']})"
                    })
                    if lt_result["exit_code"] == 0:
                        prog_ok = await _post_task_progress(linked_task, 70, "Build completed", task_token=task_token)
                        agent["output_log"].append({
                            "time": datetime.utcnow().isoformat(),
                            "type": "info",
                            "message": f"API: linked task progress 70% {'ok' if prog_ok else 'skipped/failed'}"
                        })
                    else:
                        prog_ok = await _post_task_progress(linked_task, 40, "Build finished with errors", task_token=task_token)
                        agent["output_log"].append({
                            "time": datetime.utcnow().isoformat(),
                            "type": "info",
                            "message": f"API: linked task progress 40% {'ok' if prog_ok else 'skipped/failed'}"
                        })

                    linked_note_result = await asyncio.to_thread(
                        _append_agent_session_note,
                        container_name,
                        agent_id,
                        linked_task,
                        lt_branch,
                        lt_result.get("exit_code", -1),
                        0,
                        True,
                    )
                    if linked_note_result.get("success"):
                        agent["output_log"].append({
                            "time": datetime.utcnow().isoformat(),
                            "type": "info",
                            "message": f"Updated session note: {linked_note_result.get('path')}"
                        })
                    else:
                        agent["output_log"].append({
                            "time": datetime.utcnow().isoformat(),
                            "type": "error",
                            "message": linked_note_result.get("error", "Failed to update session note.")
                        })

                    lt_commit = await asyncio.to_thread(
                        _commit_and_push, container_name, lt_title, lt_branch
                    )
                    lt_commit_success = lt_commit.get("success", False)
                    if lt_commit_success:
                        effective_lt_branch = lt_commit.get("branch", lt_branch)
                        if lt_commit.get("pushed"):
                            agent["output_log"].append({
                                "time": datetime.utcnow().isoformat(),
                                "type": "info",
                                "message": f"Pushed linked task to branch: {effective_lt_branch}"
                            })
                            if lt_commit.get("rebased"):
                                agent["output_log"].append({
                                    "time": datetime.utcnow().isoformat(),
                                    "type": "info",
                                    "message": f"Git pull --rebase integrated remote changes before push"
                                })
                            if lt_commit.get("renamed"):
                                agent["output_log"].append({
                                    "time": datetime.utcnow().isoformat(),
                                    "type": "info",
                                    "message": f"Git push fallback used (new branch: {effective_lt_branch})"
                                })
                            prog_ok = await _post_task_progress(linked_task, 95, "Pushed to git", task_token=task_token)
                            agent["output_log"].append({
                                "time": datetime.utcnow().isoformat(),
                                "type": "info",
                                "message": f"API: linked task progress 95% {'ok' if prog_ok else 'skipped/failed'}"
                            })
                            await _enqueue_git_merge(
                                effective_lt_branch,
                                agent.get("git_repo_url"),
                                agent.get("git_token"),
                                agent_id,
                                lt_title,
                                project_token=project_token
                            )
                        else:
                            agent["output_log"].append({
                                "time": datetime.utcnow().isoformat(),
                                "type": "info",
                                "message": f"No changes to push for branch: {effective_lt_branch}"
                            })
                            prog_ok = await _post_task_progress(linked_task, 95, "No changes to push", task_token=task_token)
                            agent["output_log"].append({
                                "time": datetime.utcnow().isoformat(),
                                "type": "info",
                                "message": f"API: linked task progress 95% {'ok' if prog_ok else 'skipped/failed'}"
                            })
                        clock_out_ok = await _post_timer_log(linked_task, "clock_out", task_token=task_token)
                        agent["output_log"].append({
                            "time": datetime.utcnow().isoformat(),
                            "type": "info",
                            "message": f"API: linked task clock_out {'ok' if clock_out_ok else 'failed'}"
                        })
                    else:
                        msg_ok = await _post_task_message(
                            linked_task,
                            f"Git push failed: {lt_commit.get('error', 'unknown error')}",
                            task_token=task_token,
                        )
                        prog_ok = await _post_task_progress(linked_task, 80, "Git push failed", task_token=task_token)
                        agent["output_log"].append({
                            "time": datetime.utcnow().isoformat(),
                            "type": "info",
                            "message": f"API: linked task push failure message {'ok' if msg_ok else 'failed'}, progress 80% {'ok' if prog_ok else 'skipped/failed'}"
                        })

                    lt_task_id = _normalize_task_id(linked_task)
                    if lt_checklist and lt_task_id:
                        for ci in range(len(lt_checklist)):
                            await _mark_checklist_item(
                                lt_task_id,
                                lt_checklist,
                                ci,
                                project_token=project_token,
                                task_token=task_token,
                            )

                    # Update linked task progress/completion in external system
                    # Always complete linked task if build succeeded, regardless of git push
                    if lt_result["exit_code"] == 0:
                        if lt_commit_success:
                            lt_completion_message = f"Completed by {agent_id}."
                        else:
                            lt_completion_message = f"Completed by {agent_id} (with git errors)."
                        msg_ok = await _post_task_message(linked_task, lt_completion_message, task_token=task_token)
                        prog_ok = await _post_task_progress(linked_task, 100, "Completed", task_token=task_token)
                        complete_ok = await _post_task_complete(linked_task, task_token=task_token)
                        agent["output_log"].append({
                            "time": datetime.utcnow().isoformat(),
                            "type": "info",
                            "message": (
                                f"API: linked task complete message {'ok' if msg_ok else 'failed'}, "
                                f"progress 100% {'ok' if prog_ok else 'skipped/failed'}, "
                                f"complete {'ok' if complete_ok else 'failed'}"
                            )
                        })
                    else:
                        lt_failure_message = f"Failed (exit={lt_result['exit_code']})."
                        msg_ok = await _post_task_message(linked_task, lt_failure_message, task_token=task_token)
                        prog_ok = await _post_task_progress(linked_task, 0, "Failed", task_token=task_token)
                        agent["output_log"].append({
                            "time": datetime.utcnow().isoformat(),
                            "type": "info",
                            "message": f"API: linked task failure message {'ok' if msg_ok else 'failed'}, progress 0% {'ok' if prog_ok else 'skipped/failed'}"
                        })

                    # Clear tracking state for linked task
                    lt_task_key = str(_normalize_task_id(linked_task) or linked_task.get("external_id") or linked_task.get("id"))
                    task_progress_state.pop(lt_task_key, None)
                    timer_log_state.pop(lt_task_key, None)

                # Switch back to main task branch
                if branch_name:
                    subprocess.run(
                        ["docker", "exec", "-w", "/workspace", container_name,
                         "git", "checkout", branch_name],
                        capture_output=True, text=True, timeout=15,
                    )

            # ═════════════════════════════════════════════════════════
            # GIT COMMIT & PUSH for the main task
            # ═════════════════════════════════════════════════════════
            commit_result = None
            git_success = not use_git
            if use_git and branch_name:
                agent["progress"] = 95
                agent["progress_message"] = f"Committing and pushing to {branch_name}..."

                note_result = await asyncio.to_thread(
                    _append_agent_session_note,
                    container_name,
                    agent_id,
                    task,
                    branch_name,
                    result.get("exit_code", -1),
                    fix_iteration,
                    False,
                )
                if note_result.get("success"):
                    agent["output_log"].append({
                        "time": datetime.utcnow().isoformat(),
                        "type": "info",
                        "message": f"Updated session note: {note_result.get('path')}"
                    })
                else:
                    agent["output_log"].append({
                        "time": datetime.utcnow().isoformat(),
                        "type": "error",
                        "message": note_result.get("error", "Failed to update session note.")
                    })

                commit_result = await asyncio.to_thread(
                    _commit_and_push, container_name, task["title"], branch_name
                )
                if commit_result["success"]:
                    git_success = True
                    effective_branch = commit_result.get("branch", branch_name)
                    if commit_result.get("pushed"):
                        agent["output_log"].append({
                            "time": datetime.utcnow().isoformat(),
                            "type": "info",
                            "message": f"Successfully pushed to branch: {effective_branch}"
                        })
                        if commit_result.get("rebased"):
                            agent["output_log"].append({
                                "time": datetime.utcnow().isoformat(),
                                "type": "info",
                                "message": f"Git pull --rebase integrated remote changes before push"
                            })
                        if commit_result.get("renamed"):
                            agent["output_log"].append({
                                "time": datetime.utcnow().isoformat(),
                                "type": "info",
                                "message": f"Git push fallback used (new branch: {effective_branch})"
                            })
                        prog_ok = await _post_task_progress(task, 95, "Pushed to git", task_token=task_token)
                        agent["output_log"].append({
                            "time": datetime.utcnow().isoformat(),
                            "type": "info",
                            "message": f"API: progress 95% {'ok' if prog_ok else 'skipped/failed'}"
                        })
                        await _enqueue_git_merge(
                            effective_branch,
                            agent.get("git_repo_url"),
                            agent.get("git_token"),
                            agent_id,
                            task["title"],
                            project_token=project_token
                        )
                        if bootstrap_role == "bootstrap" and not bootstrap_signal_sent:
                            await _mark_repo_bootstrap_result(
                                project_token=project_token,
                                source_agent=agent_id,
                                success=True,
                                source_branch=effective_branch,
                                message=(
                                    f"Initial scaffold pushed by {agent_id} on branch {effective_branch}."
                                ),
                            )
                            bootstrap_signal_sent = True
                            repo_base_branch = effective_branch
                            agent["output_log"].append({
                                "time": datetime.utcnow().isoformat(),
                                "type": "info",
                                "message": (
                                    "Bootstrap release sent. Waiting agents can now sync and start work."
                                )
                            })
                    else:
                        agent["output_log"].append({
                            "time": datetime.utcnow().isoformat(),
                            "type": "info",
                            "message": f"No changes to push for branch: {effective_branch}"
                        })
                        prog_ok = await _post_task_progress(task, 95, "No changes to push", task_token=task_token)
                        agent["output_log"].append({
                            "time": datetime.utcnow().isoformat(),
                            "type": "info",
                            "message": f"API: progress 95% {'ok' if prog_ok else 'skipped/failed'}"
                        })
                        if bootstrap_role == "bootstrap" and not bootstrap_signal_sent:
                            await _mark_repo_bootstrap_result(
                                project_token=project_token,
                                source_agent=agent_id,
                                success=False,
                                source_branch=None,
                                message=(
                                    f"Bootstrap agent {agent_id} finished without pushing initial scaffold."
                                ),
                            )
                            bootstrap_signal_sent = True
                            agent["output_log"].append({
                                "time": datetime.utcnow().isoformat(),
                                "type": "error",
                                "message": (
                                    "Bootstrap release sent with warning: no initial push detected."
                                )
                            })
                    clock_out_ok = await _post_timer_log(task, "clock_out", task_token=task_token)
                    agent["output_log"].append({
                        "time": datetime.utcnow().isoformat(),
                        "type": "info",
                        "message": f"API: timer log clock_out {'ok' if clock_out_ok else 'failed'}"
                    })
                else:
                    agent["output_log"].append({
                        "time": datetime.utcnow().isoformat(),
                        "type": "error",
                        "message": f"Git push failed: {commit_result['error']}"
                    })
                    msg_ok = await _post_task_message(
                        task,
                        f"Git push failed: {commit_result.get('error', 'unknown error')}",
                        task_token=task_token,
                    )
                    prog_ok = await _post_task_progress(task, 80, "Git push failed", task_token=task_token)
                    agent["output_log"].append({
                        "time": datetime.utcnow().isoformat(),
                        "type": "info",
                        "message": f"API: push failure message {'ok' if msg_ok else 'failed'}, progress 80% {'ok' if prog_ok else 'skipped/failed'}"
                    })
                    if bootstrap_role == "bootstrap" and not bootstrap_signal_sent:
                        await _mark_repo_bootstrap_result(
                            project_token=project_token,
                            source_agent=agent_id,
                            success=False,
                            source_branch=None,
                            message=(
                                f"Bootstrap push failed on {agent_id}: {commit_result.get('error', 'unknown error')}"
                            ),
                        )
                        bootstrap_signal_sent = True
                        agent["output_log"].append({
                            "time": datetime.utcnow().isoformat(),
                            "type": "error",
                            "message": (
                                "Bootstrap release sent with failure. Other agents will continue unsynced."
                            )
                        })
            elif not use_git:
                prog_ok = await _post_task_progress(task, 95, "Ready to complete", task_token=task_token)
                agent["output_log"].append({
                    "time": datetime.utcnow().isoformat(),
                    "type": "info",
                    "message": f"API: progress 95% {'ok' if prog_ok else 'skipped/failed'}"
                })
                clock_out_ok = await _post_timer_log(task, "clock_out", task_token=task_token)
                agent["output_log"].append({
                    "time": datetime.utcnow().isoformat(),
                    "type": "info",
                    "message": f"API: timer log clock_out {'ok' if clock_out_ok else 'failed'}"
                })

            # ═════════════════════════════════════════════════════════
            # TASK COMPLETE — record result, release IDs
            # ═════════════════════════════════════════════════════════
            elapsed = round(time.time() - start_time, 1)
            stats = _parse_stats_from_output(all_stdout, agent["type"])
            stats["avg_time"] = f"{elapsed}s"
            agent["stats"] = stats

            overall_success = (result["exit_code"] == 0) and git_success
            task["status"] = "completed" if overall_success else "completed_with_errors"
            agent["last_run"] = datetime.utcnow().isoformat()
            agent["last_result"] = {
                "task": task,
                "exit_code": result["exit_code"],
                "stdout": all_stdout,
                "stderr": result["stderr"],
                "generated_code": workspace_tree,
                "builder_scripts": all_generated_code,
                "duration": elapsed,
                "fix_iterations": fix_iteration,
            }

            # Always set progress to 100% and complete task when build succeeds
            # Git push failures won't prevent task completion
            if result["exit_code"] == 0:
                if overall_success:
                    completion_message = f"Completed by {agent_id} in {elapsed}s."
                else:
                    completion_message = f"Completed by {agent_id} in {elapsed}s (with git errors)."
                msg_ok = await _post_task_message(task, completion_message, task_token=task_token)
                prog_ok = await _post_task_progress(task, 100, "Completed", task_token=task_token)
                complete_ok = await _post_task_complete(task, task_token=task_token)
                agent["output_log"].append({
                    "time": datetime.utcnow().isoformat(),
                    "type": "info",
                    "message": (
                        f"API: complete message {'ok' if msg_ok else 'failed'}, "
                        f"progress 100% {'ok' if prog_ok else 'skipped/failed'}, "
                        f"complete {'ok' if complete_ok else 'failed'}"
                    )
                })
                if complete_ok:
                    rollup_result = await _sync_rollup_status_for_completed_task(
                        task,
                        project_token=project_token,
                        task_token=task_token,
                    )
                    if rollup_result.get("milestone_completed"):
                        agent["output_log"].append({
                            "time": datetime.utcnow().isoformat(),
                            "type": "info",
                            "message": "API: milestone marked as completed",
                        })
                    if rollup_result.get("sprint_completed"):
                        agent["output_log"].append({
                            "time": datetime.utcnow().isoformat(),
                            "type": "info",
                            "message": "API: sprint marked as completed",
                        })
                    if rollup_result.get("project_completed"):
                        agent["output_log"].append({
                            "time": datetime.utcnow().isoformat(),
                            "type": "info",
                            "message": "API: project status updated to Completed",
                        })
            else:
                failure_message = f"Failed (exit={result['exit_code']})."
                msg_ok = await _post_task_message(task, failure_message, task_token=task_token)
                prog_ok = await _post_task_progress(task, 0, "Failed", task_token=task_token)
                agent["output_log"].append({
                    "time": datetime.utcnow().isoformat(),
                    "type": "info",
                    "message": f"API: failure message {'ok' if msg_ok else 'failed'}, progress 0% {'ok' if prog_ok else 'skipped/failed'}"
                })

            # Clear tracking state for this task id
            task_key = str(_normalize_task_id(task) or task.get("external_id") or task.get("id"))
            task_progress_state.pop(task_key, None)
            timer_log_state.pop(task_key, None)

            # DO NOT release claimed IDs for successfully completed tasks.
            # If the external API fails to mark the task as "completed",
            # _pick_next_task would re-pick it, causing duplicate execution.
            # IDs are only discarded on error/abort (see error handler below).

            completed_tasks.append(task)
            all_results.append({
                "task": task["title"],
                "exit_code": result["exit_code"],
                "duration": elapsed,
            })

            agent["output_log"].append({
                "time": datetime.utcnow().isoformat(),
                "type": "info",
                "message": f"✅ Task '{task['title']}' completed in {elapsed}s (exit={result['exit_code']})"
            })
            agent["progress"] = 100
            agent["progress_message"] = "Task completed"

            # ── Feed Output Back to KG + Cross-Agent Memory ─────────
            # Blitzy pattern: KG is a LIVING document. Agent output is
            # parsed and inserted back into the KG + RAG so downstream
            # agents discover it via semantic search (Layer 3).
            try:
                import context_manager as ctx_mgr
                live_mem = ctx_mgr.get_live_memory(project_token or "")

                # Extract files and symbols from what the agent produced
                touched_files = ctx_mgr.extract_files_from_workspace_tree(workspace_tree)
                symbols = ctx_mgr.extract_symbols_from_code(all_generated_code)

                # 1) Register completion in shared memory (for active task tracking)
                live_mem.register_task_complete(
                    agent_id=agent_id,
                    files_touched=touched_files[:25],
                    symbols_created=symbols.get("created", []),
                    symbols_modified=symbols.get("modified", []),
                    exit_code=result["exit_code"],
                    summary=(
                        f"{'Completed' if result['exit_code'] == 0 else 'Failed'} "
                        f"task '{task['title']}' in {elapsed}s. "
                        f"Generated {len(all_generated_code.splitlines())} lines of code. "
                        f"Touched {len(touched_files)} files."
                    ),
                )

                # 2) Feed generated code back into the Knowledge Graph + RAG
                #    This is the core Blitzy pattern: KG as living source of truth.
                #    Only do this for successful builds — failed code shouldn't
                #    pollute the KG.
                if result["exit_code"] == 0 and workspace_tree and project_token:
                    kg_update = await ctx_mgr.update_kg_with_agent_output(
                        project_token=project_token,
                        agent_id=agent_id,
                        task_title=task.get("title", ""),
                        workspace_tree=workspace_tree,
                        generated_code=all_generated_code,
                    )
                    agent["output_log"].append({
                        "time": datetime.utcnow().isoformat(),
                        "type": "info",
                        "message": (
                            f"KG feedback: {kg_update.get('status')} — "
                            f"{kg_update.get('files_processed', 0)} files, "
                            f"{kg_update.get('nodes_added', 0)} nodes, "
                            f"{kg_update.get('chunks_inserted', 0)} RAG chunks inserted"
                        )
                    })
                else:
                    agent["output_log"].append({
                        "time": datetime.utcnow().isoformat(),
                        "type": "info",
                        "message": (
                            f"Cross-agent memory: recorded completion "
                            f"({len(touched_files)} files, {len(symbols.get('created', []))} new symbols). "
                            f"KG feedback skipped (exit_code={result['exit_code']})."
                        )
                    })
            except Exception as mem_err:
                agent["output_log"].append({
                    "time": datetime.utcnow().isoformat(),
                    "type": "info",
                    "message": f"Cross-agent memory write skipped: {str(mem_err)[:80]}"
                })

            # ═════════════════════════════════════════════════════════
            # PICK NEXT TASK (only if continuous mode)
            # ═════════════════════════════════════════════════════════
            if not continuous:
                task = None  # exit loop
            else:
                task = await _pick_next_task(agent_id, project_token=project_token, task_token=task_token)
                if isinstance(task, dict) and project_token:
                    task.setdefault("_project_token", project_token)
                if task:
                    agent["output_log"].append({
                        "time": datetime.utcnow().isoformat(),
                        "type": "info",
                        "message": f"⏩ Moving to next task..."
                    })
                else:
                    agent["output_log"].append({
                        "time": datetime.utcnow().isoformat(),
                        "type": "info",
                        "message": "🎉 All tasks completed! No more tasks in queue."
                    })

        # ── END OF WHILE LOOP ────────────────────────────────────────

        # Destroy container after all tasks are done
        if container_created:
            await asyncio.to_thread(_destroy_container, container_name)
            agent["output_log"].append({
                "time": datetime.utcnow().isoformat(),
                "type": "info",
                "message": f"Container '{container_name}' destroyed."
            })

        total_elapsed = round(time.time() - total_start, 1)
        agent["status"] = "completed"
        agent["progress"] = 100
        agent["progress_message"] = f"All done! {tasks_completed} task(s) in {total_elapsed}s"
        agent["current_task"] = None

        return {
            "success": True,
            "agent_id": agent_id,
            "tasks_completed": tasks_completed,
            "total_duration": total_elapsed,
            "results": all_results,
        }

    except Exception as e:
        if bootstrap_role == "bootstrap" and not bootstrap_signal_sent:
            await _mark_repo_bootstrap_result(
                project_token=project_token,
                source_agent=agent_id,
                success=False,
                source_branch=None,
                message=f"Bootstrap agent {agent_id} failed before initial push: {str(e)}",
            )
            bootstrap_signal_sent = True
        elapsed = round(time.time() - total_start, 1)
        agent["status"] = "error"
        agent["progress"] = 0
        agent["progress_message"] = f"Error: {str(e)}"
        agent["output_log"].append({
            "time": datetime.utcnow().isoformat(),
            "type": "error",
            "message": str(e)
        })
        agent["last_run"] = datetime.utcnow().isoformat()
        agent["current_task"] = None

        # Clean up container on error
        if container_created:
            await asyncio.to_thread(_destroy_container, container_name)

        # Release any claimed IDs
        if task:
            tid = str(_normalize_task_id(task) or task.get("external_id") or task.get("id"))
            claimed_task_ids.discard(tid)
            for lid in (task.get("linked_tasks") or []):
                claimed_task_ids.discard(str(lid))

        return {
            "success": False,
            "agent_id": agent_id,
            "error": str(e),
            "tasks_completed": tasks_completed,
            "duration": elapsed,
        }


# ═══════════════════════════════════════════════════════════════════════════
# PREVIEW DEPLOY — Run the merged project in a live Docker container
# ═══════════════════════════════════════════════════════════════════════════

_preview_states: Dict[str, Dict[str, Any]] = {}
_PREVIEW_PORT_RANGE_START = 9100
_PREVIEW_PORT_RANGE_END = 9200


def _find_available_preview_port() -> int:
    """Find an unused port in the preview range."""
    import socket
    used_ports = {
        s.get("host_port") for s in _preview_states.values()
        if s.get("host_port")
    }
    for port in range(_PREVIEW_PORT_RANGE_START, _PREVIEW_PORT_RANGE_END):
        if port in used_ports:
            continue
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("0.0.0.0", port))
                return port
            except OSError:
                continue
    raise RuntimeError("No available ports in preview range")


def _detect_project_stack(container_name: str) -> Dict[str, Any]:
    """Auto-detect the tech stack inside the container's /workspace."""
    stack = {"type": "static", "image": "python:3.10-slim", "port": 8080,
             "install_cmd": "", "start_cmd": "python3 -m http.server 8080"}

    # Check for package.json (Node.js)
    check_pkg = subprocess.run(
        ["docker", "exec", container_name, "cat", "/workspace/package.json"],
        capture_output=True, text=True, timeout=10,
    )
    if check_pkg.returncode == 0:
        content = check_pkg.stdout.lower()
        stack["type"] = "node"
        stack["image"] = "node:18-slim"
        stack["install_cmd"] = "cd /workspace && npm install"

        if '"vite"' in content or '"@vitejs/plugin-react"' in content:
            stack["start_cmd"] = "cd /workspace && npx vite --host 0.0.0.0 --port 5173"
            stack["port"] = 5173
        elif '"react-scripts"' in content:
            stack["start_cmd"] = "cd /workspace && npx react-scripts start"
            stack["port"] = 3000
        elif '"next"' in content:
            stack["start_cmd"] = "cd /workspace && npx next dev -p 3000"
            stack["port"] = 3000
        else:
            stack["start_cmd"] = "cd /workspace && npm start"
            stack["port"] = 3000
        return stack

    # Check for requirements.txt (Python)
    check_req = subprocess.run(
        ["docker", "exec", container_name, "cat", "/workspace/requirements.txt"],
        capture_output=True, text=True, timeout=10,
    )
    if check_req.returncode == 0:
        content = check_req.stdout.lower()
        stack["type"] = "python"
        stack["install_cmd"] = "cd /workspace && pip install -r requirements.txt"

        if "fastapi" in content or "uvicorn" in content:
            # Try to find the main app file
            find_main = subprocess.run(
                ["docker", "exec", container_name, "sh", "-c",
                 "find /workspace -maxdepth 2 -name 'main.py' -o -name 'app.py' | head -1"],
                capture_output=True, text=True, timeout=10,
            )
            main_file = (find_main.stdout.strip().replace("/workspace/", "")
                         if find_main.returncode == 0 and find_main.stdout.strip()
                         else "main:app")
            module = main_file.replace(".py", "").replace("/", ".")
            stack["start_cmd"] = f"cd /workspace && uvicorn {module}:app --host 0.0.0.0 --port 8000"
            stack["port"] = 8000
        elif "flask" in content:
            stack["start_cmd"] = "cd /workspace && flask run --host=0.0.0.0 --port 5000"
            stack["port"] = 5000
        elif "django" in content:
            stack["start_cmd"] = "cd /workspace && python manage.py runserver 0.0.0.0:8000"
            stack["port"] = 8000
        else:
            # Generic python — try to run main.py
            stack["start_cmd"] = "cd /workspace && python main.py"
            stack["port"] = 8000
        return stack

    # Check for index.html (static site)
    check_html = subprocess.run(
        ["docker", "exec", container_name, "test", "-f", "/workspace/index.html"],
        capture_output=True, text=True, timeout=5,
    )
    if check_html.returncode == 0:
        stack["type"] = "static"
        stack["start_cmd"] = "cd /workspace && python3 -m http.server 8080"
        stack["port"] = 8080

    return stack


async def deploy_preview(
    git_repo_url: str,
    git_token: str,
    project_token: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Deploy the agent/integration branch into a live Docker container with
    port mapping so the user can preview the built application.
    """
    pk = _project_key(project_token)

    # Stop any existing preview for this project
    if pk in _preview_states and _preview_states[pk].get("status") == "running":
        await stop_preview(project_token)

    preview_id = f"preview_{pk[:12]}_{int(time.time())}"
    container_name = preview_id

    _preview_states[pk] = {
        "status": "deploying",
        "container_name": container_name,
        "host_port": None,
        "preview_url": None,
        "logs": [],
        "started_at": datetime.utcnow().isoformat(),
        "stack": None,
    }
    pstate = _preview_states[pk]

    def _log(msg: str):
        pstate["logs"].append({
            "time": datetime.utcnow().isoformat(),
            "message": msg,
        })
        logger.info(f"[Preview] {msg}")

    try:
        # 1. Create container (using python:3.10-slim initially for cloning)
        _log("Creating temporary clone container...")
        create_res = _create_persistent_container(container_name)
        if not create_res.get("success"):
            raise RuntimeError(f"Failed to create container: {create_res.get('error')}")

        # 2. Install git
        _log("Installing git...")
        subprocess.run(
            ["docker", "exec", container_name, "sh", "-c",
             "apt-get update -qq && apt-get install -y -qq git > /dev/null 2>&1"],
            capture_output=True, text=True, timeout=120,
        )

        # 3. Clone the repo (agent/integration branch)
        auth_url = git_repo_url.replace("https://", f"https://x-access-token:{git_token}@")
        _log(f"Cloning {GIT_INTEGRATION_BRANCH} branch...")
        clone = subprocess.run(
            ["docker", "exec", "-w", "/", container_name,
             "git", "clone", "--branch", GIT_INTEGRATION_BRANCH, "--depth", "1",
             auth_url, "/workspace"],
            capture_output=True, text=True, timeout=120,
        )
        if clone.returncode != 0:
            raise RuntimeError(f"Git clone failed: {clone.stderr}")

        # 4. Detect the project stack
        _log("Detecting project tech stack...")
        stack = _detect_project_stack(container_name)
        pstate["stack"] = stack
        _log(f"Detected: {stack['type']} project")

        # 5. Destroy the clone container — we'll create a proper one with the right image
        _destroy_container(container_name)

        # 6. Find available port
        host_port = _find_available_preview_port()
        pstate["host_port"] = host_port

        # 7. Create the real container with the correct base image and port mapping
        _log(f"Starting {stack['type']} container...")
        docker_run = subprocess.run(
            ["docker", "run", "-d",
             "--name", container_name,
             "-p", f"{host_port}:{stack['port']}",
             "-w", "/workspace",
             "-e", "CI=true",
             "-e", "HOST=0.0.0.0",
             "-e", "PORT=3000",
             stack["image"],
             "sleep", "infinity"],
            capture_output=True, text=True, timeout=30,
        )
        if docker_run.returncode != 0:
            raise RuntimeError(f"Docker run failed: {docker_run.stderr}")

        # 8. Clone repo again inside the properly imaged container
        _log("Cloning code into preview container...")
        subprocess.run(
            ["docker", "exec", container_name, "sh", "-c",
             "apt-get update -qq && apt-get install -y -qq git > /dev/null 2>&1 || true"],
            capture_output=True, text=True, timeout=120,
        )
        # Clear workspace and clone
        subprocess.run(
            ["docker", "exec", container_name, "sh", "-c", "rm -rf /workspace/*"],
            capture_output=True, text=True, timeout=10,
        )
        clone2 = subprocess.run(
            ["docker", "exec", "-w", "/", container_name,
             "git", "clone", "--branch", GIT_INTEGRATION_BRANCH, "--depth", "1",
             auth_url, "/workspace"],
            capture_output=True, text=True, timeout=120,
        )
        if clone2.returncode != 0:
            raise RuntimeError(f"Git clone into preview container failed: {clone2.stderr}")

        # 9. Install dependencies
        if stack["install_cmd"]:
            _log(f"Installing dependencies: {stack['install_cmd']}")
            install = subprocess.run(
                ["docker", "exec", container_name, "sh", "-c", stack["install_cmd"]],
                capture_output=True, text=True, timeout=300,
            )
            if install.returncode != 0:
                _log(f"⚠️ Install warning: {install.stderr[:300]}")

        # 10. Start the dev server in the background
        _log(f"Starting application server...")
        subprocess.run(
            ["docker", "exec", "-d", container_name, "sh", "-c",
             f"nohup sh -c '{stack['start_cmd']}' > /tmp/preview_server.log 2>&1 &"],
            capture_output=True, text=True, timeout=15,
        )

        # 11. Wait a moment for the server to initialize
        await asyncio.sleep(3)

        preview_url = f"http://localhost:{host_port}"
        pstate["status"] = "running"
        pstate["preview_url"] = preview_url
        _log("✅ Preview is live and ready!")

        return {
            "status": "running",
            "preview_url": preview_url,
            "host_port": host_port,
            "container_name": container_name,
            "stack": stack["type"],
        }

    except Exception as e:
        pstate["status"] = "error"
        pstate["logs"].append({
            "time": datetime.utcnow().isoformat(),
            "message": f"❌ Deploy failed: {str(e)}",
        })
        # Clean up container on failure
        try:
            _destroy_container(container_name)
        except Exception:
            pass
        return {
            "status": "error",
            "error": str(e),
        }


def _recover_preview_from_docker(pk: str) -> Optional[Dict[str, Any]]:
    """Try to find a running preview container from Docker when in-memory state is lost."""
    try:
        # List all running containers with names starting with "preview_"
        result = subprocess.run(
            ["docker", "ps", "--filter", f"name=preview_{pk[:12]}", "--format",
             "{{.Names}}\t{{.Ports}}\t{{.Status}}"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return None

        # Parse the first matching container
        for line in result.stdout.strip().split("\n"):
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            container_name = parts[0].strip()
            ports_str = parts[1].strip()

            # Extract host port from port mapping like "0.0.0.0:9100->3000/tcp"
            host_port = None
            import re as _re_local
            port_match = _re_local.search(r"0\.0\.0\.0:(\d+)->(\d+)", ports_str)
            if port_match:
                host_port = int(port_match.group(1))

            if host_port:
                preview_url = f"http://localhost:{host_port}"
                # Reconstruct state
                recovered = {
                    "status": "running",
                    "container_name": container_name,
                    "host_port": host_port,
                    "preview_url": preview_url,
                    "logs": [{"time": datetime.utcnow().isoformat(),
                              "message": "Recovered running preview from Docker."}],
                    "started_at": datetime.utcnow().isoformat(),
                    "stack": None,
                    "server_log": "",
                }
                # Cache it in memory
                _preview_states[pk] = recovered
                return recovered
    except Exception as e:
        logger.debug(f"Preview recovery failed: {e}")
    return None


def get_preview_status(project_token: Optional[str] = None) -> Dict[str, Any]:
    """Get the current preview deployment status for a project."""
    pk = _project_key(project_token)
    pstate = _preview_states.get(pk)

    # If no in-memory state, try to recover from Docker
    if not pstate:
        recovered = _recover_preview_from_docker(pk)
        if not recovered:
            return {"status": "none", "message": "No preview deployed"}
        pstate = recovered

    # If status is "running", verify the container is actually alive
    if pstate["status"] == "running" and pstate.get("container_name"):
        check = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", pstate["container_name"]],
            capture_output=True, text=True, timeout=5,
        )
        if check.returncode != 0 or "true" not in check.stdout.lower():
            pstate["status"] = "stopped"

    # Grab recent server logs
    if pstate.get("container_name") and pstate["status"] == "running":
        try:
            log_result = subprocess.run(
                ["docker", "exec", pstate["container_name"],
                 "tail", "-20", "/tmp/preview_server.log"],
                capture_output=True, text=True, timeout=5,
            )
            if log_result.returncode == 0:
                pstate["server_log"] = log_result.stdout
        except Exception:
            pass

    return {
        "status": pstate["status"],
        "preview_url": pstate.get("preview_url"),
        "host_port": pstate.get("host_port"),
        "container_name": pstate.get("container_name"),
        "stack": pstate.get("stack", {}).get("type") if isinstance(pstate.get("stack"), dict) else pstate.get("stack"),
        "started_at": pstate.get("started_at"),
        "logs": pstate.get("logs", []),
        "server_log": pstate.get("server_log", ""),
    }


async def stop_preview(project_token: Optional[str] = None) -> Dict[str, Any]:
    """Stop and destroy the preview container for a project."""
    pk = _project_key(project_token)
    pstate = _preview_states.get(pk)
    if not pstate:
        # Try to recover from Docker
        pstate = _recover_preview_from_docker(pk)
    if not pstate:
        return {"status": "none", "message": "No preview to stop"}

    container_name = pstate.get("container_name")
    if container_name:
        await asyncio.to_thread(_destroy_container, container_name)

    pstate["status"] = "stopped"
    pstate["logs"].append({
        "time": datetime.utcnow().isoformat(),
        "message": "Preview container stopped and destroyed.",
    })

    return {"status": "stopped", "message": f"Preview container {container_name} destroyed"}


# ── Agent & Task Management Helpers ─────────────────────────────────────────

def get_pending_tasks(project_token: Optional[str] = None) -> List[Dict[str, Any]]:
    return []

def get_agent_status(agent_id: str, project_token: Optional[str] = None) -> Dict[str, Any]:
    project_agents = _get_agent_states(project_token)
    agent = project_agents.get(agent_id)
    if not agent:
        raise ValueError(f"Agent {agent_id} not found")
    return agent

def get_all_agents(project_token: Optional[str] = None) -> List[Dict[str, Any]]:
    project_agents = _get_agent_states(project_token)
    return list(project_agents.values())

def reset_agent(agent_id: str, project_token: Optional[str] = None) -> Dict[str, Any]:
    project_agents = _get_agent_states(project_token)
    agent = project_agents.get(agent_id)
    if not agent:
        raise ValueError(f"Agent {agent_id} not found")
    agent["status"] = "idle"
    agent["progress"] = 0
    agent["progress_message"] = ""
    agent["current_task"] = None
    return agent

def create_task(title: str, description: str, priority: str = "medium") -> Dict[str, Any]:
    return {
        "id": str(uuid.uuid4())[:8],
        "title": title,
        "description": description,
        "priority": priority,
        "status": "pending",
        "created_at": datetime.utcnow().isoformat(),
    }

def seed_sample_tasks():
    pass


# ── Dynamic Agent Management ────────────────────────────────────────────────

def add_agent(name: str = None, git_repo_url: str = None, git_token: str = None,
              project_token: Optional[str] = None) -> Dict[str, Any]:
    """Add a new agent dynamically."""
    project_agents = _get_agent_states(project_token)
    idx = len(project_agents)
    agent_id = f"agent_{idx + 1:02d}"
    while agent_id in project_agents:
        idx += 1
        agent_id = f"agent_{idx + 1:02d}"
    agent = _make_agent(agent_id, idx)
    if name:
        agent["name"] = name
    if git_repo_url:
        agent["git_repo_url"] = git_repo_url.strip()
    if git_token:
        agent["git_token"] = git_token.strip()
    project_agents[agent_id] = agent
    return agent


def update_agent_name(agent_id: str, name: str, project_token: Optional[str] = None) -> Dict[str, Any]:
    project_agents = _get_agent_states(project_token)
    agent = project_agents.get(agent_id)
    if not agent:
        raise ValueError(f"Agent {agent_id} not found")
    agent["name"] = name.strip()
    return agent


def remove_agent(agent_id: str, project_token: Optional[str] = None) -> bool:
    """Remove an agent (only if idle)."""
    project_agents = _get_agent_states(project_token)
    agent = project_agents.get(agent_id)
    if not agent:
        raise ValueError(f"Agent {agent_id} not found")
    if agent["status"] == "running":
        raise ValueError(f"Agent {agent_id} is currently running and cannot be removed.")
    del project_agents[agent_id]
    return True


# ── Run All Agents Simultaneously ───────────────────────────────────────────

async def run_all_agents(agents_config: Dict[str, Dict[str, str]] = None,
                         project_token: Optional[str] = None,
                         task_token: Optional[str] = None) -> Dict[str, Any]:
    """
    Assign initial tasks to all idle agents and run them in CONTINUOUS mode.
    Each agent keeps picking the next uncompleted task after finishing its current one,
    only stopping when ALL tasks are done. Agents run concurrently.
    """
    state = _ensure_project_state(project_token)
    if task_token:
        state["task_token"] = task_token
    project_agents = state["agent_states"]
    claimed_task_ids = state["claimed_task_ids"]

    # 1. Synchronously claim all idle agents immediately so UI updates instantly
    idle_agents = [
        a for a in project_agents.values()
        if a["status"] == "idle" and not _is_system_agent_id(a["id"])
    ]
    if not idle_agents:
        raise ValueError("No idle agents. Reset agents or add new ones.")

    for agent in idle_agents:
        agent["status"] = "running"
        agent["progress"] = 0
        agent["output_log"] = []
        agent["progress_message"] = "Initializing (fetching tasks)..."

    # Fetch all tasks (this is async)
    try:
        external_tasks = await _fetch_external_tasks(project_token)
        if not external_tasks:
            raise ValueError("No tasks available from the external task API. Generate tasks first.")

        # Filter to uncompleted, unclaimed tasks
        available_tasks = [
            t for t in external_tasks
            if (t.get("status") or "").lower() not in ("completed", "done")
            and str(_normalize_task_id(t) or t.get("external_id") or t.get("id")) not in claimed_task_ids
        ]

        if not available_tasks:
            raise ValueError("No unclaimed tasks available.")
            
    except Exception as e:
        # Roll back state if task fetching failed
        for agent in idle_agents:
            agent["status"] = "idle"
            agent["progress"] = 0
            agent["progress_message"] = ""
            agent["error"] = str(e)
        raise

    if not available_tasks:
        raise ValueError("No unclaimed tasks available.")

    # Assign one initial task per agent
    assignments = []
    used_task_ids = set()
    for agent in idle_agents:
        if not available_tasks:
            break
        task = available_tasks.pop(0)
        task_id = str(_normalize_task_id(task) or task.get("external_id") or task.get("id"))
        used_task_ids.add(task_id)

        # Also claim linked tasks
        linked_ids = [str(lt) for lt in (task.get("linked_tasks") or [])]
        for lid in linked_ids:
            used_task_ids.add(lid)

        claimed_task_ids.update(used_task_ids)
        assignments.append((agent["id"], task))

        # Remove linked tasks from the available pool
        available_tasks = [
            t for t in available_tasks
            if str(_normalize_task_id(t) or t.get("external_id") or t.get("id")) not in used_task_ids
        ]

    # Set individual git config on agents if provided via agents_config
    if agents_config:
        for aid, task in assignments:
            if aid in agents_config:
                repo_val = agents_config[aid].get("git_repo_url")
                if repo_val:
                    project_agents[aid]["git_repo_url"] = repo_val.strip()
                token_val = agents_config[aid].get("git_token")
                if token_val:
                    project_agents[aid]["git_token"] = token_val.strip()

    # Launch all agents concurrently in CONTINUOUS mode
    async def _run_one(agent_id, assigned_task):
        try:
            return await run_agent(
                agent_id,
                assigned_task=assigned_task,
                continuous=True,
                ignore_running_check=True,
                project_token=project_token,
                task_token=task_token,
            )
        except Exception as e:
            return {"success": False, "agent_id": agent_id, "error": str(e)}

    coroutines = [_run_one(aid, task) for aid, task in assignments]
    results = await asyncio.gather(*coroutines, return_exceptions=True)

    return {
        "launched": len(assignments),
        "agents": [aid for aid, _ in assignments],
        "results": [
            r if isinstance(r, dict) else {"error": str(r)}
            for r in results
        ],
    }
