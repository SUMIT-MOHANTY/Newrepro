"""
Fix remaining Phase 4 issues in agent_service.py:
1. Fix empty branch in broadcast_task_completed (branch is already None when broadcast fires)
2. Add missing broadcast_task_failed in second self-review failure path
"""
import os

filepath = os.path.join(os.path.dirname(__file__), "agent_service.py")

with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

changes = 0

# ── Fix 1: Save branch name BEFORE clearing current_task ─────────────────
# The current pattern:
#   agent["current_task"] = None
#   agent["resume_pending_task"] = False
#   ...
#   agent["progress_message"] = "Task completed"
#   ...
#   await broadcast_task_completed(result={"files_created": [], "branch": agent.get("current_task", {}).get("_local_branch", "")})
# 
# Fix: Capture branch before clearing current_task, then use captured value

old_completion_block = '''            # ═══ CRITICAL FIX: Clear current_task and resume_pending_task IMMEDIATELY after completion ═══
            # This prevents the agent from re-executing the same task
            agent["current_task"] = None
            agent["resume_pending_task"] = False'''

new_completion_block = '''            # ═══ CRITICAL FIX: Clear current_task and resume_pending_task IMMEDIATELY after completion ═══
            # This prevents the agent from re-executing the same task
            _completed_task_branch = agent.get("current_task", {}).get("_local_branch", "") if agent.get("current_task") else ""
            agent["current_task"] = None
            agent["resume_pending_task"] = False'''

if old_completion_block in content:
    content = content.replace(old_completion_block, new_completion_block, 1)
    print("✅ Fix 1: Saved branch name before clearing current_task")
    changes += 1
else:
    print("⚠️ Fix 1: Could not find completion block")

# Now fix the broadcast_task_completed to use the saved branch variable
old_broadcast = '''                            result={"files_created": [], "branch": agent.get("current_task", {}).get("_local_branch", "")},'''
new_broadcast = '''                            result={"files_created": [], "branch": _completed_task_branch},'''

if old_broadcast in content:
    content = content.replace(old_broadcast, new_broadcast, 1)
    print("✅ Fix 1b: Updated broadcast_task_completed to use saved branch")
    changes += 1
else:
    print("⚠️ Fix 1b: Could not find broadcast_task_completed result")

# ── Fix 2: Add broadcast_task_failed in second self-review failure path ──
# Find the second failure pattern where current_task is None'd without broadcast
old_fail2 = '''                    agent["current_task"] = None
                    
                    # DO NOT mark agent as blocked'''
new_fail2 = '''                    # Broadcast task failure (Phase 4)
                    try:
                        await broadcast_task_failed(
                            project_token=project_token or "",
                            agent_id=agent_id,
                            task=task or {},
                            error="Self-review did not pass after max fix iterations - handing off to master",
                        )
                    except Exception:
                        pass  # Non-critical
                    agent["current_task"] = None
                    
                    # DO NOT mark agent as blocked'''

# Find the last occurrence (the second failure path)
if old_fail2 in content:
    # Use rfind to get the last occurrence (second path)
    idx = content.rfind(old_fail2)
    if idx > 0 and idx < len(content) - len(old_fail2):
        # Check that this is AFTER the first broadcast_task_failed we already added
        first_fail_idx = content.find("await broadcast_task_failed(")
        if idx > first_fail_idx:
            content = content[:idx] + new_fail2 + content[idx + len(old_fail2):]
            print("✅ Fix 2: Added broadcast_task_failed in second failure path")
            changes += 1
        else:
            print("⚠️ Fix 2: Found match but before first fail hook")
    else:
        print("⚠️ Fix 2: Match at edge of file")
else:
    print("⚠️ Fix 2: Could not find second failure path")

# Save
with open(filepath, "w", encoding="utf-8") as f:
    f.write(content)

print(f"\n✅ All fixes applied! Total changes: {changes}")
