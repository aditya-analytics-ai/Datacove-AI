"""
visual_pipeline_builder.py - visual pipeline construction service.

Provides a structured way to build transformation pipelines using a
node-based approach. Each step is a node with inputs, parameters, and outputs.

The frontend sends a graph of nodes, this service converts it to a
pipeline definition that can be executed.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from enum import Enum
import uuid


class NodeType(str, Enum):
    SOURCE = "source"
    TRANSFORM = "transform"
    FILTER = "filter"
    AGGREGATE = "aggregate"
    JOIN = "join"
    OUTPUT = "output"


class TransformType(str, Enum):
    # Cleaning
    REMOVE_DUPLICATES = "remove_duplicates"
    FILL_NULLS = "fill_nulls"
    DROP_COLUMNS = "drop_columns"
    RENAME_COLUMNS = "rename_columns"
    CHANGE_DTYPE = "change_dtype"
    TRIM_STRINGS = "trim_strings"
    FIND_REPLACE = "find_replace"
    OUTLIER_REMOVE = "outlier_remove"
    NORMALIZE = "normalize"

    # Filter
    FILTER_ROWS = "filter_rows"
    FILTER_NULLS = "filter_nulls"
    FILTER_DUPLICATES = "filter_duplicates"

    # Aggregate
    GROUP_BY = "group_by"
    PIVOT = "pivot"
    MELT = "melt"

    # Join
    MERGE_DATASET = "merge_dataset"

    # Derived
    DERIVED_COLUMN = "derived_column"
    LAG_COLUMNS = "lag_columns"
    ROLLING_STATS = "rolling_stats"


@dataclass
class NodeParameter:
    name: str
    label: str
    type: str  # string, number, boolean, select, multiselect, column, columns
    required: bool = True
    default: Any = None
    options: List[str] = field(default_factory=list)
    placeholder: str = ""
    help: str = ""


@dataclass
class PipelineNode:
    id: str
    type: NodeType
    transform: Optional[TransformType] = None
    label: str = ""
    params: Dict[str, Any] = field(default_factory=dict)
    columns: List[str] = field(default_factory=list)

    def to_pipeline_step(self) -> Dict[str, Any]:
        """Convert node to pipeline step format."""
        step = {"action": self.transform.value if self.transform else "unknown"}
        step["params"] = self.params.copy()
        return step


@dataclass
class VisualPipeline:
    id: str
    name: str
    owner_id: str
    nodes: List[PipelineNode] = field(default_factory=list)
    edges: List[Dict[str, str]] = field(
        default_factory=list
    )  # [{"from": "node_id", "to": "node_id"}]
    description: str = ""
    tags: List[str] = field(default_factory=list)
    created_at: float = 0
    updated_at: float = 0

    def to_pipeline_definition(self) -> Dict[str, Any]:
        """Convert visual pipeline to executable pipeline definition."""
        steps = []

        sorted_nodes = self._topological_sort()

        for node in sorted_nodes:
            if node.type == NodeType.TRANSFORM or node.type == NodeType.FILTER:
                steps.append(node.to_pipeline_step())
            elif node.type == NodeType.AGGREGATE:
                steps.append(node.to_pipeline_step())

        return {
            "name": self.name,
            "steps": steps,
        }

    def _topological_sort(self) -> List[PipelineNode]:
        """Sort nodes in execution order based on edges."""
        if not self.edges:
            return self.nodes

        node_map = {n.id: n for n in self.nodes}
        in_degree = {n.id: 0 for n in self.nodes}

        for edge in self.edges:
            if edge["from"] in in_degree and edge["to"] in in_degree:
                in_degree[edge["to"]] += 1

        queue = [n for n in self.nodes if in_degree[n.id] == 0]
        sorted_nodes = []

        while queue:
            node = queue.pop(0)
            sorted_nodes.append(node)

            for edge in self.edges:
                if edge["from"] == node.id:
                    target = edge["to"]
                    in_degree[target] -= 1
                    if in_degree[target] == 0:
                        queue.append(node_map[target])

        return sorted_nodes + [n for n in self.nodes if n not in sorted_nodes]

    def validate(self) -> Tuple[bool, List[str]]:
        """Validate the pipeline structure."""
        errors = []

        if not self.name:
            errors.append("Pipeline name is required")

        if not self.nodes:
            errors.append("Pipeline must have at least one node")

        transform_nodes = [n for n in self.nodes if n.type == NodeType.TRANSFORM]
        if not transform_nodes and len(self.nodes) > 1:
            errors.append("Pipeline must have at least one transform node")

        for edge in self.edges:
            if "from" not in edge or "to" not in edge:
                errors.append(f"Invalid edge: {edge}")
            elif edge["from"] not in [n.id for n in self.nodes]:
                errors.append(
                    f"Edge references non-existent source node: {edge['from']}"
                )
            elif edge["to"] not in [n.id for n in self.nodes]:
                errors.append(f"Edge references non-existent target node: {edge['to']}")

        return len(errors) == 0, errors


# ── Node templates for the UI ──────────────────────────────────────────────────

NODE_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "remove_duplicates": {
        "type": NodeType.TRANSFORM,
        "transform": TransformType.REMOVE_DUPLICATES,
        "label": "Remove Duplicates",
        "icon": "copy",
        "color": "#4CAF50",
        "params": [
            {
                "name": "subset",
                "label": "Columns",
                "type": "columns",
                "required": False,
                "placeholder": "All columns",
            },
            {
                "name": "keep",
                "label": "Keep",
                "type": "select",
                "options": ["first", "last"],
                "default": "first",
            },
        ],
    },
    "fill_nulls": {
        "type": NodeType.TRANSFORM,
        "transform": TransformType.FILL_NULLS,
        "label": "Fill Nulls",
        "icon": "edit",
        "color": "#2196F3",
        "params": [
            {
                "name": "columns",
                "label": "Columns",
                "type": "columns",
                "required": False,
            },
            {
                "name": "strategy",
                "label": "Strategy",
                "type": "select",
                "options": [
                    "constant",
                    "mean",
                    "median",
                    "mode",
                    "forward_fill",
                    "backward_fill",
                ],
                "default": "constant",
            },
            {
                "name": "value",
                "label": "Fill Value",
                "type": "string",
                "required": False,
            },
        ],
    },
    "drop_columns": {
        "type": NodeType.TRANSFORM,
        "transform": TransformType.DROP_COLUMNS,
        "label": "Drop Columns",
        "icon": "delete",
        "color": "#f44336",
        "params": [
            {
                "name": "columns",
                "label": "Columns to Drop",
                "type": "columns",
                "required": True,
            },
        ],
    },
    "rename_columns": {
        "type": NodeType.TRANSFORM,
        "transform": TransformType.RENAME_COLUMNS,
        "label": "Rename Columns",
        "icon": "edit",
        "color": "#9C27B0",
        "params": [
            {
                "name": "renames",
                "label": "Renames (old:new)",
                "type": "textarea",
                "placeholder": "old_name:new_name\nold_name2:new_name2",
            },
        ],
    },
    "change_dtype": {
        "type": NodeType.TRANSFORM,
        "transform": TransformType.CHANGE_DTYPE,
        "label": "Change Data Type",
        "icon": "settings",
        "color": "#FF9800",
        "params": [
            {"name": "column", "label": "Column", "type": "column", "required": True},
            {
                "name": "dtype",
                "label": "New Type",
                "type": "select",
                "options": ["string", "integer", "float", "datetime", "boolean"],
                "required": True,
            },
        ],
    },
    "trim_strings": {
        "type": NodeType.TRANSFORM,
        "transform": TransformType.TRIM_STRINGS,
        "label": "Trim Whitespace",
        "icon": "content_cut",
        "color": "#607D8B",
        "params": [
            {
                "name": "columns",
                "label": "Columns",
                "type": "columns",
                "required": False,
            },
        ],
    },
    "find_replace": {
        "type": NodeType.TRANSFORM,
        "transform": TransformType.FIND_REPLACE,
        "label": "Find & Replace",
        "icon": "find_replace",
        "color": "#795548",
        "params": [
            {"name": "column", "label": "Column", "type": "column", "required": True},
            {"name": "find", "label": "Find", "type": "string", "required": True},
            {
                "name": "replace",
                "label": "Replace With",
                "type": "string",
                "required": True,
            },
            {
                "name": "regex",
                "label": "Use Regex",
                "type": "boolean",
                "default": False,
            },
        ],
    },
    "outlier_remove": {
        "type": NodeType.TRANSFORM,
        "transform": TransformType.OUTLIER_REMOVE,
        "label": "Remove Outliers",
        "icon": "filter_alt",
        "color": "#E91E63",
        "params": [
            {
                "name": "columns",
                "label": "Columns",
                "type": "columns",
                "required": True,
            },
            {
                "name": "method",
                "label": "Method",
                "type": "select",
                "options": ["iqr", "zscore"],
                "default": "iqr",
            },
            {
                "name": "threshold",
                "label": "Threshold",
                "type": "number",
                "default": 1.5,
            },
        ],
    },
    "normalize": {
        "type": NodeType.TRANSFORM,
        "transform": TransformType.NORMALIZE,
        "label": "Normalize",
        "icon": "equalizer",
        "color": "#00BCD4",
        "params": [
            {
                "name": "columns",
                "label": "Columns",
                "type": "columns",
                "required": True,
            },
            {
                "name": "method",
                "label": "Method",
                "type": "select",
                "options": ["minmax", "zscore", "robust"],
                "default": "minmax",
            },
        ],
    },
    "filter_rows": {
        "type": NodeType.FILTER,
        "transform": TransformType.FILTER_ROWS,
        "label": "Filter Rows",
        "icon": "filter_alt",
        "color": "#3F51B5",
        "params": [
            {"name": "column", "label": "Column", "type": "column", "required": True},
            {
                "name": "operator",
                "label": "Operator",
                "type": "select",
                "options": [
                    "==",
                    "!=",
                    ">",
                    "<",
                    ">=",
                    "<=",
                    "contains",
                    "startswith",
                    "endswith",
                    "is_null",
                    "is_not_null",
                ],
                "required": True,
            },
            {"name": "value", "label": "Value", "type": "string", "required": False},
        ],
    },
    "filter_nulls": {
        "type": NodeType.FILTER,
        "transform": TransformType.FILTER_NULLS,
        "label": "Drop Nulls",
        "icon": "filter_alt",
        "color": "#673AB7",
        "params": [
            {
                "name": "columns",
                "label": "Columns",
                "type": "columns",
                "required": False,
            },
            {
                "name": "how",
                "label": "How",
                "type": "select",
                "options": ["any", "all"],
                "default": "any",
            },
        ],
    },
    "derived_column": {
        "type": NodeType.TRANSFORM,
        "transform": TransformType.DERIVED_COLUMN,
        "label": "Add Column",
        "icon": "add",
        "color": "#009688",
        "params": [
            {
                "name": "new_column",
                "label": "Column Name",
                "type": "string",
                "required": True,
            },
            {
                "name": "expression",
                "label": "Formula",
                "type": "textarea",
                "placeholder": "Price * Quantity",
                "required": True,
                "help": "Use column names directly. Available: +, -, *, /, np, pd",
            },
        ],
    },
    "group_by": {
        "type": NodeType.AGGREGATE,
        "transform": TransformType.GROUP_BY,
        "label": "Group By",
        "icon": "group_work",
        "color": "#FF5722",
        "params": [
            {
                "name": "group_columns",
                "label": "Group By Columns",
                "type": "columns",
                "required": True,
            },
            {
                "name": "aggregations",
                "label": "Aggregations",
                "type": "textarea",
                "placeholder": "sales:sum, quantity:mean, price:max",
                "help": "Format: column:agg (agg = sum, mean, median, min, max, count, std)",
            },
        ],
    },
    "lag_columns": {
        "type": NodeType.TRANSFORM,
        "transform": TransformType.LAG_COLUMNS,
        "label": "Add Lag Features",
        "icon": "schedule",
        "color": "#8BC34A",
        "params": [
            {"name": "column", "label": "Column", "type": "column", "required": True},
            {"name": "periods", "label": "Periods", "type": "number", "default": 1},
            {"name": "suffix", "label": "Suffix", "type": "string", "default": "_lag"},
        ],
    },
    "rolling_stats": {
        "type": NodeType.TRANSFORM,
        "transform": TransformType.ROLLING_STATS,
        "label": "Rolling Statistics",
        "icon": "timeline",
        "color": "#CDDC39",
        "params": [
            {"name": "column", "label": "Column", "type": "column", "required": True},
            {"name": "window", "label": "Window Size", "type": "number", "default": 7},
            {
                "name": "operations",
                "label": "Operations",
                "type": "multiselect",
                "options": ["mean", "std", "min", "max"],
                "default": ["mean"],
            },
        ],
    },
}


def get_node_templates() -> List[Dict[str, Any]]:
    """Get all available node templates for the UI."""
    return [
        {
            "id": key,
            "type": template["type"].value,
            "transform": template["transform"].value,
            "label": template["label"],
            "icon": template["icon"],
            "color": template["color"],
            "params": template["params"],
            "category": _get_category(template["type"]),
        }
        for key, template in NODE_TEMPLATES.items()
    ]


def _get_category(node_type: NodeType) -> str:
    """Get category for a node type."""
    mapping = {
        NodeType.TRANSFORM: "Transform",
        NodeType.FILTER: "Filter",
        NodeType.AGGREGATE: "Aggregate",
        NodeType.SOURCE: "Source",
        NodeType.OUTPUT: "Output",
        NodeType.JOIN: "Join",
    }
    return mapping.get(node_type, "Other")


def parse_visual_pipeline(data: Dict[str, Any], owner_id: str) -> VisualPipeline:
    """Parse frontend visual pipeline data into a VisualPipeline object."""
    pipeline = VisualPipeline(
        id=data.get("id", str(uuid.uuid4())),
        name=data.get("name", "Untitled Pipeline"),
        owner_id=owner_id,
        description=data.get("description", ""),
        tags=data.get("tags", []),
        created_at=data.get("created_at", 0),
        updated_at=data.get("updated_at", 0),
    )

    for node_data in data.get("nodes", []):
        node = PipelineNode(
            id=node_data["id"],
            type=NodeType(node_data.get("type", "transform")),
            transform=TransformType(node_data["transform"])
            if "transform" in node_data
            else None,
            label=node_data.get("label", ""),
            params=node_data.get("params", {}),
            columns=node_data.get("columns", []),
        )
        pipeline.nodes.append(node)

    pipeline.edges = data.get("edges", [])

    return pipeline
