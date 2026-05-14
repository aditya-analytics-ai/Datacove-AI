"""
AI Data Scientist routes - auto-ML: target detection, training, evaluation.
"""
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import JSONResponse
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from models.dataset_session import get_session
from services.ai_data_scientist import run_ai_data_scientist
from utils.logger import logger
from utils.auth import get_current_user, AuthUser
from utils.session_guard import require_session

router = APIRouter(dependencies=[Depends(get_current_user)])


class MLRequest(BaseModel):
    session_id: str
    target_column: Optional[str] = None




@router.post("/ai-ml/train")
async def train_model(req: MLRequest):
    """
    Auto-detect target, train a RandomForest model, and return metrics.
    Optionally pass a specific target_column.
    """
    try:
        session = require_session(req.session_id)
        df      = session.df_current
        logger.info(f"AI ML route: training for session {req.session_id}, target={req.target_column}")
        result  = await run_in_threadpool(run_ai_data_scientist, df, req.target_column)
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        return JSONResponse(result)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"ML train failed for session={req.session_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ai-ml/targets")
def suggest_targets(session_id: str):
    """Return candidate target columns ranked by likelihood."""
    try:
        session = require_session(session_id)
        df      = session.df_current

        candidates    = []
        priority_kws  = ["target", "label", "class", "output", "result",
                         "churn", "default", "fraud", "status", "outcome",
                         "price", "salary", "revenue", "score"]

        for col in df.columns:
            col_lower = col.lower()
            score     = sum(10 for kw in priority_kws if kw in col_lower)
            n_unique  = df[col].nunique()
            if 2 <= n_unique <= 20:
                score += 5
            candidates.append({"column": col, "n_unique": int(n_unique), "score": score})

        candidates.sort(key=lambda x: x["score"], reverse=True)
        return JSONResponse({"session_id": session_id, "candidates": candidates[:10]})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Suggest targets failed for session={session_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))