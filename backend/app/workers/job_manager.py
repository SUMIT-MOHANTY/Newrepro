"""
Background Job Manager Worker
Tracks asynchronous analysis jobs, long-running agent tasks, and background job states.
"""

import logging
from typing import Any, Dict, Optional
import os
import sys

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

try:
    from analysis_job_manager import job_manager as raw_analysis_job_manager, JobStatus
except ImportError:
    raw_analysis_job_manager = None
    JobStatus = None

logger = logging.getLogger(__name__)


class AnalysisJobWorker:
    """
    Worker abstraction for tracking asynchronous analysis and generation jobs.
    """

    def __init__(self):
        self._mgr = raw_analysis_job_manager

    def create_job(self, user_id: int):
        """Create a new tracked background job."""
        if not self._mgr:
            raise RuntimeError("Analysis job manager is not initialized.")
        return self._mgr.create_job(user_id)

    def get_job(self, job_id: str):
        """Fetch an active or historical job by its UUID."""
        if not self._mgr:
            return None
        return self._mgr.get_job(job_id)

    def update_progress(self, job_id: str, progress: int, message: str):
        """Update job completion percentage (0-100) and user-facing status message."""
        if self._mgr:
            self._mgr.update_progress(job_id, progress, message)

    def update_stage(self, job_id: str, stage_name: str, stage_data: Dict[str, Any]):
        """Persist intermediate stage results (e.g. OCR complete, decomposition complete)."""
        if self._mgr:
            self._mgr.update_stage(job_id, stage_name, stage_data)

    def complete(self, job_id: str, result: Dict[str, Any]):
        """Mark job as successfully finished with final payload."""
        if self._mgr:
            self._mgr.set_completed(job_id, result)

    def fail(self, job_id: str, error: str):
        """Mark job as failed with error trace."""
        if self._mgr:
            self._mgr.set_failed(job_id, error)


analysis_job_worker = AnalysisJobWorker()
