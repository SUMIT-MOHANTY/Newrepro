"""One-shot relaunch of the Kuoni agent run with a cleaned workspace + new image.

Replicates agent_manager.start_runtime() exactly:
  - env built like AgentManager._build_env() (secrets read from backend/.env, never printed)
  - workspace bind-mount -> /workspace, agent-runtime repo -> /app
  - prompt signal queued in .agent_signals (this is what the mailbox daemon consumes)
  - port 80 mapped to a random 127.0.0.1 host port
  - mem/cpu limits, bridge network, dsuite labels

Usage:  python tmp_launch_kuoni.py
"""
import json
import os
import time
import uuid

import docker

PROJECT_ID = "ef3f4e4e-9d11-47b5-92d9-cd750b62e153"
WS_HOST = os.path.abspath("backend/storage/projects/ef3f4e4e-9d11-47b5-92d9-cd750b62e153")
RUNTIME_HOST = os.path.abspath("agent-runtime")
IMAGE = "dsuite-agent-runtime:latest"
BRD_PROMPT = (
    "Build a runnable prototype for **Kuoni - Inbox Management (OPNS Inbox)**.\n\n"
    "**Problem:** 1 FTE/day manually reviews, responds to, or forwards ~2,500 email enquiries "
    "(Japanese, German, English). Enquiries span booking changes, refund requests, "
    "visa/document questions and complaints, currently handled in a shared Outlook inbox "
    "with manual triage.\n\n"
    "**Goal:** A case management system that ingests enquiries, auto-classifies them "
    "(booking change / refund / visa / complaint), prioritises by SLA urgency, assigns "
    "them to team members, and tracks resolution with full audit history. "
    "Supervisors need a dashboard with SLA breach alerts and workload distribution.\n\n"
    "**Deliverable:** FastAPI backend (auth, cases, messages, channels) + React/Vite/Tailwind "
    "frontend (login, case list, case detail, dashboard). The app MUST start and serve."
)


def load_env(path: str) -> dict:
    env = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def main() -> None:
    dotenv = load_env("backend/.env")

    ai_api_key = dotenv.get("AI_API_KEY") or dotenv.get("NVIDIA_API_KEY") or ""
    ai_api_url = dotenv.get("AI_API_URL", "https://integrate.api.nvidia.com/v1/chat/completions")
    ai_model = dotenv.get("AI_MODEL", "minimaxai/minimax-m2.5")
    cb_secret = dotenv.get("AGENT_CALLBACK_SECRET", "dsuite-agent-callback-secret")
    callback_url = dotenv.get("AGENT_CALLBACK_URL", "http://host.docker.internal:8000/api/v1/callback")

    session_id = str(uuid.uuid4())
    task_id = f"{PROJECT_ID}_relaunch_{int(time.time())}"
    container_name = f"dsuite-agent-{PROJECT_ID[:16]}"

    env = {
        "SESSION_ID": session_id,
        "TASK_ID": task_id,
        "TASK_TYPE": "initial_generation",
        "PROMPT": BRD_PROMPT,
        "WORKSPACE_PATH": "/workspace",
        "PROJECT_ID": PROJECT_ID,
        "TENANT_ID": "Bourntec",
        "CALLBACK_URL": callback_url,
        "CALLBACK_SECRET": cb_secret,
        "MODEL_NAME": ai_model,
        "MODEL_PROVIDER": "custom",
        "AI_API_URL": ai_api_url,
        "AI_API_KEY": ai_api_key,
        "AI_MODEL": ai_model,
        "TOOL_USE_ENABLED": "true",
        "ALLOWED_TOOLS": "filesystem,git,terminal,build_tool",
        "MAX_TOOL_CALLS": "50",
        "WEB_SEARCH_ENABLED": "true",
        "GIT_REPO_URL": "",
        "GIT_TOKEN": "",
        "GIT_BRANCH": "main",
        "IDLE_TIMEOUT_SECONDS": "7200",
    }

    volumes = {
        WS_HOST: {"bind": "/workspace", "mode": "rw"},
        RUNTIME_HOST: {"bind": "/app", "mode": "rw"},
    }

    client = docker.from_env()
    # Remove any stale container with the same name
    try:
        old = client.containers.get(container_name)
        print(f"Removing stale container {container_name} ({old.status})")
        old.remove(force=True)
    except Exception:
        pass

    os.makedirs(os.path.join(WS_HOST, ".agent_signals"), exist_ok=True)
    signal = {
        "session_id": session_id,
        "task_id": task_id,
        "task_type": "initial_generation",
        "prompt": BRD_PROMPT,
        "model": ai_model,
        "repo_url": None,
        "git_token": None,
        "git_branch": "main",
        "allowed_tools": ["filesystem", "git", "terminal", "build_tool"],
        "timestamp": time.time(),
    }
    sig_path = os.path.join(WS_HOST, ".agent_signals", f"prompt_{int(time.time()*1000)}_{task_id[:8]}.json")
    with open(sig_path, "w", encoding="utf-8") as f:
        json.dump(signal, f)
    print(f"Prompt signal queued: {os.path.basename(sig_path)}")

    container = client.containers.run(
        image=IMAGE,
        name=container_name,
        detach=True,
        environment=env,
        volumes=volumes,
        ports={"80/tcp": ("127.0.0.1", None)},
        extra_hosts={"host.docker.internal": "host-gateway"},
        mem_limit="2g",
        cpu_quota=200000,
        cpu_period=100000,
        network_mode="bridge",
        remove=False,
        labels={
            "dsuite.session_id": session_id,
            "dsuite.tenant_id": "Bourntec",
            "dsuite.project_id": PROJECT_ID,
        },
    )
    print(f"CONTAINER_STARTED {container.id[:12]} name={container_name}")
    print(f"SESSION_ID={session_id}")
    print(f"TASK_ID={task_id}")


if __name__ == "__main__":
    main()
