"""
Bootstrap State Model - Persistent tracking of bootstrap execution
"""
from datetime import datetime
from sqlalchemy import Boolean, Column, Integer, String, DateTime, Text, JSON
from database import Base


class BootstrapState(Base):
    """Track bootstrap execution state per project"""
    __tablename__ = "bootstrap_states"

    id = Column(Integer, primary_key=True, index=True)
    project_token = Column(String, unique=True, index=True, nullable=False)
    
    # Bootstrap execution status
    status = Column(String, nullable=False, default="pending")  # pending, running, success, failed
    
    # Execution details
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    
    # Results
    master_note_id = Column(String, nullable=True)
    workspace_tree = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    bootstrap_branch = Column(String, nullable=True)  # The branch name where bootstrap scaffold was pushed
    
    # Metadata
    task_signature = Column(String, nullable=True)
    worker_signature = Column(String, nullable=True)
    
    # Tracking
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
