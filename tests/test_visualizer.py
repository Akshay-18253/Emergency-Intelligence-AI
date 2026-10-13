"""
Unit tests for Web Mercator Tile Mathematics & Leaflet GIS Visualizer.
======================================================================
Tests forward and inverse Web Mercator slippy tile transformations,
geographic bounding box calculations, ground resolution physics,
TMS coordinate conversions, and standalone Leaflet HTML visualizer generation.

Strict zero external runtime dependencies (Python standard library only).
"""

from __future__ import annotations

from datetime import datetime, timezone
import math
from pathlib import Path
import pytest

from emergency_intelligence.events.hazards import HazardPolygon, HazardSeverity, HazardType
from emergency_intelligence.external.overpass import (
    ClinicalCapability,
    EmergencyPOIType,
    ExtractedEmergencyPOI,
)
from emergency_intelligence.external.hydrology import FloodStage, USGSGaugeReading
from emergency_intelligence.external.visualizer import (
    MAX_LATITUDE,
    MIN_LATITUDE,
    MapIsochroneOverlay,
    MapRouteOverlay,
    TileBoundingBox,
    clamp_latitude,
    format_tile_url,
    get_tiles_for_bounding_box,
    lat_lon_to_tile_xy,
    normalize_longitude,
    render_interactive_map_html,
    resolution_meters_per_pixel,
    save_interactive_map_html,
    slippy_to_tms_y,
    tile_bounding_box,
    tile_xy_to_lat_lon,
    tms_to_slippy_y,
)
from emergency_intelligence.graph.models import Edge, Graph, Node


# ===========================================================================
# 1. Coordinate Clamping & Normalization Tests
# ===========================================================================


def test_clamp_latitude() -> None:
    """Verify latitude clamping to conformal Web Mercator boundaries."""
    assert clamp_latitude(0.0) == 0.0
    assert clamp_latitude(45.0) == 45.0
    assert clamp_latitude(-45.0) == -45.0
    assert clamp_latitude(90.0) == MAX_LATITUDE
    assert clamp_latitude(86.0) == MAX_LATITUDE
    assert clamp_latitude(-90.0) == MIN_LATITUDE
    assert clamp_latitude(-87.0) == MIN_LATITUDE


def test_normalize_longitude() -> None:
    """Verify longitude normalization to [-180.0, 180.0)."""
    assert normalize_longitude(0.0) == 0.0
    assert normalize_longitude(-122.4) == -122.4
    assert normalize_longitude(180.0) == -180.0  # Periodic boundary
    assert normalize_longitude(-180.0) == -180.0
    assert normalize_longitude(190.0) == -170.0
    assert normalize_longitude(-190.0) == 170.0
    assert normalize_longitude(540.0) == -180.0


# ===========================================================================
# 2. Slippy Map Tile Forward & Inverse Transformations
# ===========================================================================


def test_lat_lon_to_tile_xy_benchmarks() -> None:
    """Verify forward tile projection against standard GIS benchmark coordinates."""
    # Zoom 0: entire world is tile (0, 0)
    assert lat_lon_to_tile_xy(0.0, 0.0, zoom=0) == (0, 0)

    # London (51.5074 N, 0.1278 W) at zoom 10
    tile_x, tile_y = lat_lon_to_tile_xy(51.5074, -0.1278, zoom=10)
    assert tile_x == 511
    assert tile_y == 340

    # New York City (40.7128 N, 74.0060 W) at zoom 12
    tile_x, tile_y = lat_lon_to_tile_xy(40.7128, -74.0060, zoom=12)
    assert tile_x == 1205
    assert tile_y == 1540

    # San Francisco (37.7749 N, 122.4194 W) at zoom 14
    tile_x, tile_y = lat_lon_to_tile_xy(37.7749, -122.4194, zoom=14)
    assert tile_x == 2620
    assert tile_y == 6332


def test_lat_lon_to_tile_xy_invalid_zoom() -> None:
    """Verify negative zoom levels raise ValueError."""
    with pytest.raises(ValueError, match="non-negative"):
        lat_lon_to_tile_xy(37.0, -122.0, zoom=-1)


def test_tile_xy_to_lat_lon_nw_corner() -> None:
    """Verify inverse projection to NW tile corner coordinates."""
    # Zoom 0 tile (0, 0) NW corner should be (MAX_LATITUDE, -180.0)
    lat, lon = tile_xy_to_lat_lon(0, 0, zoom=0)
    assert abs(lat - MAX_LATITUDE) < 1e-4
    assert abs(lon - (-180.0)) < 1e-4

    # Zoom 1: Four quadrants
    # (0, 0) NW: (MAX_LAT, -180)
    # (1, 1) NW: Equator (0, 0)
    lat, lon = tile_xy_to_lat_lon(1, 1, zoom=1)
    assert abs(lat - 0.0) < 1e-4
    assert abs(lon - 0.0) < 1e-4


def test_tile_xy_to_lat_lon_invalid_zoom() -> None:
    """Verify inverse projection raises on negative zoom."""
    with pytest.raises(ValueError, match="non-negative"):
        tile_xy_to_lat_lon(0, 0, zoom=-2)


def test_roundtrip_tile_projection() -> None:
    """Verify forward and inverse tile projection consistency."""
    # Test arbitrary points across diverse locations
    test_coords = [
        (47.6062, -122.3321),  # Seattle
        (35.6762, 139.6503),   # Tokyo
        (-33.8688, 151.2093),  # Sydney
        (-22.9068, -43.1729),  # Rio de Janeiro
    ]
    for lat, lon in test_coords:
        for zoom in (5, 10, 15):
            tx, ty = lat_lon_to_tile_xy(lat, lon, zoom)
            bbox = tile_bounding_box(tx, ty, zoom)
            # Point must lie within tile's geographic bounding box
            assert bbox.min_lat <= lat <= bbox.max_lat or abs(lat - bbox.min_lat) < 1e-5 or abs(lat - bbox.max_lat) < 1e-5
            assert bbox.min_lon <= lon <= bbox.max_lon or abs(lon - bbox.min_lon) < 1e-5 or abs(lon - bbox.max_lon) < 1e-5


# ---------------------------------------------------------------------------
# 3. Tile Bounding Box & Discovery
# ---------------------------------------------------------------------------


def test_tile_bounding_box_properties() -> None:
    """Verify TileBoundingBox metrics and centers."""
    bbox = tile_bounding_box(tile_x=511, tile_y=340, zoom=10)
    assert bbox.tile_x == 511
    assert bbox.tile_y == 340
    assert bbox.zoom == 10
    assert bbox.min_lat < bbox.max_lat
    assert bbox.min_lon < bbox.max_lon
    assert bbox.min_lat < bbox.center_lat < bbox.max_lat
    assert bbox.min_lon < bbox.center_lon < bbox.max_lon


def test_get_tiles_for_bounding_box() -> None:
    """Verify discovering tiles intersecting a geographic envelope."""
    # Small metropolitan bounding box in Seattle at zoom 12
    tiles = get_tiles_for_bounding_box(
        min_lat=47.50,
        min_lon=-122.40,
        max_lat=47.65,
        max_lon=-122.25,
        zoom=12,
    )
    assert len(tiles) >= 1
    # Check all returned tuples are valid coordinates
    for tx, ty in tiles:
        assert isinstance(tx, int)
        assert isinstance(ty, int)
        assert tx >= 0
        assert ty >= 0

    # Inverted min/max inputs should be handled gracefully
    tiles_inv = get_tiles_for_bounding_box(
        min_lat=47.65,
        min_lon=-122.25,
        max_lat=47.50,
        max_lon=-122.40,
        zoom=12,
    )
    assert tiles == tiles_inv


def test_get_tiles_for_bounding_box_invalid_zoom() -> None:
    """Verify get_tiles_for_bounding_box raises on negative zoom."""
    with pytest.raises(ValueError, match="non-negative"):
        get_tiles_for_bounding_box(10.0, 10.0, 12.0, 12.0, zoom=-1)


# ---------------------------------------------------------------------------
# 4. Resolution & Format Helpers
# ---------------------------------------------------------------------------


def test_resolution_meters_per_pixel() -> None:
    """Verify ground resolution calculations."""
    # At zoom 0, equator: ~156,543 meters/pixel
    res_z0 = resolution_meters_per_pixel(lat=0.0, zoom=0)
    assert 156_000.0 < res_z0 < 157_000.0

    # Higher zoom should have finer ground resolution
    res_z16 = resolution_meters_per_pixel(lat=0.0, zoom=16)
    assert 2.0 < res_z16 < 3.0

    # Higher latitude reduces horizontal meter span
    res_pole = resolution_meters_per_pixel(lat=60.0, zoom=16)
    assert abs(res_pole - (res_z16 * math.cos(math.radians(60.0)))) < 1e-4


def test_tms_coordinate_conversions() -> None:
    """Verify Slippy <-> OSGeo TMS Y-coordinate invertibility."""
    for zoom in (1, 4, 10):
        n = 1 << zoom
        for y in (0, n // 2, n - 1):
            tms_y = slippy_to_tms_y(y, zoom)
            recovered_y = tms_to_slippy_y(tms_y, zoom)
            assert recovered_y == y


def test_format_tile_url() -> None:
    """Verify template replacement for XYZ tile servers."""
    url = format_tile_url(tile_x=512, tile_y=256, zoom=10)
    assert url == "https://tile.openstreetmap.org/10/512/256.png"

    custom_url = format_tile_url(
        tile_x=12,
        tile_y=34,
        zoom=5,
        template="https://custom.tiles.org/map/{z}/{x}/{y}.webp",
    )
    assert custom_url == "https://custom.tiles.org/map/5/12/34.webp"


# ---------------------------------------------------------------------------
# 5. Interactive Leaflet HTML Visualizer Tests
# ---------------------------------------------------------------------------


def test_render_interactive_map_html_minimal() -> None:
    """Verify generating a minimal standalone HTML map visualizer."""
    html = render_interactive_map_html(
        center_lat=47.606,
        center_lon=-122.332,
        zoom=13,
        title="Test Minimal Map",
    )

    assert "<!DOCTYPE html>" in html
    assert "<title>Test Minimal Map</title>" in html
    assert "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js" in html
    assert "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" in html
    assert 'center: [47.606, -122.332]' in html
    assert 'zoom: 13' in html


def test_render_interactive_map_html_full_features() -> None:
    """Verify rendering map with graphs, POIs, gauges, hazards, routes, and isochrones."""
    # 1. Graph
    graph = Graph()
    graph.add_node(Node("N1", coordinates=(-122.02, 47.50)))
    graph.add_node(Node("N2", coordinates=(-122.00, 47.50)))
    graph.add_edge(Edge("N1", "N2", cost=1500.0, attributes={"grade_percent": 12.0, "highway": "primary"}))

    # 2. POIs
    poi = ExtractedEmergencyPOI(
        osm_id=101,
        osm_type="way",
        poi_type=EmergencyPOIType.HOSPITAL,
        name="Harborview Medical Center",
        latitude=47.50,
        longitude=-122.02,
        capabilities={ClinicalCapability.TRAUMA_LEVEL_1, ClinicalCapability.BURN_CENTER},
        trauma_level=1,
        apparatus_bays=6,
        phone="911",
    )

    # 3. Gauges
    gauge = USGSGaugeReading(
        site_id="12144500",
        site_name="Snoqualmie River Gauge",
        latitude=47.50,
        longitude=-122.00,
        timestamp=datetime.now(timezone.utc),
        gage_height_ft=22.5,
        flood_stage=FloodStage.MAJOR,
    )

    # 4. Hazards
    hazard = HazardPolygon(
        hazard_id="haz_flood_1",
        hazard_type=HazardType.FLOOD_INUNDATION,
        severity=HazardSeverity.CRITICAL_BLOCKED,
        boundary_coordinates=[
            (-122.005, 47.495),
            (-121.995, 47.495),
            (-121.995, 47.505),
            (-122.005, 47.505),
        ],
        description="Major Flood Inundation",
    )

    # 5. Route
    route = MapRouteOverlay(
        route_id="r1",
        label="Ambulance Reroute Detour",
        path_nodes=["N1", "N2"],
        color="#EF4444",
        total_cost=1500.0,
    )

    # 6. Isochrone
    iso = MapIsochroneOverlay(
        isochrone_id="iso_240",
        label="NFPA 1710 240s Frontier",
        threshold_seconds=240.0,
        boundary_coordinates=[
            (-122.03, 47.49),
            (-121.99, 47.49),
            (-121.99, 47.51),
            (-122.03, 47.51),
        ],
    )

    html = render_interactive_map_html(
        center_lat=47.50,
        center_lon=-122.00,
        zoom=14,
        title="Emergency Tactical GIS",
        graph=graph,
        pois=[poi],
        gauges=[gauge],
        hazards=[hazard],
        routes=[route],
        isochrones=[iso],
        show_playback_hud=True,
    )

    # Check key components are embedded in the output
    assert "Harborview Medical Center" in html
    assert "Trauma Level 1" in html
    assert "Snoqualmie River Gauge" in html
    assert "MAJOR" in html
    assert "Major Flood Inundation" in html
    assert "Ambulance Reroute Detour" in html
    assert "NFPA 1710 240s Frontier" in html
    assert 'display: flex' in html  # Playback HUD enabled


def test_save_interactive_map_html(tmp_path: Path) -> None:
    """Verify saving interactive HTML map to disk."""
    out_file = tmp_path / "subfolder" / "emergency_map.html"
    content = "<html><body><h1>Tactical Map</h1></body></html>"

    saved_path = save_interactive_map_html(content, out_file)
    assert saved_path.is_file()
    assert saved_path == out_file.resolve()
    assert saved_path.read_text(encoding="utf-8") == content
