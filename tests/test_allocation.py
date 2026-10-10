"""
Unit Test Suite for Emergency Fleet Allocation & Apparatus Matching Subsystem.
==============================================================================
Validates multi-source catchment area Voronoi partitioning, isochrone travel
time frontiers, ETA matrix computations, fleet management, and multi-apparatus
dispatch allocation under standard and dynamic disaster conditions.
"""

from __future__ import annotations

import math
import pytest

from emergency_intelligence.allocation.catchment import (
    compute_eta_matrix,
    compute_isochrone_frontiers,
    compute_multi_source_catchment,
    find_closest_depot,
)
from emergency_intelligence.allocation.matcher import (
    FleetManager,
    allocate_fleet_for_incident,
    rank_units_for_incident,
)
from emergency_intelligence.allocation.models import (
    CatchmentPartition,
    DispatchAssignment,
    DispatchPlan,
    EmergencyStation,
    EmergencyUnit,
    ETARecord,
    UnitStatus,
)
from emergency_intelligence.events.incidents import (
    ApparatusType,
    EmergencyType,
    Incident,
    UrgencyLevel,
)
from emergency_intelligence.events.mutations import DynamicGraphView
from emergency_intelligence.graph.models import Edge, Graph, Node


@pytest.fixture
def test_network() -> Graph:
    """Creates a deterministic diamond/grid emergency test network with coordinates.

    Nodes:
      - 10: Station West (-122.420, 37.780)
      - 20: Station East (-122.400, 37.780)
      - 1: North Jct     (-122.410, 37.785)
      - 2: Center Jct    (-122.410, 37.780)
      - 3: South Jct     (-122.410, 37.775)
      - 99: Isolated Jct (-122.450, 37.750)
    """
    g = Graph()
    g.add_node(Node("10", coordinates=[-122.420, 37.780], label="Station West"))
    g.add_node(Node("20", coordinates=[-122.400, 37.780], label="Station East"))
    g.add_node(Node("1", coordinates=[-122.410, 37.785], label="North Jct"))
    g.add_node(Node("2", coordinates=[-122.410, 37.780], label="Center Jct"))
    g.add_node(Node("3", coordinates=[-122.410, 37.775], label="South Jct"))
    g.add_node(Node("99", coordinates=[-122.450, 37.750], label="Isolated Node"))

    def add_bidir(u: str, v: str, cost: float, dist: float) -> None:
        g.add_edge(Edge(u, v, cost=cost, attributes={"distance": dist}))
        g.add_edge(Edge(v, u, cost=cost, attributes={"distance": dist}))

    # Connections from Station West (10)
    add_bidir("10", "1", 10.0, 800.0)
    add_bidir("10", "2", 15.0, 900.0)
    add_bidir("10", "3", 25.0, 1200.0)

    # Connections from Station East (20)
    add_bidir("20", "1", 25.0, 1200.0)
    add_bidir("20", "2", 15.0, 900.0)
    add_bidir("20", "3", 10.0, 800.0)

    # Center interconnects
    add_bidir("1", "2", 5.0, 400.0)
    add_bidir("2", "3", 5.0, 400.0)

    return g


# ---------------------------------------------------------------------------
# Domain Model Tests
# ---------------------------------------------------------------------------

class TestAllocationModels:
    def test_emergency_unit_initialization_and_validation(self) -> None:
        unit = EmergencyUnit(
            unit_id="MEDIC-1",
            apparatus_type=ApparatusType.AMBULANCE_ALS,
            current_node_id="10",
            station_id="STN-WEST",
            speed_factor=1.1,
            capabilities={"cardiac", "als"},
        )
        assert unit.unit_id == "MEDIC-1"
        assert unit.is_available()
        assert unit.speed_factor == 1.1

        # Errors
        with pytest.raises(ValueError, match="unit_id cannot be empty"):
            EmergencyUnit(unit_id="", apparatus_type=ApparatusType.AMBULANCE_ALS, current_node_id="10")

        with pytest.raises(ValueError, match="current_node_id cannot be empty"):
            EmergencyUnit(unit_id="U1", apparatus_type=ApparatusType.AMBULANCE_ALS, current_node_id="")

        with pytest.raises(ValueError, match="speed_factor must be positive"):
            EmergencyUnit(unit_id="U1", apparatus_type=ApparatusType.AMBULANCE_ALS, current_node_id="10", speed_factor=0.0)

        with pytest.raises(TypeError):
            EmergencyUnit(unit_id="U1", apparatus_type=123, current_node_id="10")  # type: ignore

        with pytest.raises(TypeError):
            EmergencyUnit(unit_id="U1", apparatus_type=ApparatusType.AMBULANCE_ALS, current_node_id="10", status=456)  # type: ignore

    def test_emergency_unit_methods_and_serialization(self) -> None:
        unit = EmergencyUnit(
            unit_id="ENG-1",
            apparatus_type="fire_engine",  # type: ignore
            current_node_id="10",
        )
        assert unit.apparatus_type == ApparatusType.FIRE_ENGINE
        assert unit.is_available()

        unit.update_location("2")
        assert unit.current_node_id == "2"
        with pytest.raises(ValueError):
            unit.update_location("")

        unit.set_status(UnitStatus.DISPATCHED)
        assert not unit.is_available()
        assert unit.status == UnitStatus.DISPATCHED

        unit.set_status("en_route")  # type: ignore
        assert unit.status == UnitStatus.EN_ROUTE

        data = unit.to_dict()
        assert data["unit_id"] == "ENG-1"
        assert data["status"] == "en_route"

        reconstructed = EmergencyUnit.from_dict(data)
        assert reconstructed.unit_id == unit.unit_id
        assert reconstructed.apparatus_type == ApparatusType.FIRE_ENGINE
        assert reconstructed.current_node_id == "2"

    def test_emergency_station_model(self) -> None:
        stn = EmergencyStation(
            station_id="STN-1",
            name="Station One",
            node_id="10",
            assigned_unit_ids=["MEDIC-1"],
        )
        assert stn.station_id == "STN-1"
        data = stn.to_dict()
        assert data["name"] == "Station One"

        reconstructed = EmergencyStation.from_dict(data)
        assert reconstructed.station_id == "STN-1"
        assert reconstructed.assigned_unit_ids == ["MEDIC-1"]

        with pytest.raises(ValueError):
            EmergencyStation(station_id="", name="Bad", node_id="10")
        with pytest.raises(ValueError):
            EmergencyStation(station_id="S", name="Bad", node_id="")

    def test_eta_record_serialization(self) -> None:
        eta = ETARecord(
            unit_id="MEDIC-1",
            apparatus_type=ApparatusType.AMBULANCE_ALS,
            origin_node_id="10",
            destination_node_id="2",
            travel_time_seconds=15.0,
            distance_meters=900.0,
            path=["10", "2"],
            reachable=True,
        )
        d = eta.to_dict()
        assert d["travel_time_seconds"] == 15.0
        assert d["reachable"] is True

    def test_catchment_partition_methods(self) -> None:
        part = CatchmentPartition(
            depot_node_ids=["10", "20"],
            node_to_depot={"10": "10", "1": "10", "2": "10", "20": "20", "3": "20"},
            node_to_cost={"10": 0.0, "1": 10.0, "2": 15.0, "20": 0.0, "3": 10.0},
            depot_catchment_nodes={"10": ["1", "2", "10"], "20": ["20", "3"]},
        )
        assert part.get_assigned_depot("1") == "10"
        assert part.get_assigned_depot("3") == "20"
        assert part.get_assigned_depot("unknown") is None

        assert part.get_travel_cost("1") == 10.0
        assert math.isinf(part.get_travel_cost("unknown"))

        assert set(part.get_catchment("10")) == {"1", "2", "10"}
        assert part.get_catchment("nonexistent") == []

        frontier = part.get_isochrone_frontier("10", max_seconds=12.0)
        assert set(frontier) == {"10", "1"}

        d = part.to_dict()
        assert len(d["depot_node_ids"]) == 2

    def test_dispatch_plan_properties(self) -> None:
        unit1 = EmergencyUnit("M1", ApparatusType.AMBULANCE_ALS, "10")
        eta1 = ETARecord("M1", ApparatusType.AMBULANCE_ALS, "10", "2", 15.0, 900.0, ["10", "2"], True)
        assign1 = DispatchAssignment("INC-1", ApparatusType.AMBULANCE_ALS, unit1, eta1, True)

        unit2 = EmergencyUnit("E1", ApparatusType.FIRE_ENGINE, "20")
        eta2 = ETARecord("E1", ApparatusType.FIRE_ENGINE, "20", "2", 25.0, 1500.0, ["20", "2"], True)
        assign2 = DispatchAssignment("INC-1", ApparatusType.FIRE_ENGINE, unit2, eta2, True)

        plan = DispatchPlan(plan_id="P1", incident_id="INC-1", assignments=[assign1, assign2])
        assert plan.all_fulfilled is True
        assert plan.max_eta_seconds == 25.0
        assert plan.average_eta_seconds == 20.0
        assert plan.unfulfilled_requirements == []

        d = plan.to_dict()
        assert d["all_fulfilled"] is True
        assert d["max_eta_seconds"] == 25.0

        # Unfulfilled scenario
        assign3 = DispatchAssignment("INC-1", ApparatusType.LADDER_TRUCK, None, None, False)
        plan_partial = DispatchPlan(plan_id="P2", incident_id="INC-1", assignments=[assign1, assign3])
        assert not plan_partial.all_fulfilled
        assert plan_partial.unfulfilled_requirements == [ApparatusType.LADDER_TRUCK]


# ---------------------------------------------------------------------------
# Catchment & Isochrone Engine Tests
# ---------------------------------------------------------------------------

class TestCatchmentEngine:
    def test_multi_source_catchment_basic(self, test_network: Graph) -> None:
        partition = compute_multi_source_catchment(test_network, ["10", "20"])
        # Node 1 is closer to 10 (cost 10) than 20 (cost 20 via 2 or 25 direct)
        assert partition.get_assigned_depot("1") == "10"
        # Node 3 is closer to 20 (cost 10) than 10 (cost 20 via 2 or 25 direct)
        assert partition.get_assigned_depot("3") == "20"
        # Node 2 is equidistant (cost 15 from 10, cost 15 from 20) -> tie broken
        assert partition.get_assigned_depot("2") in ("10", "20")
        assert partition.get_travel_cost("2") == 15.0

    def test_multi_source_catchment_empty_and_invalid(self, test_network: Graph) -> None:
        # Empty depots
        part_empty = compute_multi_source_catchment(test_network, [])
        assert part_empty.depot_node_ids == []

        # Depots not in graph
        part_invalid = compute_multi_source_catchment(test_network, ["UNKNOWN_1", "UNKNOWN_2"])
        assert part_invalid.node_to_depot == {}

    def test_multi_source_catchment_max_cost(self, test_network: Graph) -> None:
        # Limit to max cost 12 seconds
        part = compute_multi_source_catchment(test_network, ["10", "20"], max_cost=12.0)
        # Node 1 (cost 10) and Node 3 (cost 10) are reachable
        assert part.get_assigned_depot("1") == "10"
        assert part.get_assigned_depot("3") == "20"
        # Node 2 (cost 15) must not be reached
        assert part.get_assigned_depot("2") is None

    def test_multi_source_catchment_with_dynamic_graph_view(self, test_network: Graph) -> None:
        view = DynamicGraphView(test_network)
        # Close edge 10 <-> 1 completely
        view.apply_closure("10", "1", bidirectional=True)

        partition = compute_multi_source_catchment(view, ["10", "20"])
        # Now station 10 can only reach 1 via 2 (cost 15 + 5 = 20)
        # Station 20 reaches 1 via 2 (cost 15 + 5 = 20) or 25 direct
        # Node 1 travel time from 10 increased from 10s to 20s
        assert partition.get_travel_cost("1") == 20.0

    def test_isochrone_frontiers(self, test_network: Graph) -> None:
        isochrones = compute_isochrone_frontiers(test_network, "10", [10.0, 20.0, 30.0])
        assert 10.0 in isochrones
        assert 20.0 in isochrones
        assert 30.0 in isochrones

        # At 10s: 10 (cost 0) and 1 (cost 10)
        assert set(isochrones[10.0]) == {"10", "1"}
        # At 20s: 10, 1, 2 (cost 15), 3 (cost 20 via 2)
        assert "2" in isochrones[20.0]
        assert "3" in isochrones[20.0]

        # Key error on invalid origin
        with pytest.raises(KeyError):
            compute_isochrone_frontiers(test_network, "INVALID_ORIGIN", [10.0])

        # Empty cutoffs
        assert compute_isochrone_frontiers(test_network, "10", []) == {}

    def test_compute_eta_matrix(self, test_network: Graph) -> None:
        matrix = compute_eta_matrix(test_network, ["10", "20"], ["1", "2", "3", "99"])
        assert matrix[("10", "1")] == 10.0
        assert matrix[("10", "2")] == 15.0
        assert matrix[("20", "3")] == 10.0
        assert matrix[("20", "2")] == 15.0
        # Node 99 is isolated
        assert math.isinf(matrix[("10", "99")])

        # Nonexistent source
        bad_matrix = compute_eta_matrix(test_network, ["BAD_SRC"], ["1"])
        assert math.isinf(bad_matrix[("BAD_SRC", "1")])

    def test_find_closest_depot(self, test_network: Graph) -> None:
        closest_1 = find_closest_depot(test_network, "1", ["10", "20"])
        assert closest_1 is not None
        assert closest_1[0] == "10"
        assert closest_1[1] == 10.0

        closest_3 = find_closest_depot(test_network, "3", ["10", "20"])
        assert closest_3 is not None
        assert closest_3[0] == "20"
        assert closest_3[1] == 10.0

        # Unreachable isolated node
        closest_iso = find_closest_depot(test_network, "99", ["10", "20"])
        assert closest_iso is None

        # Invalid target or empty depots
        assert find_closest_depot(test_network, "BAD_TARGET", ["10"]) is None
        assert find_closest_depot(test_network, "1", []) is None


# ---------------------------------------------------------------------------
# Fleet Matcher & Dispatch Allocation Tests
# ---------------------------------------------------------------------------

class TestFleetMatcher:
    def test_fleet_manager_registration_and_queries(self) -> None:
        fleet = FleetManager()
        stn_w = EmergencyStation("STN-W", "West Station", "10")
        stn_e = EmergencyStation("STN-E", "East Station", "20")
        fleet.register_station(stn_w)
        fleet.register_station(stn_e)

        u1 = EmergencyUnit("M-1", ApparatusType.AMBULANCE_ALS, "10", station_id="STN-W", capabilities={"cardiac"})
        u2 = EmergencyUnit("M-2", ApparatusType.AMBULANCE_BLS, "20", station_id="STN-E")
        u3 = EmergencyUnit("ENG-1", ApparatusType.FIRE_ENGINE, "10", station_id="STN-W")
        fleet.register_unit(u1)
        fleet.register_unit(u2)
        fleet.register_unit(u3)

        assert fleet.get_unit("M-1") is u1
        assert fleet.get_station("STN-W") is stn_w
        assert "M-1" in stn_w.assigned_unit_ids

        # Type checks
        with pytest.raises(TypeError):
            fleet.register_station("not_a_station")  # type: ignore
        with pytest.raises(TypeError):
            fleet.register_unit("not_a_unit")  # type: ignore

        # List units
        all_medics = fleet.list_units(apparatus_type=ApparatusType.AMBULANCE_ALS)
        assert len(all_medics) == 1
        assert all_medics[0].unit_id == "M-1"

        # Capabilities filter
        cardiac_medics = fleet.get_available_units(
            apparatus_type=ApparatusType.AMBULANCE_ALS,
            required_capabilities={"cardiac"},
        )
        assert len(cardiac_medics) == 1
        empty_pediatric = fleet.get_available_units(
            apparatus_type=ApparatusType.AMBULANCE_ALS,
            required_capabilities={"pediatric"},
        )
        assert len(empty_pediatric) == 0

        # Dispatch and release
        assert fleet.dispatch_unit("M-1", "INC-99") is True
        assert u1.status == UnitStatus.DISPATCHED
        assert fleet.dispatch_unit("M-1", "INC-99") is False  # already dispatched

        assert fleet.release_unit("M-1", new_node_id="2") is True
        assert u1.status == UnitStatus.AVAILABLE
        assert u1.current_node_id == "2"

        assert fleet.release_unit("UNKNOWN_ID") is False

        # Serialization round-trip
        data = fleet.to_dict()
        reconstructed = FleetManager.from_dict(data)
        assert reconstructed.get_unit("M-1") is not None
        assert reconstructed.get_station("STN-W") is not None

    def test_rank_units_for_incident(self, test_network: Graph) -> None:
        u_west = EmergencyUnit("M-WEST", ApparatusType.AMBULANCE_ALS, "10", speed_factor=1.0)
        u_east = EmergencyUnit("M-EAST", ApparatusType.AMBULANCE_ALS, "20", speed_factor=1.0)
        u_heavy = EmergencyUnit("ENG-WEST", ApparatusType.FIRE_ENGINE, "10", speed_factor=0.5)

        # Incident at Node 1 (closer to West: distance cost 10s vs East: 20s)
        ranked = rank_units_for_incident(test_network, "1", [u_west, u_east, u_heavy])
        assert len(ranked) == 3
        # M-WEST should arrive first (10s / 1.0 = 10s)
        assert ranked[0].unit_id == "M-WEST"
        assert ranked[0].travel_time_seconds == 10.0

        # ENG-WEST travel time is 10s / 0.5 = 20.0s (slower vehicle)
        # M-EAST travel time is 20s / 1.0 = 20.0s
        assert ranked[1].travel_time_seconds == 20.0

        # Handle unit at invalid node
        u_invalid = EmergencyUnit("M-BAD", ApparatusType.AMBULANCE_ALS, "NON_EXISTENT")
        ranked_bad = rank_units_for_incident(test_network, "1", [u_invalid])
        assert not ranked_bad[0].reachable
        assert math.isinf(ranked_bad[0].travel_time_seconds)

        # Handle isolated node destination
        ranked_iso = rank_units_for_incident(test_network, "99", [u_west])
        assert not ranked_iso[0].reachable

    def test_allocate_fleet_multi_apparatus(self, test_network: Graph) -> None:
        fleet = FleetManager()
        u_als1 = EmergencyUnit("M-1", ApparatusType.AMBULANCE_ALS, "10")
        u_als2 = EmergencyUnit("M-2", ApparatusType.AMBULANCE_ALS, "20")
        u_eng1 = EmergencyUnit("ENG-1", ApparatusType.FIRE_ENGINE, "10")
        u_lad1 = EmergencyUnit("LAD-1", ApparatusType.LADDER_TRUCK, "20")

        fleet.register_unit(u_als1)
        fleet.register_unit(u_als2)
        fleet.register_unit(u_eng1)
        fleet.register_unit(u_lad1)

        # Structure fire incident at Node 1 requiring ALS, Engine, and Ladder
        inc = Incident(
            incident_id="INC-FIRE-101",
            emergency_type=EmergencyType.STRUCTURE_FIRE,
            urgency=UrgencyLevel.PRIORITY_1_ECHO,
            coordinates=(-122.410, 37.785),
            node_id="1",
            required_apparatus=[
                ApparatusType.AMBULANCE_ALS,
                ApparatusType.FIRE_ENGINE,
                ApparatusType.LADDER_TRUCK,
            ],
        )

        plan = allocate_fleet_for_incident(test_network, inc, fleet, auto_dispatch=True)
        assert plan.all_fulfilled is True
        assert len(plan.assignments) == 3

        # Verify auto-dispatch applied
        assert u_als1.status == UnitStatus.DISPATCHED
        assert u_eng1.status == UnitStatus.DISPATCHED
        assert u_lad1.status == UnitStatus.DISPATCHED

        # M-1 (West) should be selected for Node 1 over M-2 (East)
        als_assign = next(a for a in plan.assignments if a.required_type == ApparatusType.AMBULANCE_ALS)
        assert als_assign.assigned_unit.unit_id == "M-1"

    def test_allocate_fleet_partial_and_unfulfilled(self, test_network: Graph) -> None:
        fleet = FleetManager()
        # Only 1 engine available
        u_eng = EmergencyUnit("ENG-1", ApparatusType.FIRE_ENGINE, "10")
        fleet.register_unit(u_eng)

        # Incident requiring 2 engines and 1 hazmat
        inc = Incident(
            incident_id="INC-HAZMAT-1",
            emergency_type=EmergencyType.HAZMAT_SPILL,
            urgency=UrgencyLevel.PRIORITY_2_DELTA,
            coordinates=(-122.410, 37.780),
            node_id="2",
            required_apparatus=[
                ApparatusType.FIRE_ENGINE,
                ApparatusType.FIRE_ENGINE,
                ApparatusType.HAZMAT_UNIT,
            ],
        )

        plan = allocate_fleet_for_incident(test_network, inc, fleet)
        assert not plan.all_fulfilled
        # 1st engine fulfilled, 2nd engine unfulfilled (none left), hazmat unfulfilled
        assert plan.assignments[0].fulfilled is True
        assert plan.assignments[1].fulfilled is False
        assert plan.assignments[2].fulfilled is False
        assert plan.unfulfilled_requirements == [ApparatusType.FIRE_ENGINE, ApparatusType.HAZMAT_UNIT]

    def test_allocate_fleet_with_dynamic_closures(self, test_network: Graph) -> None:
        view = DynamicGraphView(test_network)
        fleet = FleetManager()
        u_als_west = EmergencyUnit("M-WEST", ApparatusType.AMBULANCE_ALS, "10")
        u_als_east = EmergencyUnit("M-EAST", ApparatusType.AMBULANCE_ALS, "20")
        fleet.register_unit(u_als_west)
        fleet.register_unit(u_als_east)

        # Incident at Node 1
        inc = Incident(
            incident_id="INC-1",
            emergency_type=EmergencyType.MEDICAL_GENERAL,
            urgency=UrgencyLevel.PRIORITY_2_DELTA,
            coordinates=(-122.410, 37.785),
            node_id="1",
            required_apparatus=[ApparatusType.AMBULANCE_ALS],
        )

        # Baseline: West is chosen (cost 10s vs East 20s)
        plan1 = allocate_fleet_for_incident(view, inc, fleet)
        assert plan1.assignments[0].assigned_unit.unit_id == "M-WEST"
        assert plan1.assignments[0].eta_record.travel_time_seconds == 10.0

        # Close all access from West: close 10 <-> 1, 10 <-> 2, 10 <-> 3
        view.apply_closure("10", "1", bidirectional=True)
        view.apply_closure("10", "2", bidirectional=True)
        view.apply_closure("10", "3", bidirectional=True)

        # Re-allocate: West is now cut off! East should be selected automatically
        plan2 = allocate_fleet_for_incident(view, inc, fleet)
        assert plan2.assignments[0].assigned_unit.unit_id == "M-EAST"
        assert plan2.assignments[0].eta_record.travel_time_seconds == 20.0
