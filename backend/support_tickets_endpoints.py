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
from sqlalchemy import func, or_
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
        self.hub_connections: List[WebSocket] = []

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

    async def connect_hub(self, websocket: WebSocket):
        await websocket.accept()
        self.hub_connections.append(websocket)
        logger.info(f"[TicketWS] Connected to Hub WS. Total listeners: {len(self.hub_connections)}")

    def disconnect_hub(self, websocket: WebSocket):
        if websocket in self.hub_connections:
            self.hub_connections.remove(websocket)
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

    async def broadcast_hub(self, event_payload: dict):
        """Broadcasts event payload to all hub clients."""
        dead_connections = []
        for connection in list(self.hub_connections):
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


def _check_ticket_access(ticket: models.SupportTicket, current_user: models.User) -> None:
    """Ensures caller has permission to view/interact with the ticket."""
    if getattr(current_user, "is_super_admin", False):
        return
    user_org = (getattr(current_user, "organization_name", None) or "").strip().lower()
    ticket_org = (ticket.organization_name or "").strip().lower()

    if getattr(current_user, "is_org_admin", False):
        if user_org and user_org == ticket_org:
            return
        if ticket.created_by_user_id == current_user.id:
            return
        raise HTTPException(status_code=403, detail="Not authorized to access tickets from another organization")

    if ticket.created_by_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to access this ticket")


def _build_ticket_response(
    ticket: models.SupportTicket,
    current_user: models.User,
    include_messages: bool = True
) -> schemas.TicketResponse:
    is_admin = bool(getattr(current_user, "is_super_admin", False) or getattr(current_user, "is_org_admin", False))

    # Unread computation
    if is_admin:
        unread = bool(ticket.unread_by_admin)
    else:
        unread = bool(ticket.unread_by_user)

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
        query = query.filter(
            or_(
                func.lower(models.SupportTicket.organization_name) == user_org.lower(),
                models.SupportTicket.created_by_user_id == current_user.id
            )
        )
    else:
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
        query = query.filter(
            or_(
                func.lower(models.SupportTicket.organization_name) == user_org.lower(),
                models.SupportTicket.created_by_user_id == current_user.id
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

        if is_super or is_org_adm:
            if t.unread_by_admin:
                stats.unread_messages += 1
        else:
            if t.unread_by_user:
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
        query = query.filter(
            or_(
                func.lower(models.SupportTicket.organization_name) == user_org.lower(),
                models.SupportTicket.created_by_user_id == current_user.id
            )
        )
    else:
        query = query.filter(models.SupportTicket.created_by_user_id == current_user.id)

    if is_super or is_org_adm:
        query = query.filter(models.SupportTicket.unread_by_admin == True)
    else:
        query = query.filter(models.SupportTicket.unread_by_user == True)

    count = query.count()
    return {"unread_count": count}


@router.post("", response_model=schemas.TicketResponse)
async def create_ticket(
    payload: schemas.TicketCreate,
    current_user: Annotated[models.User, Depends(auth.get_current_user)],
    db: Session = Depends(get_db)
):
    """Raises a new support ticket and creates the initial opening message in the conversation thread."""
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
    await ticket_ws_manager.broadcast_hub({
        "type": "TICKET_CREATED",
        "ticket": resp.model_dump(mode="json")
    })

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
    is_admin = bool(getattr(current_user, "is_super_admin", False) or getattr(current_user, "is_org_admin", False))
    if is_admin:
        ticket.unread_by_admin = False
    else:
        ticket.unread_by_user = False
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
    """Updates status, priority, or assignee for the ticket."""
    ticket = db.query(models.SupportTicket).filter(models.SupportTicket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    _check_ticket_access(ticket, current_user)

    is_admin = bool(getattr(current_user, "is_super_admin", False) or getattr(current_user, "is_org_admin", False))

    if payload.status:
        target_status = payload.status.strip().upper()
        # Non-admins can only resolve/close their own tickets or re-open them
        if not is_admin:
            if target_status not in ("RESOLVED", "CLOSED", "OPEN"):
                raise HTTPException(status_code=403, detail="Users can only mark tickets as Resolved, Closed, or Open")
        ticket.status = target_status
        if target_status in ("RESOLVED", "CLOSED") and not ticket.resolved_at:
            ticket.resolved_at = datetime.utcnow()
            ticket.resolved_by_user_id = current_user.id

    if payload.priority:
        if not is_admin:
            raise HTTPException(status_code=403, detail="Only administrators can adjust ticket priority")
        ticket.priority = payload.priority.strip().upper()

    if payload.assigned_to_user_id is not None:
        if not is_admin:
            raise HTTPException(status_code=403, detail="Only administrators can assign tickets")
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

    if is_admin:
        ticket.unread_by_user = True
    else:
        if ticket.status == "AWAITING_INFO":
            ticket.status = "IN_PROGRESS"
        ticket.unread_by_admin = True

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
    await ticket_ws_manager.broadcast_hub({
        "type": "NEW_MESSAGE",
        "ticket_id": ticket_id,
        "ticket_code": ticket.ticket_code,
        "ticket_title": ticket.title,
        "message": msg_resp.model_dump(mode="json")
    })

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

    await ticket_ws_manager.connect_hub(websocket)

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
