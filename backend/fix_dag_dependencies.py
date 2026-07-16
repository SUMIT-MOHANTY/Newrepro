"""
Fix: DAG dependency checks were being skipped after bootstrap pushed.
The condition `if not is_bootstrap_pushed(project_token):` wrapped the
entire dependency check block — meaning once bootstrap completed, ALL
dependency checking was bypassed. Agents grabbed any task without
waiting for their linked_tasks dependencies to complete.

This caused:
- Agents working in parallel on dependent tasks (e.g. TASK-04 starts
  before TASK-03 finishes)
- Each agent building their OWN version of shared files
- Broken code structure from tasks executing out of order
- Merge conflicts when Git Merge Agent tried to integrate branches
"""
import re

FILEPATH = r"D:\BRD\BRD_Analyzer\backend\agent_service.py"

with open(FILEPATH, "r", encoding="utf-8") as f:
    content = f.read()

changes_made = 0

# ═══════════════════════════════════════════════════════════════════════════
# FIX #1 — Remove the `if not is_bootstrap_pushed(project_token):` wrapper
#          so dependency checks ALWAYS run for non-bootstrap tasks.
# ═══════════════════════════════════════════════════════════════════════════

# The old pattern: dependencies are ONLY checked when bootstrap NOT pushed
old_dep_block = '''                if not is_bootstrap_task:
                    # If bootstrap is pushed, skip all dependency checks — scaffold is ready
                    _proj_key = _project_key(project_token)
                    if not is_bootstrap_pushed(project_token):
                        task_deps = t.get("dependencies", [])
                        if not task_deps:
                            linked = t.get("linked_tasks", [])
                            if linked:
                                executable_deps = []
                                for lt_id in linked:
                                    linked_task = next((ext_t for ext_t in external_tasks if str(_normalize_task_id(ext_t) or ext_t.get("external_id") or ext_t.get("id")) == str(lt_id)), None)
                                    if linked_task:
                                        linked_type = (linked_task.get("task_type") or "").upper()
                                        if linked_type in ["TASK", "BUG"]:
                                            executable_deps.append(str(lt_id))
                                task_deps = executable_deps

                        if task_deps:
                            live_mem.register_task_dependencies(tid, [str(d) for d in task_deps])

                        if not live_mem.check_task_dependencies(tid):
                            blocking = live_mem.get_blocking_tasks(tid)
                            logger.info(f"[{agent_id}] Task {tid} blocked by dependencies: {blocking}")
                            skip_reasons["dependency_blocked"] += 1
                            continue

                    # Skip conflict checks too if bootstrap just pushed and no tasks completed yet
                    if not is_bootstrap_pushed(project_token) or live_mem.completed_history:
                        blocked, reason = _check_task_conflicts(agent_id, t, live_mem, project_token=project_token)
                        if blocked:
                            logger.info(f"[{agent_id}] Task {tid} blocked by conflict rules: {reason}")
                            if agent:
                                agent["output_log"].append({
                                    "time": datetime.utcnow().isoformat(),
                                    "type": "info",
                                    "message": f"⚠️ Task {tid} conflict: {reason}"
                                })
                            skip_reasons["conflict_blocked"] += 1
                            continue'''

# The new pattern: dependencies are ALWAYS checked (bootstrap task exempted)
new_dep_block = '''                if not is_bootstrap_task:
                    # ── DAG DEPENDENCY CHECK ──────────────────────────────────
                    # ALWAYS check dependencies, not just before bootstrap pushes.
                    # This ensures TASK-03 waits for TASK-01 and TASK-02 to complete
                    # before an agent picks it up.
                    task_deps = t.get("dependencies", [])
                    if not task_deps:
                        linked = t.get("linked_tasks", [])
                        if linked:
                            executable_deps = []
                            for lt_id in linked:
                                linked_task = next((ext_t for ext_t in external_tasks if str(_normalize_task_id(ext_t) or ext_t.get("external_id") or ext_t.get("id")) == str(lt_id)), None)
                                if linked_task:
                                    linked_type = (linked_task.get("task_type") or "").upper()
                                    if linked_type in ["TASK", "BUG"]:
                                        executable_deps.append(str(lt_id))
                            task_deps = executable_deps

                    if task_deps:
                        live_mem.register_task_dependencies(tid, [str(d) for d in task_deps])

                    if not live_mem.check_task_dependencies(tid):
                        blocking = live_mem.get_blocking_tasks(tid)
                        logger.info(f"[{agent_id}] Task {tid} blocked by dependencies: {blocking}")
                        if agent:
                            agent["output_log"].append({
                                "time": datetime.utcnow().isoformat(),
                                "type": "info",
                                "message": f"⏸️ Task {tid} waiting for dependencies: {blocking}"
                            })
                        skip_reasons["dependency_blocked"] += 1
                        continue

                    # ── CONFLICT CHECK ─────────────────────────────────────────
                    # Always check for file conflicts between agents
                    blocked, reason = _check_task_conflicts(agent_id, t, live_mem, project_token=project_token)
                    if blocked:
                        logger.info(f"[{agent_id}] Task {tid} blocked by conflict rules: {reason}")
                        if agent:
                            agent["output_log"].append({
                                "time": datetime.utcnow().isoformat(),
                                "type": "info",
                                "message": f"⚠️ Task {tid} conflict: {reason}"
                            })
                        skip_reasons["conflict_blocked"] += 1
                        continue'''

if old_dep_block in content:
    content = content.replace(old_dep_block, new_dep_block, 1)
    changes_made += 1
    print("✅ Fix 1: DAG dependency checks now ALWAYS run (not just before bootstrap)")
else:
    # Try to find a partial match to debug
    idx = content.find("If bootstrap is pushed, skip all dependency checks")
    if idx != -1:
        print(f"⚠️ Fix 1: Found the comment marker but the exact block doesn't match (formatting differences)")
        print(f"   Found at position {idx}")
        # Show context
        print(content[idx:idx+500])
    else:
        print("⚠️ Fix 1: Could not find the dependency bypass code section")
    
    # Try alternative: find and replace just the inner condition
    alt_old = '                    if not is_bootstrap_pushed(project_token):\n                        task_deps = t.get("dependencies", [])\n                        if not task_deps:\n                            linked = t.get("linked_tasks", [])\n                            if linked:'
    alt_new = '                    task_deps = t.get("dependencies", [])\n                    if not task_deps:\n                        linked = t.get("linked_tasks", [])\n                        if linked:'
    if alt_old in content:
        content = content.replace(alt_old, alt_new, 1)
        changes_made += 1
        print("✅ Fix 1 (alt): Removed bootstrap gate wrapper from dependency check")
    
    # Also fix the indent for the lines after the if block
    alt_old2 = '''                        if task_deps:
                            live_mem.register_task_dependencies(tid, [str(d) for d in task_deps])

                        if not live_mem.check_task_dependencies(tid):
                            blocking = live_mem.get_blocking_tasks(tid)
                            logger.info(f"[{agent_id}] Task {tid} blocked by dependencies: {blocking}")
                            skip_reasons["dependency_blocked"] += 1
                            continue

                    # Skip conflict checks too if bootstrap just pushed and no tasks completed yet
                    if not is_bootstrap_pushed(project_token) or live_mem.completed_history:
                        blocked, reason = _check_task_conflicts(agent_id, t, live_mem, project_token=project_token)
                        if blocked:'''
    alt_new2 = '''                        if task_deps:
                            live_mem.register_task_dependencies(tid, [str(d) for d in task_deps])

                        if not live_mem.check_task_dependencies(tid):
                            blocking = live_mem.get_blocking_tasks(tid)
                            logger.info(f"[{agent_id}] Task {tid} blocked by dependencies: {blocking}")
                            if agent:
                                agent["output_log"].append({
                                    "time": datetime.utcnow().isoformat(),
                                    "type": "info",
                                    "message": f"⏸️ Task {tid} waiting for dependencies: {blocking}"
                                })
                            skip_reasons["dependency_blocked"] += 1
                            continue

                    # ── CONFLICT CHECK ─────────────────────────────────────────
                    # Always check for file conflicts between agents
                    blocked, reason = _check_task_conflicts(agent_id, t, live_mem, project_token=project_token)
                    if blocked:'''
    if alt_old2 in content:
        content = content.replace(alt_old2, alt_new2, 1)
        print("✅ Fix 1 (alt): Fixed indent for conflict check to always run")

# Save
if changes_made > 0:
    with open(FILEPATH, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"\n✅ All changes applied! Total changes: {changes_made}")
else:
    print("\n⚠️ No changes made — none of the patterns matched")
    print("The file may already have the fix applied.")
