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


INTELLIGENT_TASK_GENERATION_PROMPT = """You are an EXPERT Project Architect and Task Breakdown Specialist with 100% SUCCESS RATE REQUIREMENT.

CRITICAL MISSION: Generate ONLY the tasks needed to fulfill the BRD requirements. No forced padding, no artificial minimums.

BULLETPROOF TASK RULES:
1. Every task MUST be executable by AI agents with 90%+ success rate
2. Every task MUST include COMPLETE setup, dependencies, and validation steps
3. Every task MUST be specific enough that AI cannot misinterpret
4. Every task MUST include error handling and fallback approaches
5. Every task MUST be testable and verifiable

FLEXIBLE HIERARCHY RULE — CREATE ONLY WHAT'S NEEDED:
- Use EPICs for large multi-feature projects
- Use FEATUREs for major capabilities
- Use STORYs for user-facing slices
- Use TASKs for atomic implementation units
- For simple projects, you may only need 1 EPIC → 1 FEATURE → 1 STORY → 1-3 TASKs
- Create as many or as few tasks as the BRD actually requires

EXAMPLE STRUCTURE (adapt based on project complexity):
EPIC-01: [High-level goal]
  └── FEATURE-01: [Major capability under EPIC-01]
        └── STORY-01: [User-facing slice of FEATURE-01]
              ├── TASK-01: [Implement specific file/endpoint/component]
              └── TASK-02: [Implement another specific file/endpoint/component] (only if needed)
        └── STORY-02: [Another slice] (only if needed)
              └── TASK-03: ... (only if needed)

TASK TYPE DEFINITIONS (100% SUCCESS FOCUSED):
- EPIC     → Large goal spanning multiple features. wallet: 8-10. linked_tasks: []
- FEATURE  → Major capability with COMPLETE implementation plan. wallet: 5-7. linked_tasks: [parent EPIC id]
- STORY    → User-facing slice with DETAILED acceptance criteria. wallet: 3-4. linked_tasks: [parent FEATURE id]
- TASK     → Single atomic unit with BULLETPROOF implementation steps (1 dev, 1-4 hrs). wallet: 1-3. linked_tasks: [parent STORY id]
- BUG      → Defect fix with EXACT reproduction steps. wallet: 1-3. linked_tasks: [related STORY or TASK id]

CRITICAL: TASK-00 is ALWAYS the first task generated with type TASK. It creates the complete project scaffold.
All other TASKs must include "TASK-00" in their linked_tasks to ensure they run after the scaffold is ready.

═══════════════════════════════════════════════════════════════
BULLETPROOF TASK REQUIREMENTS — 100% SUCCESS GUARANTEE
═══════════════════════════════════════════════════════════════

Every TASK must be BULLETPROOF with these elements:

1. EXACT FILE PATHS: Specify exact files to create/modify
2. COMPLETE DEPENDENCIES: List ALL required packages, imports, setup
3. STEP-BY-STEP IMPLEMENTATION: Break down into micro-steps
4. ERROR HANDLING: Include try-catch, validation, fallbacks
5. VERIFICATION STEPS: How to test/validate the implementation
6. STACK-SPECIFIC DETAILS: Technology-specific best practices

BULLETPROOF TASK NAME RULE — 15 TO 25 CHARACTERS MAX:
✅ GOOD: "User Auth API"
✅ GOOD: "Login Component"  
✅ GOOD: "Database Setup"
❌ BAD: "Implement comprehensive user authentication system with JWT tokens"

BULLETPROOF CHECKLIST REQUIREMENTS:
Each checklist item must be MICRO-STEP with EXACT commands/code:

✅ BULLETPROOF: "Create file: src/models/User.js with class User { constructor(email, password) { this.email = email; this.password = bcrypt.hashSync(password, 10); } }"
✅ BULLETPROOF: "Run: npm install express bcrypt jsonwebtoken --save"
✅ BULLETPROOF: "Add to package.json scripts: \"start\": \"node server.js\""
✅ BULLETPROOF: "Create endpoint: POST /api/auth/login that validates email/password and returns JWT token"
❌ VAGUE: "Set up user authentication"
❌ VAGUE: "Install dependencies"
❌ VAGUE: "Create login system"

✅ VALID TASK names (short, clear):
  - "TASK: User Registration API"
  - "TASK: Login & JWT Auth"
  - "TASK: Payment Processing"
  - "TASK: Policy Enrollment UI"
  - "TASK: Premium Scheduler"
  - "TASK: Ledger Write Service"

❌ INVALID TASK names (too long / technical):
  - "TASK: premium_schedule (policy_id UUID FK, next_due DATE, status ENUM)"
  - "TASK: Implement POST /api/auth/register with bcrypt and JWT HS256 24h expiry"
  - "TASK: Create users table migration with UUID primary key and role enum"

RULE: If the name is longer than 30 characters or contains code/SQL/schema syntax, it is WRONG. Shorten it.

❌ NEVER create a standalone TASK for these — they are CHECKLIST ITEMS only:
  - "Create DB migration" → checklist item inside the TASK that needs the schema
  - "Run npm install" → checklist item
  - "Configure environment variables" → checklist item
  - "Set up CI/CD pipeline" → checklist item (unless the whole STORY is about DevOps)
  - "Install dependencies" → checklist item
  - "Create .env file" → checklist item
  - "Initialize git repo" → checklist item
  - "Write README" → checklist item (unless documentation is the explicit deliverable)

RULE: If the work is "run a command" or "edit a config file" rather than "write application code", it belongs in the checklist of the TASK that needs it — NOT as its own TASK.

EXAMPLE — DB migration belongs INSIDE the task that needs it:
  TASK-03: "TASK: Implement User model and authentication endpoints"
  checklist: [
    "Create DB migration: users(id UUID, email VARCHAR UNIQUE, password_hash VARCHAR, role ENUM, created_at TIMESTAMP)",
    "Implement User SQLAlchemy model in models.py",
    "Implement POST /api/auth/register with bcrypt password hashing",
    "Implement POST /api/auth/login returning JWT (HS256, 24h expiry)",
    "Add auth middleware to protect private routes"
  ]
  ← The migration is a checklist step, NOT a separate TASK.

═══════════════════════════════════════════════════════════════

BULLETPROOF CHECKLIST QUALITY — MICRO-STEP PRECISION:

Each checklist item must be a MICRO-STEP that an AI agent can execute with 100% clarity.
Create ONLY the checklist items needed for the task - no forced minimums.

✅ BULLETPROOF EXAMPLES:
- "Create directory: mkdir -p src/components/auth"
- "Install package: npm install express@4.18.2 --save"
- "Create file: src/config/database.js with module.exports = { host: 'localhost', port: 5432, database: 'myapp' }"
- "Add route: app.post('/api/users', async (req, res) => { const user = new User(req.body); await user.save(); res.json(user); })"
- "Run migration: npx sequelize-cli db:migrate"
- "Test endpoint: curl -X POST http://localhost:3000/api/users -H 'Content-Type: application/json' -d '{\"name\":\"test\"}'"

✅ BULLETPROOF PATTERNS:
- "Create file: [exact_path] with [exact_content_or_structure]"
- "Install: [exact_package_name_and_version]"
- "Add to [file]: [exact_code_snippet]"
- "Run command: [exact_terminal_command]"
- "Test: [exact_verification_step]"

❌ VAGUE EXAMPLES (NEVER USE):
- "Set up authentication" → TOO VAGUE
- "Create user model" → MISSING DETAILS
- "Add validation" → NO SPECIFICS
- "Configure database" → UNCLEAR STEPS
- "Implement API" → TOO BROAD

CHECKLIST LENGTH: Create as many or as few items as needed. 1 item is fine if that's all the task requires.

DEPENDENCY LINKING (linked_tasks field):
- EPIC: linked_tasks = []
- FEATURE: linked_tasks = ["EPIC-01"]  ← its parent EPIC
- STORY: linked_tasks = ["FEATURE-01"]  ← its parent FEATURE
- TASK: linked_tasks = ["STORY-01", "TASK-XX"]  ← parent STORY + previous sibling TASK if sequential dependency exists

CRITICAL: If tasks within the same STORY must execute sequentially (e.g., TASK-02 needs files created by TASK-01), 
add the previous TASK to linked_tasks. Example:
- TASK-01: linked_tasks = ["STORY-01"]  ← first task in story
- TASK-02: linked_tasks = ["STORY-01", "TASK-01"]  ← depends on TASK-01 completing first
- TASK-03: linked_tasks = ["STORY-01", "TASK-02"]  ← depends on TASK-02 completing first

This ensures agents execute tasks in the correct order and prevents race conditions on shared files.

TASK ID NAMING CONVENTION:
- EPICs:    EPIC-01, EPIC-02, ...
- FEATUREs: FEATURE-01, FEATURE-02, ...
- STORYs:   STORY-01, STORY-02, ...
- TASKs:    TASK-00 (bootstrap), TASK-01, TASK-02, ... (sequential across ALL stories, never reset)

OUTPUT FORMAT — STRICT JSON ARRAY:

CRITICAL: The FIRST task in the array MUST ALWAYS be TASK-00 with type TASK (the project bootstrap task).

[
  {
    "task_id": "TASK-00",
    "taskName": "TASK: Project Bootstrap",
    "task_type": "TASK",
    "assignedTo": [],
    "description": "<p>Create the complete project scaffold with all directories, config files, and empty file skeletons based on the tech stack.</p><p>Directory structure to create:</p><pre>[FULL DIRECTORY TREE HERE - copy from FILE STRUCTURE section]</pre><p>Files to create: package.json, requirements.txt, app.py skeleton, index.html skeleton, etc.</p>",
    "startdate": "YYYY-MM-DD",
    "planned_start": "YYYY-MM-DD",
    "deadline": "YYYY-MM-DD",
    "priority": "critical",
    "task_wallet": 3,
    "sprint": "new",
    "milestone": "main",
    "reported_by": "system",
    "linked_tasks": [],
    "checklist": "{\"checklistItems\": [{\"text\": \"Create directory structure as specified\", \"completed\": false}, {\"text\": \"Create all config files (package.json, requirements.txt, etc.)\", \"completed\": false}, {\"text\": \"Create empty skeleton files for main modules\", \"completed\": false}, {\"text\": \"Initialize git repo if needed\", \"completed\": false}, {\"text\": \"Verify all directories and files are created\", \"completed\": false}]}"
  },
  {
    "task_id": "EPIC-01",
    "taskName": "EPIC: [Descriptive name]",
    "task_type": "EPIC",
    "assignedTo": [],
    "description": "<p>What this epic delivers and its acceptance criteria.</p>",
    "startdate": "YYYY-MM-DD",
    "planned_start": "YYYY-MM-DD",
    "deadline": "YYYY-MM-DD",
    "priority": "high",
    "task_wallet": 9,
    "sprint": "new",
    "milestone": "main",
    "reported_by": "system",
    "linked_tasks": [],
    "checklist": "{\"checklistItems\": [{\"text\": \"Specific step 1\", \"completed\": false}, {\"text\": \"Specific step 2\", \"completed\": false}, {\"text\": \"Specific step 3\", \"completed\": false}]}"
  },
  {
    "task_id": "FEATURE-01",
    "taskName": "FEATURE: [Descriptive name]",
    "task_type": "FEATURE",
    "assignedTo": [],
    "description": "<p>What this feature delivers.</p>",
    "startdate": "YYYY-MM-DD",
    "planned_start": "YYYY-MM-DD",
    "deadline": "YYYY-MM-DD",
    "priority": "high",
    "task_wallet": 6,
    "sprint": "new",
    "milestone": "main",
    "reported_by": "system",
    "linked_tasks": ["EPIC-01"],
    "checklist": "{\"checklistItems\": [{\"text\": \"Step 1\", \"completed\": false}]}"
  },
  {
    "task_id": "STORY-01",
    "taskName": "STORY: [User-facing slice name]",
    "task_type": "STORY",
    "assignedTo": [],
    "description": "<p>As a [user], I want [capability] so that [benefit].</p>",
    "startdate": "YYYY-MM-DD",
    "planned_start": "YYYY-MM-DD",
    "deadline": "YYYY-MM-DD",
    "priority": "high",
    "task_wallet": 3,
    "sprint": "new",
    "milestone": "main",
    "reported_by": "system",
    "linked_tasks": ["FEATURE-01"],
    "checklist": "{\"checklistItems\": [{\"text\": \"Step 1\", \"completed\": false}]}"
  },
  {
    "task_id": "TASK-01",
    "taskName": "TASK: Implement [specific functionality]",
    "task_type": "TASK",
    "assignedTo": [],
    "description": "<p>Implement [specific technical description].</p><p>Files to modify:</p><ul><li>backend/app.py - Add database connection</li><li>backend/models.py - Create User model</li></ul><p>Specific changes: In backend/app.py, add SQLAlchemy setup. In backend/models.py, create User class with email and password fields.</p>",
    "startdate": "YYYY-MM-DD",
    "planned_start": "YYYY-MM-DD",
    "deadline": "YYYY-MM-DD",
    "priority": "high",
    "task_wallet": 2,
    "sprint": "new",
    "milestone": "main",
    "reported_by": "system",
    "linked_tasks": ["STORY-01", "TASK-00"],
    "checklist": "{\"checklistItems\": [{\"text\": \"Edit backend/app.py: add SQLAlchemy config\", \"completed\": false}, {\"text\": \"Edit backend/models.py: create User model\", \"completed\": false}, {\"text\": \"Add input validation\", \"completed\": false}]}"
  },
  {
    "task_id": "TASK-02",
    "taskName": "TASK: Extend [file from TASK-01]",
    "task_type": "TASK",
    "assignedTo": [],
    "description": "<p>Add REST endpoints to backend/app.py.</p><p>Files to modify:</p><ul><li>backend/app.py - Add CRUD endpoints</li></ul><p>Specific changes: In backend/app.py, add POST /api/users, GET /api/users, PUT /api/users/:id, DELETE /api/users/:id endpoints.</p>",
    "startdate": "YYYY-MM-DD",
    "planned_start": "YYYY-MM-DD",
    "deadline": "YYYY-MM-DD",
    "priority": "high",
    "task_wallet": 2,
    "sprint": "new",
    "milestone": "main",
    "reported_by": "system",
    "linked_tasks": ["STORY-01", "TASK-00", "TASK-01"],
    "checklist": "{\"checklistItems\": [{\"text\": \"Edit backend/app.py: add POST /api/users endpoint\", \"completed\": false}, {\"text\": \"Edit backend/app.py: add GET /api/users endpoint\", \"completed\": false}, {\"text\": \"Edit backend/app.py: add PUT /api/users/:id endpoint\", \"completed\": false}, {\"text\": \"Edit backend/app.py: add DELETE /api/users/:id endpoint\", \"completed\": false}]}"
  }
]

ANALYSIS PROCESS — FOLLOW THIS EXACTLY:
1. Read the full BRD, governance context, prerequisites, and tech stack.
2. Identify the core deliverables of the project.
3. **FIRST**: Create TASK-00 with type TASK. This is the bootstrap task that creates the complete project scaffold (all directories, config files, empty skeletons). Include the full directory tree from FILE STRUCTURE section in its description.
4. For each deliverable, create ONE EPIC (or skip if project is very simple).
5. Under each EPIC, create FEATUREs for major capabilities (only if needed).
6. Under each FEATURE, create STORYs for user-facing slices (only if needed).
7. Under each STORY, create TASKs - AS MANY OR AS FEW AS NEEDED (each TASK = one file/endpoint/component to implement).
8. **CRITICAL**: For every TASK (TASK-01, TASK-02, etc.), include explicit file paths in the description. Example: "Edit backend/app.py to add CRUD endpoints" or "Modify frontend/src/App.jsx to add routing". This tells agents exactly which files to work on.
9. Put DB migrations, config changes, installs as CHECKLIST ITEMS inside the relevant TASK — never as standalone TASKs.
10. **CRITICAL**: For TASKs within the same STORY, determine if they have sequential dependencies:
   - If TASK-02 modifies/extends files created by TASK-01, add TASK-01 to TASK-02's linked_tasks
   - If TASK-03 needs TASK-02's output, add TASK-02 to TASK-03's linked_tasks
   - ALL TASKs (TASK-01 onwards) must include "TASK-00" in linked_tasks (bootstrap dependency)
   - If tasks are independent (different files, no shared dependencies), they can run in parallel
11. Set dates: TASKs first, then STORYs after their TASKs, then FEATUREs after their STORYs, then EPICs last.
12. Write specific, actionable checklists for every task - only the steps actually needed.

FINAL CHECK BEFORE OUTPUT:
- **CRITICAL**: Is TASK-00 with type TASK the first task in the array? If not, add it.
- Does TASK-00 description contain the full directory tree from FILE STRUCTURE section? If not, add it.
- Do all other TASKs (TASK-01, TASK-02, etc.) have "TASK-00" in their linked_tasks? If not, add it.
- Do all TASK descriptions include explicit file paths (e.g., "Edit backend/app.py", "Modify frontend/src/App.jsx")? If not, add them.
- Does any TASK represent only "run a command" or "create a config file"? If yes, merge it into the checklist of the relevant TASK.
- Are all linked_tasks referencing valid task_ids in the array? If not, fix them.
- **CRITICAL**: For each TASK, check if it modifies files created by a previous TASK in the same STORY. If yes, add that previous TASK to linked_tasks.
- Is every TASK wallet 1-3? If not, fix it.
- Are TASK numbers sequential starting from TASK-01 (after TASK-00) across ALL stories? If not, fix them.
- Did you create ONLY tasks for BRD requirements (no deployment/security/infrastructure unless explicitly required)? If not, remove extras.
- Output ONLY the JSON array. No markdown, no explanation, no text before or after.
"""


def _parse_task_json(content: str) -> List[Dict[str, Any]]:
    """Parse LLM response and extract task JSON array"""
    try:
        # Remove markdown code blocks
        content = content.replace("```json", "").replace("```", "").strip()
        
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


def _validate_task_structure(task: Dict[str, Any]) -> bool:
    """Validate that task has required fields"""
    required_fields = ["task_id", "taskName", "task_type", "description", "task_wallet"]
    
    for field in required_fields:
        if field not in task:
            logger.warning(f"Task missing required field: {field}")
            return False
    
    # Validate task_type
    valid_types = ["EPIC", "FEATURE", "STORY", "TASK", "BUG"]
    if task.get("task_type") not in valid_types:
        logger.warning(f"Invalid task_type: {task.get('task_type')}")
        return False
    
    # Validate wallet — coerce to int if needed
    wallet = task.get("task_wallet", 0)
    if isinstance(wallet, float):
        wallet = int(wallet)
        task["task_wallet"] = wallet
    if not isinstance(wallet, int) or wallet < 1 or wallet > 10:
        # Auto-fix out-of-range wallets instead of rejecting
        task_type = task.get("task_type", "TASK")
        defaults = {"EPIC": 9, "FEATURE": 5, "STORY": 3, "TASK": 1, "BUG": 2}
        task["task_wallet"] = defaults.get(task_type, 1)
        logger.warning(f"Fixed invalid task_wallet {wallet} → {task['task_wallet']} for {task.get('task_id')}")
    
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
    
    # Get latest document analysis — try to match project first, fallback to latest
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

PREREQUISITES (user-confirmed only — treat these as the ONLY known prerequisites):
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
            return []
        
        # Validate and filter tasks with bulletproof enhancement
        valid_tasks = []
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
        
        # Apply bulletproof post-processing
        bulletproof_tasks = _bulletproof_task_generation_post_process(valid_tasks)
        
        logger.info(f"Generated {len(bulletproof_tasks)} bulletproof tasks for project {project_token}")
        
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