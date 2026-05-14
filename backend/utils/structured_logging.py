"""
structured_logging.py - Structured logging configuration with correlation ID support.

Configures loguru with JSON output for production and pretty output for development.

Usage in main.py:
    from utils.structured_logging import configure_logging
    
    configure_logging(level="INFO", json_output=False)  # Before app startup

Non-breaking: Configures logging, doesn't change existing logger calls.
"""

import sys
import json
import logging
from datetime import datetime
from utils.tracing import get_trace_context
from typing import Optional

_logger = logging.getLogger(__name__)


def serialize_log_record(record: dict) -> str:
    """Serialize log record with correlation ID context."""
    # Add contextual info
    trace_ctx = get_trace_context()
    
    log_entry = {
        'timestamp': record['time'].isoformat(),
        'level': record['level'].name,
        'message': record['message'],
        'module': record['name'],
        'function': record['function'],
        'line': record['line'],
        **trace_ctx,  # Adds request_id, user_id, session_id
    }
    
    # Add extra context if provided
    if record['extra']:
        log_entry.update(record['extra'])
    
    # Add exception info if present
    if record['exception']:
        log_entry['exception'] = {
            'type': record['exception'].type.__name__,
            'value': str(record['exception'].value),
            'traceback': record['exc_info'][2] is not None
        }
    
    return json.dumps(log_entry)


def configure_logging(
    level: str = "INFO",
    json_output: bool = False,
    log_file: Optional[str] = None
) -> None:
    """
    Configure loguru for the application.
    
    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        json_output: If True, outputs JSON for production; if False, pretty format for dev
        log_file: Optional file path to write logs to
        
    Example:
        configure_logging(level="DEBUG", json_output=False)  # Development
        configure_logging(level="INFO", json_output=True)    # Production
    """
    
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)
    
    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(numeric_level)
    
    if json_output:
        # Production: JSON format
        formatter = logging.Formatter(
            '{"time": "%(asctime)s", "level": "%(levelname)s", "logger": "%(name)s", "message": "%(message)s"}'
        )
    else:
        # Development: Pretty format
        formatter = logging.Formatter(
            '%(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d | %(message)s'
        )
    
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)


def get_logger():
    """Get the configured logger instance."""
    return logging.getLogger(__name__)


# Log levels for quick reference
LOG_LEVELS = {
    'debug': 'DEBUG',
    'info': 'INFO',
    'warning': 'WARNING',
    'error': 'ERROR',
    'critical': 'CRITICAL'
}
