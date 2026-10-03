"""Agent Runtime entry point.

Architecture §7.1 main.py:
Loads configuration from environment variables injected by AgentManager,
initializes MCPServer and Orchestrator, runs the agent session, and exits.

All durable state (AgentSession rows, AgentTask rows, AgentEvents) are
written via the FastAPI callback — this process does NOT touch the platform
MySQL database directly (architecture principle: separation of control and
execution planes, §4).
"""
from __future__ import annotations

import json
import os
import sys
import time
import traceback
from pathlib import Path


def _load_task_config(workspace_path: str = "/workspace") -> dict | None:
    """Load task configuration from per-agent config or fallback to task_config.json."""
    import re
    ws = Path(workspace_path)
    agent_config_file = os.environ.get("AGENT_CONFIG_FILE")
    agent_id = os.environ.get("AGENT_ID")
    candidate_paths = []
    if agent_config_file:
        candidate_paths.append(ws / ".agent" / agent_config_file)
        candidate_paths.append(ws / agent_config_file)
    if agent_id:
        clean_aid = re.sub(r'[^a-zA-Z0-9_]', '_', agent_id)
        candidate_paths.append(ws / ".agent" / f"task_config_{clean_aid}.json")
        candidate_paths.append(ws / f"task_config_{clean_aid}.json")
    candidate_paths.append(ws / ".agent" / "task_config.json")
    candidate_paths.append(ws / "task_config.json")

    for config_path in candidate_paths:
        if config_path.exists():
            try:
                raw = config_path.read_text(encoding="utf-8")
                data = json.loads(raw)
                print(f"[AgentRuntime] Loaded task config from {config_path}")
                return data
            except Exception as exc:
                print(f"[AgentRuntime] Warning: Failed to parse {config_path}: {exc}")
    return None


def main() -> None:
    print("[AgentRuntime] Starting agent session...")

    # Priority 1: Load task config from JSON file written by control plane
    # Priority 2: Fall back to environment variables (backward compat)
    from agent.state import AgentState

    task_config = _load_task_config(
        os.environ.get("WORKSPACE_PATH", "/workspace")
    )

    if task_config:
        # Inject config values into environment so AgentState.from_env() picks them up
        env_mapping = {
            "SESSION_ID": "session_id",
            "TASK_ID": "task_id",
            "TASK_TYPE": "task_type",
            "PROMPT": "prompt",
            "WORKSPACE_PATH": "workspace_path",
            "PROJECT_ID": "project_id",
            "TENANT_ID": "tenant_id",
            "CALLBACK_URL": "callback_url",
            "CALLBACK_SECRET": "callback_secret",
            "MODEL_NAME": "model_name",
            "AI_MODEL": "model_name",
            "MODEL_PROVIDER": "model_provider",
            "TOOL_USE_ENABLED": "tool_use_enabled",
            "WEB_SEARCH_ENABLED": "web_search_enabled",
            "GIT_REPO_URL": "git_repo_url",
            "MAX_TOOL_CALLS": "max_tool_calls",
        }
        for env_key, config_key in env_mapping.items():
            if config_key in task_config and env_key not in os.environ:
                val = task_config[config_key]
                os.environ[env_key] = str(val) if not isinstance(val, bool) else str(val).lower()

    try:
        state = AgentState.from_env()
    except KeyError as exc:
        print(f"[AgentRuntime] FATAL: Missing required environment variable: {exc}")
        sys.exit(1)

    # Check for follow-up prompt (sent via file signal by agent_manager)
    follow_up_prompt = os.environ.get("FOLLOW_UP_PROMPT")
    if follow_up_prompt:
        print(f"[AgentRuntime] Follow-up prompt detected — updating state")
        state.prompt = follow_up_prompt
        state.task_type = os.environ.get("FOLLOW_UP_TASK_TYPE", state.task_type)
        follow_up_model = os.environ.get("FOLLOW_UP_MODEL")
        if follow_up_model:
            state.model_name = follow_up_model
        # Clear follow-up env vars so they don't persist
        for key in ("FOLLOW_UP_PROMPT", "FOLLOW_UP_TASK_TYPE", "FOLLOW_UP_MODEL", "FOLLOW_UP_TASK_ID"):
            os.environ.pop(key, None)

    prompt_preview = state.prompt.strip()
    if len(prompt_preview) > 300:
        first_line = prompt_preview.split('\n')[0][:120]
        print(f"[AgentRuntime] Prompt: {first_line}... ({len(prompt_preview)} chars)")
    else:
        print(f"[AgentRuntime] Prompt: {prompt_preview}")


    # Initialize MCP server
    from mcp.server import MCPServer
    mcp = MCPServer(workspace_path=state.workspace_path)

    # Initialize and run the orchestrator
    from agent.orchestrator import Orchestrator
    orchestrator = Orchestrator(state=state, mcp=mcp)

    signal_dirs = [
        Path(state.workspace_path) / ".agent_signals",
        Path("/tmp/vibe_mailbox"),
    ]
    for sdir in signal_dirs:
        try:
            sdir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

    init_marker = Path(state.workspace_path) / ".agent_initialized"
    is_existing_workspace = init_marker.exists()

    # Check if this task was already executed in this workspace
    prompts_history_file = Path(state.workspace_path) / ".agent_history" / "prompts_history.json"
    task_already_executed = False
    if prompts_history_file.exists():
        try:
            with open(prompts_history_file, "r", encoding="utf-8") as f:
                hist = json.load(f)
            if isinstance(hist, list):
                task_already_executed = any(e.get("task_id") == state.task_id for e in hist)
        except Exception:
            pass

    has_active_prompt = bool(state.prompt and state.prompt.strip())

    if is_existing_workspace and (task_already_executed or not has_active_prompt):
        print("[AgentRuntime] 🌅 Container awakened from sleep state! Workspace & history preserved.")
        try:
            orchestrator._run_preview()
            print(f"[AgentRuntime] ✅ Restored live preview on port 80: {state.preview_url}")
        except Exception as pe:
            print(f"[AgentRuntime] Warning restoring preview on wake-up: {pe}")
    else:
        if is_existing_workspace:
            print(f"[AgentRuntime] 🚀 Container started for follow-up task {state.task_id} in existing workspace.")
            if state.task_type in ("initial_generation", "greenfield", ""):
                state.task_type = "follow_up_edit"
        else:
            print(f"[AgentRuntime] 🚀 Initializing greenfield workspace for task {state.task_id}...")

        # Consume any duplicate prompt signal file in the mailbox for this task_id to prevent double execution
        for sdir in signal_dirs:
            if sdir.exists():
                for pfile in sdir.glob("prompt_*.json"):
                    try:
                        sig = json.loads(pfile.read_text(encoding="utf-8"))
                        if sig.get("task_id") == state.task_id:
                            pfile.unlink(missing_ok=True)
                    except Exception:
                        pass

        try:
            # ═══════════════════════════════════════════════════════════════
            # SUPERVISOR MODE: When multiple tasks exist in task_config.json,
            # use the SupervisorAgent to coordinate sub-agents (Backend,
            # Frontend, QA) working in parallel via the DAG scheduler.
            # LEGACY MODE: Single task → use the existing Orchestrator.
            # ═══════════════════════════════════════════════════════════════
            use_supervisor = False
            task_list = []

            if task_config:
                if isinstance(task_config, dict):
                    task_list = task_config.get("tasks", [])
                elif isinstance(task_config, list):
                    task_list = task_config
                use_supervisor = len(task_list) >= 1

            if use_supervisor:
                print(f"[AgentRuntime] 🏗️  SUPERVISOR MODE: {len(task_list)} tasks detected — launching Agent Swarm")
                from agent.supervisor import SupervisorAgent
                supervisor = SupervisorAgent(
                    workspace_path=state.workspace_path,
                    mcp=mcp,
                    router=orchestrator._router,
                    callback=orchestrator._post_event,
                    task_config=task_config,
                )
                summary = supervisor.run()
                print(f"[AgentRuntime] 📊 Swarm complete: {summary.get('completed', 0)}/{summary.get('total_tasks', 0)} tasks done")
            else:
                print(f"[AgentRuntime] 🔧 LEGACY MODE: Single task — using Orchestrator")
                orchestrator.run()

            # Boot live preview dev server upon swarm completion
            try:
                print("[AgentRuntime] 🚀 Booting live preview dev server on port 80...")
                orchestrator._run_preview()
                print(f"[AgentRuntime] ✅ Live preview ready on port 80: {state.preview_url or 'http://localhost:80'}")
            except Exception as pe:
                print(f"[AgentRuntime] Preview initialization note: {pe}")

            init_marker.touch(exist_ok=True)
            print(f"[AgentRuntime] Task {state.task_id} complete. Preview is live.")
        except Exception:
            print("[AgentRuntime] UNHANDLED EXCEPTION in agent run:")
            traceback.print_exc()

    # ══════════════════════════════════════════════════════════════════════════
    # Mailbox Daemon Loop with 15-Minute Standby & Sleep State
    # ══════════════════════════════════════════════════════════════════════════
    # Default to 15-minute standby (900s). After 15 minutes without new prompts,
    # the container exits cleanly into sleep state without deleting any files.
    IDLE_TIMEOUT_SECONDS = int(os.environ.get("IDLE_TIMEOUT_SECONDS", "30"))
    print(f"[AgentRuntime] 🚀 Agent Runtime daemon active — waiting for prompts (idle sleep timeout: {IDLE_TIMEOUT_SECONDS}s / {IDLE_TIMEOUT_SECONDS // 60}m)...")
    last_activity_time = time.time()

    while True:
        try:
            # Check for any cancellation signals
            for sdir in signal_dirs:
                if sdir.exists():
                    for cfile in sdir.glob("cancel_*.json"):
                        try:
                            cfile.unlink(missing_ok=True)
                            print(f"[AgentRuntime] 🛑 Cancel signal consumed: {cfile.name}")
                        except Exception:
                            pass

            found_signals = []
            for sdir in signal_dirs:
                if sdir.exists():
                    found_signals.extend(sorted(sdir.glob("prompt_*.json")))

            if found_signals:
                for pfile in found_signals:
                    try:
                        raw_data = pfile.read_text(encoding="utf-8")
                        pfile.unlink(missing_ok=True)
                        if not raw_data.strip():
                            continue
                        sig_data = json.loads(raw_data)
                        follow_prompt = sig_data.get("prompt", "").strip()
                        follow_task_id = sig_data.get("task_id")
                        follow_session_id = sig_data.get("session_id")
                        follow_task_type = sig_data.get("task_type", "follow_up_edit")
                        follow_model = sig_data.get("model")

                        if follow_session_id:
                            state.session_id = follow_session_id
                        if follow_model:
                            state.model_name = follow_model
                            orchestrator._router.set_model(follow_model)
                            os.environ["MODEL_NAME"] = follow_model
                            os.environ["AI_MODEL"] = follow_model

                        if follow_prompt:
                            print(f"[AgentRuntime] 📩 Mailbox signal received: task={follow_task_id} (session={state.session_id}, model={state.model_name}) | {follow_prompt[:100]}...")
                            last_activity_time = time.time()
                            orchestrator.run_follow_up(
                                prompt=follow_prompt,
                                task_id=follow_task_id,
                                task_type=follow_task_type,
                                model=follow_model,
                                session_id=follow_session_id,
                            )
                            last_activity_time = time.time()
                    except Exception as sig_err:
                        print(f"[AgentRuntime] Error processing prompt signal {pfile.name}: {sig_err}")

            # Check idle timeout (only if positive)
            if IDLE_TIMEOUT_SECONDS > 0:
                idle_duration = time.time() - last_activity_time
                if idle_duration >= IDLE_TIMEOUT_SECONDS:
                    print(f"[AgentRuntime] 💤 Container idle for {int(idle_duration)}s (>= {IDLE_TIMEOUT_SECONDS}s). Entering sleep mode.")
                    break

            time.sleep(2)
        except Exception as loop_err:
            print(f"[AgentRuntime] Daemon loop warning: {loop_err}")
            time.sleep(2)

    print("[AgentRuntime] Container entering sleep. Exiting daemon process.")
    sys.exit(0)


if __name__ == "__main__":
    main()
