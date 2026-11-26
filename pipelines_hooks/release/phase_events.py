"""Version-1 progress events and bounded subscribers for ordered release phases.

Every event carries the run ID, a strictly increasing sequence number, the
phase, the project and the five disjoint progress sets (completed, active,
remaining, failed, cancelled). A subscriber buffers at most
``SUBSCRIBER_CAPACITY`` events. One more event disconnects it: the buffer
ends with an explicit sequence-gap record, later events are not queued for it,
and it resumes only from a fresh authoritative snapshot, never by guessing
what it missed.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable
from typing import Any

from pipelines_hooks.core.errors import CannotRun

EVENT_VERSION = 1
SUBSCRIBER_CAPACITY = 256
SET_NAMES = ("completed", "active", "remaining", "failed", "cancelled")
_TRANSITIONS = {"active": "remaining", "completed": "active", "failed": "active", "cancelled": "active"}


class RunSets:
    """The five disjoint progress sets over one run inventory."""

    def __init__(self, inventory: Iterable[str]) -> None:
        self.inventory = frozenset(inventory)
        self._held: dict[str, set[str]] = {name: set() for name in SET_NAMES if name != "remaining"}

    def mark_completed(self, project: str) -> None:
        """Record a project completed in a previous invocation (a resumed run)."""
        self._held["completed"].add(project)

    def move(self, project: str, to: str) -> None:
        """Move one project along the only legal transitions."""
        source = _TRANSITIONS.get(to)
        if source is None or project not in self.inventory:
            raise CannotRun(f"unknown transition of {project!r} to {to!r}")
        if source != "remaining" and project not in self._held[source]:
            raise CannotRun(f"{project!r} cannot become {to} unless it is {source}")
        if source == "remaining" and any(project in held for held in self._held.values()):
            raise CannotRun(f"{project!r} already started")
        if source != "remaining":
            self._held[source].discard(project)
        self._held[to].add(project)

    def snapshot(self) -> dict[str, list[str]]:
        """The sets as sorted lists; they are disjoint and cover the inventory."""
        held = {name: sorted(members) for name, members in self._held.items()}
        taken = set().union(*self._held.values())
        held["remaining"] = sorted(self.inventory - taken)
        return {name: held[name] for name in SET_NAMES}

    def check(self) -> None:
        """Refuse unless the five sets are disjoint and cover the run inventory."""
        listed = [project for members in self.snapshot().values() for project in members]
        if len(listed) != len(set(listed)) or set(listed) != self.inventory:
            raise CannotRun("progress sets are not a disjoint cover of the run inventory")


class Subscriber:
    """One bounded event buffer; overflow disconnects it with a gap record."""

    def __init__(self, hub: ProgressHub, capacity: int = SUBSCRIBER_CAPACITY) -> None:
        if capacity < 1 or capacity > SUBSCRIBER_CAPACITY:
            raise CannotRun(f"a subscriber buffer holds 1 to {SUBSCRIBER_CAPACITY} events")
        self._hub = hub
        self._capacity = capacity
        self._buffer: deque[dict[str, Any]] = deque()
        self.connected = True
        self._last_queued = hub.sequence

    def offer(self, event: dict[str, Any]) -> None:
        """Queue an event, or disconnect with an explicit gap when the buffer is full."""
        if not self.connected:
            return
        if len(self._buffer) >= self._capacity:
            self.connected = False
            self._buffer.append(
                {
                    "version": EVENT_VERSION,
                    "kind": "gap",
                    "run_id": event["run_id"],
                    "last_sequence": self._last_queued,
                    "next_sequence": event["sequence"],
                    "resume": "request a fresh snapshot",
                }
            )
            return
        self._last_queued = event["sequence"]
        self._buffer.append(event)

    def drain(self) -> list[dict[str, Any]]:
        """Take every queued event (a gap record is always last)."""
        taken = list(self._buffer)
        self._buffer.clear()
        return taken

    def resume(self) -> dict[str, Any]:
        """Reconnect from a fresh authoritative snapshot; queued events are discarded."""
        self._buffer.clear()
        self.connected = True
        snapshot = self._hub.snapshot()
        self._last_queued = snapshot["sequence"]
        return snapshot


class ProgressHub:
    """Sequence and fan events out to subscribers; owns the authoritative snapshot."""

    def __init__(self, run_id: str, sets: RunSets) -> None:
        self.run_id = run_id
        self.sets = sets
        self.sequence = 0
        self._subscribers: list[Subscriber] = []

    def subscribe(self, capacity: int = SUBSCRIBER_CAPACITY) -> Subscriber:
        """Attach one subscriber with a bounded buffer."""
        subscriber = Subscriber(self, capacity)
        self._subscribers.append(subscriber)
        return subscriber

    def snapshot(self) -> dict[str, Any]:
        """The authoritative state at this instant (not a replay of events)."""
        return {
            "version": EVENT_VERSION,
            "kind": "snapshot",
            "run_id": self.run_id,
            "sequence": self.sequence,
            "sets": self.sets.snapshot(),
        }

    def emit(self, event: str, *, phase: str = "", project: str = "", **extra: Any) -> dict[str, Any]:
        """Publish one event with the current sets."""
        self.sequence += 1
        record = {
            "version": EVENT_VERSION,
            "kind": "event",
            "run_id": self.run_id,
            "sequence": self.sequence,
            "event": event,
            "phase": phase,
            "project": project,
            "sets": self.sets.snapshot(),
            **extra,
        }
        for subscriber in self._subscribers:
            subscriber.offer(record)
        return record

    def transition(self, project: str, to: str, *, phase: str) -> None:
        """Emit before and after one project state transition."""
        self.emit("transition-begin", phase=phase, project=project, to=to)
        self.sets.move(project, to)
        self.emit("transition-end", phase=phase, project=project, to=to)
