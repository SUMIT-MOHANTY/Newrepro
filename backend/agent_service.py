"""
Agent Service for AI-Powered Development Agents
Uses the existing AI model to understand tasks, then runs Python subprocesses to develop code.
"""
import asyncio
import json
import os
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime
from typing import Optional, Dict, Any, List
from config import settings
import httpx


# ── In-memory state stores ──────────────────────────────────────────────────
# In production these would be DB-backed; for now we keep them in-memory.

# Pending tasks queue (simulating tasks from an API that isn't ready yet)
pending_tasks: List[Dict[str, Any]] = []

# Agent states
agent_states: Dict[str, Dict[str, Any]] = {
    "agent_01": {
        "id": "agent_01",
        "name": "Requirements Validator",
        "type": "validator",
        "status": "idle",         # idle | running | completed | error
        "current_task": None,
        "progress": 0,
        "progress_message": "",
        "last_run": None,
        "last_result": None,
        "output_log": [],
        "stats": {"checks": 0, "coverage": 0, "avg_time": "0m"},
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
    },
}

# Track completed tasks
completed_tasks: List[Dict[str, Any]] = []


# ── Agent System Prompts ────────────────────────────────────────────────────

AGENT_SYSTEM_PROMPTS = {
    "validator": """You are a Requirements Validator AI Agent.
Your job is to analyze the given task/requirement and produce Python code that validates it.

Given a task description, you must:
1. Understand what the task requires
2. Generate a Python script that performs the validation checks
3. The script should print its findings as structured output

Your output must be ONLY valid Python code (no markdown, no explanations outside the code).
The Python script should:
- Print each check it performs
- Print PASS or FAIL for each check
- Print a final summary at the end
- Exit with code 0 if all checks pass, 1 if any fail

Example output format in the script:
print("[CHECK 1] Requirement completeness... PASS")
print("[CHECK 2] Acceptance criteria defined... FAIL - Missing acceptance criteria")
print("\\n=== SUMMARY ===")
print("Total: 5 | Passed: 4 | Failed: 1")
""",

    "risk": """You are a Risk Assessment AI Agent.
Your job is to analyze the given task/requirement and produce Python code that performs risk analysis.

Given a task description, you must:
1. Understand the potential risks in the requirement
2. Generate a Python script that identifies and categorizes risks
3. The script should print its findings as structured output

Your output must be ONLY valid Python code (no markdown, no explanations outside the code).
The Python script should:
- Identify technical, business, and operational risks
- Rate each risk as LOW, MEDIUM, HIGH, or CRITICAL
- Print a structured report
- Exit with code 0 always

Example output format in the script:
print("[RISK 1] Data Security - HIGH - No encryption specified for PII data")
print("[RISK 2] Scalability - MEDIUM - No load testing requirement defined")
print("\\n=== RISK SUMMARY ===")
print("Total: 5 | Critical: 1 | High: 2 | Medium: 1 | Low: 1")
""",

    "estimator": """You are a Resource Estimation AI Agent.
Your job is to analyze the given task/requirement and produce Python code that estimates resources needed.

Given a task description, you must:
1. Break down the task into sub-tasks
2. Generate a Python script that estimates effort, team size, and timeline
3. The script should print its findings as structured output

Your output must be ONLY valid Python code (no markdown, no explanations outside the code).
The Python script should:
- Break down work into sprints
- Estimate team size needed
- Provide timeline estimates
- Print a structured resource plan
- Exit with code 0 always

Example output format in the script:
print("[SPRINT 1] Setup & Architecture - 2 weeks - 2 developers")
print("[SPRINT 2] Core Feature Development - 3 weeks - 3 developers")
print("\\n=== RESOURCE SUMMARY ===")
print("Total Sprints: 4 | Duration: 10 weeks | Team Size: 3-4 developers")
""",
}

# Maximum number of self-healing iterations
MAX_FIX_ITERATIONS = 2


# ── Helper: Detect issues from subprocess output ───────────────────────────

def _detect_issues_from_output(stdout: str, stderr: str) -> Dict[str, Any]:
    """
    Parse subprocess output for FAIL, ERROR, CRITICAL, or gap indicators.
    Returns a dict with has_issues=True/False and a list of issue strings.
    """
    issues = []
    all_text = (stdout or "") + "\n" + (stderr or "")
    lines = all_text.strip().split("\n")

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        # Detect FAIL lines
        if "FAIL" in stripped and stripped.startswith("["):
            issues.append(stripped)
        # Detect CRITICAL risk lines
        elif "CRITICAL" in stripped and stripped.startswith("["):
            issues.append(stripped)
        # Detect gap lines (numbered gaps)
        elif stripped.startswith(("1.", "2.", "3.", "4.", "5.", "6.", "7.", "8.", "9.")) and any(
            kw in stripped.lower() for kw in ["missing", "gap", "not specified", "not defined", "undefined", "not detailed", "not documented"]
        ):
            issues.append(stripped)
        # Detect explicit error lines from stderr
        elif stderr and stripped in stderr and ("Error" in stripped or "Exception" in stripped or "Traceback" in stripped):
            issues.append(f"RUNTIME ERROR: {stripped}")

    return {
        "has_issues": len(issues) > 0,
        "issues": issues,
        "issue_count": len(issues),
    }


# ── Helper: Call AI Model ───────────────────────────────────────────────────

async def _call_ai_for_code(task_description: str, agent_type: str) -> str:
    """
    Call the existing AI model to generate Python code for a given task.
    Uses the same AI config (API URL, key, model) as the main BRD analysis.
    """
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
            {"role": "user", "content": f"Task to analyze:\n\n{task_description}"},
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
                    await asyncio.sleep(5 * attempt)  # backoff: 5s, 10s
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
        # Strip markdown code fences if present
        content = content.strip()
        if content.startswith("```python"):
            content = content[len("```python"):].strip()
        if content.startswith("```"):
            content = content[3:].strip()
        if content.endswith("```"):
            content = content[:-3].strip()
        return content
    else:
        raise ValueError("No response from AI model")


async def _call_ai_for_fix(task_description: str, agent_type: str, issues: list, previous_output: str, iteration: int) -> str:
    """
    Call the AI model to generate a FIX for previously detected gaps/errors.
    Sends the original task + the specific issues found so the AI can address them.
    """
    url = settings.ai_api_url
    key = settings.ai_api_key
    model_name = settings.ai_model

    if not key or key == "your-api-key-here":
        raise ValueError("AI API key not configured")

    system_prompt = AGENT_SYSTEM_PROMPTS.get(agent_type, AGENT_SYSTEM_PROMPTS["validator"])

    issues_text = "\n".join(f"  - {issue}" for issue in issues)

    fix_prompt = f"""SELF-HEALING ITERATION {iteration}: FIX THE GAPS AND ERRORS

You previously analyzed this task and your output contained the following gaps/errors/issues:

{issues_text}

PREVIOUS OUTPUT (for reference):
{previous_output[:2000]}

ORIGINAL TASK:
{task_description}

Now generate a NEW Python script that:
1. ADDRESSES each of the gaps/errors listed above
2. Provides concrete solutions, recommendations, or fixes for each issue
3. For each gap, print a [FIX] line showing how it should be resolved
4. Print a final summary showing how many issues were fixed

Your output must be ONLY valid Python code. The script should print structured output like:
print("[FIX 1] Password reset token expiration -> Recommend 15-minute expiry with one-time-use tokens")
print("[FIX 2] Rate limiting scope -> Implement per-IP and per-user hybrid rate limiting")
print("\\n=== FIX SUMMARY ===")
print("Total Issues: 7 | Fixed: 7 | Remaining: 0")

IMPORTANT: Use ONLY ASCII characters in your Python code. Do NOT use Unicode arrows, emojis, or special symbols.
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

    # Add a small delay before the fix call to avoid API rate limits
    await asyncio.sleep(3)

    async with httpx.AsyncClient(timeout=120.0) as client:
        last_err = None
        for attempt in range(3):
            try:
                if attempt > 0:
                    await asyncio.sleep(5 * attempt)  # backoff: 5s, 10s
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
        content = content.strip()
        if content.startswith("```python"):
            content = content[len("```python"):].strip()
        if content.startswith("```"):
            content = content[3:].strip()
        if content.endswith("```"):
            content = content[:-3].strip()
        return content
    else:
        raise ValueError("No response from AI model for fix iteration")


# ── Docker Configuration ────────────────────────────────────────────────────

DOCKER_CONTAINER_NAME = "mylinux"
DOCKER_PYTHON_CMD = "python3"
DOCKER_SCRIPT_DIR = "/tmp/agent_scripts"


def _check_docker_container() -> bool:
    """Check if the Docker container is running."""
    try:
        result = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Running}}", DOCKER_CONTAINER_NAME],
            capture_output=True, text=True, timeout=10,
        )
        return result.stdout.strip() == "true"
    except Exception:
        return False


# ── Helper: Run Python inside Docker Container ─────────────────────────────

async def _run_python_subprocess(code: str, agent_id: str) -> Dict[str, Any]:
    """
    Write the AI-generated Python code to a temp file, copy it into the Docker
    container, and execute it with `docker exec`. Captures stdout/stderr.
    """
    agent = agent_states[agent_id]

    # Write generated code to a local temp file
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, prefix=f"agent_{agent_id}_",
        encoding="utf-8",
    ) as f:
        f.write(code)
        script_path = f.name

    script_name = os.path.basename(script_path)
    container_script_path = f"{DOCKER_SCRIPT_DIR}/{script_name}"

    agent["progress"] = 60
    agent["progress_message"] = "Executing inside Docker container..."
    agent["output_log"].append({
        "time": datetime.utcnow().isoformat(),
        "type": "info",
        "message": f"Running script: {script_name}"
    })
    agent["output_log"].append({
        "time": datetime.utcnow().isoformat(),
        "type": "info",
        "message": f"Docker container: {DOCKER_CONTAINER_NAME} | Python: {DOCKER_PYTHON_CMD}"
    })

    def _exec_in_docker():
        """Copy script into container and execute it (called via asyncio.to_thread)."""
        try:
            # 1. Ensure the script directory exists inside the container
            subprocess.run(
                ["docker", "exec", DOCKER_CONTAINER_NAME, "mkdir", "-p", DOCKER_SCRIPT_DIR],
                capture_output=True, text=True, timeout=10,
            )

            # 2. Copy the script from local Windows into the Docker container
            cp_result = subprocess.run(
                ["docker", "cp", script_path, f"{DOCKER_CONTAINER_NAME}:{container_script_path}"],
                capture_output=True, text=True, timeout=15,
            )
            if cp_result.returncode != 0:
                return {
                    "exit_code": -1,
                    "stdout": "",
                    "stderr": f"docker cp failed: {cp_result.stderr}",
                    "script_path": script_path,
                    "error": f"docker cp failed: {cp_result.stderr}",
                }

            # 3. Execute the script inside the container
            result = subprocess.run(
                ["docker", "exec", DOCKER_CONTAINER_NAME, DOCKER_PYTHON_CMD, container_script_path],
                capture_output=True, text=True, timeout=60,
            )

            # 4. Clean up the script inside the container
            subprocess.run(
                ["docker", "exec", DOCKER_CONTAINER_NAME, "rm", "-f", container_script_path],
                capture_output=True, text=True, timeout=10,
            )

            return {
                "exit_code": result.returncode,
                "stdout": result.stdout or "",
                "stderr": result.stderr or "",
                "script_path": script_path,
                "error": None,
            }

        except subprocess.TimeoutExpired:
            return {
                "exit_code": -1,
                "stdout": "",
                "stderr": "Script execution timed out (60s limit) inside Docker",
                "script_path": script_path,
                "error": "timeout",
            }
        except FileNotFoundError:
            return {
                "exit_code": -1,
                "stdout": "",
                "stderr": "Docker command not found. Is Docker installed and in PATH?",
                "script_path": script_path,
                "error": "docker_not_found",
            }
        except Exception as e:
            return {
                "exit_code": -1,
                "stdout": "",
                "stderr": str(e),
                "script_path": script_path,
                "error": str(e),
            }

    try:
        # Check if Docker container is running
        container_running = await asyncio.to_thread(_check_docker_container)
        if not container_running:
            agent["output_log"].append({
                "time": datetime.utcnow().isoformat(),
                "type": "error",
                "message": f"Docker container '{DOCKER_CONTAINER_NAME}' is not running! Start it with: docker start {DOCKER_CONTAINER_NAME}"
            })
            return {
                "exit_code": -1,
                "stdout": "",
                "stderr": f"Container '{DOCKER_CONTAINER_NAME}' not running",
                "script_path": script_path,
                "error": "container_not_running",
            }

        # Execute inside Docker
        result = await asyncio.to_thread(_exec_in_docker)

        stdout_text = result["stdout"]
        stderr_text = result["stderr"]

        # Parse output lines into log entries
        for line in stdout_text.strip().split("\n"):
            if line.strip():
                agent["output_log"].append({
                    "time": datetime.utcnow().isoformat(),
                    "type": "output",
                    "message": line.strip()
                })

        if stderr_text.strip():
            for line in stderr_text.strip().split("\n"):
                if line.strip():
                    agent["output_log"].append({
                        "time": datetime.utcnow().isoformat(),
                        "type": "error",
                        "message": line.strip()
                    })

        if result.get("error") == "timeout":
            agent["output_log"].append({
                "time": datetime.utcnow().isoformat(),
                "type": "error",
                "message": "Script execution timed out (60s limit) inside Docker"
            })
        elif result.get("error") == "docker_not_found":
            agent["output_log"].append({
                "time": datetime.utcnow().isoformat(),
                "type": "error",
                "message": "Docker is not installed or not in PATH"
            })
        elif result.get("error"):
            agent["output_log"].append({
                "time": datetime.utcnow().isoformat(),
                "type": "error",
                "message": f"Docker exec error: {result['error']}"
            })

        return result

    except Exception as e:
        agent["output_log"].append({
            "time": datetime.utcnow().isoformat(),
            "type": "error",
            "message": f"Failed to run script in Docker: {str(e)}"
        })
        return {
            "exit_code": -1,
            "stdout": "",
            "stderr": str(e),
            "script_path": script_path,
        }
    finally:
        # Clean up local temp file
        try:
            os.unlink(script_path)
        except OSError:
            pass


# ── Parse agent output for stats ────────────────────────────────────────────

def _parse_stats_from_output(stdout: str, agent_type: str) -> Dict[str, Any]:
    """Extract stats from the agent subprocess output."""
    lines = stdout.strip().split("\n") if stdout else []

    if agent_type == "validator":
        checks = sum(1 for l in lines if l.strip().startswith("[CHECK"))
        passed = sum(1 for l in lines if "PASS" in l)
        coverage = round((passed / max(checks, 1)) * 100)
        return {"checks": checks, "coverage": f"{coverage}%", "avg_time": "—"}

    elif agent_type == "risk":
        risks = sum(1 for l in lines if l.strip().startswith("[RISK"))
        critical = sum(1 for l in lines if "CRITICAL" in l)
        return {"risks": risks, "critical": critical, "avg_time": "—"}

    elif agent_type == "estimator":
        sprints = sum(1 for l in lines if l.strip().startswith("[SPRINT"))
        # Try to extract team size from summary
        resources = 0
        for l in lines:
            if "Team Size" in l or "developers" in l.lower():
                import re
                nums = re.findall(r"\d+", l)
                if nums:
                    resources = int(nums[-1])
                    break
        if resources == 0:
            resources = sprints  # fallback
        return {"sprints": sprints, "resources": resources, "avg_time": "—"}

    return {}


# ── Main Agent Execution ────────────────────────────────────────────────────

async def run_agent(agent_id: str) -> Dict[str, Any]:
    """
    Main function to run an agent:
    1. Pick a pending task from the queue
    2. Call AI model to generate code for the task
    3. Run the generated code in a Python subprocess
    4. Update agent state with results
    """
    agent = agent_states.get(agent_id)
    if not agent:
        raise ValueError(f"Agent {agent_id} not found")

    if agent["status"] == "running":
        raise ValueError(f"Agent {agent_id} is already running")

    # 1. Pick a pending task
    if not pending_tasks:
        raise ValueError("No pending tasks available. Add tasks first.")

    task = pending_tasks.pop(0)  # Take the first pending task
    task["status"] = "in_progress"
    task["assigned_agent"] = agent_id
    task["started_at"] = datetime.utcnow().isoformat()

    # 2. Update agent state
    agent["status"] = "running"
    agent["current_task"] = task
    agent["progress"] = 10
    agent["progress_message"] = f"Picked task: {task['title']}"
    agent["output_log"] = [{
        "time": datetime.utcnow().isoformat(),
        "type": "info",
        "message": f"Starting work on: {task['title']}"
    }]

    start_time = time.time()

    try:
        # 3. Call AI model to generate code
        agent["progress"] = 20
        agent["progress_message"] = "AI is understanding the task..."
        agent["output_log"].append({
            "time": datetime.utcnow().isoformat(),
            "type": "info",
            "message": "Calling AI model to generate analysis code..."
        })

        generated_code = await _call_ai_for_code(task["description"], agent["type"])

        agent["progress"] = 35
        agent["progress_message"] = "Code generated, preparing execution..."
        agent["output_log"].append({
            "time": datetime.utcnow().isoformat(),
            "type": "info",
            "message": f"AI generated {len(generated_code.splitlines())} lines of Python code"
        })

        # 4. Run the subprocess
        result = await _run_python_subprocess(generated_code, agent_id)

        # ═══════════════════════════════════════════════════════════════
        # 5. SELF-HEALING LOOP: Detect issues → call AI for fix → re-run
        # ═══════════════════════════════════════════════════════════════
        all_generated_code = generated_code
        all_stdout = result["stdout"]
        fix_iteration = 0

        while fix_iteration < MAX_FIX_ITERATIONS:
            issue_report = _detect_issues_from_output(result["stdout"], result["stderr"])

            if not issue_report["has_issues"]:
                agent["output_log"].append({
                    "time": datetime.utcnow().isoformat(),
                    "type": "info",
                    "message": f"✅ No gaps/errors detected — no fix iteration needed."
                })
                break  # No issues found, exit loop

            fix_iteration += 1
            issue_count = issue_report["issue_count"]

            agent["output_log"].append({
                "time": datetime.utcnow().isoformat(),
                "type": "info",
                "message": f"══════════════════════════════════════════════"
            })
            agent["output_log"].append({
                "time": datetime.utcnow().isoformat(),
                "type": "info",
                "message": f"🔄 SELF-HEALING: Detected {issue_count} gaps/errors — starting fix iteration {fix_iteration}/{MAX_FIX_ITERATIONS}"
            })

            # Log each detected issue
            for idx, issue in enumerate(issue_report["issues"][:10], 1):  # Cap at 10
                agent["output_log"].append({
                    "time": datetime.utcnow().isoformat(),
                    "type": "info",
                    "message": f"  Issue {idx}: {issue[:120]}"
                })

            # Update progress for fix iteration
            base_progress = 50 + (fix_iteration * 20)
            agent["progress"] = min(base_progress, 90)
            agent["progress_message"] = f"Self-healing: Fixing {issue_count} issues (iteration {fix_iteration})..."

            # Call AI with the issues to get fix code
            agent["output_log"].append({
                "time": datetime.utcnow().isoformat(),
                "type": "info",
                "message": f"Calling AI model to generate fix code..."
            })

            try:
                fix_code = await _call_ai_for_fix(
                    task_description=task["description"],
                    agent_type=agent["type"],
                    issues=issue_report["issues"],
                    previous_output=result["stdout"],
                    iteration=fix_iteration,
                )

                agent["output_log"].append({
                    "time": datetime.utcnow().isoformat(),
                    "type": "info",
                    "message": f"AI generated {len(fix_code.splitlines())} lines of fix code"
                })

                # Run the fix code
                result = await _run_python_subprocess(fix_code, agent_id)
                all_generated_code += f"\n\n# ═══ FIX ITERATION {fix_iteration} ═══\n" + fix_code
                all_stdout += f"\n\n--- FIX ITERATION {fix_iteration} ---\n" + result["stdout"]

            except Exception as fix_err:
                agent["output_log"].append({
                    "time": datetime.utcnow().isoformat(),
                    "type": "error",
                    "message": f"Self-healing iteration {fix_iteration} failed: {str(fix_err)}"
                })
                break  # Stop trying if AI call fails

        # ═══════════════════════════════════════════════════════════════
        # 6. Final status update
        # ═══════════════════════════════════════════════════════════════
        elapsed = round(time.time() - start_time, 1)

        stats = _parse_stats_from_output(all_stdout, agent["type"])
        stats["avg_time"] = f"{elapsed}s"
        agent["stats"] = stats

        if fix_iteration > 0:
            agent["output_log"].append({
                "time": datetime.utcnow().isoformat(),
                "type": "info",
                "message": f"══════════════════════════════════════════════"
            })
            agent["output_log"].append({
                "time": datetime.utcnow().isoformat(),
                "type": "info",
                "message": f"🏁 Self-healing complete. Ran {fix_iteration} fix iteration(s) in {elapsed}s total."
            })

        if result["exit_code"] == 0:
            agent["status"] = "completed"
            agent["progress"] = 100
            agent["progress_message"] = f"Task completed successfully!" + (f" ({fix_iteration} auto-fix rounds)" if fix_iteration > 0 else "")
            task["status"] = "completed"
        else:
            agent["status"] = "completed"
            agent["progress"] = 100
            agent["progress_message"] = f"Completed with exit code {result['exit_code']}" + (f" after {fix_iteration} fix rounds" if fix_iteration > 0 else "")
            task["status"] = "completed_with_errors"

        agent["last_run"] = datetime.utcnow().isoformat()
        agent["last_result"] = {
            "task": task,
            "exit_code": result["exit_code"],
            "stdout": all_stdout,
            "stderr": result["stderr"],
            "generated_code": all_generated_code,
            "duration": elapsed,
            "fix_iterations": fix_iteration,
        }
        agent["current_task"] = None

        # Move task to completed
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

        # Put the task back in the queue
        task["status"] = "pending"
        task["assigned_agent"] = None
        pending_tasks.insert(0, task)

        return {
            "success": False,
            "agent_id": agent_id,
            "error": str(e),
            "duration": elapsed,
        }


# ── Task Management ─────────────────────────────────────────────────────────

def create_task(title: str, description: str, priority: str = "medium") -> Dict[str, Any]:
    """Create a new pending task."""
    task = {
        "id": str(uuid.uuid4())[:8],
        "title": title,
        "description": description,
        "priority": priority,
        "status": "pending",
        "created_at": datetime.utcnow().isoformat(),
        "assigned_agent": None,
        "started_at": None,
    }
    pending_tasks.append(task)
    return task


def get_pending_tasks() -> List[Dict[str, Any]]:
    """Get all pending tasks."""
    return pending_tasks


def get_agent_status(agent_id: str) -> Dict[str, Any]:
    """Get the current status of a specific agent."""
    agent = agent_states.get(agent_id)
    if not agent:
        raise ValueError(f"Agent {agent_id} not found")
    return agent


def get_all_agents() -> List[Dict[str, Any]]:
    """Get status of all agents."""
    return list(agent_states.values())


def reset_agent(agent_id: str) -> Dict[str, Any]:
    """Reset an agent back to idle status."""
    agent = agent_states.get(agent_id)
    if not agent:
        raise ValueError(f"Agent {agent_id} not found")
    agent["status"] = "idle"
    agent["progress"] = 0
    agent["progress_message"] = ""
    agent["current_task"] = None
    return agent


# ── Seed some sample tasks for demo ─────────────────────────────────────────

def seed_sample_tasks():
    """Create some sample pending tasks for demonstration."""
    if pending_tasks:
        return  # Already seeded

    sample_tasks = [
        {
            "title": "Validate Authentication API Requirements",
            "description": """
            The project requires a user authentication system with the following requirements:
            - Email/password based login with JWT tokens
            - OAuth 2.0 integration with Google and GitHub
            - Password reset via email
            - Session management with 30-minute timeout
            - Rate limiting on login attempts (5 per minute)
            - Multi-factor authentication (optional)
            - User roles: Admin, Manager, User
            Please validate completeness of these requirements and identify any gaps.
            """,
            "priority": "high",
        },
        {
            "title": "Assess Risks in Payment Integration",
            "description": """
            The project involves integrating a payment gateway with these specifications:
            - Stripe integration for credit/debit card payments
            - Support for subscriptions and one-time payments
            - PCI DSS compliance required
            - Handle refunds and disputes
            - Multi-currency support (USD, EUR, GBP)
            - Store payment history for 7 years
            - Real-time webhook processing for payment events
            Analyze technical, business, and compliance risks.
            """,
            "priority": "high",
        },
        {
            "title": "Estimate Resources for Dashboard Module",
            "description": """
            Build an analytics dashboard module with:
            - Real-time data visualization using charts (line, bar, pie, area)
            - Customizable dashboard layouts (drag & drop widgets)
            - Data filtering by date range, category, and custom fields
            - Export reports as PDF and CSV
            - Role-based access to different dashboard views
            - WebSocket-based live data updates
            - Mobile responsive design
            - Integration with existing REST API backend
            Estimate the team size, sprint count, and timeline.
            """,
            "priority": "medium",
        },
        {
            "title": "Validate Notification System Requirements",
            "description": """
            Build a notification system that supports:
            - Email notifications via SendGrid
            - Push notifications for mobile (iOS/Android via Firebase)
            - In-app notification center with read/unread status
            - Notification preferences per user
            - Template-based notifications with variable substitution
            - Scheduled notifications and reminders
            - Notification grouping and batching
            Validate that all requirements are well-defined.
            """,
            "priority": "medium",
        },
        {
            "title": "Assess Security Risks in File Upload Feature",
            "description": """
            The application needs a file upload feature with:
            - Support for PDF, DOCX, XLSX, images (up to 50MB each)
            - Virus scanning on upload
            - File type validation (magic bytes, not just extension)
            - Cloud storage on AWS S3 with signed URLs
            - Access control per file/folder
            - File versioning support
            - Thumbnail generation for images
            Identify all security risks and vulnerabilities.
            """,
            "priority": "high",
        },
    ]

    for task_data in sample_tasks:
        create_task(
            title=task_data["title"],
            description=task_data["description"],
            priority=task_data["priority"],
        )
