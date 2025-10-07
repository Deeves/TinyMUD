"""Demonstration of MockAI usage in TinyMUD tests.

This file shows practical examples of how to use the MockAI system to test
AI-dependent features without making actual API calls. It demonstrates
integration with existing server patterns and test fixtures.

These examples can serve as a reference for updating other test files
to use MockAI when needed.
"""

import pytest
import json
from unittest.mock import patch

# Import our MockAI components
from mock_ai import (
    MockAIModel, create_npc_generation_mock, create_goap_planning_mock,
    create_dialogue_mock, patch_server_model
)


def test_npc_familygen_with_mock_ai():
    """Demonstrate using MockAI for NPC family generation testing."""
    
    # Import server fresh for testing
    import server
    
    # Create a mock that responds to family generation requests
    mock_ai = create_npc_generation_mock()
    
    # Use the context manager to temporarily replace AI models
    with patch_server_model(server, mock_ai) as mock:
        # Set up minimal world state
        from world import World, Room, CharacterSheet
        server.world = World()
        server.world.rooms['start'] = Room(id='start', description='Start room')
        
        # Add an existing NPC to generate family for
        existing_npc = CharacterSheet(
            display_name='Edda Greywater',
            description='A salty sailor with a quick wit.'
        )
        server.world.npc_sheets['Edda Greywater'] = existing_npc
        server.world.rooms['start'].npcs.add('Edda Greywater')
        
        # Import and call the NPC service function
        import npc_service as ns
        
        # Test family generation (this would normally call Gemini)
        handled, err, emits = ns.handle_npc_command(
            server.world,
            'test_state.json',
            None,  # No socketio needed for this test
            ['familygen', 'start', 'Edda Greywater', 'sister']
        )
        
        # Verify the mock was called and family member was created
        assert handled and err is None
        assert mock.call_count > 0
        assert mock.was_called_with_pattern(r"family.*sister")
        
        # The mock should have created a new NPC
        family_members = [name for name in server.world.npc_sheets.keys() 
                         if 'Sibling' in name or 'Test' in name]
        assert len(family_members) > 0


def test_goap_planning_with_mock_ai():
    """Demonstrate using MockAI for GOAP AI planning tests."""
    
    import server
    
    # Create a mock configured for planning responses
    planning_mock = create_goap_planning_mock()
    
    with patch_server_model(server, planning_mock) as mock:
        # Set up world with NPC
        from world import World, Room, CharacterSheet, Object
        server.world = World()
        server.world.rooms['start'] = Room(id='start', description='Start room')
        
        # Create NPC with low hunger (should trigger eating plan)
        npc_sheet = CharacterSheet(
            display_name='Hungry Guard',
            description='A guard who needs food'
        )
        npc_sheet.hunger = 20  # Low hunger should trigger eating behavior
        npc_sheet.action_points = 3
        npc_sheet.plan_queue = []
        server.world.npc_sheets['Hungry Guard'] = npc_sheet
        server.world.rooms['start'].npcs.add('Hungry Guard')
        
        # Add some food in the room
        bread = Object(
            display_name='Bread',
            description='Fresh bread',
            object_tags={'Consumable', 'Food', 'small'}
        )
        bread.satiation_value = 50
        server.world.rooms['start'].objects[bread.uuid] = bread
        
        # Trigger NPC planning (this would call Gemini for plan generation)
        server.npc_think('Hungry Guard')
        
        # Verify mock was called with hunger-related prompt
        assert mock.call_count > 0
        assert mock.was_called_with_pattern(r"hunger|eat|consume")
        
        # The NPC should now have a plan to get and eat food
        assert len(npc_sheet.plan_queue) > 0
        
        # Execute one action from the plan
        if npc_sheet.plan_queue:
            action = npc_sheet.plan_queue[0]
            assert action.get('tool') in ['get_object', 'consume_object']


def test_dialogue_with_mock_ai():
    """Demonstrate using MockAI for NPC dialogue testing."""
    
    # This example shows how to test AI-powered dialogue directly
    # rather than through the full server stack
    
    dialogue_mock = create_dialogue_mock()
    
    # Simulate the kind of prompt the server would send to the AI
    world_context = "Room: Tavern. NPCs: Bartender (friendly, serves drinks)"
    npc_context = "You are the Bartender, a friendly NPC who serves drinks and shares local gossip."
    player_input = "Hello there, bartender!"
    
    prompt = f"""
Context: {world_context}
Character: {npc_context}

A player says to you: "{player_input}"

Please respond as this character would.
"""
    
    # Test the mock response
    response = dialogue_mock.generate_content(prompt)
    
    # Verify the mock was triggered and gave appropriate response
    assert dialogue_mock.call_count == 1
    assert dialogue_mock.was_called_with_pattern(r"hello|hi|greet")
    assert "Hello" in response.text or "Greetings" in response.text
    
    # Test different conversation patterns
    trade_prompt = "Do you have any items for sale?"
    trade_response = dialogue_mock.generate_content(trade_prompt)
    assert dialogue_mock.was_called_with_pattern(r"trade|buy|sell")
    assert "wares" in trade_response.text or "trade" in trade_response.text


def test_custom_mock_patterns():
    """Show how to create custom mock patterns for specific test scenarios."""
    
    # Create a custom mock for testing error scenarios
    error_mock = MockAIModel("Default AI response")
    
    # Add specific patterns for different test cases
    error_mock.add_response_pattern(
        r"create.*dangerous.*npc",
        '{"name": "Dangerous Bandit", "description": "A threatening figure in dark robes."}'
    )
    
    # Add an error pattern to test failure handling
    error_mock.add_error_pattern(
        r"cause.*api.*error",
        ConnectionError("Simulated API failure for testing")
    )
    
    # Test normal response
    response = error_mock.generate_content("Please create a dangerous NPC for this encounter")
    data = json.loads(response.text)
    assert data['name'] == "Dangerous Bandit"
    
    # Test error simulation
    with pytest.raises(ConnectionError, match="Simulated API failure"):
        error_mock.generate_content("This prompt should cause an API error")
    
    # Verify call history tracking
    assert error_mock.call_count == 2
    assert error_mock.was_called_with_pattern(r"create.*dangerous")


def test_mock_ai_with_existing_patterns():
    """Show how MockAI works with existing server code patterns."""
    
    # This demonstrates the typical pattern used in the server
    mock = MockAIModel()
    
    # Configure mock to handle the types of prompts the server generates
    mock.add_response_pattern(
        r"You are.*NPC.*respond.*player",
        "Greetings, traveler! How may I assist you on your journey?"
    )
    
    mock.add_response_pattern(
        r"Generate.*plan.*actions.*JSON",
        '[{"tool": "move", "args": {"direction": "north"}}, {"tool": "emote", "args": {"emotion": "confident"}}]'
    )
    
    # Simulate the server's AI prompt construction
    world_context = "Current room: Tavern. NPCs present: Bartender, Patron."
    npc_context = "You are a friendly bartender who serves drinks and gossip."
    player_message = "Hello, do you have any ale?"
    
    full_prompt = f"""
    {world_context}
    {npc_context}
    
    You are this NPC. Respond to the player's message: "{player_message}"
    """
    
    # The mock should handle this just like the real AI would
    response = mock.generate_content(full_prompt)
    
    assert "Greetings" in response.text
    assert mock.call_count == 1
    assert mock.was_called_with_pattern(r"You are.*NPC")


def test_performance_comparison():
    """Demonstrate the speed advantage of MockAI over real API calls."""
    
    import time
    
    mock = create_dialogue_mock()
    
    # Time multiple mock calls
    start_time = time.time()
    
    for i in range(100):
        response = mock.generate_content(f"Hello number {i}")
        assert "Hello" in response.text or "hello" in response.text
    
    mock_time = time.time() - start_time
    
    # Mock calls should be very fast (well under 1 second for 100 calls)
    assert mock_time < 1.0
    assert mock.call_count == 100
    
    print(f"MockAI processed 100 calls in {mock_time:.3f} seconds")


if __name__ == "__main__":
    # Run a quick demonstration
    print("MockAI Integration Examples")
    print("=" * 30)
    
    # Show basic usage
    mock = MockAIModel("I am a helpful AI assistant.")
    mock.add_response_pattern(r"hello", "Hello! Nice to meet you!")
    
    response = mock.generate_content("Say hello to me")
    print(f"Response: {response.text}")
    
    # Show predefined mocks
    npc_mock = create_npc_generation_mock()
    npc_response = npc_mock.generate_content("Create a new warrior character")
    print(f"NPC response text: '{npc_response.text}'")
    
    # Try a different prompt that should match the pattern
    npc_response2 = npc_mock.generate_content("Please create an NPC for me")
    print(f"NPC response 2: '{npc_response2.text}'")
    try:
        npc_data = json.loads(npc_response2.text)
        print(f"Generated NPC: {npc_data['name']}")
    except json.JSONDecodeError:
        print("NPC response was not JSON, using text response")
    
    # Show planning mock
    plan_mock = create_goap_planning_mock()
    plan_response = plan_mock.generate_content("NPC needs to move north and greet someone")
    plan_data = json.loads(plan_response.text)
    print(f"Generated plan: {len(plan_data)} actions")
    
    # Show dialogue mock
    dialogue_mock = create_dialogue_mock()
    dialogue_response = dialogue_mock.generate_content("Say hello to the player")
    print(f"NPC dialogue: {dialogue_response.text}")
    
    print("\nAll examples completed successfully! ✨")