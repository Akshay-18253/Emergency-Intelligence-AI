"""
Emergency Apparatus Compatibility Matcher & Dispatch Allocation Engine.
========================================================================
Implements real-time fleet management, apparatus constraint filtering,
multi-criteria candidate ranking, and atomic incident dispatch allocation.

Integrates with `DynamicGraphView` for real-time disaster-aware routing and
adheres strictly to standard library zero-dependency constraints.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from emergency_intelligence.allocation.models import (
    DispatchAssignment,
    DispatchPlan,
    EmergencyStation,
    EmergencyUnit,
    ETARecord,
    UnitStatus,
)
from emergency_intelligence.events.incidents import ApparatusType, Incident
from emergency_intelligence.events.mutations import DynamicGraphView
from emergency_intelligence.graph.astar import astar
from emergency_intelligence.graph.models import Graph


class FleetManager:
    """In-memory municipal emergency response fleet registry and status manager."""

    def __init__(self) -> None:
        self._units: Dict[str, EmergencyUnit] = {}
        self._stations: Dict[str, EmergencyStation] = {}

    def register_station(self, station: EmergencyStation) -> None:
        """Registers a facility depot in the fleet system."""
        if not isinstance(station, EmergencyStation):
            raise TypeError("station must be an instance of EmergencyStation.")
        self._stations[station.station_id] = station

    def register_unit(self, unit: EmergencyUnit) -> None:
        """Registers an emergency apparatus vehicle in the fleet system."""
        if not isinstance(unit, EmergencyUnit):
            raise TypeError("unit must be an instance of EmergencyUnit.")
        self._units[unit.unit_id] = unit
        if unit.station_id and unit.station_id in self._stations:
            station = self._stations[unit.station_id]
            if unit.unit_id not in station.assigned_unit_ids:
                station.assigned_unit_ids.append(unit.unit_id)

    def get_unit(self, unit_id: str) -> Optional[EmergencyUnit]:
        """Retrieves a unit by its identifier."""
        return self._units.get(str(unit_id))

    def get_station(self, station_id: str) -> Optional[EmergencyStation]:
        """Retrieves a station by its identifier."""
        return self._stations.get(str(station_id))

    def list_units(
        self,
        apparatus_type: Optional[ApparatusType] = None,
        status: Optional[UnitStatus] = None,
    ) -> List[EmergencyUnit]:
        """Lists registered units, optionally filtered by type and operational status."""
        results: List[EmergencyUnit] = []
        for unit in self._units.values():
            if apparatus_type is not None and unit.apparatus_type != apparatus_type:
                continue
            if status is not None and unit.status != status:
                continue
            results.append(unit)
        results.sort(key=lambda u: u.unit_id)
        return results

    def get_available_units(
        self,
        apparatus_type: Optional[ApparatusType] = None,
        required_capabilities: Optional[Set[str]] = None,
    ) -> List[EmergencyUnit]:
        """Returns all available units satisfying apparatus and capability constraints."""
        candidates = self.list_units(apparatus_type=apparatus_type, status=UnitStatus.AVAILABLE)
        if not required_capabilities:
            return candidates
        req_set = set(required_capabilities)
        return [c for c in candidates if req_set.issubset(c.capabilities)]

    def dispatch_unit(self, unit_id: str, incident_id: str) -> bool:
        """Marks a unit as DISPATCHED to the given incident."""
        unit = self.get_unit(unit_id)
        if not unit or not unit.is_available():
            return False
        unit.set_status(UnitStatus.DISPATCHED)
        unit.metadata["dispatched_incident_id"] = incident_id
        return True

    def release_unit(self, unit_id: str, new_node_id: Optional[str] = None) -> bool:
        """Releases a unit back to AVAILABLE status, optionally updating location."""
        unit = self.get_unit(unit_id)
        if not unit:
            return False
        unit.set_status(UnitStatus.AVAILABLE)
        unit.metadata.pop("dispatched_incident_id", None)
        if new_node_id:
            unit.update_location(new_node_id)
        return True

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the fleet registry to a dictionary."""
        return {
            "stations": [s.to_dict() for s in self._stations.values()],
            "units": [u.to_dict() for u in self._units.values()],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> FleetManager:
        """Constructs a FleetManager from serialized data."""
        manager = cls()
        for s_data in data.get("stations", []):
            manager.register_station(EmergencyStation.from_dict(s_data))
        for u_data in data.get("units", []):
            manager.register_unit(EmergencyUnit.from_dict(u_data))
        return manager


def rank_units_for_incident(
    graph: Union[Graph, DynamicGraphView],
    target_node_id: str,
    units: List[EmergencyUnit],
) -> List[ETARecord]:
    """Computes routing ETAs from all candidate units to the incident target node.

    Takes into account vehicle `speed_factor` (e.g. heavy ladder trucks encounter higher
    impedance than rapid response fly-cars) and road closures / speed throttles
    configured on `graph` or `DynamicGraphView`.

    Returns
    -------
    List[ETARecord]
        Sorted list of ETA records from fastest arriving unit to slowest.
    """
    records: List[ETARecord] = []

    for unit in units:
        if not graph.has_node(unit.current_node_id):
            records.append(
                ETARecord(
                    unit_id=unit.unit_id,
                    apparatus_type=unit.apparatus_type,
                    origin_node_id=unit.current_node_id,
                    destination_node_id=target_node_id,
                    travel_time_seconds=float("inf"),
                    distance_meters=0.0,
                    path=[],
                    reachable=False,
                )
            )
            continue

        route = astar(
            graph,  # type: ignore[arg-type]
            source=unit.current_node_id,
            destination=target_node_id,
        )

        if not route.reachable or not route.path:
            records.append(
                ETARecord(
                    unit_id=unit.unit_id,
                    apparatus_type=unit.apparatus_type,
                    origin_node_id=unit.current_node_id,
                    destination_node_id=target_node_id,
                    travel_time_seconds=float("inf"),
                    distance_meters=0.0,
                    path=[],
                    reachable=False,
                )
            )
            continue

        # Adjust travel time by apparatus speed factor
        effective_time = route.total_cost / unit.speed_factor

        # Calculate path distance in meters from edge attributes if available
        dist_m = 0.0
        for i in range(len(route.path) - 1):
            u_id, v_id = route.path[i], route.path[i + 1]
            edges = [e for e in graph.get_neighbors(u_id, include_blocked=True) if e.destination_id == v_id]
            if edges:
                dist_m += float(edges[0].attributes.get("distance", edges[0].attributes.get("length_meters", edges[0].cost)))
        if dist_m == 0.0 and route.total_cost > 0.0:
            dist_m = route.total_cost

        records.append(
            ETARecord(
                unit_id=unit.unit_id,
                apparatus_type=unit.apparatus_type,
                origin_node_id=unit.current_node_id,
                destination_node_id=target_node_id,
                travel_time_seconds=effective_time,
                distance_meters=dist_m,
                path=route.path,
                reachable=True,
            )
        )

    # Sort primarily by travel time, tie-break by unit_id for determinism
    records.sort(key=lambda r: (r.travel_time_seconds, r.unit_id))
    return records


def allocate_fleet_for_incident(
    graph: Union[Graph, DynamicGraphView],
    incident: Incident,
    fleet: FleetManager,
    auto_dispatch: bool = False,
) -> DispatchPlan:
    """Matches and allocates the optimal combination of emergency apparatus for an incident.

    Processes every required apparatus in `incident.required_apparatus`. For each requirement:
      1. Filters available units matching the required apparatus type.
      2. Reroutes across dynamic graph conditions to calculate exact turn-out ETAs.
      3. Selects the closest available unit with lowest travel impedance.
      4. Deduplicates units so each apparatus is assigned at most once.

    Parameters
    ----------
    graph : Graph or DynamicGraphView
        The network graph or disaster overlay.
    incident : Incident
        The 911 emergency incident request.
    fleet : FleetManager
        The current active municipal fleet registry.
    auto_dispatch : bool
        If True, marks successfully assigned units as DISPATCHED in the fleet registry.

    Returns
    -------
    DispatchPlan
        Complete dispatch plan containing assignments, ETAs, and status.
    """
    plan_id = f"plan_{uuid.uuid4().hex[:8]}"
    assignments: List[DispatchAssignment] = []

    # If no apparatus explicitly defined, infer default by incident type
    requirements = list(incident.required_apparatus)
    if not requirements:
        requirements = [ApparatusType.AMBULANCE_ALS]

    assigned_unit_ids: Set[str] = set()

    target_node = incident.node_id or str(incident.metadata.get("node_id", ""))
    if not target_node:
        raise ValueError(f"Incident '{incident.incident_id}' must have a valid node_id or metadata['node_id'].")

    for req_type in requirements:
        # Candidate pool: available units of this type not already assigned
        candidates = [
            u for u in fleet.get_available_units(apparatus_type=req_type)
            if u.unit_id not in assigned_unit_ids
        ]

        if not candidates:
            # No available apparatus of this type
            assignments.append(
                DispatchAssignment(
                    incident_id=incident.incident_id,
                    required_type=req_type,
                    assigned_unit=None,
                    eta_record=None,
                    fulfilled=False,
                )
            )
            continue

        ranked_records = rank_units_for_incident(
            graph=graph,
            target_node_id=target_node,
            units=candidates,
        )

        best_record = next((r for r in ranked_records if r.reachable), None)

        if best_record is None:
            # Units exist but are trapped/isolated by road closures or disjoint topology
            assignments.append(
                DispatchAssignment(
                    incident_id=incident.incident_id,
                    required_type=req_type,
                    assigned_unit=None,
                    eta_record=None,
                    fulfilled=False,
                )
            )
            continue

        best_unit = fleet.get_unit(best_record.unit_id)
        assigned_unit_ids.add(best_record.unit_id)

        if auto_dispatch:
            fleet.dispatch_unit(best_record.unit_id, incident.incident_id)

        assignments.append(
            DispatchAssignment(
                incident_id=incident.incident_id,
                required_type=req_type,
                assigned_unit=best_unit,
                eta_record=best_record,
                fulfilled=True,
            )
        )

    return DispatchPlan(
        plan_id=plan_id,
        incident_id=incident.incident_id,
        assignments=assignments,
    )
