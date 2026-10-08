"""
Data layer package.

Handles spatial calculations, geospatial distance heuristics, and ingestion
of external open geographic datasets (such as OpenStreetMap Overpass exports)
into the Emergency Intelligence AI road graph model.
"""

from pathlib import Path

from .geo import haversine_distance, haversine_heuristic
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
]
