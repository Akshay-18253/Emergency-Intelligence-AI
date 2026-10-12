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
]
