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
GIT_INTEGRATION_BRANCH = "agent/integration"
DEFAULT_PROJECT_TOKEN = "__default__"

_project_states: Dict[str, Dict[str, Any]] = {}

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
        }
        _project_states[key] = state
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
    return {
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

def get_default_agents() -> List[Dict[str, Any]]:
    return [
        _make_agent("agent_01", 0),
        _make_agent("agent_02", 1),
        _make_agent("agent_03", 2),
    ]

def initialize_agents_from_records(records: List[Any], project_token: Optional[str] = None) -> None:
    """
    Replace in-memory agent states with DB-backed agent records.
    """
    state = _ensure_project_state(project_token)
    state["claimed_task_ids"].clear()
    state["task_progress_state"].clear()
    state["timer_log_state"].clear()
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
    if state["agent_states"]:
        return
    initialize_agents_from_records(records, project_token=project_token)

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

async def _call_ai_for_code(task_description: str, agent_type: str) -> tuple[str, str]:
    """Call AI model to generate project-building Python code."""
    url = settings.ai_api_url
    key = settings.ai_api_key
    model_name = settings.ai_model

    if not key or key == "your-api-key-here":
        raise ValueError("AI API key not configured")

    system_prompt = AGENT_SYSTEM_PROMPTS.get(agent_type, AGENT_SYSTEM_PROMPTS["validator"])

    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Task to implement:\n\n{task_description}"},
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


async def _call_ai_for_fix(task_description: str, agent_type: str, issues: list, previous_output: str, iteration: int, builder_crashed: bool = False) -> tuple[str, str]:
    """
    Call AI to generate a fix script. If builder_crashed=True, the builder script
    itself had a SyntaxError and /workspace/ is empty, so we regenerate from scratch.
    """
    url = settings.ai_api_url
    key = settings.ai_api_key
    model_name = settings.ai_model

    if not key or key == "your-api-key-here":
        raise ValueError("AI API key not configured")

    system_prompt = AGENT_SYSTEM_PROMPTS.get(agent_type, AGENT_SYSTEM_PROMPTS["validator"])

    issues_text = "\n".join(f"  - {issue}" for issue in issues)

    if builder_crashed:
        fix_prompt = f"""YOUR PREVIOUS BUILDER SCRIPT CRASHED before creating any files.
The error was:
{issues_text}

ORIGINAL TASK:
{task_description}

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
        _log_git_agent(
            f"Install failed: {install_res.get('cmd')}\n{install_res.get('stderr')}",
            "error",
            project_token=project_token
        )
        return False

    for cmd in test_cmds:
        _log_git_agent(f"Running tests: {cmd}", project_token=project_token)
        test_res = await _run_commands_in_container(container_name, [cmd])
        if test_res.get("exit_code", 0) == 0:
            continue

        # Auto-fix loop
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
                return False

            # Re-run test command
            test_res = await _run_commands_in_container(container_name, [cmd])
            if test_res.get("exit_code", 0) == 0:
                _commit_if_dirty(container_name, f"Auto-fix after tests ({branch})")
                break
        else:
            _log_git_agent(f"Tests still failing after fixes: {cmd}", "error", project_token=project_token)
            return False

    return True


async def _enqueue_git_merge(branch: str, repo_url: Optional[str], token: Optional[str],
                             source_agent: str, task_title: str,
                             project_token: Optional[str] = None) -> None:
    if not branch or not repo_url:
        return
    state = _ensure_project_state(project_token)
    state["git_merge_queue"].append({
        "branch": branch,
        "repo_url": repo_url,
        "token": token or "",
        "source_agent": source_agent,
        "task_title": task_title,
        "project_token": project_token,
    })
    _log_git_agent(
        f"Queued merge: {branch} (from {source_agent}, task '{task_title}')",
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
        while state["git_merge_queue"]:
            item = state["git_merge_queue"].pop(0)
            await _process_git_merge_item(item)
    finally:
        state["git_merge_running"] = False
        project_agents = _get_agent_states(project_token)
        git_agent = project_agents.get(GIT_MANAGER_AGENT_ID)
        if git_agent:
            git_agent["status"] = "idle"
            git_agent["progress"] = 100
            git_agent["progress_message"] = "Git manager idle"


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
    if not repo_url or not branch:
        _log_git_agent("Git manager skipped merge (missing repo/branch)", "error", project_token=project_token)
        return

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

        # Fetch branch and checkout integration branch
        subprocess.run(
            ["docker", "exec", "-w", "/workspace", container_name,
             "git", "fetch", "origin", branch],
            capture_output=True, text=True, timeout=60,
        )
        default_branch = _get_default_branch(container_name)
        subprocess.run(
            ["docker", "exec", "-w", "/workspace", container_name,
             "git", "checkout", "-B", GIT_INTEGRATION_BRANCH, f"origin/{default_branch}"],
            capture_output=True, text=True, timeout=30,
        )

        if git_agent:
            git_agent["progress"] = 60
            git_agent["progress_message"] = f"Merging {branch} -> {GIT_INTEGRATION_BRANCH}"

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
                _log_git_agent(f"Merge failed for {branch}: {merge.stderr}", "error", project_token=project_token)
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
            if commit_union.returncode != 0:
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

        tests_ok = await _run_git_manager_tests_with_ai(container_name, branch, project_token=project_token)
        if not tests_ok:
            _log_git_agent(f"Tests failed after merge for {branch}. Not pushing.", "error", project_token=project_token)
            return

        push = subprocess.run(
            ["docker", "exec", "-w", "/workspace", container_name,
             "git", "push", "-u", "origin", GIT_INTEGRATION_BRANCH],
            capture_output=True, text=True, timeout=60,
        )
        if push.returncode != 0:
            err = push.stderr or push.stdout
            if "non-fast-forward" in err or "rejected" in err:
                _log_git_agent(
                    f"Non-fast-forward detected for {GIT_INTEGRATION_BRANCH}, pulling remote changes...",
                    project_token=project_token
                )
                pull = subprocess.run(
                    ["docker", "exec", "-w", "/workspace", container_name,
                     "git", "pull", "--rebase", "origin", GIT_INTEGRATION_BRANCH],
                    capture_output=True, text=True, timeout=60,
                )
                if pull.returncode == 0:
                    push_retry = subprocess.run(
                        ["docker", "exec", "-w", "/workspace", container_name,
                         "git", "push", "-u", "origin", GIT_INTEGRATION_BRANCH],
                        capture_output=True, text=True, timeout=60,
                    )
                    if push_retry.returncode == 0:
                        _log_git_agent(
                            f"Merged {branch} into {GIT_INTEGRATION_BRANCH} and pushed (after rebase).",
                            project_token=project_token
                        )
                        if git_agent:
                            git_agent["progress"] = 100
                            git_agent["progress_message"] = f"Merged {branch}"
                        return
                _log_git_agent(
                    f"Rebase failed for {GIT_INTEGRATION_BRANCH}, trying force push...",
                    "warning",
                    project_token=project_token
                )
                push_force = subprocess.run(
                    ["docker", "exec", "-w", "/workspace", container_name,
                     "git", "push", "-f", "origin", GIT_INTEGRATION_BRANCH],
                    capture_output=True, text=True, timeout=60,
                )
                if push_force.returncode == 0:
                    _log_git_agent(
                        f"Merged {branch} into {GIT_INTEGRATION_BRANCH} (force pushed).",
                        project_token=project_token
                    )
                    if git_agent:
                        git_agent["progress"] = 100
                        git_agent["progress_message"] = f"Merged {branch}"
                    return
            _log_git_agent(
                f"Push failed for {GIT_INTEGRATION_BRANCH}: {push.stderr}",
                "error",
                project_token=project_token
            )
            return

        _log_git_agent(
            f"Merged {branch} into {GIT_INTEGRATION_BRANCH} and pushed.",
            project_token=project_token
        )
        if git_agent:
            git_agent["progress"] = 100
            git_agent["progress_message"] = f"Merged {branch}"
    finally:
        await asyncio.to_thread(_destroy_container, container_name)


def _setup_git_in_container(container_name: str, repo_url: str, token: str, branch_name: str) -> Dict[str, Any]:
    """Install git, clone repo into /workspace/, create and checkout a new branch."""
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

        # 4. Create and checkout a new branch
        checkout = subprocess.run(
            ["docker", "exec", "-w", "/workspace", container_name,
             "git", "checkout", "-B", branch_name],
            capture_output=True, text=True, timeout=15,
        )
        if checkout.returncode != 0:
            return {"success": False, "error": f"Branch creation failed: {checkout.stderr}"}

        return {"success": True, "branch": branch_name}

    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Git setup timed out"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _commit_and_push(container_name: str, task_title: str, branch_name: str) -> Dict[str, Any]:
    """Stage all changes, commit with task title, and push to the remote branch."""
    try:
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

                # Strategy 2: Fallback - push to a new branch to avoid collisions
                suffix = uuid.uuid4().hex[:6]
                new_branch = f"{branch_name}-{suffix}"
                subprocess.run(
                    ["docker", "exec", "-w", "/workspace", container_name,
                     "git", "checkout", "-B", new_branch],
                    capture_output=True, text=True, timeout=15,
                )
                push2 = subprocess.run(
                    ["docker", "exec", "-w", "/workspace", container_name,
                     "git", "push", "-u", "origin", new_branch],
                    capture_output=True, text=True, timeout=60,
                )
                if push2.returncode == 0:
                    return {"success": True, "pushed": True, "branch": new_branch, "renamed": True}
                return {"success": False, "error": f"git push failed: {push2.stderr or push2.stdout}"}
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
        output_parts.append("PROJECT STRUCTURE (created in Docker container)")
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
                "_project_token": project_token,
            })
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
    from task_service import task_service
    task_id = _normalize_task_id(task)
    if not task_id:
        return False
    resolved_project = project_token or (task.get("_project_token") if isinstance(task, dict) else None)
    try:
        await task_service.post_task_message({
            "task_id": task_id,
            "message": message
        }, task_token=task_token or get_project_task_token(resolved_project))
        return True
    except Exception as e:
        print(f"[agent_service] Failed to post message for task {task_id}: {e}")
        return False


async def _post_task_progress(task: Dict[str, Any], progress: int, additional_info: str = None,
                              project_token: Optional[str] = None, task_token: Optional[str] = None) -> bool:
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
    if not state["timer_log_state"].get(task_key, False):
        print(
            f"[agent_service] Skipping progress for task {task_id}: "
            "no successful clock_in recorded"
        )
        return False
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
        print(f"[agent_service] Failed to update progress for task {task_id}: {e}")
        return False


async def _post_task_complete(task: Dict[str, Any], project_token: Optional[str] = None, task_token: Optional[str] = None) -> bool:
    from task_service import task_service
    task_id = _normalize_task_id(task)
    if not task_id:
        return False
    resolved_project = project_token or (task.get("_project_token") if isinstance(task, dict) else None)
    try:
        await task_service.complete_task({
            "task_id": task_id
        }, task_token=task_token or get_project_task_token(resolved_project))
        return True
    except Exception as e:
        print(f"[agent_service] Failed to complete task {task_id}: {e}")
        return False


async def _opt_in_task(task: Dict[str, Any], username: str,
                       project_token: Optional[str] = None, task_token: Optional[str] = None) -> bool:
    from task_service import task_service
    task_id = _normalize_task_id(task)
    if not task_id:
        return False
    resolved_project = project_token or (task.get("_project_token") if isinstance(task, dict) else None)
    try:
        await task_service.opt_in_task({
            "task_id": task_id,
            "username": username
        }, task_token=task_token or get_project_task_token(resolved_project))
        return True
    except Exception as e:
        print(f"[agent_service] Failed to opt in to task {task_id}: {e}")
        return False


async def _post_timer_log(task: Dict[str, Any], action: str, project_token: Optional[str] = None, task_token: Optional[str] = None) -> bool:
    from task_service import task_service
    task_id = _normalize_task_id(task)
    if not task_id:
        return False
    resolved_project = project_token or (task.get("_project_token") if isinstance(task, dict) else None)
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
        print(f"[agent_service] Failed to post timer log for task {task_id}: {e}")
        if action == "clock_in":
            _ensure_project_state(resolved_project)["timer_log_state"][str(task_id)] = False
        return False


# ── Main Agent Execution ────────────────────────────────────────────────────

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
    Main function to run an agent.
    When continuous=True, the agent keeps picking new tasks after completing
    the current one, only stopping when NO uncompleted tasks remain.

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
    total_start = time.time()
    tasks_completed = 0
    all_results = []

    container_name = f"{agent_id}_{uuid.uuid4().hex[:8]}"
    container_created = False

    try:
        # ── CONTINUOUS TASK LOOP ─────────────────────────────────────
        while task is not None:
            tasks_completed += 1
            task["status"] = "in_progress"
            task["assigned_agent"] = agent_id
            task["started_at"] = datetime.utcnow().isoformat()
            
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

            # ── Create task-specific git branch (for 2nd+ tasks) ─────
            branch_name = None
            if use_git:
                branch_name = _branch_name_for_task(task)
                if tasks_completed > 1:
                    # Switch back to main and create new branch
                    subprocess.run(
                        ["docker", "exec", "-w", "/workspace", container_name,
                         "git", "checkout", "main"],
                        capture_output=True, text=True, timeout=15,
                    )
                    subprocess.run(
                        ["docker", "exec", "-w", "/workspace", container_name,
                         "git", "checkout", "-B", branch_name],
                        capture_output=True, text=True, timeout=15,
                    )
                    agent["output_log"].append({
                        "time": datetime.utcnow().isoformat(),
                        "type": "info",
                        "message": f"Created branch: {branch_name}"
                    })

            # ── AI Code Generation ───────────────────────────────────
            agent["progress"] = 20
            agent["progress_message"] = "AI is generating project code..."
            agent["output_log"].append({
                "time": datetime.utcnow().isoformat(),
                "type": "info",
                "message": "Calling AI model to generate project code..."
            })

            generated_code, thought = await _call_ai_for_code(task["description"], agent["type"])
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
            # SELF-HEALING LOOP
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
            agent["progress"] = 90
            agent["progress_message"] = "Capturing project workspace..."
            workspace_tree = await asyncio.to_thread(_capture_workspace_tree, container_name)
            agent["output_log"].append({
                "time": datetime.utcnow().isoformat(),
                "type": "info",
                "message": f"Captured {workspace_tree.count('FILE:')} files from /workspace/"
            })

            # ═════════════════════════════════════════════════════════
            # MARK CHECKLIST ITEMS COMPLETE
            # ═════════════════════════════════════════════════════════
            normalized_task_id = _normalize_task_id(task)
            if checklist and normalized_task_id:
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
                         "git", "checkout", "main"],
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

                    lt_code, thought = await _call_ai_for_code(linked_task.get("description", lt_title), agent["type"])
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

            # Release claimed IDs for this task
            tid = str(_normalize_task_id(task) or task.get("external_id") or task.get("id"))
            claimed_task_ids.discard(tid)
            for lid in linked_task_ids:
                claimed_task_ids.discard(lid)

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
    idle_agents = [a for a in project_agents.values() if a["status"] == "idle" and a["id"] != "agent_03"]
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
