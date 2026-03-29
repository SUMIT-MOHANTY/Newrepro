import os
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE_DIR, "logs")

os.makedirs(LOG_DIR, exist_ok=True)

LOG_FILE = os.path.join(LOG_DIR, "agent_service.txt")
LOG_FILE_2 = os.path.join(LOG_DIR, "ai_service.txt")
SELF_REVIEW_LOG = os.path.join(LOG_DIR, "self_review.txt")
CODE_GENERATION_LOG = os.path.join(LOG_DIR, "code_generation.txt")

def log_llm_interaction(messages, response, context=None):
    """
    Log LLM interactions with optional context about the call.
    
    Args:
        messages: List of message dicts sent to the AI
        response: Response from the AI
        context: Optional dict with metadata about the call:
            - call_type: str (e.g., 'code_generation', 'self_review', 'fix_generation')
            - agent_id: str
            - task_id: str
            - iteration: int
            - phase: str (e.g., 'bootstrap', 'implementation', 'fix')
    """
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write("\n" + "="*80 + "\n")
            f.write(f"Timestamp: {datetime.utcnow().isoformat()}\n")
            
            # Add context information if provided
            if context:
                f.write(f"\n--- CALL CONTEXT ---\n")
                for key, value in context.items():
                    f.write(f"{key}: {value}\n")
                f.write("\n")
            
            f.write("\n--- SYSTEM / INPUT MESSAGES ---\n")
            for msg in messages:
                role = msg.get("role", "unknown")
                content = msg.get("content", "")
                f.write(f"[{role.upper()}]:\n{content}\n\n")
            
            f.write("\n--- AI RESPONSE ---\n")
            f.write(response if isinstance(response, str) else str(response))
            f.write("\n" + "="*80 + "\n")
        
        # Also log to specific category files based on context
        if context and context.get('call_type'):
            call_type = context['call_type']
            if call_type == 'self_review':
                _log_to_file(SELF_REVIEW_LOG, messages, response, context)
            elif call_type in ['code_generation', 'bootstrap']:
                _log_to_file(CODE_GENERATION_LOG, messages, response, context)
                
    except Exception as e:
        print(f"[LOG ERROR] Failed to write LLM log: {e}")

def _log_to_file(filepath, messages, response, context):
    """Helper to log to specific category files."""
    try:
        with open(filepath, "a", encoding="utf-8") as f:
            f.write("\n" + "="*80 + "\n")
            f.write(f"Timestamp: {datetime.utcnow().isoformat()}\n")
            
            if context:
                f.write(f"\n--- CALL CONTEXT ---\n")
                for key, value in context.items():
                    f.write(f"{key}: {value}\n")
                f.write("\n")
            
            # Log system prompt length and key sections
            f.write("\n--- PROMPT STATISTICS ---\n")
            for msg in messages:
                role = msg.get("role", "unknown")
                content = msg.get("content", "")
                f.write(f"{role.upper()} prompt length: {len(content)} characters\n")
                
                # Extract key sections from system prompts
                if role == "system":
                    if "BULLETPROOF" in content or "CODE_QUALITY" in content:
                        f.write("  Contains: CODE_QUALITY_RULES\n")
                    if "BOOTSTRAP" in content:
                        f.write("  Contains: BOOTSTRAP_RULES\n")
                    if "CRITICAL" in content:
                        critical_count = content.count("CRITICAL")
                        f.write(f"  Contains: {critical_count} CRITICAL sections\n")
            
            f.write("\n--- MESSAGES ---\n")
            for msg in messages:
                role = msg.get("role", "unknown")
                content = msg.get("content", "")
                f.write(f"[{role.upper()}]:\n{content}\n\n")
            
            f.write("\n--- AI RESPONSE ---\n")
            f.write(response if isinstance(response, str) else str(response))
            
            # Parse response for important markers
            if isinstance(response, str):
                f.write(f"\n\n--- RESPONSE ANALYSIS ---\n")
                f.write(f"Response length: {len(response)} characters\n")
                f.write(f"Response line count: {len(response.splitlines())} lines\n")
                
                # Check for script markers
                if "#!/bin/bash" in response or "#!/usr/bin/env bash" in response:
                    f.write("Contains: Bash script\n")
                if "cat <<" in response:
                    heredoc_count = response.count("cat <<")
                    f.write(f"Contains: {heredoc_count} heredoc blocks\n")
                if "mkdir -p" in response:
                    mkdir_count = response.count("mkdir -p")
                    f.write(f"Contains: {mkdir_count} directory creations\n")
                if "touch " in response:
                    touch_count = response.count("touch ")
                    f.write(f"Contains: {touch_count} touch commands\n")
            
            f.write("\n" + "="*80 + "\n")
    except Exception as e:
        print(f"[LOG ERROR] Failed to write to {filepath}: {e}")

def log_llm_interaction_ai_service(messages, response, context=None):
    """
    Log AI service interactions (for architect/master agent).
    
    Args:
        messages: List of message dicts
        response: AI response
        context: Optional metadata dict
    """
    try:
        with open(LOG_FILE_2, "a", encoding="utf-8") as f:
            f.write("\n" + "="*80 + "\n")
            f.write(f"Timestamp: {datetime.utcnow().isoformat()}\n")
            
            if context:
                f.write(f"\n--- CALL CONTEXT ---\n")
                for key, value in context.items():
                    f.write(f"{key}: {value}\n")
                f.write("\n")
            
            f.write("\n--- SYSTEM / INPUT MESSAGES ---\n")
            for msg in messages:
                role = msg.get("role", "unknown")
                content = msg.get("content", "")
                f.write(f"[{role.upper()}]:\n{content}\n\n")
            
            f.write("\n--- AI RESPONSE ---\n")
            f.write(response if isinstance(response, str) else str(response))
            f.write("\n" + "="*80 + "\n")
    except Exception as e:
        print(f"[LOG ERROR] Failed to write AI service LLM log: {e}")

def log_self_review_failure(check_number, check_name, iteration, stdout, stderr, exit_code, agent_id=None, task_id=None):
    """
    Log detailed information about self-review failures.
    
    Args:
        check_number: Which check failed (1-5)
        check_name: Name of the check
        iteration: Which iteration of the check
        stdout: Standard output from the check
        stderr: Standard error from the check
        exit_code: Exit code from the check
        agent_id: Optional agent ID
        task_id: Optional task ID
    """
    try:
        with open(SELF_REVIEW_LOG, "a", encoding="utf-8") as f:
            f.write("\n" + "="*80 + "\n")
            f.write(f"SELF-REVIEW FAILURE - {datetime.utcnow().isoformat()}\n")
            f.write("="*80 + "\n")
            
            if agent_id:
                f.write(f"Agent ID: {agent_id}\n")
            if task_id:
                f.write(f"Task ID: {task_id}\n")
            
            f.write(f"Check Number: {check_number}\n")
            f.write(f"Check Name: {check_name}\n")
            f.write(f"Iteration: {iteration}\n")
            f.write(f"Exit Code: {exit_code}\n")
            f.write("\n")
            
            f.write("--- STDOUT ---\n")
            f.write(stdout if stdout else "(empty)\n")
            f.write("\n")
            
            f.write("--- STDERR ---\n")
            f.write(stderr if stderr else "(empty)\n")
            f.write("\n")
            
            # Try to extract specific error patterns
            combined = (stdout or "") + "\n" + (stderr or "")
            
            f.write("--- ERROR ANALYSIS ---\n")
            if "syntax error" in combined.lower():
                f.write("ERROR TYPE: Syntax Error\n")
            if "import" in combined.lower() and "error" in combined.lower():
                f.write("ERROR TYPE: Import Error\n")
            if "not found" in combined.lower():
                f.write("ERROR TYPE: File/Command Not Found\n")
            if "permission denied" in combined.lower():
                f.write("ERROR TYPE: Permission Error\n")
            
            f.write("\n" + "="*80 + "\n")
    except Exception as e:
        print(f"[LOG ERROR] Failed to write self-review failure log: {e}")

def log_code_generation_success(agent_id, task_id, script_length, files_created):
    """Log successful code generation."""
    try:
        with open(CODE_GENERATION_LOG, "a", encoding="utf-8") as f:
            f.write(f"\n[SUCCESS] {datetime.utcnow().isoformat()} - Agent: {agent_id}, Task: {task_id}\n")
            f.write(f"  Script length: {script_length} characters\n")
            f.write(f"  Files created: {files_created}\n")
    except Exception as e:
        print(f"[LOG ERROR] Failed to write success log: {e}")