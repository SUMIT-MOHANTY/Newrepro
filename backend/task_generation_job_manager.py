"""
Task Generation Job Manager - Tracks progressive per-sprint task generation state & polling status.
"""
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class TaskGenerationJob:
    """Represents a progressive task generation job for a project_token."""

    def __init__(self, project_token: str):
        self.project_token = project_token
        self.status = "generating"  # "generating" | "completed" | "failed"
        self.current_sprint = 1
        self.current_sprint_name = "Sprint 1: Frontend Prototype & Bootstrap"
        self.total_sprints = 4
        self.progress_percent = 10
        self.status_message = "Initializing task generation..."
        self.released_tasks: List[Dict[str, Any]] = []
        self.released_sprints: List[Dict[str, Any]] = []
        self.error: Optional[str] = None
        self.created_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()
        self.polling_interval_seconds = 7

    def set_total_sprints(self, total_sprints: int):
        """Set dynamic total sprints determined by AI."""
        self.total_sprints = max(1, total_sprints)
        self.status_message = f"AI planned {self.total_sprints} sprints based on BRD scope and project type."
        self.updated_at = datetime.utcnow()
        logger.info(f"[{self.project_token}] AI dynamic sprint planning set total sprints = {self.total_sprints}")

    def update_chunk_status(self, current_chunk: int, total_chunks: int):
        """Update job status during chunked BRD document analysis."""
        self.status_message = f"Analyzing BRD document chunks ({current_chunk} of {total_chunks})..."
        self.progress_percent = min(15, int((current_chunk / max(1, total_chunks)) * 15))
        self.updated_at = datetime.utcnow()
        logger.info(f"[{self.project_token}] Chunked BRD analysis progress: chunk {current_chunk}/{total_chunks}")

    def update_sprint_start(self, sprint_num: int, sprint_name: str):
        """Update job when a new sprint generation starts."""
        self.status = "generating"
        self.current_sprint = sprint_num
        self.current_sprint_name = sprint_name
        self.progress_percent = min(95, int(((sprint_num - 1) / max(1, self.total_sprints)) * 80) + 15)
        self.status_message = f"Generating Sprint {sprint_num} of {self.total_sprints}: {sprint_name}..."
        self.updated_at = datetime.utcnow()
        logger.info(f"[{self.project_token}] Sprint {sprint_num} generation started: {sprint_name}")

    def add_released_sprint(self, sprint_num: int, sprint_name: str, tasks: List[Dict[str, Any]]):
        """Record released sprint tasks."""
        sprint_info = {
            "sprint_number": sprint_num,
            "sprint_name": sprint_name,
            "task_count": len(tasks),
            "released_at": datetime.utcnow().isoformat()
        }
        self.released_sprints.append(sprint_info)
        self.released_tasks.extend(tasks)
        self.progress_percent = int((sprint_num / self.total_sprints) * 90)
        self.status_message = f"Sprint {sprint_num} of {self.total_sprints} complete ({len(tasks)} tasks released)."
        self.updated_at = datetime.utcnow()
        logger.info(f"[{self.project_token}] Released Sprint {sprint_num} with {len(tasks)} tasks")

    def set_completed(self, final_tasks: List[Dict[str, Any]]):
        """Mark job as completed."""
        self.status = "completed"
        self.progress_percent = 100
        self.status_message = f"Task generation complete! Total {len(final_tasks)} tasks generated across {self.total_sprints} sprints."
        self.released_tasks = final_tasks
        self.updated_at = datetime.utcnow()
        logger.info(f"[{self.project_token}] Task generation job completed cleanly.")

    def set_failed(self, error_message: str):
        """Mark job as failed."""
        self.status = "failed"
        self.error = error_message
        err_upper = str(error_message).upper()
        if "TOKEN_EXHAUSTED" in err_upper or "402" in err_upper:
            self.status_message = "Task generation failed: Token quota exhausted. Please allocate more tokens."
        elif "PAYG_HARD_LIMIT_REACHED" in err_upper:
            self.status_message = "Task generation failed: Spending limit reached."
        else:
            self.status_message = f"Task generation failed: {error_message}"
        self.updated_at = datetime.utcnow()
        logger.error(f"[{self.project_token}] Task generation job failed: {error_message}")

    def to_dict(self) -> Dict[str, Any]:
        """Convert job to dict for frontend polling API endpoint."""
        return {
            "project_token": self.project_token,
            "is_generating": self.status == "generating",
            "status": self.status,
            "current_sprint": self.current_sprint,
            "current_sprint_name": self.current_sprint_name,
            "total_sprints": self.total_sprints,
            "progress_percent": self.progress_percent,
            "status_message": self.status_message,
            "tasks_count": len(self.released_tasks),
            "released_sprints": self.released_sprints,
            "released_tasks": self.released_tasks,
            "polling_interval_seconds": self.polling_interval_seconds,
            "error": self.error,
            "updated_at": self.updated_at.isoformat()
        }


class TaskGenerationJobManager:
    """Singleton manager for active task generation jobs."""

    def __init__(self):
        self._jobs: Dict[str, TaskGenerationJob] = {}

    def create_job(self, project_token: str) -> TaskGenerationJob:
        job = TaskGenerationJob(project_token)
        self._jobs[project_token] = job
        return job

    def get_job(self, project_token: str) -> Optional[TaskGenerationJob]:
        return self._jobs.get(project_token)

    def remove_job(self, project_token: str):
        self._jobs.pop(project_token, None)


# Global singleton instance
_task_generation_job_manager: Optional[TaskGenerationJobManager] = None


def get_task_generation_job_manager() -> TaskGenerationJobManager:
    global _task_generation_job_manager
    if _task_generation_job_manager is None:
        _task_generation_job_manager = TaskGenerationJobManager()
    return _task_generation_job_manager
