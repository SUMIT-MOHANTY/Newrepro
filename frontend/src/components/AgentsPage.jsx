import React, { useState, useEffect, useMemo, useCallback, useRef } from 'react';
import { Users, Trash2, Edit, Activity, Clock, CheckCircle, AlertCircle, RefreshCw, Filter, Server, Database, GitBranch, Bot, Globe, Plus, Upload, Code, Coffee, Zap, Triangle, Hash, Link2, Terminal, Cpu, Workflow, Shield, ShieldCheck, Layers, Building2, Send } from 'lucide-react';
import { API_ENDPOINTS } from '../config';
import RequestCapacityModal from './RequestCapacityModal';

import { getNeutralAgentName, getNeutralAgentLabel } from '../utils/agentNames';
import kaktoxLogo from '../assets/Kaktox.png';
import nModLogo from '../assets/N-Mod-icon.png';
import masterLogo from '../assets/logo1.png';
import cloudIcon from '../assets/cloud-icon.png';

const PREDEFINED_TEMPLATES = [
  {
    name: 'Frontend Developer',
    tags: 'React, Vite, CSS Modules, Tailwind CSS, Lucide Icons, UI Components',
    specialization: 'Development',
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
    description: 'Brownfield Go agent. Reads existing handlers, models, and routes, then makes targeted additions to Go microservices and REST APIs.',
    skills: `# Go Developer Agent Skill\n\n## Role\nYou are a specialized Brownfield Go Developer Agent. You work on EXISTING Go applications — reading current code before making any changes.\n\n## Tech Stack\n- Language: Go 1.19+\n- Framework: Gin / Echo / Fiber / net/http\n- ORM: GORM / sqlx\n- Package Manager: Go Modules (go.mod)\n- Testing: testing package, testify\n- Protocols: REST / gRPC\n\n## Brownfield Working Rules\n1. ALWAYS read the existing handler/struct: cat /workspace/internal/handlers/existing.go\n2. Follow the existing package structure — do NOT create new top-level packages without reason\n3. Add new route handlers as functions in existing handler files or new files in the same package\n4. Register new routes in the existing router setup (e.g., router.GET("/new", handler))\n5. New structs go in the existing models/ or types/ package\n6. Run: go test ./... after changes\n\n## Core Responsibilities\n1. Handlers: Add new HTTP handler functions following the existing (c *gin.Context) pattern\n2. Routes: Register in the existing router group setup\n3. Models/Structs: Add new GORM model structs with proper tags\n4. Services: Add business logic to existing service structs\n5. Middleware: Add new gin.HandlerFunc middleware in the existing middleware chain`,
    icon: Triangle,
    accentColor: 'from-cyan-400 to-blue-500',
    colorClass: 'text-cyan-400 bg-cyan-500/10 border-cyan-500/20 hover:border-cyan-500/40 hover:text-cyan-300'
  },
  {
    name: 'Jira MCP Agent',
    isMcp: true,
    tags: 'Jira, Project Management, Issue Tracking, MCP Server, Integration',
    specialization: 'Integration',
    description: 'MCP agent that connects to Jira via Model Context Protocol. It can view, create, and transition Jira issues directly.',
    skills: `# Jira MCP Agent Skill\n\n## Role\nYou are an integration agent equipped with the Jira Model Context Protocol (MCP) server. You connect to Jira to view, create, update, and search for issues, epics, and sprints.\n\n## MCP Integration Link\n- Official Registry: [Jira MCP Server GitHub](https://github.com/modelcontextprotocol/servers/tree/main/src/jira)\n- Package Name: \`@modelcontextprotocol/server-jira\`\n\n## Setup Configuration\nEnsure your client configuration defines the server:\n\`\`\`json\n{\n  "mcpServers": {\n    "jira": {\n      "command": "npx",\n      "args": ["-y", "@modelcontextprotocol/server-jira"],\n      "env": {\n        "JIRA_API_TOKEN": "<YOUR_JIRA_API_TOKEN>",\n        "JIRA_EMAIL": "<YOUR_JIRA_EMAIL>",\n        "JIRA_HOST": "<YOUR_JIRA_HOST>"\n      }\n    }\n  }\n}\n\`\`\`\n\n## Core Responsibilities\n1. Search Issues: Find Jira tickets matching specific queries, assignees, or statuses.\n2. Create & Update: Initialize tickets, add comments, log work, and transition states (e.g. To Do -> In Progress -> Done).\n3. Backlog Management: Fetch backlog tasks, summarize sprint progress, and highlight blockages.`,
    icon: Workflow,
    accentColor: 'from-blue-500 to-cyan-500',
    colorClass: 'text-blue-400 bg-blue-500/10 border-blue-500/20 hover:border-blue-500/40 hover:text-blue-300'
  },
  {
    name: 'GitHub MCP Agent',
    isMcp: true,
    tags: 'GitHub, Git, PRs, Code Reviews, MCP Server, Integration',
    specialization: 'Integration',
    description: 'MCP agent that connects to GitHub repository APIs via Model Context Protocol. It handles PR reviews, issue management, and file contents.',
    skills: `# GitHub MCP Agent Skill\n\n## Role\nYou are an integration agent equipped with the GitHub Model Context Protocol (MCP) server. You connect to GitHub to manage issues, pull requests, files, and branches.\n\n## MCP Integration Link\n- Official Registry: [GitHub MCP Server GitHub](https://github.com/modelcontextprotocol/servers/tree/main/src/github)\n- Package Name: \`@modelcontextprotocol/server-github\`\n\n## Setup Configuration\nEnsure your client configuration defines the server:\n\`\`\`json\n{\n  "mcpServers": {\n    "github": {\n      "command": "npx",\n      "args": ["-y", "@modelcontextprotocol/server-github"],\n      "env": {\n        "GITHUB_PERSONAL_ACCESS_TOKEN": "<YOUR_GITHUB_TOKEN>"\n      }\n    }\n  }\n}\n\`\`\`\n\n## Core Responsibilities\n1. PR Automation: Create pull requests, list reviews, merge code, and add comments.\n2. Issue Management: File bug reports, list repository issues, and organize labels/milestones.\n3. Code Inspection: Search repository files, retrieve code contents, and check commit histories.`,
    icon: GitBranch,
    accentColor: 'from-slate-400 to-slate-600',
    colorClass: 'text-slate-400 bg-slate-500/10 border-slate-500/20 hover:border-slate-500/40 hover:text-slate-300'
  },
  {
    name: 'Slack MCP Agent',
    isMcp: true,
    tags: 'Slack, Chat, Notifications, Team Sync, MCP Server, Integration',
    specialization: 'Integration',
    description: 'MCP agent that connects to Slack via Model Context Protocol. It posts notifications, reads channel history, and handles communication workflows.',
    skills: `# Slack MCP Agent Skill\n\n## Role\nYou are an integration agent equipped with the Slack Model Context Protocol (MCP) server. You interface with Slack to coordinate team communication and notifications.\n\n## MCP Integration Link\n- Official Registry: [Slack MCP Server GitHub](https://github.com/modelcontextprotocol/servers/tree/main/src/slack)\n- Package Name: \`@modelcontextprotocol/server-slack\`\n\n## Setup Configuration\nEnsure your client configuration defines the server:\n\`\`\`json\n{\n  "mcpServers": {\n    "slack": {\n      "command": "npx",\n      "args": ["-y", "@modelcontextprotocol/server-slack"],\n      "env": {\n        "SLACK_BOT_TOKEN": "<YOUR_SLACK_BOT_TOKEN>"\n      }\n    }\n  }\n}\n\`\`\`\n\n## Core Responsibilities\n1. Post Messages: Send rich text or blocks to public/private channels or direct messages.\n2. Monitor Channels: Retrieve history, search conversations, and summarize thread contexts.\n3. Status Sync: Set active status, update profiles, and automate reminders.`,
    icon: Cpu,
    accentColor: 'from-pink-500 to-purple-600',
    colorClass: 'text-pink-400 bg-pink-500/10 border-pink-500/20 hover:border-pink-500/40 hover:text-pink-300'
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
  const [showMcpHelper, setShowMcpHelper] = useState(false);

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
          tags: newAgentTags.trim() || null,
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
          tags: tmpl.tags
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
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              {/* ── Left Card: Shared Agents in Use ── */}
              <div className="rounded-xl border border-emerald-500/25 bg-gradient-to-br from-emerald-500/10 to-teal-500/5 p-4 shadow-sm hover:shadow-lg hover:border-emerald-500/40 transition-all duration-300 flex flex-col justify-between">
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <div className="p-1.5 rounded-lg bg-emerald-500/20 text-emerald-400">
                        <Bot className="w-4 h-4" />
                      </div>
                      <span className="text-sm font-bold text-app-text-main">Shared Agents</span>
                    </div>
                    <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                      Org-Wide Pool
                    </span>
                  </div>

                  <div className="mt-3 flex items-baseline justify-between">
                    <span className="text-3xl font-black text-emerald-400">{quotaSummary ? quotaSummary.sharedUsed : sharedAgents.length}</span>
                    <span className="text-xs font-semibold text-app-text-muted">Active in Projects</span>
                  </div>
                </div>

                <div className="mt-4 pt-2 border-t border-app-border-light/30 flex items-center justify-between text-[11px] text-app-text-muted">
                  <span>Allocation Mode:</span>
                  <span className="font-bold text-emerald-300">Floating / Multi-Project</span>
                </div>
              </div>

              {/* ── Middle Card: Dedicated Agents in Use ── */}
              <div className="rounded-xl border border-purple-500/25 bg-gradient-to-br from-purple-500/10 to-pink-500/5 p-4 shadow-sm hover:shadow-lg hover:border-purple-500/40 transition-all duration-300 flex flex-col justify-between">
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <div className="p-1.5 rounded-lg bg-purple-500/20 text-purple-400">
                        <Activity className="w-4 h-4" />
                      </div>
                      <span className="text-sm font-bold text-app-text-main">Dedicated Agents</span>
                    </div>
                    <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-purple-500/20 text-purple-300 border border-purple-500/30">
                      Project-Bound
                    </span>
                  </div>

                  <div className="mt-3 flex items-baseline justify-between">
                    <span className="text-3xl font-black text-purple-400">{quotaSummary ? quotaSummary.dedicatedUsed : dedicatedAgents.length}</span>
                    <span className="text-xs font-semibold text-app-text-muted">Active in Projects</span>
                  </div>
                </div>

                <div className="mt-4 pt-2 border-t border-app-border-light/30 flex items-center justify-between text-[11px] text-app-text-muted">
                  <span>Allocation Mode:</span>
                  <span className="font-bold text-purple-300">Dedicated Home Project</span>
                </div>
              </div>

              {/* ── Right Card: Capacity Governance Summary & Request Trigger ── */}
              <div className="rounded-xl border border-blue-500/25 bg-gradient-to-br from-blue-500/10 to-indigo-500/5 p-4 shadow-sm hover:shadow-lg hover:border-blue-500/40 transition-all duration-300 flex flex-col justify-between">
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <div className="p-1.5 rounded-lg bg-blue-500/20 text-blue-400">
                        <Server className="w-4 h-4" />
                      </div>
                      <span className="text-sm font-bold text-app-text-main">Capacity Governance</span>
                    </div>
                    <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-purple-500/20 text-purple-300 border border-purple-500/30">
                      Super Admin Approved
                    </span>
                  </div>

                  <div className="space-y-2 pt-1 border-t border-app-border-light/30">
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-app-text-muted">Total Super Admin Cap:</span>
                      <span className="font-extrabold text-purple-400">{quota?.max_agent_capacity || 10} Max Agents</span>
                    </div>
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-app-text-muted">Currently Active Agents:</span>
                      <span className="font-bold text-emerald-400">
                        {quotaSummary.sharedUsed + quotaSummary.dedicatedUsed} Active
                      </span>
                    </div>
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-app-text-muted">Available Capacity Slots:</span>
                      <span className="font-bold text-blue-400">
                        {Math.max(0, (quota?.max_agent_capacity || 10) - (quotaSummary.sharedUsed + quotaSummary.dedicatedUsed))} Slots
                      </span>
                    </div>
                  </div>
                </div>

                <div className="mt-4">
                  <button
                    type="button"
                    onClick={() => setShowRequestModal(true)}
                    className="w-full py-2 px-3 rounded-xl bg-purple-600 hover:bg-purple-500 text-white text-xs font-bold transition-all flex items-center justify-center gap-2 shadow-lg shadow-purple-600/30"
                  >
                    <Shield className="w-4 h-4" />
                    <span>{isOrgAdmin ? 'Request Capacity Increase (Super Admin)' : 'Notify Org Admin for Agent Capacity'}</span>
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
              Samples ({PREDEFINED_TEMPLATES.filter(t => !t.isMcp).length})
            </button>
            <button
              onClick={() => setFilter('mcp')}
              className={`px-3 py-1 text-sm font-medium rounded-lg transition-colors ${filter === 'mcp'
                ? 'bg-app-primary text-white'
                : 'bg-app-text-label/20 text-app-text-main hover:bg-app-text-label/30'
                }`}
            >
              MCP ({PREDEFINED_TEMPLATES.filter(t => t.isMcp).length})
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
                PREDEFINED_TEMPLATES.filter(tmpl => !tmpl.isMcp).map((tmpl) => {
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
                            <div className="flex items-center gap-1.5">
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
              ) : filter === 'mcp' ? (
                PREDEFINED_TEMPLATES.filter(tmpl => tmpl.isMcp).map((tmpl) => {
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
                          <div className={`w-9 h-9 rounded-lg bg-app-bg-page border flex items-center justify-center shadow-lg text-cyan-500 dark:text-cyan-400 border-cyan-500/20 dark:border-cyan-500/30 bg-cyan-500/10 dark:bg-cyan-500/20`}>
                            <IconComponent className="w-4 h-4 text-current font-bold" />
                          </div>

                          <div>
                            <div className="flex items-center gap-1.5">
                              <h4 className="text-xs font-bold text-app-text-main">
                                {tmpl.name}
                              </h4>
                              <span className="px-1.5 py-0.5 text-[8px] font-bold rounded-full uppercase tracking-wider bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">
                                {tmpl.specialization}
                              </span>
                            </div>
                            <p className="text-[9px] text-app-text-light uppercase tracking-wider font-semibold">MCP Server</p>
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
                            <div className="flex items-center gap-1.5">
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
          <div className={`relative w-full ${isConfiguringTemplate || skillsContent ? 'max-w-3xl' : 'max-w-md'} bg-app-bg-card border border-app-border rounded-xl shadow-2xl overflow-hidden flex flex-col max-h-[85vh] transition-all duration-300 animate-in zoom-in duration-200`}>
            
            {/* Top gradient line */}
            <div className={`absolute top-0 left-0 right-0 h-1 bg-gradient-to-r ${
              editingAgentId
                ? 'from-amber-400 via-orange-500 to-red-500'
                : isConfiguringTemplate 
                  ? 'from-emerald-400 via-teal-500 to-indigo-500' 
                  : 'from-app-primary to-blue-600'
            }`}></div>
            
            {/* Header */}
            <div className="p-6 pb-4 flex-shrink-0 border-b border-app-border-light/40 bg-app-bg-card/50">
              <h3 className="text-lg font-bold text-app-text-main flex items-center gap-2 mb-1">
                {editingAgentId ? (
                  <>
                    <Bot className="w-5 h-5 text-amber-400 animate-pulse" />
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
                  ? 'Modify the custom agent name, tags, face icon, and skills file content.'
                  : isConfiguringTemplate 
                    ? 'Customize the pre-defined template name, tags, and skills before deploying.'
                    : 'Create a custom dynamic agent by providing their name and uploading their skills file.'
                }
              </p>
            </div>


            {/* Form */}
            <form onSubmit={handleAddAgentSubmit} className="flex-1 flex flex-col min-h-0">
              {/* Scrollable Fields area */}
              <div className="flex-1 overflow-y-auto px-6 py-4 scrollbar-thin scrollbar-thumb-app-border">
                <div className={`grid grid-cols-1 ${isConfiguringTemplate || skillsContent ? 'md:grid-cols-2 gap-6' : 'gap-4'} pt-2`}>
                  
                  {/* Left Column: Metadata Inputs */}
                  <div className="space-y-4">
                    <div>
                      <label className="block text-xs font-bold text-app-text-muted uppercase tracking-wider mb-1.5">
                        Agent Name
                      </label>
                      <input
                        type="text"
                        value={newAgentName}
                        onChange={(e) => setNewAgentName(e.target.value)}
                        placeholder="e.g. Frontend Architect, QA Specialist"
                        className="w-full px-3 py-2 bg-app-bg-muted/50 border border-app-border-light rounded-lg text-sm text-app-text-main focus:outline-none focus:border-app-primary placeholder:text-app-text-muted/60 transition-colors"
                        disabled={addingAgent}
                        required
                      />
                    </div>

                    <div>
                      <label className="block text-xs font-bold text-app-text-muted uppercase tracking-wider mb-1.5">
                        Agent Icon / Avatar
                      </label>
                      <div className="flex items-center gap-3">
                        {newAgentFace ? (
                          <div className="relative w-12 h-12 rounded-lg border border-app-border bg-app-bg-muted overflow-hidden shrink-0 group">
                            <img src={newAgentFace} alt="Agent icon preview" className="w-full h-full object-cover" />
                            <button
                              type="button"
                              onClick={() => setNewAgentFace('')}
                              className="absolute inset-0 bg-black/60 opacity-0 group-hover:opacity-100 flex items-center justify-center text-white transition-opacity duration-200"
                            >
                              <span className="text-[10px] font-bold">Remove</span>
                            </button>
                          </div>
                        ) : (
                          <div className="w-12 h-12 rounded-lg border border-dashed border-app-border-light bg-app-bg-muted/30 flex items-center justify-center text-app-text-muted/40 shrink-0">
                            <Users className="w-5 h-5" />
                          </div>
                        )}
                        <div className="flex-1">
                          <input
                            type="file"
                            accept="image/*"
                            id="agent-face-upload"
                            onChange={handleFaceChange}
                            className="hidden"
                            disabled={addingAgent}
                          />
                          <label
                            htmlFor="agent-face-upload"
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold bg-app-bg-muted/70 hover:bg-app-bg-muted border border-app-border-light rounded-lg text-app-text-main cursor-pointer hover:border-app-primary transition-colors"
                          >
                            <Upload className="w-3.5 h-3.5" />
                            Upload Image
                          </label>
                          <p className="text-[10px] text-app-text-muted mt-1">PNG, JPG or SVG</p>
                        </div>
                      </div>
                    </div>

                    <div>
                      <label className="block text-xs font-bold text-app-text-muted uppercase tracking-wider mb-1.5">
                        Specialization Tags
                      </label>
                      <input
                        type="text"
                        value={newAgentTags}
                        onChange={(e) => setNewAgentTags(e.target.value)}
                        placeholder="e.g. React, FastApi, PostgreSQL, Pytest (comma-separated)"
                        className="w-full px-3 py-2 bg-app-bg-muted/50 border border-app-border-light rounded-lg text-sm text-app-text-main focus:outline-none focus:border-app-primary placeholder:text-app-text-muted/60 transition-colors"
                        disabled={addingAgent}
                      />
                      <p className="text-[10px] text-app-text-muted mt-1">Used by Master Agent to match task capabilities.</p>
                    </div>

                    {/* MCP Configuration Helper */}
                    <div className="mt-4 border border-app-border-light/60 rounded-xl bg-app-bg-muted/30 overflow-hidden">
                      <button
                        type="button"
                        onClick={() => setShowMcpHelper(!showMcpHelper)}
                        className="w-full px-4 py-2.5 flex items-center justify-between text-xs font-bold text-app-text-main bg-app-bg-muted/40 hover:bg-app-bg-muted/80 transition-colors border-b border-app-border-light/40"
                      >
                        <span className="flex items-center gap-1.5">
                          <Workflow className="w-3.5 h-3.5 text-cyan-400" />
                          Model Context Protocol (MCP) Setup
                        </span>
                        <span className="text-[10px] text-app-text-muted font-mono">
                          {showMcpHelper ? '[-]' : '[+]'}
                        </span>
                      </button>
                      
                      {showMcpHelper && (
                        <div className="p-4 space-y-3 text-xs leading-relaxed animate-in fade-in duration-200">
                          <p className="text-app-text-muted">
                            Model Context Protocol (MCP) lets agents connect to external tools like Jira, Slack, or databases. You can define these connections in the agent's skills.
                          </p>
                          <div className="p-2.5 rounded bg-app-bg-page border border-app-border-light font-mono text-[10px] text-app-text-muted break-all">
                            <span className="text-cyan-400 font-bold">Official Servers: </span>
                            <a href="https://github.com/modelcontextprotocol/servers" target="_blank" rel="noreferrer" className="text-app-primary hover:underline flex items-center gap-1 mt-1">
                              <Link2 className="w-3.5 h-3.5" /> github.com/modelcontextprotocol/servers
                            </a>
                          </div>
                          
                          <div className="space-y-1.5">
                            <span className="text-[11px] font-bold text-app-text-main block">Insert MCP Skill Template:</span>
                            <div className="grid grid-cols-2 gap-2">
                              <button
                                type="button"
                                onClick={() => {
                                  setNewAgentName('Jira MCP Agent');
                                  setNewAgentTags('Jira, Project Management, MCP Server, Integration');
                                  setSkillsFileName('jira_mcp_skills.md');
                                  const tmpl = PREDEFINED_TEMPLATES.find(t => t.name === 'Jira MCP Agent');
                                  if (tmpl) setSkillsContent(tmpl.skills);
                                }}
                                className="px-2 py-1.5 rounded bg-app-bg-card hover:bg-app-bg-hover border border-app-border-light/60 font-semibold text-[10px] text-app-text-main text-left truncate transition-colors flex items-center gap-1 cursor-pointer"
                              >
                                <Workflow className="w-3 h-3 text-blue-400 shrink-0" />
                                <span className="truncate">Jira MCP Server</span>
                              </button>
                              <button
                                type="button"
                                onClick={() => {
                                  setNewAgentName('GitHub MCP Agent');
                                  setNewAgentTags('GitHub, Git, PRs, MCP Server, Integration');
                                  setSkillsFileName('github_mcp_skills.md');
                                  const tmpl = PREDEFINED_TEMPLATES.find(t => t.name === 'GitHub MCP Agent');
                                  if (tmpl) setSkillsContent(tmpl.skills);
                                }}
                                className="px-2 py-1.5 rounded bg-app-bg-card hover:bg-app-bg-hover border border-app-border-light/60 font-semibold text-[10px] text-app-text-main text-left truncate transition-colors flex items-center gap-1 cursor-pointer"
                              >
                                <GitBranch className="w-3 h-3 text-slate-400 shrink-0" />
                                <span className="truncate">GitHub MCP Server</span>
                              </button>
                              <button
                                type="button"
                                onClick={() => {
                                  setNewAgentName('Slack MCP Agent');
                                  setNewAgentTags('Slack, Chat, MCP Server, Integration');
                                  setSkillsFileName('slack_mcp_skills.md');
                                  const tmpl = PREDEFINED_TEMPLATES.find(t => t.name === 'Slack MCP Agent');
                                  if (tmpl) setSkillsContent(tmpl.skills);
                                }}
                                className="px-2 py-1.5 rounded bg-app-bg-card hover:bg-app-bg-hover border border-app-border-light/60 font-semibold text-[10px] text-app-text-main text-left truncate transition-colors flex items-center gap-1 cursor-pointer"
                              >
                                <Cpu className="w-3 h-3 text-pink-400 shrink-0" />
                                <span className="truncate">Slack MCP Server</span>
                              </button>
                              <button
                                type="button"
                                onClick={() => {
                                  setNewAgentName('Custom MCP Agent');
                                  setNewAgentTags('MCP Server, Custom Tool, Integration');
                                  setSkillsFileName('custom_mcp_skills.md');
                                  setSkillsContent(`# Custom MCP Agent Skill\n\n## Role\nYou are a custom MCP integration agent.\n\n## Setup Configuration\n\`\`\`json\n{\n  "mcpServers": {\n    "custom-server": {\n      "command": "node",\n      "args": ["/path/to/server.js"],\n      "env": {}\n    }\n  }\n}\n\`\`\``);
                                }}
                                className="px-2 py-1.5 rounded bg-app-bg-card hover:bg-app-bg-hover border border-app-border-light/60 font-semibold text-[10px] text-app-text-main text-left truncate transition-colors flex items-center gap-1 cursor-pointer"
                              >
                                <Terminal className="w-3 h-3 text-yellow-400 shrink-0" />
                                <span className="truncate">Generic Template</span>
                              </button>
                            </div>
                          </div>
                        </div>
                      )}
                    </div>

                    {/* If skillsContent is NOT present, show the upload box here in the single column view */}
                    {!skillsContent && (
                      <div>
                        <label className="block text-xs font-bold text-app-text-muted uppercase tracking-wider mb-1.5">
                          Upload Skills File (skills.md)
                        </label>
                        <div className="relative">
                          <input
                            type="file"
                            accept=".md"
                            id="skills-file-upload"
                            onChange={handleFileChange}
                            className="hidden"
                            disabled={addingAgent}
                          />
                          <label
                            htmlFor="skills-file-upload"
                            className="flex flex-col items-center justify-center w-full h-32 border-2 border-dashed border-app-border-light rounded-lg cursor-pointer bg-app-bg-muted/20 hover:bg-app-bg-muted/40 transition-colors"
                          >
                            <div className="flex flex-col items-center justify-center pt-5 pb-6">
                              <Upload className="w-8 h-8 text-app-text-muted mb-2" />
                              <p className="text-sm font-semibold text-app-text-main">
                                {skillsFileName || 'Click to select skills.md'}
                              </p>
                              <p className="text-xs text-app-text-muted mt-1">
                                Markdown file (.md) only
                              </p>
                            </div>
                          </label>
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Right Column / Conditional Editor for Skills Content */}
                  {(isConfiguringTemplate || skillsContent) && (
                    <div className="flex flex-col h-full space-y-2">
                      <div className="flex items-center justify-between">
                        <label className="block text-xs font-bold text-app-text-muted uppercase tracking-wider">
                          Skills Markdown File Content
                        </label>
                        <button
                          type="button"
                          onClick={() => {
                            setSkillsContent('');
                            setSkillsFileName('');
                          }}
                          className="text-[10px] font-bold text-red-400 hover:text-red-300 transition-colors flex items-center gap-1"
                        >
                          <Trash2 className="w-3 h-3" />
                          <span>Clear / Reset</span>
                        </button>
                      </div>
                      
                      <div className="flex-1 flex flex-col rounded-lg border border-app-border bg-app-bg-page overflow-hidden">
                        {skillsFileName && (
                          <div className="px-3 py-2 bg-app-bg-muted/40 border-b border-app-border-light/60 text-[10px] text-app-text-muted font-mono flex items-center justify-between">
                            <span className="truncate max-w-[200px]" title={skillsFileName}>📄 {skillsFileName}</span>
                            <span className="text-emerald-400 font-bold uppercase tracking-wider text-[8px] bg-emerald-500/10 px-1.5 py-0.5 rounded border border-emerald-500/20">Loaded</span>
                          </div>
                        )}
                        <textarea
                          value={skillsContent}
                          onChange={(e) => setSkillsContent(e.target.value)}
                          placeholder="# Agent Skills&#10;&#10;## Role&#10;Describe role here..."
                          className="w-full min-h-[250px] md:flex-1 p-3 bg-app-bg-muted/10 text-xs text-app-text-main font-mono focus:outline-none placeholder:text-app-text-muted/40 resize-y md:resize-none scrollbar-thin scrollbar-thumb-app-border leading-relaxed"
                          disabled={addingAgent}
                          required
                        />
                      </div>
                      <p className="text-[10px] text-app-text-muted mt-1 leading-normal">
                        You can view and directly edit the instructions above. This markdown controls the agent behavior.
                      </p>
                    </div>
                  )}
                </div>

                {addAgentError && (
                  <div className="mt-4 p-3 text-xs rounded-lg bg-app-status-error/10 border border-app-status-error/20 text-red-400 animate-in fade-in duration-200">
                    {addAgentError}
                  </div>
                )}
              </div>

              {/* Actions Footer */}
              <div className="p-6 pt-4 border-t border-app-border-light flex items-center justify-end gap-2 flex-shrink-0 bg-app-bg-card/50">
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
                    setAddAgentError('');
                  }}
                  disabled={addingAgent}
                  className="px-4 py-2 text-xs font-bold text-app-text-muted hover:text-app-text-main bg-app-text-label/10 hover:bg-app-text-label/20 rounded-lg transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={addingAgent || !newAgentName.trim() || !skillsContent}
                  className="flex items-center gap-1.5 px-4 py-2 text-xs font-bold text-white bg-gradient-to-r from-app-primary to-blue-600 hover:from-blue-600 hover:to-blue-700 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg shadow transition-all"
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
