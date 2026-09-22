import asyncio
import logging
import json
from datetime import datetime
from typing import Optional, Dict, Any

from database import SessionLocal
import models
from task_service import task_service
# Import get_project_task_token to resolve task tokens from memory state if possible
from agent_service import get_project_task_token

logger = logging.getLogger(__name__)


def _extract_note_id_from_response(data: Any) -> Optional[int]:
    """Helper to extract note ID from upstream API response dict."""
    if isinstance(data, dict):
        for key in ("id", "note_id"):
            value = data.get(key)
            if value not in (None, ""):
                try:
                    return int(value)
                except Exception:
                    continue
    return None


async def sync_single_log(db_session, log: models.NXDuneSyncLog) -> bool:
    """
    Attempt to sync a single sync log record to NXDune.
    Returns True if sync succeeded, False otherwise.
    """
    # 1. Resolve token: try in-memory token first, fallback to None (which triggers credentials auth)
    project_token = log.project_token
    task_token = get_project_task_token(project_token)
    
    op = log.operation
    payload = log.payload
    
    logger.info(f"[SyncWorker] Processing log {log.id}: {op} for project {project_token} (has_token={task_token is not None})")

    # Try to resolve task_id in payload to NXDune task ID, and skip if it is a local-only task
    if isinstance(payload, dict) and "task_id" in payload:
        raw_tid = payload["task_id"]
        try:
            task = db_session.query(models.Task).filter(
                models.Task.project_token == project_token,
                ((models.Task.id == raw_tid) | (models.Task.task_id == raw_tid) | (models.Task.task_id.like(f"%_{raw_tid}")))
            ).first()
            if task:
                if task.nxdune_task_id:
                    payload["task_id"] = task.nxdune_task_id
                else:
                    logger.info(f"[SyncWorker] Task '{raw_tid}' has not been synced to NXDune yet. Skipping operation '{op}' sync (local-only task).")
                    return True
        except Exception as res_err:
            logger.warning(f"[SyncWorker] Error resolving task ID for NXDune sync: {res_err}")

    
    try:
        if op == "task_message":
            # Payload schema: {"task_id": int/str, "message": str}
            await task_service.post_task_message(payload, task_token=task_token)
            
        elif op == "task_progress":
            # Payload schema: {"task_id": int/str, "task_progress": int, "additional_info": str}
            await task_service.update_task_progress(payload, task_token=task_token)
            
        elif op == "task_complete":
            # Payload schema: {"task_id": int/str}
            await task_service.complete_task(payload, task_token=task_token)
            
        elif op == "timer_log":
            # Payload schema: timer clock logs
            await task_service.post_timer_log(payload, task_token=task_token)
            
        elif op == "opt_in_task":
            # Payload schema: opt-in logs
            await task_service.opt_in_task(payload, task_token=task_token)
            
        elif op == "note_upsert":
            # Payload schema: {"title": str, "content": str, "user": str, "note_id": Optional[int]}
            result = await task_service.upsert_note(payload, task_token=task_token)
            
            # Backfill note ID in local AgentNote table if note_upsert succeeded
            title = payload.get("title")
            if title:
                resolved_note_id = _extract_note_id_from_response(result)
                note = db_session.query(models.AgentNote).filter(
                    models.AgentNote.project_token == project_token,
                    models.AgentNote.title == title
                ).first()
                if note:
                    note.synced_to_nxdune = True
                    if resolved_note_id is not None:
                        note.nxdune_note_id = resolved_note_id
                        
        else:
            logger.error(f"[SyncWorker] Unknown operation type '{op}' in log {log.id}")
            return False
            
        # If we got here, request was successful!
        return True
        
    except Exception as e:
        logger.warning(f"[SyncWorker] Sync failed for log {log.id} (op={op}): {e}")
        return False


async def trigger_nxdune_sync_now(db_session, project_token: Optional[str] = None) -> dict:
    """
    Manual, one-time sync trigger for pending NXDune logs.
    Executes a single pass over unsynced logs without automatic retry loops.
    """
    logger.info(f"[ManualSync] Executing one-time NXDune sync for project={project_token}...")
    
    query = db_session.query(models.NXDuneSyncLog).filter(
        models.NXDuneSyncLog.success == False,
        models.NXDuneSyncLog.permanently_failed == False
    )
    if project_token:
        query = query.filter(models.NXDuneSyncLog.project_token == project_token)
        
    pending_logs = query.order_by(models.NXDuneSyncLog.created_at.asc()).limit(50).all()
    
    if not pending_logs:
        return {
            "status": "success",
            "message": "No pending logs to sync.",
            "total": 0,
            "succeeded": 0,
            "failed": 0
        }
        
    succeeded_count = 0
    failed_count = 0
    
    for log in pending_logs:
        success = await sync_single_log(db_session, log)
        log.success = success
        log.retry_count = (log.retry_count or 0) + 1
        log.last_retry_at = datetime.utcnow()
        
        if success:
            succeeded_count += 1
        else:
            failed_count += 1
            if log.retry_count >= 3:
                log.permanently_failed = True
                
        db_session.commit()
        await asyncio.sleep(0.05)
        
    return {
        "status": "completed",
        "message": f"Sync completed. {succeeded_count} succeeded, {failed_count} failed out of {len(pending_logs)} pending logs.",
        "total": len(pending_logs),
        "succeeded": succeeded_count,
        "failed": failed_count
    }


async def run_nxdune_sync_worker():
    """
    Background worker loop - Disabled by default to prevent performance impact when NXDune is offline.
    Manual syncing is available via the Plugins page button or POST /api/nxdune/sync-now.
    """
    logger.info("[SyncWorker] Automatic NXDune background worker is disabled to protect system performance. Use manual sync on Plugins page.")
    return
