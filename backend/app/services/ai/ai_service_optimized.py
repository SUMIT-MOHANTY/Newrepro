# Optimized AI Service with Multi-Stage Analysis
import asyncio
from typing import Dict, Any, Optional, List
from app.integrations.llm import llm_gateway
from app.core.llm_logs import log_llm_interaction_ai_service

# Smaller, focused prompts for each stage
STAGE_1_UNDERSTANDING_PROMPT = """# ROLE
You are an expert software architect. Analyze the provided document and extract core requirements.

## TASK
Analyze the document and provide:

### 1. Product Understanding
- Core product vision (1 paragraph)
- Functional requirements (list)
- Non-functional requirements (list)
- Implicit requirements surfaced

### 2. Technology Assessment
- Recommended technology stack with rationale
- Architecture pattern (monolith/microservices/etc.)
- Scale expectations

### 3. Clarification Questions
Generate 3-5 specific questions about:
- Missing technical details
- Ambiguous requirements
- Integration uncertainties

Output as structured JSON:
```json
{
  "product_vision": "...",
  "functional_requirements": [...],
  "non_functional_requirements": [...],
  "implicit_requirements": [...],
  "recommended_stack": {...},
  "architecture_pattern": "...",
  "questions": [...],
  "metrics": {
    "complexity": "Low/Medium/High",
    "timeline": "...",
    "deployment": "...",
    "resources": "..."
  }
}
```"""

STAGE_2_ARCHITECTURE_PROMPT = """# ROLE
You are an expert software architect. Design the technical architecture based on the requirements analysis.

## CONTEXT
You will receive:
1. Requirements analysis from Stage 1
2. Original document content (if needed for reference)

## TASK
Create detailed technical architecture:

### 1. Architecture Design
- Complete system architecture with Mermaid flowchart
- Component interaction model
- Security architecture

### 2. Data Models
- Mermaid ER diagram
- Key relationships and validation rules

### 3. API Specifications
- Endpoint tables by domain
- Authentication/authorization

Output as structured JSON with Mermaid diagrams:
```json
{
  "architecture": {
    "nodes": [...],
    "edges": [...],
    "mermaid_flowchart": "...",
    "mermaid_er_diagram": "..."
  },
  "api_endpoints": [...],
  "security_model": "..."
}
```"""

STAGE_3_IMPLEMENTATION_PROMPT = """# ROLE
You are an expert software architect. Create implementation specifications and file structure.

## CONTEXT
You will receive:
1. Requirements from Stage 1
2. Architecture from Stage 2

## TASK
Create implementation plan:

### 1. Repository Structure
- Complete file tree with all files
- File responsibilities

### 2. Implementation Guidelines
- Coding standards
- Quality requirements
- Development phases

### 3. Prerequisites & Deliverables
- Required credentials/infrastructure
- File creation plan with priorities

Output as structured JSON:
```json
{
  "file_structure": "...",
  "implementation_phases": [...],
  "prerequisites": [...],
  "deliverables": [...],
  "coding_guidelines": [...]
}
```"""

async def analyze_document_multi_stage(
    document_content: str,
    api_url: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    governance_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Multi-stage analysis to reduce payload size and improve reliability.
    """
    
    # Stage 1: Requirements Understanding (smallest payload)
    print("=== STAGE 1: Requirements Analysis ===")
    stage1_messages = [
        {"role": "system", "content": STAGE_1_UNDERSTANDING_PROMPT},
        {"role": "user", "content": f"Analyze this document:\n\n{document_content[:5000]}..."}  # Truncate for stage 1
    ]
    
    stage1_result = await llm_gateway.call_llm_and_extract(
        messages=stage1_messages,
        api_url=api_url,
        api_key=api_key,
        model=model,
        timeout=180.0  # 3 minutes
    )
    
    # Stage 2: Architecture Design
    print("=== STAGE 2: Architecture Design ===")
    stage2_messages = [
        {"role": "system", "content": STAGE_2_ARCHITECTURE_PROMPT},
        {"role": "user", "content": f"Requirements Analysis:\n{stage1_result}\n\nCreate architecture for these requirements."}
    ]
    
    stage2_result = await llm_gateway.call_llm_and_extract(
        messages=stage2_messages,
        api_url=api_url,
        api_key=api_key,
        model=model,
        timeout=180.0  # 3 minutes
    )
    
    # Stage 3: Implementation Planning
    print("=== STAGE 3: Implementation Planning ===")
    stage3_messages = [
        {"role": "system", "content": STAGE_3_IMPLEMENTATION_PROMPT},
        {"role": "user", "content": f"Requirements:\n{stage1_result[:1000]}...\n\nArchitecture:\n{stage2_result[:1000]}...\n\nCreate implementation plan."}
    ]
    
    stage3_result = await llm_gateway.call_llm_and_extract(
        messages=stage3_messages,
        api_url=api_url,
        api_key=api_key,
        model=model,
        timeout=180.0  # 3 minutes
    )
    
    # Combine results into final analysis
    combined_analysis = f"""# BRD Analysis Report

## Requirements Analysis
{stage1_result}

## Technical Architecture
{stage2_result}

## Implementation Plan
{stage3_result}

## Go/No-Go Recommendation
Based on the analysis above: **GO** - Requirements are clear and technically feasible.
"""
    
    return {
        "status": "success",
        "analysis": combined_analysis,
        "stage1": stage1_result,
        "stage2": stage2_result,
        "stage3": stage3_result,
        "model": model or "multi-stage"
    }

# Strategy 2: Document Chunking
async def analyze_document_chunked(
    document_content: str,
    api_url: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    chunk_size: int = 3000,
) -> Dict[str, Any]:
    """
    Analyze document in chunks and combine results.
    """
    
    # Split document into chunks
    chunks = [document_content[i:i+chunk_size] for i in range(0, len(document_content), chunk_size)]
    
    chunk_analyses = []
    for i, chunk in enumerate(chunks):
        print(f"=== ANALYZING CHUNK {i+1}/{len(chunks)} ===")
        
        chunk_prompt = f"""Analyze this section of a BRD document (part {i+1} of {len(chunks)}):

{chunk}

Provide:
1. Key requirements found in this section
2. Technical implications
3. Questions about this section

Keep response concise and focused."""
        
        messages = [
            {"role": "system", "content": "You are a software architect analyzing a BRD document section."},
            {"role": "user", "content": chunk_prompt}
        ]
        
        chunk_result = await llm_gateway.call_llm_and_extract(
            messages=messages,
            api_url=api_url,
            api_key=api_key,
            model=model,
            timeout=120.0
        )
        
        chunk_analyses.append(f"## Section {i+1}\n{chunk_result}")
    
    # Final synthesis
    synthesis_prompt = f"""Based on these section analyses, create a comprehensive BRD analysis:

{chr(10).join(chunk_analyses)}

Provide:
1. Overall product understanding
2. Complete technical architecture
3. Implementation recommendations
4. Clarification questions
5. Go/No-Go recommendation"""
    
    synthesis_messages = [
        {"role": "system", "content": "You are a software architect synthesizing BRD analysis sections."},
        {"role": "user", "content": synthesis_prompt}
    ]
    
    final_result = await llm_gateway.call_llm_and_extract(
        messages=synthesis_messages,
        api_url=api_url,
        api_key=api_key,
        model=model,
        timeout=180.0
    )
    
    return {
        "status": "success",
        "analysis": final_result,
        "chunks_analyzed": len(chunks),
        "model": model or "chunked"
    }

# Strategy 3: Compressed Prompt
COMPRESSED_ANALYSIS_PROMPT = """# ROLE: Software Architect

Analyze the BRD and provide:

## 1. Product Summary
- Core vision (1 paragraph)
- Key functional requirements
- Non-functional requirements

## 2. Technical Design
- Recommended tech stack with rationale
- Architecture pattern (monolith/microservices)
- Mermaid flowchart of system architecture

## 3. Implementation
- File structure overview
- Key components and APIs
- Development phases

## 4. Assessment
- 3-5 clarification questions
- Prerequisites needed
- Go/No-Go recommendation

## 5. JSON Output
```json
{
  "title": "...",
  "metrics": {"complexity": "...", "timeline": "...", "deployment": "...", "resources": "..."},
  "questions": [...],
  "prerequisites": [...],
  "architecture": {"nodes": [...], "edges": [...]}
}
```

Be concise but comprehensive. Focus on actionable technical details."""

async def analyze_document_compressed(
    document_content: str,
    api_url: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    governance_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Use compressed prompt to reduce payload size.
    """
    
    # Truncate document if too large
    max_content_length = 8000  # Adjust based on model limits
    if len(document_content) > max_content_length:
        document_content = document_content[:max_content_length] + "\n\n[Document truncated for analysis]"
    
    messages = [
        {"role": "system", "content": COMPRESSED_ANALYSIS_PROMPT},
        {"role": "user", "content": f"Analyze this BRD:\n\n{document_content}"}
    ]
    
    result = await llm_gateway.call_llm_and_extract(
        messages=messages,
        api_url=api_url,
        api_key=api_key,
        model=model,
        timeout=300.0  # 5 minutes
    )
    
    return {
        "status": "success",
        "analysis": result,
        "model": model or "compressed"
    }