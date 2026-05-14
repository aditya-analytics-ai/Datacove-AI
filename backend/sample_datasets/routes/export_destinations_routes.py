"""
export_destinations_routes.py - push cleaned data to external destinations.

POST /api/export/gsheets    - push to Google Sheets (create or update)
POST /api/export/airtable   - push to an Airtable base
POST /api/export/notion     - push to a Notion database
POST /api/export/slack      - send a summary report to a Slack channel
"""
import io
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from utils.auth import get_current_user, AuthUser
from utils.session_guard import require_session
from utils.billing import enforce_feature
from utils.logger import logger

router = APIRouter(dependencies=[Depends(get_current_user)])


# ── Google Sheets export ──────────────────────────────────────────────────────

class GSheetsExportRequest(BaseModel):
    session_id:           str
    spreadsheet_id:       Optional[str] = None   # None = create new
    sheet_name:           str = "Cleaned Data"
    service_account_json: Optional[str] = None


@router.post("/export/gsheets")
async def export_to_gsheets(req: GSheetsExportRequest,
                             user: AuthUser = Depends(get_current_user)):
    enforce_feature(user.user_id, "connectors")
    session = require_session(req.session_id, owner_id=user.user_id)
    df = session.df_current

    try:
        import gspread
        from google.oauth2.service_account import Credentials
        import json, os

        sa_json = req.service_account_json or os.getenv("GOOGLE_SA_JSON")
        if not sa_json:
            raise HTTPException(status_code=400, detail="No service account credentials provided.")

        creds = Credentials.from_service_account_info(
            json.loads(sa_json),
            scopes=[
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive.file",
            ],
        )
        gc = gspread.authorize(creds)

        # Create new spreadsheet or open existing
        if req.spreadsheet_id:
            sh = gc.open_by_key(req.spreadsheet_id)
            try:
                ws = sh.worksheet(req.sheet_name)
                ws.clear()
            except gspread.WorksheetNotFound:
                ws = sh.add_worksheet(req.sheet_name, rows=len(df)+1, cols=len(df.columns))
        else:
            sh = gc.create(f"Datacove Export - {session.filename}")
            ws = sh.sheet1
            ws.update_title(req.sheet_name)

        # Write header + data
        rows = [df.columns.tolist()] + df.fillna("").astype(str).values.tolist()
        ws.update(rows)

        logger.info(f"GSheets export: session={req.session_id} → {sh.id}")
        return JSONResponse({
            "success":        True,
            "spreadsheet_id": sh.id,
            "sheet_name":     ws.title,
            "rows_written":   len(df),
            "url":            f"https://docs.google.com/spreadsheets/d/{sh.id}",
        })
    except ImportError:
        raise HTTPException(status_code=501,
            detail="Requires: pip install gspread google-auth")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Google Sheets export failed: {e}")


# ── Airtable export ───────────────────────────────────────────────────────────

class AirtableExportRequest(BaseModel):
    session_id:  str
    base_id:     str
    table_name:  str
    api_key:     Optional[str] = None   # or set AIRTABLE_API_KEY env var


@router.post("/export/airtable")
async def export_to_airtable(req: AirtableExportRequest,
                              user: AuthUser = Depends(get_current_user)):
    enforce_feature(user.user_id, "connectors")
    session = require_session(req.session_id, owner_id=user.user_id)
    df = session.df_current

    try:
        import httpx, os, json

        api_key = req.api_key or os.getenv("AIRTABLE_API_KEY")
        if not api_key:
            raise HTTPException(status_code=400, detail="No Airtable API key provided.")

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type":  "application/json",
        }
        base_url = f"https://api.airtable.com/v0/{req.base_id}/{req.table_name}"

        # Airtable accepts up to 10 records per request
        records_created = 0
        rows = df.fillna("").astype(str).to_dict(orient="records")

        async with httpx.AsyncClient(timeout=30) as client:
            for i in range(0, len(rows), 10):
                batch = rows[i:i+10]
                payload = {"records": [{"fields": r} for r in batch]}
                resp = await client.post(base_url, headers=headers, json=payload)
                if resp.status_code not in (200, 201):
                    raise HTTPException(status_code=422,
                        detail=f"Airtable error: {resp.text[:200]}")
                records_created += len(batch)

        logger.info(f"Airtable export: session={req.session_id} → {req.base_id}/{req.table_name}")
        return JSONResponse({
            "success":         True,
            "base_id":         req.base_id,
            "table_name":      req.table_name,
            "records_created": records_created,
        })
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Airtable export failed: {e}")


# ── Notion export ──────────────────────────────────────────────────────────────

class NotionExportRequest(BaseModel):
    session_id:    str
    database_id:   str
    api_key:       Optional[str] = None
    max_rows:      int = 2000    # configurable ceiling; Notion charges API calls


@router.post("/export/notion")
async def export_to_notion(req: NotionExportRequest,
                            user: AuthUser = Depends(get_current_user)):
    enforce_feature(user.user_id, "connectors")
    session = require_session(req.session_id, owner_id=user.user_id)
    df = session.df_current.head(req.max_rows)  # respect caller-controlled limit

    try:
        import httpx, os

        api_key = req.api_key or os.getenv("NOTION_API_KEY")
        if not api_key:
            raise HTTPException(status_code=400, detail="No Notion API key provided.")

        headers = {
            "Authorization":  f"Bearer {api_key}",
            "Content-Type":   "application/json",
            "Notion-Version": "2022-06-28",
        }

        rows_written = 0
        errors = []
        first_col = df.columns[0]

        async with httpx.AsyncClient(timeout=30) as client:
            for _, row in df.fillna("").iterrows():
                # Build Notion properties - all as rich_text for compatibility
                properties = {}
                for col in df.columns:
                    val = str(row[col])
                    properties[col] = {"rich_text": [{"text": {"content": val[:2000]}}]}
                # First column is always the page title
                properties[first_col] = {"title": [{"text": {"content": str(row[first_col])[:2000]}}]}

                payload = {"parent": {"database_id": req.database_id}, "properties": properties}
                resp = await client.post("https://api.notion.com/v1/pages",
                                         headers=headers, json=payload)
                if resp.status_code in (200, 201):
                    rows_written += 1
                else:
                    # Log error but continue - don't abort the whole export on one row
                    errors.append({"row": rows_written, "detail": resp.text[:200]})
                    if len(errors) >= 10:
                        break   # stop if too many failures

        logger.info(f"Notion export: session={req.session_id} → db={req.database_id} wrote={rows_written}")
        return JSONResponse({
            "success":      rows_written > 0,
            "database_id":  req.database_id,
            "rows_written": rows_written,
            "errors":       errors if errors else None,
            "truncated":    len(session.df_current) > req.max_rows,
            "note":         f"Exported {rows_written}/{len(session.df_current)} rows." if len(session.df_current) > req.max_rows else None,
        })
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Notion export failed: {e}")


# ── Slack summary ──────────────────────────────────────────────────────────────

class SlackSummaryRequest(BaseModel):
    session_id:   str
    webhook_url:  str   # Slack incoming webhook URL


@router.post("/export/slack")
async def send_slack_summary(req: SlackSummaryRequest,
                              user: AuthUser = Depends(get_current_user)):
    session = require_session(req.session_id, owner_id=user.user_id)
    df = session.df_current
    health = session.metadata.get("last_health", {})
    score  = health.get("score", "-")
    grade  = health.get("grade", "-")

    try:
        import httpx
        message = {
            "text": f"*Datacove Report - {session.filename}*",
            "blocks": [
                {"type": "header", "text": {"type": "plain_text",
                    "text": f"📊 Datacove Report: {session.filename}"}},
                {"type": "section", "fields": [
                    {"type": "mrkdwn", "text": f"*Rows:*\n{len(df):,}"},
                    {"type": "mrkdwn", "text": f"*Columns:*\n{len(df.columns)}"},
                    {"type": "mrkdwn", "text": f"*Health Score:*\n{score}/100 (Grade {grade})"},
                    {"type": "mrkdwn", "text": f"*Missing:*\n{health.get('missing_pct', '-')}%"},
                ]},
                {"type": "divider"},
                {"type": "section", "text": {"type": "mrkdwn",
                    "text": "_Sent from Datacove AI Data Platform_"}},
            ],
        }
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(req.webhook_url, json=message)
            if resp.status_code != 200:
                raise HTTPException(status_code=422, detail=f"Slack error: {resp.text}")

        return JSONResponse({"success": True, "message": "Summary sent to Slack."})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Slack export failed: {e}")
