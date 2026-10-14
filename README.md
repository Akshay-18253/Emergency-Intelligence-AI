# Emergency Intelligence AI

> **Phase 8 Status — Interactive Prototype Application Underway (Milestones 8.1 & 8.2 Complete)**  
> Deterministic emergency routing, real-world OpenStreetMap ingestion, 2D geometric disaster hazard zones,
> non-destructive graph mutations, multi-source Voronoi fleet catchment, in-flight reactive rerouting,
> OASIS CAP v1.2 alert feed ingestion, schema-constrained structured model adapter, statutory SOP policy engine,
> tamper-evident audit verification, discrete-event simulation engine, continuous kinematics, multi-format exporters,
> live OSM Overpass POI ingestion, NASA SRTM topographic elevation models, USGS / Open-Meteo flood telemetry, Web Mercator Leaflet GIS visualizer, metropolitan disaster benchmark, zero-dependency embedded HTTP server / REST & SSE gateway, and tactical operations dashboard with interactive GIS canvas.  
> **640 unit tests passing with 94.13% code coverage across 52 modules.** Zero external runtime dependencies (100% Python standard library).
>
> 📖 **Master Engineering Chronicle:** See [`updates.md`](updates.md) for the exhaustive technical ledger of all completed milestones (1.1 through 8.2) with mathematical formulations, test suites, and interactive demo scripts.

---

## Problem

Traditional navigation systems optimise for ordinary civilian objectives:
shortest distance, estimated travel time, and typical traffic congestion patterns.

Emergency navigation introduces fundamentally different constraints:

- **Emergency type & apparatus** — ALS/BLS ambulances, fire engines, ladder trucks, heavy rescue, hazmat units
- **Urgency & response tiers** — critical (E1 life-threatening), high (E2 emergency), moderate (E3 urgent), low (E4 non-emergency)
- **Destination capabilities** — trauma centres, cardiac catheterization units, burn centers, pediatric EDs
- **Dynamic road conditions** — structural collapses, flash floods, wildfire perimeters, toxic gas plumes, downed wires
- **NFPA 1710 standards** — 240-second (4-minute) first-due travel times and 480-second (8-minute) full alarm frontiers
- **Mid-flight dynamic replanning** — sub-millisecond route recalculation when dispatched vehicles encounter emerging closures
- **Statutory policy invariance** — statutory dispatch rules that cannot be downgraded or hallucinated away by probabilistic AI models
- **Audit trail integrity & privacy** — reconstructable sequence of decisions with zero PII leakage and cryptographic sequence verification

Existing navigation engines are not built to reason about these multi-dimensional disaster constraints transparently.

---

## Motivation

Emergency response time is a critical factor in patient survival and disaster mitigation.
A system that can intelligently route and dispatch emergency apparatus through
a dynamically changing road network — while remaining explainable, reproducible, and testable —
has significant research and open-source civic value.

This project investigates how such a system can be built from deterministic engineering foundations,
with AI reasoning introduced strictly as an interpretation and orchestration layer.

---

## Long-Term Vision

The complete system combines:

1. **Road network data** — Real OpenStreetMap (OSM) streaming XML and Overpass JSON data
2. **Graph-based routing** — Decoupled, verified algorithms (Dijkstra, A\*, multi-criteria weighting)
3. **Open GIS interoperability** — RFC 7946 GeoJSON export for QGIS, Leaflet, Kepler.gl, and PostGIS
4. **Dynamic conditions & hazards** — 2D vector hazard polygons (ray-casting), edge penetration detection, and non-destructive graph overlay mutations (`DynamicGraphView`)
5. **Multi-source catchment & fleet dispatch** — Voronoi service partitioning, NFPA 1710 isochrones, and apparatus matching
6. **Reactive in-flight rerouting** — In-transit vehicle progression tracking, downstream obstruction detection, and sub-millisecond detour replanning
7. **Federal alert ingestion** — OASIS Common Alerting Protocol (CAP v1.2 / ITU-T X.1303 XML) and GeoJSON alert feeds
8. **Emergency intelligence** — Natural-language report interpretation, schema-constrained structured output generation, and statutory policy enforcement
9. **Tamper-evident auditability** — Reconstructable decision sequences, SHA-256 audit trail verification, and safe failure boundaries
10. **Simulation & quantitative benchmarking** — Reproducible scenarios measuring reroute latency, search space pruning, and travel time

### Architectural Separation of Concerns

```
Unstructured 911 / Emergency Input (Call, SMS, CAD Alert)
                       │
                       ▼
Phase 5: Emergency Intelligence & Orchestration Layer
         ├── Intake & Sanitization (PII masking, length bounds, injection detection)
         ├── Structured Model Adapter (Schema-constrained JSON extraction & bounded retries)
         ├── Deterministic Contract Boundary (ValidatedIncidentContract & coordinate bounds)
         ├── Authoritative Statutory Policy Engine (NFPA 1710 full alarms & cardiac mandates)
         └── Audit Trail & Integrity Checksum (SHA-256 digest & operator authorization context)
                       │ structured dispatch models & statutory constraints
                       ▼
Phase 4: Dynamic Conditions & Federal Alert Processing
         ├── OASIS CAP v1.2 XML / GeoJSON alert feed parser
         ├── 2D Geometric Hazard Zones (vector ray-casting & polygon intersections)
         ├── Non-Destructive DynamicGraphView (transactional closures & speed sinks)
         ├── Multi-Source Voronoi Catchment & NFPA 1710 Isochrones
         └── In-Flight Vehicle Tracker & Mid-Flight Detour Replanning
                       │
                       ▼
Phase 1/2: Deterministic Routing Engine (Dijkstra / A* / Multi-Criteria)
                       │
                       ▼
Phase 3: Topologically Contracted Road Graph (OSM / Compiled Cache)
                       │
                       ▼
Phase 6: Simulation, Benchmarking & Quantitative Evaluation
         ├── Discrete-Event Engine & Continuous Kinematics (SimulationTimeline)
         ├── Multi-Incident Scenarios & Municipal Resource Contention Models
         ├── NFPA 1710 Travel Time Analysis & Search Space Pruning Profiler
         ├── Comparative Routing Harness (Static vs Polling vs Reactive)
         └── Multi-Format Exporter (JSON Telemetry, RFC 4180 CSV, RFC 7946 GeoJSON)
                       │
                       ▼
Phase 7: External Data & Geospatial Map Integration
         ├── Live OSM Overpass QL Query Builder & Emergency POI Extractor
         ├── Trauma Tiers 1-4, Burn, Pediatric, Cardiac, Bay Triage Extraction
         ├── Orthogonal Spatial Index Snapping & POI Road Network Binding
         ├── Dynamic Fleet Generation & Multi-Criteria Hospital Routing
         ├── NASA SRTM Elevation Model & Sub-Grid Bilinear Interpolation
         └── Apparatus Incline Physics, Climb Limits & Elevation Graph Views
                       │
                       ▼
Candidate Route & Telemetry (RFC 7946 GeoJSON Export)
```

> **Core Principle:** AI interprets emergency context and formulates routing objectives.
> Deterministic algorithms compute the route. Authoritative statutory policy engines strictly
> overrule model hallucinations. This prevents LLM under-triage in life-critical navigation.

---

## Engineering Philosophy

This project is developed **brick by brick**.

Priorities (in order):
1. **Correctness & Zero Dependencies** — Core library relies 100% on the Python standard library. No external GIS, scientific, or LLM runtime packages required.
2. **Deterministic Reproducibility** — Every algorithm has verified mathematical, geometric, and invariant test cases.
3. **High Test Coverage** — Strict $\ge 90\%$ branch and statement coverage enforcement (currently **96.09%** across 612 tests).
4. **Sub-Millisecond Performance** — Critical path algorithms (detours, ray casting, heuristic lookups) run in microseconds.
5. **Open Standards** — Full compatibility with OpenStreetMap, RFC 7946 GeoJSON, and OASIS CAP v1.2.
6. **Fail-Safe Operation** — Topologically disconnected nodes, missing coordinates, and malformed inputs fail safe to staged turnout or clarification prompts.

---

## Current Capabilities (Phases 1–7 Complete)

| Capability | Module | Status |
|---|---|:---:|
| Road graph model (`Node`, `Edge`, `Graph`) | [`graph/models.py`](src/emergency_intelligence/graph/models.py) | ✅ Implemented |
| Dijkstra's shortest-path algorithm (manual `heapq`) | [`graph/dijkstra.py`](src/emergency_intelligence/graph/dijkstra.py) | ✅ Implemented |
| Admissible distance heuristics (Euclidean, Manhattan, Zero, Haversine) | [`graph/heuristics.py`](src/emergency_intelligence/graph/heuristics.py) | ✅ Implemented |
| A\* heuristic search algorithm (tie-breaking with cost priority) | [`graph/astar.py`](src/emergency_intelligence/graph/astar.py) | ✅ Implemented |
| Algorithmic benchmarking & comparative evaluation | [`graph/benchmark.py`](src/emergency_intelligence/graph/benchmark.py) | ✅ Implemented |
| Spherical Haversine distance & bearing geometry | [`data/geo.py`](src/emergency_intelligence/data/geo.py) | ✅ Implemented |
| Streaming OpenStreetMap parser (`.osm` XML iterparse & Overpass JSON) | [`data/osm.py`](src/emergency_intelligence/data/osm.py) | ✅ Implemented |
| Multi-criteria cost weighting (`DISTANCE`, `TRAVEL_TIME`, `EMERGENCY_TIME`) | [`data/osm.py`](src/emergency_intelligence/data/osm.py) | ✅ Implemented |
| Topologically contracted graph & intermediate degree-2 node contraction | [`graph/topology.py`](src/emergency_intelligence/graph/topology.py) | ✅ Implemented |
| Tarjan's Strongly Connected Components (LSCC filter) | [`graph/topology.py`](src/emergency_intelligence/graph/topology.py) | ✅ Implemented |
| Forward azimuth bearings & turn maneuver classification | [`graph/topology.py`](src/emergency_intelligence/graph/topology.py) | ✅ Implemented |
| 2D Spatial Hash Grid indexing for sub-millisecond point lookups | [`data/spatial.py`](src/emergency_intelligence/data/spatial.py) | ✅ Implemented |
| Orthogonal point-to-polyline segment projection & network snapping | [`data/spatial.py`](src/emergency_intelligence/data/spatial.py) | ✅ Implemented |
| Compiled network cache (`.eig.json` with SHA-256 integrity verification) | [`data/cache.py`](src/emergency_intelligence/data/cache.py) | ✅ Implemented |
| RFC 7946 GeoJSON export for QGIS / Leaflet (`route_to_geojson`) | [`data/geojson.py`](src/emergency_intelligence/data/geojson.py) | ✅ Implemented |
| 911 Incident domain models & urgency tiers (E1..E4) | [`events/incidents.py`](src/emergency_intelligence/events/incidents.py) | ✅ Implemented |
| 2D geometric hazard polygons (`HazardPolygon`) with severity classes | [`events/hazards.py`](src/emergency_intelligence/events/hazards.py) | ✅ Implemented |
| Pure-Python vector ray-casting & segment-polygon intersection engine | [`events/hazards.py`](src/emergency_intelligence/events/hazards.py) | ✅ Implemented |
| Non-destructive dynamic graph mutation overlay (`DynamicGraphView`) | [`events/mutations.py`](src/emergency_intelligence/events/mutations.py) | ✅ Implemented |
| Transactional mutation rollback & Time-To-Live (TTL) expiration | [`events/mutations.py`](src/emergency_intelligence/events/mutations.py) | ✅ Implemented |
| Multi-source Dijkstra / Voronoi service catchment area partitioning | [`allocation/catchment.py`](src/emergency_intelligence/allocation/catchment.py) | ✅ Implemented |
| NFPA 1710 isochrone response frontiers (4 min / 8 min) | [`allocation/catchment.py`](src/emergency_intelligence/allocation/catchment.py) | ✅ Implemented |
| Emergency fleet manager & apparatus capability compatibility matching | [`allocation/matcher.py`](src/emergency_intelligence/allocation/matcher.py) | ✅ Implemented |
| In-flight dispatched vehicle tracking (`DispatchedVehicleTracker`) | [`events/inflight.py`](src/emergency_intelligence/events/inflight.py) | ✅ Implemented |
| Downstream route collision detection & sub-millisecond detour replanning | [`events/inflight.py`](src/emergency_intelligence/events/inflight.py) | ✅ Implemented |
| OASIS CAP v1.2 XML (ITU-T X.1303) & GeoJSON alert feed parser | [`events/alerts.py`](src/emergency_intelligence/events/alerts.py) | ✅ Implemented |
| Immutable domain contracts & coordinate validation | [`intelligence/contracts.py`](src/emergency_intelligence/intelligence/contracts.py) | ✅ Implemented |
| Deterministic emergency policy engine (NFPA 1710 / SOP mandates) | [`intelligence/policy.py`](src/emergency_intelligence/intelligence/policy.py) | ✅ Implemented |
| Provider-independent natural-language interpreter interface | [`intelligence/interpreter.py`](src/emergency_intelligence/intelligence/interpreter.py) | ✅ Implemented |
| Schema-constrained structured model adapter & bounded retry policy | [`intelligence/adapter.py`](src/emergency_intelligence/intelligence/adapter.py) | ✅ Implemented |
| End-to-end pipeline orchestrator & CAD geocode manual overrides | [`intelligence/orchestrator.py`](src/emergency_intelligence/intelligence/orchestrator.py) | ✅ Implemented |
| Tamper-evident audit trail & SHA-256 sequence integrity verification | [`intelligence/orchestrator.py`](src/emergency_intelligence/intelligence/orchestrator.py) | ✅ Implemented |
| Discrete-event virtual simulation clock & priority timeline | [`simulation/timeline.py`](src/emergency_intelligence/simulation/timeline.py) | ✅ Implemented |
| Continuous vehicle kinematics along road edges (`VehicleSimState`) | [`simulation/engine.py`](src/emergency_intelligence/simulation/engine.py) | ✅ Implemented |
| Discrete-event disaster simulation engine (`SimulationEngine`) | [`simulation/engine.py`](src/emergency_intelligence/simulation/engine.py) | ✅ Implemented |
| Reproducible multi-incident scenarios & municipal contention models | [`simulation/scenarios.py`](src/emergency_intelligence/simulation/scenarios.py) | ✅ Implemented |
| NFPA 1710 compliance analyzer & percentile response times | [`evaluation/metrics.py`](src/emergency_intelligence/evaluation/metrics.py) | ✅ Implemented |
| Path Stability Index ($PSI$) & Detour Delay Factor ($DDF$) | [`evaluation/metrics.py`](src/emergency_intelligence/evaluation/metrics.py) | ✅ Implemented |
| Microsecond algorithmic profiler & $A^*$ pruning verification | [`evaluation/profiler.py`](src/emergency_intelligence/evaluation/profiler.py) | ✅ Implemented |
| Comparative routing strategy benchmarks (Static, Polling, Reactive) | [`evaluation/benchmark.py`](src/emergency_intelligence/evaluation/benchmark.py) | ✅ Implemented |
| Multi-format simulation data exporter (JSON, RFC 4180 CSV, GeoJSON) | [`evaluation/exporter.py`](src/emergency_intelligence/evaluation/exporter.py) | ✅ Implemented |
| Live OpenStreetMap Overpass emergency POI extraction (`fetch_or_load_overpass_pois`) | [`external/overpass.py`](src/emergency_intelligence/external/overpass.py) | ✅ Implemented |
| Clinical capability extraction (Trauma 1–4, Burn, Pediatric, Cardiac, Bays) | [`external/overpass.py`](src/emergency_intelligence/external/overpass.py) | ✅ Implemented |
| Orthogonal POI network projection & spatial binding (`bind_poi_to_network`) | [`external/binding.py`](src/emergency_intelligence/external/binding.py) | ✅ Implemented |
| Dynamic station fleet generation from OSM POIs (`create_fleet_from_pois`) | [`external/binding.py`](src/emergency_intelligence/external/binding.py) | ✅ Implemented |
| Multi-criteria specialized clinical facility transport routing | [`external/binding.py`](src/emergency_intelligence/external/binding.py) | ✅ Implemented |
| NASA SRTM HGT binary elevation ingestion (SRTM1, SRTM3) & parsing | [`external/elevation.py`](src/emergency_intelligence/external/elevation.py) | ✅ Implemented |
| Continuous sub-grid bilinear elevation interpolation with void handling | [`external/elevation.py`](src/emergency_intelligence/external/elevation.py) | ✅ Implemented |
| 3D Euclidean distance & terrain slope grade kinematics | [`external/elevation.py`](src/emergency_intelligence/external/elevation.py) | ✅ Implemented |
| Apparatus powertrain climb/descent speed penalties & max grade gates | [`external/elevation.py`](src/emergency_intelligence/external/elevation.py) | ✅ Implemented |
| Dynamic elevation-aware routing graph views & hill detour routing | [`external/elevation.py`](src/emergency_intelligence/external/elevation.py) | ✅ Implemented |
| Real-time USGS river gauge flood hydrology & NWS stage classification | [`external/hydrology.py`](src/emergency_intelligence/external/hydrology.py) | ✅ Implemented |
| Open-Meteo weather code ingestion & dynamic hazard polygon generation | [`external/hydrology.py`](src/emergency_intelligence/external/hydrology.py) | ✅ Implemented |
| Web Mercator slippy tile forward/inverse projection math (EPSG:3857) | [`external/visualizer.py`](src/emergency_intelligence/external/visualizer.py) | ✅ Implemented |
| Pure-Python zero-dependency interactive Leaflet GIS map renderer | [`external/visualizer.py`](src/emergency_intelligence/external/visualizer.py) | ✅ Implemented |
| City-scale metropolitan disaster benchmark & end-to-end integration suite | [`external/benchmark.py`](src/emergency_intelligence/external/benchmark.py) | ✅ Implemented |
| Automated pre-flight sanity checker & AST zero-dependency audit | [`scripts/check.py`](scripts/check.py) | ✅ Implemented |

---

## Project Structure

```
emergency-intelligence-ai/
├── src/
│   └── emergency_intelligence/
│       ├── __init__.py
│       ├── allocation/                    # Phase 4 Milestone 3: Fleet & Catchment
│       │   ├── __init__.py
│       │   ├── models.py                  # Apparatus, EmergencyFacility, IncidentAssignment
│       │   ├── catchment.py               # Multi-source Voronoi & NFPA 1710 isochrones
│       │   └── matcher.py                 # Apparatus capability matching & fleet dispatch
│       ├── data/                          # Phase 2 & 3: Data Ingestion & Geometry
│       │   ├── __init__.py
│       │   ├── geo.py                     # Haversine distance, bearing, & geographic math
│       │   ├── geojson.py                 # RFC 7946 GeoJSON export & round-trip ingestion
│       │   ├── osm.py                     # Streaming OSM XML iterparse & Overpass JSON
│       │   ├── spatial.py                 # 2D Spatial Hash Grid & road segment snapping
│       │   ├── cache.py                   # Compiled network cache with SHA-256 hash
│       │   └── sample_hospital_district.json # Bundled real OSM hospital district
│       ├── events/                        # Phase 4: Dynamic Conditions & Alerts
│       │   ├── __init__.py
│       │   ├── incidents.py               # 911 Incident domain models & urgency tiers
│       │   ├── hazards.py                 # 2D geometric hazard polygons & vector ray-casting
│       │   ├── mutations.py               # DynamicGraphView, transactional mutations, & TTL
│       │   ├── inflight.py                # Dispatched vehicle tracker & detour replanning
│       │   └── alerts.py                  # OASIS CAP v1.2 XML & GeoJSON alert ingestion
│       ├── graph/                         # Phase 1: Core Graph & Routing Algorithms
│       │   ├── __init__.py
│       │   ├── models.py                  # Node, Edge, Graph core primitives
│       │   ├── dijkstra.py                # Dijkstra shortest-path with manual heapq
│       │   ├── astar.py                   # A* informed heuristic search
│       │   ├── heuristics.py              # Euclidean, Manhattan, Zero heuristics
│       │   ├── topology.py                # Graph contraction, LSCC filter, & turn angles
│       │   └── benchmark.py               # Comparative benchmark harness
│       ├── intelligence/                  # Phase 5: AI Reasoning & Policy Orchestration
│       │   ├── __init__.py
│       │   ├── contracts.py               # ValidatedIncidentContract & location provenance
│       │   ├── policy.py                  # EmergencyPolicyEngine & statutory apparatus mandates
│       │   ├── interpreter.py             # EmergencyInterpreter & PI/adversarial sanitization
│       │   ├── adapter.py                 # StructuredModelAdapter, RetryPolicy, FakeModelProvider
│       │   └── orchestrator.py            # EmergencyIntelligenceOrchestrator & audit trail
│       ├── simulation/                    # Phase 6: Discrete-Event Disaster Simulation
│       │   ├── __init__.py
│       │   ├── timeline.py                # SimulationClock, SimEvent, SimulationTimeline priority queue
│       │   ├── engine.py                  # SimulationEngine, continuous vehicle motion & event hooks
│       │   └── scenarios.py               # Reproducible multi-incident scenarios & contention models
│       ├── evaluation/                    # Phase 6: Quantitative Evaluation & Metrics
│       │   ├── __init__.py
│       │   ├── metrics.py                 # NFPA 1710 compliance, Path Stability Index (PSI), Detour Delay (DDF)
│       │   ├── profiler.py                # Algorithmic latency & A* search space pruning profiler
│       │   ├── benchmark.py               # Comparative routing harness (Static vs Polling vs Reactive)
│       │   └── exporter.py                # JSON time-series telemetry, RFC 4180 CSV, RFC 7946 GeoJSON
│       └── external/                      # Phase 7: External Data & Map Integration
│           ├── __init__.py
│           ├── overpass.py                # Overpass QL query builder, POI parser & cached client
│           ├── binding.py                 # Spatial POI network binding, fleet creation & clinical routing
│           ├── elevation.py               # NASA SRTM DEM parser, bilinear interpolation, slope kinematics
│           ├── hydrology.py               # USGS river gauge telemetry & Open-Meteo weather alerts
│           ├── visualizer.py              # Web Mercator slippy tile math & zero-dep Leaflet GIS map renderer
│           └── benchmark.py               # Metropolitan disaster benchmark & end-to-end integration suite
├── tests/                                 # 612 test cases, >= 96% coverage
│   ├── test_models.py
│   ├── test_dijkstra.py
│   ├── test_heuristics.py
│   ├── test_astar.py
│   ├── test_benchmark.py
│   ├── test_geo.py
│   ├── test_osm.py
│   ├── test_geojson.py
│   ├── test_topology.py
│   ├── test_spatial.py
│   ├── test_incidents.py
│   ├── test_hazards.py
│   ├── test_mutations.py
│   ├── test_allocation.py
│   ├── test_inflight_and_alerts.py
│   ├── test_contracts.py                  # Phase 5 Milestone 5.1 tests
│   ├── test_policy.py                     # Phase 5 Milestone 5.2 tests
│   ├── test_interpreter.py                # Phase 5 Milestone 5.3 tests
│   ├── test_adapter_and_orchestration.py  # Phase 5 Milestone 5.4 tests
│   ├── test_audit_and_verification.py     # Phase 5 Milestone 5.5 tests
│   ├── test_simulation_engine.py          # Phase 6 Milestone 6.1 tests
│   ├── test_scenarios.py                  # Phase 6 Milestone 6.2 tests
│   ├── test_evaluation.py                 # Phase 6 Milestone 6.3 tests
│   ├── test_benchmarks.py                 # Phase 6 Milestone 6.4 tests
│   ├── test_overpass_poi.py               # Phase 7 Milestone 7.1 tests
│   ├── test_elevation.py                  # Phase 7 Milestone 7.2 tests
│   ├── test_hydrology_and_weather.py      # Phase 7 Milestone 7.3 tests
│   ├── test_visualizer.py                 # Phase 7 Milestone 7.4 tests
│   └── test_metropolitan_benchmark.py     # Phase 7 Milestone 7.5 tests
├── examples/                              # 25 runnable demonstration scripts
│   ├── demo.py                            # 1. Dijkstra foundation demonstration
│   ├── benchmark_demo.py                  # 2. A* vs Dijkstra comparative benchmark
│   ├── osm_demo.py                        # 3. Real OpenStreetMap emergency routing
│   ├── geojson_export_demo.py             # 4. RFC 7946 GeoJSON export demonstration
│   ├── architecture_comparison_demo.py    # 5. Production routing engine comparison
│   ├── osm_multimodal_demo.py             # 6. Multi-criteria cost weighting & speed limits
│   ├── topology_contraction_demo.py       # 7. Topology contraction & LSCC extraction
│   ├── spatial_indexing_demo.py           # 8. Spatial hash grid & road snapping
│   ├── disaster_hazard_demo.py            # 9. Geometric hazard polygon penetration
│   ├── dynamic_closure_demo.py            # 10. Non-destructive dynamic graph closures
│   ├── fleet_allocation_demo.py           # 11. Multi-source Voronoi catchment & fleet dispatch
│   ├── inflight_rerouting_demo.py         # 12. OASIS CAP alert ingestion & mid-flight detours
│   ├── natural_language_interpreter_demo.py # 13. Natural-language report parsing & sanitization
│   ├── orchestration_pipeline_demo.py     # 14. Full end-to-end orchestration pipeline
│   ├── verification_and_audit_demo.py     # 15. Audit trail integrity & policy invariance
│   ├── simulation_engine_demo.py          # 16. Discrete-event disaster simulation engine
│   ├── multi_incident_scenarios_demo.py   # 17. Multi-incident resource contention & mutual aid
│   ├── metrics_profiler_demo.py           # 18. NFPA 1710 compliance & search space pruning
│   ├── comparative_benchmark_demo.py      # 19. Comparative routing benchmarks & multi-format export
│   ├── simulation_suite_demo.py           # 20. Master end-to-end simulation & evaluation suite
│   ├── overpass_poi_demo.py               # 21. Live OSM Overpass emergency POI & clinical routing
│   ├── elevation_routing_demo.py          # 22. NASA SRTM elevation model & apparatus incline routing
│   ├── hydrology_hazard_demo.py           # 23. Real-time USGS flood telemetry & Open-Meteo weather routing
│   ├── map_visualizer_demo.py             # 24. Zero-dependency interactive Leaflet GIS tactical emergency map
│   └── metropolitan_benchmark_demo.py     # 25. City-scale metropolitan disaster benchmark & integration suite
├── scripts/
│   └── check.py                           # Pre-flight sanity checker & AST zero-dep audit
├── docs/
│   ├── architecture.md                    # System architecture & decision records
│   ├── roadmap.md                         # Complete 9-phase development roadmap
│   ├── ecosystem_study.md                 # Routing engine comparative study
│   ├── gsoc_strategy.md                   # GSoC 2027 alignment & participation strategy
│   ├── development.md                     # Engineering practices & contribution guide
│   ├── milestone_5_1_report.md            # Phase 5 Milestone 5.1 verification report
│   ├── milestone_5_2_report.md            # Phase 5 Milestone 5.2 verification report
│   ├── milestone_5_3_report.md            # Phase 5 Milestone 5.3 verification report
│   ├── milestone_5_4_report.md            # Phase 5 Milestone 5.4 verification report
│   ├── milestone_5_5_report.md            # Phase 5 Milestone 5.5 verification report
│   ├── audit_report_phase_5_5.md          # Phase 5 Milestone 5.5 source-level audit report
│   ├── milestone_6_1_report.md            # Phase 6 Milestone 6.1 verification report
│   ├── milestone_6_2_report.md            # Phase 6 Milestone 6.2 verification report
│   ├── milestone_6_3_report.md            # Phase 6 Milestone 6.3 verification report
│   ├── milestone_6_4_report.md            # Phase 6 Milestone 6.4 verification report
│   ├── milestone_6_evaluation_report.md   # Phase 6 Milestone 6.5 empirical evaluation report
│   ├── milestone_7_1_report.md            # Phase 7 Milestone 7.1 verification report
│   ├── milestone_7_2_report.md            # Phase 7 Milestone 7.2 verification report
│   ├── milestone_7_3_report.md            # Phase 7 Milestone 7.3 verification report
│   ├── milestone_7_4_report.md            # Phase 7 Milestone 7.4 verification report
│   └── milestone_7_report.md              # Phase 7 Completion & Verification Report
├── CONTRIBUTING.md
├── pyproject.toml
└── README.md
```

---

## Development Setup

Requires Python 3.10 or later.

```bash
# Clone the repository
git clone https://github.com/Akshay-18253/Emergency-Intelligence-AI.git
cd Emergency-Intelligence-AI

# Create and activate a virtual environment
python -m venv .venv

# On Linux / macOS
source .venv/bin/activate

# On Windows (PowerShell)
.venv\Scripts\Activate.ps1

# Install testing dependencies (runtime library requires 0 external dependencies)
pip install pytest pytest-cov
```

---

## Verification & Testing

### 1. Automated Pre-Flight Sanity Checker
We provide a unified verification script that enforces the Python version, performs an AST inspection across all 46 library modules to prove zero external runtime dependencies, runs the pytest suite with coverage enforcement, and executes all 25 demonstration scripts:

```bash
python scripts/check.py
```

### 2. Running Pytest Directly
```bash
# Run all 612 unit tests
pytest -v

# Run with statement and branch coverage enforcement (>= 90%)
pytest --cov=emergency_intelligence --cov-report=term-missing -v
```

---

## Interactive Demonstrations

All 27 demonstration scripts can be executed independently from the terminal:

| # | Demo Script | Description |
|---|---|---|
| **1** | `python examples/demo.py` | Baseline Dijkstra shortest path on an artificial emergency graph |
| **2** | `python examples/benchmark_demo.py` | A* vs Dijkstra benchmark measuring up to 90%+ search space pruning |
| **3** | `python examples/osm_demo.py` | Real OpenStreetMap hospital district ingestion and ambulance routing |
| **4** | `python examples/geojson_export_demo.py` | RFC 7946 GeoJSON telemetry export for QGIS, Leaflet, and Kepler.gl |
| **5** | `python examples/architecture_comparison_demo.py` | Comparison with OSGeo/pgRouting, Valhalla, GraphHopper, and OSRM |
| **6** | `python examples/osm_multimodal_demo.py` | Dynamic speed limit parsing and multi-criteria cost profiles (`EMERGENCY_TIME`) |
| **7** | `python examples/topology_contraction_demo.py` | Tarjan LSCC extraction, degree-2 node contraction, and turn classification |
| **8** | `python examples/spatial_indexing_demo.py` | 2D Spatial Hash Grid indexing, segment snapping, and fast `.eig.json` caching |
| **9** | `python examples/disaster_hazard_demo.py` | Vector ray-casting point-in-polygon and hazard zone penetration queries |
| **10** | `python examples/dynamic_closure_demo.py` | Non-destructive `DynamicGraphView` edge closures, transactional rollback, & TTL |
| **11** | `python examples/fleet_allocation_demo.py` | Multi-source Voronoi catchment partitioning, NFPA 1710 isochrones, & apparatus dispatch |
| **12** | `python examples/inflight_rerouting_demo.py` | Live OASIS CAP v1.2 XML alert ingestion and 65 $\mu$s in-flight detour replanning |
| **13** | `python examples/natural_language_interpreter_demo.py` | Natural-language report interpretation, PII sanitization, and adversarial injection defense |
| **14** | `python examples/orchestration_pipeline_demo.py` | Full 5-stage orchestration pipeline from raw 911 text to siren-privileged routing |
| **15** | `python examples/verification_and_audit_demo.py` | Tamper-evident audit trail, SHA-256 sequence hash, and policy invariance over under-triage |
| **16** | `python examples/simulation_engine_demo.py` | Discrete-event disaster simulation engine & continuous vehicle kinematics |
| **17** | `python examples/multi_incident_scenarios_demo.py` | Multi-incident resource contention & secondary station fallback |
| **18** | `python examples/metrics_profiler_demo.py` | NFPA 1710 response compliance, PSI/DDF degradation, & $A^*$ pruning profiler |
| **19** | `python examples/comparative_benchmark_demo.py` | Comparative routing strategies (Static vs Polling vs Reactive) & multi-format export |
| **20** | `python examples/simulation_suite_demo.py` | Master end-to-end interactive simulation demonstration uniting all 6 capabilities |
| **21** | `python examples/overpass_poi_demo.py` | Live OSM Overpass emergency POI extraction, clinical capability binding, & specialized hospital routing |
| **22** | `python examples/elevation_routing_demo.py` | NASA SRTM elevation model, 3D slope kinematics, & apparatus incline detour routing |
| **23** | `python examples/hydrology_hazard_demo.py` | Real-time USGS river gauge flood telemetry, Open-Meteo weather alerts, & flood bypass routing |
| **24** | `python examples/map_visualizer_demo.py` | Web Mercator tile projection & zero-dependency Leaflet GIS tactical emergency map generation |
| **25** | `python examples/metropolitan_benchmark_demo.py` | City-scale metropolitan disaster benchmark, multi-strategy routing evaluation & GIS export |
| **26** | `python examples/app_server_demo.py` | Embedded multi-threaded HTTP server, REST routing gateway, & SSE live telemetry stream |
| **27** | `python examples/dashboard_demo.py` | Tactical Operations Dashboard, Leaflet GIS canvas, 3D routing & dynamic hazard rerouting |

---

## Roadmap Summary

| Phase | Description | Status |
|---|---|:---:|
| **Phase 1** | Local routing engine foundation (Dijkstra, A*, Heuristics) | ✅ **Complete** |
| **Phase 2** | Open-source ecosystem participation & GIS standards (GeoJSON, Haversine, Ecosystem study) | ✅ **Complete** |
| **Phase 3** | Real road network data pipelines (Streaming OSM, Contraction, Spatial Index, Caching) | ✅ **Complete** |
| **Phase 4** | Dynamic conditions & disaster events (Hazards, Mutations, Voronoi Catchment, In-Flight Detours, CAP) | ✅ **Complete** |
| **Phase 5** | Emergency intelligence (AI natural language reasoning & dispatch orchestration layer) | ✅ **Complete** |
| **Phase 6** | Simulation and quantitative evaluation harness | ✅ **Complete** |
| **Phase 7** | External data and map integration (Milestones 7.1–7.5 Complete) | ✅ **Complete** |
| **Phase 8** | User-facing interactive prototype application (Milestones 8.1 & 8.2 Complete) | 🚀 **In Progress** |
| **Phase 9** | GSoC 2027 proposal preparation | 🔜 Future |

See [`docs/roadmap.md`](docs/roadmap.md) for the strategic phase development roadmap, and [`updates.md`](updates.md) for the exhaustive technical ledger of each and every milestone change.

---

## Disclaimer & Safety Boundary

This is an independent open-source research and engineering project. It is **not** officially affiliated with Google, Google Summer of Code, or any municipal dispatch authority.

**CRITICAL SAFETY NOTICE:** Passing automated software unit tests does not establish certification under statutory emergency response codes (NFPA, ISO, or municipal dispatch standards). All emergency apparatus turnouts, siren privileges, travel times, and vehicle tracking described herein are simulated in-memory algorithmic computations and are decoupled from physical sirens, radio transmitters, or real-world emergency dispatch consoles.

---

## License

MIT License. See `LICENSE` for details.
