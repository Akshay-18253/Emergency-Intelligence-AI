# Emergency Intelligence AI — System Architecture

> **Status:** All core foundational architectural layers (Phases 1 through 5) are **fully implemented and verified**.
> Core library has **zero external runtime dependencies** (100% Python standard library).
> **444 unit tests passing with 95.40% statement and branch coverage.**

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
│  LAYER 6: SIMULATION & QUANTITATIVE EVALUATION [PHASE 6 — NEXT]        │
│  ├── Reproducible Disaster Response Benchmark Scenarios                │
│  ├── Quantitative Rerouting Quality Metrics (ETAs, pruning ratios)     │
│  └── Real-World vs Simulation Boundary Verification                    │
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
