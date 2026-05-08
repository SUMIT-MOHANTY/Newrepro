#!/usr/bin/env python3
"""
Task Planner for Incremental Development
Breaks down large requirements into manageable, executable tasks
"""

import json
import os
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone


class Task:
    """Represents a single development task"""
    
    def __init__(self, task_id: str, title: str, description: str, 
                 files_to_create: List[str], files_to_modify: List[str],
                 dependencies: List[str], priority: str, estimated_tokens: int):
        self.task_id = task_id
        self.title = title
        self.description = description
        self.files_to_create = files_to_create
        self.files_to_modify = files_to_modify
        self.dependencies = dependencies  # List of task_ids that must complete first
        self.priority = priority  # high, medium, low
        self.estimated_tokens = estimated_tokens
        self.status = "pending"  # pending, in_progress, completed, failed
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.completed_at = None
        self.error = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "title": self.title,
            "description": self.description,
            "files_to_create": self.files_to_create,
            "files_to_modify": self.files_to_modify,
            "dependencies": self.dependencies,
            "priority": self.priority,
            "estimated_tokens": self.estimated_tokens,
            "status": self.status,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "error": self.error
        }
    
    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'Task':
        task = Task(
            task_id=data["task_id"],
            title=data["title"],
            description=data["description"],
            files_to_create=data["files_to_create"],
            files_to_modify=data["files_to_modify"],
            dependencies=data["dependencies"],
            priority=data["priority"],
            estimated_tokens=data["estimated_tokens"]
        )
        task.status = data.get("status", "pending")
        task.created_at = data.get("created_at", datetime.now(timezone.utc).isoformat())
        task.completed_at = data.get("completed_at")
        task.error = data.get("error")
        return task


class TaskPlanner:
    """Manages task planning and execution for incremental development"""
    
    TASK_PLANNING_PROMPT = """You are an expert software architect breaking down a large requirement into manageable development tasks.

CRITICAL RULES:
1. Each task should be small enough to fit within 10,000 tokens of code generation
2. Tasks must be ordered by dependencies (foundation → features → integration)
3. Each task must specify EXACTLY which files it will create or modify
4. Provide detailed implementation instructions for each task
5. Consider the token limit - break large features into multiple tasks

USER REQUIREMENT:
{requirement}

EXISTING PROJECT CONTEXT:
{context}

Generate a task breakdown in this EXACT JSON format:
{{
  "project_summary": "Brief overview of what will be built",
  "total_estimated_files": 50,
  "tasks": [
    {{
      "task_id": "task_001",
      "title": "Setup Project Foundation",
      "description": "Detailed description of what this task accomplishes and HOW to implement it. Include specific technical details, file structures, and implementation approach.",
      "files_to_create": [
        "package.json",
        "vite.config.js",
        "index.html",
        "src/main.jsx"
      ],
      "files_to_modify": [],
      "dependencies": [],
      "priority": "high",
      "estimated_tokens": 2000
    }},
    {{
      "task_id": "task_002",
      "title": "Create Authentication Module",
      "description": "Implement user authentication with login, register, and password reset. Use JWT tokens, bcrypt for passwords, and create AuthContext for state management.",
      "files_to_create": [
        "src/contexts/AuthContext.jsx",
        "src/pages/auth/Login.jsx",
        "src/pages/auth/Register.jsx",
        "src/pages/auth/ForgotPassword.jsx"
      ],
      "files_to_modify": [
        "src/App.jsx"
      ],
      "dependencies": ["task_001"],
      "priority": "high",
      "estimated_tokens": 8000
    }}
  ]
}}

IMPORTANT:
- Break down the requirement into 5-15 tasks
- Each task should be independently testable
- Specify ALL files that will be created or modified
- Provide implementation details in the description
- Order tasks by logical dependencies
"""
    
    def __init__(self, workspace_dir: str, ai_caller):
        self.workspace_dir = workspace_dir
        self.ai_caller = ai_caller
        self.tasks_file = os.path.join(workspace_dir, ".vibecoding_tasks.json")
        self.context_file = os.path.join(workspace_dir, ".vibecoding_context.json")
        self.tasks: List[Task] = []
        self.context: Dict[str, Any] = {}
        self._load_state()
    
    def _load_state(self):
        """Load existing tasks and context from disk"""
        if os.path.exists(self.tasks_file):
            with open(self.tasks_file, 'r') as f:
                data = json.load(f)
                self.tasks = [Task.from_dict(t) for t in data]
        
        if os.path.exists(self.context_file):
            with open(self.context_file, 'r') as f:
                self.context = json.load(f)
    
    def _save_state(self):
        """Save tasks and context to disk"""
        with open(self.tasks_file, 'w') as f:
            json.dump([t.to_dict() for t in self.tasks], f, indent=2)
        
        with open(self.context_file, 'w') as f:
            json.dump(self.context, f, indent=2)
    
    def generate_task_plan(self, requirement: str) -> Dict[str, Any]:
        """
        Generate a task breakdown for the given requirement
        Returns: {
            "project_summary": str,
            "total_tasks": int,
            "tasks": List[Task]
        }
        """
        # Build context from existing files
        context = self._build_project_context()
        
        # Call AI to generate task plan
        prompt = self.TASK_PLANNING_PROMPT.format(
            requirement=requirement,
            context=json.dumps(context, indent=2)
        )
        
        messages = [
            {"role": "system", "content": "You are an expert software architect."},
            {"role": "user", "content": prompt}
        ]
        
        response = self.ai_caller(messages, temperature=0.3, show_thinking=False)
        
        # Parse response
        try:
            # Extract JSON from response
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                plan_data = json.loads(json_match.group(0))
            else:
                raise ValueError("No JSON found in response")
            
            # Create Task objects
            tasks = []
            for task_data in plan_data.get("tasks", []):
                task = Task(
                    task_id=task_data["task_id"],
                    title=task_data["title"],
                    description=task_data["description"],
                    files_to_create=task_data.get("files_to_create", []),
                    files_to_modify=task_data.get("files_to_modify", []),
                    dependencies=task_data.get("dependencies", []),
                    priority=task_data.get("priority", "medium"),
                    estimated_tokens=task_data.get("estimated_tokens", 5000)
                )
                tasks.append(task)
            
            self.tasks = tasks
            self.context["project_summary"] = plan_data.get("project_summary", "")
            self.context["requirement"] = requirement
            self._save_state()
            
            return {
                "project_summary": plan_data.get("project_summary", ""),
                "total_tasks": len(tasks),
                "tasks": [t.to_dict() for t in tasks]
            }
        
        except Exception as e:
            raise Exception(f"Failed to parse task plan: {e}\nResponse: {response[:500]}")
    
    def _build_project_context(self) -> Dict[str, Any]:
        """Build context of what's already been built"""
        context = {
            "completed_tasks": [],
            "existing_files": [],
            "file_summaries": {}
        }
        
        # Get completed tasks
        for task in self.tasks:
            if task.status == "completed":
                context["completed_tasks"].append({
                    "task_id": task.task_id,
                    "title": task.title,
                    "files_created": task.files_to_create,
                    "files_modified": task.files_to_modify
                })
        
        # List existing files
        if os.path.exists(self.workspace_dir):
            for root, dirs, files in os.walk(self.workspace_dir):
                # Skip node_modules, .git, etc.
                dirs[:] = [d for d in dirs if d not in ['node_modules', '.git', 'dist', 'build', '__pycache__']]
                
                for file in files:
                    if file.startswith('.vibecoding'):
                        continue
                    rel_path = os.path.relpath(os.path.join(root, file), self.workspace_dir)
                    context["existing_files"].append(rel_path)
        
        return context
    
    def get_executable_tasks(self) -> List[Task]:
        """Get tasks that can be executed now (dependencies met)"""
        executable = []
        completed_ids = {t.task_id for t in self.tasks if t.status == "completed"}
        
        for task in self.tasks:
            if task.status != "pending":
                continue
            
            # Check if all dependencies are completed
            deps_met = all(dep_id in completed_ids for dep_id in task.dependencies)
            if deps_met:
                executable.append(task)
        
        # Sort by priority
        priority_order = {"high": 0, "medium": 1, "low": 2}
        executable.sort(key=lambda t: priority_order.get(t.priority, 1))
        
        return executable
    
    def get_task_by_id(self, task_id: str) -> Optional[Task]:
        """Get a specific task by ID"""
        for task in self.tasks:
            if task.task_id == task_id:
                return task
        return None
    
    def mark_task_completed(self, task_id: str):
        """Mark a task as completed"""
        task = self.get_task_by_id(task_id)
        if task:
            task.status = "completed"
            task.completed_at = datetime.now(timezone.utc).isoformat()
            self._save_state()
    
    def mark_task_failed(self, task_id: str, error: str):
        """Mark a task as failed"""
        task = self.get_task_by_id(task_id)
        if task:
            task.status = "failed"
            task.error = error
            self._save_state()
    
    def get_progress_summary(self) -> Dict[str, Any]:
        """Get overall progress summary"""
        total = len(self.tasks)
        completed = sum(1 for t in self.tasks if t.status == "completed")
        failed = sum(1 for t in self.tasks if t.status == "failed")
        pending = sum(1 for t in self.tasks if t.status == "pending")
        
        return {
            "total_tasks": total,
            "completed": completed,
            "failed": failed,
            "pending": pending,
            "progress_percentage": int((completed / total * 100)) if total > 0 else 0
        }
