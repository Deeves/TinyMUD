from __future__ import annotations

"""Centralized command registry system for TinyMUD.

This module provides a unified DSL for registering commands with automatic parsing,
validation, help text generation, and admin gating. It eliminates the duplication
across auth_router, dialogue_router, trade_router, interaction_router, admin_router,
and player_router by centralizing command metadata and execution logic.

Key Features:
- Declarative command registration using decorators
- Automatic argument parsing and validation
- Built-in admin permission gating
- Auto-generated help text from command metadata
- Support for both slash commands (/cmd) and flow commands (natural language)
- Preservation of existing message formats for client compatibility

Architecture:
The registry uses a two-phase approach:
1. Registration phase: Commands register their metadata (name, args, permissions, etc.)
2. Dispatch phase: Incoming text is matched against registered commands and routed

This maintains the existing router contract while eliminating parsing duplication.
"""

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple
from enum import Enum

from command_context import CommandContext, EmitFn


class PermissionLevel(Enum):
    """Permission levels for command execution."""
    PUBLIC = "public"      # Anyone can use
    AUTHENTICATED = "authenticated"  # Requires session
    ADMIN = "admin"       # Requires admin privileges


class ArgumentType(Enum):
    """Argument types for validation and parsing."""
    STRING = "string"
    PLAYER = "player"     # Resolves to player name
    NPC = "npc"          # Resolves to NPC name
    ROOM = "room"        # Resolves to room ID
    OBJECT = "object"    # Resolves to object
    NUMBER = "number"
    OPTIONAL = "optional"


@dataclass
class CommandArgument:
    """Metadata for a single command argument."""
    name: str
    type: ArgumentType
    description: str
    required: bool = True
    default: Any = None
    
    def __post_init__(self):
        """Auto-set required=False for optional arguments."""
        if self.type == ArgumentType.OPTIONAL:
            self.required = False


@dataclass
class CommandMetadata:
    """Complete metadata for a registered command."""
    name: str                                    # Command name (e.g., "auth", "barter")
    description: str                             # Human-readable description
    permission: PermissionLevel                  # Required permission level
    arguments: List[CommandArgument] = field(default_factory=list)

    # Sub-command support (like /auth create, /auth login)
    subcommands: Dict[str, 'CommandMetadata'] = field(default_factory=dict)

    # Aliases (alternative command names)
    aliases: List[str] = field(default_factory=list)

    # Flow command patterns (for natural language matching)
    flow_patterns: List[str] = field(default_factory=list)

    # Handler function
    handler: Optional[Callable] = None

    # Module/router this belongs to (for organization)
    router: str = ""

    def generate_usage_text(self) -> str:
        """Generate usage text from metadata."""
        if self.subcommands:
            subcmd_names = "|".join(self.subcommands.keys())
            return f"Usage: /{self.name} <{subcmd_names}> ..."
        
        arg_strs = []
        for arg in self.arguments:
            if arg.required:
                arg_strs.append(f"<{arg.name}>")
            else:
                arg_strs.append(f"[{arg.name}]")
        args_part = " ".join(arg_strs)
        return f"Usage: /{self.name} {args_part}".strip()

    def generate_help_text(self) -> str:
        """Generate comprehensive help text."""
        lines = [f"**/{self.name}** - {self.description}"]
        lines.append(self.generate_usage_text())
        
        if self.arguments:
            lines.append("\nArguments:")
            for arg in self.arguments:
                req_str = "required" if arg.required else "optional"
                lines.append(f"  {arg.name} ({arg.type.value}, {req_str}) - {arg.description}")
        
        if self.subcommands:
            lines.append("\nSubcommands:")
            for subcmd_name, subcmd in self.subcommands.items():
                lines.append(f"  {subcmd_name} - {subcmd.description}")
        
        if self.aliases:
            lines.append(f"\nAliases: {', '.join(self.aliases)}")
        
        return "\n".join(lines)


class CommandRegistry:
    """Central registry for all MUD commands."""
    
    def __init__(self):
        self._commands: Dict[str, CommandMetadata] = {}
        self._flow_commands: List[Tuple[re.Pattern, CommandMetadata]] = []
        self._aliases: Dict[str, str] = {}  # alias -> primary_name

    def register_command(self, metadata: CommandMetadata) -> None:
        """Register a command with the registry."""
        # Register primary name
        self._commands[metadata.name] = metadata
        
        # Register aliases
        for alias in metadata.aliases:
            self._aliases[alias] = metadata.name
        
        # Compile flow patterns
        for pattern in metadata.flow_patterns:
            compiled = re.compile(pattern, re.IGNORECASE)
            self._flow_commands.append((compiled, metadata))

    def command(
        self,
        name: str,
        description: str = "",
        permission: PermissionLevel = PermissionLevel.PUBLIC,
        arguments: Optional[List[CommandArgument]] = None,
        aliases: Optional[List[str]] = None,
        flow_patterns: Optional[List[str]] = None,
        router: str = ""
    ):
        """Decorator for registering slash commands."""
        def decorator(handler_func):
            metadata = CommandMetadata(
                name=name,
                description=description,
                permission=permission,
                arguments=arguments or [],
                aliases=aliases or [],
                flow_patterns=flow_patterns or [],
                handler=handler_func,
                router=router
            )
            self.register_command(metadata)
            return handler_func
        return decorator

    def subcommand(self, parent_name: str, sub_name: str, description: str = "",
                   permission: Optional[PermissionLevel] = None,
                   arguments: Optional[List[CommandArgument]] = None):
        """Decorator for registering subcommands."""
        def decorator(handler_func):
            parent = self._commands.get(parent_name)
            if not parent:
                raise ValueError(f"Parent command '{parent_name}' not found")

            subcmd = CommandMetadata(
                name=sub_name,
                description=description,
                permission=permission or parent.permission,
                arguments=arguments or [],
                handler=handler_func,
                router=parent.router
            )
            parent.subcommands[sub_name] = subcmd
            return handler_func
        return decorator

    def flow_command(self, patterns: List[str], description: str = "",
                     permission: PermissionLevel = PermissionLevel.PUBLIC,
                     router: str = ""):
        """Decorator for registering natural language flow commands."""
        def decorator(handler_func):
            # Generate a synthetic name from the first pattern
            name = f"flow_{len(self._flow_commands)}"
            metadata = CommandMetadata(
                name=name,
                description=description,
                permission=permission,
                flow_patterns=patterns,
                handler=handler_func,
                router=router
            )
            self.register_command(metadata)
            return handler_func
        return decorator

    def try_handle_slash(self, ctx: CommandContext, sid: str | None,
                         cmd: str, args: List[str], raw: str, emit: EmitFn) -> bool:
        """Handle slash commands through the registry."""
        # Resolve aliases
        resolved_cmd = self._aliases.get(cmd, cmd)
        metadata = self._commands.get(resolved_cmd)
        
        if not metadata or not metadata.handler:
            return False

        # Check permissions
        if not self._check_permissions(metadata, ctx, sid, emit):
            return True

        # Handle subcommands
        if metadata.subcommands and args:
            sub_name = args[0].lower()
            if sub_name in metadata.subcommands:
                sub_metadata = metadata.subcommands[sub_name]
                if not self._check_permissions(sub_metadata, ctx, sid, emit):
                    return True

                # Parse and validate subcommand arguments
                parsed_args = self._parse_arguments(sub_metadata, args[1:], emit)
                if parsed_args is None:
                    self._emit_usage(sub_metadata, emit, ctx.message_out)
                    return True

                # Execute subcommand handler
                return sub_metadata.handler(ctx, sid, parsed_args, emit)

        # Parse and validate arguments for primary command
        parsed_args = self._parse_arguments(metadata, args, emit)
        if parsed_args is None:
            self._emit_usage(metadata, emit, ctx.message_out)
            return True

        # Execute primary command handler 
        return metadata.handler(ctx, sid, parsed_args, emit)

    def try_handle_flow(self, ctx: CommandContext, sid: str | None,
                        message: str, emit: EmitFn) -> bool:
        """Handle natural language flow commands."""
        for pattern, metadata in self._flow_commands:
            match = pattern.match(message)
            if match:
                # Check permissions
                if not self._check_permissions(metadata, ctx, sid, emit):
                    return True

                # Execute with regex groups as arguments
                return metadata.handler(ctx, sid, match, emit)

        return False

    def _check_permissions(self, metadata: CommandMetadata, ctx: CommandContext,
                           sid: str | None, emit: EmitFn) -> bool:
        """Check if user has permission to execute command."""
        if metadata.permission == PermissionLevel.PUBLIC:
            return True

        if sid is None:
            emit(ctx.message_out, {'type': 'error', 'content': 'Not connected.'})
            return False

        if metadata.permission == PermissionLevel.AUTHENTICATED:
            if sid not in ctx.sessions:
                emit(ctx.message_out, {'type': 'error', 'content': 'Please log in first.'})
                return False
            return True

        if metadata.permission == PermissionLevel.ADMIN:
            if sid not in ctx.admins:
                emit(ctx.message_out, {'type': 'error', 'content': 'Admin command. Admin rights required.'})
                return False
            return True

        return False

    def _parse_arguments(self, metadata: CommandMetadata, args: List[str],
                         emit: EmitFn) -> Optional[Dict[str, Any]]:
        """Parse and validate command arguments."""
        parsed = {}

        # Check minimum required arguments
        required_count = sum(1 for arg in metadata.arguments if arg.required)
        if len(args) < required_count:
            return None

        # Parse each argument
        for i, arg_meta in enumerate(metadata.arguments):
            if i < len(args):
                raw_value = args[i]
                parsed_value = self._parse_single_argument(arg_meta, raw_value)
                parsed[arg_meta.name] = parsed_value
            elif arg_meta.required:
                return None  # Missing required argument
            else:
                parsed[arg_meta.name] = arg_meta.default

        # Collect remaining arguments as 'remaining' if there are extras
        if len(args) > len(metadata.arguments):
            remaining = args[len(metadata.arguments):]
            parsed['remaining'] = remaining

        return parsed

    def _parse_single_argument(self, arg_meta: CommandArgument, raw_value: str) -> Any:
        """Parse a single argument based on its type."""
        if arg_meta.type == ArgumentType.STRING:
            return raw_value
        elif arg_meta.type == ArgumentType.NUMBER:
            try:
                return int(raw_value)
            except ValueError:
                try:
                    return float(raw_value)
                except ValueError:
                    return raw_value  # Return as string if not a number
        # For now, return as string for complex types (PLAYER, NPC, etc.)
        # These can be resolved by the command handlers using existing utils
        return raw_value

    def _emit_usage(self, metadata: CommandMetadata, emit: EmitFn, message_out: str) -> None:
        """Emit usage text for a command."""
        usage_text = metadata.generate_usage_text()
        emit(message_out, {'type': 'error', 'content': usage_text})

    def get_all_commands(self) -> List[CommandMetadata]:
        """Get list of all registered commands."""
        return list(self._commands.values())

    def get_command(self, name: str) -> Optional[CommandMetadata]:
        """Get command metadata by name."""
        resolved_name = self._aliases.get(name, name)
        return self._commands.get(resolved_name)

    def generate_help_command(self, ctx: CommandContext, sid: str | None,
                              args: Dict[str, Any], emit: EmitFn) -> bool:
        """Built-in help command implementation."""
        if args.get('command'):
            # Help for specific command
            cmd_name = args['command']
            metadata = self.get_command(cmd_name)
            if metadata:
                help_text = metadata.generate_help_text()
                emit(ctx.message_out, {'type': 'system', 'content': help_text})
            else:
                emit(ctx.message_out, {'type': 'error', 'content': f"Unknown command: {cmd_name}"})
        else:
            # List all available commands
            commands = self.get_all_commands()
            # Filter by permission level
            available = []
            for cmd in commands:
                if self._check_permissions_silent(cmd, ctx, sid):
                    available.append(f"/{cmd.name} - {cmd.description}")

            if available:
                help_text = "Available commands:\n" + "\n".join(available)
                help_text += "\n\nUse '/help <command>' for detailed information."
            else:
                help_text = "No commands available."

            emit(ctx.message_out, {'type': 'system', 'content': help_text})

        return True

    def _check_permissions_silent(self, metadata: CommandMetadata, ctx: CommandContext,
                                  sid: str | None) -> bool:
        """Check permissions without emitting error messages."""
        if metadata.permission == PermissionLevel.PUBLIC:
            return True
        if sid is None:
            return False
        if metadata.permission == PermissionLevel.AUTHENTICATED:
            return sid in ctx.sessions
        if metadata.permission == PermissionLevel.ADMIN:
            return sid in ctx.admins
        return False


# Global registry instance
registry = CommandRegistry()

# Register built-in help command
@registry.command(
    name="help",
    description="Display help information for commands",
    arguments=[
        CommandArgument("command", ArgumentType.STRING, "Command to get help for", required=False)
    ]
)
def help_command(ctx: CommandContext, sid: str | None, args: Dict[str, Any], emit: EmitFn) -> bool:
    return registry.generate_help_command(ctx, sid, args, emit)