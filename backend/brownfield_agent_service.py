"""
Brownfield Agent Service
========================
Handles agent execution for BROWNFIELD and MODERNIZATION projects.

Design principles:
- Completely separate from agent_service.py (no modifications to that file)
- Imports shared utilities from agent_service (git auth, container tools)
- Brownfield agents clone an EXISTING repo branch, scan existing files,
  then apply targeted changes rather than building from scratch
- Task generation produces precise, file-level change tasks (no TASK-00)
"""
import subprocess
import asyncio
import logging
import os
import time
import uuid
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy imports from agent_service to avoid circular imports
# ---------------------------------------------------------------------------

def _get_agent_service_utils():
    """Lazily import shared utilities from agent_service to avoid circular imports."""
    import agent_service as _as
    return {
        "build_git_auth_url": _as._build_git_auth_url,
        "get_git_auth_config": _as._get_git_auth_config,
        "verify_container_toolchain": _as._verify_container_toolchain,
        "create_persistent_container": _as._create_persistent_container,
        "ensure_agent_runtime_image": _as._ensure_agent_runtime_image,
        "AGENT_RUNTIME_IMAGE": _as.AGENT_RUNTIME_IMAGE,
    }


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BROWNFIELD_CONTAINER_PREFIX = "dsuite_bf_"
BROWNFIELD_FEATURE_BRANCH_PREFIX = "dsuite/change-"

INVENTORY_EXTENSIONS = (
    ".py", ".ts", ".tsx", ".js", ".jsx", ".java", ".cs", ".go", ".rb",
    ".php", ".swift", ".kt", ".rs", ".vue", ".svelte",
    ".html", ".css", ".scss", ".less",
    ".json", ".yaml", ".yml", ".toml", ".env.example",
    ".sql", ".graphql", ".proto",
    ".md", ".txt", ".sh", ".dockerfile",
)

INVENTORY_EXCLUDE_DIRS = {
    "node_modules", "__pycache__", ".git", "dist", "build", ".next",
    "out", "target", "bin", "obj", ".cache", "coverage", ".nyc_output",
    "venv", ".venv", "env", ".env",
}


# ---------------------------------------------------------------------------
# Tech Stack Detection & Skill Matching
# ---------------------------------------------------------------------------

# Maps a canonical skill key → detection signals (file extensions + text keywords)
# Each entry: { "extensions": [...], "keywords": [...], "label": str, "agent_template": str }
TECH_STACK_SIGNALS: Dict[str, Dict[str, Any]] = {
    "java": {
        "extensions": [".java", ".class", ".jar"],
        "files": ["pom.xml", "build.gradle", "gradlew", ".mvn"],
        "keywords": ["spring boot", "springboot", "spring framework", "@springbootapplication",
                     "hibernate", "maven", "gradle", "javax", "jakarta"],
        "label": "Java / Spring Boot",
        "agent_template": "Java / Spring Boot Developer",
    },
    "dotnet": {
        "extensions": [".cs", ".vb", ".fs", ".csproj", ".sln", ".aspx"],
        "files": [".csproj", ".sln", "global.json", "nuget.config"],
        "keywords": [".net", "asp.net", "aspnetcore", "entity framework", "dotnet",
                     "c#", "csharp", "nuget", "blazor", "razor"],
        "label": ".NET / C#",
        "agent_template": ".NET / C# Developer",
    },
    "python_django": {
        "extensions": [".py"],
        "files": ["manage.py", "requirements.txt", "Pipfile", "pyproject.toml"],
        "keywords": ["django", "celery", "drf", "rest_framework", "wsgi", "asgi",
                     "flask", "fastapi", "sqlalchemy", "alembic"],
        "label": "Python / Django",
        "agent_template": "Python / Django Developer",
    },
    "nodejs": {
        "extensions": [".ts", ".js", ".mjs", ".cjs"],
        "files": ["package.json", "package-lock.json", "yarn.lock", "tsconfig.json"],
        "keywords": ["express", "nestjs", "fastify", "koa", "hapi", "prisma",
                     "typeorm", "sequelize", "node.js", "nodejs"],
        "label": "Node.js / TypeScript",
        "agent_template": "Node.js / Express Developer",
    },
    "react": {
        "extensions": [".tsx", ".jsx"],
        "files": ["package.json"],
        "keywords": ["react", "vite", "next.js", "nextjs", "webpack", "tailwind",
                     "redux", "zustand", "react-query", "chakra"],
        "label": "React / Frontend",
        "agent_template": "Frontend Developer",
    },
    "go": {
        "extensions": [".go"],
        "files": ["go.mod", "go.sum", "Makefile"],
        "keywords": ["gin", "echo", "fiber", "gorm", "grpc", "golang"],
        "label": "Go",
        "agent_template": "Go Developer",
    },
    "ruby": {
        "extensions": [".rb", ".rake", ".gemspec"],
        "files": ["Gemfile", "Rakefile", "config.ru"],
        "keywords": ["rails", "ruby on rails", "sinatra", "activerecord", "devise"],
        "label": "Ruby / Rails",
        "agent_template": "Ruby / Rails Developer",
    },
    "php": {
        "extensions": [".php"],
        "files": ["composer.json", "composer.lock", ".htaccess"],
        "keywords": ["laravel", "symfony", "wordpress", "phalcon", "composer"],
        "label": "PHP / Laravel",
        "agent_template": "PHP / Laravel Developer",
    },
}


def detect_required_tech_stack(
    brd_text: str = "",
    repo_files: Optional[List[str]] = None,
    repo_structure_text: str = "",
) -> Dict[str, Any]:
    """
    Detect the required tech stack from BRD/change-request text and the
    existing repo file inventory.

    Returns:
        {
          "detected": {"java": {"label": "Java / Spring Boot", ...}, ...},
          "primary": "java",           # highest-confidence single key
          "required_skills": ["Java", "Spring Boot"],
          "required_agent_templates": ["Java / Spring Boot Developer"],
        }
    """
    import re

    combined_text = (brd_text + " " + repo_structure_text).lower()
    files_lower = [f.lower() for f in (repo_files or [])]

    scores: Dict[str, int] = {k: 0 for k in TECH_STACK_SIGNALS}

    for tech_key, signals in TECH_STACK_SIGNALS.items():
        # Extension hits (strong signal)
        for ext in signals.get("extensions", []):
            hits = sum(1 for f in files_lower if f.endswith(ext))
            if hits > 0:
                scores[tech_key] += min(hits, 5)  # cap to avoid noise

        # Specific file hits (very strong signal)
        for fname in signals.get("files", []):
            if any(f.endswith(fname.lower()) or fname.lower() in f for f in files_lower):
                scores[tech_key] += 8

        # Keyword hits in text (moderate signal)
        for kw in signals.get("keywords", []):
            if kw in combined_text:
                scores[tech_key] += 3

    # Filter detected (score > 0), sort by score desc
    detected = {
        k: {**TECH_STACK_SIGNALS[k], "score": v}
        for k, v in scores.items() if v > 0
    }
    detected = dict(sorted(detected.items(), key=lambda x: x[1]["score"], reverse=True))

    primary = next(iter(detected), None)

    # Build flat required skills list from top 3 detected techs
    required_skills: List[str] = []
    required_templates: List[str] = []
    for tech_key in list(detected.keys())[:3]:
        info = TECH_STACK_SIGNALS[tech_key]
        label = info["label"]
        parts = label.split(" / ")
        required_skills.extend(parts)
        tmpl = info["agent_template"]
        if tmpl not in required_templates:
            required_templates.append(tmpl)

    # Deduplicate
    required_skills = list(dict.fromkeys(required_skills))

    return {
        "detected": detected,
        "primary": primary,
        "required_skills": required_skills,
        "required_agent_templates": required_templates,
    }


def compute_skill_gaps(
    required_skills: List[str],
    required_agent_templates: List[str],
    agent_list: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Compare required skills against registered agents' skills_tags.

    Args:
        required_skills: List of skill strings detected from the project (e.g. ["Java", "Spring Boot"])
        required_agent_templates: Agent template names recommended for this project
        agent_list: List of agent dicts with 'skills_tags' and 'name' fields

    Returns:
        {
          "covered": ["React"],          # skills that have a matching agent
          "missing": ["Java", "Spring Boot"],  # skills with NO matching agent
          "suggested_templates": ["Java / Spring Boot Developer"],
          "has_gaps": True,
          "gap_summary": "No agents found for: Java, Spring Boot. Recommended: Java / Spring Boot Developer."
        }
    """
    if not agent_list:
        agent_list = []

    # Build a flat lowercase pool of all agent tags
    agent_tag_pool: List[str] = []
    for agent in agent_list:
        raw_tags = agent.get("skills_tags") or []
        if isinstance(raw_tags, str):
            try:
                import json as _json
                raw_tags = _json.loads(raw_tags)
            except Exception:
                raw_tags = [t.strip() for t in raw_tags.split(",")]
        agent_tag_pool.extend([str(t).lower().strip() for t in raw_tags if t])

    covered: List[str] = []
    missing: List[str] = []

    for skill in required_skills:
        skill_lower = skill.lower().strip()
        # Fuzzy match: any agent tag starts-with or contains the skill
        matched = any(
            skill_lower in tag or tag in skill_lower
            for tag in agent_tag_pool
        )
        if matched:
            covered.append(skill)
        else:
            missing.append(skill)

    has_gaps = len(missing) > 0
    gap_summary = ""
    if has_gaps:
        gap_summary = (
            f"No agents found for: {', '.join(missing)}. "
            f"Recommended: {', '.join(required_agent_templates)}."
        )

    return {
        "covered": covered,
        "missing": missing,
        "suggested_templates": required_agent_templates,
        "has_gaps": has_gaps,
        "gap_summary": gap_summary,
    }


def tag_tasks_with_required_skills(
    tasks: List[Dict[str, Any]],
    tech_stack: Dict[str, Any],
    skill_gaps: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Annotate each task with required_skill and skill_flag fields.

    - required_skill: the primary tech this task likely needs (derived from target_file extension + description)
    - skill_flag: True if no registered agent covers this skill
    - skill_gap_message: human-readable flag message

    This runs AFTER LLM task generation and is purely additive — it never removes tasks.
    """
    primary = tech_stack.get("primary")
    missing_lower = {s.lower() for s in skill_gaps.get("missing", [])}
    primary_label = TECH_STACK_SIGNALS.get(primary, {}).get("label", "") if primary else ""

    for task in tasks:
        # Infer tech from target_file extension
        target_file = (task.get("target_file") or "").lower()
        inferred_tech = primary  # default to project primary

        for tech_key, signals in TECH_STACK_SIGNALS.items():
            for ext in signals.get("extensions", []):
                if target_file.endswith(ext):
                    inferred_tech = tech_key
                    break

        # Compute required_skill label for this task
        inferred_label = TECH_STACK_SIGNALS.get(inferred_tech, {}).get("label", primary_label) if inferred_tech else primary_label
        task["required_skill"] = inferred_label or "General"

        # Determine skill_flag based on whether missing covers this task's tech
        parts = [p.lower() for p in (inferred_label.split(" / ") if inferred_label else [])]
        has_gap = any(p in missing_lower or any(p in m for m in missing_lower) for p in parts)
        task["skill_flag"] = has_gap
        if has_gap:
            task["skill_gap_message"] = (
                f"⚠️ Required skill '{inferred_label}' — no registered agent found. "
                f"Add a '{TECH_STACK_SIGNALS.get(inferred_tech, {}).get('agent_template', inferred_label)}' agent."
            )
        else:
            task["skill_gap_message"] = None

    return tasks




# ---------------------------------------------------------------------------
# Repo Inventory
# ---------------------------------------------------------------------------

def get_brownfield_repo_inventory(container_name: str) -> Dict[str, Any]:
    """
    Scan /workspace in the container and return a structured inventory of
    existing files grouped by directory.
    """
    try:
        exclude_args = []
        for d in INVENTORY_EXCLUDE_DIRS:
            exclude_args += ["-name", d, "-prune", "-o"]
        exclude_args += ["-type", "f", "-print"]

        find_cmd = ["docker", "exec", container_name, "find", "/workspace"] + exclude_args
        result = subprocess.run(find_cmd, capture_output=True, text=True, timeout=60)

        raw_files = [
            line.strip().replace("/workspace/", "").strip("/")
            for line in result.stdout.splitlines()
            if line.strip() and line.strip() != "/workspace"
        ]

        relevant_files = [
            f for f in raw_files
            if any(f.lower().endswith(ext) for ext in INVENTORY_EXTENSIONS)
        ]

        groups: Dict[str, List[str]] = {}
        for f in relevant_files:
            parts = f.split("/")
            top = parts[0] if len(parts) > 1 else "."
            groups.setdefault(top, []).append(f)

        lines = [
            f"EXISTING REPOSITORY FILE INVENTORY ({len(relevant_files)} files):",
            "=" * 60,
        ]
        for group, files in sorted(groups.items()):
            lines.append(f"")
            lines.append(f"[{group}/]")
            for fp in sorted(files)[:50]:
                lines.append(f"  {fp}")
            if len(files) > 50:
                lines.append(f"  ... and {len(files) - 50} more files")

        return {
            "success": True,
            "file_count": len(relevant_files),
            "inventory_text": "\n".join(lines),
            "file_list": relevant_files,
        }
    except Exception as exc:
        logger.error(f"Repo inventory scan failed: {exc}")
        return {
            "success": False,
            "error": str(exc),
            "file_count": 0,
            "inventory_text": "",
            "file_list": [],
        }


# ---------------------------------------------------------------------------
# Git Setup for Brownfield
# ---------------------------------------------------------------------------

def setup_brownfield_git(
    container_name: str,
    source_repo_url: str,
    target_repo_url: str,
    token: str,
    base_branch: str,
    task_id: str,
    target_repo_token: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Clone the existing source repo at base_branch and create a feature branch.
    Then, set the origin to the target_repo_url for pushing.
    """
    utils = _get_agent_service_utils()
    build_git_auth_url = utils["build_git_auth_url"]
    get_git_auth_config = utils["get_git_auth_config"]
    verify_container_toolchain = utils["verify_container_toolchain"]

    try:
        toolchain_result = verify_container_toolchain(container_name)
        if not toolchain_result.get("success"):
            return {
                "success": False,
                "error": toolchain_result.get("error", "runtime toolchain verification failed"),
            }

        for cmd in [
            ["git", "config", "--global", "user.email", "agent@dsuite.ai"],
            ["git", "config", "--global", "user.name", "DSuite Agent"],
        ]:
            subprocess.run(
                ["docker", "exec", container_name] + cmd,
                capture_output=True, text=True, timeout=10,
            )

        if token and ("dev.azure.com" in source_repo_url or "visualstudio.com" in source_repo_url):
            subprocess.run(
                ["docker", "exec", container_name, "git", "config", "--global",
                 "credential.helper", "store"],
                capture_output=True, text=True, timeout=10,
            )

        source_auth_url = build_git_auth_url(source_repo_url, token)
        auth_config = get_git_auth_config(source_repo_url, token)

        subprocess.run(
            ["docker", "exec", container_name, "sh", "-c",
             "rm -rf /workspace/* /workspace/.* 2>/dev/null || true"],
            capture_output=True, text=True, timeout=10,
        )

        clone_cmd = ["docker", "exec", container_name, "git"]
        clone_cmd.extend(auth_config)
        clone_cmd.extend(["clone", "--branch", base_branch, "--single-branch", source_auth_url, "/workspace"])

        clone = subprocess.run(clone_cmd, capture_output=True, text=True, timeout=300)
        if clone.returncode != 0:
            return {
                "success": False,
                "error": (
                    f"BROWNFIELD: Failed to clone branch '{base_branch}' from source repo. "
                    f"Ensure the branch exists on the remote. "
                    f"Git error: {clone.stderr.strip()}"
                ),
            }

        if target_repo_url and target_repo_url != source_repo_url:
            push_token = target_repo_token or token
            target_auth_url = build_git_auth_url(target_repo_url, push_token)
            subprocess.run(
                ["docker", "exec", "-w", "/workspace", container_name,
                 "git", "remote", "set-url", "origin", target_auth_url],
                capture_output=True, text=True, timeout=10,
            )
        elif token:
            subprocess.run(
                ["docker", "exec", "-w", "/workspace", container_name,
                 "git", "remote", "set-url", "origin", source_auth_url],
                capture_output=True, text=True, timeout=10,
            )

        feature_branch = f"{BROWNFIELD_FEATURE_BRANCH_PREFIX}{task_id.lower().replace('_', '-')}"
        checkout = subprocess.run(
            ["docker", "exec", "-w", "/workspace", container_name,
             "git", "checkout", "-b", feature_branch],
            capture_output=True, text=True, timeout=30,
        )
        if checkout.returncode != 0:
            return {
                "success": False,
                "error": f"Failed to create feature branch '{feature_branch}': {checkout.stderr}",
            }

        logger.info(
            f"[BROWNFIELD] Cloned '{base_branch}' from source and created feature branch '{feature_branch}' for target"
        )
        return {
            "success": True,
            "feature_branch": feature_branch,
            "base_branch": base_branch,
        }
    except Exception as exc:
        logger.error(f"[BROWNFIELD] Git setup failed: {exc}")
        return {"success": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# Brownfield Prompt Builder
# ---------------------------------------------------------------------------

def build_brownfield_agent_prompt_prefix(
    task: Dict[str, Any],
    inventory: Dict[str, Any],
    base_branch: str,
    feature_branch: str,
) -> str:
    """Build the BROWNFIELD MODE prompt prefix for the agent AI."""
    task_id = task.get("task_id") or task.get("external_task_id") or "TASK-???"
    task_title = task.get("title") or task.get("taskName") or "Unknown Task"
    task_desc = task.get("description") or ""
    target_file = task.get("target_file") or ""
    change_type = task.get("change_type") or "modify"

    inventory_text = inventory.get("inventory_text", "")
    file_count = inventory.get("file_count", 0)

    target_info = ""
    if target_file:
        target_info = f"\nPRIMARY TARGET FILE: /workspace/{target_file}\nChange Type: {change_type.upper()}\n"

    inv_section = inventory_text if file_count > 0 else "Repository inventory unavailable - scan /workspace manually: find /workspace -type f | head -100"

    return f"""
=== BROWNFIELD MODE - ACTIVE ===

You are operating in BROWNFIELD mode. This is an EXISTING application.

CRITICAL RULES:
1. DO NOT create files from scratch unless they are genuinely NEW files required
2. ALWAYS read the existing file content FIRST: cat /workspace/<filepath>
3. Make SURGICAL, TARGETED changes only - preserve all unrelated existing code
4. DO NOT overwrite configuration files (like pom.xml, package.json, build.gradle) with generic template files from scratch. Keep existing properties (e.g., Spring Boot versions, Java versions, dependency configurations, Sonar/Lombok/OpenFeign blocks) completely intact. Append/edit dependencies surgically.
5. After changes run existing tests if available
6. Push to branch: {feature_branch} (NOT to {base_branch})

CURRENT TASK:
Task ID: {task_id}
Title: {task_title}
Description: {task_desc}
{target_info}

GIT CONTEXT:
Base Branch (cloned from): {base_branch}
Your Working Branch: {feature_branch}
All commits and pushes go to: {feature_branch}

{inv_section}

WORKFLOW:
1. Read the target file(s): cat /workspace/<path>
2. Understand the existing implementation
3. Make minimal targeted changes
4. Stage, commit, and push: git add -A && git commit -m "feat({task_id}): <description>" && git push origin {feature_branch}

=== END BROWNFIELD CONTEXT ===
"""


# ---------------------------------------------------------------------------
# Container Management
# ---------------------------------------------------------------------------

async def provision_brownfield_container(
    agent_id: str,
    project_token: str,
) -> Dict[str, Any]:
    """Create an ephemeral Docker container for a brownfield agent task."""
    utils = _get_agent_service_utils()
    ensure_agent_runtime_image = utils["ensure_agent_runtime_image"]
    AGENT_RUNTIME_IMAGE = utils["AGENT_RUNTIME_IMAGE"]

    container_name = f"{BROWNFIELD_CONTAINER_PREFIX}{project_token[:12]}_{agent_id}_{uuid.uuid4().hex[:6]}"

    try:
        image_result = await asyncio.to_thread(ensure_agent_runtime_image)
        if not image_result.get("success"):
            return {
                "success": False,
                "error": f"Agent runtime image not available: {image_result.get('error')}",
            }

        run_result = subprocess.run(
            [
                "docker", "run", "-d",
                "--name", container_name,
                "--memory", "2g",
                "--cpus", "1.5",
                AGENT_RUNTIME_IMAGE,
                "sleep", "7200",
            ],
            capture_output=True, text=True, timeout=60,
        )

        if run_result.returncode != 0:
            return {
                "success": False,
                "error": f"Docker run failed: {run_result.stderr.strip()}",
            }

        return {"success": True, "container_name": container_name}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def cleanup_brownfield_container(container_name: str) -> None:
    """Remove a brownfield agent container."""
    try:
        subprocess.run(
            ["docker", "rm", "-f", container_name],
            capture_output=True, text=True, timeout=30,
        )
    except Exception as exc:
        logger.warning(f"[BROWNFIELD] Container cleanup failed for {container_name}: {exc}")



# ---------------------------------------------------------------------------
# Main Brownfield Agent Execution
# ---------------------------------------------------------------------------

async def run_brownfield_agent(
    agent_id: str,
    project_token: str,
    task_token: Optional[str],
    task: Dict[str, Any],
    git_repo_url: str,
    git_token: str,
    base_branch: str,
    agent_output_log: Optional[List[Dict[str, Any]]] = None,
    target_repo_url: Optional[str] = None,
    target_repo_token: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Execute a single brownfield task using an ephemeral Docker container.

    Flow:
    1. Provision a fresh container
    2. Clone the EXISTING repo at base_branch (user-specified)
    3. Create feature branch  dsuite/change-<task_id>
    4. Scan repo file inventory for context
    5. Inject brownfield prompt prefix into task description
    6. Call the existing agent_service.run_agent() with force_branch
    7. Cleanup container

    Integration note:
        This calls agent_service.run_agent() directly rather than any
        internal helper, as run_agent() is the canonical entry point that
        handles AI loop, self-healing, commit, push, and task status updates.
        The brownfield setup (clone + feature branch) happens BEFORE hand-off
        so run_agent sees an already-prepared /workspace with the feature branch
        checked out.

    Args:
        agent_id: The agent ID from the project agent registry
        project_token: Project token for state management
        task_token: Optional NXDune task token
        task: Task dict — should include task_id, description, target_file, change_type
        git_repo_url: Remote repository URL
        git_token: PAT or OAuth token
        base_branch: Existing branch to clone (user-specified in Dashboard)
        agent_output_log: List to append log entries to (in-place mutation)

    Returns:
        {"success": bool, "feature_branch": str, "error": str (on failure)}
    """
    import datetime as _dt

    log = agent_output_log if isinstance(agent_output_log, list) else []

    def _log(message: str, log_type: str = "info"):
        log.append({
            "time": _dt.datetime.utcnow().isoformat(),
            "type": log_type,
            "message": message,
        })
        logger.info(f"[BROWNFIELD][{agent_id}] {message}")

    task_id = task.get("task_id") or task.get("external_task_id") or "UNKNOWN"

    _log(f"BROWNFIELD MODE — Starting task {task_id}")
    _log(f"  Repo: {git_repo_url}  Branch: {base_branch}")

    # ── 1. Provision container ────────────────────────────────────────────────
    container_result = await provision_brownfield_container(agent_id, project_token)
    if not container_result["success"]:
        _log(f"Container provision failed: {container_result['error']}", "error")
        return {"success": False, "error": container_result["error"]}

    container_name = container_result["container_name"]
    _log(f"Container provisioned: {container_name}")

    try:
        # ── 2+3. Clone existing branch and create feature branch ──────────────
        _log(f"Cloning '{base_branch}' from remote...")
        git_result = await asyncio.to_thread(
            setup_brownfield_git,
            container_name, git_repo_url, target_repo_url, git_token, base_branch, task_id, target_repo_token,
        )
        if not git_result["success"]:
            _log(f"Git setup failed: {git_result['error']}", "error")
            return {"success": False, "error": git_result["error"]}

        feature_branch = git_result["feature_branch"]
        _log(f"Cloned '{base_branch}' -> feature branch: '{feature_branch}'")

        # ── 4. Scan existing repo files for agent context ────────────────────
        _log("Scanning existing repository structure...")
        inventory = await asyncio.to_thread(get_brownfield_repo_inventory, container_name)
        _log(f"Repository scanned: {inventory['file_count']} files found")

        # ── 5. Build brownfield prompt prefix and inject into task description ─
        prompt_prefix = build_brownfield_agent_prompt_prefix(
            task=task,
            inventory=inventory,
            base_branch=base_branch,
            feature_branch=feature_branch,
        )

        # Build enriched task: existing description gets the brownfield context prefix
        brownfield_task = dict(task)
        existing_desc = brownfield_task.get("description") or ""
        brownfield_task["description"] = f"{prompt_prefix}\n\n{existing_desc}"
        brownfield_task["_brownfield_mode"] = True
        brownfield_task["_feature_branch"] = feature_branch
        brownfield_task["_base_branch"] = base_branch

        # ── 6. Call the canonical run_agent() with the pre-set container ─────
        # Import lazily to avoid circular imports at module load time
        import agent_service as _as

        _log(f"Handing off to agent_service.run_agent() on branch '{feature_branch}'")

        result = await _as.run_agent(
            agent_id=agent_id,
            git_repo_url=git_repo_url,
            git_token=git_token,
            assigned_task=brownfield_task,
            project_token=project_token,
            task_token=task_token,
            force_branch=feature_branch,
            ignore_running_check=True,
        )

        if result.get("success"):
            _log(f"Task {task_id} completed successfully on branch '{feature_branch}'")
        else:
            _log(f"Task {task_id} failed: {result.get('error', 'unknown error')}", "error")

        return {
            **result,
            "feature_branch": feature_branch,
            "base_branch": base_branch,
        }

    except Exception as exc:
        _log(f"Brownfield execution error: {exc}", "error")
        return {"success": False, "error": str(exc)}

    finally:
        # ── 7. Cleanup container ──────────────────────────────────────────────
        _log(f"Cleaning up container {container_name}")
        cleanup_brownfield_container(container_name)




BROWNFIELD_GENERATION_PROMPT = """
You are generating tasks for a BROWNFIELD project - enhancements, modifications, and bug fixes on top of an EXISTING repository.

CRITICAL ARCHITECTURAL CONSTRAINTS:
1. ❌ DO NOT generate any project initialization, scaffold, or setup tasks (no "Project Bootstrap", "Navigation Shell", "Create package.json").
2. ❌ DO NOT generate greenfield folders or blank projects.
3. ❌ Every task must operate on top of the existing codebase. The agent will checkout the user branch, modify code, push to a task branch, and merge to agent/integration.
4. The FIRST task MUST be: "Repo Analysis and Change Planning" (task_id: TASK-REPO-ANALYSIS).
5. All subsequent tasks must specify the exact `target_file` (relative path from repository root) and `change_type` ("modify" | "add" | "delete" | "refactor").
6. You MUST assign every task to one of the exact Sprints listed in the "AVAILABLE SPRINTS" section. Do NOT invent new sprint names, and do NOT add any custom suffixes to the sprint names. Group the tasks into the provided Sprints logically.

FIRST TASK FORMAT (always include this):
{
  "task_id": "TASK-REPO-ANALYSIS",
  "taskName": "Repo Analysis and Change Planning",
  "description": "Clone the existing repository. Analyze the full codebase structure. Map each requirement from the change request to specific existing files and functions that must be modified. Produce a structured change impact report listing: (1) files to modify, (2) files to add, (3) potential regression risks.",
  "task_type": "analysis",
  "target_file": null,
  "change_type": "analyze",
  "priority": "critical",
  "task_wallet": 2,
  "sprint": "Sprint 1 - Repo Analysis & Change Mapping",
  "checklist": [
    "Clone repository at user-specified branch",
    "Scan all existing files and directories",
    "Map each requirement to affected file(s)",
    "Identify regression risks",
    "Document change impact report"
  ]
}

CHANGE TASK FORMAT (for each requirement/user story/bug fix):
{
  "task_id": "TASK-01",
  "taskName": "<concise title describing the specific change>",
  "description": "BROWNFIELD CHANGE:\\n\\nTarget File: <exact relative path>\\nChange Type: MODIFY|ADD|DELETE\\n\\nExisting Behavior: <what the code currently does in the repo>\\nRequired Change: <exactly what needs to change and why>\\n\\nAgent Steps:\\n1. Read existing file: cat /workspace/<path>\\n2. Make surgical code updates to satisfy the requirements\\n3. Do NOT rewrite the entire file; keep all existing logic intact except what is requested\\n\\nAcceptance Criteria: <how to verify the change is correct>",
  "task_type": "development",
  "target_file": "<relative path from repo root>",
  "change_type": "modify|add|delete|refactor",
  "priority": "high|medium|low",
  "sprint": "<Exact Sprint Name from the AVAILABLE SPRINTS list>"
}

IMPORTANT: Vague tasks cause agent failures. Be precise. Specify exact files and directories to inspect and modify based on the provided impact analysis.
"""


def get_brownfield_generation_context(
    project_context: Dict[str, Any],
    repo_structure: Optional[str] = None,
) -> str:
    """Build the brownfield context block for the task generation LLM prompt."""
    lines = [
        "PROJECT MODE: BROWNFIELD (Changes to Existing Application)",
        "=" * 60,
        "",
        "GENERATION RULES:",
        "- First task MUST be TASK-REPO-ANALYSIS",
        "- No scaffold/init/setup tasks",
        "- Every task specifies target_file and change_type",
        "- Descriptions tell agents WHAT file to change and HOW precisely",
        "",
    ]

    if repo_structure:
        lines.extend([
            "EXISTING REPOSITORY STRUCTURE (use these paths in target_file):",
            "-" * 40,
            repo_structure[:3000],
            "",
        ])

    analysis = project_context.get("analysis_summary") or project_context.get("analysis") or ""
    if analysis:
        lines.extend([
            "CHANGE REQUEST / REQUIREMENTS:",
            "-" * 40,
            str(analysis)[:2000],
            "",
        ])

    return "\n".join(lines)


def is_brownfield_project(project_type: Optional[str]) -> bool:
    """Check if a project type requires brownfield agent execution."""
    if not project_type:
        return False
    return str(project_type).lower().strip() == "brownfield"
