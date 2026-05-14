"""
versioning.py - Data versioning and rollback.

Provides:
- Create named versions/snapshots
- Compare versions (diff)
- Rollback to previous versions
- Branch management (like git)
- Merge versions
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from enum import Enum
import uuid
import time
import hashlib

import pandas as pd

from utils.db import db
from utils.logger import logger


class VersionStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    COMPARING = "comparing"


@dataclass
class DataVersion:
    version_id: str
    session_id: str
    version_number: int
    name: str
    description: str
    created_at: float
    created_by: str
    rows: int
    columns: List[str]
    checksum: str
    status: VersionStatus = VersionStatus.ACTIVE
    parent_version: Optional[str] = None


@dataclass
class VersionDiff:
    added_rows: int
    removed_rows: int
    modified_rows: int
    added_columns: List[str]
    removed_columns: List[str]
    changed_columns: List[str]
    row_changes: List[Dict[str, Any]]


def _ensure_tables():
    """Create versioning tables if not exists."""
    db.execute("""
        CREATE TABLE IF NOT EXISTS data_versions (
            id VARCHAR(36) PRIMARY KEY,
            session_id VARCHAR(36) NOT NULL,
            version_number INT NOT NULL,
            name VARCHAR(255),
            description TEXT,
            created_at DOUBLE NOT NULL,
            created_by VARCHAR(36) NOT NULL,
            rows INT NOT NULL,
            columns TEXT,
            checksum VARCHAR(64) NOT NULL,
            status VARCHAR(16) NOT NULL DEFAULT 'active',
            parent_version VARCHAR(36),
            file_path VARCHAR(512),
            INDEX idx_versions_session (session_id),
            INDEX idx_versions_number (session_id, version_number)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS version_branches (
            id VARCHAR(36) PRIMARY KEY,
            session_id VARCHAR(36) NOT NULL,
            name VARCHAR(255) NOT NULL,
            head_version VARCHAR(36) NOT NULL,
            created_at DOUBLE NOT NULL,
            created_by VARCHAR(36) NOT NULL,
            INDEX idx_branches_session (session_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def create_version(
    session_id: str,
    df: pd.DataFrame,
    created_by: str,
    name: Optional[str] = None,
    description: str = "",
    parent_version: Optional[str] = None,
) -> DataVersion:
    """Create a new version snapshot of the dataset."""
    _ensure_tables()

    existing = db.fetchone(
        """
        SELECT MAX(version_number) as max_v FROM data_versions WHERE session_id = ?
    """,
        (session_id,),
    )

    version_number = (existing["max_v"] or 0) + 1
    version_id = str(uuid.uuid4())
    now = time.time()

    columns = list(df.columns)
    rows = len(df)
    checksum = hashlib.md5(pd.util.hash_pandas_object(df).values.tobytes()).hexdigest()

    file_path = f"versions/{session_id}/v{version_number}_{checksum[:8]}.parquet"

    import os

    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    df.to_parquet(file_path, index=False)

    db.execute(
        """
        INSERT INTO data_versions 
        (id, session_id, version_number, name, description, created_at, created_by,
         rows, columns, checksum, status, parent_version, file_path)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
        (
            version_id,
            session_id,
            version_number,
            name or f"Version {version_number}",
            description,
            now,
            created_by,
            rows,
            ",".join(columns),
            checksum,
            VersionStatus.ACTIVE.value,
            parent_version,
            file_path,
        ),
    )

    logger.info(f"Version created: {version_id} session={session_id} v{version_number}")

    return DataVersion(
        version_id=version_id,
        session_id=session_id,
        version_number=version_number,
        name=name or f"Version {version_number}",
        description=description,
        created_at=now,
        created_by=created_by,
        rows=rows,
        columns=columns,
        checksum=checksum,
        status=VersionStatus.ACTIVE,
        parent_version=parent_version,
    )


def get_version(version_id: str) -> Optional[DataVersion]:
    """Get a specific version."""
    _ensure_tables()

    row = db.fetchone("SELECT * FROM data_versions WHERE id = ?", (version_id,))
    if not row:
        return None

    return _row_to_version(row)


def get_version_df(version_id: str) -> Optional[pd.DataFrame]:
    """Load a version's DataFrame from storage."""
    _ensure_tables()

    row = db.fetchone("SELECT file_path FROM data_versions WHERE id = ?", (version_id,))
    if not row or not row["file_path"]:
        return None

    try:
        import os

        if os.path.exists(row["file_path"]):
            return pd.read_parquet(row["file_path"])
    except Exception as e:
        logger.error(f"Failed to load version {version_id}: {e}")

    return None


def list_versions(session_id: str) -> List[DataVersion]:
    """List all versions for a session."""
    _ensure_tables()

    rows = db.fetchall(
        """
        SELECT * FROM data_versions 
        WHERE session_id = ?
        ORDER BY version_number DESC
    """,
        (session_id,),
    )

    return [_row_to_version(row) for row in rows]


def rollback_to_version(session_id: str, version_id: str, user_id: str) -> DataVersion:
    """Rollback session to a specific version."""
    df = get_version_df(version_id)
    if df is None:
        raise ValueError(f"Version {version_id} not found or corrupted")

    old_versions = db.fetchall(
        """
        SELECT id FROM data_versions WHERE session_id = ? AND id != ?
    """,
        (session_id, version_id),
    )

    for old in old_versions:
        db.execute(
            """
            UPDATE data_versions SET status = 'archived' WHERE id = ?
        """,
            (old["id"],),
        )

    new_version = create_version(
        session_id=session_id,
        df=df,
        created_by=user_id,
        name=f"Rollback to v{get_version(version_id).version_number}",
        description=f"Rolled back from current state to version {version_id}",
        parent_version=version_id,
    )

    logger.info(f"Rollback to version {version_id} for session {session_id}")

    return new_version


def compare_versions(version_a_id: str, version_b_id: str) -> VersionDiff:
    """Compare two versions and return the differences."""
    df_a = get_version_df(version_a_id)
    df_b = get_version_df(version_b_id)

    if df_a is None or df_b is None:
        raise ValueError("One or both versions not found")

    cols_a = set(df_a.columns)
    cols_b = set(df_b.columns)

    added_columns = sorted(cols_b - cols_a)
    removed_columns = sorted(cols_a - cols_b)
    common_cols = cols_a & cols_b

    changed_columns = []
    for col in common_cols:
        if not df_a[col].equals(df_b[col]):
            changed_columns.append(col)

    df_a_reset = df_a.reset_index(drop=True).fillna("__NA__").astype(str)
    df_b_reset = df_b.reset_index(drop=True).fillna("__NA__").astype(str)

    keys_a = df_a_reset.apply(tuple, axis=1)
    keys_b = df_b_reset.apply(tuple, axis=1)

    set_a = set(keys_a)
    set_b = set(keys_b)

    removed_rows = len(set_a - set_b)
    added_rows = len(set_b - set_a)

    common_keys = set_a & set_b
    modified_rows = sum(
        1
        for k in common_keys
        if keys_a[keys_a == k].index[0] != keys_b[keys_b == k].index[0]
        or not df_a_reset.loc[keys_a == k].equals(df_b_reset.loc[keys_b == k])
    )

    row_changes = []
    max_changes = 100

    for idx, (row_a, row_b) in enumerate(
        zip(df_a_reset.itertuples(index=False), df_b_reset.itertuples(index=False))
    ):
        if len(row_changes) >= max_changes:
            break
        if row_a != row_b:
            row_dict_a = dict(zip(df_a_reset.columns, row_a))
            row_dict_b = dict(zip(df_b_reset.columns, row_b))
            row_changes.append({"row": idx, "before": row_dict_a, "after": row_dict_b})

    return VersionDiff(
        added_rows=added_rows,
        removed_rows=removed_rows,
        modified_rows=modified_rows,
        added_columns=added_columns,
        removed_columns=removed_columns,
        changed_columns=sorted(changed_columns),
        row_changes=row_changes,
    )


def create_branch(
    session_id: str, name: str, head_version_id: str, created_by: str
) -> str:
    """Create a new branch from a version."""
    _ensure_tables()

    branch_id = str(uuid.uuid4())
    now = time.time()

    db.execute(
        """
        INSERT INTO version_branches (id, session_id, name, head_version, created_at, created_by)
        VALUES (?, ?, ?, ?, ?, ?)
    """,
        (branch_id, session_id, name, head_version_id, now, created_by),
    )

    return branch_id


def merge_versions(
    session_id: str,
    source_version_id: str,
    target_version_id: str,
    user_id: str,
    strategy: str = "source",  # source, target, manual
) -> DataVersion:
    """Merge changes from source version into target version."""
    df_source = get_version_df(source_version_id)
    df_target = get_version_df(target_version_id)

    if df_source is None or df_target is None:
        raise ValueError("Source or target version not found")

    if strategy == "source":
        merged_df = df_source.copy()
    elif strategy == "target":
        merged_df = df_target.copy()
    else:
        common_cols = list(set(df_source.columns) & set(df_target.columns))
        merged_df = df_source.copy()
        for col in common_cols:
            mask = merged_df[col].isna()
            merged_df.loc[mask, col] = df_target.loc[mask, col]

    merged_version = create_version(
        session_id=session_id,
        df=merged_df,
        created_by=user_id,
        name=f"Merged v{source_version_id[:8]} → v{target_version_id[:8]}",
        description=f"Merge from {source_version_id} to {target_version_id}",
        parent_version=target_version_id,
    )

    logger.info(f"Merged versions {source_version_id} and {target_version_id}")

    return merged_version


def _row_to_version(row: dict) -> DataVersion:
    """Convert database row to DataVersion."""
    return DataVersion(
        version_id=row["id"],
        session_id=row["session_id"],
        version_number=row["version_number"],
        name=row["name"] or f"Version {row['version_number']}",
        description=row["description"] or "",
        created_at=row["created_at"],
        created_by=row["created_by"],
        rows=row["rows"],
        columns=row["columns"].split(",") if row["columns"] else [],
        checksum=row["checksum"],
        status=VersionStatus(row["status"]),
        parent_version=row["parent_version"],
    )
