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
import re
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

    # Count real files (excluding hidden dirs, node_modules, __pycache__, and doc directories)
    SKIP_DIRS = {
        "node_modules", "__pycache__", ".git", ".agent", ".agent_signals",
        ".agent_history", "venv", ".venv", "dist", "build", ".next",
        ".gemini", ".antigravity", ".vscode", ".idea", "docs", "documentation", "specs", "blueprints",
    }

    # Extensions that represent real executable application code
    CODE_EXTENSIONS = {
        ".js", ".jsx", ".ts", ".tsx", ".py", ".java", ".go", ".rs",
        ".cpp", ".c", ".cs", ".php", ".rb", ".vue", ".svelte", ".html",
    }

    file_tree = []
    config_files_found = {}

    for root, dirs, files in os.walk(workspace_dir):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        rel_root = os.path.relpath(root, workspace_dir)
        if rel_root == ".":
            rel_root = ""

        for f in files:
            # Skip documentation, git/system ignore files, and media assets
            if f.lower().endswith((".md", ".txt", ".png", ".jpg", ".jpeg", ".svg", ".ico", ".gif", ".pdf")) or f.startswith("."):
                continue

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

    source_code_files = [f for f in file_tree if any(f.endswith(ext) for ext in CODE_EXTENSIONS)]
    result["total_files"] = len(file_tree)
    result["file_tree"] = file_tree[:500]  # Cap for token budget
    result["config_files"] = list(config_files_found.keys())

    # Determine project type: Greenfield if no significant source code exists
    if len(source_code_files) <= 2:
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

    for candidate in (
        "backend/src/index.js", "backend/src/server.js", "backend/src/app.js",
        "backend/index.js", "backend/server.js", "backend/app.js",
        "server/index.js", "server/server.js", "server/app.js", "server.js", "index.js",
        # Package-style FastAPI layout (backend/app/main.py, app/main.py) — these were
        # previously invisible to the analyzer, so agents never owned the entrypoint
        # and the app shipped without it (missing main.py bug class).
        "backend/app/main.py", "backend/src/main.py", "app/main.py", "src/app/main.py",
        "backend/main.py", "backend/app.py", "main.py", "app.py", "server.py", "src/main.py",
        "cmd/main.go", "main.go"
    ):
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
    """Inspect workspace code files to discover API endpoints and DB models with full prefixes."""
    import re
    discovered_routes = []
    discovered_models = []

    # Map of router module/file -> prefix from main.py / app.py include_router statements
    include_prefixes: Dict[str, str] = {}
    global_api_prefix = ""

    # Pass 1: Discover global and router include prefixes in entry points
    for entry_cand in ("backend/app/main.py", "backend/main.py", "app/main.py", "main.py", "app.py", "server.js", "src/server.js", "server/index.js"):
        entry_file = os.path.join(workspace_dir, entry_cand)
        if os.path.exists(entry_file):
            try:
                with open(entry_file, "r", encoding="utf-8", errors="ignore") as ef:
                    entry_content = ef.read()

                # Check for global prefix like API_V1_STR = "/api/v1" or prefix="/api/v1"
                g_match = re.search(r'(?:API_V1_STR|API_PREFIX|prefix)\s*=\s*["\']([^"\']+)["\']', entry_content)
                if g_match:
                    global_api_prefix = g_match.group(1).rstrip("/")

                # FastAPI include_router: app.include_router(auth.router, prefix="/api/v1/auth")
                for inc_match in re.finditer(r'include_router\(\s*([A-Za-z0-9_.]+)(?:,\s*prefix\s*=\s*["\']([^"\']+)["\'])?', entry_content):
                    r_mod = inc_match.group(1).split(".")[0].strip()
                    r_pfx = inc_match.group(2) or ""
                    if r_pfx:
                        include_prefixes[r_mod] = r_pfx

                # Express app.use('/api/v1/users', usersRouter)
                for exp_inc in re.finditer(r'app\.use\(\s*["\']([^"\']+)["\'],\s*([A-Za-z0-9_]+)\)', entry_content):
                    pfx, mod = exp_inc.group(1), exp_inc.group(2)
                    include_prefixes[mod] = pfx
            except Exception:
                pass

    # Pass 2: Extract routes from all files with prefix resolution
    for root, _, files in os.walk(workspace_dir):
        if any(skip in root for skip in ("node_modules", ".git", ".agent", "venv", "__pycache__", "dist", "build")):
            continue
        for f in files:
            fpath = os.path.join(root, f)
            rel = os.path.relpath(fpath, workspace_dir).replace("\\", "/")
            base_no_ext = os.path.splitext(f)[0]

            if f.endswith(".py"):
                try:
                    with open(fpath, "r", encoding="utf-8", errors="ignore") as pf:
                        content = pf.read()

                    # Find APIRouter prefix inside file: router = APIRouter(prefix="/auth")
                    router_prefix = ""
                    pfx_match = re.search(r'APIRouter\([^)]*prefix\s*=\s*["\']([^"\']+)["\']', content)
                    if pfx_match:
                        router_prefix = pfx_match.group(1).strip()

                    # Combine with include_router prefix if known
                    inc_pfx = include_prefixes.get(base_no_ext, "")
                    combined_prefix = ""
                    if inc_pfx and router_prefix and router_prefix not in inc_pfx:
                        combined_prefix = f"{inc_pfx.rstrip('/')}/{router_prefix.lstrip('/')}"
                    elif inc_pfx:
                        combined_prefix = inc_pfx
                    elif router_prefix:
                        combined_prefix = router_prefix
                    elif global_api_prefix and "router" in content:
                        combined_prefix = global_api_prefix

                    route_matches = re.findall(r'@(?:router|app)\.(get|post|put|delete|patch)\(\s*["\']([^"\']*)["\']', content, re.IGNORECASE)
                    for method, path in route_matches:
                        raw_route = path.strip()
                        if combined_prefix:
                            clean_pfx = combined_prefix.rstrip("/")
                            clean_path = raw_route.lstrip("/")
                            full_path = f"{clean_pfx}/{clean_path}" if clean_path else clean_pfx
                        else:
                            full_path = raw_route if raw_route.startswith("/") else f"/{raw_route}"

                        full_path = re.sub(r'/{2,}', '/', full_path)
                        discovered_routes.append({"method": method.upper(), "path": full_path, "file": rel})

                    class_matches = re.findall(r'class\s+([A-Za-z0-9_]+)\s*\((?:BaseModel|Base|SQLModel|Model)\):', content)
                    for cls in class_matches:
                        discovered_models.append({"model": cls, "file": rel})
                except Exception:
                    pass

            elif f.endswith((".ts", ".js")):
                try:
                    with open(fpath, "r", encoding="utf-8", errors="ignore") as jf:
                        content = jf.read()

                    inc_pfx = include_prefixes.get(base_no_ext, "")
                    exp_matches = re.findall(r'(?:router|app)\.(get|post|put|delete|patch)\(\s*["\']([^"\']*)["\']', content, re.IGNORECASE)
                    for method, path in exp_matches:
                        raw_route = path.strip()
                        if inc_pfx:
                            clean_pfx = inc_pfx.rstrip("/")
                            clean_path = raw_route.lstrip("/")
                            full_path = f"{clean_pfx}/{clean_path}" if clean_path else clean_pfx
                        else:
                            full_path = raw_route if raw_route.startswith("/") else f"/{raw_route}"
                        full_path = re.sub(r'/{2,}', '/', full_path)
                        discovered_routes.append({"method": method.upper(), "path": full_path, "file": rel})
                except Exception:
                    pass

            elif f.endswith(".go"):
                try:
                    with open(fpath, "r", encoding="utf-8", errors="ignore") as gf:
                        content = gf.read()
                    go_matches = re.findall(r'\.(GET|POST|PUT|DELETE|PATCH)\(\s*["\']([^"\']+)["\']', content)
                    for method, path in go_matches:
                        discovered_routes.append({"method": method.upper(), "path": path, "file": rel})
                except Exception:
                    pass

    # Deduplicate routes preserving order
    seen_routes = set()
    unique_routes = []
    for r in discovered_routes:
        key = (r["method"], r["path"])
        if key not in seen_routes:
            seen_routes.add(key)
            unique_routes.append(r)

    contract_data = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "routes": unique_routes,
        "models": discovered_models,
    }
    save_contract(workspace_dir, "api_contract", contract_data)
    save_contract(workspace_dir, "openapi", contract_data)
    return contract_data


def export_architecture_blueprints_to_workspace(
    workspace_dir: str,
    project_token: str,
    db: Session,
) -> Dict[str, Any]:
    """Export authoritative Dsuite Executive Summary, HLD, and LLD into workspace .agent/docs/

    This enables the in-container agents (via MCP tool or file reading) to inspect
    actual database DDL, API contracts, C4 diagrams, and business goals without
    saturating LLM context windows.
    """
    docs_dir = os.path.join(workspace_dir, ".agent", "docs")
    os.makedirs(docs_dir, exist_ok=True)

    result = {
        "docs_dir": docs_dir,
        "executive_summary_path": None,
        "hld_path": None,
        "lld_path": None,
        "manifest_path": None,
        "has_content": False,
        "available_documents": [],
    }

    try:
        doc = db.query(models.Document).filter(
            models.Document.project_token == project_token
        ).first()

        gov = db.query(models.GovernanceResponse).filter(
            models.GovernanceResponse.project_token == project_token
        ).first()

        analysis_data: Dict[str, Any] = {}
        if doc and getattr(doc, "analysis_result", None):
            try:
                raw_res = doc.analysis_result
                analysis_data = json.loads(raw_res) if isinstance(raw_res, str) else dict(raw_res)
            except Exception:
                analysis_data = {}

        p_name = analysis_data.get("title") or (doc.filename if doc and getattr(doc, "filename", None) else "Enterprise Solution")
        stages = analysis_data.get("stages") or {}
        stage1 = stages.get("stage1_requirements") or analysis_data.get("stage1_requirements") or {}

        # ── 1. Executive Summary ──
        exec_summary_content = ""
        if stage1.get("product_vision") or stage1.get("project_description"):
            pv = stage1.get("product_vision") or stage1.get("project_description") or ""
            scope = stage1.get("scope") or stage1.get("project_scope") or ""
            objectives = stage1.get("objectives") or stage1.get("business_objectives") or []
            if isinstance(objectives, list):
                obj_str = "\n".join(f"- {o}" for o in objectives)
            else:
                obj_str = str(objectives)
            exec_summary_content = (
                f"# EXECUTIVE SUMMARY — {p_name}\n\n"
                f"## 1. Product Vision\n{pv}\n\n"
                f"## 2. Business Objectives & Success Criteria\n{obj_str}\n\n"
                f"## 3. Scope & Target Archetype\n{scope}\n"
            )
        elif gov and getattr(gov, "recommendation", None):
            exec_summary_content = f"# EXECUTIVE SUMMARY — {p_name}\n\n{gov.recommendation}\n"
        elif doc and getattr(doc, "full_content", None):
            exec_summary_content = f"# EXECUTIVE SUMMARY — {p_name}\n\n{doc.full_content[:4000]}\n"

        if exec_summary_content:
            summary_file = os.path.join(docs_dir, "EXECUTIVE_SUMMARY.md")
            with open(summary_file, "w", encoding="utf-8") as f:
                f.write(exec_summary_content)
            result["executive_summary_path"] = summary_file
            result["has_content"] = True

        # ── 2. High-Level Design (HLD) ──
        hld_content = ""
        hld_obj = analysis_data.get("hld")
        if isinstance(hld_obj, dict) and hld_obj.get("markdown"):
            hld_content = hld_obj["markdown"]
        elif analysis_data:
            try:
                from app.services.ai.architecture_design_service import synthesize_hld_from_analysis
                hld_content = synthesize_hld_from_analysis(analysis_data, project_name=p_name)
            except Exception as e:
                logger.debug(f"HLD synthesis note: {e}")

        if hld_content:
            hld_file = os.path.join(docs_dir, "HLD.md")
            with open(hld_file, "w", encoding="utf-8") as f:
                f.write(hld_content)
            result["hld_path"] = hld_file
            result["has_content"] = True

        # ── 3. Low-Level Design (LLD) ──
        lld_content = ""
        lld_obj = analysis_data.get("lld")
        if isinstance(lld_obj, dict) and lld_obj.get("markdown"):
            lld_content = lld_obj["markdown"]
        elif analysis_data:
            try:
                from app.services.ai.architecture_design_service import synthesize_lld_from_analysis
                lld_content = synthesize_lld_from_analysis(analysis_data, project_name=p_name)
            except Exception as e:
                logger.debug(f"LLD synthesis note: {e}")

        if lld_content:
            lld_file = os.path.join(docs_dir, "LLD.md")
            with open(lld_file, "w", encoding="utf-8") as f:
                f.write(lld_content)
            result["lld_path"] = lld_file
            result["has_content"] = True

        # ── 4. Structured Architecture Manifest ──
        available_docs = [
            f for f in ["EXECUTIVE_SUMMARY.md", "HLD.md", "LLD.md"]
            if os.path.exists(os.path.join(docs_dir, f))
        ]
        result["available_documents"] = available_docs

        manifest_data = {
            "project_name": p_name,
            "project_token": project_token,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "has_executive_summary": bool(result["executive_summary_path"]),
            "has_hld": bool(result["hld_path"]),
            "has_lld": bool(result["lld_path"]),
            "available_documents": available_docs,
            "recommended_query_sections": [
                "database", "api", "components", "workflows", "security", "overview"
            ]
        }
        manifest_file = os.path.join(docs_dir, "architecture_manifest.json")
        with open(manifest_file, "w", encoding="utf-8") as f:
            json.dump(manifest_data, f, indent=2)
        result["manifest_path"] = manifest_file

        # ── 5. Pre-seed .agent/contracts/api_contract.json from Stage 3 / LLD ──
        stage3 = stages.get("stage3_data_api") or analysis_data.get("stage3_data_api") or {}
        lld_endpoints = stage3.get("api_endpoints", [])
        if lld_endpoints and isinstance(lld_endpoints, list):
            seeded_routes = [
                {
                    "method": str(ep.get("method", "GET")).upper(),
                    "path": str(ep.get("path", "/api/v1")),
                    "purpose": str(ep.get("purpose", "")),
                    "file": "LLD_AUTHORITATIVE_CONTRACT",
                }
                for ep in lld_endpoints
                if isinstance(ep, dict) and ep.get("path")
            ]
            if seeded_routes:
                save_contract(workspace_dir, "api_contract", {
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "source": "lld_blueprint",
                    "routes": seeded_routes,
                    "models": [],
                })
                logger.info(f"[MasterOrchestrator] Pre-seeded {len(seeded_routes)} authoritative LLD routes into api_contract.json")

        logger.info(f"[MasterOrchestrator] Exported architecture blueprints to {docs_dir}: {available_docs}")
    except Exception as exc:
        logger.warning(f"[MasterOrchestrator] Failed exporting architecture blueprints: {exc}")

    return result


def organize_tasks_into_phases(assignments: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    """Group assigned agents into execution phases (Dependency DAG).

    Phase 1: Backend & Data Layer (agents working on backend/database/server)
    Phase 2: Frontend & UI Layer (agents working on frontend/ui/web)
    Phase 3: DevOps & Container Infrastructure (Dockerfile, docker-compose, nginx, packaging)
    Phase 4: QA & Verification Gate (Test Agent T_agent_01 / QA specialists)
    """
    phase1_backend: List[str] = []
    phase2_frontend: List[str] = []
    phase3_devops: List[str] = []
    phase4_qa: List[str] = []

    seen_agents: Set[str] = set()

    for a in assignments:
        lane = str(a.get("lane", "general")).lower()
        aid = a.get("assigned_to")
        if not aid or aid in seen_agents:
            continue
        seen_agents.add(aid)

        if lane in ("backend", "api", "database", "data") or any(k in lane for k in ("db", "server", "model")):
            phase1_backend.append(aid)
        elif lane in ("frontend", "ui", "web", "client"):
            phase2_frontend.append(aid)
        elif lane in ("devops", "infra", "infrastructure", "docker", "deploy", "ci"):
            phase3_devops.append(aid)
        elif lane in ("qa", "test", "verification", "testing"):
            phase4_qa.append(aid)
        else:
            phase1_backend.append(aid)

    if not phase4_qa:
        phase4_qa.append("T_agent_01")

    return {
        "phase1_backend": phase1_backend,
        "phase2_frontend": phase2_frontend,
        "phase3_devops": phase3_devops,
        "phase4_qa_gate": phase4_qa,
    }


# ══════════════════════════════════════════════════════════════════════════════
# Task Assignment — Skill-Based Matching
# ══════════════════════════════════════════════════════════════════════════════

async def assign_tasks_to_agents(
    tasks: List[models.Task],
    agents: List[Dict[str, Any]],
    db: Session,
    project_token: Optional[str] = None,
    current_user: Optional[Any] = None,
) -> List[Dict[str, Any]]:
    """Dynamically assign tasks to agents using the Master Orchestrator AI (LLM).

    The AI evaluates task domain, goals, and role requirements against agent skills,
    assigning each task to the optimal agent and classifying its execution lane.
    Falls back to semantic role-based matching if LLM is unavailable.
    """
    worker_agents = [a for a in agents if not _is_system_id(a.get("id", ""))]
    if not worker_agents:
        logger.warning("[MasterOrchestrator] No worker agents available for assignment")
        return []

    # 1. Prepare agent metadata for AI prompt
    agents_summary = []
    worker_by_id = {}
    for a in worker_agents:
        aid = a.get("id", "")
        worker_by_id[aid] = a
        name = a.get("name", aid)
        role = a.get("role") or a.get("specialization") or "Developer"
        spec = a.get("specialization") or "General"
        skills = a.get("skills_summary") or a.get("skills_content") or a.get("skills_tags") or ""
        if isinstance(skills, list):
            skills = ", ".join(str(s) for s in skills)
        agents_summary.append({
            "agent_id": aid,
            "name": name,
            "role": role,
            "specialization": spec,
            "skills": str(skills)[:300],
        })

    # 2. Prepare tasks metadata for AI prompt
    tasks_summary = []
    task_by_id = {}
    for task in tasks:
        t_id = getattr(task, "task_id", getattr(task, "id", ""))
        task_by_id[str(t_id)] = task
        if "_" in str(t_id):
            task_by_id[str(t_id).split("_", 1)[1]] = task
        t_title = getattr(task, "task_name", getattr(task, "title", "Task"))
        t_desc = getattr(task, "description", "") or ""
        tasks_summary.append({
            "task_id": str(t_id),
            "title": t_title,
            "type": getattr(task, "task_type", "FEATURE"),
            "summary": t_desc[:350],
        })

    assignments: List[Dict[str, Any]] = []

    # 3. Call Master Orchestrator LLM for dynamic assignment
    try:
        from app.integrations.llm.llm_gateway import (
            call_llm_and_extract,
            ai_project_context,
            current_user_id_var,
            current_user_org_var,
        )

        u_id = getattr(current_user, "id", None) or current_user_id_var.get()
        u_org = getattr(current_user, "organization_name", None) or current_user_org_var.get()
        if not u_id and project_token:
            doc = db.query(models.Document).filter(models.Document.project_token == project_token).first()
            if doc and doc.owner_id:
                u_id = doc.owner_id
                u_rec = db.query(models.User).filter(models.User.id == u_id).first()
                if u_rec and u_rec.organization_name:
                    u_org = u_rec.organization_name

        if u_id:
            current_user_id_var.set(u_id)
        if u_org:
            current_user_org_var.set(u_org)

        ai_prompt = (
            "You are the Master Orchestrator AI in an autonomous multi-agent software engineering platform.\n"
            "Analyze the tasks below and dynamically assign each task to the most appropriate worker agent based on domain, role, and technical skills.\n\n"
            f"Available Worker Agents:\n{json.dumps(agents_summary, indent=2)}\n\n"
            f"Tasks to Assign:\n{json.dumps(tasks_summary, indent=2)}\n\n"
            "Assignment & Lane Rules:\n"
            "1. Backend tasks (server, REST/GraphQL APIs, database models, schemas, auth/JWT, migrations, business logic) -> Assign to a Backend Developer. Lane MUST be 'backend'.\n"
            "2. Frontend tasks (UI screens, web views, pages, React/Vue components, forms, client routing, dashboards, design systems) -> Assign to a Frontend Developer. Lane MUST be 'frontend'.\n"
            "3. Testing/QA tasks (writing unit test suites, integration tests, E2E test scripts, linter audits, QA verification) -> Assign to a QA/Test Specialist. Lane MUST be 'qa'.\n"
            "4. DevOps/Infrastructure tasks (CI/CD workflows, Docker packaging, deployment scripts, monitoring) -> Assign to a DevOps Agent. Lane MUST be 'devops'.\n"
            "5. CRITICAL: NEVER assign UI screens or frontend views to a QA specialist or backend engineer when a Frontend Developer is available!\n"
            "6. Each task MUST be assigned to exactly one agent ID from the provided list.\n\n"
            "Return valid JSON ONLY with this schema:\n"
            "{\n"
            '  "assignments": [\n'
            "    {\n"
            '      "task_id": "...",\n'
            '      "assigned_agent_id": "...",\n'
            '      "lane": "frontend" | "backend" | "qa" | "devops" | "general",\n'
            '      "confidence": 0.95,\n'
            '      "reasoning": "Brief explanation why this agent and lane were chosen"\n'
            "    }\n"
            "  ]\n"
            "}"
        )

        messages = [{"role": "user", "content": ai_prompt}]
        parsed = None
        max_retries = 3

        for attempt in range(max_retries):
            with ai_project_context(project_token=project_token):
                raw_ai_res = await call_llm_and_extract(messages, timeout=45.0)

            if not raw_ai_res:
                logger.warning(f"[MasterOrchestrator] Empty AI assignment response (attempt {attempt + 1}/{max_retries})")
                continue

            clean_res = raw_ai_res.strip()
            if clean_res.startswith("```"):
                clean_res = re.sub(r"^```(?:json)?\s*", "", clean_res)
                clean_res = re.sub(r"\s*```$", "", clean_res)

            # Robust JSON extraction: search for outermost JSON object
            json_match = re.search(r"(\{[\s\S]*\})", clean_res)
            target_str = json_match.group(1) if json_match else clean_res

            try:
                candidate = json.loads(target_str)
                if isinstance(candidate, dict) and "assignments" in candidate and isinstance(candidate["assignments"], list) and len(candidate["assignments"]) > 0:
                    parsed = candidate
                    break
                else:
                    raise ValueError("JSON parsed successfully but missing valid non-empty 'assignments' list")
            except Exception as parse_err:
                logger.warning(f"[MasterOrchestrator] AI assignment parse failure (attempt {attempt + 1}/{max_retries}): {parse_err}")
                if attempt < max_retries - 1:
                    messages.append({"role": "assistant", "content": raw_ai_res[:1000]})
                    messages.append({
                        "role": "user",
                        "content": (
                            f"Your previous response failed validation. Error: {parse_err}.\n"
                            "Please output ONLY valid, well-formed JSON conforming to the requested schema. "
                            "Do not include explanation, markdown comments, or trailing commas. Follow this exact schema:\n"
                            '{\n  "assignments": [\n    {"task_id": "...", "assigned_agent_id": "...", "lane": "frontend" | "backend" | "qa" | "devops" | "general", "confidence": 0.95, "reasoning": "..."}\n  ]\n}'
                        )
                    })

        if parsed and isinstance(parsed, dict) and "assignments" in parsed:
            assigned_task_ids = set()
            for item in parsed["assignments"]:
                t_id_str = str(item.get("task_id", ""))
                task = task_by_id.get(t_id_str)
                if not task:
                    for k, v in task_by_id.items():
                        if k.endswith(t_id_str) or t_id_str.endswith(k):
                            task = v
                            break
                if not task:
                    continue

                actual_task_id = getattr(task, "task_id", getattr(task, "id", ""))
                if actual_task_id in assigned_task_ids:
                    continue

                chosen_agent_id = str(item.get("assigned_agent_id", ""))
                chosen_agent = worker_by_id.get(chosen_agent_id)
                if not chosen_agent:
                    item_lane = item.get("lane", "general")
                    for a in worker_agents:
                        a_spec = (a.get("specialization") or a.get("role") or "").lower()
                        if item_lane in a_spec:
                            chosen_agent = a
                            chosen_agent_id = a["id"]
                            break
                    if not chosen_agent:
                        chosen_agent = worker_agents[0]
                        chosen_agent_id = chosen_agent["id"]

                lane = item.get("lane") or "general"
                score = float(item.get("confidence", 0.95))
                reasoning = item.get("reasoning", "")

                task.assigned_to = json.dumps([chosen_agent_id])
                task.assigned_agent_id = chosen_agent_id
                task.assigned_agent_role = chosen_agent.get("name", "Developer")
                if getattr(task, "status", None) in (None, "pending", "todo", "TODO"):
                    task.status = "in_progress"

                assignments.append({
                    "task_id": actual_task_id,
                    "title": getattr(task, "task_name", getattr(task, "title", "Task")),
                    "lane": lane,
                    "assigned_to": chosen_agent_id,
                    "score": round(score, 3),
                    "reasoning": reasoning,
                })
                assigned_task_ids.add(actual_task_id)

            if len(assignments) == len(tasks):
                logger.info(f"[MasterOrchestrator] AI assigned all {len(assignments)} tasks dynamically.")
            elif len(assignments) > 0:
                logger.info(f"[MasterOrchestrator] AI assigned {len(assignments)}/{len(tasks)} tasks; remainder completed by semantic fallback.")
    except Exception as ai_err:
        logger.warning(f"[MasterOrchestrator] Dynamic AI task assignment error: {ai_err}; using semantic role fallback.")

    # 4. Fallback / Remainder assignment (Semantic Role Matching, no keyword substring traps)
    assigned_ids_set = set(a["task_id"] for a in assignments)
    for task in tasks:
        actual_task_id = getattr(task, "task_id", getattr(task, "id", ""))
        if actual_task_id in assigned_ids_set:
            continue

        t_title = getattr(task, "task_name", getattr(task, "title", "Task"))
        t_desc = getattr(task, "description", "") or ""
        task_lane = _infer_task_lane(t_title, t_desc)

        best_agent = None
        best_score = -1.0

        for agent in worker_agents:
            agent_lanes = get_agent_lanes_from_skills(
                agent_id=agent.get("id", ""),
                skills_tags=agent.get("skills_tags"),
                specialization=agent.get("specialization"),
            )
            if not is_task_in_agent_lanes(task_lane, agent_lanes):
                continue

            score = 0.85 if task_lane in agent_lanes else 0.4
            if score > best_score:
                best_score = score
                best_agent = agent

        if not best_agent:
            best_agent = worker_agents[0]

        assigned_id = best_agent["id"]
        task.assigned_to = json.dumps([assigned_id])
        task.assigned_agent_id = assigned_id
        task.assigned_agent_role = best_agent.get("name", "Developer")
        if getattr(task, "status", None) in (None, "pending", "todo", "TODO"):
            task.status = "in_progress"

        assignments.append({
            "task_id": actual_task_id,
            "title": t_title,
            "lane": task_lane,
            "assigned_to": assigned_id,
            "score": round(best_score, 3),
            "reasoning": f"Assigned to {best_agent.get('name')} based on {task_lane} domain match.",
        })

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"[MasterOrchestrator] Error saving task assignments: {e}")

    return assignments


def _infer_task_lane(title: str, description: str) -> str:
    """Infer the execution lane primarily from task title, with description context.

    Uses title-priority and word boundaries to avoid greedy substring false positives.
    """
    title_lower = title.lower()
    desc_lower = (description or "").lower()

    # 1. Title is the definitive intent of the task
    if any(w in title_lower for w in ("test suite", "test suites", "e2e test", "e2e tests", "unit test", "unit & integration")):
        return "qa"
    if any(w in title_lower for w in ("screen", "screens", "ui", "view", "page", "dashboard", "component", "components", "frontend", "form", "loading", "spinner", "toast", "skeleton", "theme")):
        return "frontend"
    if any(w in title_lower for w in ("backend", "api", "database", "model", "schema", "controller", "server", "auth", "jwt", "migration")):
        return "backend"
    if re.search(r"\b(test suite|e2e|testing|unit test|quality assurance|audit|lint)\b", title_lower):
        return "qa"
    if any(w in title_lower for w in ("deploy", "docker", "ci/cd", "pipeline", "infrastructure")):
        return "devops"

    # 2. Contextual check using word boundaries (never greedy substring matching)
    if re.search(r"\b(react|vite|tailwind|css|html|ui component|ui components|screen|screens|layout|frontend|toast|spinner|skeleton)\b", desc_lower):
        return "frontend"
    if re.search(r"\b(fastapi|django|flask|express|sql|orm|database|endpoint|crud|backend)\b", desc_lower):
        return "backend"
    if re.search(r"\b(pytest|jest|vitest|cypress|playwright|e2e test|unit test)\b", desc_lower):
        return "qa"
    if re.search(r"\b(dockerfile|kubernetes|nginx|ci/cd)\b", desc_lower):
        return "devops"

    return "general"


def _is_system_id(agent_id: str) -> bool:
    """Check if agent_id belongs to a system/default agent."""
    clean_id = agent_id.split("::")[-1].split("#")[0].lower().strip()
    sys_ids = {"m_agent_01", "master_agent", "t_agent_01", "deploy_agent", "g_agent_01", "git_manager"}
    return clean_id in sys_ids


# ══════════════════════════════════════════════════════════════════════════════
# Orchestration Entry Point
# ══════════════════════════════════════════════════════════════════════════════

async def orchestrate_project(
    db: Session,
    project_token: str,
    agent_service: Any,
    project_name: Optional[str] = None,
    current_user: Optional[Any] = None,
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

    # ── Step 6: Dynamically assign tasks via Master Orchestrator AI ──
    assignments = await assign_tasks_to_agents(
        tasks=target_tasks,
        agents=all_agents,
        db=db,
        project_token=project_token,
        current_user=current_user,
    )

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
    skills_content: Optional[str] = None,
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

    # ── Authoritative Architecture Blueprints Context (Executive Summary, HLD, LLD) ──
    blueprints_context = ""
    docs_dir = os.path.join(target_ws, ".agent", "docs") if target_ws else None
    if docs_dir and os.path.isdir(docs_dir):
        available = [
            f for f in ("EXECUTIVE_SUMMARY.md", "HLD.md", "LLD.md")
            if os.path.exists(os.path.join(docs_dir, f))
        ]
        if available:
            blueprints_context = (
                "\n## 🏛️ Authoritative Architecture Blueprints (Dsuite HLD & LLD Mounted)\n"
                f"The authoritative design blueprints are mounted in your workspace under `.agent/docs/`:\n"
            )
            for doc_name in available:
                blueprints_context += f"- `.agent/docs/{doc_name}`\n"
            blueprints_context += (
                "\n**Architectural Inspection Directive:**\n"
                "- Call `get_architecture_spec(document='lld', section='database')` to retrieve exact table DDL schemas and relationships.\n"
                "- Call `get_architecture_spec(document='lld', section='api')` to retrieve exact REST endpoint contracts and response models.\n"
                "- Call `get_architecture_spec(document='hld', section='components')` to inspect UI component hierarchies.\n"
                "- Alternatively, read `.agent/docs/LLD.md` or `.agent/docs/HLD.md` with `read_file` or `grep_search`.\n"
                "- **CRITICAL:** Do NOT invent arbitrary database schemas or endpoints when authoritative contracts exist in `LLD.md`!\n"
            )

    # ── Phase 3 instructions based on agent role ──
    if is_qa_agent:
        phase3 = (
            "### PHASE 3: QA Execution & Test Authoring (ZERO APP CODE MODIFICATION)\n"
            "- CRITICAL: You have read-only access to application source code.\n"
            "- Detect the test framework (pytest, jest, vitest, mocha, playwright, cypress).\n"
            "- Author test files in tests/, __tests__/, *.test.*, or *.spec.* directories.\n"
            "- Execute: pytest tests/ -v (Python) or npm test or npx playwright test (Node.js).\n"
            "- Report ALL failures with exact file:line references and full error messages.\n"
            "- Write defect reports to .agent/defect_reports/ for any failing tests.\n"
            "- If ALL tests pass: write .agent/contracts/qa_gate.json with status=PASSED."
        )
    else:
        phase3 = (
            "### PHASE 3: Targeted Implementation with Authorized Tools\n"
            "- Implement assigned subtasks using: write_file, read_file, execute_bash, list_directory, find_and_replace.\n"
            "- READ FIRST: Always read a file before modifying it. NEVER overwrite working code blindly.\n"
            "- Use find_and_replace for surgical edits to existing files -- avoid full rewrites unless truly necessary.\n"
            "- Maintain existing code style, naming conventions, and architecture patterns.\n"
            "- NO hardcoded data -- use proper data structures, environment variables, and API patterns.\n"
            "- Backend agents: after each endpoint, document it in .agent/contracts/api_contract.json."
        )

    # File ownership directives per lane -- prevents cross-agent conflicts while allowing full application scaffolding
    if is_qa_agent or "qa" in (agent_lanes or set()):
        file_ownership = "tests/, __tests__/, *.test.*, *.spec.*, cypress/, playwright/, .agent/defect_reports/"
    elif "frontend" in (agent_lanes or set()) or "ui" in (agent_lanes or set()):
        file_ownership = "frontend/, src/, components/, pages/, views/, hooks/, contexts/, styles/, public/, package.json, index.html, App.*, main.*, vite.config.*, tsconfig.json"
    elif "backend" in (agent_lanes or set()):
        file_ownership = "backend/, server/, api/, controllers/, models/, database/, migrations/, services/, routes/, main.py, app.py, requirements.txt, pyproject.toml"
    elif "devops" in (agent_lanes or set()):
        file_ownership = "Dockerfile, docker-compose*, .github/workflows/, nginx.conf, Makefile, scripts/, k8s/"
    else:
        file_ownership = "All project files relevant to your assigned tasks and making the application runnable"

    prompt = (
        "# Persona & Execution Assignment\n"
        f"You are **{agent_name}**, serving as **{agent_role}** specialized in **{agent_spec}**.\n"
        f"- Operational Lanes: {lanes_str}\n"
        f"- Configured AI Engine: {assigned_model.upper()}\n"
        f"- Authorized Container Tools: {tools_str}\n"
        f"- Primary Focus Scope: {file_ownership}\n"
        + (f"- Skills & Focus: {skills_summary}\n" if skills_summary else "")
        + (f"\n## Bespoke System Prompt & Specialization Instructions:\n{skills_content.strip()}\n" if skills_content and skills_content.strip() else "")
        + f"\n{workspace_context}\n{contracts_context}\n{blueprints_context}\n"
        + (f"## Business Requirements & Architecture:\n{brd_context}\n" if brd_context else "")
        + f"\n{task_summary}\n"
        "\n## ============================================================================\n"
        "## CORE DIRECTIVE: BRD FULFILLMENT & RUNNABLE APPLICATION (PRIMARY OBJECTIVE)\n"
        "## ============================================================================\n"
        "## 1. TASKS ARE MILESTONES, NOT CAGES: The assigned task and subtasks guide your\n"
        "##    milestone focus. They do NOT limit your engineering responsibility. Your primary\n"
        "##    duty is to fulfill the Business Requirements Document (BRD) and deliver a 100%\n"
        "##    working, connected, and RUNNABLE application.\n"
        "## 2. FIX MISSING FOUNDATIONS: If foundational files are missing or broken (such as\n"
        "##    package.json, entry points main.tsx/main.py, root App router, layouts, styling,\n"
        "##    or environment configs), you HAVE FULL AUTONOMY AND RESPONSIBILITY to create or\n"
        "##    repair them immediately. Never leave code unrunnable because a prerequisite wasn't\n"
        "##    explicitly written in the subtask checklist.\n"
        "## 3. ZERO ORPHANED FEATURES: Every UI feature or page you build MUST be wired into\n"
        "##    the application router and navigation layout (sidebar/header) so real users can\n"
        "##    reach and interact with it. Components floating unrendered on disk are FAILURES.\n"
        "## 4. END-TO-END CONNECTION: Connect frontend features to real backend endpoints or\n"
        "##    verified contracts (.agent/contracts/api_contract.json). Never leave fake routes\n"
        "##    that 404. If a backend endpoint is still pending, provide clean local mock data.\n"
        "## ============================================================================\n"
        "\n## ============================================================================\n"
        "## AGENTIC OS -- AUTONOMOUS REACT LOOP (OBSERVE -> ACT -> VERIFY -> SELF-HEAL)\n"
        "## ============================================================================\n"
        "## You are an autonomous software engineering process running inside a sandboxed\n"
        "## container. Each tool call (read_file, write_file, execute_bash) is an OS syscall.\n"
        "## You have full autonomy -- but ZERO tolerance for unverified code.\n"
        "## ============================================================================\n"
        "\n### PHASE 1: Tech-Stack-Agnostic Discovery (MANDATORY -- DO THIS FIRST)\n"
        "- NEVER assume the tech stack, file structure, or existing code without reading first.\n"
        "- Begin with list_directory('/workspace') to understand what already exists.\n"
        "- Detect the tech stack by reading manifest files:\n"
        "  - package.json -> Node.js (read dependencies for React/Vue/Next/Angular/Svelte/Express/NestJS)\n"
        "  - requirements.txt / pyproject.toml -> Python (check for FastAPI/Django/Flask/SQLAlchemy)\n"
        "  - go.mod -> Go | Cargo.toml -> Rust | pom.xml / build.gradle -> Java/Spring/Kotlin\n"
        "  - composer.json -> PHP Laravel | Gemfile -> Ruby/Rails\n"
        "- Read the entry point file (index.js, main.py, app.py, src/App.jsx) to understand patterns.\n"
        "- GREENFIELD (0-2 files): design structure from BRD requirements.\n"
        "- BROWNFIELD (existing code): read 3-5 key files BEFORE writing anything.\n"
        f"- PRIMARY FOCUS: Concentrate work within: {file_ownership}\n"
        "  Ensure all changes support a unified, runnable project.\n"
        "\n### PHASE 2: Execution Planning & Dependency-Ordered Subtask Breakdown\n"
        "- Formulate a dependency-ordered plan BEFORE writing any code:\n"
        "  Data/Schema layer -> Service/Business Logic -> API/Route -> UI Integration -> Verification\n"
        "- Identify which files need to be CREATED vs MODIFIED.\n"
        "- Verify all imports reference real, existing modules before using them.\n"
        "- Backend agents: define the API contract (endpoint, method, request/response schema) FIRST.\n"
        "- Frontend agents: read_file('.agent/contracts/api_contract.json') BEFORE any API client code.\n"
        f"\n{phase3}\n"
        "\n### PHASE 4: Zero-Error Verification Gate (MANDATORY -- EVERY TASK)\n"
        "- After EVERY significant file change, immediately run the project's verification command:\n"
        "  - Python: python -m py_compile <file> then python -c 'import <module_path>'\n"
        "  - JavaScript/TypeScript: detect build command from package.json scripts field\n"
        "  - Run: npm run build / npx tsc --noEmit / npm run lint / eslint src/ as applicable\n"
        "- If ANY error -> OBSERVE the full error -> ACT to fix -> VERIFY again.\n"
        "- ZERO-ERROR CONTRACT -- A task is NOT complete until:\n"
        "  All files compile/parse without syntax errors.\n"
        "  All imports resolve to existing, real modules (no phantom imports).\n"
        "  Build command exits with code 0.\n"
        "  No undefined variables, missing types, or broken references.\n"
        "\n### PHASE 5: Inter-Agent Contract IPC (Multi-Agent Coordination)\n"
        "- Backend Agents: After implementing endpoints, publish .agent/contracts/api_contract.json:\n"
        '  {"updated_at": "<ISO timestamp>", "routes": [{"method": "POST", "path": "/api/...", "request": {}, "response": {}}], "models": [{"name": "User", "fields": {"id": "int", "email": "str"}}]}\n'
        "- Frontend Agents: Read .agent/contracts/api_contract.json before wiring any API client.\n"
        "  If not found, create stub API client with TODO comments for each expected endpoint.\n"
        "- QA Agents: Read api_contract.json and source files before authoring tests.\n"
        "  Write results to .agent/contracts/qa_gate.json with pass/fail status.\n"
        "\n### REACT SELF-HEALING LOOP (Execute on EVERY error without exception)\n"
        "1. OBSERVE: Read the full error output -- trace, file path, line number, error type\n"
        "2. LOCATE: read_file('<error_file>', start_line=N-5, end_line=N+10) to see context\n"
        "3. DIAGNOSE: Identify root cause (missing import? wrong type? undefined var? syntax?)\n"
        "4. ACT: Use find_and_replace for a surgical fix -- change ONLY the broken lines\n"
        "5. VERIFY: Re-run the exact command that failed -- confirm exit code 0\n"
        "6. REPEAT: Until all checks pass. Minimum 1, maximum 5 self-heal iterations per error.\n"
    )
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


def get_project_execution_status(project_token: str) -> Dict[str, Any]:
    """Return the current shared execution status for a project.

    This is the single coordination view that other services should consult
    when deciding whether to start agents, retry work, or escalate a blocker.
    """
    try:
        from .project_execution_tracker import get_tracker

        tracker = get_tracker(project_token)
        return tracker.snapshot()
    except Exception as e:
        logger.debug(
            "[MasterOrchestrator] get_project_execution_status failed for %s: %s",
            project_token,
            e,
        )
        return {
            "project_token": project_token,
            "status": "unknown",
            "is_blocked": False,
            "blocked_reasons": [],
            "error": str(e),
        }


def assess_project_runnable_state(
    project_token: str,
    workspace_dir: str,
    build_cmd: Optional[str] = None,
    run_cmd: Optional[str] = None,
) -> Dict[str, Any]:
    """Assess whether the project is currently blocked or potentially runnable.

    This is a lightweight coordination gate, not a full verification suite.
    It combines:
    - execution tracker blocked reasons
    - workspace-level presence of essential project files
    - any passed runnable verification marker if one exists
    """
    try:
        from .project_execution_tracker import get_tracker

        tracker = get_tracker(project_token)
        snapshot = tracker.snapshot()

        result: Dict[str, Any] = {
            "project_token": project_token,
            "is_blocked": tracker.is_blocked(),
            "blocked_reasons": list(tracker.blocked_reasons),
            "verified_runnable": tracker.is_verified_runnable(),
            "workspace_dir": workspace_dir,
            "essential_files_present": False,
            "assessment": "unknown",
        }

        workspace_present = False
        essential_files: List[str] = []

        if os.path.isdir(workspace_dir):
            workspace_present = True
            entries = os.listdir(workspace_dir)
            requirements = any(f in entries for f in ("requirements.txt", "pyproject.toml", "setup.py"))
            package = "package.json" in entries
            docker_compose = any(f in entries for f in ("docker-compose.yml", "docker-compose.yaml"))
            dockerfile = "Dockerfile" in entries

            essential_files = []
            if requirements or package:
                essential_files.append("project_manifest")
            if dockerfile or docker_compose:
                essential_files.append("container_defs")
            if os.path.isdir(os.path.join(workspace_dir, "backend")) or os.path.isdir(os.path.join(workspace_dir, "src")):
                essential_files.append("source_dir")

            result["essential_files_present"] = len(essential_files) > 0
            result["essential_files"] = essential_files

        if not workspace_present:
            result["assessment"] = "no_workspace"
        elif tracker.is_blocked():
            result["assessment"] = "blocked_by_execution_state"
        elif not result["essential_files_present"]:
            result["assessment"] = "missing_essential_workspace_files"
        elif tracker.is_verified_runnable() is True:
            result["assessment"] = "verified_runnable"
        else:
            result["assessment"] = "unverified_but_not_blocked"

        return result
    except Exception as e:
        logger.debug(
            "[MasterOrchestrator] assess_project_runnable_state failed for %s: %s",
            project_token,
            e,
        )
        return {
            "project_token": project_token,
            "is_blocked": False,
            "blocked_reasons": [],
            "assessment": "assessment_error",
            "error": str(e),
        }



def triage_deployment_failure_for_hotfix(
    db: Session,
    project_token: str,
    workspace_dir: str,
    deploy_error: str,
    deploy_report: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Master Agent Hot-Fix Triage:
    Analyzes a deployment failure raised by the Deploy Agent, determines whether the root cause
    is in the Backend, Frontend, or DevOps/Nginx layer, looks up the exact AI agent assigned to
    those tasks in `models.Task`, and constructs a surgical Hot-Fix instruction prompt.
    """
    report = deploy_report or {}
    fe_err = str(report.get("frontend_error") or "")
    be_err = str(report.get("backend_error") or "")
    combined = f"{fe_err}\n{be_err}\n{deploy_error}".strip()
    lower_err = combined.lower()

    # 1. Determine responsible lane from error signature & file paths
    if fe_err or any(k in lower_err for k in (
        "vite", "rollup", "tsx", "jsx", "npm run build", "postcss", "tailwind", "react", "src/components", "src/pages", "src/app"
    )):
        target_lane = "frontend"
    elif any(k in lower_err for k in (
        "nginx", "docker-compose", "dockerfile", "502 bad gateway", "upstream", "nginx.conf"
    )) and not be_err:
        target_lane = "devops"
    else:
        target_lane = "backend"

    # 2. Find the exact AI agent who owns tasks in `target_lane` (or modified the offending file)
    tasks = db.query(models.Task).filter(models.Task.project_token == project_token).all()
    responsible_agent_id = None
    responsible_task_title = None

    # Extract any file paths mentioned in the traceback
    mentioned_files = re.findall(
        r'([a-zA-Z0-9_\-./]+\.(?:py|tsx|jsx|ts|js|vue|svelte|css|conf|yml|yaml))',
        combined,
    )

    for t in tasks:
        t_aid = getattr(t, "assigned_agent_id", None)
        if not t_aid or _is_system_id(t_aid):
            continue
        t_title = getattr(t, "task_name", None) or getattr(t, "title", "") or ""
        t_desc = getattr(t, "description", "") or ""
        t_lane = _infer_task_lane(t_title, t_desc)

        # Match by offending file name in task description/title first
        if mentioned_files and any(mf.split("/")[-1] in f"{t_title} {t_desc}" for mf in mentioned_files):
            responsible_agent_id = t_aid
            responsible_task_title = t_title
            break

        if t_lane == target_lane and not responsible_agent_id:
            responsible_agent_id = t_aid
            responsible_task_title = t_title

    # Fallback: pick any onboarded custom agent matching the lane or first available worker
    if not responsible_agent_id:
        from app.services.agents.agent_service import agent_service
        all_agents = agent_service.get_all_agents(project_token)
        for a in all_agents:
            aid = a.get("id", "")
            if _is_system_id(aid):
                continue
            lanes = get_agent_lanes_from_skills(
                agent_id=aid,
                skills_tags=a.get("skills_tags"),
                specialization=a.get("specialization"),
            )
            if target_lane in lanes:
                responsible_agent_id = aid
                break
        if not responsible_agent_id:
            workers = [a["id"] for a in all_agents if not _is_system_id(a.get("id", ""))]
            responsible_agent_id = workers[0] if workers else "M_agent_01"

    offending_str = ", ".join(list(dict.fromkeys(mentioned_files[:6]))) or "Inspect entrypoint and logs below"
    hotfix_prompt = (
        f"# 🚨 URGENT PRODUCTION DEPLOYMENT HOT-FIX (Assigned by Master Agent)\n\n"
        f"- **Target Lane**: `{target_lane.upper()}`\n"
        f"- **Responsible Agent**: `{responsible_agent_id}`\n"
        f"- **Related Task Scope**: `{responsible_task_title or 'Application Runtime & Build'}`\n"
        f"- **Suspected Files**: `{offending_str}`\n\n"
        f"## Exact Deployment / Runtime Failure Captured by Deploy Agent:\n"
        f"```\n{combined[:3000]}\n```\n\n"
        "## MANDATORY HOT-FIX INSTRUCTIONS:\n"
        "1. Read the failing file(s) identified in the traceback above using `read_file`.\n"
        "2. Apply a surgical fix using `replace_file_content` or `write_file` to resolve the root cause "
        "(missing import, broken schema/model, startup crash, or build error).\n"
        "3. Verify syntax and compilation using `check_syntax` or `run_command`.\n"
        "4. Commit your hot-fix so the Deploy Agent can re-pull `main` and complete live deployment."
    )

    return {
        "target_lane": target_lane,
        "responsible_agent_id": responsible_agent_id,
        "responsible_task_title": responsible_task_title,
        "offending_files": list(dict.fromkeys(mentioned_files[:6])),
        "hotfix_prompt": hotfix_prompt,
        "error_summary": combined[:500],
    }
