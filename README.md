# Emergency Intelligence AI

> **Phase 4 Status — Dynamic Conditions & Real-Time Disaster Events (Complete)**
> Deterministic emergency routing, real-world OpenStreetMap ingestion, 2D geometric disaster hazard zones,
> non-destructive graph mutations, multi-source Voronoi fleet catchment, in-flight reactive rerouting, and
> OASIS CAP v1.2 alert feed ingestion.
> **295 unit tests passing with 95.07% code coverage.** Zero external runtime dependencies (100% Python standard library).

---

## Problem

Traditional navigation systems optimise for ordinary civilian objectives:
shortest distance, estimated travel time, typical congestion patterns.

Emergency navigation introduces fundamentally different constraints:

- **Emergency type & apparatus** — ALS/BLS ambulances, fire engines, ladder trucks, heavy rescue, hazmat units
- **Urgency & response tiers** — critical (E1 life-threatening), high (E2 emergency), moderate (E3 urgent), low (E4 non-emergency)
- **Destination capabilities** — trauma centres, cardiac catheterization units, burn centers, pediatric EDs
- **Dynamic road conditions** — structural collapses, flash floods, wildfire perimeters, toxic gas plumes, downed wires
- **NFPA 1710 standards** — 240-second (4-minute) first-due travel times and 480-second (8-minute) full alarm frontiers
- **Mid-flight dynamic replanning** — sub-millisecond route recalculation when dispatched vehicles encounter emerging closures

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
8. **Emergency intelligence** — AI reasoning to interpret unstructured dispatch transcripts and formulate deterministic routing policies
9. **Simulation & quantitative benchmarking** — Reproducible scenarios measuring reroute latency, search space pruning, and travel time

### Architectural Separation of Concerns

```
Unstructured 911 / Emergency Input (Call, SMS, CAD)
                       │
                       ▼
Phase 5: Emergency Intelligence (AI Reasoning & Policy Layer)
                       │ structured dispatch models & routing constraints
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
Candidate Route & Telemetry (RFC 7946 GeoJSON Export)
```

> **Core Principle:** AI interprets emergency context and formulates routing objectives.
> Deterministic algorithms compute the route. This prevents LLM hallucinations in life-critical navigation.

---

## Engineering Philosophy

This project is developed **brick by brick**.

Priorities (in order):
1. **Correctness & Zero Dependencies** — Core library relies 100% on the Python standard library. No external GIS or C++ wrappers required at runtime.
2. **Deterministic Reproducibility** — Every algorithm has verified mathematical and geometric test cases.
3. **High Test Coverage** — Strict $\ge 90\%$ branch and statement coverage enforcement (currently **95.07%** across 295 tests).
4. **Sub-Millisecond Performance** — Critical path algorithms (detours, ray casting, heuristic lookups) run in microseconds.
5. **Open Standards** — Full compatibility with OpenStreetMap, RFC 7946 GeoJSON, and OASIS CAP v1.2.

---

## Current Capabilities (Phase 4 Complete)

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
│       └── graph/                         # Phase 1: Core Graph & Routing Algorithms
│           ├── __init__.py
│           ├── models.py                  # Node, Edge, Graph core primitives
│           ├── dijkstra.py                # Dijkstra shortest-path with manual heapq
│           ├── astar.py                   # A* informed heuristic search
│           ├── heuristics.py              # Euclidean, Manhattan, Zero heuristics
│           ├── topology.py                # Graph contraction, LSCC filter, & turn angles
│           └── benchmark.py               # Comparative benchmark harness
├── tests/                                 # 295 test cases, >= 95% coverage
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
│   └── test_inflight_and_alerts.py
├── examples/                              # 12 runnable demonstration scripts
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
│   └── inflight_rerouting_demo.py         # 12. OASIS CAP alert ingestion & mid-flight detours
├── scripts/
│   └── check.py                           # Pre-flight sanity checker & AST zero-dep audit
├── docs/
│   ├── architecture.md                    # System architecture & decision records
│   ├── roadmap.md                         # Complete 9-phase development roadmap
│   ├── ecosystem_study.md                 # Routing engine comparative study
│   ├── gsoc_strategy.md                   # GSoC 2027 alignment & participation strategy
│   └── development.md                     # Engineering practices & contribution guide
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
We provide a unified verification script that enforces the Python version, performs an AST inspection across all 24 library modules to prove zero external runtime dependencies, runs the pytest suite with coverage enforcement, and executes all 12 demonstration scripts:

```bash
python scripts/check.py
```

### 2. Running Pytest Directly
```bash
# Run all 295 unit tests
pytest -v

# Run with statement and branch coverage enforcement (>= 90%)
pytest --cov=emergency_intelligence --cov-report=term-missing -v
```

---

## Interactive Demonstrations

All 12 demonstration scripts can be executed independently from the terminal:

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

---

## Roadmap Summary

| Phase | Description | Status |
|---|---|:---:|
| **Phase 1** | Local routing engine foundation (Dijkstra, A*, Heuristics) | ✅ **Complete** |
| **Phase 2** | Open-source ecosystem participation & GIS standards (GeoJSON, Haversine, Ecosystem study) | ✅ **Complete** |
| **Phase 3** | Real road network data pipelines (Streaming OSM, Contraction, Spatial Index, Caching) | ✅ **Complete** |
| **Phase 4** | Dynamic conditions & disaster events (Hazards, Mutations, Voronoi Catchment, In-Flight Detours, CAP) | ✅ **Complete** |
| **Phase 5** | Emergency intelligence (AI natural language reasoning & dispatch orchestration layer) | 🔜 **Next** |
| **Phase 6** | Simulation and quantitative evaluation harness | 🔜 Future |
| **Phase 7** | External data and map integration | 🔜 Future |
| **Phase 8** | User-facing interactive prototype application | 🔜 Future |
| **Phase 9** | GSoC 2027 proposal preparation | 🔜 Future |

See [`docs/roadmap.md`](docs/roadmap.md) for detailed milestone breakdowns.

---

## Disclaimer

This is an independent open-source research and engineering project. It is **not** officially affiliated with Google, Google Summer of Code, or any specific open-source foundation. Official GSoC 2027 mentoring organisations and requirements will be evaluated as announcements are published.

---

## License

MIT License. See `LICENSE` for details.
