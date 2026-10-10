"""
Emergency Fleet Allocation Domain Models.
=========================================
Defines domain abstractions for emergency response units (ambulances, engines,
ladder trucks), physical stations/depots, status state machines, travel time
matrices, network Voronoi catchment partitions, and incident dispatch plans.

Adheres strictly to zero external runtime dependencies (Python standard library only).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import math
from typing import Any, Dict, List, Optional, Set

from emergency_intelligence.events.incidents import ApparatusType


class UnitStatus(Enum):
    """Operational readiness state machine for emergency apparatus."""

    AVAILABLE = "available"
    DISPATCHED = "dispatched"
    EN_ROUTE = "en_route"
    ON_SCENE = "on_scene"
    RETURNING = "returning"
    OUT_OF_SERVICE = "out_of_service"


@dataclass
class EmergencyUnit:
    """An individual emergency apparatus in the municipal response fleet.

    Attributes
    ----------
    unit_id : str
        Unique vehicle identifier (e.g. 'MEDIC-101', 'ENG-402', 'LADDER-1').
    apparatus_type : ApparatusType
        Standardized emergency vehicle taxonomy classification.
    current_node_id : str
        Current topological node position on the road network graph.
    station_id : Optional[str]
        Identifier of the home base station/depot, if assigned.
    status : UnitStatus
        Current operational readiness state.
    speed_factor : float
        Vehicle velocity multiplier relative to standard road speeds.
        (e.g., 1.0 = standard ambulance, 0.85 = heavy 60,000lb ladder truck, 1.15 = fly-car SUV).
    capabilities : Set[str]
        Specialized certification/equipment tags (e.g. {'als', 'cardiac', 'ventilator'}).
    metadata : Dict[str, Any]
        Arbitrary user-defined attributes (call sign, crew size, radio frequency).
    """

    unit_id: str
    apparatus_type: ApparatusType
    current_node_id: str
    station_id: Optional[str] = None
    status: UnitStatus = UnitStatus.AVAILABLE
    speed_factor: float = 1.0
    capabilities: Set[str] = field(default_factory=set)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.unit_id:
            raise ValueError("unit_id cannot be empty.")
        if not self.current_node_id:
            raise ValueError("current_node_id cannot be empty.")
        if self.speed_factor <= 0.0:
            raise ValueError(f"speed_factor must be positive, got {self.speed_factor}")
        if not isinstance(self.apparatus_type, ApparatusType):
            if isinstance(self.apparatus_type, str):
                self.apparatus_type = ApparatusType(self.apparatus_type)
            else:
                raise TypeError(f"Invalid apparatus_type: {self.apparatus_type}")
        if not isinstance(self.status, UnitStatus):
            if isinstance(self.status, str):
                self.status = UnitStatus(self.status)
            else:
                raise TypeError(f"Invalid status: {self.status}")

    def is_available(self) -> bool:
        """Returns True if the apparatus can be immediately assigned to a new call."""
        return self.status == UnitStatus.AVAILABLE

    def update_location(self, node_id: str) -> None:
        """Updates the current graph node position of the unit."""
        if not node_id:
            raise ValueError("node_id cannot be empty.")
        self.current_node_id = str(node_id)

    def set_status(self, new_status: UnitStatus) -> None:
        """Transitions the apparatus to a new operational status."""
        if not isinstance(new_status, UnitStatus):
            new_status = UnitStatus(new_status)
        self.status = new_status

    def to_dict(self) -> Dict[str, Any]:
        """Serializes unit state to a JSON-compatible dictionary."""
        return {
            "unit_id": self.unit_id,
            "apparatus_type": self.apparatus_type.value,
            "current_node_id": self.current_node_id,
            "station_id": self.station_id,
            "status": self.status.value,
            "speed_factor": self.speed_factor,
            "capabilities": sorted(list(self.capabilities)),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> EmergencyUnit:
        """Constructs an EmergencyUnit from a dictionary representation."""
        caps = set(data.get("capabilities", []))
        return cls(
            unit_id=str(data["unit_id"]),
            apparatus_type=ApparatusType(data["apparatus_type"]),
            current_node_id=str(data["current_node_id"]),
            station_id=str(data["station_id"]) if data.get("station_id") is not None else None,
            status=UnitStatus(data.get("status", UnitStatus.AVAILABLE.value)),
            speed_factor=float(data.get("speed_factor", 1.0)),
            capabilities=caps,
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class EmergencyStation:
    """A physical municipal emergency depot, station, or precinct.

    Attributes
    ----------
    station_id : str
        Unique station identifier (e.g. 'STATION-12', 'MEDIC-HQ').
    name : str
        Human-readable facility name (e.g. 'Engine Co. 12 & Rescue').
    node_id : str
        Graph node ID representing station street egress/ingress location.
    station_type : str
        Classification tag (e.g. 'fire_station', 'ems_depot', 'police_precinct').
    assigned_unit_ids : List[str]
        List of apparatus IDs assigned to this facility.
    metadata : Dict[str, Any]
        Optional metadata (jurisdiction, phone number, capacity).
    """

    station_id: str
    name: str
    node_id: str
    station_type: str = "fire_station"
    assigned_unit_ids: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.station_id:
            raise ValueError("station_id cannot be empty.")
        if not self.node_id:
            raise ValueError("node_id cannot be empty.")

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the station to a dictionary."""
        return {
            "station_id": self.station_id,
            "name": self.name,
            "node_id": self.node_id,
            "station_type": self.station_type,
            "assigned_unit_ids": list(self.assigned_unit_ids),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> EmergencyStation:
        """Constructs an EmergencyStation from a dictionary."""
        return cls(
            station_id=str(data["station_id"]),
            name=str(data.get("name", data["station_id"])),
            node_id=str(data["node_id"]),
            station_type=str(data.get("station_type", "fire_station")),
            assigned_unit_ids=list(data.get("assigned_unit_ids", [])),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass
class ETARecord:
    """Estimated Time of Arrival calculation result for an apparatus."""

    unit_id: str
    apparatus_type: ApparatusType
    origin_node_id: str
    destination_node_id: str
    travel_time_seconds: float
    distance_meters: float
    path: List[str]
    reachable: bool

    def to_dict(self) -> Dict[str, Any]:
        """Serializes ETARecord to dictionary."""
        return {
            "unit_id": self.unit_id,
            "apparatus_type": self.apparatus_type.value,
            "origin_node_id": self.origin_node_id,
            "destination_node_id": self.destination_node_id,
            "travel_time_seconds": round(self.travel_time_seconds, 2),
            "distance_meters": round(self.distance_meters, 2),
            "path": list(self.path),
            "reachable": self.reachable,
        }


@dataclass
class CatchmentPartition:
    """Network-topology Voronoi catchment partitioning across multiple depots.

    Attributes
    ----------
    depot_node_ids : List[str]
        List of origin depot node identifiers.
    node_to_depot : Dict[str, str]
        Mapping from each network node ID to its closest serving depot ID.
    node_to_cost : Dict[str, float]
        Travel impedance (seconds) from the closest serving depot to each node.
    depot_catchment_nodes : Dict[str, List[str]]
        Inverse index mapping depot ID -> list of node IDs in its primary catchment basin.
    """

    depot_node_ids: List[str]
    node_to_depot: Dict[str, str]
    node_to_cost: Dict[str, float]
    depot_catchment_nodes: Dict[str, List[str]]

    def get_assigned_depot(self, node_id: str) -> Optional[str]:
        """Returns the identifier of the primary depot serving the given node."""
        return self.node_to_depot.get(str(node_id))

    def get_travel_cost(self, node_id: str) -> float:
        """Returns travel impedance from the assigned depot, or infinity if unreachable."""
        return self.node_to_cost.get(str(node_id), math.inf)

    def get_catchment(self, depot_id: str) -> List[str]:
        """Returns all graph nodes located within the specified depot's catchment basin."""
        return self.depot_catchment_nodes.get(str(depot_id), [])

    def get_isochrone_frontier(self, depot_id: str, max_seconds: float) -> List[str]:
        """Returns all nodes in depot's catchment reachable within max_seconds."""
        depot_nodes = self.get_catchment(depot_id)
        return [
            nid for nid in depot_nodes
            if self.node_to_cost.get(nid, math.inf) <= max_seconds
        ]

    def to_dict(self) -> Dict[str, Any]:
        """Serializes catchment partitioning to dictionary."""
        return {
            "depot_node_ids": list(self.depot_node_ids),
            "node_to_depot": dict(self.node_to_depot),
            "node_to_cost": {k: round(v, 2) for k, v in self.node_to_cost.items()},
            "depot_catchment_nodes": {k: list(v) for k, v in self.depot_catchment_nodes.items()},
        }


@dataclass
class DispatchAssignment:
    """Assignment record matching a specific required apparatus to an incident."""

    incident_id: str
    required_type: ApparatusType
    assigned_unit: Optional[EmergencyUnit]
    eta_record: Optional[ETARecord]
    fulfilled: bool

    def to_dict(self) -> Dict[str, Any]:
        """Serializes assignment to dictionary."""
        return {
            "incident_id": self.incident_id,
            "required_type": self.required_type.value,
            "assigned_unit": self.assigned_unit.to_dict() if self.assigned_unit else None,
            "eta_record": self.eta_record.to_dict() if self.eta_record else None,
            "fulfilled": self.fulfilled,
        }


@dataclass
class DispatchPlan:
    """Comprehensive multi-apparatus dispatch and turn-out plan for an emergency incident."""

    plan_id: str
    incident_id: str
    assignments: List[DispatchAssignment]
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def all_fulfilled(self) -> bool:
        """Returns True if every required apparatus was successfully allocated."""
        return all(a.fulfilled for a in self.assignments)

    @property
    def max_eta_seconds(self) -> float:
        """Returns the latest arrival time among all dispatched apparatuses."""
        etas = [
            a.eta_record.travel_time_seconds
            for a in self.assignments
            if a.fulfilled and a.eta_record and a.eta_record.reachable
        ]
        return max(etas) if etas else 0.0

    @property
    def average_eta_seconds(self) -> float:
        """Returns the average arrival time across all dispatched units."""
        etas = [
            a.eta_record.travel_time_seconds
            for a in self.assignments
            if a.fulfilled and a.eta_record and a.eta_record.reachable
        ]
        return (sum(etas) / len(etas)) if etas else 0.0

    @property
    def unfulfilled_requirements(self) -> List[ApparatusType]:
        """Returns the list of apparatus types that could not be satisfied."""
        return [a.required_type for a in self.assignments if not a.fulfilled]

    def to_dict(self) -> Dict[str, Any]:
        """Serializes dispatch plan to dictionary."""
        return {
            "plan_id": self.plan_id,
            "incident_id": self.incident_id,
            "all_fulfilled": self.all_fulfilled,
            "max_eta_seconds": round(self.max_eta_seconds, 2),
            "average_eta_seconds": round(self.average_eta_seconds, 2),
            "unfulfilled_requirements": [t.value for t in self.unfulfilled_requirements],
            "assignments": [a.to_dict() for a in self.assignments],
            "created_at": self.created_at.isoformat(),
        }
