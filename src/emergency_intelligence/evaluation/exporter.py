"""
Multi-format simulation data exporter for Emergency Intelligence AI.

Provides standards-compliant data export across:
1. Structured JSON Time-Series Telemetry:
   Full chronological event logs, incident states, apparatus kinematics, and queue profiles.
2. Tabular CSV Metrics:
   RFC 4180 compliant tabular files for statistical analysis in spreadsheet and data-science workflows.
3. RFC 7946 GeoJSON Spatial Replay:
   Standard GIS GeoJSON FeatureCollections containing road network edges, emergency stations,
   incident scenes, hazard polygons, and vehicle movement trajectories.
"""

from __future__ import annotations

import csv
import io
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

from emergency_intelligence.events.hazards import HazardPolygon
from emergency_intelligence.graph.models import Graph
from emergency_intelligence.simulation.scenarios import ScenarioDefinition, ScenarioResult
from .benchmark import ComparativeBenchmarkSummary
from .metrics import IncidentResponseRecord


# ---------------------------------------------------------------------------
# JSON Telemetry Exporter
# ---------------------------------------------------------------------------


def export_telemetry_json(
    result: ScenarioResult,
    filepath: Optional[Union[str, Path]] = None,
    indent: int = 2,
) -> str:
    """Exports full scenario simulation results to a canonical JSON structure.

    Parameters
    ----------
    result : ScenarioResult
        Result returned by ScenarioRunner.run().
    filepath : Optional[Union[str, Path]]
        Optional destination file path. If provided, file will be written to disk.
    indent : int
        Indentation spaces for formatted JSON (default 2).

    Returns
    -------
    str
        JSON serialized string.
    """
    payload = {
        "schema_version": "1.0.0",
        "type": "EmergencySimulationTelemetry",
        "scenario": {
            "name": result.scenario_name,
            "simulated_duration_seconds": round(result.simulated_duration, 2),
            "wall_clock_execution_ms": round(result.wall_clock_ms, 2),
            "total_incidents": result.total_incidents,
            "incidents_serviced": result.incidents_serviced,
            "incidents_queued": result.incidents_queued_count,
            "units_dispatched": result.units_dispatched_count,
            "total_reroutes": result.total_reroutes,
            "total_distance_meters": round(result.total_distance_meters, 2),
            "average_response_time_seconds": round(result.average_response_time, 2),
            "max_response_time_seconds": round(result.max_response_time, 2),
            "average_queue_delay_seconds": round(result.average_queue_delay_seconds, 2),
            "max_queue_delay_seconds": round(result.max_queue_delay_seconds, 2),
        },
        "incidents": result.incident_records,
        "vehicles": result.vehicle_records,
        "engine_summary": result.engine_summary,
    }

    json_str = json.dumps(payload, indent=indent)

    if filepath is not None:
        p = Path(filepath)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json_str, encoding="utf-8")

    return json_str


# ---------------------------------------------------------------------------
# Tabular CSV Metrics Exporters
# ---------------------------------------------------------------------------


def export_incident_metrics_csv(
    records: Sequence[IncidentResponseRecord],
    filepath: Optional[Union[str, Path]] = None,
) -> str:
    """Exports incident response records to an RFC 4180 compliant CSV string.

    Parameters
    ----------
    records : Sequence[IncidentResponseRecord]
        List of IncidentResponseRecord objects.
    filepath : Optional[Union[str, Path]]
        Optional file path to persist the CSV output.

    Returns
    -------
    str
        Serialized CSV string.
    """
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")

    # Header
    writer.writerow([
        "incident_id",
        "emergency_type",
        "urgency",
        "report_time_s",
        "first_dispatch_time_s",
        "first_arrival_time_s",
        "all_arrival_time_s",
        "cleared_time_s",
        "queue_delay_s",
        "turnout_time_s",
        "first_travel_time_s",
        "first_total_response_time_s",
        "full_alarm_travel_time_s",
        "units_count",
        "assigned_units",
    ])

    for r in records:
        writer.writerow([
            r.incident_id,
            r.emergency_type,
            r.urgency,
            f"{r.report_time:.2f}",
            f"{r.first_dispatch_time:.2f}" if r.first_dispatch_time is not None else "",
            f"{r.first_arrival_time:.2f}" if r.first_arrival_time is not None else "",
            f"{r.all_arrival_time:.2f}" if r.all_arrival_time is not None else "",
            f"{r.cleared_time:.2f}" if r.cleared_time is not None else "",
            f"{r.queue_delay_seconds:.2f}",
            f"{r.turnout_time_seconds:.2f}" if r.turnout_time_seconds is not None else "",
            f"{r.first_travel_time_seconds:.2f}" if r.first_travel_time_seconds is not None else "",
            f"{r.first_total_response_time_seconds:.2f}" if r.first_total_response_time_seconds is not None else "",
            f"{r.full_alarm_travel_time_seconds:.2f}" if r.full_alarm_travel_time_seconds is not None else "",
            len(r.assigned_units),
            ";".join(r.assigned_units),
        ])

    csv_text = output.getvalue()

    if filepath is not None:
        p = Path(filepath)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(csv_text, encoding="utf-8")

    return csv_text


def export_strategy_comparison_csv(
    summary: ComparativeBenchmarkSummary,
    filepath: Optional[Union[str, Path]] = None,
) -> str:
    """Exports comparative routing benchmark outcomes to an RFC 4180 compliant CSV.

    Parameters
    ----------
    summary : ComparativeBenchmarkSummary
        Outcome from ComparativeRoutingBenchmark.run_all().
    filepath : Optional[Union[str, Path]]
        Optional destination file path.

    Returns
    -------
    str
        Serialized CSV string.
    """
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")

    writer.writerow([
        "scenario_name",
        "strategy",
        "arrived",
        "travel_time_seconds",
        "total_distance_meters",
        "reroute_count",
        "stalled",
        "polling_interval_seconds",
        "path_stability_index",
        "detour_delay_factor",
    ])

    for strat, res in summary.results.items():
        t_str = f"{res.travel_time_seconds:.2f}" if math.isfinite(res.travel_time_seconds) else "STALLED"
        poll_str = f"{res.polling_interval_seconds:.1f}" if res.polling_interval_seconds is not None else ""
        writer.writerow([
            res.scenario_name,
            strat.value,
            "true" if res.arrived else "false",
            t_str,
            f"{res.total_distance_meters:.2f}",
            res.reroute_count,
            "true" if res.stalled else "false",
            poll_str,
            f"{res.path_stability_index:.4f}",
            f"{res.detour_delay_factor:.4f}",
        ])

    csv_text = output.getvalue()

    if filepath is not None:
        p = Path(filepath)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(csv_text, encoding="utf-8")

    return csv_text


# ---------------------------------------------------------------------------
# RFC 7946 GeoJSON Spatial Replay Exporter
# ---------------------------------------------------------------------------


def export_spatial_replay_geojson(
    scenario_def: ScenarioDefinition,
    result: ScenarioResult,
    filepath: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    """Exports road network, stations, incidents, hazards, and vehicle trajectories to RFC 7946 GeoJSON.

    Produces a valid FeatureCollection suitable for import into QGIS, kepler.gl,
    geojson.io, Leaflet, and Mapbox.

    Parameters
    ----------
    scenario_def : ScenarioDefinition
        The scenario definition containing road network graph, stations, and hazards.
    result : ScenarioResult
        The execution result containing incident and vehicle telemetry.
    filepath : Optional[Union[str, Path]]
        Optional destination file path to save GeoJSON.

    Returns
    -------
    Dict[str, Any]
        RFC 7946 compliant GeoJSON FeatureCollection dictionary.
    """
    graph: Graph = scenario_def.graph
    features: List[Dict[str, Any]] = []

    # 1. Road Network Edges (LineStrings)
    for node_id in graph.node_ids():
        u_node = graph.get_node(node_id)
        if not u_node or not u_node.coordinates:
            continue
        u_coords = list(u_node.coordinates)

        for edge in graph.get_neighbors(node_id):
            v_node = graph.get_node(edge.destination_id)
            if not v_node or not v_node.coordinates:
                continue
            v_coords = list(v_node.coordinates)

            features.append({
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [u_coords, v_coords],
                },
                "properties": {
                    "feature_type": "road_edge",
                    "source_id": edge.source_id,
                    "destination_id": edge.destination_id,
                    "cost": edge.cost,
                    "distance_meters": edge.attributes.get("distance", edge.cost),
                    "speed_limit_kmh": edge.attributes.get("speed_limit_kmh", 50.0),
                },
            })

    # 2. Emergency Stations (Points)
    for station in scenario_def.stations:
        st_node = graph.get_node(station.node_id)
        coords = list(st_node.coordinates) if st_node and st_node.coordinates else [0.0, 0.0]
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": coords,
            },
            "properties": {
                "feature_type": "station",
                "station_id": station.station_id,
                "name": station.name,
                "node_id": station.node_id,
            },
        })

    # 3. Incidents (Points)
    for inc_rec in result.incident_records:
        iid = inc_rec["incident_id"]
        # Find incident node coordinates in scenario
        matching_inc = next(
            (inc for _, inc, _ in scenario_def.incidents if inc.incident_id == iid),
            None,
        )
        coords = [0.0, 0.0]
        if matching_inc and matching_inc.coordinates:
            coords = list(matching_inc.coordinates)

        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": coords,
            },
            "properties": {
                "feature_type": "incident",
                "incident_id": iid,
                "emergency_type": inc_rec.get("emergency_type"),
                "urgency": inc_rec.get("urgency"),
                "report_time_seconds": inc_rec.get("report_time"),
                "first_arrival_time_seconds": inc_rec.get("first_arrival_time"),
                "response_time_seconds": inc_rec.get("response_time_seconds"),
                "queue_delay_seconds": inc_rec.get("queue_delay_seconds"),
                "assigned_units": inc_rec.get("assigned_units", []),
                "is_resolved": inc_rec.get("is_resolved", False),
            },
        })

    # 4. Hazard Polygons (Polygons)
    for _, hid, hazard_poly in scenario_def.hazards:
        boundary = [list(pt) for pt in hazard_poly.boundary_coordinates]
        # RFC 7946 requires linear ring to be closed: first == last
        if boundary and boundary[0] != boundary[-1]:
            boundary.append(list(boundary[0]))

        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [boundary],
            },
            "properties": {
                "feature_type": "hazard_polygon",
                "hazard_id": hid,
                "hazard_type": hazard_poly.hazard_type.value,
                "severity": hazard_poly.severity.value,
            },
        })

    # 5. Vehicle Executed Trajectories (LineStrings)
    for v_rec in result.vehicle_records:
        uid = v_rec["unit_id"]
        tracker = v_rec.get("tracker")
        path_nodes = tracker.get("path", []) if tracker else []

        if len(path_nodes) >= 2:
            path_coords: List[List[float]] = []
            for nid in path_nodes:
                n = graph.get_node(nid)
                if n and n.coordinates:
                    path_coords.append(list(n.coordinates))

            if len(path_coords) >= 2:
                features.append({
                    "type": "Feature",
                    "geometry": {
                        "type": "LineString",
                        "coordinates": path_coords,
                    },
                    "properties": {
                        "feature_type": "vehicle_trajectory",
                        "unit_id": uid,
                        "apparatus_type": v_rec.get("apparatus_type"),
                        "status": v_rec.get("status"),
                        "total_travel_time_seconds": v_rec.get("total_travel_time"),
                        "total_distance_meters": v_rec.get("total_distance_meters"),
                        "reroute_count": v_rec.get("reroute_count"),
                        "node_path": path_nodes,
                    },
                })

    geojson_doc = {
        "type": "FeatureCollection",
        "name": f"{scenario_def.name} Spatial Replay",
        "metadata": {
            "scenario_name": scenario_def.name,
            "simulated_duration_seconds": result.simulated_duration,
            "feature_count": len(features),
        },
        "features": features,
    }

    if filepath is not None:
        p = Path(filepath)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(geojson_doc, indent=2), encoding="utf-8")

    return geojson_doc
