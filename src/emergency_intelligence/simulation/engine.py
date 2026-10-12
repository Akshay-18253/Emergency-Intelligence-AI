"""
Discrete-Event Disaster Simulation Engine.
==========================================
Coordinates simulation time, vehicle kinematics, dynamic road conditions,
and event scheduling. Supports sub-millisecond multi-hour disaster simulations
with zero external runtime dependencies.

Strictly adheres to Python standard library only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from emergency_intelligence.allocation.models import UnitStatus
from emergency_intelligence.events.hazards import HazardPolygon, find_edges_intersecting_hazard
from emergency_intelligence.events.incidents import ApparatusType, Incident, UrgencyLevel
from emergency_intelligence.events.inflight import (
    DispatchedVehicleTracker,
    check_route_obstruction,
    replan_inflight_route,
)
from emergency_intelligence.events.mutations import DynamicGraphView, EdgeMutation, MutationType
from emergency_intelligence.graph.models import Edge, Graph
from emergency_intelligence.simulation.timeline import (
    SimEvent,
    SimEventType,
    SimulationClock,
    SimulationTimeline,
)


@dataclass
class VehicleSimState:
    """Represents the real-time kinematic and operational state of an emergency vehicle.

    Attributes
    ----------
    unit_id : str
        Unique apparatus identifier (e.g. "MEDIC-1", "ENGINE-4").
    apparatus_type : ApparatusType
        Type of emergency apparatus.
    station_id : str
        Base station identifier.
    status : UnitStatus
        Current operational status.
    tracker : Optional[DispatchedVehicleTracker]
        In-flight waypoint and segment progress tracker.
    assigned_incident_id : Optional[str]
        Target emergency incident currently assigned to this unit.
    dispatch_time : Optional[float]
        Simulated timestamp (seconds) when dispatch order was issued.
    en_route_time : Optional[float]
        Simulated timestamp (seconds) when wheels began rolling.
    arrival_time : Optional[float]
        Simulated timestamp (seconds) when unit arrived on scene.
    clear_time : Optional[float]
        Simulated timestamp (seconds) when unit cleared scene.
    total_travel_time : float
        Cumulative travel duration in seconds.
    total_distance_meters : float
        Cumulative distance traveled in meters.
    reroute_count : int
        Number of mid-flight detours taken due to dynamic hazards.
    metadata : Dict[str, Any]
        Arbitrary telemetry attributes.
    """

    unit_id: str
    apparatus_type: ApparatusType
    station_id: str
    status: UnitStatus = UnitStatus.AVAILABLE
    tracker: Optional[DispatchedVehicleTracker] = None
    assigned_incident_id: Optional[str] = None
    dispatch_time: Optional[float] = None
    en_route_time: Optional[float] = None
    arrival_time: Optional[float] = None
    clear_time: Optional[float] = None
    total_travel_time: float = 0.0
    total_distance_meters: float = 0.0
    reroute_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_available(self) -> bool:
        """Returns True if the vehicle is in quarters and available for dispatch."""
        return self.status == UnitStatus.AVAILABLE

    @property
    def is_en_route(self) -> bool:
        """Returns True if the vehicle is actively driving towards an incident."""
        return self.status == UnitStatus.EN_ROUTE

    @property
    def is_on_scene(self) -> bool:
        """Returns True if the vehicle has arrived and is actively operating on scene."""
        return self.status == UnitStatus.ON_SCENE

    def current_position_coords(self, graph: Graph) -> Optional[Tuple[float, float]]:
        """Calculates interpolated 2D spatial coordinates along the current edge.

        Returns (x, y) coordinates, or None if coordinates cannot be determined.
        """
        if self.tracker is None or not self.tracker.path:
            return None

        if self.tracker.is_arrived:
            last_node = graph.get_node(self.tracker.path[-1])
            return last_node.coordinates if last_node else None

        u_id = self.tracker.current_tail_node
        v_id = self.tracker.current_head_node
        node_u = graph.get_node(u_id)
        node_v = graph.get_node(v_id)

        if node_u and node_v and node_u.coordinates and node_v.coordinates:
            xu, yu = node_u.coordinates
            xv, yv = node_v.coordinates
            ratio = self.tracker.progress_ratio
            interp_x = xu + ratio * (xv - xu)
            interp_y = yu + ratio * (yv - yu)
            return (round(interp_x, 6), round(interp_y, 6))

        if node_u and node_u.coordinates:
            return node_u.coordinates
        if node_v and node_v.coordinates:
            return node_v.coordinates
        return None

    @classmethod
    def _find_edge(
        cls,
        u: str,
        v: str,
        graph: Graph,
        dynamic_view: DynamicGraphView,
    ) -> Optional[Edge]:
        """Resolves edge with dynamic cost multiplier applied."""
        if not graph.has_node(u):
            return None
        for edge in graph.get_neighbors(u):
            if edge.destination_id == v:
                mut = dynamic_view.get_mutation(u, v)
                if mut:
                    eff_cost = mut.effective_cost(edge.cost)
                    return Edge(edge.source_id, edge.destination_id, cost=eff_cost, attributes=dict(edge.attributes))
                return edge
        return None

    def step_movement(
        self,
        delta_seconds: float,
        graph: Graph,
        dynamic_view: DynamicGraphView,
    ) -> bool:
        """Advances vehicle along its assigned path by elapsed simulated time.

        Parameters
        ----------
        delta_seconds : float
            Elapsed simulation duration in seconds.
        graph : Graph
            Base network graph.
        dynamic_view : DynamicGraphView
            Active dynamic graph overlay.

        Returns
        -------
        bool
            True if the vehicle reached its destination during this step.
        """
        if not self.is_en_route or self.tracker is None or self.tracker.is_arrived:
            return False

        if delta_seconds <= 0.0:
            return False

        speed_factor = max(self.tracker.speed_factor, 0.01)
        budget = delta_seconds * speed_factor

        while budget > 0.0 and not self.tracker.is_arrived:
            u = self.tracker.current_tail_node
            v = self.tracker.current_head_node

            if dynamic_view.is_edge_blocked(u, v):
                # Road segment is completely severed; vehicle cannot proceed forward
                break

            edge = self._find_edge(u, v, graph, dynamic_view)
            edge_time, edge_dist = self._resolve_edge_metrics(edge)

            needed_time = edge_time * (1.0 - self.tracker.progress_ratio)

            if budget >= needed_time:
                # Traversed remaining segment length completely
                budget -= needed_time
                time_spent = needed_time / speed_factor
                self.total_travel_time += time_spent
                dist_spent = edge_dist * (1.0 - self.tracker.progress_ratio)
                self.total_distance_meters += dist_spent
                self.tracker.step_to_next_node()
            else:
                # Traversed partial segment length
                fraction = budget / edge_time
                self.tracker.advance(fraction)
                time_spent = budget / speed_factor
                self.total_travel_time += time_spent
                dist_spent = edge_dist * fraction
                self.total_distance_meters += dist_spent
                budget = 0.0

        if self.tracker.is_arrived:
            return True
        return False

    @staticmethod
    def _resolve_edge_metrics(edge: Optional[Edge]) -> Tuple[float, float]:
        """Resolves (traversal_time_seconds, length_meters) for an edge."""
        if edge is None:
            return (1.0, 10.0)

        # 1. Travel time
        edge_time = 1.0
        if "travel_time" in edge.attributes and edge.attributes["travel_time"] > 0:
            edge_time = float(edge.attributes["travel_time"])
        elif edge.cost > 0 and edge.cost != math.inf:
            edge_time = float(edge.cost)

        # 2. Distance
        edge_dist = 0.0
        if "distance" in edge.attributes and edge.attributes["distance"] > 0:
            edge_dist = float(edge.attributes["distance"])
        elif "length" in edge.attributes and edge.attributes["length"] > 0:
            edge_dist = float(edge.attributes["length"])
        else:
            edge_dist = edge_time * 13.88  # default ~50 km/h approx

        return (max(edge_time, 0.001), max(edge_dist, 0.0))

    def to_dict(self) -> Dict[str, Any]:
        """Serializes vehicle state to a dictionary."""
        return {
            "unit_id": self.unit_id,
            "apparatus_type": (
                self.apparatus_type.value
                if isinstance(self.apparatus_type, ApparatusType)
                else str(self.apparatus_type)
            ),
            "station_id": self.station_id,
            "status": self.status.value if isinstance(self.status, UnitStatus) else str(self.status),
            "assigned_incident_id": self.assigned_incident_id,
            "dispatch_time": self.dispatch_time,
            "en_route_time": self.en_route_time,
            "arrival_time": self.arrival_time,
            "clear_time": self.clear_time,
            "total_travel_time": round(self.total_travel_time, 2),
            "total_distance_meters": round(self.total_distance_meters, 2),
            "reroute_count": self.reroute_count,
            "tracker": self.tracker.to_dict() if self.tracker else None,
        }


class DisasterSimEngine:
    """Discrete-Event Disaster Simulation Engine.

    Manages virtual time progression, vehicle navigation, incident response,
    dynamic environmental hazards, and metric collection.
    """

    def __init__(
        self,
        graph: Graph,
        dynamic_view: Optional[DynamicGraphView] = None,
        clock: Optional[SimulationClock] = None,
        timeline: Optional[SimulationTimeline] = None,
        auto_reroute: bool = True,
    ) -> None:
        self.graph = graph
        self.dynamic_view = dynamic_view or DynamicGraphView(graph)
        self.clock = clock or SimulationClock()
        self.timeline = timeline or SimulationTimeline()
        self.auto_reroute = auto_reroute

        self.vehicles: Dict[str, VehicleSimState] = {}
        self.incidents: Dict[str, Incident] = {}
        self.active_hazards: Dict[str, HazardPolygon] = {}

        self._handlers: Dict[SimEventType, List[Callable[[SimEvent, DisasterSimEngine], None]]] = {}
        self.event_history: List[SimEvent] = []
        self.telemetry_log: List[Dict[str, Any]] = []

    def register_handler(
        self,
        event_type: SimEventType,
        handler: Callable[[SimEvent, DisasterSimEngine], None],
    ) -> None:
        """Registers a callback handler for a specific event type."""
        self._handlers.setdefault(event_type, []).append(handler)

    def add_vehicle(self, vehicle: VehicleSimState) -> None:
        """Registers an emergency vehicle into the simulation fleet."""
        self.vehicles[vehicle.unit_id] = vehicle

    def register_incident(self, incident: Incident) -> None:
        """Stores an incident definition in the incident registry."""
        self.incidents[incident.incident_id] = incident

    def schedule_incident(
        self,
        incident: Incident,
        report_time: float,
        priority: int = 5,
    ) -> SimEvent:
        """Schedules an incident report onto the simulation timeline."""
        self.register_incident(incident)
        loc = incident.node_id or f"{incident.coordinates[0]:.4f},{incident.coordinates[1]:.4f}"
        return self.timeline.schedule_event(
            timestamp=report_time,
            event_type=SimEventType.INCIDENT_DECLARED,
            payload={
                "incident_id": incident.incident_id,
                "urgency_level": (
                    incident.urgency.value
                    if hasattr(incident.urgency, "value")
                    else str(incident.urgency)
                ),
                "location_node_id": incident.node_id,
                "coordinates": incident.coordinates,
            },
            priority=priority,
            description=f"Incident {incident.incident_id} reported at {loc}",
        )

    def dispatch_vehicle(
        self,
        unit_id: str,
        incident_id: str,
        path: List[str],
        dispatch_time: Optional[float] = None,
        speed_factor: float = 1.0,
    ) -> bool:
        """Dispatches an apparatus along an assigned route towards an incident."""
        vehicle = self.vehicles.get(unit_id)
        if not vehicle:
            raise KeyError(f"Vehicle '{unit_id}' not found in simulation fleet.")

        t = self.clock.current_time if dispatch_time is None else dispatch_time

        vehicle.assigned_incident_id = incident_id
        vehicle.dispatch_time = t

        vehicle.tracker = DispatchedVehicleTracker(
            unit_id=unit_id,
            incident_id=incident_id,
            destination_node_id=path[-1],
            path=list(path),
            speed_factor=speed_factor,
        )

        if t > self.clock.current_time:
            vehicle.status = UnitStatus.DISPATCHED
        else:
            vehicle.status = UnitStatus.EN_ROUTE
            vehicle.en_route_time = t

        self.timeline.schedule_event(
            timestamp=t,
            event_type=SimEventType.UNIT_DISPATCHED,
            payload={
                "unit_id": unit_id,
                "incident_id": incident_id,
                "origin_node_id": path[0],
                "destination_node_id": path[-1],
                "path_length": len(path),
            },
            priority=3,
            description=f"Unit {unit_id} dispatched to incident {incident_id}",
        )
        return True

    def spawn_hazard(
        self,
        hazard_id: str,
        polygon: HazardPolygon,
        timestamp: Optional[float] = None,
        priority: int = 2,
    ) -> SimEvent:
        """Schedules the emergence of a dynamic spatial hazard polygon."""
        t = self.clock.current_time if timestamp is None else timestamp
        return self.timeline.schedule_event(
            timestamp=t,
            event_type=SimEventType.HAZARD_SPAWNED,
            payload={"hazard_id": hazard_id, "polygon": polygon},
            priority=priority,
            description=f"Hazard zone {hazard_id} declared",
        )

    def sever_road(
        self,
        source_id: str,
        destination_id: str,
        timestamp: Optional[float] = None,
        reason: str = "Disaster road closure",
        priority: int = 1,
    ) -> SimEvent:
        """Schedules a road closure mutation on the network graph."""
        t = self.clock.current_time if timestamp is None else timestamp
        return self.timeline.schedule_event(
            timestamp=t,
            event_type=SimEventType.ROAD_CLOSED,
            payload={"source_id": source_id, "destination_id": destination_id, "reason": reason},
            priority=priority,
            description=f"Road {source_id} -> {destination_id} closed: {reason}",
        )

    def restore_road(
        self,
        source_id: str,
        destination_id: str,
        timestamp: Optional[float] = None,
        priority: int = 1,
    ) -> SimEvent:
        """Schedules reopening of a previously severed road segment."""
        t = self.clock.current_time if timestamp is None else timestamp
        return self.timeline.schedule_event(
            timestamp=t,
            event_type=SimEventType.ROAD_REOPENED,
            payload={"source_id": source_id, "destination_id": destination_id},
            priority=priority,
            description=f"Road {source_id} -> {destination_id} reopened",
        )

    def step(self, step_size: float = 1.0) -> List[SimEvent]:
        """Executes a single discrete simulation step.

        1. Pops and processes all events scheduled at or before target time.
        2. Advances clock to target time.
        3. Updates vehicle movement along edges.
        4. Detects obstructions and triggers reactive rerouting if auto_reroute is active.
        5. Emits arrival events for reaching destinations.
        """
        if step_size <= 0.0:
            raise ValueError(f"step_size must be positive, got {step_size}.")

        target_time = self.clock.current_time + step_size
        due_events = self.timeline.pop_due(target_time)

        # 1. Process due events
        for event in due_events:
            if event.timestamp > self.clock.current_time:
                self.clock.advance_to(event.timestamp)
            self._process_event(event)
            self.event_history.append(event)

        # 2. Advance clock to target time
        self.clock.advance_to(target_time)

        # 3. Check for obstructions & replan BEFORE or DURING movement
        if self.auto_reroute:
            self._check_and_reroute_vehicles()

        # 4. Advance physical movement of vehicles
        for vehicle in self.vehicles.values():
            if vehicle.is_en_route and vehicle.tracker:
                arrived = vehicle.step_movement(step_size, self.graph, self.dynamic_view)
                if arrived:
                    vehicle.status = UnitStatus.ON_SCENE
                    vehicle.arrival_time = self.clock.current_time
                    arrival_event = self.timeline.schedule_event(
                        timestamp=self.clock.current_time,
                        event_type=SimEventType.UNIT_ARRIVED,
                        payload={
                            "unit_id": vehicle.unit_id,
                            "incident_id": vehicle.assigned_incident_id,
                            "destination_node_id": vehicle.tracker.destination_node_id,
                            "total_travel_time": vehicle.total_travel_time,
                            "total_distance_meters": vehicle.total_distance_meters,
                            "reroute_count": vehicle.reroute_count,
                        },
                        priority=4,
                        description=f"Unit {vehicle.unit_id} arrived on scene at {vehicle.tracker.destination_node_id}",
                    )
                    self.event_history.append(arrival_event)
                    self._process_event(arrival_event)

        return due_events

    def _process_event(self, event: SimEvent) -> None:
        """Executes internal state transitions and user callbacks for an event."""
        # Built-in state mutations
        if event.event_type == SimEventType.ROAD_CLOSED:
            src = event.payload["source_id"]
            dst = event.payload["destination_id"]
            reason = event.payload.get("reason", "Road closure")
            self.dynamic_view.apply_closure(src, dst, reason=reason)

        elif event.event_type == SimEventType.ROAD_REOPENED:
            src = event.payload["source_id"]
            dst = event.payload["destination_id"]
            self.dynamic_view.remove_mutation(src, dst)

        elif event.event_type == SimEventType.HAZARD_SPAWNED:
            hid = event.payload["hazard_id"]
            poly = event.payload["polygon"]
            self.active_hazards[hid] = poly
            intersecting_edges = find_edges_intersecting_hazard(self.graph, poly)
            for edge in intersecting_edges:
                self.dynamic_view.apply_closure(edge.source_id, edge.destination_id, reason=f"Hazard zone {hid}")

        elif event.event_type == SimEventType.UNIT_DISPATCHED:
            uid = event.payload.get("unit_id")
            if uid and uid in self.vehicles:
                self.vehicles[uid].status = UnitStatus.EN_ROUTE
                self.vehicles[uid].en_route_time = event.timestamp

        # Execute registered user callbacks
        for handler in self._handlers.get(event.event_type, []):
            handler(event, self)

    def _check_and_reroute_vehicles(self) -> None:
        """Checks for route obstructions and replans detours for active vehicles."""
        for vehicle in self.vehicles.values():
            if vehicle.is_en_route and vehicle.tracker and not vehicle.tracker.is_arrived:
                obstruction = check_route_obstruction(vehicle.tracker, self.dynamic_view)
                if obstruction is not None:
                    replan_result = replan_inflight_route(vehicle.tracker, self.dynamic_view)
                    if replan_result is not None and replan_result.reachable:
                        vehicle.reroute_count += 1
                        reroute_event = self.timeline.schedule_event(
                            timestamp=self.clock.current_time,
                            event_type=SimEventType.UNIT_REROUTED,
                            payload={
                                "unit_id": vehicle.unit_id,
                                "obstructed_edge": list(obstruction),
                                "new_path": list(vehicle.tracker.path),
                                "new_estimated_cost": replan_result.total_cost,
                            },
                            priority=2,
                            description=f"Unit {vehicle.unit_id} dynamically rerouted around {obstruction}",
                        )
                        self.event_history.append(reroute_event)
                        self._process_event(reroute_event)

    def run_until(
        self,
        target_time: float,
        step_size: float = 1.0,
        max_ticks: int = 100_000,
    ) -> Dict[str, Any]:
        """Runs the simulation forward until clock reaches target_time."""
        ticks = 0
        while self.clock.current_time < target_time and ticks < max_ticks:
            dt = min(step_size, target_time - self.clock.current_time)
            self.step(dt)
            ticks += 1
        return self.summary()

    def run_until_idle(
        self,
        max_time: float = 3600.0,
        step_size: float = 1.0,
        max_ticks: int = 100_000,
    ) -> Dict[str, Any]:
        """Runs simulation until all events are processed and all units have arrived."""
        ticks = 0
        while self.clock.current_time < max_time and ticks < max_ticks:
            any_en_route = any(v.is_en_route for v in self.vehicles.values())
            if self.timeline.is_empty() and not any_en_route:
                break
            self.step(step_size)
            ticks += 1
        return self.summary()

    def summary(self) -> Dict[str, Any]:
        """Computes summary state metrics of the completed or active simulation."""
        total_travel_time = sum(v.total_travel_time for v in self.vehicles.values())
        total_distance = sum(v.total_distance_meters for v in self.vehicles.values())
        total_reroutes = sum(v.reroute_count for v in self.vehicles.values())
        units_arrived = sum(1 for v in self.vehicles.values() if v.is_on_scene)
        units_en_route = sum(1 for v in self.vehicles.values() if v.is_en_route)

        return {
            "current_time": round(self.clock.current_time, 2),
            "total_events_processed": len(self.event_history),
            "pending_events": len(self.timeline),
            "active_vehicles": len(self.vehicles),
            "units_arrived": units_arrived,
            "units_en_route": units_en_route,
            "total_travel_time": round(total_travel_time, 2),
            "total_distance_meters": round(total_distance, 2),
            "total_reroutes": total_reroutes,
            "active_hazards": len(self.active_hazards),
        }
