# Architecture

> **Status:** This document describes both the current (Day 1) implementation
> and the long-term architectural vision. Components marked **[FUTURE]** do
> not exist yet. Do not treat them as implemented.

---

## Guiding Principle

> AI should help interpret emergency context and formulate routing
> objectives or constraints, while deterministic and testable algorithms
> should perform route computation wherever appropriate.

This separation between **AI reasoning**, **deterministic computation**,
**data**, and **evaluation** is the architectural foundation of the project.
It produces a system that is explainable, reproducible, and testable.

---

## System Overview

```
User / Emergency Input
        │
        ▼
┌───────────────────────────┐
│  Emergency Intelligence   │   [FUTURE]
│  / AI Reasoning Layer     │
└─────────────┬─────────────┘
              │  structured objectives + constraints
              ▼
┌───────────────────────────┐
│  Dynamic Conditions       │   [FUTURE]
│  / Event Processing       │
└─────────────┬─────────────┘
              │
              ▼
┌───────────────────────────┐
│  Routing Engine           │   ← DAY 1: Dijkstra implemented
│  Dijkstra / A*            │
└─────────────┬─────────────┘
              │
              ▼
┌───────────────────────────┐
│  Road Network / Graph     │   ← DAY 1: In-memory graph model
│  OSM / open datasets      │
└─────────────┬─────────────┘
              │
              ▼
         Candidate Route
              │
              ▼
┌───────────────────────────┐
│  Simulation & Evaluation  │   [FUTURE]
└───────────────────────────┘
```

---

## Layer 1 — Data Layer

**Responsibility**

Store, load, and expose road network data in a form the routing engine
can consume.

**Current state (Day 1)**

An in-memory directed weighted graph built from Python objects.
Graph topology is defined in code, not loaded from an external dataset.

**Future inputs**

- OpenStreetMap PBF / GeoJSON exports
- Parsed road segments with geometry and attributes
- Facility datasets (hospitals, fire stations, police)

**Future outputs**

- `Graph` object populated from real road data
- Node metadata (coordinates, labels, facility type)
- Edge metadata (road type, speed limit, access restrictions)

**Design considerations**

- The data layer should be replaceable without changing the routing engine.
- OSM integration should be isolated behind a loader interface.
- Node coordinates are not required for Dijkstra but will be needed for A\*.

---

## Layer 2 — Road Graph Layer

**Responsibility**

Represent the road network as a directed weighted graph.
Provide efficient adjacency queries to the routing engine.

**Current state (Milestone 2)**

- `Node`: an intersection or named location with optional 2D spatial coordinates `(x, y)` and convenience properties.
- `Edge`: a directed connection between two nodes with a non-negative traversal cost.
- `Graph`: adjacency-list representation of the directed weighted graph.

**Future inputs**

- Parsed road-network data from the data layer.
- Dynamic event updates (edge cost modifications, edge removal).

**Future outputs**

- Neighbour lists for a given node.
- Modified graphs reflecting current dynamic conditions.

**Design considerations**

- The graph is directed: A → B does not imply B → A.
- Edge cost is abstract on Day 1 (a numerical value). Future phases will
  assign semantic meaning: travel time, congestion cost, risk score,
  emergency penalty, or composite cost.
- Future: node coordinates will enable heuristic-based algorithms (A\*).

---

## Layer 3 — Routing Engine

**Responsibility**

Compute the least-cost path between a source and a destination,
subject to constraints provided by the intelligence layer.

**Current state (Milestone 2)**

- Manual implementation of Dijkstra's algorithm using Python's `heapq`.
- Manual implementation of the A\* heuristic search algorithm with admissible heuristics (Euclidean, Manhattan, Zero).
- `RouteResult` captures path, total cost, reachability, nodes explored, and execution time in ms.
- Comparative benchmarking module (`compare_algorithms`) and synthetic grid generator (`create_grid_network`).

**Future inputs**

- Structured routing objectives (minimise travel time, avoid certain road types).
- Routing constraints (avoid flooded roads, prefer hospital access routes).
- Modified graph reflecting dynamic conditions.

**Future outputs**

- Optimal path (ordered list of node IDs).
- Total path cost.
- Nodes explored (for benchmarking).
- Execution time (for benchmarking).

**Design considerations**

- Dijkstra is correct for non-negative weighted graphs.
- A\* will be introduced later for heuristic-guided search. It requires
  node coordinates and an admissible heuristic.
- The routing engine must remain decoupled from the AI layer.
  It accepts only structured parameters, not natural language.

---

## Layer 4 — Dynamic Conditions [FUTURE]

**Responsibility**

Modify graph edge costs or availability in response to real-time events.
Trigger rerouting when conditions change significantly.

**Future inputs**

- Event streams: accidents, road closures, congestion updates.
- Emergency service broadcasts.

**Future outputs**

- Modified `Graph` or delta updates to the routing engine.
- Rerouting requests when a current route becomes invalid.

**Design considerations**

- Events must be clearly typed and timestamped.
- The routing engine should be re-runnable after any graph modification.
- Rerouting latency is a key evaluation metric.

---

## Layer 5 — Emergency Intelligence [FUTURE]

**Responsibility**

Interpret natural-language or structured emergency context.
Transform it into structured routing objectives and constraints
that the routing engine can consume.

**Future inputs**

- Natural-language emergency descriptions ("severe chest pain, nearest cardiac unit").
- Structured emergency type codes.
- Urgency indicators.

**Future outputs**

- Emergency classification (medical / fire / police / hazmat / SAR).
- Priority level (critical / high / moderate / low).
- Destination type (cardiac unit / trauma centre / fire station / etc.).
- Routing objective (minimise time / minimise risk / avoid certain roads).
- Constraints (avoid closures, prefer certain road classes).

**Design considerations**

- The AI layer must NOT compute routes directly.
- Its output must be a structured, serialisable object that the routing
  engine can consume.
- This makes the AI contribution testable, replaceable, and auditable.
- LLM integration should be isolated behind a well-defined interface.

---

## Layer 6 — Simulation and Evaluation [FUTURE]

**Responsibility**

Define reproducible emergency scenarios.
Evaluate routing strategies against quantitative metrics.
Support comparative analysis of algorithmic approaches.

**Future inputs**

- Scenario definitions (emergency type, location, time, events).
- Multiple routing strategies to compare.

**Future outputs**

- Metrics per scenario: route cost, travel time, rerouting latency,
  nodes explored, memory usage, route stability.
- Comparative reports across algorithms and strategies.

**Design considerations**

- Scenarios must be deterministic and reproducible.
- Metrics must be objective and measurable.
- This layer is critical for research credibility.

---

## Layer 7 — API [FUTURE]

**Responsibility**

Expose routing capabilities over HTTP.
Allow programmatic access to the routing engine.

**Design considerations**

- The API must be a thin layer above the routing engine.
- It must not contain routing logic.
- Must be documented, versioned, and testable.

---

## Layer 8 — User Interface [FUTURE]

**Responsibility**

Provide a human-facing interface for demonstrating system capabilities.

**Design considerations**

- The UI should reflect actual system capabilities.
- It should not create the impression of features that do not exist.
- A map-based UI requires node coordinates (not available on Day 1).

---

## Architecture Decision Log

| Decision | Rationale |
|---|---|
| Manual Dijkstra implementation | Demonstrates algorithmic correctness before introducing libraries. Enables line-level understanding and testing. |
| Adjacency-list graph representation | Efficient for sparse graphs. Road networks are sparse by nature. |
| `RouteResult` return type | Captures path, cost, and reachability in one structured object. Makes tests expressive. |
| Zero runtime dependencies (Day 1) | Reduces surface area. Ensures the foundation is self-contained. |
| Directed graph | Road networks have one-way streets. Undirected graphs would be incorrect for this domain. |
| Non-negative edge cost invariant | Required by Dijkstra's correctness proof. Enforced in `Edge.__post_init__`. |
