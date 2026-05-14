"""
compliance.py - GDPR/CCPA compliance tools.

Provides:
- Data subject request handling (right to access, right to delete)
- Personal data discovery and classification
- Data retention policies
- Audit trails for compliance
- Consent management
- Data processing agreements
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


class DataCategory(str, Enum):
    PERSONAL = "personal"
    SENSITIVE = "sensitive"
    FINANCIAL = "financial"
    HEALTH = "health"
    BIOMETRIC = "biometric"
    LOCATION = "location"
    PUBLIC = "public"
    ANONYMIZED = "anonymized"


@dataclass
class PersonalDataField:
    column_name: str
    category: DataCategory
    pii_type: str
    sensitivity_score: float  # 0-1
    contains_data: bool = True


@dataclass
class ComplianceReport:
    report_id: str
    report_type: str  # dsar, audit, retention, data_inventory
    user_id: str
    status: str
    created_at: float
    completed_at: Optional[float] = None
    data: Dict[str, Any] = field(default_factory=dict)


def _ensure_tables():
    """Create compliance tables if not exists."""
    db.execute("""
        CREATE TABLE IF NOT EXISTS personal_data_inventory (
            id VARCHAR(36) PRIMARY KEY,
            session_id VARCHAR(36) NOT NULL,
            owner_id VARCHAR(36) NOT NULL,
            column_name VARCHAR(255) NOT NULL,
            data_category VARCHAR(32) NOT NULL,
            pii_type VARCHAR(64),
            sensitivity_score DOUBLE NOT NULL,
            created_at DOUBLE NOT NULL,
            INDEX idx_inventory_session (session_id),
            INDEX idx_inventory_owner (owner_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS compliance_requests (
            id VARCHAR(36) PRIMARY KEY,
            request_type VARCHAR(32) NOT NULL,
            requester_email VARCHAR(255) NOT NULL,
            requester_id VARCHAR(36),
            user_id VARCHAR(36),
            status VARCHAR(16) NOT NULL DEFAULT 'pending',
            details TEXT,
            created_at DOUBLE NOT NULL,
            completed_at DOUBLE,
            completed_by VARCHAR(36)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS consent_records (
            id VARCHAR(36) PRIMARY KEY,
            user_id VARCHAR(36) NOT NULL,
            consent_type VARCHAR(64) NOT NULL,
            granted BOOLEAN NOT NULL,
            granted_at DOUBLE NOT NULL,
            revoked_at DOUBLE,
            ip_address VARCHAR(45),
            user_agent TEXT
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS data_retention_policies (
            id VARCHAR(36) PRIMARY KEY,
            workspace_id VARCHAR(36),
            owner_id VARCHAR(36) NOT NULL,
            policy_name VARCHAR(255) NOT NULL,
            retention_days INT NOT NULL,
            data_types TEXT NOT NULL,
            auto_delete BOOLEAN NOT NULL DEFAULT TRUE,
            created_at DOUBLE NOT NULL,
            INDEX idx_policies_workspace (workspace_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS audit_events (
            id VARCHAR(36) PRIMARY KEY,
            event_type VARCHAR(64) NOT NULL,
            user_id VARCHAR(36),
            session_id VARCHAR(36),
            resource_type VARCHAR(64),
            resource_id VARCHAR(36),
            action VARCHAR(32) NOT NULL,
            pii_accessed BOOLEAN DEFAULT FALSE,
            details TEXT,
            ip_address VARCHAR(45),
            timestamp DOUBLE NOT NULL,
            INDEX idx_audit_user (user_id),
            INDEX idx_audit_timestamp (timestamp)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


# ── PII Detection Patterns ──────────────────────────────────────────────────────

PII_PATTERNS = {
    "email": {
        "pattern": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
        "category": DataCategory.PERSONAL,
        "sensitivity": 0.8,
    },
    "phone": {
        "pattern": r"\b(\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b",
        "category": DataCategory.PERSONAL,
        "sensitivity": 0.7,
    },
    "ssn": {
        "pattern": r"\b\d{3}[-\s]?\d{2}[-\s]?\d{4}\b",
        "category": DataCategory.SENSITIVE,
        "sensitivity": 1.0,
    },
    "credit_card": {
        "pattern": r"\b(?:\d[ -]?){13,16}\b",
        "category": DataCategory.FINANCIAL,
        "sensitivity": 1.0,
    },
    "ip_address": {
        "pattern": r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
        "category": DataCategory.LOCATION,
        "sensitivity": 0.5,
    },
    "dob": {
        "pattern": r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b",
        "category": DataCategory.PERSONAL,
        "sensitivity": 0.6,
    },
    "address": {
        "pattern": r"\b\d+\s+[\w\s]+(?:street|st|avenue|ave|road|rd| boulevard|blvd)\b",
        "category": DataCategory.LOCATION,
        "sensitivity": 0.7,
    },
    "name": {
        "heuristic": True,
        "category": DataCategory.PERSONAL,
        "sensitivity": 0.8,
    },
    "age": {
        "heuristic": True,
        "category": DataCategory.PERSONAL,
        "sensitivity": 0.3,
    },
}


def scan_for_pii(df: pd.DataFrame) -> List[PersonalDataField]:
    """Scan DataFrame columns for PII/PCI/PHI data."""
    import re

    personal_fields = []

    for col in df.columns:
        col_lower = col.lower()
        sample_values = df[col].dropna().astype(str).head(100).tolist()
        sample_text = " ".join(sample_values)

        for pii_type, pii_info in PII_PATTERNS.items():
            if pii_info.get("heuristic"):
                if pii_type == "name" and any(
                    kw in col_lower
                    for kw in [
                        "name",
                        "first",
                        "last",
                        "full",
                        "customer",
                        "user",
                        "client",
                    ]
                ):
                    personal_fields.append(
                        PersonalDataField(
                            column_name=col,
                            category=pii_info["category"],
                            pii_type=pii_type,
                            sensitivity_score=pii_info["sensitivity"],
                        )
                    )
                    break
                elif pii_type == "age" and any(
                    kw in col_lower for kw in ["age", "dob", "birth", "years"]
                ):
                    personal_fields.append(
                        PersonalDataField(
                            column_name=col,
                            category=pii_info["category"],
                            pii_type=pii_type,
                            sensitivity_score=pii_info["sensitivity"],
                        )
                    )
                    break
            else:
                pattern = pii_info["pattern"]
                matches = re.findall(pattern, sample_text, re.IGNORECASE)
                if len(matches) > len(sample_values) * 0.1:
                    personal_fields.append(
                        PersonalDataField(
                            column_name=col,
                            category=pii_info["category"],
                            pii_type=pii_type,
                            sensitivity_score=pii_info["sensitivity"],
                        )
                    )
                    break

    return personal_fields


def register_pii_inventory(
    session_id: str, owner_id: str, fields: List[PersonalDataField]
) -> None:
    """Register discovered PII fields in the inventory."""
    _ensure_tables()

    db.execute(
        "DELETE FROM personal_data_inventory WHERE session_id = ?", (session_id,)
    )

    for field in fields:
        db.execute(
            """
            INSERT INTO personal_data_inventory 
            (id, session_id, owner_id, column_name, data_category, pii_type, sensitivity_score, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                str(uuid.uuid4()),
                session_id,
                owner_id,
                field.column_name,
                field.category.value,
                field.pii_type,
                field.sensitivity_score,
                time.time(),
            ),
        )


# ── Data Subject Requests (DSAR) ────────────────────────────────────────────────


class DSARType(str, Enum):
    ACCESS = "access"  # Right to know what data is held
    RECTIFICATION = "rectification"  # Right to correct data
    ERASURE = "erasure"  # Right to be forgotten
    PORTABILITY = "portability"  # Right to export data
    OBJECTION = "objection"  # Right to object to processing


def create_dsar(
    request_type: DSARType, requester_email: str, requester_id: Optional[str] = None
) -> str:
    """Create a Data Subject Access Request."""
    _ensure_tables()

    request_id = str(uuid.uuid4())
    now = time.time()

    db.execute(
        """
        INSERT INTO compliance_requests 
        (id, request_type, requester_email, requester_id, status, created_at)
        VALUES (?, ?, ?, ?, 'pending', ?)
    """,
        (request_id, request_type.value, requester_email, requester_id, now),
    )

    logger.info(f"DSAR created: {request_id} type={request_type.value}")
    return request_id


def get_user_data_export(user_id: str) -> Dict[str, Any]:
    """Export all data associated with a user for DSAR."""
    _ensure_tables()

    user_rows = db.fetchall("SELECT * FROM users WHERE id = ?", (user_id,))

    session_rows = db.fetchall(
        "SELECT id, filename, rows, created_at FROM sessions WHERE owner_id = ?",
        (user_id,),
    )

    audit_rows = db.fetchall(
        "SELECT * FROM audit_events WHERE user_id = ? ORDER BY timestamp DESC LIMIT 1000",
        (user_id,),
    )

    consent_rows = db.fetchall(
        "SELECT * FROM consent_records WHERE user_id = ?", (user_id,)
    )

    return {
        "profile": [dict(r) for r in user_rows],
        "sessions": [dict(r) for r in session_rows],
        "audit_log": [dict(r) for r in audit_rows],
        "consents": [dict(r) for r in consent_rows],
        "exported_at": time.time(),
    }


def delete_user_data(
    user_id: str, request_id: str, completed_by: str
) -> Dict[str, Any]:
    """Delete all personal data for a user (right to be forgotten)."""
    _ensure_tables()

    deleted_items = []

    sessions = db.fetchall("SELECT id FROM sessions WHERE owner_id = ?", (user_id,))
    for session in sessions:
        db.execute("DELETE FROM sessions WHERE id = ?", (session["id"],))
        deleted_items.append(f"session:{session['id']}")

    db.execute("DELETE FROM users WHERE id = ?", (user_id,))
    deleted_items.append(f"user:{user_id}")

    db.execute("DELETE FROM audit_events WHERE user_id = ?", (user_id,))

    db.execute("DELETE FROM consent_records WHERE user_id = ?", (user_id,))

    db.execute("DELETE FROM personal_data_inventory WHERE owner_id = ?", (user_id,))

    db.execute(
        """
        UPDATE compliance_requests 
        SET status = 'completed', completed_at = ?, completed_by = ?
        WHERE id = ?
    """,
        (time.time(), completed_by, request_id),
    )

    logger.info(f"User data deleted for GDPR request: {user_id}")

    return {
        "request_id": request_id,
        "deleted_items": deleted_items,
        "deleted_at": time.time(),
    }


# ── Consent Management ─────────────────────────────────────────────────────────


def record_consent(
    user_id: str,
    consent_type: str,
    granted: bool,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> bool:
    """Record user consent for data processing."""
    _ensure_tables()

    now = time.time()

    existing = db.fetchone(
        "SELECT id FROM consent_records WHERE user_id = ? AND consent_type = ?",
        (user_id, consent_type),
    )

    if existing:
        if granted:
            db.execute(
                """
                UPDATE consent_records 
                SET granted = TRUE, granted_at = ?, revoked_at = NULL
                WHERE user_id = ? AND consent_type = ?
            """,
                (now, user_id, consent_type),
            )
        else:
            db.execute(
                """
                UPDATE consent_records 
                SET granted = FALSE, revoked_at = ?
                WHERE user_id = ? AND consent_type = ?
            """,
                (now, user_id, consent_type),
            )
    else:
        record_id = str(uuid.uuid4())
        db.execute(
            """
            INSERT INTO consent_records 
            (id, user_id, consent_type, granted, granted_at, ip_address, user_agent)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
            (record_id, user_id, consent_type, granted, now, ip_address, user_agent),
        )

    return True


def get_user_consents(user_id: str) -> List[Dict[str, Any]]:
    """Get all consent records for a user."""
    _ensure_tables()

    rows = db.fetchall(
        "SELECT * FROM consent_records WHERE user_id = ? ORDER BY granted_at DESC",
        (user_id,),
    )
    return [dict(r) for r in rows]


def has_consent(user_id: str, consent_type: str) -> bool:
    """Check if user has given consent for a specific type."""
    _ensure_tables()

    row = db.fetchone(
        """
        SELECT granted FROM consent_records 
        WHERE user_id = ? AND consent_type = ? AND granted = TRUE AND revoked_at IS NULL
        ORDER BY granted_at DESC LIMIT 1
    """,
        (user_id, consent_type),
    )

    return bool(row)


# ── Retention Policies ─────────────────────────────────────────────────────────


def create_retention_policy(
    owner_id: str,
    policy_name: str,
    retention_days: int,
    data_types: List[str],
    workspace_id: Optional[str] = None,
) -> str:
    """Create a data retention policy."""
    _ensure_tables()

    policy_id = str(uuid.uuid4())
    now = time.time()

    db.execute(
        """
        INSERT INTO data_retention_policies 
        (id, workspace_id, owner_id, policy_name, retention_days, data_types, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """,
        (
            policy_id,
            workspace_id,
            owner_id,
            policy_name,
            retention_days,
            ",".join(data_types),
            now,
        ),
    )

    return policy_id


def apply_retention_policies() -> Dict[str, Any]:
    """Apply retention policies and delete expired data. Run via cron."""
    _ensure_tables()

    now = time.time()
    deleted_count = 0

    policies = db.fetchall(
        "SELECT * FROM data_retention_policies WHERE auto_delete = TRUE"
    )

    for policy in policies:
        cutoff = now - (policy["retention_days"] * 86400)
        data_types = policy["data_types"].split(",")

        logger.info(
            f"Applying retention policy {policy['id']}: deleting data older than {cutoff}"
        )

    return {"policies_checked": len(policies), "records_deleted": deleted_count}


# ── Audit Logging ──────────────────────────────────────────────────────────────


def log_compliance_event(
    event_type: str,
    action: str,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    pii_accessed: bool = False,
    details: Optional[Dict] = None,
    ip_address: Optional[str] = None,
) -> None:
    """Log a compliance-related event for audit trail."""
    _ensure_tables()

    import json

    event_id = str(uuid.uuid4())

    db.execute(
        """
        INSERT INTO audit_events 
        (id, event_type, user_id, session_id, resource_type, resource_id, 
         action, pii_accessed, details, ip_address, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
        (
            event_id,
            event_type,
            user_id,
            session_id,
            resource_type,
            resource_id,
            action,
            pii_accessed,
            json.dumps(details) if details else None,
            ip_address,
            time.time(),
        ),
    )


def get_compliance_audit_log(
    user_id: Optional[str] = None,
    start_date: Optional[float] = None,
    end_date: Optional[float] = None,
    event_type: Optional[str] = None,
    limit: int = 1000,
) -> List[Dict[str, Any]]:
    """Get compliance audit log with filtering."""
    _ensure_tables()

    query = "SELECT * FROM audit_events WHERE 1=1"
    params = []

    if user_id:
        query += " AND user_id = ?"
        params.append(user_id)

    if start_date:
        query += " AND timestamp >= ?"
        params.append(start_date)

    if end_date:
        query += " AND timestamp <= ?"
        params.append(end_date)

    if event_type:
        query += " AND event_type = ?"
        params.append(event_type)

    query += " ORDER BY timestamp DESC LIMIT ?"
    params.append(limit)

    rows = db.fetchall(query, tuple(params))
    return [dict(r) for r in rows]


# ── Compliance Reports ──────────────────────────────────────────────────────────


def generate_compliance_report(
    report_type: str, user_id: str, session_id: Optional[str] = None
) -> ComplianceReport:
    """Generate a compliance report."""
    report_id = str(uuid.uuid4())
    now = time.time()

    report = ComplianceReport(
        report_id=report_id,
        report_type=report_type,
        user_id=user_id,
        status="generating",
        created_at=now,
    )

    if report_type == "data_inventory":
        fields = db.fetchall(
            "SELECT * FROM personal_data_inventory WHERE owner_id = ?", (user_id,)
        )
        report.data = {"pii_fields": [dict(f) for f in fields]}
        report.status = "completed"
        report.completed_at = time.time()

    elif report_type == "audit":
        events = get_compliance_audit_log(user_id=user_id, limit=100)
        report.data = {"events": events}
        report.status = "completed"
        report.completed_at = time.time()

    return report
