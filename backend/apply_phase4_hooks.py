"""
Apply Phase 4 broadcast hook calls at task start/complete/fail points.
The hooks are imported but never called - this fixes that.
"""
filepath = "D:/BRD/BRD_Analyzer/backend/agent_service.py"

with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

changes = 0

# ── 1. Add broadcast_task_started after agent["status"] = "running" ─────────
# Pattern: agent["status"] = "running" where a task is about to be executed
old_start = '''        agent["status"] = "running"'''
new_start = '''        # Broadcast task started via communication hooks (Phase 4)
        try:
            await broadcast_task_started(
                project_token=project_token or "",
                agent_id=agent_id,
                task=task or {},
            )
        except Exception:
            pass  # Non-critical
        agent["status"] = "running"'''

# Only replace the FIRST occurrence (the most relevant task start point)
if old_start in content:
    idx = content.find(old_start)
    if idx > 0:
        content = content[:idx] + new_start + content[idx + len(old_start):]
        print("✅ Phase 4: Added broadcast_task_started")
        changes += 1
else:
    print("⚠️ Phase 4: Could not find task start point")

# ── 2. Add broadcast_task_completed after task completion ───────────────────
old_complete = '''            agent["progress_message"] = "Task completed"'''
new_complete = '''            agent["progress_message"] = "Task completed"
                    # Broadcast task completion via communication hooks (Phase 4)
                    try:
                        await broadcast_task_completed(
                            project_token=project_token or "",
                            agent_id=agent_id,
                            task=task or {},
                            result={"files_created": [], "branch": agent.get("current_task", {}).get("_local_branch", "")},
                        )
                    except Exception:
                        pass  # Non-critical'''

if old_complete in content:
    content = content.replace(old_complete, new_complete, 1)
    print("✅ Phase 4: Added broadcast_task_completed")
    changes += 1
else:
    print("⚠️ Phase 4: Could not find task completion point")

# ── 3. Add broadcast_task_failed in self-review failure path ────────────────
old_fail = '''                                agent["current_task"] = None
                                
                                # DO NOT mark agent as blocked - allow it to continue with next task'''
new_fail = '''                                # Broadcast task failure via communication hooks (Phase 4)
                                try:
                                    await broadcast_task_failed(
                                        project_token=project_token or "",
                                        agent_id=agent_id,
                                        task=task or {},
                                        error="Self-review failed after max attempts",
                                        brd_impact="Task requires manual review - handover to master",
                                    )
                                except Exception:
                                    pass  # Non-critical
                                agent["current_task"] = None
                                
                                # DO NOT mark agent as blocked - allow it to continue with next task'''

if old_fail in content:
    content = content.replace(old_fail, new_fail, 1)
    print("✅ Phase 4: Added broadcast_task_failed after self-review failure")
    changes += 1
else:
    print("⚠️ Phase 4: Could not find self-review failure point")

# ── 4. Add broadcast_task_failed for the second self-review failure path ────
old_fail2 = '''                    agent["current_task"] = None
                    
                    # DO NOT mark agent as blocked - allow it to continue with next task'''
new_fail2 = '''                    # Broadcast task failure (Phase 4)
                    try:
                        await broadcast_task_failed(
                            project_token=project_token or "",
                            agent_id=agent_id,
                            task=task or {},
                            error="Self-review did not pass",
                            brd_impact="Task may have unresolved issues",
                        )
                    except Exception:
                        pass  # Non-critical
                    agent["current_task"] = None
                    
                    # DO NOT mark agent as blocked - allow it to continue with next task'''

# Only replace the second occurrence, not the first
if old_fail2 in content:
    # Find all occurrences and replace only after the first failure point
    parts = content.split(old_fail2)
    if len(parts) >= 3:
        # Rejoin with replacement only for the middle parts
        content = parts[0] + old_fail2 + parts[1] + new_fail2 + "".join(parts[2:])
        print("✅ Phase 4: Added broadcast_task_failed for alternate failure path")
        changes += 1
    else:
        print("⚠️ Phase 4: Could not find second failure point (only 1 match)")

# ── Save ──
with open(filepath, "w", encoding="utf-8") as f:
    f.write(content)

print(f"\n✅ Phase 4 complete! Total changes: {changes}")
