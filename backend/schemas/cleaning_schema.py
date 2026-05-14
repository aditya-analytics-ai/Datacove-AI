"""
Pydantic schemas for cleaning API requests and responses.
"""

from typing import Any, Dict, List
from pydantic import BaseModel


class TransformRequest(BaseModel):
    session_id: str
    action: str
    params: Dict[str, Any] = {}


class AutoCleanRequest(BaseModel):
    session_id: str
    intensity: str = "standard"
    dry_run: bool = False


class UndoRequest(BaseModel):
    session_id: str


class CleaningResult(BaseModel):
    success: bool
    rows: int
    columns: List[str]
    preview: List[Dict[str, Any]]
    message: str = ""
    version_saved: int = 0
