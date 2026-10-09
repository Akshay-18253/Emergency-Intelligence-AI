"""
Unit tests for spatial indexing, point-to-segment projection, road snapping,
and compiled network cache serialization with SHA-256 integrity verification.
"""

import json
from pathlib import Path
import pytest

from emergency_intelligence.data import (
    CACHE_SCHEMA_VERSION,
    SAMPLE_HOSPITAL_DISTRICT_PATH,
    SnappedLocation,
    SpatialIndex,
    compute_file_checksum,
    load_graph_cache,
    load_osm_graph_from_file,
    project_point_to_segment,
    save_graph_cache,
)
from emergency_intelligence.data.geo import haversine_distance
from emergency_intelligence.graph.models import Edge, Graph, Node


# ---------------------------------------------------------------------------
# 1. Point-to-Segment Projection Tests
# ---------------------------------------------------------------------------


class TestPointProjection:
    def test_point_directly_on_segment_midpoint(self):
        seg_a = (0.0, 0.0)
        seg_b = (2.0, 0.0)
        p = (1.0, 0.0)

        proj, dist_m, t = project_point_to_segment(p, seg_a, seg_b)
        assert proj == pytest.approx((1.0, 0.0))
        assert dist_m == pytest.approx(0.0, abs=1e-3)
        assert t == pytest.approx(0.5)

    def test_point_perpendicular_offset(self):
        # Horizontal segment along latitude 37.0 from lon -122.0 to -122.1
        seg_a = (-122.0, 37.0)
        seg_b = (-122.1, 37.0)
        # Point offset slightly north at lon -122.05, lat 37.001
        p = (-122.05, 37.001)

        proj, dist_m, t = project_point_to_segment(p, seg_a, seg_b)
        assert proj[0] == pytest.approx(-122.05)
        assert proj[1] == pytest.approx(37.0)
        assert t == pytest.approx(0.5)
        assert dist_m > 50.0  # ~111 meters for 0.001 lat
        assert dist_m < 150.0

    def test_point_clamped_to_segment_start(self):
        seg_a = (0.0, 0.0)
        seg_b = (1.0, 0.0)
        p = (-0.5, 0.5)  # Behind segment start

        proj, dist_m, t = project_point_to_segment(p, seg_a, seg_b)
        assert proj == pytest.approx(seg_a)
        assert t == 0.0

    def test_point_clamped_to_segment_end(self):
        seg_a = (0.0, 0.0)
        seg_b = (1.0, 0.0)
        p = (1.5, 0.5)  # Beyond segment end

        proj, dist_m, t = project_point_to_segment(p, seg_a, seg_b)
        assert proj == pytest.approx(seg_b)
        assert t == 1.0

    def test_degenerate_zero_length_segment(self):
        seg_a = (-122.4, 37.7)
        seg_b = (-122.4, 37.7)
        p = (-122.41, 37.71)

        proj, dist_m, t = project_point_to_segment(p, seg_a, seg_b)
        assert proj == seg_a
        assert t == 0.0
        assert dist_m > 0.0


# ---------------------------------------------------------------------------
# 2. Spatial Index & Nearest-Node Query Tests
# ---------------------------------------------------------------------------


class TestSpatialIndex:
    def test_invalid_cell_size_raises(self):
        g = Graph()
        with pytest.raises(ValueError, match="strictly positive"):
            SpatialIndex(g, cell_size_deg=0.0)
        with pytest.raises(ValueError, match="strictly positive"):
            SpatialIndex(g, cell_size_deg=-0.05)

    def test_empty_graph_index_query_raises(self):
        g = Graph()
        idx = SpatialIndex(g)
        assert idx.indexed_nodes_count == 0
        with pytest.raises(ValueError, match="empty spatial index"):
            idx.nearest_node((-122.4, 37.7))

    def test_single_node_index(self):
        g = Graph()
        g.add_node(Node("HOSPITAL", coordinates=(-122.4194, 37.7749)))
        idx = SpatialIndex(g)
        assert idx.indexed_nodes_count == 1

        nearest_id, dist_m = idx.nearest_node((-122.4190, 37.7745))
        assert nearest_id == "HOSPITAL"
        assert dist_m > 0.0

    def test_nearest_node_matches_brute_force_baseline(self):
        # Load real hospital district
        graph = load_osm_graph_from_file(SAMPLE_HOSPITAL_DISTRICT_PATH)
        idx = SpatialIndex(graph, cell_size_deg=0.002)
        assert idx.indexed_nodes_count == 11

        test_points = [
            (-122.4194, 37.7749),  # Exactly at Node 1001
            (-122.4180, 37.7760),  # In between nodes
            (-122.4170, 37.7770),
            (-122.4200, 37.7740),
        ]

        for pt in test_points:
            # Spatial index query
            fast_id, fast_dist = idx.nearest_node(pt)

            # Brute force linear scan
            brute_id = None
            brute_dist = float("inf")
            for nid in graph.node_ids():
                coords = graph.get_node(nid).coordinates
                if coords:
                    d = haversine_distance(pt, coords, unit="m")
                    if d < brute_dist:
                        brute_dist = d
                        brute_id = nid

            assert fast_id == brute_id
            assert fast_dist == pytest.approx(brute_dist, rel=1e-5)

    def test_search_radius_exceeded_raises(self):
        g = Graph()
        g.add_node(Node("SAN_FRANCISCO", coordinates=(-122.4194, 37.7749)))
        idx = SpatialIndex(g)

        # Query in Tokyo, Japan (thousands of km away) with a 10 km limit
        with pytest.raises(ValueError, match="No road node found within"):
            idx.nearest_node((139.6917, 35.6895), max_search_radius_m=10000.0)


# ---------------------------------------------------------------------------
# 3. Road Segment Snapping Tests
# ---------------------------------------------------------------------------


class TestRoadSnapping:
    def test_snap_to_road_network_mid_block(self):
        # Construct two street nodes along 10th St
        g = Graph()
        g.add_node(Node("1001", coordinates=(-122.419416, 37.774929)))
        g.add_node(Node("1002", coordinates=(-122.419416, 37.775820)))
        g.add_edge(Edge("1001", "1002", cost=100.0))

        idx = SpatialIndex(g)

        # Incident location slightly east of the street block (inside a building)
        caller_gps = (-122.419000, 37.775375)
        snapped = idx.snap_to_road_network(caller_gps)

        assert isinstance(snapped, SnappedLocation)
        assert snapped.original_coordinates == caller_gps
        # Snapped longitude should be on the street (-122.419416)
        assert snapped.snapped_coordinates[0] == pytest.approx(-122.419416, abs=1e-5)
        assert snapped.distance_to_road_m > 10.0  # Some offset distance
        assert snapped.nearest_edge is not None
        assert snapped.nearest_edge.source_id == "1001"
        assert snapped.nearest_edge.destination_id == "1002"
        assert 0.0 < snapped.projection_factor < 1.0


# ---------------------------------------------------------------------------
# 4. Compiled Network Cache Tests
# ---------------------------------------------------------------------------


class TestNetworkCache:
    def test_cache_round_trip_equality(self, tmp_path: Path):
        orig_graph = load_osm_graph_from_file(SAMPLE_HOSPITAL_DISTRICT_PATH)
        cache_file = tmp_path / "district.eig.json"

        # Save cache
        saved_path = save_graph_cache(orig_graph, cache_file, source_checksum="abc123hash")
        assert saved_path.is_file()

        # Load cache
        loaded_graph, meta = load_graph_cache(cache_file, verify_checksum=True)

        assert loaded_graph.node_count() == orig_graph.node_count()
        assert loaded_graph.edge_count() == orig_graph.edge_count()
        assert meta["schema_version"] == CACHE_SCHEMA_VERSION
        assert meta["source_checksum"] == "abc123hash"
        assert meta["node_count"] == 11
        assert meta["edge_count"] == 25

        # Check node coordinates preserved
        node = loaded_graph.get_node("1001")
        assert node.coordinates == orig_graph.get_node("1001").coordinates
        assert node.label == orig_graph.get_node("1001").label

        # Check edge cost and attributes preserved
        e_orig = orig_graph.get_neighbors("1001")[0]
        e_loaded = loaded_graph.get_neighbors("1001")[0]
        assert e_orig.cost == pytest.approx(e_loaded.cost)
        assert e_orig.attributes.get("highway") == e_loaded.attributes.get("highway")

    def test_compute_file_checksum(self, tmp_path: Path):
        dummy_file = tmp_path / "dummy.txt"
        dummy_file.write_text("emergency routing verification", encoding="utf-8")
        chk = compute_file_checksum(dummy_file)
        assert isinstance(chk, str)
        assert len(chk) == 64  # SHA-256 is 64 hex characters

    def test_load_nonexistent_cache_raises(self):
        with pytest.raises(FileNotFoundError):
            load_graph_cache("nonexistent_cache.eig.json")

    def test_corrupted_json_raises(self, tmp_path: Path):
        corrupt_file = tmp_path / "bad.json"
        corrupt_file.write_text("{ incomplete json ...", encoding="utf-8")
        with pytest.raises(ValueError, match="Invalid JSON"):
            load_graph_cache(corrupt_file)

    def test_unsupported_schema_version_raises(self, tmp_path: Path):
        bad_version_file = tmp_path / "bad_ver.json"
        bad_version_file.write_text(json.dumps({"schema_version": "99.0.0"}), encoding="utf-8")
        with pytest.raises(ValueError, match="Unsupported cache schema version"):
            load_graph_cache(bad_version_file)

    def test_tampered_payload_checksum_raises(self, tmp_path: Path):
        orig_graph = load_osm_graph_from_file(SAMPLE_HOSPITAL_DISTRICT_PATH)
        cache_file = tmp_path / "district.eig.json"
        save_graph_cache(orig_graph, cache_file)

        # Tamper with the content
        with open(cache_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Modify an edge cost maliciously
        data["edges"][0]["cost"] = 999999.0
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(data, f)

        # Loading with verification should detect tampering
        with pytest.raises(ValueError, match="Corrupted cache file: SHA-256 payload checksum mismatch"):
            load_graph_cache(cache_file, verify_checksum=True)
