"""Validation utilities for LXC Autoscaler."""

import re
from typing import Any, List, Optional

from .exceptions import ValidationError


class Validator:
    """Base validator class."""
    
    def __init__(self, field_name: str):
        """Initialize validator.
        
        Args:
            field_name: Name of the field being validated.
        """
        self.field_name = field_name
    
    def validate(self, value: Any) -> Any:
        """Validate a value.
        
        Args:
            value: Value to validate.
            
        Returns:
            Validated value (may be transformed).
            
        Raises:
            ValidationError: If validation fails.
        """
        raise NotImplementedError


class RequiredValidator(Validator):
    """Validates that a value is present (not None)."""
    
    def validate(self, value: Any) -> Any:
        """Validate value is not None."""
        if value is None:
            raise ValidationError(f"{self.field_name} is required")
        return value


class TypeValidator(Validator):
    """Validates that a value is of the correct type."""
    
    def __init__(self, field_name: str, expected_type: type):
        """Initialize type validator.
        
        Args:
            field_name: Name of the field being validated.
            expected_type: Expected Python type.
        """
        super().__init__(field_name)
        self.expected_type = expected_type
    
    def validate(self, value: Any) -> Any:
        """Validate value type."""
        if not isinstance(value, self.expected_type):
            raise ValidationError(
                f"{self.field_name} must be of type {self.expected_type.__name__}, "
                f"got {type(value).__name__}"
            )
        return value


class RangeValidator(Validator):
    """Validates that a numeric value is within a range."""
    
    def __init__(self, field_name: str, min_value: Optional[float] = None, max_value: Optional[float] = None):
        """Initialize range validator.
        
        Args:
            field_name: Name of the field being validated.
            min_value: Minimum allowed value (inclusive).
            max_value: Maximum allowed value (inclusive).
        """
        super().__init__(field_name)
        self.min_value = min_value
        self.max_value = max_value
    
    def validate(self, value: Any) -> Any:
        """Validate value is within range."""
        if not isinstance(value, (int, float)):
            raise ValidationError(f"{self.field_name} must be numeric")
        
        if self.min_value is not None and value < self.min_value:
            raise ValidationError(f"{self.field_name} must be >= {self.min_value}")
        
        if self.max_value is not None and value > self.max_value:
            raise ValidationError(f"{self.field_name} must be <= {self.max_value}")
        
        return value


class ChoiceValidator(Validator):
    """Validates that a value is one of allowed choices."""
    
    def __init__(self, field_name: str, choices: List[Any]):
        """Initialize choice validator.
        
        Args:
            field_name: Name of the field being validated.
            choices: List of allowed values.
        """
        super().__init__(field_name)
        self.choices = choices
    
    def validate(self, value: Any) -> Any:
        """Validate value is in choices."""
        if value not in self.choices:
            raise ValidationError(f"{self.field_name} must be one of {self.choices}")
        return value


class RegexValidator(Validator):
    """Validates that a string matches a regular expression."""
    
    def __init__(self, field_name: str, pattern: str, flags: int = 0):
        """Initialize regex validator.
        
        Args:
            field_name: Name of the field being validated.
            pattern: Regular expression pattern.
            flags: Regex flags.
        """
        super().__init__(field_name)
        self.pattern = re.compile(pattern, flags)
    
    def validate(self, value: Any) -> Any:
        """Validate value matches pattern."""
        if not isinstance(value, str):
            raise ValidationError(f"{self.field_name} must be a string")
        
        if not self.pattern.match(value):
            raise ValidationError(f"{self.field_name} does not match required format")
        
        return value


class LengthValidator(Validator):
    """Validates string or list length."""
    
    def __init__(self, field_name: str, min_length: Optional[int] = None, max_length: Optional[int] = None):
        """Initialize length validator.
        
        Args:
            field_name: Name of the field being validated.
            min_length: Minimum length.
            max_length: Maximum length.
        """
        super().__init__(field_name)
        self.min_length = min_length
        self.max_length = max_length
    
    def validate(self, value: Any) -> Any:
        """Validate value length."""
        if not hasattr(value, '__len__'):
            raise ValidationError(f"{self.field_name} must have a length")
        
        length = len(value)
        
        if self.min_length is not None and length < self.min_length:
            raise ValidationError(f"{self.field_name} must have at least {self.min_length} characters")
        
        if self.max_length is not None and length > self.max_length:
            raise ValidationError(f"{self.field_name} must have at most {self.max_length} characters")
        
        return value


class HostnameValidator(RegexValidator):
    """Validates hostname format."""
    
    def __init__(self, field_name: str):
        """Initialize hostname validator."""
        # Hostname regex pattern
        pattern = r'^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*$'
        super().__init__(field_name, pattern)


class PortValidator(RangeValidator):
    """Validates port number."""
    
    def __init__(self, field_name: str):
        """Initialize port validator."""
        super().__init__(field_name, 1, 65535)


class PercentageValidator(RangeValidator):
    """Validates percentage value (0-100)."""
    
    def __init__(self, field_name: str):
        """Initialize percentage validator."""
        super().__init__(field_name, 0.0, 100.0)


class VMIDValidator(RangeValidator):
    """Validates Proxmox VMID."""
    
    def __init__(self, field_name: str):
        """Initialize VMID validator."""
        super().__init__(field_name, 100, 999999999)


def validate_field(value: Any, validators: List[Validator]) -> Any:
    """Validate a field using multiple validators.
    
    Args:
        value: Value to validate.
        validators: List of validators to apply.
        
    Returns:
        Validated value.
        
    Raises:
        ValidationError: If any validation fails.
    """
    for validator in validators:
        value = validator.validate(value)
    return value


def validate_object(obj: dict, field_validators: dict) -> dict:
    """Validate an object using field validators.
    
    Args:
        obj: Object to validate (as dictionary).
        field_validators: Mapping of field names to validator lists.
        
    Returns:
        Validated object.
        
    Raises:
        ValidationError: If any field validation fails.
    """
    validated = {}
    
    for field_name, validators in field_validators.items():
        value = obj.get(field_name)
        
        try:
            validated[field_name] = validate_field(value, validators)
        except ValidationError as e:
            # Re-raise with field context if not already present
            if not e.message.startswith(field_name):
                raise ValidationError(f"{field_name}: {e.message}")
            raise
    
    return validated