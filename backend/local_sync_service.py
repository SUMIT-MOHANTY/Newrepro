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


async def run_nxdune_sync_worker():
    """
    Background worker loop that polls for unsynced logs and syncs them to NXDune.
    Runs continuously with a delay between poll runs.
    """
    logger.info("[SyncWorker] Starting NXDune background synchronization worker...")
    
    poll_interval_seconds = 10.0
    
    while True:
        try:
            db = SessionLocal()
            try:
                # Fetch pending sync logs that are not permanently failed
                pending_logs = db.query(models.NXDuneSyncLog).filter(
                    models.NXDuneSyncLog.success == False,
                    models.NXDuneSyncLog.permanently_failed == False
                ).order_by(models.NXDuneSyncLog.created_at.asc()).limit(20).all()
                
                if pending_logs:
                    logger.info(f"[SyncWorker] Found {len(pending_logs)} pending sync logs to process.")
                    
                    for log in pending_logs:
                        success = await sync_single_log(db, log)
                        
                        log.success = success
                        log.retry_count = (log.retry_count or 0) + 1
                        log.last_retry_at = datetime.utcnow()
                        
                        # Cap retries at 5 attempts
                        if not success and log.retry_count >= 5:
                            log.permanently_failed = True
                            logger.error(f"[SyncWorker] Log {log.id} (op={log.operation}) has failed 5 times. Marking permanently failed.")
                            
                        db.commit()
                        
                        # Yield control to allow other tasks to run
                        await asyncio.sleep(0.1)
            except Exception as loop_err:
                db.rollback()
                logger.error(f"[SyncWorker] Error during sync poll execution: {loop_err}")
            finally:
                db.close()
                
        except Exception as outer_err:
            logger.error(f"[SyncWorker] Outer loop exception: {outer_err}")
            
        # Wait before next poll
        await asyncio.sleep(poll_interval_seconds)
