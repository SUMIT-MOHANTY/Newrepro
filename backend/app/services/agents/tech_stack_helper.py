"""
Tech Stack & Skill Detection Helpers
Pure python utilities for detecting tech stacks and computing skill gaps from project context.
No external dependencies, fast and reliable.
"""
from typing import Dict, Any, List, Optional
import re
import json

TECH_STACK_SIGNALS = {
    "python": {
        "label": "Python / FastAPI / Django",
        "extensions": [".py"],
        "keywords": ["python", "fastapi", "django", "flask", "pydantic", "sqlalchemy", "poetry", "pip", "pytest"],
        "skills": ["Python", "FastAPI"],
        "templates": ["Python / Backend Developer", "Fullstack Developer"],
    },
    "javascript": {
        "label": "JavaScript / Node.js / React",
        "extensions": [".js", ".jsx", ".ts", ".tsx", ".mjs"],
        "keywords": ["react", "node", "typescript", "javascript", "express", "next.js", "vite", "npm", "tailwind"],
        "skills": ["React", "JavaScript", "TypeScript"],
        "templates": ["Frontend Developer", "Fullstack Developer"],
    },
    "java": {
        "label": "Java / Spring Boot",
        "extensions": [".java", ".gradle", ".pom"],
        "keywords": ["java", "spring", "springboot", "spring boot", "maven", "gradle", "hibernate"],
        "skills": ["Java", "Spring Boot"],
        "templates": ["Java / Backend Developer"],
    },
    "csharp": {
        "label": "C# / .NET",
        "extensions": [".cs", ".csproj", ".sln"],
        "keywords": ["c#", "dotnet", ".net", "asp.net", "nuget", "entity framework"],
        "skills": ["C#", ".NET"],
        "templates": [".NET Developer"],
    },
    "qa": {
        "label": "QA & Test Automation",
        "extensions": ["test.js", "test.py", "spec.js", "spec.ts"],
        "keywords": ["testing", "qa", "verification", "pytest", "jest", "playwright", "cypress", "unit test", "integration test"],
        "skills": ["Test Automation", "QA Verification"],
        "templates": ["QA & Verification Engineer"],
    },
}


def is_brownfield_project(project_type: Optional[str]) -> bool:
    """Check if the project is brownfield/migration/enhancement."""
    if not project_type:
        return False
    return project_type.strip().lower() in ("brownfield", "migration", "refactor", "modernization", "enhancement")


def detect_required_tech_stack(
    brd_text: str = "",
    repo_files: Optional[List[str]] = None,
    repo_structure_text: str = "",
) -> Dict[str, Any]:
    """Detect required tech stack from BRD and repo structure."""
    combined_text = (brd_text + " " + repo_structure_text).lower()
    files_lower = [f.lower() for f in (repo_files or [])]

    scores: Dict[str, int] = {k: 0 for k in TECH_STACK_SIGNALS}

    for tech_key, signals in TECH_STACK_SIGNALS.items():
        for ext in signals.get("extensions", []):
            hits = sum(1 for f in files_lower if f.endswith(ext))
            if hits > 0:
                scores[tech_key] += min(hits, 5)

        for kw in signals.get("keywords", []):
            if re.search(r'\b' + re.escape(kw) + r'\b', combined_text):
                scores[tech_key] += 2

    # Determine highest scored stack or default to javascript / python
    detected = {}
    required_skills = set()
    required_templates = set()

    for tech_key, score in scores.items():
        if score > 0:
            signals = TECH_STACK_SIGNALS[tech_key]
            detected[tech_key] = {"label": signals["label"], "score": score}
            required_skills.update(signals["skills"])
            required_templates.update(signals["templates"])

    primary = max(scores, key=scores.get) if any(scores.values()) else "javascript"
    if not detected:
        primary_signals = TECH_STACK_SIGNALS["javascript"]
        detected["javascript"] = {"label": primary_signals["label"], "score": 1}
        required_skills.update(primary_signals["skills"])
        required_templates.update(primary_signals["templates"])

    return {
        "detected": detected,
        "primary": primary,
        "required_skills": sorted(list(required_skills)),
        "required_agent_templates": sorted(list(required_templates)),
    }


def compute_skill_gaps(
    required_skills: List[str],
    required_agent_templates: List[str],
    agent_list: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Compare required skills against available agents."""
    if not agent_list:
        agent_list = []

    agent_tag_pool: List[str] = []
    for agent in agent_list:
        raw_tags = agent.get("skills_tags") or []
        if isinstance(raw_tags, str):
            try:
                raw_tags = json.loads(raw_tags)
            except Exception:
                raw_tags = [t.strip() for t in raw_tags.split(",") if t.strip()]
        if isinstance(raw_tags, list):
            agent_tag_pool.extend([str(t).lower() for t in raw_tags])
        if agent.get("specialization"):
            agent_tag_pool.append(str(agent["specialization"]).lower())
        if agent.get("name"):
            agent_tag_pool.append(str(agent["name"]).lower())

    covered = []
    missing = []

    for skill in required_skills:
        skill_lower = skill.lower()
        if any(skill_lower in tag or tag in skill_lower for tag in agent_tag_pool):
            covered.append(skill)
        else:
            missing.append(skill)

    has_gaps = len(missing) > 0
    gap_summary = (
        f"Missing skills: {', '.join(missing)}. Suggested: {', '.join(required_agent_templates)}."
        if has_gaps else "All required skills are covered."
    )

    return {
        "covered": covered,
        "missing": missing,
        "suggested_templates": required_agent_templates if has_gaps else [],
        "has_gaps": has_gaps,
        "gap_summary": gap_summary,
    }


def tag_tasks_with_required_skills(
    tasks: List[Dict[str, Any]],
    tech_stack: Dict[str, Any],
    skill_gaps: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Annotate tasks with required skills and skill flags."""
    primary = tech_stack.get("primary")
    missing_lower = {s.lower() for s in skill_gaps.get("missing", [])}
    primary_label = TECH_STACK_SIGNALS.get(primary, {}).get("label", "") if primary else ""

    for task in tasks:
        target_file = (task.get("target_file") or "").lower()
        inferred_tech = primary

        for tech_key, signals in TECH_STACK_SIGNALS.items():
            for ext in signals.get("extensions", []):
                if target_file.endswith(ext):
                    inferred_tech = tech_key
                    break

        inferred_label = TECH_STACK_SIGNALS.get(inferred_tech, {}).get("label", primary_label) if inferred_tech else primary_label
        task["required_skill"] = inferred_label or "General"

        parts = [p.lower() for p in (inferred_label.split(" / ") if inferred_label else [])]
        has_gap = any(p in missing_lower or any(p in m for m in missing_lower) for p in parts)
        task["skill_flag"] = has_gap
        if has_gap:
            task["skill_gap_message"] = f"No agent registered with skill: {inferred_label}"

    return tasks


BROWNFIELD_GENERATION_PROMPT = """
You are generating tasks for a BROWNFIELD project - enhancements, modifications, and bug fixes on top of an EXISTING repository.

CRITICAL ARCHITECTURAL CONSTRAINTS:
1. DO NOT generate any project initialization, scaffold, or setup tasks.
2. DO NOT generate greenfield folders or blank projects.
3. Every task must operate on top of the existing codebase.
4. The FIRST task MUST be: "Repo Analysis and Change Planning" (task_id: TASK-REPO-ANALYSIS).
5. All subsequent tasks must specify the exact target_file and change_type (modify | add | delete | refactor).
6. Assign every task to one of the exact Sprints listed in the AVAILABLE SPRINTS section.
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
            "EXISTING REPOSITORY STRUCTURE:",
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
        ])

    return "\n".join(lines)

