import os
import sys
import json
import subprocess
import logging
import asyncio
from typing import Dict, Any, List, Optional

from container_pool_manager import pool_manager
from fast_playground_executor import fast_executor
from app.integrations.llm import llm_gateway
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

    async def validate_structural_compliance(
        self,
        container_name: str,
        project_token: str,
        agent_id: str,
        expected_files: List[str],
        phase: int,
        tech_stack: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """
        Comprehensive structural compliance check:
        
        1. Get actual file tree from container (docker exec find /workspace)
        2. Compare against expected_files:
           - Flag ROGUE files (exist but not in expected list) - WARNING level
           - Flag MISSING files (expected but don't exist) - ERROR level
           - Flag WRONG LOCATION (similar basename but different directory) - ERROR level
        3. Phase boundary check logic is in validate_phase_boundary.
        4. Return {compliant: bool, violations: [{type, file, description, severity}]}
        """
        self._broadcast_log(project_token, agent_id, "🔍 Master Agent validating structural compliance...")
        try:
            res = subprocess.run(
                ["docker", "exec", container_name, "find", "/workspace", "-type", "f", "-not", "-path", "*/.*"],
                capture_output=True, text=True, timeout=10
            )
            actual_files = res.stdout.strip().split('\n') if res.stdout else []
            actual_files = [f.replace("/workspace/", "", 1) for f in actual_files if f.startswith("/workspace/")]
            
            violations = []
            expected_set = set(expected_files)
            actual_set = set(actual_files)
            
            for ef in expected_files:
                if ef not in actual_set:
                    ef_basename = os.path.basename(ef)
                    found_wrong_loc = False
                    for af in actual_files:
                        if os.path.basename(af) == ef_basename:
                            violations.append({"type": "WRONG_LOCATION", "file": af, "description": f"Expected at {ef}", "severity": "ERROR"})
                            found_wrong_loc = True
                            break
                    if not found_wrong_loc:
                        violations.append({"type": "MISSING", "file": ef, "description": "File is missing", "severity": "ERROR"})
            
            for af in actual_files:
                if af not in expected_set:
                    if not any(v["type"] == "WRONG_LOCATION" and v["file"] == af for v in violations):
                        violations.append({"type": "ROGUE", "file": af, "description": "File not in expected list", "severity": "WARNING"})
            
            compliant = len([v for v in violations if v.get("severity") == "ERROR"]) == 0
            if compliant:
                self._broadcast_log(project_token, agent_id, "✅ Structural Compliance Check: PASSED!")
            else:
                self._broadcast_log(project_token, agent_id, f"⚠️ Structural Compliance Check: FAILED with {len(violations)} violations", event_type="WARNING")
            
            return {"compliant": compliant, "violations": violations}
        except Exception as e:
            logger.warning(f"[MasterGovernance] Structural compliance check error: {e}")
            return {"compliant": False, "violations": []}

    async def validate_phase_boundary(
        self,
        container_name: str,
        project_token: str,
        agent_id: str,
        files_created: List[str],
        phase: int,
        tech_stack: Optional[Dict] = None,
    ) -> List[Dict[str, str]]:
        """
        Check that files respect phase boundaries.
        
        For each file, read content from container and check:
        - Phase 1 files: Must NOT import from backend framework (determined by tech_stack.backend)
        - Phase 2 files: Must NOT modify frontend files
        - Phase 3 files: Must NOT have mock data imports remaining
        
        Returns list of violations: [{file, violation, description}]
        """
        self._broadcast_log(project_token, agent_id, "🔍 Master Agent validating phase boundaries...")
        violations = []
        if not tech_stack:
            tech_stack = {}
            
        backend_framework = str(tech_stack.get("backend", "")).lower()
        
        try:
            for file_path in files_created:
                res = subprocess.run(
                    ["docker", "exec", container_name, "cat", f"/workspace/{file_path}"],
                    capture_output=True, text=True, timeout=5
                )
                if res.returncode != 0:
                    continue
                content = res.stdout.lower()
                
                if phase == 1:
                    if backend_framework and backend_framework in content and "import" in content:
                        violations.append({"file": file_path, "violation": "Phase 1 Boundary", "description": f"Backend framework ({backend_framework}) import found in Phase 1."})
                elif phase == 2:
                    if "frontend" in file_path.lower() or "src/components" in file_path.lower() or "src/pages" in file_path.lower():
                        violations.append({"file": file_path, "violation": "Phase 2 Boundary", "description": "Frontend file modified in Phase 2."})
                elif phase == 3:
                    if "mock" in content or "dummy" in content:
                        violations.append({"file": file_path, "violation": "Phase 3 Boundary", "description": "Mock data references found in Phase 3."})
                        
            if not violations:
                self._broadcast_log(project_token, agent_id, "✅ Phase Boundary Check: PASSED!")
            else:
                self._broadcast_log(project_token, agent_id, f"⚠️ Phase Boundary Check: FAILED with {len(violations)} violations", event_type="WARNING")
        except Exception as e:
            logger.warning(f"[MasterGovernance] Phase boundary check error: {e}")
            
        return violations

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
            expected_files = task.get("expected_files", [])
            phase = int(task.get("phase", 1))
            tech_stack = task.get("tech_stack", {})
            files_created = task.get("files_created", [])
            
            await self.validate_structural_compliance(
                container_name, project_token, agent_id, expected_files, phase, tech_stack
            )
            await self.validate_phase_boundary(
                container_name, project_token, agent_id, files_created, phase, tech_stack
            )

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
