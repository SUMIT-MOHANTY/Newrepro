"""
Agent Communication Hooks - Wires agents into the communication service

This module provides hooks that agents call during execution to broadcast
their status, failures, and completions.
"""
import logging
from typing import Optional, Dict, Any
from app.core.database import SessionLocal
import agent_communication_service as comm

logger = logging.getLogger(__name__)


async def broadcast_task_started(
    project_token: str,
    agent_id: str,
    task: Dict[str, Any]
):
    """Agent broadcasts that it's starting a task"""
    db = SessionLocal()
    try:
        task_id = task.get("id") or task.get("task_id") or task.get("external_id") or "unknown"
        task_title = task.get("title") or task.get("taskName") or "Untitled Task"
        
        await comm.send_message(
            db=db,
            project_token=project_token,
            from_agent=agent_id,
            message=f"🏗️ Starting task: {task_title}",
            msg_type="OFFERING",
            related_task_id=str(task_id),
            payload={"task": task_title, "status": "started"}
        )
        logger.info(f"[{agent_id}] Broadcast task started: {task_title}")
    except Exception as e:
        logger.warning(f"[{agent_id}] Failed to broadcast task started: {e}")
    finally:
        db.close()


async def broadcast_task_completed(
    project_token: str,
    agent_id: str,
    task: Dict[str, Any],
    result: Dict[str, Any]
):
    """Agent broadcasts successful task completion"""
    db = SessionLocal()
    try:
        task_id = task.get("id") or task.get("task_id") or task.get("external_id") or "unknown"
        task_title = task.get("title") or task.get("taskName") or "Untitled Task"
        
        await comm.send_message(
            db=db,
            project_token=project_token,
            from_agent=agent_id,
            message=f"✅ Completed task: {task_title}",
            msg_type="READY",
            related_task_id=str(task_id),
            payload={
                "task": task_title,
                "status": "completed",
                "files_created": result.get("files_created", []),
                "branch": result.get("branch")
            }
        )
        logger.info(f"[{agent_id}] Broadcast task completed: {task_title}")
    except Exception as e:
        logger.warning(f"[{agent_id}] Failed to broadcast task completed: {e}")
    finally:
        db.close()


async def broadcast_task_failed(
    project_token: str,
    agent_id: str,
    task: Dict[str, Any],
    error: str,
    brd_impact: Optional[str] = None
):
    """Agent broadcasts task failure with BRD impact analysis"""
    db = SessionLocal()
    try:
        task_id = task.get("id") or task.get("task_id") or task.get("external_id") or "unknown"
        task_title = task.get("title") or task.get("taskName") or "Untitled Task"
        
        message = f"🚫 BLOCKED: Task failed - {task_title}\nError: {error[:200]}"
        if brd_impact:
            message += f"\n⚠️ BRD Impact: {brd_impact}"
        
        await comm.send_message(
            db=db,
            project_token=project_token,
            from_agent=agent_id,
            message=message,
            msg_type="BLOCKED",
            related_task_id=str(task_id),
            payload={
                "task": task_title,
                "status": "failed",
                "error": error,
                "brd_impact": brd_impact,
                "needs_help": True
            }
        )
        logger.error(f"[{agent_id}] Broadcast task failed: {task_title} - {error[:100]}")
    except Exception as e:
        logger.warning(f"[{agent_id}] Failed to broadcast task failure: {e}")
    finally:
        db.close()


async def broadcast_waiting_for_dependency(
    project_token: str,
    agent_id: str,
    task: Dict[str, Any],
    blocking_tasks: list
):
    """Agent broadcasts that it's waiting for dependencies"""
    db = SessionLocal()
    try:
        task_id = task.get("id") or task.get("task_id") or task.get("external_id") or "unknown"
        task_title = task.get("title") or task.get("taskName") or "Untitled Task"
        
        blocking_str = ", ".join(str(t) for t in blocking_tasks[:3])
        
        await comm.send_message(
            db=db,
            project_token=project_token,
            from_agent=agent_id,
            message=f"⏳ Waiting for dependencies: {blocking_str} before starting {task_title}",
            msg_type="INFO",
            related_task_id=str(task_id),
            payload={
                "task": task_title,
                "status": "waiting",
                "blocking_tasks": blocking_tasks
            }
        )
        logger.info(f"[{agent_id}] Broadcast waiting for dependencies: {blocking_str}")
    except Exception as e:
        logger.warning(f"[{agent_id}] Failed to broadcast dependency wait: {e}")
    finally:
        db.close()


async def broadcast_bootstrap_waiting(
    project_token: str,
    agent_id: str
):
    """Agent broadcasts that it's waiting for bootstrap"""
    db = SessionLocal()
    try:
        await comm.send_message(
            db=db,
            project_token=project_token,
            from_agent=agent_id,
            message=f"⏳ Waiting for bootstrap agent to create project scaffold...",
            msg_type="INFO",
            payload={"status": "waiting_bootstrap"}
        )
        logger.info(f"[{agent_id}] Broadcast waiting for bootstrap")
    except Exception as e:
        logger.warning(f"[{agent_id}] Failed to broadcast bootstrap wait: {e}")
    finally:
        db.close()
