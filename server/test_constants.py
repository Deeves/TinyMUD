"""
Test cases for server/constants.py

These tests verify that the constants module provides the expected values
and helper functions work correctly. This ensures the centralized constants
remain consistent and don't break server functionality.
"""

import pytest
from constants import (
    # Socket.IO events
    MESSAGE_IN, MESSAGE_OUT,
    
    # Message types
    MSG_TYPE_SYSTEM, MSG_TYPE_PLAYER, MSG_TYPE_NPC, MSG_TYPE_ERROR,
    
    # Command prefixes
    COMMAND_PREFIX, ROOM_BUILD_PREFIX,
    
    # Defaults
    DEFAULT_MAX_MESSAGE_LENGTH, DEFAULT_SAFETY_LEVEL,
    
    # Environment variables
    ENV_GEMINI_API_KEY, ENV_GOOGLE_API_KEY,
    
    # Validation constants
    SAFETY_LEVELS, MIN_WORLD_NAME_LENGTH, MAX_WORLD_NAME_LENGTH,
    
    # Helper functions
    get_message_payload, is_slash_command, is_room_build_command,
    validate_world_name, validate_safety_level
)


class TestConstants:
    """Test that constants have expected values."""
    
    def test_socket_io_events(self):
        """Verify Socket.IO event names match protocol."""
        assert MESSAGE_IN == 'message_to_server'
        assert MESSAGE_OUT == 'message'
    
    def test_message_types(self):
        """Verify message type constants for client rendering."""
        assert MSG_TYPE_SYSTEM == 'system'
        assert MSG_TYPE_PLAYER == 'player'
        assert MSG_TYPE_NPC == 'npc'
        assert MSG_TYPE_ERROR == 'error'
    
    def test_command_prefixes(self):
        """Verify command parsing prefixes."""
        assert COMMAND_PREFIX == '/'
        assert ROOM_BUILD_PREFIX == '+'
    
    def test_defaults_are_reasonable(self):
        """Verify default values make sense."""
        assert DEFAULT_MAX_MESSAGE_LENGTH == 1000
        assert DEFAULT_SAFETY_LEVEL == 'PG-13'
        assert DEFAULT_SAFETY_LEVEL in SAFETY_LEVELS
    
    def test_environment_variable_names(self):
        """Verify env var names match expected patterns."""
        assert ENV_GEMINI_API_KEY == 'GEMINI_API_KEY'
        assert ENV_GOOGLE_API_KEY == 'GOOGLE_API_KEY'
    
    def test_safety_levels_complete(self):
        """Verify all expected safety levels are present."""
        expected = ['G', 'PG-13', 'R', 'OFF']
        assert SAFETY_LEVELS == expected
    
    def test_world_name_limits(self):
        """Verify world name length constraints."""
        assert MIN_WORLD_NAME_LENGTH == 2
        assert MAX_WORLD_NAME_LENGTH == 64
        assert MIN_WORLD_NAME_LENGTH < MAX_WORLD_NAME_LENGTH


class TestHelperFunctions:
    """Test helper functions in constants module."""
    
    def test_get_message_payload_basic(self):
        """Test creating basic message payloads."""
        payload = get_message_payload(MSG_TYPE_SYSTEM, "Hello world")
        expected = {'type': 'system', 'content': 'Hello world'}
        assert payload == expected
    
    def test_get_message_payload_with_name(self):
        """Test creating message payloads with speaker name."""
        payload = get_message_payload(MSG_TYPE_PLAYER, "Hi there!", "Alice")
        expected = {'type': 'player', 'content': 'Hi there!', 'name': 'Alice'}
        assert payload == expected
    
    def test_get_message_payload_without_name(self):
        """Test that None name is handled correctly."""
        payload = get_message_payload(MSG_TYPE_ERROR, "Oops!", None)
        expected = {'type': 'error', 'content': 'Oops!'}
        assert payload == expected
        assert 'name' not in payload
    
    def test_is_slash_command_valid(self):
        """Test slash command detection."""
        assert is_slash_command("/help")
        assert is_slash_command("/auth login Alice")
        assert is_slash_command("   /setup   ")  # with whitespace
    
    def test_is_slash_command_invalid(self):
        """Test non-slash commands are rejected."""
        assert not is_slash_command("help")
        assert not is_slash_command("look")
        assert not is_slash_command("say hello")
        assert not is_slash_command("")
        assert not is_slash_command(None)
        assert not is_slash_command(123)
    
    def test_is_room_build_command_valid(self):
        """Test room build command detection."""
        assert is_room_build_command("+room")
        assert is_room_build_command("+door tavern")
        assert is_room_build_command("   +stairs   ")  # with whitespace
    
    def test_is_room_build_command_invalid(self):
        """Test non-build commands are rejected."""
        assert not is_room_build_command("room")
        assert not is_room_build_command("/room create")
        assert not is_room_build_command("look")
        assert not is_room_build_command("")
        assert not is_room_build_command(None)
        assert not is_room_build_command(123)
    
    def test_validate_world_name_valid(self):
        """Test valid world names."""
        assert validate_world_name("My World")  # normal case
        assert validate_world_name("AB")  # minimum length
        assert validate_world_name("X" * 64)  # maximum length
        assert validate_world_name("  Test  ")  # whitespace trimmed
    
    def test_validate_world_name_invalid(self):
        """Test invalid world names."""
        assert not validate_world_name("A")  # too short
        assert not validate_world_name("X" * 65)  # too long
        assert not validate_world_name("")  # empty
        assert not validate_world_name("   ")  # whitespace only
        assert not validate_world_name(None)  # not string
        assert not validate_world_name(123)  # not string
    
    def test_validate_safety_level_valid(self):
        """Test valid safety levels."""
        for level in SAFETY_LEVELS:
            assert validate_safety_level(level)
            assert validate_safety_level(level.lower())  # case insensitive
    
    def test_validate_safety_level_invalid(self):
        """Test invalid safety levels."""
        assert not validate_safety_level("X")
        assert not validate_safety_level("PG")  # close but wrong
        assert not validate_safety_level("")
        assert not validate_safety_level(None)
        assert not validate_safety_level(123)


class TestConstantsIntegration:
    """Test that constants integrate properly with expected usage patterns."""
    
    def test_all_message_types_different(self):
        """Ensure message types are distinct."""
        types = [MSG_TYPE_SYSTEM, MSG_TYPE_PLAYER, MSG_TYPE_NPC, MSG_TYPE_ERROR]
        assert len(set(types)) == len(types), "Message types must be unique"
    
    def test_prefixes_different(self):
        """Ensure command prefixes don't conflict."""
        assert COMMAND_PREFIX != ROOM_BUILD_PREFIX
    
    def test_message_payload_structure(self):
        """Test that message payloads follow expected structure for client."""
        # The client expects 'type' and 'content' keys, with optional 'name'
        payload = get_message_payload(MSG_TYPE_SYSTEM, "Test message", "TestUser")
        
        # Required keys
        assert 'type' in payload
        assert 'content' in payload
        
        # Values match expected format
        assert isinstance(payload['type'], str)
        assert isinstance(payload['content'], str)
        
        # Optional name is handled correctly
        assert payload.get('name') == "TestUser"
    
    def test_constants_are_strings(self):
        """Verify that string constants are actually strings."""
        string_constants = [
            MESSAGE_IN, MESSAGE_OUT,
            MSG_TYPE_SYSTEM, MSG_TYPE_PLAYER, MSG_TYPE_NPC, MSG_TYPE_ERROR,
            COMMAND_PREFIX, ROOM_BUILD_PREFIX,
            DEFAULT_SAFETY_LEVEL,
            ENV_GEMINI_API_KEY, ENV_GOOGLE_API_KEY
        ]
        
        for constant in string_constants:
            assert isinstance(constant, str), f"Constant {constant} should be a string"
    
    def test_numeric_constants_reasonable(self):
        """Verify numeric constants have reasonable values."""
        assert isinstance(DEFAULT_MAX_MESSAGE_LENGTH, int)
        assert DEFAULT_MAX_MESSAGE_LENGTH > 0
        assert DEFAULT_MAX_MESSAGE_LENGTH <= 10000  # reasonable upper limit
        
        assert isinstance(MIN_WORLD_NAME_LENGTH, int)
        assert isinstance(MAX_WORLD_NAME_LENGTH, int)
        assert MIN_WORLD_NAME_LENGTH > 0
        assert MAX_WORLD_NAME_LENGTH > MIN_WORLD_NAME_LENGTH