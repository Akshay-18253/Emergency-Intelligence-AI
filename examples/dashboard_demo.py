"""
Demonstration: Tactical Operations Dashboard & Interactive GIS Map Canvas.
==========================================================================
Demonstrates Milestone 8.2 capabilities:
  1. Bootstrapping the embedded web server and delivering the Tactical EOC single-page application.
  2. Serving dark-mode CSS tokens, glassmorphism cards, and Leaflet dark-mode overrides.
  3. Serving modular ES6 JavaScript architecture (api.js, sse.js, map.js, app.js).
  4. Client bootstrap telemetry handshake (health check, road network topology, emergency POIs).
  5. Topographic 3D elevation-aware emergency route calculation with turn maneuver telemetry.
  6. Dynamic disaster hazard injection triggering topological road severance.
  7. Graceful daemon shutdown.

Usage:
    python examples/dashboard_demo.py
"""

from __future__ import annotations

import json
import time
import urllib.request

from emergency_intelligence.app.server import EmergencyAppServer
from emergency_intelligence.app.state import AppState


def run_dashboard_demo() -> None:
    """Execute the end-to-end tactical operations dashboard demonstration."""
    print("=" * 80)
    print("  Emergency Intelligence AI — Milestone 8.2 Tactical Dashboard Demo")
    print("=" * 80)

    # Step 1: Bootstrapping Embedded Server
    print("\n[Step 1/6] Launching Embedded Server on Ephemeral Port...")
    state = AppState()
    server = EmergencyAppServer(host="127.0.0.1", port=0, state=state, enable_logging=False)
    server.start(blocking=False)
    base_url = f"http://127.0.0.1:{server.port}"
    print(f"  --> EOC Dashboard URL: {base_url}")
    print("  --> Runtime Engine:    Python Standard Library (Zero External Dependencies)")

    try:
        # Step 2: Static Asset Delivery
        print("\n[Step 2/6] Verifying Tactical Operations Frontend Assets Delivery...")
        assets = [
            ("/", "text/html"),
            ("/css/dashboard.css", "text/css"),
            ("/css/leaflet-custom.css", "text/css"),
            ("/js/api.js", "javascript"),
            ("/js/sse.js", "javascript"),
            ("/js/map.js", "javascript"),
            ("/js/app.js", "javascript"),
        ]

        for path, expected_mime in assets:
            req = urllib.request.Request(f"{base_url}{path}", method="GET")
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                status = resp.status
                mime = resp.headers.get("content-type", "")
                size_kb = len(resp.read()) / 1024.0
                print(f"  --> GET {path:<26} [{status} OK]  Size: {size_kb:5.1f} KB  MIME: {mime}")
                assert status == 200
                assert expected_mime in mime

        # Step 3: Telemetry & Network Topology Handshake
        print("\n[Step 3/6] Simulating Client GIS Map Topology & POI Intake...")
        with urllib.request.urlopen(f"{base_url}/api/network", timeout=3.0) as resp:
            network_env = json.loads(resp.read().decode("utf-8"))
            net_data = network_env.get("data", network_env)
            features = net_data.get("features", [])
            print(f"  --> Road Network Features: {len(features)} edges loaded")

        with urllib.request.urlopen(f"{base_url}/api/facilities", timeout=3.0) as resp:
            fac_env = json.loads(resp.read().decode("utf-8"))
            fac_data = fac_env.get("data", fac_env)
            print(f"  --> Emergency Facilities:  {len(fac_data)} POIs loaded")
            for poi in fac_data[:2]:
                print(f"      * [{poi['poi_type'].upper()}] {poi['name']} (Node: {poi['id']})")

        # Step 4: Emergency Route Calculation
        print("\n[Step 4/6] Computing 3D Elevation-Aware Route (ALS Ambulance N_0_0 -> N_3_3)...")
        route_payload = json.dumps({
            "origin": "N_0_0",
            "destination": "N_3_3",
            "apparatus_type": "AMBULANCE_ALS",
            "elevation_aware": True,
        }).encode("utf-8")

        req = urllib.request.Request(
            f"{base_url}/api/route",
            data=route_payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            route_env = json.loads(resp.read().decode("utf-8"))
            route = route_env.get("data", route_env)
            print(f"  --> Path Found:        {route.get('path_found')}")
            print(f"  --> Est. Duration:     {route.get('duration_seconds')} seconds")
            print(f"  --> Distance (2D/3D):  {route.get('distance_2d_meters')} m / {route.get('distance_3d_meters')} m")
            print(f"  --> Elevation Gain:    +{route.get('elevation_gain_meters')} m (Max Grade: {route.get('max_grade_percent')}%)")
            print(f"  --> Turn Maneuvers:    {len(route.get('maneuvers', []))} turn instructions generated")

        # Step 5: Dynamic Hazard Injection & Reroute Simulation
        print("\n[Step 5/6] Simulating Dynamic Disaster Hazard Injection (USGS River Flood)...")
        flood_payload = json.dumps({
            "polygon_coords": [
                [-122.332, 47.595],
                [-122.327, 47.595],
                [-122.327, 47.615],
                [-122.332, 47.615],
            ],
            "hazard_type": "RIVER_FLOOD",
            "speed_multiplier": 0.0,
            "severity": 1.0,
        }).encode("utf-8")

        req = urllib.request.Request(
            f"{base_url}/api/hazards",
            data=flood_payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            haz_env = json.loads(resp.read().decode("utf-8"))
            haz = haz_env.get("data", haz_env)
            print(f"  --> Hazard ID:         {haz.get('hazard_id')}")
            print(f"  --> Road Edges Closed: {haz.get('edges_closed')} links severed")
            print(f"  --> Total Hazards:     {haz.get('total_active_hazards')}")

        # Reset Hazards
        req = urllib.request.Request(f"{base_url}/api/hazards/reset", data=b"{}", headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            reset_env = json.loads(resp.read().decode("utf-8"))
            reset_data = reset_env.get("data", reset_env)
            print(f"  --> Hazards Reset:     {reset_data.get('cleared_count')} polygons cleared")

        # Step 6: Shutdown
        print("\n[Step 6/6] Shutting Down Server Daemon...")
        print("  --> Server shutdown complete.")

    finally:
        server.stop()

    print("\n" + "=" * 80)
    print("  Milestone 8.2 Demonstration Completed Successfully!")
    print("=" * 80)


if __name__ == "__main__":
    run_dashboard_demo()
