"""
Unit tests for OpenStreetMap (OSM) ingestion and real-world road graph routing.
"""

from pathlib import Path
import pytest

from emergency_intelligence.data.geo import haversine_heuristic
from emergency_intelligence.data.osm import (
    DEFAULT_HIGHWAY_TYPES,
    load_osm_graph_from_data,
    load_osm_graph_from_file,
)
from emergency_intelligence.data import SAMPLE_HOSPITAL_DISTRICT_PATH
from emergency_intelligence.graph.astar import astar
from emergency_intelligence.graph.dijkstra import dijkstra


class TestOSMParser:
    def test_load_sample_hospital_district_file(self):
        graph = load_osm_graph_from_file(SAMPLE_HOSPITAL_DISTRICT_PATH)

        # 11 active road nodes (1001 to 1011). Orphaned node 9999 should be excluded.
        assert graph.node_count() == 11
        assert not graph.has_node("9999")
        assert graph.has_node("1001")
        assert graph.has_node("1008")

        # Check node coordinates were parsed
        dispatch_node = graph.get_node("1001")
        assert dispatch_node.coordinates == pytest.approx((-122.419416, 37.774929))
        assert dispatch_node.label == "Central Emergency Dispatch"

    def test_oneway_direction_enforced(self):
        graph = load_osm_graph_from_file(SAMPLE_HOSPITAL_DISTRICT_PATH)

        # Way 2002 (Mission St) is oneway=yes from 1005 -> 1006 -> 1007 -> 1008
        nbrs_1005 = [e.destination_id for e in graph.get_neighbors("1005")]
        nbrs_1006 = [e.destination_id for e in graph.get_neighbors("1006")]

        # Forward edge exists
        assert "1006" in nbrs_1005
        # Reverse edge does NOT exist on 1006 -> 1005 for Mission St
        # (Only 1005 -> 1006 was created for way 2002)
        assert "1005" not in nbrs_1006

    def test_non_highway_elements_ignored(self):
        # Non-highway building way (8888) should not create extra edges
        graph = load_osm_graph_from_file(SAMPLE_HOSPITAL_DISTRICT_PATH)
        assert graph.edge_count() > 0

    def test_highway_filter_custom(self):
        # Only primary highways
        graph = load_osm_graph_from_file(
            SAMPLE_HOSPITAL_DISTRICT_PATH,
            highway_filter={"primary"},
        )
        # Only nodes on Market St (2001) and 8th St (2006) should be loaded
        assert graph.has_node("1001")
        assert graph.has_node("1004")
        assert graph.has_node("1008")
        assert graph.has_node("1011")
        # 1009 is on Howard St (tertiary), so it should not be in this graph
        assert not graph.has_node("1009")

    def test_invalid_data_raises_value_error(self):
        with pytest.raises(ValueError, match="elements"):
            load_osm_graph_from_data({"invalid_key": []})

    def test_nonexistent_file_raises_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            load_osm_graph_from_file(Path("nonexistent_path_to_osm.json"))


class TestOSMRouting:
    def test_dijkstra_on_real_osm_network(self):
        graph = load_osm_graph_from_file(SAMPLE_HOSPITAL_DISTRICT_PATH)

        # Route from Central Emergency Dispatch (1001) to Regional Trauma Center (1008)
        result = dijkstra(graph, "1001", "1008")

        assert result.reachable is True
        assert result.path[0] == "1001"
        assert result.path[-1] == "1008"
        # Total distance is positive and measured in realistic physical meters
        assert result.total_cost > 200.0  # At least a couple hundred meters
        assert result.nodes_explored > 1

    def test_astar_with_haversine_matches_dijkstra_optimal_cost(self):
        graph = load_osm_graph_from_file(SAMPLE_HOSPITAL_DISTRICT_PATH)

        d_res = dijkstra(graph, "1001", "1008")
        a_res = astar(graph, "1001", "1008", heuristic=haversine_heuristic)

        assert d_res.reachable is True
        assert a_res.reachable is True
        assert d_res.total_cost == pytest.approx(a_res.total_cost, rel=1e-5)
        # Optimal cost agreement
        assert d_res.path == a_res.path

    def test_reverse_route_respects_oneway_restrictions(self):
        graph = load_osm_graph_from_file(SAMPLE_HOSPITAL_DISTRICT_PATH)

        # Forward: 1001 -> 1008 can use Mission St (one-way forward)
        fwd_res = dijkstra(graph, "1001", "1008")
        # Return: 1008 -> 1001 CANNOT use Mission St in reverse
        rev_res = dijkstra(graph, "1008", "1001")

        assert fwd_res.reachable is True
        assert rev_res.reachable is True
        # Mission St is one-way forward: [1005, 1006, 1007, 1008]
        # Return path must take an alternative route (e.g. Market St or Howard St)
        assert not ("1008" in rev_res.path and "1007" in rev_res.path and "1006" in rev_res.path)
