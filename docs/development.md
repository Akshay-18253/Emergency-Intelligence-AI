# Development Guide

> This guide explains how to set up a development environment, run tests,
> run the demonstration, and understand the coding conventions used in
> Emergency Intelligence AI.

---

## Requirements

| Requirement | Version |
|---|---|
| Python | 3.10 or later |
| pip | 21.0 or later |
| Operating System | Linux, macOS, Windows |

No external system libraries are required for Day 1.

---

## Environment Setup

### 1. Clone the repository

```bash
git clone <repository-url>
cd emergency-intelligence-ai
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

### 4. Install the package in editable mode

```bash
pip install -e ".[dev]"
```

This installs:
- The `emergency_intelligence` package in editable mode (source is live-linked).
- `pytest` and `pytest-cov` for testing.

No other dependencies are installed on Day 1.

### 5. Verify the installation

```bash
python -c "import emergency_intelligence; print(emergency_intelligence.__version__)"
```

Expected output:
```
0.1.0
```

---

## Running Tests

```bash
python -m pytest tests/ -v
```

With coverage report:

```bash
python -m pytest tests/ -v --cov=emergency_intelligence --cov-report=term-missing
```

All tests should pass. A failing test is a blocker — do not proceed to
new features until all tests are green.

---

## Running the Demonstration

```bash
python examples/demo.py
```

The demonstration constructs an artificial road graph and runs Dijkstra's
algorithm across four scenarios:

1. A → D (two paths exist; algorithm selects the lower-cost one)
2. B → D (direct single-hop path)
3. A → A (source equals destination; cost = 0)
4. D → A (no path exists; destination is unreachable)

No graphical interface. No external API calls. Output is printed to the terminal.

---

## Project Structure

```
emergency-intelligence-ai/
├── src/
│   └── emergency_intelligence/      # Main Python package
│       ├── __init__.py
│       └── graph/
│           ├── __init__.py
│           ├── models.py            # Node, Edge, Graph
│           └── dijkstra.py          # Dijkstra's algorithm + RouteResult
├── tests/
│   ├── __init__.py
│   ├── test_models.py               # Tests for Node, Edge, Graph
│   └── test_dijkstra.py             # Tests for Dijkstra (11 cases)
├── examples/
│   └── demo.py                      # Minimal demonstration script
├── docs/
│   ├── architecture.md
│   ├── roadmap.md
│   └── development.md               # This file
├── pyproject.toml                   # Package configuration
├── .gitignore
└── README.md
```

---

## Coding Conventions

### Python version

Target Python 3.10+. Use `from __future__ import annotations` for
forward-reference support where needed.

### Type hints

All public functions and methods must have type hints on parameters
and return values.

```python
def dijkstra(graph: Graph, source: str, destination: str) -> RouteResult:
```

### Docstrings

All public modules, classes, and functions must have docstrings.

Use NumPy-style docstrings with `Parameters`, `Returns`, `Raises`,
and `Notes` sections where appropriate.

### Data classes

Use `@dataclass` for simple data-holding objects (e.g. `Node`, `Edge`,
`RouteResult`). Use `__post_init__` for validation.

### Error handling

Raise specific, descriptive exceptions with clear messages.

```python
raise KeyError(f"Source node {source!r} does not exist in the graph.")
```

Do not use bare `except:` clauses.

### Naming

- Modules: `snake_case`
- Classes: `PascalCase`
- Functions and variables: `snake_case`
- Constants: `UPPER_SNAKE_CASE`

### Imports

Standard library imports first, then third-party, then local.
Use absolute imports within the package.

### No premature optimisation

Readability and correctness take priority. Optimise only when a
performance problem is demonstrated by measurement.

---

## Current Limitations

| Limitation | Notes |
|---|---|
| Artificial graph only | No real road data (OSM, etc.) — planned Phase 3 |
| Dijkstra only | A\* not yet implemented — planned next in Phase 1 |
| No dynamic conditions | Static graph only — planned Phase 4 |
| No AI layer | Deterministic only — planned Phase 5 |
| No API or UI | Library only — planned Phases 7–8 |
| No node coordinates | Needed for A\* heuristic and map visualisation |
| No parallelism | Single-threaded — not required at this scale |
| In-memory only | No persistence layer |

These are intentional limitations of Day 1, not engineering oversights.

---

## Dependency Policy

Day 1 runtime dependencies: **none**.

Day 1 development dependencies: `pytest`, `pytest-cov`.

Before adding any new dependency, ask:

1. Is it essential for correctness or safety?
2. Can it be replaced by the Python standard library?
3. Is it actively maintained and appropriately licensed?
4. Does its addition simplify the code in a measurable way?

If the answer to (1) or (2) is no, do not add the dependency.

---

## Git Workflow

- Commit small, logical units of work.
- Write clear commit messages that explain *why*, not just *what*.
- Tests must pass before committing.
- Do not commit commented-out code or debug prints.
