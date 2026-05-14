"""
Pydantic schemas for dataset-related API responses and requests.
Provides validation and auto-documentation via FastAPI.
"""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class DatasetUploadResponse(BaseModel):
    session_id: str
    filename: str
    rows: int
    columns: List[str]
    preview: List[Dict[str, Any]]


class DatasetSummaryResponse(BaseModel):
    session_id: str
    filename: str
    rows: int
    columns: int
    column_names: List[str]
    health: Dict[str, Any]
    top_issues: List[Dict[str, Any]]
    history_len: int
    versions: int


class CleanRequest(BaseModel):
    session_id: str
    action: str
    params: Dict[str, Any] = {}


class CleanResponse(BaseModel):
    success: bool
    rows: int
    columns: List[str]
    preview: List[Dict[str, Any]]
    history: List[Dict[str, Any]]


class SessionRequest(BaseModel):
    session_id: str
