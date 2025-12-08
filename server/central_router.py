"""Central command router coordinator using the command registry system.

This module demonstrates how to consolidate command parsing duplication by using 
the centralized command registry. It provides a single point for routing all 
commands while preserving existing behavior and message formats.

Key improvements:
- Eliminates duplicated command parsing logic across routers
- Provides automatic help text generation  
- Centralizes permission checking and argument validation
- Maintains backward compatibility with existing router interfaces
- Enables easy addition of new commands without code duplication

Usage pattern:
1. Register commands using the @registry.command decorator
2. Use the central try_handle_command() function to route commands
3. Existing routers can be gradually migrated or kept as compatibility wrappers
"""

from __future__ import annotations

from typing import Dict, Any

from command_context import CommandContext, EmitFn
from command_registry import registry, CommandArgument, ArgumentType, PermissionLevel


def try_handle_command(ctx: CommandContext, sid: str | None, cmd: str, 
                      args: list[str], raw: str, emit: EmitFn) -> bool:
    """Central command handler using the registry system.
    
    This function replaces the individual router try_handle calls by routing
    through the centralized command registry. Commands can be registered from
    any module and will be automatically handled with proper parsing, validation,
    permission checking, and help generation.
    
    Args:
        ctx: Command context with world state and utilities
        sid: Socket session ID (None if not connected)
        cmd: Command name (without the / prefix)
        args: List of command arguments
        raw: Original raw command text
        emit: Function to emit messages back to client
        
    Returns:
        bool: True if command was handled (successfully or with error), False if unknown
    """
    return registry.try_handle_slash(ctx, sid, cmd, args, raw, emit)


def try_handle_flow_command(ctx: CommandContext, sid: str | None, message: str, 
                           emit: EmitFn) -> bool:
    """Handle natural language flow commands using the registry.
    
    This handles patterns like "interact with <object>" or quoted speech that
    don't follow the /command format.
    
    Args:
        ctx: Command context
        sid: Socket session ID
        message: Full user message
        emit: Function to emit responses
        
    Returns:
        bool: True if a flow command was matched and handled
    """
    return registry.try_handle_flow(ctx, sid, message, emit)


# Example: Register a simple test command to demonstrate the system
@registry.command(
    name="registry_test", 
    description="Test command to demonstrate centralized registry",
    permission=PermissionLevel.AUTHENTICATED,
    arguments=[
        CommandArgument("message", ArgumentType.STRING, "Test message to echo", required=False, default="Hello!")
    ]
)
def test_command_handler(ctx: CommandContext, sid: str | None, args: Dict[str, Any], emit: EmitFn) -> bool:
    """Example command handler showing registry usage."""
    message = args.get('message', 'Hello!')
    
    # Handle remaining args if user provided multiple words
    if 'remaining' in args and args['remaining']:
        message = ' '.join([message] + args['remaining'])
    
    emit(ctx.message_out, {
        'type': 'system', 
        'content': f'Registry test: {message}'
    })
    return True


# Example: Register a flow command for natural language
@registry.flow_command(
    patterns=[r"^test registry with (.+)$"],
    description="Test flow command matching natural language",
    permission=PermissionLevel.PUBLIC
)
def test_flow_handler(ctx: CommandContext, sid: str | None, match, emit: EmitFn) -> bool:
    """Example flow command handler."""
    captured_text = match.group(1)
    emit(ctx.message_out, {
        'type': 'system',
        'content': f'Flow command captured: {captured_text}'
    })
    return True


# Compatibility functions for gradual migration

def get_command_help(command_name: str = None) -> str:
    """Get help text for a specific command or all commands.
    
    Args:
        command_name: Specific command to get help for, or None for all commands
        
    Returns:
        str: Formatted help text
    """
    if command_name:
        cmd = registry.get_command(command_name)
        if cmd:
            return cmd.generate_help_text()
        return f"Unknown command: {command_name}"
    
    # Generate help for all commands
    commands = registry.get_all_commands()
    if not commands:
        return "No commands registered."
    
    help_lines = ["Available commands:"]
    for cmd in commands:
        help_lines.append(f"  /{cmd.name} - {cmd.description}")
    
    help_lines.append("\nUse '/help <command>' for detailed information.")
    return "\n".join(help_lines)


def list_commands_by_router(router_name: str) -> list[str]:
    """Get list of commands registered by a specific router module.
    
    Args:
        router_name: Name of the router module
        
    Returns:
        list[str]: Command names from that router
    """
    commands = registry.get_all_commands()
    return [cmd.name for cmd in commands if cmd.router == router_name]


def get_command_usage(command_name: str) -> str:
    """Get just the usage text for a command.
    
    Args:
        command_name: Name of the command
        
    Returns:
        str: Usage text or error message
    """
    cmd = registry.get_command(command_name)
    if cmd:
        return cmd.generate_usage_text()
    return f"Unknown command: {command_name}"


# Statistics and debugging functions

def get_registry_stats() -> Dict[str, Any]:
    """Get statistics about the command registry for debugging/monitoring."""
    commands = registry.get_all_commands()
    
    stats = {
        'total_commands': len(commands),
        'commands_by_permission': {
            'public': 0,
            'authenticated': 0, 
            'admin': 0
        },
        'commands_by_router': {},
        'commands_with_subcommands': 0,
        'total_subcommands': 0,
        'flow_commands': len(registry._flow_commands)
    }
    
    for cmd in commands:
        # Count by permission
        if cmd.permission == PermissionLevel.PUBLIC:
            stats['commands_by_permission']['public'] += 1
        elif cmd.permission == PermissionLevel.AUTHENTICATED:
            stats['commands_by_permission']['authenticated'] += 1
        elif cmd.permission == PermissionLevel.ADMIN:
            stats['commands_by_permission']['admin'] += 1
        
        # Count by router
        router = cmd.router or 'unknown'
        stats['commands_by_router'][router] = stats['commands_by_router'].get(router, 0) + 1
        
        # Count subcommands
        if cmd.subcommands:
            stats['commands_with_subcommands'] += 1
            stats['total_subcommands'] += len(cmd.subcommands)
    
    return stats