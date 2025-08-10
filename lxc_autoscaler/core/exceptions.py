"""Core exception classes for LXC Autoscaler."""

from typing import Any, Dict, Optional


class LXCAutoscalerError(Exception):
    """Base exception for all LXC Autoscaler errors."""
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        """Initialize exception.
        
        Args:
            message: Error message.
            details: Additional error details.
        """
        super().__init__(message)
        self.details = details or {}


class ValidationError(LXCAutoscalerError):
    """Data validation error."""
    pass


class ServiceError(LXCAutoscalerError):
    """Service operation error."""
    pass


class ResourceError(LXCAutoscalerError):
    """Resource management error."""
    pass


class ConfigurationValidationError(ValidationError):
    """Configuration validation specific error."""
    
    def __init__(self, message: str, field: Optional[str] = None, value: Optional[Any] = None):
        """Initialize configuration validation error.
        
        Args:
            message: Error message.
            field: Configuration field name.
            value: Invalid value.
        """
        details = {}
        if field is not None:
            details["field"] = field
        if value is not None:
            details["value"] = str(value)
        
        super().__init__(message, details)
        self.field = field
        self.value = value