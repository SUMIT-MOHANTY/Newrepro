"""
Fix Phase 4 broadcast hooks:
1. Remove the misplaced broadcast_task_started (wrong location)
2. Add broadcast_task_started in the correct location (inside run_agent)
3. Add broadcast_task_failed at the self-review failure points
"""
filepath = "D:/BRD/BRD_Analyzer/backend/agent_service.py"

with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

changes = 0

# ── FIX 1: Remove the misplaced broadcast_task_started block ─────────
# Find and remove the broadcast_task_started that was placed incorrectly
old_misplaced = '''        # Broadcast task started via communication hooks (Phase 4)
        try:
            await broadcast_task_started(
                project_token=project_token or "",
                agent_id=agent_id,
                task=task or {},
            )
        except Exception:
            pass  # Non-critical
        agent["status"] = "running"'''

new_misplaced = '''        agent["status"] = "running"'''

if old_misplaced in content:
    content = content.replace(old_misplaced, new_misplaced, 1)
    print("✅ Fix 1: Removed misplaced broadcast_task_started")
    changes += 1
else:
    print("⚠️ Fix 1: Misplaced broadcast not found (may have different formatting)")

# ── FIX 2: Add broadcast_task_started at the CORRECT location ──────
# In run_agent function, right before agent["status"] = "running"
# We need to find the SPECIFIC occurrence in run_agent, not the first one
# Look for "Set agent to running" comment which precedes the correct match
old_correct_start_pattern = '''    # Set agent to running (or idle if no task in continuous mode)
    if task:'''
new_correct_start_pattern = '''    # Set agent to running (or idle if no task in continuous mode)
    if task:
        # Broadcast task started via communication hooks (Phase 4)
        try:
            await broadcast_task_started(
                project_token=project_token or "",
                agent_id=agent_id,
                task=task or {},
            )
        except Exception:
            pass  # Non-critical'''

if old_correct_start_pattern in content:
    content = content.replace(old_correct_start_pattern, new_correct_start_pattern, 1)
    print("✅ Fix 2: Added broadcast_task_started at correct location (run_agent)")
    changes += 1
else:
    print("⚠️ Fix 2: Could not find correct start location in run_agent")

# ── FIX 3: Add broadcast_task_failed at self-review failure path ────
# Pattern: "Self-healing: max retries reached" / "failed after max_fix_attempts"
old_fail1 = '''                                agent["progress"] = 0
                                agent["current_task"] = None'''
new_fail1 = '''                                agent["progress"] = 0
                                # Broadcast task failure (Phase 4)
                                try:
                                    await broadcast_task_failed(
                                        project_token=project_token or "",
                                        agent_id=agent_id,
                                        task=task or {},
                                        error="Task failed after max self-healing attempts",
                                    )
                                except Exception:
                                    pass  # Non-critical
                                agent["current_task"] = None'''

# Find the specific failure point - after "Self-healing iterations exhausted"
if old_fail1 in content:
    # Use rfind to get the last occurrence (the failure path, not the initial assignment)
    idx = content.rfind(old_fail1)
    if idx > 0:
        content = content[:idx] + new_fail1 + content[idx + len(old_fail1):]
        print("✅ Fix 3: Added broadcast_task_failed at self-review failure path")
        changes += 1
    else:
        print("⚠️ Fix 3: Could not find failure path")
else:
    # Try alternative pattern
    alt_fail = '''                                agent["current_task"] = None
                                
                                # DO NOT mark agent as blocked'''
    if alt_fail in content:
        idx = content.rfind(alt_fail)
        if idx > 0:
            old_text = content[idx:idx+len(alt_fail)]
            new_text = '''                                # Broadcast task failure (Phase 4)
                                try:
                                    await broadcast_task_failed(
                                        project_token=project_token or "",
                                        agent_id=agent_id,
                                        task=task or {},
                                        error="Task failed - proceeding to next task",
                                    )
                                except Exception:
                                    pass  # Non-critical
''' + old_text
            content = content[:idx] + new_text + content[idx+len(alt_fail):]
            print("✅ Fix 3: Added broadcast_task_failed at failure path (alt)")
            changes += 1
        else:
            print("⚠️ Fix 3: Could not find failure path (alt)")

# Save
with open(filepath, "w", encoding="utf-8") as f:
    f.write(content)

print(f"\n✅ All fixes applied! Total changes: {changes}")
