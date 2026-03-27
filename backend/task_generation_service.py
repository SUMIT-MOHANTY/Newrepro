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


INTELLIGENT_TASK_GENERATION_PROMPT = """You are a senior AI systems architect specializing in multi-agent task orchestration.

I will give you an Agent Action Plan markdown document. Your job is to convert it into a structured task list that multiple AI coding agents can execute IN PARALLEL without conflicts.

CRITICAL: Create CHUNKED, MEANINGFUL tasks — NOT micro-tasks. Group related work together into substantial units of work.

## Core Principles

**1. AGGRESSIVE GROUPING — Merge Everything That Belongs Together**
- If two pieces of work touch the same layer/domain, they should be ONE task
- Backend auth + backend calculator = ONE backend task (not two)
- Frontend pages + frontend components = ONE frontend task (not separate)
- Integration + CORS + API client = ONE integration task (not separate)
- DO NOT split by feature within the same layer — split by LAYER

**2. Avoid Over-Fragmentation (Critical Rule)**
- Simple monolithic projects → 4-6 tasks maximum
- Medium projects with some modularity → 6-10 tasks
- Complex microservices/distributed systems → 10-15 tasks (each service can be separate)
- If you're creating more tasks than this, you're splitting too much
- BUT: In microservices, each independent service with its own database/API can be its own task

**3. Complexity-Aware Splitting**
- Analyze the project architecture first before deciding task boundaries
- Simple monolithic apps → Merge aggressively (4-6 tasks)
- Microservices/distributed systems → Each independent service can be its own task
- Key question: "Can these two things be built by the same agent without conflicts?"
  - If YES and same layer → Merge them
  - If NO or different services → Keep separate

**Examples:**
- Calculator app: Backend auth + calculator logic → MERGE (same Flask app)
- E-commerce: User Service + Product Service → KEEP SEPARATE (different microservices, different databases)
- E-commerce: Order Service + Payment Service → MERGE if tightly coupled, SEPARATE if independent

**4. Layer-Based Thinking (Not Feature-Based)**
- Think: "What can one agent own completely?"
- Backend agent owns ALL backend code (models + APIs + business logic + auth)
- Frontend agent owns ALL frontend code (pages + components + routing + styling)
- Integration agent owns ALL connection code (API calls + error handling + CORS)
- Don't split backend into "auth task" and "calculator task" — that's over-fragmentation
- EXCEPTION: In microservices, each service is independent and can be its own task

**5. Merge Small Tasks**
- If a task is < 3 wallet points, it's probably too small
- CORS setup is NOT a separate task — merge it into integration
- Config/setup is NOT a separate task — merge it into bootstrap
- Small utilities are NOT separate tasks — merge them into the layer that uses them
- EXCEPTION: In microservices, a small independent service can still be its own task

**6. Think in Parallel Execution**
- Tasks that don't share file ownership can run simultaneously
- Backend and Frontend can run in parallel (different folders)
- But don't split backend into multiple tasks just to "create more parallelism"
- Quality > artificial parallelism

Use this exact JSON format for every task:

[
  {
    "task_id": "TASK-00",
    "taskName": "Short, specific task title",
    "description": "[What to build - describe the ENTIRE scope of this task]. This agent owns: [folders/modules]. This agent must NOT modify: [other folders].",
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
      { "text": "High-level milestone covering multiple related items", "completed": false },
      { "text": "High-level milestone covering multiple related items", "completed": false },
      { "text": "High-level milestone covering multiple related items", "completed": false },
      { "text": "High-level milestone covering multiple related items", "completed": false },
      { "text": "Verify entire task scope works end-to-end with tests", "completed": false }
    ]
  }
]

---

## Sprint Assignment Logic

**Sprint = Wave of parallel execution.**
All tasks with the same sprint number will be dispatched to different agents simultaneously.
Tasks in Sprint N+1 can only start after ALL Sprint N tasks are complete.

- Sprint 1 → Foundation tasks (bootstrap, setup, infrastructure)
- Sprint 2 → Core implementation tasks that depend on Sprint 1 (can run in parallel if no file conflicts)
- Sprint 3 → Integration tasks that depend on Sprint 2 outputs
- Sprint 4 → Finalization tasks (testing, polish, deployment)

Assign sprints based on actual dependencies in the project, not a fixed formula.

---

## Task Wallet (Effort Points) Guide

Since tasks are chunked and represent complete layers:
- 2 → Very simple setup (bootstrap for tiny project)
- 3 → Standard layer with moderate scope (simple backend or simple frontend)
- 5 → Complex layer with significant scope (backend with auth + business logic + APIs)
- 8 → Very large layer or critical integration (full microservice, complex frontend with many features)

Most tasks should be 3-5 wallet points. If you have many 2-point tasks, you're splitting too much.

---

## File Ownership Rules

- Each task description MUST state: "This agent owns: [folders/modules]"
- Each task description MUST state: "This agent must NOT modify: [other folders]"
- Define clear boundaries so parallel tasks don't conflict
- Shared/common code should be created early so other tasks can depend on it

---

## Checklist Item Rules

- Checklist items should be HIGH-LEVEL milestones, not micro-steps
- Each item should cover a meaningful chunk of work (multiple files, complete feature, etc.)
- Focus on what needs to be accomplished, not how to do it step-by-step
- Last checklist item must always be a test/verification step

---

## Critical Rules

1. **TASK-00 MUST BE FIRST** - Project Bootstrap
   - This is the foundation task that creates the repository structure
   - ALL other tasks depend on TASK-00
   - Assign to Sprint 1, Infrastructure milestone
   - The repository structure will be automatically injected into this task

2. **Dependency Management:**
   - Use `linked_tasks` array to declare dependencies
   - ALL tasks (except TASK-00) must include "TASK-00" in linked_tasks
   - If Task B needs Task A's output, add Task A to Task B's linked_tasks
   - Tasks with no shared dependencies can run in parallel (same sprint)

3. **Sprint Assignment:**
   - Use the AVAILABLE SPRINTS list provided
   - Assign tasks to sprints based on their actual dependencies
   - Tasks in the same sprint should not have file ownership conflicts

4. **Milestone Assignment:**
   - Use the AVAILABLE MILESTONES list provided
   - Group related tasks under the same milestone
   - Milestones represent major functional areas or system layers

5. **File Path Accuracy:**
   - Reference folders/modules from the repository structure
   - Use paths from section 0.5.1 of the Agent Action Plan
   - Be specific about ownership boundaries

6. **Output Format:**
   - Return ONLY valid JSON array
   - No markdown code blocks, no explanations, no extra text
   - Ensure all JSON is properly escaped and valid

7. **Dynamic Task Count (Follow These Guidelines):**
   - Simple monolithic projects (calculator, todo, blog) → 4-6 tasks total
   - Medium projects (CRM, inventory, booking) → 6-10 tasks total
   - Complex microservices (e-commerce, platform) → 10-15 tasks total
   - Each independent microservice with its own DB/API → Can be its own task
   - If you exceed these ranges for monolithic apps, you're over-splitting
   - Quality over quantity — fewer meaningful tasks beat many fragmented ones

8. **Microservices Special Rule:**
   - If the project uses microservices architecture, each service can be a separate task
   - User Service, Product Service, Order Service → Can each be their own task
   - But still merge within each service (don't split a service into multiple tasks)
   - Frontend can still be one task (or split by customer/admin if very large)

9. **Common Merging Patterns:**
   - Backend auth + backend business logic → ONE backend task
   - Frontend pages + frontend components → ONE frontend task
   - Integration + CORS + error handling → ONE integration task
   - Testing + polish + deployment → ONE QA task (unless project is very large)

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
        ("Foundation & Setup", "Project foundation and infrastructure setup"),
        ("Core Development", "Core features and business logic implementation"),
        ("Integration & Testing", "System integration and comprehensive testing"),
        ("Deployment & Polish", "Production deployment and final polish")
    ]
    
    milestone_names = [
        ("Foundation Complete", "Infrastructure and setup complete"),
        ("Core Features Complete", "All core features implemented"),
        ("Integration Complete", "All systems integrated and tested"),
        ("Production Ready", "System deployed and production-ready")
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
        code_files = [f for f in files if any(f.endswith(ext) for ext in ['.py', '.js', '.ts', '.jsx', '.tsx'])]
        doc_files = [f for f in files if any(f.endswith(ext) for ext in ['.md', '.txt', '.rst'])]
        
        if config_files:
            for config_file in config_files[:5]:
                checklist.append({
                    "text": f"Create config file: touch {project_name}/{config_file}",
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
    """Extract the repository structure from section 0.5.1 of Agent Action Plan"""
    if not analysis_text:
        return ""
    
    import re
    
    # Look for section 0.5.1 - match just the number, ignore title
    patterns = [
        # Match: ## 0.5.1 (with or without title)
        r'##\s*0\.5\.1\s*[^\n]*\n(.*?)(?=\n##|\Z)',
        # Match: ### 0.5.1 (with or without title)
        r'###\s*0\.5\.1\s*[^\n]*\n(.*?)(?=\n###|\Z)',
        # Match: 0.5.1 anywhere (with or without title)
        r'0\.5\.1\s*[^\n]*\n(.*?)(?=\n##|\n###|\n\d+\.|\Z)',
        # Match: **0.5.1** (bold in markdown)
        r'\*\*0\.5\.1\*\*\s*[^\n]*\n(.*?)(?=\n##|\n###|\n\*\*\d+\.|\Z)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, analysis_text, re.IGNORECASE | re.DOTALL)
        if match:
            structure = match.group(1).strip()
            
            # Extract content from code blocks if present
            code_block_match = re.search(r'```(?:text|bash|shell|tree)?\s*(.*?)\s*```', structure, re.DOTALL)
            if code_block_match:
                extracted = code_block_match.group(1).strip()
                logger.info(f"Extracted repository structure from section 0.5.1 (from code block, {len(extracted)} chars)")
                return extracted
            
            # If no code block, return the raw content
            if structure:
                logger.info(f"Extracted repository structure from section 0.5.1 (raw content, {len(structure)} chars)")
                return structure
    
    logger.warning("Could not find section 0.5.1 in BRD analysis")
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
    
    # Get latest document analysis
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
    
    # Build project context
    context = _build_project_context(project_token, db, user_id)

    if project_type:
        context["project_type"] = project_type

    # Calculate project timeline
    today = datetime.now().date()
    if process_mode == "ai_first":
        project_deadline = today + timedelta(days=28)  # 4 weeks for 4 sprints
    elif process_mode == "vibe_coding":
        project_deadline = today + timedelta(days=42)  # 6 weeks
    else:
        project_deadline = today + timedelta(days=84)  # 12 weeks
    
    # Generate multiple sprints and milestones
    logger.info(f"Generating multiple sprints and milestones for project {project_token}")
    sprints, milestones = _generate_sprints_and_milestones(
        project_start=datetime.combine(today, datetime.min.time()),
        project_deadline=datetime.combine(project_deadline, datetime.min.time()),
        num_phases=4
    )
    
    logger.info(f"Generated {len(sprints)} sprints and {len(milestones)} milestones")
    for sprint in sprints:
        logger.info(f"  - {sprint['name']}: {sprint['start_date']} to {sprint['deadline']}")
    
    # Build sprint/milestone list for prompt with dates
    sprint_list = "\n".join([
        f"- {s['name']}: {s['start_date']} to {s['deadline']} ({s['summary']})"
        for s in sprints
    ])
    
    milestone_list = "\n".join([
        f"- {m['name']}: {m['summary']} (Sprint: {m['sprint']})"
        for m in milestones
    ])
    
    # Build prompt context
    prompt_context = f"""
AVAILABLE SPRINTS (with dates):
================================
{sprint_list}

AVAILABLE MILESTONES:
=====================
{milestone_list}

REPOSITORY STRUCTURE (from section 0.5.1):
==========================================
{context.get('repository_structure', 'Not available - extract from Agent Action Plan section 0.5.1')}

CURRENT DATE: {today.strftime('%Y-%m-%d')}
PROJECT DEADLINE: {project_deadline.strftime('%Y-%m-%d')}

===================================================================
AGENT ACTION PLAN MARKDOWN DOCUMENT
===================================================================

{context['brd_analysis'] if context['brd_analysis'] else 'No Agent Action Plan available'}

===================================================================

Generate the complete task list now. Remember:

1. **TASK-00 FIRST** - Project Bootstrap (Sprint 1, Infrastructure milestone)
   - The repository structure will be automatically injected
   - This is the foundation for all other tasks

2. **Sprint Assignment** - Assign based on dependencies:
   - Sprint 1: Foundation tasks (no dependencies except TASK-00)
   - Sprint 2: Core modules (depend on Sprint 1)
   - Sprint 3: Integration & UI (depend on Sprint 2)
   - Sprint 4: Testing & Polish (depend on Sprint 3)

3. **Parallel Execution** - Tasks in the same sprint run in parallel:
   - Ensure no file ownership conflicts
   - Clearly state "This agent owns: X" and "must NOT modify: Y"
   - Use exact file paths from repository structure

4. **Milestone Grouping** - Group by agent specialization:
   - Infrastructure, Auth, Domain Modules, Frontend, QA, Docs

5. **Dependencies** - Use linked_tasks array:
   - ALL tasks must link to TASK-00
   - Frontend tasks link to their backend API tasks
   - Integration tasks link to both modules

6. **Checklist Quality** - Each task needs 5+ specific steps:
   - Include exact file paths
   - Include exact commands
   - Last item must be a test/verification step

7. **Output** - Return ONLY valid JSON array, no markdown, no explanations

Generate tasks now:
"""
    
    messages = [
        {"role": "system", "content": INTELLIGENT_TASK_GENERATION_PROMPT},
        {"role": "user", "content": prompt_context}
    ]
    
    logger.info(f"Generating tasks for project {project_token}")
    
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
        
        logger.info(f"Parsed {len(tasks)} tasks from LLM response")
        
        # Validate and process tasks
        valid_tasks = []
        for task in tasks:
            if _validate_task_structure(task):
                # Ensure required fields
                task.setdefault("assignedTo", [])
                task.setdefault("reported_by", "system")
                task.setdefault("priority", "medium")
                task.setdefault("linked_tasks", [])
                
                # Validate sprint and milestone
                if "sprint" not in task or not task["sprint"]:
                    task["sprint"] = sprints[0]["name"]
                if "milestone" not in task or not task["milestone"]:
                    task["milestone"] = milestones[0]["name"]
                
                # Ensure dates
                if "startdate" not in task:
                    task["startdate"] = today.strftime('%Y-%m-%d')
                if "planned_start" not in task:
                    task["planned_start"] = task["startdate"]
                if "deadline" not in task:
                    days_offset = min(task["task_wallet"], 7)
                    task["deadline"] = (today + timedelta(days=days_offset)).strftime('%Y-%m-%d')
                
                # CRITICAL: Inject repository structure into TASK-00
                if task.get("task_id") == "TASK-00" and context.get("repository_structure"):
                    repo_structure = context["repository_structure"]
                    
                    # Wrap structure with markers for agent parsing
                    structure_block = f"\n\n===BEGIN_DIRECTORY_STRUCTURE===\n{repo_structure}\n===END_DIRECTORY_STRUCTURE===\n\n"
                    
                    # Add to description
                    current_desc = task.get("description", "")
                    task["description"] = current_desc + structure_block + (
                        "CRITICAL: This is the CANONICAL directory structure for the entire project. "
                        "You MUST create ALL directories and files shown in the structure above. "
                        "ALL subsequent tasks MUST reference files from this structure. "
                        "ALL agents MUST wait for this task to be completed before starting their work."
                    )
                    
                    # Generate detailed checklist from repository structure
                    detailed_checklist = _generate_bootstrap_checklist(repo_structure, context.get("project_name", "project"))
                    
                    # Replace the AI-generated checklist with our detailed one
                    if detailed_checklist:
                        task["checklist"] = detailed_checklist
                        logger.info(f"Generated {len(detailed_checklist)} detailed checklist items for TASK-00")
                    
                    logger.info(f"Injected repository structure into TASK-00 ({len(repo_structure)} chars)")
                
                valid_tasks.append(task)
        
        logger.info(f"Generated {len(valid_tasks)} valid tasks")
        
        return valid_tasks
    
    except Exception as e:
        logger.error(f"Task generation failed: {e}")
        raise Exception(f"Failed to generate tasks: {str(e)}")
