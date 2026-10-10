"""
Events sub-package.

Exposes domain models, taxonomies, spatial geometry algorithms, and non-destructive
graph mutation overlays for dynamic emergency conditions, incident dispatches,
and environmental disaster zones.
"""

from .incidents import (
    ApparatusType,
    EmergencyType,
    Incident,
    UrgencyLevel,
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
]
