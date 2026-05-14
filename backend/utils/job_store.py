"""
job_store.py - Background job registry with Celery + Redis support.

Tiers:
  1. Celery + Redis (production): REDIS_URL set in .env, Celery installed
     → Jobs run in dedicated worker processes; survives server restarts.
  2. ThreadPoolExecutor (development): no Redis/Celery required
     → 4 workers in-process; works out of the box.

The public API (submit / get / list_active / update_progress / cleanup)
is identical for both tiers - zero changes needed in callers.

Job lifecycle:
  pending → running → done | failed
"""
from __future__ import annotations

import os
import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, Optional

from utils.logger import logger

_MAX_WORKERS = 4
_JOB_TTL     = 3600 * 2   # keep completed jobs 2 hours

REDIS_URL = os.getenv("REDIS_URL", "")


# ── Celery-backed job store ───────────────────────────────────────────────────

class CeleryJobStore:
    """
    Thin wrapper that tracks Celery AsyncResult objects so GET /jobs/{id}
    can translate Celery state into Datacove's job dict schema.
    """

    def __init__(self) -> None:
        self._map: Dict[str, Any] = {}   # job_id → AsyncResult
        self._meta: Dict[str, dict] = {} # job_id → snapshot metadata
        self._lock = threading.Lock()

    def submit(self, fn: Callable, *args, job_id: str | None = None, **kwargs) -> str:
        """Submit via Celery. fn must be a Celery @task."""
        try:
            from worker import submit_task
            jid = job_id or str(uuid.uuid4())
            result = submit_task(fn, *args, **kwargs)
            with self._lock:
                self._map[jid] = result
                self._meta[jid] = {
                    "job_id":     jid,
                    "created_at": time.time(),
                    "message":    "Queued",
                }
            logger.info(f"CeleryJob {jid}: submitted")
            return jid
        except Exception as exc:
            logger.error(f"CeleryJobStore.submit failed: {exc}; falling back to sync")
            # Sync fallback
            jid = job_id or str(uuid.uuid4())
            try:
                r = fn(*args, **kwargs)
            except Exception as e:
                r = {"error": str(e)}
            with self._lock:
                self._meta[jid] = {
                    "job_id": jid, "status": "done" if "error" not in r else "failed",
                    "created_at": time.time(), "finished_at": time.time(),
                    "result": r, "error": r.get("error"), "progress": 100, "message": "Completed",
                }
            return jid

    def get(self, job_id: str) -> Optional[dict]:
        with self._lock:
            celery_result = self._map.get(job_id)
            meta          = self._meta.get(job_id)

        if celery_result is None:
            return dict(meta) if meta else None

        state = celery_result.state  # PENDING/STARTED/SUCCESS/FAILURE
        base = {
            "job_id":     job_id,
            "created_at": meta.get("created_at") if meta else None,
        }

        if state == "SUCCESS":
            return {**base, "status": "done", "progress": 100,
                    "result": celery_result.result, "error": None,
                    "finished_at": time.time(), "message": "Completed"}
        elif state == "FAILURE":
            return {**base, "status": "failed", "progress": 0,
                    "error": str(celery_result.result),
                    "finished_at": time.time(), "message": "Failed"}
        elif state == "STARTED":
            return {**base, "status": "running", "progress": 30, "message": "Running…"}
        else:
            return {**base, "status": "pending", "progress": 0, "message": "Queued"}

    def update_progress(self, job_id: str, progress: int, message: str = "") -> None:
        pass  # Celery handles its own state

    def list_active(self) -> list[dict]:
        active = []
        with self._lock:
            for jid in list(self._map.keys()):
                j = self.get(jid)
                if j and j["status"] in ("pending", "running"):
                    active.append(j)
        return active

    def cleanup(self) -> int:
        return 0   # Redis TTL handles expiry automatically


# ── ThreadPoolExecutor-backed job store (default) ─────────────────────────────

class ThreadJobStore:
    def __init__(self) -> None:
        self._jobs: Dict[str, dict] = {}
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=_MAX_WORKERS,
                                            thread_name_prefix="dc-job")

    def submit(self, fn: Callable, *args, job_id: str | None = None, **kwargs) -> str:
        jid = job_id or str(uuid.uuid4())
        with self._lock:
            self._jobs[jid] = {
                "job_id":      jid,
                "status":      "pending",
                "created_at":  time.time(),
                "started_at":  None,
                "finished_at": None,
                "result":      None,
                "error":       None,
                "progress":    0,
                "message":     "Queued",
            }
        self._executor.submit(self._run_job, jid, fn, args, kwargs)
        logger.info(f"ThreadJob {jid}: submitted ({fn.__name__})")
        return jid

    def get(self, job_id: str) -> Optional[dict]:
        with self._lock:
            return dict(self._jobs[job_id]) if job_id in self._jobs else None

    def update_progress(self, job_id: str, progress: int, message: str = "") -> None:
        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id]["progress"] = min(100, max(0, progress))
                self._jobs[job_id]["message"]  = message

    def list_active(self) -> list[dict]:
        with self._lock:
            return [dict(j) for j in self._jobs.values()
                    if j["status"] in ("pending", "running")]

    def cleanup(self) -> int:
        now = time.time()
        with self._lock:
            old = [jid for jid, j in self._jobs.items()
                   if j["status"] in ("done", "failed")
                   and (now - (j["finished_at"] or 0)) > _JOB_TTL]
            for jid in old:
                del self._jobs[jid]
        return len(old)

    def _run_job(self, job_id: str, fn: Callable, args: tuple, kwargs: dict) -> None:
        with self._lock:
            self._jobs[job_id]["status"]     = "running"
            self._jobs[job_id]["started_at"] = time.time()
            self._jobs[job_id]["message"]    = "Running…"
        logger.info(f"ThreadJob {job_id}: started")
        try:
            result = fn(*args, **kwargs)
            with self._lock:
                self._jobs[job_id]["status"]      = "done"
                self._jobs[job_id]["finished_at"] = time.time()
                self._jobs[job_id]["progress"]    = 100
                self._jobs[job_id]["result"]      = result
                self._jobs[job_id]["message"]     = "Completed"
            logger.info(f"ThreadJob {job_id}: done")
        except Exception as exc:
            tb = traceback.format_exc()
            logger.error(f"ThreadJob {job_id}: failed - {exc}\n{tb}")
            with self._lock:
                self._jobs[job_id]["status"]      = "failed"
                self._jobs[job_id]["finished_at"] = time.time()
                self._jobs[job_id]["error"]       = str(exc)
                self._jobs[job_id]["message"]     = f"Failed: {exc}"


# ── Auto-select backend ───────────────────────────────────────────────────────

def _build_job_store():
    if REDIS_URL:
        try:
            import redis as _redis
            import celery as _celery  # noqa: F401
            r = _redis.from_url(REDIS_URL, socket_connect_timeout=2)
            r.ping()
            logger.info("JobStore: using Celery + Redis backend")
            return CeleryJobStore()
        except Exception as exc:
            logger.warning(f"JobStore: Celery/Redis unavailable ({exc}), "
                           "falling back to ThreadPoolExecutor")
    logger.info("JobStore: using ThreadPoolExecutor backend")
    return ThreadJobStore()


job_store = _build_job_store()
