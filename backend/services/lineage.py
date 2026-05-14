"""
lineage.py - Data lineage tracking.

Tracks the flow of data through transformations, showing:
- Column-level lineage (which columns came from where)
- Transformation history
- Data flow between sessions
- Impact analysis
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set
from enum import Enum
import uuid
import time
import hashlib

import pandas as pd

from utils.db import db
from utils.logger import logger


class NodeType(str, Enum):
    SOURCE = "source"
    TRANSFORM = "transform"
    JOIN = "join"
    AGGREGATE = "aggregate"
    FILTER = "filter"
    DERIVED = "derived"


@dataclass
class LineageNode:
    id: str
    node_type: NodeType
    name: str
    session_id: str
    version: int
    inputs: List[str] = field(default_factory=list)  # Node IDs
    outputs: List[str] = field(default_factory=list)  # Column names
    params: Dict[str, Any] = field(default_factory=dict)
    created_at: float
    created_by: Optional[str] = None


@dataclass
class LineageEdge:
    id: str
    source_node: str
    target_node: str
    source_column: str
    target_column: str
    transformation: Optional[str] = None  # e.g., "renamed", "derived", "cast"


@dataclass
class ColumnLineage:
    column_name: str
    source_columns: List[str]
    transformations: List[str]
    root_source: str  # Original data source


def _ensure_tables():
    """Create lineage tables if not exists."""
    db.execute("""
        CREATE TABLE IF NOT EXISTS lineage_nodes (
            id VARCHAR(36) PRIMARY KEY,
            node_type VARCHAR(32) NOT NULL,
            name VARCHAR(255) NOT NULL,
            session_id VARCHAR(36) NOT NULL,
            version INT NOT NULL,
            inputs TEXT,
            outputs TEXT,
            params TEXT,
            created_at DOUBLE NOT NULL,
            created_by VARCHAR(36),
            INDEX idx_nodes_session (session_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS lineage_edges (
            id VARCHAR(36) PRIMARY KEY,
            source_node VARCHAR(36) NOT NULL,
            target_node VARCHAR(36) NOT NULL,
            source_column VARCHAR(255) NOT NULL,
            target_column VARCHAR(255) NOT NULL,
            transformation VARCHAR(255),
            created_at DOUBLE NOT NULL,
            INDEX idx_edges_source (source_node),
            INDEX idx_edges_target (target_node)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS lineage_graphs (
            id VARCHAR(36) PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            owner_id VARCHAR(36) NOT NULL,
            workspace_id VARCHAR(36),
            root_session_id VARCHAR(36) NOT NULL,
            created_at DOUBLE NOT NULL,
            updated_at DOUBLE NOT NULL,
            INDEX idx_graphs_owner (owner_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def record_transformation(
    session_id: str,
    version: int,
    action: str,
    params: Dict[str, Any],
    before_columns: List[str],
    after_columns: List[str],
    user_id: Optional[str] = None,
) -> str:
    """Record a transformation in the lineage graph."""
    _ensure_tables()

    node_id = str(uuid.uuid4())
    now = time.time()

    inputs = []
    for col in before_columns:
        edge_id = str(uuid.uuid4())
        source_edge = db.fetchone(
            """
            SELECT source_node FROM lineage_edges WHERE target_column = ?
            ORDER BY created_at DESC LIMIT 1
        """,
            (col,),
        )
        if source_edge:
            inputs.append(source_edge["source_node"])

            db.execute(
                """
                INSERT INTO lineage_edges (id, source_node, target_node, source_column, target_column, transformation, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (edge_id, source_edge["source_node"], node_id, col, col, action, now),
            )

    outputs = []
    for col in after_columns:
        if col not in before_columns:
            outputs.append(col)
            edge_id = str(uuid.uuid4())
            db.execute(
                """
                INSERT INTO lineage_edges (id, source_node, target_node, source_column, target_column, transformation, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (edge_id, node_id, "", col, col, "created", now),
            )
        else:
            outputs.append(col)

    node_type = _get_node_type(action)

    db.execute(
        """
        INSERT INTO lineage_nodes 
        (id, node_type, name, session_id, version, inputs, outputs, params, created_at, created_by)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
        (
            node_id,
            node_type.value,
            action,
            session_id,
            version,
            str(inputs),
            str(outputs),
            str(params),
            now,
            user_id,
        ),
    )

    logger.info(f"Lineage node recorded: {node_id} action={action}")

    return node_id


def _get_node_type(action: str) -> NodeType:
    """Map action to node type."""
    type_mapping = {
        "remove_duplicates": NodeType.FILTER,
        "fill_nulls": NodeType.TRANSFORM,
        "drop_columns": NodeType.FILTER,
        "rename_columns": NodeType.TRANSFORM,
        "change_dtype": NodeType.TRANSFORM,
        "trim_strings": NodeType.TRANSFORM,
        "find_replace": NodeType.TRANSFORM,
        "outlier_remove": NodeType.FILTER,
        "normalize": NodeType.TRANSFORM,
        "filter_rows": NodeType.FILTER,
        "filter_nulls": NodeType.FILTER,
        "derived_column": NodeType.DERIVED,
        "group_by": NodeType.AGGREGATE,
        "merge": NodeType.JOIN,
        "pivot": NodeType.AGGREGATE,
        "melt": NodeType.TRANSFORM,
    }
    return type_mapping.get(action, NodeType.TRANSFORM)


def get_column_lineage(session_id: str, column: str) -> ColumnLineage:
    """Get the full lineage for a specific column."""
    _ensure_tables()

    root_source = None
    transformations = []
    source_columns = []

    current_column = column
    visited_nodes: Set[str] = set()

    while True:
        edge = db.fetchone(
            """
            SELECT * FROM lineage_edges 
            WHERE target_column = ? AND target_node != ''
            ORDER BY created_at ASC
        """,
            (current_column,),
        )

        if not edge:
            if not root_source:
                root_source = current_column
            break

        if edge["source_node"] in visited_nodes:
            break
        visited_nodes.add(edge["source_node"])

        transformations.append(edge["transformation"])
        source_columns.append(edge["source_column"])

        node = db.fetchone(
            "SELECT * FROM lineage_nodes WHERE id = ?", (edge["source_node"],)
        )
        if node:
            current_column = (
                node["outputs"].strip("[]").replace("'", "").split(",")[0]
                if node["outputs"]
                else ""
            )

        if not current_column or current_column == "None":
            root_source = current_column
            break

    return ColumnLineage(
        column_name=column,
        source_columns=source_columns,
        transformations=transformations,
        root_source=root_source or column,
    )


def get_session_lineage(session_id: str) -> Dict[str, Any]:
    """Get the complete lineage graph for a session."""
    _ensure_tables()

    nodes = db.fetchall(
        """
        SELECT * FROM lineage_nodes 
        WHERE session_id = ?
        ORDER BY version ASC
    """,
        (session_id,),
    )

    edges = db.fetchall(
        """
        SELECT le.* FROM lineage_edges le
        JOIN lineage_nodes ln ON le.target_node = ln.id
        WHERE ln.session_id = ?
    """,
        (session_id,),
    )

    import json

    lineage_nodes = []
    for node in nodes:
        lineage_nodes.append(
            {
                "id": node["id"],
                "type": node["node_type"],
                "name": node["name"],
                "version": node["version"],
                "params": json.loads(node["params"]) if node["params"] else {},
                "created_at": node["created_at"],
            }
        )

    lineage_edges = []
    for edge in edges:
        lineage_edges.append(
            {
                "id": edge["id"],
                "source": edge["source_node"],
                "target": edge["target_node"],
                "source_column": edge["source_column"],
                "target_column": edge["target_column"],
                "transformation": edge["transformation"],
            }
        )

    return {
        "nodes": lineage_nodes,
        "edges": lineage_edges,
        "total_nodes": len(lineage_nodes),
        "total_edges": len(lineage_edges),
    }


def impact_analysis(session_id: str, column: str) -> Dict[str, Any]:
    """
    Perform impact analysis: what downstream operations/sessions
    depend on this column?
    """
    _ensure_tables()

    affected = []
    visited_edges: Set[str] = set()
    queue = [column]

    while queue:
        current_col = queue.pop(0)

        edges = db.fetchall(
            """
            SELECT * FROM lineage_edges 
            WHERE source_column = ?
        """,
            (current_col,),
        )

        for edge in edges:
            if edge["id"] in visited_edges:
                continue
            visited_edges.add(edge["id"])

            node = db.fetchone(
                "SELECT * FROM lineage_nodes WHERE id = ?", (edge["target_node"])
            )
            if node:
                affected.append(
                    {
                        "session_id": node["session_id"],
                        "node_id": node["id"],
                        "action": node["name"],
                        "version": node["version"],
                        "column_impacted": edge["target_column"],
                    }
                )

                for out_col in node["outputs"].strip("[]").replace("'", "").split(","):
                    if out_col and out_col != "None":
                        queue.append(out_col)

    return {
        "source_column": column,
        "affected_operations": affected,
        "total_affected": len(affected),
    }


def create_lineage_graph(
    name: str, owner_id: str, root_session_id: str, workspace_id: Optional[str] = None
) -> str:
    """Create a named lineage graph (snapshot)."""
    _ensure_tables()

    graph_id = str(uuid.uuid4())
    now = time.time()

    db.execute(
        """
        INSERT INTO lineage_graphs (id, name, owner_id, workspace_id, root_session_id, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """,
        (graph_id, name, owner_id, workspace_id, root_session_id, now, now),
    )

    return graph_id


def list_lineage_graphs(owner_id: str) -> List[Dict[str, Any]]:
    """List all lineage graphs for a user."""
    _ensure_tables()

    rows = db.fetchall(
        """
        SELECT * FROM lineage_graphs 
        WHERE owner_id = ?
        ORDER BY updated_at DESC
    """,
        (owner_id,),
    )

    return [dict(r) for r in rows]
