"""
workspaces.py - Multi-user workspace management.

Workspaces allow teams to share datasets, pipelines, and collaborate
on data cleaning projects.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import uuid
import time

from utils.db import db
from utils.logger import logger


@dataclass
class Workspace:
    id: str
    name: str
    description: str
    owner_id: str
    created_at: float
    updated_at: float
    settings: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkspaceMember:
    user_id: str
    workspace_id: str
    role: str  # owner, admin, member, viewer
    joined_at: float


def _ensure_tables():
    """Create workspace tables if not exists."""
    db.execute("""
        CREATE TABLE IF NOT EXISTS workspaces (
            id VARCHAR(36) PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            description TEXT,
            owner_id VARCHAR(36) NOT NULL,
            settings TEXT,
            created_at DOUBLE NOT NULL,
            updated_at DOUBLE NOT NULL,
            INDEX idx_workspaces_owner (owner_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS workspace_members (
            user_id VARCHAR(36) NOT NULL,
            workspace_id VARCHAR(36) NOT NULL,
            role VARCHAR(16) NOT NULL DEFAULT 'member',
            joined_at DOUBLE NOT NULL,
            PRIMARY KEY (user_id, workspace_id),
            INDEX idx_workspace_members_workspace (workspace_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS workspace_invites (
            id VARCHAR(36) PRIMARY KEY,
            workspace_id VARCHAR(36) NOT NULL,
            email VARCHAR(255) NOT NULL,
            role VARCHAR(16) NOT NULL DEFAULT 'member',
            token VARCHAR(64) NOT NULL,
            expires_at DOUBLE NOT NULL,
            used_at DOUBLE,
            created_by VARCHAR(36) NOT NULL,
            INDEX idx_invites_workspace (workspace_id),
            INDEX idx_invites_token (token)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def create_workspace(name: str, owner_id: str, description: str = "") -> Workspace:
    """Create a new workspace."""
    _ensure_tables()

    workspace_id = str(uuid.uuid4())
    now = time.time()

    db.execute(
        """
        INSERT INTO workspaces (id, name, description, owner_id, settings, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """,
        (workspace_id, name, description, owner_id, "{}", now, now),
    )

    db.execute(
        """
        INSERT INTO workspace_members (user_id, workspace_id, role, joined_at)
        VALUES (?, ?, ?, ?)
    """,
        (owner_id, workspace_id, "owner", now),
    )

    logger.info(f"Workspace created: {workspace_id} by {owner_id}")

    return Workspace(
        id=workspace_id,
        name=name,
        description=description,
        owner_id=owner_id,
        created_at=now,
        updated_at=now,
    )


def get_workspace(workspace_id: str) -> Optional[Workspace]:
    """Get workspace by ID."""
    _ensure_tables()

    row = db.fetchone("SELECT * FROM workspaces WHERE id = ?", (workspace_id,))
    if not row:
        return None

    import json

    return Workspace(
        id=row["id"],
        name=row["name"],
        description=row["description"] or "",
        owner_id=row["owner_id"],
        settings=json.loads(row["settings"] or "{}"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def list_user_workspaces(user_id: str) -> List[Workspace]:
    """List all workspaces a user has access to."""
    _ensure_tables()

    rows = db.fetchall(
        """
        SELECT w.* FROM workspaces w
        JOIN workspace_members wm ON w.id = wm.workspace_id
        WHERE wm.user_id = ?
        ORDER BY w.updated_at DESC
    """,
        (user_id,),
    )

    import json

    workspaces = []
    for row in rows:
        workspaces.append(
            Workspace(
                id=row["id"],
                name=row["name"],
                description=row["description"] or "",
                owner_id=row["owner_id"],
                settings=json.loads(row["settings"] or "{}"),
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
        )

    return workspaces


def update_workspace(
    workspace_id: str,
    user_id: str,
    name: Optional[str] = None,
    description: Optional[str] = None,
    settings: Optional[Dict] = None,
) -> bool:
    """Update workspace settings. Only owner/admins can update."""
    _ensure_tables()

    if not can_admin_workspace(user_id, workspace_id):
        return False

    updates = []
    params = []

    if name is not None:
        updates.append("name = ?")
        params.append(name)
    if description is not None:
        updates.append("description = ?")
        params.append(description)
    if settings is not None:
        import json

        updates.append("settings = ?")
        params.append(json.dumps(settings))

    updates.append("updated_at = ?")
    params.append(time.time())

    params.append(workspace_id)

    db.execute(
        f"UPDATE workspaces SET {', '.join(updates)} WHERE id = ?", tuple(params)
    )
    return True


def delete_workspace(workspace_id: str, user_id: str) -> bool:
    """Delete workspace. Only owner can delete."""
    _ensure_tables()

    workspace = get_workspace(workspace_id)
    if not workspace or workspace.owner_id != user_id:
        return False

    db.execute("DELETE FROM workspace_members WHERE workspace_id = ?", (workspace_id,))
    db.execute("DELETE FROM workspace_invites WHERE workspace_id = ?", (workspace_id,))
    db.execute("DELETE FROM workspaces WHERE id = ?", (workspace_id,))

    logger.info(f"Workspace deleted: {workspace_id}")
    return True


def add_member(workspace_id: str, user_id: str, role: str = "member") -> bool:
    """Add a member to workspace."""
    _ensure_tables()

    now = time.time()
    db.execute(
        """
        INSERT INTO workspace_members (user_id, workspace_id, role, joined_at)
        VALUES (?, ?, ?, ?)
        ON DUPLICATE KEY UPDATE role = VALUES(role)
    """,
        (user_id, workspace_id, role, now),
    )

    return True


def remove_member(workspace_id: str, user_id: str, removed_by: str) -> bool:
    """Remove a member from workspace."""
    _ensure_tables()

    if not can_admin_workspace(removed_by, workspace_id):
        return False

    workspace = get_workspace(workspace_id)
    if workspace.owner_id == user_id:
        return False

    db.execute(
        """
        DELETE FROM workspace_members WHERE user_id = ? AND workspace_id = ?
    """,
        (user_id, workspace_id),
    )

    return True


def list_members(workspace_id: str) -> List[Dict[str, Any]]:
    """List all members of a workspace."""
    _ensure_tables()

    rows = db.fetchall(
        """
        SELECT wm.*, u.username, u.email
        FROM workspace_members wm
        JOIN users u ON wm.user_id = u.id
        WHERE wm.workspace_id = ?
        ORDER BY wm.joined_at
    """,
        (workspace_id,),
    )

    return [dict(row) for row in rows]


def create_invite(
    workspace_id: str,
    email: str,
    role: str,
    created_by: str,
    expires_in_hours: int = 72,
) -> str:
    """Create an invite link for a workspace."""
    _ensure_tables()

    import secrets

    invite_id = str(uuid.uuid4())
    token = secrets.token_urlsafe(32)
    now = time.time()
    expires_at = now + (expires_in_hours * 3600)

    db.execute(
        """
        INSERT INTO workspace_invites (id, workspace_id, email, role, token, expires_at, created_by)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """,
        (invite_id, workspace_id, email, role, token, expires_at, created_by),
    )

    return token


def accept_invite(token: str, user_id: str, user_email: str) -> Optional[str]:
    """Accept an invite and join workspace. Returns workspace_id on success."""
    _ensure_tables()

    row = db.fetchone(
        """
        SELECT * FROM workspace_invites WHERE token = ? AND used_at IS NULL
    """,
        (token,),
    )

    if not row:
        return None

    if row["email"].lower() != user_email.lower():
        return None

    if time.time() > row["expires_at"]:
        return None

    workspace_id = row["workspace_id"]
    role = row["role"]

    add_member(workspace_id, user_id, role)

    db.execute(
        """
        UPDATE workspace_invites SET used_at = ? WHERE id = ?
    """,
        (time.time(), row["id"]),
    )

    logger.info(f"User {user_id} joined workspace {workspace_id} via invite")

    return workspace_id


def can_view_workspace(user_id: str, workspace_id: str) -> bool:
    """Check if user can view workspace."""
    _ensure_tables()

    row = db.fetchone(
        """
        SELECT 1 FROM workspace_members WHERE user_id = ? AND workspace_id = ?
    """,
        (user_id, workspace_id),
    )

    return row is not None


def can_admin_workspace(user_id: str, workspace_id: str) -> bool:
    """Check if user can admin workspace (owner or admin role)."""
    _ensure_tables()

    row = db.fetchone(
        """
        SELECT role FROM workspace_members WHERE user_id = ? AND workspace_id = ?
    """,
        (user_id, workspace_id),
    )

    if not row:
        return False

    return row["role"] in ("owner", "admin")


def get_member_role(user_id: str, workspace_id: str) -> Optional[str]:
    """Get user's role in workspace."""
    _ensure_tables()

    row = db.fetchone(
        """
        SELECT role FROM workspace_members WHERE user_id = ? AND workspace_id = ?
    """,
        (user_id, workspace_id),
    )

    return row["role"] if row else None
