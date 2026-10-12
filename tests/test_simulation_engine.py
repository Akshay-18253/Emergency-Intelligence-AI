"""
Tests for Discrete-Event Disaster Simulation Engine & Virtual Clock.
====================================================================
Verifies simulation timeline, clock progression, vehicle kinematics,
event handlers, and dynamic in-flight replanning under disaster closures.
"""

from __future__ import annotations

import math
import pytest

from emergency_intelligence.allocation.models import UnitStatus
from emergency_intelligence.events.hazards import HazardPolygon, HazardSeverity, HazardType
from emergency_intelligence.events.incidents import ApparatusType, Incident, EmergencyType, UrgencyLevel
from emergency_intelligence.events.mutations import DynamicGraphView
from emergency_intelligence.graph.models import Edge, Graph, Node
from emergency_intelligence.simulation.engine import DisasterSimEngine, VehicleSimState
from emergency_intelligence.simulation.timeline import (
    SimEvent,
    SimEventType,
    SimulationClock,
    SimulationTimeline,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def grid_graph() -> Graph:
    """Creates a 4-node diamond street network with coordinates:

    A (0, 1) ---> B (1, 2) ---> D (2, 1)
      |                          ^
      v                          |
      C (1, 0) ------------------+
    """
    g = Graph()
    g.add_node(Node("A", coordinates=(0.0, 1.0)))
    g.add_node(Node("B", coordinates=(1.0, 2.0)))
    g.add_node(Node("C", coordinates=(1.0, 0.0)))
    g.add_node(Node("D", coordinates=(2.0, 1.0)))

    # Direct upper path: A -> B -> D (each edge 10 seconds, 100 meters)
    g.add_edge(Edge("A", "B", cost=10.0, attributes={"travel_time": 10.0, "distance": 100.0}))
    g.add_edge(Edge("B", "D", cost=10.0, attributes={"travel_time": 10.0, "distance": 100.0}))

    # Detour lower path: A -> C -> D (each edge 15 seconds, 150 meters)
    g.add_edge(Edge("A", "C", cost=15.0, attributes={"travel_time": 15.0, "distance": 150.0}))
    g.add_edge(Edge("C", "D", cost=15.0, attributes={"travel_time": 15.0, "distance": 150.0}))

    return g


# ---------------------------------------------------------------------------
# Timeline & Clock Tests
# ---------------------------------------------------------------------------


class TestSimulationClock:
    def test_default_initialization(self) -> None:
        clock = SimulationClock()
        assert clock.current_time == 0.0

    def test_advance_to_valid_time(self) -> None:
        clock = SimulationClock(10.0)
        assert clock.advance_to(25.5) == 25.5
        assert clock.current_time == 25.5

    def test_advance_to_backwards_raises(self) -> None:
        clock = SimulationClock(50.0)
        with pytest.raises(ValueError, match="Clock cannot retreat backwards"):
            clock.advance_to(49.9)

    def test_tick_advances_forward(self) -> None:
        clock = SimulationClock(0.0)
        assert clock.tick(5.0) == 5.0
        assert clock.tick(12.5) == 17.5

    def test_tick_negative_raises(self) -> None:
        clock = SimulationClock(10.0)
        with pytest.raises(ValueError, match="cannot be negative"):
            clock.tick(-1.0)

    def test_reset(self) -> None:
        clock = SimulationClock(100.0)
        clock.reset(0.0)
        assert clock.current_time == 0.0
        clock.reset(15.0)
        assert clock.current_time == 15.0

    def test_reset_negative_raises(self) -> None:
        clock = SimulationClock()
        with pytest.raises(ValueError, match="cannot be negative"):
            clock.reset(-5.0)


class TestSimulationTimeline:
    def test_schedule_and_peek(self) -> None:
        tl = SimulationTimeline()
        assert tl.is_empty()
        assert tl.peek() is None

        e1 = tl.schedule_event(10.0, SimEventType.INCIDENT_DECLARED, description="Inc 1")
        assert not tl.is_empty()
        assert len(tl) == 1
        assert tl.peek() == e1

    def test_chronological_ordering(self) -> None:
        tl = SimulationTimeline()
        e3 = tl.schedule_event(30.0, SimEventType.UNIT_ARRIVED)
        e1 = tl.schedule_event(10.0, SimEventType.INCIDENT_DECLARED)
        e2 = tl.schedule_event(20.0, SimEventType.UNIT_DISPATCHED)

        assert tl.pop_next() == e1
        assert tl.pop_next() == e2
        assert tl.pop_next() == e3
        assert tl.pop_next() is None

    def test_priority_tie_breaking(self) -> None:
        tl = SimulationTimeline()
        # Same timestamp, different priority (lower number = higher priority)
        e_low = tl.schedule_event(15.0, SimEventType.CUSTOM, priority=20, description="Low")
        e_high = tl.schedule_event(15.0, SimEventType.CUSTOM, priority=5, description="High")

        assert tl.pop_next() == e_high
        assert tl.pop_next() == e_low

    def test_fifo_tie_breaking_on_identical_time_and_priority(self) -> None:
        tl = SimulationTimeline()
        first = tl.schedule_event(10.0, SimEventType.CUSTOM, priority=10, description="First")
        second = tl.schedule_event(10.0, SimEventType.CUSTOM, priority=10, description="Second")

        assert tl.pop_next() == first
        assert tl.pop_next() == second

    def test_pop_due_events(self) -> None:
        tl = SimulationTimeline()
        tl.schedule_event(5.0, SimEventType.INCIDENT_DECLARED)
        tl.schedule_event(10.0, SimEventType.UNIT_DISPATCHED)
        tl.schedule_event(15.0, SimEventType.HAZARD_SPAWNED)
        tl.schedule_event(20.0, SimEventType.UNIT_ARRIVED)

        due_at_12 = tl.pop_due(12.0)
        assert len(due_at_12) == 2
        assert [e.timestamp for e in due_at_12] == [5.0, 10.0]

        due_at_14 = tl.pop_due(14.0)
        assert len(due_at_14) == 0

        due_at_25 = tl.pop_due(25.0)
        assert len(due_at_25) == 2
        assert [e.timestamp for e in due_at_25] == [15.0, 20.0]
        assert tl.is_empty()

    def test_cancel_event(self) -> None:
        tl = SimulationTimeline()
        e1 = tl.schedule_event(10.0, SimEventType.INCIDENT_DECLARED)
        e2 = tl.schedule_event(20.0, SimEventType.UNIT_DISPATCHED)

        assert len(tl) == 2
        assert tl.cancel(e1.event_id) is True
        assert len(tl) == 1
        assert tl.peek() == e2
        assert tl.pop_next() == e2
        assert tl.is_empty()

    def test_cancel_invalid_id(self) -> None:
        tl = SimulationTimeline()
        assert tl.cancel("") is False

    def test_negative_timestamp_raises(self) -> None:
        tl = SimulationTimeline()
        with pytest.raises(ValueError, match="cannot be negative"):
            tl.schedule(SimEvent(timestamp=-1.0))

    def test_clear(self) -> None:
        tl = SimulationTimeline()
        tl.schedule_event(10.0, SimEventType.CUSTOM)
        tl.schedule_event(20.0, SimEventType.CUSTOM)
        tl.clear()
        assert tl.is_empty()
        assert len(tl) == 0

    def test_event_to_dict(self) -> None:
        e = SimEvent(
            timestamp=12.3456,
            priority=5,
            sequence_id=1,
            event_id="evt_001",
            event_type=SimEventType.UNIT_ARRIVED,
            payload={"unit": "M1"},
            description="Unit M1 arrived",
        )
        d = e.to_dict()
        assert d["timestamp"] == 12.346
        assert d["event_id"] == "evt_001"
        assert d["event_type"] == "unit_arrived"
        assert d["payload"] == {"unit": "M1"}


# ---------------------------------------------------------------------------
# Vehicle State & Kinematics Tests
# ---------------------------------------------------------------------------


class TestVehicleSimState:
    def test_initial_state_properties(self) -> None:
        v = VehicleSimState(
            unit_id="MEDIC-1",
            apparatus_type=ApparatusType.AMBULANCE_ALS,
            station_id="STATION-1",
        )
        assert v.is_available is True
        assert v.is_en_route is False
        assert v.is_on_scene is False

    def test_coordinates_interpolation(self, grid_graph: Graph) -> None:
        v = VehicleSimState(
            unit_id="MEDIC-1",
            apparatus_type=ApparatusType.AMBULANCE_ALS,
            station_id="STATION-1",
            status=UnitStatus.EN_ROUTE,
        )
        # No tracker yet
        assert v.current_position_coords(grid_graph) is None

        # Dispatched on path A -> B -> D
        from emergency_intelligence.events.inflight import DispatchedVehicleTracker
        v.tracker = DispatchedVehicleTracker(
            unit_id="MEDIC-1",
            incident_id="INC-1",
            destination_node_id="D",
            path=["A", "B", "D"],
            progress_ratio=0.5,
        )

        # Midway between A (0, 1) and B (1, 2) => (0.5, 1.5)
        coords = v.current_position_coords(grid_graph)
        assert coords == (0.5, 1.5)

        # Arrived at D (2, 1)
        v.tracker.step_to_next_node()
        v.tracker.step_to_next_node()
        assert v.tracker.is_arrived is True
        assert v.current_position_coords(grid_graph) == (2.0, 1.0)

    def test_step_movement_partial_edge(self, grid_graph: Graph) -> None:
        from emergency_intelligence.events.inflight import DispatchedVehicleTracker
        v = VehicleSimState(
            unit_id="MEDIC-1",
            apparatus_type=ApparatusType.AMBULANCE_ALS,
            station_id="STATION-1",
            status=UnitStatus.EN_ROUTE,
            tracker=DispatchedVehicleTracker(
                unit_id="MEDIC-1",
                incident_id="INC-1",
                destination_node_id="D",
                path=["A", "B", "D"],
            ),
        )
        dview = DynamicGraphView(grid_graph)

        # Edge A -> B takes 10 seconds (100m)
        # Advance 4 seconds => 40% progress
        arrived = v.step_movement(4.0, grid_graph, dview)
        assert arrived is False
        assert pytest.approx(v.tracker.progress_ratio, 0.001) == 0.4
        assert pytest.approx(v.total_travel_time, 0.001) == 4.0
        assert pytest.approx(v.total_distance_meters, 0.001) == 40.0

    def test_step_movement_multi_edge_arrival(self, grid_graph: Graph) -> None:
        from emergency_intelligence.events.inflight import DispatchedVehicleTracker
        v = VehicleSimState(
            unit_id="MEDIC-1",
            apparatus_type=ApparatusType.AMBULANCE_ALS,
            station_id="STATION-1",
            status=UnitStatus.EN_ROUTE,
            tracker=DispatchedVehicleTracker(
                unit_id="MEDIC-1",
                incident_id="INC-1",
                destination_node_id="D",
                path=["A", "B", "D"],
            ),
        )
        dview = DynamicGraphView(grid_graph)

        # Path A -> B (10s, 100m) -> D (10s, 100m) = total 20s, 200m
        # Advance 25 seconds (overshoot)
        arrived = v.step_movement(25.0, grid_graph, dview)
        assert arrived is True
        assert v.tracker.is_arrived is True
        assert pytest.approx(v.total_travel_time, 0.001) == 20.0
        assert pytest.approx(v.total_distance_meters, 0.001) == 200.0

    def test_step_movement_blocked_road_halts_progress(self, grid_graph: Graph) -> None:
        from emergency_intelligence.events.inflight import DispatchedVehicleTracker
        v = VehicleSimState(
            unit_id="MEDIC-1",
            apparatus_type=ApparatusType.AMBULANCE_ALS,
            station_id="STATION-1",
            status=UnitStatus.EN_ROUTE,
            tracker=DispatchedVehicleTracker(
                unit_id="MEDIC-1",
                incident_id="INC-1",
                destination_node_id="D",
                path=["A", "B", "D"],
            ),
        )
        dview = DynamicGraphView(grid_graph)
        dview.apply_closure("A", "B", reason="Bridge collapse")

        # Edge is closed; movement should halt immediately
        arrived = v.step_movement(5.0, grid_graph, dview)
        assert arrived is False
        assert v.tracker.progress_ratio == 0.0
        assert v.total_travel_time == 0.0

    def test_to_dict_serialization(self) -> None:
        v = VehicleSimState(
            unit_id="ENGINE-1",
            apparatus_type=ApparatusType.FIRE_ENGINE,
            station_id="STATION-4",
            total_travel_time=120.5,
            total_distance_meters=1500.0,
            reroute_count=2,
        )
        d = v.to_dict()
        assert d["unit_id"] == "ENGINE-1"
        assert d["apparatus_type"] == "fire_engine"
        assert d["total_travel_time"] == 120.5
        assert d["reroute_count"] == 2


# ---------------------------------------------------------------------------
# DisasterSimEngine Tests
# ---------------------------------------------------------------------------


class TestDisasterSimEngine:
    def test_register_and_dispatch_vehicle(self, grid_graph: Graph) -> None:
        engine = DisasterSimEngine(grid_graph)
        vehicle = VehicleSimState(
            unit_id="MEDIC-1",
            apparatus_type=ApparatusType.AMBULANCE_ALS,
            station_id="STATION-1",
        )
        engine.add_vehicle(vehicle)

        assert "MEDIC-1" in engine.vehicles
        assert vehicle.is_available is True

        dispatched = engine.dispatch_vehicle("MEDIC-1", "INC-1", ["A", "B", "D"])
        assert dispatched is True
        assert vehicle.is_en_route is True
        assert vehicle.assigned_incident_id == "INC-1"
        assert vehicle.tracker is not None
        assert vehicle.tracker.path == ["A", "B", "D"]

    def test_dispatch_unknown_vehicle_raises(self, grid_graph: Graph) -> None:
        engine = DisasterSimEngine(grid_graph)
        with pytest.raises(KeyError, match="not found in simulation fleet"):
            engine.dispatch_vehicle("GHOST-1", "INC-1", ["A", "B"])

    def test_step_progress_and_arrival(self, grid_graph: Graph) -> None:
        engine = DisasterSimEngine(grid_graph)
        vehicle = VehicleSimState(
            unit_id="MEDIC-1",
            apparatus_type=ApparatusType.AMBULANCE_ALS,
            station_id="STATION-1",
        )
        engine.add_vehicle(vehicle)
        engine.dispatch_vehicle("MEDIC-1", "INC-1", ["A", "B", "D"])

        # Path duration is 20s. Step by 10s:
        events = engine.step(10.0)
        assert engine.clock.current_time == 10.0
        assert vehicle.is_en_route is True
        assert pytest.approx(vehicle.tracker.progress_ratio, 0.001) == 0.0
        assert vehicle.tracker.current_edge_index == 1  # reached node B

        # Step another 10s: arrives at D
        engine.step(10.0)
        assert engine.clock.current_time == 20.0
        assert vehicle.is_on_scene is True
        assert vehicle.arrival_time == 20.0

    def test_dynamic_road_closure_triggers_inflight_rerouting(self, grid_graph: Graph) -> None:
        """Tests that when road B -> D closes while unit is at B, unit automatically

        reroutes via detour A -> C -> D!
        """
        engine = DisasterSimEngine(grid_graph, auto_reroute=True)
        vehicle = VehicleSimState(
            unit_id="MEDIC-1",
            apparatus_type=ApparatusType.AMBULANCE_ALS,
            station_id="STATION-1",
        )
        engine.add_vehicle(vehicle)
        engine.dispatch_vehicle("MEDIC-1", "INC-1", ["A", "B", "D"])

        # Step 10 seconds: unit reaches node B
        engine.step(10.0)
        assert vehicle.tracker.current_tail_node == "B"

        # Now sever the road ahead (B -> D)
        engine.sever_road("B", "D", reason="Sinkhole opened")

        # Step next 1 second: engine processes closure, detects obstruction, and replans
        # Note: B has no other outgoing edges to D in our simple grid, so let's add bidirectional
        # or reverse edge B -> A so it can backtrack to C -> D:
        grid_graph.add_edge(Edge("B", "A", cost=10.0, attributes={"travel_time": 10.0, "distance": 100.0}))

        engine.step(1.0)

        # Vehicle should have replanned via B -> A -> C -> D
        assert vehicle.reroute_count >= 1
        assert "D" in vehicle.tracker.path
        assert not engine.dynamic_view.is_edge_blocked("A", "C")

    def test_hazard_spawn_closes_intersecting_edges(self, grid_graph: Graph) -> None:
        engine = DisasterSimEngine(grid_graph)
        # Polygon encompassing edge B (1, 2) -> D (2, 1)
        hazard = HazardPolygon(
            hazard_id="HAZ-1",
            hazard_type=HazardType.FLASH_FLOOD,
            severity=HazardSeverity.CRITICAL_BLOCKED,
            boundary_coordinates=[(0.8, 0.8), (2.2, 0.8), (2.2, 2.2), (0.8, 2.2)],
        )
        engine.spawn_hazard("HAZ-1", hazard)

        # Step clock to process hazard spawn
        engine.step(1.0)
        assert "HAZ-1" in engine.active_hazards
        # B -> D should now be blocked
        assert engine.dynamic_view.is_edge_blocked("B", "D")

    def test_road_reopen_event(self, grid_graph: Graph) -> None:
        engine = DisasterSimEngine(grid_graph)
        engine.sever_road("A", "B")
        engine.restore_road("A", "B", timestamp=50.0)

        engine.step(1.0)
        assert engine.dynamic_view.is_edge_blocked("A", "B")

        engine.step(50.0)
        assert not engine.dynamic_view.is_edge_blocked("A", "B")

    def test_custom_event_handler_callback(self, grid_graph: Graph) -> None:
        engine = DisasterSimEngine(grid_graph)
        called = []

        def on_incident(event: SimEvent, eng: DisasterSimEngine) -> None:
            called.append(event.payload.get("incident_id"))

        engine.register_handler(SimEventType.INCIDENT_DECLARED, on_incident)

        inc = Incident(
            incident_id="INC-99",
            emergency_type=EmergencyType.CARDIAC_ARREST,
            urgency=UrgencyLevel.PRIORITY_1_ECHO,
            coordinates=(2.0, 1.0),
            node_id="D",
            required_apparatus=[ApparatusType.AMBULANCE_ALS],
        )
        engine.schedule_incident(inc, report_time=5.0)

        engine.step(10.0)
        assert called == ["INC-99"]

    def test_run_until_idle(self, grid_graph: Graph) -> None:
        engine = DisasterSimEngine(grid_graph)
        vehicle = VehicleSimState(
            unit_id="MEDIC-1",
            apparatus_type=ApparatusType.AMBULANCE_ALS,
            station_id="STATION-1",
        )
        engine.add_vehicle(vehicle)
        engine.dispatch_vehicle("MEDIC-1", "INC-1", ["A", "B", "D"])

        summary = engine.run_until_idle(max_time=100.0, step_size=2.0)
        assert summary["units_arrived"] == 1
        assert summary["units_en_route"] == 0
        assert summary["current_time"] >= 20.0
        assert summary["total_travel_time"] == 20.0

    def test_summary_metrics(self, grid_graph: Graph) -> None:
        engine = DisasterSimEngine(grid_graph)
        summary = engine.summary()
        assert summary["current_time"] == 0.0
        assert summary["active_vehicles"] == 0
        assert summary["units_arrived"] == 0
        assert summary["pending_events"] == 0

    def test_invalid_step_size_raises(self, grid_graph: Graph) -> None:
        engine = DisasterSimEngine(grid_graph)
        with pytest.raises(ValueError, match="step_size must be positive"):
            engine.step(0.0)
        with pytest.raises(ValueError, match="step_size must be positive"):
            engine.step(-5.0)

    def test_run_until_target_time(self, grid_graph: Graph) -> None:
        engine = DisasterSimEngine(grid_graph)
        vehicle = VehicleSimState(
            unit_id="MEDIC-1",
            apparatus_type=ApparatusType.AMBULANCE_ALS,
            station_id="STATION-1",
        )
        engine.add_vehicle(vehicle)
        engine.dispatch_vehicle("MEDIC-1", "INC-1", ["A", "B", "D"])

        summary = engine.run_until(target_time=15.0, step_size=2.0)
        assert summary["current_time"] == 15.0
        assert vehicle.is_en_route is True

    def test_auto_reroute_disabled(self, grid_graph: Graph) -> None:
        engine = DisasterSimEngine(grid_graph, auto_reroute=False)
        vehicle = VehicleSimState(
            unit_id="MEDIC-1",
            apparatus_type=ApparatusType.AMBULANCE_ALS,
            station_id="STATION-1",
        )
        engine.add_vehicle(vehicle)
        engine.dispatch_vehicle("MEDIC-1", "INC-1", ["A", "B", "D"])

        engine.step(10.0)
        engine.sever_road("B", "D")
        engine.step(1.0)
        # Reroute was not triggered because auto_reroute is False
        assert vehicle.reroute_count == 0

    def test_auto_reroute_unreachable_destination(self, grid_graph: Graph) -> None:
        engine = DisasterSimEngine(grid_graph, auto_reroute=True)
        vehicle = VehicleSimState(
            unit_id="MEDIC-1",
            apparatus_type=ApparatusType.AMBULANCE_ALS,
            station_id="STATION-1",
        )
        engine.add_vehicle(vehicle)
        engine.dispatch_vehicle("MEDIC-1", "INC-1", ["A", "B", "D"])

        engine.step(10.0)
        # B has no other outgoing paths in grid_graph, so closing B -> D makes destination unreachable
        engine.sever_road("B", "D")
        engine.step(1.0)
        # Replan fails cleanly without raising, reroute_count remains 0
        assert vehicle.reroute_count == 0

    def test_coordinate_fallbacks_and_missing_nodes(self) -> None:
        g = Graph()
        g.add_node(Node("N1"))  # No coordinates
        g.add_node(Node("N2", coordinates=(5.0, 10.0)))
        g.add_edge(Edge("N1", "N2", cost=1.0))

        v = VehicleSimState(
            unit_id="U1",
            apparatus_type=ApparatusType.AMBULANCE_ALS,
            station_id="S1",
            status=UnitStatus.EN_ROUTE,
        )
        from emergency_intelligence.events.inflight import DispatchedVehicleTracker
        v.tracker = DispatchedVehicleTracker(
            unit_id="U1",
            incident_id="I1",
            destination_node_id="N2",
            path=["N1", "N2"],
        )
        # N1 has no coords, N2 has coords => fallback to N2 coords
        assert v.current_position_coords(g) == (5.0, 10.0)

    def test_movement_edge_cases(self, grid_graph: Graph) -> None:
        v = VehicleSimState(
            unit_id="U1",
            apparatus_type=ApparatusType.AMBULANCE_ALS,
            station_id="S1",
            status=UnitStatus.AVAILABLE,
        )
        dview = DynamicGraphView(grid_graph)
        # Not en route
        assert v.step_movement(5.0, grid_graph, dview) is False

        v.status = UnitStatus.EN_ROUTE
        from emergency_intelligence.events.inflight import DispatchedVehicleTracker
        v.tracker = DispatchedVehicleTracker(
            unit_id="U1",
            incident_id="I1",
            destination_node_id="D",
            path=["A", "B", "D"],
        )
        # Non-positive delta
        assert v.step_movement(0.0, grid_graph, dview) is False
        assert v.step_movement(-1.0, grid_graph, dview) is False

    def test_resolve_edge_metrics_defaults(self) -> None:
        # None edge
        time_res, dist_res = VehicleSimState._resolve_edge_metrics(None)
        assert time_res == 1.0
        assert dist_res == 10.0

        # Edge with length attribute
        e = Edge("X", "Y", cost=5.0, attributes={"length": 500.0})
        time_res, dist_res = VehicleSimState._resolve_edge_metrics(e)
        assert time_res == 5.0
        assert dist_res == 500.0
