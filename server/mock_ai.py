"""MockAI — Configurable mock AI models for testing.

This module provides mock implementations of the Gemini AI interface to enable
fast, deterministic testing of AI-dependent features without requiring actual
API calls. The mock responses can be configured per-test to exercise different
code paths and edge cases.

Key features:
- MockAIResponse: mimics the Gemini response structure with .text attribute
- MockAIModel: configurable mock that can return different responses based on prompt patterns
- Predefined response templates for common use cases (NPC generation, GOAP planning, etc.)
- Error simulation for testing failure scenarios

Usage:
    # Simple fixed response
    mock_model = MockAIModel(default_response="Hello, world!")
    
    # Pattern-based responses
    mock_model = MockAIModel()
    mock_model.add_response_pattern("create.*npc", '{"name": "Test NPC", "description": "A test character"}')
    mock_model.add_response_pattern("plan.*action", '[{"tool": "move", "args": {"direction": "north"}}]')
    
    # Use in tests
    original_model = server.model
    server.model = mock_model
    try:
        # Run test code that uses AI
        pass
    finally:
        server.model = original_model
"""

from __future__ import annotations

import re
import json
from typing import Dict, List, Optional, Any, Union
import logging

logger = logging.getLogger(__name__)


class MockAIResponse:
    """Mock implementation of Gemini AI response object.
    
    This class mimics the structure of actual Gemini responses, providing
    the .text attribute that the rest of the codebase expects. It's designed
    to be a drop-in replacement for testing scenarios.
    """
    
    def __init__(self, text: str):
        """Initialize mock response with given text content.
        
        Args:
            text: The response text that would normally come from the AI model
        """
        self.text = text


class MockAIModel:
    """Configurable mock AI model for testing.
    
    This class provides a flexible way to mock AI model behavior for tests.
    It can return different responses based on prompt patterns, simulate
    errors, and track usage for verification in tests.
    
    The model maintains compatibility with the Gemini GenerativeModel interface
    by providing a generate_content method that accepts prompts and safety
    settings (though safety settings are ignored in the mock).
    """
    
    def __init__(self, default_response: str = "Mock AI response"):
        """Initialize the mock model with optional default response.
        
        Args:
            default_response: Text to return when no pattern matches
        """
        self.default_response = default_response
        self.response_patterns: List[tuple[str, str]] = []
        self.call_history: List[str] = []
        self.error_patterns: List[tuple[str, Exception]] = []
        self.call_count = 0
    
    def add_response_pattern(self, pattern: str, response: str) -> None:
        """Add a regex pattern that triggers a specific response.
        
        When generate_content is called, the prompt will be checked against
        all registered patterns in order. The first match will determine
        the response. If no patterns match, default_response is used.
        
        Args:
            pattern: Regex pattern to match against prompts (case-insensitive)
            response: Text to return when pattern matches
        """
        self.response_patterns.append((pattern, response))
    
    def add_error_pattern(self, pattern: str, error: Exception) -> None:
        """Add a pattern that triggers an exception when matched.
        
        This allows testing error handling scenarios by simulating AI
        failures for specific types of prompts.
        
        Args:
            pattern: Regex pattern to match against prompts (case-insensitive)
            error: Exception to raise when pattern matches
        """
        self.error_patterns.append((pattern, error))
    
    def generate_content(self, prompt: str, safety_settings: Optional[Any] = None) -> MockAIResponse:
        """Generate mock content based on the prompt and configured patterns.
        
        This is the main method that mimics the Gemini model interface.
        It processes the prompt through registered patterns and returns
        appropriate responses or raises configured exceptions.
        
        Args:
            prompt: The input prompt text
            safety_settings: Ignored in mock (kept for interface compatibility)
            
        Returns:
            MockAIResponse containing the matched or default response text
            
        Raises:
            Exception: If prompt matches an error pattern
        """
        self.call_count += 1
        self.call_history.append(prompt)
        
        # Check for error patterns first (they take precedence)
        for pattern, error in self.error_patterns:
            if re.search(pattern, prompt, re.IGNORECASE | re.DOTALL):
                logger.debug(f"MockAI: Error pattern '{pattern}' matched, raising {type(error).__name__}")
                raise error
        
        # Check response patterns
        for pattern, response in self.response_patterns:
            if re.search(pattern, prompt, re.IGNORECASE | re.DOTALL):
                logger.debug(f"MockAI: Pattern '{pattern}' matched, returning configured response")
                return MockAIResponse(response)
        
        # No patterns matched, return default
        logger.debug("MockAI: No patterns matched, returning default response")
        return MockAIResponse(self.default_response)
    
    def clear_patterns(self) -> None:
        """Clear all configured patterns and reset state."""
        self.response_patterns.clear()
        self.error_patterns.clear()
        self.call_history.clear()
        self.call_count = 0
    
    def get_last_prompt(self) -> Optional[str]:
        """Get the most recent prompt sent to the model."""
        return self.call_history[-1] if self.call_history else None
    
    def was_called_with_pattern(self, pattern: str) -> bool:
        """Check if any previous prompts matched the given pattern."""
        for prompt in self.call_history:
            if re.search(pattern, prompt, re.IGNORECASE | re.DOTALL):
                return True
        return False


# Pre-configured mock models for common testing scenarios

def create_npc_generation_mock() -> MockAIModel:
    """Create a mock model configured for NPC generation testing.
    
    Returns responses that look like typical NPC generation JSON,
    with different responses for different request types.
    """
    mock = MockAIModel()
    
    # Standard NPC creation
    mock.add_response_pattern(
        r"create.*npc|generate.*character",
        '{"name": "Test Warrior", "description": "A brave fighter with a mysterious past."}'
    )
    
    # Family generation
    mock.add_response_pattern(
        r"family.*relation|sister|brother|parent",
        '{"name": "Test Sibling", "description": "A loyal family member who shares the same values."}'
    )
    
    # Error case for malformed requests
    mock.add_error_pattern(
        r"invalid.*request",
        Exception("Simulated API error for testing")
    )
    
    return mock


def create_goap_planning_mock() -> MockAIModel:
    """Create a mock model configured for GOAP AI planning testing.
    
    Returns JSON arrays that represent action sequences for NPCs,
    allowing testing of the GOAP planning and execution system.
    """
    mock = MockAIModel()
    
    # Simple movement plan
    mock.add_response_pattern(
        r"move|travel|go.*to",
        '[{"tool": "move", "args": {"direction": "north"}}]'
    )
    
    # Consumption/interaction plan
    mock.add_response_pattern(
        r"eat|drink|consume|hunger|thirst",
        '[{"tool": "get_object", "args": {"object_name": "Bread"}}, {"tool": "consume_object", "args": {"object_uuid": "test-uuid"}}]'
    )
    
    # Social interaction plan
    mock.add_response_pattern(
        r"talk|greet|social",
        '[{"tool": "emote", "args": {"emotion": "friendly"}}, {"tool": "say", "args": {"message": "Hello there!"}}]'
    )
    
    # Complex multi-step plan
    mock.add_response_pattern(
        r"complex.*plan|multi.*step",
        '[{"tool": "move", "args": {"direction": "east"}}, {"tool": "get_object", "args": {"object_name": "Key"}}, {"tool": "move", "args": {"direction": "west"}}, {"tool": "use_object", "args": {"object_name": "Key", "target": "Door"}}]'
    )
    
    # Empty plan (NPC has nothing to do)
    mock.add_response_pattern(
        r"idle|wait|nothing",
        '[]'
    )
    
    return mock


def create_dialogue_mock() -> MockAIModel:
    """Create a mock model configured for dialogue generation testing.
    
    Returns conversational responses that NPCs might give, enabling
    testing of chat interactions without real AI calls.
    """
    mock = MockAIModel()
    
    # Friendly greeting
    mock.add_response_pattern(
        r"hello|hi|greet",
        "Hello there, traveler! Welcome to our humble town."
    )
    
    # Information request
    mock.add_response_pattern(
        r"information|help|question",
        "I'd be happy to help you with whatever you need to know."
    )
    
    # Trading/commerce
    mock.add_response_pattern(
        r"trade|buy|sell|shop",
        "I have some fine wares if you're interested in making a deal."
    )
    
    # Quest/adventure
    mock.add_response_pattern(
        r"quest|adventure|task|mission",
        "There are rumors of strange happenings in the old ruins to the north."
    )
    
    # Farewell
    mock.add_response_pattern(
        r"goodbye|farewell|bye",
        "Safe travels, and may fortune smile upon you!"
    )
    
    return mock


def create_world_setup_mock() -> MockAIModel:
    """Create a mock model for world generation and setup testing.
    
    Returns structured JSON for creating rooms, NPCs, and world elements
    during the initial world setup process.
    """
    mock = MockAIModel()
    
    # Room generation
    mock.add_response_pattern(
        r"create.*room|generate.*location",
        '{"name": "Test Chamber", "description": "A well-lit stone chamber with ancient symbols on the walls."}'
    )
    
    # Multi-room world generation
    mock.add_response_pattern(
        r"world.*setup|multiple.*rooms",
        '''[
            {"name": "Town Square", "description": "A bustling square at the heart of the town."},
            {"name": "Old Tavern", "description": "A cozy tavern with flickering candlelight."},
            {"name": "Mysterious Cave", "description": "A dark cave entrance shrouded in mist."}
        ]'''
    )
    
    return mock


# Utility functions for test setup

def patch_server_model(server_module, mock_model: MockAIModel):
    """Context manager helper to temporarily replace server AI model.
    
    This function provides a clean way to patch the server's AI model
    for testing without having to remember to restore it manually.
    
    Args:
        server_module: The imported server module to patch
        mock_model: The MockAIModel instance to use temporarily
        
    Returns:
        Context manager that handles patching/restoration
    """
    class ModelPatcher:
        def __init__(self, server, mock):
            self.server = server
            self.mock = mock
            self.original_model = None
            self.original_plan_model = None
        
        def __enter__(self):
            # Store originals
            self.original_model = getattr(self.server, 'model', None)
            self.original_plan_model = getattr(self.server, 'plan_model', None)
            
            # Install mock
            setattr(self.server, 'model', self.mock)
            setattr(self.server, 'plan_model', self.mock)
            
            return self.mock
        
        def __exit__(self, exc_type, exc_val, exc_tb):
            # Restore originals
            if hasattr(self.server, 'model'):
                setattr(self.server, 'model', self.original_model)
            if hasattr(self.server, 'plan_model'):
                setattr(self.server, 'plan_model', self.original_plan_model)
    
    return ModelPatcher(server_module, mock_model)


# Example usage for quick testing
if __name__ == "__main__":
    # Demonstrate basic usage
    mock = MockAIModel("Default response for testing")
    mock.add_response_pattern(r"hello", "Hello from MockAI!")
    mock.add_response_pattern(r"json", '{"test": "data"}')
    
    # Test responses
    resp1 = mock.generate_content("Say hello to me")
    print(f"Response 1: {resp1.text}")
    
    resp2 = mock.generate_content("Return some json data")
    print(f"Response 2: {resp2.text}")
    
    resp3 = mock.generate_content("Random prompt")
    print(f"Response 3: {resp3.text}")
    
    # Show call history
    print(f"Total calls: {mock.call_count}")
    print(f"Last prompt: {mock.get_last_prompt()}")