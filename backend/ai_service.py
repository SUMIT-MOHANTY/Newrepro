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


def _has_architecture_block(text: str) -> bool:
    parsed = _extract_json_object(text)
    if not isinstance(parsed, dict):
        return False
    architecture = parsed.get("architecture")
    return isinstance(architecture, dict)


def _build_architecture_repair_prompt(previous_response: str) -> str:
    return (
        "Your previous response is missing or contains an invalid JSON block with an 'architecture' object.\n"
        "Return the FULL response again with the SAME HTML report body, and end with ONE valid JSON block in a "
        "```json``` fence that includes: title, metrics, questions, prerequisites, user_flow, "
        "implementation_structure, and architecture (nodes + edges).\n\n"
        "Previous response:\n\n"
        f"{previous_response}"
    )

# BRD Analysis System Prompt
PREREQUISITE_CATEGORIES: List[tuple[str, str]] = [
    ("credentials", "API keys, authentication tokens, OAuth secrets, SSL certificates, SSH keys, SSO/LDAP access"),
    ("apis", "Third-party API integrations, payment gateways, webhooks, callback URLs"),
    ("infrastructure", "CI/CD pipelines, Docker/Kubernetes, SMTP/email, domain/DNS, firewalls, monitoring/logging"),
    ("databases", "Database credentials, connection strings, cache servers (Redis/Memcache)"),
    ("cloud", "AWS/Azure/GCP accounts, S3/blob storage, CDN, cloud subscriptions"),
    ("dependencies", "Private package registries, licensed libraries, SDK access"),
]

def _build_prerequisite_section() -> str:
    """Construct the prerequisite description block dynamically from ``PREREQUISITE_CATEGORIES``.
    This makes the prompt generic and easy to adjust via configuration.
    """
    lines = [
        "# 5. Prerequisites & Credentials",
        "Identify ALL prerequisites, credentials, infrastructure, external services, and access requirements that must be arranged BEFORE development can begin. Be thorough and specific. For each prerequisite, classify it into one of these categories:",
    ]
    for cat, desc in PREREQUISITE_CATEGORIES:
        lines.append(f"- **{cat}**: {desc}")
    lines.append("")
    lines.append("List each prerequisite in a clear bullet format with its category and priority (high/medium/low).")
    return "\n".join(lines)

BRD_ANALYSIS_PROMPT = f"""You are an expert Senior Business Analyst and Technical Architect.
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

{_build_prerequisite_section()}

# 6. Go / No-Go Recommendation
**[GO / NO-GO / PROCEED WITH CAUTION]**
Provide a definitive recommendation on whether to proceed with development, accompanied by a short justification based on the clarity and feasibility of the requirements.

Output format rules for the main report body (everything before the final JSON block):
- Use valid HTML only.
- Use semantic tags such as: <h2>, <h3>, <p>, <ul>, <ol>, <li>, <table>, <thead>, <tbody>, <tr>, <th>, <td>, <strong>, <em>.
- Do NOT use Markdown syntax (no `#`, `**`, `*`, or pipe-table markdown).
- Do NOT wrap the HTML content in code fences.

Finally, output a SINGLE JSON block containing the key metrics, targeted questions, prerequisites, AND a detailed application architecture diagram.
{{
  "title": "A concise, one-sentence summary title for the project",
  "metrics": {{
    "deployment": "Cloud / On-prem / Hybrid (extracted from requirements)",
    "resources": "Estimated team size (e.g., '3-5 Developers')",
    "complexity": "Low / Medium / High",
    "timeline": "Estimated duration (e.g., '3-4 Months')",
    "project_type": "greenfield / brownfield / modernization (Identify based on whether it's a new build, extension of current app, or tech stack upgrade)"
  }},

  "questions": [
    "How many concurrent users are expected?",
    "What is the total expected user base?",
    "Question 3"
  ],
  "prerequisites": [
    {{
      "name": "Short descriptive name (e.g., 'AWS S3 Bucket Access')",
      "description": "Detailed description of what is needed and why",
      "category": "one of: credentials, apis, infrastructure, databases, cloud, dependencies",
      "priority": "high / medium / low"
    }}
  ],

  "user_flow": "A user journey diagram definition describing the end-to-end flow through the application for the primary user types (public users, internal operators, admins, etc.). Derive this ONLY from the business / functional requirements and roles described in the BRD. The flow MUST: (1) start from the primary actor(s), (2) include authentication if the system requires login, (3) include each major feature or workflow (such as performing a calculation, submitting a form, placing an order), (4) include viewing results/confirmation, and (5) include end-of-session actions such as logout/exit where applicable. Steps should align with the architecture modules (for example: Edge/WAF → Frontend → API Gateway → Auth Service → Domain Services → Databases/Ledger). If the BRD does not provide enough detail, fall back to a standard web flow and explicitly note this assumption in the HTML report.",

  "implementation_structure": "A high-level but concrete code structure for the system using an ASCII directory-style tree (for example: 'myproject/', '├── app/', '│   ├── api/', ...).",

  "architecture": {{
    "nodes": [
      {{
        "id": "string-unique-node-id",
        "label": "Short name (e.g., 'API Gateway', 'XYZ Service', 'Ledger DB')",
        "layer": "frontend | backend | service | data | integration | infra",
        "type": "service | database | queue | cache | external | ui",
        "cluster": "Logical module / bounded context for visual grouping (e.g., 'Edge', 'Frontend', 'Banking', 'Insurance', 'Ledger & Reporting')"
      }}
    ],
    "edges": [
      {{
        "from": "source-node-id",
        "to": "target-node-id",
        "description": "short text describing the interaction (e.g., 'HTTPS JSON API', 'writes ledger events')"
      }}
    ]
  }}
}}
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
    use_brn_llama = bool(getattr(settings, "use_brn_llama", False))
    url = api_url or (settings.brn_llama_url if use_brn_llama else settings.ai_api_url)
    key = api_key or settings.ai_api_key
    model_name = model or (settings.brn_model if use_brn_llama else settings.ai_model)

    if not use_brn_llama and (not key or key == "your-api-key-here"):
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

    # Prepare request payloads
    openai_payload = {
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

    if isinstance(final_user_content, list):
        brn_user_prompt = "\n\n".join(
            block.get("text", "")
            for block in final_user_content
            if isinstance(block, dict) and block.get("type") == "text"
        ).strip()
    else:
        brn_user_prompt = str(final_user_content)
    brn_prompt = f"{BRD_ANALYSIS_PROMPT}\n\n{brn_user_prompt}"

    brn_payload = {
        "model": model_name,
        "prompt": brn_prompt,
        "stream": False,
        "agent_id": settings.brn_agent_id,
        "platform_id": settings.brn_platform_id,
        "max_tokens": settings.brn_max_tokens,
        "temperature": settings.brn_temperature,
    }

    openai_headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {key}"
    }
    brn_headers = {
        "Content-Type": "application/json"
    }

    try:
        client = httpx.AsyncClient(timeout=120.0)
        
        if stream:
            if use_brn_llama:
                async def stream_response():
                    try:
                        response = await client.post(url, json=brn_payload, headers=brn_headers)
                        response.raise_for_status()
                        data = response.json()
                        content = data.get('response', data.get('text', data.get('content', '')))
                        response_chunk = {
                            "choices": [{
                                "delta": {
                                    "content": content if content else None,
                                    "reasoning_content": None
                                }
                            }]
                        }
                        yield f"data: {json.dumps(response_chunk)}\n\n"
                        yield "data: [DONE]\n\n"
                    except Exception as e:
                        yield f"data: {json.dumps({'error': str(e)})}\n\n"
                    finally:
                        await client.aclose()
                return stream_response()

            async def stream_response():
                try:
                    # State machine to handle <think> tags embedded in content
                    # Some models (e.g. minimax-m2.5) put reasoning inside <think> in content
                    _inside_think = False
                    _think_buffer = ""

                    async with client.stream("POST", url, json=openai_payload, headers=openai_headers) as response:
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
                if use_brn_llama:
                    response = await client.post(url, json=brn_payload, headers=brn_headers)
                else:
                    response = await client.post(url, json=openai_payload, headers=openai_headers)
                response.raise_for_status()
                
                data = response.json()

                if use_brn_llama:
                    content = data.get('response', data.get('text', data.get('content', '')))
                    if not _has_architecture_block(content):
                        repair_prompt = _build_architecture_repair_prompt(content)
                        repair_payload = {
                            "model": model_name,
                            "prompt": f"{BRD_ANALYSIS_PROMPT}\n\n{repair_prompt}",
                            "stream": False,
                            "agent_id": settings.brn_agent_id,
                            "platform_id": settings.brn_platform_id,
                            "max_tokens": settings.brn_max_tokens,
                            "temperature": settings.brn_temperature,
                        }
                        repair_response = await client.post(url, json=repair_payload, headers=brn_headers)
                        repair_response.raise_for_status()
                        repair_data = repair_response.json()
                        repaired_content = repair_data.get('response', repair_data.get('text', repair_data.get('content', '')))
                        if _has_architecture_block(repaired_content):
                            content = repaired_content
                    return {
                        "status": "success",
                        "analysis": content,
                        "reasoning": None,
                        "model": data.get("model", model_name),
                        "usage": data.get("usage", {})
                    }

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

                    if not _has_architecture_block(content):
                        repair_prompt = _build_architecture_repair_prompt(content)
                        repair_payload = {
                            "model": model_name,
                            "messages": [
                                {"role": "system", "content": BRD_ANALYSIS_PROMPT},
                                {"role": "user", "content": repair_prompt}
                            ],
                            "stream": False,
                            "chat_template_kwargs": {
                                "thinking": False
                            }
                        }
                        repair_response = await client.post(url, json=repair_payload, headers=openai_headers)
                        repair_response.raise_for_status()
                        repair_data = repair_response.json()
                        if "choices" in repair_data and len(repair_data["choices"]) > 0:
                            repair_message = repair_data["choices"][0].get("message", {})
                            repaired_content = repair_message.get("content", "")
                            if _has_architecture_block(repaired_content):
                                content = repaired_content
                    
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
    use_brn_llama = bool(getattr(settings, "use_brn_llama", False))
    key = settings.ai_api_key
    masked_key = None
    if key and key != "your-api-key-here":
        masked_key = f"{key[:8]}...{key[-4:]}" if len(key) > 12 else "***"
    
    return {
        "provider": "brn_llama" if use_brn_llama else "nvidia_openai_compatible",
        "use_brn_llama": use_brn_llama,
        "api_url": settings.brn_llama_url if use_brn_llama else settings.ai_api_url,
        "api_key_configured": True if use_brn_llama else bool(key and key != "your-api-key-here"),
        "api_key_masked": None if use_brn_llama else masked_key,
        "model": settings.brn_model if use_brn_llama else settings.ai_model
    }

FULL_PROJECT_TASK_PROMPT = """You are an expert Project Manager and Agile Practitioner.
You are generating the FULL, COMPREHENSIVE task list for a project all at once.

CRITICAL: The VERY FIRST task you create (task with ID 1, phase="foundation")
MUST be a **full-stack project bootstrap** that creates a COMPLETE, CLEAN and
PRODUCTION-READY project structure for BOTH backend AND frontend.

RULES:
1. Generate ALL necessary tasks for the entire project from start to finish.
2. Provide the complete list without repeating tasks or starting over.
3. The total wallet combined for all tasks MUST NOT exceed the TOTAL WALLET provided.
4. Each task's wallet MUST be between 1 and 10 (inclusive). Never assign 0 or any value above 10.
5. YOU MUST NOT assign any agents. The `assignees` field MUST ALWAYS be an empty array `[]`.
6. Ensure tasks follow a logical sequence from project start to completion (e.g., setup before features, features before testing).
7. **Complexity-based Scoring**: Assign wallet points (1-10) based on task complexity (Simple = 1-3, Medium = 4-6, High/Complex = 7-10).
8. **Smart Budgeting**: You MUST complete the entire project development within the total project wallet. Allocate points smartly so that high-priority/complex tasks get sufficient budget while still leaving enough for the remaining development.
9. **Placeholder Handling for Missing Prerequisites**: If the PREREQUISITES section lists items marked as [NOT YET PROVIDED], you MUST include in the relevant task descriptions:
    - Use environment variables with placeholder defaults (e.g., `API_KEY=your-api-key-here`) so the app can still run.
    - Use mock/stub services where applicable (e.g., mock SMTP, in-memory cache instead of Redis, local file storage instead of S3).
    - Add a clear note in the task description like: "NOTE: Using placeholder credentials — replace with real values once provided."
    - This ensures development is NOT blocked by missing credentials or access.
10. **PHASE-BASED DEVELOPMENT**: Assign each task to a phase based on its nature:
    - "foundation": Project setup, structure, API contracts, database schema, configuration files.
      For FULL-STACK projects (e.g., React + Flask), the **foundation phase MUST create**:
        * Core application directories (e.g., backend logic, frontend scaffolding) appropriate for the stack.
        * Core dependencies definition (`requirements.txt`, `package.json`, virtualenvs/bundler configs)
        * Root-level files: `.env.example`, `.gitignore`, `README.md`, (optionally) `docker-compose.yml`
    - "backend-core": Core backend features (auth system, base models, base API setup, middleware)
    - "backend-features": Feature-specific backend endpoints (books API, members API, transactions API)
    - "frontend-core": Frontend setup (routing, state management, API service layer, auth UI) BUILDING ON the foundation structure
    - "frontend-features": Feature-specific frontend components (Books UI, Members UI, Transactions UI)
    - "integration": Testing, bug fixes, deployment preparation, end-to-end integration
11. **DEPENDENCIES**: List task IDs from prior tasks that must complete BEFORE a given task can start:
    - Foundation tasks have NO dependencies (empty array [])
    - Backend features depend on backend-core tasks
    - Frontend features depend on frontend-core tasks AND corresponding backend-features tasks
    - Integration tasks depend on all feature tasks
12. **DOMAIN**: Assign each task to a feature domain for better organization (e.g. "auth", "books", "members", "common", "infrastructure").

Output ONLY a JSON array of task objects with this structure:
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
    "dependencies": [int],  // Array of prior task IDs that must complete first. Foundation tasks have [].
    "domain": "string"      // Feature domain: "auth", "books", "members", "transactions", "reports", "common", "infrastructure"
  }
]

Do not include any other markdown, text, or explanations. Only output the JSON array.
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

    bad example:
        "improve performance"

    good example:
        "implement redis caching for user profile api"

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

good checklist examples:

    - analyze current module
    - design interface
    - implement service layer
    - add database migration
    - write unit tests
    - update documentation

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

rule_5:
    tasks must be small enough to be executed independently

rule_6:
    project bootstrap:
        if PROJECT_TYPE == "greenfield" and BATCH_NUMBER == 1,
        ensure the first task covers core project bootstrap (repo, basic architecture, pipelines).

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
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL)
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

    url = api_url or settings.ai_api_url
    key = api_key or settings.ai_api_key
    model_name = model or settings.ai_model

    if not key or key == "your-api-key-here":
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

    text_content = (
        f"PROJECT_NAME: Project\n"
        f"PROJECT_TYPE: {project_type}\n"
        f"PROJECT_DESCRIPTION:\n{analysis_report}\n\n"
        f"TECH_STACK: (embedded in analysis if available)\n"
        f"ARCHITECTURE: (embedded in analysis if available)\n"
        f"REPOSITORY_STRUCTURE: (embedded in analysis if available)\n\n"
        f"PRODUCT_REQUIREMENTS: (embedded in analysis if available)\n"
        f"FEATURE_REQUESTS: (embedded in analysis if available)\n"
        f"BUG_REPORTS: (embedded in analysis if available)\n\n"
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

    logger.info(f"[Batch {batch_number}] Requesting next architectural batch. Remaining wallet: {remaining_wallet}")

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

                tasks = _normalize_generated_tasks(tasks, remaining_wallet)
                logger.info(
                    f"[Batch {batch_number}] Generated {len(tasks)} tasks (with checklists), "
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
    url = api_url or settings.ai_api_url
    key = api_key or settings.ai_api_key
    model_name = model or settings.ai_model

    if not key or key == "your-api-key-here":
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
        f"- Execution Mode (process_mode): {normalized_mode}\n"
        f"\n"
        f"EXECUTION MODE RULES (MUST FOLLOW):\n"
        f"- ai_first: schedule assumes AI-only execution speed.\n"
        f"- coexistence: schedule assumes AI + human work simultaneously (fastest calendar duration).\n"
        f"- developer_only: schedule assumes human-only execution speed.\n"
        f"- ai_assist: schedule MUST follow human-only calendar timing.\n"
        f"- vibe_coding: schedule assumes AI-only execution speed.\n"
        f"BRD ANALYSIS REPORT:\n"
        f"{analysis_report}\n\n"
        f"{'CUSTOM RULES TO FOLLOW:' + chr(10) + custom_rules + chr(10) + chr(10) if custom_rules else ''}"
        f"Generate the FULL list of tasks. "
        f"The total wallet for all combined tasks must NOT exceed {project_wallet}. "
    )

    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": FULL_PROJECT_TASK_PROMPT},
            {"role": "user", "content": text_content},
        ],
        "stream": False,
        "chat_template_kwargs": {"thinking": False},
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {key}",
    }

    logger.info(f"Requesting full task generation. Total wallet: {project_wallet}")

    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            logger.info(f"LLM response status: {response.status_code}")
            response.raise_for_status()

            data = response.json()
            if "choices" in data and len(data["choices"]) > 0:
                content = data["choices"][0].get("message", {}).get("content", "")
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
    project_type: str = "greenfield",
) -> list:
    """Legacy: generates all tasks in a single LLM call. Use generate_task_batch for incremental generation."""
    url = api_url or settings.ai_api_url
    key = api_key or settings.ai_api_key
    model_name = model or settings.ai_model

    if not key or key == "your-api-key-here":
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

    logger.info(f"Starting Architectural Task Generation with model '{model_name}'")

    try:
        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            logger.info(f"Received LLM response with status {response.status_code}")
            response.raise_for_status()

            data = response.json()
            if "choices" in data and len(data["choices"]) > 0:
                content = data["choices"][0].get("message", {}).get("content", "")
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
