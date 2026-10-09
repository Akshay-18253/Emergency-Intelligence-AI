"""
Compiled road network cache serialization and integrity verification.

Enables instant (< 50 ms) loading of pre-processed, topologically contracted,
and speed-weighted city networks with SHA-256 checksum verification.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from emergency_intelligence.graph.models import Edge, Graph, Node

CACHE_SCHEMA_VERSION = "1.0.0"


def compute_file_checksum(file_path: Union[str, Path]) -> str:
    """Compute the hexadecimal SHA-256 checksum of a file on disk.

    Parameters
    ----------
    file_path:
        Path to the target file.

    Returns
    -------
    str
        Hexadecimal SHA-256 hash string.
    """
    path = Path(file_path)
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def _compute_payload_hash(nodes_data: List[Dict[str, Any]], edges_data: List[Dict[str, Any]]) -> str:
    """Compute deterministic SHA-256 hash over nodes and edges structures."""
    hasher = hashlib.sha256()
    payload_str = json.dumps({"nodes": nodes_data, "edges": edges_data}, sort_keys=True)
    hasher.update(payload_str.encode("utf-8"))
    return hasher.hexdigest()


def save_graph_cache(
    graph: Graph,
    file_path: Union[str, Path],
    source_checksum: Optional[str] = None,
) -> Path:
    """Serialize a :class:`~emergency_intelligence.graph.models.Graph` into a compiled cache file.

    Parameters
    ----------
    graph:
        The graph instance to serialize.
    file_path:
        Destination file path (e.g. ``"network.eig.json"``).
    source_checksum:
        Optional SHA-256 hash of the raw OSM source dataset for cache invalidation.

    Returns
    -------
    Path
        Path to the created cache file.
    """
    out_path = Path(file_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    nodes_list: List[Dict[str, Any]] = []
    for nid in graph.node_ids():
        node = graph.get_node(nid)
        nodes_list.append({
            "id": node.node_id,
            "label": node.label,
            "coordinates": list(node.coordinates) if node.coordinates else None,
        })

    edges_list: List[Dict[str, Any]] = []
    for u in graph.node_ids():
        for edge in graph.get_neighbors(u):
            edges_list.append({
                "source": edge.source_id,
                "destination": edge.destination_id,
                "cost": edge.cost,
                "attributes": edge.attributes,
            })

    payload_hash = _compute_payload_hash(nodes_list, edges_list)

    cache_document: Dict[str, Any] = {
        "schema_version": CACHE_SCHEMA_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_checksum": source_checksum,
        "payload_sha256": payload_hash,
        "node_count": len(nodes_list),
        "edge_count": len(edges_list),
        "nodes": nodes_list,
        "edges": edges_list,
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(cache_document, f, indent=2)

    return out_path


def load_graph_cache(
    file_path: Union[str, Path],
    verify_checksum: bool = True,
) -> Tuple[Graph, Dict[str, Any]]:
    """Load a compiled road network cache from disk into a :class:`Graph`.

    Parameters
    ----------
    file_path:
        Path to the compiled cache file.
    verify_checksum:
        Whether to enforce SHA-256 payload integrity checking.

    Returns
    -------
    Tuple[Graph, Dict[str, Any]]
        A tuple of ``(graph, metadata_dict)``.

    Raises
    ------
    FileNotFoundError
        If *file_path* does not exist.
    ValueError
        If the file has an unsupported schema version, invalid JSON, or a corrupted checksum.
    """
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"Cache file not found: {path.resolve()}")

    with open(path, "r", encoding="utf-8") as f:
        try:
            doc = json.load(f)
        except json.JSONDecodeError as err:
            raise ValueError(f"Invalid JSON in cache file: {err}") from err

    if not isinstance(doc, dict):
        raise ValueError("Invalid cache structure: expected a JSON object.")

    version = doc.get("schema_version")
    if version != CACHE_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported cache schema version {version!r}. Expected {CACHE_SCHEMA_VERSION!r}."
        )

    nodes_list = doc.get("nodes", [])
    edges_list = doc.get("edges", [])

    if verify_checksum:
        expected_hash = doc.get("payload_sha256")
        actual_hash = _compute_payload_hash(nodes_list, edges_list)
        if expected_hash != actual_hash:
            raise ValueError(
                f"Corrupted cache file: SHA-256 payload checksum mismatch. "
                f"Expected {expected_hash}, got {actual_hash}."
            )

    graph = Graph()

    for n_data in nodes_list:
        coords = None
        if n_data.get("coordinates") is not None:
            c = n_data["coordinates"]
            coords = (float(c[0]), float(c[1]))
        graph.add_node(
            Node(
                node_id=str(n_data["id"]),
                label=n_data.get("label"),
                coordinates=coords,
            )
        )

    for e_data in edges_list:
        graph.add_edge(
            Edge(
                source_id=str(e_data["source"]),
                destination_id=str(e_data["destination"]),
                cost=float(e_data["cost"]),
                attributes=dict(e_data.get("attributes", {})),
            )
        )

    metadata: Dict[str, Any] = {
        "schema_version": version,
        "created_at": doc.get("created_at"),
        "source_checksum": doc.get("source_checksum"),
        "payload_sha256": doc.get("payload_sha256"),
        "node_count": len(nodes_list),
        "edge_count": len(edges_list),
    }

    return graph, metadata
