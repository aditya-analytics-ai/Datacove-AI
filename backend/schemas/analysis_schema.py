"""
Pydantic schemas for analysis API responses.
"""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class HealthScore(BaseModel):
    score: float
    grade: str
    deductions: List[Dict[str, Any]] = []


class AnalysisResponse(BaseModel):
    profile: Dict[str, Any]
    issues: List[Dict[str, Any]]
    health: Dict[str, Any]
    anomalies: List[Dict[str, Any]]
    suggestions: List[str]


class NLCommandRequest(BaseModel):
    session_id: str
    command: str


class CompareRequest(BaseModel):
    session_id_a: str
    session_id_b: str
