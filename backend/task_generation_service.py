"""
Task Generation Service - Creates tasks locally before sending to NXDUNE
Uses Agent Action Plan to generate structured tasks with multiple sprints and milestones
"""
import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from models import Task, Document, GovernanceResponse
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
  1. **React Router v6 setup** in `src/App.tsx` with ALL application routes pre-registered
  2. **Shared Layout component** (`src/components/layout/AppLayout.tsx`) containing:
     - Persistent sidebar with navigation links to every major section
     - Top navigation bar with user avatar, notifications bell, and breadcrumbs
     - Main content area where page components are rendered via `<Outlet />`
  3. **Design token file** (`src/styles/tokens.css` or `src/theme/tokens.ts`) defining:
     - Primary, secondary, accent, surface, and text color variables
     - Typography scale (display, heading, body, caption font sizes)
     - Spacing scale, border radius, shadow levels
  4. **Global mock data store** (`src/mocks/mockData.ts`) with 5-10 realistic records per entity type, using domain-specific names, realistic values, and varied statuses
  5. **Shared UI components** (`src/components/ui/`) — Button, Badge, Card, Modal, Table, Sidebar, etc. — used consistently by all page components

Every subsequent Sprint 1 frontend task IMPORTS from these shared foundations. No task invents its own navigation, colors, or mock data structure.

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
  - "This agent owns: [exact file paths from section 0.5]"
  - "This agent must create: [list of specific files with full paths and their purpose]"
  - "This agent must NOT modify: [other folders/files]"
  - For Sprint 1 tasks: "This agent must IMPORT from: src/components/layout/AppLayout.tsx, src/mocks/mockData.ts, src/components/ui/"

**Example of GOOD Sprint 1 frontend task description (abbreviated):**
```
[SCREEN STORY]
The user arrives at the Projects Overview screen after clicking "Projects" in the sidebar.
They see a page header "All Projects" with a "+ New Project" button in the top right.
Below the header, a search input and status filter dropdown allow real-time filtering of the project list.
The main content is a data table with columns: Project Name, Status (color-coded badge), Owner, Due Date, Budget Utilization (progress bar), and Actions.
Clicking any row navigates to /projects/:id (Project Detail screen).
Clicking "+ New Project" opens a Drawer from the right with a 3-field form (Name, Description, Due Date). On submit, a success toast "Project created" appears, the drawer closes, and the new project is optimistically prepended to the table.

[SCREEN CONNECTIVITY]
- Sidebar "Projects" → current page (active state)
- Table row click → /projects/:id (Project Detail)
- "+ New Project" button → opens ProjectCreateDrawer (right-side drawer, no navigation)
- "View Report" action → /projects/:id/report (Project Report)
- Breadcrumb "Home" → /dashboard

[MOCK DATA SPECIFICATION]
Entity: Project — 8 records
Fields: id, name ("Apollo CRM Rebuild", "Nexus Dashboard v2", ...), status (Active/On Hold/Completed/At Risk), owner ("Sarah Chen", "Marcus Webb", ...), dueDate, budgetUsed (0-100), budgetTotal

[FILE OWNERSHIP]
This agent owns: src/pages/projects/ProjectsPage.tsx, src/pages/projects/ProjectDetailPage.tsx, src/components/projects/ProjectCreateDrawer.tsx, src/components/projects/ProjectTable.tsx
This agent must create:
  - src/pages/projects/ProjectsPage.tsx (main projects list screen)
  - src/pages/projects/ProjectDetailPage.tsx (individual project drill-down)
  - src/components/projects/ProjectCreateDrawer.tsx (new project right-side drawer)
  - src/components/projects/ProjectTable.tsx (data table with sort, filter, row actions)
This agent must IMPORT from: src/components/layout/AppLayout.tsx, src/mocks/mockData.ts, src/components/ui/
This agent must NOT modify: src/App.tsx, src/mocks/mockData.ts, src/components/layout/, src/styles/tokens.css, backend/
```

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
  - src/App.tsx (React Router route registry)
  - src/components/layout/AppLayout.tsx (persistent navigation shell)
  - src/styles/tokens.css OR src/theme/tokens.ts (design tokens)
  - src/mocks/mockData.ts (global mock data store)
  - src/components/ui/* (shared UI component kit)
  - backend/main.py (entry point skeleton)
No other task in any sprint may modify these files. They are read-only after TASK-00 completes.

### TASK-00 MANDATORY CONTENT (use this exact structure):

```json
{
  "task_id": "TASK-00",
  "taskName": "Project Bootstrap, Navigation Shell & Shared Frontend Foundation",
  "description": "GATEWAY TASK — All other tasks depend on this. Must complete before any other agent starts.\n\nThis task creates the entire shared foundation that every Sprint 1 frontend agent will import from. It does NOT build any feature screens — it builds the INFRASTRUCTURE that makes all screens possible.\n\n[WHAT THIS TASK BUILDS]\n1. Repository scaffold: all directories from the canonical structure, package.json, tsconfig, vite.config, tailwind.config, .env.example.\n2. React Router v6 setup in src/App.tsx: ALL application routes pre-registered with placeholder lazy-loaded components, wrapped in the AppLayout shell.\n3. AppLayout.tsx (src/components/layout/AppLayout.tsx): persistent left sidebar with navigation links to every major section, top navbar with app logo, user avatar dropdown, notifications bell, breadcrumb trail, and <Outlet /> for page content. Sidebar must be collapsible.\n4. Design token system (src/styles/tokens.css): CSS custom properties for — primary/secondary/accent colors, semantic colors (success, warning, error, info), surface/background layers, typography scale (display/heading/subheading/body/caption), spacing scale, border-radius levels, box-shadow levels. All Sprint 1 screens MUST use these tokens, never hardcoded values.\n5. Global mock data store (src/mocks/mockData.ts): exports typed arrays of 8–10 realistic mock records for EVERY entity type in the application. Use domain-appropriate names, IDs, dates, and statuses. This is the single source of truth for all Sprint 1 mock data.\n6. Shared UI component kit (src/components/ui/): Button (variants: primary, secondary, ghost, danger), Badge (color variants by status), Card, Modal, Drawer (right-side slide-in panel), DataTable (sortable, with row-click handler prop), SearchInput, Toast/notification system, LoadingSkeleton, EmptyState, PageHeader (title + subtitle + action slot).\n7. Backend entry point ONLY: backend/main.py with FastAPI app instantiation, CORS middleware, and a /health endpoint. NO database, NO models, NO business logic.\n\n[WHAT THIS TASK MUST NOT BUILD]\n- No feature screens (those are built by subsequent Sprint 1 tasks)\n- No backend database schemas, models, or API routes (Sprint 2)\n- No third-party API integrations (Sprint 2)\n\nThis agent owns: src/App.tsx, src/components/layout/, src/components/ui/, src/styles/, src/mocks/, src/theme/, backend/main.py, all config files (package.json, vite.config.ts, tailwind.config.ts, tsconfig.json)\nThis agent must NOT modify: src/pages/ (owned by individual Sprint 1 screen tasks)\nAll subsequent tasks MUST wait for this task to complete before starting.",
  "task_type": "TASK",
  "priority": "high",
  "task_wallet": 8,
  "sprint": "<Sprint 1 name from AVAILABLE SPRINTS>",
  "milestone": "Navigation Shell & Design System",
  "assignedTo": [],
  "linked_tasks": [],
  "reported_by": "system",
  "checklist": [
    { "text": "Scaffold full repository structure: all directories, package.json, tsconfig, vite.config, tailwind.config, .env.example, README", "completed": false },
    { "text": "Build AppLayout.tsx with collapsible sidebar (all nav links), top navbar (logo, user avatar, notifications, breadcrumbs), and <Outlet /> content slot. Register all routes in src/App.tsx with React Router v6.", "completed": false },
    { "text": "Create design token file with complete color palette (primary, accent, semantic), typography scale, spacing scale, border radius, and shadow levels. Verify tokens render correctly in browser.", "completed": false },
    { "text": "Populate src/mocks/mockData.ts with 8–10 realistic typed records for every entity type in the application. Verify all exported arrays are importable and TypeScript-typed.", "completed": false },
    { "text": "Build shared UI component kit: Button (all variants), Badge, Card, Modal, Drawer, DataTable, SearchInput, Toast system, LoadingSkeleton, EmptyState, PageHeader. Verify each component renders with mock props.", "completed": false }
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
   - Reference exact folders/modules from the repository structure (section 0.5.1 of the Agent Action Plan)
   - Sprint 1 agents: src/ paths only. Sprint 2 agents: backend/ paths only.

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


def _generate_sprints_and_milestones(
    project_start: datetime,
    project_deadline: datetime,
    num_phases: int = 4
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Generate multiple sprints and milestones based on project timeline"""
    
    sprints = []
    milestones = []
    
    total_days = (project_deadline - project_start).days
    sprint_duration = max(total_days // num_phases, 7)  # At least 7 days per sprint
    
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
        logger.error(f"Failed to parse task JSON: {e}")
        logger.error(f"Content: {content[:500]}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error parsing task JSON: {e}")
        return []


def _validate_task_structure(task: Dict[str, Any]) -> bool:
    """Validate that task has required fields"""
    
    critical_fields = ["task_id", "taskName", "task_type", "description"]
    for field in critical_fields:
        if field not in task or not task[field]:
            logger.warning(f"Task missing critical field: {field}")
            return False
    
    valid_types = ["EPIC", "FEATURE", "STORY", "TASK", "BUG"]
    if task.get("task_type") not in valid_types:
        logger.warning(f"Invalid task_type: {task.get('task_type')}")
        return False
    
    # Auto-fix task_wallet if missing
    wallet = task.get("task_wallet", None)
    if wallet is None:
        task_type = task.get("task_type", "TASK")
        defaults = {"EPIC": 9, "FEATURE": 5, "STORY": 3, "TASK": 1, "BUG": 2}
        task["task_wallet"] = defaults.get(task_type, 1)
        logger.info(f"Auto-fixed missing task_wallet → {task['task_wallet']} for {task.get('task_id')}")
    
    return True


def _generate_bootstrap_checklist(repo_structure: str, project_name: str) -> List[Dict[str, Any]]:
    """Generate detailed checklist items from repository structure for TASK-00"""
    
    checklist = []
    
    # Parse the repository structure to extract directories and files
    import re
    
    # Extract all directory paths (lines ending with /)
    dir_pattern = r'[\s│├└─`|]*([a-zA-Z0-9_\-./]+/)[\s]*$'
    # Extract all file paths (lines with file extensions or specific files)
    file_pattern = r'[\s│├└─`|]*([a-zA-Z0-9_\-./]+\.[a-zA-Z0-9]+)[\s]*$'
    
    directories = []
    files = []
    
    for line in repo_structure.split('\n'):
        # Skip empty lines and root project line
        if not line.strip() or line.strip() == project_name or line.strip().endswith(project_name + '/'):
            continue
        
        # Check for directory
        dir_match = re.search(dir_pattern, line)
        if dir_match:
            dir_path = dir_match.group(1).strip()
            if dir_path and dir_path not in directories:
                directories.append(dir_path)
        
        # Check for file
        file_match = re.search(file_pattern, line)
        if file_match:
            file_path = file_match.group(1).strip()
            if file_path and file_path not in files:
                files.append(file_path)
    
    # Add checklist items
    checklist.append({
        "text": f"Create root project directory: mkdir -p {project_name}",
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
            dirs_str = ' '.join([f"{project_name}/{d.rstrip('/')}" for d in main_dirs[:5]])
            checklist.append({
                "text": f"Create main directory structure: mkdir -p {dirs_str}",
                "completed": False
            })
        
        # Create subdirectories
        sub_dirs = [d for d in directories if d.count('/') > 2]
        if sub_dirs:
            for i in range(0, min(len(sub_dirs), 10), 3):
                batch = sub_dirs[i:i+3]
                dirs_str = ' '.join([f"{project_name}/{d.rstrip('/')}" for d in batch])
                checklist.append({
                    "text": f"Create subdirectories: mkdir -p {dirs_str}",
                    "completed": False
                })
    
    # Add file creation items
    if files:
        # Group files by type
        config_files = [f for f in files if any(x in f.lower() for x in ['.env', '.json', '.yml', '.yaml', '.toml', '.ini', '.config'])]
        json_files = [f for f in files if f.endswith('.json')]
        code_files = [f for f in files if any(f.endswith(ext) for ext in ['.py', '.js', '.ts', '.jsx', '.tsx'])]
        doc_files = [f for f in files if any(f.endswith(ext) for ext in ['.md', '.txt', '.rst'])]
        
        if config_files:
            for config_file in config_files[:5]:
                checklist.append({
                    "text": f"Create config file: touch {project_name}/{config_file}",
                    "completed": False
                })
        
        # NEW: Add JSON validation step
        if json_files:
            json_paths = ' '.join([f'{project_name}/{f}' for f in json_files[:10]])
            checklist.append({
                "text": f"Validate JSON syntax for all JSON files: for f in {json_paths}; do python3 -m json.tool \"$f\" > /dev/null || echo \"Invalid JSON: $f\"; done",
                "completed": False
            })
        
        if doc_files:
            checklist.append({
                "text": f"Create documentation files: touch {' '.join([f'{project_name}/{f}' for f in doc_files[:3]])}",
                "completed": False
            })
        
        if code_files:
            checklist.append({
                "text": f"Create placeholder code files: touch {' '.join([f'{project_name}/{f}' for f in code_files[:5]])}",
                "completed": False
            })
    
    # Add .gitignore
    checklist.append({
        "text": f"Create .gitignore with appropriate rules for the tech stack",
        "completed": False
    })
    
    # Add README
    checklist.append({
        "text": f"Create README.md with project overview and setup instructions",
        "completed": False
    })
    
    # Add verification step
    checklist.append({
        "text": f"Verify all directories and files exist: ls -R {project_name} | wc -l (should show more than 10 items)",
        "completed": False
    })
    
    checklist.append({
        "text": "Commit initial structure: git add . && git commit -m 'Initial project structure'",
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
    
    # Get governance response
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
    
    # Get document analysis for this specific project
    # First try to find a document that has this project_token in its analysis_result
    token_pattern = f'%"project_token": "{project_token}"%'
    document = db.query(Document).filter(
        Document.owner_id == user_id,
        Document.analysis_result.isnot(None),
        Document.analysis_result.like(token_pattern)
    ).order_by(Document.upload_date.desc()).first()
    
    # Fallback to latest document if no project-specific document found
    if not document:
        logger.warning(f"No document found with project_token {project_token}, using latest document")
        document = db.query(Document).filter(
            Document.owner_id == user_id,
            Document.analysis_result.isnot(None)
        ).order_by(Document.upload_date.desc()).first()
    
    if document and document.analysis_result:
        try:
            analysis = json.loads(document.analysis_result)
            raw_analysis = analysis.get("analysis", "")
            if not raw_analysis and isinstance(analysis, str):
                raw_analysis = analysis
            
            context["brd_analysis"] = raw_analysis
            
            # Extract repository structure from section 0.5.1
            context["repository_structure"] = _extract_repository_structure(raw_analysis)
            
            if "project_type" in analysis:
                context["project_type"] = analysis["project_type"]
        except Exception as e:
            logger.warning(f"Failed to parse document analysis: {e}")
    
    return context


# ─────────────────────────────────────────────────────────────────────────────
# SPRINT-SPECIFIC GENERATION PROMPTS
# Each sprint gets its own focused prompt so the LLM output stays small,
# never hits max_tokens, and never produces truncated JSON.
# ─────────────────────────────────────────────────────────────────────────────

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
    if project_type:
        context["project_type"] = project_type

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

    # ── 4. Shared BRD context block (injected into every sprint call) ──────────
    brd_block = f"""
AVAILABLE SPRINTS (with dates):
================================
{sprint_list}

AVAILABLE MILESTONES:
=====================
{milestone_list}

REPOSITORY STRUCTURE (from section 0.5.1):
==========================================
{context.get('repository_structure', 'Not available')}

CURRENT DATE: {today.strftime('%Y-%m-%d')}
PROJECT DEADLINE: {project_deadline.strftime('%Y-%m-%d')}

===================================================================
AGENT ACTION PLAN MARKDOWN DOCUMENT
===================================================================
{context['brd_analysis'] if context['brd_analysis'] else 'No Agent Action Plan available'}
===================================================================
"""

    # ── 5. PHASED GENERATION — one LLM call per sprint ────────────────────────
    all_tasks: List[Dict[str, Any]] = []

    # ── Phase 1: Sprint 1 (TASK-00 + frontend screens) ────────────────────────
    logger.info(f"[{project_token}] Phase 1/4 — Sprint 1 (bootstrap + frontend prototype)")
    sprint1_tasks = await _generate_sprint_phase(
        sprint_number=1,
        sprint_prompt_template=SPRINT1_GENERATION_PROMPT,
        prompt_context=brd_block,
        api_url=api_url,
        api_key=api_key,
        model=model,
        project_token=project_token,
    )
    # Renumber starting at 0 (TASK-00 stays TASK-00)
    sprint1_tasks = _renumber_task_ids(sprint1_tasks, start_index=1)
    # Sprint 1 tasks get sprint[0] as default
    for t in sprint1_tasks:
        t.setdefault("sprint",     sprints[0]["name"])
        t.setdefault("milestone",  milestones[0]["name"])
    all_tasks.extend(sprint1_tasks)

    next_index = max(
        (int(t["task_id"].replace("TASK-", "")) for t in sprint1_tasks if t.get("task_id", "").startswith("TASK-") and t["task_id"] != "TASK-00"),
        default=0
    ) + 1

    # ── Phase 2: Sprint 2 (backend services) ──────────────────────────────────
    sprint1_summary = _build_tasks_summary(sprint1_tasks)
    logger.info(f"[{project_token}] Phase 2/4 — Sprint 2 (backend services) — next task index: TASK-{next_index:02d}")
    sprint2_prompt = SPRINT2_GENERATION_PROMPT.replace(
        "{start_index}", f"{next_index:02d}"
    ).replace(
        "{sprint1_summary}", sprint1_summary
    )
    sprint2_tasks = await _generate_sprint_phase(
        sprint_number=2,
        sprint_prompt_template=sprint2_prompt,
        prompt_context=brd_block,
        api_url=api_url,
        api_key=api_key,
        model=model,
        project_token=project_token,
    )
    sprint2_tasks = _renumber_task_ids(sprint2_tasks, start_index=next_index)
    for t in sprint2_tasks:
        t.setdefault("sprint",    sprints[1]["name"])
        t.setdefault("milestone", milestones[1]["name"])
        # Guarantee TASK-00 is always in linked_tasks
        if "TASK-00" not in t.get("linked_tasks", []):
            t.setdefault("linked_tasks", []).insert(0, "TASK-00")
    all_tasks.extend(sprint2_tasks)

    next_index = max(
        (int(t["task_id"].replace("TASK-", "")) for t in sprint2_tasks if t.get("task_id", "").startswith("TASK-") and t["task_id"] != "TASK-00"),
        default=next_index - 1
    ) + 1

    # ── Phase 3: Sprint 3 (integration) ───────────────────────────────────────
    sprint2_summary = _build_tasks_summary(sprint2_tasks)
    logger.info(f"[{project_token}] Phase 3/4 — Sprint 3 (integration) — next task index: TASK-{next_index:02d}")
    sprint3_prompt = SPRINT3_GENERATION_PROMPT.replace(
        "{start_index}", f"{next_index:02d}"
    ).replace(
        "{sprint1_summary}", sprint1_summary
    ).replace(
        "{sprint2_summary}", sprint2_summary
    )
    sprint3_tasks = await _generate_sprint_phase(
        sprint_number=3,
        sprint_prompt_template=sprint3_prompt,
        prompt_context=brd_block,
        api_url=api_url,
        api_key=api_key,
        model=model,
        project_token=project_token,
    )
    sprint3_tasks = _renumber_task_ids(sprint3_tasks, start_index=next_index)
    for t in sprint3_tasks:
        t.setdefault("sprint",    sprints[2]["name"])
        t.setdefault("milestone", milestones[2]["name"])
        if "TASK-00" not in t.get("linked_tasks", []):
            t.setdefault("linked_tasks", []).insert(0, "TASK-00")
    all_tasks.extend(sprint3_tasks)

    next_index = max(
        (int(t["task_id"].replace("TASK-", "")) for t in sprint3_tasks if t.get("task_id", "").startswith("TASK-") and t["task_id"] != "TASK-00"),
        default=next_index - 1
    ) + 1

    # ── Phase 4: Sprint 4 (testing & deployment) ──────────────────────────────
    all_previous_summary = _build_tasks_summary(sprint1_tasks + sprint2_tasks + sprint3_tasks)
    logger.info(f"[{project_token}] Phase 4/4 — Sprint 4 (testing & deployment) — next task index: TASK-{next_index:02d}")
    sprint4_prompt = SPRINT4_GENERATION_PROMPT.replace(
        "{start_index}", f"{next_index:02d}"
    ).replace(
        "{all_previous_summary}", all_previous_summary
    )
    sprint4_tasks = await _generate_sprint_phase(
        sprint_number=4,
        sprint_prompt_template=sprint4_prompt,
        prompt_context=brd_block,
        api_url=api_url,
        api_key=api_key,
        model=model,
        project_token=project_token,
    )
    sprint4_tasks = _renumber_task_ids(sprint4_tasks, start_index=next_index)
    for t in sprint4_tasks:
        t.setdefault("sprint",    sprints[3]["name"])
        t.setdefault("milestone", milestones[3]["name"])
        if "TASK-00" not in t.get("linked_tasks", []):
            t.setdefault("linked_tasks", []).insert(0, "TASK-00")
    all_tasks.extend(sprint4_tasks)

    logger.info(f"[{project_token}] All phases complete — {len(all_tasks)} total tasks before validation")

    if not all_tasks:
        logger.error("No tasks generated across any sprint phase")
        return []

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

        valid_tasks.append(task)

    # ── 7. Guarantee TASK-00 is the first element ──────────────────────────────
    task_00 = next((t for t in valid_tasks if t.get("task_id") == "TASK-00"), None)
    if task_00:
        valid_tasks = [task_00] + [t for t in valid_tasks if t.get("task_id") != "TASK-00"]

    logger.info(f"[{project_token}] ✅ Sprint-wise generation complete — {len(valid_tasks)} valid tasks")
    for t in valid_tasks:
        logger.info(f"    {t['task_id']}: {t['taskName']} [{t.get('sprint', '?')}]")

    return valid_tasks