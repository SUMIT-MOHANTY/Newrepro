"""
TokenOps — Idempotency model.

Table:
    idempotency_keys — Stores request IDs to prevent duplicate processing.
"""

from datetime import datetime

from sqlalchemy import Column, DateTime, String
from database import Base

class IdempotencyKey(Base):
    """
    Stores request IDs that have already been processed successfully.
    Used to guarantee exactly-once execution for token wallet operations.
    """
    __tablename__ = "idempotency_keys"

    request_id = Column(
        String, primary_key=True, index=True,
        comment="Unique identifier for a client request (e.g., UUID)"
    )
    created_at = Column(
        DateTime, nullable=False, default=datetime.utcnow,
        comment="When this request was processed"
    )
    status = Column(
        String, nullable=False, default="PROCESSING",
        comment="PROCESSING or COMPLETED"
    )

    def __repr__(self) -> str:
        return f"<IdempotencyKey request_id={self.request_id!r}>"
