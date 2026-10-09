"""
Developer Pre-Flight Sanity Checker for Emergency Intelligence AI.

Runs a fast, comprehensive quality check prior to git commits and pull requests:
  1. Python version compliance check (>= 3.10).
  2. Static AST dependency audit: strictly verifies ZERO external runtime imports
     in core library code (standard library only).
  3. Executes the full test suite with coverage enforcement (>= 90%).
  4. Executes all 5 demonstration scripts to verify zero crashes.

Usage:
    python scripts/check.py
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
import time
from pathlib import Path

# Colors for terminal output
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"


def print_step(title: str) -> None:
    print(f"\n{BLUE}==>{RESET} {title}...")


def print_success(msg: str) -> None:
    print(f"  {GREEN}[PASS]{RESET} {msg}")


def print_fail(msg: str) -> None:
    print(f"  {RED}[FAIL]{RESET} {msg}")


def step_python_version() -> bool:
    print_step("Step 1: Checking Python runtime version")
    major, minor = sys.version_info[:2]
    if (major, minor) < (3, 10):
        print_fail(f"Python 3.10+ required. Current version is {major}.{minor}.")
        return False
    print_success(f"Python version {major}.{minor}.{sys.version_info[2]} satisfies >= 3.10 requirement.")
    return True


def step_static_import_audit(root_dir: Path) -> bool:
    print_step("Step 2: Static AST import audit (Zero Runtime Dependencies Rule)")
    src_dir = root_dir / "src" / "emergency_intelligence"
    if not src_dir.is_dir():
        print_fail(f"Source directory not found: {src_dir}")
        return False

    stdlib_modules = getattr(sys, "stdlib_module_names", set())

    violations = []
    py_files = list(src_dir.rglob("*.py"))

    for py_file in py_files:
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        except Exception as err:
            violations.append(f"{py_file.name}: syntax error: {err}")
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top_pkg = alias.name.split(".")[0]
                    if top_pkg != "emergency_intelligence" and top_pkg not in stdlib_modules:
                        violations.append(f"{py_file.relative_to(root_dir)} imports external package '{top_pkg}'")
            elif isinstance(node, ast.ImportFrom):
                if node.level == 0 and node.module:
                    top_pkg = node.module.split(".")[0]
                    if top_pkg != "emergency_intelligence" and top_pkg not in stdlib_modules:
                        violations.append(f"{py_file.relative_to(root_dir)} imports from external package '{top_pkg}'")

    if violations:
        for v in violations:
            print_fail(v)
        return False

    print_success(f"Audited {len(py_files)} library modules: zero external dependencies detected.")
    return True


def step_run_tests(root_dir: Path) -> bool:
    print_step("Step 3: Running pytest suite with branch coverage enforcement")
    cmd = [sys.executable, "-m", "pytest", "-q", "--cov=emergency_intelligence", "--cov-fail-under=90"]
    result = subprocess.run(cmd, cwd=root_dir)
    if result.returncode != 0:
        print_fail("Pytest suite failed or coverage was below required threshold.")
        return False
    print_success("All unit tests passed with >= 90% branch coverage.")
    return True


def step_run_demos(root_dir: Path) -> bool:
    print_step("Step 4: Executing all demonstration scripts")
    demos = [
        "examples/demo.py",
        "examples/benchmark_demo.py",
        "examples/osm_demo.py",
        "examples/geojson_export_demo.py",
        "examples/architecture_comparison_demo.py",
        "examples/osm_multimodal_demo.py",
        "examples/topology_contraction_demo.py",
        "examples/spatial_indexing_demo.py",
    ]

    for demo in demos:
        demo_path = root_dir / demo
        if not demo_path.is_file():
            print_fail(f"Demonstration script missing: {demo}")
            return False

        t0 = time.perf_counter()
        res = subprocess.run([sys.executable, str(demo_path)], cwd=root_dir, capture_output=True, text=True)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        if res.returncode != 0:
            print_fail(f"{demo} failed with exit code {res.returncode}:")
            print(res.stderr)
            return False

        print_success(f"{demo} passed successfully in {elapsed_ms:.1f} ms.")

    return True


def main() -> None:
    print("=" * 72)
    print("  Emergency Intelligence AI — Developer Pre-Flight Sanity Check")
    print("=" * 72)

    root_dir = Path(__file__).resolve().parent.parent

    start_all = time.perf_counter()

    if not step_python_version():
        sys.exit(1)

    if not step_static_import_audit(root_dir):
        sys.exit(1)

    if not step_run_tests(root_dir):
        sys.exit(1)

    if not step_run_demos(root_dir):
        sys.exit(1)

    total_time = time.perf_counter() - start_all
    print("\n" + "=" * 72)
    print(f"  {GREEN}ALL CHECKS PASSED{RESET} in {total_time:.2f} seconds.")
    print("  Codebase is clean, tested, zero-dependency, and ready for commit/PR!")
    print("=" * 72 + "\n")


if __name__ == "__main__":
    main()
