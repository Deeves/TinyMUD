"""Tests for service contract helpers."""

from service_contract import success, error, not_handled, ServiceReturn


def test_success_helper():
    """Test success() constructs valid 4-tuple."""
    result = success([{'type': 'system', 'content': 'OK'}])
    assert result == (True, None, [{'type': 'system', 'content': 'OK'}], [])
    assert isinstance(result, tuple)
    assert len(result) == 4


def test_success_with_broadcasts():
    """Test success() with broadcasts argument."""
    emits = [{'type': 'system', 'content': 'You did it'}]
    broadcasts = [('room1', {'type': 'system', 'content': 'They did it'})]
    result = success(emits, broadcasts)
    assert result == (True, None, emits, broadcasts)


def test_error_helper():
    """Test error() constructs valid 4-tuple."""
    result = error('Something went wrong')
    assert result == (True, 'Something went wrong', [], [])
    assert isinstance(result, tuple)
    assert len(result) == 4


def test_not_handled_helper():
    """Test not_handled() constructs valid 4-tuple."""
    result = not_handled()
    assert result == (False, None, [], [])
    assert isinstance(result, tuple)
    assert len(result) == 4


def test_service_return_type_alias():
    """Test that ServiceReturn type alias is correct."""
    # This is more of a documentation test - the type alias should
    # match the actual tuple structure
    result: ServiceReturn = (True, None, [], [])
    handled, err, emits, broadcasts = result
    assert handled is True
    assert err is None
    assert emits == []
    assert broadcasts == []


def test_error_still_handled():
    """Test that errors return handled=True (command was recognized)."""
    result = error("Test error")
    handled, err, emits, broadcasts = result
    assert handled is True
    assert err == "Test error"


def test_success_default_broadcasts():
    """Test that success() defaults broadcasts to empty list if not provided."""
    result = success([{'type': 'system', 'content': 'test'}])
    handled, err, emits, broadcasts = result
    assert broadcasts == []
    assert isinstance(broadcasts, list)


def test_unpacking_pattern():
    """Test the standard unpacking pattern used in routers."""
    # Simulate a service call
    result = success(
        [{'type': 'system', 'content': 'Operation complete'}],
        [('room123', {'type': 'system', 'content': 'Someone did something'})]
    )
    
    # Standard unpacking in router
    handled, err, emits, broadcasts = result
    
    assert handled is True
    assert err is None
    assert len(emits) == 1
    assert len(broadcasts) == 1
    assert broadcasts[0][0] == 'room123'
