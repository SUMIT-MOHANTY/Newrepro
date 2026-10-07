"""
Swarm Blackboard Service - Inter-Agent Blackboard & Dynamic File Leasing System.
Coordinates concurrent multi-agent executions, manages file leases/locks to prevent
race conditions, stores live API contracts, and broadcasts real-time collaboration events
(thoughts, locks, handshakes, repairs) to the frontend workspace modal.
"""

import os
import json
import time
import logging
import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from app.core.config import get_settings
from app.routers.helpers import broadcast_preview_log, sync_broadcast_preview_log

logger = logging.getLogger(__name__)


class SwarmBlackboard:
    """
    Central Blackboard for autonomous agents in a project workspace.
    Synchronizes across container agents and host backend via .agent/locks.json
    and .agent/collaboration_feed.json.
    """

    def __init__(self, project_token: str, workspace_dir: Optional[str] = None):
        self.project_token = project_token
        settings = get_settings()
        clean_token = (project_token or "default_project").replace("/", "_").replace("\\", "_")
        self.workspace_dir = workspace_dir or os.path.join(settings.project_storage_root, clean_token)
        self.agent_dir = os.path.join(self.workspace_dir, ".agent")
        self.locks_file = os.path.join(self.agent_dir, "locks.json")
        self.feed_file = os.path.join(self.agent_dir, "collaboration_feed.json")
        self.contracts_dir = os.path.join(self.agent_dir, "contracts")
        self.api_contract_file = os.path.join(self.contracts_dir, "api_contract.json")

        self._ensure_storage()

    def _ensure_storage(self) -> None:
        try:
            os.makedirs(self.agent_dir, exist_ok=True)
            os.makedirs(self.contracts_dir, exist_ok=True)
            if not os.path.exists(self.locks_file):
                with open(self.locks_file, "w", encoding="utf-8") as f:
                    json.dump({}, f)
            if not os.path.exists(self.feed_file):
                with open(self.feed_file, "w", encoding="utf-8") as f:
                    json.dump([], f)
        except Exception as e:
            logger.warning(f"[SwarmBlackboard] Error initializing storage: {e}")

    def _read_locks(self) -> Dict[str, Any]:
        try:
            if os.path.exists(self.locks_file):
                with open(self.locks_file, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"[SwarmBlackboard] Read locks failed: {e}")
        return {}

    def _write_locks(self, locks: Dict[str, Any]) -> None:
        try:
            tmp = f"{self.locks_file}.tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(locks, f, indent=2)
            os.replace(tmp, self.locks_file)
        except Exception as e:
            logger.error(f"[SwarmBlackboard] Write locks failed: {e}")

    def claim_file_lock(
        self,
        filepath: str,
        agent_id: str,
        reason: str = "Active file write",
        ttl_seconds: int = 180,
    ) -> Dict[str, Any]:
        """
        Claim an exclusive lock on a file.
        Returns:
            {"success": True, "lock": {...}} if claimed,
            {"success": False, "locked_by": "...", "reason": "...", "expires_at": ...} if held by peer.
        """
        norm_path = filepath.replace("\\", "/").strip().lstrip("/")
        now = time.time()
        locks = self._read_locks()

        # Check existing lock and TTL
        if norm_path in locks:
            existing = locks[norm_path]
            expires = existing.get("expires_at", 0)
            holder = existing.get("agent_id")
            if holder != agent_id and now < expires:
                # Active lock held by someone else!
                logger.info(
                    f"[SwarmBlackboard] Lock conflict: '{norm_path}' held by {holder} (expires in {int(expires - now)}s)"
                )
                sync_broadcast_preview_log(
                    project_token=self.project_token,
                    content=f"🔒 Lock conflict: {agent_id} requested '{norm_path}' but currently locked by {holder}",
                    event_type="lock_conflict",
                    payload={
                        "filepath": norm_path,
                        "requesting_agent": agent_id,
                        "holding_agent": holder,
                        "reason": existing.get("reason"),
                        "expires_at": expires,
                    },
                )
                return {
                    "success": False,
                    "locked_by": holder,
                    "reason": existing.get("reason"),
                    "expires_at": expires,
                }

        # Lock is free or expired or held by same agent
        lock_entry = {
            "agent_id": agent_id,
            "filepath": norm_path,
            "reason": reason,
            "acquired_at": now,
            "expires_at": now + ttl_seconds,
            "acquired_at_iso": datetime.now(timezone.utc).isoformat(),
        }
        locks[norm_path] = lock_entry
        self._write_locks(locks)

        # Broadcast lock claimed event
        sync_broadcast_preview_log(
            project_token=self.project_token,
            content=f"🔒 [{agent_id}] Acquired exclusive file lock for '{norm_path}': {reason}",
            event_type="file_locked",
            payload={
                "filepath": norm_path,
                "agent_id": agent_id,
                "reason": reason,
                "expires_at": lock_entry["expires_at"],
            },
        )
        return {"success": True, "lock": lock_entry}

    def release_file_lock(self, filepath: str, agent_id: str) -> bool:
        """Release a held lock on a file."""
        norm_path = filepath.replace("\\", "/").strip().lstrip("/")
        locks = self._read_locks()

        if norm_path not in locks:
            return True

        holder = locks[norm_path].get("agent_id")
        if holder == agent_id or holder is None:
            del locks[norm_path]
            self._write_locks(locks)
            sync_broadcast_preview_log(
                project_token=self.project_token,
                content=f"🔓 [{agent_id}] Released file lock for '{norm_path}'",
                event_type="file_released",
                payload={"filepath": norm_path, "agent_id": agent_id},
            )
            return True

        logger.warning(f"[SwarmBlackboard] Agent {agent_id} tried to release '{norm_path}' owned by {holder}")
        return False

    def release_all_agent_locks(self, agent_id: str) -> int:
        """Release all locks held by a specific agent upon completion or crash."""
        locks = self._read_locks()
        released = 0
        to_delete = []
        for path, lock in locks.items():
            if lock.get("agent_id") == agent_id:
                to_delete.append(path)

        for path in to_delete:
            del locks[path]
            released += 1

        if released > 0:
            self._write_locks(locks)
            sync_broadcast_preview_log(
                project_token=self.project_token,
                content=f"🔓 [{agent_id}] Released all held locks ({released} file(s))",
                event_type="all_locks_released",
                payload={"agent_id": agent_id, "count": released},
            )
        return released

    def get_active_locks(self) -> Dict[str, Any]:
        """Returns all currently valid, non-expired locks."""
        now = time.time()
        locks = self._read_locks()
        valid = {}
        cleaned = False
        for path, lock in locks.items():
            if now < lock.get("expires_at", 0):
                valid[path] = lock
            else:
                cleaned = True

        if cleaned:
            self._write_locks(valid)
        return valid

    def record_agent_thought(
        self,
        agent_id: str,
        thought: str,
        task_id: Optional[str] = None,
        file_path: Optional[str] = None,
        event_kind: str = "logic",  # "logic", "code", "repair", "waiting"
        peer_waiting: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Record and broadcast an agent thought / reasoning step to the live feed.
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        entry = {
            "id": f"thought_{int(time.time() * 1000)}",
            "agent_id": agent_id,
            "task_id": task_id,
            "file_path": file_path,
            "type": event_kind,
            "thought": thought,
            "peer_waiting": peer_waiting,
            "timestamp": now_iso,
        }

        try:
            feed = []
            if os.path.exists(self.feed_file):
                with open(self.feed_file, "r", encoding="utf-8") as f:
                    feed = json.load(f)
            feed.append(entry)
            if len(feed) > 300:
                feed = feed[-300:]
            with open(self.feed_file, "w", encoding="utf-8") as f:
                json.dump(feed, f, indent=2)
        except Exception as e:
            logger.warning(f"[SwarmBlackboard] Error recording thought: {e}")

        # Broadcast via WebSocket
        sync_broadcast_preview_log(
            project_token=self.project_token,
            content=f"🧠 [{agent_id}] {thought[:180]}",
            event_type="agent_thought",
            payload=entry,
        )
        return entry

    def publish_contract(self, contract_data: Dict[str, Any], agent_id: str = "M_agent_01") -> None:
        """Publish updated API contracts to .agent/contracts/api_contract.json."""
        try:
            with open(self.api_contract_file, "w", encoding="utf-8") as f:
                json.dump(contract_data, f, indent=2)

            routes_count = len(contract_data.get("routes", []))
            models_count = len(contract_data.get("models", []))
            sync_broadcast_preview_log(
                project_token=self.project_token,
                content=f"📜 Published verified API contracts: {routes_count} routes, {models_count} data schemas.",
                event_type="contract_published",
                payload={
                    "agent_id": agent_id,
                    "routes_count": routes_count,
                    "models_count": models_count,
                    "contracts": contract_data,
                },
            )
        except Exception as e:
            logger.error(f"[SwarmBlackboard] Error publishing contract: {e}")

    def get_published_contract(self) -> Dict[str, Any]:
        """Read the published API contract if available."""
        if os.path.exists(self.api_contract_file):
            try:
                with open(self.api_contract_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"[SwarmBlackboard] Error reading contract: {e}")
        return {}


# Blackboard Factory
_blackboards: Dict[str, SwarmBlackboard] = {}


def get_swarm_blackboard(project_token: str, workspace_dir: Optional[str] = None) -> SwarmBlackboard:
    """Retrieve or create the singleton SwarmBlackboard instance for a project."""
    pt = project_token or "default_project"
    if pt not in _blackboards or workspace_dir:
        _blackboards[pt] = SwarmBlackboard(project_token=pt, workspace_dir=workspace_dir)
    return _blackboards[pt]
