"""
Events sub-package.

Exposes domain models, taxonomies, spatial geometry algorithms, non-destructive
graph mutation overlays, OASIS CAP alert ingestion, and in-flight reactive
rerouting for dynamic emergency conditions.
"""

from .alerts import (
    CAPAlert,
    CAPCertainty,
    CAPMsgType,
    CAPSeverity,
    CAPUrgency,
    parse_cap_xml,
    parse_geojson_alerts,
)
from .hazards import (
    DEFAULT_SEVERITY_SPEED_MULTIPLIERS,
    HazardPolygon,
    HazardSeverity,
    HazardType,
    compute_effective_edge_cost,
    find_edges_intersecting_hazard,
    find_hazards_affecting_edge,
    point_in_polygon,
    segment_intersects_polygon,
    segments_intersect,
)
from .incidents import (
    ApparatusType,
    EmergencyType,
    Incident,
    UrgencyLevel,
)
from .inflight import (
    DispatchedVehicleTracker,
    check_route_obstruction,
    replan_inflight_route,
)
from .mutations import (
    DynamicGraphView,
    EdgeMutation,
    MutationType,
)

__all__ = [
    # Incidents
    "EmergencyType",
    "UrgencyLevel",
    "ApparatusType",
    "Incident",
    # Hazards
    "HazardType",
    "HazardSeverity",
    "DEFAULT_SEVERITY_SPEED_MULTIPLIERS",
    "HazardPolygon",
    "point_in_polygon",
    "segments_intersect",
    "segment_intersects_polygon",
    "find_edges_intersecting_hazard",
    "find_hazards_affecting_edge",
    "compute_effective_edge_cost",
    # Mutations & Dynamic View
    "MutationType",
    "EdgeMutation",
    "DynamicGraphView",
    # OASIS CAP & GeoJSON Alert Ingestion
    "CAPMsgType",
    "CAPUrgency",
    "CAPSeverity",
    "CAPCertainty",
    "CAPAlert",
    "parse_cap_xml",
    "parse_geojson_alerts",
    # In-Flight Rerouting
    "DispatchedVehicleTracker",
    "check_route_obstruction",
    "replan_inflight_route",
]
