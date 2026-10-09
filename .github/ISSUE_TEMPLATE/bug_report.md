---
name: Bug Report
about: Create a report to help us improve the routing engine and data pipelines
title: "[BUG] <Brief summary of the issue>"
labels: ["bug", "triage"]
assignees: []
---

## Description
A clear and concise description of the bug.

## Steps to Reproduce
1. Graph setup / dataset used:
2. Query executed: `dijkstra(graph, source, destination)` or `astar(...)`
3. Unexpected behavior or crash:

```python
# Minimal reproducible example
from emergency_intelligence.graph import Graph, Node, Edge, dijkstra

graph = Graph()
# ...
```

## Expected Behavior
A clear and concise description of what you expected to happen.

## Actual Output / Traceback
```text
<Paste full traceback or unexpected return values here>
```

## Environment
- OS: [e.g. Windows 11, Ubuntu 22.04, macOS Sonoma]
- Python Version: [e.g. 3.10.12, 3.12.3]
- Git Commit / Release: [e.g. `main` branch, v0.2.0]

## Additional Context
Add any other context about the problem here (e.g. OSM Overpass query, geographic coordinates, edge case).
