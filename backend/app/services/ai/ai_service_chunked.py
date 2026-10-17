"""
AI Service with Intelligent Chunking Strategy
Maintains the same BRD analysis quality while reducing payload size through multi-stage processing
"""
import asyncio
import json
import re
from typing import Dict, Any, Optional, List, Tuple  # Added Tuple for type hinting
from datetime import datetime
import logging
from app.integrations.llm import llm_gateway
from app.core.llm_logs import log_llm_interaction_ai_service

logger = logging.getLogger(__name__)

def _get_job(job_id: Optional[str]):
    if not job_id:
        return None
    try:
        import sys
        for mod_name in ("analysis_job_manager", "app.workers.analysis_job_manager"):
            if mod_name in sys.modules:
                mod = sys.modules[mod_name]
                if hasattr(mod, "get_job_manager"):
                    mgr = mod.get_job_manager()
                    job = mgr.get_job(job_id) if mgr else None
                    if job:
                        return job
        try:
            import analysis_job_manager
            mgr = analysis_job_manager.get_job_manager()
            job = mgr.get_job(job_id) if mgr else None
            if job:
                return job
        except ImportError:
            pass
        from app.workers.analysis_job_manager import get_job_manager as _gjm
        mgr = _gjm()
        return mgr.get_job(job_id) if mgr else None
    except Exception as e:
        logger.warning(f"Failed to lookup analysis job {job_id}: {e}")
        return None

# ─────────────────────────────────────────────────────────────────────────────
# PREREQUISITES CONFIGURATION & HELPERS
# ─────────────────────────────────────────────────────────────────────────────

PREREQUISITE_CATEGORIES: List[Tuple[str, str]] = [
    ("credentials", "API keys, authentication tokens, SMTP credentials"),
    ("apis", "Third-party API integrations"),
    ("infrastructure", "Servers, domains, SSL certificates"),
    ("databases", "Database credentials, connection strings"),
    ("cloud", "Cloud accounts, CDN (only if specified in BRD)"),
    ("dependencies", "Private package registries, licensed libraries"),
]

def _build_prerequisite_instruction_text() -> str:
    """Construct the prerequisite description block dynamically for the prompt."""
    lines = [
        "### 2. Prerequisites & Credentials",
        "List **only** the prerequisites that are explicitly derived from the BRD features. "
        "Do NOT invent requirements. If the BRD does not mention a specific service (e.g., SMS, Cloud Storage), do not list it as a prerequisite.",
        "Use the following logic:",
        "- If BRD mentions 'Email/Notification', add SMTP or Notification Service credentials.",
        "- If BRD mentions 'Payment', add Payment Gateway credentials.",
        "- If BRD mentions 'User Login', add Authentication credentials/keys.",
        "",
        "Categories:"
    ]
    for cat, desc in PREREQUISITE_CATEGORIES:
        lines.append(f"- **{cat}**: {desc}")
    lines.append("\nList each prerequisite with its category and priority.")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════
# STAGE 1: REQUIREMENTS EXTRACTION (Minimal Payload)
# ═══════════════════════════════════════════════════════════════════════════

STAGE_1_REQUIREMENTS_PROMPT = """# ROLE
You are an expert Business Analyst extracting requirements from a BRD document.

## TASK
Analyze the document and extract:

### 1. Core Product Information
- Product name and vision (2-3 sentences)
- Target users and use cases
- Product category and scale expectations

### 2. Functional Requirements
List ALL functional requirements (explicit + implicit):
- User management and authentication needs
- Core business features
- Data management requirements
- Integration requirements
- Reporting/analytics needs

### 3. Non-Functional Requirements
- Performance expectations
- Security requirements
- Scalability needs
- Compliance requirements
- Data integrity rules

### 4. Technical Constraints
- Specified technologies (if any)
- Deployment preferences
- Integration constraints
- Budget/timeline constraints

### 5. Ambiguities & Questions
Generate 3-8 clarification questions about:
- Missing technical details
- Ambiguous requirements
- Integration uncertainties
- Performance targets
- Security specifications

### 6. Development Classification
Classify the project development type:
- If modifying an existing application directly inside its existing structure, classify as "Brownfield".
- If migrating from an existing application to a brand new repository structure, classify as "Migration".
- If building entirely from scratch, classify as "Greenfield".

## CRITICAL TEXT FORMATTING RULES
**USE ONLY STANDARD ASCII CHARACTERS:**
- Use regular hyphen `-` NOT Unicode hyphens (‑, –, —)
- Use regular space NOT Unicode spaces
- Use regular apostrophe `'` NOT Unicode quotes (', ')
- Use `>=` NOT `≥`, use `<=` NOT `≤`
- NO emoji characters or Unicode symbols

## OUTPUT FORMAT
Return ONLY valid JSON (no markdown fences):
{
  "product_name": "...",
  "product_vision": "...",
  "target_users": "...",
  "product_category": "...",
  "scale_expectation": "MVP|Production|Enterprise",
  "functional_requirements": ["req1", "req2", ...],
  "non_functional_requirements": ["req1", "req2", ...],
  "implicit_requirements": ["req1", "req2", ...],
  "technical_constraints": {
    "specified_tech": [],
    "deployment": "...",
    "integrations": []
  },
  "clarification_questions": ["q1", "q2", ...],
  "development_classification": {
    "type": "Greenfield|Brownfield|Migration|Modernization",
    "rationale": "...",
    "existing_codebase_detected": true
  }
}"""

# ═══════════════════════════════════════════════════════════════════════════
# STAGE 2: TECHNOLOGY & ARCHITECTURE DESIGN (Focused Payload)
# ═══════════════════════════════════════════════════════════════════════════

STAGE_2_ARCHITECTURE_PROMPT = """# ROLE
You are an expert Enterprise Software Architect designing technical architecture.

## CONTEXT
You will receive extracted requirements from Stage 1 (and existing repository context if Brownfield/Migration).

## TASK
Design the technical architecture:

### 1. Technology Stack Selection
Recommend a complete, production-grade stack with rationale:
- **IF BROWNFIELD**: You MUST detect and preserve the existing technology stack, language, framework, and database from the provided repository context unless the BRD explicitly requests adding a new service.
- **DATABASE & PREVIEW DEPLOYMENT RULE (CRITICAL FOR GREENFIELD & MODERNIZATION)**:
  * For GREENFIELD and MODERNIZATION projects, architect a **Dual-Mode Relational Persistence Layer** using the stack's standard ORM (e.g., SQLAlchemy for Python/FastAPI, Prisma/Drizzle for Node/TypeScript):
    1. **Preview / Default Mode (Zero-Config)**: Default `DATABASE_URL` to embedded **SQLite** (`sqlite:///./app.db`) so the application can be built, migrated, seeded, and previewed immediately in any container without external database credentials.
    2. **Enterprise Production Mode**: Support seamless switchover to **PostgreSQL 16** solely by overriding the `DATABASE_URL` environment variable.
  * **Portable Schema Mandate**: In all LLD SQL DDL and ORM schemas, use portable ANSI SQL types (`VARCHAR(36)` for UUIDs generated in application code, `TIMESTAMP`, `NUMERIC`, `TEXT`/`JSON`). Do NOT use database-engine-locked extensions (like `gen_random_uuid()` or PL/pgSQL triggers) that would fail in SQLite preview mode.
  * **Auto-Bootstrap on Startup**: The backend MUST automatically initialize tables and seed realistic demo data on startup if the database is empty, guaranteeing a working, populated live preview.
  * **Third-Party Service Fallbacks**: Do NOT inject Redis, Kafka, or microservices unless justified by scale or async requirements in the BRD. If caching, messaging, or email are used, implement the Adapter Fallback Pattern (in-memory cache fallback if `REDIS_URL` is unset, console/DB logger if `SMTP_API_KEY` is unset).
- Cover: Frontend framework & UI library, Backend framework & language, Database (with Dual-Mode ORM strategy), Caching/Queue (only if required, with fallback), Authentication method, API documentation tool, Containerization approach.

Format as table:
| Layer | Technology | Version | Rationale |

### 2. Architecture Pattern
- Choose pattern: Monolith / Modular Monolith / Microservices / Strangler Fig (for Modernization)
- Justify based on requirements and project type (Greenfield vs. Brownfield vs. Modernization)
- Describe component interaction model

### 3. User Flow Diagram (Functional View for Business Users)
Create a COMPLETE Mermaid `flowchart TB` showing the USER JOURNEY and BUSINESS PROCESSES.
The diagram MUST show:
- **User Roles**: Different types of users (Admin, Customer, Manager, Guest, etc.)
- **User Actions**: What users can do (Login, Submit Form, View Dashboard, etc.)
- **Business Processes**: Key workflows (Order Processing, Approval Flow, Notification, etc.)
- **Decision Points**: Business rules and conditions (diamond shapes)
- **System Responses**: What happens after user actions (Success, Error, Notification)
- **External Touchpoints**: Third-party systems users interact with (Payment Gateway, Email Service)

## STRICT Mermaid Safety Rules
1. Every subgraph must have one matching end
2. All edges must be placed after final end
3. NEVER connect to subgraph IDs
4. Use only node-to-node edges
5. Quote all labels
6. Use ASCII characters only
7. Every edge node must exist
8. Node IDs MUST NOT contain spaces or special characters (use underscores or camelCase)

### 4. Technical System Architecture JSON (Component Graph for Agents)
Provide the ACTUAL technical system components (Frontend, API Gateway, Backend Services, Databases, External APIs) so downstream coding and architecture agents have a true system topology:
{
  "nodes": [
    {"id": "node_id", "label": "Specific Technical Component (e.g., FastAPI Backend, PostgreSQL DB)", "layer": "frontend|backend|service|data|integration|infra", "type": "service|database|queue|cache|external|ui"}
  ],
  "edges": [
    {"from": "source_id", "to": "target_id", "description": "protocol or data flow"}
  ]
}

## CRITICAL TEXT FORMATTING RULES
**USE ONLY STANDARD ASCII CHARACTERS:**
- Use regular hyphen `-` NOT Unicode hyphens
- Use regular space NOT Unicode spaces
- Use regular apostrophe `'` NOT Unicode quotes
- Use `>=` and `<=`
- NO emoji characters or Unicode symbols

## OUTPUT FORMAT
Return ONLY valid JSON:
{
  "tech_stack": [
    {"layer": "...", "technology": "...", "version": "...", "rationale": "..."}
  ],
  "architecture_pattern": "...",
  "architecture_justification": "...",
  "component_interaction": "...",
  "mermaid_flowchart": "flowchart TB\\n...",
  "architecture": {
    "nodes": [...],
    "edges": [...]
  }
}"""

# ═══════════════════════════════════════════════════════════════════════════
# STAGE 3: DATA MODELS & API DESIGN (Focused Payload)
# ═══════════════════════════════════════════════════════════════════════════

STAGE_3_DATA_API_PROMPT = """# ROLE
You are an expert Database Architect and API Designer.

## CONTEXT
You will receive:
- Requirements from Stage 1
- Architecture from Stage 2

## TASK
Design data models and APIs:

### 1. Data Models
Create Mermaid ER diagram with:
- All entities and their attributes
- Relationships (1-to-1, 1-to-many, many-to-many)
- Key constraints

**ER Diagram Rules:**
- Use `erDiagram` (no `end` keyword needed)
- Use proper relationship syntax: ||--o{, }}o--||, etc.
- Quote attribute names with spaces
- ONLY use 'PK' or 'FK' (or 'PK, FK') for key annotations. Do NOT use 'UQ', 'UK', 'NN', or other unsupported annotations. Attribute format: datatype attribute_name PK/FK (e.g. "int id PK", "string name", "int user_id FK"). ALWAYS place PK/FK AFTER the attribute name, NEVER before.
### 2. Validation Rules
List business validation rules:
- Field validations
- Business logic constraints
- Data integrity rules

### 3. API Endpoints
Create comprehensive endpoint table:
| Method | Path | Purpose | Auth Required | Request Body | Response |

Group by domain (Auth, Users, Core Features, Admin)

## CRITICAL TEXT FORMATTING RULES
**USE ONLY STANDARD ASCII CHARACTERS:**
- Use regular hyphen `-` NOT Unicode hyphens (‑, –, —)
- Use regular space NOT Unicode spaces
- Use regular apostrophe `'` NOT Unicode quotes (', ')
- Use `>=` NOT `≥`, use `<=` NOT `≤`
- NO emoji characters or Unicode symbols

## OUTPUT FORMAT
Return ONLY valid JSON:
{
  "mermaid_er_diagram": "erDiagram\\n...",
  "validation_rules": ["rule1", "rule2", ...],
  "api_endpoints": [
    {"method": "GET", "path": "/api/...", "purpose": "...", "auth": "required|optional|none", "domain": "..."}
  ]
}"""

# ═══════════════════════════════════════════════════════════════════════════
# STAGE 4: IMPLEMENTATION PLAN (Focused Payload)
# ═══════════════════════════════════════════════════════════════════════════

STAGE_4_IMPLEMENTATION_PROMPT = f"""# ROLE
You are an expert Implementation Planner.

## CONTEXT
You will receive:
- Requirements from Stage 1
- Architecture from Stage 2
- Data/API design from Stage 3

## TASK
Create implementation plan:

### 1. Repository Structure
Provide COMPLETE file tree with inline comments.
Include: backend, frontend, config, tests, docs, CI/CD

CRITICAL: The repository structure tree MUST start directly with the root-level files and directories of the project (e.g. `src/`, `backend/`, `package.json`, `.gitignore`). Do NOT wrap the entire structure in a top-level parent folder named after the project.

Define the repository structure based on the project type:
- **BROWNFIELD**: DO NOT generate a complete repository file tree from scratch. You MUST work directly within the existing repository structure and files. Generate an impact analysis tree showing ONLY the files that need to be created, modified, or deleted within the existing architecture. You MUST use the `existing_repository_structure` provided in the context to map all existing files and paths correctly. DO NOT make up paths or package directories that do not exist.
- **MIGRATION / MODERNIZATION**: Plan a new repository structure (from scratch). You should use the `existing_repository_structure` (if provided in the context) to map the source files and structure to the new destination repository structure.
- **GREENFIELD**: Plan a new repository structure (from scratch). If an `existing_repository_structure` is provided in the context, you MUST analyze it first to understand the functionalities already implemented in the previous repository, and use that knowledge to design the new repository structure.

{_build_prerequisite_instruction_text()}

### 3. Implementation Phases
Define ordered phases:
- Foundation (setup, structure, config)
- Backend Core (auth, base models, middleware)
- Backend Features (feature endpoints)
- Frontend Core (routing, state, auth UI)
- Frontend Features (feature components)
- Integration (testing, deployment)

### 4. File Creation Plan
Table of ALL files to create:
| File Path | Purpose | Content Type | Priority | Phase |

### 5. Implementation Guidelines
List 8-12 coding rules:
- Framework best practices
- Security standards
- Error handling patterns
- Testing requirements
- Naming conventions

## CRITICAL TEXT FORMATTING RULES
**USE ONLY STANDARD ASCII CHARACTERS:**
- Use regular hyphen `-` NOT Unicode hyphens (‑, –, —)
- Use regular space NOT Unicode spaces
- Use regular apostrophe `'` NOT Unicode quotes (', ')
- Use `>=` NOT `≥`, use `<=` NOT `≤`
- NO emoji characters or Unicode symbols

## OUTPUT FORMAT
Return ONLY valid JSON:
{{
  "repository_structure": "...",
  "prerequisites": [
     {{
       "name": "Specific Prerequisite Name",
       "description": "Why this is needed based on BRD functional requirements.",
       "category": "credentials | apis | infrastructure | databases | cloud | dependencies",
       "priority": "high | medium | low"
     }}
  ],
  "implementation_phases": [
    {{"phase": "...", "description": "...", "deliverables": [...]}}
  ],
  "file_creation_plan": [...],
  "implementation_guidelines": [...]
}}"""

# ═══════════════════════════════════════════════════════════════════════════
# STAGE 5: FINAL SYNTHESIS & REPORT GENERATION (Minimal Payload)
# ═══════════════════════════════════════════════════════════════════════════

STAGE_5_SYNTHESIS_PROMPT = """# ROLE
You are an expert Technical Writer synthesizing a comprehensive BRD Analysis Report.

## CONTEXT
You will receive outputs from all previous stages.

## TASK
Create a comprehensive Markdown report with these sections:

# BRD Analysis Report

## 0.1 Product Understanding
[Use Stage 1 data. Format this section as a structured list of bold items (e.g. **Product Name**, **Vision**, **Target Users**, **Product Category**, etc.) followed by descriptive sentences. DO NOT format this section as a table.]

## 0.2 Background Research
[Synthesize from Stage 2 tech stack rationale]

## 0.3 Technical Architecture Design
[Use Stage 2 architecture + Mermaid user flow diagram]

**IMPORTANT**: The Mermaid diagram should be a FUNCTIONAL USER FLOW diagram showing:
- User roles and their journeys
- Business processes and workflows
- User actions and decisions
- System responses and notifications
- Business outcomes

NOT a technical architecture diagram with databases, APIs, and servers.

## 0.4 Implementation Specifications
### 0.4.1 Core Components
[Derive from Stage 2 architecture]

### 0.4.2 Data Models and Schemas
[Use Stage 3 ER diagram]

### 0.4.3 API Specifications
[Use Stage 3 API endpoints]

## 0.5 Repository Structure Planning
[Use Stage 4 file tree EXACTLY AS PROVIDED]

CRITICAL: If the Stage 4 tree is a "BROWNFIELD IMPACT ANALYSIS", output it exactly as is without modifying the structure. For Greenfield projects, the repository structure tree MUST start directly with the root-level files and directories of the project (e.g. `src/`, `backend/`, `package.json`, `.gitignore`). Do NOT wrap the entire structure in a top-level parent folder named after the project.

## 0.6 Scope Definition
[Derive from Stage 1 requirements]

## 0.7 Deliverable Mapping
[Use Stage 4 file creation plan and phases]

## 0.8 Risks & Gap Analysis
[Analyze based on all stages. Format this section as a structured list of bold risk items followed by detailed mitigation sentences. DO NOT use a table.]

## 0.9 Clarification Questions
[Use Stage 1 questions]

## 0.10 Prerequisites & Credentials
[Use Stage 4 prerequisites. Group them logically by category (credentials, apis, infrastructure, databases, cloud, dependencies). Format each category as a clean bulleted list showing name, description, and priority in sentences. DO NOT use a table.]

## 0.11 Execution Patterns
[Use Stage 4 implementation guidelines]

## 0.12 Go / No-Go Recommendation
**[GO / NO-GO / PROCEED WITH CAUTION]**
[Provide recommendation based on analysis]

## 0.13 Revision Delta & Impact Analysis
(Include ONLY if document content contains multiple revisions or PREVIOUS REVISION headers)
- **Comparison Summary**: One sentence describing how the current revision differs from previous revisions.
- **Modified / Overridden Requirements**: Bulleted list of exact features/requirements updated or replaced from previous revisions.
- **Newly Added Capabilities**: Bulleted list of exact new features introduced in this revision.
- **Scope Divergence / Pivot Evaluation**: State whether this revision pivots to a completely different product domain.

---

## CRITICAL TEXT FORMATTING RULES
**YOU MUST FOLLOW THESE FORMATTING RULES TO ENSURE PDF COMPATIBILITY:**

1. **USE ONLY STANDARD ASCII CHARACTERS**: 
   - Use regular hyphen `-` NOT Unicode hyphens (‑, –, —)
   - Use regular space ` ` NOT Unicode spaces (  ,  , etc.)
   - Use regular apostrophe `'` NOT Unicode quotes (', ', ", ")
   - Use regular numbers `1, 2, 3` NOT emoji numbers (1️⃣, 2️⃣, 3️⃣)

2. **FORBIDDEN UNICODE CHARACTERS**:
   - NO `\\u2011` (non-breaking hyphen) - use `-`
   - NO `\\u2013` (en dash) - use `-`
   - NO `\\u2014` (em dash) - use `--`
   - NO `\\u202f` (narrow no-break space) - use regular space
   - NO `\\u00a0` (non-breaking space) - use regular space
   - NO `\\ufe0f\\u20e3` (emoji keycaps) - use plain numbers
   - NO `\\u2265` (greater than or equal) - use `>=`
   - NO fancy Unicode bullets - use `-` or `*`

3. **TABLE FORMATTING**:
   - Write all table cell content with normal words and spacing
   - Example CORRECT: `| Product Name | Pegasus Platform |`
   - Example WRONG: `| P r o d u c t   N a m e | P e g a s u s |`

4. **LIST FORMATTING**:
   - Use standard Markdown bullets: `-` or `*`
   - Use standard numbers: `1.`, `2.`, `3.`
   - NO emoji bullets or fancy Unicode list markers

5. **EMPHASIS**:
   - Use `**bold**` for bold text
   - Use `*italic*` for italic text
   - NO Unicode bold/italic characters

## OUTPUT FORMAT
Return the complete Markdown report followed by a JSON block:

```json
{{
  "title": "...",
  "metrics": {{
    "complexity": "Low|Medium|High",
    "timeline": "...",
    "deployment": "...",
    "resources": "...",
    "project_type": "greenfield|brownfield|modernization" // MUST MATCH the classification from Stage 1
  }},
  "questions": [...],
  "prerequisites": [...],
  "user_flow": "...",
  "implementation_structure": "...",
  "revision_delta": {{
    "is_revision": true,
    "comparison_summary": "...",
    "overridden_features": ["item 1", "item 2"],
    "new_features": ["item 1", "item 2"],
    "pivot_recommended": false,
    "pivot_reason": ""
  }},
  "architecture": {{
    "nodes": [...],
    "edges": [...]
  }}
}}
```"""

# ═══════════════════════════════════════════════════════════════════════════
# ASYNCHRONOUS ARCHITECTURE SPECIFICATION WORKER (HLD & LLD)
# ═══════════════════════════════════════════════════════════════════════════

def _persist_specs_to_db(
    job_id: Optional[str],
    document_id: Optional[int],
    hld_data: Optional[Dict[str, Any]] = None,
    lld_data: Optional[Dict[str, Any]] = None,
    spec_status: Optional[Dict[str, str]] = None
) -> Optional[int]:
    """
    Persist HLD, LLD, and spec_status directly to the database document as soon as available.
    Finds document either by explicit document_id or by querying analysis_result JSON containing job_id.
    """
    try:
        from app.core.database import SessionLocal
        import models
        with SessionLocal() as db:
            doc = None
            if document_id:
                doc = db.query(models.Document).filter(models.Document.id == document_id).first()
            if not doc and job_id:
                doc = db.query(models.Document).filter(models.Document.analysis_result.contains(job_id)).order_by(models.Document.id.desc()).first()

            if doc and doc.analysis_result:
                try:
                    parsed = json.loads(doc.analysis_result)
                except Exception:
                    parsed = {}
                if not isinstance(parsed, dict):
                    parsed = {}

                if hld_data:
                    parsed["hld"] = hld_data
                if lld_data:
                    parsed["lld"] = lld_data
                if spec_status:
                    existing_status = parsed.get("spec_status") or {}
                    existing_status.update(spec_status)
                    parsed["spec_status"] = existing_status
                if job_id and not parsed.get("_jobId"):
                    parsed["_jobId"] = job_id

                doc.analysis_result = json.dumps(parsed)
                db.add(doc)
                db.commit()
                db.refresh(doc)
                logger.info(f"[{job_id}] Persisted specs to DB document {doc.id} (status: {spec_status}, has_hld={bool(hld_data)}, has_lld={bool(lld_data)})")
                return doc.id
    except Exception as db_err:
        logger.warning(f"Failed to persist specs to database (job_id={job_id}, doc_id={document_id}): {db_err}")
    return None


async def generate_architecture_specs_background(
    job_id: Optional[str],
    brd_content: str,
    analysis_meta: Dict[str, Any],
    project_label: str,
    document_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Background worker that synthesizes High-Level Design (HLD) and Low-Level Design (LLD)
    asynchronously so the user can immediately interact with the Stage 1-5 BRD Analysis Report.
    Updates the AnalysisJob stages/spec_status as each document completes, and progressively
    persists each document to the database the instant it finishes.
    """
    job = _get_job(job_id) if job_id else None
    hld_data = None
    lld_data = None

    try:
        from app.services.ai.architecture_design_service import architecture_design_service
        if job:
            job.update_spec_status("hld", "generating")
            job.update_progress(92, f"Generating High-Level Design (HLD) for {project_label}...")

        # Record initial background generating status in DB
        _persist_specs_to_db(
            job_id,
            document_id,
            spec_status={"analysis_report": "ready", "hld": "generating", "lld": "pending"}
        )

        hld_res = await architecture_design_service.generate_high_level_design(
            brd_content=brd_content,
            analysis_data=analysis_meta,
            project_name=project_label
        )
        hld_data = {
            "title": f"High-Level Design (HLD) — {project_label}",
            "markdown": hld_res.get("markdown", ""),
            "version": "1.0.0",
            "generated_at": datetime.utcnow().isoformat()
        }
        if job:
            job.update_spec_status("hld", "ready", hld_data)
            logger.info(f"Job {job_id}: High-Level Design (HLD) ready!")

        # STEP 1 INSTANT PERSISTENCE: Save HLD to DB right now!
        saved_id = _persist_specs_to_db(
            job_id,
            document_id,
            hld_data=hld_data,
            spec_status={"analysis_report": "ready", "hld": "ready", "lld": "generating"}
        )
        if saved_id:
            document_id = saved_id

        if job:
            job.update_spec_status("lld", "generating")
            job.update_progress(96, f"Generating Low-Level Design (LLD) for {project_label}...")

        lld_res = await architecture_design_service.generate_low_level_design(
            brd_content=brd_content,
            hld_content=hld_res.get("markdown", ""),
            analysis_data=analysis_meta,
            project_name=project_label
        )
        lld_data = {
            "title": f"Low-Level Design (LLD) — {project_label}",
            "markdown": lld_res.get("markdown", ""),
            "version": "1.0.0",
            "generated_at": datetime.utcnow().isoformat()
        }
        if job:
            job.update_spec_status("lld", "ready", lld_data)
            job.update_progress(100, "All analysis artifacts and specs complete!")
            logger.info(f"Job {job_id}: Low-Level Design (LLD) ready!")

        # STEP 2 INSTANT PERSISTENCE: Save LLD to DB right now!
        _persist_specs_to_db(
            job_id,
            document_id,
            hld_data=hld_data,
            lld_data=lld_data,
            spec_status={"analysis_report": "ready", "hld": "ready", "lld": "ready"}
        )

    except Exception as synth_err:
        logger.warning(f"Background auto-synthesis of HLD/LLD failed for job {job_id}: {synth_err}")
        fail_status = {}
        if job:
            if not hld_data:
                job.update_spec_status("hld", "failed")
                fail_status["hld"] = "failed"
            if not lld_data:
                job.update_spec_status("lld", "failed")
                fail_status["lld"] = "failed"
        _persist_specs_to_db(job_id, document_id, hld_data=hld_data, lld_data=lld_data, spec_status=fail_status)

    return {"hld": hld_data, "lld": lld_data}


# ═══════════════════════════════════════════════════════════════════════════
# MAIN CHUNKED ANALYSIS FUNCTION
# ═══════════════════════════════════════════════════════════════════════════

async def analyze_document_chunked(
    document_content: str,
    api_url: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    governance_context: Optional[Dict[str, Any]] = None,
    stream: bool = False,
    user_feedback: Optional[str] = None,
    image_paths: Optional[List[str]] = None,
    job_id: Optional[str] = None,  # NEW: Optional job ID for progress tracking
) -> Dict[str, Any]:
    """
    Multi-stage chunked analysis that maintains the same output quality
    while reducing payload size per API call.
    
    Strategy:
    1. Extract requirements (small payload)
    2. Design architecture (focused on tech decisions)
    3. Design data models & APIs (focused on data layer)
    4. Create implementation plan (focused on execution)
    5. Synthesize final report (combines all stages)
    
    Args:
        job_id: Optional job ID for progress tracking via job manager
    """
    
    # Helper to update job progress if job_id is provided
    def update_job_progress(progress: int, message: str):
        job = _get_job(job_id)
        if job:
            job.update_progress(progress, message)
    
    if not llm_gateway.check_api_key(api_key):
        error = "API key not configured. Please set AI_API_KEY in your environment."
        return {"status": "error", "error": error}
    
    try:
        update_job_progress(15, "Preparing document content...")
        
        # Extract repository context if present to avoid truncation
        repo_context_text = ""
        repo_marker = "--- REPOSITORY CONTEXT ---"
        if repo_marker in document_content:
            parts = document_content.split(repo_marker)
            # The part after the marker contains the repository context
            if len(parts) > 1:
                repo_context_text = repo_marker + parts[1]
                # Strip it from document_content to leave only the BRD content for truncation
                document_content_brd = parts[0]
            else:
                document_content_brd = document_content
        else:
            document_content_brd = document_content

        # Prepare document content (truncate if too large for Stage 1)
        max_stage1_content = 8000
        stage1_content = document_content_brd[:max_stage1_content]
        if len(document_content_brd) > max_stage1_content:
            stage1_content += "\n\n[Document truncated for initial analysis - full context will be used in later stages]"
        
        # Re-append repository context if it was extracted, so it's always included in Stage 1
        if repo_context_text:
            stage1_content += f"\n\n{repo_context_text}"

        
        # Add governance context if provided
        governance_text = _format_governance_context(governance_context)
        if governance_text:
            stage1_content = f"{stage1_content}\n\n{governance_text}"
        
        # Add user feedback if provided
        if user_feedback:
            stage1_content = f"USER FEEDBACK/ANSWERS:\n{user_feedback}\n\n{stage1_content}"
        
        update_job_progress(20, "Stage 1: Extracting requirements...")
        logger.info("=== STAGE 1: Requirements Extraction ===")
        stage1_messages = [
            {"role": "system", "content": STAGE_1_REQUIREMENTS_PROMPT},
            {"role": "user", "content": f"Extract requirements from this BRD:\n\n{stage1_content}"}
        ]
        
        stage1_result = await llm_gateway.call_llm_and_extract(
            messages=stage1_messages,
            api_url=api_url,
            api_key=api_key,
            model=model,
            timeout=180.0,
            retries=3,
            retry_delay=5.0,
            purpose="BRD Analysis & Architecture",
        )
        
        stage1_data = _extract_json_from_response(stage1_result)
        logger.info(f"Stage 1 complete: Extracted {len(stage1_data.get('functional_requirements', []))} functional requirements")
        
        # Save stage 1 result to job
        job = _get_job(job_id)
        if job:
            job.update_stage("stage1_requirements", stage1_data)
        
        # ─────────────────────────────────────────────────────────────────
        # STAGE 2: Architecture Design (Include repo context for Brownfield)
        # ─────────────────────────────────────────────────────────────────
        update_job_progress(35, "Stage 2: Designing architecture...")
        logger.info("=== STAGE 2: Architecture Design ===")
        stage2_input = dict(stage1_data)
        if repo_context_text:
            stage2_input["existing_repository_structure"] = repo_context_text.replace("--- REPOSITORY CONTEXT ---", "").strip()[:6000]

        stage2_messages = [
            {"role": "system", "content": STAGE_2_ARCHITECTURE_PROMPT},
            {"role": "user", "content": f"Design architecture for these requirements:\n\n{json.dumps(stage2_input, indent=2)}"}
        ]
        
        stage2_result = await llm_gateway.call_llm_and_extract(
            messages=stage2_messages,
            api_url=api_url,
            api_key=api_key,
            model=model,
            timeout=180.0,
            retries=3,
            retry_delay=5.0,
            purpose="BRD Analysis & Architecture",
        )
        
        stage2_data = _extract_json_from_response(stage2_result)
        logger.info(f"Stage 2 complete: Architecture pattern = {stage2_data.get('architecture_pattern', 'N/A')}")
        
        job = _get_job(job_id)
        if job:
            job.update_stage("stage2_architecture", stage2_data)
        
        # ─────────────────────────────────────────────────────────────────
        # STAGE 3: Data Models & API Design (NO [:10] TRUNCATION!)
        # ─────────────────────────────────────────────────────────────────
        update_job_progress(55, "Stage 3: Designing data models and APIs...")
        logger.info("=== STAGE 3: Data Models & API Design ===")
        stage3_context = {
            "development_classification": stage1_data.get("development_classification"),
            "requirements_summary": {
                "functional": stage1_data.get("functional_requirements", []),
                "implicit": stage1_data.get("implicit_requirements", []),
                "non_functional": stage1_data.get("non_functional_requirements", [])
            },
            "architecture": {
                "pattern": stage2_data.get("architecture_pattern"),
                "tech_stack": stage2_data.get("tech_stack", []),
                "components": stage2_data.get("architecture", {}).get("nodes", [])
            }
        }
        if repo_context_text:
            stage3_context["existing_repository_structure"] = repo_context_text.replace("--- REPOSITORY CONTEXT ---", "").strip()[:6000]
        
        stage3_messages = [
            {"role": "system", "content": STAGE_3_DATA_API_PROMPT},
            {"role": "user", "content": f"Design data models and APIs for:\n\n{json.dumps(stage3_context, indent=2)}"}
        ]
        
        stage3_result = await llm_gateway.call_llm_and_extract(
            messages=stage3_messages,
            api_url=api_url,
            api_key=api_key,
            model=model,
            timeout=180.0,
            retries=3,
            retry_delay=5.0,
            purpose="BRD Analysis & Architecture",
        )
        
        stage3_data = _extract_json_from_response(stage3_result)
        logger.info(f"Stage 3 complete: Designed {len(stage3_data.get('api_endpoints', []))} API endpoints")
        
        job = _get_job(job_id)
        if job:
            job.update_stage("stage3_data_api", stage3_data)
        
        # ─────────────────────────────────────────────────────────────────
        # STAGE 4: Implementation Plan (Pass FULL requirements, APIs, & ER)
        # ─────────────────────────────────────────────────────────────────
        update_job_progress(70, "Stage 4: Creating implementation plan...")
        logger.info("=== STAGE 4: Implementation Planning ===")
        stage4_context = {
            "development_classification": stage1_data.get("development_classification"),
            "product_name": stage1_data.get("product_name"),
            "functional_requirements": stage1_data.get("functional_requirements", []),
            "implicit_requirements": stage1_data.get("implicit_requirements", []),
            "technical_constraints": stage1_data.get("technical_constraints", {}),
            "architecture_pattern": stage2_data.get("architecture_pattern"),
            "tech_stack": stage2_data.get("tech_stack", []),
            "mermaid_er_diagram": stage3_data.get("mermaid_er_diagram", ""),
            "api_endpoints": stage3_data.get("api_endpoints", [])
        }
        if repo_context_text:
            stage4_context["existing_repository_structure"] = repo_context_text.replace("--- REPOSITORY CONTEXT ---", "").strip()
        
        stage4_messages = [
            {"role": "system", "content": STAGE_4_IMPLEMENTATION_PROMPT},
            {"role": "user", "content": f"Create implementation plan for:\n\n{json.dumps(stage4_context, indent=2)}"}
        ]
        
        stage4_result = await llm_gateway.call_llm_and_extract(
            messages=stage4_messages,
            api_url=api_url,
            api_key=api_key,
            model=model,
            timeout=180.0,
            retries=3,
            retry_delay=5.0,
            purpose="BRD Analysis & Architecture",
        )
        
        stage4_data = _extract_json_from_response(stage4_result)
        stage4_data = _normalize_stage4_schema(stage4_data)
        logger.info(f"Stage 4 complete: Created {len(stage4_data.get('file_creation_plan', []))} file specifications")
        
        job = _get_job(job_id)
        if job:
            job.update_stage("stage4_implementation", stage4_data)

        # ─────────────────────────────────────────────────────────────────
        # STAGE 5: Final Synthesis
        # ─────────────────────────────────────────────────────────────────
        update_job_progress(85, "Stage 5: Synthesizing final report...")
        logger.info("=== STAGE 5: Final Report Synthesis ===")
        synthesis_context = {
            "stage1_requirements": stage1_data,
            "stage2_architecture": stage2_data,
            "stage3_data_api": stage3_data,
            "stage4_implementation": stage4_data
        }
        
        stage5_messages = [
            {"role": "system", "content": STAGE_5_SYNTHESIS_PROMPT},
            {"role": "user", "content": f"Synthesize comprehensive BRD Analysis Report from:\n\n{json.dumps(synthesis_context, indent=2)[:80000]}"}
        ]
        
        stage5_result = await llm_gateway.call_llm_and_extract(
            messages=stage5_messages,
            api_url=api_url,
            api_key=api_key,
            model=model,
            timeout=240.0,
            retries=3,
            retry_delay=5.0,
            purpose="BRD Analysis & Architecture",
        )
        
        logger.info("Stage 5 complete: Final report generated")
        update_job_progress(88, "Stage 5 complete: Processing metrics and architecture...")
        
        final_json = _extract_json_from_response(stage5_result)
        
        if not final_json.get("architecture"):
            final_json["architecture"] = stage2_data.get("architecture", {"nodes": [], "edges": []})
        
        # Accurately preserve Greenfield, Brownfield, AND Modernization/Migration
        stage1_class = stage1_data.get("development_classification", {}).get("type", "").lower()
        if not final_json.get("metrics"):
            final_json["metrics"] = {}
        if "brown" in stage1_class:
            final_json["metrics"]["project_type"] = "brownfield"
            logger.info("Enforced 'brownfield' project_type from Stage 1 classification")
        elif "modern" in stage1_class or "migrat" in stage1_class:
            final_json["metrics"]["project_type"] = "modernization"
            logger.info("Enforced 'modernization' project_type from Stage 1 classification")
        elif "green" in stage1_class:
            final_json["metrics"]["project_type"] = "greenfield"
            logger.info("Enforced 'greenfield' project_type from Stage 1 classification")

        # Auto-synthesize baseline enterprise HLD and LLD specifications
        analysis_meta = {
            "title": final_json.get("title"),
            "project_type": final_json.get("metrics", {}).get("project_type", "greenfield"),
            "existing_repository_structure": repo_context_text.replace("--- REPOSITORY CONTEXT ---", "").strip() if repo_context_text else "",
            "stages": {
                "stage1_requirements": stage1_data,
                "stage2_architecture": stage2_data,
                "stage3_data_api": stage3_data,
                "stage4_implementation": stage4_data
            }
        }
        project_label = final_json.get("title") or stage1_data.get("product_name") or "Enterprise Solution"

        hld_data = None
        lld_data = None

        if job_id:
            # ─────────────────────────────────────────────────────────────────
            # PROGRESSIVE ASYNC DELIVERY:
            # Dispatch HLD & LLD generation to non-blocking background task.
            # Immediately return the complete Stage 1-5 BRD Analysis Report
            # so the user can review and interact with it right away (~2 min vs ~8 min).
            # ─────────────────────────────────────────────────────────────────
            update_job_progress(90, f"Analysis Report ready! Generating HLD and LLD in background...")
            asyncio.create_task(
                generate_architecture_specs_background(
                    job_id=job_id,
                    brd_content=document_content,
                    analysis_meta=analysis_meta,
                    project_label=project_label
                )
            )
        else:
            # Synchronous fallback for headless/script callers without a background job manager
            try:
                specs = await generate_architecture_specs_background(
                    job_id=None,
                    brd_content=document_content,
                    analysis_meta=analysis_meta,
                    project_label=project_label
                )
                hld_data = specs.get("hld")
                lld_data = specs.get("lld")
            except Exception as synth_err:
                logger.warning(f"Synchronous synthesis of HLD/LLD failed: {synth_err}")

        update_job_progress(100, "Analysis complete!")

        return {
            "status": "success",
            "analysis": stage5_result,
            "_jobId": job_id,
            "model": model or "chunked-multi-stage",
            "questions": final_json.get("questions", []),
            "metrics": final_json.get("metrics"),
            "prerequisites": final_json.get("prerequisites", []),
            "architecture": final_json.get("architecture"),
            "user_flow": final_json.get("user_flow"),
            "title": final_json.get("title"),
            "revision_delta": final_json.get("revision_delta"),
            "hld": hld_data,
            "lld": lld_data,
            "spec_status": {
                "analysis_report": "ready",
                "hld": "ready" if hld_data else "generating",
                "lld": "ready" if lld_data else "pending"
            },
            "stages": {
                "stage1_requirements": stage1_data,
                "stage2_architecture": stage2_data,
                "stage3_data_api": stage3_data,
                "stage4_implementation": stage4_data
            }
        }
    
    except Exception as e:
        logger.error(f"Chunked analysis failed: {str(e)}", exc_info=True)
        error_message = str(e) if str(e) else "Unknown error occurred during analysis"
        
        # Update job status if job_id is provided
        job = _get_job(job_id)
        if job:
            job.set_failed(error_message)
        
        return {
            "status": "error",
            "error": f"Analysis failed: {error_message}"
        }


# ═══════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════

def _extract_json_from_response(text: str) -> dict:
    """Extract JSON object from LLM response, handling markdown fences and think tags."""
    if not text or not isinstance(text, str):
        return {}
    
    # Remove think tags
    text = re.sub(r"ქ.*?ქ", "", text, flags=re.DOTALL)
    text = re.sub(r"<think>[\s\S]*?</think>", "", text, flags=re.IGNORECASE)

    # 1. First try: clean outer markdown code fences if response is wrapped as ```json ... ```
    cleaned = text.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:].strip()
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:].strip()
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3].strip()

    if cleaned.startswith("{") and cleaned.endswith("}"):
        try:
            return json.loads(cleaned)
        except Exception:
            pass

    # 2. Try greedy extraction between outermost { and }
    first_brace = cleaned.find("{")
    last_brace = cleaned.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        candidate = cleaned[first_brace:last_brace + 1].strip()
        try:
            return json.loads(candidate)
        except Exception:
            pass
    
    # 3. Try to find JSON in markdown fence
    fenced_regex = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.IGNORECASE)
    for match in fenced_regex.finditer(text):
        candidate = match.group(1).strip()
        if candidate.startswith("{") and candidate.endswith("}"):
            try:
                return json.loads(candidate)
            except:
                continue
    
    # 4. Try to find trailing JSON object
    trimmed = text.strip()
    for i in range(len(trimmed) - 1, -1, -1):
        if trimmed[i] == "{":
            candidate = trimmed[i:].strip()
            try:
                return json.loads(candidate)
            except:
                continue
    
    return {}


def _normalize_stage4_schema(stage4_data: dict) -> dict:
    """
    P1.5-02: Normalize Stage 4 implementation plan output keys to canonical schema.
    Canonical key: file_creation_plan
    Supported aliases: implementation_files, files, file_plan, implementation_plan, file_list
    """
    if not isinstance(stage4_data, dict):
        return {}
    
    normalized = dict(stage4_data)
    
    # Check canonical key first
    files_list = normalized.get("file_creation_plan")
    
    # If missing or empty or not a list, check supported aliases
    if not files_list or not isinstance(files_list, list) or len(files_list) == 0:
        known_aliases = [
            "implementation_files",
            "files",
            "file_plan",
            "implementation_plan",
            "file_list"
        ]
        for alias in known_aliases:
            candidate = normalized.get(alias)
            if candidate:
                if isinstance(candidate, list) and len(candidate) > 0:
                    files_list = candidate
                    logger.info(f"Normalized Stage 4 key '{alias}' to canonical 'file_creation_plan' ({len(candidate)} items)")
                    break
                elif isinstance(candidate, dict):
                    flattened = []
                    for cat, items in candidate.items():
                        if isinstance(items, list):
                            for item in items:
                                if isinstance(item, dict):
                                    if "phase" not in item:
                                        item["phase"] = str(cat)
                                    flattened.append(item)
                                elif isinstance(item, str):
                                    flattened.append({
                                        "file_path": item,
                                        "purpose": f"Implementation file for {cat}",
                                        "content_type": "source",
                                        "priority": "high",
                                        "phase": str(cat)
                                    })
                    if flattened:
                        files_list = flattened
                        logger.info(f"Normalized nested Stage 4 key '{alias}' to canonical 'file_creation_plan' ({len(flattened)} items)")
                        break

    # Normalize file items inside file_creation_plan
    canonical_files = []
    if isinstance(files_list, list):
        for item in files_list:
            if isinstance(item, dict):
                f_path = item.get("file_path") or item.get("path") or item.get("file") or item.get("filename") or ""
                normalized_item = dict(item)
                if f_path:
                    normalized_item["file_path"] = str(f_path)
                canonical_files.append(normalized_item)
            elif isinstance(item, str) and item.strip():
                canonical_files.append({
                    "file_path": item.strip(),
                    "purpose": "Implementation file",
                    "content_type": "source",
                    "priority": "high",
                    "phase": "Implementation"
                })

    normalized["file_creation_plan"] = canonical_files
    return normalized


def _format_governance_context(governance_context: Optional[Dict[str, Any]]) -> str:
    """Convert governance questionnaire context into prompt text."""
    if not governance_context or not isinstance(governance_context, dict):
        return ""
    
    lines = ["GOVERNANCE CONTEXT (treat as constraints):"]
    
    project_name = governance_context.get("project_name")
    hard_stops = governance_context.get("hard_stops") or []
    
    if project_name:
        lines.append(f"- Project: {project_name}")
    
    if hard_stops:
        lines.append("- Critical Issues:")
        for stop in hard_stops:
            lines.append(f"  - {stop}")
    
    answers = governance_context.get("answers")
    if isinstance(answers, list) and answers:
        lines.append("- Governance Answers:")
        for answer in answers:
            if not isinstance(answer, dict):
                continue
            question = answer.get("question", "")
            selected = answer.get("selected_option", "")
            if question and selected:
                lines.append(f"  - {question}: {selected}")
    
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════
# TARGETED UPDATE PROMPTS
# ═══════════════════════════════════════════════════════════════════════════

TARGETED_DIFF_PROMPT = """# ROLE
You are an expert BRD analyst performing a TARGETED, SURGICAL update to an existing analysis.

## CRITICAL INSTRUCTION - READ THIS CAREFULLY
You MUST NOT regenerate the entire analysis from scratch.
You MUST NOT rewrite sections that are not affected by the user's request.
You MUST preserve the EXACT original wording, technology stack, architecture decisions, and all other content that is NOT directly related to the user's specific change request.

**ABSOLUTE RULE**: If the user asks to change "Project Name from Pegasus Platform to Pegasus Captive Management", you MUST:
1. ONLY change occurrences of "Pegasus Platform" to "Pegasus Captive Management"
2. PRESERVE ALL OTHER CONTENT EXACTLY AS-IS including:
   - Technology stack (ASP.NET Core, React, SQLite, Node.js, Azure, etc.)
   - Architecture patterns and decisions
   - Data models and schemas
   - API specifications
   - Repository structure
   - Prerequisites and credentials
   - Implementation guidelines
   - All other technical details

Think of this like a "Find and Replace" operation — only what the user explicitly asked to change, not the whole file.

## INPUTS YOU WILL RECEIVE
1. `previous_analysis`: The full existing BRD analysis (Stage 1-5 data + final report)
2. `change_request`: What the user wants to update (answers to questions, revision changes, feedback)
3. `document_content`: The source BRD document (for context only — do NOT re-extract everything)

## YOUR TASK
1. Read the change_request carefully
2. Identify which sections of the existing analysis are ACTUALLY AFFECTED
3. For ONLY those sections, produce updated content
4. Return a JSON diff object with only the changed fields

## OUTPUT FORMAT
Return ONLY valid JSON (no markdown fences):
{
  "change_summary": "A friendly, conversational, and highly detailed message explaining exactly what enhancements or changes you implemented in the BRD based on the requested technique/feedback, why it benefits the project, and inviting user feedback on this update.",
  "affected_sections": ["section names that changed"],
  "stage1_updates": {
    // Only include fields that actually changed. Omit unchanged fields entirely.
    // Example: if only clarification_questions changed, only include that field
    "clarification_questions": ["updated q1", ...],
    "functional_requirements": null  // null means: keep existing unchanged
  },
  "stage2_updates": {
    // Only include if architecture/tech stack changed due to the update
    // null means: keep existing unchanged
  },
  "stage3_updates": {
    // Only include if data models or APIs changed
    // null means: keep existing unchanged
  },
  "stage4_updates": {
    // Only include if implementation plan or prerequisites changed
    // null means: keep existing unchanged
  },
  "report_section_patches": [
    {
      "section_heading": "## 0.X Section Title",
      "replacement_content": "New markdown content for this section only"
    }
    // Only sections that need updating. Other sections stay unchanged.
  ],
  "metrics_updates": {
    // Only if metrics changed. null or omit to keep existing.
    "complexity": null,
    "timeline": null,
    "deployment": null,
    "resources": null
  }
}

## RULES - THESE ARE MANDATORY
- If a field is not affected by the user's specific request, set it to null or omit it entirely
- If answering a question that doesn't change the architecture, do NOT update stages 2/3/4
- Preserve ALL existing analysis that is not directly changed - copy it verbatim
- Be EXTREMELY conservative: when in doubt about whether something changed, leave it unchanged
- For name changes: ONLY change the name, preserve ALL other content exactly as-is
- For technology changes: ONLY change the specific technology mentioned, preserve everything else
- For architecture changes: ONLY change the specific component mentioned, preserve everything else
- NEVER regenerate or rephrase content that wasn't explicitly requested to change
- Use ASCII characters only

## EXAMPLES OF CORRECT BEHAVIOR
**User Request**: "Change project name from Pegasus Platform to Pegasus Captive Management"
**Correct Response**: Only update "product_name" field and any mentions of "Pegasus Platform" in the report. ALL technology stack, architecture, data models, APIs, etc. remain EXACTLY the same.

**User Request**: "Add payment gateway integration"
**Correct Response**: Add payment gateway to functional requirements, add payment API endpoints, add payment-related prerequisites. Do NOT change existing tech stack, architecture pattern, or other unrelated sections.

**User Request**: "Change deployment from Azure to AWS"
**Correct Response**: Update deployment target and cloud-specific services. Preserve application architecture, data models, APIs, and all other non-cloud-specific content."""

TARGETED_REPORT_PATCH_PROMPT = """# ROLE
You are a technical writer applying targeted patches to a BRD analysis report.

## TASK
You will receive:
1. The CURRENT report markdown
2. A list of section patches (heading + new content)
3. The change_summary

Apply ONLY the patches listed. Do not modify any other section.
Return the COMPLETE updated report markdown.

## CRITICAL RULES
- Only replace the sections listed in the patches
- Keep all other sections EXACTLY as-is
- Maintain the same heading structure and numbering
- Use ASCII characters only"""


async def update_analysis_targeted(
    previous_analysis: Dict[str, Any],
    change_request: str,
    document_content: str,
    api_url: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    governance_context: Optional[Dict[str, Any]] = None,
    job_id: Optional[str] = None,
    update_type: str = "feedback",  # "feedback" | "revision" | "qa"
) -> Dict[str, Any]:
    """
    Performs a surgical, targeted update to an existing BRD analysis.
    
    Instead of regenerating everything from scratch, it:
    1. Identifies which parts of the analysis are affected by the change
    2. Updates ONLY those parts
    3. Patches the final report with only the changed sections
    4. Merges the changes back into the full analysis object
    
    Args:
        previous_analysis: The complete existing analysis object (stages + report)
        change_request: What changed (user answers, revision reason, feedback)
        document_content: Source BRD document
        update_type: Type of update for context ("feedback", "revision", "qa")
    """

    def update_job_progress(progress: int, message: str):
        if job_id:
            try:
                job = _get_job(job_id)
                if job:
                    job.update_progress(progress, message)
            except Exception as e:
                logger.warning(f"Failed to update job progress: {e}")

    if not llm_gateway.check_api_key(api_key):
        error = "API key not configured. Please set AI_API_KEY in your environment."
        return {"status": "error", "error": error}

    try:
        update_job_progress(15, "Analyzing what needs to change...")

        # Extract existing stages from the previous analysis
        existing_stages = previous_analysis.get("stages", {})
        existing_report = previous_analysis.get("analysis", "")
        existing_metrics = previous_analysis.get("metrics", {})
        existing_questions = previous_analysis.get("questions", [])
        existing_prerequisites = previous_analysis.get("prerequisites", [])
        existing_architecture = previous_analysis.get("architecture", {})

        # Build context for the diff prompt
        update_type_label = {
            "feedback": "User provided additional feedback/context",
            "revision": "User uploaded a new revision of the document",
            "qa": "User answered clarification questions"
        }.get(update_type, "User requested an update")

        diff_context = {
            "update_type": update_type_label,
            "change_request": change_request,
            "document_snippet": document_content[:3000],  # Small snippet for context
            "existing_stage1": existing_stages.get("stage1_requirements", {}),
            "existing_stage2_summary": {
                "architecture_pattern": existing_stages.get("stage2_architecture", {}).get("architecture_pattern"),
                "tech_stack_count": len(existing_stages.get("stage2_architecture", {}).get("tech_stack", [])),
            },
            "existing_stage3_summary": {
                "api_count": len(existing_stages.get("stage3_data_api", {}).get("api_endpoints", [])),
                "has_er_diagram": bool(existing_stages.get("stage3_data_api", {}).get("mermaid_er_diagram")),
            },
            "existing_metrics": existing_metrics,
            "existing_questions": existing_questions,
        }

        update_job_progress(30, "Identifying affected sections...")

        # Step 1: Get the targeted diff
        diff_messages = [
            {"role": "system", "content": TARGETED_DIFF_PROMPT},
            {"role": "user", "content": f"Apply this targeted update:\n\n{json.dumps(diff_context, indent=2)[:5000]}"}
        ]

        diff_result = await llm_gateway.call_llm_and_extract(
            messages=diff_messages,
            api_url=api_url,
            api_key=api_key,
            model=model,
            timeout=120.0,
            purpose="BRD Incremental Update",
        )

        diff_data = _extract_json_from_response(diff_result)
        logger.info(f"Targeted diff complete. Affected sections: {diff_data.get('affected_sections', [])}")
        update_job_progress(55, f"Updating affected sections: {', '.join(diff_data.get('affected_sections', ['analysis']))}...")

        # Step 2: Merge diffs back into existing stages
        updated_stages = dict(existing_stages)  # Start with a copy

        def _merge_updates(existing: dict, updates: Optional[dict]) -> dict:
            """Merge non-null updates into existing dict."""
            if not updates or not isinstance(updates, dict):
                return existing
            merged = dict(existing)
            for key, value in updates.items():
                if value is not None:  # null means "keep existing"
                    merged[key] = value
            return merged

        stage1_updates = diff_data.get("stage1_updates")
        if stage1_updates and isinstance(stage1_updates, dict):
            updated_stages["stage1_requirements"] = _merge_updates(
                updated_stages.get("stage1_requirements", {}), stage1_updates
            )

        stage2_updates = diff_data.get("stage2_updates")
        if stage2_updates and isinstance(stage2_updates, dict):
            updated_stages["stage2_architecture"] = _merge_updates(
                updated_stages.get("stage2_architecture", {}), stage2_updates
            )

        stage3_updates = diff_data.get("stage3_updates")
        if stage3_updates and isinstance(stage3_updates, dict):
            updated_stages["stage3_data_api"] = _merge_updates(
                updated_stages.get("stage3_data_api", {}), stage3_updates
            )

        stage4_updates = diff_data.get("stage4_updates")
        if stage4_updates and isinstance(stage4_updates, dict):
            updated_stages["stage4_implementation"] = _merge_updates(
                updated_stages.get("stage4_implementation", {}), stage4_updates
            )

        # Step 3: Patch the report markdown
        update_job_progress(70, "Patching report sections...")
        report_patches = diff_data.get("report_section_patches", [])

        updated_report = existing_report
        if report_patches and isinstance(report_patches, list) and len(report_patches) > 0:
            patch_context = {
                "current_report": existing_report[:8000],
                "patches": report_patches,
                "change_summary": diff_data.get("change_summary", "")
            }

            patch_messages = [
                {"role": "system", "content": TARGETED_REPORT_PATCH_PROMPT},
                {"role": "user", "content": f"Apply these patches:\n\n{json.dumps(patch_context, indent=2)[:6000]}"}
            ]

            patch_result = await llm_gateway.call_llm_and_extract(
                messages=patch_messages,
                api_url=api_url,
                api_key=api_key,
                model=model,
                timeout=180.0,
                purpose="BRD Incremental Update",
            )

            # The patched report is the raw text (not JSON)
            if patch_result and isinstance(patch_result, str) and len(patch_result) > 100:
                # Strip any JSON that may have been appended
                clean_report = patch_result
                # Remove trailing JSON block if present
                last_fence = clean_report.rfind("```json")
                if last_fence > 0:
                    clean_report = clean_report[:last_fence].strip()
                updated_report = clean_report
            else:
                logger.warning("Patch result was too short, keeping original report")

        # Step 4: Merge metrics updates
        updated_metrics = dict(existing_metrics)
        metrics_updates = diff_data.get("metrics_updates")
        if metrics_updates and isinstance(metrics_updates, dict):
            for key, value in metrics_updates.items():
                if value is not None:
                    updated_metrics[key] = value

        # Step 5: Extract updated questions/prerequisites from updated stages
        updated_questions = (
            updated_stages.get("stage1_requirements", {}).get("clarification_questions")
            or existing_questions
        )
        updated_prerequisites = (
            updated_stages.get("stage4_implementation", {}).get("prerequisites")
            or existing_prerequisites
        )
        updated_architecture = (
            updated_stages.get("stage2_architecture", {}).get("architecture")
            or existing_architecture
        )

        update_job_progress(95, "Finalizing updated analysis...")

        change_summary = diff_data.get("change_summary", "Analysis updated based on your input.")
        affected_sections = diff_data.get("affected_sections", [])

        return {
            "status": "success",
            "analysis": updated_report,
            "model": model or "targeted-update",
            "change_summary": change_summary,
            "affected_sections": affected_sections,
            "stages": updated_stages,
            "metrics": updated_metrics,
            "questions": updated_questions,
            "prerequisites": updated_prerequisites,
            "architecture": updated_architecture,
            "update_type": update_type,
        }

    except Exception as e:
        logger.error(f"Targeted update failed: {str(e)}", exc_info=True)
        error_message = str(e) if str(e) else "Unknown error during targeted update"

        job = _get_job(job_id)
        if job:
            job.set_failed(error_message)

        return {"status": "error", "error": f"Targeted update failed: {error_message}"}


# ═══════════════════════════════════════════════════════════════════════════
# EXPORT MAIN FUNCTION AS analyze_document FOR DROP-IN REPLACEMENT
# ═══════════════════════════════════════════════════════════════════════════

async def analyze_document(
    document_content: str,
    api_url: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    stream: bool = False,
    user_feedback: Optional[str] = None,
    image_paths: Optional[List[str]] = None,
    governance_context: Optional[Dict[str, Any]] = None,
    job_id: Optional[str] = None,  # NEW: Optional job ID for progress tracking
) -> Dict[str, Any]:
    """
    Drop-in replacement for the original analyze_document function.
    Uses intelligent chunking to reduce payload size while maintaining output quality.
    
    Args:
        job_id: Optional job ID for progress tracking via job manager
    """
    return await analyze_document_chunked(
        document_content=document_content,
        api_url=api_url,
        api_key=api_key,
        model=model,
        governance_context=governance_context,
        stream=stream,
        user_feedback=user_feedback,
        image_paths=image_paths,
        job_id=job_id,
    )