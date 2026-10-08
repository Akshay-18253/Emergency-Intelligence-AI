# Emergency Intelligence AI

> **Phase 2 Status — Open-Source Ecosystem Participation & Standards Interoperability**
> Complete Phase 1 foundation + Phase 2 open GIS standards integration:
> OpenStreetMap (OSM) data ingestion, Haversine geographic heuristics, Dijkstra & A* routing,
> RFC 7946 GeoJSON trajectory export, and comprehensive architectural comparative analysis.
> **148 unit tests passing with 98% code coverage.** Zero external runtime dependencies.

---

## Problem

Traditional navigation systems optimise for ordinary objectives:
shortest distance, estimated travel time, typical traffic.

Emergency navigation introduces fundamentally different constraints:

- **Emergency type** — medical, fire, police, hazmat, search and rescue
- **Urgency** — critical, high, moderate
- **Destination requirements** — trauma centre, cardiac unit, nearest fire station
- **Dynamic road conditions** — accidents, closures, congestion, temporary restrictions
- **Risk factors** — flood, debris, fire perimeter, structural damage
- **Vehicle capabilities** — ambulance, fire truck, motorcycle response unit
- **Facility availability** — hospital capacity, unit availability

Existing navigation tools are not designed to reason about these
dimensions simultaneously and transparently.

---

## Motivation

Emergency response time is a critical factor in outcomes.
A system that can intelligently route an emergency vehicle through
a dynamically changing road network — while remaining explainable,
testable, and reproducible — has significant research and practical value.

This project investigates how such a system can be built from
deterministic engineering foundations, with AI reasoning introduced
carefully and only where it genuinely adds value.

---

## Long-Term Vision

The eventual system will combine:

1. **Road-network data** — real graph data from open datasets (e.g. OpenStreetMap)
2. **Graph-based routing** — correct, tested algorithms (Dijkstra, A\*)
3. **Open GIS interoperability** — RFC 7946 GeoJSON for QGIS, Leaflet, and PostGIS
4. **Dynamic conditions** — event-driven rerouting (closures, congestion, accidents)
5. **Emergency intelligence** — AI reasoning to interpret context and formulate routing objectives
6. **Simulation** — reproducible emergency scenario evaluation
7. **Quantitative evaluation** — measurable benchmarks for routing quality and system performance

The architecture separates these concerns deliberately:

```
User / Emergency Input
        │
        ▼
Emergency Intelligence (AI Reasoning Layer)
        │  structured objectives + constraints
        ▼
Dynamic Conditions / Event Processing
        │
        ▼
Routing Engine  (Dijkstra / A*)
        │
        ▼
Road Graph  (OSM / open datasets)
        │
        ▼
Candidate Route  (RFC 7946 GeoJSON Export)
        │
        ▼
Simulation & Evaluation
```

> **Core principle:** AI interprets emergency context and formulates
> routing objectives. Deterministic algorithms compute the route.
> This makes the system explainable, reproducible, and testable.

---

## Engineering Philosophy

This project is developed **brick by brick**.

Each stage establishes a tested foundation for the next.

Priorities (in order):

1. Correctness
2. Simplicity
3. Reproducibility
4. Testing
5. Documentation
6. Modularity
7. Explainability
8. Benchmarking
9. Open-source maintainability
10. Research potential

Things deliberately avoided:

- Hype and inflated capability claims
- Fake AI functionality
- Fabricated benchmarks or research results
- Unnecessary dependencies
- Premature infrastructure
- Giant untested codebases

---

## Current Capabilities (Phase 2 Complete)

| Capability | Status |
|---|---|
| Road graph model (`Node`, `Edge`, `Graph`) | ✅ Implemented |
| Spatial 2D coordinates on `Node` | ✅ Implemented |
| Dijkstra's shortest-path algorithm (manual `heapq`) | ✅ Implemented |
| Admissible heuristics (Euclidean, Manhattan, Zero, Haversine) | ✅ Implemented |
| A\* heuristic search algorithm (manual `heapq` with tie-breaking) | ✅ Implemented |
| Algorithmic benchmarking & comparative analysis | ✅ Implemented |
| Real road data ingestion (OpenStreetMap Overpass parser) | ✅ Implemented |
| Spherical Haversine distance calculations | ✅ Implemented |
| RFC 7946 GeoJSON route & waypoint export (`route_to_geojson`) | ✅ Implemented |
| Open-source ecosystem comparative study ([`docs/ecosystem_study.md`](docs/ecosystem_study.md)) | ✅ Implemented |
| GSoC 2027 alignment & engagement strategy ([`docs/gsoc_strategy.md`](docs/gsoc_strategy.md)) | ✅ Implemented |
| Community contribution guidelines ([`CONTRIBUTING.md`](CONTRIBUTING.md)) | ✅ Implemented |
| Unit tests (148 passed, 98% code coverage, 0 failures) | ✅ Passing |
| Local demonstrations (5 working CLI demonstrations) | ✅ Working |
| Dynamic conditions & event processing | 🔜 Phase 4 |
| AI reasoning layer (emergency context) | 🔜 Phase 5 |
| REST API & UI | 🔜 Phase 7/8 |

---

## Project Structure

```
emergency-intelligence-ai/
├── src/
│   └── emergency_intelligence/
│       ├── __init__.py
│       ├── data/
│       │   ├── __init__.py
│       │   ├── geo.py                     # Haversine distance & heuristic
│       │   ├── geojson.py                 # RFC 7946 GeoJSON export, bbox, & round-trip ingestion
│       │   ├── osm.py                     # OpenStreetMap Overpass parser
│       │   └── sample_hospital_district.json  # Bundled real OSM dataset
│       └── graph/
│           ├── __init__.py
│           ├── models.py                  # Node (coords), Edge, Graph
│           ├── dijkstra.py                # Dijkstra shortest path
│           ├── astar.py                   # A* informed search (100% coverage)
│           ├── heuristics.py              # Euclidean, Manhattan, Zero heuristics (100% coverage)
│           └── benchmark.py               # Comparative benchmark (100% coverage)
├── tests/
│   ├── __init__.py
│   ├── test_models.py                     # Data model & coordinate tests
│   ├── test_dijkstra.py                   # Dijkstra tests (11 cases)
│   ├── test_heuristics.py                 # Distance heuristics tests
│   ├── test_astar.py                      # A* correctness & efficiency tests
│   ├── test_benchmark.py                  # Benchmark suite tests
│   ├── test_geo.py                        # Haversine distance & heuristic tests
│   ├── test_osm.py                        # OpenStreetMap parsing & routing tests
│   └── test_geojson.py                    # RFC 7946 GeoJSON export & round-trip tests
├── examples/
│   ├── demo.py                            # Dijkstra foundation demonstration
│   ├── benchmark_demo.py                  # A* vs Dijkstra comparative benchmark
│   ├── osm_demo.py                        # Real OpenStreetMap routing demonstration
│   ├── geojson_export_demo.py             # RFC 7946 GeoJSON export demonstration
│   └── architecture_comparison_demo.py    # Production routing ecosystem evaluation demo
├── docs/
│   ├── architecture.md                    # System architecture & decision log
│   ├── roadmap.md                         # Phased development roadmap
│   ├── ecosystem_study.md                 # Open-source routing ecosystem comparison
│   ├── gsoc_strategy.md                   # GSoC 2027 alignment & participation strategy
│   └── development.md                     # Engineering practices & setup
├── CONTRIBUTING.md                        # Open-source contributor guide
├── pyproject.toml
├── .gitignore
└── README.md
```

---

## Development Setup

Requires Python 3.10 or later.

```bash
# Create and activate a virtual environment
python -m venv .venv

# On Linux / macOS
source .venv/bin/activate

# On Windows (PowerShell)
.venv\Scripts\Activate.ps1

# Install development testing dependencies
pip install pytest pytest-cov
```

---

## Running Tests

```bash
# Run all unit tests
pytest -v

# Run with test coverage report
pytest --cov=src --cov-report=term-missing -v
```

---

## Running the Demonstrations

### 1. Foundation Dijkstra Demonstration
```bash
python examples/demo.py
```
Constructs a small artificial graph, runs Dijkstra's algorithm across 4 scenarios,
and prints the results to the terminal.

### 2. A* Informed Search & Comparative Benchmark
```bash
python examples/benchmark_demo.py
```
Runs side-by-side comparisons of Dijkstra and A* (Euclidean and Manhattan heuristics)
across emergency corridors and scaled 10x10 and 20x20 grid networks, measuring
optimal cost agreement, search space pruning (up to 90%+), and execution time.

### 3. Real OpenStreetMap (OSM) Emergency Routing
```bash
python examples/osm_demo.py
```
Parses a real-world metropolitan hospital district dataset from OpenStreetMap,
enforces one-way transit street rules, calculates physical distances in meters
using Haversine calculations, and routes an ambulance to a regional trauma center.

### 4. RFC 7946 GeoJSON Export & GIS Interoperability
```bash
python examples/geojson_export_demo.py
```
Computes an ambulance dispatch trajectory on real OSM streets, serializes the route
and intersection waypoints to an RFC 7946 GeoJSON file (`output_emergency_route.geojson`),
and tests round-trip network re-import and re-routing.

### 5. Production Routing Ecosystem & Architecture Evaluation
```bash
python examples/architecture_comparison_demo.py
```
Evaluates production engine paradigms (OSGeo/pgRouting, GraphHopper, Valhalla, OSRM)
against Emergency Intelligence AI, and simulates real-time arterial road blockages
with sub-millisecond ambulance detour recalculation.

---

## Roadmap Summary

| Phase | Description | Status |
|---|---|---|
| Phase 1 | Local routing engine foundation | ✅ **Complete** |
| Phase 2 | Open-source ecosystem participation & standards | ✅ **Complete** |
| Phase 3 | Real road network data pipelines (scaled OSM) | 🔜 Next |
| Phase 4 | Dynamic conditions & event processing | 🔜 Future |
| Phase 5 | Emergency intelligence (AI layer) | 🔜 Future |
| Phase 6 | Simulation and evaluation | 🔜 Future |
| Phase 7 | External data / map integration | 🔜 Future |
| Phase 8 | Prototype application | 🔜 Future |
| Phase 9 | GSoC proposal preparation | 🔜 Future |

See [`docs/roadmap.md`](docs/roadmap.md) for the full roadmap.

---

## Contribution Philosophy

This project values:

- Correctness over speed
- Documentation over cleverness
- Tests over assumptions
- Explainability over performance (at this stage)

Contributions that add real engineering value — tests, documentation
improvements, algorithm correctness fixes — are welcome.

---

## Disclaimer

This is an independent open-source research project.

It is **not** affiliated with Google, Google Summer of Code, or any
specific open-source organisation.

The GSoC 2027 programme has not yet been announced. Appropriate
mentoring organisations and official project requirements will be
determined from official GSoC channels when available.

---

## License

MIT License. See `LICENSE` for details.
