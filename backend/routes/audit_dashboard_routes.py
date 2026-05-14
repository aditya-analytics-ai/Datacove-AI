"""
Audit Dashboard Routes - query and manage audit logs.

Base path: /api/audit
Requires: Admin role
"""

from datetime import datetime, timedelta, timezone
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from middleware.auth import get_current_user_id, require_admin
from services.audit_dashboard import (
    query_events,
    get_user_timeline,
    get_resource_history,
    get_failed_events,
    get_activity_summary,
    get_security_summary,
    generate_compliance_report,
    export_events_csv,
    export_events_json,
    create_alert_rule,
    get_alert_rules,
    toggle_alert_rule,
    delete_alert_rule,
    record_event,
    AuditEventType,
)
from utils.logger import logger


router = APIRouter(prefix="/audit", tags=["Audit Dashboard"])


# ── Models ────────────────────────────────────────────────────────────────────


class AuditEvent(BaseModel):
    event_id: str
    event_type: str
    category: str
    actor_id: Optional[str]
    actor_email: Optional[str]
    target_type: Optional[str]
    target_id: Optional[str]
    resource_id: Optional[str]
    ip_address: Optional[str]
    metadata: dict
    status: str
    error_message: Optional[str]
    duration_ms: Optional[int]
    created_at: str


class AlertRuleCreate(BaseModel):
    rule_name: str
    rule_config: dict
    notify_email: bool = False
    notify_webhook: bool = False
    webhook_url: Optional[str] = None


class ActivitySummary(BaseModel):
    period_days: int
    total_events: int
    by_category: dict
    by_status: dict
    top_event_types: List[dict]
    daily_counts: List[dict]
    top_actors: List[dict]


# ── Query Endpoints ────────────────────────────────────────────────────────────


@router.get("/events", response_model=List[AuditEvent])
def list_events(
    actor_id: Optional[str] = Query(None, description="Filter by actor ID"),
    target_id: Optional[str] = Query(None, description="Filter by target ID"),
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    category: Optional[str] = Query(
        None, description="Filter by category (auth, data, security, etc.)"
    ),
    status: Optional[str] = Query(
        None, description="Filter by status (success, failure)"
    ),
    start_date: Optional[datetime] = Query(None, description="Start date (ISO format)"),
    end_date: Optional[datetime] = Query(None, description="End date (ISO format)"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    admin: str = Depends(require_admin),
):
    """Query audit events with filters."""
    events = query_events(
        actor_id=actor_id,
        target_id=target_id,
        event_type=event_type,
        category=category,
        status=status,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset,
    )
    return [AuditEvent(**e) for e in events]


@router.get("/user/{user_id}/timeline", response_model=List[AuditEvent])
def user_timeline(
    user_id: str,
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(100, ge=1, le=1000),
    admin: str = Depends(require_admin),
):
    """Get activity timeline for a specific user."""
    events = get_user_timeline(user_id, days, limit)
    return [AuditEvent(**e) for e in events]


@router.get("/resource/{resource_id}/history", response_model=List[AuditEvent])
def resource_history(
    resource_id: str,
    limit: int = Query(50, ge=1, le=500),
    admin: str = Depends(require_admin),
):
    """Get all events related to a specific resource."""
    events = get_resource_history(resource_id, limit)
    return [AuditEvent(**e) for e in events]


@router.get("/failures", response_model=List[AuditEvent])
def list_failed_events(
    hours: int = Query(24, ge=1, le=168),
    limit: int = Query(100, ge=1, le=1000),
    admin: str = Depends(require_admin),
):
    """Get recent failed events (potential security issues)."""
    events = get_failed_events(hours, limit)
    return [AuditEvent(**e) for e in events]


# ── Analytics Endpoints ────────────────────────────────────────────────────────


@router.get("/summary")
def activity_summary(
    days: int = Query(30, ge=1, le=365),
    admin: str = Depends(require_admin),
):
    """Get summary statistics for audit events."""
    return get_activity_summary(days)


@router.get("/security-summary")
def security_summary(
    days: int = Query(30, ge=1, le=365),
    admin: str = Depends(require_admin),
):
    """
    Get security-focused audit summary.

    Returns metrics on failed logins, suspicious activities,
    rate limit violations, and risk level assessment.
    """
    return get_security_summary(days)


@router.get("/user/{user_id}/summary")
def user_activity_summary(
    user_id: str,
    days: int = Query(30, ge=1, le=365),
    admin: str = Depends(require_admin),
):
    """Get activity summary for a specific user."""
    return get_activity_summary(days, actor_id=user_id)


# ── Compliance Reports ────────────────────────────────────────────────────────


@router.get("/compliance/{framework}")
def compliance_report(
    framework: Literal["gdpr", "soc2", "hipaa", "pci-dss"],
    start_date: datetime = Query(..., description="Report period start"),
    end_date: datetime = Query(..., description="Report period end"),
    admin: str = Depends(require_admin),
):
    """
    Generate a compliance report for GDPR, SOC 2, HIPAA, or PCI-DSS.

    Returns structured compliance checks and evidence data.
    """
    if start_date > end_date:
        raise HTTPException(
            status_code=400, detail="start_date must be before end_date"
        )

    return generate_compliance_report(framework, start_date, end_date)


# ── Export Endpoints ───────────────────────────────────────────────────────────


@router.get("/export/csv")
def export_csv(
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    categories: Optional[str] = Query(
        None, description="Comma-separated list of categories"
    ),
    admin: str = Depends(require_admin),
):
    """
    Export audit events to CSV format.

    Useful for SIEM integration and external analysis.
    """
    cats = categories.split(",") if categories else None

    csv_data = export_events_csv(start_date, end_date, cats)

    return StreamingResponse(
        iter([csv_data]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=audit_export_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
        },
    )


@router.get("/export/json")
def export_json(
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    admin: str = Depends(require_admin),
):
    """
    Export audit events to JSON format.
    """
    return StreamingResponse(
        iter([export_events_json(start_date, end_date)]),
        media_type="application/json",
        headers={
            "Content-Disposition": f"attachment; filename=audit_export_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
        },
    )


# ── Alert Management ─────────────────────────────────────────────────────────


@router.get("/alerts", response_model=List[dict])
def list_alert_rules(admin: str = Depends(require_admin)):
    """List all configured audit alert rules."""
    return get_alert_rules()


@router.post("/alerts")
def create_alert(
    request: AlertRuleCreate,
    admin: str = Depends(require_admin),
):
    """Create a new audit alert rule."""
    rule_id = create_alert_rule(
        rule_name=request.rule_name,
        rule_config=request.rule_config,
        notify_email=request.notify_email,
        notify_webhook=request.notify_webhook,
        webhook_url=request.webhook_url,
    )
    return {"rule_id": rule_id, "status": "created"}


@router.patch("/alerts/{rule_id}/toggle")
def toggle_alert(
    rule_id: int,
    enabled: bool,
    admin: str = Depends(require_admin),
):
    """Enable or disable an alert rule."""
    if toggle_alert_rule(rule_id, enabled):
        return {"rule_id": rule_id, "enabled": enabled}
    raise HTTPException(status_code=404, detail="Alert rule not found")


@router.delete("/alerts/{rule_id}")
def remove_alert(
    rule_id: int,
    admin: str = Depends(require_admin),
):
    """Delete an alert rule."""
    if delete_alert_rule(rule_id):
        return {"status": "ok", "message": "Alert rule deleted"}
    raise HTTPException(status_code=404, detail="Alert rule not found")


# ── Record Events (Internal Use) ──────────────────────────────────────────────


@router.post("/record")
def record_audit_event(
    event_type: str,
    actor_id: Optional[str] = None,
    actor_email: Optional[str] = None,
    target_type: Optional[str] = None,
    target_id: Optional[str] = None,
    resource_id: Optional[str] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    metadata: Optional[dict] = None,
    status: str = "success",
    error_message: Optional[str] = None,
    duration_ms: Optional[int] = None,
):
    """
    Record an audit event (internal use by other services).

    This endpoint is typically called from middleware or other services,
    not directly by API clients.
    """
    event_id = record_event(
        event_type=event_type,
        actor_id=actor_id,
        actor_email=actor_email,
        target_type=target_type,
        target_id=target_id,
        resource_id=resource_id,
        ip_address=ip_address,
        user_agent=user_agent,
        metadata=metadata,
        status=status,
        error_message=error_message,
        duration_ms=duration_ms,
    )
    return {"event_id": event_id}


# ── Statistics Dashboard ──────────────────────────────────────────────────────


@router.get("/dashboard/stats")
def dashboard_stats(
    days: int = Query(7, ge=1, le=90),
    admin: str = Depends(require_admin),
):
    """
    Get key statistics for the audit dashboard.

    Returns at-a-glance metrics for the specified time period.
    """
    summary = get_activity_summary(days)
    security = get_security_summary(days)

    failed_events = get_failed_events(hours=days * 24, limit=20)

    return {
        "period_days": days,
        "total_events": summary["total_events"],
        "events_by_category": summary["by_category"],
        "events_by_status": summary["by_status"],
        "security_metrics": {
            "failed_logins": security["failed_logins"],
            "suspicious_activities": security["suspicious_activities"],
            "rate_limit_violations": security["rate_limit_violations"],
            "risk_level": security["risk_level"],
        },
        "recent_failures": failed_events[:10],
        "top_actors": summary["top_actors"][:5],
        "daily_trend": summary["daily_counts"][:14],
    }
