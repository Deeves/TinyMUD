from __future__ import annotations

"""
Multi-tier rate limiting for TinyMUD operations.

This module provides token bucket rate limiting to protect against malicious client spam
and ensure fair resource usage. Different operations have different costs based on their
computational/resource requirements.

Token buckets refill continuously at a configured rate, with burst capacity limits.
Operations consume tokens based on their classification:

- BASIC (1 token): look, say, movement, simple queries
- MODERATE (3 tokens): crafting, object creation, inventory management
- HEAVY (10 tokens): AI calls, admin commands, world modifications
- SUPER_HEAVY (25 tokens): world purge, bulk operations, family generation

The system is designed to be fail-safe - if rate limiting encounters errors,
it logs the issue but allows operations to continue (fail-open policy).

Environment configuration:
- MUD_RATE_ENABLE: "1" to enable rate limiting (default: disabled)
- MUD_RATE_CAPACITY: maximum burst tokens per SID (default: 50)
- MUD_RATE_REFILL_PER_SEC: tokens refilled per second (default: 5.0)
- MUD_RATE_LOG_VIOLATIONS: "1" to log rate limit violations (default: enabled)
"""

import os
import time
import logging
from enum import Enum
from typing import Dict


# Logging setup for rate limiter violations
_logger = logging.getLogger(__name__)


class OperationType(Enum):
    """Classification of operations by resource cost."""
    BASIC = 1           # look, say, movement, simple queries
    MODERATE = 3        # crafting, object creation, inventory management
    HEAVY = 10          # AI calls, admin commands, world modifications
    SUPER_HEAVY = 25    # world purge, bulk operations, family generation


class TokenBucket:
    """Token bucket implementation for rate limiting a single client (SID).
    
    This implements the classic token bucket algorithm:
    - Tokens are added at a constant rate up to a maximum capacity
    - Operations consume tokens when performed
    - If insufficient tokens are available, the operation is rate limited
    
    The bucket refills continuously based on elapsed time since last access.
    """
    
    def __init__(self, capacity: float, refill_rate: float):
        """Initialize token bucket.
        
        Args:
            capacity: Maximum number of tokens the bucket can hold
            refill_rate: Tokens added per second
        """
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.tokens = capacity  # Start with full bucket
        self.last_update = time.time()
    
    def consume(self, tokens: float) -> bool:
        """Attempt to consume tokens from the bucket.
        
        Args:
            tokens: Number of tokens to consume
            
        Returns:
            True if tokens were successfully consumed, False if rate limited
        """
        self._refill()
        
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False
    
    def _refill(self) -> None:
        """Refill the bucket based on elapsed time."""
        now = time.time()
        elapsed = max(0.0, now - self.last_update)
        self.last_update = now
        
        # Add tokens based on elapsed time, capped at capacity
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)


class RateLimiter:
    """Multi-tier rate limiter using per-SID token buckets.
    
    This class manages rate limiting across all clients, creating and maintaining
    token buckets for each session ID (SID). It provides a simple interface for
    checking whether operations should be allowed based on their resource cost.
    
    The rate limiter is designed to be fail-safe - if any errors occur during
    rate limiting checks, it logs the error and allows the operation to proceed.
    This ensures that bugs in rate limiting don't break core functionality.
    """
    
    def __init__(self):
        """Initialize the rate limiter with configuration from environment."""
        self._buckets: Dict[str, TokenBucket] = {}
        
        # Load configuration from environment
        self._enabled = self._parse_bool_env('MUD_RATE_ENABLE', False)
        self._capacity = float(os.getenv('MUD_RATE_CAPACITY', '50'))
        self._refill_per_sec = float(os.getenv('MUD_RATE_REFILL_PER_SEC', '5.0'))
        self._log_violations = self._parse_bool_env('MUD_RATE_LOG_VIOLATIONS', True)
        
        if self._enabled:
            _logger.info(f"Rate limiting enabled: capacity={self._capacity}, "
                         f"refill={self._refill_per_sec}/sec")
    
    def check_and_consume(self, sid: str | None, operation_type: OperationType,
                          operation_name: str = "unknown") -> bool:
        """Check if an operation should be allowed and consume tokens if so.
        
        Args:
            sid: Session ID of the client (None for anonymous)
            operation_type: Classification of the operation's resource cost
            operation_name: Human-readable operation name for logging
            
        Returns:
            True if operation should proceed, False if rate limited
        """
        # Rate limiting disabled - always allow
        if not self._enabled:
            return True
        
        # Handle anonymous/None SID
        effective_sid = sid or "anonymous"
        
        try:
            # Get or create token bucket for this SID
            if effective_sid not in self._buckets:
                self._buckets[effective_sid] = TokenBucket(self._capacity, self._refill_per_sec)
            
            bucket = self._buckets[effective_sid]
            tokens_needed = operation_type.value
            
            # Try to consume tokens
            if bucket.consume(tokens_needed):
                return True
            else:
                # Rate limited - log violation if enabled
                if self._log_violations:
                    _logger.warning(f"Rate limit violation: SID {effective_sid} "
                                    f"blocked from {operation_name} "
                                    f"(needed {tokens_needed} tokens, had {bucket.tokens:.1f})")
                return False
                
        except Exception as e:
            # Fail-open policy: log error but allow operation
            _logger.error(f"Rate limiter error for SID {effective_sid}, "
                          f"operation {operation_name}: {e}")
            return True
    
    def get_bucket_status(self, sid: str | None) -> tuple[float, float]:
        """Get current token count and capacity for debugging.
        
        Args:
            sid: Session ID to check
            
        Returns:
            Tuple of (current_tokens, max_capacity)
        """
        effective_sid = sid or "anonymous"
        
        try:
            if effective_sid in self._buckets:
                bucket = self._buckets[effective_sid]
                bucket._refill()  # Ensure tokens are up to date
                return (bucket.tokens, bucket.capacity)
            else:
                return (self._capacity, self._capacity)  # Fresh bucket would have full capacity
        except Exception:
            return (0.0, self._capacity)
    
    def reset_bucket(self, sid: str | None) -> None:
        """Reset a client's token bucket (useful for admin override).
        
        Args:
            sid: Session ID to reset
        """
        effective_sid = sid or "anonymous"
        try:
            if effective_sid in self._buckets:
                del self._buckets[effective_sid]
        except Exception as e:
            _logger.error(f"Error resetting bucket for SID {effective_sid}: {e}")
    
    def cleanup_old_buckets(self, max_age_seconds: float = 3600) -> None:
        """Remove token buckets for clients that haven't been active recently.
        
        This prevents memory leaks from accumulating buckets for disconnected clients.
        
        Args:
            max_age_seconds: Remove buckets older than this many seconds
        """
        try:
            now = time.time()
            cutoff = now - max_age_seconds
            
            # Find buckets to remove (avoid modifying dict during iteration)
            old_sids = []
            for sid, bucket in self._buckets.items():
                if bucket.last_update < cutoff:
                    old_sids.append(sid)
            
            # Remove old buckets
            for sid in old_sids:
                del self._buckets[sid]
            
            if old_sids and self._log_violations:
                _logger.info(f"Cleaned up {len(old_sids)} old rate limit buckets")
                
        except Exception as e:
            _logger.error(f"Error during rate limiter cleanup: {e}")
    
    @staticmethod
    def _parse_bool_env(key: str, default: bool) -> bool:
        """Parse environment variable as boolean."""
        value = os.getenv(key, '').strip().lower()
        if value in ('1', 'true', 'yes', 'on'):
            return True
        elif value in ('0', 'false', 'no', 'off'):
            return False
        else:
            return default


# Global rate limiter instance
_global_rate_limiter = RateLimiter()


def check_rate_limit(sid: str | None, operation_type: OperationType,
                     operation_name: str = "unknown") -> bool:
    """Convenience function to check rate limits using the global rate limiter.
    
    Args:
        sid: Session ID of the client
        operation_type: Classification of the operation's resource cost
        operation_name: Human-readable operation name for logging
        
    Returns:
        True if operation should proceed, False if rate limited
    """
    return _global_rate_limiter.check_and_consume(sid, operation_type, operation_name)


def get_rate_limit_status(sid: str | None) -> tuple[float, float]:
    """Get current rate limit status for debugging.
    
    Args:
        sid: Session ID to check
        
    Returns:
        Tuple of (current_tokens, max_capacity)
    """
    return _global_rate_limiter.get_bucket_status(sid)


def reset_rate_limit(sid: str | None, operation_key: str | None = None) -> None:
    """Reset rate limit for a specific client (admin function).
    
    Args:
        sid: Session ID to reset (if None, resets for operation_key)
        operation_key: Specific operation key to reset (for keyed operations)
    """
    if operation_key and hasattr(_global_rate_limiter, 'keyed_buckets'):
        # Reset specific keyed bucket if the rate limiter supports it
        keyed_buckets = getattr(_global_rate_limiter, 'keyed_buckets', {})
        if operation_key in keyed_buckets:
            del keyed_buckets[operation_key]
    elif sid:
        _global_rate_limiter.reset_bucket(sid)


def cleanup_rate_limiter() -> None:
    """Clean up old rate limit buckets to prevent memory leaks."""
    _global_rate_limiter.cleanup_old_buckets()
    
    
def cleanup_npc_planning_rate_limits() -> int:
    """Clean up rate limiting state for NPC planning operations.
    
    This is called during world reload to ensure fresh planner state.
    
    Returns:
        Number of NPC planning buckets cleaned up
    """
    cleaned_count = 0
    
    try:
        # Access the internal bucket storage if available (defensive access)
        buckets_attr = getattr(_global_rate_limiter, 'buckets', None)
        if buckets_attr is not None:
            npc_keys_to_remove = []
            
            # Find all keys that look like NPC planning operations
            for key in buckets_attr.keys():
                if isinstance(key, str) and 'npc_goap_plan_' in key:
                    npc_keys_to_remove.append(key)
            
            # Remove the found keys
            for key in npc_keys_to_remove:
                if key in buckets_attr:
                    del buckets_attr[key]
                    cleaned_count += 1
                    _logger.debug(f"Cleaned NPC planning rate limit: {key}")
                
        # Also check for keyed buckets if the limiter supports them
        keyed_buckets_attr = getattr(_global_rate_limiter, 'keyed_buckets', None)
        if keyed_buckets_attr is not None:
            npc_keys_to_remove = []
            
            for key in keyed_buckets_attr.keys():
                if isinstance(key, str) and 'npc_goap_plan_' in key:
                    npc_keys_to_remove.append(key)
            
            for key in npc_keys_to_remove:
                if key in keyed_buckets_attr:
                    del keyed_buckets_attr[key]
                    cleaned_count += 1
                    _logger.debug(f"Cleaned NPC planning keyed rate limit: {key}")
                
    except Exception as e:
        _logger.warning(f"Failed to clean NPC planning rate limits: {e}")
        # Fallback to general cleanup
        try:
            cleanup_rate_limiter()
            cleaned_count = 1  # Indicate we did some cleanup
        except Exception:
            pass  # Best effort
    
    return cleaned_count


# Backwards compatibility with the simple rate limiter
class _SimpleRateLimiter:
    """Backwards compatibility wrapper for the old simple rate limiter.
    
    This maintains the same interface as the original _SimpleRateLimiter
    but uses the new multi-tier system under the hood with BASIC operation cost.
    """
    
    def __init__(self, sid: str | None):
        self.sid = sid
    
    @classmethod
    def get(cls, sid: str | None) -> "_SimpleRateLimiter":
        """Factory method to create rate limiter instance."""
        return cls(sid)
    
    def allow(self) -> bool:
        """Check if basic operation should be allowed."""
        return check_rate_limit(self.sid, OperationType.BASIC, "legacy_simple_check")
