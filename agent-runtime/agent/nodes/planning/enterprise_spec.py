"""Enterprise specification and architectural blueprint node (plan_node).

Synthesizes domain research, architectural patterns (Clean Architecture, DDD,
Microservices, or Reactive SPA), and generates structured step-by-step plans.
"""
from __future__ import annotations

import json
from typing import Any

from agent.model_router import TaskType
from agent.nodes.core.context import NodeContext
from agent.nodes.legacy.frontend_ui_helper import _extract_clarification_blueprint
from agent.prompts.system_prompts import PLANNING_SYSTEM_PROMPT
from agent.state import LangGraphState, Plan, PlanStep, parse_plan_from_text
from agent.tools.tool_executor import ToolExecutor
from agent.tools.tool_registry import ToolPhase
from infrastructure.claude_tool_client import ClaudeToolClient


def plan_node(state: LangGraphState, ctx: NodeContext) -> dict[str, Any]:
    """Generate structured implementation plan with domain research (1-2 turns max)."""
    task_str = str(state.get("task_type", "")).lower()
    if any(k in task_str for k in ("follow_up", "edit", "bug", "question")):
        print("[Graph:PlanNode] Skipping plan for edit/follow-up task.")
        return {"plan_data": None, "plan_text": "", "status": "planned"}

    print("[Graph:PlanNode] Formulating implementation plan & domain research...")
    ctx.post_event("planning_started", {
        "session_id": state["session_id"],
        "task_id": state["task_id"],
    })

    config = ctx.router.route(TaskType.planning, model=state.get("model_name"))
    tools = ctx.registry.get_tools(ToolPhase.planning)  # submit_plan + web_search
    executor = ToolExecutor(ctx.mcp, ctx.registry, event_callback=getattr(ctx, "post_event", None))

    client = ClaudeToolClient(
        model=config.model,
        api_key=config.api_key,
        tools=tools,
        max_tokens=config.max_tokens,
        temperature=config.temperature,
        reality_guard=ctx.reality_guard,
        file_manifest=ctx.active_manifest,
    )

    techstack = state.get("techstack") or {"is_custom": False, "stack": "generic", "project_mode": "greenfield", "architecture_type": "frontend"}
    arch_type = techstack.get("architecture_type", "frontend")
    p_mode = techstack.get("project_mode", "greenfield")
    lang = techstack.get("primary_language", "javascript")

    if arch_type in ("backend", "microservice") or lang in ("java", "python", "go", "rust", "csharp") or techstack.get("is_custom"):
        stack_instructions = (
            f"- TARGET TECH STACK: `{techstack.get('stack')}` ({arch_type}, language: {lang}, mode: {p_mode}).\n"
            "- Architecture & Dependency Plan: You MUST formulate the exact application architecture tree and dependency graph:\n"
            "  1. Dependencies & Manifest: List exact dependencies and build configuration (e.g. pom.xml, requirements.txt, go.mod, package.json).\n"
            "  2. Build & Runtime Config: State required runtime files, environment variables (.env), and main entrypoint.\n"
            "  3. Project Directory Tree: Define clean separation of concerns (models/entities, services/business logic, controllers/endpoints, tests).\n"
            "  4. Contracts & Verification: Plan clean data models, request/response contracts, and test/compilation verification steps.\n"
        )
        default_project_type = techstack.get("stack", "custom")
    elif p_mode == "migration":
        stack_instructions = (
            f"- MIGRATION ARCHITECTURE: Target stack `{techstack.get('stack')}` ({lang}).\n"
            "- Migration Strategy:\n"
            "  1. Audit Legacy Codebase: Read and map existing data structures, APIs, and business rules.\n"
            "  2. Target Stack Scaffolding: Setup modern manifest and directory structure.\n"
            "  3. Incremental Migration: Port logic module-by-module ensuring functional parity.\n"
            "  4. Parity Testing: Validate migrated components against existing requirements.\n"
        )
        default_project_type = techstack.get("stack", "custom")
    else:
        stack_instructions = (
            "- Default Tech Stack: React 18 + Vite + Tailwind CSS (SPA).\n"
            "- LEAN RUNNABLE PROTOTYPE SPECIFICATION (FAST DELIVERY PRINCIPLE):\n"
            "  * Objective: Deliver an engaging, fully functional, interactive runnable prototype as FAST as possible.\n"
            "  * Strict Prototype File Budget: Plan AT MOST 4 to 5 total files:\n"
            "    1. `src/data/mockData.js`: Centralized mock domain data (single file, < 120 lines, 3-5 realistic records per entity).\n"
            "    2. (Optional) `src/services/apiClient.js`: Thin async adapter — include ONLY if explicitly needed.\n"
            "    3. Primary view component: Name it based on the DOMAIN (e.g. `src/components/FlightBoard.jsx` for aviation, "
            "`src/components/PatientQueue.jsx` for healthcare, `src/components/InventoryGrid.jsx` for warehousing, "
            "`src/components/PricingWorkbench.jsx` for pricing/deals). NEVER default to `DashboardView.jsx` unless the app is literally a generic dashboard!\n"
            "    4. Secondary view component (optional): Name it based on the domain-specific secondary function (e.g. `ApprovalDrawer.jsx`, `AuditHistoryTable.jsx`).\n"
            "    5. `src/App.jsx`: Application shell with layout navigation and view switching.\n"
            "  * STRICTLY FORBIDDEN IN INITIAL PROTOTYPE:\n"
            "    - Do NOT plan separate semantic layer files, metric definition files, or narrative generator services.\n"
            "    - Do NOT plan separate `pages/` folders or dozens of micro-components.\n"
            "    - Any secondary sub-views, detail drawers, or modals must be composed directly inline inside the primary view or App.jsx.\n"
            "    - Advanced sub-pages and additional standalone modules will be planned and added incrementally in FUTURE user requests!\n"
            "- Plan Steps: Limit your plan strictly to 4-5 steps corresponding ONLY to the 4-5 core files above.\n"
            "- UI BLUEPRINT SPECIFICATION (MANDATORY):\n"
            "  In your `submit_plan` tool call, include a JSON object in `architecture_notes` with key `\"ui_blueprint\"`:\n"
            "  {\n"
            "    \"layout\": \"sidebar\" | \"top_nav\" | \"split_pane\" | \"card_grid\" | \"kanban\" | \"wizard_flow\" | \"command_center\",\n"
            "    \"theme\": \"light\" | \"dark\",\n"
            "    \"color_palette\": {\"primary\": \"#hex\", \"accent\": \"#hex\"},\n"
            "    \"kpi_style\": \"metric_cards\" | \"status_rings\" | \"progress_bars\" | \"mini_sparklines\" | \"score_badges\",\n"
            "    \"data_visualization\": \"table\" | \"chart\" | \"timeline\" | \"calendar\" | \"kanban_cards\" | \"map\" | \"score_matrix\"\n"
            "  }\n"
            "  CHOOSE LAYOUT & VISUALS THAT UNIQUELY FIT THE REQUESTED APPLICATION DOMAIN!\n"
            "  DIVERSIFY PALETTES: Avoid defaulting to corporate navy blue (#1E3A8A / #0B1120). Select authentic colors matching the industry (warm terracotta, sage/emerald, violet/zinc, amber, or crisp light mode)!\n"
        )
        default_project_type = "react_vite"

    clarification_overrides = _extract_clarification_blueprint(state["prompt"])
    clarification_blueprint_hint = ""
    if clarification_overrides:
        parts = []
        if "theme" in clarification_overrides:
            parts.append(f"theme={clarification_overrides['theme']}")
        if "color_palette" in clarification_overrides:
            cp = clarification_overrides["color_palette"]
            parts.append(f"primary={cp.get('primary', '')}, accent={cp.get('accent', '')}")
        clarification_blueprint_hint = (
            f"\n\nCRITICAL USER PREFERENCE (PRE-ANSWERED — DO NOT USE WEB_SEARCH FOR COLORS/THEME):\n"
            f"The user has already answered the theme/color question. You MUST use these exact values "
            f"in your ui_blueprint: {', '.join(parts)}. "
            f"Do NOT override these with your own aesthetic choices. "
            f"Skip web_search for color palettes — the user's selection is final."
        )
        no_color_search_note = "- Do NOT use web_search for brand colors or visual themes — the user already chose them (see CRITICAL USER PREFERENCE above).\n"
    else:
        no_color_search_note = ""

    if clarification_overrides.get("theme"):
        domain_research_note = (
            "- Domain Research: If this is a specialized domain (e.g. enterprise workflows, logistics, "
            "travel/hospitality, quality reporting), use web_search to discover realistic industry KPIs, "
            "terminology, and mock data schemas ONLY (colors are already specified above — skip color search).\n"
            f"{no_color_search_note}"
        )
    else:
        domain_research_note = (
            "- Domain Research: If this is a specialized domain (e.g. enterprise workflows, logistics, "
            "travel/hospitality, quality reporting), use web_search to discover realistic industry KPIs, "
            "terminology, brand color palettes, and mock data schemas.\n"
            "- If this is a straightforward change or simple UI edit, do NOT use web_search.\n"
        )

    planner_msg = (
        f"Formulate a lean, fast-delivery product blueprint & implementation plan for this prototype.\n\n"
        f"User requirement:\n{state['prompt']}"
        f"{clarification_blueprint_hint}\n\n"
        f"Instructions:\n"
        f"{stack_instructions}"
        f"{domain_research_note}"
        "- Mock Data: Outline realistic domain entities and realistic records (zero dummy 0s).\n"
        "- When ready, call the `submit_plan(title, steps, architecture_notes)` tool to submit the plan."
    )

    messages = [{"role": "user", "content": planner_msg}]

    result = client.run_tool_loop(
        system=PLANNING_SYSTEM_PROMPT,
        messages=messages,
        tool_executor=executor,
        max_iterations=3,
        on_event=ctx.event_callback,
    )

    plan_dict = executor.submitted_plan or {}
    if plan_dict:
        title = plan_dict.get("title", "Implementation Plan")
        steps = plan_dict.get("steps", [])
        plan_obj = Plan(title=title, project_type=default_project_type)
        for s_idx, s in enumerate(steps, 1):
            plan_obj.steps.append(PlanStep(
                step_number=s.get("step_number", s_idx),
                action=s.get("action", "create_component"),
                description=s.get("description", ""),
                files_involved=s.get("files_involved", []),
            ))
    else:
        plan_obj = parse_plan_from_text(result.final_text)

    ui_blueprint = {}
    arch_notes = plan_dict.get("architecture_notes", "")
    if isinstance(arch_notes, dict):
        ui_blueprint = arch_notes.get("ui_blueprint", arch_notes)
    elif isinstance(arch_notes, str) and arch_notes.strip():
        try:
            parsed_arch = json.loads(arch_notes.strip())
            if isinstance(parsed_arch, dict):
                ui_blueprint = parsed_arch.get("ui_blueprint", parsed_arch)
        except Exception:
            pass
        
        if not ui_blueprint:
            try:
                start_idx = arch_notes.find('{"ui_blueprint"')
                if start_idx == -1:
                    start_idx = arch_notes.find('{"layout"')
                if start_idx != -1:
                    brace_depth = 0
                    end_idx = -1
                    for i in range(start_idx, len(arch_notes)):
                        if arch_notes[i] == '{':
                            brace_depth += 1
                        elif arch_notes[i] == '}':
                            brace_depth -= 1
                            if brace_depth == 0:
                                end_idx = i + 1
                                break
                    if end_idx != -1:
                        parsed_substr = json.loads(arch_notes[start_idx:end_idx])
                        if isinstance(parsed_substr, dict):
                            ui_blueprint = parsed_substr.get("ui_blueprint", parsed_substr)
            except Exception:
                pass

    if not ui_blueprint and isinstance(plan_dict.get("ui_blueprint"), dict):
        ui_blueprint = plan_dict["ui_blueprint"]

    if clarification_overrides:
        print(f"[Graph:PlanNode] Applying clarification overrides to ui_blueprint: {clarification_overrides}")
        if "theme" in clarification_overrides:
            ui_blueprint["theme"] = clarification_overrides["theme"]
        if "color_palette" in clarification_overrides:
            existing_palette = ui_blueprint.get("color_palette") or {}
            existing_palette.update(clarification_overrides["color_palette"])
            ui_blueprint["color_palette"] = existing_palette

    plan_text = f"\n\n## Implementation Plan ({plan_obj.title})\n"
    if plan_dict.get("domain_research"):
        plan_text += f"**Domain Research & Brand Palette:** {plan_dict['domain_research']}\n"
    if ui_blueprint:
        plan_text += (
            f"**UI Blueprint:** Layout={ui_blueprint.get('layout')}, Theme={ui_blueprint.get('theme')}, "
            f"Viz={ui_blueprint.get('data_visualization')}\n"
        )
        if clarification_overrides.get("color_palette"):
            cp = clarification_overrides["color_palette"]
            plan_text += (
                f"**MANDATORY User-Selected Colors (MUST USE EXACTLY):** "
                f"primary={cp.get('primary', '')}, accent={cp.get('accent', '')}"
                + (f", background={cp.get('background', '')}" if cp.get('background') else "")
                + f"\n"
                f"**MANDATORY Theme:** {ui_blueprint.get('theme', 'light').upper()} — "
                f"{'ZERO dark backgrounds (bg-zinc-900, bg-slate-900, bg-[#09090B]) allowed.' if ui_blueprint.get('theme') == 'light' else 'ZERO light backgrounds (bg-white, bg-slate-50) allowed.'}\n"
            )
    if plan_dict.get("mock_data_schemas"):
        plan_text += f"**Mock Data Entities:** {plan_dict['mock_data_schemas']}\n"
    if plan_dict.get("app_flow"):
        plan_text += f"**App Flow & Routes:** {plan_dict['app_flow']}\n"
    for step in plan_obj.steps:
        files = ", ".join(step.files_involved[:3]) if step.files_involved else "..."
        plan_text += f"- Step {step.step_number}: {step.description} [{files}]\n"

    ctx.post_event("planning_completed", {
        "session_id": state["session_id"],
        "task_id": state["task_id"],
        "steps": len(plan_obj.steps),
        "plan": plan_obj.title,
    })

    plan_data_dict = plan_obj.to_dict()
    plan_data_dict["ui_blueprint"] = ui_blueprint
    plan_data_dict["domain_research"] = plan_dict.get("domain_research", "")

    return {
        "plan_data": plan_data_dict,
        "plan_text": plan_text,
        "ast_dependency_graph": {
            "title": plan_obj.title,
            "architecture_notes": plan_dict.get("architecture_notes", ""),
            "steps": [s.to_dict() for s in plan_obj.steps],
        },
        "status": "planned",
    }
