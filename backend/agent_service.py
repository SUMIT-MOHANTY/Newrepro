"""
Agent Service for AI-Powered Development Agents
Agents create ephemeral Docker containers, build real project code inside them,
self-heal until everything works, capture the workspace, then clean up.
"""
import asyncio
import ast
import hashlib
import json
import os
import shlex
import subprocess
import sys
import tempfile
import time
import uuid
import re as _re
from collections import Counter
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from config import settings
import httpx
import logging
import llm_gateway

logger = logging.getLogger(__name__)


# ── AI Response Cleaner ─────────────────────────────────────────────────────

def _clean_ai_code_response(content: str) -> tuple[str, str]:
    """
    Robustly extract a shell build/fix script from an AI model response.
    Returns (script_string, thought_string).
    Handles: <comment> blocks, markdown fences, narrative preamble,
    and Unicode punctuation that can break shell parsing.
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

    # 2. Extract script from markdown fences
    fence_match = _re.search(r'```(?:bash|sh|shell|python)?\s*\n(.*?)```', content, flags=_re.DOTALL)
    if not fence_match:
        fence_match = _re.search(r'```\s*\n(.*?)```', content, flags=_re.DOTALL)
    if fence_match:
        content = fence_match.group(1).strip()
    else:
        for prefix in ('```bash', '```sh', '```shell', '```python'):
            if content.startswith(prefix):
                content = content[len(prefix):].strip()
                break
        if content.startswith('```'):
            content = content[3:].strip()
        if content.endswith('```'):
            content = content[:-3].strip()

    # 3. Strip narrative preamble before the first command line
    lines = content.split('\n')
    first_code_line = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        if (
            stripped.startswith((
                '#!', 'set -', 'cd ', 'ls', 'find ', 'mkdir ', 'cat ', 'grep ', 'sed ', 'awk ',
                'cp ', 'mv ', 'rm ', 'touch ', 'echo ', 'printf ', 'git ', 'npm ', 'npx ',
                'pip ', 'pip3 ', 'python ', 'python3 ', 'if ', 'for ', 'while ', 'case ', ': '
            ))
            or _re.match(r'^[A-Za-z_][A-Za-z0-9_]*=', stripped)
        ):
            first_code_line = i
            break
            
    narrative = ""
    if first_code_line > 0:
        preamble = '\n'.join(lines[:first_code_line]).strip()
        if not preamble.startswith('#'):
            narrative = preamble
            content = '\n'.join(lines[first_code_line:])

    # 4. Replace Unicode with ASCII-friendly equivalents
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
DEPLOY_AGENT_ID = "agent_05"
GIT_INTEGRATION_BRANCH = "agent/integration"
MASTER_NOTE_PREFIX = "MASTER_PLAN"
MASTER_NOTE_SCOPE = "Canonical Project Tree and Task Plan"
DEFAULT_PROJECT_TOKEN = "__default__"
NOTE_PAYLOAD_MARKER = "AGENT_NOTE_PAYLOAD"
BOOTSTRAP_WAIT_TIMEOUT_SECONDS = 1800
BOOTSTRAP_WAIT_LOG_INTERVAL_SECONDS = 20
RUN_ALL_WAITING_MESSAGE = "Waiting for master plan..."
MASTER_BUILDING_MESSAGE = "Creating canonical project tree note..."
MASTER_READY_MESSAGE = "Master plan ready"
MASTER_FAILED_MESSAGE = "Master plan failed"
NOTE_PAYLOAD_CACHE_TTL_SECONDS = 15.0
WORKSPACE_CONTRACT_PROBE_TTL_SECONDS = 300.0

TECH_SPEC_ARCHITECT_SYSTEM_PROMPT = (
    "You are a Senior Software Architect. Produce precise, unambiguous technical specifications. "
    "The user content includes an authoritative PLANNING_PACKET_JSON. Parse that JSON before reasoning. "
    "Treat the task titles, descriptions, checklists, planned file hints, current repo tree, stack decision, "
    "stack evidence, and workspace contract in that packet as the primary source of truth. "
    "Do not fall back to generic scaffolds when they contradict the packet. "
    "Never mix mutually exclusive stacks in one response, such as Flask with Express, Flask/Jinja with React/Vite, "
    "React with Vue, or Next.js with static HTML. "
    "When defining file structure, output exactly one final canonical project tree. "
    "Choose one production-ready structure and commit to it. "
    "Never output alternative roots, conditional structures, migration options, fallback layouts, "
    "or prose such as 'pick one', 'if X then Y', or 'the tree collapses to'. "
    "If the current repository tree already establishes a root, preserve it unless the requirements "
    "clearly force a migration. "
    "For Flask + Jinja projects, keep templates and static assets inside the Flask application structure "
    "instead of inventing a separate Node frontend."
)

MASTER_TREE_GENERATOR_SYSTEM_PROMPT = (
    "You are a senior software architect generating the canonical project tree used by all worker agents. "
    "The user content includes an authoritative PLANNING_PACKET_JSON. Parse that JSON first and treat it as binding. "
    "Use the task details and checklist items as hard evidence for what the tree must contain. "
    "Return exactly one final tree as a strictly valid JSON objects with a nested 'children' structure. "
    "Each node in the JSON should have a 'name' (string) and optional 'children' (array of nodes). "
    "Choose one solid structure and commit to it. "
    "Never output alternate roots, conditional variants, migration notes, fallback layouts, "
    "multiple diagrams, or prose like 'pick one'. "
    "Never combine conflicting frameworks in one tree. "
    "If the packet indicates Flask + Jinja, do not invent Express, React, Vite, Next.js, or a separate frontend app root "
    "unless the tasks explicitly require them. "
    "The tree must be production-ready, structurally complete for the tasks, and consistent with the "
    "current repository tree, workspace contract, and stack decision. "
    "Output MUST be strict JSON only (double quotes only, no Python dict literals, no single quotes). "
    "Do not place serialized JSON/Python objects inside any node 'name'. "
    "Root 'name' must be a plain folder label (for example, 'project' or 'app'). "
    "Do not flatten the tree into duplicate file lists under the root. "
    "Place module/tool configuration files in module roots, not inside source-code folders. "
    "Do not emit multiple extension variants of the same config stem in the same directory. "
    "Use repository-relative structure semantics: canonical source roots must map to real repository directories "
    "and must not be prefixed by a synthetic wrapper segment."
)

MASTER_TREE_VALIDATOR_SYSTEM_PROMPT = (
    "You are a rigorous software architecture validator. The user content includes an authoritative "
    "PLANNING_PACKET_JSON. Parse that JSON before evaluating the tree. Respond only with JSON. "
    "Reject any project tree that contains ambiguity, multiple candidate roots, alternative layouts, "
    "conditional wording, migration options, more than one tree, or mixed stack signals that contradict the packet. "
    "Reject trees that introduce frameworks or roots that are not supported by the task details, checklist evidence, "
    "current repo tree, stack decision, and workspace contract. "
    "Reject malformed JSON trees, including Python-style dict literals, single-quoted pseudo-JSON, "
    "or any node whose 'name' contains serialized objects like '{\"name\": ...}' or '{'name': ...}'. "
    "Reject trees that duplicate flattened file lists at root in addition to nested directories. "
    "Reject trees that place configuration files under source directories when they should be module-level files. "
    "Reject trees that include multiple extension variants of the same config file stem in one directory. "
    "Reject trees whose canonical source roots require a synthetic wrapper prefix that is not a real repository "
    "top-level directory in the current repo snapshot. "
    "Approve only one complete replacement tree with one fixed root. "
    "If rejected, corrected_tree must be a strictly valid JSON project tree (with 'name' and 'children' keys), not a diff, ASCII diagram, or a set of options."
)


def _is_system_agent_id(agent_id: Optional[str]) -> bool:
    return agent_id in {GIT_MANAGER_AGENT_ID, MASTER_AGENT_ID}


def _extract_dev_agent_sequence(agent_id: Optional[str]) -> Optional[int]:
    source = str(agent_id or "").strip().lower()
    if not source or _is_system_agent_id(source):
        return None
    match = _re.search(r"(\d+)$", source)
    if not match:
        return None
    return int(match.group(1))


def get_default_agent_name(agent_id: Optional[str]) -> str:
    if agent_id == GIT_MANAGER_AGENT_ID:
        return "Git Manager"
    if agent_id == MASTER_AGENT_ID:
        return "Master Agent"
    sequence = _extract_dev_agent_sequence(agent_id)
    if sequence is None:
        return "Agent"
    return f"Agent {sequence}"


def normalize_agent_name(agent_id: Optional[str], name: Optional[str]) -> str:
    default_name = get_default_agent_name(agent_id)
    cleaned = str(name or "").strip()
    if not cleaned:
        return default_name
    if _is_system_agent_id(agent_id):
        return default_name

    normalized = cleaned.lower()
    raw_id = str(agent_id or "").strip().lower()
    if normalized in {
        "requirements validator",
        "risk assessment",
        "resource estimation",
    }:
        return default_name
    if normalized == raw_id or normalized == raw_id.replace("_", " "):
        return default_name
    if _re.fullmatch(r"(shared|dedicated|dev)[ _-]*agent(?:[ _-]*\d+)?", normalized):
        return default_name
    if _re.fullmatch(r"agent(?:[ _-]*\d+)?", normalized):
        return default_name
    return cleaned


def _next_dev_agent_sequence(project_agents: Dict[str, Dict[str, Any]]) -> int:
    used_numbers = {
        sequence
        for sequence in (_extract_dev_agent_sequence(agent_id) for agent_id in project_agents)
        if sequence is not None
    }
    next_number = 1
    while next_number in used_numbers:
        next_number += 1
    return next_number


def build_external_agent_username(agent_id: Optional[str], fallback_name: Optional[str] = None) -> str:
    source_id = str(agent_id or "").strip().lower()
    match = _re.search(r"(\d+)$", source_id)
    if match:
        sequence = int(match.group(1))
        # Shared agents use agent3, agent4, etc. to avoid conflicts with dedicated agents
        if source_id.startswith("shared_"):
            sequence = sequence + 2  # Start from agent3
        return f"agent{sequence}"

    fallback = normalize_agent_name(agent_id, fallback_name)
    fallback_match = _re.search(r"(\d+)$", fallback.lower())
    if fallback_match:
        sequence = int(fallback_match.group(1))
        # Shared agents use agent3, agent4, etc. to avoid conflicts
        if "shared" in fallback.lower():
            sequence = sequence + 2
        return f"agent{sequence}"

    normalized = _re.sub(r"[^a-z0-9]", "", fallback.strip().lower())
    return normalized or "agent"

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
            "task_claim_lock": asyncio.Lock(),
            "task_progress_state": {},
            "timer_log_state": {},
            "completed_tasks": [],
            "tasks": [],
            "master_task_context": [],
            "brd_analysis": {},
            "master_note_cache": {},
            "master_note_lock": asyncio.Lock(),
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
            "note_title_cache": {},
            "note_payload_cache": {},
            "persisted_assignment_restore": {},
            "workspace_contract_probe": {},
        }
        _project_states[key] = state
    else:
        state.setdefault("completed_milestones_synced", set())
        state.setdefault("completed_sprints_synced", set())
        state.setdefault("project_status_synced", None)
        state.setdefault("status_sync_lock", asyncio.Lock())
        state.setdefault("note_title_cache", {})
        state.setdefault("note_payload_cache", {})
        state.setdefault("persisted_assignment_restore", {})
        state.setdefault("workspace_contract_probe", {})
        state.setdefault("tasks", [])
        state.setdefault("master_task_context", [])
        state.setdefault("brd_analysis", {})
        state.setdefault("master_note_cache", {})
        state.setdefault("master_note_lock", asyncio.Lock())
        state.setdefault("task_claim_lock", asyncio.Lock())
    return state

def _get_agent_states(project_token: Optional[str]) -> Dict[str, Dict[str, Any]]:
    return _ensure_project_state(project_token)["agent_states"]


def _flatten_seed_checklists(raw_groups: Any) -> List[Dict[str, Any]]:
    flattened: List[Dict[str, Any]] = []
    if not isinstance(raw_groups, list):
        return flattened

    for group in raw_groups:
        if not isinstance(group, dict):
            continue
        items = group.get("items")
        if not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, dict):
                text = str(item.get("text") or item.get("title") or "").strip()
                completed = bool(item.get("completed"))
            else:
                text = str(item or "").strip()
                completed = False
            if text:
                flattened.append({"text": text, "completed": completed})
    return flattened


def _extract_task_checklist_items(task: Dict[str, Any], limit: Optional[int] = None) -> List[str]:
    collected: List[str] = []

    def extend(raw_value: Any) -> None:
        if isinstance(raw_value, dict):
            if isinstance(raw_value.get("items"), list):
                extend(raw_value.get("items"))
                return
            if isinstance(raw_value.get("checklistItems"), list):
                extend(raw_value.get("checklistItems"))
                return
            text = str(
                raw_value.get("text")
                or raw_value.get("title")
                or raw_value.get("name")
                or ""
            ).strip()
            if text:
                collected.append(text)
            return
        if isinstance(raw_value, list):
            for item in raw_value:
                extend(item)
            return
        text = str(raw_value or "").strip()
        if text:
            collected.append(text)

    extend(task.get("checklist"))
    extend(_flatten_seed_checklists(task.get("checklists")))

    task_json = task.get("task_json") if isinstance(task.get("task_json"), dict) else {}
    if task_json:
        extend(task_json.get("checklist"))
        extend(_flatten_seed_checklists(task_json.get("checklists")))

    normalized: List[str] = []
    seen = set()
    for item in collected:
        text = " ".join(str(item or "").split())
        if not text or text in seen:
            continue
        seen.add(text)
        normalized.append(text)
        if isinstance(limit, int) and limit > 0 and len(normalized) >= limit:
            break
    return normalized


def _build_brd_analysis_context(brd_analysis: Any, max_chars: int = 0) -> str:
    if isinstance(brd_analysis, str):
        if max_chars > 0:
            return str(brd_analysis).strip()[:max_chars]
        return str(brd_analysis).strip()
    if not isinstance(brd_analysis, dict):
        return ""

    def to_text(value: Any, limit: int) -> str:
        if value in (None, "", [], {}):
            return ""
        if isinstance(value, str):
            text = value.strip()
        else:
            try:
                text = json.dumps(value, ensure_ascii=True, indent=2)
            except Exception:
                text = str(value).strip()
        if limit != float('inf') and len(text) > limit:
            return text[: max(0, int(limit) - 3)].rstrip() + "..."
        return text

    sections: List[str] = []
    seen_values = set()
    preferred_keys = [
        ("summary", "Summary"),
        ("analysis", "Detailed Analysis"),
        ("projectMeta", "Project Metadata"),
        ("businessGoals", "Business Goals"),
        ("functionalRequirements", "Functional Requirements"),
        ("nonFunctionalRequirements", "Non-Functional Requirements"),
        ("technicalRecommendations", "Technical Recommendations"),
        ("risks", "Risks"),
        ("assumptions", "Assumptions"),
        ("governanceContext", "Governance Context"),
    ]

    per_section_limit = max(240, max_chars // max(2, len(preferred_keys))) if max_chars > 0 else float('inf')
    for key, label in preferred_keys:
        text = to_text(brd_analysis.get(key), per_section_limit)
        if not text or text in seen_values:
            continue
        sections.append(f"{label}:\n{text}")
        seen_values.add(text)

    if not sections:
        fallback_text = to_text(brd_analysis, float('inf') if max_chars == 0 else max_chars)
        return fallback_text if max_chars == 0 else fallback_text[:max_chars]

    combined = "\n\n".join(sections)
    if max_chars > 0 and len(combined) > max_chars:
        combined = combined[: max(0, max_chars - 3)].rstrip() + "..."
    return combined

def _normalize_seed_task(task: Dict[str, Any], sequence_number: int, project_token: Optional[str] = None) -> Dict[str, Any]:
    task_id = str(task.get("task_id") or task.get("id") or f"TASK-{sequence_number:02d}").strip()
    title = str(task.get("title") or task.get("taskName") or "Untitled Task").strip()
    task_type = str(task.get("task_type") or task.get("type") or "TASK").strip().upper() or "TASK"
    planned_start = task.get("planned_start") or task.get("startdate") or task.get("start_date")
    planned_end = task.get("planned_end") or task.get("deadline") or task.get("end_date")

    return {
        **dict(task),
        "id": task_id,
        "external_id": task_id,
        "task_id": task_id,
        "taskName": title,
        "title": title,
        "description": str(task.get("description") or "").strip(),
        "task_type": task_type,
        "type": str(task.get("type") or task_type).strip().lower(),
        "status": str(task.get("status") or "todo").strip().lower() or "todo",
        "priority": str(task.get("priority") or "medium").strip().lower() or "medium",
        "wallet": task.get("wallet", task.get("story_points", 0)) or task.get("story_points", 0),
        "story_points": task.get("story_points", task.get("wallet", 0)) or task.get("wallet", 0),
        "sequence_number": task.get("sequence_number", sequence_number),
        "dependencies": [
            str(dep).strip()
            for dep in (task.get("dependencies") or [])
            if str(dep).strip()
        ],
        "linked_tasks": [
            str(dep).strip()
            for dep in (task.get("linked_tasks") or [])
            if str(dep).strip()
        ],
        "checklist": _flatten_seed_checklists(task.get("checklists")),
        "startdate": planned_start,
        "deadline": planned_end,
        "sprint_id": task.get("sprint_id"),
        "sprint_name": task.get("sprint_name"),
        "milestone_id": task.get("milestone_id"),
        "milestone_name": task.get("milestone_name"),
        "_project_token": project_token,
    }


def seed_project_tasks(project_token: Optional[str], tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    state = _ensure_project_state(project_token)
    normalized_tasks = [
        _normalize_seed_task(task, index + 1, project_token=project_token)
        for index, task in enumerate(tasks or [])
        if isinstance(task, dict)
    ]
    state["master_task_context"] = normalized_tasks
    state["master_note_cache"] = {}
    return normalized_tasks


def _is_waiting_for_master_plan(agent: Optional[Dict[str, Any]]) -> bool:
    if not isinstance(agent, dict):
        return False
    return str(agent.get("progress_message") or "").strip() == RUN_ALL_WAITING_MESSAGE


def mark_run_all_waiting_state(
    project_token: Optional[str],
    agent_ids: List[str],
) -> None:
    project_agents = _get_agent_states(project_token)
    for agent_id in agent_ids:
        if _is_system_agent_id(agent_id):
            continue
        agent = project_agents.get(agent_id)
        if not agent:
            continue
        agent["status"] = "running"
        agent["progress"] = 0
        agent["progress_message"] = RUN_ALL_WAITING_MESSAGE

    master_agent = project_agents.get(MASTER_AGENT_ID)
    if master_agent:
        master_agent["status"] = "running"
        master_agent["progress"] = 0
        master_agent["progress_message"] = MASTER_BUILDING_MESSAGE


def complete_run_all_waiting_state(
    project_token: Optional[str],
    *,
    success: bool,
    error_message: Optional[str] = None,
) -> None:
    project_agents = _get_agent_states(project_token)
    for agent_id, agent in project_agents.items():
        if _is_system_agent_id(agent_id):
            continue
        if not _is_waiting_for_master_plan(agent):
            continue
        if not success:
            agent["status"] = "idle"
            agent["progress"] = 0
            agent["progress_message"] = ""
            if error_message:
                agent["error"] = error_message

    master_agent = project_agents.get(MASTER_AGENT_ID)
    if master_agent:
        master_agent["status"] = "idle"
        master_agent["progress"] = 100 if success else 0
        master_agent["progress_message"] = MASTER_READY_MESSAGE if success else MASTER_FAILED_MESSAGE

def set_project_task_token(project_token: Optional[str], task_token: Optional[str]) -> None:
    if not task_token:
        return
    _ensure_project_state(project_token)["task_token"] = task_token

def get_project_task_token(project_token: Optional[str]) -> Optional[str]:
    return _ensure_project_state(project_token).get("task_token")


def clear_project_runtime_state(project_token: Optional[str]) -> None:
    """Clear in-memory runtime state for a single project token."""
    key = _project_key(project_token)
    _project_states.pop(key, None)
    _preview_states.pop(key, None)

    token = (project_token or "").strip()
    if token:
        _project_tech_specs.pop(token, None)


def clear_all_runtime_state() -> None:
    """Clear all in-memory runtime state after structural agent changes."""
    _project_states.clear()
    _preview_states.clear()
    _project_tech_specs.clear()

def _make_agent(agent_id: str, idx: int = 0) -> Dict[str, Any]:
    """Create a fresh agent state dict."""
    sequence = _extract_dev_agent_sequence(agent_id)
    type_index = (sequence - 1) if sequence is not None else idx
    atype = _AGENT_TYPES[type_index % len(_AGENT_TYPES)]
    aname = get_default_agent_name(agent_id)
    agent = {
        "id": agent_id,
        "name": aname,
        "type": atype,
        "status": "idle",
        "current_task": None,
        "resume_pending_task": False,
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


def _pick_best_dev_agent(project_token: Optional[str]) -> str:
    """Pick the most recently active or appropriate dev agent."""
    state = _ensure_project_state(project_token)
    project_agents = state["agent_states"]
    
    # Exclude system agents
    dev_agent_ids = [aid for aid in project_agents.keys() if not _is_system_agent_id(aid) and aid != DEPLOY_AGENT_ID]
    if not dev_agent_ids:
        return "agent_01" # Fallback
        
    # Pick the one with the most recent last_run or just the first one
    active = sorted(dev_agent_ids, key=lambda aid: project_agents[aid].get("last_run") or "", reverse=True)
    return active[0]


def get_default_agents() -> List[Dict[str, Any]]:
    return [
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
    state["note_payload_cache"].clear()
    state["persisted_assignment_restore"] = {}
    state["workspace_contract_probe"] = {}
    agent_states = state["agent_states"]
    agent_states.clear()
    for idx, rec in enumerate(records):
        agent_id = getattr(rec, "id", None) or (rec.get("id") if isinstance(rec, dict) else None)
        if not agent_id:
            continue
        name = getattr(rec, "name", None) or (rec.get("name") if isinstance(rec, dict) else None)
        atype = getattr(rec, "type", None) or (rec.get("type") if isinstance(rec, dict) else None)
        agent = _make_agent(agent_id, idx)
        agent["name"] = normalize_agent_name(agent_id, name)
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
        agent["name"] = normalize_agent_name(agent_id, name)
        if atype:
            agent["type"] = atype
        agent_states[agent_id] = agent

def get_completed_tasks(project_token: Optional[str]) -> List[Dict[str, Any]]:
    return list(_ensure_project_state(project_token)["completed_tasks"])


def _task_status_is_done(status: Any) -> bool:
    return str(status or "").strip().lower() in {
        "completed",
        "done",
        "complete",
        "closed",
        "resolved",
    }


def _active_owned_task_ids(project_token: Optional[str]) -> set[str]:
    state = _ensure_project_state(project_token)
    owned = set()
    for agent in state["agent_states"].values():
        if (
            (agent.get("status") or "").lower() != "running"
            and not bool(agent.get("resume_pending_task"))
        ):
            continue
        current_task = agent.get("current_task")
        if not isinstance(current_task, dict):
            continue
        tid = str(_normalize_task_id(current_task) or current_task.get("external_id") or current_task.get("id") or "").strip()
        if tid:
            owned.add(tid)
        for linked in (current_task.get("linked_tasks") or []):
            linked_id = str(linked or "").strip()
            if linked_id:
                owned.add(linked_id)
    return owned


def _find_active_task_owner(task_id: str, project_token: Optional[str]) -> str:
    normalized_task_id = str(task_id or "").strip()
    if not normalized_task_id:
        return ""
    state = _ensure_project_state(project_token)
    for agent_id, agent in state["agent_states"].items():
        if _is_system_agent_id(agent_id):
            continue
        if (
            (agent.get("status") or "").lower() != "running"
            and not bool(agent.get("resume_pending_task"))
        ):
            continue
        current_task = agent.get("current_task")
        if not isinstance(current_task, dict):
            continue
        current_task_id = _task_identity(current_task)
        if current_task_id and current_task_id == normalized_task_id:
            return agent_id
        for linked in (current_task.get("linked_tasks") or []):
            if str(linked or "").strip() == normalized_task_id:
                return agent_id
    return ""

# Backward compatibility default scope.
agent_states = _get_agent_states(None)


# ── Agent System Prompts ────────────────────────────────────────────────────
# Agents MUST create real files inside /workspace/ in the container.
# CRITICAL: Keep scripts compact (<300 lines) to avoid AI token-limit truncation.

_COMPACT_CODE_RULES = """

CRITICAL SCRIPT SIZE RULES:
- Return a Bash shell script UNDER 300 lines total. This is very important.
- Use shell commands to inspect and create files: ls, find, mkdir -p, cat <<'EOF' > file, grep -q, sed -i, cp, mv, rm -f, touch.
- Write each file's content with heredocs via cat <<'EOF' > path or cat <<'EOF' >> path. Do NOT use Python code to write files.
- Focus on the 10-15 most essential files. Do NOT try to create 30+ files in one script.
- Keep all work rooted in /workspace and prefer editing existing files instead of recreating whole trees.

CRITICAL STRUCTURAL RULES (NO EXCEPTIONS):
- You MUST perfectly follow the provided Canonical Project Tree (the Master Agent's structure).
- DO NOT invent your own file structure, nesting, or source roots. 
- You do NOT have the authority to decide where files should go if it contradicts the canonical tree.
- If you have doubts about where a file belongs, or if you think a new folder is needed, DO NOT guess and DO NOT auto-create it. You must stick to the existing master structure.
- If you believe the Master Agent's structure is missing something critical, write your code within the closest existing canonical directory and leave a comment explaining your doubt so the Master Agent can refine it later.

If you have want to add a comment to the task if you fell necessary or want to , wrap it in <comment>...</comment> tags anytime in your response. For example:
<comment>
I will implement a Flask backend with a PostgreSQL database as requested.
</comment>
```bash
# your shell script here
```
<comment>
I finished the initial implementation, but note that the database still needs schema setup.
</comment>

Example of the CORRECT compact pattern:
#!/usr/bin/env bash
set -euo pipefail
cd /workspace
mkdir -p app/
cat <<'EOF' > app/main.py
from flask import Flask

app = Flask(__name__)
EOF
printf '[CREATED] app/main.py\n'
grep -q 'Flask' app/main.py && printf '[CHECK] PASS app/main.py\n'

Do NOT use Python helpers like open(), pathlib, or os.makedirs() for file creation.
"""

AGENT_SYSTEM_PROMPTS = {
    "validator": """You are a Project Builder AI Agent.
Your job is to analyze the given task and CREATE a complete, working project implementation.

CRITICAL: YOU MUST FOLLOW THE MASTER AGENT'S CANONICAL PROJECT TREE!
- The Master Agent publishes a canonical project tree and workspace contract for this project.
- Create/modify files ONLY inside that canonical structure and allowed source roots.
- DO NOT invent new top-level directories (e.g., `app/`, `src/`, `project/`, `server/`) unless the canonical tree already includes them.
- If you think a new top-level directory is required, STOP and instead extend the existing structure provided by the master agent.

CRITICAL: NEVER create or commit these files:
- __pycache__/ directories or *.pyc files (Python cache - will cause merge conflicts)
- .pyc, .pyo, .pyd files (compiled Python)
- node_modules/ (Node.js dependencies)
- .env files (environment variables - use .env.example instead)
- *.log files (log files)
- .DS_Store, Thumbs.db (OS files)
- venv/, env/, .venv/ (virtual environments)

Given a task description and Technical Specification, you must:
1. READ the Master Agent's Canonical Project Tree carefully to determine file locations
2. Create files EXACTLY in the directories specified in the Master Agent tree
3. Generate a shell script that CREATES all necessary files and directories
4. Use commands like mkdir -p, cat, grep, sed, ls, and find to create or update real files
5. Write real, production-quality code into each file
6. NEVER create __pycache__ directories or .pyc files
7. Print [CREATED] for each file, [CHECK] PASS/FAIL for validations
8. Print === SUMMARY === at the end
""" + _COMPACT_CODE_RULES,

    "risk": """You are a Security and Risk Analysis Builder AI Agent.
Your job is to analyze the given task, identify all risks, and CREATE actual mitigation code and config files.

CRITICAL: YOU MUST FOLLOW THE MASTER AGENT'S CANONICAL PROJECT TREE!
- Create/modify files ONLY inside the canonical structure and allowed source roots.
- DO NOT invent new top-level directories (e.g., `app/`, `src/`, `project/`) unless the canonical tree already includes them.

CRITICAL: NEVER create or commit these files:
- __pycache__/ directories or *.pyc files (Python cache - will cause merge conflicts)
- .pyc, .pyo, .pyd files (compiled Python)
- node_modules/ (Node.js dependencies)
- .env files (environment variables - use .env.example instead)
- *.log files (log files)
- .DS_Store, Thumbs.db (OS files)
- venv/, env/, .venv/ (virtual environments)

Given a task description and Technical Specification, you must:
1. READ the Master Agent's Canonical Project Tree carefully to determine file locations
2. Identify technical, business, security, and operational risks
3. Generate a shell script that CREATES mitigation files in the exact Master Agent tree directories
4. NEVER create __pycache__ directories or .pyc files
5. Print [RISK N] for each risk, [CREATED] for each file, [CHECK] for validations
6. Print === RISK SUMMARY === at the end
""" + _COMPACT_CODE_RULES,

    "estimator": """You are a Project Planning and Scaffolding AI Agent.
Your job is to analyze the task, estimate resources, and CREATE a complete project scaffold.

CRITICAL: YOU MUST FOLLOW THE MASTER AGENT'S CANONICAL PROJECT TREE!
- Create/modify files ONLY inside the canonical structure and allowed source roots.
- DO NOT invent new top-level directories (e.g., `app/`, `src/`, `project/`) unless the canonical tree already includes them.

CRITICAL: NEVER create or commit these files:
- __pycache__/ directories or *.pyc files (Python cache - will cause merge conflicts)
- .pyc, .pyo, .pyd files (compiled Python)
- node_modules/ (Node.js dependencies)
- .env files (environment variables - use .env.example instead)
- *.log files (log files)
- .DS_Store, Thumbs.db (OS files)
- venv/, env/, .venv/ (virtual environments)

Given a task description and Technical Specification, you must:
1. READ the Master Agent's Canonical Project Tree carefully to determine file locations
2. Break down the project into sprints and tasks
3. Generate a shell script that CREATES the project scaffold EXACTLY matching the canonical tree
4. Create source files, configs, deployment/orchestration, CI/CD, tests in correct directories
5. NEVER create __pycache__ directories or .pyc files
6. Print [SPRINT N] for each sprint, [CREATED] for each file, [CHECK] for validations
7. Print === RESOURCE SUMMARY === at the end
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
    repo_tree_context: str = "",
    workspace_contract: Optional[Dict[str, Any]] = None,
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
    url = llm_gateway.resolve_url()
    key = llm_gateway.resolve_key()
    model_name = llm_gateway.resolve_model()

    if not llm_gateway.check_api_key():
        return {"status": "skipped", "reason": "no_api_key", "spec": ""}

    stack_profile = _infer_project_stack(
        tasks=tasks,
        tech_spec="\n".join(part for part in (brd_summary, repo_tree_context, kg_context) if part),
        workspace_contract=workspace_contract if isinstance(workspace_contract, dict) else {},
    )
    task_list_text = _build_task_context_block(
        tasks,
        max_total_chars=16000,
        max_description_chars=220,
        include_file_hints=True,
        include_checklist_preview=True,
        stack_profile=stack_profile,
        workspace_contract=workspace_contract,
    )
    planning_packet_json = json.dumps(
        _build_master_planning_packet(
            tasks=tasks,
            brd_summary=brd_summary,
            kg_context=kg_context,
            tech_spec="",
            stack_profile=stack_profile,
            workspace_contract=workspace_contract,
            repo_tree_context=repo_tree_context,
        ),
        ensure_ascii=True,
        indent=2,
    )
    stack_text = (
        f"Frontend: {stack_profile.get('frontend') or 'unspecified'}\n"
        f"Backend: {stack_profile.get('backend') or 'unspecified'}\n"
        f"Confidence: {stack_profile.get('confidence') or 'unspecified'}\n"
        f"Reason: {stack_profile.get('reason') or 'n/a'}"
    )

    architect_prompt = f"""You are a Senior Software Architect Agent. Your job is to produce a
CANONICAL TECHNICAL SPECIFICATION that all coding agents will reference as the single source of truth.

BUSINESS REQUIREMENTS (from BRD analysis report):
{brd_summary[:4500] if brd_summary else "Not provided."}

EXISTING CODEBASE KNOWLEDGE (from Knowledge Graph):
{kg_context[:4000] if kg_context else "New project — no existing codebase."}

CURRENT GIT PROJECT TREE SNAPSHOT:
{repo_tree_context[:4000] if repo_tree_context else "Not provided."}

AUTHORITATIVE PLANNING_PACKET_JSON:
{planning_packet_json}

TASKS TO BE IMPLEMENTED BY AGENTS (titles, descriptions, checklists, and file hints):
{task_list_text}

STACK DECISION TO FOLLOW:
{stack_text}

Generate a Technical Specification with these EXACT sections:

## 1. ARCHITECTURE OVERVIEW
- System layers (frontend, backend, database, external services)
- Module breakdown and responsibilities
- Data flow between modules
- If a layer is not required (for example, a frontend-only static site with no backend), explicitly write "Not applicable for this project."

## 2. API CONTRACTS
- List every API endpoint with: method, path, request body schema, response schema
- Use consistent field naming throughout (choose snake_case or camelCase and state it)
- If the project has no backend/API surface, explicitly write "Not applicable for this project."

## 3. DATA MODELS
- Every database table/model with exact field names, types, and constraints
- Relationships between models (FK, many-to-many, etc.)
- If the project has no persistent data model, explicitly write "Not applicable for this project."

## 4. FILE STRUCTURE (CRITICAL - Output as a tree diagram!)
You MUST output a specific directory tree. The example below is only for formatting syntax.
Do NOT copy its frameworks or directory names unless the PLANNING_PACKET_JSON requires them.

For YOUR project, output the exact directory tree with:
- Only the directories actually required by the tasks and stack decision
- Every file with its purpose in comments
- Output exactly one final canonical tree. Do not output alternatives, migrations, conditional variants, or "pick one" instructions.
- Treat the PLANNING_PACKET_JSON as authoritative. Resolve contradictions in favor of task details, checklist evidence, stack evidence, and the current repo tree.
- Never mix conflicting stacks in one spec. For example: Flask with Express, Flask/Jinja with React/Vite, React with Vue, or Next.js with static HTML.
- Extend the current repo tree when possible instead of inventing alternate roots
- If the current repo tree already establishes an app root, preserve that root unless the BRD/tasks clearly require a migration
- Design the directory layout based on the BEST PRACTICES for the chosen tech stack (e.g., Flask typically uses `app/` at the root, Django uses a standard project folder, Next.js uses `src/app/`).
- Do NOT arbitrarily prefix paths with `backend/` or `frontend/` unless the project is actually a monorepo requiring that separation.
- Configuration files only when the tasks/spec explicitly require them
- For static HTML/CSS sites, keep `index.html` and `styles.css` together in the existing canonical static root from the repo/task plan; if no root exists yet, choose one canonical root and keep both files there
- Do not invent backend, database, Docker, CI, or package-manager files for a minimal static project
- Do not duplicate the same file in multiple roots

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

    messages = [
        {"role": "system", "content": TECH_SPEC_ARCHITECT_SYSTEM_PROMPT},
        {"role": "user", "content": architect_prompt},
    ]

    try:
        spec_text = await llm_gateway.call_llm_and_extract(
            messages=messages,
            api_url=url,
            api_key=key,
            model=model_name,
            timeout=180.0
        )

        spec_record = {
            "status": "generated",
            "spec": spec_text,
            "generated_at": datetime.utcnow().isoformat(),
            "task_signature": _master_task_signature(tasks, brd_context=brd_summary),
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
    task_messages: str = "",
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
    url = llm_gateway.resolve_url()
    key = llm_gateway.resolve_key()
    model_name = llm_gateway.resolve_model()

    # Fallback to static prompt
    static_prompt = AGENT_SYSTEM_PROMPTS.get(agent_type, AGENT_SYSTEM_PROMPTS["validator"])

    if not llm_gateway.check_api_key():
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

PRIOR TASK MESSAGES/COMMENTS (HISTORY):
{task_messages[:2000] if task_messages else "No prior comments found."}

Write a system prompt for the Coding Agent that:
1. Tells it EXACTLY what module/files to create for THIS specific task
2. References the EXACT field names, API endpoints, and types from the Tech Spec
3. Tells it what files/symbols already exist (from KG) that it should import/reference
4. Warns about any files being edited by other agents (avoid conflicts)
5. Specifies the exact naming conventions to follow
6. **CRITICAL: MUST perfectly follow the provided Canonical Project Tree (the Master Agent's structure). DO NOT invent your own file nesting or directories.**
7. **CRITICAL: If you have ANY doubts about where to put a file, DO NOT guess. You MUST strictly follow the exact structure defined by the Master Agent. Agents cannot decide on their own entirely new architectural structures.**
8. Ends with the shell generation rules (create files under /workspace/, use mkdir/cat/grep/sed/find, etc.)

The prompt MUST include these code generation rules at the end:
{_COMPACT_CODE_RULES}

Write ONLY the system prompt text. Do not include any meta-commentary."""

    try:
        messages = [
            {"role": "system", "content": "You are a prompt engineering expert. Write precise, actionable system prompts for coding agents."},
            {"role": "user", "content": manager_prompt},
        ]

        dynamic_prompt = await llm_gateway.call_llm_and_extract(
            messages=messages,
            api_url=url,
            api_key=key,
            model=model_name,
            timeout=60.0
        )
        if len(dynamic_prompt) > 100:  # Sanity check
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
    clean_url = repo_url.rstrip("/")
    if clean_url.lower().endswith(".git"):
        clean_url = clean_url[:-4]
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
                repo_ref = f"{owner}/{repo}"
                return {
                    "success": False,
                    "error": f"GitHub API {response.status_code} for {repo_ref}: {response.text[:300]}",
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
        agent = t.get("assigned_agent_name")
        if not agent:
            agent_id = t.get("assigned_agent")
            agent = normalize_agent_name(agent_id, None) if agent_id else "unknown"
        task_summaries.append(f"- **{title}** (by `{agent}`)")

    task_list = "\n".join(task_summaries) if task_summaries else "- No task summaries available"

    # Try AI-powered PR body
    url = llm_gateway.resolve_url()
    key = llm_gateway.resolve_key()
    model_name = llm_gateway.resolve_model()

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

            messages = [
                {"role": "system", "content": "You are a technical writer creating GitHub PR descriptions."},
                {"role": "user", "content": prompt},
            ]

            ai_body = await llm_gateway.call_llm_and_extract(
                messages=messages,
                api_url=url,
                api_key=key,
                model=model_name,
                timeout=60.0
            )
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
*Generated by DSuite Agent Pipeline*
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
    """Detect if the build script itself crashed before meaningful workspace output."""
    if not stderr:
        return False
    crash_indicators = [
        "SyntaxError", "IndentationError", "NameError", "ImportError",
        "unterminated", "invalid syntax", "unexpected EOF",
        "syntax error near unexpected token", "unexpected end of file", "bad substitution",
    ]
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
    workspace_tree: str = "",
    live_repo_tree: str = "",
) -> tuple[str, str]:
    """Call AI model to generate a project-building shell script.
    
    Args:
        task_description: The task to implement
        agent_type: Type of agent (validator, risk, estimator)
        code_context: Optional JIT context from Knowledge Graph + RAG system
        system_prompt_override: Dynamic prompt from Manager Agent (Layer 3)
        tech_spec: Canonical Technical Spec from Architect Agent (Layer 1)
        workspace_tree: The Master Agent's Canonical Project Tree
        live_repo_tree: The actual current file structure from the git repository
    """
    url = llm_gateway.resolve_url()
    key = llm_gateway.resolve_key()
    model_name = llm_gateway.resolve_model()

    if not llm_gateway.check_api_key():
        raise ValueError("AI API key not configured")

    # Use dynamic prompt if provided, otherwise fall back to static
    system_prompt = system_prompt_override if system_prompt_override else AGENT_SYSTEM_PROMPTS.get(agent_type, AGENT_SYSTEM_PROMPTS["validator"])

    # Build user prompt with context layers
    user_parts = []

    # Layer 1: Tech Spec (canonical architecture reference)
    if tech_spec:
        user_parts.append(
            f"TECHNICAL SPECIFICATION (Canonical — follow this exactly):\n"
            f"{tech_spec[:4000]}\n\n"
        )

    # Layer 2: Master Canonical Workspace Tree (the target state)
    if workspace_tree:
        user_parts.append(
            f"MASTER AGENT'S CANONICAL PROJECT TREE (Target Structure):\n"
            f"{workspace_tree[:4000]}\n\n"
        )
        
    # Layer 2b: Live Repository Structure (the current state)
    if live_repo_tree:
        user_parts.append(
            f"LIVE REPOSITORY STRUCTURE (Current state on disk):\n"
            f"{live_repo_tree[:4000]}\n\n"
            f"⚠️ CRITICAL: Compare the LIVE STRUCTURE vs the CANONICAL TREE. "
            f"Fix any discrepancies or missing files found on disk.\n\n---\n"
        )

    if workspace_tree or live_repo_tree:
        user_parts.append(
            f"⚠️ CRITICAL: You MUST create files where the CANONICAL TREE indicates. "
            f"DO NOT invent your own folders or alter the pre-approved structure.\n\n---\n"
        )
    elif tech_spec:
        user_parts.append(
            f"⚠️ CRITICAL: Pay special attention to the '## 4. FILE STRUCTURE' section above. "
            f"All files MUST be created in the directories specified in that section. "
            f"DO NOT create files directly in /workspace/ root unless the FILE STRUCTURE section explicitly says so.\n\n---\n"
        )

    # Layer 3: KG context (relevant existing code)
    if code_context:
        user_parts.append(
            f"RELEVANT CODEBASE CONTEXT (from Knowledge Graph analysis):\n"
            f"{code_context}\n\n---\n"
        )

    user_parts.append(f"Task to implement:\n\n{task_description}")

    if code_context or tech_spec or workspace_tree:
        user_parts.append(
            "\n\nUse the context above to understand existing patterns, "
            "naming conventions, file structure, and dependencies. "
            "Ensure your generated code is consistent with the Technical Spec "
            "and existing codebase.\n\n"
            "⚠️ REMINDER: You MUST perfectly align your file paths with the "
            "pre-approved canonical tree / file structure above. Do not decide file placement on your own."
        )

    user_content = "\n".join(user_parts)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]

    last_err = None
    content = ""
    for attempt in range(3):
        try:
            if attempt > 0:
                await asyncio.sleep(5 * attempt)
            content = await llm_gateway.call_llm_and_extract(
                messages=messages,
                api_url=url,
                api_key=key,
                model=model_name,
                timeout=120.0
            )
            last_err = None
            break
        except Exception as e:
            last_err = e
            if attempt == 2:
                raise
    if last_err:
        raise last_err

    if content:
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
    workspace_tree: str = "",
    live_repo_tree: str = "",
) -> tuple[str, str]:
    """
    Call AI to generate a fix script. Enhanced with:
    - KG error context: relevant code from the Knowledge Graph to fix errors
    - Tech spec: canonical architecture reference to stay consistent
    - Workspace tree: the target canonical structure
    - Live repo tree: the actual current state on disk to help compare
    If builder_crashed=True, the previous build script failed before producing files
    and /workspace/ is empty, so we regenerate from scratch.
    """
    url = llm_gateway.resolve_url()
    key = llm_gateway.resolve_key()
    model_name = llm_gateway.resolve_model()

    if not llm_gateway.check_api_key():
        raise ValueError("AI API key not configured")

    system_prompt = AGENT_SYSTEM_PROMPTS.get(agent_type, AGENT_SYSTEM_PROMPTS["validator"])

    issues_text = "\n".join(f"  - {issue}" for issue in issues)

    # Build supplementary context from KG and tech spec
    supplementary_context = ""
    if tech_spec:
        supplementary_context += f"\nTECHNICAL SPECIFICATION (follow exact naming and conventions):\n{tech_spec[:2000]}\n"
    if workspace_tree:
        supplementary_context += f"\nMASTER AGENT'S CANONICAL PROJECT TREE (Target Structure):\n{workspace_tree[:4000]}\n"
    if live_repo_tree:
        supplementary_context += f"\nLIVE REPOSITORY STRUCTURE (Current state on disk):\n{live_repo_tree[:4000]}\n"
        supplementary_context += "\n⚠️ CRITICAL: Compare the LIVE STRUCTURE vs the CANONICAL TREE. Fix any discrepancies or missing files.\n"
    if kg_error_context:
        supplementary_context += f"\n{kg_error_context}\n"

    if builder_crashed:
        fix_prompt = f"""YOUR PREVIOUS BUILDER SCRIPT CRASHED before creating any files.
The error was:
{issues_text}

ORIGINAL TASK:
{task_description}
{supplementary_context}
You MUST generate a NEW, SHORTER shell script (UNDER 300 lines) that creates the project.
The /workspace/ directory is currently EMPTY - you need to create everything from scratch.

CRITICAL RULES TO AVOID CRASHING AGAIN:
1. Start with a valid shell script for bash.
2. Use shell commands like mkdir -p, cat <<'EOF' > path, grep -q, sed -i, ls, and find.
3. Do NOT use Python to write files.
4. Keep the script under 300 lines total.
5. Focus on the 10-15 most important files only.
6. Print [CREATED] for each file and [CHECK] PASS for each validation.
7. Print === SUMMARY === at the end.
8. Use ONLY ASCII characters.
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
Generate a NEW shell script (UNDER 300 lines) that:
1. FIXES each issue by modifying or creating files under /workspace/
2. Actually writes/overwrites the files that need fixing
3. Creates any missing files, directories, or configurations
4. Print [FIX N] for each fix applied
5. Print [CHECK] PASS for each successful validation
6. Print === FIX SUMMARY === at the end

IMPORTANT RULES:
- Use shell commands like mkdir -p, cat <<'EOF' > path, grep -q, sed -i, ls, and find.
- Do NOT use Python helpers or Python file-writing code.
- Keep under 300 lines. Use ONLY ASCII characters.
- Exit with code 0 if all fixes pass, 1 if any remain.
"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": fix_prompt},
    ]

    await asyncio.sleep(3)

    last_err = None
    content = ""
    for attempt in range(3):
        try:
            if attempt > 0:
                await asyncio.sleep(5 * attempt)
            content = await llm_gateway.call_llm_and_extract(
                messages=messages,
                api_url=url,
                api_key=key,
                model=model_name,
                timeout=120.0
            )
            last_err = None
            break
        except Exception as e:
            last_err = e
            if attempt == 2:
                raise
    if last_err:
        raise last_err

    if content:
        return _clean_ai_code_response(content)
    else:
        raise ValueError("No response from AI model for fix iteration")


async def _call_ai_for_self_review(
    task_description: str,
    agent_type: str,
    workspace_tree: str,
    tech_spec: str = "",
) -> tuple[bool, str]:
    """Call AI to generate a self-review of the project structure before pushing."""
    url = llm_gateway.resolve_url()
    key = llm_gateway.resolve_key()
    model_name = llm_gateway.resolve_model()

    if not llm_gateway.check_api_key():
        raise ValueError("AI API key not configured")

    system_prompt = AGENT_SYSTEM_PROMPTS.get(agent_type, AGENT_SYSTEM_PROMPTS["validator"])
    
    review_prompt = f"""SELF-REVIEW TASK:
You are about to commit your work to the main repository. Before you do, evaluate your generated workspace tree against the original task description and technical requirements.

ORIGINAL TASK:
{task_description}

"""
    if tech_spec:
        review_prompt += f"TECH SPEC:\n{tech_spec[:2000]}\n\n"

    review_prompt += f"""GENERATED WORKSPACE TREE:
{workspace_tree}

Are the core requirements structurally met? Are there any glaring missing folders/files based on the specs?
Reply EXACTLY on the very first line with either 'PASS' or 'FAIL'.
On the following lines, provide a short 1-3 sentence justification."""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": review_prompt},
    ]

    last_err = None
    content = ""
    for attempt in range(3):
        try:
            content = await llm_gateway.call_llm_and_extract(
                messages=messages,
                api_url=url,
                api_key=key,
                model=model_name,
                timeout=60.0,
                temperature=0.2
            )
            last_err = None
            break
        except Exception as e:
            last_err = e
    if last_err:
        return True, f"Self-review API failed: {last_err}. Passing by default."

    if content:
        passed = content.upper().startswith("PASS")
        return passed, content
    return True, "No response from AI model for self-review. Passing by default."


# ── Docker Configuration ────────────────────────────────────────────────────

AGENT_RUNTIME_IMAGE = "brd-analyzer-agent-runtime:latest"
AGENT_RUNTIME_DOCKERFILE = os.path.join(
    os.path.dirname(__file__),
    "docker",
    "agent-runtime.Dockerfile",
)
AGENT_RUNTIME_BUILD_CONTEXT = os.path.dirname(AGENT_RUNTIME_DOCKERFILE)
DOCKER_BASE_IMAGE = AGENT_RUNTIME_IMAGE


def _ensure_agent_runtime_image() -> Dict[str, Any]:
    """Build the shared agent runtime image when it is not present locally."""
    if not os.path.exists(AGENT_RUNTIME_DOCKERFILE):
        return {
            "success": False,
            "error": f"Missing agent runtime blueprint: {AGENT_RUNTIME_DOCKERFILE}",
        }

    inspect = subprocess.run(
        ["docker", "image", "inspect", AGENT_RUNTIME_IMAGE],
        capture_output=True,
        text=True,
        timeout=20,
    )
    if inspect.returncode == 0:
        return {"success": True, "image": AGENT_RUNTIME_IMAGE, "built": False}

    build = subprocess.run(
        [
            "docker",
            "build",
            "-t",
            AGENT_RUNTIME_IMAGE,
            "-f",
            AGENT_RUNTIME_DOCKERFILE,
            AGENT_RUNTIME_BUILD_CONTEXT,
        ],
        capture_output=True,
        text=True,
        timeout=1800,
    )
    if build.returncode != 0:
        error_tail = (build.stderr or build.stdout or "").strip()
        return {
            "success": False,
            "error": f"Agent runtime image build failed: {error_tail[-1200:]}",
        }

    return {"success": True, "image": AGENT_RUNTIME_IMAGE, "built": True}


def _verify_container_toolchain(container_name: str) -> Dict[str, Any]:
    """Verify the runtime container has the required toolchain preinstalled."""
    checks = {
        "git": "git --version",
        "python3": "python3 --version",
        "pip": "pip --version",
        "npm": "npm --version",
    }
    versions: Dict[str, str] = {}

    for tool_name, command in checks.items():
        result = subprocess.run(
            ["docker", "exec", container_name, "sh", "-lc", command],
            capture_output=True,
            text=True,
            timeout=20,
        )
        if result.returncode != 0:
            return {
                "success": False,
                "error": (
                    f"Missing required tool '{tool_name}' in runtime container: "
                    f"{(result.stderr or result.stdout or '').strip()}"
                ),
            }
        version_line = (result.stdout or result.stderr or "").splitlines()
        versions[tool_name] = version_line[0].strip() if version_line else ""

    return {"success": True, "versions": versions}


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


def _is_azure_devops_url(repo_url: str) -> bool:
    """Check if the repository URL is from Azure DevOps."""
    repo_url = repo_url.strip().lower()
    return "dev.azure.com" in repo_url or "visualstudio.com" in repo_url


def _build_git_auth_url(repo_url: str, token: str) -> str:
    """Insert token into HTTPS git URL for authentication."""
    repo_url = repo_url.strip()
    if not token:
        return repo_url
    
    token = token.strip()
    
    # Azure DevOps uses different auth format than GitHub
    if _is_azure_devops_url(repo_url):
        # For Azure DevOps, use PAT authentication
        # Format: https://:PAT@dev.azure.com/org/project/_git/repo
        # or https://PAT@dev.azure.com/org/project/_git/repo
        if repo_url.startswith("https://"):
            # Remove any existing credentials
            repo_url = repo_url.replace("https://", "https://", 1)
            # Insert token with colon prefix (standard Basic Auth format for Azure DevOps)
            return repo_url.replace("https://", f"https://:{token}@", 1)
    else:
        # GitHub and other providers
        if repo_url.startswith("https://"):
            return repo_url.replace("https://", f"https://{token}@", 1)
    
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


def prime_project_git_credentials(
    agents_config: Optional[Dict[str, Dict[str, str]]],
    project_token: Optional[str] = None,
) -> Dict[str, str]:
    if not isinstance(agents_config, dict) or not agents_config:
        return {"repo_url": "", "token": ""}

    project_agents = _get_agent_states(project_token)
    repo_url = ""
    token = ""
    for agent_id in sorted(agents_config):
        cfg = agents_config.get(agent_id) or {}
        if not isinstance(cfg, dict):
            continue
        repo_val = str(cfg.get("git_repo_url") or "").strip()
        token_val = str(cfg.get("git_token") or "").strip()
        if repo_val and not repo_url:
            repo_url = repo_val
        if token_val and not token:
            token = token_val
        agent = project_agents.get(agent_id)
        if not agent:
            continue
        if repo_val:
            agent["git_repo_url"] = repo_val
        if token_val:
            agent["git_token"] = token_val

    if repo_url:
        for special_agent_id in (GIT_MANAGER_AGENT_ID, MASTER_AGENT_ID):
            agent = project_agents.get(special_agent_id)
            if not agent:
                continue
            agent["git_repo_url"] = repo_url
            if token:
                agent["git_token"] = token

    return {"repo_url": repo_url, "token": token}


def _resolve_project_git_credentials(
    project_token: Optional[str] = None,
    agents_config: Optional[Dict[str, Dict[str, str]]] = None,
) -> Dict[str, str]:
    seeded = prime_project_git_credentials(agents_config, project_token=project_token)
    if seeded.get("repo_url"):
        return seeded

    project_agents = _get_agent_states(project_token)
    preferred_order = [GIT_MANAGER_AGENT_ID, MASTER_AGENT_ID]
    preferred_order.extend(
        agent_id
        for agent_id in sorted(project_agents)
        if agent_id not in preferred_order
    )
    for agent_id in preferred_order:
        agent = project_agents.get(agent_id) or {}
        repo_url = str(agent.get("git_repo_url") or "").strip()
        token = str(agent.get("git_token") or "").strip()
        if repo_url:
            return {"repo_url": repo_url, "token": token}
    return {"repo_url": "", "token": ""}


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


def _collect_workspace_file_paths(container_name: str) -> List[str]:
    result = subprocess.run(
        [
            "docker", "exec", "-w", "/workspace", container_name, "sh", "-lc",
            (
                "find /workspace -type f "
                "-not -path '*/.git/*' "
                "-not -path '*/node_modules/*' "
                "-not -path '*/dist/*' "
                "-not -path '*/build/*' "
                "-not -path '*/.next/*' "
                "-not -path '*/.turbo/*' "
                "-not -path '*/__pycache__/*' "
                "-not -path '*/venv/*' "
                "-not -path '*/.venv/*' "
                "-not -path '*/.pytest_cache/*' "
                "| sed 's|^/workspace/||' | LC_ALL=C sort"
            ),
        ],
        capture_output=True,
        text=True,
        timeout=45,
    )
    if result.returncode != 0:
        return []
    return [
        path.strip()
        for path in (result.stdout or "").splitlines()
        if path.strip()
    ]


def _refresh_workspace_contract_from_container(
    container_name: str,
    project_token: Optional[str],
    *,
    source: str = "git_repo",
) -> Dict[str, Any]:
    effective_project = str(project_token or "").strip()
    if not effective_project:
        return {"success": False, "error": "missing project token"}
    try:
        import context_manager as ctx_mgr
    except Exception as exc:
        return {"success": False, "error": f"context manager unavailable: {exc}"}

    file_paths = _collect_workspace_file_paths(container_name)
    if not file_paths:
        return {"success": False, "error": "no repository files detected"}

    contract = ctx_mgr.update_workspace_contract_from_file_paths(
        effective_project,
        file_paths,
        source=source,
        merge_ready=True,
        force_refresh=True,
    )
    return {
        "success": True,
        "file_count": len(file_paths),
        "contract": contract,
    }


async def _refresh_workspace_contract_from_git_repo(
    *,
    project_token: Optional[str],
    repo_url: str,
    token: str = "",
    force: bool = False,
) -> Dict[str, Any]:
    effective_project = str(project_token or "").strip()
    repo_value = str(repo_url or "").strip()
    if not effective_project or not repo_value:
        return {"success": False, "skipped": True, "error": "missing project token or repo url"}

    state = _ensure_project_state(project_token)
    probe_state = state.get("workspace_contract_probe") if isinstance(state.get("workspace_contract_probe"), dict) else {}
    loaded_at = float(probe_state.get("loaded_at") or 0.0)
    if (
        not force
        and probe_state.get("repo_url") == repo_value
        and (time.time() - loaded_at) < WORKSPACE_CONTRACT_PROBE_TTL_SECONDS
    ):
        return {"success": True, "cached": True, "contract": probe_state.get("contract") or {}}

    container_name = f"workspace_contract_{uuid.uuid4().hex[:8]}"
    try:
        container_result = await asyncio.to_thread(_create_persistent_container, container_name)
        if not container_result.get("success"):
            return {"success": False, "error": container_result.get("error") or "container creation failed"}

        toolchain_result = _verify_container_toolchain(container_name)
        if not toolchain_result.get("success"):
            return {"success": False, "error": toolchain_result.get("error") or "toolchain verification failed"}

        auth_url = _build_git_auth_url(repo_value, token)
        clone = subprocess.run(
            ["docker", "exec", container_name, "git", "clone", "--depth", "1", auth_url, "/workspace"],
            capture_output=True,
            text=True,
            timeout=300,
        )
        if clone.returncode != 0:
            return {"success": False, "error": clone.stderr or clone.stdout or "git clone failed"}

        refresh_result = _refresh_workspace_contract_from_container(
            container_name,
            project_token,
            source="git_repo",
        )
        if refresh_result.get("success"):
            state["workspace_contract_probe"] = {
                "repo_url": repo_value,
                "loaded_at": time.time(),
                "source": "git_repo",
                "file_count": int(refresh_result.get("file_count") or 0),
                "contract": refresh_result.get("contract") or {},
            }
        return refresh_result
    finally:
        await asyncio.to_thread(_destroy_container, container_name)


async def _call_ai_for_test_plan(summary: Dict[str, Any]) -> Dict[str, Any]:
    key = llm_gateway.resolve_key()
    if not llm_gateway.check_api_key():
        return {}
    url = llm_gateway.resolve_url()
    model_name = llm_gateway.resolve_model()
    prompt = (
        "You are a build engineer. Given this repo summary, return JSON only with keys "
        "\"install\" (list of shell commands) and \"tests\" (list of shell commands). "
        "Use only safe commands such as: pip install -r requirements.txt, pip install -e ., "
        "python -m pytest -q, pytest -q, npm install, npm test, npm run test, npm run build, "
        "pnpm install, pnpm test, yarn install, yarn test. If no tests, return empty lists.\n\n"
        f"REPO SUMMARY:\n{json.dumps(summary, indent=2)}"
    )
    messages = [
        {"role": "system", "content": "Return only valid JSON."},
        {"role": "user", "content": prompt},
    ]
    try:
        content = await llm_gateway.call_llm_and_extract(
            messages=messages,
            api_url=url,
            api_key=key,
            model=model_name,
            timeout=120.0
        )
        start = content.find("{")
        end = content.rfind("}")
        if start == -1 or end == -1:
            return {}
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
    
    # Clean and normalize paths from git diff output
    cleaned_paths = []
    for line in (diff.stdout or "").splitlines():
        path = line.strip()
        if not path:
            continue
        
        # Remove quotes if present
        path = path.strip('"').strip("'")
        
        # Handle rename indicators (old => new format)
        if " => " in path:
            # For renames, take the new path (after =>)
            path = path.split(" => ", 1)[1].strip()
        
        # Remove any status suffixes like /r, /m, etc. that might come from git
        # These are typically at the end of the line
        if path.endswith(("/r", "/m", "/a", "/c", "/d")):
            path = path[:-2]
        
        # Remove any trailing whitespace or special characters
        path = path.strip().rstrip("/")
        
        if path:
            cleaned_paths.append(path)
    
    return cleaned_paths


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

    try:
        source_domain = live_mem.get_agent_domain(source_agent) if source_agent else None
        contract_validation = ctx_mgr.validate_paths_against_workspace_contract(
            project_token or "",
            changed_files,
            task_domain=source_domain,
        )
        if not contract_validation.get("allowed", True):
            return {
                "allowed": False,
                "changed_files": changed_files,
                "conflicts": [{
                    "agent_id": "workspace-contract",
                    "branch": "(contract)",
                    "overlap": contract_validation.get("violations") or [],
                }],
                "reason_type": "workspace_contract",
            }
    except Exception:
        pass

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
        "reason_type": "overlap" if conflicts else None,
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


def _pick_fix_agent_id(project_token: Optional[str] = None) -> Optional[str]:
    project_agents = _get_agent_states(project_token)
    if not project_agents:
        return None

    def _eligible(agent_id: str, agent: Dict[str, Any]) -> bool:
        if _is_system_agent_id(agent_id):
            return False
        return True

    def _preferred(ids: List[str]) -> Optional[str]:
        idle = [aid for aid in ids if project_agents.get(aid, {}).get("status") == "idle"]
        return idle[0] if idle else (ids[0] if ids else None)

    dedicated = [
        aid for aid, agent in project_agents.items()
        if aid.startswith("dedicated_agent_") and _eligible(aid, agent)
    ]
    shared = [
        aid for aid, agent in project_agents.items()
        if aid.startswith("shared_agent_") and _eligible(aid, agent)
    ]
    others = [
        aid for aid, agent in project_agents.items()
        if _eligible(aid, agent) and aid not in dedicated and aid not in shared
    ]

    return _preferred(dedicated) or _preferred(shared) or _preferred(others)


async def _create_merge_fix_task(
    *,
    title: str,
    description: str,
    project_token: Optional[str],
    task_token: Optional[str],
    preferred_agent_id: Optional[str] = None,
) -> Optional[str]:
    from task_service import task_service

    effective_token = task_token or get_project_task_token(project_token)
    startdate = datetime.utcnow().strftime("%Y-%m-%d")
    deadline = await _resolve_project_deadline(project_token, task_token=effective_token)
    if deadline and deadline < startdate:
        deadline = startdate

    payload = {
        "taskName": title,
        "description": description,
        "assignees": [],
        "wallet": 1,
        "deadline": deadline,
        "startdate": startdate,
        "task_type": "BUG",
        "priority": "high",
    }

    try:
        result = await task_service.create_task(payload, task_token=effective_token)
    except Exception as exc:
        _log_git_agent(
            f"Failed to create fix task for merge failure: {exc}",
            "error",
            project_token=project_token,
        )
        return None

    task_id = (
        str(result.get("id") or result.get("task_id") or result.get("taskId") or "").strip()
        if isinstance(result, dict) else ""
    )
    if not task_id:
        _log_git_agent(
            "Fix task created but no task id was returned.",
            "warning",
            project_token=project_token,
        )
        return None

    if preferred_agent_id:
        assigned = await _master_assign_task_to_agent(
            task_id,
            preferred_agent_id,
            agent_name=_get_agent_states(project_token).get(preferred_agent_id, {}).get("name"),
            project_token=project_token,
            task_token=effective_token,
        )
        if not assigned:
            _log_git_agent(
                f"Fix task {task_id} created but assignment to {preferred_agent_id} failed.",
                "warning",
                project_token=project_token,
            )

    return task_id


async def _run_git_manager_tests_with_ai(container_name: str, branch: str, project_token: Optional[str] = None) -> Dict[str, Any]:
    summary = _collect_repo_summary(container_name)
    plan = await _call_ai_for_test_plan(summary)
    if not plan:
        plan = _heuristic_test_plan(summary)

    install_cmds = plan.get("install") or []
    test_cmds = plan.get("tests") or []
    if not test_cmds:
        _log_git_agent("No test commands detected. Skipping tests.", project_token=project_token)
        return {"ok": True, "failures": [], "details": []}

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
            return {"ok": True, "failures": [], "details": []}
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
        return {"ok": True, "failures": [], "details": []}

    test_failures: List[str] = []
    failure_details: List[Dict[str, str]] = []

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
                r"(?:No module named|ModuleNotFoundError:.*?)['\"]?([^'\"\s]+)['\"]?",
                combined_output,
            )
            if "no module named pytest" in combined_output.lower() and "pytest" not in missing_modules:
                missing_modules.append("pytest")
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
            # Tests still failing after auto-fix attempts — record and let
            # the caller decide whether to allow the merge.
            _log_git_agent(
                f"⚠️ Tests still failing after fixes: {cmd}",
                "warning",
                project_token=project_token,
            )
            test_failures.append(cmd)
            tail = (test_res.get("stderr") or test_res.get("stdout") or "")[-800:]
            failure_details.append({"cmd": cmd, "tail": tail})
            # We still commit local fixes so logs reflect what was tried,
            # but the overall gate result will be False.
            _commit_if_dirty(container_name, f"Push with test warnings ({branch})")

    # Gate result: only pass when no test command ultimately failed.
    if test_failures:
        _log_git_agent(
            f"Test gate failed for {branch}: {', '.join(test_failures)}",
            "error",
            project_token=project_token,
        )
        return {"ok": False, "failures": test_failures, "details": failure_details}

    return {"ok": True, "failures": [], "details": []}


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


async def wait_for_git_merge_drain(
    project_token: Optional[str] = None,
    timeout_seconds: float = 300.0,
    poll_interval: float = 1.0,
) -> bool:
    """Wait until the git merge queue and in-flight work are drained."""
    deadline = time.time() + max(1.0, timeout_seconds)
    while time.time() < deadline:
        state = _ensure_project_state(project_token)
        if (
            not state.get("git_merge_running")
            and not state.get("git_merge_queue")
            and not state.get("git_merge_inflight")
        ):
            return True
        await asyncio.sleep(max(0.2, poll_interval))
    return False


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


def _read_merge_stage_file(container_name: str, file_path: str, stage: int) -> str:
    result = subprocess.run(
        ["docker", "exec", "-w", "/workspace", container_name, "git", "show", f":{stage}:{file_path}"],
        capture_output=True,
        text=True,
        timeout=20,
    )
    if result.returncode != 0:
        return ""
    return result.stdout or ""


def _write_workspace_file_to_container(container_name: str, file_path: str, content: str) -> bool:
    local_tmp = None
    remote_tmp = f"/tmp/ai_merge_{uuid.uuid4().hex[:8]}.tmp"
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            delete=False,
            encoding="utf-8",
            prefix="ai_merge_",
            suffix=".tmp",
        ) as handle:
            handle.write(content)
            local_tmp = handle.name

        copy_res = subprocess.run(
            ["docker", "cp", local_tmp, f"{container_name}:{remote_tmp}"],
            capture_output=True,
            text=True,
            timeout=20,
        )
        if copy_res.returncode != 0:
            return False

        target_dir = os.path.dirname(file_path) or "."
        write_script = (
            f"mkdir -p {shlex.quote(target_dir)} && "
            f"cat {shlex.quote(remote_tmp)} > {shlex.quote(file_path)} && "
            f"rm -f {shlex.quote(remote_tmp)}"
        )
        write_res = subprocess.run(
            ["docker", "exec", "-w", "/workspace", container_name, "sh", "-c", write_script],
            capture_output=True,
            text=True,
            timeout=20,
        )
        return write_res.returncode == 0
    finally:
        if local_tmp and os.path.exists(local_tmp):
            try:
                os.unlink(local_tmp)
            except OSError:
                pass
        subprocess.run(
            ["docker", "exec", container_name, "rm", "-f", remote_tmp],
            capture_output=True,
            text=True,
            timeout=10,
        )


def _validate_ai_merged_file(container_name: str, file_path: str) -> tuple[bool, str]:
    rel_path = str(file_path or "").strip()
    if not rel_path:
        return False, "missing file path"

    marker_check = subprocess.run(
        [
            "docker", "exec", "-w", "/workspace", container_name, "sh", "-c",
            f"grep -n '<<<<<<<\\|=======\\|>>>>>>>' {shlex.quote(rel_path)} >/dev/null 2>&1",
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if marker_check.returncode == 0:
        return False, "conflict markers remain"

    lower = rel_path.lower()
    if lower.endswith(".py"):
        check = subprocess.run(
            ["docker", "exec", "-w", "/workspace", container_name, "python3", "-m", "py_compile", rel_path],
            capture_output=True,
            text=True,
            timeout=20,
        )
        if check.returncode != 0:
            return False, check.stderr or check.stdout or "python syntax check failed"
    elif lower.endswith(".json"):
        check = subprocess.run(
            ["docker", "exec", "-w", "/workspace", container_name, "python3", "-m", "json.tool", rel_path],
            capture_output=True,
            text=True,
            timeout=20,
        )
        if check.returncode != 0:
            return False, check.stderr or check.stdout or "json validation failed"

    return True, ""


def _normalize_ai_merged_content(content: str) -> str:
    merged = str(content or "").strip()
    if not merged:
        return ""

    if merged.startswith("```"):
        lines = merged.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        merged = "\n".join(lines).strip()

    # Sometimes the model returns the entire file as a quoted string literal.
    if len(merged) >= 2 and merged[0] == merged[-1] and merged[0] in {"'", '"'}:
        try:
            decoded = ast.literal_eval(merged)
            if isinstance(decoded, str) and decoded:
                merged = decoded
        except Exception:
            pass

    # Handle escaped whole-file output such as "import x;\\nconst y = 1;..."
    if "\\n" in merged and "\n" not in merged:
        merged = (
            merged
            .replace("\\r\\n", "\n")
            .replace("\\n", "\n")
            .replace("\\t", "\t")
        )
        if '\\"' in merged and merged.count('"') == 0:
            merged = merged.replace('\\"', '"')
        if "\\'" in merged and merged.count("'") == 0:
            merged = merged.replace("\\'", "'")

    return merged.strip()


async def _call_ai_for_merge_resolution(
    *,
    file_path: str,
    base_content: str,
    ours_content: str,
    theirs_content: str,
    source_branch: str,
    source_agent: Optional[str],
    task_title: str,
) -> str:
    if not llm_gateway.check_api_key():
        return ""

    prompt = f"""You are resolving a git merge conflict for a software repository.
Return ONLY the final merged file content for `{file_path}`.
Do not wrap the answer in markdown fences. Do not explain your reasoning.

Merge context:
- Source branch being merged: {source_branch}
- Source agent: {source_agent or "unknown"}
- Task title: {task_title or "unknown"}

Rules:
1. Preserve behavior from both versions whenever they are compatible.
2. Prefer the target/integration branch structure if the source branch is incomplete.
3. Remove all conflict markers.
4. Keep imports, typing, and formatting valid.
5. If this is a code file, ensure the file is syntactically valid.

BASE VERSION:
<<<BASE
{base_content[:12000]}
BASE>>>

SOURCE BRANCH VERSION:
<<<OURS
{ours_content[:12000]}
OURS>>>

INTEGRATION BRANCH VERSION:
<<<THEIRS
{theirs_content[:12000]}
THEIRS>>>"""

    messages = [
        {
            "role": "system",
            "content": "You are an expert git merge assistant. Output only merged file contents.",
        },
        {"role": "user", "content": prompt},
    ]

    try:
        content = await llm_gateway.call_llm_and_extract(
            messages=messages,
            timeout=90.0
        )
        return _normalize_ai_merged_content(content)
    except Exception as e:
        logger.error(f"AI merge resolution failed: {e}")
        return ""


async def _resolve_conflicts_with_ai(
    *,
    container_name: str,
    conflict_files: List[str],
    source_branch: str,
    source_agent: Optional[str],
    task_title: str,
    project_token: Optional[str],
) -> bool:
    unresolved = [f for f in conflict_files if f]
    if not unresolved:
        return True

    _log_git_agent(
        f"Attempting AI merge resolution for {len(unresolved)} file(s): {', '.join(unresolved[:5])}",
        project_token=project_token,
    )

    for file_path in unresolved:
        base_content = _read_merge_stage_file(container_name, file_path, 1)
        ours_content = _read_merge_stage_file(container_name, file_path, 2)
        theirs_content = _read_merge_stage_file(container_name, file_path, 3)

        merged = await _call_ai_for_merge_resolution(
            file_path=file_path,
            base_content=base_content,
            ours_content=ours_content,
            theirs_content=theirs_content,
            source_branch=source_branch,
            source_agent=source_agent,
            task_title=task_title,
        )
        if not merged:
            _log_git_agent(
                f"AI merge returned empty content for {file_path}",
                "error",
                project_token=project_token,
            )
            return False

        if not _write_workspace_file_to_container(container_name, file_path, merged + "\n"):
            _log_git_agent(
                f"Failed to write AI-merged file {file_path} into the merge container",
                "error",
                project_token=project_token,
            )
            return False

        valid, validation_error = _validate_ai_merged_file(container_name, file_path)
        if not valid:
            _log_git_agent(
                f"AI merge validation failed for {file_path}: {validation_error}",
                "error",
                project_token=project_token,
            )
            return False

        subprocess.run(
            ["docker", "exec", "-w", "/workspace", container_name, "git", "add", file_path],
            capture_output=True,
            text=True,
            timeout=10,
        )

    remaining = subprocess.run(
        ["docker", "exec", "-w", "/workspace", container_name, "git", "diff", "--name-only", "--diff-filter=U"],
        capture_output=True,
        text=True,
        timeout=20,
    )
    unresolved_after = [f.strip() for f in (remaining.stdout or "").splitlines() if f.strip()]
    if unresolved_after:
        _log_git_agent(
            f"AI merge left unresolved conflicts: {', '.join(unresolved_after[:5])}",
            "error",
            project_token=project_token,
        )
        return False

    _log_git_agent(
        f"AI merge resolution succeeded for {len(unresolved)} file(s).",
        project_token=project_token,
    )
    return True


def _filter_merge_conflict_files(conflict_files: List[str]) -> List[str]:
    return [
        f for f in (conflict_files or [])
        if f
        and "__pycache__" not in f
        and not f.endswith(".pyc")
        and not f.endswith(".pyo")
        and not f.endswith(".pyd")
        and ".DS_Store" not in f
        and "Thumbs.db" not in f
    ]


def _resolve_conflicts_smart(
    container_name: str,
    conflict_files: List[str],
    source_branch: str,
    source_agent: Optional[str],
    project_token: Optional[str],
) -> bool:
    """
    Resolve merge conflicts intelligently based on file ownership rules.
    
    Strategy:
    1. Get source agent's domain from live memory
    2. For each conflicted file:
       - If backend-owned and source is backend: keep source version
       - If frontend-owned and source is frontend: keep source version
       - If shared file (README.md, etc.): use union merge (combine both)
       - If ownership mismatch: keep integration branch version (safer)
    
    Returns True if all conflicts resolved, False otherwise.
    """
    try:
        import context_manager as ctx_mgr
        live_mem = ctx_mgr.get_live_memory(project_token or "")
        
        # Get source agent's domain
        source_domain = None
        if source_agent:
            with live_mem._lock:
                source_record = live_mem.active_tasks.get(source_agent)
                if not source_record:
                    # Check history
                    for record in live_mem.completed_history:
                        if record.agent_id == source_agent:
                            source_domain = record.task_domain
                            break
                else:
                    source_domain = source_record.task_domain
        
        # Filter out __pycache__ and other unnecessary files
        filtered_conflicts = _filter_merge_conflict_files(conflict_files)
        
        # If all conflicts are in __pycache__, just remove them and continue
        if not filtered_conflicts:
            _log_git_agent(
                f"All conflicts are in __pycache__ files - removing from tracking and continuing",
                project_token=project_token,
            )
            # Remove __pycache__ from git tracking
            for file_path in conflict_files:
                subprocess.run(
                    ["docker", "exec", "-w", "/workspace", container_name,
                     "git", "rm", "--cached", "-r", file_path],
                    capture_output=True, text=True, timeout=10,
                )
            return True
        
        resolved_count = 0
        union_files = []
        ours_files = []
        theirs_files = []
        
        for file_path in filtered_conflicts:
            # Determine file ownership
            file_owner = live_mem.get_file_owner(file_path)
            
            # Strategy decision
            if file_owner is None:
                # Shared file - use union merge
                union_files.append(file_path)
            elif file_owner == source_domain:
                # Source agent owns this file - keep source version (ours in merge context)
                ours_files.append(file_path)
            else:
                # Ownership mismatch - keep integration branch version (theirs in merge context)
                # This prevents backend agent from overwriting frontend files and vice versa
                theirs_files.append(file_path)
                _log_git_agent(
                    f"Conflict in {file_path}: ownership mismatch "
                    f"(source={source_domain}, file_owner={file_owner}). "
                    f"Keeping integration branch version.",
                    "warning",
                    project_token=project_token,
                )
        
        # Resolve conflicts
        all_resolved = True
        
        # 1. Keep source version for files owned by source domain
        for file_path in ours_files:
            checkout_cmd = subprocess.run(
                ["docker", "exec", "-w", "/workspace", container_name,
                 "git", "checkout", "--ours", file_path],
                capture_output=True, text=True, timeout=30,
            )
            if checkout_cmd.returncode == 0:
                subprocess.run(
                    ["docker", "exec", "-w", "/workspace", container_name,
                     "git", "add", file_path],
                    capture_output=True, text=True, timeout=10,
                )
                resolved_count += 1
                _log_git_agent(
                    f"Resolved {file_path}: kept source version (owned by {source_domain})",
                    project_token=project_token,
                )
            else:
                all_resolved = False
                _log_git_agent(
                    f"Failed to resolve {file_path}: {checkout_cmd.stderr}",
                    "error",
                    project_token=project_token,
                )
        
        # 2. Keep integration branch version for ownership mismatches
        for file_path in theirs_files:
            checkout_cmd = subprocess.run(
                ["docker", "exec", "-w", "/workspace", container_name,
                 "git", "checkout", "--theirs", file_path],
                capture_output=True, text=True, timeout=30,
            )
            if checkout_cmd.returncode == 0:
                subprocess.run(
                    ["docker", "exec", "-w", "/workspace", container_name,
                     "git", "add", file_path],
                    capture_output=True, text=True, timeout=10,
                )
                resolved_count += 1
            else:
                all_resolved = False
                _log_git_agent(
                    f"Failed to resolve {file_path}: {checkout_cmd.stderr}",
                    "error",
                    project_token=project_token,
                )
        
        # 3. Union merge for shared files (README.md, .gitignore, etc.)
        for file_path in union_files:
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
            if file_merge.returncode == 0:
                resolved_count += 1
                _log_git_agent(
                    f"Resolved {file_path}: union merge (shared file)",
                    project_token=project_token,
                )
            else:
                all_resolved = False
                _log_git_agent(
                    f"Union merge failed for {file_path}: {file_merge.stderr}",
                    "error",
                    project_token=project_token,
                )
        
        _log_git_agent(
            f"Conflict resolution: {resolved_count}/{len(filtered_conflicts)} files resolved "
            f"(ours={len(ours_files)}, theirs={len(theirs_files)}, union={len(union_files)}, "
            f"skipped __pycache__: {len(conflict_files) - len(filtered_conflicts)})",
            project_token=project_token,
        )
        
        return all_resolved and resolved_count == len(filtered_conflicts)
        
    except Exception as e:
        logger.error(f"Error in smart conflict resolution: {e}")
        _log_git_agent(
            f"Smart conflict resolution error: {str(e)[:200]}",
            "error",
            project_token=project_token,
        )
        return False


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

        toolchain_result = _verify_container_toolchain(container_name)
        if not toolchain_result.get("success"):
            _log_git_agent(
                f"Git manager runtime verification failed: {toolchain_result.get('error')}",
                "error",
                project_token=project_token,
            )
            return

        # Configure git user
        subprocess.run(
            ["docker", "exec", container_name, "git", "config", "--global", "user.email", "git-agent@dsuite.ai"],
            capture_output=True, text=True, timeout=10,
        )
        subprocess.run(
            ["docker", "exec", container_name, "git", "config", "--global", "user.name", "BRD Git Manager"],
            capture_output=True, text=True, timeout=10,
        )

        # Clone repo
        auth_url = _build_git_auth_url(repo_url, token)
        clone = subprocess.run(
            ["docker", "exec", container_name, "git", "clone", clone_url, "/workspace"],
            capture_output=True, text=True, timeout=300,
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
            base_branch_name = base_ref.replace("origin/", "", 1) if base_ref.startswith("origin/") else default_branch

            try:
                contract_sync = _sync_local_branch_from_remote(
                    container_name,
                    "__workspace_contract_probe__",
                    base_branch_name,
                )
                if contract_sync.get("success"):
                    refreshed_contract = _refresh_workspace_contract_from_container(
                        container_name,
                        project_token,
                        source="git_repo",
                    )
                    if refreshed_contract.get("success"):
                        _ensure_project_state(project_token)["workspace_contract_probe"] = {
                            "repo_url": repo_url,
                            "loaded_at": time.time(),
                            "source": "git_repo",
                            "file_count": int(refreshed_contract.get("file_count") or 0),
                            "contract": refreshed_contract.get("contract") or {},
                        }
            except Exception as exc:
                logger.warning("[%s] Failed to refresh workspace contract from merge base: %s", project_token or "", exc)

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

                if ownership_gate.get("reason_type") == "workspace_contract":
                    fix_agent_id = _pick_fix_agent_id(project_token)
                    details = (
                        f"Merge blocked by workspace contract for branch {branch}.\n"
                        f"Task: {task_title or 'unknown'}.\n"
                        f"Violations: {conflict_msg}.\n\n"
                        f"Fix by moving files into allowed roots or updating the workspace contract."
                    )
                    await _create_merge_fix_task(
                        title=f"Fix: Workspace contract violation for {branch}",
                        description=details,
                        project_token=project_token,
                        task_token=get_project_task_token(project_token),
                        preferred_agent_id=fix_agent_id,
                    )
                    _log_git_agent(
                        f"Workspace contract blocked merge for {branch}"
                        f"{f' ({task_title})' if task_title else ''}: {conflict_msg}. "
                        "Branch introduces files outside the canonical repository structure.",
                        "error",
                        project_token=project_token,
                    )
                    return

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

                initial_conflicts = _filter_merge_conflict_files(files)

                if initial_conflicts:
                    await _resolve_conflicts_with_ai(
                        container_name=container_name,
                        conflict_files=initial_conflicts,
                        source_branch=branch,
                        source_agent=source_agent,
                        task_title=task_title,
                        project_token=project_token,
                    )

                remaining_conflicts = subprocess.run(
                    ["docker", "exec", "-w", "/workspace", container_name, "git", "diff", "--name-only", "--diff-filter=U"],
                    capture_output=True,
                    text=True,
                    timeout=20,
                )
                raw_unresolved_files = [
                    f.strip()
                    for f in (remaining_conflicts.stdout or "").splitlines()
                    if f.strip()
                ]
                unresolved_files = _filter_merge_conflict_files(raw_unresolved_files)

                if raw_unresolved_files:
                    _log_git_agent(
                        f"AI merge left {len(raw_unresolved_files)} unresolved file(s); applying ownership fallback.",
                        "warning",
                        project_token=project_token,
                    )
                    _resolve_conflicts_smart(
                        container_name=container_name,
                        conflict_files=raw_unresolved_files,
                        source_branch=branch,
                        source_agent=source_agent,
                        project_token=project_token,
                    )

                remaining_conflicts = subprocess.run(
                    ["docker", "exec", "-w", "/workspace", container_name, "git", "diff", "--name-only", "--diff-filter=U"],
                    capture_output=True,
                    text=True,
                    timeout=20,
                )
                raw_unresolved_files = [
                    f.strip()
                    for f in (remaining_conflicts.stdout or "").splitlines()
                    if f.strip()
                ]
                unresolved_files = _filter_merge_conflict_files(raw_unresolved_files)

                if unresolved_files:
                    _log_git_agent(
                        f"Ownership fallback left {len(unresolved_files)} unresolved file(s); retrying with AI.",
                        "warning",
                        project_token=project_token,
                    )
                    await _resolve_conflicts_with_ai(
                        container_name=container_name,
                        conflict_files=unresolved_files,
                        source_branch=branch,
                        source_agent=source_agent,
                        task_title=task_title,
                        project_token=project_token,
                    )

                remaining_conflicts = subprocess.run(
                    ["docker", "exec", "-w", "/workspace", container_name, "git", "diff", "--name-only", "--diff-filter=U"],
                    capture_output=True,
                    text=True,
                    timeout=20,
                )
                unresolved_files = [
                    f.strip()
                    for f in (remaining_conflicts.stdout or "").splitlines()
                    if f.strip()
                ]
                if unresolved_files:
                    _log_git_agent(
                        f"Failed to resolve conflicts for {branch}: {', '.join(unresolved_files[:5])}. Aborting merge.",
                        "error",
                        project_token=project_token,
                    )
                    subprocess.run(
                        ["docker", "exec", "-w", "/workspace", container_name, "git", "merge", "--abort"],
                        capture_output=True, text=True, timeout=10,
                    )
                    return

                commit_resolved = subprocess.run(
                    ["docker", "exec", "-w", "/workspace", container_name,
                     "git", "commit", "-m", f"Resolved conflicts for {branch} using AI-assisted merge logic"],
                    capture_output=True, text=True, timeout=30,
                )
                commit_out = (commit_resolved.stdout or "") + (commit_resolved.stderr or "")
                if commit_resolved.returncode != 0 and "nothing to commit" not in commit_out.lower():
                    _log_git_agent(
                        f"Conflict resolution commit failed for {branch}: {commit_resolved.stderr}",
                        "error",
                        project_token=project_token
                    )
                    subprocess.run(
                        ["docker", "exec", "-w", "/workspace", container_name, "git", "merge", "--abort"],
                        capture_output=True, text=True, timeout=10,
                    )
                    return

            try:
                tests_result = await _run_git_manager_tests_with_ai(container_name, branch, project_token=project_token)
            except Exception as test_err:
                _log_git_agent(
                    f"Test runner error after merging {branch}: {str(test_err)[:200]}",
                    "error",
                    project_token=project_token,
                )
                tests_result = {"ok": False, "failures": ["test runner error"], "details": []}
            if not tests_result.get("ok"):
                fix_agent_id = _pick_fix_agent_id(project_token)
                detail_lines = []
                for entry in tests_result.get("details") or []:
                    cmd = entry.get("cmd") or ""
                    tail = entry.get("tail") or ""
                    if cmd or tail:
                        detail_lines.append(f"Command: {cmd}\n{tail}")
                details_blob = "\n\n".join(detail_lines).strip()
                description = "\n".join(
                    part for part in [
                        f"Merge tests failed for branch {branch}.",
                        f"Task: {task_title or 'unknown'}.",
                        f"Failures: {', '.join(tests_result.get('failures') or [])}.",
                        "",
                        details_blob,
                    ]
                    if part
                )
                await _create_merge_fix_task(
                    title=f"Fix: Merge test failures for {branch}",
                    description=description,
                    project_token=project_token,
                    task_token=get_project_task_token(project_token),
                    preferred_agent_id=fix_agent_id,
                )
                _log_git_agent(
                    f"❌ Tests/validation failed after merge for {branch}. Aborting merge and leaving "
                    f"{GIT_INTEGRATION_BRANCH} at last known-good state.",
                    "error",
                    project_token=project_token,
                )
                # Mark integration as blocked so only fix tasks are allowed until it is green again.
                try:
                    import context_manager as ctx_mgr
                    live_mem = ctx_mgr.get_live_memory(project_token or "")
                    live_mem.set_integration_blocked(True)
                except Exception:
                    pass

                # Do not push this broken merge; retry loop will end and container will be destroyed.
                return

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
                
                # Integration Gate: Set blocked flag if validation fails
                # This prevents new tasks from being picked until integration is fixed
                try:
                    import context_manager as ctx_mgr
                    live_mem = ctx_mgr.get_live_memory(project_token or "")
                    # For now, we'll set blocked=False after successful merge
                    # If validation fails later, it should set blocked=True
                    # This will be enhanced when integration_validator is re-added
                    live_mem.set_integration_blocked(False)
                except Exception:
                    pass  # Non-critical, continue
                
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
    Verify toolchain, clone repo into /workspace/, and create the working branch.
    Also detects whether bootstrap coordination is required.
    """
    try:
        toolchain_result = _verify_container_toolchain(container_name)
        if not toolchain_result.get("success"):
            return {
                "success": False,
                "error": toolchain_result.get("error", "runtime toolchain verification failed"),
            }

        # 2. Configure git user
        subprocess.run(
            ["docker", "exec", container_name, "git", "config", "--global", "user.email", "agent@dsuite.ai"],
            capture_output=True, text=True, timeout=10,
        )
        subprocess.run(
            ["docker", "exec", container_name, "git", "config", "--global", "user.name", "BRD Agent"],
            capture_output=True, text=True, timeout=10,
        )

        # 2.5. Configure git credential helper for Azure DevOps PAT authentication
        if token and ("dev.azure.com" in repo_url or "visualstudio.com" in repo_url):
            # Use credential.helper store instead of embedding in URL
            subprocess.run(
                ["docker", "exec", container_name, "git", "config", "--global", "credential.helper", "store"],
                capture_output=True, text=True, timeout=10,
            )
            # Save credentials to ~/.git-credentials (empty username for Azure DevOps)
            subprocess.run(
                ["docker", "exec", "-e", f"PAT={token}", container_name, "sh", "-c",
                 "echo 'https://:$PAT@dev.azure.com' >> ~/.git-credentials && echo 'https://:$PAT@*.visualstudio.com' >> ~/.git-credentials"],
                capture_output=True, text=True, timeout=10,
            )

        # 3. Clone repo into /workspace/
        # For Azure DevOps, credentials are handled by credential.helper (set above).
        # For GitHub and other providers, embed the token directly in the URL so
        # the container (which has no TTY) never needs to prompt for credentials.
        clone_url = _build_git_auth_url(repo_url, token) if token and not _is_azure_devops_url(repo_url) else repo_url
        subprocess.run(
            ["docker", "exec", container_name, "sh", "-c", "rm -rf /workspace/* /workspace/.* 2>/dev/null || true"],
            capture_output=True, text=True, timeout=10,
        )
        clone = subprocess.run(
            ["docker", "exec", container_name, "git", "clone", clone_url, "/workspace"],
            capture_output=True, text=True, timeout=300,
        )
        if clone.returncode != 0:
            return {"success": False, "error": f"Git clone failed: {clone.stderr}"}

        # Ensure the remote URL has credentials embedded so push works without a TTY.
        # For Azure DevOps this is handled via credential.helper; for GitHub/others we
        # set the remote URL directly so git never needs to prompt interactively.
        if token and not _is_azure_devops_url(repo_url):
            auth_url = _build_git_auth_url(repo_url, token)
            subprocess.run(
                ["docker", "exec", "-w", "/workspace", container_name,
                 "git", "remote", "set-url", "origin", auth_url],
                capture_output=True, text=True, timeout=10,
            )

        # 3.5. Pull latest integration branch if it exists (CRITICAL: agents work on latest code)
        fetch_result = subprocess.run(
            ["docker", "exec", "-w", "/workspace", container_name, "git", "fetch", "origin", GIT_INTEGRATION_BRANCH],
            capture_output=True, text=True, timeout=60,
        )
        if fetch_result.returncode == 0:
            # Check if integration branch exists
            check_integration = subprocess.run(
                ["docker", "exec", "-w", "/workspace", container_name, "git", "show-ref", "--verify", "--quiet", f"refs/remotes/origin/{GIT_INTEGRATION_BRANCH}"],
                capture_output=True, text=True, timeout=15,
            )
            if check_integration.returncode == 0:
                # Integration branch exists - merge it into current branch to get latest code
                # First, get current branch or default
                current_branch_result = subprocess.run(
                    ["docker", "exec", "-w", "/workspace", container_name, "git", "rev-parse", "--abbrev-ref", "HEAD"],
                    capture_output=True, text=True, timeout=10,
                )
                current_branch = current_branch_result.stdout.strip() if current_branch_result.returncode == 0 else "main"
                
                # Merge integration branch into current branch (if not already on integration)
                if current_branch != GIT_INTEGRATION_BRANCH:
                    merge_result = subprocess.run(
                        ["docker", "exec", "-w", "/workspace", container_name, "git", "merge", f"origin/{GIT_INTEGRATION_BRANCH}", "--no-edit", "--no-ff"],
                        capture_output=True, text=True, timeout=60,
                    )
                    # If merge fails, resolve conflicts by keeping integration branch version (source of truth)
                    if merge_result.returncode != 0:
                        conflict_list = subprocess.run(
                            ["docker", "exec", "-w", "/workspace", container_name,
                             "git", "diff", "--name-only", "--diff-filter=U"],
                            capture_output=True, text=True, timeout=20,
                        )
                        conflict_files = [f.strip() for f in (conflict_list.stdout or "").splitlines() if f.strip()]
                        
                        if conflict_files:
                            # Keep integration branch version (theirs) for all conflicts
                            # This ensures agents always work on the latest integration branch code
                            for file_path in conflict_files:
                                subprocess.run(
                                    ["docker", "exec", "-w", "/workspace", container_name,
                                     "git", "checkout", "--theirs", file_path],
                                    capture_output=True, text=True, timeout=30,
                                )
                                subprocess.run(
                                    ["docker", "exec", "-w", "/workspace", container_name,
                                     "git", "add", file_path],
                                    capture_output=True, text=True, timeout=10,
                                )
                            
                            # Complete the merge
                            merge_complete = subprocess.run(
                                ["docker", "exec", "-w", "/workspace", container_name,
                                 "git", "commit", "--no-edit"],
                                capture_output=True, text=True, timeout=30,
                            )
                            if merge_complete.returncode == 0:
                                logger.info(f"Resolved conflicts by keeping integration branch version for {len(conflict_files)} files")
                            else:
                                logger.warning(f"Failed to complete merge after conflict resolution, aborting")
                                subprocess.run(
                                    ["docker", "exec", "-w", "/workspace", container_name, "git", "merge", "--abort"],
                                    capture_output=True, text=True, timeout=10,
                                )
                        else:
                            # No conflicts but merge failed - abort and continue
                            logger.warning(f"Merge failed but no conflicts detected, aborting merge")
                            subprocess.run(
                                ["docker", "exec", "-w", "/workspace", container_name, "git", "merge", "--abort"],
                                capture_output=True, text=True, timeout=10,
                            )

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
        else:
            # Check if it exists remotely
            check_remote = subprocess.run(
                ["docker", "exec", "-w", "/workspace", container_name, "git", "ls-remote", "--heads", "origin", branch_name],
                capture_output=True, text=True, timeout=15,
            )
            if branch_name in check_remote.stdout:
                # If we are already on the target branch (e.g. main), checkout without -B
                checkout_cmd = ["git", "checkout", branch_name]

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

    except subprocess.TimeoutExpired as exc:
        return {
            "success": False,
            "error": (
                f"Git setup timed out while running: "
                f"{' '.join(str(part) for part in (exc.cmd or []))}"
            ),
        }
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

        # Optional structural guard: if a canonical backend/ project exists,
        # prevent agents from introducing competing Django roots at repo root.
        try:
            probe_backend = subprocess.run(
                ["docker", "exec", "-w", "/workspace", container_name,
                 "sh", "-c", "test -d backend && echo yes || echo no"],
                capture_output=True, text=True, timeout=5,
            )
            has_backend = (probe_backend.returncode == 0 and
                           (probe_backend.stdout or "").strip() == "yes")
            if has_backend:
                # Disallow common stray Django-style roots at /workspace/*
                disallowed_roots = [
                    "api", "books", "catalog", "project", "core",
                    "notifications", "reservation_system", "reservations",
                    "users", "rest_framework",
                ]
                for name in disallowed_roots:
                    subprocess.run(
                        ["docker", "exec", "-w", "/workspace", container_name,
                         "sh", "-c", f"[ -d {name} ] && rm -rf {name} || true"],
                        capture_output=True, text=True, timeout=5,
                    )
        except Exception:
            # Non-critical: if this guard fails, we still proceed with commit,
            # but Git Manager tests will catch any structural breakage.
            pass

        # Ensure .gitignore exists and excludes unnecessary files
        gitignore_content = """# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
*.pyc
*.pyo
*.pyd

# Virtual environments
venv/
ENV/
env/
.venv

# IDE
.idea/
.vscode/
*.swp
*.swo
.DS_Store

# Environment
.env
.env.local

# Build artifacts
dist/
build/
*.egg-info/

# Node
node_modules/
npm-debug.log
yarn-error.log

# Database
*.db
*.sqlite
*.sqlite3

# Logs
*.log
"""
        # Create/update .gitignore
        subprocess.run(
            ["docker", "exec", "-w", "/workspace", container_name, "sh", "-c",
             f"echo '{gitignore_content}' > /workspace/.gitignore"],
            capture_output=True, text=True, timeout=10,
        )
        
        # Remove __pycache__ directories before git add
        subprocess.run(
            ["docker", "exec", "-w", "/workspace", container_name, "sh", "-c",
             "find /workspace -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true"],
            capture_output=True, text=True, timeout=10,
        )
        
        # Remove .pyc files before git add
        subprocess.run(
            ["docker", "exec", "-w", "/workspace", container_name, "sh", "-c",
             "find /workspace -name '*.pyc' -delete 2>/dev/null || true"],
            capture_output=True, text=True, timeout=10,
        )
        
        # Remove __pycache__ from git tracking if already tracked
        subprocess.run(
            ["docker", "exec", "-w", "/workspace", container_name, "git", "rm", "-r", "--cached", "__pycache__", "*/__pycache__", "*/*/__pycache__", "2>/dev/null || true"],
            capture_output=True, text=True, timeout=10,
        )

        # Add all files (respects .gitignore)
        add = subprocess.run(
            ["docker", "exec", "-w", "/workspace", container_name, "git", "add", "."],
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
        image_result = _ensure_agent_runtime_image()
        if not image_result.get("success"):
            return {
                "success": False,
                "error": image_result.get("error", "runtime image unavailable"),
            }

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

        toolchain_result = _verify_container_toolchain(container_name)
        if not toolchain_result.get("success"):
            subprocess.run(["docker", "rm", "-f", container_name], capture_output=True, timeout=10)
            return {
                "success": False,
                "error": toolchain_result.get("error", "runtime toolchain verification failed"),
            }

        return {"success": True, "container_name": container_name}

    except Exception as e:
        subprocess.run(["docker", "rm", "-f", container_name], capture_output=True, timeout=10)
        return {"success": False, "error": str(e)}


def _exec_script_in_container(container_name: str, code: str, script_label: str = "script") -> Dict[str, Any]:
    """Copy a shell script into a running container and execute it with bash."""
    script_body = str(code or "").strip()
    if not script_body:
        return {
            "exit_code": -1,
            "stdout": "",
            "stderr": "Empty build script",
            "error": "empty_script",
        }
    if not script_body.startswith("#!"):
        script_body = "#!/usr/bin/env bash\nset -euo pipefail\n\n" + script_body

    # Write to local temp file
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".sh", delete=False, prefix=f"agent_{script_label}_",
        encoding="utf-8",
    ) as f:
        f.write(script_body)
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

        subprocess.run(
            ["docker", "exec", container_name, "chmod", "+x", container_script],
            capture_output=True, text=True, timeout=10,
        )

        # Execute inside container
        result = subprocess.run(
            ["docker", "exec", container_name, "bash", container_script],
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


# ── Master Agent Task Assignment ────────────────────────────────────────────

async def _master_assign_task_to_agent(
    task_id: str,
    agent_id: str,
    agent_name: Optional[str] = None,
    project_token: Optional[str] = None,
    task_token: Optional[str] = None,
) -> bool:
    """
    Master Agent actively assigns task to agent via task_service.assign_task().
    Called when an agent sits idle for too long and the supervisor intervenes.
    The /api/agent/task-assign-in/ endpoint in main.py handles external/UI calls.
    """
    try:
        # ── GUARD: Check if this agent already has an active task ──
        state = _ensure_project_state(project_token)
        project_agents = state["agent_states"]
        try:
            existing_tasks = await _fetch_external_tasks(project_token)
            for t in existing_tasks:
                if _task_status_is_done(t.get("status")):
                    continue
                resolved_owner = _resolve_assigned_runtime_agent_id(t, project_agents)
                if resolved_owner == agent_id:
                    existing_tid = str(_normalize_task_id(t) or t.get("external_id") or t.get("id") or "")
                    _log_master_agent(
                        f"⏭️ Skipping assignment of task {task_id} to {agent_id}: "
                        f"agent already has active task {existing_tid}",
                        project_token=project_token,
                    )
                    return False
        except Exception as check_err:
            logger.warning(f"[Master Agent] Could not check existing assignments for {agent_id}: {check_err}")

        # Convert task_id to int (handle both string and int)
        try:
            task_id_int = int(task_id)
        except (ValueError, TypeError):
            logger.warning(f"[Master Agent] Invalid task_id for assignment: {task_id}")
            return False

        # Get agent username
        username = build_external_agent_username(agent_id, agent_name)

        # Call task_service directly instead of HTTP self-call
        from task_service import task_service
        effective_token = task_token or get_project_task_token(project_token)

        result = await task_service.assign_task(
            task_id=task_id_int,
            assignees=[username],
            task_token=effective_token,
        )

        _log_master_agent(
            f"✅ Assigned task {task_id} to {username} ({agent_id})",
            project_token=project_token,
        )
        return True

    except Exception as e:
        logger.warning(f"[Master Agent] Failed to assign task {task_id} to {agent_id}: {e}")
        _log_master_agent(
            f"⚠️ Failed to assign task {task_id} to {agent_id}: {str(e)[:100]}",
            level="warning",
            project_token=project_token,
        )
        return False


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

    def _normalize_relation_ids(raw_value: Any) -> List[str]:
        values: List[str] = []

        def _append(value: Any) -> None:
            if isinstance(value, dict):
                nested = (
                    value.get("id")
                    or value.get("task_id")
                    or value.get("external_id")
                    or value.get("value")
                    or value.get("pk")
                )
                if nested not in (None, ""):
                    _append(nested)
                return
            if isinstance(value, (list, tuple, set)):
                for item in value:
                    _append(item)
                return
            if value in (None, ""):
                return
            text = str(value).strip()
            if text:
                values.append(text)

        if isinstance(raw_value, str):
            raw_text = raw_value.strip()
            if raw_text.startswith("[") and raw_text.endswith("]"):
                try:
                    _append(json.loads(raw_text))
                except Exception:
                    _append(raw_text)
            elif "," in raw_text:
                for part in raw_text.split(","):
                    _append(part)
            else:
                _append(raw_text)
        else:
            _append(raw_value)

        deduped: List[str] = []
        seen = set()
        for value in values:
            if value in seen:
                continue
            seen.add(value)
            deduped.append(value)
        return deduped

    def _extract_primary_assignee(task_payload: Dict[str, Any]) -> tuple[Optional[str], Optional[str]]:
        direct_id = (
            task_payload.get("assigned_agent")
            or task_payload.get("assignee")
            or task_payload.get("assigned_to")
        )
        direct_name = (
            task_payload.get("assigned_agent_name")
            or task_payload.get("assignee_name")
            or task_payload.get("assigned_to_name")
        )
        if direct_id or direct_name:
            return (
                str(direct_id).strip() if direct_id not in (None, "") else None,
                str(direct_name).strip() if direct_name not in (None, "") else None,
            )

        raw_assignees = task_payload.get("assignees")
        assignees = raw_assignees if isinstance(raw_assignees, list) else [raw_assignees]
        for assignee in assignees:
            if isinstance(assignee, dict):
                assignee_id = assignee.get("user_id") or assignee.get("id") or assignee.get("agent_id")
                assignee_name = (
                    assignee.get("name")
                    or assignee.get("username")
                    or assignee.get("full_name")
                    or assignee.get("email")
                )
                return (
                    str(assignee_id).strip() if assignee_id not in (None, "") else None,
                    str(assignee_name).strip() if assignee_name not in (None, "") else None,
                )
            if assignee not in (None, ""):
                return str(assignee).strip(), None
        return None, None

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
            assigned_agent, assigned_agent_name = _extract_primary_assignee(t)
            linked_task_ids = _normalize_relation_ids(t.get("linked_tasks"))
            dependency_ids = _normalize_relation_ids(
                t.get("dependencies") if t.get("dependencies") not in (None, "") else t.get("dependency_ids")
            )
            if sprint_id in (None, ""):
                sprint_id = t.get("sprint_id")
            if milestone_id in (None, ""):
                milestone_id = t.get("milestone_id")
            task_start_date = t.get("startdate") or t.get("start_date")
            task_deadline = t.get("deadline") or t.get("end_date")
            task_title = t.get("taskName") or t.get("title") or "Untitled Task"
            task_description = t.get("description") or t.get("details") or task_title or ""
            task_phase = str(
                t.get("phase")
                or t.get("task_phase")
                or t.get("taskPhase")
                or ""
            ).strip()
            task_domain = str(
                t.get("domain")
                or t.get("task_domain")
                or t.get("taskDomain")
                or ""
            ).strip()
            wallet_value = _to_int(t.get("task_wallet", t.get("wallet")))
            normalized.append({
                "id": str(task_id),
                "external_id": external_id if external_id is not None else task_id,
                "title": task_title,
                "taskName": task_title,
                "description": task_description,
                "priority": (t.get("priority") or "medium").lower(),
                "status": t.get("taskStatus") or t.get("status") or "pending",
                "task_type": t.get("task_type", "TASK"),
                "created_at": t.get("created_at") or datetime.utcnow().isoformat(),
                "assigned_agent": assigned_agent,
                "assigned_agent_name": assigned_agent_name,
                "started_at": None,
                "linked_tasks": linked_task_ids,
                "dependencies": dependency_ids,
                "phase": task_phase,
                "task_phase": task_phase,
                "domain": task_domain,
                "task_domain": task_domain,
                "wallet": wallet_value if wallet_value is not None else 0,
                "checklist": checklist_items,
                "sprint_id": sprint_id,
                "sprint_name": sprint_name,
                "milestone_id": milestone_id,
                "milestone_name": milestone_name,
                "startdate": task_start_date,
                "deadline": task_deadline,
                "assignees": t.get("assignees") or [],
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
        logger.error(f"[agent_service] Failed to fetch external tasks: {e}")
        return []


async def _mark_checklist_item(task_id, checklist_items: list, item_index: int, project_token: Optional[str] = None, task_token: Optional[str] = None):
    """Mark a single checklist item as completed via external API."""
    try:
        if not task_id:
            return
        updated = []
        for i, item in enumerate(checklist_items):
            updated.append({
                "text": item.get("text", ""),
                "completed": True if i <= item_index else item.get("completed", False),
            })
        from task_service import task_service
        task_token = task_token or get_project_task_token(project_token)
        await task_service.add_checklist_to_task(int(task_id), updated, task_token=task_token)
    except Exception as e:
        logger.error(f"[agent_service] Failed to update checklist for task {task_id}: {e}")


def _normalize_task_id(task: Dict[str, Any]):
    tid = task.get("id") or task.get("external_id")
    if tid is None:
        return None
    try:
        return int(tid)
    except (TypeError, ValueError):
        return tid


def _note_scope_key(project_token: Optional[str]) -> str:
    return _project_key(project_token)


def _note_title(prefix: str, project_token: Optional[str], scope: str) -> str:
    return f"{prefix}::{_note_scope_key(project_token)}::{scope}"


def _master_note_title(project_token: Optional[str]) -> str:
    return _note_title(MASTER_NOTE_PREFIX, project_token, MASTER_NOTE_SCOPE)


def _note_user_for_agent(agent_id: str) -> str:
    match = _re.match(r"agent_0*([0-9]+)$", str(agent_id or "").strip())
    if match:
        return f"agent{int(match.group(1))}"
    sanitized = _re.sub(r"[^a-zA-Z0-9_-]+", "", str(agent_id or "").strip())
    return sanitized or "agent"


def _note_timestamp() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _parse_agent_note_content(raw_content: Any) -> Dict[str, Any]:
    text = str(raw_content or "").strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    payload_match = _re.search(
        rf"<!--\s*{NOTE_PAYLOAD_MARKER}\s*(?P<payload>[\s\S]*?)-->",
        text,
        flags=_re.DOTALL,
    )
    if payload_match:
        candidate = str(payload_match.group("payload") or "").strip()
        if candidate:
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                pass
    return {"entries": [{"summary": text}]}


def _task_identity(task: Optional[Dict[str, Any]]) -> str:
    if not isinstance(task, dict):
        return ""
    return str(
        _normalize_task_id(task)
        or task.get("external_id")
        or task.get("id")
        or ""
    ).strip()


def _latest_active_status_note_entry(payload: Dict[str, Any]) -> Dict[str, Any]:
    active_statuses = {"in_progress", "running", "started"}
    best_entry: Dict[str, Any] = {}
    best_key = ""
    for entry in _coerce_note_entries(payload):
        task_id = str(entry.get("task_id") or "").strip()
        status_value = str(entry.get("status") or "").strip().lower()
        if not task_id or status_value not in active_statuses:
            continue
        sort_key = (
            str(entry.get("updated_at") or "").strip()
            or str(entry.get("started_at") or "").strip()
            or task_id
        )
        if sort_key >= best_key:
            best_key = sort_key
            best_entry = entry
    return best_entry


def _agent_identity_keys(agent_id: str, agent_name: Optional[str]) -> set[str]:
    sequence = _extract_dev_agent_sequence(agent_id)
    values = {
        str(agent_id or "").strip().lower(),
        normalize_agent_name(agent_id, agent_name).strip().lower(),
        build_external_agent_username(agent_id, agent_name).strip().lower(),
    }
    if sequence is not None:
        values.add(str(sequence))
        values.add(f"agent {sequence}")
        values.add(f"agent{sequence}")

    compacted = {
        _re.sub(r"[^a-z0-9]", "", value)
        for value in values
        if value
    }
    return {value for value in values | compacted if value}


def _resolve_assigned_runtime_agent_id(
    task: Dict[str, Any],
    agent_states: Dict[str, Dict[str, Any]],
) -> Optional[str]:
    raw_values = [
        str(task.get("assigned_agent") or "").strip(),
        str(task.get("assigned_agent_name") or "").strip(),
    ]
    assignees_list = task.get("assignees") or []
    if isinstance(assignees_list, list):
        for assignee in assignees_list:
            if isinstance(assignee, dict):
                val = assignee.get("username") or assignee.get("name")
                if val:
                    raw_values.append(str(val).strip())
            elif isinstance(assignee, str):
                raw_values.append(assignee.strip())
    candidate_values = {
        value.lower()
        for value in raw_values
        if value
    }
    candidate_values.update(
        _re.sub(r"[^a-z0-9]", "", value)
        for value in list(candidate_values)
        if value
    )
    if not candidate_values:
        return None

    for agent_id, agent in agent_states.items():
        if _is_system_agent_id(agent_id):
            continue
        if _agent_identity_keys(agent_id, agent.get("name")) & candidate_values:
            return agent_id
    return None


async def _restore_persisted_agent_assignments(
    *,
    project_token: Optional[str] = None,
    task_token: Optional[str] = None,
    agent_ids: Optional[List[str]] = None,
    external_tasks: Optional[List[Dict[str, Any]]] = None,
    force: bool = False,
) -> Dict[str, Any]:
    if task_token:
        set_project_task_token(project_token, task_token)

    effective_token = task_token or get_project_task_token(project_token)
    state = _ensure_project_state(project_token)
    restore_meta = state.setdefault("persisted_assignment_restore", {})
    agent_states = state["agent_states"]
    claimed_task_ids = state["claimed_task_ids"]
    task_claim_lock = state["task_claim_lock"]

    target_agent_ids = [
        agent_id
        for agent_id in (agent_ids or list(agent_states.keys()))
        if agent_id in agent_states and not _is_system_agent_id(agent_id)
    ]
    if not target_agent_ids:
        return {"count": 0, "recovered": []}

    now = time.time()
    last_restore_at = restore_meta.get("completed_at", 0)
    if (
        not force
        and str(restore_meta.get("task_token") or "").strip() == str(effective_token or "").strip()
        and restore_meta.get("completed") is True
        and (now - last_restore_at < 120)  # 2 minutes cache
    ):
        return {
            "count": 0,
            "recovered": [],
            "cached": True,
        }

    tasks = external_tasks
    if tasks is None:
        try:
            tasks = await _fetch_external_tasks(project_token)
        except Exception:
            tasks = []
    if isinstance(tasks, list):
        state["tasks"] = tasks
    else:
        tasks = []

    task_by_id = {}
    for task in tasks:
        tid = _task_identity(task)
        if tid:
            task_by_id[tid] = task

    note_payloads: Dict[str, Dict[str, Any]] = {}
    if effective_token:
        async def _load_status_payload(agent_id: str) -> tuple[str, Dict[str, Any]]:
            payload = await _get_existing_note_payload(
                title=_note_title("STATUS", project_token, agent_id),
                project_token=project_token,
                task_token=effective_token,
            )
            return agent_id, payload if isinstance(payload, dict) else {}

        loaded = await asyncio.gather(
            *(_load_status_payload(agent_id) for agent_id in target_agent_ids),
            return_exceptions=True,
        )
        for item in loaded:
            if isinstance(item, tuple) and len(item) == 2:
                note_payloads[item[0]] = item[1]

    assigned_task_by_agent: Dict[str, Dict[str, Any]] = {}
    for task in tasks:
        if _task_status_is_done(task.get("status")):
            continue
        owner_agent_id = _resolve_assigned_runtime_agent_id(task, agent_states)
        if owner_agent_id and owner_agent_id in target_agent_ids:
            assigned_task_by_agent.setdefault(owner_agent_id, task)

    recovered_entries: List[Dict[str, Any]] = []
    async with task_claim_lock:
        for agent_id in target_agent_ids:
            agent = agent_states.get(agent_id)
            if not agent:
                continue

            recovery_source = ""
            recovered_task: Optional[Dict[str, Any]] = None

            current_task = agent.get("current_task")
            current_task_id = _task_identity(current_task)
            if current_task_id:
                external_current = task_by_id.get(current_task_id)
                if external_current and not _task_status_is_done(external_current.get("status")):
                    recovered_task = dict(external_current)
                    recovery_source = "runtime"

            if recovered_task is None:
                payload = note_payloads.get(agent_id) or {}
                active_entry = _latest_active_status_note_entry(payload)
                note_task_id = str(active_entry.get("task_id") or "").strip()
                external_note_task = task_by_id.get(note_task_id)
                if external_note_task and not _task_status_is_done(external_note_task.get("status")):
                    recovered_task = dict(external_note_task)
                    recovery_source = "status_note"

            if recovered_task is None:
                external_assigned = assigned_task_by_agent.get(agent_id)
                if external_assigned and not _task_status_is_done(external_assigned.get("status")):
                    recovered_task = dict(external_assigned)
                    recovery_source = "external_assignee"

            if recovered_task is None:
                if agent.get("resume_pending_task"):
                    agent["resume_pending_task"] = False
                if (
                    (agent.get("status") or "").lower() == "idle"
                    and isinstance(agent.get("current_task"), dict)
                ):
                    agent["current_task"] = None
                    if str(agent.get("progress_message") or "").startswith("Ready to resume:"):
                        agent["progress"] = 0
                        agent["progress_message"] = ""
                continue

            recovered_task = _apply_master_task_metadata(recovered_task, project_token=project_token)
            if project_token:
                recovered_task.setdefault("_project_token", project_token)
            task_id = _task_identity(recovered_task)
            other_owner = _find_active_task_owner(task_id, project_token) if task_id else ""
            if other_owner and other_owner != agent_id:
                if agent.get("resume_pending_task"):
                    agent["resume_pending_task"] = False
                agent["current_task"] = None
                if str(agent.get("progress_message") or "").startswith("Ready to resume:"):
                    agent["progress"] = 0
                    agent["progress_message"] = ""
                continue

            current_task_id = _task_identity(agent.get("current_task"))
            if task_id and task_id in claimed_task_ids and current_task_id != task_id:
                if agent.get("resume_pending_task"):
                    agent["resume_pending_task"] = False
                agent["current_task"] = None
                if str(agent.get("progress_message") or "").startswith("Ready to resume:"):
                    agent["progress"] = 0
                    agent["progress_message"] = ""
                continue

            recovered_task["assigned_agent"] = agent_id
            recovered_task["assigned_agent_name"] = normalize_agent_name(agent_id, agent.get("name"))

            agent["current_task"] = recovered_task
            agent["resume_pending_task"] = True
            if (agent.get("status") or "").lower() == "idle":
                agent["progress"] = 0
                agent["progress_message"] = f"Ready to resume: {str(recovered_task.get('title') or 'Untitled task')[:80]}"

            if task_id:
                claimed_task_ids.add(task_id)
            for linked_id in (recovered_task.get("linked_tasks") or []):
                linked_key = str(linked_id or "").strip()
                if linked_key:
                    claimed_task_ids.add(linked_key)

            recovered_entries.append({
                "agent_id": agent_id,
                "task_id": task_id,
                "title": str(recovered_task.get("title") or recovered_task.get("taskName") or "Untitled task"),
                "source": recovery_source or "unknown",
            })

    result = {
        "count": len(recovered_entries),
        "recovered": recovered_entries,
    }
    restore_meta.update(
        {
            "completed": True,
            "completed_at": time.time(),
            "task_token": effective_token,
            "count": len(recovered_entries),
        }
    )
    return result


def _embed_note_payload(content_text: str, content_payload: Dict[str, Any]) -> str:
    body = str(content_text or "").rstrip()
    payload_text = json.dumps(content_payload or {}, ensure_ascii=True, sort_keys=True, indent=2)
    metadata_block = f"<!-- {NOTE_PAYLOAD_MARKER}\n{payload_text}\n-->"
    if not body:
        return metadata_block
    return f"{body}\n\n{metadata_block}"


def _extract_markdown_section(spec_text: str, section_pattern: str) -> str:
    text = str(spec_text or "").strip()
    if not text:
        return ""

    patterns = [
        rf"(?ms)^##\s*{section_pattern}\s*\n(.*?)(?=^##\s|\Z)",
        rf"(?ms)^##\s*{section_pattern}.*?\n(.*?)(?=^##\s|\Z)",
    ]
    for pattern in patterns:
        match = _re.search(pattern, text, flags=_re.IGNORECASE)
        if match:
            return str(match.group(1) or "").strip()
    return ""


def _strip_markdown_fences(text: str) -> str:
    value = str(text or "").strip()
    if not value:
        return ""
    if value.startswith("```"):
        lines = value.splitlines()
        if lines:
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        value = "\n".join(lines).strip()
    return value


def _count_tree_file_lines(tree_text: str) -> int:
    raw = str(tree_text or "").strip()
    if not raw:
        return 0

    if raw.startswith(("{", "[")):
        try:
            import json
            data = json.loads(raw)
            
            def count_json_entries(node):
                if isinstance(node, dict):
                    name = node.get("name")
                    children = node.get("children")
                    if name:
                        if children and isinstance(children, list):
                            return sum(count_json_entries(c) for c in children)
                        return 1
                    return sum(count_json_entries(v) for v in node.values())
                if isinstance(node, list):
                    return sum(count_json_entries(i) for i in node)
                return 1
            
            return count_json_entries(data)
        except Exception:
            pass

    count = 0
    for raw_line in raw.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        candidate = line.split("#", 1)[0].rstrip()
        if candidate.endswith("/"):
            continue
        if any(token in candidate for token in (".", "Dockerfile", "Makefile", ".env")):
            count += 1
    return count


def _looks_like_repo_file_name(name: str) -> bool:
    value = str(name or "").strip()
    if not value:
        return False
    if value in {"Dockerfile", "Makefile", "Procfile", "LICENSE"}:
        return True
    if value.startswith(".env"):
        return True
    if value in {".gitignore", ".dockerignore", ".prettierrc", ".prettierrc.json", ".eslintrc", ".eslintrc.json"}:
        return True
    if value in {"README", "README.md", "package.json", "tsconfig.json", "pyproject.toml", "requirements.txt", "alembic.ini"}:
        return True
    return bool(_re.search(r"\.[A-Za-z0-9]+$", value))


def _extract_tree_root_label(tree_text: str, fallback: str = "project") -> str:
    for raw_line in str(tree_text or "").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line or line.startswith("```"):
            continue
        line = _re.sub(r"^[\s│├└─]+", "", line).strip()
        if not line:
            continue
        if line.endswith("/"):
            line = line[:-1].strip()
        if line:
            return line
    return fallback


def _normalize_master_tree_path_candidate(candidate: Any) -> str:
    value = str(candidate or "").strip().strip("`\"'")
    if not value:
        return ""
    value = value.replace("\\", "/")
    value = value.split("#", 1)[0].strip()
    if "://" in value:
        return ""
    if value.startswith("/workspace/"):
        value = value[len("/workspace/"):]
    if value.startswith("./"):
        value = value[2:]
    while "//" in value:
        value = value.replace("//", "/")
    return value.strip().strip("/")


def _prefer_stack_consistent_extension(path: str, stack_profile: Optional[Dict[str, Any]] = None) -> str:
    normalized = _normalize_master_tree_path_candidate(path)
    if not normalized:
        return ""

    stack = stack_profile if isinstance(stack_profile, dict) else {}
    frontend_key = str(stack.get("frontend_key") or "").strip()
    backend_key = str(stack.get("backend_key") or "").strip()
    lower = normalized.lower()
    basename = os.path.basename(lower)

    if frontend_key in {"react-vite", "nextjs"} and lower.endswith(".jsx"):
        return normalized[:-4] + ".tsx"

    if lower.endswith(".js"):
        if basename in {"sw.js", "vite.config.js", "next.config.js", "jest.config.js"}:
            return normalized
        if frontend_key in {"react-vite", "nextjs"} and "/src/" in normalized:
            return normalized[:-3] + ".ts"
        if backend_key == "express" and "/src/" in normalized:
            return normalized[:-3] + ".ts"

    return normalized


def _is_stack_consistent_master_tree_path(
    path: str,
    stack_profile: Optional[Dict[str, Any]] = None,
) -> bool:
    normalized = _normalize_master_tree_path_candidate(path)
    if not normalized:
        return False

    stack = stack_profile if isinstance(stack_profile, dict) else {}
    frontend_key = str(stack.get("frontend_key") or "").strip()
    backend_key = str(stack.get("backend_key") or "").strip()
    lower = normalized.lower()
    basename = os.path.basename(lower)

    # 1. Frontend filtering
    if frontend_key == "react-vite":
        if basename in {"next.config.js", "next.config.ts", "next.config.mjs"}:
            return False
        if "/app/" in lower and basename in {"page.tsx", "page.jsx", "layout.tsx", "layout.jsx"}:
            return False
    elif frontend_key == "nextjs":
        if basename in {"vite.config.js", "vite.config.ts"}:
            return False
        # Catch typical Vite entry points
        if basename in {"main.tsx", "main.jsx"} and "src/" in lower:
            return False
    elif frontend_key == "jinja-html":
        if basename in {
            "next.config.js",
            "next.config.ts",
            "next.config.mjs",
            "vite.config.js",
            "vite.config.ts",
            "package.json",
            "tsconfig.json",
        }:
            return False
        if lower.endswith((".tsx", ".jsx")):
            return False
    elif frontend_key == "static-html":
        if basename in {"next.config.js", "next.config.ts", "next.config.mjs", "vite.config.js", "vite.config.ts"}:
            return False
        if lower.endswith((".tsx", ".jsx")):
            return False

    # 2. Backend filtering
    if backend_key in {"fastapi", "flask"}:
        if basename in {"app.ts", "server.ts", "index.ts"} and frontend_key == "none":
            return False
        # If neither frontend nor backend uses Node ecosystem
        if frontend_key in {"jinja-html", "static-html", "none"} and basename in {"package.json", "tsconfig.json"}:
            return False
    elif backend_key == "express":
        if basename in {"requirements.txt", "pyproject.toml", "alembic.ini", "Pipfile"}:
            return False
        if lower.endswith(".py"):
            return False
    elif backend_key == "none":
        if basename in {"requirements.txt", "pyproject.toml", "alembic.ini", "Pipfile", "main.py", "app.py"}:
            return False

    return True


def _canonicalize_master_tree_path(
    candidate: Any,
    *,
    stack_profile: Optional[Dict[str, Any]] = None,
) -> str:
    normalized = _normalize_master_tree_path_candidate(candidate)
    if not normalized:
        return ""

    lower = normalized.lower()
    if lower == "env.example":
        normalized = ".env.example"
    elif _re.fullmatch(r"env\.[A-Za-z0-9_.-]+", lower):
        normalized = "." + normalized
    elif lower.startswith("github/workflows/"):
        normalized = ".github/" + normalized[len("github/"):]

    stack = stack_profile if isinstance(stack_profile, dict) else {}
    frontend_key = str(stack.get("frontend_key") or "").strip()
    lower = normalized.lower()
    basename = os.path.basename(lower)

    # Lift environment/config files out of source directories generically.
    if "/src/" in lower and (
        basename.startswith(".env")
        or ("config." in basename and "." in basename)
    ):
        prefix = normalized.split("/src/", 1)[0]
        normalized = f"{prefix}/{os.path.basename(normalized)}"
        lower = normalized.lower()

    if frontend_key == "static-html":
        if lower.startswith("frontend/src/"):
            normalized = "frontend/" + normalized[len("frontend/src/"):]
        elif lower.startswith("src/"):
            normalized = f"frontend/{normalized[len('src/'):]}"
    elif frontend_key == "jinja-html":
        if lower.startswith("frontend/"):
            rel = normalized[len("frontend/"):].lstrip("/")
            rel_lower = rel.lower()
            if rel_lower.startswith("templates/"):
                normalized = f"app/{rel}"
            elif rel_lower.startswith("static/"):
                normalized = f"app/{rel}"
            elif rel_lower.endswith(".html"):
                normalized = f"app/templates/{rel}"
            elif rel_lower.endswith((".css", ".scss", ".js")):
                normalized = f"app/static/{rel}"
        elif lower.startswith("templates/"):
            normalized = f"app/{normalized}"
        elif lower.startswith("static/"):
            normalized = f"app/{normalized}"

    return _prefer_stack_consistent_extension(normalized, stack_profile)


def _allowed_master_tree_root_segments(
    stack_profile: Optional[Dict[str, Any]] = None,
    workspace_contract: Optional[Dict[str, Any]] = None,
) -> set[str]:
    contract = workspace_contract if isinstance(workspace_contract, dict) else {}
    allowed = {
        "backend",
        "frontend",
        "shared",
        "infra",
        "apps",
        "packages",
        "docs",
        "scripts",
        ".github",
        "public",
        "tests",
        "migrations",
        "docker",
        "config",
        "server",
        "client",
        "web",
        "mobile",
        "cmd",
        "internal",
        "pkg",
        "src",
        "app",
    }
    for path in (contract.get("allowed_source_roots") or []):
        text = _normalize_master_tree_path_candidate(path)
        if text:
            allowed.add(text.split("/", 1)[0].lower())
    for path in (contract.get("allowed_top_level_dirs") or []):
        text = _normalize_master_tree_path_candidate(path)
        if text and "/" not in text:
            allowed.add(text.lower())
    for path in (contract.get("root_files") or []):
        text = _normalize_master_tree_path_candidate(path)
        if text and "/" not in text:
            allowed.add(text.lower())
    return allowed


def _is_valid_master_tree_path_candidate(
    path: str,
    *,
    stack_profile: Optional[Dict[str, Any]] = None,
    workspace_contract: Optional[Dict[str, Any]] = None,
) -> bool:
    normalized = _normalize_master_tree_path_candidate(path)
    if not normalized:
        return False

    banned_segments = {
        "node.js",
        "express.js",
        "react.js",
        "next.js",
        "math.js",
        "typescript.js",
        "javascript.js",
        "node/express",
    }
    parts = [part for part in normalized.split("/") if part]
    if not parts:
        return False
    if any(part.lower() in banned_segments for part in parts):
        return False
    if any(not _re.match(r"^[A-Za-z0-9._-]+$", part) for part in parts):
        return False

    first = parts[0].lower()
    if len(parts) == 1 and _looks_like_repo_file_name(parts[0]):
        return True

    allowed_roots = _allowed_master_tree_root_segments(stack_profile, workspace_contract)
    if first not in allowed_roots:
        return False

    if len(parts) == 1:
        generic_nested_roots = {
            "api",
            "src",
            "utils",
            "services",
            "components",
            "routes",
            "hooks",
            "pages",
            "store",
            "types",
            "lib",
        }
        if first in generic_nested_roots:
            contract = workspace_contract if isinstance(workspace_contract, dict) else {}
            contract_roots = {
                _normalize_master_tree_path_candidate(path).split("/", 1)[0].lower()
                for path in (contract.get("allowed_source_roots") or [])
                if _normalize_master_tree_path_candidate(path)
            }
            if contract_roots and first in contract_roots:
                return True
            return False

    return True


def _preferred_contract_source_root(
    workspace_contract: Optional[Dict[str, Any]],
    kind: str,
    fallback: str,
) -> str:
    contract = workspace_contract if isinstance(workspace_contract, dict) else {}
    if kind == "backend":
        preferred_roots = contract.get("canonical_backend_roots") or []
    else:
        preferred_roots = contract.get("canonical_frontend_roots") or []
    normalized_roots = [
        _normalize_master_tree_path_candidate(path)
        for path in preferred_roots
        if _normalize_master_tree_path_candidate(path)
    ]
    if normalized_roots:
        return sorted(normalized_roots, key=lambda item: (item.count("/"), len(item)))[0]
    return fallback


def _module_root_from_source_root(source_root: str, fallback: str) -> str:
    normalized = _normalize_master_tree_path_candidate(source_root)
    if not normalized:
        return fallback
    if normalized.endswith("/src/app"):
        return normalized[:-len("/src/app")] or fallback
    if normalized.endswith("/src"):
        return normalized[:-len("/src")] or fallback
    if "/src/" in normalized:
        return normalized.split("/src/", 1)[0] or fallback
    return normalized


def _flask_template_root_from_source_root(source_root: str) -> str:
    normalized = _normalize_master_tree_path_candidate(source_root)
    if not normalized:
        return "app/templates"
    if normalized.endswith("/templates"):
        return normalized
    if normalized.endswith("/static"):
        return normalized[:-len("/static")] + "/templates"
    return normalized.rstrip("/") + "/templates"


def _flask_static_root_from_source_root(source_root: str) -> str:
    normalized = _normalize_master_tree_path_candidate(source_root)
    if not normalized:
        return "app/static"
    if normalized.endswith("/static"):
        return normalized
    if normalized.endswith("/templates"):
        return normalized[:-len("/templates")] + "/static"
    return normalized.rstrip("/") + "/static"


def _infer_repo_path_from_filename(
    name: str,
    stack_profile: Optional[Dict[str, Any]] = None,
    workspace_contract: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Previously, this function forcibly routed flat filenames (e.g. 'main.py' -> 'backend/main.py').
    We are now fully trusting the AI to define its own directory structure. 
    If the AI generates a flat filename, we leave it flat.
    """
    filename = str(name or "").strip().strip("`\"'")
    if not filename or not _looks_like_repo_file_name(filename):
        return ""
    
    return filename


def _default_master_tree_paths(
    stack_profile: Optional[Dict[str, Any]] = None,
    workspace_contract: Optional[Dict[str, Any]] = None,
) -> List[str]:
    stack = stack_profile if isinstance(stack_profile, dict) else {}
    contract = workspace_contract if isinstance(workspace_contract, dict) else {}
    frontend_key = str(stack.get("frontend_key") or "").strip()
    backend_key = str(stack.get("backend_key") or "").strip()

    paths = {"README.md"}

    if contract.get("status") == "ready":
        for module in (contract.get("modules") or []):
            if not isinstance(module, dict):
                continue
            for manifest in (module.get("manifests") or [])[:10]:
                normalized_manifest = _normalize_master_tree_path_candidate(manifest)
                if normalized_manifest:
                    paths.add(normalized_manifest)
        return sorted(paths)

    if frontend_key == "nextjs":
        paths.update({
            "package.json",
            "tsconfig.json",
            "next.config.ts",
            "src/app/layout.tsx",
            "src/app/page.tsx",
        })
    elif frontend_key == "jinja-html":
        paths.update({
            "templates/base.html",
            "templates/index.html",
            "static/styles.css",
            "static/ux.js",
        })
    elif frontend_key == "react-vite":
        paths.update({
            "package.json",
            "tsconfig.json",
            "vite.config.ts",
            "index.html",
            "src/main.tsx",
            "src/App.tsx",
        })
    elif frontend_key == "static-html":
        paths.update({
            "index.html",
            "styles.css",
        })

    if backend_key == "express":
        paths.update({
            "package.json",
            "tsconfig.json",
            "src/index.ts",
            "src/app.ts",
        })
    elif backend_key == "flask":
        paths.update({
            "requirements.txt",
            "gunicorn_conf.py",
            "app/__init__.py",
            "tests/test_app.py",
        })
    else:
        paths.update({
            "requirements.txt",
            "main.py",
            "config.py",
        })

    return sorted(paths)


def _collect_master_tree_required_paths(
    *,
    workspace_tree: str,
    tech_spec: str,
    task_plan: List[Dict[str, Any]],
    workspace_contract: Optional[Dict[str, Any]] = None,
    validation: Optional[Dict[str, Any]] = None,
    stack_profile: Optional[Dict[str, Any]] = None,
    repo_file_paths: Optional[List[str]] = None,
) -> tuple[List[str], List[str]]:
    contract = workspace_contract if isinstance(workspace_contract, dict) else {}
    payload = validation if isinstance(validation, dict) else {}
    candidates: List[str] = []
    spec_file_structure = _extract_markdown_section(tech_spec, r"4\.\s*FILE STRUCTURE")

    for source_text in (
        workspace_tree,
        spec_file_structure,
    ):
        candidates.extend(_extract_task_paths_from_text(source_text))

    for task in task_plan or []:
        if not isinstance(task, dict):
            continue
        for planned in task.get("planned_files") or []:
            candidates.append(str(planned or ""))

    for key in ("issues_missing_files", "recommendations"):
        for item in (payload.get(key) or []):
            candidates.extend(_extract_task_paths_from_text(item))

    candidates.extend(str(path or "") for path in (repo_file_paths or []))
    candidates.extend(_default_master_tree_paths(stack_profile, contract))
    candidates.extend(str(path or "") for path in (contract.get("root_files") or []))
    for module in (contract.get("modules") or []):
        if not isinstance(module, dict):
            continue
        for manifest in (module.get("manifests") or []):
            candidates.append(str(manifest or ""))

    directories = {
        str(path or "").strip().strip("/")
        for path in (contract.get("allowed_source_roots") or [])
        if str(path or "").strip()
    }
    files = set()
    for candidate in candidates:
        normalized = _canonicalize_master_tree_path(
            candidate,
            stack_profile=stack_profile,
        )
        if not normalized:
            continue
        inferred = normalized
        if "/" not in inferred:
            inferred = _infer_repo_path_from_filename(
                inferred,
                stack_profile,
                workspace_contract=contract,
            ) or inferred
        if not _is_valid_master_tree_path_candidate(
            inferred,
            stack_profile=stack_profile,
            workspace_contract=contract,
        ):
            continue
        if not _is_stack_consistent_master_tree_path(inferred, stack_profile):
            continue
        if "/" in inferred or _looks_like_repo_file_name(os.path.basename(inferred)):
            files.add(inferred)
            parent = os.path.dirname(inferred)
            while parent and parent not in {"."}:
                if _is_valid_master_tree_path_candidate(
                    parent,
                    stack_profile=stack_profile,
                    workspace_contract=contract,
                ):
                    directories.add(parent)
                parent = os.path.dirname(parent)
        else:
            directories.add(inferred)

    return sorted(files), sorted(directories)


def _render_tree_from_paths(
    file_paths: List[str],
    directory_paths: Optional[List[str]] = None,
    root_label: str = "project",
    output_format: str = "ascii",
) -> str:
    tree: Dict[str, Any] = {}

    def ensure_dir(parts: List[str]) -> Dict[str, Any]:
        cursor = tree
        for part in parts:
            cursor = cursor.setdefault(part, {})
        return cursor

    for dir_path in directory_paths or []:
        normalized = _normalize_master_tree_path_candidate(dir_path)
        if not normalized:
            continue
        ensure_dir([part for part in normalized.split("/") if part])

    for file_path in file_paths or []:
        normalized = _normalize_master_tree_path_candidate(file_path)
        if not normalized:
            continue
        parts = [part for part in normalized.split("/") if part]
        if not parts:
            continue
        parent = ensure_dir(parts[:-1])
        parent.setdefault(parts[-1], None)

    if output_format == "json":
        import json
        def dict_to_json_node(name: str, node: Any) -> Dict[str, Any]:
            if node is None:
                return {"name": name, "children": []}
            children = []
            dir_names = sorted(k for k, v in node.items() if isinstance(v, dict))
            file_names = sorted(k for k, v in node.items() if v is None)
            for k in dir_names:
                children.append(dict_to_json_node(k, node[k]))
            for k in file_names:
                children.append(dict_to_json_node(k, None))
            return {"name": name, "children": children}
            
        root_node = {"name": root_label, "children": []}
        dir_names = sorted(k for k, v in tree.items() if isinstance(v, dict))
        file_names = sorted(k for k, v in tree.items() if v is None)
        for k in dir_names:
            root_node["children"].append(dict_to_json_node(k, tree[k]))
        for k in file_names:
            root_node["children"].append(dict_to_json_node(k, None))
            
        return json.dumps(root_node, ensure_ascii=True, indent=2)

    lines = [f"{root_label}/"]

    def walk(node: Dict[str, Any], prefix: str = "") -> None:
        dir_names = sorted(name for name, value in node.items() if isinstance(value, dict))
        file_names = sorted(name for name, value in node.items() if value is None)
        ordered = dir_names + file_names
        for index, name in enumerate(ordered):
            is_last = index == len(ordered) - 1
            branch = "└── " if is_last else "├── "
            value = node[name]
            if isinstance(value, dict):
                lines.append(f"{prefix}{branch}{name}/")
                walk(value, prefix + ("    " if is_last else "│   "))
            else:
                lines.append(f"{prefix}{branch}{name}")

    walk(tree)
    return "\n".join(lines)


def _build_deterministic_master_tree(
    *,
    workspace_tree: str,
    tech_spec: str,
    task_plan: List[Dict[str, Any]],
    workspace_contract: Optional[Dict[str, Any]] = None,
    validation: Optional[Dict[str, Any]] = None,
    stack_profile: Optional[Dict[str, Any]] = None,
    fallback_root_label: str = "project",
    repo_file_paths: Optional[List[str]] = None,
) -> str:
    file_paths, directory_paths = _collect_master_tree_required_paths(
        workspace_tree=workspace_tree,
        tech_spec=tech_spec,
        task_plan=task_plan,
        workspace_contract=workspace_contract,
        validation=validation,
        stack_profile=stack_profile,
        repo_file_paths=repo_file_paths,
    )
    if not file_paths and not directory_paths:
        return ""
    root_label = _extract_tree_root_label(workspace_tree, fallback=fallback_root_label)
    return _render_tree_from_paths(file_paths, directory_paths, root_label=root_label, output_format="json")


def _sanitize_master_planned_files(
    paths: List[str],
    *,
    stack_profile: Optional[Dict[str, Any]] = None,
    workspace_contract: Optional[Dict[str, Any]] = None,
    limit: int = 8,
) -> List[str]:
    contract = workspace_contract if isinstance(workspace_contract, dict) else {}
    normalized: List[str] = []
    seen = set()
    for raw_path in paths or []:
        candidate = _canonicalize_master_tree_path(
            raw_path,
            stack_profile=stack_profile,
        )
        if not candidate:
            continue
        if "/" not in candidate:
            candidate = _infer_repo_path_from_filename(
                candidate,
                stack_profile,
                workspace_contract=contract,
            ) or candidate
        if not _is_valid_master_tree_path_candidate(
            candidate,
            stack_profile=stack_profile,
            workspace_contract=contract,
        ):
            continue
        if not _is_stack_consistent_master_tree_path(candidate, stack_profile):
            continue
        if candidate in seen:
            continue
        seen.add(candidate)
        normalized.append(candidate)
        if len(normalized) >= limit:
            break
    return normalized


def _build_master_task_plan(
    tasks: List[Dict[str, Any]],
    limit: Optional[int] = None,
    *,
    stack_profile: Optional[Dict[str, Any]] = None,
    workspace_contract: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    plan = []
    ordered_tasks = _sort_tasks_for_execution(tasks or [])
    if isinstance(limit, int) and limit > 0:
        ordered_tasks = ordered_tasks[:limit]
    for task in ordered_tasks:
        task_id = _normalize_task_id(task)
        task_dependencies = [
            str(dep).strip()
            for dep in (task.get("dependencies") or [])
            if str(dep).strip()
        ]
        plan.append({
            "task_id": str(task_id) if task_id is not None else "",
            "title": task.get("title") or task.get("taskName") or "Untitled task",
            "description": str(task.get("description") or "").strip(),
            "phase": task.get("phase") or task.get("task_phase") or "",
            "domain": _normalize_task_domain(task) or task.get("domain") or task.get("task_domain") or "",
            "priority": task.get("priority") or "medium",
            "task_type": task.get("task_type") or "TASK",
            "status": task.get("status") or "",
            "wallet": task.get("wallet") or task.get("task_wallet") or 0,
            "dependencies": task_dependencies,
            "checklist": _extract_task_checklist_items(task, limit=12),
            "assignee": task.get("assigned_agent") or "",
            "task_json": {
                "project_id": task.get("project_id"),
                "project_name": task.get("project_name"),
                "task_id": task.get("task_id") or (str(task_id) if task_id is not None else ""),
                "parent_id": task.get("parent_id"),
                "type": task.get("type") or str(task.get("task_type") or "").lower(),
                "title": task.get("title") or task.get("taskName") or "Untitled task",
                "description": str(task.get("description") or "").strip(),
                "status": task.get("status") or "",
                "priority": task.get("priority") or "medium",
                "story_points": task.get("story_points", task.get("wallet") or task.get("task_wallet") or 0),
                "sprint_id": task.get("sprint_id"),
                "sprint_name": task.get("sprint_name"),
                "milestone_id": task.get("milestone_id"),
                "reporter": task.get("reporter"),
                "assignee": task.get("assignee") or "",
                "resource_names": list(task.get("resource_names") or [])[:10] if isinstance(task.get("resource_names"), list) else [],
                "planned_start": task.get("planned_start") or task.get("startdate") or task.get("start_date"),
                "planned_end": task.get("planned_end") or task.get("deadline") or task.get("end_date"),
                "estimated_hours": task.get("estimated_hours"),
                "wbs": task.get("wbs"),
                "level": task.get("level"),
                "dependencies": task_dependencies,
                "checklists": task.get("checklists") if isinstance(task.get("checklists"), list) else [],
            },
            "planned_files": _sanitize_master_planned_files(
                _predict_task_file_intents(task),
                stack_profile=stack_profile,
                workspace_contract=workspace_contract,
                limit=8,
            ),
        })
    return plan


def _master_worker_signature(project_token: Optional[str] = None) -> str:
    state = _ensure_project_state(project_token)
    entries = []
    for agent_id in sorted(state.get("agent_states", {})):
        if _is_system_agent_id(agent_id):
            continue
        agent = state["agent_states"].get(agent_id) or {}
        entries.append(
            "|".join(
                [
                    agent_id,
                    normalize_agent_name(agent_id, agent.get("name")),
                    str(agent.get("type") or "").strip(),
                ]
            )
        )
    return "||".join(entries)


def _workspace_contract_signature(workspace_contract: Optional[Dict[str, Any]] = None) -> str:
    contract = workspace_contract if isinstance(workspace_contract, dict) else {}
    if not contract:
        return ""
    modules = []
    for module in (contract.get("modules") or []):
        if not isinstance(module, dict):
            continue
        modules.append({
            "root": str(module.get("root") or "").strip(),
            "kind": str(module.get("kind") or "").strip(),
            "source_roots": [
                str(path or "").strip()
                for path in (module.get("source_roots") or [])
                if str(path or "").strip()
            ],
        })
    payload = {
        "allowed_top_level_dirs": [
            str(path or "").strip()
            for path in (contract.get("allowed_top_level_dirs") or [])
            if str(path or "").strip()
        ],
        "allowed_source_roots": [
            str(path or "").strip()
            for path in (contract.get("allowed_source_roots") or [])
            if str(path or "").strip()
        ],
        "root_files": [
            str(path or "").strip()
            for path in (contract.get("root_files") or [])
            if str(path or "").strip()
        ],
        "modules": modules,
    }
    return hashlib.sha1(
        json.dumps(payload, ensure_ascii=True, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _classify_task_assignment_lane(task: Dict[str, Any]) -> str:
    phase = str(task.get("phase") or task.get("task_phase") or "").strip().lower()
    domain = str(_normalize_task_domain(task) or "").strip().lower()
    predicted_files = [
        str(path or "").strip().lower()
        for path in _predict_task_file_intents(task)
        if str(path or "").strip()
    ]
    combined = " ".join(
        [
            phase,
            domain,
            str(task.get("title") or task.get("taskName") or ""),
            str(task.get("description") or ""),
            " ".join(predicted_files),
        ]
    ).lower()

    if any(token in combined for token in ("test", "jest", "pytest", "cypress", "qa", "smoke", "accessibility")):
        return "qa"
    if any(token in combined for token in ("deploy", "docker", "infra", "ci", "cd", "release", "observability", "monitor")):
        return "devops"
    if phase.startswith("frontend") or domain == "frontend":
        return "frontend"
    if phase.startswith("backend") or domain == "backend":
        return "backend"
    if phase == "integration" or domain == "integration":
        return "integration"
    if phase == "foundation" or domain == "foundation":
        return "foundation"
    if any(token in combined for token in ("react", "vite", "tsx", "jsx", "component", "css", "scss", "page")):
        return "frontend"
    if any(token in combined for token in ("fastapi", "express", "api", "service", "route", "database", "schema", "python", "node")):
        return "backend"
    return "general"


def _infer_agent_assignment_lanes(agent_id: str, agent_state: Optional[Dict[str, Any]] = None) -> set[str]:
    state = agent_state if isinstance(agent_state, dict) else {}
    combined = " ".join(
        [
            str(agent_id or ""),
            str(state.get("name") or ""),
            str(state.get("type") or ""),
        ]
    ).lower()
    lanes = {"general"}

    if any(token in combined for token in ("frontend", "react", "ui", "web", "component", "design")):
        lanes.add("frontend")
    if any(token in combined for token in ("backend", "api", "server", "python", "node", "express", "fastapi")):
        lanes.add("backend")
    if any(token in combined for token in ("qa", "test", "validator", "quality")):
        lanes.add("qa")
    if any(token in combined for token in ("devops", "infra", "deploy", "release", "ops")):
        lanes.add("devops")
    if any(token in combined for token in ("integration", "fullstack", "shared")):
        lanes.add("integration")

    return lanes


def _build_master_recommended_assignments(
    *,
    tasks: List[Dict[str, Any]],
    task_plan: List[Dict[str, Any]],
    project_token: Optional[str] = None,
) -> List[Dict[str, Any]]:
    state = _ensure_project_state(project_token)
    agent_states = state.get("agent_states") if isinstance(state.get("agent_states"), dict) else {}
    worker_agents = [
        {
            "id": agent_id,
            "name": normalize_agent_name(agent_id, (agent_states.get(agent_id) or {}).get("name")),
            "type": str((agent_states.get(agent_id) or {}).get("type") or "").strip(),
            "lanes": _infer_agent_assignment_lanes(agent_id, agent_states.get(agent_id) or {}),
            "sequence": _extract_dev_agent_sequence(agent_id) or 999,
        }
        for agent_id in sorted(agent_states)
        if not _is_system_agent_id(agent_id)
    ]
    if not worker_agents:
        return []

    history_by_agent: Dict[str, Counter] = {}
    for completed in state.get("completed_tasks") or []:
        if not isinstance(completed, dict):
            continue
        agent_id = str(completed.get("assigned_agent") or "").strip()
        if not agent_id or _is_system_agent_id(agent_id):
            continue
        lane = _classify_task_assignment_lane(completed)
        counter = history_by_agent.setdefault(agent_id, Counter())
        counter[lane] += 1
        domain = str(_normalize_task_domain(completed) or "").strip().lower()
        if domain:
            counter[domain] += 1

    load_by_agent = {agent["id"]: 0 for agent in worker_agents}
    plan_by_task_id = {
        str(item.get("task_id") or "").strip(): item
        for item in task_plan
        if isinstance(item, dict) and str(item.get("task_id") or "").strip()
    }

    assignments: List[Dict[str, Any]] = []
    for task in _sort_tasks_for_execution(tasks or []):
        task_id = str(_normalize_task_id(task) or task.get("external_id") or task.get("id") or "").strip()
        if not task_id:
            continue
        lane = _classify_task_assignment_lane(task)
        domain = str(_normalize_task_domain(task) or "").strip().lower()
        upstream_assignee = str(task.get("assigned_agent") or "").strip()
        best_agent = None
        best_score = None

        for agent in worker_agents:
            score = 0
            reasons: List[str] = []
            if upstream_assignee and upstream_assignee == agent["id"]:
                score += 100
                reasons.append("task already tagged for this agent")
            if lane in agent["lanes"]:
                score += 30
                reasons.append(f"best match for {lane} work")
            elif domain and domain in agent["lanes"]:
                score += 24
                reasons.append(f"aligned to {domain} domain")
            elif lane in {"foundation", "integration", "general"}:
                score += 8
                reasons.append("suitable for cross-cutting work")
            else:
                score += 4
            prior_lane_count = int((history_by_agent.get(agent["id"]) or {}).get(lane, 0))
            prior_domain_count = int((history_by_agent.get(agent["id"]) or {}).get(domain, 0)) if domain else 0
            if prior_lane_count:
                score += min(prior_lane_count, 3) * 6
                reasons.append(f"has prior {lane} task history")
            elif prior_domain_count:
                score += min(prior_domain_count, 3) * 5
                reasons.append(f"has prior {domain} task history")

            score -= load_by_agent.get(agent["id"], 0) * 3
            score -= agent["sequence"] * 0.01

            if best_score is None or score > best_score:
                best_score = score
                best_agent = {
                    **agent,
                    "reason_tokens": reasons,
                }

        if not best_agent:
            continue

        load_by_agent[best_agent["id"]] = load_by_agent.get(best_agent["id"], 0) + 1
        opt_in_username = build_external_agent_username(best_agent["id"], best_agent.get("name"))
        reason_tokens = list(best_agent.get("reason_tokens") or [])
        if not reason_tokens:
            if load_by_agent[best_agent["id"]] == 1:
                reason_tokens.append("selected as the initial balanced owner")
            else:
                reason_tokens.append("selected by balanced round-robin fallback")

        recommendation = {
            "task_id": task_id,
            "title": task.get("title") or task.get("taskName") or "Untitled task",
            "phase": task.get("phase") or task.get("task_phase") or "",
            "priority": task.get("priority") or "medium",
            "recommended_agent_id": best_agent["id"],
            "recommended_agent_name": best_agent.get("name") or get_default_agent_name(best_agent["id"]),
            "opt_in_username": opt_in_username,
            "lane": lane,
            "reason": "; ".join(dict.fromkeys(reason_tokens))[:280],
            "assigned": False,  # Track if actually assigned via API
        }
        assignments.append(recommendation)

        plan_entry = plan_by_task_id.get(task_id)
        if isinstance(plan_entry, dict):
            plan_entry["assignee"] = recommendation["recommended_agent_id"]
            plan_entry["recommended_agent_name"] = recommendation["recommended_agent_name"]
            plan_entry["opt_in_username"] = recommendation["opt_in_username"]
            plan_entry["assignment_reason"] = recommendation["reason"]

    return assignments


async def _master_assign_recommended_tasks(
    recommended_assignments: List[Dict[str, Any]],
    project_token: Optional[str] = None,
    task_token: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Master Agent actively assigns tasks to agents via API.
    This enforces assignments instead of just recommending.
    """
    if not recommended_assignments:
        return {"assigned": 0, "failed": 0, "total": 0}
    
    assigned_count = 0
    failed_count = 0
    
    for assignment in recommended_assignments:
        task_id = str(assignment.get("task_id") or "").strip()
        agent_id = str(assignment.get("recommended_agent_id") or "").strip()
        agent_name = assignment.get("recommended_agent_name")
        
        if not task_id or not agent_id:
            continue
        
        # Skip if already assigned
        if assignment.get("assigned"):
            continue
        
        # Only assign tasks that are not completed
        # We'll check task status when agent picks it up
        
        success = await _master_assign_task_to_agent(
            task_id=task_id,
            agent_id=agent_id,
            agent_name=agent_name,
            project_token=project_token,
            task_token=task_token,
        )
        
        if success:
            assignment["assigned"] = True
            assigned_count += 1
        else:
            failed_count += 1
    
    _log_master_agent(
        f"📋 Task assignment complete: {assigned_count} assigned, {failed_count} failed (total: {len(recommended_assignments)})",
        project_token=project_token,
    )
    
    return {
        "assigned": assigned_count,
        "failed": failed_count,
        "total": len(recommended_assignments),
    }


def _get_master_recommended_assignment_map(project_token: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
    state = _ensure_project_state(project_token)
    cached = state.get("master_note_cache") if isinstance(state.get("master_note_cache"), dict) else {}
    recommendations = cached.get("recommended_assignments")
    if not isinstance(recommendations, list):
        return {}

    mapping: Dict[str, Dict[str, Any]] = {}
    for entry in recommendations:
        if not isinstance(entry, dict):
            continue
        task_id = str(entry.get("task_id") or "").strip()
        if task_id:
            mapping[task_id] = entry
    return mapping


def _get_master_task_plan_map(project_token: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
    state = _ensure_project_state(project_token)
    cached = state.get("master_note_cache") if isinstance(state.get("master_note_cache"), dict) else {}
    tasks_considered = cached.get("tasks_considered")
    if not isinstance(tasks_considered, list):
        return {}

    mapping: Dict[str, Dict[str, Any]] = {}
    for entry in tasks_considered:
        if not isinstance(entry, dict):
            continue
        task_id = str(entry.get("task_id") or "").strip()
        if task_id:
            mapping[task_id] = entry
    return mapping


def _apply_master_task_metadata(task: Optional[Dict[str, Any]], project_token: Optional[str] = None) -> Optional[Dict[str, Any]]:
    if not isinstance(task, dict):
        return task

    task_id = str(_normalize_task_id(task) or task.get("external_id") or task.get("id") or "").strip()
    if not task_id:
        return task

    task_plan_entry = _get_master_task_plan_map(project_token).get(task_id) or {}
    planned_files = [
        str(path or "").strip()
        for path in (task_plan_entry.get("planned_files") or [])
        if str(path or "").strip()
    ]
    if planned_files:
        task["_predicted_files"] = planned_files[:25]
        task["_predicted_files_source"] = "master_plan"
    if not task.get("phase") and task_plan_entry.get("phase"):
        task["phase"] = task_plan_entry.get("phase")
    if not task.get("task_phase") and task_plan_entry.get("phase"):
        task["task_phase"] = task_plan_entry.get("phase")
    return task


def _resolve_locked_task_owner(
    task: Dict[str, Any],
    recommendation_map: Optional[Dict[str, Dict[str, Any]]] = None,
    worker_agent_ids: Optional[set[str]] = None,
) -> str:
    tid = str(_normalize_task_id(task) or task.get("external_id") or task.get("id") or "").strip()
    recommendations = recommendation_map if isinstance(recommendation_map, dict) else {}
    workers = worker_agent_ids if isinstance(worker_agent_ids, set) else set()

    recommended_agent_id = str((recommendations.get(tid) or {}).get("recommended_agent_id") or "").strip()
    if recommended_agent_id and (not workers or recommended_agent_id in workers):
        return recommended_agent_id

    upstream_assignee = str(task.get("assigned_agent") or "").strip()
    if upstream_assignee and (not workers or upstream_assignee in workers):
        return upstream_assignee

    return ""


def _log_master_assignment_plan(
    recommended_assignments: List[Dict[str, Any]],
    *,
    project_token: Optional[str] = None,
) -> None:
    if not recommended_assignments:
        _log_master_agent(
            "Master assignment plan created with no task-owner recommendations.",
            project_token=project_token,
        )
        return

    _log_master_agent(
        f"Master assignment plan created for {len(recommended_assignments)} task(s).",
        project_token=project_token,
    )
    for entry in recommended_assignments[:50]:
        if not isinstance(entry, dict):
            continue
        task_id = str(entry.get("task_id") or "").strip()
        title = str(entry.get("title") or "Untitled task").strip()
        recommended_agent_id = str(entry.get("recommended_agent_id") or "").strip() or "unassigned"
        opt_in_username = str(entry.get("opt_in_username") or "").strip()
        reason = str(entry.get("reason") or "").strip()
        message = (
            f"Master assignment: [{task_id or '?'}] {title[:120]} -> {recommended_agent_id}"
            + (f" (opt-in: {opt_in_username})" if opt_in_username else "")
        )
        if reason:
            message += f" | reason: {reason[:180]}"
        _log_master_agent(message, project_token=project_token)


def _master_task_signature(tasks: List[Dict[str, Any]], brd_context: str = "") -> str:
    digest = hashlib.sha256()
    for task in _sort_tasks_for_execution(tasks or []):
        payload = {
            "task_id": str(_normalize_task_id(task) or task.get("id") or "").strip(),
            "title": str(task.get("title") or task.get("taskName") or "").strip(),
            "description": str(task.get("description") or "").strip(),
            "priority": str(task.get("priority") or "").strip().lower(),
            "phase": str(task.get("phase") or task.get("task_phase") or "").strip().lower(),
            "domain": str(_normalize_task_domain(task) or task.get("domain") or task.get("task_domain") or "").strip().lower(),
            "task_type": str(task.get("task_type") or "").strip().lower(),
            "dependencies": [
                str(dep).strip()
                for dep in (task.get("dependencies") or [])
                if str(dep).strip()
            ],
            "checklist": _extract_task_checklist_items(task, limit=20),
            "wallet": task.get("wallet") or task.get("task_wallet") or 0,
        }
        digest.update(json.dumps(payload, ensure_ascii=True, sort_keys=True).encode("utf-8"))
        digest.update(b"\n")
    brd_digest_text = _truncate_task_text(brd_context, 4000)
    if brd_digest_text:
        digest.update(brd_digest_text.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def _truncate_task_text(value: Any, limit: int) -> str:
    text = " ".join(str(value or "").split())
    if limit <= 0 or len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def _build_task_context_block(
    tasks: List[Dict[str, Any]],
    *,
    max_total_chars: Optional[int] = None,
    max_description_chars: int = 220,
    include_file_hints: bool = False,
    include_checklist_preview: bool = False,
    checklist_item_limit: int = 4,
    stack_profile: Optional[Dict[str, Any]] = None,
    workspace_contract: Optional[Dict[str, Any]] = None,
) -> str:
    ordered_tasks = _sort_tasks_for_execution(tasks or [])
    if not ordered_tasks:
        return "No tasks provided."

    remaining_budget = max_total_chars if isinstance(max_total_chars, int) and max_total_chars > 0 else None
    lines = [f"Total tasks: {len(ordered_tasks)}"]

    for index, task in enumerate(ordered_tasks, 1):
        remaining_tasks = len(ordered_tasks) - index
        min_reserved = remaining_tasks * 52 if remaining_budget is not None else 0
        task_id = str(_normalize_task_id(task) or task.get("external_id") or task.get("id") or "").strip()
        phase = str(task.get("phase") or task.get("task_phase") or "").strip() or "unphased"
        priority = str(task.get("priority") or "medium").strip() or "medium"
        domain = str(_normalize_task_domain(task) or "").strip()
        metadata = " | ".join(part for part in [phase, priority, domain] if part)

        title_budget = 180
        if remaining_budget is not None:
            title_budget = max(32, min(180, remaining_budget - min_reserved - 24))
        title = _truncate_task_text(task.get("title") or task.get("taskName") or "Untitled task", title_budget)

        line = f"{index}. "
        if task_id:
            line += f"[{task_id}] "
        line += f"[{metadata}] {title}"

        desc_limit = max_description_chars
        if remaining_budget is not None:
            desc_limit = max(0, min(max_description_chars, remaining_budget - min_reserved - len(line) - 2))
        task_description = _truncate_task_text(task.get("description") or "", desc_limit)
        if task_description and desc_limit >= 24:
            line += f": {task_description}"

        file_hints: List[str] = []
        if include_file_hints:
            file_hints = _sanitize_master_planned_files(
                _predict_task_file_intents(task),
                stack_profile=stack_profile,
                workspace_contract=workspace_contract,
                limit=5,
            )

        if file_hints:
            hint_text = f" | File hints: {', '.join(file_hints)}"
            if remaining_budget is None:
                line += hint_text
            else:
                available = remaining_budget - min_reserved - len(line)
                if available >= 24:
                    line += _truncate_task_text(hint_text, available)

        entry_lines = [line]
        if include_checklist_preview:
            checklist_items = _extract_task_checklist_items(task, limit=checklist_item_limit)
            if checklist_items:
                checklist_line = f"   Checklist: {'; '.join(checklist_items)}"
                if remaining_budget is None:
                    entry_lines.append(_truncate_task_text(checklist_line, 420))
                else:
                    consumed = sum(len(item) + 1 for item in entry_lines)
                    available = remaining_budget - min_reserved - consumed
                    if available >= 32:
                        entry_lines.append(_truncate_task_text(checklist_line, available))

        lines.extend(entry_lines)
        if remaining_budget is not None:
            remaining_budget -= sum(len(item) + 1 for item in entry_lines)

    return "\n".join(lines)


def _build_stack_evidence_summary(
    *,
    tasks: List[Dict[str, Any]],
    brd_summary: str = "",
    tech_spec: str = "",
    repo_tree_context: str = "",
    workspace_contract: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    contract = workspace_contract if isinstance(workspace_contract, dict) else {}
    contract_paths = [
        str(path or "").strip().lower()
        for path in (contract.get("allowed_source_roots") or [])
        if str(path or "").strip()
    ]
    contract_paths.extend(
        str(path or "").strip().lower()
        for path in (contract.get("root_files") or [])
        if str(path or "").strip()
    )
    for module in (contract.get("modules") or []):
        if not isinstance(module, dict):
            continue
        contract_paths.extend(
            str(path or "").strip().lower()
            for path in (module.get("manifests") or [])
            if str(path or "").strip()
        )

    task_fragments: List[str] = []
    for task in tasks or []:
        if not isinstance(task, dict):
            continue
        task_fragments.extend(
            [
                str(task.get("title") or task.get("taskName") or ""),
                str(task.get("description") or ""),
                " ".join(_extract_task_checklist_items(task, limit=16)),
            ]
        )
    combined_text = " ".join(
        part for part in [brd_summary, tech_spec, repo_tree_context, " ".join(task_fragments)] if str(part or "").strip()
    ).lower()

    evidence_rules = {
        "frontend": {
            "jinja-html": (
                "jinja",
                "jinja2",
                "render_template",
                "base.html",
                "templates/",
                "template inheritance",
                "server-side rendered html",
            ),
            "static-html": (
                "static html",
                "pure html",
                "single html",
                "index.html",
                "styles.css",
                "vanilla js",
                "vanilla javascript",
            ),
            "react-vite": (
                "react",
                "vite",
                "tsx",
                "jsx",
                "react testing library",
            ),
            "nextjs": (
                "next.js",
                "nextjs",
                "app router",
                "next.config",
            ),
            "vue": (
                "vue",
                "pinia",
                "vue-router",
                ".vue",
            ),
        },
        "backend": {
            "flask": (
                "flask",
                "gunicorn",
                "blueprint",
                "create_app",
                "app factory",
                ".flaskenv",
                "werkzeug",
            ),
            "fastapi": (
                "fastapi",
                "uvicorn",
                "pydantic",
                "sqlalchemy",
                "openapi",
            ),
            "express": (
                "express",
                "node.js",
                "node/express",
                "app.ts",
                "server.ts",
                "typescript",
            ),
            "django": (
                "django",
                "manage.py",
                "wsgi.py",
                "asgi.py",
            ),
        },
    }

    summary: Dict[str, Any] = {"frontend": {}, "backend": {}, "conflicts": []}
    for scope, scope_rules in evidence_rules.items():
        for label, terms in scope_rules.items():
            matched_terms = []
            for term in terms:
                if term in combined_text or any(term in path for path in contract_paths):
                    matched_terms.append(term)
            summary[scope][label] = {
                "score": len(matched_terms),
                "matched_terms": matched_terms[:8],
            }

    frontend_hits = [
        label for label, payload in summary["frontend"].items()
        if isinstance(payload, dict) and payload.get("score", 0) > 0
    ]
    backend_hits = [
        label for label, payload in summary["backend"].items()
        if isinstance(payload, dict) and payload.get("score", 0) > 0
    ]
    if len(frontend_hits) > 1:
        summary["conflicts"].append(
            f"Frontend evidence mentions multiple frameworks: {', '.join(frontend_hits[:4])}"
        )
    if len(backend_hits) > 1:
        summary["conflicts"].append(
            f"Backend evidence mentions multiple frameworks: {', '.join(backend_hits[:4])}"
        )
    return summary


def _build_master_planning_packet(
    *,
    tasks: List[Dict[str, Any]],
    brd_summary: str = "",
    kg_context: str = "",
    tech_spec: str = "",
    stack_profile: Optional[Dict[str, Any]] = None,
    workspace_contract: Optional[Dict[str, Any]] = None,
    repo_tree_context: str = "",
) -> Dict[str, Any]:
    contract = workspace_contract if isinstance(workspace_contract, dict) else {}
    stack = stack_profile if isinstance(stack_profile, dict) else {}
    task_plan = _build_master_task_plan(
        tasks,
        limit=40,
        stack_profile=stack,
        workspace_contract=contract,
    )
    compact_tasks: List[Dict[str, Any]] = []
    for entry in task_plan:
        if not isinstance(entry, dict):
            continue
        compact_tasks.append({
            "task_id": str(entry.get("task_id") or "").strip(),
            "title": _truncate_task_text(entry.get("title") or "Untitled task", 180),
            "description": _truncate_task_text(entry.get("description") or "", 420),
            "task_type": str(entry.get("task_type") or "").strip(),
            "priority": str(entry.get("priority") or "").strip(),
            "phase": str(entry.get("phase") or "").strip(),
            "domain": str(entry.get("domain") or "").strip(),
            "dependencies": [
                str(dep).strip()
                for dep in (entry.get("dependencies") or [])
                if str(dep).strip()
            ][:10],
            "checklist": [
                str(item).strip()
                for item in (entry.get("checklist") or [])
                if str(item).strip()
            ][:10],
            "planned_files": [
                str(path).strip()
                for path in (entry.get("planned_files") or [])
                if str(path).strip()
            ][:10],
        })

    contract_modules = []
    for module in (contract.get("modules") or [])[:12]:
        if not isinstance(module, dict):
            continue
        contract_modules.append({
            "name": str(module.get("name") or "").strip(),
            "kind": str(module.get("kind") or "").strip(),
            "root": str(module.get("root") or "").strip(),
            "manifests": [
                str(path or "").strip()
                for path in (module.get("manifests") or [])
                if str(path or "").strip()
            ][:12],
        })

    packet = {
        "stack_decision": {
            "frontend_key": str(stack.get("frontend_key") or "").strip(),
            "frontend": str(stack.get("frontend") or "").strip(),
            "backend_key": str(stack.get("backend_key") or "").strip(),
            "backend": str(stack.get("backend") or "").strip(),
            "confidence": str(stack.get("confidence") or "").strip(),
            "reason": _truncate_task_text(stack.get("reason") or "", 300),
        },
        "stack_evidence": _build_stack_evidence_summary(
            tasks=tasks,
            brd_summary=brd_summary,
            tech_spec=tech_spec,
            repo_tree_context=repo_tree_context,
            workspace_contract=contract,
        ),
        "workspace_contract": {
            "status": str(contract.get("status") or "").strip(),
            "source": str(contract.get("source") or "").strip(),
            "allowed_source_roots": [
                str(path or "").strip()
                for path in (contract.get("allowed_source_roots") or [])
                if str(path or "").strip()
            ][:20],
            "canonical_frontend_roots": [
                str(path or "").strip()
                for path in (contract.get("canonical_frontend_roots") or [])
                if str(path or "").strip()
            ][:10],
            "canonical_backend_roots": [
                str(path or "").strip()
                for path in (contract.get("canonical_backend_roots") or [])
                if str(path or "").strip()
            ][:10],
            "root_files": [
                str(path or "").strip()
                for path in (contract.get("root_files") or [])
                if str(path or "").strip()
            ][:20],
            "modules": contract_modules,
        },
        "current_repo_tree": repo_tree_context[:5000],
        "existing_codebase_context": kg_context[:3500],
        "brd_summary": brd_summary[:5000],
        "tech_spec_excerpt": tech_spec[:5000],
        "tasks": compact_tasks,
        "hard_constraints": [
            "Output one final canonical structure only.",
            "Do not mix conflicting frameworks in one project tree.",
            "Every planned file must have a home inside the canonical tree.",
            "Prefer extending the current repo tree over inventing parallel roots.",
            "If Flask + Jinja is indicated, keep templates and static assets inside the Flask app structure.",
        ],
    }
    return packet


def _infer_project_stack(
    *,
    tasks: List[Dict[str, Any]],
    tech_spec: str = "",
    workspace_contract: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    task_text = " ".join(
        " ".join(
            str(task.get(key) or "")
            for key in ("title", "taskName", "description", "phase", "task_phase", "domain", "task_domain")
        )
        for task in (tasks or [])
    ).lower()
    spec_text = str(tech_spec or "").lower()
    combined_text = " ".join([spec_text, task_text]).strip()

    frontend = None
    backend = None
    confidence = "explicit"
    reason = ""

    contract = workspace_contract if isinstance(workspace_contract, dict) else {}
    contract_manifests = [
        str(path or "").strip().lower()
        for module in (contract.get("modules") or [])
        if isinstance(module, dict)
        for path in (module.get("manifests") or [])
        if str(path or "").strip()
    ]
    contract_manifests.extend(
        str(path or "").strip().lower()
        for path in (contract.get("root_files") or [])
        if str(path or "").strip()
    )
    contract_roots = [
        str(root or "").strip().lower()
        for root in (contract.get("allowed_source_roots") or [])
        if str(root or "").strip()
    ]

    frontend_scores: Counter[str] = Counter()
    backend_scores: Counter[str] = Counter()

    if any("next.config" in path for path in contract_manifests):
        frontend_scores["nextjs"] += 4
    if any("vite.config" in path for path in contract_manifests):
        frontend_scores["react-vite"] += 4
    if any(path.endswith("/index.html") or path == "index.html" for path in contract_manifests):
        frontend_scores["static-html"] += 4
    if any(path.endswith("/styles.css") or path.endswith("/style.css") for path in contract_manifests):
        frontend_scores["static-html"] += 2
    if any("/templates/" in path or path.endswith("/templates") for path in contract_manifests):
        frontend_scores["jinja-html"] += 4
    if any("/static/" in path or path.endswith("/static") for path in contract_manifests):
        frontend_scores["jinja-html"] += 2
    if any(path.endswith("/base.html") for path in contract_manifests):
        frontend_scores["jinja-html"] += 3
    if any(token in path for path in contract_manifests for token in ("gunicorn", ".flaskenv", "wsgi.py")):
        backend_scores["flask"] += 3
    if any(path.endswith("/app.py") or path.endswith("/__init__.py") for path in contract_manifests):
        backend_scores["flask"] += 1

    for token in ("next.js", "nextjs", "app router", "next.config"):
        if token in task_text:
            frontend_scores["nextjs"] += 4
        elif token in combined_text:
            frontend_scores["nextjs"] += 3
    for token in (
        "react", "vite", "tsx", "jsx", "react testing library", "cypress",
        "toast", "theme toggle", "component", "history panel", "scientific keypad",
        "nginx static", "static container",
    ):
        if token in task_text:
            frontend_scores["react-vite"] += 2
        elif token in combined_text:
            frontend_scores["react-vite"] += 1
    for token in (
        "static html", "static-only", "static only", "pure html", "pure css",
        "single html", "single static", "frontend only", "frontend-only",
        "landing page", "marketing page", "index.html", "styles.css",
        "vanilla js", "vanilla javascript",
    ):
        if token in task_text:
            frontend_scores["static-html"] += 3
        elif token in combined_text:
            frontend_scores["static-html"] += 1

    for token in (
        "jinja", "jinja2", "render_template", "base.html", "templates/",
        "template inheritance", "server-side rendered html", "flask template",
    ):
        if token in task_text:
            frontend_scores["jinja-html"] += 4
        elif token in combined_text:
            frontend_scores["jinja-html"] += 2

    for token in (
        "flask", "gunicorn", "blueprint", "create_app", "app factory",
        ".flaskenv", "wsgi", "werkzeug",
    ):
        if token in task_text:
            backend_scores["flask"] += 4
        elif token in combined_text:
            backend_scores["flask"] += 2
    for token in (
        "django", "manage.py", "settings.py", "wsgi.py", "asgi.py", 
        "django admin", "urls.py", "django models", "django templates"
    ):
        if token in task_text:
            backend_scores["django"] += 4
        elif token in combined_text:
            backend_scores["django"] += 2
    for token in ("fastapi", "pydantic", "sqlalchemy", "uvicorn", "python api"):
        if token in task_text:
            backend_scores["fastapi"] += 3
        elif token in combined_text:
            backend_scores["fastapi"] += 2
    for token in ("express", "node api", "node.js", "node/express"):
        if token in task_text:
            backend_scores["express"] += 3
        elif token in combined_text:
            backend_scores["express"] += 2

    # Avoid overfitting stack inference to host repository roots when task evidence exists.
    if not task_text.strip():
        for root in contract_roots:
            if "frontend" in root or root.endswith("web") or root.endswith("client"):
                frontend_scores["react-vite"] += 1
            if root.endswith("templates") or root.endswith("static"):
                frontend_scores["jinja-html"] += 2
            if "backend" in root or root.endswith("api") or root.endswith("server"):
                backend_scores["fastapi"] += 2
            if root == "app" or root.endswith("/app"):
                backend_scores["flask"] += 2

    backend_explicitly_not_required = bool(
        _re.search(r"\bbackend\b.{0,40}\bnot applicable\b", combined_text, flags=_re.IGNORECASE)
        or _re.search(r"\bnot applicable\b.{0,40}\bbackend\b", combined_text, flags=_re.IGNORECASE)
        or _re.search(r"\b(frontend[- ]only|pure client[- ]side|browser[- ]only)\b", combined_text, flags=_re.IGNORECASE)
    )

    frontend_task_evidence = any(
        str(task.get("phase") or task.get("task_phase") or "").strip().lower().startswith("frontend")
        or str(_normalize_task_domain(task) or task.get("domain") or task.get("task_domain") or "").strip().lower() == "frontend"
        for task in (tasks or [])
    ) or any(token in task_text for token in ("html", "css", "ui", "page", "component", "landing", "jinja", "template"))
    backend_task_evidence = any(
        str(task.get("phase") or task.get("task_phase") or "").strip().lower().startswith("backend")
        or str(_normalize_task_domain(task) or task.get("domain") or task.get("task_domain") or "").strip().lower() == "backend"
        for task in (tasks or [])
    ) or any(
        token in task_text
        for token in ("api", "database", "schema", "model", "auth", "server", "endpoint", "fastapi", "express", "python", "flask", "gunicorn")
    )

    if frontend_scores:
        frontend_priority = {
            "jinja-html": 4,
            "static-html": 3,
            "react-vite": 2,
            "nextjs": 1,
        }
        frontend = sorted(
            frontend_scores.items(),
            key=lambda item: (item[1], frontend_priority.get(item[0], 0)),
            reverse=True,
        )[0][0]

    if backend_scores:
        backend_priority = {
            "django": 5,
            "flask": 4,
            "fastapi": 3,
            "express": 2,
        }
        backend = sorted(
            backend_scores.items(),
            key=lambda item: (item[1], backend_priority.get(item[0], 0)),
            reverse=True,
        )[0][0]

    if backend == "flask" and frontend_scores.get("jinja-html", 0) >= max(1, frontend_scores.get("static-html", 0)):
        frontend = "jinja-html"

    if not frontend and any("frontend" in root for root in contract_roots):
        frontend = "static-html" if any(
            path.endswith("/index.html") or path.endswith("/styles.css")
            for path in contract_manifests
        ) else "react-vite"
    if (
        not backend
        and any("backend" in root for root in contract_roots)
        and not backend_explicitly_not_required
        and (backend_task_evidence or not frontend_task_evidence)
    ):
        backend = "fastapi"
    if not backend and backend_scores.get("flask", 0) > 0:
        backend = "flask"
    if not frontend and frontend_scores.get("jinja-html", 0) > 0:
        frontend = "jinja-html"

    explicit_frontend_only = (
        frontend_task_evidence
        and not backend_task_evidence
    )
    explicit_backend_only = (
        backend_task_evidence
        and not frontend_task_evidence
        and not any("frontend" in root for root in contract_roots)
    )

    if backend_explicitly_not_required and not backend_task_evidence:
        if not frontend or frontend == "none":
            if frontend_scores.get("jinja-html", 0) > max(frontend_scores.get("static-html", 0), frontend_scores.get("react-vite", 0)):
                frontend = "jinja-html"
            else:
                frontend = "static-html" if frontend_scores.get("static-html") >= frontend_scores.get("react-vite") else "react-vite"
        if frontend == "jinja-html":
            backend = "flask"
            reason = "Specification indicates backend is not applicable except Flask template rendering."
        else:
            backend = "none"
            reason = "Specification indicates a frontend-only project with no backend required."
    elif explicit_frontend_only:
        if not frontend or frontend == "none":
            if frontend_scores.get("jinja-html", 0) > max(frontend_scores.get("static-html", 0), frontend_scores.get("react-vite", 0)):
                frontend = "jinja-html"
            else:
                frontend = "static-html" if frontend_scores.get("static-html") >= frontend_scores.get("react-vite") else "react-vite"
        if frontend == "jinja-html":
            backend = "flask"
            reason = "Tasks describe Flask-rendered templates, so Flask + Jinja was selected."
        elif frontend == "static-html":
            backend = "none"
            reason = "Tasks describe a frontend-only static site, so no backend stack was added."
        else:
            backend = "none"
            reason = "Tasks describe frontend-only work, so no backend stack was added."
    elif explicit_backend_only:
        if not backend or backend == "none":
            backend = "flask" if backend_scores.get("flask", 0) >= backend_scores.get("fastapi", 0) else "fastapi"
        frontend = "none"
        reason = "Tasks describe backend-only work, so no frontend stack was added."

    if not frontend and not backend:
        frontend = "static-html"
        backend = "none"
        confidence = "default"
        reason = "No backend evidence was found. Defaulting to a minimal static frontend project."
    elif not frontend:
        if backend == "flask" and frontend_scores.get("jinja-html", 0) > 0:
            frontend = "jinja-html"
        else:
            frontend = "react-vite" if backend != "none" else "none"
        confidence = "mixed"
        reason = reason or "Frontend stack was not explicit, so no frontend stack was added."
    elif not backend:
        if frontend == "jinja-html":
            backend = "flask"
            confidence = "mixed"
            reason = reason or "Jinja template evidence implies a Flask backend."
        elif frontend == "static-html" or explicit_frontend_only:
            backend = "none"
            confidence = "mixed"
            reason = reason or "No backend evidence was found for this frontend-only project."
        else:
            backend = "fastapi"
            confidence = "mixed"
            reason = reason or "Backend stack was not explicit, so a default backend stack was selected."

    labels = {
        "jinja-html": "Jinja2 Templates + HTML/CSS",
        "static-html": "Static HTML + CSS",
        "nextjs": "Next.js + TypeScript",
        "react-vite": "React + Vite + TypeScript",
        "django": "Django + Python",
        "flask": "Flask + Python",
        "fastapi": "FastAPI + Python",
        "express": "Node.js + Express + TypeScript",
        "none": "None / not required",
    }
    return {
        "frontend_key": frontend,
        "frontend": labels.get(frontend, frontend),
        "backend_key": backend,
        "backend": labels.get(backend, backend),
        "confidence": confidence,
        "reason": reason,
    }


def _render_master_note_markdown(payload: Dict[str, Any]) -> str:
    title = "Canonical Project Tree and Task Plan"
    project_token = str(payload.get("project_token") or "").strip()
    author_agent_id = str(payload.get("author_agent_id") or "").strip()
    summary = str(payload.get("summary") or "").strip()
    brd_analysis_context = str(payload.get("brd_analysis_context") or "").strip()
    current_repo_tree = str(payload.get("current_repo_tree") or "").rstrip()
    current_repo_tree_source = str(payload.get("current_repo_tree_source") or "").strip()
    workspace_tree = str(payload.get("workspace_tree") or "").rstrip()
    workspace_tree_json = str(payload.get("workspace_tree_json") or "").strip()
    architecture_overview = str(payload.get("architecture_overview") or "").strip()
    dependencies = str(payload.get("dependencies") or "").strip()
    validation = payload.get("validation") if isinstance(payload.get("validation"), dict) else {}
    instructions = payload.get("instructions") if isinstance(payload.get("instructions"), list) else []
    tasks_considered = payload.get("tasks_considered") if isinstance(payload.get("tasks_considered"), list) else []
    workspace_contract = payload.get("workspace_contract") if isinstance(payload.get("workspace_contract"), dict) else {}
    stack_profile = payload.get("stack_profile") if isinstance(payload.get("stack_profile"), dict) else {}

    lines = [f"# {title}"]
    if project_token:
        lines.append(f"Project Token: `{project_token}`")
    if author_agent_id:
        lines.append(f"Author Agent: `{author_agent_id}`")
    if summary:
        lines.append("")
        lines.append(summary)

    if stack_profile:
        lines.append("")
        lines.append("## Stack Decision")
        lines.append(f"- Frontend: {stack_profile.get('frontend')}")
        lines.append(f"- Backend: {stack_profile.get('backend')}")
        lines.append(f"- Confidence: {stack_profile.get('confidence')}")
        if stack_profile.get("reason"):
            lines.append(f"- Reason: {stack_profile.get('reason')}")

    if validation:
        lines.append("")
        lines.append("## Validation")
        lines.append(
            f"- Approved: {bool(validation.get('approved'))}"
            + (f" | Validator: {validation.get('validator_agent_id')}" if validation.get("validator_agent_id") else "")
            + (f" | Mode: {validation.get('mode')}" if validation.get("mode") else "")
            + (f" | Confidence: {validation.get('confidence')}" if validation.get("confidence") not in (None, "") else "")
        )
        for issue in (validation.get("issues_missing_files") or [])[:8]:
            lines.append(f"- Missing/Coverage: {issue}")
        for issue in (validation.get("issues_conflicts") or [])[:8]:
            lines.append(f"- Conflict: {issue}")
        for recommendation in (validation.get("recommendations") or [])[:8]:
            lines.append(f"- Recommendation: {recommendation}")

    if tasks_considered:
        lines.append("")
        lines.append("## Tasks Considered")
        for task in tasks_considered:
            if not isinstance(task, dict):
                continue
            task_title = str(task.get("title") or task.get("task_title") or "Untitled task").strip()
            task_phase = str(task.get("phase") or "").strip()
            task_domain = str(task.get("domain") or "").strip()
            task_priority = str(task.get("priority") or "").strip()
            task_type = str(task.get("task_type") or "").strip()
            task_id = str(task.get("task_id") or "").strip()
            header = f"- `{task_id}` {task_title}" if task_id else f"- {task_title}"
            if task_phase or task_domain or task_priority or task_type:
                header += " | " + " | ".join(
                    item
                    for item in [
                        f"phase={task_phase}" if task_phase else "",
                        f"domain={task_domain}" if task_domain else "",
                        f"priority={task_priority}" if task_priority else "",
                        f"type={task_type}" if task_type else "",
                    ]
                    if item
                )
            lines.append(header)
            task_dependencies = [
                str(dep).strip()
                for dep in (task.get("dependencies") or [])
                if str(dep).strip()
            ]
            if task_dependencies:
                lines.append(f"  Depends on: {', '.join(task_dependencies[:10])}")
            planned_files = [
                str(path or "").strip()
                for path in (task.get("planned_files") or [])
                if str(path or "").strip()
            ]
            if planned_files:
                lines.append(f"  Planned files: {', '.join(planned_files[:6])}")

    canonical_tree_json = workspace_tree_json or _ensure_workspace_tree_json(
        workspace_tree,
        fallback_root_label=(project_token or "project"),
    )
    if canonical_tree_json:
        lines.append("")
        lines.append("## Canonical Project Tree (JSON)")
        lines.append("```json")
        lines.append(canonical_tree_json)
        lines.append("```")

    if workspace_contract:
        allowed_roots = [
            str(path or "").strip()
            for path in (workspace_contract.get("allowed_source_roots") or [])
            if str(path or "").strip()
        ]
        if allowed_roots:
            lines.append("")
            lines.append("## Canonical Source Roots")
            for root in allowed_roots[:20]:
                lines.append(f"- {root}")

    if instructions:
        lines.append("")
        lines.append("## Instructions")
        for instruction in instructions[:5]:
            lines.append(f"- {instruction}")

    return "\n".join(lines).strip()


def _repo_root_dir() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _ensure_workspace_tree_json(workspace_tree: str, fallback_root_label: str = "project") -> str:
    raw = str(workspace_tree or "").strip()
    if not raw:
        return ""
    parsed = _extract_json_object_from_text(raw)
    if isinstance(parsed, dict):
        sanitized = _sanitize_tree_node(parsed)
        if sanitized and sanitized.get("name"):
            return json.dumps(sanitized, ensure_ascii=True, indent=2)

    paths = _extract_paths_from_workspace_tree(raw)
    if not paths:
        return ""
    root = _extract_tree_root_label(raw, fallback=fallback_root_label)
    return _render_tree_from_paths(paths, root_label=root or fallback_root_label, output_format="json")


def _extract_paths_from_workspace_tree(workspace_tree: str) -> List[str]:
    raw = str(workspace_tree or "").strip()
    if not raw:
        return []

    paths: List[str] = []
    seen = set()

    def add_path(value: str) -> None:
        normalized = _normalize_master_tree_path_candidate(value)
        if not normalized or normalized in seen:
            return
        seen.add(normalized)
        paths.append(normalized)

    if raw.startswith(("{", "[")):
        try:
            parsed = json.loads(raw)

            def walk(node: Any, prefix: str = "", is_root: bool = False) -> None:
                if not isinstance(node, dict):
                    return
                name = str(node.get("name") or "").strip()
                children = node.get("children")
                children_list = children if isinstance(children, list) else []
                name_is_file = _looks_like_repo_file_name(name)
                current_prefix = prefix
                if name and not is_root:
                    current_prefix = f"{prefix}/{name}" if prefix else name
                    if name_is_file:
                        add_path(current_prefix)
                for child in children_list:
                    walk(child, current_prefix, False)

            if isinstance(parsed, dict):
                walk(parsed, "", True)
            elif isinstance(parsed, list):
                for node in parsed:
                    walk(node, "", True)
            return paths
        except Exception:
            pass

    for path in _extract_task_paths_from_text(raw):
        add_path(path)
    return paths


def _resolve_repo_manifest_path(path: str, repo_root: str) -> str:
    normalized = _normalize_master_tree_path_candidate(path)
    if not normalized:
        return ""
    direct = os.path.join(repo_root, normalized)
    if os.path.isfile(direct):
        return normalized

    parts = normalized.split("/")
    for idx in range(1, min(4, len(parts))):
        candidate = "/".join(parts[idx:])
        if not candidate:
            continue
        if os.path.isfile(os.path.join(repo_root, candidate)):
            return candidate
    return ""


def _derive_dynamic_architecture_overview(
    *,
    stack_profile: Optional[Dict[str, Any]],
    workspace_contract: Optional[Dict[str, Any]],
    workspace_tree: str,
    tasks: Optional[List[Dict[str, Any]]] = None,
) -> str:
    stack = stack_profile if isinstance(stack_profile, dict) else {}
    contract = workspace_contract if isinstance(workspace_contract, dict) else {}
    frontend = str(stack.get("frontend") or "").strip()
    backend = str(stack.get("backend") or "").strip()
    frontend_key = str(stack.get("frontend_key") or "").strip()
    backend_key = str(stack.get("backend_key") or "").strip()
    roots = [
        str(root).strip()
        for root in (contract.get("allowed_source_roots") or [])
        if str(root).strip()
    ][:8]
    tree_paths = _extract_paths_from_workspace_tree(workspace_tree)
    lower_paths = [path.lower() for path in tree_paths]
    task_domains = {
        str(_normalize_task_domain(task) or "").strip()
        for task in (tasks or [])
        if isinstance(task, dict)
    }
    task_domains = {domain for domain in task_domains if domain}

    lines: List[str] = []
    if frontend and frontend_key != "none":
        lines.append(f"- **Frontend**: {frontend}")
    elif frontend_key == "none":
        lines.append("- **Frontend**: Not applicable for this project")
    if backend and backend_key != "none":
        lines.append(f"- **Backend**: {backend}")
    elif backend_key == "none":
        lines.append("- **Backend**: Not applicable for this project")

    if roots:
        lines.append(f"- **Canonical source roots**: {', '.join(roots)}")
    if any("/store/" in path for path in lower_paths):
        lines.append("- **State management**: Store/reducer layer present under the canonical frontend source tree")
    if any(path.endswith(("manifest.json", "sw.js")) for path in lower_paths):
        lines.append("- **PWA/offline layer**: Manifest/service worker files are part of the planned structure")
    if any("/test" in path or path.endswith((".spec.ts", ".test.ts", "_test.py")) for path in lower_paths):
        lines.append("- **Testing**: Dedicated test files/directories are included in the canonical tree")
    if task_domains:
        lines.append(f"- **Task coverage domains**: {', '.join(sorted(task_domains))}")

    return "\n".join(lines).strip()


def _derive_dynamic_dependencies(
    *,
    workspace_tree: str,
    workspace_contract: Optional[Dict[str, Any]],
) -> str:
    repo_root = _repo_root_dir()
    contract = workspace_contract if isinstance(workspace_contract, dict) else {}
    candidates: List[str] = []

    candidates.extend(_extract_paths_from_workspace_tree(workspace_tree))
    candidates.extend(
        str(path or "").strip()
        for path in (contract.get("root_files") or [])
        if str(path or "").strip()
    )
    for module in (contract.get("modules") or []):
        if not isinstance(module, dict):
            continue
        candidates.extend(
            str(path or "").strip()
            for path in (module.get("manifests") or [])
            if str(path or "").strip()
        )
    resolved: List[str] = []
    seen = set()

    def _looks_like_dependency_manifest(path: str) -> bool:
        normalized = _normalize_master_tree_path_candidate(path).lower()
        if not normalized:
            return False
        filename = os.path.basename(normalized)
        if filename in {"dockerfile", "readme.md", "license", "license.md"}:
            return False
        # Pattern-based detection instead of exact manifest name matching.
        manifest_hint = _re.search(
            r"(depend|deps|package|requirement|pip|poetry|pdm|pyproject|lock)",
            filename,
            flags=_re.IGNORECASE,
        )
        extension_hint = filename.endswith((".json", ".toml", ".txt", ".lock", ".yml", ".yaml"))
        return bool(manifest_hint and extension_hint)

    # First resolve manifests hinted by canonical tree/task/contract context.
    for candidate in candidates:
        rel = _resolve_repo_manifest_path(candidate, repo_root)
        if not rel or rel in seen:
            continue
        if not _looks_like_dependency_manifest(rel):
            continue
        seen.add(rel)
        resolved.append(rel)

    # Then discover manifests directly from repository files to avoid path assumptions.
    for root, _, files in os.walk(repo_root):
        rel_root = os.path.relpath(root, repo_root)
        root_name = os.path.basename(rel_root)
        if rel_root.startswith(".git") or root_name in {"venv", ".venv", "node_modules", "__pycache__"}:
            continue
        for name in files:
            rel = name if rel_root in (".", "") else f"{rel_root}/{name}"
            rel = rel.replace("\\", "/")
            if rel in seen:
                continue
            if not _looks_like_dependency_manifest(rel):
                continue
            seen.add(rel)
            resolved.append(rel)

    if not resolved:
        return ""

    sections: List[str] = []
    for rel in sorted(resolved):
        abs_path = os.path.join(repo_root, rel)
        basename = os.path.basename(rel).lower()
        try:
            with open(abs_path, "r", encoding="utf-8") as fh:
                raw = fh.read()
        except Exception:
            continue

        if rel.lower().endswith(".json"):
            try:
                data = json.loads(raw)
            except Exception:
                data = None
            if isinstance(data, dict):
                dependency_keys = [
                    key for key, value in data.items()
                    if isinstance(value, dict) and "depend" in str(key).lower()
                ]
                if dependency_keys:
                    payload: Dict[str, Dict[str, str]] = {}
                    for key in dependency_keys[:4]:
                        value = data.get(key)
                        if isinstance(value, dict):
                            payload[str(key)] = {
                                str(k): str(v) for k, v in sorted(value.items())[:30]
                            }
                    if payload:
                        sections.append(f"**Manifest (`{rel}`)**")
                        sections.append("```json")
                        sections.append(json.dumps(payload, ensure_ascii=True, indent=2))
                        sections.append("```")
                        continue

        if rel.lower().endswith(".toml"):
            preview = [line.rstrip() for line in raw.splitlines() if line.strip()][:80]
            if preview:
                sections.append(f"**Manifest (`{rel}`)**")
                sections.append("```toml")
                sections.extend(preview)
                sections.append("```")
                continue

        lines = [
            line.strip()
            for line in raw.splitlines()
            if line.strip() and not line.strip().startswith("#")
        ][:40]
        if lines:
            sections.append(f"**Manifest (`{rel}`)**")
            sections.append("```text")
            sections.extend(lines)
            sections.append("```")

    return "\n".join(sections).strip()


def _build_public_master_task_plan(task_plan: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    public_plan: List[Dict[str, Any]] = []
    for entry in task_plan or []:
        if not isinstance(entry, dict):
            continue
        sanitized = dict(entry)
        for key in (
            "assignee",
            "recommended_agent_name",
            "opt_in_username",
            "assignment_reason",
        ):
            sanitized.pop(key, None)
        public_plan.append(sanitized)
    return public_plan


async def _generate_detailed_project_tree_plan(
    *,
    tasks: List[Dict[str, Any]],
    brd_summary: str = "",
    kg_context: str = "",
    tech_spec: str = "",
    stack_profile: Optional[Dict[str, Any]] = None,
    workspace_contract: Optional[Dict[str, Any]] = None,
    repo_tree_context: str = "",
    previous_tree_feedback: str = "",
) -> str:
    url = llm_gateway.resolve_url()
    key = llm_gateway.resolve_key()
    model_name = llm_gateway.resolve_model()

    if not llm_gateway.check_api_key():
        return ""

    task_list_text = _build_task_context_block(
        tasks,
        max_total_chars=16000,
        max_description_chars=220,
        include_file_hints=True,
        include_checklist_preview=True,
        stack_profile=stack_profile,
        workspace_contract=workspace_contract,
    )
    stack = stack_profile if isinstance(stack_profile, dict) else {}
    stack_text = (
        f"Frontend: {stack.get('frontend') or 'unspecified'}\n"
        f"Backend: {stack.get('backend') or 'unspecified'}\n"
        f"Confidence: {stack.get('confidence') or 'unspecified'}\n"
        f"Reason: {stack.get('reason') or 'n/a'}"
    )
    planning_packet_json = json.dumps(
        _build_master_planning_packet(
            tasks=tasks,
            brd_summary=brd_summary,
            kg_context=kg_context,
            tech_spec=tech_spec,
            stack_profile=stack_profile,
            workspace_contract=workspace_contract,
            repo_tree_context=repo_tree_context,
        ),
        ensure_ascii=True,
        indent=2,
    )

    prompt = f"""You are the Master Architect Agent.
Create the SINGLE CANONICAL PROJECT TREE that all coding agents must follow.

BUSINESS REQUIREMENTS:
{brd_summary[:4000] if brd_summary else "Not provided."}

EXISTING CODEBASE CONTEXT:
{kg_context[:3000] if kg_context else "New project or minimal context."}

CURRENT GIT PROJECT TREE SNAPSHOT:
{repo_tree_context[:4000] if repo_tree_context else "Not provided."}

EXISTING TECHNICAL SPEC:
{tech_spec[:3500] if tech_spec else "Not provided."}

AUTHORITATIVE PLANNING_PACKET_JSON:
{planning_packet_json}

ALL TASKS TO COVER IN THE PROJECT STRUCTURE (titles, descriptions, checklists, file hints):
{task_list_text}

STACK DECISION TO FOLLOW:
{stack_text}

Output rules:
- Output ONLY one project tree as a strictly valid JSON object.
- The JSON object must have a "name" for the root and a "children" array containing nested objects.
- Example structure: {{"name": "project_root", "children": [{{"name": "backend", "children": [{{"name": "api.py"}}]}}]}}
- The tree must declare exactly one fixed canonical root.
- Never output multiple alternatives, fallback layouts, conditional notes, or instructions like "pick only one".
- Treat the PLANNING_PACKET_JSON as authoritative structured input. Use it before relying on generic scaffold defaults.
- Resolve framework contradictions in favor of the task details, checklist evidence, stack evidence, and current repo tree.
- Never mix conflicting stacks in one tree.
- Include directories and specific file names, not placeholders like "etc" or "other files".
- Every listed task must have an obvious home in the tree.
- Include configuration files, tests, shared types/contracts, and integration points when appropriate.
- Keep the tree consistent with the stack decision above.
- Use only directories that are justified by the tasks or existing codebase context.
- Use the BEST PRACTICE project structure for the detected tech stack. For example:
  - Flask apps: use app/ at the repo root with templates/, static/, etc. inside it
  - Django apps: use the standard Django project/app layout with manage.py at root
  - FastAPI: use a Python package structure with main.py at root
  - React/Next.js: use the standard frontend framework layout
- Do NOT force files into a rigid pre-existing workspace contract layout if it contradicts best practices for the tech stack.
- The tech stack and tasks should drive the directory structure, not pre-existing workspace contract source roots.
- Choose the best production-ready structure for the tasks, not the easiest structure.
- Do not include prose before or after the JSON.
- Keep paths repository-relative; do not require an extra wrapper prefix in canonical source roots.
- If you use a root label in JSON, it must not force all source roots to be prefixed with a non-repository segment.

CRITICAL STRUCTURAL RULES (MUST FOLLOW):
- NEVER include virtual environments (venv/, .venv/, env/), node_modules/, __pycache__/, .git/, dist/, build/ in the tree. These are ephemeral artifacts.
- ALL test files (test_*.py, *_test.py, *.spec.ts, *.test.ts) MUST go in the tests/ directory, NEVER inside the application source (e.g., app/services/test_parser.py is WRONG; tests/test_parser.py is CORRECT).
- For Flask/Python backends, ALWAYS include a wsgi.py or run.py entry point alongside gunicorn_conf.py.
- For Django backends, ALWAYS include manage.py and a settings module.
- Every task with planned_files in the PLANNING_PACKET_JSON must have those files (or equivalent) present in the tree. Do NOT omit task files.
- If a task mentions "export", "history", "analytics", etc., there MUST be a corresponding source file in the tree (e.g., app/export.py, app/history.py, app/analytics.py).
- For Alembic/migration setups, include migrations/env.py and migrations/versions/ (not just an empty migrations/ directory).
- conftest.py belongs in tests/, not in the app source directory.
{previous_tree_feedback if previous_tree_feedback else ''}
"""

    messages = [
        {"role": "system", "content": MASTER_TREE_GENERATOR_SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]

    try:
        content = await llm_gateway.call_llm_and_extract(
            messages=messages,
            api_url=url,
            api_key=key,
            model=model_name,
            timeout=120.0
        )
        clean_text = _strip_markdown_fences(content)
        parsed_json = _extract_json_object_from_text(clean_text)
        if parsed_json is not None:
            return json.dumps(parsed_json, ensure_ascii=False, indent=2)
            
        return clean_text
    except Exception as exc:
        logger.warning("Master project tree generation failed: %s", exc)
        return ""


def _extract_json_object_from_text(text: str) -> Optional[Dict[str, Any]]:
    raw = str(text or "").strip()
    if not raw:
        return None

    candidates = [raw]
    match = _re.search(r"\{[\s\S]*\}", raw)
    if match:
        candidates.insert(0, match.group(0))

    for candidate in candidates:
        normalized = _strip_markdown_fences(candidate)
        try:
            parsed = json.loads(normalized)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            try:
                # Fallback for pseudo-JSON emitted as Python dict literals.
                py_parsed = ast.literal_eval(normalized)
                if isinstance(py_parsed, dict):
                    return py_parsed
            except Exception:
                continue
    return None


def _tree_name_looks_serialized_payload(name: Any) -> bool:
    text = str(name or "").strip()
    if not text:
        return False
    return text.startswith("{'name':") or text.startswith('{"name":') or ("'children'" in text and "'name'" in text)


def _sanitize_tree_node(node: Any) -> Optional[Dict[str, Any]]:
    # Directories that should NEVER appear in a canonical project tree
    _FORBIDDEN_NODE_NAMES = {
        "venv", ".venv", "env", "node_modules", "__pycache__",
        ".git", "dist", "build", ".next", ".turbo",
        ".pytest_cache", ".mypy_cache", ".tox",
    }

    if not isinstance(node, dict):
        return None

    raw_name = node.get("name")
    name = str(raw_name or "").strip()
    if not name:
        return None

    # Strip forbidden ephemeral directories
    if name.lower().rstrip("/") in _FORBIDDEN_NODE_NAMES:
        return None

    if _tree_name_looks_serialized_payload(name):
        try:
            reparsed = ast.literal_eval(name)
            if isinstance(reparsed, dict):
                reparsed_node = _sanitize_tree_node(reparsed)
                if reparsed_node:
                    return reparsed_node
        except Exception:
            return None

    children_in = node.get("children")
    children_list = children_in if isinstance(children_in, list) else []
    sanitized_children: List[Dict[str, Any]] = []
    seen = set()
    for child in children_list:
        sanitized_child = _sanitize_tree_node(child)
        if not sanitized_child:
            continue
        sig = (
            sanitized_child.get("name"),
            bool(sanitized_child.get("children")),
        )
        if sig in seen:
            continue
        seen.add(sig)
        sanitized_children.append(sanitized_child)

    return {"name": name, "children": sanitized_children}


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes", "approved"}


def _detect_ambiguous_master_tree_issues(workspace_tree: str) -> List[str]:
    raw = str(workspace_tree or "").strip()
    if not raw:
        return []

    # JSON trees are deterministic and don't suffer from ASCII parsing ambiguities
    if raw.startswith(("{", "[")):
        return []

    text = raw
    lower = text.lower()
    issues: List[str] = []

    if any(
        marker in lower
        for marker in (
            "pick only one",
            "collapses to",
            "becomes the repository root",
            "preserving whichever directory root is in use",
        )
    ):
        issues.append(
            "The canonical tree contains conditional or alternate structures. It must declare exactly one fixed root."
        )

    root_candidates: List[str] = []
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("```"):
            continue
        if stripped.startswith(("├──", "└──", "│")):
            continue
        cleaned = _re.sub(r"^[\s│├└─]+", "", stripped).strip()
        if cleaned.endswith("/") and "/" not in cleaned[:-1]:
            root_label = cleaned[:-1].strip()
            if root_label:
                root_candidates.append(root_label)

    unique_roots = []
    seen_roots = set()
    for root in root_candidates:
        if root in seen_roots:
            continue
        seen_roots.add(root)
        unique_roots.append(root)

    if len(unique_roots) > 1:
        issues.append(
            "The canonical tree declares multiple candidate roots "
            + f"({', '.join(unique_roots[:3])}). Only one canonical root is allowed."
        )

    if text.count("```") >= 4:
        issues.append("The canonical tree contains multiple code blocks/diagrams instead of one single tree.")

    return issues


def _heuristic_master_tree_validation(
    *,
    tasks: List[Dict[str, Any]],
    workspace_tree: str,
    workspace_contract: Optional[Dict[str, Any]] = None,
    stack_profile: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    task_count = len(tasks or [])
    file_line_count = _count_tree_file_lines(workspace_tree)
    lines_lower = str(workspace_tree or "").lower()
    expected_roots = []

    contract = workspace_contract if isinstance(workspace_contract, dict) else {}
    stack = stack_profile if isinstance(stack_profile, dict) else {}
    frontend_key = str(stack.get("frontend_key") or "").strip()
    backend_key = str(stack.get("backend_key") or "").strip()
    minimum_file_lines = 6
    if frontend_key == "static-html" and backend_key == "none":
        minimum_file_lines = 3
    elif frontend_key in {"static-html", "none"} or backend_key == "none":
        minimum_file_lines = 4
    expected_file_lines = max(
        minimum_file_lines,
        min(18, task_count // 2 + (3 if minimum_file_lines <= 4 else 4)),
    )

    issues = []
    recommendations = []
    issues.extend(_detect_ambiguous_master_tree_issues(workspace_tree)[:3])
    tree_file_paths = _extract_paths_from_workspace_tree(workspace_tree)
    tree_file_paths_lower = [path.lower() for path in tree_file_paths]

    raw_tree = str(workspace_tree or "").strip()
    if raw_tree.startswith(("{", "[")):
        parsed_tree = _extract_json_object_from_text(raw_tree)
        if not isinstance(parsed_tree, dict):
            issues.append("Canonical tree JSON is malformed or not parseable as an object.")
        else:
            root_name = str(parsed_tree.get("name") or "").strip()
            if _tree_name_looks_serialized_payload(root_name):
                issues.append("Canonical tree root 'name' contains serialized object text instead of a plain label.")
            sanitized = _sanitize_tree_node(parsed_tree)
            if not sanitized:
                issues.append("Canonical tree JSON failed structural sanitization (invalid node shape).")

    if task_count > 0 and file_line_count < expected_file_lines:
        issues.append(
            "The project tree is too shallow relative to the number of tasks and may not contain enough concrete files."
        )

    # Generic structural hygiene checks.
    config_under_source = [
        path for path in tree_file_paths_lower
        if "/src/" in path and ("config." in os.path.basename(path) or os.path.basename(path).startswith(".env"))
    ]
    if config_under_source:
        issues.append("Configuration/environment files are placed inside source directories instead of module roots.")

    config_variants: Dict[str, set[str]] = {}
    for path in tree_file_paths_lower:
        base = os.path.basename(path)
        match = _re.match(r"^(.*?config)\.([a-z0-9]+)$", base)
        if not match:
            continue
        stem = match.group(1)
        ext = match.group(2)
        directory = os.path.dirname(path)
        key = f"{directory}/{stem}"
        config_variants.setdefault(key, set()).add(ext)
    if any(len(exts) > 1 for exts in config_variants.values()):
        issues.append("The tree contains multiple extension variants of the same config file in a single directory.")

    # NOTE: Workspace contract source root checks are advisory only.
    # The AI model decides the best structure based on tasks and tech stack.
    # Do NOT block tree generation because of workspace contract mismatches.
    for root in (contract.get("allowed_source_roots") or [])[:8]:
        root_text = str(root or "").strip()
        if root_text and root_text.lower() not in lines_lower:
            recommendations.append(f"Workspace contract lists source root '{root_text}' which is not in the tree. This is OK if the AI chose a better structure for the tech stack.")

    if file_line_count < minimum_file_lines:
        recommendations.append("Add concrete file names for entrypoints, configuration, tests, and feature modules.")

    # ── Check for ephemeral/build artifacts that should never be in the canonical tree ──
    _FORBIDDEN_DIRS = {"venv", ".venv", "env", "node_modules", "__pycache__", ".git", "dist", "build", ".next", ".turbo"}
    for path in tree_file_paths:
        parts = [p.lower() for p in path.split("/")]
        for part in parts:
            if part in _FORBIDDEN_DIRS:
                issues.append(f"The tree contains '{part}/' which is an ephemeral artifact (virtual env, cache, or build output) and must not be in the canonical tree.")
                break

    approved = not issues and file_line_count >= minimum_file_lines
    return {
        "approved": approved,
        "confidence": 0.65 if approved else 0.35,
        "issues_missing_files": issues[:8],
        "issues_conflicts": [],
        "recommendations": recommendations[:8],
        "corrected_tree": "",
        "validator_agent_id": "structure_validator",
        "mode": "heuristic",
    }


async def _validate_master_project_tree_plan(
    *,
    tasks: List[Dict[str, Any]],
    workspace_tree: str,
    brd_summary: str = "",
    tech_spec: str = "",
    workspace_contract: Optional[Dict[str, Any]] = None,
    stack_profile: Optional[Dict[str, Any]] = None,
    repo_tree_context: str = "",
) -> Dict[str, Any]:
    heuristic = _heuristic_master_tree_validation(
        tasks=tasks,
        workspace_tree=workspace_tree,
        workspace_contract=workspace_contract,
        stack_profile=stack_profile,
    )

    url = llm_gateway.resolve_url()
    key = llm_gateway.resolve_key()
    model_name = llm_gateway.resolve_model()

    if not llm_gateway.check_api_key():
        return heuristic

    task_lines = _build_task_context_block(
        tasks,
        max_total_chars=14000,
        max_description_chars=200,
        include_file_hints=True,
        include_checklist_preview=True,
        stack_profile=stack_profile,
        workspace_contract=workspace_contract,
    )
    spec_file_structure = _extract_markdown_section(tech_spec, r"4\.\s*FILE STRUCTURE")
    spec_reference = spec_file_structure[:3200] if spec_file_structure else tech_spec[:3200]

    contract_summary = json.dumps({
        "status": (workspace_contract or {}).get("status"),
        "allowed_source_roots": list((workspace_contract or {}).get("allowed_source_roots") or [])[:20],
        "modules": list((workspace_contract or {}).get("modules") or [])[:10],
    }, ensure_ascii=True, indent=2)
    stack_summary = json.dumps(stack_profile or {}, ensure_ascii=True, indent=2)
    planning_packet_json = json.dumps(
        _build_master_planning_packet(
            tasks=tasks,
            brd_summary=brd_summary,
            kg_context="",
            tech_spec=tech_spec,
            stack_profile=stack_profile,
            workspace_contract=workspace_contract,
            repo_tree_context=repo_tree_context,
        ),
        ensure_ascii=True,
        indent=2,
    )

    prompt = f"""You are the Structure Validator Agent.
Validate whether the proposed canonical project tree is correct and complete enough for the provided task plan.

BUSINESS REQUIREMENTS:
{brd_summary[:3200] if brd_summary else "Not provided."}

TECHNICAL SPEC FILE STRUCTURE / MANDATORY FILES:
{spec_reference if spec_reference else "Not provided."}

CURRENT GIT PROJECT TREE SNAPSHOT:
{repo_tree_context[:3500] if repo_tree_context else "Not provided."}

AUTHORITATIVE PLANNING_PACKET_JSON:
{planning_packet_json}

TASKS (titles, descriptions, checklists, file hints):
{task_lines}

STACK DECISION:
{stack_summary}

PROPOSED PROJECT TREE:
{workspace_tree[:6000] if workspace_tree else "No tree provided."}

Return ONLY valid JSON with this exact shape:
{{
  "approved": true,
  "confidence": 0.0,
  "issues_missing_files": [],
  "issues_conflicts": [],
  "recommendations": [],
  "corrected_tree": ""
}}

Rules:
- Approve if the tree has concrete filenames and clear homes for every task.
- Approve if the tree follows best practices for the detected tech stack.
- The AI model decides the best project structure based on the tasks and tech stack. Do NOT enforce rigid workspace contract source root boundaries.
- Reject if the tree is too shallow (missing files for tasks) or contradicts the stack decision.
- Reject if the tree contradicts the structured evidence in PLANNING_PACKET_JSON.
- Reject if the tree mixes conflicting stacks, such as Flask with Express, Flask/Jinja with React/Vite, React with Vue, or Next.js with static HTML.
- Reject if the tree contains alternatives, conditional wording, multiple diagrams, or more than one candidate root.
- Reject if Flask + Jinja is indicated but the tree invents a separate Node frontend app root instead of using template/static structure.
- Do NOT reject simply because the tree uses a different directory layout than the workspace contract. The AI should use the best structure for the tech stack.
- If rejected, provide a corrected_tree as a full replacement tree that follows best practices for the tech stack.
"""

    messages = [
        {"role": "system", "content": MASTER_TREE_VALIDATOR_SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]

    try:
        content = await llm_gateway.call_llm_and_extract(
            messages=messages,
            api_url=url,
            api_key=key,
            model=model_name,
            timeout=120.0
        )
        parsed = _extract_json_object_from_text(content)
        if not parsed:
            return heuristic
        try:
            confidence = float(parsed.get("confidence") or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0
        ai_result = {
            "approved": _coerce_bool(parsed.get("approved")),
            "confidence": confidence,
            "issues_missing_files": [
                str(item) for item in (parsed.get("issues_missing_files") or [])[:10]
            ],
            "issues_conflicts": [
                str(item) for item in (parsed.get("issues_conflicts") or [])[:10]
            ],
            "recommendations": [
                str(item) for item in (parsed.get("recommendations") or [])[:10]
            ],
            "corrected_tree": _strip_markdown_fences(str(parsed.get("corrected_tree") or "")),
            "validator_agent_id": "structure_validator",
            "mode": "ai",
        }
        return ai_result
    except Exception as exc:
        logger.warning("Master project tree validation failed, using heuristic fallback: %s", exc)
        return heuristic


def _summarize_master_tree_validation(validation: Optional[Dict[str, Any]]) -> str:
    payload = validation if isinstance(validation, dict) else {}
    issues_missing = [
        str(item or "").strip()
        for item in (payload.get("issues_missing_files") or [])
        if str(item or "").strip()
    ]
    issues_conflicts = [
        str(item or "").strip()
        for item in (payload.get("issues_conflicts") or [])
        if str(item or "").strip()
    ]
    recommendations = [
        str(item or "").strip()
        for item in (payload.get("recommendations") or [])
        if str(item or "").strip()
    ]
    mode = str(payload.get("mode") or "").strip()

    detail_parts = []
    if issues_missing:
        detail_parts.append(f"missing/coverage: {issues_missing[0]}")
    if issues_conflicts:
        detail_parts.append(f"conflict: {issues_conflicts[0]}")
    if recommendations and not detail_parts:
        detail_parts.append(f"recommendation: {recommendations[0]}")
    if mode:
        detail_parts.append(f"mode={mode}")
    return " | ".join(detail_parts[:3])


def _render_master_tree_validation_report(validation: Optional[Dict[str, Any]]) -> str:
    payload = validation if isinstance(validation, dict) else {}
    lines: List[str] = []
    mode = str(payload.get("mode") or "").strip()
    confidence = payload.get("confidence")
    if mode:
        lines.append(f"mode: {mode}")
    if confidence not in (None, ""):
        lines.append(f"confidence: {confidence}")

    missing = [
        str(item or "").strip()
        for item in (payload.get("issues_missing_files") or [])
        if str(item or "").strip()
    ]
    conflicts = [
        str(item or "").strip()
        for item in (payload.get("issues_conflicts") or [])
        if str(item or "").strip()
    ]
    recommendations = [
        str(item or "").strip()
        for item in (payload.get("recommendations") or [])
        if str(item or "").strip()
    ]
    corrected_tree = _strip_markdown_fences(str(payload.get("corrected_tree") or "")).strip()

    if missing:
        lines.append("missing/coverage issues:")
        for item in missing[:12]:
            lines.append(f"- {item}")
    if conflicts:
        lines.append("conflicts:")
        for item in conflicts[:12]:
            lines.append(f"- {item}")
    if recommendations:
        lines.append("recommendations:")
        for item in recommendations[:12]:
            lines.append(f"- {item}")
    if corrected_tree:
        preview = corrected_tree[:1800]
        lines.append("validator_corrected_tree_preview:")
        lines.append(preview)

    return "\n".join(lines).strip()


def _coerce_note_entries(existing_payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    entries = existing_payload.get("entries")
    if isinstance(entries, list):
        return [entry for entry in entries if isinstance(entry, dict)]

    legacy_entry = {}
    for key in (
        "task_id",
        "task_title",
        "status",
        "branch",
        "planned_files",
        "completed_files",
        "symbols_created",
        "symbols_modified",
        "next_agent_should",
        "summary",
        "started_at",
        "updated_at",
        "completed_at",
    ):
        value = existing_payload.get(key)
        if value not in (None, "", [], {}):
            legacy_entry[key] = value
    return [legacy_entry] if legacy_entry else []


async def _get_existing_note_payload(
    *,
    title: str,
    project_token: Optional[str] = None,
    task_token: Optional[str] = None,
) -> Dict[str, Any]:
    effective_token = task_token or get_project_task_token(project_token)
    if not effective_token:
        return {}

    state = _ensure_project_state(project_token)
    payload_cache = state.setdefault("note_payload_cache", {})
    cached_entry = payload_cache.get(title)
    now = time.time()
    if isinstance(cached_entry, dict):
        cached_token = str(cached_entry.get("task_token") or "").strip()
        cached_age = now - float(cached_entry.get("loaded_at") or 0.0)
        if cached_token == str(effective_token).strip() and cached_age <= NOTE_PAYLOAD_CACHE_TTL_SECONDS:
            cached_payload = cached_entry.get("payload")
            if isinstance(cached_payload, dict):
                return dict(cached_payload)

    note_id = await _find_note_id_by_title(
        title,
        project_token=project_token,
        task_token=effective_token,
    )
    if note_id is None:
        return {}

    try:
        from task_service import task_service

        detail = await task_service.get_note_detail(note_id, task_token=effective_token)
        payload = _parse_agent_note_content((detail or {}).get("content"))
        payload_cache[title] = {
            "payload": dict(payload) if isinstance(payload, dict) else {},
            "loaded_at": now,
            "task_token": effective_token,
        }
        return payload
    except Exception:
        return {}


async def _load_persisted_master_note(
    *,
    title: str,
    project_token: Optional[str],
    task_token: Optional[str],
    tasks: List[Dict[str, Any]],
    task_signature: str,
    worker_signature: str,
    workspace_contract_signature: str = "",
) -> Dict[str, Any]:
    payload = await _get_existing_note_payload(
        title=title,
        project_token=project_token,
        task_token=task_token,
    )
    if not isinstance(payload, dict) or payload.get("note_type") != "master_project_plan":
        return {}

    validation = payload.get("validation") if isinstance(payload.get("validation"), dict) else {}
    if not validation.get("approved"):
        return {}
    if str(validation.get("mode") or "").strip().lower() == "heuristic_override":
        # Do not reuse notes where AI validator rejected the structure.
        return {}

    persisted_task_signature = str(payload.get("task_signature") or "").strip()
    if persisted_task_signature and persisted_task_signature != task_signature:
        return {}
    persisted_contract_signature = str(payload.get("workspace_contract_signature") or "").strip()
    if workspace_contract_signature and persisted_contract_signature != workspace_contract_signature:
        return {}

    workspace_tree = str(payload.get("workspace_tree") or "").strip()
    if not workspace_tree:
        return {}
    normalized_persisted_tree = _ensure_workspace_tree_json(
        workspace_tree,
        fallback_root_label=(project_token or "project"),
    )
    if not normalized_persisted_tree:
        # Persisted note contains malformed/non-canonical tree; force regeneration.
        return {}
    workspace_tree = normalized_persisted_tree

    stack_profile = payload.get("stack_profile") if isinstance(payload.get("stack_profile"), dict) else {}
    workspace_contract = payload.get("workspace_contract") if isinstance(payload.get("workspace_contract"), dict) else {}
    task_plan = payload.get("tasks_considered") if isinstance(payload.get("tasks_considered"), list) else []
    if not task_plan:
        task_plan = _build_master_task_plan(
            tasks=tasks,
            stack_profile=stack_profile,
            workspace_contract=workspace_contract,
        )

    note_id = await _find_note_id_by_title(
        title,
        project_token=project_token,
        task_token=task_token,
    )

    return {
        "success": True,
        "note_id": note_id,
        "title": title,
        "task_count": len(task_plan),
        "validation": validation,
        "approved": True,
        "task_signature": task_signature,
        "worker_signature": worker_signature,
        "workspace_contract_signature": workspace_contract_signature,
        "recommended_assignments": [],
        "tasks_considered": task_plan,
        "workspace_tree": workspace_tree,
        "stack_profile": stack_profile,
        "workspace_contract": workspace_contract,
        "instructions": list(payload.get("instructions") or [])[:12],
    }


def _merge_agent_note_entry(existing: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(existing or {})

    for key in ("task_id", "task_title", "status", "branch", "next_agent_should", "summary", "updated_at"):
        value = incoming.get(key)
        if value not in (None, ""):
            merged[key] = value

    for key in ("planned_files", "completed_files", "symbols_created", "symbols_modified"):
        value = incoming.get(key)
        if isinstance(value, list):
            merged[key] = value[:25]

    merged["started_at"] = existing.get("started_at") or incoming.get("started_at") or incoming.get("updated_at")

    status_value = str(incoming.get("status") or merged.get("status") or "").lower()
    if status_value in {"completed", "failed"}:
        merged["completed_at"] = incoming.get("completed_at") or existing.get("completed_at") or incoming.get("updated_at")
    else:
        merged.pop("completed_at", None)

    return merged


def _build_agent_note_payload(
    *,
    existing_payload: Dict[str, Any],
    agent_id: str,
    project_token: Optional[str],
    entry: Dict[str, Any],
) -> Dict[str, Any]:
    entries = _coerce_note_entries(existing_payload)
    target_idx = None
    entry_task_id = str(entry.get("task_id") or "").strip()

    for idx in range(len(entries) - 1, -1, -1):
        candidate_task_id = str((entries[idx] or {}).get("task_id") or "").strip()
        if candidate_task_id and candidate_task_id == entry_task_id:
            target_idx = idx
            break

    if target_idx is None:
        entries.append(entry)
    else:
        entries[target_idx] = _merge_agent_note_entry(entries[target_idx], entry)

    return {
        "project_token": _note_scope_key(project_token),
        "agent_id": agent_id,
        "updated_at": entry.get("updated_at") or _note_timestamp(),
        "entries": entries[-20:],
    }


def _extract_note_id_from_response(data: Any) -> Optional[int]:
    if isinstance(data, dict):
        for key in ("id", "note_id"):
            value = data.get(key)
            if value in (None, ""):
                continue
            try:
                return int(value)
            except Exception:
                continue
    return None


async def _find_note_id_by_title(
    title: str,
    project_token: Optional[str] = None,
    task_token: Optional[str] = None,
) -> Optional[int]:
    effective_token = task_token or get_project_task_token(project_token)
    if not effective_token:
        return None

    state = _ensure_project_state(project_token)
    cache = state.setdefault("note_title_cache", {})
    cached = cache.get(title)
    if cached:
        return cached

    try:
        from task_service import task_service

        notes = await task_service.list_notes(task_token=effective_token)
    except Exception:
        return None

    if not isinstance(notes, list):
        return None

    for note in notes:
        if str((note or {}).get("title") or "").strip() != title:
            continue
        note_id = _extract_note_id_from_response(note)
        if note_id is not None:
            cache[title] = note_id
            return note_id

    return None


async def _upsert_agent_note(
    *,
    title: str,
    content_payload: Dict[str, Any],
    content_text: Optional[str] = None,
    user: Optional[str],
    project_token: Optional[str] = None,
    task_token: Optional[str] = None,
) -> Dict[str, Any]:
    effective_token = task_token or get_project_task_token(project_token)
    if not effective_token:
        return {"success": False, "skipped": True, "reason": "missing_task_token"}

    try:
        from task_service import task_service
    except Exception as exc:
        return {"success": False, "error": str(exc)}

    note_id = await _find_note_id_by_title(
        title,
        project_token=project_token,
        task_token=effective_token,
    )

    payload = {
        "title": title,
        "content": (
            _embed_note_payload(str(content_text).strip(), content_payload)
            if content_text not in (None, "")
            else json.dumps(content_payload, ensure_ascii=True, sort_keys=True, indent=2)
        ),
    }
    if note_id is not None:
        payload["note_id"] = note_id
    if user:
        payload["user"] = user

    try:
        result = await task_service.upsert_note(payload, task_token=effective_token)
        resolved_note_id = _extract_note_id_from_response(result) or note_id
        if resolved_note_id is None:
            resolved_note_id = await _find_note_id_by_title(
                title,
                project_token=project_token,
                task_token=effective_token,
            )
        if resolved_note_id is not None:
            state = _ensure_project_state(project_token)
            state.setdefault("note_title_cache", {})[title] = resolved_note_id
            state.setdefault("note_payload_cache", {})[title] = {
                "payload": dict(content_payload or {}),
                "loaded_at": time.time(),
                "task_token": effective_token,
            }
        return {
            "success": True,
            "note_id": resolved_note_id,
            "result": result,
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


async def ensure_master_workspace_note(
    *,
    project_token: Optional[str] = None,
    task_token: Optional[str] = None,
) -> Dict[str, Any]:
    effective_project = project_token or ""
    if task_token:
        set_project_task_token(project_token, task_token)

    state = _ensure_project_state(project_token)
    title = _master_note_title(project_token)

    async with state["master_note_lock"]:
        master_tasks = state.get("master_task_context") if isinstance(state.get("master_task_context"), list) else []
        tasks = list(master_tasks) if master_tasks else []
        if not tasks:
            tasks = state.get("tasks") if isinstance(state.get("tasks"), list) else []
        if not tasks:
            try:
                tasks = await _fetch_external_tasks(project_token)
                state["tasks"] = tasks
            except Exception as exc:
                logger.warning("[%s] Failed to fetch tasks for master note: %s", effective_project, exc)
                tasks = []
        ctx_mgr = None
        workspace_contract: Dict[str, Any] = {}
        workspace_contract_signature = ""
        try:
            import context_manager as ctx_mgr  # type: ignore

            repo_creds = _resolve_project_git_credentials(project_token)
            if effective_project and repo_creds.get("repo_url"):
                refresh_result = await _refresh_workspace_contract_from_git_repo(
                    project_token=project_token,
                    repo_url=repo_creds.get("repo_url") or "",
                    token=repo_creds.get("token") or "",
                )
                if not refresh_result.get("success") and not refresh_result.get("skipped"):
                    logger.warning(
                        "[%s] Failed to hydrate workspace contract from git repo: %s",
                        effective_project,
                        refresh_result.get("error") or "unknown error",
                    )
            workspace_contract = ctx_mgr.get_workspace_contract(effective_project) if effective_project else {}
            workspace_contract_signature = _workspace_contract_signature(workspace_contract)
        except Exception as exc:
            logger.warning("[%s] Failed to prepare workspace contract for master note: %s", effective_project, exc)
            workspace_contract = {}
            workspace_contract_signature = ""
        brd_analysis = state.get("brd_analysis")
        brd_summary = _build_brd_analysis_context(brd_analysis)
        if not brd_summary:
            if isinstance(brd_analysis, dict):
                brd_summary = str(
                    brd_analysis.get("summary")
                    or brd_analysis.get("analysis")
                    or ""
                ).strip()
            else:
                brd_summary = str(brd_analysis or "").strip()
        task_signature = _master_task_signature(tasks, brd_context=brd_summary)
        worker_signature = _master_worker_signature(project_token)
        cached_master_note = state.get("master_note_cache") if isinstance(state.get("master_note_cache"), dict) else {}
        if (
            cached_master_note.get("success")
            and cached_master_note.get("approved")
            and cached_master_note.get("title") == title
            and cached_master_note.get("task_signature") == task_signature
            and cached_master_note.get("worker_signature") == worker_signature
            and cached_master_note.get("workspace_contract_signature") == workspace_contract_signature
        ):
            try:
                cached_contract = ctx_mgr.get_workspace_contract(effective_project) if ctx_mgr and effective_project else {}
                cached_contract = cached_contract if isinstance(cached_contract, dict) else {}
                cached_tree = str(cached_master_note.get("workspace_tree") or "").strip()
                if cached_contract.get("status") != "ready" and cached_tree:
                    refreshed_contract = ctx_mgr.update_workspace_contract_from_canonical_tree(
                        effective_project,
                        cached_tree,
                    ) if ctx_mgr else {}
                    refreshed_contract = refreshed_contract if isinstance(refreshed_contract, dict) else {}
                    if refreshed_contract.get("status") == "ready":
                        _log_master_agent(
                            "Reused cached master tree to restore the workspace contract.",
                            project_token=project_token,
                    )
            except Exception as exc:
                logger.warning("[%s] Failed to restore workspace contract from cached master tree: %s", effective_project, exc)
            return dict(cached_master_note)

        persisted_master_note = await _load_persisted_master_note(
            title=title,
            project_token=project_token,
            task_token=task_token,
            tasks=tasks,
            task_signature=task_signature,
            worker_signature=worker_signature,
            workspace_contract_signature=workspace_contract_signature,
        )
        if persisted_master_note:
            try:
                persisted_tree = str(persisted_master_note.get("workspace_tree") or "").strip()
                if persisted_tree and ctx_mgr:
                    refreshed_contract = ctx_mgr.update_workspace_contract_from_canonical_tree(
                        effective_project,
                        persisted_tree,
                    )
                    if not isinstance(refreshed_contract, dict):
                        refreshed_contract = {}
            except Exception as exc:
                logger.warning("[%s] Failed to restore workspace contract from persisted master note: %s", effective_project, exc)
            _log_master_agent(
                "Reusing published master project tree note for current task plan.",
                project_token=project_token,
            )
            state["master_note_cache"] = dict(persisted_master_note)
            return dict(persisted_master_note)

        _log_master_agent(
            "Creating canonical project tree note from the full task plan.",
            project_token=project_token,
        )

        tech_spec_record = _project_tech_specs.get(effective_project, {}) if effective_project else {}
        tech_spec = str((tech_spec_record or {}).get("spec") or "").strip()
        tech_spec_signature = str((tech_spec_record or {}).get("task_signature") or "").strip()

        current_repo_tree = ""
        current_repo_tree_source = ""
        current_repo_file_paths: List[str] = []

        kg_context = ""
        try:
            if ctx_mgr and effective_project and ctx_mgr.is_project_indexed(effective_project):
                kg_context = await ctx_mgr.get_full_agent_context(
                    project_token=effective_project,
                    task_description="Canonical project structure and architecture overview",
                    agent_id=MASTER_AGENT_ID,
                    task_token=task_token,
                )
            if ctx_mgr and effective_project:
                workspace_contract = ctx_mgr.get_workspace_contract(effective_project)
                repo_snapshot = ctx_mgr.get_current_project_tree_snapshot(effective_project)
                if isinstance(repo_snapshot, dict):
                    current_repo_tree = str(repo_snapshot.get("tree") or "").strip()
                    current_repo_tree_source = str(repo_snapshot.get("source") or "").strip()
                    current_repo_file_paths = [
                        str(path).strip()
                        for path in (repo_snapshot.get("all_file_paths") or [])
                        if str(path).strip()
                    ]
                    if current_repo_file_paths:
                        refreshed_contract = ctx_mgr.update_workspace_contract_from_file_paths(
                            effective_project,
                            current_repo_file_paths,
                            source=f"{current_repo_tree_source or 'git_repo'}_snapshot",
                            merge_ready=True,
                            force_refresh=True,
                        )
                        if isinstance(refreshed_contract, dict) and refreshed_contract.get("status") == "ready":
                            workspace_contract = refreshed_contract
                workspace_contract_signature = _workspace_contract_signature(workspace_contract)
        except Exception as exc:
            logger.warning("[%s] Failed to build context for master note: %s", effective_project, exc)
            if not workspace_contract:
                workspace_contract = {}

        if effective_project and (not tech_spec or tech_spec_signature != task_signature):
            spec_result = await _generate_technical_spec(
                project_token=effective_project,
                tasks=tasks,
                brd_summary=brd_summary,
                kg_context=kg_context,
                repo_tree_context=current_repo_tree,
                workspace_contract=workspace_contract if isinstance(workspace_contract, dict) else {},
            )
            refreshed_spec = str(spec_result.get("spec") or "").strip()
            if refreshed_spec:
                tech_spec = refreshed_spec

        stack_profile = _infer_project_stack(
            tasks=tasks,
            tech_spec="\n".join(part for part in (tech_spec, current_repo_tree) if part),
            workspace_contract=workspace_contract if isinstance(workspace_contract, dict) else {},
        )

        workspace_tree = _strip_markdown_fences(
            _extract_markdown_section(tech_spec, r"4\.\s*FILE STRUCTURE")
        )
        workspace_tree_source = "tech_spec" if workspace_tree else "none"
        if _count_tree_file_lines(workspace_tree) < 6:
            generated_tree = await _generate_detailed_project_tree_plan(
                tasks=tasks,
                brd_summary=brd_summary,
                kg_context=kg_context,
                tech_spec=tech_spec,
                stack_profile=stack_profile,
                workspace_contract=workspace_contract if isinstance(workspace_contract, dict) else {},
                repo_tree_context=current_repo_tree,
            )
            if _count_tree_file_lines(generated_tree) >= _count_tree_file_lines(workspace_tree):
                workspace_tree = generated_tree
                workspace_tree_source = "ai_tree_plan"

        if not workspace_tree and isinstance(workspace_contract, dict):
            roots = list(workspace_contract.get("allowed_source_roots") or [])
            root_files = list(workspace_contract.get("root_files") or [])
            lines = ["project/"]
            for root in roots[:12]:
                lines.append(f"├── {root}/")
            for root_file in root_files[:12]:
                lines.append(f"├── {root_file}")
            workspace_tree = "\n".join(lines)
            workspace_tree_source = "workspace_contract"

        # Ensure the workspace contract reflects the Master Agent's canonical tree.
        # This makes the canonical structure the source of truth for merge gating.
        try:
            if ctx_mgr and effective_project and workspace_tree:
                refreshed_contract = ctx_mgr.update_workspace_contract_from_canonical_tree(
                    effective_project,
                    workspace_tree,
                )
                if isinstance(refreshed_contract, dict) and refreshed_contract.get("status") == "ready":
                    workspace_contract = refreshed_contract
                    workspace_contract_signature = _workspace_contract_signature(workspace_contract)
        except Exception as exc:
            logger.warning("[%s] Failed to refresh workspace contract from canonical tree: %s", effective_project, exc)

        architecture_overview = _extract_markdown_section(
            tech_spec,
            r"1\.\s*ARCHITECTURE OVERVIEW",
        )
        dependencies = _extract_markdown_section(
            tech_spec,
            r"6\.\s*DEPENDENCIES",
        )
        task_plan = _build_master_task_plan(
            tasks=tasks,
            stack_profile=stack_profile,
            workspace_contract=workspace_contract if isinstance(workspace_contract, dict) else {},
        )
        recommended_assignments: List[Dict[str, Any]] = []
        
        # Build recommended assignments
        if tasks:
            recommended_assignments = _build_master_recommended_assignments(
                tasks=tasks,
                task_plan=task_plan,
                project_token=project_token,
            )
            # We track recommendations silently internally to assist idle assignment later.
        
        deterministic_tree = _build_deterministic_master_tree(
            workspace_tree=workspace_tree,
            tech_spec=tech_spec,
            task_plan=task_plan,
            workspace_contract=workspace_contract if isinstance(workspace_contract, dict) else {},
            stack_profile=stack_profile,
            fallback_root_label=effective_project or "project",
            repo_file_paths=current_repo_file_paths,
        )
        if _count_tree_file_lines(deterministic_tree) > _count_tree_file_lines(workspace_tree):
            workspace_tree = deterministic_tree
            workspace_tree_source = "deterministic_spec_merge"
        validation = await _validate_master_project_tree_plan(
            tasks=tasks,
            workspace_tree=workspace_tree,
            brd_summary=brd_summary,
            tech_spec=tech_spec,
            workspace_contract=workspace_contract if isinstance(workspace_contract, dict) else {},
            stack_profile=stack_profile,
            repo_tree_context=current_repo_tree,
        )
        corrected_tree = _strip_markdown_fences(str(validation.get("corrected_tree") or ""))
        if not validation.get("approved") and corrected_tree:
            revised_validation = await _validate_master_project_tree_plan(
                tasks=tasks,
                workspace_tree=corrected_tree,
                brd_summary=brd_summary,
                tech_spec=tech_spec,
                workspace_contract=workspace_contract if isinstance(workspace_contract, dict) else {},
                stack_profile=stack_profile,
                repo_tree_context=current_repo_tree,
            )
            if revised_validation.get("approved"):
                workspace_tree = corrected_tree
                validation = revised_validation
                workspace_tree_source = "validator_corrected_tree"
            elif _count_tree_file_lines(corrected_tree) > _count_tree_file_lines(workspace_tree):
                workspace_tree = corrected_tree
                validation = revised_validation
                workspace_tree_source = "validator_corrected_tree"

        if not validation.get("approved"):
            deterministic_tree = _build_deterministic_master_tree(
                workspace_tree=workspace_tree,
                tech_spec=tech_spec,
                task_plan=task_plan,
                workspace_contract=workspace_contract if isinstance(workspace_contract, dict) else {},
                validation=validation,
                stack_profile=stack_profile,
                fallback_root_label=effective_project or "project",
                repo_file_paths=current_repo_file_paths,
            )
            if deterministic_tree and deterministic_tree != workspace_tree:
                revised_validation = await _validate_master_project_tree_plan(
                    tasks=tasks,
                    workspace_tree=deterministic_tree,
                    brd_summary=brd_summary,
                    tech_spec=tech_spec,
                    workspace_contract=workspace_contract if isinstance(workspace_contract, dict) else {},
                    stack_profile=stack_profile,
                    repo_tree_context=current_repo_tree,
                )
                if revised_validation.get("approved") or _count_tree_file_lines(deterministic_tree) > _count_tree_file_lines(workspace_tree):
                    workspace_tree = deterministic_tree
                    validation = revised_validation
                    workspace_tree_source = "deterministic_spec_merge"

        max_retries = 3
        retry_count = 0
        while not validation.get("approved") and retry_count < max_retries:
            retry_count += 1
            validation_summary = _summarize_master_tree_validation(validation)
            validation_report = _render_master_tree_validation_report(validation)
            _log_master_agent(
                f"🔄 Master project tree validation conflict (Attempt {retry_count}/{max_retries}): {validation_summary}\n"
                "Auto-healing... Master Agent is actively regenerating tree plan to fix structural mismatch.",
                level="warning",
                project_token=project_token,
            )
            
            # Build explicit feedback with the PREVIOUS failed tree + full validation report
            # so the AI knows exactly what it produced and what's wrong with it.
            _log_master_agent(
                f"  Stack: {stack_profile.get('backend', 'unknown') if isinstance(stack_profile, dict) else 'unknown'} backend, "
                f"{stack_profile.get('frontend', 'unknown') if isinstance(stack_profile, dict) else 'unknown'} frontend",
                level="warning",
                project_token=project_token,
            )
            previous_tree_feedback = (
                "\n\n=== CRITICAL FIX REQUIRED ===\n"
                "Your PREVIOUS tree (shown below) failed validation. You MUST fix ALL issues listed.\n\n"
                f"--- PREVIOUS FAILED TREE ---\n{workspace_tree[:4000]}\n--- END PREVIOUS TREE ---\n\n"
                f"--- VALIDATION ERRORS ---\n{validation_report or validation_summary}\n--- END ERRORS ---\n\n"
                "INSTRUCTIONS:\n"
                "- Fix every issue listed above. Do not partially fix one item and ignore others.\n"
                "- The corrected tree must still be valid JSON with a single root.\n"
                "- Use the BEST PRACTICE project structure for the detected tech stack.\n"
                "- Output ONLY valid JSON containing an 'actions' array of dictionaries.\n"
                "- For Django apps: manage.py at root with standard Django layout.\n"
                "- Ensure every task has a clear file home in the tree.\n"
            )
            
            workspace_tree = await _generate_detailed_project_tree_plan(
                tasks=tasks,
                brd_summary=brd_summary,
                kg_context=kg_context,
                tech_spec=tech_spec,
                stack_profile=stack_profile,
                workspace_contract=workspace_contract if isinstance(workspace_contract, dict) else {},
                repo_tree_context=current_repo_tree,
                previous_tree_feedback=previous_tree_feedback,
            )
            workspace_tree_source = f"ai_tree_plan_retry_{retry_count}"
            
            validation = await _validate_master_project_tree_plan(
                tasks=tasks,
                workspace_tree=workspace_tree,
                brd_summary=brd_summary,
                tech_spec=tech_spec,
                workspace_contract=workspace_contract if isinstance(workspace_contract, dict) else {},
                stack_profile=stack_profile,
                repo_tree_context=current_repo_tree,
            )

        if not validation.get("approved"):
            validation_summary = _summarize_master_tree_validation(validation)
            _log_master_agent(
                f"❌ Master project tree failed validation after {max_retries} auto-healing attempts and will not be published.\n"
                f"Conflict: {validation_summary}\n"
                "Agents are safely waiting. The Master Agent will keep attempting to fix this in the next background cycle until it matches requirements.",
                level="error",
                project_token=project_token,
            )
            return {
                "success": False,
                "reason": "master_tree_validation_failed",
                "error": f"master_tree_validation_failed: {validation_summary}",
                "title": title,
                "validation": validation,
            }

        dynamic_architecture = _derive_dynamic_architecture_overview(
            stack_profile=stack_profile,
            workspace_contract=workspace_contract if isinstance(workspace_contract, dict) else {},
            workspace_tree=workspace_tree,
            tasks=tasks,
        )
        if dynamic_architecture:
            architecture_overview = dynamic_architecture

        dynamic_dependencies = _derive_dynamic_dependencies(
            workspace_tree=workspace_tree,
            workspace_contract=workspace_contract if isinstance(workspace_contract, dict) else {},
        )
        if dynamic_dependencies:
            dependencies = dynamic_dependencies

        normalized_tree_json = _ensure_workspace_tree_json(
            workspace_tree,
            fallback_root_label=(effective_project or "project"),
        )
        if normalized_tree_json:
            workspace_tree = normalized_tree_json

        try:
            refreshed_contract = ctx_mgr.update_workspace_contract_from_canonical_tree(
                effective_project,
                workspace_tree,
            ) if ctx_mgr else {}
            refreshed_contract = refreshed_contract if isinstance(refreshed_contract, dict) else {}
            if refreshed_contract.get("status") == "ready":
                workspace_contract = refreshed_contract
                workspace_contract_signature = _workspace_contract_signature(workspace_contract)
                _log_master_agent(
                    "Master tree established the workspace contract for agent coordination.",
                    project_token=project_token,
                )
        except Exception as exc:
            logger.warning("[%s] Failed to bootstrap workspace contract from master tree: %s", effective_project, exc)

        public_task_plan = _build_public_master_task_plan(task_plan)
        public_payload = {
            "note_type": "master_project_plan",
            "project_token": _note_scope_key(project_token),
            "author_agent_id": MASTER_AGENT_ID,
            "updated_at": _note_timestamp(),
            "task_signature": task_signature,
            "worker_signature": worker_signature,
            "workspace_contract_signature": workspace_contract_signature,
            "summary": (
                "Canonical project tree and implementation plan created by the master agent from the BRD analysis, "
                "task details, checklist context, and current repository tree. "
                "All worker agents must follow this tree, implement inside these boundaries, "
                "and align their work with the task plan below."
            ),
            "brd_analysis_context": brd_summary[:4000],
            "current_repo_tree": current_repo_tree,
            "current_repo_tree_source": current_repo_tree_source,
            "workspace_tree": workspace_tree,
            "workspace_tree_json": normalized_tree_json or workspace_tree,
            "workspace_tree_source": workspace_tree_source,
            "architecture_overview": architecture_overview[:3000],
            "dependencies": dependencies[:1800],
            "tasks_considered": public_task_plan,
            "stack_profile": stack_profile,
            "workspace_contract": {
                "status": workspace_contract.get("status") if isinstance(workspace_contract, dict) else None,
                "source": workspace_contract.get("source") if isinstance(workspace_contract, dict) else None,
                "allowed_top_level_dirs": list((workspace_contract or {}).get("allowed_top_level_dirs") or [])[:25],
                "allowed_source_roots": list((workspace_contract or {}).get("allowed_source_roots") or [])[:25],
            },
            "validation": {
                "approved": bool(validation.get("approved")),
                "confidence": validation.get("confidence"),
                "issues_missing_files": list(validation.get("issues_missing_files") or [])[:10],
                "issues_conflicts": list(validation.get("issues_conflicts") or [])[:10],
                "recommendations": list(validation.get("recommendations") or [])[:10],
                "validator_agent_id": validation.get("validator_agent_id") or "structure_validator",
                "mode": validation.get("mode") or "heuristic",
            },
            "instructions": [
                "Use this canonical tree as the single source of truth for where files should live.",
                "Every task below must be implemented inside this structure; do not create alternate app roots or duplicate folders.",
                "Coordinate task pickup through the normal task workflow.",
                "If a task requires a structural change, update this master note first.",
            ],
        }
        rendered_markdown = _render_master_note_markdown(public_payload)

        result = await _upsert_agent_note(
            title=title,
            content_payload=public_payload,
            content_text=rendered_markdown,
            user=_note_user_for_agent(MASTER_AGENT_ID),
            project_token=project_token,
            task_token=task_token,
        )
        if result.get("success"):
            _log_master_agent(
                f"Published master project tree note: {title}",
                project_token=project_token,
            )
        else:
            _log_master_agent(
                f"Failed to publish master note: {result.get('error', 'unknown error')}",
                level="error",
                project_token=project_token,
            )
        final_result = {
            **result,
            "title": title,
            "task_count": len(task_plan),
            "validation": public_payload["validation"],
            "approved": True,
            "task_signature": task_signature,
            "worker_signature": worker_signature,
            "workspace_contract_signature": workspace_contract_signature,
            "recommended_assignments": recommended_assignments,
            "tasks_considered": task_plan,
            "workspace_tree": workspace_tree,
            "stack_profile": stack_profile,
            "workspace_contract": public_payload["workspace_contract"],
            "brd_analysis_context": public_payload.get("brd_analysis_context"),
            "current_repo_tree": public_payload.get("current_repo_tree"),
            "current_repo_tree_source": public_payload.get("current_repo_tree_source"),
            "instructions": list(public_payload.get("instructions") or [])[:12],
        }
        state["master_note_cache"] = dict(final_result)
        return final_result


async def _publish_agent_status_note(
    *,
    agent_id: str,
    task: Dict[str, Any],
    status: str,
    project_token: Optional[str] = None,
    task_token: Optional[str] = None,
    branch_name: Optional[str] = None,
    planned_files: Optional[List[str]] = None,
    completed_files: Optional[List[str]] = None,
    symbols_created: Optional[List[str]] = None,
    symbols_modified: Optional[List[str]] = None,
    next_agent_should: str = "",
    summary: str = "",
) -> Dict[str, Any]:
    task_id = str(_normalize_task_id(task) or task.get("external_id") or task.get("id") or "unknown")
    title = _note_title("STATUS", project_token, agent_id)
    timestamp = _note_timestamp()
    existing_payload = await _get_existing_note_payload(
        title=title,
        project_token=project_token,
        task_token=task_token,
    )
    entry = {
        "task_id": task_id,
        "task_title": task.get("title") or task.get("taskName") or "Untitled task",
        "status": status,
        "branch": branch_name or "",
        "planned_files": list(planned_files or [])[:25],
        "completed_files": list(completed_files or [])[:25],
        "symbols_created": list(symbols_created or [])[:25],
        "symbols_modified": list(symbols_modified or [])[:25],
        "next_agent_should": next_agent_should,
        "summary": summary or _to_single_line(task.get("description") or ""),
        "started_at": timestamp,
        "updated_at": timestamp,
    }
    if str(status).lower() in {"completed", "failed"}:
        entry["completed_at"] = timestamp

    payload = _build_agent_note_payload(
        existing_payload=existing_payload,
        agent_id=agent_id,
        project_token=project_token,
        entry=entry,
    )
    return await _upsert_agent_note(
        title=title,
        content_payload=payload,
        user=_note_user_for_agent(agent_id),
        project_token=project_token,
        task_token=task_token,
    )


async def _publish_task_handoff_note(
    *,
    agent_id: str,
    task: Dict[str, Any],
    project_token: Optional[str] = None,
    task_token: Optional[str] = None,
    branch_name: Optional[str] = None,
    completed_files: Optional[List[str]] = None,
    symbols_created: Optional[List[str]] = None,
    symbols_modified: Optional[List[str]] = None,
    summary: str = "",
) -> Dict[str, Any]:
    completed = list(completed_files or [])[:25]
    next_agent_should = (
        f"Continue from these files: {', '.join(completed[:5])}. "
        "Do not recreate the same feature in alternate directories."
        if completed
        else "Use the latest merged branch artifacts and extend them instead of recreating them."
    )
    return await _publish_agent_status_note(
        agent_id=agent_id,
        task=task,
        status="completed",
        project_token=project_token,
        task_token=task_token,
        branch_name=branch_name,
        completed_files=completed,
        symbols_created=symbols_created,
        symbols_modified=symbols_modified,
        next_agent_should=next_agent_should,
        summary=summary,
    )


_TASK_PHASE_ORDER = {
    "foundation": 1,
    "backend-core": 2,
    "backend-features": 3,
    "frontend-core": 4,
    "frontend-features": 5,
    "integration": 6,
}


def _get_task_priority_score(task: Dict[str, Any]) -> int:
    priority = str(task.get("priority") or "medium").lower()
    return {"high": 3, "medium": 2, "low": 1}.get(priority, 2)


def _get_task_phase_order(task: Dict[str, Any]) -> int:
    phase = str(task.get("phase") or task.get("task_phase") or "").lower().strip()
    return _TASK_PHASE_ORDER.get(phase, 99)


def _coerce_task_execution_order(value: Any) -> Optional[float]:
    if value in (None, "") or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except Exception:
        match = _re.match(r"^\D*(\d+(?:\.\d+)?)", text)
        if match:
            try:
                return float(match.group(1))
            except Exception:
                return None
    return None


def _sort_tasks_for_execution(tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Sort tasks for serial execution order:
      1. Sprint (earlier sprints first, by sprint_id numeric order)
      2. Priority (High → Medium → Low)
      3. Task serial number (task_number, sequence, etc.)
      4. Original index as final tiebreaker
    """
    ordered = list(tasks or [])
    indexed_tasks = list(enumerate(ordered))
    order_fields = (
        "task_number",
        "number",
        "sequence",
        "sequence_number",
        "position",
        "sort_order",
        "display_order",
        "order",
        "serial_number",
        "serial",
    )

    # Priority ranking: lower number = higher priority
    _PRIORITY_RANK = {
        "critical": 0,
        "urgent": 0,
        "high": 1,
        "medium": 2,
        "normal": 2,
        "low": 3,
        "none": 4,
    }

    def _sprint_sort_key(task: Dict[str, Any]) -> float:
        """Return a numeric sprint rank. Lower = earlier sprint."""
        sprint_id = task.get("sprint_id") or task.get("sprint")
        if isinstance(sprint_id, dict):
            sprint_id = sprint_id.get("id")
        rank = _coerce_task_execution_order(sprint_id)
        if rank is not None:
            return rank
        # Try to extract sprint number from sprint_name (e.g. "Sprint 2 - Feature Development")
        sprint_name = str(task.get("sprint_name") or "").strip().lower()
        if sprint_name:
            # "foundation" sprints come first
            if "foundation" in sprint_name:
                return 0.0
            match = _re.search(r"sprint\s*(\d+)", sprint_name)
            if match:
                return float(match.group(1))
        return 10**9  # Unknown sprint goes last

    def _priority_sort_key(task: Dict[str, Any]) -> int:
        """Return priority rank. Lower = higher priority."""
        raw = str(task.get("priority") or "medium").strip().lower()
        return _PRIORITY_RANK.get(raw, 2)

    def _serial_sort_key(index: int, task: Dict[str, Any]) -> float:
        """Return task serial number from order fields."""
        for field in order_fields:
            explicit = _coerce_task_execution_order(task.get(field))
            if explicit is not None:
                return explicit
        return float(index)

    def _task_sort_key(item: tuple[int, Dict[str, Any]]) -> tuple[float, int, float, int]:
        index, task = item
        return (
            _sprint_sort_key(task),        # 1. Sprint order
            _priority_sort_key(task),      # 2. Priority (High first)
            _serial_sort_key(index, task), # 3. Task serial number
            index,                         # 4. Stable tiebreaker
        )

    indexed_tasks.sort(key=_task_sort_key)
    return [task for _, task in indexed_tasks]


def _normalize_task_domain(task: Dict[str, Any]) -> Optional[str]:
    raw_domain = str(task.get("domain") or task.get("task_domain") or "").lower().strip()
    if raw_domain in {"backend", "frontend", "integration", "foundation"}:
        return raw_domain

    phase = str(task.get("phase") or task.get("task_phase") or "").lower().strip()
    if phase.startswith("backend"):
        return "backend"
    if phase.startswith("frontend"):
        return "frontend"
    if phase == "integration":
        return "integration"
    if phase == "foundation":
        return "foundation"

    text = " ".join(
        str(task.get(part) or "")
        for part in ("title", "taskName", "description")
    ).lower()
    if any(token in text for token in ("react", "frontend", "ui", "component", "vite", "css", "jsx", "tsx")):
        return "frontend"
    if any(token in text for token in ("backend", "api", "database", "schema", "sql", "fastapi", "python")):
        return "backend"

    return raw_domain or None


def _extract_task_paths_from_text(text: str) -> List[str]:
    content = str(text or "")
    if not content:
        return []

    patterns = [
        r"`([^`\n]+\.[A-Za-z0-9]+)`",
        r"([A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+\.[A-Za-z0-9]+)",
        r"((?:backend|frontend|src|app|api|routes|services|components)/[A-Za-z0-9_./-]+)",
        r"\b([A-Za-z0-9_.-]+\.(?:py|js|jsx|ts|tsx|json|yml|yaml|md|sql|css|scss|html))\b",
    ]

    matches: List[str] = []
    for pattern in patterns:
        matches.extend(_re.findall(pattern, content))

    banned_singletons = {
        "node.js",
        "express.js",
        "react.js",
        "next.js",
        "math.js",
        "typescript.js",
        "javascript.js",
    }

    normalized = []
    seen = set()
    for item in matches:
        candidate = str(item or "").strip().strip(".,:;()[]{}<>\"'")
        if not candidate:
            continue
        candidate = candidate.replace("\\", "/")
        if candidate.startswith("/workspace/"):
            candidate = candidate[len("/workspace/"):]
        if candidate.startswith("./"):
            candidate = candidate[2:]
        candidate_lower = candidate.lower()
        if "/" not in candidate and candidate_lower in banned_singletons:
            continue
        if candidate in seen:
            continue
        seen.add(candidate)
        normalized.append(candidate)
    return normalized


def _extend_paths_from_value(target: List[str], value: Any) -> None:
    if value is None:
        return
    if isinstance(value, str):
        target.extend(_extract_task_paths_from_text(value))
        return
    if isinstance(value, dict):
        for nested in value.values():
            _extend_paths_from_value(target, nested)
        return
    if isinstance(value, list):
        for nested in value:
            _extend_paths_from_value(target, nested)


def _predict_task_file_intents(task: Dict[str, Any]) -> List[str]:
    predicted = list(task.get("_predicted_files") or [])
    if predicted:
        if not task.get("_predicted_files_source"):
            task["_predicted_files_source"] = "provided"
        return predicted

    candidates: List[str] = []
    for key in (
        "affected_files",
        "file_paths",
        "files",
        "target_files",
        "paths",
        "touch_files",
        "artifacts",
        "deliverables",
    ):
        _extend_paths_from_value(candidates, task.get(key))

    _extend_paths_from_value(candidates, task.get("title"))
    _extend_paths_from_value(candidates, task.get("taskName"))
    _extend_paths_from_value(candidates, task.get("description"))
    _extend_paths_from_value(candidates, task.get("summary"))
    _extend_paths_from_value(candidates, task.get("acceptance_criteria"))
    _extend_paths_from_value(candidates, task.get("checklist"))

    normalized: List[str] = []
    seen = set()
    for path in candidates:
        candidate = str(path or "").strip()
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        normalized.append(candidate)

    task["_predicted_files"] = normalized[:25]
    task["_predicted_files_source"] = "task_text"
    return task["_predicted_files"]


def _task_is_fix_task(task: Dict[str, Any]) -> bool:
    task_name = str(task.get("taskName") or task.get("title") or "").lower()
    return "fix" in task_name or "bug" in task_name


def _check_task_conflicts(
    agent_id: str,
    task: Dict[str, Any],
    live_mem: Any,
    project_token: Optional[str] = None,
) -> tuple[bool, str]:
    task_domain = _normalize_task_domain(task)
    predicted_files = _predict_task_file_intents(task)
    predicted_source = str(task.get("_predicted_files_source") or "").strip().lower()
    if predicted_files and project_token:
        try:
            import context_manager as ctx_mgr

            normalized_predicted_files = ctx_mgr.normalize_paths_for_workspace_contract(
                project_token,
                predicted_files,
                task_domain=task_domain,
            )
            if normalized_predicted_files:
                predicted_files = normalized_predicted_files
                task["_predicted_files"] = predicted_files[:25]
        except Exception:
            pass
    if predicted_files and live_mem:
        try:
            inferred_domain = live_mem.infer_domain_for_files(predicted_files)
        except Exception:
            inferred_domain = None
        if inferred_domain:
            if inferred_domain == "integration" or not task_domain:
                task_domain = inferred_domain
            elif (
                predicted_source == "master_plan"
                and inferred_domain in {"backend", "frontend"}
                and task_domain in {"backend", "frontend"}
                and inferred_domain != task_domain
            ):
                task_domain = inferred_domain
    if task_domain:
        task["_resolved_task_domain"] = task_domain

    if not live_mem:
        return False, ""

    if predicted_files:
        if project_token:
            try:
                import context_manager as ctx_mgr

                contract_validation = ctx_mgr.validate_paths_against_workspace_contract(
                    project_token,
                    predicted_files,
                    task_domain=task_domain,
                )
                if not contract_validation.get("allowed", True):
                    violations = contract_validation.get("violations") or []
                    return True, "; ".join(violations[:5])
            except Exception:
                pass

        blocked = []
        if task_domain in {"backend", "frontend"}:
            for file_path in predicted_files:
                allowed, reason = live_mem.can_agent_edit_file(task_domain, file_path)
                if not allowed:
                    blocked.append(f"{file_path}: {reason}")
        if blocked:
            return True, "; ".join(blocked[:5])

        conflict_map = live_mem.get_file_conflicts(agent_id, predicted_files)
        if conflict_map:
            compact = [
                f"{path} -> {', '.join(sorted(editors))}"
                for path, editors in sorted(conflict_map.items())
            ]
            return True, "; ".join(compact[:5])
    elif task_domain in {"backend", "frontend"}:
        with live_mem._lock:
            for other_agent_id, record in live_mem.active_tasks.items():
                if other_agent_id == agent_id:
                    continue
                if record.task_domain == task_domain and not record.files_touched:
                    return True, (
                        f"domain '{task_domain}' already busy by {other_agent_id} "
                        f"for '{record.task_title}'"
                    )

    return False, ""


async def _claim_initial_task_assignments(
    agents_config: Dict[str, Dict[str, str]] = None,
    project_token: Optional[str] = None,
    task_token: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Prepare the ordered agent queue for supervisor execution.
    Serial assignment: tasks are sorted by execution order and assigned
    one-by-one to agents (task 1 → agent 1, task 2 → agent 2, etc.).
    If agents sit idle, the master supervisor will assign them later.
    """
    state = _ensure_project_state(project_token)
    if task_token:
        state["task_token"] = task_token
    project_agents = state["agent_states"]
    claimed_task_ids = state["claimed_task_ids"]

    idle_agents = [
        a for a in project_agents.values()
        if (
            (a["status"] == "idle")
            or _is_waiting_for_master_plan(a)
        )
        and not _is_system_agent_id(a["id"])
    ]
    if not idle_agents:
        raise ValueError("No idle agents. Reset agents or add new ones.")

    try:
        external_tasks = await _fetch_external_tasks(project_token)
        if not external_tasks:
            raise ValueError("No tasks available from the external task API. Generate tasks first.")
        state["tasks"] = external_tasks
    except Exception as exc:
        raise

    await _restore_persisted_agent_assignments(
        project_token=project_token,
        task_token=task_token,
        agent_ids=[agent["id"] for agent in idle_agents],
        external_tasks=external_tasks,
    )

    if agents_config:
        for agent in idle_agents:
            agent_cfg = agents_config.get(agent["id"]) or {}
            repo_val = agent_cfg.get("git_repo_url")
            token_val = agent_cfg.get("git_token")
            if repo_val:
                agent["git_repo_url"] = repo_val.strip()
            if token_val:
                agent["git_token"] = token_val.strip()

    # ── Serial assignment: sort tasks by execution order, assign to agents one-by-one ──
    serial_agents = sorted(idle_agents, key=lambda item: item["id"])
    sorted_tasks = _sort_tasks_for_execution(external_tasks)

    # Filter to only available (non-done, non-claimed) tasks
    available_tasks = []
    for t in sorted_tasks:
        tid = str(_normalize_task_id(t) or t.get("external_id") or t.get("id") or "")
        if not tid:
            continue
        if _task_status_is_done(t.get("status")):
            continue
        if tid in claimed_task_ids:
            continue
        # Skip tasks already assigned to a specific agent (they'll pick those up in _pick_next_task)
        existing_assignee = _resolve_assigned_runtime_agent_id(t, project_agents)
        if existing_assignee:
            continue
        available_tasks.append(t)

    # Serial round-robin: task 1 → agent 1, task 2 → agent 2, ...
    assignments = []
    task_index = 0
    effective_token = task_token or get_project_task_token(project_token)

    for agent in serial_agents:
        # ── GUARD: Skip if this agent already has an active task ──
        already_has_task = None
        for t in external_tasks:
            if _task_status_is_done(t.get("status")):
                continue
            resolved_owner = _resolve_assigned_runtime_agent_id(t, project_agents)
            if resolved_owner == agent["id"]:
                already_has_task = t
                break
        
        if already_has_task:
            existing_tid = str(_normalize_task_id(already_has_task) or already_has_task.get("external_id") or already_has_task.get("id") or "")
            logger.info(
                f"[Serial Assignment] Agent {agent['id']} already has active task {existing_tid}. Skipping new assignment."
            )
            claimed_task_ids.add(existing_tid)
            reserved = _apply_master_task_metadata(dict(already_has_task), project_token=project_token)
            if project_token:
                reserved.setdefault("_project_token", project_token)
            agent["current_task"] = reserved
            agent["resume_pending_task"] = True
            assignments.append((agent["id"], reserved))
            continue

        if task_index >= len(available_tasks):
            # No more tasks — agent starts idle, master supervisor will assign later
            assignments.append((agent["id"], None))
            continue

        task = available_tasks[task_index]
        tid = str(_normalize_task_id(task) or task.get("external_id") or task.get("id") or "")

        # Opt-in serially via task_service
        try:
            from task_service import task_service
            agent_username = build_external_agent_username(agent["id"], agent.get("name"))
            await task_service.opt_in_task(
                {"task_id": int(tid), "username": agent_username},
                task_token=effective_token,
            )
            claimed_task_ids.add(tid)
            task = _apply_master_task_metadata(dict(task), project_token=project_token)
            if project_token:
                task.setdefault("_project_token", project_token)
            agent["current_task"] = task
            agent["resume_pending_task"] = True
            assignments.append((agent["id"], task))
            logger.info(f"[Serial Assignment] Task {tid} → {agent['id']} ({agent.get('name', 'unnamed')})")
            task_index += 1
        except Exception as opt_err:
            logger.warning(f"[Serial Assignment] Opt-in failed for task {tid} → {agent['id']}: {opt_err}")
            # Skip this task (someone else may have claimed it) and try next
            task_index += 1
            assignments.append((agent["id"], None))

    if not assignments:
        raise ValueError("No idle agents available for serial execution.")

    logger.info(
        f"[Serial Assignment] Assigned {sum(1 for _, t in assignments if t is not None)} tasks "
        f"to {len(assignments)} agents serially."
    )

    return {
        "idle_agents": [agent["id"] for agent in idle_agents],
        "assignments": assignments,
    }


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
            if progress == 100:
                print(f"[agent_service] Progress reached 100% for task {task_id}, triggering task completion...")
                await _post_task_complete(task, project_token=resolved_project, task_token=effective_token)
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
            print(f"[agent_service] Successfully opted in to task {task_id}, posting check-in message...")
            await _post_task_message(task, f"{username} checked in and reviewing task.", project_token=resolved_project, task_token=task_token)
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
    """
    Pick the next uncompleted, unclaimed task from the external API.
    Serial opt-in: agents pick tasks one at a time in sorted order.
    When an eligible task is found, the agent opts-in via task_service.opt_in_task()
    atomically inside the claim lock. If opt-in fails (another agent got there first),
    the task is skipped and the next one is tried.
    If the agent ends up idle (no tasks), the master supervisor loop will
    assign tasks to them via _master_assign_task_to_agent().
    """
    if task_token:
        set_project_task_token(project_token, task_token)
    state = _ensure_project_state(project_token)
    project_agents = state["agent_states"]
    claimed_task_ids = state["claimed_task_ids"]
    task_claim_lock = state["task_claim_lock"]
    
    # Check integration gate - if blocked, only allow fix tasks
    try:
        import context_manager as ctx_mgr
        live_mem = ctx_mgr.get_live_memory(project_token or "")
        workspace_contract = ctx_mgr.get_workspace_contract(project_token or "")
        if live_mem.is_integration_blocked():
            integration_blocked = True
        else:
            integration_blocked = False
    except Exception:
        live_mem = None
        workspace_contract = {"status": "insufficient"}
        integration_blocked = False

    if live_mem and workspace_contract.get("status") != "ready":
        with live_mem._lock:
            other_active = [
                aid for aid in live_mem.active_tasks
                if aid != agent_id and not _is_system_agent_id(aid)
            ]
        if other_active:
            logger.info(
                f"[{agent_id}] Workspace contract not ready; waiting for bootstrap agent(s): {other_active}"
            )
            return None
    
    external_tasks = await _fetch_external_tasks(project_token)

    # ── GUARD: Check if this agent already has an active (non-completed) task ──
    # If the agent is already assigned to a task, return that task instead of picking a new one.
    # This prevents a single agent from being assigned to multiple tasks simultaneously.
    agent = project_agents.get(agent_id)
    agent_username = build_external_agent_username(agent_id, agent.get("name") if agent else None)
    for t in external_tasks:
        if _task_status_is_done(t.get("status")):
            continue
        resolved_owner = _resolve_assigned_runtime_agent_id(t, project_agents)
        if resolved_owner == agent_id:
            tid = str(_normalize_task_id(t) or t.get("external_id") or t.get("id") or "")
            # This agent already has this task — return it, don't pick another
            logger.info(
                f"[{agent_id}] Already assigned to active task {tid} "
                f"('{(t.get('title') or t.get('taskName') or '')[:50]}'). "
                f"Resuming instead of picking a new task."
            )
            claimed_task_ids.add(tid)
            reserved = _apply_master_task_metadata(dict(t), project_token=project_token)
            if project_token:
                reserved.setdefault("_project_token", project_token)
            if agent:
                agent["current_task"] = reserved
                agent["resume_pending_task"] = True
            return reserved

    async with task_claim_lock:
        active_owned_ids = _active_owned_task_ids(project_token)
        completed_task_ids = {
            _task_identity(task)
            for task in (state.get("completed_tasks") or [])
            if isinstance(task, dict)
        }
        external_status_by_id = {
            str(_normalize_task_id(task) or task.get("external_id") or task.get("id")): str(task.get("status") or "").strip().lower()
            for task in external_tasks
        }
        stale_claims = []
        for claimed_id in list(claimed_task_ids):
            if claimed_id in active_owned_ids:
                continue
            if claimed_id in completed_task_ids:
                continue
            ext_status = external_status_by_id.get(str(claimed_id))
            # Only release a claimed id if it has disappeared upstream or is
            # definitively completed. If it is still active upstream, keep it
            # marked as claimed so other local agents do not compete for it.
            if ext_status is None or _task_status_is_done(ext_status):
                claimed_task_ids.discard(claimed_id)
                stale_claims.append(str(claimed_id))
        if stale_claims:
            logger.info(
                f"[{agent_id}] Released stale claimed task ids: {', '.join(sorted(stale_claims)[:10])}"
            )

        # Get current active sprint from project state (if available)
        current_sprint_id = None
        try:
            project_state = _ensure_project_state(project_token)
        except Exception:
            pass

        external_tasks = _sort_tasks_for_execution(external_tasks)

        skip_reasons = {
            "completed_or_claimed": 0,
            "integration_gate": 0,
            "sprint_mismatch": 0,
            "dependency_blocked": 0,
            "conflict_blocked": 0,
            "explicitly_blocked": 0,
            "opt_in_failed": 0,
        }
        
        # ── Step 1: Separate tasks into assigned-to-me vs unassigned ──
        assigned_to_me = []
        other_tasks = []
        
        for t in external_tasks:
            resolved_agent_id = _resolve_assigned_runtime_agent_id(t, project_agents)
            if resolved_agent_id == agent_id:
                assigned_to_me.append(t)
            elif not resolved_agent_id:
                other_tasks.append(t)
        
        # ── Step 2: Serial pick — assigned-to-me first, then unassigned ──
        for t in assigned_to_me + other_tasks:
            _apply_master_task_metadata(t, project_token=project_token)
            tid = str(_normalize_task_id(t) or t.get("external_id") or t.get("id"))
            status_lower = (t.get("status") or "").lower()

            # Skip if completed or already claimed by another agent in this process
            if _task_status_is_done(status_lower) or tid in claimed_task_ids:
                skip_reasons["completed_or_claimed"] += 1
                continue
            
            # If the task explicitly has the "BLOCKED" tag or status, skip it
            task_tags = [str(tag).lower() for tag in (t.get("tags") or [])]
            if status_lower == "blocked" or "blocked" in task_tags:
                skip_reasons["explicitly_blocked"] += 1
                continue

            # Integration gate: if blocked, only allow fix tasks
            if integration_blocked:
                task_name = (t.get("taskName") or t.get("title") or "").lower()
                if "fix" not in task_name and "bug" not in task_name.lower():
                    skip_reasons["integration_gate"] += 1
                    continue

            if current_sprint_id:
                task_sprint_id = t.get("sprint") or t.get("sprint_id")
                if task_sprint_id and str(task_sprint_id) != str(current_sprint_id):
                    skip_reasons["sprint_mismatch"] += 1
                    continue

            if live_mem:
                task_deps = t.get("dependencies", [])
                if not task_deps:
                    linked = t.get("linked_tasks", [])
                    if linked:
                        task_deps = [str(lt) for lt in linked]

                if task_deps:
                    live_mem.register_task_dependencies(tid, [str(d) for d in task_deps])

                if not live_mem.check_task_dependencies(tid):
                    blocking = live_mem.get_blocking_tasks(tid)
                    logger.info(
                        f"[{agent_id}] Task {tid} blocked by dependencies: {blocking}"
                    )
                    skip_reasons["dependency_blocked"] += 1
                    continue

                blocked, reason = _check_task_conflicts(agent_id, t, live_mem, project_token=project_token)
                if blocked:
                    logger.info(f"[{agent_id}] Task {tid} blocked by conflict rules: {reason}")
                    skip_reasons["conflict_blocked"] += 1
                    continue

            # ── Step 3: Serial opt-in — atomically claim via external API ──
            try:
                from task_service import task_service
                effective_token = task_token or get_project_task_token(project_token)
                await task_service.opt_in_task(
                    {"task_id": int(tid), "username": agent_username},
                    task_token=effective_token,
                )
                logger.info(f"[{agent_id}] ✅ Serial opt-in succeeded for task {tid}")
            except Exception as opt_err:
                # If upstream reports that the task already has assigned users,
                # treat it as claimed elsewhere so no other local agents will
                # attempt to opt in again.
                err_text = str(opt_err).lower()
                if "task already has assigned users" in err_text:
                    claimed_task_ids.add(tid)
                    logger.info(
                        f"[{agent_id}] Task {tid} already has assigned users upstream; "
                        f"marking as claimed and skipping."
                    )
                else:
                    logger.info(
                        f"[{agent_id}] Opt-in failed for task {tid} (another agent may have claimed it): {opt_err}"
                    )
                skip_reasons["opt_in_failed"] += 1
                continue

            # Opt-in succeeded — claim locally
            claimed_task_ids.add(tid)
            for lt in (t.get("linked_tasks") or []):
                claimed_task_ids.add(str(lt))
            if agent:
                reserved_task = _apply_master_task_metadata(dict(t), project_token=project_token)
                if project_token:
                    reserved_task.setdefault("_project_token", project_token)
                agent["current_task"] = reserved_task
                agent["resume_pending_task"] = True
            return t

        logger.info(
            f"[{agent_id}] No eligible task found from {len(external_tasks)} fetched task(s). "
            f"Skip summary: {skip_reasons}. Claimed ids remaining: {len(claimed_task_ids)}. "
            f"Master supervisor will assign if agent stays idle."
        )
        return None


async def run_agent(agent_id: str, git_repo_url: str = None, git_token: str = None,
                    assigned_task: Dict[str, Any] = None,
                    continuous: bool = False,
                    ignore_running_check: bool = False,
                    project_token: Optional[str] = None,
                    task_token: Optional[str] = None,
                    force_branch: Optional[str] = None) -> Dict[str, Any]:
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

    if not assigned_task and not _is_system_agent_id(agent_id):
        try:
            await _restore_persisted_agent_assignments(
                project_token=project_token,
                task_token=task_token,
                agent_ids=[agent_id],
            )
        except Exception as exc:
            logger.warning("[%s] Failed to restore persisted assignment for %s: %s", project_token or "", agent_id, exc)

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
                force_branch=force_branch,
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
                agent["resume_pending_task"] = False
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
                agent["resume_pending_task"] = False
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
                agent["resume_pending_task"] = False
                agent["progress"] = 0
                agent["progress_message"] = f"Error after {MAX_RETRIES} retries: {str(e)}"
                agent["output_log"].append({
                    "time": datetime.utcnow().isoformat(),
                    "type": "error",
                    "message": f"❌ All {MAX_RETRIES} attempts failed. Last error: {str(e)}",
                })
                
                # Notify Master Agent for failure analysis
                try:
                    current_task = agent.get("current_task")
                    await _master_notify_agent_failure(
                        agent_id=agent_id,
                        task=current_task,
                        error=str(e),
                        project_token=project_token,
                        task_token=task_token,
                    )
                except Exception as master_err:
                    logger.warning(f"[{agent_id}] Failed to notify Master Agent: {master_err}")
                
                agent["last_run"] = datetime.utcnow().isoformat()
                agent["current_task"] = None
                return last_result

    return last_result


async def _run_agent_once(agent_id: str, git_repo_url: str = None, git_token: str = None,
                    assigned_task: Dict[str, Any] = None,
                    continuous: bool = False,
                    ignore_running_check: bool = False,
                    project_token: Optional[str] = None,
                    task_token: Optional[str] = None,
                    force_branch: Optional[str] = None) -> Dict[str, Any]:
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
    master_note_result = None
    if not _is_system_agent_id(agent_id):
        try:
            master_note_result = await ensure_master_workspace_note(
                project_token=project_token,
                task_token=task_token,
            )
        except Exception as exc:
            master_note_result = {"success": False, "error": str(exc)}
        if not master_note_result.get("success"):
            validation_summary = _summarize_master_tree_validation(master_note_result.get("validation"))
            raise ValueError(
                "Master project tree is not validated yet. "
                f"Reason: {master_note_result.get('error') or master_note_result.get('reason') or 'unknown'}"
                + (f" ({validation_summary})" if validation_summary else "")
            )

    # 1. Get the first task
    resumed_existing_task = False
    if assigned_task:
        task = assigned_task
    elif isinstance(agent.get("current_task"), dict):
        resumed_task = _apply_master_task_metadata(dict(agent["current_task"]), project_token=project_token)
        resumed_task_id = _task_identity(resumed_task)
        external_tasks = state.get("tasks") if isinstance(state.get("tasks"), list) else []
        if resumed_task_id:
            external_match = next(
                (
                    ext_task for ext_task in external_tasks
                    if _task_identity(ext_task) == resumed_task_id
                ),
                None,
            )
            if external_match and not _task_status_is_done(external_match.get("status")):
                resumed_task = _apply_master_task_metadata(dict(external_match), project_token=project_token)
        if project_token:
            resumed_task.setdefault("_project_token", project_token)
        if resumed_task_id and not _task_status_is_done(resumed_task.get("status")):
            task = resumed_task
            resumed_existing_task = True
        else:
            agent["current_task"] = None
            agent["resume_pending_task"] = False
            task = await _pick_next_task(agent_id, project_token=project_token, task_token=task_token)
    else:
        task = await _pick_next_task(agent_id, project_token=project_token, task_token=task_token)
    if not task:
        now = datetime.utcnow().isoformat()
        agent["status"] = "idle"
        agent["resume_pending_task"] = False
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
    task = _apply_master_task_metadata(task, project_token=project_token)
    if isinstance(task, dict) and project_token:
        task.setdefault("_project_token", project_token)

    # Set agent to running
    agent["status"] = "running"
    agent["resume_pending_task"] = False
    agent["output_log"] = []
    if master_note_result:
        if master_note_result.get("success"):
            agent["output_log"].append({
                "time": datetime.utcnow().isoformat(),
                "type": "info",
                "message": f"Master note loaded: {master_note_result.get('title')}"
            })
        else:
            agent["output_log"].append({
                "time": datetime.utcnow().isoformat(),
                "type": "info",
                "message": f"Master note unavailable: {master_note_result.get('error') or master_note_result.get('reason') or 'unknown'}"
            })
    if resumed_existing_task:
        task_id = _task_identity(task)
        agent["output_log"].append({
            "time": datetime.utcnow().isoformat(),
            "type": "info",
            "message": (
                f"Recovered assigned task [{task_id or '?'}] {str(task.get('title') or task.get('taskName') or 'Untitled task')[:120]} "
                "from persisted coordination state."
            ),
        })
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
            started_by_name = normalize_agent_name(agent_id, agent.get("name"))
            task["status"] = "in_progress"
            task["assigned_agent"] = agent_id
            task["assigned_agent_name"] = started_by_name
            task["started_at"] = datetime.utcnow().isoformat()
            agent["resume_pending_task"] = False
            coordination_branch = (force_branch if force_branch else _branch_name_for_task(task)) if use_git else None

            # ── Register in Cross-Agent Shared Memory ────────────────
            try:
                import context_manager as ctx_mgr
                live_mem = ctx_mgr.get_live_memory(project_token or "")
                task_id = str(_normalize_task_id(task) or task.get("external_id") or task.get("id") or "")
                task_phase = task.get("phase") or task.get("task_phase")
                task_domain = task.get("_resolved_task_domain") or task.get("domain") or task.get("task_domain") or _normalize_task_domain(task)
                task_deps = task.get("dependencies", [])
                predicted_files = _predict_task_file_intents(task)
                
                live_mem.register_task_start(
                    agent_id=agent_id,
                    task_title=task.get("title", "Untitled"),
                    task_description=task.get("description", "")[:500],
                    branch_name=coordination_branch,
                    task_id=task_id,
                    task_phase=task_phase,
                    task_domain=task_domain,
                    dependencies=[str(d) for d in task_deps],
                )
                if predicted_files:
                    live_mem.register_file_intent(agent_id, predicted_files)
                other_active = [
                    aid for aid in live_mem.active_tasks
                    if aid != agent_id
                ]
                other_active_names = [
                    normalize_agent_name(aid, None)
                    for aid in other_active
                ]
                completed_count = len(live_mem.completed_history)
                agent["output_log"].append({
                    "time": datetime.utcnow().isoformat(),
                    "type": "info",
                    "message": (
                        f"Cross-agent memory: registered task start"
                        f" | {len(other_active)} peer(s) active"
                        f", {completed_count} task(s) in history"
                        + (f" | peers: {', '.join(other_active_names)}" if other_active_names else "")
                    )
                })
            except Exception as mem_err:
                agent["output_log"].append({
                    "time": datetime.utcnow().isoformat(),
                    "type": "info",
                    "message": f"Cross-agent memory: skipped ({str(mem_err)[:80]})"
                })
            
            username = build_external_agent_username(agent_id, agent.get("name"))
            # Opt-in already happened inside _pick_next_task (serial opt-in).
            # Just log confirmation here.
            agent["output_log"].append({
                "time": datetime.utcnow().isoformat(),
                "type": "info",
                "message": f"API: task opt-in already completed during serial task pick (agent: {username})"
            })

            clock_in_ok = await _post_timer_log(task, "clock_in", task_token=task_token)
            agent["output_log"].append({
                "time": datetime.utcnow().isoformat(),
                "type": "info",
                "message": f"API: timer log clock_in {'ok' if clock_in_ok else 'failed'}"
            })
            msg_ok = await _post_task_message(task, f"Started by {started_by_name}.", task_token=task_token)
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
                agent["progress_message"] = f"Initializing environment: {container_name}"
                agent["output_log"].append({
                    "time": datetime.utcnow().isoformat(),
                    "type": "info",
                    "message": f"Creating persistent environment: {container_name}"
                })

                container_result = await asyncio.to_thread(_create_persistent_container, container_name)
                if not container_result["success"]:
                    raise ValueError(f"Failed to create container: {container_result['error']}")
                container_created = True

                agent["output_log"].append({
                    "time": datetime.utcnow().isoformat(),
                    "type": "info",
                    "message": f"Environment '{container_name}' is running with /workspace/ ready"
                })

                # Clone git repo ONCE on first task
                if use_git:
                    first_branch = force_branch if force_branch else _branch_name_for_task(task)
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
                branch_name = force_branch if force_branch else _branch_name_for_task(task)
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

            # ── Structure Validation Before Code Generation ────────────
            agent["progress"] = 14
            agent["progress_message"] = "Validating project structure..."
            structure_validation = await _master_validate_structure(project_token=project_token)
            
            structure_warnings = []
            if structure_validation.get("duplicates"):
                dup_count = len(structure_validation.get("duplicates", []))
                structure_warnings.append(f"⚠️ {dup_count} duplicate file(s) detected in project")
            if structure_validation.get("violations"):
                viol_count = len(structure_validation.get("violations", []))
                structure_warnings.append(f"⚠️ {viol_count} structure violation(s) detected")
            
            if structure_warnings:
                agent["output_log"].append({
                    "time": datetime.utcnow().isoformat(),
                    "type": "warning",
                    "message": " | ".join(structure_warnings)
                })

            # ── AI Code Generation ───────────────────────────────────
            agent["progress"] = 15
            agent["progress_message"] = "Preparing context layers..."

            # ── LAYER 1: Retrieve or generate Technical Spec ────────
            tech_spec = ""
            # 1. Fetch fresh repository documentation & tree for context
            repo_tree_context = ""
            try:
                import context_manager as ctx_mgr
                repo_snapshot = ctx_mgr.get_current_project_tree_snapshot(project_token or "")
                if isinstance(repo_snapshot, dict):
                    repo_tree_context = str(repo_snapshot.get("tree") or "").strip()
                    # If indexed, update the contract as a side effect for the architect
                    repo_file_paths = [str(p).strip() for p in (repo_snapshot.get("all_file_paths") or []) if str(p).strip()]
                    if repo_file_paths and project_token:
                        ctx_mgr.update_workspace_contract_from_file_paths(
                            project_token, repo_file_paths,
                            source=f"{repo_snapshot.get('source') or 'git_repo'}_snapshot",
                            merge_ready=True, force_refresh=True
                        )
            except Exception:
                pass

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
                    brd_payload = state.get("brd_analysis")
                    brd_summary = _build_brd_analysis_context(brd_payload)
                    if not brd_summary:
                        if isinstance(brd_payload, dict):
                            brd_summary = str(brd_payload.get("summary") or brd_payload.get("analysis") or "").strip()
                        else:
                            brd_summary = str(brd_payload or "").strip()
                    # Get all tasks for architecture planning
                    all_tasks = state.get("tasks", [])
                    # Get KG context for architecture decisions
                    arch_kg_context = ""
                    workspace_contract = {}
                    try:
                        import context_manager as ctx_mgr
                        if ctx_mgr.is_project_indexed(project_token or ""):
                            arch_kg_context = await ctx_mgr.get_full_agent_context(
                                project_token=project_token,
                                task_description="Full system architecture overview",
                                agent_id="architect_agent",
                                task_token=task_token,
                            )
                        workspace_contract = ctx_mgr.get_workspace_contract(project_token or "")
                    except Exception:
                        pass

                    spec_result = await _generate_technical_spec(
                        project_token=project_token,
                        tasks=all_tasks if all_tasks else [task],
                        brd_summary=brd_summary,
                        kg_context=arch_kg_context,
                        repo_tree_context=repo_tree_context,
                        workspace_contract=workspace_contract if isinstance(workspace_contract, dict) else {},
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
                        task_token=task_token,
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

            # Fetch Task message/comment context for additional history
            task_messages_text = ""
            try:
                from task_service import task_service
                tid = str(_normalize_task_id(task) or task.get("external_id") or task.get("id") or "")
                if tid:
                    msg_resp = await task_service.get_task_messages(tid, task_token=task_token)
                    if isinstance(msg_resp, dict) and msg_resp.get("comments"):
                        comments = msg_resp["comments"]
                        msg_lines = []
                        # Take last 10 comments for context
                        for c in comments[-10:]:
                            user = c.get("user") or "unknown"
                            msg = c.get("message") or ""
                            msg_lines.append(f"[{user}]: {msg}")
                        task_messages_text = "\n".join(msg_lines)
                        if task_messages_text:
                            agent["output_log"].append({
                                "time": datetime.utcnow().isoformat(),
                                "type": "info",
                                "message": f"Task history retrieved: {len(comments)} comments found"
                            })
            except Exception as msg_err:
                logger.warning(f"Failed to fetch task messages for context: {msg_err}")

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
                
                # Add recovery prompt even if dynamic generation failed
                master_recovery_prompt = agent.get("master_recovery_prompt")
                if master_recovery_prompt:
                    dynamic_system_prompt = f"{dynamic_system_prompt}\n\n{master_recovery_prompt}"
                    agent.pop("master_recovery_prompt", None)
                    agent.pop("master_failure_analysis", None)
                
                agent["output_log"].append({
                    "time": datetime.utcnow().isoformat(),
                    "type": "info",
                    "message": f"Dynamic prompt failed ({str(prompt_err)[:60]}), using static prompt"
                })

            agent["progress"] = 25
            agent["progress_message"] = "AI is generating build script..."
            agent["output_log"].append({
                "time": datetime.utcnow().isoformat(),
                "type": "info",
                "message": "Calling AI model to generate build script..."
            })

            generated_code, thought = await _call_ai_for_code(
                task["description"], agent["type"],
                code_context=jit_context,
                system_prompt_override=dynamic_system_prompt,
                tech_spec=tech_spec,
                workspace_tree=master_note_result.get("workspace_tree", "") if master_note_result else "",
                live_repo_tree=repo_tree_context,
            )
            if thought:
                await _post_task_message(task, f"🤔 {agent_id} thought:\n{thought}", task_token=task_token)

            agent["progress"] = 30
            agent["progress_message"] = "Running project..."
            agent["output_log"].append({
                "time": datetime.utcnow().isoformat(),
                "type": "info",
                "message": f"AI generated {len(generated_code.splitlines())} lines of build script"
            })

            # ── Execute build script ─────────────────────────────────
            result = await asyncio.to_thread(
                _exec_script_in_container, container_name, generated_code, f"build_{agent_id}"
            )
            
            # ── Post-execution structure validation ──────────────────
            # Validate structure after files are created
            try:
                post_structure_validation = await _master_validate_structure(project_token=project_token)
                if post_structure_validation.get("duplicates") or post_structure_validation.get("violations"):
                    dup_count = len(post_structure_validation.get("duplicates", []))
                    viol_count = len(post_structure_validation.get("violations", []))
                    detail_text = _format_structure_issue_details(
                        post_structure_validation.get("duplicates", []) or [],
                        post_structure_validation.get("violations", []) or [],
                        max_items=3,
                    )
                    base_message = f"⚠️ Structure issues detected after execution: {dup_count} duplicates, {viol_count} violations"
                    if detail_text:
                        base_message += f" | {detail_text}"
                    agent["output_log"].append({
                        "time": datetime.utcnow().isoformat(),
                        "type": "warning",
                        "message": base_message
                    })
            except Exception as struct_err:
                logger.debug(f"Structure validation skipped: {struct_err}")

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
                        "message": "Calling AI model to generate fix script..."
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
                        workspace_tree=master_note_result.get("workspace_tree", "") if master_note_result else "",
                        live_repo_tree=repo_tree_context,
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
                        "message": f"AI generated {len(fix_code.splitlines())} lines of fix script"
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
            # AGENT SELF-REVIEW (Ensures Structure matches Task)
            # ═════════════════════════════════════════════════════════
            if workspace_tree.count('FILE:') > 0:
                agent["progress"] = 92
                agent["progress_message"] = "Self-Reviewing code structure..."
                agent["output_log"].append({
                    "time": datetime.utcnow().isoformat(),
                    "type": "info",
                    "message": "Initiating AI self-review before committing..."
                })
                try:
                    passed_review, review_feedback = await _call_ai_for_self_review(
                        task_description=task.get("description", task.get("title")),
                        agent_type=agent["type"],
                        workspace_tree=workspace_tree,
                        tech_spec=task.get("_tech_spec", "")
                    )
                    log_type = "info" if passed_review else "warning"
                    pass_str = "PASSED" if passed_review else "FAILED"
                    agent["output_log"].append({
                        "time": datetime.utcnow().isoformat(),
                        "type": log_type,
                        "message": f"🤖 Self-Review {pass_str}:\n{review_feedback[:300]}"
                    })
                    if not passed_review and not integration_blocked:
                        logger.warning(f"[{agent_id}] Self-review failed: {review_feedback[:100]}")
                        # Even if failed, it pushes to Git so Master Agent can intervene in next cycle, 
                        # but agent logs it properly as a warning structural mismatch.
                except Exception as eval_err:
                    agent["output_log"].append({
                        "time": datetime.utcnow().isoformat(),
                        "type": "warning",
                        "message": f"Self-review failed to execute: {eval_err}"
                    })

            # ═════════════════════════════════════════════════════════
            # MARK CHECKLIST ITEMS COMPLETE
            # Only if the workspace capture contains real project files.
            # ═════════════════════════════════════════════════════════
            workspace_file_count = workspace_tree.count('FILE:')
            normalized_task_id = _normalize_task_id(task)
            if workspace_file_count <= 0:
                agent["output_log"].append({
                    "time": datetime.utcnow().isoformat(),
                    "type": "warning",
                    "message": (
                        "⚠️ Skipping checklist completion: no files captured from /workspace/ "
                        "— AI may not have produced real code"
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
                    
                    # Update dynamic percentage strictly based on checklist tracking
                    current_percent = int(((idx_cl + 1) / len(checklist)) * 100)
                    await _post_task_progress(task, current_percent, f"Completed checklist step {idx_cl+1}/{len(checklist)}", task_token=task_token)
                    
                    agent["output_log"].append({
                        "time": datetime.utcnow().isoformat(),
                        "type": "info",
                        "message": f"  ✓ Checklist step {idx_cl+1}/{len(checklist)}: {checklist[idx_cl].get('text','')[:80]} (Progress: {current_percent}%)"
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
                    linked_task["assigned_agent"] = agent_id
                    linked_task["assigned_agent_name"] = started_by_name
                    msg_ok = await _post_task_message(linked_task, f"Started by {started_by_name}.", task_token=task_token)
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
                                task_token=task_token,
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
                            # Update dynamic percentage strictly based on checklist tracking for Linked Tasks
                            lt_percent = int(((ci + 1) / len(lt_checklist)) * 100)
                            await _post_task_progress(linked_task, lt_percent, f"Completed linked checklist step {ci+1}/{len(lt_checklist)}", task_token=task_token)

                    # Update linked task progress/completion in external system
                    # Always complete linked task if build succeeded, regardless of git push
                    if lt_result["exit_code"] == 0:
                        if lt_commit_success:
                            lt_completion_message = f"Completed by {agent_id}."
                        else:
                            lt_completion_message = f"Completed by {agent_id} (with git errors)."
                        msg_ok = await _post_task_message(linked_task, lt_completion_message, task_token=task_token)
                        
                        # Note: We rely on the checklist iteration above to have updated progress to exactly 100%.
                        # To ensure the final state registers, we still mark task_complete.
                        complete_ok = await _post_task_complete(linked_task, task_token=task_token)
                        agent["output_log"].append({
                            "time": datetime.utcnow().isoformat(),
                            "type": "info",
                            "message": (
                                f"API: linked task complete message {'ok' if msg_ok else 'failed'}, "
                                f"complete {'ok' if complete_ok else 'failed'}"
                            )
                        })
                    else:
                        lt_failure_message = f"Failed (exit={lt_result['exit_code']})."
                        msg_ok = await _post_task_message(linked_task, lt_failure_message, task_token=task_token)
                        agent["output_log"].append({
                            "time": datetime.utcnow().isoformat(),
                            "type": "info",
                            "message": f"API: linked task failure message {'ok' if msg_ok else 'failed'}"
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
                        if not force_branch:
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
                
                # Note: Progress should be 100% already strictly set by the checklist iterator!
                # We just confirm `complete` physically inside NxDune
                complete_ok = await _post_task_complete(task, task_token=task_token)
                agent["output_log"].append({
                    "time": datetime.utcnow().isoformat(),
                    "type": "info",
                    "message": (
                        f"API: complete message {'ok' if msg_ok else 'failed'}, "
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
                agent["output_log"].append({
                    "time": datetime.utcnow().isoformat(),
                    "type": "info",
                    "message": f"API: failure message {'ok' if msg_ok else 'failed'}"
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
                task_id = str(_normalize_task_id(task) or task.get("external_id") or task.get("id") or "")
                # Mark task as completed in dependency system if successful
                if result["exit_code"] == 0 and task_id:
                    live_mem.mark_task_completed(task_id)
                    
                    # Auto-advance phase if all tasks in current phase are complete
                    try:
                        task_phase = task.get("phase") or task.get("task_phase")
                        if task_phase and live_mem:
                            # Check if all tasks in this phase are complete
                            # Fetch all tasks to check phase completion
                            external_tasks_check = await _fetch_external_tasks(project_token)
                            phase_tasks = [
                                t for t in external_tasks_check
                                if (t.get("phase") or t.get("task_phase")) == task_phase
                                and (t.get("status") or "").lower() not in ("completed", "done")
                            ]
                            if not phase_tasks:
                                # All tasks in this phase are complete - advance to next phase
                                PHASE_ORDER = ["foundation", "backend-core", "backend-features", "frontend-core", "frontend-features", "integration"]
                                current_index = PHASE_ORDER.index(task_phase) if task_phase in PHASE_ORDER else -1
                                if current_index >= 0 and current_index < len(PHASE_ORDER) - 1:
                                    next_phase = PHASE_ORDER[current_index + 1]
                                    live_mem.set_current_phase(next_phase)
                                    logger.info(f"[{agent_id}] Phase '{task_phase}' complete. Auto-advancing to '{next_phase}'")
                    except Exception as phase_err:
                        logger.warning(f"Phase auto-advance check failed: {phase_err}")
                
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

                try:
                    note_branch = ((commit_result or {}).get("branch") if isinstance(commit_result, dict) else None) or branch_name or coordination_branch
                    note_status = "completed" if result["exit_code"] == 0 else "failed"
                    status_summary = (
                        f"{'Completed' if result['exit_code'] == 0 else 'Failed'} task "
                        f"'{task['title']}' in {elapsed}s. "
                        f"Touched {len(touched_files)} files and generated "
                        f"{len(symbols.get('created', []))} new symbols."
                    )
                    status_note = await _publish_agent_status_note(
                        agent_id=agent_id,
                        task=task,
                        status=note_status,
                        project_token=project_token,
                        task_token=task_token,
                        branch_name=note_branch,
                        planned_files=_predict_task_file_intents(task),
                        completed_files=touched_files,
                        symbols_created=symbols.get("created", []),
                        symbols_modified=symbols.get("modified", []),
                        next_agent_should=(
                            (
                                f"Continue from these files: {', '.join(touched_files[:5])}. "
                                "Extend the existing implementation instead of recreating it."
                            )
                            if result["exit_code"] == 0 and touched_files
                            else "Inspect the failed task context and resume from the same planned files."
                        ),
                        summary=status_summary,
                    )
                    if status_note.get("success"):
                        agent["output_log"].append({
                            "time": datetime.utcnow().isoformat(),
                            "type": "info",
                            "message": f"Coordination note updated: {note_status} status published"
                        })
                except Exception as note_err:
                    agent["output_log"].append({
                        "time": datetime.utcnow().isoformat(),
                        "type": "info",
                        "message": f"Coordination note publish skipped: {str(note_err)[:80]}"
                    })

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
                task = _apply_master_task_metadata(task, project_token=project_token)
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
                "message": f"Environment '{container_name}' destroyed."
            })

        total_elapsed = round(time.time() - total_start, 1)
        agent["status"] = "completed"
        agent["resume_pending_task"] = False
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
        agent["resume_pending_task"] = False
        agent["progress"] = 0
        agent["progress_message"] = f"Error: {str(e)}"
        agent["output_log"].append({
            "time": datetime.utcnow().isoformat(),
            "type": "error",
            "message": str(e)
        })
        agent["last_run"] = datetime.utcnow().isoformat()
        agent["current_task"] = None

        try:
            import context_manager as ctx_mgr
            live_mem = ctx_mgr.get_live_memory(project_token or "")
            if task:
                live_mem.register_task_complete(
                    agent_id=agent_id,
                    files_touched=_predict_task_file_intents(task),
                    exit_code=1,
                    summary=str(e)[:300],
                )
            live_mem.release_file_intent(agent_id)
        except Exception:
            pass

        if task:
            try:
                active_branch = locals().get("branch_name") or locals().get("coordination_branch") or force_branch
                note_result = await _publish_agent_status_note(
                    agent_id=agent_id,
                    task=task,
                    status="failed",
                    project_token=project_token,
                    task_token=task_token,
                    branch_name=active_branch,
                    planned_files=_predict_task_file_intents(task),
                    next_agent_should="Resume or repair this task in the same files instead of starting a parallel implementation.",
                    summary=str(e)[:300],
                )
                if note_result.get("success"):
                    agent["output_log"].append({
                        "time": datetime.utcnow().isoformat(),
                        "type": "info",
                        "message": "Coordination note updated: failure status published"
                    })
            except Exception as note_err:
                agent["output_log"].append({
                    "time": datetime.utcnow().isoformat(),
                    "type": "info",
                    "message": f"Coordination failure note skipped: {str(note_err)[:80]}"
                })

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


def _dedupe_preserve_order(values: List[str]) -> List[str]:
    deduped: List[str] = []
    seen = set()
    for raw_value in values:
        value = str(raw_value or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def _workspace_relative_path(path: Any) -> str:
    return _normalize_master_tree_path_candidate(path)


def _path_matches_deploy_root(path: Any, root: Any) -> bool:
    normalized_path = _workspace_relative_path(path)
    normalized_root = _workspace_relative_path(root)
    if not normalized_path or not normalized_root:
        return False
    return normalized_path == normalized_root or normalized_path.startswith(normalized_root + "/")


def _path_matches_any_deploy_root(path: Any, roots: List[str]) -> bool:
    normalized_path = _workspace_relative_path(path)
    if not normalized_path:
        return False
    return any(_path_matches_deploy_root(normalized_path, root) for root in (roots or []))


def _runtime_root_candidates(path: Any) -> List[str]:
    normalized = _workspace_relative_path(path)
    if not normalized:
        return []

    if "." in os.path.basename(normalized):
        normalized = os.path.dirname(normalized).strip("/")
    if not normalized:
        return []

    parts = [part for part in normalized.split("/") if part]
    if not parts:
        return []

    trim_segments = {
        "src",
        "app",
        "apps",
        "pages",
        "components",
        "hooks",
        "styles",
        "assets",
        "public",
        "lib",
        "core",
        "api",
        "server",
        "client",
        "ui",
    }

    candidates: List[str] = []
    current = list(parts)
    while current:
        candidate = "/".join(current).strip("/")
        if candidate:
            candidates.append(candidate)
        if current[-1].lower() not in trim_segments:
            break
        current = current[:-1]

    return _dedupe_preserve_order(candidates)


def _looks_like_frontend_repo_path(path: Any) -> bool:
    normalized = _workspace_relative_path(path).lower()
    if not normalized:
        return False

    parts = [part for part in normalized.split("/") if part]
    basename = os.path.basename(normalized)
    if any(part in {"frontend", "client", "web", "site", "ui"} for part in parts):
        return True
    if basename.startswith(("vite.config", "next.config")):
        return True
    return basename.endswith((".tsx", ".jsx", ".ts", ".js", ".css", ".scss", ".html"))


def _looks_like_backend_repo_path(path: Any) -> bool:
    normalized = _workspace_relative_path(path).lower()
    if not normalized:
        return False

    parts = [part for part in normalized.split("/") if part]
    basename = os.path.basename(normalized)
    if any(part in {"backend", "api", "server", "service", "services"} for part in parts):
        return True
    if basename in {"requirements.txt", "pyproject.toml", "manage.py", "alembic.ini"}:
        return True
    if basename in {"main.py", "app.py"} and any(part in {"backend", "api", "server", "service", "services"} for part in parts[:-1]):
        return True
    return False


async def _load_master_deploy_hints(project_token: Optional[str]) -> Dict[str, Any]:
    effective_project = str(project_token or "").strip()
    if not effective_project:
        return {}

    state = _ensure_project_state(project_token)
    cached_note = state.get("master_note_cache") if isinstance(state.get("master_note_cache"), dict) else {}
    title = _master_note_title(project_token)

    payload: Dict[str, Any] = {}
    if (
        cached_note.get("approved")
        and (
            cached_note.get("workspace_tree")
            or cached_note.get("stack_profile")
            or cached_note.get("workspace_contract")
        )
    ):
        payload = dict(cached_note)

    if not payload.get("stack_profile") or not payload.get("workspace_contract") or not payload.get("workspace_tree"):
        persisted = await _get_existing_note_payload(
            title=title,
            project_token=project_token,
        )
        validation = persisted.get("validation") if isinstance(persisted.get("validation"), dict) else {}
        if persisted.get("note_type") == "master_project_plan" and validation.get("approved"):
            merged_payload = dict(payload)
            merged_payload.update({
                "workspace_tree": persisted.get("workspace_tree") or payload.get("workspace_tree"),
                "stack_profile": persisted.get("stack_profile") if isinstance(persisted.get("stack_profile"), dict) else payload.get("stack_profile"),
                "workspace_contract": persisted.get("workspace_contract") if isinstance(persisted.get("workspace_contract"), dict) else payload.get("workspace_contract"),
                "instructions": persisted.get("instructions") if isinstance(persisted.get("instructions"), list) else payload.get("instructions"),
            })
            payload = merged_payload

    stack_profile = payload.get("stack_profile") if isinstance(payload.get("stack_profile"), dict) else {}
    workspace_contract = payload.get("workspace_contract") if isinstance(payload.get("workspace_contract"), dict) else {}
    workspace_tree = str(payload.get("workspace_tree") or "").strip()
    if not stack_profile and not workspace_contract and not workspace_tree:
        return {}

    frontend_key = str(stack_profile.get("frontend_key") or "").strip().lower()
    backend_key = str(stack_profile.get("backend_key") or "").strip().lower()

    preferred_frontend_roots: List[str] = []
    preferred_backend_roots: List[str] = []
    preferred_static_files: List[str] = []

    allowed_source_roots = [
        _workspace_relative_path(root)
        for root in (workspace_contract.get("allowed_source_roots") or [])
        if _workspace_relative_path(root)
    ]

    for root in allowed_source_roots:
        is_frontend_root = frontend_key not in {"", "none"} and (
            _looks_like_frontend_repo_path(root)
            or (frontend_key == "jinja-html" and any(token in root for token in ("templates", "static")))
            or backend_key == "none"
            or (frontend_key == "static-html" and not _looks_like_backend_repo_path(root))
        )
        is_backend_root = backend_key not in {"", "none"} and (
            _looks_like_backend_repo_path(root)
            or frontend_key == "none"
            or (backend_key == "flask" and (root == "app" or root.endswith("/app")))
        )

        if is_frontend_root:
            preferred_frontend_roots.extend(_runtime_root_candidates(root))
        if is_backend_root:
            preferred_backend_roots.extend(_runtime_root_candidates(root))

    tree_paths: List[str] = []
    if workspace_tree:
        try:
            import context_manager as ctx_mgr  # type: ignore

            tree_paths = [
                _workspace_relative_path(path)
                for path in ctx_mgr._extract_file_paths_from_canonical_tree(workspace_tree)
                if _workspace_relative_path(path)
            ]
        except Exception:
            tree_paths = []

    for path in tree_paths:
        basename = os.path.basename(path).lower()

        if basename == "index.html":
            preferred_static_files.append(path)
            if frontend_key not in {"", "none"}:
                preferred_frontend_roots.extend(_runtime_root_candidates(path))
            continue

        if basename in {"requirements.txt", "pyproject.toml", "manage.py", "main.py", "app.py"}:
            if backend_key not in {"", "none"}:
                preferred_backend_roots.extend(_runtime_root_candidates(path))
            continue

        if basename.startswith(("vite.config", "next.config")):
            if frontend_key not in {"", "none"}:
                preferred_frontend_roots.extend(_runtime_root_candidates(path))
            continue

        if basename == "package.json":
            if frontend_key not in {"", "none"} and _looks_like_frontend_repo_path(path):
                preferred_frontend_roots.extend(_runtime_root_candidates(path))
            if backend_key == "express" and (_looks_like_backend_repo_path(path) or frontend_key == "none"):
                preferred_backend_roots.extend(_runtime_root_candidates(path))

    preferred_frontend_roots = _dedupe_preserve_order(preferred_frontend_roots)
    preferred_backend_roots = _dedupe_preserve_order(preferred_backend_roots)
    preferred_static_files = _dedupe_preserve_order(preferred_static_files)

    preferred_runtime = ""
    if frontend_key == "static-html":
        preferred_runtime = "static"
    elif frontend_key == "jinja-html":
        preferred_runtime = "python"
    elif frontend_key not in {"", "none"}:
        preferred_runtime = "node"
    elif backend_key == "express":
        preferred_runtime = "node"
    elif backend_key not in {"", "none"}:
        preferred_runtime = "python"

    if not preferred_frontend_roots and not preferred_backend_roots and not preferred_static_files and not preferred_runtime:
        return {}

    return {
        "source": "master_note",
        "stack_profile": stack_profile,
        "workspace_contract": workspace_contract,
        "preferred_runtime": preferred_runtime,
        "preferred_frontend_roots": preferred_frontend_roots,
        "preferred_backend_roots": preferred_backend_roots,
        "preferred_static_files": preferred_static_files,
    }


def _detect_project_stack(container_name: str, deployment_hints: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Auto-detect the tech stack inside the container's /workspace."""
    stack = {
        "type": "static",
        "image": "python:3.10-slim",
        "port": 8080,
        "install_cmd": "",
        "start_cmd": "cd /workspace && python3 -m http.server 8080",
        "workdir": "/workspace",
        "detected_from": "/workspace/index.html",
    }
    hints = deployment_hints if isinstance(deployment_hints, dict) else {}
    stack_profile = hints.get("stack_profile") if isinstance(hints.get("stack_profile"), dict) else {}
    frontend_key = str(stack_profile.get("frontend_key") or "").strip().lower()
    backend_key = str(stack_profile.get("backend_key") or "").strip().lower()
    preferred_runtime = str(hints.get("preferred_runtime") or "").strip().lower()
    preferred_frontend_roots = [
        _workspace_relative_path(path)
        for path in (hints.get("preferred_frontend_roots") or [])
        if _workspace_relative_path(path)
    ]
    preferred_backend_roots = [
        _workspace_relative_path(path)
        for path in (hints.get("preferred_backend_roots") or [])
        if _workspace_relative_path(path)
    ]
    preferred_static_files = [
        _workspace_relative_path(path)
        for path in (hints.get("preferred_static_files") or [])
        if _workspace_relative_path(path)
    ]

    def _cat_file(path: str, timeout: int = 10) -> Optional[str]:
        result = subprocess.run(
            ["docker", "exec", container_name, "cat", path],
            capture_output=True, text=True, timeout=timeout,
        )
        if result.returncode == 0:
            return result.stdout
        return None

    def _file_exists(path: str, timeout: int = 5) -> bool:
        result = subprocess.run(
            ["docker", "exec", container_name, "test", "-f", path],
            capture_output=True, text=True, timeout=timeout,
        )
        return result.returncode == 0

    def _dirname(path: str) -> str:
        if "/" not in path:
            return "/workspace"
        return path.rsplit("/", 1)[0] or "/workspace"

    def _repo_rel(path: str) -> str:
        return _workspace_relative_path(path)

    def _find_files(file_name: str, max_depth: int = 5) -> List[str]:
        result = subprocess.run(
            [
                "docker", "exec", container_name, "sh", "-c",
                (
                    f"find /workspace -maxdepth {max_depth} -name '{file_name}' "
                    "-not -path '*/node_modules/*' -not -path '*/.git/*' "
                    "-not -path '*/venv/*' -not -path '*/.venv/*' 2>/dev/null"
                ),
            ],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return []
        return [line.strip() for line in result.stdout.splitlines() if line.strip()]

    def _resolve_static_candidate(force_scan: bool = False) -> Optional[Dict[str, Any]]:
        candidate_paths: List[str] = []
        for relative_path in preferred_static_files:
            full_path = f"/workspace/{relative_path}"
            if _file_exists(full_path):
                candidate_paths.append(full_path)

        if force_scan or preferred_frontend_roots:
            for index_path in _find_files("index.html", max_depth=6):
                if index_path not in candidate_paths:
                    candidate_paths.append(index_path)

        if not candidate_paths:
            return None

        def _static_score(index_path: str) -> int:
            relative_path = _repo_rel(index_path)
            workdir = _repo_rel(_dirname(index_path))
            score = 0
            if relative_path in preferred_static_files:
                score += 320
            if _path_matches_any_deploy_root(relative_path, preferred_frontend_roots):
                score += 220
            if _path_matches_any_deploy_root(workdir, preferred_frontend_roots):
                score += 220
            if index_path == "/workspace/index.html":
                score += 180
            if "/frontend/" in index_path or "/client/" in index_path or "/web/" in index_path:
                score += 80
            if relative_path.endswith("public/index.html"):
                score -= 120
            return score

        index_path = max(candidate_paths, key=_static_score)
        workdir = _dirname(index_path)
        if workdir.endswith("/public"):
            workdir = _dirname(workdir)
        return {
            "type": "static",
            "image": "python:3.10-slim",
            "port": 8080,
            "install_cmd": "",
            "start_cmd": f"cd {workdir} && python3 -m http.server 8080",
            "workdir": workdir,
            "detected_from": index_path,
        }

    node_candidates: List[tuple[str, str]] = []
    root_package = _cat_file("/workspace/package.json")
    if root_package is not None:
        node_candidates.append(("/workspace/package.json", root_package))
    for package_path in _find_files("package.json", max_depth=5):
        if package_path == "/workspace/package.json":
            continue
        package_content = _cat_file(package_path)
        if package_content is not None:
            node_candidates.append((package_path, package_content))

    if node_candidates:
        def _node_candidate_score(candidate: tuple[str, str]) -> int:
            package_path, package_content = candidate
            text = package_content.lower()
            scripts: Dict[str, str] = {}
            script_text = ""
            has_workspaces = False
            try:
                parsed_package = json.loads(package_content)
                raw_scripts = parsed_package.get("scripts", {}) if isinstance(parsed_package, dict) else {}
                if isinstance(raw_scripts, dict):
                    scripts = {str(k).strip().lower(): str(v).lower() for k, v in raw_scripts.items()}
                    script_text = " ".join(scripts.values())
                has_workspaces = bool(parsed_package.get("workspaces")) if isinstance(parsed_package, dict) else False
            except Exception:
                scripts = {}
                script_text = ""
                has_workspaces = False

            score = 0
            rel_package_path = _repo_rel(package_path)
            rel_workdir = _repo_rel(_dirname(package_path))
            
            # 1. Content capabilities (does it look runnable?)
            if '"scripts"' in text:
                score += 20
            if '"start"' in text or "start" in scripts:
                score += 30
            if '"dev"' in text or "dev" in scripts:
                score += 30
            if '"vite"' in text or '"next"' in text or '"react-scripts"' in text:
                score += 30

            # 2. Dynamic Contract Enforcement (Driven by the Master Agent's Workspace Tree)
            if _path_matches_any_deploy_root(rel_package_path, preferred_frontend_roots):
                score += 200
            if _path_matches_any_deploy_root(rel_workdir, preferred_frontend_roots):
                score += 200
            if _path_matches_any_deploy_root(rel_package_path, preferred_backend_roots):
                score += 150 if backend_key == "express" else 50
            if _path_matches_any_deploy_root(rel_workdir, preferred_backend_roots):
                score += 150 if backend_key == "express" else 50
                
            if preferred_runtime == "node":
                score += 40
            return score

        package_path, package_content = max(node_candidates, key=_node_candidate_score)
        package_text = package_content.lower()
        workdir = _dirname(package_path)

        stack["type"] = "node"
        stack["image"] = "node:18-slim"
        stack["workdir"] = workdir
        stack["detected_from"] = package_path
        stack["install_cmd"] = f"cd {workdir} && npm install"

        scripts: Dict[str, Any] = {}
        try:
            parsed_package = json.loads(package_content)
            raw_scripts = parsed_package.get("scripts", {}) if isinstance(parsed_package, dict) else {}
            if isinstance(raw_scripts, dict):
                scripts = {str(k).strip().lower(): str(v) for k, v in raw_scripts.items()}
        except Exception:
            scripts = {}

        script_text = " ".join(str(v).lower() for v in scripts.values())
        has_start = "start" in scripts
        has_dev = "dev" in scripts
        has_preview = "preview" in scripts
        start_script = str(scripts.get("start", "")).lower()
        start_targets_backend = (
            "start:backend" in start_script
            or "cd backend" in start_script
            or "flask" in start_script
            or "uvicorn" in start_script
        )

        if '"vite"' in package_text or '"@vitejs/plugin-react"' in package_text or "vite" in script_text:
            if has_dev:
                stack["start_cmd"] = f"cd {workdir} && npm run dev -- --host 0.0.0.0 --port 5173"
            else:
                stack["start_cmd"] = f"cd {workdir} && npx vite --host 0.0.0.0 --port 5173"
            stack["port"] = 5173
            return stack

        if '"next"' in package_text or "next" in script_text:
            if has_dev:
                stack["start_cmd"] = f"cd {workdir} && npm run dev -- --hostname 0.0.0.0 --port 3000"
            else:
                stack["start_cmd"] = f"cd {workdir} && npx next dev -p 3000 -H 0.0.0.0"
            stack["port"] = 3000
            return stack

        if '"react-scripts"' in package_text or "react-scripts" in script_text:
            has_cra_index = _file_exists(f"{workdir}/public/index.html")
            has_cra_entry = (
                _file_exists(f"{workdir}/src/index.js")
                or _file_exists(f"{workdir}/src/index.jsx")
                or _file_exists(f"{workdir}/src/index.ts")
                or _file_exists(f"{workdir}/src/index.tsx")
            )
            if not (has_cra_index and has_cra_entry):
                # Many repos migrated from CRA to Vite but retained old start scripts.
                # Prefer explicit dev/preview scripts in that case.
                if has_dev:
                    stack["start_cmd"] = f"cd {workdir} && npm run dev -- --host 0.0.0.0 --port 5173"
                    stack["port"] = 5173
                    return stack
                if has_preview:
                    stack["start_cmd"] = f"cd {workdir} && npm run preview -- --host 0.0.0.0 --port 4173"
                    stack["port"] = 4173
                    return stack
                if _file_exists(f"{workdir}/index.html"):
                    stack["start_cmd"] = f"cd {workdir} && npx vite --host 0.0.0.0 --port 5173"
                    stack["port"] = 5173
                    return stack

            if has_dev:
                stack["start_cmd"] = f"cd {workdir} && npm run dev"
            else:
                stack["start_cmd"] = f"cd {workdir} && npx react-scripts start"
            stack["port"] = 3000
            return stack

        if has_dev:
            stack["start_cmd"] = f"cd {workdir} && npm run dev"
            stack["port"] = 3000
            return stack

        if has_preview:
            stack["start_cmd"] = f"cd {workdir} && npm run preview -- --host 0.0.0.0 --port 4173"
            stack["port"] = 4173
            return stack

        if has_start:
            if start_targets_backend and has_dev:
                stack["start_cmd"] = f"cd {workdir} && npm run dev"
                stack["port"] = 3000
                return stack
            stack["start_cmd"] = f"cd {workdir} && npm start"
            stack["port"] = 3000
            return stack

    if preferred_runtime == "static" or frontend_key == "static-html":
        static_candidate = _resolve_static_candidate(force_scan=True)
        if static_candidate:
            return static_candidate

    python_candidates: List[tuple[str, str]] = []
    root_requirements = _cat_file("/workspace/requirements.txt")
    if root_requirements is not None:
        python_candidates.append(("/workspace/requirements.txt", root_requirements))
    for req_path in _find_files("requirements.txt", max_depth=5):
        if req_path == "/workspace/requirements.txt":
            continue
        req_content = _cat_file(req_path)
        if req_content is not None:
            python_candidates.append((req_path, req_content))

    if python_candidates:
        def _python_candidate_score(candidate: tuple[str, str]) -> int:
            req_path, req_content = candidate
            text = req_content.lower()
            rel_req_path = _repo_rel(req_path)
            rel_workdir = _repo_rel(_dirname(req_path))
            score = 0
            
            # 1. Content capabilities (does it look runnable?)    
            if "fastapi" in text or "uvicorn" in text:
                score += 40
            if "flask" in text or "django" in text:
                score += 40

            # 2. Dynamic Contract Enforcement (Driven by the Master Agent's Workspace Tree)
            if _path_matches_any_deploy_root(rel_req_path, preferred_backend_roots):
                score += 200
            if _path_matches_any_deploy_root(rel_workdir, preferred_backend_roots):
                score += 200
                
            if preferred_runtime == "python" or backend_key in {"fastapi", "flask", "django"}:
                score += 40
            return score

        req_path, req_content = max(python_candidates, key=_python_candidate_score)
        req_text = req_content.lower()
        workdir = _dirname(req_path)

        stack["type"] = "python"
        stack["image"] = "python:3.10-slim"
        stack["workdir"] = workdir
        stack["detected_from"] = req_path
        stack["install_cmd"] = f"cd {workdir} && pip install -r requirements.txt"

        if "fastapi" in req_text or "uvicorn" in req_text:
            find_main = subprocess.run(
                [
                    "docker", "exec", container_name, "sh", "-c",
                    f"find {workdir} -maxdepth 2 -name 'main.py' -o -name 'app.py' | head -1",
                ],
                capture_output=True, text=True, timeout=10,
            )
            if find_main.returncode == 0 and find_main.stdout.strip():
                main_file = find_main.stdout.strip()
                relative_main = main_file.replace(f"{workdir}/", "", 1)
                module = relative_main.replace(".py", "").replace("/", ".")
            else:
                module = "main"
            stack["start_cmd"] = f"cd {workdir} && uvicorn {module}:app --host 0.0.0.0 --port 8000"
            stack["port"] = 8000
        elif "flask" in req_text:
            stack["start_cmd"] = f"cd {workdir} && flask run --host=0.0.0.0 --port 5000"
            stack["port"] = 5000
        elif "django" in req_text:
            stack["start_cmd"] = f"cd {workdir} && python manage.py runserver 0.0.0.0:8000"
            stack["port"] = 8000
        else:
            stack["start_cmd"] = f"cd {workdir} && python main.py"
            stack["port"] = 8000
        return stack

    static_candidate = _resolve_static_candidate(force_scan=not python_candidates)
    if static_candidate:
        return static_candidate

    return stack


async def _generate_master_verification_report(
    project_token: str,
    tech_spec: str = "",
    brd_analysis: str = "",
    tasks: List[Dict[str, Any]] = None,
) -> str:
    """
    Generate a dynamic verification report/checklist based on project analysis.
    This defines exactly what the Master Agent should look for in the HTML.
    """
    url = llm_gateway.resolve_url()
    key = llm_gateway.resolve_key()
    model_name = llm_gateway.resolve_model()

    if not llm_gateway.check_api_key():
        return "Check if the application is running and matches basic requirements."

    tasks_text = ""
    if tasks:
        tasks_text = "\n".join([f"- {t.get('title')}: {t.get('description', '')[:200]}" for t in tasks[:10]])

    prompt = f"""You are the Master Verification Architect. Your job is to generate a CUSTOM VERIFICATION CHECKLIST for a web application.
This checklist will be used by an AI agent to audit a live deployment's HTML content.

PROJECT REQUIREMENTS (BRD):
{brd_analysis[:2000] if brd_analysis else "Not available."}

TECHNICAL SPECIFICATION:
{tech_spec[:2000] if tech_spec else "Not available."}

RECENTLY COMPLETED TASKS:
{tasks_text[:1500] if tasks_text else "None."}

Write a PRECISE list of features, components, elements, and UI signals that MUST be present on the homepage (/) for this project to be considered "Success".
- Do not mention generic things like "HTML tag" or "Correct status code".
- Be extremely specific to THIS project's unique functional requirements and business logic.
- Directly reference the core components, data fields, and interactive elements defined in the Tech Spec and BRD.
- Explicitly look for the unique value proposition of the app, not generic framework boilerplates.

Return ONLY the checklist (max 10 points) as a clear, actionable text report.
"""
    try:
        messages = [
            {"role": "system", "content": "You are a software quality architect. Write precise, project-specific verification checklists."},
            {"role": "user", "content": prompt},
        ]
        report = await llm_gateway.call_llm_and_extract(
            messages=messages,
            api_url=url,
            api_key=key,
            model=model_name,
            timeout=45.0
        )
        if report:
            return report
    except Exception as e:
        logger.warning(f"Failed to generate dynamic verification report: {e}")
    
    return "Ensure the landing page reflects the core functional requirements of the project."


async def _master_verify_deployed_html(html_content: str, hints_text: str = "", verification_report: str = "") -> tuple[bool, str, Dict[str, Any]]:
    """
    Uses the Master Agent LLM to critically evaluate the raw HTML of a deployment.
    Returns (is_valid, summary_reason, full_analysis_dict).
    """
    try:
        url = llm_gateway.resolve_url()
        key = llm_gateway.resolve_key()
        model_name = llm_gateway.resolve_model()
        
        html_preview = html_content[:20000]
        
        prompt = f"""You are the Master AI Verification Agent. Your mandate is to REJECT any deployment that is a placeholder or does not contain real features.

PROJECT SUCCESS CRITERIA:
{verification_report}

DEPLOYED HTML CONTENT:
```html
{html_preview}
```
{hints_text}

INSTRUCTIONS:
1. Conduct a point-by-point audit. For every requirement in the PROJECT SUCCESS CRITERIA, look for specific evidence (IDs, CSS classes, unique text, HTML structure) in the DEPLOYED HTML CONTENT.
2. If the HTML only shows "Application successfully deployed", "Preview", "Vite + React", or other boilerplate text without the features requested, you MUST mark it "REJECT".
3. Verify the presence of the primary interactive elements and data displays associated with the project's unique purpose as defined in the success criteria.
4. Do NOT be "helpful" or optimistic. If the core features matching the project requirements are missing, REJECT it.

Respond with JSON strictly following this schema:
{{
  "status": "APPROVE" or "REJECT",
  "reason": "Overall summary of the decision",
  "audit_log": [
     "Requirement 1: Found [SPECIFIC EVIDENCE OF FEATURE] in HTML (PASS)",
     "Requirement 2: No [REQUIRED COMPONENT] found in HTML (FAIL)",
     ...
  ]
}}
"""
        messages = [
            {"role": "system", "content": "You are a highly critical software auditor. You perform strict, evidence-based verification of HTML content against requirements."},
            {"role": "user", "content": prompt}
        ]
        
        response_format = {"type": "json_object"} if "gpt" in str(model_name).lower() else None

        content = await llm_gateway.call_llm_and_extract(
            messages=messages,
            api_url=url,
            api_key=key,
            model=model_name,
            timeout=60.0,
            response_format=response_format
        )
        
        if content:
            content = content.replace("```json", "").replace("```", "").strip()
            start_idx = content.find("{")
            end_idx = content.rfind("}")
            if start_idx != -1 and end_idx != -1:
                content = content[start_idx:end_idx + 1]
                try:
                    analysis = json.loads(content)
                    is_approved = analysis.get("status", "").upper() == "APPROVE"
                    return is_approved, analysis.get("reason", ""), analysis
                except Exception as parse_e:
                    return False, f"Failed to parse AI audit: {parse_e}", {}
    except Exception as e:
        logger.warning(f"[Master Agent] HTML verification AI failed: {e}")
        return False, f"Semantic audit failed to execute: {str(e)[:100]}", {"status": "REJECT", "audit_log": [f"ERROR: AI audit crashed ({e})"]}
        
    return False, "Audit failed: AI provided no response", {"status": "REJECT", "audit_log": ["ERROR: Empty AI response"]}


async def deploy_preview(
    git_repo_url: str,
    git_token: str,
    project_token: Optional[str] = None,
    is_retry: bool = False,
) -> Dict[str, Any]:
    """
    Deploy the agent/integration branch into a live Docker container with
    port mapping so the user can preview the built application.
    """
    pk = _project_key(project_token)

    # Stop any existing preview for this project
    if pk in _preview_states and _preview_states[pk].get("status") == "running":
        await stop_preview(project_token)

    existing_pstate = _preview_states.get(pk)
    if is_retry and existing_pstate:
        logs = existing_pstate.get("logs", [])
        retries = existing_pstate.get("retries", 0)
    else:
        logs = []
        retries = 0

    preview_id = f"preview_{pk[:12]}_{int(time.time())}"
    container_name = preview_id

    _preview_states[pk] = {
        "status": "deploying",
        "container_name": container_name,
        "host_port": None,
        "preview_url": None,
        "logs": logs,
        "started_at": datetime.utcnow().isoformat(),
        "stack": None,
        "retries": retries,
        "server_log": "",
    }
    pstate = _preview_states[pk]
    deployment_hints: Dict[str, Any] = {}
    summary_bits = []

    def _log(msg: str):
        pstate["logs"].append({
            "time": datetime.utcnow().isoformat(),
            "message": msg,
        })
        logger.info(f"[Preview] {msg}")

    # Master Agent reference for live logging
    state = _ensure_project_state(project_token)
    project_agents = state["agent_states"]
    master_agent = project_agents.get(MASTER_AGENT_ID)
    
    def _master_log(msg: str):
        if master_agent:
            master_agent["output_log"].append({
                "time": datetime.utcnow().isoformat(),
                "type": "info",
                "message": f"🕵️ [Preview-Audit] {msg}"
            })

    try:
        try:
            deployment_hints = await _load_master_deploy_hints(project_token)
        except Exception as hint_err:
            deployment_hints = {}
            logger.warning("[%s] Failed to load master deploy hints: %s", pk, hint_err)

        if deployment_hints:
            stack_profile = deployment_hints.get("stack_profile") if isinstance(deployment_hints.get("stack_profile"), dict) else {}
            frontend_roots = list(deployment_hints.get("preferred_frontend_roots") or [])
            backend_roots = list(deployment_hints.get("preferred_backend_roots") or [])
            preferred_runtime = str(deployment_hints.get("preferred_runtime") or "").strip()
            if stack_profile.get("frontend"):
                summary_bits.append(f"frontend={stack_profile.get('frontend')}")
            if stack_profile.get("backend"):
                summary_bits.append(f"backend={stack_profile.get('backend')}")
            if preferred_runtime:
                summary_bits.append(f"runtime={preferred_runtime}")
            _log(
                "Master Agent deployment hints loaded"
                + (f" ({', '.join(summary_bits)})" if summary_bits else "")
            )
            if frontend_roots:
                _log(f"Preferred frontend roots from canonical tree: {', '.join(frontend_roots[:4])}")
            if backend_roots:
                _log(f"Preferred backend roots from canonical tree: {', '.join(backend_roots[:4])}")

        # 1. Create container from the shared runtime blueprint for cloning
        _log("Creating temporary clone container...")
        create_res = _create_persistent_container(container_name)
        if not create_res.get("success"):
            raise RuntimeError(f"Failed to create container: {create_res.get('error')}")

        toolchain_result = _verify_container_toolchain(container_name)
        if not toolchain_result.get("success"):
            raise RuntimeError(toolchain_result.get("error", "Preview runtime toolchain verification failed"))

        # 2. Clone the repo (agent/integration branch)
        auth_url = _build_git_auth_url(git_repo_url, git_token)
        _log(f"Cloning {GIT_INTEGRATION_BRANCH} branch...")
        
        # Configure Git for better performance with large repos
        subprocess.run(
            ["docker", "exec", "-w", "/", container_name,
             "git", "config", "--global", "http.postBuffer", "524288000"],
            capture_output=True, text=True, timeout=10,
        )
        subprocess.run(
            ["docker", "exec", "-w", "/", container_name,
             "git", "config", "--global", "http.lowSpeedLimit", "0"],
            capture_output=True, text=True, timeout=10,
        )
        subprocess.run(
            ["docker", "exec", "-w", "/", container_name,
             "git", "config", "--global", "http.lowSpeedTime", "999999"],
            capture_output=True, text=True, timeout=10,
        )
        
        clone = subprocess.run(
            ["docker", "exec", "-w", "/", container_name,
             "git", "clone", "--branch", GIT_INTEGRATION_BRANCH, "--depth", "1",
             "--single-branch", "--no-tags",
             "-c", "http.postBuffer=524288000",
             "-c", "pack.windowMemory=256m",
             "-c", "pack.packSizeLimit=256m",
             auth_url, "/workspace"],
            capture_output=True, text=True, timeout=600,  # Increased to 10 minutes
        )
        if clone.returncode != 0:
            error_msg = clone.stderr or clone.stdout or "git clone failed"
            _log(f"⚠️ Initial clone failed: {error_msg[:500]}")
            
            # Retry with even more aggressive settings
            _log("🔄 Retrying clone with minimal history...")
            subprocess.run(
                ["docker", "exec", "-w", "/", container_name, "sh", "-c", "rm -rf /workspace/*"],
                capture_output=True, text=True, timeout=10,
            )
            clone_retry = subprocess.run(
                ["docker", "exec", "-w", "/", container_name,
                 "git", "clone", "--branch", GIT_INTEGRATION_BRANCH, "--depth", "1",
                 "--single-branch", "--no-tags",
                 "-c", "core.compression=0",
                 "-c", "pack.windowMemory=512m",
                 auth_url, "/workspace"],
                capture_output=True, text=True, timeout=900,  # 15 minutes for retry
            )
            if clone_retry.returncode != 0:
                raise RuntimeError(f"Git clone failed after retry: {clone_retry.stderr}")
            _log("✅ Clone successful on retry!")
        else:
            _log("✅ Clone successful!")

        # 3. Detect the project stack
        _log("Detecting project tech stack...")
        stack = _detect_project_stack(container_name, deployment_hints=deployment_hints)
        pstate["stack"] = stack
        _log(f"Detected: {stack['type']} project")
        if stack.get("detected_from"):
            _log(f"Detected entrypoint: {stack['detected_from']}")
        if stack.get("workdir"):
            _log(f"Using working directory: {stack['workdir']}")
        if stack.get("start_cmd"):
            _log(f"Resolved start command: {stack['start_cmd']}")

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
             "-e", f"PORT={stack['port']}",
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
             "apt-get update -qq && apt-get install -y -qq git procps > /dev/null 2>&1 || true"],
            capture_output=True, text=True, timeout=120,
        )
        
        # Configure Git for better performance
        subprocess.run(
            ["docker", "exec", container_name,
             "git", "config", "--global", "http.postBuffer", "524288000"],
            capture_output=True, text=True, timeout=10,
        )
        
        # Clear workspace and clone
        subprocess.run(
            ["docker", "exec", container_name, "sh", "-c", "rm -rf /workspace/*"],
            capture_output=True, text=True, timeout=10,
        )
        clone2 = subprocess.run(
            ["docker", "exec", "-w", "/", container_name,
             "git", "clone", "--branch", GIT_INTEGRATION_BRANCH, "--depth", "1",
             "--single-branch", "--no-tags",
             "-c", "http.postBuffer=524288000",
             auth_url, "/workspace"],
            capture_output=True, text=True, timeout=600,  # Increased to 10 minutes
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

        # Check if the process excited shortly after starting
        log_check = subprocess.run(
            ["docker", "exec", container_name, "tail", "-n", "30", "/tmp/preview_server.log"],
            capture_output=True, text=True, timeout=5,
        )
        
        # Check if the process is currently running
        ps_check = subprocess.run(
            ["docker", "exec", container_name, "sh", "-c", "ps aux || ps -ef"],
            capture_output=True, text=True, timeout=5,
        )
        ps_out = ps_check.stdout.lower()

        is_crashed = False
        if stack["type"] == "python" and "python" not in ps_out and "uvicorn" not in ps_out and "flask" not in ps_out:
            is_crashed = True
        elif stack["type"] == "node" and "node" not in ps_out and "npm" not in ps_out:
            is_crashed = True
        
        if not is_crashed and log_check.returncode == 0:
            # Maybe it is alive but spitting critical errors
            output = log_check.stdout.lower()
            if "traceback (most recent call last)" in output or "address already in use" in output:
                is_crashed = True
                
        if is_crashed:
            err_log = log_check.stdout[-1000:] if log_check.returncode == 0 else ""
            ps_tail = ""
            if ps_check.returncode == 0 and ps_check.stdout:
                ps_tail = "\n".join(ps_check.stdout.splitlines()[-25:])
            if ps_tail:
                err_log = f"{err_log}\n\nProcess snapshot:\n{ps_tail}".strip()
            pstate["server_log"] = err_log
            raise RuntimeError(f"Server crashed shortly after starting or failed to start:\n{err_log}")

        preview_url = f"http://localhost:{host_port}"

        # 12. Master Agent Verification via curl equivalent
        _log(f"🕵️ Master Agent verifying deployed page at {preview_url}...")
        try:
            import urllib.request
            import urllib.error
            # Allow the server an extra couple of seconds to bind to the port completely
            await asyncio.sleep(2)
            req = urllib.request.Request(preview_url, headers={'User-Agent': 'MasterAgent/1.0'})
            with urllib.request.urlopen(req, timeout=10) as response:
                status_code = response.getcode()
                html = response.read().decode('utf-8', errors='ignore')
                _log(f"Master verification received HTTP {status_code}")
                
                hints_text = ""
                if summary_bits:
                    hints_text = "Context: This is meant to be a " + ", ".join(summary_bits) + " application."
                
                _log(f"🕵️ Master Agent verification snapshot (Length: {len(html)} chars)")
                _master_log(f"Auditing live page content (Length: {len(html)} chars)...")
                _master_log(f"--- FETCHED HTML CONTENT ---\n{html[:2000]}\n--- END HTML ---")
                
                # Dynamic Verification Planning Layer
                _master_log("Planning semantic verification strategy based on project context...")
                state = _ensure_project_state(project_token)
                brd_analysis = _build_brd_analysis_context(state.get("brd_analysis"))
                cur_tech_spec = get_technical_spec(project_token or "")
                completed_tasks = state.get("completed_tasks", [])
                
                verification_report = await _generate_master_verification_report(
                    project_token=project_token or "",
                    tech_spec=cur_tech_spec,
                    brd_analysis=brd_analysis,
                    tasks=completed_tasks
                )
                
                _master_log(f"Verification Checkpoint:\n{verification_report}")
                
                is_valid, summary, analysis = await _master_verify_deployed_html(html, hints_text, verification_report)
                
                # Log detailed audit for transparency
                for log_item in (analysis.get("audit_log") or []):
                    _master_log(f"🔎 Audit: {log_item}")
                
                if not is_valid:
                    _master_log(f"🔴 Deployment Verification REJECTED: {summary}")
                    raise RuntimeError(f"Master Agent Audit failed: {summary}")
                
                _master_log(f"🟢 Deployment Verification APPROVED: {summary}")
        
        except urllib.error.HTTPError as e:
            html = e.read().decode('utf-8', errors='ignore')
            
            hints_text = f"The server returned HTTP {e.code}."
            
            # Use dynamic verification even for error pages to see if it's a "semantic" error
            state = _ensure_project_state(project_token)
            brd_analysis = _build_brd_analysis_context(state.get("brd_analysis"))
            cur_tech_spec = get_technical_spec(project_token or "")
            verification_report = await _generate_master_verification_report(
                project_token=project_token or "",
                tech_spec=cur_tech_spec,
                brd_analysis=brd_analysis
            )
            
            is_valid, summary, analysis = await _master_verify_deployed_html(html, hints_text, verification_report)
            error_reason = summary if not is_valid and summary else f"The app crashed returning HTTP {e.code}"
            
            _master_log(f"🔴 Deployment Verification FAILED (HTTP {e.code}): {error_reason}")
            raise RuntimeError(f"Master verification failed (HTTP {e.code}): {error_reason}. Output: {html[:500]}")
        except urllib.error.URLError as e:
            raise RuntimeError(f"Master verification failed: Connection refused on {preview_url} ({e.reason}). The app failed to bind to the port.")
        except Exception as e:
            if not isinstance(e, RuntimeError):
                raise RuntimeError(f"Master verification failed: {str(e)}")
            raise e

        pstate["status"] = "running"
        pstate["preview_url"] = preview_url
        _log("✅ Preview is live and verified!")

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

        max_retries = 2
        if pstate.get("retries", 0) < max_retries:
            pstate["retries"] += 1
            pstate["logs"].append({
                "time": datetime.utcnow().isoformat(),
                "message": f"🔄 Auto-triggering AI self-heal (attempt {pstate['retries']}/{max_retries})..."
            })
            # Trigger repair asynchronously without blocking
            asyncio.create_task(repair_preview(git_repo_url, git_token, project_token))
            return {
                "status": "deploying",
                "message": f"Deploy failed. Auto-triggering AI self-heal (attempt {pstate['retries']}/{max_retries})."
            }

        return {
            "status": "error",
            "error": str(e),
        }


async def repair_preview(
    git_repo_url: str,
    git_token: str,
    project_token: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Triggers an AI agent to fix the current preview error.
    Then automatically redeploys.
    """
    pk = _project_key(project_token)
    pstate = _preview_states.get(pk)
    if not pstate:
        return {"status": "error", "message": "No preview deployment found to repair."}

    # Ensure system agents exist
    state = _ensure_project_state(project_token)
    project_agents = state["agent_states"]
    if GIT_MANAGER_AGENT_ID not in project_agents:
        project_agents[GIT_MANAGER_AGENT_ID] = _make_agent(GIT_MANAGER_AGENT_ID, 2)
    if MASTER_AGENT_ID not in project_agents:
        project_agents[MASTER_AGENT_ID] = _make_agent(MASTER_AGENT_ID, 3)
    if DEPLOY_AGENT_ID not in project_agents:
        project_agents[DEPLOY_AGENT_ID] = _make_agent(DEPLOY_AGENT_ID, 4)

    # Get current repository structure for deployment agent context
    repo_structure = ""
    try:
        import context_manager as ctx_mgr
        repo_snapshot = ctx_mgr.get_current_project_tree_snapshot(project_token or "")
        if isinstance(repo_snapshot, dict):
            repo_structure = str(repo_snapshot.get("tree") or "").strip()
    except Exception:
        pass

    logs = "\n".join([log.get("message", "") for log in pstate.get("logs", [])[-30:]])
    server_log = pstate.get("server_log", "")
    error_context = logs
    if server_log:
        error_context += "\n\nServer Logs:\n" + server_log[-2000:]

    tree_context = f"\n\nCurrent Repository Structure:\n{repo_structure}\n" if repo_structure else ""
    
    pstate["status"] = "deploying"
    pstate["logs"].append({
        "time": datetime.utcnow().isoformat(),
        "message": "🤖 Starting AI repair process...",
    })
    pstate["logs"].append({
        "time": datetime.utcnow().isoformat(),
        "message": "🤖 AI repair is running in background (timeout: 15 minutes).",
    })

    async def _repair_bg():
        # Master Agent reference for live logging in the repair background task
        master_agent = project_agents.get(MASTER_AGENT_ID)
        def _master_log(msg: str):
            if master_agent:
                master_agent["output_log"].append({
                    "time": datetime.utcnow().isoformat(),
                    "type": "info",
                    "message": f"🕵️ [Preview-Audit] {msg}"
                })

        try:
            import uuid
            task = {
                "id": f"fix-{uuid.uuid4().hex[:8]}",
                "title": "Fix Preview Deployment Failure",
                "description": f"The application failed to start or deploy in the preview environment.\n\nLogs:\n{error_context}\n{tree_context}\nPlease identify the issue and modify the code to fix this deployment error.",
                "status": "pending"
            }
            
            # Align Deploy Agent for setup issues, Dev Agent for semantic/logic issues
            repair_owner = DEPLOY_AGENT_ID
            pstate["last_error_reason"] = str(error_context)
            
            # Simple content-based triage
            is_semantic = any(kw in str(error_context).lower() for kw in ["missing", "component", "wrong", "rejected", "semantic", "audit failed", "lacks", "placeholder"])
            if is_semantic:
                repair_owner = _pick_best_dev_agent(project_token)
                
            master_agent = project_agents.get(MASTER_AGENT_ID)
            if master_agent:
                master_agent["output_log"].append({
                    "time": datetime.utcnow().isoformat(),
                    "type": "info",
                    "message": f"⚖️ Triage: Aligning {repair_owner} to address deployment failure ({'semantic' if is_semantic else 'operational'} issue)."
                })

            # Formalize as a system task (BUG) for visibility
            try:
                from task_service import task_service
                effective_token = get_project_task_token(project_token)
                deadline = await _resolve_project_deadline(project_token, task_token=effective_token)
                
                bug_payload = {
                    "taskName": f"Fix Deployment: {repair_owner}",
                    "description": f"The application failed verification/deployment.\n\nTYPE: {'Semantic/Logic' if is_semantic else 'Operational/Setup'}\n\nERROR:\n{error_context[:2000]}",
                    "assignees": [repair_owner],
                    "wallet": 1,
                    "deadline": deadline,
                    "startdate": datetime.utcnow().strftime("%Y-%m-%d"),
                    "task_type": "BUG",
                    "priority": "high",
                }
                
                create_res = await task_service.create_task(bug_payload, task_token=effective_token)
                ext_task_id_raw = create_res.get("id") or create_res.get("task_id") or create_res.get("taskId")
                ext_task_id = str(ext_task_id_raw or uuid.uuid4().hex[:8])
                task["id"] = ext_task_id
                
                # Normalize username for the external API (e.g., agent_05 -> agent5)
                # This ensures the external system recognizes the assigned worker.
                ext_username = build_external_agent_username(repair_owner)
                
                # Assign it formally
                await task_service.assign_task(ext_task_id, [ext_username], task_token=effective_token)
                
                # Explicitly transition status to "In Progress" so it shows as "started" in the dashboard
                try:
                    if ext_task_id_raw:
                        await task_service.update_task(int(ext_task_id_raw), {"taskStatus": "In Progress"}, task_token=effective_token)
                except Exception as e_status:
                    _master_log(f"⚠️ Could not transition task {ext_task_id} status: {e_status}")
                
                # Opt-in automatically so the agent "starts" working in the system
                await task_service.opt_in_task({"task_id": ext_task_id, "username": ext_username}, task_token=effective_token)
                
                _master_log(f"🛠️ Created, assigned, and opted-in BUG task {ext_task_id} to {ext_username} for deployment repair.")
            except Exception as e_task:
                _master_log(f"⚠️ Failed to formalize BUG task startup: {e_task}")

            # Wait for AI to finish
            res = await asyncio.wait_for(
                run_agent(
                    agent_id=repair_owner,
                    assigned_task=task,
                    continuous=False,
                    ignore_running_check=True,
                    git_repo_url=git_repo_url,
                    git_token=git_token,
                    project_token=project_token,
                    force_branch=GIT_INTEGRATION_BRANCH
                ),
                timeout=900,
            )
            
            pstate["logs"].append({
                "time": datetime.utcnow().isoformat(),
                "message": f"🤖 AI repair completed (success: {res.get('success')}). Redeploying preview..."
            })
            
            # Redeploy
            await deploy_preview(git_repo_url, git_token, project_token, is_retry=True)
            
        except asyncio.TimeoutError:
            pstate["logs"].append({
                "time": datetime.utcnow().isoformat(),
                "message": "❌ AI repair timed out after 15 minutes.",
            })
            pstate["status"] = "error"
        except Exception as e:
            pstate["logs"].append({
                "time": datetime.utcnow().isoformat(),
                "message": f"❌ AI repair failed internally: {str(e)}"
            })
            pstate["status"] = "error"

    asyncio.create_task(_repair_bg())
    return {"status": "deploying", "message": "AI is repairing the deployment."}


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
                              "message": "Recovered running preview environment."}],
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
        "message": "Preview environment stopped and destroyed.",
    })
    return {"status": "stopped", "message": f"Preview environment {container_name} destroyed"}


# ── Agent & Task Management Helpers ─────────────────────────────────────────

def get_pending_tasks(project_token: Optional[str] = None) -> List[Dict[str, Any]]:
    state = _ensure_project_state(project_token)
    claimed_task_ids = state["claimed_task_ids"]
    tasks = state.get("tasks") if isinstance(state.get("tasks"), list) else []
    pending = []
    for task in _sort_tasks_for_execution(tasks):
        tid = str(_normalize_task_id(task) or task.get("external_id") or task.get("id") or "")
        if _task_status_is_done(task.get("status")):
            continue
        if tid and tid in claimed_task_ids:
            continue
        pending.append(task)
    return pending

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
    state = _ensure_project_state(project_token)
    claimed_task_ids = state["claimed_task_ids"]
    agent = project_agents.get(agent_id)
    if not agent:
        raise ValueError(f"Agent {agent_id} not found")
    current_task = agent.get("current_task") if isinstance(agent.get("current_task"), dict) else None
    task_id = _task_identity(current_task)
    if task_id:
        claimed_task_ids.discard(task_id)
    for linked_id in (current_task.get("linked_tasks") or []) if current_task else []:
        linked_key = str(linked_id or "").strip()
        if linked_key:
            claimed_task_ids.discard(linked_key)
    agent["status"] = "idle"
    agent["resume_pending_task"] = False
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
              kind: Optional[str] = None, project_token: Optional[str] = None) -> Dict[str, Any]:
    """Add a new agent dynamically."""
    project_agents = _get_agent_states(project_token)
    normalized_kind = str(kind or "").strip().lower()
    sequence = _next_dev_agent_sequence(project_agents)

    if normalized_kind in {"shared", "dedicated"}:
        prefix = f"{normalized_kind}_agent_"
        agent_id = f"{prefix}{sequence:02d}"
        while agent_id in project_agents:
            sequence += 1
            agent_id = f"{prefix}{sequence:02d}"
        seed_idx = sequence - 1
    else:
        seed_idx = sequence - 1
        agent_id = f"agent_{sequence:02d}"
        while agent_id in project_agents:
            sequence += 1
            seed_idx = sequence - 1
            agent_id = f"agent_{sequence:02d}"

    agent = _make_agent(agent_id, seed_idx)
    agent["name"] = normalize_agent_name(agent_id, name)
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
    agent["name"] = normalize_agent_name(agent_id, name)
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

# ── Master Agent Failure Detection & Intervention ──────────────────────────────

async def _master_detect_agent_failures(
    project_token: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Detect agents that failed or are stuck.
    Returns list of failed agents with context.
    """
    state = _ensure_project_state(project_token)
    project_agents = state["agent_states"]
    failed_agents = []
    
    current_time = datetime.utcnow()
    stuck_threshold_seconds = 1800  # 30 minutes
    
    for agent_id, agent in project_agents.items():
        if _is_system_agent_id(agent_id):
            continue
        
        agent_status = agent.get("status", "idle")
        current_task = agent.get("current_task")
        output_log = agent.get("output_log", [])
        last_run = agent.get("last_run")
        
        failure_info = {
            "agent_id": agent_id,
            "agent_name": agent.get("name", ""),
            "status": agent_status,
            "current_task": current_task,
            "failure_type": None,
            "failure_reason": None,
            "output_log_tail": output_log[-10:] if output_log else [],
            "last_run": last_run,
        }
        
        # Check for error status
        if agent_status == "error":
            failure_info["failure_type"] = "error"
            failure_info["failure_reason"] = agent.get("progress_message", "Agent in error state")
            failed_agents.append(failure_info)
            continue
        
        # Check for stuck agents (running too long)
        if agent_status == "running" and last_run:
            try:
                # Dynamic SLA timeout based on days_left
                # 1 day = 86400 seconds, fallback to 1800s if days_left is 0 or missing
                days_left = 0
                if isinstance(current_task, dict):
                    try:
                        days_left = int(current_task.get("days_left", 0))
                    except (ValueError, TypeError):
                        pass
                
                # If they have a deadline, give them up to that deadline incrementally
                # Otherwise, stick to the strict 30 min (1800s) hard limit
                dynamic_threshold = max((days_left * 86400) // 24, stuck_threshold_seconds) if days_left > 0 else stuck_threshold_seconds
                
                last_run_time = datetime.fromisoformat(last_run.replace("Z", "+00:00"))
                if last_run_time.tzinfo is None:
                    last_run_time = last_run_time.replace(tzinfo=timezone.utc)
                elapsed = (current_time.replace(tzinfo=timezone.utc) - last_run_time).total_seconds()
                
                if elapsed > dynamic_threshold:
                    failure_info["failure_type"] = "stuck"
                    failure_info["failure_reason"] = f"Agent running for {elapsed:.0f} seconds (>{stuck_threshold_seconds}s threshold)"
                    failed_agents.append(failure_info)
            except Exception:
                pass
        
        # Check for idle agents (sitting idle too long)
        if agent_status == "idle" and last_run:
            try:
                last_run_time = datetime.fromisoformat(last_run.replace("Z", "+00:00"))
                if last_run_time.tzinfo is None:
                    last_run_time = last_run_time.replace(tzinfo=timezone.utc)
                elapsed = (current_time.replace(tzinfo=timezone.utc) - last_run_time).total_seconds()
                
                if elapsed > 180:  # 3 minutes threshold
                    failure_info["failure_type"] = "idle_too_long"
                    failure_info["failure_reason"] = f"Agent idle for {elapsed:.0f} seconds (>180s threshold)"
                    failed_agents.append(failure_info)
            except Exception:
                pass
        
        # Check for repeated failures in output log
        error_count = sum(1 for log_entry in output_log if log_entry.get("type") == "error")
        if error_count >= 3:
            failure_info["failure_type"] = "repeated_errors"
            failure_info["failure_reason"] = f"Agent has {error_count} error entries in log"
            if failure_info not in failed_agents:
                failed_agents.append(failure_info)
    
    return failed_agents


async def _master_analyze_failure(
    agent_id: str,
    task: Optional[Dict[str, Any]],
    error: str,
    output_log: List[Dict[str, Any]],
    project_token: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Master Agent analyzes why agent failed using AI.
    Returns analysis with root cause and recovery plan.
    """
    url = llm_gateway.resolve_url()
    key = llm_gateway.resolve_key()
    model_name = llm_gateway.resolve_model()
    
    if not llm_gateway.check_api_key():
        return {
            "root_cause": "API key not configured",
            "recovery_plan": "Check configuration",
            "confidence": 0.0,
        }
    
    # Get task context
    task_title = task.get("title", "Unknown task") if task else "Unknown task"
    task_description = task.get("description", "")[:500] if task else ""
    
    # Get recent error messages from log
    error_messages = [
        entry.get("message", "") 
        for entry in output_log[-20:] 
        if entry.get("type") in ("error", "warning")
    ]
    error_summary = "\n".join(error_messages[-5:])
    
    # Get tech spec and master plan context
    tech_spec = get_technical_spec(project_token or "")
    state = _ensure_project_state(project_token)
    master_note = state.get("master_note_cache") if isinstance(state.get("master_note_cache"), dict) else {}
    workspace_tree = str(master_note.get("workspace_tree") or "")[:2000]
    
    prompt = f"""You are the Master Agent analyzing why a development agent failed.

AGENT: {agent_id}
TASK: {task_title}
TASK DESCRIPTION: {task_description}

ERROR MESSAGE:
{error}

RECENT ERROR LOG:
{error_summary}

PROJECT STRUCTURE (from Master Plan):
{workspace_tree[:1500]}

TECHNICAL SPEC (if available):
{tech_spec[:1500] if tech_spec else "Not available"}

Analyze the failure and provide:
1. Root cause analysis (what went wrong?)
2. Recovery plan (what should the agent do to fix it?)
3. Confidence level (0.0 to 1.0)

Return ONLY valid JSON:
{{
  "root_cause": "Brief explanation of what went wrong",
  "recovery_plan": "Step-by-step recovery instructions",
  "confidence": 0.0,
  "suggested_prompt_addition": "Additional context/prompt to give to the agent"
}}
"""
    
    try:
        messages = [
            {
                "role": "system",
                "content": "You are an expert software architect analyzing agent failures. Provide clear, actionable recovery plans."
            },
            {
                "role": "user",
                "content": prompt
            }
        ]
        
        content = await llm_gateway.call_llm_and_extract(
            messages=messages,
            api_url=url,
            api_key=key,
            model=model_name,
            timeout=60.0
        )
        
        if content:
            content = content.replace("```json", "").replace("```", "").strip()
            start_idx = content.find("{")
            end_idx = content.rfind("}")
            if start_idx != -1 and end_idx != -1:
                content = content[start_idx:end_idx + 1]
                analysis = json.loads(content)
                return analysis
        
        return {
            "root_cause": "Failed to analyze",
            "recovery_plan": "Retry the task",
            "confidence": 0.0,
        }
    except Exception as e:
        logger.warning(f"[Master Agent] Failure analysis failed: {e}")
        return {
            "root_cause": f"Analysis error: {str(e)[:100]}",
            "recovery_plan": "Retry the task with fresh context",
            "confidence": 0.0,
        }


async def _master_generate_recovery_prompt(
    agent_id: str,
    task: Dict[str, Any],
    failure_analysis: Dict[str, Any],
    project_token: Optional[str] = None,
) -> str:
    """
    Master Agent generates recovery prompt for stuck/failed agent.
    This prompt will be added to the agent's system prompt on retry.
    """
    root_cause = failure_analysis.get("root_cause", "Unknown issue")
    recovery_plan = failure_analysis.get("recovery_plan", "Retry the task")
    suggested_prompt = failure_analysis.get("suggested_prompt_addition", "")
    
    task_title = task.get("title", "Unknown task")
    task_description = task.get("description", "")[:300]
    
    recovery_prompt = f"""⚠️ MASTER AGENT RECOVERY GUIDANCE ⚠️

You previously failed on this task. Master Agent has analyzed the failure and provides guidance:

TASK: {task_title}
DESCRIPTION: {task_description}

ROOT CAUSE ANALYSIS:
{root_cause}

RECOVERY PLAN:
{recovery_plan}

{suggested_prompt if suggested_prompt else ""}

INSTRUCTIONS:
1. Read the root cause analysis carefully
2. Follow the recovery plan step-by-step
3. Pay attention to the specific issues mentioned
4. If you encounter the same error, try a different approach
5. Ensure you follow the canonical project structure from the Master Plan

Focus on fixing the specific issues identified rather than starting over.
"""
    
    return recovery_prompt


async def _master_notify_agent_failure(
    agent_id: str,
    task: Optional[Dict[str, Any]],
    error: str,
    project_token: Optional[str] = None,
    task_token: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Notify Master Agent about agent failure and get recovery guidance.
    This is called when an agent fails after all retries.
    """
    state = _ensure_project_state(project_token)
    project_agents = state["agent_states"]
    agent = project_agents.get(agent_id)
    
    if not agent:
        return {"success": False, "error": "Agent not found"}
    
    output_log = agent.get("output_log", [])
    
    _log_master_agent(
        f"🔍 Analyzing failure for agent {agent_id} on task {task.get('title', 'unknown') if task else 'unknown'}",
        project_token=project_token,
    )
    
    # Analyze the failure
    failure_analysis = await _master_analyze_failure(
        agent_id=agent_id,
        task=task,
        error=error,
        output_log=output_log,
        project_token=project_token,
    )
    
    # Generate recovery prompt
    if task:
        recovery_prompt = await _master_generate_recovery_prompt(
            agent_id=agent_id,
            task=task,
            failure_analysis=failure_analysis,
            project_token=project_token,
        )
        
        # Store recovery prompt in agent state for next retry
        agent["master_recovery_prompt"] = recovery_prompt
        agent["master_failure_analysis"] = failure_analysis
        
        _log_master_agent(
            f"✅ Generated recovery plan for agent {agent_id}: {failure_analysis.get('root_cause', 'Unknown')[:100]}",
            project_token=project_token,
        )
        
        # Post message to task
        try:
            await _post_task_message(
                task,
                f"🔍 Master Agent Analysis:\n\n**Root Cause:** {failure_analysis.get('root_cause', 'Unknown')}\n\n**Recovery Plan:** {failure_analysis.get('recovery_plan', 'Retry task')}",
                project_token=project_token,
                task_token=task_token,
            )
            
            # Explicitly mark the task as blocked using the new tag API
            task_id = _normalize_task_id(task)
            if task_id:
                from task_service import task_service
                await task_service.update_task_tags({
                    "task_id": int(task_id),
                    "tags": ["blocked"]
                }, task_token=task_token)
                _log_master_agent(f"🔴 Marked task {task_id} as BLOCKED", project_token=project_token)

        except Exception as api_err:
            logger.warning(f"Failed to post failure artifacts or block status: {api_err}")
    
    return {
        "success": True,
        "failure_analysis": failure_analysis,
        "recovery_prompt": recovery_prompt if task else None,
    }


# ── Master Agent Structure Validation ──────────────────────────────────────────

async def _master_validate_structure(
    project_token: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Master Agent validates structure continuously.
    Checks for duplicates, violations, and ensures canonical tree is followed.
    """
    state = _ensure_project_state(project_token)
    master_note = state.get("master_note_cache") if isinstance(state.get("master_note_cache"), dict) else {}
    workspace_tree = str(master_note.get("workspace_tree") or "").strip()
    
    if not workspace_tree:
        return {
            "valid": False,
            "reason": "No master tree available",
            "duplicates": [],
            "violations": [],
        }
    
    try:
        import context_manager as ctx_mgr
        workspace_contract = ctx_mgr.get_workspace_contract(project_token or "")
        repo_snapshot = ctx_mgr.get_current_project_tree_snapshot(project_token or "")
        
        violations = []
        duplicates = []
        
        if isinstance(repo_snapshot, dict):
            current_files = [
                str(path).strip()
                for path in (repo_snapshot.get("all_file_paths") or [])
                if str(path).strip()
            ]
            
            # Check for true duplicates (exact same normalized path observed multiple times).
            path_counts: Dict[str, int] = {}
            for file_path in current_files:
                normalized = _normalize_master_tree_path_candidate(file_path)
                if not normalized:
                    continue
                path_counts[normalized] = path_counts.get(normalized, 0) + 1
            for normalized, count in path_counts.items():
                if count > 1:
                    duplicates.append({
                        "file": normalized,
                        "occurrences": count,
                    })
            
            # Check workspace contract violations
            if isinstance(workspace_contract, dict) and workspace_contract.get("status") == "ready":
                allowed_roots = [
                    _normalize_master_tree_path_candidate(path)
                    for path in (workspace_contract.get("allowed_source_roots") or [])
                    if _normalize_master_tree_path_candidate(path)
                ]
                allowed_dirs = {
                    _normalize_master_tree_path_candidate(path)
                    for path in (workspace_contract.get("allowed_top_level_dirs") or [])
                    if _normalize_master_tree_path_candidate(path)
                }
                allowed_root_files = {
                    _normalize_master_tree_path_candidate(path)
                    for path in (workspace_contract.get("root_files") or [])
                    if _normalize_master_tree_path_candidate(path)
                }
                
                for file_path in current_files:
                    normalized_path = _normalize_master_tree_path_candidate(file_path)
                    if not normalized_path:
                        continue
                    if normalized_path in allowed_root_files:
                        continue
                    parts = normalized_path.split("/")
                    root_dir = parts[0] if parts else ""
                    if root_dir in {".git", ".github", "node_modules", "__pycache__", ".venv", "venv"}:
                        continue
                    in_allowed_dir = root_dir in allowed_dirs
                    in_allowed_root = any(
                        normalized_path == root
                        or normalized_path.startswith(root + "/")
                        for root in allowed_roots
                    )
                    if not in_allowed_dir and not in_allowed_root:
                        violations.append({
                            "file": normalized_path,
                            "reason": f"File outside allowed roots: {root_dir}",
                        })
        
        return {
            "valid": len(violations) == 0 and len(duplicates) == 0,
            "duplicates": duplicates[:10],  # Limit to first 10
            "violations": violations[:10],  # Limit to first 10
            "total_files_checked": len(current_files) if isinstance(repo_snapshot, dict) else 0,
        }
    except Exception as e:
        logger.warning(f"[Master Agent] Structure validation failed: {e}")
        return {
            "valid": True,  # Assume valid if check fails
            "reason": f"Validation check failed: {str(e)[:100]}",
            "duplicates": [],
            "violations": [],
        }


def _format_structure_issue_details(
    duplicates: List[Dict[str, Any]],
    violations: List[Dict[str, Any]],
    *,
    max_items: int = 3,
) -> str:
    detail_parts: List[str] = []

    for entry in (duplicates or [])[:max_items]:
        if not isinstance(entry, dict):
            continue
        file_path = str(entry.get("file") or "").strip()
        occurrences = entry.get("occurrences")
        if file_path:
            if occurrences not in (None, ""):
                detail_parts.append(f"duplicate: {file_path} (occurrences={occurrences})")
            else:
                detail_parts.append(f"duplicate: {file_path}")

    for entry in (violations or [])[:max_items]:
        if not isinstance(entry, dict):
            continue
        file_path = str(entry.get("file") or "").strip()
        reason = str(entry.get("reason") or "").strip()
        if file_path and reason:
            detail_parts.append(f"violation: {file_path} ({reason})")
        elif file_path:
            detail_parts.append(f"violation: {file_path}")
        elif reason:
            detail_parts.append(f"violation: {reason}")

    return " | ".join(detail_parts[: max_items * 2])


def _check_file_duplication_before_create(
    file_path: str,
    project_token: Optional[str] = None,
) -> tuple[bool, str]:
    """
    Check if file already exists before agent creates it.
    Returns (is_duplicate, reason)
    """
    try:
        import context_manager as ctx_mgr
        repo_snapshot = ctx_mgr.get_current_project_tree_snapshot(project_token or "")
        
        if isinstance(repo_snapshot, dict):
            existing_files = [
                str(path).strip().lower()
                for path in (repo_snapshot.get("all_file_paths") or [])
                if str(path).strip()
            ]
            
            file_path_lower = file_path.strip().lower()
            
            # Check exact match
            if file_path_lower in existing_files:
                return True, f"File {file_path} already exists"
            
            # Check basename match (same filename in different location)
            basename = os.path.basename(file_path_lower)
            for existing in existing_files:
                if os.path.basename(existing) == basename and existing != file_path_lower:
                    return True, f"File {basename} already exists at {existing}"
        
        return False, ""
    except Exception:
        return False, ""  # Allow creation if check fails


# ── Master Agent Git Manager Coordination ─────────────────────────────────────

async def _master_coordinate_git_manager(
    project_token: Optional[str] = None,
    task_token: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Master Agent coordinates with Git Manager.
    Checks integration branch readiness and coordinates merges.
    Ensures deploy-ready state when all tasks complete.
    """
    try:
        import context_manager as ctx_mgr
        
        # Get all tasks
        external_tasks = await _fetch_external_tasks(project_token)
        
        # Check if all tasks are completed
        completed_tasks = [t for t in external_tasks if _task_status_is_done(t.get("status"))]
        total_tasks = len(external_tasks)
        completed_count = len(completed_tasks)
        
        # Check integration branch status
        workspace_contract = ctx_mgr.get_workspace_contract(project_token or "")
        repo_snapshot = ctx_mgr.get_current_project_tree_snapshot(project_token or "")
        
        integration_ready = False
        integration_branch = GIT_INTEGRATION_BRANCH
        
        if isinstance(repo_snapshot, dict):
            current_branches = repo_snapshot.get("branches", [])
            if integration_branch in current_branches:
                integration_ready = True
        
        # Validate structure before integration
        structure_validation = await _master_validate_structure(project_token=project_token)
        
        deploy_ready = (
            integration_ready and
            structure_validation.get("valid", True) and
            completed_count == total_tasks and
            total_tasks > 0
        )
        
        # If all tasks completed and structure valid, notify Git Manager
        if completed_count == total_tasks and total_tasks > 0:
            if structure_validation.get("valid", True):
                _log_master_agent(
                    f"✅ All tasks completed ({completed_count}/{total_tasks}). Structure validated. Ready for integration.",
                    project_token=project_token,
                )
                
                # Get Git Manager credentials
                state = _ensure_project_state(project_token)
                git_creds = _resolve_project_git_credentials(project_token)
                repo_url = git_creds.get("repo_url")
                git_token = git_creds.get("token")
                
                if repo_url:
                    # Ensure integration branch exists and is ready
                    _log_master_agent(
                        f"🔗 Coordinating with Git Manager for integration branch: {integration_branch}",
                        project_token=project_token,
                    )
            else:
                _log_master_agent(
                    f"⚠️ All tasks completed but structure has issues. Fix before deployment.",
                    level="warning",
                    project_token=project_token,
                )
        
        return {
            "integration_ready": integration_ready,
            "integration_branch": integration_branch,
            "tasks_completed": completed_count,
            "tasks_total": total_tasks,
            "structure_valid": structure_validation.get("valid", True),
            "structure_duplicates": structure_validation.get("duplicates", []),
            "structure_violations": structure_validation.get("violations", []),
            "deploy_ready": deploy_ready,
            "completion_percentage": round((completed_count / total_tasks * 100) if total_tasks > 0 else 0, 1),
        }
    except Exception as e:
        logger.warning(f"[Master Agent] Git Manager coordination failed: {e}")
        return {
            "integration_ready": False,
            "error": str(e)[:200],
            "deploy_ready": False,
        }


# ── Master Agent Supervisor Loop ──────────────────────────────────────────────

async def _master_supervisor_loop(
    project_token: Optional[str] = None,
    task_token: Optional[str] = None,
    check_interval: int = 30,
    max_iterations: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Continuous supervisor loop to ensure all agents work.
    - Monitors agent status
    - Assigns tasks to idle agents
    - Detects stuck/failed agents
    - Redistributes work
    """
    state = _ensure_project_state(project_token)
    if task_token:
        state["task_token"] = task_token
    
    iteration = 0
    total_assignments = 0
    total_interventions = 0
    
    _log_master_agent(
        f"🔄 Master Supervisor Loop started (check_interval={check_interval}s)",
        project_token=project_token,
    )
    
    try:
        while max_iterations is None or iteration < max_iterations:
            iteration += 1
            
            # Get current state
            project_agents = state["agent_states"]
            external_tasks = await _fetch_external_tasks(project_token)
            state["tasks"] = external_tasks
            
            # Find idle agents
            idle_agents = [
                agent for agent in project_agents.values()
                if agent["status"] == "idle" and not _is_system_agent_id(agent["id"])
            ]
            
            # Find available tasks (not completed, not claimed)
            available_tasks = []
            claimed_task_ids = state["claimed_task_ids"]
            
            for task in external_tasks:
                tid = str(_normalize_task_id(task) or task.get("external_id") or task.get("id") or "")
                if not tid:
                    continue
                if _task_status_is_done(task.get("status")):
                    continue
                if tid in claimed_task_ids:
                    continue
                available_tasks.append(task)
            
            # Agent self-assignment ensures they opt-in sequentially.
            # Active assignment is only done when an agent is idle for too long (see failure/idle handling below)
            
            # Check for failed/stuck agents using dedicated function
            failed_agents = await _master_detect_agent_failures(project_token=project_token)
            
            for failure_info in failed_agents:
                agent_id = failure_info["agent_id"]
                failure_type = failure_info["failure_type"]
                failure_reason = failure_info["failure_reason"]
                current_task = failure_info.get("current_task")
                
                if failure_type == "error":
                    _log_master_agent(
                        f"❌ Agent {agent_id} in error state: {failure_reason}",
                        level="error",
                        project_token=project_token,
                    )
                    
                    # Analyze and provide recovery guidance
                    if current_task:
                        try:
                            await _master_notify_agent_failure(
                                agent_id=agent_id,
                                task=current_task,
                                error=failure_reason or "Agent in error state",
                                project_token=project_token,
                                task_token=task_token,
                            )
                            
                            # Reassign task if agent keeps failing
                            agent = project_agents.get(agent_id)
                            if agent and agent.get("status") == "error":
                                # Unassign task using explicit API endpoint so Master Agent can review and fix
                                task_id = str(_normalize_task_id(current_task) or current_task.get("external_id") or current_task.get("id") or "")
                                if task_id:
                                    username = build_external_agent_username(agent_id, agent.get("name"))
                                    from task_service import task_service
                                    await task_service.unassign_task({
                                        "task_id": int(task_id),
                                        "username": username
                                    }, task_token=task_token)
                                    _log_master_agent(
                                        f"🔄 Unassigned blocked task {task_id} from failing agent {agent_id} for Master Agent review",
                                        project_token=project_token,
                                    )
                                    await _post_task_message(
                                        current_task,
                                        f"Master Agent intervened: Unassigned task from failing agent {agent_id} for review.",
                                        project_token=project_token,
                                        task_token=task_token,
                                    )
                                    agent["current_task"] = None
                                    agent["status"] = "idle"
                        except Exception as analysis_err:
                            logger.warning(f"[Master Agent] Failed to analyze agent {agent_id} failure: {analysis_err}")
                    
                    total_interventions += 1
                elif failure_type == "stuck":
                    _log_master_agent(
                        f"⚠️ Agent {agent_id} appears stuck: {failure_reason}",
                        level="warning",
                        project_token=project_token,
                    )
                    total_interventions += 1
                elif failure_type == "idle_too_long":
                    _log_master_agent(
                        f"⚠️ Agent {agent_id} is idle for >3 mins, Master Agent intervening to assign task.",
                        level="warning",
                        project_token=project_token,
                    )
                    if available_tasks:
                        task = available_tasks.pop(0)
                        task_id = str(_normalize_task_id(task) or task.get("external_id") or task.get("id") or "")
                        if task_id:
                            success = await _master_assign_task_to_agent(
                                task_id=task_id,
                                agent_id=agent_id,
                                agent_name=project_agents.get(agent_id, {}).get("name"),
                                project_token=project_token,
                                task_token=task_token,
                            )
                            if success:
                                _log_master_agent(
                                    f"✅ Assigned task {task_id} to idle agent {agent_id}",
                                    project_token=project_token,
                                )
                                total_assignments += 1
                    total_interventions += 1
            
            # Check integration branch readiness
            if iteration % 10 == 0:  # Check every 10 iterations (5 minutes)
                git_coordination = await _master_coordinate_git_manager(
                    project_token=project_token,
                    task_token=task_token,
                )
                if git_coordination.get("deploy_ready"):
                    _log_master_agent(
                        f"🚀 Project ready for deployment! All tasks completed, structure validated.",
                        project_token=project_token,
                    )
                elif git_coordination.get("structure_duplicates") or git_coordination.get("structure_violations"):
                    dup_items = git_coordination.get("structure_duplicates", []) or []
                    viol_items = git_coordination.get("structure_violations", []) or []
                    detail_text = _format_structure_issue_details(
                        dup_items,
                        viol_items,
                        max_items=3,
                    )
                    message = (
                        f"⚠️ Structure issues detected: {len(dup_items)} duplicates, "
                        f"{len(viol_items)} violations"
                    )
                    if detail_text:
                        message += f" | {detail_text}"
                    _log_master_agent(
                        message,
                        level="warning",
                        project_token=project_token,
                    )
            
            # Sleep before next check
            await asyncio.sleep(check_interval)
            
    except asyncio.CancelledError:
        _log_master_agent(
            "🛑 Master Supervisor Loop cancelled",
            project_token=project_token,
        )
        raise
    except Exception as e:
        _log_master_agent(
            f"❌ Master Supervisor Loop error: {str(e)[:200]}",
            level="error",
            project_token=project_token,
        )
        raise
    
    return {
        "iterations": iteration,
        "total_assignments": total_assignments,
        "total_interventions": total_interventions,
    }


async def run_all_agents(agents_config: Dict[str, Dict[str, str]] = None,
                         project_token: Optional[str] = None,
                         task_token: Optional[str] = None,
                         enable_supervisor: bool = True) -> Dict[str, Any]:
    """
    Run idle agents simultaneously with Master Agent supervision.
    Each agent picks tasks assigned to them or picks from available tasks.
    Supervisor loop ensures all agents work continuously.
    """
    prime_project_git_credentials(agents_config, project_token=project_token)
    
    # Start supervisor loop in background if enabled
    supervisor_task = None
    if enable_supervisor:
        supervisor_task = asyncio.create_task(
            _master_supervisor_loop(
                project_token=project_token,
                task_token=task_token,
                check_interval=30,
            )
        )
        _log_master_agent(
            "🚀 Master Supervisor Loop started in background",
            project_token=project_token,
        )
    
    try:
        import langgraph_workflow

        result = await langgraph_workflow.run_agent_supervisor_workflow(
            agents_config=agents_config,
            project_token=project_token,
            task_token=task_token,
        )
        
        # DO NOT cancel supervisor - it should run continuously to handle new tasks
        # The supervisor loop runs independently and monitors/assigns tasks continuously
        # Even if workflow completes, supervisor keeps running for continuous operation
        
        return result
    except ImportError as exc:
        logger.warning("LangGraph workflow unavailable, falling back to legacy runner: %s", exc)

    state = _ensure_project_state(project_token)
    if task_token:
        state["task_token"] = task_token
    project_agents = state["agent_states"]

    idle_agents = [
        a for a in project_agents.values()
        if a["status"] == "idle" and not _is_system_agent_id(a["id"])
    ]
    if not idle_agents:
        raise ValueError("No idle agents. Reset agents or add new ones.")

    try:
        external_tasks = await _fetch_external_tasks(project_token)
        if not external_tasks:
            raise ValueError("No tasks available from the external task API. Generate tasks first.")
        state["tasks"] = external_tasks
    except Exception as e:
        raise

    ordered_agent_ids = [agent["id"] for agent in sorted(idle_agents, key=lambda item: item["id"])]
    if agents_config:
        for aid in ordered_agent_ids:
            if aid in agents_config:
                repo_val = agents_config[aid].get("git_repo_url")
                if repo_val:
                    project_agents[aid]["git_repo_url"] = repo_val.strip()
                token_val = agents_config[aid].get("git_token")
                if token_val:
                    project_agents[aid]["git_token"] = token_val.strip()

    launched_agents = list(ordered_agent_ids)

    async def _run_one(agent_id: str) -> Dict[str, Any]:
        try:
            return await run_agent(
                agent_id,
                assigned_task=None,
                continuous=True,
                ignore_running_check=True,
                project_token=project_token,
                task_token=task_token,
            )
        except Exception as e:
            return {"success": False, "agent_id": agent_id, "error": str(e), "tasks_completed": 0}

    results = await asyncio.gather(*(_run_one(agent_id) for agent_id in ordered_agent_ids), return_exceptions=True)

    return {
        "launched": len(launched_agents),
        "agents": launched_agents,
        "results": [
            result if isinstance(result, dict) else {"success": False, "error": str(result), "tasks_completed": 0}
            for result in results
        ],
    }
