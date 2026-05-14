"""
sql_routes.py - DuckDB SQL endpoints.

POST /api/sql/query   - run a SELECT query, return results (read-only)
POST /api/sql/apply   - run a SELECT query and replace df_current with result
"""

from utils.request_validator import _validate_sql_query
from fastapi import APIRouter, HTTPException, Depends
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import pandas as pd

from models.dataset_session import get_session, save_version, persist_dataset
from services.sql_engine import run_sql, sql_to_dataframe
from utils.auth import get_current_user, AuthUser
from utils.preview import safe_preview
from utils.logger import logger
from utils.session_guard import require_session
from utils.errors import SQLValidationError

router = APIRouter(dependencies=[Depends(get_current_user)])


class SQLRequest(BaseModel):
    session_id: str
    query: str


def _preview(df: pd.DataFrame, n: int = 100) -> list:
    return safe_preview(df, n)


@router.post("/sql/query")
async def sql_query(req: SQLRequest, user: AuthUser = Depends(get_current_user)):
    """Execute a read-only SQL query and return results without modifying the session."""
    session = require_session(req.session_id, owner_id=user.user_id)
    logger.info(f"SQL query: session={req.session_id} user={user.user_id}")
    try:
        result = await run_in_threadpool(run_sql, session.df_current, req.query)
        return JSONResponse(result)
    except SQLValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"SQL query failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sql/apply")
async def sql_apply(req: SQLRequest, user: AuthUser = Depends(get_current_user)):
    """
    Run a SELECT query and replace df_current with the result.
    Useful for filtering, aggregating, or joining data in-place.
    """
    session = require_session(req.session_id, owner_id=user.user_id)
    df_before = session.df_current.copy()
    logger.info(f"SQL apply: session={req.session_id} user={user.user_id}")
    try:
        df_result = await run_in_threadpool(
            sql_to_dataframe, session.df_current, req.query
        )
        version = len(session.versions) + 1
        session.versions.append(save_version(req.session_id, df_before, version))
        session.push_history(df_before, "sql_apply", {"query": req.query})
        session.df_current = df_result
        persist_dataset(req.session_id, df_result, session.filename)
        return JSONResponse(
            {
                "success": True,
                "rows": len(df_result),
                "columns": list(df_result.columns),
                "preview": _preview(df_result),
                "history": session.history_as_list(),
            }
        )
    except SQLValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"SQL apply failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
