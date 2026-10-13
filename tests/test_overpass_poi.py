"""
Unit tests for OSM Overpass POI Ingestion & Emergency Infrastructure Binding.
=============================================================================
Tests Overpass QL query construction, API parsing, clinical capability extraction,
spatial network snapping, fleet creation, and specialized hospital routing.

Adheres strictly to zero external runtime dependencies and 100% offline execution.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any, Dict
import urllib.error
import urllib.request
import pytest

from emergency_intelligence.allocation.matcher import FleetManager
from emergency_intelligence.allocation.models import EmergencyStation, EmergencyUnit
from emergency_intelligence.events.incidents import ApparatusType
from emergency_intelligence.external.binding import (
    POINetworkBinding,
    SpatialBindingError,
    bind_poi_to_network,
    bind_pois_to_network,
    create_fleet_from_pois,
    find_nearest_clinical_facility,
    poi_to_emergency_station,
)
from emergency_intelligence.external.overpass import (
    ClinicalCapability,
    EmergencyPOIType,
    ExtractedEmergencyPOI,
    OverpassNetworkError,
    OverpassParseError,
    build_emergency_poi_query,
    fetch_or_load_overpass_pois,
    parse_overpass_response,
)
from emergency_intelligence.graph.models import Edge, Graph, Node


# ============================================================================
# 1. Domain Models & POI Representation Tests
# ============================================================================

def test_extracted_poi_valid_initialization() -> None:
    poi = ExtractedEmergencyPOI(
        osm_id=123456,
        osm_type="node",
        poi_type=EmergencyPOIType.HOSPITAL,
        name="Harborview Medical Center",
        latitude=47.604,
        longitude=-122.325,
        capabilities={ClinicalCapability.TRAUMA_LEVEL_1, ClinicalCapability.BURN_CENTER},
        trauma_level=1,
        apparatus_bays=None,
        operator="UW Medicine",
        phone="+1-206-744-3000",
        address="325 9th Ave, Seattle",
        raw_tags={"amenity": "hospital", "emergency:trauma_level": "1"},
    )
    assert poi.osm_id == 123456
    assert poi.has_capability(ClinicalCapability.TRAUMA_LEVEL_1)
    assert poi.has_capability("burn_center")
    assert not poi.has_capability(ClinicalCapability.PEDIATRIC_CARE)
    assert not poi.has_capability("non_existent_capability")


def test_extracted_poi_coordinate_validation() -> None:
    with pytest.raises(ValueError, match="Invalid latitude"):
        ExtractedEmergencyPOI(
            osm_id=1,
            osm_type="node",
            poi_type=EmergencyPOIType.FIRE_STATION,
            name="Invalid Lat",
            latitude=95.0,
            longitude=-122.0,
        )

    with pytest.raises(ValueError, match="Invalid longitude"):
        ExtractedEmergencyPOI(
            osm_id=2,
            osm_type="node",
            poi_type=EmergencyPOIType.FIRE_STATION,
            name="Invalid Lon",
            latitude=45.0,
            longitude=-195.0,
        )

    with pytest.raises(ValueError, match="finite numbers"):
        ExtractedEmergencyPOI(
            osm_id=3,
            osm_type="node",
            poi_type=EmergencyPOIType.FIRE_STATION,
            name="Non-finite",
            latitude=float("nan"),
            longitude=-122.0,
        )


def test_extracted_poi_type_conversion_and_validation() -> None:
    poi = ExtractedEmergencyPOI(
        osm_id=10,
        osm_type="way",
        poi_type="fire_station",  # string coerced to enum
        name="Station 10",
        latitude=47.6,
        longitude=-122.3,
    )
    assert poi.poi_type == EmergencyPOIType.FIRE_STATION

    with pytest.raises(TypeError, match="Invalid poi_type"):
        ExtractedEmergencyPOI(
            osm_id=11,
            osm_type="node",
            poi_type=12345,  # type: ignore
            name="Bad Type",
            latitude=47.6,
            longitude=-122.3,
        )


def test_extracted_poi_dict_roundtrip() -> None:
    original = ExtractedEmergencyPOI(
        osm_id=999,
        osm_type="relation",
        poi_type=EmergencyPOIType.FIRE_STATION,
        name="Downtown Fire Depot",
        latitude=47.61,
        longitude=-122.33,
        capabilities={ClinicalCapability.HAZMAT_DECON},
        trauma_level=None,
        apparatus_bays=4,
        operator="City Fire Dept",
        phone="911",
        address="100 4th Ave",
        raw_tags={"amenity": "fire_station", "bays": "4"},
    )
    d = original.to_dict()
    assert d["osm_id"] == 999
    assert d["poi_type"] == "fire_station"
    assert "hazmat_decon" in d["capabilities"]
    assert d["apparatus_bays"] == 4

    restored = ExtractedEmergencyPOI.from_dict(d)
    assert restored.osm_id == original.osm_id
    assert restored.name == original.name
    assert restored.capabilities == original.capabilities
    assert restored.apparatus_bays == original.apparatus_bays


# ============================================================================
# 2. Overpass QL Query Builder Tests
# ============================================================================

def test_build_query_with_bbox() -> None:
    bbox = (47.59, -122.35, 47.65, -122.30)
    query = build_emergency_poi_query(bbox=bbox, timeout_seconds=30)
    assert "[out:json][timeout:30];" in query
    assert "(47.59,-122.35,47.65,-122.3)" in query
    assert 'node["amenity"="hospital"]' in query
    assert 'way["amenity"="fire_station"]' in query
    assert "out center tags;" in query


def test_build_query_with_area_name() -> None:
    query = build_emergency_poi_query(area_name="Seattle", timeout_seconds=15)
    assert 'area["name"="Seattle"]->.searchArea;' in query
    assert "(area.searchArea);" in query


def test_build_query_with_specific_poi_types() -> None:
    bbox = (47.59, -122.35, 47.65, -122.30)
    query = build_emergency_poi_query(
        bbox=bbox,
        poi_types=[EmergencyPOIType.HOSPITAL, EmergencyPOIType.HELIPAD],
    )
    assert '["amenity"="hospital"]' in query
    assert '["aeroway"="helipad"]' in query
    assert '["amenity"="fire_station"]' not in query


def test_build_query_errors() -> None:
    with pytest.raises(ValueError, match="Either bbox or area_name"):
        build_emergency_poi_query()

    with pytest.raises(ValueError, match="Invalid latitude"):
        build_emergency_poi_query(bbox=(95.0, -122.0, 96.0, -121.0))

    with pytest.raises(ValueError, match="Invalid longitude"):
        build_emergency_poi_query(bbox=(47.0, -200.0, 48.0, -121.0))


# ============================================================================
# 3. Overpass Response Parser Tests
# ============================================================================

SAMPLE_OVERPASS_JSON: Dict[str, Any] = {
    "version": 0.6,
    "generator": "Overpass API",
    "elements": [
        {
            "type": "node",
            "id": 1001,
            "lat": 47.6045,
            "lon": -122.3248,
            "tags": {
                "amenity": "hospital",
                "name": "Harborview Medical Center",
                "emergency": "yes",
                "emergency:trauma_level": "1",
                "healthcare:speciality": "cardiology;burn;pediatrics",
                "emergency:helipad": "yes",
                "operator": "UW Medicine",
                "addr:street": "9th Ave",
                "addr:housenumber": "325",
                "addr:city": "Seattle",
                "phone": "+1-206-744-3000",
            },
        },
        {
            "type": "way",
            "id": 2002,
            "center": {"lat": 47.6189, "lon": -122.3321},
            "tags": {
                "amenity": "fire_station",
                "name": "Seattle Fire Station 2",
                "fire_station:engine_bays": "3",
                "hazmat": "yes",
                "phone": "+1-206-386-1400",
            },
        },
        {
            "type": "relation",
            "id": 3003,
            "center": {"lat": 47.6120, "lon": -122.3410},
            "tags": {
                "aeroway": "helipad",
                "name": "Ecolab Helipad",
            },
        },
        {
            "type": "node",
            "id": 4004,
            "lat": 47.6000,
            "lon": -122.3300,
            "tags": {
                "emergency": "ambulance_station",
                "name": "King County Medic One",
            },
        },
        {
            "type": "node",
            "id": 5005,
            "lat": 47.6080,
            "lon": -122.3350,
            "tags": {
                "amenity": "police",
                "name": "West Precinct Police",
            },
        },
        {
            "type": "node",
            "id": 6006,
            "lat": 47.6150,
            "lon": -122.3200,
            "tags": {
                "amenity": "clinic",
                "healthcare": "centre",
                "name": "Capitol Hill Urgent Care",
            },
        },
        {
            "type": "node",
            "id": 7007,
            "lat": 47.6200,
            "lon": -122.3100,
            "tags": {
                "emergency": "control_centre",
                "name": "County 911 Communications",
            },
        },
        {
            "type": "node",
            "id": 8008,
            "lat": 47.6300,
            "lon": -122.3000,
            "tags": {
                "amenity": "hospital",
                # Unnamed hospital
                "emergency:trauma_level": "3",
                "healthcare:speciality": "stroke",
            },
        },
        {
            "type": "node",
            "id": 9999,
            "lat": 47.60,
            "lon": -122.30,
            "tags": {
                "amenity": "restaurant",  # Irrelevant amenity
                "name": "Coffee Shop",
            },
        },
    ],
}


def test_parse_overpass_response() -> None:
    pois = parse_overpass_response(SAMPLE_OVERPASS_JSON)
    assert len(pois) == 8  # Restaurant omitted

    # Hospital verification
    hosp = next(p for p in pois if p.osm_id == 1001)
    assert hosp.poi_type == EmergencyPOIType.HOSPITAL
    assert hosp.name == "Harborview Medical Center"
    assert hosp.trauma_level == 1
    assert hosp.has_capability(ClinicalCapability.TRAUMA_LEVEL_1)
    assert hosp.has_capability(ClinicalCapability.CARDIAC_CARE)
    assert hosp.has_capability(ClinicalCapability.BURN_CENTER)
    assert hosp.has_capability(ClinicalCapability.PEDIATRIC_CARE)
    assert hosp.has_capability(ClinicalCapability.HELIPAD)
    assert hosp.address == "325, 9th Ave, Seattle"

    # Fire station verification
    fire = next(p for p in pois if p.osm_id == 2002)
    assert fire.poi_type == EmergencyPOIType.FIRE_STATION
    assert fire.apparatus_bays == 3
    assert fire.has_capability(ClinicalCapability.HAZMAT_DECON)

    # Helipad verification
    heli = next(p for p in pois if p.osm_id == 3003)
    assert heli.poi_type == EmergencyPOIType.HELIPAD

    # Ambulance Station verification
    amb = next(p for p in pois if p.osm_id == 4004)
    assert amb.poi_type == EmergencyPOIType.AMBULANCE_STATION

    # Police verification
    pol = next(p for p in pois if p.osm_id == 5005)
    assert pol.poi_type == EmergencyPOIType.POLICE

    # Urgent care verification
    urg = next(p for p in pois if p.osm_id == 6006)
    assert urg.poi_type == EmergencyPOIType.URGENT_CARE

    # Dispatch center verification
    cad = next(p for p in pois if p.osm_id == 7007)
    assert cad.poi_type == EmergencyPOIType.DISPATCH_CENTER

    # Unnamed hospital fallback name & stroke capability
    unnamed = next(p for p in pois if p.osm_id == 8008)
    assert "Unnamed Hospital" in unnamed.name
    assert unnamed.trauma_level == 3
    assert unnamed.has_capability(ClinicalCapability.STROKE_CENTER)


def test_parse_overpass_json_string() -> None:
    raw_str = json.dumps(SAMPLE_OVERPASS_JSON)
    pois = parse_overpass_response(raw_str)
    assert len(pois) == 8


def test_parse_overpass_error_handling() -> None:
    with pytest.raises(OverpassParseError, match="Failed to parse"):
        parse_overpass_response("invalid json string {} {")

    with pytest.raises(OverpassParseError, match="missing mandatory 'elements'"):
        parse_overpass_response({"version": 0.6})

    with pytest.raises(OverpassParseError, match="Expected dict or str"):
        parse_overpass_response([1, 2, 3])  # type: ignore


# ============================================================================
# 4. Offline Client & HTTP Cache Tests
# ============================================================================

def test_fetch_or_load_cache_hit(tmp_path: Path) -> None:
    cache_file = tmp_path / "seattle_emergency.json"
    cache_file.write_text(json.dumps(SAMPLE_OVERPASS_JSON), encoding="utf-8")

    pois = fetch_or_load_overpass_pois(
        query="irrelevant query",
        cache_path=cache_file,
        force_refresh=False,
    )
    assert len(pois) == 8


class MockHTTPResponse:
    def __init__(self, data: bytes, status: int = 200) -> None:
        self.data = data
        self.status = status

    def read(self) -> bytes:
        return self.data

    def __enter__(self) -> MockHTTPResponse:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        pass


def test_fetch_or_load_mocked_network_success(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cache_file = tmp_path / "downloaded_cache.json"

    def mock_urlopen(req: Any, timeout: float = 10.0) -> MockHTTPResponse:
        payload_bytes = json.dumps(SAMPLE_OVERPASS_JSON).encode("utf-8")
        return MockHTTPResponse(payload_bytes, status=200)

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

    pois = fetch_or_load_overpass_pois(
        query="mock query",
        cache_path=cache_file,
        force_refresh=True,
    )
    assert len(pois) == 8
    assert cache_file.is_file()
    assert "Harborview" in cache_file.read_text(encoding="utf-8")


def test_fetch_or_load_mocked_network_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    def mock_urlopen_http_err(req: Any, timeout: float = 10.0) -> Any:
        raise urllib.error.HTTPError(
            url="https://overpass-api.de",
            code=429,
            msg="Too Many Requests",
            hdrs={},  # type: ignore
            fp=io.BytesIO(b"rate limited"),
        )

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen_http_err)

    with pytest.raises(OverpassNetworkError, match="Overpass HTTP Error 429"):
        fetch_or_load_overpass_pois(query="query", force_refresh=True)

    def mock_urlopen_url_err(req: Any, timeout: float = 10.0) -> Any:
        raise urllib.error.URLError("Connection refused")

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen_url_err)

    with pytest.raises(OverpassNetworkError, match="Overpass URL/Connection Error"):
        fetch_or_load_overpass_pois(query="query", force_refresh=True)


# ============================================================================
# 5. Spatial Network Snapping & Binding Tests
# ============================================================================

@pytest.fixture
def urban_road_network() -> Graph:
    """Creates a small Manhattan-style road network grid with coordinates."""
    g = Graph()
    # 3x3 grid around Seattle downtown (~47.60, -122.33)
    # n00 (0,0) --- n10 (1,0) --- n20 (2,0)
    #  |             |             |
    # n01 (0,1) --- n11 (1,1) --- n21 (2,1)
    #  |             |             |
    # n02 (0,2) --- n12 (1,2) --- n22 (2,2)

    lons = [-122.340, -122.330, -122.320]
    lats = [47.600, 47.610, 47.620]

    for y_idx, lat in enumerate(lats):
        for x_idx, lon in enumerate(lons):
            nid = f"n{x_idx}{y_idx}"
            g.add_node(Node(node_id=nid, coordinates=(lon, lat)))

    # Add bidirectional edges
    for y in range(3):
        for x in range(2):
            u, v = f"n{x}{y}", f"n{x+1}{y}"
            g.add_edge(Edge(source_id=u, destination_id=v, cost=100.0))
            g.add_edge(Edge(source_id=v, destination_id=u, cost=100.0))

    for x in range(3):
        for y in range(2):
            u, v = f"n{x}{y}", f"n{x}{y+1}"
            g.add_edge(Edge(source_id=u, destination_id=v, cost=100.0))
            g.add_edge(Edge(source_id=v, destination_id=u, cost=100.0))

    return g


def test_bind_poi_to_network(urban_road_network: Graph) -> None:
    # Facility near n11 (-122.330, 47.610)
    poi = ExtractedEmergencyPOI(
        osm_id=101,
        osm_type="node",
        poi_type=EmergencyPOIType.HOSPITAL,
        name="Central Hospital",
        latitude=47.6105,
        longitude=-122.3302,
        capabilities={ClinicalCapability.CARDIAC_CARE},
    )

    binding = bind_poi_to_network(poi, urban_road_network, max_snap_distance_m=1000.0)
    assert binding.poi.osm_id == 101
    assert binding.nearest_node_id == "n11"
    assert binding.distance_meters < 100.0
    d = binding.to_dict()
    assert d["nearest_node_id"] == "n11"
    assert d["distance_meters"] > 0.0


def test_bind_poi_distance_exceeded(urban_road_network: Graph) -> None:
    # Facility 50km away
    poi = ExtractedEmergencyPOI(
        osm_id=999,
        osm_type="node",
        poi_type=EmergencyPOIType.FIRE_STATION,
        name="Remote Outpost",
        latitude=48.500,
        longitude=-122.330,
    )
    with pytest.raises(SpatialBindingError, match="(beyond search radius|exceeding threshold)"):
        bind_poi_to_network(poi, urban_road_network, max_snap_distance_m=500.0)


def test_batch_bind_pois(urban_road_network: Graph) -> None:
    poi_near = ExtractedEmergencyPOI(
        osm_id=1,
        osm_type="node",
        poi_type=EmergencyPOIType.FIRE_STATION,
        name="Near Station",
        latitude=47.601,
        longitude=-122.339,
    )
    poi_far = ExtractedEmergencyPOI(
        osm_id=2,
        osm_type="node",
        poi_type=EmergencyPOIType.HOSPITAL,
        name="Far Hospital",
        latitude=48.99,
        longitude=-122.33,
    )

    bindings, unbound = bind_pois_to_network(
        [poi_near, poi_far],
        urban_road_network,
        max_snap_distance_m=500.0,
        skip_unbound=True,
    )
    assert 1 in bindings
    assert len(unbound) == 1
    assert unbound[0].osm_id == 2


# ============================================================================
# 6. Fleet Allocation Integration Tests
# ============================================================================

def test_poi_to_emergency_station_and_fleet_creation(urban_road_network: Graph) -> None:
    poi_fire = ExtractedEmergencyPOI(
        osm_id=501,
        osm_type="way",
        poi_type=EmergencyPOIType.FIRE_STATION,
        name="Station 501",
        latitude=47.6102,
        longitude=-122.3301,
        capabilities={ClinicalCapability.HAZMAT_DECON},
        apparatus_bays=2,
    )
    poi_hosp = ExtractedEmergencyPOI(
        osm_id=601,
        osm_type="node",
        poi_type=EmergencyPOIType.HOSPITAL,
        name="Trauma Center 601",
        latitude=47.6201,
        longitude=-122.3201,
        capabilities={ClinicalCapability.TRAUMA_LEVEL_1},
    )

    bindings, _ = bind_pois_to_network([poi_fire, poi_hosp], urban_road_network)
    fleet = create_fleet_from_pois([poi_fire, poi_hosp], bindings)

    # Station verification
    station_fire = fleet.get_station("OSM-W-501")
    assert station_fire is not None
    assert station_fire.name == "Station 501"
    assert station_fire.node_id == "n11"

    station_hosp = fleet.get_station("OSM-N-601")
    assert station_hosp is not None
    assert station_hosp.node_id == "n22"

    # Units verification
    units = fleet.get_available_units()
    assert len(units) >= 3  # Fire engines, ladder truck, hospital ambulance
    fire_engines = [u for u in units if u.apparatus_type == ApparatusType.FIRE_ENGINE]
    assert len(fire_engines) >= 1


# ============================================================================
# 7. Specialized Clinical Hospital Routing Tests
# ============================================================================

def test_find_nearest_clinical_facility(urban_road_network: Graph) -> None:
    # Hospital A at n00: Basic hospital, no cardiac care
    hosp_a = ExtractedEmergencyPOI(
        osm_id=10,
        osm_type="node",
        poi_type=EmergencyPOIType.HOSPITAL,
        name="Community Clinic",
        latitude=47.6001,
        longitude=-122.3399,
        capabilities={ClinicalCapability.TRAUMA_LEVEL_4},
        trauma_level=4,
    )
    # Hospital B at n22: Comprehensive Cardiac and Trauma 1 Center
    hosp_b = ExtractedEmergencyPOI(
        osm_id=20,
        osm_type="node",
        poi_type=EmergencyPOIType.HOSPITAL,
        name="Regional Cardiac & Trauma Center",
        latitude=47.6199,
        longitude=-122.3201,
        capabilities={ClinicalCapability.TRAUMA_LEVEL_1, ClinicalCapability.CARDIAC_CARE},
        trauma_level=1,
    )

    bindings, _ = bind_pois_to_network([hosp_a, hosp_b], urban_road_network)

    # Incident occurs at n10 (closest to hosp_a geographically)
    incident_node = "n10"

    # Query 1: Nearest hospital without capability requirements -> should pick hosp_a (distance 100)
    res_any = find_nearest_clinical_facility(
        incident_node_id=incident_node,
        graph=urban_road_network,
        candidate_pois=[hosp_a, hosp_b],
        bindings=bindings,
    )
    assert res_any is not None
    best_poi, best_binding, path, cost = res_any
    assert best_poi.osm_id == 10
    assert cost == 100.0

    # Query 2: Nearest hospital with Cardiac Care requirement -> must bypass hosp_a and pick hosp_b!
    res_cardiac = find_nearest_clinical_facility(
        incident_node_id=incident_node,
        graph=urban_road_network,
        candidate_pois=[hosp_a, hosp_b],
        bindings=bindings,
        required_capabilities={ClinicalCapability.CARDIAC_CARE},
    )
    assert res_cardiac is not None
    cardiac_poi, _, c_path, c_cost = res_cardiac
    assert cardiac_poi.osm_id == 20
    assert cardiac_poi.name == "Regional Cardiac & Trauma Center"
    assert c_cost > 100.0  # Greater distance, but clinically appropriate

    # Query 3: Burn center requirement (neither has burn center) -> None
    res_burn = find_nearest_clinical_facility(
        incident_node_id=incident_node,
        graph=urban_road_network,
        candidate_pois=[hosp_a, hosp_b],
        bindings=bindings,
        required_capabilities={ClinicalCapability.BURN_CENTER},
    )
    assert res_burn is None

    # Query 4: Incident node not in graph -> None
    res_unknown = find_nearest_clinical_facility(
        incident_node_id="non_existent_node",
        graph=urban_road_network,
        candidate_pois=[hosp_a, hosp_b],
        bindings=bindings,
    )
    assert res_unknown is None


def test_batch_bind_skip_unbound_false(urban_road_network: Graph) -> None:
    poi_far = ExtractedEmergencyPOI(
        osm_id=99,
        osm_type="node",
        poi_type=EmergencyPOIType.HOSPITAL,
        name="Distant Hospital",
        latitude=49.0,
        longitude=-122.0,
    )
    with pytest.raises(SpatialBindingError):
        bind_pois_to_network([poi_far], urban_road_network, max_snap_distance_m=100.0, skip_unbound=False)


def test_build_query_all_types() -> None:
    query = build_emergency_poi_query(
        bbox=(47.0, -122.5, 47.5, -122.0),
        poi_types=[
            EmergencyPOIType.DISPATCH_CENTER,
            EmergencyPOIType.URGENT_CARE,
            EmergencyPOIType.AMBULANCE_STATION,
            EmergencyPOIType.POLICE,
        ],
    )
    assert "control_centre" in query
    assert "clinic" in query
    assert "ambulance_station" in query
    assert "police" in query


def test_parse_overpass_edge_cases() -> None:
    malformed_elements = {
        "elements": [
            "not_a_dict",
            {"type": "node"},  # Missing id and tags
            {"type": "node", "id": 1, "lat": 47.0, "lon": -122.0, "tags": "invalid_tags"},
            {"type": "node", "id": 2, "lat": 47.0, "tags": {"amenity": "hospital"}},  # Missing lon
            {"type": "node", "id": 3, "lat": "bad_lat", "lon": -122.0, "tags": {"amenity": "hospital"}},
            {"type": "node", "id": 4, "lat": 95.0, "lon": -122.0, "tags": {"amenity": "hospital"}},  # Out of range
            {
                "type": "way",
                "id": 5,
                "center": {"lat": 47.0, "lon": -122.0},
                "tags": {
                    "amenity": "fire_station",
                    "emergency:trauma_level": "gold",  # Invalid int
                    "bays": "plenty",  # Invalid int
                    "emergency:helipad": "yes",
                    "emergency:decontamination": "yes",
                },
            },
            {
                "type": "relation",
                "id": 6,
                "center": {"lat": 47.1, "lon": -122.1},
                "tags": {
                    "amenity": "hospital",
                    "name": "Regional Hospital",
                    "healthcare:speciality": "burn;stroke",
                },
            },
        ]
    }
    pois = parse_overpass_response(malformed_elements)
    assert len(pois) == 2
    fire_poi = next(p for p in pois if p.osm_id == 5)
    assert fire_poi.trauma_level is None
    assert fire_poi.apparatus_bays is None
    assert fire_poi.has_capability(ClinicalCapability.HELIPAD)
    assert fire_poi.has_capability(ClinicalCapability.HAZMAT_DECON)

    hosp_poi = next(p for p in pois if p.osm_id == 6)
    assert hosp_poi.has_capability(ClinicalCapability.BURN_CENTER)
    assert hosp_poi.has_capability(ClinicalCapability.STROKE_CENTER)


def test_fetch_or_load_corrupted_cache(tmp_path: Path) -> None:
    bad_cache = tmp_path / "corrupted.json"
    bad_cache.write_text("invalid json content", encoding="utf-8")
    with pytest.raises(OverpassParseError, match="Failed to read cached Overpass data"):
        fetch_or_load_overpass_pois(query="q", cache_path=bad_cache, force_refresh=False)


def test_fetch_or_load_http_non_200(monkeypatch: pytest.MonkeyPatch) -> None:
    def mock_urlopen_503(req: Any, timeout: float = 10.0) -> MockHTTPResponse:
        return MockHTTPResponse(b"Service Unavailable", status=503)

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen_503)
    with pytest.raises(OverpassNetworkError, match="returned HTTP 503"):
        fetch_or_load_overpass_pois(query="q", force_refresh=True)


def test_fetch_or_load_generic_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    def mock_urlopen_crash(req: Any, timeout: float = 10.0) -> Any:
        raise RuntimeError("Socket timeout")

    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen_crash)
    with pytest.raises(OverpassNetworkError, match="request failed"):
        fetch_or_load_overpass_pois(query="q", force_refresh=True)


def test_create_fleet_custom_blueprint(urban_road_network: Graph) -> None:
    poi = ExtractedEmergencyPOI(
        osm_id=777,
        osm_type="node",
        poi_type=EmergencyPOIType.AMBULANCE_STATION,
        name="Station 777",
        latitude=47.61,
        longitude=-122.33,
        apparatus_bays=5,
    )
    bindings, _ = bind_pois_to_network([poi], urban_road_network)
    custom_blueprint = {
        EmergencyPOIType.AMBULANCE_STATION: [(ApparatusType.AMBULANCE_ALS, 3, 1.1)],
    }
    fleet = create_fleet_from_pois([poi], bindings, apparatus_blueprint=custom_blueprint)
    station = fleet.get_station("OSM-N-777")
    assert station is not None
    assert len(station.assigned_unit_ids) == 3


def test_find_nearest_facility_edge_cases(urban_road_network: Graph) -> None:
    hosp_unbound = ExtractedEmergencyPOI(
        osm_id=888,
        osm_type="node",
        poi_type=EmergencyPOIType.HOSPITAL,
        name="Unbound Hospital",
        latitude=47.60,
        longitude=-122.33,
        capabilities={ClinicalCapability.TRAUMA_LEVEL_1},
        trauma_level=None,  # Trauma level None when level 1 required
    )
    # Target node not in graph
    fake_binding = POINetworkBinding(
        poi=hosp_unbound,
        nearest_node_id="ghost_node",
        snapped_coordinates=(-122.33, 47.60),
        distance_meters=10.0,
        snapped_to_road=False,
    )
    bindings = {888: fake_binding}

    # Ghost node
    res = find_nearest_clinical_facility(
        incident_node_id="n00",
        graph=urban_road_network,
        candidate_pois=[hosp_unbound],
        bindings=bindings,
    )
    assert res is None

    # Node in graph, but trauma_level required while poi.trauma_level is None
    fake_binding.nearest_node_id = "n00"
    res_trauma = find_nearest_clinical_facility(
        incident_node_id="n10",
        graph=urban_road_network,
        candidate_pois=[hosp_unbound],
        bindings=bindings,
        required_capabilities={ClinicalCapability.TRAUMA_LEVEL_1},
    )
    assert res_trauma is None

