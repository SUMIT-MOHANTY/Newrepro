"""
Analysis Job Manager - Tracks long-running AI analysis jobs
"""
import asyncio
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from enum import Enum

logger = logging.getLogger(__name__)


class JobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class AnalysisJob:
    """Represents a single analysis job"""
    
    def __init__(self, job_id: str, user_id: int):
        self.job_id = job_id
        self.user_id = user_id
        self.status = JobStatus.PENDING
        self.progress = 0
        self.progress_message = "Initializing analysis..."
        self.result: Optional[Dict[str, Any]] = None
        self.error: Optional[str] = None
        self.created_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()
        self.completed_at: Optional[datetime] = None
        
    def update_progress(self, progress: int, message: str):
        """Update job progress"""
        self.progress = progress
        self.progress_message = message
        self.updated_at = datetime.utcnow()
        
    def set_processing(self):
        """Mark job as processing"""
        self.status = JobStatus.PROCESSING
        self.updated_at = datetime.utcnow()
        
    def set_completed(self, result: Dict[str, Any]):
        """Mark job as completed with result"""
        self.status = JobStatus.COMPLETED
        self.result = result
        self.progress = 100
        self.progress_message = "Analysis complete!"
        self.completed_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()
        
    def set_failed(self, error: str):
        """Mark job as failed with error"""
        self.status = JobStatus.FAILED
        self.error = error
        self.completed_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert job to dictionary for API response"""
        return {
            "job_id": self.job_id,
            "status": self.status.value,
            "progress": self.progress,
            "progress_message": self.progress_message,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


class AnalysisJobManager:
    """Manages analysis jobs in memory"""
    
    def __init__(self):
        self._jobs: Dict[str, AnalysisJob] = {}
        self._cleanup_task: Optional[asyncio.Task] = None
        
    def create_job(self, job_id: str, user_id: int) -> AnalysisJob:
        """Create a new analysis job"""
        job = AnalysisJob(job_id, user_id)
        self._jobs[job_id] = job
        logger.info(f"Created analysis job {job_id} for user {user_id}")
        return job
        
    def get_job(self, job_id: str) -> Optional[AnalysisJob]:
        """Get job by ID"""
        return self._jobs.get(job_id)
        
    def get_user_job(self, job_id: str, user_id: int) -> Optional[AnalysisJob]:
        """Get job by ID, ensuring it belongs to the user"""
        job = self._jobs.get(job_id)
        if job and job.user_id == user_id:
            return job
        return None
        
    def delete_job(self, job_id: str):
        """Delete a job"""
        if job_id in self._jobs:
            del self._jobs[job_id]
            logger.info(f"Deleted analysis job {job_id}")
            
    async def cleanup_old_jobs(self, max_age_hours: int = 24):
        """
        Cleanup jobs older than max_age_hours.
        Keep completed/failed jobs for at least 1 hour to allow frontend to retrieve results.
        """
        cutoff = datetime.utcnow() - timedelta(hours=max_age_hours)
        completed_cutoff = datetime.utcnow() - timedelta(hours=1)  # Keep completed jobs for 1 hour minimum
        jobs_to_delete = []
        
        for job_id, job in self._jobs.items():
            # For completed/failed jobs, use shorter retention (1 hour)
            if job.status in [JobStatus.COMPLETED, JobStatus.FAILED]:
                if job.completed_at and job.completed_at < completed_cutoff:
                    jobs_to_delete.append(job_id)
            # For pending/processing jobs, use longer retention (24 hours)
            elif job.updated_at < cutoff:
                jobs_to_delete.append(job_id)
                
        for job_id in jobs_to_delete:
            self.delete_job(job_id)
            
        if jobs_to_delete:
            logger.info(f"Cleaned up {len(jobs_to_delete)} old analysis jobs")
            
    async def start_cleanup_task(self):
        """Start background cleanup task"""
        async def cleanup_loop():
            while True:
                try:
                    await asyncio.sleep(3600)  # Run every hour
                    await self.cleanup_old_jobs()
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Error in cleanup task: {e}")
                    
        self._cleanup_task = asyncio.create_task(cleanup_loop())
        logger.info("Started analysis job cleanup task")
        
    async def stop_cleanup_task(self):
        """Stop background cleanup task"""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            logger.info("Stopped analysis job cleanup task")


# Global job manager instance
_job_manager: Optional[AnalysisJobManager] = None


def get_job_manager() -> AnalysisJobManager:
    """Get the global job manager instance"""
    global _job_manager
    if _job_manager is None:
        _job_manager = AnalysisJobManager()
    return _job_manager


async def initialize_job_manager():
    """Initialize the job manager and start cleanup task"""
    manager = get_job_manager()
    await manager.start_cleanup_task()
    

async def shutdown_job_manager():
    """Shutdown the job manager"""
    manager = get_job_manager()
    await manager.stop_cleanup_task()
