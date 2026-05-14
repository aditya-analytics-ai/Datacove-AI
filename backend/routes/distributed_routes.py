"""
Distributed Processing API - scales data operations to billions of rows.

Endpoints:
  POST /distributed/profile      - Profile a dataset and get scaling recommendations
  POST /distributed/process      - Process a DataFrame with distributed execution
  POST /distributed/process-file - Process a large file (CSV/Parquet) in chunks
  GET  /distributed/status/{job_id} - Get job status and progress
  GET  /distributed/partitions   - Get partition info for a dataset
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor
import tempfile
import os

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field

from middleware.auth import get_current_user_id
from services.distributed_processor import (
    DistributedProcessingEngine,
    DistributedConfig,
    ChunkedFileProcessor,
    ProcessingMode,
    SMALL_DATASET_THRESHOLD,
    MEDIUM_DATASET_THRESHOLD,
    LARGE_DATASET_THRESHOLD,
    DASK_AVAILABLE,
)
from services.dataset_loader import load_dataset_by_id
from utils.logger import logger


router = APIRouter(prefix="/distributed", tags=["Distributed Processing"])

# In-memory job store for background processing status
_job_store: Dict[str, Dict[str, Any]] = {}
_executor = ThreadPoolExecutor(max_workers=4)


# ── Request/Response Models ────────────────────────────────────────────────────


class ProfileRequest(BaseModel):
    dataset_id: str
    session_id: Optional[str] = None


class ProfileResponse(BaseModel):
    row_count: int
    column_count: int
    memory_mb: float
    dtypes: Dict[str, str]
    null_counts: Dict[str, int]
    recommended_mode: str
    recommended_partitions: Optional[int] = None
    scaling_recommendations: Dict[str, Any]


class ProcessRequest(BaseModel):
    dataset_id: str
    transformations: List[Dict[str, Any]]
    mode: Optional[str] = Field(
        default="auto",
        description="'auto', 'pandas', 'dask_local', 'dask_cluster', 'streaming'",
    )
    n_workers: Optional[int] = Field(default=4, ge=1, le=64)
    threads_per_worker: Optional[int] = Field(default=2, ge=1, le=16)
    memory_limit_per_worker: Optional[str] = Field(default="4GB")
    checkpoint_enabled: bool = Field(default=False)
    session_id: Optional[str] = None


class ProcessResponse(BaseModel):
    job_id: str
    status: str
    message: str


class ProcessFileRequest(BaseModel):
    source_type: str = Field(description="'csv', 'parquet', 'jsonl'")
    source_path: str = Field(description="File path or S3 URI")
    output_path: Optional[str] = None
    transformations: List[Dict[str, Any]]
    chunk_size: int = Field(default=100_000, ge=10_000, le=1_000_000)
    checkpoint_enabled: bool = Field(default=True)
    row_group_size: Optional[int] = Field(default=None, description="For Parquet files")
    encoding: Optional[str] = Field(default="utf-8")
    usecols: Optional[List[str]] = Field(default=None, description="Columns to load")
    dtype: Optional[Dict[str, str]] = Field(
        default=None, description="Column dtype hints"
    )


class ProcessFileResponse(BaseModel):
    job_id: str
    status: str
    output_path: Optional[str] = None


class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    progress: Optional[Dict[str, Any]] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


class PartitionInfoRequest(BaseModel):
    dataset_id: str
    target_partition_size_mb: int = Field(default=128, ge=16, le=1024)


class PartitionInfoResponse(BaseModel):
    total_rows: int
    total_partitions: int
    estimated_memory_mb: float
    partition_size_mb: int
    recommended_chunk_size: int


# ── Endpoints ──────────────────────────────────────────────────────────────────


@router.post("/profile", response_model=ProfileResponse)
def profile_dataset(
    request: ProfileRequest,
    user_id: str = Depends(get_current_user_id),
):
    """
    Profile a dataset and get scaling recommendations.

    Returns statistics and suggests the optimal processing mode
    based on dataset size and available infrastructure.
    """
    df = load_dataset_by_id(request.dataset_id, request.session_id, user_id)
    if df is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    config = DistributedConfig()
    with DistributedProcessingEngine(config) as engine:
        stats = engine.profile_distributed(df)

    row_count = stats["row_count"]

    recommendations = {
        "thresholds": {
            "small_dataset": f"< {SMALL_DATASET_THRESHOLD:,} rows",
            "medium_dataset": f"{SMALL_DATASET_THRESHOLD:,} - {MEDIUM_DATASET_THRESHOLD:,} rows",
            "large_dataset": f"{MEDIUM_DATASET_THRESHOLD:,} - {LARGE_DATASET_THRESHOLD:,} rows",
            "extreme_dataset": f"> {LARGE_DATASET_THRESHOLD:,} rows",
        },
        "current_tier": (
            "small"
            if row_count < SMALL_DATASET_THRESHOLD
            else "medium"
            if row_count < MEDIUM_DATASET_THRESHOLD
            else "large"
            if row_count < LARGE_DATASET_THRESHOLD
            else "extreme"
        ),
        "dask_available": DASK_AVAILABLE,
        "tips": [],
    }

    if row_count < SMALL_DATASET_THRESHOLD:
        recommendations["tips"].append(
            "Dataset is small enough for standard pandas processing"
        )
    elif row_count < MEDIUM_DATASET_THRESHOLD:
        recommendations["tips"].append(
            "Consider Dask local mode for faster parallel processing"
        )
    else:
        recommendations["tips"].append("Enable checkpointing for fault tolerance")
        if not DASK_AVAILABLE:
            recommendations["tips"].append(
                "Install dask[dataframe] for distributed processing"
            )

    return ProfileResponse(
        row_count=stats["row_count"],
        column_count=stats["column_count"],
        memory_mb=stats["memory_mb"],
        dtypes=stats["dtypes"],
        null_counts=stats["null_counts"],
        recommended_mode=stats["recommended_mode"],
        recommended_partitions=stats.get("recommended_partitions"),
        scaling_recommendations=recommendations,
    )


@router.post("/process", response_model=ProcessResponse)
def process_dataset(
    request: ProcessRequest,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_current_user_id),
):
    """
    Process a dataset using distributed execution.

    Returns immediately with a job_id. Use GET /distributed/status/{job_id}
    to poll for progress and results.
    """
    job_id = str(uuid.uuid4())
    mode = (
        ProcessingMode(request.mode)
        if request.mode != "auto"
        else ProcessingMode.PANDAS
    )

    config = DistributedConfig(
        mode=mode,
        n_workers=request.n_workers,
        threads_per_worker=request.threads_per_worker,
        memory_limit_per_worker=request.memory_limit_per_worker,
        checkpoint_dir=tempfile.mkdtemp() if request.checkpoint_enabled else None,
    )

    _job_store[job_id] = {
        "status": "queued",
        "config": {
            "dataset_id": request.dataset_id,
            "transformations": request.transformations,
            "mode": request.mode,
            "n_workers": request.n_workers,
            "checkpoint_enabled": request.checkpoint_enabled,
        },
        "started_at": datetime.now(timezone.utc).isoformat(),
        "user_id": user_id,
    }

    def _run_job():
        try:
            df = load_dataset_by_id(request.dataset_id, request.session_id, user_id)
            if df is None:
                _job_store[job_id]["status"] = "failed"
                _job_store[job_id]["error"] = "Dataset not found"
                return

            _job_store[job_id]["status"] = "running"

            with DistributedProcessingEngine(config) as engine:
                result = engine.process_dataframe(df, request.transformations)

            _job_store[job_id]["status"] = "completed" if result.success else "failed"
            _job_store[job_id]["result"] = {
                "rows_total": result.rows_total,
                "rows_modified": result.rows_modified,
                "partitions_completed": result.partitions_completed,
                "partitions_failed": result.partitions_failed,
                "duration_seconds": result.duration_seconds,
                "mode": result.mode.value,
                "errors": result.errors,
            }
            _job_store[job_id]["completed_at"] = datetime.now(timezone.utc).isoformat()

        except Exception as e:
            _job_store[job_id]["status"] = "failed"
            _job_store[job_id]["error"] = str(e)
            logger.error(f"Distributed job {job_id} failed: {e}")

    _executor.submit(_run_job)

    return ProcessResponse(
        job_id=job_id,
        status="queued",
        message=f"Processing job {job_id} queued. Poll /distributed/status/{job_id} for progress.",
    )


@router.post("/process-file", response_model=ProcessFileResponse)
def process_large_file(
    request: ProcessFileRequest,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_current_user_id),
):
    """
    Process a large file that doesn't fit in memory.

    Supports CSV, Parquet, and JSONL formats. Uses chunked processing
    with optional checkpointing for fault tolerance.
    """
    job_id = str(uuid.uuid4())
    output_path = request.output_path or os.path.join(
        tempfile.mkdtemp(), f"processed_{job_id}.{request.source_type}"
    )

    _job_store[job_id] = {
        "status": "queued",
        "source_type": request.source_type,
        "source_path": request.source_path,
        "output_path": output_path,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "user_id": user_id,
    }

    def _run_file_job():
        try:
            _job_store[job_id]["status"] = "running"

            processor = ChunkedFileProcessor(
                chunk_size=request.chunk_size,
                checkpoint_dir=tempfile.mkdtemp()
                if request.checkpoint_enabled
                else None,
            )

            if request.source_type == "csv":
                iterator = processor.process_csv(
                    request.source_path,
                    output_path,
                    request.transformations,
                    usecols=request.usecols,
                    dtype=request.dtype,
                    encoding=request.encoding or "utf-8",
                )
            elif request.source_type == "parquet":
                iterator = processor.process_parquet(
                    request.source_path,
                    output_path,
                    request.transformations,
                    row_group_size=request.row_group_size,
                )
            else:
                raise ValueError(f"Unsupported source type: {request.source_type}")

            final_status = None
            for progress in iterator:
                _job_store[job_id]["progress"] = progress
                if progress["status"] in ("completed", "error"):
                    final_status = progress

            _job_store[job_id]["status"] = "completed"
            _job_store[job_id]["result"] = final_status
            _job_store[job_id]["completed_at"] = datetime.now(timezone.utc).isoformat()

        except Exception as e:
            _job_store[job_id]["status"] = "failed"
            _job_store[job_id]["error"] = str(e)
            logger.error(f"File processing job {job_id} failed: {e}")

    _executor.submit(_run_file_job)

    return ProcessFileResponse(
        job_id=job_id,
        status="queued",
        output_path=output_path,
    )


@router.get("/status/{job_id}", response_model=JobStatusResponse)
def get_job_status(
    job_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Get the status and progress of a distributed processing job."""
    if job_id not in _job_store:
        raise HTTPException(status_code=404, detail="Job not found")

    job = _job_store[job_id]

    if job.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    return JobStatusResponse(
        job_id=job_id,
        status=job["status"],
        progress=job.get("progress"),
        result=job.get("result"),
        error=job.get("error"),
        started_at=job.get("started_at"),
        completed_at=job.get("completed_at"),
    )


@router.post("/partitions", response_model=PartitionInfoResponse)
def get_partition_info(
    request: PartitionInfoRequest,
    user_id: str = Depends(get_current_user_id),
):
    """
    Calculate optimal partition configuration for a dataset.

    Helps determine chunk sizes and number of workers for distributed processing.
    """
    df = load_dataset_by_id(request.dataset_id, None, user_id)
    if df is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    row_count = len(df)
    memory_bytes = df.memory_usage(deep=True).sum()
    memory_mb = memory_bytes / 1_048_576

    estimated_partitions = max(1, int(memory_mb / request.target_partition_size_mb))
    recommended_chunk_size = (
        max(10_000, row_count // estimated_partitions)
        if estimated_partitions > 0
        else request.chunk_size
    )

    return PartitionInfoResponse(
        total_rows=row_count,
        total_partitions=estimated_partitions,
        estimated_memory_mb=round(memory_mb, 2),
        partition_size_mb=request.target_partition_size_mb,
        recommended_chunk_size=recommended_chunk_size,
    )


@router.get("/modes")
def get_processing_modes():
    """List available processing modes and their capabilities."""
    return {
        "modes": [
            {
                "name": "pandas",
                "display_name": "Standard Pandas",
                "description": "Single-threaded pandas processing. Best for <1M rows.",
                "max_rows": SMALL_DATASET_THRESHOLD,
                "requires_dask": False,
                "distributed": False,
            },
            {
                "name": "dask_local",
                "display_name": "Dask Local",
                "description": "Parallel processing with local threads/processes. Best for 1M-100M rows.",
                "max_rows": MEDIUM_DATASET_THRESHOLD,
                "requires_dask": True,
                "distributed": True,
            },
            {
                "name": "dask_cluster",
                "display_name": "Dask Cluster",
                "description": "Distributed processing on a Dask cluster. Best for 100M-1B rows.",
                "max_rows": LARGE_DATASET_THRESHOLD,
                "requires_dask": True,
                "distributed": True,
            },
            {
                "name": "streaming",
                "display_name": "Streaming",
                "description": "Chunked streaming for >1B rows. Checkpoints for fault tolerance.",
                "max_rows": None,
                "requires_dask": False,
                "distributed": True,
            },
        ],
        "dask_available": DASK_AVAILABLE,
        "thresholds": {
            "small": SMALL_DATASET_THRESHOLD,
            "medium": MEDIUM_DATASET_THRESHOLD,
            "large": LARGE_DATASET_THRESHOLD,
        },
    }


@router.delete("/job/{job_id}")
def cancel_job(
    job_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Cancel a running or queued job."""
    if job_id not in _job_store:
        raise HTTPException(status_code=404, detail="Job not found")

    job = _job_store[job_id]
    if job.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    if job["status"] in ("completed", "failed"):
        raise HTTPException(status_code=400, detail="Job already finished")

    job["status"] = "cancelled"
    return {"job_id": job_id, "status": "cancelled"}


@router.delete("/cleanup")
def cleanup_completed_jobs(user_id: str = Depends(get_current_user_id)):
    """Remove completed jobs from the job store."""
    global _job_store
    _job_store = {k: v for k, v in _job_store.items() if v.get("user_id") != user_id}
    return {"status": "ok", "message": "Cleanup complete"}
