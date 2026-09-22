from datetime import datetime
from typing import Dict, List, Optional, Tuple
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session, joinedload

from app.models.ticket import SupportTicket, TicketMessage
from app.repositories.base import BaseRepository
from app.schemas.ticket import TicketCreate, TicketUpdate
import models


class TicketRepository(BaseRepository[SupportTicket, TicketCreate, TicketUpdate]):
    """Repository managing SupportTicket and TicketMessage database persistence."""

    def __init__(self):
        super().__init__(SupportTicket)

    def get_by_code(self, db: Session, ticket_code: str) -> Optional[SupportTicket]:
        return db.query(SupportTicket).filter(SupportTicket.ticket_code == ticket_code).first()

    def get_with_relations(self, db: Session, ticket_id: int) -> Optional[SupportTicket]:
        return (
            db.query(SupportTicket)
            .options(
                joinedload(SupportTicket.created_by),
                joinedload(SupportTicket.assigned_to),
                joinedload(SupportTicket.resolved_by),
                joinedload(SupportTicket.messages).joinedload(TicketMessage.sender),
            )
            .filter(SupportTicket.id == ticket_id)
            .first()
        )

    def get_existing_codes_by_prefix(self, db: Session, prefix: str) -> List[str]:
        rows = db.query(SupportTicket.ticket_code).filter(
            SupportTicket.ticket_code.like(f"{prefix}%")
        ).all()
        return [row[0] for row in rows if row[0]]

    def list_tickets_scoped(
        self,
        db: Session,
        current_user: models.User,
        status_filter: Optional[str] = None,
        priority: Optional[str] = None,
        category: Optional[str] = None,
        cat_prefix: Optional[str] = None,
        search: Optional[str] = None,
    ) -> List[SupportTicket]:
        query = db.query(SupportTicket).options(
            joinedload(SupportTicket.created_by),
            joinedload(SupportTicket.assigned_to),
            joinedload(SupportTicket.resolved_by),
        )

        is_super = bool(getattr(current_user, "is_super_admin", False))
        is_org_adm = bool(getattr(current_user, "is_org_admin", False))
        user_org = (getattr(current_user, "organization_name", None) or "").strip().lower()

        # RBAC Filtering
        if is_super:
            pass
        elif is_org_adm and user_org:
            query = query.filter(
                or_(
                    SupportTicket.created_by_user_id == current_user.id,
                    and_(
                        func.lower(SupportTicket.organization_name) == user_org,
                        models.User.id == SupportTicket.created_by_user_id,
                        models.User.is_org_admin.is_(False),
                        models.User.is_super_admin.is_(False),
                    ),
                )
            )
        else:
            query = query.filter(SupportTicket.created_by_user_id == current_user.id)

        # Status filter
        if status_filter and status_filter.upper() != "ALL":
            query = query.filter(func.upper(SupportTicket.status) == status_filter.upper())

        # Priority filter
        if priority and priority.upper() != "ALL":
            query = query.filter(func.upper(SupportTicket.priority) == priority.upper())

        # Category filter
        if category and category.upper() != "ALL":
            conditions = [func.lower(SupportTicket.category) == category.lower()]
            if cat_prefix:
                conditions.append(SupportTicket.ticket_code.like(f"{cat_prefix}%"))
            query = query.filter(or_(*conditions))

        # Search query
        if search and search.strip():
            term = f"%{search.strip()}%"
            query = query.filter(
                or_(
                    SupportTicket.title.ilike(term),
                    SupportTicket.description.ilike(term),
                    SupportTicket.ticket_code.ilike(term),
                    SupportTicket.category.ilike(term),
                )
            )

        return query.order_by(SupportTicket.last_message_at.desc()).all()

    def add_message(
        self,
        db: Session,
        ticket: SupportTicket,
        sender_user_id: int,
        message: str,
        is_internal_note: bool = False,
        attachments: Optional[list] = None,
        is_admin_sender: bool = False,
    ) -> TicketMessage:
        msg = TicketMessage(
            ticket_id=ticket.id,
            sender_user_id=sender_user_id,
            message=message,
            is_internal_note=is_internal_note,
            attachments=attachments or None,
            created_at=datetime.utcnow(),
        )
        db.add(msg)

        ticket.last_message_at = datetime.utcnow()
        if is_admin_sender:
            ticket.unread_by_user = True
            ticket.unread_by_admin = False
        else:
            ticket.unread_by_admin = True
            ticket.unread_by_user = False

        db.commit()
        db.refresh(msg)
        return msg


ticket_repository = TicketRepository()

__all__ = ["TicketRepository", "ticket_repository"]
