"""
Milestone 6.1 Demonstration: Discrete-Event Disaster Simulation Engine.
========================================================================
Demonstrates:
  1. Virtual simulation clock advancing without sleep or wall-clock dependencies.
  2. Priority queue event scheduling (incidents, apparatus dispatches, dynamic hazards).
  3. Continuous vehicle motion along network edges with kinematic interpolation.
  4. Real-time dynamic road closure during transit triggering reactive in-flight rerouting.
  5. Sub-millisecond execution: simulating minutes of multi-unit disaster response in milliseconds.
"""

from __future__ import annotations

import time

from emergency_intelligence.allocation.models import UnitStatus
from emergency_intelligence.events.hazards import HazardPolygon, HazardSeverity, HazardType
from emergency_intelligence.events.incidents import ApparatusType, EmergencyType, Incident, UrgencyLevel
from emergency_intelligence.graph.models import Edge, Graph, Node
from emergency_intelligence.simulation.engine import DisasterSimEngine, VehicleSimState
from emergency_intelligence.simulation.timeline import SimEventType


def build_demo_network() -> Graph:
    """Builds a representative 6-node urban road network:

        Station A (0, 2) -----(15s)-----> Junction B (2, 3) -----(12s)-----> Trauma Bay E (4, 3)
            |                                  |                                  ^
          (10s)                              (14s)                              (10s)
            v                                  v                                  |
        Crossroad C (0, 0) --(18s)-----> Bridge D (2, 1) --------(16s)---------->+
    """
    g = Graph()
    g.add_node(Node("A", label="Fire Station 1", coordinates=(0.0, 2.0)))
    g.add_node(Node("B", label="Northern Arterial", coordinates=(2.0, 3.0)))
    g.add_node(Node("C", label="South Avenue", coordinates=(0.0, 0.0)))
    g.add_node(Node("D", label="Main River Bridge", coordinates=(2.0, 1.0)))
    g.add_node(Node("E", label="Trauma Center", coordinates=(4.0, 3.0)))

    # Northern primary corridor
    g.add_edge(Edge("A", "B", cost=15.0, attributes={"travel_time": 15.0, "distance": 600.0}))
    g.add_edge(Edge("B", "E", cost=12.0, attributes={"travel_time": 12.0, "distance": 450.0}))

    # Southern secondary corridor
    g.add_edge(Edge("A", "C", cost=10.0, attributes={"travel_time": 10.0, "distance": 400.0}))
    g.add_edge(Edge("C", "D", cost=18.0, attributes={"travel_time": 18.0, "distance": 700.0}))
    g.add_edge(Edge("D", "E", cost=16.0, attributes={"travel_time": 16.0, "distance": 650.0}))

    # Connectors
    g.add_edge(Edge("B", "D", cost=14.0, attributes={"travel_time": 14.0, "distance": 500.0}))
    g.add_edge(Edge("D", "B", cost=14.0, attributes={"travel_time": 14.0, "distance": 500.0}))

    return g


def main() -> None:
    print("=" * 76)
    print("  Milestone 6.1: Discrete-Event Disaster Simulation Engine Demonstration")
    print("=" * 76)

    graph = build_demo_network()
    engine = DisasterSimEngine(graph, auto_reroute=True)

    # 1. Register fleet
    medic1 = VehicleSimState(
        unit_id="MEDIC-1",
        apparatus_type=ApparatusType.AMBULANCE_ALS,
        station_id="STATION-1",
    )
    engine.add_vehicle(medic1)

    # 2. Schedule incident and dispatch
    incident = Incident(
        incident_id="INC-2026-4401",
        emergency_type=EmergencyType.CARDIAC_ARREST,
        urgency=UrgencyLevel.PRIORITY_1_ECHO,
        coordinates=(4.0, 3.0),
        node_id="E",
        required_apparatus=[ApparatusType.AMBULANCE_ALS],
        description="Elderly male, unresponsive, CPR in progress",
    )
    engine.schedule_incident(incident, report_time=5.0)

    # Initial planned path: A -> B -> E (expected 27.0 seconds travel time)
    engine.dispatch_vehicle("MEDIC-1", "INC-2026-4401", path=["A", "B", "E"], dispatch_time=5.0)

    # 3. Schedule mid-flight environmental disaster:
    # At t = 18.0s (when MEDIC-1 is navigating junction B), northern arterial B -> E is severed by flood debris
    engine.sever_road(
        source_id="B",
        destination_id="E",
        timestamp=18.0,
        reason="Severe flash flood & fallen high-voltage power lines",
    )

    print("\n[Scenario Setup]")
    print(f"  Incident: {incident.incident_id} ({incident.emergency_type.value}) at node E")
    print("  Initial Assigned Path: A -> B -> E (27.0s baseline)")
    print("  Scheduled Disaster: Road B -> E closes at t = 18.0s")
    print("  Auto-Reroute Engine: ACTIVE")

    print("\n[Executing Simulation Steps]")
    start_wall = time.perf_counter()

    # Step simulation forward in 2.0-second increments
    step_num = 0
    while engine.clock.current_time < 60.0 and (not medic1.is_on_scene):
        step_num += 1
        due = engine.step(step_size=2.0)
        curr_t = engine.clock.current_time

        coords = medic1.current_position_coords(graph)
        u = medic1.tracker.current_tail_node if medic1.tracker else "?"
        v = medic1.tracker.current_head_node if medic1.tracker else "?"
        p = medic1.tracker.progress_ratio if medic1.tracker else 0.0

        status_str = f"t={curr_t:4.1f}s | {medic1.unit_id} [{medic1.status.value}] on ({u}->{v}, {p*100:4.1f}%) coords={coords}"
        print(f"  Step {step_num:02d}: {status_str}")

        for ev in due:
            if ev.event_type not in (SimEventType.TELEMETRY_SAMPLE,):
                print(f"         --> Event: {ev.event_type.value} | {ev.description}")

    elapsed_wall_ms = (time.perf_counter() - start_wall) * 1000.0

    print("\n[Simulation Results & Summary]")
    summary = engine.summary()
    print(f"  Simulated Virtual Time Elapsed : {summary['current_time']:.1f} s")
    print(f"  Wall-Clock Computation Time    : {elapsed_wall_ms:.2f} ms")
    print(f"  Speedup Factor (Virtual/Wall)  : {(summary['current_time'] / (elapsed_wall_ms / 1000.0)):,.0f}x real-time")
    print(f"  Events Processed               : {summary['total_events_processed']}")
    print(f"  Dynamic In-Flight Reroutes     : {medic1.reroute_count}")
    print(f"  Actual Final Route Traversed   : {' -> '.join(medic1.tracker.path)}")
    print(f"  Total Vehicle Travel Time      : {medic1.total_travel_time:.2f} s")
    print(f"  Total Distance Traversed       : {medic1.total_distance_meters:.1f} m")
    print(f"  On-Scene Arrival Status        : {'ARRIVED' if medic1.is_on_scene else 'IN-TRANSIT'}")

    assert medic1.is_on_scene, "Unit must have safely arrived on scene via the detour."
    assert medic1.reroute_count >= 1, "Unit must have executed an in-flight detour."
    print("\n[VERIFIED] Milestone 6.1 Discrete-Event Simulation Engine executed flawlessly!")


if __name__ == "__main__":
    main()
