# Emergency Intelligence AI — Tactical EOC Operator Walkthrough & Operations Manual

> **Document Version:** 1.0.0  
> **System Release:** 0.2.0 (Phase 8 Complete)  
> **Target Audience:** Emergency Operations Center (EOC) Watch Officers, 911 CAD Dispatchers, Municipal Responders, and Systems Engineers.

---

## 1. Executive Overview & Operational Ambition

**Emergency Intelligence AI** is a zero-external-dependency, tactical crisis routing and autonomous dispatch verification system engineered for high-stress municipal emergency management. It bridges the gap between chaotic, natural-language 911 caller intake and deterministic, statutory emergency fleet routing.

### Core Operational Principles
1. **Zero External Runtime Dependencies:** Operates exclusively using the standard Python runtime (`python >= 3.10`) and native web technologies (HTML5, Vanilla CSS, ES6 JavaScript, Web Audio API, and SVG). No external pip packages, Node.js runtimes, or database engines are required at runtime.
2. **Deterministic Safety Guardrails:** AI natural language reasoning is strictly separated from statutory response policies. Mandatory dual-response requirements (such as AHA cardiac arrest rules and NFPA 1710 structure fire complements) are computed deterministically and cannot be bypassed.
3. **Cryptographic Tamper-Evident Auditability:** Every CAD narrative evaluation produces a SHA-256 hash chaining the raw input, masked text, statutory determinations, and apparatus assignments into an immutable chronological ledger.
4. **Resilient Offline Operation:** Capable of running in air-gapped, isolated field command vehicles, disaster response trailers, and hardened EOC server racks without internet connectivity.

---

## 2. System Architecture & Topology

```
                   +-----------------------------------------------+
                   |           Tactical EOC Browser Client         |
                   |   (Dashboard HTML, Map Canvas, CAD Terminal,  |
                   |      Audio Synthesizer, Timeline Scrub Bar)   |
                   +-----------------------+-----------------------+
                                           | HTTP REST & SSE Stream
                                           v
                   +-----------------------------------------------+
                   |       Embedded EmergencyAppServer (HTTP)      |
                   |      Python ThreadingHTTPServer (Port 8080)   |
                   +-----------------------+-----------------------+
                                           |
            +------------------------------+------------------------------+
            |                              |                              |
            v                              v                              v
+-----------------------+      +-----------------------+      +-----------------------+
|  Emergency Intelligence|     |  Dynamic Hazard &     |      |  Discrete-Event       |
|  Orchestration Engine |      |  Rerouting Subsystem  |      |  Simulation Timeline  |
|  (NLP, Policy, Hash)  |      |  (Ray-casting, A*)    |      |  (Kinematics, Events) |
+-----------------------+      +-----------------------+      +-----------------------+
```

---

## 3. Launching the Embedded EOC Server

The operations server can be deployed through three standard methods:

### Method A: Command-Line Interface (Installed Package)
Once the wheel or package is installed, launch the server using the standard CLI entrypoint:
```bash
emergency-intelligence-server --host 127.0.0.1 --port 8080 --log
```

### Method B: Direct Python Module Invocation (Pure Standard Library)
From the root of the repository without any prior installation:
```bash
python -m emergency_intelligence.app.server --host 0.0.0.0 --port 8080
```

### Method C: Zero-Dependency Docker Container
Build and launch the lightweight container image:
```bash
# Build the container (approx. 150MB based on python:3.12-slim)
docker build -t emergency-intelligence:latest .

# Run container mapping port 8080
docker run -d --name eoc-server -p 8080:8080 emergency-intelligence:latest

# Verify health status
docker inspect --format='{{json .State.Health.Status}}' eoc-server
```

Once running, navigate your web browser to:
```
http://127.0.0.1:8080/
```

---

## 4. Tactical Operations Dashboard Navigation

The EOC console is partitioned into four synchronized tactical zones:

### 4.1 Header Telemetry Bar
- **System Indicator:** Displays `EMERGENCY INTELLIGENCE AI` with real-time UTC timestamp.
- **Connection Status:** Shows live Server-Sent Events (SSE) telemetry connectivity (`CONNECTED` / `OFFLINE`).
- **Tactical Fleet Status:** Live apparatus counter indicating available and dispatched units.
- **Active Hazards Counter:** Real-time count of active dynamic hazard zones affecting road geometry.

### 4.2 Interactive GIS Map Canvas
- **Carto Dark Matter Canvas:** High-contrast GIS backdrop optimized for dim EOC monitor walls.
- **Interactive Layers:**
  - **Hospital Facilities (Blue Crosses):** Primary clinical trauma centers, burn units, and emergency bays.
  - **Fire & EMS Stations (Red Shields):** Municipal deployment depots housing engines, ladders, and ambulances.
  - **Dynamic Hazard Polygons (Amber / Red Zones):** Floods, road closures, and collapse zones rendered with vector outlines.
  - **Active Fleet (Moving Icons):** Ambulances (🚑), Fire Engines (🚒), and Rescue Units with heading vectors.
  - **Emergency Route Corridors (Cyan Polylines):** Real-time 3D slope-weighted shortest paths computed by the A* routing engine.

---

## 5. Live CAD 911 Narrative Intake & Natural Language Pipeline

The CAD Intake Terminal allows dispatchers to type raw emergency call narratives or select standard pre-incident scenarios.

### 5.1 Pre-Configured Incident Presets
Click any of the three quick-load buttons to populate realistic scenarios:
1. **Waterfront Cardiac Arrest:** Critical Alpha-level medical emergency triggering mandatory dual-response protocols.
2. **Multi-Alarm Structural Fire:** High-risk fire event triggering NFPA 1710 full alarm complement assignment.
3. **Hazardous Materials Leak:** Chemical spill requiring specialized hazmat apparatus and perimeter isolation.

### 5.2 Step-by-Step Narrative Intake Workflow
1. Type or paste the caller narrative into the `Caller Narrative Intake` text area.
2. Click **Evaluate & Dispatch Incident** (`#btn-cad-dispatch`).
3. The server processes the narrative through the 5-Stage Orchestration Pipeline:
   - **Stage 1 (PII Masking):** Patient names, phone numbers, and SSNs are scrubbed via HIPAA Safe Harbor compliance patterns.
   - **Stage 2 (Intent & Location Extraction):** Identifies incident category, severity score, and coordinates.
   - **Stage 3 (Statutory Policy Verification):** Evaluates statutory response mandates (AHA / NFPA).
   - **Stage 4 (Apparatus Matching & A* Routing):** Finds the nearest capable apparatus and computes optimal transit routes.
   - **Stage 5 (Tamper-Evident SHA-256 Hashing):** Generates a cryptographic ledger entry verifying policy invariance.

### 5.3 Reviewing the 5-Stage Policy Verification Card
Upon dispatch, the **Policy Verification Card** (`#cad-policy-card`) renders:
- **Triage Priority & Category:** e.g., `CRITICAL` / `CARDIAC_ARREST`.
- **AHA Dual-Response Mandate:** Confirms simultaneous dispatch of Basic Life Support (BLS) and Advanced Life Support (ALS) units.
- **NFPA 1710 Full Alarm Compliance:** Confirms apparatus assignments meet statutory firefighter arrival complements.
- **Cryptographic Audit Digest:** 64-character SHA-256 hex string validating dispatch integrity.

---

## 6. Web Audio Warning System

To alert EOC personnel of priority incident triage without external media dependencies:
- **Synthetic Frequency Generator:** Uses the browser's native `AudioContext` to generate dual-tone acoustic alerts (880 Hz / 660 Hz frequency pairs).
- **Audio Toggle Control:** Operators can silence or reactivate the audio alert system at any time using the `Mute / Unmute Audio` button (`#btn-audio-toggle`).
- **Tone Frequency Standard:**
  - Priority 1 (Critical): High-tempo alternating dual-tone siren pulse.
  - Priority 2/3 (Routine/Urgent): Single confirming chime.

---

## 7. Simulation Timeline & Playback Controller

The bottom timeline bar allows operators to scrub through simulated time and observe kinematic fleet behavior.

### 7.1 Timeline Control Operations
- **Step Forward (+15s) (`#btn-sim-step`):** Advances the discrete-event clock by 15 seconds. In-transit vehicles advance along their assigned road edges proportionally to their kinematic speeds.
- **Play / Pause (`#btn-sim-play`):** Starts continuous 1 Hz simulation clock ticking.
- **Direct Time Scrubbing (`#sim-timeline-slider`):** Drag the timeline slider to scrub to any point from $T+0\text{ s}$ to $T+300\text{ s}$.
- **Reset Simulation (`#btn-sim-reset`):** Restores all apparatus to depot stations and clears simulated incident queues.

### 7.2 Kinematic Vehicle Progression Invariants
During simulation playback, vehicles adhere to continuous kinematic progression:
$$r_v(t + \Delta t) = \min\left(1.0, r_v(t) + \frac{\Delta t \cdot v_{\text{speed}}}{L_{\text{edge}}}\right)$$
When progress ratio $r_v = 1.0$, the vehicle transitions to the subsequent edge on its A* trajectory or assumes `ON_SCENE` status upon reaching the incident coordinate.

---

## 8. Dynamic Disaster Hazard Injection & Detour Rerouting

During an unfolding crisis, road networks degrade dynamically:
1. **Dynamic Flood Inundation:** Triggering a river overflow marks downstream segments with high-cost traversal penalties.
2. **Structural Collapse Zones:** Complete polygon closures sever graph edges using non-destructive transactional rollbacks (`DynamicGraphView`).
3. **Reactive In-Flight Rerouting:** Active en-route apparatus detect upcoming road obstructions within 100 milliseconds and calculate deterministic bypass detours around hazard boundaries.

---

## 9. REST & Server-Sent Events (SSE) API Reference

For integration into municipal dispatch backbones and third-party CAD systems, the server provides standard JSON endpoints:

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/health` | Service liveness probe returning system uptime and component health. |
| `GET` | `/api/network/status` | Current count of nodes, edges, stations, hospitals, and apparatus. |
| `POST` | `/api/route/compute` | Computes A* route between two coordinates with vehicle profile weighting. |
| `POST` | `/api/cad/evaluate` | Evaluates 911 natural language narrative, enforces policies, and dispatches fleet. |
| `GET` | `/api/cad/audit-log` | Retrieves chronological SHA-256 tamper-evident dispatch audit records. |
| `GET` | `/api/simulation/status` | Returns discrete-event simulation time, active incidents, and vehicle coordinates. |
| `POST` | `/api/simulation/step` | Advances simulation clock by $\Delta t$ seconds and recalculates kinematics. |
| `POST` | `/api/simulation/reset` | Resets simulation timeline back to $T+0\text{ s}$. |
| `POST` | `/api/hazards` | Injects a geometric hazard polygon (flood, fire, structural collapse). |
| `DELETE` | `/api/hazards` | Clears all active dynamic hazard zones and restores baseline graph edges. |
| `GET` | `/api/telemetry/events` | Real-time Server-Sent Events (SSE) stream broadcasting fleet and hazard mutations. |

---

## 10. Statutory Compliance & Non-Certification Notice

> [!IMPORTANT]
> **Regulatory Disclaimer:**  
> This software is an experimental, open-source decision-support prototype. It has not been formally certified under NFPA 1221, NFPA 1710, or municipal public safety answering point (PSAP) standards for autonomous emergency dispatch. All dispatches, sirens, and travel times generated within this prototype must be monitored and verified by licensed human telecommunicators prior to physical field activation.
