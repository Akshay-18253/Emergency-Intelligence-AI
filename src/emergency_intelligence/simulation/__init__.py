"""
Emergency Intelligence AI — Simulation Subsystem.
=================================================
Discrete-event disaster simulation, virtual clock scheduling, vehicle kinematics,
and dynamic hazard progression.
"""

from emergency_intelligence.simulation.engine import (
    DisasterSimEngine,
    VehicleSimState,
)
from emergency_intelligence.simulation.scenarios import (
    QueuedIncidentState,
    ScenarioDefinition,
    ScenarioResult,
    ScenarioRunner,
    build_cascading_multi_alarm_scenario,
    build_infrastructure_severance_scenario,
    build_progressive_inundation_scenario,
    build_single_incident_baseline_scenario,
    get_benchmark_scenario,
    list_benchmark_scenarios,
)
from emergency_intelligence.simulation.timeline import (
    SimEvent,
    SimEventType,
    SimulationClock,
    SimulationTimeline,
)

__all__ = [
    "DisasterSimEngine",
    "VehicleSimState",
    "SimEvent",
    "SimEventType",
    "SimulationClock",
    "SimulationTimeline",
    "QueuedIncidentState",
    "ScenarioDefinition",
    "ScenarioResult",
    "ScenarioRunner",
    "build_cascading_multi_alarm_scenario",
    "build_infrastructure_severance_scenario",
    "build_progressive_inundation_scenario",
    "build_single_incident_baseline_scenario",
    "get_benchmark_scenario",
    "list_benchmark_scenarios",
]
