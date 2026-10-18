"""Durable SSE event broadcaster with per-channel replay buffer.

Architecture:
  - Supports streaming events by project_token, session_id, or agent_id.
  - Every published event is appended to a bounded deque(maxlen=400) replay buffer.
  - Events carry a monotonic integer `id` so clients can request a replay from a
    known position after reconnect or tab switch.
  - Keeps live connections open with heartbeat pings every 15s.
"""
from __future__ import annotations

import asyncio
import itertools
from collections import defaultdict, deque
from typing import Any, AsyncGenerator

# Monotonic event ID counter across the process lifetime
_event_id_counter = itertools.count(1)


class EventBroadcaster:
    """Singleton in-memory broadcaster for SSE agent events with replay."""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[asyncio.Queue]] = defaultdict(list)
        # Each entry: (event_id: int, event: dict)
        self._replay_buffers: dict[str, deque[tuple[int, dict]]] = defaultdict(
            lambda: deque(maxlen=400)
        )

    def subscribe(self, channel_key: str) -> asyncio.Queue:
        """Create a new subscription queue for the given channel."""
        queue: asyncio.Queue = asyncio.Queue(maxsize=1024)
        self._subscribers[channel_key].append(queue)
        return queue

    def unsubscribe(self, channel_key: str, queue: asyncio.Queue) -> None:
        """Remove a subscription queue on disconnect."""
        queues = self._subscribers.get(channel_key, [])
        if queue in queues:
            queues.remove(queue)
        if not queues:
            self._subscribers.pop(channel_key, None)

    async def publish(self, channel_key: str, event: dict[str, Any]) -> None:
        """Push an event to the replay buffer and all live subscribers."""
        if not channel_key:
            return

        event_id = next(_event_id_counter)
        stamped = {**event, "_id": event_id}

        # Persist in replay buffer
        self._replay_buffers[channel_key].append((event_id, stamped))

        # Fan-out to live subscribers
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

    def publish_sync(self, channel_key: str, event: dict[str, Any]) -> None:
        """Synchronously push an event to replay buffer and live subscribers."""
        if not channel_key:
            return

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


    async def stream(
        self,
        channel_key: str,
        queue: asyncio.Queue,
        last_event_id: int | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Yield events from `last_event_id` onwards, then stream live events."""
        max_id_sent = last_event_id if last_event_id is not None else -1

        # Phase 1: Replay missed events
        if last_event_id is not None:
            buffer = list(self._replay_buffers.get(channel_key, deque()))
            for eid, ev in buffer:
                if eid > last_event_id:
                    max_id_sent = max(max_id_sent, eid)
                    yield ev

        # Phase 2: Live stream with keep-alive heartbeats
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

    def get_buffered_events(self, channel_key: str) -> list[dict[str, Any]]:
        """Return all buffered events for instant initial state hydration."""
        buffer = list(self._replay_buffers.get(channel_key, deque()))
        return [ev for _, ev in buffer]

    def clear_channel(self, channel_key: str) -> None:
        """Clear channel subscribers and buffer."""
        self._subscribers.pop(channel_key, None)
        self._replay_buffers.pop(channel_key, None)


# Module-level singleton
_broadcaster = EventBroadcaster()


def get_event_broadcaster() -> EventBroadcaster:
    """Dependency injector / accessor for singleton broadcaster."""
    return _broadcaster
