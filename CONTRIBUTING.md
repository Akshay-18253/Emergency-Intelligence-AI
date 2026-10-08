# Contributing to Emergency Intelligence AI

Thank you for your interest in contributing to **Emergency Intelligence AI**! We welcome contributions from developers, researchers, students, and open-source enthusiasts.

This project is an open-source research and engineering initiative preparing for community participation and prospective alignment with Google Summer of Code (GSoC) 2027.

---

## 1. Core Engineering Principles

Before opening a pull request, please review our foundational design constraints:

1. **Zero External Runtime Dependencies:**  
   The core library (`src/emergency_intelligence`) must run on a clean installation of Python 3.10+ using **only the Python Standard Library** (`math`, `heapq`, `json`, `pathlib`, `typing`, `time`, etc.). No third-party runtime packages (such as `requests`, `numpy`, or `networkx`) may be added to core modules without maintainer consensus.
2. **Strict Architectural Decoupling:**  
   The deterministic routing engine must never depend on or import AI, LLM, or probabilistic reasoning modules. The graph layer must remain mathematically verifiable and independently testable.
3. **Correctness Before Speed:**  
   Algorithmic correctness and edge-case handling take precedence over micro-optimizations. Algorithms must be implemented explicitly and auditably.
4. **Comprehensive Test Coverage:**  
   Any new code must be accompanied by thorough unit tests. Our test suite enforces strict branch coverage (minimum **90%**, currently maintaining **97%**).
5. **Deterministic, Offline Testing:**  
   Unit tests must never perform network requests or depend on unseeded random states. Tests must pass reliably and offline across Windows, macOS, and Linux.

---

## 2. Development Setup

### Prerequisites
- Python 3.10 or higher (Python 3.10, 3.11, 3.12, 3.13, 3.14 supported).
- Git.

### Setting Up a Local Environment

```bash
# 1. Clone the repository
git clone https://github.com/Akshay-18253/Emergency-Intelligence-AI.git
cd Emergency-Intelligence-AI

# 2. Create and activate a virtual environment
# Windows (PowerShell):
python -m venv .venv
.venv\Scripts\Activate.ps1

# Linux / macOS:
python3 -m venv .venv
source .venv/bin/activate

# 3. Install development testing dependencies
pip install pytest pytest-cov
```

---

## 3. Running Tests and Verification

Always run the full test suite and verify code coverage before submitting changes:

```bash
# Run all unit tests with statement and branch coverage
pytest --cov=src -v

# Run a specific test module
pytest tests/test_geojson.py -v

# Run the demonstration examples
python examples/demo.py
python examples/benchmark_demo.py
python examples/osm_demo.py
python examples/geojson_export_demo.py
```

All tests must pass with zero failures and zero warnings.

---

## 4. Coding Standards

- **Formatting & Style:** Adhere strictly to **PEP 8** style conventions. Keep lines readable (preferably under 100 characters).
- **Type Annotations:** All function signatures, method parameters, and return types must be fully typed using standard `typing` annotations (or Python 3.10+ built-in generics with `from __future__ import annotations`).
- **Docstrings:** Provide descriptive docstrings for all public classes, functions, and modules, documenting parameters, return values, and possible exceptions.
- **No Console Logging in Library Code:** Never use `print()` statements inside `src/emergency_intelligence/`. Use returned data objects or structured exceptions. Terminal output is reserved exclusively for scripts in `examples/`.
- **Exception Handling:** Raise specific exceptions (`ValueError`, `KeyError`, `FileNotFoundError`) with clear, diagnostic error messages.

---

## 5. Submitting Changes

1. **Check Existing Issues:** Before starting large architectural work, check the issue tracker or create a new issue to discuss your proposal.
2. **Create a Feature Branch:**
   ```bash
   git checkout -b feature/dynamic-edge-weighting
   # or
   git checkout -b fix/geojson-coordinate-validation
   ```
3. **Commit Guidelines:**
   - Write clear, concise, present-tense commit messages (e.g., `feat(geojson): add coordinate bounds validation`, `fix(osm): handle missing oneway tag`).
   - Keep commits atomic: one logical change per commit.
4. **Pull Request Checklist:**
   - [ ] Does `pytest --cov=src -v` pass with $\ge 90\%$ coverage?
   - [ ] Are all new public functions and classes fully type-annotated?
   - [ ] Has documentation been updated in `docs/` where appropriate?
   - [ ] Does the change avoid introducing external runtime dependencies?

---

## 6. Code of Conduct

We are committed to providing a friendly, safe, and welcoming environment for all contributors regardless of background, gender, identity, race, or experience level. Please maintain professional, constructive, and respectful communication in all issues, pull requests, and discussions.
