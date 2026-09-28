import React, { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import { Users, Trash2, Edit, Activity, Clock, CheckCircle, AlertCircle, RefreshCw, Filter, Server, Database, GitBranch, Bot, Globe, Plus, Upload, Code, Coffee, Zap, Triangle, Hash, Link2, Terminal, Cpu, Workflow, Shield, ShieldCheck, Layers, Building2, Send, ChevronRight, ChevronDown, TrendingUp, PlusCircle, Wrench, Check, Sparkles, X } from 'lucide-react';
import { API_ENDPOINTS } from '../config';
import RequestCapacityModal from './RequestCapacityModal';

import { getNeutralAgentName, getNeutralAgentLabel } from '../utils/agentNames';
import kaktoxLogo from '../assets/Kaktox.png';
import nModLogo from '../assets/N-Mod-icon.png';
import masterLogo from '../assets/logo1.png';
import cloudIcon from '../assets/cloud-icon.png';

export const DEFAULT_TOOLS_CATALOG = [
  {
    id: 'filesystem',
    name: 'File System & Code Editor',
    category: 'Core Development',
    description: 'Read, write, edit, and search source code files across the workspace.',
    icon: 'FolderCode',
    default: true,
    capabilities: ['read_file', 'write_file', 'edit_file', 'list_dir', 'search_files']
  },
  {
    id: 'git',
    name: 'Git & Version Control',
    category: 'Core Development',
    description: 'Branching, staging, committing, inspecting diffs, and syncing code with git.',
    icon: 'GitBranch',
    default: true,
    capabilities: ['git_status', 'git_commit', 'git_diff', 'git_branch', 'git_checkout']
  },
  {
    id: 'terminal',
    name: 'Terminal & Shell Execution',
    category: 'Execution',
    description: 'Execute bash commands and manage processes in the isolated Linux Docker container.',
    icon: 'Terminal',
    default: true,
    capabilities: ['execute_bash', 'kill_process', 'get_process_status']
  },
  {
    id: 'build_tool',
    name: 'Build & Dependency Manager',
    category: 'Execution',
    description: 'Run npm, pip, maven, gradle builds, compile code, and verify dependency health.',
    icon: 'Package',
    default: true,
    capabilities: ['npm_build', 'pip_install', 'dependency_check', 'verify_compilation']
  },
  {
    id: 'test_runner',
    name: 'Testing & QA Suite',
    category: 'Verification',
    description: 'Execute Pytest unit tests, Jest specs, Playwright browser flows, and test assertions.',
    icon: 'CheckSquare',
    default: false,
    capabilities: ['run_pytest', 'run_jest', 'e2e_playwright', 'assert_status']
  },
  {
    id: 'web_search',
    name: 'Web Search & Documentation',
    category: 'Research',
    description: 'Search developer documentation, API references, library examples, and debug runtime errors.',
    icon: 'Search',
    default: false,
    capabilities: ['search_docs', 'fetch_webpage', 'lookup_api_reference']
  },
  {
    id: 'visual_qa',
    name: 'Visual QA & Live Inspector',
    category: 'Verification',
    description: 'Capture screenshots of preview running on port 80, inspect browser console logs, and verify DOM.',
    icon: 'Eye',
    default: false,
    capabilities: ['capture_screenshot', 'inspect_console', 'dom_query']
  },
  {
    id: 'database_tools',
    name: 'Database & Migration Inspector',
    category: 'Data',
    description: 'Inspect SQL schemas, run database migrations, verify seed data integrity.',
    icon: 'Database',
    default: false,
    capabilities: ['inspect_schema', 'run_migration', 'verify_seeds']
  }
];

export const getToolIcon = (iconName, className = 'w-3 h-3') => {
  switch (iconName) {
    case 'FolderCode': return <Code className={`${className} text-emerald-400`} />;
    case 'GitBranch': return <GitBranch className={`${className} text-cyan-400`} />;
    case 'Terminal': return <Terminal className={`${className} text-amber-400`} />;
    case 'Package': return <Layers className={`${className} text-indigo-400`} />;
    case 'CheckSquare': return <CheckCircle className={`${className} text-purple-400`} />;
    case 'Search': return <Globe className={`${className} text-sky-400`} />;
    case 'Eye': return <Activity className={`${className} text-pink-400`} />;
    case 'Database': return <Database className={`${className} text-emerald-400`} />;
    case 'Workflow': return <Workflow className={`${className} text-blue-400`} />;
    case 'Github': return <GitBranch className={`${className} text-slate-400`} />;
    default: return <Wrench className={`${className} text-app-primary`} />;
  }
};

export const CAPABILITY_LABELS = {
  read_file: 'Read Files',
  write_file: 'Write Files',
  edit_file: 'Edit Code',
  list_dir: 'List Directory',
  search_files: 'Search Files',
  git_status: 'Git Status',
  git_commit: 'Commit Changes',
  git_diff: 'Inspect Diffs',
  git_branch: 'Branch Management',
  git_checkout: 'Switch Branches',
  execute_bash: 'Bash Terminal',
  kill_process: 'Process Control',
  get_process_status: 'Process Monitor',
  npm_build: 'NPM / Vite Build',
  pip_install: 'Pip Packages',
  dependency_check: 'Dependency Audit',
  verify_compilation: 'Compile Validation',
  run_pytest: 'Pytest Suite',
  run_jest: 'Jest / Vitest',
  e2e_playwright: 'Playwright E2E',
  assert_status: 'HTTP Assertions',
  search_docs: 'Search Docs',
  fetch_webpage: 'Fetch Webpage',
  lookup_api_reference: 'API References',
  capture_screenshot: 'UI Screenshots',
  inspect_console: 'Console Logs',
  dom_query: 'DOM Inspector',
  inspect_schema: 'Schema Inspector',
  run_migration: 'Database Migration',
  verify_seeds: 'Seed Verification',
};

export const formatCapability = (cap) => {
  if (!cap) return '';
  const key = String(cap).trim().toLowerCase();
  if (CAPABILITY_LABELS[key]) return CAPABILITY_LABELS[key];
  return cap
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
};

export const sanitizeModelName = (name, id) => {
  const norm = `${id || ''} ${name || ''}`.toLowerCase();
  if (norm.includes('claude')) return 'Claude';
  if (norm.includes('deepseek')) return 'DeepSeek';
  if (norm.includes('kimi')) return 'Kimi';
  return name || 'Claude';
};

export const DEFAULT_MODELS_CATALOG = [
  {
    id: 'claude',
    name: 'Claude',
    provider: 'Anthropic',
    description: 'Flagship reasoning, fullstack architecture, multi-file code editing, and tool calling.',
    color: 'amber'
  },
  {
    id: 'deepseek',
    name: 'DeepSeek',
    provider: 'DeepSeek AI',
    description: 'Deep mathematical logic, test generation, QA verification, algorithmic optimizations.',
    color: 'emerald'
  },
  {
    id: 'kimi',
    name: 'Kimi',
    provider: 'Moonshot AI',
    description: 'Ultra-fast streaming response, long context retention, API schema and docs alignment.',
    color: 'sky'
  }
];

export const getModelBadge = (modelId = 'claude') => {
  const norm = (modelId || 'claude').toLowerCase();
  if (norm.includes('deepseek')) {
    return {
      label: 'DeepSeek',
      pillClass: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30',
      dotClass: 'bg-emerald-400'
    };
  }
  if (norm.includes('kimi')) {
    return {
      label: 'Kimi',
      pillClass: 'bg-sky-500/10 text-sky-400 border-sky-500/30',
      dotClass: 'bg-sky-400'
    };
  }
  return {
    label: 'Claude',
    pillClass: 'bg-amber-500/10 text-amber-400 border-amber-500/30',
    dotClass: 'bg-amber-400'
  };
};

const PREDEFINED_TEMPLATES = [
  {
    name: 'Frontend Developer',
    tags: 'React, Vite, CSS Modules, Tailwind CSS, Lucide Icons, UI Components',
    specialization: 'Development',
    defaultModel: 'claude',
    defaultTools: ['filesystem', 'build_tool', 'visual_qa', 'web_search'],
    description: 'Specialized React & Vite agent. Connects page routing, implements responsive UI layouts, and styles elements using CSS tokens.',
    skills: `# Frontend Developer Agent Skill\n\n## Role\nYou are a specialized Frontend Development Agent focused on building React applications with modern tooling (Vite, React) and styling (Tailwind CSS/CSS Modules).\n\n## Tech Stack\n- Framework: React\n- Build Tool: Vite\n- Styling: Tailwind CSS & CSS Modules\n- UI Components: Lucide React (icons)\n- State Management: React Context / Hooks\n\n## Core Responsibilities\n1. Component Development: Create modular, responsive React components using hooks.\n2. Routing: Register pages/components in the main routing shell (App.jsx).\n3. API Connection: Replace mock data with real API calls using fetch or axios.\n4. Layout & Styling: Maintain consistent layout systems, sidebar navigation, and use CSS variable tokens.`,
    icon: Globe,
    accentColor: 'from-emerald-400 to-teal-500',
    colorClass: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20 hover:border-emerald-500/40 hover:text-emerald-300'
  },
  {
    name: 'Backend Developer',
    tags: 'FastAPI, Python, SQL Databases, SQLite, PostgreSQL, REST API',
    specialization: 'Development',
    defaultModel: 'claude',
    defaultTools: ['filesystem', 'git', 'terminal', 'build_tool', 'database_tools'],
    description: 'Specialized FastAPI & Python agent. Sets up REST routes, SQLAlchemy models, migration scripts, and business validation.',
    skills: `# Backend Developer Agent Skill\n\n## Role\nYou are a specialized Backend Development Agent focused on building Python APIs with FastAPI, SQLAlchemy, databases, and clean routing.\n\n## Tech Stack\n- Language: Python\n- Framework: FastAPI\n- ORM: SQLAlchemy / SQLModel\n- Database: SQLite / PostgreSQL\n- API Protocol: REST / JSON\n\n## Core Responsibilities\n1. API Routing: Create clear, versioned FastAPI APIRouter endpoints.\n2. Database Schema: Implement SQLAlchemy models, migrations, and Pydantic schemas.\n3. Business Logic: Write modular services for data processing, validation, and auth.\n4. Security: Implement CORS, password hashing, and token-based auth (JWT).`,
    icon: Server,
    accentColor: 'from-blue-400 to-indigo-500',
    colorClass: 'text-blue-400 bg-blue-500/10 border-blue-500/20 hover:border-blue-500/40 hover:text-blue-300'
  },
  {
    name: 'QA & Testing Specialist',
    tags: 'Testing, Pytest, Playwright, E2E Testing, Integration Testing, Assertions',
    specialization: 'Testing',
    defaultModel: 'deepseek',
    defaultTools: ['terminal', 'test_runner', 'visual_qa', 'filesystem'],
    description: 'Specialized Pytest & Playwright agent. Creates unit/integration test suites and browser automation to verify features.',
    skills: `# QA & Testing Specialist Agent Skill\n\n## Role\nYou are a specialized Quality Assurance and Testing Agent focused on verifying features, running backend unit tests, and executing E2E frontend flows.\n\n## Tech Stack\n- Backend Testing: Pytest, unittest\n- Frontend E2E: Playwright / Cypress\n- Assertions: standard assertions, status code checks\n- Mocking: unittest.mock, patch\n\n## Core Responsibilities\n1. Unit Tests: Create test cases in tests/ directory validating API responses, database operations, and edge cases.\n2. E2E Tests: Write automated browser scripts to simulate user login, navigation, and form submissions.\n3. Verification: Assert status codes, content fields, and UI element presence on successful/error execution.`,
    icon: Activity,
    accentColor: 'from-purple-400 to-pink-500',
    colorClass: 'text-purple-400 bg-purple-500/10 border-purple-500/20 hover:border-purple-500/40 hover:text-purple-300'
  },
  // ── Brownfield / Language-Specific Templates ────────────────────────────────
  {
    name: 'Java / Spring Boot Developer',
    tags: 'Java, Spring Boot, Maven, Hibernate, JPA, REST API, Gradle',
    specialization: 'Development',
    brownfieldOnly: true,
    defaultModel: 'claude',
    defaultTools: ['filesystem', 'git', 'terminal', 'build_tool', 'database_tools'],
    description: 'Brownfield Java agent. Reads existing Spring Boot services, applies targeted modifications, adds endpoints, entities, and service logic without breaking existing code.',
    skills: `# Java / Spring Boot Developer Agent Skill\n\n## Role\nYou are a specialized Brownfield Java Developer Agent. You work on EXISTING Spring Boot applications — reading current code before making any changes.\n\n## Tech Stack\n- Language: Java 11/17/21\n- Framework: Spring Boot (Spring MVC, Spring Data, Spring Security)\n- Build: Maven / Gradle\n- ORM: Hibernate / JPA / Spring Data JPA\n- Testing: JUnit 5, Mockito\n- DB: PostgreSQL / MySQL / H2\n\n## Brownfield Working Rules\n1. ALWAYS read the existing class before modifying: cat /workspace/src/main/java/.../ClassName.java\n2. Make SURGICAL changes — preserve existing methods, annotations, and imports\n3. Add new endpoints in existing Controllers or create new @RestController classes\n4. New entities go in the existing entities/ or model/ package structure\n5. Register new beans, services, or repositories following the existing patterns\n6. Run: mvn test -pl . --no-transfer-progress (or ./gradlew test) after changes\n\n## Core Responsibilities\n1. Endpoint Development: Add/modify @GetMapping, @PostMapping in @RestController classes\n2. Service Layer: Add business logic in @Service classes, injecting existing repositories\n3. Entity Changes: Modify @Entity JPA classes, add @Column fields with proper constraints\n4. Repository: Add custom @Query methods to existing JpaRepository interfaces\n5. Configuration: Modify application.properties / application.yml for new settings`,
    icon: Coffee,
    accentColor: 'from-orange-400 to-red-500',
    colorClass: 'text-orange-400 bg-orange-500/10 border-orange-500/20 hover:border-orange-500/40 hover:text-orange-300'
  },
  {
    name: '.NET / C# Developer',
    tags: 'C#, .NET, ASP.NET Core, Entity Framework, NuGet, REST API',
    specialization: 'Development',
    brownfieldOnly: true,
    defaultModel: 'claude',
    defaultTools: ['filesystem', 'git', 'terminal', 'build_tool', 'database_tools'],
    description: 'Brownfield .NET agent. Reads existing ASP.NET Core controllers, applies targeted modifications, adds endpoints, EF migrations, and service logic.',
    skills: `# .NET / C# Developer Agent Skill\n\n## Role\nYou are a specialized Brownfield .NET Developer Agent. You work on EXISTING ASP.NET Core applications — reading current code before making any changes.\n\n## Tech Stack\n- Language: C# (.NET 6/7/8)\n- Framework: ASP.NET Core (Web API, Minimal APIs)\n- ORM: Entity Framework Core\n- Package Manager: NuGet\n- Testing: xUnit, Moq\n- DB: SQL Server / PostgreSQL / SQLite\n\n## Brownfield Working Rules\n1. ALWAYS read the existing file: cat /workspace/src/.../ClassName.cs\n2. Preserve existing namespaces, using directives, and dependency injection registrations\n3. Add new action methods to existing Controllers or create new ControllerBase-derived classes\n4. New entities go in the existing Models/ or Entities/ directory\n5. Register new services in Program.cs / Startup.cs following the existing pattern\n6. Run: dotnet test after changes\n\n## Core Responsibilities\n1. API Controllers: Add [HttpGet]/[HttpPost] actions to [ApiController] classes\n2. Service Layer: Add methods to existing interface + implementation pairs\n3. EF Migrations: Modify DbContext and generate new Add-Migration / dotnet ef migration\n4. Models/DTOs: Add new properties to existing record or class definitions\n5. Middleware: Wire new middleware in the existing app.Use() pipeline`,
    icon: Hash,
    accentColor: 'from-violet-400 to-purple-500',
    colorClass: 'text-violet-400 bg-violet-500/10 border-violet-500/20 hover:border-violet-500/40 hover:text-violet-300'
  },
  {
    name: 'Python / Django Developer',
    tags: 'Python, Django, DRF, Celery, PostgreSQL, REST API, Migrations',
    specialization: 'Development',
    brownfieldOnly: true,
    defaultModel: 'claude',
    defaultTools: ['filesystem', 'git', 'terminal', 'build_tool', 'database_tools'],
    description: 'Brownfield Django agent. Reads existing views, models, and URLs then applies targeted changes to add features, API endpoints, and celery tasks.',
    skills: `# Python / Django Developer Agent Skill\n\n## Role\nYou are a specialized Brownfield Python/Django Developer Agent. You work on EXISTING Django applications — reading current code before making any changes.\n\n## Tech Stack\n- Language: Python 3.9+\n- Framework: Django + Django REST Framework (DRF)\n- Task Queue: Celery + Redis\n- ORM: Django ORM\n- Testing: pytest-django, unittest\n- DB: PostgreSQL / SQLite\n\n## Brownfield Working Rules\n1. ALWAYS read the existing file: cat /workspace/app_name/views.py (or models.py, urls.py)\n2. Preserve existing URL patterns — add new patterns without removing existing ones\n3. Add new serializers in the existing serializers.py file\n4. New models go in the existing models.py of the appropriate Django app\n5. Generate and apply migrations: python manage.py makemigrations && python manage.py migrate\n6. Run tests: python manage.py test\n\n## Core Responsibilities\n1. Views/Viewsets: Add new APIView or ModelViewSet classes in existing views.py\n2. Models: Add fields or new Model classes with proper Meta and migrations\n3. Serializers: Add DRF serializers for new or modified models\n4. URL Routing: Register new routes in urls.py with router.register() or urlpatterns\n5. Celery Tasks: Add @shared_task decorated functions to existing tasks.py`,
    icon: Code,
    accentColor: 'from-green-400 to-emerald-500',
    colorClass: 'text-green-400 bg-green-500/10 border-green-500/20 hover:border-green-500/40 hover:text-green-300'
  },
  {
    name: 'Node.js / Express Developer',
    tags: 'Node.js, Express, TypeScript, Prisma, REST API, npm, MongoDB',
    specialization: 'Development',
    brownfieldOnly: true,
    defaultModel: 'claude',
    defaultTools: ['filesystem', 'git', 'terminal', 'build_tool', 'database_tools'],
    description: 'Brownfield Node.js agent. Reads existing Express routes and middleware, then adds endpoints, schema changes, and service logic with minimal disruption.',
    skills: `# Node.js / Express Developer Agent Skill\n\n## Role\nYou are a specialized Brownfield Node.js/Express Developer Agent. You work on EXISTING Node.js applications — reading current code before making any changes.\n\n## Tech Stack\n- Language: TypeScript / JavaScript\n- Framework: Express / NestJS / Fastify\n- ORM: Prisma / TypeORM / Mongoose\n- Package Manager: npm / yarn / pnpm\n- Testing: Jest, Supertest\n- DB: PostgreSQL / MongoDB / MySQL\n\n## Brownfield Working Rules\n1. ALWAYS read the existing file: cat /workspace/src/routes/existingRouter.ts\n2. Add new route handlers to existing Express Router files or create new modular routers\n3. Register new routers in the existing app.use() configuration in app.ts/index.ts\n4. New Prisma models: add to schema.prisma then run npx prisma migrate dev\n5. Keep existing middleware chain intact — add middleware AFTER existing ones\n6. Run: npm test after changes\n\n## Core Responsibilities\n1. Routes: Add new GET/POST/PUT/DELETE handlers in existing router files\n2. Controllers: Add new controller functions following the existing request/response pattern\n3. Services: Add business logic to existing service files\n4. Prisma Schema: Add new models or fields and generate migrations\n5. Middleware: Add authentication guards, validators following existing patterns`,
    icon: Zap,
    accentColor: 'from-yellow-400 to-amber-500',
    colorClass: 'text-yellow-400 bg-yellow-500/10 border-yellow-500/20 hover:border-yellow-500/40 hover:text-yellow-300'
  },
  {
    name: 'Go Developer',
    tags: 'Go, Gin, GORM, gRPC, REST API, Docker, Microservices',
    specialization: 'Development',
    brownfieldOnly: true,
    defaultModel: 'claude',
    defaultTools: ['filesystem', 'git', 'terminal', 'build_tool'],
    description: 'Brownfield Go agent. Reads existing handlers, models, and routes, then makes targeted additions to Go microservices and REST APIs.',
    skills: `# Go Developer Agent Skill\n\n## Role\nYou are a specialized Brownfield Go Developer Agent. You work on EXISTING Go applications — reading current code before making any changes.\n\n## Tech Stack\n- Language: Go 1.19+\n- Framework: Gin / Echo / Fiber / net/http\n- ORM: GORM / sqlx\n- Package Manager: Go Modules (go.mod)\n- Testing: testing package, testify\n- Protocols: REST / gRPC\n\n## Brownfield Working Rules\n1. ALWAYS read the existing handler/struct: cat /workspace/internal/handlers/existing.go\n2. Follow the existing package structure — do NOT create new top-level packages without reason\n3. Add new route handlers as functions in existing handler files or new files in the same package\n4. Register new routes in the existing router setup (e.g., router.GET("/new", handler))\n5. New structs go in the existing models/ or types/ package\n6. Run: go test ./... after changes\n\n## Core Responsibilities\n1. Handlers: Add new HTTP handler functions following the existing (c *gin.Context) pattern\n2. Routes: Register in the existing router group setup\n3. Models/Structs: Add new GORM model structs with proper tags\n4. Services: Add business logic to existing service structs\n5. Middleware: Add new gin.HandlerFunc middleware in the existing middleware chain`,
    icon: Triangle,
    accentColor: 'from-cyan-400 to-blue-500',
    colorClass: 'text-cyan-400 bg-cyan-500/10 border-cyan-500/20 hover:border-cyan-500/40 hover:text-cyan-300'
  }
];

/**
 * AgentsPage – Full‑screen view of all agents for the current organization.
 * It lists system and custom agents and allows creation/deletion of custom agents globally.
 */
export default function AgentsPage({ projects = [] }) {
  const [sharedAgents, setSharedAgents] = useState([]);        // Development custom agents
  const [dedicatedAgents, setDedicatedAgents] = useState([]);   // Testing custom agents
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [deletingId, setDeletingId] = useState(null);
  const [filter, setFilter] = useState('all');
  const [quota, setQuota] = useState(null);
  const [quotaError, setQuotaError] = useState('');
  const [quotaLoading, setQuotaLoading] = useState(false);
  const [sharedDevToAdd, setSharedDevToAdd] = useState(0);
  const [dedicatedDevToAdd, setDedicatedDevToAdd] = useState(0);
  const [quotaUpdatingKind, setQuotaUpdatingKind] = useState('');

  // Project agent requests & modal states
  const [showRequestModal, setShowRequestModal] = useState(false);
  const [projectRequests, setProjectRequests] = useState([]);
  const [userRbac, setUserRbac] = useState(null);

  const isOrgAdmin = Boolean(userRbac?.is_org_admin);

  useEffect(() => {
    const token = localStorage.getItem('token');
    if (!token) return;
    fetch(API_ENDPOINTS.ORG_RBAC_ME, {
      headers: { Authorization: `Bearer ${token}` }
    })
      .then(res => res.json())
      .then(data => setUserRbac(data))
      .catch(() => {});
  }, []);

  const fetchProjectRequests = useCallback(async () => {
    const token = localStorage.getItem('token');
    if (!token) return;
    try {
      const res = await fetch(API_ENDPOINTS.AGENT_PROJECT_REQUESTS, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setProjectRequests(data);
      }
    } catch (e) {
      console.error('Failed to load project requests', e);
    }
  }, []);

  useEffect(() => {
    fetchProjectRequests();
  }, [fetchProjectRequests]);

  // Toast notifications state
  const [toast, setToast] = useState({ message: '', type: null });
  const toastTimerRef = useRef(null);
  const [addingTemplateName, setAddingTemplateName] = useState(null);

  const showToast = useCallback((message, type = 'success') => {
    setToast({ message, type });
    if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
    toastTimerRef.current = setTimeout(() => {
      setToast({ message: '', type: null });
      toastTimerRef.current = null;
    }, 4500);
  }, []);

  const hideToast = useCallback(() => {
    setToast({ message: '', type: null });
    if (toastTimerRef.current) {
      clearTimeout(toastTimerRef.current);
      toastTimerRef.current = null;
    }
  }, []);

  useEffect(() => {
    return () => {
      if (toastTimerRef.current) {
        clearTimeout(toastTimerRef.current);
      }
    };
  }, []);

  const handleApproveProjectRequest = async (req) => {
    const token = localStorage.getItem('token');
    if (!token) return;
    try {
      const res = await fetch(API_ENDPOINTS.AGENT_PROJECT_REQUEST_APPROVE(req.id), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify({ review_comment: 'Approved by Organization Admin' })
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'Failed to approve request');
      }
      showToast(`Request for "${req.project_name || req.project_token}" approved!`, 'success');
      fetchProjectRequests();
      if (typeof fetchQuota === 'function') fetchQuota();
    } catch (err) {
      showToast(err.message || 'Failed to approve request', 'error');
    }
  };

  const handleRejectProjectRequest = async (req) => {
    const token = localStorage.getItem('token');
    if (!token) return;
    const comment = window.prompt(`Please enter reason for rejecting request for "${req.project_name || req.project_token}" (optional):`);
    if (comment === null) return;

    try {
      const res = await fetch(API_ENDPOINTS.AGENT_PROJECT_REQUEST_REJECT(req.id), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify({ review_comment: comment.trim() || 'Rejected by Organization Admin' })
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'Failed to reject request');
      }
      showToast(`Request for "${req.project_name || req.project_token}" rejected.`, 'info');
      fetchProjectRequests();
    } catch (err) {
      showToast(err.message || 'Failed to reject request', 'error');
    }
  };

  const handleEscalateProjectRequest = async (req) => {
    const token = localStorage.getItem('token');
    if (!token) return;
    const totalAgents = (req.requested_shared_count || 0) + (req.requested_dedicated_count || 0);
    if (!window.confirm(`Escalate capacity request for "${req.project_name || req.project_token}" (+${totalAgents} agents) to Super Admin?`)) {
      return;
    }

    try {
      const res = await fetch(API_ENDPOINTS.AGENT_PROJECT_REQUEST_ESCALATE(req.id), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`
        }
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'Failed to escalate request');
      }
      showToast(`Request for "${req.project_name || req.project_token}" escalated to Super Admin!`, 'success');
      fetchProjectRequests();
    } catch (err) {
      showToast(err.message || 'Failed to escalate request', 'error');
    }
  };

  const [showAddAgentModal, setShowAddAgentModal] = useState(false);
  const [newAgentName, setNewAgentName] = useState('');
  const [skillsContent, setSkillsContent] = useState('');
  const [skillsFileName, setSkillsFileName] = useState('');
  const [newAgentFace, setNewAgentFace] = useState('');
  const [newAgentTags, setNewAgentTags] = useState('');
  const [addingAgent, setAddingAgent] = useState(false);
  const [addAgentError, setAddAgentError] = useState('');
  const [isConfiguringTemplate, setIsConfiguringTemplate] = useState(false);
  const [editingAgentId, setEditingAgentId] = useState(null);
  const [skillsTab, setSkillsTab] = useState('editor');

  // Authorized tools state
  const [availableToolsList, setAvailableToolsList] = useState(DEFAULT_TOOLS_CATALOG);
  const [selectedTools, setSelectedTools] = useState([
    'filesystem', 'git', 'terminal', 'build_tool'
  ]);

  // Attached AI Engine model state
  const [availableModelsList, setAvailableModelsList] = useState(DEFAULT_MODELS_CATALOG);
  const [selectedModel, setSelectedModel] = useState('claude');

  const fetchAvailableTools = useCallback(async () => {
    try {
      const token = localStorage.getItem('token');
      const endpoint = API_ENDPOINTS.AGENT_TOOLS_AVAILABLE || `${API_ENDPOINTS.AGENTS}/tools/available`;
      const res = await fetch(endpoint, {
        headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}) }
      });
      if (res.ok) {
        const data = await res.json();
        if (data.tools && Array.isArray(data.tools) && data.tools.length > 0) {
          setAvailableToolsList(data.tools);
        }
      }
    } catch (err) {
      console.warn('Using default tool catalog fallback:', err);
    }
  }, []);

  useEffect(() => {
    fetchAvailableTools();
  }, [fetchAvailableTools]);

  const fetchAvailableModels = useCallback(async () => {
    try {
      const token = localStorage.getItem('token');
      const endpoint = API_ENDPOINTS.AGENT_MODELS_AVAILABLE || `${API_ENDPOINTS.AGENTS}/models/available`;
      const res = await fetch(endpoint, {
        headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}) }
      });
      if (res.ok) {
        const data = await res.json();
        if (data.models && Array.isArray(data.models) && data.models.length > 0) {
          const cleaned = data.models.map(m => ({
            ...m,
            name: sanitizeModelName(m.name, m.id)
          }));
          setAvailableModelsList(cleaned);
        }
      }
    } catch (err) {
      console.warn('Using default model catalog fallback:', err);
    }
  }, []);

  useEffect(() => {
    fetchAvailableModels();
  }, [fetchAvailableModels]);

  // Skill-gap detection state (brownfield projects)
  const [skillGapData, setSkillGapData] = useState(null);
  const [skillGapLoading, setSkillGapLoading] = useState(false);

  // Current active brownfield project (first project in list with type brownfield)
  const activeBrownfieldProject = useMemo(() => {
    return (projects || []).find(p =>
      ['brownfield', 'modernization', 'migration'].includes(
        (p.project_type || '').toLowerCase()
      )
    ) || null;
  }, [projects]);

  // Fetch skill gaps for the active brownfield project
  const fetchSkillGaps = useCallback(async (projectToken) => {
    if (!projectToken) { setSkillGapData(null); return; }
    setSkillGapLoading(true);
    try {
      const token = localStorage.getItem('token');
      const base = (API_ENDPOINTS.AGENTS || '').replace(/\/agents\/?$/, '');
      const res = await fetch(`${base}/projects/${projectToken}/skill-gaps`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        setSkillGapData(data);
      } else {
        setSkillGapData(null);
      }
    } catch {
      setSkillGapData(null);
    } finally {
      setSkillGapLoading(false);
    }
  }, []);

  // Handle markdown file selection and parse content inside the browser
  const handleFileChange = (e) => {
    const file = e.target.files[0];

    if (file) {
      if (!file.name.endsWith('.md')) {
        setAddAgentError('Please upload a markdown (.md) file.');
        return;
      }
      setSkillsFileName(file.name);
      setAddAgentError('');

      const reader = new FileReader();
      reader.onload = (event) => {
        setSkillsContent(event.target.result);
        setSkillsTab('editor');
      };
      reader.onerror = () => {
        setAddAgentError('Failed to read the file.');
      };
      reader.readAsText(file);
    }
  };

  // Handle agent icon (face) file selection and convert to Base64
  const handleFaceChange = (e) => {
    const file = e.target.files[0];
    if (file) {
      if (!file.type.startsWith('image/')) {
        setAddAgentError('Please upload an image file for the agent icon.');
        return;
      }
      const reader = new FileReader();
      reader.onload = (event) => {
        setNewAgentFace(event.target.result);
      };
      reader.onerror = () => {
        setAddAgentError('Failed to read the image file.');
      };
      reader.readAsDataURL(file);
    }
  };

  const handleAddAgentSubmit = async (e) => {
    e.preventDefault();
    if (!newAgentName.trim() || !skillsContent) return;
    setAddingAgent(true);
    setAddAgentError('');
    const token = localStorage.getItem('token');
    const isEditing = !!editingAgentId;
    const url = isEditing 
      ? `${API_ENDPOINTS.AGENTS}/skills/update/${editingAgentId}` 
      : `${API_ENDPOINTS.AGENTS}/skills/add`;
    try {
      const res = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          name: newAgentName.trim(),
          skills_content: skillsContent,
          face: newAgentFace || null,
          tags: newAgentTags.trim() || (newAgentName.trim() ? newAgentName.trim().split(/[\s/\\_-]+/).filter(Boolean).slice(0, 4).join(', ') : 'Custom Agent'),
          tools: selectedTools,
          model_name: selectedModel || 'claude',
          project_token: projects && projects[0] ? projects[0].project_token : null
        })
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || `Failed to ${isEditing ? 'update' : 'create'} custom agent`);
      }

      // Reset form and modal
      setShowAddAgentModal(false);
      setIsConfiguringTemplate(false);
      setEditingAgentId(null);
      setNewAgentName('');
      setSkillsContent('');
      setSkillsFileName('');
      setNewAgentFace('');
      setNewAgentTags('');
      setSelectedTools(['filesystem', 'git', 'terminal', 'build_tool']);
      setSelectedModel('claude');

      showToast(`Agent "${newAgentName.trim()}" ${isEditing ? 'updated' : 'added'} successfully!`, 'success');

      // Refresh lists
      await fetchAgents();
      await fetchQuota();
      if (activeBrownfieldProject?.project_token) {
        await fetchSkillGaps(activeBrownfieldProject.project_token);
      }
    } catch (err) {
      setAddAgentError(err.message || `Failed to ${isEditing ? 'update' : 'add'} custom agent`);
      showToast(err.message || `Failed to ${isEditing ? 'update' : 'add'} custom agent`, 'error');
    } finally {
      setAddingAgent(false);
    }
  };


  const handleQuickAddAgent = async (tmpl) => {
    setLoading(true);
    setError(null);
    setAddingTemplateName(tmpl.name);
    const token = localStorage.getItem('token');
    try {
      const res = await fetch(`${API_ENDPOINTS.AGENTS}/skills/add`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          name: tmpl.name,
          skills_content: tmpl.skills,
          face: null,
          tags: tmpl.tags,
          tools: tmpl.defaultTools || ['filesystem', 'git', 'terminal', 'build_tool'],
          model_name: tmpl.defaultModel || 'claude',
          project_token: projects && projects[0] ? projects[0].project_token : null
        })
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'Failed to add agent');
      }
      showToast(`Agent "${tmpl.name}" added successfully!`, 'success');
      await fetchAgents();
      await fetchQuota();
      if (activeBrownfieldProject?.project_token) {
        await fetchSkillGaps(activeBrownfieldProject.project_token);
      }
    } catch (err) {
      setError(err.message || 'Failed to add custom agent');
      showToast(err.message || 'Failed to add custom agent', 'error');
    } finally {
      setLoading(false);
      setAddingTemplateName(null);
    }
  };

  const fetchAgents = async () => {
    setLoading(true);
    setError(null);
    const token = localStorage.getItem('token');
    try {
      const headers = { Authorization: `Bearer ${token}` };
      const parse = (data) => Array.isArray(data) ? data : (data?.agents || data?.results || data?.data || []);

      const url = new URL(API_ENDPOINTS.AGENTS);
      url.searchParams.set('include_defaults', 'false');

      const res = await fetch(url.toString(), { headers });
      const data = await res.json();
      const customList = parse(data);

      // Classify custom agents based on specialization:
      // 'Testing' specialists mapped to dedicatedAgents, others to sharedAgents
      const devAgents = customList
        .filter(a => a.specialization !== 'Testing')
        .map(a => ({ ...a, agentType: 'shared' }));
      const testAgents = customList
        .filter(a => a.specialization === 'Testing')
        .map(a => ({ ...a, agentType: 'dedicated' }));

      setSharedAgents(devAgents);
      setDedicatedAgents(testAgents);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAgents();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const fetchQuota = async () => {
    const token = localStorage.getItem('token');
    if (!token) return;
    setQuotaLoading(true);
    setQuotaError('');
    try {
      const res = await fetch(API_ENDPOINTS.ORG_AGENT_QUOTA, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(data.detail || 'Failed to load organization agent quota');
      }
      setQuota(data);
    } catch (e) {
      setQuotaError(e?.message || 'Failed to load organization agent quota');
    } finally {
      setQuotaLoading(false);
    }
  };

  useEffect(() => {
    fetchQuota();
  }, []);

  // Fetch skill gaps whenever the active brownfield project changes
  useEffect(() => {
    if (activeBrownfieldProject?.project_token) {
      fetchSkillGaps(activeBrownfieldProject.project_token);
    } else {
      setSkillGapData(null);
    }
  }, [activeBrownfieldProject, fetchSkillGaps]);

  const clampPositiveInt = (value, max = 1000) => {
    const n = Number(value);
    if (!Number.isFinite(n)) return 1;
    return Math.max(1, Math.min(max, Math.floor(n)));
  };

  const increaseQuota = async (kind, subType, amount) => {
    const token = localStorage.getItem('token');
    if (!token) return;
    setQuotaUpdatingKind(kind);
    setQuotaError('');
    try {
      const res = await fetch(API_ENDPOINTS.ORG_AGENT_QUOTA_INCREASE, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ kind, sub_type: subType, amount }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(data.detail || 'Failed to update agent quota');
      }
      setQuota(data);
      await fetchAgents();
      await fetchQuota();
    } catch (e) {
      setQuotaError(e?.message || 'Failed to update agent quota');
    } finally {
      setQuotaUpdatingKind('');
    }
  };

  const handleDeleteAgent = async (agentId) => {
    setDeletingId(agentId);
    const token = localStorage.getItem('token');
    try {
      const deleteUrl = new URL(API_ENDPOINTS.AGENT_REMOVE(agentId));
      const res = await fetch(deleteUrl.toString(), {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error('Failed to delete agent');

      // Remove from states and refetch
      setSharedAgents((prev) => prev.filter((a) => a.id !== agentId));
      setDedicatedAgents((prev) => prev.filter((a) => a.id !== agentId));
      showToast('Agent deleted successfully!', 'success');
      await fetchAgents();
      await fetchQuota();
      if (activeBrownfieldProject?.project_token) {
        await fetchSkillGaps(activeBrownfieldProject.project_token);
      }
    } catch (e) {
      setError(e.message);
      showToast(e.message || 'Failed to delete agent', 'error');
    } finally {
      setDeletingId(null);
    }
  };

  const getStatusIcon = (status) => {
    switch (status) {
      case 'running':
        return <Activity className="w-4 h-4 text-cyan-500 animate-pulse" />;
      case 'idle':
        return <CheckCircle className="w-4 h-4 text-app-primary" />;
      case 'error':
      case 'failed':
        return <AlertCircle className="w-4 h-4 text-app-status-error" />;
      default:
        return <Clock className="w-4 h-4 text-app-text-light" />;
    }
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'running':
        return 'bg-cyan-500/10 border-cyan-500/30 text-cyan-400';
      case 'idle':
        return 'bg-app-primary/10 border-app-primary/30 text-blue-400';
      case 'error':
      case 'failed':
        return 'bg-app-status-error/10 border-app-status-error/30 text-red-400';
      default:
        return 'bg-app-text-muted/10 border-app-text-muted/30 text-app-text-light';
    }
  };

  // Default system agents that appear in all projects
  const defaultAgents = useMemo(() => {
    return [
      {
        id: 'agent_03',
        name: 'Git Manager',
        status: 'idle',
        agentType: 'system',
        type: 'system',
        logo: null,
        icon: GitBranch,
      },
      {
        id: 'agent_04',
        name: 'Master Agent',
        status: 'idle',
        agentType: 'system',
        type: 'system',
        logo: masterLogo,
        icon: Bot,
      },
      {
        id: 'deploy_agent',
        name: 'Deploy Agent',
        status: 'idle',
        agentType: 'system',
        type: 'system',
        icon: Globe,
      },
    ];
  }, []);

  // Filter agents based on selected filter
  const getFilteredAgents = () => {
    const allAgents = [...defaultAgents, ...sharedAgents, ...dedicatedAgents];
    switch (filter) {
      case 'shared':
        return sharedAgents;
      case 'dedicated':
        return dedicatedAgents;
      default:
        return allAgents;
    }
  };

  const filteredAgents = getFilteredAgents();
  const totalAgents = defaultAgents.length + sharedAgents.length + dedicatedAgents.length;

  const quotaSummary = useMemo(() => {
    if (!quota) return null;
    const sharedQuota = Number(quota.shared_quota ?? 0);
    const sharedUsed = Number(quota.shared_used ?? 0);
    const sharedAvailable = Math.max(0, sharedQuota - sharedUsed);

    const dedicatedQuota = Number(quota.dedicated_quota ?? 0);
    const dedicatedUsed = Number(quota.dedicated_used ?? 0);
    const dedicatedAvailable = Math.max(0, dedicatedQuota - dedicatedUsed);

    return {
      sharedQuota,
      sharedUsed,
      sharedAvailable,
      dedicatedQuota,
      dedicatedUsed,
      dedicatedAvailable,
    };
  }, [quota]);

  return (
    <div className="h-full w-full flex flex-col overflow-y-auto bg-app-bg-page text-app-text-main custom-scrollbar">
      {/* Header */}
      <div className="flex-shrink-0 flex items-center justify-between px-6 py-4 border-b border-app-border-light bg-app-bg-card/50">
        <h1 className="text-2xl font-bold flex items-center">
          <Users className="w-6 h-6 mr-2 animate-pulse" /> Agents
        </h1>
        <div className="flex items-center space-x-3">
          <span className="text-sm text-app-text-muted">
            {totalAgents} agent{totalAgents !== 1 ? 's' : ''} ({defaultAgents.length} system, {sharedAgents.length} dev, {dedicatedAgents.length} test)
          </span>
          <button
            onClick={async () => {
              await fetchAgents();
              await fetchQuota();
            }}
            disabled={loading}
            className="flex items-center px-4 py-2 text-sm font-medium text-app-text-main bg-app-text-label/20 rounded-lg hover:bg-app-text-label/30 transition-colors disabled:opacity-50"
          >
            <RefreshCw className={`w-4 h-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      {/* Organization Capacity */}
      <div className="flex-shrink-0 px-4 md:px-6 py-4 border-b border-app-border-light bg-gradient-to-br from-app-bg-card/50 to-app-bg-card/30">
        {quotaLoading && !quota ? (
          <div className="flex items-center gap-2 text-xs text-app-text-muted py-1">
            <RefreshCw className="w-3 h-3 animate-spin" />
            <span>Loading capacity…</span>
          </div>
        ) : quotaError ? (
          <div className="p-2 rounded-lg bg-app-status-error/10 border border-app-status-error/30">
            <p className="text-xs text-red-400 flex items-center gap-2">
              <AlertCircle className="w-3 h-3" />
              {quotaError}
            </p>
          </div>
        ) : quotaSummary ? (
          <div>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3.5 sm:gap-4">
              {/* ── Card 1: Shared Agents in Use ── */}
              <div className="bg-app-bg-card border border-app-border hover:border-slate-300 dark:hover:border-slate-600 rounded-2xl p-3.5 sm:p-4 shadow-xs hover:shadow-md transition-all flex flex-col justify-between">
                <div>
                  <div className="flex items-center gap-2.5 mb-3">
                    <div className="w-9 h-9 rounded-xl bg-emerald-50 dark:bg-emerald-950/50 text-emerald-600 dark:text-emerald-400 flex items-center justify-center shrink-0">
                      <Users className="w-4 h-4" />
                    </div>
                    <span className="text-sm font-bold text-app-text-main">Shared Agents</span>
                  </div>

                  <div className="text-3xl font-bold tracking-tight text-emerald-600 dark:text-emerald-400">
                    {quotaSummary ? quotaSummary.sharedUsed : sharedAgents.length}
                  </div>
                </div>

                <div className="mt-3 space-y-1.5">
                  <div className="text-xs text-app-text-muted font-medium">Allocation Mode</div>
                  <div>
                    <span className="inline-flex items-center px-3 py-1 rounded-full text-xs font-semibold bg-emerald-50 dark:bg-emerald-950/50 text-emerald-700 dark:text-emerald-300 border border-emerald-200/80 dark:border-emerald-800/60">
                      Floating / Multi-Project
                    </span>
                  </div>
                </div>
              </div>

              {/* ── Card 2: Dedicated Agents in Use ── */}
              <div className="bg-app-bg-card border border-app-border hover:border-slate-300 dark:hover:border-slate-600 rounded-2xl p-3.5 sm:p-4 shadow-xs hover:shadow-md transition-all flex flex-col justify-between">
                <div>
                  <div className="flex items-center gap-2.5 mb-3">
                    <div className="w-9 h-9 rounded-xl bg-purple-50 dark:bg-purple-950/50 text-purple-600 dark:text-purple-400 flex items-center justify-center shrink-0">
                      <Activity className="w-4 h-4" />
                    </div>
                    <span className="text-sm font-bold text-app-text-main">Dedicated Agents</span>
                  </div>

                  <div className="text-3xl font-bold tracking-tight text-purple-600 dark:text-purple-400">
                    {quotaSummary ? quotaSummary.dedicatedUsed : dedicatedAgents.length}
                  </div>
                </div>

                <div className="mt-3 space-y-1.5">
                  <div className="text-xs text-app-text-muted font-medium">Allocation Mode</div>
                  <div>
                    <span className="inline-flex items-center px-3 py-1 rounded-full text-xs font-semibold bg-purple-50 dark:bg-purple-950/50 text-purple-700 dark:text-purple-300 border border-purple-200/80 dark:border-purple-800/60">
                      Dedicated Home Project
                    </span>
                  </div>
                </div>
              </div>

              {/* ── Card 3: Capacity Governance Summary ── */}
              <div className="bg-app-bg-card border border-app-border hover:border-slate-300 dark:hover:border-slate-600 rounded-2xl p-3.5 sm:p-4 shadow-xs hover:shadow-md transition-all flex flex-col justify-between">
                <div>
                  <div className="flex items-center gap-2.5 mb-3">
                    <div className="w-9 h-9 rounded-xl bg-blue-50 dark:bg-blue-950/50 text-blue-600 dark:text-blue-400 flex items-center justify-center shrink-0">
                      <Server className="w-4 h-4" />
                    </div>
                    <span className="text-sm font-bold text-app-text-main">Capacity Governance</span>
                  </div>

                  <div className="space-y-2 mt-1 text-[11px] xl:text-xs">
                    <div className="flex items-center justify-between gap-1 whitespace-nowrap">
                      <span className="text-app-text-muted">Total Super Admin Cap:</span>
                      <span className="font-bold text-blue-600 dark:text-blue-400">
                        {quota?.max_agent_capacity || 10} Max Agents
                      </span>
                    </div>
                    <div className="flex items-center justify-between gap-1 whitespace-nowrap">
                      <span className="text-app-text-muted">Currently Active Agents:</span>
                      <span className="font-bold text-emerald-600 dark:text-emerald-400">
                        {quotaSummary.sharedUsed + quotaSummary.dedicatedUsed} Active
                      </span>
                    </div>
                    <div className="flex items-center justify-between gap-1 whitespace-nowrap">
                      <span className="text-app-text-muted">Available Capacity Slots:</span>
                      <span className="font-bold text-blue-600 dark:text-blue-400">
                        {Math.max(0, (quota?.max_agent_capacity || 10) - (quotaSummary.sharedUsed + quotaSummary.dedicatedUsed))} Slots
                      </span>
                    </div>
                  </div>
                </div>
              </div>

              {/* ── Card 4: Capacity Request ── */}
              <div className="bg-app-bg-card border border-app-border hover:border-slate-300 dark:hover:border-slate-600 rounded-2xl p-3.5 sm:p-4 shadow-xs hover:shadow-md transition-all flex flex-col justify-between">
                <div>
                  <div className="flex items-center gap-2.5 mb-3">
                    <div className="w-9 h-9 rounded-xl bg-purple-50 dark:bg-purple-950/50 text-purple-600 dark:text-purple-400 flex items-center justify-center shrink-0">
                      <TrendingUp className="w-4 h-4" />
                    </div>
                    <span className="text-sm font-bold text-app-text-main">Capacity Request</span>
                  </div>

                  <p className="text-xs text-app-text-muted leading-relaxed mt-1">
                    Request additional capacity for projects when required.
                  </p>
                </div>

                <div className="mt-3">
                  <button
                    type="button"
                    onClick={() => setShowRequestModal(true)}
                    className="w-full py-2 px-3 rounded-xl bg-indigo-600 hover:bg-indigo-700 active:bg-indigo-800 text-white text-xs font-semibold transition-all flex items-center justify-center gap-1.5 shadow-sm cursor-pointer whitespace-nowrap"
                  >
                    <PlusCircle className="w-3.5 h-3.5 shrink-0" />
                    <span>Request Capacity Increase</span>
                  </button>
                </div>
              </div>
            </div>

            {/* ── End-User Project Requests Control Panel (Visible to Org Admins & Team Members) ── */}
            {projectRequests && projectRequests.length > 0 && (
              <div className="mt-6 p-4 rounded-2xl bg-app-bg-card border border-app-border-light space-y-3">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-bold text-app-text-main flex items-center gap-2">
                    <Building2 className="w-4 h-4 text-purple-400" />
                    Project Agent Capacity Requests
                  </h3>
                  <span className="text-xs text-app-text-muted">
                    {isOrgAdmin ? 'Requests raised by End Users for projects' : 'My Project Capacity Requests'}
                  </span>
                </div>

                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs">
                    <thead className="bg-app-bg-muted/50 text-app-text-muted font-semibold uppercase text-[10px]">
                      <tr>
                        <th className="py-2 px-3">Project</th>
                        <th className="py-2 px-3">Requested By</th>
                        <th className="py-2 px-3">Shared</th>
                        <th className="py-2 px-3">Dedicated</th>
                        <th className="py-2 px-3">Reason</th>
                        <th className="py-2 px-3">Status</th>
                        <th className="py-2 px-3 text-right">Actions</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-app-border-light/40 text-app-text-main">
                      {projectRequests.map((req) => (
                        <tr key={req.id} className="hover:bg-app-bg-muted/20">
                          <td className="py-2.5 px-3 font-semibold text-purple-300">
                            {req.project_name || req.project_token}
                          </td>
                          <td className="py-2.5 px-3 text-app-text-muted">{req.requested_by_email}</td>
                          <td className="py-2.5 px-3 font-bold text-emerald-400">+{req.requested_shared_count}</td>
                          <td className="py-2.5 px-3 font-bold text-blue-400">+{req.requested_dedicated_count}</td>
                          <td className="py-2.5 px-3 text-app-text-muted italic max-w-xs" title={req.reason}>
                            <div className="truncate">{req.reason || 'No reason provided'}</div>
                            {req.review_comment && (
                              <div className="text-[10px] text-purple-400/90 truncate mt-0.5" title={`Admin Note: ${req.review_comment}`}>
                                Note: {req.review_comment}
                              </div>
                            )}
                          </td>
                          <td className="py-2.5 px-3">
                            <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                              req.status === 'APPROVED' ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30' :
                              req.status === 'REJECTED' ? 'bg-rose-500/20 text-rose-400 border border-rose-500/30' :
                              req.status === 'ESCALATED' ? 'bg-purple-500/20 text-purple-300 border border-purple-500/30' :
                              'bg-amber-500/20 text-amber-300 border border-amber-500/30'
                            }`}>
                              {req.status}
                            </span>
                          </td>
                          <td className="py-2.5 px-3 text-right">
                            {isOrgAdmin && req.status === 'PENDING' ? (
                              <div className="inline-flex items-center justify-end gap-1.5 flex-wrap">
                                <button
                                  onClick={() => handleApproveProjectRequest(req)}
                                  className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md bg-emerald-600 hover:bg-emerald-500 text-white text-[11px] font-bold transition-all shadow-sm"
                                  title="Approve and allocate from existing organization capacity"
                                >
                                  <CheckCircle className="w-3 h-3" />
                                  Approve
                                </button>
                                <button
                                  onClick={() => handleRejectProjectRequest(req)}
                                  className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md bg-rose-600 hover:bg-rose-500 text-white text-[11px] font-bold transition-all shadow-sm"
                                  title="Reject this request"
                                >
                                  <Trash2 className="w-3 h-3" />
                                  Reject
                                </button>
                                <button
                                  onClick={() => handleEscalateProjectRequest(req)}
                                  className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md bg-purple-600 hover:bg-purple-500 text-white text-[11px] font-bold transition-all shadow-sm"
                                  title="Escalate to Super Admin for additional quota"
                                >
                                  <Shield className="w-3 h-3" />
                                  Escalate
                                </button>
                              </div>
                            ) : req.status === 'ESCALATED' ? (
                              <span className="inline-flex items-center gap-1 text-[11px] text-purple-400 font-medium">
                                <Clock className="w-3 h-3" />
                                Escalated to Super Admin
                              </span>
                            ) : req.status === 'APPROVED' ? (
                              <span className="inline-flex items-center gap-1 text-[11px] text-emerald-400 font-medium">
                                <CheckCircle className="w-3 h-3" />
                                Approved
                              </span>
                            ) : req.status === 'REJECTED' ? (
                              <span className="inline-flex items-center gap-1 text-[11px] text-rose-400 font-medium" title={req.review_comment || ''}>
                                <AlertCircle className="w-3 h-3" />
                                Rejected
                              </span>
                            ) : req.status === 'PENDING' ? (
                              <span className="inline-flex items-center gap-1 text-[11px] text-amber-400 font-medium">
                                <Clock className="w-3 h-3" />
                                Awaiting Org Admin
                              </span>
                            ) : (
                              <span className="text-app-text-muted text-[11px]">—</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        ) : (
          <div className="p-2 rounded-lg bg-app-bg-muted/50 border border-app-border-light">
            <p className="text-xs text-app-text-muted">Capacity not available.</p>
          </div>
        )}
      </div>

      {/* Filter Buttons */}
      <div className="flex-shrink-0 px-6 py-2 border-b border-app-border-light bg-app-bg-card/30">
        <div className="flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <Filter className="w-4 h-4 text-app-text-muted" />
            <span className="text-sm font-medium text-app-text-muted mr-2">Filter:</span>
            <button
              onClick={() => setFilter('all')}
              className={`px-3 py-1 text-sm font-medium rounded-lg transition-colors ${filter === 'all'
                ? 'bg-app-primary text-white'
                : 'bg-app-text-label/20 text-app-text-main hover:bg-app-text-label/30'
                }`}
            >
              All ({totalAgents})
            </button>
            <button
              onClick={() => setFilter('samples')}
              className={`px-3 py-1 text-sm font-medium rounded-lg transition-colors ${filter === 'samples'
                ? 'bg-app-primary text-white'
                : 'bg-app-text-label/20 text-app-text-main hover:bg-app-text-label/30'
                }`}
            >
              Templates ({PREDEFINED_TEMPLATES.length})
            </button>
            <button
              onClick={() => setFilter('shared')}
              className={`px-3 py-1 text-sm font-medium rounded-lg transition-colors ${filter === 'shared'
                ? 'bg-app-primary text-white'
                : 'bg-app-text-label/20 text-app-text-main hover:bg-app-text-label/30'
                }`}
            >
              Development ({sharedAgents.length})
            </button>
            <button
              onClick={() => setFilter('dedicated')}
              className={`px-3 py-1 text-sm font-medium rounded-lg transition-colors ${filter === 'dedicated'
                ? 'bg-app-primary text-white'
                : 'bg-app-text-label/20 text-app-text-main hover:bg-app-text-label/30'
                }`}
            >
              Testing ({dedicatedAgents.length})
            </button>

          </div>

          <button
            onClick={() => {
              setIsConfiguringTemplate(false);
              setEditingAgentId(null);
              setNewAgentName('');
              setSkillsContent('');
              setSkillsFileName('');
              setNewAgentFace('');
              setNewAgentTags('');
              setSelectedTools(['filesystem', 'git', 'terminal', 'build_tool']);
              setSelectedModel('claude');
              setAddAgentError('');
              setShowAddAgentModal(true);
            }}
            className="flex items-center gap-1.5 px-3 py-1 text-sm font-semibold rounded-lg bg-gradient-to-r from-app-primary to-blue-600 hover:from-blue-600 hover:to-blue-700 text-white shadow-sm transition-all duration-200"
          >

            <Plus className="w-4 h-4" />
            <span>Add Agent</span>
          </button>
        </div>
      </div>


      {/* Main Content Area — Agent Cards Grid */}
      <div className="p-6 space-y-6">
          {/* Loading State */}
          {loading && filteredAgents.length === 0 && (
            <div className="flex items-center justify-center h-full">
              <div className="flex flex-col items-center">
                <RefreshCw className="w-8 h-8 text-app-primary animate-spin mb-4" />
                <p className="text-app-text-muted">Loading agents...</p>
              </div>
            </div>
          )}

          {/* Error State */}
          {error && (
            <div className="mb-6 p-4 bg-app-status-error/10 border border-app-status-error/30 rounded-lg">
              <p className="text-red-400 flex items-center">
                <AlertCircle className="w-5 h-5 mr-2" />
                {error}
              </p>
            </div>
          )}


          {/* Skill Gap Warning Banner for Brownfield Projects */}
          {activeBrownfieldProject && skillGapData?.skill_gaps?.has_gaps && (
            <div className="mb-6 p-5 bg-amber-500/10 border border-amber-500/20 rounded-xl flex flex-col gap-4 shadow-sm">
              <div className="flex items-start gap-3">
                <AlertCircle className="w-5 h-5 text-amber-400 flex-shrink-0 mt-0.5" />
                <div>
                  <h4 className="text-sm font-bold text-amber-200">
                    Required Agent Skills Missing
                  </h4>
                  <p className="text-xs text-amber-300/80 leading-relaxed mt-1">
                    Your brownfield project change request requires skills that are not covered by any of your registered agents.
                    Onboard a matching developer agent below to start task execution.
                  </p>
                  <div className="flex flex-wrap gap-2 mt-3">
                    <span className="text-xs font-semibold text-amber-300/60 self-center">Missing Skills:</span>
                    {skillGapData.skill_gaps.missing.map((skill, idx) => (
                      <span key={idx} className="px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-red-500/10 border border-red-500/20 text-red-400">
                        {skill}
                      </span>
                    ))}
                  </div>
                </div>
              </div>

              {/* Suggestions */}
              {skillGapData.skill_gaps.suggested_templates?.length > 0 && (
                <div className="pt-3 border-t border-amber-500/10 flex flex-col gap-2">
                  <span className="text-[11px] font-bold text-amber-200/70 uppercase tracking-wider">Suggested Agent Templates:</span>
                  <div className="flex flex-wrap gap-3">
                    {skillGapData.skill_gaps.suggested_templates.map((tmplName) => {
                      const tmpl = PREDEFINED_TEMPLATES.find(t => t.name === tmplName);
                      if (!tmpl) return null;
                      const IconComponent = tmpl.icon || Bot;
                      return (
                        <div key={tmplName} className="flex items-center gap-3 bg-app-bg-card/45 border border-app-border-light/30 rounded-lg p-2 pr-3.5 hover:border-app-primary/30 transition-all">
                          <div className="w-8 h-8 rounded-md bg-app-bg-page border flex items-center justify-center text-app-primary">
                            <IconComponent className="w-4 h-4" />
                          </div>
                          <div>
                            <div className="text-xs font-bold text-app-text-main">{tmpl.name}</div>
                            <div className="text-[10px] text-app-text-muted">{tmpl.tags.split(', ').slice(0, 3).join(', ')}</div>
                          </div>
                          <button
                            onClick={() => handleQuickAddAgent(tmpl)}
                            disabled={loading}
                            className="ml-2 px-2.5 py-1 text-[10px] font-bold bg-app-primary hover:bg-blue-600 text-white rounded-md transition-colors flex items-center gap-1 cursor-pointer"
                          >
                            {addingTemplateName === tmpl.name ? (
                              <RefreshCw className="w-3 h-3 animate-spin" />
                            ) : (
                              <Plus className="w-3 h-3" />
                            )}
                            <span>Quick Add</span>
                          </button>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Agents List */}
          {!error && (filteredAgents.length > 0 || !loading) && (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {filter === 'samples' ? (
                PREDEFINED_TEMPLATES.map((tmpl) => {
                  const IconComponent = tmpl.icon;
                  return (
                    <div
                      key={tmpl.name}
                      className="bg-app-bg-card rounded-xl shadow border border-app-border-light p-3.5 flex flex-col relative overflow-hidden group hover:shadow-lg transition-shadow"
                    >
                      {/* Top accent bar */}
                      <div className={`absolute top-0 left-0 right-0 h-1 bg-gradient-to-r ${tmpl.accentColor}`}></div>

                      <div className="flex items-start justify-between mb-2">
                        <div className="flex items-center gap-2.5">
                          {/* Agent Icon/Logo */}
                          <div className={`w-9 h-9 rounded-lg bg-app-bg-page border flex items-center justify-center shadow-lg ${
                            tmpl.name.includes('Frontend') ? 'text-emerald-500 dark:text-emerald-400 border-emerald-500/20 dark:border-emerald-500/30 bg-emerald-500/10 dark:bg-emerald-500/20' :
                            tmpl.name.includes('Backend') ? 'text-blue-500 dark:text-blue-400 border-blue-500/20 dark:border-blue-500/30 bg-blue-500/10 dark:bg-blue-500/20' :
                            tmpl.specialization === 'Integration' ? 'text-cyan-500 dark:text-cyan-400 border-cyan-500/20 dark:border-cyan-500/30 bg-cyan-500/10 dark:bg-cyan-500/20' :
                            'text-purple-500 dark:text-purple-400 border-purple-500/20 dark:border-purple-500/30 bg-purple-500/10 dark:bg-purple-500/20'
                          }`}>
                            <IconComponent className="w-4 h-4 text-current font-bold" />
                          </div>

                          <div>
                            <div className="flex items-center gap-1.5 flex-wrap">
                              <h4 className="text-xs font-bold text-app-text-main">
                                {tmpl.name}
                              </h4>
                              <span className={`px-1.5 py-0.5 text-[8px] font-bold rounded-full uppercase tracking-wider ${
                                tmpl.specialization === 'Testing'
                                  ? 'bg-purple-500/10 text-purple-400 border border-purple-500/20'
                                  : 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                              }`}>
                                {tmpl.specialization}
                              </span>
                              {(() => {
                                const mb = getModelBadge(tmpl.defaultModel || 'claude');
                                return (
                                  <span className={`px-1.5 py-0.5 text-[8px] font-bold rounded-full uppercase tracking-wider border ${mb.pillClass}`}>
                                    {mb.label}
                                  </span>
                                );
                              })()}
                            </div>
                            <p className="text-[9px] text-app-text-light uppercase tracking-wider font-semibold">Sample Template</p>
                          </div>
                        </div>
                      </div>

                      {/* Description */}
                      <div className="p-2 rounded-lg bg-app-bg-muted/40 border border-app-border-light/30 flex-1 flex flex-col justify-between mb-3">
                        <div>
                          <p className="text-[11px] leading-relaxed text-app-text-main">
                            {tmpl.description}
                          </p>
                          <div className="flex flex-wrap gap-1 mt-2">
                            {tmpl.tags.split(', ').map((tag, idx) => (
                              <span
                                key={idx}
                                className="px-1 py-0.5 rounded text-[8px] font-semibold bg-app-bg-page text-app-text-muted border border-app-border-light/40"
                              >
                                {tag}
                              </span>
                            ))}
                          </div>
                        </div>
                      </div>

                      {/* Action buttons */}
                      <div className="grid grid-cols-2 gap-2 mt-auto">
                        <button
                          type="button"
                          onClick={() => {
                            setNewAgentName(tmpl.name);
                            setNewAgentTags(tmpl.tags);
                            setSkillsContent(tmpl.skills);
                            setSkillsFileName(`${tmpl.name.toLowerCase().replace(/ & /g, '_').replace(/ /g, '_')}_skills.md`);
                            setSelectedTools(tmpl.defaultTools || ['filesystem', 'build_tool', 'visual_qa', 'web_search']);
                            setSelectedModel(tmpl.defaultModel || 'claude');
                            setIsConfiguringTemplate(true);
                            setShowAddAgentModal(true);
                          }}
                          className="py-1.5 rounded-lg bg-app-bg-muted hover:bg-app-bg-hover border border-app-border-light text-xs font-bold text-app-text-main transition-all flex items-center justify-center gap-1 cursor-pointer"
                        >
                          <Bot className="w-3.5 h-3.5" />
                          <span>Configure</span>
                        </button>
                        <button
                          type="button"
                          onClick={() => handleQuickAddAgent(tmpl)}
                          disabled={loading}
                          className="py-1.5 rounded-lg bg-app-primary hover:bg-blue-600 text-white text-xs font-bold transition-all flex items-center justify-center gap-1 cursor-pointer shadow-sm hover:shadow"
                        >
                          {addingTemplateName === tmpl.name ? (
                            <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                          ) : (
                            <Plus className="w-3.5 h-3.5" />
                          )}
                          <span>Quick Add</span>
                        </button>
                      </div>
                    </div>
                  );
                })
              ) : filteredAgents.length > 0 ? (
                filteredAgents.map((agent) => {
                  const isSystem = agent.agentType === 'system';
                  const isShared = agent.agentType === 'shared';
                  const isDedicated = agent.agentType === 'dedicated';
                  const isGitManager = agent.id === 'agent_03';
                  const isMasterAgent = agent.id === 'agent_04';
                  const isDeployAgent = agent.id === 'deploy_agent';
                  const isTestAgent = agent.sub_type === 'test' || agent.specialization === 'Testing';
                  const isRunning = agent.status === 'running';
                  const isCompleted = agent.status === 'completed';
                  const isError = agent.status === 'error';
                  const isIdle = agent.status === 'idle';

                  // Determine agent config based on ID
                  let accentColor = 'from-app-text-light to-app-text-muted';
                  let statusColor = 'gray';
                  let useLogo = false;
                  let logoSrc = null;

                  if (isGitManager) {
                    accentColor = 'from-app-primary to-app-primary';
                    statusColor = 'indigo';
                  } else if (isMasterAgent) {
                    accentColor = 'from-fuchsia-500 to-app-status-error';
                    statusColor = 'fuchsia';
                    useLogo = true;
                    logoSrc = agent.logo || masterLogo;
                  } else if (isTestAgent && isSystem) {
                    accentColor = 'from-app-status-warning to-orange-500';
                    statusColor = 'amber';
                    useLogo = true;
                    logoSrc = agent.logo || kaktoxLogo;
                  } else if (isDeployAgent) {
                    accentColor = 'from-violet-500 to-purple-600';
                    statusColor = 'violet';
                    useLogo = true;
                    logoSrc = cloudIcon;
                  } else if (isShared || isDedicated) {
                    accentColor = isShared ? 'from-emerald-400 to-teal-500' : 'from-purple-400 to-pink-500';
                    statusColor = isShared ? 'emerald' : 'purple';
                    useLogo = true;
                    logoSrc = agent.face || agent.logo || nModLogo;
                  }

                  const finalStatusColor = isRunning ? statusColor : isCompleted ? 'emerald' : isError ? 'red' : 'gray';

                  return (
                    <div
                      key={agent.id}
                      className="bg-app-bg-card rounded-xl shadow border border-app-border-light p-3.5 flex flex-col relative overflow-hidden group hover:shadow-lg transition-shadow"
                    >
                      {/* Top accent bar */}
                      <div className={`absolute top-0 left-0 right-0 h-1 bg-gradient-to-r ${accentColor}`}></div>

                      <div className="flex items-start justify-between mb-2">
                        <div className="flex items-center gap-2.5">
                          {/* Agent Icon/Logo */}
                          <div className={`w-9 h-9 rounded-lg ${useLogo ? 'bg-app-bg-page border border-app-border' : `bg-gradient-to-br ${isGitManager ? 'from-app-primary to-app-primary' :
                            isMasterAgent ? 'from-fuchsia-500 to-app-status-error' :
                              isTestAgent ? 'from-app-status-warning to-orange-600' :
                                isDeployAgent ? 'from-violet-500 to-purple-600' :
                                  isShared ? 'from-emerald-400 to-app-status-success' :
                                    'from-app-primary to-app-primary'
                            }`} flex items-center justify-center shadow-lg ${isGitManager ? 'shadow-app-primary-ring' :
                              isMasterAgent ? 'shadow-app-bg-hover' :
                                isTestAgent ? 'shadow-app-bg-hover' :
                                  isDeployAgent ? 'shadow-app-bg-hover' :
                                    isShared ? 'shadow-emerald-200' :
                                      'shadow-app-primary-ring'
                            } ${useLogo && !agent.face ? 'p-1' : ''}`}>
                            {useLogo && logoSrc ? (
                              <img src={logoSrc} alt={agent.name || getNeutralAgentName(agent)} className={`w-full h-full ${agent.face ? 'object-cover rounded-lg' : 'object-contain'}`} />
                            ) : isGitManager ? (
                              <GitBranch className="w-4 h-4 text-white" />
                            ) : isMasterAgent ? (
                              <Bot className="w-4 h-4 text-white" />
                            ) : isTestAgent ? (
                              <Activity className="w-4 h-4 text-white" />
                            ) : isDeployAgent ? (
                              <Globe className="w-4 h-4 text-white" />
                            ) : (
                              getStatusIcon(agent.status)
                            )}
                          </div>
                          <div>
                            <div className="flex items-center gap-1.5 flex-wrap">
                              <h4 className="text-xs font-bold text-app-text-main">
                                {agent.name || getNeutralAgentName(agent)}
                              </h4>
                              {agent.specialization && (
                                <span className={`px-1.5 py-0.5 text-[8px] font-bold rounded-full uppercase tracking-wider ${
                                  agent.specialization === 'Testing'
                                    ? 'bg-purple-500/10 text-purple-400 border border-purple-500/20'
                                    : 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                                }`}>
                                  {agent.specialization}
                                </span>
                              )}
                              {/* Attached AI Engine Model Badge */}
                              {(() => {
                                const mb = getModelBadge(agent.model_name || 'claude');
                                return (
                                  <span
                                    title={`Attached AI Engine: ${agent.model_name || 'claude'}`}
                                    className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full text-[8px] font-bold border ${mb.pillClass}`}
                                  >
                                    <span className={`w-1.5 h-1.5 rounded-full ${mb.dotClass}`}></span>
                                    <span>{mb.label}</span>
                                  </span>
                                );
                              })()}
                            </div>
                            <p className="text-[9px] text-app-text-light uppercase tracking-wider font-semibold">{getNeutralAgentLabel(agent)}</p>
                          </div>
                        </div>
                        <div className="flex items-center gap-1.5">
                          <div className="flex items-center gap-1.5 mr-1">
                            {isRunning && (
                              <span className="relative flex h-2 w-2">
                                <span className={`animate-ping absolute inline-flex h-full w-full rounded-full bg-${finalStatusColor}-400 opacity-75`}></span>
                                <span className={`relative inline-flex rounded-full h-2 w-2 bg-${finalStatusColor}-500`}></span>
                              </span>
                            )}
                            <span className={`text-[9px] font-bold text-${finalStatusColor}-${isIdle ? '500' : '600'}`}>
                              {agent.status?.toUpperCase() || 'IDLE'}
                            </span>
                          </div>
                          
                          {/* Edit / Configure Button - Available for all custom agents */}
                          {(isShared || isDedicated) && (
                            <button
                              onClick={() => {
                                setNewAgentName(agent.name || getNeutralAgentName(agent));
                                setNewAgentTags(agent.skills_tags ? agent.skills_tags.join(', ') : '');
                                setSkillsContent(agent.skills_content || '');
                                setSkillsFileName(`${(agent.name || getNeutralAgentName(agent)).toLowerCase().replace(/ & /g, '_').replace(/ /g, '_')}_skills.md`);
                                setNewAgentFace(agent.face || '');
                                setEditingAgentId(agent.id);
                                setSelectedTools(agent.allowed_tools && Array.isArray(agent.allowed_tools) && agent.allowed_tools.length > 0
                                  ? agent.allowed_tools
                                  : ['filesystem', 'git', 'terminal', 'build_tool']);
                                setSelectedModel(agent.model_name || 'claude');
                                setShowAddAgentModal(true);
                              }}
                              className="p-1 rounded-lg bg-app-bg-card/50 text-app-text-muted hover:text-app-primary hover:bg-app-primary/10 transition-all cursor-pointer"
                              title="Configure / Edit Agent"
                            >
                              <Edit className="w-3.5 h-3.5" />
                            </button>
                          )}

                          {/* Delete Button - Available for all custom agents */}
                          {(isShared || isDedicated) && (
                            <button
                              onClick={() => handleDeleteAgent(agent.id)}
                              disabled={deletingId === agent.id}
                              className="p-1 rounded-lg bg-app-bg-card/50 text-red-400 hover:text-red-300 hover:bg-app-status-error/10 transition-all disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
                              title="Delete custom agent"
                            >
                              {deletingId === agent.id ? (
                                <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                              ) : (
                                <Trash2 className="w-3.5 h-3.5" />
                              )}
                            </button>
                          )}
                        </div>
                      </div>

                      {/* Skills Summary for Custom Agents */}
                      {agent.skills_summary && (
                        <div className="mt-2.5 p-2 rounded-lg bg-app-bg-muted/40 border border-app-border-light/30 flex-1 flex flex-col justify-between mb-3">
                          <div>
                            <p className="text-[11px] text-app-text-main leading-relaxed italic mb-1.5">
                              "{agent.skills_summary}"
                            </p>
                          </div>

                          {/* Skills Tags Rendering */}
                          {agent.skills_tags && Array.isArray(agent.skills_tags) && agent.skills_tags.length > 0 && (
                            <div className="flex flex-wrap gap-1 mt-1">
                              {agent.skills_tags.map((tag, idx) => (
                                <span
                                  key={idx}
                                  className="px-1 py-0.5 rounded text-[8px] font-semibold bg-app-bg-page text-app-text-muted border border-app-border-light/40"
                                >
                                  {tag}
                                </span>
                              ))}
                            </div>
                          )}

                          {/* Authorized Tools Badges */}
                          {agent.allowed_tools && Array.isArray(agent.allowed_tools) && agent.allowed_tools.length > 0 && (
                            <div className="mt-2 pt-2 border-t border-app-border-light/30">
                              <div className="flex items-center justify-between mb-1">
                                <span className="text-[9px] font-bold text-app-text-muted uppercase tracking-wider flex items-center gap-1">
                                  <Wrench className="w-2.5 h-2.5 text-app-primary" />
                                  Sandbox Tools ({agent.allowed_tools.length})
                                </span>
                              </div>
                              <div className="flex flex-wrap gap-1">
                                {agent.allowed_tools.map((tId) => {
                                  const toolDef = (availableToolsList || DEFAULT_TOOLS_CATALOG).find(t => t.id === tId) || { name: tId };
                                  return (
                                    <span
                                      key={tId}
                                      title={toolDef.description || toolDef.name}
                                      className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[9px] font-medium bg-app-bg-muted/80 text-app-text-main border border-app-border-light/60 hover:border-app-primary/40 transition-colors"
                                    >
                                      {getToolIcon(toolDef.icon, 'w-2.5 h-2.5')}
                                      <span>{toolDef.name || tId}</span>
                                    </span>
                                  );
                                })}
                              </div>
                            </div>
                          )}
                        </div>
                      )}


                      {/* Progress indicator if running */}
                      {isRunning && agent.progress > 0 && (
                        <div className="mb-3">
                          <div className="flex justify-between text-[10px] text-app-text-light mb-1">
                            <span className="truncate max-w-[180px]">{agent.progress_message || 'Processing...'}</span>
                            <span className={`font-bold text-${statusColor}-600`}>{agent.progress}%</span>
                          </div>
                          <div className="w-full bg-app-bg-muted rounded-full h-1.5 overflow-hidden">
                            <div className={`bg-gradient-to-r ${accentColor} h-1.5 rounded-full transition-all duration-1000 ease-out`} style={{ width: `${agent.progress}%` }}></div>
                          </div>
                        </div>
                      )}

                      {/* Additional Details */}
                      {agent.progress_message && !isRunning && (
                        <div className="mt-3 pt-3 border-t border-app-border-light/30">
                          <p className="text-sm text-app-text-muted flex items-center">
                            <Activity className="w-3 h-3 mr-2" />
                            {agent.progress_message}
                          </p>
                        </div>
                      )}

                      {/* Last Run Info */}
                      {agent.last_run && (
                        <div className="mt-2 text-xs text-app-text-muted flex items-center">
                          <Clock className="w-3 h-3 mr-1" />
                          Last run: {new Date(agent.last_run).toLocaleString('en-IN')}
                        </div>
                      )}
                    </div>
                  );
                })
              ) : (
                <div className="col-span-full flex flex-col items-center justify-center py-20 text-app-text-muted">
                  <Users className="w-16 h-16 mb-4 opacity-30 animate-bounce" />
                  <p className="text-lg font-bold">No agents available</p>
                  <p className="text-sm mt-1 max-w-sm text-center">
                    {filter === 'shared' && 'No Development custom agents found'}
                    {filter === 'dedicated' && 'No Testing custom agents found'}
                    {filter === 'all' && 'Custom agents will appear here once configured and uploaded'}
                  </p>
                </div>
              )}
            </div>
          )}
        </div>

      {/* Add Agent Modal */}
      {showAddAgentModal && (
        <div className="fixed inset-0 z-[300] flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="relative w-full max-w-5xl xl:max-w-6xl bg-app-bg-card border border-app-border/80 rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh] transition-all duration-300 animate-in zoom-in-95 duration-200">
            
            {/* Top accent bar */}
            <div className={`absolute top-0 left-0 right-0 h-1 bg-gradient-to-r ${
              editingAgentId
                ? 'from-amber-400 via-orange-500 to-red-500'
                : isConfiguringTemplate 
                  ? 'from-emerald-400 via-teal-500 to-indigo-500' 
                  : 'from-app-primary via-blue-500 to-cyan-500'
            }`}></div>
            
            {/* Header */}
            <div className="px-6 py-3.5 sm:py-4 flex-shrink-0 border-b border-app-border-light/50 bg-app-bg-card/70 backdrop-blur-sm flex flex-col md:flex-row md:items-center justify-between gap-3">
              <div className="min-w-0 flex-1">
                <h3 className="text-base sm:text-lg font-bold text-app-text-main flex items-center gap-2 mb-0.5">
                  {editingAgentId ? (
                    <>
                      <Bot className="w-5 h-5 text-amber-400" />
                      <span>Edit Custom Agent</span>
                    </>
                  ) : isConfiguringTemplate ? (
                    <>
                      <Bot className="w-5 h-5 text-emerald-400" />
                      <span>Configure Agent Template</span>
                    </>
                  ) : (
                    <>
                      <Bot className="w-5 h-5 text-app-primary" />
                      <span>Add Custom Agent</span>
                    </>
                  )}
                </h3>
                <p className="text-xs text-app-text-muted">
                  {editingAgentId 
                    ? 'Modify the custom agent configuration, skills, attached AI model, and authorized tools.'
                    : isConfiguringTemplate 
                      ? 'Customize the template instructions and authorized sandbox tools before deploying.'
                      : 'Configure a dynamic custom agent with specialized skills and container sandbox tools.'
                  }
                </p>
              </div>

              {/* Parallel to right of header: AI Engine Dropdown & Close */}
              <div className="flex items-center gap-3 shrink-0 self-end md:self-auto">
                <div className="flex items-center gap-2 px-3 py-1.5 rounded-xl border border-app-border-light bg-app-bg-page/80 shadow-2xs">
                  <div className="flex items-center gap-1.5 text-[11px] font-semibold text-app-text-main shrink-0">
                    <Sparkles className="w-3.5 h-3.5 text-amber-400" />
                    <span className="hidden sm:inline">AI Engine (LLM):</span>
                    <span className="sm:hidden">AI:</span>
                  </div>
                  <div className="relative">
                    <select
                      value={selectedModel || 'claude'}
                      onChange={(e) => setSelectedModel(e.target.value)}
                      disabled={addingAgent}
                      className="px-1 pr-5 py-1 bg-transparent border-0 text-xs font-semibold text-app-text-main focus:outline-none cursor-pointer appearance-none"
                    >
                      {(availableModelsList || DEFAULT_MODELS_CATALOG).map((model) => (
                        <option
                          key={model.id}
                          value={model.id}
                          className="bg-app-bg-card text-app-text-main py-1"
                        >
                          {sanitizeModelName(model.name, model.id)} ({model.provider || 'AI Engine'})
                        </option>
                      ))}
                    </select>
                    <ChevronDown className="w-3.5 h-3.5 text-app-text-muted pointer-events-none absolute right-0.5 top-1/2 -translate-y-1/2" />
                  </div>
                </div>

                <button
                  type="button"
                  onClick={() => {
                    setShowAddAgentModal(false);
                    setIsConfiguringTemplate(false);
                    setEditingAgentId(null);
                    setNewAgentName('');
                    setSkillsContent('');
                    setSkillsFileName('');
                    setNewAgentFace('');
                    setNewAgentTags('');
                    setSelectedTools(['filesystem', 'git', 'terminal', 'build_tool']);
                    setSelectedModel('claude');
                    setAddAgentError('');
                  }}
                  className="p-1.5 -mr-1 rounded-xl text-app-text-muted hover:text-app-text-main hover:bg-app-bg-muted transition-colors cursor-pointer"
                  title="Close"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>
            </div>

            {/* Form */}
            <form onSubmit={handleAddAgentSubmit} className="flex-1 flex flex-col min-h-0">
              {/* Scrollable Fields area with hidden scrollbar */}
              <div className="flex-1 overflow-y-auto p-5 sm:p-6 no-scrollbar">
                <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
                  
                  {/* Left Column: Top Identity and Spacious Prompt Workspace */}
                  <div className="lg:col-span-6 flex flex-col space-y-3.5">
                    {/* Identity Details Card: Name & Avatar */}
                    <div className="p-3 rounded-xl border border-app-border-light/80 bg-app-bg-card/70 backdrop-blur-sm">
                      <div className="flex items-center gap-3">
                        {/* Avatar */}
                        <div className="relative group shrink-0">
                          {newAgentFace ? (
                            <div className="relative w-11 h-11 rounded-xl border border-app-border overflow-hidden bg-app-bg-muted shadow-xs">
                              <img src={newAgentFace} alt="Avatar" className="w-full h-full object-cover" />
                              <button
                                type="button"
                                onClick={() => setNewAgentFace('')}
                                className="absolute inset-0 bg-black/60 opacity-0 group-hover:opacity-100 flex items-center justify-center text-white text-[10px] font-bold transition-opacity"
                              >
                                Remove
                              </button>
                            </div>
                          ) : (
                            <label
                              htmlFor="agent-face-upload"
                              className="w-11 h-11 rounded-xl border border-dashed border-app-border-light hover:border-app-primary bg-app-bg-muted/40 hover:bg-app-bg-muted flex flex-col items-center justify-center text-app-text-muted hover:text-app-primary cursor-pointer transition-all shadow-xs"
                              title="Upload avatar"
                            >
                              <Users className="w-4 h-4 mb-0.5" />
                              <span className="text-[8px] font-medium">+Icon</span>
                            </label>
                          )}
                          <input
                            type="file"
                            accept="image/*"
                            id="agent-face-upload"
                            onChange={handleFaceChange}
                            className="hidden"
                            disabled={addingAgent}
                          />
                        </div>

                        {/* Name Input */}
                        <div className="flex-1 min-w-0">
                          <label className="block text-[11px] font-semibold text-app-text-main mb-1">
                            Agent Name <span className="text-red-400">*</span>
                          </label>
                          <input
                            type="text"
                            value={newAgentName}
                            onChange={(e) => setNewAgentName(e.target.value)}
                            placeholder="e.g. Frontend Architect, QA Specialist"
                            className="w-full px-3 py-2 bg-app-bg-page/80 border border-app-border-light rounded-xl text-xs font-semibold text-app-text-main focus:outline-none focus:border-app-primary focus:ring-1 focus:ring-app-primary/20 placeholder:font-normal placeholder:text-app-text-muted/50 transition-all"
                            disabled={addingAgent}
                            required
                          />
                        </div>
                      </div>
                    </div>

                    {/* Agent Skills / Prompt Editor (Spacious Workspace) */}
                    <div className="flex-1 flex flex-col p-4 rounded-xl border border-app-border-light/80 bg-app-bg-card/70 backdrop-blur-sm min-h-[440px]">
                      {/* Editor Toolbar Header */}
                      <div className="flex items-center justify-between gap-2 pb-3 mb-3 border-b border-app-border-light/50 shrink-0">
                        <div className="flex items-center gap-1 bg-app-bg-muted/50 p-0.5 rounded-lg border border-app-border-light/60">
                          <button
                            type="button"
                            onClick={() => setSkillsTab('editor')}
                            className={`px-3 py-1 rounded-md text-[11px] font-semibold transition-all cursor-pointer flex items-center gap-1.5 ${
                              skillsTab === 'editor'
                                ? 'bg-app-bg-card text-app-text-main shadow-xs'
                                : 'text-app-text-muted hover:text-app-text-main'
                            }`}
                          >
                            <Code className="w-3.5 h-3.5 text-app-primary" />
                            <span>Prompt Editor</span>
                          </button>
                          <button
                            type="button"
                            onClick={() => setSkillsTab('upload')}
                            className={`px-3 py-1 rounded-md text-[11px] font-semibold transition-all cursor-pointer flex items-center gap-1.5 ${
                              skillsTab === 'upload'
                                ? 'bg-app-bg-card text-app-text-main shadow-xs'
                                : 'text-app-text-muted hover:text-app-text-main'
                            }`}
                          >
                            <Upload className="w-3.5 h-3.5 text-app-primary" />
                            <span>Upload File (.md)</span>
                          </button>
                        </div>

                        <div className="flex items-center gap-2">
                          {!skillsContent && (
                            <button
                              type="button"
                              onClick={() => {
                                setSkillsContent(`# ${newAgentName.trim() || 'Custom'} Agent System Prompt\n\n## Role & Objective\nYou are an autonomous agent specialized in requirements analysis, code development, and quality verification.\n\n## Working Rules\n1. Review existing code and architectural patterns before modifying\n2. Maintain backward compatibility and cleanly isolate changes\n3. Execute test suites and verify compilation after code modifications\n\n## Output Format\nProvide clear git diffs and summarize verified changes.`);
                              }}
                              className="px-2.5 py-1 rounded-md text-[10px] font-medium text-app-primary bg-app-primary/10 hover:bg-app-primary/20 transition-all cursor-pointer flex items-center gap-1 border border-app-primary/20"
                              title="Insert standard agent prompt template"
                            >
                              <Sparkles className="w-3 h-3" />
                              <span>Starter Template</span>
                            </button>
                          )}

                          {skillsContent && (
                            <button
                              type="button"
                              onClick={() => {
                                setSkillsContent('');
                                setSkillsFileName('');
                              }}
                              className="text-[10px] font-semibold text-red-400 hover:text-red-300 transition-colors flex items-center gap-1 cursor-pointer px-2 py-1 rounded-md hover:bg-red-500/10"
                              title="Clear editor contents"
                            >
                              <Trash2 className="w-3 h-3" />
                              <span>Reset</span>
                            </button>
                          )}
                        </div>
                      </div>

                      {/* Editor Body */}
                      {skillsTab === 'editor' ? (
                        <div className="flex-1 flex flex-col min-h-0">
                          {skillsFileName && (
                            <div className="flex items-center justify-between px-3 py-1 mb-2 rounded-lg bg-app-bg-page border border-app-border-light/60 text-[10px] text-app-text-muted font-mono shrink-0">
                              <span className="truncate max-w-[240px]">📄 {skillsFileName}</span>
                              <span className="text-emerald-500 font-bold uppercase tracking-wider text-[8px] bg-emerald-500/10 px-1.5 py-0.5 rounded border border-emerald-500/20">Loaded</span>
                            </div>
                          )}
                          <div className="flex-1 relative flex flex-col min-h-0">
                            <textarea
                              value={skillsContent}
                              onChange={(e) => setSkillsContent(e.target.value)}
                              placeholder={`# Agent Role & Instructions\n\n## Core Role\nYou are a specialized AI agent responsible for analyzing requirements, implementing features, and verifying functionality.\n\n## Guidelines\n1. Always review existing code before writing\n2. Run tests to confirm changes`}
                              className="w-full flex-1 p-3.5 bg-app-bg-page/90 dark:bg-black/25 border border-app-border-light rounded-xl font-mono text-xs text-app-text-main leading-relaxed focus:outline-none focus:border-app-primary focus:ring-1 focus:ring-app-primary/20 transition-all resize-none no-scrollbar placeholder:text-app-text-muted/40 min-h-[340px]"
                              disabled={addingAgent}
                              required
                            />
                          </div>

                          {/* Footer stats bar */}
                          <div className="mt-2.5 flex items-center justify-between text-[10px] text-app-text-muted shrink-0 font-mono">
                            <div className="flex items-center gap-2">
                              <span>System Prompt</span>
                              <span>•</span>
                              <span className="text-app-text-main font-semibold">
                                {skillsContent ? skillsContent.split('\n').length : 0} lines
                              </span>
                              <span>•</span>
                              <span className="text-app-text-main font-semibold">
                                {skillsContent ? skillsContent.length.toLocaleString() : 0} chars
                              </span>
                            </div>
                            <span className="text-[10px] text-emerald-400 font-sans font-medium flex items-center gap-1">
                              <ShieldCheck className="w-3 h-3 text-emerald-400" />
                              <span>Container Injected</span>
                            </span>
                          </div>
                        </div>
                      ) : (
                        <div className="flex-1 flex flex-col items-center justify-center min-h-[340px] border-2 border-dashed border-app-border-light hover:border-app-primary/60 rounded-xl cursor-pointer bg-app-bg-page/40 hover:bg-app-bg-muted/20 transition-all p-6 group">
                          <input
                            type="file"
                            accept=".md"
                            id="skills-file-upload-tab"
                            onChange={handleFileChange}
                            className="hidden"
                            disabled={addingAgent}
                          />
                          <label
                            htmlFor="skills-file-upload-tab"
                            className="flex flex-col items-center justify-center w-full h-full cursor-pointer text-center"
                          >
                            <div className="w-12 h-12 rounded-2xl bg-app-primary/10 flex items-center justify-center mb-3 group-hover:scale-110 transition-transform">
                              <Upload className="w-6 h-6 text-app-primary" />
                            </div>
                            <p className="text-xs font-bold text-app-text-main">
                              Select or drop a Markdown file (.md)
                            </p>
                            <p className="text-[11px] text-app-text-muted mt-1 max-w-xs">
                              Upload any existing skill prompt or role specification to immediately populate the editor.
                            </p>
                            <span className="mt-3 px-3 py-1.5 rounded-lg text-[10px] font-semibold bg-app-bg-card border border-app-border-light text-app-text-main group-hover:border-app-primary transition-colors">
                              Browse Files
                            </span>
                          </label>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Right Column: Authorized Sandbox Tools & Capabilities */}
                  <div className="lg:col-span-6 flex flex-col">
                    <div className="p-4 rounded-xl border border-app-border-light/80 bg-app-bg-card/70 backdrop-blur-sm flex-1 flex flex-col">
                      <div className="flex items-center justify-between mb-1.5">
                        <label className="text-xs font-semibold text-app-text-main flex items-center gap-1.5">
                          <Wrench className="w-3.5 h-3.5 text-app-primary" />
                          <span>Authorized Sandbox Tools</span>
                        </label>
                        <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-app-primary/10 text-app-primary font-bold border border-app-primary/20 flex items-center gap-1">
                          <span className="w-1.5 h-1.5 rounded-full bg-app-primary animate-pulse" />
                          <span>{selectedTools.length} of {(availableToolsList || DEFAULT_TOOLS_CATALOG).length} enabled</span>
                        </span>
                      </div>
                      <p className="text-[11px] text-app-text-muted mb-2.5">
                        Configure which container runtime tools and APIs this agent is authorized to leverage.
                      </p>

                      {/* Tool Presets */}
                      <div className="flex flex-wrap gap-1.5 mb-3">
                        <button
                          type="button"
                          onClick={() => setSelectedTools(['filesystem', 'git', 'terminal', 'build_tool', 'database_tools'])}
                          className="px-2.5 py-1 rounded-lg text-[10px] font-semibold bg-app-bg-page hover:bg-app-bg-hover text-app-text-main border border-app-border-light transition-all cursor-pointer"
                        >
                          Dev Preset
                        </button>
                        <button
                          type="button"
                          onClick={() => setSelectedTools(['terminal', 'test_runner', 'visual_qa', 'filesystem'])}
                          className="px-2.5 py-1 rounded-lg text-[10px] font-semibold bg-app-bg-page hover:bg-app-bg-hover text-app-text-main border border-app-border-light transition-all cursor-pointer"
                        >
                          QA Preset
                        </button>
                        <button
                          type="button"
                          onClick={() => setSelectedTools((availableToolsList || DEFAULT_TOOLS_CATALOG).map(t => t.id))}
                          className="px-2.5 py-1 rounded-lg text-[10px] font-semibold bg-app-primary/10 hover:bg-app-primary/20 text-app-primary border border-app-primary/20 transition-all cursor-pointer"
                        >
                          Select All
                        </button>
                        <button
                          type="button"
                          onClick={() => setSelectedTools([])}
                          className="px-2.5 py-1 rounded-lg text-[10px] font-semibold bg-app-bg-page hover:bg-red-500/10 text-app-text-muted hover:text-red-400 border border-app-border-light transition-all cursor-pointer"
                        >
                          Clear
                        </button>
                      </div>

                      {/* Tool Cards Scroll Grid with hidden scrollbar */}
                      <div className="space-y-2.5 overflow-y-auto max-h-[460px] pr-1 no-scrollbar">
                        {(availableToolsList || DEFAULT_TOOLS_CATALOG).map((tool) => {
                          const isSelected = selectedTools.includes(tool.id);
                          return (
                            <div
                              key={tool.id}
                              onClick={() => {
                                if (isSelected) {
                                  setSelectedTools(selectedTools.filter(id => id !== tool.id));
                                } else {
                                  setSelectedTools([...selectedTools, tool.id]);
                                }
                              }}
                              className={`p-3 rounded-xl border transition-all duration-150 cursor-pointer flex items-start gap-3 select-none ${
                                isSelected
                                  ? 'bg-blue-500/5 dark:bg-blue-500/10 border-blue-500/60 shadow-2xs ring-1 ring-blue-500/20'
                                  : 'bg-app-bg-page/70 border-app-border-light/70 hover:border-app-border hover:bg-app-bg-muted/40'
                              }`}
                            >
                              {/* Custom Styled Checkbox */}
                              <div className={`w-4 h-4 rounded-md flex items-center justify-center mt-0.5 transition-all shrink-0 ${
                                isSelected
                                  ? 'bg-blue-500 text-white shadow-2xs'
                                  : 'border border-app-border-light bg-app-bg-page'
                              }`}>
                                {isSelected && <Check className="w-2.5 h-2.5 stroke-[3]" />}
                              </div>

                              <div className="flex-1 min-w-0">
                                <div className="flex items-center justify-between gap-1 mb-1">
                                  <span className="text-xs font-bold text-app-text-main flex items-center gap-1.5 truncate">
                                    <span className="p-1 rounded-lg bg-app-bg-muted border border-app-border-light/50">
                                      {getToolIcon(tool.icon, 'w-3.5 h-3.5')}
                                    </span>
                                    <span>{tool.name}</span>
                                  </span>
                                  <span className="text-[9px] font-mono px-2 py-0.5 rounded-full bg-app-bg-muted text-app-text-muted border border-app-border-light/60 shrink-0">
                                    {tool.category}
                                  </span>
                                </div>
                                <p className="text-[11px] text-app-text-muted leading-relaxed mb-2">
                                  {tool.description}
                                </p>
                                {tool.capabilities && tool.capabilities.length > 0 && (
                                  <div className="pt-2 border-t border-app-border-light/40">
                                    <div className="text-[9px] uppercase tracking-wider font-semibold text-app-text-muted/70 mb-1.5">
                                      Authorized Capabilities:
                                    </div>
                                    <div className="flex flex-wrap gap-1.5">
                                      {tool.capabilities.map((cap, i) => (
                                        <span
                                          key={i}
                                          className={`text-[10px] font-medium px-2 py-0.5 rounded-full border transition-colors ${
                                            isSelected
                                              ? 'bg-app-bg-card border-app-primary/30 text-app-text-main shadow-2xs'
                                              : 'bg-app-bg-muted/60 border-app-border-light text-app-text-muted'
                                          }`}
                                        >
                                          {formatCapability(cap)}
                                        </span>
                                      ))}
                                    </div>
                                  </div>
                                )}
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  </div>

                </div>

                {addAgentError && (
                  <div className="mt-4 p-3 text-xs rounded-xl bg-app-status-error/10 border border-app-status-error/20 text-red-400 animate-in fade-in duration-200">
                    {addAgentError}
                  </div>
                )}
              </div>

              {/* Actions Footer */}
              <div className="px-6 py-4 border-t border-app-border-light/60 flex items-center justify-end gap-2.5 flex-shrink-0 bg-app-bg-card/70 backdrop-blur-sm">
                <button
                  type="button"
                  onClick={() => {
                    setShowAddAgentModal(false);
                    setIsConfiguringTemplate(false);
                    setEditingAgentId(null);
                    setNewAgentName('');
                    setSkillsContent('');
                    setSkillsFileName('');
                    setNewAgentFace('');
                    setNewAgentTags('');
                    setSelectedTools(['filesystem', 'git', 'terminal', 'build_tool']);
                    setSelectedModel('claude');
                    setAddAgentError('');
                  }}
                  disabled={addingAgent}
                  className="px-4 py-2 text-xs font-semibold text-app-text-muted hover:text-app-text-main bg-app-bg-muted/60 hover:bg-app-bg-muted rounded-xl transition-all cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={addingAgent || !newAgentName.trim() || !skillsContent}
                  className="flex items-center gap-1.5 px-5 py-2 text-xs font-semibold text-white bg-gradient-to-r from-blue-600 via-indigo-600 to-blue-700 hover:from-blue-500 hover:to-indigo-600 disabled:opacity-40 disabled:cursor-not-allowed rounded-xl shadow-sm hover:shadow transition-all cursor-pointer"
                >
                  {addingAgent ? (
                    <>
                      <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                      <span>{editingAgentId ? 'Saving...' : isConfiguringTemplate ? 'Deploying...' : 'Adding...'}</span>
                    </>
                  ) : (
                    <>
                      {editingAgentId ? (
                        <>
                          <CheckCircle className="w-3.5 h-3.5" />
                          <span>Save Changes</span>
                        </>
                      ) : isConfiguringTemplate ? (
                        <>
                          <Plus className="w-3.5 h-3.5" />
                          <span>Create from Template</span>
                        </>
                      ) : (
                        <>
                          <Plus className="w-3.5 h-3.5" />
                          <span>Create Agent</span>
                        </>
                      )}
                    </>
                  )}
                </button>
              </div>

            </form>
          </div>
        </div>
      )}

      {/* Custom Capacity Request Modal */}
      <RequestCapacityModal
        isOpen={showRequestModal}
        onClose={() => setShowRequestModal(false)}
        projects={projects}
        isOrgAdmin={isOrgAdmin}
        onSuccess={() => {
          showToast(
            isOrgAdmin
              ? 'Capacity Increase Request submitted to Super Admin!'
              : 'Project Agent Capacity Request submitted to Org Admin!',
            'success'
          );
          fetchQuota();
          fetchProjectRequests();
        }}
      />

      {/* Floating Toast Notification */}
      {toast.message && (
        <div className="fixed top-20 right-6 z-[9999] pointer-events-auto bg-app-bg-card border border-app-border/80 shadow-2xl rounded-2xl p-4 min-w-[340px] max-w-sm flex items-center gap-3.5 animate-slide-in-right transition-colors duration-200">
          <div className={`flex-shrink-0 p-2 rounded-xl ${
            toast.type === 'success' ? 'bg-emerald-500/10 text-emerald-500 dark:bg-emerald-500/20 dark:text-emerald-400' :
            toast.type === 'error' ? 'bg-rose-500/10 text-rose-500 dark:bg-rose-500/20 dark:text-rose-400' :
            'bg-app-primary/10 text-app-primary dark:bg-app-primary/20 dark:text-blue-400'
          }`}>
            {toast.type === 'success' ? (
              <CheckCircle className="w-5 h-5 text-current" />
            ) : toast.type === 'error' ? (
              <AlertCircle className="w-5 h-5 text-current" />
            ) : (
              <Bot className="w-5 h-5 text-current" />
            )}
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-xs font-bold text-app-text-main">
              {toast.type === 'success' ? 'Success' : toast.type === 'error' ? 'Error' : 'Notification'}
            </p>
            <p className="text-[11px] text-app-text-muted mt-0.5 leading-relaxed">{toast.message}</p>
          </div>
          <button
            onClick={hideToast}
            className="text-app-text-light hover:text-app-text-main transition-colors flex-shrink-0 p-1.5 rounded-lg hover:bg-app-bg-hover cursor-pointer"
            title="Dismiss"
          >
            <span className="text-lg leading-none">&times;</span>
          </button>
        </div>
      )}

    </div>
  );
}
