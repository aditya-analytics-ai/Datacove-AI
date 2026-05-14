"""
compliance_routes.py - GDPR/CCPA compliance API.

POST /api/compliance/scan-pii        - Scan dataset for PII
GET  /api/compliance/inventory        - Get PII inventory
POST /api/compliance/dsar            - Create data subject request
GET  /api/compliance/dsar/{id}      - Get DSAR status
POST /api/compliance/consent         - Record consent
GET  /api/compliance/consents        - Get user consents
POST /api/compliance/retention       - Create retention policy
GET  /api/compliance/audit          - Get audit log
POST /api/compliance/report          - Generate compliance report
"""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import JSONResponse
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, EmailStr

from utils.session_guard import require_session
from services.compliance import (
    scan_for_pii,
    register_pii_inventory,
    get_user_data_export,
    delete_user_data,
    record_consent,
    get_user_consents,
    has_consent,
    create_retention_policy,
    apply_retention_policies,
    get_compliance_audit_log,
    generate_compliance_report,
    DSARType,
    DataCategory,
    create_dsar,
)
from utils.auth import get_current_user, AuthUser
from utils.logger import logger

router = APIRouter(prefix="/compliance", dependencies=[Depends(get_current_user)])


class ScanPIIRequest(BaseModel):
    session_id: str


class DSARRequest(BaseModel):
    request_type: str  # access, rectification, erasure, portability, objection
    requester_email: EmailStr


class RecordConsentRequest(BaseModel):
    consent_type: str  # marketing, analytics, third_party_sharing
    granted: bool


class RetentionPolicyRequest(BaseModel):
    policy_name: str
    retention_days: int
    data_types: List[str]
    workspace_id: Optional[str] = None
    auto_delete: bool = True


class ComplianceReportRequest(BaseModel):
    report_type: str  # data_inventory, audit, retention
    session_id: Optional[str] = None


@router.post("/scan-pii")
async def scan_dataset_pii(
    req: ScanPIIRequest, user: AuthUser = Depends(get_current_user)
):
    """Scan a dataset for PII/PHI/PII fields."""
    session = require_session(req.session_id, owner_id=user.user_id)
    df = session.df_current

    def _scan():
        return scan_for_pii(df)

    pii_fields = await run_in_threadpool(_scan)

    register_pii_inventory(req.session_id, user.user_id, pii_fields)

    return JSONResponse(
        {
            "session_id": req.session_id,
            "pii_fields": [
                {
                    "column": f.column_name,
                    "category": f.category.value,
                    "pii_type": f.pii_type,
                    "sensitivity": f.sensitivity_score,
                }
                for f in pii_fields
            ],
            "total_pii_columns": len(pii_fields),
            "sensitive_columns": len(
                [f for f in pii_fields if f.category == DataCategory.SENSITIVE]
            ),
        }
    )


@router.get("/inventory")
def get_pii_inventory(user: AuthUser = Depends(get_current_user)):
    """Get all PII fields inventoried for this user's datasets."""
    from utils.db import db

    rows = db.fetchall(
        """
        SELECT pdi.*, s.filename 
        FROM personal_data_inventory pdi
        JOIN sessions s ON pdi.session_id = s.id
        WHERE pdi.owner_id = ?
        ORDER BY pdi.created_at DESC
    """,
        (user.user_id,),
    )

    return JSONResponse(
        {
            "inventory": [dict(r) for r in rows],
            "total_fields": len(rows),
        }
    )


@router.post("/dsar")
def create_data_subject_request(
    req: DSARRequest, user: AuthUser = Depends(get_current_user)
):
    """Create a Data Subject Access Request (GDPR right)."""
    if req.request_type not in [t.value for t in DSARType]:
        raise HTTPException(status_code=400, detail="Invalid request type")

    request_id = create_dsar(
        DSARType(req.request_type), req.requester_email, user.user_id
    )

    return JSONResponse(
        {
            "request_id": request_id,
            "request_type": req.request_type,
            "status": "pending",
        }
    )


@router.get("/dsar/{request_id}")
async def get_dsar_status(request_id: str, user: AuthUser = Depends(get_current_user)):
    """Get status of a DSAR request."""
    from utils.db import db

    row = db.fetchone(
        """
        SELECT * FROM compliance_requests 
        WHERE id = ? AND (requester_id = ? OR user_id = ?)
    """,
        (request_id, user.user_id, user.user_id),
    )

    if not row:
        raise HTTPException(status_code=404, detail="Request not found")

    return JSONResponse(
        {
            "request_id": row["id"],
            "request_type": row["request_type"],
            "status": row["status"],
            "created_at": row["created_at"],
            "completed_at": row["completed_at"],
        }
    )


@router.post("/dsar/{request_id}/export")
async def export_user_data(request_id: str, user: AuthUser = Depends(get_current_user)):
    """Export all data for a DSAR (access request)."""
    from utils.db import db

    row = db.fetchone(
        """
        SELECT * FROM compliance_requests 
        WHERE id = ? AND request_type = 'access'
    """,
        (request_id,),
    )

    if not row:
        raise HTTPException(status_code=404, detail="Export request not found")

    export_data = get_user_data_export(row["user_id"])

    return JSONResponse(export_data)


@router.post("/dsar/{request_id}/delete")
async def process_deletion(request_id: str, user: AuthUser = Depends(get_current_user)):
    """Process a deletion request (right to be forgotten)."""
    from utils.db import db

    row = db.fetchone(
        """
        SELECT * FROM compliance_requests 
        WHERE id = ? AND request_type = 'erasure'
    """,
        (request_id,),
    )

    if not row:
        raise HTTPException(status_code=404, detail="Deletion request not found")

    result = delete_user_data(row["user_id"], request_id, user.user_id)

    return JSONResponse(result)


@router.post("/consent")
def record_user_consent(
    req: RecordConsentRequest,
    user: AuthUser = Depends(get_current_user),
    request: Request = None,
):
    """Record user consent for data processing."""
    ip_address = request.client.host if request else None
    user_agent = request.headers.get("user-agent") if request else None

    record_consent(
        user_id=user.user_id,
        consent_type=req.consent_type,
        granted=req.granted,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    return JSONResponse(
        {
            "consent_type": req.consent_type,
            "granted": req.granted,
            "recorded": True,
        }
    )


@router.get("/consents")
def get_consents(user: AuthUser = Depends(get_current_user)):
    """Get all consent records for the current user."""
    consents = get_user_consents(user.user_id)

    return JSONResponse(
        {
            "consents": consents,
            "total": len(consents),
        }
    )


@router.get("/consent/{consent_type}")
def check_consent(consent_type: str, user: AuthUser = Depends(get_current_user)):
    """Check if user has given consent for a specific type."""
    granted = has_consent(user.user_id, consent_type)

    return JSONResponse(
        {
            "consent_type": consent_type,
            "granted": granted,
        }
    )


@router.post("/retention")
def create_policy(
    req: RetentionPolicyRequest, user: AuthUser = Depends(get_current_user)
):
    """Create a data retention policy."""
    policy_id = create_retention_policy(
        owner_id=user.user_id,
        policy_name=req.policy_name,
        retention_days=req.retention_days,
        data_types=req.data_types,
        workspace_id=req.workspace_id,
    )

    return JSONResponse(
        {
            "policy_id": policy_id,
            "policy_name": req.policy_name,
            "retention_days": req.retention_days,
        }
    )


@router.post("/retention/apply")
def apply_retention(user: AuthUser = Depends(get_current_user)):
    """Manually trigger retention policy enforcement."""
    from utils.auth import _is_admin

    if not _is_admin(user.user_id):
        raise HTTPException(status_code=403, detail="Admin only")

    result = apply_retention_policies()
    return JSONResponse(result)


@router.get("/audit")
def get_audit_log(
    start_date: Optional[float] = None,
    end_date: Optional[float] = None,
    event_type: Optional[str] = None,
    user: AuthUser = Depends(get_current_user),
):
    """Get compliance audit log."""
    from utils.auth import _is_admin

    if not _is_admin(user.user_id):
        start_date = None
        end_date = None

    events = get_compliance_audit_log(
        user_id=user.user_id,
        start_date=start_date,
        end_date=end_date,
        event_type=event_type,
    )

    return JSONResponse(
        {
            "events": events,
            "total": len(events),
        }
    )


@router.post("/report")
def create_report(
    req: ComplianceReportRequest, user: AuthUser = Depends(get_current_user)
):
    """Generate a compliance report."""
    report = generate_compliance_report(req.report_type, user.user_id, req.session_id)

    return JSONResponse(
        {
            "report_id": report.report_id,
            "report_type": report.report_type,
            "status": report.status,
            "created_at": report.created_at,
            "data": report.data,
        }
    )
