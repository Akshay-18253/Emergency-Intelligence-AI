# Emergency Intelligence AI — Development Guide

> This guide explains how to set up a development environment, run the pre-flight
> verification checker, execute tests, run demonstration scripts, and adhere to
> the engineering conventions of Emergency Intelligence AI.

---

## Requirements

| Requirement | Version |
|---|---|
| Python | 3.10 or later (tested on 3.10, 3.11, 3.12, 3.13, 3.14) |
| pip | 21.0 or later |
| Operating System | Linux, macOS, Windows |

The core library requires **zero external runtime dependencies** (100% Python standard library).

---

## Environment Setup

### 1. Clone the repository

```bash
git clone https://github.com/Akshay-18253/Emergency-Intelligence-AI.git
cd Emergency-Intelligence-AI
```

### 2. Create a virtual environment

```bash
python -m venv .venv
```

### 3. Activate the virtual environment

On Linux / macOS:
```bash
source .venv/bin/activate
```

On Windows (PowerShell):
```powershell
.venv\Scripts\Activate.ps1
```

On Windows (Command Prompt):
```bat
.venv\Scripts\activate.bat
```

### 4. Install development dependencies

```bash
pip install -e ".[dev]"
# Or install testing tools directly:
pip install pytest pytest-cov
```

This installs:
- The `emergency_intelligence` package in editable mode.
- `pytest` and `pytest-cov` for testing.

---

## Verification & Pre-Flight Sanity Checker

Before submitting any commit or pull request, execute the unified developer pre-flight sanity checker:

```bash
python scripts/check.py
```

The checker enforces:
1. **Python version check:** Validates runtime is $\ge 3.10$.
2. **Static AST dependency audit:** Inspects all 30 library modules in `src/emergency_intelligence` to verify strictly zero third-party runtime imports.
3. **Pytest suite with coverage gate:** Executes all 444 unit tests with $\ge 90\%$ branch and statement coverage enforcement.
4. **Demonstration suite:** Executes all 15 example scripts to ensure zero crashes or regressions.

---

## Running Tests Directly

```bash
# Run all unit tests
pytest -v

# Run with statement and branch coverage enforcement (>= 90%)
pytest --cov=emergency_intelligence --cov-report=term-missing -v

# Run a specific test suite
pytest tests/test_audit_and_verification.py -v
```

All tests must pass. A failing test is a blocker — never proceed to new features until all tests are green.

---

## Interactive Demonstration Scripts

The project includes 15 runnable demonstration scripts in `examples/`:

```bash
# Core Graph & Routing Demos
python examples/demo.py
python examples/benchmark_demo.py
python examples/architecture_comparison_demo.py

# OpenStreetMap & Geospatial Demos
python examples/osm_demo.py
python examples/geojson_export_demo.py
python examples/osm_multimodal_demo.py
python examples/topology_contraction_demo.py
python examples/spatial_indexing_demo.py

# Dynamic Conditions & Fleet Demos
python examples/disaster_hazard_demo.py
python examples/dynamic_closure_demo.py
python examples/fleet_allocation_demo.py
python examples/inflight_rerouting_demo.py

# Emergency Intelligence Demos
python examples/natural_language_interpreter_demo.py
python examples/orchestration_pipeline_demo.py
python examples/verification_and_audit_demo.py
```

---

## Project Structure

```
emergency-intelligence-ai/
├── src/
│   └── emergency_intelligence/
│       ├── __init__.py
│       ├── graph/           # Core graph model, Dijkstra, A*, Heuristics, Topology
│       ├── data/            # OSM streaming parser, GeoJSON, Spatial Hash Grid, Cache
│       ├── events/          # Incident models, Hazard polygons, DynamicGraphView, CAP alerts
│       ├── allocation/      # Multi-source Voronoi catchment, Isochrones, FleetManager
│       └── intelligence/    # Domain contracts, Statutory policy, Interpreter, Adapter, Orchestrator
├── tests/                   # 444 unit test cases across 20 test modules
├── examples/                # 15 runnable demonstration scripts
├── scripts/
│   └── check.py             # Pre-flight sanity checker & AST zero-dependency audit
├── docs/                    # System architecture, roadmap, ecosystem studies, reports
├── CONTRIBUTING.md
├── pyproject.toml
└── README.md
```

---

## Coding Conventions

### Python version
Target Python 3.10+. Use `from __future__ import annotations` at the top of every module.

### Type hints
All public functions, methods, and classes must have complete type annotations:
```python
def dijkstra(graph: Graph, source: str, destination: str) -> RouteResult:
```

### Docstrings
All public modules, classes, and functions must have descriptive docstrings explaining parameters, return values, and failure modes.

### Data classes
Use `@dataclass(frozen=True)` for immutable contract objects (`ValidatedIncidentContract`, `OperationalPolicyDirective`, etc.) and mutable dataclasses where state mutation is explicitly managed.

### Error handling
Raise specific, descriptive exceptions with clear messages. Never use bare `except:` clauses.

### Zero-dependency rule
Do not add external packages to `src/emergency_intelligence/`. Use the Python standard library.

---

## Known Boundaries & Limitations

| Dimension | Current State | Notes |
|---|---|---|
| Routing graph | Static OSM extracts or DynamicGraphView overlays | In-memory graphs; does not query commercial live traffic APIs |
| Model provider | `StructuredModelAdapter` with `FakeModelProvider` test doubles | Real foundation model APIs require user-supplied keys and external networking |
| Fleet dispatch | In-memory `FleetManager` | Simulated turnout times and paths; no live physical siren/radio activation |
| Legal status | Open-source research & verification suite | Not certified for live emergency dispatch operations |

---

## Git Workflow

- Commit small, logical, atomic units of work.
- Write conventional commit messages (`feat: ...`, `fix: ...`, `test: ...`, `docs: ...`).
- Run `python scripts/check.py` before committing.
- Do not commit debug prints or temporary files.
