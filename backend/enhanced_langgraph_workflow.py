low_part2.py
            "errors": errors,
        }


def _route_after_planning(state: EnhancedAgentState) -> str:
    if state.get("assignments"):
        return "run_coordinated_agents"
    return "finalize"


# ═══════════════════════════════════════════════════════════════════════════
# PHASE 3: COORDINATED AGENT EXECUTION WITH SELF-HEALING
# ═══════════════════════════════════════════════════════════════════════════

# This will be implemented in the next file due to size limits
# Continue in enhanced_langgraph_workf           task_token=state.get("task_token"),
        )
        
        assignments = [
            {"agent_id": agent_id, "assigned_task": task}
            for agent_id, task in claimed.get("assignments", [])
        ]
        
        return {"assignments": assignments}
        
    except Exception as exc:
        logger.warning("Task planning failed: %s", exc)
        errors = list(state.get("errors") or [])
        errors.append(f"planning: {str(exc)}")
        return {
            "assignments": [],
═══════════════════════
# PHASE 2: TASK PLANNING WITH COORDINATION
# ═══════════════════════════════════════════════════════════════════════════

async def _plan_assignments_with_coordination(state: EnhancedAgentState) -> Dict[str, Any]:
    """Plan task assignments with dependency awareness"""
    import agent_service
    
    try:
        claimed = await agent_service._claim_initial_task_assignments(
            agents_config=state.get("agents_config"),
            project_token=state.get("project_token"),
 
        level="error",
        project_token=state.get("project_token"),
    )
    
    return {
        "summary": {
            "workflow": "enhanced_langgraph",
            "status": "paused_for_intervention",
            "reason": "bootstrap_failure",
            "error": state.get("bootstrap_state", {}).get("error_message"),
            "message": "Bootstrap failed. Please review logs and restart workflow after fixing the issue."
        }
    }


# ════════════════════════════════════════════════════n bootstrap outcome"""
    if state.get("requires_intervention"):
        return "wait_for_intervention"
    if state.get("bootstrap_state", {}).get("status") == "success":
        return "plan_assignments"
    return "finalize"


async def _wait_for_intervention(state: EnhancedAgentState) -> Dict[str, Any]:
    """Pause workflow and wait for human intervention"""
    import agent_service
    
    agent_service._log_master_agent(
        "⏸️ Workflow paused - bootstrap failed. Manual intervention required.",t.get('title')}",
        project_token=project_token,
    )
    
    bootstrap_state["status"] = "success"
    phase_gates = state.get("phase_gates", {})
    phase_gates["bootstrap"] = True
    
    return {
        "master_note": result,
        "bootstrap_state": bootstrap_state,
        "phase_gates": phase_gates,
        "current_phase": "development",
        "errors": errors,
        "requires_intervention": False
    }


def _route_after_bootstrap(state: EnhancedAgentState) -> str:
    """Route based oclose()
    
    # Broadcast success
    db = SessionLocal()
    try:
        await comm.send_message(
            db=db,
            project_token=project_token or "",
            from_agent="MASTER_AGENT",
            message=f"✅ Bootstrap complete! Project structure ready. Agents can now start working.",
            msg_type="READY",
            payload={"bootstrap_success": True}
        )
    finally:
        db.close()
    
    agent_service._log_master_agent(
        f"✅ Master plan note published: {resulpersist to DB
    db = SessionLocal()
    try:
        bootstrap_record = db.query(BootstrapState).filter(
            BootstrapState.project_token == project_token
        ).first()
        if bootstrap_record:
            bootstrap_record.status = "success"
            bootstrap_record.completed_at = datetime.utcnow()
            bootstrap_record.master_note_id = result.get("note_id")
            bootstrap_record.workspace_tree = result.get("workspace_tree")
            db.commit()
    finally:
        db.db.close()
        
        agent_service._log_master_agent(
            f"⚠️ Master plan note failed: {reason}",
            level="warning",
            project_token=project_token,
        )
        
        bootstrap_state["status"] = "failed"
        bootstrap_state["error_message"] = str(reason)
        
        return {
            "master_note": result,
            "bootstrap_state": bootstrap_state,
            "errors": errors,
            "requires_intervention": True
        }
    
    # Success -   db.close()
        
        # Broadcast failure to all agents
        db = SessionLocal()
        try:
            await comm.send_message(
                db=db,
                project_token=project_token or "",
                from_agent="MASTER_AGENT",
                message=f"🚫 Bootstrap failed: {reason}. All agents blocked until this is resolved.",
                msg_type="BLOCKED",
                payload={"bootstrap_failure": True, "error": str(reason)}
            )
        finally:
             note: {reason}")
        
        # Persist failure to DB
        db = SessionLocal()
        try:
            bootstrap_record = db.query(BootstrapState).filter(
                BootstrapState.project_token == project_token
            ).first()
            if bootstrap_record:
                bootstrap_record.status = "failed"
                bootstrap_record.completed_at = datetime.utcnow()
                bootstrap_record.error_message = str(reason)
                db.commit()
        finally:
             state.get("agents_config"),
        project_token=project_token,
    )
    
    result = await agent_service.ensure_master_workspace_note(
        project_token=project_token,
        task_token=state.get("task_token"),
    )
    
    errors = list(state.get("errors") or [])
    bootstrap_state = state.get("bootstrap_state", {})
    
    if not result.get("success") and not result.get("skipped"):
        reason = result.get("error") or result.get("reason") or "unknown error"
        errors.append(f"masterootstrap_record = db.query(BootstrapState).filter(
            BootstrapState.project_token == project_token
        ).first()
        if bootstrap_record:
            bootstrap_record.status = "running"
            bootstrap_record.started_at = datetime.utcnow()
            db.commit()
    finally:
        db.close()
    
    agent_service._log_master_agent(
        "📋 Creating canonical project tree note...",
        project_token=project_token,
    )
    
    agent_service.prime_project_git_credentials(
     _found": [],
        "errors": []
    }


async def _publish_master_workspace_note_with_recovery(state: EnhancedAgentState) -> Dict[str, Any]:
    """Bootstrap with persistent state and failure broadcasting"""
    import agent_service
    import agent_communication_service as comm
    from database import SessionLocal
    from models_bootstrap_state import BootstrapState
    
    project_token = state.get("project_token")
    
    # Update bootstrap state to running
    db = SessionLocal()
    try:
        btures
    return {
        "bootstrap_state": bootstrap_state,
        "agent_statuses": {},
        "active_blockers": [],
        "communication_log": [],
        "failed_tasks": [],
        "fix_tasks_created": [],
        "retry_count": 0,
        "max_retries": 3,
        "current_phase": "bootstrap",
        "phase_gates": {
            "bootstrap": False,
            "development": False,
            "integration": False,
            "testing": False,
            "deployment": False
        },
        "bugsrecord)
        
        bootstrap_state = {
            "status": bootstrap_record.status,
            "started_at": bootstrap_record.started_at.isoformat() if bootstrap_record.started_at else None,
            "completed_at": bootstrap_record.completed_at.isoformat() if bootstrap_record.completed_at else None,
            "error_message": bootstrap_record.error_message,
            "master_note_id": bootstrap_record.master_note_id,
        }
    finally:
        db.close()
    
    # Initialize coordination strucate.get("project_token")
    
    # Load or create bootstrap state from DB
    db = SessionLocal()
    try:
        bootstrap_record = db.query(BootstrapState).filter(
            BootstrapState.project_token == project_token
        ).first()
        
        if not bootstrap_record:
            bootstrap_record = BootstrapState(
                project_token=project_token,
                status="pending"
            )
            db.add(bootstrap_record)
            db.commit()
            db.refresh(bootstrap_
_CHECKPOINTER = InMemorySaver()


# ═══════════════════════════════════════════════════════════════════════════
# PHASE 1: BOOTSTRAP WITH PERSISTENT STATE
# ═══════════════════════════════════════════════════════════════════════════

async def _initialize_workflow(state: EnhancedAgentState) -> Dict[str, Any]:
    """Initialize workflow with persistent state loading"""
    import agent_service
    from database import SessionLocal
    from models_bootstrap_state import BootstrapState
    
    project_token = stist[Dict[str, Any]]
    fix_tasks_created: List[Dict[str, Any]]
    retry_count: int
    max_retries: int
    
    # BRD validation
    brd_coverage: Dict[str, Any]
    missing_requirements: List[str]
    
    # Phase gates
    current_phase: str
    phase_gates: Dict[str, bool]
    
    # Integration testing
    integration_test_results: Dict[str, Any]
    bugs_found: List[Dict[str, Any]]
    
    # Final state
    errors: List[str]
    merge_queue_drained: bool
    summary: Dict[str, Any]

 Dict[str, Dict[str, str]]
    brd_analysis: Dict[str, Any]
    
    # Bootstrap tracking
    bootstrap_state: Dict[str, Any]
    master_note: Dict[str, Any]
    
    # Task management
    assignments: List[Dict[str, Any]]
    launched_agents: List[str]
    results: List[Dict[str, Any]]
    
    # Coordination state
    agent_statuses: Dict[str, str]  # agent_id -> status
    active_blockers: List[Dict[str, Any]]
    communication_log: List[Dict[str, Any]]
    
    # Self-healing tracking
    failed_tasks: Ling and bug fixing loops
6. Phase gates (dev → integration → testing → deployment)
"""
import asyncio
import logging
import uuid
from typing import Any, Dict, List, Optional, TypedDict
from datetime import datetime

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

logger = logging.getLogger(__name__)


class EnhancedAgentState(TypedDict, total=False):
    # Project context
    project_token: Optional[str]
    task_token: Optional[str]
    agents_config:trap state (survives restarts)
2. Real-time agent communication (BLOCKED/OFFERING/READY)
3. Automatic failure detection and recovery
4. BRD-aware validation and gap filling
5. Integration testhanced LangGraph Workflow with Full Self-Healing Agent Coordination

This workflow implements:
1. Persistent boots"""
En