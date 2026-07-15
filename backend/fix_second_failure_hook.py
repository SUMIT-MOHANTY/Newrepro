"""
Fix: Add missing broadcast_task_failed in the second self-review failure path
(agent["current_task"] = None at line ~21913)
"""
import os

filepath = os.path.join(os.path.dirname(__file__), "agent_service.py")

with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

# The target pattern - we need to add broadcast_task_failed BEFORE the current_task = None
target = '# DO NOT mark agent as blocked - allow it to continue with next task\n                    agent["status"] = "idle"\n                    agent["progress"] = 0\n                    agent["current_task"] = None'

if target in content:
    idx = content.rfind(target)
    if idx > 0:
        # Make sure this is the SECOND failure path (after the first broadcast_task_failed)
        first_fail_idx = content.find("await broadcast_task_failed(")
        if idx > first_fail_idx:
            replacement = '# DO NOT mark agent as blocked - allow it to continue with next task\n                    # Broadcast task failure (Phase 4)\n                    try:\n                        await broadcast_task_failed(\n                            project_token=project_token or "",\n                            agent_id=agent_id,\n                            task=task or {},\n                            error="Self-review did not pass after max fix iterations",\n                        )\n                    except Exception:\n                        pass  # Non-critical\n                    agent["status"] = "idle"\n                    agent["progress"] = 0\n                    agent["current_task"] = None'
            content = content[:idx] + replacement + content[idx + len(target):]
            print("✅ Added broadcast_task_failed in second failure path")
        else:
            print("⚠️ Found match but before first fail hook - not replacing")
    
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    print("✅ File saved")
else:
    print("⚠️ Target pattern not found")
