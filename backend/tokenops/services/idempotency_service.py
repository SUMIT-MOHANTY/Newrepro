from tokenops.repositories.idempotency import IdempotencyRepository

class IdempotencyService:
    def __init__(self, repo: IdempotencyRepository):
        self.repo = repo

    def create_processing_record(self, request_id: str | None) -> bool:
        """
        Returns True if the request should proceed (new request_id or no request_id).
        Returns False if the request has already been processed or is processing.
        """
        if not request_id:
            # If no request_id is provided, we can't guarantee idempotency, but we proceed.
            return True
            
        return self.repo.create_processing_record(request_id)

    def mark_completed(self, request_id: str | None) -> None:
        """
        Marks the record as COMPLETED if a request_id is present.
        """
        if request_id:
            self.repo.mark_completed(request_id)

    def get_status(self, request_id: str | None) -> str | None:
        if not request_id:
            return None
        return self.repo.get_status(request_id)
