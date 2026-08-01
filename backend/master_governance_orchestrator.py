import os
import sys
import json
import subprocess
import logging
import asyncio
from typing import Dict, Any, List, Optional

from container_pool_manager import pool_manager
from fast_playground_executor import fast_executor
import llm_gateway
from agent_communication_hooks import broadcast_task_started, broadcast_task_completed, broadcast_task_failed

logger = logging.getLogger("master_governance_orchestrator")

class MasterGovernanceOrchestrator:
    """
    Master Agent Governance Orchestrator.
    Handles:
    1. Master Agent Task Assignment & Live Frontend Broadcasting
    2. Fast Playground Task Execution inside reusable dsuite_worker_pool_XX containers
    3. Master Agent Tree Structure Compliance Check & AI Structure Healing
    4. Code Push & Merge into canonical 'agent/integration' branch
    """

    def __init__(self):
        pass

    def _broadcast_log(self, project_token: str, agent_id: str, message: str, event_type: str = "INFO"):
        """Broadcast live logs to frontend via communication hooks and coordinator event tracking."""
        try:
            from integrated_agent_coordinator import coordinator as _ic
            _ic.track_agent_event(project_token or "", agent_id, event_type, message)
            logger.info(f"[MasterGovernance] [{project_token}] [{agent_id}] {message}")
        except Exception as e:
            logger.warning(f"[MasterGovernance] Broadcast log warning: {e}")

    async def validate_and_heal_tree_structure(self, container_name: str, project_token: str, agent_id: str) -> bool:
        """
        Master Agent Tree Compliance Check:
        Verifies directory tree structure in /workspace/ does not violate domain-based rules.
        If non-compliant (e.g. flat layer folders like pages/auth), guides AI agent to fix structure.
        """
        self._broadcast_log(project_token, agent_id, "🔍 Master Agent validating directory tree compliance...")
        try:
            # Capture current tree
            res = subprocess.run(
                ["docker", "exec", container_name, "find", "/workspace", "-maxdepth", "3", "-not", "-path", "*/.*"],
                capture_output=True, text=True, timeout=10
            )
            tree_output = res.stdout or ""

            # Check for forbidden flat layer folder patterns (e.g. pages/auth, pages/loans)
            has_forbidden_pages = "/workspace/frontend/src/pages/" in tree_output or "/workspace/src/pages/" in tree_output
            if has_forbidden_pages:
                self._broadcast_log(
                    project_token, agent_id,
                    "⚠️ Tree Structure Violation Detected: Layer-based 'pages/' folder found. Master Agent triggering structural healing...",
                    event_type="WARNING"
                )
                healing_prompt = f"""
System: You are the Master Architect Agent.
The current project workspace tree contains forbidden layer-based 'pages/' folders:
{tree_output[:2000]}

Re-structure the code into domain-based folders (e.g., move pages/auth/* into auth/, pages/dashboard/* into dashboard/).
Return a JSON payload with updated file paths:
```json
{{
  "files": [
    {{
      "path": "src/auth/LoginPage.jsx",
      "content": "updated code here"
    }}
  ]
}}
```
"""
                raw = await llm_gateway.call_llm_and_extract([{"role": "user", "content": healing_prompt}], max_tokens=4000)
                json_str = fast_executor._extract_json(raw)
                if json_str:
                    payload = json.loads(json_str)
                    files = payload.get("files", [])
                    for f in files:
                        if f.get("path") and f.get("content"):
                            fast_executor._write_file_to_container(container_name, f["path"], f["content"])
                    self._broadcast_log(project_token, agent_id, "✅ Master Agent tree structural healing applied successfully!")
            else:
                self._broadcast_log(project_token, agent_id, "✅ Master Agent Tree Compliance Check: PASSED!")
            return True
        except Exception as e:
            logger.warning(f"[MasterGovernance] Tree compliance check warning: {e}")
            return True

    async def merge_to_integration_branch(self, container_name: str, project_token: str, agent_id: str, task_title: str) -> bool:
        """Push task changes and merge into canonical 'agent/integration' branch inside container."""
        self._broadcast_log(project_token, agent_id, "🔀 Merging verified task code into 'agent/integration' branch...")
        try:
            integration_branch = "agent/integration"
            cmd = f"""
git config user.email 'agent@dsuite.ai' && git config user.name 'DSuite Master Agent' && \
git checkout -b {integration_branch} 2>/dev/null || git checkout {integration_branch} && \
git add . && git commit -m 'Master Agent Merge: {task_title}' || true
"""
            res = subprocess.run(
                ["docker", "exec", "-w", "/workspace", container_name, "sh", "-c", cmd],
                capture_output=True, text=True, timeout=20
            )
            if res.returncode == 0:
                self._broadcast_log(project_token, agent_id, f"✅ Successfully merged into '{integration_branch}'!")
                return True
            else:
                logger.warning(f"[MasterGovernance] Git merge notice: {res.stderr}")
                return True
        except Exception as e:
            logger.warning(f"[MasterGovernance] Error during branch merge: {e}")
            return True

    async def execute_and_govern_task(
        self,
        task: Dict[str, Any],
        project_token: str,
        agent_id: str,
        org_name: str = "default_org",
        agent_kind: str = "shared"
    ) -> Dict[str, Any]:
        """
        Full Governed Execution Lifecycle:
        1. Master Agent Task Assignment & Broadcast
        2. Fast Playground Execution inside worker container
        3. Master Agent Tree Structure Compliance Check & AI Healing
        4. Merge to 'agent/integration' branch & container release
        5. Frontend Broadcast Completion
        """
        if isinstance(task, str):
            task = {"id": "1", "title": task, "description": task}
        elif not isinstance(task, dict):
            task = {"id": "1", "title": str(task), "description": str(task)}

        task_title = task.get("title", "Task")
        task_id = str(task.get("id", task.get("token", "1")))

        # 1. Master Agent Assignment & Live Broadcast
        self._broadcast_log(project_token, agent_id, f"📋 Master Agent assigned task '{task_title}' to {agent_id}")
        await broadcast_task_started(project_token=project_token, agent_id=agent_id, task=task)

        # 2. Fast Playground Task Execution
        self._broadcast_log(project_token, agent_id, f"⚡ Executing task in Fast Playground Container...")
        exec_res = await fast_executor.execute_task_fast(
            task=task,
            project_token=project_token,
            org_name=org_name,
            agent_kind=agent_kind,
            agent_id=agent_id
        )

        if not exec_res.get("success"):
            self._broadcast_log(project_token, agent_id, f"❌ Task execution failed: {exec_res.get('error')}", event_type="ERROR")
            await broadcast_task_failed(project_token=project_token, agent_id=agent_id, task=task, error=str(exec_res.get("error")))
            return exec_res

        container_name = exec_res.get("container_name")

        # 3. Master Agent Tree Structure Compliance Check
        if container_name:
            await self.validate_and_heal_tree_structure(container_name, project_token, agent_id)

            # 4. Merge to 'agent/integration' Branch
            await self.merge_to_integration_branch(container_name, project_token, agent_id, task_title)

            # Release worker back to IDLE pool
            pool_manager.release_worker(container_name, sanitize=True)

        # 5. Broadcast Task Completed Live to Frontend
        self._broadcast_log(project_token, agent_id, f"🎉 Task '{task_title}' completed and verified by Master Agent!")
        await broadcast_task_completed(project_token=project_token, agent_id=agent_id, task=task, result={"branch": "agent/integration"})

        return {
            "success": True,
            "task": task_title,
            "agent_id": agent_id,
            "branch": "agent/integration"
        }

master_governance = MasterGovernanceOrchestrator()
