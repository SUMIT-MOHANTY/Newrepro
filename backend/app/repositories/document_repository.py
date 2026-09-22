from typing import List, Optional
from sqlalchemy.orm import Session

from app.models.document import Document
from app.repositories.base import BaseRepository
from app.schemas.document import DocumentCreate


class DocumentRepository(BaseRepository[Document, DocumentCreate, DocumentCreate]):
    """Repository managing Document database persistence."""

    def __init__(self):
        super().__init__(Document)

    def list_by_owner(
        self, db: Session, owner_id: int, skip: int = 0, limit: int = 100
    ) -> List[Document]:
        return (
            db.query(Document)
            .filter(Document.owner_id == owner_id)
            .order_by(Document.upload_date.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def list_by_project_token(
        self, db: Session, project_token: str, owner_id: Optional[int] = None
    ) -> List[Document]:
        query = db.query(Document).filter(Document.project_token == project_token)
        if owner_id:
            query = query.filter(Document.owner_id == owner_id)
        return query.order_by(Document.upload_date.desc()).all()

    def get_by_id_and_owner(
        self, db: Session, doc_id: int, owner_id: int
    ) -> Optional[Document]:
        return (
            db.query(Document)
            .filter(Document.id == doc_id, Document.owner_id == owner_id)
            .first()
        )


document_repository = DocumentRepository()

__all__ = ["DocumentRepository", "document_repository"]
