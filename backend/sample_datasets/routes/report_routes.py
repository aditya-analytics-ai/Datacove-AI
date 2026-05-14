"""
report_routes.py - quality report download endpoint v2.

Changes from v1:
  - Pulls audit log for the session and includes it in the report
  - Uses profile_with_sampling for large dataset performance
  - Caches profile from session metadata if available (avoids re-profiling)

GET /api/report?session_id=... - download a self-contained HTML quality report
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse

from models.dataset_session import get_session
from services.profiling_engine import profile_dataset
from services.issue_detector import detect_issues
from services.health_score import calculate_health_score
from services.anomaly_detector import detect_anomalies
from services.report_generator import generate_html_report
from services.audit_log import get_log as get_audit_log
from services.performance import profile_with_sampling
from utils.auth import get_current_user, AuthUser
from utils.logger import logger

router = APIRouter(dependencies=[Depends(get_current_user)])


@router.get("/report")
async def download_report(
    session_id: str = Query(...),
    user: AuthUser = Depends(get_current_user),
):
    """Generate and download a self-contained HTML data quality report."""
    session = get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found.")

    logger.info(f"Report: session={session_id} rows={len(session.df_current):,}")

    try:
        df = session.df_current

        # Use sampling-aware profiling for large datasets
        profile   = await run_in_threadpool(profile_with_sampling, df, profile_dataset)
        issues    = await run_in_threadpool(detect_issues, df)
        health    = await run_in_threadpool(calculate_health_score, df, issues)
        anomalies = await run_in_threadpool(detect_anomalies, df)

        # Pull the full audit log for this session
        audit_entries = get_audit_log(session_id)

        html_str = generate_html_report(
            filename      = session.filename,
            profile       = profile,
            issues        = issues,
            health        = health,
            anomalies     = anomalies,
            audit_entries = audit_entries if audit_entries else None,
        )

        stem = session.filename.rsplit(".", 1)[0]
        return HTMLResponse(
            content=html_str,
            headers={
                "Content-Disposition": f'attachment; filename="{stem}_quality_report.html"',
            },
        )
    except Exception as e:
        logger.error(f"Report generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
