"""
Export routes - download cleaned dataset as CSV, Excel, or JSON.
Also supports downloading versioned snapshots.

Fixed in v3:
  - Use fastapi.responses.Response (not StreamingResponse) for pre-built
    in-memory content. StreamingResponse(iter([bytes])) is unreliable;
    some ASGI servers buffer differently and Content-Length can mismatch.
    Response(content=bytes) is direct, correct, and simpler.
  - Strip timezone info from datetime columns before Excel export.
    openpyxl raises ValueError: "Excel does not support datetimes with timezones."
  - Convert NaT to None so JSON/CSV don't emit the literal string "NaT".
  - Expose Content-Disposition per-response (belt + suspenders alongside
    the global expose_headers added to CORS middleware in main.py).
"""
import io
import os
import pandas as pd

from fastapi import APIRouter, Query, HTTPException, Response, Depends
from fastapi.responses import JSONResponse, StreamingResponse

from models.dataset_session import get_session, DATASET_DIR
from utils.logger import logger
from utils.auth import get_current_user, AuthUser
from utils.session_guard import require_session

router = APIRouter(dependencies=[Depends(get_current_user)])


# ── Helpers ───────────────────────────────────────────────────────────────────



def _strip_tz(df: pd.DataFrame) -> pd.DataFrame:
    """Strip timezone from all tz-aware datetime columns.
    Uses tz_convert(None) (not tz_localize) so wall-clock times are correctly
    converted to UTC-naive before stripping - required by openpyxl."""
    df = df.copy()
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            if getattr(df[col].dt, "tz", None) is not None:
                df[col] = df[col].dt.tz_convert(None)
    return df


def _nat_to_none(df: pd.DataFrame) -> pd.DataFrame:
    """Replace NaT with None so it serialises as null/empty, not 'NaT'."""
    return df.where(df.notna(), other=None)


def _safe_stem(filename: str) -> str:
    if not filename:
        return "dataset"
    parts = filename.rsplit(".", 1)
    return parts[0] if parts[0] else "dataset"


def _make_response(content: bytes, media_type: str, filename: str) -> Response:
    """Build a download Response with all required headers."""
    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(content)),
            "Access-Control-Expose-Headers": "Content-Disposition, Content-Length",
        },
    )


def _export_df(df: pd.DataFrame, fmt: str, stem: str) -> Response:
    """Serialise df to the requested format and return a download Response."""

    if fmt == "csv":
        buf = io.StringIO()
        _strip_tz(df).to_csv(buf, index=False)
        return _make_response(
            buf.getvalue().encode("utf-8"),
            "text/csv; charset=utf-8",
            f"{stem}.csv",
        )

    if fmt == "json":
        df_out  = _strip_tz(_nat_to_none(df))
        payload = df_out.to_json(orient="records", date_format="iso", default_handler=str)
        return _make_response(
            payload.encode("utf-8"),
            "application/json; charset=utf-8",
            f"{stem}.json",
        )

    if fmt == "parquet":
        buf = io.BytesIO()
        _strip_tz(df).to_parquet(buf, index=False, engine="pyarrow")
        return _make_response(
            buf.getvalue(),
            "application/octet-stream",
            f"{stem}.parquet",
        )

    # xlsx - strip tz before openpyxl writes
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        _strip_tz(df).to_excel(writer, index=False, sheet_name="Cleaned Data")
    return _make_response(
        buf.getvalue(),
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        f"{stem}.xlsx",
    )


# ── Main export endpoint ──────────────────────────────────────────────────────

@router.get("/export")
def export(
    session_id: str = Query(...),
    fmt: str        = Query("csv", pattern="^(csv|xlsx|json|parquet)$"),
):
    """Download the cleaned dataset in CSV, Excel, or JSON format."""
    try:
        session = require_session(session_id)
        stem    = _safe_stem(session.filename) + "_cleaned"
        logger.info(f"Export: session={session_id} fmt={fmt} rows={len(session.df_current)}")
        return _export_df(session.df_current, fmt, stem)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Export failed session={session_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")


# ── Versioned snapshots ───────────────────────────────────────────────────────

@router.get("/export/versions")
def list_export_versions(session_id: str = Query(...)):
    """List all saved dataset version snapshots for a session."""
    try:
        require_session(session_id)
        versions = []
        i = 1
        while True:
            path = os.path.join(str(DATASET_DIR), f"{session_id}_v{i}.csv")
            if not os.path.exists(path):
                break
            df_v = pd.read_csv(path)
            versions.append({"version": i, "path": path,
                             "rows": len(df_v), "columns": list(df_v.columns)})
            i += 1
        return JSONResponse({"session_id": session_id, "versions": versions})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"List versions failed session={session_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/export/version/{version}")
def export_version(
    version: int,
    session_id: str = Query(...),
    fmt: str        = Query("csv", pattern="^(csv|xlsx|json)$"),
):
    """Download a specific versioned snapshot."""
    try:
        path = os.path.join(str(DATASET_DIR), f"{session_id}_v{version}.csv")
        if not os.path.exists(path):
            raise HTTPException(status_code=404, detail=f"Version {version} not found.")
        return _export_df(pd.read_csv(path), fmt, f"dataset_v{version}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Export version failed session={session_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Export version failed: {str(e)}")