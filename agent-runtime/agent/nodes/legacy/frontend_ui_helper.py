"""Legacy single-page React UI generators, contracts, and layout directives.

Contains UI design specs, file signature extraction, sequential 1-file-at-a-time
React Vite component generator, and Rollup stub reconciler.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from agent.model_router import TaskType
from agent.nodes.core.context import NodeContext
from agent.prompts.system_prompts import CODING_SYSTEM_PROMPT
from agent.state import LangGraphState
from agent.tools.tool_executor import ToolExecutor
from agent.tools.tool_registry import ToolPhase
from infrastructure.claude_tool_client import ClaudeToolClient
from infrastructure.model_profile import ModelProfile, get_profile
from infrastructure.token_counter import estimate_tokens, prompt_fits_safely, select_context_tier


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
    service_files: list[str] = []
    if all_services and len(raw_files) <= 5:
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

    readme_entry = "README.md"
    if readme_entry not in ordered_queue:
        ordered_queue.append(readme_entry)

    # Hard Cap: max 5 app files (README excluded)
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
            history_context = "No previous application files generated yet. This is the first file."
            tools_for_turn = write_tool_schema

        elif tier == 1:
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
            plan_dict_for_ui = state.get("plan_data") or {}
            ui_spec = build_ui_directive(plan_dict_for_ui, target_rel, file_type)
            spec_inst = (
                "COMPONENT GENERATION:\n"
                + (ui_spec + "\n\n" if ui_spec else "")
                + budget_line
            )

        # ── 5. Build prompt ───────────────────────────────────────────────────
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

    resolved_ws = Path(ws).resolve()
    created_stubs: list[str] = []
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

                if not spec.startswith(".") or spec.endswith((".css", ".scss", ".png", ".jpg", ".jpeg", ".svg", ".json", ".gif", ".webp")):
                    continue

                resolved_base = (file_dir / spec).resolve()
                exists = False
                for ext in ("", ".jsx", ".tsx", ".js", ".ts", "/index.jsx", "/index.tsx", "/index.js"):
                    candidate = Path(f"{resolved_base}{ext}")
                    if candidate.exists() and candidate.is_file():
                        exists = True
                        break

                if not exists:
                    target_file = resolved_base.with_suffix(".jsx")
                    rel_created = os.path.relpath(str(target_file), str(resolved_ws)).replace("\\", "/")

                    comp_name = default_sym or target_file.stem or "ComponentView"
                    comp_name = re.sub(r"\W+", "", comp_name)
                    if not comp_name or not comp_name[0].isupper():
                        comp_name = comp_name.capitalize() if comp_name else "StubView"

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
