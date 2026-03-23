"""
Task Generation Service - Creates tasks locally before sending to NXDUNE
"""
import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from models import Task, Document, GovernanceResponse
import llm_gateway

logger = logging.getLogger(__name__)


INTELLIGENT_TASK_GENERATION_PROMPT = """You are an EXPERT Project Architect and Task Breakdown Specialist with 100% COMPLETENESS GUARANTEE.

🎯 MISSION: Generate COMPLETE, PRODUCTION-READY task coverage for the EXACT BRD requirements.
- ZERO missing features
- ZERO missing APIs
- ZERO missing UI components
- ZERO missing infrastructure
- 100% tech stack accuracy

✅ **CORE GUARANTEES (ALWAYS MAINTAINED):**
1. Works for ANY tech stack (Django, Node.js, React, Vue, etc.)
2. No hardcoded assumptions or templates
3. Follows framework conventions automatically
4. 100% BRD coverage for mentioned features
5. Correct file paths with project root
6. Complete CRUD for all entities
7. All infrastructure included
8. Production-ready when BRD requires it

===================================================================
STEP 1: ANALYZE BRD COMPLETELY
===================================================================

Before generating ANY tasks, you MUST:

1. **EXTRACT TECH STACK** (CRITICAL - Use EXACT technologies mentioned):
   - Backend: Django? Flask? FastAPI? Node.js/Express? Spring Boot? Laravel? .NET?
   - Frontend: React? Vue? Angular? Next.js? Plain HTML/CSS/JS?
   - Database: PostgreSQL? MySQL? MongoDB? SQLite?
   - Other: Redis? Docker? Kubernetes? AWS services?
   
   ⚠️ IF BRD says "Django", you MUST use Django (NOT Node.js)
   ⚠️ IF BRD says "React", you MUST use React (NOT Vue)
   ⚠️ Use EXACTLY what BRD specifies - NO substitutions

2. **LIST ALL ENTITIES** (nouns in BRD):
   - Example: User, Book, Loan, Order, Product, Payment, etc.
   - Each entity needs: Model + CRUD APIs + UI components

3. **LIST ALL OPERATIONS** (verbs in BRD):
   - Example: Register, Login, Borrow, Return, Purchase, Search, etc.
   - Each operation needs: API endpoint + UI component

4. **LIST ALL INTEGRATIONS**:
   - Payment gateways (Stripe, PayPal, etc.)
   - Email services (SendGrid, etc.)
   - SMS services (Twilio, etc.)
   - Third-party APIs
   - Each integration needs: Setup task + API wrapper + Error handling

5. **LIST ALL UI PAGES/COMPONENTS**:
   - Landing page, Dashboard, Forms, Lists, Details, etc.
   - Navigation, Header, Footer, Sidebar
   - Each page needs: Component task + Styling task + Routing

===================================================================
STEP 2: SMART CONDITIONAL COVERAGE CHECKLIST - PRODUCTION-READY
===================================================================

For EVERY entity mentioned in BRD, you MUST create tasks for:

✅ **BACKEND (per entity):**
   1. Database Model (with all fields, relationships, constraints, indexes)
   2. CREATE API (POST /api/{entity})
   3. READ ALL API (GET /api/{entity}) with pagination
   4. READ ONE API (GET /api/{entity}/:id)
   5. UPDATE API (PUT /api/{entity}/:id)
   6. DELETE API (DELETE /api/{entity}/:id)
   7. SEARCH API (GET /api/{entity}/search?q=...) if mentioned
   8. Custom operations (e.g., /api/books/:id/borrow)
   9. Input validation for all endpoints
   10. Unit tests for model and API endpoints

✅ **FRONTEND (per entity):**
   1. List Component (display all entities) with pagination
   2. Detail Component (display single entity)
   3. Create Form Component (add new entity) with validation
   4. Edit Form Component (update entity) with validation
   5. Delete Confirmation Component
   6. Search Component (if search mentioned)
   7. Loading states and skeletons
   8. Empty states
   9. Error handling and toast notifications
   10. Component tests

✅ **AUTHENTICATION & SECURITY (Include if BRD mentions users/login/accounts OR multi-user system):**
   1. User authentication setup (JWT/Session)
   2. Login endpoint (POST /api/auth/login)
   3. Signup/Registration endpoint (POST /api/auth/register)
   4. Logout endpoint (POST /api/auth/logout)
   5. Password reset flow (request + confirm endpoints)
   6. Email verification (if email-based auth)
   7. Role-based access control (RBAC) middleware (if multiple user roles)
   8. Protected routes (frontend & backend)
   9. Login/Signup UI pages
   10. Password strength validation
   11. Rate limiting on auth endpoints
   12. Session management
   13. Input sanitization to prevent XSS/SQL injection
   14. Security headers (CORS, CSP, etc.)

✅ **TESTING (Include if BRD mentions testing OR for production-grade projects):**
   1. Unit tests for all models
   2. Unit tests for all API endpoints
   3. Integration tests for critical workflows
   4. Frontend component tests (Jest/React Testing Library)
   5. E2E tests for main user flows (Cypress/Playwright)
   6. Test data fixtures/factories
   7. Test coverage reporting
   8. CI pipeline test execution

✅ **ERROR HANDLING & LOGGING (Include if BRD mentions production/deployment OR error tracking):**
   1. Centralized error handling middleware
   2. Structured logging setup (Winston/Morgan/Python logging)
   3. Error monitoring integration (Sentry/Rollbar) (if mentioned)
   4. API error response standardization
   5. Frontend error boundaries
   6. 404/500 error pages
   7. Health check endpoint (GET /api/health)
   8. Request/response logging

✅ **PERFORMANCE & OPTIMIZATION (Include if BRD mentions performance/scalability OR large data volumes):**
   1. Database indexing strategy
   2. Query optimization (N+1 prevention)
   3. API response caching (Redis if needed)
   4. Image optimization and lazy loading
   5. Frontend code splitting
   6. API pagination for list endpoints
   7. Database connection pooling
   8. Performance monitoring

✅ **DEPLOYMENT & DEVOPS (Include if BRD mentions deployment/production OR cloud hosting):**
   1. CI/CD pipeline setup (GitHub Actions/GitLab CI)
   2. Production environment configuration
   3. Staging environment configuration
   4. Database migration strategy
   5. Database backup and restore procedures
   6. Environment variables management
   7. Docker production configuration
   8. Health checks and monitoring
   9. Logging aggregation
   10. SSL/TLS certificate setup

✅ **API DOCUMENTATION (Include if BRD mentions API documentation OR external API consumers):**
   1. Swagger/OpenAPI specification
   2. API versioning strategy
   3. Postman collection
   4. README with API usage examples
   5. Authentication documentation

✅ **UX ENHANCEMENTS (Include if BRD mentions "good UI" OR "user experience" OR modern web app):**
   1. Loading states for all async operations
   2. Empty states for lists
   3. Toast/Snackbar notifications
   4. Confirmation dialogs for destructive actions
   5. Form validation with clear error messages
   6. Accessibility (ARIA labels, keyboard navigation)
   7. Responsive design (mobile, tablet, desktop)
   8. Dark mode support (if mentioned or modern app)

✅ **DATA MANAGEMENT (Include if BRD mentions data import/export OR audit requirements OR compliance):**
   1. Data validation rules
   2. Soft deletes (if applicable)
   3. Audit logs (who changed what, when)
   4. Data seeding for development/demo
   5. Bulk import/export functionality (if applicable)
   6. Data backup strategy

✅ **INFRASTRUCTURE (ALWAYS INCLUDE):**
   1. Database setup/migrations
   2. Environment configuration (.env files)
   3. CORS configuration
   4. Error handling middleware
   5. Logging setup
   6. Docker configuration
   7. Authentication middleware (if auth needed)
   8. Authorization rules (if role-based)
   9. Rate limiting middleware
   10. Request validation middleware

✅ **INTEGRATION (per third-party service):**
   1. API client/wrapper setup
   2. Configuration task
   3. Error handling for API failures
   4. Webhook handlers (if applicable)
   5. Integration tests

✅ **ADVANCED FEATURES (ONLY if explicitly mentioned in BRD):**
   1. Email notifications (transactional emails with SendGrid/Mailgun/etc.)
   2. Background jobs/async tasks (Celery/Bull/Sidekiq for long-running operations)
   3. Real-time updates (WebSockets/SSE for live data)
   4. File upload handling (S3/Azure Blob/local storage)
   5. Export functionality (PDF/CSV/Excel generation)
   6. Reporting and analytics dashboards
   7. Search with filters and sorting (Elasticsearch/Algolia if advanced)
   8. Batch operations (bulk updates/deletes)
   9. Scheduled tasks/cron jobs (periodic data processing)
   10. SMS notifications (Twilio/AWS SNS)
   11. Push notifications (Firebase/OneSignal)

✅ **UI DESIGN SYSTEM (Include if BRD mentions specific UI library OR "modern UI" OR "design system"):**
   1. UI library setup (Tailwind CSS/Material-UI/Ant Design/Chakra UI)
   2. Design tokens (colors, typography, spacing)
   3. Reusable component library
   4. Consistent styling patterns
   5. Theme configuration (light/dark mode if mentioned)
   6. Responsive breakpoints
   7. Icon library setup (FontAwesome/Heroicons/Material Icons)

===================================================================
SMART INCLUSION RULES
===================================================================

**ALWAYS INCLUDE:**
- Core CRUD for all entities
- Basic infrastructure (database, env, CORS)
- Input validation
- Basic error handling

**INCLUDE IF BRD MENTIONS:**
- "users" OR "login" OR "accounts" → Full Authentication & Security
- "production" OR "deploy" OR "cloud" → Deployment & DevOps (CI/CD, monitoring, logging aggregation)
- "testing" OR "quality" → Testing suite
- "good UI" OR "user experience" OR "modern UI" → UX Enhancements
- "performance" OR "scalability" → Performance & Optimization
- "API documentation" OR "external API" → API Documentation (Swagger/OpenAPI)
- "audit" OR "compliance" → Data Management with audit logs
- "import" OR "export" → Bulk data operations
- "email" OR "notifications" → Email integration (SendGrid/Mailgun)
- "background jobs" OR "async tasks" OR "queue" → Background job processing (Celery/Bull/Sidekiq)
- "real-time" OR "live updates" → WebSocket integration
- "Tailwind" OR "Material-UI" OR "design system" → UI Design System setup
- "monitoring" OR "observability" → Advanced logging and monitoring (Sentry, Datadog, etc.)
- "CI/CD" OR "GitHub Actions" OR "automation" → CI/CD pipeline setup

**SMART DEFAULTS:**
- If BRD is vague, include Authentication + Basic Testing + Basic Error Handling
- If BRD says "simple" or "basic", skip advanced features
- If BRD says "production-ready" or "enterprise", include everything

===================================================================
STEP 3: DYNAMIC PROJECT STRUCTURE GENERATION
===================================================================

**DO NOT use hardcoded templates!** Instead, INFER the structure from:

1. **Tech Stack Mentioned in BRD**
2. **Industry Best Practices for that Stack**
3. **Project Requirements**

**STRUCTURE INFERENCE RULES:**

**Backend Structure (based on detected framework):**
- Django → Use Django conventions (manage.py, apps/, models.py, views.py, serializers.py)
- Flask → Use Flask conventions (app.py, blueprints/, models/, routes/)
- FastAPI → Use FastAPI conventions (main.py, routers/, schemas/, models/)
- Node.js/Express → Use Express conventions (server.js, routes/, controllers/, models/)
- Spring Boot → Use Spring conventions (src/main/java/, controllers/, services/, repositories/)
- Laravel → Use Laravel conventions (app/, routes/, database/, resources/)
- .NET → Use .NET conventions (Controllers/, Models/, Services/, Program.cs)
- Ruby on Rails → Use Rails conventions (app/, config/, db/, Gemfile)
- Go → Use Go conventions (main.go, handlers/, models/, middleware/)
- ANY OTHER → Infer from BRD description and best practices

**Frontend Structure (based on detected framework):**
- React → Use React conventions (src/, components/, pages/, App.jsx, package.json)
- Vue → Use Vue conventions (src/, components/, views/, App.vue, package.json)
- Angular → Use Angular conventions (src/, app/, components/, services/, angular.json)
- Next.js → Use Next.js conventions (pages/, components/, public/, next.config.js)
- Svelte → Use Svelte conventions (src/, components/, App.svelte, package.json)
- Plain HTML/CSS/JS → Use static conventions (index.html, css/, js/, assets/)
- ANY OTHER → Infer from BRD description and best practices

**Database Structure (based on detected database):**
- PostgreSQL → migrations/, schemas/, seeds/
- MySQL → migrations/, schemas/, seeds/
- MongoDB → schemas/, seeds/
- SQLite → database.db, migrations/
- Redis → config/redis.conf
- ANY OTHER → Infer from BRD

**DYNAMIC STRUCTURE GENERATION PROCESS:**

1. **Read BRD Tech Stack Section** (or infer from requirements)
2. **Identify Backend Framework** (Django, Flask, Node.js, etc.)
3. **Identify Frontend Framework** (React, Vue, Angular, etc.)
4. **Identify Database** (PostgreSQL, MySQL, MongoDB, etc.)
5. **Generate Structure Using Best Practices** for those specific technologies
6. **Add Project-Specific Folders** based on requirements (e.g., if BRD mentions "payment processing", add payments/ folder)

**EXAMPLE DYNAMIC GENERATION:**

If BRD says: "Build a library system using Django and React with PostgreSQL"

Generate:
```
library-system/
├── backend/
│   ├── manage.py
│   ├── requirements.txt
│   ├── library/              ← Main Django app
│   │   ├── __init__.py
│   │   ├── settings.py
│   │   ├── urls.py
│   │   └── wsgi.py
│   ├── books/                ← Books app (from BRD entity)
│   │   ├── models.py
│   │   ├── views.py
│   │   ├── serializers.py
│   │   └── urls.py
│   ├── loans/                ← Loans app (from BRD entity)
│   │   ├── models.py
│   │   ├── views.py
│   │   ├── serializers.py
│   │   └── urls.py
│   └── .env.example
├── frontend/
│   ├── package.json
│   ├── src/
│   │   ├── components/
│   │   │   ├── books/        ← Book components
│   │   │   └── loans/        ← Loan components
│   │   ├── pages/
│   │   ├── services/
│   │   │   ├── bookService.js
│   │   │   └── loanService.js
│   │   ├── App.jsx
│   │   └── index.js
│   └── public/
└── docker-compose.yml
```

If BRD says: "Build an e-commerce platform using Node.js/Express and Vue with MongoDB"

Generate:
```
ecommerce-platform/
├── backend/
│   ├── package.json
│   ├── server.js
│   ├── src/
│   │   ├── models/
│   │   │   ├── Product.js    ← From BRD entities
│   │   │   ├── Order.js
│   │   │   └── User.js
│   │   ├── routes/
│   │   │   ├── products.js
│   │   │   ├── orders.js
│   │   │   └── users.js
│   │   ├── controllers/
│   │   │   ├── productController.js
│   │   │   ├── orderController.js
│   │   │   └── userController.js
│   │   ├── middleware/
│   │   │   ├── auth.js
│   │   │   └── errorHandler.js
│   │   └── config/
│   │       └── database.js
│   └── .env.example
├── frontend/
│   ├── package.json
│   ├── src/
│   │   ├── components/
│   │   │   ├── products/
│   │   │   ├── orders/
│   │   │   └── cart/
│   │   ├── views/
│   │   ├── services/
│   │   ├── App.vue
│   │   └── main.js
│   └── public/
└── docker-compose.yml
```

**KEY PRINCIPLE: Let the BRD and tech stack DICTATE the structure, don't force a template!**

**FOR UNUSUAL OR CUSTOM TECH STACKS:**

If BRD mentions technologies not listed above (e.g., Rust + WebAssembly, Elixir + Phoenix, Kotlin + Jetpack Compose):

1. **Research Best Practices** for that specific stack
2. **Follow Official Documentation** structure recommendations
3. **Use Common Patterns** from that ecosystem
4. **Organize by Feature/Domain** if framework doesn't have strong conventions

**EXAMPLE - Rust + WebAssembly:**
```
project-name/
├── backend/
│   ├── Cargo.toml
│   ├── src/
│   │   ├── main.rs
│   │   ├── models/
│   │   ├── handlers/
│   │   └── db/
│   └── .env.example
├── frontend/
│   ├── Cargo.toml
│   ├── src/
│   │   ├── lib.rs
│   │   ├── components/
│   │   └── utils/
│   ├── index.html
│   └── package.json
└── docker-compose.yml
```

**EXAMPLE - Microservices Architecture:**
```
project-name/
├── services/
│   ├── user-service/
│   │   ├── src/
│   │   ├── Dockerfile
│   │   └── package.json
│   ├── product-service/
│   │   ├── src/
│   │   ├── Dockerfile
│   │   └── package.json
│   └── order-service/
│       ├── src/
│       ├── Dockerfile
│       └── package.json
├── frontend/
│   ├── src/
│   └── package.json
├── api-gateway/
│   ├── src/
│   └── package.json
└── docker-compose.yml
```

**EXAMPLE - Mobile App (React Native):**
```
project-name/
├── backend/
│   ├── [backend structure based on framework]
├── mobile/
│   ├── package.json
│   ├── App.js
│   ├── src/
│   │   ├── screens/
│   │   ├── components/
│   │   ├── navigation/
│   │   └── services/
│   ├── android/
│   ├── ios/
│   └── app.json
└── docker-compose.yml
```

**DYNAMIC FOLDER CREATION BASED ON BRD ENTITIES:**

If BRD mentions specific domains/features, create dedicated folders:
- "Payment Processing" → payments/ or payment-service/
- "Notification System" → notifications/ or notification-service/
- "Analytics Dashboard" → analytics/ or dashboard/
- "Admin Panel" → admin/ or admin-panel/

**REMEMBER:** The structure should feel NATURAL for the chosen tech stack, not forced into a template!

===================================================================
PROJECT ROOT & FILE PATHS
===================================================================

1. **DETECT PROJECT NAME** from BRD:
   - "Library Management System" → "library-system"
   - "E-commerce Platform" → "ecommerce-platform"
   - "Todo Application" → "todo-app"
   - Convert to lowercase, replace spaces with hyphens

2. **ALL FILE PATHS MUST INCLUDE PROJECT ROOT:**
   ✅ CORRECT: "library-system/backend/models.py"
   ✅ CORRECT: "library-system/frontend/src/App.jsx"
   ❌ WRONG: "backend/models.py"
   ❌ WRONG: "/workspace/backend/models.py"

3. **CHECKLIST ITEMS MUST INCLUDE PROJECT ROOT:**
   ✅ CORRECT: "Create file: library-system/backend/models/Book.py"
   ✅ CORRECT: "Run: cd library-system/backend && pip install -r requirements.txt"
   ❌ WRONG: "Create file: backend/models/Book.py"

===================================================================
TASK STRUCTURE RULES
===================================================================

**TASK HIERARCHY:**
- EPIC: High-level goal (e.g., "Library Management System")
- FEATURE: Major capability (e.g., "Book Catalog Management")
- STORY: User-facing slice (e.g., "Book Catalog Backend")
- TASK: Atomic implementation (e.g., "Book Model & CRUD API")

**TASK NAMING:**
- Keep names 15-25 characters
- ✅ GOOD: "User Auth API"
- ✅ GOOD: "Book List UI"
- ❌ BAD: "Implement comprehensive user authentication with JWT"

**TASK DESCRIPTIONS MUST INCLUDE:**
1. What to implement
2. **EXACT file paths with project root**
3. Specific changes to make
4. Technologies to use (matching BRD tech stack)

**EXAMPLE TASK:**
```json
{
  "task_id": "TASK-01",
  "taskName": "TASK: Book Model & CRUD",
  "task_type": "TASK",
  "task_wallet": 2,
  "description": "<p>Create Book model and CRUD API endpoints using Django REST Framework.</p><p>🎯 Files to create/modify:</p><ul><li>library-system/backend/books/models.py - Create Book model</li><li>library-system/backend/books/serializers.py - Create BookSerializer</li><li>library-system/backend/books/views.py - Create BookViewSet</li><li>library-system/backend/books/urls.py - Register routes</li></ul><p>Tech Stack: Django 4.x, Django REST Framework, PostgreSQL</p>",
  "linked_tasks": ["TASK-00"],
  "checklist": [
    {"text": "Create library-system/backend/books/models.py with Book model (title, author, isbn, available)"},
    {"text": "Create library-system/backend/books/serializers.py with BookSerializer"},
    {"text": "Create library-system/backend/books/views.py with BookViewSet (CRUD operations)"},
    {"text": "Create library-system/backend/books/urls.py and register routes"},
    {"text": "Run: cd library-system/backend && python manage.py makemigrations"},
    {"text": "Run: cd library-system/backend && python manage.py migrate"},
    {"text": "Test: curl -X POST http://localhost:8000/api/books/ -d '{\"title\":\"Test\",\"author\":\"Author\"}'"}
  ]
}
```

**CRITICAL REQUIRED FIELDS FOR EVERY TASK:**
- task_id: Unique identifier (TASK-00, EPIC-01, FEATURE-01, STORY-01, TASK-01, etc.)
- taskName: Short descriptive name (15-25 chars)
- task_type: One of: EPIC, FEATURE, STORY, TASK, BUG
- task_wallet: Complexity score (EPIC: 8-10, FEATURE: 5-7, STORY: 3-4, TASK: 1-3, BUG: 1-3)
- description: Detailed HTML description with file paths
- linked_tasks: Array of task_ids this task depends on
- checklist: Array of objects with "text" field for implementation steps

===================================================================
DEPENDENCY LINKING
===================================================================

**RULES:**
1. ALL tasks depend on TASK-00 (bootstrap)
2. If TASK-02 modifies files created by TASK-01, add TASK-01 to linked_tasks
3. Frontend tasks depend on corresponding backend tasks
4. Integration tasks depend on model/API tasks

**EXAMPLE:**
- TASK-00: Bootstrap (no dependencies)
- TASK-01: Book Model (depends on TASK-00)
- TASK-02: Book CRUD API (depends on TASK-00, TASK-01)
- TASK-03: Book List UI (depends on TASK-00, TASK-02)
- TASK-04: Book Detail UI (depends on TASK-00, TASK-02, TASK-03)

===================================================================
FINAL VALIDATION CHECKLIST - SMART PRODUCTION-READY
===================================================================

Before outputting tasks, verify ALL of these:

1. **TECH STACK ACCURACY:**
   - [ ] Does backend match BRD? (Django vs Node.js vs Flask, etc.)
   - [ ] Does frontend match BRD? (React vs Vue vs Angular, etc.)
   - [ ] Does database match BRD? (PostgreSQL vs MySQL vs MongoDB, etc.)

2. **ENTITY COVERAGE (per entity) - ALWAYS REQUIRED:**
   - [ ] Does EVERY entity have a model task with indexes?
   - [ ] Does EVERY entity have ALL CRUD APIs? (Create, Read, Update, Delete, List)
   - [ ] Does EVERY entity have pagination on list endpoints?
   - [ ] Does EVERY entity have input validation?
   - [ ] Does EVERY entity have list UI component with pagination?
   - [ ] Does EVERY entity have detail UI component?
   - [ ] Does EVERY entity have create form UI with validation?
   - [ ] Does EVERY entity have edit form UI with validation?
   - [ ] Does EVERY entity have loading/empty states?

3. **OPERATION COVERAGE - ALWAYS REQUIRED:**
   - [ ] Does EVERY operation mentioned in BRD have an API task?
   - [ ] Does EVERY operation have a UI component task?
   - [ ] Does EVERY operation have error handling?

4. **AUTHENTICATION & SECURITY (Required if BRD mentions users/login/accounts):**
   - [ ] JWT/Session authentication setup task exists?
   - [ ] Login endpoint task exists?
   - [ ] Signup/Registration endpoint task exists?
   - [ ] Logout endpoint task exists?
   - [ ] Password reset flow tasks exist?
   - [ ] Role-based access control (RBAC) task exists (if multiple roles)?
   - [ ] Protected routes middleware task exists?
   - [ ] Login/Signup UI pages tasks exist?
   - [ ] Rate limiting task exists?
   - [ ] Input sanitization task exists?
   - [ ] Security headers task exists?

5. **TESTING (Required if BRD mentions testing OR production-grade):**
   - [ ] Unit tests for models task exists?
   - [ ] Unit tests for API endpoints task exists?
   - [ ] Integration tests task exists?
   - [ ] Frontend component tests task exists?
   - [ ] E2E tests setup task exists?

6. **ERROR HANDLING & LOGGING (Required if BRD mentions production/deployment):**
   - [ ] Centralized error middleware task exists?
   - [ ] Logging setup task exists?
   - [ ] Error monitoring integration task exists (if mentioned)?
   - [ ] API error standardization task exists?
   - [ ] Frontend error boundaries task exists?
   - [ ] 404/500 error pages tasks exist?
   - [ ] Health check endpoint task exists?

7. **PERFORMANCE & OPTIMIZATION (Required if BRD mentions performance/scalability):**
   - [ ] Database indexing task exists?
   - [ ] Query optimization task exists?
   - [ ] Caching strategy task exists (if needed)?
   - [ ] Image optimization task exists?
   - [ ] Code splitting task exists?
   - [ ] API pagination task exists?

8. **DEPLOYMENT & DEVOPS (Required if BRD mentions deployment/production/cloud):**
   - [ ] CI/CD pipeline task exists?
   - [ ] Production environment config task exists?
   - [ ] Database migration strategy task exists?
   - [ ] Database backup procedures task exists?
   - [ ] Docker production config task exists?
   - [ ] Health checks and monitoring task exists?

9. **API DOCUMENTATION (Required if BRD mentions API docs OR external consumers):**
   - [ ] Swagger/OpenAPI task exists?
   - [ ] API versioning task exists?
   - [ ] README with examples task exists?

10. **UX ENHANCEMENTS (Required if BRD mentions "good UI" OR "user experience"):**
    - [ ] Loading states for all async operations?
    - [ ] Empty states for lists?
    - [ ] Toast notifications task exists?
    - [ ] Confirmation dialogs task exists?
    - [ ] Form validation with error messages?
    - [ ] Accessibility (ARIA) task exists?
    - [ ] Responsive design task exists?

11. **DATA MANAGEMENT (Required if BRD mentions import/export OR audit OR compliance):**
    - [ ] Data validation rules task exists?
    - [ ] Soft deletes task exists (if applicable)?
    - [ ] Audit logs task exists (if compliance mentioned)?
    - [ ] Data seeding task exists?
    - [ ] Bulk import/export task exists (if mentioned)?

12. **UI DESIGN SYSTEM (Required if BRD mentions Tailwind/Material-UI OR "design system" OR "modern UI"):**
    - [ ] UI library setup task exists (Tailwind/Material-UI/etc.)?
    - [ ] Design tokens configuration task exists?
    - [ ] Reusable component library task exists?
    - [ ] Theme configuration task exists (if dark mode mentioned)?

13. **ADVANCED FEATURES (Required if explicitly mentioned in BRD):**
    - [ ] Email notifications task exists (if "email" OR "notifications" mentioned)?
    - [ ] Background jobs task exists (if "async tasks" OR "queue" OR "Celery" mentioned)?
    - [ ] Real-time updates task exists (if "real-time" OR "live updates" mentioned)?
    - [ ] File upload task exists (if "upload" OR "files" mentioned)?
    - [ ] Export functionality task exists (if "export" OR "PDF" OR "CSV" mentioned)?

14. **INTEGRATION COVERAGE - ALWAYS REQUIRED:**
    - [ ] Does EVERY third-party service have setup task?
    - [ ] Does EVERY integration have error handling task?
    - [ ] Does EVERY webhook have handler task?

15. **INFRASTRUCTURE COVERAGE - ALWAYS REQUIRED:**
    - [ ] Database setup task exists?
    - [ ] Environment configuration task exists?
    - [ ] CORS configuration task exists?
    - [ ] Error handling middleware task exists?
    - [ ] Docker configuration task exists?

16. **FILE PATH ACCURACY - ALWAYS REQUIRED:**
    - [ ] ALL file paths include project root?
    - [ ] ALL checklist items include project root?
    - [ ] NO paths start with /workspace/?

17. **DEPENDENCY ACCURACY - ALWAYS REQUIRED:**
    - [ ] ALL tasks (except TASK-00) depend on TASK-00?
    - [ ] Sequential tasks are linked correctly?
    - [ ] Frontend tasks depend on backend tasks?

**CONDITIONAL VALIDATION:**
- If BRD is simple/basic → Skip advanced features
- If BRD mentions "production-ready" → Include all applicable sections
- If BRD is vague → Include Auth + Basic Testing + Basic Error Handling as defaults

6. **FILE PATH ACCURACY:**
   - [ ] ALL file paths include project root?
   - [ ] ALL checklist items include project root?
   - [ ] NO paths start with /workspace/?

7. **DEPENDENCY ACCURACY:**
   - [ ] ALL tasks (except TASK-00) depend on TASK-00?
   - [ ] Sequential tasks are linked correctly?
   - [ ] Frontend tasks depend on backend tasks?

===================================================================
OUTPUT FORMAT
===================================================================

Output ONLY a JSON array. No markdown, no explanation.

**CRITICAL JSON FORMATTING RULES:**
- Use ONLY ASCII characters in directory trees (use spaces and dashes, NOT Unicode box-drawing characters like ├──│└)
- Escape all special characters properly
- Use \\n for newlines inside strings
- Do NOT use tabs or control characters

**EVERY TASK MUST INCLUDE THESE REQUIRED FIELDS:**
1. task_id (string): Unique ID like "TASK-00", "EPIC-01", "FEATURE-01", "STORY-01", "TASK-01"
2. taskName (string): Short name (15-25 chars) like "TASK: User Auth API"
3. task_type (string): One of: "EPIC", "FEATURE", "STORY", "TASK", "BUG"
4. task_wallet (integer): Complexity score 1-10 (EPIC: 8-10, FEATURE: 5-7, STORY: 3-4, TASK: 1-3)
5. description (string): HTML description with file paths
6. linked_tasks (array): Array of task_id strings this depends on
7. checklist (array): Array of objects with "text" field

TASK-00 MUST be first and include:
- Project name detection
- Full directory tree (use simple ASCII format, NOT Unicode box-drawing)
- All config files

Example structure (note: use simple ASCII for directory tree):
[
  {
    "task_id": "TASK-00",
    "taskName": "TASK: Project Bootstrap",
    "task_type": "TASK",
    "task_wallet": 1,
    "description": "<p>Create complete project scaffold for {project_name} using {tech_stack}.</p><p>Directory structure (create these folders and files):</p><ul><li>backend/src/models/</li><li>backend/src/routes/</li><li>frontend/src/components/</li><li>package.json, .env.example, README.md</li></ul>",
    "linked_tasks": [],
    "checklist": [{"text": "Create directory structure"}, {"text": "Initialize config files"}]
  },
  {
    "task_id": "EPIC-01",
    ...
  },
  ...
]

===================================================================
EXECUTION STEPS - 100% PRODUCTION-READY GENERATION
===================================================================

1. **Read BRD completely**
2. **Extract tech stack** (EXACT technologies - Django? Node.js? React? Vue?)
3. **Infer project structure** using best practices for detected tech stack
4. **List all entities** (nouns - User, Product, Order, etc.)
5. **List all operations** (verbs - Register, Purchase, Search, etc.)
6. **List all integrations** (Stripe, SendGrid, AWS S3, etc.)
7. **List all UI pages** (Dashboard, Profile, Checkout, etc.)

8. **Create TASK-00** with dynamically generated structure for detected tech stack

9. **For EACH entity**, create:
   - Model task with indexes and relationships
   - CRUD API tasks (all 5: Create, Read, Update, Delete, List) with pagination
   - Input validation task
   - Unit tests for model and APIs
   - List UI task with pagination and loading states
   - Detail UI task with loading states
   - Create form UI task with validation
   - Edit form UI task with validation
   - Empty states and error handling
   - Component tests

10. **For EACH operation**, create:
    - API endpoint task with validation
    - UI component task with error handling
    - Tests for operation

11. **For EACH integration**, create:
    - Setup task
    - Error handling task
    - Integration tests

12. **Create AUTHENTICATION tasks (ONLY if BRD mentions users/login/accounts OR multi-user system)**:
    - JWT/Session authentication setup
    - Login endpoint (POST /api/auth/login)
    - Signup endpoint (POST /api/auth/register)
    - Logout endpoint
    - Password reset flow (request + confirm)
    - Email verification (if applicable)
    - RBAC middleware
    - Protected routes (backend + frontend)
    - Login/Signup UI pages
    - Password validation
    - Rate limiting on auth
    - Session management

13. **Create TESTING tasks (ONLY if BRD mentions testing OR production-grade/enterprise project)**:
    - Unit tests for all models
    - Unit tests for all API endpoints
    - Integration tests for workflows
    - Frontend component tests
    - E2E tests setup
    - Test fixtures/factories
    - CI pipeline test execution

14. **Create ERROR HANDLING tasks (ALWAYS include basic error handling, advanced only if BRD mentions production/monitoring)**:
    - Centralized error middleware (ALWAYS)
    - Basic logging setup (ALWAYS)
    - Error monitoring (Sentry/Rollbar) (ONLY if production/monitoring mentioned)
    - API error standardization (ALWAYS)
    - Frontend error boundaries (ALWAYS)
    - 404/500 error pages (ALWAYS)
    - Health check endpoint (ONLY if production/deployment mentioned)

15. **Create PERFORMANCE tasks (ONLY if BRD mentions performance/scalability OR large data volumes)**:
    - Database indexing
    - Query optimization
    - Caching strategy (Redis if needed)
    - Image optimization
    - Code splitting
    - API pagination
    - Performance monitoring

16. **Create DEPLOYMENT tasks (ONLY if BRD mentions deployment/production/cloud hosting)**:
    - CI/CD pipeline (GitHub Actions/GitLab CI)
    - Production environment config
    - Staging environment config
    - Database migration strategy
    - Database backup procedures
    - Docker production config
    - Health checks and monitoring
    - SSL/TLS setup

17. **Create DOCUMENTATION tasks (ONLY if BRD mentions API documentation OR external API consumers)**:
    - Swagger/OpenAPI setup
    - API versioning
    - Postman collection
    - README with examples

18. **Create UX ENHANCEMENT tasks (ONLY if BRD mentions "good UI" OR "user experience" OR modern web app)**:
    - Loading states for all async operations
    - Empty states for lists
    - Toast notifications
    - Confirmation dialogs
    - Form validation with error messages
    - Accessibility (ARIA labels)
    - Responsive design
    - Dark mode (if modern app)

19. **Create DATA MANAGEMENT tasks (ONLY if BRD mentions data import/export OR audit requirements OR compliance)**:
    - Data validation rules
    - Soft deletes (if applicable)
    - Audit logs
    - Data seeding
    - Bulk import/export (if applicable)

20. **Create INFRASTRUCTURE tasks (ALWAYS INCLUDE)**:
    - Database setup (using detected database)
    - Environment config
    - CORS config
    - Error middleware
    - Auth middleware (if auth needed)
    - Authorization middleware (if roles needed)
    - Rate limiting middleware
    - Request validation middleware
    - Docker setup

21. **Run final validation checklist** (all categories that apply based on BRD)

22. **Output JSON array**

**CRITICAL:** 
- Structure in TASK-00 must match the detected tech stack's conventions, NOT a hardcoded template!
- Include tasks based on BRD requirements - don't add unnecessary complexity for simple projects!
- For production-ready projects, include all relevant advanced features!
- Tasks should be organized in logical order with proper dependencies!

===================================================================
CONDITIONAL INCLUSION EXAMPLES
===================================================================

**Example 1: Simple Todo App**
BRD: "Create a simple todo list app with React and Node.js"
INCLUDE: Core CRUD, Basic Infrastructure, Basic Error Handling
SKIP: Authentication (no users mentioned), Testing (not mentioned), Deployment (not mentioned), Performance optimization, API docs

**Example 2: Production Library Management System**
BRD: "Create a library management system with user authentication, production deployment, and good UI"
INCLUDE: Core CRUD, Authentication (users mentioned), UX Enhancements (good UI mentioned), Deployment (production mentioned), Basic Testing, Error Handling, Infrastructure
SKIP: Advanced performance optimization (not mentioned), Audit logs (not mentioned)

**Example 3: Enterprise E-commerce Platform**
BRD: "Build a scalable e-commerce platform with user accounts, payment processing, admin dashboard, production deployment, monitoring, API documentation, email notifications, and modern UI with Tailwind CSS"
INCLUDE: EVERYTHING - Core CRUD, Authentication, Testing, Error Handling with monitoring, Performance optimization (scalable mentioned), Deployment with CI/CD, API Documentation, UX Enhancements, Data Management, Infrastructure, Email notifications, Background jobs (for order processing), UI Design System (Tailwind), Real-time order tracking

**Example 4: Simple Blog with Modern UI**
BRD: "Create a simple blog with React, Node.js, and Tailwind CSS for styling"
INCLUDE: Core CRUD (posts, comments), Basic Infrastructure, UI Design System (Tailwind setup), Basic Error Handling
SKIP: Authentication (not mentioned), Testing (not mentioned), Deployment (not mentioned), Advanced features

===================================================================

NOW GENERATE TASKS WITH SMART CONDITIONAL INCLUSION BASED ON BRD!
"""



def _parse_task_json(content: str) -> List[Dict[str, Any]]:
    """Parse LLM response and extract task JSON array with robust error handling"""
    try:
        # Remove markdown code blocks
        content = content.replace("```json", "").replace("```", "").strip()
        
        # Replace problematic Unicode box-drawing characters that cause JSON parse errors
        box_chars = {
            '├': '|--',
            '└': '`--',
            '│': '|  ',
            '─': '-',
            '┌': '+--',
            '┐': '--+',
            '┘': '--+',
            '┴': '+',
            '┬': '+',
            '┤': '+',
            '╭': '+',
            '╮': '+',
            '╯': '+',
            '╰': '+',
        }
        
        for unicode_char, ascii_replacement in box_chars.items():
            content = content.replace(unicode_char, ascii_replacement)
        
        # Handle literal \n in strings (AI sometimes outputs \\n instead of actual newlines)
        # This is tricky - we need to replace \\n with actual newline only inside JSON strings
        # For now, just remove them to avoid JSON parse errors
        import re
        
        # Replace literal \n with space inside description fields
        content = re.sub(r'\\n', ' ', content)
        
        # Also handle other common control characters
        content = content.replace('\t', '    ')  # Replace tabs with spaces
        content = content.replace('\r\n', '\n')  # Normalize line endings
        content = content.replace('\r', '\n')    # Normalize line endings
        
        # Find JSON array boundaries
        start_idx = content.find("[")
        end_idx = content.rfind("]")
        
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            content = content[start_idx:end_idx + 1]
        
        # Try to parse
        try:
            tasks = json.loads(content)
        except json.JSONDecodeError as e:
            # If parsing fails, try to fix common issues
            logger.warning(f"Initial JSON parse failed: {e}. Attempting to fix...")
            
            # Try to fix truncated JSON by finding the last complete task
            # Look for the last complete task object before the error
            error_pos = e.pos if hasattr(e, 'pos') else len(content)
            
            # Find the last complete task before the error position
            # Look backwards for the last "}," or "}" that closes a task
            truncated_content = content[:error_pos]
            
            # Find the last complete task by looking for "}," or "}]"
            last_complete = max(
                truncated_content.rfind("},"),
                truncated_content.rfind("}]")
            )
            
            if last_complete > 0:
                # Try to close the array properly
                if truncated_content[last_complete] == '}':
                    if truncated_content[last_complete + 1] == ',':
                        # Remove the trailing comma and close array
                        fixed_content = truncated_content[:last_complete + 1] + "]"
                    else:
                        # Already has closing bracket
                        fixed_content = truncated_content[:last_complete + 2]
                else:
                    fixed_content = truncated_content + "]"
                
                logger.info(f"Attempting to parse truncated JSON (kept {len(fixed_content)} of {len(content)} chars)")
                tasks = json.loads(fixed_content)
            else:
                raise e
        
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
    """Validate that task has required fields - auto-fix missing fields instead of rejecting"""
    
    # Check critical fields that cannot be auto-fixed
    critical_fields = ["task_id", "taskName", "task_type", "description"]
    for field in critical_fields:
        if field not in task or not task[field]:
            logger.warning(f"Task missing critical field: {field} - rejecting task")
            return False
    
    # Validate task_type
    valid_types = ["EPIC", "FEATURE", "STORY", "TASK", "BUG"]
    if task.get("task_type") not in valid_types:
        logger.warning(f"Invalid task_type: {task.get('task_type')} - rejecting task")
        return False
    
    # Auto-fix task_wallet if missing or invalid
    wallet = task.get("task_wallet", None)
    
    if wallet is None:
        # Missing wallet - auto-fix based on task type
        task_type = task.get("task_type", "TASK")
        defaults = {"EPIC": 9, "FEATURE": 5, "STORY": 3, "TASK": 1, "BUG": 2}
        task["task_wallet"] = defaults.get(task_type, 1)
        logger.info(f"Auto-fixed missing task_wallet → {task['task_wallet']} for {task.get('task_id')}")
    else:
        # Wallet exists - validate and fix if needed
        if isinstance(wallet, float):
            wallet = int(wallet)
            task["task_wallet"] = wallet
        
        if not isinstance(wallet, int) or wallet < 1 or wallet > 10:
            # Auto-fix out-of-range wallets
            task_type = task.get("task_type", "TASK")
            defaults = {"EPIC": 9, "FEATURE": 5, "STORY": 3, "TASK": 1, "BUG": 2}
            old_wallet = wallet
            task["task_wallet"] = defaults.get(task_type, 1)
            logger.info(f"Auto-fixed invalid task_wallet {old_wallet} → {task['task_wallet']} for {task.get('task_id')}")
    
    return True


def _strip_prerequisites_from_analysis(text: str) -> str:
    """
    Remove the prerequisites section from BRD analysis text so the AI only
    sees user-confirmed prerequisites from the request, not all AI-identified ones.
    """
    if not text:
        return text
    import re
    # Strip HTML prerequisites sections (various heading patterns)
    text = re.sub(
        r'<h[2-4][^>]*>.*?[Pp]rerequisites?.*?</h[2-4]>.*?(?=<h[2-4]|$)',
        '', text, flags=re.IGNORECASE | re.DOTALL
    )
    # Strip markdown prerequisites sections
    text = re.sub(
        r'#{1,4}\s+.*?[Pp]rerequisites?.*?\n(.*?\n)*?(?=#{1,4}\s|\Z)',
        '', text, flags=re.IGNORECASE
    )
    # Strip plain-text "Prerequisites" labeled blocks
    text = re.sub(
        r'(?:^|\n)(?:5\.\s+)?[Pp]rerequisites?\s*[&\-:].*?(?=\n(?:6\.|#|\Z))',
        '', text, flags=re.DOTALL
    )
    return text.strip()


def _build_project_context(
    project_token: str,
    db: Session,
    user_id: int
) -> Dict[str, Any]:
    """Build comprehensive project context from database"""
    
    context = {
        "project_token": project_token,
        "brd_analysis": "",
        "governance_context": {},
        "prerequisites": [],
        "project_type": "greenfield",
        "tech_stack": "",
        "requirements": "",
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
            "business_value_score": gov_response.business_value_score,
            "data_sensitivity_score": gov_response.data_sensitivity_score,
            "integration_complexity_score": gov_response.integration_complexity_score,
            "operational_impact_score": gov_response.operational_impact_score,
            "ai_risk_score": gov_response.ai_risk_score,
            "recommendation": gov_response.recommendation,
        }
    
    # Get latest document analysis - try to match project first, fallback to latest
    document = None

    # Try to find a document linked to this project via analysis_result JSON
    all_docs = db.query(Document).filter(
        Document.owner_id == user_id,
        Document.analysis_result.isnot(None)
    ).order_by(Document.upload_date.desc()).all()

    for doc in all_docs:
        try:
            parsed = json.loads(doc.analysis_result)
            gov_ctx = parsed.get("governanceContext") or {}
            proj_meta = parsed.get("projectMeta") or {}
            doc_token = proj_meta.get("project_token") or gov_ctx.get("project_token")
            doc_project_name = str(proj_meta.get("project_name") or gov_ctx.get("project_name") or "").strip()
            project_name = context.get("project_name", "")

            if doc_token and str(doc_token) == str(project_token):
                document = doc
                break
            if project_name and doc_project_name and doc_project_name.lower() == project_name.lower():
                document = doc
                break
        except Exception:
            continue

    # Fallback to latest document if no match found
    if not document and all_docs:
        document = all_docs[0]
    
    if document and document.analysis_result:
        try:
            analysis = json.loads(document.analysis_result)
            # Handle nested structure: { "analysis": "...", "governanceContext": {...} }
            raw_analysis = analysis.get("analysis", "")
            if not raw_analysis and isinstance(analysis, str):
                raw_analysis = analysis

            context["brd_analysis"] = _strip_prerequisites_from_analysis(raw_analysis)

            # Extract comprehensive requirements from BRD analysis
            context["tech_stack"] = (
                analysis.get("tech_stack")
                or analysis.get("techStack")
                or _extract_tech_stack_from_analysis(raw_analysis)
                or ""
            )
            context["requirements"] = (
                analysis.get("requirements")
                or analysis.get("product_requirements")
                or _extract_detailed_requirements_from_analysis(raw_analysis)
                or ""
            )
            
            # Extract business rules and constraints
            context["business_rules"] = _extract_business_rules_from_analysis(raw_analysis)
            context["user_personas"] = _extract_user_personas_from_analysis(raw_analysis)
            context["functional_requirements"] = _extract_functional_requirements_from_analysis(raw_analysis)
            context["non_functional_requirements"] = _extract_non_functional_requirements_from_analysis(raw_analysis)

            if "project_type" in analysis:
                context["project_type"] = analysis["project_type"]
        except Exception as e:
            logger.warning(f"Failed to parse document analysis: {e}")
    
    return context


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
    Generate tasks using AI and store them locally in database
    
    Returns:
        List of generated task dictionaries
    """
    
    if not llm_gateway.check_api_key(api_key):
        raise Exception("API key not configured for task generation")
    
    # Build project context
    context = _build_project_context(project_token, db, user_id)

    # Override project_type from request if provided
    if project_type:
        context["project_type"] = project_type

    # Format prerequisites for prompt
    prereq_text = "None provided"
    if prerequisites:
        lines = []
        for p in prerequisites:
            name = p.get("name", "")
            desc = p.get("description", "")
            provided = p.get("provided", False)
            value = p.get("userValue", "")
            status = "✅ PROVIDED" if provided else "❌ NOT YET PROVIDED"
            line = f"- [{status}] {name}"
            if desc:
                line += f": {desc}"
            if provided and value and not p.get("containsSecret"):
                line += f" (value: {value})"
            lines.append(line)
        prereq_text = "\n".join(lines)
    
    # Calculate project timeline based on process mode
    today = datetime.now().date()
    if process_mode == "ai_first":
        # AI-first: Fast execution, 3-7 days
        project_deadline = today + timedelta(days=7)
    elif process_mode == "vibe_coding":
        # Vibe coding: 2-3 weeks
        project_deadline = today + timedelta(days=21)
    else:
        # Human-paced: 1-2 months
        project_deadline = today + timedelta(days=60)
    
    # Build prompt context
    prompt_context = f"""
PROJECT CONTEXT:
==============
Project Token: {project_token}
Project Name: {context.get('project_name', 'Untitled Project')}
Project Type: {context['project_type']}
Process Mode: {process_mode}
Current Date: {today.strftime('%Y-%m-%d')}
Target Deadline: {project_deadline.strftime('%Y-%m-%d')}

BRD ANALYSIS (COMPLETE REQUIREMENTS):
===================================
{context['brd_analysis'][:4000] if context['brd_analysis'] else 'No BRD analysis available'}

EXTRACTED TECH STACK:
====================
{context['tech_stack'] if context['tech_stack'] else 'Not specified - use best practices based on requirements'}

DETAILED REQUIREMENTS:
=====================
{context['requirements'][:2500] if context['requirements'] else 'Extract from BRD analysis above'}

BUSINESS RULES & CONSTRAINTS:
============================
{context.get('business_rules', 'Extract from BRD analysis above')[:1500]}

USER PERSONAS & ROLES:
=====================
{context.get('user_personas', 'Extract from BRD analysis above')[:1000]}

FUNCTIONAL REQUIREMENTS:
=======================
{context.get('functional_requirements', 'Extract from BRD analysis above')[:2000]}

NON-FUNCTIONAL REQUIREMENTS:
===========================
{context.get('non_functional_requirements', 'Extract from BRD analysis above')[:1500]}

GOVERNANCE CONTEXT:
==================
Classification: {context['governance_context'].get('classification', 'N/A')}
Weighted Score: {context['governance_context'].get('weighted_score', 'N/A')}
Business Value: {context['governance_context'].get('business_value_score', 'N/A')}
Data Sensitivity: {context['governance_context'].get('data_sensitivity_score', 'N/A')}
Integration Complexity: {context['governance_context'].get('integration_complexity_score', 'N/A')}
Operational Impact: {context['governance_context'].get('operational_impact_score', 'N/A')}
AI Risk Score: {context['governance_context'].get('ai_risk_score', 'N/A')}
Recommendation: {str(context['governance_context'].get('recommendation') or 'N/A')[:500]}

CUSTOM RULES:
============
{custom_rules if custom_rules else 'None'}

PREREQUISITES (user-confirmed only - treat these as the ONLY known prerequisites):
=============
{prereq_text}

IMPORTANT: The PREREQUISITES section above contains ONLY what the user has explicitly confirmed is available.
Do NOT infer or assume additional prerequisites from the BRD analysis text.
Tasks must be designed around what is confirmed above.

CRITICAL TASK GENERATION RULES:
==============================
1. ONLY create tasks for requirements EXPLICITLY stated in the BRD
2. DO NOT add tasks for deployment, security, or infrastructure unless the BRD specifically requires them
3. DO NOT pad task counts - if 1 task fulfills the requirement, create only 1 task
4. Tasks must be SPECIFIC to the exact features described in the BRD
5. Use the EXACT terminology and feature names from the BRD analysis
6. Create tasks that implement the PRECISE business logic described

TASK GENERATION INSTRUCTIONS:
============================
Based on the above context, generate ONLY the tasks needed to deliver what is specified in the BRD.

Focus on:
1. EXACT implementation of every BRD requirement (nothing more, nothing less)
2. Proper task hierarchy and dependencies
3. Realistic timelines within the {project_deadline.strftime('%Y-%m-%d')} deadline
4. Specific, actionable checklist items that implement the precise business logic
5. Minimal viable implementation - avoid gold-plating or over-engineering

Generate tasks now:
"""
    
    messages = [
        {"role": "system", "content": INTELLIGENT_TASK_GENERATION_PROMPT},
        {"role": "user", "content": prompt_context}
    ]
    
    logger.info(f"Generating tasks for project {project_token} using {process_mode} mode")
    
    try:
        # Call LLM
        response_content = await llm_gateway.call_llm_and_extract(
            messages=messages,
            api_url=api_url,
            api_key=api_key,
            model=model,
            timeout=180.0
        )
        
        # Parse tasks
        tasks = _parse_task_json(response_content)
        
        if not tasks:
            logger.error("No tasks generated by LLM")
            logger.error(f"LLM Response (first 1000 chars): {response_content[:1000]}")
            return []
        
        logger.info(f"Parsed {len(tasks)} tasks from LLM response")
        
        # Validate and filter tasks with bulletproof enhancement
        valid_tasks = []
        rejected_tasks = []
        
        for task in tasks:
            if _validate_task_structure(task):
                # Ensure required fields have defaults
                task.setdefault("assignedTo", [])
                task.setdefault("sprint", "new")
                task.setdefault("milestone", "main")
                task.setdefault("reported_by", "system")
                task.setdefault("priority", "medium")
                task.setdefault("linked_tasks", [])
                
                # Ensure dates are strings
                if "startdate" not in task:
                    task["startdate"] = today.strftime('%Y-%m-%d')
                if "planned_start" not in task:
                    task["planned_start"] = task["startdate"]
                if "deadline" not in task:
                    # Set deadline based on wallet
                    days_offset = min(task["task_wallet"], 7)
                    task["deadline"] = (today + timedelta(days=days_offset)).strftime('%Y-%m-%d')
                
                valid_tasks.append(task)
            else:
                rejected_tasks.append(task.get("task_id", "unknown"))
        
        if rejected_tasks:
            logger.warning(f"Rejected {len(rejected_tasks)} tasks due to validation failures: {rejected_tasks}")
        
        if not valid_tasks:
            logger.error(f"All {len(tasks)} tasks were rejected during validation")
            logger.error(f"Sample rejected task: {tasks[0] if tasks else 'None'}")
            raise Exception(f"All generated tasks failed validation. Check that the AI is generating required fields: task_id, taskName, task_type, description")
        
        # Apply bulletproof post-processing
        bulletproof_tasks = _bulletproof_task_generation_post_process(valid_tasks)
        
        logger.info(f"Generated {len(bulletproof_tasks)} bulletproof tasks for project {project_token} ({len(rejected_tasks)} rejected)")
        
        return bulletproof_tasks
    
    except Exception as e:
        logger.error(f"Task generation failed: {e}")
        raise Exception(f"Failed to generate tasks: {str(e)}")

def _extract_tech_stack_from_analysis(analysis_text: str) -> str:
    """Extract technology stack from BRD analysis text"""
    if not analysis_text:
        return ""
    
    text_lower = analysis_text.lower()
    
    # Look for explicit tech stack mentions
    tech_indicators = {
        "frontend": ["react", "vue", "angular", "next.js", "svelte", "html", "css", "javascript", "typescript"],
        "backend": ["fastapi", "django", "flask", "express", "spring", "rails", "laravel", ".net", "node.js"],
        "database": ["postgresql", "mysql", "mongodb", "sqlite", "redis", "dynamodb"],
        "cloud": ["aws", "azure", "gcp", "docker", "kubernetes"],
        "mobile": ["react native", "flutter", "swift", "kotlin", "ionic"]
    }
    
    detected_stack = []
    for category, technologies in tech_indicators.items():
        found_techs = [tech for tech in technologies if tech in text_lower]
        if found_techs:
            detected_stack.append(f"{category.title()}: {', '.join(found_techs)}")
    
    return "; ".join(detected_stack) if detected_stack else ""

def _extract_detailed_requirements_from_analysis(analysis_text: str) -> str:
    """Extract detailed requirements from BRD analysis"""
    if not analysis_text:
        return ""
    
    # Look for requirement sections
    requirement_patterns = [
        r"requirements?[:\s]+(.*?)(?=\n\n|\n[A-Z]|$)",
        r"features?[:\s]+(.*?)(?=\n\n|\n[A-Z]|$)",
        r"functionality[:\s]+(.*?)(?=\n\n|\n[A-Z]|$)",
        r"capabilities[:\s]+(.*?)(?=\n\n|\n[A-Z]|$)"
    ]
    
    import re
    extracted_requirements = []
    
    for pattern in requirement_patterns:
        matches = re.findall(pattern, analysis_text, re.IGNORECASE | re.DOTALL)
        extracted_requirements.extend(matches)
    
    return "\n".join(extracted_requirements[:3])  # Limit to avoid token overflow

def _extract_business_rules_from_analysis(analysis_text: str) -> str:
    """Extract business rules and constraints from BRD analysis"""
    if not analysis_text:
        return ""
    
    import re
    
    # Look for business rule patterns
    rule_patterns = [
        r"business rules?[:\s]+(.*?)(?=\n\n|\n[A-Z]|$)",
        r"constraints?[:\s]+(.*?)(?=\n\n|\n[A-Z]|$)",
        r"policies[:\s]+(.*?)(?=\n\n|\n[A-Z]|$)",
        r"validation[:\s]+(.*?)(?=\n\n|\n[A-Z]|$)"
    ]
    
    extracted_rules = []
    for pattern in rule_patterns:
        matches = re.findall(pattern, analysis_text, re.IGNORECASE | re.DOTALL)
        extracted_rules.extend(matches)
    
    return "\n".join(extracted_rules[:2])

def _extract_user_personas_from_analysis(analysis_text: str) -> str:
    """Extract user personas and roles from BRD analysis"""
    if not analysis_text:
        return ""
    
    import re
    
    # Look for user/persona patterns
    persona_patterns = [
        r"users?[:\s]+(.*?)(?=\n\n|\n[A-Z]|$)",
        r"personas?[:\s]+(.*?)(?=\n\n|\n[A-Z]|$)",
        r"roles?[:\s]+(.*?)(?=\n\n|\n[A-Z]|$)",
        r"actors?[:\s]+(.*?)(?=\n\n|\n[A-Z]|$)"
    ]
    
    extracted_personas = []
    for pattern in persona_patterns:
        matches = re.findall(pattern, analysis_text, re.IGNORECASE | re.DOTALL)
        extracted_personas.extend(matches)
    
    return "\n".join(extracted_personas[:2])

def _extract_functional_requirements_from_analysis(analysis_text: str) -> str:
    """Extract functional requirements from BRD analysis"""
    if not analysis_text:
        return ""
    
    import re
    
    # Look for functional requirement patterns
    functional_patterns = [
        r"functional requirements?[:\s]+(.*?)(?=\n\n|\n[A-Z]|$)",
        r"system shall[:\s]+(.*?)(?=\n\n|\n[A-Z]|$)",
        r"the system must[:\s]+(.*?)(?=\n\n|\n[A-Z]|$)",
        r"functionality[:\s]+(.*?)(?=\n\n|\n[A-Z]|$)"
    ]
    
    extracted_functional = []
    for pattern in functional_patterns:
        matches = re.findall(pattern, analysis_text, re.IGNORECASE | re.DOTALL)
        extracted_functional.extend(matches)
    
    return "\n".join(extracted_functional[:3])

def _extract_non_functional_requirements_from_analysis(analysis_text: str) -> str:
    """Extract non-functional requirements from BRD analysis"""
    if not analysis_text:
        return ""
    
    import re
    
    # Look for non-functional requirement patterns
    nfr_patterns = [
        r"non-?functional requirements?[:\s]+(.*?)(?=\n\n|\n[A-Z]|$)",
        r"performance[:\s]+(.*?)(?=\n\n|\n[A-Z]|$)",
        r"security[:\s]+(.*?)(?=\n\n|\n[A-Z]|$)",
        r"scalability[:\s]+(.*?)(?=\n\n|\n[A-Z]|$)",
        r"availability[:\s]+(.*?)(?=\n\n|\n[A-Z]|$)"
    ]
    
    extracted_nfr = []
    for pattern in nfr_patterns:
        matches = re.findall(pattern, analysis_text, re.IGNORECASE | re.DOTALL)
        extracted_nfr.extend(matches)
    
    return "\n".join(extracted_nfr[:2])
def _validate_bulletproof_task(task: Dict[str, Any]) -> Dict[str, Any]:
    """Validate task for 90%+ execution success guarantee"""
    
    validation_result = {
        "valid": True,
        "score": 100,
        "issues": [],
        "suggestions": []
    }
    
    # Check task name length and clarity
    task_name = task.get("taskName", "")
    if len(task_name) > 35:
        validation_result["score"] -= 10
        validation_result["issues"].append("Task name too long (>35 chars)")
        validation_result["suggestions"].append("Shorten task name to 15-25 characters")
    
    if not task_name or "TASK:" not in task_name:
        validation_result["score"] -= 20
        validation_result["issues"].append("Invalid task name format")
        validation_result["suggestions"].append("Use format: 'TASK: Short Description'")
    
    # Check description specificity
    description = task.get("description", "")
    if len(description) < 100:
        validation_result["score"] -= 15
        validation_result["issues"].append("Task description too vague")
        validation_result["suggestions"].append("Add specific implementation details")
    
    # Check checklist quality
    checklist_str = task.get("checklist", "{}")
    try:
        checklist_data = json.loads(checklist_str) if isinstance(checklist_str, str) else checklist_str
        checklist_items = checklist_data.get("checklistItems", [])
        
        if len(checklist_items) < 3:
            validation_result["score"] -= 20
            validation_result["issues"].append("Insufficient checklist items")
            validation_result["suggestions"].append("Add at least 3-5 specific implementation steps")
        
        # Check checklist item quality
        vague_patterns = ["implement", "create", "add", "setup", "configure"]
        specific_patterns = ["mkdir", "npm install", "cat <<", "echo", "curl", "python"]
        
        vague_count = 0
        specific_count = 0
        
        for item in checklist_items:
            item_text = item.get("text", "").lower()
            if any(pattern in item_text for pattern in vague_patterns):
                vague_count += 1
            if any(pattern in item_text for pattern in specific_patterns):
                specific_count += 1
        
        if vague_count > specific_count:
            validation_result["score"] -= 25
            validation_result["issues"].append("Checklist items too vague")
            validation_result["suggestions"].append("Use specific commands and file paths")
        
    except Exception as e:
        validation_result["score"] -= 30
        validation_result["issues"].append("Invalid checklist format")
        validation_result["suggestions"].append("Fix checklist JSON structure")
    
    # Check task wallet (complexity)
    wallet = task.get("task_wallet", 0)
    task_type = task.get("task_type", "")
    
    if task_type == "TASK" and wallet > 2:
        validation_result["score"] -= 10
        validation_result["issues"].append("Task too complex (wallet > 2)")
        validation_result["suggestions"].append("Break into smaller tasks")
    
    # Check for stack-specific requirements
    if "database" in description.lower() and "migration" not in description.lower():
        validation_result["score"] -= 5
        validation_result["suggestions"].append("Consider adding database migration steps")
    
    if "api" in description.lower() and "test" not in description.lower():
        validation_result["score"] -= 5
        validation_result["suggestions"].append("Consider adding API testing steps")
    
    # Final validation
    if validation_result["score"] < 70:
        validation_result["valid"] = False
    
    return validation_result

def _enhance_task_for_bulletproof_execution(task: Dict[str, Any]) -> Dict[str, Any]:
    """Enhance task to guarantee 90%+ execution success - NO FORCED ADDITIONS"""
    
    enhanced_task = dict(task)
    
    # Only add bulletproof requirements if they're genuinely missing and critical
    description = enhanced_task.get("description", "")
    task_type = enhanced_task.get("task_type", "")
    
    if task_type == "TASK":
        # Only add critical missing elements, don't pad unnecessarily
        bulletproof_additions = []
        
        # Only add error handling if it's a backend/API task and not mentioned
        if "error" not in description.lower() and any(keyword in description.lower() for keyword in ["api", "endpoint", "service", "backend"]):
            bulletproof_additions.append("Include error handling for edge cases.")
        
        if bulletproof_additions:
            enhanced_task["description"] = f"{description}\n\nBULLETPROOF REQUIREMENTS:\n" + "\n".join(f"- {req}" for req in bulletproof_additions)
    
    # DO NOT add generic checklist items - keep only what the AI generated
    # The checklist should already be complete from the AI generation
    
    return enhanced_task

def _bulletproof_task_generation_post_process(tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Post-process generated tasks for bulletproof execution"""
    
    bulletproof_tasks = []
    
    for task in tasks:
        # Validate task quality
        validation = _validate_bulletproof_task(task)
        
        if validation["valid"]:
            # Enhance task for bulletproof execution
            enhanced_task = _enhance_task_for_bulletproof_execution(task)
            bulletproof_tasks.append(enhanced_task)
        else:
            # Log validation issues but still include task with warnings
            logger.warning(f"Task validation issues for {task.get('task_id', 'unknown')}: {validation['issues']}")
            
            # Apply suggestions automatically where possible
            if "Shorten task name" in str(validation["suggestions"]):
                task_name = task.get("taskName", "")
                if len(task_name) > 35:
                    # Truncate task name
                    task["taskName"] = task_name[:32] + "..."
            
            enhanced_task = _enhance_task_for_bulletproof_execution(task)
            bulletproof_tasks.append(enhanced_task)
    
    return bulletproof_tasks
