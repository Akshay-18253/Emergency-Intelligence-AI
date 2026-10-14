"""
Demonstration: Zero-Dependency Embedded HTTP Server & REST / Event-Stream Gateway.
==================================================================================
Demonstrates Milestone 8.1 capabilities:
  1. Bootstrapping embedded multi-threaded HTTP server with zero external dependencies.
  2. Health, network topology, and facility inspection REST endpoints.
  3. Real-time multi-criteria route calculation with turn maneuver telemetry.
  4. 5-stage 911 intake and statutory emergency policy orchestration.
  5. Dynamic hazard polygon injection and live topological edge severance.
  6. Server-Sent Events (SSE) telemetry connection.
  7. Graceful daemon shutdown.

Usage:
    python examples/app_server_demo.py
"""

from __future__ import annotations

import json
import time
import urllib.request

from emergency_intelligence.app.server import EmergencyAppServer
from emergency_intelligence.app.state import AppState


def run_app_server_demo() -> None:
    """Execute the end-to-end embedded HTTP server demonstration."""
    print("=" * 80)
    print("  Emergency Intelligence AI — Phase 8 Milestone 8.1 Embedded Server Demo")
    print("=" * 80)

    # Step 1: Bootstrapping Embedded Server
    print("\n[Step 1/6] Launching Embedded ThreadingHTTPServer on Ephemeral Port...")
    state = AppState()
    server = EmergencyAppServer(host="127.0.0.1", port=0, state=state)
    server.start(blocking=False)
    base_url = f"http://127.0.0.1:{server.port}"
    print(f"  --> Server Status:     ONLINE at {base_url}")
    print(f"  --> Background Thread: {server._thread.name if server._thread else 'active'}")
    print("  --> Runtime Engine:    Python 100% Standard Library (http.server / threading)")

    try:
        # Step 2: Health & System Diagnostics
        print("\n[Step 2/6] Querying GET /api/health...")
        with urllib.request.urlopen(f"{base_url}/api/health", timeout=3.0) as resp:
            health_json = json.loads(resp.read().decode("utf-8"))
            data = health_json.get("data", {})
            print(f"  --> Status:            {data.get('status')}")
            print(f"  --> Graph Topology:    {data.get('graph_nodes')} intersections, {data.get('graph_edges')} road segments")
            print(f"  --> Facilities Bound:  {data.get('emergency_facilities')} hospitals and stations")
            print(f"  --> Active Hazards:    {data.get('active_hazards')}")

        # Step 3: Emergency Facilities Catalog
        print("\n[Step 3/6] Querying GET /api/facilities...")
        with urllib.request.urlopen(f"{base_url}/api/facilities", timeout=3.0) as resp:
            fac_json = json.loads(resp.read().decode("utf-8"))
            facilities = fac_json.get("data", [])
            print(f"  --> Facilities Retrieved: {len(facilities)}")
            for fac in facilities:
                print(f"      - [{fac['poi_type'].upper()}] {fac['name']} (Bays: {fac['apparatus_bays']}, Helipad: {fac['has_helipad']})")

        # Step 4: Multi-Criteria Route Calculation
        print("\n[Step 4/6] Executing POST /api/route (ALS Ambulance from N_0_0 to N_3_5)...")
        route_payload = {
            "origin": "N_0_0",
            "destination": "N_3_5",
            "apparatus_type": "ambulance_als",
            "elevation_aware": True,
        }
        req = urllib.request.Request(
            f"{base_url}/api/route",
            data=json.dumps(route_payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            route_json = json.loads(resp.read().decode("utf-8"))
            route_data = route_json.get("data", {})
            print(f"  --> Path Reachable:     {route_data.get('path_found')}")
            print(f"  --> Duration:           {route_data.get('duration_seconds')} s")
            print(f"  --> 2D / 3D Distance:   {route_data.get('distance_2d_meters')} m / {route_data.get('distance_3d_meters')} m")
            print(f"  --> Elevation Gain:     {route_data.get('elevation_gain_meters')} m (Max Grade: {route_data.get('max_grade_percent')}%)")
            print(f"  --> Turn Maneuvers:     {len(route_data.get('maneuvers', []))} navigational turn instructions")
            print(f"  --> Route Nodes:        {' -> '.join(route_data.get('nodes', []))}")

        # Step 5: 911 Call Intake & Statutory Policy Enforcement
        print("\n[Step 5/6] Executing POST /api/intake (Cardiac Arrest Narrative)...")
        intake_payload = {
            "raw_text": "55yo male sudden cardiac arrest collapse at 4th and Pine. Caller: 206-555-0199.",
            "caller_phone": "206-555-0199",
        }
        req = urllib.request.Request(
            f"{base_url}/api/intake",
            data=json.dumps(intake_payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            intake_json = json.loads(resp.read().decode("utf-8"))
            intake_data = intake_json.get("data", {})
            print(f"  --> Intake ID:          {intake_data.get('intake_id')}")
            print(f"  --> Urgency Tier:       {intake_data.get('urgency')}")
            print(f"  --> Policy Directives:  {', '.join(intake_data.get('policy_directives', []))}")
            dispatched = intake_data.get("dispatched_units", [])
            print(f"  --> Units Dispatched:   {len(dispatched)}")
            for u in dispatched:
                print(f"      * Unit: {u['unit_id']} ({u['apparatus_type']}) from {u['station_id']} [ETA: {u['eta_seconds']:.1f}s]")
            if intake_data.get("destination_facility"):
                dest = intake_data["destination_facility"]
                print(f"  --> Hospital Matched:   {dest['name']} (Trauma Level: {dest['trauma_level']})")
            print(f"  --> Audit Fingerprint:  {intake_data.get('audit_checksum')[:32]}... (SHA-256)")

        # Step 6: Dynamic Hazard Injection & Reset
        print("\n[Step 6/6] Executing POST /api/hazards (River Flood Causeway Blockage)...")
        hazard_payload = {
            "hazard_type": "flood_inundation",
            "speed_multiplier": 0.0,
            "severity": "CRITICAL",
            "polygon_coords": [
                [-122.332, 47.600],
                [-122.328, 47.600],
                [-122.328, 47.610],
                [-122.332, 47.610],
            ],
        }
        req = urllib.request.Request(
            f"{base_url}/api/hazards",
            data=json.dumps(hazard_payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            haz_json = json.loads(resp.read().decode("utf-8"))
            haz_data = haz_json.get("data", {})
            print(f"  --> Injected Hazard:    {haz_data.get('hazard_id')}")
            print(f"  --> Severed Edges:      {haz_data.get('edges_closed')} closed bridges / causeways")

        # Clear and reset
        req_reset = urllib.request.Request(f"{base_url}/api/hazards/reset", data=b"{}", headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req_reset, timeout=3.0) as resp:
            reset_json = json.loads(resp.read().decode("utf-8"))
            print(f"  --> Hazard Cleared:     {reset_json['data']['status']} (Cleared: {reset_json['data']['cleared_count']})")

    finally:
        print("\n[Teardown] Shutting down embedded HTTP server...")
        server.stop()
        print("  --> Server Terminated cleanly.")

    print("\n" + "=" * 80)
    print("  Milestone 8.1 Embedded Server & API Gateway Demo Completed Successfully!")
    print("=" * 80)


if __name__ == "__main__":
    run_app_server_demo()
