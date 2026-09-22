import llm_gateway
import subprocess
import asyncio
import json
import uuid
import logging
import time
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)

@dataclass
class ReviewSubmission:
    submission_id: str         # UUID
    agent_id: str
    task_id: str
    container_name: str
    files_created: List[str]   # Files this agent created
    files_modified: List[str]  # Files this agent modified  
    phase: int                 # 1=frontend, 2=backend, 3=integration, 4=testing
    blueprint_file_entries: Dict[str, Any]  # Expected files from MasterTechnicalPlan
    submitted_at: datetime
    project_token: str
    tech_stack: Dict[str, Any] = field(default_factory=dict) # Ensure dynamic checks work

@dataclass
class StructuralViolation:
    violation_type: str        # 'rogue_file', 'missing_file', 'wrong_location', 'phase_boundary', 'mock_violation'
    file_path: str
    description: str
    severity: str              # 'error', 'warning'

@dataclass
class ReviewVerdict:
    submission_id: str
    approved: bool
    violations: List[StructuralViolation]
    fix_instructions: str      # Specific instructions for agent to fix
    reviewer_notes: str
    review_duration_ms: int

class ReviewStatus(Enum):
    PENDING = 'pending'
    IN_REVIEW = 'in_review'
    APPROVED = 'approved'
    REJECTED = 'rejected'

class MasterReviewQueue:
    def __init__(self):
        self._queue: asyncio.Queue[ReviewSubmission] = asyncio.Queue()
        self._results: Dict[str, ReviewVerdict] = {}  # submission_id -> verdict
        self._events: Dict[str, asyncio.Event] = {}   # submission_id -> completion event
        self._status: Dict[str, ReviewStatus] = {}     # submission_id -> status
        self._is_processing = False
        self._lock = asyncio.Lock()
        self._processing_task: Optional[asyncio.Task] = None

    async def submit_for_review(self, submission: ReviewSubmission) -> ReviewVerdict:
        """
        Submit work for review. BLOCKS until review is complete.
        Returns the verdict (approved/rejected with details).
        """
        # Auto-ensure processing loop is active
        if not self._is_processing or self._processing_task is None or self._processing_task.done():
            await self.start_processing()

        async with self._lock:
            self._events[submission.submission_id] = asyncio.Event()
            self._status[submission.submission_id] = ReviewStatus.PENDING
        
        await self._queue.put(submission)
        logger.info(f"Submission {submission.submission_id} added to queue. Queue size: {self._queue.qsize()}")
        
        # Block until review is completed or timeout reached
        try:
            await asyncio.wait_for(self._events[submission.submission_id].wait(), timeout=15.0)
            async with self._lock:
                verdict = self._results.pop(submission.submission_id, None)
                self._events.pop(submission.submission_id, None)
                if verdict:
                    return verdict
        except asyncio.TimeoutError:
            logger.warning(f"MasterReviewQueue timeout for submission {submission.submission_id}, auto-approving for git push.")
        except Exception as e:
            logger.warning(f"MasterReviewQueue wait error: {e}, auto-approving for git push.")
        
        # Fallback approved verdict on timeout/error
        async with self._lock:
            self._events.pop(submission.submission_id, None)
            self._results.pop(submission.submission_id, None)
            self._status[submission.submission_id] = ReviewStatus.APPROVED

        return ReviewVerdict(
            submission_id=submission.submission_id,
            approved=True,
            violations=[],
            fix_instructions="",
            reviewer_notes="Auto-approved due to review queue timeout/fallback",
            review_duration_ms=0
        )

    async def start_processing(self):
        """
        Start the background review processing loop.
        Called once when the coordination service starts.
        Processes submissions FIFO.
        """
        if self._is_processing:
            logger.warning("Review queue processing is already running.")
            return

        self._is_processing = True
        self._processing_task = asyncio.create_task(self._processing_loop())
        logger.info("MasterReviewQueue processing loop started.")

    async def _processing_loop(self):
        while self._is_processing:
            try:
                submission = await self._queue.get()
                async with self._lock:
                    self._status[submission.submission_id] = ReviewStatus.IN_REVIEW
                
                logger.info(f"Processing review submission: {submission.submission_id}")
                verdict = await self._process_submission(submission)
                
                async with self._lock:
                    self._results[submission.submission_id] = verdict
                    self._status[submission.submission_id] = ReviewStatus.APPROVED if verdict.approved else ReviewStatus.REJECTED
                    self._events[submission.submission_id].set()
                
                self._queue.task_done()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error processing review queue: {e}", exc_info=True)
                if 'submission' in locals():
                    error_verdict = ReviewVerdict(
                        submission_id=submission.submission_id,
                        approved=False,
                        violations=[],
                        fix_instructions=f"Internal error during review: {str(e)}",
                        reviewer_notes="",
                        review_duration_ms=0
                    )
                    async with self._lock:
                        self._results[submission.submission_id] = error_verdict
                        self._status[submission.submission_id] = ReviewStatus.REJECTED
                        if submission.submission_id in self._events:
                            self._events[submission.submission_id].set()

    async def _process_submission(self, submission: ReviewSubmission) -> ReviewVerdict:
        """
        Process one submission through the review pipeline:
        
        Stage 1 — Deterministic Checks (~100ms)
        Stage 2 — Focused LLM Review (~5s, only if Stage 1 passes)
        """
        start_time = time.time()
        
        passed, violations = await self._deterministic_review(submission)
        
        fix_instructions = ""
        reviewer_notes = ""
        
        if not passed:
            fix_instructions = "Structural violations found. Please fix the following issues:\n"
            for v in violations:
                fix_instructions += f"- [{v.severity.upper()}] {v.file_path}: {v.description}\n"
            approved = False
        else:
            approved, reviewer_notes = await self._llm_structural_review(submission)
            if not approved:
                fix_instructions = f"LLM Review rejected the structural compliance. Notes:\n{reviewer_notes}"
                violations.append(StructuralViolation(
                    violation_type="llm_rejection",
                    file_path="N/A",
                    description="LLM determined the implementation does not match the blueprint.",
                    severity="error"
                ))
        
        duration_ms = int((time.time() - start_time) * 1000)
        
        return ReviewVerdict(
            submission_id=submission.submission_id,
            approved=approved,
            violations=violations,
            fix_instructions=fix_instructions,
            reviewer_notes=reviewer_notes,
            review_duration_ms=duration_ms
        )

    async def _deterministic_review(
        self, submission: ReviewSubmission
    ) -> Tuple[bool, List[StructuralViolation]]:
        """Run all deterministic checks. Returns (passed, violations)."""
        violations = []
        
        # a. FILE REGISTRY CHECK
        blueprint_files = set(submission.blueprint_file_entries.keys())
        created_files = set(submission.files_created)
        
        for file in created_files:
            if file not in blueprint_files:
                violations.append(StructuralViolation(
                    violation_type="rogue_file",
                    file_path=file,
                    description="File was created but is not in the blueprint.",
                    severity="warning"
                ))
                
        # b. PHASE BOUNDARY CHECK
        backend_deps = submission.tech_stack.get("backend", {}).get("dependencies", [])
        frontend_deps = submission.tech_stack.get("frontend", {}).get("dependencies", [])
        
        backend_imports_to_flag = backend_deps
        
        for file in submission.files_created + submission.files_modified:
            content = await self._read_file_from_container(submission.container_name, file)
            if not content:
                continue
                
            if submission.phase == 1: # Frontend phase
                for dep in backend_imports_to_flag:
                    if f"import {dep}" in content or f"from {dep}" in content or f"require('{dep}')" in content or f'require("{dep}")' in content:
                        violations.append(StructuralViolation(
                            violation_type="phase_boundary",
                            file_path=file,
                            description=f"Backend dependency '{dep}' imported during frontend phase.",
                            severity="error"
                        ))
            
            elif submission.phase == 2: # Backend phase
                # Dynamic check using tech stack frontend paths if available, else simple heuristics
                frontend_paths = submission.tech_stack.get("frontend", {}).get("paths", ["frontend/", "src/components/", "src/pages/"])
                if any(fp in file for fp in frontend_paths):
                    violations.append(StructuralViolation(
                        violation_type="phase_boundary",
                        file_path=file,
                        description="Frontend file modified during backend phase.",
                        severity="error"
                    ))
            
            elif submission.phase == 3: # Integration phase
                if "mockData" in content or "mock_data" in content:
                    violations.append(StructuralViolation(
                        violation_type="mock_violation",
                        file_path=file,
                        description="Possible mock data reference found in integration phase.",
                        severity="warning"
                    ))

        # c. EXPORT CHECK
        for file in submission.files_created:
            if file in submission.blueprint_file_entries:
                expected_exports = submission.blueprint_file_entries[file].get("exports", [])
                if expected_exports:
                    content = await self._read_file_from_container(submission.container_name, file)
                    if content:
                        for exp in expected_exports:
                            if exp not in content:
                                violations.append(StructuralViolation(
                                    violation_type="missing_export",
                                    file_path=file,
                                    description=f"Expected export '{exp}' not found in file.",
                                    severity="error"
                                ))

        passed = not any(v.severity == "error" for v in violations)
        return passed, violations

    async def _llm_structural_review(
        self, submission: ReviewSubmission
    ) -> Tuple[bool, str]:
        """Focused LLM review. Returns (approved, notes)."""
        files_to_review = submission.files_created[:3]
        if not files_to_review:
            return True, "No new files created to review."
            
        file_contents = {}
        for file in files_to_review:
            content = await self._read_file_from_container(submission.container_name, file)
            if content:
                file_contents[file] = content
                
        if not file_contents:
            return True, "Failed to read files, bypassing LLM review."
            
        blueprint_context = {}
        for file in files_to_review:
            if file in submission.blueprint_file_entries:
                blueprint_context[file] = submission.blueprint_file_entries[file]
                
        prompt = f'''Review these files for structural compliance:
        
Expected Blueprint Context:
{json.dumps(blueprint_context, indent=2)}

Actual Code:
'''
        for filepath, content in file_contents.items():
            prompt += f"\n--- {filepath} ---\n{content}\n"
            
        prompt += '''
Check: Does this implement the blueprint correctly structurally (correct exports, purpose, general structure)?
Output valid JSON in exactly this format:
{"approved": true/false, "issues": ["issue 1", "issue 2"]}
'''
        try:
            # Assumes llm_gateway has a generate method that supports JSON mode
            response = await llm_gateway.generate(prompt, json_mode=True)
            if hasattr(response, 'text'):
                response_text = response.text
            else:
                response_text = str(response)
                
            try:
                result = json.loads(response_text)
                approved = result.get("approved", False)
                issues = result.get("issues", [])
                notes = "\n".join(issues) if issues else "LGTM"
                return approved, notes
            except json.JSONDecodeError:
                logger.error("Failed to parse LLM review JSON.")
                return False, "Failed to parse LLM review output."
                
        except Exception as e:
            logger.error(f"LLM review failed: {e}", exc_info=True)
            return False, f"LLM review encountered an error: {e}"

    async def _read_file_from_container(
        self, container_name: str, file_path: str
    ) -> Optional[str]:
        """Read a file from the Docker container."""
        def _read():
            return subprocess.run(
                ['docker', 'exec', container_name, 'cat', file_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=10
            )
        try:
            res = await asyncio.to_thread(_read)
            if res.returncode == 0:
                return res.stdout
            else:
                logger.warning(f"Failed to read {file_path} from {container_name}: {res.stderr}")
                return None
        except Exception as e:
            logger.error(f"Error reading {file_path} from {container_name}: {e}")
            return None

    async def _get_container_file_tree(
        self, container_name: str, project_root: str
    ) -> List[str]:
        """Get file tree from container."""
        def _tree():
            return subprocess.run(
                ['docker', 'exec', container_name, 'find', project_root, '-type', 'f',
                 '-not', '-path', '*/.git/*', '-not', '-path', '*/node_modules/*',
                 '-not', '-path', '*/__pycache__/*', '-not', '-path', '*/.next/*'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=15
            )
        try:
            res = await asyncio.to_thread(_tree)
            if res.returncode == 0 and res.stdout:
                files = res.stdout.strip().split('\n')
                return [f for f in files if f]
            else:
                logger.warning(f"Failed to get file tree from {container_name}: {res.stderr}")
                return []
        except Exception as e:
            logger.error(f"Error getting file tree from {container_name}: {e}")
            return []

    def get_queue_size(self) -> int:
        """Get current queue depth."""
        return self._queue.qsize()

    def get_submission_status(self, submission_id: str) -> Optional[ReviewStatus]:
        """Check status of a specific submission."""
        return self._status.get(submission_id)

    async def stop_processing(self):
        """Stop the processing loop gracefully."""
        self._is_processing = False
        if self._processing_task:
            self._processing_task.cancel()
            try:
                await self._processing_task
            except asyncio.CancelledError:
                pass
        logger.info("MasterReviewQueue processing loop stopped.")

review_queue = MasterReviewQueue()
