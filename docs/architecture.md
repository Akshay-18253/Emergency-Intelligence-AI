# Emergency Intelligence AI — System Architecture

> **Status:** Foundational architectural layers (Phases 1 through 6) and Phase 7 (Milestones 7.1 and 7.2) are **fully implemented and verified**.
> Core library has **zero external runtime dependencies** (100% Python standard library).
> **569 unit tests passing with 95.70% statement and branch coverage across 42 modules.**

---

## Guiding Principle

> **AI should help interpret emergency context and formulate routing objectives or constraints, while deterministic and testable algorithms should perform route computation wherever appropriate.**

This strict separation between **AI reasoning**, **statutory policy enforcement**, **deterministic graph computation**, and **dynamic disaster adaptation** is the architectural foundation of the project. It produces a system that is mathematically explainable, reproducible, tamper-evident, and immune to model hallucinations in life-critical dispatch environments.

---

## Complete System Overview

```
Unstructured 911 / Emergency Input (Call, SMS, Speech-to-Text, CAD Alert)
                               │
                               ▼
┌────────────────────────────────────────────────────────────────────────┐
│  LAYER 5: EMERGENCY INTELLIGENCE & ORCHESTRATION LAYER                 │
│  ├── Stage 1: Intake & PII Sanitization (regex mask, length bounds)    │
│  ├── Stage 2: Schema-Constrained Model Adapter (StructuredModelAdapter)│
│  ├── Stage 3: Deterministic Contract Boundary (validate_incident)      │
│  ├── Stage 4: Authoritative Statutory Policy Engine (NFPA 1710/1221)   │
│  └── Audit Trail & Integrity Checksum (SHA-256 sequence hash)          │
└──────────────────────────────┬─────────────────────────────────────────┘
                               │ Structured OperationalPolicyDirective
                               │ & Validated Incident Contract
                               ▼
┌────────────────────────────────────────────────────────────────────────┐
│  LAYER 4: FLEET ALLOCATION & CATCHMENT PARTITIONING                    │
│  ├── Multi-Source Voronoi Catchment Area Partitioning                  │
│  ├── NFPA 1710 Travel Time Isochrone Frontiers (240s / 480s)           │
│  └── Apparatus Capability Matcher & Candidate ETA Ranking              │
└──────────────────────────────┬─────────────────────────────────────────┘
                               │ Filtered Unit Candidates
                               ▼
┌────────────────────────────────────────────────────────────────────────┐
│  LAYER 3: DYNAMIC CONDITIONS & REAL-TIME DISASTER MUTATIONS            │
│  ├── OASIS CAP v1.2 XML / GeoJSON Federal Alert Feed Parsers           │
│  ├── 2D Geometric Hazard Polygons (vector ray-casting & intersections) │
│  ├── Non-Destructive Graph Overlay Mutations (DynamicGraphView)        │
│  └── In-Flight Vehicle Tracker & Sub-Millisecond Detour Replanning     │
└──────────────────────────────┬─────────────────────────────────────────┘
                               │ Active Dynamic Graph & Edge Penalties
                               ▼
┌────────────────────────────────────────────────────────────────────────┐
│  LAYER 7: EXTERNAL DATA & GEOSPATIAL MAP INTEGRATION [PHASE 7]         │
│  ├── Overpass QL Query Builder & Live OSM Emergency POI Extractor       │
│  ├── Trauma Tiers 1-4, Burn, Pediatric, Cardiac, Bay Triage Extraction │
│  ├── Multi-Criteria Spatial Index Snapping & POI Road Network Binding  │
│  ├── Dynamic Fleet Generation & Multi-Criteria Hospital Routing        │
│  ├── NASA SRTM Elevation Model & Sub-Grid Bilinear Interpolation       │
│  └── Apparatus Incline Physics, Climb Limits & Elevation Graph Views   │
└──────────────────────────────┬─────────────────────────────────────────┘
                               │ Enriched Clinical Road Graph & POIs
                               ▼
┌────────────────────────────────────────────────────────────────────────┐
│  LAYER 2: GEOSPATIAL & ROAD NETWORK INGESTION                          │
│  ├── Streaming OpenStreetMap XML (iterparse) & Overpass JSON Loader    │
│  ├── 2D Spatial Hash Grid (O(1) localized point lookups)               │
│  ├── Orthogonal Segment Snapping & Network Coordinate Projection       │
│  └── Compiled Road Network Caching (.eig.json with SHA-256 digest)     │
└──────────────────────────────┬─────────────────────────────────────────┘
                               │ Sanitized Network Topology
                               ▼
┌────────────────────────────────────────────────────────────────────────┐
│  LAYER 1: CORE ROUTING ENGINE & TOPOLOGY OPTIMIZATION                  │
│  ├── In-Memory Directed Graph Primitives (Node, Edge, Graph)           │
│  ├── Tarjan's Strongly Connected Components (LSCC Island Filter)       │
│  ├── Degree-2 Intermediate Node Contraction (Topology Compression)     │
│  ├── Heuristic Search (A*, Dijkstra, Multi-Criteria Cost Profiles)    │
│  └── RFC 7946 GeoJSON Trajectory Exporter (QGIS / Leaflet Export)      │
└──────────────────────────────┬─────────────────────────────────────────┘
                               │
                               ▼
┌────────────────────────────────────────────────────────────────────────┐
│  LAYER 6: SIMULATION & QUANTITATIVE EVALUATION [PHASE 6 — VERIFIED]    │
│  ├── Discrete-Event Disaster Simulation Engine (SimulationTimeline)    │
│  ├── Continuous Edge Kinematics & Fractional Position Tracking         │
│  ├── Multi-Incident Scenarios & Resource Contention Models             │
│  ├── NFPA 1710 Response Compliance & Heuristic Search Profiling        │
│  ├── Comparative Routing Benchmarks (Static vs Polling vs Reactive)    │
│  └── Multi-Format Exporters (JSON Telemetry, CSV, RFC 7946 GeoJSON)    │
└────────────────────────────────────────────────────────────────────────┘
```

---

## Layer Breakdown

### Layer 1 — Core Routing Engine & Topology Optimization
**Location:** [`src/emergency_intelligence/graph/`](../src/emergency_intelligence/graph/)

- **Graph Primitives (`models.py`):** Directed, weighted graph model supporting directed one-way streets, multi-edges, and bidirectional avenues.
- **Routing Algorithms (`dijkstra.py`, `astar.py`):** Dijkstra's algorithm implemented with manual `heapq` state tracking, and A* informed heuristic search with cost tie-breaking.
- **Admissible Heuristics (`heuristics.py`):** Euclidean, Manhattan, Zero (Dijkstra equivalence), and Spherical Haversine distance heuristics.
- **Topology Optimization (`topology.py`):**
  - **Tarjan's SCC:** Extracts the Largest Strongly Connected Component (LSCC) to prune unreachable dead-end islands.
  - **Degree-2 Contraction:** Compresses intermediate linear waypoints into single shortcut edges while preserving exact cumulative distance and transit times.
  - **Maneuver Classification:** Computes azimuth forward bearings and classifies turn maneuvers (`TURN_LEFT`, `TURN_RIGHT`, `SLIGHT_LEFT`, `U_TURN`).

### Layer 2 — Geospatial & Road Network Ingestion
**Location:** [`src/emergency_intelligence/data/`](../src/emergency_intelligence/data/)

- **Spherical Geometry (`geo.py`):** Pure-Python Haversine distance formula and forward azimuth bearing computations.
- **Streaming OSM Loader (`osm.py`):** Uses streaming `xml.etree.ElementTree.iterparse` to ingest multi-gigabyte OpenStreetMap extracts without running out of memory. Parses vehicular tags (`highway`), speed limits (`maxspeed`), and one-way rules (`oneway`).
- **Multi-Criteria Weighting (`osm.py`):** Supports three cost weighting profiles:
  - `DISTANCE`: Minimizes geographic meters traveled.
  - `TRAVEL_TIME`: Accounts for civilian posted speed limits.
  - `EMERGENCY_TIME`: Applies emergency vehicle siren speed privileges and priority multipliers.
- **2D Spatial Hash Grid (`spatial.py`):** Buckets road vertices into spatial grid cells for $O(1)$ nearest-neighbor coordinate lookup. Computes orthogonal point projections onto road segments for GPS snapping.
- **Compiled Network Cache (`cache.py`):** Serializes topology-contracted graphs to compact `.eig.json` files with SHA-256 checksums to eliminate cold-start parsing overhead.
- **RFC 7946 GeoJSON Exporter (`geojson.py`):** Exports route paths as valid GeoJSON FeatureCollections for visualization in QGIS, Leaflet, Kepler.gl, and PostGIS.

### Layer 3 — Dynamic Conditions & Real-Time Disaster Mutations
**Location:** [`src/emergency_intelligence/events/`](../src/emergency_intelligence/events/)

- **Incident Domain Models (`incidents.py`):** Categorizes emergencies into 10 standard types (`STRUCTURE_FIRE`, `CARDIAC_ARREST`, `HAZMAT_SPILL`, etc.) across 4 urgency tiers (Echo, Delta, Bravo, Alpha).
- **Geometric Hazard Zones (`hazards.py`):** Defines 2D polygon boundaries (`HazardPolygon`) with severity categories and speed penalty multipliers. Implements pure-Python vector ray-casting and segment-polygon edge penetration detection.
- **Dynamic Graph Overlay (`mutations.py`):** `DynamicGraphView` provides a non-destructive layer over base road graphs. Overlays temporary closures (`ROAD_CLOSURE`) or disaster speed sinks (`SPEED_PENALTY`) with transactional rollback (`begin_transaction`, `rollback_transaction`) and Time-To-Live (TTL) automatic expiration.
- **In-Flight Vehicle Tracker & Detour Replanning (`inflight.py`):** Tracks in-transit emergency vehicles, detects newly emerged downstream route obstructions, and replans optimal detours in under 70 microseconds.
- **Federal Alert Ingestion (`alerts.py`):** Parses OASIS Common Alerting Protocol (CAP v1.2 / ITU-T X.1303 XML) and GeoJSON alert feeds, transforming polygons directly into active graph mutations.

### Layer 4 — Multi-Source Fleet Allocation & Catchment Partitioning
**Location:** [`src/emergency_intelligence/allocation/`](../src/emergency_intelligence/allocation/)

- **Fleet Management (`models.py`, `matcher.py`):** Tracks municipal apparatus (ALS/BLS ambulances, fire engines, ladder trucks, heavy rescue, hazmat units, battalion chiefs) across multiple station depots.
- **Multi-Source Voronoi Catchment (`catchment.py`):** Computes generalized multi-source Dijkstra partitions to allocate geographic service territories across municipal fire stations.
- **NFPA 1710 Response Isochrones (`catchment.py`):** Delineates travel-time frontiers for 240-second (4-minute) first-due turnout and 480-second (8-minute) full alarm assignments.
- **Apparatus Matching & Ranking (`matcher.py`):** Ranks available apparatus by travel time, vehicle capabilities, and speed factors to fulfill multi-unit dispatch assignments.

### Layer 5 — Emergency Intelligence & Policy Orchestration
**Location:** [`src/emergency_intelligence/intelligence/`](../src/emergency_intelligence/intelligence/)

- **Domain Contracts & Location Provenance (`contracts.py`):**
  - Isolates untrusted model proposals (`ProposedIncidentInterpretation`) from authoritative state.
  - Validates geographic ranges ($-180 \le \text{lon} \le 180$, $-90 \le \text{lat} \le 90$) and verifies numerical finiteness (`math.isfinite`) to reject `NaN` and `Inf`.
  - Tags location provenance (`VERIFIED_COORDINATES`, `APPROXIMATE_ADDRESS`, `CROSS_STREETS`, `UNKNOWN`).
  - Emits immutable `ValidatedIncidentContract`.
- **Deterministic Statutory Policy Engine (`policy.py`):**
  - Enforces authoritative municipal Standard Operating Procedures (SOPs) and NFPA 1710/1221 standards.
  - Statutory Apparatus Mandates: Structure fires require 2 Engines, 1 Ladder, 1 Chief, 1 ALS Ambulance; cardiac arrests require dual ALS Ambulance + Fire Engine turnout; hazmat spills require Hazmat containment units and trigger bridge/tunnel bans.
  - **Statutory Invariance:** Model proposals can augment apparatus but cannot remove mandatory requirements or downgrade critical urgency tiers.
- **Natural-Language Interpretation Interface (`interpreter.py`):**
  - Provider-independent abstraction (`EmergencyInterpreter`).
  - Input sanitization: control character stripping, length clamping $[3, 4000]$, and sensitive PII masking (phone numbers, SSNs, credit cards).
  - Adversarial prompt injection defense (`detect_adversarial_patterns` flags instruction override attempts and dispatch suppression).
- **Structured Model Adapter & Recovery Policy (`adapter.py`):**
  - Schema-constrained extraction (`StructuredModelAdapter`) adhering to JSON Schema Draft-07.
  - Bounded exponential backoff retry policy (`RetryPolicy`) with transient vs. permanent error classification.
  - Safe JSON repair (`extract_json_payload`): strips markdown code fences, handles conversational preambles, and **strictly rejects ambiguous outputs containing multiple candidate code fences**.
  - Decoupled `ModelProvider` ABC with deterministic `FakeModelProvider` for network-free offline testing.
- **Pipeline Orchestrator & Audit Trail (`orchestrator.py`):**
  - End-to-end coordination (`EmergencyIntelligenceOrchestrator`): Intake $\to$ Sanitization $\to$ Adapter $\to$ Contract Validation $\to$ Policy Evaluation $\to$ Fleet Allocation $\to$ Dynamic A* Routing.
  - Missing locations fail safe to `OrchestrationStatus.STAGED_AWAITING_LOCATION` with operator clarification prompts.
  - CAD manual geocode overrides validate numeric coordinates, verify active graph nodes, and record `operator_id` authorization.
  - Chronological, privacy-preserving audit trail with deterministic SHA-256 sequence hash (`audit_checksum`).

---

## End-to-End Orchestration Data Flow

```
   [Raw 911 Caller Narrative / Audio Transcript / CAD Alert]
                               │
                               ▼
   ┌────────────────────────────────────────────────────────┐
   │            Stage 1: Intake & Sanitization              │
   │  - Character length bounds enforcement [3, 4000]       │
   │  - Redaction of SSNs, credit cards, telephone numbers  │
   │  - Detection of adversarial prompt-injection patterns  │
   │  - Records Request ID and Intake in Audit Trail        │
   └───────────────────────────┬────────────────────────────┘
                               │
                               ▼
   ┌────────────────────────────────────────────────────────┐
   │      Stage 2: Schema-Constrained Model Adapter         │
   │            (StructuredModelAdapter)                    │
   │  - Formulates structured prompt with JSON schema       │
   │  - Bounded exponential backoff on transient errors     │
   │  - Fast-fails on permanent authentication errors       │
   │  - Strips markdown code fences; rejects multi-fences   │
   │  - Independent JSON schema & Enum validation           │
   │  - Records provider ID, retries, latency in Audit      │
   └───────────────────────────┬────────────────────────────┘
                               │
                               ▼  [ProposedIncidentInterpretation]
   ┌────────────────────────────────────────────────────────┐
   │        Stage 3: Deterministic Contract Boundary        │
   │            (validate_incident_proposal)                │
   │  - Finite float checks (rejects NaN, +Inf, -Inf)       │
   │  - Geographic coordinate range bounds validation       │
   │  - Provenance tagging (VERIFIED, ESTIMATED, UNKNOWN)   │
   │  - Detects under-triage contradictions                 │
   │  - Records contract status & issues count in Audit     │
   └───────────────────────────┬────────────────────────────┘
                               │
                               ▼  [ValidatedIncidentContract]
   ┌────────────────────────────────────────────────────────┐
   │        Stage 4: Authoritative Statutory Policy         │
   │             (EmergencyPolicyEngine)                    │
   │  - Pure, idempotent rule evaluation (zero mutations)   │
   │  - Enforces NFPA 1710 structure fire full alarms       │
   │  - Enforces cardiac dual ALS/Engine turnout mandate    │
   │  - Hazmat spill tunnel bans & containment mandates     │
   │  - Overrules model hallucinations and under-triages    │
   │  - Records mandated unit count and applied rule IDs    │
   └───────────────────────────┬────────────────────────────┘
                               │
                ┌──────────────┴──────────────┐
                ▼                             ▼
    [Valid Operable Coordinates]    [Missing Coordinates / Nodes]
                │                             │
                ▼                             ▼
   ┌─────────────────────────────┐ ┌─────────────────────────────┐
   │ Stage 5: Fleet Allocation & │ │ Staged Response & Operator  │
   │ Dynamic Detour Routing      │ │ Clarification Questions     │
   │ - DynamicGraphView closures │ │ - Staged at fire depots     │
   │ - Multi-criteria ranking    │ │ - Status: STAGED_AWAITING   │
   │ - Speed factor adjustments  │ │ - CAD manual coordinate     │
   │ - Topologically unreachable │ │   override with operator_id │
   │   fails safe to staged      │ │ - Records CAD override in   │
   │ - Status: DISPATCH_OPTIMIZED│ │   Audit Trail               │
   └─────────────┬───────────────┘ └──────────────┬──────────────┘
                 │                                │
                 └────────────────┬───────────────┘
                                  │
                                  ▼
   ┌────────────────────────────────────────────────────────┐
   │               Orchestration Result Boundary            │
   │  - Request ID & correlation metadata                   │
   │  - Immutable contract & authoritative policy directive│
   │  - Dispatched route paths & differentiated ETAs        │
   │  - Sanitized, chronological audit trail lines          │
   │  - Deterministic SHA-256 sequence audit_checksum       │
   │  - Simulation Boundary: ZERO live sirens or radio tx   │
   └────────────────────────────────────────────────────────┘
```

---

### Layer 6 — Discrete-Event Disaster Simulation & Evaluation Engine
**Location:** [`src/emergency_intelligence/simulation/`](../src/emergency_intelligence/simulation/) & [`src/emergency_intelligence/evaluation/`](../src/emergency_intelligence/evaluation/)

- **Discrete-Event Simulation Engine (`engine.py`, `timeline.py`):**
  - **Virtual Simulation Clock (`SimulationClock`):** Monotonically advancing virtual time container supporting deterministic, nanosecond-precise scheduling.
  - **Priority-Queue Event Scheduler (`SimulationTimeline`):** Min-heap event queue ordering event executions by `(timestamp, priority, sequence_id)`.
  - **Continuous Edge Kinematics (`VehicleSimState`):** Fractional edge traversal tracking (`traversed_fraction`), dynamic speed penalties, and event-driven position updates.
  - **Event Dispatcher Hooks:** Decoupled observers notifying registered handlers on incident arrivals, unit dispatch, en-route motion, hazard evolutions, and on-scene arrivals.
- **Reproducible Multi-Incident Scenarios (`scenarios.py`):**
  - Parameterized generator creating reproducible disaster environments with fixed RNG seeds.
  - Standard scenario suite: Baseline Single Incident, Cascading Urban Multi-Alarm, Mid-Flight Infrastructure Severance, and Progressive Inundation.
  - Station apparatus capacity modeling, secondary station fallback, and resource exhaustion queuing.
- **Quantitative Metrics & Algorithmic Profiler (`metrics.py`, `profiler.py`):**
  - **NFPA 1710 Compliance:** Linear percentile interpolation analyzing 240s first-due and 480s full-alarm response standard compliance.
  - **Topological Degradation Metrics:** Path Stability Index ($PSI$) measuring route divergence, and Detour Delay Degradation Factor ($DDF$) quantifying transit time inflation.
  - **Search Space Pruning Profiler:** Proves $A^*$ heuristic optimality and measures node/edge exploration savings against Dijkstra baselines.
  - **Latency Profiling:** High-resolution latency distribution measurements ($p50, p90, p95, p99, \max$) for routing computations.
- **Comparative Routing Strategy Harness (`benchmark.py`):**
  - Evaluates routing paradigms across identical disaster scenario instances:
    - `STATIC`: Fixed initial dispatch without in-flight adaptation (baseline).
    - `PERIODIC_POLLING`: Periodic recalculation at fixed discrete time intervals ($\Delta t$).
    - `REACTIVE_EVENT_DRIVEN`: Instantaneous recalculation triggered exclusively by network edge hazard mutations.
- **Multi-Format Simulation Exporter (`exporter.py`):**
  - **JSON Time-Series Telemetry:** Microsecond-precision event timeline and step-by-step vehicle kinematic trajectories.
  - **RFC 4180 Tabular CSV:** High-throughput metrics tables for statistical analysis.
  - **RFC 7946 Spatial GeoJSON:** Geographic LineString feature collections for visual GIS replay in QGIS, Kepler.gl, or Leaflet.

---

### Layer 7 — External Data & Geospatial Map Integration
**Location:** [`src/emergency_intelligence/external/`](../src/emergency_intelligence/external/)

- **Overpass POI Extraction (`overpass.py`):**
  - **Declarative Overpass QL Query Builder (`build_emergency_poi_query`):** Generates structured queries supporting geographic bounding boxes `(south, west, north, east)` and named administrative boundary searches.
  - **Granular Emergency POI Classification (`EmergencyPOIType`):** Catalogs hospitals, clinics, fire stations, ambulance stations, dispatch centers, police stations, helipads, and fire hydrants.
  - **Clinical Capability Extraction (`ClinicalCapability`):** Extracts specialized attributes: trauma care tiers (Levels 1 through 4), burn treatment units, pediatric emergency departments, stroke centers, cardiac catheterization labs, helipads, apparatus bay capacities, and emergency phone numbers.
  - **Offline-First HTTP Client (`fetch_or_load_overpass_pois`):** Implements deterministic file caching, fallback loading, and network error containment with timeout safeguards using Python's standard `urllib.request`.
- **Clinical & Facility Road Network Binding (`binding.py`):**
  - **Orthogonal Network Snapping (`bind_poi_to_network` / `bind_pois_to_network`):** Snaps off-road POI coordinates to the nearest traversable network node using `SpatialIndex` with customizable search radiuses.
  - **Spatial Error Isolation (`SpatialBindingError`):** Prevents individual disconnected facilities from causing batch ingestion failures.
  - **Automated Fleet Ingestion (`create_fleet_from_pois`):** Instantiates `FleetManager`, `EmergencyStation`, and apparatus rosters dynamically from real-world OSM fire and ambulance stations.
  - **Specialized Clinical Transport Router (`find_nearest_clinical_facility`):** Multi-criteria $A^*$ hospital transport router resolving the closest receiving medical center satisfying required clinical specialties (e.g., burn unit, pediatric care, Level 1 trauma).
- **Topographic Digital Elevation Models & Incline Routing (`elevation.py`):**
  - **NASA SRTM HGT Binary Ingestion (`SRTMTile`):** Big-endian 16-bit signed integer (`>h`) binary parser supporting SRTM1 (3601x3601) and SRTM3 (1201x1201) with microsecond offset indexing.
  - **Sub-Grid Bilinear Interpolation (`get_elevation`):** Continuous 4-point bilinear interpolation with automatic void-sample (`-32768`) detection, normalization, and terrestrial bounds clamping.
  - **3D Slope & Incline Kinematics (`calculate_slope_metrics`):** Computes horizontal distance, vertical delta $\Delta h$, true 3D Euclidean traversal length ($d_{3d} = \sqrt{d^2 + \Delta h^2}$), pitch angle, and slope grade ($\frac{\Delta h}{d} \times 100\%$).
  - **Apparatus Powertrain Incline Physics (`get_grade_speed_multiplier`):** Implements vehicle-specific velocity degradation and maximum passable climb thresholds (14% max climb for aerial ladder trucks vs 26% for ambulances), with steep descent runaway braking constraints.
  - **Dynamic Incline Routing View (`ElevationGraphView`):** Dynamic graph view adjusting traversal costs by grade multipliers and pruning impassable edges, enabling $A^*$ to divert heavy apparatus through gentler valleys.
- **Real-Time Hydrological & Meteorological Feeds (`hydrology.py`):**
  - **USGS Water Services Telemetry (`build_usgs_water_query_url`, `parse_usgs_water_response`):** Standard-library JSON parser for instantaneous river telemetry (`00065` gage height in feet, `00060` discharge streamflow in cfs) across national river stations.
  - **NWS River Flood Stage Classification (`USGSGaugeThresholds`, `FloodStage`):** Categorizes water levels into Action, Minor, Moderate, and Major stages with station-specific threshold tables.
  - **Open-Meteo Severe Weather Ingestion (`parse_open_meteo_response`):** Maps WMO storm codes, high-speed wind gusts ($\ge 75\text{ km/h}$), and torrential rain ($\ge 25\text{ mm/hr}$) to formal emergency alert levels (`WeatherAlertLevel`).
  - **Automated Dynamic Hazard Polygon Synthesis (`create_flood_inundation_polygon`, `create_weather_hazard_polygon`):** Generates 2D spherical buffer polygons around active flood gauges and storms, scaling radii from 250m to 1000m based on disaster severity.
  - **Environmental Graph Mutation Manager (`apply_environmental_hazards_to_graph`):** Spatially intersects flood/weather zones with road segments and applies atomic edge closures or speed penalties via `DynamicGraphView`.

---

## Safety Guarantees & Verification Boundaries

1. **Separation of Concerns:** Model proposals are treated as untrusted advice. The deterministic validation engine and statutory policy engine dictate authoritative dispatch, apparatus assignments, and routing constraints.
2. **Under-Triage Immunity:** An adversarial or erroneous model proposal cannot reduce a structure fire or cardiac arrest to a non-emergency tier, nor omit mandated apparatus companies.
3. **Audit Trail Privacy:** Audit logs record stage transitions, rule IDs, and retry counts, but strictly exclude caller names, phone numbers, SSNs, and raw narrative text.
4. **Tamper-Evident Sequence Integrity:** Every orchestration result exposes a deterministic SHA-256 digest (`audit_checksum`) computed over all joined audit trail entries.
5. **Decoupled Simulation Boundary:** All route computations, apparatus turnouts, and siren privileges are simulated in software. The system does not interface with physical emergency sirens, land mobile radio networks, or live CAD dispatch consoles.

---

## Technology Stack & Zero-Dependency Rule

| Component | Technology | Rationale |
|---|---|---|
| Language | Python 3.10+ (tested through 3.14) | Standard modern typing, dataclasses, pattern matching |
| Core Library | Python Standard Library | Zero external runtime dependencies; maximum portability |
| Data Ingestion | `xml.etree.ElementTree.iterparse`, `json` | Memory-efficient streaming of large OSM datasets |
| Graph Modeling | In-memory adjacency lists with `heapq` | Transparent, verifiable algorithmic implementations |
| Geometry | Pure-Python vector math & ray-casting | Complete independence from GDAL/GEOS/Shapely C-bindings |
| Testing | `pytest`, `pytest-cov` | Enforces strict $\ge 90\%$ statement and branch coverage |
