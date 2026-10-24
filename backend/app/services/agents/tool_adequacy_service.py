"""
Tool Adequacy Service
---------------------
Analyses whether an agent's allowed_tools list is sufficient for its
assigned execution lanes and project tasks.

Usage::

    from app.services.agents.tool_adequacy_service import analyse_tool_adequacy

    result = analyse_tool_adequacy(
        agent_tools=["filesystem", "git", "terminal"],
        lanes={"backend"},
        tasks=[{"title": "...", "description": "..."}],
    )
    # result["status"] in ("sufficient", "warning", "critical")
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

# ---------------------------------------------------------------------------
# Canonical tool registry
# ---------------------------------------------------------------------------
ALL_KNOWN_TOOLS: List[str] = [
    "filesystem",
    "git",
    "terminal",
    "build_tool",
    "test_runner",
    "visual_qa",
    "database",
    "browser",
    "docker",
    "cloud_cli",
    "web_search",
]

# ---------------------------------------------------------------------------
# Per-lane requirements
# ---------------------------------------------------------------------------
# Each lane maps to:
#   required     – missing any of these → status "critical"
#   recommended  – missing any of these → status "warning" (if not already critical)
TOOL_REQUIREMENTS: Dict[str, Dict[str, List[str]]] = {
    "frontend": {
        "required":    ["filesystem"],
        "recommended": ["build_tool", "git", "terminal"],
    },
    "backend": {
        "required":    ["filesystem"],
        "recommended": ["build_tool", "git", "terminal"],
    },
    "database": {
        "required":    ["filesystem"],
        "recommended": ["database", "terminal", "git"],
    },
    "qa": {
        "required":    ["test_runner"],
        "recommended": ["visual_qa", "filesystem", "terminal"],
    },
    "devops": {
        "required":    ["filesystem", "terminal"],
        "recommended": ["docker", "git"],
    },
    "governance": {
        "required":    ["filesystem"],
        "recommended": ["git", "terminal"],
    },
    "integration": {
        "required":    ["filesystem"],
        "recommended": ["build_tool", "git", "terminal"],
    },
    "general": {
        "required":    ["filesystem"],
        "recommended": ["git", "terminal"],
    },
}

# ---------------------------------------------------------------------------
# Human-readable tool descriptions (used in verdict messages)
# ---------------------------------------------------------------------------
_TOOL_LABELS: Dict[str, str] = {
    "filesystem":  "File System",
    "git":         "Git",
    "terminal":    "Terminal",
    "build_tool":  "Build Tool",
    "test_runner": "Test Runner",
    "visual_qa":   "Visual QA",
    "database":    "Database",
    "browser":     "Browser",
    "docker":      "Docker",
    "cloud_cli":   "Cloud CLI",
    "web_search":  "Web Search",
}


def analyse_tool_adequacy(
    agent_tools: List[str],
    lanes: Set[str],
    tasks: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Determine whether *agent_tools* are adequate for the given *lanes*.

    Returns a dict with keys:
        status              – "sufficient" | "warning" | "critical"
        missing_required    – list[str] of tools that are required but absent
        missing_recommended – list[str] of tools that are recommended but absent
        verdict             – human-readable summary sentence
        blocked_tasks       – list of task titles whose lane has a critical gap
        suggested_tools     – union of all missing required + recommended tools
    """
    if tasks is None:
        tasks = []

    tool_set: Set[str] = {t.lower().strip() for t in (agent_tools or [])}
    active_lanes: Set[str] = {ln.lower() for ln in (lanes or {"general"})} or {"general"}

    missing_required: Set[str] = set()
    missing_recommended: Set[str] = set()
    critical_lanes: Set[str] = set()
    all_required: Set[str] = set()
    all_recommended: Set[str] = set()

    for lane in active_lanes:
        reqs = TOOL_REQUIREMENTS.get(lane, TOOL_REQUIREMENTS["general"])
        for t in reqs.get("required", []):
            all_required.add(t)
            if t not in tool_set:
                missing_required.add(t)
                critical_lanes.add(lane)
        for t in reqs.get("recommended", []):
            all_recommended.add(t)
            if t not in tool_set:
                missing_recommended.add(t)

    # Identify tasks whose lane would be critically impaired
    blocked_tasks: List[str] = []
    if missing_required and tasks:
        for task in tasks:
            title = task.get("title") or task.get("task_name") or ""
            desc = (task.get("description") or "").lower()
            task_text = (title + " " + desc).lower()
            # Quick heuristic: if the task text matches any critical lane keyword
            for lane in critical_lanes:
                if lane in task_text or _lane_keywords_match(lane, task_text):
                    blocked_tasks.append(title)
                    break

    suggested_tools: List[str] = sorted(missing_required | missing_recommended)

    if missing_required:
        status = "critical"
        missing_r_labels = ", ".join(
            _TOOL_LABELS.get(t, t) for t in sorted(missing_required)
        )
        verdict = (
            f"Critical tools missing: {missing_r_labels}. "
            "Agent execution will be blocked until these tools are assigned."
        )
    elif missing_recommended:
        status = "warning"
        missing_rc_labels = ", ".join(
            _TOOL_LABELS.get(t, t) for t in sorted(missing_recommended)
        )
        verdict = (
            f"Recommended tools missing: {missing_rc_labels}. "
            "Agent can run but may produce lower quality results."
        )
    else:
        status = "sufficient"
        verdict = "All required and recommended tools are present. Agent is ready to run."

    return {
        "status": status,
        "missing_required": sorted(missing_required),
        "missing_recommended": sorted(missing_recommended),
        "required_tools": sorted(all_required),
        "recommended_tools": sorted(all_recommended),
        "verdict": verdict,
        "blocked_tasks": blocked_tasks,
        "suggested_tools": suggested_tools,
    }


# ---------------------------------------------------------------------------
# Recommend agents for a project based on task lanes
# ---------------------------------------------------------------------------

def recommend_agents_for_project(
    task_lanes: Dict[str, int],  # {lane: task_count}
) -> List[Dict[str, Any]]:
    """
    Given a mapping of lane → task_count, return a list of recommended
    agent configurations (one per active lane).

    Each entry has:
        role        – human-readable role name
        lane        – canonical lane name
        task_count  – number of tasks in this lane
        tools       – list of required + recommended tools
        specialization – suggested specialization string
    """
    recommendations: List[Dict[str, Any]] = []

    _LANE_META: Dict[str, Dict[str, str]] = {
        "frontend":   {"role": "Frontend Agent",   "specialization": "Development"},
        "backend":    {"role": "Backend Agent",    "specialization": "Development"},
        "qa":         {"role": "QA Agent",         "specialization": "Testing"},
        "devops":     {"role": "DevOps Agent",     "specialization": "DevOps"},
        "governance": {"role": "Governance Agent", "specialization": "Governance"},
        "integration":{"role": "Integration Agent","specialization": "Development"},
        "general":    {"role": "General Agent",    "specialization": "General"},
    }

    for lane, count in task_lanes.items():
        if count == 0:
            continue
        meta = _LANE_META.get(lane, _LANE_META["general"])
        reqs = TOOL_REQUIREMENTS.get(lane, TOOL_REQUIREMENTS["general"])
        tools = list(dict.fromkeys(reqs["required"] + reqs["recommended"]))
        recommendations.append({
            "role":              meta["role"],
            "lane":              lane,
            "task_count":        count,
            "tools":             tools,
            "required_tools":    list(reqs.get("required", ["filesystem"])),
            "mandatory_tools":   list(reqs.get("required", ["filesystem"])),
            "recommended_tools": list(reqs.get("recommended", [])),
            "specialization":    meta["specialization"],
        })

    # Sort by task count descending so the busiest lane comes first
    recommendations.sort(key=lambda r: r["task_count"], reverse=True)
    return recommendations


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _lane_keywords_match(lane: str, text: str) -> bool:
    """Return True if *text* contains keywords typical for *lane*."""
    _KEYWORDS: Dict[str, List[str]] = {
        "frontend":    ["ui", "react", "css", "html", "component", "page", "view"],
        "backend":     ["api", "endpoint", "database", "server", "model", "migration"],
        "qa":          ["test", "spec", "e2e", "qa", "quality", "coverage"],
        "devops":      ["docker", "deploy", "ci", "pipeline", "infra", "k8s"],
        "governance":  ["compliance", "brd", "review", "governance", "policy"],
        "integration": ["integration", "webhook", "socket", "third-party", "external"],
    }
    for kw in _KEYWORDS.get(lane, []):
        if kw in text:
            return True
    return False
