"""
orchestrator_routes.py - unified AI analysis endpoint.

Bug fixes applied vs deliverable:
  Bug 1: session.df → session.df_current
  Bug 2: session.add_to_history() → session.push_history(df_before, action, params)
  Bug 3: validate_session_access() → require_session() from session_guard
  Bug 4: action_id.split("_", 1) → split on "|" delimiter (handles multi-word action names)
"""
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import JSONResponse
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from typing import Optional
import pandas as pd

from models.dataset_session import get_session, save_version, persist_dataset
from services.ai_orchestrator import orchestrate_ai_analysis
from utils.auth import get_current_user, AuthUser
from utils.session_guard import require_session
from utils.logger import logger

router = APIRouter(dependencies=[Depends(get_current_user)])


class OrchestrateRequest(BaseModel):
    session_id: str
    user_goal: Optional[str] = None


class ExecuteActionRequest(BaseModel):
    session_id: str
    action_id:  str


@router.post("/ai/orchestrate")
async def orchestrate_analysis(
    req: OrchestrateRequest,
    user: AuthUser = Depends(get_current_user),
):
    """
    Run comprehensive AI analysis on a dataset.

    Orchestrates: profiling → issue detection → health score →
                  AI suggestions → structured action plan → visualizations.

    Auto-triggered after upload; also callable manually from AICommandCenter.
    """
    try:
        # BUG FIX 3: use require_session (not validate_session_access)
        session = require_session(req.session_id, user.user_id)

        logger.info(f"Orchestrator route: session={req.session_id} user={user.user_id}")

        # BUG FIX 1: use session.df_current (not session.df)
        result = await run_in_threadpool(
            orchestrate_ai_analysis,
            session.df_current,
            session.filename,
            req.user_goal,
        )

        return JSONResponse({"success": True, **result})

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Orchestrator failed session={req.session_id}: {e}")
        raise HTTPException(status_code=500, detail=f"AI analysis failed: {str(e)}")


@router.post("/ai/execute-action")
async def execute_action(
    req: ExecuteActionRequest,
    user: AuthUser = Depends(get_current_user),
):
    """
    Execute a single action from the orchestrator's action plan.
    Called when the user clicks "Apply" in AICommandCenter.

    action_id format: "{action_type}|{column_or_dataset}"
    """
    try:
        from services.cleaning_engine import apply_transformation
        from utils.explainability import explain_action

        # BUG FIX 3: require_session enforces ownership correctly
        session = require_session(req.session_id, user.user_id)

        # BUG FIX 4: split on "|" so "fill_missing|revenue" parses correctly
        parts       = req.action_id.split("|", 1)
        action_type = parts[0]
        column      = parts[1] if len(parts) > 1 and parts[1] != "dataset" else None

        logger.info(f"Execute action '{action_type}' col='{column}' session={req.session_id}")

        params: dict = {}
        if column:
            params["column"] = column
        if action_type == "fill_missing":
            params["strategy"] = "median"

        # BUG FIX 1: use session.df_current throughout
        df_before   = session.df_current.copy()
        rows_before = len(df_before)

        df_after = await run_in_threadpool(apply_transformation, df_before, action_type, params)

        rows_after    = len(df_after)
        rows_affected = abs(rows_before - rows_after)

        # BUG FIX 2: push_history(df_before, action, params) - correct name + signature
        version = len(session.versions) + 1
        session.versions.append(save_version(req.session_id, df_before, version))
        session.push_history(df_before, action_type, params)

        # BUG FIX 1: assign back to df_current
        session.df_current = df_after
        persist_dataset(req.session_id, df_after, session.filename)

        explanation = explain_action(
            action=action_type,
            column=column,
            rows_affected=rows_affected,
            params=params,
            status="applied",
        ).to_dict()

        logger.info(f"Action '{action_type}' applied - {rows_affected} rows affected")

        return JSONResponse({
            "success":     True,
            "action_id":   req.action_id,
            "rows_before": rows_before,
            "rows_after":  rows_after,
            "rows":        rows_after,
            "columns":     list(df_after.columns),
            "preview":     df_after.head(500).where(pd.notnull(df_after.head(500)), None).to_dict(orient="records"),
            "explanation": explanation,
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Execute action failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to execute action: {str(e)}")
