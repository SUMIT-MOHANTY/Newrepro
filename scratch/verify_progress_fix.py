"""Throwaway verification for the task-progress reconciliation fix."""
import os
import json
import ast as _ast
import tempfile

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


def extract_fn(path, fn_name):
    src = open(path, "r", encoding="utf-8").read()
    tree = _ast.parse(src)
    for node in _ast.walk(tree):
        if isinstance(node, _ast.FunctionDef) and node.name == fn_name:
            seg = _ast.get_source_segment(src, node)
            return _ast.parse(seg)
    raise AssertionError(f"{fn_name} not found in {path}")


class FakeSettings:
    project_storage_root = ""  # set per-test


class FakeOW:
    def __init__(self, status="in_progress", task_data=None):
        self.status = status
        self.task_data = task_data
        self.agent_id = "old_agent"
        self.claimed_at = None
        self.started_at = None


class FakeTask:
    def __init__(self, task_id):
        self.task_id = task_id


class FakeQuery:
    def __init__(self, result):
        self.result = result
    def filter(self, *a, **k):
        return self
    def first(self):
        return self.result


class FakeDB:
    """One preconfigured .first() result per model class, then a queue for adds."""
    def __init__(self):
        self.added = []
        self.commits = 0
        self.rollbacks = 0
        self.first_results = {}
        self.created_ows = []
    def query(self, cls):
        return FakeQuery(self.first_results.get(cls))
    def add(self, obj):
        self.added.append(obj)
    def flush(self):
        pass
    def commit(self):
        self.commits += 1
    def rollback(self):
        self.rollbacks += 1


class FakeOwnershipModel:
    # SQLAlchemy-style class attributes referenced inside filter() expressions
    project_token = None
    task_id = None
    task_data = None  # nullable JSON column default
    def __init__(self, **kw):
        self.__dict__.update(kw)


# ── Test with the REAL project ledger ──────────────────────────────────────
real_ws = os.path.abspath("backend/storage/projects/0aef5ef5-4026-46b9-a615-8ab4bd6690a2")
FakeSettings.project_storage_root = os.path.dirname(real_ws)
token = os.path.basename(real_ws)

ledger = json.load(open(os.path.join(real_ws, ".agent", "task_summary.json")))
ledger_tasks = ledger.get("tasks") or {}
print(f"  (real ledger has {len(ledger_tasks)} tasks)")

completed_verified = [k for k, v in ledger_tasks.items()
                      if isinstance(v, dict) and v.get("status") == "completed" and v.get("platform_verified")]
completed_unverified = [k for k, v in ledger_tasks.items()
                        if isinstance(v, dict) and v.get("status") == "completed" and not v.get("platform_verified")]
failed = [k for k, v in ledger_tasks.items() if isinstance(v, dict) and v.get("status") == "failed"]
print(f"  (completed+verified={len(completed_verified)}, completed+unverified={len(completed_unverified)}, failed={len(failed)})")

proj = "0aef5ef5-4026-46b9-a615-8ab4bd6690a2"
suffix = lambda k: k.split("_", 1)[-1]

# Build DB tasks from ledger keys
db_tasks = [FakeTask(k) for k in list(ledger_tasks.keys())[:5] + ["PROJ_TASK-99"]]

# TASK-01 (or first completed+verified): stale ownership row exists
stale_id = (completed_verified or list(ledger_tasks.keys()))[0]
stale_ow = FakeOW(status="in_progress", task_data=None)

db = FakeDB()
db.first_results = {
    "Task": None,           # unused; lookup is by attribute below
    "AgentTaskOwnership": None,  # no existing ownership rows except stale
}
# The fake can't differentiate per-task; run 1: pre-existing stale ow for stale_id's task.
# We handle matching by running extraction with a lookup returning stale_ow only for that task.
ns = {
    "os": os, "json": json, "settings": FakeSettings(),
    "models": type("M", (), {"AgentTaskOwnership": FakeOwnershipModel, "Task": FakeTask}),
    "logger": type("L", (), {"warning": staticmethod(lambda *a, **k: print("  WARN:", k or a))}),
    "Session": object,
    "List": list, "Dict": dict, "Any": object,
}
mod = extract_fn("backend/app/routers/agents.py", "_reconcile_progress_from_ledger")
fn = compile(mod, "agents", "exec")

# Per-task first() results: simplest is to give FakeDB dynamic behavior
class DynDB(FakeDB):
    def __init__(self, stale_task_id, tasks):
        super().__init__()
        self.stale_task_id = stale_task_id
        self.tasks = tasks
    def query(self, cls):
        name = cls.__name__ if isinstance(cls, type) else str(cls)
        if "Ownership" in name:
            return FakeQuery(None)  # replaced below per-task via closure trick
        return FakeQuery(None)

# Scenario A: ownership exists and is stale -> must be upgraded
class MatchDB(FakeDB):
    def __init__(self, existing_ow=None, task=None):
        super().__init__()
        self.existing_ow = existing_ow
        self.task = task
    def query(self, cls):
        name = getattr(cls, "__name__", str(cls))
        if "Ownership" in name:
            return FakeQuery(self.existing_ow)
        return FakeQuery(self.task)

exec(fn, ns)
reconcile = ns["_reconcile_progress_from_ledger"]

# A1: completed+verified ledger entry with stale 'in_progress' ownership -> done/100
if completed_verified:
    tid = completed_verified[0]
    ow = FakeOW(status="in_progress", task_data=None)
    dbA = MatchDB(existing_ow=ow, task=FakeTask(tid))
    dbA.first_results = {}
    reconcile(dbA, [FakeTask(tid)], token)
    check("stale in_progress -> done", ow.status == "done", ow.status)
    check("progress set to 100", ow.task_data and ow.task_data.get("task_progress") == 100, str(ow.task_data))
    check("commit issued", dbA.commits == 1, str(dbA.commits))

# A2: completed+unverified -> in_review/75 (honest)
if completed_unverified:
    tid = completed_unverified[0]
    ow = FakeOW(status="in_progress", task_data=None)
    dbA2 = MatchDB(existing_ow=ow, task=FakeTask(tid))
    reconcile(dbA2, [FakeTask(tid)], token)
    check("unverified completion -> in_review", ow.status == "in_review", ow.status)
    check("unverified progress 75", ow.task_data and ow.task_data.get("task_progress") == 75, str(ow.task_data))

# A3: failed -> failed/0
if failed:
    tid = failed[0]
    ow = FakeOW(status="in_progress", task_data=None)
    dbA3 = MatchDB(existing_ow=ow, task=FakeTask(tid))
    reconcile(dbA3, [FakeTask(tid)], token)
    check("failed task -> failed", ow.status == "failed", ow.status)
    check("failed progress 0", ow.task_data and ow.task_data.get("task_progress") == 0, str(ow.task_data))

# A4: already-correct row -> NO changes, NO commit (no-op when in sync)
if completed_verified:
    tid = completed_verified[0]
    ow = FakeOW(status="done", task_data={"task_progress": 100})
    dbA4 = MatchDB(existing_ow=ow, task=FakeTask(tid))
    reconcile(dbA4, [FakeTask(tid)], token)
    check("in-sync row untouched", ow.status == "done")
    check("no commit when in sync", dbA4.commits == 0, str(dbA4.commits))

# A5: no existing ownership -> creates one with ledger status
if completed_verified:
    tid = completed_verified[0]
    dbA5 = MatchDB(existing_ow=None, task=FakeTask(tid))
    reconcile(dbA5, [FakeTask(tid)], token)
    check("missing ownership created", len(dbA5.added) == 1, str(len(dbA5.added)))
    if dbA5.added:
        new_ow = dbA5.added[0]
        check("created row done/100", new_ow.status == "done" and new_ow.task_data.get("task_progress") == 100,
              f"{new_ow.status} {new_ow.task_data}")

# A6: missing ledger -> no-op
FakeSettings.project_storage_root = tempfile.gettempdir()
dbA6 = MatchDB(existing_ow=None, task=FakeTask("X_TASK-1"))
reconcile(dbA6, [FakeTask("X_TASK-1")], "nonexistent_token_xyz")
check("missing ledger no-op", dbA6.commits == 0 and dbA6.added == [])

# A7: corrupt ledger -> no crash
tmpd = tempfile.mkdtemp()
projd = os.path.join(tmpd, "tok_corrupt", ".agent")
os.makedirs(projd)
open(os.path.join(projd, "task_summary.json"), "w").write("{bad json")
FakeSettings.project_storage_root = tmpd
dbA7 = MatchDB(existing_ow=None, task=FakeTask("tok_corrupt_TASK-1"))
reconcile(dbA7, [FakeTask("tok_corrupt_TASK-1")], "tok_corrupt")
check("corrupt ledger no crash", dbA7.commits == 0)

print(f"\n{'='*50}\nRESULT: {PASS} passed, {FAIL} failed")
import sys
sys.exit(1 if FAIL else 0)
