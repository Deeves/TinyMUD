"""Tests for MockAI functionality.

This module tests the MockAI implementation to ensure it provides a reliable
foundation for testing AI-dependent features across the TinyMUD codebase.

The tests verify:
- Basic response generation and pattern matching
- Error simulation capabilities
- Integration with existing code patterns
- Performance and usability for test scenarios
"""

import pytest
import json
import re
from unittest.mock import patch

from mock_ai import (
    MockAIResponse, MockAIModel,
    create_npc_generation_mock, create_goap_planning_mock,
    create_dialogue_mock, create_world_setup_mock,
    patch_server_model
)


class TestMockAIResponse:
    """Test the basic MockAIResponse class."""
    
    def test_response_has_text_attribute(self):
        """MockAIResponse should have a .text attribute like real Gemini responses."""
        response = MockAIResponse("Test content")
        assert hasattr(response, 'text')
        assert response.text == "Test content"
    
    def test_response_works_with_json(self):
        """MockAIResponse should work with JSON content."""
        json_content = '{"name": "Test", "value": 42}'
        response = MockAIResponse(json_content)
        
        # Should be able to parse the JSON from the response
        parsed = json.loads(response.text)
        assert parsed["name"] == "Test"
        assert parsed["value"] == 42
    
    def test_response_works_with_multiline(self):
        """MockAIResponse should handle multiline content properly."""
        multiline = "Line 1\nLine 2\nLine 3"
        response = MockAIResponse(multiline)
        assert "Line 1" in response.text
        assert "Line 2" in response.text
        assert "Line 3" in response.text


class TestMockAIModel:
    """Test the core MockAIModel functionality."""
    
    def test_default_response(self):
        """Model should return default response when no patterns match."""
        model = MockAIModel("Default test response")
        response = model.generate_content("Random prompt")
        
        assert isinstance(response, MockAIResponse)
        assert response.text == "Default test response"
    
    def test_pattern_matching(self):
        """Model should return specific responses for matching patterns."""
        model = MockAIModel()
        model.add_response_pattern(r"hello", "Hello back!")
        model.add_response_pattern(r"goodbye", "Farewell!")
        
        # Test hello pattern
        response = model.generate_content("Say hello to me")
        assert response.text == "Hello back!"
        
        # Test goodbye pattern
        response = model.generate_content("I must say goodbye now")
        assert response.text == "Farewell!"
    
    def test_case_insensitive_patterns(self):
        """Pattern matching should be case-insensitive."""
        model = MockAIModel()
        model.add_response_pattern(r"HELLO", "Hello response")
        
        # Should match regardless of case
        response = model.generate_content("hello world")
        assert response.text == "Hello response"
        
        response = model.generate_content("HELLO WORLD")
        assert response.text == "Hello response"
        
        response = model.generate_content("Hello World")
        assert response.text == "Hello response"
    
    def test_first_pattern_wins(self):
        """First matching pattern should take precedence."""
        model = MockAIModel("Default")
        model.add_response_pattern(r"test", "First match")
        model.add_response_pattern(r"test", "Second match")  # Should not be used
        
        response = model.generate_content("This is a test")
        assert response.text == "First match"
    
    def test_error_patterns(self):
        """Model should raise exceptions for error patterns."""
        model = MockAIModel()
        model.add_error_pattern(r"error", ValueError("Test error"))
        model.add_response_pattern(r"success", "Success!")
        
        # Should raise error
        with pytest.raises(ValueError, match="Test error"):
            model.generate_content("This should error")
        
        # Should return normal response
        response = model.generate_content("This should success")
        assert response.text == "Success!"
    
    def test_error_patterns_take_precedence(self):
        """Error patterns should be checked before response patterns."""
        model = MockAIModel()
        model.add_response_pattern(r"test", "Normal response")
        model.add_error_pattern(r"test", RuntimeError("Error response"))
        
        # Error should be raised even though response pattern also matches
        with pytest.raises(RuntimeError, match="Error response"):
            model.generate_content("This is a test")
    
    def test_call_history_tracking(self):
        """Model should track all calls for verification."""
        model = MockAIModel()
        
        assert model.call_count == 0
        assert len(model.call_history) == 0
        
        model.generate_content("First prompt")
        assert model.call_count == 1
        assert model.call_history[0] == "First prompt"
        
        model.generate_content("Second prompt")
        assert model.call_count == 2
        assert model.call_history[1] == "Second prompt"
        assert model.get_last_prompt() == "Second prompt"
    
    def test_was_called_with_pattern(self):
        """Model should be able to check if it was called with specific patterns."""
        model = MockAIModel()
        
        model.generate_content("Hello world")
        model.generate_content("Generate some JSON")
        model.generate_content("Plan an action")
        
        assert model.was_called_with_pattern(r"hello")
        assert model.was_called_with_pattern(r"JSON")
        assert model.was_called_with_pattern(r"Plan.*action")
        assert not model.was_called_with_pattern(r"goodbye")
    
    def test_clear_patterns(self):
        """Model should be able to reset all state."""
        model = MockAIModel()
        model.add_response_pattern(r"test", "Response")
        model.add_error_pattern(r"error", ValueError("Error"))
        model.generate_content("Test prompt")
        
        assert model.call_count > 0
        assert len(model.call_history) > 0
        assert len(model.response_patterns) > 0
        assert len(model.error_patterns) > 0
        
        model.clear_patterns()
        
        assert model.call_count == 0
        assert len(model.call_history) == 0
        assert len(model.response_patterns) == 0
        assert len(model.error_patterns) == 0
    
    def test_safety_settings_ignored(self):
        """Model should accept safety_settings parameter but ignore it."""
        model = MockAIModel("Test response")
        
        # Should work with or without safety settings
        response1 = model.generate_content("Test prompt")
        response2 = model.generate_content("Test prompt", safety_settings={"some": "setting"})
        
        assert response1.text == response2.text == "Test response"


class TestPredefinedMocks:
    """Test the pre-configured mock models for specific use cases."""
    
    def test_npc_generation_mock(self):
        """NPC generation mock should respond appropriately to character creation."""
        mock = create_npc_generation_mock()
        
        # Test standard NPC creation
        response = mock.generate_content("Please create a new NPC character")
        data = json.loads(response.text)
        assert "name" in data
        assert "description" in data
        assert "Test Warrior" in data["name"]
        
        # Test family generation
        response = mock.generate_content("Create a sister for this character")
        data = json.loads(response.text)
        assert "Test Sibling" in data["name"]
        assert "family" in data["description"]
    
    def test_goap_planning_mock(self):
        """GOAP planning mock should return valid action sequences."""
        mock = create_goap_planning_mock()
        
        # Test movement plan
        response = mock.generate_content("Plan to move north")
        actions = json.loads(response.text)
        assert isinstance(actions, list)
        assert len(actions) > 0
        assert actions[0]["tool"] == "move"
        
        # Test consumption plan
        response = mock.generate_content("The NPC is hungry and needs to eat")
        actions = json.loads(response.text)
        assert any(action["tool"] == "get_object" for action in actions)
        assert any(action["tool"] == "consume_object" for action in actions)
        
        # Test empty plan
        response = mock.generate_content("The NPC should idle and wait")
        actions = json.loads(response.text)
        assert actions == []
    
    def test_dialogue_mock(self):
        """Dialogue mock should provide conversational responses."""
        mock = create_dialogue_mock()
        
        # Test greeting
        response = mock.generate_content("Player says hello to NPC")
        assert "Hello" in response.text or "hello" in response.text
        
        # Test trading
        response = mock.generate_content("Player wants to trade items")
        assert "trade" in response.text or "wares" in response.text
        
        # Test farewell
        response = mock.generate_content("Player says goodbye")
        assert "travel" in response.text or "fortune" in response.text
    
    def test_world_setup_mock(self):
        """World setup mock should provide structured world data."""
        mock = create_world_setup_mock()
        
        # Test single room
        response = mock.generate_content("Create a new room for the world")
        data = json.loads(response.text)
        assert "name" in data
        assert "description" in data
        
        # Test multi-room generation
        response = mock.generate_content("Generate multiple rooms for world setup")
        rooms = json.loads(response.text)
        assert isinstance(rooms, list)
        assert len(rooms) > 1
        assert all("name" in room and "description" in room for room in rooms)


class TestServerIntegration:
    """Test integration with actual server patterns."""
    
    def test_patch_server_model_context_manager(self):
        """Test the server model patching utility."""
        
        # Mock a server-like object
        class MockServer:
            def __init__(self):
                self.model = "original_model"
                self.plan_model = "original_plan_model"
        
        server = MockServer()
        mock_model = MockAIModel("Test response")
        
        # Test that patching works
        with patch_server_model(server, mock_model) as patched_mock:
            assert patched_mock is mock_model
            assert server.model is mock_model
            assert server.plan_model is mock_model
        
        # Test that restoration works
        assert server.model == "original_model"
        assert server.plan_model == "original_plan_model"
    
    def test_compatibility_with_existing_patterns(self):
        """Test that MockAI works with existing server code patterns."""
        mock = MockAIModel()
        
        # This pattern matches how the server uses AI models
        mock.add_response_pattern(
            r"role.*play.*npc",
            "I am a friendly shopkeeper. How can I help you today?"
        )
        
        # Simulate server-style usage
        prompt = "Please role-play as this NPC and respond to the player"
        safety_settings = None  # Often passed as None
        
        response = mock.generate_content(prompt, safety_settings=safety_settings)
        
        # Should work like real Gemini responses
        assert hasattr(response, 'text')
        assert isinstance(response.text, str)
        assert "shopkeeper" in response.text
    
    def test_json_parsing_with_markdown_fences(self):
        """Test handling of JSON wrapped in markdown code fences."""
        mock = MockAIModel()
        
        # Simulate AI responses that include markdown formatting
        json_with_fences = '''```json
{
  "name": "Test Character",
  "description": "A character for testing"
}
```'''
        
        mock.add_response_pattern(r"json", json_with_fences)
        response = mock.generate_content("Return some json data")
        
        # Should be able to extract JSON from fences (testing existing patterns)
        text = response.text
        assert "```json" in text
        
        # Simulate the extraction logic used in setup_service.py
        json_match = re.search(r'```json\s*\n(.*?)\n```', text, re.DOTALL)
        if json_match:
            clean_json = json_match.group(1)
            data = json.loads(clean_json)
            assert data["name"] == "Test Character"


class TestPerformanceAndUsability:
    """Test that MockAI is suitable for extensive test usage."""
    
    def test_large_number_of_patterns(self):
        """Model should handle many patterns efficiently."""
        mock = MockAIModel()
        
        # Add many patterns - use word boundaries to avoid partial matches
        for i in range(100):
            mock.add_response_pattern(rf"\bpattern{i}\b", f"response{i}")
        
        # Should still work efficiently
        response = mock.generate_content("pattern50 test")
        assert response.text == "response50"
    
    def test_complex_regex_patterns(self):
        """Model should handle complex regex patterns."""
        mock = MockAIModel()
        
        # Complex pattern with groups, lookaheads, etc.
        complex_pattern = r"create\s+(npc|character)\s+.*(?:with|having)\s+(?:name|called)\s+(\w+)"
        mock.add_response_pattern(complex_pattern, "Complex pattern matched!")
        
        response = mock.generate_content("create npc fighter with name Aragorn")
        assert response.text == "Complex pattern matched!"
    
    def test_large_prompt_handling(self):
        """Model should handle very large prompts efficiently."""
        mock = MockAIModel()
        mock.add_response_pattern(r"large", "Handled large prompt")
        
        # Create a large prompt (simulating detailed world state)
        large_prompt = "large prompt " + "context " * 1000
        
        response = mock.generate_content(large_prompt)
        assert response.text == "Handled large prompt"
        
        # Should still track it properly
        assert mock.call_count == 1
        assert len(mock.get_last_prompt()) > 5000


if __name__ == "__main__":
    # Quick smoke test when run directly
    print("Running MockAI smoke tests...")
    
    # Test basic functionality
    mock = MockAIModel("Default response")
    mock.add_response_pattern(r"hello", "Hello from MockAI!")
    
    response = mock.generate_content("Say hello")
    assert response.text == "Hello from MockAI!"
    
    response = mock.generate_content("Random text")
    assert response.text == "Default response"
    
    print("✓ Basic functionality works")
    
    # Test predefined mocks
    npc_mock = create_npc_generation_mock()
    response = npc_mock.generate_content("Create a new NPC")
    data = json.loads(response.text)
    assert "name" in data and "description" in data
    
    print("✓ Predefined mocks work")
    
    # Test error simulation
    mock.add_error_pattern(r"error", ValueError("Test error"))
    try:
        mock.generate_content("This should error")
        assert False, "Expected error was not raised"
    except ValueError as e:
        assert str(e) == "Test error"
    
    print("✓ Error simulation works")
    
    print("All smoke tests passed! 🎉")