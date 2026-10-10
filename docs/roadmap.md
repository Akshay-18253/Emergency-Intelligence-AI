# Roadmap

> This roadmap describes the phased development strategy for
> Emergency Intelligence AI. Phases are ordered but do not carry
> fixed calendar dates. Progress is incremental and each phase
> establishes the foundation for the next.
>
> **Current position: Phase 4 (In Progress) — Milestone 1 Complete.**

---

## Phase 1 — Local Routing Engine Foundation

**Objective:** Prove the project can correctly model a road network
and compute shortest paths before introducing any AI.

| Milestone | Status |
|---|---|
| Milestone 1: Python structure, `Node`/`Edge`/`Graph`, manual Dijkstra, initial tests | ✅ Done |
| Milestone 2: Spatial coordinates, A* search, admissible heuristics, grid benchmarking | ✅ Done |
| Milestone 3: Real OSM Overpass parser, spherical Haversine formula, ambulance routing | ✅ Done |
| Phase 1 Test Suite: 117 tests passing, 96% branch coverage, zero dependencies | ✅ Done |

**Engineering focus:**
- Correctness first
- Every algorithm manually implemented before relying on a library
- Tests before adding complexity

---

## Phase 2 — Open-Source Ecosystem Participation

**Objective:** Understand relevant open-source routing and geospatial
ecosystems. Establish open GIS standards interoperability, architectural comparative
studies, and community contribution frameworks.

### Milestone Breakdown

| Milestone | Deliverables | Status |
|---|---|---|
| **Milestone 1: Geospatial Open Standards & Interoperability** | • RFC 7946 GeoJSON route & waypoint exporter (`route_to_geojson`, `save_route_geojson`)<br>• Unit tests verifying RFC 7946 compliance (`tests/test_geojson.py`)<br>• Interactive GIS demo script (`examples/geojson_export_demo.py`) | ✅ Complete |
| **Milestone 2: Ecosystem Architecture Comparative Study** | • Production engine deep dive: OSGeo/pgRouting, GraphHopper, Valhalla, OSRM<br>• Graph representation trade-offs: Node vs Edge-expanded vs Contraction Hierarchies vs Tiling<br>• Emergency Vehicle Routing (EVR) domain constraints analysis<br>• Comprehensive report ([`docs/ecosystem_study.md`](file:///d:/Personal/GSoC%20Project/Emergency%20Intelligence%20AI/docs/ecosystem_study.md))<br>• Dynamic incident rerouting demo ([`examples/architecture_comparison_demo.py`](file:///d:/Personal/GSoC%20Project/Emergency%20Intelligence%20AI/examples/architecture_comparison_demo.py)) | ✅ Complete |
| **Milestone 3: Community Governance & GSoC 2027 Alignment** | • Open-source contributor guidelines ([`CONTRIBUTING.md`](file:///d:/Personal/GSoC%20Project/Emergency%20Intelligence%20AI/CONTRIBUTING.md)) & Security Policy ([`SECURITY.md`](file:///d:/Personal/GSoC%20Project/Emergency%20Intelligence%20AI/SECURITY.md))<br>• Standardized `.github/` templates (Bug Report, Feature Request, GSoC Idea Proposal, PR Checklist)<br>• Automated multi-platform CI/CD workflow ([`.ci/workflows/ci.yml`](file:///d:/Personal/GSoC%20Project/Emergency%20Intelligence%20AI/.ci/workflows/ci.yml))<br>• Developer pre-flight sanity & AST zero-dependency audit script ([`scripts/check.py`](file:///d:/Personal/GSoC%20Project/Emergency%20Intelligence%20AI/scripts/check.py))<br>• GSoC 2027 mentoring organization analysis & curated starter tasks ([`docs/gsoc_strategy.md`](file:///d:/Personal/GSoC%20Project/Emergency%20Intelligence%20AI/docs/gsoc_strategy.md)) | ✅ Complete |

> ⚠️ **GSoC Disclaimer:** No specific mentoring organisation for GSoC 2027 is assumed.
> The appropriate organisation will be determined from official GSoC 2027
> announcements when available. Prospective fits (OSGeo, HOT/OSMF) are evaluated in
> [`docs/gsoc_strategy.md`](file:///d:/Personal/GSoC%20Project/Emergency%20Intelligence%20AI/docs/gsoc_strategy.md).

---

## Phase 3 — Real Road Network Data

**Objective:** Replace artificial graphs with real OpenStreetMap road networks,
introducing production-grade streaming ingestion, dynamic speed limit models,
emergency vehicle access rules, topological graph contraction, and spatial snapping.

### Milestone Breakdown

| Milestone | Deliverables | Status |
|---|---|---|
| **Milestone 1: Production OSM Ingestion & Multi-Criteria Cost Models** | • Streaming OSM XML (`.osm`) via `xml.etree.ElementTree.iterparse` & Overpass JSON dual parser<br>• Dynamic `maxspeed` parser (km/h, mph, condition tags, default highway speed matrix)<br>• Multi-criteria cost weighting profiles (`Profile.DISTANCE`, `Profile.TRAVEL_TIME`, `Profile.EMERGENCY_TIME`)<br>• Access restriction & emergency bypass filtering (`access=no`, `emergency=yes`)<br>• Comprehensive test suite & multi-criteria demo (`examples/osm_multimodal_demo.py`) | ✅ Complete |
| **Milestone 2: Graph Topology Hardening & Graph Contraction** | • Degree-2 intermediate node contraction with polyline geometry retention<br>• Largest Strongly Connected Component (LSCC) extraction via Tarjan's SCC algorithm<br>• Geographic forward azimuth bearing & turn maneuver classification ('straight', 'right', 'left', 'u_turn')<br>• Unit test suite ([`tests/test_topology.py`](file:///d:/Personal/GSoC%20Project/Emergency%20Intelligence%20AI/tests/test_topology.py)) & interactive demo ([`examples/topology_contraction_demo.py`](file:///d:/Personal/GSoC%20Project/Emergency%20Intelligence%20AI/examples/topology_contraction_demo.py)) | ✅ Complete |
| **Milestone 3: Spatial Snapping, Coordinate Indexing & Fast Network Caching** | • Zero-dependency 2D Spatial Hash Grid index for sub-millisecond coordinate lookups<br>• Orthogonal point-to-polyline road segment projection and snapping (`project_point_to_segment`, `snap_to_road_network`)<br>• Compiled network cache format (`.eig.json` with SHA-256 cryptographic integrity hash)<br>• Unit test suite ([`tests/test_spatial.py`](file:///d:/Personal/GSoC%20Project/Emergency%20Intelligence%20AI/tests/test_spatial.py)) & interactive demo ([`examples/spatial_indexing_demo.py`](file:///d:/Personal/GSoC%20Project/Emergency%20Intelligence%20AI/examples/spatial_indexing_demo.py)) | ✅ Complete |

**Engineering focus:**
- Zero external runtime dependencies (Python standard library only)
- Routing algorithms (`Dijkstra`, `AStarSearch`) remain completely decoupled from ingestion
- Every algorithm verified with unit tests and $\ge 90\%$ branch coverage gate
---

## Phase 4 — Dynamic Conditions & Real-Time Disaster Events

**Objective:** Enable event-driven route recalculation and emergency response
under dynamic disaster environments (floods, wildfires, road collapses, debris).

### Milestone Breakdown

| Milestone | Deliverables | Status |
|---|---|---|
| **Milestone 1: Dynamic Incident Taxonomy & Geometric Hazard Zones** | • 911 Incident domain models with urgency tiers (`UrgencyLevel`) and apparatus requirements (`ApparatusType`)<br>• 2D spatial disaster hazard polygons (`HazardPolygon`) with severity classification & speed multipliers<br>• Pure-Python vector ray-casting point-in-polygon & segment-polygon intersection engine<br>• Network edge penetration query (`find_edges_intersecting_hazard`, `find_hazards_affecting_edge`)<br>• Unit test suite ([`tests/test_incidents.py`](file:///d:/Personal/GSoC%20Project/Emergency%20Intelligence%20AI/tests/test_incidents.py), [`tests/test_hazards.py`](file:///d:/Personal/GSoC%20Project/Emergency%20Intelligence%20AI/tests/test_hazards.py)) & interactive demo ([`examples/disaster_hazard_demo.py`](file:///d:/Personal/GSoC%20Project/Emergency%20Intelligence%20AI/examples/disaster_hazard_demo.py)) | ✅ Complete |
| **Milestone 2: Non-Destructive Graph Mutation Layer & Invalidation Engine** | • Dynamic graph overlay layer (`DynamicGraphView`) for zero-overhead reversible edge closures and speed sinks<br>• Transactional rollback and snapshotting (`apply_mutation`, `rollback_transaction`, `create_snapshot`)<br>• Time-To-Live (TTL) automatic closure expiration timestamps (`purge_expired`)<br>• Unit test suite ([`tests/test_mutations.py`](file:///d:/Personal/GSoC%20Project/Emergency%20Intelligence%20AI/tests/test_mutations.py)) & live detour demo ([`examples/dynamic_closure_demo.py`](file:///d:/Personal/GSoC%20Project/Emergency%20Intelligence%20AI/examples/dynamic_closure_demo.py)) | ✅ Complete |
| **Milestone 3: Multi-Source Emergency Fleet Allocation & Apparatus Matching** | • Multi-source Dijkstra / Voronoi service catchment area partitioning (`compute_multi_source_catchment`)<br>• NFPA 1710 isochrone response frontiers (`compute_isochrone_frontiers`)<br>• Apparatus compatibility matcher & multi-criteria fleet ranking (`FleetManager`, `allocate_fleet_for_incident`)<br>• Unit test suite ([`tests/test_allocation.py`](file:///d:/Personal/GSoC%20Project/Emergency%20Intelligence%20AI/tests/test_allocation.py)) & fleet dispatch demo ([`examples/fleet_allocation_demo.py`](file:///d:/Personal/GSoC%20Project/Emergency%20Intelligence%20AI/examples/fleet_allocation_demo.py)) | ✅ Complete |
| **Milestone 4: In-Flight Reactive Rerouting & OASIS CAP Alert Ingestion** | • OASIS Common Alerting Protocol (CAP v1.2 / ITU-T X.1303 XML) & GeoJSON alert feed parsers (`parse_cap_xml`, `parse_geojson_alerts`)<br>• Real-time in-transit vehicle tracker (`DispatchedVehicleTracker`), route obstruction detection (`check_route_obstruction`), and mid-flight detour replanner (`replan_inflight_route`)<br>• Unit test suite ([`tests/test_inflight_and_alerts.py`](file:///d:/Personal/GSoC%20Project/Emergency%20Intelligence%20AI/tests/test_inflight_and_alerts.py)) & interactive ambulance detour demo ([`examples/inflight_rerouting_demo.py`](file:///d:/Personal/GSoC%20Project/Emergency%20Intelligence%20AI/examples/inflight_rerouting_demo.py))<br>• Verified sub-70 microsecond mid-flight reactive replanning | ✅ Complete |

**Engineering focus:**
- Event-driven reactive computing with zero-overhead graph overlay abstractions
- Pure Python vector geometry algorithms without heavy GIS dependencies
- 100% test coverage and continuous pre-flight gate verification

---

## Phase 5 — Emergency Intelligence

**Objective:** Introduce AI reasoning as an interpretation and
orchestration layer above the deterministic routing engine.

Example flow:

```
Input:  "My father is experiencing severe chest pain."
         ↓
AI Layer:
  Emergency type:        medical
  Priority:              critical
  Destination type:      cardiac unit
  Routing objective:     minimise travel time
  Constraints:           avoid road closures
         ↓
Routing Engine:          compute route
         ↓
Output:  Optimal route to nearest suitable hospital
```

The AI layer must:
- Output structured objects (not raw text to the routing engine)
- Be replaceable and testable independently
- Not perform route computation itself

---

## Phase 6 — Simulation and Evaluation

**Objective:** Create reproducible emergency scenarios and measure
routing quality quantitatively.

Example scenarios:
- Medical emergency (single incident)
- Fire response (single incident)
- Multiple simultaneous incidents
- Road closure during active routing
- Progressive congestion

Evaluation metrics:
- Route cost
- Travel time (estimated)
- Rerouting latency
- Nodes explored
- Memory usage
- Route stability under changing conditions
- Computational cost

This phase is critical for research credibility and eventual publication.

---

## Phase 7 — External Data and Map Integration

**Objective:** Integrate real-world open data sources where they
improve evaluation quality.

Principles:
- Open standards and open datasets only
- Any external integration must be documented, isolated, and replaceable
- Integration must not affect core routing logic correctness

---

## Phase 8 — Prototype Application

**Objective:** Build a user-facing prototype that demonstrates the
actual capabilities of the routing engine.

Principles:
- The UI reflects what the system can actually do
- No visual polish that obscures limitations
- Thin API layer above the routing engine
- Map visualisation requires node coordinates (introduced in Phase 3)

---

## Phase 9 — GSoC Proposal Preparation

**Objective:** Identify an appropriate open-source mentoring organisation
and prepare a credible, technically grounded proposal.

This phase begins only after:
- Official GSoC 2027 participating organisations are announced
- Genuine contributions to the ecosystem have been made
- A well-scoped technical problem aligned with maintainer needs is identified

Activities:
- Study official GSoC 2027 project lists from announced organisations
- Communicate with maintainers
- Align project scope with real needs
- Prepare proposal with technical milestones and measurable deliverables
- Include prior contributions and evaluation strategy

> ⚠️ Do not begin proposal writing until the appropriate organisation
> has been identified and community relationships have been established.

---

## Principles Across All Phases

- No phase is skipped or rushed
- Each phase produces tested, documented, working code
- Claims are never made beyond what has been implemented
- Dependencies are introduced only when justified
- The routing engine remains decoupled from the AI layer at all times
