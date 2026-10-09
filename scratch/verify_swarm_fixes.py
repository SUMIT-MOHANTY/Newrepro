"""Throwaway verification for the 4 swarm runtime fixes. Not part of the app."""
import os
import sys
import json
import time
import tempfile
import importlib.util

PASS = 0
FAIL = 0

def check(name, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name} {extra}")

# ── 1. Supervisor summary merge ────────────────────────────────────────────
sys.path.insert(0, "agent-runtime")
from agent.supervisor import SupervisorAgent  # noqa: E402

with tempfile.TemporaryDirectory() as td:
    agent_dir = os.path.join(td, ".agent")
    os.makedirs(agent_dir)
    # Simulate run 1 by agent_01: task A completed, task B failed
    old = {
        "tasks": {
            "TASK-A": {"status": "completed", "files_changed": ["src/a.ts"]},
            "TASK-B": {"status": "failed", "error": "boom"},
        }
    }
    with open(os.path.join(agent_dir, "task_summary.json"), "w") as f:
        json.dump(old, f)
    # Simulate run 2 by agent_03 (the run that used to wipe history)
    new = {
        "tasks": {"TASK-C": {"status": "completed", "files_changed": ["src/c.tsx"]}},
        "files_changed": 1,
        "agent_reported_status": "completed",
    }
    merged = SupervisorAgent._merge_summaries(agent_dir, new)
    check("merge keeps old tasks", set(merged["tasks"]) == {"TASK-A", "TASK-B", "TASK-C"})
    check("merge recomputes completed", merged["completed"] == 2, str(merged["completed"]))
    check("merge recomputes failed", merged["failed"] == 1, str(merged["failed"]))
    check("merge unions files_changed", merged["files_changed"] == 2, str(merged["files_changed"]))
    check("merge honest status", merged["agent_reported_status"] == "partial", merged["agent_reported_status"])
    # All-completed run flips to completed
    new2 = {
        "tasks": {"TASK-B": {"status": "completed", "files_changed": ["src/b.ts"]}},
        "files_changed": 1,
        "agent_reported_status": "completed",
    }
    merged2 = SupervisorAgent._merge_summaries(agent_dir, new2)
    check("re-run of failed task upgrades it", merged2["tasks"]["TASK-B"]["status"] == "completed")
    check("all-done status", merged2["agent_reported_status"] == "completed", merged2["agent_reported_status"])
    # Corrupt existing file must not crash the merge
    with open(os.path.join(agent_dir, "task_summary.json"), "w") as f:
        f.write("{not json")
    merged3 = SupervisorAgent._merge_summaries(agent_dir, new)
    check("merge survives corrupt ledger", merged3["completed"] == 1)

# ── 2. ToolExecutor file claims ────────────────────────────────────────────
from agent.tools.tool_executor import ToolExecutor  # noqa: E402

with tempfile.TemporaryDirectory() as ws:
    os.environ["WORKSPACE_PATH"] = ws
    te = ToolExecutor.__new__(ToolExecutor)  # skip __init__ (needs MCPServer)
    te._mcp = None
    locks_file = os.path.join(ws, ".agent", "locks.json")

    os.environ["AGENT_ID"] = "agent_01"
    err = te._acquire_file_claims(["frontend/src/api.ts"])
    check("claim free file succeeds", err is None, str(err))
    locks = json.load(open(locks_file))
    check("claim persisted in locks.json", "frontend/src/api.ts" in locks)

    # Same agent re-claiming its own file is fine
    err = te._acquire_file_claims(["frontend/src/api.ts"])
    check("same agent re-claim OK", err is None, str(err))

    # A peer with a LIVE claim must conflict
    os.environ["AGENT_ID"] = "agent_02"
    te._CLAIM_WAIT_SECONDS = 0.3  # shrink wait for the test
    err = te._acquire_file_claims(["frontend/src/api.ts"])
    check("peer live claim conflicts", err is not None and "agent_01" in str(err), str(err))

    # An EXPIRED peer claim is taken over
    locks["frontend/src/api.ts"]["expires_at"] = time.time() - 1
    json.dump(locks, open(locks_file, "w"))
    err = te._acquire_file_claims(["frontend/src/api.ts"])
    check("expired claim taken over", err is None, str(err))
    check("takeover records new holder", json.load(open(locks_file))["frontend/src/api.ts"]["agent_id"] == "agent_02")

    # Release and verify cleanup
    te._release_file_claims(["frontend/src/api.ts"])
    check("release removes claim", "frontend/src/api.ts" not in json.load(open(locks_file)))

    # Extract paths across the write tools
    p1 = te._extract_write_paths("write_file", {"path": "a/b.ts"})
    p2 = te._extract_write_paths("write_files", {"files": [{"path": "a.ts"}, {"path": "b.ts"}]})
    p3 = te._extract_write_paths("batch_replace_file_content", {"edits": [{"path": "c.ts"}, {"path": "a.ts"}]})
    check("extract single path", p1 == ["a/b.ts"], str(p1))
    check("extract batch paths", p2 == ["a.ts", "b.ts"], str(p2))
    check("extract edits dedup", p3 == ["c.ts", "a.ts"], str(p3))

# ── 3. Failed-task collector against the REAL project ledger ──────────────
spec = importlib.util.spec_from_file_location(
    "conv_mod", "backend/app/services/agents/convergence_engine.py"
)
# importing full module needs app deps; instead exec only the function
import ast as _ast
src = open("backend/app/services/agents/convergence_engine.py", "r", encoding="utf-8").read()
tree = _ast.parse(src)
ns = {"os": os, "json": json, "List": list, "Dict": dict, "Any": object}
for node in tree.body:
    if isinstance(node, _ast.FunctionDef) and node.name == "collect_failed_tasks":
        mod = _ast.Module(body=[node], type_ignores=[])
        exec(compile(mod, "conv", "exec"), ns)
        break
real_ws = "backend/storage/projects/0aef5ef5-4026-46b9-a615-8ab4bd6690a2"
failed = ns["collect_failed_tasks"](real_ws)
check("collector finds real failed tasks", isinstance(failed, list) and len(failed) > 0, f"got {len(failed)}")
if failed:
    sample = failed[0]
    check("entries carry task_id+error", "task_id" in sample and "error" in sample, str(sample)[:120])
    ids = {f["task_id"] for f in failed}
    check("no duplicate task ids", len(ids) == len(failed), f"{len(ids)} vs {len(failed)}")
    print(f"        (real ledger: {len(failed)} failed tasks, e.g. {sorted(ids)[:3]})")

# ── 4. Phase escalation decision logic ─────────────────────────────────────
src2 = open("agent-runtime/infrastructure/claude_tool_client.py", "r", encoding="utf-8").read()
tree2 = _ast.parse(src2)
ns2 = {"Any": object, "Optional": object, "getattr": getattr}
for node in _ast.walk(tree2):
    if isinstance(node, _ast.ClassDef) and node.name == "ClaudeToolClient":
        for item in node.body:
            if isinstance(item, _ast.FunctionDef) and item.name == "_try_phase_escalation":
                mod2 = _ast.Module(body=[item], type_ignores=[])
                exec(compile(mod2, "ctc", "exec"), ns2)
                break
fn = ns2.get("_try_phase_escalation")

class _Reg:
    def __init__(self, has):
        self.has = has
    def get_mcp_mapping(self, name):
        return ("m", "f") if self.has else None

class _Tracker:
    def __init__(self, done):
        self.done = done
    def is_all_file_tasks_completed(self):
        return self.done

class _Exec:
    def __init__(self, registry, files_changed):
        self._registry = registry
        self.files_changed = files_changed

class _Client:
    _active_task_tracker = None

c = _Client()
# Unknown tool -> never escalate
check("unknown tool denied", not fn(c, "nuke_everything", _Exec(_Reg(False), [])))
# Real tool + unfinished tasks -> escalate
c._active_task_tracker = _Tracker(done=False)
check("unfinished tasks escalate", fn(c, "write_file", _Exec(_Reg(True), [])))
# All tasks done + no writes yet -> keep denial (wrap-up preserved)
c._active_task_tracker = _Tracker(done=True)
check("post-build no escalation", not fn(c, "read_file", _Exec(_Reg(True), [])))
# All tasks done but agent wrote files (fix posture) -> escalate
check("execution posture escalates", fn(c, "write_file", _Exec(_Reg(True), ["src/x.ts"])))

print(f"\n{'='*50}\nRESULT: {PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
