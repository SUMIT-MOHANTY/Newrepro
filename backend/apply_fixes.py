"""
Apply two fixes:
1. Self-review non-blocking (agent_service.py)
2. Controlled Executor container matching (agent_controlled_executor.py)
"""
import re

# ══════════════════════════════════════════════════════════════════
# FIX 1: Self-review non-blocking
# ══════════════════════════════════════════════════════════════════
with open("agent_service.py", "r", encoding="utf-8") as f:
    content = f.read()

# Find the start of the self-review block
start_marker = 'agent["output_log"].append({\n                    "time": datetime.utcnow().isoformat(),\n                    "type": "info",\n                    "message": "Initiating AI self-review before committing..."\n                })'
end_marker = 'continue  # Continue the main agent loop'

start_idx = content.find(start_marker)
if start_idx == -1:
    print("❌ Fix 1: Could not find start marker")
else:
    # Find the end - the continue statement after the self-review block
    end_idx = content.find(end_marker, start_idx)
    if end_idx == -1:
        print("❌ Fix 1: Could not find end marker")
    else:
        # Include the continue line in what we remove
        end_of_line = content.find("\n", end_idx)
        if end_of_line == -1:
            end_of_line = end_idx + len(end_marker)
        else:
            end_of_line += 1  # Include newline
        
        # Get the content before start marker (to preserve the "Initiating AI self-review" log)
        before = content[:start_idx]
        
        # Calculate the indent level from the start marker
        indent = "                "  # 16 spaces
        
        # New non-blocking replacement
        replacement = f'''{indent}# ── NON-BLOCKING SELF-REVIEW ─────────────────────────────────
{indent}# Try self-review once. Log the result. NEVER block commit/push.
{indent}# flake8/pylint already passed — code is syntactically valid.
{indent}try:
{indent}    passed_review, review_feedback = await _call_ai_for_self_review(
{indent}        task_description=task.get("description", task.get("title")),
{indent}        agent_type=agent["type"],
{indent}        workspace_tree=workspace_tree,
{indent}        tech_spec=task.get("_tech_spec", ""),
{indent}        project_root=capture_root,
{indent}        container_name=container_name,
{indent}    )
{indent}    pass_str = "PASSED" if passed_review else "FAILED"
{indent}    agent["output_log"].append({{
{indent}        "time": datetime.utcnow().isoformat(),
{indent}        "type": "info" if passed_review else "warning",
{indent}        "message": f"🤖 Self-Review {{pass_str}} (non-blocking):\\n{{review_feedback[:300]}}"
{indent}    }})
{indent}    if not passed_review:
{indent}        logger.warning(f"[{{agent_id}}] Self-review {{pass_str}} — proceeding with push (code quality already passed).")
{indent}        agent["output_log"].append({{
{indent}            "time": datetime.utcnow().isoformat(),
{indent}            "type": "warning",
{indent}            "message": "⚠️ Self-review flagged issues but proceeding with push (non-blocking mode). flake8/pylint already passed."
{indent}        }})
{indent}except Exception as self_review_err:
{indent}    logger.warning(f"[{{agent_id}}] Self-review skipped due to error: {{self_review_err}}")
{indent}    agent["output_log"].append({{
{indent}        "time": datetime.utcnow().isoformat(),
{indent}        "type": "warning",
{indent}        "message": f"⚠️ Self-review skipped (error): {{str(self_review_err)[:100]}}. Proceeding with push."
{indent}    }})

{indent}# Always proceed — self-review is advisory, not a gatekeeper
{indent}passed_review = True
'''
        
        # Find the end of the start marker block (the closing of the output_log.append)
        # Everything after the start marker until the continue statement gets replaced
        after_start_marker = start_idx + len(start_marker)
        before_part = content[:after_start_marker]
        after_part = content[end_of_line:]
        
        new_content = before_part + "\n\n" + replacement + after_part
        with open("agent_service.py", "w", encoding="utf-8") as f:
            f.write(new_content)
        
        print(f"✅ Fix 1: Self-review is now non-blocking (replaced block ending at position {end_of_line})")

# ══════════════════════════════════════════════════════════════════
# FIX 2: Controlled Executor container matching
# ══════════════════════════════════════════════════════════════════
with open("agent_controlled_executor.py", "r", encoding="utf-8") as f:
    ce_content = f.read()

old_func = '''def _find_agent_container(agent_id: str) -> Optional[str]:
    """
    Find a running Docker container for this agent by scanning container names.
    Container names follow the pattern: {agent_id}_{8-char-hex}
    """
    if not agent_id:
        return None
    try:
        # List all running containers and filter by name containing agent_id
        result = subprocess.run(
            ["docker", "ps", "--filter", f"name={agent_id}",
             "--format", "{{.Names}}", "--no-trunc"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return None

        containers = [n.strip() for n in result.stdout.strip().split("\\n") if n.strip()]
        if not containers:
            return None

        # Exact match: prefer container that starts with agent_id_
        for name in containers:
            if name.startswith(f"{agent_id}_"):
                return name

        # Fallback to first matching container
        return containers[0]

    except Exception as e:
        logger.debug(f"Container discovery failed for {agent_id}: {e}")
        return None'''

new_func = '''def _find_agent_container(agent_id: str) -> Optional[str]:
    """
    Find a running Docker container for this agent by scanning container names.
    Container names follow the pattern: {sanitized_agent_id}_{8-char-hex}
    Agent IDs containing '#' are sanitized to '_' to match how containers are named.
    """
    if not agent_id:
        return None
    try:
        # Normalize agent_id: containers replace '#' with '_' in names
        sanitized_id = agent_id.replace('#', '_')
        
        # List all running containers and filter by name containing sanitized_id
        result = subprocess.run(
            ["docker", "ps", "--filter", f"name={sanitized_id}",
             "--format", "{{.Names}}", "--no-trunc"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return None

        containers = [n.strip() for n in result.stdout.strip().split("\\n") if n.strip()]
        if not containers:
            return None

        # Exact match: prefer container that starts with sanitized_id_
        for name in containers:
            if name.startswith(f"{sanitized_id}_"):
                return name

        # Fallback to first matching container
        return containers[0]

    except Exception as e:
        logger.debug(f"Container discovery failed for {agent_id}: {e}")
        return None'''

if old_func in ce_content:
    ce_content = ce_content.replace(old_func, new_func, 1)
    with open("agent_controlled_executor.py", "w", encoding="utf-8") as f:
        f.write(ce_content)
    print("✅ Fix 2: Controlled Executor container matching fixed ('#' → '_')")
else:
    print("❌ Fix 2: Could not find old function in agent_controlled_executor.py")
    # Debug: print first 100 chars of old_func vs file
    idx = ce_content.find("def _find_agent_container")
    if idx != -1:
        print("   Function found at position", idx)
    else:
        print("   Function NOT found in file!")
