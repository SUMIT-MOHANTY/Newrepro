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

import llm_gateway
from llm_logs import log_llm_interaction_ai_service

logger = logging.getLogger(__name__)

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
  "clarification_questions": ["q1", "q2", ...]
}"""

# ═══════════════════════════════════════════════════════════════════════════
# STAGE 2: TECHNOLOGY & ARCHITECTURE DESIGN (Focused Payload)
# ═══════════════════════════════════════════════════════════════════════════

STAGE_2_ARCHITECTURE_PROMPT = """# ROLE
You are an expert Software Architect designing technical architecture.

## CONTEXT
You will receive extracted requirements from Stage 1.

## TASK
Design the technical architecture:

### 1. Technology Stack Selection
Recommend complete stack with rationale:
- Frontend framework and UI library
- Backend framework and language
- Database (with version)
- Caching/Queue system
- Authentication method
- API documentation tool
- Containerization approach

Format as table:
| Layer | Technology | Version | Rationale |

### 2. Architecture Pattern
- Choose pattern: Monolith / Modular Monolith / Microservices
- Justify based on requirements
- Describe component interaction model

### 3. System Architecture Diagram
Create a COMPLETE Mermaid `flowchart TB` architecture based on the ACTUAL BRD requirements.

The diagram MUST include:
- client layer
- API layer
- auth/security
- business services
- data stores
- async/event systems
- integrations
- observability
- infrastructure

Show:
- write path
- read path
- async/background flow
- auth flow
- reporting path

## STRICT Mermaid Safety Rules
1. Every subgraph must have one matching end
2. All edges must be placed after final end
3. NEVER connect to subgraph IDs
4. Use only node-to-node edges
5. Quote all labels
6. Use ASCII characters only
7. Every edge node must exist
8. Use architecture JSON as source-of-truth

### 4. Architecture JSON
Provide structured architecture data:
{
  "nodes": [
    {"id": "node_id", "label": "Component Name", "layer": "frontend|backend|data|service", "type": "service|database|cache|ui"}
  ],
  "edges": [
    {"from": "source_id", "to": "target_id", "description": "interaction"}
  ]
}

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
[Use Stage 1 data]

## 0.2 Background Research
[Synthesize from Stage 2 tech stack rationale]

## 0.3 Technical Architecture Design
[Use Stage 2 architecture + Mermaid diagrams]

## 0.4 Implementation Specifications
### 0.4.1 Core Components
[Derive from Stage 2 architecture]

### 0.4.2 Data Models and Schemas
[Use Stage 3 ER diagram]

### 0.4.3 API Specifications
[Use Stage 3 API endpoints]

## 0.5 Repository Structure Planning
[Use Stage 4 file tree]

## 0.6 Scope Definition
[Derive from Stage 1 requirements]

## 0.7 Deliverable Mapping
[Use Stage 4 file creation plan and phases]

## 0.8 Risks & Gap Analysis
[Analyze based on all stages]

## 0.9 Clarification Questions
[Use Stage 1 questions]

## 0.10 Prerequisites & Credentials
[Use Stage 4 prerequisites. Group them logically by category (credentials, apis, infrastructure, databases, cloud, dependencies). List each with name, description, and priority.]

## 0.11 Execution Patterns
[Use Stage 4 implementation guidelines]

## 0.12 Go / No-Go Recommendation
**[GO / NO-GO / PROCEED WITH CAUTION]**
[Provide recommendation based on analysis]

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
    "project_type": "greenfield|brownfield|modernization"
  }},
  "questions": [...],
  "prerequisites": [...],
  "user_flow": "...",
  "implementation_structure": "...",
  "architecture": {{
    "nodes": [...],
    "edges": [...]
  }}
}}
```"""

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
        if job_id:
            try:
                from analysis_job_manager import get_job_manager
                job_manager = get_job_manager()
                job = job_manager.get_job(job_id)
                if job:
                    job.update_progress(progress, message)
            except Exception as e:
                logger.warning(f"Failed to update job progress: {e}")
    
    if not llm_gateway.check_api_key(api_key):
        error = "API key not configured. Please set AI_API_KEY in your environment."
        return {"status": "error", "error": error}
    
    try:
        update_job_progress(15, "Preparing document content...")
        
        # Prepare document content (truncate if too large for Stage 1)
        max_stage1_content = 8000
        stage1_content = document_content[:max_stage1_content]
        if len(document_content) > max_stage1_content:
            stage1_content += "\n\n[Document truncated for initial analysis - full context will be used in later stages]"
        
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
            timeout=180.0
        )
        
        stage1_data = _extract_json_from_response(stage1_result)
        logger.info(f"Stage 1 complete: Extracted {len(stage1_data.get('functional_requirements', []))} functional requirements")
        
        # ─────────────────────────────────────────────────────────────────
        # STAGE 2: Architecture Design
        # ─────────────────────────────────────────────────────────────────
        update_job_progress(35, "Stage 2: Designing architecture...")
        logger.info("=== STAGE 2: Architecture Design ===")
        stage2_messages = [
            {"role": "system", "content": STAGE_2_ARCHITECTURE_PROMPT},
            {"role": "user", "content": f"Design architecture for these requirements:\n\n{json.dumps(stage1_data, indent=2)}"}
        ]
        
        stage2_result = await llm_gateway.call_llm_and_extract(
            messages=stage2_messages,
            api_url=api_url,
            api_key=api_key,
            model=model,
            timeout=180.0
        )
        
        stage2_data = _extract_json_from_response(stage2_result)
        logger.info(f"Stage 2 complete: Architecture pattern = {stage2_data.get('architecture_pattern', 'N/A')}")
        
        # ─────────────────────────────────────────────────────────────────
        # STAGE 3: Data Models & API Design
        # ─────────────────────────────────────────────────────────────────
        update_job_progress(55, "Stage 3: Designing data models and APIs...")
        logger.info("=== STAGE 3: Data Models & API Design ===")
        stage3_context = {
            "requirements_summary": {
                "functional": stage1_data.get("functional_requirements", [])[:10],  # Top 10
                "non_functional": stage1_data.get("non_functional_requirements", [])
            },
            "architecture": {
                "pattern": stage2_data.get("architecture_pattern"),
                "tech_stack": stage2_data.get("tech_stack", [])[:5]  # Key technologies
            }
        }
        
        stage3_messages = [
            {"role": "system", "content": STAGE_3_DATA_API_PROMPT},
            {"role": "user", "content": f"Design data models and APIs for:\n\n{json.dumps(stage3_context, indent=2)}"}
        ]
        
        stage3_result = await llm_gateway.call_llm_and_extract(
            messages=stage3_messages,
            api_url=api_url,
            api_key=api_key,
            model=model,
            timeout=180.0
        )
        
        stage3_data = _extract_json_from_response(stage3_result)
        logger.info(f"Stage 3 complete: Designed {len(stage3_data.get('api_endpoints', []))} API endpoints")
        
        # ─────────────────────────────────────────────────────────────────
        # STAGE 4: Implementation Plan
        # ─────────────────────────────────────────────────────────────────
        update_job_progress(70, "Stage 4: Creating implementation plan...")
        logger.info("=== STAGE 4: Implementation Planning ===")
        stage4_context = {
            "product_name": stage1_data.get("product_name"),
            "requirements_count": len(stage1_data.get("functional_requirements", [])),
            "architecture_pattern": stage2_data.get("architecture_pattern"),
            "tech_stack_summary": [t.get("technology") for t in stage2_data.get("tech_stack", [])[:8]],
            "api_count": len(stage3_data.get("api_endpoints", []))
        }
        
        stage4_messages = [
            {"role": "system", "content": STAGE_4_IMPLEMENTATION_PROMPT},
            {"role": "user", "content": f"Create implementation plan for:\n\n{json.dumps(stage4_context, indent=2)}"}
        ]
        
        stage4_result = await llm_gateway.call_llm_and_extract(
            messages=stage4_messages,
            api_url=api_url,
            api_key=api_key,
            model=model,
            timeout=180.0
        )
        
        stage4_data = _extract_json_from_response(stage4_result)
        logger.info(f"Stage 4 complete: Created {len(stage4_data.get('file_creation_plan', []))} file specifications")
        
        # ─────────────────────────────────────────────────────────────────
        # STAGE 5: Final Synthesis
        # ─────────────────────────────────────────────────────────────────
        update_job_progress(85, "Stage 5: Synthesizing final report...")
        logger.info("=== STAGE 5: Final Report Synthesis ===")
        
        # Build a more compact synthesis context to avoid truncation issues
        synthesis_context = {
            "stage1_requirements": {
                "product_name": stage1_data.get("product_name"),
                "product_vision": stage1_data.get("product_vision"),
                "functional_requirements": stage1_data.get("functional_requirements", []),
                "non_functional_requirements": stage1_data.get("non_functional_requirements", []),
                "clarification_questions": stage1_data.get("clarification_questions", [])
            },
            "stage2_architecture": {
                "tech_stack": stage2_data.get("tech_stack", []),
                "architecture_pattern": stage2_data.get("architecture_pattern"),
                "architecture_justification": stage2_data.get("architecture_justification"),
                "mermaid_flowchart": stage2_data.get("mermaid_flowchart"),
                "architecture": stage2_data.get("architecture", {})
            },
            "stage3_data_api": {
                "mermaid_er_diagram": stage3_data.get("mermaid_er_diagram"),
                "validation_rules": stage3_data.get("validation_rules", []),
                "api_endpoints": stage3_data.get("api_endpoints", [])
            },
            "stage4_implementation": {
                "repository_structure": stage4_data.get("repository_structure"),
                "prerequisites": stage4_data.get("prerequisites", []),
                "implementation_phases": stage4_data.get("implementation_phases", []),
                "implementation_guidelines": stage4_data.get("implementation_guidelines", [])
            }
        }
        
        # Serialize context and check size
        context_json = json.dumps(synthesis_context, indent=2)
        logger.info(f"Stage 5 context size: {len(context_json)} characters")
        
        # If context is too large, summarize further
        if len(context_json) > 12000:
            logger.warning(f"Stage 5 context too large ({len(context_json)} chars), summarizing...")
            synthesis_context["stage1_requirements"]["functional_requirements"] = stage1_data.get("functional_requirements", [])[:15]
            synthesis_context["stage2_architecture"]["tech_stack"] = stage2_data.get("tech_stack", [])[:10]
            synthesis_context["stage3_data_api"]["api_endpoints"] = stage3_data.get("api_endpoints", [])[:20]
            context_json = json.dumps(synthesis_context, indent=2)
            logger.info(f"Stage 5 context reduced to: {len(context_json)} characters")
        
        stage5_messages = [
            {"role": "system", "content": STAGE_5_SYNTHESIS_PROMPT},
            {"role": "user", "content": f"Synthesize comprehensive BRD Analysis Report from:\n\n{context_json}"}
        ]
        
        try:
            stage5_result = await llm_gateway.call_llm_and_extract(
                messages=stage5_messages,
                api_url=api_url,
                api_key=api_key,
                model=model,
                timeout=240.0
            )
            
            if not stage5_result or len(stage5_result.strip()) == 0:
                raise ValueError("Stage 5 returned empty response from LLM")
            
            logger.info(f"Stage 5 complete: Generated report of {len(stage5_result)} characters")
            update_job_progress(95, "Finalizing analysis...")
            
            # Extract final JSON from the report
            final_json = _extract_json_from_response(stage5_result)
            
            if not final_json:
                logger.error("Failed to extract JSON from Stage 5 response")
                logger.error(f"Stage 5 response preview: {stage5_result[:500]}")
                raise ValueError("Failed to extract valid JSON from Stage 5 synthesis")
                
        except Exception as stage5_error:
            logger.error(f"Stage 5 failed: {type(stage5_error).__name__}: {str(stage5_error)}")
            # Create a fallback response using data from previous stages
            logger.warning("Creating fallback response from previous stages")
            stage5_result = _create_fallback_report(stage1_data, stage2_data, stage3_data, stage4_data)
            final_json = {
                "title": f"{stage1_data.get('product_name', 'Product')} - BRD Analysis",
                "metrics": {
                    "complexity": "Medium",
                    "timeline": "To be determined",
                    "deployment": stage2_data.get("architecture_pattern", "To be determined"),
                    "resources": "To be determined",
                    "project_type": "greenfield"
                },
                "questions": stage1_data.get("clarification_questions", []),
                "prerequisites": stage4_data.get("prerequisites", []),
                "architecture": stage2_data.get("architecture", {"nodes": [], "edges": []})
            }
        
        # Ensure architecture data is included
        if not final_json.get("architecture"):
            final_json["architecture"] = stage2_data.get("architecture", {"nodes": [], "edges": []})
        
        update_job_progress(100, "Analysis complete!")
        
        return {
            "status": "success",
            "analysis": stage5_result,
            "model": model or "chunked-multi-stage",
            "stages": {
                "stage1_requirements": stage1_data,
                "stage2_architecture": stage2_data,
                "stage3_data_api": stage3_data,
                "stage4_implementation": stage4_data
            }
        }
    
    except Exception as e:
        error_type = type(e).__name__
        error_msg = str(e) if str(e) else "Unknown error occurred"
        logger.error(f"Chunked analysis failed: {error_type}: {error_msg}", exc_info=True)
        return {
            "status": "error",
            "error": f"Analysis failed: {error_type}: {error_msg}"
        }


# ═══════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════

def _normalize_unicode_to_ascii(text: str) -> str:
    """
    Normalize problematic Unicode characters to ASCII equivalents.
    This fixes issues where LLMs return Unicode characters despite instructions.
    """
    replacements = {
        '\u2011': '-',  # Non-breaking hyphen
        '\u2013': '-',  # En dash
        '\u2014': '--', # Em dash
        '\u202f': ' ',  # Narrow no-break space
        '\u00a0': ' ',  # Non-breaking space
        '\u2265': '>=', # Greater than or equal
        '\u2264': '<=', # Less than or equal
        '\u2018': "'",  # Left single quote
        '\u2019': "'",  # Right single quote
        '\u201c': '"',  # Left double quote
        '\u201d': '"',  # Right double quote
        '\u2022': '-',  # Bullet point
        '\u2026': '...', # Ellipsis
    }
    
    for unicode_char, ascii_char in replacements.items():
        text = text.replace(unicode_char, ascii_char)
    
    return text


def _create_fallback_report(stage1_data: dict, stage2_data: dict, stage3_data: dict, stage4_data: dict) -> str:
    """
    Create a basic markdown report from stage data when Stage 5 synthesis fails.
    """
    report_parts = []
    
    # Header
    product_name = stage1_data.get("product_name", "Product")
    report_parts.append(f"# BRD Analysis Report: {product_name}\n")
    report_parts.append("*Note: This is a fallback report generated from stage data.*\n\n")
    
    # Product Understanding
    report_parts.append("## 0.1 Product Understanding\n")
    report_parts.append(f"**Product Name:** {product_name}\n\n")
    if stage1_data.get("product_vision"):
        report_parts.append(f"**Vision:** {stage1_data['product_vision']}\n\n")
    
    # Requirements
    report_parts.append("## 0.2 Functional Requirements\n")
    for req in stage1_data.get("functional_requirements", [])[:20]:
        report_parts.append(f"- {req}\n")
    report_parts.append("\n")
    
    # Architecture
    report_parts.append("## 0.3 Technical Architecture\n")
    report_parts.append(f"**Pattern:** {stage2_data.get('architecture_pattern', 'Not specified')}\n\n")
    
    # Tech Stack
    report_parts.append("### Technology Stack\n")
    for tech in stage2_data.get("tech_stack", [])[:10]:
        report_parts.append(f"- **{tech.get('layer')}:** {tech.get('technology')} {tech.get('version', '')}\n")
    report_parts.append("\n")
    
    # Prerequisites
    report_parts.append("## 0.4 Prerequisites\n")
    for prereq in stage4_data.get("prerequisites", [])[:15]:
        report_parts.append(f"- **{prereq.get('name')}** ({prereq.get('category')}): {prereq.get('description')}\n")
    report_parts.append("\n")
    
    # Questions
    report_parts.append("## 0.5 Clarification Questions\n")
    for q in stage1_data.get("clarification_questions", []):
        report_parts.append(f"- {q}\n")
    report_parts.append("\n")
    
    return "".join(report_parts)


def _extract_json_from_response(text: str) -> dict:
    """Extract JSON object from LLM response, handling markdown fences and think tags."""
    if not text or not isinstance(text, str):
        logger.warning("Empty or invalid text provided to _extract_json_from_response")
        return {}
    
    # Remove think tags
    text = re.sub(r"ქ.*?ქ", "", text, flags=re.DOTALL)
    
    # Normalize Unicode characters to ASCII before parsing
    text = _normalize_unicode_to_ascii(text)
    
    # Try to find JSON in markdown fence
    fenced_regex = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.IGNORECASE)
    for match in fenced_regex.finditer(text):
        candidate = match.group(1).strip()
        if candidate.startswith("{") and candidate.endswith("}"):
            try:
                return json.loads(candidate)
            except Exception as e:
                logger.warning(f"Failed to parse JSON from markdown fence: {e}")
                continue
    
    # Try to find trailing JSON object
    trimmed = text.strip()
    for i in range(len(trimmed) - 1, -1, -1):
        if trimmed[i] == "{":
            candidate = trimmed[i:].strip()
            try:
                return json.loads(candidate)
            except Exception as e:
                logger.warning(f"Failed to parse JSON from position {i}: {e}")
                continue
    
    logger.error("No valid JSON found in LLM response")
    return {}


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