import os
import sys
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.core.exceptions import EntityNotFoundError, PermissionDeniedError
from app.models.document import Document
from app.models.user import User
from app.repositories.document_repository import document_repository


class DocumentService:
    """Business logic service for document management, storage paths, and history."""

    UPLOAD_DIR = os.path.join(backend_dir, "uploads")

    def get_document_file_path(self, filename: str) -> str:
        safe_filename = os.path.basename(filename)
        file_path = os.path.join(self.UPLOAD_DIR, safe_filename)
        if not os.path.exists(file_path):
            raise EntityNotFoundError(f"Document '{safe_filename}' does not exist on disk.")
        return file_path

    def get_user_history(
        self, db: Session, current_user: User, skip: int = 0, limit: int = 100
    ) -> List[Document]:
        return document_repository.list_by_owner(db, current_user.id, skip=skip, limit=limit)

    def get_document_by_id(
        self, db: Session, doc_id: int, current_user: User
    ) -> Document:
        doc = document_repository.get_by_id_and_owner(db, doc_id, current_user.id)
        if not doc:
            raise EntityNotFoundError(f"Document #{doc_id} not found.")
        return doc

    def delete_user_document(
        self, db: Session, doc_id: int, current_user: User
    ) -> bool:
        doc = self.get_document_by_id(db, doc_id, current_user)
        # Attempt disk cleanup if file exists
        if doc.file_path and os.path.exists(doc.file_path):
            try:
                os.remove(doc.file_path)
            except Exception:
                pass
        document_repository.remove(db, id=doc.id)
        return True


document_service = DocumentService()

__all__ = ["DocumentService", "document_service"]
