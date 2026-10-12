"""
Discrete-Event Simulation Timeline & Virtual Clock.
===================================================
Provides deterministic event scheduling and virtual clock management for
emergency response simulations. Events are ordered strictly by timestamp,
priority, and insertion sequence using a min-heap priority queue.

Strictly zero external runtime dependencies (Python standard library only).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import heapq
import itertools
from typing import Any, Callable, Dict, List, Optional, Tuple


class SimEventType(str, Enum):
    """Enumeration of recognized discrete simulation event types."""

    # Incident lifecycle
    INCIDENT_DECLARED = "incident_declared"
    INCIDENT_ESCALATED = "incident_escalated"
    INCIDENT_RESOLVED = "incident_resolved"

    # Vehicle / Apparatus lifecycle
    UNIT_DISPATCHED = "unit_dispatched"
    UNIT_EN_ROUTE = "unit_en_route"
    UNIT_REROUTED = "unit_rerouted"
    UNIT_ARRIVED = "unit_arrived"
    UNIT_CLEARED = "unit_cleared"

    # Environmental / Hazard lifecycle
    HAZARD_SPAWNED = "hazard_spawned"
    HAZARD_EXPANDED = "hazard_expanded"
    HAZARD_RESOLVED = "hazard_resolved"

    # Network topology mutations
    ROAD_CLOSED = "road_closed"
    ROAD_REOPENED = "road_reopened"
    SPEED_DEGRADED = "speed_degraded"

    # Periodic diagnostics & telemetry
    TELEMETRY_SAMPLE = "telemetry_sample"
    CUSTOM = "custom"


@dataclass
class SimulationClock:
    """Deterministic virtual simulation clock.

    Tracks simulated time progression in seconds without sleeping or relying
    on system wall-clock time.
    """

    current_time: float = 0.0

    def advance_to(self, target_time: float) -> float:
        """Advances clock forward to target_time.

        Parameters
        ----------
        target_time : float
            New simulation time in seconds.

        Returns
        -------
        float
            New current simulation time.

        Raises
        ------
        ValueError
            If target_time is less than current_time (time cannot flow backwards).
        """
        if target_time < self.current_time:
            raise ValueError(
                f"Clock cannot retreat backwards from {self.current_time:.3f}s to {target_time:.3f}s."
            )
        self.current_time = float(target_time)
        return self.current_time

    def tick(self, delta_seconds: float) -> float:
        """Advances clock forward by delta_seconds.

        Parameters
        ----------
        delta_seconds : float
            Elapsed duration in seconds.

        Returns
        -------
        float
            New current simulation time.

        Raises
        ------
        ValueError
            If delta_seconds is negative.
        """
        if delta_seconds < 0.0:
            raise ValueError(f"Clock tick delta cannot be negative ({delta_seconds}).")
        self.current_time += float(delta_seconds)
        return self.current_time

    def reset(self, start_time: float = 0.0) -> None:
        """Resets the simulation clock to the specified start timestamp."""
        if start_time < 0.0:
            raise ValueError("Start time cannot be negative.")
        self.current_time = float(start_time)


@dataclass(order=True)
class SimEvent:
    """Discrete simulation event scheduled on the timeline.

    Ordered primarily by timestamp, secondarily by priority (lower number = higher priority),
    and tertiarily by sequential insertion order for deterministic tie-breaking.
    """

    timestamp: float
    priority: int = 10
    sequence_id: int = 0
    event_id: str = field(default="", compare=False)
    event_type: SimEventType = field(default=SimEventType.CUSTOM, compare=False)
    payload: Dict[str, Any] = field(default_factory=dict, compare=False)
    description: str = field(default="", compare=False)

    def to_dict(self) -> Dict[str, Any]:
        """Serializes event to a dictionary for logging and telemetry."""
        return {
            "timestamp": round(self.timestamp, 3),
            "priority": self.priority,
            "sequence_id": self.sequence_id,
            "event_id": self.event_id,
            "event_type": self.event_type.value if isinstance(self.event_type, Enum) else str(self.event_type),
            "description": self.description,
            "payload": dict(self.payload),
        }


class SimulationTimeline:
    """Min-heap priority queue of discrete simulation events.

    Guarantees deterministic, chronological event dispatch with secondary
    priority resolution and FIFO ordering on ties.
    """

    def __init__(self) -> None:
        self._heap: List[SimEvent] = []
        self._seq_counter = itertools.count()
        self._cancelled_ids: set[str] = set()

    def schedule(self, event: SimEvent) -> SimEvent:
        """Schedules a SimEvent onto the timeline."""
        if event.timestamp < 0.0:
            raise ValueError(f"Event timestamp cannot be negative ({event.timestamp}).")
        if not event.sequence_id:
            event.sequence_id = next(self._seq_counter)
        if not event.event_id:
            event.event_id = f"evt_{event.sequence_id:06d}"

        heapq.heappush(self._heap, event)
        return event

    def schedule_event(
        self,
        timestamp: float,
        event_type: SimEventType,
        payload: Optional[Dict[str, Any]] = None,
        priority: int = 10,
        description: str = "",
        event_id: Optional[str] = None,
    ) -> SimEvent:
        """Constructs and schedules a SimEvent onto the timeline."""
        seq = next(self._seq_counter)
        eid = event_id or f"evt_{seq:06d}"
        event = SimEvent(
            timestamp=float(timestamp),
            priority=int(priority),
            sequence_id=seq,
            event_id=eid,
            event_type=event_type,
            payload=dict(payload or {}),
            description=description,
        )
        return self.schedule(event)

    def peek(self) -> Optional[SimEvent]:
        """Returns the next non-cancelled event without removing it, or None if empty."""
        while self._heap:
            top = self._heap[0]
            if top.event_id in self._cancelled_ids:
                heapq.heappop(self._heap)
                self._cancelled_ids.discard(top.event_id)
            else:
                return top
        return None

    def pop_next(self) -> Optional[SimEvent]:
        """Pops and returns the next non-cancelled event in chronological order."""
        while self._heap:
            event = heapq.heappop(self._heap)
            if event.event_id in self._cancelled_ids:
                self._cancelled_ids.discard(event.event_id)
                continue
            return event
        return None

    def pop_due(self, current_time: float) -> List[SimEvent]:
        """Pops and returns all non-cancelled events scheduled at or before current_time."""
        due_events: List[SimEvent] = []
        while self._heap:
            top = self.peek()
            if top is None or top.timestamp > current_time:
                break
            popped = self.pop_next()
            if popped is not None:
                due_events.append(popped)
        return due_events

    def cancel(self, event_id: str) -> bool:
        """Marks an event as cancelled by its ID."""
        if not event_id:
            return False
        self._cancelled_ids.add(event_id)
        return True

    def is_empty(self) -> bool:
        """Returns True if the timeline contains no active events."""
        return self.peek() is None

    def __len__(self) -> int:
        """Returns the number of active (non-cancelled) events currently on the timeline."""
        return sum(1 for e in self._heap if e.event_id not in self._cancelled_ids)

    def clear(self) -> None:
        """Clears all events from the timeline."""
        self._heap.clear()
        self._cancelled_ids.clear()
