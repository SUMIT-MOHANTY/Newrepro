"""Orchestrator — the main agent execution loop.

Architecture §7.1 orchestrator.py, §12 Agent Execution Flow:

This orchestrator supports Claude's native tool-use mode:
- Claude calls tools directly (read_file, write_file, grep_search, find_and_replace, etc.)
- The orchestrator monitors the tool-use loop and posts lifecycle events
- This replaces the old Planner → Coder → Reviewer pipeline with a single
  agentic session where Claude autonomously builds the entire application

Lifecycle:
  initialize_workspace → run_with_tools (Claude drives everything) →
  build → preview → post completion event via callback
"""
from __future__ import annotations

import json
import os
import time
from typing import Any, TYPE_CHECKING

from agent.model_router import ModelRouter, TaskType
from agent.prompts.system_prompts import PromptBuilder, PromptPhase
from agent.state import AgentState, Plan, PlanStep, StepResult, ReviewResult
from agent.tools.tool_registry import ToolRegistry, ToolPhase
from agent.tools.tool_executor import ToolExecutor
from infrastructure.llm_client import LLMClient
from infrastructure.model_profile import get_profile

if TYPE_CHECKING:
    from mcp.server import MCPServer


class Orchestrator:
    """Drives the full agent lifecycle for one session/task pair."""

    def __init__(self, state: AgentState, mcp: "MCPServer") -> None:
        self._state = state
        self._mcp = mcp
        self._router = ModelRouter(model=state.model_name)
        self._active_conversation: list[dict] | None = None
        self._active_file_manifest: Any | None = None

        # Auto token billing: EVERY AI call through LLMClient reports its
        # exact usage via this sink -> llm_call_completed event. No per-phase
        # registration needed; the sink is class-level so it covers every
        # client instance in the container, present and future.
        LLMClient.set_usage_sink(self._report_llm_call)

        # Reality Guard (Authoritative ground truth + Tool Execution Firewall)
        from runtime.reality_guard import AgentRealityGuard
        self._reality_guard = AgentRealityGuard(state.workspace_path)

        # Tool registry for Claude's native tool-use (includes dynamic MCP tools)
        discovered_tools = getattr(mcp, "get_discovered_tools", lambda: [])()
        self._registry = ToolRegistry(
            web_search_enabled=state.web_search_enabled,
            dynamic_tools=discovered_tools,
        )

    def run(self) -> None:
        """Execute the full agent lifecycle using LangGraph StateGraph engine."""
        s = self._state
        try:
            from agent.graph import create_agent_graph
            from agent.nodes.core.context import NodeContext

            ctx = NodeContext(
                mcp=self._mcp,
                registry=self._registry,
                router=self._router,
                reality_guard=self._reality_guard,
                event_callback=self._post_event,
            )

            graph = create_agent_graph(ctx)

            initial_state = {
                "session_id": s.session_id,
                "task_id": s.task_id,
                "prompt": s.prompt,
                "workspace_path": s.workspace_path,
                "task_type": s.task_type,
                "model_name": s.model_name,
                "files_changed": [],
                "fix_attempts": 0,
            }

            final_state = graph.invoke(initial_state)

            s.preview_url = final_state.get("preview_url") or "http://localhost:80"
            s.files_changed = final_state.get("files_changed", [])
            self._last_final_text = final_state.get("final_text", "")

            # Phase 5: Browser verification & console error check / auto-fix
            # Runs BEFORE session_completed so the user never sees a broken preview!
            if final_state.get("status") != "failed":
                try:
                    console_errors = self._check_console_errors()
                    if console_errors and console_errors.has_errors:
                        print(f"[Orchestrator] Found {console_errors.error_count} console error(s) — fixing before completion...")
                        self._fix_console_errors(console_errors)
                    else:
                        self._post_event("console_fix_completed", {
                            "session_id": s.session_id,
                            "task_id": s.task_id,
                            "status": "clean",
                            "message": "No console errors found.",
                            "errors_remaining": 0,
                        })
                except NameError as ne:
                    print(f"[Orchestrator] Console fix skipped (variable not in scope): {ne}")
                except Exception as ce:
                    print(f"[Orchestrator] Console checking/auto-fixing completed with note: {ce}")

                # Emit session_completed only AFTER browser verification & auto-fix completes
                # Gate C honesty: completion carries platform verification evidence.
                # If the platform gate was skipped (not proven), emit "completed_unverified"
                # so the platform never advertises an unproven app as success.
                msg = self._last_final_text or "Application is live, validated, and ready to use."
                v_report = final_state.get("verification_report") or {}
                gate_skipped = bool(v_report.get("skipped"))
                completion_event = "completed_unverified" if gate_skipped else "session_completed"
                self._post_event(completion_event, {
                    "session_id": s.session_id,
                    "task_id": s.task_id,
                    "message": msg,
                    "final_text": msg,
                    "preview_url": s.preview_url,
                    "files_changed": len(s.files_changed),
                    "model": s.model_name,
                    "backend_healthy": final_state.get("backend_healthy", True),
                    "backend_error": final_state.get("backend_error"),
                    "platform_verified": bool(final_state.get("platform_verified", False)),
                    "verification_report": v_report or None,
                })


        except KeyboardInterrupt:
            print(f"[Orchestrator] Task {s.task_id} was soft-cancelled by user")
            self._post_event("session_cancelled", {
                "session_id": s.session_id, "task_id": s.task_id, "message": "Task cancelled by user"
            })
            return
        except Exception as exc:
            print(f"[Orchestrator] FATAL: {exc}")
            self._post_event("session_failed", {
                "session_id": s.session_id, "task_id": s.task_id, "error": str(exc),
            })
            raise

    def run_follow_up(
        self,
        prompt: str,
        task_id: str | None = None,
        task_type: str = "follow_up_edit",
        model: str | None = None,
        session_id: str | None = None,
    ) -> None:
        """Execute a follow-up prompt using the LangGraph StateGraph engine."""
        s = self._state
        if session_id:
            s.session_id = session_id
        if task_id:
            s.task_id = task_id
        s.task_type = task_type
        s.prompt = prompt
        if model:
            s.model_name = model
            self._router.set_model(model)
            os.environ["MODEL_NAME"] = model
            os.environ["AI_MODEL"] = model
            print(f"[Orchestrator] Active model switched to: {model}")

        # Record follow-up prompt in workspace history (.agent_history/prompts_history.json)
        try:
            hist_dir = os.path.join(s.workspace_path, ".agent_history")
            os.makedirs(hist_dir, exist_ok=True)
            prompts_file = os.path.join(hist_dir, "prompts_history.json")
            history = []
            if os.path.exists(prompts_file):
                with open(prompts_file, "r", encoding="utf-8") as f:
                    history = json.load(f)
            history.append({"task_id": s.task_id, "prompt": prompt, "time": time.time()})
            with open(prompts_file, "w", encoding="utf-8") as f:
                json.dump(history, f, indent=2)
        except Exception:
            pass

        # Ensure active_file_manifest is loaded from workspace
        if not self._active_file_manifest:
            try:
                from infrastructure.claude_tool_client import FileManifest
                m = FileManifest()
                m.scan_workspace(s.workspace_path)
                self._active_file_manifest = m
            except Exception:
                pass

        print(f"[Orchestrator] Starting follow-up task {s.task_id}: {prompt}")

        try:
            from agent.graph import create_agent_graph
            from agent.nodes.core.context import NodeContext

            ctx = NodeContext(
                mcp=self._mcp,
                registry=self._registry,
                router=self._router,
                reality_guard=self._reality_guard,
                event_callback=self._post_event,
                prior_conversation=list(self._active_conversation) if self._active_conversation else [],
                prior_manifest=self._active_file_manifest,
            )

            graph = create_agent_graph(ctx)

            initial_state = {
                "session_id": s.session_id,
                "task_id": s.task_id,
                "prompt": s.prompt,
                "workspace_path": s.workspace_path,
                "task_type": s.task_type,
                "model_name": s.model_name,
                "files_changed": s.files_changed,
                "fix_attempts": 0,
            }

            final_state = graph.invoke(initial_state)

            s.preview_url = final_state.get("preview_url") or "http://localhost:80"
            s.files_changed = final_state.get("files_changed", [])
            self._last_final_text = final_state.get("final_text", "")
            print(f"[Orchestrator] Follow-up task {s.task_id} completed successfully. Preview live at {s.preview_url}")

            if final_state.get("status") != "failed":
                try:
                    console_errors = self._check_console_errors()
                    if console_errors and console_errors.has_errors:
                        self._fix_console_errors(console_errors)
                    else:
                        self._post_event("console_fix_completed", {
                            "session_id": s.session_id,
                            "task_id": s.task_id,
                            "status": "clean",
                            "message": "No console errors found.",
                            "errors_remaining": 0,
                        })
                except NameError as ne:
                    print(f"[Orchestrator] Console fix skipped (variable not in scope): {ne}")
                except Exception as ce:
                    print(f"[Orchestrator] Follow-up visual/console check completed with note: {ce}")

                msg = self._last_final_text or "Follow-up changes applied and verified."
                self._post_event("session_completed", {
                    "session_id": s.session_id,
                    "task_id": s.task_id,
                    "message": msg,
                    "final_text": msg,
                    "preview_url": s.preview_url,
                    "files_changed": len(s.files_changed),
                    "model": s.model_name,
                    "backend_healthy": final_state.get("backend_healthy", True),
                    "backend_error": final_state.get("backend_error"),
                })
        except KeyboardInterrupt:
            print(f"[Orchestrator] Follow-up task {s.task_id} was soft-cancelled by user")
            self._post_event("session_cancelled", {
                "session_id": s.session_id, "task_id": s.task_id, "message": "Task cancelled by user"
            })
            return
        except Exception as exc:
            print(f"[Orchestrator] Follow-up task failed: {exc}")
            self._post_event("session_failed", {
                "session_id": s.session_id, "task_id": s.task_id, "error": str(exc),
            })

    # ------------------------------------------------------------------
    # Phase 1: workspace initialization
    # ------------------------------------------------------------------

    def _initialize_workspace(self) -> None:
        """Ensure the workspace directory exists, is seeded or cloned, and has a git repo."""
        import os

        s = self._state
        # Create workspace if needed
        self._mcp.call_tool("filesystem", "create_directory", {"path": s.workspace_path})

        repo_url = os.environ.get("GIT_REPO_URL") or s.github_repo_url
        git_token = os.environ.get("GIT_TOKEN")
        git_branch = os.environ.get("GIT_BRANCH", "main")

        from pathlib import Path
        ws_path = Path(s.workspace_path)
        existing_items = [
            f for f in ws_path.iterdir()
            if not f.name.startswith(".") and f.name not in ("node_modules", "__pycache__")
        ] if ws_path.exists() else []

        if existing_items:
            print(f"[Orchestrator] 🚀 Existing workspace code detected ({len(existing_items)} items: {[f.name for f in existing_items[:5]]}) — running directly from local workspace without re-cloning!")
            if not (ws_path / ".git").exists():
                self._mcp.call_tool("git", "init", {"workspace_path": s.workspace_path})
        elif repo_url:
            self._post_event("git_clone_started", {
                "session_id": s.session_id,
                "task_id": s.task_id,
                "repo_url": repo_url,
                "branch": git_branch,
                "message": f"Cloning repository {repo_url} (branch: {git_branch})...",
            })
            res = self._mcp.call_tool("git", "clone", {
                "repo_url": repo_url,
                "branch": git_branch,
                "auth_token": git_token,
                "workspace_path": s.workspace_path,
            })
            success = bool(getattr(res, "success", False))
            self._post_event("git_clone_completed", {
                "session_id": s.session_id,
                "task_id": s.task_id,
                "status": "success" if success else "error",
                "message": f"Repository cloned ({git_branch})" if success else f"Clone warning: {getattr(res, 'error', 'failed')}",
            })
            if not success:
                print(f"[Orchestrator] Warning: Git clone failed. Initializing clean local git repository without injecting scaffold.")
                self._mcp.call_tool("git", "init", {"workspace_path": s.workspace_path})
        else:
            from agent.techstack_detector import detect_techstack
            decision = detect_techstack(s.prompt or "", workspace_path=s.workspace_path)
            print(f"[Orchestrator] Stack '{decision.get('stack')}' ({decision.get('architecture_type')}, mode: {decision.get('project_mode')}) detected — keeping workspace clean for autonomous stack setup.")
            self._mcp.call_tool("git", "init", {"workspace_path": s.workspace_path})

        # Sync authoritative filesystem state
        self._reality_guard.state.refresh()
        print(f"[Orchestrator] Workspace ready: {s.workspace_path}")

    # ------------------------------------------------------------------
    # Phase 0: Intelligent Analysis — uses tools + web_search
    # ------------------------------------------------------------------

    def _run_intelligent_analysis(self) -> str | None:
        """AI-powered analysis that uses tools to understand the workspace and domain.

        Instead of asking the user blind questions, the AI:
        1. Reads the workspace to understand what exists
        2. Web-searches the domain to gather context
        3. Decides if it has enough info to proceed OR needs clarification

        Returns: clarification answers string to append to prompt, or None if no questions needed.
        """
        import json
        import os
        import time

        s = self._state
        task_str = str(s.task_type).lower()

        # Skip analysis for edits, fixes, questions — only analyze new projects
        if any(k in task_str for k in ("follow_up", "edit", "bug", "question")):
            return None

        # Skip analysis if user blueprint/clarifications are already provided in the prompt
        if "## User Clarifications" in str(s.prompt):
            print("[Orchestrator] User clarifications already provided in prompt — proceeding directly to planning")
            return None

        print("[Orchestrator] Running intelligent analysis with tools...")
        self._post_event("analysis_started", {
            "session_id": s.session_id, "task_id": s.task_id,
        })

        try:
            from infrastructure.claude_tool_client import ClaudeToolClient
            from agent.prompts.system_prompts import PromptBuilder, PromptPhase

            # Route with the session's CURRENT model (state.model_name) so a
            # follow-up model switch changes which engine this phase calls.
            config = self._router.route(TaskType.planning, model=s.model_name)
            tools = self._registry.get_tools(ToolPhase.planning)  # read-only + web_search
            executor = ToolExecutor(self._mcp, self._registry)

            # Build the analysis prompt
            analysis_system = (
                "You are an intelligent requirements analyst inside an AI coding platform.\n"
                "Your job is to analyze the user's prompt and determine if you have enough\n"
                "information to build exactly what they want.\n\n"
                "You have READ-ONLY tools to:\n"
                "1. Inspect the workspace (list_directory, read_file) to understand existing code\n"
                "2. Web-search the domain to gather context about the industry, data patterns, UI conventions\n"
                "3. Make a decision: do you have enough info, or do you need to ask the user?\n\n"
                "RULES:\n"
                "- If the prompt is vague (missing domain, theme, or data), use web_search to RESEARCH\n"
                "  the domain FIRST. Often the web search gives you enough context to proceed.\n"
                "- ONLY ask the user if, AFTER researching, you still can't determine key details.\n"
                "- Questions MUST be non-technical and easy for a non-technical user to answer.\n"
                "- Limit to max 2 questions.\n"
                "- If you have enough info, respond with: NO_QUESTIONS_NEEDED\n"
                "- If you need clarification, respond with a JSON object:\n"
                '{\n'
                '  "needs_clarification": true,\n'
                '  "questions": [\n'
                '    {"id": "q1", "question": "...", "context": "...", "options": ["...", "..."], "default_option": "..."}\n'
                '  ]\n'
                '}\n'
                "- If you have enough info, respond with:\n"
                '{ "needs_clarification": false }\n\n'
                "IMPORTANT: Do NOT ask about technical details (frameworks, libraries, etc.).\n"
                "Only ask about product/business details that affect what to build.\n"
                "If web_search gives you the answer, use it and DON'T ask the user."
            )

            analysis_msg = (
                f"User requirement:\n{s.prompt}\n\n"
                f"Workspace path: {s.workspace_path}\n\n"
                "First, inspect the workspace to see what exists. Then, if the prompt is vague,\n"
                "use web_search to research the domain. Finally, decide if you need to ask\n"
                "the user any clarifying questions."
            )

            client = ClaudeToolClient(
                model=config.model,
                api_key=config.api_key,
                tools=tools,
                max_tokens=config.max_tokens,
                temperature=config.temperature,
            )

            result = client.run_tool_loop(
                system=analysis_system,
                messages=[{"role": "user", "content": analysis_msg}],
                tool_executor=executor,
                max_iterations=10,
                on_event=self._on_tool_event,
            )

            # Store analysis conversation + manifest so planner and coding can continue
            self._active_conversation = result.conversation
            self._active_file_manifest = client._file_manifest

            response_text = result.final_text or ""
            print(f"[Orchestrator] Analysis response: {response_text[:200]}...")

            # Check if analysis says no questions needed
            if "NO_QUESTIONS_NEEDED" in response_text or '"needs_clarification": false' in response_text.lower():
                print("[Orchestrator] Analysis: sufficient info — proceeding without questions")
                self._post_event("analysis_completed", {
                    "session_id": s.session_id, "task_id": s.task_id,
                    "needs_clarification": False,
                    "message": "AI analyzed the requirements and has enough context to proceed.",
                })
                return None

            # Try to parse questions from response
            questions_data = self._extract_questions(response_text)
            if not questions_data:
                print("[Orchestrator] Analysis: could not parse questions — proceeding")
                self._post_event("analysis_completed", {
                    "session_id": s.session_id, "task_id": s.task_id,
                    "needs_clarification": False,
                })
                return None

            # Post clarification_needed event with questions
            print(f"[Orchestrator] Analysis: asking {len(questions_data)} question(s)")
            self._post_event("clarification_needed", {
                "session_id": s.session_id,
                "task_id": s.task_id,
                "questions": questions_data,
                "message": "The AI needs a few details before building your app.",
            })

            # Wait for user to answer — poll for signal file
            answers = self._wait_for_clarification()
            if answers is None:
                print("[Orchestrator] Clarification wait timed out — proceeding without answers")
                return None

            # Format answers for prompt enrichment
            clarification_text = "\n\n## User Clarifications & Architecture Preferences:"
            for q in questions_data:
                answer = answers.get(q["id"], q.get("default_option", ""))
                clarification_text += f"\n- **{q['question']}**: {answer}"
            clarification_text += "\n"

            self._post_event("analysis_completed", {
                "session_id": s.session_id, "task_id": s.task_id,
                "needs_clarification": True,
                "answers_received": True,
                **usage,
            })

            return clarification_text

        except Exception as e:
            print(f"[Orchestrator] Analysis failed (non-fatal): {e}")
            self._post_event("analysis_completed", {
                "session_id": s.session_id, "task_id": s.task_id,
                "needs_clarification": False,
                "error": str(e),
            })
            return None

    def _extract_questions(self, text: str) -> list[dict]:
        """Extract question data from the AI's analysis response."""
        import re
        import json

        # Try to find JSON object in the response
        json_match = re.search(r'\{[\s\S]*"questions"[\s\S]*\}', text)
        if json_match:
            try:
                data = json.loads(json_match.group(0))
                questions = data.get("questions", [])
                if questions and isinstance(questions, list):
                    return questions[:2]  # Cap at 2
            except (json.JSONDecodeError, ValueError):
                pass

        # Try to find any JSON object
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end > start:
            try:
                data = json.loads(text[start:end + 1])
                questions = data.get("questions", [])
                if questions and isinstance(questions, list):
                    return questions[:2]
            except (json.JSONDecodeError, ValueError):
                pass

        return []

    def _wait_for_clarification(self, timeout: int = 300) -> dict | None:
        """Wait for user to answer clarification questions via signal file.

        The backend writes answers to a signal file when the user responds.
        This method polls for that file.
        """
        import json
        import os

        s = self._state
        signal_dir = os.path.join(s.workspace_path, ".agent_signals")
        os.makedirs(signal_dir, exist_ok=True)
        answers_file = os.path.join(signal_dir, f"clarification_answers_{s.task_id}.json")

        print(f"[Orchestrator] Waiting for user clarification answers (timeout: {timeout}s)...")
        start_time = time.time()

        while time.time() - start_time < timeout:
            if os.path.exists(answers_file):
                try:
                    with open(answers_file, "r") as f:
                        answers = json.load(f)
                    os.remove(answers_file)  # Consume the signal
                    print(f"[Orchestrator] Received clarification answers: {answers}")
                    return answers
                except Exception as e:
                    print(f"[Orchestrator] Error reading answers: {e}")
            time.sleep(2)

        print(f"[Orchestrator] Clarification wait timed out ({timeout}s)")
        return None

    # ------------------------------------------------------------------
    # Phase 1.5: Planning (optional — for initial generation only)
    # ------------------------------------------------------------------

    def _run_planner(self) -> str | None:
        """Run the planner to produce an implementation plan before coding.

        Only runs for initial_generation tasks. The plan is injected into
        the user message so the coding AI knows exactly what to build.
        Reduces wasted iterations by giving the AI a clear roadmap.
        """
        from agent.planner import Planner
        from agent.prompts.system_prompts import PromptBuilder, PromptPhase

        s = self._state
        task_str = str(s.task_type).lower()

        # Only plan for new projects — skip for edits, fixes, questions
        if not any(k in task_str for k in ("initial", "generation")):
            return None

        print("[Orchestrator] Running planner to create implementation plan...")
        self._post_event("planning_started", {
            "session_id": s.session_id, "task_id": s.task_id,
        })

        try:
            planner = Planner(self._router)
            plan, planner_conversation, planner_manifest = planner.create_plan_with_tools(
                s, self._mcp, self._registry,
                existing_conversation=self._active_conversation,
                existing_manifest=self._active_file_manifest,
            )

            # Store planner's conversation + manifest for coding phase
            self._active_conversation = planner_conversation
            self._active_file_manifest = planner_manifest

            # Format plan for injection into user message
            plan_text = f"\n\n## Implementation Plan ({plan.title})\n"
            for step in plan.steps:
                files = ", ".join(step.files_involved[:3]) if step.files_involved else "..."
                plan_text += f"- Step {step.step_number}: {step.description} [{files}]\n"
            plan_text += "\nExecute this plan. You may adjust based on what you find in the workspace."

            print(f"[Orchestrator] Plan created: {len(plan.steps)} steps")
            self._post_event("planning_completed", {
                "session_id": s.session_id, "task_id": s.task_id,
                "steps": len(plan.steps),
                "plan": plan.title,
                "plan_details": {
                    "title": plan.title,
                    "project_type": plan.project_type,
                    "step_list": [
                        {
                            "number": step.step_number,
                            "action": step.action,
                            "description": step.description,
                            "files": step.files_involved[:3] if step.files_involved else [],
                        }
                        for step in plan.steps
                    ],
                },
            })

            return plan_text

        except Exception as e:
            print(f"[Orchestrator] Planner failed (non-fatal): {e}")
            self._post_event("planning_completed", {
                "session_id": s.session_id, "task_id": s.task_id,
                "error": str(e),
            })
            return None

    def _run_reviewer(self) -> bool:
        """Run the reviewer to check code quality before building.

        Returns True if code is approved, False if issues found.
        If issues found, injects them into the conversation for correction.
        """
        from agent.reviewer import Reviewer

        s = self._state

        # Only review if files were changed
        if not s.files_changed:
            return True

        print("[Orchestrator] Running reviewer to check code quality...")
        self._post_event("review_started", {
            "session_id": s.session_id, "task_id": s.task_id,
        })

        try:
            reviewer = Reviewer(self._router)
            step = PlanStep(
                step_number=1,
                action="review",
                description=s.prompt[:200],
                files_involved=s.files_changed,
            )
            step_result = StepResult(
                success=True,
                files_changed=s.files_changed,
            )

            review = reviewer.review_with_tools(s, step_result, step, self._mcp, self._registry)

            if review.approved:
                print(f"[Orchestrator] Review PASSED")
                self._post_event("review_completed", {
                    "session_id": s.session_id, "task_id": s.task_id,
                    "approved": True,
                })
                return True
            else:
                issues = review.issues or []
                fixes = review.suggested_fixes or ""
                print(f"[Orchestrator] Review FOUND {len(issues)} issue(s): {issues[:3]}")
                self._post_event("review_completed", {
                    "session_id": s.session_id, "task_id": s.task_id,
                    "approved": False,
                    "issues": issues[:5],
                    "suggested_fixes": fixes[:500],
                })

                # Inject issues into conversation for correction
                if self._active_conversation:
                    issue_text = "\n".join(f"- {i}" for i in issues[:5])
                    correction_msg = (
                        f"Code review found issues:\n{issue_text}\n"
                    )
                    if fixes:
                        correction_msg += f"\nSuggested fixes: {fixes[:500]}\n"
                    correction_msg += "\nFix these issues using replace_file_content, then proceed."

                    self._active_conversation.append({
                        "role": "user",
                        "content": correction_msg,
                    })

                    # Run correction iteration
                    self._run_with_tools(
                        conversation=self._active_conversation,
                        max_iterations=5,
                        phase=PromptPhase.EDITING,
                    )

                return False

        except Exception as e:
            print(f"[Orchestrator] Reviewer failed (non-fatal): {e}")
            return True  # Auto-approve on failure

    # ------------------------------------------------------------------
    # Phase 2: Claude native tool-use — single agentic session
    # ------------------------------------------------------------------

    def _run_with_tools(
        self,
        conversation: list[dict] | None = None,
        max_iterations: int | None = None,
        phase: PromptPhase | None = None,
    ) -> None:
        """Run Claude with native tool-use to build/edit the application.

        Claude autonomously:
        1. Inspects the workspace (list_directory, read_file)
        2. Researches mock data (web_search, if enabled)
        3. Creates/edits files (write_file, find_and_replace)
        4. All through native tool calls — not text parsing

        If `conversation` is provided, continues from existing history
        (used for build fix continuation — no new session, no re-exploration).

        If `phase` is provided, uses that prompt phase directly instead of
        inferring from task_type (e.g., pass BUILD_FIX for build error retries).
        """
        from infrastructure.claude_tool_client import ClaudeToolClient

        s = self._state
        # Route with the session's CURRENT model (state.model_name) so a
        # follow-up model switch changes which engine this phase calls.
        config = self._router.route(TaskType.coding, model=s.model_name)

        # Determine prompt phase: explicit override or infer from task_type
        if phase is None:
            phase = PromptBuilder.determine_phase(str(s.task_type))
        system_prompt = PromptBuilder.build(phase)
        print(f"[Orchestrator] Prompt phase: {phase.value} (~{len(system_prompt) // 4} tokens)")

        print("[Orchestrator] Starting Claude tool-use session...")
        self._post_event("coding_started", {
            "session_id": s.session_id, "task_id": s.task_id,
            "mode": "claude_tool_use",
        })

        # Map prompt phase to appropriate tool set — weaker models perform better with fewer tools
        _phase_to_tool_phase = {
            PromptPhase.NEW_PROJECT: ToolPhase.full,
            PromptPhase.EDITING: ToolPhase.full,
            PromptPhase.BUILD_FIX: ToolPhase.build_fix,
            PromptPhase.CONSOLE_FIX: ToolPhase.build_fix,
            PromptPhase.SERVER_FIX: ToolPhase.build_fix,
            PromptPhase.QUESTION: ToolPhase.reviewing,
        }
        tool_phase = _phase_to_tool_phase.get(phase, ToolPhase.full)
        tools = self._registry.get_tools(tool_phase)
        print(f"[Orchestrator] Tools available: {len(tools)} (phase: {tool_phase.value})")

        # Create tool executor
        executor = ToolExecutor(self._mcp, self._registry)

        # Build messages: continue existing conversation or start fresh
        if conversation:
            messages = conversation
            print(f"[Orchestrator] Continuing existing conversation ({len(conversation)} messages)")
        else:
            user_message = self._build_user_message(s)

            # Run planner for initial generation — inject plan into user message
            task_str = str(s.task_type).lower()
            is_edit_task = any(k in task_str for k in ("follow_up", "edit", "bug", "question"))
            if phase in (PromptPhase.NEW_PROJECT, None) and not is_edit_task:
                plan_text = self._run_planner()
                if plan_text:
                    user_message += plan_text

            # Chain from analysis + planner conversation if available
            if self._active_conversation:
                messages = list(self._active_conversation)
                messages.append({"role": "user", "content": user_message})
                print(f"[Orchestrator] Chaining from analysis+planner conversation ({len(messages)} messages)")
            else:
                messages = [{"role": "user", "content": user_message}]

        # Create the Claude tool-use client with RealityGuard
        client = ClaudeToolClient(
            model=config.model,
            api_key=config.api_key,
            tools=tools,
            max_tokens=config.max_tokens,
            temperature=config.temperature,
            reality_guard=self._reality_guard,
            file_manifest=self._active_file_manifest,
        )

        # Run the tool-use loop
        result = client.run_tool_loop(
            system=system_prompt,
            messages=messages,
            tool_executor=executor,
            max_iterations=max_iterations or s.max_tool_calls,
            on_event=self._on_tool_event,
        )

        # Store conversation and file manifest for potential continuation
        self._active_conversation = result.conversation
        self._active_file_manifest = client._file_manifest

        # Update state with results
        s.tool_call_count = executor.tool_call_count
        s.files_changed = executor.files_changed
        s.built_in_tool_loop = executor.built_successfully
        self._last_final_text = result.final_text

        # Create Git checkpoint commit if files were changed
        if executor.files_changed:
            try:
                from mcp.git_tools import GitTools
                git = GitTools(s.workspace_path)
                ckpt_res = git.commit_checkpoint(
                    task_id=s.task_id,
                    summary=s.prompt[:80],
                    files_changed=executor.files_changed,
                )
                if ckpt_res.success and ckpt_res.data:
                    commit_hash = ckpt_res.data.get("commit_hash", "")
                    self._post_event("checkpoint_created", {
                        "session_id": s.session_id,
                        "task_id": s.task_id,
                        "commit_hash": commit_hash,
                        "changed_files": executor.files_changed,
                    })
            except Exception as git_err:
                print(f"[Orchestrator] Warning creating checkpoint: {git_err}")

        # Fail-fast: If build failed and no files changed, stop early
        if not executor.built_successfully and len(executor.files_changed) == 0:
            print(f"[Orchestrator] Build failed and no files changed — stopping early to avoid loop.")
            return

        self._post_event("coding_completed", {
            "session_id": s.session_id,
            "task_id": s.task_id,
            "message": result.final_text or "Coding phase completed.",
            "final_text": result.final_text,
            "tool_calls": executor.tool_call_count,
            "files_changed": len(executor.files_changed),
            "iterations": result.iterations,
        })

        print(f"[Orchestrator] Tool-use session complete: "
              f"{executor.tool_call_count} tool calls, "
              f"{len(executor.files_changed)} files changed | "
              f"Tokens: in={result.total_input_tokens}, out={result.total_output_tokens}, total={result.total_tokens}")

    def _build_user_message(self, state: AgentState) -> str:
        """Build the user message with context for Claude."""
        from agent.spec_manager import ProductSpec
        spec = ProductSpec.load_or_init(state.workspace_path, state.prompt)

        parts = [
            spec.to_system_context(),
            f"\nUser requirement:\n{state.prompt}",
            f"\nWorkspace path: {state.workspace_path}",
            f"Task type: {state.task_type}",
        ]

        # Inject verified filesystem ground truth
        if hasattr(self, "_reality_guard") and self._reality_guard:
            parts.append(f"\n{self._reality_guard.state.to_verified_summary()}")

        # Determine if this is an edit/change request (by task_type or existing project)
        task_str = str(state.task_type).lower()
        is_edit = any(k in task_str for k in ("follow_up", "edit", "bug_fix", "change", "update"))

        # Check if this is a question-only task (no edits needed)
        is_question = "question" in str(state.task_type).lower()

        if is_question:
            parts.append(
                "\n📝 QUESTION MODE — DO NOT EDIT ANY FILES:\n"
                "- The user is asking a question about the app. Just answer it.\n"
                "- You may use `read_file` or `list_directory` to inspect the code if needed to answer.\n"
                "- DO NOT use write_file, write_files, find_and_replace, or replace_file_content.\n"
                "- Answer concisely and helpfully. Then stop."
            )
        else:
            # CRITICAL: Always tell the AI to check what exists before writing
            parts.append(
                "\n⚠️ CRITICAL FILE AWARENESS RULE:\n"
                "- ALWAYS run `list_directory` on the workspace src folder FIRST to see what files already exist.\n"
                "- If files already exist, READ them with `read_file` before writing anything.\n"
                "- NEVER blindly rewrite existing files from scratch. Make SURGICAL edits.\n"
                "- Each file write wastes tokens and time. Check first, edit second."
            )

        if is_edit and not is_question:
            parts.append(
                "\n🚨 INCREMENTAL EDIT / CHANGE REQUEST (PRESERVE EXISTING UI):\n"
                "- This is a modification to an EXISTING project. The UI and components are ALREADY built.\n"
                "- PRESERVE all existing layouts, components, state, styling, and features.\n"
                "- Use grep_search and read_file to find the relevant code, then use replace_file_content or find_and_replace to apply surgical changes.\n"
                "- DO NOT rewrite entire existing files with write_files/write_file. Only modify the specific lines/components required for this request."
            )
        else:
            parts.append(
                "\nPlease build the application now. Start by inspecting "
                "the workspace, then create or edit files as needed. When done, "
                "the system will automatically build and deploy the preview."
            )

        return "\n".join(parts)

    def _is_cancelled(self) -> bool:
        """Check if a cancellation signal file has been dropped into .agent_signals."""
        from pathlib import Path
        s = self._state
        sig_dir = Path(s.workspace_path) / ".agent_signals"
        if sig_dir.exists():
            for f in sig_dir.glob("cancel_*.json"):
                try:
                    f.unlink(missing_ok=True)
                except Exception:
                    pass
                return True
        return False

    def _report_llm_call(self, info: dict) -> None:
        """Auto-reported per-call token usage — fired by LLMClient for EVERY AI call.

        This is the single source of billing truth: each provider call posts one
        llm_call_completed event with the exact model + tokens, so the platform
        stores and prices every call regardless of which phase made it.
        """
        s = self._state
        try:
            model_name = info.get("model") or s.model_name
            profile = get_profile(model_name)
            ctx_window = int(info.get("context_window") or getattr(profile, "context_window", 100_000) or 100_000)
            self._post_event("llm_call_completed", {
                "session_id": s.session_id,
                "task_id": s.task_id,
                "model": model_name,
                "input_tokens": int(info.get("input_tokens") or 0),
                "output_tokens": int(info.get("output_tokens") or 0),
                "total_tokens": int(info.get("total_tokens") or 0),
                "context_window": max(ctx_window, 100_000),
                "latency_ms": int(info.get("latency_ms") or 0),
            })
        except Exception as exc:
            print(f"[Orchestrator] WARNING: usage report failed: {exc}")

    def _on_tool_event(self, event_type: str, data: dict) -> None:
        """Callback fired during tool-use loop for progress tracking."""
        if self._is_cancelled():
            print("[Orchestrator] 🛑 Soft cancellation signal detected — halting active task cleanly.")
            raise KeyboardInterrupt("Task soft-cancelled by user")

        s = self._state
        if event_type == "thinking":
            thought_summary = data.get("thought_summary", "Analyzing task and planning implementation...")
            reasoning = data.get("reasoning", "")
            self._post_event("tool_progress", {
                "session_id": s.session_id,
                "task_id": s.task_id,
                "message": f"Thinking: {thought_summary}",
                "reasoning": reasoning,
                "type": "thinking",
                "iteration": data.get("iteration", 0),
            })
        elif event_type == "tool_called":
            tool_name = data.get("tool", "unknown")
            desc = data.get("description") or f"Running tool {tool_name}"
            is_file = data.get("is_file", False)
            self._post_event("tool_progress", {
                "session_id": s.session_id,
                "task_id": s.task_id,
                "message": desc,
                "tool": tool_name,
                "is_file": is_file,
                "iteration": data.get("iteration", 0),
            })
        elif event_type == "files_changed":
            self._post_event("files_changed", {
                "session_id": s.session_id,
                "task_id": s.task_id,
                "created": data.get("created", []),
                "modified": data.get("modified", []),
                "deleted": data.get("deleted", []),
                "iteration": data.get("iteration", 0),
            })
        elif event_type == "checkpoint_created":
            self._post_event("checkpoint_created", {
                "session_id": s.session_id,
                "task_id": s.task_id,
                "commit_hash": data.get("commit_hash", ""),
                "changed_files": data.get("changed_files", []),
            })

    # ------------------------------------------------------------------
    # Phase 3: build
    # ------------------------------------------------------------------

    def _run_build(self) -> None:
        import os
        import time
        s = self._state
        dist_html = os.path.join(s.workspace_path, "dist", "index.html")
        if s.built_in_tool_loop and os.path.exists(dist_html):
            print("[Orchestrator] Application already successfully built in tool loop — skipping duplicate build.")
            self._post_event("build_completed", {
                "session_id": s.session_id, "task_id": s.task_id,
                "attempt": 1,
            })
            # Validate built output for hardcoded URLs (non-fatal)
            self._validate_build_output()
            return

        print("[Orchestrator] Starting build...")
        self._post_event("build_started", {"session_id": s.session_id, "task_id": s.task_id})

        for attempt in range(s.max_build_attempts):
            s.build_attempts += 1
            result = self._mcp.call_tool("build", "install_and_build",
                                         {"workspace": s.workspace_path})
            if result.success:
                print("[Orchestrator] Build succeeded.")
                self._post_event("build_completed", {
                    "session_id": s.session_id, "task_id": s.task_id,
                    "attempt": s.build_attempts,
                })
                # Validate built output for hardcoded URLs (non-fatal)
                self._validate_build_output()
                # Git commit the successful build
                try:
                    self._mcp.call_tool("git", "commit", {
                        "message": f"Build successful — {s.task_type}: {s.prompt[:80]}"
                    })
                except Exception:
                    pass
                return

            print(f"[Orchestrator] Build failed (attempt {s.build_attempts}): {result.error}")
            self._post_event("build_failed", {
                "session_id": s.session_id, "task_id": s.task_id,
                "attempt": s.build_attempts, "error": result.error,
            })

            if attempt < s.max_build_attempts - 1:
                print("[Orchestrator] Fixing build error (same conversation)...")
                self._continue_conversation_for_build_fix(result.error or "")
                time.sleep(2)

        raise RuntimeError(f"Build failed after {s.max_build_attempts} attempts")

    def _run_static_preflight(self) -> None:
        """Run instant static pre-flight analysis across all workspace files.

        Catches all missing imports (Lucide icons, components), missing files,
        broken paths, and unguarded calls across all files simultaneously in ~10ms.
        Prompts AI to fix ALL issues in a single batch turn.
        """
        from runtime.static_scanner import run_static_scan
        s = self._state
        print("[Orchestrator] Running static pre-flight scanner across workspace...")
        scan_result = run_static_scan(s.workspace_path)

        if not scan_result.has_issues:
            print(f"[Orchestrator] ✅ Static pre-flight passed ({scan_result.files_scanned} files in {scan_result.duration_ms}ms)")
            return

        print(f"[Orchestrator] ⚠️ Static pre-flight found {scan_result.issue_count} issue(s) across workspace — fixing in ONE batch...")
        fix_prompt = scan_result.to_fix_prompt()
        self._continue_conversation_for_build_fix(fix_prompt)

    def _validate_build_output(self) -> None:
        """Scan built JS/CSS for hardcoded localhost or absolute API URLs.

        Catches CRA-style mistakes where the AI wrote process.env.NODE_ENV
        ternaries or hardcoded localhost URLs that bypass the Nginx proxy.
        Logs warnings — does NOT block the build (non-fatal).
        """
        import os
        import re
        s = self._state
        dist_dir = os.path.join(s.workspace_path, "dist", "assets")
        if not os.path.isdir(dist_dir):
            return

        # Patterns that indicate hardcoded URLs bypassing Nginx proxy
        hardcoded_patterns = [
            (r'http://localhost:\d+', 'Hardcoded localhost URL'),
            (r'https://localhost:\d+', 'Hardcoded localhost URL'),
            (r'process\.env\.NODE_ENV', 'CRA-style process.env (use import.meta.env in Vite)'),
            (r'process\.env\.PORT', 'CRA-style process.env.PORT'),
        ]

        warnings = []
        for fname in os.listdir(dist_dir):
            if not fname.endswith(('.js', '.css')):
                continue
            fpath = os.path.join(dist_dir, fname)
            try:
                with open(fpath, encoding='utf-8', errors='ignore') as f:
                    content = f.read()
            except Exception:
                continue
            for pattern, description in hardcoded_patterns:
                matches = re.findall(pattern, content)
                if matches:
                    warnings.append(f"{description} in {fname}: {matches[0]}")

        if warnings:
            print(f"[Orchestrator] Build validation warnings (non-fatal):")
            for w in warnings:
                print(f"  ⚠️  {w}")
            self._post_event("build_warnings", {
                "session_id": s.session_id, "task_id": s.task_id,
                "warnings": warnings,
            })
        else:
            print("[Orchestrator] Build validation passed — no hardcoded URLs found.")

    def _continue_conversation_for_build_fix(self, error_output: str) -> None:
        """Fix build errors by continuing the existing conversation.

        Instead of creating a new ClaudeToolClient (which wastes ~50K tokens on
        re-sending system prompt + file context), we inject the build error into
        the existing conversation and continue the tool loop. The AI already knows
        what files it wrote and what it tried — no re-discovery needed.

        Falls back to fresh session if no conversation exists.
        """
        if self._active_conversation:
            print("[Orchestrator] Continuing existing conversation for build fix")
            # Inject build error into existing conversation
            self._active_conversation.append({
                "role": "user",
                "content": (
                    f"The build failed with this error:\n\n{error_output}\n\n"
                    f"Workspace: {self._state.workspace_path}\n"
                    "Fix ALL issues in ONE pass using batch_replace_file_content (or replace_file_content / write_file if creating missing files), then call install_and_build."
                ),
            })
            # Continue tool loop with BUILD_FIX phase (not inferred from task_type)
            self._run_with_tools(
                conversation=self._active_conversation,
                max_iterations=2,
                phase=PromptPhase.BUILD_FIX,
            )
        else:
            # Fallback: no conversation to continue (shouldn't happen)
            print("[Orchestrator] No active conversation — falling back to fresh fix session")
            self._fix_build_with_tools_fresh(error_output)

    def _fix_build_with_tools_fresh(self, error_output: str) -> None:
        """Last resort: create a fresh session to fix build errors.

        Only used when no existing conversation is available.
        Prefer _continue_conversation_for_build_fix when possible.
        """
        from infrastructure.claude_tool_client import ClaudeToolClient

        s = self._state
        # Route with the session's CURRENT model (state.model_name) so a
        # follow-up model switch changes which engine this phase calls.
        config = self._router.route(TaskType.build_fix, model=s.model_name)

        # Use lean build fix prompt (not the full 4000-word prompt)
        system_prompt = PromptBuilder.build(PromptPhase.BUILD_FIX)

        tools = self._registry.get_tools(ToolPhase.build_fix)
        executor = ToolExecutor(self._mcp, self._registry)

        client = ClaudeToolClient(
            model=config.model,
            api_key=config.api_key,
            tools=tools,
            max_tokens=config.max_tokens,
            temperature=config.temperature,
            file_manifest=self._active_file_manifest,
        )

        user_msg = (
            f"The build failed with this error:\n\n{error_output}\n\n"
            f"Workspace: {s.workspace_path}\n"
            "Fix ALL issues in ONE pass using write_files, then call install_and_build."
        )

        result = client.run_tool_loop(
            system=system_prompt,
            messages=[{"role": "user", "content": user_msg}],
            tool_executor=executor,
            max_iterations=2,
        )

        s.tool_call_count += executor.tool_call_count
        for f in executor.files_changed:
            s.track_file_change(f)

        # Update active conversation and manifest with this fix session's history
        self._active_conversation = result.conversation
        self._active_file_manifest = client._file_manifest

        print(f"[Orchestrator] Build fix (fresh): {executor.tool_call_count} tool calls, "
              f"{len(executor.files_changed)} files changed")

        self._post_event("build_fix_completed", {
            "session_id": s.session_id,
            "task_id": s.task_id,
            "status": "completed",
        })

    # ------------------------------------------------------------------
    # Phase 4: preview
    # ------------------------------------------------------------------

    def _run_preview(self) -> Any:
        from runtime.preview_manager import PreviewManager
        s = self._state
        print("[Orchestrator] Starting dynamic preview...")
        pm = PreviewManager(workspace_path=s.workspace_path)
        info = pm.start_preview(project_type="auto")
        s.preview_url = info.url
        self._post_event("preview_started", {
            "session_id": s.session_id, "task_id": s.task_id,
            "preview_url": info.url, "port": info.port,
        })
        print(f"[Orchestrator] Preview live at: {info.url}")

        # 1. If frontend failed to start or compile (Vite transform, missing imports, syntax), self-heal dynamically
        if getattr(info, "frontend_error", None):
            print(f"[Orchestrator] ⚠️ Frontend error detected: {info.frontend_error[:200]}")
            healed = self._fix_frontend_errors(
                info.frontend_error, pm,
                cwd=getattr(info, "frontend_cwd", None)
            )
            if healed:
                info = healed
                s.preview_url = info.url

        # 2. If backend failed to start, self-heal dynamically
        if getattr(info, "backend_error", None):
            print(f"[Orchestrator] ⚠️ Backend failed to start: {info.backend_error[:200]}")
            healed = self._fix_server_errors(
                info.backend_error, pm,
                entrypoint=getattr(info, "backend_entrypoint", None),
                cwd=getattr(info, "backend_cwd", None)
            )
            if healed:
                info = healed
                s.preview_url = info.url

        # 3. Dynamic API endpoint health probe
        api_ok, api_err = pm.probe_api_health(info)
        if not api_ok and api_err:
            print(f"[Orchestrator] ⚠️ Backend API returned server error: {api_err[:200]}")
            healed = self._fix_server_errors(
                f"API health check failed with server error:\n{api_err}\nCheck database models, unapplied migrations, and route handlers.",
                pm,
                entrypoint=getattr(info, "backend_entrypoint", None),
                cwd=getattr(info, "backend_cwd", None)
            )
            if healed:
                info = healed
                s.preview_url = info.url

        return info

    def _fix_frontend_errors(self, error_output: str, pm, cwd: str | None = None) -> Any:
        """Ask AI to fix frontend startup/compilation errors — retries preview after fix.
        
        Dynamically handles ANY frontend tech stack (Vite, Webpack, Next.js, Nuxt, React, Vue, Svelte, Angular).
        Uses the existing conversation context if available.
        Max 2 attempts.
        """
        from infrastructure.claude_tool_client import ClaudeToolClient
        s = self._state
        config = self._router.route(TaskType.build_fix, model=s.model_name)
        MAX_ATTEMPTS = 2

        for attempt in range(MAX_ATTEMPTS):
            print(f"[Orchestrator] Frontend fix attempt {attempt + 1}/{MAX_ATTEMPTS}...")
            self._post_event("frontend_fix_started", {
                "session_id": s.session_id, "task_id": s.task_id,
                "attempt": attempt + 1,
                "error": error_output[:500],
            })

            tools = self._registry.get_tools(ToolPhase.build_fix)
            executor = ToolExecutor(self._mcp, self._registry)

            client = ClaudeToolClient(
                model=config.model,
                api_key=config.api_key,
                tools=tools,
                max_tokens=config.max_tokens,
                temperature=config.temperature,
                file_manifest=self._active_file_manifest,
            )

            fe_hint = f"Working directory: {cwd}\n" if cwd else ""
            user_msg = (
                f"The frontend dev server or build failed to start/compile with this error:\n\n{error_output}\n\n"
                f"Workspace: {s.workspace_path}\n"
                f"{fe_hint}"
                "Diagnose and fix the issue. Common causes:\n"
                "- Missing imported file or component (e.g. routes, components, pages) — create it or correct the import.\n"
                "- Missing path alias configuration (e.g. `@/` in vite.config or tsconfig) — configure alias or adjust imports.\n"
                "- Syntax error, broken export, or invalid JSX/TSX.\n"
                "Inspect the failing file and make the targeted fix so the frontend compiles and runs cleanly."
            )

            if self._active_conversation:
                messages = list(self._active_conversation)
                messages.append({"role": "user", "content": user_msg})
            else:
                messages = [{"role": "user", "content": user_msg}]

            result = client.run_tool_loop(
                system=PromptBuilder.build(PromptPhase.BUILD_FIX),
                messages=messages,
                tool_executor=executor,
                max_iterations=15,
            )

            self._active_conversation = result.conversation
            self._active_file_manifest = client._file_manifest

            s.tool_call_count += executor.tool_call_count
            for f in executor.files_changed:
                s.track_file_change(f)

            print(f"[Orchestrator] Frontend fix: {executor.tool_call_count} tool calls, {len(executor.files_changed)} files changed")

            if not executor.files_changed:
                print("[Orchestrator] No files changed — stopping frontend fix")
                break

            # Kill old frontend process and restart preview
            try:
                pm.stop_frontend()
            except Exception:
                pass

            time.sleep(1)
            info = pm.start_preview(project_type="auto")
            s.preview_url = info.url

            if not getattr(info, "frontend_error", None):
                print(f"[Orchestrator] ✅ Frontend fixed and running!")
                self._post_event("frontend_fix_completed", {
                    "session_id": s.session_id, "task_id": s.task_id,
                    "attempt": attempt + 1,
                    "status": "fixed",
                })
                return info

            error_output = info.frontend_error
            print(f"[Orchestrator] Frontend still failing: {error_output[:200]}")

        print("[Orchestrator] Frontend fix attempts exhausted")
        self._post_event("frontend_fix_completed", {
            "session_id": s.session_id, "task_id": s.task_id,
            "status": "exhausted",
            "error": error_output[:500],
        })
        return None

    def _fix_server_errors(self, error_output: str, pm, entrypoint: str | None = None, cwd: str | None = None) -> Any:
        """Ask AI to fix backend server errors — retries preview after fix.

        Similar to build fix and console fix, but for backend startup failures.
        Uses the existing conversation (AI already knows what it wrote).
        Max 2 attempts to prevent infinite loops.
        """
        from infrastructure.claude_tool_client import ClaudeToolClient
        s = self._state
        # Route with the session's CURRENT model (state.model_name) so a
        # follow-up model switch changes which engine this phase calls.
        config = self._router.route(TaskType.build_fix, model=s.model_name)
        MAX_ATTEMPTS = 2

        for attempt in range(MAX_ATTEMPTS):
            print(f"[Orchestrator] Server fix attempt {attempt + 1}/{MAX_ATTEMPTS}...")
            self._post_event("server_fix_started", {
                "session_id": s.session_id, "task_id": s.task_id,
                "attempt": attempt + 1,
                "error": error_output[:500],
            })

            tools = self._registry.get_tools(ToolPhase.build_fix)
            executor = ToolExecutor(self._mcp, self._registry)

            client = ClaudeToolClient(
                model=config.model,
                api_key=config.api_key,
                tools=tools,
                max_tokens=config.max_tokens,
                temperature=config.temperature,
                file_manifest=self._active_file_manifest,
            )

            server_hint = (
                f"Backend entrypoint file: {entrypoint}\n"
                f"Working directory: {cwd}\n"
                f"Inspect `{entrypoint}` using `read_file(path='{entrypoint}')` to diagnose the failure.\n"
            ) if entrypoint else ""

            user_msg = (
                f"The backend server failed to start or threw a server error:\n\n{error_output}\n\n"
                f"Workspace: {s.workspace_path}\n"
                f"{server_hint}"
                "Fix the server file, models, or configuration so it starts successfully and responds cleanly. "
                "If database tables or migrations are missing, ensure migrations are created or tables defined. "
                "One targeted edit — do NOT rewrite the entire file."
            )

            # Continue from existing conversation if available (saves ~50K tokens)
            if self._active_conversation:
                messages = list(self._active_conversation)
                messages.append({"role": "user", "content": user_msg})
            else:
                messages = [{"role": "user", "content": user_msg}]

            result = client.run_tool_loop(
                system=PromptBuilder.build(PromptPhase.SERVER_FIX),
                messages=messages,
                tool_executor=executor,
                max_iterations=15,
            )

            # Store conversation and manifest for potential future continuation
            self._active_conversation = result.conversation
            self._active_file_manifest = client._file_manifest

            s.tool_call_count += executor.tool_call_count
            for f in executor.files_changed:
                s.track_file_change(f)

            print(f"[Orchestrator] Server fix: {executor.tool_call_count} tool calls, "
                  f"{len(executor.files_changed)} files changed")

            if not executor.files_changed:
                print("[Orchestrator] No files changed — stopping server fix")
                break

            # Kill old backend process and restart preview
            try:
                pm.stop_backend()
            except Exception:
                pass

            time.sleep(1)
            info = pm.start_preview(project_type="auto")
            s.preview_url = info.url

            if not info.backend_error:
                print(f"[Orchestrator] ✅ Backend fixed and running on port {info.backend_port}")
                self._post_event("server_fix_completed", {
                    "session_id": s.session_id, "task_id": s.task_id,
                    "attempt": attempt + 1,
                    "status": "fixed",
                })
                return info

            error_output = info.backend_error
            print(f"[Orchestrator] Backend still failing: {error_output[:200]}")

        print("[Orchestrator] Server fix exhausted — backend may not be functional")
        self._post_event("server_fix_completed", {
            "session_id": s.session_id, "task_id": s.task_id,
            "status": "exhausted",
            "error": error_output[:500],
        })
        return None

    # ------------------------------------------------------------------
    # Phase 5: console error check
    # ------------------------------------------------------------------

    def _check_console_errors(self):
        """Run Playwright to capture browser console errors after preview is live."""
        from runtime.console_checker import check_console_errors
        s = self._state
        print("[Orchestrator] Checking browser console for errors...")
        
        result = check_console_errors(
            url=s.preview_url or "http://localhost:80",
            timeout_ms=15000,
            wait_after_load_ms=3000,
            workspace_path=s.workspace_path,
        )
        
        if result.has_errors:
            print(f"[Orchestrator] ⚠️ Found {result.error_count} console error(s)")
            for err in result.errors:
                print(f"  → {err}")
        else:
            print(f"[Orchestrator] ✅ No console errors detected ({result.check_duration_ms}ms)")
        
        self._post_event("console_check", {
            "session_id": s.session_id,
            "task_id": s.task_id,
            "error_count": result.error_count,
            "warning_count": result.warning_count,
            "errors": [e.to_dict() for e in result.errors],
        })

        return result

    def _fix_console_errors(self, console_result) -> None:
        """Ask AI to fix browser console errors — capped at 2 rounds per batch.
        
        After cap hit, saves context and waits for user retry signal.
        User can click "Fix Those Issues" to trigger another batch of fixes.
        AI continues from where it left off — no re-reading files.
        
        Hard rules:
        - MAX 2 rounds per batch (not 3)
        - If 0 files changed in any round → stop immediately
        - Always post console_fix_completed event with can_retry flag
        - After cap, watch for retry signal file and continue
        """
        from infrastructure.claude_tool_client import ClaudeToolClient
        from agent.prompts.system_prompts import CONSOLE_FIX_PROMPT, CONSOLE_FIX_ESCALATED_PROMPT
        import json
        import os
        import time

        s = self._state
        # Route with the session's CURRENT model (state.model_name) so a
        # follow-up model switch changes which engine this phase calls.
        config = self._router.route(TaskType.build_fix, model=s.model_name)
        MAX_ROUNDS = 2  # Hard cap per batch
        ITERATIONS_PER_ROUND = 20  # Allow enough turns: inspect -> edit -> verify (expanded per user request)
        RETRY_CONTEXT_FILE = os.path.join(s.workspace_path, ".console_fix_context.json")
        RETRY_SIGNAL_FILE = os.path.join(s.workspace_path, ".console_fix_retry")
        RETRY_POLL_INTERVAL = 3  # seconds
        RETRY_MAX_WAIT = 300  # 5 min max wait for retry

        total_rounds_used = 0

        def _post_console_fix_completed(payload):
            """Post a console_fix_completed lifecycle event (usage is auto-reported per call)."""
            self._post_event("console_fix_completed", payload)

        def _run_fix_batch(current_console_result, start_round=1):
            """Run up to MAX_ROUNDS of console fixing. Returns remaining ConsoleCheckResult."""
            nonlocal total_rounds_used
            rounds_this_batch = 0

            for round_num in range(start_round, start_round + MAX_ROUNDS):
                total_rounds_used += 1
                rounds_this_batch += 1
                print(f"[Orchestrator] Console fix round {round_num}...")
                self._post_event("console_fix_progress", {
                    "session_id": s.session_id,
                    "task_id": s.task_id,
                    "round": round_num,
                    "message": f"Fixing console errors (round {round_num})...",
                    "errors_remaining": current_console_result.error_count,
                })

                prompt = CONSOLE_FIX_PROMPT if round_num <= 2 else CONSOLE_FIX_ESCALATED_PROMPT
                tools = self._registry.get_tools(ToolPhase.build_fix)
                executor = ToolExecutor(self._mcp, self._registry)

                fix_prompt = current_console_result.to_fix_prompt(s.workspace_path)
                if not fix_prompt.strip():
                    print("[Orchestrator] No actionable errors to fix. Skipping.")
                    break

                user_msg = (
                    f"{fix_prompt}\n\n"
                    f"Workspace: {s.workspace_path}\n"
                    f"Round {round_num}: Fix the runtime console errors listed above.\n"
                    "IMPORTANT: Read ONLY the targeted component lines, apply replace_file_content immediately, and verify with check_syntax.\n"
                    "CRITICAL: Do NOT call read_file on workspace folders or directories (e.g. '/workspace' or 'src/'). Only read specific .jsx/.js files.\n"
                    "CRITICAL: NEVER read or edit files inside `node_modules/` — these are third-party packages you cannot modify. "
                    "If an error points to a node_modules path, find and fix the CALLING component in `src/` instead."
                )

                # Continue from existing conversation if available (saves ~50K tokens)
                if self._active_conversation:
                    messages = list(self._active_conversation)
                    messages.append({"role": "user", "content": user_msg})
                else:
                    messages = [{"role": "user", "content": user_msg}]

                client = ClaudeToolClient(
                    model=config.model,
                    api_key=config.api_key,
                    tools=tools,
                    max_tokens=config.max_tokens,
                    temperature=config.temperature,
                    file_manifest=self._active_file_manifest,
                )

                result = client.run_tool_loop(
                    system=prompt,
                    messages=messages,
                    tool_executor=executor,
                    max_iterations=ITERATIONS_PER_ROUND,
                )

                # Store conversation and manifest for next round continuation
                self._active_conversation = result.conversation
                self._active_file_manifest = client._file_manifest

                s.tool_call_count += executor.tool_call_count
                for f in executor.files_changed:
                    s.track_file_change(f)

                files_fixed = len(executor.files_changed)
                print(f"[Orchestrator] Round {round_num}: {files_fixed} files changed")

                if files_fixed == 0:
                    print(f"[Orchestrator] No files changed — AI unable to fix. Stopping.")
                    break

                # Rebuild after fixes
                try:
                    s.built_in_tool_loop = False
                    self._run_build()
                except Exception as e:
                    print(f"[Orchestrator] Rebuild failed: {e}")
                    break

                # Restart preview
                try:
                    self._run_preview()
                    time.sleep(2)
                except Exception as e:
                    print(f"[Orchestrator] Preview restart failed: {e}")
                    break

                # Re-check console
                print(f"[Orchestrator] Re-checking console...")
                current_console_result = self._check_console_errors()

                if not current_console_result.has_errors:
                    print(f"[Orchestrator] All console errors fixed!")
                    return current_console_result

                print(f"[Orchestrator] {current_console_result.error_count} error(s) remain")

            return current_console_result

        # --- Run first batch of fixes ---
        console_result = _run_fix_batch(console_result, start_round=1)

        # --- If errors remain, record context ---
        if console_result and console_result.has_errors:
            remaining = console_result.error_count
            error_msgs = [str(e) for e in console_result.errors]

            # Save context for retry
            context = {
                "session_id": s.session_id,
                "task_id": s.task_id,
                "errors": error_msgs,
                "error_count": remaining,
                "rounds_used": total_rounds_used,
                "files_changed": list(s.files_changed),
            }
            with open(RETRY_CONTEXT_FILE, "w") as f:
                json.dump(context, f, indent=2)
            print(f"[Orchestrator] Saved fix context to {RETRY_CONTEXT_FILE}")

            # Post event with can_retry flag
            _post_console_fix_completed({
                "session_id": s.session_id,
                "task_id": s.task_id,
                "status": "partial",
                "message": f"{remaining} console error(s) remain. Click 'Fix Those Issues' to retry.",
                "errors_remaining": remaining,
                "errors": error_msgs[:5],
                "can_retry": True,
                "rounds_used": total_rounds_used,
            })
            print(f"[Orchestrator] {remaining} errors remain. Waiting for retry signal...")

            # --- Wait for retry signal ---
            start_wait = time.time()
            while time.time() - start_wait < RETRY_MAX_WAIT:
                if os.path.exists(RETRY_SIGNAL_FILE):
                    print("[Orchestrator] Retry signal received! Continuing fixes...")
                    os.remove(RETRY_SIGNAL_FILE)  # Consume the signal

                    # Reload context (user might have updated errors)
                    try:
                        with open(RETRY_CONTEXT_FILE) as f:
                            context = json.load(f)
                        # Re-check console for fresh errors
                        console_result = self._check_console_errors()
                        if not console_result or not console_result.has_errors:
                            _post_console_fix_completed({
                                "session_id": s.session_id,
                                "task_id": s.task_id,
                                "status": "fixed",
                                "message": "All errors resolved!",
                                "errors_remaining": 0,
                                "can_retry": False,
                            })
                            return
                    except Exception:
                        console_result = self._check_console_errors()

                    if console_result and console_result.has_errors:
                        # Run another batch of fixes (2 more rounds)
                        self._post_event("console_fix_progress", {
                            "session_id": s.session_id,
                            "task_id": s.task_id,
                            "round": total_rounds_used + 1,
                            "message": f"Retrying fixes (batch 2)...",
                            "errors_remaining": console_result.error_count,
                        })
                        console_result = _run_fix_batch(console_result, start_round=total_rounds_used + 1)

                    # Check final state
                    if not console_result or not console_result.has_errors:
                        _post_console_fix_completed({
                            "session_id": s.session_id,
                            "task_id": s.task_id,
                            "status": "fixed",
                            "message": "All errors resolved!",
                            "errors_remaining": 0,
                            "can_retry": False,
                        })
                    else:
                        remaining = console_result.error_count
                        error_msgs = [str(e) for e in console_result.errors]
                        # Update context for potential next retry
                        context["errors"] = error_msgs
                        context["error_count"] = remaining
                        context["rounds_used"] = total_rounds_used
                        with open(RETRY_CONTEXT_FILE, "w") as f:
                            json.dump(context, f, indent=2)

                        _post_console_fix_completed({
                            "session_id": s.session_id,
                            "task_id": s.task_id,
                            "status": "partial",
                            "message": f"{remaining} error(s) still remain. Click 'Fix Those Issues' to retry again.",
                            "errors_remaining": remaining,
                            "errors": error_msgs[:5],
                            "can_retry": True,
                            "rounds_used": total_rounds_used,
                        })
                    # Loop back to wait for next retry
                    start_wait = time.time()  # Reset timer
                    continue

                time.sleep(RETRY_POLL_INTERVAL)

            # Timed out waiting for retry
            print(f"[Orchestrator] Retry wait timed out ({RETRY_MAX_WAIT}s). Exiting.")
            _post_console_fix_completed({
                "session_id": s.session_id,
                "task_id": s.task_id,
                "status": "timed_out",
                "message": f"{remaining} error(s) remain. Retry window expired.",
                "errors_remaining": remaining,
                "can_retry": False,
            })

        else:
            # All clean
            _post_console_fix_completed({
                "session_id": s.session_id,
                "task_id": s.task_id,
                "status": "clean",
                "message": "No console errors found.",
                "errors_remaining": 0,
                "can_retry": False,
            })

        return console_result

    # ------------------------------------------------------------------
    # Callback
    # ------------------------------------------------------------------

    def _post_event(self, event_type: str, payload: dict) -> None:
        """POST an event to the FastAPI callback endpoint.

        Architecture §17: every major lifecycle event needs correlation fields.
        The callback secret is verified server-side (HMAC check) so arbitrary
        callers cannot inject fake events into the platform.
        """
        import hashlib
        import hmac
        import json
        import urllib.request
        import urllib.error

        s = self._state

        # Resolve callback URL: if inside Docker, replace localhost with host.docker.internal
        callback_url = s.callback_url
        if callback_url and ('localhost' in callback_url or '127.0.0.1' in callback_url):
            import socket
            try:
                socket.getaddrinfo('host.docker.internal', None)
                callback_url = callback_url.replace('localhost', 'host.docker.internal').replace('127.0.0.1', 'host.docker.internal')
            except socket.gaierror:
                pass  # Not in Docker, keep localhost

        if not isinstance(payload, dict):
            payload = {"message": str(payload)}
        else:
            payload = dict(payload)

        # Ensure session_id, task_id, and project_id are always injected so callbacks route correctly
        if "session_id" not in payload and getattr(s, "session_id", None):
            payload["session_id"] = s.session_id
        if "task_id" not in payload and getattr(s, "task_id", None):
            payload["task_id"] = s.task_id
        if "project_id" not in payload:
            proj_id = getattr(s, "project_id", None) or os.environ.get("PROJECT_ID")
            if proj_id:
                payload["project_id"] = proj_id

        body = json.dumps({"event_type": event_type, "payload": payload}).encode()
        sig = hmac.new(s.callback_secret.encode(), body, hashlib.sha256).hexdigest()

        try:
            req = urllib.request.Request(
                url=callback_url,
                data=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Callback-Secret": sig,
                    "X-Session-Id": getattr(s, "session_id", "") or "",
                    "X-Task-Id": getattr(s, "task_id", "") or "",
                    "X-Project-Id": getattr(s, "project_id", "") or os.environ.get("PROJECT_ID", "") or "",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=3) as resp:
                print(f"[Orchestrator] Event '{event_type}' posted: {resp.status}")
        except urllib.error.URLError as exc:
            # Non-fatal: agent continues even if callback fails
            print(f"[Orchestrator] WARNING: Could not post event '{event_type}': {exc}")
        except Exception as exc:
            print(f"[Orchestrator] WARNING: Unexpected error posting event: {exc}")
