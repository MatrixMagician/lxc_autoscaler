"""Tests for validation utilities."""

import pytest

from lxc_autoscaler.core.exceptions import ValidationError
from lxc_autoscaler.core.validators import (
    RequiredValidator,
    TypeValidator,
    RangeValidator,
    ChoiceValidator,
    RegexValidator,
    LengthValidator,
    HostnameValidator,
    PortValidator,
    PercentageValidator,
    VMIDValidator,
    validate_field,
    validate_object,
)


class TestRequiredValidator:
    """Test RequiredValidator."""
    
    def test_valid_value(self):
        """Test required validator with valid value."""
        validator = RequiredValidator("test_field")
        assert validator.validate("some_value") == "some_value"
        assert validator.validate(0) == 0
        assert validator.validate(False) is False
    
    def test_none_value_fails(self):
        """Test required validator fails on None."""
        validator = RequiredValidator("test_field")
        with pytest.raises(ValidationError, match="test_field is required"):
            validator.validate(None)


class TestTypeValidator:
    """Test TypeValidator."""
    
    def test_valid_type(self):
        """Test type validator with valid type."""
        validator = TypeValidator("test_field", str)
        assert validator.validate("hello") == "hello"
        
        validator = TypeValidator("test_field", int)
        assert validator.validate(42) == 42
    
    def test_invalid_type_fails(self):
        """Test type validator fails on wrong type."""
        validator = TypeValidator("test_field", str)
        with pytest.raises(ValidationError, match="test_field must be of type str"):
            validator.validate(42)


class TestRangeValidator:
    """Test RangeValidator."""
    
    def test_valid_range(self):
        """Test range validator with valid values."""
        validator = RangeValidator("test_field", 0, 100)
        assert validator.validate(50) == 50
        assert validator.validate(0) == 0
        assert validator.validate(100) == 100
    
    def test_value_too_low_fails(self):
        """Test range validator fails on too low value."""
        validator = RangeValidator("test_field", 10, 100)
        with pytest.raises(ValidationError, match="test_field must be >= 10"):
            validator.validate(5)
    
    def test_value_too_high_fails(self):
        """Test range validator fails on too high value."""
        validator = RangeValidator("test_field", 0, 100)
        with pytest.raises(ValidationError, match="test_field must be <= 100"):
            validator.validate(150)
    
    def test_non_numeric_fails(self):
        """Test range validator fails on non-numeric value."""
        validator = RangeValidator("test_field", 0, 100)
        with pytest.raises(ValidationError, match="test_field must be numeric"):
            validator.validate("not_a_number")


class TestChoiceValidator:
    """Test ChoiceValidator."""
    
    def test_valid_choice(self):
        """Test choice validator with valid choice."""
        validator = ChoiceValidator("test_field", ["apple", "banana", "cherry"])
        assert validator.validate("banana") == "banana"
    
    def test_invalid_choice_fails(self):
        """Test choice validator fails on invalid choice."""
        validator = ChoiceValidator("test_field", ["apple", "banana", "cherry"])
        with pytest.raises(ValidationError, match="test_field must be one of"):
            validator.validate("grape")


class TestRegexValidator:
    """Test RegexValidator."""
    
    def test_valid_pattern(self):
        """Test regex validator with matching pattern."""
        validator = RegexValidator("test_field", r"^[a-z]+$")
        assert validator.validate("hello") == "hello"
    
    def test_invalid_pattern_fails(self):
        """Test regex validator fails on non-matching pattern."""
        validator = RegexValidator("test_field", r"^[a-z]+$")
        with pytest.raises(ValidationError, match="test_field does not match required format"):
            validator.validate("Hello123")
    
    def test_non_string_fails(self):
        """Test regex validator fails on non-string."""
        validator = RegexValidator("test_field", r"^[a-z]+$")
        with pytest.raises(ValidationError, match="test_field must be a string"):
            validator.validate(123)


class TestLengthValidator:
    """Test LengthValidator."""
    
    def test_valid_length(self):
        """Test length validator with valid length."""
        validator = LengthValidator("test_field", 2, 10)
        assert validator.validate("hello") == "hello"
        assert validator.validate([1, 2, 3]) == [1, 2, 3]
    
    def test_too_short_fails(self):
        """Test length validator fails on too short value."""
        validator = LengthValidator("test_field", 5, 10)
        with pytest.raises(ValidationError, match="test_field must have at least 5 characters"):
            validator.validate("hi")
    
    def test_too_long_fails(self):
        """Test length validator fails on too long value."""
        validator = LengthValidator("test_field", 2, 5)
        with pytest.raises(ValidationError, match="test_field must have at most 5 characters"):
            validator.validate("this is too long")


class TestSpecializedValidators:
    """Test specialized validators."""
    
    def test_hostname_validator(self):
        """Test hostname validator."""
        validator = HostnameValidator("hostname")
        
        # Valid hostnames
        assert validator.validate("example.com") == "example.com"
        assert validator.validate("sub.example.com") == "sub.example.com"
        assert validator.validate("localhost") == "localhost"
        assert validator.validate("server-01") == "server-01"
        
        # Invalid hostnames
        with pytest.raises(ValidationError):
            validator.validate("invalid..hostname")
        with pytest.raises(ValidationError):
            validator.validate("-invalid")
        with pytest.raises(ValidationError):
            validator.validate("invalid-")
    
    def test_port_validator(self):
        """Test port validator."""
        validator = PortValidator("port")
        
        # Valid ports
        assert validator.validate(80) == 80
        assert validator.validate(8006) == 8006
        assert validator.validate(65535) == 65535
        
        # Invalid ports
        with pytest.raises(ValidationError):
            validator.validate(0)
        with pytest.raises(ValidationError):
            validator.validate(65536)
    
    def test_percentage_validator(self):
        """Test percentage validator."""
        validator = PercentageValidator("percentage")
        
        # Valid percentages
        assert validator.validate(0.0) == 0.0
        assert validator.validate(50.5) == 50.5
        assert validator.validate(100.0) == 100.0
        
        # Invalid percentages
        with pytest.raises(ValidationError):
            validator.validate(-1.0)
        with pytest.raises(ValidationError):
            validator.validate(101.0)
    
    def test_vmid_validator(self):
        """Test VMID validator."""
        validator = VMIDValidator("vmid")
        
        # Valid VMIDs
        assert validator.validate(100) == 100
        assert validator.validate(101) == 101
        assert validator.validate(999999) == 999999
        
        # Invalid VMIDs
        with pytest.raises(ValidationError):
            validator.validate(99)  # Too low
        with pytest.raises(ValidationError):
            validator.validate(1000000000)  # Too high


class TestValidationHelpers:
    """Test validation helper functions."""
    
    def test_validate_field_multiple_validators(self):
        """Test validating field with multiple validators."""
        validators = [
            RequiredValidator("test_field"),
            TypeValidator("test_field", str),
            LengthValidator("test_field", 3, 10)
        ]
        
        # Valid value
        result = validate_field("hello", validators)
        assert result == "hello"
        
        # Invalid value (None)
        with pytest.raises(ValidationError):
            validate_field(None, validators)
        
        # Invalid value (wrong type)
        with pytest.raises(ValidationError):
            validate_field(123, validators)
        
        # Invalid value (too short)
        with pytest.raises(ValidationError):
            validate_field("hi", validators)
    
    def test_validate_object(self):
        """Test validating object with field validators."""
        field_validators = {
            "name": [
                RequiredValidator("name"),
                TypeValidator("name", str),
                LengthValidator("name", 1, 50)
            ],
            "port": [
                RequiredValidator("port"),
                TypeValidator("port", int),
                PortValidator("port")
            ]
        }
        
        # Valid object
        obj = {"name": "test-server", "port": 8080}
        result = validate_object(obj, field_validators)
        assert result["name"] == "test-server"
        assert result["port"] == 8080
        
        # Invalid object (missing field)
        with pytest.raises(ValidationError):
            validate_object({"name": "test"}, field_validators)
        
        # Invalid object (invalid port)
        with pytest.raises(ValidationError):
            validate_object({"name": "test", "port": 99999}, field_validators)


if __name__ == '__main__':
    pytest.main([__file__])