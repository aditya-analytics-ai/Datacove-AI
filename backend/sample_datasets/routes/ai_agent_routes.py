"""
AI Agent routes - run the full automated cleaning pipeline.
"""
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import JSONResponse
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from models.dataset_session import get_session, save_version, persist_dataset
from services.ai_agent import run_ai_agent
from services.nl_query_engine import parse_command
from utils.logger import logger
from utils.preview import safe_preview
from utils.auth import get_current_user, AuthUser
from utils.session_guard import require_session

router = APIRouter(dependencies=[Depends(get_current_user)])


class AgentRequest(BaseModel):
    session_id: str


class NLCommandRequest(BaseModel):
    session_id: str
    command: str
    history: list = []       # conversation history for multi-turn context
    confirmed: bool = False  # must be True to actually apply the transform



def _df_preview(df, n: int = 100):
    return safe_preview(df, n)


@router.post("/ai-agent/run")
async def run_agent(req: AgentRequest):
    """
    Run the full AI cleaning agent on the current dataset.
    Returns a comprehensive report and updates the session.
    """
    try:
        session   = require_session(req.session_id)
        df_before = session.df_current.copy()

        logger.info(f"AI Agent route: running for session {req.session_id}")
        df_cleaned, report = await run_in_threadpool(run_ai_agent, df_before)

        version = len(session.versions) + 1
        path    = save_version(req.session_id, df_before, version)
        session.versions.append(path)
        session.push_history(df_before, "ai_agent_run", {})
        session.df_current = df_cleaned
        persist_dataset(req.session_id, df_cleaned, session.filename)

        return JSONResponse({
            "success": True,
            "report":  report,
            "rows":    len(df_cleaned),
            "columns": list(df_cleaned.columns),
            "preview": _df_preview(df_cleaned),
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"AI Agent run failed for session={req.session_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ai-agent/nl-clean")
async def nl_clean(req: NLCommandRequest):
    """
    Two-step NL command endpoint.

    Step 1 - Parse (confirmed=False, default):
      Returns the parsed action + params for user confirmation.
      Does NOT modify the dataset.

    Step 2 - Apply (confirmed=True):
      Applies the previously parsed action to the dataset.
      The client should pass the same command + history so the parse
      result is reproduced (idempotent given the same LLM call).
    """
    from services.cleaning_engine import apply_transformation, auto_clean

    try:
        session   = require_session(req.session_id)
        df_before = session.df_current.copy()

        parsed = await run_in_threadpool(
            parse_command, req.command, list(df_before.columns), req.history
        )

        if "error" in parsed:
            raise HTTPException(status_code=400, detail=parsed["error"])

        action = parsed.get("action", "")
        params = parsed.get("params", {})

        # ── Step 1: return preview without applying ───────────────────────────
        if not req.confirmed:
            return JSONResponse({
                "success":       True,
                "confirmed":     False,
                "parsed_action": parsed,
                "message": (
                    f"Understood: will run '{action}'"
                    + (f" on column '{params.get('column')}'" if params.get("column") else "")
                    + ". Send with confirmed=true to apply."
                ),
            })

        # ── Step 2: apply ─────────────────────────────────────────────────────
        if action == "auto_clean":
            df_after = await run_in_threadpool(auto_clean, df_before)
        else:
            df_after = await run_in_threadpool(apply_transformation, df_before, action, params)

        session.push_history(df_before, action, params)
        session.df_current = df_after
        persist_dataset(req.session_id, df_after, session.filename)

        return JSONResponse({
            "success":       True,
            "confirmed":     True,
            "parsed_action": parsed,
            "rows":          len(df_after),
            "columns":       list(df_after.columns),
            "preview":       _df_preview(df_after),
        })
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as e:
        logger.error(f"NL clean failed for session={req.session_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ai-agent/versions")
def list_versions(session_id: str):
    """List all saved dataset versions for a session."""
    try:
        session = require_session(session_id)
        return JSONResponse({
            "session_id": session_id,
            "versions":   session.versions,
            "count":      len(session.versions),
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"List versions failed for session={session_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))