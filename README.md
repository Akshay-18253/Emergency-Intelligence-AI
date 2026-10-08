# Emergency Intelligence AI

> **Milestone 2 status — Informed Search (A*), Spatial Models & Benchmarking**
> The routing engine implements both Dijkstra's algorithm and the A*
> search algorithm with admissible spatial heuristics (Euclidean, Manhattan).
> 100 unit tests passing with 97% code coverage. Zero external runtime dependencies.

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
3. **Dynamic conditions** — event-driven rerouting (closures, congestion, accidents)
4. **Emergency intelligence** — AI reasoning to interpret context and formulate routing objectives
5. **Simulation** — reproducible emergency scenario evaluation
6. **Quantitative evaluation** — measurable benchmarks for routing quality and system performance

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
Candidate Route
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

## Current Capabilities (Milestone 2)

| Capability | Status |
|---|---|
| Road graph model (`Node`, `Edge`, `Graph`) | ✅ Implemented |
| Spatial 2D coordinates on `Node` | ✅ Implemented |
| Dijkstra's shortest-path algorithm (manual `heapq`) | ✅ Implemented |
| Admissible heuristics (Euclidean, Manhattan, Zero) | ✅ Implemented |
| A\* heuristic search algorithm (manual `heapq`) | ✅ Implemented |
| Algorithmic benchmarking & comparative analysis | ✅ Implemented |
| Unit tests (100 passed, 97% code coverage) | ✅ Passing |
| Local demonstrations (Dijkstra + A\* benchmark) | ✅ Working |
| Real road data (OSM integration) | 🔜 Future |
| Dynamic conditions & event processing | 🔜 Future |
| AI reasoning layer (emergency context) | 🔜 Future |
| REST API | 🔜 Future |
| User interface | 🔜 Future |

---

## Project Structure

```
emergency-intelligence-ai/
├── src/
│   └── emergency_intelligence/
│       ├── __init__.py
│       └── graph/
│           ├── __init__.py
│           ├── models.py       # Node (coords), Edge, Graph
│           ├── dijkstra.py     # Dijkstra shortest path
│           ├── astar.py        # A* informed search
│           ├── heuristics.py   # Euclidean, Manhattan, Zero heuristics
│           └── benchmark.py    # Algorithmic comparative benchmark
├── tests/
│   ├── __init__.py
│   ├── test_models.py          # Data model & coordinate tests
│   ├── test_dijkstra.py        # Dijkstra tests (11 cases)
│   ├── test_heuristics.py      # Distance heuristics tests
│   ├── test_astar.py           # A* correctness & efficiency tests
│   └── test_benchmark.py       # Benchmark suite tests
├── examples/
│   ├── demo.py                 # Dijkstra foundation demonstration
│   └── benchmark_demo.py       # A* vs Dijkstra comparative benchmark
├── docs/
│   ├── architecture.md
│   ├── roadmap.md
│   └── development.md
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

# On Windows
.venv\Scripts\activate

# Install the package in editable mode with development dependencies
pip install -e ".[dev]"
```

---

## Running Tests

```bash
python -m pytest tests/ -v
```

With coverage:

```bash
python -m pytest tests/ -v --cov=emergency_intelligence --cov-report=term-missing
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

---

## Roadmap Summary

| Phase | Description | Status |
|---|---|---|
| Phase 1 | Local routing engine foundation | 🔨 **In progress** |
| Phase 2 | Open-source ecosystem participation | 🔜 Future |
| Phase 3 | Real road network data (OSM) | 🔜 Future |
| Phase 4 | Dynamic conditions | 🔜 Future |
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
