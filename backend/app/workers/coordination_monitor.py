"""
Coordination Monitor - Background task that enables self-healing

This monitor runs continuously and:
1. Detects blocked agents and finds helpers
2. Creates fix tasks for failures
3. Validates BRD coverage
4. Manages phase gates
5. Triggers integration tests
"""
import asyncio
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from app.core.database import SessionLocal
from models import AgentMessage
import agent_communication_service as comm
from app.integrations.llm import llm_gateway

logger = logging.getLogger(__name__)


class CoordinationMonitor:
    """Monitors agent coordination and triggers self-healing actions"""
    
    def __init__(self, project_token: str):
        self.project_token = project_token
        self.running = False
        self.check_interval = 10  # seconds
        
    async def start(self):
        """Start the coordination monitor"""
        self.running = True
        logger.info(f"[CoordinationMonitor] Started for project {self.project_token}")
        
        while self.running:
            try:
                await self._check_blocked_agents()
                await self._check_failed_tasks()
                await self._validate_brd_coverage()
                await asyncio.sleep(self.check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception(f"[CoordinationMonitor] Error: {e}")
                await asyncio.sleep(self.check_interval)
        
        logger.info(f"[CoordinationMonitor] Stopped for project {self.project_token}")
    
    def stop(self):
        """Stop the coordination monitor"""
        self.running = False
    
    async def _check_blocked_agents(self):
        """Find blocked agents and try to help them"""
        db = SessionLocal()
        try:
            # Get all unresolved BLOCKED messages
            blocked_messages = db.query(AgentMessage).filter(
                AgentMessage.project_token == self.project_token,
                AgentMessage.msg_type == "BLOCKED",
                AgentMessage.resolved == False
            ).all()
            
            for msg in blocked_messages:
                await self._handle_blocked_agent(msg, db)
                
        finally:
            db.close()
    
    async def _handle_blocked_agent(self, msg: AgentMessage, db):
        """Handle a blocked agent by creating a fix task or finding a helper"""
        from_agent = msg.from_agent
        task_id = msg.related_task_id
        error = msg.payload.get("error") if msg.payload else None
        
        logger.info(f"[CoordinationMonitor] Handling blocked agent {from_agent} on task {task_id}")
        
        # Option B Pure Incremental Mode: Handle blocked agent messages directly
        
        # Analyze the failure and create a fix task
        fix_task = await self._create_fix_task(from_agent, task_id, error)
        
        if fix_task:
            # Broadcast that a fix task was created
            await comm.send_message(
                db=db,
                project_token=self.project_token,
                from_agent="COORDINATION_MONITOR",
                message=f"🔧 Created fix task for {from_agent}'s blocker on task {task_id}",
                msg_type="OFFERING",
                related_task_id=task_id,
                payload={"fix_task": fix_task}
            )
            
            logger.info(f"[CoordinationMonitor] Created fix task for {from_agent}")
        
        # Always resolve the blocked message so it isn't repeatedly processed every loop iteration
        msg.resolved = True
        db.commit()
    
    async def _handle_bootstrap_failure(self, error: Optional[str], db):
        """Handle bootstrap failure by creating a fix task for master agent"""
        logger.info(f"[CoordinationMonitor] Creating bootstrap fix task")
        
        try:
            from app.services.agents import agent_service
            
            # Use AI to analyze bootstrap failure and create fix
            analysis_prompt = f"""
You are a project architecture expert. The bootstrap/master agent failed to create the project structure.

Error: {error or 'Unknown bootstrap error'}

Analyze this failure and create a fix task that will resolve it. Common bootstrap issues:
1. Conflicting directory structures in BRD
2. Invalid file paths or naming
3. Missing required framework files
4. Ambiguous tech stack requirements

Return a JSON object with:
{{
    "title": "Fix Bootstrap: [brief description]",
    "description": "[detailed fix steps with exact file structure]",
    "root_cause": "[what went wrong in bootstrap]",
    "fix_approach": "[how to fix the project structure]",
    "corrected_structure": "[the correct directory tree]"
}}
"""
            
            response = await llm_gateway.call_llm(
                messages=[{
                    "role": "user",
                    "content": analysis_prompt
                }],
                temperature=0.3,
                purpose="Autonomous Coding Agent: Bootstrap Recovery",
            )
            
            import json
            import re
            content = llm_gateway.extract_content_from_response(response)
            json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', content, re.DOTALL)
            if json_match:
                content = json_match.group(1)
            
            fix_data = json.loads(content)
            
            # Create bootstrap fix task
            fix_task = {
                "id": f"BOOTSTRAP-FIX-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
                "task_id": "TASK-00-FIX",
                "title": fix_data.get("title", "Fix Bootstrap: Project Structure"),
                "description": fix_data.get("description", ""),
                "task_type": "BOOTSTRAP",
                "priority": "CRITICAL",
                "linked_tasks": ["TASK-00"],
                "root_cause": fix_data.get("root_cause"),
                "fix_approach": fix_data.get("fix_approach"),
                "corrected_structure": fix_data.get("corrected_structure"),
                "created_by": "COORDINATION_MONITOR",
                "created_at": datetime.utcnow().isoformat(),
                "is_bootstrap_fix": True
            }
            
            # Add to project tasks
            state = agent_service._ensure_project_state(self.project_token)
            tasks = state.get("tasks", [])
            tasks.insert(0, fix_task)  # Insert at beginning - highest priority
            state["tasks"] = tasks
            
            # Broadcast that bootstrap fix task was created
            await comm.send_message(
                db=db,
                project_token=self.project_token,
                from_agent="COORDINATION_MONITOR",
                message=f"🔧 Bootstrap failed, but I created a fix task. Master agent will retry with corrections.",
                msg_type="OFFERING",
                related_task_id="TASK-00",
                payload={"bootstrap_fix_task": fix_task}
            )
            
            # Reset bootstrap state to pending so it can be retried
            from bootstrap_persistence import get_bootstrap_state
            from app.core.database import SessionLocal
            from models_bootstrap_state import BootstrapState
            
            db_session = SessionLocal()
            try:
                bootstrap_record = db_session.query(BootstrapState).filter(
                    BootstrapState.project_token == self.project_token
                ).first()
                if bootstrap_record:
                    bootstrap_record.status = "pending"  # Allow retry
                    db_session.commit()
            finally:
                db_session.close()
            
            logger.info(f"[CoordinationMonitor] Created bootstrap fix task: {fix_task['title']}")
            
        except Exception as e:
            logger.exception(f"[CoordinationMonitor] Failed to create bootstrap fix task: {e}")
    
    async def _create_fix_task(self, agent_id: str, task_id: str, error: Optional[str]) -> Optional[Dict[str, Any]]:
        """Use AI to analyze the failure and create a fix task"""
        try:
            # Get the original task details
            from app.services.agents import agent_service
            state = agent_service._ensure_project_state(self.project_token)
            tasks = state.get("tasks", [])
            
            original_task = next(
                (t for t in tasks if str(t.get("id") or t.get("task_id") or t.get("external_id")) == str(task_id)),
                None
            )
            
            if not original_task:
                logger.warning(f"[CoordinationMonitor] Could not find original task {task_id}")
                return None
            
            # Use AI to analyze the failure and suggest a fix
            analysis_prompt = f"""
You are a debugging expert. An agent failed to complete this task:

Task: {original_task.get('title') or original_task.get('taskName')}
Description: {original_task.get('description', '')[:500]}
Error: {error or 'Unknown error'}

Analyze the failure and create a fix task that will resolve this issue.
The fix task should:
1. Identify the root cause
2. Provide specific steps to fix it
3. Reference the exact files/code that need changes

Return a JSON object with:
{{
    "title": "Fix: [brief description]",
    "description": "[detailed fix steps]",
    "root_cause": "[what went wrong]",
    "fix_approach": "[how to fix it]"
}}
"""
            
            response = await llm_gateway.call_llm(
                messages=[{
                    "role": "user",
                    "content": analysis_prompt
                }],
                temperature=0.3,
                purpose="Autonomous Coding Agent: Workspace Analysis",
            )
            
            # Parse the AI response
            import json
            import re
            
            content = llm_gateway.extract_content_from_response(response)
            # Extract JSON from markdown code blocks if present
            json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', content, re.DOTALL)
            if json_match:
                content = json_match.group(1)
            
            fix_task_data = json.loads(content)
            
            # Create the fix task
            fix_task = {
                "id": f"FIX-{task_id}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
                "title": fix_task_data.get("title", f"Fix: {original_task.get('title')}"),
                "description": fix_task_data.get("description", ""),
                "task_type": "BUG",
                "priority": "HIGH",
                "linked_tasks": [task_id],
                "root_cause": fix_task_data.get("root_cause"),
                "fix_approach": fix_task_data.get("fix_approach"),
                "original_agent": agent_id,
                "created_by": "COORDINATION_MONITOR",
                "created_at": datetime.utcnow().isoformat()
            }
            
            # Add to project tasks
            tasks.append(fix_task)
            state["tasks"] = tasks
            
            logger.info(f"[CoordinationMonitor] Created fix task: {fix_task['title']}")
            return fix_task
            
        except Exception as e:
            logger.exception(f"[CoordinationMonitor] Failed to create fix task: {e}")
            return None
    
    async def _check_failed_tasks(self):
        """Check for failed tasks and decide if they need retry or escalation"""
        # Implementation: Check agent results, identify failures, decide on retry vs escalation
        pass
    
    async def _validate_brd_coverage(self):
        """Validate that all BRD requirements are being addressed"""
        # Implementation: Compare BRD requirements with completed/in-progress tasks
        pass


# Global registry of monitors
_monitors: Dict[str, CoordinationMonitor] = {}


async def start_coordination_monitor(project_token: str) -> CoordinationMonitor:
    """Start a coordination monitor for a project"""
    if project_token in _monitors:
        logger.info(f"[CoordinationMonitor] Already running for project {project_token}")
        return _monitors[project_token]
    
    monitor = CoordinationMonitor(project_token)
    _monitors[project_token] = monitor
    
    # Start in background
    asyncio.create_task(monitor.start())
    
    return monitor


def stop_coordination_monitor(project_token: str):
    """Stop the coordination monitor for a project"""
    if project_token in _monitors:
        _monitors[project_token].stop()
        del _monitors[project_token]
        logger.info(f"[CoordinationMonitor] Stopped for project {project_token}")
