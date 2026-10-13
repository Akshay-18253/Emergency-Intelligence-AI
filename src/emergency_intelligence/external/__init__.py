"""
External Data and Geospatial Map Integration Subsystem.
======================================================
Provides standard-library-compliant integration with open geospatial data feeds:
- OpenStreetMap Overpass API POI query building and clinical facility parsing
- Spatial network binding of emergency infrastructure to road graph topology
- USGS hydrological streamflow and flood hazard feeds
- Topographic digital elevation models (DEM) and slope incline weighting
- Interactive zero-dependency Leaflet GIS visualizers
"""

from __future__ import annotations

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
from emergency_intelligence.external.binding import (
    POINetworkBinding,
    SpatialBindingError,
    bind_poi_to_network,
    bind_pois_to_network,
    create_fleet_from_pois,
    find_nearest_clinical_facility,
    poi_to_emergency_station,
)

__all__ = [
    "ClinicalCapability",
    "EmergencyPOIType",
    "ExtractedEmergencyPOI",
    "OverpassNetworkError",
    "OverpassParseError",
    "build_emergency_poi_query",
    "fetch_or_load_overpass_pois",
    "parse_overpass_response",
    "POINetworkBinding",
    "SpatialBindingError",
    "bind_poi_to_network",
    "bind_pois_to_network",
    "create_fleet_from_pois",
    "find_nearest_clinical_facility",
    "poi_to_emergency_station",
]
