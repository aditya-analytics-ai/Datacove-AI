"""
scheduler.py - Real in-process scheduler for Datacove pipeline runs.

Replaces the ghost scheduler that stored cron records in MySQL but never
fired anything. Uses APScheduler (BackgroundScheduler - no Redis needed)
with a 60-second heartbeat that:

  1. Queries `schedules` WHERE next_run_at <= now() AND enabled = 1.
  2. For each due schedule, runs the pipeline against the stored session.
  3. Records the run in `schedule_runs`.
  4. Re-computes next_run_at using croniter.

Lifecycle:
  - start_scheduler() called on FastAPI startup.
  - stop_scheduler() called on FastAPI shutdown.

Usage:
    from services.scheduler import start_scheduler, stop_scheduler
"""
from __future__ import annotations

import time
import uuid
import traceback
from typing import Optional

from utils.logger import logger

# ── APScheduler ───────────────────────────────────────────────────────────────

_scheduler = None   # BackgroundScheduler instance; set in start_scheduler()


def start_scheduler() -> None:
    """Start the APScheduler BackgroundScheduler. Call once on app startup."""
    global _scheduler
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
    except ImportError:
        logger.warning(
            "APScheduler not installed - scheduled pipeline runs are disabled. "
            "Run: pip install apscheduler croniter"
        )
        return

    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_job(
        _tick,
        trigger="interval",
        seconds=60,
        id="schedule_tick",
        name="Pipeline schedule heartbeat",
        max_instances=1,           # Never run two ticks at once
        misfire_grace_time=30,     # Tolerate up to 30 s of startup delay
    )
    _scheduler.start()
    logger.info("Scheduler: APScheduler started (60-second heartbeat)")


def stop_scheduler() -> None:
    """Gracefully shut down the scheduler. Call on app shutdown."""
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler: APScheduler stopped")


# ── Heartbeat tick ────────────────────────────────────────────────────────────

def _tick() -> None:
    """
    Heartbeat function called every 60 seconds.
    Finds all enabled schedules whose next_run_at is in the past and fires them.
    """
    try:
        from utils.db import db
        now = time.time()

        due = db.fetchall(
            "SELECT id, owner_id, pipeline_id, session_id, cron FROM schedules "
            "WHERE enabled = 1 AND next_run_at <= %s",
            (now,),
        )

        if not due:
            return

        logger.info(f"Scheduler tick: {len(due)} schedule(s) due")

        for row in due:
            _run_schedule(row)

    except Exception as exc:
        logger.error(f"Scheduler tick error: {exc}\n{traceback.format_exc()}")


def _run_schedule(row: dict) -> None:
    """Execute a single due schedule and update its run state in the DB."""
    from utils.db import db

    schedule_id = row["id"]
    run_id      = str(uuid.uuid4())
    started_at  = time.time()

    # Mark the schedule as 'in-progress' (update last_run_at immediately
    # so a double-tick doesn't double-fire while this run is in progress)
    next_run = _compute_next_run(row["cron"])
    db.execute(
        "UPDATE schedules SET last_run_at = %s, next_run_at = %s WHERE id = %s",
        (started_at, next_run, schedule_id),
    )

    # Create a run record (status=running)
    db.execute(
        """INSERT INTO schedule_runs
           (id, schedule_id, started_at, status)
           VALUES (%s, %s, %s, 'running')""",
        (run_id, schedule_id, started_at),
    )

    logger.info(
        f"Scheduler: running schedule={schedule_id} "
        f"pipeline={row['pipeline_id']} session={row['session_id']}"
    )

    try:
        rows_before, rows_after = _execute_pipeline(
            pipeline_id=row["pipeline_id"],
            session_id=row["session_id"],
            owner_id=row["owner_id"],
        )
        finished_at = time.time()
        db.execute(
            """UPDATE schedule_runs
               SET finished_at=%s, status='done', rows_before=%s, rows_after=%s
               WHERE id=%s""",
            (finished_at, rows_before, rows_after, run_id),
        )
        logger.info(
            f"Scheduler: schedule={schedule_id} done in "
            f"{finished_at - started_at:.1f}s  "
            f"rows {rows_before}→{rows_after}"
        )

    except Exception as exc:
        finished_at = time.time()
        err_msg = str(exc)[:1000]  # cap error length stored in DB
        db.execute(
            """UPDATE schedule_runs
               SET finished_at=%s, status='failed', error=%s
               WHERE id=%s""",
            (finished_at, err_msg, run_id),
        )
        logger.error(
            f"Scheduler: schedule={schedule_id} failed - {exc}\n"
            f"{traceback.format_exc()}"
        )


def _execute_pipeline(pipeline_id: str, session_id: str, owner_id: str):
    """
    Load the pipeline steps from DB and apply them to the session dataset.
    Returns (rows_before, rows_after).
    """
    from utils.db import db
    from models.dataset_session import get_session, save_session
    from services.cleaning_engine import apply_transformation
    import json

    # Load the session (from memory → disk → SQLite)
    session = get_session(session_id, owner_id=owner_id)
    if session is None:
        raise RuntimeError(
            f"Session {session_id} not found - dataset may have been deleted."
        )

    rows_before = len(session.df_current)

    # Load pipeline steps from DB
    row = db.fetchone(
        "SELECT steps FROM pipelines WHERE id = %s",
        (pipeline_id,),
    )
    if row is None:
        raise RuntimeError(f"Pipeline {pipeline_id} not found in DB.")

    steps = json.loads(row["steps"]) if isinstance(row["steps"], str) else row["steps"]

    # Apply each step
    df = session.df_current.copy()
    for step in steps:
        action = step.get("action", "")
        params  = dict(step.get("params", {}))
        try:
            df = apply_transformation(df, action, params)
        except Exception as e:
            logger.warning(
                f"Scheduler pipeline step '{action}' failed: {e} - continuing."
            )

    session.df_current = df
    save_session(session_id, session)

    return rows_before, len(df)


# ── croniter helper ───────────────────────────────────────────────────────────

def _compute_next_run(cron_expr: str) -> float:
    """
    Compute the next UTC fire time for a cron expression using croniter.
    Falls back to 86400 s from now if croniter is unavailable.
    """
    try:
        from croniter import croniter
        import datetime
        now = datetime.datetime.utcnow()
        it  = croniter(cron_expr, now)
        return it.get_next(float)
    except Exception:
        logger.warning(
            f"croniter unavailable or bad cron '{cron_expr}' - defaulting to +24h"
        )
        return time.time() + 86400
