"""
Agent Contract Store
Shared in-memory + DB-backed store for:
  1. API contracts (endpoint paths, methods, models) — fixes frontend/backend mismatch
  2. Migration registry — fixes migration ordering
  3. File lock enforcement — fixes merge conflicts
  4. Deadlock detection — fixes circular peer-wait
  5. Agent crash detection — fixes long peer-wait timeout

All agents read/write here so they stay in sync without waiting for git.
"""
import asyncio
import logging
import time
from typing import Dict, Any, Optional, List, Set
from datetime import datetime

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# 1. API CONTRACT STORE
# Agents publish their endpoints here. Frontend agents read before building.
# ─────────────────────────────────────────────────────────────────────────────

# project_token -> { "endpoint_key": { path, method, agent_id, models, timestamp } }
_api_contracts: Dict[str, Dict[str, Any]] = {}
_contract_lock = asyncio.Lock()


async def publish_api_contract(
    project_token: str,
    agent_id: str,
    endpoints: List[Dict[str, Any]],  # [{ "path": "/api/loans/", "method": "GET", "models": ["Loan"] }]
) -> None:
    """Backend agent publishes its API endpoints so frontend agents use correct paths."""
    async with _contract_lock:
        store = _api_contracts.setdefault(project_token, {})
        for ep in endpoints:
            key = f"{ep.get('method','GET').upper()}:{ep.get('path','')}"
            store[key] = {**ep, "agent_id": agent_id, "published_at": time.time()}
    logger.info(f"[{agent_id}] Published {len(endpoints)} API contracts for {project_token}")


async def get_api_contracts(project_token: str) -> Dict[str, Any]:
    """Frontend agents call this to get all known backend endpoints."""
    async with _contract_lock:
        return dict(_api_contracts.get(project_token, {}))


async def validate_api_usage(
    project_token: str,
    agent_id: str,
    used_paths: List[str],
) -> List[str]:
    """
    Check if paths used by frontend agent exist in the contract store.
    Returns list of mismatches with suggestions.
    """
    async with _contract_lock:
        contracts = _api_contracts.get(project_token, {})

    known_paths = {v["path"] for v in contracts.values()}
    mismatches = []

    for used in used_paths:
        if used not in known_paths:
            # Find closest match
            suggestion = _closest_path(used, known_paths)
            mismatches.append(
                f"Path '{used}' not in contract. "
                + (f"Did you mean '{suggestion}'?" if suggestion else "No similar path found.")
            )

    if mismatches:
        logger.warning(f"[{agent_id}] API contract mismatches: {mismatches}")

    return mismatches


def _closest_path(target: str, known: Set[str]) -> Optional[str]:
    """Simple similarity: find path with most matching segments."""
    if not known:
        return None
    target_parts = set(target.strip("/").split("/"))
    best, best_score = None, 0
    for p in known:
        parts = set(p.strip("/").split("/"))
        score = len(target_parts & parts)
        if score > best_score:
            best, best_score = p, score
    return best if best_score > 0 else None


# ─────────────────────────────────────────────────────────────────────────────
# 2. MIGRATION REGISTRY
# Agents register their models before running migrations.
# Migration runner waits until all declared models are registered.
# ─────────────────────────────────────────────────────────────────────────────

# project_token -> { model_name: { agent_id, registered_at, migrated } }
_migration_registry: Dict[str, Dict[str, Any]] = {}
_migration_lock = asyncio.Lock()


async def register_models(
    project_token: str,
    agent_id: str,
    model_names: List[str],
) -> None:
    """Agent declares which models it will create (before running migrations)."""
    async with _migration_lock:
        reg = _migration_registry.setdefault(project_token, {})
        for name in model_names:
            reg[name] = {"agent_id": agent_id, "registered_at": time.time(), "migrated": False}
    logger.info(f"[{agent_id}] Registered models: {model_names}")


async def mark_models_migrated(project_token: str, model_names: List[str]) -> None:
    async with _migration_lock:
        reg = _migration_registry.get(project_token, {})
        for name in model_names:
            if name in reg:
                reg[name]["migrated"] = True


async def wait_for_models_before_migration(
    project_token: str,
    agent_id: str,
    required_models: List[str],
    timeout_seconds: int = 300,
) -> bool:
    """
    Before running migrations, wait until all required models are registered
    by their respective agents. Prevents migration ordering failures.
    """
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        async with _migration_lock:
            reg = _migration_registry.get(project_token, {})
            missing = [m for m in required_models if m not in reg]

        if not missing:
            logger.info(f"[{agent_id}] All required models registered: {required_models}")
            return True

        logger.info(f"[{agent_id}] Waiting for models to be registered: {missing}")
        await asyncio.sleep(10)

    logger.warning(f"[{agent_id}] Migration wait timed out. Missing models: {missing}")
    return False


def get_registered_models(project_token: str) -> Dict[str, Any]:
    return dict(_migration_registry.get(project_token, {}))


# ─────────────────────────────────────────────────────────────────────────────
# 3. FILE LOCK ENFORCEMENT
# Hard locks on shared files (urls.py, settings.py, etc.)
# Agents must acquire lock before writing, preventing merge conflicts.
# ─────────────────────────────────────────────────────────────────────────────

# project_token -> { file_path: { agent_id, acquired_at, timeout } }
_file_locks: Dict[str, Dict[str, Any]] = {}
_file_lock_mutex = asyncio.Lock()

# Files that MUST be locked before writing (shared across agents)
SHARED_FILES = {
    "urls.py", "settings.py", "wsgi.py", "asgi.py",
    "App.js", "App.jsx", "App.tsx",
    "router.js", "router.jsx", "router.tsx",
    "index.js", "index.jsx", "index.tsx",
    "docker-compose.yml", "requirements.txt", "package.json",
}


async def acquire_file_lock(
    project_token: str,
    agent_id: str,
    file_path: str,
    timeout_seconds: int = 120,
) -> bool:
    """
    Acquire exclusive write lock on a file.
    Returns True if lock acquired, False if timed out.
    """
    filename = file_path.split("/")[-1]
    if filename not in SHARED_FILES:
        return True  # Non-shared files don't need locking

    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        async with _file_lock_mutex:
            locks = _file_locks.setdefault(project_token, {})
            existing = locks.get(file_path)

            # Check if existing lock is stale (holder crashed)
            if existing:
                age = time.time() - existing.get("acquired_at", 0)
                holder = existing.get("agent_id", "")
                
                # Check if we already hold this lock
                if holder == agent_id:
                    # Update timestamp to keep it fresh
                    existing["acquired_at"] = time.time()
                    logger.debug(f"[{agent_id}] Renewed existing lock: {file_path}")
                    return True

                if age > 300 or _is_agent_crashed(project_token, holder):
                    # Stale lock — take it over
                    logger.warning(f"[{agent_id}] Taking over stale lock on {file_path} from {holder}")
                    existing = None

            if not existing:
                locks[file_path] = {
                    "agent_id": agent_id,
                    "acquired_at": time.time(),
                    "file_path": file_path,
                }
                logger.info(f"[{agent_id}] Acquired lock: {file_path}")
                return True

        await asyncio.sleep(5)

    logger.warning(f"[{agent_id}] Could not acquire lock on {file_path} after {timeout_seconds}s")
    return False


async def release_file_lock(project_token: str, agent_id: str, file_path: str) -> None:
    async with _file_lock_mutex:
        locks = _file_locks.get(project_token, {})
        existing = locks.get(file_path)
        if existing and existing.get("agent_id") == agent_id:
            del locks[file_path]
            logger.info(f"[{agent_id}] Released lock: {file_path}")


async def release_all_locks(project_token: str, agent_id: str) -> None:
    """Release all locks held by an agent (called on crash or completion)."""
    async with _file_lock_mutex:
        locks = _file_locks.get(project_token, {})
        to_release = [fp for fp, info in locks.items() if info.get("agent_id") == agent_id]
        for fp in to_release:
            del locks[fp]
    if to_release:
        logger.info(f"[{agent_id}] Released all locks: {to_release}")


def get_active_locks(project_token: str) -> Dict[str, Any]:
    return dict(_file_locks.get(project_token, {}))


# ─────────────────────────────────────────────────────────────────────────────
# 4. DEADLOCK DETECTION
# Tracks who is waiting for whom. Detects cycles (A→B→A).
# ─────────────────────────────────────────────────────────────────────────────

# project_token -> { agent_id: set of agent_ids it's waiting for }
_wait_graph: Dict[str, Dict[str, Set[str]]] = {}
_wait_graph_lock = asyncio.Lock()


async def register_wait(project_token: str, waiter: str, waiting_for_agent: str) -> bool:
    """
    Register that `waiter` is waiting for `waiting_for_agent`.
    Returns True if safe, False if deadlock detected.
    """
    async with _wait_graph_lock:
        graph = _wait_graph.setdefault(project_token, {})
        graph.setdefault(waiter, set()).add(waiting_for_agent)

        # Detect cycle using DFS
        if _has_cycle(graph, waiter, set()):
            logger.error(f"DEADLOCK DETECTED: {waiter} ↔ {waiting_for_agent} in {project_token}")
            # Break the cycle: remove the edge we just added
            graph[waiter].discard(waiting_for_agent)
            return False  # Caller should NOT wait — proceed without peer

    return True


async def clear_wait(project_token: str, waiter: str) -> None:
    async with _wait_graph_lock:
        graph = _wait_graph.get(project_token, {})
        graph.pop(waiter, None)


def _has_cycle(graph: Dict[str, Set[str]], start: str, visited: Set[str]) -> bool:
    if start in visited:
        return True
    visited.add(start)
    for neighbor in graph.get(start, set()):
        if _has_cycle(graph, neighbor, visited.copy()):
            return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
# 5. AGENT CRASH DETECTION
# Agents send heartbeats. If heartbeat stops, they're considered crashed.
# Waiting agents check this instead of sitting for 10 minutes.
# ─────────────────────────────────────────────────────────────────────────────

# project_token -> { agent_id: last_heartbeat_timestamp }
_heartbeats: Dict[str, Dict[str, float]] = {}
_heartbeat_lock = asyncio.Lock()

HEARTBEAT_TIMEOUT = 120  # seconds — agent considered crashed if no heartbeat for 2 min


async def heartbeat(project_token: str, agent_id: str) -> None:
    """Agent calls this periodically to signal it's alive."""
    async with _heartbeat_lock:
        _heartbeats.setdefault(project_token, {})[agent_id] = time.time()


def _is_agent_crashed(project_token: str, agent_id: str) -> bool:
    beats = _heartbeats.get(project_token, {})
    last = beats.get(agent_id)
    if last is None:
        return False  # Never registered — assume alive
    return (time.time() - last) > HEARTBEAT_TIMEOUT


def is_agent_alive(project_token: str, agent_id: str) -> bool:
    return not _is_agent_crashed(project_token, agent_id)


def get_crashed_agents(project_token: str) -> List[str]:
    beats = _heartbeats.get(project_token, {})
    return [aid for aid, ts in beats.items() if (time.time() - ts) > HEARTBEAT_TIMEOUT]


async def wait_for_agent_or_crash(
    project_token: str,
    waiter_id: str,
    target_agent_id: str,
    q: asyncio.Queue,
    missing_symbols: List[str],
    timeout_seconds: int = 600,
) -> str:
    """
    Wait for READY signal OR detect target agent crash.
    Returns: "resolved" | "crashed" | "timeout" | "deadlock"
    """
    # Deadlock check first
    safe = await register_wait(project_token, waiter_id, target_agent_id)
    if not safe:
        return "deadlock"

    deadline = asyncio.get_event_loop().time() + timeout_seconds

    try:
        while asyncio.get_event_loop().time() < deadline:
            # Check if target crashed
            if _is_agent_crashed(project_token, target_agent_id):
                logger.warning(f"[{waiter_id}] Target agent {target_agent_id} appears crashed. Stopping wait.")
                return "crashed"

            remaining = deadline - asyncio.get_event_loop().time()
            try:
                msg = await asyncio.wait_for(q.get(), timeout=min(15.0, remaining))
            except asyncio.TimeoutError:
                continue

            if msg.get("msg_type") in ("READY", "RESOLVED"):
                ready_text = (msg.get("message", "") + " " + str(msg.get("payload", ""))).lower()
                if any(sym.lower() in ready_text for sym in missing_symbols):
                    return "resolved"

            if msg.get("_event") == "resolved" and msg.get("from_agent") != waiter_id:
                return "resolved"

        return "timeout"
    finally:
        await clear_wait(project_token, waiter_id)
