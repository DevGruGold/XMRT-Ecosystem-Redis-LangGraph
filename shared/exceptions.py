"""
Custom exceptions for XMRT-Ecosystem Redis and LangGraph integration

Defines custom exception classes for better error handling and debugging.
"""


class XMRTIntegrationError(Exception):
    """Base exception for XMRT integration errors"""
    
    def __init__(self, message: str, error_code: str = None, context: dict = None):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.context = context or {}
    
    def __str__(self):
        base_msg = self.message
        if self.error_code:
            base_msg = f"[{self.error_code}] {base_msg}"
        if self.context:
            base_msg += f" | Context: {self.context}"
        return base_msg


class ConfigurationError(XMRTIntegrationError):
    """Raised when there's a configuration error"""
    pass


class ConnectionError(XMRTIntegrationError):
    """Raised when connection to external service fails"""
    pass


class CacheError(XMRTIntegrationError):
    """Raised when cache operations fail"""
    pass


class StateError(XMRTIntegrationError):
    """Raised when state management operations fail"""
    pass


class WorkflowError(XMRTIntegrationError):
    """Raised when workflow execution fails"""
    pass


class ValidationError(XMRTIntegrationError):
    """Raised when data validation fails"""
    pass


class SerializationError(XMRTIntegrationError):
    """Raised when data serialization/deserialization fails"""
    pass


class TimeoutError(XMRTIntegrationError):
    """Raised when operations timeout"""
    pass


class AuthenticationError(XMRTIntegrationError):
    """Raised when authentication fails"""
    pass


class AuthorizationError(XMRTIntegrationError):
    """Raised when authorization fails"""
    pass


class ResourceNotFoundError(XMRTIntegrationError):
    """Raised when a requested resource is not found"""
    pass


class ResourceExistsError(XMRTIntegrationError):
    """Raised when trying to create a resource that already exists"""
    pass


class RateLimitError(XMRTIntegrationError):
    """Raised when rate limits are exceeded"""
    pass


class CircuitBreakerError(XMRTIntegrationError):
    """Raised when circuit breaker is open"""
    pass


class RetryExhaustedError(XMRTIntegrationError):
    """Raised when retry attempts are exhausted"""
    pass

