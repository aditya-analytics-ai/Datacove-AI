"""
Datacove v6 - FastAPI backend entry point.

New in v6 (Phase 3):
  - Onboarding routes: sample dataset catalogue + loader
  - Sharing routes: share links, fork, revoke
  - Schedule routes: cron schedules + webhook triggers
  - Connector routes: URL, Google Sheets, S3, SQL database
  - Billing routes: tier management + Stripe integration
  - Export destination routes: Google Sheets, Airtable, Notion, Slack
"""

from contextlib import asynccontextmanager
from pathlib import Path
import shutil
import time
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

from config import settings
from services.scheduler import start_scheduler, stop_scheduler
from middleware.rate_limit import GlobalRateLimitMiddleware
from routes import (
    session_routes,
    auth_routes,
    upload_routes,
    analysis_routes,
    cleaning_routes,
    export_routes,
    pipeline_routes,
    ai_agent_routes,
    ai_data_scientist_routes,
    streaming_routes,
    sql_routes,
    fuzzy_routes,
    validation_routes,
    report_routes,
    power_routes,
    onboarding_routes,
    sharing_routes,
    schedule_routes,
    connector_routes,
    billing_routes,
    export_destinations_routes,
    audit_routes,
    admin_routes,
    jobs_routes,
    vocab_routes,
    batch_routes,
)
from routes import (
    orchestrator_routes,
    connectors_v2,
    visual_pipeline_routes,
    ai_copilot_routes,
    workspace_routes,
    marketplace_routes,
    compliance_routes,
    websocket_routes,
    sso_routes,
    distributed_routes,
    api_key_routes,
    public_api,
    audit_dashboard_routes,
    collaboration_routes,
)
from utils.logger import logger

# ── Credential log-redaction filter ────────────────────────────────────────────
import logging
import json as _json


class _CredentialRedactFilter(logging.Filter):
    """Scrubs aws_secret_access_key and service_account_json from log records."""

    _SENSITIVE = (
        "aws_secret_access_key",
        "service_account_json",
        "api_key",
        "refresh_token",
    )

    def filter(self, record: logging.LogRecord) -> bool:
        msg = str(record.getMessage())
        for key in self._SENSITIVE:
            if key in msg:
                # Replace value after the key with [REDACTED]
                import re as _re

                msg = _re.sub(
                    rf'("{key}"\s*:\s*)"[^"]*"',
                    rf'\1"[REDACTED]"',
                    msg,
                )
                record.msg = msg
                record.args = ()
        return True


for _handler in logging.root.handlers:
    _handler.addFilter(_CredentialRedactFilter())

# ── Security check ─────────────────────────────────────────────────────────────
settings.validate_secrets()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle - starts the real APScheduler."""
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(
    title="Datacove AI API",
    description="""
## Overview

Datacove is an AI-native data cleaning, profiling, and ML platform.

## Features

- **Data Cleaning**: 95+ transformations with AI-powered suggestions
- **Data Profiling**: Automatic column analysis and health scoring
- **AI Copilot**: Natural language to data transformations
- **Pipeline Builder**: Visual and code-based pipeline creation
- **Real-time Collaboration**: Multi-user editing sessions
- **Compliance**: GDPR/CCPA/SOC2 compliance tools
- **Distributed Processing**: Scale to billions of rows with Dask

## Authentication

Most endpoints require JWT authentication. Include the token in the Authorization header:
```
Authorization: Bearer <your_token>
```

## Rate Limits

Rate limits depend on your tier:
- Free: 60 requests/minute
- Pro: 1000 requests/minute
- Enterprise: 10000 requests/minute
    """,
    version="6.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition", "Content-Length", "Content-Type"],
)
# Global per-IP rate limiting (sits inside CORS so it returns proper headers)
app.add_middleware(GlobalRateLimitMiddleware)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.detail,
            "status_code": exc.status_code,
        },
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    error_id = f"ERR-{int(time.time() * 1000)}"
    logger.error(
        f"[{error_id}] Unhandled exception on {request.method} {request.url}: {exc}",
        exc_info=True,
    )

    error_messages = {
        "ValidationError": "Invalid request data. Please check your input.",
        "AuthenticationError": "Authentication failed. Please log in again.",
        "PermissionError": "You don't have permission to perform this action.",
        "NotFoundError": "The requested resource was not found.",
        "RateLimitError": "Too many requests. Please wait and try again.",
        "TimeoutError": "The request took too long. Please try again.",
    }

    error_type = type(exc).__name__
    message = error_messages.get(error_type, "An internal server error occurred.")

    return JSONResponse(
        status_code=500,
        content={
            "detail": message,
            "error_id": error_id,
            "error_type": error_type,
        },
    )


# ── Core routers ───────────────────────────────────────────────────────────────
app.include_router(auth_routes.router, prefix="/api", tags=["Auth"])
app.include_router(session_routes.router, prefix="/api", tags=["Sessions"])
app.include_router(upload_routes.router, prefix="/api", tags=["Upload"])
app.include_router(analysis_routes.router, prefix="/api", tags=["Analysis"])
app.include_router(cleaning_routes.router, prefix="/api", tags=["Cleaning"])
app.include_router(streaming_routes.router, prefix="/api", tags=["Streaming"])
app.include_router(sql_routes.router, prefix="/api", tags=["SQL"])
app.include_router(fuzzy_routes.router, prefix="/api", tags=["Fuzzy"])
app.include_router(validation_routes.router, prefix="/api", tags=["Validation"])
app.include_router(report_routes.router, prefix="/api", tags=["Report"])
app.include_router(export_routes.router, prefix="/api", tags=["Export"])
app.include_router(pipeline_routes.router, prefix="/api", tags=["Pipeline"])
app.include_router(ai_agent_routes.router, prefix="/api", tags=["AI Agent"])
app.include_router(ai_data_scientist_routes.router, prefix="/api", tags=["AI ML"])
app.include_router(power_routes.router, prefix="/api", tags=["Power Features"])

app.include_router(vocab_routes.router, prefix="/api", tags=["Vocabulary"])
app.include_router(batch_routes.router, prefix="/api", tags=["Batch"])

# ── Phase 3 routers ────────────────────────────────────────────────────────────
app.include_router(onboarding_routes.router, prefix="/api", tags=["Onboarding"])
app.include_router(sharing_routes.router, prefix="/api", tags=["Sharing"])
app.include_router(schedule_routes.router, prefix="/api", tags=["Schedules"])
app.include_router(connector_routes.router, prefix="/api", tags=["Connectors"])
app.include_router(connectors_v2.router, prefix="/api", tags=["Connectors v2"])
app.include_router(
    visual_pipeline_routes.router, prefix="/api", tags=["Visual Pipeline"]
)
app.include_router(ai_copilot_routes.router, prefix="/api", tags=["AI Copilot"])
app.include_router(billing_routes.router, prefix="/api", tags=["Billing"])
app.include_router(
    export_destinations_routes.router, prefix="/api", tags=["Export Destinations"]
)

app.include_router(audit_routes.router, prefix="/api", tags=["Audit"])

# ── Admin + background jobs ───────────────────────────────────────────────────
app.include_router(admin_routes.router, prefix="/api", tags=["Admin"])
app.include_router(jobs_routes.router, prefix="/api", tags=["Jobs"])
app.include_router(orchestrator_routes.router, prefix="/api", tags=["AI Orchestrator"])
app.include_router(workspace_routes.router, prefix="/api", tags=["Workspaces"])
app.include_router(marketplace_routes.router, prefix="/api", tags=["Marketplace"])
app.include_router(compliance_routes.router, prefix="/api", tags=["Compliance"])
app.include_router(sso_routes.router, prefix="/api", tags=["SSO"])
app.include_router(websocket_routes.router)
app.include_router(distributed_routes.router, prefix="/api", tags=["Distributed"])
app.include_router(api_key_routes.router, prefix="/api", tags=["API Keys"])
app.include_router(public_api.router, tags=["Public API"])
app.include_router(
    audit_dashboard_routes.router, prefix="/api", tags=["Audit Dashboard"]
)
app.include_router(collaboration_routes.router, prefix="/api", tags=["Collaboration"])


@app.get("/health")
def health_check():
    """
    Dependency health probe - checks MySQL, Redis, and disk.
    Returns HTTP 200 when all critical services are up.
    Returns HTTP 503 with detail when any critical service is down.

    Safe for load-balancer / Kubernetes liveness + readiness probes.
    Does NOT expose secrets or internal state.
    """
    import time

    checks: dict = {}
    healthy = True

    # ── MySQL ────────────────────────────────────────────────────────────────
    try:
        from utils.db import db

        t0 = time.perf_counter()
        db.fetchone("SELECT 1", ())
        checks["mysql"] = {
            "status": "ok",
            "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
        }
    except Exception as exc:
        checks["mysql"] = {"status": "error", "detail": str(exc)[:120]}
        healthy = False  # MySQL is critical

    # ── Redis ────────────────────────────────────────────────────────────────
    try:
        from models.redis_session_store import ping as redis_ping, _is_available

        if _is_available():
            t0 = time.perf_counter()
            ok = redis_ping()
            checks["redis"] = {
                "status": "ok" if ok else "error",
                "latency_ms": round((time.perf_counter() - t0) * 1000, 1),
            }
            if not ok:
                checks["redis"]["detail"] = "ping returned False"
                # Redis is optional (app degrades to in-memory) - not fatal
        else:
            checks["redis"] = {"status": "not_configured"}
    except Exception as exc:
        checks["redis"] = {"status": "error", "detail": str(exc)[:120]}

    # ── Disk space (uploads dir) ─────────────────────────────────────────────
    try:
        usage = shutil.disk_usage(str(settings.UPLOAD_DIR))
        free_pct = (usage.free / usage.total) * 100
        checks["disk"] = {
            "status": "ok" if free_pct > 5 else "warning",
            "free_pct": round(free_pct, 1),
            "free_gb": round(usage.free / 1e9, 2),
        }
        if free_pct < 2:
            healthy = False  # less than 2% disk = critical
    except Exception as exc:
        checks["disk"] = {"status": "error", "detail": str(exc)[:80]}

    status_code = 200 if healthy else 503
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ok" if healthy else "degraded",
            "version": "6.0.0",
            "checks": checks,
        },
    )


_FRONTEND_HTML = Path(__file__).resolve().parent.parent / "datacove.html"


@app.get("/", response_class=HTMLResponse)
def serve_frontend():
    if _FRONTEND_HTML.exists():
        return HTMLResponse(_FRONTEND_HTML.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>datacove.html not found</h1>", status_code=404)
