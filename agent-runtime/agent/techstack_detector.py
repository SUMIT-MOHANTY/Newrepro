"""Tech stack detector — analyzes user prompt, BRD, and workspace manifests
to determine project mode (greenfield, brownfield, migration), architecture type,
primary language, and build tools without static framework bias.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, TypedDict


class TechStackDecision(TypedDict, total=False):
    is_custom: bool
    stack: str
    reason: str
    project_mode: str              # "greenfield" | "brownfield" | "migration"
    architecture_type: str         # "frontend" | "backend" | "fullstack" | "microservice" | "cli" | "library"
    primary_language: str          # "python" | "java" | "typescript" | "javascript" | "go" | "rust" | "csharp"
    build_tool: str                # "npm" | "pnpm" | "yarn" | "pip" | "poetry" | "mvn" | "gradle" | "go" | "cargo"
    requires_starter_scaffold: bool
    source_stack: str | None       # For migration mode: stack being migrated from



DEFAULT_DECISION: TechStackDecision = {
    "is_custom": False,
    "stack": "react_vite",
    "reason": "Default responsive web application",
    "project_mode": "greenfield",
    "architecture_type": "frontend",
    "primary_language": "javascript",
    "build_tool": "npm",
    "requires_starter_scaffold": False,
}

DETECTOR_SYSTEM_PROMPT = """You are an objective software architecture classifier for an autonomous engineering runtime.
Analyze the user's project requirements, BRD, or task description to classify the technical architecture objectively without imposing default biases.

Classify the following:
1. project_mode:
   - "greenfield": Brand new application starting from scratch.
   - "brownfield": Working within an existing codebase or repository.
   - "migration": Migrating legacy code/architecture (e.g. Java 8 to 21, Python 2 to 3, monolithic to microservices, framework migration).
2. architecture_type:
   - "frontend": Client-side web UI (React, Vue, Svelte, Angular, HTML/JS).
   - "backend": Server-side API, microservice, data pipeline, or background worker.
   - "fullstack": Combined frontend UI + backend server.
   - "microservice": Distributed service / API component.
   - "cli" / "library": Command-line utility or shared SDK.
3. primary_language: "python" | "java" | "typescript" | "javascript" | "go" | "rust" | "csharp"
4. stack: Specific descriptive identifier, e.g. "java_spring_boot", "python_fastapi", "python_django", "go_gin", "node_express", "react_vite", "next_js", "vue_vite", "microservice_grpc".
5. build_tool: "mvn" | "gradle" | "pip" | "poetry" | "npm" | "pnpm" | "yarn" | "go" | "cargo"
6. requires_starter_scaffold: boolean. Always false — workspace starts 100% clean for autonomous setup from scratch.

Respond with a JSON object ONLY:
{
  "project_mode": "greenfield" | "brownfield" | "migration",
  "architecture_type": "frontend" | "backend" | "fullstack" | "microservice" | "cli" | "library",
  "primary_language": string,
  "stack": string,
  "build_tool": string,
  "requires_starter_scaffold": false,
  "is_custom": boolean,
  "reason": string
}"""


def _detect_from_workspace_files(workspace_path: str = "/workspace") -> TechStackDecision | None:
    """Detect tech stack from existing manifest files on disk (Brownfield / Repo checkout)."""
    ws = Path(workspace_path)
    if not ws.exists():
        return None

    # Check for Java Maven / Gradle
    if (ws / "pom.xml").exists() or (ws / "backend" / "pom.xml").exists():
        return {
            "is_custom": True,
            "stack": "java_maven",
            "reason": "Detected pom.xml in workspace",
            "project_mode": "brownfield",
            "architecture_type": "backend",
            "primary_language": "java",
            "build_tool": "mvn",
            "requires_starter_scaffold": False,
        }
    if (ws / "build.gradle").exists() or (ws / "build.gradle.kts").exists() or (ws / "backend" / "build.gradle").exists():
        return {
            "is_custom": True,
            "stack": "java_gradle",
            "reason": "Detected build.gradle in workspace",
            "project_mode": "brownfield",
            "architecture_type": "backend",
            "primary_language": "java",
            "build_tool": "gradle",
            "requires_starter_scaffold": False,
        }

    # Check for Python
    has_python = (ws / "requirements.txt").exists() or (ws / "pyproject.toml").exists() or (ws / "backend" / "requirements.txt").exists()
    has_node = (ws / "package.json").exists() or (ws / "frontend" / "package.json").exists()

    if has_python and has_node:
        return {
            "is_custom": True,
            "stack": "fullstack_python_node",
            "reason": "Detected both Python requirements and Node package.json in workspace",
            "project_mode": "brownfield",
            "architecture_type": "fullstack",
            "primary_language": "python",
            "build_tool": "pip",
            "requires_starter_scaffold": False,
        }
    if has_python:
        return {
            "is_custom": True,
            "stack": "python",
            "reason": "Detected Python manifest in workspace",
            "project_mode": "brownfield",
            "architecture_type": "backend",
            "primary_language": "python",
            "build_tool": "pip",
            "requires_starter_scaffold": False,
        }

    # Check for Go
    if (ws / "go.mod").exists() or (ws / "backend" / "go.mod").exists():
        return {
            "is_custom": True,
            "stack": "go_module",
            "reason": "Detected go.mod in workspace",
            "project_mode": "brownfield",
            "architecture_type": "backend",
            "primary_language": "go",
            "build_tool": "go",
            "requires_starter_scaffold": False,
        }

    # Check for Rust
    if (ws / "Cargo.toml").exists():
        return {
            "is_custom": True,
            "stack": "rust_cargo",
            "reason": "Detected Cargo.toml in workspace",
            "project_mode": "brownfield",
            "architecture_type": "backend",
            "primary_language": "rust",
            "build_tool": "cargo",
            "requires_starter_scaffold": False,
        }

    # Check for Node.js
    if (ws / "package.json").exists():
        try:
            pkg_data = json.loads((ws / "package.json").read_text(encoding="utf-8"))
            deps = {**pkg_data.get("dependencies", {}), **pkg_data.get("devDependencies", {})}
            if "next" in deps:
                stack = "next_js"
            elif "express" in deps or "nestjs" in deps or "@nestjs/core" in deps:
                stack = "node_backend"
            elif "vue" in deps:
                stack = "vue_vite"
            elif "react" in deps:
                stack = "react_vite"
            else:
                stack = "node_generic"
            return {
                "is_custom": True if stack != "react_vite" else False,
                "stack": stack,
                "reason": f"Detected existing package.json with {stack} dependencies",
                "project_mode": "brownfield",
                "architecture_type": "backend" if "backend" in stack else "frontend",
                "primary_language": "typescript" if any(k for k in deps if "typescript" in k) else "javascript",
                "build_tool": "npm",
                "requires_starter_scaffold": False,
            }
        except Exception:
            pass

    return None


def _detect_stack_from_keywords(prompt_lower: str, mode: str = "greenfield") -> TechStackDecision | None:
    """Detect stack based on keyword heuristics in prompt."""
    if any(k in prompt_lower for k in ("spring boot", "springboot", "java 21", "java 17", "java 8", "java ", "maven", "gradle", "jvm")):
        return {
            "is_custom": True,
            "stack": "java_spring_boot",
            "reason": "Detected Java / Spring Boot specification",
            "project_mode": mode,
            "architecture_type": "backend",
            "primary_language": "java",
            "build_tool": "gradle" if "gradle" in prompt_lower else "mvn",
            "requires_starter_scaffold": False,
        }

    if any(k in prompt_lower for k in ("fastapi", "flask", "django", "python backend", "python api", "sqlalchemy", "pydantic", "celery")):
        stack = "python_django" if "django" in prompt_lower else ("python_flask" if "flask" in prompt_lower else "python_fastapi")
        return {
            "is_custom": True,
            "stack": stack,
            "reason": f"Detected Python backend specification ({stack})",
            "project_mode": mode,
            "architecture_type": "backend",
            "primary_language": "python",
            "build_tool": "poetry" if "poetry" in prompt_lower else "pip",
            "requires_starter_scaffold": False,
        }

    if any(k in prompt_lower for k in ("golang", "go backend", "go ", "go/gin", "go-zero", "gorilla")):
        return {
            "is_custom": True,
            "stack": "go_backend",
            "reason": "Detected Go backend specification",
            "project_mode": mode,
            "architecture_type": "backend",
            "primary_language": "go",
            "build_tool": "go",
            "requires_starter_scaffold": False,
        }

    if any(k in prompt_lower for k in ("rust web", "actix", "axum", "tokio", "cargo")):
        return {
            "is_custom": True,
            "stack": "rust_backend",
            "reason": "Detected Rust specification",
            "project_mode": mode,
            "architecture_type": "backend",
            "primary_language": "rust",
            "build_tool": "cargo",
            "requires_starter_scaffold": False,
        }

    if any(k in prompt_lower for k in ("next.js", "nextjs", "nuxt", "remix", "astro", "vue.js", "vue 3", "svelte", "angular")):
        target = "next_js" if "next" in prompt_lower else ("vue_vite" if "vue" in prompt_lower else "custom_frontend")
        return {
            "is_custom": True,
            "stack": target,
            "reason": f"Detected modern frontend framework: {target}",
            "project_mode": mode,
            "architecture_type": "frontend",
            "primary_language": "typescript",
            "build_tool": "npm",
            "requires_starter_scaffold": False,
        }

    if any(k in prompt_lower for k in ("react", "vite", "tailwind")):
        return {
            "is_custom": False,
            "stack": "react_vite",
            "reason": "Detected React/Vite specification",
            "project_mode": mode,
            "architecture_type": "frontend",
            "primary_language": "javascript",
            "build_tool": "npm",
            "requires_starter_scaffold": False,
        }

    return None


def detect_techstack(
    prompt: str,
    llm_client: Any = None,
    model: str = "",
    workspace_path: str = "/workspace",
) -> TechStackDecision:
    """Analyze prompt, BRD, and workspace to determine technical stack and project mode."""
    prompt_lower = (prompt or "").lower()
    is_migration = any(k in prompt_lower for k in (
        "migration", "migrate", "legacy", "convert from", "port from",
        "port to", "convert to", "rewrite in", "modernize", "upgrade from"
    ))
    is_brownfield = any(k in prompt_lower for k in ("brownfield", "existing repo", "existing codebase", "clone repo", "feature branch"))
    mode = "migration" if is_migration else ("brownfield" if is_brownfield else "greenfield")

    # Priority 0: Check existing workspace files first (authoritative for Brownfield / cloned repos)
    ws_decision = _detect_from_workspace_files(workspace_path)
    if ws_decision:
        if is_migration:
            source_stack = ws_decision.get("stack", "legacy_codebase")
            target_slice = prompt_lower
            for sep in (" to ", " into ", " rewrite in ", " port to ", " modernize to ", " convert to "):
                if sep in prompt_lower:
                    target_slice = prompt_lower.split(sep, 1)[1]
                    break
            target_decision = _detect_stack_from_keywords(target_slice, mode="migration")
            if target_decision:
                target_decision["source_stack"] = source_stack
                target_decision["project_mode"] = "migration"
                target_decision["reason"] = f"Migrating from {source_stack} to {target_decision['stack']}: {target_decision['reason']}"
                return target_decision
            ws_decision = dict(ws_decision)
            ws_decision["source_stack"] = source_stack
            ws_decision["project_mode"] = "migration"
            ws_decision["reason"] = f"Codebase migration from {source_stack} ({ws_decision['reason']})"
        return ws_decision

    if not prompt or not prompt.strip():
        return dict(DEFAULT_DECISION)

    # Priority 1: Check control plane workspace config files
    try:
        for cfg_file in (
            os.path.join(workspace_path, ".agent", "task_config.json"),
            os.path.join(workspace_path, ".agent", "workspace_index.json"),
        ):
            if os.path.exists(cfg_file):
                with open(cfg_file, "r", encoding="utf-8") as f:
                    cfg_data = json.load(f)
                resolved_stack = cfg_data.get("techstack") or cfg_data.get("detected_stack")
                project_mode = cfg_data.get("project_mode", mode)
                if resolved_stack:
                    if isinstance(resolved_stack, dict):
                        be = resolved_stack.get("backend")
                        fe = resolved_stack.get("frontend")
                        stack_name = f"{fe or ''}_{be or ''}".strip("_") or "custom"
                        is_backend = bool(be)
                        return {
                            "is_custom": True if be or (fe and fe != "react_vite") else False,
                            "stack": stack_name,
                            "reason": f"Resolved from control plane workspace analysis ({cfg_file})",
                            "project_mode": project_mode,
                            "architecture_type": "fullstack" if (be and fe) else ("backend" if be else "frontend"),
                            "primary_language": "python" if "python" in str(be) else ("java" if "spring" in str(be) else "typescript"),
                            "build_tool": "pip" if "python" in str(be) else ("mvn" if "spring" in str(be) else "npm"),
                            "requires_starter_scaffold": False,
                        }
                    elif isinstance(resolved_stack, str) and resolved_stack:
                        is_react = resolved_stack in ("react_vite", "react_vite_tailwind")
                        return {
                            "is_custom": not is_react,
                            "stack": resolved_stack,
                            "reason": f"Specified in {cfg_file}",
                            "project_mode": project_mode,
                            "architecture_type": "frontend" if is_react else "backend",
                            "primary_language": "javascript" if is_react else "python",
                            "build_tool": "npm" if is_react else "pip",
                            "requires_starter_scaffold": False,
                        }
    except Exception:
        pass

    # Priority 2: Keyword-based architectural heuristics
    if is_migration:
        target_slice = prompt_lower
        source_slice = prompt_lower
        for sep in (" to ", " into ", " rewrite in ", " port to ", " modernize to ", " convert to "):
            if sep in prompt_lower:
                parts = prompt_lower.split(sep, 1)
                source_slice = parts[0]
                target_slice = parts[1]
                break
        target_decision = _detect_stack_from_keywords(target_slice, mode="migration")
        source_decision = _detect_stack_from_keywords(source_slice, mode="migration")
        if target_decision:
            src_name = source_decision["stack"] if source_decision else "legacy_codebase"
            target_decision["source_stack"] = src_name
            target_decision["project_mode"] = "migration"
            target_decision["reason"] = f"Migrating from {src_name} to {target_decision['stack']}: {target_decision['reason']}"
            return target_decision

    keyword_decision = _detect_stack_from_keywords(prompt_lower, mode=mode)
    if keyword_decision:
        return keyword_decision


    # If LLM client is available, perform objective classification
    if llm_client and hasattr(llm_client, "call_ai"):
        detection_prompt = (
            f"{DETECTOR_SYSTEM_PROMPT}\n\n"
            f"USER PROMPT / BRD:\n\"\"\"{prompt[:2000]}\"\"\"\n\n"
            "Return the JSON object:"
        )
        try:
            response = llm_client.call_ai(
                detection_prompt,
                tools=[],
                model=model,
                max_tokens=600,
            )
            raw_text = ""
            if hasattr(response, "content") and isinstance(response.content, str):
                raw_text = response.content
            elif hasattr(response, "text") and isinstance(response.text, str):
                raw_text = response.text
            elif isinstance(response, str):
                raw_text = response

            clean_json = raw_text.strip()
            match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', clean_json, re.DOTALL)
            if match:
                clean_json = match.group(0)

            data = json.loads(clean_json)
            p_mode = data.get("project_mode", mode)
            arch_type = data.get("architecture_type", "frontend")
            lang = data.get("primary_language", "javascript")
            stack = str(data.get("stack", "react_vite")).strip()
            b_tool = str(data.get("build_tool", "npm")).strip()
            req_scaffold = bool(data.get("requires_starter_scaffold", False))
            is_custom = bool(data.get("is_custom", stack != "react_vite"))
            reason = str(data.get("reason", "Objective architectural analysis")).strip()

            # Guard: Backends, Java, Python, Go must NEVER require starter scaffold
            if arch_type in ("backend", "microservice") or lang in ("java", "python", "go", "rust", "csharp") or p_mode in ("brownfield", "migration"):
                req_scaffold = False

            return {
                "is_custom": is_custom,
                "stack": stack,
                "reason": reason,
                "project_mode": p_mode,
                "architecture_type": arch_type,
                "primary_language": lang,
                "build_tool": b_tool,
                "requires_starter_scaffold": False,
            }
        except Exception as exc:
            print(f"[TechStackDetector] Warning: AI detection call failed ({exc}), falling back to heuristics.")

    # Default fallback: If prompt asks for generic UI prototype, use React; otherwise if it's general development, avoid forcing scaffold
    is_explicit_react = "react" in prompt_lower or "vite" in prompt_lower
    return {
        "is_custom": not is_explicit_react,
        "stack": "react_vite" if is_explicit_react else "generic_app",
        "reason": "Explicit React requested" if is_explicit_react else "General software application requirement",
        "project_mode": mode,
        "architecture_type": "frontend" if is_explicit_react else "fullstack",
        "primary_language": "javascript" if is_explicit_react else "python",
        "build_tool": "npm" if is_explicit_react else "pip",
        "requires_starter_scaffold": False,
    }
