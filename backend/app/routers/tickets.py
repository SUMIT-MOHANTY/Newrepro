import asyncio
import json
import logging
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

from app.core.dependencies import get_current_user, get_db
from app.core.security import verify_token
from app.models.ticket import SupportTicket
from app.repositories.ticket_repository import ticket_repository
from app.schemas.ticket import (
    TicketCreate,
    TicketMessageCreate,
    TicketMessageResponse,
    TicketResolvePayload,
    TicketResponse,
    TicketStatsResponse,
    TicketUpdate,
)
from app.services.ticket_service import ticket_service
import database
import models

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tickets", tags=["Support Tickets"])


# ── WebSocket Manager for Live Ticket Communication ─────────────────────────

class TicketConnectionManager:
    """Tracks active WebSockets per ticket and per hub for instant multi-user updates."""

    def __init__(self):
        self.active_connections: Dict[int, List[WebSocket]] = {}
        self.hub_connections: Dict[WebSocket, dict] = {}

    async def connect(self, websocket: WebSocket, ticket_id: int):
        await websocket.accept()
        if ticket_id not in self.active_connections:
            self.active_connections[ticket_id] = []
        self.active_connections[ticket_id].append(websocket)
        logger.info(f"[TicketWS] Connected to ticket #{ticket_id}. Listeners: {len(self.active_connections[ticket_id])}")

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
        logger.info(f"[TicketWS] Connected to Hub WS (user={user_meta.get('email')}). Total: {len(self.hub_connections)}")

    def disconnect_hub(self, websocket: WebSocket):
        if websocket in self.hub_connections:
            del self.hub_connections[websocket]
        logger.info(f"[TicketWS] Disconnected from Hub WS. Remaining: {len(self.hub_connections)}")

    async def broadcast_to_ticket(self, ticket_id: int, message_payload: dict):
        if ticket_id not in self.active_connections:
            return
        dead_connections = []
        for connection in list(self.active_connections[ticket_id]):
            try:
                await connection.send_json(message_payload)
            except Exception as e:
                logger.warning(f"[TicketWS] Error broadcasting: {e}")
                dead_connections.append(connection)
        for dead in dead_connections:
            self.disconnect(dead, ticket_id)

    async def broadcast_hub(self, event_payload: dict, ticket_meta: Optional[dict] = None):
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
                    can_see = False
                elif is_org_adm and user_org and user_org == ticket_org:
                    can_see = True
                else:
                    can_see = False

                if not can_see:
                    continue

            try:
                await connection.send_json(event_payload)
            except Exception as e:
                logger.warning(f"[TicketWS] Hub error: {e}")
                dead_connections.append(connection)

        for dead in dead_connections:
            self.disconnect_hub(dead)


ticket_ws_manager = TicketConnectionManager()


# ── REST API Endpoints ──────────────────────────────────────────────────────

@router.get("/stats", response_model=TicketStatsResponse)
def get_ticket_stats(
    current_user: Annotated[models.User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    tickets = ticket_repository.list_tickets_scoped(db, current_user)
    is_admin = bool(getattr(current_user, "is_super_admin", False)) or bool(getattr(current_user, "is_org_admin", False))

    stats = TicketStatsResponse(
        total=len(tickets),
        open=sum(1 for t in tickets if t.status == "OPEN"),
        in_progress=sum(1 for t in tickets if t.status == "IN_PROGRESS"),
        awaiting_info=sum(1 for t in tickets if t.status == "AWAITING_INFO"),
        resolved=sum(1 for t in tickets if t.status == "RESOLVED"),
        closed=sum(1 for t in tickets if t.status == "CLOSED"),
        urgent=sum(1 for t in tickets if t.priority == "URGENT" and t.status in ("OPEN", "IN_PROGRESS")),
        unread_messages=sum(1 for t in tickets if (t.unread_by_admin if is_admin else t.unread_by_user)),
    )
    return stats


@router.get("", response_model=List[TicketResponse])
def get_tickets(
    current_user: Annotated[models.User, Depends(get_current_user)],
    status_filter: Optional[str] = Query(None, alias="status"),
    priority: Optional[str] = None,
    category: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
):
    cat_prefix = ticket_service.get_servicenow_prefix(category) if category and category.upper() != "ALL" else None
    tickets = ticket_repository.list_tickets_scoped(
        db=db,
        current_user=current_user,
        status_filter=status_filter,
        priority=priority,
        category=category,
        cat_prefix=cat_prefix,
        search=search,
    )
    return [ticket_service.build_ticket_response(t, current_user) for t in tickets]


@router.post("", response_model=TicketResponse, status_code=status.HTTP_201_CREATED)
async def create_ticket(
    payload: TicketCreate,
    current_user: Annotated[models.User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    ticket = ticket_service.create_ticket(db, payload, current_user)
    resp = ticket_service.build_ticket_response(ticket, current_user)

    ticket_meta = {
        "created_by_user_id": ticket.created_by_user_id,
        "creator_is_admin": bool(getattr(current_user, "is_super_admin", False)) or bool(getattr(current_user, "is_org_admin", False)),
        "organization_name": ticket.organization_name,
    }
    await ticket_ws_manager.broadcast_hub(
        {
            "event": "TICKET_CREATED",
            "ticket": resp.model_dump(mode="json"),
            "sender_name": current_user.email.split("@")[0],
        },
        ticket_meta=ticket_meta,
    )
    return resp


def _check_ticket_access(ticket: SupportTicket, current_user: models.User) -> None:
    """
    Ensures caller has permission to view/interact with the ticket:
    - Super Admin: Full access to all tickets.
    - Ticket Creator: Can access their own tickets.
    - If raised by Org Admin: Visible ONLY to Super Admin and the Org Admin creator.
    - If raised by Regular User: Visible ONLY to Super Admin, the creator, and Org Admins of that organization.
    """
    if getattr(current_user, "is_super_admin", False):
        return

    if ticket.created_by_user_id == current_user.id:
        return

    creator = ticket.created_by
    creator_is_admin = False
    if creator:
        creator_is_admin = bool(getattr(creator, "is_org_admin", False) or getattr(creator, "is_super_admin", False))

    if creator_is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this ticket. Tickets raised by Organization Admins are confidential to Super Admins.",
        )

    if not getattr(current_user, "is_org_admin", False):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied.")

    user_org = (getattr(current_user, "organization_name", None) or "").strip().lower()
    ticket_org = (ticket.organization_name or "").strip().lower()
    if not user_org or user_org != ticket_org:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access tickets from another organization.",
        )


def _can_user_resolve_or_change_status(ticket: SupportTicket, current_user: models.User) -> bool:
    """
    Determines whether caller can resolve or alter ticket status/priority:
    - Super Admin can change anything.
    - If raised by Org Admin, only Super Admin can resolve or modify status.
    - If raised by regular user, Org Admin in same org can resolve/modify.
    - Creator user can close/resolve their own ticket.
    """
    if getattr(current_user, "is_super_admin", False):
        return True

    creator = ticket.created_by
    creator_is_admin = False
    if creator:
        creator_is_admin = bool(getattr(creator, "is_org_admin", False) or getattr(creator, "is_super_admin", False))
    elif ticket.created_by_user_id == current_user.id:
        creator_is_admin = bool(getattr(current_user, "is_org_admin", False))

    if creator_is_admin:
        # Org Admin raised tickets can only be resolved/modified by Super Admin
        return False

    if getattr(current_user, "is_org_admin", False):
        user_org = (getattr(current_user, "organization_name", None) or "").strip().lower()
        ticket_org = (ticket.organization_name or "").strip().lower()
        return bool(user_org and user_org == ticket_org)

    return ticket.created_by_user_id == current_user.id


@router.get("/unread-count")
def get_unread_tickets_count(
    current_user: Annotated[models.User, Depends(get_current_user)],
    db: Session = Depends(get_db),
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
                    models.User.is_super_admin.is_(False),
                ),
            )
        )
    else:
        query = query.filter(models.SupportTicket.created_by_user_id == current_user.id)

    query = query.filter(
        or_(
            and_(
                models.SupportTicket.created_by_user_id == current_user.id,
                models.SupportTicket.unread_by_user.is_(True),
            ),
            and_(
                models.SupportTicket.created_by_user_id != current_user.id,
                models.SupportTicket.unread_by_admin.is_(True),
            ),
        )
    )

    count = query.count()
    return {"unread_count": count}


@router.get("/{ticket_id}", response_model=TicketResponse)
def get_ticket(
    ticket_id: int,
    current_user: Annotated[models.User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    ticket = ticket_repository.get_with_relations(db, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Support ticket not found.")

    _check_ticket_access(ticket, current_user)

    is_super = bool(getattr(current_user, "is_super_admin", False))
    is_org_adm = bool(getattr(current_user, "is_org_admin", False))

    # Mark unread flag as read
    if is_super or is_org_adm:
        ticket.unread_by_admin = False
    else:
        ticket.unread_by_user = False
    db.commit()

    return ticket_service.build_ticket_response(ticket, current_user, include_messages=True)


@router.patch("/{ticket_id}", response_model=TicketResponse)
async def update_ticket(
    ticket_id: int,
    payload: TicketUpdate,
    current_user: Annotated[models.User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    """Updates status, priority, or assignee for the ticket with RBAC verification."""
    ticket = ticket_repository.get_with_relations(db, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Support ticket not found.")

    _check_ticket_access(ticket, current_user)

    if payload.status is not None:
        if not _can_user_resolve_or_change_status(ticket, current_user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to change the status of this ticket. If raised by an Organization Admin, only Super Admin can change status.",
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
                detail="Not authorized to adjust ticket priority.",
            )
        ticket.priority = payload.priority.strip().upper()

    if payload.assigned_to_user_id is not None:
        if not _can_user_resolve_or_change_status(ticket, current_user):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to assign tickets.",
            )
        ticket.assigned_to_user_id = payload.assigned_to_user_id or None

    ticket.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(ticket)

    resp = ticket_service.build_ticket_response(ticket, current_user, include_messages=True)
    await ticket_ws_manager.broadcast_to_ticket(
        ticket_id,
        {
            "event": "TICKET_UPDATED",
            "type": "TICKET_UPDATED",
            "ticket": resp.model_dump(mode="json"),
        },
    )
    await ticket_ws_manager.broadcast_hub(
        {
            "event": "TICKET_UPDATED",
            "type": "TICKET_UPDATED",
            "ticket": resp.model_dump(mode="json"),
            "sender_name": current_user.email.split("@")[0],
        }
    )
    return resp


@router.post("/{ticket_id}/resolve", response_model=TicketResponse)
async def resolve_ticket(
    ticket_id: int,
    payload: TicketResolvePayload,
    current_user: Annotated[models.User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    ticket = ticket_service.resolve_ticket(db, ticket_id, payload, current_user)
    resp = ticket_service.build_ticket_response(ticket, current_user, include_messages=True)

    event_payload = {
        "event": "TICKET_RESOLVED",
        "ticket_id": ticket.id,
        "ticket_code": ticket.ticket_code,
        "status": "RESOLVED",
        "resolution_summary": ticket.resolution_summary,
        "resolved_by": current_user.email,
    }
    await ticket_ws_manager.broadcast_to_ticket(ticket.id, event_payload)
    await ticket_ws_manager.broadcast_hub(
        {
            "event": "TICKET_UPDATED",
            "ticket": resp.model_dump(mode="json"),
            "sender_name": current_user.email.split("@")[0],
        }
    )
    return resp


@router.post("/{ticket_id}/messages", response_model=TicketMessageResponse)
async def post_ticket_message(
    ticket_id: int,
    payload: TicketMessageCreate,
    current_user: Annotated[models.User, Depends(get_current_user)],
    db: Session = Depends(get_db),
):
    ticket = ticket_repository.get_with_relations(db, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Support ticket not found.")

    is_super = bool(getattr(current_user, "is_super_admin", False))
    is_org_adm = bool(getattr(current_user, "is_org_admin", False))
    is_admin = is_super or is_org_adm

    if payload.is_internal_note and not is_admin:
        raise HTTPException(status_code=403, detail="Only administrators can post internal notes.")

    msg = ticket_repository.add_message(
        db=db,
        ticket=ticket,
        sender_user_id=current_user.id,
        message=payload.message.strip(),
        is_internal_note=payload.is_internal_note,
        attachments=payload.attachments,
        is_admin_sender=is_admin,
    )

    msg_resp = TicketMessageResponse(
        id=msg.id,
        ticket_id=msg.ticket_id,
        sender_user_id=msg.sender_user_id,
        sender=ticket_service.user_to_sender_info(current_user),
        message=msg.message,
        is_internal_note=msg.is_internal_note,
        attachments=msg.attachments,
        created_at=msg.created_at,
    )

    await ticket_ws_manager.broadcast_to_ticket(
        ticket.id,
        {
            "event": "NEW_MESSAGE",
            "ticket_id": ticket.id,
            "message": msg_resp.model_dump(mode="json"),
        },
    )
    return msg_resp


# ── WebSockets ───────────────────────────────────────────────────────────────

@router.websocket("/ws/{ticket_id}")
async def ticket_websocket(websocket: WebSocket, ticket_id: int):
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    payload = verify_token(token)
    if not payload:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await ticket_ws_manager.connect(websocket, ticket_id)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ticket_ws_manager.disconnect(websocket, ticket_id)


@router.websocket("/ws/hub")
@router.websocket("/ws-hub")
async def ticket_hub_websocket(websocket: WebSocket):
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    payload = verify_token(token)
    if not payload:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    email = payload.get("sub")
    db = database.SessionLocal()
    user = db.query(models.User).filter(models.User.email == email).first()
    db.close()

    if not user:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    user_meta = {
        "user_id": user.id,
        "email": user.email,
        "is_super_admin": bool(getattr(user, "is_super_admin", False)),
        "is_org_admin": bool(getattr(user, "is_org_admin", False)),
        "organization_name": user.organization_name,
    }
    await ticket_ws_manager.connect_hub(websocket, user_meta)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ticket_ws_manager.disconnect_hub(websocket)


__all__ = ["router", "ticket_ws_manager"]
