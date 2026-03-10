import logging
import json
import re
from html import escape
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

import ai_service
from agent_service import MASTER_AGENT_ID

logger = logging.getLogger(__name__)

TYPE_CONFIG = {
    "EPIC": {"prefix": "EPIC", "level": 1},
    "FEATURE": {"prefix": "FEAT", "level": 2},
    "STORY": {"prefix": "STORY", "level": 3},
    "TASK": {"prefix": "TASK", "level": 4},
    "BUG": {"prefix": "BUG", "level": 4},
}

# Phase-to-sprint-group mapping: tasks whose phase maps to the same
# index will be placed inside the same sprint.
PHASE_TO_SPRINT_INDEX = {
    "foundation": 0,
    "backend-core": 0,
    "backend-features": 1,
    "frontend-core": 1,
    "frontend-features": 2,
    "integration": 2,
}

SPRINT_GROUP_LABELS = [
    ("Foundation & Core Setup", "Project foundation, scaffolding, and core backend setup"),
    ("Feature Development", "Backend and frontend feature implementation"),
    ("Integration & Polish", "Frontend features, integration testing, and deployment preparation"),
]


def _format_date(value: date) -> str:
    return value.strftime("%Y-%m-%d")


def _parse_date(value: Any) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value

    text = str(value).strip()
    if not text:
        return None

    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _parse_timeline_deadline(timeline: Any, *, start_date: date) -> date:
    default_deadline = start_date + timedelta(days=30)
    lower = str(timeline or "").strip().lower()
    if not lower:
        return default_deadline

    matchers = (
        (r"(\d+)(?:\s*-\s*(\d+))?\s*week", 7),
        (r"(\d+)(?:\s*-\s*(\d+))?\s*month", 30),
        (r"(\d+)(?:\s*-\s*(\d+))?\s*day", 1),
        (r"(\d+)(?:\s*-\s*(\d+))?\s*year", 365),
    )
    for pattern, unit_days in matchers:
        match = re.search(pattern, lower)
        if not match:
            continue
        upper_bound = int(match.group(2) or match.group(1))
        return start_date + timedelta(days=max(upper_bound * unit_days, 1))

    return default_deadline


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_priority(value: Any) -> str:
    priority = str(value or "").strip().lower()
    if priority in {"high", "medium", "low"}:
        return priority
    return "medium"


def _normalize_task_type(value: Any) -> str:
    candidate = str(value or "TASK").strip().upper()
    if candidate in TYPE_CONFIG:
        return candidate
    return "TASK"


def _display_name(raw_name: Optional[str]) -> str:
    cleaned = str(raw_name or "").strip()
    return cleaned or "Master Agent"


def _coalesce_date(*values: Any) -> Optional[date]:
    for value in values:
        parsed = _parse_date(value)
        if parsed is not None:
            return parsed
    return None


def _normalize_project_dates(analysis_payload: Dict[str, Any]) -> tuple[date, date]:
    project_meta = analysis_payload.get("projectMeta")
    if not isinstance(project_meta, dict):
        project_meta = {}
    metrics = analysis_payload.get("metrics")
    if not isinstance(metrics, dict):
        metrics = {}

    start_date = _coalesce_date(
        analysis_payload.get("project_start_date"),
        analysis_payload.get("project_start"),
        analysis_payload.get("start_date"),
        analysis_payload.get("startDate"),
        analysis_payload.get("projectStartDate"),
        project_meta.get("project_start_date"),
        project_meta.get("project_start"),
        project_meta.get("start_date"),
        project_meta.get("startDate"),
        project_meta.get("projectStartDate"),
    ) or date.today()

    explicit_deadline = _coalesce_date(
        analysis_payload.get("project_deadline"),
        analysis_payload.get("project_end_date"),
        analysis_payload.get("project_end"),
        analysis_payload.get("deadline"),
        analysis_payload.get("end_date"),
        analysis_payload.get("endDate"),
        analysis_payload.get("projectDeadline"),
        analysis_payload.get("projectEndDate"),
        project_meta.get("project_deadline"),
        project_meta.get("project_end_date"),
        project_meta.get("project_end"),
        project_meta.get("deadline"),
        project_meta.get("end_date"),
        project_meta.get("endDate"),
        project_meta.get("projectDeadline"),
        project_meta.get("projectEndDate"),
    )
    deadline = explicit_deadline
    if deadline is None:
        timeline = metrics.get("timeline") or project_meta.get("timeline")
        deadline = _parse_timeline_deadline(timeline, start_date=start_date)
    if deadline < start_date:
        deadline = start_date if explicit_deadline is not None else start_date + timedelta(days=30)
    return start_date, deadline


def _derive_total_wallet(analysis_payload: Dict[str, Any], analysis_report: str) -> int:
    metrics = analysis_payload.get("metrics")
    if not isinstance(metrics, dict):
        metrics = {}

    complexity = str(metrics.get("complexity") or "").strip().lower()
    base_wallet = {
        "low": 24,
        "medium": 40,
        "high": 60,
    }.get(complexity, 36)

    timeline = str(metrics.get("timeline") or "").strip().lower()
    if "year" in timeline:
        base_wallet += 20
    elif "month" in timeline:
        month_values = [int(m) for m in re.findall(r"\d+", timeline)]
        if month_values:
            base_wallet += max(month_values) * 2
    elif "week" in timeline:
        week_values = [int(w) for w in re.findall(r"\d+", timeline)]
        if week_values:
            base_wallet += max(week_values)

    lower_analysis = analysis_report.lower()
    if "enterprise" in lower_analysis or "complex" in lower_analysis:
        base_wallet += 8

    return max(20, min(base_wallet, 90))
 
 
def _derive_project_type(analysis_payload: Dict[str, Any]) -> str:
    metrics = analysis_payload.get("metrics") or {}
    ptype = str(metrics.get("project_type") or "").strip().lower()
    if "modernization" in ptype:
        return "modernization"
    if "brownfield" in ptype:
        return "brownfield"
    return "greenfield"




def _build_analysis_context(
    analysis_report: str,
    prerequisites: List[Dict[str, Any]],
    custom_rules: Optional[str],
    *,
    max_chars: int = 8000,
) -> str:
    """
    Build the analysis context string for downstream AI calls.

    The analysis text is truncated to `max_chars` to avoid unbounded token usage
    while still keeping the most recent / most relevant content.
    """
    trimmed_report = str(analysis_report or "").strip()
    if max_chars and len(trimmed_report) > max_chars:
        logger.info(
            "Truncating analysis report for AI context: original_len=%s, max_chars=%s",
            len(trimmed_report),
            max_chars,
        )
        trimmed_report = trimmed_report[:max_chars]

    parts: List[str] = [trimmed_report]

    if prerequisites:
        prereq_lines = ["PREREQUISITES & CREDENTIALS (confirmed by the team):"]
        for item in prerequisites:
            name = str(item.get("name") or "Unknown").strip()
            description = str(item.get("description") or "").strip()
            category = str(item.get("category") or "other").strip()
            priority = str(item.get("priority") or "medium").strip()
            provided = bool(item.get("provided"))
            status = "PROVIDED" if provided else "NOT YET PROVIDED"

            details: List[str] = []
            if not bool(item.get("containsSecret")):
                user_value = str(item.get("userValue") or "").strip()
                user_file = str(item.get("userFileName") or "").strip()
                user_notes = str(item.get("userNotes") or "").strip()
                if user_value:
                    details.append(f"Value: {user_value}")
                if user_file:
                    details.append(f"File: {user_file}")
                if user_notes:
                    details.append(f"Notes: {user_notes}")

            line = f"- [{status}] {name} ({category}, {priority})"
            if description:
                line += f": {description}"
            if details:
                line += f" | Team Input: {' | '.join(details)}"
            prereq_lines.append(line)
        parts.append("\n".join(prereq_lines))

    if custom_rules:
        parts.append(f"CUSTOM RULES TO FOLLOW:\n{custom_rules.strip()}")

    return "\n\n".join(part for part in parts if part).strip()


def _normalize_task_dates(
    start_value: Any,
    end_value: Any,
    *,
    min_date: date,
    max_date: date,
    require_strict_order: bool = False,
) -> tuple[str, str]:
    start_date = _parse_date(start_value) or min_date
    end_date = _parse_date(end_value) or max_date

    if start_date < min_date:
        start_date = min_date
    if start_date > max_date:
        start_date = max_date

    if require_strict_order:
        if end_date <= start_date:
            start_date = min_date
            end_date = max_date
    elif end_date < start_date:
        end_date = start_date

    if end_date > max_date:
        end_date = max_date
    if require_strict_order:
        if end_date <= start_date and min_date < max_date:
            start_date = min_date
            end_date = max_date
    elif end_date < start_date:
        end_date = start_date

    return _format_date(start_date), _format_date(end_date)


def _normalize_dependencies(value: Any) -> List[int]:
    if not isinstance(value, list):
        return []

    dependencies: List[int] = []
    for item in value:
        seq = _safe_int(item, default=0)
        if seq > 0 and seq not in dependencies:
            dependencies.append(seq)
    return dependencies


def _determine_sprint_groups(raw_tasks: List[Dict[str, Any]]) -> List[int]:
    """Return sorted list of sprint-group indices that have at least one task."""
    groups: set[int] = set()
    for task in raw_tasks:
        phase = str(task.get("phase") or "").strip().lower()
        groups.add(PHASE_TO_SPRINT_INDEX.get(phase, 0))
    return sorted(groups) if groups else [0]


def _create_sprints_and_milestones(
    *,
    groups_used: List[int],
    project_start: date,
    project_deadline: date,
    project_name: str,
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[int, int]]:
    """Create sprint and milestone objects for each active phase group.

    Returns ``(sprints, milestones, group_index -> position)``.
    """
    num = max(len(groups_used), 1)
    if not groups_used:
        groups_used = [0]

    total_days = max((project_deadline - project_start).days, 1)
    sprint_days = max(total_days // num, 1)

    sprints: List[Dict[str, Any]] = []
    milestones: List[Dict[str, Any]] = []
    group_to_pos: Dict[int, int] = {}

    for i, group_idx in enumerate(groups_used):
        s_start = project_start + timedelta(days=i * sprint_days)
        s_end = (
            project_deadline
            if i == num - 1
            else project_start + timedelta(days=(i + 1) * sprint_days - 1)
        )
        if s_end < s_start:
            s_end = s_start

        label, summary = (
            SPRINT_GROUP_LABELS[group_idx]
            if group_idx < len(SPRINT_GROUP_LABELS)
            else (f"Phase {i + 1}", f"Sprint {i + 1} for {project_name}")
        )
        sprint_id = f"SPR-{i + 1:02d}"
        milestone_id = f"MS-{i + 1:02d}"

        sprints.append({
            "id": sprint_id,
            "name": f"Sprint {i + 1} - {label}",
            "summary": summary,
            "start_date": _format_date(s_start),
            "deadline": _format_date(s_end),
        })
        milestones.append({
            "id": milestone_id,
            "name": f"Milestone {i + 1} - {label}",
            "sprint_id": sprint_id,
            "start_date": _format_date(s_start),
            "deadline": _format_date(s_end),
        })
        group_to_pos[group_idx] = i

    return sprints, milestones, group_to_pos


def _normalize_generated_task(
    raw_task: Dict[str, Any],
    *,
    sequence_number: int,
    project_start: date,
    project_deadline: date,
) -> Dict[str, Any]:
    task_name = str(raw_task.get("taskName") or "").strip()
    task_description = str(raw_task.get("description") or "").strip()
    task_type = _normalize_task_type(raw_task.get("task_type"))
    wallet = max(1, min(_safe_int(raw_task.get("wallet"), default=1), 10))
    start_iso, end_iso = _normalize_task_dates(
        raw_task.get("startdate"),
        raw_task.get("deadline"),
        min_date=project_start,
        max_date=project_deadline,
    )

    return {
        "sequence_number": sequence_number,
        "taskName": task_name,
        "description": task_description,
        "task_type": task_type,
        "priority": _normalize_priority(raw_task.get("priority")),
        "wallet": wallet,
        "startdate": start_iso,
        "deadline": end_iso,
        "dependencies": _normalize_dependencies(raw_task.get("dependencies")),
        "phase": str(raw_task.get("phase") or "").strip().lower(),
        "domain": str(raw_task.get("domain") or "").strip().lower(),
        "checklist": raw_task.get("checklist"),
    }



def _fallback_checklist(title: str, task_type: str) -> List[Dict[str, Any]]:
    checklist_title = "Planning" if task_type in {"epic", "feature"} else "Execution"
    return [
        {
            "title": checklist_title,
            "items": [
                f"Review scope for {title}",
                f"Implement {title.lower()}",
                f"Validate and document {title.lower()}",
            ],
        }
    ]


def _select_parent_id(
    *,
    level: int,
    dependency_ids: List[str],
    latest_by_level: Dict[int, str],
    task_meta_by_id: Dict[str, Dict[str, Any]],
) -> Optional[str]:
    best_parent_id: Optional[str] = None
    best_parent_level = 0

    for dep_id in dependency_ids:
        dep_meta = task_meta_by_id.get(dep_id)
        if not dep_meta:
            continue
        dep_level = _safe_int(dep_meta.get("level"), 0)
        if dep_level < level and dep_level > best_parent_level:
            best_parent_id = dep_id
            best_parent_level = dep_level

    if best_parent_id:
        return best_parent_id

    for candidate_level in range(level - 1, 0, -1):
        candidate = latest_by_level.get(candidate_level)
        if candidate:
            return candidate

    return None


def _extract_numeric_suffix(value: Any) -> Optional[int]:
    if value in (None, ""):
        return None
    if isinstance(value, int):
        return value

    text = str(value).strip()
    if not text:
        return None
    if text.isdigit():
        return int(text)

    match = re.search(r"(\d+)$", text)
    if not match:
        return None
    return int(match.group(1))


def _normalize_preview_project_reference(project_reference: Any, project_token: str) -> Any:
    if project_reference not in (None, ""):
        numeric_reference = _extract_numeric_suffix(project_reference)
        if numeric_reference is not None and str(project_reference).strip().isdigit():
            return numeric_reference
        return project_reference
    return project_token


def _wrap_html_paragraph(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "<p></p>"
    return f"<p>{escape(text)}</p>"


def _build_preview_checklist(checklists: Any) -> Optional[str]:
    if not isinstance(checklists, list):
        return None

    checklist_items: List[Dict[str, Any]] = []
    for group in checklists:
        if not isinstance(group, dict):
            continue
        raw_items = group.get("items")
        if not isinstance(raw_items, list):
            continue
        for item in raw_items:
            if isinstance(item, dict):
                text = str(item.get("text") or item.get("title") or "").strip()
                completed = bool(item.get("completed"))
            else:
                text = str(item or "").strip()
                completed = False
            if text:
                checklist_items.append({
                    "text": text,
                    "completed": completed,
                })

    if not checklist_items:
        return None

    return json.dumps(
        {
            "checklistItems": checklist_items,
        },
        ensure_ascii=False,
    )


def _build_preview_json_tasks(
    structured_tasks: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    preview_tasks: List[Dict[str, Any]] = []
    for task in structured_tasks:
        checklist_payload = _build_preview_checklist(task.get("checklists"))

        raw_task_wallet = max(
            _safe_int(task.get("story_points"), 0),
            _safe_int(task.get("estimated_hours"), 0) // 8,
            0,
        )
        task_wallet = max(1, min(5, raw_task_wallet))

        payload: Dict[str, Any] = {
            "taskName": task.get("title") or "Untitled Task",
            "task_type": str(task.get("type") or "task").upper(),
            "description": _wrap_html_paragraph(task.get("description")),
            "startdate": task.get("planned_start"),
            "planned_start": task.get("planned_start"),
            "deadline": task.get("planned_end"),
            "priority": task.get("priority") or "medium",
            "task_wallet": task_wallet,
            "_placeholder_sprint_id": task.get("sprint_id"),
            "_placeholder_milestone_id": task.get("milestone_id"),
        }

        if checklist_payload:
            payload["checklist"] = checklist_payload

        preview_tasks.append(payload)

    return preview_tasks


def _build_structured_tasks(
    raw_tasks: List[Dict[str, Any]],
    *,
    project_id: str,
    project_name: str,
    sprints: List[Dict[str, Any]],
    milestones: List[Dict[str, Any]],
    group_to_sprint_idx: Dict[int, int],
    reporter_name: str,
) -> List[Dict[str, Any]]:
    type_counters: Dict[str, int] = {}
    seq_to_task_id: Dict[int, str] = {}
    latest_by_level: Dict[int, str] = {}
    child_count_by_parent: Dict[str, int] = {}
    task_meta_by_id: Dict[str, Dict[str, Any]] = {}
    structured_tasks: List[Dict[str, Any]] = []
    root_count = 0

    for index, raw_task in enumerate(raw_tasks):
        task_type = _normalize_task_type(raw_task.get("task_type"))
        config = TYPE_CONFIG[task_type]
        type_counters[task_type] = type_counters.get(task_type, 0) + 1
        task_id = f"{config['prefix']}-{type_counters[task_type]:02d}"
        dependency_ids = [
            seq_to_task_id[seq]
            for seq in raw_task.get("dependencies", [])
            if seq in seq_to_task_id
        ]

        level = config["level"]
        parent_id = None if level == 1 else _select_parent_id(
            level=level,
            dependency_ids=dependency_ids,
            latest_by_level=latest_by_level,
            task_meta_by_id=task_meta_by_id,
        )

        if parent_id is None:
            root_count += 1
            wbs = str(root_count)
        else:
            child_count_by_parent[parent_id] = child_count_by_parent.get(parent_id, 0) + 1
            parent_wbs = str(task_meta_by_id[parent_id]["wbs"])
            wbs = f"{parent_wbs}.{child_count_by_parent[parent_id]}"
            if parent_id not in dependency_ids:
                dependency_ids.append(parent_id)

        # Determine which sprint this task belongs to based on its phase
        phase = str(raw_task.get("phase") or "").strip().lower()
        group_idx = PHASE_TO_SPRINT_INDEX.get(phase, 0)
        sprint_pos = group_to_sprint_idx.get(group_idx, 0)
        task_sprint = sprints[sprint_pos]
        task_milestone = milestones[sprint_pos]

        # Re-clamp task dates to the assigned sprint's date range
        sprint_start = _parse_date(task_sprint["start_date"]) or date.today()
        sprint_end = _parse_date(task_sprint["deadline"]) or sprint_start
        planned_start, planned_end = _normalize_task_dates(
            raw_task.get("startdate"),
            raw_task.get("deadline"),
            min_date=sprint_start,
            max_date=sprint_end,
        )

        structured = {
            "project_id": project_id,
            "project_name": project_name,
            "task_id": task_id,
            "parent_id": parent_id,
            "type": task_type.lower(),
            "title": raw_task.get("taskName") or "Untitled Task",
            "description": raw_task.get("description") or "",
            "status": "in_progress" if index == 0 else "todo",
            "priority": raw_task.get("priority") or "medium",
            "story_points": 0 if task_type == "EPIC" else raw_task.get("wallet", 1),
            "sprint_id": task_sprint["id"],
            "sprint_name": task_sprint["name"],
            "milestone_id": task_milestone["id"],
            "reporter": MASTER_AGENT_ID,
            "assignee": "",
            "resource_names": [reporter_name],
            "planned_start": planned_start,
            "planned_end": planned_end,
            "estimated_hours": max(_safe_int(raw_task.get("wallet"), 1) * 8, 8),
            "wbs": wbs,
            "level": level,
            "dependencies": dependency_ids,
            "checklists": [],
            "raw_checklist": raw_task.get("checklist"),
        }


        structured_tasks.append(structured)
        seq_to_task_id[_safe_int(raw_task.get("sequence_number"), 0)] = task_id
        task_meta_by_id[task_id] = {"level": level, "wbs": wbs}
        latest_by_level[level] = task_id
        for deeper_level in range(level + 1, 5):
            latest_by_level.pop(deeper_level, None)

    return structured_tasks


async def _attach_checklists(
    *,
    structured_tasks: List[Dict[str, Any]],
    analysis_report: str,
) -> None:
    tasks_needing_checklists = []
    for task in structured_tasks:
        raw_items = task.get("raw_checklist")
        if isinstance(raw_items, list) and raw_items:
            items = []
            for item in raw_items:
                if isinstance(item, dict):
                    text = str(item.get("text") or item.get("title") or "").strip()
                else:
                    text = str(item or "").strip()
                if text:
                    items.append(text)

            # Enforce architect spec: at least 4 concrete checklist steps
            while len(items) < 4:
                # Add generic but real development actions to reach minimum length
                filler_steps = [
                    "analyze current module",
                    "design interface",
                    "implement service layer",
                    "write unit tests",
                    "update documentation",
                ]
                for step in filler_steps:
                    if len(items) >= 4:
                        break
                    if step not in items:
                        items.append(step)

            item_count = len(items)
            if item_count < 3 or item_count > 7:
                logger.warning(
                    "Checklist item count out of recommended range (3-7). "
                    "task_id=%s type=%s count=%s",
                    task.get("task_id"),
                    task.get("type"),
                    item_count,
                )
                # Hard cap extremely long lists to avoid bloated payloads.
                if item_count > 10:
                    items = items[:10]

            if items:
                task["checklists"] = [
                    {
                        "title": "Planning" if task["type"] in {"epic", "feature"} else "Execution",
                        "items": items,
                    }
                ]
                continue
        
        tasks_needing_checklists.append(task)

    if not tasks_needing_checklists:
        return

    checklist_inputs = [
        {
            "id": task["task_id"],
            "taskName": task["title"],
            "description": task["description"],
            "task_type": str(task["type"]).upper(),
            "priority": task["priority"],
        }
        for task in tasks_needing_checklists
    ]

    checklist_map: Dict[str, Any] = {}
    try:
        checklist_map = await ai_service.generate_checklists_for_tasks(
            tasks_with_ids=checklist_inputs,
            analysis_report=analysis_report,
        )
    except Exception as exc:
        logger.warning(f"Checklist generation failed for preview payload: {exc}")

    for task in tasks_needing_checklists:
        raw_items = checklist_map.get(task["task_id"]) if isinstance(checklist_map, dict) else None
        if isinstance(raw_items, list):
            items = [
                str(item.get("text") or "").strip()
                for item in raw_items
                if isinstance(item, dict) and str(item.get("text") or "").strip()
            ]
            if items:
                # Ensure at least 4 checklist items as per architect rules
                while len(items) < 4:
                    filler_steps = [
                        "analyze current module",
                        "design interface",
                        "implement service layer",
                        "write unit tests",
                        "update documentation",
                    ]
                    for step in filler_steps:
                        if len(items) >= 4:
                            break
                        if step not in items:
                            items.append(step)

                task["checklists"] = [
                    {
                        "title": "Planning" if task["type"] in {"epic", "feature"} else "Execution",
                        "items": items,
                    }
                ]
                continue

        task["checklists"] = _fallback_checklist(task["title"], task["type"])



async def _generate_ai_tasks(
    *,
    analysis_report: str,
    reporter: str,
    project_deadline: str,
    total_wallet: int,
    project_start: date,
    project_end: date,
    custom_rules: Optional[str],
    project_type: str = "greenfield",
    process_mode: Optional[str] = None,
) -> tuple[List[Dict[str, Any]], int]:

    agents = [{"user_id": 1, "username": reporter}]
    normalized_tasks: List[Dict[str, Any]] = []

    raw_tasks = await ai_service.generate_all_tasks(
        analysis_report=analysis_report,
        agents=agents,
        project_deadline=project_deadline,
        project_wallet=total_wallet,
        process_mode=process_mode,
    )


    for index, raw_task in enumerate(raw_tasks or []):
        task_name = str(raw_task.get("taskName") or "").strip()
        if not task_name:
            continue

        normalized = _normalize_generated_task(
            raw_task,
            sequence_number=len(normalized_tasks) + 1,
            project_start=project_start,
            project_deadline=project_end,
        )
        normalized_tasks.append(normalized)

    def _ai_days(wallet_points: int) -> int:
        """AI-only estimated duration (days) derived from wallet points."""
        w = max(1, min(int(wallet_points or 1), 10))
        # Aggressively faster than human pace: roughly 1/3–1/4 of human duration.
        # For wallet 1..10 this yields 1..3 calendar days.
        return max(1, (w + 3) // 4)

    def _human_days(wallet_points: int) -> int:
        """Human-only estimated duration (days) derived from wallet points."""
        w = max(1, min(int(wallet_points or 1), 10))
        # 1..10 days
        return max(1, w)

    def _mode_days(wallet_points: int) -> int:
        """
        Convert wallet points into an estimated duration (days), strictly based on execution mode:
        - ai_first: AI timeline
        - vibe_coding: AI timeline
        - developer_only: human timeline
        - ai_assist: human timeline (AI assists but calendar follows human pace)
        - coexistence: AI + human simultaneously -> faster than AI-only
        """
        mode = str(process_mode or "").strip().lower()
        ai = _ai_days(wallet_points)
        human = _human_days(wallet_points)

        if mode in {"developer_only", "ai_assist"}:
            return human
        if mode in {"ai_first", "vibe_coding"}:
            return ai
        if mode == "coexistence":
            # Simultaneous execution (AI + human) should be faster than AI-only.
            # Apply a modest compression while keeping a floor of 1 day.
            return max(1, int(round(ai * 0.7)))

        # Unknown -> default to human pace to avoid overly optimistic schedules.
        return human

    def _apply_mode_schedule(tasks: List[Dict[str, Any]]) -> None:
        if not tasks:
            return

        # Let the execution mode strictly decide the calendar duration.
        # We deliberately do NOT scale durations to fit into an existing
        # project window; instead, the project deadline will be derived
        # from the resulting task schedule.
        durations = [_mode_days(t.get("wallet")) for t in tasks]

        mode = str(process_mode or "").strip().lower()

        if mode == "coexistence":
            # Coexistence: model parallel work (AI + human) using 2 lanes.
            # Place tasks on the earliest-available lane to shorten overall project time.
            lane_cursors = [project_start, project_start]
            for t, days in zip(tasks, durations):
                lane_idx = 0 if lane_cursors[0] <= lane_cursors[1] else 1
                start = lane_cursors[lane_idx]
                end = min(project_end, start + timedelta(days=max(days - 1, 0)))
                t["startdate"] = _format_date(start)
                t["deadline"] = _format_date(end)
                lane_cursors[lane_idx] = min(project_end, end + timedelta(days=1))
            return

        # Default: sequential schedule (single lane)
        cursor = project_start
        for t, days in zip(tasks, durations):
            start = cursor
            end = min(project_end, start + timedelta(days=max(days - 1, 0)))
            t["startdate"] = _format_date(start)
            t["deadline"] = _format_date(end)
            cursor = min(project_end, end + timedelta(days=1))

    _apply_mode_schedule(normalized_tasks)

    remaining_wallet = max(
        total_wallet - sum(max(_safe_int(task.get("wallet"), 0), 0) for task in normalized_tasks),
        0,
    )
    return normalized_tasks, remaining_wallet


async def build_local_task_plan_preview(
    *,
    project_token: str,
    project_name: str,
    project_reference: Any = None,
    sprint_reference: Any = None,
    milestone_reference: Any = None,
    analysis_report: str = "",
    analysis_payload: Optional[Dict[str, Any]] = None,
    prerequisites: Optional[List[Dict[str, Any]]] = None,
    reporter_name: Optional[str] = None,
    custom_rules: Optional[str] = None,
    project_type: str = "greenfield",
    process_mode: Optional[str] = None,
) -> Dict[str, Any]:

    analysis_payload = analysis_payload or {}
    prerequisites = prerequisites or []

    reporter = _display_name(reporter_name)
    project_start, project_deadline = _normalize_project_dates(analysis_payload)

    # Always anchor new execution plans from "today" onwards. If the BRD
    # contained an old historical start date (e.g. 2024), we clamp it so
    # that AI timelines are calculated from the current date instead of
    # a past calendar window.
    today = date.today()
    if project_start < today:
        project_start = today
    total_wallet = _derive_total_wallet(analysis_payload, analysis_report)
    deadline_iso = _format_date(project_deadline)
    analysis_context = _build_analysis_context(
        analysis_report,
        prerequisites,
        custom_rules,
        max_chars=0,
    )
    
    # Derive project_type from analysis if not explicitly overriden
    derived_project_type = project_type if project_type != "greenfield" else _derive_project_type(analysis_payload)

    # For mode-based scheduling we use a generous horizon so that the
    # execution mode (AI vs human vs coexistence) strictly controls the
    # resulting project duration, instead of forcing it into any pre-set
    # deadline window derived from the BRD.
    schedule_horizon = project_start + timedelta(days=365 * 3)

    raw_tasks, remaining_wallet = await _generate_ai_tasks(
        analysis_report=analysis_context,
        reporter=reporter,
        project_deadline=deadline_iso,
        total_wallet=total_wallet,
        project_start=project_start,
        project_end=schedule_horizon,
        custom_rules=custom_rules,
        project_type=derived_project_type,
        process_mode=process_mode,
    )

    # ------------------------------------------------------------
    # Mode-based project deadline:
    # The selected process_mode strictly decides the calendar timeline. We derive
    # the project deadline from the scheduled tasks (max task deadline).
    # ------------------------------------------------------------
    mode_project_deadline = project_deadline
    try:
        task_deadlines = []
        for t in raw_tasks or []:
            d = _parse_date(t.get("deadline"))
            if d is not None:
                task_deadlines.append(d)
        if task_deadlines:
            mode_project_deadline = max(task_deadlines)
    except Exception:
        mode_project_deadline = project_deadline

    deadline_iso = _format_date(mode_project_deadline)

    # Now generate sprint/milestone suggestions INSIDE the mode-based project deadline.
    sprint_plan = await ai_service.generate_sprint_milestone_plan(
        analysis_report=analysis_context,
        project_name=project_name,
        project_deadline=deadline_iso,
    )

    sprint_payload = sprint_plan.get("sprint") if isinstance(sprint_plan, dict) else {}
    milestone_payload = sprint_plan.get("milestone") if isinstance(sprint_plan, dict) else {}
    sprint_start_iso, sprint_deadline_iso = _normalize_task_dates(
        sprint_payload.get("start_date"),
        sprint_payload.get("deadline"),
        min_date=project_start,
        max_date=mode_project_deadline,
        require_strict_order=True,
    )
    sprint = {
        "id": "SPR-01",
        "name": str(sprint_payload.get("name") or "Sprint 1").strip() or "Sprint 1",
        "summary": str(sprint_payload.get("summary") or f"Initial sprint for {project_name or 'the project'}").strip(),
        "start_date": sprint_start_iso,
        "deadline": sprint_deadline_iso,
    }
    sprint_start = _parse_date(sprint["start_date"]) or project_start
    sprint_deadline = _parse_date(sprint["deadline"]) or mode_project_deadline
    milestone_start_iso, milestone_deadline_iso = _normalize_task_dates(
        milestone_payload.get("start_date"),
        milestone_payload.get("deadline"),
        min_date=sprint_start,
        max_date=sprint_deadline,
    )
    milestone = {
        "id": "MS-01",
        "name": str(milestone_payload.get("name") or "Phase 1 Complete").strip() or "Phase 1 Complete",
        "sprint_id": sprint["id"],
        "start_date": milestone_start_iso,
        "deadline": milestone_deadline_iso,
    }

    groups_used = _determine_sprint_groups(raw_tasks)
    sprints, milestones, group_to_sprint_idx = _create_sprints_and_milestones(
        groups_used=groups_used,
        project_start=project_start,
        project_deadline=mode_project_deadline,
        project_name=project_name or "Untitled Project",
    )

    if sprints and sprint:
        sprints[0]["name"] = sprint.get("name") or sprints[0]["name"]
        sprints[0]["summary"] = sprint.get("summary") or sprints[0]["summary"]
    if milestones and milestone:
        milestones[0]["name"] = milestone.get("name") or milestones[0]["name"]

    structured_tasks = _build_structured_tasks(
        raw_tasks,
        project_id=str(project_token or "PROJ-001"),
        project_name=project_name or "Untitled Project",
        sprints=sprints,
        milestones=milestones,
        group_to_sprint_idx=group_to_sprint_idx,
        reporter_name=reporter,
    )
    await _attach_checklists(structured_tasks=structured_tasks, analysis_report=analysis_context)
    preview_tasks = _build_preview_json_tasks(structured_tasks)

    # ------------------------------------------------------------
    # Strategy-aware statistics to help verify architect behaviour
    # ------------------------------------------------------------
    task_type_counts: Dict[str, int] = {}
    domain_counts: Dict[str, int] = {}
    for task in structured_tasks:
        ttype = str(task.get("type") or "").lower()
        if ttype:
            task_type_counts[ttype] = task_type_counts.get(ttype, 0) + 1
        domain = str(task.get("domain") or "").lower()
        if domain:
            domain_counts[domain] = domain_counts.get(domain, 0) + 1

    total_tasks = len(structured_tasks) or 1
    def _ratio(keys: List[str], pool: Dict[str, int]) -> float:
        return sum(pool.get(k, 0) for k in keys) / float(total_tasks)

    strategy_alignment = {
        "project_type": derived_project_type,
        "greenfield_focus_foundation": _ratio(
            ["epic", "feature"], task_type_counts
        ),
        "brownfield_fix_ratio": _ratio(
            ["bug", "task", "story", "refactor"], task_type_counts
        ),
        "modernization_infra_security_ratio": _ratio(
            ["infrastructure", "task", "story"], task_type_counts
        )
        + _ratio(
            ["security", "devops"], domain_counts
        ),
    }

    logger.info(
        "Local plan preview stats: project_type=%s total_tasks=%s type_counts=%s domain_counts=%s",
        derived_project_type,
        len(structured_tasks),
        task_type_counts,
        domain_counts,
    )

    return {
        "status": "success",
        "preview_mode": True,
        "message": (
            f"AI generated {len(structured_tasks)} task preview item(s) across "
            f"{len(sprints)} sprint(s) from the analysis report. "
            "No external task API call was made."
        ),
        "project_start_date": _format_date(project_start),
        "project_deadline": deadline_iso,
        "project_wallet": total_wallet,
        "remaining_wallet": remaining_wallet,
        "tasks_created": len(structured_tasks),
        "sprint_id": sprints[0]["id"] if sprints else "SPR-01",
        "milestone_id": milestones[0]["id"] if milestones else "MS-01",
        "created_sprint": sprints[0] if sprints else {},
        "created_milestone": milestones[0] if milestones else {},
        "created_sprints": sprints,
        "created_milestones": milestones,
        "sprints": sprints,
        "milestones": milestones,
        "tasks": structured_tasks,
        "preview_json": preview_tasks,
        "task_type_counts": task_type_counts,
        "domain_counts": domain_counts,
        "strategy_alignment": strategy_alignment,
    }
