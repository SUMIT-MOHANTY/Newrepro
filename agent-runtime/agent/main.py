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


def main() -> None:
    print("[AgentRuntime] Starting agent session...")

    # Build state from environment
    try:
        from agent.state import AgentState
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

    print(f"[AgentRuntime] Session: {state.session_id} | Task: {state.task_id}")
    print(f"[AgentRuntime] Prompt: {state.prompt}")


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
            orchestrator.run()
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
    IDLE_TIMEOUT_SECONDS = int(os.environ.get("IDLE_TIMEOUT_SECONDS", "900"))
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
