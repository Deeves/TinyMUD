from __future__ import annotations

"""Authentication and account management router.

Extracted from the monolithic `server.py` so that:
  - /auth create | login | promote | demote | list_admins
  - First-user setup wizard bootstrap

Behavior (messages, errors, ordering) is intentionally preserved to keep tests green.
"""

from typing import Any

from command_context import CommandContext, EmitFn
from account_service import create_account_and_login, login_existing
from admin_service import promote_user, demote_user, list_admins


def try_handle(ctx: CommandContext, sid: str | None, cmd: str, args: list[str], raw: str, emit: EmitFn) -> bool:
    if cmd != 'auth':
        return False
    MESSAGE_OUT = ctx.message_out
    world = ctx.world

    if sid is None:
        emit(MESSAGE_OUT, {'type': 'error', 'content': 'Not connected.'})
        return True
    if len(args) == 0:
        emit(MESSAGE_OUT, {'type': 'system', 'content': 'Usage: /auth <create|login> ...'})
        return True
    sub = args[0].lower()

    # Admin subs
    if sub == 'promote':
        if sid not in ctx.admins:
            emit(MESSAGE_OUT, {'type': 'error', 'content': 'Admin command. Admin rights required.'})
            return True
        if len(args) < 2:
            emit(MESSAGE_OUT, {'type': 'error', 'content': 'Usage: /auth promote <name>'})
            return True
        target_name = ctx.strip_quotes(" ".join(args[1:]).strip())
        ok, err, emits2 = promote_user(world, ctx.sessions, ctx.admins, target_name, ctx.state_path)
        if err:
            emit(MESSAGE_OUT, {'type': 'error', 'content': err})
            return True
        for p in emits2:
            emit(MESSAGE_OUT, p)
        return True
    if sub == 'list_admins':
        names = list_admins(world)
        if not names:
            emit(MESSAGE_OUT, {'type': 'system', 'content': 'No admin users found.'})
        else:
            emit(MESSAGE_OUT, {'type': 'system', 'content': 'Admins: ' + ", ".join(names)})
        return True
    if sub == 'demote':
        if sid not in ctx.admins:
            emit(MESSAGE_OUT, {'type': 'error', 'content': 'Admin command. Admin rights required.'})
            return True
        if len(args) < 2:
            emit(MESSAGE_OUT, {'type': 'error', 'content': 'Usage: /auth demote <name>'})
            return True
        target_name = ctx.strip_quotes(" ".join(args[1:]).strip())
        ok, err, emits2 = demote_user(world, ctx.sessions, ctx.admins, target_name, ctx.state_path)
        if err:
            emit(MESSAGE_OUT, {'type': 'error', 'content': err})
            return True
        for p in emits2:
            emit(MESSAGE_OUT, p)
        return True

    # Create account
    if sub == 'create':
        try:
            joined = " ".join(args[1:])
            display_name, rest = [p.strip() for p in joined.split('|', 1)]
            password, description = [p.strip() for p in rest.split('|', 1)]
        except Exception:
            emit(MESSAGE_OUT, {'type': 'error', 'content': 'Usage: /auth create <display_name> | <password> | <description>'})
            return True
        display_name = ctx.strip_quotes(display_name)
        password = ctx.strip_quotes(password)
        if len(display_name) < 2 or len(display_name) > 32:
            emit(MESSAGE_OUT, {'type': 'error', 'content': 'Display name must be 2-32 characters.'})
            return True
        if len(password) < 3:
            emit(MESSAGE_OUT, {'type': 'error', 'content': 'Password too short (min 3).'})
            return True
        if world.get_user_by_display_name(display_name):
            emit(MESSAGE_OUT, {'type': 'error', 'content': 'That display name is already taken.'})
            return True
        ok, err, emits2, broadcasts2 = create_account_and_login(world, sid, display_name, password, description, ctx.sessions, ctx.admins, ctx.state_path)
        if not ok:
            emit(MESSAGE_OUT, {'type': 'error', 'content': err or 'Failed to create user.'})
            return True
        for p in emits2:
            emit(MESSAGE_OUT, p)
        for room_id, payload in broadcasts2:
            ctx.broadcast_to_room(room_id, payload, sid)
        # First-user setup wizard
        try:  # pragma: no cover - defensive
            if not getattr(world, 'setup_complete', False) and sid in ctx.sessions:
                uid = ctx.sessions.get(sid)
                user = world.users.get(uid) if uid else None
                if user and getattr(user, 'is_admin', False):
                    ctx.world_setup_sessions[sid] = {"step": "world_name", "temp": {}}
                    emit(MESSAGE_OUT, {'type': 'system', 'content': 'You are the first adventurer here and have been made an Admin.'})
                    emit(MESSAGE_OUT, {'type': 'system', 'content': "Let's set up your world! What's the name of this world?"})
                    return True
        except Exception:
            pass
        return True

    if sub == 'login':
        try:
            joined = " ".join(args[1:])
            display_name, password = [p.strip() for p in joined.split('|', 1)]
        except Exception:
            emit(MESSAGE_OUT, {'type': 'error', 'content': 'Usage: /auth login <display_name> | <password>'})
            return True
        display_name = ctx.strip_quotes(display_name)
        password = ctx.strip_quotes(password)
        ok, err, emits2, broadcasts2 = login_existing(world, sid, display_name, password, ctx.sessions, ctx.admins)
        if not ok:
            emit(MESSAGE_OUT, {'type': 'error', 'content': err or 'Invalid name or password.'})
            return True
        for p in emits2:
            emit(MESSAGE_OUT, p)
        for room_id, payload in broadcasts2:
            ctx.broadcast_to_room(room_id, payload, sid)
        return True

    emit(MESSAGE_OUT, {'type': 'error', 'content': 'Unknown /auth subcommand. Use create or login.'})
    return True
