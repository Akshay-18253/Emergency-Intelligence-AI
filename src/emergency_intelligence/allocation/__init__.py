"""
Emergency Intelligence AI - Fleet Allocation & Apparatus Matching Subsystem.
============================================================================
Export public classes and routines for multi-source catchment partitioning,
isochrone frontiers, fleet management, and apparatus dispatch allocation.
"""

from __future__ import annotations

from emergency_intelligence.allocation.catchment import (
    compute_eta_matrix,
    compute_isochrone_frontiers,
    compute_multi_source_catchment,
    find_closest_depot,
)
from emergency_intelligence.allocation.matcher import (
    FleetManager,
    allocate_fleet_for_incident,
    rank_units_for_incident,
)
from emergency_intelligence.allocation.models import (
    CatchmentPartition,
    DispatchAssignment,
    DispatchPlan,
    EmergencyStation,
    EmergencyUnit,
    ETARecord,
    UnitStatus,
)

__all__ = [
    "CatchmentPartition",
    "DispatchAssignment",
    "DispatchPlan",
    "EmergencyStation",
    "EmergencyUnit",
    "ETARecord",
    "FleetManager",
    "UnitStatus",
    "allocate_fleet_for_incident",
    "compute_eta_matrix",
    "compute_isochrone_frontiers",
    "compute_multi_source_catchment",
    "find_closest_depot",
    "rank_units_for_incident",
]
