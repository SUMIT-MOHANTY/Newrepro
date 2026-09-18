import asyncio
import json
import logging
import random
import string
from datetime import datetime
from typing import Annotated, Dict, List, Optional

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

import auth
import models
import schemas
from database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tickets", tags=["Support Tickets"])


# ── WebSocket Manager for Live Ticket Communication ─────────────────────────

class TicketConnectionManager:
    """Tracks active WebSockets per ticket and per hub for instant multi-user updates."""

    def __init__(self):
        self.active_connections: Dict[int, List[WebSocket]] = {}
        # Map websocket to user metadata dict for scoped hub broadcasting:
        # {websocket: {"user_id": int, "email": str, "is_super_admin": bool, "is_org_admin": bool, "organization_name": Optional[str]}}
        self.hub_connections: Dict[WebSocket, dict] = {}

    async def connect(self, websocket: WebSocket, ticket_id: int):
        await websocket.accept()
        if ticket_id not in self.active_connections:
            self.active_connections[ticket_id] = []
        self.active_connections[ticket_id].append(websocket)
        logger.info(f"[TicketWS] Connected to ticket #{ticket_id}. Total listeners: {len(self.active_connections[ticket_id])}")

    def disconnect(self, websocket: WebSocket, ticket_id: int):
        if ticket_id in self.active_connections:
            if websocket in self.active_connections[ticket_id]:
                self.active_connections[ticket_id].remove(websocket)
            if not self.active_connections[ticket_id]:
                del self.active_connections[ticket_id]
        logger.info(f"[TicketWS] Disconnected from ticket #{ticket_id}")

    async def connect_hub(self, websocket: WebSocket, user_meta: dict):
        await websocket.accept()
        self.hub_connections[websocket] = user_meta
        logger.info(f"[TicketWS] Connected to Hub WS (user={user_meta.get('email')}). Total listeners: {len(self.hub_connections)}")

    def disconnect_hub(self, websocket: WebSocket):
        if websocket in self.hub_connections:
            del self.hub_connections[websocket]
        logger.info(f"[TicketWS] Disconnected from Hub WS. Remaining: {len(self.hub_connections)}")

    async def broadcast_to_ticket(self, ticket_id: int, message_payload: dict):
        """Broadcasts event payload to all clients viewing the ticket."""
        if ticket_id not in self.active_connections:
            return
        dead_connections = []
        for connection in list(self.active_connections[ticket_id]):
            try:
                await connection.send_json(message_payload)
            except Exception as e:
                logger.warning(f"[TicketWS] Error broadcasting to connection: {e}")
                dead_connections.append(connection)
        for dead in dead_connections:
            self.disconnect(dead, ticket_id)

    async def broadcast_hub(self, event_payload: dict, ticket_meta: Optional[dict] = None):
        """
        Broadcasts event payload to authorized hub clients based on RBAC rules:
        - If ticket_meta is provided:
          - Super Admin receives all events.
          - Creator of ticket always receives events for their ticket.
          - If ticket was raised by Org Admin: Only Super Admin and creator receive it (no other users/org admins).
          - If ticket was raised by Regular User: Org Admins of that org and Super Admin receive it (no other users).
        """
        dead_connections = []
        for connection, user_meta in list(self.hub_connections.items()):
            if ticket_meta:
                can_see = False
                is_super = user_meta.get("is_super_admin", False)
                user_id = user_meta.get("user_id")
                is_org_adm = user_meta.get("is_org_admin", False)
                user_org = (user_meta.get("organization_name") or "").strip().lower()

                creator_id = ticket_meta.get("created_by_user_id")
                creator_is_admin = ticket_meta.get("creator_is_admin", False)
                ticket_org = (ticket_meta.get("organization_name") or "").strip().lower()

                if is_super or user_id == creator_id:
                    can_see = True
                elif creator_is_admin:
                    # Raised by Org Admin: Confidential between creator and Super Admin
                    can_see = False
                elif is_org_adm and user_org and user_org == ticket_org:
                    # Raised by regular user: Org Admin of the same organization can see
                    can_see = True
                else:
                    can_see = False

                if not can_see:
                    continue

            try:
                await connection.send_json(event_payload)
            except Exception as e:
                logger.warning(f"[TicketWS] Error broadcasting to hub: {e}")
                dead_connections.append(connection)

        for dead in dead_connections:
            self.disconnect_hub(dead)


ticket_ws_manager = TicketConnectionManager()


# ── Helper Functions ────────────────────────────────────────────────────────

def _generate_ticket_code(db: Session) -> str:
    """Generates unique human-readable ticket code, e.g. TCK-2026-84920."""
    year = datetime.utcnow().year
    for _ in range(20):
        random_digits = "".join(random.choices(string.digits, k=5))
        code = f"TCK-{year}-{random_digits}"
        exists = db.query(models.SupportTicket).filter(models.SupportTicket.ticket_code == code).first()
        if not exists:
            return code
    # Fallback with timestamp
    return f"TCK-{year}-{int(datetime.utcnow().timestamp()) % 100000}"


def _user_to_sender_info(user: Optional[models.User]) -> Optional[schemas.TicketSenderInfo]:
    if not user:
        return None
    is_super = bool(getattr(user, "is_super_admin", False))
    is_org_adm = bool(getattr(user, "is_org_admin", False))
    if is_super:
        role_label = "Super Admin"
    elif is_org_adm:
        role_label = "Organization Admin"
    else:
        role_label = getattr(user, "role_name", None) or "User"

    return schemas.TicketSenderInfo(
        id=user.id,
        email=user.email,
        role_name=role_label,
        is_super_admin=is_super,
        is_org_admin=is_org_adm,
        organization_name=user.organization_name
    )


def _can_user_resolve_or_change_status(ticket: models.SupportTicket, current_user: models.User) -> bool:
    """
    Returns True if current_user has permission to resolve ticket or change its status/priority:
    1. Super Admin: Can resolve and change status for all tickets.
    2. Regular User: CANNOT resolve or change status (access limited to Org Admin & Super Admin).
    3. Org Admin:
       - If the ticket was raised by an Org Admin (or Super Admin), ONLY Super Admin can resolve or change status.
         Org Admin CANNOT resolve or change status.
       - If the ticket was raised by a regular user in the same organization, Org Admin CAN resolve or change status.
    """
    if getattr(current_user, "is_super_admin", False):
        return True

    if not getattr(current_user, "is_org_admin", False):
        return False

    # Current user is an Org Admin. Check if ticket was created by an Org Admin or Super Admin:
    creator = ticket.created_by
    creator_is_admin = False
    if creator:
        creator_is_admin = bool(getattr(creator, "is_org_admin", False) or getattr(creator, "is_super_admin", False))
    elif ticket.created_by_user_id == current_user.id:
        creator_is_admin = True

    if creator_is_admin:
        # Ticket was raised by an Org Admin. Only Super Admin can resolve or change status.
        return False

    # Ticket was raised by a regular user. Org Admin can resolve/change status if same org.
    user_org = (getattr(current_user, "organization_name", None) or "").strip().lower()
    ticket_org = (ticket.organization_name or "").strip().lower()
    return bool(user_org and user_org == ticket_org)


def _check_ticket_access(ticket: models.SupportTicket, current_user: models.User) -> None:
    """
    Ensures caller has permission to view/interact with the ticket:
    - Super Admin: Full access to all tickets.
    - Ticket Creator: Can access their own tickets.
    - If raised by Org Admin: Visible ONLY to Super Admin and the Org Admin creator. Others cannot see.
    - If raised by Regular User: Visible ONLY to Super Admin, the user creator, and Org Admins of that organization.
      Other users cannot see.
    """
    if getattr(current_user, "is_super_admin", False):
        return

    # Creator can always view their own ticket
    if ticket.created_by_user_id == current_user.id:
        return

    # Non-creator user trying to access
    creator = ticket.created_by
    creator_is_admin = False
    if creator:
        creator_is_admin = bool(getattr(creator, "is_org_admin", False) or getattr(creator, "is_super_admin", False))

    if creator_is_admin:
        # Ticket raised by Org Admin: Confidential between creator and Super Admin
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this ticket. Tickets raised by Organization Admins are confidential to Super Admins."
        )

    # Ticket raised by a regular user.
    # Regular users cannot view other regular users' tickets
    if not getattr(current_user, "is_org_admin", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this ticket."
        )

    # Org Admin can only view regular users' tickets in their own organization
    user_org = (getattr(current_user, "organization_name", None) or "").strip().lower()
    ticket_org = (ticket.organization_name or "").strip().lower()
    if not user_org or user_org != ticket_org:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access tickets from another organization."
        )


def _build_ticket_response(
    ticket: models.SupportTicket,
    current_user: models.User,
    include_messages: bool = True
) -> schemas.TicketResponse:
    is_admin = bool(getattr(current_user, "is_super_admin", False) or getattr(current_user, "is_org_admin", False))

    # Unread computation:
    # If current user is the creator of the ticket, they care about unread_by_user (messages from support).
    # If current user is an admin viewing someone else's ticket, they care about unread_by_admin (messages from requester).
    if current_user.id == ticket.created_by_user_id:
        unread = bool(ticket.unread_by_user)
    else:
        unread = bool(ticket.unread_by_admin)

    msg_responses = []
    if include_messages and ticket.messages:
        for m in ticket.messages:
            # If user is not admin and message is internal note, hide it
            if m.is_internal_note and not is_admin:
                continue
            msg_responses.append(
                schemas.TicketMessageResponse(
                    id=m.id,
                    ticket_id=m.ticket_id,
                    sender_user_id=m.sender_user_id,
                    sender=_user_to_sender_info(m.sender),
                    message=m.message,
                    is_internal_note=m.is_internal_note,
                    attachments=m.attachments,
                    created_at=m.created_at
                )
            )

    can_change = _can_user_resolve_or_change_status(ticket, current_user)
    can_res = can_change and (ticket.status or "").upper() not in ("RESOLVED", "CLOSED")

    return schemas.TicketResponse(
        id=ticket.id,
        ticket_code=ticket.ticket_code,
        title=ticket.title,
        description=ticket.description,
        category=ticket.category,
        priority=ticket.priority,
        status=ticket.status,
        organization_name=ticket.organization_name,
        created_by_user_id=ticket.created_by_user_id,
        created_by=_user_to_sender_info(ticket.created_by),
        assigned_to_user_id=ticket.assigned_to_user_id,
        assigned_to=_user_to_sender_info(ticket.assigned_to),
        resolution_summary=ticket.resolution_summary,
        resolved_by_user_id=ticket.resolved_by_user_id,
        resolved_by=_user_to_sender_info(ticket.resolved_by),
        resolved_at=ticket.resolved_at,
        last_message_at=ticket.last_message_at or ticket.created_at,
        unread=unread,
        message_count=len(msg_responses),
        messages=msg_responses,
        can_change_status=can_change,
        can_resolve=can_res,
        created_at=ticket.created_at,
        updated_at=ticket.updated_at
    )


# ── REST API Endpoints ──────────────────────────────────────────────────────

@router.get("", response_model=List[schemas.TicketResponse])
def get_tickets(
    status_filter: Optional[str] = Query(None, alias="status"),
    priority: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    organization: Optional[str] = Query(None),
    current_user: Annotated[models.User, Depends(auth.get_current_user)] = None,
    db: Session = Depends(get_db)
):
    """
    Returns support tickets scoped to current user's role:
    - Super Admin: All tickets across all organizations.
    - Org Admin: All tickets belonging to current user's organization.
    - End User: Only tickets created by current user.
    """
    is_super = bool(getattr(current_user, "is_super_admin", False))
    is_org_adm = bool(getattr(current_user, "is_org_admin", False))
    user_org = (getattr(current_user, "organization_name", None) or "").strip()

    query = db.query(models.SupportTicket)

    if is_super:
        if organization:
            query = query.filter(func.lower(models.SupportTicket.organization_name) == organization.strip().lower())
    elif is_org_adm and user_org:
        # Org Admin sees:
        # 1. Tickets they themselves created
        # 2. Tickets created by regular users in their org (not tickets created by other org admins or super admins)
        query = query.join(models.User, models.SupportTicket.created_by_user_id == models.User.id).filter(
            or_(
                models.SupportTicket.created_by_user_id == current_user.id,
                and_(
                    func.lower(models.SupportTicket.organization_name) == user_org.lower(),
                    models.User.is_org_admin.is_(False),
                    models.User.is_super_admin.is_(False)
                )
            )
        )
    else:
        # Regular user sees only their own tickets
        query = query.filter(models.SupportTicket.created_by_user_id == current_user.id)

    # Filters
    if status_filter and status_filter.upper() != "ALL":
        query = query.filter(func.upper(models.SupportTicket.status) == status_filter.upper())

    if priority and priority.upper() != "ALL":
        query = query.filter(func.upper(models.SupportTicket.priority) == priority.upper())

    if category and category.upper() != "ALL":
        query = query.filter(func.lower(models.SupportTicket.category) == category.lower())

    if search and search.strip():
        term = f"%{search.strip()}%"
        query = query.filter(
            or_(
                models.SupportTicket.title.ilike(term),
                models.SupportTicket.description.ilike(term),
                models.SupportTicket.ticket_code.ilike(term),
                models.SupportTicket.category.ilike(term)
            )
        )

    tickets = query.order_by(models.SupportTicket.last_message_at.desc()).all()
    return [_build_ticket_response(t, current_user, include_messages=False) for t in tickets]


@router.get("/stats", response_model=schemas.TicketStatsResponse)
def get_ticket_stats(
    current_user: Annotated[models.User, Depends(auth.get_current_user)],
    db: Session = Depends(get_db)
):
    """Returns metric counters for tickets according to the user's role."""
    is_super = bool(getattr(current_user, "is_super_admin", False))
    is_org_adm = bool(getattr(current_user, "is_org_admin", False))
    user_org = (getattr(current_user, "organization_name", None) or "").strip()

    query = db.query(models.SupportTicket)
    if is_super:
        pass
    elif is_org_adm and user_org:
        query = query.join(models.User, models.SupportTicket.created_by_user_id == models.User.id).filter(
            or_(
                models.SupportTicket.created_by_user_id == current_user.id,
                and_(
                    func.lower(models.SupportTicket.organization_name) == user_org.lower(),
                    models.User.is_org_admin.is_(False),
                    models.User.is_super_admin.is_(False)
                )
            )
        )
    else:
        query = query.filter(models.SupportTicket.created_by_user_id == current_user.id)

    tickets = query.all()
    stats = schemas.TicketStatsResponse()
    stats.total = len(tickets)

    for t in tickets:
        st = (t.status or "").upper()
        if st == "OPEN":
            stats.open += 1
        elif st == "IN_PROGRESS":
            stats.in_progress += 1
        elif st == "AWAITING_INFO":
            stats.awaiting_info += 1
        elif st == "RESOLVED":
            stats.resolved += 1
        elif st == "CLOSED":
            stats.closed += 1

        if (t.priority or "").upper() == "URGENT" and st not in ("RESOLVED", "CLOSED"):
            stats.urgent += 1

        if current_user.id == t.created_by_user_id:
            if t.unread_by_user:
                stats.unread_messages += 1
        else:
            if t.unread_by_admin:
                stats.unread_messages += 1

    return stats


@router.get("/unread-count")
def get_unread_tickets_count(
    current_user: Annotated[models.User, Depends(auth.get_current_user)],
    db: Session = Depends(get_db)
):
    """Fast endpoint for sidebar navigation badge."""
    is_super = bool(getattr(current_user, "is_super_admin", False))
    is_org_adm = bool(getattr(current_user, "is_org_admin", False))
    user_org = (getattr(current_user, "organization_name", None) or "").strip()

    query = db.query(models.SupportTicket)
    if is_super:
        pass
    elif is_org_adm and user_org:
        query = query.join(models.User, models.SupportTicket.created_by_user_id == models.User.id).filter(
            or_(
                models.SupportTicket.created_by_user_id == current_user.id,
                and_(
                    func.lower(models.SupportTicket.organization_name) == user_org.lower(),
                    models.User.is_org_admin.is_(False),
                    models.User.is_super_admin.is_(False)
                )
            )
        )
    else:
        query = query.filter(models.SupportTicket.created_by_user_id == current_user.id)

    query = query.filter(
        or_(
            and_(
                models.SupportTicket.created_by_user_id == current_user.id,
                models.SupportTicket.unread_by_user.is_(True)
            ),
            and_(
                models.SupportTicket.created_by_user_id != current_user.id,
                models.SupportTicket.unread_by_admin.is_(True)
            )
        )
    )

    count = query.count()
    return {"unread_count": count}


@router.post("", response_model=schemas.TicketResponse)
async def create_ticket(
    payload: schemas.TicketCreate,
    current_user: Annotated[models.User, Depends(auth.get_current_user)],
    db: Session = Depends(get_db)
):
    """Raises a new support ticket and creates the initial opening message in the conversation thread."""
    if getattr(current_user, "is_super_admin", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super Administrators oversee and resolve tickets; they cannot raise tickets."
        )

    user_org = (getattr(current_user, "organization_name", None) or "").strip() or None
    ticket_code = _generate_ticket_code(db)

    ticket = models.SupportTicket(
        ticket_code=ticket_code,
        title=payload.title.strip(),
        description=payload.description.strip(),
        category=payload.category.strip(),
        priority=payload.priority.strip().upper(),
        status="OPEN",
        organization_name=user_org,
        created_by_user_id=current_user.id,
        unread_by_admin=True,
        unread_by_user=False,
        last_message_at=datetime.utcnow()
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)

    # Add initial opening message into the conversation thread
    initial_msg = models.TicketMessage(
        ticket_id=ticket.id,
        sender_user_id=current_user.id,
        message=payload.description.strip(),
        is_internal_note=False
    )
    db.add(initial_msg)
    db.commit()
    db.refresh(ticket)

    resp = _build_ticket_response(ticket, current_user, include_messages=True)
    creator_is_admin = bool(getattr(current_user, "is_org_admin", False) or getattr(current_user, "is_super_admin", False))
    ticket_meta = {
        "ticket_id": ticket.id,
        "created_by_user_id": ticket.created_by_user_id,
        "creator_is_admin": creator_is_admin,
        "organization_name": ticket.organization_name
    }
    await ticket_ws_manager.broadcast_hub({
        "type": "TICKET_CREATED",
        "ticket": resp.model_dump(mode="json")
    }, ticket_meta=ticket_meta)

    return resp


@router.get("/{ticket_id}", response_model=schemas.TicketResponse)
def get_ticket_detail(
    ticket_id: int,
    current_user: Annotated[models.User, Depends(auth.get_current_user)],
    db: Session = Depends(get_db)
):
    """Fetches full ticket details and marks messages as read for the viewer."""
    ticket = db.query(models.SupportTicket).filter(models.SupportTicket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    _check_ticket_access(ticket, current_user)

    # Mark as read
    if current_user.id == ticket.created_by_user_id:
        ticket.unread_by_user = False
    else:
        ticket.unread_by_admin = False
    db.commit()
    db.refresh(ticket)

    return _build_ticket_response(ticket, current_user, include_messages=True)


@router.patch("/{ticket_id}", response_model=schemas.TicketResponse)
async def update_ticket(
    ticket_id: int,
    payload: schemas.TicketUpdate,
    current_user: Annotated[models.User, Depends(auth.get_current_user)],
    db: Session = Depends(get_db)
):
    """Updates status, priority, or assignee for the ticket with RBAC verification."""
    ticket = db.query(models.SupportTicket).filter(models.SupportTicket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    _check_ticket_access(ticket, current_user)

    if payload.status is not None:
        if not _can_user_resolve_or_change_status(ticket, current_user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to change the status of this ticket. If raised by an Organization Admin, only Super Admin can change status."
            )
        target_status = payload.status.strip().upper()
        ticket.status = target_status
        if target_status in ("RESOLVED", "CLOSED") and not ticket.resolved_at:
            ticket.resolved_at = datetime.utcnow()
            ticket.resolved_by_user_id = current_user.id

    if payload.priority is not None:
        if not _can_user_resolve_or_change_status(ticket, current_user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to adjust ticket priority."
            )
        ticket.priority = payload.priority.strip().upper()

    if payload.assigned_to_user_id is not None:
        if not _can_user_resolve_or_change_status(ticket, current_user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to assign tickets."
            )
        ticket.assigned_to_user_id = payload.assigned_to_user_id or None

    ticket.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(ticket)

    # Broadcast status change
    resp = _build_ticket_response(ticket, current_user, include_messages=True)
    await ticket_ws_manager.broadcast_to_ticket(ticket_id, {
        "type": "TICKET_UPDATED",
        "ticket": resp.model_dump(mode="json")
    })

    return resp


@router.post("/{ticket_id}/resolve", response_model=schemas.TicketResponse)
async def resolve_ticket(
    ticket_id: int,
    payload: schemas.TicketResolvePayload,
    current_user: Annotated[models.User, Depends(auth.get_current_user)],
    db: Session = Depends(get_db)
):
    """Marks ticket as RESOLVED with resolution summary and appends a resolution system event."""
    ticket = db.query(models.SupportTicket).filter(models.SupportTicket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    _check_ticket_access(ticket, current_user)

    if not _can_user_resolve_or_change_status(ticket, current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to resolve this ticket. If raised by an Organization Admin, only Super Admin can resolve it."
        )

    summary = (payload.resolution_summary or "").strip() or "Issue marked as resolved."

    ticket.status = "RESOLVED"
    ticket.resolved_at = datetime.utcnow()
    ticket.resolved_by_user_id = current_user.id
    ticket.resolution_summary = summary
    ticket.updated_at = datetime.utcnow()
    ticket.last_message_at = datetime.utcnow()

    # Append resolution message
    res_msg = models.TicketMessage(
        ticket_id=ticket.id,
        sender_user_id=current_user.id,
        message=f"Ticket resolved by {current_user.email}: {summary}",
        is_internal_note=False
    )
    db.add(res_msg)
    db.commit()
    db.refresh(ticket)

    resp = _build_ticket_response(ticket, current_user, include_messages=True)
    await ticket_ws_manager.broadcast_to_ticket(ticket_id, {
        "type": "TICKET_RESOLVED",
        "ticket": resp.model_dump(mode="json"),
        "resolution_summary": summary
    })

    creator = ticket.created_by
    creator_is_admin = bool(
        creator and (getattr(creator, "is_org_admin", False) or getattr(creator, "is_super_admin", False))
    )
    ticket_meta = {
        "ticket_id": ticket.id,
        "created_by_user_id": ticket.created_by_user_id,
        "creator_is_admin": creator_is_admin,
        "organization_name": ticket.organization_name
    }
    await ticket_ws_manager.broadcast_hub({
        "type": "TICKET_RESOLVED",
        "ticket_id": ticket.id,
        "resolution_summary": summary
    }, ticket_meta=ticket_meta)

    return resp


@router.post("/{ticket_id}/messages", response_model=schemas.TicketMessageResponse)
async def post_ticket_message(
    ticket_id: int,
    payload: schemas.TicketMessageCreate,
    current_user: Annotated[models.User, Depends(auth.get_current_user)],
    db: Session = Depends(get_db)
):
    """Sends a chat reply or internal note into the ticket thread and broadcasts in real-time."""
    ticket = db.query(models.SupportTicket).filter(models.SupportTicket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    _check_ticket_access(ticket, current_user)

    is_admin = bool(getattr(current_user, "is_super_admin", False) or getattr(current_user, "is_org_admin", False))
    if payload.is_internal_note and not is_admin:
        raise HTTPException(status_code=403, detail="Only administrators can post internal notes")

    new_msg = models.TicketMessage(
        ticket_id=ticket.id,
        sender_user_id=current_user.id,
        message=payload.message.strip(),
        is_internal_note=payload.is_internal_note,
        attachments=payload.attachments
    )
    db.add(new_msg)

    # Update ticket timestamps and unread flags
    ticket.last_message_at = datetime.utcnow()
    ticket.updated_at = datetime.utcnow()

    if current_user.id == ticket.created_by_user_id:
        if ticket.status == "AWAITING_INFO":
            ticket.status = "IN_PROGRESS"
        ticket.unread_by_admin = True
    else:
        ticket.unread_by_user = True

    db.commit()
    db.refresh(new_msg)

    msg_resp = schemas.TicketMessageResponse(
        id=new_msg.id,
        ticket_id=new_msg.ticket_id,
        sender_user_id=new_msg.sender_user_id,
        sender=_user_to_sender_info(current_user),
        message=new_msg.message,
        is_internal_note=new_msg.is_internal_note,
        attachments=new_msg.attachments,
        created_at=new_msg.created_at
    )

    # Broadcast message to live WebSocket listeners viewing this ticket
    await ticket_ws_manager.broadcast_to_ticket(ticket_id, {
        "type": "NEW_MESSAGE",
        "ticket_id": ticket_id,
        "message": msg_resp.model_dump(mode="json")
    })

    # Broadcast to Hub listeners for instant cross-ticket notification
    creator = ticket.created_by
    creator_is_admin = bool(
        creator and (getattr(creator, "is_org_admin", False) or getattr(creator, "is_super_admin", False))
    )
    ticket_meta = {
        "ticket_id": ticket.id,
        "created_by_user_id": ticket.created_by_user_id,
        "creator_is_admin": creator_is_admin,
        "organization_name": ticket.organization_name
    }
    await ticket_ws_manager.broadcast_hub({
        "type": "NEW_MESSAGE",
        "ticket_id": ticket_id,
        "ticket_code": ticket.ticket_code,
        "ticket_title": ticket.title,
        "message": msg_resp.model_dump(mode="json")
    }, ticket_meta=ticket_meta)

    return msg_resp


# ── WebSocket Endpoints ──────────────────────────────────────────────────────

@router.websocket("/ws/hub")
async def hub_websocket(
    websocket: WebSocket,
    token: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """
    Real-time Hub WebSocket for global notification events,
    cross-ticket incoming messages, and live unread counts without polling.
    """
    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    try:
        payload = auth.verify_token(token)
        if not payload or "sub" not in payload:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        user_email = payload["sub"]
        user = db.query(models.User).filter(models.User.email == user_email).first()
        if not user:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
    except Exception as e:
        logger.warning(f"[TicketWS Hub] Auth failed: {e}")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    user_meta = {
        "user_id": user.id,
        "email": user.email,
        "is_super_admin": bool(getattr(user, "is_super_admin", False)),
        "is_org_admin": bool(getattr(user, "is_org_admin", False)),
        "organization_name": user.organization_name
    }
    await ticket_ws_manager.connect_hub(websocket, user_meta)

    try:
        await websocket.send_json({
            "type": "HUB_CONNECTED",
            "connected_user": user.email
        })

        while True:
            data_text = await websocket.receive_text()
            try:
                data = json.loads(data_text)
                if data.get("type") == "PING":
                    await websocket.send_json({"type": "PONG"})
            except Exception:
                pass
    except WebSocketDisconnect:
        ticket_ws_manager.disconnect_hub(websocket)
    except Exception as e:
        logger.warning(f"[TicketWS Hub] Exception: {e}")
        ticket_ws_manager.disconnect_hub(websocket)


@router.websocket("/ws/{ticket_id}")
async def ticket_websocket(
    websocket: WebSocket,
    ticket_id: int,
    token: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """
    WebSocket endpoint for real-time live ticket chat, typing indicators,
    and instantaneous resolution notifications.
    """
    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    try:
        payload = auth.verify_token(token)
        if not payload or "sub" not in payload:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        user_email = payload["sub"]
        user = db.query(models.User).filter(models.User.email == user_email).first()
        if not user:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        ticket = db.query(models.SupportTicket).filter(models.SupportTicket.id == ticket_id).first()
        if not ticket:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        _check_ticket_access(ticket, user)
    except Exception as e:
        logger.warning(f"[TicketWS] Auth failed for ticket {ticket_id}: {e}")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await ticket_ws_manager.connect(websocket, ticket_id)

    try:
        await websocket.send_json({
            "type": "CONNECTED",
            "ticket_id": ticket_id,
            "connected_user": user.email
        })

        while True:
            data_text = await websocket.receive_text()
            try:
                data = json.loads(data_text)
                msg_type = data.get("type")
                if msg_type == "PING":
                    await websocket.send_json({"type": "PONG"})
                elif msg_type == "TYPING":
                    await ticket_ws_manager.broadcast_to_ticket(ticket_id, {
                        "type": "USER_TYPING",
                        "user_email": user.email,
                        "user_id": user.id,
                        "is_typing": bool(data.get("is_typing", True))
                    })
            except Exception:
                pass
    except WebSocketDisconnect:
        ticket_ws_manager.disconnect(websocket, ticket_id)
    except Exception as e:
        logger.warning(f"[TicketWS] Exception in loop for ticket {ticket_id}: {e}")
        ticket_ws_manager.disconnect(websocket, ticket_id)
