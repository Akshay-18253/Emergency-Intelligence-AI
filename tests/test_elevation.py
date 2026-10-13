"""
Unit tests for NASA SRTM Digital Elevation Models (DEM) & Slope Cost Weighting.
==============================================================================
Tests NASA SRTM binary parsing, sub-grid bilinear interpolation, slope kinematics,
apparatus climb/descent speed multipliers, graph elevation enrichment, and dynamic
incline routing views with zero external runtime dependencies.
"""

from __future__ import annotations

import math
from pathlib import Path
import struct
import pytest

from emergency_intelligence.events.incidents import ApparatusType
from emergency_intelligence.external.elevation import (
    APPARATUS_GRADE_PROFILES,
    DEMResolution,
    ElevationEnrichmentSummary,
    ElevationGraphView,
    ElevationProvider,
    SlopeMetrics,
    SRTMTile,
    SRTM_VOID_VALUE,
    build_synthetic_dem_tile,
    calculate_slope_metrics,
    enrich_graph_with_elevation,
    format_srtm_tile_name,
    get_grade_speed_multiplier,
    parse_srtm_tile_name,
)
from emergency_intelligence.graph.astar import astar
from emergency_intelligence.graph.dijkstra import dijkstra
from emergency_intelligence.graph.models import Edge, Graph, Node


# ===========================================================================
# 1. Tile Naming & Format Tests
# ===========================================================================


def test_parse_srtm_tile_name_valid() -> None:
    """Verify parsing of valid SRTM tile filenames."""
    assert parse_srtm_tile_name("N37W123.hgt") == (37, -123)
    assert parse_srtm_tile_name("S12E045.hgt") == (-12, 45)
    assert parse_srtm_tile_name("n00e000.hgt") == (0, 0)
    assert parse_srtm_tile_name("N00W000") == (0, 0)
    assert parse_srtm_tile_name("path/to/S45W070.hgt") == (-45, -70)
    assert parse_srtm_tile_name("N89E179.hgt") == (89, 179)


def test_parse_srtm_tile_name_invalid() -> None:
    """Verify error handling on invalid tile names."""
    with pytest.raises(ValueError, match="Invalid SRTM tile filename"):
        parse_srtm_tile_name("invalid_name.hgt")

    with pytest.raises(ValueError, match="Invalid SRTM tile filename"):
        parse_srtm_tile_name("N37W12.hgt")  # Longitude must be 3 digits

    with pytest.raises(ValueError, match="SRTM latitude 95 out of valid range"):
        parse_srtm_tile_name("N95W020.hgt")

    with pytest.raises(ValueError, match="SRTM longitude -185 out of valid range"):
        parse_srtm_tile_name("N10W185.hgt")


def test_format_srtm_tile_name() -> None:
    """Verify formatting of tile names from coordinates."""
    assert format_srtm_tile_name(37, -123) == "N37W123.hgt"
    assert format_srtm_tile_name(-12, 45) == "S12E045.hgt"
    assert format_srtm_tile_name(0, 0) == "N00E000.hgt"
    assert format_srtm_tile_name(-45, -70) == "S45W070.hgt"


# ===========================================================================
# 2. SRTMTile Construction & Binary Buffer Validation
# ===========================================================================


def test_srtm_tile_post_init_validation() -> None:
    """Verify validation constraints in SRTMTile.__post_init__."""
    with pytest.raises(ValueError, match="dimension must be at least 2"):
        SRTMTile(tile_name="N00E000.hgt", lat_origin=0, lon_origin=0, dimension=1)

    with pytest.raises(ValueError, match="must have either _buffer or _samples"):
        SRTMTile(tile_name="N00E000.hgt", lat_origin=0, lon_origin=0, dimension=5)

    # Buffer length mismatch
    with pytest.raises(ValueError, match="Buffer size 10 bytes does not match"):
        SRTMTile(
            tile_name="N00E000.hgt",
            lat_origin=0,
            lon_origin=0,
            dimension=5,
            _buffer=b"0123456789",  # Needs 5*5*2 = 50 bytes
        )

    # Sample count mismatch
    with pytest.raises(ValueError, match="Sample count 4 does not match"):
        SRTMTile(
            tile_name="N00E000.hgt",
            lat_origin=0,
            lon_origin=0,
            dimension=3,
            _samples=(10, 20, 30, 40),  # Needs 9 samples
        )


def test_srtm_tile_from_samples() -> None:
    """Verify creating a tile from in-memory sample tuples."""
    samples = [100, 110, 120, 130]  # 2x2 grid
    tile = SRTMTile.from_samples(
        samples=samples,
        lat_origin=37,
        lon_origin=-122,
        dimension=2,
    )
    assert tile.dimension == 2
    assert tile.lat_origin == 37
    assert tile.lon_origin == -122
    assert tile.get_sample(0, 0) == 100
    assert tile.get_sample(0, 1) == 110
    assert tile.get_sample(1, 0) == 120
    assert tile.get_sample(1, 1) == 130

    with pytest.raises(IndexError, match="out of bounds"):
        tile.get_sample(2, 0)


def test_srtm_tile_from_bytes_and_file(tmp_path: Path) -> None:
    """Verify creating a tile from raw bytes and file."""
    # 3x3 grid = 9 samples = 18 bytes
    samples = [10, 20, 30, 40, 50, 60, 70, 80, 90]
    data = struct.pack(">9h", *samples)

    tile = SRTMTile.from_bytes(data, tile_name="N30E010.hgt", dimension=3)
    assert tile.dimension == 3
    assert tile.get_sample(1, 1) == 50

    # Auto-detect dimension for square buffer
    tile_auto = SRTMTile.from_bytes(data, tile_name="N30E010.hgt")
    assert tile_auto.dimension == 3

    # File reading
    file_path = tmp_path / "N30E010.hgt"
    file_path.write_bytes(data)

    tile_from_file = SRTMTile.from_file(file_path)
    assert tile_from_file.dimension == 3
    assert tile_from_file.get_sample(2, 2) == 90

    # Non-existent file
    with pytest.raises(FileNotFoundError):
        SRTMTile.from_file(tmp_path / "non_existent.hgt")

    # Invalid byte buffer size that is not square
    invalid_data = b"012345"  # 6 bytes = 3 samples (not a perfect square)
    with pytest.raises(ValueError, match="Cannot deduce dimension"):
        SRTMTile.from_bytes(invalid_data, tile_name="N00E000.hgt")

    bad_file = tmp_path / "N00E000.hgt"
    bad_file.write_bytes(invalid_data)
    with pytest.raises(ValueError, match="Unrecognized SRTM file size"):
        SRTMTile.from_file(bad_file)


# ===========================================================================
# 3. Spatial Bounds & Bilinear Interpolation
# ===========================================================================


def test_srtm_tile_contains() -> None:
    """Verify spatial boundary testing for a 1x1 degree tile."""
    tile = build_synthetic_dem_tile(lat_origin=37, lon_origin=-122, dimension=5)
    assert tile.contains(37.0, -122.0)
    assert tile.contains(37.5, -121.5)
    assert tile.contains(38.0, -121.0)
    assert not tile.contains(36.9, -121.5)
    assert not tile.contains(38.1, -121.5)
    assert not tile.contains(37.5, -122.1)
    assert not tile.contains(37.5, -120.9)


def test_srtm_tile_bilinear_interpolation() -> None:
    """Verify bilinear interpolation across grid vertices."""
    # 3x3 grid:
    # Row 0 (lat 38.0): 200, 250, 300
    # Row 1 (lat 37.5): 100, 150, 200
    # Row 2 (lat 37.0):   0,  50, 100
    # Col 0 (-122.0), Col 1 (-121.5), Col 2 (-121.0)
    samples = [
        200, 250, 300,
        100, 150, 200,
          0,  50, 100,
    ]
    tile = SRTMTile.from_samples(
        samples=samples,
        lat_origin=37,
        lon_origin=-122,
        dimension=3,
    )

    # Exact corner points
    assert tile.get_elevation(37.0, -122.0) == 0.0
    assert tile.get_elevation(38.0, -122.0) == 200.0
    assert tile.get_elevation(37.0, -121.0) == 100.0
    assert tile.get_elevation(38.0, -121.0) == 300.0
    assert tile.get_elevation(37.5, -121.5) == 150.0

    # Sub-grid point (37.25, -121.75): exactly midway in southwest 2x2 sub-cell
    # Southwest sub-cell:
    # North: (Row 1): 100, 150
    # South: (Row 2):   0,  50
    # Midpoint should be average of (100+150+0+50)/4 = 75.0
    elev = tile.get_elevation(37.25, -121.75)
    assert elev is not None
    assert pytest.approx(elev, 0.01) == 75.0

    # Nearest neighbor interpolation
    assert tile.get_elevation(37.1, -121.9, interpolate=False) == 0.0
    assert tile.get_elevation(37.9, -121.9, interpolate=False) == 200.0

    # Out of bounds coordinate
    assert tile.get_elevation(40.0, -122.0) is None


def test_srtm_tile_void_handling() -> None:
    """Verify graceful handling of void data (-32768) during interpolation."""
    # 2x2 grid with 1 void corner:
    # Row 0: 100, 200
    # Row 1:  50, VOID
    samples = [100, 200, 50, SRTM_VOID_VALUE]
    tile = SRTMTile.from_samples(
        samples=samples,
        lat_origin=37,
        lon_origin=-122,
        dimension=2,
    )

    # Nearest neighbor on void corner returns None
    assert tile.get_elevation(37.0, -121.0, interpolate=False) is None

    # Bilinear interpolation ignores void corner and renormalizes over 3 valid corners
    elev = tile.get_elevation(37.5, -121.5, interpolate=True)
    assert elev is not None
    # Each corner would have weight 0.25; with 1 void, weights are 0.25 / 0.75 = 1/3 each
    # Expected: (100 + 200 + 50) / 3 = 116.666...
    assert pytest.approx(elev, 0.01) == (100.0 + 200.0 + 50.0) / 3.0

    # All void corners
    all_void = SRTMTile.from_samples(
        samples=[SRTM_VOID_VALUE] * 4,
        lat_origin=37,
        lon_origin=-122,
        dimension=2,
    )
    assert all_void.get_elevation(37.5, -121.5, interpolate=True) is None


# ===========================================================================
# 4. Synthetic DEM Builder Tests
# ===========================================================================


def test_build_synthetic_dem_tile() -> None:
    """Verify generation of synthetic DEM tiles with custom slope and functions."""
    with pytest.raises(ValueError, match="Dimension must be at least 2"):
        build_synthetic_dem_tile(37, -122, dimension=1)

    tile = build_synthetic_dem_tile(
        lat_origin=37,
        lon_origin=-122,
        dimension=11,
        base_elevation=100.0,
        slope_north_per_deg=500.0,
        slope_east_per_deg=200.0,
    )
    assert tile.dimension == 11
    assert tile.contains(37.5, -121.5)

    # Southwest corner (lat 37.0, lon -122.0)
    assert pytest.approx(tile.get_elevation(37.0, -122.0), 1.0) == 100.0

    # Northeast corner (lat 38.0, lon -121.0) -> 100 + 500 + 200 = 800.0
    assert pytest.approx(tile.get_elevation(38.0, -121.0), 1.0) == 800.0

    # Custom callable function
    func_tile = build_synthetic_dem_tile(
        lat_origin=37,
        lon_origin=-122,
        dimension=5,
        elevation_fn=lambda lat, lon: 50.0 + (lat - 37.0) * 10.0,
        void_coordinates=[(0, 0)],
    )
    assert func_tile.get_sample(0, 0) == SRTM_VOID_VALUE
    assert func_tile.get_sample(4, 4) == 50


# ===========================================================================
# 5. ElevationProvider Multi-Tile Cache Tests
# ===========================================================================


def test_elevation_provider_cache_and_directory(tmp_path: Path) -> None:
    """Verify ElevationProvider caching, file discovery, and fallback behavior."""
    provider = ElevationProvider(tile_directory=tmp_path, default_elevation=42.0)

    # In-memory tile for (37, -123)
    tile1 = build_synthetic_dem_tile(37, -123, dimension=5, base_elevation=150.0)
    provider.add_tile(tile1)

    # Disk tile for (37, -122) saved in tmp_path
    tile2 = build_synthetic_dem_tile(37, -122, dimension=5, base_elevation=250.0)
    file_path = tmp_path / "N37W122.hgt"
    if tile2._buffer is not None:
        file_path.write_bytes(tile2._buffer)

    # Query tile1 (from memory cache)
    elev1 = provider.get_elevation(37.5, -122.5)
    assert elev1 is not None
    assert pytest.approx(elev1, 1.0) == 150.0

    # Query tile2 (auto-loaded from directory)
    elev2 = provider.get_elevation(37.5, -121.5)
    assert elev2 is not None
    assert pytest.approx(elev2, 1.0) == 250.0

    # Missing tile outside region -> None and default fallback
    assert provider.get_elevation(45.0, 10.0) is None
    assert provider.get_elevation_or_default(45.0, 10.0) == 42.0

    # Non-finite coordinates
    assert provider.get_elevation(float("nan"), -122.0) is None
    assert provider.get_elevation(37.0, float("inf")) is None


# ===========================================================================
# 6. Slope & Incline Kinematics Tests
# ===========================================================================


def test_calculate_slope_metrics() -> None:
    """Verify slope geometry, 3D Euclidean distance, and grade percent."""
    # Point 1 to Point 2: ~111,000 meters horizontal distance along meridian
    coord1 = (-122.0, 37.0)
    coord2 = (-122.0, 37.01)  # ~1113 meters north

    metrics_flat = calculate_slope_metrics(coord1, 100.0, coord2, 100.0)
    assert metrics_flat.horizontal_distance_m > 1000.0
    assert metrics_flat.vertical_delta_m == 0.0
    assert metrics_flat.grade_percent == 0.0
    assert metrics_flat.slope_angle_deg == 0.0

    # Uphill climb: 100m rise over ~1113m distance -> ~9% grade
    metrics_uphill = calculate_slope_metrics(coord1, 100.0, coord2, 200.0)
    assert metrics_uphill.vertical_delta_m == 100.0
    assert metrics_uphill.distance_3d_m > metrics_uphill.horizontal_distance_m
    assert metrics_uphill.grade_percent > 8.0
    assert metrics_uphill.slope_angle_deg > 0.0

    # Downhill descent: 50m drop
    metrics_downhill = calculate_slope_metrics(coord1, 150.0, coord2, 100.0)
    assert metrics_downhill.vertical_delta_m == -50.0
    assert metrics_downhill.grade_percent < 0.0
    assert metrics_downhill.slope_angle_deg < 0.0

    # Zero distance identical coordinates
    metrics_zero = calculate_slope_metrics(coord1, 50.0, coord1, 50.0)
    assert metrics_zero.horizontal_distance_m == 0.0
    assert metrics_zero.grade_percent == 0.0
    assert metrics_zero.slope_angle_deg == 0.0


# ===========================================================================
# 7. Apparatus Grade Speed Multiplier Tests
# ===========================================================================


def test_apparatus_grade_speed_multiplier_flat() -> None:
    """Verify flat terrain returns nominal multiplier 1.0."""
    for app_type in ApparatusType:
        assert get_grade_speed_multiplier(app_type, 0.0) == 1.0
        assert get_grade_speed_multiplier(app_type, 0.8) == 1.0
        assert get_grade_speed_multiplier(app_type, -0.8) == 1.0


def test_apparatus_grade_speed_multiplier_climb() -> None:
    """Verify climb speed degradation and apparatus-specific impassable thresholds."""
    # Light Ambulance vs Heavy Ladder Truck on 10% grade
    amb_mult = get_grade_speed_multiplier(ApparatusType.AMBULANCE_ALS, 10.0)
    ladder_mult = get_grade_speed_multiplier(ApparatusType.LADDER_TRUCK, 10.0)
    engine_mult = get_grade_speed_multiplier(ApparatusType.FIRE_ENGINE, 10.0)

    assert 0.0 < ladder_mult < engine_mult < amb_mult < 1.0

    # Extreme 15% grade:
    # Ladder truck max climb is 14% -> must return 0.0 (impassable!)
    # Fire engine max climb is 18% -> passable crawl
    # Ambulance max climb is 26% -> passable
    assert get_grade_speed_multiplier(ApparatusType.LADDER_TRUCK, 15.0) == 0.0
    assert get_grade_speed_multiplier(ApparatusType.FIRE_ENGINE, 15.0) > 0.0
    assert get_grade_speed_multiplier(ApparatusType.AMBULANCE_ALS, 15.0) > 0.0

    # Impossible 35% grade: all municipal vehicles impassable
    assert get_grade_speed_multiplier(ApparatusType.AMBULANCE_ALS, 35.0) == 0.0
    assert get_grade_speed_multiplier(ApparatusType.BATTALION_CHIEF, 35.0) == 0.0


def test_apparatus_grade_speed_multiplier_descent() -> None:
    """Verify downhill descent speed penalties and runaway limits."""
    # Moderate descent (-4%): minimal penalty
    assert get_grade_speed_multiplier(ApparatusType.FIRE_ENGINE, -4.0) > 0.90

    # Steep descent (-12%): low gearing / braking required
    steep_mult = get_grade_speed_multiplier(ApparatusType.FIRE_ENGINE, -12.0)
    assert 0.35 <= steep_mult < 0.90

    # Runaway hazard descent (-25%):
    # Ladder truck max descent is 16% -> 0.0
    # Fire engine max descent is 20% -> 0.0
    # Ambulance max descent is 28% -> passable with heavy braking
    assert get_grade_speed_multiplier(ApparatusType.LADDER_TRUCK, -25.0) == 0.0
    assert get_grade_speed_multiplier(ApparatusType.FIRE_ENGINE, -25.0) == 0.0
    assert get_grade_speed_multiplier(ApparatusType.AMBULANCE_ALS, -25.0) > 0.0


# ===========================================================================
# 8. Graph Elevation Enrichment Tests
# ===========================================================================


def test_enrich_graph_with_elevation() -> None:
    """Verify node and edge annotation with elevation and slope attributes."""
    graph = Graph()
    # Node A: (lon -122.0, lat 37.0) -> elev 100m
    # Node B: (lon -122.0, lat 37.01) -> elev 250m
    # Node C: (lon -122.01, lat 37.0) -> elev 100m
    # Node A: (lon -122.5, lat 37.0) -> elev 100m
    # Node B: (lon -122.5, lat 37.01) -> elev 250m
    # Node C: (lon -122.51, lat 37.0) -> elev 100m
    graph.add_node(Node("A", coordinates=(-122.5, 37.0)))
    graph.add_node(Node("B", coordinates=(-122.5, 37.01)))
    graph.add_node(Node("C", coordinates=(-122.51, 37.0)))

    graph.add_edge(Edge("A", "B", cost=60.0))  # Uphill A -> B
    graph.add_edge(Edge("B", "A", cost=60.0))  # Downhill B -> A
    graph.add_edge(Edge("A", "C", cost=45.0))  # Flat A -> C

    # Mock provider: elev = 100 + (lat - 37.0) * 15000
    tile = build_synthetic_dem_tile(
        lat_origin=37,
        lon_origin=-123,
        dimension=11,
        elevation_fn=lambda lat, lon: 100.0 + (lat - 37.0) * 15000.0,
    )
    provider = ElevationProvider()
    provider.add_tile(tile)

    summary = enrich_graph_with_elevation(graph, provider)

    assert summary.nodes_enriched == 3
    assert summary.edges_enriched == 3
    assert summary.min_elevation_m == pytest.approx(100.0, 1.0)
    assert summary.max_elevation_m == pytest.approx(250.0, 1.0)
    assert summary.max_uphill_grade_percent > 10.0
    assert summary.max_downhill_grade_percent < -10.0

    # Verify edge attributes
    edge_ab = next(e for e in graph.get_neighbors("A") if e.destination_id == "B")
    assert edge_ab is not None
    assert edge_ab.attributes["elevation_source"] == pytest.approx(100.0, 1.0)
    assert edge_ab.attributes["elevation_destination"] == pytest.approx(250.0, 1.0)
    assert edge_ab.attributes["elevation_delta_m"] == pytest.approx(150.0, 1.0)
    assert edge_ab.attributes["grade_percent"] > 10.0
    assert edge_ab.attributes["distance_3d_m"] > 1000.0


def test_enrich_graph_without_coordinates() -> None:
    """Verify fallback behavior when nodes lack geographic coordinates."""
    graph = Graph()
    graph.add_node(Node("X"))
    graph.add_node(Node("Y"))
    graph.add_edge(Edge("X", "Y", cost=100.0, attributes={"distance_m": 500.0}))

    provider = ElevationProvider(default_elevation=50.0)
    summary = enrich_graph_with_elevation(graph, provider, default_elevation=50.0)

    assert summary.nodes_enriched == 2
    assert summary.edges_enriched == 1
    edge = next(e for e in graph.get_neighbors("X") if e.destination_id == "Y")
    assert edge is not None
    assert edge.attributes["grade_percent"] == 0.0


# ===========================================================================
# 9. ElevationGraphView & Incline-Aware Routing
# ===========================================================================


def test_elevation_graph_view_interface() -> None:
    """Verify Graph interface compliance of ElevationGraphView."""
    graph = Graph()
    graph.add_node(Node("N1", coordinates=(-122.0, 37.0)))
    graph.add_node(Node("N2", coordinates=(-122.0, 37.01)))
    edge = Edge("N1", "N2", cost=60.0, attributes={"grade_percent": 8.0, "distance_3d_m": 1200.0, "distance_m": 1000.0})
    graph.add_edge(edge)

    view = ElevationGraphView(graph, apparatus_type=ApparatusType.FIRE_ENGINE)
    assert view.has_node("N1")
    assert view.has_edge("N1", "N2")
    assert view.node_count() == 2
    assert view.edge_count() == 1
    assert view.node_ids() == ["N1", "N2"]

    # Traversal cost is inflated due to grade penalty and 3D distance
    modified_edge = view.get_edge("N1", "N2")
    assert modified_edge is not None
    assert modified_edge.cost > 60.0
    assert "effective_grade_multiplier" in modified_edge.attributes


def test_elevation_aware_routing_detour() -> None:
    """Verify that heavy apparatus (Ladder Truck) automatically detours around steep grades."""
    # Graph Topology:
    # Origin: S, Destination: D
    # Path 1 (Direct Hill): S -> H -> D (Short but steep 15% grade!)
    # Path 2 (Valley Bypass): S -> V -> D (Longer flat road 0% grade!)
    graph = Graph()
    graph.add_node(Node("S", coordinates=(-122.0, 37.0)))
    graph.add_node(Node("H", coordinates=(-122.0, 37.01)))
    graph.add_node(Node("D", coordinates=(-122.0, 37.02)))
    graph.add_node(Node("V", coordinates=(-122.02, 37.01)))

    # Direct steep hill: 15% grade on S -> H (cost = 100 / 0.6126 = 163.22 + 100 = 263.22)
    graph.add_edge(Edge("S", "H", cost=100.0, attributes={"grade_percent": 15.0}))
    graph.add_edge(Edge("H", "D", cost=100.0, attributes={"grade_percent": 0.0}))

    # Flat valley bypass: 0% grade, higher base distance/cost (300.0 total > 263.22)
    graph.add_edge(Edge("S", "V", cost=150.0, attributes={"grade_percent": 0.0}))
    graph.add_edge(Edge("V", "D", cost=150.0, attributes={"grade_percent": 0.0}))

    # Case 1: Ambulance (can climb 15% grade)
    ambulance_view = ElevationGraphView(graph, apparatus_type=ApparatusType.AMBULANCE_ALS)
    route_amb = astar(ambulance_view, "S", "D")
    assert route_amb.reachable
    # Ambulance takes direct steep hill path: S -> H -> D
    assert route_amb.path == ["S", "H", "D"]

    # Case 2: Aerial Ladder Truck (max climb is 14% -> S->H is impassable!)
    ladder_view = ElevationGraphView(graph, apparatus_type=ApparatusType.LADDER_TRUCK)
    route_ladder = astar(ladder_view, "S", "D")
    assert route_ladder.reachable
    # Ladder truck is forced to take the flat valley detour: S -> V -> D
    assert route_ladder.path == ["S", "V", "D"]

    # Case 3: Verify Dijkstra produces identical detour
    dijkstra_ladder = dijkstra(ladder_view, "S", "D")
    assert dijkstra_ladder.reachable
    assert dijkstra_ladder.path == ["S", "V", "D"]
