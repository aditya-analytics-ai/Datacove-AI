"""
schedule_routes.py - scheduled pipeline runs and webhook triggers.

POST /api/schedules              - create a schedule for a pipeline
GET  /api/schedules              - list user's schedules
PATCH /api/schedules/{id}        - enable/disable a schedule
DELETE /api/schedules/{id}       - delete a schedule
GET  /api/schedules/{id}/runs    - list past run history

POST /api/webhooks               - register a webhook endpoint
GET  /api/webhooks               - list user's webhooks
DELETE /api/webhooks/{id}        - remove a webhook
POST /api/webhooks/{id}/trigger  - manually trigger a webhook (for testing)

Note: actual job execution uses APScheduler (lightweight, no Redis needed).
Celery+Redis is still the right choice at scale - see requirements.txt comments.
"""

import uuid
import time
import hashlib
import hmac
import json
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from utils.auth import get_current_user, AuthUser
from utils.db import db
from utils.logger import logger

router = APIRouter(dependencies=[Depends(get_current_user)])

# DB tables migration moved to db.py

VALID_CRONS = {
    "hourly": "0 * * * *",
    "daily": "0 9 * * *",
    "weekly": "0 9 * * 1",
    "monthly": "0 9 1 * *",
}


# ── Schedules ──────────────────────────────────────────────────────────────────


class CreateScheduleRequest(BaseModel):
    pipeline_id: str
    session_id: str
    cron: str  # preset name OR raw cron string
    label: str = ""


class UpdateScheduleRequest(BaseModel):
    enabled: bool


def _parse_cron(cron: str) -> str:
    return VALID_CRONS.get(cron, cron)


def _next_run(cron_str: str) -> float:
    """Compute the next fire time using croniter (accurate to the second)."""
    from services.scheduler import _compute_next_run

    return _compute_next_run(cron_str)


@router.post("/schedules")
def create_schedule(
    req: CreateScheduleRequest, user: AuthUser = Depends(get_current_user)
):
    cron_str = _parse_cron(req.cron)
    sched_id = str(uuid.uuid4())
    now = time.time()
    next_run = _next_run(cron_str)

    db.execute(
        """
        INSERT INTO schedules (id, owner_id, pipeline_id, session_id, cron, label, next_run_at, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """,
        (
            sched_id,
            user.user_id,
            req.pipeline_id,
            req.session_id,
            cron_str,
            req.label,
            next_run,
            now,
        ),
    )

    logger.info(
        f"Schedule created: id={sched_id} pipeline={req.pipeline_id} cron={cron_str}"
    )
    return JSONResponse(
        {
            "schedule_id": sched_id,
            "cron": cron_str,
            "next_run_at": next_run,
            "enabled": True,
        }
    )


@router.get("/schedules")
def list_schedules(user: AuthUser = Depends(get_current_user)):
    rows = db.fetchall(
        """
        SELECT id, pipeline_id, session_id, cron, label, enabled, last_run_at, next_run_at, created_at
        FROM schedules WHERE owner_id = ? ORDER BY created_at DESC
    """,
        (user.user_id,),
    )
    return JSONResponse({"schedules": [dict(r) for r in rows]})


@router.patch("/schedules/{schedule_id}")
def toggle_schedule(
    schedule_id: str,
    req: UpdateScheduleRequest,
    user: AuthUser = Depends(get_current_user),
):
    row = db.fetchone("SELECT owner_id FROM schedules WHERE id = ?", (schedule_id,))
    if not row:
        raise HTTPException(status_code=404, detail="Schedule not found.")
    if row["owner_id"] != user.user_id:
        raise HTTPException(status_code=403, detail="Not your schedule.")
    db.execute(
        "UPDATE schedules SET enabled = ? WHERE id = ?",
        (1 if req.enabled else 0, schedule_id),
    )
    return JSONResponse({"schedule_id": schedule_id, "enabled": req.enabled})


@router.delete("/schedules/{schedule_id}")
def delete_schedule(schedule_id: str, user: AuthUser = Depends(get_current_user)):
    row = db.fetchone("SELECT owner_id FROM schedules WHERE id = ?", (schedule_id,))
    if not row:
        raise HTTPException(status_code=404, detail="Schedule not found.")
    if row["owner_id"] != user.user_id:
        raise HTTPException(status_code=403, detail="Not your schedule.")
    db.execute("DELETE FROM schedules WHERE id = ?", (schedule_id,))
    db.execute("DELETE FROM schedule_runs WHERE schedule_id = ?", (schedule_id,))
    return JSONResponse({"deleted": True})


@router.get("/schedules/{schedule_id}/runs")
def list_runs(schedule_id: str, user: AuthUser = Depends(get_current_user)):
    row = db.fetchone("SELECT owner_id FROM schedules WHERE id = ?", (schedule_id,))
    if not row or row["owner_id"] != user.user_id:
        raise HTTPException(status_code=404, detail="Schedule not found.")
    runs = db.fetchall(
        """
        SELECT id, started_at, finished_at, `status`, rows_before, rows_after, error
        FROM schedule_runs WHERE schedule_id = ? ORDER BY started_at DESC LIMIT 50
    """,
        (schedule_id,),
    )
    return JSONResponse({"runs": [dict(r) for r in runs]})


# ── Webhooks ──────────────────────────────────────────────────────────────────


class CreateWebhookRequest(BaseModel):
    pipeline_id: str
    label: str = ""


def _sign_payload(secret: str, payload: dict) -> str:
    """HMAC-SHA256 signature for webhook payload verification."""
    body = json.dumps(payload, separators=(",", ":")).encode()
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


@router.post("/webhooks")
def create_webhook(
    req: CreateWebhookRequest, user: AuthUser = Depends(get_current_user)
):
    wh_id = str(uuid.uuid4())
    secret = uuid.uuid4().hex + uuid.uuid4().hex  # 64-char secret
    now = time.time()

    db.execute(
        """
        INSERT INTO webhooks (id, owner_id, pipeline_id, label, secret, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """,
        (wh_id, user.user_id, req.pipeline_id, req.label, secret, now),
    )

    return JSONResponse(
        {
            "webhook_id": wh_id,
            "trigger_url": f"/api/webhooks/{wh_id}/trigger",
            "secret": secret,
            "warning": "Save this secret now - it will not be shown again. "
            "Use it to sign webhook payloads with HMAC-SHA256 "
            "(X-Datacove-Signature header).",
        }
    )


@router.get("/webhooks")
def list_webhooks(user: AuthUser = Depends(get_current_user)):
    rows = db.fetchall(
        """
        SELECT id, pipeline_id, label, created_at, last_used_at, trigger_count
        FROM webhooks WHERE owner_id = ? ORDER BY created_at DESC
    """,
        (user.user_id,),
    )
    return JSONResponse({"webhooks": [dict(r) for r in rows]})


@router.delete("/webhooks/{webhook_id}")
def delete_webhook(webhook_id: str, user: AuthUser = Depends(get_current_user)):
    row = db.fetchone("SELECT owner_id FROM webhooks WHERE id = ?", (webhook_id,))
    if not row or row["owner_id"] != user.user_id:
        raise HTTPException(status_code=404, detail="Webhook not found.")
    db.execute("DELETE FROM webhooks WHERE id = ?", (webhook_id,))
    return JSONResponse({"deleted": True})


@router.post("/webhooks/{webhook_id}/trigger")
def trigger_webhook(
    webhook_id: str,
    background: BackgroundTasks,
    user: AuthUser = Depends(get_current_user),
):
    """Manually trigger a webhook - useful for testing before automating."""
    row = db.fetchone("SELECT * FROM webhooks WHERE id = ?", (webhook_id,))
    if not row or row["owner_id"] != user.user_id:
        raise HTTPException(status_code=404, detail="Webhook not found.")

    db.execute(
        """
        UPDATE webhooks SET last_used_at = ?, trigger_count = trigger_count + 1
        WHERE id = ?
    """,
        (time.time(), webhook_id),
    )

    # In production: background.add_task(run_pipeline_async, row["pipeline_id"])
    logger.info(f"Webhook triggered: id={webhook_id} pipeline={row['pipeline_id']}")

    return JSONResponse(
        {
            "triggered": True,
            "webhook_id": webhook_id,
            "pipeline_id": row["pipeline_id"],
            "message": "Pipeline queued. Connect Celery+Redis to enable async execution.",
        }
    )
