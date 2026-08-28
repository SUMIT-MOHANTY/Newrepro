from sqlalchemy.orm import Session
from sqlalchemy import text
from tokenops.models.idempotency import IdempotencyKey

from sqlalchemy.exc import IntegrityError
import datetime

class IdempotencyRepository:
    def __init__(self, session: Session):
        self.session = session

    def create_processing_record(self, request_id: str) -> bool:
        """
        Atomically attempts to insert a PROCESSING record using the database unique constraint on request_id.
        Returns True if this is the first execution claiming the request_id.
        Returns False if a duplicate request_id is detected via IntegrityError collision.
        """
        if not request_id:
            return True

        now = datetime.datetime.utcnow()

        # Isolate the atomic INSERT within a nested savepoint
        savepoint = self.session.begin_nested()
        try:
            stmt = text("INSERT INTO idempotency_keys (request_id, created_at, status) VALUES (:req, :now, 'PROCESSING')")
            self.session.execute(stmt, {"req": request_id, "now": now})
            savepoint.commit()
            return True
        except IntegrityError as e:
            # Roll back only the nested savepoint, preserving the caller's root transaction
            savepoint.rollback()
            err_msg = str(e).lower()
            if (
                "idempotency_keys" in err_msg
                or "unique" in err_msg
                or "primary" in err_msg
                or "duplicate" in err_msg
                or "constraint" in err_msg
                or "request_id" in err_msg
            ):
                return False
            # Re-raise any unrelated integrity error
            raise e

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
