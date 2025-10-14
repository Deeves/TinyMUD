"""Example migration of auth_router.py to use the centralized command registry.

This shows how to register commands with the centralized registry while
preserving existing behavior and message formats for client compatibility.

The migration demonstrates:
- Converting manual command parsing to declarative registration
- Preserving exact message formats and error conditions
- Using subcommands for /auth create, /auth login, etc.
- Admin permission gating through the registry
- Automatic usage text generation
"""

from __future__ import annotations

from typing import Dict, Any

from command_context import CommandContext, EmitFn
from command_registry import (
    registry, CommandArgument, ArgumentType, PermissionLevel
)
from account_service import create_account_and_login, login_existing
from admin_service import promote_user, demote_user, list_admins


# Register the main /auth command with subcommands
@registry.command(
    name="auth",
    description="Authentication and account management",
    permission=PermissionLevel.PUBLIC,
    router="auth_router"
)
def auth_main_handler(ctx: CommandContext, sid: str | None, args: Dict[str, Any],
                      emit: EmitFn) -> bool:
    """Main auth command handler - should not be called as subcommands handle everything."""
    # This should only be reached if no subcommand was provided
    emit(ctx.message_out, {'type': 'system', 'content': 'Usage: /auth <create|login> ...'})
    return True


# Register auth subcommands
@registry.subcommand(
    parent_name="auth",
    sub_name="create",
    description="Create a new account and character",
    permission=PermissionLevel.PUBLIC,
    arguments=[
        CommandArgument("display_name", ArgumentType.STRING, "Character display name"),
        CommandArgument("password", ArgumentType.STRING, "Account password"),
        CommandArgument("description", ArgumentType.STRING, "Character description")
    ]
)
def auth_create_handler(ctx: CommandContext, sid: str | None, args: Dict[str, Any],
                        emit: EmitFn) -> bool:
    """Handle /auth create command."""
    MESSAGE_OUT = ctx.message_out
    
    if sid is None:
        emit(MESSAGE_OUT, {'type': 'error', 'content': 'Not connected.'})
        return True
    
    # Extract arguments - the registry has already parsed them
    display_name = args.get('display_name', '')
    password = args.get('password', '')
    description = args.get('description', '')
    
    # Handle the case where arguments might be joined by remaining args
    # This preserves the original pipe-separated parsing behavior
    if 'remaining' in args:
        remaining = args['remaining']
        if len(remaining) >= 2:
            password = remaining[0] if not password else password
            description = remaining[1] if not description else description
            if len(remaining) > 2:
                # Join remaining parts as description
                description = ' '.join(remaining[1:])
    
    # Check for pipe-separated format in the display_name if that's all we got
    if '|' in display_name and not password:
        parts = display_name.split('|')
        if len(parts) >= 3:
            display_name = parts[0].strip()
            password = parts[1].strip()
            description = parts[2].strip()
        else:
            usage_msg = 'Usage: /auth create <display_name> | <password> | <description>'
            emit(MESSAGE_OUT, {'type': 'error', 'content': usage_msg})
            return True
    
    if not all([display_name, password, description]):
        usage_msg = 'Usage: /auth create <display_name> | <password> | <description>'
        emit(MESSAGE_OUT, {'type': 'error', 'content': usage_msg})
        return True
    
    # Use the existing service
    ok, err, emits, broadcasts = create_account_and_login(
        ctx.world, ctx.sessions, ctx.admins, display_name, password,
        description, ctx.state_path
    )
    
    if err:
        emit(MESSAGE_OUT, {'type': 'error', 'content': err})
        return True
    
    for p in emits:
        emit(MESSAGE_OUT, p)
    for room_id, payload in broadcasts:
        ctx.broadcast_to_room(room_id, payload, exclude_sid=sid)
    
    return True


@registry.subcommand(
    parent_name="auth",
    sub_name="login",
    description="Log in to an existing account",
    permission=PermissionLevel.PUBLIC,
    arguments=[
        CommandArgument("display_name", ArgumentType.STRING, "Character display name"),
        CommandArgument("password", ArgumentType.STRING, "Account password")
    ]
)
def auth_login_handler(ctx: CommandContext, sid: str | None, args: Dict[str, Any], emit: EmitFn) -> bool:
    """Handle /auth login command."""
    MESSAGE_OUT = ctx.message_out
    
    if sid is None:
        emit(MESSAGE_OUT, {'type': 'error', 'content': 'Not connected.'})
        return True
    
    # Extract arguments with pipe-separated fallback
    display_name = args.get('display_name', '')
    password = args.get('password', '')
    
    # Handle remaining args or pipe format
    if 'remaining' in args and args['remaining']:
        if not password:
            password = args['remaining'][0] if args['remaining'] else ''
    
    if '|' in display_name and not password:
        parts = display_name.split('|')
        if len(parts) >= 2:
            display_name = parts[0].strip()
            password = parts[1].strip()
        else:
            emit(MESSAGE_OUT, {'type': 'error', 'content': 'Usage: /auth login <display_name> | <password>'})
            return True
    
    if not all([display_name, password]):
        emit(MESSAGE_OUT, {'type': 'error', 'content': 'Usage: /auth login <display_name> | <password>'})
        return True
    
    # Use the existing service
    ok, err, emits, broadcasts = login_existing(
        ctx.world, ctx.sessions, display_name, password
    )
    
    if err:
        emit(MESSAGE_OUT, {'type': 'error', 'content': err})
        return True
    
    for p in emits:
        emit(MESSAGE_OUT, p)
    for room_id, payload in broadcasts:
        ctx.broadcast_to_room(room_id, payload, exclude_sid=sid)
    
    return True


@registry.subcommand(
    parent_name="auth",
    sub_name="promote",
    description="Elevate a user to admin (admin only)",
    permission=PermissionLevel.ADMIN,
    arguments=[
        CommandArgument("target_name", ArgumentType.STRING, "Name of user to promote")
    ]
)
def auth_promote_handler(ctx: CommandContext, sid: str | None, args: Dict[str, Any], emit: EmitFn) -> bool:
    """Handle /auth promote command."""
    MESSAGE_OUT = ctx.message_out
    
    target_name = args.get('target_name', '')
    if 'remaining' in args:
        # Join all remaining as target name (handles spaces)
        full_args = [target_name] + args['remaining']
        target_name = ' '.join(full_args).strip()
    
    target_name = ctx.strip_quotes(target_name)
    
    if not target_name:
        emit(MESSAGE_OUT, {'type': 'error', 'content': 'Usage: /auth promote <name>'})
        return True
    
    ok, err, emits2, broadcasts2 = promote_user(
        ctx.world, ctx.sessions, ctx.admins, target_name, ctx.state_path
    )
    
    if err:
        emit(MESSAGE_OUT, {'type': 'error', 'content': err})
        return True
    
    for p in emits2:
        emit(MESSAGE_OUT, p)
    for room_id, payload in broadcasts2:
        ctx.broadcast_to_room(room_id, payload, exclude_sid=sid)
    
    return True


@registry.subcommand(
    parent_name="auth",
    sub_name="demote",
    description="Revoke user's admin rights (admin only)",
    permission=PermissionLevel.ADMIN,
    arguments=[
        CommandArgument("target_name", ArgumentType.STRING, "Name of user to demote")
    ]
)
def auth_demote_handler(ctx: CommandContext, sid: str | None, args: Dict[str, Any], emit: EmitFn) -> bool:
    """Handle /auth demote command."""
    MESSAGE_OUT = ctx.message_out
    
    target_name = args.get('target_name', '')
    if 'remaining' in args:
        # Join all remaining as target name (handles spaces)
        full_args = [target_name] + args['remaining']
        target_name = ' '.join(full_args).strip()
    
    target_name = ctx.strip_quotes(target_name)
    
    if not target_name:
        emit(MESSAGE_OUT, {'type': 'error', 'content': 'Usage: /auth demote <name>'})
        return True
    
    ok, err, emits2, broadcasts2 = demote_user(
        ctx.world, ctx.sessions, ctx.admins, target_name, ctx.state_path
    )
    
    if err:
        emit(MESSAGE_OUT, {'type': 'error', 'content': err})
        return True
    
    for p in emits2:
        emit(MESSAGE_OUT, p)
    for room_id, payload in broadcasts2:
        ctx.broadcast_to_room(room_id, payload, exclude_sid=sid)
    
    return True


@registry.subcommand(
    parent_name="auth",
    sub_name="list_admins",
    description="List all admin users",
    permission=PermissionLevel.PUBLIC
)
def auth_list_admins_handler(ctx: CommandContext, sid: str | None, args: Dict[str, Any], emit: EmitFn) -> bool:
    """Handle /auth list_admins command."""
    MESSAGE_OUT = ctx.message_out
    
    ok, err, emits2 = list_admins(ctx.world, ctx.sessions, ctx.admins)
    
    if err:
        emit(MESSAGE_OUT, {'type': 'error', 'content': err})
        return True
    
    for p in emits2:
        emit(MESSAGE_OUT, p)
    
    return True


# Compatibility function that can be called from the original router pattern
def try_handle(ctx: CommandContext, sid: str | None, cmd: str, args: list[str], raw: str, emit: EmitFn) -> bool:
    """Compatibility wrapper for the old router interface.
    
    This allows gradual migration - the server can call either the old or new interface.
    """
    return registry.try_handle_slash(ctx, sid, cmd, args, raw, emit)