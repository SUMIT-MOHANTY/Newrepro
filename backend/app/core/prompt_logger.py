"""
Prompt Logger - Logs exact prompts and data sent to agents

This module logs all AI prompts to the agent's execution log so you can see
exactly what context and instructions each agent receives.
"""
import logging
from typing import Dict, Any, List
from datetime import datetime

logger = logging.getLogger(__name__)


def log_prompt_to_agent(
    agent_id: str,
    agent_output_log: List[Dict[str, Any]],
    prompt_type: str,
    system_prompt: str,
    user_prompt: str,
    context_summary: Dict[str, Any] = None
):
    """
    Log the exact prompt being sent to an agent
    
    Args:
        agent_id: The agent receiving the prompt
        agent_output_log: The agent's output log list
        prompt_type: Type of prompt (e.g., "CODE_GENERATION", "FIX_GENERATION", "SELF_REVIEW")
        system_prompt: The system prompt
        user_prompt: The user prompt
        context_summary: Summary of context provided (lengths, sources, etc.)
    """
    now = datetime.utcnow().isoformat()
    
    # Create a summary of what's being sent
    summary_parts = [
        f"📝 {prompt_type} PROMPT",
        f"",
        f"System Prompt Length: {len(system_prompt)} chars",
        f"User Prompt Length: {len(user_prompt)} chars",
    ]
    
    if context_summary:
        summary_parts.append("")
        summary_parts.append("Context Provided:")
        for key, value in context_summary.items():
            summary_parts.append(f"  - {key}: {value}")
    
    summary_parts.extend([
        "",
        "=" * 80,
        "SYSTEM PROMPT:",
        "=" * 80,
        system_prompt[:2000] + ("..." if len(system_prompt) > 2000 else ""),
        "",
        "=" * 80,
        "USER PROMPT:",
        "=" * 80,
        user_prompt[:3000] + ("..." if len(user_prompt) > 3000 else ""),
        "",
        "=" * 80,
    ])
    
    log_entry = {
        "time": now,
        "type": "prompt_log",
        "prompt_type": prompt_type,
        "message": "\n".join(summary_parts)
    }
    
    agent_output_log.append(log_entry)
    
    logger.info(f"[{agent_id}] Logged {prompt_type} prompt ({len(system_prompt) + len(user_prompt)} total chars)")


def extract_context_summary(
    tech_spec: str = "",
    workspace_tree: str = "",
    live_repo_tree: str = "",
    code_context: str = "",
    peer_context: str = "",
    project_root: str = ""
) -> Dict[str, Any]:
    """Extract a summary of what context is being provided"""
    summary = {}
    
    if project_root:
        summary["Project Root"] = project_root
    
    if tech_spec:
        summary["Tech Spec"] = f"{len(tech_spec)} chars"
    
    if workspace_tree:
        summary["Canonical Tree"] = f"{len(workspace_tree)} chars, {workspace_tree.count(chr(10))} lines"
    
    if live_repo_tree:
        summary["Live Repo Tree"] = f"{len(live_repo_tree)} chars, {live_repo_tree.count(chr(10))} lines"
    
    if code_context:
        summary["Knowledge Graph Context"] = f"{len(code_context)} chars"
    
    if peer_context:
        summary["Peer Agent Context"] = f"{len(peer_context)} chars"
    
    return summary


def log_ai_response(
    agent_id: str,
    agent_output_log: List[Dict[str, Any]],
    response_type: str,
    response_content: str,
    metadata: Dict[str, Any] = None
):
    """Log the AI's response"""
    now = datetime.utcnow().isoformat()
    
    summary_parts = [
        f"🤖 AI RESPONSE ({response_type})",
        f"",
        f"Response Length: {len(response_content)} chars",
    ]
    
    if metadata:
        summary_parts.append("")
        summary_parts.append("Metadata:")
        for key, value in metadata.items():
            summary_parts.append(f"  - {key}: {value}")
    
    summary_parts.extend([
        "",
        "=" * 80,
        "RESPONSE:",
        "=" * 80,
        response_content[:2000] + ("..." if len(response_content) > 2000 else ""),
        "",
        "=" * 80,
    ])
    
    log_entry = {
        "time": now,
        "type": "ai_response_log",
        "response_type": response_type,
        "message": "\n".join(summary_parts)
    }
    
    agent_output_log.append(log_entry)
    
    logger.info(f"[{agent_id}] Logged AI response ({len(response_content)} chars)")
