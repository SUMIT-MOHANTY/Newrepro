"""
AI Service for BRD Analysis
Supports OpenAI-compatible APIs (OpenAI, NVIDIA, Azure, local LLMs, etc.)
"""
import httpx
from typing import Optional
from config import settings
import logging
import re
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# BRD Analysis System Prompt
BRD_ANALYSIS_PROMPT = """You are an expert Senior Business Analyst and Technical Architect.
Analyze the provided Business Requirement Document (BRD) or client requirements.

Your analysis must include the following sections exactly:

# 1. Executive Summary
Briefly summarize the project scope and primary objectives.

# 2. Key Requirements Breakdown
- **Functional Requirements**: Core features and user interactions.
- **Non-Functional Requirements**: Performance, security, scalability, and compliance needs.


# 3. Feasibility Analysis
Assess the technical viability of the project.
- **Complexity Assessment**: Low/Medium/High with reasoning.
- **Tech Stack Recommendations**: Suggested technologies if not specified.
- **Potential Challenges**: Technical bottlenecks or difficult implementations.

# 4. Risks & Gap Analysis
- **Missing Elements**: What is not defined but should be?
- **Business Risks**: Potential pitfalls.

# 5. Prerequisites & Credentials
Identify ALL prerequisites, credentials, infrastructure, external services, and access requirements that must be arranged BEFORE development can begin. Be thorough and specific. For each prerequisite, classify it into one of these categories:
- **credentials**: API keys, authentication tokens, OAuth secrets, SSL certificates, SSH keys, SSO/LDAP access
- **apis**: Third-party API integrations, payment gateways, webhooks, callback URLs
- **infrastructure**: CI/CD pipelines, Docker/Kubernetes, SMTP/email, domain/DNS, firewalls, monitoring/logging
- **databases**: Database credentials, connection strings, cache servers (Redis/Memcache)
- **cloud**: AWS/Azure/GCP accounts, S3/blob storage, CDN, cloud subscriptions
- **dependencies**: Private package registries, licensed libraries, SDK access

List each prerequisite in a clear bullet format with its category and priority (high/medium/low).

# 6. Go / No-Go Recommendation
**Verdict: [GO / NO-GO / PROCEED WITH CAUTION]**
Provide a definitive recommendation on whether to proceed with development, accompanied by a short justification based on the clarity and feasibility of the requirements.

Output format rules for the main report body (everything before the final JSON block):
- Use valid HTML only.
- Use semantic tags such as: <h2>, <h3>, <p>, <ul>, <ol>, <li>, <table>, <thead>, <tbody>, <tr>, <th>, <td>, <strong>, <em>.
- Do NOT use Markdown syntax (no `#`, `**`, `*`, or pipe-table markdown).
- Do NOT wrap the HTML content in code fences.

Finally, output a SINGLE JSON block containing the key metrics, targeted questions, AND prerequisites.
All targeted questions must appear ONLY in the final JSON `questions` array.
Do not include or repeat questions anywhere else in the response body.
The `questions` array should include at least 5-7 specific technical questions, covering:
- **User Volume & Scale**
- **Security & Compliance**
- **Data Strategy**
- **Integrations**
- **Platform/Device Support**
- **Reporting & Analytics**
- Any ambiguities in business logic or user flows
The JSON must follow this exact structure:
```json
{
  "title": "A concise, one-sentence summary title for the project",
  "metrics": {
    "deployment": "Cloud / On-prem / Hybrid (extracted from requirements)",
    "resources": "Estimated team size (e.g., '3-5 Developers')",
    "complexity": "Low / Medium / High",
    "timeline": "Estimated duration (e.g., '3-4 Months')"
  },
  "questions": [
    "How many concurrent users are expected?",
    "What is the total expected user base?",
    "Question 3"
  ],
  "prerequisites": [
    {
      "name": "Short descriptive name (e.g., 'AWS S3 Bucket Access')",
      "description": "Detailed description of what is needed and why",
      "category": "one of: credentials, apis, infrastructure, databases, cloud, dependencies",
      "priority": "high / medium / low"
    }
  ]
}
```
Ensure the JSON is valid and enclosed in a json code block at the very end of your response."""


import json
from typing import AsyncGenerator, Union, Dict, Any

def _format_governance_context(governance_context: Optional[Dict[str, Any]]) -> str:
    """Convert governance questionnaire context into prompt text for the model."""
    if not governance_context or not isinstance(governance_context, dict):
        return ""

    lines = ["GOVERNANCE QUESTIONNAIRE CONTEXT (treat as constraints):"]

    project_name = governance_context.get("project_name")
    classification = governance_context.get("classification")
    weighted_score = governance_context.get("weighted_score")
    hard_stops = governance_context.get("hard_stops") or []

    if project_name:
        lines.append(f"- Project Name: {project_name}")
    if classification:
        lines.append(f"- Governance Classification: {classification}")
    if weighted_score is not None:
        lines.append(f"- Governance Weighted Score: {weighted_score}/10")
    if hard_stops:
        lines.append("- Hard Stops:")
        for stop in hard_stops:
            lines.append(f"  - {stop}")

    answers = governance_context.get("answers")
    if isinstance(answers, list) and answers:
        lines.append("- Questionnaire Answers:")
        for answer in answers:
            if not isinstance(answer, dict):
                continue
            question_label = answer.get("question") or f"Question {answer.get('question_id', '')}".strip()
            selected_option = answer.get("selected_option") or "No option selected"
            score = answer.get("score")
            dimension = answer.get("dimension")

            detail_parts = [selected_option]
            if score is not None:
                detail_parts.append(f"score={score}")
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
    Analyze a document using an OpenAI-compatible API.
    
    Args:
        document_content: The extracted text/markdown from the document
        api_url: Custom API URL (uses settings default if not provided)
        api_key: API key (uses settings default if not provided)
        model: Model name (uses settings default if not provided)
        stream: Whether to stream the response
        user_feedback: Optional user clarifications/answers to refine the analysis
        image_paths: Optional list of local file paths to images extracted from the document
        governance_context: Optional governance questionnaire context from frontend
    
    Returns:
        If stream=False: dict with analysis results or error
        If stream=True: async generator yielding partial response chunks
    """
    # Use provided values or fall back to settings
    url = api_url or settings.ai_api_url
    key = api_key or settings.ai_api_key
    model_name = model or settings.ai_model
    
    if not key or key == "your-api-key-here":
        error = "API key not configured. Please set AI_API_KEY in your environment or provide it in the request."
        return {"status": "error", "error": error}
    
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
        # If images exist, construct a multimodal message list
        content_blocks = [{"type": "text", "text": text_content}]
        
        for img_path in image_paths:
            try:
                with open(img_path, "rb") as img_file:
                    base64_image = base64.b64encode(img_file.read()).decode('utf-8')
                    # Add image block
                    content_blocks.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{base64_image}"
                        }
                    })
                    print(f"Successfully encoded and included image: {img_path}")
            except Exception as e:
                print(f"Warning: Failed to encode image {img_path}: {e}")
        
        final_user_content = content_blocks

    # Prepare the request payload (OpenAI-compatible format)
    payload = {
        "model": model_name,
        "messages": [
            {
                "role": "system",
                "content": BRD_ANALYSIS_PROMPT
            },
            {
                "role": "user",
                "content": final_user_content
            }
        ],
        "stream": stream,
        "chat_template_kwargs": {
            "thinking": False
        }
    }
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {key}"
    }

    try:
        client = httpx.AsyncClient(timeout=120.0)
        
        if stream:
            async def stream_response():
                try:
                    # State machine to handle <think> tags embedded in content
                    # Some models (e.g. minimax-m2.5) put reasoning inside <think> in content
                    _inside_think = False
                    _think_buffer = ""

                    async with client.stream("POST", url, json=payload, headers=headers) as response:
                        response.raise_for_status()
                        async for line in response.aiter_lines():
                            if line.startswith("data: "):
                                data_str = line[6:]
                                if data_str.strip() == "[DONE]":
                                    break
                                try:
                                    data_json = json.loads(data_str)
                                    if "choices" in data_json and len(data_json["choices"]) > 0:
                                        delta = data_json["choices"][0].get("delta", {})
                                        
                                        raw_content = delta.get("content") or ""
                                        reasoning = delta.get("reasoning_content") or ""
                                        
                                        # Handle <think> tags inside content
                                        clean_content = ""
                                        if raw_content:
                                            if _inside_think:
                                                # Check if </think> appears in this chunk
                                                end_idx = raw_content.find("</think>")
                                                if end_idx != -1:
                                                    # Think block ends here
                                                    _think_buffer += raw_content[:end_idx]
                                                    reasoning += _think_buffer
                                                    _think_buffer = ""
                                                    _inside_think = False
                                                    # Content after </think> is real content
                                                    clean_content = raw_content[end_idx + len("</think>"):]
                                                else:
                                                    # Still inside think block
                                                    _think_buffer += raw_content
                                            else:
                                                # Check if <think> starts in this chunk
                                                start_idx = raw_content.find("<think>")
                                                if start_idx != -1:
                                                    # Content before <think> is real
                                                    clean_content = raw_content[:start_idx]
                                                    remaining = raw_content[start_idx + len("<think>"):]
                                                    # Check if </think> is also in this chunk
                                                    end_idx = remaining.find("</think>")
                                                    if end_idx != -1:
                                                        reasoning += remaining[:end_idx]
                                                        clean_content += remaining[end_idx + len("</think>"):]
                                                    else:
                                                        _inside_think = True
                                                        _think_buffer = remaining
                                                else:
                                                    clean_content = raw_content
                                        
                                        # Only yield if there's actual content or reasoning
                                        if clean_content or reasoning:
                                            response_chunk = {
                                                "choices": [{
                                                    "delta": {
                                                        "content": clean_content if clean_content else None,
                                                        "reasoning_content": reasoning if reasoning else None
                                                    }
                                                }]
                                            }
                                            yield f"data: {json.dumps(response_chunk)}\n\n"
                                except json.JSONDecodeError:
                                    continue
                except Exception as e:
                     # yield error formatted as JSON
                     yield f"data: {json.dumps({'error': str(e)})}\n\n"
                finally:
                    await client.aclose()
            
            return stream_response()
            
        else:
            # Non-streaming implementation
            try:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                
                data = response.json()
                
                # Extract the assistant's response
                if "choices" in data and len(data["choices"]) > 0:
                    message = data["choices"][0].get("message", {})
                    content = message.get("content", "")
                    reasoning_from_api = message.get("reasoning_content", "")
                    
                    # Clean up <think> blocks from content if present
                    if "<think>" in content:
                        think_match = re.search(r"<think>(.*?)</think>", content, re.DOTALL)
                        if think_match and not reasoning_from_api:
                            reasoning_from_api = think_match.group(1).strip()
                        content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
                    
                    return {
                        "status": "success",
                        "analysis": content,
                        "reasoning": reasoning_from_api if reasoning_from_api else None,
                        "model": data.get("model", model_name),
                        "usage": data.get("usage", {})
                    }
                else:
                    return {
                        "status": "error",
                        "error": "No response from AI model",
                        "raw_response": data
                    }
            finally:
                await client.aclose()
                
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
    key = settings.ai_api_key
    masked_key = None
    if key and key != "your-api-key-here":
        masked_key = f"{key[:8]}...{key[-4:]}" if len(key) > 12 else "***"
    
    return {
        "api_url": settings.ai_api_url,
        "api_key_configured": bool(key and key != "your-api-key-here"),
        "api_key_masked": masked_key,
        "model": settings.ai_model
    }

TASK_GENERATION_PROMPT = """You are an expert Project Manager and Agile Practitioner.
Given the following BRD Analysis Report and Project constraints, break down the project into an actionable, detailed task list (Epics, Features, User Stories, and Tasks).

You are provided with a team of Agents (with their `user_id` and `username`) and a wallet budget. However, YOU MUST NOT assign any agents. The `assignees` field MUST ALWAYS be an empty array `[]`.

You MUST format your ONLY output as a JSON array of task objects matching this exact structure:

[
  {
    "taskName": "string", // Short descriptive title
    "description": "string", // Detailed description of the work
    "wallet": int, // Estimated cost/effort from the budget (MUST be between 1 and 10)
    "deadline": "YYYY-MM-DD", // A realistic deadline within the project timeframe
    "startdate": "YYYY-MM-DD", // Start date within the project timeframe
    "task_type": "string", // Must be one of: "EPIC", "FEATURE", "STORY", "TASK", "BUG"
    "priority": "string" // Must be one of: "high", "medium", "low"
  }
]

COMPLEXITY & BUDGET RULES:
1. **Scoring**: Assign wallet points (1-10) based on task complexity (Simple = 1-3, Medium = 4-6, High/Complex = 7-10).
2. **Smart Allocation**: Distribute the total project wallet smartly across all phases (EPIC, FEATURE, STORY). Higher-level epics should reflect the cumulative weight of their sub-tasks.
3. **Budget Adherence**: Ensure the sum of all task wallets does not exceed the provided Total Budget Wallet.

IMPORTANT: Each task's "wallet" value MUST be between 1 and 10 (inclusive). Never assign 0 or any value above 10.
Do not include any other markdown, text, or explanations. Only output the JSON array.
"""

BATCH_TASK_PROMPT = """You are an expert Project Manager and Agile Practitioner.
You are generating tasks INCREMENTALLY for a project in batches of up to 5 tasks at a time.

CRITICAL: The VERY FIRST task you create (task with ID 1 in the first batch, phase="foundation")
MUST be a **full-stack project bootstrap** that creates a COMPLETE, CLEAN and
PRODUCTION-READY project structure for BOTH backend AND frontend.

RULES:
1. Generate the NEXT batch of up to 5 tasks only.
2. DO NOT repeat any tasks that have already been created (listed below).
3. The total wallet for this batch MUST NOT exceed the REMAINING WALLET provided.
4. Each task's wallet MUST be between 1 and 10 (inclusive). Never assign 0 or any value above 10.
5. YOU MUST NOT assign any agents. The `assignees` field MUST ALWAYS be an empty array `[]`.
6. Continue logically from where the previous batch left off.
7. Ensure tasks follow a logical sequence (e.g., setup before features, features before testing).
8. **Complexity-based Scoring**: Assign wallet points (1-10) based on task complexity (Simple = 1-3, Medium = 4-6, High/Complex = 7-10).
9. **Smart Budgeting**: You MUST complete the entire project development within the total project wallet. Allocate points smartly so that high-priority/complex tasks get sufficient budget while still leaving enough for the remaining development (e.g., don't exhaust the budget on just the first few features).
10. If all necessary tasks have already been created and the project breakdown is complete, return an EMPTY array: []
11. **Placeholder Handling for Missing Prerequisites**: If the PREREQUISITES section lists items marked as [NOT YET PROVIDED], you MUST include in the relevant task descriptions:
    - Use environment variables with placeholder defaults (e.g., `API_KEY=your-api-key-here`) so the app can still run.
    - Use mock/stub services where applicable (e.g., mock SMTP, in-memory cache instead of Redis, local file storage instead of S3).
    - Add a clear note in the task description like: "NOTE: Using placeholder credentials — replace with real values once provided."
    - This ensures development is NOT blocked by missing credentials or access.
12. **PHASE-BASED DEVELOPMENT**: Assign each task to a phase based on its nature:
    - "foundation": Project setup, structure, API contracts, database schema, configuration files.
      For FULL-STACK projects (e.g., React + Flask), the **foundation phase MUST create**:
        * `backend/` directory with: virtualenv, `requirements.txt`, `config.py`, app entry, API module layout
        * `frontend/` directory with: `package.json`, bundler config (Vite/Next/etc.), `src/` with `components/` and `pages/`, main entry files
        * Root-level files: `.env.example`, `.gitignore`, `README.md`, (optionally) `docker-compose.yml`
    - "backend-core": Core backend features (auth system, base models, base API setup, middleware)
    - "backend-features": Feature-specific backend endpoints (books API, members API, transactions API)
    - "frontend-core": Frontend setup (routing, state management, API service layer, auth UI) BUILDING ON the already-created `frontend/` structure
    - "frontend-features": Feature-specific frontend components (Books UI, Members UI, Transactions UI)
    - "integration": Testing, bug fixes, deployment preparation, end-to-end integration
13. **DEPENDENCIES**: List task IDs from "ALREADY CREATED TASKS" that must complete BEFORE this task can start:
    - Foundation tasks have NO dependencies (empty array [])
    - Backend features depend on backend-core tasks
    - Frontend features depend on frontend-core tasks AND corresponding backend-features tasks
    - Integration tasks depend on all feature tasks
    - Use sequential numbering: First batch = 1,2,3,4,5. Second batch = 6,7,8,9,10. Reference these IDs in dependencies.
14. **DOMAIN**: Assign each task to a feature domain for better organization:
    - "auth": Authentication, authorization, user management
    - "books": Book management, catalog, inventory
    - "members": Member/user management
    - "transactions": Borrowing, returning, transactions
    - "reports": Reporting, analytics, statistics
    - "common": Shared utilities, helpers, common components
    - "infrastructure": DevOps, CI/CD, deployment, infrastructure setup

Output ONLY a JSON array of task objects (max 5) with this structure:
[
  {
    "taskName": "string",
    "description": "string",
    "assignees": [],     // ALWAYS an empty array
    "wallet": int,       // MUST be between 1 and 10
    "deadline": "YYYY-MM-DD",
    "startdate": "YYYY-MM-DD",
    "task_type": "string",  // "EPIC", "FEATURE", "STORY", "TASK", or "BUG"
    "priority": "string",   // "high", "medium", or "low"
    "phase": "string",      // REQUIRED: "foundation", "backend-core", "backend-features", "frontend-core", "frontend-features", or "integration"
    "dependencies": [int],  // Array of task IDs from ALREADY CREATED TASKS that must complete first. Foundation tasks have [].
    "domain": "string"      // Feature domain: "auth", "books", "members", "transactions", "reports", "common", "infrastructure"
  }
]

If the project is fully broken down, return: []
Do not include any other markdown, text, or explanations. Only output the JSON array.
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
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL)
    content = content.replace("```json", "").replace("```", "").strip()
    start_idx = content.find("[")
    end_idx = content.rfind("]")
    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        content = content[start_idx:end_idx + 1]
    tasks = json.loads(content)
    if not isinstance(tasks, list):
        raise ValueError("LLM did not return a list")
    # Clamp each task's wallet to 1-10
    for task in tasks:
        w = task.get("wallet", 1)
        task["wallet"] = max(1, min(10, w))
    return tasks


CHECKLIST_GENERATION_PROMPT = """You are an expert Project Manager creating actionable checklists for development tasks.

Given a list of tasks, generate a checklist (sub-items) for EACH task. The checklist items should be:
1. Specific, actionable sub-steps required to complete the task.
2. Contextually relevant to the task description AND to the overall project.
3. Ordered logically (setup → implementation → testing → review).
4. Each task should have 3 to 7 checklist items.
5. All checklist items should start as NOT completed (completed: false).

Output ONLY a JSON object where each key is the task ID (as a string) and the value is an array of checklist items:
{
  "1234": [
    {"text": "Set up development environment", "completed": false},
    {"text": "Create database schema", "completed": false},
    {"text": "Write unit tests", "completed": false}
  ],
  "5678": [
    {"text": "Design API endpoints", "completed": false},
    {"text": "Implement authentication", "completed": false}
  ]
}

Do not include any other markdown, text, or explanations. Only output the JSON object.
"""


async def generate_checklists_for_tasks(
    tasks_with_ids: list,
    analysis_report: str,
    api_url: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
) -> dict:
    """
    Generate checklists for a batch of tasks using the LLM.
    
    Args:
        tasks_with_ids: List of dicts, each with 'id', 'taskName', 'description', 'task_type'
        analysis_report: The BRD analysis for project context
    
    Returns:
        Dict mapping task_id (str) -> list of checklist items
    """
    url = api_url or settings.ai_api_url
    key = api_key or settings.ai_api_key
    model_name = model or settings.ai_model

    if not key or key == "your-api-key-here":
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

    text_content = (
        f"TASKS TO CREATE CHECKLISTS FOR:\n{tasks_summary}\n\n"
        f"PROJECT CONTEXT (BRD Analysis):\n{analysis_report[:3000]}\n\n"
        f"Generate detailed, contextually relevant checklists for each task above."
    )

    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": CHECKLIST_GENERATION_PROMPT},
            {"role": "user", "content": text_content},
        ],
        "stream": False,
        "chat_template_kwargs": {"thinking": False},
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {key}",
    }

    logger.info(f"Generating checklists for {len(tasks_with_ids)} tasks")

    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()

            data = response.json()
            if "choices" in data and len(data["choices"]) > 0:
                content = data["choices"][0].get("message", {}).get("content", "")
                # Clean response
                content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL)
                content = content.replace("```json", "").replace("```", "").strip()
                # Extract JSON object
                start_idx = content.find("{")
                end_idx = content.rfind("}")
                if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                    content = content[start_idx:end_idx + 1]
                checklists = json.loads(content)
                if not isinstance(checklists, dict):
                    raise ValueError("LLM did not return a dict for checklists")
                logger.info(f"Generated checklists for {len(checklists)} tasks")
                return checklists
            else:
                raise Exception("No response from AI model for checklist generation")

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
    api_url: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
) -> list:
    """
    Generate the NEXT batch of up to 5 tasks using the LLM.
    Provides context of previously created tasks so the LLM continues
    without repeating or starting over.

    Returns an empty list when the LLM considers the breakdown complete
    or when the remaining wallet is exhausted.
    """
    url = api_url or settings.ai_api_url
    key = api_key or settings.ai_api_key
    model_name = model or settings.ai_model

    if not key or key == "your-api-key-here":
        raise Exception("API key not configured.")

    if remaining_wallet <= 0:
        logger.info(f"[Batch {batch_number}] No remaining wallet. Stopping task generation.")
        return []

    current_date = datetime.now().strftime("%Y-%m-%d")

    # Build context summary of already-created tasks
    if already_created_tasks:
        created_summary = json.dumps(
            [
                {
                    "taskName": t.get("taskName"),
                    "task_type": t.get("task_type"),
                    "wallet": t.get("wallet"),
                    "startdate": t.get("startdate"),
                    "deadline": t.get("deadline"),
                }
                for t in already_created_tasks
            ],
            indent=2,
        )
        wallet_used = sum(t.get("wallet", 0) for t in already_created_tasks)
        context_block = (
            f"\n\nALREADY CREATED TASKS ({len(already_created_tasks)} tasks, wallet used: {wallet_used}):\n"
            f"{created_summary}\n"
        )
    else:
        context_block = "\n\nNo tasks have been created yet. Start from the beginning.\n"

    text_content = (
        f"PROJECT CONSTRAINTS:\n"
        f"- Current Date (Today): {current_date}\n"
        f"- Project Deadline: {project_deadline}\n"
        f"- TOTAL Project Wallet: {total_project_wallet}\n"
        f"- REMAINING Wallet Budget: {remaining_wallet}\n"
        f"- Available Agents: {json.dumps(agents)}\n"
        f"- Batch Number: {batch_number} (generating tasks in batches of 5)\n"
        f"{context_block}\n"
        f"BRD ANALYSIS REPORT:\n"
        f"{analysis_report}\n\n"
        f"Generate the NEXT batch of up to 5 tasks. "
        f"The total wallet for this batch must NOT exceed {remaining_wallet}. "
        f"If all tasks are already covered, return an empty array []."
    )

    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": BATCH_TASK_PROMPT},
            {"role": "user", "content": text_content},
        ],
        "stream": False,
        "chat_template_kwargs": {"thinking": False},
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {key}",
    }

    logger.info(f"[Batch {batch_number}] Requesting next batch. Remaining wallet: {remaining_wallet}")

    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            logger.info(f"[Batch {batch_number}] LLM response status: {response.status_code}")
            response.raise_for_status()

            data = response.json()
            if "choices" in data and len(data["choices"]) > 0:
                content = data["choices"][0].get("message", {}).get("content", "")
                tasks = _parse_llm_task_response(content)

                if not tasks:
                    logger.info(f"[Batch {batch_number}] LLM returned empty — task generation complete.")
                    return []

                # Normalize this batch against the remaining wallet
                tasks = _normalize_task_wallets(tasks, remaining_wallet)

                logger.info(
                    f"[Batch {batch_number}] Generated {len(tasks)} tasks, "
                    f"batch wallet: {sum(t.get('wallet', 0) for t in tasks)}"
                )
                return tasks
            else:
                raise Exception("No response from AI model")

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
    url = api_url or settings.ai_api_url
    key = api_key or settings.ai_api_key
    model_name = model or settings.ai_model

    default_plan = _default_sprint_milestone_plan(project_name, project_deadline)
    if not key or key == "your-api-key-here":
        return default_plan

    text_content = (
        f"Project Name: {project_name or 'Project'}\n"
        f"Project Deadline: {project_deadline}\n\n"
        f"BRD ANALYSIS REPORT:\n{analysis_report[:5000]}\n\n"
        "Create one practical initial sprint and one milestone."
    )

    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": SPRINT_MILESTONE_PROMPT},
            {"role": "user", "content": text_content},
        ],
        "stream": False,
        "chat_template_kwargs": {"thinking": False},
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {key}",
    }

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            if "choices" not in data or not data["choices"]:
                return default_plan
            content = data["choices"][0].get("message", {}).get("content", "")
            content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
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
) -> list:
    """Legacy: generates all tasks in a single LLM call. Use generate_task_batch for incremental generation."""
    url = api_url or settings.ai_api_url
    key = api_key or settings.ai_api_key
    model_name = model or settings.ai_model

    if not key or key == "your-api-key-here":
        raise Exception("API key not configured.")

    current_date = datetime.now().strftime("%Y-%m-%d")

    text_content = (
        f"PROJECT RESTRAINTS:\n"
        f"- Current Date (Today): {current_date}\n"
        f"- Deadline: {project_deadline}\n"
        f"- Total Budget Wallet: {project_wallet}\n"
        f"- Available Agents: {json.dumps(agents)}\n\n"
        f"BRD ANALYSIS REPORT:\n"
        f"{analysis_report}\n\n"
        f"Generate the comprehensive task breakdown mapping these factors together."
    )

    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": TASK_GENERATION_PROMPT},
            {"role": "user", "content": text_content},
        ],
        "stream": False,
        "chat_template_kwargs": {"thinking": False},
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {key}",
    }

    logger.info(f"Starting AI Task Generation with model '{model_name}'")
    logger.info(f"Passing {len(agents)} agents to LLM context.")

    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            logger.info(f"Received LLM response with status {response.status_code}")
            response.raise_for_status()

            data = response.json()
            if "choices" in data and len(data["choices"]) > 0:
                content = data["choices"][0].get("message", {}).get("content", "")
                tasks = _parse_llm_task_response(content)
                tasks = _normalize_task_wallets(tasks, project_wallet)
                return tasks
            else:
                raise Exception("No response from AI model")
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
