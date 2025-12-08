"""
Safe execution utilities to replace bare except pass patterns.

This module provides helpers that log exception types once to help with debugging
while avoiding spam in logs from repetitive failures.

Environment Opt‑In (Debug Raising):
    Set the environment variable DEBUG_RAISE_EXCEPTIONS to a truthy value ('1', 'true',
    'yes', or 'on') to force re‑raising of exceptions after the first (still logged)
    occurrence. This is useful while developing or when you want CI to fail fast instead
    of swallowing errors. Because we read the env var at call time you can modify it in
    tests with monkeypatch/setenv and immediately change behavior.

Usage Examples:
    # Before: Bare except that hides all errors
    try:
        risky_operation()
    except Exception:
        pass
    
    # After: Log first occurrence of each error type
    safe_call(risky_operation)
    
    # With custom default return value
    result = safe_call_with_default(get_config_value, "default_value", key)
    
    # As a decorator
    @safe_decorator(default=[])
    def get_items(self):
        return self.items  # May raise AttributeError
        
Integration Pattern:
    Replace bare 'except Exception: pass' blocks throughout the codebase with safe_call
    to get better debugging information while maintaining graceful failure behavior.
"""

import logging
import os
from typing import Any, Callable, Optional, Set, TypeVar
from functools import wraps

# Track seen exception types to log each unique type only once per session
_seen_exceptions: Set[str] = set()

# Debug guard: when DEBUG_RAISE_EXCEPTIONS is set to a truthy value, we re-raise
# instead of swallowing exceptions. This allows developers (and CI runs configured
# explicitly) to surface stack traces without modifying call sites.
# Truthy values: '1', 'true', 'yes', 'on'. Checked dynamically each call so tests
# can toggle via os.environ mid-run.
def _debug_raise_enabled() -> bool:
    try:
        val = os.getenv('DEBUG_RAISE_EXCEPTIONS', '').strip().lower()
        return val in ('1', 'true', 'yes', 'on')
    except Exception:
        return False

# Configure logger for this module
logger = logging.getLogger(__name__)

T = TypeVar('T')


def safe_call(fn: Callable[..., T], *args, **kwargs) -> Optional[T]:
    """
    Execute a function safely, logging exception types once and returning None on failure.
    
    This helper is designed to replace bare 'except Exception: pass' patterns throughout
    the codebase. It provides better debugging information by logging the first occurrence
    of each exception type, while avoiding log spam from repetitive failures.
    
    Args:
        fn: The function to execute
        *args: Positional arguments to pass to the function
        **kwargs: Keyword arguments to pass to the function
        
    Returns:
        The function's return value on success, None on any exception
        
    Examples:
        # Replace bare exception handling:
        # OLD:
        try:
            socketio.emit(MESSAGE_OUT, payload, to=psid)
        except Exception:
            pass
            
        # NEW:
        safe_call(socketio.emit, MESSAGE_OUT, payload, to=psid)
        
        # Refactor complex try/except blocks:
        # OLD:
        try:
            for rid, room in world.rooms.items():
                if npc_name in (room.npcs or set()):
                    return rid
        except Exception:
            pass
        return None
            
        # NEW:
        def _find_room():
            for rid, room in world.rooms.items():
                if npc_name in (room.npcs or set()):
                    return rid
            return None
        return safe_call(_find_room) or None
    """
    try:
        return fn(*args, **kwargs)
    except Exception as e:
        # Create a unique key for this exception type and context
        exc_type = type(e).__name__
        exc_key = f"{fn.__name__ if hasattr(fn, '__name__') else str(fn)}:{exc_type}"
        
        # Log this exception type only once per session
        if exc_key not in _seen_exceptions:
            _seen_exceptions.add(exc_key)
            logger.warning(
                f"safe_call: {fn.__name__ if hasattr(fn, '__name__') else str(fn)} "
                f"failed with {exc_type}: {e} (subsequent {exc_type} exceptions from this function will be silent)"
            )
        # In debug mode, bubble the original exception immediately after first log
        if _debug_raise_enabled():
            raise
        return None


def safe_call_with_default(fn: Callable[..., T], default: T, *args, **kwargs) -> T:
    """
    Execute a function safely, returning a default value on failure.
    
    Similar to safe_call but allows specifying a custom default return value
    instead of None.
    
    Args:
        fn: The function to execute
        default: Value to return if the function raises an exception
        *args: Positional arguments to pass to the function
        **kwargs: Keyword arguments to pass to the function
        
    Returns:
        The function's return value on success, default value on any exception
        
    Example:
        # Get a config value with fallback
        timeout = safe_call_with_default(int, 30, os.getenv('TIMEOUT'))
    """
    try:
        return fn(*args, **kwargs)
    except Exception as e:
        # Create a unique key for this exception type and context
        exc_type = type(e).__name__
        exc_key = f"{fn.__name__ if hasattr(fn, '__name__') else str(fn)}:{exc_type}"
        
        # Log this exception type only once per session
        if exc_key not in _seen_exceptions:
            _seen_exceptions.add(exc_key)
            logger.warning(
                f"safe_call_with_default: {fn.__name__ if hasattr(fn, '__name__') else str(fn)} "
                f"failed with {exc_type}: {e} (returning default: {default})"
            )
        if _debug_raise_enabled():
            raise
        return default


def safe_decorator(default: Any = None):
    """
    Decorator version of safe_call for methods that should never raise exceptions.
    
    Args:
        default: Value to return if the decorated function raises an exception
        
    Example:
        @safe_decorator()
        def risky_method(self):
            return self.might_fail()
            
        @safe_decorator(default=[])
        def get_items(self):
            return self.items_that_might_not_exist
    """
    def decorator(func: Callable[..., T]) -> Callable[..., Optional[T]]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Optional[T]:
            # Reuse safe_call_with_default which already respects debug raise flag
            return safe_call_with_default(func, default, *args, **kwargs)
        return wrapper
    return decorator


def reset_seen_exceptions() -> None:
    """
    Reset the set of seen exceptions.
    
    This is primarily useful for testing to ensure clean state between test runs.
    """
    global _seen_exceptions
    _seen_exceptions.clear()