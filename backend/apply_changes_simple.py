"""
Apply Phase 3 and Phase 4 integration changes to agent_service.py.
"""
import re

filepath = "D:/BRD/BRD_Analyzer/backend/agent_service.py"

with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

changes_made = 0

# ── Phase 3: Add import ──
old_import = "from agent_communication_hooks import broadcast_task_started, broadcast_task_completed, broadcast_task_failed, broadcast_bootstrap_waiting"
new_import = old_import + "\nfrom agent_controlled_executor import call_ai_for_code_with_controlled"

if old_import in content:
    content = content.replace(old_import, new_import, 1)
    print("✅ Phase 3: Added import for call_ai_for_code_with_controlled")
    changes_made += 1
else:
    print("⚠️ Phase 3: Import line not found, trying alternate pattern")
    alt = re.search(r"from agent_communication_hooks import[^\n]*", content)
    if alt:
        content = content.replace(alt.group(0), alt.group(0) + "\nfrom agent_controlled_executor import call_ai_for_code_with_controlled", 1)
        print("✅ Phase 3: Added import (alt)")
        changes_made += 1

# ── Phase 3: Replace all _call_ai_for_code calls ──
count_before = content.count("await _call_ai_for_code(")
content = content.replace("await _call_ai_for_code(", "await call_ai_for_code_with_controlled(")
count_after = content.count("await call_ai_for_code_with_controlled(")
print(f"✅ Phase 3: Replaced {count_before} calls → {count_after} controlled calls")
changes_made += 1

# ── Save ──
with open(filepath, "w", encoding="utf-8") as f:
    f.write(content)

print(f"\n✅ All changes applied! Total changes: {changes_made}")
print(f"File size: {len(content)} chars")
