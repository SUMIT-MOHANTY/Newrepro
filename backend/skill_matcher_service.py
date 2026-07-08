"""
Skill Matcher Service - Intelligently matches skills.md files to tasks
The master agent uses this to determine which skills are relevant for each task
"""
import logging
from typing import List, Dict, Any, Optional
import re

logger = logging.getLogger(__name__)


def extract_skill_keywords(skill_content: str) -> List[str]:
    """
    Extract keywords from a skill.md file content.
    Looks for headers, code blocks, and important terms.
    """
    keywords = set()
    
    # Extract markdown headers (# Header, ## Header, etc.)
    headers = re.findall(r'^#{1,6}\s+(.+)$', skill_content, re.MULTILINE)
    for header in headers:
        # Split header into words and add them
        words = re.findall(r'\b[a-zA-Z]{3,}\b', header.lower())
        keywords.update(words)
    
    # Extract code language identifiers (```python, ```javascript, etc.)
    code_langs = re.findall(r'```(\w+)', skill_content)
    keywords.update(lang.lower() for lang in code_langs)
    
    # Extract common technical terms (case-insensitive)
    technical_terms = re.findall(
        r'\b(api|rest|graphql|database|sql|nosql|auth|jwt|oauth|'
        r'react|vue|angular|python|javascript|typescript|java|go|rust|'
        r'docker|kubernetes|aws|azure|gcp|ci|cd|test|unit|integration|'
        r'frontend|backend|fullstack|microservice|monolith|'
        r'security|encryption|validation|error|logging|monitoring)\b',
        skill_content,
        re.IGNORECASE
    )
    keywords.update(term.lower() for term in technical_terms)
    
    # Extract file extensions mentioned
    file_exts = re.findall(r'\.(\w{2,4})\b', skill_content)
    keywords.update(ext.lower() for ext in file_exts if len(ext) <= 4)
    
    return list(keywords)


def calculate_task_skill_relevance(
    task: Dict[str, Any],
    skill_name: str,
    skill_content: str,
    skill_keywords: List[str]
) -> float:
    """
    Calculate relevance score (0.0 to 1.0) between a task and a skill.
    Higher score means more relevant.
    """
    score = 0.0
    max_score = 0.0
    
    # Get task text fields
    task_title = str(task.get('title') or task.get('taskName') or '').lower()
    task_description = str(task.get('description') or '').lower()
    task_checklist = str(task.get('checklist') or '').lower()
    task_domain = str(task.get('domain') or '').lower()
    task_phase = str(task.get('phase') or task.get('task_phase') or '').lower()
    
    # Combine all task text
    task_text = f"{task_title} {task_description} {task_checklist} {task_domain} {task_phase}"
    
    # 1. Check if skill name appears in task (high weight)
    max_score += 30
    skill_name_clean = skill_name.replace('.md', '').replace('-', ' ').replace('_', ' ').lower()
    if skill_name_clean in task_text:
        score += 30
    elif any(word in task_text for word in skill_name_clean.split()):
        score += 15
    
    # 2. Check keyword matches (medium weight)
    max_score += 50
    keyword_matches = sum(1 for keyword in skill_keywords if keyword in task_text)
    if skill_keywords:
        keyword_score = (keyword_matches / len(skill_keywords)) * 50
        score += keyword_score
    
    # 3. Check file hints (if available)
    max_score += 20
    file_hints = task.get('file_hints') or []
    if isinstance(file_hints, list) and file_hints:
        file_hint_text = ' '.join(str(hint).lower() for hint in file_hints)
        file_matches = sum(1 for keyword in skill_keywords if keyword in file_hint_text)
        if skill_keywords:
            file_score = (file_matches / len(skill_keywords)) * 20
            score += file_score
    
    # Normalize score to 0.0-1.0 range
    return score / max_score if max_score > 0 else 0.0


def match_skills_to_task(
    task: Dict[str, Any],
    available_skills: List[Dict[str, Any]],
    relevance_threshold: float = 0.3
) -> List[Dict[str, Any]]:
    """
    Match relevant skills to a task based on content analysis.
    
    Args:
        task: Task dictionary with title, description, checklist, etc.
        available_skills: List of skill dictionaries with {name, content, uploadedAt}
        relevance_threshold: Minimum relevance score (0.0-1.0) to include a skill
    
    Returns:
        List of relevant skills sorted by relevance score (highest first)
    """
    if not available_skills:
        return []
    
    skill_scores = []
    
    for skill in available_skills:
        skill_name = skill.get('name', '')
        skill_content = skill.get('content', '')
        
        if not skill_name or not skill_content:
            continue
        
        # Extract keywords from skill content (cache this in production)
        keywords = extract_skill_keywords(skill_content)
        
        # Calculate relevance score
        relevance = calculate_task_skill_relevance(
            task=task,
            skill_name=skill_name,
            skill_content=skill_content,
            skill_keywords=keywords
        )
        
        if relevance >= relevance_threshold:
            skill_scores.append({
                'skill': skill,
                'relevance': relevance,
                'matched_keywords': keywords[:10]  # Top 10 keywords for debugging
            })
    
    # Sort by relevance (highest first)
    skill_scores.sort(key=lambda x: x['relevance'], reverse=True)
    
    return skill_scores


def build_skill_context_block(matched_skills: List[Dict[str, Any]]) -> str:
    """
    Build a formatted context block from matched skills for agent prompts.
    
    Args:
        matched_skills: List of matched skills with relevance scores
    
    Returns:
        Formatted string to inject into agent prompts
    """
    if not matched_skills:
        return ""
    
    lines = ["# RELEVANT SKILLS FOR THIS TASK\n"]
    lines.append("The following specialized skills are relevant to this task. Follow these guidelines:\n")
    
    for idx, match in enumerate(matched_skills, 1):
        skill = match['skill']
        relevance = match['relevance']
        skill_name = skill.get('name', f'Skill {idx}')
        skill_content = skill.get('content', '')
        
        lines.append(f"\n## Skill {idx}: {skill_name} (Relevance: {relevance:.0%})\n")
        lines.append(f"{skill_content}\n")
        lines.append("---\n")
    
    return "\n".join(lines)


def get_claude_md_context(claude_md_files: List[Dict[str, Any]]) -> str:
    """
    Build context block from claude.md files (always loaded for all agents).
    
    Args:
        claude_md_files: List of claude.md file dictionaries
    
    Returns:
        Formatted string to inject into agent prompts
    """
    if not claude_md_files:
        return ""
    
    lines = ["# PROJECT CONTEXT (Claude.md Files)\n"]
    lines.append("The following files contain mandatory project context and guidelines:\n")
    
    for idx, file in enumerate(claude_md_files, 1):
        file_name = file.get('name', f'File {idx}')
        file_content = file.get('content', '')
        
        lines.append(f"\n## {file_name}\n")
        lines.append(f"{file_content}\n")
        lines.append("---\n")
    
    return "\n".join(lines)


async def inject_context_for_task(
    task: Dict[str, Any],
    project_token: str,
    db_session: Any
) -> Dict[str, str]:
    """
    Main function to inject both claude.md and relevant skills.md into task context.
    
    Args:
        task: Task dictionary
        project_token: Project identifier
        db_session: Database session
    
    Returns:
        Dictionary with 'claude_context' and 'skills_context' keys
    """
    try:
        from database import SessionLocal
        import models
        
        # Get governance response for this project
        governance = db_session.query(models.GovernanceResponse).filter(
            models.GovernanceResponse.project_token == project_token
        ).first()
        
        if not governance:
            logger.warning(f"No governance found for project {project_token}")
            return {'claude_context': '', 'skills_context': ''}
        
        # Get claude.md files (always loaded)
        claude_md_files = governance.claude_md_files or []
        claude_context = get_claude_md_context(claude_md_files)
        
        # Get skills.md files and match to task
        skills_md_files = governance.skills_md_files or []
        matched_skills = match_skills_to_task(
            task=task,
            available_skills=skills_md_files,
            relevance_threshold=0.3  # 30% relevance threshold
        )
        
        skills_context = build_skill_context_block(matched_skills)
        
        if matched_skills:
            logger.info(
                f"Task '{task.get('title', 'Unknown')}': "
                f"Matched {len(matched_skills)} relevant skills from {len(skills_md_files)} available"
            )
        
        return {
            'claude_context': claude_context,
            'skills_context': skills_context
        }
    
    except Exception as e:
        logger.error(f"Error injecting context for task: {e}", exc_info=True)
        return {'claude_context': '', 'skills_context': ''}
