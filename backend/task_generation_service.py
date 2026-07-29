"""
Task Generation Service - Creates tasks locally before sending to NXDUNE
Uses Agent Action Plan to generate structured tasks with multiple sprints and milestones
"""
import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Set
from sqlalchemy.orm import Session
from models import Task, Document, GovernanceResponse, User
from sqlalchemy import func
import llm_gateway

logger = logging.getLogger(__name__)


INTELLIGENT_TASK_GENERATION_PROMPT = """You are a senior AI systems architect and principal UX engineer specializing in multi-agent task orchestration and prototype-first product development.

I will give you an Agent Action Plan markdown document. Your job is to convert it into a structured task list that multiple AI coding agents can execute IN PARALLEL without conflicts — and where Sprint 1 produces a fully interactive, visually stunning, internally-linked frontend prototype that gives stakeholders a true bird's-eye view of the finished product.

---

## ═══════════════════════════════════════════════════════
## PART 1 — SPRINT 1 FRONTEND PROTOTYPE PHILOSOPHY
## ═══════════════════════════════════════════════════════

Sprint 1 is NOT a collection of isolated screens. It is a **living, breathing application prototype** — a complete interactive story where every screen connects to every other screen, every button does something, and the end-user can walk through real user journeys end-to-end using realistic mock data.

Think of Sprint 1 as building the **demo-ready product trailer**. When a stakeholder opens the app for the first time, they must be able to:
  1. Navigate naturally between all major screens without hitting dead ends
  2. Click buttons, fill forms, open modals, switch tabs — all with working UI state
  3. See realistic, domain-appropriate mock data (not "User 1" or "Lorem ipsum")
  4. Experience a visually polished, cohesive design that feels production-ready

### THE GOLDEN RULE — ZERO DEAD UI
**Every single interactive element in the prototype MUST do something.** No exceptions.
- Every button → navigates to a screen, opens a modal/drawer, triggers a state change, or shows a toast notification
- Every nav link → routes to its target page using React Router `<Link>` or `useNavigate()`
- Every table row → is clickable and navigates to a detail view
- Every form → has a working submit handler that shows a success/error state
- Every card → responds to hover/click with visual feedback
- Every dropdown/select → updates visible state when an option is chosen
- Every tab → switches the visible panel content
- Every search input → filters the displayed list in real-time (client-side, no API)

If an agent builds a button that does nothing, the task has FAILED. There are no placeholder elements in Sprint 1.

### NAVIGATION ARCHITECTURE REQUIREMENT
TASK-00 MUST establish the navigation foundation that ALL frontend tasks depend on:
  1. **React Router v6 setup** in the main App entry file with ALL application routes pre-registered
  2. **Shared Layout component** (e.g. AppLayout.tsx) containing:
     - Persistent sidebar with navigation links to every major section
     - Top navigation bar with user avatar, notifications bell, and breadcrumbs
     - Main content area where page components are rendered via `<Outlet />`
  3. **Design token file** (e.g. tokens.css or tokens.ts) defining:
     - Primary, secondary, accent, surface, and text color variables
     - Typography scale (display, heading, body, caption font sizes)
     - Spacing scale, border radius, shadow levels
  4. **Global mock data store** (e.g. mockData.ts) with 5-10 realistic records per entity type, using domain-specific names, realistic values, and varied statuses
  5. **Shared UI components** (e.g. a ui/ directory) — Button, Badge, Card, Modal, Table, Sidebar, etc. — used consistently by all page components

Every subsequent Sprint 1 frontend task IMPORTS from these shared foundations. No task invents its own navigation, colors, or mock data structure.

### ⚠️ CRITICAL — CANONICAL PATH RULE (APPLIES TO ALL TASKS)
The REPOSITORY STRUCTURE provided in the context is the SINGLE SOURCE OF TRUTH for all file paths.
Every file path you write in FILE OWNERSHIP blocks, descriptions, and checklists MUST use the FULL path exactly as it appears in the canonical repository structure tree.

**EXAMPLES of the rule in action:**
- If the canonical tree shows `frontend/src/pages/`, then all frontend page paths MUST start with `frontend/src/pages/...` — NEVER bare `src/pages/...`
- If the canonical tree shows `backend/app/models/`, then all model paths MUST start with `backend/app/models/...` — NEVER bare `app/models/...`
- If there is NO `frontend/` wrapper in the tree (flat project), then `src/pages/...` is correct.

The rule is simple: **look at the tree, use the exact prefix shown in the tree.** If the tree has a `frontend/` parent directory containing `src/`, then every frontend path MUST include `frontend/` as the prefix. No exceptions.

### DESIGN QUALITY STANDARD
Sprint 1 prototype screens must be visually outstanding — not generic, not bare, not "bootstrap default."
  - **Aesthetic direction**: Choose a clear, committed visual identity appropriate to the project domain (e.g., enterprise SaaS → clean, structured, data-dense; consumer app → warm, playful, card-based; fintech → precise, trustworthy, dark-mode-ready)
  - **Typography**: Use a distinctive font pairing — a strong display/heading font plus a clean body font. Import from Google Fonts or use system fonts deliberately. Never default to Inter/Arial/system-ui without intention.
  - **Color system**: Define a cohesive palette — one primary action color, one accent, semantic colors (success green, warning amber, error red), and surface/background layers. Apply consistently.
  - **Spacing and layout**: Use consistent spacing scale. Pages should feel structured and breathable, not cramped or randomly spaced.
  - **Micro-interactions**: Add CSS transitions on hover states, smooth route transitions, loading skeleton states, and animated feedback on form submissions.
  - **Visual richness**: Charts/graphs must use realistic data shapes. Tables must have multi-column data. Dashboards must have KPI cards with real numbers, trend indicators, and sparklines.

### STORY-FIRST TASK DESCRIPTION FORMAT
Every Sprint 1 frontend task description MUST follow this narrative format — written like a product specification screenplay, not a file manifest:

```
[SCREEN STORY]
Describe the user journey on this screen from arrival to completion.
- "The user arrives at the [Screen Name] after clicking [Source] in the sidebar/navbar."
- "They are greeted by [what they see first — hero, table, KPIs, etc.]."
- "When they click [Primary Action Button], [exactly what happens — modal opens / navigates to /route / form appears]."
- "The [Table/List] shows [N] records with columns [X, Y, Z]. Clicking any row navigates to [Detail Route]."
- "The [Filter/Search bar] filters results in real-time as the user types."
- "A [Status Badge] on each row is color-coded: [Green=Active, Red=Inactive, Amber=Pending]."
- "The [Create/Add button] opens a [Drawer/Modal] with a multi-field form. On submit, a success toast appears and the new item is optimistically added to the list."
- "The breadcrumb trail shows: [Home > Section > This Page]."

[SCREEN CONNECTIVITY]
List every navigation target this screen links to:
- [Button/Link Name] → navigates to: /route-path ([Screen Name])
- [Row click] → navigates to: /route-path/:id ([Detail Screen Name])
- [Back button] → navigates to: /route-path ([Parent Screen Name])
- [Tab: "Settings"] → shows: inline settings panel (no navigation)

[MOCK DATA SPECIFICATION]
Define the realistic mock data this screen uses:
- Entity: [EntityName] — 8 records with fields: [field1: "realistic value", field2: ...]
- Use domain-appropriate names (e.g., for a hospital app: "Dr. Sarah Chen", "Ward 4B", "Patient ID: PT-2847")
- Vary statuses across records to show all badge states

[FILE OWNERSHIP]
This agent owns: [exact file paths]
This agent must create:
  - [file path] ([what it does])
This agent must NOT modify: [other folders/files]
```

This format is MANDATORY for all Sprint 1 frontend tasks. Backend tasks may use the abbreviated ownership-only format.

---

## ═══════════════════════════════════════════════════════
## PART 2 — CORE ARCHITECTURE PRINCIPLES
## ═══════════════════════════════════════════════════════

**1. FILE-BOUNDED OWNERSHIP — Prevent Conflicts**
- Parallel execution requires clean separation. Each task must have strict, exclusive file boundaries.
- If multiple agents need to work on the same layers or features, split them into sequential sprints or separate, modular files rather than compressing everything into single, monolithic tasks.
- Shared files (like route registers, AppLayout, global mock stores, and design tokens) must be created in TASK-00 or an early Sprint 1 foundation task so that all subsequent parallel tasks only IMPORT from them, never modify them concurrently.

**2. Complexity-Driven Granular Splitting (NO Arbitrary Task Limits)**
- There is NO arbitrary limit on the number of tasks (do NOT cap at 15).
- For complex systems, generate 20–40 granular tasks. Slicing work into precise, modular tasks ensures agents have crystal-clear context and avoid context window overload.
- Every major screen deserves its own task. A "Dashboard" and a "Reports" page are two separate tasks, not one.

**3. Complexity-Aware Splitting**
- Simple monolithic apps → 4–8 granular tasks.
- Medium modular systems → 8–15 granular tasks.
- Large multi-layered platforms or microservices → 15–40 granular, independent tasks.
- Key question: "Can this task be completed end-to-end by one independent agent without file lock collisions?"
  - YES → keep it separate. NO → sequence via `linked_tasks` or group logically.

**4. Specialization-Based Work Distribution**
- Align tasks to domains: Backend Services, Database Schemas, Frontend Pages, Dashboard Widgets, Auth Flows, PDF/File Processing, DevOps/Security.
- State exactly which folders are owned and which are forbidden.

**5. Avoid Monolithic Tasks**
- Never create one task covering an entire layer (DB → API → UI).
- Split: one task for DB model + API endpoint, a separate task for the frontend screen consuming it.

**6. Parallelism Maximization**
- Tasks in the same Sprint run concurrently. Zero overlapping file ownership between parallel tasks.

---

## ═══════════════════════════════════════════════════════
## PART 3 — JSON TASK FORMAT
## ═══════════════════════════════════════════════════════

Use this exact JSON format for every task:

[
  {
    "task_id": "TASK-00",
    "taskName": "Short, specific task title",
    "description": "[STORY-FIRST description for Sprint 1 frontend tasks as per the STORY-FIRST FORMAT above. For backend/infra tasks: concise scope + file ownership statement.]",
    "task_type": "FEATURE | BUG | TASK",
    "priority": "high | medium | low",
    "task_wallet": <2 | 3 | 5 | 8 based on scope>,
    "deadline": "YYYY-MM-DD",
    "startdate": "YYYY-MM-DD",
    "sprint": "Sprint name from AVAILABLE SPRINTS list",
    "milestone": "Milestone name from AVAILABLE MILESTONES list",
    "assignedTo": [],
    "linked_tasks": ["TASK-ID"],
    "reported_by": "system",
    "checklist": [
      { "text": "Specific, screen-aware milestone step", "completed": false },
      { "text": "Specific, screen-aware milestone step", "completed": false },
      { "text": "Specific, screen-aware milestone step", "completed": false },
      { "text": "Specific, screen-aware milestone step", "completed": false },
      { "text": "Verify all interactive elements navigate correctly and zero dead UI remains", "completed": false }
    ]
  }
]

---

## ═══════════════════════════════════════════════════════
## PART 4 — SPRINT LIFECYCLE (MANDATORY FRONTEND-FIRST)
## ═══════════════════════════════════════════════════════

**Sprint = Wave of parallel execution.**
All tasks with the same sprint number dispatch to different agents simultaneously.
Sprint N+1 only starts after ALL Sprint N tasks complete.

### Sprint 1 → Foundation, Navigation Shell & Fully-Linked Frontend Prototype

TASK-00 (mandatory first task) creates the entire project scaffold including:
  - React Router v6 with ALL routes pre-registered in App.tsx
  - AppLayout.tsx with persistent sidebar navigation and top navbar
  - Design token file (colors, typography, spacing)
  - Global mock data store (src/mocks/mockData.ts) with 8–10 realistic records per entity
  - Shared UI component library (Button, Badge, Card, Modal, Drawer, Table, etc.)
  - Basic backend entry point skeleton ONLY (e.g., main.py with no DB or business logic)

All other Sprint 1 tasks build individual screens/feature areas that:
  - IMPORT the AppLayout wrapper — every screen renders inside the shared navigation shell
  - IMPORT mock data from the global mock store — no agent invents its own data
  - IMPORT shared UI components — no agent reimplements buttons or cards
  - Wire every interactive element to a real React Router navigation target or local state handler
  - Are visually complete, styled with the design token system, and match the aesthetic direction

CRITICAL Sprint 1 constraints:
  - NO backend API calls. All data comes from the mock store.
  - NO database schemas, models, or third-party API configs in Sprint 1.
  - YES to full navigation: every screen reachable from the sidebar and from contextual buttons.
  - YES to realistic interactions: modals, drawers, toasts, form validation, tab switching, search/filter.
  - The result must be a deployable, fully interactive frontend prototype that a non-technical stakeholder can navigate and understand without any explanation.

### Sprint 2 → Backend Services, Database Setup & Core Configurations
  - All SQLAlchemy database schemas, models foundation, JWT authentication, and core configurations.
  - All third-party API dependencies, external service integrations (AWS, Azure, payment processors, email).
  - All actual backend API routes, endpoints, and controllers.

### Sprint 3 → Frontend-Backend Integration & Database Connectivity Check
  - Connect Sprint 1 frontend screens to Sprint 2 real backend APIs.
  - Replace mock data imports with React Query fetch/mutation hooks.
  - Run database connectivity checks, verify JWT auth end-to-end, validate system data flows.

### Sprint 4 → Testing, Polish, and Production Deployment
  - Comprehensive frontend unit/integration test suites (Vitest/component tests) and backend suites (Pytest).
  - Full End-to-End integration and system testing.
  - Production deployment configs, Docker setups, final documentation.

---

## ═══════════════════════════════════════════════════════
## PART 5 — TASK WALLET (EFFORT POINTS) GUIDE
## ═══════════════════════════════════════════════════════

- 2 → Setup, boilerplate, simple config files, minor utilities
- 3 → Single backend module or a simple, read-only frontend screen
- 5 → Complex interactive screen (tables, modals, forms, real-time filter, charts), multi-step wizard, or service integration
- 8 → Critical architectural foundation (TASK-00, navigation shell, design system), massive state-heavy workflows, or enterprise-grade data grids with drill-down

Sprint 1 frontend screens with deep interactivity (modals, drawers, search, forms, drill-through) should score 5. TASK-00 (which sets up routing, layout, design tokens, and mock data) should score 8.

---

## ═══════════════════════════════════════════════════════
## PART 6 — FILE OWNERSHIP RULES
## ═══════════════════════════════════════════════════════

Every task description MUST state:
  - "This agent owns: [exact file paths derived from the CANONICAL REPOSITORY STRUCTURE]"
  - "This agent must create: [list of specific files with FULL canonical paths and their purpose]"
  - "This agent must NOT modify: [other folders/files]"
  - For Sprint 1 tasks: "This agent must IMPORT from: [canonical path to layout], [canonical path to mockData], [canonical path to ui components]"

⚠️ REMINDER: All file paths in FILE OWNERSHIP blocks MUST match the CANONICAL REPOSITORY STRUCTURE exactly.
If the repo tree shows files under `frontend/src/`, use `frontend/src/...` — NEVER bare `src/...`.
If the repo tree shows files under `backend/app/`, use `backend/app/...` — NEVER bare `app/...`.
Deriving paths from the tree prevents conflicts between task descriptions and the actual project layout.

**Example of GOOD Sprint 1 frontend task description (abbreviated):**
(Note: paths below use `{fe}` as placeholder for whatever the canonical frontend root is — e.g. `frontend/` or empty if flat)
```
[SCREEN STORY]
The user arrives at the Projects Overview screen after clicking "Projects" in the sidebar.
They see a page header "All Projects" with a "+ New Project" button in the top right.
The main content is a data table with columns: Project Name, Status (color-coded badge), Owner, Due Date, Budget Utilization (progress bar), and Actions.
Clicking any row navigates to /projects/:id (Project Detail screen).
Clicking "+ New Project" opens a Drawer from the right with a 3-field form. On submit, a success toast appears.

[SCREEN CONNECTIVITY]
- Sidebar "Projects" → current page (active state)
- Table row click → /projects/:id (Project Detail)
- "+ New Project" button → opens ProjectCreateDrawer (right-side drawer, no navigation)
- Breadcrumb "Home" → /dashboard

[MOCK DATA SPECIFICATION]
Entity: Project — 8 records
Fields: id, name, status (Active/On Hold/Completed/At Risk), owner, dueDate, budgetUsed, budgetTotal

[FILE OWNERSHIP]
This agent owns: {fe}src/pages/projects/ProjectsPage.tsx, {fe}src/pages/projects/ProjectDetailPage.tsx
This agent must create:
  - {fe}src/pages/projects/ProjectsPage.tsx (main projects list screen)
  - {fe}src/pages/projects/ProjectDetailPage.tsx (individual project drill-down)
This agent must IMPORT from: {fe}src/components/layout/AppLayout.tsx, {fe}src/mocks/mockData.ts, {fe}src/components/ui/
This agent must NOT modify: {fe}src/App.tsx, {fe}src/mocks/mockData.ts, {fe}src/components/layout/, backend/
```
IMPORTANT: In your actual output, replace `{fe}` with the real canonical frontend prefix from the REPOSITORY STRUCTURE (e.g. `frontend/` if the tree shows `frontend/src/`, or nothing if `src/` is at root).

---

## ═══════════════════════════════════════════════════════
## PART 7 — CHECKLIST ITEM RULES
## ═══════════════════════════════════════════════════════

Checklist items must be **screen-specific and interaction-aware** — not generic milestone labels.

For Sprint 1 frontend tasks, each checklist item must reference the actual screen, a specific UI element, or a specific user interaction. BAD: "Implement service layer." GOOD: "Build ProjectTable component with sortable columns, status badge coloring, and row-click navigation to /projects/:id."

- Item 1: Build the primary screen structure and layout (header, content sections, sidebar slot)
- Item 2: Implement the main data display (table/list/cards) with realistic mock data and all columns
- Item 3: Wire all navigation targets — every button, link, and row click routes to the correct screen
- Item 4: Build all secondary interactions (modals, drawers, forms, search/filter, tabs, toasts)
- Item 5: Apply the design token system — verify typography, color, spacing consistency with other Sprint 1 screens; confirm zero dead UI elements remain

For backend/infra tasks:
- Item 1–4: High-level functional milestones covering meaningful code blocks
- Item 5: Test/verification step with exact command or assertion

---

## ═══════════════════════════════════════════════════════
## PART 8 — TASK-00: THE IMMOVABLE GATEWAY
## ═══════════════════════════════════════════════════════

TASK-00 is not a regular task. It is the **project gateway** — a structural law, not a suggestion.

### NON-NEGOTIABLE TASK-00 RULES:

**Rule 1 — TASK-00 is ALWAYS the first object in the JSON array.**
No exceptions. Index 0 in the output array is always TASK-00. If you generate it anywhere else, the output is invalid.

**Rule 2 — TASK-00 has a fixed task_id: "TASK-00".**
The task_id field must be exactly the string "TASK-00". It cannot be "TASK-01", "BOOTSTRAP", "SETUP", or anything else.

**Rule 3 — TASK-00 is the ONLY task with no linked_tasks dependencies.**
Every other task in the entire plan — Sprint 1, 2, 3, and 4 — must list "TASK-00" in its linked_tasks array. TASK-00 itself has an empty linked_tasks: [].

**Rule 4 — No Sprint 1 screen task may begin before TASK-00 completes.**
This is enforced by the linked_tasks dependency. All Sprint 1 tasks depend on TASK-00 because they import from the files it creates (AppLayout, mockData, design tokens, UI components, App.tsx routes). An agent starting a screen task without TASK-00's output would fail immediately.

**Rule 5 — TASK-00 owns the entire shared foundation. No other task may touch these files.**
  - The main App entry file (e.g. App.tsx — route registry)
  - The shared Layout component (e.g. AppLayout.tsx — persistent navigation shell)
  - The design token file (e.g. tokens.css or tokens.ts)
  - The global mock data store (e.g. mockData.ts)
  - The shared UI component directory (e.g. components/ui/*)
  - The backend entry point skeleton (e.g. main.py)
No other task in any sprint may modify these files. They are read-only after TASK-00 completes.
⚠️ Use FULL CANONICAL PATHS from the REPOSITORY STRUCTURE when listing these in the actual task output. Never use bare relative paths like `src/App.tsx` if the canonical tree shows `frontend/src/`.

### TASK-00 MANDATORY CONTENT (use this structure, with CANONICAL PATHS from the repository tree):

```json
{
  "task_id": "TASK-00",
  "taskName": "Project Bootstrap, Navigation Shell & Shared Frontend Foundation",
  "description": "GATEWAY TASK — All other tasks depend on this. Must complete before any other agent starts.\n\nThis task creates the entire shared foundation that every Sprint 1 frontend agent will import from. It does NOT build any feature screens — it builds the INFRASTRUCTURE that makes all screens possible.\n\n[WHAT THIS TASK BUILDS]\n1. Repository scaffold: all directories from the CANONICAL REPOSITORY STRUCTURE, plus package.json, tsconfig, vite.config, tailwind.config, .env.example.\n2. React Router v6 setup in the main App entry file: ALL application routes pre-registered with placeholder lazy-loaded components, wrapped in the AppLayout shell.\n3. AppLayout.tsx: persistent left sidebar with navigation links to every major section, top navbar with app logo, user avatar dropdown, notifications bell, breadcrumb trail, and <Outlet /> for page content. Sidebar must be collapsible.\n4. Design token system: CSS custom properties for colors, typography, spacing, border-radius, box-shadow. All Sprint 1 screens MUST use these tokens, never hardcoded values.\n5. Global mock data store (e.g. mockData.ts): exports typed arrays of 8-10 realistic mock records for EVERY entity type. Use domain-appropriate names, IDs, dates, and statuses.\n6. Shared UI component kit: Button (variants: primary, secondary, ghost, danger), Badge, Card, Modal, Drawer, DataTable, SearchInput, Toast system, LoadingSkeleton, EmptyState, PageHeader.\n7. Backend entry point skeleton ONLY (e.g. main.py) with CORS middleware and a /health endpoint. NO database, NO models, NO business logic.\n\n[WHAT THIS TASK MUST NOT BUILD]\n- No feature screens (those are built by subsequent Sprint 1 tasks)\n- No backend database schemas, models, or API routes (Sprint 2)\n- No third-party API integrations (Sprint 2)\n\n⚠️ FILE OWNERSHIP: List ALL owned files using FULL CANONICAL PATHS from the REPOSITORY STRUCTURE. If the tree shows frontend/src/, use frontend/src/... not bare src/...\nAll subsequent tasks MUST wait for this task to complete before starting.",
  "task_type": "TASK",
  "priority": "high",
  "task_wallet": 8,
  "sprint": "<Sprint 1 name from AVAILABLE SPRINTS>",
  "milestone": "Navigation Shell & Design System",
  "assignedTo": [],
  "linked_tasks": [],
  "reported_by": "system",
  "checklist": [
    { "text": "Scaffold full repository structure: all directories from canonical tree, package.json, tsconfig, vite.config, tailwind.config, .env.example, README", "completed": false },
    { "text": "Build AppLayout.tsx with collapsible sidebar (all nav links), top navbar (logo, user avatar, notifications, breadcrumbs), and <Outlet /> content slot. Register all routes in the main App entry file with React Router v6.", "completed": false },
    { "text": "Create design token file with complete color palette (primary, accent, semantic), typography scale, spacing scale, border radius, and shadow levels.", "completed": false },
    { "text": "Populate global mock data store with 8-10 realistic typed records for every entity type in the application.", "completed": false },
    { "text": "Build shared UI component kit: Button (all variants), Badge, Card, Modal, Drawer, DataTable, SearchInput, Toast system, LoadingSkeleton, EmptyState, PageHeader.", "completed": false }
  ]
}
```

### THE SPRINT 1 DEPENDENCY CHAIN (enforced by linked_tasks):

```
TASK-00 (no deps)
   ├── TASK-01: Auth / Login Screen        → linked_tasks: ["TASK-00"]
   ├── TASK-02: Dashboard Screen           → linked_tasks: ["TASK-00"]
   ├── TASK-03: [Entity] List Screen       → linked_tasks: ["TASK-00"]
   ├── TASK-04: [Entity] Detail Screen     → linked_tasks: ["TASK-00"]
   ├── TASK-05: Settings / Profile Screen  → linked_tasks: ["TASK-00"]
   └── ... (all Sprint 1 tasks)            → linked_tasks: ["TASK-00"]

Sprint 2 tasks → linked_tasks: ["TASK-00"]
Sprint 3 tasks → linked_tasks: ["TASK-00", "TASK-XX (Sprint 1)", "TASK-YY (Sprint 2)"]
Sprint 4 tasks → linked_tasks: ["TASK-00", relevant Sprint 2/3 tasks]
```

---

## ═══════════════════════════════════════════════════════
## PART 9 — REMAINING CRITICAL RULES
## ═══════════════════════════════════════════════════════

1. **Sprint Assignment:**
   - Use the AVAILABLE SPRINTS list provided
   - Tasks in the same sprint must have zero file ownership conflicts

2. **Milestone Assignment:**
   - Group related tasks under meaningful functional milestones
   - Sprint 1 milestones: "Navigation Shell & Design System" (TASK-00 only), "Authentication Screens", "Dashboard & Analytics", "[Domain] Management Screens", "Settings & Admin"
   - Sprint 2 milestones: "Database Foundation", "Authentication Backend", "[Domain] API Services"
   - Sprint 3 milestones: "Full-Stack Integration", "Auth Integration"
   - Sprint 4 milestones: "QA & Testing", "Production Deployment"

3. **File Path Accuracy:**
   - ALL file paths MUST be derived from the CANONICAL REPOSITORY STRUCTURE provided in the context.
   - NEVER use bare `src/...` if the canonical tree shows the frontend source under a subdirectory like `frontend/src/...`.
   - NEVER use bare `app/...` if the canonical tree shows the backend source under `backend/app/...`.
   - The canonical tree is the single source of truth. Every path you output must be traceable to a node in that tree.

4. **Output Format:**
   - Return ONLY a valid JSON array
   - No markdown code blocks, no explanations, no extra text
   - First element of the array MUST be TASK-00

5. **Dynamic Task Scaling:**
   - NO cap at 15 tasks. Large apps need 25–40 granular tasks.
   - Every major screen = its own Sprint 1 task. Every major backend domain = its own Sprint 2 task.

6. **PROTOTYPE COMPLETENESS CHECK (Sprint 1 only):**
   Before finalizing, mentally walk every user journey:
   - Can a user log in and reach the dashboard?
   - Can a user navigate to every major section from the sidebar?
   - Can a user complete a full entity CRUD flow (create → list → detail → edit)?
   - Can a user complete any domain-specific multi-step flow?
   If ANY journey has a gap — a missing screen, a dead button, an unreachable route — add tasks until all journeys are complete.

---

"""


def _deduplicate_tasks(tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Remove duplicate tasks from the list based on title and description keywords.
    Preserves the first occurrence and removes subsequent near-duplicates.
    """
    if not tasks:
        return tasks

    seen_titles: Set[str] = set()
    seen_task_ids: Set[str] = set()
    deduped: List[Dict[str, Any]] = []

    for task in tasks:
        task_id = str(task.get("task_id", "")).strip()
        title = str(task.get("taskName", "") or task.get("title", "")).strip().lower()
        # Normalize: remove punctuation, collapse whitespace
        import re
        normalized = re.sub(r"[^a-z0-9\\s]", "", title)
        normalized = re.sub(r"\\s+", " ", normalized).strip()

        # Skip if we've already seen this task_id
        if task_id and task_id in seen_task_ids:
            logger.info(f"[DEDUP] Skipping duplicate task_id: {task_id}")
            continue

        # Skip if we've already seen a very similar title
        if normalized and normalized in seen_titles:
            logger.info(f"[DEDUP] Skipping duplicate title: {title} (task_id: {task_id})")
            continue

        if task_id:
            seen_task_ids.add(task_id)
        if normalized:
            seen_titles.add(normalized)
        deduped.append(task)

    if len(deduped) < len(tasks):
        logger.info(f"[DEDUP] Removed {len(tasks) - len(deduped)} duplicate tasks, {len(deduped)} remaining")

    return deduped


def _generate_sprints_and_milestones(
    project_start: datetime,
    project_deadline: datetime,
    num_phases: int = 4,
    project_type: str = "greenfield"
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Generate multiple sprints and milestones based on project timeline and type"""
    
    sprints = []
    milestones = []
    
    total_days = (project_deadline - project_start).days
    sprint_duration = max(total_days // num_phases, 7)  # At least 7 days per sprint
    
    is_bf = str(project_type).lower().strip() == "brownfield"
    if is_bf:
        phase_names = [
            ("Repo Analysis & Change Mapping", "Clone repository, analyze existing codebase structure, and plan target modifications"),
            ("Feature Enhancement & Implementation", "Implement code updates, add new service modules, and fix functional bugs"),
            ("Regression Testing & Validation", "Validate code changes against existing test suites, perform manual regression tests, and prepare PR"),
            ("Release & Deployment", "Deploy to staging, execute final checks, and merge to main production branch")
        ]
        
        milestone_names = [
            ("Codebase Analysis Completed", "Repository cloned, file structure parsed, and all change tasks mapped to source files"),
            ("Enhancements Implemented", "All change requests code completed and verified in local containers"),
            ("Validation & Tests Completed", "No regressions detected, unit tests updated, and Pull Request created for merge"),
            ("Enhancements Released", "New changes safely merged and deployed to staging/production")
        ]
    else:
        phase_names = [
            ("Frontend Proto & Bootstrap", "Project bootstrap, setup, and all frontend UI screens/prototypes with dummy data"),
            ("Backend Services & DB Config", "Database schemas, models, JWT auth, and third-party API configurations/external dependencies"),
            ("Frontend-Backend Integration", "Connect frontend screens to backend APIs, replace dummy data, and run DB connectivity checks"),
            ("Testing & Polish", "Comprehensive unit, integration, and E2E testing, and production deployment configuration")
        ]
        
        milestone_names = [
            ("Frontend Screens & Bootstrap Complete", "Repository bootstrapped and all frontend screens fully operational with dummy data"),
            ("Backend Services Operational", "AWS config, database schemas, and all backend API controllers/endpoints fully developed"),
            ("Integration & DB Sync Complete", "Frontend integrated with real backend APIs and database connectivity verified"),
            ("Production & Testing Ready", "Frontend/backend test suites complete and production deployment validated")
        ]
    
    for i in range(num_phases):
        sprint_start = project_start + timedelta(days=i * sprint_duration)
        sprint_end = min(
            project_start + timedelta(days=(i + 1) * sprint_duration - 1),
            project_deadline
        )
        
        phase_name, phase_desc = phase_names[i] if i < len(phase_names) else (f"Phase {i+1}", f"Sprint {i+1}")
        milestone_name, milestone_desc = milestone_names[i] if i < len(milestone_names) else (f"Milestone {i+1}", f"Milestone {i+1}")
        
        sprint = {
            "name": f"Sprint {i+1} - {phase_name}",
            "summary": phase_desc,
            "start_date": sprint_start.strftime('%Y-%m-%d'),
            "deadline": sprint_end.strftime('%Y-%m-%d'),
            "phase": i + 1
        }
        
        milestone = {
            "name": milestone_name,
            "summary": milestone_desc,
            "start_date": sprint_start.strftime('%Y-%m-%d'),
            "deadline": sprint_end.strftime('%Y-%m-%d'),
            "sprint": sprint["name"],
            "phase": i + 1
        }
        
        sprints.append(sprint)
        milestones.append(milestone)
    
    return sprints, milestones

async def _chunk_and_summarize_brd(
    raw_text: str,
    api_url: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    status_callback: Optional[Any] = None,
) -> str:
    """Chunk large BRD documents into logical blocks (~8000 chars) and summarize key features."""
    if not raw_text or len(raw_text) <= 15000:
        return raw_text

    logger.info(f"Large BRD document detected ({len(raw_text)} chars). Executing chunked BRD summarization...")
    chunk_size = 8000
    chunks = [raw_text[i:i + chunk_size] for i in range(0, len(raw_text), chunk_size)]
    summaries = []

    for idx, chunk in enumerate(chunks):
        logger.info(f"Summarizing BRD chunk {idx + 1} of {len(chunks)}...")
        if status_callback:
            try:
                status_callback("chunk", idx + 1, len(chunks))
            except Exception:
                pass

        messages = [
            {
                "role": "system",
                "content": "You are a Senior Business Analyst. Summarize key functional requirements, core modules, data flows, and technical requirements from this document chunk into concise bullet points."
            },
            {
                "role": "user",
                "content": f"Document Chunk {idx + 1}/{len(chunks)}:\n\n{chunk}"
            }
        ]
        try:
            summary = await llm_gateway.call_llm_and_extract(
                messages=messages, api_url=api_url, api_key=api_key, model=model, timeout=120.0, retries=3
            )
            summaries.append(f"--- BRD SECTION {idx + 1} SUMMARY ---\n{summary}")
        except Exception as e:
            logger.warning(f"Failed to summarize BRD chunk {idx + 1}: {e}")

    consolidated_map = "\n\n".join(summaries)
    logger.info(f"Chunked BRD summarization complete: consolidated {len(chunks)} chunks into {len(consolidated_map)} chars")
    return consolidated_map


async def _ai_plan_sprints(
    brd_context: str,
    project_type: str,
    process_mode: str,
    api_url: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """Ask AI to dynamically analyze BRD scope and decide optimal sprint count (2-6) and names."""
    logger.info("Executing AI Dynamic Sprint Planning...")
    prompt = f"""# ROLE
You are an Agile Lead Architect.

# TASK
Analyze the provided BRD requirements and project context. Dynamically determine the OPTIMAL NUMBER OF SPRINTS (between 2 and 6) and milestone targets required to deliver this project cleanly based on its scope, complexity, and project type.

PROJECT TYPE: {project_type}
PROCESS MODE: {process_mode}

BRD CONTEXT:
====================
{brd_context[:25000]}

# OUTPUT FORMAT (JSON ONLY)
Return a valid JSON object:
```json
{{
  "total_sprints": 3,
  "rationale": "Explanation of why this sprint count was chosen...",
  "sprints": [
    {{
      "sprint_number": 1,
      "name": "Sprint 1: Frontend Prototype & Core UI",
      "summary": "Build UI screens, navigation shell, and mock store.",
      "milestone": "Frontend Proto Complete",
      "focus": "frontend"
    }},
    {{
      "sprint_number": 2,
      "name": "Sprint 2: Backend Services & Database",
      "summary": "Develop database schemas, controllers, and APIs.",
      "milestone": "Backend Services Operational",
      "focus": "backend"
    }},
    {{
      "sprint_number": 3,
      "name": "Sprint 3: E2E Integration & Staging Cutover",
      "summary": "Connect UI to backend APIs, run tests, and prepare deployment.",
      "milestone": "Production Ready",
      "focus": "integration"
    }}
  ]
}}
```"""

    messages = [
        {"role": "system", "content": "You are a master Agile Lead Architect. Output valid JSON only."},
        {"role": "user", "content": prompt}
    ]

    try:
        raw_res = await llm_gateway.call_llm_and_extract(
            messages=messages, api_url=api_url, api_key=api_key, model=model, timeout=120.0, retries=3
        )
        data = _extract_json_from_response(raw_res)
        if isinstance(data, dict) and isinstance(data.get("sprints"), list) and len(data["sprints"]) > 0:
            logger.info(f"AI Dynamic Sprint Planning succeeded: planned {len(data['sprints'])} sprints.")
            return data
    except Exception as e:
        logger.warning(f"AI Dynamic Sprint Planning failed: {e}. Falling back to default 4-phase plan.")

    # Fallback to default 4 sprints if LLM planning fails
    return {
        "total_sprints": 4,
        "rationale": "Default 4-phase plan",
        "sprints": [
            {"sprint_number": 1, "name": "Sprint 1: Frontend Prototype & Bootstrap", "summary": "UI screens, navigation shell, mock data", "milestone": "Frontend Complete", "focus": "frontend"},
            {"sprint_number": 2, "name": "Sprint 2: Backend Services & Database", "summary": "DB models, REST endpoints, auth", "milestone": "Backend Complete", "focus": "backend"},
            {"sprint_number": 3, "name": "Sprint 3: Frontend-Backend Integration", "summary": "API wiring, state sync, DB checks", "milestone": "Integration Complete", "focus": "integration"},
            {"sprint_number": 4, "name": "Sprint 4: Testing & Deployment", "summary": "E2E testing, polish, deployment config", "milestone": "Production Ready", "focus": "testing"}
        ]
    }


def _parse_task_json(content: str) -> List[Dict[str, Any]]:
    """Parse LLM response and extract task JSON array with robust error handling"""
    try:
        # Remove markdown code blocks
        content = content.replace("```json", "").replace("```", "").strip()
        
        # Replace problematic Unicode box-drawing characters
        box_chars = {
            '├': '|--', '└': '`--', '│': '|  ', '─': '-',
            '┌': '+--', '┐': '--+', '┘': '--+', '┴': '+',
            '┬': '+', '┤': '+', '╭': '+', '╮': '+',
            '╯': '+', '╰': '+'
        }
        
        for unicode_char, ascii_replacement in box_chars.items():
            content = content.replace(unicode_char, ascii_replacement)
        
        # Handle literal \n in strings
        import re
        content = re.sub(r'\\n', ' ', content)
        content = content.replace('\t', '    ')
        content = content.replace('\r\n', '\n')
        content = content.replace('\r', '\n')
        
        # Find JSON array boundaries
        start_idx = content.find("[")
        end_idx = content.rfind("]")
        
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            content = content[start_idx:end_idx + 1]
        
        tasks = json.loads(content)
        
        if not isinstance(tasks, list):
            logger.error("Parsed content is not a list")
            return []
        
        return tasks
    
    except json.JSONDecodeError as e:
        # ── Truncation detection & salvage ──
        # LLM outputs can be cut off mid-response.  Detect that and try to
        # salvage partial tasks rather than returning nothing.
        content_stripped = content.strip()
        truncated_indicators = (
            not content_stripped.endswith(']')  # missing closing array bracket
            or content_stripped.endswith(',')     # trailing comma (incomplete object)
            or content_stripped.rfind('"') > content_stripped.rfind('}')  # string truncated mid-way
        )
        if truncated_indicators:
            try:
                salvaged = content_stripped
                open_braces = salvaged.count('{') - salvaged.count('}')
                open_brackets = salvaged.count('[') - salvaged.count(']')
                if open_braces > 0 or open_brackets > 0:
                    # Close any unterminated structures
                    # Remove trailing comma before closing (common truncation point)
                    while salvaged.rstrip().endswith(','):
                        salvaged = salvaged.rstrip()[:-1]
                    salvaged += '}' * max(open_braces, 0) + ']' * max(open_brackets, 0)
                    tasks = json.loads(salvaged)
                    if isinstance(tasks, list) and tasks:
                        logger.warning(
                            f"⚠️ LLM output was TRUNCATED — salvaged {len(tasks)} partial tasks "
                            f"(expected at least {len(tasks) + 1} based on truncation position)"
                        )
                        return tasks
            except Exception:
                pass
            logger.error(
                f"LLM output TRUNCATED and could not be salvaged. "
                f"Last 200 chars: ...{content_stripped[-200:]}"
            )
        else:
            logger.error(f"Failed to parse task JSON: {e}")
            logger.error(f"Content preview: {content[:500]}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error parsing task JSON: {e}")
        return []


def _sanitize_repository_tree_hierarchical(repo_structure: str) -> str:
    """Helper to strip python directories and files from src/ folders to avoid tree hallucinations"""
    if not repo_structure:
        return ""
    import re
    lines = repo_structure.split('\n')
    cleaned_lines = []
    path_stack = []
    ignore_until_level = None
    
    for line in lines:
        if not line.strip():
            cleaned_lines.append(line)
            continue
            
        match = re.search(r'([a-zA-Z0-9_\-\.\/]+(?:/)?)$', line)
        if not match:
            cleaned_lines.append(line)
            continue
            
        full_name = match.group(1).strip()
        is_dir = full_name.endswith('/')
        name = full_name.rstrip('/')
        
        # Determine indentation level
        leading_part = line[:match.start()]
        leading_stripped = re.sub(r'[│├└─]', ' ', leading_part)
        level = len(leading_stripped) - len(leading_stripped.lstrip(' '))
        
        while path_stack and path_stack[-1][0] >= level:
            path_stack.pop()
            
        if is_dir:
            path_stack.append((level, name))
        else:
            path_stack.append((level, name))
            
        current_path = "/".join([folder for _, folder in path_stack])
        
        # Check if we should pop out of ignored hierarchy
        if ignore_until_level is not None:
            if level <= ignore_until_level:
                ignore_until_level = None
            else:
                if is_dir:
                    path_stack.pop()
                continue
                
        # Check if we should start ignoring python files/folders inside frontend src/app
        if current_path.startswith("src/app") or "src/app/" in current_path:
            is_python = name.endswith('.py') or name in ['database', 'models', 'routers', 'schemas', 'services', 'migrations', '__init__.py']
            if is_python:
                ignore_until_level = level
                if is_dir:
                    path_stack.pop()
                continue
                
        cleaned_lines.append(line)
        if not is_dir:
            path_stack.pop()
            
    return "\n".join(cleaned_lines)


def clean_repository_structure_string(repo_structure: str) -> str:
    """Strip top-level container folder from ASCII directory tree if present and sanitize duplicate paths"""
    if not repo_structure:
        return ""
        
    lines = [line for line in repo_structure.split('\n') if line.strip()]
    if not lines:
        return ""
        
    first_line = lines[0].strip()
    # A root container directory name usually contains no tree-drawing characters
    if not any(c in first_line for c in ['│', '├', '└', '─', ' ']):
        is_container = True
        for line in lines[1:]:
            stripped = line.strip()
            if stripped and not any(line.startswith(c) for c in [' ', '│', '├', '└', '─', '┌', '┬', '┴']):
                is_container = False
                break
        
        if is_container:
            cleaned_lines = lines[1:]
            repo_structure = "\n".join(cleaned_lines)
            
    # Sanitize duplicate python folders inside frontend directories
    return _sanitize_repository_tree_hierarchical(repo_structure)


def _validate_task_structure(task: Dict[str, Any]) -> bool:
    """Validate that task has required fields"""
    
    critical_fields = ["task_id", "taskName", "task_type", "description"]
    for field in critical_fields:
        if field not in task or not task[field]:
            logger.warning(f"Task missing critical field: {field}")
            return False
    
    normalized_type = str(task.get("task_type", "")).upper().strip()
    valid_types = [
        "EPIC", "FEATURE", "STORY", "TASK", "BUG",
        "FRONTEND", "BACKEND", "INFRASTRUCTURE", "INTEGRATION",
        "DEVOPS", "QA", "TESTING", "DOCUMENTATION", "SECURITY",
        "PERFORMANCE", "ANALYSIS", "DATABASE", "UI", "API",
        "CONFIG", "ENHANCEMENT", "DESIGN", "ARCHITECTURE",
        "MIGRATION", "SETUP", "TOOLING", "FIX", "REFACTOR",
        "FEATURE", "DEV", "OPS", "TASK", "STORY",
        "QUALITY", "DEPLOYMENT",
    ]
    if normalized_type not in valid_types:
        logger.warning(f"Invalid task_type: {task.get('task_type')} (normalized: '{normalized_type}')")
        return False
    
    # Auto-fix task_wallet if missing
    wallet = task.get("task_wallet", None)
    if wallet is None:
        task_type = task.get("task_type", "TASK")
        task_type_upper = str(task_type).upper().strip()
        defaults = {
            "EPIC": 9, "FEATURE": 5, "STORY": 3, "TASK": 1, "BUG": 2,
            "FRONTEND": 5, "BACKEND": 5, "INFRASTRUCTURE": 8, "INTEGRATION": 3,
            "DEVOPS": 8, "QA": 5, "TESTING": 5, "DOCUMENTATION": 2, "SECURITY": 5,
            "PERFORMANCE": 3, "ANALYSIS": 3, "DATABASE": 5, "UI": 5, "API": 5,
            "CONFIG": 2, "ENHANCEMENT": 3, "DESIGN": 3, "ARCHITECTURE": 8,
            "MIGRATION": 5, "SETUP": 2, "TOOLING": 2, "FIX": 2, "REFACTOR": 3,
            "DEV": 5, "OPS": 5,
            "QUALITY": 5, "DEPLOYMENT": 5,
        }
        task["task_wallet"] = defaults.get(task_type_upper, 3)
        logger.info(f"Auto-fixed missing task_wallet → {task['task_wallet']} for {task.get('task_id')}")
    
    return True


def _validate_task_set_completeness(
    tasks: List[Dict[str, Any]], 
    project_token: str = ""
) -> List[str]:
    """
    Post-generation validation that checks the generated task set for:
    - TASK-00 existence (bootstrap task)
    - DAG connectivity (no orphan tasks with unresolvable linked_tasks)
    - Cross-reference integrity (every linked_task ID refers to an existing task)
    - Sprint ordering consistency (Sprint N+1 tasks only reference Sprint N or earlier)
    - No cycles in the dependency graph

    Returns a list of human-readable issue strings. Empty list = no issues.
    """
    issues: List[str] = []

    if not tasks:
        return ["No tasks generated at all"]

    # Build lookup maps
    task_ids: Set[str] = set()
    task_by_id: Dict[str, Dict[str, Any]] = {}
    sprint_order: Dict[str, float] = {}

    for t in tasks:
        tid = str(t.get("task_id", "")).strip().upper()
        if not tid:
            issues.append(f"Task '{t.get('taskName', t.get('title', '?'))}' has no task_id")
            continue
        task_ids.add(tid)
        task_by_id[tid] = t

        # Record sprint ordering for cross-sprint dependency checking
        sprint_raw = t.get("sprint") or t.get("sprint_id") or t.get("sprint_name", "")
        if sprint_raw:
            sprint_str = str(sprint_raw)
            # Try to extract numeric sprint order (Sprint 1 → 1.0)
            import re as _re_validate
            sprint_match = _re_validate.match(r"^\D*(\d+(?:\.\d+)?)", sprint_str)
            if sprint_match:
                sprint_order[tid] = float(sprint_match.group(1))
            else:
                sprint_order[tid] = float("inf")
        else:
            sprint_order[tid] = float("inf")

    # ── CHECK 1: TASK-00 existence ────────────────────────────
    if "TASK-00" not in task_ids:
        issues.append("CRITICAL: TASK-00 (bootstrap/scaffold task) is missing — every project must have a bootstrap gateway")

    # ── CHECK 2: linked_tasks cross-reference integrity ───────
    for tid, t in task_by_id.items():
        linked = t.get("linked_tasks", [])
        if not isinstance(linked, list):
            linked = []
        for link_id in linked:
            link_id_str = str(link_id).strip().upper()
            if link_id_str not in task_ids:
                issues.append(
                    f"Task '{tid}' references linked_tasks '{link_id_str}' which does NOT exist in the task set"
                )

    # ── CHECK 3: DAG cycle detection (simple DFS) ─────────────
    visited: Set[str] = set()
    rec_stack: Set[str] = set()

    def _has_cycle(node: str) -> bool:
        visited.add(node)
        rec_stack.add(node)
        t = task_by_id.get(node)
        if t:
            for link_id in (t.get("linked_tasks") or []):
                link_id_str = str(link_id).strip().upper()
                if link_id_str not in task_ids:
                    continue  # already caught in cross-ref check
                if link_id_str not in visited:
                    if _has_cycle(link_id_str):
                        return True
                elif link_id_str in rec_stack:
                    return True
        rec_stack.discard(node)
        return False

    for tid in task_ids:
        if tid not in visited:
            if _has_cycle(tid):
                issues.append(f"CRITICAL: Cyclic dependency detected involving task '{tid}'")
                break  # one cycle is enough — report once

    # ── CHECK 4: Sprint ordering — ensure no task depends on a later sprint ──
    for tid, t in task_by_id.items():
        tid_sprint = sprint_order.get(tid, float("inf"))
        linked = t.get("linked_tasks", [])
        if not isinstance(linked, list):
            linked = []
        for link_id in linked:
            link_id_str = str(link_id).strip().upper()
            link_sprint = sprint_order.get(link_id_str, float("inf"))
            # If dependency sprint > this task's sprint → forward dependency violation
            if link_sprint > tid_sprint and link_sprint != float("inf") and tid_sprint != float("inf"):
                issues.append(
                    f"Task '{tid}' (sprint ~{tid_sprint}) depends on '{link_id_str}' "
                    f"(sprint ~{link_sprint}) which is in a LATER sprint"
                )

    # ── CHECK 5: Ensure every non-TASK-00 executable task has at least one dependency ──
    # (in complex projects, isolated tasks with no links may indicate incomplete generation)
    if len(tasks) > 3:  # only warn for non-trivial projects
        unlinked: List[str] = []
        for tid, t in task_by_id.items():
            if tid == "TASK-00":
                continue
            task_type = str(t.get("task_type", "")).upper()
            if task_type not in ("TASK", "BUG", "ANALYSIS", "DEVELOPMENT", "TESTING"):
                continue
            linked = t.get("linked_tasks", [])
            if not linked or (isinstance(linked, list) and len(linked) == 1 and str(linked[0]).upper() == "TASK-00"):
                # Only warn if task ONLY depends on TASK-00 (no real dependencies)
                pass  # actually, TASK-00 dependency is the minimum — this is ok
            if not linked:
                unlinked.append(tid)
        if unlinked:
            issues.append(
                f"{len(unlinked)} executable tasks have NO linked_tasks at all: {', '.join(unlinked[:5])}"
                + (f"... (+{len(unlinked)-5} more)" if len(unlinked) > 5 else "")
            )

    return issues


def _score_task_quality(task: Dict[str, Any], task_id: str) -> Dict[str, Any]:
    """
    Score a single generated task on quality dimensions (0-10 scale).
    Returns {"score": int, "warnings": [str], "level": "good"|"ok"|"poor"}.

    Catches common LLM-generation problems before tasks reach agents.
    """
    warnings: List[str] = []
    score = 10  # start perfect, deduct for issues

    task_type = str(task.get("task_type", "")).upper()
    desc = str(task.get("description", "") or "")
    title = str(task.get("taskName", "") or task.get("title", "") or "")
    checklist = task.get("checklist", []) or []
    sprint = task.get("sprint") or task.get("sprint_id") or ""

    # Only score executable tasks; containers don't need fine-grained quality
    if task_type not in ("TASK", "BUG", "ANALYSIS", "DEVELOPMENT", "TESTING"):
        return {"score": 10, "warnings": [], "level": "good"}

    # ── Description length ──
    desc_len = len(desc.strip())
    if desc_len < 80:
        score -= 3
        warnings.append(f"Description too short ({desc_len} chars — should be 80+ for actionable context)")
    elif desc_len < 150:
        score -= 1

    # ── File paths in description ──
    import re as _re_q
    file_paths = _re_q.findall(r'[a-zA-Z0-9_\-]+/[a-zA-Z0-9_\-/.]+', desc)
    if not file_paths:
        score -= 2
        warnings.append("No file paths mentioned in description — agent may not know what to create")

    # ── Checklist completeness ──
    if isinstance(checklist, list):
        if len(checklist) < 2:
            score -= 2
            warnings.append(f"Only {len(checklist)} checklist item(s) — should have 3+ for verification")
    else:
        score -= 1
        warnings.append("Checklist is missing or not a list")

    # ── Title quality ──
    generic_titles = {"set up project", "create app", "add feature", "fix bug", "update code",
                      "implement functionality", "write tests", "setup", "init", "misc"}
    if title.strip().lower() in generic_titles or len(title.strip()) < 10:
        score -= 2
        warnings.append(f"Task title is too generic: '{title[:60]}' — should describe specific deliverable")

    # ── Sprint assignment ──
    if not sprint:
        score -= 1
        warnings.append("No sprint assigned — task may be executed out of order")

    # ── Story-first check for frontend tasks ──
    title_lower = title.lower()
    desc_lower = desc.lower()
    is_frontend = any(kw in title_lower or kw in desc_lower
                      for kw in ("screen", "page", "component", "ui", "frontend", "modal", "dashboard"))
    if is_frontend and task.get("sprint") and str(task.get("sprint", "")).lower().startswith("sprint 1"):
        if "[SCREEN STORY]" not in desc and "screen story" not in desc_lower:
            score -= 2
            warnings.append("Sprint 1 frontend task missing [SCREEN STORY] — agent may produce isolated dead UI")

    # ── Final level ──
    if score >= 7:
        level = "good"
    elif score >= 4:
        level = "ok"
    else:
        level = "poor"

    return {"score": max(score, 0), "warnings": warnings, "level": level}


def _generate_bootstrap_checklist(repo_structure: str, project_name: str) -> List[Dict[str, Any]]:
    """Generate detailed checklist items from repository structure for TASK-00"""
    
    checklist = []
    import re
    
    # Pre-clean the repo structure tree string
    repo_structure = clean_repository_structure_string(repo_structure)
    
    # Indentation-aware stack parser to reconstruct full hierarchical parent-child directory and file paths
    path_stack = []
    directories = []
    files = []
    
    for line in repo_structure.split('\n'):
        stripped = line.strip()
        if not stripped:
            continue
            
        # Match directory or file name at the end of the line
        match = re.search(r'([a-zA-Z0-9_\-./]+/?)\s*$', line)
        if not match:
            continue
            
        full_name = match.group(1).strip()
        is_dir = full_name.endswith('/')
        name = full_name.rstrip('/')
        
        if not name or name == project_name:
            continue
            
        # Determine indentation level by replacing tree-drawing characters with spaces and counting
        leading_part = line[:match.start()]
        leading_stripped = re.sub(r'[│├└─]', ' ', leading_part)
        level = (len(leading_stripped) - len(leading_stripped.lstrip(' '))) // 4
        
        # Pop standard stack levels to match our current depth
        while path_stack and path_stack[-1][0] >= level:
            path_stack.pop()
            
        if is_dir:
            path_stack.append((level, name))
            full_path = "/".join([folder for _, folder in path_stack])
            if full_path not in directories:
                directories.append(full_path)
        else:
            parent_path = "/".join([folder for _, folder in path_stack])
            full_path = f"{parent_path}/{name}" if parent_path else name
            if full_path not in files:
                files.append(full_path)
                
    # Normalize paths: strip common top-level container directory if all paths start with it
    if directories:
        root_candidates = [d for d in directories if '/' not in d]
        if len(root_candidates) == 1:
            root_dir = root_candidates[0]
            is_container = True
            for d in directories:
                if d != root_dir and not d.startswith(root_dir + '/'):
                    is_container = False
                    break
            for f in files:
                if not f.startswith(root_dir + '/'):
                    is_container = False
                    break
            
            if is_container:
                prefix_len = len(root_dir) + 1
                directories = [d[prefix_len:] for d in directories if d != root_dir]
                files = [f[prefix_len:] for f in files]
                logger.info(f"Stripped top-level container folder '{root_dir}' from bootstrap checklist paths.")
    
    # Add checklist items
    checklist.append({
        "text": "Verify working directory is /workspace (the repo root). DO NOT create a subdirectory.",
        "completed": False
    })
    
    checklist.append({
        "text": "Initialize git repository: git init",
        "completed": False
    })
    
    # Group directories by depth for proper creation order
    if directories:
        # Create main directories first
        main_dirs = [d for d in directories if d.count('/') <= 2]
        if main_dirs:
            dirs_str = ' '.join([d.rstrip('/') for d in main_dirs[:5]])
            checklist.append({
                "text": f"Create main directory structure: mkdir -p {dirs_str}",
                "completed": False
            })
        
        # Create subdirectories
        sub_dirs = [d for d in directories if d.count('/') > 2]
        if sub_dirs:
            for i in range(0, min(len(sub_dirs), 10), 3):
                batch = sub_dirs[i:i+3]
                dirs_str = ' '.join([d.rstrip('/') for d in batch])
                checklist.append({
                    "text": f"Create subdirectories: mkdir -p {dirs_str}",
                    "completed": False
                })
    
    # Add file creation items
    if files:
        # Group files by type
        config_files = [f for f in files if any(x in f.lower() for x in ['.env', '.json', '.yml', '.yaml', '.toml', '.ini', '.config', '.html'])]
        json_files = [f for f in files if f.endswith('.json')]
        code_files = [f for f in files if any(f.endswith(ext) for ext in ['.py', '.js', '.ts', '.jsx', '.tsx'])]
        doc_files = [f for f in files if any(f.endswith(ext) for ext in ['.md', '.txt', '.rst'])]
        
        if config_files:
            for config_file in config_files:
                checklist.append({
                    "text": f"Create config file: touch {config_file}",
                    "completed": False
                })
        
        # JSON validation step (cross-platform)
        if json_files:
            checklist.append({
                "text": "Validate JSON syntax: python3 -m json.tool package.json > /dev/null && echo 'package.json OK'",
                "completed": False
            })
        
        if doc_files:
            checklist.append({
                "text": f"Create documentation files: touch {' '.join([f for f in doc_files[:3]])}",
                "completed": False
            })
        
        if code_files:
            checklist.append({
                "text": f"Create placeholder code files: touch {' '.join(code_files)}",
                "completed": False
            })
    
    # --- Tech-stack-aware dependency installation step ---
    _all_file_basenames = [f.split('/')[-1].lower() for f in files]
    _has_package_json = 'package.json' in _all_file_basenames
    _has_requirements = 'requirements.txt' in _all_file_basenames
    _has_pyproject = 'pyproject.toml' in _all_file_basenames

    if _has_package_json:
        checklist.append({
            "text": "Install Node.js dependencies: npm install (verify node_modules/ is created and package-lock.json updated)",
            "completed": False
        })
    elif _has_requirements:
        checklist.append({
            "text": "Install Python dependencies: pip install -r requirements.txt (verify all packages install without errors)",
            "completed": False
        })
    elif _has_pyproject:
        checklist.append({
            "text": "Install Python project in editable mode: pip install -e . (verify package is importable)",
            "completed": False
        })

    # Add .gitignore
    checklist.append({
        "text": "Create .gitignore with appropriate rules for the tech stack",
        "completed": False
    })

    # Add README
    checklist.append({
        "text": "Create README.md with project overview and setup instructions",
        "completed": False
    })

    # Cross-platform structure verification (replaces Linux-only ls -R | wc -l)
    checklist.append({
        "text": (
            "Verify project structure (cross-platform): "
            "python3 -c \"import os; total=sum(len(d)+len(f) for _,d,f in os.walk('.') if '.git' not in _); "
            "print(f'Structure OK: {total} items found')\" "
            "(expect > 10 items)"
        ),
        "completed": False
    })

    # Enforce verification checklist items (Change #3 and Change #7) - Tech-stack agnostic
    primary_scaffold_file = "package.json" if _has_package_json else ("requirements.txt" if _has_requirements else "README.md")
    checklist.append({
        "text": f"Verify file exists: run `test -f {primary_scaffold_file}` and verify exit code 0",
        "completed": False
    })

    build_cmd = "npm run build" if _has_package_json else ("python3 -m py_compile $(find . -name '*.py')" if (_has_requirements or _has_pyproject) else "true")
    checklist.append({
        "text": f"Verify production build: run `{build_cmd}` and verify exit code 0 (no compilation errors)",
        "completed": False
    })

    dev_cmd = "npm run dev" if _has_package_json else ("python3 main.py --help" if (_has_requirements or _has_pyproject) else "true")
    checklist.append({
        "text": f"Verify development server: run `{dev_cmd}` and verify server/toolchain starts without console errors",
        "completed": False
    })

    checklist.append({
        "text": "Commit initial scaffold: git init && git add . && git commit -m 'chore: initial project scaffold'",
        "completed": False
    })

    return checklist


def _extract_repository_structure(analysis_text: str) -> str:
    """Extract the repository structure from section 0.5.1 or 0.5 of Agent Action Plan"""
    if not analysis_text:
        return ""
    
    import re
    
    # Look for section 0.5.1 OR 0.5 - match just the number, ignore title
    # UPDATED: Added more patterns to handle ai_service_chunked.py format
    patterns = [
        # Match: ## 0.5.1 (with or without title)
        r'##\s*0\.5\.1\s*[^\n]*\n(.*?)(?=\n##|\Z)',
        # Match: ### 0.5.1 (with or without title)
        r'###\s*0\.5\.1\s*[^\n]*\n(.*?)(?=\n###|\Z)',
        # Match: 0.5.1 anywhere (with or without title)
        r'0\.5\.1\s*[^\n]*\n(.*?)(?=\n##|\n###|\n\d+\.|\Z)',
        # Match: **0.5.1** (bold in markdown)
        r'\*\*0\.5\.1\*\*\s*[^\n]*\n(.*?)(?=\n##|\n###|\n\*\*\d+\.|\Z)',
        # NEW: Match section 0.5 (without subsection) - for ai_service_chunked.py format
        r'##\s*0\.5\s+Repository Structure Planning[^\n]*\n(.*?)(?=\n##|\n\d+\.|\Z)',
        r'###\s*0\.5\s+Repository Structure Planning[^\n]*\n(.*?)(?=\n###|\n\d+\.|\Z)',
        r'##\s*0\.5\s+[Rr]epository\s+[Ss]tructure[^\n]*\n(.*?)(?=\n##|\n\d+\.|\Z)',
        r'###\s*0\.5\s+[Rr]epository\s+[Ss]tructure[^\n]*\n(.*?)(?=\n###|\n\d+\.|\Z)',
        # Fallback: Just "0.5" followed by repository-related keywords
        r'0\.5\s+[Rr]epository[^\n]*\n(.*?)(?=\n##|\n###|\n\d+\.|\Z)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, analysis_text, re.IGNORECASE | re.DOTALL)
        if match:
            structure = match.group(1).strip()
            
            # Extract content from code blocks if present
            code_block_match = re.search(r'```(?:text|bash|shell|tree)?\s*(.*?)\s*```', structure, re.DOTALL)
            if code_block_match:
                extracted = code_block_match.group(1).strip()
                logger.info(f"✅ Extracted repository structure from section 0.5/0.5.1 (from code block, {len(extracted)} chars)")
                return extracted
            
            # If no code block, the structure might be directly in the text (ai_service_chunked.py format)
            # Look for lines that look like a directory tree (starting with project name or ├──)
            if structure and ('├──' in structure or '└──' in structure or structure.strip().endswith('/')):
                logger.info(f"✅ Extracted repository structure from section 0.5/0.5.1 (raw tree format, {len(structure)} chars)")
                return structure
            
            # If no tree characters but has content, return it anyway
            if structure and len(structure) > 50:  # Minimum length check
                logger.info(f"✅ Extracted repository structure from section 0.5/0.5.1 (raw content, {len(structure)} chars)")
                return structure
    
    logger.error("❌ Could not find section 0.5.1 or 0.5 in BRD analysis - agents will have no structure guidance!")
    return ""

def _get_real_repository_structure(repo_url: str, token: str = None, branch: str = None) -> str:
    """Clones repository to a temporary directory and scans its file structure"""
    import subprocess
    import os
    import tempfile
    import shutil
    import urllib.parse
    
    auth_url = repo_url
    if token:
        parsed = urllib.parse.urlparse(repo_url)
        # Safely insert the token for authentication
        auth_url = f"https://{token}@{parsed.netloc}{parsed.path}"
        
    temp_dir = tempfile.mkdtemp()
    try:
        clone_cmd = ["git", "clone", "--depth", "1"]
        if branch:
            clone_cmd.extend(["--branch", branch])
        clone_cmd.extend([auth_url, temp_dir])
        
        logger.info(f"Cloning repository for structure scanning: {repo_url} (branch: {branch or 'default'})")
        result = subprocess.run(clone_cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            logger.warning(f"Failed to clone repository for structure scanning: {result.stderr}")
            return ""
            
        exclude_dirs = {".git", "node_modules", "target", "bin", "build", "dist", ".gradle", ".mvn", "__pycache__"}
        
        tree_lines = []
        for root, dirs, files in os.walk(temp_dir):
            # Exclude directories in-place to avoid walking down them
            dirs[:] = [d for d in dirs if d not in exclude_dirs]
            
            rel_path = os.path.relpath(root, temp_dir)
            if rel_path == ".":
                depth = 0
            else:
                depth = rel_path.count(os.sep) + 1
                
            prefix = "│   " * (depth - 1) + "├── " if depth > 0 else ""
            
            if rel_path != ".":
                tree_lines.append(f"{prefix}{os.path.basename(root)}/")
                
            file_prefix = "│   " * depth + "├── "
            for file in sorted(files):
                ext = os.path.splitext(file)[1].lower()
                # Include source code, config and text files
                if ext in {".java", ".py", ".js", ".ts", ".tsx", ".jsx", ".xml", ".properties", ".yml", ".yaml", ".json", ".md", ".txt", ".sql", ".sh", ".cmd", ".bat", ".html", ".css", ".jsp", ".jspx", ".gradle", ".csproj", ".sln"}:
                    tree_lines.append(f"{file_prefix}{file}")
                    
        return "\n".join(tree_lines)
    except Exception as e:
        logger.error(f"Error scanning repository: {e}")
        return ""
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

def _build_project_context(
    project_token: str,
    db: Session,
    user_id: int
) -> Dict[str, Any]:
    """Build comprehensive project context from database"""
    
    context = {
        "project_token": project_token,
        "brd_analysis": "",
        "repository_structure": "",
        "governance_context": {},
        "project_type": "greenfield",
    }
    
    # Get governance response — support org-scoped visibility
    user = db.query(User).filter(User.id == user_id).first()
    org_name = str(user.organization_name).strip().lower() if user and user.organization_name else None

    if org_name:
        # Org-scoped: find governance from any member of the same org
        org_user_ids = db.query(User.id).filter(
            func.lower(User.organization_name) == org_name
        ).scalar_subquery()
        gov_response = db.query(GovernanceResponse).filter(
            GovernanceResponse.project_token == project_token,
            GovernanceResponse.owner_id.in_(org_user_ids)
        ).order_by(GovernanceResponse.id.desc()).first()
    else:
        # Personal scope: only this user
        gov_response = db.query(GovernanceResponse).filter(
            GovernanceResponse.project_token == project_token,
            GovernanceResponse.owner_id == user_id
        ).first()
    
    if gov_response:
        context["project_name"] = gov_response.project_name or project_token
        context["governance_context"] = {
            "classification": gov_response.classification,
            "weighted_score": gov_response.weighted_score,
        }
        if gov_response.project_type:
            context["project_type"] = gov_response.project_type
    
    # Get document analysis for this specific project — support org-scoped visibility
    # NOTE: We do NOT use a LIKE filter on analysis_result here because JSON can
    # store project_token as a quoted string, unquoted number, or null.
    # The LIKE pattern %"project_token": "VALUE"% would fail for numbers/null.
    # Instead, we fetch all docs with analysis_result and filter in Python below.
    if org_name:
        # Org-scoped: find documents from any member of the same org
        org_user_ids_doc = db.query(User.id).filter(
            func.lower(User.organization_name) == org_name
        ).scalar_subquery()
        candidate_docs = db.query(Document).filter(
            Document.owner_id.in_(org_user_ids_doc),
            Document.analysis_result.isnot(None)
        ).order_by(Document.upload_date.desc()).all()
    else:
        # Personal scope: only this user
        candidate_docs = db.query(Document).filter(
            Document.owner_id == user_id,
            Document.analysis_result.isnot(None)
        ).order_by(Document.upload_date.desc()).all()
    
    def _doc_matches_project(cand, proj_token, gov=None):
        """Check if a document's analysis_result references the given project_token
        (handles both flat keys and nested structures like projectMeta.project_token)."""
        try:
            cand_parsed = json.loads(cand.analysis_result)
            if not isinstance(cand_parsed, dict):
                return False
            # Check flat key (handle None/null by skipping comparison)
            pt = cand_parsed.get("project_token")
            if pt is not None and str(pt) == str(proj_token):
                return True
            # Check nested paths
            gov_ctx = cand_parsed.get("governanceContext") or {}
            proj_meta = cand_parsed.get("projectMeta") or {}
            # Use str() comparison to handle both string and number project_token
            pt_meta = proj_meta.get("project_token")
            if pt_meta is not None and str(pt_meta) == str(proj_token):
                return True
            pt_gov = gov_ctx.get("project_token")
            if pt_gov is not None and str(pt_gov) == str(proj_token):
                return True
            # Also check governance_result_id linkage
            if gov:
                gr_id = proj_meta.get("governance_result_id")
                if gr_id is not None and str(gr_id) == str(gov.id):
                    return True
            return False
        except Exception:
            return False
    
    document = None
    for cand in candidate_docs:
        if _doc_matches_project(cand, project_token, gov_response):
            document = cand
            break
    
    if not document:
        proj_name = context.get("project_name")
        display_name = f'"{proj_name}"' if proj_name and proj_name != project_token else "this project"
        raise ValueError(f"No requirement document or BRD analysis found for {display_name}. Please upload project documents and generate Agent Analysis first before creating tasks.")
    
    brd_analysis_structure = ""
    _raw_analysis_ok = False
    if document and document.analysis_result:
        try:
            analysis = json.loads(document.analysis_result)
            raw_analysis = analysis.get("analysis", "")
            if not raw_analysis and isinstance(analysis, str):
                raw_analysis = analysis
            
            if raw_analysis and raw_analysis.strip():
                _raw_analysis_ok = True
                context["brd_analysis"] = raw_analysis
                
                # Extract repository structure from section 0.5.1
                raw_struct = _extract_repository_structure(raw_analysis)
                brd_analysis_structure = clean_repository_structure_string(raw_struct)
                
                if "project_type" in analysis:
                    context["project_type"] = analysis["project_type"]
                elif "metrics" in analysis and isinstance(analysis.get("metrics"), dict) and "project_type" in analysis["metrics"]:
                    context["project_type"] = analysis["metrics"]["project_type"]
        except Exception as e:
            logger.warning(f"Failed to parse document analysis: {e}")
    
    # Check AFTER the try/except so the error isn't swallowed
    if not _raw_analysis_ok:
        proj_name = context.get("project_name")
        display_name = f'"{proj_name}"' if proj_name and proj_name != project_token else "this project"
        raise ValueError(
            f"AI Agent Analysis is not yet completed for {display_name}. "
            f"Please wait for the Agent Analysis to finish before creating tasks."
        )
            
    # Set the fallback repository structure
    context["repository_structure"] = brd_analysis_structure

    # Check if a repository is connected and contains files (for any project type)
    repo_url = None
    repo_token = None
    branch = None
    
    if gov_response:
        repo_url = gov_response.source_repo_url or gov_response.dest_repo_url
        repo_token = gov_response.source_repo_token or gov_response.dest_repo_token
        # Try to find a bootstrap branch
        try:
            from bootstrap_persistence import get_bootstrap_branch
            branch = get_bootstrap_branch(project_token)
        except Exception:
            pass
            
    if not repo_url:
        from models import AgentCredential
        cred = db.query(AgentCredential).filter(
            AgentCredential.project_token == project_token,
            AgentCredential.owner_id == user_id
        ).first()
        if cred:
            repo_url = cred.git_repo_url
            repo_token = cred.git_token
            
    if repo_url:
        logger.info(f"[{project_token}] Connected repository found: {repo_url}. Attempting to scan actual repository structure...")
        real_structure = _get_real_repository_structure(repo_url, repo_token, branch)
        if real_structure:
            context["repository_structure"] = real_structure
            logger.info(f"[{project_token}] Successfully scanned actual repository structure ({len(real_structure)} chars)")
        else:
            logger.warning(f"[{project_token}] Actual repository scan returned empty, keeping BRD-extracted structure as fallback")
            
    return context


# ─────────────────────────────────────────────────────────────────────────────
# SPRINT-SPECIFIC GENERATION PROMPTS
# Each sprint gets its own focused prompt so the LLM output stays small,
# never hits max_tokens, and never produces truncated JSON.
# ─────────────────────────────────────────────────────────────────────────────

ALL_SPRINTS_SINGLE_CALL_PROMPT = """You are generating ALL tasks for the entire project in ONE response.

Unlike the previous approach where tasks were split across 4 separate LLM calls (one per sprint),
this prompt asks you to generate EVERYTHING at once — all 4 sprints, all tasks — in a single JSON array.

## WHY THIS MATTERS
- Single call eliminates duplicate tasks (the #1 problem with multi-call generation)
- You can see the full picture and create proper dependencies between sprints
- You can ensure no two tasks overlap in file ownership
- You can number tasks correctly from the start (TASK-00 through TASK-NN)

## SPRINT STRUCTURE (generate ALL 4 sprints)

### Sprint 1 → Foundation, Navigation Shell & Fully-Linked Frontend Prototype
- TASK-00 (mandatory first task, index 0, task_id exactly "TASK-00", linked_tasks: [], task_wallet: 8)
  Creates: repo scaffold, React Router + ALL routes, AppLayout (collapsible sidebar + navbar),
  design tokens (tokens.css), global mockData.ts, shared UI component kit, backend health endpoint ONLY
- After TASK-00: one task per major screen/feature area
- NO backend code in Sprint 1 except entry-point skeleton
- Every Sprint 1 screen task uses the STORY-FIRST description format
- All Sprint 1 tasks (except TASK-00) have linked_tasks: ["TASK-00"]

### Sprint 2 → Backend Services, Database Setup & Core Configurations
- SQLAlchemy DB schemas, models, JWT auth, API routes, third-party integrations
- linked_tasks: ["TASK-00"] at minimum
- If a Sprint 2 task depends on a specific Sprint 1 frontend task, include it too

### Sprint 3 → Frontend-Backend Integration & Database Connectivity
- Replace mockData with React Query hooks / real API calls
- One integration task per major frontend-backend connection
- Each Sprint 3 task links to TASK-00 + its Sprint 1 source + its Sprint 2 backend task

### Sprint 4 → Testing, Polish & Production Deployment
- Frontend tests (Vitest), backend tests (Pytest), E2E tests
- Production deployment config (Docker, nginx, CI/CD)
- linked_tasks: TASK-00 + relevant Sprint 2/3 tasks

## CRITICAL: PROPER DEPENDENCY RESOLUTION
- linked_tasks MUST be SPECIFIC, not just ["TASK-00"] for everything
- Example correct dependencies:
  TASK-00 (Bootstrap) → linked_tasks: []
  TASK-01 (Auth UI) → linked_tasks: ["TASK-00"]
  TASK-02 (Dashboard) → linked_tasks: ["TASK-00"]
  TASK-03 (Auth Backend) → linked_tasks: ["TASK-00", "TASK-01"]
  TASK-04 (Dashboard Integration) → linked_tasks: ["TASK-00", "TASK-02", "TASK-03"]
  TASK-05 (Tests) → linked_tasks: ["TASK-00", "TASK-04"]

## DUPLICATE PREVENTION RULES
- NEVER create two tasks with the same or very similar title
- NEVER create two tasks that own the same files
- NEVER create two tasks with the same taskName
- If Sprint 1 creates "Auth UI" (login page), Sprint 2 creates "Auth Backend" (API endpoints),
  Sprint 3 creates "Auth Integration" (connecting them) — NOT another "Auth UI"
- Every task must have a UNIQUE purpose and UNIQUE file ownership

## CANONICAL PATH ENFORCEMENT
- ALL file paths in task descriptions, FILE OWNERSHIP blocks, and checklists MUST use the FULL canonical paths from the REPOSITORY STRUCTURE provided in the context.
- If the repository tree shows `frontend/src/`, then ALL frontend paths MUST start with `frontend/src/...` — NEVER bare `src/...`.
- If the repository tree shows `backend/app/`, then ALL backend paths MUST start with `backend/app/...` — NEVER bare `app/...`.
- Derive every path from the tree. Do NOT invent or assume path prefixes.

## OUTPUT RULES
- Return ONLY a valid JSON array — no markdown, no preamble, no explanation
- First element MUST be TASK-00 (task_id exactly "TASK-00", linked_tasks: [])
- Task IDs: TASK-00, TASK-01, TASK-02, ... sequential
- Every task must have: task_id, taskName, description, task_type, priority, task_wallet, sprint, milestone, linked_tasks, checklist, assignedTo, reported_by
- DESCRIPTIONS: Sprint 1 frontend tasks use the STORY-FIRST format. Sprint 2-4 tasks use concise ownership format.
- Use the repository structure and available sprints/milestones provided in the context.
- Generate all tasks for all 4 sprints in this single response.
"""


SPRINT1_GENERATION_PROMPT = """You are generating ONLY Sprint 1 tasks for a multi-sprint project plan.

SPRINT 1 SCOPE: Project Bootstrap + Fully-Linked Frontend Prototype
- TASK-00 must be FIRST (index 0), task_id exactly "TASK-00", linked_tasks: [], task_wallet: 8
- After TASK-00: one task per major screen/feature area — all linked_tasks: ["TASK-00"]
- NO backend DB schemas, NO models, NO third-party API configs — only entry-point skeleton in TASK-00
- Every Sprint 1 screen task uses the STORY-FIRST description format:
    [SCREEN STORY] narrative of user journey on this screen
    [SCREEN CONNECTIVITY] every button/link → exact /route target
    [MOCK DATA SPECIFICATION] entity name, field list, 8 realistic records
    [FILE OWNERSHIP] owns / must import from / must NOT modify
- Every interactive element MUST navigate or trigger state — zero dead UI

PRE-GENERATION CHECKLIST (do this mentally before writing JSON):
1. Lock TASK-00: repo scaffold, React Router + ALL routes, AppLayout (collapsible sidebar + navbar),
   design tokens (tokens.css), global mockData.ts with ALL entity types, shared UI kit, backend health endpoint.
2. Map every major screen (Login, Dashboard, entity lists, detail views, wizards, Settings, Profile, etc.)
3. Walk every user journey — confirm no dead ends, no missing screens
4. Confirm TASK-00 produces the files every other Sprint 1 task will IMPORT

TASK ID NUMBERING: Start at TASK-00. Increment sequentially: TASK-00, TASK-01, TASK-02 …

OUTPUT RULES:
- Return ONLY a valid JSON array — no markdown, no preamble, no explanation
- First element MUST be TASK-00
- All other Sprint 1 tasks have linked_tasks: ["TASK-00"]
- ALL file paths MUST use FULL canonical paths from the REPOSITORY STRUCTURE (e.g. `frontend/src/...` if the tree shows `frontend/src/`, NEVER bare `src/...`)

Generate Sprint 1 tasks now:"""

SPRINT2_GENERATION_PROMPT = """You are generating ONLY Sprint 2 tasks for a multi-sprint project plan.

SPRINT 2 SCOPE: Backend Services, Database Setup & Core Configurations
- SQLAlchemy DB schemas and models
- JWT authentication system
- All actual backend API routes, endpoints, and controllers
- Third-party API configurations and external service integrations (AWS, payment processors, email, etc.)
- NO frontend changes — Sprint 1 already built the UI prototype

DESCRIPTION FORMAT for Sprint 2 tasks (concise, ownership-focused):
"[What this service/module does]. This agent owns: [exact backend file paths].
This agent must create: [list of files with purpose]. This agent must NOT modify: [frontend/, Sprint 1 files]."

TASK ID NUMBERING: Start at TASK-{start_index} (continue from Sprint 1).

DEPENDENCY RULE: Every Sprint 2 task must include "TASK-00" in linked_tasks.

SPRINT 1 TASKS ALREADY GENERATED (for reference — use their task_ids in linked_tasks where relevant):
{sprint1_summary}

OUTPUT RULES:
- Return ONLY a valid JSON array — no markdown, no preamble, no explanation
- Every task linked_tasks must include "TASK-00" at minimum
- ALL file paths MUST use FULL canonical paths from the REPOSITORY STRUCTURE (e.g. `backend/app/...` if the tree shows `backend/app/`, NEVER bare `app/...`)

Generate Sprint 2 tasks now:"""

SPRINT3_GENERATION_PROMPT = """You are generating ONLY Sprint 3 tasks for a multi-sprint project plan.

SPRINT 3 SCOPE: Frontend-Backend Integration & Database Connectivity
- Connect Sprint 1 frontend screens to Sprint 2 real backend APIs
- Replace mockData imports with React Query fetch/mutation hooks in each screen
- Database connectivity verification
- JWT auth end-to-end validation
- System data flow testing

Each Sprint 3 task should correspond to one Sprint 1 frontend screen being wired to its Sprint 2 backend.
Create one integration task per major frontend-backend connection (e.g., "Wire Dashboard to /api/metrics",
"Connect User Management screen to /api/users CRUD endpoints", "Integrate Auth screen with JWT login flow").

DESCRIPTION FORMAT:
"[Screen name] integration: replace mockData import with React Query hooks calling [API endpoints].
This agent owns: [exact frontend page/hook files].
Sprint 1 source task: [TASK-XX]. Sprint 2 backend task: [TASK-YY].
This agent must NOT modify: backend/ API files (owned by Sprint 2 tasks)."

TASK ID NUMBERING: Start at TASK-{start_index} (continue from Sprint 2).

DEPENDENCY RULE: Every Sprint 3 task must link to TASK-00 + its Sprint 1 source + its Sprint 2 backend task.

SPRINT 1 TASKS (frontend screens already built):
{sprint1_summary}

SPRINT 2 TASKS (backend APIs already built):
{sprint2_summary}

OUTPUT RULES:
- Return ONLY a valid JSON array — no markdown, no preamble, no explanation
- Every task's linked_tasks must reference: ["TASK-00", "<Sprint1 task_id>", "<Sprint2 task_id>"]
- ALL file paths MUST use FULL canonical paths from the REPOSITORY STRUCTURE

Generate Sprint 3 tasks now:"""

SPRINT4_GENERATION_PROMPT = """You are generating ONLY Sprint 4 tasks for a multi-sprint project plan.

SPRINT 4 SCOPE: Testing, Polish & Production Deployment
- Comprehensive frontend unit/integration test suites (Vitest / React Testing Library)
- Backend test suites (Pytest) with endpoint and service coverage
- End-to-End system testing (Playwright or Cypress)
- Production deployment configuration (Docker, docker-compose, nginx, environment configs)
- Final documentation (API docs, README, deployment guide)
- Performance audit and accessibility review (optional but recommended)

Create granular tasks: one for frontend testing, one for backend testing, one for E2E, one for deployment.
Keep tasks small and focused so each agent has a clear, bounded scope.

DESCRIPTION FORMAT:
"[What this task tests or deploys]. This agent owns: [exact test/config file paths].
Commands to run: [exact test/build commands].
This agent must NOT modify: src/ or backend/ source files (only test and config files)."

TASK ID NUMBERING: Start at TASK-{start_index} (continue from Sprint 3).

DEPENDENCY RULE: Every Sprint 4 task must link to TASK-00 + relevant Sprint 2/3 tasks.

PREVIOUSLY GENERATED TASKS (all sprints — for linked_tasks reference):
{all_previous_summary}

OUTPUT RULES:
- Return ONLY a valid JSON array — no markdown, no preamble, no explanation
- Every task's linked_tasks must include "TASK-00" at minimum
- ALL file paths MUST use FULL canonical paths from the REPOSITORY STRUCTURE

Generate Sprint 4 tasks now:"""


def _build_tasks_summary(tasks: List[Dict[str, Any]]) -> str:
    """
    Build a compact summary of already-generated tasks to pass as context
    to subsequent sprint generation calls. Keeps token count low.
    """
    if not tasks:
        return "None generated yet."
    lines = []
    for t in tasks:
        task_id   = t.get("task_id", "?")
        task_name = t.get("taskName", "?")
        sprint    = t.get("sprint", "?")
        milestone = t.get("milestone", "?")
        owns      = ""
        desc      = t.get("description", "")
        # Extract a short ownership line from description
        for line in desc.splitlines():
            if "This agent owns:" in line:
                owns = line.strip()[:120]
                break
        lines.append(f"  {task_id}: {task_name} | Sprint: {sprint} | Milestone: {milestone}" + (f"\n    {owns}" if owns else ""))
    return "\n".join(lines)


def _renumber_task_ids(tasks: List[Dict[str, Any]], start_index: int) -> List[Dict[str, Any]]:
    """
    Re-map task IDs so they are sequential across sprints with no gaps or collisions.
    TASK-00 is always preserved as-is (index 0 of Sprint 1).
    Returns the tasks with updated task_id values and updated linked_tasks references.
    """
    if not tasks:
        return tasks

    id_map: Dict[str, str] = {}
    counter = start_index

    for task in tasks:
        old_id = task.get("task_id", "")
        # TASK-00 is sacred — never renumber it
        if old_id == "TASK-00":
            id_map[old_id] = "TASK-00"
        else:
            new_id = f"TASK-{counter:02d}"
            id_map[old_id] = new_id
            counter += 1

    # Apply the mapping
    for task in tasks:
        old_id = task.get("task_id", "")
        task["task_id"] = id_map.get(old_id, old_id)
        # Remap linked_tasks
        task["linked_tasks"] = [
            id_map.get(dep, dep) for dep in task.get("linked_tasks", [])
        ]

    return tasks


async def _generate_sprint_phase(
    sprint_number: int,
    sprint_prompt_template: str,
    prompt_context: str,
    api_url: Optional[str],
    api_key: Optional[str],
    model: Optional[str],
    project_token: str,
) -> List[Dict[str, Any]]:
    """
    Call the LLM to generate tasks for a single sprint phase.
    Returns the parsed task list, or [] on failure.
    """
    logger.info(f"  → Generating Sprint {sprint_number} tasks...")

    messages = [
        {"role": "system", "content": INTELLIGENT_TASK_GENERATION_PROMPT},
        {"role": "user",   "content": prompt_context + "\n\n" + sprint_prompt_template},
    ]

    try:
        response_content = await llm_gateway.call_llm_and_extract(
            messages=messages,
            api_url=api_url,
            api_key=api_key,
            model=model,
            timeout=180.0,
        )

        tasks = _parse_task_json(response_content)
        if not tasks:
            logger.warning(f"  Sprint {sprint_number}: LLM returned no parseable tasks")
            return []

        logger.info(f"  Sprint {sprint_number}: parsed {len(tasks)} tasks")
        return tasks

    except Exception as e:
        logger.error(f"  Sprint {sprint_number} generation failed: {e}")
        return []


async def generate_brownfield_tasks(
    project_token: str,
    context: Dict[str, Any],
    api_url: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    agent_list: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Generate tasks for brownfield/migration projects with skill-gap detection.

    Brownfield task generation rules:
    - NO TASK-00 (no project scaffold)
    - First task is always TASK-REPO-ANALYSIS (clone + analyze existing repo)
    - Subsequent tasks are file-level targeted change tasks
    - Each task specifies: target_file, change_type, precise description of what to change
    - Each task is tagged with required_skill and skill_flag

    Returns:
        Dict with keys:
            tasks: List of generated task dicts (each has required_skill, skill_flag)
            skill_gaps: {covered, missing, suggested_templates, has_gaps, gap_summary}
            detected_tech_stack: {primary, required_skills, required_agent_templates, detected}
    """
    from brownfield_agent_service import (
        get_brownfield_generation_context,
        BROWNFIELD_GENERATION_PROMPT,
        detect_required_tech_stack,
        compute_skill_gaps,
        tag_tasks_with_required_skills,
    )

    today = datetime.now().date()
    project_deadline = today + timedelta(days=28)

    sprints, milestones = _generate_sprints_and_milestones(
        project_start=datetime.combine(today, datetime.min.time()),
        project_deadline=datetime.combine(project_deadline, datetime.min.time()),
        num_phases=3,  # Brownfield: Analyze → Implement → Validate
        project_type="brownfield",
    )

    sprint_list = "\n".join([
        f"- {s['name']}: {s['start_date']} to {s['deadline']} ({s['summary']})"
        for s in sprints
    ])

    # Build brownfield-specific context
    brownfield_context = get_brownfield_generation_context(
        project_context=context,
        repo_structure=context.get("repository_structure"),
    )

    generation_prompt = f"""
{BROWNFIELD_GENERATION_PROMPT}

AVAILABLE SPRINTS:
==================
{sprint_list}

CURRENT DATE: {today.strftime('%Y-%m-%d')}
PROJECT DEADLINE: {project_deadline.strftime('%Y-%m-%d')}

{brownfield_context}

=== BRD / CHANGE REQUEST DOCUMENT ===
{context.get('brd_analysis', 'No analysis available')}
===

Generate a complete list of brownfield tasks. Output ONLY a valid JSON array.
The FIRST task MUST be task_id "TASK-REPO-ANALYSIS".
Do NOT include any TASK-00 or project scaffold tasks.
Each task MUST include: task_id, taskName, description, task_type, target_file, change_type, priority, sprint, milestone, task_wallet, deadline, startdate, linked_tasks, checklist.
"""

    logger.info(f"[{project_token}] Brownfield task generation — calling LLM")
    model_name = llm_gateway.resolve_model(model)

    try:
        raw_response = await llm_gateway.call_llm(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a senior technical project manager specializing in brownfield development. "
                        "Generate precise, actionable tasks for modifying an existing codebase. "
                        "Output ONLY a valid JSON array of task objects with no markdown wrapping."
                    ),
                },
                {"role": "user", "content": generation_prompt},
            ],
            api_url=api_url,
            api_key=api_key,
            model=model_name,
        )

        content = ""
        if isinstance(raw_response, dict):
            content = llm_gateway.extract_content_from_response(raw_response)
        elif isinstance(raw_response, str):
            content = raw_response

        tasks = _parse_task_json(content)

    except Exception as exc:
        logger.error(f"[{project_token}] Brownfield LLM call failed: {exc}")
        tasks = []

    if not tasks:
        logger.warning(f"[{project_token}] Brownfield LLM returned no tasks — using fallback")
        # Fallback: return minimal TASK-REPO-ANALYSIS only
        tasks = [
            {
                "task_id": "TASK-REPO-ANALYSIS",
                "taskName": "Repo Analysis and Change Planning",
                "description": (
                    "Clone the existing repository. Analyze the full codebase structure. "
                    "Map each requirement from the change request to specific existing files and "
                    "functions that must be modified. Produce a structured change impact report."
                ),
                "task_type": "analysis",
                "target_file": None,
                "change_type": "analyze",
                "priority": "critical",
                "sprint": sprints[0]["name"] if sprints else "Sprint 1",
                "milestone": milestones[0]["name"] if milestones else "Milestone 1",
                "task_wallet": 3,
                "startdate": today.strftime("%Y-%m-%d"),
                "deadline": (today + timedelta(days=3)).strftime("%Y-%m-%d"),
                "linked_tasks": [],
                "checklist": [
                    "Clone repository at user-specified branch",
                    "Scan all existing files and directories",
                    "Map each requirement to affected file(s)",
                    "Identify regression risks",
                    "Document change impact report",
                ],
                "assignedTo": [],
                "reported_by": "system",
            }
        ]

    # Enrich tasks
    valid_tasks = []
    for task in tasks:
        if not task.get("task_id") or not task.get("taskName"):
            continue

        task.setdefault("assignedTo", [])
        task.setdefault("reported_by", "system")
        task.setdefault("priority", "medium")
        task.setdefault("linked_tasks", [])
        task.setdefault("target_file", None)
        task.setdefault("change_type", "modify")

        if not task.get("sprint"):
            task["sprint"] = sprints[0]["name"] if sprints else "Sprint 1"
        if not task.get("milestone"):
            task["milestone"] = milestones[0]["name"] if milestones else "Milestone 1"

        if "startdate" not in task:
            task["startdate"] = today.strftime("%Y-%m-%d")
        task.setdefault("planned_start", task["startdate"])
        if "deadline" not in task:
            task["deadline"] = project_deadline.strftime("%Y-%m-%d")

        # Ensure TASK-REPO-ANALYSIS is the dependency for all other tasks
        if task["task_id"] != "TASK-REPO-ANALYSIS":
            linked = task.get("linked_tasks", [])
            if "TASK-REPO-ANALYSIS" not in linked:
                linked.insert(0, "TASK-REPO-ANALYSIS")
            task["linked_tasks"] = linked

        valid_tasks.append(task)

    # ── Skill-gap detection ──────────────────────────────────────────────────
    # Detect required tech stack from BRD text + repo file inventory
    brd_text = str(context.get("brd_analysis", ""))
    repo_structure_text = str(context.get("repository_structure", ""))
    # Flatten repo structure text into a pseudo file-list for extension detection
    repo_file_lines = [
        line.strip() for line in repo_structure_text.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]

    tech_stack = detect_required_tech_stack(
        brd_text=brd_text,
        repo_files=repo_file_lines,
        repo_structure_text=repo_structure_text,
    )

    skill_gaps = compute_skill_gaps(
        required_skills=tech_stack["required_skills"],
        required_agent_templates=tech_stack["required_agent_templates"],
        agent_list=agent_list or [],
    )

    # Tag every task with required_skill and skill_flag
    valid_tasks = tag_tasks_with_required_skills(valid_tasks, tech_stack, skill_gaps)

    if skill_gaps["has_gaps"]:
        logger.warning(
            f"[{project_token}] SKILL GAPS DETECTED — {skill_gaps['gap_summary']}"
        )
    else:
        logger.info(f"[{project_token}] Skill check passed — all required skills are covered")

    logger.info(f"[{project_token}] Brownfield generation complete — {len(valid_tasks)} tasks")

    return {
        "tasks": valid_tasks,
        "skill_gaps": skill_gaps,
        "detected_tech_stack": tech_stack,
    }





async def generate_tasks_locally(
    project_token: str,
    db: Session,
    user_id: int,
    custom_rules: Optional[str] = None,
    process_mode: str = "ai_first",
    project_type: str = "greenfield",
    prerequisites: Optional[List[Dict[str, Any]]] = None,
    api_url: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    branch: Optional[str] = None,
    sprint_callback: Optional[Any] = None,
) -> List[Dict[str, Any]]:
    """
    Generate tasks using AI with multiple sprints and milestones
    
    Returns:
        List of generated task dictionaries
    """

    if not llm_gateway.check_api_key(api_key):
        raise Exception("API key not configured for task generation")

    # ── 1. Build project context ───────────────────────────────────────────────
    context = _build_project_context(project_token, db, user_id)
    
    # If the caller passed a generic "greenfield" but the document analysis
    # detected something else (e.g. "brownfield"), use the detected type.
    if project_type == "greenfield" and context.get("project_type") and context["project_type"] != "greenfield":
        project_type = context["project_type"]
        logger.info(f"[{project_token}] Overriding default greenfield with document-detected project_type: {project_type}")
    elif project_type:
        context["project_type"] = project_type

    from brownfield_agent_service import is_brownfield_project
    if is_brownfield_project(project_type):
        if branch:
            from bootstrap_persistence import set_bootstrap_branch
            set_bootstrap_branch(project_token, branch)
            context["bootstrap_branch"] = branch
            logger.info(f"[{project_token}] Saved branch for brownfield bootstrap: {branch}")

    # ── BROWNFIELD / MIGRATION PATH ────────────────────────────────────────────
    # For brownfield/migration projects, use a completely different generation
    # strategy: no TASK-00, no scaffold tasks, file-level change tasks only.
    if is_brownfield_project(project_type):
        logger.info(f"[{project_token}] BROWNFIELD mode — routing to brownfield task generation")
        
        # Query agents to check skill gaps via organization mappings
        from sqlalchemy import text
        user_row = db.execute(
            text("SELECT organization_name FROM users WHERE id = :uid"),
            {"uid": user_id}
        ).fetchone()
        user_org = user_row[0] if user_row else None
        
        if user_org:
            all_agents = db.execute(
                text("""
                    SELECT a.skills_tags, a.name, a.specialization 
                    FROM agents a
                    JOIN organization_agent_mappings m ON a.id = m.agent_id
                    WHERE lower(m.organization_name) = :org_name
                """),
                {"org_name": user_org.lower()}
            ).fetchall()
        else:
            all_agents = db.execute(
                text("SELECT skills_tags, name, specialization FROM agents WHERE project_token = :project_token OR project_token IS NULL"),
                {"project_token": project_token}
            ).fetchall()

        agent_list = [
            {"name": row[1], "skills_tags": row[0], "specialization": row[2]}
            for row in all_agents
        ]
        
        return await generate_brownfield_tasks(
            project_token=project_token,
            context=context,
            api_url=api_url,
            api_key=api_key,
            model=model,
            agent_list=agent_list,
        )

    # ── 2. Timeline ────────────────────────────────────────────────────────────
    today = datetime.now().date()
    if process_mode == "ai_first":
        project_deadline = today + timedelta(days=28)
    elif process_mode == "vibe_coding":
        project_deadline = today + timedelta(days=42)
    else:
        project_deadline = today + timedelta(days=84)

    # ── 3. Sprints & milestones ────────────────────────────────────────────────
    sprints, milestones = _generate_sprints_and_milestones(
        project_start=datetime.combine(today, datetime.min.time()),
        project_deadline=datetime.combine(project_deadline, datetime.min.time()),
        num_phases=4,
    )
    logger.info(f"[{project_token}] Sprint-wise generation — {len(sprints)} sprints")

    sprint_list = "\n".join([
        f"- {s['name']}: {s['start_date']} to {s['deadline']} ({s['summary']})"
        for s in sprints
    ])
    milestone_list = "\n".join([
        f"- {m['name']}: {m['summary']} (Sprint: {m['sprint']})"
        for m in milestones
    ])

    # ── 4. Shared context block (injected into every sprint LLM call) ────────
    gov_ctx = context.get('governance_context', {}) or {}
    governance_block = f"""
GOVERNANCE CONTEXT:
====================
Project Type:      {context.get('project_type', 'Not specified')}
Classification:    {gov_ctx.get('classification', 'Not available')}
Weighted Score:    {gov_ctx.get('weighted_score', 'Not available')}
"""

    raw_brd_analysis = context.get('brd_analysis', '')
    
    # ── 4b. Chunked BRD Summarization for large documents (> 15,000 chars) ───
    if raw_brd_analysis and len(raw_brd_analysis) > 15000:
        logger.info(f"[{project_token}] Raw BRD length {len(raw_brd_analysis)} exceeds 15,000 chars. Executing chunked BRD analysis...")
        raw_brd_analysis = await _chunk_and_summarize_brd(
            raw_text=raw_brd_analysis,
            api_url=api_url,
            api_key=api_key,
            model=model,
        )

    # ── 4c. AI Dynamic Sprint Planning ────────────────────────────────────────
    ai_sprint_plan = await _ai_plan_sprints(
        brd_context=raw_brd_analysis,
        project_type=project_type,
        process_mode=process_mode,
        api_url=api_url,
        api_key=api_key,
        model=model,
    )
    ai_sprints = ai_sprint_plan.get("sprints", [])
    total_sprints_count = len(ai_sprints)
    logger.info(f"[{project_token}] AI Dynamic Sprint Planning determined {total_sprints_count} sprints")

    # Update job manager total sprints count if job exists
    from task_generation_job_manager import get_task_generation_job_manager
    job = get_task_generation_job_manager().get_job(project_token)
    if job:
        job.set_total_sprints(total_sprints_count)

    sprint_list = "\n".join([
        f"- {s.get('name')}: ({s.get('summary')})"
        for s in ai_sprints
    ])
    milestone_list = "\n".join([
        f"- {s.get('milestone')}: (Sprint: {s.get('name')})"
        for s in ai_sprints if s.get('milestone')
    ])

    brd_block = f"""
AVAILABLE SPRINTS (AI Planned):
================================
{sprint_list}

AVAILABLE MILESTONES:
====================
{milestone_list}

REPOSITORY STRUCTURE (from section 0.5.1):
==========================================
{context.get('repository_structure', 'Not available')}

{governance_block}
CURRENT DATE: {today.strftime('%Y-%m-%d')}
PROJECT DEADLINE: {project_deadline.strftime('%Y-%m-%d')}

===================================================================
AGENT ACTION PLAN MARKDOWN DOCUMENT
===================================================================
{raw_brd_analysis if raw_brd_analysis else 'No Agent Action Plan available'}
===================================================================
"""

    # ── 5. PER-SPRINT DYNAMIC SEQUENTIAL GENERATION ───────────────────────────
    logger.info(f"[{project_token}] Per-sprint sequential generation — {total_sprints_count} AI-planned sprints")

    all_tasks: List[Dict[str, Any]] = []

    import asyncio
    async def _notify_sprint(sprint_num: int, sprint_name: str, tasks: List[Dict[str, Any]]):
        if sprint_callback:
            try:
                res = sprint_callback(sprint_num, sprint_name, tasks)
                if asyncio.iscoroutine(res):
                    await res
            except Exception as cb_err:
                logger.warning(f"[{project_token}] Sprint {sprint_num} callback error: {cb_err}")

    # Generate tasks dynamically for each AI-planned sprint
    for s_idx, sp in enumerate(ai_sprints):
        sprint_num = sp.get("sprint_number", s_idx + 1)
        sprint_name = sp.get("name", f"Sprint {sprint_num}")
        sprint_summary = sp.get("summary", "")
        sprint_focus = sp.get("focus", "general")

        if job:
            job.update_sprint_start(sprint_num, sprint_name)

        logger.info(f"  → Generating Sprint {sprint_num}/{total_sprints_count}: {sprint_name}...")

        prev_summary = _build_tasks_summary(all_tasks) if all_tasks else "No previous tasks generated yet."

        prompt_content = f"""{brd_block}

CURRENT SPRINT SCOPE ({sprint_num} of {total_sprints_count}):
===================================================================
Sprint Name: {sprint_name}
Sprint Summary: {sprint_summary}
Sprint Focus Target: {sprint_focus}
Start Task Index: {len(all_tasks) + 1}

PREVIOUS SPRINTS TASK SUMMARY:
===================================================================
{prev_summary}

INSTRUCTIONS:
Generate 3 to 8 actionable, technical, story-first tasks specifically for {sprint_name}.
Set the "sprint" field of every generated task to "{sprint_name}".
Set the "milestone" field of every generated task to "{sp.get('milestone', '')}".
"""

        messages_sprint = [
            {"role": "system", "content": INTELLIGENT_TASK_GENERATION_PROMPT},
            {"role": "user", "content": prompt_content},
        ]

        try:
            response_sprint = await llm_gateway.call_llm_and_extract(
                messages=messages_sprint, api_url=api_url, api_key=api_key, model=model, timeout=180.0, retries=3
            )
            tasks_sprint = _parse_task_json(response_sprint)
            if tasks_sprint:
                all_tasks.extend(tasks_sprint)
                logger.info(f"[{project_token}] Sprint {sprint_num} generated {len(tasks_sprint)} tasks")
                await _notify_sprint(sprint_num, sprint_name, tasks_sprint)
            else:
                logger.warning(f"[{project_token}] Sprint {sprint_num} generated 0 tasks")
        except Exception as e:
            logger.error(f"[{project_token}] Sprint {sprint_num} generation failed: {e}")

    if not all_tasks:
        logger.error(f"[{project_token}] No tasks generated from any sprint")
        return []

    # Cross-sprint deduplication (removes any overlap between sprints)
    before_dedup = len(all_tasks)
    all_tasks = _deduplicate_tasks(all_tasks)
    if len(all_tasks) < before_dedup:
        logger.info(f"[{project_token}] Cross-sprint dedup removed {before_dedup - len(all_tasks)} tasks")

    logger.info(f"[{project_token}] Per-sprint generation complete — {len(all_tasks)} tasks across all sprints")

    # ── 5b. Validate and ensure TASK-00 exists ─────────────────────────────────
    if not all_tasks:
        logger.error(f"[{project_token}] No tasks generated from single-call")
        return []

    # Ensure TASK-00 is the first element
    task_00 = next((t for t in all_tasks if t.get("task_id") == "TASK-00"), None)
    if not task_00:
        logger.warning(f"[{project_token}] TASK-00 not found in single-call output — renumbering from 1")
        all_tasks = _renumber_task_ids(all_tasks, start_index=1)
        # Insert a minimal TASK-00 if truly missing
        if not any(t.get("task_id") == "TASK-00" for t in all_tasks):
            logger.warning(f"[{project_token}] No TASK-00 at all — adding scaffold task")
            scaffold = {
                "task_id": "TASK-00",
                "taskName": "Project Bootstrap & Shared Foundation",
                "description": "Project bootstrap: repository scaffold, navigation shell, design tokens, mock data store, and shared UI components.\nThis agent owns: all config files and shared foundation directories as defined in the canonical repository structure.",
                "task_type": "TASK",
                "priority": "high",
                "task_wallet": 8,
                "sprint": sprints[0]["name"],
                "milestone": milestones[0]["name"],
                "assignedTo": [],
                "linked_tasks": [],
                "reported_by": "system",
                "checklist": [{"text": "Scaffold repository structure", "completed": False}]
            }
            all_tasks.insert(0, scaffold)

    # ── 5c. DEDUPLICATE FIRST (before renumbering to keep IDs clean) ────────────
    before_dedup = len(all_tasks)
    all_tasks = _deduplicate_tasks(all_tasks)
    if len(all_tasks) < before_dedup:
        logger.info(f"[{project_token}] Dedup removed {before_dedup - len(all_tasks)} tasks")

    # ── 5d. Renumber tasks sequentially (AFTER dedup, so IDs have no gaps) ─────
    all_tasks = _renumber_task_ids(all_tasks, start_index=1)
    sprint_map = {}
    for s in sprints:
        sprint_map[s["name"]] = s["name"]
    milestone_map = {}
    for m in milestones:
        milestone_map[m["name"]] = m["name"]

    for t in all_tasks:
        task_sprint = t.get("sprint", "")
        if task_sprint and task_sprint in sprint_map:
            pass  # Keep the LLM-assigned sprint
        else:
            # Infer sprint from task description keywords
            desc = str(t.get("description", "")).lower()
            if any(kw in desc for kw in ["test", "deploy", "production", "docker"]):
                t["sprint"] = sprints[3]["name"] if len(sprints) > 3 else sprints[-1]["name"]
            elif any(kw in desc for kw in ["integrat", "connect", "wire", "api call"]):
                t["sprint"] = sprints[2]["name"] if len(sprints) > 2 else sprints[-1]["name"]
            elif any(kw in desc for kw in ["backend", "api ", "database", "model", "schema"]):
                t["sprint"] = sprints[1]["name"] if len(sprints) > 1 else sprints[-1]["name"]
            else:
                t["sprint"] = sprints[0]["name"]
        t.setdefault("milestone", milestones[0]["name"])

    # ── 5f. Ensure every task has TASK-00 in linked_tasks (except TASK-00 itself) ─
    for t in all_tasks:
        if t.get("task_id") != "TASK-00":
            linked = t.setdefault("linked_tasks", [])
            if "TASK-00" not in linked:
                linked.insert(0, "TASK-00")
            t["linked_tasks"] = linked

    logger.info(f"[{project_token}] Single-call generation complete — {len(all_tasks)} tasks after dedup")

    # ── Helper: detect frontend prefix from canonical tree ────────────────────
    def _detect_frontend_prefix(tree_text: str) -> str:
        """
        Scan the canonical repository tree to find the parent directory
        that wraps 'src/' (e.g. 'frontend/'). Returns '' if src/ is at root.
        
        Works with any tree format:
          ├── frontend/
          │   ├── src/
        """
        import re
        lines = tree_text.splitlines()

        def _get_depth(line):
            """Count nesting depth by counting tree connector groups (each ~4 chars)."""
            stripped = line.rstrip()
            if not stripped:
                return -1
            depth = 0
            pos = 0
            while pos < len(stripped):
                chunk = stripped[pos:pos+4]
                if chunk in ('│   ', '├── ', '└── ', '    ', '|   '):
                    depth += 1
                    pos += 4
                elif stripped[pos:pos+3] in ('├──', '└──'):
                    depth += 1
                    pos += 3
                    break
                else:
                    break
            return depth

        def _get_name(line):
            """Extract the clean name from a tree line."""
            return re.sub(r'^[\s│├└─\-\|]+', '', line).strip()

        for i, line in enumerate(lines):
            name = _get_name(line)
            if name in ('src/', 'src'):
                src_depth = _get_depth(line)
                # Walk backwards to find parent (lower depth)
                for j in range(i - 1, -1, -1):
                    parent_name = _get_name(lines[j])
                    parent_depth = _get_depth(lines[j])
                    if parent_depth < src_depth and parent_name and parent_name not in ('.', './', ''):
                        parent_dir = parent_name.rstrip('/') + '/'
                        if parent_dir in ('.', './', '/'):
                            return ''
                        return parent_dir
                # No parent found → src/ is at root
                return ''
        return ''

    # ── 6. Validate, enrich, inject repo structure ─────────────────────────────
    valid_tasks: List[Dict[str, Any]] = []
    repo_structure = context.get("repository_structure", "")
    project_name   = context.get("project_name", "project")

    for task in all_tasks:
        if not _validate_task_structure(task):
            continue

        # Required field defaults
        task.setdefault("assignedTo",   [])
        task.setdefault("reported_by",  "system")
        task.setdefault("priority",     "medium")
        task.setdefault("linked_tasks", [])

        # Sprint / milestone guard
        if not task.get("sprint"):
            task["sprint"] = sprints[0]["name"]
        if not task.get("milestone"):
            task["milestone"] = milestones[0]["name"]

        # Date defaults
        if "startdate" not in task:
            task["startdate"] = today.strftime('%Y-%m-%d')
        task.setdefault("planned_start", task["startdate"])
        if "deadline" not in task:
            task["deadline"] = (today + timedelta(days=min(task["task_wallet"], 7))).strftime('%Y-%m-%d')

        # ── Normalize paths in description to match canonical tree ────────────
        # Detect if the canonical repo tree has a frontend/ wrapper around src/
        # If so, fix any bare src/ references in the description to use frontend/src/
        if repo_structure:
            import re
            desc = task.get("description", "")
            if desc:
                fe_prefix = _detect_frontend_prefix(repo_structure)

                # If we found a frontend prefix (e.g. "frontend/"), fix bare src/ paths
                if fe_prefix:
                    # Replace bare src/ references that are NOT already prefixed
                    prefix_no_slash = fe_prefix.rstrip("/")
                    desc = re.sub(
                        r'(?<!' + re.escape(prefix_no_slash) + r'/)(?<![a-zA-Z0-9_-])(src/)',
                        fe_prefix + r'src/',
                        desc
                    )
                    task["description"] = desc

        # ── Inject repo structure ──────────────────────────────────────────────
        if repo_structure:
            if task.get("task_id") == "TASK-00":
                structure_block = (
                    f"\n\n===BEGIN_DIRECTORY_STRUCTURE===\n{repo_structure}\n===END_DIRECTORY_STRUCTURE===\n\n"
                    "CRITICAL: This is the CANONICAL directory structure for the entire project. "
                    "You MUST create ALL directories and files shown above. "
                    "ALL subsequent tasks MUST reference files from this structure. "
                    "ALL agents MUST wait for this task to complete before starting their own work."
                )
                task["description"] = task.get("description", "") + structure_block

                detailed_checklist = _generate_bootstrap_checklist(repo_structure, project_name)
                if detailed_checklist:
                    task["checklist"] = detailed_checklist
                    logger.info(f"✅ TASK-00: injected repo structure + {len(detailed_checklist)} checklist items")
            else:
                structure_reference = (
                    f"\n\n===CANONICAL_REPOSITORY_STRUCTURE===\n{repo_structure}\n===END_STRUCTURE===\n\n"
                    "⚠️ CRITICAL FILE PATH RULES:\n"
                    "1. Use ONLY file paths from the CANONICAL_REPOSITORY_STRUCTURE above\n"
                    "2. Do NOT invent new file paths or directory structures\n"
                    "3. Validate every file path against the canonical structure before creating it\n\n"
                )
                task["description"] = task.get("description", "") + structure_reference

        # Enforce verification checklist items for other Sprint 1 tasks (Change #3 and Change #7)
        task_id = task.get("task_id", "")
        if task_id != "TASK-00" and task.get("sprint") == sprints[0]["name"]:
            checklist = task.setdefault("checklist", [])
            
            # Check if build/dev server checks already exist to avoid duplicates
            has_build_check = any("run build" in item.get("text", "").lower() or "production build" in item.get("text", "").lower() for item in checklist)
            has_dev_check = any("run dev" in item.get("text", "").lower() or "development server" in item.get("text", "").lower() for item in checklist)
            
            # Smart file target detection from description or files
            # Match full canonical paths: frontend/src/..., backend/..., or bare src/...
            import re
            file_matches = re.findall(r'((?:[a-zA-Z0-9_-]+/)*src/[a-zA-Z0-9_\-/]+\.(?:tsx|jsx|ts|js|css))', task.get("description", ""))
            if not file_matches:
                # Also try backend paths like backend/app/models.py
                file_matches = re.findall(r'((?:[a-zA-Z0-9_-]+/)+[a-zA-Z0-9_\-/]+\.(?:py|rb|go|java|rs|php))', task.get("description", ""))
            primary_file = file_matches[0] if file_matches else None
            
            if primary_file and not any(f"test -f {primary_file}" in item.get("text", "") for item in checklist):
                checklist.append({
                    "text": f"Verify file exists: run `test -f {primary_file}` and verify exit code 0",
                    "completed": False
                })
                
            # --- Smart subcomponent integration check ---
            desc_text = task.get("description", "")
            title_text = task.get("taskName", "")
            task_files = re.findall(r'((?:[a-zA-Z0-9_-]+/)*src/[a-zA-Z0-9_\-/]+\.(?:tsx|jsx|ts|js))', desc_text)
            
            # Find React component names mentioned in the description, excluding common React terms
            matches = set(re.findall(r'\b(Task[A-Z][a-zA-Z0-9]+|[A-Z][a-zA-Z0-9]+List|[A-Z][a-zA-Z0-9]+Item|[A-Z][a-zA-Z0-9]+Filter|[A-Z][a-zA-Z0-9]+Form|[A-Z][a-zA-Z0-9]+Stats)\b', desc_text + " " + title_text))
            
            subcomponents = []
            for comp in matches:
                is_sub = True
                for tf in task_files:
                    if comp in tf:
                        is_sub = False
                        break
                if is_sub and comp not in ['React', 'Component', 'AppLayout', 'App', 'LoadingSpinner', 'Button', 'Badge', 'Card', 'Modal', 'Drawer', 'Toast', 'EmptyState', 'PageHeader']:
                    subcomponents.append(comp)
            
            if subcomponents and task_files:
                sub_list = sorted(list(set(subcomponents)))[:3]
                sub_check_cmds = []
                for sub in sub_list:
                    check_parts = [f'grep -qi "{sub}" {tf}' for tf in task_files]
                    sub_check_cmds.append(f"({ ' || '.join(check_parts) })")
                
                if sub_check_cmds:
                    verify_cmd = " && ".join(sub_check_cmds)
                    checklist.append({
                        "text": f"Verify subcomponent integration: ensure subcomponents {', '.join(sub_list)} are imported and referenced in the task files (run: `{verify_cmd}`)",
                        "completed": False
                    })
            # --- End Smart subcomponent integration check ---
            if not has_build_check:
                checklist.append({
                    "text": "Verify production build: run `npm run build` (or matching stack build command) and verify exit code 0 (no compile errors)",
                    "completed": False
                })
            if not has_dev_check:
                checklist.append({
                    "text": "Verify development server: run `npm run dev` (or matching stack run command) and verify server starts without console errors",
                    "completed": False
                })

        valid_tasks.append(task)

    # ── 7. Guarantee TASK-00 is the first element ──────────────
    task_00 = next((t for t in valid_tasks if t.get("task_id") == "TASK-00"), None)
    
    first_elements = []
    if task_00:
        first_elements.append(task_00)
        
    valid_tasks = first_elements + [t for t in valid_tasks if t.get("task_id") != "TASK-00"]

    logger.info(f"[{project_token}] ✅ Sprint-wise generation complete — {len(valid_tasks)} valid tasks")

    # ── 7b. POST-GENERATION VALIDATION ──────────────────────────
    issues = _validate_task_set_completeness(valid_tasks, project_token)
    if issues:
        logger.warning(f"[{project_token}] ⚠️ Task validation found {len(issues)} issues:")
        for issue in issues:
            logger.warning(f"[{project_token}]   → {issue}")

    # ── 7b2. BRD-TASK COVERAGE CROSS-REFERENCE ─────────────────
    # Check that all BRD requirements are covered by at least one task.
    # This catches LLM omissions where entire feature areas are missed.
    brd_raw = context.get("brd_analysis", "")
    if brd_raw and len(valid_tasks) > 3:
        try:
            coverage_issues = await _audit_brd_task_coverage(
                brd_content=str(brd_raw)[:20000],  # Truncate huge BRDs
                tasks=valid_tasks,
                project_token=project_token,
                api_url=api_url,
                api_key=api_key,
                model=model,
            )
            if coverage_issues:
                logger.warning(
                    f"[{project_token}] 🚨 BRD COVERAGE GAP: {len(coverage_issues)} requirement(s) not mapped to any task!"
                )
                for ci in coverage_issues:
                    logger.warning(f"[{project_token}]   ⚠️ UNCOVERED: {ci}")

                # ── AUTO-FILL: Generate tasks for uncovered requirements ──────
                logger.info(f"[{project_token}] 🔄 Auto-generating tasks for {len(coverage_issues)} uncovered requirements...")
                try:
                    fill_prompt = (
                        "You are generating additional tasks to fill gaps in a project plan.\n\n"
                        "The following BRD requirements were found to have NO corresponding task:\n"
                        + "\n".join(f"{i+1}. {req}" for i, req in enumerate(coverage_issues)) +
                        "\n\n"
                        "EXISTING TASKS (do NOT duplicate any of these):\n"
                        + _build_tasks_summary(valid_tasks) +
                        "\n\n"
                        "Generate ONE task per uncovered requirement. Each task must:\n"
                        "- Have a unique task_id (starting from TASK-GAP-01, TASK-GAP-02, ...)\n"
                        "- Include: taskName, description, task_type (\"FEATURE\"), priority, "
                        "task_wallet (3-5), sprint (infer from content), milestone, "
                        "linked_tasks, checklist (3-5 items), assignedTo: []\n"
                        "- linked_tasks must include \"TASK-00\" plus any relevant existing task IDs\n"
                        "- Description must explicitly reference the BRD requirement it fulfills\n"
                        "- Use the same repository structure as existing tasks for file paths\n"
                        "\nReturn ONLY a valid JSON array — no markdown, no preamble, no explanation."
                    )
                    fill_messages = [
                        {"role": "system", "content": "You are a precise task planner filling gaps in a project plan. Generate complete, actionable task objects."},
                        {"role": "user", "content": fill_prompt},
                    ]
                    fill_response = await llm_gateway.call_llm_and_extract(
                        messages=fill_messages,
                        api_url=api_url,
                        api_key=api_key,
                        model=model,
                        timeout=120.0,
                    )
                    fill_tasks = _parse_task_json(fill_response)
                    if fill_tasks:
                        # Validate each new task has required fields
                        validated_fill = []
                        for ft in fill_tasks:
                            ft.setdefault("task_type", "FEATURE")
                            ft.setdefault("priority", "medium")
                            ft.setdefault("task_wallet", 3)
                            ft.setdefault("assignedTo", [])
                            ft.setdefault("reported_by", "system")
                            ft.setdefault("checklist", [{"text": "Implement this feature", "completed": False}])
                            ft.setdefault("linked_tasks", ["TASK-00"])
                            ft["sprint"] = ft.get("sprint", "Sprint 1 - Frontend Proto & Bootstrap")
                            ft["milestone"] = ft.get("milestone", "Frontend Screens & Bootstrap Complete")
                            validated_fill.append(ft)

                        before = len(valid_tasks)
                        valid_tasks.extend(validated_fill)
                        # Renumber so gap tasks get proper sequential IDs
                        valid_tasks = _renumber_task_ids(valid_tasks, start_index=1)
                        added = len(valid_tasks) - before
                        logger.info(f"[{project_token}] ✅ Coverage auto-fill: added {added} new task(s)")
                    else:
                        logger.warning(f"[{project_token}] Coverage auto-fill returned 0 tasks — gaps remain")
                except Exception as fill_err:
                    logger.warning(f"[{project_token}] Coverage auto-fill failed (non-critical): {fill_err}")
                # ── END AUTO-FILL ─────────────────────────────────────────────
            else:
                logger.info(f"[{project_token}] ✅ BRD coverage audit: all requirements mapped to tasks")
        except Exception as cov_err:
            logger.warning(f"[{project_token}] BRD coverage audit skipped (non-critical): {cov_err}")
    # ═══ END BRD-TASK COVERAGE AUDIT ═══

    # ── 7c. QUALITY SCORING ────────────────────────────────────
    quality_stats = {"good": 0, "ok": 0, "poor": 0}
    for t in valid_tasks:
        tid = str(t.get("task_id", ""))
        result = _score_task_quality(t, tid)
        quality_stats[result["level"]] = quality_stats.get(result["level"], 0) + 1
        if result["level"] == "poor":
            logger.warning(
                f"[{project_token}] 🟡 LOW-QUALITY task {tid}: score={result['score']}/10 — "
                + "; ".join(result["warnings"])
            )
    if quality_stats["poor"] > 0:
        logger.warning(
            f"[{project_token}] 📊 Quality: {quality_stats['good']} good, "
            f"{quality_stats['ok']} ok, {quality_stats['poor']} poor"
        )

    for t in valid_tasks:
        logger.info(f"    {t['task_id']}: {t['taskName']} [{t.get('sprint', '?')}]")

    return valid_tasks


async def _audit_brd_task_coverage(
    brd_content: str,
    tasks: List[Dict[str, Any]],
    project_token: str = "",
    api_url: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
) -> List[str]:
    """
    Cross-reference the BRD/Action Plan against generated tasks to detect
    requirements that have NO corresponding task.  Returns a list of
    uncovered requirement descriptions (empty = full coverage).

    Uses a lightweight LLM call since this is a classification problem, not
    generation.
    """
    if not brd_content or not tasks:
        return []

    # Build a compact task summary: one line per task
    task_summaries: List[str] = []
    for t in tasks:
        tid = t.get("task_id", "?")
        title = t.get("taskName") or t.get("title", "Untitled")
        desc = (t.get("description") or "")[:120]
        sprint = t.get("sprint", "?")
        task_summaries.append(f"{tid}: [{sprint}] {title} — {desc}")

    task_block = "\n".join(task_summaries)

    system_prompt = (
        "You are a precise requirements analyst. "
        "Compare the BRD/Agent-Action-Plan to the task list and return "
        "ONLY requirements from the BRD that are NOT covered by ANY task. "
        "If every requirement is covered, return an empty JSON array: []. "
        "Each uncovered item should be a short string describing the missing requirement."
    )

    user_prompt = (
        f"BRD / AGENT ACTION PLAN (truncated):\n"
        f"{brd_content[:15000]}\n\n"
        f"GENERATED TASKS:\n"
        f"{task_block[:8000]}\n\n"
        f"List all BRD requirements that have NO corresponding task. "
        f"Return as JSON array of short strings. Return [] if fully covered."
    )

    import llm_gateway
    if not llm_gateway.check_api_key(api_key):
        logger.warning(f"[{project_token}] Skipping BRD coverage audit — no API key")
        return []

    try:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        response = await llm_gateway.call_llm_and_extract(
            messages=messages,
            api_url=api_url,
            api_key=api_key,
            model=model,
            timeout=60.0,
        )
        raw = (response or "").strip()
        # Strip markdown fences if present
        import re
        raw_clean = re.sub(r"```json\s*", "", raw, flags=re.IGNORECASE)
        raw_clean = re.sub(r"```\s*$", "", raw_clean, flags=re.IGNORECASE).strip()
        uncovered = json.loads(raw_clean)
        if isinstance(uncovered, list):
            return [str(item) for item in uncovered if item]
        return []
    except json.JSONDecodeError:
        logger.warning(f"[{project_token}] BRD coverage audit: LLM returned non-JSON: {str(response)[:200]}")
        return []
    except Exception as e:
        logger.warning(f"[{project_token}] BRD coverage audit failed: {e}")
        return []