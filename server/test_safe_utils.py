"""
Tests for safe_utils module.

Verifies that safe_call and related utilities work correctly and log appropriately.
"""

import logging
import pytest
from unittest.mock import patch
from safe_utils import safe_call, safe_call_with_default, safe_decorator, reset_seen_exceptions


def test_safe_call_success():
    """Test that safe_call returns the function result when no exception occurs."""
    def simple_func(a, b):
        return a + b
    
    result = safe_call(simple_func, 2, 3)
    assert result == 5


def test_safe_call_failure():
    """Test that safe_call returns None when function raises an exception."""
    def failing_func():
        raise ValueError("Test error")
    
    result = safe_call(failing_func)
    assert result is None


def test_safe_call_with_args_and_kwargs():
    """Test that safe_call properly passes args and kwargs."""
    def complex_func(a, b, c=10):
        return a + b + c
    
    result = safe_call(complex_func, 1, 2, c=5)
    assert result == 8


def test_safe_call_with_default():
    """Test that safe_call_with_default returns custom default on failure."""
    def failing_func():
        raise RuntimeError("Test error")
    
    result = safe_call_with_default(failing_func, "default_value")
    assert result == "default_value"


def test_safe_call_with_default_success():
    """Test that safe_call_with_default returns function result on success."""
    def working_func():
        return "success"
    
    result = safe_call_with_default(working_func, "default_value")
    assert result == "success"


def test_safe_decorator():
    """Test the safe_decorator functionality."""
    @safe_decorator()
    def risky_method():
        raise ValueError("Decorated failure")
    
    result = risky_method()
    assert result is None


def test_safe_decorator_with_default():
    """Test safe_decorator with custom default value."""
    @safe_decorator(default=[])
    def risky_method():
        raise ValueError("Decorated failure")
    
    result = risky_method()
    assert result == []


def test_safe_decorator_success():
    """Test that safe_decorator preserves successful results."""
    @safe_decorator(default="fallback")
    def working_method():
        return "success"
    
    result = working_method()
    assert result == "success"


def test_logging_behavior():
    """Test that exceptions are logged only once per function+type combination."""
    reset_seen_exceptions()
    
    def failing_func():
        raise ValueError("Test error")
    
    # Patch the logger to capture log messages
    with patch('safe_utils.logger') as mock_logger:
        # First call should log
        safe_call(failing_func)
        assert mock_logger.warning.call_count == 1
        
        # Second call with same function+exception type should not log
        safe_call(failing_func)
        assert mock_logger.warning.call_count == 1
        
        # Call with different exception type should log again
        def different_error():
            raise TypeError("Different error")
        
        safe_call(different_error)
        assert mock_logger.warning.call_count == 2


def test_logging_message_format():
    """Test that log messages contain expected information."""
    reset_seen_exceptions()
    
    def named_function():
        raise ValueError("Test message")
    
    with patch('safe_utils.logger') as mock_logger:
        safe_call(named_function)
        
        # Verify the log message contains function name and exception type
        args, kwargs = mock_logger.warning.call_args
        log_message = args[0]
        assert "named_function" in log_message
        assert "ValueError" in log_message
        assert "Test message" in log_message


def test_reset_seen_exceptions():
    """Test that reset_seen_exceptions clears the tracking state."""
    def failing_func():
        raise ValueError("Test error")
    
    with patch('safe_utils.logger') as mock_logger:
        # First call logs
        safe_call(failing_func)
        assert mock_logger.warning.call_count == 1
        
        # Second call doesn't log (already seen)
        safe_call(failing_func)
        assert mock_logger.warning.call_count == 1
        
        # Reset and call again - should log again
        reset_seen_exceptions()
        safe_call(failing_func)
        assert mock_logger.warning.call_count == 2


def test_lambda_function_handling():
    """Test that safe_call handles lambda functions gracefully."""
    failing_lambda = lambda: 1 / 0
    
    result = safe_call(failing_lambda)
    assert result is None


def test_method_handling():
    """Test that safe_call works with class methods."""
    class TestClass:
        def failing_method(self):
            raise RuntimeError("Method failure")
        
        def working_method(self, x):
            return x * 2
    
    obj = TestClass()
    
    # Test failing method
    result = safe_call(obj.failing_method)
    assert result is None
    
    # Test working method
    result = safe_call(obj.working_method, 5)
    assert result == 10