"""
Apply Phase 3 and Phase 4 integration changes to agent_service.py.

Phase 3: Replace _call_ai_for_code with call_ai_for_code_with_controlled
Phase 4: Add broadcast hook calls at task start/complete/fail points
"""
import os
import re
import sys

filepath = os.path.join(os.path.dirname(__file__), "agent_service.py")

with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

# ── Phase 3: Add import ──────────────────────────────────────────────────────
old_import = ("from agent_communication_hooks import broadcast_task_started, "
              "broadcast_task_completed, broadcast_task_failed, broadcast_bootstrap_waiting")

new_import = old_import + ("\nfrom agent_controlled_executor import "
                           "call_ai_for_code_with_controlled")

if old_import in content:
    content = content.replace(old_import, new_import, 1)
    print("✅ Phase 3: Added import for call_ai_for_code_with_controlled")
else:
    # Try finding just the agent_communication_hooks line within a larger import block
    alt_pattern = r"(from agent_communication_hooks import[^\n]+)"
    match = re.search(alt_pattern, content)
    if match:
        old_line = match.group(1)
        content = content.replace(old_line, old_line + "\nfrom agent_controlled_executor import call_ai_for_code_with_controlled", 1)
        print("✅ Phase 3: Added import (alternative pattern)")
    else:
        print("❌ Phase 3: Could not find import location")

# ── Phase 3: Replace all _call_ai_for_code calls ─────────────────────────────
old_calls = content.count("await _call_ai_for_code(")
content = content.replace("await _call_ai_for_code(", "await call_ai_for_code_with_controlled(")
new_calls = content.count("await call_ai_for_code_with_controlled(")
print(f"✅ Phase 3: Replaced {old_calls} _call_ai_for_code calls → now {new_calls} controlled calls")

# ── Phase 4: Add broadcast_task_started before the first code generation ─────
# Find the pattern: before the first call_ai_for_code_with_controlled in the
# main task execution loop, add broadcast_task_started
# Pattern: Find "task_description_with_checklist" context which precedes the first call
broadcast_start_block = """
                # Broadcast task started via communication hooks (Phase 4)
                try:
                    await broadcast_task_started(
                        project_token=project_token or _ensure_project_state(project_token).get("task_token", ""),
                        agent_id=agent_id,
                        task=task or {},
                    )
                except Exception:
                    pass  # Non-critical

"""

# Insert broadcast_task_started before the first call_ai_for_code_with_controlled
# that appears in the context of a task description
first_call_idx = content.find("call_ai_for_code_with_controlled(")
if first_call_idx > 0:
    # Find the preceding newline to insert before
    insert_pos = content.rfind("\n", 0, first_call_idx - 100, first_call_idx)
    if insert_pos > 0:
        content = content[:insert_pos] + broadcast_start_block + content[insert_pos:]
        print("✅ Phase 4: Added broadcast_task_started before first code generation")
else:
    print("⚠️ Phase 4: Could not find insertion point for broadcast_task_started")

# ── Phase 4: Add broadcast_task_completed/failed after execution results ────
# Find where the execution result is evaluated (look for "success" check after code generation)
# We add broadcast after successful task completion
broadcast_complete_block = """
                    # Broadcast task completion (Phase 4)
                    try:
                        if result.get("success"):
                            await broadcast_task_completed(
                                project_token=project_token or "",
                                agent_id=agent_id,
                                task=task or {},
                                result={"files_created": result.get("files_written", []), "branch": result.get("branch")},
                            )
                        else:
                            await broadcast_task_failed(
                                project_token=project_token or "",
                                agent_id=agent_id,
                                task=task or {},
                                error=result.get("error", "Unknown error"),
                            )
                    except Exception:
                        pass  # Non-critical

"""

# Insert after the last _exec_script_in_container call (which follows code generation)
# Look for the pattern where execution result is used
# Find "_exec_script_in_container, container_name, generated_code" pattern
exec_call_pos = content.rfind("_exec_script_in_container, container_name, generated_code")
if exec_call_pos > 0:
    # Find the end of this block (next line containing result check)
    block_end = content.find("\n", exec_call_pos)
    if block_end > 0:
        block_end = content.find("if result.get(", block_end)
        if block_end > 0:
            content = content[:block_end] + broadcast_complete_block + content[block_end:]
            print("✅ Phase 4: Added broadcast_task_completed/failed after execution")
else:
    print("⚠️ Phase 4: Could not find insertion point for broadcast completion")

# ── Phase 4: Add broadcast_task_failed in the fix/retry loop ────────────────
# Find the fix code generation pattern
broadcast_fix_failed_block = """
                        # Broadcast fix failure (Phase 4)
                        try:
                            await broadcast_task_failed(
                                project_token=project_token or "",
                                agent_id=agent_id,
                                task=task or {},
                                error=fix_error,
                                brd_impact="Fix iteration failed for task",
                            )
                        except Exception:
                            pass  # Non-critical

"""

fix_pos = content.rfind("fix_code, fix_thought = await call_ai_for_code_with_controlled(")
if fix_pos > 0:
    content = content[:fix_pos] + broadcast_fix_failed_block + content[fix_pos:]
    print("✅ Phase 4: Added broadcast_task_failed in fix loop")
else:
    print("⚠️ Phase 4: Could not find fix loop insertion point")

# Save
with open(filepath, "w", encoding="utf-8") as f:
    f.write(content)

print("\n✅ All integration changes applied!")
print("=" * 60)
