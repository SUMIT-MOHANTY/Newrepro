import json
import logging
import os
from typing import List, Dict, Set, Any
from enum import Enum

logger = logging.getLogger(__name__)

class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

class Task:
    def __init__(self, data: Dict[str, Any]):
        self.task_id = str(data.get("task_id") or data.get("id") or data.get("db_id") or "")
        self.title = data.get("title", "")
        self.description = data.get("description", "")
        self.lane = (data.get("lane") or "backend").lower()
        self.subtasks = data.get("subtasks", [])
        
        # Robustly parse depends_on or linked_tasks
        raw_deps = data.get("depends_on") or data.get("linked_tasks") or []
        if isinstance(raw_deps, str):
            try:
                raw_deps = json.loads(raw_deps)
            except Exception:
                raw_deps = [raw_deps]
        if not isinstance(raw_deps, list):
            raw_deps = []
        self.depends_on = [str(d) for d in raw_deps if d]
        
        raw_status = str(data.get("status", "pending")).lower()
        try:
            self.status = TaskStatus(raw_status)
        except ValueError:
            self.status = TaskStatus.PENDING

    def to_dict(self):
        return {
            "task_id": self.task_id,
            "title": self.title,
            "description": self.description,
            "lane": self.lane,
            "subtasks": self.subtasks,
            "depends_on": self.depends_on,
            "status": self.status.value
        }

class DAGScheduler:
    """DAG-based task scheduler"""
    def __init__(self, task_config_path: str, tasks_data: List[Dict[str, Any]] | None = None):
        self.task_config_path = task_config_path
        self.tasks: Dict[str, Task] = {}
        self._original_config: Dict[str, Any] = {}
        if tasks_data:
            for t in tasks_data:
                task = Task(t)
                if task.task_id:
                    self.tasks[task.task_id] = task
        else:
            self._load_tasks()

    def _load_tasks(self):
        try:
            if not os.path.exists(self.task_config_path):
                return
            with open(self.task_config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, dict):
                    self._original_config = data
                    task_items = data.get("tasks", [])
                elif isinstance(data, list):
                    task_items = data
                else:
                    task_items = []
                for t in task_items:
                    task = Task(t)
                    if task.task_id:
                        self.tasks[task.task_id] = task
        except Exception as e:
            logger.error(f"Failed to load tasks from {self.task_config_path}: {e}")

    def save_tasks(self):
        try:
            task_list = [t.to_dict() for t in self.tasks.values()]
            payload: Any = task_list
            if isinstance(self._original_config, dict) and self._original_config:
                payload = dict(self._original_config)
                payload["tasks"] = task_list
            elif os.path.exists(self.task_config_path):
                try:
                    with open(self.task_config_path, 'r', encoding='utf-8') as f:
                        existing = json.load(f)
                    if isinstance(existing, dict):
                        payload = existing
                        payload["tasks"] = task_list
                except Exception:
                    pass

            with open(self.task_config_path, 'w', encoding='utf-8') as f:
                json.dump(payload, f, indent=4)
        except Exception as e:
            logger.error(f"Failed to save tasks to {self.task_config_path}: {e}")

    def _find_task_by_id(self, dep_id: str) -> Task | None:
        """Find task by exact ID or short ID suffix (e.g. 'TASK-00' matching '<uuid>_TASK-00')."""
        if not dep_id:
            return None
        if dep_id in self.tasks:
            return self.tasks[dep_id]
        clean_dep = dep_id.strip()
        for t_id, task in self.tasks.items():
            if t_id == clean_dep or t_id.endswith(f"_{clean_dep}") or t_id.endswith(f"-{clean_dep}"):
                return task
        return None

    def _is_external_dependency_completed(self, dep_id: str) -> bool:
        """Check if a dependency assigned to another agent in the swarm has completed."""
        clean_dep = dep_id.strip()
        workspace_agent_dir = os.path.dirname(self.task_config_path) if self.task_config_path else "/workspace/.agent"
        if not os.path.exists(workspace_agent_dir):
            return False
        try:
            for fname in os.listdir(workspace_agent_dir):
                fpath = os.path.join(workspace_agent_dir, fname)
                if not os.path.isfile(fpath):
                    continue
                # Check task_summary files first (highest fidelity)
                if fname.startswith("task_summary") and fname.endswith(".json"):
                    try:
                        with open(fpath, "r", encoding="utf-8") as f:
                            s_data = json.load(f)
                            tasks_map = s_data.get("tasks") or s_data.get("task_results") or {}
                            for t_id, res in tasks_map.items():
                                if t_id == clean_dep or t_id.endswith(f"_{clean_dep}") or t_id.endswith(f"-{clean_dep}"):
                                    if isinstance(res, dict) and str(res.get("status", "")).lower() in ("completed", "done", "passed"):
                                        return True
                                    elif isinstance(res, str) and res.lower() in ("completed", "done", "passed"):
                                        return True
                    except Exception:
                        pass
                # Check sibling task_config files
                elif fname.startswith("task_config_") and fname.endswith(".json") and fpath != self.task_config_path:
                    try:
                        with open(fpath, "r", encoding="utf-8") as f:
                            c_data = json.load(f)
                            items = c_data.get("tasks", []) if isinstance(c_data, dict) else (c_data if isinstance(c_data, list) else [])
                            for item in items:
                                if isinstance(item, dict):
                                    t_id = str(item.get("task_id") or item.get("id") or "")
                                    if t_id == clean_dep or t_id.endswith(f"_{clean_dep}") or t_id.endswith(f"-{clean_dep}"):
                                        if str(item.get("status", "")).lower() in ("completed", "done", "passed"):
                                            return True
                    except Exception:
                        pass
        except Exception:
            pass
        return False

    def get_ready_tasks(self) -> List[Task]:
        ready_tasks = []
        for task in self.tasks.values():
            if task.status == TaskStatus.PENDING:
                can_run = True
                for dep in task.depends_on:
                    dep_task = self._find_task_by_id(dep)
                    if dep_task:
                        if dep_task.status != TaskStatus.COMPLETED:
                            can_run = False
                            break
                    else:
                        # Dependency is external (assigned to another agent in the swarm)
                        if not self._is_external_dependency_completed(dep):
                            can_run = False
                            break
                if can_run:
                    ready_tasks.append(task)
        return ready_tasks

    def update_task_status(self, task_id: str, status: TaskStatus):
        target_task = self._find_task_by_id(task_id)
        if target_task:
            target_task.status = status
            self.save_tasks()

    def get_execution_order(self) -> List[List[Task]]:
        """Returns lists of tasks that can be executed in parallel (topological sort)"""
        in_degree = {t_id: 0 for t_id in self.tasks}
        graph = {t_id: [] for t_id in self.tasks}
        
        for t_id, task in self.tasks.items():
            for dep in task.depends_on:
                dep_task = self._find_task_by_id(dep)
                if dep_task and dep_task.task_id in graph:
                    graph[dep_task.task_id].append(t_id)
                    in_degree[t_id] += 1
                    
        execution_batches = []
        queue = [t_id for t_id, deg in in_degree.items() if deg == 0]
        
        while queue:
            current_batch = []
            next_queue = []
            for t_id in queue:
                current_batch.append(self.tasks[t_id])
                for neighbor in graph[t_id]:
                    in_degree[neighbor] -= 1
                    if in_degree[neighbor] == 0:
                        next_queue.append(neighbor)
            execution_batches.append(current_batch)
            queue = next_queue
            
        return execution_batches
