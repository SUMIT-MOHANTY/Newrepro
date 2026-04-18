"""
Agent Communication Service
Handles agent-to-agent messaging, blocker detection, and collaborative resolution.

Flow:
  Agent stuck → broadcasts BLOCKED message → peers check if they can help
  → helper responds with OFFERING → stuck agent waits → helper signals READY
  → stuck agent resumes → marks RESOLVED
"""
import asyncio
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List

from sqlalchemy.orm import Session
from models import AgentMessage

logger = logging.getLogger(__name__)

# In-memory pub/sub so agents get messages instantly without polling DB
# project_token -> list of asyncio.Queue
_subscribers: Dict[str, List[asyncio.Queue]] = {}
_sub_lock = asyncio.Lock()


# ── Pub/Sub ──────────────────────────────────────────────────────────────────

async def subscribe(project_token: str) -> asyncio.Queue:
    async with _sub_lock:
        q: asyncio.Queue = asyncio.Queue()
        _subscribers.setdefault(project_token, []).append(q)
        return q


async def unsubscribe(project_token: str, q: asyncio.Queue) -> None:
    async with _sub_lock:
        subs = _subscribers.get(project_token, [])
        try:
            subs.remove(q)
        except ValueError:
            pass


async def _broadcast(project_token: str, msg: Dict[str, Any]) -> None:
    async with _sub_lock:
        queues = list(_subscribers.get(project_token, []))
    for q in queues:
        try:
            q.put_nowait(msg)
        except asyncio.QueueFull:
            pass


# ── Core send ────────────────────────────────────────────────────────────────

async def send_message(
    db: Session,
    project_token: str,
    from_agent: str,
    message: str,
    msg_type: str = "INFO",
    to_agent: Optional[str] = None,
    related_task_id: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
) -> AgentMessage:
    """Persist a message and broadcast it to all subscribers."""
    record = AgentMessage(
        project_token=project_token,
        from_agent=from_agent,
        to_agent=to_agent,
        msg_type=msg_type,
        message=message,
        payload=payload,
        related_task_id=related_task_id,
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    await _broadcast(project_token, _serialize(record))
    logger.info(f"[{from_agent}] {msg_type} → {to_agent or 'ALL'}: {message[:80]}")
    return record


def _serialize(msg: AgentMessage) -> Dict[str, Any]:
    return {
        "id": msg.id,
        "project_token": msg.project_token,
        "from_agent": msg.from_agent,
        "to_agent": msg.to_agent,
        "msg_type": msg.msg_type,
        "message": msg.message,
        "payload": msg.payload,
        "related_task_id": msg.related_task_id,
        "resolved": msg.resolved,
        "resolved_by": msg.resolved_by,
        "resolved_at": msg.resolved_at.isoformat() if msg.resolved_at else None,
        "created_at": msg.created_at.isoformat(),
    }


# ── Blocker flow ─────────────────────────────────────────────────────────────

async def broadcast_blocked(
    db: Session,
    project_token: str,
    from_agent: str,
    reason: str,
    related_task_id: Optional[str] = None,
    needs: Optional[str] = None,  # e.g. "Loan model from banking module"
) -> AgentMessage:
    """Agent broadcasts that it is blocked and needs help."""
    payload = {"needs": needs} if needs else {}
    return await send_message(
        db, project_token, from_agent,
        f"🚫 BLOCKED: {reason}" + (f" | Needs: {needs}" if needs else ""),
        msg_type="BLOCKED",
        related_task_id=related_task_id,
        payload=payload,
    )


async def broadcast_offering(
    db: Session,
    project_token: str,
    from_agent: str,
    offering: str,
    related_task_id: Optional[str] = None,
) -> AgentMessage:
    """Agent broadcasts what it is currently building (so others can wait)."""
    return await send_message(
        db, project_token, from_agent,
        f"🔨 BUILDING: {offering}",
        msg_type="OFFERING",
        related_task_id=related_task_id,
        payload={"offering": offering},
    )


async def broadcast_ready(
    db: Session,
    project_token: str,
    from_agent: str,
    what_is_ready: str,
    related_task_id: Optional[str] = None,
) -> AgentMessage:
    """Agent signals it finished something others may be waiting for."""
    return await send_message(
        db, project_token, from_agent,
        f"✅ READY: {what_is_ready} is now available",
        msg_type="READY",
        related_task_id=related_task_id,
        payload={"ready": what_is_ready},
    )


async def respond_to_blocker(
    db: Session,
    project_token: str,
    from_agent: str,
    to_agent: str,
    response: str,
    blocker_message_id: int,
    related_task_id: Optional[str] = None,
) -> AgentMessage:
    """Agent responds to another agent's BLOCKED message."""
    return await send_message(
        db, project_token, from_agent,
        f"💬 RESPONSE to {to_agent}: {response}",
        msg_type="RESPONSE",
        to_agent=to_agent,
        related_task_id=related_task_id,
        payload={"blocker_message_id": blocker_message_id},
    )


async def resolve_blocker(
    db: Session,
    project_token: str,
    message_id: int,
    resolved_by: str,
) -> Optional[AgentMessage]:
    """Mark a BLOCKED message as resolved."""
    msg = db.query(AgentMessage).filter(AgentMessage.id == message_id).first()
    if not msg:
        return None
    msg.resolved = True
    msg.resolved_by = resolved_by
    msg.resolved_at = datetime.utcnow()
    db.commit()
    db.refresh(msg)

    await _broadcast(msg.project_token, {**_serialize(msg), "_event": "resolved"})
    logger.info(f"Blocker #{message_id} resolved by {resolved_by}")
    return msg


# ── Query helpers ─────────────────────────────────────────────────────────────

def get_messages(
    db: Session,
    project_token: str,
    limit: int = 100,
    msg_type: Optional[str] = None,
    unresolved_only: bool = False,
) -> List[Dict[str, Any]]:
    q = db.query(AgentMessage).filter(AgentMessage.project_token == project_token)
    if msg_type:
        q = q.filter(AgentMessage.msg_type == msg_type)
    if unresolved_only:
        q = q.filter(AgentMessage.resolved == False)
    return [_serialize(m) for m in q.order_by(AgentMessage.created_at.desc()).limit(limit).all()]


def get_active_blockers(db: Session, project_token: str) -> List[Dict[str, Any]]:
    """Return all unresolved BLOCKED messages for a project."""
    return get_messages(db, project_token, msg_type="BLOCKED", unresolved_only=True)


# ── Auto-resolution logic ─────────────────────────────────────────────────────

async def check_and_auto_resolve(
    db: Session,
    project_token: str,
    from_agent: str,
    what_was_built: str,
) -> int:
    """
    Called when an agent finishes building something.
    Checks if any BLOCKED agents were waiting for this and resolves them.
    Returns count of resolved blockers.
    """
    blockers = db.query(AgentMessage).filter(
        AgentMessage.project_token == project_token,
        AgentMessage.msg_type == "BLOCKED",
        AgentMessage.resolved == False,
    ).all()

    resolved_count = 0
    what_lower = what_was_built.lower()

    for blocker in blockers:
        needs = (blocker.payload or {}).get("needs", "").lower()
        # Simple keyword match - if what was built matches what was needed
        if needs and any(kw in what_lower for kw in needs.split()):
            blocker.resolved = True
            blocker.resolved_by = from_agent
            blocker.resolved_at = datetime.utcnow()
            resolved_count += 1

            # Notify the blocked agent
            await send_message(
                db, project_token, from_agent,
                f"✅ AUTO-RESOLVED: {blocker.from_agent}'s blocker — '{what_was_built}' is now available. You can resume.",
                msg_type="RESOLVED",
                to_agent=blocker.from_agent,
                related_task_id=blocker.related_task_id,
            )

    if resolved_count:
        db.commit()
        logger.info(f"[{from_agent}] Auto-resolved {resolved_count} blocker(s) after building '{what_was_built}'")

    return resolved_count
