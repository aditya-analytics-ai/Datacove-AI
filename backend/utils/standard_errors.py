"""
standard_errors.py - Standardized error responses for all endpoints.

This module provides consistent error handling across the API without
modifying existing error handling. New endpoints should use these.

Example:
    from utils.standard_errors import error_response
    
    raise error_response(
        status_code=400,
        error_code="VALIDATION_ERROR",
        message="Invalid dataset format",
        details={"allowed_formats": ["csv", "xlsx"]}
    )
"""

from enum import Enum
from typing import Optional, Dict, Any
from fastapi import HTTPException
from pydantic import BaseModel


class ErrorCode(str, Enum):
    """Standardized error codes for API responses."""
    # Authentication errors (4xx)
    UNAUTHORIZED = "UNAUTHORIZED"
    INVALID_TOKEN = "INVALID_TOKEN"
    TOKEN_EXPIRED = "TOKEN_EXPIRED"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    
    # Validation errors (4xx)
    VALIDATION_ERROR = "VALIDATION_ERROR"
    INVALID_FORMAT = "INVALID_FORMAT"
    MISSING_REQUIRED = "MISSING_REQUIRED"
    
    # Resource errors (4xx)
    NOT_FOUND = "NOT_FOUND"
    SESSION_NOT_FOUND = "SESSION_NOT_FOUND"
    DATASET_NOT_FOUND = "DATASET_NOT_FOUND"
    CONFLICT = "CONFLICT"
    DUPLICATE_RESOURCE = "DUPLICATE_RESOURCE"
    
    # Rate limiting (4xx)
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
    AI_RATE_LIMIT = "AI_RATE_LIMIT"
    
    # Processing errors (5xx)
    PROCESSING_ERROR = "PROCESSING_ERROR"
    DATABASE_ERROR = "DATABASE_ERROR"
    EXTERNAL_SERVICE_ERROR = "EXTERNAL_SERVICE_ERROR"
    TIMEOUT = "TIMEOUT"
    
    # Generic (5xx)
    INTERNAL_ERROR = "INTERNAL_ERROR"


class StandardErrorResponse(BaseModel):
    """Standard error response format for all endpoints."""
    status: int
    error_code: ErrorCode
    message: str
    details: Optional[Dict[str, Any]] = None
    request_id: Optional[str] = None  # For tracing


def error_response(
    status_code: int,
    error_code: ErrorCode,
    message: str,
    details: Optional[Dict[str, Any]] = None,
    request_id: Optional[str] = None,
) -> HTTPException:
    """
    Create a standardized HTTPException.
    
    Args:
        status_code: HTTP status code
        error_code: ErrorCode enum value
        message: Human-readable error message
        details: Optional error details (e.g., validation errors)
        request_id: Optional request ID for tracing
    
    Returns:
        HTTPException with standardized content
    
    Example:
        raise error_response(
            status_code=400,
            error_code=ErrorCode.VALIDATION_ERROR,
            message="Invalid CSV format",
            details={"line": 5, "error": "Missing column 'name'"}
        )
    """
    exc = HTTPException(
        status_code=status_code,
        detail={
            "status": status_code,
            "error_code": error_code.value,
            "message": message,
            "details": details,
            "request_id": request_id,
        }
    )
    return exc


def validation_error(
    message: str,
    details: Optional[Dict[str, Any]] = None,
    request_id: Optional[str] = None,
) -> HTTPException:
    """Shorthand for validation errors."""
    return error_response(
        status_code=400,
        error_code=ErrorCode.VALIDATION_ERROR,
        message=message,
        details=details,
        request_id=request_id,
    )


def not_found_error(
    resource_type: str,
    resource_id: str,
    request_id: Optional[str] = None,
) -> HTTPException:
    """Shorthand for resource not found errors."""
    return error_response(
        status_code=404,
        error_code=ErrorCode.NOT_FOUND,
        message=f"{resource_type} '{resource_id}' not found",
        request_id=request_id,
    )


def auth_error(
    message: str = "Authentication required",
    request_id: Optional[str] = None,
) -> HTTPException:
    """Shorthand for authentication errors."""
    return error_response(
        status_code=401,
        error_code=ErrorCode.UNAUTHORIZED,
        message=message,
        request_id=request_id,
    )


def permission_error(
    message: str = "Permission denied",
    request_id: Optional[str] = None,
) -> HTTPException:
    """Shorthand for permission errors."""
    return error_response(
        status_code=403,
        error_code=ErrorCode.PERMISSION_DENIED,
        message=message,
        request_id=request_id,
    )


def rate_limit_error(
    retry_after: int,
    request_id: Optional[str] = None,
) -> HTTPException:
    """Shorthand for rate limit errors."""
    exc = error_response(
        status_code=429,
        error_code=ErrorCode.RATE_LIMIT_EXCEEDED,
        message=f"Rate limit exceeded. Retry after {retry_after} seconds",
        details={"retry_after": retry_after},
        request_id=request_id,
    )
    exc.headers = {"Retry-After": str(retry_after)}
    return exc


def processing_error(
    message: str,
    details: Optional[Dict[str, Any]] = None,
    request_id: Optional[str] = None,
) -> HTTPException:
    """Shorthand for processing errors."""
    return error_response(
        status_code=500,
        error_code=ErrorCode.PROCESSING_ERROR,
        message=message,
        details=details,
        request_id=request_id,
    )
