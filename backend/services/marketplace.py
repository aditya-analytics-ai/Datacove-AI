"""
marketplace.py - Pipeline template marketplace.

Allows users to publish, browse, and install pipeline templates.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import uuid
import time
import hashlib

from utils.db import db
from utils.logger import logger


@dataclass
class PipelineTemplate:
    id: str
    name: str
    description: str
    author_id: str
    author_name: str
    category: str
    tags: List[str]
    steps: List[Dict[str, Any]]
    downloads: int
    rating: float
    rating_count: int
    created_at: float
    updated_at: float
    is_featured: bool = False
    is_verified: bool = False


def _ensure_tables():
    """Create marketplace tables if not exists."""
    db.execute("""
        CREATE TABLE IF NOT EXISTS pipeline_templates (
            id VARCHAR(36) PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            description TEXT,
            author_id VARCHAR(36) NOT NULL,
            author_name VARCHAR(255) NOT NULL,
            category VARCHAR(64) NOT NULL,
            tags TEXT,
            steps TEXT NOT NULL,
            downloads INT NOT NULL DEFAULT 0,
            rating DOUBLE NOT NULL DEFAULT 0,
            rating_count INT NOT NULL DEFAULT 0,
            is_featured TINYINT(1) NOT NULL DEFAULT 0,
            is_verified TINYINT(1) NOT NULL DEFAULT 0,
            created_at DOUBLE NOT NULL,
            updated_at DOUBLE NOT NULL,
            INDEX idx_templates_category (category),
            INDEX idx_templates_author (author_id),
            INDEX idx_templates_downloads (downloads)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS template_ratings (
            id VARCHAR(36) PRIMARY KEY,
            template_id VARCHAR(36) NOT NULL,
            user_id VARCHAR(36) NOT NULL,
            rating INT NOT NULL,
            created_at DOUBLE NOT NULL,
            UNIQUE KEY unique_rating (template_id, user_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


CATEGORIES = [
    "data_cleaning",
    "data_validation",
    "feature_engineering",
    "data_transformation",
    "aggregation",
    "time_series",
    "text_processing",
    "other",
]


def publish_template(
    name: str,
    description: str,
    author_id: str,
    author_name: str,
    category: str,
    tags: List[str],
    steps: List[Dict[str, Any]],
) -> PipelineTemplate:
    """Publish a pipeline template to the marketplace."""
    _ensure_tables()

    if category not in CATEGORIES:
        category = "other"

    template_id = str(uuid.uuid4())
    now = time.time()

    db.execute(
        """
        INSERT INTO pipeline_templates 
        (id, name, description, author_id, author_name, category, tags, steps, 
         downloads, rating, rating_count, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 0, ?, ?)
    """,
        (
            template_id,
            name,
            description,
            author_id,
            author_name,
            category,
            ",".join(tags),
            str(steps),
            now,
            now,
        ),
    )

    logger.info(f"Pipeline template published: {template_id} by {author_id}")

    return PipelineTemplate(
        id=template_id,
        name=name,
        description=description,
        author_id=author_id,
        author_name=author_name,
        category=category,
        tags=tags,
        steps=steps,
        downloads=0,
        rating=0,
        rating_count=0,
        created_at=now,
        updated_at=now,
    )


def get_template(template_id: str) -> Optional[PipelineTemplate]:
    """Get a template by ID."""
    _ensure_tables()

    row = db.fetchone("SELECT * FROM pipeline_templates WHERE id = ?", (template_id,))
    if not row:
        return None

    return _row_to_template(row)


def list_templates(
    category: Optional[str] = None,
    search: Optional[str] = None,
    sort_by: str = "downloads",
    limit: int = 20,
    offset: int = 0,
) -> List[PipelineTemplate]:
    """List templates with filtering and sorting."""
    _ensure_tables()

    query = "SELECT * FROM pipeline_templates WHERE 1=1"
    params = []

    if category:
        query += " AND category = ?"
        params.append(category)

    if search:
        query += " AND (name LIKE ? OR description LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%"])

    sort_options = {
        "downloads": "downloads DESC",
        "rating": "rating DESC",
        "newest": "created_at DESC",
        "name": "name ASC",
    }
    order_by = sort_options.get(sort_by, "downloads DESC")
    query += f" ORDER BY is_featured DESC, {order_by} LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    rows = db.fetchall(query, tuple(params))
    return [_row_to_template(row) for row in rows]


def get_featured_templates(limit: int = 5) -> List[PipelineTemplate]:
    """Get featured templates."""
    _ensure_tables()

    rows = db.fetchall(
        "SELECT * FROM pipeline_templates WHERE is_featured = 1 ORDER BY downloads DESC LIMIT ?",
        (limit,),
    )
    return [_row_to_template(row) for row in rows]


def rate_template(template_id: str, user_id: str, rating: int) -> bool:
    """Rate a template (1-5 stars)."""
    _ensure_tables()

    if rating < 1 or rating > 5:
        return False

    now = time.time()
    rating_id = hashlib.md5(f"{template_id}:{user_id}".encode()).hexdigest()[:12]

    db.execute(
        """
        INSERT INTO template_ratings (id, template_id, user_id, rating, created_at)
        VALUES (?, ?, ?, ?, ?)
        ON DUPLICATE KEY UPDATE rating = VALUES(rating)
    """,
        (rating_id, template_id, user_id, rating, now),
    )

    _update_template_rating(template_id)

    return True


def _update_template_rating(template_id: str):
    """Recalculate template's average rating."""
    row = db.fetchone(
        """
        SELECT AVG(rating) as avg, COUNT(*) as count 
        FROM template_ratings 
        WHERE template_id = ?
    """,
        (template_id,),
    )

    if row:
        avg_rating = float(row["avg"]) if row["avg"] else 0
        count = int(row["count"]) if row["count"] else 0

        db.execute(
            """
            UPDATE pipeline_templates 
            SET rating = ?, rating_count = ?, updated_at = ?
            WHERE id = ?
        """,
            (avg_rating, count, time.time(), template_id),
        )


def increment_downloads(template_id: str) -> bool:
    """Increment download counter when a template is installed."""
    _ensure_tables()

    db.execute(
        """
        UPDATE pipeline_templates 
        SET downloads = downloads + 1, updated_at = ?
        WHERE id = ?
    """,
        (time.time(), template_id),
    )

    return True


def delete_template(template_id: str, user_id: str) -> bool:
    """Delete a template. Only author can delete."""
    _ensure_tables()

    row = db.fetchone(
        "SELECT author_id FROM pipeline_templates WHERE id = ?", (template_id,)
    )
    if not row or row["author_id"] != user_id:
        return False

    db.execute("DELETE FROM template_ratings WHERE template_id = ?", (template_id,))
    db.execute("DELETE FROM pipeline_templates WHERE id = ?", (template_id,))

    return True


def feature_template(template_id: str, featured: bool = True) -> bool:
    """Mark/unmark template as featured (admin only)."""
    _ensure_tables()

    db.execute(
        """
        UPDATE pipeline_templates 
        SET is_featured = ?, updated_at = ?
        WHERE id = ?
    """,
        (1 if featured else 0, time.time(), template_id),
    )

    return True


def verify_template(template_id: str, verified: bool = True) -> bool:
    """Mark template as verified (admin only)."""
    _ensure_tables()

    db.execute(
        """
        UPDATE pipeline_templates 
        SET is_verified = ?, updated_at = ?
        WHERE id = ?
    """,
        (1 if verified else 0, time.time(), template_id),
    )

    return True


def _row_to_template(row: dict) -> PipelineTemplate:
    """Convert database row to PipelineTemplate."""
    import json

    return PipelineTemplate(
        id=row["id"],
        name=row["name"],
        description=row["description"] or "",
        author_id=row["author_id"],
        author_name=row["author_name"],
        category=row["category"],
        tags=row["tags"].split(",") if row["tags"] else [],
        steps=json.loads(row["steps"]) if row["steps"] else [],
        downloads=int(row["downloads"]),
        rating=float(row["rating"]),
        rating_count=int(row["rating_count"]),
        is_featured=bool(row["is_featured"]),
        is_verified=bool(row["is_verified"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
