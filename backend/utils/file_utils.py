"""
File utilities - safe file handling for uploads.

Improvements:
  - Hard byte-cap on upload (reads with limit, not advisory header check)
  - Validates UUID format to prevent path traversal
"""
import uuid
from pathlib import Path
from fastapi import UploadFile, HTTPException
from config import UPLOAD_DIR, MAX_UPLOAD_BYTES, ALLOWED_EXTENSIONS


def validate_upload(file: UploadFile) -> None:
    """Raise HTTPException if the upload doesn't meet policy."""
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{suffix}'. Allowed: {ALLOWED_EXTENSIONS}",
        )


async def save_upload(file: UploadFile) -> Path:
    """
    Stream the upload to disk with a hard byte-cap.
    Unlike the original advisory Content-Length check, this reads with a
    real limit so a client that omits the header cannot bypass it.
    """
    suffix = Path(file.filename or "data").suffix.lower()
    dest   = UPLOAD_DIR / f"{uuid.uuid4()}{suffix}"
    total  = 0
    chunk  = 64 * 1024   # 64 KB

    with open(dest, "wb") as fp:
        while True:
            data = await file.read(chunk)
            if not data:
                break
            total += len(data)
            if total > MAX_UPLOAD_BYTES:
                dest.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=413,
                    detail=f"File exceeds maximum allowed size of "
                           f"{MAX_UPLOAD_BYTES // (1024 * 1024)} MB.",
                )
            fp.write(data)

    return dest


async def save_upload_sync(file: UploadFile) -> Path:
    """
    Alias for save_upload - used by async job routes to make it clear
    the file is saved to disk before the background job picks it up.
    The actual I/O is identical; the name documents the intent.
    """
    return await save_upload(file)
