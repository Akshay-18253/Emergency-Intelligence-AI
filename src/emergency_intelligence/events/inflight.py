"""
In-Flight Reactive Rerouting & Real-Time Emergency Vehicle Tracking.
====================================================================
Maintains active in-transit state for dispatched emergency apparatus. Dynamically
detects upcoming route collisions with newly declared disaster hazards or
road closures, triggering sub-millisecond in-flight detour replanning.

Adheres strictly to zero external runtime dependencies (Python standard library only).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import math
import time
from typing import Any, Dict, List, Optional, Tuple, Union

from emergency_intelligence.events.mutations import DynamicGraphView
from emergency_intelligence.graph.astar import astar
from emergency_intelligence.graph.dijkstra import RouteResult
from emergency_intelligence.graph.models import Graph


@dataclass
class DispatchedVehicleTracker:
    """Tracks an emergency response vehicle navigating an active route in the field.

    Attributes
    ----------
    unit_id : str
        Vehicle apparatus identifier.
    incident_id : str
        Target emergency incident identifier.
    destination_node_id : str
        Target destination graph node (e.g. incident scene or hospital trauma bay).
    path : List[str]
        Ordered sequence of waypoints from origin to destination.
    current_edge_index : int
        Zero-based index into `path` representing the currently traversed road segment
        (from `path[current_edge_index]` to `path[current_edge_index + 1]`).
    progress_ratio : float
        Fraction in [0.0, 1.0] of current road segment traversed.
    speed_factor : float
        Vehicle velocity multiplier (default 1.0).
    reroute_count : int
        Number of mid-route detour recalculations executed during this mission.
    metadata : Dict[str, Any]
        Arbitrary telemetry attributes (fuel, crew, radio frequency).
    """

    unit_id: str
    incident_id: str
    destination_node_id: str
    path: List[str]
    current_edge_index: int = 0
    progress_ratio: float = 0.0
    speed_factor: float = 1.0
    reroute_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.path or len(self.path) < 1:
            raise ValueError("Tracker path must contain at least one node.")
        if self.destination_node_id != self.path[-1]:
            raise ValueError(
                f"destination_node_id '{self.destination_node_id}' must match path terminus '{self.path[-1]}'."
            )
        if not (0.0 <= self.progress_ratio <= 1.0):
            raise ValueError(f"progress_ratio must be in [0.0, 1.0], got {self.progress_ratio}.")

    @property
    def is_arrived(self) -> bool:
        """Returns True if the vehicle has reached its final destination."""
        return self.current_edge_index >= len(self.path) - 1

    @property
    def current_tail_node(self) -> str:
        """The junction node the vehicle most recently departed."""
        idx = min(self.current_edge_index, len(self.path) - 1)
        return self.path[idx]

    @property
    def current_head_node(self) -> str:
        """The immediate upcoming junction node the vehicle is driving towards."""
        if self.is_arrived:
            return self.path[-1]
        return self.path[self.current_edge_index + 1]

    @property
    def remaining_path(self) -> List[str]:
        """Waypoints remaining from the upcoming junction node to the destination."""
        if self.is_arrived:
            return [self.path[-1]]
        return self.path[self.current_edge_index + 1 :]

    def advance(self, fraction: float) -> None:
        """Simulates vehicle progression forward along the active trajectory."""
        if self.is_arrived:
            return

        self.progress_ratio += fraction
        while self.progress_ratio >= 1.0 and not self.is_arrived:
            self.progress_ratio -= 1.0
            self.current_edge_index += 1

        if self.is_arrived:
            self.progress_ratio = 1.0

    def step_to_next_node(self) -> None:
        """Advances vehicle directly to the upcoming intersection."""
        if not self.is_arrived:
            self.current_edge_index += 1
            self.progress_ratio = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Serializes vehicle tracker state to a dictionary."""
        return {
            "unit_id": self.unit_id,
            "incident_id": self.incident_id,
            "destination_node_id": self.destination_node_id,
            "path": list(self.path),
            "current_edge_index": self.current_edge_index,
            "progress_ratio": round(self.progress_ratio, 3),
            "current_tail_node": self.current_tail_node,
            "current_head_node": self.current_head_node,
            "is_arrived": self.is_arrived,
            "reroute_count": self.reroute_count,
            "speed_factor": self.speed_factor,
            "metadata": dict(self.metadata),
        }


def check_route_obstruction(
    tracker: DispatchedVehicleTracker,
    graph: Union[Graph, DynamicGraphView],
) -> Optional[Tuple[str, str]]:
    """Checks if any remaining edge on the vehicle's route is blocked or impassable.

    Returns
    -------
    Optional[Tuple[str, str]]
        The first blocked directed edge (u, v) encountered ahead of the vehicle,
        or None if the downstream route is completely clear.
    """
    if tracker.is_arrived:
        return None

    # Check edges from current index forward
    for i in range(tracker.current_edge_index, len(tracker.path) - 1):
        u = tracker.path[i]
        v = tracker.path[i + 1]

        if isinstance(graph, DynamicGraphView):
            if graph.is_edge_blocked(u, v):
                return (u, v)
        else:
            if not graph.has_edge(u, v):
                return (u, v)

    return None


def replan_inflight_route(
    tracker: DispatchedVehicleTracker,
    graph: Union[Graph, DynamicGraphView],
) -> Optional[RouteResult]:
    """Dynamically recalculates the optimal trajectory for an in-transit vehicle.

    If the road ahead is obstructed by a new disaster closure or hazard zone:
      - If vehicle is midway through segment (u -> v), it navigates safely to the
        immediate head junction `v`, from which a new optimal path is calculated.
      - If vehicle has not entered the blocked segment (progress == 0.0), replans
        directly from `u`.
      - Updates `tracker.path` seamlessly to preserve past traversed history.

    Parameters
    ----------
    tracker : DispatchedVehicleTracker
        The active vehicle tracker.
    graph : Graph or DynamicGraphView
        The network graph overlay containing active disaster conditions.

    Returns
    -------
    Optional[RouteResult]
        The newly computed RouteResult detour, or None if destination is unreachable.
    """
    if tracker.is_arrived:
        return None

    obstruction = check_route_obstruction(tracker, graph)
    if obstruction is None:
        # Route is clear, no replan required
        return None

    # Determine pivot node where replan begins
    curr_u = tracker.current_tail_node
    curr_v = tracker.current_head_node

    if obstruction == (curr_u, curr_v) and tracker.progress_ratio == 0.0:
        pivot_node = curr_u
        traversed_prefix = tracker.path[: tracker.current_edge_index]
    else:
        pivot_node = curr_v
        traversed_prefix = tracker.path[: tracker.current_edge_index + 1]

    if pivot_node == tracker.destination_node_id:
        return None

    # Compute optimal detour from pivot node to destination
    route = astar(
        graph,  # type: ignore[arg-type]
        source=pivot_node,
        destination=tracker.destination_node_id,
    )

    if not route.reachable or not route.path:
        # Destination currently cut off by disasters
        return None

    # Stitch new route onto traversed prefix
    new_path = traversed_prefix + route.path
    tracker.path = new_path
    tracker.reroute_count += 1

    return route
