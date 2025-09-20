"""
Common domain exceptions.
"""


class DomainException(Exception):
    """Base domain exception."""
    
    def __init__(self, message: str, code: str = None):
        self.message = message
        self.code = code or self.__class__.__name__
        super().__init__(self.message)


class ValidationError(DomainException):
    """Validation error in domain logic."""
    pass


class NotFoundError(DomainException):
    """Entity not found error."""
    pass


class BusinessRuleViolationError(DomainException):
    """Business rule violation error."""
    pass


class ConcurrencyError(DomainException):
    """Concurrency conflict error."""
    pass


class AuthorizationError(DomainException):
    """Authorization error."""
    pass


class RateLimitExceededError(DomainException):
    """Rate limit exceeded error."""
    pass


class ExternalServiceError(DomainException):
    """External service error."""
    pass


class ConfigurationError(DomainException):
    """Configuration error."""
    pass
