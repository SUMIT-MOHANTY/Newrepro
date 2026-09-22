from datetime import datetime
from typing import Dict, List, Optional
from sqlalchemy.orm import Session

from app.core.exceptions import BusinessRuleViolationError, EntityNotFoundError, PermissionDeniedError
from app.models.ticket import SupportTicket, TicketMessage
from app.repositories.ticket_repository import ticket_repository
from app.schemas.ticket import (
    TicketCreate,
    TicketMessageCreate,
    TicketMessageResponse,
    TicketResolvePayload,
    TicketResponse,
    TicketSenderInfo,
    TicketStatsResponse,
    TicketUpdate,
)
import models


class TicketService:
    """Business logic service for ServiceNow-compliant support ticket workflows."""

    VALID_STATUSES = {"OPEN", "IN_PROGRESS", "AWAITING_INFO", "RESOLVED", "CLOSED"}
    VALID_PRIORITIES = {"LOW", "MEDIUM", "HIGH", "URGENT"}

    @staticmethod
    def get_servicenow_prefix(category_or_type: Optional[str]) -> str:
        """Maps user-friendly category to ServiceNow prefix: REQ, INC, INQ, CHG, PRB."""
        if not category_or_type:
            return "REQ"
        norm = str(category_or_type).strip().upper()

        if norm in ("REQ", "INC", "INQ", "CHG", "PRB"):
            return norm

        if any(k in norm for k in ("TOKEN", "CAPACITY", "QUOTA", "ACCESS", "SERVICE REQUEST", "ALLOCATION", "BILLING", "FEATURE REQUEST")):
            return "REQ"
        if any(k in norm for k in ("ISSUE", "ERROR", "BUG", "TECHNICAL", "INCIDENT", "OUTAGE", "FAIL", "BROKEN")):
            return "INC"
        if any(k in norm for k in ("QUESTION", "INQUIRY", "HELP", "HOW", "GUIDE", "GENERAL")):
            return "INQ"
        if any(k in norm for k in ("CHANGE", "CONFIG", "MODEL", "INTEGRATION", "ENV")):
            return "CHG"
        if "PROBLEM" in norm:
            return "PRB"

        return "REQ"

    @classmethod
    def generate_ticket_code(cls, db: Session, category_or_type: Optional[str] = None) -> str:
        """
        Generates unique ServiceNow-style ticket code starting from the beginning (0000001):
        {PREFIX}{7-digit sequential number}, e.g. REQ0000001, INC0000001, INQ0000001.
        """
        prefix = cls.get_servicenow_prefix(category_or_type)
        existing_codes = ticket_repository.get_existing_codes_by_prefix(db, prefix)

        max_num = 0  # Starts from the beginning: first ticket becomes 0000001
        for raw_code in existing_codes:
            num_part = (raw_code or "")[len(prefix):].lstrip("-")
            if num_part.isdigit():
                val = int(num_part)
                if val > max_num:
                    max_num = val

        next_num = max_num + 1
        while True:
            candidate_code = f"{prefix}{next_num:07d}"
            exists = ticket_repository.get_by_code(db, candidate_code)
            if not exists:
                return candidate_code
            next_num += 1

    @classmethod
    def user_to_sender_info(cls, user: Optional[models.User]) -> Optional[TicketSenderInfo]:
        if not user:
            return None
        is_super = bool(getattr(user, "is_super_admin", False))
        is_org_adm = bool(getattr(user, "is_org_admin", False))
        role_name = "Super Admin" if is_super else ("Org Admin" if is_org_adm else "User")
        return TicketSenderInfo(
            id=user.id,
            email=user.email,
            role_name=role_name,
            is_super_admin=is_super,
            is_org_admin=is_org_adm,
            organization_name=user.organization_name,
        )

    @classmethod
    def build_ticket_response(
        cls, ticket: SupportTicket, current_user: models.User, include_messages: bool = False
    ) -> TicketResponse:
        is_super = bool(getattr(current_user, "is_super_admin", False))
        is_org_adm = bool(getattr(current_user, "is_org_admin", False))
        is_admin = is_super or is_org_adm
        is_creator = ticket.created_by_user_id == current_user.id

        unread = ticket.unread_by_admin if is_admin else ticket.unread_by_user
        can_change_status = is_admin or is_creator
        can_resolve = is_admin or is_creator

        messages_out: List[TicketMessageResponse] = []
        if include_messages and hasattr(ticket, "messages") and ticket.messages:
            for m in ticket.messages:
                if m.is_internal_note and not is_admin:
                    continue
                messages_out.append(
                    TicketMessageResponse(
                        id=m.id,
                        ticket_id=m.ticket_id,
                        sender_user_id=m.sender_user_id,
                        sender=cls.user_to_sender_info(m.sender),
                        message=m.message,
                        is_internal_note=m.is_internal_note,
                        attachments=m.attachments or None,
                        created_at=m.created_at,
                    )
                )

        return TicketResponse(
            id=ticket.id,
            ticket_code=ticket.ticket_code,
            title=ticket.title,
            description=ticket.description,
            category=ticket.category,
            priority=ticket.priority,
            status=ticket.status,
            organization_name=ticket.organization_name,
            created_by_user_id=ticket.created_by_user_id,
            created_by=cls.user_to_sender_info(ticket.created_by),
            assigned_to_user_id=ticket.assigned_to_user_id,
            assigned_to=cls.user_to_sender_info(ticket.assigned_to),
            resolution_summary=ticket.resolution_summary,
            resolved_by_user_id=ticket.resolved_by_user_id,
            resolved_by=cls.user_to_sender_info(ticket.resolved_by),
            resolved_at=ticket.resolved_at,
            last_message_at=ticket.last_message_at,
            unread=unread,
            message_count=len(messages_out) if include_messages else 0,
            messages=messages_out,
            can_change_status=can_change_status,
            can_resolve=can_resolve,
            created_at=ticket.created_at,
            updated_at=ticket.updated_at,
        )

    def create_ticket(
        self, db: Session, payload: TicketCreate, current_user: models.User
    ) -> SupportTicket:
        if payload.priority.upper() not in self.VALID_PRIORITIES:
            raise BusinessRuleViolationError(
                f"Invalid priority '{payload.priority}'. Valid: {list(self.VALID_PRIORITIES)}"
            )

        user_org = (getattr(current_user, "organization_name", None) or "").strip() or None
        ticket_code = self.generate_ticket_code(db, payload.category.strip() if payload.category else None)

        ticket = SupportTicket(
            ticket_code=ticket_code,
            title=payload.title.strip(),
            description=payload.description.strip(),
            category=payload.category.strip(),
            priority=payload.priority.upper(),
            status="OPEN",
            organization_name=user_org,
            created_by_user_id=current_user.id,
            unread_by_admin=True,
            unread_by_user=False,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            last_message_at=datetime.utcnow(),
        )
        db.add(ticket)
        db.commit()
        db.refresh(ticket)
        return ticket

    def resolve_ticket(
        self, db: Session, ticket_id: int, payload: TicketResolvePayload, current_user: models.User
    ) -> SupportTicket:
        ticket = ticket_repository.get_with_relations(db, ticket_id)
        if not ticket:
            raise EntityNotFoundError(f"Support ticket #{ticket_id} not found.")

        is_super = bool(getattr(current_user, "is_super_admin", False))
        is_org_adm = bool(getattr(current_user, "is_org_admin", False))
        if not (is_super or is_org_adm or ticket.created_by_user_id == current_user.id):
            raise PermissionDeniedError("You do not have permission to resolve this ticket.")

        ticket.status = "RESOLVED"
        ticket.resolved_by_user_id = current_user.id
        ticket.resolved_at = datetime.utcnow()
        ticket.updated_at = datetime.utcnow()
        ticket.last_message_at = datetime.utcnow()
        if payload.resolution_summary and payload.resolution_summary.strip():
            ticket.resolution_summary = payload.resolution_summary.strip()

        db.commit()
        db.refresh(ticket)
        return ticket


ticket_service = TicketService()

__all__ = ["TicketService", "ticket_service"]
