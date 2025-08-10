"""Custom exceptions for Proxmox API interactions."""

from typing import Any, Dict, Optional


class ProxmoxAPIError(Exception):
    """Base exception for Proxmox API errors."""
    
    def __init__(self, message: str, status_code: Optional[int] = None, response_data: Optional[Dict[str, Any]] = None):
        """Initialize API error.
        
        Args:
            message: Error message.
            status_code: HTTP status code if available.
            response_data: API response data if available.
        """
        super().__init__(message)
        self.status_code = status_code
        self.response_data = response_data or {}


class ProxmoxConnectionError(ProxmoxAPIError):
    """Connection to Proxmox API failed."""
    pass


class ProxmoxAuthenticationError(ProxmoxAPIError):
    """Authentication with Proxmox API failed."""
    pass


class ProxmoxResourceNotFoundError(ProxmoxAPIError):
    """Requested Proxmox resource not found."""
    pass


class ProxmoxOperationError(ProxmoxAPIError):
    """Proxmox operation failed."""
    pass


class ProxmoxTimeoutError(ProxmoxAPIError):
    """Proxmox API request timed out."""
    pass


class ProxmoxRateLimitError(ProxmoxAPIError):
    """Proxmox API rate limit exceeded."""
    pass