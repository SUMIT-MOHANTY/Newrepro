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


INTELLIGENT_TASK_GENERATION_PROMPT = """You are an EXPERT Project Architect and Task Breakdown Specialist.

Your mission: Analyze the provided project context and create a COMPLETE, PROPERLY STRUCTURED task breakdown with ALL levels of hierarchy.

MANDATORY HIERARCHY RULE — THIS IS NON-NEGOTIABLE:
Every EPIC must have FEATUREs.
Every FEATURE must have STORYs.
Every STORY must have at least 2-3 TASKs.
If you generate an EPIC or FEATURE without drilling down to TASK level, your output is WRONG.

REQUIRED STRUCTURE (you MUST follow this):
EPIC-01: [High-level goal]
  └── FEATURE-01: [Major capability under EPIC-01]
        └── STORY-01: [User-facing slice of FEATURE-01]
              ├── TASK-01: [Implement specific file/endpoint/component]
              ├── TASK-02: [Implement another specific file/endpoint/component]
              └── TASK-03: [Write tests / validation for the above]
        └── STORY-02: [Another slice of FEATURE-01]
              ├── TASK-04: ...
              └── TASK-05: ...
  └── FEATURE-02: [Another capability under EPIC-01]
        └── STORY-03: ...
              ├── TASK-06: ...
              └── TASK-07: ...

TASK TYPE DEFINITIONS:
- EPIC     → Large goal spanning multiple features. wallet: 8-10. linked_tasks: []
- FEATURE  → Major capability. wallet: 5-7. linked_tasks: [parent EPIC id]
- STORY    → User-facing slice of a feature. wallet: 3-4. linked_tasks: [parent FEATURE id]
- TASK     → Single atomic unit of work (1 dev, 1-4 hrs). wallet: 1-2. linked_tasks: [parent STORY id]
- BUG      → Defect fix. wallet: 1-3. linked_tasks: [related STORY or TASK id]

═══════════════════════════════════════════════════════════════
CRITICAL RULE — WHAT IS A VALID TASK vs WHAT BELONGS IN CHECKLIST
═══════════════════════════════════════════════════════════════

A TASK must represent writing or modifying actual code files.
A TASK name must describe a specific file, endpoint, component, or module being created/modified.

TASK NAME RULE — 20 TO 30 CHARACTERS MAX (excluding the "TASK: " prefix):
The taskName field must be short and human-readable. All technical detail goes in description and checklist.

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

CHECKLIST QUALITY — SPECIFIC AND ACTIONABLE:
✅ GOOD: "Create DB migration: users(id UUID, email VARCHAR UNIQUE, password_hash VARCHAR, role ENUM, created_at TIMESTAMP)"
✅ GOOD: "Implement POST /api/auth/login returning JWT signed with HS256, 24h expiry"
✅ GOOD: "Write pytest unit tests for login endpoint covering valid, invalid password, and locked account cases"
✅ GOOD: "Add input validation using Pydantic schema: email format, password min 8 chars"
❌ BAD: "Review scope for task"
❌ BAD: "Implement the feature"
❌ BAD: "Validate and document"

DEPENDENCY LINKING (linked_tasks field):
- EPIC: linked_tasks = []
- FEATURE: linked_tasks = ["EPIC-01"]  ← its parent EPIC
- STORY: linked_tasks = ["FEATURE-01"]  ← its parent FEATURE
- TASK: linked_tasks = ["STORY-01"]  ← its parent STORY

TASK ID NAMING CONVENTION:
- EPICs:    EPIC-01, EPIC-02, ...
- FEATUREs: FEATURE-01, FEATURE-02, ...
- STORYs:   STORY-01, STORY-02, ...
- TASKs:    TASK-01, TASK-02, TASK-03, ... (sequential across ALL stories, never reset)

OUTPUT FORMAT — STRICT JSON ARRAY:
[
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
    "taskName": "TASK: Implement [specific file/endpoint/component]",
    "task_type": "TASK",
    "assignedTo": [],
    "description": "<p>Implement [specific technical description]. Files: [list files to create/modify].</p>",
    "startdate": "YYYY-MM-DD",
    "planned_start": "YYYY-MM-DD",
    "deadline": "YYYY-MM-DD",
    "priority": "high",
    "task_wallet": 2,
    "sprint": "new",
    "milestone": "main",
    "reported_by": "system",
    "linked_tasks": ["STORY-01"],
    "checklist": "{\"checklistItems\": [{\"text\": \"Create DB migration if schema change needed\", \"completed\": false}, {\"text\": \"Implement the model/endpoint/component\", \"completed\": false}, {\"text\": \"Add input validation\", \"completed\": false}, {\"text\": \"Write unit tests\", \"completed\": false}]}"
  }
]

ANALYSIS PROCESS — FOLLOW THIS EXACTLY:
1. Read the full BRD, governance context, prerequisites, and tech stack.
2. Identify the core deliverables of the project.
3. For each deliverable, create ONE EPIC.
4. Under each EPIC, create FEATUREs (major capabilities).
5. Under each FEATURE, create STORYs (user-facing slices).
6. Under each STORY, create 2-4 TASKs (each TASK = one file/endpoint/component to implement).
7. Put DB migrations, config changes, installs as CHECKLIST ITEMS inside the relevant TASK — never as standalone TASKs.
8. Set dates: TASKs first, then STORYs after their TASKs, then FEATUREs after their STORYs, then EPICs last.
9. Write specific, actionable checklists for every task.

FINAL CHECK BEFORE OUTPUT:
- Does every STORY have at least 2 TASK children? If not, add them.
- Does any TASK represent only "run a command" or "create a config file"? If yes, merge it into the checklist of the relevant TASK.
- Are all linked_tasks referencing valid task_ids in the array? If not, fix them.
- Is every TASK wallet 1 or 2? If not, fix it.
- Are TASK numbers sequential across ALL stories (TASK-01, TASK-02, ... never reset)? If not, fix them.
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

            # Tech stack and requirements may be nested inside analysis text or top-level
            context["tech_stack"] = (
                analysis.get("tech_stack")
                or analysis.get("techStack")
                or ""
            )
            context["requirements"] = (
                analysis.get("requirements")
                or analysis.get("product_requirements")
                or ""
            )

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

BRD ANALYSIS:
============
{context['brd_analysis'][:3000] if context['brd_analysis'] else 'No BRD analysis available'}

TECH STACK:
==========
{context['tech_stack'] if context['tech_stack'] else 'Not specified - use best practices'}

REQUIREMENTS:
============
{context['requirements'][:2000] if context['requirements'] else 'Extract from BRD analysis'}

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

TASK GENERATION INSTRUCTIONS:
============================
Based on the above context, generate the MINIMUM set of ESSENTIAL tasks needed to successfully deliver this project.

Focus on:
1. What MUST be built to meet the requirements
2. Proper task hierarchy and dependencies
3. Realistic timelines within the {project_deadline.strftime('%Y-%m-%d')} deadline
4. Specific, actionable checklist items
5. No unnecessary or redundant tasks

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
        
        # Validate and filter tasks
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
        
        logger.info(f"Generated {len(valid_tasks)} valid tasks for project {project_token}")
        
        return valid_tasks
    
    except Exception as e:
        logger.error(f"Task generation failed: {e}")
        raise Exception(f"Failed to generate tasks: {str(e)}")
