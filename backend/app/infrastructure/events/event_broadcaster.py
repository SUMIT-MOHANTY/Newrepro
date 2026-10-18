"""Durable SSE event broadcaster with strict per-project and per-agent channel isolation."""

from __future__ import annotations

import asyncio
import itertools
import json
import os
from collections import defaultdict, deque
from typing import Any, AsyncGenerator, Optional

_event_id_counter = itertools.count(1)


class EventBroadcaster:
    """Singleton in-memory broadcaster for SSE agent events with replay & disk persistence."""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[asyncio.Queue]] = defaultdict(list)
        self._replay_buffers: dict[str, deque[tuple[int, dict]]] = defaultdict(
            lambda: deque(maxlen=600)
        )
        self._seen_uids: dict[str, deque[str]] = defaultdict(
            lambda: deque(maxlen=1000)
        )

    @staticmethod
    def project_channel(project_token: str) -> str:
        clean_pt = (project_token or "default_project").strip()
        return f"project:{clean_pt}"

    @staticmethod
    def agent_channel(project_token: str, agent_id: str) -> str:
        clean_pt = (project_token or "default_project").strip()
        base_aid = (agent_id or "default_agent").split("#")[0].strip().lower()
        return f"agent:{clean_pt}:{base_aid}"

    def subscribe(self, channel_key: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=1024)
        self._subscribers[channel_key].append(queue)
        return queue

    def unsubscribe(self, channel_key: str, queue: asyncio.Queue) -> None:
        queues = self._subscribers.get(channel_key, [])
        if queue in queues:
            queues.remove(queue)
        if not queues:
            self._subscribers.pop(channel_key, None)

    def _enqueue(self, channel_key: str, event: dict[str, Any]) -> Optional[dict[str, Any]]:
        if not channel_key:
            return None

        # Deduplicate if event carries a unique uid
        uid = event.get("event_uid")
        if uid:
            if uid in self._seen_uids[channel_key]:
                return None
            self._seen_uids[channel_key].append(uid)

        event_id = next(_event_id_counter)
        stamped = {**event, "_id": event_id}
        self._replay_buffers[channel_key].append((event_id, stamped))

        for queue in list(self._subscribers.get(channel_key, [])):
            try:
                queue.put_nowait(stamped)
            except asyncio.QueueFull:
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                try:
                    queue.put_nowait(stamped)
                except asyncio.QueueFull:
                    pass
        return stamped

    async def publish(self, channel_key: str, event: dict[str, Any]) -> None:
        """Publish to a specific channel (and auto-route to agent sub-channel if agent_id is present)."""
        self.publish_sync(channel_key, event)

    def publish_sync(self, channel_key: str, event: dict[str, Any]) -> None:
        """Synchronously push an event to the project channel AND dedicated agent channel."""
        if not channel_key:
            return

        # If caller passed raw project_token, normalize to project channel + agent channel
        if not channel_key.startswith(("project:", "agent:", "session:")):
            project_token = channel_key
            proj_chan = self.project_channel(project_token)
            self._enqueue(proj_chan, event)
            # Also keep raw key for backward compatibility
            self._enqueue(project_token, event)

            agent_id = event.get("agent_id") or (event.get("payload") or {}).get("agent_id")
            if agent_id:
                agt_chan = self.agent_channel(project_token, str(agent_id))
                self._enqueue(agt_chan, event)
        else:
            self._enqueue(channel_key, event)

    async def stream(
        self,
        channel_key: str,
        queue: asyncio.Queue,
        last_event_id: int | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        max_id_sent = last_event_id if last_event_id is not None else -1

        # Phase 1: Replay buffered events
        buffer = list(self._replay_buffers.get(channel_key, deque()))
        for eid, ev in buffer:
            if last_event_id is None or eid > last_event_id:
                max_id_sent = max(max_id_sent, eid)
                yield ev

        # Phase 2: Live stream with 15s keep-alive heartbeats
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)
                    eid = event.get("_id")
                    if eid is not None:
                        if eid <= max_id_sent:
                            continue
                        max_id_sent = max(max_id_sent, eid)
                    yield event
                except asyncio.TimeoutError:
                    yield {"type": "ping", "channel": channel_key, "_id": None}
        except asyncio.CancelledError:
            return
        finally:
            self.unsubscribe(channel_key, queue)

    def get_buffered_events(
        self,
        project_token: str,
        agent_id: Optional[str] = None,
        workspace_dir: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Return buffered events strictly scoped to (project_token, agent_id)."""
        # If project_token is already a formatted channel string and agent_id is None
        if (project_token.startswith("agent:") or project_token.startswith("project:") or project_token.startswith("session:")) and not agent_id:
            buffer = list(self._replay_buffers.get(project_token, deque()))
            return [ev for _, ev in buffer]

        if agent_id:
            chan = self.agent_channel(project_token, agent_id)
            buffer = list(self._replay_buffers.get(chan, deque()))
            if buffer:
                return [ev for _, ev in buffer]

            # Fallback: read from disk ledger `.agent/events_{clean_aid}.jsonl` if memory is empty
            if workspace_dir:
                clean_aid = "".join(c for c in agent_id.split("#")[0] if c.isalnum() or c == "_")
                ledger_path = os.path.join(workspace_dir, ".agent", f"events_{clean_aid}.jsonl")
                if os.path.isfile(ledger_path):
                    disk_events = []
                    try:
                        with open(ledger_path, "r", encoding="utf-8", errors="replace") as f:
                            for line in f:
                                if line.strip():
                                    ev = json.loads(line)
                                    disk_events.append(ev)
                                    self._enqueue(chan, ev)
                        return disk_events[-400:]
                    except Exception:
                        pass
            return []

        proj_chan = self.project_channel(project_token)
        buffer = list(self._replay_buffers.get(proj_chan, deque()))
        if not buffer:
            buffer = list(self._replay_buffers.get(project_token, deque()))
        return [ev for _, ev in buffer]

    def clear_channel(self, channel_key: str) -> None:
        self._subscribers.pop(channel_key, None)
        self._replay_buffers.pop(channel_key, None)
        self._seen_uids.pop(channel_key, None)


_broadcaster = EventBroadcaster()


def get_event_broadcaster() -> EventBroadcaster:
    return _broadcaster
