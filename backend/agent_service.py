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

def _clean_ai_code_response(content: str) -> str:
    """
    Robustly extract pure Python code from an AI model response.
    Handles: <think> blocks, markdown fences, narrative preamble,
    and Unicode curly quotes that cause SyntaxErrors.
    """
    content = content.strip()

    # 1. Strip <think>...</think> blocks
    content = _re.sub(r'<think>.*?</think>', '', content, flags=_re.DOTALL).strip()
    content = _re.sub(r'<think>.*', '', content, flags=_re.DOTALL).strip()

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
    if first_code_line > 0:
        preamble = '\n'.join(lines[:first_code_line]).strip()
        if not preamble.startswith('#'):
            content = '\n'.join(lines[first_code_line:])

    # 4. Replace Unicode with ASCII
    content = content.replace('\u2018', "'").replace('\u2019', "'")
    content = content.replace('\u201c', '"').replace('\u201d', '"')
    content = content.replace('\u2013', '-').replace('\u2014', '--')
    content = content.replace('\u2026', '...')
    content = content.replace('\u2192', '->').replace('\u2190', '<-')

    return content.strip()


# ── In-memory state stores ──────────────────────────────────────────────────

agent_states: Dict[str, Dict[str, Any]] = {
    "agent_01": {
        "id": "agent_01",
        "name": "Requirements Validator",
        "type": "validator",
        "status": "idle",
        "current_task": None,
        "progress": 0,
        "progress_message": "",
        "last_run": None,
        "last_result": None,
        "output_log": [],
        "stats": {"checks": 0, "coverage": 0, "avg_time": "0m"},
        "git_repo_url": None,
        "git_token": None,
    },
    "agent_02": {
        "id": "agent_02",
        "name": "Risk Assessment",
        "type": "risk",
        "status": "idle",
        "current_task": None,
        "progress": 0,
        "progress_message": "",
        "last_run": None,
        "last_result": None,
        "output_log": [],
        "stats": {"risks": 0, "critical": 0, "avg_time": "0m"},
        "git_repo_url": None,
        "git_token": None,
    },
    "agent_03": {
        "id": "agent_03",
        "name": "Resource Estimation",
        "type": "estimator",
        "status": "idle",
        "current_task": None,
        "progress": 0,
        "progress_message": "",
        "last_run": None,
        "last_result": None,
        "output_log": [],
        "stats": {"sprints": 0, "resources": 0, "avg_time": "0m"},
        "git_repo_url": None,
        "git_token": None,
    },
}

completed_tasks: List[Dict[str, Any]] = []


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

async def _call_ai_for_code(task_description: str, agent_type: str) -> str:
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


async def _call_ai_for_fix(task_description: str, agent_type: str, issues: list, previous_output: str, iteration: int, builder_crashed: bool = False) -> str:
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


def _build_git_auth_url(repo_url: str, token: str) -> str:
    """Insert token into HTTPS git URL for authentication."""
    repo_url = repo_url.strip()
    if not token:
        return repo_url
    if repo_url.startswith("https://"):
        return repo_url.replace("https://", f"https://{token.strip()}@", 1)
    return repo_url


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
             "git", "checkout", "-b", branch_name],
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
            return {"success": False, "error": f"git push failed: {push.stderr}"}

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

async def _fetch_external_tasks() -> List[Dict[str, Any]]:
    """Fetch tasks from the external task management API."""
    from task_service import task_service
    try:
        data = await task_service.get_tasks()
        if isinstance(data, list):
            tasks = data
        elif isinstance(data, dict) and "results" in data:
            tasks = data["results"]
        else:
            tasks = []

        normalized = []
        for t in tasks:
            normalized.append({
                "id": str(t.get("id", uuid.uuid4().hex[:8])),
                "title": t.get("taskName") or t.get("title") or "Untitled Task",
                "description": t.get("description") or t.get("taskName") or "",
                "priority": (t.get("priority") or "medium").lower(),
                "status": t.get("taskStatus") or t.get("status") or "pending",
                "task_type": t.get("task_type", "TASK"),
                "created_at": t.get("created_at") or datetime.utcnow().isoformat(),
                "assigned_agent": None,
                "started_at": None,
                "external_id": t.get("id"),
            })
        return normalized
    except Exception as e:
        print(f"[agent_service] Failed to fetch external tasks: {e}")
        return []


# ── Main Agent Execution ────────────────────────────────────────────────────

async def run_agent(agent_id: str, git_repo_url: str = None, git_token: str = None) -> Dict[str, Any]:
    """
    Main function to run an agent:
    1. Fetch a task from the external API
    2. Create a persistent Docker container
    3. If git repo provided: clone repo, create task branch
    4. AI generates project code -> runs inside the container
    5. Self-healing loop until perfect
    6. If git repo: commit & push changes to the task branch
    7. Capture workspace, destroy container
    """
    agent = agent_states.get(agent_id)
    if not agent:
        raise ValueError(f"Agent {agent_id} not found")

    if agent["status"] == "running":
        raise ValueError(f"Agent {agent_id} is already running")

    # Store git config if provided (remembered for future runs)
    if git_repo_url:
        agent["git_repo_url"] = git_repo_url.strip()
    if git_token:
        agent["git_token"] = git_token.strip()

    use_git = bool(agent.get("git_repo_url"))

    # 1. Fetch tasks from external API
    external_tasks = await _fetch_external_tasks()
    if not external_tasks:
        raise ValueError("No tasks available from the external task API. Generate tasks first.")

    task = None
    for t in external_tasks:
        status_lower = (t.get("status") or "").lower()
        if status_lower not in ("completed", "done"):
            task = t
            break

    if not task:
        raise ValueError("All tasks from the external API are already completed.")

    task["status"] = "in_progress"
    task["assigned_agent"] = agent_id
    task["started_at"] = datetime.utcnow().isoformat()

    # 2. Update agent state
    agent["status"] = "running"
    agent["current_task"] = task
    agent["progress"] = 5
    agent["progress_message"] = f"Picked task: {task['title']}"
    agent["output_log"] = [{
        "time": datetime.utcnow().isoformat(),
        "type": "info",
        "message": f"Starting work on: {task['title']}"
    }]

    start_time = time.time()
    container_name = f"agent_{agent_id}_{uuid.uuid4().hex[:8]}"

    try:
        # 3. Check Docker
        docker_available = await asyncio.to_thread(_check_docker_available)
        if not docker_available:
            raise ValueError("Docker is not available. Make sure Docker Desktop is running.")

        # 4. Create persistent container
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

        agent["output_log"].append({
            "time": datetime.utcnow().isoformat(),
            "type": "info",
            "message": f"Container '{container_name}' is running with /workspace/ ready"
        })

        # 5. If git repo configured, clone it and create a task branch
        branch_name = None
        if use_git:
            branch_name = _slugify_branch_name(task["title"])
            agent["progress"] = 15
            agent["progress_message"] = f"Cloning git repo & creating branch: {branch_name}"
            agent["output_log"].append({
                "time": datetime.utcnow().isoformat(),
                "type": "info",
                "message": f"Cloning {agent['git_repo_url']} into /workspace/..."
            })

            git_result = await asyncio.to_thread(
                _setup_git_in_container, container_name,
                agent["git_repo_url"], agent.get("git_token", ""), branch_name
            )
            if not git_result["success"]:
                raise ValueError(f"Git setup failed: {git_result['error']}")

            agent["output_log"].append({
                "time": datetime.utcnow().isoformat(),
                "type": "info",
                "message": f"Git repo cloned. Working on branch: {branch_name}"
            })

        # 6. Generate project-building code with AI
        agent["progress"] = 20
        agent["progress_message"] = "AI is generating project code..."
        agent["output_log"].append({
            "time": datetime.utcnow().isoformat(),
            "type": "info",
            "message": "Calling AI model to generate project code..."
        })

        generated_code = await _call_ai_for_code(task["description"], agent["type"])

        agent["progress"] = 30
        agent["progress_message"] = "Running project builder inside Docker..."
        agent["output_log"].append({
            "time": datetime.utcnow().isoformat(),
            "type": "info",
            "message": f"AI generated {len(generated_code.splitlines())} lines of builder code"
        })

        # 6. Execute builder code inside the persistent container
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

        # ═══════════════════════════════════════════════════════════════
        # 7. SELF-HEALING LOOP — keep fixing until project is perfect
        # ═══════════════════════════════════════════════════════════════
        all_generated_code = generated_code
        all_stdout = result["stdout"]
        fix_iteration = 0

        while fix_iteration < MAX_FIX_ITERATIONS:
            issue_report = _detect_issues_from_output(result["stdout"], result["stderr"], result["exit_code"])

            # Check if builder script itself crashed (SyntaxError etc.)
            builder_crashed = _is_builder_script_crash(result.get("stderr", ""))
            workspace_empty = False
            if builder_crashed:
                workspace_empty = await asyncio.to_thread(_is_workspace_empty, container_name)

            # If workspace is empty after a crash, force rebuild
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
                fix_code = await _call_ai_for_fix(
                    task_description=task["description"],
                    agent_type=agent["type"],
                    issues=issue_report["issues"],
                    previous_output=result["stdout"],
                    iteration=fix_iteration,
                    builder_crashed=(builder_crashed and workspace_empty),
                )

                agent["output_log"].append({
                    "time": datetime.utcnow().isoformat(),
                    "type": "info",
                    "message": f"AI generated {len(fix_code.splitlines())} lines of fix code"
                })

                # Run fix code in the SAME container (files persist)
                result = await asyncio.to_thread(
                    _exec_script_in_container, container_name, fix_code, f"fix_{agent_id}_{fix_iteration}"
                )

                # Log fix output
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

        # ═══════════════════════════════════════════════════════════════
        # 8. CAPTURE WORKSPACE — get all files + code before cleanup
        # ═══════════════════════════════════════════════════════════════
        agent["progress"] = 90
        agent["progress_message"] = "Capturing project workspace..."
        agent["output_log"].append({
            "time": datetime.utcnow().isoformat(),
            "type": "info",
            "message": "=============================================="
        })
        agent["output_log"].append({
            "time": datetime.utcnow().isoformat(),
            "type": "info",
            "message": "Capturing workspace file tree and code..."
        })

        workspace_tree = await asyncio.to_thread(_capture_workspace_tree, container_name)

        agent["output_log"].append({
            "time": datetime.utcnow().isoformat(),
            "type": "info",
            "message": f"Captured {workspace_tree.count('FILE:')} files from /workspace/"
        })

        # ═══════════════════════════════════════════════════════════════
        # 9. GIT COMMIT & PUSH — if a repository was provided
        # ═══════════════════════════════════════════════════════════════
        if use_git and branch_name:
            agent["progress"] = 95
            agent["progress_message"] = f"Committing and pushing to {branch_name}..."
            agent["output_log"].append({
                "time": datetime.utcnow().isoformat(),
                "type": "info",
                "message": f"Committing changes and pushing to branch: {branch_name}..."
            })
            
            commit_result = await asyncio.to_thread(
                _commit_and_push, container_name, task["title"], branch_name
            )
            
            if commit_result["success"]:
                agent["output_log"].append({
                    "time": datetime.utcnow().isoformat(),
                    "type": "info",
                    "message": f"Successfully pushed code to GitHub branch: {branch_name}"
                })
            else:
                agent["output_log"].append({
                    "time": datetime.utcnow().isoformat(),
                    "type": "error",
                    "message": f"Git pushing failed: {commit_result['error']}"
                })
        else:
            agent["output_log"].append({
                "time": datetime.utcnow().isoformat(),
                "type": "info",
                "message": "Git is not configured. Skipping code push."
            })

        # ═══════════════════════════════════════════════════════════════
        # 10. CLEANUP container now that everything is captured
        # ═══════════════════════════════════════════════════════════════
        await asyncio.to_thread(_destroy_container, container_name)
        agent["output_log"].append({
            "time": datetime.utcnow().isoformat(),
            "type": "info",
            "message": f"Container '{container_name}' destroyed. Project code captured."
        })

        # ═══════════════════════════════════════════════════════════════
        # 10. Final status update
        # ═══════════════════════════════════════════════════════════════
        elapsed = round(time.time() - start_time, 1)

        stats = _parse_stats_from_output(all_stdout, agent["type"])
        stats["avg_time"] = f"{elapsed}s"
        agent["stats"] = stats

        if fix_iteration > 0:
            agent["output_log"].append({
                "time": datetime.utcnow().isoformat(),
                "type": "info",
                "message": f"Self-healing complete. Ran {fix_iteration} fix round(s) in {elapsed}s."
            })

        if result["exit_code"] == 0:
            agent["status"] = "completed"
            agent["progress"] = 100
            agent["progress_message"] = f"Project built successfully!" + (f" ({fix_iteration} fix rounds)" if fix_iteration > 0 else "")
            task["status"] = "completed"
        else:
            agent["status"] = "completed"
            agent["progress"] = 100
            agent["progress_message"] = f"Completed with exit code {result['exit_code']}" + (f" after {fix_iteration} rounds" if fix_iteration > 0 else "")
            task["status"] = "completed_with_errors"

        agent["last_run"] = datetime.utcnow().isoformat()
        agent["last_result"] = {
            "task": task,
            "exit_code": result["exit_code"],
            "stdout": all_stdout,
            "stderr": result["stderr"],
            "generated_code": workspace_tree,   # The full project structure + code
            "builder_scripts": all_generated_code,  # The AI-generated builder scripts
            "duration": elapsed,
            "fix_iterations": fix_iteration,
        }
        agent["current_task"] = None

        completed_tasks.append(task)

        return {
            "success": True,
            "agent_id": agent_id,
            "task": task,
            "exit_code": result["exit_code"],
            "output": all_stdout,
            "errors": result["stderr"],
            "duration": elapsed,
            "stats": stats,
            "fix_iterations": fix_iteration,
        }

    except Exception as e:
        elapsed = round(time.time() - start_time, 1)
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

        # Always clean up container on error
        await asyncio.to_thread(_destroy_container, container_name)

        return {
            "success": False,
            "agent_id": agent_id,
            "error": str(e),
            "duration": elapsed,
        }


# ── Agent & Task Management Helpers ─────────────────────────────────────────

def get_pending_tasks() -> List[Dict[str, Any]]:
    return []

def get_agent_status(agent_id: str) -> Dict[str, Any]:
    agent = agent_states.get(agent_id)
    if not agent:
        raise ValueError(f"Agent {agent_id} not found")
    return agent

def get_all_agents() -> List[Dict[str, Any]]:
    return list(agent_states.values())

def reset_agent(agent_id: str) -> Dict[str, Any]:
    agent = agent_states.get(agent_id)
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
