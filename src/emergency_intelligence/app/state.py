"""
Application State Container & Gateway Bridge (Milestone 8.1).
============================================================
Holds thread-safe in-memory instances of:
- Metropolitan road graph (from synthetic benchmark or real-world OSM)
- DynamicGraphView for non-destructive, reversible hazard injections
- SpatialIndex (2D Hash Grid) for O(1) coordinate snapping
- ExtractedEmergencyPOIs and POINetworkBindings
- FleetManager with stationed apparatus units
- EmergencyIntelligenceOrchestrator (5-stage natural language pipeline)
- Server-Sent Events (SSE) broadcast pub/sub queues

Strictly zero external runtime dependencies: Python standard library only.
"""

from __future__ import annotations

import json
import math
import queue
import threading
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from emergency_intelligence.allocation.matcher import FleetManager
from emergency_intelligence.data.geo import haversine_distance, haversine_heuristic
from emergency_intelligence.data.geojson import route_to_geojson
from emergency_intelligence.data.osm import WeightingProfile
from emergency_intelligence.data.spatial import SpatialIndex
from emergency_intelligence.events.hazards import (
    HazardPolygon,
    HazardSeverity,
    HazardType,
    find_edges_intersecting_hazard,
)
from emergency_intelligence.events.incidents import ApparatusType, UrgencyLevel
from emergency_intelligence.events.inflight import DispatchedVehicleTracker
from emergency_intelligence.events.mutations import DynamicGraphView
from emergency_intelligence.external.benchmark import build_metropolitan_benchmark_district
from emergency_intelligence.external.binding import (
    bind_pois_to_network,
    create_fleet_from_pois,
    find_nearest_clinical_facility,
)
from emergency_intelligence.external.elevation import (
    ElevationGraphView,
    ElevationProvider,
    enrich_graph_with_elevation,
)
from emergency_intelligence.external.hydrology import (
    USGSGaugeReading,
    WeatherConditions,
)
from emergency_intelligence.external.overpass import (
    ClinicalCapability,
    ExtractedEmergencyPOI,
)
from emergency_intelligence.graph.astar import astar
from emergency_intelligence.graph.models import Graph, Node
from emergency_intelligence.graph.topology import calculate_turn_angle, classify_turn_maneuver
from emergency_intelligence.intelligence.interpreter import FixtureEmergencyInterpreter
from emergency_intelligence.intelligence.orchestrator import EmergencyIntelligenceOrchestrator
from emergency_intelligence.intelligence.policy import EmergencyPolicyEngine


class AppState:
    """Thread-safe state container and domain gateway for the Emergency Intelligence App."""

    def __init__(
        self,
        base_graph: Optional[Graph] = None,
        pois: Optional[List[ExtractedEmergencyPOI]] = None,
        elevation_provider: Optional[ElevationProvider] = None,
        river_gauge: Optional[USGSGaugeReading] = None,
        weather: Optional[WeatherConditions] = None,
    ) -> None:
        self._lock = threading.RLock()
        self.start_time = time.time()

        if base_graph is None or pois is None:
            default_graph, default_pois, default_elev, default_gauge, default_weather = (
                build_metropolitan_benchmark_district()
            )
            self.base_graph = default_graph
            self.pois = default_pois
            self.elevation_provider = default_elev
            self.river_gauge = default_gauge
            self.weather = default_weather
        else:
            self.base_graph = base_graph
            self.pois = pois
            self.elevation_provider = elevation_provider
            self.river_gauge = river_gauge
            self.weather = weather

        # Enrich base graph with 3D elevation if provider is available
        if self.elevation_provider:
            enrich_graph_with_elevation(self.base_graph, self.elevation_provider)

        # Dynamic graph overlay for reversible disaster mutations
        self.dynamic_graph = DynamicGraphView(self.base_graph)

        # 2D Spatial Hash Grid index for sub-millisecond coordinate snapping
        self.spatial_index = SpatialIndex(self.base_graph, cell_size_deg=0.005)

        # Bind emergency POIs to road network
        self.poi_bindings, self.unbound_pois = bind_pois_to_network(
            self.pois, self.base_graph, spatial_index=self.spatial_index, max_snap_distance_m=2000.0
        )

        # Build fleet manager
        self.fleet_manager = create_fleet_from_pois(self.pois, self.poi_bindings)

        # AI Orchestration & Statutory Policy Engine
        self.policy_engine = EmergencyPolicyEngine()
        self.interpreter = FixtureEmergencyInterpreter()
        self.orchestrator = EmergencyIntelligenceOrchestrator(
            interpreter=self.interpreter,
            policy_engine=self.policy_engine,
            fleet_manager=self.fleet_manager,
            graph=self.dynamic_graph,
        )

        # Active dynamic hazard tracking
        self.active_hazards: Dict[str, HazardPolygon] = {}
        self._hazard_counter = 0

        # Server-Sent Events subscriber queues
        self._sse_subscribers: Set[queue.Queue[str]] = set()

        # Simulation playback and scenario state
        self.simulation_time = 0.0
        self.simulation_active = False
        self.simulation_scenario_name = "metropolitan_disaster"
        self.simulated_incidents: List[Dict[str, Any]] = []
        self.simulated_vehicles: Dict[str, Dict[str, Any]] = {}
        self.active_cad_incidents: Dict[str, Dict[str, Any]] = {}
        self._init_simulation_state()

    # -------------------------------------------------------------------------
    # Server-Sent Events (SSE) Pub/Sub
    # -------------------------------------------------------------------------

    def register_sse_client(self) -> queue.Queue[str]:
        """Register a new SSE client connection and return its dedicated queue."""
        with self._lock:
            client_queue: queue.Queue[str] = queue.Queue(maxsize=128)
            self._sse_subscribers.add(client_queue)
            return client_queue

    def unregister_sse_client(self, client_queue: queue.Queue[str]) -> None:
        """Remove a disconnected SSE client queue."""
        with self._lock:
            self._sse_subscribers.discard(client_queue)

    def broadcast_sse(self, event_name: str, data: Any) -> None:
        """Broadcast a formatted SSE event frame to all registered client queues."""
        data_json = json.dumps(data, ensure_ascii=False)
        frame = f"event: {event_name}\ndata: {data_json}\n\n"

        with self._lock:
            dead_queues = []
            for q in self._sse_subscribers:
                try:
                    q.put_nowait(frame)
                except queue.Full:
                    dead_queues.append(q)
            for dq in dead_queues:
                self._sse_subscribers.discard(dq)

    # -------------------------------------------------------------------------
    # System Status & Health
    # -------------------------------------------------------------------------

    def get_health_status(self) -> Dict[str, Any]:
        """Return real-time operational health telemetry."""
        with self._lock:
            uptime = time.time() - self.start_time
            return {
                "status": "healthy",
                "service": "emergency-intelligence-ai",
                "version": "0.2.0",
                "uptime_seconds": round(uptime, 2),
                "graph_nodes": self.base_graph.node_count(),
                "graph_edges": self.base_graph.edge_count(),
                "severed_edges": self.dynamic_graph.active_mutation_count(),
                "emergency_facilities": len(self.pois),
                "active_hazards": len(self.active_hazards),
                "sse_subscribers": len(self._sse_subscribers),
            }

    # -------------------------------------------------------------------------
    # Spatial Network & Facilities
    # -------------------------------------------------------------------------

    def get_network_geojson(self) -> Dict[str, Any]:
        """Serialize the road network topology to RFC 7946 GeoJSON FeatureCollection."""
        with self._lock:
            features = []
            seen_edges: Set[Tuple[str, str]] = set()

            for u in self.base_graph.node_ids():
                u_node = self.base_graph.get_node(u)
                if not u_node or not u_node.coordinates:
                    continue
                u_lon, u_lat = u_node.coordinates

                for edge in self.base_graph.get_neighbors(u):
                    v = edge.destination_id
                    v_node = self.base_graph.get_node(v)
                    if not v_node or not v_node.coordinates:
                        continue
                    v_lon, v_lat = v_node.coordinates

                    edge_key = (min(u, v), max(u, v))
                    if edge_key in seen_edges:
                        continue
                    seen_edges.add(edge_key)

                    is_severed = self.dynamic_graph.is_edge_blocked(u, v)
                    dist_m = edge.attributes.get("distance_m", edge.attributes.get("length_m", 0.0))
                    speed_kmh = edge.attributes.get("speed_kmh", 45.0)

                    features.append({
                        "type": "Feature",
                        "geometry": {
                            "type": "LineString",
                            "coordinates": [[u_lon, u_lat], [v_lon, v_lat]],
                        },
                        "properties": {
                            "source": u,
                            "target": v,
                            "length_m": round(dist_m, 1),
                            "maxspeed_kmh": round(speed_kmh, 1),
                            "highway": edge.attributes.get("highway", "residential"),
                            "is_bridge": bool(edge.attributes.get("is_river_bridge", False)),
                            "is_severed": is_severed,
                        },
                    })

            lons = [
                self.base_graph.get_node(nid).coordinates[0]
                for nid in self.base_graph.node_ids()
                if self.base_graph.get_node(nid) and self.base_graph.get_node(nid).coordinates
            ]
            lats = [
                self.base_graph.get_node(nid).coordinates[1]
                for nid in self.base_graph.node_ids()
                if self.base_graph.get_node(nid) and self.base_graph.get_node(nid).coordinates
            ]

            bbox = [min(lons), min(lats), max(lons), max(lats)] if lons and lats else [0, 0, 0, 0]

            return {
                "type": "FeatureCollection",
                "bbox": bbox,
                "features": features,
            }

    def get_facilities_data(self) -> List[Dict[str, Any]]:
        """Return structured listing of hospitals, clinics, and fire stations."""
        with self._lock:
            result = []
            for poi in self.pois:
                capabilities = [c.value for c in poi.capabilities]
                result.append({
                    "id": f"OSM-{poi.osm_type[0].upper()}-{poi.osm_id}",
                    "osm_id": poi.osm_id,
                    "name": poi.name,
                    "poi_type": poi.poi_type.value,
                    "coordinates": [poi.longitude, poi.latitude],
                    "trauma_level": poi.trauma_level,
                    "capabilities": capabilities,
                    "apparatus_bays": poi.apparatus_bays,
                    "has_helipad": ClinicalCapability.HELIPAD in poi.capabilities,
                })
            return result

    # -------------------------------------------------------------------------
    # Routing Calculations
    # -------------------------------------------------------------------------

    def _resolve_node(self, target: Any) -> Optional[str]:
        """Resolve either a node ID or coordinate pair to a valid graph node."""
        if isinstance(target, str):
            if self.base_graph.has_node(target):
                return target
            return None

        if isinstance(target, (list, tuple)) and len(target) == 2:
            c0, c1 = float(target[0]), float(target[1])
            if abs(c0) <= 90.0:  # [lat, lon]
                lat, lon = c0, c1
            else:  # [lon, lat]
                lon, lat = c0, c1
            try:
                node_id, _ = self.spatial_index.nearest_node((lon, lat))
                return node_id
            except Exception:
                return None

        return None

    def compute_route(
        self,
        origin: Any,
        destination: Any,
        apparatus_type: ApparatusType = ApparatusType.AMBULANCE_ALS,
        profile: str = WeightingProfile.EMERGENCY_TIME,
        elevation_aware: bool = False,
    ) -> Dict[str, Any]:
        """Compute optimal emergency route considering active hazards and topography."""
        with self._lock:
            u_node = self._resolve_node(origin)
            v_node = self._resolve_node(destination)

            if not u_node or not v_node:
                return {
                    "path_found": False,
                    "error": f"Could not resolve nodes for origin='{origin}', dest='{destination}'",
                    "nodes": [],
                    "duration_seconds": 0.0,
                    "distance_2d_meters": 0.0,
                }

            t0 = time.perf_counter()
            active_graph = self.dynamic_graph
            if elevation_aware and self.elevation_provider is not None:
                active_graph = ElevationGraphView(
                    self.dynamic_graph,
                    apparatus_type=apparatus_type,
                    use_3d_distance=True,
                )

            route_result = astar(
                graph=active_graph,
                source=u_node,
                destination=v_node,
                heuristic=haversine_heuristic,
            )
            elapsed_ms = (time.perf_counter() - t0) * 1000.0

            if not route_result.reachable:
                return {
                    "path_found": False,
                    "origin_node": u_node,
                    "destination_node": v_node,
                    "duration_seconds": 0.0,
                    "distance_2d_meters": 0.0,
                    "nodes": [],
                    "node_count": 0,
                    "geojson": None,
                    "execution_ms": round(elapsed_ms, 2),
                }

            node_path = route_result.path
            dist_2d = 0.0
            dist_3d = 0.0
            gain_m = 0.0
            max_grade = 0.0
            maneuvers = []

            for i in range(len(node_path) - 1):
                cur_id = node_path[i]
                nxt_id = node_path[i + 1]

                cur_node = self.base_graph.get_node(cur_id)
                nxt_node = self.base_graph.get_node(nxt_id)
                if not cur_node or not nxt_node or not cur_node.coordinates or not nxt_node.coordinates:
                    continue

                d = haversine_distance(cur_node.coordinates, nxt_node.coordinates, unit="m")
                dist_2d += d

                if self.elevation_provider:
                    h1 = self.elevation_provider.get_elevation(cur_node.coordinates[1], cur_node.coordinates[0]) or 0.0
                    h2 = self.elevation_provider.get_elevation(nxt_node.coordinates[1], nxt_node.coordinates[0]) or 0.0
                    dh = h2 - h1
                    if dh > 0:
                        gain_m += dh
                    grade = (dh / d * 100.0) if d > 0 else 0.0
                    max_grade = max(max_grade, abs(grade))
                    dist_3d += math.hypot(d, dh)
                else:
                    dist_3d += d

                if i < len(node_path) - 2:
                    third_node = self.base_graph.get_node(node_path[i + 2])
                    if third_node and third_node.coordinates:
                        turn_angle = calculate_turn_angle(
                            cur_node.coordinates,
                            nxt_node.coordinates,
                            third_node.coordinates,
                        )
                        maneuver = classify_turn_maneuver(turn_angle)
                        if maneuver != "straight":
                            maneuvers.append({
                                "node_id": nxt_id,
                                "maneuver": maneuver,
                                "at_meters": round(dist_2d, 1),
                            })

            geojson_route = route_to_geojson(
                route=route_result,
                graph=self.base_graph,
                algorithm_name="AStar_Elevation" if elevation_aware else "AStar_Baseline",
            )

            return {
                "path_found": True,
                "origin_node": u_node,
                "destination_node": v_node,
                "duration_seconds": round(route_result.total_cost, 2),
                "distance_2d_meters": round(dist_2d, 1),
                "distance_3d_meters": round(dist_3d, 1),
                "elevation_gain_meters": round(gain_m, 1),
                "max_grade_percent": round(max_grade, 1),
                "nodes": node_path,
                "node_count": len(node_path),
                "maneuvers": maneuvers,
                "geojson": geojson_route,
                "execution_ms": round(elapsed_ms, 2),
            }

    # -------------------------------------------------------------------------
    # 911 Call Intake & AI Policy Orchestration
    # -------------------------------------------------------------------------

    def process_911_intake(
        self,
        raw_text: str,
        caller_phone: Optional[str] = None,
        location_coords: Optional[Tuple[float, float]] = None,
    ) -> Dict[str, Any]:
        """Execute the 5-stage dispatch and statutory policy pipeline."""
        with self._lock:
            staged_lon, staged_lat = (-122.3300, 47.6050)
            if location_coords:
                c0, c1 = float(location_coords[0]), float(location_coords[1])
                if abs(c0) <= 90.0:
                    staged_lat, staged_lon = c0, c1
                else:
                    staged_lon, staged_lat = c0, c1

            incident_node, _ = self.spatial_index.nearest_node((staged_lon, staged_lat))

            result = self.orchestrator.process(
                report=raw_text,
                coordinates=(staged_lon, staged_lat),
                node_id=incident_node,
            )

            urgency_str = (
                result.directive.effective_urgency.value
                if result.directive
                else (result.contract.urgency.value if result.contract and result.contract.urgency else "priority_1_echo")
            )

            # Broadcast live SSE alert
            self.broadcast_sse("incident_intake", {
                "intake_id": result.request_id,
                "urgency": urgency_str,
                "sanitized_summary": result.raw_report,
                "audit_checksum": result.audit_checksum,
            })

            # Format dispatched units
            dispatched = []
            for route in result.dispatched_routes:
                dispatched.append({
                    "unit_id": route.unit_id,
                    "apparatus_type": route.apparatus_type.value,
                    "station_id": route.station_id,
                    "eta_seconds": route.eta_seconds,
                    "route_path": list(route.route_path),
                })

            # Clinical hospital matching
            target_fac = None
            req_caps = None
            text_lower = raw_text.lower()
            if "cardiac" in text_lower:
                req_caps = {ClinicalCapability.CARDIAC_CARE}
            elif "burn" in text_lower:
                req_caps = {ClinicalCapability.BURN_CENTER}
            elif "trauma" in text_lower:
                req_caps = {ClinicalCapability.TRAUMA_LEVEL_1}

            nearest_hosp = find_nearest_clinical_facility(
                incident_node_id=incident_node,
                graph=self.dynamic_graph,
                candidate_pois=self.pois,
                bindings=self.poi_bindings,
                required_capabilities=req_caps,
            )
            if nearest_hosp:
                best_poi, best_bind, best_path, best_cost = nearest_hosp
                target_fac = {
                    "id": f"OSM-{best_poi.osm_type[0].upper()}-{best_poi.osm_id}",
                    "osm_id": best_poi.osm_id,
                    "name": best_poi.name,
                    "trauma_level": best_poi.trauma_level,
                    "capabilities": [c.value for c in best_poi.capabilities],
                    "travel_time_seconds": round(best_cost, 2),
                }

            policy_directives = (
                list(result.directive.policy_rules_applied)
                if result.directive
                else []
            )

            candidate_nodes = list(result.dispatched_routes[0].route_path) if result.dispatched_routes else []

            intake_res = {
                "intake_id": result.request_id,
                "sanitized_text": result.raw_report,
                "urgency": urgency_str,
                "policy_directives": policy_directives,
                "dispatched_units": dispatched,
                "destination_facility": target_fac,
                "candidate_route_found": len(dispatched) > 0,
                "candidate_route_nodes": candidate_nodes,
                "audit_checksum": result.audit_checksum,
                "incident_node": incident_node,
                "incident_coords": [staged_lon, staged_lat],
            }
            self.active_cad_incidents[result.request_id] = intake_res
            return intake_res

    # -------------------------------------------------------------------------
    # Dynamic Hazards & Bridge Severance
    # -------------------------------------------------------------------------

    def inject_hazard_polygon(
        self,
        polygon_coords: List[Tuple[float, float]],
        hazard_type: str = "flood_inundation",
        speed_multiplier: float = 0.0,
        severity: str = "critical_blocked",
    ) -> Dict[str, Any]:
        """Inject a 2D disaster hazard polygon, severing intersecting edges."""
        with self._lock:
            self._hazard_counter += 1
            hazard_id = f"HAZ_{self._hazard_counter:03d}"

            h_type = HazardType.FLOOD_INUNDATION
            if isinstance(hazard_type, HazardType):
                h_type = hazard_type
            elif isinstance(hazard_type, str):
                ht_clean = hazard_type.lower().strip()
                if "flood" in ht_clean:
                    h_type = HazardType.FLOOD_INUNDATION
                elif "wildfire" in ht_clean or "fire" in ht_clean:
                    h_type = HazardType.WILDFIRE_PERIMETER
                elif "gas" in ht_clean or "toxic" in ht_clean:
                    h_type = HazardType.TOXIC_GAS_PLUME
                elif "debris" in ht_clean or "collapse" in ht_clean:
                    h_type = HazardType.STRUCTURAL_DEBRIS
                else:
                    try:
                        h_type = HazardType(ht_clean)
                    except ValueError:
                        h_type = HazardType.FLOOD_INUNDATION

            sev = HazardSeverity.CRITICAL_BLOCKED
            if isinstance(severity, HazardSeverity):
                sev = severity
            elif isinstance(severity, str):
                s_clean = severity.lower().strip()
                if "critical" in s_clean:
                    sev = HazardSeverity.CRITICAL_BLOCKED
                elif "severe" in s_clean:
                    sev = HazardSeverity.SEVERE
                elif "mod" in s_clean:
                    sev = HazardSeverity.MODERATE
                elif "low" in s_clean:
                    sev = HazardSeverity.LOW
                else:
                    try:
                        sev = HazardSeverity(s_clean)
                    except ValueError:
                        sev = HazardSeverity.CRITICAL_BLOCKED

            poly = HazardPolygon(
                hazard_id=hazard_id,
                hazard_type=h_type,
                severity=sev,
                boundary_coordinates=polygon_coords,
                speed_multiplier=speed_multiplier,
                description=f"Dynamic Hazard {hazard_id} ({h_type.value})",
            )
            self.active_hazards[hazard_id] = poly

            mutations = self.dynamic_graph.apply_hazard(poly, bidirectional=True)
            closed_count = sum(1 for m in mutations if m.blocked)
            degraded_count = len(mutations) - closed_count

            # Broadcast SSE notification
            self.broadcast_sse("hazard_injected", {
                "hazard_id": hazard_id,
                "hazard_type": h_type.value,
                "edges_closed": closed_count,
                "edges_degraded": degraded_count,
            })

            return {
                "hazard_id": hazard_id,
                "edges_closed": closed_count,
                "edges_degraded": degraded_count,
                "total_active_hazards": len(self.active_hazards),
            }

    def clear_hazard(self, hazard_id: str) -> bool:
        """Clear a dynamic hazard and restore base edge connectivity."""
        with self._lock:
            if hazard_id not in self.active_hazards:
                return False

            del self.active_hazards[hazard_id]
            self.dynamic_graph.clear_mutations()

            for surviving_hazard in self.active_hazards.values():
                self.dynamic_graph.apply_hazard(surviving_hazard, bidirectional=True)

            self.broadcast_sse("hazard_cleared", {"hazard_id": hazard_id, "remaining": len(self.active_hazards)})
            return True

    def reset_all_hazards(self) -> int:
        """Clear all active hazards and revert graph to baseline state."""
        with self._lock:
            count = len(self.active_hazards)
            self.active_hazards.clear()
            self.dynamic_graph.clear_mutations()
            self.broadcast_sse("hazards_reset", {"cleared_count": count})
            return count

    # -------------------------------------------------------------------------
    # Discrete-Event Simulation & Playback Controller
    # -------------------------------------------------------------------------

    def _get_node_coords(self, node_id: str) -> List[float]:
        """Return [lon, lat] for a given graph node ID."""
        node = self.base_graph.get_node(node_id)
        if node and node.coordinates:
            return [float(node.coordinates[0]), float(node.coordinates[1])]
        return [-122.3300, 47.6050]

    def _init_simulation_state(self) -> None:
        """Initialize scenario incidents and fleet vehicle trackers."""
        self.simulation_time = 0.0
        self.simulation_active = False
        self.simulation_duration = getattr(self, "simulation_duration", 3600.0)
        self.simulation_scenario_name = getattr(self, "simulation_scenario_name", "metropolitan_disaster")

        self.simulated_incidents = [
            {
                "incident_id": "INC-101",
                "report_time": 10.0,
                "node_id": "N_0_1",
                "coords": self._get_node_coords("N_0_1"),
                "urgency": "PRIORITY_1_ECHO",
                "emergency_type": "CARDIAC_ARREST",
                "narrative": "Waterfront pedestrian collapsed, unresponsive, bystander CPR underway.",
                "required_apparatus": ["AMBULANCE_ALS", "FIRE_ENGINE"],
                "dispatched": False,
                "dispatched_units": [],
                "service_duration": 180.0,
                "status": "REPORTED",
            },
            {
                "incident_id": "INC-102",
                "report_time": 45.0,
                "node_id": "N_4_4",
                "coords": self._get_node_coords("N_4_4"),
                "urgency": "PRIORITY_1_DELTA",
                "emergency_type": "STRUCTURE_FIRE",
                "narrative": "Commercial 2-alarm warehouse fire on 4th Ave, heavy smoke visible.",
                "required_apparatus": ["FIRE_ENGINE", "LADDER_TRUCK"],
                "dispatched": False,
                "dispatched_units": [],
                "service_duration": 240.0,
                "status": "REPORTED",
            },
            {
                "incident_id": "INC-103",
                "report_time": 120.0,
                "node_id": "N_2_2",
                "coords": self._get_node_coords("N_2_2"),
                "urgency": "PRIORITY_1_ECHO",
                "emergency_type": "TRAFFIC_COLLISION",
                "narrative": "Multi-vehicle pileup near bridge approach with entrapment.",
                "required_apparatus": ["AMBULANCE_ALS", "FIRE_ENGINE"],
                "dispatched": False,
                "dispatched_units": [],
                "service_duration": 200.0,
                "status": "REPORTED",
            },
        ]

        self.simulated_vehicles = {}
        for unit in self.fleet_manager.list_units():
            unit_id = unit.unit_id
            home_node = unit.current_node_id or "N_0_0"
            coords = self._get_node_coords(home_node)
            self.simulated_vehicles[unit_id] = {
                "unit_id": unit_id,
                "apparatus_type": unit.apparatus_type.value,
                "station_id": unit.station_id,
                "home_node_id": home_node,
                "current_node_id": home_node,
                "current_coords": coords,
                "status": "AVAILABLE",
                "tracker": None,
                "assigned_incident_id": None,
                "arrived_time": None,
                "progress_ratio": 0.0,
                "distance_traveled_m": 0.0,
                "current_speed_mps": 15.0,
            }

    def _dispatch_simulated_incident(self, inc: Dict[str, Any]) -> None:
        """Find closest apparatus, plan paths, and assign trackers for a simulated incident."""
        target_node = inc["node_id"]
        for req_type in inc["required_apparatus"]:
            best_veh = None
            best_route = None
            best_cost = math.inf

            for veh in self.simulated_vehicles.values():
                if veh["status"] == "AVAILABLE" and veh["apparatus_type"].upper() == req_type.upper():
                    res = astar(self.dynamic_graph, source=veh["current_node_id"], destination=target_node)
                    if res.reachable and res.path and res.total_cost < best_cost:
                        best_cost = res.total_cost
                        best_route = res
                        best_veh = veh

            if best_veh and best_route and best_route.path:
                best_veh["status"] = "EN_ROUTE"
                best_veh["assigned_incident_id"] = inc["incident_id"]
                best_veh["tracker"] = DispatchedVehicleTracker(
                    unit_id=best_veh["unit_id"],
                    incident_id=inc["incident_id"],
                    destination_node_id=target_node,
                    path=list(best_route.path),
                )
                inc["dispatched_units"].append(best_veh["unit_id"])

        inc["dispatched"] = True
        inc["status"] = "DISPATCHED" if inc["dispatched_units"] else "QUEUED"

        self.broadcast_sse("cad_dispatch", {
            "incident_id": inc["incident_id"],
            "urgency": inc["urgency"],
            "narrative": inc["narrative"],
            "coords": inc["coords"],
            "node_id": inc["node_id"],
            "dispatched_units": inc["dispatched_units"],
        })

    def init_simulation(self, scenario_id: str = "metropolitan_disaster", max_duration_seconds: float = 3600.0) -> Dict[str, Any]:
        """Start or re-initialize a simulation scenario."""
        with self._lock:
            self.simulation_scenario_name = scenario_id
            self.simulation_duration = max_duration_seconds
            self._init_simulation_state()
            self.simulation_active = True
            return self.get_simulation_status()

    def step_simulation(self, step_seconds: float = 5.0, target_time: Optional[float] = None) -> Dict[str, Any]:
        """Advance simulation clock, kinematics, and active dispatches."""
        with self._lock:
            if target_time is not None:
                delta = max(0.0, target_time - self.simulation_time)
                self.simulation_time = target_time
            else:
                delta = step_seconds
                self.simulation_time += delta

            # 1. Dispatch any due incidents
            for inc in self.simulated_incidents:
                if inc["report_time"] <= self.simulation_time and not inc["dispatched"]:
                    self._dispatch_simulated_incident(inc)

            # 2. Advance vehicle trackers
            for veh in self.simulated_vehicles.values():
                tracker: Optional[DispatchedVehicleTracker] = veh.get("tracker")
                if tracker and not tracker.is_arrived:
                    # Realistic fraction advancement based on response travel time
                    fraction = min(1.0, max(0.05, delta / 60.0))
                    tracker.advance(fraction)

                    tail = self._get_node_coords(tracker.current_tail_node)
                    head = self._get_node_coords(tracker.current_head_node)
                    ratio = tracker.progress_ratio
                    lon = tail[0] + ratio * (head[0] - tail[0])
                    lat = tail[1] + ratio * (head[1] - tail[1])
                    veh["current_coords"] = [round(lon, 6), round(lat, 6)]
                    veh["progress_ratio"] = round(ratio, 3)
                    veh["distance_traveled_m"] = round(veh.get("distance_traveled_m", 0.0) + delta * 15.0, 1)

                    if tracker.is_arrived:
                        veh["status"] = "ON_SCENE"
                        veh["arrived_time"] = self.simulation_time
                        veh["current_node_id"] = tracker.destination_node_id
                        veh["current_coords"] = self._get_node_coords(tracker.destination_node_id)

                elif veh["status"] == "ON_SCENE":
                    arrived = veh.get("arrived_time", self.simulation_time)
                    if self.simulation_time - arrived >= 120.0:  # cleared scene
                        veh["status"] = "AVAILABLE"
                        veh["tracker"] = None
                        veh["assigned_incident_id"] = None

            status = self.get_simulation_status()
            self.broadcast_sse("simulation_step", status)
            return status

    def reset_simulation(self) -> Dict[str, Any]:
        """Reset simulation clock and return all units to station readiness."""
        with self._lock:
            self._init_simulation_state()
            self.simulation_active = False
            self.simulation_time = 0.0
            self.broadcast_sse("simulation_reset", {"status": "reset_successful", "simulation_time": 0.0, "current_sim_time": 0.0})
            return self.get_simulation_status()

    def get_simulation_status(self) -> Dict[str, Any]:
        """Compile complete current simulation and active CAD status."""
        with self._lock:
            vehs = []
            for v in self.simulated_vehicles.values():
                vehs.append({
                    "unit_id": v["unit_id"],
                    "vehicle_id": v["unit_id"],
                    "callsign": v["unit_id"],
                    "apparatus_type": v["apparatus_type"],
                    "station_id": v["station_id"],
                    "status": v["status"],
                    "current_node_id": v["current_node_id"],
                    "current_coords": v["current_coords"],
                    "progress_ratio": v.get("progress_ratio", 0.0),
                    "distance_traveled_m": v.get("distance_traveled_m", 0.0),
                    "assigned_incident_id": v["assigned_incident_id"],
                })

            incs = []
            for inc in self.simulated_incidents:
                incs.append({
                    "incident_id": inc["incident_id"],
                    "report_time": inc["report_time"],
                    "emergency_type": inc["emergency_type"],
                    "urgency": inc["urgency"],
                    "coords": inc["coords"],
                    "node_id": inc["node_id"],
                    "narrative": inc["narrative"],
                    "status": inc["status"],
                    "dispatched_units": inc["dispatched_units"],
                })

            return {
                "initialized": True,
                "is_running": self.simulation_active,
                "is_active": self.simulation_active,
                "current_sim_time": round(self.simulation_time, 1),
                "simulation_time": round(self.simulation_time, 1),
                "max_duration_seconds": getattr(self, "simulation_duration", 3600.0),
                "scenario_id": self.simulation_scenario_name,
                "vehicles": vehs,
                "incidents": incs,
                "active_incidents": incs,
                "active_cad_incidents_count": len(self.active_cad_incidents),
            }

