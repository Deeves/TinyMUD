from __future__ import annotations

import os
from typing import List

import pytest

from world import World
from setup_service import begin_setup, handle_setup_input


@pytest.fixture()
def world_and_state(tmp_path):
    w = World()
    state_path = os.fspath(tmp_path / 'world_state.json')
    return w, state_path


def _drain(emits: List[dict]) -> List[str]:
    return [e.get('content', '') for e in emits]


def test_begin_and_full_setup_flow(world_and_state):
    w, state_path = world_and_state
    sid = 'sid_admin'
    sessions = {}

    # Begin
    first = begin_setup(sessions, sid)
    assert any('set up your world' in c.lower() for c in _drain(first))

    # World name
    handled, err, emits, broadcasts = handle_setup_input(w, state_path, sid, 'Eldoria', sessions)
    assert handled and any('describe the world' in c.lower() for c in _drain(emits))

    # World description
    handled, err, emits, broadcasts = handle_setup_input(w, state_path, sid, 'A land of rivers and runes.', sessions)
    assert handled and any('main conflict' in c.lower() for c in _drain(emits))

    # Conflict
    handled, err, emits, broadcasts = handle_setup_input(w, state_path, sid, 'Warring clans over ancient magic.', sessions)
    assert handled and any('manual' in c.lower() and 'quick' in c.lower() for c in _drain(emits))

    # Creation mode - choose manual
    handled, err, emits, broadcasts = handle_setup_input(w, state_path, sid, 'manual', sessions)
    assert handled and any('comfortable' in c.lower() for c in _drain(emits))

    # Safety level
    handled, err, emits, broadcasts = handle_setup_input(w, state_path, sid, 'PG-13', sessions)
    assert handled and any('goap' in c.lower() for c in _drain(emits))
    assert getattr(w, 'safety_level', None) == 'PG-13'

    # Advanced GOAP opt-in
    handled, err, emits, broadcasts = handle_setup_input(w, state_path, sid, 'yes', sessions)
    assert handled and any('starting room' in c.lower() for c in _drain(emits))
    assert getattr(w, 'advanced_goap_enabled', None) is True

    # Room id
    handled, err, emits, broadcasts = handle_setup_input(w, state_path, sid, 'town_square', sessions)
    assert handled and any('description for the starting room' in c.lower() for c in _drain(emits))

    # Room description
    handled, err, emits, broadcasts = handle_setup_input(w, state_path, sid, 'The bustling heart of the city.', sessions)
    assert handled and any('enter an npc name' in c.lower() for c in _drain(emits))

    # NPC name
    handled, err, emits, broadcasts = handle_setup_input(w, state_path, sid, 'Town Guard', sessions)
    assert handled and any('short description' in c.lower() for c in _drain(emits))

    # NPC description (finalize)
    handled, err, emits, broadcasts = handle_setup_input(w, state_path, sid, 'A stalwart guardian of the peace.', sessions)
    assert handled
    out = '\n'.join(_drain(emits))
    assert 'setup complete' in out.lower()
    assert getattr(w, 'setup_complete', False)
    assert 'town_square' in w.rooms
    assert w.start_room_id == 'town_square'
    assert 'Town Guard' in w.npc_sheets
    
    # Validate world integrity after setup mutations
    validation_errors = w.validate()
    assert validation_errors == [], f"World validation failed after setup: {validation_errors}"


def test_cancel_flow(world_and_state):
    w, state_path = world_and_state
    sid = 'sid_admin'
    sessions = {}
    begin_setup(sessions, sid)
    handled, err, emits, broadcasts = handle_setup_input(w, state_path, sid, 'cancel', sessions)
    assert handled and any('cancelled' in c.lower() for c in _drain(emits))


def test_quick_world_generation_fallback(world_and_state):
    """Test that quick world generation uses deterministic fallback when AI unavailable."""
    from setup_service import _generate_quick_world, _get_deterministic_fallback
    
    w, state_path = world_and_state
    w.world_name = "Test Realm"
    w.world_description = "A testing ground for brave adventurers."
    w.world_conflict = "Bugs vs Features in eternal combat."
    
    # Test deterministic fallback directly
    room_id, room_desc, npc_name, npc_desc = _get_deterministic_fallback(w)
    
    # Verify deterministic properties
    assert isinstance(room_id, str) and len(room_id) > 0
    assert isinstance(room_desc, str) and "Test Realm" in room_desc
    assert isinstance(npc_name, str) and len(npc_name) > 0
    assert isinstance(npc_desc, str) and len(npc_desc) > 0
    
    # Test that fallback is deterministic (same input = same output)
    room_id2, room_desc2, npc_name2, npc_desc2 = _get_deterministic_fallback(w)
    assert room_id == room_id2
    assert room_desc == room_desc2
    assert npc_name == npc_name2
    assert npc_desc == npc_desc2
    
    # Test full generation (will use fallback when no API key)
    success, error_msg = _generate_quick_world(w, state_path)
    
    # Should succeed using fallback even without AI
    assert success or "fallback" in error_msg.lower()
    
    # If successful, verify world was populated
    if success:
        assert w.start_room_id in w.rooms
        assert len(w.npc_sheets) > 0


def test_quick_world_generation_with_mock_ai(world_and_state):
    """Test quick world generation with mocked AI to simulate various scenarios."""
    import unittest.mock
    from setup_service import _try_ai_generation, _call_ai_with_timeout
    
    w, state_path = world_and_state
    w.world_name = "Mock World"
    w.world_description = "A world for testing AI integration."
    w.world_conflict = "Chaos between order and randomness."
    
    # Test 1: Successful AI response
    mock_response = unittest.mock.MagicMock()
    mock_response.text = '''
    {
        "room": {
            "id": "test_chamber",
            "description": "A chamber designed for testing purposes."
        },
        "npc": {
            "name": "Test Guardian", 
            "description": "An NPC created for testing."
        }
    }
    '''
    
    with unittest.mock.patch('setup_service.genai') as mock_genai:
        with unittest.mock.patch.dict('os.environ', {'GEMINI_API_KEY': 'test_key'}):
            mock_model = unittest.mock.MagicMock()
            mock_model.generate_content.return_value = mock_response
            mock_genai.GenerativeModel.return_value = mock_model
            mock_genai.configure = unittest.mock.MagicMock()
            
            # Mock the AI availability
            with unittest.mock.patch('setup_service.AI_AVAILABLE', True):
                result, error = _try_ai_generation(w, "Mock World", "Test description", "Test conflict")
                
            assert result is not False, f"AI generation failed: {error}"
            assert result['room']['id'] == 'test_chamber'
            assert result['npc']['name'] == 'Test Guardian'


def test_ai_timeout_protection():
    """Test timeout protection for AI calls."""
    import unittest.mock
    from setup_service import _call_ai_with_timeout
    
    # Test with None model (should fail immediately)
    success, result, truncated = _call_ai_with_timeout(None, "test prompt")
    assert not success
    assert "no ai model available" in result.lower()
    assert not truncated
    
    # Test with mock model that raises an exception
    class FailingMockModel:
        def generate_content(self, prompt):
            raise ConnectionError("Simulated API failure")
    
    failing_model = FailingMockModel()
    success, result, truncated = _call_ai_with_timeout(
        failing_model, "test prompt", timeout_seconds=1.0
    )
    
    assert not success
    assert "failed" in result.lower()
    assert not truncated


def test_giant_text_protection():
    """Test protection against hallucinated giant text responses."""
    import unittest.mock
    from setup_service import _call_ai_with_timeout
    
    # Mock AI that returns enormous response
    class GiantTextModel:
        def generate_content(self, prompt):
            mock_response = unittest.mock.MagicMock()
            # Create text larger than MAX_RESPONSE_LENGTH (10000 chars)
            mock_response.text = "A" * 15000  # 15k chars
            return mock_response
    
    giant_model = GiantTextModel()
    
    # Test size protection
    success, result, truncated = _call_ai_with_timeout(
        giant_model, "test prompt", timeout_seconds=5.0
    )
    
    assert success  # Should succeed but truncate
    assert truncated  # Should be marked as truncated
    if hasattr(result, 'text'):
        assert len(result.text) <= 10000  # Should be limited to MAX_RESPONSE_LENGTH


def test_json_extraction_robustness():
    """Test robust JSON extraction from various AI response formats."""
    from setup_service import _extract_json_block
    
    # Test 1: Clean JSON
    clean_json = '{"room": {"id": "test"}, "npc": {"name": "Test"}}'
    result = _extract_json_block(clean_json)
    assert result == clean_json
    
    # Test 2: JSON with code fences
    fenced_json = '''
    ```json
    {"room": {"id": "test"}, "npc": {"name": "Test"}}
    ```
    '''
    result = _extract_json_block(fenced_json)
    assert result == '{"room": {"id": "test"}, "npc": {"name": "Test"}}'
    
    # Test 3: JSON with explanatory text
    explained_json = '''
    Here's the JSON you requested:
    {"room": {"id": "test"}, "npc": {"name": "Test"}}
    I hope this helps!
    '''
    result = _extract_json_block(explained_json)
    assert result == '{"room": {"id": "test"}, "npc": {"name": "Test"}}'
    
    # Test 4: No valid JSON
    no_json = "This is just plain text with no JSON structure."
    result = _extract_json_block(no_json)
    assert result is None
    
    # Test 5: Multiple JSON objects (should get first)
    multi_json = '''
    {"first": "object"} and then {"second": "object"}
    '''
    result = _extract_json_block(multi_json)
    assert result == '{"first": "object"}'


def test_deterministic_fallback_variations():
    """Test that deterministic fallback varies appropriately with different world properties."""
    from setup_service import _get_deterministic_fallback
    from world import World
    
    # Test different world names produce different but deterministic results
    worlds = []
    results = []
    
    for i, (name, desc) in enumerate([
        ("Aethermoor", "A realm of floating islands"),
        ("Shadowlands", "Dark territories shrouded in mist"),  
        ("Crystal Empire", "Gleaming cities of living crystal")
    ]):
        w = World()
        w.world_name = name
        w.world_description = desc
        worlds.append(w)
        results.append(_get_deterministic_fallback(w))
    
    # Results should be different for different worlds
    assert results[0] != results[1]
    assert results[1] != results[2]
    assert results[0] != results[2]
    
    # But deterministic for the same world
    for w, expected in zip(worlds, results):
        repeat_result = _get_deterministic_fallback(w)
        assert repeat_result == expected
    
    # Room IDs should incorporate world names
    for i, (w, (room_id, _, _, _)) in enumerate(zip(worlds, results)):
        world_name_parts = w.world_name.lower().split()
        # Should contain some recognizable part of world name or be a default
        assert any(part in room_id for part in world_name_parts) or room_id in ['starting_chamber']


def test_quick_creation_mode_integration(world_and_state):
    """Test the quick creation mode integration in the setup wizard."""
    w, state_path = world_and_state
    sid = 'sid_admin'
    sessions = {}
    
    # Set up world through creation mode selection
    begin_setup(sessions, sid)
    
    # World name
    handle_setup_input(w, state_path, sid, 'Test World', sessions)
    # World description  
    handle_setup_input(w, state_path, sid, 'A world for testing quick generation.', sessions)
    # World conflict
    handle_setup_input(w, state_path, sid, 'Testing vs Production environments.', sessions)
    
    # Choose quick mode
    handled, err, emits, broadcasts = handle_setup_input(w, state_path, sid, 'quick', sessions)
    
    assert handled
    # Should either succeed with AI or mention fallback
    content = ' '.join(_drain(emits)).lower()
    assert 'complete' in content or 'fallback' in content
    
    # Should proceed to safety level regardless of AI success/failure
    assert 'comfortable' in content or 'safety' in content
