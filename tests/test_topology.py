"""
Unit tests for graph topology hardening, degree-2 contraction, Tarjan's SCC,
and turn maneuver classification.
"""

import pytest

from emergency_intelligence.data import SAMPLE_HOSPITAL_DISTRICT_PATH, load_osm_graph_from_file
from emergency_intelligence.graph.dijkstra import dijkstra
from emergency_intelligence.graph.models import Edge, Graph, Node
from emergency_intelligence.graph.topology import (
    calculate_bearing,
    calculate_turn_angle,
    classify_turn_maneuver,
    contract_degree2_nodes,
    extract_largest_strongly_connected_component,
    tarjan_scc,
)


# ---------------------------------------------------------------------------
# 1. Geographic Azimuth Bearing & Turn Maneuver Tests
# ---------------------------------------------------------------------------


class TestBearingAndTurnClassification:
    def test_calculate_bearing_cardinal_directions(self):
        # Origin at (0, 0)
        p0 = (0.0, 0.0)
        p_north = (0.0, 1.0)
        p_east = (1.0, 0.0)
        p_south = (0.0, -1.0)
        p_west = (-1.0, 0.0)

        assert calculate_bearing(p0, p_north) == pytest.approx(0.0, abs=1e-3)
        assert calculate_bearing(p0, p_east) == pytest.approx(90.0, abs=1e-3)
        assert calculate_bearing(p0, p_south) == pytest.approx(180.0, abs=1e-3)
        assert calculate_bearing(p0, p_west) == pytest.approx(270.0, abs=1e-3)

    def test_calculate_turn_angle(self):
        # Traveling North (from (0, -1) to (0, 0))
        p_in = (0.0, -1.0)
        p_junction = (0.0, 0.0)

        # Continuing straight North
        p_straight = (0.0, 1.0)
        assert calculate_turn_angle(p_in, p_junction, p_straight) == pytest.approx(0.0, abs=1e-3)

        # Turning East (Right turn)
        p_right = (1.0, 0.0)
        assert calculate_turn_angle(p_in, p_junction, p_right) == pytest.approx(90.0, abs=1e-3)

        # Turning West (Left turn)
        p_left = (-1.0, 0.0)
        assert calculate_turn_angle(p_in, p_junction, p_left) == pytest.approx(-90.0, abs=1e-3)

        # Turning back South (U-turn)
        p_back = (0.0, -1.0)
        assert abs(calculate_turn_angle(p_in, p_junction, p_back)) == pytest.approx(180.0, abs=1e-3)

    def test_classify_turn_maneuver(self):
        assert classify_turn_maneuver(0.0) == "straight"
        assert classify_turn_maneuver(15.0) == "straight"
        assert classify_turn_maneuver(-15.0) == "straight"
        assert classify_turn_maneuver(30.0) == "slight_right"
        assert classify_turn_maneuver(90.0) == "right"
        assert classify_turn_maneuver(150.0) == "sharp_right"
        assert classify_turn_maneuver(-30.0) == "slight_left"
        assert classify_turn_maneuver(-90.0) == "left"
        assert classify_turn_maneuver(-150.0) == "sharp_left"
        assert classify_turn_maneuver(175.0) == "u_turn"
        assert classify_turn_maneuver(-175.0) == "u_turn"


# ---------------------------------------------------------------------------
# 2. Tarjan's Strongly Connected Components (SCC) Tests
# ---------------------------------------------------------------------------


class TestTarjanSCC:
    def test_empty_graph(self):
        g = Graph()
        assert tarjan_scc(g) == []
        assert extract_largest_strongly_connected_component(g).node_count() == 0

    def test_single_node(self):
        g = Graph()
        g.add_node(Node("A"))
        sccs = tarjan_scc(g)
        assert len(sccs) == 1
        assert sccs[0] == ["A"]

    def test_directed_cycle_is_single_scc(self):
        # A -> B -> C -> A
        g = Graph()
        for nid in ("A", "B", "C"):
            g.add_node(Node(nid))
        g.add_edge(Edge("A", "B", cost=1.0))
        g.add_edge(Edge("B", "C", cost=1.0))
        g.add_edge(Edge("C", "A", cost=1.0))

        sccs = tarjan_scc(g)
        assert len(sccs) == 1
        assert set(sccs[0]) == {"A", "B", "C"}

    def test_multi_component_graph(self):
        # Component 1: {A, B} mutually connected
        # Component 2: {C, D, E} mutually connected
        # Directed bridge: B -> C (cannot go back)
        g = Graph()
        for nid in ("A", "B", "C", "D", "E"):
            g.add_node(Node(nid))

        # C1
        g.add_edge(Edge("A", "B", cost=1.0))
        g.add_edge(Edge("B", "A", cost=1.0))

        # Bridge
        g.add_edge(Edge("B", "C", cost=2.0))

        # C2
        g.add_edge(Edge("C", "D", cost=1.0))
        g.add_edge(Edge("D", "E", cost=1.0))
        g.add_edge(Edge("E", "C", cost=1.0))

        sccs = tarjan_scc(g)
        assert len(sccs) == 2
        # C2 is size 3, C1 is size 2
        assert len(sccs[0]) == 3
        assert len(sccs[1]) == 2
        assert set(sccs[0]) == {"C", "D", "E"}
        assert set(sccs[1]) == {"A", "B"}

    def test_extract_largest_strongly_connected_component(self):
        g = Graph()
        for nid in ("A", "B", "C", "D"):
            g.add_node(Node(nid))

        # Triangle A <-> B <-> C <-> A (size 3)
        g.add_edge(Edge("A", "B", cost=1.0))
        g.add_edge(Edge("B", "A", cost=1.0))
        g.add_edge(Edge("B", "C", cost=1.0))
        g.add_edge(Edge("C", "B", cost=1.0))
        g.add_edge(Edge("C", "A", cost=1.0))
        g.add_edge(Edge("A", "C", cost=1.0))

        # Isolated dead-end island: D (size 1)
        g.add_edge(Edge("A", "D", cost=5.0))

        lscc = extract_largest_strongly_connected_component(g)
        assert lscc.node_count() == 3
        assert lscc.has_node("A")
        assert lscc.has_node("B")
        assert lscc.has_node("C")
        assert not lscc.has_node("D")


# ---------------------------------------------------------------------------
# 3. Degree-2 Node Contraction Tests
# ---------------------------------------------------------------------------


class TestDegree2Contraction:
    def test_oneway_chain_contraction(self):
        # A -> B -> C (B is degree 2)
        g = Graph()
        g.add_node(Node("A", coordinates=(0.0, 0.0)))
        g.add_node(Node("B", coordinates=(0.0, 1.0)))
        g.add_node(Node("C", coordinates=(0.0, 2.0)))

        g.add_edge(Edge("A", "B", cost=10.0, attributes={"distance_m": 10.0, "travel_time_s": 1.0}))
        g.add_edge(Edge("B", "C", cost=15.0, attributes={"distance_m": 15.0, "travel_time_s": 1.5}))

        contracted = contract_degree2_nodes(g)

        assert contracted.node_count() == 2
        assert not contracted.has_node("B")
        assert contracted.has_edge("A", "C")

        edge_ac = contracted.get_neighbors("A")[0]
        assert edge_ac.destination_id == "C"
        assert edge_ac.cost == 25.0
        assert edge_ac.attributes["distance_m"] == 25.0
        assert edge_ac.attributes["travel_time_s"] == 2.5
        # Stitched geometry should contain A, B, C
        assert edge_ac.attributes["geometry"] == [(0.0, 0.0), (0.0, 1.0), (0.0, 2.0)]

    def test_bidirectional_chain_contraction(self):
        # A <-> B <-> C
        g = Graph()
        g.add_node(Node("A", coordinates=(0.0, 0.0)))
        g.add_node(Node("B", coordinates=(1.0, 0.0)))
        g.add_node(Node("C", coordinates=(2.0, 0.0)))

        g.add_edge(Edge("A", "B", cost=5.0))
        g.add_edge(Edge("B", "A", cost=5.0))
        g.add_edge(Edge("B", "C", cost=8.0))
        g.add_edge(Edge("C", "B", cost=8.0))

        contracted = contract_degree2_nodes(g)
        assert contracted.node_count() == 2
        assert not contracted.has_node("B")
        assert contracted.has_edge("A", "C")
        assert contracted.has_edge("C", "A")

        assert contracted.get_neighbors("A")[0].cost == 13.0
        assert contracted.get_neighbors("C")[0].cost == 13.0

    def test_long_multi_node_chain_collapse(self):
        # A <-> B <-> C <-> D <-> E (3 intermediate nodes)
        g = Graph()
        nodes = ["A", "B", "C", "D", "E"]
        for i, nid in enumerate(nodes):
            g.add_node(Node(nid, coordinates=(float(i), 0.0)))

        for i in range(len(nodes) - 1):
            u = nodes[i]
            v = nodes[i + 1]
            g.add_edge(Edge(u, v, cost=2.0))
            g.add_edge(Edge(v, u, cost=2.0))

        contracted = contract_degree2_nodes(g)
        assert contracted.node_count() == 2
        assert set(contracted.node_ids()) == {"A", "E"}
        assert contracted.get_neighbors("A")[0].cost == 8.0
        assert len(contracted.get_neighbors("A")[0].attributes["geometry"]) == 5

    def test_protected_node_not_contracted(self):
        # A <-> B <-> C <-> D, where B is protected
        g = Graph()
        for i, nid in enumerate(["A", "B", "C", "D"]):
            g.add_node(Node(nid, coordinates=(float(i), 0.0)))

        for i in range(3):
            u, v = ["A", "B", "C", "D"][i], ["A", "B", "C", "D"][i + 1]
            g.add_edge(Edge(u, v, cost=1.0))
            g.add_edge(Edge(v, u, cost=1.0))

        # Protect node B
        contracted = contract_degree2_nodes(g, protected_node_ids={"B"})
        # Node C is contracted into B <-> D, but B remains
        assert contracted.node_count() == 3
        assert contracted.has_node("A")
        assert contracted.has_node("B")
        assert contracted.has_node("D")
        assert not contracted.has_node("C")

    def test_intersections_and_dead_ends_preserved(self):
        # T-junction: T connected to North, East, South, West
        g = Graph()
        g.add_node(Node("T"))
        for nid in ("N", "E", "S", "W"):
            g.add_node(Node(nid))
            g.add_edge(Edge("T", nid, cost=1.0))
            g.add_edge(Edge(nid, "T", cost=1.0))

        contracted = contract_degree2_nodes(g)
        # All 5 nodes preserved: T is degree 4 (intersection), others are dead ends
        assert contracted.node_count() == 5


# ---------------------------------------------------------------------------
# 4. OSM Ingestion with Contraction & LSCC Integration
# ---------------------------------------------------------------------------


class TestOSMTopologyIntegration:
    def test_load_sample_hospital_district_with_lscc_and_contraction(self):
        # Baseline raw graph
        raw_graph = load_osm_graph_from_file(SAMPLE_HOSPITAL_DISTRICT_PATH)
        assert raw_graph.node_count() == 11

        # Ingestion with LSCC extraction
        lscc_graph = load_osm_graph_from_file(
            SAMPLE_HOSPITAL_DISTRICT_PATH,
            extract_lscc=True,
        )
        assert lscc_graph.node_count() <= raw_graph.node_count()
        assert lscc_graph.has_node("1001")
        assert lscc_graph.has_node("1008")

        # Ingestion with topology simplification (contraction)
        contracted_graph = load_osm_graph_from_file(
            SAMPLE_HOSPITAL_DISTRICT_PATH,
            simplify_topology=True,
            protected_node_ids={"1001", "1008"},
        )
        # Critical origin and destination are protected
        assert contracted_graph.has_node("1001")
        assert contracted_graph.has_node("1008")

        # Routing between protected origin and destination is preserved
        raw_res = dijkstra(raw_graph, "1001", "1008")
        cont_res = dijkstra(contracted_graph, "1001", "1008")

        assert raw_res.reachable is True
        assert cont_res.reachable is True
        assert raw_res.total_cost == pytest.approx(cont_res.total_cost, rel=1e-4)
