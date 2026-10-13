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
from emergency_intelligence.external.elevation import (
    APPARATUS_GRADE_PROFILES,
    ApparatusGradeLimits,
    DEMResolution,
    ElevationEnrichmentSummary,
    ElevationGraphView,
    ElevationProvider,
    SlopeMetrics,
    SRTMTile,
    build_synthetic_dem_tile,
    calculate_slope_metrics,
    enrich_graph_with_elevation,
    format_srtm_tile_name,
    get_grade_speed_multiplier,
    parse_srtm_tile_name,
)

from emergency_intelligence.external.hydrology import (
    DEFAULT_GAUGE_THRESHOLDS,
    EnvironmentalMutationSummary,
    FloodStage,
    USGSGaugeReading,
    USGSGaugeThresholds,
    WeatherAlertLevel,
    WeatherConditions,
    apply_environmental_hazards_to_graph,
    build_usgs_water_query_url,
    classify_wmo_weather_code,
    create_flood_inundation_polygon,
    create_weather_hazard_polygon,
    parse_open_meteo_response,
    parse_usgs_water_response,
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
    "APPARATUS_GRADE_PROFILES",
    "ApparatusGradeLimits",
    "DEMResolution",
    "ElevationEnrichmentSummary",
    "ElevationGraphView",
    "ElevationProvider",
    "SlopeMetrics",
    "SRTMTile",
    "build_synthetic_dem_tile",
    "calculate_slope_metrics",
    "enrich_graph_with_elevation",
    "format_srtm_tile_name",
    "get_grade_speed_multiplier",
    "parse_srtm_tile_name",
    "DEFAULT_GAUGE_THRESHOLDS",
    "EnvironmentalMutationSummary",
    "FloodStage",
    "USGSGaugeReading",
    "USGSGaugeThresholds",
    "WeatherAlertLevel",
    "WeatherConditions",
    "apply_environmental_hazards_to_graph",
    "build_usgs_water_query_url",
    "classify_wmo_weather_code",
    "create_flood_inundation_polygon",
    "create_weather_hazard_polygon",
    "parse_open_meteo_response",
    "parse_usgs_water_response",
]

