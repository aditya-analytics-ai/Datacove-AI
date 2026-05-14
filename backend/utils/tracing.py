"""
tracing.py - Distributed tracing and correlation IDs for observability.

Enhances logging with request tracing. Non-breaking addition that
integrates with existing logging.

Example:
    from utils.tracing import get_request_id, set_request_id
    
    # In middleware:
    request_id = str(uuid4())
    set_request_id(request_id)
    response = await call_next(request)
    
    # In services - automatically includes request_id:
    logger.info("Processing started")  # Shows request_id automatically
"""

from contextvars import ContextVar
from typing import Optional
from uuid import uuid4

# Context variables for distributed tracing
_request_id: ContextVar[str] = ContextVar('request_id', default='unknown')
_user_id: ContextVar[str] = ContextVar('user_id', default='anonymous')
_session_id: ContextVar[str] = ContextVar('session_id', default='')


def set_request_id(request_id: str) -> None:
    """Set the request ID for this context."""
    _request_id.set(request_id)


def get_request_id() -> str:
    """Get the current request ID."""
    return _request_id.get()


def set_user_id(user_id: str) -> None:
    """Set the user ID for this context."""
    _user_id.set(user_id)


def get_user_id() -> str:
    """Get the current user ID."""
    return _user_id.get()


def set_session_id(session_id: str) -> None:
    """Set the session ID for this context."""
    _session_id.set(session_id)


def get_session_id() -> str:
    """Get the current session ID."""
    return _session_id.get()


def clear_context() -> None:
    """Clear all context variables."""
    _request_id.set('unknown')
    _user_id.set('anonymous')
    _session_id.set('')


def generate_request_id() -> str:
    """Generate a new request ID and set it in context."""
    request_id = str(uuid4())
    set_request_id(request_id)
    return request_id


def get_trace_context() -> dict:
    """Get complete trace context for logging."""
    return {
        'request_id': get_request_id(),
        'user_id': get_user_id(),
        'session_id': get_session_id(),
    }
