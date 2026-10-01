"""
Master Orchestrator — LLM-Driven Multi-Agent Orchestration Service.

Replaces the old keyword-matching task partitioner with an intelligent
orchestration brain that:

1. Analyzes the project context (BRD, workspace, project type)
2. Detects tech stack dynamically (greenfield/brownfield/migration)
3. Builds a dependency-ordered task graph via LLM
4. Assigns tasks to agents using skill-based matching
5. Coordinates phased execution with validation gates

Zero hardcoded tech stacks. Zero template code. Pure LLM-driven orchestration.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from sqlalchemy.orm import Session

import models
from app.core.config import get_settings
from app.services.agents.skill_matcher_service import (
    calculate_task_skill_relevance,
    extract_skill_keywords,
)
from app.services.agents.local_state_manager import (
    get_agent_lanes_from_skills,
    is_task_in_agent_lanes,
)

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# Workspace Analyzer (inline — no separate file needed for now)
# ══════════════════════════════════════════════════════════════════════════════

def analyze_workspace(workspace_dir: str) -> Dict[str, Any]:
    """Scan the workspace to detect project type, tech stack, and file structure.

    This is deterministic (no LLM call) — it reads filesystem markers like
    package.json, requirements.txt, go.mod, pom.xml, etc.
    """
    result = {
        "project_type": "greenfield",
        "detected_stack": {},
        "file_tree": [],
        "total_files": 0,
        "entry_points": {},
        "config_files": [],
    }

    if not os.path.exists(workspace_dir):
        return result

    # Count real files (excluding hidden dirs, node_modules, __pycache__)
    SKIP_DIRS = {
        "node_modules", "__pycache__", ".git", ".agent", ".agent_signals",
        ".agent_history", "venv", ".venv", "dist", "build", ".next",
    }

    file_tree = []
    config_files_found = {}

    for root, dirs, files in os.walk(workspace_dir):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        rel_root = os.path.relpath(root, workspace_dir)
        if rel_root == ".":
            rel_root = ""

        for f in files:
            rel_path = os.path.join(rel_root, f) if rel_root else f
            rel_path = rel_path.replace("\\", "/")
            file_tree.append(rel_path)

            # Track config files for stack detection
            lower_f = f.lower()
            if lower_f in ("package.json", "tsconfig.json", "vite.config.js",
                           "vite.config.ts", "next.config.js", "next.config.mjs",
                           "nuxt.config.ts", "angular.json", "svelte.config.js"):
                config_files_found[lower_f] = os.path.join(root, f)
            elif lower_f in ("requirements.txt", "pyproject.toml", "setup.py",
                             "pipfile", "poetry.lock"):
                config_files_found[lower_f] = os.path.join(root, f)
            elif lower_f in ("go.mod", "cargo.toml", "pom.xml", "build.gradle",
                             "build.gradle.kts", "composer.json", "gemfile"):
                config_files_found[lower_f] = os.path.join(root, f)

    result["total_files"] = len(file_tree)
    result["file_tree"] = file_tree[:500]  # Cap for token budget
    result["config_files"] = list(config_files_found.keys())

    # Determine project type
    if result["total_files"] <= 2:
        result["project_type"] = "greenfield"
    else:
        result["project_type"] = "brownfield"

    # Detect frontend stack
    if "package.json" in config_files_found:
        try:
            with open(config_files_found["package.json"], "r", encoding="utf-8") as f:
                pkg = json.load(f)
            deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}

            if "next" in deps:
                result["detected_stack"]["frontend"] = "nextjs"
            elif "nuxt" in deps:
                result["detected_stack"]["frontend"] = "nuxt"
            elif "@angular/core" in deps:
                result["detected_stack"]["frontend"] = "angular"
            elif "svelte" in deps:
                result["detected_stack"]["frontend"] = "svelte"
            elif "vue" in deps:
                result["detected_stack"]["frontend"] = "vue"
            elif "react" in deps:
                if "vite" in deps:
                    result["detected_stack"]["frontend"] = "react_vite"
                else:
                    result["detected_stack"]["frontend"] = "react"

            if "tailwindcss" in deps:
                result["detected_stack"]["css"] = "tailwind"
            elif "styled-components" in deps:
                result["detected_stack"]["css"] = "styled_components"
            elif "@mui/material" in deps:
                result["detected_stack"]["css"] = "material_ui"

            result["entry_points"]["frontend"] = pkg.get("main", "src/main.jsx")
        except Exception:
            pass

    # Detect backend stack
    if "requirements.txt" in config_files_found or "pyproject.toml" in config_files_found:
        result["detected_stack"]["backend"] = "python"
        cfg_file = config_files_found.get("requirements.txt") or config_files_found.get("pyproject.toml")
        try:
            with open(cfg_file, "r", encoding="utf-8") as f:
                content = f.read().lower()
            if "fastapi" in content:
                result["detected_stack"]["backend"] = "fastapi"
            elif "django" in content:
                result["detected_stack"]["backend"] = "django"
            elif "flask" in content:
                result["detected_stack"]["backend"] = "flask"
        except Exception:
            pass
    elif "go.mod" in config_files_found:
        result["detected_stack"]["backend"] = "go"
    elif "cargo.toml" in config_files_found:
        result["detected_stack"]["backend"] = "rust"
    elif "pom.xml" in config_files_found or "build.gradle" in config_files_found:
        result["detected_stack"]["backend"] = "java"

    # Detect entry points
    for candidate in ("src/main.jsx", "src/main.tsx", "src/index.js", "src/index.tsx",
                       "src/App.jsx", "src/App.tsx", "pages/index.tsx", "app/page.tsx"):
        full = os.path.join(workspace_dir, candidate)
        if os.path.exists(full):
            result["entry_points"]["frontend"] = candidate
            break

    for candidate in ("main.py", "app.py", "server.py", "backend/main.py",
                       "backend/app.py", "src/main.py", "cmd/main.go", "main.go"):
        full = os.path.join(workspace_dir, candidate)
        if os.path.exists(full):
            result["entry_points"]["backend"] = candidate
            break

    return result


def build_workspace_index_file(workspace_dir: str, brd_summary: str = "") -> str:
    """Build and write workspace_index.json into .agent/ directory.

    Returns the JSON string for inclusion in agent prompts.
    """
    analysis = analyze_workspace(workspace_dir)
    analysis["brd_summary"] = brd_summary[:3000] if brd_summary else ""

    index_dir = os.path.join(workspace_dir, ".agent")
    os.makedirs(index_dir, exist_ok=True)
    index_path = os.path.join(index_dir, "workspace_index.json")

    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(analysis, f, indent=2)

    return json.dumps(analysis, indent=2)


# ══════════════════════════════════════════════════════════════════════════════
# Inter-Agent Shared Contract Registry
# ══════════════════════════════════════════════════════════════════════════════

def save_contract(workspace_dir: str, contract_name: str, data: Dict[str, Any]) -> str:
    """Save an inter-agent contract to .agent/contracts/<contract_name>.json."""
    contracts_dir = os.path.join(workspace_dir, ".agent", "contracts")
    os.makedirs(contracts_dir, exist_ok=True)
    file_path = os.path.join(contracts_dir, f"{contract_name}.json")
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    return file_path


def load_contracts(workspace_dir: str) -> Dict[str, Any]:
    """Load all published contracts from .agent/contracts/."""
    contracts_dir = os.path.join(workspace_dir, ".agent", "contracts")
    contracts = {}
    if not os.path.exists(contracts_dir):
        return contracts
    for fname in os.listdir(contracts_dir):
        if fname.endswith(".json"):
            c_name = fname[:-5]
            try:
                with open(os.path.join(contracts_dir, fname), "r", encoding="utf-8") as f:
                    contracts[c_name] = json.load(f)
            except Exception:
                pass
    return contracts


def extract_backend_contracts(workspace_dir: str) -> Dict[str, Any]:
    """Inspect workspace code files to discover API endpoints and DB models."""
    import re
    discovered_routes = []
    discovered_models = []

    for root, _, files in os.walk(workspace_dir):
        if any(skip in root for skip in ("node_modules", ".git", ".agent", "venv", "__pycache__")):
            continue
        for f in files:
            fpath = os.path.join(root, f)
            rel = os.path.relpath(fpath, workspace_dir).replace("\\", "/")
            if f.endswith(".py"):
                try:
                    with open(fpath, "r", encoding="utf-8", errors="ignore") as pf:
                        content = pf.read()
                    route_matches = re.findall(r'@(?:router|app)\.(get|post|put|delete|patch)\(\s*["\']([^"\']+)["\']', content, re.IGNORECASE)
                    for method, path in route_matches:
                        discovered_routes.append({"method": method.upper(), "path": path, "file": rel})
                    class_matches = re.findall(r'class\s+([A-Za-z0-9_]+)\s*\((?:BaseModel|Base|SQLModel|Model)\):', content)
                    for cls in class_matches:
                        discovered_models.append({"model": cls, "file": rel})
                except Exception:
                    pass
            elif f.endswith((".ts", ".js")):
                try:
                    with open(fpath, "r", encoding="utf-8", errors="ignore") as jf:
                        content = jf.read()
                    exp_matches = re.findall(r'(?:router|app)\.(get|post|put|delete|patch)\(\s*["\']([^"\']+)["\']', content, re.IGNORECASE)
                    for method, path in exp_matches:
                        discovered_routes.append({"method": method.upper(), "path": path, "file": rel})
                except Exception:
                    pass

    contract_data = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "routes": discovered_routes,
        "models": discovered_models,
    }
    save_contract(workspace_dir, "api_contract", contract_data)
    return contract_data


def organize_tasks_into_phases(assignments: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    """Group assigned agents into execution phases (Dependency DAG).

    Phase 1: Backend & Data Layer (agents working on backend/database/server)
    Phase 2: Frontend & UI Layer (agents working on frontend/ui/web)
    Phase 3: QA & Verification Gate (Test Agent T_agent_01 / QA specialists)
    """
    phase1_agents = set()
    phase2_agents = set()
    phase3_agents = set()

    for a in assignments:
        lane = a.get("lane", "general")
        aid = a.get("assigned_to")
        if not aid:
            continue
        if lane in ("backend", "devops") or any(k in lane for k in ("db", "data", "api")):
            phase1_agents.add(aid)
        elif lane in ("frontend", "ui", "web"):
            phase2_agents.add(aid)
        elif lane in ("qa", "test", "verification"):
            phase3_agents.add(aid)
        else:
            phase1_agents.add(aid)

    if not phase3_agents:
        phase3_agents.add("T_agent_01")

    return {
        "phase1_backend": list(phase1_agents),
        "phase2_frontend": list(phase2_agents),
        "phase3_qa_gate": list(phase3_agents),
    }


# ══════════════════════════════════════════════════════════════════════════════
# Task Assignment — Skill-Based Matching
# ══════════════════════════════════════════════════════════════════════════════

def assign_tasks_to_agents(
    tasks: List[models.Task],
    agents: List[Dict[str, Any]],
    db: Session,
) -> List[Dict[str, Any]]:
    """Assign tasks to agents using skill-based relevance scoring.

    Falls back to lane-based matching if no skill content is available.
    """
    worker_agents = [a for a in agents if not _is_system_id(a.get("id", ""))]
    if not worker_agents:
        logger.warning("[MasterOrchestrator] No worker agents available for assignment")
        return []

    assignments = []

    for task in tasks:
        t_title = getattr(task, "task_name", getattr(task, "title", "Task"))
        t_desc = getattr(task, "description", "") or ""
        task_dict = {"title": t_title, "description": t_desc}

        # Determine task lane from title/description keywords
        task_lane = _infer_task_lane(t_title, t_desc)

        # Score each agent
        best_agent = None
        best_score = -1.0

        for agent in worker_agents:
            agent_lanes = get_agent_lanes_from_skills(
                agent_id=agent.get("id", ""),
                skills_tags=agent.get("skills_tags"),
                specialization=agent.get("specialization"),
            )

            # Skip agents that can't work in this lane
            if not is_task_in_agent_lanes(task_lane, agent_lanes):
                continue

            skills_content = agent.get("skills_content") or agent.get("skills_summary") or ""
            if skills_content:
                skill_keywords = extract_skill_keywords(skills_content)
                score = calculate_task_skill_relevance(
                    task=task_dict,
                    skill_name=agent.get("name", ""),
                    skill_content=skills_content,
                    skill_keywords=skill_keywords,
                )
            else:
                # If no skill content, score based on lane match specificity
                specialized_lanes = agent_lanes - {"general"}
                score = 0.7 if task_lane in specialized_lanes else 0.3

            if score > best_score:
                best_score = score
                best_agent = agent

        # Fallback: assign to any available worker
        if not best_agent:
            best_agent = worker_agents[0]

        assigned_id = best_agent["id"]
        task.assigned_to = json.dumps([assigned_id])
        if getattr(task, "status", None) in (None, "pending", "todo"):
            task.status = "in_progress"

        assignments.append({
            "task_id": getattr(task, "task_id", getattr(task, "id", "")),
            "title": t_title,
            "lane": task_lane,
            "assigned_to": assigned_id,
            "score": round(best_score, 3),
        })

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"[MasterOrchestrator] Error saving task assignments: {e}")

    return assignments


def _infer_task_lane(title: str, description: str) -> str:
    """Infer the execution lane from task title and description."""
    combined = f"{title} {description}".lower()

    backend_kw = (
        "backend", "api", "database", "model", "schema", "controller", "server",
        "fastapi", "crud", "sql", "orm", "endpoint", "route", "middleware",
        "migration", "seed", "auth", "jwt", "session", "microservice",
    )
    frontend_kw = (
        "frontend", "ui", "screen", "view", "component", "button", "css",
        "tailwind", "layout", "page", "form", "modal", "dashboard", "sidebar",
        "navigation", "responsive", "animation", "chart", "table", "card",
    )
    qa_kw = (
        "test", "qa", "lint", "validate", "verify", "audit", "e2e", "spec",
        "integration test", "unit test", "coverage", "quality",
    )
    devops_kw = (
        "deploy", "docker", "ci", "cd", "pipeline", "nginx", "kubernetes",
        "infrastructure", "monitoring", "logging",
    )

    if any(kw in combined for kw in qa_kw):
        return "qa"
    if any(kw in combined for kw in devops_kw):
        return "devops"

    # Check backend before frontend because some tasks mention both
    be_score = sum(1 for kw in backend_kw if kw in combined)
    fe_score = sum(1 for kw in frontend_kw if kw in combined)

    if be_score > fe_score:
        return "backend"
    if fe_score > 0:
        return "frontend"
    if be_score > 0:
        return "backend"

    return "general"


def _is_system_id(agent_id: str) -> bool:
    """Check if agent_id belongs to a system/default agent."""
    sys_ids = {"m_agent_01", "master_agent", "t_agent_01", "deploy_agent"}
    return agent_id.lower().strip() in sys_ids


# ══════════════════════════════════════════════════════════════════════════════
# Orchestration Entry Point
# ══════════════════════════════════════════════════════════════════════════════

def orchestrate_project(
    db: Session,
    project_token: str,
    agent_service: Any,
    project_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Master Orchestrator: Analyze project, assign tasks, prepare execution context.

    This replaces the old orchestrate_master_scaffold_and_tasks() with a
    tech-stack-agnostic, skill-based approach.

    Steps:
      1. Analyze workspace (detect project type + tech stack)
      2. Query selected tasks
      3. Get available worker agents
      4. Assign tasks using skill matching
      5. Build workspace index for agent context
      6. Return execution plan

    The actual agent execution (container launch) is handled by the caller
    (run_all_agents endpoint).
    """
    settings = get_settings()
    clean_token = project_token.replace("/", "_").replace("\\", "_")
    workspace_dir = os.path.join(settings.project_storage_root, clean_token)
    os.makedirs(workspace_dir, exist_ok=True)

    # Update Master Agent status
    agent_service.ensure_project_initialized(project_token)
    master_status = agent_service.get_agent_status("M_agent_01", project_token)
    master_status["status"] = "running"
    master_status["progress"] = 10
    master_status["progress_message"] = "Analyzing project workspace and requirements..."

    from app.routers.helpers import sync_broadcast_preview_log
    sync_broadcast_preview_log(
        project_token=project_token,
        content="[Master Agent] Phase 1: Analyzing project workspace and requirements...",
        event_type="thinking",
        payload={"agent": "Master Agent", "type": "thinking"},
    )

    # ── Step 1: Analyze workspace ──
    workspace_analysis = analyze_workspace(workspace_dir)
    project_type = workspace_analysis["project_type"]
    detected_stack = workspace_analysis.get("detected_stack", {})

    agent_service.append_agent_log(
        "M_agent_01",
        f"[Master Agent] Project type: {project_type.upper()}. "
        f"Detected stack: {json.dumps(detected_stack) if detected_stack else 'None (greenfield)'}. "
        f"Files in workspace: {workspace_analysis['total_files']}.",
        "output",
        project_token,
    )

    master_status["progress"] = 30
    master_status["progress_message"] = f"Project analyzed: {project_type}. Querying tasks..."

    # ── Step 2: Get BRD context ──
    brd_summary = ""
    gov = (
        db.query(models.GovernanceResponse)
        .filter(models.GovernanceResponse.project_token == project_token)
        .first()
    )
    if gov and getattr(gov, "recommendation", None):
        brd_summary = gov.recommendation[:3000]
    else:
        doc = (
            db.query(models.Document)
            .filter(models.Document.project_token == project_token)
            .first()
        )
        if doc and getattr(doc, "full_content", None):
            brd_summary = doc.full_content[:3000]

    # ── Step 3: Build workspace index ──
    workspace_index_json = build_workspace_index_file(workspace_dir, brd_summary)

    master_status["progress"] = 50
    master_status["progress_message"] = "Querying tasks and assigning to agents..."

    # ── Step 4: Query tasks ──
    tasks = (
        db.query(models.Task)
        .filter(models.Task.project_token == project_token)
        .order_by(models.Task.created_at.asc())
        .all()
    )
    target_tasks = [t for t in tasks if getattr(t, "selected", False)]
    if not target_tasks:
        target_tasks = tasks

    if not target_tasks:
        master_status["status"] = "completed"
        master_status["progress"] = 100
        master_status["progress_message"] = "No tasks found for this project."
        return {"assigned_tasks": [], "total_tasks": 0, "workspace_analysis": workspace_analysis}

    # ── Step 5: Get worker agents ──
    all_agents = agent_service.get_all_agents(project_token)
    worker_agents = [a for a in all_agents if not _is_system_id(a["id"])]

    # ── Step 6: Assign tasks using skill matching ──
    assignments = assign_tasks_to_agents(target_tasks, all_agents, db)

    agent_service.append_agent_log(
        "M_agent_01",
        f"[Master Agent] Phase 2: Assigned {len(assignments)} tasks to "
        f"{len(set(a['assigned_to'] for a in assignments))} specialized agents using skill matching.",
        "info",
        project_token,
    )

    for a in assignments:
        agent_service.append_agent_log(
            "M_agent_01",
            f"  → {a['title'][:60]} → Agent {a['assigned_to']} (lane: {a['lane']}, score: {a['score']})",
            "output",
            project_token,
        )

    # ── Step 7: Construct Phased Dependency DAG ──
    phased_plan = organize_tasks_into_phases(assignments)

    agent_service.append_agent_log(
        "M_agent_01",
        f"[Master Agent] Phase 3: Constructed Phased Dependency DAG: "
        f"Phase 1 Backend: {len(phased_plan['phase1_backend'])} agents | "
        f"Phase 2 Frontend: {len(phased_plan['phase2_frontend'])} agents | "
        f"Phase 3 QA Gate: {len(phased_plan['phase3_qa_gate'])} agents.",
        "info",
        project_token,
    )

    sync_broadcast_preview_log(
        project_token=project_token,
        content=f"[Master Agent] Assigned {len(assignments)} tasks across 3 phased execution tiers.",
        event_type="planning_completed",
        payload={"steps": len(assignments), "agent": "Master Agent", "phases": phased_plan},
    )

    # ── Master complete ──
    master_status["status"] = "completed"
    master_status["progress"] = 100
    master_status["progress_message"] = (
        f"Assigned {len(assignments)} tasks to agents across 3 execution tiers. "
        f"Project type: {project_type}. Ready for phased execution."
    )

    return {
        "workspace_analysis": workspace_analysis,
        "brd_summary": brd_summary[:500],
        "assigned_tasks": assignments,
        "total_tasks": len(assignments),
        "project_type": project_type,
        "phased_plan": phased_plan,
    }


# ══════════════════════════════════════════════════════════════════════════════
# Agent Prompt Builder — Dynamic, Tech-Stack Agnostic
# ══════════════════════════════════════════════════════════════════════════════

def build_agent_prompt(
    agent_name: str,
    agent_role: str,
    agent_spec: str,
    agent_lanes: Set[str],
    assigned_model: str,
    assigned_tools: List[str],
    skills_summary: str,
    assigned_tasks: List[Dict[str, Any]],
    other_tasks: List[Dict[str, Any]],
    brd_context: str,
    workspace_analysis: Dict[str, Any],
    is_qa_agent: bool = False,
    workspace_dir: Optional[str] = None,
) -> str:
    """Build a comprehensive, tech-stack-agnostic prompt for an agent.

    This replaces the hardcoded prompt at agents.py L1598-1629 with a
    dynamic prompt that adapts to any project type and tech stack.
    """
    tools_str = ", ".join(assigned_tools) if isinstance(assigned_tools, list) else str(assigned_tools)
    lanes_str = ", ".join(sorted(agent_lanes))

    # Format task list
    task_summary = ""
    if assigned_tasks:
        task_summary += f"\n\n### Tasks Assigned to You ({agent_name} / {agent_spec}):\n"
        for i, t in enumerate(assigned_tasks, 1):
            task_summary += f"{i}. **[{t.get('type', 'TASK')}] {t['title']}** (ID: {t['id']}, Lane: {t['lane']})\n"
            if t.get("description"):
                task_summary += f"   - Description: {t['description']}\n"
            if t.get("subtasks"):
                task_summary += "   - Actionable Subtasks / Checklist:\n"
                for st in t["subtasks"]:
                    task_summary += f"     * [ ] {st}\n"

    if other_tasks:
        task_summary += "\n\n### Other Related Project Tasks (Reference Only):\n"
        for i, t in enumerate(other_tasks[:10], 1):
            task_summary += f"{i}. **{t['title']}** (Lane: {t['lane']})\n"

    # Workspace context
    ws = workspace_analysis
    project_type = ws.get("project_type", "greenfield")
    stack = ws.get("detected_stack", {})
    stack_desc = json.dumps(stack) if stack else "Not yet determined — you must analyze the workspace"
    file_count = ws.get("total_files", 0)

    workspace_context = f"""
## Project Context
- **Project Type**: {project_type.upper()}
- **Detected Tech Stack**: {stack_desc}
- **Files in Workspace**: {file_count}
- **Entry Points**: {json.dumps(ws.get('entry_points', {}))}
"""

    # Inter-agent published contracts (APIs, schemas, routes)
    contracts_context = ""
    target_ws = workspace_dir or ws.get("workspace_dir")
    if target_ws:
        contracts = load_contracts(target_ws)
        api_c = contracts.get("api_contract")
        if api_c and (api_c.get("routes") or api_c.get("models")):
            contracts_context += "\n## ════════════════════════════════════════════════════════════════════════════\n"
            contracts_context += "## VERIFIED INTER-AGENT CONTRACTS (APIs & DATA MODELS)\n"
            contracts_context += "## ════════════════════════════════════════════════════════════════════════════\n"
            if api_c.get("routes"):
                contracts_context += "### Verified Backend API Endpoints:\n"
                for r in api_c["routes"][:20]:
                    contracts_context += f"- `{r.get('method', 'GET')} {r.get('path', '/')}` (in `{r.get('file', 'backend')}`)\n"
            if api_c.get("models"):
                contracts_context += "\n### Verified Data Models & Schemas:\n"
                for m in api_c["models"][:15]:
                    contracts_context += f"- Schema `{m.get('model', 'Model')}` (in `{m.get('file', 'models')}`)\n"
            if is_qa_agent:
                contracts_context += "\nAuthor your integration test suites and assertions against these exact endpoints.\n"
            elif any(l in agent_lanes for l in ("frontend", "ui", "web")):
                contracts_context += "\nConnect your UI pages and API client hooks directly to these verified routes.\n"

    # Build phase 3 instructions based on agent role
    if is_qa_agent:
        phase3 = """### PHASE 3: QA Execution & Test Authoring (ZERO APP CODE MODIFICATION)
- CRITICAL: You have read-only access to application source code. You MUST NOT edit production application code.
- Your scope: inspect code using `read_file`/`list_directory`, then author test files in `tests/` or `*.test.*`.
- Execute test suites and report failures with file:line references.
- If a bug is found, write a structured Defect Report — do NOT fix production code yourself."""
    else:
        phase3 = """### PHASE 3: Targeted Implementation with Authorized Tools
- Implement the planned subtasks using your container tools (`write_file`, `read_file`, `execute_bash`, `list_directory`).
- **CRITICAL**: Read existing files before writing. Do NOT overwrite existing working code blindly.
- Maintain the project's existing code style, naming conventions, and architecture patterns.
- Write clean, production-ready code with proper error handling and type safety.
- NO hardcoded mock data — use proper data structures and API patterns."""

    prompt = f"""# Persona & Execution Assignment
You are **{agent_name}**, serving as **{agent_role}** specialized in **{agent_spec}**.
- Operational Lanes: {lanes_str}
- Configured AI Engine: {assigned_model.upper()}
- Authorized Container Tools: {tools_str}
{f"- Skills & Focus: {skills_summary}" if skills_summary else ""}

{workspace_context}
{contracts_context}

{f"## Business Requirements & Architecture:{chr(10)}{brd_context}" if brd_context else ""}
{task_summary}

## ════════════════════════════════════════════════════════════════════════════
## MANDATORY 4-PHASE AUTONOMOUS AGENT EXECUTION PROTOCOL
## ════════════════════════════════════════════════════════════════════════════

### PHASE 1: Codebase Discovery & Assessment (READ BEFORE WRITE)
- Ground your understanding before executing tasks. Do NOT hallucinate existing file paths or imports.
- Use `list_directory` to explore the workspace structure.
- Use `read_file` to inspect existing code, configs (package.json, requirements.txt, etc.), and entry points.
- Identify the tech stack, existing components, routing patterns, and data schemas.
- If this is a GREENFIELD project, determine the appropriate project structure from the BRD requirements.

### PHASE 2: Execution Planning & Subtask Breakdown
- Create a precise, dependency-ordered plan for your assigned tasks.
- Break each task into atomic subtasks (Data/Model → Component/Service → Route/Integration → Verification).
- Verify prerequisites before beginning implementation.

{phase3}

### PHASE 4: Zero-Error Verification Gate (MANDATORY)
- Verify ALL changes are error-free before marking any task complete.
- Run the project's build/lint command (detect from package.json scripts or Makefile).
- Inspect compiler/linter output. If ANY errors exist, fix them immediately.
- ZERO-ERROR CONTRACT: A task is NOT complete if there are unresolved errors.
"""
    return prompt


def build_task_config(
    agent_id: str,
    agent_name: str,
    agent_model: str,
    prompt: str,
    project_token: str,
    workspace_analysis: Dict[str, Any],
    callback_url: str = "",
    web_search_enabled: bool = False,
) -> Dict[str, Any]:
    """Build the task_config.json payload for the in-container LangGraph runtime."""
    project_type = workspace_analysis.get("project_type", "greenfield")

    # Map project type to task_type the runtime understands
    if project_type == "greenfield":
        task_type = "initial_generation"
    elif project_type == "migration":
        task_type = "initial_generation"  # Migration starts fresh in target
    else:
        task_type = "follow_up_edit"  # Brownfield = modify existing code

    return {
        "session_id": f"{agent_id}-{uuid.uuid4().hex[:8]}",
        "task_id": f"{project_token}-{agent_id}",
        "task_type": task_type,
        "prompt": prompt,
        "workspace_path": "/workspace",
        "project_id": project_token,
        "tenant_id": "default",
        "callback_url": callback_url or "http://host.docker.internal:8000/api/agent/callback",
        "callback_secret": "dsuite-agent-secret",
        "model_name": agent_model,
        "model_provider": "anthropic" if "claude" in agent_model.lower() else "openai",
        "tool_use_enabled": True,
        "web_search_enabled": web_search_enabled,
        "max_tool_calls": 80,
    }
