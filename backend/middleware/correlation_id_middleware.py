"""
correlation_id_middleware.py - Middleware for injecting correlation IDs into all requests.

Automatically generates and tracks request IDs across service layers for distributed tracing.

Usage in main.py:
    from middleware.correlation_id_middleware import CorrelationIdMiddleware
    
    app.add_middleware(CorrelationIdMiddleware)

Non-breaking: Works alongside existing middleware. Requests work with or without correlation ID.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from utils.tracing import generate_request_id, set_user_id, set_session_id, clear_context
from typing import Callable
import logging
import time

logger = logging.getLogger(__name__)


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Middleware that injects request IDs and user context for distributed tracing."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Inject correlation ID and user context, then track request execution.
        
        Args:
            request: The incoming HTTP request
            call_next: The next middleware/route handler
            
        Returns:
            Response with correlation ID header
        """
        # Attempt to extract existing request ID (from headers)
        request_id = request.headers.get('X-Request-ID')
        if not request_id:
            request_id = generate_request_id()
        else:
            from utils.tracing import set_request_id
            set_request_id(request_id)
        
        # Extract user context if available (from headers, usually set by frontend)
        user_id = request.headers.get('X-User-ID', 'anonymous')
        set_user_id(user_id)
        
        session_id = request.headers.get('X-Session-ID', '')
        if session_id:
            set_session_id(session_id)
        
        # Log request start
        start_time = time.time()
        method = request.method
        url = request.url.path
        
        logger.info(f"Request started: {method} {url} [ID: {request_id}]")
        
        try:
            # Call the next middleware/route
            response = await call_next(request)
            
            # Calculate request duration
            duration_ms = (time.time() - start_time) * 1000
            
            # Log request completion
            logger.info(
                f"Request completed: {method} {url} → {response.status_code} ({duration_ms:.2f}ms) [ID: {request_id}]"
            )
            
            # Add correlation ID to response headers for tracing
            response.headers["X-Request-ID"] = request_id
            
            return response
            
        except Exception as e:
            # Log errors with context
            duration_ms = (time.time() - start_time) * 1000
            logger.error(
                f"Request failed: {method} {url} ({duration_ms:.2f}ms) [ID: {request_id}] - {str(e)}",
                exc_info=True
            )
            raise
        
        finally:
            # Clear context variables
            clear_context()
