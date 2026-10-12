"""
Evaluation metrics for emergency response systems.

Provides standardized quantitative evaluations including:
1. NFPA 1710 Statutory Response Compliance Analysis:
   - First-Arriving Engine Travel Time (<= 240 seconds for >= 90% of incidents).
   - Initial Full Alarm Assignment Travel Time (<= 480 seconds for >= 90% of incidents).
   - Turnout Time (<= 60 seconds for EMS, <= 80 seconds for Fire).
2. Path Stability Index (PSI):
   - Measures route consistency and churn between initial planned trajectories
     and executed trajectories under dynamic rerouting.
3. Detour Delay Degradation Factor (DDF):
   - Quantifies the relative excess travel time incurred due to dynamic in-flight
     road network closures.

References
----------
- NFPA 1710: Standard for the Organization and Deployment of Fire Suppression
  Operations, Emergency Medical Operations, and Special Operations to the
  Public by Career Fire Departments (2020 Edition).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple


# ---------------------------------------------------------------------------
# Percentile Helper (Pure Python Standard Library)
# ---------------------------------------------------------------------------


def compute_percentile(data: Sequence[float], percentile: float) -> float:
    """Computes the p-th percentile of a dataset using linear interpolation.

    Parameters
    ----------
    data : Sequence[float]
        Numeric samples.
    percentile : float
        Percentile rank in range [0.0, 100.0].

    Returns
    -------
    float
        The interpolated percentile value, or 0.0 if data is empty.
    """
    if not data:
        return 0.0
    if len(data) == 1:
        return float(data[0])

    sorted_data = sorted(data)
    n = len(sorted_data)
    rank = (percentile / 100.0) * (n - 1)
    lower_idx = int(math.floor(rank))
    upper_idx = int(math.ceil(rank))

    if lower_idx == upper_idx:
        return float(sorted_data[lower_idx])

    weight = rank - lower_idx
    return float(sorted_data[lower_idx] * (1.0 - weight) + sorted_data[upper_idx] * weight)


# ---------------------------------------------------------------------------
# Incident Response Records
# ---------------------------------------------------------------------------


@dataclass
class IncidentResponseRecord:
    """Standardized record of operational timing milestones for an incident.

    Attributes
    ----------
    incident_id : str
        Unique incident identifier.
    emergency_type : str
        Category of emergency (e.g. 'structure_fire', 'cardiac_arrest').
    urgency : str
        Operational urgency level (e.g. 'critical', 'high', 'medium', 'low').
    report_time : float
        Timestamp (simulated seconds) when the incident was reported to CAD.
    first_dispatch_time : Optional[float]
        Timestamp when the first emergency apparatus was dispatched.
    first_arrival_time : Optional[float]
        Timestamp when the first apparatus arrived on scene (initial shock unit).
    all_arrival_time : Optional[float]
        Timestamp when all required units arrived (initial full alarm assignment).
    cleared_time : Optional[float]
        Timestamp when operations concluded and apparatus cleared scene.
    queue_delay_seconds : float
        Duration the incident spent pending in dispatch queue before assignment.
    assigned_units : List[str]
        Identifiers of apparatus dispatched to the incident.
    """

    incident_id: str
    emergency_type: str = "general"
    urgency: str = "high"
    report_time: float = 0.0
    first_dispatch_time: Optional[float] = None
    first_arrival_time: Optional[float] = None
    all_arrival_time: Optional[float] = None
    cleared_time: Optional[float] = None
    queue_delay_seconds: float = 0.0
    assigned_units: List[str] = field(default_factory=list)

    @property
    def turnout_time_seconds(self) -> Optional[float]:
        """Turnout time: elapsed duration between call receipt and unit dispatch."""
        if self.first_dispatch_time is not None and self.first_dispatch_time >= self.report_time:
            return self.first_dispatch_time - self.report_time
        return None

    @property
    def first_travel_time_seconds(self) -> Optional[float]:
        """Travel time for first-arriving unit: dispatch to first arrival on scene."""
        if (
            self.first_arrival_time is not None
            and self.first_dispatch_time is not None
            and self.first_arrival_time >= self.first_dispatch_time
        ):
            return self.first_arrival_time - self.first_dispatch_time
        return None

    @property
    def first_total_response_time_seconds(self) -> Optional[float]:
        """Total response time: call receipt to first on-scene arrival."""
        if self.first_arrival_time is not None and self.first_arrival_time >= self.report_time:
            return self.first_arrival_time - self.report_time
        return None

    @property
    def full_alarm_travel_time_seconds(self) -> Optional[float]:
        """Travel time for full alarm assignment: dispatch to all-units arrival."""
        if (
            self.all_arrival_time is not None
            and self.first_dispatch_time is not None
            and self.all_arrival_time >= self.first_dispatch_time
        ):
            return self.all_arrival_time - self.first_dispatch_time
        return None

    @property
    def full_alarm_total_response_time_seconds(self) -> Optional[float]:
        """Total response time for full alarm: call receipt to all-units arrival."""
        if self.all_arrival_time is not None and self.all_arrival_time >= self.report_time:
            return self.all_arrival_time - self.report_time
        return None


# ---------------------------------------------------------------------------
# NFPA 1710 Compliance Metrics
# ---------------------------------------------------------------------------


@dataclass
class NFPA1710Metrics:
    """Quantitative compliance evaluation against NFPA 1710 statutory standards.

    Attributes
    ----------
    total_incidents : int
        Total number of incidents evaluated.
    serviced_incidents : int
        Number of incidents that achieved at least one on-scene arrival.
    first_arrival_threshold_seconds : float
        Statutory threshold for first-arriving engine travel time (default 240.0s / 4 min).
    full_alarm_threshold_seconds : float
        Statutory threshold for full alarm travel time (default 480.0s / 8 min).
    target_compliance_ratio : float
        Statutory compliance requirement target (default 0.90 / 90%).
    first_arrival_compliant_count : int
        Number of incidents satisfying first-arrival threshold.
    first_arrival_compliance_rate : float
        Proportion of serviced incidents satisfying first-arrival threshold [0.0, 1.0].
    full_alarm_compliant_count : int
        Number of incidents satisfying full alarm arrival threshold.
    full_alarm_compliance_rate : float
        Proportion of serviced incidents satisfying full alarm threshold [0.0, 1.0].
    is_first_arrival_compliant : bool
        True if first_arrival_compliance_rate >= target_compliance_ratio.
    is_full_alarm_compliant : bool
        True if full_alarm_compliance_rate >= target_compliance_ratio.
    is_overall_compliant : bool
        True if all evaluated thresholds meet or exceed statutory 90% benchmark.
    mean_first_travel_time : float
        Mean travel time in seconds for first arrivals.
    median_first_travel_time : float
        50th percentile (median) travel time in seconds for first arrivals.
    p90_first_travel_time : float
        90th percentile travel time in seconds (statutory evaluation benchmark).
    p95_first_travel_time : float
        95th percentile travel time in seconds.
    max_first_travel_time : float
        Maximum travel time in seconds observed.
    mean_queue_delay : float
        Average queue holding delay in seconds before dispatch.
    max_queue_delay : float
        Maximum queue delay in seconds.
    """

    total_incidents: int
    serviced_incidents: int
    first_arrival_threshold_seconds: float = 240.0
    full_alarm_threshold_seconds: float = 480.0
    target_compliance_ratio: float = 0.90
    first_arrival_compliant_count: int = 0
    first_arrival_compliance_rate: float = 0.0
    full_alarm_compliant_count: int = 0
    full_alarm_compliance_rate: float = 0.0
    is_first_arrival_compliant: bool = False
    is_full_alarm_compliant: bool = False
    is_overall_compliant: bool = False
    mean_first_travel_time: float = 0.0
    median_first_travel_time: float = 0.0
    p90_first_travel_time: float = 0.0
    p95_first_travel_time: float = 0.0
    max_first_travel_time: float = 0.0
    mean_queue_delay: float = 0.0
    max_queue_delay: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Serializes compliance metrics to dictionary."""
        return {
            "total_incidents": self.total_incidents,
            "serviced_incidents": self.serviced_incidents,
            "first_arrival_threshold_seconds": self.first_arrival_threshold_seconds,
            "full_alarm_threshold_seconds": self.full_alarm_threshold_seconds,
            "target_compliance_ratio": self.target_compliance_ratio,
            "first_arrival_compliant_count": self.first_arrival_compliant_count,
            "first_arrival_compliance_rate": round(self.first_arrival_compliance_rate, 4),
            "full_alarm_compliant_count": self.full_alarm_compliant_count,
            "full_alarm_compliance_rate": round(self.full_alarm_compliance_rate, 4),
            "is_first_arrival_compliant": self.is_first_arrival_compliant,
            "is_full_alarm_compliant": self.is_full_alarm_compliant,
            "is_overall_compliant": self.is_overall_compliant,
            "mean_first_travel_time": round(self.mean_first_travel_time, 2),
            "median_first_travel_time": round(self.median_first_travel_time, 2),
            "p90_first_travel_time": round(self.p90_first_travel_time, 2),
            "p95_first_travel_time": round(self.p95_first_travel_time, 2),
            "max_first_travel_time": round(self.max_first_travel_time, 2),
            "mean_queue_delay": round(self.mean_queue_delay, 2),
            "max_queue_delay": round(self.max_queue_delay, 2),
        }


def evaluate_nfpa1710_compliance(
    records: Sequence[IncidentResponseRecord],
    first_arrival_threshold: float = 240.0,
    full_alarm_threshold: float = 480.0,
    target_ratio: float = 0.90,
    use_total_response_time: bool = False,
) -> NFPA1710Metrics:
    """Evaluates a batch of response records against NFPA 1710 benchmarks.

    Parameters
    ----------
    records : Sequence[IncidentResponseRecord]
        List of incident response timing records.
    first_arrival_threshold : float
        Statutory threshold in seconds for first arrival (default 240.0s).
    full_alarm_threshold : float
        Statutory threshold in seconds for full alarm assignment (default 480.0s).
    target_ratio : float
        Required statutory compliance ratio (default 0.90 / 90%).
    use_total_response_time : bool
        If True, measures from report_time (call receipt).
        If False (default), measures statutory travel time (dispatch to arrival).

    Returns
    -------
    NFPA1710Metrics
        Comprehensive evaluation results.
    """
    total = len(records)
    if total == 0:
        return NFPA1710Metrics(
            total_incidents=0,
            serviced_incidents=0,
            first_arrival_threshold_seconds=first_arrival_threshold,
            full_alarm_threshold_seconds=full_alarm_threshold,
            target_compliance_ratio=target_ratio,
        )

    # Collect first-arrival times
    first_times: List[float] = []
    full_times: List[float] = []
    queue_delays: List[float] = []

    for r in records:
        queue_delays.append(r.queue_delay_seconds)

        t_first = (
            r.first_total_response_time_seconds
            if use_total_response_time
            else r.first_travel_time_seconds
        )
        if t_first is not None:
            first_times.append(t_first)

        t_full = (
            r.full_alarm_total_response_time_seconds
            if use_total_response_time
            else r.full_alarm_travel_time_seconds
        )
        if t_full is not None:
            full_times.append(t_full)

    serviced = len(first_times)
    first_compliant = sum(1 for t in first_times if t <= first_arrival_threshold)
    first_rate = (first_compliant / serviced) if serviced > 0 else 0.0

    full_serviced = len(full_times)
    full_compliant = sum(1 for t in full_times if t <= full_alarm_threshold)
    full_rate = (full_compliant / full_serviced) if full_serviced > 0 else (
        1.0 if serviced == 0 else 0.0
    )

    is_first_comp = (first_rate >= target_ratio) if serviced > 0 else False
    is_full_comp = (full_rate >= target_ratio) if full_serviced > 0 else is_first_comp
    is_overall = is_first_comp and is_full_comp

    mean_first = (sum(first_times) / serviced) if serviced > 0 else 0.0
    median_first = compute_percentile(first_times, 50.0) if serviced > 0 else 0.0
    p90_first = compute_percentile(first_times, 90.0) if serviced > 0 else 0.0
    p95_first = compute_percentile(first_times, 95.0) if serviced > 0 else 0.0
    max_first = max(first_times) if serviced > 0 else 0.0

    mean_q = (sum(queue_delays) / total) if total > 0 else 0.0
    max_q = max(queue_delays) if queue_delays else 0.0

    return NFPA1710Metrics(
        total_incidents=total,
        serviced_incidents=serviced,
        first_arrival_threshold_seconds=first_arrival_threshold,
        full_alarm_threshold_seconds=full_alarm_threshold,
        target_compliance_ratio=target_ratio,
        first_arrival_compliant_count=first_compliant,
        first_arrival_compliance_rate=first_rate,
        full_alarm_compliant_count=full_compliant,
        full_alarm_compliance_rate=full_rate,
        is_first_arrival_compliant=is_first_comp,
        is_full_alarm_compliant=is_full_comp,
        is_overall_compliant=is_overall,
        mean_first_travel_time=mean_first,
        median_first_travel_time=median_first,
        p90_first_travel_time=p90_first,
        p95_first_travel_time=p95_first,
        max_first_travel_time=max_first,
        mean_queue_delay=mean_q,
        max_queue_delay=max_q,
    )


def records_from_dicts(records: Sequence[Dict[str, Any]]) -> List[IncidentResponseRecord]:
    """Converts a sequence of dictionaries into IncidentResponseRecord objects.

    Convenient for processing raw telemetry exported from ScenarioResult.
    """
    res: List[IncidentResponseRecord] = []
    for d in records:
        res.append(
            IncidentResponseRecord(
                incident_id=str(d.get("incident_id", "")),
                emergency_type=str(d.get("emergency_type", "general")),
                urgency=str(d.get("urgency", "high")),
                report_time=float(d.get("report_time", 0.0)),
                first_dispatch_time=d.get("first_dispatch_time"),
                first_arrival_time=d.get("first_arrival_time"),
                all_arrival_time=d.get("all_arrival_time"),
                cleared_time=d.get("cleared_time"),
                queue_delay_seconds=float(d.get("queue_delay_seconds", 0.0)),
                assigned_units=list(d.get("assigned_units", [])),
            )
        )
    return res


# ---------------------------------------------------------------------------
# Path Stability Index (PSI) & Detour Degradation (DDF)
# ---------------------------------------------------------------------------


def _extract_directed_edges(path: Sequence[str]) -> List[Tuple[str, str]]:
    """Converts a sequence of node IDs into directed edge pairs (u, v)."""
    if len(path) < 2:
        return []
    return [(path[i], path[i + 1]) for i in range(len(path) - 1)]


def compute_path_stability_index(
    planned_path: Sequence[str],
    executed_path: Sequence[str],
) -> float:
    """Computes the Path Stability Index (PSI) between planned and executed paths.

    The Path Stability Index measures route consistency and absence of route flapping.
    Defined as the Jaccard similarity of directed edge sets:

    .. math::
        PSI = \\frac{|E_{\\text{planned}} \\cap E_{\\text{executed}}|}{|E_{\\text{planned}} \\cup E_{\\text{executed}}|}

    Parameters
    ----------
    planned_path : Sequence[str]
        Ordered sequence of node IDs in the initial baseline route.
    executed_path : Sequence[str]
        Ordered sequence of node IDs in the actual route executed.

    Returns
    -------
    float
        Stability index in range [0.0, 1.0].
        1.0 indicates identical routes (zero churn/deviation).
        0.0 indicates completely disjoint routes.
    """
    # Edge case: single-node paths
    if len(planned_path) <= 1 and len(executed_path) <= 1:
        if planned_path == executed_path:
            return 1.0
        return 0.0

    edges_planned = set(_extract_directed_edges(planned_path))
    edges_executed = set(_extract_directed_edges(executed_path))

    if not edges_planned and not edges_executed:
        return 1.0
    if not edges_planned or not edges_executed:
        return 0.0

    intersection = edges_planned.intersection(edges_executed)
    union = edges_planned.union(edges_executed)

    return len(intersection) / len(union)


def compute_detour_delay_degradation(
    initial_travel_time: float,
    actual_travel_time: float,
) -> float:
    """Computes the Detour Delay Degradation Factor (DDF).

    Quantifies the relative excess travel time incurred due to dynamic
    in-flight closures or rerouting:

    .. math::
        DDF = \\max\\left(0, \\frac{T_{\\text{actual}} - T_{\\text{initial}}}{T_{\\text{initial}}}\\right)

    Parameters
    ----------
    initial_travel_time : float
        Optimal free-flow travel time (seconds) planned at dispatch.
    actual_travel_time : float
        Actual travel time (seconds) taken to arrive at destination.

    Returns
    -------
    float
        Relative delay degradation factor (>= 0.0).
        0.0 indicates zero delay degradation.
        0.5 indicates a 50% increase in travel duration.
    """
    if initial_travel_time <= 0.0:
        return 0.0
    excess = actual_travel_time - initial_travel_time
    if excess <= 0.0:
        return 0.0
    return excess / initial_travel_time


@dataclass
class RouteStabilityMetrics:
    """Aggregated route stability and detour delay metrics for a vehicle mission.

    Attributes
    ----------
    unit_id : str
        Apparatus identifier.
    initial_path : List[str]
        Initial route planned at dispatch.
    executed_path : List[str]
        Actual trajectory traversed.
    initial_travel_time : float
        Free-flow planned travel time (seconds).
    actual_travel_time : float
        Actual elapsed travel time (seconds).
    reroute_count : int
        Number of mid-flight dynamic rerouting events executed.
    path_stability_index : float
        Jaccard edge stability index in range [0.0, 1.0].
    detour_delay_degradation_factor : float
        Relative excess travel time ratio (>= 0.0).
    excess_delay_seconds : float
        Absolute excess seconds spent due to detour.
    """

    unit_id: str
    initial_path: List[str]
    executed_path: List[str]
    initial_travel_time: float
    actual_travel_time: float
    reroute_count: int = 0
    path_stability_index: float = 1.0
    detour_delay_degradation_factor: float = 0.0
    excess_delay_seconds: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Serializes route stability metrics to dictionary."""
        return {
            "unit_id": self.unit_id,
            "initial_path": list(self.initial_path),
            "executed_path": list(self.executed_path),
            "initial_travel_time": round(self.initial_travel_time, 2),
            "actual_travel_time": round(self.actual_travel_time, 2),
            "reroute_count": self.reroute_count,
            "path_stability_index": round(self.path_stability_index, 4),
            "detour_delay_degradation_factor": round(self.detour_delay_degradation_factor, 4),
            "excess_delay_seconds": round(self.excess_delay_seconds, 2),
        }


def evaluate_route_stability(
    unit_id: str,
    initial_path: Sequence[str],
    executed_path: Sequence[str],
    initial_travel_time: float,
    actual_travel_time: float,
    reroute_count: int = 0,
) -> RouteStabilityMetrics:
    """Evaluates stability and delay metrics for an executed vehicle mission.

    Parameters
    ----------
    unit_id : str
        Apparatus identifier.
    initial_path : Sequence[str]
        Initial planned route.
    executed_path : Sequence[str]
        Actual traversed path.
    initial_travel_time : float
        Planned travel time in seconds.
    actual_travel_time : float
        Actual travel time in seconds.
    reroute_count : int
        Number of mid-flight replans.

    Returns
    -------
    RouteStabilityMetrics
        Computed stability and detour degradation metrics.
    """
    psi = compute_path_stability_index(initial_path, executed_path)
    ddf = compute_detour_delay_degradation(initial_travel_time, actual_travel_time)
    excess_s = max(0.0, actual_travel_time - initial_travel_time)

    return RouteStabilityMetrics(
        unit_id=unit_id,
        initial_path=list(initial_path),
        executed_path=list(executed_path),
        initial_travel_time=initial_travel_time,
        actual_travel_time=actual_travel_time,
        reroute_count=reroute_count,
        path_stability_index=psi,
        detour_delay_degradation_factor=ddf,
        excess_delay_seconds=excess_s,
    )
