"""
AI Service for BRD Analysis
Supports OpenAI-compatible APIs (OpenAI, NVIDIA, Azure, local LLMs, etc.)
"""
import httpx
from typing import Optional
from config import settings
import logging
from datetime import datetime

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

# 5. Go / No-Go Recommendation
**Verdict: [GO / NO-GO / PROCEED WITH CAUTION]**
Provide a definitive recommendation on whether to proceed with development, accompanied by a short justification based on the clarity and feasibility of the requirements.

Output format rules for the main report body (everything before the final JSON block):
- Use valid HTML only.
- Use semantic tags such as: <h2>, <h3>, <p>, <ul>, <ol>, <li>, <table>, <thead>, <tbody>, <tr>, <th>, <td>, <strong>, <em>.
- Do NOT use Markdown syntax (no `#`, `**`, `*`, or pipe-table markdown).
- Do NOT wrap the HTML content in code fences.

Finally, output a SINGLE JSON block containing both the key metrics and the targeted questions.
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
                                        
                                        # Construct a clean chunk to proxy back to frontend
                                        # Use OpenAI format so frontend parser works seamlessly
                                        response_chunk = {
                                            "choices": [{
                                                "delta": {
                                                    "content": delta.get("content"),
                                                    "reasoning_content": delta.get("reasoning_content")
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
                    reasoning = message.get("reasoning_content", "")
                    
                    return {
                        "status": "success",
                        "analysis": content,
                        "reasoning": reasoning if reasoning else None,
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

You are provided with a team of Agents (with their `user_id` and `username`) and a wallet budget.
You MUST format your ONLY output as a JSON array of task objects matching this exact structure:

[
  {
    "taskName": "string", // Short descriptive title
    "description": "string", // Detailed description of the work
    "assignees": [int], // Array of `user_id` numbers of the agents who will work on this
    "wallet": int, // Estimated cost/effort from the budget
    "deadline": "YYYY-MM-DD", // A realistic deadline within the project timeframe
    "startdate": "YYYY-MM-DD", // Start date within the project timeframe
    "task_type": "string", // Must be one of: "EPIC", "FEATURE", "STORY", "TASK", "BUG"
    "priority": "string" // Must be one of: "high", "medium", "low"
  }
]

Do not include any other markdown, text, or explanations. Only output the JSON array.
"""

async def generate_tasks_for_project(
    analysis_report: str,
    agents: list,
    project_deadline: str,
    project_wallet: int,
    api_url: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None
) -> list:
    """Uses the LLM to auto-generate tasks based on an analysis report and available agents."""
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
            {
                "role": "system",
                "content": TASK_GENERATION_PROMPT
            },
            {
                "role": "user",
                "content": text_content
            }
        ],
        "stream": False,
        "chat_template_kwargs": {
            "thinking": False
        }
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {key}"
    }

    logger.info(f"Starting AI Task Generation with model '{model_name}'")
    logger.info(f"Passing {len(agents)} agents to LLM context.")
    
    try:
        # Increase timeout drastically (e.g. 5 minutes) as mapping a whole project to tasks can take a long time for the LLM
        async with httpx.AsyncClient(timeout=300.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            
            logger.info(f"Received LLM response with status {response.status_code}")
            
            response.raise_for_status()
            
            data = response.json()
            if "choices" in data and len(data["choices"]) > 0:
                content = data["choices"][0].get("message", {}).get("content", "")
                content = content.replace("```json", "").replace("```", "").strip()
                try:
                     tasks = json.loads(content)
                     if not isinstance(tasks, list):
                         raise ValueError("LLM did not return a list")
                     return tasks
                except Exception as e:
                     raise Exception(f"Failed to parse LLM response into tasks array: {e}\nResponse was: {content}")
            else:
                raise Exception("No response from AI model")
    except httpx.HTTPStatusError as e:
        import traceback
        error_details = traceback.format_exc()
        try:
             error_body = e.response.json()
        except:
             error_body = e.response.text
        raise Exception(f"Failed during task generation. HTTP Status: {e.response.status_code}. Response: {error_body}")
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        raise Exception(f"Failed during task generation: {str(e)}\n\nTraceback:\n{error_details}")
