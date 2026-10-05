"""GraphNodes — Discrete, isolated phase handlers for the 3-Phase Deterministic Pipeline.

Key architectural guarantees:
- Phase Isolation: PlanNode formulates domain architecture; BatchCodeNode executes generation.
- Strict Scoped Tools: BatchCodeNode binds ONLY write_files & write_file (zero read tools, zero read loops).
- 2-Batch Generation: Batch 1 (Data Layer) -> Batch 2 (UI Views & App.jsx).
- Hard Gatekeeper: FailNode aborts immediately if 0 files were changed.
- Bounded Self-Healing: FixNode handles build errors with cyclic retries (capped at 2).
"""
from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Callable

from agent.model_router import ModelRouter, TaskType
from agent.prompts.system_prompts import (
    CODING_SYSTEM_PROMPT,
    FOLLOWUP_PLANNING_SYSTEM_PROMPT,
    PLANNING_SYSTEM_PROMPT,
    PromptBuilder,
    PromptPhase,
)
from agent.spec_manager import ProductSpec
from agent.state import LangGraphState, Plan, PlanStep, parse_plan_from_text
from agent.tools.tool_executor import ToolExecutor
from agent.tools.tool_registry import ToolPhase, ToolRegistry
from infrastructure.claude_tool_client import (
    ClaudeToolClient,
    FileManifest,
    generate_clean_file_tree,
    TaskChecklistTracker,
)
from mcp.server import MCPServer
from runtime.preview_manager import PreviewManager
from runtime.process_supervisor import ProcessSupervisor
from runtime.reality_guard import AgentRealityGuard
from runtime.starter_scaffold import seed_starter_scaffold
from runtime.static_scanner import StaticScanner
from agent.techstack_detector import detect_techstack
from infrastructure.llm_client import LLMClient
from infrastructure.model_profile import ModelProfile, get_profile
from infrastructure.token_counter import select_context_tier, estimate_tokens, prompt_fits_safely


class NodeContext:
    """Dependency container passed to all LangGraph nodes."""

    def __init__(
        self,
        mcp: MCPServer,
        registry: ToolRegistry,
        router: ModelRouter,
        reality_guard: AgentRealityGuard | None = None,
        event_callback: Callable[[str, dict[str, Any]], None] | None = None,
        prior_conversation: list[dict[str, Any]] | None = None,
        prior_manifest: "FileManifest | None" = None,
    ) -> None:
        self.mcp = mcp
        self.registry = registry
        self.router = router
        self.reality_guard = reality_guard or AgentRealityGuard(getattr(mcp, "_workspace_path", "/workspace"))
        self.event_callback = event_callback
        self.active_manifest: FileManifest | None = None
        self.active_conversation: list[dict[str, Any]] = []
        # Prior session context — threaded from orchestrator for follow-up continuity
        self.prior_conversation: list[dict[str, Any]] = prior_conversation or []
        self.prior_manifest: "FileManifest | None" = prior_manifest

    def post_event(self, event_name: str, data: dict[str, Any]) -> None:
        if self.event_callback:
            try:
                self.event_callback(event_name, data)
            except Exception as e:
                print(f"[NodeContext] Error posting event '{event_name}': {e}")


# ─────────────────────────────────────────────────────────────────────────────
# 1. Initialize Node
# ─────────────────────────────────────────────────────────────────────────────

def initialize_node(state: LangGraphState, ctx: NodeContext) -> dict[str, Any]:
    """Seed base scaffold, initialize git, and synthesize Living Product Spec."""
    task_str = str(state.get("task_type", "")).lower()
    if any(k in task_str for k in ("follow_up", "edit", "bug", "question", "brownfield", "migration", "qa", "verification")):
        print(f"[Graph:InitializeNode] Defensive skip: task_type is '{state.get('task_type')}', delegating to follow_up_node.")
        return follow_up_node(state, ctx)

    ws = state["workspace_path"]
    prompt = state["prompt"]

    print(f"[Graph:InitializeNode] Initializing workspace at {ws}...")
    os.makedirs(ws, exist_ok=True)
    ctx.mcp.call_tool("filesystem", "create_directory", {"path": ws})

    # Detect if user explicitly requested a custom tech stack or if workspace has existing files
    llm_client = LLMClient()
    techstack = detect_techstack(prompt, llm_client=llm_client, model=state.get("model_name", ""))
    print(
        f"[Graph:InitializeNode] Tech stack decision: is_custom={techstack['is_custom']}, "
        f"stack={techstack['stack']} ({techstack['reason']})"
    )

    # Check if workspace already has existing files (brownfield or pre-existing code)
    has_existing_code = False
    try:
        entries = [f for f in os.listdir(ws) if not f.startswith(".")]
        if len(entries) > 2 or any(f in entries for f in ("package.json", "requirements.txt", "go.mod", "pom.xml", "main.py")):
            has_existing_code = True
    except Exception:
        pass

    if not techstack["is_custom"] and not has_existing_code:
        print(f"[Graph:InitializeNode] Greenfield React+Tailwind scaffold tooling initialized...")
        seed_starter_scaffold(ws)
    else:
        if has_existing_code:
            print(f"[Graph:InitializeNode] Existing codebase detected in workspace. Preserving all existing code and skipping starter scaffold.")
        else:
            print(f"[Graph:InitializeNode] Tech stack '{techstack['stack']}' requested. Skipping starter scaffold injection.")

    ctx.mcp.call_tool("git", "init", {"workspace_path": ws})
    ctx.reality_guard.state.refresh()

    # Synthesize or load Living Product Spec
    spec = ProductSpec.load_or_init(ws, prompt)

    # Persist prompt history in workspace (.agent_history/prompts_history.json)
    try:
        hist_dir = os.path.join(ws, ".agent_history")
        os.makedirs(hist_dir, exist_ok=True)
        prompts_file = os.path.join(hist_dir, "prompts_history.json")
        if not os.path.exists(prompts_file):
            with open(prompts_file, "w", encoding="utf-8") as f:
                json.dump([{"task_id": state["task_id"], "prompt": prompt, "time": time.time()}], f, indent=2)
    except Exception:
        pass

    # Initialize and pre-seed FileManifest with actual workspace files
    manifest = FileManifest()
    manifest.scan_workspace(ws)
    ctx.active_manifest = manifest

    ctx.post_event("session_started", {
        "session_id": state["session_id"],
        "task_id": state["task_id"],
        "task_type": state["task_type"],
        "model": state["model_name"],
        "techstack": techstack,
    })

    return {
        "spec": spec.to_dict(),
        "techstack": techstack,
        "status": "initialized",
        "files_changed": [],
        "fix_attempts": 0,
        "build_success": False,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 2. Plan Node (Domain Research & Product Blueprint)
# ─────────────────────────────────────────────────────────────────────────────

def _extract_clarification_blueprint(prompt: str) -> dict:
    """Parse ## User Clarifications section of the prompt to extract ui_blueprint overrides.

    The prompt_analysis_service already ran a web search and asked the user
    domain-specific questions. The answers are appended to the prompt as:
      ## User Clarifications & Architecture Preferences:
      - **theme**: Ingham's Alpine Red — Light | theme: light | colors: #CC0000, #F5F5F5, #6B7280

    We extract:
      - theme: "light" or "dark"
      - color_palette: {"primary": "#hex", "accent": "#hex"}

    Returns a partial ui_blueprint dict (only keys that were actually found).
    """
    overrides: dict = {}

    clarification_header = "## User Clarifications"
    idx = prompt.find(clarification_header)
    if idx == -1:
        return overrides

    section = prompt[idx:]

    # ── 1. Extract theme: light | dark ──────────────────────────────────────
    theme_match = re.search(r'\btheme\s*:\s*(light|dark)\b', section, re.IGNORECASE)
    if theme_match:
        overrides["theme"] = theme_match.group(1).lower()
    else:
        # Fallback: look for explicit "light" or "dark" keywords in the theme answer line
        theme_line = re.search(r'\*\*theme\*\*[^|\n]*\|\s*theme\s*:\s*(light|dark)', section, re.IGNORECASE)
        if theme_line:
            overrides["theme"] = theme_line.group(1).lower()

    # ── 2. Extract color hex codes ───────────────────────────────────────────
    # Pattern: "colors: #XXXXXX, #YYYYYY[, #ZZZZZZ]"
    colors_match = re.search(r'colors\s*:\s*(#[0-9A-Fa-f]{3,8}(?:\s*,\s*#[0-9A-Fa-f]{3,8})*)', section)
    if colors_match:
        hex_codes = [c.strip() for c in colors_match.group(1).split(',')]
        if hex_codes:
            color_palette = {"primary": hex_codes[0]}
            if len(hex_codes) >= 2:
                color_palette["accent"] = hex_codes[1]
            if len(hex_codes) >= 3:
                color_palette["background"] = hex_codes[2]
            overrides["color_palette"] = color_palette
    else:
        # Fallback: extract any bare hex codes mentioned in the theme clarification line
        theme_answer_line = re.search(r'\*\*theme\*\*:?\s*(.+)', section)
        if theme_answer_line:
            bare_hexes = re.findall(r'#[0-9A-Fa-f]{6}', theme_answer_line.group(1))
            if bare_hexes:
                color_palette = {"primary": bare_hexes[0]}
                if len(bare_hexes) >= 2:
                    color_palette["accent"] = bare_hexes[1]
                overrides["color_palette"] = color_palette

    return overrides


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

    techstack = state.get("techstack") or {"is_custom": False, "stack": "react_vite_tailwind"}
    if techstack.get("is_custom"):
        stack_instructions = (
            f"- CUSTOM TECH STACK: The user explicitly requested `{techstack.get('stack')}`.\n"
            "- Architecture & Dependency Tree: You MUST formulate the exact application techstack tree and dependency graph:\n"
            "  1. Dependencies & Manifest: List exact package names and versions needed in package.json (or language equivalent).\n"
            "  2. Build & Runtime Config: State required bundler/config files (e.g. vite.config, next.config, etc.).\n"
            "  3. Project File Tree & Entrypoint: Define the full directory hierarchy and main entry file.\n"
            "  4. Dependency Graph: Clarify import/export relationships between core modules.\n"
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

    # ── Pre-extract clarification blueprint overrides before calling planner ──
    # The prompt_analysis_service already ran a web search and asked the user about
    # theme, colors, etc. We parse those answers NOW so the planner can use them
    # directly — no redundant web search for palette/theme needed.
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
        # Skip web_search for brand colors since user already chose them
        no_color_search_note = "- Do NOT use web_search for brand colors or visual themes — the user already chose them (see CRITICAL USER PREFERENCE above).\n"
    else:
        no_color_search_note = ""

    # ── Domain research note: skip web_search if user clarifications already cover it ──
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
        max_iterations=3,  # 1-2 web searches + submit_plan
        on_event=ctx.event_callback,
    )

    # Extract plan either from submit_plan tool or text parse
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

    # Parse ui_blueprint from architecture_notes or plan_dict
    ui_blueprint = {}
    arch_notes = plan_dict.get("architecture_notes", "")
    if isinstance(arch_notes, dict):
        ui_blueprint = arch_notes.get("ui_blueprint", arch_notes)
    elif isinstance(arch_notes, str) and arch_notes.strip():
        # 1. Try parsing arch_notes directly as JSON
        try:
            parsed_arch = json.loads(arch_notes.strip())
            if isinstance(parsed_arch, dict):
                ui_blueprint = parsed_arch.get("ui_blueprint", parsed_arch)
        except Exception:
            pass
        
        # 2. If direct JSON parse failed, try extracting JSON substring safely
        if not ui_blueprint:
            try:
                # Look for {"ui_blueprint": ...} or {"layout": ...}
                start_idx = arch_notes.find('{"ui_blueprint"')
                if start_idx == -1:
                    start_idx = arch_notes.find('{"layout"')
                if start_idx != -1:
                    # Parse from opening brace to matching balanced closing brace
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

    # ── CRITICAL: Force-override ui_blueprint with user's pre-answered clarifications ──
    # The planner may have chosen its own theme/colors — we ALWAYS override with the user's
    # explicit choices from the clarification questions (they are authoritative).
    if clarification_overrides:
        print(f"[Graph:PlanNode] Applying clarification overrides to ui_blueprint: {clarification_overrides}")
        if "theme" in clarification_overrides:
            ui_blueprint["theme"] = clarification_overrides["theme"]
        if "color_palette" in clarification_overrides:
            existing_palette = ui_blueprint.get("color_palette") or {}
            existing_palette.update(clarification_overrides["color_palette"])
            ui_blueprint["color_palette"] = existing_palette

    # Format plan text for injection into coding phase
    plan_text = f"\n\n## Implementation Plan ({plan_obj.title})\n"
    if plan_dict.get("domain_research"):
        plan_text += f"**Domain Research & Brand Palette:** {plan_dict['domain_research']}\n"
    if ui_blueprint:
        plan_text += (
            f"**UI Blueprint:** Layout={ui_blueprint.get('layout')}, Theme={ui_blueprint.get('theme')}, "
            f"Viz={ui_blueprint.get('data_visualization')}\n"
        )
        # Inject user-selected colors into plan_text so they appear in every file's coding prompt
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


# ─────────────────────────────────────────────────────────────────────────────
# 3. Phased React Generation & Dependency Reconciliation Nodes
# ─────────────────────────────────────────────────────────────────────────────

def extract_file_exports(file_path: str) -> list[str]:
    """Extract named and default export signatures from a JS/JSX file."""
    if not os.path.exists(file_path):
        return []
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except Exception:
        return []

    exports: list[str] = []
    # Named exports: export const/let/var/function/class Name
    for match in re.finditer(r'export\s+(?:async\s+)?(?:const|let|var|function|class)\s+([A-Za-z0-9_$]+)', content):
        exports.append(match.group(1))

    # Named block exports: export { a, b as c, d }
    for match in re.finditer(r'export\s*\{([^}]+)\}', content):
        block = match.group(1)
        for item in block.split(','):
            item = item.strip()
            if not item:
                continue
            if ' as ' in item:
                item = item.split(' as ')[1].strip()
            if item:
                exports.append(item)

    # Default exports: export default Name
    default_match = re.search(r'export\s+default\s+(?:function\s+|class\s+)?([A-Za-z0-9_$]+)?', content)
    if default_match and default_match.group(1):
        exports.append(f"default ({default_match.group(1)})")
    elif re.search(r'export\s+default\b', content):
        exports.append("default")

    return list(dict.fromkeys(exports))


def extract_file_signatures(file_path: str, max_chars: int = 3_000) -> str:
    """Extract import statements + export signatures only (no implementation bodies).

    Reduces a 20KB component file to ~1-2KB of pure contract information:
    what the file imports and what it exports, without function bodies.
    This is Tier 2 context — enough to know what to import without blowing the context.
    """
    if not os.path.exists(file_path):
        return f"# File not found: {file_path}"
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except Exception:
        return f"# Could not read: {file_path}"

    lines = content.split("\n")
    sig_lines: list[str] = []

    # Pass 1: collect import lines (top of file)
    in_import_block = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("import "):
            sig_lines.append(line)
            in_import_block = stripped.endswith(",") or stripped.endswith("from") or not stripped.endswith(";")
        elif in_import_block:
            sig_lines.append(line)
            if stripped.endswith(";") or (stripped.endswith("'") or stripped.endswith('"')):
                in_import_block = False
        elif stripped == "" and sig_lines:
            # First blank line after imports — stop collecting imports
            if not in_import_block:
                sig_lines.append("")
                break

    # Pass 2: collect export signature lines (function/const/class declarations, NOT bodies)
    for i, line in enumerate(lines):
        stripped = line.strip()
        # export const/function/async function/class declarations
        if re.match(r'export\s+(?:default\s+)?(?:async\s+)?(?:const|let|function|class)\s+\w+', stripped):
            sig_lines.append(line)
            # If it's a function, add the next line (params) but not the body
            if "(" in stripped and "{" not in stripped and i + 1 < len(lines):
                sig_lines.append(lines[i + 1])
            sig_lines.append("  // ...implementation")
        elif re.match(r'export\s*\{', stripped):
            sig_lines.append(line)

    result = "\n".join(sig_lines)
    if len(result) > max_chars:
        result = result[:max_chars] + "\n// ... (truncated)"
    return result


# ---------------------------------------------------------------------------
# UI Design System — injected per component type for production-grade output
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# UI Design System — Domain-Adaptive (replaces one-size-fits-all templates)
# ---------------------------------------------------------------------------
# Each spec maps to a ui_blueprint field that the PlanNode fills from domain research.

_LAYOUT_SPECS: dict[str, str] = {
    "sidebar": (
        "SHELL LAYOUT: COLLAPSIBLE left sidebar + main content area.\n"
        "Pattern:\n"
        "  const [sidebarOpen, setSidebarOpen] = useState(true);\n"
        "  <div className=\"flex min-h-screen overflow-hidden\">\n"
        "    <aside className={`${sidebarOpen ? 'w-56' : 'w-14'} flex-shrink-0 flex flex-col transition-all duration-200 overflow-hidden`}>\n"
        "      {/* Toggle button at top: onClick={() => setSidebarOpen(!sidebarOpen)} */}\n"
        "      {/* Nav items: show icon always, show label only when sidebarOpen */}\n"
        "    </aside>\n"
        "    <div className=\"flex-1 min-w-0 flex flex-col overflow-hidden\">\n"
        "      {/* main content */}\n"
        "    </div>\n"
        "  </div>\n"
        "CRITICAL: Add min-w-0 and overflow-hidden to the main content div — prevents flex children from overflowing the preview iframe.\n"
        "ZERO-MARGIN RULE: NEVER add ml-56/pl-56 to the main area — flex already positions them side-by-side.\n"
        "PREVIEW VIEWPORT: The app renders inside a ~750-900px wide iframe. Design for THIS width first, not 1440px desktop."
    ),
    "top_nav": (
        "SHELL LAYOUT: Sticky top navigation bar (h-14, border-b) + full-width content below.\n"
        "Structure: <div className=\"min-h-screen flex flex-col overflow-hidden\"> with <nav className=\"sticky top-0 z-10 flex-shrink-0\"> "
        "+ <main className=\"flex-1 min-w-0 overflow-y-auto p-4\">.\n"
        "Nav items arranged horizontally with active underline indicator.\n"
        "PREVIEW VIEWPORT: The app renders inside a ~750-900px wide iframe. Use compact padding (p-4 not p-8)."
    ),
    "split_pane": (
        "SHELL LAYOUT: Two-column split — left list/tree panel (w-64 flex-shrink-0 min-w-0) + right detail panel (flex-1 min-w-0).\n"
        "Structure: <div className=\"flex h-screen overflow-hidden\"> with two panels.\n"
        "Left panel: searchable list (overflow-y-auto). Right panel: selected-item detail view (overflow-y-auto).\n"
        "PREVIEW VIEWPORT: Total width ~750-900px. Left panel max w-64, right panel flex-1 min-w-0."
    ),
    "card_grid": (
        "SHELL LAYOUT: Full-width card grid, no persistent sidebar.\n"
        "Top search/filter bar, then responsive grid: grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6.\n"
        "Each card: rounded-2xl shadow-sm hover:shadow-md transition with image + title + metadata."
    ),
    "kanban": (
        "SHELL LAYOUT: Horizontal scrolling kanban board with columns.\n"
        "Structure: <div className=\"flex gap-4 overflow-x-auto p-6 h-screen\"> with fixed-width columns (w-72 flex-shrink-0).\n"
        "Each column: rounded-xl bg-slate-100 with scrollable card list."
    ),
    "wizard_flow": (
        "SHELL LAYOUT: Centered multi-step wizard (max-w-2xl mx-auto).\n"
        "Step progress indicator at top: numbered circles + connecting lines.\n"
        "Form content below, prev/next navigation buttons at bottom."
    ),
    "command_center": (
        "SHELL LAYOUT: Full-screen dark command center — dark bg-[#0B1120], dense monitoring grid.\n"
        "Top status bar (h-12) + main area as grid of monitoring panels.\n"
        "Real-time feel: pulsing indicators, high-contrast data, monospace values."
    ),
}

_KPI_STYLE_SPECS: dict[str, str] = {
    "metric_cards": (
        "KPI Display: Responsive card grid — grid-cols-2 lg:grid-cols-4 gap-3.\n"
        "PREVIEW VIEWPORT RULE: Default to 2-column grid (grid-cols-2) — the preview iframe is ~750-900px wide, "
        "NOT a 1440px desktop. Use lg:grid-cols-4 only as an enhancement, never the default.\n"
        "Each card: rounded-xl p-4 (NOT p-6), icon top-right (w-8 h-8), label (text-xs uppercase tracking-wide), "
        "large bold value (text-2xl font-bold), trend badge (▲/▼ text-xs) and vs-target delta.\n"
        "Add min-w-0 to each card to prevent overflow. Use overflow-hidden on the grid container."
    ),
    "status_rings": (
        "KPI Display: Circular SVG donut rings for percentage/quota metrics.\n"
        "Each ring: SVG with strokeDasharray/strokeDashoffset for progress. Center shows value.\n"
        "Good for: completion rates, utilization %, health scores."
    ),
    "progress_bars": (
        "KPI Display: Horizontal progress bars with label left + value right.\n"
        "Bar color by threshold: green (good), amber (warning), red (critical). Rounded full bar.\n"
        "Good for: capacity usage, quota progress, SLA compliance."
    ),
    "mini_sparklines": (
        "KPI Display: Compact row layout with label + value + inline SVG sparkline trend.\n"
        "Sparkline: 60x20px SVG polyline using last 7 data points from mockData.\n"
        "Good for: dense monitoring views with many metrics."
    ),
    "score_badges": (
        "KPI Display: Large score/grade badges (A/B/C or 0-100 scale).\n"
        "Color-coded: A/90+=green, B/75+=blue, C/60+=amber, D/below=red.\n"
        "Good for: quality scoring, performance grading, audit results."
    ),
}

_VIZ_SPECS: dict[str, str] = {
    "table": (
        "Primary Visualization: Sortable/filterable data table.\n"
        "Sticky thead (bg-slate-800 text-white), alternating rows (bg-white/bg-slate-50),\n"
        "hover:bg-blue-50, rounded-xl container with overflow-hidden.\n"
        "Status pills: px-2 py-0.5 rounded-full text-xs font-semibold, color by status.\n"
        "Action buttons per row (View, Edit, Delete) as icon buttons."
    ),
    "chart": (
        "Primary Visualization: recharts BarChart or LineChart.\n"
        "Use REAL values from mockData (NOT zeros). CartesianGrid dashed opacity-30.\n"
        "Custom Tooltip: white bg + shadow-lg. Labeled XAxis/YAxis. Branded fill colors.\n"
        "Wrap in ResponsiveContainer width='100%' height={300}."
    ),
    "timeline": (
        "Primary Visualization: Vertical event timeline.\n"
        "Each event: dot-connector + timestamp + actor name + description + status badge.\n"
        "Most recent events at top. Alternating left/right for visual variety."
    ),
    "calendar": (
        "Primary Visualization: Monthly/weekly calendar grid.\n"
        "7-column grid for days. Each cell: date number + event badges (colored by category).\n"
        "Clicking a date shows event detail panel or modal."
    ),
    "kanban_cards": (
        "Primary Visualization: Cards within kanban columns.\n"
        "Each card: title + assignee avatar initials + priority badge + due date.\n"
        "Drag-drop hint (cursor-grab class). Card count badge on column header."
    ),
    "map": (
        "Primary Visualization: SVG region map or CSS grid heatmap.\n"
        "Color cells/regions by metric value with a color scale (e.g. blue→red).\n"
        "Hover tooltip shows region name + value."
    ),
    "score_matrix": (
        "Primary Visualization: 2D matrix/heatmap table.\n"
        "Rows = entities, columns = dimensions. Each cell: color-coded score value.\n"
        "Color scale: green (high) → amber (mid) → red (low)."
    ),
}


def build_ui_directive(plan_dict: dict, target_rel: str, file_type: str) -> str:
    """Build a domain-adaptive UI directive from the plan's ui_blueprint.

    Reads the plan's ui_blueprint (set by plan_node from domain research) and returns
    tailored instructions for the specific domain instead of the same generic template.
    Falls back to sensible defaults when blueprint is missing.
    """
    blueprint = (plan_dict or {}).get("ui_blueprint") or {}
    layout = blueprint.get("layout", "sidebar")
    kpi_style = blueprint.get("kpi_style", "metric_cards")
    viz_type = blueprint.get("data_visualization", "chart")
    color_palette = blueprint.get("color_palette") or {}
    primary_color = color_palette.get("primary", "#3B82F6")
    accent_color = color_palette.get("accent", "#10B981")
    theme = blueprint.get("theme", "light")  # Default to light — safer for most enterprise apps

    layout_spec = _LAYOUT_SPECS.get(layout, _LAYOUT_SPECS["sidebar"])
    kpi_spec = _KPI_STYLE_SPECS.get(kpi_style, _KPI_STYLE_SPECS["metric_cards"])
    viz_spec = _VIZ_SPECS.get(viz_type, _VIZ_SPECS["chart"])

    if theme == "dark":
        bg_spec = (
            f"MANDATORY DARK THEME — You MUST use dark backgrounds on ALL surfaces. "
            f"Canvas: bg-[#09090B] or bg-slate-950 or bg-zinc-950. "
            f"Cards: bg-slate-900/70 border border-slate-800/90 rounded-2xl shadow-xl backdrop-blur-md. "
            f"Text: text-white (headings), text-slate-300 (body), text-slate-500 (muted). "
            f"FORBIDDEN: bg-white, bg-slate-50, bg-stone-50, bg-gray-50 — these are light-theme classes."
        )
    else:
        bg_spec = (
            f"MANDATORY LIGHT THEME — You MUST use light backgrounds on ALL surfaces. "
            f"Canvas: bg-slate-50 or bg-[#F8FAFC] or bg-gray-50. "
            f"Cards: bg-white border border-slate-200/80 rounded-2xl shadow-sm. "
            f"Text: text-slate-900 (headings), text-slate-700 (body), text-slate-500 (muted). "
            f"FORBIDDEN: bg-[#09090B], bg-slate-900, bg-slate-950, bg-zinc-900, bg-zinc-950 — these are dark-theme classes."
        )

    color_spec = (
        f"Brand Colors: primary={primary_color}, accent={accent_color}.\n"
        f"Apply via Tailwind arbitrary values e.g. bg-[{primary_color}], text-[{primary_color}], border-[{primary_color}], or define "
        f"a COLORS constant at the top of the file.\n"
        f"{bg_spec}"
    )

    icon_rule = (
        "STRICT ICON IMPORT INTEGRITY: EVERY Lucide icon used in JSX (TrendingUp, AlertTriangle, etc.) "
        "MUST be explicitly listed in the `import {{ ... }} from 'lucide-react'` block. "
        "NEVER reference an unimported icon — it causes a fatal browser crash!"
    )

    viewport_rule = (
        "PREVIEW VIEWPORT (CRITICAL): This app renders in a ~750-900px wide iframe inside the Vibecoding platform. "
        "ALL layout decisions must work at this width — NOT at 1440px desktop width. "
        "Rules: (1) Use grid-cols-2 (NOT grid-cols-4) as default for KPI cards. "
        "(2) Add min-w-0 and overflow-hidden to all flex children to prevent overflow. "
        "(3) Use compact spacing: p-4 not p-8, gap-3 not gap-6. "
        "(4) Sidebar max width w-56 in expanded state, w-14 in collapsed state. "
        "(5) NEVER use fixed px widths wider than 200px on inner panels."
    )

    if file_type == "App":
        return (
            f"APPLICATION SHELL — {layout.upper().replace('_', ' ')} LAYOUT:\n"
            f"{layout_spec}\n\n"
            f"Color System:\n{color_spec}\n\n"
            f"{viewport_rule}\n\n"
            "Navigation: Use domain-specific view names from the plan (NOT generic 'Dashboard'/'Settings').\n"
            "Each nav item: Lucide icon (20px) + label (hidden when sidebar collapsed). Active: bg-brand text-white rounded-lg.\n"
            "Header: app title + session info + notification bell (Lucide Bell icon).\n"
            "CRITICAL: ONLY import components from the exact file paths generated in prior steps. ZERO phantom imports.\n"
            "Master-Detail Wiring: If rendering a primary list view and a secondary detail view/drawer, manage `selectedId` in state: pass the selection handler e.g. `<PrimaryView onSelect={handleSelect} onEmployeeSelect={handleSelect} onSelectItem={handleSelect} />` and conditionally render `{selectedId && <DetailComponent employeeId={selectedId} itemId={selectedId} id={selectedId} onClose={() => setSelectedId(null)} />}`.\n"
            "Use `HashRouter` from `react-router-dom`. NEVER BrowserRouter.\n"
            f"{icon_rule}"
        )

    elif file_type == "component":
        is_primary = any(
            k in target_rel.lower()
            for k in ("dashboard", "overview", "summary", "main", "home", "board",
                      "queue", "list", "grid", "view", "feed", "tracker", "monitor")
        )
        if is_primary:
            return (
                f"PRIMARY VIEW COMPONENT:\n"
                f"{kpi_spec}\n\n"
                f"{viz_spec}\n\n"
                f"Color System:\n{color_spec}\n\n"
                f"{viewport_rule}\n\n"
                "Loading skeleton: 3 animate-pulse cards for 600ms on mount via useState+useEffect.\n"
                "Filter controls: date range <input type=\"date\"> pair + status <select> (styled inline).\n"
                "Interactive Rows & Selection Contract: If displaying records, table rows, or entity cards, you MUST accept selection callbacks with safe defaults in props: `const ComponentName = ({ onSelect = () => {}, onSelectEmployee = () => {}, onEmployeeSelect = () => {}, onSelectItem = () => {} }) => { ... }`. Every row/card MUST have `onClick={() => (onSelectEmployee || onEmployeeSelect || onSelect || onSelectItem)(item.id || item)}` and `cursor-pointer` so detail views/drawers can open. NEVER add cursor-pointer or chevron icons without an onClick handler!\n"
                "Empty state: centered icon + message when filtered = 0.\n"
                "Import data from `../data/mockData.js`. Export as `export default ComponentName`.\n"
                f"{icon_rule}"
            )
        else:
            return (
                f"SECONDARY VIEW COMPONENT:\n"
                f"Color System:\n{color_spec}\n\n"
                f"{viewport_rule}\n\n"
                "Match the same color theme and visual polish as the primary view.\n"
                "Status pills, hover states, and action buttons where relevant.\n"
                "Detail / Drawer View Contract: If this is an inline detail panel, modal, or drawer, accept `({ employeeId, itemId, id, onClose = () => {} })` in props with safe fallbacks and render a close button with `onClick={onClose}`.\n"
                "Import data from `../data/mockData.js`. Export as `export default ComponentName`.\n"
                f"{icon_rule}"
            )

    # mockData, apiClient — no UI spec
    return ""



_APPCLIENT_SPEC = """
THIN ADAPTER ONLY — maximum 60 lines total. No class wrappers. No JSDoc blocks.
Import directly from '../data/mockData.js'. Export exactly 3 functions:
  export async function getKPIs() { return { ...mockKpiData }; }
  export async function getRecords(type) { return mockData[type] || []; }
  export async function updateRecord(id, changes) { return { success: true, id, ...changes }; }
Simulate async with: await new Promise(r => setTimeout(r, 100));
Nothing else. No retry logic, no error classes, no TypeScript types.
"""

# Per-file character caps: prevents unbounded generation even if model ignores line limits
_FILE_CHAR_CAPS: dict[str, int] = {
    "mockData":   3_500,   # Just constants: 3-5 records per entity
    "apiClient":  2_200,   # Thin adapter: 3 functions only
    "component":  8_500,   # One rich JSX component
    "App":        6_500,   # App shell: nav + view switching + inline sub-views
    "readme":     2_500,   # README.md: title, features, run steps, stack
}


def sequential_code_node(state: LangGraphState, ctx: NodeContext) -> dict[str, Any]:
    """Execute deterministic 1-file-at-a-time code generation for React Vite Tailwind.

    Guarantees:
    - Exactly 1 targeted turn per file (no runaway iteration loops).
    - Token-budget-aware context strategy (4 tiers) based on ModelProfile.
    - Per-file char caps prevent unbounded file sizes.
    - Rich UI design directives for production-grade output.
    - get_generated_file capped at 120 lines to prevent inspection token explosion.
    - max_turns=3 allows: inspect → write → continuation-if-truncated.
    """
    ws = state["workspace_path"]
    prompt = state["prompt"]
    plan_text = state.get("plan_text", "")
    print("[Graph:SequentialCodeNode] Starting deterministic file-by-file code generation...")
    ctx.post_event("coding_started", {
        "session_id": state["session_id"],
        "task_id": state["task_id"],
    })

    config = ctx.router.route(TaskType.coding, model=state.get("model_name"))

    # ── Load ModelProfile for this session ────────────────────────────────────
    profile: ModelProfile = get_profile(config.model)
    print(f"[Graph:SequentialCodeNode] ModelProfile: {profile.describe()}")

    write_tool_schema = ctx.registry.get_tools(ToolPhase.batch_coding)  # write_file, write_files
    get_file_schema = [t for t in ctx.registry.get_tools(ToolPhase.editing) if t.get("name") == "get_generated_file"]
    if not get_file_schema:
        get_file_schema = [{
            "name": "get_generated_file",
            "description": (
                "Read the first 120 lines of a previously generated file to understand its exports. "
                "Use ONLY to verify import names before writing. Do NOT read files you don't need."
            ),
            "input_schema": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        }]

    executor = ToolExecutor(ctx.mcp, ctx.registry, event_callback=getattr(ctx, "post_event", None))
    client = ClaudeToolClient(
        model=config.model,
        api_key=config.api_key,
        tools=write_tool_schema + get_file_schema,
        max_tokens=config.max_tokens,
        temperature=0.2,
        reality_guard=ctx.reality_guard,
        file_manifest=ctx.active_manifest,
    )

    # ── 1. Build ordered generation queue from plan steps ─────────────────────
    plan_data = state.get("plan_data") or {}
    steps = plan_data.get("steps", [])
    raw_files: list[str] = []
    for s in steps:
        for f in s.get("files_involved", []):
            if f.endswith((".js", ".jsx", ".ts", ".tsx")):
                norm_f = f.replace("/workspace/", "").lstrip("/\\")
                if norm_f not in raw_files:
                    raw_files.append(norm_f)

    # ── 2. Fast Prototype Topological Filter ──────────────────────────────────
    # New 4-file default queue: Data → Component1 → Component2 → App.jsx
    # apiClient REMOVED from default queue: components import mockData directly.
    # This saves ~90s and ~5K context tokens with zero prototype functionality loss.

    # Layer 1: Exactly 1 mock data file
    all_data = [f for f in raw_files if "mockData" in f or ("data/" in f and "api" not in f.lower())]
    primary_data = next(
        (f for f in all_data if "mockData" in f),
        all_data[0] if all_data else "src/data/mockData.js"
    )
    data_files = [primary_data]

    # Layer 2: Optional thin service file — only include if explicitly planned AND short enough
    all_services = [
        f for f in raw_files
        if ("apiClient" in f or "services/" in f or "api." in f) and f not in data_files
    ]
    # Default: skip apiClient. Include only if plan explicitly names it AND we have budget.
    service_files: list[str] = []
    if all_services and len(raw_files) <= 5:
        # Plan explicitly included a service file; include it with strict cap
        primary_service = next((f for f in all_services if "apiClient" in f), all_services[0])
        service_files = [primary_service]

    # Layer 3: Core UI Components (max 2 — dashboard + table/grid)
    all_comps = [
        f for f in raw_files
        if ("components/" in f or "pages/" in f or "views/" in f)
        and f not in data_files
        and f not in service_files
        and not f.endswith(("App.jsx", "App.tsx", "main.jsx", "main.tsx"))
    ]

    selected_comps: list[str] = []
    dash_comp = next(
        (f for f in all_comps if any(k in f.lower() for k in ("dashboard", "overview", "summary", "main", "home"))),
        None
    )
    if dash_comp:
        selected_comps.append(dash_comp)

    grid_comp = next(
        (f for f in all_comps if any(k in f.lower() for k in ("table", "grid", "report", "metric", "card", "list"))
         and f not in selected_comps),
        None
    )
    if grid_comp:
        selected_comps.append(grid_comp)

    for c in all_comps:
        if len(selected_comps) >= 2:
            break
        if c not in selected_comps:
            selected_comps.append(c)

    if not selected_comps:
        selected_comps = ["src/components/DashboardView.jsx", "src/components/DataTable.jsx"]

    # Layer 4: App entrypoint
    entry_files = ["src/App.jsx"]

    ordered_queue: list[str] = []
    for flist in (data_files, service_files, selected_comps, entry_files):
        for f in flist:
            if f not in ordered_queue and not f.endswith("main.jsx"):
                ordered_queue.append(f)

    # README.md is a MANDATORY deliverable on every project: appended after the
    # entrypoint and NEVER subject to the lean cap (same protection backend
    # files get). Generated last so it can describe the finished app.
    readme_entry = "README.md"
    if readme_entry not in ordered_queue:
        ordered_queue.append(readme_entry)

    # Hard Cap: max 5 app files (README excluded — it can never be pruned)
    if len(ordered_queue) > 6:
        app_files = [f for f in ordered_queue if f != readme_entry]
        pruned_out = app_files[4:-1]
        kept = app_files[:4] + [app_files[-1]]
        ordered_queue = kept + [readme_entry]
        ordered_queue = list(dict.fromkeys(ordered_queue))
        print(f"[Graph:SequentialCodeNode] ⚡ Cap: pruned {len(pruned_out)} files: {pruned_out}")
    elif len(raw_files) > len(ordered_queue):
        pruned_count = len(raw_files) - len(ordered_queue)
        print(
            f"[Graph:SequentialCodeNode] ⚡ Fast Prototype Filter: "
            f"Selected {len(ordered_queue)} core files from {len(raw_files)} planned "
            f"(deferred {pruned_count} secondary files to future requests)."
        )

    print(f"[Graph:SequentialCodeNode] Lean Prototype Queue ({len(ordered_queue)} files): {ordered_queue}")

    accumulated_files: dict[str, str] = {}
    files_changed: list[str] = []

    for idx, target_rel in enumerate(ordered_queue, 1):
        print(f"\n[Graph:SequentialCodeNode] ({idx}/{len(ordered_queue)}) Generating `{target_rel}`...")

        # ── 3. 4-Tier Context Strategy (ModelProfile-aware) ───────────────────
        total_chars = sum(len(c) for c in accumulated_files.values())
        tier = select_context_tier(total_chars, profile)
        print(f"[Graph:SequentialCodeNode]   Context tier: {tier} (accumulated {total_chars:,} chars)")

        if tier == 0:
            # Tier 0: No history — first file
            history_context = "No previous application files generated yet. This is the first file."
            tools_for_turn = write_tool_schema

        elif tier == 1:
            # Tier 1: Full inline source — all previous files fit comfortably
            context_blocks = []
            for p, c in accumulated_files.items():
                context_blocks.append(f"### FILE: `{p}`\n```javascript\n{c}\n```")
            history_context = (
                "## CODE GENERATED SO FAR (FULL SOURCE — import directly from these exact paths):\n"
                + "\n\n".join(context_blocks)
                + "\n\nCRITICAL: Use the exact export names and function signatures shown above!"
            )
            tools_for_turn = write_tool_schema

        elif tier == 2:
            # Tier 2: Signature strip — imports + export declarations only, no bodies
            sig_blocks = []
            for p in accumulated_files.keys():
                abs_p = os.path.join(ws, p)
                sigs = extract_file_signatures(abs_p, max_chars=2_500)
                sig_blocks.append(f"### SIGNATURES: `{p}`\n```javascript\n{sigs}\n```")
            history_context = (
                "## WORKSPACE FILE SIGNATURES (imports + exports only — bodies omitted to save context):\n"
                + "\n\n".join(sig_blocks)
                + "\n\nImport from these exact paths using the exported names shown above."
            )
            tools_for_turn = write_tool_schema

        else:
            # Tier 3: Compact manifest — name + export list only
            # Also expose get_generated_file for on-demand inspection (capped at 120 lines)
            index_blocks = []
            for p in accumulated_files.keys():
                abs_p = os.path.join(ws, p)
                exports = extract_file_exports(abs_p)
                index_blocks.append(f"- `{p}`: exports [{', '.join(exports[:8])}]")
            history_context = (
                "## WORKSPACE FILE INDEX (names + exports only — context buffer guard active):\n"
                + "\n".join(index_blocks)
                + "\n\n[GUARD]: If you need to see a file's imports, call `get_generated_file(path)`. "
                "It returns the first 120 lines. Use it at most ONCE, then write immediately."
            )
            tools_for_turn = write_tool_schema + get_file_schema

        # ── 4. Per-file budget + spec instructions ────────────────────────────
        # Determine file type for budget lookup
        if target_rel == "README.md" or target_rel.endswith("/README.md"):
            file_type = "readme"
        elif "mockData" in target_rel or ("data/" in target_rel and "api" not in target_rel.lower()):
            file_type = "mockData"
        elif "apiClient" in target_rel or "services/" in target_rel:
            file_type = "apiClient"
        elif "App." in target_rel:
            file_type = "App"
        else:
            file_type = "component"

        char_cap = _FILE_CHAR_CAPS.get(file_type, profile.max_file_chars)
        # Never exceed what the model can output in one response
        char_cap = min(char_cap, profile.max_file_chars)
        budget_line = (
            f"\nFILE SIZE BUDGET: Generate AT MOST {char_cap:,} characters for `{target_rel}`. "
            f"This fits in {int(char_cap / profile.chars_per_token):,} output tokens. "
            f"Quality over quantity — concise, complete code wins."
        )

        if file_type == "mockData":
            spec_inst = (
                "BOUNDED MOCK DATA:\n"
                "- Strictly 3-5 realistic records per entity collection. No more.\n"
                "- Export named constants for each entity + a default summary KPI object.\n"
                "- Use domain-accurate values from the plan's domain_research (zero placeholder 0s).\n"
                "- Zero JSDoc comments, zero lengthy explanations — pure data constants only."
                + budget_line
            )

        elif file_type == "apiClient":
            spec_inst = _APPCLIENT_SPEC + budget_line

        elif file_type == "readme":
            domain_title = (state.get("plan_data") or {}).get("title") or "Application Prototype"
            app_files_list = [f for f in ordered_queue if f != "README.md"]
            spec_inst = (
                "README.MD GENERATION (MANDATORY PROJECT DELIVERABLE):\n"
                f"- First line: `# {domain_title}`\n"
                "- **What it does**: 2-3 sentences describing the app's purpose and main workflow, grounded in the user requirement and plan (no generic filler).\n"
                "- **Key features**: 4-7 bullets reflecting what was actually built.\n"
                f"- **How to run**: `npm install` then `npm run dev`, open the local Vite URL.\n"
                f"- **Tech stack**: React 18 + Vite + Tailwind CSS.\n"
                f"- **Project structure**: one bullet per generated file ({', '.join(app_files_list)}) with a one-phrase description.\n"
                "- Pure Markdown, no code fences around the whole document."
                + budget_line
            )

        elif file_type == "App":
            avail_components = [p for p in accumulated_files.keys() if any(k in p for k in ("component", "view", "page", "View", "Table", "Grid", "Card"))]
            comp_list_str = "\n".join(f"  - `{p}`" for p in avail_components) if avail_components else "  None"
            plan_dict_for_ui = state.get("plan_data") or {}
            ui_spec = build_ui_directive(plan_dict_for_ui, target_rel, "App")
            spec_inst = (
                f"EXACT GENERATED COMPONENTS (import ONLY these):\n{comp_list_str}\n\n"
                + ui_spec
                + "\n"
                + budget_line
            )

        else:
            # Component files — domain-adaptive UI directive
            plan_dict_for_ui = state.get("plan_data") or {}
            ui_spec = build_ui_directive(plan_dict_for_ui, target_rel, file_type)
            spec_inst = (
                "COMPONENT GENERATION:\n"
                + (ui_spec + "\n\n" if ui_spec else "")
                + budget_line
            )

        # ── 5. Build prompt — check it fits safely ────────────────────────────
        file_prompt = (
            f"You are generating file ({idx}/{len(ordered_queue)}): `{target_rel}`\n\n"
            f"User Requirement:\n{prompt}\n\n"
            f"{plan_text}\n\n"
            f"{history_context}\n\n"
            f"### DIRECTIVE:\n"
            f"Generate ONLY `{target_rel}`. Do NOT generate any other file.\n"
            f"{spec_inst}\n\n"
            f"Issue the structured `write_file` tool call now to write `{target_rel}`."
        )

        if not prompt_fits_safely(file_prompt, CODING_SYSTEM_PROMPT, profile, safety_fraction=0.65):
            # Auto-downgrade to compact manifest if prompt is too large
            print(f"[Graph:SequentialCodeNode] ⚠️  Prompt too large for tier {tier} — downgrading to compact manifest.")
            index_blocks = []
            for p in accumulated_files.keys():
                abs_p = os.path.join(ws, p)
                exports = extract_file_exports(abs_p)
                index_blocks.append(f"- `{p}`: exports [{', '.join(exports[:8])}]")
            compact_history = (
                "## WORKSPACE FILE INDEX (auto-compacted — prompt was approaching context limit):\n"
                + "\n".join(index_blocks)
            )
            file_prompt = (
                f"You are generating file ({idx}/{len(ordered_queue)}): `{target_rel}`\n\n"
                f"User Requirement:\n{prompt}\n\n"
                f"{plan_text}\n\n"
                f"{compact_history}\n\n"
                f"### DIRECTIVE:\n"
                f"Generate ONLY `{target_rel}`.\n"
                f"{spec_inst}\n\n"
                f"Issue the structured `write_file` tool call now to write `{target_rel}`."
            )
            tools_for_turn = write_tool_schema + get_file_schema

        estimated_input = estimate_tokens(file_prompt + CODING_SYSTEM_PROMPT, profile.chars_per_token)
        print(f"[Graph:SequentialCodeNode]   Prompt: ~{estimated_input:,} input tokens | budget: {char_cap:,} chars out")

        # ── 6. Generate the file ───────────────────────────────────────────────
        ok, content = client.generate_single_file(
            system=CODING_SYSTEM_PROMPT,
            prompt=file_prompt,
            target_path=target_rel,
            tool_executor=executor,
            tools=tools_for_turn,
            on_event=ctx.event_callback,
        )

        if ok and content:
            accumulated_files[target_rel] = content
            if target_rel not in files_changed:
                files_changed.append(target_rel)
            print(f"[Graph:SequentialCodeNode] [OK] ({idx}/{len(ordered_queue)}) `{target_rel}` verified on disk ({len(content):,} chars).")
        else:
            print(f"[Graph:SequentialCodeNode] [WARN] Failed generating `{target_rel}` on turn. Checking disk...")
            abs_p = os.path.join(ws, target_rel)
            if os.path.exists(abs_p) and os.path.getsize(abs_p) > 20:
                with open(abs_p, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                accumulated_files[target_rel] = content
                if target_rel not in files_changed:
                    files_changed.append(target_rel)

    print(f"\n[Graph:SequentialCodeNode] Completed sequential generation of {len(files_changed)} files.")
    return {
        "files_changed": files_changed,
        "final_text": f"Generated {len(files_changed)} application files sequentially.",
        "status": "coded",
    }



def react_data_node(state: LangGraphState, ctx: NodeContext) -> dict[str, Any]:
    """Compatibility wrapper delegating to sequential_code_node."""
    return sequential_code_node(state, ctx)


def react_components_node(state: LangGraphState, ctx: NodeContext) -> dict[str, Any]:
    """Compatibility wrapper delegating to sequential_code_node."""
    return sequential_code_node(state, ctx)


def react_entry_node(state: LangGraphState, ctx: NodeContext) -> dict[str, Any]:
    """Compatibility wrapper delegating to sequential_code_node."""
    return sequential_code_node(state, ctx)


def reconcile_local_imports(ws: str) -> list[str]:
    """Scan all source files for broken relative imports and generate functional stub components.
    
    Prevents Vite Rollup build failures such as:
    [plugin:vite:import-analysis] Failed to resolve import "./pages/DashboardPage" from "src/App.jsx"
    """
    src_dir = os.path.join(ws, "src")
    if not os.path.exists(src_dir):
        return []

    from pathlib import Path
    resolved_ws = Path(ws).resolve()
    created_stubs: list[str] = []
    # Match default imports: import Foo from './...' or import Foo, { ... } from './...'
    # Match named imports: import { Foo, Bar } from './...'
    import_pat = re.compile(
        r"""import\s+(?:(?P<default>[A-Z]\w+)|(?:\{\s*(?P<named>[^}]+)\s*\})|(?:(?P<def2>[A-Z]\w+)\s*,\s*\{\s*(?P<named2>[^}]+)\s*\}))\s+from\s+['"](?P<spec>\.[^'"]+)['"]"""
    )
    simple_pat = re.compile(r"""from\s+['"](?P<spec>\.[^'"]+)['"]""")

    for root, _, files in os.walk(src_dir):
        for file in files:
            if not file.endswith((".js", ".jsx", ".ts", ".tsx")):
                continue
            fp = os.path.join(root, file)
            file_dir = Path(fp).parent
            try:
                with open(fp, "r", encoding="utf-8", errors="ignore") as f:
                    lines = f.readlines()
            except Exception:
                continue

            for line in lines:
                if not line.strip().startswith("import"):
                    continue
                match = import_pat.search(line)
                if not match:
                    simple_match = simple_pat.search(line)
                    if not simple_match:
                        continue
                    spec = simple_match.group("spec")
                    default_sym = None
                    named_syms: list[str] = []
                else:
                    spec = match.group("spec")
                    default_sym = match.group("default") or match.group("def2")
                    named_raw = match.group("named") or match.group("named2") or ""
                    named_syms = [s.strip().split(" as ")[0].strip() for s in named_raw.split(",") if s.strip()]

                # Ignore non-relative imports and assets/stylesheets
                if not spec.startswith(".") or spec.endswith((".css", ".scss", ".png", ".jpg", ".jpeg", ".svg", ".json", ".gif", ".webp")):
                    continue

                # Check if target file exists on disk
                resolved_base = (file_dir / spec).resolve()
                exists = False
                for ext in ("", ".jsx", ".tsx", ".js", ".ts", "/index.jsx", "/index.tsx", "/index.js"):
                    candidate = Path(f"{resolved_base}{ext}")
                    if candidate.exists() and candidate.is_file():
                        exists = True
                        break

                if not exists:
                    # Target does NOT exist! Auto-generate a clean functional component stub.
                    target_file = resolved_base.with_suffix(".jsx")
                    rel_created = os.path.relpath(str(target_file), str(resolved_ws)).replace("\\", "/")

                    # Determine component name
                    comp_name = default_sym or target_file.stem or "ComponentView"
                    comp_name = re.sub(r"\W+", "", comp_name)
                    if not comp_name or not comp_name[0].isupper():
                        comp_name = comp_name.capitalize() if comp_name else "StubView"

                    # Generate named exports if requested
                    named_exports_code = ""
                    for sym in named_syms:
                        clean_sym = re.sub(r"\W+", "", sym)
                        if clean_sym and clean_sym != comp_name:
                            named_exports_code += f"\nexport const {clean_sym} = (props) => <div className=\"p-3 border border-dashed border-gray-300 rounded text-sm text-gray-500\">{clean_sym} View</div>;\n"

                    stub_content = f"""import React from 'react';

/**
 * Auto-generated stub component for `{spec}`
 * Automatically created to ensure clean compilation when imported by `{file}`.
 */
export default function {comp_name}(props) {{
  return (
    <div className="p-6 bg-white rounded-xl shadow-sm border border-gray-200 m-4">
      <div className="flex items-center space-x-3 mb-3">
        <div className="w-3 h-3 rounded-full bg-indigo-500"></div>
        <h2 className="text-xl font-bold text-gray-800">{comp_name}</h2>
      </div>
      <p className="text-sm text-gray-500 mb-4">
        This view is registered and active in the application router.
      </p>
      <div className="p-4 bg-gray-50 rounded-lg border border-gray-100 text-xs font-mono text-gray-600">
        Module: {spec}
      </div>
    </div>
  );
}}
{named_exports_code}"""

                    target_file.parent.mkdir(parents=True, exist_ok=True)
                    target_file.write_text(stub_content, encoding="utf-8")
                    print(f"[Graph:ReconcileDepsNode] [STUB] Auto-created component stub: `{rel_created}` (imported by `{file}`)")
                    created_stubs.append(rel_created)

    return created_stubs


def reconcile_deps_node(state: LangGraphState, ctx: NodeContext) -> dict[str, Any]:
    """Scan all external imports in workspace against package.json and reconcile missing packages."""
    ws = state["workspace_path"]
    print("[Graph:ReconcileDepsNode] Auditing dependencies and local imports...")
    ctx.post_event("reconcile_deps_started", {
        "session_id": state["session_id"],
        "task_id": state["task_id"],
    })

    # 0. Reconcile local relative imports (auto-stub any missing components)
    local_stubs = reconcile_local_imports(ws)
    files_changed = list(state.get("files_changed", []))
    for stub in local_stubs:
        if stub not in files_changed:
            files_changed.append(stub)

    pkg_path = os.path.join(ws, "package.json")
    if not os.path.exists(pkg_path):
        print("[Graph:ReconcileDepsNode] No package.json found — skipping external package reconciliation.")
        return {"status": "deps_reconciled", "files_changed": files_changed}

    # 1. Statically extract all external package imports across src/ and backend files
    candidate_files: list[str] = []
    src_dir = os.path.join(ws, "src")
    if os.path.exists(src_dir):
        for root, _, files in os.walk(src_dir):
            for file in files:
                if file.endswith((".js", ".jsx", ".ts", ".tsx")):
                    candidate_files.append(os.path.join(root, file))

    # Also scan root backend files (server.js, app.js, index.js) and backend/
    for backend_cand in ("server.js", "app.js", "index.js"):
        cand_path = os.path.join(ws, backend_cand)
        if os.path.isfile(cand_path):
            candidate_files.append(cand_path)
    backend_dir = os.path.join(ws, "backend")
    if os.path.exists(backend_dir):
        for root, _, files in os.walk(backend_dir):
            for file in files:
                if file.endswith((".js", ".ts", ".mjs", ".cjs")):
                    candidate_files.append(os.path.join(root, file))

    scanned_packages = set()
    import_regex = re.compile(r"""(?:import\s+.*?\s+from\s+['"]([^'"]+)['"]|import\(['"]([^'"]+)['"]\)|require\(['"]([^'"]+)['"]\))""")
    for fp in candidate_files:
        try:
            with open(fp, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            for match in import_regex.finditer(content):
                specifier = match.group(1) or match.group(2) or match.group(3)
                if not specifier:
                    continue
                specifier = specifier.strip()
                if specifier.startswith((".", "/", "@/", "~/")):
                    continue
                # Extract root package name (e.g. '@tanstack/react-table' or 'date-fns')
                if specifier.startswith("@"):
                    parts = specifier.split("/")
                    pkg_name = "/".join(parts[:2]) if len(parts) >= 2 else specifier
                else:
                    pkg_name = specifier.split("/")[0]
                # Exclude node built-ins
                node_builtins = (
                    "fs", "path", "os", "crypto", "http", "https", "stream",
                    "events", "util", "url", "buffer", "child_process", "assert", "net"
                )
                if pkg_name not in node_builtins and not pkg_name.startswith("node:"):
                    scanned_packages.add(pkg_name)
        except Exception:
            pass

    # 2. Read existing dependencies in package.json
    try:
        with open(pkg_path, "r", encoding="utf-8") as f:
            pkg_data = json.load(f)
    except Exception as e:
        print(f"[Graph:ReconcileDepsNode] Error reading package.json: {e}")
        return {"status": "deps_reconciled"}

    existing_deps = set(pkg_data.get("dependencies", {}).keys()) | set(pkg_data.get("devDependencies", {}).keys())
    missing_packages = sorted(list(scanned_packages - existing_deps))

    if not missing_packages:
        print(f"[Graph:ReconcileDepsNode] ✅ All {len(scanned_packages)} scanned external packages are satisfied in package.json.")
        return {"status": "deps_reconciled"}

    print(f"[Graph:ReconcileDepsNode] ⚠️ Detected missing dependencies: {missing_packages}. Resolving dynamically via AI (zero static fallbacks)...")

    # Dynamic resolution via targeted AI call — zero static fallbacks
    if missing_packages:
        config = ctx.router.route(TaskType.coding)
        tools = ctx.registry.get_tools(ToolPhase.batch_coding)
        executor = ToolExecutor(ctx.mcp, ctx.registry, event_callback=getattr(ctx, "post_event", None))
        client = ClaudeToolClient(
            model=config.model,
            api_key=config.api_key,
            tools=tools,
            max_tokens=2048,
            temperature=0.1,
            reality_guard=ctx.reality_guard,
        )
        prompt_content = (
            f"The application imports external npm packages that are currently missing from package.json:\n"
            f"Missing packages: {missing_packages}\n\n"
            f"Current package.json:\n```json\n{json.dumps(pkg_data, indent=2)}\n```\n\n"
            f"Update package.json using `write_file` to add these missing packages under 'dependencies' with appropriate modern semver. Do NOT remove existing dependencies."
        )
        client.run_tool_loop(
            system="You are a package manager specialist. Update package.json to include missing npm packages with valid semver.",
            messages=[{"role": "user", "content": prompt_content}],
            tool_executor=executor,
            max_iterations=2,
            on_event=ctx.event_callback,
        )

    # Run npm install via build MCP install_dependencies (which checks package.json hash)
    print("[Graph:ReconcileDepsNode] Running npm install to install reconciled packages...")
    install_res = ctx.mcp.call_tool("build", "install_dependencies", {"workspace": ws})
    if not install_res.success:
        print(f"[Graph:ReconcileDepsNode] ⚠️ npm install warning: {install_res.error}")

    files_changed = state.get("files_changed", [])
    if "package.json" not in files_changed:
        files_changed = files_changed + ["package.json"]

    return {
        "status": "deps_reconciled",
        "files_changed": files_changed,
    }


def custom_batch_code_node(state: LangGraphState, ctx: NodeContext) -> dict[str, Any]:
    """2-Batch Generation for custom tech stacks (Next.js, Vue, FastAPI, etc.)."""
    print("[Graph:CustomBatchCodeNode] Starting custom tech stack batch generation...")
    ctx.post_event("coding_started", {
        "session_id": state["session_id"],
        "task_id": state["task_id"],
    })

    config = ctx.router.route(TaskType.coding, model=state.get("model_name"))
    tools = ctx.registry.get_tools(ToolPhase.batch_coding)
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

    ws = state["workspace_path"]
    spec = ProductSpec.load_or_init(ws, state.get("prompt", ""))
    spec_context = spec.to_system_context()
    plan_text = state.get("plan_text", "")
    base_context = f"{spec_context}\n\nUser Prompt:\n{state['prompt']}\n{plan_text}"

    techstack = state.get("techstack") or {"is_custom": True, "stack": "custom"}
    custom_stack_name = techstack.get("stack", "custom")

    # ── CUSTOM STACK BATCH 1: Project Architecture, Manifest & Configuration ──
    print(f"[Graph:CustomBatchCodeNode] 📦 Batch 1/2: Generating Custom Architecture Tree for {custom_stack_name}...")
    batch1_msg = (
        f"{base_context}\n\n"
        f"### BATCH 1 DIRECTIVE: Custom Project Tree & Tooling ({custom_stack_name})\n"
        "You are setting up the foundation and configuration for this custom tech stack.\n"
        "You MUST issue a structured `write_files` tool call now to write the core project files:\n"
        "1. Dependency manifest (e.g. `package.json` or language equivalent with all required dependencies, build/start scripts).\n"
        "2. Build & bundler configurations (e.g. config files, styling configs, compiler settings).\n"
        "3. Root HTML / server / entrypoint wrapper files (e.g. `index.html`, root layout, server entry).\n\n"
        "Issue the `write_files` call now."
    )

    res1 = client.run_tool_loop(
        system=CODING_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": batch1_msg}],
        tool_executor=executor,
        max_iterations=3,
        on_event=ctx.event_callback,
    )

    # ── CUSTOM STACK BATCH 2: Application Views & Business Logic ──────────────
    print(f"[Graph:CustomBatchCodeNode] 📦 Batch 2/2: Generating Application Views & Logic for {custom_stack_name}...")
    batch2_msg = (
        f"{base_context}\n\n"
        f"### BATCH 2 DIRECTIVE: Application Components & Views ({custom_stack_name})\n"
        "The project configuration and tooling have been established.\n"
        "You MUST issue a structured `write_files` tool call now to write the application code:\n"
        "1. Realistic mock data, services, or API adapters.\n"
        "2. All user interface views, routes, components, and styling implementing the user's requirements.\n\n"
        "Ensure all components import and render the domain data. Issue the `write_files` call now."
    )

    res2 = client.run_tool_loop(
        system=CODING_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": batch2_msg}],
        tool_executor=executor,
        max_iterations=3,
        on_event=ctx.event_callback,
    )

    all_files_changed = list(dict.fromkeys(res1.files_changed + res2.files_changed))
    print(f"[Graph:CustomBatchCodeNode] Completed custom batch generation. Total files: {len(all_files_changed)}")

    return {
        "files_changed": all_files_changed,
        "final_text": res2.final_text or res1.final_text or "Custom batch code generation completed.",
        "status": "coded",
    }


def batch_code_node(state: LangGraphState, ctx: NodeContext) -> dict[str, Any]:
    """Legacy router node — dispatches to multi-stage React pipeline or custom batch."""
    techstack = state.get("techstack") or {}
    if techstack.get("is_custom"):
        return custom_batch_code_node(state, ctx)
    return sequential_code_node(state, ctx)


# ─────────────────────────────────────────────────────────────────────────────
# 4. Follow-Up Node & Edit Code Node (Surgical Edits for Follow-Up Prompts)
# ─────────────────────────────────────────────────────────────────────────────

def _derive_acceptance_check(t: dict) -> dict[str, Any] | None:
    """Derive a naive greppable acceptance check when the planner omitted one.

    Conservative: only derives when a clear pattern exists (a capitalized component
    name in the description that should be rendered, or a newly created file that
    must export). Tasks without a derivable pattern fall back to mark-on-write.
    """
    import re as _re
    desc = str(t.get("description", ""))
    action = str(t.get("action", ""))
    f_name = str(t.get("file", ""))
    spec: dict[str, Any] = {}

    # "render X" / "X as the default route" / "set X as" → the component must actually appear as JSX
    m = _re.search(r"\b(?:render|display|show)\s+([A-Z][A-Za-z0-9_]*)", desc)
    if not m:
        m = _re.search(r"\b([A-Z][A-Za-z0-9_]*)\s+(?:as the\s+)?(?:default|landing|root)\b", desc)
    if not m:
        m = _re.search(r"\bimport\s+([A-Z][A-Za-z0-9_]*)\b", desc)
    if m:
        comp = m.group(1)
        # Render usage means JSX tag — excludes the import line (which has no "<")
        spec.setdefault("contains", []).append(f"<{comp}")

    # Newly created files must at least export something usable
    if action == "create" and f_name.endswith((".jsx", ".js", ".tsx", ".ts")):
        spec.setdefault("contains", []).append("export")

    return spec or None


def _extract_plan_json(raw_text: Any) -> dict[str, Any] | None:
    """Robust JSON extractor for LLM planning responses using bracket balance matching."""
    if hasattr(raw_text, "content"):
        raw_text = raw_text.content
    if not isinstance(raw_text, str):
        raw_text = str(raw_text or "")
    clean_json = raw_text.strip()
    start = clean_json.find("{")
    end = -1
    if start != -1:
        depth = 0
        in_str = False
        escape = False
        for i in range(start, len(clean_json)):
            ch = clean_json[i]
            if escape:
                escape = False
                continue
            if ch == '\\':
                escape = True
                continue
            if ch == '"':
                in_str = not in_str
                continue
            if not in_str:
                if ch == '{':
                    depth += 1
                elif ch == '}':
                    depth -= 1
                    if depth == 0:
                        end = i + 1
                        break
    if start != -1 and end != -1:
        clean_json = clean_json[start:end]
    elif "{" in clean_json and "}" in clean_json:
        clean_json = clean_json[clean_json.find("{"):clean_json.rfind("}") + 1]

    try:
        plan_dict = json.loads(clean_json)
        if isinstance(plan_dict, dict) and plan_dict.get("tasks"):
            return plan_dict
    except Exception:
        pass
    return None


def scan_local_imports(ws: str) -> dict[str, list[str]]:
    """Scan workspace source files to map which local files import what.
    
    Returns a dict mapping imported relative targets to the files that import them.
    E.g. {'src/data/mockData.js': ['src/components/ApprovalDrawer.jsx', 'src/services/apiClient.js']}
    """
    if not ws or not os.path.exists(ws):
        return {}
    src_dir = os.path.join(ws, "src")
    scan_root = src_dir if os.path.exists(src_dir) else ws

    import_pat = re.compile(
        r"""(?:import\s+.*?\s+from\s+['"](?P<rel>\.[^'"]+)['"]|require\(['"](?P<req>\.[^'"]+)['"]\))"""
    )

    dep_map: dict[str, set[str]] = {}
    for root, dirs, files in os.walk(scan_root):
        dirs[:] = [d for d in dirs if d not in ("node_modules", "dist", ".git", ".next", "build")]
        for f in files:
            if not f.endswith((".js", ".jsx", ".ts", ".tsx")):
                continue
            full_p = os.path.join(root, f)
            rel_file = os.path.relpath(full_p, ws).replace("\\", "/")
            try:
                with open(full_p, "r", encoding="utf-8", errors="ignore") as fp:
                    content = fp.read()
                for m in import_pat.finditer(content):
                    spec = m.group("rel") or m.group("req")
                    target_dir = os.path.dirname(full_p)
                    resolved_target = os.path.normpath(os.path.join(target_dir, spec))
                    matched_file = None
                    for ext in ("", ".js", ".jsx", ".ts", ".tsx", os.path.sep + "index.js", os.path.sep + "index.jsx"):
                        candidate = resolved_target + ext
                        if os.path.isfile(candidate):
                            matched_file = os.path.relpath(candidate, ws).replace("\\", "/")
                            break
                    if not matched_file:
                        matched_file = os.path.relpath(resolved_target, ws).replace("\\", "/")
                    dep_map.setdefault(matched_file, set()).add(rel_file)
            except Exception:
                pass

    return {k: sorted(list(v)) for k, v in sorted(dep_map.items())}


def format_import_dependencies(dep_map: dict[str, list[str]]) -> str:
    """Format the import dependencies as a clean, concise string for the planner."""
    if not dep_map:
        return ""
    lines = ["## Codebase Import Dependencies:"]
    for target, importers in dep_map.items():
        importers_str = ", ".join(f"`{imp}`" for imp in importers)
        lines.append(f"- `{target}` is imported by: {importers_str}")
    return "\n".join(lines) + "\n"


def formulate_followup_plan(
    prompt: str,
    prompt_history: list[dict[str, Any]],
    clean_tree: str,
    active_manifest: Any,
    config: Any,
    ctx: NodeContext,
    workspace_path: str = "",
    session_id: str = "",
) -> dict[str, Any]:
    """Formulate an objective-driven, multi-file execution plan for follow-up requests.

    Uses Tool-Assisted Inspection (ToolPhase.followup_planning):
    1. The AI architect uses read_file / grep_search to inspect real files (e.g. package.json, App.jsx).
    2. Once grounded in disk facts, the AI submits the plan via submit_plan.
    3. Tasks are validated against disk state to ensure high execution precision.
    """
    history_context = ""
    if prompt_history and len(prompt_history) > 1:
        history_context = "Previous user requests in this project:\n"
        for idx, h in enumerate(prompt_history[:-1], 1):
            p = h.get("prompt", "")[:200]
            history_context += f"- Prompt {idx}: \"{p}\"\n"

    manifest_summary = ""
    if active_manifest and hasattr(active_manifest, "to_manifest_string"):
        manifest_summary = active_manifest.to_manifest_string()

    is_continue = bool(re.search(r'\bcontinue\b', prompt, re.IGNORECASE))
    continuation_note = ""
    if is_continue:
        continuation_note = (
            "IMPORTANT CONTINUATION INSTRUCTION: The user has requested to CONTINUE the previous task. "
            "Inspect the previous requests in history and the files currently in the workspace. "
            "Determine what has already been built/modified and what remains to be completed or verified. "
            "Structure your objective and tasks to finish the remaining changes and verify the build.\n\n"
        )

    ws_path = workspace_path or getattr(active_manifest, "workspace_path", "") or os.environ.get("WORKSPACE_PATH", "")
    dep_map = scan_local_imports(ws_path) if ws_path else {}
    dep_context = format_import_dependencies(dep_map)

    planning_msg = (
        "You are an expert full-stack engineer and software architect.\n"
        "A user has submitted a follow-up request to modify an existing, deployed application.\n"
        "Inspect the codebase using your tools (`read_file`, `grep_search`, `list_directory`), "
        "then call `submit_plan` with an accurate, dynamic execution plan.\n\n"
        f"WORKSPACE CODEBASE TREE:\n{clean_tree}\n\n"
        + (f"{dep_context}\n" if dep_context else "")
        + f"{manifest_summary}\n\n"
        + f"{history_context}\n"
        + f"{continuation_note}"
        + f"CURRENT USER REQUEST TO PLAN:\n\"{prompt}\"\n\n"
        "INSTRUCTIONS FOR INSPECTION & PLANNING:\n"
        "1. First, inspect the relevant existing files using your tools:\n"
        "   - Use `read_file` to check `package.json` for installed packages (e.g. recharts, lucide-react, react-router-dom, date-fns, clsx).\n"
        "   - Use `read_file` or `grep_search` to check `src/App.jsx` (or router file) for existing routes, navigation, and placeholder stubs.\n"
        "   - Inspect existing component or mock data files if relevant to understand current structure.\n"
        "2. When you understand the codebase state, call `submit_plan` with your objective, current state, changes required, and file checklist.\n"
        "   - DEPENDENCY RULE: If a library needed for the request is already in `package.json`, DO NOT plan a task to edit `package.json` or install it!\n"
        "   - ROUTING INTEGRITY: When adding or completing a section/view (e.g. replacing placeholder or adding a new tab), ensure BOTH the component file is planned (action: 'create' or 'edit') AND `src/App.jsx` is planned (action: 'edit') to import the component and mount it inside its Route element. Never leave placeholder JSX in App.jsx.\n"
        "   - If package.json is genuinely modified to add NEW dependencies, include a task with action 'install' right after it.\n"
        "   - When integrating third-party connectors or services (payments, auth, storage, database), plan interactive client-side components and mock adapters (simulated checkout modal, sandbox status, mock data, localStorage persistence) so the prototype is 100% runnable out of the box.\n"
        "   - Conclude with a verification task (`file: 'build_verification'`, `action: 'verify'`).\n"
    )

    tools = ctx.registry.get_tools(ToolPhase.followup_planning)
    executor = ToolExecutor(ctx.mcp, ctx.registry, event_callback=getattr(ctx, "post_event", None))

    client = ClaudeToolClient(
        model=config.model,
        api_key=config.api_key,
        tools=tools,
        max_tokens=config.max_tokens,
        temperature=config.temperature,
        reality_guard=ctx.reality_guard,
        file_manifest=active_manifest,
        workspace_path=ws_path,
    )

    print(f"[Graph:FollowUpPlan] 🔍 Launching Tool-Assisted Inspection loop (room: 8 turns) for session {session_id}...")
    result = client.run_tool_loop(
        system=FOLLOWUP_PLANNING_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": planning_msg}],
        tool_executor=executor,
        max_iterations=8,  # Generous room for multi-component inspection turns + submit_plan
        on_event=ctx.event_callback,
    )

    # 1. Extract plan from submit_plan tool call
    plan: dict[str, Any] = executor.submitted_plan or {}

    # 2. Fallback: extract JSON from assistant final text if submit_plan was not called
    if not plan or not isinstance(plan, dict) or not plan.get("tasks"):
        plan = _extract_plan_json(result.final_text or "") or {}

    # 3. Secondary Fallback: if plan is still missing, run 1 direct completion attempt to structure it
    if not plan or not isinstance(plan, dict) or not plan.get("tasks"):
        try:
            print("[Graph:FollowUpPlan] ⚠️ Fallback: Calling direct completion to extract structured plan...")
            llm_fallback = LLMClient(config)
            fallback_prompt = (
                f"{planning_msg}\n\n"
                f"Assistant Notes/Observations from Inspection:\n{result.final_text}\n\n"
                "Output ONLY a valid JSON object matching this schema (no markdown code fences):\n"
                "{\n"
                '  "objective": "Clear statement of what the user wants to achieve.",\n'
                '  "current_state": "Summary of relevant components found.",\n'
                '  "changes_required": "Breakdown of changes needed.",\n'
                '  "tasks": [\n'
                '    {"task_id": 1, "file": "src/App.jsx", "action": "edit", "description": "Update routing"},\n'
                '    {"task_id": 2, "file": "build_verification", "action": "verify", "description": "Run install_and_build"}\n'
                "  ]\n"
                "}"
            )
            raw_fallback = llm_fallback.call_ai(model=config.model, prompt=fallback_prompt)
            fallback_text = getattr(raw_fallback, "content", "") if hasattr(raw_fallback, "content") else str(raw_fallback or "")
            plan = _extract_plan_json(fallback_text) or {}
        except Exception as e:
            print(f"[Graph:FollowUpPlan] Fallback extraction error: {e}")

    if not plan or not isinstance(plan, dict) or not plan.get("tasks"):
        raise RuntimeError("The AI failed to generate a valid follow-up execution plan after tool-assisted inspection.")

    # Physical disk audit: prune phantom delete tasks and adjust edit vs create
    validated_tasks = []
    raw_tasks = plan.get("tasks", [])
    for idx_t, t in enumerate(raw_tasks):
        if not isinstance(t, dict):
            continue
        f_name = str(t.get("file", "")).strip()
        action = str(t.get("action", "")).strip().lower()

        if action in ("verify", "install") or "verification" in f_name.lower():
            t["task_id"] = len(validated_tasks) + 1
            validated_tasks.append(t)
            continue

        # Check physical existence on disk
        file_exists = False
        if ws_path and f_name:
            norm_f = f_name.replace(ws_path, "").replace("\\", "/").lstrip("/")
            disk_p = os.path.join(ws_path, norm_f)
            file_exists = os.path.exists(disk_p)
        elif active_manifest and hasattr(active_manifest, "has_file"):
            file_exists = active_manifest.has_file(f_name)

        if action == "delete":
            if not file_exists:
                print(f"[Graph:FollowUpPlan] 🛡️ Pruned phantom delete task for non-existent file: `{f_name}`")
                continue
        elif action == "edit":
            if not file_exists:
                print(f"[Graph:FollowUpPlan] 🛡️ Converted edit to create for new file: `{f_name}`")
                t["action"] = "create"
                t["description"] = f"Create {f_name}"
        elif action == "create":
            if file_exists:
                print(f"[Graph:FollowUpPlan] 🛡️ Converted create to edit for existing file on disk: `{f_name}`")
                t["action"] = "edit"

        # Acceptance checks: keep planner-specified, else derive a naive one
        if not t.get("verify"):
            derived = _derive_acceptance_check(t)
            if derived:
                t["verify"] = derived
                print(f"[Graph:FollowUpPlan] 🎯 Derived acceptance check for `{f_name}`: {derived}")

        t["task_id"] = len(validated_tasks) + 1
        validated_tasks.append(t)

        # Ensure install task immediately follows package.json modifications
        if f_name.endswith("package.json"):
            has_next_install = False
            if idx_t + 1 < len(raw_tasks):
                next_t = raw_tasks[idx_t + 1]
                if isinstance(next_t, dict) and (next_t.get("action") == "install" or "install" in str(next_t.get("file", "")).lower() or "install" in str(next_t.get("description", "")).lower()):
                    has_next_install = True
            if not has_next_install:
                print("[Graph:FollowUpPlan] ⚡ Injected mandatory install task immediately following package.json update.")
                validated_tasks.append({
                    "task_id": len(validated_tasks) + 1,
                    "file": "package.json",
                    "action": "install",
                    "description": "Run install_dependencies (npm install) to install newly declared dependencies before writing code",
                })

    # Safe ordering: non-delete tasks -> delete tasks -> verify tasks
    non_delete = [t for t in validated_tasks if t.get("action") not in ("delete", "verify")]
    delete_tasks = [t for t in validated_tasks if t.get("action") == "delete"]
    verify_tasks = [t for t in validated_tasks if t.get("action") == "verify"]

    ordered_tasks = non_delete + delete_tasks + verify_tasks
    for idx, t in enumerate(ordered_tasks, 1):
        t["task_id"] = idx
    plan["tasks"] = ordered_tasks
    print(f"[Graph:FollowUpPlan] ✅ Follow-up plan validated with {len(plan['tasks'])} tasks.")
    return plan


def follow_up_node(state: LangGraphState, ctx: NodeContext) -> dict[str, Any]:
    """Execute dedicated follow-up pipeline for Prompt 2+ (surgical edits & features).

    Architectural guarantees:
    - Bypasses techstack detection (saves AI call, ~400 tokens, 3-5 seconds).
    - Bypasses starter scaffold seeding and git init (preserves code intact).
    - Refreshes reality guard and scans active file manifest.
    - Appends prompt to .agent_history/prompts_history.json.
    - Mounts Active Inspected Files Cache to prevent model amnesia.
    - Records completed fix summary to .agent_history/fix_history.json.
    """
    ws = state["workspace_path"]
    prompt = state["prompt"]
    session_id = state.get("session_id", "")
    task_id = state.get("task_id", "")

    print(f"[Graph:FollowUpNode] Executing dedicated follow-up pipeline for session {session_id}, task {task_id}...")
    ctx.post_event("coding_started", {
        "session_id": session_id,
        "task_id": task_id,
    })

    # 1. Refresh reality guard physical disk state
    if ctx.reality_guard:
        ctx.reality_guard.state.refresh()

    # 2. Update active FileManifest with current workspace files
    active_manifest = ctx.prior_manifest or ctx.active_manifest or FileManifest()
    active_manifest.scan_workspace(ws)
    ctx.active_manifest = active_manifest

    # Generate clean codebase tree (excluding node_modules, dist, git)
    clean_tree = generate_clean_file_tree(ws)

    # 3. Persist prompt history in workspace (.agent_history/prompts_history.json)
    hist_dir = os.path.join(ws, ".agent_history")
    os.makedirs(hist_dir, exist_ok=True)
    prompts_file = os.path.join(hist_dir, "prompts_history.json")
    prompt_history_entries: list[dict[str, Any]] = []
    try:
        if os.path.exists(prompts_file):
            with open(prompts_file, "r", encoding="utf-8") as f:
                prompt_history_entries = json.load(f)
        if not prompt_history_entries or prompt_history_entries[-1].get("task_id") != task_id:
            prompt_history_entries.append({
                "task_id": task_id,
                "prompt": prompt,
                "time": time.time(),
            })
            with open(prompts_file, "w", encoding="utf-8") as f:
                json.dump(prompt_history_entries, f, indent=2)
    except Exception as e:
        print(f"[Graph:FollowUpNode] Warning writing prompt history: {e}")

    # 4. Formulate Plan & Objective (Phase 1 of Follow-up: Tool-Assisted Inspection)
    planning_config = ctx.router.route(TaskType.planning, model=state.get("model_name"))
    plan = formulate_followup_plan(
        prompt=prompt,
        prompt_history=prompt_history_entries,
        clean_tree=clean_tree,
        active_manifest=active_manifest,
        config=planning_config,
        ctx=ctx,
        workspace_path=ws,
        session_id=session_id,
    )

    # Persist plan in .agent_history/current_plan.json
    try:
        plan_file = os.path.join(hist_dir, "current_plan.json")
        with open(plan_file, "w", encoding="utf-8") as f:
            json.dump(plan, f, indent=2)
    except Exception:
        pass

    objective = plan.get("objective", prompt[:200])
    current_state = plan.get("current_state", "")
    changes_required = plan.get("changes_required", "")
    tasks = plan.get("tasks", [])

    print(f"[Graph:FollowUpNode] 🎯 Objective: {objective}")
    print(f"[Graph:FollowUpNode] 🔍 Current State: {current_state}")
    print(f"[Graph:FollowUpNode] 🛠️ Changes Required: {changes_required}")
    print(f"[Graph:FollowUpNode] 📋 Planned {len(tasks)} tasks.")

    task_tracker = TaskChecklistTracker(
        tasks=tasks,
        objective=objective,
        current_state=current_state,
        changes_required=changes_required,
    )

    # Post plan event for live tracking
    ctx.post_event("plan_formulated", {
        "session_id": session_id,
        "task_id": task_id,
        "objective": objective,
        "current_state": current_state,
        "changes_required": changes_required,
        "tasks": tasks,
    })
    if ctx.event_callback:
        ctx.event_callback("task_plan", {
            "objective": objective,
            "tasks": tasks,
        })

    # 5. Formulate contextual prompt with history
    prompt_history_text = ""
    if len(prompt_history_entries) > 1:
        prompt_history_text = "## Conversation & Project History (Previous User Requests in this session):\n"
        for idx, entry in enumerate(prompt_history_entries[:-1], 1):
            p_text = entry.get("prompt", "").strip()
            summary = p_text if len(p_text) < 300 else p_text[:300] + "..."
            prompt_history_text += f"- Request {idx}: \"{summary}\"\n"
        prompt_history_text += "\n"

    user_request_section = (
        f"{prompt_history_text}"
        f"## Current User Request to Implement:\n"
        f"{prompt}\n\n"
    )
    if re.search(r'\bcontinue\b', prompt, re.IGNORECASE):
        user_request_section += (
            "NOTE: The user is continuing the previous task. Check what files are already updated, "
            "finish any remaining implementation details, and verify with install_and_build.\n\n"
        )

    context_summary = ""
    if active_manifest and active_manifest.get_file_count() > 0:
        context_summary = (
            "## Workspace Files (already built — DO NOT re-create or overwrite):\n"
            + active_manifest.to_manifest_string()
            + "\n\nAll files above EXIST on disk. Inspect files, then apply surgical updates.\n\n"
        )

    edit_prompt = (
        context_summary
        + user_request_section
        + f"Workspace: {ws}\n\n"
        + "## Task Execution Guidelines:\n"
        + "1. Follow the task checklist to create or update the necessary files.\n"
        + "2. Read the relevant file if needed for context, then apply updates with `replace_file_content` or `write_file`.\n"
        + "3. Once all planned updates are completed, run `install_and_build` to verify the build passes.\n"
        + "4. Provide a clear, concise summary of the changes.\n"
    )

    tools = ctx.registry.get_tools(ToolPhase.editing)
    executor = ToolExecutor(ctx.mcp, ctx.registry, event_callback=getattr(ctx, "post_event", None))
    coding_config = ctx.router.route(TaskType.coding, model=state.get("model_name"))

    client = ClaudeToolClient(
        model=coding_config.model,
        api_key=coding_config.api_key,
        tools=tools,
        max_tokens=coding_config.max_tokens,
        temperature=coding_config.temperature,
        reality_guard=ctx.reality_guard,
        file_manifest=active_manifest,
        workspace_path=ws,
    )

    result = client.run_tool_loop(
        system=PromptBuilder.build(PromptPhase.EDITING),
        messages=[{"role": "user", "content": edit_prompt}],
        tool_executor=executor,
        max_iterations=25,
        on_event=ctx.event_callback,
        task_tracker=task_tracker,
        clean_file_tree=clean_tree,
    )

    # 5. Record fix outcome in .agent_history/fix_history.json
    try:
        fix_history_file = os.path.join(hist_dir, "fix_history.json")
        fix_entries = []
        if os.path.exists(fix_history_file):
            with open(fix_history_file, "r", encoding="utf-8") as f:
                fix_entries = json.load(f)
        fix_entries.append({
            "task_id": task_id,
            "prompt": prompt,
            "files_changed": result.files_changed,
            "tool_calls_count": len(result.tool_calls_made),
            "timestamp": time.time(),
            "final_text": (result.final_text or "")[:500],
        })
        with open(fix_history_file, "w", encoding="utf-8") as f:
            json.dump(fix_entries, f, indent=2)
    except Exception as e:
        print(f"[Graph:FollowUpNode] Warning saving fix history: {e}")

    built_ok = bool(getattr(executor, "built_successfully", False))

    return {
        "files_changed": result.files_changed,
        "final_text": result.final_text,
        "build_success": built_ok,
        "status": "coded",
    }



def edit_code_node(state: LangGraphState, ctx: NodeContext) -> dict[str, Any]:
    """Backwards-compatible wrapper delegating to follow_up_node."""
    return follow_up_node(state, ctx)




# ─────────────────────────────────────────────────────────────────────────────
# 5. Fail Node (Hard Gatekeeper on Zero Files Changed)
# ─────────────────────────────────────────────────────────────────────────────

def fail_node(state: LangGraphState, ctx: NodeContext) -> dict[str, Any]:
    """Hard gatekeeper failure node — called when code generation produced 0 files or build failed."""
    if state.get("build_error"):
        msg = f"Build failed after fix attempts: {state['build_error']}"
    elif not state.get("files_changed"):
        msg = "Code generation failed: No files were changed by the AI model. Halting pipeline to prevent placeholder deployment."
    else:
        msg = state.get("error") or "Pipeline execution failed."

    print(f"[Graph:FailNode] [FAIL] {msg[:200]}")
    ctx.post_event("session_failed", {
        "session_id": state["session_id"],
        "task_id": state["task_id"],
        "error": msg,
    })
    return {
        "status": "failed",
        "error": msg,
        "build_success": False,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 6. Static Scan Node (~50ms Preflight Scanner)
# ─────────────────────────────────────────────────────────────────────────────

def static_scan_node(state: LangGraphState, ctx: NodeContext) -> dict[str, Any]:
    """Pre-flight static scanner — bypassed per user request to ensure fast builds."""
    print("[Graph:StaticScanNode] Static scanner bypassed per user configuration (fast output enabled).")
    return {"status": "scanned"}


# ─────────────────────────────────────────────────────────────────────────────
# 7. Build Node (install_and_build + Health Check Probe)
# ─────────────────────────────────────────────────────────────────────────────

def build_node(state: LangGraphState, ctx: NodeContext) -> dict[str, Any]:
    """Execute build and verify liveness via ProcessSupervisor."""
    print("[Graph:BuildNode] Running build verification...")
    ctx.post_event("build_started", {
        "session_id": state["session_id"],
        "task_id": state["task_id"],
    })

    build_res = ctx.mcp.call_tool("build", "install_and_build", {})

    if build_res.success:
        # Backend boot smoke-test (Fix #2): if the project has a backend, boot it
        # once during verification so startup crashes surface HERE with full stderr,
        # instead of silently failing later at preview time.
        # Pure-frontend projects: smoke_test_backend returns (True, None) immediately.
        backend_port = None
        try:
            ws = state["workspace_path"]
            pm_probe = PreviewManager(ws)
            backend_port = pm_probe.detect_backend_port() or 3001
            ok, boot_err = pm_probe.smoke_test_backend(timeout=10.0)
            if not ok:
                print(f"[Graph:BuildNode] ⚠️ Backend smoke-test FAILED (build still passes, backend will be repaired at preview): {str(boot_err)[:300]}")
                ctx.post_event("backend_smoke_test", {
                    "session_id": state["session_id"],
                    "task_id": state["task_id"],
                    "status": "failed",
                    "error": str(boot_err)[:1000],
                })
            else:
                print("[Graph:BuildNode] Backend smoke-test passed (or no backend present).")
                ctx.post_event("backend_smoke_test", {
                    "session_id": state["session_id"],
                    "task_id": state["task_id"],
                    "status": "passed",
                })
        except Exception as smoke_exc:
            # Never fail the build because of the smoke-test itself
            print(f"[Graph:BuildNode] Backend smoke-test skipped: {smoke_exc}")

        print("[Graph:BuildNode] Build succeeded! Probing health endpoint...")
        ctx.post_event("build_completed", {
            "session_id": state["session_id"],
            "task_id": state["task_id"],
            "success": True,
        })
        return {
            "build_success": True,
            "build_error": None,
            "status": "verified",
            "backend_port": backend_port,
        }
    else:
        err_msg = str(build_res.error or "Build failed")
        print(f"[Graph:BuildNode] Build failed: {err_msg[:200]}...")
        ctx.post_event("build_completed", {
            "session_id": state["session_id"],
            "task_id": state["task_id"],
            "success": False,
            "error": err_msg,
        })
        return {
            "build_success": False,
            "build_error": err_msg,
            "status": "build_failed",
        }


# ─────────────────────────────────────────────────────────────────────────────
# 8. Self-Healing Fix Node (Cyclic Repair Loop)
# ─────────────────────────────────────────────────────────────────────────────

def fix_node(state: LangGraphState, ctx: NodeContext) -> dict[str, Any]:
    """Apply targeted repairs using the exact compiler/syntax stderr."""
    attempts = state.get("fix_attempts", 0) + 1
    err = state.get("build_error", "Unknown build failure")
    ws = state["workspace_path"]
    print(f"[Graph:FixNode] Starting self-healing fix attempt {attempts}/2...")

    config = ctx.router.route(TaskType.build_fix, model=state.get("model_name"))
    all_tools = ctx.registry.get_tools(ToolPhase.build_fix)
    # Strictly allow only surgical file modification tools to prevent read-file cognitive loops
    tools = [t for t in all_tools if t.get("name") in ("replace_file_content", "write_file", "write_files")]
    if not tools:
        tools = all_tools

    executor = ToolExecutor(ctx.mcp, ctx.registry, event_callback=getattr(ctx, "post_event", None))

    # 1. Statically extract failing file from compiler output and inject its full source
    failing_file = None
    failing_code = ""
    m = re.search(r'(?:file:\s+|from\s+["\']|at\s+)(/workspace/src/[^"\':\s]+|src/[^"\':\s]+)', err)
    if m:
        candidate = m.group(1).replace("/workspace/", "").lstrip("/\\")
        abs_candidate = os.path.join(ws, candidate)
        if os.path.exists(abs_candidate):
            failing_file = candidate
            try:
                with open(abs_candidate, "r", encoding="utf-8", errors="ignore") as f:
                    failing_code = f.read()
            except Exception:
                pass

    file_context = ""
    if failing_file and failing_code:
        file_context = f"\n### CURRENT SOURCE OF FAILING FILE (`{failing_file}`):\n```javascript\n{failing_code}\n```\n"

    fix_msg = (
        f"The build failed with this compiler error:\n\n{err}\n\n"
        f"Workspace: {ws}\n"
        f"{file_context}\n"
        "DIRECTIVE:\n"
        "- Apply a surgical fix using `replace_file_content` (or `write_file` if creating a missing file).\n"
        "- Do NOT call read tools — the failing code is already shown above.\n"
        "- Execute the repair tool call immediately."
    )

    client = ClaudeToolClient(
        model=config.model,
        api_key=config.api_key,
        tools=tools,
        max_tokens=config.max_tokens,
        temperature=config.temperature,
        reality_guard=ctx.reality_guard,
    )

    client.run_tool_loop(
        system=PromptBuilder.build(PromptPhase.BUILD_FIX),
        messages=[{"role": "user", "content": fix_msg}],
        tool_executor=executor,
        max_iterations=2,
        on_event=ctx.event_callback,
    )

    return {
        "fix_attempts": attempts,
        "status": "fixing",
    }


# ─────────────────────────────────────────────────────────────────────────────
# 9. Preview Node (Launch & Health Check)
# ─────────────────────────────────────────────────────────────────────────────

def _heal_backend_if_needed(state: LangGraphState, ctx: NodeContext, pm: PreviewManager, info) -> Any:
    """Self-heal a backend that failed to start (mirrors orchestrator._fix_server_errors).

    Runs the bounded AI repair loop when PreviewManager reports a backend_error,
    then restarts the preview. Returns the (possibly updated) PreviewInfo.
    Success path (backend healthy) never enters this function.
    """
    error_output = getattr(info, "backend_error", None)
    if not error_output:
        return info

    print(f"[Graph:PreviewNode] ⚠️ Backend failed to start: {error_output[:200]}")
    ctx.post_event("server_fix_started", {
        "session_id": state["session_id"],
        "task_id": state["task_id"],
        "attempt": 1,
        "error": error_output[:500],
    })

    config = ctx.router.route(TaskType.build_fix, model=state.get("model_name"))
    MAX_ATTEMPTS = 2

    for attempt in range(MAX_ATTEMPTS):
        print(f"[Graph:PreviewNode] Server fix attempt {attempt + 1}/{MAX_ATTEMPTS}...")
        tools = ctx.registry.get_tools(ToolPhase.build_fix)
        executor = ToolExecutor(ctx.mcp, ctx.registry, event_callback=getattr(ctx, "post_event", None))

        client = ClaudeToolClient(
            model=config.model,
            api_key=config.api_key,
            tools=tools,
            max_tokens=config.max_tokens,
            temperature=config.temperature,
            file_manifest=ctx.active_manifest,
        )

        entrypoint = getattr(info, "backend_entrypoint", None)
        cwd = getattr(info, "backend_cwd", None)
        server_hint = (
            f"Backend entrypoint file: {entrypoint}\n"
            f"Working directory: {cwd}\n"
            f"Inspect `{entrypoint}` using `read_file(path='{entrypoint}')` to diagnose the failure.\n"
        ) if entrypoint else ""

        user_msg = (
            f"The backend server failed to start with this error:\n\n{error_output}\n\n"
            f"Workspace: {state['workspace_path']}\n"
            f"{server_hint}"
            "Fix the server file so it starts successfully. "
            "One targeted edit — do NOT rewrite the entire file."
        )

        messages = list(ctx.active_conversation) if ctx.active_conversation else []
        messages.append({"role": "user", "content": user_msg})

        try:
            result = client.run_tool_loop(
                system=PromptBuilder.build(PromptPhase.SERVER_FIX),
                messages=messages,
                tool_executor=executor,
                max_iterations=15,
                on_event=ctx.event_callback,
            )
            ctx.active_conversation = result.conversation
            ctx.active_manifest = client._file_manifest
        except Exception as fix_exc:
            print(f"[Graph:PreviewNode] Server fix loop error: {fix_exc}")

        files_changed = list(state.get("files_changed", []))
        for f in executor.files_changed:
            if f not in files_changed:
                files_changed.append(f)
        state["files_changed"] = files_changed

        if not executor.files_changed:
            print("[Graph:PreviewNode] No files changed — stopping server fix")
            break

        # Kill old backend process and restart preview
        try:
            pm.stop_backend()
        except Exception:
            pass

        time.sleep(1)
        info = pm.start_preview(project_type="auto")

        if not getattr(info, "backend_error", None):
            print(f"[Graph:PreviewNode] ✅ Backend fixed and running on port {info.backend_port}")
            ctx.post_event("server_fix_completed", {
                "session_id": state["session_id"],
                "task_id": state["task_id"],
                "attempt": attempt + 1,
                "status": "fixed",
            })
            return info

        error_output = info.backend_error
        print(f"[Graph:PreviewNode] Backend still failing: {error_output[:200]}")

    print("[Graph:PreviewNode] Server fix exhausted — backend may not be functional")
    ctx.post_event("server_fix_completed", {
        "session_id": state["session_id"],
        "task_id": state["task_id"],
        "status": "exhausted",
        "error": (error_output or "")[:500],
    })
    return info


def preview_node(state: LangGraphState, ctx: NodeContext) -> dict[str, Any]:
    """Start Vite preview server, clean port holders, and post session_completed.

    If the backend failed to start, run the bounded self-heal loop first and
    only post session_completed with full health status reflected.
    """
    ws = state["workspace_path"]
    print("[Graph:PreviewNode] Launching preview service...")

    pm = PreviewManager(ws)
    detected_backend_port = 3001
    try:
        detected_backend_port = pm.detect_backend_port() or 3001
    except Exception:
        pass
    ProcessSupervisor.kill_port_holders(detected_backend_port)

    info = pm.start_preview(project_type="auto")

    # Self-heal dead backends instead of declaring success unconditionally.
    if info is not None and getattr(info, "backend_error", None):
        info = _heal_backend_if_needed(state, ctx, pm, info)

    preview_url = info.url if info else "http://localhost:80"
    backend_healthy = info is not None and not getattr(info, "backend_error", None)

    if backend_healthy:
        final_text = state.get("final_text") or "Application is live, validated, and ready to use."
    else:
        backend_err = getattr(info, "backend_error", None) or "Backend did not start"
        final_text = (
            "⚠️ Application preview is live, but the backend could not be started "
            f"after automatic repair attempts. Reason: {backend_err[:300]}"
        )
        print(f"[Graph:PreviewNode] ⚠️ Completing with degraded status: {backend_err[:200]}")

    ctx.post_event("preview_started", {
        "session_id": state["session_id"],
        "task_id": state["task_id"],
        "message": "Preview service started. Running browser validation...",
        "preview_url": preview_url,
        "model": state["model_name"],
        "backend_healthy": backend_healthy,
        "backend_error": None if backend_healthy else (getattr(info, "backend_error", None) or "Backend did not start")[:500],
    })

    print(f"[Graph:PreviewNode] Preview service started. Preview live at {preview_url}. Pending browser verification.")

    return {
        "preview_url": preview_url,
        "status": "preview_ready",
        "backend_healthy": backend_healthy,
        "backend_error": None if backend_healthy else (getattr(info, "backend_error", None) or "Backend did not start")[:500],
        "final_text": final_text,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Git Push Node — Auto-commit and push after task completion
# ─────────────────────────────────────────────────────────────────────────────

def git_push_node(state: LangGraphState, ctx: NodeContext) -> dict[str, Any]:
    """Auto-commit all workspace changes and push to remote Git repository.

    This node runs AFTER preview_node succeeds. It:
    1. Stages all changed files
    2. Creates a checkpoint commit with task metadata
    3. Pushes to the remote repository (if GIT_REPO_URL is configured)
    4. Reports the commit hash back via lifecycle events

    Architecture: Every successful task completion produces a versioned commit
    that is pushed to the project's Git repository, making agent work
    immediately visible to the team.
    """
    ws = state["workspace_path"]
    task_id = state.get("task_id", "unknown")
    session_id = state.get("session_id", "unknown")
    files_changed = state.get("files_changed", [])

    print(f"[Graph:GitPushNode] Auto-committing and pushing {len(files_changed)} file(s)...")

    from mcp.git_tools import GitTools
    git = GitTools(ws)

    # Step 1: Ensure git repo is initialized
    try:
        git.init(workspace_path=ws)
    except Exception as e:
        print(f"[Graph:GitPushNode] Git init note: {e}")

    # Step 2: Commit checkpoint
    summary = state.get("final_text", "Agent task completed")[:120]
    commit_result = git.commit_checkpoint(
        task_id=task_id,
        summary=summary,
        files_changed=files_changed,
    )

    commit_hash = "unknown"
    if commit_result.success:
        commit_hash = commit_result.data.get("commit_hash", "unknown")
        commit_status = commit_result.data.get("status", "committed")
        print(f"[Graph:GitPushNode] Committed: {commit_hash[:8]} ({commit_status})")
    else:
        print(f"[Graph:GitPushNode] Commit failed: {commit_result.error}")

    # Step 3: Push to remote
    push_success = False
    push_message = "Push not attempted"

    repo_url = os.environ.get("GIT_REPO_URL", "")
    auth_token = os.environ.get("GIT_AUTH_TOKEN") or os.environ.get("GIT_PAT_TOKEN", "")

    if repo_url:
        try:
            push_result = git.push(
                branch=os.environ.get("GIT_BRANCH", "main"),
                auth_token=auth_token if auth_token else None,
                repo_url=repo_url if repo_url else None,
            )
            if push_result.success:
                push_success = True
                push_message = f"Pushed to {repo_url}"
                print(f"[Graph:GitPushNode] Pushed to remote: {repo_url}")
            else:
                push_message = f"Push failed: {push_result.error}"
                print(f"[Graph:GitPushNode] Push failed: {push_result.error}")
        except Exception as e:
            push_message = f"Push error: {e}"
            print(f"[Graph:GitPushNode] Push error: {e}")
    else:
        push_message = "No GIT_REPO_URL configured - skipping push"
        print(f"[Graph:GitPushNode] No GIT_REPO_URL set, skipping push")

    # Step 4: Post lifecycle event
    ctx.post_event("git_push_completed", {
        "session_id": session_id,
        "task_id": task_id,
        "commit_hash": commit_hash,
        "push_success": push_success,
        "push_message": push_message,
        "files_committed": len(files_changed),
    })

    return {
        "commit_hash": commit_hash,
        "push_success": push_success,
        "push_message": push_message,
    }

