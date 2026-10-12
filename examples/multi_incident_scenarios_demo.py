"""
Milestone 6.2 Demonstration: Multi-Incident Disaster Scenarios & Resource Contention.
=====================================================================================
Demonstrates:
  1. Standard benchmark disaster scenarios:
     - Scenario 1: Single Incident Baseline
     - Scenario 2: Cascading Urban Multi-Alarm & Municipal Fleet Exhaustion
     - Scenario 3: Mid-Flight Critical Infrastructure Severance
     - Scenario 4: Progressive Dynamic Flood Inundation
  2. Multi-tier priority holding queue when all municipal apparatus are committed.
  3. Secondary station cross-catchment dispatch and post-mission field redeployment.
  4. Empirical comparison table of response times, queue delays, and wall-clock latencies.
"""

from __future__ import annotations

import time

from emergency_intelligence.simulation.scenarios import (
    ScenarioRunner,
    get_benchmark_scenario,
    list_benchmark_scenarios,
)


def main() -> None:
    print("=" * 80)
    print("  Milestone 6.2: Multi-Incident Scenarios & Resource Contention Demonstration")
    print("=" * 80)

    scenario_names = list_benchmark_scenarios()
    print(f"\nRegistered Disaster Benchmark Scenarios ({len(scenario_names)}):")
    for idx, name in enumerate(scenario_names, start=1):
        scen = get_benchmark_scenario(name)
        print(f"  [{idx}] {scen.name:36s} | {scen.description}")

    results = []

    print("\n" + "-" * 80)
    print("Executing Benchmark Scenarios...")
    print("-" * 80)

    for name in scenario_names:
        scen = get_benchmark_scenario(name)
        print(f"\n>> Running: {scen.name}...")

        runner = ScenarioRunner(scen)
        res = runner.run()
        results.append(res)

        print(f"   Simulated Duration : {res.simulated_duration:.1f} s")
        print(f"   Wall-Clock Runtime : {res.wall_clock_ms:.2f} ms")
        print(f"   Incidents Serviced : {res.incidents_serviced}/{res.total_incidents}")
        print(f"   Apparatus Dispatched: {res.units_dispatched_count} units")
        print(f"   Queued Incidents   : {res.incidents_queued_count}")
        if res.incidents_queued_count > 0:
            print(f"   Average Queue Delay: {res.average_queue_delay_seconds:.2f} s (Max: {res.max_queue_delay_seconds:.2f} s)")
        print(f"   Avg Response Time  : {res.average_response_time:.2f} s")
        print(f"   Dynamic In-Flight Reroutes: {res.total_reroutes}")

    # Summary Comparison Table
    print("\n" + "=" * 80)
    print("  EMPIRICAL BENCHMARK COMPARISON TABLE")
    print("=" * 80)
    header = f"{'Scenario Name':32s} | {'Calls':5s} | {'Srvd':4s} | {'Q Delay':7s} | {'Avg Resp':8s} | {'Reroutes':8s} | {'Wall ms':7s}"
    print(header)
    print("-" * 80)

    for r in results:
        q_str = f"{r.average_queue_delay_seconds:5.1f}s" if r.incidents_queued_count > 0 else "  0.0s"
        row = (
            f"{r.scenario_name:32s} | "
            f"{r.total_incidents:5d} | "
            f"{r.incidents_serviced:4d} | "
            f"{q_str:7s} | "
            f"{r.average_response_time:6.1f}s | "
            f"{r.total_reroutes:8d} | "
            f"{r.wall_clock_ms:6.2f}ms"
        )
        print(row)

    print("=" * 80)

    # Validate essential criteria
    for r in results:
        assert r.incidents_serviced >= 1, f"Scenario {r.scenario_name} had zero serviced incidents."
    assert any(r.total_reroutes > 0 for r in results), "Severance scenario must produce in-flight reroutes."
    assert any(r.incidents_queued_count > 0 for r in results), "Cascading scenario must encounter resource queuing."

    print("\n[VERIFIED] Milestone 6.2 Multi-Incident Disaster Scenarios executed flawlessly!")


if __name__ == "__main__":
    main()
