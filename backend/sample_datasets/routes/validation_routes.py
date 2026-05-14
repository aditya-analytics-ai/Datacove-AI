"""
validation_routes.py - custom validation rule endpoints.

POST /api/validate       - run validation rules against current dataset
POST /api/validate/save  - save a named ruleset to the session
GET  /api/validate/rules - list saved rulesets for this session
"""
from typing import Any, Dict, List
from fastapi import APIRouter, HTTPException, Depends
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from models.dataset_session import get_session
from services.validation_rules import run_validation
from utils.auth import get_current_user, AuthUser
from utils.logger import logger
from utils.session_guard import require_session

router = APIRouter(dependencies=[Depends(get_current_user)])


class ValidationRequest(BaseModel):
    session_id: str
    rules: List[Dict[str, Any]]


class SaveRulesetRequest(BaseModel):
    session_id: str
    name: str
    rules: List[Dict[str, Any]]




@router.post("/validate")
async def validate(req: ValidationRequest, user: AuthUser = Depends(get_current_user)):
    """Run validation rules against the current dataset. Read-only."""
    session = require_session(req.session_id)
    logger.info(f"Validate: session={req.session_id} rules={len(req.rules)}")
    try:
        result = await run_in_threadpool(run_validation, session.df_current, req.rules)
        return JSONResponse(result)
    except Exception as e:
        logger.error(f"Validate failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/validate/save")
def save_ruleset(req: SaveRulesetRequest, user: AuthUser = Depends(get_current_user)):
    """Save a named validation ruleset to the session metadata."""
    session = require_session(req.session_id)
    if "rulesets" not in session.metadata:
        session.metadata["rulesets"] = {}
    session.metadata["rulesets"][req.name] = req.rules
    logger.info(f"Ruleset saved: '{req.name}' session={req.session_id}")
    return JSONResponse({"saved": req.name, "rules": req.rules})


@router.get("/validate/rules")
def list_rulesets(session_id: str, user: AuthUser = Depends(get_current_user)):
    """List saved validation rulesets for this session."""
    session = require_session(session_id)
    rulesets = session.metadata.get("rulesets", {})
    return JSONResponse({"session_id": session_id, "rulesets": rulesets})
