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
            with open(self.task_config_path, 'w', encoding='utf-8') as f:
                json.dump([t.to_dict() for t in self.tasks.values()], f, indent=4)
        except Exception as e:
            logger.error(f"Failed to save tasks to {self.task_config_path}: {e}")

    def get_ready_tasks(self) -> List[Task]:
        ready_tasks = []
        for task in self.tasks.values():
            if task.status == TaskStatus.PENDING:
                can_run = True
                for dep in task.depends_on:
                    if dep in self.tasks and self.tasks[dep].status != TaskStatus.COMPLETED:
                        can_run = False
                        break
                if can_run:
                    ready_tasks.append(task)
        return ready_tasks

    def update_task_status(self, task_id: str, status: TaskStatus):
        if task_id in self.tasks:
            self.tasks[task_id].status = status
            self.save_tasks()

    def get_execution_order(self) -> List[List[Task]]:
        """Returns lists of tasks that can be executed in parallel (topological sort)"""
        in_degree = {t_id: 0 for t_id in self.tasks}
        graph = {t_id: [] for t_id in self.tasks}
        
        for t_id, task in self.tasks.items():
            for dep in task.depends_on:
                if dep in graph:
                    graph[dep].append(t_id)
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
