#!/usr/bin/env python3

"""
Test suite for the rate_limiter module.

This test verifies that the multi-tier token bucket rate limiting works correctly
and provides protection against malicious client spam.
"""

import os
import time
import sys
from pathlib import Path

# Add server directory to path for imports
server_dir = Path(__file__).parent
sys.path.insert(0, str(server_dir))

from rate_limiter import (
    RateLimiter, OperationType, check_rate_limit, 
    get_rate_limit_status, reset_rate_limit
)


def test_rate_limiter_disabled():
    """Test that rate limiter allows all operations when disabled."""
    # Ensure rate limiting is disabled
    os.environ['MUD_RATE_ENABLE'] = '0'
    
    # Create fresh limiter
    limiter = RateLimiter()
    
    # Should allow unlimited operations
    for i in range(100):
        assert limiter.check_and_consume("test_sid", OperationType.SUPER_HEAVY, "test_op")
    
    print("✓ Rate limiter disabled test passed")


def test_rate_limiter_enabled():
    """Test that rate limiter blocks operations when enabled."""
    # Enable rate limiting with small limits for testing
    os.environ['MUD_RATE_ENABLE'] = '1'
    os.environ['MUD_RATE_CAPACITY'] = '10'
    os.environ['MUD_RATE_REFILL_PER_SEC'] = '1'
    
    # Create fresh limiter
    limiter = RateLimiter()
    
    # Should allow a few operations then block
    allowed_count = 0
    for i in range(20):
        if limiter.check_and_consume("test_sid", OperationType.MODERATE, "test_op"):
            allowed_count += 1
        else:
            break
    
    # Should have allowed some but not all operations
    assert 0 < allowed_count < 20, f"Expected some operations allowed but not all, got {allowed_count}"
    
    print(f"✓ Rate limiter enabled test passed (allowed {allowed_count}/20 operations)")


def test_operation_costs():
    """Test that different operation types have different costs."""
    os.environ['MUD_RATE_ENABLE'] = '1'
    os.environ['MUD_RATE_CAPACITY'] = '20'
    os.environ['MUD_RATE_REFILL_PER_SEC'] = '0'  # No refill for predictable testing
    
    limiter = RateLimiter()
    
    # Should allow more BASIC operations than HEAVY operations
    basic_count = 0
    for i in range(30):
        if limiter.check_and_consume("basic_sid", OperationType.BASIC, "basic_op"):
            basic_count += 1
        else:
            break
    
    heavy_count = 0
    for i in range(30):
        if limiter.check_and_consume("heavy_sid", OperationType.HEAVY, "heavy_op"):
            heavy_count += 1
        else:
            break
    
    assert basic_count > heavy_count, f"Expected more basic ops ({basic_count}) than heavy ops ({heavy_count})"
    
    print(f"✓ Operation costs test passed (basic: {basic_count}, heavy: {heavy_count})")


def test_token_refill():
    """Test that tokens refill over time."""
    os.environ['MUD_RATE_ENABLE'] = '1'
    os.environ['MUD_RATE_CAPACITY'] = '5'
    os.environ['MUD_RATE_REFILL_PER_SEC'] = '10'  # Fast refill for testing
    
    limiter = RateLimiter()
    
    # Consume all tokens
    sid = "refill_test_sid"
    while limiter.check_and_consume(sid, OperationType.BASIC, "consume_all"):
        pass
    
    # Should be blocked now
    assert not limiter.check_and_consume(sid, OperationType.BASIC, "blocked_op")
    
    # Wait for refill
    time.sleep(0.6)  # Should refill ~6 tokens
    
    # Should be allowed again
    assert limiter.check_and_consume(sid, OperationType.BASIC, "refilled_op")
    
    print("✓ Token refill test passed")


def test_convenience_functions():
    """Test the global convenience functions."""
    os.environ['MUD_RATE_ENABLE'] = '1'
    os.environ['MUD_RATE_CAPACITY'] = '15'
    os.environ['MUD_RATE_REFILL_PER_SEC'] = '2'
    
    # Import after setting environment to get updated global limiter
    import importlib
    import rate_limiter
    importlib.reload(rate_limiter)
    from rate_limiter import check_rate_limit, get_rate_limit_status, reset_rate_limit, OperationType
    
    sid = "convenience_test"
    
    # Test check_rate_limit function
    assert check_rate_limit(sid, OperationType.BASIC, "test_basic")
    
    # Test status function
    tokens, capacity = get_rate_limit_status(sid)
    assert 0 <= tokens <= capacity
    assert capacity == 15
    
    # Test reset function (should not raise exception)
    reset_rate_limit(sid)
    
    print("✓ Convenience functions test passed")


def test_anonymous_sid():
    """Test handling of None/anonymous SID."""
    os.environ['MUD_RATE_ENABLE'] = '1'
    os.environ['MUD_RATE_CAPACITY'] = '10'
    
    limiter = RateLimiter()
    
    # Should handle None SID gracefully
    assert limiter.check_and_consume(None, OperationType.BASIC, "anon_op")
    
    # Multiple None SIDs should share the same bucket
    for i in range(5):
        limiter.check_and_consume(None, OperationType.MODERATE, f"anon_op_{i}")
    
    # Should eventually be rate limited
    blocked = False
    for i in range(10):
        if not limiter.check_and_consume(None, OperationType.MODERATE, f"anon_op_block_{i}"):
            blocked = True
            break
    
    assert blocked, "Anonymous SID should eventually be rate limited"
    
    print("✓ Anonymous SID test passed")


def run_all_tests():
    """Run all rate limiter tests."""
    print("Running rate limiter tests...")
    
    # Clean environment
    for key in ['MUD_RATE_ENABLE', 'MUD_RATE_CAPACITY', 'MUD_RATE_REFILL_PER_SEC']:
        if key in os.environ:
            del os.environ[key]
    
    try:
        test_rate_limiter_disabled()
        test_rate_limiter_enabled()
        test_operation_costs()
        test_token_refill()
        test_convenience_functions()
        test_anonymous_sid()
        
        print("\n🎉 All rate limiter tests passed!")
        return True
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)