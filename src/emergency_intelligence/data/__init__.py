"""
Data layer package.

Handles spatial calculations, geospatial distance heuristics, ingestion
of external open geographic datasets (such as OpenStreetMap Overpass exports),
and export to standard RFC 7946 GeoJSON format.
"""

from pathlib import Path

from .geo import haversine_distance, haversine_heuristic
from .geojson import (
    compute_bounding_box,
    graph_to_geojson,
    load_graph_from_geojson,
    route_to_geojson,
    save_geojson,
    save_graph_geojson,
    save_route_geojson,
    validate_wgs84_coordinates,
)
from .osm import (
    DEFAULT_HIGHWAY_TYPES,
    load_osm_graph_from_data,
    load_osm_graph_from_file,
)

# Canonical path to the bundled OpenStreetMap hospital district fixture
SAMPLE_HOSPITAL_DISTRICT_PATH: Path = (
    Path(__file__).parent / "sample_hospital_district.json"
)

__all__ = [
    "haversine_distance",
    "haversine_heuristic",
    "DEFAULT_HIGHWAY_TYPES",
    "load_osm_graph_from_data",
    "load_osm_graph_from_file",
    "SAMPLE_HOSPITAL_DISTRICT_PATH",
    "compute_bounding_box",
    "graph_to_geojson",
    "load_graph_from_geojson",
    "route_to_geojson",
    "save_geojson",
    "save_graph_geojson",
    "save_route_geojson",
    "validate_wgs84_coordinates",
]
