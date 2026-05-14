"""Shared domain errors for route/service boundaries."""

from __future__ import annotations


class DomainError(Exception):
    """Base class for expected domain/application errors."""


class ValidationDomainError(DomainError):
    """Raised when input is structurally valid for transport but invalid for domain logic."""


class PermissionDomainError(DomainError):
    """Raised when a caller is authenticated but not allowed to access a resource."""


class NotFoundDomainError(DomainError):
    """Raised when a requested domain resource does not exist."""


class SessionValidationError(ValidationDomainError):
    pass


class SessionPermissionError(PermissionDomainError):
    pass


class SessionNotFoundError(NotFoundDomainError):
    pass


class AuthConflictError(ValidationDomainError, ValueError):
    pass


class AuthCredentialsError(ValidationDomainError, ValueError):
    pass


class AuthInactiveError(PermissionDomainError):
    pass


class APIKeyNotFoundError(NotFoundDomainError):
    pass


class CleaningValidationError(ValidationDomainError, ValueError):
    pass


class ConnectorValidationError(ValidationDomainError, ValueError):
    pass


class ConnectorNotFoundError(NotFoundDomainError):
    pass


class PipelineValidationError(ValidationDomainError, ValueError):
    pass


class PipelineNotFoundError(NotFoundDomainError, ValueError):
    pass


class BillingValidationError(ValidationDomainError, ValueError):
    pass


class BillingPermissionError(PermissionDomainError):
    pass


class SQLValidationError(ValidationDomainError, ValueError):
    pass


class CollaborationValidationError(ValidationDomainError, ValueError):
    pass


class CollaborationPermissionError(PermissionDomainError):
    pass
