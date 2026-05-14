"""
ai_copilot_routes.py - Natural Language to Pipeline API.

POST /api/copilot/nl-to-pipeline    - Convert NL command to pipeline steps
POST /api/copilot/suggest           - Get AI cleaning suggestions
GET  /api/copilot/explain/{column}  - Get AI explanation of a column
POST /api/copilot/ask               - Ask a question about the dataset
POST /api/copilot/story             - Generate a data story
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import JSONResponse
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from utils.session_guard import require_session
from services.ai_copilot import get_copilot, PipelineFromNL
from services.profiling_engine import profile_dataset
from services.issue_detector import detect_issues
from utils.auth import get_current_user, AuthUser
from utils.billing import enforce_ai
from utils.logger import logger

router = APIRouter(prefix="/copilot", dependencies=[Depends(get_current_user)])


class NLToPipelineRequest(BaseModel):
    session_id: str
    command: str  # e.g., "remove duplicates, fill missing ages with median"


class SuggestRequest(BaseModel):
    session_id: str
    include_issues: bool = True


class AskRequest(BaseModel):
    session_id: str
    question: str


@router.post("/nl-to-pipeline")
async def nl_to_pipeline(
    req: NLToPipelineRequest, user: AuthUser = Depends(get_current_user)
):
    """
    Convert a natural language command into pipeline steps.

    Example:
      command: "remove duplicates, fill missing ages with median, normalize prices"
    """
    enforce_ai(user.user_id)

    session = require_session(req.session_id, owner_id=user.user_id)
    df = session.df_current

    columns = list(df.columns)
    column_types = {col: str(dtype) for col, dtype in df.dtypes.items()}
    sample_data = df.head(3).to_dict(orient="records")

    def _convert():
        copilot = get_copilot()
        return copilot.nl_to_pipeline(req.command, columns, column_types, sample_data)

    result: PipelineFromNL = await run_in_threadpool(_convert)

    logger.info(f"NL to pipeline: '{req.command}' → {len(result.steps)} steps")

    return JSONResponse(
        {
            "command": req.command,
            "steps": result.steps,
            "explanation": result.explanation,
            "warnings": result.warnings,
        }
    )


@router.post("/suggest")
async def suggest_cleaning(
    req: SuggestRequest, user: AuthUser = Depends(get_current_user)
):
    """
    Get AI-powered cleaning suggestions based on data profile and issues.
    """
    enforce_ai(user.user_id)

    session = require_session(req.session_id, owner_id=user.user_id)
    df = session.df_current

    def _profile():
        return profile_dataset(df)

    def _detect_issues():
        return detect_issues(df)

    profile, issues = await run_in_threadpool(_profile, _detect_issues)
    issues = issues[:20]

    def _suggest():
        copilot = get_copilot()
        return copilot.suggest_cleaning(profile, issues, list(df.columns))

    suggestions = await run_in_threadpool(_suggest)

    return JSONResponse(
        {
            "suggestions": [
                {
                    "action": s.action,
                    "params": s.params,
                    "reason": s.reason,
                    "confidence": s.confidence,
                    "impact": s.impact,
                }
                for s in suggestions
            ],
            "based_on": {
                "rows": len(df),
                "columns": len(df.columns),
                "issues_found": len(issues),
            },
        }
    )


@router.get("/explain/{column}")
async def explain_column(
    column: str, session_id: str, user: AuthUser = Depends(get_current_user)
):
    """Get AI explanation of a specific column."""
    enforce_ai(user.user_id)

    session = require_session(session_id, owner_id=user.user_id)
    df = session.df_current

    if column not in df.columns:
        raise HTTPException(status_code=404, detail=f"Column '{column}' not found")

    def _profile_column():
        return profile_dataset(df)[["columns"]]

    profile = await run_in_threadpool(profile_dataset, df)

    col_profile = next(
        (c for c in profile.get("columns", []) if c["name"] == column), {}
    )

    def _explain():
        copilot = get_copilot()
        return copilot.explain_column(column, col_profile)

    explanation = await run_in_threadpool(_explain)

    return JSONResponse(
        {
            "column": column,
            "explanation": explanation,
            "profile": col_profile,
        }
    )


@router.post("/ask")
async def ask_question(req: AskRequest, user: AuthUser = Depends(get_current_user)):
    """Ask a question about the dataset in natural language."""
    enforce_ai(user.user_id)

    session = require_session(req.session_id, owner_id=user.user_id)
    df = session.df_current

    profile = await run_in_threadpool(profile_dataset, df)
    sample_data = df.head(5).to_dict(orient="records")

    def _ask():
        copilot = get_copilot()
        return copilot.answer_question(req.question, profile, sample_data)

    answer = await run_in_threadpool(_ask)

    logger.info(f"Copilot Q&A: '{req.question[:50]}...' → answered")

    return JSONResponse(
        {
            "question": req.question,
            "answer": answer,
        }
    )


@router.post("/story")
async def generate_story(
    req: SuggestRequest, user: AuthUser = Depends(get_current_user)
):
    """Generate an AI-powered data story summarizing the dataset."""
    enforce_ai(user.user_id)

    session = require_session(req.session_id, owner_id=user.user_id)
    df = session.df_current

    def _tasks():
        prof = profile_dataset(df)
        issues = detect_issues(df) if req.include_issues else []
        return prof, issues

    profile, issues = await run_in_threadpool(_tasks)

    insights = [
        f"{len(df)} rows, {len(df.columns)} columns",
        f"Health score: {profile.get('health_score', 'N/A')}",
        f"Issues found: {len(issues)}",
    ]

    def _story():
        copilot = get_copilot()
        return copilot.generate_story(profile, insights)

    story = await run_in_threadpool(_story)

    return JSONResponse(
        {
            "story": story,
            "profile": {
                "rows": len(df),
                "columns": len(df.columns),
                "duplicate_rows": profile.get("duplicate_count", 0),
                "missing_total": profile.get("missing_total", 0),
            },
        }
    )
