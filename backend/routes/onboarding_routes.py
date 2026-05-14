"""
onboarding_routes.py - sample dataset loading for new users.

GET  /api/samples          - list available sample datasets with descriptions
POST /api/samples/load     - load a sample dataset into a new session
"""
import uuid
from pathlib import Path
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import JSONResponse
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from utils.auth import get_current_user, AuthUser
from utils.preview import safe_preview
from models.dataset_session import DatasetSession, save_session
from services.dataset_loader import load_dataset
from utils.logger import logger

router = APIRouter(dependencies=[Depends(get_current_user)])

_SAMPLES_DIR = Path(__file__).resolve().parent.parent / "sample_datasets"

SAMPLE_CATALOGUE = [
    {
        "id":          "messy_customers",
        "filename":    "messy_customers.csv",
        "title":       "Messy Customer Data",
        "description": "20 customer records with duplicate rows, invalid emails, mixed date formats, negative salaries, and whitespace issues. Great for exploring the full cleaning toolkit.",
        "issues":      ["duplicates", "invalid emails", "mixed dates", "negative values", "missing data", "inconsistent casing"],
        "rows":        20,
        "columns":     8,
    },
    {
        "id":          "sales_data",
        "filename":    "sales_data.csv",
        "title":       "Sales Orders with Outliers",
        "description": "20 sales orders with price outliers, negative quantities, mixed date formats, inconsistent categories, and missing values. Perfect for numeric cleaning and outlier detection.",
        "issues":      ["outliers", "negative quantities", "mixed dates", "category variants", "missing values"],
        "rows":        20,
        "columns":     9,
    },
    {
        "id":          "hr_data",
        "filename":    "hr_data.csv",
        "title":       "HR Employee Records",
        "description": "15 employee records containing PII (SSNs, phone numbers), mixed performance score types, inconsistent boolean fields, and missing data. Ideal for PII detection and type coercion.",
        "issues":      ["PII (SSN, phone)", "mixed types", "inconsistent booleans", "missing values", "mixed dates"],
        "rows":        15,
        "columns":     10,
    },
]


class LoadSampleRequest(BaseModel):
    sample_id: str


@router.get("/samples")
def list_samples():
    """Return available sample datasets with descriptions and issue previews."""
    return JSONResponse({"samples": SAMPLE_CATALOGUE})


@router.post("/samples/load")
async def load_sample(
    req: LoadSampleRequest,
    user: AuthUser = Depends(get_current_user),
):
    """Load a sample dataset into a new session, same as a regular upload."""
    sample = next((s for s in SAMPLE_CATALOGUE if s["id"] == req.sample_id), None)
    if sample is None:
        raise HTTPException(status_code=404, detail=f"Sample '{req.sample_id}' not found.")

    file_path = _SAMPLES_DIR / sample["filename"]
    if not file_path.exists():
        raise HTTPException(status_code=500, detail="Sample file missing on server.")

    try:
        df = await run_in_threadpool(load_dataset, file_path)
        session_id = str(uuid.uuid4())
        session    = DatasetSession(
            df=df,
            filename=sample["filename"],
            owner_id=user.user_id,
        )
        save_session(session_id, session)
        logger.info(f"Sample loaded: {req.sample_id} → session={session_id} user={user.user_id}")

        return JSONResponse({
            "session_id":  session_id,
            "filename":    sample["filename"],
            "title":       sample["title"],
            "rows":        len(df),
            "columns":     list(df.columns),
            "preview":     safe_preview(df),
            "known_issues": sample["issues"],
        })
    except Exception as e:
        logger.error(f"Sample load failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
