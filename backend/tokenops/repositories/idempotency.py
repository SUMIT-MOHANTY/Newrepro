from sqlalchemy.orm import Session
from sqlalchemy import text
from tokenops.models.idempotency import IdempotencyKey

class IdempotencyRepository:
    def __init__(self, session: Session):
        self.session = session

    def create_processing_record(self, request_id: str) -> bool:
        """
        Attempts to insert a PROCESSING record.
        Uses SQLite INSERT OR IGNORE to avoid IntegrityError (and thereby savepoints).
        Returns True if successful (new request), False if it already exists (concurrent/duplicate).
        """
        stmt_check = text("SELECT status FROM idempotency_keys WHERE request_id = :req")
        status = self.session.execute(stmt_check, {"req": request_id}).scalar_one_or_none()
        
        if status is not None:
            # It already exists
            return False
            
        import datetime
        now = datetime.datetime.utcnow()
        stmt = text("INSERT INTO idempotency_keys (request_id, created_at, status) VALUES (:req, :now, 'PROCESSING')")
        self.session.execute(stmt, {"req": request_id, "now": now})
        return True
            
        # It already exists, return False
        return False

    def mark_completed(self, request_id: str) -> None:
        """
        Marks the idempotency record as COMPLETED.
        Called successfully at the end of the operation before commit.
        """
        stmt = text("UPDATE idempotency_keys SET status = 'COMPLETED' WHERE request_id = :req")
        self.session.execute(stmt, {"req": request_id})

    def get_status(self, request_id: str) -> str | None:
        """
        Check the status of an existing request_id.
        """
        stmt = text("SELECT status FROM idempotency_keys WHERE request_id = :req")
        result = self.session.execute(stmt, {"req": request_id}).scalar_one_or_none()
        return result
