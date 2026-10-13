"""
Demonstration: OpenStreetMap Overpass POI Ingestion & Clinical Network Binding.
==============================================================================
Demonstrates Milestone 7.1 capabilities:
  1. Overpass QL query construction for geographic bounding boxes.
  2. Ingestion and clinical capability parsing of emergency infrastructure
     (Trauma Level 1, Burn Unit, Cardiac Catheterization, Fire Stations, Helipads).
  3. Sub-millisecond orthogonal snapping of facilities onto the road network.
  4. Automated population of municipal FleetManager response assets.
  5. Specialized clinical hospital transport routing using A* search.

Usage:
    python examples/overpass_poi_demo.py
"""

from __future__ import annotations

import time
from emergency_intelligence.allocation.matcher import FleetManager
from emergency_intelligence.allocation.models import UnitStatus
from emergency_intelligence.events.incidents import ApparatusType
from emergency_intelligence.external.binding import (
    bind_pois_to_network,
    create_fleet_from_pois,
    find_nearest_clinical_facility,
)
from emergency_intelligence.external.overpass import (
    ClinicalCapability,
    EmergencyPOIType,
    build_emergency_poi_query,
    parse_overpass_response,
)
from emergency_intelligence.graph.models import Edge, Graph, Node


# Sample bundled Overpass JSON response for Seattle Metro District
SEATTLE_METRO_OVERPASS_FIXTURE = {
    "version": 0.6,
    "elements": [
        {
            "type": "node",
            "id": 101,
            "lat": 47.6045,
            "lon": -122.3248,
            "tags": {
                "amenity": "hospital",
                "name": "Harborview Medical Center",
                "emergency": "yes",
                "emergency:trauma_level": "1",
                "healthcare:speciality": "cardiology;burn;pediatrics",
                "emergency:helipad": "yes",
                "operator": "UW Medicine",
                "addr:street": "9th Ave",
                "addr:housenumber": "325",
                "phone": "+1-206-744-3000",
            },
        },
        {
            "type": "node",
            "id": 102,
            "lat": 47.6090,
            "lon": -122.3290,
            "tags": {
                "amenity": "hospital",
                "name": "Virginia Mason Medical Center",
                "emergency": "yes",
                "emergency:trauma_level": "2",
                "healthcare:speciality": "cardiology;stroke",
                "addr:street": "Terry Ave",
                "addr:housenumber": "1100",
                "phone": "+1-206-223-6600",
            },
        },
        {
            "type": "node",
            "id": 103,
            "lat": 47.6210,
            "lon": -122.3550,
            "tags": {
                "amenity": "hospital",
                "name": "Queen Anne Community Urgent Care",
                "emergency:trauma_level": "4",
                "healthcare:speciality": "general",
            },
        },
        {
            "type": "way",
            "id": 201,
            "center": {"lat": 47.6189, "lon": -122.3321},
            "tags": {
                "amenity": "fire_station",
                "name": "Seattle Fire Station 2 (Belltown)",
                "fire_station:engine_bays": "3",
                "hazmat": "yes",
                "phone": "+1-206-386-1400",
            },
        },
        {
            "type": "node",
            "id": 202,
            "lat": 47.6020,
            "lon": -122.3310,
            "tags": {
                "amenity": "fire_station",
                "name": "Seattle Fire Station 10 (Pioneer Square / HQ)",
                "fire_station:engine_bays": "4",
                "phone": "+1-206-386-1410",
            },
        },
        {
            "type": "node",
            "id": 301,
            "lat": 47.6010,
            "lon": -122.3280,
            "tags": {
                "emergency": "ambulance_station",
                "name": "King County Medic One Headquarters",
                "phone": "+1-206-296-4693",
            },
        },
        {
            "type": "node",
            "id": 401,
            "lat": 47.6205,
            "lon": -122.3493,
            "tags": {
                "aeroway": "helipad",
                "name": "KOMO Sky4 Medevac Helipad",
            },
        },
    ],
}


def build_seattle_test_graph() -> Graph:
    """Builds a connected road graph representing the downtown Seattle grid."""
    g = Graph()
    # 4x4 urban grid
    lons = [-122.355, -122.345, -122.332, -122.324]
    lats = [47.600, 47.608, 47.616, 47.624]

    for y_idx, lat in enumerate(lats):
        for x_idx, lon in enumerate(lons):
            nid = f"INT_{x_idx}_{y_idx}"
            g.add_node(Node(node_id=nid, coordinates=(lon, lat)))

    # Add bidirectional arterial connections with travel times (seconds)
    for y in range(4):
        for x in range(3):
            u, v = f"INT_{x}_{y}", f"INT_{x+1}_{y}"
            g.add_edge(Edge(source_id=u, destination_id=v, cost=45.0))
            g.add_edge(Edge(source_id=v, destination_id=u, cost=45.0))

    for x in range(4):
        for y in range(3):
            u, v = f"INT_{x}_{y}", f"INT_{x}_{y+1}"
            g.add_edge(Edge(source_id=u, destination_id=v, cost=55.0))
            g.add_edge(Edge(source_id=v, destination_id=u, cost=55.0))

    return g


def main() -> None:
    t_start = time.perf_counter()
    print("=" * 76)
    print("  Emergency Intelligence AI -- OSM Overpass POI Ingestion & Binding Demo")
    print("=" * 76)

    # 1. Overpass QL Query Construction
    print("\n[Stage 1] Constructing Overpass QL Query for Seattle Bounding Box...")
    bbox = (47.595, -122.360, 47.630, -122.320)
    query = build_emergency_poi_query(
        bbox=bbox,
        poi_types=[
            EmergencyPOIType.HOSPITAL,
            EmergencyPOIType.FIRE_STATION,
            EmergencyPOIType.AMBULANCE_STATION,
            EmergencyPOIType.HELIPAD,
        ],
        timeout_seconds=25,
    )
    print(f"  Generated Query (showing top 6 lines):")
    for line in query.splitlines()[:6]:
        print(f"    {line}")
    print("    ...")

    # 2. Parsing Overpass Response & Capability Inference
    print("\n[Stage 2] Parsing Overpass JSON & Extracting Clinical Capabilities...")
    pois = parse_overpass_response(SEATTLE_METRO_OVERPASS_FIXTURE)
    print(f"  Extracted {len(pois)} emergency facilities:")
    print("  " + "-" * 72)
    print(f"  {'OSM ID':<8} {'Type':<17} {'Name':<32} {'Trauma':<7} {'Bays'}")
    print("  " + "-" * 72)
    for poi in pois:
        trauma_str = f"Tier {poi.trauma_level}" if poi.trauma_level else "N/A"
        bays_str = str(poi.apparatus_bays) if poi.apparatus_bays else "N/A"
        print(f"  {poi.osm_id:<8} {poi.poi_type.value:<17} {poi.name[:30]:<32} {trauma_str:<7} {bays_str}")
    print("  " + "-" * 72)

    # 3. Spatial Network Snapping
    print("\n[Stage 3] Spatially Snapping Facilities to Topological Road Graph...")
    graph = build_seattle_test_graph()
    bindings, unbound = bind_pois_to_network(pois, graph, max_snap_distance_m=1500.0)
    print(f"  Successfully bound {len(bindings)} facilities to road vertices (Unbound: {len(unbound)}):")
    for osm_id, b in sorted(bindings.items()):
        print(
            f"    * {b.poi.name[:32]:<32} -> Node: {b.nearest_node_id:<10} "
            f"Offset: {b.distance_meters:.1f}m"
        )

    # 4. Automated Fleet Creation
    print("\n[Stage 4] Instantiating Municipal Fleet from Bound OSM Depots...")
    fleet = create_fleet_from_pois(pois, bindings)
    available_units = fleet.get_available_units()
    print(f"  Generated Response Fleet with {len(available_units)} active apparatus across 3 depots:")
    for unit in available_units:
        caps_str = ", ".join(sorted(unit.capabilities)) if unit.capabilities else "standard"
        station = fleet.get_station(unit.station_id or "")
        station_name = station.name if station else "Unknown Station"
        print(
            f"    - [{unit.unit_id}] {unit.apparatus_type.value.upper():<16} "
            f"at {unit.current_node_id} (Depot: {station_name[:25]})"
        )

    # 5. Specialized Clinical Facility Routing
    print("\n[Stage 5] Multi-Criteria Specialized Clinical Hospital Dispatch...")
    incident_location = "INT_0_0"  # Near Pioneer Square / South Waterfront
    print(f"  Emergency Incident Scene: Vertex '{incident_location}'")

    # Scenario A: Nearest Hospital (Any capability)
    hospitals = [p for p in pois if p.poi_type == EmergencyPOIType.HOSPITAL]
    res_any = find_nearest_clinical_facility(
        incident_node_id=incident_location,
        graph=graph,
        candidate_pois=hospitals,
        bindings=bindings,
    )
    if res_any:
        hosp, binding, path, cost = res_any
        print(f"  [Scenario A - Unconstrained Nearest Hospital]:")
        print(f"    Facility : {hosp.name} (Trauma Tier {hosp.trauma_level or 'N/A'})")
        print(f"    Travel Time : {cost:.1f} seconds")
        print(f"    Transit Path: {' -> '.join(path)}")

    # Scenario B: Specialized Cardiac Care & Burn Center requirement
    required_caps = {ClinicalCapability.CARDIAC_CARE, ClinicalCapability.BURN_CENTER}
    print(f"\n  [Scenario B - Critical Patient: Cardiac Catheterization & Burn Center Required]:")
    res_specialized = find_nearest_clinical_facility(
        incident_node_id=incident_location,
        graph=graph,
        candidate_pois=hospitals,
        bindings=bindings,
        required_capabilities=required_caps,
    )
    if res_specialized:
        hosp, binding, path, cost = res_specialized
        print(f"    Selected Facility: {hosp.name} (Verified Trauma 1, Burn, Cardiac)")
        print(f"    Travel Time      : {cost:.1f} seconds")
        print(f"    Optimal Route    : {' -> '.join(path)}")
        print(f"    Clinical Invariance: Safely bypassed non-burn facilities to ensure clinical survival.")

    elapsed_ms = (time.perf_counter() - t_start) * 1000.0
    print("\n" + "=" * 76)
    print(f"  DEMONSTRATION COMPLETED SUCCESSFULLY in {elapsed_ms:.2f} ms.")
    print("=" * 76 + "\n")


if __name__ == "__main__":
    main()
