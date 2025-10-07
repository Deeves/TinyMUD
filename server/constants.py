"""
TinyMUD Server Constants

Central location for all server configuration constants, message types, event names,
and other shared values. Having these in one place makes the codebase more maintainable
and reduces magic strings scattered throughout the code.

This follows the coding guidelines of being roughly 30% comments - each constant is
documented with its purpose and usage context to help new contributors understand
how the server operates and where these values are used.
"""

# =============================================================================
# Socket.IO Event Names
# =============================================================================

# The event name that clients send when they want to communicate with the server
# Used by the Godot client in src/chat_ui.gd and socket_io_client.gd
MESSAGE_IN = 'message_to_server'

# The event name the server uses to send messages back to clients
# This is the primary communication channel from server to client
MESSAGE_OUT = 'message'

# =============================================================================
# Message Types  
# =============================================================================

# These type constants define the different categories of messages sent to clients
# The client (src/chat_ui.gd) uses these to apply different colors and formatting

# System messages - server notifications, command results, world state changes
MSG_TYPE_SYSTEM = 'system'

# Player messages - things said by other human players in the world
MSG_TYPE_PLAYER = 'player'  

# NPC messages - dialogue and responses from AI-driven non-player characters
MSG_TYPE_NPC = 'npc'

# Error messages - command failures, invalid input, system errors
MSG_TYPE_ERROR = 'error'

# =============================================================================
# Command Prefixes and Special Characters
# =============================================================================

# Prefix for slash commands like /auth, /help, /admin, etc.
# Used in server.py handle_command() to route administrative and system commands
COMMAND_PREFIX = '/'

# Prefix for room building/creation commands
# Used in room creation syntax like +room, +door, +stairs
ROOM_BUILD_PREFIX = '+'

# =============================================================================
# Server Configuration Defaults
# =============================================================================

# Maximum length for incoming player messages to prevent spam/abuse
# Can be overridden with MUD_MAX_MESSAGE_LEN environment variable
DEFAULT_MAX_MESSAGE_LENGTH = 1000

# Server build identifier for version tracking and external fixture compatibility
# Increment when making behavioral changes that external tools need to detect
SERVER_BUILD_ID = 8

# Default safety level for AI content generation
# Used when world.safety_level is not set during world initialization
DEFAULT_SAFETY_LEVEL = 'PG-13'

# Default NPC description when creating characters without explicit descriptions
DEFAULT_NPC_DESCRIPTION = "A person who belongs in this world."

# =============================================================================
# Environment Variable Keys
# =============================================================================

# Environment variable names for server configuration
# These allow deployment-time configuration without code changes

# Google Gemini API key for AI functionality
ENV_GEMINI_API_KEY = 'GEMINI_API_KEY'
ENV_GOOGLE_API_KEY = 'GOOGLE_API_KEY'  # Alternative key name

# Maximum message length override
ENV_MAX_MESSAGE_LEN = 'MUD_MAX_MESSAGE_LEN'

# Server host and port configuration
ENV_HOST = 'MUD_HOST'
ENV_PORT = 'MUD_PORT'

# Default values for server networking
DEFAULT_HOST = '0.0.0.0'
DEFAULT_PORT = 5000

# =============================================================================
# World State and Persistence
# =============================================================================

# Default filename for world state persistence
DEFAULT_WORLD_STATE_FILE = 'world_state.json'

# Debounced save delay in seconds - how long to wait before saving after changes
# This prevents excessive disk I/O during rapid world state mutations
DEFAULT_SAVE_DELAY = 2.0

# =============================================================================
# Character and Inventory Limits
# =============================================================================

# Minimum and maximum lengths for world names during setup
MIN_WORLD_NAME_LENGTH = 2
MAX_WORLD_NAME_LENGTH = 64

# Minimum length for world descriptions to ensure meaningful content
MIN_WORLD_DESCRIPTION_LENGTH = 10

# Minimum length for conflict descriptions during world setup  
MIN_CONFLICT_DESCRIPTION_LENGTH = 5

# =============================================================================
# Game Mechanics Constants
# =============================================================================

# Valid safety levels for AI content generation
# These map to Google's safety settings and control content appropriateness
SAFETY_LEVELS = ['G', 'PG-13', 'R', 'OFF']

# Valid setup modes during world creation wizard
SETUP_MODES = ['manual', 'quick']

# Valid yes/no responses for confirmation prompts
# Used in various confirmation dialogs throughout the server
CONFIRM_YES = ['yes', 'y', 'true', '1', 'on']
CONFIRM_NO = ['no', 'n', 'false', '0', 'off']

# =============================================================================
# NPC and AI Constants  
# =============================================================================

# Default tools available to NPCs for GOAP (Goal-Oriented Action Planning) AI
# These define the actions NPCs can take in the world
DEFAULT_NPC_TOOLS = [
    'move',      # Move to different rooms
    'say',       # Speak to everyone in the room
    'emote',     # Perform expressive actions
    'look',      # Examine the environment
    'interact',  # Interact with objects or other characters
]

# Cooldown periods for NPC actions to prevent spam
NPC_ACTION_COOLDOWN = 1.0  # seconds between NPC actions

# =============================================================================
# Error Messages and Status Codes
# =============================================================================

# Common error messages used throughout the server
# Centralizing these makes them consistent and easier to maintain

ERROR_NOT_CONNECTED = 'Not connected.'
ERROR_NOT_AUTHENTICATED = 'Please authenticate first with /auth.'
ERROR_PLAYER_NOT_FOUND = 'Player not found.'
ERROR_NOWHERE = 'You are nowhere.'
ERROR_MESSAGE_TOO_LONG = 'Message too long'
ERROR_INVALID_COMMAND = 'Invalid command'

# Success messages for common operations
SUCCESS_LOGIN = 'Login successful'
SUCCESS_CHARACTER_CREATED = 'Character created successfully'
SUCCESS_WORLD_SAVED = 'World saved'

# =============================================================================
# Logging and Debug Configuration
# =============================================================================

# Default log format for server messages
DEFAULT_LOG_FORMAT = '[%(levelname)s] %(message)s'

# Log levels for different components
LOG_LEVEL_DEFAULT = 'INFO'
LOG_LEVEL_DEBUG = 'DEBUG'
LOG_LEVEL_ERROR = 'ERROR'

# =============================================================================
# File and Path Constants
# =============================================================================

# Subdirectories within the server directory for organization
DIR_ROUTERS = 'routers'
DIR_TESTS = 'tests'
DIR_CACHE = '__pycache__'

# File extensions for different types of server files
EXT_PYTHON = '.py'
EXT_JSON = '.json'
EXT_LOG = '.log'

# =============================================================================
# Network and Protocol Constants  
# =============================================================================

# Socket.IO transport protocols
TRANSPORT_WEBSOCKET = 'websocket'
TRANSPORT_POLLING = 'polling'

# Default Socket.IO namespace (empty string means default)
SOCKETIO_NAMESPACE = '/'

# Connection timeout in seconds
DEFAULT_CONNECTION_TIMEOUT = 30

# =============================================================================
# Room and World Building Constants
# =============================================================================

# Special room reference that means "current room" in commands
ROOM_HERE = 'here'

# Object tags for special room features
TAG_IMMOVABLE = 'Immovable'
TAG_TRAVEL_POINT = 'Travel Point'
TAG_EDIBLE = 'edible'
TAG_DRINKABLE = 'drinkable'

# Room connection types for travel between locations
CONNECTION_DOOR = 'door'
CONNECTION_STAIRS = 'stairs'
CONNECTION_EXIT = 'exit'

# =============================================================================
# Helper Functions for Constants
# =============================================================================

def get_message_payload(msg_type: str, content: str, name: str | None = None) -> dict:
    """
    Create a standardized message payload for Socket.IO emission.
    
    This helper ensures all messages sent to clients follow the same structure
    and makes it easy to create properly formatted payloads throughout the server.
    
    Args:
        msg_type: One of MSG_TYPE_* constants (system, player, npc, error)
        content: The message text to display to the user
        name: Optional speaker name for player/npc messages
        
    Returns:
        Dictionary ready for Socket.IO emit() calls
    """
    payload = {
        'type': msg_type,
        'content': content
    }
    if name:
        payload['name'] = name
    return payload


def is_slash_command(text) -> bool:
    """
    Check if a message is a slash command.
    
    Args:
        text: The input text to check (any type)
        
    Returns:
        True if the text starts with COMMAND_PREFIX and is a command
    """
    return isinstance(text, str) and text.strip().startswith(COMMAND_PREFIX)


def is_room_build_command(text) -> bool:
    """
    Check if a message is a room building command.
    
    Args:
        text: The input text to check (any type)
        
    Returns:
        True if the text starts with ROOM_BUILD_PREFIX for room creation
    """
    return isinstance(text, str) and text.strip().startswith(ROOM_BUILD_PREFIX)


def validate_world_name(name) -> bool:
    """
    Validate a world name meets length requirements.
    
    Args:
        name: The proposed world name (any type)
        
    Returns:
        True if the name is valid length, False otherwise
    """
    if not isinstance(name, str):
        return False
    return MIN_WORLD_NAME_LENGTH <= len(name.strip()) <= MAX_WORLD_NAME_LENGTH


def validate_safety_level(level) -> bool:
    """
    Check if a safety level is valid.
    
    Args:
        level: The proposed safety level (any type)
        
    Returns:
        True if the level is in SAFETY_LEVELS, False otherwise
    """
    return isinstance(level, str) and level.upper() in SAFETY_LEVELS