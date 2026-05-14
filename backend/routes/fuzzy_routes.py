"""
fuzzy_routes.py - fuzzy duplicate detection and removal endpoints.

POST /api/fuzzy/find    - find near-duplicates (read-only, returns groups)
POST /api/fuzzy/remove  - remove near-duplicates, update session
"""
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
import pandas as pd

from models.dataset_session import get_session, save_version, persist_dataset
from services.fuzzy_dedup import find_fuzzy_duplicates, remove_fuzzy_duplicates
from utils.auth import get_current_user, AuthUser
from utils.preview import safe_preview
from utils.logger import logger
from utils.session_guard import require_session

router = APIRouter(dependencies=[Depends(get_current_user)])


class FuzzyRequest(BaseModel):
    session_id: str
    columns: Optional[List[str]] = None
    threshold: int = Field(default=85, ge=50, le=100)




def _preview(df: pd.DataFrame, n: int = 100) -> list:
    return safe_preview(df, n)


@router.post("/fuzzy/find")
async def fuzzy_find(req: FuzzyRequest, user: AuthUser = Depends(get_current_user)):
    """Scan for near-duplicate rows and return groups. Does not modify the dataset."""
    session = require_session(req.session_id, owner_id=user.user_id)
    logger.info(f"Fuzzy find: session={req.session_id} threshold={req.threshold}")
    try:
        result = await run_in_threadpool(
            find_fuzzy_duplicates,
            session.df_current,
            req.columns,
            req.threshold,
        )
        return JSONResponse(result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Fuzzy find failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/fuzzy/remove")
async def fuzzy_remove(req: FuzzyRequest, user: AuthUser = Depends(get_current_user)):
    """Remove near-duplicate rows and update the session."""
    session = require_session(req.session_id, owner_id=user.user_id)
    df_before = session.df_current.copy()
    logger.info(f"Fuzzy remove: session={req.session_id} threshold={req.threshold}")
    try:
        df_after = await run_in_threadpool(
            remove_fuzzy_duplicates,
            session.df_current,
            req.columns,
            req.threshold,
        )
        removed = len(df_before) - len(df_after)
        version = len(session.versions) + 1
        session.versions.append(save_version(req.session_id, df_before, version))
        session.push_history(df_before, "fuzzy_remove_duplicates",
                             {"threshold": req.threshold, "columns": req.columns})
        session.df_current = df_after
        persist_dataset(req.session_id, df_after, session.filename)
        return JSONResponse({
            "success":      True,
            "rows_removed": removed,
            "rows":         len(df_after),
            "columns":      list(df_after.columns),
            "preview":      _preview(df_after),
            "history":      session.history_as_list(),
        })
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Fuzzy remove failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
