"""
connector_routes.py - external data source connectors.

POST /api/connectors/url          - load CSV/Excel from a public URL
POST /api/connectors/gsheets      - import a Google Sheet (service account)
POST /api/connectors/s3           - import from AWS S3
POST /api/connectors/database     - query a SQL database → session
GET  /api/connectors/test/{type}  - test a connector config without importing
"""
import uuid
import io
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import JSONResponse
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from utils.auth import get_current_user, AuthUser
from utils.preview import safe_preview
from models.dataset_session import DatasetSession, save_session
from utils.logger import logger

router = APIRouter(dependencies=[Depends(get_current_user)])


def _cap_query(query: str, limit: int) -> str:
    """
    Inject a server-side LIMIT into a SELECT query.
    Strips any user-supplied LIMIT/FETCH clause first to enforce the cap.
    """
    import re
    # Remove trailing semicolons
    q = query.rstrip(";").rstrip()
    # Strip existing LIMIT / FETCH FIRST / FETCH NEXT clauses (case-insensitive)
    q = re.sub(r'\bLIMIT\s+\d+(\s*,\s*\d+)?\s*$', '', q, flags=re.IGNORECASE).rstrip()
    q = re.sub(r'\bFETCH\s+(FIRST|NEXT)\s+\d+\s+ROWS?\s+ONLY\s*$', '', q,
               flags=re.IGNORECASE).rstrip()
    return f"{q} LIMIT {limit}"


# ── Connector 1: URL (public CSV / Excel) ─────────────────────────────────────

class URLConnectorRequest(BaseModel):
    url:      str
    filename: Optional[str] = None


@router.post("/connectors/url")
async def connect_url(req: URLConnectorRequest, user: AuthUser = Depends(get_current_user)):
    """Load a CSV or Excel file from any public URL."""
    import httpx, pandas as pd
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.get(req.url)
            resp.raise_for_status()

        content_type = resp.headers.get("content-type", "")
        filename = req.filename or req.url.split("/")[-1].split("?")[0] or "imported.csv"
        raw = io.BytesIO(resp.content)

        if "spreadsheet" in content_type or filename.endswith((".xlsx", ".xls")):
            df = pd.read_excel(raw)
        else:
            df = pd.read_csv(raw)

        session_id = str(uuid.uuid4())
        session    = DatasetSession(df=df, filename=filename, owner_id=user.user_id)
        save_session(session_id, session)
        logger.info(f"URL connector: {req.url} → session={session_id}")

        return JSONResponse({
            "session_id": session_id,
            "filename":   filename,
            "source":     req.url,
            "rows":       len(df),
            "columns":    list(df.columns),
            "preview":    safe_preview(df),
        })
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Failed to load from URL: {e}")


# ── Connector 2: Google Sheets ────────────────────────────────────────────────

class GSheetsRequest(BaseModel):
    spreadsheet_id: str    # from the Google Sheets URL
    sheet_name:     Optional[str] = None
    # Pass service account JSON as a string, or set GOOGLE_SA_JSON env var
    service_account_json: Optional[str] = None


@router.post("/connectors/gsheets")
async def connect_gsheets(req: GSheetsRequest, user: AuthUser = Depends(get_current_user)):
    """Import a Google Sheet using a service account."""
    try:
        import gspread                                          # pip install gspread
        from google.oauth2.service_account import Credentials  # pip install google-auth
        import json, os, pandas as pd

        sa_json = req.service_account_json or os.getenv("GOOGLE_SA_JSON")
        if not sa_json:
            raise HTTPException(
                status_code=400,
                detail="No service account credentials provided. "
                       "Pass service_account_json or set GOOGLE_SA_JSON env var.",
            )

        creds  = Credentials.from_service_account_info(
            json.loads(sa_json),
            scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
        )
        gc     = gspread.authorize(creds)
        sh     = gc.open_by_key(req.spreadsheet_id)
        ws     = sh.worksheet(req.sheet_name) if req.sheet_name else sh.sheet1
        data   = ws.get_all_records()
        df     = pd.DataFrame(data)

        filename   = f"{sh.title}_{ws.title}.csv"
        session_id = str(uuid.uuid4())
        session    = DatasetSession(df=df, filename=filename, owner_id=user.user_id)
        save_session(session_id, session)
        logger.info(f"GSheets connector: {req.spreadsheet_id}/{ws.title} → session={session_id}")

        return JSONResponse({
            "session_id":      session_id,
            "filename":        filename,
            "spreadsheet_id":  req.spreadsheet_id,
            "sheet":           ws.title,
            "rows":            len(df),
            "columns":         list(df.columns),
            "preview":         safe_preview(df),
        })
    except ImportError:
        raise HTTPException(
            status_code=501,
            detail="Google Sheets connector requires: pip install gspread google-auth",
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Google Sheets import failed: {e}")


# ── Connector 3: AWS S3 ───────────────────────────────────────────────────────

class S3ConnectorRequest(BaseModel):
    bucket:            str
    key:               str          # path to file within the bucket
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None
    region:            str = "us-east-1"


@router.post("/connectors/s3")
async def connect_s3(req: S3ConnectorRequest, user: AuthUser = Depends(get_current_user)):
    """Import a CSV or Excel file from an AWS S3 bucket."""
    try:
        import boto3, pandas as pd, os  # pip install boto3

        session_kwargs = {"region_name": req.region}
        if req.aws_access_key_id:
            session_kwargs["aws_access_key_id"]     = req.aws_access_key_id
            session_kwargs["aws_secret_access_key"] = req.aws_secret_access_key
        # Falls back to IAM role / env vars if no explicit creds

        s3  = boto3.client("s3", **session_kwargs)
        obj = s3.get_object(Bucket=req.bucket, Key=req.key)
        raw = io.BytesIO(obj["Body"].read())

        filename = req.key.split("/")[-1]
        if filename.endswith((".xlsx", ".xls")):
            df = pd.read_excel(raw)
        else:
            df = pd.read_csv(raw)

        session_id = str(uuid.uuid4())
        session    = DatasetSession(df=df, filename=filename, owner_id=user.user_id)
        save_session(session_id, session)
        logger.info(f"S3 connector: s3://{req.bucket}/{req.key} → session={session_id}")

        return JSONResponse({
            "session_id": session_id,
            "filename":   filename,
            "source":     f"s3://{req.bucket}/{req.key}",
            "rows":       len(df),
            "columns":    list(df.columns),
            "preview":    safe_preview(df),
        })
    except ImportError:
        raise HTTPException(status_code=501, detail="S3 connector requires: pip install boto3")
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"S3 import failed: {e}")


# ── Connector 4: SQL database ─────────────────────────────────────────────────

class DatabaseConnectorRequest(BaseModel):
    connection_string: str     # SQLAlchemy URL: postgresql://user:pass@host/db
    query:             str     # SELECT query to run
    filename:          Optional[str] = "db_query.csv"


@router.post("/connectors/database")
async def connect_database(req: DatabaseConnectorRequest,
                            user: AuthUser = Depends(get_current_user)):
    """
    Run a SELECT query against any SQLAlchemy-compatible database and
    load the result into a Datacove session.

    Supported: PostgreSQL, MySQL, SQLite, MSSQL, BigQuery (with extras).
    Row cap: 100,000 rows (server-enforced regardless of user query).
    """
    # Safety: only allow SELECT statements
    stripped = req.query.strip().upper()
    if not stripped.startswith("SELECT"):
        raise HTTPException(status_code=400, detail="Only SELECT queries are allowed.")

    # Inject a server-side row cap to prevent unbounded reads
    MAX_ROWS = 100_000
    safe_query = _cap_query(req.query, MAX_ROWS)

    try:
        import sqlalchemy as sa, pandas as pd  # pip install sqlalchemy

        engine = sa.create_engine(req.connection_string, pool_pre_ping=True)
        with engine.connect() as conn:
            df = pd.read_sql(sa.text(safe_query), conn)

        if len(df) == MAX_ROWS:
            logger.warning(
                f"DB connector: result capped at {MAX_ROWS} rows for session safety."
            )

        session_id = str(uuid.uuid4())
        session    = DatasetSession(df=df, filename=req.filename or "db_query.csv",
                                    owner_id=user.user_id)
        save_session(session_id, session)
        logger.info(f"DB connector: {len(df)} rows → session={session_id}")

        return JSONResponse({
            "session_id": session_id,
            "filename":   req.filename,
            "rows":       len(df),
            "columns":    list(df.columns),
            "preview":    safe_preview(df),
            "capped":     len(df) == MAX_ROWS,
        })
    except ImportError:
        raise HTTPException(
            status_code=501,
            detail="Database connector requires: pip install sqlalchemy "
                   "plus your DB driver (psycopg2, pymysql, etc.)",
        )
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Database import failed: {e}")


# ── Connector health check ─────────────────────────────────────────────────────

@router.get("/connectors/available")
def list_available_connectors():
    """Return which connectors are available based on installed packages."""
    available = {"url": True}  # always available (uses httpx)
    for name, pkg in [("gsheets", "gspread"), ("s3", "boto3"), ("database", "sqlalchemy")]:
        try:
            __import__(pkg)
            available[name] = True
        except ImportError:
            available[name] = False
    return JSONResponse({"connectors": available})
