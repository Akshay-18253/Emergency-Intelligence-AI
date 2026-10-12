"""
Comparative routing benchmark harness for Emergency Intelligence AI.

Evaluates and benchmarks multiple routing paradigms under dynamic disaster conditions:
1. STATIC:
   Initial shortest-path dispatch without mid-flight awareness. Stalls or is blocked
   if an edge closes ahead.
2. PERIODIC_POLLING:
   Discrete periodic polling (e.g., every delta_t seconds) to detect network updates.
   Suffers from latency lag between event occurrence and detection epoch.
3. REACTIVE_EVENT_DRIVEN:
   Instantaneous, sub-millisecond event-hook replanning upon dynamic graph mutation
   or hazard boundary intersection.

References
----------
- Pelechano, N., & Malkawi, A. (2008). Evacuation simulation models: Challenges in
  representing dynamic routing during sudden-onset structural collapse.
"""

from __future__ import annotations

import copy
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple

from emergency_intelligence.events.incidents import ApparatusType, UrgencyLevel
from emergency_intelligence.events.mutations import DynamicGraphView
from emergency_intelligence.graph.astar import astar
from emergency_intelligence.graph.models import Graph
from emergency_intelligence.simulation.engine import DisasterSimEngine, VehicleSimState
from emergency_intelligence.simulation.scenarios import (
    QueuedIncidentState,
    ScenarioDefinition,
    ScenarioResult,
    ScenarioRunner,
)
from emergency_intelligence.simulation.timeline import SimEvent, SimEventType
from .metrics import (
    compute_detour_delay_degradation,
    compute_path_stability_index,
)


class RoutingStrategy(str, Enum):
    """Routing adaptation strategy under dynamic disaster environments."""

    STATIC = "static"
    PERIODIC_POLLING = "periodic_polling"
    REACTIVE_EVENT_DRIVEN = "reactive_event_driven"


@dataclass
class StrategyBenchmarkResult:
    """Benchmark outcome for a single routing strategy on a disaster scenario.

    Attributes
    ----------
    strategy : RoutingStrategy
        Evaluated routing strategy.
    scenario_name : str
        Name of the evaluated benchmark scenario.
    arrived : bool
        True if responding apparatus successfully reached the target scene.
    travel_time_seconds : float
        Elapsed travel time in seconds (math.inf if vehicle stalled/failed to arrive).
    total_distance_meters : float
        Cumulative physical distance traversed in meters.
    reroute_count : int
        Number of mid-flight replans executed.
    stalled : bool
        True if vehicle was obstructed by a severed road and could not proceed.
    polling_interval_seconds : Optional[float]
        Polling interval if periodic polling was evaluated.
    path_stability_index : float
        Jaccard edge stability index compared to baseline initial planned route.
    detour_delay_factor : float
        Relative delay degradation factor compared to free-flow initial ETA.
    executed_path : List[str]
        Actual node sequence traversed by apparatus.
    """

    strategy: RoutingStrategy
    scenario_name: str
    arrived: bool
    travel_time_seconds: float
    total_distance_meters: float
    reroute_count: int
    stalled: bool = False
    polling_interval_seconds: Optional[float] = None
    path_stability_index: float = 1.0
    detour_delay_factor: float = 0.0
    executed_path: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serializes benchmark result to dictionary."""
        return {
            "strategy": self.strategy.value,
            "scenario_name": self.scenario_name,
            "arrived": self.arrived,
            "travel_time_seconds": (
                round(self.travel_time_seconds, 2)
                if math.isfinite(self.travel_time_seconds)
                else "STALLED"
            ),
            "total_distance_meters": round(self.total_distance_meters, 2),
            "reroute_count": self.reroute_count,
            "stalled": self.stalled,
            "polling_interval_seconds": self.polling_interval_seconds,
            "path_stability_index": round(self.path_stability_index, 4),
            "detour_delay_factor": round(self.detour_delay_factor, 4),
            "executed_path": list(self.executed_path),
        }


@dataclass
class ComparativeBenchmarkSummary:
    """Aggregated comparison across multiple routing paradigms on the same scenario.

    Attributes
    ----------
    scenario_name : str
        Name of the evaluated scenario.
    results : Dict[RoutingStrategy, StrategyBenchmarkResult]
        Outcomes indexed by routing strategy.
    time_savings_vs_static_seconds : Optional[float]
        Travel time reduction achieved by reactive rerouting over static routing.
    time_savings_vs_polling_seconds : Optional[float]
        Travel time reduction achieved by reactive rerouting over periodic polling.
    """

    scenario_name: str
    results: Dict[RoutingStrategy, StrategyBenchmarkResult]
    time_savings_vs_static_seconds: Optional[float] = None
    time_savings_vs_polling_seconds: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serializes comparative benchmark summary."""
        return {
            "scenario_name": self.scenario_name,
            "strategies": {
                strat.value: res.to_dict() for strat, res in self.results.items()
            },
            "time_savings_vs_static_seconds": (
                round(self.time_savings_vs_static_seconds, 2)
                if self.time_savings_vs_static_seconds is not None
                else None
            ),
            "time_savings_vs_polling_seconds": (
                round(self.time_savings_vs_polling_seconds, 2)
                if self.time_savings_vs_polling_seconds is not None
                else None
            ),
        }

    def format_table(self) -> str:
        """Formats an aligned ASCII comparative benchmark table."""
        lines = [
            f"Scenario: {self.scenario_name}",
            "-" * 88,
            f"{'Strategy':<24} {'Arrived':<10} {'Travel Time (s)':<18} {'Distance (m)':<14} {'Reroutes':<10} {'PSI':<8}",
            "-" * 88,
        ]
        for strat, res in self.results.items():
            t_str = f"{res.travel_time_seconds:.1f}" if math.isfinite(res.travel_time_seconds) else "STALLED"
            arr_str = "YES" if res.arrived else "NO"
            lines.append(
                f"{strat.value:<24} {arr_str:<10} {t_str:<18} {res.total_distance_meters:<14.1f} {res.reroute_count:<10} {res.path_stability_index:<8.3f}"
            )
        lines.append("-" * 88)
        if self.time_savings_vs_polling_seconds is not None:
            lines.append(
                f"Reactive Advantage over Polling: {self.time_savings_vs_polling_seconds:.1f}s time saved."
            )
        return "\n".join(lines)


class ComparativeRoutingBenchmark:
    """Executes a declarative scenario across multiple routing strategies.

    Parameters
    ----------
    scenario : ScenarioDefinition
        Base scenario definition containing road network, closures, and incidents.
    polling_interval : float
        Fixed polling interval (seconds) used for the PERIODIC_POLLING strategy (default 15.0s).
    """

    def __init__(
        self,
        scenario: ScenarioDefinition,
        polling_interval: float = 15.0,
    ) -> None:
        self.scenario = scenario
        self.polling_interval = max(1.0, polling_interval)

    def run_strategy(self, strategy: RoutingStrategy) -> StrategyBenchmarkResult:
        """Executes a single routing strategy on the benchmark scenario.

        Parameters
        ----------
        strategy : RoutingStrategy
            The routing adaptation strategy to execute.

        Returns
        -------
        StrategyBenchmarkResult
            Empirical outcome of the strategy.
        """
        # Configure scenario runner with fresh state isolation
        scenario_run = copy.deepcopy(self.scenario)
        runner = ScenarioRunner(scenario_run)

        # Apply strategy-specific engine configurations
        if strategy == RoutingStrategy.STATIC:
            runner.engine.auto_reroute = False
            last_poll_time = -1.0

        elif strategy == RoutingStrategy.PERIODIC_POLLING:
            runner.engine.auto_reroute = False
            last_poll_time = 0.0

        else:  # REACTIVE_EVENT_DRIVEN
            runner.engine.auto_reroute = True
            last_poll_time = -1.0

        # Step-by-step execution to control polling epochs
        clock = runner.engine.clock
        step_sz = self.scenario.step_size

        while clock.current_time < self.scenario.max_simulation_time:
            # Check completion: all incidents resolved or vehicle arrived
            all_resolved = all(s.is_resolved for s in runner.incident_states.values())
            any_en_route = any(v.is_en_route for v in runner.engine.vehicles.values())

            if all_resolved and not any_en_route and runner.engine.timeline.is_empty():
                break

            # Polling strategy trigger
            if strategy == RoutingStrategy.PERIODIC_POLLING:
                if clock.current_time - last_poll_time >= self.polling_interval:
                    runner.engine._check_and_reroute_vehicles()
                    last_poll_time = clock.current_time

            # Step physical engine
            runner.engine.step(step_size=step_sz)

        # Extract primary responding vehicle telemetry
        primary_veh = next(iter(runner.engine.vehicles.values()), None)
        if primary_veh is None:
            return StrategyBenchmarkResult(
                strategy=strategy,
                scenario_name=self.scenario.name,
                arrived=False,
                travel_time_seconds=math.inf,
                total_distance_meters=0.0,
                reroute_count=0,
                stalled=True,
            )

        arrived = primary_veh.arrival_time is not None or primary_veh.is_on_scene
        travel_time = primary_veh.total_travel_time if arrived else math.inf
        stalled = not arrived and primary_veh.is_en_route

        # Calculate initial free-flow path for baseline comparison
        init_path = (
            list(primary_veh.tracker.path)
            if primary_veh.tracker
            else []
        )
        # Note: If vehicle rerouted, tracker.path has updated; we extract initial from incident
        inc_state = next(iter(runner.incident_states.values()), None)
        dest_node = inc_state.incident.node_id if inc_state else None
        station_node = self.scenario.stations[0].node_id if self.scenario.stations else None

        if station_node and dest_node:
            initial_route = astar(self.scenario.graph, station_node, dest_node)
            planned_path = initial_route.path
            initial_cost = initial_route.total_cost
        else:
            planned_path = init_path
            initial_cost = travel_time

        executed_path = (
            primary_veh.tracker.path if primary_veh.tracker else []
        )

        psi = compute_path_stability_index(planned_path, executed_path)
        ddf = (
            compute_detour_delay_degradation(initial_cost, travel_time)
            if math.isfinite(travel_time)
            else 1.0
        )

        return StrategyBenchmarkResult(
            strategy=strategy,
            scenario_name=self.scenario.name,
            arrived=arrived,
            travel_time_seconds=travel_time,
            total_distance_meters=primary_veh.total_distance_meters,
            reroute_count=primary_veh.reroute_count,
            stalled=stalled,
            polling_interval_seconds=(
                self.polling_interval if strategy == RoutingStrategy.PERIODIC_POLLING else None
            ),
            path_stability_index=psi,
            detour_delay_factor=ddf,
            executed_path=list(executed_path),
        )

    def run_all(self) -> ComparativeBenchmarkSummary:
        """Runs all three strategies consecutively and computes comparative advantages."""
        results: Dict[RoutingStrategy, StrategyBenchmarkResult] = {}

        for strat in [
            RoutingStrategy.STATIC,
            RoutingStrategy.PERIODIC_POLLING,
            RoutingStrategy.REACTIVE_EVENT_DRIVEN,
        ]:
            results[strat] = self.run_strategy(strat)

        res_reactive = results[RoutingStrategy.REACTIVE_EVENT_DRIVEN]
        res_static = results[RoutingStrategy.STATIC]
        res_polling = results[RoutingStrategy.PERIODIC_POLLING]

        time_savings_vs_static = None
        if math.isfinite(res_static.travel_time_seconds) and math.isfinite(res_reactive.travel_time_seconds):
            time_savings_vs_static = max(0.0, res_static.travel_time_seconds - res_reactive.travel_time_seconds)

        time_savings_vs_polling = None
        if math.isfinite(res_polling.travel_time_seconds) and math.isfinite(res_reactive.travel_time_seconds):
            time_savings_vs_polling = max(0.0, res_polling.travel_time_seconds - res_reactive.travel_time_seconds)

        return ComparativeBenchmarkSummary(
            scenario_name=self.scenario.name,
            results=results,
            time_savings_vs_static_seconds=time_savings_vs_static,
            time_savings_vs_polling_seconds=time_savings_vs_polling,
        )
