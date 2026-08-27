from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Index
from database import Base
from datetime import datetime

class AdminAuditLog(Base):
    """
    Audit log for all Super Admin mutations.
    """
    __tablename__ = "admin_audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    admin_user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    actor_type = Column(String, index=True, nullable=False, default="SUPER_ADMIN") # SUPER_ADMIN or ORG_ADMIN
    action = Column(String, index=True, nullable=False) # e.g. "BLOCK_ORG", "APPROVE_PAYG", "UPDATE_PRICE", "ALLOCATE_TOKENS"
    target_entity = Column(String, nullable=False) # e.g. organization_name, model_name, user_id
    organization_name = Column(String, index=True, nullable=True) # The context organization
    request_id = Column(String, index=True, nullable=True) # Used for idempotent actions or traces
    details = Column(String, nullable=True) # JSON string with specifics
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
