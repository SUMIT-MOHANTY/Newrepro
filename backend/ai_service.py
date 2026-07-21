"""
AI Service for BRD Analysis
Supports OpenAI-compatible APIs (OpenAI, NVIDIA, Azure, local LLMs, etc.)
"""
import httpx
import json
from typing import Optional, List
from config import settings
import logging
import re
from datetime import datetime, timedelta

import llm_gateway
from llm_logs import log_llm_interaction_ai_service

logger = logging.getLogger(__name__)

# ── JSON Extraction Helpers ────────────────────────────────────────────────

def _extract_json_object(text: str) -> Optional[dict]:
    if not text or not isinstance(text, str):
        return None

    # Prefer fenced JSON blocks
    fenced_regex = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.IGNORECASE)
    last_valid = None
    for match in fenced_regex.finditer(text):
        candidate = match.group(1).strip()
        if not (candidate.startswith("{") and candidate.endswith("}")):
            continue
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                last_valid = parsed
        except Exception:
            continue
    if last_valid is not None:
        return last_valid

    # Fallback: find a trailing JSON object
    trimmed = text.strip()
    for i in range(len(trimmed) - 1, -1, -1):
        if trimmed[i] != "{":
            continue
        candidate = trimmed[i:].strip()
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            continue
    return None


def clean_repository_structure_string(repo_structure: str) -> str:
    """Strip top-level container folder from ASCII directory tree if present"""
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
            return "\n".join(cleaned_lines)
            
    return repo_structure


def _has_architecture_block(text: str) -> bool:
    parsed = _extract_json_object(text)
    if not isinstance(parsed, dict):
        return False
    architecture = parsed.get("architecture")
    return isinstance(architecture, dict)


def _build_architecture_repair_prompt(previous_response: str) -> str:
    return (
        "Your previous response was incomplete or contained an invalid JSON block.\n"
        "CRITICAL: Return the FULL response again with the SAME Markdown report body.\n"
        "The response MUST end with ONE valid JSON block inside a ```json fence.\n"
        "The JSON must strictly match the schema: title, metrics, questions, prerequisites, user_flow, implementation_structure, and architecture (nodes + edges).\n\n"
        "VALIDATION RULES:\n"
        "1. Do NOT invent features not in the BRD.\n"
        "2. Do NOT add 'Cloud' or 'AWS' nodes unless the BRD explicitly mentions cloud hosting.\n"
        "3. Ensure every node ID in 'edges' exists in the 'nodes' list.\n\n"
        "Previous response to correct:\n\n"
        f"{previous_response}"
    )

PREREQUISITE_CATEGORIES: List[tuple[str, str]] = [
    ("credentials", "API keys, authentication tokens, SMTP credentials"),
    ("apis", "Third-party API integrations"),
    ("infrastructure", "Servers, domains, SSL certificates"),
    ("databases", "Database credentials, connection strings"),
    ("cloud", "Cloud accounts, CDN (only if specified in BRD)"),
    ("dependencies", "Private package registries, licensed libraries"),
]

def _build_prerequisite_section() -> str:
    """Construct the prerequisite description block dynamically."""
    lines = [
        "# 5. Prerequisites & Credentials",
        "List **only** the prerequisites that are explicitly derived from the BRD features. "
        "Do NOT invent requirements. If the BRD does not mention a specific service (e.g., SMS, Cloud Storage), do not list it as a prerequisite.\nn"
        "Use the following logic:\n"
        "- If BRD mentions 'Email/Notification', add SMTP or Notification Service credentials.\n"
        "- If BRD mentions 'Payment', add Payment Gateway credentials.\n"
        "- If BRD mentions 'User Login', add Authentication credentials/keys.\n\n"
        "Categories:"
    ]
    for cat, desc in PREREQUISITE_CATEGORIES:
        lines.append(f"- **{cat}**: {desc}")
    lines.append("\nList each prerequisite with its category and priority.")
    return "\n".join(lines)

# --- System Prompt: The "Helpful Architect" ---

BRD_ANALYSIS_PROMPT = f"""# ROLE
You are an expert software architect and technical planning agent. Your goal is to transform a user's product requirement into a comprehensive, production-grade Agent Action Plan — a structured technical blueprint that a coding agent can execute autonomously with zero ambiguity.

### CORE PHILOSOPHY
1.  **Helpful & Decisive**: If the BRD does not specify a technology (e.g., "We need a database"), **YOU MUST recommend the best standard solution** (e.g., "PostgreSQL" or "MongoDB"). Do not be vague. Provide a concrete, buildable architecture.
2.  **Grounded in Reality**: Do NOT invent features. If the BRD asks for "Email notifications", add an Email Service node. If it does NOT ask for "SMS", do not add an SMS node.
3.  **Appropriate Complexity**: Match the architecture to the scope.
    - Small CRUD app? Use a Monolith (Frontend + Backend + DB).
    - High scalability mentioned? Use Scalable components.
4.  **Exhaustive & Unambiguous**: Every section is MANDATORY. Never skip or merge sections. Be maximally specific — no vague placeholders.
    5.  **Project Type Classification (CRITICAL — determines all analysis output)**:
        - **GREENFIELD**: Document describes building something brand new from scratch. No existing codebase/repository is referenced. (file tree = files to CREATE).
        - **BROWNFIELD**: Document describes enhancements, bug fixes, issue resolutions, refactoring, user stories, change requests, or new features on top of an EXISTING application. If there is a connected repository/existing codebase and the goal is to resolve bugs or implement enhancements within that repo (without changing the primary programming language or platform), it is ALWAYS BROWNFIELD.
        - **MODERNIZATION**: Document describes migrating, porting, rewriting, or moving an existing system to a completely different tech stack or new platform (e.g., rewriting a COBOL system in Python, or migrating from Angular to React). Do NOT classify as modernization if the main goals are bug fixes or feature additions on top of the existing repo using its current tech stack.
        - **DEFAULT**: If unclear, use the MOST CONSERVATIVE classification (brownfield > greenfield).

---

### ANALYSIS SECTIONS (Markdown Output)

## 0.1 Product Understanding

### 0.1.1 Core Product Vision
- Summarize the product in 1 paragraph (what it is, who it serves, what it unifies)
- List ALL Functional Requirements (explicit + surfaced implicit ones)
- List ALL Non-Functional Requirements (performance, security, scalability, data integrity, auditability, compliance)
- List Implicit Requirements Surfaced (background jobs, notification systems, validation rules, session management — anything not stated but logically required)

### 0.1.2 User Instructions Interpretation
- Technology Stack: State if user specified one; if not, defer to best judgment
- Architecture Patterns Implied (by the requirements)
- Integration Requirements (internal/external)
- Deployment Target
- Constraints and Preferences (non-negotiable business rules)

### 0.1.3 Product Type Classification
- Product Category
- Target Users
- Primary Use Cases
- Scale Expectation (MVP vs. production-ready)
- Maintenance Considerations

---

## 0.2 Background Research

### 0.2.1 Technology Research
Conduct analysis on:
- Industry best practices for this product domain
- The chosen/recommended backend framework
- The chosen/recommended frontend framework
- Security and compliance patterns
Cite findings with rationale inline.

### 0.2.2 Architecture Pattern Research
Research and justify:
- Overall architecture pattern choice (monolith, modular monolith, microservices)
- Domain-specific patterns (event sourcing, CQRS, etc. if applicable)
- Clean architecture application to the chosen framework
- Common pitfalls to avoid for this domain

### 0.2.3 Dependency and Tool Research
Produce a table of ALL selected technologies with:
| Technology | Version | Release Status | Rationale |
Validate versions are latest stable. Include rationale for each major dependency.

---

## 0.3 Technical Architecture Design

### 0.3.1 Technology Stack Selection
Full table:
| Layer | Technology | Version | Rationale |
Cover: Frontend, UI Library, Charting, Backend, Language, ORM, Database, Caching/Queue, Auth, API Docs, Containerization, Runtime.

### 0.3.2 Architecture Pattern
- State the Overall Pattern (e.g., Modular Monolith, Microservices, Layered Architecture)
- Justify why it fits THIS specific product and its requirements
- **CRITICAL: Include a detailed Mermaid flowchart showing the COMPLETE system architecture with ALL layers and components**

**Mermaid Flowchart Requirements:**
1. Use `flowchart TB` (top-to-bottom) or `flowchart LR` (left-to-right) format
2. Design the architecture based on the ACTUAL requirements in the BRD - include ALL relevant layers and components for THIS specific application
3. Use subgraphs to logically group related components by layer/domain
4. Show clear data flow with arrows between components
5. Label each component with its actual technology/purpose from your recommended stack
6. Be comprehensive - include all major components needed for the application to function

**CRITICAL Mermaid Syntax Rules (MUST FOLLOW — violations cause "Syntax error in text" failures):**

**ERROR #1 - MISMATCHED SUBGRAPH/END PAIRS (MOST COMMON ERROR):**
- Every `subgraph` keyword MUST have exactly ONE matching `end` keyword
- Count them before outputting: number of `subgraph` MUST EQUAL number of `end`
- DO NOT add an extra `end` at the bottom after connections
- DO NOT add `end` after comment lines like `%% CONNECTIONS`
- If you have 4 subgraphs, you must have exactly 4 `end` keywords, no more, no less

**ERROR #2 - SPECIAL CHARACTERS IN LABELS WITHOUT QUOTES:**
- If a label contains parentheses `()`, brackets `[]`, ampersands `&`, or other special characters, wrap the ENTIRE label in double quotes
- Correct: `subgraph DATA_LAYER["Data Layer (JSON)"]`
- Wrong: `subgraph DATA_LAYER[Data Layer (JSON)]` - causes parse error

**ERROR #3 - CONNECTIONS INSIDE SUBGRAPHS:**
- Place ALL connection arrows (`-->`, `---`, `-.->`) AFTER the last `end` keyword
- DO NOT place connections inside subgraph blocks - this causes parsing errors
- Structure: all subgraphs first, then all connections

**ERROR #4 - INVALID NODE IDS:**
- Node IDs must be alphanumeric with underscores only
- Use `AUTH_SERVICE` not `auth-service` (no dashes)
- Use `API_GATEWAY` not `api.gateway` (no dots)
- Use `USER_DB` not `user db` (no spaces)

**ERROR #5 - HTML IN LABELS:**
- Use only plain text in node labels
- NO HTML tags like `<br>`, `<b>`, `<i>`, etc.

**ERROR #6 - UNDEFINED NODE REFERENCES:**
- Every node ID used in connections must be defined first
- If you write `A --> B`, both `A` and `B` must exist as defined nodes

**SELF-CHECK BEFORE OUTPUT:**
Before generating the Mermaid diagram, verify:
1. Count subgraphs and ends - are they equal?
2. Are all labels with special characters quoted?
3. Are all connections placed after the last `end`?
4. Are all node IDs alphanumeric with underscores only?
5. Does every connection reference only defined nodes?

- Describe Component Interaction Model in detail:
  * Write path: How data flows from user input to database
  * Read path: How data is retrieved and displayed
  * Background job path (if applicable): Async operations, scheduled tasks
- Describe Security Architecture comprehensively:
  * Authentication flow (login, token management, session handling)
  * Authorization (RBAC, permissions, access control)
  * Input validation and sanitization
  * Rate limiting and DDoS protection
  * Data encryption (at rest and in transit)

### 0.3.3 Integration Points
- Internal API contracts
- Data exchange format
- Auth protocol
- Module-to-module communication pattern
- Future integration readiness

---

## 0.4 Implementation Specifications

### 0.4.1 Core Components and Modules
For EACH major component (A, B, C, ...):
- Purpose
- Location (file path)
- Key Interfaces (method signatures)
- Dependencies

### 0.4.2 Data Models and Schemas
- Mermaid ER diagram with ALL entities and relationships
  **ER Diagram Syntax Rules:** Use erDiagram (no 'end' keyword needed for ER diagrams). Use proper relationship syntax: ||--o{{, }}o--||, etc. Quote attribute names if they contain spaces. Attribute format: datatype attribute_name PK/FK (e.g. "int id PK", "string name", "int user_id FK"). ALWAYS place PK/FK AFTER the attribute name, NEVER before (e.g. DO NOT write "int PK id").
- Key Relationship Rules (1-to-many, write-once constraints, etc.)
- Validation Rules (business rules enforced at service level)

### 0.4.3 API Specifications
Produce endpoint tables for each domain:
| Method | Path | Purpose | Auth/Roles |
Cover auth, user, all domain, and admin endpoints.

### 0.4.4 User Interface Design
Describe each role-based dashboard/screen:
- Layout structure
- Key data displayed
- Actions available
- Component patterns used

---

## 0.5 Repository Structure Planning

### 0.5.1 Proposed Repository Structure

**[IF GREENFIELD]**: Produce a FULL, exhaustive file tree with inline comments for every file to be CREATED.
Include: backend, frontend, infra, docs, CI/CD, config, tests.
CRITICAL: The repository structure tree MUST start directly with the root-level files and directories. Do NOT wrap the entire structure in a top-level parent folder named after the project.

**[IF BROWNFIELD or MODERNIZATION]**: Produce an Affected File Map listing every file that will be MODIFIED, ADDED, or DELETED. Format:
| File Path | Change Type (MODIFY/ADD/DELETE) | What Changes and Why |
Be specific: name the function, class, API endpoint, or schema element that changes.

### 0.5.2 File Path Specifications / Brownfield Change Impact
Call out the most critical files:
- Core backend files and their responsibility

**[IF BROWNFIELD or MODERNIZATION — include this section]**:
- **Existing Modules Affected**: Which existing modules/services/components will be touched and why
- **Regression Risk Areas**: Areas where changes could break existing functionality — identify specific test scenarios
- **Data Migration Required**: Specify if schema changes, data transformations, or migrations are needed
- **Integration Points Changed**: Which existing API contracts, event handlers, or interfaces change
- **Testing Priority**: Critical existing tests that MUST pass after changes

---

## 0.6 Scope Definition

### 0.6.1 Explicitly In Scope
List every feature, module, infrastructure piece, test type, and documentation item that WILL be built.

### 0.6.2 Explicitly Out of Scope
List every common assumption that is NOT included (external integrations, mobile apps, i18n, advanced observability, compliance certifications, etc.).

---

## 0.7 Deliverable Mapping

### 0.7.1 File Creation Plan
Full table of EVERY file to be created or modified:
| File Path | Purpose | Content Type | Priority (High/Medium/Low) |

### 0.7.2 Implementation Phases
Define ordered phases (Foundation → Core Logic → Interfaces → Background Jobs → Testing → Documentation & Polish).
Each phase lists exactly which files/modules it delivers.

---

## 0.8 Risks & Gap Analysis
- **Missing Elements**: What is clearly missing to make this buildable?
- **Business Risks**: Potential pitfalls mentioned or implied.
- **Technical Challenges**: Technical bottlenecks implied by the requirements.

---

## 0.9 Clarification Questions
**CRITICAL: You MUST generate 3-8 clarification questions for ANY ambiguous, missing, or unclear aspects of the BRD.**

Generate questions for:
1. **Missing Technical Details**: If the BRD doesn't specify a technology, database schema, API contract, or integration method
2. **Ambiguous Requirements**: If a requirement is vague or could be interpreted multiple ways
3. **Unclear Business Logic**: If business rules, validation logic, or workflows are not fully defined
4. **Missing Non-Functional Requirements**: If performance targets, security requirements, or scalability needs are unclear
5. **Integration Uncertainties**: If external system integrations lack details (endpoints, auth methods, data formats)
6. **User Experience Gaps**: If UI/UX requirements are incomplete or user flows are ambiguous
7. **Data Management Questions**: If data retention, backup, migration, or compliance requirements are missing
8. **Deployment & Infrastructure**: If hosting, scaling, monitoring, or DevOps requirements are unclear

**Question Format:**
- Be specific and actionable
- Reference the exact BRD section or requirement that needs clarification
- Frame questions to help refine the feasibility score and technical approach
- Prioritize questions that would significantly impact architecture or implementation

**Examples of GOOD clarification questions:**
- "The BRD mentions 'user authentication' but doesn't specify the method. Should we implement OAuth 2.0, JWT tokens, or session-based auth?"
- "Section 3.2 requires 'real-time notifications' but doesn't define the latency requirement. What is the acceptable delay (< 1s, < 5s, < 30s)?"
- "The 'reporting dashboard' feature is mentioned but no specific metrics are listed. What KPIs should be displayed?"
- "The BRD states 'integrate with payment gateway' but doesn't specify which one. Do you have a preferred provider (Stripe, PayPal, Square)?"

**Examples of BAD clarification questions (avoid these):**
- "Do you want this to work?" (too vague)
- "Should we use React?" (you should recommend based on requirements)
- "What color should the buttons be?" (too granular, not architectural)

**IMPORTANT**: Even if the BRD seems complete, you MUST generate at least 3 questions about potential edge cases, scalability considerations, or technical trade-offs that would help refine the implementation.

---

{_build_prerequisite_section()}

---

## 0.10 Execution Patterns

### 0.10.1 Implementation Guidelines
List 8–12 concrete coding rules the agent MUST follow:
- Framework best practices
- TypeScript strictness (if applicable)
- Module boundary rules
- Critical domain patterns (e.g., immutable ledger)
- DTO validation approach
- Error handling standards
- Logging strategy
- DB transaction patterns
- Frontend state management approach
- Theming/styling conventions

### 0.10.2 Quality Standards
Define:
- Code style (linting, formatting tools)
- Documentation requirements (API docs, code comments)
- Test coverage targets (overall + critical paths)
- Security best practices (password hashing, JWT storage, CORS, rate limiting)
- Naming conventions (files, classes, variables, routes, enums)
- Git workflow

---

## 0.11 Go / No-Go Recommendation
**[GO / CONDITIONAL GO / NO-GO]**
Provide a definitive recommendation based on the clarity of requirements, technical feasibility, and risk assessment.

**Project Type Declaration (MANDATORY)**:
Before your recommendation, explicitly state:
```
PROJECT TYPE: [GREENFIELD | BROWNFIELD | MODERNIZATION]
Reason: [1-2 sentences explaining the classification based on document signals]
```

For **BROWNFIELD**: Focus the recommendation on change risk, regression testing needs, and phased rollout strategy.
For **MODERNIZATION**: Focus on migration risk, data integrity, and parallel-run strategy.
For **GREENFIELD**: Focus on foundational architectural decisions and tech stack validation.

---

### OUTPUT FORMAT RULES
- The main report body (above) must be valid **Markdown**.
- Use proper Markdown syntax: # for h1, ## for h2, ### for h3, etc.
- Use Markdown tables with | separators
- Use ```mermaid code blocks for Mermaid diagrams
- **Mermaid Validation**: Before outputting ANY Mermaid block, self-check: (1) count of `subgraph` == count of `end`, (2) no stray `end` after the last subgraph closure, (3) all node IDs referenced in edges are defined, (4) labels with special chars are quoted
- Use - or * for unordered lists, 1. 2. 3. for ordered lists
- Use **bold** and *italic* for emphasis
- Use `inline code` and ```language code blocks for code
- Do NOT use HTML tags in the Markdown body
- Keep the Markdown clean and well-formatted

Finally, output a SINGLE JSON block containing the structured data and architecture diagram definition.

### JSON STRUCTURE SPECIFICATION

```json
{{
  "title": "Concise project title",
  "metrics": {{
    "deployment": "Cloud / On-prem / Hybrid (Recommended based on BRD scope)",
    "resources": "Estimated team size based on scope.",
    "complexity": "Low / Medium / High",
    "timeline": "Estimated duration based on complexity.",
    "project_type": "greenfield | brownfield | modernization  — MUST be derived from document signals. greenfield=new build from scratch. brownfield=changes to existing app. modernization=migration/rewrite."
  }},

  "questions": [
    "Clarification question 1 regarding missing data in BRD.",
    "Clarification question 2 regarding constraints in BRD.",
    "Clarification question 3 regarding ambiguous requirements."
  ],
  
  "prerequisites": [
    {{
      "name": "Specific Prerequisite Name (e.g., SMTP Server Credentials)",
      "description": "Why this is needed based on BRD functional requirements.",
      "category": "credentials | apis | infrastructure | databases | cloud | dependencies",
      "priority": "high | medium | low"
    }}
  ],

  "user_flow": "A step-by-step text description of the user journey. This MUST mirror the 'Process Flow' or 'Functional Requirements' section of the BRD exactly. Do not invent steps.",

  "implementation_structure": "An ASCII directory tree. Use the Tech Stack you recommended (e.g., if you recommended React, show 'src/components').",

  "architecture": {{
    "nodes": [
      {{
        "id": "node_id",
        "label": "Specific Component Name (e.g., 'PostgreSQL Database' or 'React Frontend')",
        "layer": "frontend | backend | service | data | integration | infra",
        "type": "service | database | queue | cache | external | ui",
        "cluster": "Logical module or bounded context"
      }}
    ],
    "edges": [
      {{
        "from": "source-node-id",
        "to": "target-node-id",
        "description": "Interaction description"
      }}
    ]
  }}
}}
```

### CRITICAL RULES
1. Every section is MANDATORY. Never skip or merge sections.
2. Be maximally specific — no vague placeholders like "add auth here".
3. Every technology choice must include a version number and rationale.
4. Mermaid diagrams are required in 0.3.2 and 0.4.2.
5. The file tree in 0.5.1 must be exhaustive — every file, including DTOs, guards, decorators, interceptors, hooks, providers, and config files.
6. Scope boundaries in 0.6 must be explicit and unambiguous.
7. The deliverable table in 0.7.1 must list every single file with Priority.
8. Implementation phases in 0.7.2 must be sequentially ordered by dependency.
9. Execution patterns in 0.10 must be prescriptive, not suggestive.
10. **CLARIFICATION QUESTIONS (0.9) ARE MANDATORY**: You MUST generate 3-8 specific, actionable questions about ambiguities, missing details, or technical trade-offs. Even if the BRD seems complete, ask about edge cases, scalability, or implementation preferences.
11. Ensure the JSON is valid and enclosed in a json code block at the very end of your response."""


import json
from typing import AsyncGenerator, Union, Dict, Any

def _format_governance_context(governance_context: Optional[Dict[str, Any]]) -> str:
    """Convert governance questionnaire context into prompt text for the model."""
    if not governance_context or not isinstance(governance_context, dict):
        return ""

    lines = ["GOVERNANCE QUESTIONNAIRE CONTEXT (treat as constraints):"]

    project_name = governance_context.get("project_name")
    hard_stops = governance_context.get("hard_stops") or []

    if project_name:
        lines.append(f"- Project Name: {project_name}")
    
    if hard_stops:
        lines.append("- Hard Stops (Critical Issues):")
        for stop in hard_stops:
            lines.append(f"  - {stop}")

    answers = governance_context.get("answers")
    if isinstance(answers, list) and answers:
        lines.append("- Governance Questionnaire Answers:")
        for answer in answers:
            if not isinstance(answer, dict):
                continue
            question_label = answer.get("question") or f"Question {answer.get('question_id', '')}".strip()
            selected_option = answer.get("selected_option") or "No option selected"
            dimension = answer.get("dimension")

            detail_parts = [selected_option]
            if dimension:
                detail_parts.append(f"dimension={dimension}")

            lines.append(f"  - {question_label}: {', '.join(detail_parts)}")

    return "\n".join(lines)


async def analyze_document(
    document_content: str,
    api_url: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    stream: bool = False,
    user_feedback: Optional[str] = None,
    image_paths: Optional[list[str]] = None,
    governance_context: Optional[Dict[str, Any]] = None,
) -> Union[Dict[str, Any], AsyncGenerator[str, None]]:
    """
    Analyze a document using the configured AI provider (BRN Llama or OpenAI-compatible).
    Routes through llm_gateway based on USE_BRN_LLAMA setting.
    """
    if not llm_gateway.check_api_key(api_key):
        error = "API key not configured. Please set AI_API_KEY in your environment or provide it in the request."
        return {"status": "error", "error": error}

    model_name = llm_gateway.resolve_model(model)
    governance_text = _format_governance_context(governance_context)

    # Construct the base text content
    if user_feedback:
        text_content = (
            f"Please refine your analysis based on the following USER ANSWERS to your previous questions:\n\n"
            f"USER ANSWERS/FEEDBACK:\n{user_feedback}\n\n"
            f"ORIGINAL DOCUMENT CONTENT:\n{document_content}\n\n"
            f"Please update the Feasibility Analysis, Risks, and especially the Go/No-Go Recommendation based on these clarifications."
        )
    else:
        text_content = f"Please analyze the following document content. If images are provided, incorporate their visual information (charts, diagrams, UI flows) into your analysis:\n\n{document_content}"

    if governance_text:
        text_content += (
            f"\n\n{governance_text}\n\n"
            "Use this governance context to strengthen compliance/risk analysis and align the recommendation with governance constraints."
        )

    # Prepare user content payload (Text Only or Multimodal)
    final_user_content = text_content

    if image_paths and len(image_paths) > 0:
        import base64
        content_blocks = [{"type": "text", "text": text_content}]
        for img_path in image_paths:
            try:
                with open(img_path, "rb") as img_file:
                    base64_image = base64.b64encode(img_file.read()).decode('utf-8')
                    content_blocks.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{base64_image}"}
                    })
                    print(f"Successfully encoded and included image: {img_path}")
            except Exception as e:
                print(f"Warning: Failed to encode image {img_path}: {e}")
        final_user_content = content_blocks

    messages = [
        {"role": "system", "content": BRD_ANALYSIS_PROMPT},
        {"role": "user", "content": final_user_content},
    ]

    try:
        if stream:
            # Use llm_gateway streaming with extended timeout for comprehensive analysis
            async def stream_response():
                async for chunk in llm_gateway.call_llm_streaming(
                    messages=messages,
                    api_url=api_url,
                    api_key=api_key,
                    model=model,
                    timeout=600.0,  # 10 minutes for comprehensive Agent Action Plan
                ):
                    yield chunk
            return stream_response()
        else:
            # Non-streaming: use llm_gateway with extended timeout
            data = await llm_gateway.call_llm(
                messages=messages,
                api_url=api_url,
                api_key=api_key,
                model=model,
                timeout=600.0,  # 10 minutes for comprehensive Agent Action Plan
            )
            print(f"Document Analysis AI response/n/n=================FROM ai_service.py line 528=============={data}")
            
            content = llm_gateway.extract_content_from_response(data)
            log_llm_interaction_ai_service(messages, content)
            reasoning_from_api = llm_gateway.extract_reasoning_from_response(data)

            # Clean up ქ blocks from content if present
            if "ქ" in content:
                think_match = re.search(r"ქ(.*?)ქ", content, re.DOTALL)
                if think_match and not reasoning_from_api:
                    reasoning_from_api = think_match.group(1).strip()
                content = re.sub(r"ქ.*?ქ", "", content, flags=re.DOTALL).strip()

            # Repair architecture block if missing
            if not _has_architecture_block(content):
                repair_prompt = _build_architecture_repair_prompt(content)
                repair_messages = [
                    {"role": "system", "content": BRD_ANALYSIS_PROMPT},
                    {"role": "user", "content": repair_prompt},
                ]
                try:
                    repair_data = await llm_gateway.call_llm(
                        messages=repair_messages,
                        api_url=api_url,
                        api_key=api_key,
                        model=model,
                        timeout=360.0,  # 6 minutes for repair attempt
                    )
                    repaired_content = llm_gateway.extract_content_from_response(repair_data)
                    if _has_architecture_block(repaired_content):
                        content = repaired_content
                except Exception:
                    pass  # Keep original content if repair fails

            return {
                "status": "success",
                "analysis": content,
                "reasoning": reasoning_from_api if reasoning_from_api else None,
                "model": data.get("model", model_name),
                "usage": data.get("usage", {})
            }

    except httpx.TimeoutException:
        error = "Request timed out. The document may be too large or the API is slow."
        if stream:
             async def error_gen(): yield f"Error: {error}"
             return error_gen()
        return {"status": "error", "error": error}
    except httpx.HTTPStatusError as e:
        error = f"API returned error {e.response.status_code}: {e.response.text}"
        if stream:
             async def error_gen(): yield f"Error: {error}"
             return error_gen()
        return {"status": "error", "error": error}
    except Exception as e:
        error = str(e)
        if stream:
             async def error_gen(): yield f"Error: {error}"
             return error_gen()
        return {"status": "error", "error": error}


async def get_ai_config() -> dict:
    """Get current AI configuration (without exposing the full API key)."""
    use_brn = llm_gateway.is_brn_llama_enabled()
    key = settings.ai_api_key
    masked_key = None
    if key and key != "your-api-key-here":
        masked_key = f"{key[:8]}...{key[-4:]}" if len(key) > 12 else "***"
    
    return {
        "provider": "brn_llama" if use_brn else "nvidia_openai_compatible",
        "use_brn_llama": use_brn,
        "api_url": llm_gateway.resolve_url(),
        "api_key_configured": llm_gateway.check_api_key(),
        "api_key_masked": None if use_brn else masked_key,
        "model": llm_gateway.resolve_model()
    }

FULL_PROJECT_TASK_PROMPT = """You are an expert Software Architect, Project Manager, and Agile Practitioner.
You are generating the FULL, COMPREHENSIVE task list for a software project in a SINGLE pass.

═══════════════════════════════════════════════════════
PART 1 — STACK DETECTION (Read the BRD analysis FIRST before generating any tasks)
═══════════════════════════════════════════════════════

From the BRD ANALYSIS REPORT, identify:
- FRONTEND: Which UI framework is used? (React, Vue, Next.js, Angular, Svelte, None, etc.)
- BACKEND: Which server framework is used? (FastAPI, Express, Django, Flask, NestJS, None, etc.)
- DATABASE: Which database is used? (PostgreSQL, MongoDB, SQLite, None, etc.)
- IS_FULLSTACK: true if both frontend AND backend are explicitly required
- IS_FRONTEND_ONLY: true if only a UI layer is needed
- IS_BACKEND_ONLY: true if only a server/API layer is needed

Use this detection to drive ALL task generation below. NEVER generate frontend tasks for a backend-only
project, and NEVER generate backend tasks for a frontend-only project.

═══════════════════════════════════════════════════════
PART 2 — TASK-00: THE IMMOVABLE GATEWAY (ALWAYS the first task, sequence 1)
═══════════════════════════════════════════════════════

NON-NEGOTIABLE TASK-00 RULES:
1. Task with sequence 1 is ALWAYS the FIRST object in the JSON array. No exceptions.
2. Task 1 (TASK-00) has phase="foundation" and dependencies=[] (no dependencies).
3. ALL other tasks MUST include 1 in their dependencies array.
4. Task 1 wallet MUST be 10 (maximum — it is the most critical task in the project).
5. Task 1 scope is STRICTLY determined by the detected stack:
   - FULL-STACK: bootstrap creates BOTH frontend scaffold AND backend scaffold
   - FRONTEND-ONLY: bootstrap creates ONLY frontend structure (NO backend folders, NO server files)
   - BACKEND-ONLY: bootstrap creates ONLY backend structure (NO frontend folders, NO React/UI files)
6. Task 1 description MUST state explicitly:
   - GATEWAY TASK — all other tasks depend on this. Must complete before any other task starts.
   - The EXACT directory tree to create (derived from the BRD analysis repository structure section 0.5.1)
   - The EXACT config files to create (package.json/pyproject.toml, .env.example, .gitignore, README.md, and any framework config)
   - The EXACT entry point files to create
   - For frontend projects: AppLayout, design token file, mock data store, shared UI kit
   - For backend projects: main entry file, CORS config, health endpoint, database connection stub
   - What NOT to build in this task (no feature screens, no business logic, no DB schemas)
7. Task 1 checklist MUST contain at minimum 8 FILE-LEVEL steps (see PART 4 for format rules).

═══════════════════════════════════════════════════════
PART 3 — PHASE-BASED DEVELOPMENT (Generate ONLY phases relevant to the detected stack)
═══════════════════════════════════════════════════════

Phase "foundation" → ALWAYS required. Contains TASK-00 (sequence 1) only.

IF FRONTEND EXISTS in the detected stack:
  Phase "frontend-core" → Frontend routing setup, layout shell, design tokens, shared UI library,
    mock data store, authentication screens. These tasks DEPEND on foundation.
  Phase "frontend-features" → Feature-specific screens/pages derived from BRD requirements.
    NO real API calls — all data from mock store. DEPEND on frontend-core tasks.

IF BACKEND EXISTS in the detected stack:
  Phase "backend-core" → Database setup, core models/schemas, JWT auth implementation,
    base middleware, CORS config, error handling. DEPEND on foundation.
  Phase "backend-features" → Feature-specific API endpoints derived from BRD requirements.
    DEPEND on backend-core tasks.

IF BOTH FRONTEND AND BACKEND EXIST:
  Phase "integration" → Connect frontend to real backend APIs, replace mock data with React Query
    hooks, run E2E database connectivity tests. DEPEND on all feature tasks.

Phase "integration" also covers testing, deployment preparation, Docker setup, and CI/CD
  for ALL project types (even single-side projects).

DEPENDENCY CHAIN (strictly enforced by the `dependencies` array):
  foundation (1) → frontend-core → frontend-features → integration
  foundation (1) → backend-core → backend-features → integration

═══════════════════════════════════════════════════════
PART 4 — CHECKLIST RULES (file-level precision MANDATORY)
═══════════════════════════════════════════════════════

Every checklist item MUST be a concrete, file-level action referencing EXACT paths.
  ✗ FORBIDDEN (vague): "Set up development environment"
  ✗ FORBIDDEN (vague): "Implement service layer"
  ✗ FORBIDDEN (vague): "Build authentication module"
  ✓ REQUIRED (file-level): "Create `src/components/ui/Button.tsx` with variants: primary, secondary, ghost, danger"
  ✓ REQUIRED (file-level): "Create `backend/auth/routes.py` with POST /login, POST /register, POST /refresh-token"
  ✓ REQUIRED (file-level): "Run `npm install react@18 react-router-dom@6 @tanstack/react-query@5` and verify package-lock.json"

Checklist item counts:
  - foundation / TASK-00 tasks → minimum 8, up to 12 items
  - backend-core / backend-features tasks → 5 to 8 items
  - frontend-core / frontend-features tasks → 5 to 8 items
  - integration tasks → 4 to 7 items

═══════════════════════════════════════════════════════
PART 5 — GENERAL RULES
═══════════════════════════════════════════════════════

1. Generate ALL necessary tasks for the entire project from start to finish.
2. Provide the complete list without repeating tasks or starting over.
3. The total wallet combined for all tasks MUST NOT exceed the TOTAL WALLET provided.
4. Each task wallet MUST be between 1 and 10 (inclusive). Never 0, never above 10.
5. Wallet guide: 1-3=simple; 4-6=medium; 7-9=complex; 10=TASK-00 only.
6. YOU MUST NOT assign any agents. `assignees` MUST ALWAYS be an empty array [].
7. For `ai_first` execution mode: machine-speed deadlines (days, NOT months). A 50-task project = 2-5 DAYS.
8. NO arbitrary task cap. Complex projects need 20-40+ tasks. Simple projects need 5-10 tasks.
9. Every major screen/page = its own frontend-features task.
10. Every major API domain = its own backend-features task.
11. If prerequisites list [NOT YET PROVIDED] items, use env var placeholders and note: "NOTE: Using placeholder credentials".
12. All tasks MUST be derived ONLY from the BRD analysis — no hallucinated features.
13. DOMAIN: Assign each task a feature domain from the BRD (e.g., "auth", "user-management", "dashboard").

Output ONLY a JSON array of task objects. No markdown, no prose, no code fences. First task MUST be TASK-00.

[
  {
    "taskName": "string",
    "description": "string — include exact file paths, scope, and what this task owns vs what it must not touch",
    "assignees": [],
    "wallet": int,
    "deadline": "YYYY-MM-DD",
    "startdate": "YYYY-MM-DD",
    "task_type": "EPIC" | "FEATURE" | "STORY" | "TASK" | "BUG",
    "priority": "high" | "medium" | "low",
    "phase": "foundation" | "backend-core" | "backend-features" | "frontend-core" | "frontend-features" | "integration",
    "dependencies": [int],
    "domain": "string",
    "checklist": [
      {"text": "file-level action with exact path", "completed": false}
    ]
  }
]
"""


TASK_GENERATION_PROMPT = """system_role = "software_task_architect"

mission:
    generate real software development tasks that can be executed by engineering teams.

objectives:
    - reduce hallucination
    - generate executable dev tasks
    - support greenfield, brownfield, modernization projects
    - maintain wallet scoring
    - link task dependencies
    - generate implementation checklists
    - append new tasks without duplication
    - operate safely within context window limits

--------------------------------------------------

inputs

PROJECT_NAME
PROJECT_TYPE
PROJECT_DESCRIPTION

TECH_STACK
ARCHITECTURE
REPOSITORY_STRUCTURE

PRODUCT_REQUIREMENTS
FEATURE_REQUESTS
BUG_REPORTS

EXISTING_TASK_SUMMARY

TASK_GENERATION_MODE

MAX_TASKS_TO_GENERATE

--------------------------------------------------

allowed project types

project_type ∈ { greenfield, brownfield, modernization }

--------------------------------------------------

hallucination prevention rules

rule_1:
    tasks must only be derived from:
        PROJECT_DESCRIPTION
        PRODUCT_REQUIREMENTS
        FEATURE_REQUESTS
        BUG_REPORTS
        TECH_STACK
        ARCHITECTURE

rule_2:
    if required information is missing:
        create investigation task instead of guessing

rule_3:
    never generate tasks already present in:
        EXISTING_TASK_SUMMARY

rule_4:
    tasks must represent real engineering work
    tasks must be specific and actionable
    tasks must reference actual components from the project requirements

rule_5:
    tasks must be small enough to be executed independently

--------------------------------------------------

project strategy

if PROJECT_TYPE == "greenfield":

    generate tasks for:
        architecture design
        repository setup
        database schema
        api design
        authentication
        logging
        monitoring
        testing
        ci_cd
        deployment


if PROJECT_TYPE == "brownfield":

    analyze existing system context

    generate tasks for:
        bug fixes
        feature additions
        refactoring
        performance improvements
        test coverage


if PROJECT_TYPE == "modernization":

    identify legacy components

    generate tasks for:
        migration
        refactoring
        infrastructure modernization
        api standardization
        security upgrades

--------------------------------------------------

task creation logic

for each work_area identified:

    create task_object


task_object fields

TaskID = auto_increment

Title =
    short actionable engineering task

Description =
    implementation goal and scope

TaskType =
    feature
    bug
    refactor
    infrastructure
    investigation
    migration

Area =
    backend
    frontend
    database
    devops
    security
    architecture

Priority =
    P0 | P1 | P2 | P3

Dependencies =
    list of TaskID

WalletScore =
    numeric reward value

Checklist =
    ordered implementation steps

--------------------------------------------------

checklist generation rules

each task must contain at least 4 checklist items

checklist items must represent real development actions

checklist items must be specific to the project requirements and tech stack

--------------------------------------------------

dependency linking

if a task requires another task:

    link using TaskID

--------------------------------------------------

context window control

never load full historical task list

only use:

    EXISTING_TASK_SUMMARY

format:

    TASK_ID : SHORT_DESCRIPTION

--------------------------------------------------

append mode logic

if TASK_GENERATION_MODE == "append":

    generate tasks that:

        - are not present in EXISTING_TASK_SUMMARY
        - logically extend existing system
        - add meaningful capabilities

--------------------------------------------------

wallet scoring logic

wallet_score =

    base_score
    + complexity_weight
    + business_value_weight
    + system_impact_weight

--------------------------------------------------

output format

return structured json only

task_list = [

{
    "TaskID": integer,
    "Title": "short actionable engineering task",
    "Description": "implementation goal and scope",
    "TaskType": "feature" | "bug" | "refactor" | "infrastructure" | "investigation" | "migration",
    "Area": "backend" | "frontend" | "database" | "devops" | "security" | "architecture",
    "Priority": "P0" | "P1" | "P2" | "P3",
    "Dependencies": [TaskID],
    "WalletScore": integer,
    "Checklist": [
        "step_1",
        "step_2",
        "step_3",
        "step_4"
    ]
}

]

limit results to:

MAX_TASKS_TO_GENERATE

Output ONLY the JSON array for task_list. No markdown, no prose.
"""


BATCH_TASK_PROMPT = """system_role = "software_task_architect"

mission:
    Break down the project into executable dev tasks for engineering teams.
    You generate tasks INCREMENTALLY in batches of up to 5.

objectives:
    - reduce hallucination
    - generate executable dev tasks
    - support greenfield, brownfield, modernization projects
    - maintain wallet scoring
    - link task dependencies
    - generate implementation checklists
    - append new tasks without duplication
    - operate safely within context window limits

--------------------------------------------------

inputs

PROJECT_NAME
PROJECT_TYPE
PROJECT_DESCRIPTION
TECH_STACK
PRODUCT_REQUIREMENTS
EXISTING_TASK_SUMMARY
TASK_GENERATION_MODE
MAX_TASKS_TO_GENERATE
BATCH_NUMBER

--------------------------------------------------

allowed project types

project_type ∈ { greenfield, brownfield, modernization }

--------------------------------------------------

project strategy

if PROJECT_TYPE == "greenfield":

    generate tasks for:
        architecture design
        repository setup
        database schema
        api design
        authentication
        logging
        monitoring
        testing
        ci_cd
        deployment


if PROJECT_TYPE == "brownfield":

    analyze existing system context

    generate tasks for:
        bug fixes
        feature additions
        refactoring
        performance improvements
        test coverage


if PROJECT_TYPE == "modernization":

    identify legacy components

    generate tasks for:
        migration
        refactoring
        infrastructure modernization
        api standardization
        security upgrades

--------------------------------------------------

hallucination prevention rules

rule_1:
    tasks must only be derived from:
        PROJECT_DESCRIPTION
        PRODUCT_REQUIREMENTS
        TECH_STACK

rule_2:
    if required information is missing:
        create investigation task instead of guessing

rule_3:
    never generate tasks already present in:
        EXISTING_TASK_SUMMARY

rule_4:
    tasks must represent real engineering work
    tasks must be specific to the project requirements

rule_5:
    tasks must be small enough to be executed independently

rule_6:
    project bootstrap:
        if PROJECT_TYPE == "greenfield" and BATCH_NUMBER == 1,
        ensure the first task covers core project bootstrap based on the detected tech stack.

--------------------------------------------------

task_object fields

Use the same task_list object shape as in TASK_GENERATION_PROMPT.

If the project is fully broken down, return an empty array: [].

Output ONLY the JSON array for task_list. No markdown, no prose.
"""



def _normalize_task_wallets(tasks: list, project_wallet: int) -> list:
    """
    Normalize task wallets so the total never exceeds the project budget.
    Uses proportional scaling to fairly distribute the budget across tasks.
    Each task is guaranteed a minimum wallet of 1.
    """
    if not tasks or project_wallet <= 0:
        return tasks

    total_allocated = sum(task.get("wallet", 0) for task in tasks)

    if total_allocated <= project_wallet:
        logger.info(f"Task wallets OK: total={total_allocated}, budget={project_wallet}")
        return tasks

    logger.warning(
        f"Task wallets exceed budget: total={total_allocated}, budget={project_wallet}. "
        f"Scaling down proportionally."
    )

    num_tasks = len(tasks)
    min_reserved = num_tasks
    distributable = max(project_wallet - min_reserved, 0)

    for task in tasks:
        original = task.get("wallet", 0)
        if total_allocated > 0 and distributable > 0:
            proportion = original / total_allocated
            scaled = int(proportion * distributable)
            task["wallet"] = max(scaled, 0) + 1
        else:
            task["wallet"] = 1

    new_total = sum(task.get("wallet", 0) for task in tasks)
    diff = project_wallet - new_total
    if diff != 0 and tasks:
        largest_task = max(tasks, key=lambda t: t.get("wallet", 0))
        largest_task["wallet"] = max(largest_task["wallet"] + diff, 1)

    final_total = sum(task.get("wallet", 0) for task in tasks)
    logger.info(f"Wallet normalization complete: {num_tasks} tasks, total={final_total}, budget={project_wallet}")

    return tasks


def _parse_llm_task_response(content: str) -> list:
    """Parse the LLM response content into a list of tasks, handling think tags and markdown fences."""
    content = re.sub(r"ქ.*?ქ", "", content, flags=re.DOTALL)
    content = content.replace("```json", "").replace("```", "").strip()
    start_idx = content.find("[")
    end_idx = content.rfind("]")
    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        content = content[start_idx:end_idx + 1]
    try:
        tasks = json.loads(content)
    except json.JSONDecodeError as decode_err:
        logger.warning(f"JSONDecodeError parsing tasks: {decode_err}. Attempting basic fix.")
        # Try finding the last '}' and appending ']'
        last_brace = content.rfind("}")
        if last_brace != -1:
            try:
                repaired = content[:last_brace + 1] + "]"
                tasks = json.loads(repaired)
                logger.info("Successfully repaired truncated JSON array.")
            except json.JSONDecodeError:
                logger.error("Failed to parse JSON even after simple repair.")
                tasks = []
        else:
            logger.error("Failed to parse JSON. No objects found.")
            tasks = []

    if not isinstance(tasks, list):
        raise ValueError("LLM did not return a list")

    # Normalize alternate architect schemas into the internal shape
    for task in tasks:
        # Support spec-style field names
        if "Title" in task and "taskName" not in task:
            task["taskName"] = task.pop("Title")
        if "TaskType" in task and "task_type" not in task:
            task["task_type"] = task.pop("TaskType")
        if "Area" in task and "domain" not in task:
            task["domain"] = task.pop("Area")
        if "WalletScore" in task and "wallet" not in task:
            task["wallet"] = task.pop("WalletScore")
        if "Checklist" in task and "checklist" not in task:
            task["checklist"] = task.pop("Checklist")
        if "Dependencies" in task and "dependencies" not in task:
            task["dependencies"] = task.pop("Dependencies")

        # Clamp each task's wallet to 1-10
        w = task.get("wallet", 1)
        task["wallet"] = max(1, min(10, w))
    return tasks


CHECKLIST_GENERATION_PROMPT = """You are a senior software architect and expert project manager generating file-precise, actionable implementation checklists for AI coding agents.

CRITICAL OUTPUT RULES:
1. Output ONLY a valid JSON object — no markdown, no prose, no code fences.
2. Each key is the task ID (string). Each value is an array of checklist item objects.
3. Every checklist item MUST be a concrete, file-level action — NOT a vague milestone.
4. Reference EXACT file paths from the REPOSITORY STRUCTURE provided in the user content.
5. Order items: scaffold/setup → install dependencies → implement → wire/integrate → test → verify.

ITEM COUNT RULES (detected from task description keywords):
- Tasks with "bootstrap", "TASK-00", "project setup", "scaffold", or "foundation" → MINIMUM 10 items, up to 15
- Tasks with "backend", "api", "database", "auth", "service", "model", or "endpoint" → 6 to 9 items
- Tasks with "frontend", "ui", "screen", "page", "component", or "view" → 6 to 9 items
- Tasks with "test", "deploy", "ci/cd", "docker", or "integration" → 5 to 8 items
- All other tasks → minimum 5 items, up to 8 items

FILE-LEVEL ITEM FORMAT (MANDATORY — no exceptions):
  ✗ FORBIDDEN (vague): "Set up development environment"
  ✗ FORBIDDEN (vague): "Implement service layer"
  ✗ FORBIDDEN (vague): "Build authentication module"
  ✓ REQUIRED: "Create `src/components/ui/Button.tsx` exporting variants: primary, secondary, ghost, danger with forwarded ref and disabled state"
  ✓ REQUIRED: "Create `backend/auth/routes.py` with POST /login, POST /register, POST /refresh-token endpoints returning signed JWT access and refresh tokens"
  ✓ REQUIRED: "Create `src/mocks/mockData.ts` exporting typed arrays: mockUsers: User[] (8 records), mockProjects: Project[] (6 records) with realistic domain-appropriate names"
  ✓ REQUIRED: "Run `npm install react@18 react-dom@18 react-router-dom@6 @tanstack/react-query@5` and confirm package-lock.json is updated"

BOOTSTRAP / TASK-00 MANDATORY CHECKLIST STRUCTURE:
For tasks identified as project bootstrap, TASK-00, or project scaffold, the checklist MUST include ALL steps below (adapted to the detected tech stack from user context):
  1. Create ALL top-level directories from the repository structure: `mkdir -p <dir1> <dir2> ...` (list every directory from the repo tree)
  2. Initialize the dependency manifest at its exact path: create package.json with correct name/scripts OR pyproject.toml/requirements.txt with all packages listed
  3. Install core dependencies with exact commands: `npm install <pkg>@<version>` or `pip install <pkg>==<version>`
  4. Create ALL root config files by exact filename: tsconfig.json, vite.config.ts, tailwind.config.ts, .env.example, .gitignore, README.md
  5. Create the framework entry point at its exact path (e.g., `src/main.tsx` mounting <App /> into #root; `backend/main.py` with FastAPI app)
  6. Create the router/entry component at exact path (e.g., `src/App.tsx`) with ALL application routes pre-registered
  7. Create the shared layout at exact path (e.g., `src/components/layout/AppLayout.tsx`) with collapsible sidebar, top navbar, and <Outlet />
  8. Create the design token file at exact path (e.g., `src/styles/tokens.css`) with CSS custom properties for primary/accent/semantic colors, typography scale, spacing scale
  9. Create the global mock data store at exact path (e.g., `src/mocks/mockData.ts`) with 8+ realistic records per entity using domain-appropriate names
  10. Create ALL shared UI components at their exact paths under `src/components/ui/`: Button, Badge, Card, Modal, Drawer, DataTable, SearchInput, Toast, LoadingSkeleton, EmptyState, PageHeader
  11. Create backend entry point at exact path (e.g., `backend/main.py`) with FastAPI/Express instantiation, CORS config, and /health endpoint only — NO business logic
  12. Verify structure and commit: `git init && git add . && git commit -m 'chore: initial project scaffold'`

Use the REPOSITORY STRUCTURE and TECH STACK provided in the user message to determine exact file paths and commands.

Output format (JSON object only — no other text):
{
  "<task_id_1>": [
    {"text": "Create `src/components/ui/Button.tsx` with primary/secondary/ghost/danger variants, forwarded ref, and disabled state", "completed": false},
    {"text": "Create `backend/auth/routes.py` — POST /login and POST /logout using JWT; imports from `backend/auth/service.py`", "completed": false}
  ],
  "<task_id_2>": [
    {"text": "exact file-level action", "completed": false}
  ]
}
"""


def _normalize_generated_task_checklist(task: Dict[str, Any]) -> None:
    """Ensure generated task checklist items always follow the UI/API shape."""
    raw_checklist = task.get("checklist", [])
    if not isinstance(raw_checklist, list):
        return

    normalized_checklist = []
    for item in raw_checklist:
        if isinstance(item, str):
            normalized_checklist.append({"text": item, "completed": False})
        elif isinstance(item, dict):
            text_val = item.get("text") or item.get("step") or str(item)
            normalized_checklist.append({"text": text_val, "completed": False})

    task["checklist"] = normalized_checklist


def _normalize_generated_tasks(tasks: list, wallet_budget: int) -> list:
    """Apply shared normalization for task outputs from any prompt variant."""
    for task in tasks:
        _normalize_generated_task_checklist(task)
    return _normalize_task_wallets(tasks, wallet_budget)


async def generate_checklists_for_tasks(
    tasks_with_ids: list,
    analysis_report: str,
    api_url: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
) -> dict:
    """
    Generate file-precise checklists for a batch of tasks using the LLM.

    Args:
        tasks_with_ids: List of dicts, each with 'id', 'taskName', 'description', 'task_type'
        analysis_report: The full BRD analysis for project context (NOT truncated)

    Returns:
        Dict mapping task_id (str) -> list of checklist items
    """
    if not llm_gateway.check_api_key(api_key):
        raise Exception("API key not configured.")

    tasks_summary = json.dumps(
        [
            {
                "id": t.get("id"),
                "taskName": t.get("taskName"),
                "description": t.get("description"),
                "task_type": t.get("task_type"),
                "priority": t.get("priority"),
            }
            for t in tasks_with_ids
        ],
        indent=2,
    )

    # --- Extract repository structure from BRD analysis (section 0.5.1 or 0.5) ---
    repo_structure = ""
    _repo_patterns = [
        r'##\s*0\.5\.1\s*[^\n]*\n(.*?)(?=\n##|\Z)',
        r'###\s*0\.5\.1\s*[^\n]*\n(.*?)(?=\n###|\Z)',
        r'0\.5\.1\s*[^\n]*\n(.*?)(?=\n##|\n###|\n\d+\.|\Z)',
        r'##\s*0\.5\s+[Rr]epository[^\n]*\n(.*?)(?=\n##|\Z)',
        r'###\s*0\.5\s+[Rr]epository[^\n]*\n(.*?)(?=\n###|\Z)',
    ]
    for _pat in _repo_patterns:
        _m = re.search(_pat, analysis_report, re.IGNORECASE | re.DOTALL)
        if _m:
            _candidate = _m.group(1).strip()
            _code_block = re.search(r'```(?:text|bash|shell|tree)?\s*(.*?)\s*```', _candidate, re.DOTALL)
            repo_structure = _code_block.group(1).strip() if _code_block else _candidate
            if repo_structure:
                repo_structure = clean_repository_structure_string(repo_structure)
                break

    # --- Extract tech stack section (section 0.2) ---
    tech_stack = ""
    _ts_match = re.search(r'##\s*0\.2[^\n]*\n(.*?)(?=\n##|\Z)', analysis_report, re.IGNORECASE | re.DOTALL)
    if _ts_match:
        tech_stack = _ts_match.group(1).strip()[:2000]

    # --- Detect if any task is a bootstrap / TASK-00 / foundation task ---
    has_bootstrap_task = any(
        any(kw in str(t.get("taskName", "") + " " + t.get("description", "")).lower()
            for kw in ["task-00", "bootstrap", "scaffold", "project setup", "foundation", "gateway task"])
        for t in tasks_with_ids
    )

    # --- Build rich context for the LLM ---
    context_parts = [f"TASKS TO CREATE CHECKLISTS FOR:\n{tasks_summary}"]

    if repo_structure:
        context_parts.append(
            f"REPOSITORY STRUCTURE (use these EXACT paths in every file-level checklist item):\n{repo_structure}"
        )
    if tech_stack:
        context_parts.append(f"TECH STACK:\n{tech_stack}")

    # Fallback: if neither section was found, pass a larger slice of the analysis
    if not repo_structure and not tech_stack:
        context_parts.append(f"PROJECT CONTEXT (BRD Analysis):\n{analysis_report[:6000]}")

    if has_bootstrap_task:
        context_parts.append(
            "IMPORTANT: One or more tasks above are BOOTSTRAP / TASK-00 / foundation tasks. "
            "Apply the BOOTSTRAP MANDATORY CHECKLIST STRUCTURE from your system instructions for those tasks. "
            "Use the REPOSITORY STRUCTURE above to reference exact directory and file paths."
        )

    context_parts.append(
        "Generate file-precise, contextually accurate checklists for EVERY task listed above."
    )
    text_content = "\n\n".join(context_parts)

    messages = [
        {"role": "system", "content": CHECKLIST_GENERATION_PROMPT},
        {"role": "user", "content": text_content},
    ]

    logger.info(
        f"Generating checklists for {len(tasks_with_ids)} tasks "
        f"(has_bootstrap={has_bootstrap_task}, repo_structure={'yes' if repo_structure else 'no'})"
    )

    try:
        content = await llm_gateway.call_llm_and_extract(
            messages=messages,
            api_url=api_url,
            api_key=api_key,
            model=model,
            timeout=300.0,
        )
        print(f"Checklist Generation AI response\n\n=================FROM ai_service.py [generate_checklists_for_tasks]==============\n{content}")
        log_llm_interaction_ai_service(messages, content)
        content = content.replace("```json", "").replace("```", "").strip()
        start_idx = content.find("{")
        end_idx = content.rfind("}")
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            content = content[start_idx:end_idx + 1]
        checklists = json.loads(content)
        if not isinstance(checklists, dict):
            raise ValueError("LLM did not return a dict for checklists")
        logger.info(f"Generated checklists for {len(checklists)} tasks")
        return checklists

    except Exception as e:
        logger.error(f"Checklist generation failed: {str(e)}")
        return {}


async def generate_task_batch(
    analysis_report: str,
    agents: list,
    project_deadline: str,
    remaining_wallet: int,
    total_project_wallet: int,
    already_created_tasks: list,
    batch_number: int,
    custom_rules: Optional[str] = None,
    api_url: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    project_type: str = "greenfield", # New param
) -> list:
    """
    Generate the NEXT batch of up to 5 tasks using the LLM.
    Provides context of previously created tasks so the LLM continues
    without repeating or starting over.
    
    Checklists are generated synchronously within the task object.
    """

    if not llm_gateway.check_api_key(api_key):
        raise Exception("API key not configured.")

    if remaining_wallet <= 0:
        logger.info(f"[Batch {batch_number}] No remaining wallet. Stopping task generation.")
        return []

    current_date = datetime.now().strftime("%Y-%m-%d")
    max_tasks_to_generate = min(5, max(1, remaining_wallet))

    # Derive TASK_GENERATION_MODE and EXISTING_TASK_SUMMARY per architect spec
    if already_created_tasks:
        task_lines = []
        for idx, t in enumerate(already_created_tasks, start=1):
            title = str(t.get("taskName") or t.get("title") or "Untitled Task").strip()
            short = title[:80]
            task_lines.append(f"T{idx} : {short}")
        existing_task_summary = "\n".join(task_lines)
        task_generation_mode = "append"
    else:
        existing_task_summary = ""
        task_generation_mode = "fresh"

    # --- Extract repository structure from analysis for explicit injection ---
    _batch_repo_structure = ""
    _batch_repo_patterns = [
        r'##\s*0\.5\.1\s*[^\n]*\n(.*?)(?=\n##|\Z)',
        r'###\s*0\.5\.1\s*[^\n]*\n(.*?)(?=\n###|\Z)',
        r'0\.5\.1\s*[^\n]*\n(.*?)(?=\n##|\n###|\n\d+\.|\Z)',
        r'##\s*0\.5\s+[Rr]epository[^\n]*\n(.*?)(?=\n##|\Z)',
        r'###\s*0\.5\s+[Rr]epository[^\n]*\n(.*?)(?=\n###|\Z)',
    ]
    for _bp in _batch_repo_patterns:
        _bm = re.search(_bp, analysis_report, re.IGNORECASE | re.DOTALL)
        if _bm:
            _bc = _bm.group(1).strip()
            _bcb = re.search(r'```(?:text|bash|shell|tree)?\s*(.*?)\s*```', _bc, re.DOTALL)
            _batch_repo_structure = _bcb.group(1).strip() if _bcb else _bc
            if _batch_repo_structure:
                _batch_repo_structure = clean_repository_structure_string(_batch_repo_structure)
                break

    text_content = (
        f"PROJECT_NAME: Project\n"
        f"PROJECT_TYPE: {project_type}\n"
        f"PROJECT_DESCRIPTION:\n{analysis_report}\n\n"
        f"TECH_STACK: (see TECH STACK section inside PROJECT_DESCRIPTION above)\n"
        f"ARCHITECTURE: (see ARCHITECTURE section inside PROJECT_DESCRIPTION above)\n"
        f"REPOSITORY_STRUCTURE:\n{_batch_repo_structure if _batch_repo_structure else '(see section 0.5.1 inside PROJECT_DESCRIPTION above)'}\n\n"
        f"PRODUCT_REQUIREMENTS: (see FUNCTIONAL REQUIREMENTS section inside PROJECT_DESCRIPTION above)\n"
        f"FEATURE_REQUESTS: (see FEATURES section inside PROJECT_DESCRIPTION above)\n"
        f"BUG_REPORTS: None\n\n"
        f"EXISTING_TASK_SUMMARY:\n{existing_task_summary or 'None'}\n\n"
        f"TASK_GENERATION_MODE: {task_generation_mode}\n"
        f"MAX_TASKS_TO_GENERATE: {max_tasks_to_generate}\n"
        f"BATCH_NUMBER: {batch_number}\n"
        f"CURRENT_DATE: {current_date}\n"
        f"PROJECT_DEADLINE: {project_deadline}\n"
        f"TOTAL_PROJECT_WALLET: {total_project_wallet}\n"
        f"REMAINING_WALLET_BUDGET: {remaining_wallet}\n\n"
        f"CUSTOM_RULES:\n{custom_rules or 'None'}\n"
    )

    messages = [
        {"role": "system", "content": BATCH_TASK_PROMPT},
        {"role": "user", "content": text_content},
    ]

    logger.info(f"[Batch {batch_number}] Requesting next architectural batch. Remaining wallet: {remaining_wallet}")

    try:
        content = await llm_gateway.call_llm_and_extract(
            messages=messages,
            api_url=api_url,
            api_key=api_key,
            model=model,
            timeout=300.0,
        )
        print(f"Task Batch AI response\n\n=================FROM ai_service.py [generate_task_batch]==============\n{content}")
        log_llm_interaction_ai_service(messages, content)
        tasks = _parse_llm_task_response(content)

        if not tasks:
            logger.info(f"[Batch {batch_number}] LLM returned empty — task generation complete.")
            return []

        tasks = _normalize_generated_tasks(tasks, remaining_wallet)
        logger.info(
            f"[Batch {batch_number}] Generated {len(tasks)} tasks (with checklists), "
            f"batch wallet: {sum(t.get('wallet', 0) for t in tasks)}"
        )
        return tasks

    except httpx.HTTPStatusError as e:
        import traceback
        traceback.format_exc()
        try:
            error_body = e.response.json()
        except Exception:
            error_body = e.response.text
        raise Exception(
            f"[Batch {batch_number}] Task generation failed. HTTP {e.response.status_code}: {error_body}"
        )
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        raise Exception(
            f"[Batch {batch_number}] Task generation failed: {str(e)}\n\nTraceback:\n{error_details}"
        )


async def generate_all_tasks(
    analysis_report: str,
    agents: list,
    project_deadline: str,
    project_wallet: int,
    custom_rules: Optional[str] = None,
    api_url: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    project_type: str = "greenfield",
    process_mode: Optional[str] = None,
) -> list:
    """
    Generate all tasks for the project in a single LLM call.
    """
    if not llm_gateway.check_api_key(api_key):
        raise Exception("API key not configured.")

    if project_wallet <= 0:
        logger.info("No project wallet provided. Defaulting to empty list.")
        return []

    current_date = datetime.now().strftime("%Y-%m-%d")
    normalized_mode = str(process_mode or "").strip().lower() or "unspecified"

    text_content = (
        f"PROJECT CONSTRAINTS:\n"
        f"- Current Date (Today): {current_date}\n"
        f"- Project Type: {project_type}\n"
        f"- Project Deadline: {project_deadline}\n"
        f"- TOTAL Project Wallet: {project_wallet}\n"
        f"- Available Agents: {json.dumps(agents)}\n"
        f"- Execution Mode (process_mode): {normalized_mode}\n\n"
        f"EXECUTION MODE RULES (CRITICAL FOR CALENDAR DEADLINES):\n"
        f"- ai_first: High-speed Agentic workflows running 24/7. This is 'machine-speed'. A 100-task project should finish in 3-5 DAYS TOTAL. DO NOT use human months. Parallel execution is mandatory.\n"
        f"- vibe_coding: Prototyping speed. Developer + AI in high-sync. Expect 2x-3x human speed.\n"
        f"- developer_only: Standard human industrial calendar. Traditional project timelines apply (months).\n"
        f"- ai_assist: Standard human industrial calendar. AI helps with quality, but the project pace follows human developer availability.\n"
        f"- coexistence: Hybrid speed. Human-driven with AI acceleration. Faster than human-only, but still anchored to a human calendar.\n"
        f"BRD ANALYSIS REPORT:\n"
        f"{analysis_report}\n\n"
        f"Generate the FULL list of tasks. "
        f"The total wallet for all combined tasks must NOT exceed {project_wallet}. "
    )

    messages = [
        {"role": "system", "content": FULL_PROJECT_TASK_PROMPT},
        {"role": "user", "content": text_content},
    ]

    logger.info(f"Requesting full task generation. Total wallet: {project_wallet}")

    try:
        content = await llm_gateway.call_llm_and_extract(
            messages=messages,
            api_url=api_url,
            api_key=api_key,
            model=model,
            timeout=300.0,
        )
        print(f"Full Task Generation AI response\n\n=================FROM ai_service.py [generate_all_tasks]==============\n{content}")
        log_llm_interaction_ai_service(messages, content)
        tasks = _parse_llm_task_response(content)

        if not tasks:
            logger.info("LLM returned empty — task generation failed or complete.")
            return []

        tasks = _normalize_generated_tasks(tasks, project_wallet)

        logger.info(
            f"Generated {len(tasks)} tasks, "
            f"total wallet allocated: {sum(t.get('wallet', 0) for t in tasks)}"
        )
        return tasks

    except httpx.HTTPStatusError as e:
        import traceback
        traceback.format_exc()
        try:
            error_body = e.response.json()
        except Exception:
            error_body = e.response.text
        raise Exception(
            f"Task generation failed. HTTP {e.response.status_code}: {error_body}"
        )
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        raise Exception(
            f"Task generation failed: {str(e)}\n\nTraceback:\n{error_details}"
        )



SPRINT_MILESTONE_PROMPT = """You are an expert Agile Delivery Manager.
Given BRD analysis and project deadline, propose ONE sprint and ONE milestone to start delivery.

Output ONLY valid JSON with this shape:
{
  "sprint": {
    "name": "string",
    "summary": "string",
    "start_date": "YYYY-MM-DD",
    "deadline": "YYYY-MM-DD"
  },
  "milestone": {
    "name": "string",
    "start_date": "YYYY-MM-DD",
    "deadline": "YYYY-MM-DD"
  }
}

Rules:
- milestone dates must be inside sprint dates
- sprint deadline must be <= project deadline
- no markdown, no explanations, only JSON
"""


def _safe_date(value: str, fallback: str) -> str:
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return value
    except Exception:
        return fallback


def _default_sprint_milestone_plan(project_name: str, project_deadline: str) -> dict:
    today = datetime.utcnow().date()
    today_iso = today.strftime("%Y-%m-%d")
    safe_project_deadline = _safe_date(project_deadline, (today + timedelta(days=30)).strftime("%Y-%m-%d"))
    pd = datetime.strptime(safe_project_deadline, "%Y-%m-%d").date()
    sprint_deadline = min(today + timedelta(days=14), pd)
    if sprint_deadline < today:
        sprint_deadline = today
    milestone_deadline = min(today + timedelta(days=10), sprint_deadline)
    return {
        "sprint": {
            "name": "Sprint 1",
            "summary": f"Initial sprint for {project_name or 'the project'}",
            "start_date": today_iso,
            "deadline": sprint_deadline.strftime("%Y-%m-%d"),
        },
        "milestone": {
            "name": "Phase 1 Complete",
            "start_date": today_iso,
            "deadline": milestone_deadline.strftime("%Y-%m-%d"),
        },
    }


def _normalize_plan_dates(plan: dict, project_deadline: str) -> dict:
    default_plan = _default_sprint_milestone_plan("", project_deadline)
    project_deadline_safe = _safe_date(project_deadline, default_plan["sprint"]["deadline"])

    sprint = plan.get("sprint") if isinstance(plan, dict) else {}
    milestone = plan.get("milestone") if isinstance(plan, dict) else {}

    sprint_start = _safe_date(str(sprint.get("start_date", "")), default_plan["sprint"]["start_date"])
    sprint_deadline = _safe_date(str(sprint.get("deadline", "")), default_plan["sprint"]["deadline"])

    ss = datetime.strptime(sprint_start, "%Y-%m-%d").date()
    sd = datetime.strptime(sprint_deadline, "%Y-%m-%d").date()
    pd = datetime.strptime(project_deadline_safe, "%Y-%m-%d").date()
    if sd < ss:
        sd = ss
    if sd > pd:
        sd = pd
    if sd < ss:
        sd = ss

    milestone_start = _safe_date(str(milestone.get("start_date", "")), sprint_start)
    milestone_deadline = _safe_date(str(milestone.get("deadline", "")), sd.strftime("%Y-%m-%d"))

    ms = datetime.strptime(milestone_start, "%Y-%m-%d").date()
    md = datetime.strptime(milestone_deadline, "%Y-%m-%d").date()
    if ms < ss:
        ms = ss
    if ms > sd:
        ms = ss
    if md < ms:
        md = ms
    if md > sd:
        md = sd

    return {
        "sprint": {
            "name": (sprint.get("name") or default_plan["sprint"]["name"]).strip(),
            "summary": (sprint.get("summary") or default_plan["sprint"]["summary"]).strip(),
            "start_date": ss.strftime("%Y-%m-%d"),
            "deadline": sd.strftime("%Y-%m-%d"),
        },
        "milestone": {
            "name": (milestone.get("name") or default_plan["milestone"]["name"]).strip(),
            "start_date": ms.strftime("%Y-%m-%d"),
            "deadline": md.strftime("%Y-%m-%d"),
        },
    }


async def generate_sprint_milestone_plan(
    analysis_report: str,
    project_name: str,
    project_deadline: str,
    api_url: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
) -> dict:
    """Generate one sprint and one milestone plan from BRD context."""

    default_plan = _default_sprint_milestone_plan(project_name, project_deadline)
    if not llm_gateway.check_api_key(api_key):
        return default_plan

    text_content = (
        f"Project Name: {project_name or 'Project'}\n"
        f"Project Deadline: {project_deadline}\n\n"
        f"BRD ANALYSIS REPORT:\n{analysis_report[:5000]}\n\n"
        "Create one practical initial sprint and one milestone."
    )

    messages = [
        {"role": "system", "content": SPRINT_MILESTONE_PROMPT},
        {"role": "user", "content": text_content},
    ]

    try:
        content = await llm_gateway.call_llm_and_extract(
            messages=messages,
            api_url=api_url,
            api_key=api_key,
            model=model,
            timeout=120.0,
        )
        content = content.replace("```json", "").replace("```", "").strip()
        start = content.find("{")
        end = content.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return default_plan
        parsed = json.loads(content[start:end + 1])
        return _normalize_plan_dates(parsed, project_deadline)
    except Exception as e:
        logger.warning(f"Sprint/milestone AI planning failed, using defaults: {e}")
        return default_plan


# Keep the legacy single-shot function for backward compatibility
async def generate_tasks_for_project(
    analysis_report: str,
    agents: list,
    project_deadline: str,
    project_wallet: int,
    api_url: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    project_type: str = "greenfield",
) -> list:
    """Legacy: generates all tasks in a single LLM call. Use generate_task_batch for incremental generation."""
    if not llm_gateway.check_api_key(api_key):
        raise Exception("API key not configured.")

    current_date = datetime.now().strftime("%Y-%m-%d")

    text_content = (
        f"INPUTS:\n"
        f"- PROJECT_TYPE: {project_type}\n"
        f"- CURRENT_DATE: {current_date}\n"
        f"- PROJECT_DEADLINE: {project_deadline}\n"
        f"- TOTAL_PROJECT_WALLET: {project_wallet}\n"
        f"- AVAILABLE_AGENTS: {json.dumps(agents)}\n\n"
        f"PROJECT_DESCRIPTION (BRD Analysis):\n"
        f"{analysis_report}\n"
    )

    messages = [
        {"role": "system", "content": TASK_GENERATION_PROMPT},
        {"role": "user", "content": text_content},
    ]

    logger.info(f"Starting Architectural Task Generation with model '{llm_gateway.resolve_model(model)}'")

    try:
        content = await llm_gateway.call_llm_and_extract(
            messages=messages,
            api_url=api_url,
            api_key=api_key,
            model=model,
            timeout=300.0,
        )
        tasks = _parse_llm_task_response(content)

        # Normalize fields if LLM used alternate architect names
        for t in tasks:
            if "Title" in t and "taskName" not in t:
                t["taskName"] = t.pop("Title")
            if "WalletScore" in t and "wallet" not in t:
                t["wallet"] = t.pop("WalletScore")

            # Ensure checklist is normalized
            raw_checklist = t.get("checklist", [])
            if isinstance(raw_checklist, list):
                normalized_checklist = []
                for item in raw_checklist:
                    if isinstance(item, str):
                        normalized_checklist.append({"text": item, "completed": False})
                    elif isinstance(item, dict):
                        text_val = item.get("text") or item.get("step") or str(item)
                        normalized_checklist.append({"text": text_val, "completed": False})
                t["checklist"] = normalized_checklist

        tasks = _normalize_task_wallets(tasks, project_wallet)
        return tasks

    except httpx.HTTPStatusError as e:
        import traceback
        traceback.format_exc()
        try:
            error_body = e.response.json()
        except Exception:
            error_body = e.response.text
        raise Exception(
            f"Task generation failed. HTTP {e.response.status_code}: {error_body}"
        )
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        raise Exception(f"Failed during task generation: {str(e)}\n\nTraceback:\n{error_details}")


def build_chat_messages(message: str, context: Optional[dict] = None) -> list:
    """Build the messages list for the chat LLM call."""
    system_prompt = """You are a friendly AI assistant built into a project management platform. Your job is to help users understand what each page does and guide them through the platform.

PLATFORM OVERVIEW:
This platform guides teams through a complete AI-powered project workflow:
1. Sign up and create your organization
2. Start a new project and fill in a governance questionnaire
3. Review and provide prerequisites the AI extracted from your requirements
4. Let AI generate a full task plan with sprints and milestones
5. Onboard AI agents to work on your tasks
6. Monitor progress and manage execution in real time

KEY CAPABILITIES:
- Uploads and analyzes Business Requirement Documents (BRDs)
- Scores your project across 6 governance dimensions
- Automatically identifies what credentials, APIs, and infrastructure you need before dev starts
- Generates a complete task breakdown with priorities and deadlines
- Supports multiple working modes (Developer Only, AI Assist, AI-First, etc.)
- Integrates with GitHub and Azure DevOps
- Lets you monitor AI agents working on your project in real time

RESPONSE RULES — follow these strictly:
- Never mention URL paths, route names, or technical identifiers (e.g. do NOT say "/agents", "path: /agents", or "route /dashboard")
- Speak in plain, friendly language a non-technical user can understand
- When describing a page, explain what the user can actually DO there, not what the system does internally
- Keep responses concise and practical — bullet points are fine for lists of actions
- Do not use jargon like "SSE", "endpoint", "payload", "API route", etc.
- If the user asks about a page, describe its purpose and key actions in simple terms"""

    if context:
        current_step = context.get('currentStep', '')
        current_path = context.get('currentPath', '/')
        if current_step:
            system_prompt += f"\n\nCURRENT PAGE: The user is on the \"{current_step}\" page. Describe what this page is for and what they can do here in plain, friendly language. Do not mention the URL or any technical route names."

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": message},
    ]


async def chat_with_llm(
    message: str,
    context: Optional[dict] = None,
    api_url: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
) -> str:
    """
    Context-aware chat function for conversational interactions with the LLM.
    """
    if not llm_gateway.check_api_key(api_key):
        raise Exception("API key not configured.")

    messages = build_chat_messages(message, context)

    try:
        content = await llm_gateway.call_llm_and_extract(
            messages=messages,
            api_url=api_url,
            api_key=api_key,
            model=model,
            timeout=60.0,
        )
        print(f"Chat AI response\n\n=================FROM ai_service.py [chat_with_llm]==============\n{content}")
        log_llm_interaction_ai_service(messages, content)
        return content.strip()

    except httpx.HTTPStatusError as e:
        try:
            error_body = e.response.json()
        except Exception:
            error_body = e.response.text
        raise Exception(
            f"Chat request failed. HTTP {e.response.status_code}: {error_body}"
        )
    except Exception as e:
        raise Exception(f"Failed during chat: {str(e)}")