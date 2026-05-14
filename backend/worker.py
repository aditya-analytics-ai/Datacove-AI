"""
worker.py - Celery task definitions for Datacove background jobs.

Celery + Redis replaces the in-process ThreadPoolExecutor for CPU-heavy
and long-running tasks (AI agent, large-file uploads, async transforms).

Setup
─────
1. Install: pip install "celery>=5.3.0" "redis>=5.0.0"
2. Set REDIS_URL in .env:
      REDIS_URL=redis://localhost:6379/0
3. Start the worker (separate terminal, same directory as main.py):
      celery -A worker.celery_app worker --loglevel=info --concurrency=4
4. The FastAPI app sends tasks via .delay() or .apply_async().
   Results are stored in Redis for 1 hour.

Fallback
────────
If Redis is unavailable or REDIS_URL is not set, the module still imports
cleanly. Task functions can be called directly (synchronously) as a fallback.
"""
from __future__ import annotations

import os
from typing import Any, Dict

from utils.logger import logger

# ── Celery bootstrap ──────────────────────────────────────────────────────────
REDIS_URL = os.getenv("REDIS_URL", "")

try:
    from celery import Celery

    celery_app = Celery(
        "datacove",
        broker=REDIS_URL or "redis://localhost:6379/0",
        backend=REDIS_URL or "redis://localhost:6379/0",
    )
    celery_app.conf.update(
        task_serializer         = "json",
        result_serializer       = "json",
        accept_content          = ["json"],
        result_expires          = 3600,          # 1 hour
        task_track_started      = True,
        task_acks_late          = True,          # re-queue on worker crash
        worker_prefetch_multiplier = 1,          # fair dispatch
        task_routes             = {
            "worker.run_ai_agent_task": {"queue": "ai"},
            "worker.process_upload_task": {"queue": "uploads"},
            "worker.apply_transform_task": {"queue": "transforms"},
        },
    )
    CELERY_AVAILABLE = True
    logger.info("Celery: app initialised")
except ImportError:
    celery_app = None          # type: ignore[assignment]
    CELERY_AVAILABLE = False
    logger.warning("Celery not installed - background tasks run synchronously. "
                   "Install with: pip install 'celery>=5.3.0' 'redis>=5.0.0'")


# ── Helper: submit or run synchronously ──────────────────────────────────────

def submit_task(fn, *args, **kwargs):
    """
    Submit a Celery task if available, otherwise call synchronously.
    Returns a Celery AsyncResult (or a simple namespace with .id and .get()).
    """
    if CELERY_AVAILABLE and REDIS_URL:
        return fn.delay(*args, **kwargs)
    # Synchronous fallback - returns a mock result object
    result = fn(*args, **kwargs)
    class _SyncResult:
        id = "sync"
        def get(self, **_): return result
    return _SyncResult()


# ── Task definitions ──────────────────────────────────────────────────────────

if CELERY_AVAILABLE:
    @celery_app.task(bind=True, name="worker.run_ai_agent_task",
                     max_retries=2, default_retry_delay=5)
    def run_ai_agent_task(self, session_id: str, user_id: str):
        """Run the AI data cleaning agent for a session (async)."""
        try:
            from models.dataset_session import get_session, persist_dataset
            from services.ai_agent import run_agent

            session = get_session(session_id)
            if session is None:
                return {"error": "Session not found"}

            result = run_agent(session.df_current, session_id=session_id)
            if result.get("df") is not None:
                session.df_current = result["df"]
                persist_dataset(session_id, result["df"], session.filename)
            logger.info(f"Celery AI agent done: session={session_id}")
            return result
        except Exception as exc:
            logger.error(f"Celery AI agent error: {exc}")
            raise self.retry(exc=exc)

    @celery_app.task(bind=True, name="worker.process_upload_task",
                     max_retries=1)
    def process_upload_task(self, file_path: str, filename: str, user_id: str):
        """Process a large uploaded file and create a session (async)."""
        try:
            from services.dataset_loader import load_dataset
            from models.dataset_session import create_session

            df, schema_suggestions = load_dataset(file_path)
            session_id = create_session(df, filename, owner_id=user_id)
            logger.info(f"Celery upload done: session={session_id} rows={len(df)}")
            return {
                "session_id": session_id,
                "rows": len(df),
                "columns": list(df.columns),
                "schema_suggestions": schema_suggestions,
            }
        except Exception as exc:
            logger.error(f"Celery upload error: {exc}")
            raise self.retry(exc=exc)

    @celery_app.task(bind=True, name="worker.apply_transform_task",
                     max_retries=2, default_retry_delay=2)
    def apply_transform_task(self, session_id: str, action: str,
                              params: Dict[str, Any], user_id: str):
        """Apply a transformation to a dataset (async, for large files)."""
        try:
            from services.cleaning_engine import apply_transformation
            from models.dataset_session import get_session, persist_dataset, save_version

            session = get_session(session_id)
            if session is None:
                return {"error": "Session not found"}

            df_before = session.df_current.copy()
            df_after  = apply_transformation(session.df_current, action, params)

            version = len(session.versions) + 1
            session.versions.append(save_version(session_id, df_before, version))
            session.push_history(df_before, action, params)
            session.df_current = df_after
            persist_dataset(session_id, df_after, session.filename)

            logger.info(f"Celery transform done: session={session_id} action={action}")
            return {
                "success": True,
                "rows":    len(df_after),
                "columns": list(df_after.columns),
            }
        except Exception as exc:
            logger.error(f"Celery transform error: {exc}")
            raise self.retry(exc=exc)

else:
    # Stub functions for when Celery is not installed
    def run_ai_agent_task(session_id, user_id):
        from services.ai_agent import run_agent
        from models.dataset_session import get_session
        session = get_session(session_id)
        if session is None:
            return {"error": "Session not found"}
        return run_agent(session.df_current, session_id=session_id)

    def process_upload_task(file_path, filename, user_id):
        from services.dataset_loader import load_dataset
        from models.dataset_session import create_session
        df, schema = load_dataset(file_path)
        return {"session_id": create_session(df, filename, owner_id=user_id),
                "rows": len(df), "columns": list(df.columns), "schema_suggestions": schema}

    def apply_transform_task(session_id, action, params, user_id):
        from services.cleaning_engine import apply_transformation
        from models.dataset_session import get_session, persist_dataset
        session = get_session(session_id)
        if session is None:
            return {"error": "Session not found"}
        df_after = apply_transformation(session.df_current, action, params)
        session.df_current = df_after
        persist_dataset(session_id, df_after, session.filename)
        return {"success": True, "rows": len(df_after), "columns": list(df_after.columns)}
