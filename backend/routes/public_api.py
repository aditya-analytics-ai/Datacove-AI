"""
Public API - programmatic access to Datacove using API keys.

Authentication:
  Pass your API key in the `Authorization` header:
    Authorization: Bearer dk_live_xxxxx

Rate limits are per API key and depend on your tier.

Base path: /api/v1
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from services.api_key_manager import (
    APIKeyAuthResult,
    authenticate_api_key,
    check_rate_limit,
    has_scope,
    has_any_scope,
    record_usage,
    get_api_key,
)
from services.dataset_loader import (
    load_dataset,
    load_dataset_by_id,
    save_dataset,
    list_datasets,
)
from services.cleaning_engine import apply_transformation
from services.pipeline_engine import run_pipeline, create_pipeline
from services.profiling_engine import profile_dataset as get_profile
import pandas as pd


def get_summary_stats(df: pd.DataFrame) -> dict:
    """Get summary statistics for a DataFrame."""
    return {
        "rows": len(df),
        "columns": len(df.columns),
        "column_names": list(df.columns),
        "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()},
        "null_counts": df.isnull().sum().to_dict(),
        "memory_mb": df.memory_usage(deep=True).sum() / 1_048_576,
    }


from utils.db import db
from utils.logger import logger


router = APIRouter(prefix="/api/v1", tags=["Public API v1"])

# ── Authentication Dependency ──────────────────────────────────────────────────


def require_auth(
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    x_forwarded_for: Optional[str] = Header(None, alias="X-Forwarded-For"),
):
    """
    Authenticate API request using Bearer token or X-API-Key header.
    Extracts client IP from X-Forwarded-For if behind a proxy.
    """
    raw_key = None

    if authorization:
        if authorization.startswith("Bearer "):
            raw_key = authorization[7:]
        else:
            raw_key = authorization

    if not raw_key and x_api_key:
        raw_key = x_api_key

    if not raw_key:
        raise HTTPException(status_code=401, detail="Missing API key")

    ip_address = x_forwarded_for.split(",")[0].strip() if x_forwarded_for else None

    result = authenticate_api_key(raw_key, ip_address)

    if not result.valid:
        raise HTTPException(status_code=401, detail=result.error)

    if result.is_rate_limited:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Retry after {result.retry_after} seconds.",
            headers={
                "Retry-After": str(result.retry_after),
                "X-RateLimit-Retry-After": str(result.retry_after),
            },
        )

    return result


def require_scope(required_scope: str):
    """Factory for scope-checking dependency."""

    def checker(auth: APIKeyAuthResult = Depends(require_auth)):
        if not has_scope(auth, required_scope):
            raise HTTPException(
                status_code=403,
                detail=f"Missing required scope: {required_scope}. Your key has: {auth.scopes}",
            )
        return auth

    return checker


# ── Health & Info ───────────────────────────────────────────────────────────────


@router.get("/health")
def api_health():
    """API health check (no auth required)."""
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


@router.get("/me")
def api_me(auth: APIKeyAuthResult = Depends(require_auth)):
    """Get information about the authenticated API key."""
    key = get_api_key(auth.key_id, auth.owner_id)
    return {
        "key_id": auth.key_id,
        "tier": key.tier if key else "unknown",
        "scopes": auth.scopes,
        "rate_limits": auth.rate_limits,
    }


# ── Datasets ───────────────────────────────────────────────────────────────────


@router.get("/datasets")
def list_datasets_api(
    auth: APIKeyAuthResult = Depends(require_scope("datasets:read")),
    limit: int = 100,
    offset: int = 0,
):
    """List all datasets accessible to this API key."""
    datasets = list_datasets(auth.owner_id, limit=limit, offset=offset)
    return {"datasets": datasets, "total": len(datasets)}


@router.get("/datasets/{dataset_id}")
def get_dataset(
    dataset_id: str,
    auth: APIKeyAuthResult = Depends(require_scope("datasets:read")),
):
    """Get metadata for a dataset."""
    df = load_dataset_by_id(dataset_id, None, auth.owner_id)
    if df is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    return {
        "dataset_id": dataset_id,
        "rows": len(df),
        "columns": list(df.columns),
        "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()},
        "memory_mb": df.memory_usage(deep=True).sum() / 1_048_576,
        "null_counts": df.isnull().sum().to_dict(),
    }


@router.post("/datasets")
def create_dataset_api(
    request: Request,
    auth: APIKeyAuthResult = Depends(require_scope("datasets:write")),
):
    """
    Create a new dataset from JSON data.

    Request body:
    {
        "name": "my_dataset",
        "columns": ["col1", "col2"],
        "rows": [[1, "a"], [2, "b"]]
    }
    """
    body = request._json if hasattr(request, "_json") else None
    if not body:
        import json

        body = json.loads(request._content)

    name = body.get("name", f"api_dataset_{int(time.time())}")
    columns = body.get("columns", [])
    rows = body.get("rows", [])

    if not rows:
        raise HTTPException(status_code=400, detail="No rows provided")

    import pandas as pd

    df = pd.DataFrame(rows, columns=columns[: len(rows[0])] if rows else columns)

    dataset_id = save_dataset(df, name, auth.owner_id)

    return {"dataset_id": dataset_id, "rows": len(df), "status": "created"}


@router.delete("/datasets/{dataset_id}")
def delete_dataset_api(
    dataset_id: str,
    auth: APIKeyAuthResult = Depends(require_scope("datasets:delete")),
):
    """Delete a dataset."""
    db.execute(
        "DELETE FROM datasets WHERE id = %s AND owner_id = %s",
        (dataset_id, auth.owner_id),
    )
    return {"status": "ok", "message": "Dataset deleted"}


@router.get("/datasets/{dataset_id}/data")
def get_dataset_data(
    dataset_id: str,
    auth: APIKeyAuthResult = Depends(require_scope("datasets:read")),
    limit: int = 1000,
    offset: int = 0,
):
    """Get dataset rows as JSON."""
    df = load_dataset_by_id(dataset_id, None, auth.owner_id)
    if df is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    df = df.iloc[offset : offset + limit]

    return {
        "dataset_id": dataset_id,
        "rows": len(df),
        "offset": offset,
        "data": df.to_dict(orient="records"),
    }


# ── Cleaning ───────────────────────────────────────────────────────────────────


@router.post("/datasets/{dataset_id}/clean")
def clean_dataset_api(
    dataset_id: str,
    request: Request,
    auth: APIKeyAuthResult = Depends(require_scope("cleaning:execute")),
):
    """
    Apply cleaning transformations to a dataset.

    Request body:
    {
        "transformations": [
            {"action": "remove_duplicates", "params": {}},
            {"action": "fill_missing", "params": {"columns": ["col1"], "strategy": "mean"}}
        ],
        "output_name": "cleaned_dataset"
    }
    """
    import json

    body = json.loads(request._content)

    df = load_dataset_by_id(dataset_id, None, auth.owner_id)
    if df is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    transformations = body.get("transformations", [])
    output_name = body.get("output_name", f"cleaned_{dataset_id}")

    for transform in transformations:
        action = transform.get("action")
        params = transform.get("params", {})
        try:
            df = apply_transformation(df, action, params)
        except Exception as e:
            raise HTTPException(
                status_code=400, detail=f"Transformation failed: {action}: {e}"
            )

    output_id = save_dataset(df, output_name, auth.owner_id)

    return {
        "output_dataset_id": output_id,
        "rows": len(df),
        "transformations_applied": len(transformations),
    }


# ── Pipelines ──────────────────────────────────────────────────────────────────


@router.get("/pipelines")
def list_pipelines_api(
    auth: APIKeyAuthResult = Depends(require_scope("pipelines:read")),
):
    """List all pipelines accessible to this API key."""
    rows = db.fetchall(
        "SELECT id, name, created_at FROM pipelines WHERE owner_id = %s ORDER BY created_at DESC",
        (auth.owner_id,),
    )
    return {
        "pipelines": [
            {
                "id": row[0],
                "name": row[1],
                "created_at": row[2].isoformat() if row[2] else None,
            }
            for row in rows
        ]
    }


@router.post("/pipelines")
def create_pipeline_api(
    request: Request,
    auth: APIKeyAuthResult = Depends(require_scope("pipelines:write")),
):
    """
    Create a new pipeline.

    Request body:
    {
        "name": "my_pipeline",
        "steps": [
            {"action": "remove_duplicates", "params": {}},
            {"action": "fill_missing", "params": {"strategy": "mean"}}
        ]
    }
    """
    import json

    body = json.loads(request._content)

    name = body.get("name")
    steps = body.get("steps", [])

    if not name or not steps:
        raise HTTPException(status_code=400, detail="Name and steps required")

    pipeline = create_pipeline(name, steps, auth.owner_id)

    return {"pipeline_id": pipeline.id, "name": pipeline.name, "steps": len(steps)}


@router.post("/pipelines/{pipeline_id}/run")
def run_pipeline_api(
    pipeline_id: str,
    request: Request,
    auth: APIKeyAuthResult = Depends(require_scope("pipelines:execute")),
):
    """
    Execute a pipeline on a dataset.

    Request body:
    {
        "input_dataset_id": "xxx",
        "output_name": "output_dataset"
    }
    """
    import json

    body = json.loads(request._content)

    input_id = body.get("input_dataset_id")
    output_name = body.get("output_name", f"pipeline_output_{pipeline_id}")

    if not input_id:
        raise HTTPException(status_code=400, detail="input_dataset_id required")

    df = load_dataset_by_id(input_id, None, auth.owner_id)
    if df is None:
        raise HTTPException(status_code=404, detail="Input dataset not found")

    result = run_pipeline(pipeline_id, df, owner_id=auth.owner_id)

    if result.get("success"):
        output_id = save_dataset(result["df"], output_name, auth.owner_id)
        return {
            "output_dataset_id": output_id,
            "rows": len(result["df"]),
            "steps_run": len(result.get("steps_run", [])),
        }
    else:
        raise HTTPException(
            status_code=400, detail=f"Pipeline failed: {result.get('errors')}"
        )


# ── Analysis ───────────────────────────────────────────────────────────────────


@router.get("/datasets/{dataset_id}/summary")
def get_summary_api(
    dataset_id: str,
    auth: APIKeyAuthResult = Depends(require_scope("analysis:read")),
):
    """Get summary statistics for a dataset."""
    df = load_dataset_by_id(dataset_id, None, auth.owner_id)
    if df is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    return get_summary_stats(df)


@router.get("/datasets/{dataset_id}/profile")
def get_profile_api(
    dataset_id: str,
    auth: APIKeyAuthResult = Depends(require_scope("analysis:read")),
):
    """Get detailed profile for a dataset."""
    df = load_dataset_by_id(dataset_id, None, auth.owner_id)
    if df is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    return get_profile(df)


# ── Rate Limit Headers ──────────────────────────────────────────────────────────


@router.get("/rate-limits")
def get_rate_limits(auth: APIKeyAuthResult = Depends(require_auth)):
    """Get current rate limit status."""
    row = db.fetchone(
        "SELECT minute_requests, day_requests, month_requests FROM api_key_rate_limits WHERE key_id = %s",
        (auth.key_id,),
    )

    if not row:
        return {"status": "unknown"}

    minute_requests, day_requests, month_requests = row
    limits = auth.rate_limits

    return {
        "minute": {
            "used": minute_requests,
            "limit": limits.get("requests_per_minute", 60),
        },
        "day": {"used": day_requests, "limit": limits.get("requests_per_day", 1000)},
        "month": {
            "used": month_requests,
            "limit": limits.get("requests_per_month", 10000),
        },
    }
