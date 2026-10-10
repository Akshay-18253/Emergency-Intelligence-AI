"""
Unit Test Suite for OASIS CAP Alerts & In-Flight Reactive Rerouting Subsystem.
=============================================================================
Validates CAP v1.2 XML document parsing, GeoJSON alert feed conversions,
in-transit vehicle tracker state machines, obstacle detection, and mid-flight
sub-millisecond detour replanning.
"""

from __future__ import annotations

from datetime import datetime, timezone
import math
import pytest

from emergency_intelligence.events.alerts import (
    CAPAlert,
    CAPCertainty,
    CAPMsgType,
    CAPSeverity,
    CAPUrgency,
    parse_cap_xml,
    parse_geojson_alerts,
)
from emergency_intelligence.events.hazards import HazardSeverity, HazardType
from emergency_intelligence.events.inflight import (
    DispatchedVehicleTracker,
    check_route_obstruction,
    replan_inflight_route,
)
from emergency_intelligence.events.mutations import DynamicGraphView
from emergency_intelligence.graph.models import Edge, Graph, Node


# ---------------------------------------------------------------------------
# Sample OASIS CAP v1.2 XML Document
# ---------------------------------------------------------------------------

SAMPLE_CAP_XML = """<?xml version="1.0" encoding="UTF-8"?>
<alert xmlns="urn:oasis:names:tc:emergency:cap:1.2">
  <identifier>NWS-SFO-2026-FLOOD-001</identifier>
  <sender>w-nws.webmaster@noaa.gov</sender>
  <sent>2026-10-10T14:00:00-00:00</sent>
  <status>Actual</status>
  <msgType>Alert</msgType>
  <scope>Public</scope>
  <info>
    <category>Met</category>
    <event>Flash Flood Warning</event>
    <urgency>Immediate</urgency>
    <severity>Severe</severity>
    <certainty>Observed</certainty>
    <expires>2026-10-10T18:00:00-00:00</expires>
    <description>Severe flash flooding over Market St. Transit corridor.</description>
    <area>
      <areaDesc>San Francisco Downtown / Civic Center</areaDesc>
      <polygon>37.778,-122.415 37.785,-122.415 37.785,-122.405 37.778,-122.405 37.778,-122.415</polygon>
    </area>
  </info>
</alert>
"""


@pytest.fixture
def test_inflight_network() -> Graph:
    """Creates a 5-node corridor test network:
       100 -> 101 -> 102 -> 103 -> 104
       Bypass detour: 101 -> 200 -> 103
    """
    g = Graph()
    g.add_node(Node("100", coordinates=[-122.420, 37.780]))
    g.add_node(Node("101", coordinates=[-122.415, 37.780]))
    g.add_node(Node("102", coordinates=[-122.410, 37.780]))
    g.add_node(Node("103", coordinates=[-122.405, 37.780]))
    g.add_node(Node("104", coordinates=[-122.400, 37.780]))
    g.add_node(Node("200", coordinates=[-122.410, 37.785]))  # detour node

    def add_bi(u: str, v: str, cost: float) -> None:
        g.add_edge(Edge(u, v, cost=cost))
        g.add_edge(Edge(v, u, cost=cost))

    # Main corridor
    add_bi("100", "101", 10.0)
    add_bi("101", "102", 10.0)
    add_bi("102", "103", 10.0)
    add_bi("103", "104", 10.0)

    # Alternate bypass corridor around 102
    add_bi("101", "200", 12.0)
    add_bi("200", "103", 12.0)

    return g


# ---------------------------------------------------------------------------
# OASIS CAP & GeoJSON Alert Parser Tests
# ---------------------------------------------------------------------------

class TestAlertParser:
    def test_parse_valid_cap_xml(self) -> None:
        alert = parse_cap_xml(SAMPLE_CAP_XML)
        assert alert.identifier == "NWS-SFO-2026-FLOOD-001"
        assert alert.event == "Flash Flood Warning"
        assert alert.urgency == CAPUrgency.IMMEDIATE
        assert alert.severity == CAPSeverity.SEVERE
        assert alert.certainty == CAPCertainty.OBSERVED
        assert len(alert.polygons) == 1

        # Check coordinates in [lon, lat] order
        poly = alert.polygons[0]
        assert len(poly) >= 4
        # lat 37.778, lon -122.415 should be stored as [-122.415, 37.778]
        assert poly[0] == (-122.415, 37.778)

        # Convert to internal HazardPolygon
        hazards = alert.to_hazard_polygons()
        assert len(hazards) == 1
        h = hazards[0]
        assert h.hazard_type == HazardType.FLASH_FLOOD
        assert h.severity == HazardSeverity.SEVERE
        assert h.is_blocking() is True

        d = alert.to_dict()
        assert d["identifier"] == alert.identifier
        assert len(d["polygons"]) == 1

    def test_parse_cap_xml_fallback_without_info(self) -> None:
        raw_xml = """<alert><identifier>ALERT-MINIMAL</identifier><sender>TEST</sender></alert>"""
        alert = parse_cap_xml(raw_xml)
        assert alert.identifier == "ALERT-MINIMAL"
        assert alert.event == "General Emergency"
        assert len(alert.polygons) == 0

    def test_parse_cap_xml_invalid_syntax_raises(self) -> None:
        with pytest.raises(ValueError, match="Failed to parse CAP XML"):
            parse_cap_xml("<<not-valid-xml>>")

    def test_to_hazard_polygons_type_inference(self) -> None:
        base_alert = CAPAlert(
            identifier="TEST-TYPES",
            sender="TEST",
            sent_at=datetime.now(timezone.utc),
            msg_type=CAPMsgType.ALERT,
            event="Chemical Leak Hazard",
            urgency=CAPUrgency.IMMEDIATE,
            severity=CAPSeverity.EXTREME,
            certainty=CAPCertainty.OBSERVED,
            polygons=[[(-122.41, 37.78), (-122.40, 37.78), (-122.40, 37.79), (-122.41, 37.78)]],
        )
        hazards = base_alert.to_hazard_polygons()
        assert len(hazards) == 1
        assert hazards[0].hazard_type == HazardType.TOXIC_GAS_PLUME
        assert hazards[0].severity == HazardSeverity.CRITICAL_BLOCKED

    def test_parse_geojson_alerts(self) -> None:
        payload = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "id": "QUAKE-01",
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [
                            [
                                [-122.41, 37.78],
                                [-122.40, 37.78],
                                [-122.40, 37.79],
                                [-122.41, 37.78],
                            ]
                        ],
                    },
                    "properties": {
                        "event": "Bridge Collapse",
                        "severity": "critical_blocked",
                        "speed_multiplier": 0.0,
                    },
                },
                {
                    # Invalid point geometry should be ignored
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [-122.4, 37.7]},
                },
            ],
        }

        hazards = parse_geojson_alerts(payload)
        assert len(hazards) == 1
        assert hazards[0].hazard_id == "QUAKE-01"
        assert hazards[0].hazard_type == HazardType.ROAD_COLLAPSE
        assert hazards[0].is_blocking() is True


# ---------------------------------------------------------------------------
# In-Flight Vehicle Tracker & Reactive Rerouting Tests
# ---------------------------------------------------------------------------

class TestInFlightRerouter:
    def test_tracker_initialization_and_validation(self) -> None:
        tracker = DispatchedVehicleTracker(
            unit_id="MEDIC-1",
            incident_id="INC-1",
            destination_node_id="104",
            path=["100", "101", "102", "103", "104"],
            progress_ratio=0.25,
        )
        assert tracker.unit_id == "MEDIC-1"
        assert tracker.current_tail_node == "100"
        assert tracker.current_head_node == "101"
        assert tracker.remaining_path == ["101", "102", "103", "104"]
        assert not tracker.is_arrived

        # Validation errors
        with pytest.raises(ValueError, match="at least one node"):
            DispatchedVehicleTracker("U1", "I1", "D1", path=[])

        with pytest.raises(ValueError, match="must match path terminus"):
            DispatchedVehicleTracker("U1", "I1", "WRONG_TERM", path=["100", "101"])

        with pytest.raises(ValueError, match="progress_ratio"):
            DispatchedVehicleTracker("U1", "I1", "101", path=["100", "101"], progress_ratio=1.5)

    def test_tracker_advance_and_step(self) -> None:
        tracker = DispatchedVehicleTracker(
            unit_id="MEDIC-1",
            incident_id="INC-1",
            destination_node_id="104",
            path=["100", "101", "102", "103", "104"],
        )

        tracker.advance(0.5)
        assert tracker.current_edge_index == 0
        assert tracker.progress_ratio == 0.5

        # Advance beyond current edge
        tracker.advance(0.7)
        assert tracker.current_edge_index == 1
        assert tracker.progress_ratio == pytest.approx(0.2)
        assert tracker.current_tail_node == "101"
        assert tracker.current_head_node == "102"

        # Step to next node directly
        tracker.step_to_next_node()
        assert tracker.current_edge_index == 2
        assert tracker.current_tail_node == "102"
        assert tracker.current_head_node == "103"

        # Advance to completion
        tracker.advance(10.0)
        assert tracker.is_arrived
        assert tracker.current_head_node == "104"

        d = tracker.to_dict()
        assert d["is_arrived"] is True

    def test_check_route_obstruction(self, test_inflight_network: Graph) -> None:
        view = DynamicGraphView(test_inflight_network)
        tracker = DispatchedVehicleTracker(
            unit_id="MEDIC-1",
            incident_id="INC-1",
            destination_node_id="104",
            path=["100", "101", "102", "103", "104"],
            current_edge_index=0,
        )

        # Clear route
        assert check_route_obstruction(tracker, view) is None

        # Block downstream edge 102 <-> 103
        view.apply_closure("102", "103", bidirectional=True)
        obstructed = check_route_obstruction(tracker, view)
        assert obstructed == ("102", "103")

        # Advance past obstruction
        tracker.current_edge_index = 3  # now on 103 -> 104
        assert check_route_obstruction(tracker, view) is None

        # Arrived vehicle
        tracker.current_edge_index = 4
        assert check_route_obstruction(tracker, view) is None

    def test_replan_inflight_route_downstream_detour(self, test_inflight_network: Graph) -> None:
        view = DynamicGraphView(test_inflight_network)
        # Vehicle is travelling along 100 -> 101 (at 40% progress)
        tracker = DispatchedVehicleTracker(
            unit_id="MEDIC-1",
            incident_id="INC-1",
            destination_node_id="104",
            path=["100", "101", "102", "103", "104"],
            current_edge_index=0,
            progress_ratio=0.4,
        )

        # Sudden road closure ahead on 101 -> 102
        view.apply_closure("101", "102", reason="Collapsed Water Main", bidirectional=True)

        # Replan
        new_route = replan_inflight_route(tracker, view)
        assert new_route is not None
        assert new_route.reachable

        # Vehicle must reach 101, then detour via 200 to 103 and 104!
        # Initial path: ['100', '101'] + detour from 101: ['101', '200', '103', '104']
        assert "200" in tracker.path
        assert "102" not in tracker.path[tracker.current_edge_index :]
        assert tracker.reroute_count == 1
        assert tracker.destination_node_id == "104"

    def test_replan_inflight_route_when_unreachable(self, test_inflight_network: Graph) -> None:
        view = DynamicGraphView(test_inflight_network)
        tracker = DispatchedVehicleTracker(
            unit_id="MEDIC-1",
            incident_id="INC-1",
            destination_node_id="104",
            path=["100", "101", "102", "103", "104"],
            current_edge_index=1,
            progress_ratio=0.5,
        )

        # Close all paths to 104: close 103 <-> 104
        view.apply_closure("103", "104", bidirectional=True)

        new_route = replan_inflight_route(tracker, view)
        # 104 is completely unreachable
        assert new_route is None
        assert tracker.reroute_count == 0

    def test_replan_inflight_route_noop_when_clear_or_arrived(self, test_inflight_network: Graph) -> None:
        view = DynamicGraphView(test_inflight_network)
        tracker = DispatchedVehicleTracker(
            unit_id="MEDIC-1",
            incident_id="INC-1",
            destination_node_id="104",
            path=["100", "101", "102", "103", "104"],
        )
        # Clear route returns None
        assert replan_inflight_route(tracker, view) is None

        # Arrived tracker returns None
        tracker.current_edge_index = 4
        assert replan_inflight_route(tracker, view) is None

    def test_replan_inflight_route_from_tail_at_zero_progress(self, test_inflight_network: Graph) -> None:
        view = DynamicGraphView(test_inflight_network)
        # Vehicle at node 100 with progress 0.0
        tracker = DispatchedVehicleTracker(
            unit_id="MEDIC-1",
            incident_id="INC-1",
            destination_node_id="104",
            path=["100", "101", "102", "103", "104"],
            current_edge_index=0,
            progress_ratio=0.0,
        )
        # Block immediate edge 100 -> 101
        view.apply_closure("100", "101", bidirectional=True)
        # With 100->101 blocked and no other outgoing edge from 100, destination unreachable
        new_route = replan_inflight_route(tracker, view)
        assert new_route is None

    def test_check_route_obstruction_base_graph(self, test_inflight_network: Graph) -> None:
        tracker = DispatchedVehicleTracker(
            unit_id="MEDIC-1",
            incident_id="INC-1",
            destination_node_id="104",
            path=["100", "101", "NON_EXISTENT", "104"],
        )
        obstructed = check_route_obstruction(tracker, test_inflight_network)
        assert obstructed == ("101", "NON_EXISTENT")

    def test_alert_type_inference_branches(self) -> None:
        alert_fire = CAPAlert("1", "T", datetime.now(timezone.utc), CAPMsgType.ALERT, "Wildfire Warning", CAPUrgency.IMMEDIATE, CAPSeverity.EXTREME, CAPCertainty.OBSERVED, polygons=[[(-122.4, 37.7), (-122.3, 37.7), (-122.3, 37.8), (-122.4, 37.7)]])
        assert alert_fire.to_hazard_polygons()[0].hazard_type == HazardType.WILDFIRE_PERIMETER

        alert_debris = CAPAlert("2", "T", datetime.now(timezone.utc), CAPMsgType.ALERT, "Downed Tree Debris", CAPUrgency.EXPECTED, CAPSeverity.MODERATE, CAPCertainty.LIKELY, polygons=[[(-122.4, 37.7), (-122.3, 37.7), (-122.3, 37.8), (-122.4, 37.7)]])
        assert alert_debris.to_hazard_polygons()[0].hazard_type == HazardType.STRUCTURAL_DEBRIS

        alert_unrest = CAPAlert("3", "T", datetime.now(timezone.utc), CAPMsgType.ALERT, "Civil Unrest Hazard", CAPUrgency.EXPECTED, CAPSeverity.MINOR, CAPCertainty.POSSIBLE, polygons=[[(-122.4, 37.7), (-122.3, 37.7), (-122.3, 37.8), (-122.4, 37.7)]])
        assert alert_unrest.to_hazard_polygons()[0].hazard_type == HazardType.CIVIL_UNREST

    def test_parse_geojson_alerts_string_and_types(self) -> None:
        json_str = """{
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "id": "HAZ-SMOKE",
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[[-122.41, 37.78], [-122.40, 37.78], [-122.40, 37.79], [-122.41, 37.78]]]
                    },
                    "properties": {"hazard_type": "smoke"}
                },
                {
                    "type": "Feature",
                    "id": "HAZ-DEBRIS",
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[[-122.41, 37.78], [-122.40, 37.78], [-122.40, 37.79], [-122.41, 37.78]]]
                    },
                    "properties": {"hazard_type": "debris"}
                },
                {
                    "type": "Feature",
                    "id": "HAZ-FLASH",
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[[-122.41, 37.78], [-122.40, 37.78], [-122.40, 37.79], [-122.41, 37.78]]]
                    },
                    "properties": {"hazard_type": "flash"}
                },
                {
                    "type": "Feature",
                    "id": "HAZ-FIRE",
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[[-122.41, 37.78], [-122.40, 37.78], [-122.40, 37.79], [-122.41, 37.78]]]
                    },
                    "properties": {"hazard_type": "fire"}
                }
            ]
        }"""
        hazards = parse_geojson_alerts(json_str)
        assert len(hazards) == 4
        assert hazards[0].hazard_type == HazardType.TOXIC_GAS_PLUME
        assert hazards[1].hazard_type == HazardType.STRUCTURAL_DEBRIS
        assert hazards[2].hazard_type == HazardType.FLASH_FLOOD
        assert hazards[3].hazard_type == HazardType.WILDFIRE_PERIMETER

    def test_parse_cap_xml_date_and_poly_fallbacks(self) -> None:
        xml = """<alert><identifier>A1</identifier><sent>invalid-date</sent><info><event>Flood</event><expires>invalid-expires</expires><area><polygon>37.7,-122.4</polygon></area></info></alert>"""
        alert = parse_cap_xml(xml)
        assert alert.identifier == "A1"
        assert alert.expires_at is None
        assert len(alert.polygons) == 0
