"""
Apply Fixes v3 — Remaining critical fixes:
  Fix #3: Agents stuck in infinite "No eligible tasks found" loop
  Fix #4: Git Manager container conflict (use docker rm -f before create)
  Fix #5: G_agent_01/M_agent_01 flooding logs with reinitialization messages
"""

import re

FILEPATH = r"D:\BRD\BRD_Analyzer\backend\agent_service.py"

with open(FILEPATH, "r", encoding="utf-8") as f:
    content = f.read()
    lines = content.splitlines(keepends=True)

changes_made = 0

# ═══════════════════════════════════════════════════════════════════════════════
#  FIX #4 — Git Manager Container: remove existing container before creating
#  The code uses `docker ps -q -f name=...` which only finds RUNNING containers.
#  If a container exists but is STOPPED (from a previous run), docker ps doesn't
#  find it, but docker create fails with "already in use".
# ═══════════════════════════════════════════════════════════════════════════════

fix4_marker = '    container_exists = bool(existing_container.stdout.strip())'
fix4_insert_after = f'''    \n    # Force remove any existing container (running or stopped) to avoid name conflict\n    subprocess.run(\n        ["docker", "rm", "-f", container_name],\n        capture_output=True, text=True, timeout=10,\n    )\n'''

# Find the marker and insert after it
inserted_fix4 = False
for i, line in enumerate(lines):
    if fix4_marker in line and not inserted_fix4:
        # Check if already has the fix
        if 'docker rm -f' not in content:
            # Insert after this line
            indent = ' ' * (len(line) - len(line.lstrip()))
            insert_lines = [
                '    # Force remove any existing container (running or stopped) to avoid name conflict\n',
                f'    subprocess.run(\n',
                f'        ["docker", "rm", "-f", container_name],\n',
                f'        capture_output=True, text=True, timeout=10,\n',
                f'    )\n',
            ]
            for j, ins in enumerate(insert_lines):
                lines.insert(i + 1 + j, ins)
            changes_made += 1
            inserted_fix4 = True
            print("✅ Fix 4: Added docker rm -f before creating git manager container")
        else:
            print("ℹ️ Fix 4: Already applied (docker rm -f found)")
            inserted_fix4 = True
        break

if not inserted_fix4:
    print("⚠️ Fix 4: Could not find the git manager container creation code")

# Write intermediate result for Fix 4
content = "".join(lines)

# ═══════════════════════════════════════════════════════════════════════════════
#  FIX #3 — Agents stuck in infinite "No eligible tasks found" loop
#  When `_find_eligible_task` returns None, the caller should not loop forever.
#  The _run_agent_once function is called in a loop (continuous mode).
#  After returning None, the caller should break the loop.
#
#  The function returns None at line ~18874. The caller (_run_agent_once's
#  return / run_agent's loop) receives this.
#
#  Fix: In the task loop inside _run_agent_once, when no eligible task is found,
#  set agent status to "idle" and return instead of looping.
# ═══════════════════════════════════════════════════════════════════════════════

# Search for the specific continuous loop pattern inside _run_agent_once
# After the agent completes a task and if continuous=True, it loops back.
# We need to track consecutive "no task" results and break after N.

fix3_target = '                "message": f"❌ No eligible tasks found. Reasons: {dict(skip_reasons)}"\n            })\n        \n        return None'

fix3_replacement = '                "message": f"❌ No eligible tasks found. Reasons: {dict(skip_reasons)}"\n            })\n            \n            # ── AUTO-IDLE: Stop agent from looping forever when no tasks available ──\n            # After all tasks are claimed/completed, this agent has nothing to do.\n            # Mark it idle so the Master Supervisor can wake it later if new tasks appear.\n            if agent:\n                agent["status"] = "idle"\n                agent["progress"] = 100\n                agent["progress_message"] = "All tasks completed — agent idle"\n                agent["current_task"] = None\n                agent["resume_pending_task"] = False\n                logger.info(\n                    f"[{agent_id}] No eligible tasks — agent set to idle. "\n                    f"Master supervisor will re-activate if new tasks appear."\n                )\n        \n        return None'

if fix3_target in content:
    content = content.replace(fix3_target, fix3_replacement, 1)
    changes_made += 1
    print("✅ Fix 3: Added auto-idle when no eligible tasks found (stops infinite loop)")
else:
    print("⚠️ Fix 3: Could not find the 'no eligible tasks' return section")

# ═══════════════════════════════════════════════════════════════════════════════
#  FIX #5 — G_agent_01/M_agent_01 log flooding
#  _make_agent() adds an initialization log entry every time it's called.
#  When `initialize_agents_from_records()` runs (e.g. on each run-all),
#  it clears ALL agent states and recreates them fresh, generating new logs.
#
#  Fix: In _make_agent, only add the "initialized and waiting" log if the
#  agent doesn't already have this message in its log.
#  Better: skip adding initialization log for system agents on re-creates.
# ═══════════════════════════════════════════════════════════════════════════════

fix5_target_g = (
    '    if agent_id == GIT_MANAGER_AGENT_ID:\n'
    '        agent["name"] = "Git Manager"\n'
    '        agent["progress"] = 100\n'
    '        agent["progress_message"] = "Git manager idle"\n'
    '        agent["output_log"].append({\n'
    '            "time": datetime.utcnow().isoformat(),\n'
    '            "type": "info",\n'
    '            "message": "Git manager initialized and waiting for merge events."\n'
    '        })\n'
    '    elif agent_id == MASTER_AGENT_ID:\n'
    '        agent["name"] = "Master Agent"\n'
    '        agent["progress"] = 100\n'
    '        agent["progress_message"] = "Master agent idle"\n'
    '        agent["output_log"].append({\n'
    '            "time": datetime.utcnow().isoformat(),\n'
    '            "type": "info",\n'
    '            "message": "Master agent initialized and waiting for orchestration/status events."\n'
    '        })'
)

fix5_replacement = (
    '    if agent_id == GIT_MANAGER_AGENT_ID:\n'
    '        agent["name"] = "Git Manager"\n'
    '        agent["progress"] = 100\n'
    '        agent["progress_message"] = "Git manager idle"\n'
    '        # Only log initialization once — prevent log flooding on re-creates\n'
    '        _has_init_log = any(\n'
    '            e.get("message", "") == "Git manager initialized and waiting for merge events."\n'
    '            for e in agent["output_log"]\n'
    '        )\n'
    '        if not _has_init_log:\n'
    '            agent["output_log"].append({\n'
    '                "time": datetime.utcnow().isoformat(),\n'
    '                "type": "info",\n'
    '                "message": "Git manager initialized and waiting for merge events."\n'
    '            })\n'
    '    elif agent_id == MASTER_AGENT_ID:\n'
    '        agent["name"] = "Master Agent"\n'
    '        agent["progress"] = 100\n'
    '        agent["progress_message"] = "Master agent idle"\n'
    '        # Only log initialization once — prevent log flooding on re-creates\n'
    '        _has_init_log = any(\n'
    '            e.get("message", "") == "Master agent initialized and waiting for orchestration/status events."\n'
    '            for e in agent["output_log"]\n'
    '        )\n'
    '        if not _has_init_log:\n'
    '            agent["output_log"].append({\n'
    '                "time": datetime.utcnow().isoformat(),\n'
    '                "type": "info",\n'
    '                "message": "Master agent initialized and waiting for orchestration/status events."\n'
    '            })'
)

if fix5_target_g in content:
    content = content.replace(fix5_target_g, fix5_replacement, 1)
    changes_made += 1
    print("✅ Fix 5: Added dedup guard for system agent initialization logs")
else:
    print("⚠️ Fix 5: Could not find the system agent initialization section")

# Save the modified file
if changes_made > 0:
    with open(FILEPATH, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"\n✅ All changes applied! Total changes: {changes_made}")
else:
    print("\n⚠️ No changes made — nothing matched")
