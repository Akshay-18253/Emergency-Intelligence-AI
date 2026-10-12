"""
Multi-Incident Disaster Scenarios & Municipal Resource Contention.
==================================================================
Provides declarative multi-incident disaster benchmark suites and resource
exhaustion models:
  1. Spatial catchment saturation and secondary station cross-district fallback.
  2. Multi-tier priority holding queues during total fleet exhaustion.
  3. Turnout, en-route transit, on-scene service duration, and field redeployment.
  4. Standardized reproducible benchmarks:
     - Baseline Single Incident
     - Cascading Urban Multi-Alarm
     - Mid-Flight Critical Infrastructure Severance
     - Progressive Dynamic Inundation

Strictly zero external runtime dependencies (Python standard library only).
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
import time
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from emergency_intelligence.allocation.matcher import FleetManager, allocate_fleet_for_incident
from emergency_intelligence.allocation.models import (
    EmergencyStation,
    EmergencyUnit,
    UnitStatus,
)
from emergency_intelligence.events.hazards import HazardPolygon, HazardSeverity, HazardType
from emergency_intelligence.events.incidents import ApparatusType, EmergencyType, Incident, UrgencyLevel
from emergency_intelligence.events.mutations import DynamicGraphView
from emergency_intelligence.graph.astar import astar
from emergency_intelligence.graph.models import Edge, Graph, Node
from emergency_intelligence.simulation.engine import DisasterSimEngine, VehicleSimState
from emergency_intelligence.simulation.timeline import SimEvent, SimEventType


@dataclass
class QueuedIncidentState:
    """Tracks the live dispatch and service progression of an active incident.

    Attributes
    ----------
    incident : Incident
        Core incident domain entity.
    report_time : float
        Simulated timestamp (seconds) when emergency call was logged.
    on_scene_service_seconds : float
        Required duration apparatus must operate on scene before clearing.
    unfulfilled_requirements : List[ApparatusType]
        Apparatus types still pending dispatch due to municipal fleet exhaustion.
    assigned_units : List[str]
        Identifiers of apparatus dispatched to this incident.
    first_dispatch_time : Optional[float]
        Timestamp when the first unit was dispatched.
    all_dispatched_time : Optional[float]
        Timestamp when all required units were dispatched.
    first_arrival_time : Optional[float]
        Timestamp when the first unit arrived on scene (NFPA 1710 initial arrival).
    all_arrival_time : Optional[float]
        Timestamp when all required apparatus arrived on scene (NFPA 1710 full alarm).
    cleared_time : Optional[float]
        Timestamp when on-scene operations concluded and units cleared.
    queue_delay_seconds : float
        Duration between call intake and full apparatus dispatch.
    """

    incident: Incident
    report_time: float
    on_scene_service_seconds: float = 30.0
    unfulfilled_requirements: List[ApparatusType] = field(default_factory=list)
    assigned_units: List[str] = field(default_factory=list)
    first_dispatch_time: Optional[float] = None
    all_dispatched_time: Optional[float] = None
    first_arrival_time: Optional[float] = None
    all_arrival_time: Optional[float] = None
    cleared_time: Optional[float] = None
    queue_delay_seconds: float = 0.0

    @property
    def is_fully_dispatched(self) -> bool:
        """Returns True if all required apparatus have been assigned and dispatched."""
        return len(self.unfulfilled_requirements) == 0

    @property
    def is_resolved(self) -> bool:
        """Returns True if the incident has concluded on-scene operations and cleared."""
        return self.cleared_time is not None


@dataclass
class ScenarioDefinition:
    """Declarative specification of a reproducible disaster simulation scenario.

    Attributes
    ----------
    name : str
        Unique identifier for the benchmark scenario.
    description : str
        Detailed scenario narrative and evaluation objectives.
    graph : Graph
        Road network topology.
    stations : List[EmergencyStation]
        Municipal stations and response depots.
    fleet_units : List[EmergencyUnit]
        Response apparatus fleet.
    incidents : List[Tuple[float, Incident, float]]
        Ordered list of (report_time_seconds, Incident, on_scene_service_seconds).
    hazards : List[Tuple[float, str, HazardPolygon]]
        Scheduled environmental hazard emergence (timestamp, hazard_id, polygon).
    road_closures : List[Tuple[float, str, str, str]]
        Scheduled road severances (timestamp, source_id, destination_id, reason).
    max_simulation_time : float
        Maximum simulation time in seconds before terminating.
    step_size : float
        Discrete clock step increment in seconds.
    """

    name: str
    description: str
    graph: Graph
    stations: List[EmergencyStation]
    fleet_units: List[EmergencyUnit]
    incidents: List[Tuple[float, Incident, float]]
    hazards: List[Tuple[float, str, HazardPolygon]] = field(default_factory=list)
    road_closures: List[Tuple[float, str, str, str]] = field(default_factory=list)
    max_simulation_time: float = 3600.0
    step_size: float = 1.0


@dataclass
class ScenarioResult:
    """Comprehensive empirical telemetry output of an executed scenario."""

    scenario_name: str
    simulated_duration: float
    wall_clock_ms: float
    total_incidents: int
    incidents_serviced: int
    incidents_queued_count: int
    average_queue_delay_seconds: float
    max_queue_delay_seconds: float
    units_dispatched_count: int
    total_reroutes: int
    total_travel_time: float
    total_distance_meters: float
    average_response_time: float
    max_response_time: float
    incident_records: List[Dict[str, Any]]
    vehicle_records: List[Dict[str, Any]]
    engine_summary: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        """Serializes scenario results for benchmarking telemetry and export."""
        return {
            "scenario_name": self.scenario_name,
            "simulated_duration": round(self.simulated_duration, 2),
            "wall_clock_ms": round(self.wall_clock_ms, 2),
            "total_incidents": self.total_incidents,
            "incidents_serviced": self.incidents_serviced,
            "incidents_queued_count": self.incidents_queued_count,
            "average_queue_delay_seconds": round(self.average_queue_delay_seconds, 2),
            "max_queue_delay_seconds": round(self.max_queue_delay_seconds, 2),
            "units_dispatched_count": self.units_dispatched_count,
            "total_reroutes": self.total_reroutes,
            "total_travel_time": round(self.total_travel_time, 2),
            "total_distance_meters": round(self.total_distance_meters, 2),
            "average_response_time": round(self.average_response_time, 2),
            "max_response_time": round(self.max_response_time, 2),
            "incident_records": self.incident_records,
            "vehicle_records": self.vehicle_records,
            "engine_summary": self.engine_summary,
        }


class ScenarioRunner:
    """Executes a declarative ScenarioDefinition against DisasterSimEngine.

    Coordinates multi-incident dispatching, resource exhaustion queuing,
    secondary station fallback, on-scene service duration, and post-mission
    field redeployment.
    """

    def __init__(self, scenario: ScenarioDefinition) -> None:
        self.scenario = scenario
        self.engine = DisasterSimEngine(
            graph=scenario.graph,
            auto_reroute=True,
        )
        self.fleet_manager = FleetManager()

        # Operational state
        self.incident_states: Dict[str, QueuedIncidentState] = {}
        self.pending_queue: List[QueuedIncidentState] = []
        self._on_scene_units: Dict[str, Tuple[str, float]] = {}  # unit_id -> (incident_id, scheduled_clear_time)

        self._setup_scenario()

    def _setup_scenario(self) -> None:
        """Registers facilities, fleet vehicles, and schedules environmental events."""
        # 1. Register stations
        for station in self.scenario.stations:
            self.fleet_manager.register_station(station)

        # 2. Register fleet units
        for u in self.scenario.fleet_units:
            self.fleet_manager.register_unit(u)
            sim_vehicle = VehicleSimState(
                unit_id=u.unit_id,
                apparatus_type=u.apparatus_type,
                station_id=u.station_id or "STATION_UNKNOWN",
                status=UnitStatus.AVAILABLE,
            )
            self.engine.add_vehicle(sim_vehicle)

        # 3. Schedule incidents
        for report_time, inc, service_dur in self.scenario.incidents:
            reqs = list(inc.required_apparatus) if inc.required_apparatus else [ApparatusType.AMBULANCE_ALS]
            state = QueuedIncidentState(
                incident=inc,
                report_time=report_time,
                on_scene_service_seconds=service_dur,
                unfulfilled_requirements=list(reqs),
            )
            self.incident_states[inc.incident_id] = state

            # Schedule on engine timeline
            self.engine.schedule_incident(inc, report_time=report_time)

        # 4. Schedule hazards
        for t, hid, poly in self.scenario.hazards:
            self.engine.spawn_hazard(hid, poly, timestamp=t)

        # 5. Schedule road closures
        for t, src, dst, reason in self.scenario.road_closures:
            self.engine.sever_road(src, dst, timestamp=t, reason=reason)

        # 6. Wire internal event handlers
        self.engine.register_handler(SimEventType.INCIDENT_DECLARED, self._on_incident_declared)
        self.engine.register_handler(SimEventType.UNIT_ARRIVED, self._on_unit_arrived)
        self.engine.register_handler(SimEventType.UNIT_CLEARED, self._on_unit_cleared)

    def _on_incident_declared(self, event: SimEvent, eng: DisasterSimEngine) -> None:
        """Invoked when an incident report occurs on the timeline."""
        iid = event.payload["incident_id"]
        state = self.incident_states[iid]
        self._attempt_dispatch(state)

    def _attempt_dispatch(self, state: QueuedIncidentState) -> bool:
        """Attempts to match and allocate available apparatus for pending requirements."""
        if state.is_fully_dispatched:
            return True

        curr_time = self.engine.clock.current_time
        still_unfulfilled: List[ApparatusType] = []

        for req_type in state.unfulfilled_requirements:
            # Find available apparatus
            candidates = [
                u for u in self.fleet_manager.get_available_units(apparatus_type=req_type)
                if self.engine.vehicles[u.unit_id].is_available
            ]

            if not candidates:
                still_unfulfilled.append(req_type)
                continue

            # Rank by shortest path ETA
            target_node = state.incident.node_id or ""
            best_unit: Optional[EmergencyUnit] = None
            best_route = None
            best_cost = math.inf

            for cand in candidates:
                route = astar(
                    self.engine.dynamic_view,
                    source=cand.current_node_id,
                    destination=target_node,
                )
                if route.reachable and route.path and route.total_cost < best_cost:
                    best_cost = route.total_cost
                    best_route = route
                    best_unit = cand

            if best_unit is not None and best_route is not None:
                # Dispatch unit
                best_unit.status = UnitStatus.EN_ROUTE
                self.engine.dispatch_vehicle(
                    unit_id=best_unit.unit_id,
                    incident_id=state.incident.incident_id,
                    path=best_route.path,
                    dispatch_time=curr_time,
                )
                state.assigned_units.append(best_unit.unit_id)

                if state.first_dispatch_time is None:
                    state.first_dispatch_time = curr_time
            else:
                still_unfulfilled.append(req_type)

        state.unfulfilled_requirements = still_unfulfilled

        if state.is_fully_dispatched:
            state.all_dispatched_time = curr_time
            state.queue_delay_seconds = curr_time - state.report_time
            if state in self.pending_queue:
                self.pending_queue.remove(state)
            return True
        else:
            if state not in self.pending_queue:
                self.pending_queue.append(state)
                # Sort holding queue: higher urgency tier first, then FIFO by report_time
                self.pending_queue.sort(
                    key=lambda s: (self._urgency_rank(s.incident.urgency), s.report_time)
                )
            return False

    @staticmethod
    def _urgency_rank(urgency: UrgencyLevel) -> int:
        """Returns integer rank for priority sorting (lower int = higher priority)."""
        ranks = {
            UrgencyLevel.PRIORITY_1_ECHO: 1,
            UrgencyLevel.PRIORITY_2_DELTA: 2,
            UrgencyLevel.PRIORITY_3_BRAVO: 3,
            UrgencyLevel.PRIORITY_4_ALPHA: 4,
        }
        return ranks.get(urgency, 10)

    def _on_unit_arrived(self, event: SimEvent, eng: DisasterSimEngine) -> None:
        """Invoked when a vehicle reaches the incident scene."""
        uid = event.payload["unit_id"]
        iid = event.payload["incident_id"]
        state = self.incident_states.get(iid)
        curr_time = eng.clock.current_time

        if state:
            if state.first_arrival_time is None:
                state.first_arrival_time = curr_time

            # Check if all assigned units have arrived on scene
            all_arrived = all(
                eng.vehicles[u_id].is_on_scene
                for u_id in state.assigned_units
            )
            if all_arrived and state.is_fully_dispatched and state.all_arrival_time is None:
                state.all_arrival_time = curr_time

            # Schedule unit clearance when on-scene service duration completes
            clear_time = curr_time + state.on_scene_service_seconds
            self._on_scene_units[uid] = (iid, clear_time)
            eng.timeline.schedule_event(
                timestamp=clear_time,
                event_type=SimEventType.UNIT_CLEARED,
                payload={"unit_id": uid, "incident_id": iid},
                priority=3,
                description=f"Unit {uid} cleared scene at {iid}",
            )

    def _on_unit_cleared(self, event: SimEvent, eng: DisasterSimEngine) -> None:
        """Invoked when a vehicle finishes on-scene work and becomes available."""
        uid = event.payload["unit_id"]
        iid = event.payload["incident_id"]
        state = self.incident_states.get(iid)
        curr_time = eng.clock.current_time

        self._on_scene_units.pop(uid, None)

        sim_veh = eng.vehicles[uid]
        fleet_u = self.fleet_manager.get_unit(uid)

        # Update unit's physical position to the scene location where it just cleared
        if state and state.incident.node_id and fleet_u:
            fleet_u.current_node_id = state.incident.node_id

        # Mark unit available for redeployment
        sim_veh.status = UnitStatus.AVAILABLE
        sim_veh.clear_time = curr_time
        sim_veh.assigned_incident_id = None
        if fleet_u:
            fleet_u.status = UnitStatus.AVAILABLE

        # Check if all units for this incident have cleared
        if state:
            assigned_cleared = all(
                eng.vehicles[u_id].clear_time is not None
                for u_id in state.assigned_units
            )
            if assigned_cleared and state.cleared_time is None:
                state.cleared_time = curr_time

        # Check holding queue for pending incidents awaiting this apparatus type!
        self._process_queue()

    def _process_queue(self) -> None:
        """Inspects the pending queue and allocates newly freed apparatus."""
        for state in list(self.pending_queue):
            fulfilled = self._attempt_dispatch(state)
            if fulfilled:
                # Dispatched successfully, continue to next
                pass

    def run(self) -> ScenarioResult:
        """Runs the benchmark scenario to completion or timeout."""
        start_wall = time.perf_counter()

        while self.engine.clock.current_time < self.scenario.max_simulation_time:
            # Check completion: all incidents resolved and timeline empty
            all_resolved = all(s.is_resolved for s in self.incident_states.values())
            any_en_route = any(v.is_en_route for v in self.engine.vehicles.values())
            if all_resolved and not any_en_route and self.engine.timeline.is_empty():
                break

            self.engine.step(step_size=self.scenario.step_size)

        wall_ms = (time.perf_counter() - start_wall) * 1000.0

        return self._compile_results(wall_ms)

    def _compile_results(self, wall_ms: float) -> ScenarioResult:
        """Compiles empirical telemetry into a structured ScenarioResult."""
        serviced = [s for s in self.incident_states.values() if s.first_arrival_time is not None]
        response_times = [
            (s.first_arrival_time - s.report_time)
            for s in serviced
            if s.first_arrival_time is not None
        ]

        for s in self.incident_states.values():
            if not s.is_fully_dispatched:
                s.queue_delay_seconds = self.engine.clock.current_time - s.report_time

        queued = [
            s for s in self.incident_states.values()
            if s.queue_delay_seconds > 0.0 or (not s.is_fully_dispatched)
        ]
        queue_delays = [s.queue_delay_seconds for s in queued]

        avg_resp = (sum(response_times) / len(response_times)) if response_times else 0.0
        max_resp = max(response_times) if response_times else 0.0

        avg_q_delay = (sum(queue_delays) / len(queue_delays)) if queue_delays else 0.0
        max_q_delay = max(queue_delays) if queue_delays else 0.0

        incident_recs = []
        for s in self.incident_states.values():
            incident_recs.append({
                "incident_id": s.incident.incident_id,
                "emergency_type": s.incident.emergency_type.value,
                "urgency": s.incident.urgency.value,
                "report_time": round(s.report_time, 2),
                "first_dispatch_time": round(s.first_dispatch_time, 2) if s.first_dispatch_time else None,
                "first_arrival_time": round(s.first_arrival_time, 2) if s.first_arrival_time else None,
                "all_arrival_time": round(s.all_arrival_time, 2) if s.all_arrival_time else None,
                "cleared_time": round(s.cleared_time, 2) if s.cleared_time else None,
                "response_time_seconds": (
                    round(s.first_arrival_time - s.report_time, 2)
                    if s.first_arrival_time
                    else None
                ),
                "queue_delay_seconds": round(s.queue_delay_seconds, 2),
                "assigned_units": list(s.assigned_units),
                "is_resolved": s.is_resolved,
            })

        vehicle_recs = [v.to_dict() for v in self.engine.vehicles.values()]

        summary = self.engine.summary()

        return ScenarioResult(
            scenario_name=self.scenario.name,
            simulated_duration=self.engine.clock.current_time,
            wall_clock_ms=wall_ms,
            total_incidents=len(self.incident_states),
            incidents_serviced=len(serviced),
            incidents_queued_count=len(queued),
            average_queue_delay_seconds=avg_q_delay,
            max_queue_delay_seconds=max_q_delay,
            units_dispatched_count=sum(len(s.assigned_units) for s in self.incident_states.values()),
            total_reroutes=summary["total_reroutes"],
            total_travel_time=summary["total_travel_time"],
            total_distance_meters=summary["total_distance_meters"],
            average_response_time=avg_resp,
            max_response_time=max_resp,
            incident_records=incident_recs,
            vehicle_records=vehicle_recs,
            engine_summary=summary,
        )


# ---------------------------------------------------------------------------
# Standard Benchmark Scenario Builders
# ---------------------------------------------------------------------------


def build_single_incident_baseline_scenario() -> ScenarioDefinition:
    """Builds Scenario 1: Baseline Single Incident.

    Single medical emergency at node E (Trauma Center). Station 1 at node A
    dispatches MEDIC-1 along clear, unobstructed route A -> B -> E (27.0s baseline).
    """
    g = Graph()
    g.add_node(Node("A", coordinates=(0.0, 2.0)))
    g.add_node(Node("B", coordinates=(2.0, 3.0)))
    g.add_node(Node("E", coordinates=(4.0, 3.0)))

    g.add_edge(Edge("A", "B", cost=15.0, attributes={"travel_time": 15.0, "distance": 600.0}))
    g.add_edge(Edge("B", "E", cost=12.0, attributes={"travel_time": 12.0, "distance": 450.0}))

    station = EmergencyStation(
        station_id="STATION-1",
        name="Station 1 - Central",
        node_id="A",
    )
    unit = EmergencyUnit(
        unit_id="MEDIC-1",
        apparatus_type=ApparatusType.AMBULANCE_ALS,
        current_node_id="A",
        station_id="STATION-1",
    )

    incident = Incident(
        incident_id="INC-BASE-01",
        emergency_type=EmergencyType.CARDIAC_ARREST,
        urgency=UrgencyLevel.PRIORITY_1_ECHO,
        coordinates=(4.0, 3.0),
        node_id="E",
        required_apparatus=[ApparatusType.AMBULANCE_ALS],
    )

    return ScenarioDefinition(
        name="Baseline Single Incident",
        description="Controlled baseline single ALS medical emergency response under clear roads.",
        graph=g,
        stations=[station],
        fleet_units=[unit],
        incidents=[(5.0, incident, 20.0)],
        max_simulation_time=120.0,
        step_size=1.0,
    )


def build_cascading_multi_alarm_scenario() -> ScenarioDefinition:
    """Builds Scenario 2: Cascading Urban Multi-Alarm & Resource Contention.

    Two stations across town:
      - Station 1 at A: ENGINE-1, MEDIC-1
      - Station 2 at F: ENGINE-2, MEDIC-2

    Timeline:
      t = 5s:  Incident 1 (Structure Fire at D) requires [FIRE_ENGINE, AMBULANCE_ALS].
               Depletes Station 1's engine and ambulance!
      t = 15s: Incident 2 (Structure Fire at B) requires [FIRE_ENGINE].
               Station 1 is exhausted; triggers cross-district secondary dispatch from Station 2!
      t = 25s: Incident 3 (Cardiac Arrest at C) requires [AMBULANCE_ALS].
               Station 1 has no ambulances; Station 2 dispatches MEDIC-2!
      t = 30s: Incident 4 (Cardiac Arrest at B) requires [AMBULANCE_ALS].
               TOTAL FLEET EXHAUSTION! All ambulances in city are occupied.
               Incident 4 enters the priority holding queue.
               When MEDIC-1 finishes on scene at Incident 1, it redeploys to Incident 4!
    """
    g = Graph()
    # City layout:
    # A (Station 1) --- B --- D
    # |                 |     |
    # C --------------- E --- F (Station 2)
    g.add_node(Node("A", coordinates=(0.0, 2.0)))
    g.add_node(Node("B", coordinates=(2.0, 2.0)))
    g.add_node(Node("C", coordinates=(0.0, 0.0)))
    g.add_node(Node("D", coordinates=(4.0, 2.0)))
    g.add_node(Node("E", coordinates=(2.0, 0.0)))
    g.add_node(Node("F", coordinates=(4.0, 0.0)))

    # Bidirectional street grid (10-15s per segment)
    edges = [
        ("A", "B", 10.0), ("B", "A", 10.0),
        ("B", "D", 10.0), ("D", "B", 10.0),
        ("A", "C", 12.0), ("C", "A", 12.0),
        ("B", "E", 12.0), ("E", "B", 12.0),
        ("D", "F", 12.0), ("F", "D", 12.0),
        ("C", "E", 10.0), ("E", "C", 10.0),
        ("E", "F", 10.0), ("F", "E", 10.0),
    ]
    for u, v, cost in edges:
        g.add_edge(Edge(u, v, cost=cost, attributes={"travel_time": cost, "distance": cost * 40.0}))

    s1 = EmergencyStation("STATION-1", "Central Fire", "A", (0.0, 2.0))
    s2 = EmergencyStation("STATION-2", "Eastside Fire", "F", (4.0, 0.0))

    e1 = EmergencyUnit("ENGINE-1", ApparatusType.FIRE_ENGINE, "A", "STATION-1")
    m1 = EmergencyUnit("MEDIC-1", ApparatusType.AMBULANCE_ALS, "A", "STATION-1")
    e2 = EmergencyUnit("ENGINE-2", ApparatusType.FIRE_ENGINE, "F", "STATION-2")
    m2 = EmergencyUnit("MEDIC-2", ApparatusType.AMBULANCE_ALS, "F", "STATION-2")

    inc1 = Incident(
        "INC-FIRE-01",
        EmergencyType.STRUCTURE_FIRE,
        UrgencyLevel.PRIORITY_1_ECHO,
        coordinates=(4.0, 2.0),
        node_id="D",
        required_apparatus=[ApparatusType.FIRE_ENGINE, ApparatusType.AMBULANCE_ALS],
    )
    inc2 = Incident(
        "INC-FIRE-02",
        EmergencyType.STRUCTURE_FIRE,
        UrgencyLevel.PRIORITY_1_ECHO,
        coordinates=(2.0, 2.0),
        node_id="B",
        required_apparatus=[ApparatusType.FIRE_ENGINE],
    )
    inc3 = Incident(
        "INC-MED-03",
        EmergencyType.CARDIAC_ARREST,
        UrgencyLevel.PRIORITY_1_ECHO,
        coordinates=(0.0, 0.0),
        node_id="C",
        required_apparatus=[ApparatusType.AMBULANCE_ALS],
    )
    inc4 = Incident(
        "INC-MED-04",
        EmergencyType.CARDIAC_ARREST,
        UrgencyLevel.PRIORITY_2_DELTA,
        coordinates=(2.0, 2.0),
        node_id="B",
        required_apparatus=[ApparatusType.AMBULANCE_ALS],
    )

    return ScenarioDefinition(
        name="Cascading Urban Multi-Alarm",
        description="Multi-alarm concurrency testing cross-station fallback, apparatus exhaustion, and queue dispatch.",
        graph=g,
        stations=[s1, s2],
        fleet_units=[e1, m1, e2, m2],
        incidents=[
            (5.0, inc1, 25.0),
            (15.0, inc2, 30.0),
            (25.0, inc3, 20.0),
            (30.0, inc4, 15.0),
        ],
        max_simulation_time=300.0,
        step_size=1.0,
    )


def build_infrastructure_severance_scenario() -> ScenarioDefinition:
    """Builds Scenario 3: Mid-Flight Critical Infrastructure Severance.

    Ambulance MEDIC-1 departs Station A towards Hospital E via Northern Bridge B -> E.
    At t = 16.0s (midway through transit), Bridge B -> E collapses.
    Tests dynamic vector replanning via Southern Bridge D -> E.
    """
    g = Graph()
    g.add_node(Node("A", coordinates=(0.0, 2.0)))
    g.add_node(Node("B", coordinates=(2.0, 3.0)))
    g.add_node(Node("C", coordinates=(0.0, 0.0)))
    g.add_node(Node("D", coordinates=(2.0, 1.0)))
    g.add_node(Node("E", coordinates=(4.0, 2.0)))

    g.add_edge(Edge("A", "B", cost=15.0, attributes={"travel_time": 15.0, "distance": 600.0}))
    g.add_edge(Edge("B", "E", cost=12.0, attributes={"travel_time": 12.0, "distance": 480.0}))
    g.add_edge(Edge("A", "C", cost=10.0, attributes={"travel_time": 10.0, "distance": 400.0}))
    g.add_edge(Edge("C", "D", cost=18.0, attributes={"travel_time": 18.0, "distance": 720.0}))
    g.add_edge(Edge("D", "E", cost=16.0, attributes={"travel_time": 16.0, "distance": 640.0}))
    g.add_edge(Edge("B", "D", cost=14.0, attributes={"travel_time": 14.0, "distance": 560.0}))
    g.add_edge(Edge("D", "B", cost=14.0, attributes={"travel_time": 14.0, "distance": 560.0}))

    station = EmergencyStation("STATION-1", "North Station", "A", (0.0, 2.0))
    unit = EmergencyUnit("MEDIC-1", ApparatusType.AMBULANCE_ALS, "A", "STATION-1")

    incident = Incident(
        "INC-SEVER-01",
        EmergencyType.TRAUMA_MAJOR,
        UrgencyLevel.PRIORITY_1_ECHO,
        coordinates=(4.0, 2.0),
        node_id="E",
        required_apparatus=[ApparatusType.AMBULANCE_ALS],
    )

    return ScenarioDefinition(
        name="Mid-Flight Infrastructure Severance",
        description="Ambulance encounters active bridge collapse while en-route; recalculates in-flight detour.",
        graph=g,
        stations=[station],
        fleet_units=[unit],
        incidents=[(0.0, incident, 20.0)],
        road_closures=[(12.0, "B", "E", "Earthquake / bridge structural failure")],
        max_simulation_time=120.0,
        step_size=1.0,
    )


def build_progressive_inundation_scenario() -> ScenarioDefinition:
    """Builds Scenario 4: Progressive Dynamic Inundation.

    Flood boundary expands across the river valley in 3 discrete phases:
      Phase 1 at t = 10s: Clips low-lying riverbank road
      Phase 2 at t = 25s: Floods central intersection
      Phase 3 at t = 40s: Submerges eastern bypass
    Two responding units must navigate around the spreading hazard boundary.
    """
    g = Graph()
    g.add_node(Node("W1", coordinates=(0.0, 2.0)))
    g.add_node(Node("W2", coordinates=(1.0, 3.0)))
    g.add_node(Node("C1", coordinates=(2.0, 2.0)))
    g.add_node(Node("C2", coordinates=(2.0, 0.0)))
    g.add_node(Node("E1", coordinates=(4.0, 2.0)))
    g.add_node(Node("E2", coordinates=(4.0, 0.0)))

    edges = [
        ("W1", "W2", 10.0), ("W2", "W1", 10.0),
        ("W1", "C2", 12.0), ("C2", "W1", 12.0),
        ("W2", "C1", 10.0), ("C1", "W2", 10.0),
        ("C1", "E1", 10.0), ("E1", "C1", 10.0),
        ("C2", "E2", 10.0), ("E2", "C2", 10.0),
        ("E1", "E2", 10.0), ("E2", "E1", 10.0),
        ("C1", "C2", 10.0), ("C2", "C1", 10.0),
    ]
    for u, v, cost in edges:
        g.add_edge(Edge(u, v, cost=cost, attributes={"travel_time": cost, "distance": cost * 40.0}))

    station = EmergencyStation("STATION-1", "West Depot", "W1", (0.0, 2.0))
    m1 = EmergencyUnit("MEDIC-1", ApparatusType.AMBULANCE_ALS, "W1", "STATION-1")
    e1 = EmergencyUnit("ENGINE-1", ApparatusType.FIRE_ENGINE, "W1", "STATION-1")

    inc1 = Incident(
        "INC-FLOOD-01",
        EmergencyType.FLASH_FLOOD,
        UrgencyLevel.PRIORITY_1_ECHO,
        coordinates=(4.0, 2.0),
        node_id="E1",
        required_apparatus=[ApparatusType.AMBULANCE_ALS],
    )
    inc2 = Incident(
        "INC-FLOOD-02",
        EmergencyType.TRAUMA_MAJOR,
        UrgencyLevel.PRIORITY_1_ECHO,
        coordinates=(4.0, 0.0),
        node_id="E2",
        required_apparatus=[ApparatusType.FIRE_ENGINE],
    )

    # 3 Progressive flood expansion polygons
    flood_p1 = HazardPolygon(
        hazard_id="FLOOD-STAGE-1",
        hazard_type=HazardType.FLASH_FLOOD,
        severity=HazardSeverity.CRITICAL_BLOCKED,
        boundary_coordinates=[(1.8, 1.8), (2.2, 1.8), (2.2, 2.2), (1.8, 2.2)],
    )
    flood_p2 = HazardPolygon(
        hazard_id="FLOOD-STAGE-2",
        hazard_type=HazardType.FLASH_FLOOD,
        severity=HazardSeverity.CRITICAL_BLOCKED,
        boundary_coordinates=[(0.8, 1.8), (2.5, 1.8), (2.5, 3.2), (0.8, 3.2)],
    )

    return ScenarioDefinition(
        name="Progressive Dynamic Inundation",
        description="Multi-unit response against an expanding flood hazard polygon closing successive corridors.",
        graph=g,
        stations=[station],
        fleet_units=[m1, e1],
        incidents=[
            (2.0, inc1, 20.0),
            (5.0, inc2, 20.0),
        ],
        hazards=[
            (10.0, "FLOOD-STAGE-1", flood_p1),
            (25.0, "FLOOD-STAGE-2", flood_p2),
        ],
        max_simulation_time=150.0,
        step_size=1.0,
    )


BENCHMARK_SCENARIOS: Dict[str, Callable[[], ScenarioDefinition]] = {
    "single_incident_baseline": build_single_incident_baseline_scenario,
    "cascading_multi_alarm": build_cascading_multi_alarm_scenario,
    "infrastructure_severance": build_infrastructure_severance_scenario,
    "progressive_inundation": build_progressive_inundation_scenario,
}


def list_benchmark_scenarios() -> List[str]:
    """Returns sorted list of registered benchmark scenario keys."""
    return sorted(BENCHMARK_SCENARIOS.keys())


def get_benchmark_scenario(name: str) -> ScenarioDefinition:
    """Instantiates and returns the benchmark scenario matching name."""
    factory = BENCHMARK_SCENARIOS.get(name)
    if not factory:
        raise KeyError(
            f"Scenario '{name}' not found. Available scenarios: {list_benchmark_scenarios()}."
        )
    return factory()
