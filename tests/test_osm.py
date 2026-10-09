"""
Unit tests for OpenStreetMap (OSM) ingestion, dynamic speed limit parsing,
multi-criteria cost weighting profiles, and streaming XML ingestion.
"""

import io
from pathlib import Path
import pytest

from emergency_intelligence.data.geo import haversine_heuristic
from emergency_intelligence.data.osm import (
    DEFAULT_HIGHWAY_TYPES,
    DEFAULT_SPEEDS_KMH,
    EMERGENCY_SPEED_FACTORS,
    WeightingProfile,
    is_way_accessible,
    load_osm_graph_from_data,
    load_osm_graph_from_file,
    load_osm_graph_from_xml_file,
    load_osm_graph_from_xml_stream,
    load_osm_graph_from_xml_string,
    parse_maxspeed,
)
from emergency_intelligence.data import SAMPLE_HOSPITAL_DISTRICT_PATH
from emergency_intelligence.graph.astar import astar
from emergency_intelligence.graph.dijkstra import dijkstra


# ---------------------------------------------------------------------------
# Test Speed Limit Parsing
# ---------------------------------------------------------------------------


class TestMaxspeedParser:
    def test_numeric_inputs(self):
        assert parse_maxspeed(50) == 50.0
        assert parse_maxspeed(45.5) == 45.5
        assert parse_maxspeed(0, default_speed_kmh=30.0) == 30.0
        assert parse_maxspeed(-10, default_speed_kmh=25.0) == 25.0

    def test_metric_strings(self):
        assert parse_maxspeed("50") == 50.0
        assert parse_maxspeed("60 km/h") == 60.0
        assert parse_maxspeed("80 kmh") == 80.0
        assert parse_maxspeed("100kph") == 100.0

    def test_imperial_mph_strings(self):
        # 30 mph * 1.609344 = 48.28032 km/h
        val = parse_maxspeed("30 mph")
        assert val == pytest.approx(48.28032)

        val_no_space = parse_maxspeed("25mph")
        assert val_no_space == pytest.approx(40.2336)

    def test_special_tokens(self):
        assert parse_maxspeed("walk") == 5.0
        assert parse_maxspeed("none", default_speed_kmh=100.0) == 100.0
        assert parse_maxspeed("signals", default_speed_kmh=50.0) == 50.0
        assert parse_maxspeed("variable", default_speed_kmh=60.0) == 60.0
        assert parse_maxspeed("implicit", default_speed_kmh=40.0) == 40.0

    def test_conditional_and_compound_limits(self):
        # Extracts primary value before conditions
        assert parse_maxspeed("50 @ (06:00-20:00)") == 50.0
        assert parse_maxspeed("80; 60") == 80.0

    def test_none_empty_or_invalid_falls_back_to_default(self):
        assert parse_maxspeed(None, default_speed_kmh=35.0) == 35.0
        assert parse_maxspeed("", default_speed_kmh=35.0) == 35.0
        assert parse_maxspeed("   ", default_speed_kmh=35.0) == 35.0
        assert parse_maxspeed("unparseable_speed", default_speed_kmh=35.0) == 35.0


# ---------------------------------------------------------------------------
# Test Access Restrictions & Emergency Bypass
# ---------------------------------------------------------------------------


class TestAccessAndEmergencyBypass:
    def test_generic_accessible_way(self):
        tags = {"highway": "primary", "name": "Main Street"}
        assert is_way_accessible(tags) is True

    def test_restricted_access_without_emergency_tag(self):
        assert is_way_accessible({"access": "no"}) is False
        assert is_way_accessible({"access": "private"}) is False
        assert is_way_accessible({"motor_vehicle": "no"}) is False
        assert is_way_accessible({"motorcar": "delivery"}) is False

    def test_emergency_bypass_overrides_restrictions(self):
        tags_emergency_yes = {"access": "no", "emergency": "yes"}
        assert is_way_accessible(tags_emergency_yes, allow_emergency_access=True) is True
        assert is_way_accessible(tags_emergency_yes, allow_emergency_access=False) is False

        tags_emergency_designated = {"motor_vehicle": "no", "emergency": "designated"}
        assert is_way_accessible(tags_emergency_designated, allow_emergency_access=True) is True

        tags_access_emergency = {"access": "emergency"}
        assert is_way_accessible(tags_access_emergency, allow_emergency_access=True) is True


# ---------------------------------------------------------------------------
# Test Multi-Criteria Weighting Profiles (JSON Ingestion)
# ---------------------------------------------------------------------------


class TestMultiCriteriaWeighting:
    def test_invalid_weighting_profile_raises(self):
        with pytest.raises(ValueError, match="Invalid weighting_profile"):
            load_osm_graph_from_file(
                SAMPLE_HOSPITAL_DISTRICT_PATH,
                weighting_profile="invalid_profile",
            )

    def test_distance_profile_edge_attributes(self):
        graph = load_osm_graph_from_file(
            SAMPLE_HOSPITAL_DISTRICT_PATH,
            weighting_profile=WeightingProfile.DISTANCE,
        )
        edge = graph.get_neighbors("1001")[0]
        # In distance profile, cost equals physical distance
        assert edge.cost == pytest.approx(edge.attributes["distance_m"])
        assert "travel_time_s" in edge.attributes
        assert "emergency_time_s" in edge.attributes
        assert "maxspeed_kmh" in edge.attributes
        assert "highway" in edge.attributes

    def test_travel_time_profile(self):
        dist_graph = load_osm_graph_from_file(
            SAMPLE_HOSPITAL_DISTRICT_PATH,
            weighting_profile=WeightingProfile.DISTANCE,
        )
        time_graph = load_osm_graph_from_file(
            SAMPLE_HOSPITAL_DISTRICT_PATH,
            weighting_profile=WeightingProfile.TRAVEL_TIME,
        )

        d_res = dijkstra(dist_graph, "1001", "1008")
        t_res = dijkstra(time_graph, "1001", "1008")

        assert d_res.reachable is True
        assert t_res.reachable is True
        # Cost is in seconds, significantly smaller numerical value than distance in meters
        assert t_res.total_cost < d_res.total_cost
        assert t_res.total_cost > 0.0

    def test_emergency_time_profile_faster_than_standard(self):
        standard_graph = load_osm_graph_from_file(
            SAMPLE_HOSPITAL_DISTRICT_PATH,
            weighting_profile=WeightingProfile.TRAVEL_TIME,
        )
        emergency_graph = load_osm_graph_from_file(
            SAMPLE_HOSPITAL_DISTRICT_PATH,
            weighting_profile=WeightingProfile.EMERGENCY_TIME,
        )

        std_res = dijkstra(standard_graph, "1001", "1008")
        emg_res = dijkstra(emergency_graph, "1001", "1008")

        # Emergency vehicle with priority moves faster -> lower travel time in seconds
        assert emg_res.total_cost <= std_res.total_cost


# ---------------------------------------------------------------------------
# Test Streaming XML Ingestion
# ---------------------------------------------------------------------------


SAMPLE_OSM_XML = """<?xml version="1.0" encoding="UTF-8"?>
<osm version="0.6">
  <node id="1" lat="37.7749" lon="-122.4194">
    <tag k="name" v="Hospital Dispatch"/>
  </node>
  <node id="2" lat="37.7758" lon="-122.4194">
    <tag k="name" v="Midtown Junction"/>
  </node>
  <node id="3" lat="37.7767" lon="-122.4194">
    <tag k="name" v="Emergency Trauma Hub"/>
  </node>
  <node id="4" lat="37.7770" lon="-122.4180">
    <tag k="name" v="Roundabout East"/>
  </node>
  <node id="999" lat="37.8000" lon="-122.4000">
    <tag k="name" v="Orphaned Point"/>
  </node>
  <!-- Two-way primary arterial -->
  <way id="101">
    <nd ref="1"/>
    <nd ref="2"/>
    <tag k="highway" v="primary"/>
    <tag k="maxspeed" v="45 mph"/>
    <tag k="name" v="Grand Avenue"/>
  </way>
  <!-- One-way reverse street -->
  <way id="102">
    <nd ref="2"/>
    <nd ref="3"/>
    <tag k="highway" v="secondary"/>
    <tag k="oneway" v="-1"/>
    <tag k="maxspeed" v="30 km/h"/>
  </way>
  <!-- Roundabout junction -->
  <way id="103">
    <nd ref="3"/>
    <nd ref="4"/>
    <tag k="highway" v="tertiary"/>
    <tag k="junction" v="roundabout"/>
  </way>
  <!-- Pedestrian way with emergency bypass -->
  <way id="104">
    <nd ref="4"/>
    <nd ref="1"/>
    <tag k="highway" v="service"/>
    <tag k="access" v="no"/>
    <tag k="emergency" v="yes"/>
  </way>
</osm>
"""


class TestStreamingXMLParser:
    def test_load_from_xml_string(self):
        graph = load_osm_graph_from_xml_string(SAMPLE_OSM_XML)

        # Active nodes 1, 2, 3, 4 should be present; orphaned 999 excluded
        assert graph.node_count() == 4
        assert not graph.has_node("999")
        assert graph.has_node("1")
        assert graph.has_node("2")
        assert graph.has_node("3")
        assert graph.has_node("4")

        # Node coordinates
        node_1 = graph.get_node("1")
        assert node_1.coordinates == pytest.approx((-122.4194, 37.7749))
        assert node_1.label == "Hospital Dispatch"

        # Check two-way Grand Avenue
        nbrs_1 = [e.destination_id for e in graph.get_neighbors("1")]
        nbrs_2 = [e.destination_id for e in graph.get_neighbors("2")]
        assert "2" in nbrs_1
        assert "1" in nbrs_2

        # Check reverse oneway (way 102 from 2->3 with oneway=-1 means directed 3 -> 2 only)
        nbrs_3 = [e.destination_id for e in graph.get_neighbors("3")]
        assert "2" in nbrs_3
        assert "3" not in nbrs_2

        # Check roundabout (way 103 from 3->4 is forward-only)
        assert "4" in nbrs_3
        nbrs_4 = [e.destination_id for e in graph.get_neighbors("4")]
        assert "3" not in nbrs_4

        # Check emergency bypass (service road with access=no and emergency=yes)
        assert "1" in nbrs_4

    def test_xml_stream_invalid_weighting_profile_raises(self):
        with pytest.raises(ValueError, match="Invalid weighting_profile"):
            load_osm_graph_from_xml_string(SAMPLE_OSM_XML, weighting_profile="bogus")

    def test_load_from_xml_file(self, tmp_path: Path):
        xml_file = tmp_path / "test_city.osm"
        xml_file.write_text(SAMPLE_OSM_XML, encoding="utf-8")

        graph = load_osm_graph_from_xml_file(xml_file)
        assert graph.node_count() == 4

        # Routing check
        result = dijkstra(graph, "1", "2")
        assert result.reachable is True
        assert result.path == ["1", "2"]

    def test_load_nonexistent_xml_file_raises(self):
        with pytest.raises(FileNotFoundError):
            load_osm_graph_from_xml_file("nonexistent_map.osm")


# ---------------------------------------------------------------------------
# Test Backwards Compatibility with Phase 1 Tests
# ---------------------------------------------------------------------------


class TestOSMParserBackwardsCompatibility:
    def test_load_sample_hospital_district_file(self):
        graph = load_osm_graph_from_file(SAMPLE_HOSPITAL_DISTRICT_PATH)
        assert graph.node_count() == 11
        assert not graph.has_node("9999")
        assert graph.has_node("1001")
        assert graph.has_node("1008")

        dispatch_node = graph.get_node("1001")
        assert dispatch_node.coordinates == pytest.approx((-122.419416, 37.774929))
        assert dispatch_node.label == "Central Emergency Dispatch"

    def test_oneway_direction_enforced(self):
        graph = load_osm_graph_from_file(SAMPLE_HOSPITAL_DISTRICT_PATH)
        nbrs_1005 = [e.destination_id for e in graph.get_neighbors("1005")]
        nbrs_1006 = [e.destination_id for e in graph.get_neighbors("1006")]
        assert "1006" in nbrs_1005
        assert "1005" not in nbrs_1006

    def test_reverse_oneway_parsing_in_json(self):
        data = {
            "elements": [
                {"type": "node", "id": 10, "lat": 37.77, "lon": -122.41},
                {"type": "node", "id": 20, "lat": 37.78, "lon": -122.41},
                {
                    "type": "way",
                    "id": 99,
                    "nodes": [10, 20],
                    "tags": {"highway": "primary", "oneway": "-1"},
                },
            ]
        }
        graph = load_osm_graph_from_data(data)
        assert graph.has_edge("20", "10")
        assert not graph.has_edge("10", "20")

    def test_highway_filter_custom(self):
        graph = load_osm_graph_from_file(
            SAMPLE_HOSPITAL_DISTRICT_PATH,
            highway_filter={"primary"},
        )
        assert graph.has_node("1001")
        assert graph.has_node("1004")
        assert graph.has_node("1008")
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
        result = dijkstra(graph, "1001", "1008")
        assert result.reachable is True
        assert result.path[0] == "1001"
        assert result.path[-1] == "1008"
        assert result.total_cost > 200.0

    def test_astar_with_haversine_matches_dijkstra_optimal_cost(self):
        graph = load_osm_graph_from_file(SAMPLE_HOSPITAL_DISTRICT_PATH)
        d_res = dijkstra(graph, "1001", "1008")
        a_res = astar(graph, "1001", "1008", heuristic=haversine_heuristic)

        assert d_res.reachable is True
        assert a_res.reachable is True
        assert d_res.total_cost == pytest.approx(a_res.total_cost, rel=1e-5)
        assert d_res.path == a_res.path

    def test_reverse_route_respects_oneway_restrictions(self):
        graph = load_osm_graph_from_file(SAMPLE_HOSPITAL_DISTRICT_PATH)
        fwd_res = dijkstra(graph, "1001", "1008")
        rev_res = dijkstra(graph, "1008", "1001")
        assert fwd_res.reachable is True
        assert rev_res.reachable is True
        assert not ("1008" in rev_res.path and "1007" in rev_res.path and "1006" in rev_res.path)
