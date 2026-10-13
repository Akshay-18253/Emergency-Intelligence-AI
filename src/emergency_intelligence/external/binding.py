"""
Emergency Infrastructure Network Binding & Domain Bridge.
=========================================================
Binds OpenStreetMap extracted emergency facilities to the topological road graph:
- Sub-millisecond orthogonal snapping onto road network vertices and polyline edges
- Automatic generation of municipal `EmergencyStation` and `EmergencyUnit` fleet assets
- Multi-criteria clinical routing for specialized emergency patient transports
  (e.g., nearest verified Trauma Level 1 or Cardiac Care catheterization unit)

Adheres strictly to zero external runtime dependencies (Python standard library only).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple

from emergency_intelligence.allocation.matcher import FleetManager
from emergency_intelligence.allocation.models import EmergencyStation, EmergencyUnit, UnitStatus
from emergency_intelligence.data.spatial import SnappedLocation, SpatialIndex
from emergency_intelligence.events.incidents import ApparatusType
from emergency_intelligence.external.overpass import (
    ClinicalCapability,
    EmergencyPOIType,
    ExtractedEmergencyPOI,
)
from emergency_intelligence.graph.astar import astar
from emergency_intelligence.graph.models import Edge, Graph


class SpatialBindingError(ValueError):
    """Raised when an emergency facility cannot be snapped to the road network."""


@dataclass
class POINetworkBinding:
    """Represents an emergency facility spatially bound to the road network.

    Attributes
    ----------
    poi : ExtractedEmergencyPOI
        The originating OpenStreetMap emergency facility.
    nearest_node_id : str
        The topologically connected road vertex identifier.
    snapped_coordinates : Tuple[float, float]
        The exact road connection coordinate (lon, lat).
    distance_meters : float
        Perpendicular offset distance from facility coordinate to road network.
    snapped_to_road : bool
        True if snapped onto an edge polyline; False if snapped to an existing vertex.
    nearest_edge : Optional[Edge]
        The road segment onto which the facility was projected.
    projection_factor : float
        Fractional position t in [0.0, 1.0] along the road segment.
    """

    poi: ExtractedEmergencyPOI
    nearest_node_id: str
    snapped_coordinates: Tuple[float, float]
    distance_meters: float
    snapped_to_road: bool
    nearest_edge: Optional[Edge] = None
    projection_factor: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the binding to a JSON dictionary."""
        return {
            "osm_id": self.poi.osm_id,
            "poi_name": self.poi.name,
            "poi_type": self.poi.poi_type.value,
            "nearest_node_id": self.nearest_node_id,
            "snapped_coordinates": [self.snapped_coordinates[0], self.snapped_coordinates[1]],
            "distance_meters": round(self.distance_meters, 2),
            "snapped_to_road": self.snapped_to_road,
            "projection_factor": round(self.projection_factor, 4),
        }


def bind_poi_to_network(
    poi: ExtractedEmergencyPOI,
    graph: Graph,
    spatial_index: Optional[SpatialIndex] = None,
    max_snap_distance_m: float = 2000.0,
) -> POINetworkBinding:
    """Binds an individual emergency POI to the nearest navigable road graph segment.

    Parameters
    ----------
    poi : ExtractedEmergencyPOI
        The emergency amenity to bind.
    graph : Graph
        The active road network graph.
    spatial_index : Optional[SpatialIndex]
        Pre-built 2D spatial hash grid index (built on-the-fly if omitted).
    max_snap_distance_m : float
        Maximum allowed distance threshold before rejecting the facility as isolated.

    Returns
    -------
    POINetworkBinding
        The spatial binding with road vertex and snapped coordinate references.

    Raises
    ------
    SpatialBindingError
        If no reachable road segment exists within max_snap_distance_m.
    """
    if spatial_index is None:
        spatial_index = SpatialIndex(graph)

    query_coords = (poi.longitude, poi.latitude)
    try:
        snapped = spatial_index.snap_to_road_network(
            query_coords,
            max_search_radius_m=max_snap_distance_m,
        )
    except ValueError as err:
        raise SpatialBindingError(
            f"Emergency facility '{poi.name}' (OSM:{poi.osm_id}) is beyond search radius: {err}"
        ) from err

    if snapped.distance_to_road_m > max_snap_distance_m:
        raise SpatialBindingError(
            f"Emergency facility '{poi.name}' (OSM:{poi.osm_id}) is "
            f"{snapped.distance_to_road_m:.1f}m from nearest road, exceeding "
            f"threshold of {max_snap_distance_m:.1f}m."
        )

    snapped_to_road = snapped.nearest_edge is not None and snapped.projection_factor > 0.0

    return POINetworkBinding(
        poi=poi,
        nearest_node_id=snapped.nearest_node_id,
        snapped_coordinates=snapped.snapped_coordinates,
        distance_meters=snapped.distance_to_road_m,
        snapped_to_road=snapped_to_road,
        nearest_edge=snapped.nearest_edge,
        projection_factor=snapped.projection_factor,
    )


def bind_pois_to_network(
    pois: List[ExtractedEmergencyPOI],
    graph: Graph,
    spatial_index: Optional[SpatialIndex] = None,
    max_snap_distance_m: float = 2000.0,
    skip_unbound: bool = True,
) -> Tuple[Dict[int, POINetworkBinding], List[ExtractedEmergencyPOI]]:
    """Batch-binds multiple emergency POIs to the road network using a shared spatial index.

    Parameters
    ----------
    pois : List[ExtractedEmergencyPOI]
        List of candidate emergency amenities.
    graph : Graph
        The active road network graph.
    spatial_index : Optional[SpatialIndex]
        Pre-built spatial index (constructed once if omitted).
    max_snap_distance_m : float
        Maximum snap threshold distance in meters.
    skip_unbound : bool
        If True, un-bindable facilities are collected in the returned unbound list.
        If False, raises SpatialBindingError on the first failure.

    Returns
    -------
    Tuple[Dict[int, POINetworkBinding], List[ExtractedEmergencyPOI]]
        Mapping of osm_id -> POINetworkBinding, and a list of unbound facilities.
    """
    if spatial_index is None:
        spatial_index = SpatialIndex(graph)

    bindings: Dict[int, POINetworkBinding] = {}
    unbound: List[ExtractedEmergencyPOI] = []

    for poi in pois:
        try:
            binding = bind_poi_to_network(
                poi=poi,
                graph=graph,
                spatial_index=spatial_index,
                max_snap_distance_m=max_snap_distance_m,
            )
            bindings[poi.osm_id] = binding
        except SpatialBindingError:
            if skip_unbound:
                unbound.append(poi)
            else:
                raise

    return bindings, unbound


def poi_to_emergency_station(
    poi: ExtractedEmergencyPOI,
    binding: POINetworkBinding,
) -> EmergencyStation:
    """Translates an extracted fire or ambulance POI into an EmergencyStation model."""
    station_id = f"OSM-{poi.osm_type[0].upper()}-{poi.osm_id}"
    return EmergencyStation(
        station_id=station_id,
        name=poi.name,
        node_id=binding.nearest_node_id,
        station_type=poi.poi_type.value,
        metadata={
            "osm_id": poi.osm_id,
            "osm_type": poi.osm_type,
            "capabilities": [c.value for c in sorted(list(poi.capabilities), key=lambda x: x.value)],
            "trauma_level": poi.trauma_level,
            "apparatus_bays": poi.apparatus_bays,
            "address": poi.address,
            "phone": poi.phone,
            "operator": poi.operator,
            "distance_to_road_m": binding.distance_meters,
        },
    )


def create_fleet_from_pois(
    pois: List[ExtractedEmergencyPOI],
    bindings: Dict[int, POINetworkBinding],
    apparatus_blueprint: Optional[Dict[EmergencyPOIType, List[Tuple[ApparatusType, int, float]]]] = None,
) -> FleetManager:
    """Constructs and populates a FleetManager directly from extracted and bound OSM POIs.

    Parameters
    ----------
    pois : List[ExtractedEmergencyPOI]
        List of facilities to instantiate as response stations.
    bindings : Dict[int, POINetworkBinding]
        Spatial network bindings for the facilities.
    apparatus_blueprint : Optional[Dict[EmergencyPOIType, List[Tuple[ApparatusType, int, float]]]]
        Mapping of POI type to apparatus assignments: [(type, count, speed_factor)].
        Sensible default municipal profiles are used if omitted.

    Returns
    -------
    FleetManager
        Configured and populated fleet registry ready for dispatch allocation.
    """
    if apparatus_blueprint is None:
        blueprint: Dict[EmergencyPOIType, List[Tuple[ApparatusType, int, float]]] = {
            EmergencyPOIType.FIRE_STATION: [
                (ApparatusType.FIRE_ENGINE, 2, 0.90),
                (ApparatusType.LADDER_TRUCK, 1, 0.80),
                (ApparatusType.AMBULANCE_BLS, 1, 1.00),
            ],
            EmergencyPOIType.AMBULANCE_STATION: [
                (ApparatusType.AMBULANCE_ALS, 2, 1.05),
                (ApparatusType.AMBULANCE_BLS, 2, 1.00),
            ],
            EmergencyPOIType.HOSPITAL: [
                (ApparatusType.AMBULANCE_ALS, 1, 1.05),
            ],
        }
    else:
        blueprint = apparatus_blueprint

    fleet = FleetManager()
    unit_seq = 1

    for poi in pois:
        if poi.osm_id not in bindings:
            continue
        binding = bindings[poi.osm_id]

        # Only register facility types that house response units
        if poi.poi_type not in (
            EmergencyPOIType.FIRE_STATION,
            EmergencyPOIType.AMBULANCE_STATION,
            EmergencyPOIType.HOSPITAL,
        ):
            continue

        station = poi_to_emergency_station(poi, binding)
        fleet.register_station(station)

        # Allocate apparatus units based on blueprint
        unit_templates = blueprint.get(poi.poi_type, [])
        for app_type, count, speed_factor in unit_templates:
            # Scale count if explicit apparatus_bays tag exists
            effective_count = count
            if poi.apparatus_bays is not None and poi.apparatus_bays > 0:
                effective_count = max(1, min(poi.apparatus_bays, count))

            for idx in range(1, effective_count + 1):
                unit_code = app_type.value.upper()[:3]
                unit_id = f"{unit_code}-{poi.osm_id}-{idx}-{unit_seq}"
                unit_seq += 1

                caps = {c.value for c in poi.capabilities}
                if app_type == ApparatusType.AMBULANCE_ALS:
                    caps.add("als")
                    caps.add("paramedic")
                elif app_type == ApparatusType.AMBULANCE_BLS:
                    caps.add("bls")

                unit = EmergencyUnit(
                    unit_id=unit_id,
                    apparatus_type=app_type,
                    current_node_id=binding.nearest_node_id,
                    station_id=station.station_id,
                    status=UnitStatus.AVAILABLE,
                    speed_factor=speed_factor,
                    capabilities=caps,
                    metadata={"home_poi_name": poi.name},
                )
                fleet.register_unit(unit)

    return fleet


def find_nearest_clinical_facility(
    incident_node_id: str,
    graph: Graph,
    candidate_pois: List[ExtractedEmergencyPOI],
    bindings: Dict[int, POINetworkBinding],
    required_capabilities: Optional[Set[ClinicalCapability]] = None,
) -> Optional[Tuple[ExtractedEmergencyPOI, POINetworkBinding, List[str], float]]:
    """Calculates the optimal clinical transport route to the nearest suitable hospital.

    Matches medical urgency requirements (e.g. Trauma Level 1, Burn Unit, Cardiac Unit)
    and computes the shortest A* route from the emergency scene to the facility.

    Parameters
    ----------
    incident_node_id : str
        The road network vertex of the emergency scene.
    graph : Graph
        The active road network graph.
    candidate_pois : List[ExtractedEmergencyPOI]
        List of hospital / medical facility POIs.
    bindings : Dict[int, POINetworkBinding]
        Spatial bindings for the facilities.
    required_capabilities : Optional[Set[ClinicalCapability]]
        Mandatory clinical certifications (e.g. {ClinicalCapability.CARDIAC_CARE}).

    Returns
    -------
    Optional[Tuple[ExtractedEmergencyPOI, POINetworkBinding, List[str], float]]
        (best_facility_poi, binding, shortest_path_node_ids, travel_time_or_distance),
        or None if no reachable facility satisfies the clinical criteria.
    """
    if incident_node_id not in graph.node_ids():
        return None

    best_poi: Optional[ExtractedEmergencyPOI] = None
    best_binding: Optional[POINetworkBinding] = None
    best_path: Optional[List[str]] = None
    best_cost: float = float("inf")

    req_caps = required_capabilities or set()

    for poi in candidate_pois:
        if poi.osm_id not in bindings:
            continue
        binding = bindings[poi.osm_id]

        target_node = binding.nearest_node_id
        if target_node not in graph.node_ids():
            continue

        # Capability filtering
        if not poi.capabilities.issuperset(req_caps):
            continue

        # If Trauma Level is required, check tier
        if any(c.value.startswith("trauma_level_") for c in req_caps):
            if poi.trauma_level is None:
                continue

        # Compute A* route from incident to hospital
        route = astar(graph, incident_node_id, target_node)
        if route.reachable and route.total_cost < best_cost:
            best_cost = route.total_cost
            best_path = route.path
            best_poi = poi
            best_binding = binding

    if best_poi is None or best_binding is None or best_path is None:
        return None

    return (best_poi, best_binding, best_path, best_cost)
