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

def log_ai_tracker(messages, response_data):
    """
    Clearly tracks what was sent to the AI (including system prompt)
    and what was received in response, with token counts in a txt file.
    Includes comprehensive call-stack backtrace to understand exactly
    where and why the AI call was made.
    """
    import json
    import inspect
    TRACKER_FILE = os.path.join(LOG_DIR, "ai_calls_tracker.txt")
    try:
        # Determine caller information dynamically
        caller_file = "Unknown File"
        caller_func = "Unknown Function"
        caller_line = 0
        calling_code = "Unknown Code Line"
        why_called = "Generic AI Call"
        
        # Analyze frame stack
        stack = inspect.stack()
        for idx, frame_info in enumerate(stack):
            filename = frame_info.filename
            function = frame_info.function
            lineno = frame_info.lineno
            
            # Skip logging files and general wrappers to find the real business logic caller
            if any(term in filename.lower() for term in ["llm_logs.py", "llm_gateway.py", "inspect"]):
                continue
                
            caller_file = os.path.basename(filename)
            caller_func = function
            caller_line = lineno
            if frame_info.code_context:
                calling_code = frame_info.code_context[0].strip()
                
            # Get function docstring if possible to explain "why"
            try:
                frame = frame_info.frame
                func_obj = frame.f_globals.get(function)
                if func_obj and func_obj.__doc__:
                    why_called = func_obj.__doc__.strip().split('\n')[0]
                else:
                    # Provide intuitive explanations based on common functions
                    func_lower = function.lower()
                    if "bootstrap" in func_lower:
                        why_called = "Initializing project structure and initial setup scaffold (Bootstrap)"
                    elif "brd" in func_lower:
                        why_called = "Analyzing Business Requirements Document (BRD) to extract specs"
                    elif "plan" in func_lower or "task" in func_lower:
                        why_called = "Planning features, breaking down tasks, or managing task schedules"
                    elif "review" in func_lower or "check" in func_lower:
                        why_called = "Running agent self-review / code quality checks to auto-heal errors"
                    elif "fix" in func_lower or "heal" in func_lower:
                        why_called = "Generating fixes or self-healing codebase/lint errors"
                    else:
                        why_called = f"Executing standard business logic in {function}()"
            except Exception:
                pass
            break

        content_text = ""
        model_name = "Unknown Model"
        usage = {"input_tokens": 0, "output_tokens": 0}
        
        if isinstance(response_data, dict):
            # Try extracting content
            # Try importing dynamically to avoid circular import issues
            try:
                from llm_gateway import extract_content_from_response
                content_text = extract_content_from_response(response_data)
            except Exception:
                # Fallback if import fails
                content_text = response_data.get("response") or response_data.get("text") or str(response_data)
            
            # Model name
            model_name = response_data.get("model", "Unknown Model")
            
            # Token usage
            raw_usage = response_data.get("usage") or {}
            if "prompt_tokens" in raw_usage:
                usage["input_tokens"] = raw_usage.get("prompt_tokens", 0)
                usage["output_tokens"] = raw_usage.get("completion_tokens", 0)
            elif "input_tokens" in raw_usage:
                usage["input_tokens"] = raw_usage.get("input_tokens", 0)
                usage["output_tokens"] = raw_usage.get("output_tokens", 0)
                if "cache_creation_input_tokens" in raw_usage:
                    usage["cache_creation_input_tokens"] = raw_usage["cache_creation_input_tokens"]
                if "cache_read_input_tokens" in raw_usage:
                    usage["cache_read_input_tokens"] = raw_usage["cache_read_input_tokens"]
            else:
                # If usage is not present, estimate it based on character length
                total_input_chars = sum(len(str(m.get("content", ""))) for m in messages)
                usage["input_tokens"] = total_input_chars // 4
                usage["output_tokens"] = len(str(content_text)) // 4
        else:
            content_text = str(response_data)
            total_input_chars = sum(len(str(m.get("content", ""))) for m in messages)
            usage["input_tokens"] = total_input_chars // 4
            usage["output_tokens"] = len(content_text) // 4

        # Construct the sample JSON format for AI response tracking
        formatted_response_json = {
            "content": [
                {
                    "text": content_text,
                    "type": "text"
                }
            ],
            "id": response_data.get("id") if isinstance(response_data, dict) else "unknown_msg_id",
            "model": model_name,
            "role": "assistant",
            "stop_reason": response_data.get("stop_reason") if isinstance(response_data, dict) else "end_turn",
            "stop_sequence": response_data.get("stop_sequence") if isinstance(response_data, dict) else None,
            "type": "message",
            "usage": {
                "cache_creation_input_tokens": usage.get("cache_creation_input_tokens", 0),
                "cache_read_input_tokens": usage.get("cache_read_input_tokens", 0),
                "input_tokens": usage.get("input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0)
            }
        }

        with open(TRACKER_FILE, "a", encoding="utf-8") as f:
            f.write("\n" + "="*80 + "\n")
            f.write(f"TRACKED AI CALL - {datetime.utcnow().isoformat()}\n")
            f.write("="*80 + "\n")
            
            # Write caller information and explanation of why the call was made
            f.write("\n[SOURCE CODE & CALL ORIGIN DETAILS]\n")
            f.write(f"File Name:     {caller_file}\n")
            f.write(f"Function Name: {caller_func}()\n")
            f.write(f"Line Number:   {caller_line}\n")
            f.write(f"Triggering Code: {calling_code}\n")
            f.write(f"Call Purpose:  {why_called}\n")
            
            # Write System Prompt and User Prompt
            f.write("\n[INPUT / PROMPTS SENT TO AI]\n")
            for msg in messages:
                role = msg.get("role", "unknown").upper()
                content = msg.get("content", "")
                f.write(f"--- {role} ---\n{content}\n\n")
            
            f.write("\n[AI RESPONSE METADATA & RAW USAGE]\n")
            f.write(json.dumps(formatted_response_json, indent=4))
            f.write("\n\n")
            
            # Write unescaped readable text content for easy reading
            f.write("#" * 80 + "\n")
            f.write("# [READABLE AI TEXT CONTENT - response.content[0].text]\n")
            f.write("#" * 80 + "\n\n")
            f.write(content_text if content_text else "(No text content generated)")
            f.write("\n\n" + "="*80 + "\n")
            
    except Exception as e:
        print(f"[TRACKER ERROR] Failed to write AI tracker log: {e}")