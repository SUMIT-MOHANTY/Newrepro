"""Throwaway probe: behavioral check of _sync_task_progress_to_db (real-time callback path)."""
import os
import ast as _ast

src = open("backend/app/routers/agent_callbacks.py", encoding="utf-8").read()
tree = _ast.parse(src)
node = next(n for n in _ast.walk(tree) if isinstance(n, _ast.FunctionDef) and n.name == "_sync_task_progress_to_db")
mod = _ast.parse(_ast.get_source_segment(src, node))

PASS, FAIL = 0, 0
def check(name, cond, extra=""):
    global PASS, FAIL
    if cond: PASS += 1; print(f"  PASS  {name}")
    else: FAIL += 1; print(f"  FAIL  {name} {extra}")

class _Col:
    """Mimics an SQLAlchemy instrumented attribute for filter() expressions."""
    def like(self, *a, **k): return self
    def __eq__(self, other): return False

class FakeTask:
    # SQLAlchemy-style class attributes referenced inside filter() expressions
    task_id = _Col()
    project_token = _Col()
    def __init__(self, tid): self.task_id = tid

class FakeOwnership:
    project_token = None
    task_id = None
    task_data = None  # nullable JSON column default
    def __init__(self, **kw): self.__dict__.update(kw)

class Q:
    def __init__(self, r): self.r = r
    def filter(self, *a, **k): return self
    def first(self): return self.r

class DB:
    def __init__(self, task, ow):
        self.task, self.ow = task, ow
        self.added, self.commits = [], 0
    def query(self, cls):
        name = getattr(cls, "__name__", str(cls))
        return Q(self.ow if "Ownership" in name else self.task)
    def add(self, o): self.added.append(o)
    def flush(self): pass
    def commit(self): self.commits += 1

def run(event_type, payload, existing_ow=None, task=None):
    task = task or FakeTask("proj_TASK-01")
    db = DB(task, existing_ow)
    ns["_sync_task_progress_to_db"](db, "proj", "proj_TASK-01", event_type, payload)
    target = existing_ow if existing_ow is not None else (db.added[0] if db.added else None)
    return db, target

ns = dict(models=type("M", (), {"Task": FakeTask, "AgentTaskOwnership": FakeOwnership}),
          logger=type("L", (), {"warning": staticmethod(lambda *a, **k: print("  WARN:", a))}),
          Session=object, Dict=dict, Any=object, Optional=object)
exec(compile(mod, "cb", "exec"), ns)

# 1. task_started: existing ownership -> in_progress / 10
ow = FakeOwnership(status="to_do", task_data=None)
db, t = run("task_started", {"agent_id": "a1"}, existing_ow=ow)
check("started -> in_progress", t.status == "in_progress", t.status)
check("started progress 10", t.task_data.get("task_progress") == 10, str(t.task_data))
check("commit on change", db.commits == 1)

# 2. task_completed with platform_verified -> done / 100
ow2 = FakeOwnership(status="in_progress", task_data={"task_progress": 10})
db2, t2 = run("task_completed", {"platform_verified": True}, existing_ow=ow2)
check("verified completion -> done", t2.status == "done", t2.status)
check("verified progress 100", t2.task_data.get("task_progress") == 100, str(t2.task_data))

# 3. task_completed WITHOUT verification -> in_review / 75 (honest)
ow3 = FakeOwnership(status="in_progress", task_data=None)
db3, t3 = run("task_completed", {}, existing_ow=ow3)
check("unverified completion -> in_review", t3.status == "in_review", t3.status)
check("unverified progress 75", t3.task_data.get("task_progress") == 75, str(t3.task_data))

# 4. task_failed -> failed / 0
ow4 = FakeOwnership(status="in_progress", task_data=None)
db4, t4 = run("task_failed", {"error": "boom"}, existing_ow=ow4)
check("failed -> failed", t4.status == "failed", t4.status)
check("failed progress 0", t4.task_data.get("task_progress") == 0, str(t4.task_data))

# 5. no ownership row -> created
db5, t5 = run("task_completed", {"platform_verified": True}, existing_ow=None)
check("missing ownership created", len(db5.added) == 1)
check("created row done/100", t5.status == "done" and t5.task_data.get("task_progress") == 100,
      f"{t5.status} {t5.task_data}")

# 6. unknown task -> graceful no-op (no crash, no commit)
db6 = DB(None, None)
ns["_sync_task_progress_to_db"](db6, "proj", "ghost_TASK-99", "task_completed", {})
check("unknown task no-op", db6.commits == 0 and db6.added == [])

# 7. idempotent: same event twice -> second call commits nothing
ow7 = FakeOwnership(status="in_progress", task_data=None)
db7, t7 = run("task_completed", {"platform_verified": True}, existing_ow=ow7)
db7b, t7b = run("task_completed", {"platform_verified": True}, existing_ow=t7)
check("idempotent re-run no commit", db7b.commits == 0, str(db7b.commits))

print(f"\n{'='*50}\nRESULT: {PASS} passed, {FAIL} failed")
import sys
sys.exit(1 if FAIL else 0)
